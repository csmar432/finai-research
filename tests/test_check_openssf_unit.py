"""Unit tests for scripts/check_openssf.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def osf():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import check_openssf
    yield check_openssf
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestHelpers:
    def test_read_returns_text(self, osf, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert osf._read(f) == "hello"

    def test_read_missing_returns_empty(self, osf, tmp_path):
        f = tmp_path / "missing.txt"
        assert osf._read(f) == ""


class TestCountTests:
    def test_returns_zero_when_dir_missing(self, osf, tmp_path, monkeypatch):
        monkeypatch.setattr(osf, "ROOT", tmp_path / "no_tests")
        assert osf._count_tests() == 0

    def test_counts_test_functions(self, osf, tmp_path, monkeypatch):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text(
            "def test_one(): pass\n"
            "def test_two(): pass\n"
        )
        (tests_dir / "test_b.py").write_text(
            "def test_three(): pass\n"
        )
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        n = osf._count_tests()
        assert n == 3


class TestHasHardcodedSecrets:
    def test_returns_true_no_secrets(self, osf, tmp_path, monkeypatch):
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        (script_dir / "safe.py").write_text("# no secrets here\nx = 1\n")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, bad = osf._has_hardcoded_secrets()
        assert ok is True
        assert bad == []

    def test_detects_api_key_literal(self, osf, tmp_path, monkeypatch):
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        (script_dir / "bad.py").write_text('API_KEY = "abcdef1234567890abcdef1234"\n')
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, bad = osf._has_hardcoded_secrets()
        assert ok is False
        assert len(bad) > 0

    def test_skips_placeholder_code(self, osf, tmp_path, monkeypatch):
        """Files with example.com / <your_ are skipped."""
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        (script_dir / "demo.py").write_text(
            'api_key = "sk-1234567890abcdef1234"\n'
            'example.com is here\n'
        )
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, bad = osf._has_hardcoded_secrets()
        assert ok is True

    def test_skips_legacy(self, osf, tmp_path, monkeypatch):
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "old.py").write_text('secret = "abcdefghijklmnopqrstuvwxyz12"\n')
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, bad = osf._has_hardcoded_secrets()
        # legacy/ path is excluded
        assert ok is True


class TestRunCheck:
    def test_special_s2_runs_secret_scan(self, osf):
        ok, _ = osf.run_check("S2", "scan", None)
        # Either no secrets, or secrets detected — depends on project state
        assert isinstance(ok, bool)

    def test_special_any_dir(self, osf, tmp_path, monkeypatch):
        (tmp_path / "dirA").mkdir()
        (tmp_path / "dirA" / "f.txt").write_text("x")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("X1", "dir test", "dirA", None, "any")
        assert ok is True
        assert "non-empty" in msg

    def test_special_test_count_50(self, osf, tmp_path, monkeypatch):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        for i in range(60):
            (tests_dir / f"test_a{i}.py").write_text("def test_x(): pass\n")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("Q1", "test count", "tests", None, "test_count_50")
        assert ok is True
        assert "60" in msg

    def test_missing_file(self, osf, tmp_path, monkeypatch):
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("X", "missing", "nofile.py", lambda c: True)
        assert ok is False
        assert "not found" in msg

    def test_empty_file(self, osf, tmp_path, monkeypatch):
        f = tmp_path / "empty.py"
        f.write_text("")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("X", "empty", "empty.py", lambda c: True)
        assert ok is False

    def test_passing_content(self, osf, tmp_path, monkeypatch):
        f = tmp_path / "good.py"
        f.write_text("hello world")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("X", "check", "good.py", lambda c: "hello" in c)
        assert ok is True

    def test_failing_content(self, osf, tmp_path, monkeypatch):
        f = tmp_path / "bad.py"
        f.write_text("hello world")
        monkeypatch.setattr(osf, "ROOT", tmp_path)
        ok, msg = osf.run_check("X", "check", "bad.py", lambda c: "missing" in c)
        assert ok is False
        assert "failed" in msg


class TestChecksList:
    def test_checks_is_nonempty_list(self, osf):
        assert len(osf.CHECKS) > 0
        for check in osf.CHECKS:
            assert isinstance(check, tuple)
            assert len(check) >= 3
            cid = check[0]
            assert isinstance(cid, str)

    def test_check_ids_are_unique(self, osf):
        ids = [c[0] for c in osf.CHECKS]
        assert len(ids) == len(set(ids))

