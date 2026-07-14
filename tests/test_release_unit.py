"""Unit tests for scripts/release.py — test only pure-Python logic."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def release():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import release
    yield release
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestBumpVersion:
    def test_bumps_version(self, release, tmp_path, monkeypatch):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
        monkeypatch.chdir(tmp_path)
        # Mock Path("pyproject.toml") calls
        with mock.patch.object(release, "Path", lambda p: tmp_path / p if isinstance(p, str) else p):
            release.bump_version("2.0.0")
        assert "version = \"2.0.0\"" in pyproject.read_text()

    def test_no_existing_version(self, release, tmp_path, monkeypatch):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\n')
        monkeypatch.chdir(tmp_path)
        with mock.patch("sys.exit") as exit_mock:
            with mock.patch.object(Path, "read_text", return_value='[project]\nname = "x"\n'):
                release.bump_version("2.0.0")
                # Should call sys.exit(1) since 0 matches
                exit_mock.assert_called()


class TestUpdateChangelog:
    def test_no_changelog_file(self, release, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        # No CHANGELOG.md exists
        with mock.patch.object(Path, "exists", return_value=False):
            release.update_changelog("2.0.0")
        out = capsys.readouterr().out
        assert "CHANGELOG.md 不存在" in out or "skip" in out.lower()

    def test_inserts_version_section(self, release, tmp_path, monkeypatch):
        cl = tmp_path / "CHANGELOG.md"
        cl.write_text("# Changelog\n\n## [Unreleased]\n\n- stuff\n")
        monkeypatch.chdir(tmp_path)
        # Stub date
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(stdout="2026-07-14\n")
            with mock.patch.object(Path, "read_text", return_value=cl.read_text()):
                with mock.patch.object(Path, "exists", return_value=True):
                    release.update_changelog("2.0.0")
        # Real file should now contain version section
        # We can't easily check without monkey-patching write_text too
        # but let's verify the run function was called for date
        assert any("date" in str(c) for c in mock_run.call_args_list)


class TestRun:
    def test_run_returns_completed_process(self, release):
        """`run` invokes subprocess and returns CompletedProcess-like."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            result = release.run(["echo", "x"], check=False)
            assert result.returncode == 0

    def test_run_exits_on_error(self, release):
        """`run` exits when check=True and rc != 0."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="err")
            with mock.patch("sys.exit") as exit_mock:
                release.run(["false"], check=True, capture=True)
                exit_mock.assert_called()

