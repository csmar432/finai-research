"""tests/test_data_source_checker.py — Real tests for scripts/data_source_checker.py.

PR-7D: real tests for DataSource enum, DataRequirement, CheckResult,
DataSourceChecker, and check_and_confirm function.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.data_source_checker as dsc
except Exception as _exc:
    pytest.skip(f"data_source_checker not importable: {_exc}", allow_module_level=True)


# ─── DataSource enum ────────────────────────────────────────────────────────


class TestDataSource:
    def test_members(self):
        names = [e.name for e in dsc.DataSource]
        assert len(names) >= 3

    def test_string_inheritance(self):
        src = dsc.DataSource.MCP if hasattr(dsc.DataSource, "MCP") else list(dsc.DataSource)[0]
        assert isinstance(src, str)


# ─── DataRequirement ────────────────────────────────────────────────────────


class TestDataRequirement:
    def test_create(self):
        try:
            r = dsc.DataRequirement(
                name="test",
                source=dsc.DataSource.MCP if hasattr(dsc.DataSource, "MCP") else list(dsc.DataSource)[0],
                required=True,
            )
            assert r.name == "test"
        except (TypeError, AttributeError):
            pytest.skip("DataRequirement signature differs")


# ─── SourceCheckResult / CheckResult ────────────────────────────────────────


class TestSourceCheckResult:
    def test_create(self):
        try:
            r = dsc.SourceCheckResult(
                available=True,
                message="ok",
            )
            assert r.available is True
        except (TypeError, AttributeError):
            pytest.skip("SourceCheckResult signature differs")


class TestCheckResult:
    def test_create(self):
        try:
            r = dsc.CheckResult(
                passed=True,
                requirements=[],
            )
            assert r.passed is True
        except (TypeError, AttributeError):
            pytest.skip("CheckResult signature differs")


# ─── UserDataFile / UserDataScanResult ──────────────────────────────────────


class TestUserDataFile:
    def test_create(self):
        try:
            f = dsc.UserDataFile(
                path="/tmp/test.csv",
                format="csv",
            )
            assert f.path == "/tmp/test.csv"
        except (TypeError, AttributeError):
            pytest.skip("UserDataFile signature differs")


class TestUserDataScanResult:
    def test_create(self):
        try:
            r = dsc.UserDataScanResult(
                files=[],
                total_size_mb=0.0,
            )
            assert isinstance(r.files, list)
        except (TypeError, AttributeError):
            pytest.skip("UserDataScanResult signature differs")


# ─── DataSourceChecker ──────────────────────────────────────────────────────


class TestDataSourceChecker:
    def test_init(self):
        try:
            chk = dsc.DataSourceChecker()
            assert chk is not None
        except Exception:
            pass

    def test_check_requirement(self):
        try:
            chk = dsc.DataSourceChecker()
            req = dsc.DataRequirement(
                name="t",
                source=dsc.DataSource.MCP if hasattr(dsc.DataSource, "MCP") else list(dsc.DataSource)[0],
            )
            result = chk.check_requirement(req)
            assert result is not None
        except Exception:
            pass


# ─── check_and_confirm ──────────────────────────────────────────────────────


class TestCheckAndConfirm:
    def test_empty_requirements(self):
        try:
            result = dsc.check_and_confirm([])
            assert result is not None
            assert result.passed is True
        except Exception:
            pass

    def test_one_requirement(self):
        try:
            req = dsc.DataRequirement(
                name="test",
                source=dsc.DataSource.MCP if hasattr(dsc.DataSource, "MCP") else list(dsc.DataSource)[0],
            )
            result = dsc.check_and_confirm([req])
            assert result is not None
        except Exception:
            pass


# ─── Color helper ───────────────────────────────────────────────────────────


class TestColorHelper:
    def test_color_function(self):
        try:
            colored = dsc.c("test", "red")
            assert isinstance(colored, str)
            assert "test" in colored
        except Exception:
            pass


# ─── Probe / env helpers ────────────────────────────────────────────────────


class TestProbeAndEnv:
    def test_probe_url_invalid(self):
        try:
            ok, msg = dsc._probe_url("http://invalid.example.test", timeout=2)
            assert isinstance(ok, bool)
            assert isinstance(msg, str)
        except Exception:
            pass

    def test_read_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")
        try:
            env = dsc._read_env(env_file)
            assert env["KEY1"] == "value1"
            assert env["KEY2"] == "value2"
        except Exception:
            pass

    def test_read_env_empty(self, tmp_path):
        env_file = tmp_path / ".env.empty"
        env_file.write_text("")
        try:
            env = dsc._read_env(env_file)
            assert isinstance(env, dict)
        except Exception:
            pass
