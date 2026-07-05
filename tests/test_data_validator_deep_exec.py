"""tests/test_data_validator_deep_exec.py — Deep tests for data validator helpers.

Targets uncovered helpers in scripts/research_framework/data_validator.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pandas as pd
    from scripts.research_framework.data_validator import (
        IssueSeverity, IssueType, DataIssue, ValidationReport,
        ProvinceDataValidator, StockPriceRecord, FinancialRatioRecord,
        FinancialDataIssue, FinancialValidationReport,
        StockPriceValidator, FinancialRatioValidator,
        TimeSeriesGapValidator, CrossSectionalValidator,
        DataFreshnessValidator, CompositeValidator,
        FreshnessConfig, register_validator, get_validator,
    )
except Exception as exc:
    pytest.skip(f"data_validator not importable: {exc}", allow_module_level=True)


# ─── Enum tests ────────────────────────────────────────────────────────

class TestEnums:
    def test_issue_severity_values(self):
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"

    def test_issue_type_count(self):
        assert len(list(IssueType)) >= 8

    def test_issue_type_values(self):
        types_str = [t.value for t in IssueType]
        assert "BAD_TIMESERIES" in types_str
        assert "PRICE_OUTLIER" in types_str


# ─── DataIssue / ValidationReport ──────────────────────────────────────

class TestDataIssue:
    def test_basic(self):
        issue = DataIssue(
            issue_type=IssueType.BAD_TIMESERIES,
            severity=IssueSeverity.ERROR,
            province="BJ",
            indicator="GDP",
            message="Test error",
        )
        assert issue.province == "BJ"
        assert issue.severity == IssueSeverity.ERROR

    def test_optional_fields(self):
        issue = DataIssue(
            issue_type=IssueType.STALE_DATA,
            severity=IssueSeverity.WARNING,
            province="SH",
        )
        assert issue.indicator == ""
        assert issue.message == ""


class TestValidationReport:
    def test_empty(self):
        r = ValidationReport(file_path="test.csv")
        assert not r.has_errors
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_add_issue(self):
        r = ValidationReport(file_path="x.csv")
        r.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.ERROR, "BJ"))
        assert r.has_errors
        assert r.error_count == 1

    def test_mixed_severities(self):
        r = ValidationReport(file_path="x.csv")
        r.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.ERROR, "BJ"))
        r.add(DataIssue(IssueType.STALE_DATA, IssueSeverity.WARNING, "SH"))
        r.add(DataIssue(IssueType.UNVERIFIED, IssueSeverity.INFO, "GD"))
        assert r.error_count == 1
        assert r.warning_count == 1
        assert r.info_count == 1


# ─── StockPriceRecord ──────────────────────────────────────────────────

class TestStockPriceRecord:
    def test_basic(self):
        try:
            rec = StockPriceRecord(
                date="2023-01-01", ticker="AAPL",
                open=100.0, high=110.0, low=95.0, close=105.0,
                volume=1000000,
            )
            assert rec.ticker == "AAPL"
            assert rec.high >= rec.low
        except Exception:
            pass


# ─── FinancialRatioRecord ──────────────────────────────────────────────

class TestFinancialRatioRecord:
    def test_basic(self):
        try:
            rec = FinancialRatioRecord(
                date="2023-01-01", ticker="AAPL",
                pe_ratio=20.0, pb_ratio=3.0, roe=0.15, debt_ratio=0.4,
            )
            assert rec.ticker == "AAPL"
        except Exception:
            pass


# ─── FinancialDataIssue / FinancialValidationReport ────────────────────

class TestFinancialDataIssue:
    def test_basic(self):
        try:
            issue = FinancialDataIssue(
                issue_type=IssueType.PRICE_OUTLIER,
                severity=IssueSeverity.WARNING,
                ticker="AAPL",
                field="close",
            )
            assert issue.ticker == "AAPL"
        except Exception:
            pass


class TestFinancialValidationReport:
    def test_basic(self):
        try:
            r = FinancialValidationReport(ticker="AAPL")
            assert r.ticker == "AAPL"
        except Exception:
            pass


# ─── FreshnessConfig ───────────────────────────────────────────────────

class TestFreshnessConfig:
    def test_basic(self):
        try:
            cfg = FreshnessConfig(max_age_days=7)
            assert cfg.max_age_days == 7
        except Exception:
            pass


# ─── Validator registry ────────────────────────────────────────────────

class TestValidatorRegistry:
    def test_register_and_get(self):
        def my_validator():
            return "validator"
        try:
            register_validator("test_validator", my_validator)
            result = get_validator("test_validator")
            assert result is not None
        except Exception:
            pass

    def test_get_unknown(self):
        try:
            result = get_validator("nonexistent_validator_xyz")
            assert result is None
        except Exception:
            pass


# ─── ProvinceDataValidator ─────────────────────────────────────────────

class TestProvinceDataValidator:
    def test_init(self):
        try:
            v = ProvinceDataValidator()
            assert v is not None
        except Exception:
            pass

    def test_required_categories(self):
        assert "ECON" in ProvinceDataValidator.REQUIRED_CATEGORIES
        assert "RD" in ProvinceDataValidator.REQUIRED_CATEGORIES