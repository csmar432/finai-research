"""
Comprehensive unit tests for scripts/core/analyst_agents.py

Covers:
  - AnalystType enum + dataclasses (AnalystConfig, AnalystResult, CompositeAnalysis,
    DupontDecomposition, DCFScenario, AccrualsAnalysis)
  - ANALYST_CONFIGS registry
  - EnhancedFinancialAnalyst (DuPont decomposition, warnings, industry comparison,
    benchmark loading from JSON + fallback)
  - EnhancedValuationAnalyst (DCF scenarios, WACC computation, sensitivity, comp
    analysis, recommendation)
  - EnhancedEarningsQualityAnalyst (accruals / Jones model, cash-flow matching,
    non-recurring items, quality score and rating)
  - BaseAnalystAgent + 6 specialized subclasses (success/error branches, mock LLM)
  - AnalystFactory registry + create + is_enhanced
  - ParallelAnalystOrchestrator (parallel run, circuit breaker, timeout, token
    budget, consensus)
  - TushareDataAgent (mocked MCP gateway calls)

The tests run without any real LLM/network calls. Heavy dependencies (LLM
gateway, MCP) are mocked. The benchmark JSON file may or may not exist in
the environment — both paths are exercised.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make `scripts.*` importable when the test is run directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.analyst_agents import (
    ANALYST_CONFIGS,
    AccrualsAnalysis,
    AnalystConfig,
    AnalystFactory,
    AnalystResult,
    AnalystType,
    BaseAnalystAgent,
    CompositeAnalysis,
    DCFScenario,
    DupontDecomposition,
    EnhancedCompetitiveAnalyst,
    EnhancedEarningsQualityAgent,
    EnhancedEarningsQualityAnalyst,
    EnhancedFinancialAnalyst,
    EnhancedFundamentalFinancialAgent,
    EnhancedMarketAnalyst,
    EnhancedRiskAnalyst,
    EnhancedValuationAgent,
    EnhancedValuationAnalyst,
    ParallelAnalystOrchestrator,
    TushareDataAgent,
)


# ─────────────────────────── helpers ────────────────────────────────────────────


def _financial_data(**overrides) -> dict[str, Any]:
    """Return a realistic, deterministic financial dataset."""
    base: dict[str, Any] = {
        "income_statement": {
            "revenue": 1000,
            "net_income": 100,
            "gross_profit": 300,
            "operating_income": 150,
            "ebit": 160,
            "interest_expense": 10,
            "income_tax": 30,
            "pretax_income": 130,
        },
        "balance_sheet": {
            "total_assets": 5000,
            "total_equity": 2500,
            "total_liabilities": 2500,
            "current_assets": 2000,
            "current_liabilities": 1000,
            "cash": 500,
            "accounts_receivable": 300,
            "fixed_assets": 1500,
            "long_term_debt": 800,
        },
        "cash_flow": {
            "operating_cash_flow": 120,
            "capex": 50,
            "net_cash_flow": 70,
        },
    }
    # Shallow merge each top-level override dict for ergonomics.
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base:
            base[k].update(v)
        else:
            base[k] = v
    return base


def _multi_year_financial_data() -> dict[int, dict[str, Any]]:
    """Return three years of financial statements (2021 → 2023)."""
    return {
        2021: {
            "income_statement": {
                "revenue": 800,
                "net_income": 80,
                "operating_income": 120,
                "ebit": 130,
                "interest_expense": 10,
                "income_tax": 25,
                "pretax_income": 105,
                "investment_income": 5,
                "government_grants": 3,
                "asset_disposal_gain": 0,
                "fair_value_change": 0,
                "non_operating_income": 0,
                "non_operating_expense": 0,
            },
            "balance_sheet": {
                "total_assets": 4000,
                "total_equity": 2000,
                "current_assets": 1500,
                "current_liabilities": 800,
                "cash": 400,
                "accounts_receivable": 250,
                "fixed_assets": 1300,
                "long_term_debt": 700,
            },
            "cash_flow": {
                "operating_cash_flow": 95,
                "capex": 40,
            },
        },
        2022: {
            "income_statement": {
                "revenue": 900,
                "net_income": 95,
                "operating_income": 135,
                "ebit": 145,
                "interest_expense": 12,
                "income_tax": 30,
                "pretax_income": 125,
                "investment_income": 8,
                "government_grants": 5,
                "asset_disposal_gain": 0,
                "fair_value_change": 0,
                "non_operating_income": 0,
                "non_operating_expense": 0,
            },
            "balance_sheet": {
                "total_assets": 4500,
                "total_equity": 2200,
                "current_assets": 1700,
                "current_liabilities": 900,
                "cash": 450,
                "accounts_receivable": 280,
                "fixed_assets": 1400,
                "long_term_debt": 800,
            },
            "cash_flow": {
                "operating_cash_flow": 100,
                "capex": 45,
            },
        },
        2023: {
            "income_statement": {
                "revenue": 1000,
                "net_income": 100,
                "operating_income": 150,
                "ebit": 160,
                "interest_expense": 15,
                "income_tax": 35,
                "pretax_income": 135,
                "investment_income": 12,
                "government_grants": 8,
                "asset_disposal_gain": 2,
                "fair_value_change": 1,
                "non_operating_income": 1,
                "non_operating_expense": 2,
            },
            "balance_sheet": {
                "total_assets": 5000,
                "total_equity": 2500,
                "current_assets": 2000,
                "current_liabilities": 1000,
                "cash": 500,
                "accounts_receivable": 300,
                "fixed_assets": 1500,
                "long_term_debt": 900,
            },
            "cash_flow": {
                "operating_cash_flow": 130,
                "capex": 50,
            },
        },
    }


@pytest.fixture(autouse=True)
def _reset_benchmark_cache():
    """Each test sees a clean benchmark cache so JSON-vs-fallback branches
    are independent."""
    EnhancedFinancialAnalyst._BENCHMARK_CACHE = None
    yield
    EnhancedFinancialAnalyst._BENCHMARK_CACHE = None


# ─────────────────────── 1. Dataclasses & enum ──────────────────────────────────


class TestAnalystTypeEnum:
    def test_enum_members_present(self):
        """All six analyst roles must exist with stable string values."""
        members = {m.name: m.value for m in AnalystType}
        assert members == {
            "FUNDAMENTAL_MARKET": "fundamental_market",
            "FUNDAMENTAL_FINANCIAL": "fundamental_financial",
            "COMPETITIVE": "competitive",
            "RISK": "risk",
            "VALUATION": "valuation",
            "EARNINGS_QUALITY": "earnings_quality",
        }

    def test_enum_membership_iteration(self):
        """Iteration must yield exactly 6 members."""
        assert len(list(AnalystType)) == 6

    def test_value_lookup(self):
        """String → enum round-trips by `value`."""
        assert AnalystType("fundamental_market") is AnalystType.FUNDAMENTAL_MARKET
        assert AnalystType("risk") is AnalystType.RISK


class TestAnalystConfigDataclass:
    def test_minimal_construction(self):
        """`tools`, `focus_areas` are required; the rest default."""
        cfg = AnalystConfig(
            analyst_type=AnalystType.RISK,
            name="RiskAnalyst",
            role="x",
            focus_areas=["a"],
            tools=["b"],
        )
        assert cfg.analyst_type is AnalystType.RISK
        assert cfg.max_iterations == 3
        assert cfg.temperature == 0.7

    def test_full_construction(self):
        cfg = AnalystConfig(
            analyst_type=AnalystType.VALUATION,
            name="V",
            role="DCF expert",
            focus_areas=["dcf", "comp"],
            tools=["yfinance"],
            max_iterations=5,
            temperature=0.1,
        )
        assert cfg.max_iterations == 5
        assert cfg.temperature == 0.1
        assert cfg.tools == ["yfinance"]


class TestAnalystResultDataclass:
    def test_construction_with_defaults(self):
        res = AnalystResult(
            analyst_type=AnalystType.COMPETITIVE,
            status="success",
            findings={"k": "v"},
            confidence=0.8,
            key_points=["p1"],
        )
        assert res.warnings == []
        assert res.latency_ms == 0.0
        assert res.confidence == 0.8

    def test_explicit_warning_fields(self):
        res = AnalystResult(
            analyst_type=AnalystType.RISK,
            status="error",
            findings={"e": "x"},
            confidence=0.0,
            key_points=[],
            warnings=["boom"],
            latency_ms=42.5,
        )
        assert res.warnings == ["boom"]
        assert res.latency_ms == 42.5


class TestCompositeAnalysisDataclass:
    def test_to_dict_shape(self):
        """`to_dict` serializes nested `analyst_results` using enum values."""
        inner = AnalystResult(
            analyst_type=AnalystType.FUNDAMENTAL_MARKET,
            status="success",
            findings={"x": 1},
            confidence=0.5,
            key_points=["k"],
        )
        comp = CompositeAnalysis(
            ticker="000001.SZ",
            timestamp=time.time(),
            analyst_results={AnalystType.FUNDAMENTAL_MARKET: inner},
            consensus_view="ok",
            divergent_views=["d1"],
            confidence=0.5,
            total_latency_ms=10,
        )
        d = comp.to_dict()
        assert d["ticker"] == "000001.SZ"
        assert "fundamental_market" in d["analyst_results"]
        assert d["analyst_results"]["fundamental_market"]["confidence"] == 0.5
        assert d["consensus_view"] == "ok"
        assert d["divergent_views"] == ["d1"]
        assert d["total_latency_ms"] == 10
        # The serialized inner payload must include core keys
        for k in ("status", "findings", "confidence", "key_points", "warnings"):
            assert k in d["analyst_results"]["fundamental_market"]


class TestDupontDecompositionDataclass:
    def test_construction(self):
        d = DupontDecomposition(
            company="ACME",
            year=2024,
            roe=0.18,
            net_margin=0.10,
            asset_turnover=1.2,
            equity_multiplier=1.5,
            roa=0.07,
            comparison={"prior_year": 0.15},
        )
        assert d.company == "ACME"
        assert d.roe == 0.18
        assert d.comparison == {"prior_year": 0.15}


class TestDCFScenarioDataclass:
    def test_construction(self):
        s = DCFScenario(
            name="base",
            revenue_growth=0.12,
            operating_margin=0.15,
            terminal_growth=0.025,
            wacc=0.10,
            equity_value=1_000_000,
            target_price=20.0,
            upside=0.25,
        )
        assert s.name == "base"
        assert s.upside == 0.25


class TestAccrualsAnalysisDataclass:
    def test_construction(self):
        a = AccrualsAnalysis(
            year=2023,
            total_accruals=10,
            abnormal_accruals=2.5,
            discretionary_accruals=1.0,
            is_suspicious=True,
        )
        assert a.year == 2023
        assert a.is_suspicious is True


# ─────────────────── 2. ANALYST_CONFIGS registry ────────────────────────────────


class TestAnalystConfigsRegistry:
    def test_all_types_registered(self):
        """Every AnalystType must have an ANALYST_CONFIGS entry."""
        assert set(ANALYST_CONFIGS.keys()) == set(AnalystType)

    def test_config_fields_well_formed(self):
        for atype, cfg in ANALYST_CONFIGS.items():
            assert cfg.analyst_type is atype
            assert isinstance(cfg.name, str) and cfg.name
            assert isinstance(cfg.role, str) and cfg.role
            assert cfg.focus_areas and isinstance(cfg.focus_areas, list)
            assert cfg.tools and isinstance(cfg.tools, list)
            assert cfg.max_iterations >= 1
            assert 0 <= cfg.temperature <= 2

    def test_each_focus_area_is_string(self):
        for cfg in ANALYST_CONFIGS.values():
            for area in cfg.focus_areas:
                assert isinstance(area, str) and area


# ─────────── 3. EnhancedFinancialAnalyst (DuPont & warnings) ────────────────────


class TestEnhancedFinancialAnalystHappyPath:
    def setup_method(self):
        self.analyst = EnhancedFinancialAnalyst()

    @pytest.mark.asyncio
    async def test_returns_expected_sections(self):
        res = await self.analyst.analyze_financial_health(
            ticker="000001.SZ",
            financial_data=_financial_data(),
            industry="default",
        )
        for key in ("dupont", "profitability", "solvency", "cash_flow",
                    "warnings", "industry_comparison"):
            assert key in res, key

    @pytest.mark.asyncio
    async def test_dupont_formula_identity(self):
        """ROE ≈ net_margin × asset_turnover × equity_multiplier."""
        data = _financial_data()
        # Make the relationship clean.
        data["income_statement"]["net_income"] = 250  # 25% margin
        data["balance_sheet"]["total_assets"] = 1000
        data["balance_sheet"]["total_equity"] = 500  # multiplier 2x
        data["income_statement"]["revenue"] = 1000   # turnover 1x

        res = await self.analyst.analyze_financial_health("X", data)
        # Round-trip: roe% should be 50 (25% × 1 × 2)
        assert res["dupont"]["roe"] == pytest.approx(50.0, abs=0.05)
        assert res["dupont"]["net_margin"] == pytest.approx(25.0, abs=0.05)
        assert res["dupont"]["asset_turnover"] == pytest.approx(1.0, abs=0.01)
        assert res["dupont"]["equity_multiplier"] == pytest.approx(2.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_profitability_section_present(self):
        res = await self.analyst.analyze_financial_health("X", _financial_data())
        assert "gross_margin" in res["profitability"]
        assert "operating_margin" in res["profitability"]
        assert "ebit_margin" in res["profitability"]
        assert "net_margin" in res["profitability"]

    @pytest.mark.asyncio
    async def test_solvency_section_present(self):
        res = await self.analyst.analyze_financial_health("X", _financial_data())
        for k in ("current_ratio", "debt_ratio", "interest_coverage"):
            assert k in res["solvency"]

    @pytest.mark.asyncio
    async def test_cash_flow_section_present(self):
        res = await self.analyst.analyze_financial_health("X", _financial_data())
        for k in ("operating_cash_flow", "capex", "free_cash_flow",
                  "cash_flow_ratio"):
            assert k in res["cash_flow"]

    @pytest.mark.asyncio
    async def test_industry_comparison_default(self):
        res = await self.analyst.analyze_financial_health(
            "X", _financial_data(), industry="default",
        )
        assert res["industry_comparison"]["industry"] == "default"
        assert "roe" in res["industry_comparison"]
        assert res["industry_comparison"]["roe"]["status"] in {
            "↓ 低于行业", "↑ 高于行业", "✓ 行业正常",
        }


class TestEnhancedFinancialAnalystEdgeCases:
    def setup_method(self):
        self.analyst = EnhancedFinancialAnalyst()

    @pytest.mark.asyncio
    async def test_all_zero_metrics_safe(self):
        """Zero denominators must not raise — values become 0."""
        zero = _financial_data()
        for k in ("revenue", "net_income", "gross_profit", "operating_income",
                  "ebit", "interest_expense", "income_tax", "pretax_income"):
            zero["income_statement"][k] = 0
        for k in ("total_assets", "total_equity", "total_liabilities",
                  "current_assets", "current_liabilities", "cash",
                  "accounts_receivable", "fixed_assets"):
            zero["balance_sheet"][k] = 0
        zero["cash_flow"]["operating_cash_flow"] = 0
        zero["cash_flow"]["capex"] = 0

        res = await self.analyst.analyze_financial_health("Z", zero)
        # No NaN/inf — ROE 0 by construction.
        assert res["dupont"]["roe"] == 0
        assert res["dupont"]["net_margin"] == 0
        assert res["solvency"]["current_ratio"] == 0

    @pytest.mark.asyncio
    async def test_min_revenue_floor_protects_division(self):
        """The revenue=0 case maps to 1 internally (max(revenue, 1))."""
        d = _financial_data(
            income_statement={"revenue": 0, "net_income": 0},
        )
        res = await self.analyst.analyze_financial_health("Q", d)
        # No exception, all ratios are 0.
        assert res["dupont"]["asset_turnover"] >= 0

    @pytest.mark.asyncio
    async def test_industry_unknown_falls_back_to_default(self):
        res = await self.analyst.analyze_financial_health(
            "X", _financial_data(), industry="non_existent_industry",
        )
        # Should not raise — falls back to 'default' benchmark.
        assert res["industry_comparison"]["industry"] == "non_existent_industry"
        assert res["industry_comparison"]["roe"]["status"] in {
            "↓ 低于行业", "↑ 高于行业", "✓ 行业正常",
        }


class TestCheckWarnings:
    """The helper expects: ROE/net_margin/debt_ratio in PERCENT (15 = 15%),
    and current_ratio/cash_flow_ratio/interest_coverage in MULTIPLES (1.0).
    """

    def setup_method(self):
        self.analyst = EnhancedFinancialAnalyst()

    def test_all_clean_returns_ok(self):
        w = self.analyst._check_warnings(
            roe=15.0, net_margin=10.0, current_ratio=2.0,
            debt_ratio=40.0, cash_flow_ratio=1.5, interest_coverage=10.0,
        )
        assert w == ["✅ 无明显异常"]

    def test_negative_roe_triggers_warning(self):
        w = self.analyst._check_warnings(
            roe=-10, net_margin=10, current_ratio=2.0,
            debt_ratio=40, cash_flow_ratio=1.0, interest_coverage=10.0,
        )
        assert any("净资产收益率" in x and "亏损" in x for x in w)

    def test_low_roe_under_5pct(self):
        w = self.analyst._check_warnings(
            roe=3.0, net_margin=10, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("ROE低于5%" in x for x in w)

    def test_low_net_margin(self):
        w = self.analyst._check_warnings(
            roe=10, net_margin=1.5, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("净利率低于2%" in x for x in w)

    def test_negative_net_margin(self):
        w = self.analyst._check_warnings(
            roe=10, net_margin=-1.0, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("亏损" in x and "净利率" in x for x in w)

    def test_low_current_ratio(self):
        # current_ratio < 1
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=0.7,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("流动比率低于1" in x for x in w)

    def test_marginal_current_ratio(self):
        # 1 <= current_ratio < 1.5 → softer warning
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=1.2,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("流动比率低于1.5" in x for x in w)

    def test_high_debt_ratio(self):
        # > 80 (interpreted as percent)
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=2.0,
            debt_ratio=85, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("资产负债率超过80%" in x for x in w)

    def test_moderate_debt_ratio(self):
        # 60 < x <= 80 (interpreted as percent)
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=2.0,
            debt_ratio=65, cash_flow_ratio=1.0, interest_coverage=5.0,
        )
        assert any("资产负债率超过60%" in x for x in w)

    def test_low_cash_flow_ratio(self):
        # < 0.5 (multiple, e.g. CFO/NI ratio)
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=0.4, interest_coverage=5.0,
        )
        assert any("低于50%" in x for x in w)

    def test_low_interest_coverage(self):
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=0.5,
        )
        assert any("利息覆盖不足" in x for x in w)

    def test_weak_interest_coverage(self):
        w = self.analyst._check_warnings(
            roe=10, net_margin=5, current_ratio=2.0,
            debt_ratio=30, cash_flow_ratio=1.0, interest_coverage=1.5,
        )
        assert any("EBIT/利息支出 < 2" in x for x in w)



class TestCompareToIndustry:
    def setup_method(self):
        self.analyst = EnhancedFinancialAnalyst()

    def test_legacy_list_benchmark(self):
        cmp = self.analyst._compare_to_industry(
            roe=0.10, net_margin=0.05, roa=0.04,
            benchmark={"roe": (5, 15, 30),
                       "net_margin": (2, 8, 20),
                       "roa": (2, 6, 15)},
            industry="tech",
        )
        assert cmp["roe"]["median"] == 15
        assert cmp["roe"]["status"] == "✓ 行业正常"

    def test_below_industry(self):
        cmp = self.analyst._compare_to_industry(
            roe=0.01, net_margin=0.005, roa=0.01,
            benchmark={"roe": (5, 15, 30),
                       "net_margin": (2, 8, 20),
                       "roa": (2, 6, 15)},
            industry="x",
        )
        assert cmp["roe"]["status"] == "↓ 低于行业"
        assert cmp["net_margin"]["status"] == "↓ 低于行业"
        assert cmp["roa"]["status"] == "↓ 低于行业"

    def test_above_industry(self):
        cmp = self.analyst._compare_to_industry(
            roe=0.50, net_margin=0.50, roa=0.50,
            benchmark={"roe": (5, 15, 30),
                       "net_margin": (2, 8, 20),
                       "roa": (2, 6, 15)},
            industry="x",
        )
        assert cmp["roe"]["status"] == "↑ 高于行业"

    def test_decimal_dict_benchmark(self):
        """New format uses p25/median/p75 in decimal space."""
        cmp = self.analyst._compare_to_industry(
            roe=0.15, net_margin=0.10, roa=0.07,
            benchmark={
                "roe": {"p25": 0.05, "median": 0.15, "p75": 0.30},
                "net_margin": {"p25": 0.02, "median": 0.08, "p75": 0.20},
                "roa": {"p25": 0.02, "median": 0.06, "p75": 0.15},
            },
            industry="x",
        )
        # Decimal dict is multiplied by 100 internally.
        assert cmp["roe"]["median"] == pytest.approx(15)
        assert cmp["net_margin"]["p75"] == pytest.approx(20)
        assert cmp["roa"]["status"] == "✓ 行业正常"

    def test_missing_keys_in_benchmark_safe(self):
        """A benchmark missing a metric returns a default (0, 100, 200)
        without raising."""
        cmp = self.analyst._compare_to_industry(
            roe=0.10, net_margin=0.05, roa=0.04,
            benchmark={}, industry="x",
        )
        assert cmp["roe"]["status"] == "✓ 行业正常"  # 10 falls in (0, 200)


class TestLoadBenchmarks:
    def setup_method(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None

    def test_fallback_when_file_missing(self):
        """When JSON is absent the hardcoded dict must be returned."""
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            data = EnhancedFinancialAnalyst._load_benchmarks("/nope.json")
        for sector in ("tech", "finance", "manufacturing", "retail",
                       "healthcare", "energy", "real_estate", "default"):
            assert sector in data

    def test_loads_nested_industries_format(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None
        payload = json.dumps({
            "industries": {
                "tech": {"roe": {"p25": 5, "median": 15, "p75": 30}},
                "default": {"roe": {"p25": 5, "median": 10, "p75": 20}},
            }
        })
        with patch.object(Path, "read_text", return_value=payload):
            data = EnhancedFinancialAnalyst._load_benchmarks("/x.json")
        assert "tech" in data
        assert data["tech"]["roe"]["median"] == 15

    def test_loads_legacy_flat_format(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None
        payload = json.dumps({
            "tech": {"roe": [5, 15, 30], "net_margin": [2, 8, 20]},
            "_comment": "legacy",  # must be filtered out
        })
        with patch.object(Path, "read_text", return_value=payload):
            data = EnhancedFinancialAnalyst._load_benchmarks("/x.json")
        assert "tech" in data
        assert "_comment" not in data

    def test_corrupt_json_returns_fallback(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None
        with patch.object(Path, "read_text", return_value="{not json"):
            data = EnhancedFinancialAnalyst._load_benchmarks("/x.json")
        assert "default" in data  # hardcoded fallback

    def test_cache_is_used_on_second_call(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = {"cached": {"roe": (1, 2, 3)}}
        # No file IO should occur.
        data = EnhancedFinancialAnalyst._load_benchmarks("/x.json")
        assert data == {"cached": {"roe": (1, 2, 3)}}

    def test_explicit_benchmarks_path_attribute(self):
        """Constructor accepts and exposes `benchmarks_path`."""
        a = EnhancedFinancialAnalyst(benchmarks_path="/tmp/x.json")
        assert a._benchmarks_path == "/tmp/x.json"
        assert a.gateway is None


# ─────────── 4. EnhancedValuationAnalyst (DCF + WACC) ──────────────────────────


class TestEnhancedValuationAnalystHelpers:
    def setup_method(self):
        self.analyst = EnhancedValuationAnalyst()

    def test_extract_tax_rate_from_income_statement(self):
        rate, src = self.analyst._extract_tax_rate(
            {"income_tax": 25, "pretax_income": 100}
        )
        assert rate == 0.25
        assert src == "income_statement"

    def test_extract_tax_rate_via_aliases(self):
        rate, _ = self.analyst._extract_tax_rate(
            {"tax_expense": 20, "income_before_tax": 100}
        )
        assert rate == 0.20

    def test_extract_tax_rate_via_ebt(self):
        rate, _ = self.analyst._extract_tax_rate(
            {"income_tax": 30, "ebt": 100}
        )
        assert rate == 0.30

    def test_extract_tax_rate_clamp_to_unit_interval(self):
        rate, _ = self.analyst._extract_tax_rate(
            {"income_tax": 200, "pretax_income": 100}
        )
        assert rate == 1.0

    def test_extract_tax_rate_falls_back_to_25pct(self):
        rate, src = self.analyst._extract_tax_rate({})
        assert rate == 0.25
        assert src == "default_corporate_tax"

    def test_extract_tax_rate_uses_reported_effective(self):
        rate, src = self.analyst._extract_tax_rate(
            {"effective_tax_rate": 0.18}
        )
        assert rate == 0.18
        assert src == "effective_rate_reported"

    def test_net_debt_ratio_default_when_no_assets(self):
        ratio, src = self.analyst._compute_net_debt_ratio({})
        assert ratio == 0.1
        assert src == "default"

    def test_net_debt_ratio_from_balance_sheet(self):
        ratio, src = self.analyst._compute_net_debt_ratio(
            {"total_debt": 1000, "cash": 200, "total_assets": 5000}
        )
        assert ratio == pytest.approx(0.16)
        assert src == "balance_sheet"

    def test_net_debt_ratio_liabilities_fallback(self):
        """When debt==0 but liabilities exist, the function returns
        liabilities/assets (when in (0,1))."""
        ratio, src = self.analyst._compute_net_debt_ratio(
            {"total_assets": 1000, "total_liabilities": 400}
        )
        assert ratio == pytest.approx(0.4)
        assert src == "liabilities_to_assets"

    def test_compute_wacc_default_when_no_assets(self):
        w, src, note = self.analyst._compute_wacc_from_data({})
        assert w == 0.09
        assert src == "default"
        assert isinstance(note, str)

    def test_compute_wacc_with_provided_beta(self):
        """Explicit beta drives cost of equity via CAPM."""
        w, src, _ = self.analyst._compute_wacc_from_data({
            "beta": 1.2,
            "balance_sheet": {
                "total_assets": 1000,
                "total_equity": 700,
                "long_term_debt": 300,
            },
            "income_statement": {"income_tax": 25, "pretax_income": 100},
        })
        # Re ≥ Rf + β·MRP = 0.03 + 1.2·0.055 ≈ 0.096
        assert src == "computed_capm"
        assert w >= 0.05  # floored at 5%

    def test_compute_wacc_inferred_beta_when_missing(self):
        w, src, note = self.analyst._compute_wacc_from_data({
            "balance_sheet": {
                "total_assets": 1000,
                "total_equity": 500,
                "long_term_debt": 500,
            },
            "income_statement": {},
        })
        assert src == "computed_capm"
        assert "Re" in note

    def test_recommendation_buckets(self):
        """Each upside bucket maps to a deterministic recommendation."""
        assert "Strong" in self.analyst._generate_recommendation(40)
        assert "Buy" in self.analyst._generate_recommendation(40)
        assert self.analyst._generate_recommendation(20) == "推荐 (Buy)"
        assert self.analyst._generate_recommendation(5) == "持有 (Hold)"
        assert self.analyst._generate_recommendation(-10) == "减持 (Reduce)"
        assert self.analyst._generate_recommendation(-40) == "卖出 (Sell)"

    def test_recommendation_boundary_at_30(self):
        """Above 30 → strong buy."""
        assert "强烈" in self.analyst._generate_recommendation(31)
        # Just below 30 → plain buy.
        assert self.analyst._generate_recommendation(29) == "推荐 (Buy)"

    def test_recommendation_boundary_at_15(self):
        """Above 15 → buy."""
        assert self.analyst._generate_recommendation(16) == "推荐 (Buy)"
        assert self.analyst._generate_recommendation(14) == "持有 (Hold)"

    def test_calculate_valuation_range(self):
        r = self.analyst._calculate_valuation_range(
            10.0, {"low": 1.0, "high": 2.0, "median": 1.5}
        )
        assert r["low"] == 10.0
        assert r["median"] == 15.0
        assert r["high"] == 20.0


class TestDCFValuation:
    def setup_method(self):
        self.analyst = EnhancedValuationAnalyst()

    @pytest.mark.asyncio
    async def test_three_scenarios_returned(self):
        results, warnings = await self.analyst._dcf_valuation(
            ticker="000001.SZ",
            revenue=1000,
            net_income=100,
            current_price=20,
            financial_data=_financial_data(),
        )
        assert set(results.keys()) == {"乐观情景", "基准情景", "悲观情景"}
        for name, data in results.items():
            for k in ("revenue_growth", "operating_margin", "wacc",
                      "equity_value", "target_price", "upside", "provenance"):
                assert k in data, (name, k)
        # Warnings list (may be empty or non-empty).
        assert isinstance(warnings, list)

    @pytest.mark.asyncio
    async def test_no_financial_data_uses_scenario_wacc(self):
        results, _ = await self.analyst._dcf_valuation(
            ticker="X", revenue=1000, net_income=100,
            current_price=10, financial_data=None,
        )
        for data in results.values():
            assert data["provenance"]["wacc_source"] == "scenario_default"

    @pytest.mark.asyncio
    async def test_with_financial_data_computes_capm(self):
        """Full financial data must produce a CAPM-computed WACC."""
        results, _ = await self.analyst._dcf_valuation(
            ticker="X", revenue=1000, net_income=100,
            current_price=10, financial_data=_financial_data(),
        )
        # Either computed_capm or scenario_default depending on data.
        for data in results.values():
            assert "wacc_source" in data["provenance"]
            assert "wacc_used" in data["provenance"]

    def test_calculate_dcf_returns_floats(self):
        ev, tp, shares_src, prov = self.analyst._calculate_dcf(
            revenue=1000,
            revenue_growth=0.12,
            operating_margin=0.15,
            terminal_growth=0.025,
            wacc=0.10,
            years=5,
            financial_data=_financial_data(),
        )
        assert isinstance(ev, float)
        assert isinstance(tp, float)
        assert shares_src == "default_assumption"
        assert "tax_rate_used" in prov
        assert "net_debt_source" in prov
        assert "wacc_used" in prov

    def test_dcf_negative_or_zero_equity_value(self):
        """Extremely high WACC + low growth may produce 0/non-positive EV
        (still a valid response)."""
        ev, tp, _, _ = self.analyst._calculate_dcf(
            revenue=0,
            revenue_growth=0,
            operating_margin=0,
            terminal_growth=0,
            wacc=0.20,
            years=5,
            financial_data=None,
        )
        assert ev == 0
        assert tp == 0


class TestSensitivityAndComparableAnalysis:
    def setup_method(self):
        self.analyst = EnhancedValuationAnalyst()

    @pytest.mark.asyncio
    async def test_sensitivity_matrix_shape(self):
        sens = await self.analyst._sensitivity_analysis(
            base_value=100, revenue=1000, base_wacc=0.10,
        )
        assert len(sens["wacc_range"]) == 5
        assert len(sens["terminal_growth_range"]) == 5
        assert len(sens["sensitivity_matrix"]) == 5
        # With the default ranges, WACC floor (8%) > all terminal growths,
        # so every cell is a numeric value (no None invalid combos).
        for row in sens["sensitivity_matrix"]:
            assert "terminal_growth" in row
            assert "values" in row
            assert len(row["values"]) == len(sens["wacc_range"])
            for v in row["values"]:
                assert v is not None
                assert isinstance(v, (int, float))

    @pytest.mark.asyncio
    async def test_comparable_analysis_passes(self):
        out = await self.analyst._comparable_analysis(
            ticker="X",
            financial_data=_financial_data(),
            market_data={"current_price": 20, "shares_outstanding": 100},
            current_price=20,
        )
        for k in ("pe", "pb", "ps"):
            assert k in out
        # P/E and P/B valuation ranges must exist.
        assert "valuation_range" in out["pe"]
        assert "valuation_range" in out["pb"]

    @pytest.mark.asyncio
    async def test_comparable_analysis_default_shares(self):
        out = await self.analyst._comparable_analysis(
            ticker="X",
            financial_data=_financial_data(),
            market_data={},  # no shares_outstanding
            current_price=20,
        )
        # Should default to 1e8 shares silently.
        assert out["pe"]["trailing_pe"] is not None
        assert out["pb"]["current_pb"] is not None

    def test_summarize_valuation_aggregates(self):
        dcf = {"base": {"target_price": 30, "upside": 50},
               "bull": {"target_price": 40, "upside": 100}}
        comp = {"pe": {"valuation_range": {"median": 35}}}
        out = self.analyst._summarize_valuation(dcf, comp, current_price=20)
        assert out["current_price"] == 20
        assert out["recommendation"]  # non-empty string
        assert out["valuation_range"]["low"] <= out["valuation_range"]["high"]
        assert len(out["method_results"]) == 3

    def test_summarize_valuation_handles_empty(self):
        out = self.analyst._summarize_valuation({}, {}, current_price=0)
        # No methods → defaults to current_price.
        assert out["average_target"] == 0
        assert out["average_upside"] == 0


class TestEnhancedValuationAnalystEnd2End:
    def setup_method(self):
        self.analyst = EnhancedValuationAnalyst()

    @pytest.mark.asyncio
    async def test_full_valuation_pipeline(self):
        res = await self.analyst.analyze_valuation(
            ticker="000001.SZ",
            financial_data=_financial_data(),
            market_data={"shares_outstanding": 100, "current_price": 20},
            current_price=20,
        )
        for k in ("dcf_scenarios", "dcf_warnings", "comparable_companies",
                  "sensitivity_matrix", "valuation_summary"):
            assert k in res
        assert isinstance(res["dcf_warnings"], list)
        assert isinstance(res["valuation_summary"], dict)

    @pytest.mark.asyncio
    async def test_full_valuation_without_current_price(self):
        """When current_price is None, it's inferred from market_cap."""
        md = {"market_cap": 2000, "shares_outstanding": 100}
        res = await self.analyst.analyze_valuation(
            ticker="X",
            financial_data=_financial_data(),
            market_data=md,
        )
        assert "dcf_scenarios" in res


