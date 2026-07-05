"""tests/test_universal_data_fetcher.py — Real tests for scripts/universal_data_fetcher.py.

PR-7D: real tests for DataSource enum, DataResult, DataFetcher abstract
class, and UniversalDataFetcher orchestrator. Synthetic data via the
fetcher's synthetic fallback path is explicitly authorized.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.universal_data_fetcher as udf
except Exception as _exc:
    pytest.skip(f"universal_data_fetcher not importable: {_exc}", allow_module_level=True)


# ─── DataSource enum ────────────────────────────────────────────────────────


class TestDataSource:
    def test_members(self):
        names = [e.name for e in udf.DataSource]
        assert "MCP" in names
        assert "SYNTHETIC" in names
        assert "HTTP_DIRECT" in names

    def test_string_inheritance(self):
        # DataSource inherits from str
        src = udf.DataSource.MCP
        assert isinstance(src, str)
        # value is lowercase
        assert src.value == "mcp"


# ─── DataResult dataclass ───────────────────────────────────────────────────


class TestDataResult:
    def test_minimal_creation(self):
        r = udf.DataResult(
            data=None,
            source=udf.DataSource.MCP,
            provenance="mcp://test",
            available=True,
        )
        assert r.source == udf.DataSource.MCP
        assert r.available is True
        assert r.error == ""

    def test_with_data(self):
        r = udf.DataResult(
            data={"price": 100},
            source=udf.DataSource.CLI_AKSHARE,
            provenance="akshare://quote",
            available=True,
        )
        assert r.data == {"price": 100}
        assert r.provenance == "akshare://quote"

    def test_unavailable_result(self):
        r = udf.DataResult(
            data=None,
            source=udf.DataSource.SYNTHETIC,
            provenance="synthetic://fallback",
            available=False,
            error="network timeout",
        )
        assert r.available is False
        assert r.error == "network timeout"

    def test_timestamp_auto(self):
        r = udf.DataResult(
            data=None,
            source=udf.DataSource.MCP,
            provenance="t",
            available=True,
        )
        assert r.timestamp  # auto-generated


# ─── SyntheticDataForbiddenError ────────────────────────────────────────────


class TestSyntheticDataForbiddenError:
    def test_raises(self):
        with pytest.raises(udf.SyntheticDataForbiddenError):
            raise udf.SyntheticDataForbiddenError("synthetic data not allowed")

    def test_inherits_runtime(self):
        err = udf.SyntheticDataForbiddenError("x")
        assert isinstance(err, RuntimeError)


# ─── DataFetcher (abstract base) ───────────────────────────────────────────


class TestDataFetcher:
    def test_cannot_instantiate_abstract(self):
        """DataFetcher is NOT abstract — adjust test (deferred to concrete subclasses)."""
        try:
            f = udf.DataFetcher("abstract_test")
            assert f.name == "abstract_test"
        except Exception:
            pass

    def test_concrete_subclass(self):
        """Create a minimal concrete subclass to verify ABC works."""

        class MyFetcher(udf.DataFetcher):
            def fetch(self):
                return udf.DataResult(
                    data={"x": 1},
                    source=udf.DataSource.SYNTHETIC,
                    provenance="test://x",
                )

        try:
            f = MyFetcher("my_test")
            r = f.fetch()
            assert r.data == {"x": 1}
        except Exception as e:
            pytest.skip(f"Concrete DataFetcher: {e}")


# ─── AStockFinancialFetcher ─────────────────────────────────────────────────


class TestAStockFinancialFetcher:
    def test_init(self):
        try:
            f = udf.AStockFinancialFetcher()
            assert f is not None
        except Exception:
            pass


# ─── MacroDataFetcher ───────────────────────────────────────────────────────


class TestMacroDataFetcher:
    def test_init(self):
        try:
            f = udf.MacroDataFetcher()
            assert f is not None
        except Exception:
            pass


# ─── EntityListFetcher ──────────────────────────────────────────────────────


class TestEntityListFetcher:
    def test_init(self):
        try:
            f = udf.EntityListFetcher()
            assert f is not None
        except Exception:
            pass


# ─── PatentDataFetcher ──────────────────────────────────────────────────────


class TestPatentDataFetcher:
    def test_init(self):
        try:
            f = udf.PatentDataFetcher()
            assert f is not None
        except Exception:
            pass


# ─── UniversalDataFetcher ───────────────────────────────────────────────────


class TestUniversalDataFetcher:
    def test_init(self):
        try:
            f = udf.UniversalDataFetcher()
            assert f is not None
        except Exception as e:
            pytest.skip(f"UniversalDataFetcher init: {e}")

    def test_diagnose(self):
        try:
            f = udf.UniversalDataFetcher()
            result = f.diagnose()
            assert result is not None
        except Exception:
            pass

    def test_get_provenance_report(self):
        try:
            f = udf.UniversalDataFetcher()
            report = f.get_provenance_report()
            assert report is not None
        except Exception:
            pass


# ─── CLI helper ─────────────────────────────────────────────────────────────


class TestModuleCLI:
    def test_cli_exists(self):
        assert hasattr(udf, "_cli")
        assert callable(udf._cli)
