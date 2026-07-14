"""Unit tests for scripts/keychain_manager.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def kcm():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import keychain_manager
    yield keychain_manager
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestPlatformDetection:
    def test_is_macos_true_on_darwin(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert kcm._is_macos() is True

    def test_is_macos_false_on_linux(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert kcm._is_macos() is False

    def test_is_macos_false_on_windows(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert kcm._is_macos() is False


class TestKeychainAvailable:
    def test_false_on_non_macos(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert kcm._keychain_available() is False

    def test_returns_false_on_security_error(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(kcm, "_is_macos", lambda: True)
        # Mock subprocess.run to return non-zero
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1)
            assert kcm._keychain_available() is False

    def test_returns_true_on_security_success(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(kcm, "_is_macos", lambda: True)
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            assert kcm._keychain_available() is True

    def test_handles_timeout(self, kcm, monkeypatch):
        """When security CLI raises, _keychain_available returns False."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(kcm, "_is_macos", lambda: True)
        import subprocess
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("security", 2)):
            assert kcm._keychain_available() is False

    def test_handles_file_not_found(self, kcm, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(kcm, "_is_macos", lambda: True)
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            assert kcm._keychain_available() is False


class TestFromKeychain:
    def test_returns_none_when_keychain_unavailable(self, kcm, monkeypatch):
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        assert kcm._from_keychain("FOO") is None


class TestGetSecret:
    def test_returns_env_var(self, kcm, monkeypatch):
        monkeypatch.setenv("TEST_KCM_VAR", "hello")
        # Keychain disabled
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        monkeypatch.setattr(kcm, "_from_keychain", lambda x: None)
        assert kcm.get_secret("TEST_KCM_VAR") == "hello"

    def test_returns_none_for_missing(self, kcm, monkeypatch):
        monkeypatch.delenv("DEFINITELY_NOT_SET_123", raising=False)
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        monkeypatch.setattr(kcm, "_from_keychain", lambda x: None)
        assert kcm.get_secret("DEFINITELY_NOT_SET_123") is None

    def test_empty_string_treated_as_missing(self, kcm, monkeypatch):
        """Empty string env var is treated as 'not configured'."""
        monkeypatch.setenv("TEST_EMPTY_VAR", "")
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        monkeypatch.setattr(kcm, "_from_keychain", lambda x: None)
        assert kcm.get_secret("TEST_EMPTY_VAR") is None

    def test_prefer_env_skips_keychain(self, kcm, monkeypatch):
        monkeypatch.setenv("TEST_KCM_E", "from_env")
        # Even if keychain would have a value, prefer=env should NOT call keychain.
        with mock.patch.object(kcm, "_from_keychain") as mock_kc:
            mock_kc.return_value = "from_keychain"
            assert kcm.get_secret("TEST_KCM_E", prefer="env") == "from_env"
            mock_kc.assert_not_called()

    def test_prefer_keychain_skips_env(self, kcm, monkeypatch):
        monkeypatch.setenv("TEST_KCM_K", "from_env")
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", True)
        # Even if env has a value, prefer=keychain should NOT read env.
        with mock.patch.object(kcm, "_from_keychain", return_value="from_kc") as mock_kc:
            assert kcm.get_secret("TEST_KCM_K", prefer="keychain") == "from_kc"
            mock_kc.assert_called_once()

    def test_auto_uses_keychain_first(self, kcm, monkeypatch):
        monkeypatch.setenv("TEST_KCM_AUTO", "from_env")
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", True)
        # When keychain has a value, return it without checking env.
        with mock.patch.object(kcm, "_from_keychain", return_value="from_kc"):
            assert kcm.get_secret("TEST_KCM_AUTO", prefer="auto") == "from_kc"


class TestGetSecretOrWarn:
    def test_returns_value(self, kcm, monkeypatch):
        monkeypatch.setenv("TEST_KCM_OW", "value")
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        monkeypatch.setattr(kcm, "_from_keychain", lambda x: None)
        assert kcm.get_secret_or_warn("TEST_KCM_OW") == "value"

    def test_warns_on_missing(self, kcm, monkeypatch):
        monkeypatch.delenv("DEFINITELY_NOT_SET_OW", raising=False)
        monkeypatch.setattr(kcm, "_KEYCHAIN_OK", False)
        monkeypatch.setattr(kcm, "_from_keychain", lambda x: None)
        with pytest.warns(UserWarning, match="DEFINITELY_NOT_SET_OW"):
            assert kcm.get_secret_or_warn("DEFINITELY_NOT_SET_OW") is None


class TestHealthCheck:
    def test_health_check_returns_dict(self, kcm):
        h = kcm.health_check()
        assert isinstance(h, dict)
        assert "platform" in h
        assert "keychain_available" in h
        assert "keychain_service" in h
        assert "env_loaded" in h

    def test_health_check_platform_is_string(self, kcm):
        h = kcm.health_check()
        assert isinstance(h["platform"], str)