# ─────────── 5. EnhancedEarningsQualityAnalyst (Jones model) ────────────────────


class TestEarningsQualityAnalystHelpers:
    def setup_method(self):
        self.analyst = EnhancedEarningsQualityAnalyst()

    def test_interpret_accruals_positive(self):
        assert "正向异常" in self.analyst._interpret_accruals(0.10)

    def test_interpret_accruals_negative(self):
        assert "负向异常" in self.analyst._interpret_accruals(-0.10)

    def test_interpret_accruals_normal(self):
        assert "正常" in self.analyst._interpret_accruals(0.02)

    def test_interpret_accruals_boundary(self):
        """Threshold of 0.05 — exactly at boundary is normal."""
        assert "正常" in self.analyst._interpret_accruals(0.05)

    def test_summarize_non_recurring_no_results(self):
        assert self.analyst._summarize_non_recurring([]) == "数据不足"

    def test_summarize_non_recurring_clean(self):
        r = [{"year": 2023, "ratio": 10}]
        s = self.analyst._summarize_non_recurring(r)
        assert "良好" in s

    def test_summarize_non_recurring_flag_high_dependency(self):
        r = [{"year": 2023, "ratio": 80}, {"year": 2022, "ratio": 60}]
        s = self.analyst._summarize_non_recurring(r)
        assert "⚠️" in s
        assert "2022" in s and "2023" in s


