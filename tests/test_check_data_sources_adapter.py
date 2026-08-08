"""Unit tests for scripts.data_source_checker.check_data_sources adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.data_source_checker import (
    DataSourceGateReport,
    _infer_requirements_from_text,
    check_data_sources,
)


def test_infer_macro_and_customs():
    reqs = _infer_requirements_from_text("使用海关出口与 GDP/CPI 宏观数据")
    names = {r.name for r in reqs}
    assert "customs" in names
    assert "macro" in names


def test_infer_us_equity():
    reqs = _infer_requirements_from_text("We use yfinance and SEC 10-K filings")
    assert any(r.name == "us_equity" for r in reqs)


def test_check_data_sources_report_property_back_compat():
    report = check_data_sources("纯理论")
    assert isinstance(report, DataSourceGateReport)
    assert report._report is report
    assert report.passed is True


def test_check_data_sources_available_sources_pass():
    with patch("scripts.data_source_checker.DataSourceChecker") as MockChecker:
        inst = MockChecker.return_value
        result = MagicMock()
        result.requires_synthetic_data = False
        result.summary_message = "ok"
        result.available_sources = ["akshare"]
        result.unavailable_sources = []
        inst.run.return_value = result
        report = check_data_sources("A股上市公司财务数据")
    assert report.passed is True
    assert report.details["available_sources"] == ["akshare"]
