"""Unit tests for scripts/green_credit_data.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def gd():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import green_credit_data as g
    yield g
    if _p in sys.path:
        sys.path.remove(_p)


class TestDataSource:
    def test_exists(self, gd):
        assert hasattr(gd, "DataSource")

    def test_data_status(self, gd):
        assert hasattr(gd, "DataStatus")


class TestFunctions:
    def test_fetch_mcp_tushare_financial(self, gd):
        assert callable(gd.fetch_mcp_tushare_financial)

    def test_fetch_mcp_tushare_financial_batch(self, gd):
        assert callable(gd.fetch_mcp_tushare_financial_batch)

    def test_fetch_multiple_stocks(self, gd):
        # Bug #2 regression: fetch_multiple_stocks was missing and would NameError
        assert callable(gd.fetch_multiple_stocks)

    def test_fetch_multiple_stocks_default_no_mock(self, gd, monkeypatch):
        """By default (allow_user_approved_mock=False), mock layer is skipped
        even when tushare + stock_data both fail."""
        # Force both layers to fail
        monkeypatch.setattr(gd, "fetch_mcp_tushare_financial_batch",
                            lambda symbols, report_type="balance": {"success": {}, "failed": {s: "x" for s in symbols}})
        monkeypatch.setattr(gd, "fetch_mcp_stock_data",
                            lambda symbols: {"success": {}, "failed": {s: "x" for s in symbols}})
        result = gd.fetch_multiple_stocks(["600519"], allow_user_approved_mock=False)
        assert result["success"] == {}
        assert "600519" in result["failed"]
        assert "all sources exhausted" in result["failed"]["600519"]

    def test_fetch_multiple_stocks_mock_when_approved(self, gd, monkeypatch):
        """When allow_user_approved_mock=True, mock layer fills remaining failures."""
        monkeypatch.setattr(gd, "fetch_mcp_tushare_financial_batch",
                            lambda symbols, report_type="balance": {"success": {}, "failed": {s: "x" for s in symbols}})
        monkeypatch.setattr(gd, "fetch_mcp_stock_data",
                            lambda symbols: {"success": {}, "failed": {s: "x" for s in symbols}})
        result = gd.fetch_multiple_stocks(["600519", "000001"], allow_user_approved_mock=True)
        assert set(result["success"].keys()) == {"600519", "000001"}
        assert result["success"]["600519"]["source"] == gd.DataSource.MOCK_DATA
        assert result["failed"] == {}

    def test_fetch_multiple_stocks_layer_recovery(self, gd, monkeypatch):
        """If layer 2 (stock_data) recovers some failures from layer 1, those should appear in success."""
        def fake_tushare(symbols, report_type="balance"):
            return {"success": {"000001": {"source": "tushare", "data": {}, "ticker": "000001"}},
                    "failed": {"600519": "x"}}
        def fake_stock(symbols):
            return {"success": {"600519": {"source": "stock_data", "data": {}, "ticker": "600519"}},
                    "failed": {}}
        monkeypatch.setattr(gd, "fetch_mcp_tushare_financial_batch", fake_tushare)
        monkeypatch.setattr(gd, "fetch_mcp_stock_data", fake_stock)
        result = gd.fetch_multiple_stocks(["000001", "600519"])
        assert set(result["success"].keys()) == {"000001", "600519"}
        assert result["failed"] == {}