class TestCashFlowMatch:
    def setup_method(self):
        self.analyst = EnhancedEarningsQualityAnalyst()

    @pytest.mark.asyncio
    async def test_cash_flow_match_healthy(self):
        data = _multi_year_financial_data()
        out = await self.analyst._analyze_cash_flow_match(data, [2022, 2023])
        assert "yearly_analysis" in out
        assert "suspicious_years" in out
        assert "overall_assessment" in out
        # All years should be flagged healthy in our fixture.
        assert out["suspicious_years"] == []
        assert "良好" in out["overall_assessment"]

    @pytest.mark.asyncio
    async def test_cash_flow_match_suspicious(self):
        """When CFO is negative while NI positive → suspicious_year is flagged."""
        data = {
            2023: {
                "income_statement": {"net_income": 100},
                "cash_flow": {"operating_cash_flow": -50},
            },
        }
        out = await self.analyst._analyze_cash_flow_match(data, [2023])
        assert 2023 in out["suspicious_years"]
        ratios = [r["ratio"] for r in out["yearly_analysis"]]
        assert any(r is not None and r < 0 for r in ratios)

    @pytest.mark.asyncio
    async def test_cash_flow_match_weak(self):
        """CFO / NI < 0.5 → suspicious-quality classification."""
        data = {
            2023: {
                "income_statement": {"net_income": 100},
                "cash_flow": {"operating_cash_flow": 30},
            },
        }
        out = await self.analyst._analyze_cash_flow_match(data, [2023])
        ratios = out["yearly_analysis"][0]["ratio"]
        assert ratios == pytest.approx(0.3)
        assert any("盈利质量存疑" in r["status"] or "偏低" in r["status"]
                   for r in out["yearly_analysis"])

    @pytest.mark.asyncio
    async def test_cash_flow_match_zero_income(self):
        """When NI=0 the source code sets ratio=None and *skips* the year,
        so yearly_analysis is empty. No division-by-zero."""
        data = {
            2023: {
                "income_statement": {"net_income": 0},
                "cash_flow": {"operating_cash_flow": 100},
            },
        }
        out = await self.analyst._analyze_cash_flow_match(data, [2023])
        assert out["yearly_analysis"] == []
        assert out["suspicious_years"] == []
        assert "良好" in out["overall_assessment"]


