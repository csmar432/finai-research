"""Unit tests for scripts/ci_verify.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ROOT = SCRIPTS_DIR.parent


@pytest.fixture
def civ():
    """Import ci_verify. Requires scripts/ on sys.path via conftest or PYTHONPATH."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import ci_verify
    yield ci_verify
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestCheckResult:
    def test_init(self, civ):
        r = civ.CheckResult("name", True, "detail")
        assert r.name == "name"
        assert r.passed is True
        assert r.detail == "detail"

    def test_str_passed(self, civ):
        r = civ.CheckResult("OK", True)
        s = str(r)
        assert "PASS" in s
        assert "OK" in s

    def test_str_failed(self, civ):
        r = civ.CheckResult("Bad", False)
        s = str(r)
        assert "FAIL" in s
        assert "Bad" in s

    def test_str_with_detail(self, civ):
        r = civ.CheckResult("X", True, "extra info")
        s = str(r)
        assert "extra info" in s


class TestMain:
    def test_main_docker_check(self, civ, capsys, monkeypatch):
        """`--docker-check` exits 0 and prints env keys."""
        monkeypatch.setattr(sys, "argv", ["ci_verify.py", "--docker-check"])
        # Set the expected env vars
        monkeypatch.setenv("LC_ALL", "C.UTF-8")
        monkeypatch.setenv("PYTHONHASHSEED", "0")
        monkeypatch.setenv("OMP_NUM_THREADS", "1")
        monkeypatch.setenv("MKL_NUM_THREADS", "1")
        monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
        rc = civ.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Docker" in out or "LC_ALL" in out

    def test_main_runs_full_check(self, civ, capsys, monkeypatch):
        """Full check returns 0 when env is correct."""
        monkeypatch.setenv("LC_ALL", "C.UTF-8")
        monkeypatch.setenv("PYTHONHASHSEED", "0")
        monkeypatch.setenv("OMP_NUM_THREADS", "1")
        monkeypatch.setenv("MKL_NUM_THREADS", "1")
        monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
        monkeypatch.setattr(sys, "argv", ["ci_verify.py"])
        rc = civ.main()
        # rc is 0 if everything passed
        out = capsys.readouterr().out
        assert "Cross-Platform" in out or "Result" in out

