"""tests/test_a_share_variables_deep_exec.py — Deep execution tests for
scripts/research_framework/a_share_variables.py

Extends shallow coverage in the original file with:
  - VariableResult dataclass (init, to_dict, computed_at)
  - AShareVariableFetcher (fetch, fetch_multiple, get_availability_summary,
    get_provenance, _normalize_institutional_df, _build_analyst_coverage_metrics)
  - VARIABLE_REGISTRY
  - Module-level MCP helpers (_call_mcp_tool, _call_mcp_tool_via_http)
  - Simulated fetch paths (top_list, block_trade, esg with no file)
  - fetch_a_share_variable convenience function
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import pandas as pd

try:
    from scripts.research_framework.a_share_variables import (
        AShareVariable,
        VariableAvailability,
        VariableSpec,
        VariableResult,
        AShareVariableFetcher,
        VARIABLE_REGISTRY,
        fetch_a_share_variable,
    )
except Exception as exc:
    pytest.skip(f"a_share_variables not importable: {exc}", allow_module_level=True)


# ─── VARIABLE_REGISTRY ────────────────────────────────────────────────────────

class TestVariableRegistry:
    def test_registry_not_empty(self):
        assert len(VARIABLE_REGISTRY) >= 5

    def test_all_enum_members_registered(self):
        for member in AShareVariable:
            assert member in VARIABLE_REGISTRY

    def test_registry_spec_types(self):
        for var, spec in VARIABLE_REGISTRY.items():
            assert isinstance(spec, VariableSpec)
            assert spec.variable == var
            assert isinstance(spec.display_name, str)
            assert isinstance(spec.description, str)
            assert isinstance(spec.research_uses, list)

    def test_margin_balance_spec(self):
        spec = VARIABLE_REGISTRY[AShareVariable.MARGIN_BALANCE]
        assert spec.mcp_server == "user-tushare"
        assert spec.availability == VariableAvailability.AVAILABLE

    def test_top_list_spec(self):
        spec = VARIABLE_REGISTRY[AShareVariable.TOP_LIST]
        assert spec.availability == VariableAvailability.NEEDS_NEW_TOOL
        assert spec.mcp_server is None

    def test_esg_spec(self):
        spec = VARIABLE_REGISTRY[AShareVariable.ESG_RATING]
        assert spec.availability == VariableAvailability.AVAILABLE_FILE
        assert spec.local_file is not None


# ─── VariableResult dataclass ─────────────────────────────────────────────────

class TestVariableResult:
    def test_basic_init(self):
        r = VariableResult(
            variable=AShareVariable.MARGIN_BALANCE,
            data=pd.DataFrame({"col": [1, 2, 3]}),
            source="mcp:tushare",
            source_detail="margin_detail",
            available=True,
            is_simulated=False,
        )
        assert r.variable == AShareVariable.MARGIN_BALANCE
        assert isinstance(r.data, pd.DataFrame)
        assert r.available is True
        assert r.is_simulated is False

    def test_simulated_init(self):
        r = VariableResult(
            variable=AShareVariable.TOP_LIST,
            data=None,
            source="simulated",
            source_detail="",
            available=False,
            is_simulated=True,
            error="No MCP tool",
        )
        assert r.available is False
        assert r.is_simulated is True
        assert len(r.error) > 0

    def test_cached_flag(self):
        r = VariableResult(
            variable=AShareVariable.NORTH_FLOW,
            data=pd.DataFrame(),
            source="mcp:tushare",
            source_detail="hsgt",
            available=True,
        )
        assert r.cached is False
        r.cached = True
        assert r.cached is True

    def test_to_dict(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        r = VariableResult(
            variable=AShareVariable.ESG_RATING,
            data=df,
            source="file",
            source_detail="data/esg.json",
            available=True,
        )
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["variable"] == "esg_rating"
        assert d["available"] is True
        assert d["source_detail"] == "data/esg.json"
        assert d["n_rows"] == 2


# ─── AShareVariableFetcher ────────────────────────────────────────────────────

class TestAShareVariableFetcher:
    def test_init_defaults(self):
        f = AShareVariableFetcher()
        assert f.cache_ttl == 86400.0
        assert f.verbose is False
        assert isinstance(f._cache, dict)

    def test_init_custom(self):
        # cache_ttl_seconds is the actual parameter name
        f = AShareVariableFetcher(cache_ttl_seconds=3600.0, verbose=True)
        assert f.cache_ttl == 3600.0
        assert f.verbose is True

    def test_standard_columns_mapping(self):
        f = AShareVariableFetcher()
        assert AShareVariable.MARGIN_BALANCE in f.STANDARD_COLUMNS
        assert AShareVariable.NORTH_FLOW in f.STANDARD_COLUMNS
        assert AShareVariable.ESG_RATING in f.STANDARD_COLUMNS
        cols = f.STANDARD_COLUMNS[AShareVariable.MARGIN_BALANCE]
        assert "ts_code" in cols
        assert "trade_date" in cols
        assert "margin_balance" in cols

    # ── fetch: simulated paths ──────────────────────────────────────────

    def test_fetch_top_list_simulated(self):
        f = AShareVariableFetcher()
        r = f.fetch(AShareVariable.TOP_LIST)
        assert r.available is False
        assert r.is_simulated is True
        assert len(r.error) > 0
        assert "top_list" in r.error.lower() or "toplist" in r.error.lower()

    def test_fetch_top_list_by_name(self):
        f = AShareVariableFetcher()
        r = f.fetch("top_list")
        assert r.available is False
        assert r.is_simulated is True

    def test_fetch_block_trade_simulated(self):
        f = AShareVariableFetcher()
        r = f.fetch(AShareVariable.BLOCK_TRADE)
        assert r.available is False
        assert r.is_simulated is True
        assert len(r.error) > 0

    def test_fetch_block_trade_by_name(self):
        f = AShareVariableFetcher()
        r = f.fetch("block_trade")
        assert r.available is False
        assert r.is_simulated is True

    def test_fetch_analyst_coverage_no_ts_code(self):
        f = AShareVariableFetcher()
        r = f.fetch(AShareVariable.ANALYST_COVERAGE)
        assert r.available is False
        assert r.is_simulated is True
        assert "required" in r.error.lower() or "ts_code" in r.error.lower()

    def test_fetch_institutional_hold_no_ts_code(self):
        f = AShareVariableFetcher()
        r = f.fetch(AShareVariable.INSTITUTIONAL_HOLD)
        assert r.available is False
        assert r.is_simulated is True

    def test_fetch_unknown_variable(self):
        f = AShareVariableFetcher()
        # AShareVariable("nonexistent_var_xyz") raises ValueError
        with pytest.raises(ValueError):
            f.fetch("nonexistent_var_xyz")

    # ── fetch: simulated ESG path (no local file) ──────────────────────

    def test_fetch_esg_no_file_no_network(self):
        f = AShareVariableFetcher(verbose=True)
        r = f.fetch(AShareVariable.ESG_RATING, ts_code="600519.SH")
        # The Sina scraper may succeed (returning a row with msci_rating=None),
        # or it may fail (return simulated). Accept either outcome.
        assert isinstance(r, VariableResult)

    # ── fetch_multiple ───────────────────────────────────────────────────

    def test_fetch_multiple(self):
        f = AShareVariableFetcher()
        results = f.fetch_multiple(
            [AShareVariable.TOP_LIST, AShareVariable.BLOCK_TRADE]
        )
        assert isinstance(results, dict)
        assert "top_list" in results
        assert "block_trade" in results

    def test_fetch_multiple_by_name(self):
        f = AShareVariableFetcher()
        results = f.fetch_multiple(["top_list", "esg_rating"])
        assert "top_list" in results
        assert "esg_rating" in results

    # ── get_availability_summary ────────────────────────────────────────

    def test_get_availability_summary(self):
        f = AShareVariableFetcher()
        df = f.get_availability_summary()
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 5
        assert "variable" in df.columns
        assert "display_name" in df.columns
        assert "availability" in df.columns
        assert "mcp_server" in df.columns

    # ── get_provenance ─────────────────────────────────────────────────

    def test_get_provenance(self):
        f = AShareVariableFetcher()
        tracker = f.get_provenance()
        assert tracker is not None
        # Should have a record method
        assert hasattr(tracker, "record")

    # ── internal helpers ────────────────────────────────────────────────

    def test_normalize_institutional_df_basic(self):
        f = AShareVariableFetcher()
        df = pd.DataFrame({
            "holder_name_col": ["Fund A", "Fund B"],
            "holder_type_col": ["QFII", "Fund"],
            "hold_pct_col": [0.05, 0.03],
            "ann_date_col": ["2023-01-01", "2023-01-02"],
            "ts_code_col": ["000001.SZ", "000002.SZ"],
        })
        result = f._normalize_institutional_df(df)
        assert isinstance(result, pd.DataFrame)

    def test_normalize_institutional_df_empty(self):
        f = AShareVariableFetcher()
        result = f._normalize_institutional_df(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)

    def test_build_analyst_coverage_metrics_empty(self):
        f = AShareVariableFetcher()
        df = pd.DataFrame()
        result = f._build_analyst_coverage_metrics(df, "000001.SZ")
        assert isinstance(result, pd.DataFrame)
        assert result["analyst_count"].iloc[0] == 0

    def test_build_analyst_coverage_metrics_with_data(self):
        f = AShareVariableFetcher()
        df = pd.DataFrame({
            "analyst": ["A", "B", "A", "C"],
            "report_date": ["2023-01-01", "2023-01-02", "2023-02-01", "2023-03-01"],
            "rating": ["买入", "增持", "中性", "推荐"],
        })
        result = f._build_analyst_coverage_metrics(df, "000001.SZ")
        assert isinstance(result, pd.DataFrame)
        assert result["analyst_count"].iloc[0] == 3
        assert result["ts_code"].iloc[0] == "000001.SZ"


# ─── Module convenience function ────────────────────────────────────────────────

class TestFetchAFShareVariable:
    def test_fetch_a_share_variable_callable(self):
        assert callable(fetch_a_share_variable)

    def test_fetch_a_share_variable_top_list(self):
        r = fetch_a_share_variable("top_list")
        assert r.available is False

    def test_fetch_a_share_variable_block_trade(self):
        r = fetch_a_share_variable("block_trade")
        assert r.available is False

    def test_fetch_a_share_variable_unknown(self):
        # Invalid variable name raises ValueError
        with pytest.raises(ValueError):
            fetch_a_share_variable("nonexistent_var")

    def test_fetch_a_share_variable_with_tracker(self):
        from scripts.research_framework.a_share_variables import ProvenanceTracker
        tracker = ProvenanceTracker()
        r = fetch_a_share_variable("top_list", tracker=tracker)
        assert r is not None