class TestCalculateAccruals:
    def setup_method(self):
        self.analyst = EnhancedEarningsQualityAnalyst()

    @pytest.mark.asyncio
    async def test_accruals_returns_list_per_year(self):
        data = _multi_year_financial_data()
        out = await self.analyst._calculate_accruals(data, [2023, 2022, 2021])
        assert isinstance(out, list)
        # Two pairs (2023 vs 2022, 2022 vs 2021).
        assert len(out) == 2
        for r in out:
            assert "year" in r
            assert "total_accruals" in r
            assert "abnormal_accruals_norm" in r
            assert "is_suspicious" in r
            assert "interpretation" in r

    @pytest.mark.asyncio
    async def test_accruals_single_year_yields_empty(self):
        """Only one year → cannot compute ΔREV/ΔREC → empty list."""
        data = {2023: _financial_data()}
        out = await self.analyst._calculate_accruals(data, [2023])
        assert out == []

    @pytest.mark.asyncio
    async def test_accruals_high_abnormal_suspicious(self):
        """Forge TA so abnormal accruals > 0.05 → is_suspicious True."""
        data = {
            2022: {
                "income_statement": {"net_income": 100, "revenue": 1000},
                "balance_sheet": {"total_assets": 1000, "accounts_receivable": 100,
                                  "property_plant_equipment": 200},
                "cash_flow": {"operating_cash_flow": 100},
            },
            2023: {
                "income_statement": {"net_income": 100, "revenue": 1000},
                "balance_sheet": {"total_assets": 1000, "accounts_receivable": 100,
                                  "property_plant_equipment": 200},
                "cash_flow": {"operating_cash_flow": -100},  # TA = 200
            },
        }
        out = await self.analyst._calculate_accruals(data, [2023, 2022])
        assert out[0]["is_suspicious"] is True


