"""Unit tests for scripts/startup_check.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def sc():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import startup_check
    yield startup_check
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestCheckItem:
    def test_init(self, sc):
        item = sc.CheckItem(category="X", name="Y", status="✅", message="ok")
        assert item.category == "X"
        assert item.name == "Y"
        assert item.status == "✅"
        assert item.message == "ok"
        assert item.fix_hint == ""

    def test_with_fix_hint(self, sc):
        item = sc.CheckItem(category="X", name="Y", status="❌", message="x", fix_hint="fix")
        assert item.fix_hint == "fix"


class TestCheckPythonVersion:
    def test_passes_for_py310(self, sc):
        """When version is 3.10, status is ✅."""
        vi_tuple = (3, 10, 0, "final", 0)
        # sc.check_python_version does `v = sys.version_info`, then access .major/.minor
        # Simulate by patching sys.version_info in module namespace
        with mock.patch.object(sc.sys, "version_info") as vi:
            vi.major = vi_tuple[0]
            vi.minor = vi_tuple[1]
            vi.micro = vi_tuple[2]
            item = sc.check_python_version()
        assert item.status == "✅"

    def test_passes_for_py312(self, sc):
        vi_tuple = (3, 12, 0, "final", 0)
        with mock.patch.object(sc.sys, "version_info") as vi:
            vi.major = vi_tuple[0]
            vi.minor = vi_tuple[1]
            vi.micro = vi_tuple[2]
            item = sc.check_python_version()
        assert item.status == "✅"

    def test_fails_for_py39(self, sc):
        vi_tuple = (3, 9, 0, "final", 0)
        with mock.patch.object(sc.sys, "version_info") as vi:
            vi.major = vi_tuple[0]
            vi.minor = vi_tuple[1]
            vi.micro = vi_tuple[2]
            item = sc.check_python_version()
        assert item.status == "❌"

    def test_fails_for_py2(self, sc):
        vi_tuple = (2, 7, 0, "final", 0)
        with mock.patch.object(sc.sys, "version_info") as vi:
            vi.major = vi_tuple[0]
            vi.minor = vi_tuple[1]
            vi.micro = vi_tuple[2]
            item = sc.check_python_version()
        assert item.status == "❌"


class TestCheckLLMKeys:
    def test_empty_when_nothing_set(self, sc, monkeypatch, tmp_path):
        """Returns items with status=❌ when keys are missing."""
        # Set empty env
        for k in ["DEEPSEEK_API_KEY", "RELAY_API_KEY", "OLLAMA_ENABLED"]:
            monkeypatch.delenv(k, raising=False)
        # Use a tmp .env.local that doesn't exist
        monkeypatch.setattr(sc, "_PROJECT_ROOT", tmp_path)
        items = sc.check_llm_keys()
        assert len(items) == 3
        # DEEPSEEK and RELAY should be ❌, OLLAMA may be ✅
        statuses = {i.name: i.status for i in items}
        assert statuses["DEEPSEEK_API_KEY"] == "❌"
        assert statuses["RELAY_API_KEY"] == "❌"

    def test_passes_with_key_set(self, sc, monkeypatch, tmp_path):
        """DEEPSEEK_API_KEY set → ✅."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234")
        monkeypatch.delenv("RELAY_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_ENABLED", raising=False)
        monkeypatch.setattr(sc, "_PROJECT_ROOT", tmp_path)
        items = sc.check_llm_keys()
        deepseek_item = [i for i in items if i.name == "DEEPSEEK_API_KEY"][0]
        assert deepseek_item.status == "✅"

    def test_rejects_placeholder(self, sc, monkeypatch, tmp_path):
        """YOUR_KEY placeholder is treated as missing."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "YOUR_KEY_HERE")
        monkeypatch.delenv("RELAY_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_ENABLED", raising=False)
        monkeypatch.setattr(sc, "_PROJECT_ROOT", tmp_path)
        items = sc.check_llm_keys()
        item = [i for i in items if i.name == "DEEPSEEK_API_KEY"][0]
        assert item.status == "❌"

    def test_ollama_default_passes(self, sc, monkeypatch, tmp_path):
        """When OLLAMA_ENABLED is unset, defaults to ✅."""
        monkeypatch.delenv("OLLAMA_ENABLED", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("RELAY_API_KEY", raising=False)
        monkeypatch.setattr(sc, "_PROJECT_ROOT", tmp_path)
        items = sc.check_llm_keys()
        item = [i for i in items if i.name == "OLLAMA_ENABLED"][0]
        assert item.status == "✅"

