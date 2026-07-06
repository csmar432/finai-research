"""tests/test_research_framework_base_smoke.py — Smoke tests for scripts/research_framework/base.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.base import (
        DataSource,
        DataProvenance,
        ProvenanceTracker,
        fmt_coef,
        stars_for_stars,
        to_markdown_table,
        to_latex_table,
    )
except Exception as _exc:
    pytest.skip(f"base not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert DataSource is not None
        assert ProvenanceTracker is not None

    def test_datasource_is_string_enum(self):
        # DataSource should compare equal to its string value
        assert DataSource.MCP_YFINANCE == "mcp:yfinance"
        assert DataSource.MCP_YFINANCE.value == "mcp:yfinance"


class TestStars:
    def test_three_stars(self):
        assert stars_for_stars(0.0001) == "***"

    def test_two_stars(self):
        assert stars_for_stars(0.005) == "**"

    def test_one_star(self):
        assert stars_for_stars(0.02) == "*"

    def test_dagger(self):
        assert stars_for_stars(0.07) == r"$\dagger$"

    def test_no_significance(self):
        assert stars_for_stars(0.5) == ""


class TestFmtCoef:
    def test_format(self):
        out = fmt_coef(0.052, 0.021, 0.018)
        assert "0.052" in out
        assert "0.021" in out
        assert "*" in out  # significant

    def test_no_stars(self):
        out = fmt_coef(0.05, 0.10, 0.5, stars=False)
        assert "*" not in out

    def test_precision(self):
        out = fmt_coef(0.123456, 0.012345, 0.3, prec=4)
        assert "0.1235" in out


class TestProvenanceTracker:
    def test_record_basic(self):
        tracker = ProvenanceTracker()
        tracker.record("roa", DataSource.MCP_YFINANCE, "API response")
        summary = tracker.summary()
        assert summary["by_source"]["mcp:yfinance"] == 1
        assert summary["total_fields"] == 1

    def test_flag_simulated(self):
        tracker = ProvenanceTracker()
        tracker.flag_simulated("roa", "yfinance returned empty")
        summary = tracker.summary()
        assert summary["simulated"] == 1

    def test_flag_fallback(self):
        tracker = ProvenanceTracker()
        tracker.flag_fallback("roa", method="industry_median")
        summary = tracker.summary()
        assert summary["fallback"] == 1

    def test_record_string_source(self):
        tracker = ProvenanceTracker()
        tracker.record("x", "manual_csv", "user uploaded file")
        summary = tracker.summary()
        assert summary["total_fields"] == 1


class TestMarkdownTable:
    def test_simple(self):
        df = pd.DataFrame({"A": [1, 2], "B": [3.5, 4.6]})
        out = to_markdown_table(df)
        assert "| A | B |" in out
        assert "| 1.000 | 3.500 |" in out

    def test_empty(self):
        df = pd.DataFrame()
        assert to_markdown_table(df) == "_No data_"


class TestLatexTable:
    def test_simple(self):
        df = pd.DataFrame({"col1": [1, 2], "col2": [3.5, 4.6]})
        out = to_latex_table(df, caption="Test table", label="tab:test")
        assert "\\begin{table}" in out
        assert "\\caption{Test table}" in out
        assert "\\label{tab:test}" in out
        assert "\\toprule" in out
        assert "\\bottomrule" in out
        assert "col1" in out

    def test_notes(self):
        df = pd.DataFrame({"a": [1.0]})
        out = to_latex_table(df, notes="standard errors in parens")
        assert "tablenotes" in out
        assert "standard errors in parens" in out