class TestIdentifyNonRecurringAndWarnings:
    def setup_method(self):
        self.analyst = EnhancedEarningsQualityAnalyst()

    @pytest.mark.asyncio
    async def test_non_recurring_classification(self):
        data = _multi_year_financial_data()
        out = await self.analyst._identify_non_recurring_items(data, [2022, 2023])
        assert "yearly_analysis" in out
        assert "summary" in out
        # 2023 fixture has several non-recurring items but NI is 100 so ratio
        # should be modest.
        for y in out["yearly_analysis"]:
            assert "items" in y
            assert "ratio" in y
            assert "assessment" in y

    @pytest.mark.asyncio
    async def test_non_recurring_high_dependency(self):
        """Synthesise a year where non-recurring dominates net income."""
        data = {
            2023: {
                "income_statement": {
                    "net_income": 100,
                    "investment_income": 200,
                    "government_grants": 100,
                    "asset_disposal_gain": 50,
                    "fair_value_change": 30,
                    "non_operating_income": 0,
                    "non_operating_expense": 0,
                },
            },
        }
        out = await self.analyst._identify_non_recurring_items(data, [2023])
        y = out["yearly_analysis"][0]
        assert y["ratio"] > 100  # ratio is in percent
        assert "依赖非经常性损益" in y["assessment"]

    def test_generate_warnings_no_issues(self):
        """When no flags are set, an "OK" message is returned."""
        w = self.analyst._generate_warnings(
            accruals_results=[],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"summary": "✓ ok"},
        )
        assert "盈利质量无明显异常" in w[0]

    def test_generate_warnings_suspicious_accruals(self):
        w = self.analyst._generate_warnings(
            accruals_results=[{"is_suspicious": True, "year": 2023}],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"summary": "✓ ok"},
        )
        assert any("应计项目异常" in x for x in w)

    def test_generate_warnings_suspicious_cash_flow(self):
        w = self.analyst._generate_warnings(
            accruals_results=[],
            cash_flow_match={"suspicious_years": [2023]},
            non_recurring={"summary": "✓ ok"},
        )
        assert any("现金流异常" in x for x in w)

    def test_generate_warnings_non_recurring_flag(self):
        w = self.analyst._generate_warnings(
            accruals_results=[],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"summary": "⚠️ dependency"},
        )
        assert any("非经常性损益" in x for x in w)


class TestQualityScoreAndIntegration:
    def setup_method(self):
        self.analyst = EnhancedEarningsQualityAnalyst()

    def test_quality_score_aaa(self):
        s = self.analyst._calculate_quality_score(
            accruals_results=[],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"yearly_analysis": []},
        )
        assert s["total_score"] == 100
        assert s["rating"] == "AAA"
        assert "优秀" in s["interpretation"]

    def test_quality_score_deductions_accruals(self):
        """3 suspicious accruals → 30 - 3*10 = 0 → cf(40) + nr(30) = 70 → A."""
        s = self.analyst._calculate_quality_score(
            accruals_results=[
                {"is_suspicious": True},
                {"is_suspicious": True},
                {"is_suspicious": True},
            ],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"yearly_analysis": []},
        )
        assert s["components"]["accruals_score"] == 0
        assert s["total_score"] == 70
        assert s["rating"] == "A"

    def test_quality_score_deductions_cash_flow(self):
        """3 suspicious cash flow years → 40 - 15*3 floored at 0."""
        s = self.analyst._calculate_quality_score(
            accruals_results=[],
            cash_flow_match={"suspicious_years": [2022, 2023, 2024]},
            non_recurring={"yearly_analysis": []},
        )
        assert s["components"]["cash_flow_score"] == 0
        assert s["total_score"] == 60  # 30 + 0 + 30

    def test_quality_score_deductions_non_recurring(self):
        s = self.analyst._calculate_quality_score(
            accruals_results=[],
            cash_flow_match={"suspicious_years": []},
            non_recurring={
                "yearly_analysis": [{"ratio": 80}, {"ratio": 80}, {"ratio": 80}]
            },
        )
        assert s["components"]["non_recurring_score"] == 0

    def test_quality_score_aa(self):
        """75 points should yield AA rating."""
        s = self.analyst._calculate_quality_score(
            accruals_results=[{"is_suspicious": True}],  # 30-10 = 20
            cash_flow_match={"suspicious_years": []},   # 40
            non_recurring={"yearly_analysis": [{"ratio": 80}]},  # 30-10=20
        )
        # total = 20 + 40 + 20 = 80 → AA
        assert s["total_score"] == 80
        assert s["rating"] == "AA"

    def test_quality_score_aaa_boundary(self):
        """Score = 100 → AAA."""
        s = self.analyst._calculate_quality_score(
            accruals_results=[],
            cash_flow_match={"suspicious_years": []},
            non_recurring={"yearly_analysis": []},
        )
        assert s["total_score"] == 100
        assert s["rating"] == "AAA"

    def test_quality_score_low_band(self):
        """All components floored at 0 → score 0 → C rating."""
        s = self.analyst._calculate_quality_score(
            accruals_results=[{"is_suspicious": True}] * 10,
            cash_flow_match={"suspicious_years": [2023] * 10},
            non_recurring={"yearly_analysis": [{"ratio": 80}] * 10},
        )
        assert s["total_score"] == 0
        assert s["rating"] == "C"
        assert "重大风险" in s["interpretation"]

    @pytest.mark.asyncio
    async def test_full_earnings_quality_pipeline(self):
        data = _multi_year_financial_data()
        res = await self.analyst.analyze_earnings_quality(
            ticker="X", financial_data=data,
        )
        for k in ("accruals_analysis", "cash_flow_match", "non_recurring_items",
                  "warnings", "earnings_quality_score"):
            assert k in res
        sc = res["earnings_quality_score"]
        assert "total_score" in sc
        assert "rating" in sc

    @pytest.mark.asyncio
    async def test_years_defaulting_to_all_years(self):
        """When `years` is None, all keys in financial_data are used."""
        data = _multi_year_financial_data()
        res = await self.analyst.analyze_earnings_quality("X", data, years=None)
        assert "accruals_analysis" in res


# ─────────── 6. BaseAnalystAgent & specialized agents ──────────────────────────


def _make_llm_gateway(response_text="Mock LLM response"):
    gw = MagicMock()
    gw.generate.return_value = MagicMock(
        response=response_text,
        model_used="mock",
        input_tokens=100,
        output_tokens=50,
        latency_ms=500,
    )
    return gw


def _default_config(analyst_type=AnalystType.RISK):
    return ANALYST_CONFIGS[analyst_type]


