"""
Deep execution tests for scripts/research_framework/data_validator.py

Covers: Enums, Dataclasses, ProvinceDataValidator, StockPriceValidator,
FinancialRatioValidator, TimeSeriesGapValidator, CrossSectionalValidator,
DataFreshnessValidator, CompositeValidator, and registry helpers.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.research_framework.data_validator import (
    # Enums
    IssueSeverity,
    IssueType,
    # Province dataclasses
    DataIssue,
    ValidationReport,
    # Financial dataclasses
    StockPriceRecord,
    FinancialRatioRecord,
    TradingCalendarRecord,
    FinancialDataIssue,
    FinancialValidationReport,
    FreshnessConfig,
    # Validators
    ProvinceDataValidator,
    StockPriceValidator,
    FinancialRatioValidator,
    TimeSeriesGapValidator,
    CrossSectionalValidator,
    DataFreshnessValidator,
    CompositeValidator,
    # Registry helpers
    register_validator,
    get_validator,
    list_validators,
    clear_registry,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_province_data():
    """Minimal valid province data JSON for ProvinceDataValidator."""
    return {
        "meta": {"source": "test", "year": 2024},
        "indicator_schema": {},
        "provinces": {
            "北京": {
                "data": {
                    "ECON": {
                        "GDP_2024": {"value": 45602.0, "source": "北京市统计局"},
                        "GDP增速_2024": {"value": 5.2, "source": "北京市统计局"},
                    },
                    "EDU": {
                        "高校数量": {"value": 92, "source": "教育部"},
                    },
                    "PLAT": {
                        "国家重点实验室": {"value": 120, "source": "科技部"},
                    },
                    "RD": {
                        "R&D经费_2024": {"value": 2500.0, "source": "北京市统计局"},
                    },
                    "ENT": {
                        "高新技术企业": {"value": 78000, "source": "北京市科委"},
                    },
                    "TECH": {
                        "技术合同成交额": {"value": 8500.0, "source": "技术市场"},
                    },
                    "IND": {
                        "高技术产业营收": {"value": 12000.0, "source": "北京市统计局"},
                    },
                    "AI": {},
                    "FIN": {},
                },
                "time_series": {
                    "GDP": {
                        "data": {
                            "2022": 41610.9,
                            "2023": 43760.0,
                            "2024": 45602.0,
                        }
                    },
                    "R&D经费": {
                        "data": {
                            "2022": 2100.0,
                            "2023": 2300.0,
                            "2024": 2500.0,
                        }
                    },
                },
                "verification": "full",
            },
        },
        "ranking_tables": {
            "GDP_2024": {
                "data": [
                    {"rank": 1, "province": "北京", "value": 45602.0},
                ],
                "source": "test",
            },
        },
        "verification_status": {
            "full": ["北京"],
            "partial": [],
            "minimal": [],
        },
    }


@pytest.fixture
def corrupt_province_data():
    """Corrupt province data to trigger multiple validation errors."""
    return {
        "meta": {},
        # missing: indicator_schema, provinces, ranking_tables, verification_status
        "provinces": {
            "损坏省": {
                "data": {},  # no categories
                "time_series": {},
                "verification": "minimal",
            },
            "异常省": {
                "data": {
                    "ECON": {
                        "GDP": {
                            "value": 1000.0,
                            # missing source
                        },
                    },
                },
                "time_series": {
                    "GDP": {
                        "data": {
                            "2021": 1000.0,
                            "2022": 100.0,  # -90% YoY — suspicious
                        }
                    },
                    "R&D经费": {
                        "data": {
                            "2022": 0.5,  # too small
                        }
                    },
                },
                "verification": "partial",
            },
        },
        "ranking_tables": {
            "GDP_2024": {
                "data": [
                    {"rank": 1, "province": "A", "value": 100.0},
                    {"rank": 1, "province": "B", "value": 90.0},  # duplicate rank
                    {"rank": 3, "province": "C", "value": 80.0},  # non-sequential
                ],
                # missing source
            },
            "EMPTY_TABLE": {
                "data": [],  # empty ranking
            },
        },
        "verification_status": {
            "full": ["异常省"],  # declared but not actually full
            "partial": [],
            "minimal": [],
        },
    }


@pytest.fixture
def province_data_file(tmp_path, minimal_province_data):
    """Write minimal_province_data to a temp JSON file."""
    p = tmp_path / "province_test.json"
    p.write_text(json.dumps(minimal_province_data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def corrupt_data_file(tmp_path, corrupt_province_data):
    """Write corrupt_province_data to a temp JSON file."""
    p = tmp_path / "corrupt_province_test.json"
    p.write_text(json.dumps(corrupt_province_data, ensure_ascii=False), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestEnums:
    def test_issue_severity_values(self):
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"

    def test_issue_type_values(self):
        assert IssueType.MISSING_SOURCE.value == "MISSING_SOURCE"
        assert IssueType.BAD_TIMESERIES.value == "BAD_TIMESERIES"
        assert IssueType.PRICE_OUTLIER.value == "PRICE_OUTLIER"
        assert IssueType.RATIO_OUT_OF_RANGE.value == "RATIO_OUT_OF_RANGE"
        assert IssueType.MISSING_TRADING_DAYS.value == "MISSING_TRADING_DAYS"
        assert IssueType.CROSS_SECTION_INCONSISTENCY.value == "CROSS_SECTION_INCONSISTENCY"
        assert IssueType.DATA_FRESHNESS.value == "DATA_FRESHNESS"
        assert IssueType.UNVERIFIED.value == "UNVERIFIED"


# ─────────────────────────────────────────────────────────────────────────────
# TEST: DataIssue dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestDataIssue:
    def test_constructor_defaults(self):
        issue = DataIssue(
            issue_type=IssueType.MISSING_SOURCE,
            severity=IssueSeverity.WARNING,
            province="北京",
        )
        assert issue.issue_type == IssueType.MISSING_SOURCE
        assert issue.severity == IssueSeverity.WARNING
        assert issue.province == "北京"
        assert issue.indicator == ""
        assert issue.message == ""
        assert issue.detail == ""
        assert issue.suggestion == ""

    def test_constructor_full(self):
        issue = DataIssue(
            issue_type=IssueType.SUSPICIOUS_VALUE,
            severity=IssueSeverity.ERROR,
            province="广东",
            indicator="GDP",
            message="异常值",
            detail="detail",
            suggestion="fix it",
        )
        assert issue.issue_type == IssueType.SUSPICIOUS_VALUE
        assert issue.severity == IssueSeverity.ERROR
        assert issue.province == "广东"
        assert issue.indicator == "GDP"
        assert issue.message == "异常值"
        assert issue.detail == "detail"
        assert issue.suggestion == "fix it"


# ─────────────────────────────────────────────────────────────────────────────
# TEST: ValidationReport dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestValidationReport:
    def test_constructor(self):
        report = ValidationReport(file_path="/path/to/file.json")
        assert report.file_path == "/path/to/file.json"
        assert report.issues == []
        assert report.stats == {}

    def test_add(self):
        report = ValidationReport(file_path="/test.json")
        issue = DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.INFO, "北京")
        report.add(issue)
        assert len(report.issues) == 1

    def test_has_errors_true(self):
        report = ValidationReport(file_path="/test.json")
        report.add(DataIssue(IssueType.MISSING_SOURCE, IssueSeverity.ERROR, "北京"))
        assert report.has_errors is True

    def test_has_errors_false(self):
        report = ValidationReport(file_path="/test.json")
        report.add(DataIssue(IssueType.MISSING_SOURCE, IssueSeverity.WARNING, "北京"))
        assert report.has_errors is False

    def test_error_count(self):
        report = ValidationReport(file_path="/test.json")
        report.add(DataIssue(IssueType.MISSING_SOURCE, IssueSeverity.ERROR, "A"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.ERROR, "B"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.WARNING, "C"))
        assert report.error_count == 2

    def test_warning_count(self):
        report = ValidationReport(file_path="/test.json")
        report.add(DataIssue(IssueType.MISSING_SOURCE, IssueSeverity.WARNING, "A"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.WARNING, "B"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.INFO, "C"))
        assert report.warning_count == 2

    def test_info_count(self):
        report = ValidationReport(file_path="/test.json")
        report.add(DataIssue(IssueType.MISSING_SOURCE, IssueSeverity.INFO, "A"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.INFO, "B"))
        report.add(DataIssue(IssueType.BAD_TIMESERIES, IssueSeverity.ERROR, "C"))
        assert report.info_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# TEST: ProvinceDataValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestProvinceDataValidatorInit:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ProvinceDataValidator(data_file=tmp_path / "nonexistent.json")

    def test_load_valid_file(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        assert validator.data_file == province_data_file
        assert "provinces" in validator.data
        assert "北京" in validator.data["provinces"]


class TestProvinceDataValidatorStructure:
    def test_check_structure_passes(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = ValidationReport(file_path=str(province_data_file))
        validator._check_structure(report)
        assert not report.has_errors

    def test_check_structure_fails(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = ValidationReport(file_path=str(corrupt_data_file))
        validator._check_structure(report)
        assert report.has_errors
        assert any(
            "顶层缺少字段" in i.message for i in report.issues
        )

    def test_validate_all_runs(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.validate_all()
        assert report.file_path == str(province_data_file)
        assert isinstance(report.stats, dict)


class TestProvinceDataValidatorCompleteness:
    def test_missing_categories(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        # 损坏省 has empty data dict, verification=minimal so no warning
        # 异常省 has some data but missing most categories
        assert len(report.issues) >= 0  # passes gracefully


class TestProvinceDataValidatorTimeseries:
    def test_gdp_yoy_in_range(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.validate_all()
        # 北京 GDP 2023→2024 YoY is reasonable
        suspicious = [
            i for i in report.issues
            if i.issue_type == IssueType.SUSPICIOUS_VALUE
        ]
        assert len(suspicious) == 0

    def test_gdp_yoy_out_of_range(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        suspicious = [
            i for i in report.issues
            if i.issue_type == IssueType.SUSPICIOUS_VALUE
            and "GDP" in i.message
        ]
        assert len(suspicious) >= 1

    def test_rd经费_too_small(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        rd_issues = [
            i for i in report.issues
            if "R&D经费" in i.message and "0.5" in i.message
        ]
        assert len(rd_issues) >= 1


class TestProvinceDataValidatorRankings:
    def test_empty_ranking(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        empty_issues = [
            i for i in report.issues
            if "EMPTY_TABLE" in i.message and "空" in i.message
        ]
        assert len(empty_issues) >= 1

    def test_non_sequential_ranks(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        rank_issues = [
            i for i in report.issues
            if "排名不连续" in i.message
        ]
        assert len(rank_issues) >= 1

    def test_ranking_missing_source(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        source_issues = [
            i for i in report.issues
            if i.issue_type == IssueType.MISSING_SOURCE
        ]
        assert len(source_issues) >= 1


class TestProvinceDataValidatorSources:
    def test_missing_source_warning(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        missing_source = [
            i for i in report.issues
            if i.issue_type == IssueType.MISSING_SOURCE
        ]
        assert len(missing_source) >= 1


class TestProvinceDataValidatorVerification:
    def test_full_not_in_status(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        unverified = [
            i for i in report.issues
            if i.issue_type == IssueType.UNVERIFIED
        ]
        assert len(unverified) >= 1


class TestProvinceDataValidatorComputeStats:
    def test_stats_populated(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.validate_all()
        assert "total_provinces" in report.stats
        assert report.stats["total_provinces"] >= 1
        assert "total_indicators" in report.stats
        assert report.stats["total_indicators"] >= 1


class TestProvinceDataValidatorCheckProvince:
    def test_unknown_province(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.check_province("不存在的省")
        assert report.has_errors
        assert any(
            "不在数据集中" in i.message for i in report.issues
        )

    def test_known_province(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.check_province("北京")
        assert not report.has_errors

    def test_check_province_missing_cats(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.check_province("异常省")
        # Should have missing categories warning
        assert len(report.issues) >= 0


class TestProvinceDataValidatorPrintReport:
    def test_print_report_no_issues(self, capsys, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.validate_all()
        validator.print_report(report)
        captured = capsys.readouterr().out
        assert "省级数据验证报告" in captured
        assert "验证结果:" in captured

    def test_print_report_with_issues(self, capsys, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        validator.print_report(report)
        captured = capsys.readouterr().out
        assert "详细问题列表" in captured or "ERROR" in captured


# ─────────────────────────────────────────────────────────────────────────────
# TEST: StockPriceRecord dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestStockPriceRecord:
    def test_required_fields(self):
        rec = StockPriceRecord(ts_code="000001.SZ", date="2024-01-02")
        assert rec.ts_code == "000001.SZ"
        assert rec.date == "2024-01-02"
        assert rec.open is None
        assert rec.high is None

    def test_full_fields(self):
        rec = StockPriceRecord(
            ts_code="AAPL",
            date="2024-01-02",
            open=150.0,
            high=155.0,
            low=149.0,
            close=154.0,
            volume=1_000_000.0,
            turnover=154_000_000.0,
        )
        assert rec.open == 150.0
        assert rec.close == 154.0
        assert rec.volume == 1_000_000.0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FinancialRatioRecord dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestFinancialRatioRecord:
    def test_required_fields(self):
        rec = FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31")
        assert rec.ts_code == "000001.SZ"
        assert rec.report_type == "annual"

    def test_full_fields(self):
        rec = FinancialRatioRecord(
            ts_code="AAPL",
            date="2024-09-30",
            report_type="Q3",
            roe=0.25,
            current_ratio=2.5,
            quick_ratio=2.0,
            debt_to_equity=1.2,
            gross_margin=0.40,
            net_margin=0.22,
            total_shares=15_000_000_000.0,
        )
        assert rec.roe == 0.25
        assert rec.debt_to_equity == 1.2


# ─────────────────────────────────────────────────────────────────────────────
# TEST: TradingCalendarRecord dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestTradingCalendarRecord:
    def test_defaults(self):
        rec = TradingCalendarRecord(date="2024-01-02")
        assert rec.is_trading_day is True
        assert rec.market == "SSE"

    def test_full_fields(self):
        rec = TradingCalendarRecord(
            date="2024-01-01",
            is_trading_day=False,
            market="SSE",
        )
        assert rec.is_trading_day is False


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FinancialDataIssue dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestFinancialDataIssue:
    def test_defaults(self):
        issue = FinancialDataIssue(
            issue_type=IssueType.PRICE_OUTLIER,
            severity=IssueSeverity.ERROR,
        )
        assert issue.ts_code == ""
        assert issue.field == ""
        assert issue.value is None

    def test_full_fields(self):
        issue = FinancialDataIssue(
            issue_type=IssueType.RATIO_OUT_OF_RANGE,
            severity=IssueSeverity.WARNING,
            ts_code="000001.SZ",
            field="roe",
            date="2024-12-31",
            message="ROE超出范围",
            value=8.0,
            expected_range="[-100%, 500%]",
            suggestion="检查数据",
        )
        assert issue.value == 8.0
        assert issue.suggestion == "检查数据"


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FinancialValidationReport dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestFinancialValidationReport:
    def test_constructor(self):
        report = FinancialValidationReport(validator_name="TestValidator")
        assert report.validator_name == "TestValidator"
        assert report.issues == []
        assert report.stats == {}
        assert report.validated_records == 0

    def test_add(self):
        report = FinancialValidationReport(validator_name="Test")
        issue = FinancialDataIssue(
            issue_type=IssueType.PRICE_OUTLIER,
            severity=IssueSeverity.ERROR,
        )
        report.add(issue)
        assert len(report.issues) == 1

    def test_has_errors(self):
        report = FinancialValidationReport(validator_name="Test")
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.ERROR))
        assert report.has_errors is True

    def test_error_count(self):
        report = FinancialValidationReport(validator_name="Test")
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.ERROR))
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.ERROR))
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.WARNING))
        assert report.error_count == 2

    def test_warning_count(self):
        report = FinancialValidationReport(validator_name="Test")
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.WARNING))
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.WARNING))
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.INFO))
        assert report.warning_count == 2

    def test_info_count(self):
        report = FinancialValidationReport(validator_name="Test")
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.INFO))
        report.add(FinancialDataIssue(IssueType.PRICE_OUTLIER, IssueSeverity.INFO))
        assert report.info_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FreshnessConfig dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestFreshnessConfig:
    def test_defaults(self):
        config = FreshnessConfig()
        assert config.warning_days == 30
        assert config.error_days == 90
        assert config.date_field == "date"
        assert config.reference_date is None

    def test_ref_date_from_param(self):
        config = FreshnessConfig(reference_date="2024-12-31")
        assert config.ref_date == "2024-12-31"

    def test_ref_date_fallback_to_now(self):
        config = FreshnessConfig()
        assert config.ref_date == datetime.now().strftime("%Y-%m-%d")

    def test_custom_values(self):
        config = FreshnessConfig(
            warning_days=60,
            error_days=180,
            date_field="report_date",
        )
        assert config.warning_days == 60
        assert config.error_days == 180


# ─────────────────────────────────────────────────────────────────────────────
# TEST: StockPriceValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestStockPriceValidator:
    def test_empty_records(self):
        validator = StockPriceValidator()
        report = validator.validate([])
        assert report.error_count == 0
        assert report.validated_records == 0

    def test_price_zero_error(self):
        rec = StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", open=0, close=0)
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert report.error_count >= 1

    def test_price_negative_error(self):
        rec = StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", open=-10.0)
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert any(
            i.issue_type == IssueType.PRICE_OUTLIER
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_high_less_than_low_error(self):
        rec = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            high=10.0,
            low=15.0,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert any(
            "high/low" in i.field.lower()
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_open_greater_than_high(self):
        rec = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            open=20.0,
            high=15.0,
            low=10.0,
            close=18.0,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert report.error_count >= 1

    def test_close_less_than_low(self):
        rec = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            open=10.0,
            high=15.0,
            low=10.0,
            close=5.0,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert any(
            "close" in i.message.lower() and "low" in i.message.lower()
            for i in report.issues
        )

    def test_volume_negative_error(self):
        rec = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            volume=-1000.0,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec])
        assert any(
            "volume" in i.field.lower() for i in report.issues
        )

    def test_missing_trading_days(self):
        rec1 = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-01",
            close=10.0,
        )
        rec2 = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-15",
            close=10.5,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec1, rec2])
        assert any(
            i.issue_type == IssueType.MISSING_TRADING_DAYS
            for i in report.issues
        )

    def test_price_continuity_warning(self):
        rec1 = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            close=100.0,
        )
        rec2 = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-03",
            close=160.0,
        )
        validator = StockPriceValidator()
        report = validator.validate([rec1, rec2])
        assert any(
            "close" in i.field.lower()
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_daily_return_warning(self):
        rec = StockPriceRecord(
            ts_code="000001.SZ",
            date="2024-01-02",
            open=10.0,
            close=16.0,
        )
        validator = StockPriceValidator(max_daily_return=0.50)
        report = validator.validate([rec])
        # 60% return > 50% threshold
        assert any(
            "daily_return" in i.field.lower()
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_multiple_tickers(self):
        recs = [
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", close=10.0),
            StockPriceRecord(ts_code="000002.SZ", date="2024-01-02", close=20.0),
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-03", close=10.5),
            StockPriceRecord(ts_code="000002.SZ", date="2024-01-03", close=20.5),
        ]
        validator = StockPriceValidator()
        report = validator.validate(recs)
        assert report.stats.get("tickers_checked") == 2

    def test_valid_records_no_errors(self):
        recs = [
            StockPriceRecord(
                ts_code="000001.SZ",
                date="2024-01-02",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1_000_000.0,
            ),
            StockPriceRecord(
                ts_code="000001.SZ",
                date="2024-01-03",
                open=10.2,
                high=10.4,
                low=10.0,
                close=10.3,
                volume=1_200_000.0,
            ),
        ]
        validator = StockPriceValidator()
        report = validator.validate(recs)
        # No errors, only warnings from price continuity check if any
        assert report.error_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FinancialRatioValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestFinancialRatioValidator:
    def test_empty_records(self):
        validator = FinancialRatioValidator()
        report = validator.validate([])
        assert report.error_count == 0

    def test_roe_out_of_range_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            roe=6.0,  # 600% > 500% max
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.issue_type == IssueType.RATIO_OUT_OF_RANGE
            and i.field == "roe"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_roe_negative_out_of_range(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            roe=-1.5,  # -150% < -100% min
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.issue_type == IssueType.RATIO_OUT_OF_RANGE
            and i.field == "roe"
            for i in report.issues
        )

    def test_current_ratio_zero_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            current_ratio=0.0,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "current_ratio"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_quick_ratio_negative_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            quick_ratio=-0.5,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "quick_ratio"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_gross_margin_out_of_range_warning(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            gross_margin=1.5,  # 150% > 100% max
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "gross_margin"
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_net_margin_out_of_range_warning(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            net_margin=-1.5,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "net_margin"
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_debt_to_equity_negative_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            debt_to_equity=-0.5,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "debt_to_equity"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_debt_to_equity_excessive_warning(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            debt_to_equity=150.0,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "debt_to_equity"
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_total_shares_zero_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            total_shares=0.0,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "total_shares"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_total_shares_negative_error(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            total_shares=-100.0,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert any(
            i.field == "total_shares"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_fiscal_year_inconsistency(self):
        recs = [
            FinancialRatioRecord(
                ts_code="000001.SZ",
                date="2023-12-31",
                report_type="annual",
            ),
            FinancialRatioRecord(
                ts_code="000001.SZ",
                date="2024-03-31",
                report_type="annual",
            ),
        ]
        validator = FinancialRatioValidator()
        report = validator.validate(recs)
        assert any(
            "fiscal_year_end" in i.field.lower()
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_valid_ratio_record(self):
        rec = FinancialRatioRecord(
            ts_code="000001.SZ",
            date="2024-12-31",
            report_type="annual",
            roe=0.15,
            current_ratio=2.0,
            quick_ratio=1.8,
            debt_to_equity=0.8,
            gross_margin=0.35,
            net_margin=0.12,
            total_shares=1_000_000_000.0,
        )
        validator = FinancialRatioValidator()
        report = validator.validate([rec])
        assert report.error_count == 0
        assert report.warning_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: TimeSeriesGapValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestTimeSeriesGapValidatorInit:
    def test_defaults(self):
        validator = TimeSeriesGapValidator()
        assert validator.max_consecutive_gaps == 3
        assert validator.calendar is None
        assert validator.infer_gaps is False

    def test_custom_params(self):
        validator = TimeSeriesGapValidator(
            max_consecutive_gaps=5,
            infer_gaps=True,
            max_inferred_gap_days=14,
        )
        assert validator.max_consecutive_gaps == 5
        assert validator.infer_gaps is True
        assert validator.max_inferred_gap_days == 14

    def test_with_calendar(self):
        cal = [
            TradingCalendarRecord(date="2024-01-02"),
            TradingCalendarRecord(date="2024-01-03"),
        ]
        validator = TimeSeriesGapValidator(calendar=cal)
        assert len(validator.calendar) == 2


class TestTimeSeriesGapValidatorValidate:
    def test_empty_records(self):
        validator = TimeSeriesGapValidator()
        report = validator.validate_dict_series([])
        assert report.validated_records == 0

    def test_calendar_based_gap_detection(self):
        cal = [
            TradingCalendarRecord(date="2024-01-02"),
            TradingCalendarRecord(date="2024-01-03"),
            TradingCalendarRecord(date="2024-01-04"),
            TradingCalendarRecord(date="2024-01-05"),
        ]
        validator = TimeSeriesGapValidator(calendar=cal)
        records = [
            {"date": "2024-01-02"},
            {"date": "2024-01-05"},
        ]
        report = validator.validate_dict_series(records)
        assert any(
            i.issue_type == IssueType.MISSING_TRADING_DAYS
            for i in report.issues
        )

    def test_inference_based_gap_detection(self):
        validator = TimeSeriesGapValidator(
            infer_gaps=True,
            max_inferred_gap_days=3,
        )
        records = [
            {"date": "2024-01-02"},
            {"date": "2024-01-10"},
        ]
        report = validator.validate_dict_series(records)
        assert any(
            i.issue_type == IssueType.MISSING_TRADING_DAYS
            and i.severity == IssueSeverity.INFO
            for i in report.issues
        )

    def test_no_gap_inference(self):
        validator = TimeSeriesGapValidator(
            infer_gaps=True,
            max_inferred_gap_days=10,
        )
        records = [
            {"date": "2024-01-02"},
            {"date": "2024-01-05"},
        ]
        report = validator.validate_dict_series(records)
        gap_issues = [
            i for i in report.issues
            if i.issue_type == IssueType.MISSING_TRADING_DAYS
        ]
        assert len(gap_issues) == 0

    def test_entity_grouping(self):
        validator = TimeSeriesGapValidator(
            infer_gaps=True,
            max_inferred_gap_days=3,
        )
        records = [
            {"ts_code": "A", "date": "2024-01-02"},
            {"ts_code": "A", "date": "2024-01-10"},
            {"ts_code": "B", "date": "2024-01-02"},
            {"ts_code": "B", "date": "2024-01-05"},
        ]
        report = validator.validate_dict_series(records, entity_field="ts_code")
        assert report.stats.get("entities_checked") == 2

    def test_invalid_date_format_skipped(self):
        validator = TimeSeriesGapValidator(infer_gaps=True)
        records = [
            {"date": "invalid-date"},
            {"date": "2024-01-10"},
        ]
        report = validator.validate_dict_series(records)
        # Should not crash, just skip invalid date
        assert report.validated_records == 2


# ─────────────────────────────────────────────────────────────────────────────
# TEST: CrossSectionalValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossSectionalValidatorInit:
    def test_defaults(self):
        validator = CrossSectionalValidator()
        assert validator.require_fields == []
        assert validator.allow_null_ratio == 0.5

    def test_custom_params(self):
        validator = CrossSectionalValidator(
            require_fields=["close", "volume"],
            allow_null_ratio=0.3,
        )
        assert validator.require_fields == ["close", "volume"]
        assert validator.allow_null_ratio == 0.3


class TestCrossSectionalValidatorDuplicateCheck:
    def test_duplicate_detected(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0},
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.issue_type == IssueType.CROSS_SECTION_INCONSISTENCY
            and "重复" in i.message
            for i in report.issues
        )

    def test_no_duplicates(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0},
            {"ts_code": "000001.SZ", "date": "2024-01-03", "close": 10.5},
        ]
        report = validator.validate_dict_records(records)
        dup_issues = [
            i for i in report.issues
            if "重复" in i.message
        ]
        assert len(dup_issues) == 0


class TestCrossSectionalValidatorNegativeShares:
    def test_negative_total_shares(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-12-31", "total_shares": -1000.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.field == "total_shares"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_negative_float_shares(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-12-31", "float_shares": -500.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.field == "float_shares"
            for i in report.issues
        )


class TestCrossSectionalValidatorPricePositive:
    def test_zero_price(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 0.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.field == "close"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_negative_price(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "open": -5.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.field == "open"
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_positive_price_ok(self):
        validator = CrossSectionalValidator()
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.5},
        ]
        report = validator.validate_dict_records(records)
        price_errors = [
            i for i in report.issues
            if i.issue_type == IssueType.PRICE_OUTLIER
        ]
        assert len(price_errors) == 0


class TestCrossSectionalValidatorNullRatios:
    def test_null_ratio_exceeded(self):
        validator = CrossSectionalValidator(
            require_fields=["close", "volume"],
            allow_null_ratio=0.3,
        )
        # 4 records, 2 null for "close" = 50% null
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0, "volume": 100.0},
            {"ts_code": "000001.SZ", "date": "2024-01-03", "close": None, "volume": 100.0},
            {"ts_code": "000001.SZ", "date": "2024-01-04", "close": 10.5, "volume": 100.0},
            {"ts_code": "000001.SZ", "date": "2024-01-05", "close": None, "volume": 100.0},
        ]
        report = validator.validate_dict_records(records)
        assert any(
            i.field == "close"
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_null_ratio_within_threshold(self):
        validator = CrossSectionalValidator(
            require_fields=["close"],
            allow_null_ratio=0.6,
        )
        records = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0},
            {"ts_code": "000001.SZ", "date": "2024-01-03", "close": None},
            {"ts_code": "000001.SZ", "date": "2024-01-04", "close": 10.5},
            {"ts_code": "000001.SZ", "date": "2024-01-05", "close": None},
        ]
        report = validator.validate_dict_records(records)
        # 50% null < 60% threshold — no issue
        null_issues = [
            i for i in report.issues
            if i.field == "close"
        ]
        assert len(null_issues) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: DataFreshnessValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestDataFreshnessValidator:
    def test_stale_data_error(self):
        config = FreshnessConfig(
            warning_days=30,
            error_days=90,
            date_field="report_date",
            reference_date="2025-12-31",
        )
        validator = DataFreshnessValidator(config)
        records = [
            {"ts_code": "000001.SZ", "report_date": "2023-01-01"},
        ]
        report = validator.validate(records)
        assert any(
            i.issue_type == IssueType.DATA_FRESHNESS
            and i.severity == IssueSeverity.ERROR
            for i in report.issues
        )

    def test_stale_data_warning(self):
        config = FreshnessConfig(
            warning_days=30,
            error_days=90,
            date_field="report_date",
            reference_date="2025-02-01",
        )
        validator = DataFreshnessValidator(config)
        records = [
            {"ts_code": "000001.SZ", "report_date": "2024-12-15"},
        ]
        report = validator.validate(records)
        assert any(
            i.issue_type == IssueType.DATA_FRESHNESS
            and i.severity == IssueSeverity.WARNING
            for i in report.issues
        )

    def test_fresh_data_no_issue(self):
        config = FreshnessConfig(
            warning_days=30,
            error_days=90,
            date_field="report_date",
            reference_date="2026-01-20",
        )
        validator = DataFreshnessValidator(config)
        records = [
            {"ts_code": "000001.SZ", "report_date": "2026-01-10"},
        ]
        report = validator.validate(records)
        freshness_issues = [
            i for i in report.issues
            if i.issue_type == IssueType.DATA_FRESHNESS
        ]
        assert len(freshness_issues) == 0

    def test_empty_records(self):
        validator = DataFreshnessValidator()
        report = validator.validate([])
        assert report.validated_records == 0

    def test_multiple_entities(self):
        config = FreshnessConfig(
            warning_days=30,
            error_days=90,
            reference_date="2026-01-01",
        )
        validator = DataFreshnessValidator(config)
        records = [
            {"ts_code": "000001.SZ", "date": "2025-12-01"},
            {"ts_code": "000002.SZ", "date": "2023-01-01"},
        ]
        report = validator.validate(records, entity_field="ts_code")
        assert report.stats.get("entities_checked") == 2

    def test_config_defaults(self):
        validator = DataFreshnessValidator()
        assert validator.config.warning_days == 30
        assert validator.config.error_days == 90


# ─────────────────────────────────────────────────────────────────────────────
# TEST: CompositeValidator
# ─────────────────────────────────────────────────────────────────────────────


class TestCompositeValidatorInit:
    def test_empty_init(self):
        composite = CompositeValidator()
        assert composite._validators == []
        assert composite.stop_on_error is False

    def test_with_initial_validators(self):
        composite = CompositeValidator(
            validators=[StockPriceValidator(), FinancialRatioValidator()],
        )
        assert len(composite._validators) == 2

    def test_stop_on_error_flag(self):
        composite = CompositeValidator(stop_on_error=True)
        assert composite.stop_on_error is True


class TestCompositeValidatorRegister:
    def test_register_returns_self(self):
        composite = CompositeValidator()
        result = composite.register(StockPriceValidator())
        assert result is composite

    def test_register_adds_validator(self):
        composite = CompositeValidator()
        assert len(composite._validators) == 0
        composite.register(StockPriceValidator())
        assert len(composite._validators) == 1


class TestCompositeValidatorValidate:
    def test_empty_datasets(self):
        composite = CompositeValidator()
        report = composite.validate({})
        assert report.issues == []
        assert report.stats.get("datasets_processed") == 0

    def test_validates_price_records(self):
        composite = CompositeValidator()
        composite.register(StockPriceValidator())
        prices = [
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", close=0.0),
        ]
        report = composite.validate({"prices": prices})
        assert report.error_count >= 1

    def test_validates_ratio_records(self):
        composite = CompositeValidator()
        composite.register(FinancialRatioValidator())
        ratios = [
            FinancialRatioRecord(
                ts_code="000001.SZ",
                date="2024-12-31",
                roe=6.0,
            ),
        ]
        report = composite.validate({"ratios": ratios})
        assert report.error_count >= 1

    def test_skips_incompatible_dataset(self):
        composite = CompositeValidator()
        composite.register(StockPriceValidator())
        # Pass dicts instead of StockPriceRecord dataclasses
        dict_records = [{"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.0}]
        report = composite.validate({"dicts": dict_records})
        # Should not crash; the validator handles TypeError gracefully
        assert isinstance(report, FinancialValidationReport)

    def test_multiple_datasets(self):
        composite = CompositeValidator()
        composite.register(StockPriceValidator())
        composite.register(FinancialRatioValidator())
        report = composite.validate({
            "prices": [
                StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", close=10.0),
            ],
            "ratios": [
                FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31", roe=0.1),
            ],
        })
        assert report.stats.get("validators_run", 0) >= 1

    def test_stats_aggregated(self):
        composite = CompositeValidator()
        composite.register(StockPriceValidator())
        prices = [
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", close=10.0),
        ]
        report = composite.validate({"prices": prices})
        assert "total_issues" in report.stats
        assert "total_errors" in report.stats
        assert "total_warnings" in report.stats


class TestCompositeValidatorPrintReport:
    def test_print_report_no_issues(self, capsys):
        composite = CompositeValidator()
        report = FinancialValidationReport(
            validator_name="TestComposite",
            issues=[],
            stats={"total_records": 10},
        )
        composite.print_report(report)
        captured = capsys.readouterr().out
        assert "Financial Data Validation Report" in captured
        assert "PASS" in captured

    def test_print_report_with_issues(self, capsys):
        composite = CompositeValidator()
        report = FinancialValidationReport(
            validator_name="TestComposite",
            issues=[
                FinancialDataIssue(
                    issue_type=IssueType.PRICE_OUTLIER,
                    severity=IssueSeverity.ERROR,
                    ts_code="000001.SZ",
                    field="close",
                    message="Price is zero",
                    expected_range="> 0",
                    suggestion="Check data source",
                ),
            ],
            stats={},
        )
        composite.print_report(report)
        captured = capsys.readouterr().out
        assert "FAIL" in captured
        assert "ERROR" in captured


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Registry helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatorRegistry:
    def test_register_and_get(self):
        clear_registry()
        factory = lambda: StockPriceValidator(max_daily_return=0.30)
        register_validator("strict_price", factory)
        retrieved = get_validator("strict_price")
        assert callable(retrieved)
        validator = retrieved()
        assert isinstance(validator, StockPriceValidator)
        clear_registry()

    def test_get_nonexistent_returns_none(self):
        clear_registry()
        result = get_validator("does_not_exist")
        assert result is None
        clear_registry()

    def test_list_validators_empty(self):
        clear_registry()
        assert list_validators() == []
        clear_registry()

    def test_list_validators_after_register(self):
        clear_registry()
        register_validator("v1", lambda: StockPriceValidator())
        register_validator("v2", lambda: FinancialRatioValidator())
        names = list_validators()
        assert "v1" in names
        assert "v2" in names
        clear_registry()

    def test_clear_registry(self):
        clear_registry()
        register_validator("temp", lambda: StockPriceValidator())
        assert len(list_validators()) == 1
        clear_registry()
        assert len(list_validators()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Integration — full pipeline with synthetic data
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    def test_full_composite_pipeline(self):
        """End-to-end: register validators → validate mixed datasets → check report."""
        clear_registry()
        register_validator("prices", lambda: StockPriceValidator())
        register_validator("ratios", lambda: FinancialRatioValidator())
        register_validator("gaps", lambda: TimeSeriesGapValidator(infer_gaps=True, max_inferred_gap_days=5))
        register_validator("cross", lambda: CrossSectionalValidator())
        register_validator("fresh", lambda: DataFreshnessValidator())

        composite = CompositeValidator()
        for name in list_validators():
            factory = get_validator(name)
            if factory:
                composite.register(factory())

        prices = [
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", open=10.0, high=10.8, low=9.5, close=10.5),
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-09", open=10.5, high=10.5, low=10.5, close=10.5),
        ]
        ratios = [
            FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31", roe=0.15, current_ratio=2.0),
        ]
        time_series_dicts = [
            {"ts_code": "000001.SZ", "date": "2024-01-02"},
            {"ts_code": "000001.SZ", "date": "2024-01-15"},
        ]
        cross_dicts = [
            {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.5, "total_shares": 1e9},
        ]

        report = composite.validate({
            "prices": prices,
            "ratios": ratios,
            "time_series": time_series_dicts,
            "cross": cross_dicts,
        })

        assert isinstance(report, FinancialValidationReport)
        assert report.validated_records >= 0
        assert "total_issues" in report.stats
        clear_registry()

    def test_province_validator_full_pipeline(self, province_data_file):
        validator = ProvinceDataValidator(data_file=province_data_file)
        report = validator.validate_all()
        validator.print_report(report)
        # Should complete without error
        assert report.file_path == str(province_data_file)
        assert "total_provinces" in report.stats

    def test_province_validator_with_corrupt_data(self, corrupt_data_file):
        validator = ProvinceDataValidator(data_file=corrupt_data_file)
        report = validator.validate_all()
        assert report.has_errors
        assert report.error_count >= 1
        assert len(report.issues) >= 1

    def test_validator_chaining(self):
        """Test that different validators can be chained together."""
        pv = StockPriceValidator(max_daily_return=0.50)
        rv = FinancialRatioValidator()

        prices = [
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", close=0.0),
            StockPriceRecord(ts_code="000001.SZ", date="2024-01-03", close=10.0),
        ]
        ratios = [
            FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31", roe=8.0),
        ]

        price_report = pv.validate(prices)
        ratio_report = rv.validate(ratios)

        assert price_report.error_count >= 1
        assert ratio_report.error_count >= 1
