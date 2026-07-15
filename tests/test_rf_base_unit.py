"""Unit tests for scripts/research_framework/base.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def rfb():
    sys.path.insert(0, str(SCRIPTS_DIR))
    from research_framework import base as b
    yield b
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestDataSourceEnum:
    def test_all_members_are_strings(self, rfb):
        for member in rfb.DataSource:
            assert isinstance(member.value, str)
            assert isinstance(member, str)  # also a string instance

    def test_mcp_yfinance(self, rfb):
        assert rfb.DataSource.MCP_YFINANCE == "mcp:yfinance"

    def test_mcp_tushare(self, rfb):
        assert rfb.DataSource.MCP_TUSHARE == "mcp:tushare"

    def test_simulated(self, rfb):
        assert rfb.DataSource.SIMULATED == "simulated"

    def test_manual(self, rfb):
        assert rfb.DataSource.MANUAL == "manual"

    def test_comparison_with_string(self, rfb):
        assert rfb.DataSource.MCP_YFINANCE == "mcp:yfinance"
        assert "mcp:yfinance" == rfb.DataSource.MCP_YFINANCE

    def test_value_attribute(self, rfb):
        assert rfb.DataSource.MCP_FINVIZ.value == "mcp:finviz"


class TestStars:
    def test_three_stars(self, rfb):
        assert rfb._stars(0.0001) == "***"

    def test_two_stars(self, rfb):
        result = rfb._stars(0.002)
        assert result == "**"

    def test_one_star(self, rfb):
        result = rfb._stars(0.01)
        assert result == "*"

    def test_dagger_for_p05(self, rfb):
        result = rfb._stars(0.05)
        assert "dagger" in result.lower() or "†" in result or result == ""

    def test_no_stars_high_p(self, rfb):
        result = rfb._stars(0.5)
        assert result == ""

    def test_nan(self, rfb):
        import math
        assert rfb._stars(math.nan) == ""


class TestExports:
    def test_data_source_exported(self, rfb):
        assert hasattr(rfb, "DataSource")

    def test_stars_exported(self, rfb):
        assert hasattr(rfb, "_stars")