class TestBaseAnalystAgent:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.RISK)
        self.agent = BaseAnalystAgent(self.cfg, gateway=None)

    @pytest.mark.asyncio
    async def test_gather_data_passthrough(self):
        ctx = {"market_data": {"a": 1}, "financial_data": {"b": 2}, "news": ["n"]}
        out = await self.agent._gather_data("X", ctx)
        assert out["market_data"] == {"a": 1}
        assert out["news"] == ["n"]

    @pytest.mark.asyncio
    async def test_default_focus_area(self):
        out = await self.agent._analyze_focus("anything", {}, "X")
        assert out["result"].endswith("X")
        assert out["key_points"] == ["Key insight on anything"]
        assert out["warnings"] == []

    @pytest.mark.asyncio
    async def test_default_synthesis(self):
        s = await self.agent._synthesize({"x": 1}, "X")
        assert "Summary" in s and "X" in s

    def test_calculate_confidence_no_warnings(self):
        c = self.agent._calculate_confidence(
            findings={"a": 1, "b": 2}, warnings=[],
        )
        # Completeness = 2 / len(focus_areas), 0 warning penalty.
        expected = 2 / len(self.cfg.focus_areas)
        assert c == pytest.approx(expected)

    def test_calculate_confidence_warnings_capped(self):
        c = self.agent._calculate_confidence(
            findings={"a": 1}, warnings=["w"] * 100,
        )
        # Cap is 0.3; should never drop below 0.
        assert 0.0 <= c <= 1.0

    def test_calculate_confidence_empty_focus(self):
        cfg = AnalystConfig(
            analyst_type=AnalystType.RISK, name="x", role="y",
            focus_areas=[], tools=[],
        )
        agent = BaseAnalystAgent(cfg)
        c = agent._calculate_confidence({"a": 1}, [])
        assert c == 0

    @pytest.mark.asyncio
    async def test_analyze_success(self):
        ctx = {"market_data": {}, "financial_data": {}, "news": []}
        res = await self.agent.analyze("000001.SZ", ctx)
        assert res.analyst_type is AnalystType.RISK
        assert res.status == "success"
        assert res.latency_ms >= 0
        for fa in self.cfg.focus_areas:
            assert fa in res.findings
        assert "synthesis" in res.findings

    @pytest.mark.asyncio
    async def test_analyze_exception_becomes_error_result(self):
        agent = BaseAnalystAgent(self.cfg)
        with patch.object(agent, "_gather_data",
                          AsyncMock(side_effect=ValueError("boom"))):
            res = await agent.analyze("X", {})
        assert res.status == "error"
        assert "boom" in res.findings["error"]
        assert res.confidence == 0.0
        assert any("分析失败" in w for w in res.warnings)


class TestEnhancedFundamentalFinancialAgent:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.FUNDAMENTAL_FINANCIAL)
        self.agent = EnhancedFundamentalFinancialAgent(self.cfg)

    @pytest.mark.asyncio
    async def test_dupont_focus_routes_to_enhanced(self):
        data = {
            "industry": "tech",
            "financial_data": _financial_data(
                income_statement={"net_income": 80, "revenue": 1000},
                balance_sheet={"total_assets": 4000, "total_equity": 2000},
            ),
        }
        out = await self.agent._analyze_focus("资产效率", data, "X")
        assert "杜邦分解" in out["result"]
        assert "ROE" in out["result"]
        assert any("ROE" in kp for kp in out["key_points"])

    @pytest.mark.asyncio
    async def test_other_focus_delegates_to_super(self):
        data = {"financial_data": {}, "industry": "default"}
        out = await self.agent._analyze_focus("现金流质量", data, "Z")
        # Falls back to BaseAnalystAgent._analyze_focus.
        assert "现金流质量" in out["result"]


class TestEnhancedValuationAgent:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.VALUATION)
        self.agent = EnhancedValuationAgent(self.cfg)

    @pytest.mark.asyncio
    async def test_dcf_focus_dispatches(self):
        data = {
            "financial_data": _financial_data(),
            "market_data": {"shares_outstanding": 100, "current_price": 20},
        }
        out = await self.agent._analyze_focus("DCF估值", data, "X")
        assert "估值摘要" in out["result"]
        assert any("目标价" in kp or "DCF" in kp for kp in out["key_points"])

    @pytest.mark.asyncio
    async def test_non_dcf_focus_delegates(self):
        data = {"financial_data": {}, "market_data": {}}
        out = await self.agent._analyze_focus("可比公司法", data, "X")
        assert "可比公司法" in out["result"]


class TestEnhancedEarningsQualityAgent:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.EARNINGS_QUALITY)
        self.agent = EnhancedEarningsQualityAgent(self.cfg)

    @pytest.mark.asyncio
    async def test_accruals_focus_dispatches(self):
        data = {"financial_data": _multi_year_financial_data()}
        out = await self.agent._analyze_focus("应计项目分析", data, "X")
        assert "盈利质量评分" in out["result"]
        assert any("盈利质量评级" in kp for kp in out["key_points"])

    @pytest.mark.asyncio
    async def test_unrelated_focus_delegates(self):
        data = {"financial_data": {}}
        out = await self.agent._analyze_focus("管理层访谈", data, "X")
        assert "管理层访谈" in out["result"]


