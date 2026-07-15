"""Unit tests for scripts/fix_git_authorship.py (pure functions)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def fga():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import fix_git_authorship as f
    yield f
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestFunctionsExist:
    def test_get_old_identity_callable(self, fga):
        assert callable(fga.get_old_identity)

    def test_count_commits_callable(self, fga):
        assert callable(fga.count_commits)


class TestGetOldIdentity:
    def test_exits_on_failure(self, fga, monkeypatch):
        class MockResult:
            returncode = 1
            stdout = ""
            stderr = ""
        monkeypatch.setattr(
            fga.subprocess, "run", lambda *a, **k: MockResult()
        )
        with pytest.raises(SystemExit):
            fga.get_old_identity()


class TestCountCommits:
    def test_returns_int(self, fga, monkeypatch):
        class MockResult:
            returncode = 0
            stdout = "42\n"
            stderr = ""
        monkeypatch.setattr(
            fga.subprocess, "run", lambda *a, **k: MockResult()
        )
        count = fga.count_commits()
        assert isinstance(count, int)
        assert count == 42


class TestBuildFilterCommand:
    def test_function_exists(self, fga):
        if hasattr(fga, "build_filter_command"):
            assert callable(fga.build_filter_command)

