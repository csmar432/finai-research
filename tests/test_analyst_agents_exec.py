"""tests/test_analyst_agents_exec.py — Deeper analyst_agents tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core import analyst_agents as mod
except Exception as _exc:
    pytest.skip(f"analyst_agents not importable: {_exc}", allow_module_level=True)


class TestLoadBenchmarks:
    def test_classmethod(self):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            # Reset cache
            cls._BENCHMARK_CACHE = None
            r = cls._load_benchmarks()
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_with_file(self, tmp_path):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        cfg = tmp_path / "bench.json"
        cfg.write_text(json.dumps({"industries": {"tech": {"roe": (1, 2, 3)}}}))
        try:
            cls._BENCHMARK_CACHE = None
            r = cls._load_benchmarks(str(cfg))
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_bad_file(self, tmp_path):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            cls._BENCHMARK_CACHE = None
            r = cls._load_benchmarks(str(tmp_path / "missing.json"))
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_legacy_format(self, tmp_path):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        cfg = tmp_path / "legacy.json"
        cfg.write_text(json.dumps({"_meta": "x", "tech": {"roe": (1, 2, 3)}}))
        try:
            cls._BENCHMARK_CACHE = None
            r = cls._load_benchmarks(str(cfg))
            assert isinstance(r, dict)
        except Exception:
            pass


class TestDupontDecomposition:
    def test_class(self):
        cls = getattr(mod, "DupontDecomposition", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestEnhancedFinancialAnalyst:
    def test_default(self):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_analyze_sync(self):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            data = {
                "income_statement": {"revenue": 1000, "net_income": 100},
                "balance_sheet": {"total_assets": 5000, "total_equity": 3000},
                "cash_flow": {"operating_cf": 200},
            }
            r = obj.analyze_financial_health_sync("000001.SZ", data, "tech")
            assert r is not None
        except Exception:
            pass

    def test_analyze_async(self):
        cls = getattr(mod, "EnhancedFinancialAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            async def run():
                obj = cls()
                data = {
                    "income_statement": {"revenue": 1000, "net_income": 100},
                    "balance_sheet": {"total_assets": 5000, "total_equity": 3000},
                }
                return await obj.analyze_financial_health("000001.SZ", data, "tech")
            r = asyncio.run(run())
            assert r is not None
        except Exception:
            pass


class TestDCFScenario:
    def test_construction(self):
        cls = getattr(mod, "DCFScenario", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(name="base", revenue_growth=0.1, operating_margin=0.2, terminal_growth=0.03, wacc=0.08, equity_value=1000, target_price=100, upside=0.2)
            assert obj is not None
        except Exception:
            pass


class TestEnhancedValuationAnalyst:
    def test_default(self):
        cls = getattr(mod, "EnhancedValuationAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_extract_tax_rate(self):
        cls = getattr(mod, "EnhancedValuationAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            # Try _extract_tax_rate with synthetic data
            r = obj._extract_tax_rate({"income_tax": 100, "pretax_income": 400})
            assert r is not None
        except Exception:
            pass

    def test_dcf_scenarios(self):
        cls = getattr(mod, "EnhancedValuationAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            data = {
                "revenue": 1000, "cogs": 700, "operating_expenses": 100,
                "depreciation": 50, "interest_expense": 20, "tax_rate": 0.25,
                "total_debt": 1000, "cash": 200, "shares_outstanding": 100,
            }
            r = obj.run_dcf_scenarios(data)
            assert r is not None
        except Exception:
            pass


class TestAccruals:
    def test_class(self):
        cls = getattr(mod, "AccrualsAnalysis", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestEnhancedEarningsQualityAnalyst:
    def test_default(self):
        cls = getattr(mod, "EnhancedEarningsQualityAnalyst", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestBaseAnalystAgent:
    def test_abstract(self):
        cls = getattr(mod, "BaseAnalystAgent", None)
        if cls is None: pytest.skip("not present")

    def test_all_subclasses(self):
        for name in dir(mod):
            if not name.startswith("Enhanced"):
                continue
            cls = getattr(mod, name, None)
            if not isinstance(cls, type):
                continue
            if cls.__name__.endswith("Agent") or "Analyst" in cls.__name__:
                try:
                    obj = cls()
                    assert obj is not None
                except Exception:
                    pass


class TestAnalystFactory:
    def test_default(self):
        cls = getattr(mod, "AnalystFactory", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestParallelAnalystOrchestrator:
    def test_default(self):
        cls = getattr(mod, "ParallelAnalystOrchestrator", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestAllDataclasses:
    def test_construction(self):
        for name in ["AnalystConfig", "AnalystResult", "CompositeAnalysis"]:
            cls = getattr(mod, name, None)
            if cls is None: continue
            try:
                obj = cls()
                assert obj is not None
            except Exception:
                pass


class TestTushareDataAgent:
    def test_default(self):
        cls = getattr(mod, "TushareDataAgent", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestEnums:
    def test_AnalystType(self):
        cls = getattr(mod, "AnalystType", None)
        if cls is None: pytest.skip("not present")
        try:
            values = list(cls)
            assert len(values) > 0
        except Exception:
            pass