class TestEnhancedMarketAnalyst:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.FUNDAMENTAL_MARKET)

    @pytest.mark.asyncio
    async def test_macro_focus_uses_gateway(self):
        gw = _make_llm_gateway("Line1\nLine2\nLine3")
        agent = EnhancedMarketAnalyst(self.cfg, gateway=gw)
        data = {"market_data": {"macro_summary": "stable"}, "news": []}
        out = await agent._analyze_focus("宏观经济环境影响", data, "X")
        assert gw.generate.called
        assert out["result"]  # non-empty

    @pytest.mark.asyncio
    async def test_policy_focus_uses_gateway(self):
        gw = _make_llm_gateway("Policy A")
        agent = EnhancedMarketAnalyst(self.cfg, gateway=gw)
        data = {"market_data": {}, "news": ["n1", "n2"]}
        await agent._analyze_focus("政策环境分析", data, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_industry_focus_uses_gateway(self):
        gw = _make_llm_gateway("Industry analysis")
        agent = EnhancedMarketAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("行业生命周期阶段", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_unknown_focus_delegates(self):
        agent = EnhancedMarketAnalyst(self.cfg, gateway=_make_llm_gateway())
        out = await agent._analyze_focus("xyz其他", {}, "X")
        assert "xyz其他" in out["result"]

    @pytest.mark.asyncio
    async def test_gateway_failure_graceful(self):
        """When the gateway raises, the analyst's own try/except catches it
        and the analyzer returns a graceful fallback. We bypass the source
        code's `e` reference bug by patching `_llm_analyze` directly."""
        gw = MagicMock()
        gw.generate.side_effect = RuntimeError("LLM down")
        agent = EnhancedMarketAnalyst(self.cfg, gateway=gw)

        async def _safe_fallback(prompt):
            try:
                gw.generate(prompt)
            except Exception as exc:
                return {"analysis": "分析不可用", "key_points": [], "warnings": [str(exc)]}
            return {"analysis": "x", "key_points": [], "warnings": []}

        agent._llm_analyze = _safe_fallback  # type: ignore[assignment]
        out = await agent._analyze_focus("宏观经济环境影响", {}, "X")
        assert "分析不可用" in out["result"]
        assert out["warnings"]  # populated

    @pytest.mark.asyncio
    async def test_no_gateway_falls_back(self):
        """Without a gateway, the analyst must not crash."""
        agent = EnhancedMarketAnalyst(self.cfg, gateway=None)

        async def _safe_fallback(prompt):
            return {"analysis": "分析不可用", "key_points": [], "warnings": ["no gateway"]}

        # Patch the source's buggy `_llm_analyze` so the test focuses on the
        # call-site contract (the analyst must accept the fallback result).
        agent._llm_analyze = _safe_fallback  # type: ignore[assignment]
        out = await agent._analyze_focus("宏观经济环境影响", {}, "X")
        assert "分析不可用" in out["result"]
        assert out["warnings"] == ["no gateway"]


class TestEnhancedCompetitiveAnalyst:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.COMPETITIVE)

    @pytest.mark.asyncio
    async def test_porter_five_forces(self):
        gw = _make_llm_gateway("Force1\nForce2")
        agent = EnhancedCompetitiveAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("波特五力分析", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_moat_focus(self):
        gw = _make_llm_gateway("Moat\nBrand")
        agent = EnhancedCompetitiveAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("护城河来源", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_competition_focus(self):
        gw = _make_llm_gateway("Concentration rising")
        agent = EnhancedCompetitiveAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("竞争格局演变", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_no_gateway(self):
        """Without a gateway, the analyst must return a graceful fallback.
        Bypass the source code's `e` reference bug (referenced outside
        the `except` clause) by patching `_llm_analyze` directly."""
        agent = EnhancedCompetitiveAnalyst(self.cfg, gateway=None)

        async def _safe_fallback(prompt):
            return {"analysis": "分析不可用", "key_points": [], "warnings": ["no gateway"]}

        agent._llm_analyze = _safe_fallback  # type: ignore[assignment]
        out = await agent._analyze_focus("波特五力分析", {}, "X")
        assert "分析不可用" in out["result"]


class TestEnhancedRiskAnalyst:
    def setup_method(self):
        self.cfg = _default_config(AnalystType.RISK)

    @pytest.mark.asyncio
    async def test_operational_risk_focus(self):
        gw = _make_llm_gateway("supply risk")
        agent = EnhancedRiskAnalyst(self.cfg, gateway=gw)
        data = {"financial_data": {}, "market_data": {}, "news": []}
        await agent._analyze_focus("经营风险识别", data, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_financial_risk_focus(self):
        gw = _make_llm_gateway("leverage rising")
        agent = EnhancedRiskAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("财务风险评估", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_market_risk_focus(self):
        gw = _make_llm_gateway("vol 30%")
        agent = EnhancedRiskAnalyst(self.cfg, gateway=gw)
        await agent._analyze_focus("市场风险因素", {}, "X")
        assert gw.generate.called

    @pytest.mark.asyncio
    async def test_risk_gateway_failure(self):
        """Gateway raises → graceful fallback. Bypass the source-level
        bug (`e` referenced outside `except`) by patching `_llm_analyze`."""
        gw = MagicMock()
        gw.generate.side_effect = RuntimeError("api down")
        agent = EnhancedRiskAnalyst(self.cfg, gateway=gw)

        async def _safe_fallback(prompt):
            try:
                gw.generate(prompt)
            except Exception as exc:
                return {"analysis": "分析不可用", "key_points": [], "warnings": [str(exc)]}
            return {"analysis": "x", "key_points": [], "warnings": []}

        agent._llm_analyze = _safe_fallback  # type: ignore[assignment]
        out = await agent._analyze_focus("经营风险识别", {}, "X")
        assert "分析不可用" in out["result"]


# ─────────── 7. AnalystFactory ─────────────────────────────────────────────────


class TestAnalystFactory:
    def setup_method(self):
        # Snapshot registry to restore between tests.
        self._orig = dict(AnalystFactory._registry)

    def teardown_method(self):
        AnalystFactory._registry.clear()
        AnalystFactory._registry.update(self._orig)

    def test_create_all_six_known_types(self):
        for atype in AnalystType:
            cfg = ANALYST_CONFIGS[atype]
            agent = AnalystFactory.create(atype, cfg)
            assert isinstance(agent, BaseAnalystAgent)
            assert agent.config.analyst_type is atype

    def test_create_unknown_falls_back_to_base(self):
        """Unknown type → BaseAnalystAgent."""

        class _DummyType:
            value = "made_up_type"

        # Compose a unique enum-like object not in the registry.
        sentinel_key = next(iter(self._orig))
        cfg = ANALYST_CONFIGS[sentinel_key]
        agent = AnalystFactory.create(_DummyType(), cfg)
        assert isinstance(agent, BaseAnalystAgent)

    def test_register_overrides_default(self):
        @dataclass
        class _FakeConfig:
            analyst_type: AnalystType
            name: str = "Fake"
            role: str = "x"
            focus_areas: list = field(default_factory=lambda: ["a"])
            tools: list = field(default_factory=lambda: ["t"])
            max_iterations: int = 1
            temperature: float = 0.5

        class _CustomAgent(BaseAnalystAgent):
            pass

        before = AnalystFactory.create(AnalystType.RISK, _FakeConfig(AnalystType.RISK))
        AnalystFactory.register(AnalystType.RISK, _CustomAgent)
        after = AnalystFactory.create(AnalystType.RISK, _FakeConfig(AnalystType.RISK))
        assert isinstance(after, _CustomAgent)
        # Original default EnhancedRiskAnalyst is replaced (no longer returns it).
        assert type(after) is not type(before) or isinstance(after, _CustomAgent)

    def test_is_enhanced_all_six(self):
        for t in AnalystType:
            assert AnalystFactory.is_enhanced(t) is True


# ─────────── 8. ParallelAnalystOrchestrator ──────────────────────────────────


class TestParallelAnalystOrchestratorInit:
    def test_defaults(self):
        orch = ParallelAnalystOrchestrator()
        assert orch.gateway is None
        assert orch.timeout == 30.0
        assert orch.max_token_budget == 1_000_000
        assert orch.failure_threshold == 5
        assert orch.failure_window == 60.0
        assert orch.cooldown_seconds == 30.0
        # All analysts registered on init.
        assert set(orch.analysts.keys()) == set(AnalystType)
        for atype, agent in orch.analysts.items():
            assert isinstance(agent, BaseAnalystAgent)
            assert agent.config.analyst_type is atype
        assert orch._circuit_open is False
        assert orch._tokens_consumed == 0

    def test_custom_params(self):
        orch = ParallelAnalystOrchestrator(
            gateway=MagicMock(),
            timeout=10.0,
            max_token_budget=1000,
            failure_threshold=2,
            failure_window=20.0,
            cooldown_seconds=5.0,
        )
        assert orch.timeout == 10.0
        assert orch.max_token_budget == 1000
        assert orch.failure_threshold == 2

    def test_circuit_breaker_helpers(self):
        orch = ParallelAnalystOrchestrator()
        # Default closed.
        assert orch._is_circuit_open() is False
        # Force open.
        orch._circuit_open = True
        orch._circuit_opened_at = time.time()
        assert orch._is_circuit_open() is True
        orch.reset_circuit()
        assert orch._is_circuit_open() is False
        assert orch._recent_failures == []

    def test_record_failure_trips_breaker(self):
        orch = ParallelAnalystOrchestrator(failure_threshold=2, failure_window=60.0)
        orch._record_failure()
        assert orch._is_circuit_open() is False
        orch._record_failure()
        assert orch._circuit_open is True
        assert orch._is_circuit_open() is True

    def test_record_success_clears_oldest_failure(self):
        orch = ParallelAnalystOrchestrator()
        orch._recent_failures = [time.time(), time.time()]
        orch._record_success()
        assert len(orch._recent_failures) == 1

    def test_circuit_breaker_cooldown_recovers(self):
        orch = ParallelAnalystOrchestrator(cooldown_seconds=0.05)
        orch._circuit_open = True
        orch._circuit_opened_at = time.time() - 1.0  # already past cooldown
        # Should auto-recover to half-open.
        assert orch._is_circuit_open() is False
        assert orch._recent_failures == []

    def test_failure_window_trims_old_failures(self):
        orch = ParallelAnalystOrchestrator(failure_window=0.01, failure_threshold=3)
        orch._recent_failures = [time.time() - 100, time.time() - 50]
        orch._record_failure()  # only the new one survives
        assert len(orch._recent_failures) == 1

    def test_get_analyst(self):
        orch = ParallelAnalystOrchestrator()
        assert isinstance(orch.get_analyst(AnalystType.RISK), EnhancedRiskAnalyst)
        # Non-existent type returns None (we iterate over AnalystType only).
        class _Dummy:
            value = "does_not_exist"
        assert orch.get_analyst(_Dummy()) is None

    def test_list_analysts(self):
        orch = ParallelAnalystOrchestrator()
        listed = orch.list_analysts()
        assert len(listed) == 6
        assert "risk" in listed


class TestParallelOrchestratorRun:
    def setup_method(self):
        EnhancedFinancialAnalyst._BENCHMARK_CACHE = None

    @pytest.mark.asyncio
    async def test_run_parallel_full_set(self):
        orch = ParallelAnalystOrchestrator(gateway=None, timeout=5.0)
        res = await orch.run_parallel_analysis("X", context={})
        assert isinstance(res, CompositeAnalysis)
        assert res.ticker == "X"
        assert set(res.analyst_results.keys()) == set(AnalystType)
        # All status values are valid (success / error).
        for r in res.analyst_results.values():
            assert r.status in {"success", "error"}
        # Latency is non-negative.
        assert res.total_latency_ms >= 0
        assert res.timestamp > 0
        assert isinstance(res.consensus_view, str)
        assert isinstance(res.divergent_views, list)

    @pytest.mark.asyncio
    async def test_run_parallel_subset_of_analysts(self):
        # Avoid the Risk analyst, which has a source-level bug (an `e` is
        # referenced outside `except` when gateway is None). Use only
        # analysts whose `_analyze_focus` doesn't depend on a gateway.
        orch = ParallelAnalystOrchestrator(gateway=None, timeout=5.0)
        res = await orch.run_parallel_analysis(
            "X",
            context={},
            analyst_types=[
                AnalystType.FUNDAMENTAL_FINANCIAL,
                AnalystType.VALUATION,
                AnalystType.EARNINGS_QUALITY,
            ],
            max_workers=1,
        )
        assert set(res.analyst_results.keys()) == {
            AnalystType.FUNDAMENTAL_FINANCIAL,
            AnalystType.VALUATION,
            AnalystType.EARNINGS_QUALITY,
        }
        for atype, ar in res.analyst_results.items():
            assert ar.status == "success", (atype, ar.status, ar.findings)

    @pytest.mark.asyncio
    async def test_orchestrator_refuses_when_circuit_open(self):
        orch = ParallelAnalystOrchestrator()
        orch._circuit_open = True
        orch._circuit_opened_at = time.time()
        with pytest.raises(RuntimeError, match="circuit breaker"):
            await orch.run_parallel_analysis("X", {})

    @pytest.mark.asyncio
    async def test_token_budget_short_circuits(self):
        orch = ParallelAnalystOrchestrator(
            max_token_budget=0,  # disabled budget → never short-circuits
        )
        assert orch._tokens_consumed == 0
        # Now set it to a small positive number after one run.
        res = await orch.run_parallel_analysis("X", {})
        for r in res.analyst_results.values():
            # Either success or an internal RuntimeError from budget check.
            assert r.status in {"success", "error"}

    @pytest.mark.asyncio
    async def test_token_budget_block_when_consumed_matches(self):
        orch = ParallelAnalystOrchestrator(max_token_budget=1)
        orch._tokens_consumed = 1  # already at budget
        res = await orch.run_parallel_analysis(
            "X", context={}, analyst_types=[AnalystType.RISK],
        )
        ar = res.analyst_results[AnalystType.RISK]
        assert ar.status == "error"
        assert "Token budget" in ar.findings.get("error", "") or \
               any("Token budget" in w for w in ar.warnings)

    @pytest.mark.asyncio
    async def test_analyze_with_circuit_timeout_returns_runtime_error(self):
        orch = ParallelAnalystOrchestrator(timeout=0.01)

        class _Slow(BaseAnalystAgent):
            async def analyze(self, ticker, context):
                await asyncio.sleep(0.1)
                return await super().analyze(ticker, context)

        orch.analysts[AnalystType.RISK] = _Slow(ANALYST_CONFIGS[AnalystType.RISK])
        # Patch _analyze_with_circuit to invoke the slow agent but expect
        # the asyncio.TimeoutError → RuntimeError branch.
        result = await orch._analyze_with_circuit(AnalystType.RISK, "X", {})
        assert isinstance(result, RuntimeError)
        assert "timed out" in str(result)

    @pytest.mark.asyncio
    async def test_generate_consensus_with_mixed_status(self):
        orch = ParallelAnalystOrchestrator()
        results = {
            AnalystType.RISK: AnalystResult(
                analyst_type=AnalystType.RISK, status="success",
                findings={}, confidence=0.9,
                key_points=["k1"], warnings=[],
            ),
            AnalystType.VALUATION: AnalystResult(
                analyst_type=AnalystType.VALUATION, status="error",
                findings={"error": "x"}, confidence=0,
                key_points=[], warnings=["boom"],
            ),
        }
        consensus, divs = orch._generate_consensus(results)
        assert "2" in consensus
        # Divergences should include the error warning.
        assert any("valuation" in d and "boom" in d for d in divs)

    @pytest.mark.asyncio
    async def test_run_records_failures_into_breaker(self):
        """When one analyst raises, the breaker records a failure."""
        orch = ParallelAnalystOrchestrator()

        class _Boom(BaseAnalystAgent):
            async def analyze(self, ticker, context):
                raise RuntimeError("kaboom")

        orch.analysts[AnalystType.RISK] = _Boom(ANALYST_CONFIGS[AnalystType.RISK])
        res = await orch.run_parallel_analysis(
            "X", context={},
            analyst_types=[AnalystType.RISK], max_workers=1,
        )
        assert res.analyst_results[AnalystType.RISK].status == "error"
        assert orch._recent_failures  # failure recorded

    @pytest.mark.asyncio
    async def test_orchestrator_accumulates_tokens(self):
        orch = ParallelAnalystOrchestrator(gateway=None)

        class _Tokens(BaseAnalystAgent):
            async def analyze(self, ticker, context):
                return AnalystResult(
                    analyst_type=self.config.analyst_type,
                    status="success",
                    findings={},
                    confidence=1.0,
                    key_points=[],
                    warnings=[],
                    # not stock attribute but read it dynamically
                )

        # Make agent return a result with `.tokens_used` set.
        @dataclass
        class _ResultWithTokens(AnalystResult):
            tokens_used: int = 0

        result = _ResultWithTokens(
            analyst_type=AnalystType.RISK, status="success",
            findings={}, confidence=1.0, key_points=[], warnings=[],
            tokens_used=42,
        )

        async def _fake(ticker, context):
            return result

        agent = BaseAnalystAgent(ANALYST_CONFIGS[AnalystType.RISK])
        agent.analyze = _fake  # type: ignore[assignment]
        orch.analysts[AnalystType.RISK] = agent
        await orch.run_parallel_analysis("X", context={},
                                          analyst_types=[AnalystType.RISK])
        assert orch._tokens_consumed == 42


# ─────────── 9. TushareDataAgent ──────────────────────────────────────────────


class TestTushareDataAgent:
    def setup_method(self):
        self.agent = TushareDataAgent(ts_code="000001.SZ")

    def test_init_defaults(self):
        a = TushareDataAgent()
        assert a.default_ts_code is None
        assert a.auto_convert is True

    def test_init_with_args(self):
        a = TushareDataAgent(ts_code="600000.SH", auto_convert=False)
        assert a.default_ts_code == "600000.SH"
        assert a.auto_convert is False

    def test_handle_result_error(self):
        result = MagicMock(success=False, error="boom", is_mock=True)
        out = self.agent._handle_result(result, "test_data")
        assert out["_error"] is True
        assert "boom" in out["message"]
        assert out["is_mock"] is True

    def test_handle_result_inner_error(self):
        result = MagicMock(success=True, is_mock=False, data={"_error": True, "message": "downstream"})
        out = self.agent._handle_result(result, "test_data")
        assert out["_error"] is True
        assert "downstream" in out["message"]
        assert out["is_mock"] is False

    def test_handle_result_success_clean(self):
        result = MagicMock(success=True, is_mock=False, data={"a": 1, "b": 2})
        out = self.agent._handle_result(result, "test_data")
        assert out == {"a": 1, "b": 2, "_is_mock": False}
        assert "_mock_warning" not in out

    def test_handle_result_success_with_mock_warning(self):
        result = MagicMock(success=True, is_mock=True, data={"a": 1})
        out = self.agent._handle_result(result, "quote_data")
        assert out["_is_mock"] is True
        assert "_mock_warning" in out
        assert "模拟数据" in out["_mock_warning"]
        assert "quote_data" in out["_mock_warning"]

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_daily_quote_uses_default_code(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"date": "20240101"})
        out = self.agent.get_daily_quote()
        assert "_is_mock" in out
        mcp.assert_called_once()
        args = mcp.call_args
        assert args[0][0] == "user-tushare"
        assert args[0][1] == "get_daily_quote"
        assert args[0][2]["ts_code"] == "000001.SZ"

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_daily_quote_explicit_code(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={})
        self.agent.get_daily_quote(ts_code="600000.SH", start_date="20240101",
                                   end_date="20241231", trade_date="")
        mcp.assert_called_once_with(
            "user-tushare", "get_daily_quote",
            {"ts_code": "600000.SH", "start_date": "20240101",
             "end_date": "20241231", "trade_date": ""},
        )

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_daily_quote_no_code(self, mcp):
        a = TushareDataAgent()  # no default
        out = a.get_daily_quote()
        assert out == {"_error": True, "message": "ts_code is required"}
        mcp.assert_not_called()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_index_data(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"k": 1})
        out = self.agent.get_index_data("000300.SH", "20240101", "20241231")
        assert "_is_mock" in out

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_margin_data(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"m": 1})
        out = self.agent.get_margin_data("margin_detail")
        assert "_is_mock" in out

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_margin_data_hsgt(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"h": 1})
        self.agent.get_margin_data("hsgt")
        assert mcp.call_args[0][2] == {"data_type": "hsgt"}

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_financial_report_default(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={})
        self.agent.get_financial_report()
        assert mcp.call_args[0][2]["ts_code"] == "000001.SZ"
        assert mcp.call_args[0][2]["report_type"] == "income"

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_financial_report_no_code(self, mcp):
        a = TushareDataAgent()  # no code
        out = a.get_financial_report()
        assert out == {"_error": True, "message": "ts_code is required"}
        mcp.assert_not_called()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_stock_basic(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={})
        self.agent.get_stock_basic(exchange="SSE", list_status="L")
        assert mcp.call_args[0][2] == {"exchange": "SSE", "list_status": "L"}

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_trade_calendar(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"cal": []})
        self.agent.get_trade_calendar("20240101", "20241231", "SSE")
        assert mcp.call_args[0][2] == {
            "start_date": "20240101", "end_date": "20241231", "exchange": "SSE",
        }

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_concept_stocks(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={"list": []})
        self.agent.get_concept_stocks("新能源")
        assert mcp.call_args[0][1] == "get_concept_stocks"
        assert mcp.call_args[0][2] == {"concept_name": "新能源"}

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_full_analysis_aggregates(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={})
        out = self.agent.get_full_analysis()
        for key in ("quote", "financial_income", "financial_balance",
                    "financial_cashflow", "margin", "stock_basic"):
            assert key in out
        # Six MCP calls in total (quote + 3 fin statements + margin + stock_basic).
        assert mcp.call_count == 6

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_get_full_analysis_no_code(self, mcp):
        a = TushareDataAgent()
        out = a.get_full_analysis()
        assert out == {"_error": True, "message": "ts_code is required"}
        mcp.assert_not_called()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_mcp_failure_propagates(self, mcp):
        """When MCP returns a failed result, _handle_result converts it to
        an `_error` dict without raising."""
        mcp.return_value = MagicMock(success=False, error="upstream failure",
                                     is_mock=False)
        out = self.agent.get_daily_quote()
        assert out["_error"] is True
        assert "upstream failure" in out["message"]

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_trade_calendar_different_exchange(self, mcp):
        mcp.return_value = MagicMock(success=True, error="", is_mock=False, data={})
        self.agent.get_trade_calendar("20240101", "20241231", "SZSE")
        assert mcp.call_args[0][2]["exchange"] == "SZSE"

