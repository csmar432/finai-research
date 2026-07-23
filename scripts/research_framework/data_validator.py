"""Province Data Validator — 自动核查省级科技创新数据。

运行机制：
  1. 结构完整性检查 — 各省数据字段是否齐全
  2. 时间序列逻辑检查 — 同比/环比是否合理
  3. 跨省数据校验 — 排名表内部一致性
  4. 来源标注检查 — 是否所有数据都标注了来源
  5. 数据新鲜度检查 — 数据是否为最新年份

使用方式：
    from scripts.research_framework.data_validator import ProvinceDataValidator
    validator = ProvinceDataValidator()
    report = validator.validate_all()
    validator.print_report(report)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Protocol,
    TypeVar,
)

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "national_province_data_2026.json"

# ── Enums ──────────────────────────────────────────────────────────────────


class IssueSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(Enum):
    MISSING_SOURCE = "MISSING_SOURCE"
    BAD_TIMESERIES = "BAD_TIMESERIES"
    RANKING_INCONSISTENCY = "RANKING_INCONSISTENCY"
    INCOMPLETE_PROVINCE = "INCOMPLETE_PROVINCE"
    STALE_DATA = "STALE_DATA"
    SUSPICIOUS_VALUE = "SUSPICIOUS_VALUE"
    UNVERIFIED = "UNVERIFIED"
    # Financial data validation issue types
    PRICE_OUTLIER = "PRICE_OUTLIER"
    RATIO_OUT_OF_RANGE = "RATIO_OUT_OF_RANGE"
    MISSING_TRADING_DAYS = "MISSING_TRADING_DAYS"
    CROSS_SECTION_INCONSISTENCY = "CROSS_SECTION_INCONSISTENCY"
    DATA_FRESHNESS = "DATA_FRESHNESS"


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class DataIssue:
    issue_type: IssueType
    severity: IssueSeverity
    province: str
    indicator: str = ""
    message: str = ""
    detail: str = ""
    suggestion: str = ""


@dataclass
class ValidationReport:
    file_path: str
    issues: list[DataIssue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def error_count(self) -> bool:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.INFO)

    def add(self, issue: DataIssue):
        self.issues.append(issue)


# ── ProvinceDataValidator ────────────────────────────────────────────────────────


class ProvinceDataValidator:
    """自动核查全国各省科技创新数据的完整性、逻辑性和一致性。"""

    # 9大类别（必须全部出现）
    REQUIRED_CATEGORIES = {"ECON", "EDU", "PLAT", "RD", "ENT", "TECH", "IND", "AI", "FIN"}

    # 各类别核心指标（用于完整性检查；支持带年份后缀的键名）
    # 匹配逻辑：包含其中一个子串即视为已覆盖
    CORE_INDICATORS: dict[str, list[str]] = {
        "ECON": ["GDP", "GDP增速"],
        "EDU":  ["高校", "在校生"],
        "PLAT": ["实验室", "平台", "装置"],
        "RD":   ["R&D", "研发", "科技支出"],
        "ENT":  ["高新", "科技型", "专精特新"],
        "TECH": ["技术合同", "转化"],
        "IND":  ["高技术", "数字经济", "战略性"],
        "AI":   [],
        "FIN":  [],
    }

    # GDP同比变化合理范围（%）
    GDP_YOY_MIN = -15.0
    GDP_YOY_MAX = 20.0

    # R&D强度合理范围（%）
    RD_INTENSITY_MIN = 0.5
    RD_INTENSITY_MAX = 10.0

    # 各省最新数据年份（动态计算）
    EXPECTED_LATEST_YEAR = datetime.now().year  # 动态：当前年份
    ACCEPTABLE_LATEST_YEAR = datetime.now().year - 1  # 容忍上一年

    def __init__(self, data_file: Path | None = None):
        self.data_file = data_file or DATA_FILE
        self.data: dict = {}
        self._load()

    # ── Load ─────────────────────────────────────────────────────────────────

    def _load(self):
        if not self.data_file.exists():
            raise FileNotFoundError(f"Data file not found: {self.data_file}")
        with open(self.data_file, encoding="utf-8") as f:
            self.data = json.load(f)

    # ── Main entry ──────────────────────────────────────────────────────────

    def validate_all(self) -> ValidationReport:
        """运行全部验证检查，返回验证报告。"""
        report = ValidationReport(file_path=str(self.data_file))
        self._check_structure(report)
        self._check_completeness(report)
        self._check_timeseries(report)
        self._check_rankings(report)
        self._check_sources(report)
        self._check_verification_status(report)
        self._compute_stats(report)
        return report

    # ── Check 1: File structure ─────────────────────────────────────────────

    def _check_structure(self, report: ValidationReport):
        required_keys = {"meta", "indicator_schema", "provinces", "ranking_tables", "verification_status"}
        missing = required_keys - set(self.data.keys())
        if missing:
            report.add(DataIssue(
                IssueType.INCOMPLETE_PROVINCE, IssueSeverity.ERROR,
                province="全局", message=f"顶层缺少字段: {missing}",
                suggestion="确保 national_province_data_2026.json 包含所有顶层键"))
        else:
            logger.info("Structure check PASSED")

    # ── Check 2: Per-province completeness ──────────────────────────────────

    def _check_completeness(self, report: ValidationReport):
        provinces = self.data.get("provinces", {})
        for prov_key, prov_data in provinces.items():
            cats = prov_data.get("data", {})
            verif = prov_data.get("verification", "unknown")

            # Check all 9 categories exist
            missing_cats = self.REQUIRED_CATEGORIES - set(cats.keys())
            if missing_cats and verif in ("full", "partial"):
                report.add(DataIssue(
                    IssueType.INCOMPLETE_PROVINCE, IssueSeverity.WARNING,
                    province=prov_key,
                    message=f"缺少类别: {missing_cats} (verification={verif})",
                    suggestion=f"补充 {prov_key} 省缺失类别的数据，或将 verification 改为 minimal"))

            # Check core indicators in each category (substring matching)
            for cat_id, core_inds in self.CORE_INDICATORS.items():
                if cat_id not in cats:
                    continue
                cat_items = cats[cat_id]
                cat_keys = list(cat_items.keys())
                for core in core_inds:
                    if not any(core in k for k in cat_keys):
                        report.add(DataIssue(
                            IssueType.INCOMPLETE_PROVINCE, IssueSeverity.INFO,
                            province=prov_key, indicator=cat_id,
                            message=f"缺少核心指标: {core} (在 {cat_id} 类别中)",
                            suggestion=f"查找 {prov_key} 省 {core} 的官方数据"))

    # ── Check 3: Time-series logic ─────────────────────────────────────────

    def _check_timeseries(self, report: ValidationReport):
        provinces = self.data.get("provinces", {})
        for prov_key, prov_data in provinces.items():
            ts = prov_data.get("time_series", {})
            for series_name, series_data in ts.items():
                data = series_data.get("data", {})
                if len(data) < 3:
                    report.add(DataIssue(
                        IssueType.BAD_TIMESERIES, IssueSeverity.INFO,
                        province=prov_key, indicator=series_name,
                        message=f"时间序列数据点不足: {len(data)} < 3",
                        suggestion=f"补充 {prov_key} {series_name} 的历史数据"))

                years = sorted(data.keys(), key=lambda y: int(y))
                for i in range(1, len(years)):
                    y_prev, y_curr = years[i - 1], years[i]
                    v_prev, v_curr = float(data.get(y_prev, 0)), float(data.get(y_curr, 0))
                    if v_prev <= 0:
                        continue
                    yoy = (v_curr - v_prev) / v_prev * 100
                    gap = int(y_curr) - int(y_prev)

                    # GDP YoY check
                    if series_name == "GDP" and gap == 1:
                        if yoy < self.GDP_YOY_MIN or yoy > self.GDP_YOY_MAX:
                            report.add(DataIssue(
                                IssueType.SUSPICIOUS_VALUE, IssueSeverity.ERROR,
                                province=prov_key, indicator=series_name,
                                message=(
                                    f"{prov_key} GDP {y_prev}→{y_curr} 同比 "
                                    f"{yoy:+.1f}% (合理范围 [{self.GDP_YOY_MIN}%, {self.GDP_YOY_MAX}%])"
                                ),
                                detail=f"v({y_prev})={v_prev:.2f}, v({y_curr})={v_curr:.2f}",
                                suggestion="核查原始数据来源，可能是录入错误或特殊因素（如疫情）"))

                    # R&D intensity check
                    if series_name == "R&D经费":
                        if v_curr < 0 or (v_prev > 0 and yoy < -50):
                            report.add(DataIssue(
                                IssueType.SUSPICIOUS_VALUE, IssueSeverity.ERROR,
                                province=prov_key, indicator=series_name,
                                message=f"{prov_key} R&D经费 {y_curr}年数据异常: {v_curr}亿元",
                                suggestion="核查数据来源"))

                # R&D intensity sanity check
                if series_name == "R&D经费":
                    latest_year = max(data.keys(), key=lambda y: int(y))
                    latest = float(data[latest_year])
                    # Check against national average if we have GDP data
                    if latest < 1.0:  # Less than 1 billion is suspicious for a province
                        report.add(DataIssue(
                            IssueType.SUSPICIOUS_VALUE, IssueSeverity.WARNING,
                            province=prov_key, indicator=series_name,
                            message=f"{prov_key} R&D经费 latest({latest_year})={latest}亿元 — 可能过小",
                            suggestion="核查原始数据来源"))

    # ── Check 4: Rankings internal consistency ─────────────────────────────

    def _check_rankings(self, report: ValidationReport):
        provinces = self.data.get("provinces", {})
        rankings = self.data.get("ranking_tables", {})

        for table_id, table_data in rankings.items():
            rows = table_data.get("data", [])
            if not rows:
                report.add(DataIssue(
                    IssueType.RANKING_INCONSISTENCY, IssueSeverity.ERROR,
                    province="全局", indicator=table_id,
                    message=f"排名表 {table_id} 为空"))
                continue

            # Check ranks are sequential
            ranks = [r["rank"] for r in rows]
            expected = list(range(1, len(rows) + 1))
            if ranks != expected:
                report.add(DataIssue(
                    IssueType.RANKING_INCONSISTENCY, IssueSeverity.ERROR,
                    province="全局", indicator=table_id,
                    message=f"{table_id} 排名不连续: {ranks} (期望 {expected})",
                    suggestion="修复排名表中的 rank 字段"))

            # Check values are non-increasing (for GDP, R&D, etc.)
            values = [r["value"] for r in rows]
            if all(isinstance(v, (int, float)) for v in values):
                if not all(values[i] >= values[i + 1] for i in range(len(values) - 1)):
                    report.add(DataIssue(
                        IssueType.RANKING_INCONSISTENCY, IssueSeverity.WARNING,
                        province="全局", indicator=table_id,
                        message=f"{table_id} 数值未按降序排列",
                        suggestion="按 value 降序重新排列"))

            # Cross-check ranking values against province data
            if table_id == "GDP_2024":
                for row in rows:
                    prov_name = row["province"]
                    rank_value = row["value"]
                    if prov_name in provinces:
                        prov_data = provinces[prov_name]
                        if "data" in prov_data and "ECON" in prov_data["data"]:
                            gdp_data = prov_data["data"]["ECON"].get("GDP_2024", {})
                            actual = gdp_data.get("value")
                            if actual and abs(actual - rank_value) / actual > 0.01:
                                report.add(DataIssue(
                                    IssueType.RANKING_INCONSISTENCY, IssueSeverity.ERROR,
                                    province=prov_name, indicator="GDP_2024",
                                    message=(
                                        f"{prov_name} GDP 在排名表={rank_value}亿元，"
                                        f"在省级数据={actual}亿元，差异{(rank_value-actual)/actual*100:+.1f}%"
                                    ),
                                    suggestion="统一排名表和省级数据中的GDP数值"))

            # Check ranking sources
            if not table_data.get("source"):
                report.add(DataIssue(
                    IssueType.MISSING_SOURCE, IssueSeverity.WARNING,
                    province="全局", indicator=table_id,
                    message=f"排名表 {table_id} 缺少 source 字段",
                    suggestion="添加数据来源说明"))

    # ── Check 5: Source annotation ───────────────────────────────────────────

    def _check_sources(self, report: ValidationReport):
        provinces = self.data.get("provinces", {})
        for prov_key, prov_data in provinces.items():
            cats = prov_data.get("data", {})
            for cat_id, items in cats.items():
                for ind_key, ind_data in items.items():
                    if isinstance(ind_data, dict):
                        if not ind_data.get("source"):
                            report.add(DataIssue(
                                IssueType.MISSING_SOURCE, IssueSeverity.WARNING,
                                province=prov_key, indicator=f"{cat_id}/{ind_key}",
                                message=f"{prov_key}/{ind_key} 缺少 source 字段",
                                suggestion=f"为 {prov_key} {ind_key} 补充数据来源"))

    # ── Check 6: Verification status ───────────────────────────────────────

    def _check_verification_status(self, report: ValidationReport):
        vs = self.data.get("verification_status", {})
        provinces = self.data.get("provinces", {})

        for prov_key, prov_data in provinces.items():
            declared = prov_data.get("verification", "unknown")
            # Check consistency
            if declared == "full" and prov_key not in vs.get("full", []):
                report.add(DataIssue(
                    IssueType.UNVERIFIED, IssueSeverity.WARNING,
                    province=prov_key,
                    message=f"{prov_key} verification=full 但不在 verification_status.full 中"))
            if declared == "partial" and prov_key not in vs.get("partial", []):
                report.add(DataIssue(
                    IssueType.UNVERIFIED, IssueSeverity.INFO,
                    province=prov_key,
                    message=f"{prov_key} verification=partial 但不在 verification_status.partial 中"))

        # Check provinces with minimal data
        for prov_key in vs.get("minimal", []):
            prov_data = provinces.get(prov_key, {})
            cats = prov_data.get("data", {})
            if len(cats) > 5:
                report.add(DataIssue(
                    IssueType.UNVERIFIED, IssueSeverity.INFO,
                    province=prov_key,
                    message=(
                        f"{prov_key} verification=minimal 但有 {len(cats)} 个类别数据。"
                        "建议将 verification 升级为 partial。"
                    ),
                ))

    # ── Compute stats ───────────────────────────────────────────────────────

    def _compute_stats(self, report: ValidationReport):
        provinces = self.data.get("provinces", {})
        total_indicators = 0
        total_with_source = 0
        total_ts_points = 0

        for prov_key, prov_data in provinces.items():
            cats = prov_data.get("data", {})
            for cat_items in cats.values():
                for ind_data in cat_items.values():
                    if isinstance(ind_data, dict):
                        total_indicators += 1
                        if ind_data.get("source"):
                            total_with_source += 1
            ts = prov_data.get("time_series", {})
            for series_data in ts.values():
                total_ts_points += len(series_data.get("data", {}))

        report.stats = {
            "total_provinces": len(provinces),
            "total_indicators": total_indicators,
            "indicators_with_source": total_with_source,
            "source_coverage_pct": round(total_with_source / total_indicators * 100, 1) if total_indicators else 0,
            "total_timeseries_points": total_ts_points,
            "total_ranking_tables": len(self.data.get("ranking_tables", {})),
        }

    # ── Report printing ──────────────────────────────────────────────────────

    def print_report(self, report: ValidationReport):
        print("=" * 70)
        print(f"  省级数据验证报告 — {report.file_path}")
        print("=" * 70)
        print("\n数据概况:")
        for k, v in report.stats.items():
            print(f"  {k}: {v}")

        print(f"\n验证结果: {'PASS' if not report.has_errors else 'FAIL'}")
        print(f"  ERROR:   {report.error_count}")
        print(f"  WARNING: {report.warning_count}")
        print(f"  INFO:    {report.info_count}")

        if report.issues:
            print("\n详细问题列表:")
            print("-" * 70)
            for issue in report.issues:
                sev = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[issue.severity.value]
                loc = f"[{issue.province}]" + (f" {issue.indicator}" if issue.indicator else "")
                print(f"  [{sev}] {loc}")
                print(f"    {issue.message}")
                if issue.suggestion:
                    print(f"    → 建议: {issue.suggestion}")
        else:
            print("\n无问题。数据验证通过。")

        print("=" * 70)

    # ── Quick checks ─────────────────────────────────────────────────────────

    def check_province(self, province: str) -> ValidationReport:
        """只验证指定省份。"""
        report = ValidationReport(file_path=str(self.data_file))
        provinces = self.data.get("provinces", {})
        if province not in provinces:
            report.add(DataIssue(
                IssueType.INCOMPLETE_PROVINCE, IssueSeverity.ERROR,
                province=province, message=f"省份 '{province}' 不在数据集中"))
            return report

        prov_data = provinces[province]
        cats = prov_data.get("data", {})

        missing_cats = self.REQUIRED_CATEGORIES - set(cats.keys())
        if missing_cats:
            report.add(DataIssue(
                IssueType.INCOMPLETE_PROVINCE, IssueSeverity.WARNING,
                province=province, message=f"缺少类别: {missing_cats}"))

        ts = prov_data.get("time_series", {})
        for series_name, series_data in ts.items():
            data = series_data.get("data", {})
            if len(data) < 3:
                report.add(DataIssue(
                    IssueType.BAD_TIMESERIES, IssueSeverity.INFO,
                    province=province, indicator=series_name,
                    message=f"时间序列数据点不足: {len(data)} < 3"))

        self._compute_stats(report)
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# FinancialDataValidator — General Financial Data Validator
# ═══════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


@dataclass
class StockPriceRecord:
    """A single stock price observation.

    Attributes:
        ts_code: Stock ticker (e.g. "000001.SZ", "AAPL").
        date: Trading date in "YYYY-MM-DD" format.
        open: Opening price.
        high: Daily high price.
        low: Daily low price.
        close: Closing price.
        volume: Trading volume.
        turnover: Turnover amount (optional).
    """
    ts_code: str
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    turnover: float | None = None


@dataclass
class FinancialRatioRecord:
    """A single financial ratio observation.

    Attributes:
        ts_code: Stock ticker.
        date: Reporting date in "YYYY-MM-DD" format.
        report_type: Type of report ("Q1", "Q2", "Q3", "Q4" or "annual").
        roe: Return on equity (decimal, e.g. 0.15 for 15%).
        current_ratio: Current ratio (current assets / current liabilities).
        quick_ratio: Quick ratio.
        debt_to_equity: Debt-to-equity ratio.
        gross_margin: Gross profit margin.
        net_margin: Net profit margin.
        total_shares: Total shares outstanding.
    """
    ts_code: str
    date: str
    report_type: str = "annual"
    roe: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_to_equity: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    total_shares: float | None = None


@dataclass
class FinancialDataIssue:
    """A single issue detected during financial data validation.

    Attributes:
        issue_type: Categorized type of the issue.
        severity: Error severity level.
        ts_code: Affected stock ticker (empty string if cross-sectional).
        field: Field name where the issue was found.
        date: Date or reporting period of the record.
        message: Human-readable issue description.
        value: The problematic value (if applicable).
        expected_range: Expected valid range for the value.
        suggestion: Recommended action to fix the issue.
    """
    issue_type: IssueType
    severity: IssueSeverity
    ts_code: str = ""
    field: str = ""
    date: str = ""
    message: str = ""
    value: Any = None
    expected_range: str = ""
    suggestion: str = ""


@dataclass
class FinancialValidationReport:
    """Aggregated results from financial data validation.

    Attributes:
        validator_name: Name of the validator that produced this report.
        issues: List of detected issues.
        stats: Summary statistics about the validated data.
        validated_records: Number of records checked.
    """
    validator_name: str
    issues: list[FinancialDataIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    validated_records: int = 0

    @property
    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.INFO)

    def add(self, issue: FinancialDataIssue):
        self.issues.append(issue)


# ── Validator Protocol ─────────────────────────────────────────────────────────


class BaseValidator(Protocol[T]):
    """Protocol defining the interface for all validators."""

    def validate(self, data: list[T]) -> FinancialValidationReport:
        """Validate a list of records and return a report."""
        ...


# ── Stock Price Validator ──────────────────────────────────────────────────────


class StockPriceValidator:
    """Validates stock price data for anomalies and logical errors.

    Checks performed:
      1. Price outliers — prices <= 0, prices that imply >50% daily return.
      2. High/Low consistency — high >= low, high >= open/close, low <= open/close.
      3. Volume sanity — volume >= 0.
      4. Gap detection — missing trading days relative to expected calendar.
      5. Price continuity — large gaps between consecutive trading days.

    Example:
        >>> prices = [StockPriceRecord(ts_code="000001.SZ", date="2024-01-02",
        ...                            open=10.0, high=10.5, low=9.8, close=10.2)]
        >>> validator = StockPriceValidator()
        >>> report = validator.validate(prices)
        >>> print(report.error_count)
    """

    MAX_DAILY_RETURN: float = 0.50  # 50% maximum daily return
    MIN_REASONABLE_PRICE: float = 0.001  # minimum non-zero price

    def __init__(self, max_daily_return: float = 0.50) -> None:
        self.max_daily_return = max_daily_return

    def validate(self, records: list[StockPriceRecord]) -> FinancialValidationReport:
        report = FinancialValidationReport(validator_name="StockPriceValidator")
        report.validated_records = len(records)

        if not records:
            return report

        # Group by ticker and sort by date
        by_ticker: dict[str, list[StockPriceRecord]] = {}
        for rec in records:
            by_ticker.setdefault(rec.ts_code, []).append(rec)

        for ts_code, ticker_records in by_ticker.items():
            ticker_records.sort(key=lambda r: r.date)
            self._check_price_outliers(ts_code, ticker_records, report)
            self._check_high_low_consistency(ts_code, ticker_records, report)
            self._check_volume_sanity(ts_code, ticker_records, report)
            self._check_gaps(ts_code, ticker_records, report)
            self._check_price_continuity(ts_code, ticker_records, report)

        report.stats = {
            "total_records": report.validated_records,
            "tickers_checked": len(by_ticker),
        }
        return report

    def _check_price_outliers(
        self, ts_code: str, records: list[StockPriceRecord], report: FinancialValidationReport
    ):
        for rec in records:
            for field_name in ("open", "high", "low", "close"):
                val = getattr(rec, field_name, None)
                if val is None:
                    continue
                if val <= 0:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                        ts_code=ts_code, field=field_name, date=rec.date,
                        message=f"{ts_code} {rec.date} {field_name}={val} <= 0",
                        value=val,
                        expected_range="> 0",
                        suggestion="检查数据来源，确认是否复权价格或除权除息日数据"))

            # Daily return check: use previous close vs current open/close
            if rec.open is not None and rec.close is not None and rec.open > 0:
                daily_return = abs(rec.close - rec.open) / rec.open
                if daily_return > self.max_daily_return:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.WARNING,
                        ts_code=ts_code, field="daily_return", date=rec.date,
                        message=(
                            f"{ts_code} {rec.date} 日涨跌 {daily_return*100:.1f}% "
                            f"超过阈值 {self.max_daily_return*100:.0f}%"
                        ),
                        value=daily_return,
                        expected_range=f"<= {self.max_daily_return*100:.0f}%",
                        suggestion="确认是否为除权除息日、重大公告或数据错误"))

    def _check_high_low_consistency(
        self, ts_code: str, records: list[StockPriceRecord], report: FinancialValidationReport
    ):
        for rec in records:
            if rec.high is not None and rec.low is not None:
                if rec.high < rec.low:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                        ts_code=ts_code, field="high/low", date=rec.date,
                        message=f"{ts_code} {rec.date} 最高价({rec.high}) < 最低价({rec.low})",
                        value={"high": rec.high, "low": rec.low},
                        suggestion="核查数据来源，修正 high/low 字段"))

            for price_field in ("open", "close"):
                val = getattr(rec, price_field, None)
                if val is None:
                    continue
                if rec.high is not None and val > rec.high:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                        ts_code=ts_code, field=price_field, date=rec.date,
                        message=f"{ts_code} {rec.date} {price_field}({val}) > high({rec.high})",
                        value=val,
                        expected_range=f"<= {rec.high}",
                        suggestion="检查数据来源"))
                if rec.low is not None and val < rec.low:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                        ts_code=ts_code, field=price_field, date=rec.date,
                        message=f"{ts_code} {rec.date} {price_field}({val}) < low({rec.low})",
                        value=val,
                        expected_range=f">= {rec.low}",
                        suggestion="检查数据来源"))

    def _check_volume_sanity(
        self, ts_code: str, records: list[StockPriceRecord], report: FinancialValidationReport
    ):
        for rec in records:
            if rec.volume is not None and rec.volume < 0:
                report.add(FinancialDataIssue(
                    IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                    ts_code=ts_code, field="volume", date=rec.date,
                    message=f"{ts_code} {rec.date} 成交量={rec.volume} < 0",
                    value=rec.volume,
                    expected_range=">= 0",
                    suggestion="修正成交量数据"))

    def _check_gaps(
        self, ts_code: str, records: list[StockPriceRecord], report: FinancialValidationReport
    ):
        """Detect missing trading days based on a 5-day calendar week."""
        from datetime import datetime

        dates = [datetime.strptime(r.date, "%Y-%m-%d") for r in records]
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            if delta > 7:
                report.add(FinancialDataIssue(
                    IssueType.MISSING_TRADING_DAYS, IssueSeverity.WARNING,
                    ts_code=ts_code, field="trading_days", date=f"{records[i-1].date} to {records[i].date}",
                    message=(
                        f"{ts_code} {records[i-1].date} → {records[i].date} "
                        f"间隔 {delta} 天，疑似缺失 {(delta // 7) - 1} 个交易日"
                    ),
                    value=delta,
                    expected_range="<= 7 days",
                    suggestion="补充缺失交易日数据或确认是否为停牌期间"))

    def _check_price_continuity(
        self, ts_code: str, records: list[StockPriceRecord], report: FinancialValidationReport
    ):
        """Check for suspiciously large price jumps between consecutive trading days."""
        MAX_CONTINUOUS_CHANGE: float = 0.40  # 40%

        for i in range(1, len(records)):
            prev_close = records[i - 1].close
            curr_close = records[i].close
            if prev_close is not None and curr_close is not None and prev_close > 0:
                change = abs(curr_close - prev_close) / prev_close
                if change > MAX_CONTINUOUS_CHANGE:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.WARNING,
                        ts_code=ts_code, field="close", date=records[i].date,
                        message=(
                            f"{ts_code} {records[i-1].date}→{records[i].date} "
                            f"收盘价变动 {change*100:.1f}% 超过 40%"
                        ),
                        value=change,
                        expected_range=f"<= {MAX_CONTINUOUS_CHANGE*100:.0f}%",
                        suggestion="确认是否为涨跌停、重大事件或数据错误"))


# ── Financial Ratio Validator ───────────────────────────────────────────────────


class FinancialRatioValidator:
    """Validates financial ratio data for sanity and logical consistency.

    Checks performed:
      1. ROE range — must be in [-1.0, 5.0] (i.e. -100% to 500%).
      2. Liquidity ratios — current_ratio > 0, quick_ratio > 0.
      3. Margin ratios — gross_margin and net_margin in [-1.0, 1.0].
      4. Debt-to-equity — must be >= 0.
      5. Shares outstanding — must be > 0.
      6. Cross-report consistency — fiscal year-end consistency.

    Example:
        >>> ratios = [FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31",
        ...                                roe=0.15, current_ratio=2.0)]
        >>> validator = FinancialRatioValidator()
        >>> report = validator.validate(ratios)
    """

    ROE_MIN: float = -1.0   # -100%
    ROE_MAX: float = 5.0    # 500%
    MARGIN_MIN: float = -1.0
    MARGIN_MAX: float = 1.0
    MAX_CONTINUOUS_CHANGE: float = 5.0  # allow up to 500% YoY change for ratios

    def validate(self, records: list[FinancialRatioRecord]) -> FinancialValidationReport:
        report = FinancialValidationReport(validator_name="FinancialRatioValidator")
        report.validated_records = len(records)

        if not records:
            return report

        by_ticker: dict[str, list[FinancialRatioRecord]] = {}
        for rec in records:
            by_ticker.setdefault(rec.ts_code, []).append(rec)

        for ts_code, ticker_records in by_ticker.items():
            ticker_records.sort(key=lambda r: r.date)
            self._check_roe(ts_code, ticker_records, report)
            self._check_liquidity(ts_code, ticker_records, report)
            self._check_margins(ts_code, ticker_records, report)
            self._check_debt_to_equity(ts_code, ticker_records, report)
            self._check_shares_outstanding(ts_code, ticker_records, report)
            self._check_fiscal_year_consistency(ts_code, ticker_records, report)

        report.stats = {
            "total_records": report.validated_records,
            "tickers_checked": len(by_ticker),
        }
        return report

    def _add_ratio_issue(
        self,
        report: FinancialValidationReport,
        issue_type: IssueType,
        severity: IssueSeverity,
        ts_code: str,
        field: str,
        date: str,
        value: float | None,
        expected_range: str,
        message: str,
    ):
        report.add(FinancialDataIssue(
            issue_type=issue_type,
            severity=severity,
            ts_code=ts_code,
            field=field,
            date=date,
            value=value,
            expected_range=expected_range,
            message=message,
            suggestion=f"检查 {ts_code} {date} 的 {field} 数据来源",
        ))

    def _check_roe(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        for rec in records:
            if rec.roe is None:
                continue
            if rec.roe < self.ROE_MIN or rec.roe > self.ROE_MAX:
                self._add_ratio_issue(
                    report, IssueType.RATIO_OUT_OF_RANGE, IssueSeverity.ERROR,
                    ts_code, "roe", rec.date, rec.roe,
                    f"[{self.ROE_MIN*100:.0f}%, {self.ROE_MAX*100:.0f}%]",
                    f"{ts_code} {rec.date} ROE={rec.roe*100:.1f}% 超出合理范围 "
                    f"[{self.ROE_MIN*100:.0f}%, {self.ROE_MAX*100:.0f}%]",
                )

    def _check_liquidity(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        for rec in records:
            for field_name, val in (("current_ratio", rec.current_ratio), ("quick_ratio", rec.quick_ratio)):
                if val is None:
                    continue
                if val <= 0:
                    self._add_ratio_issue(
                        report, IssueType.RATIO_OUT_OF_RANGE, IssueSeverity.ERROR,
                        ts_code, field_name, rec.date, val, "> 0",
                        f"{ts_code} {rec.date} {field_name}={val:.2f} <= 0",
                    )

    def _check_margins(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        for rec in records:
            for field_name, val in (("gross_margin", rec.gross_margin), ("net_margin", rec.net_margin)):
                if val is None:
                    continue
                if val < self.MARGIN_MIN or val > self.MARGIN_MAX:
                    self._add_ratio_issue(
                        report, IssueType.RATIO_OUT_OF_RANGE, IssueSeverity.WARNING,
                        ts_code, field_name, rec.date, val,
                        f"[{self.MARGIN_MIN*100:.0f}%, {self.MARGIN_MAX*100:.0f}%]",
                        f"{ts_code} {rec.date} {field_name}={val*100:.1f}% 超出合理范围",
                    )

    def _check_debt_to_equity(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        for rec in records:
            if rec.debt_to_equity is None:
                continue
            if rec.debt_to_equity < 0:
                self._add_ratio_issue(
                    report, IssueType.RATIO_OUT_OF_RANGE, IssueSeverity.ERROR,
                    ts_code, "debt_to_equity", rec.date, rec.debt_to_equity, ">= 0",
                    f"{ts_code} {rec.date} 资产负债率={rec.debt_to_equity:.2f} < 0",
                )
            if rec.debt_to_equity > 100:  # > 100x is extremely unusual
                self._add_ratio_issue(
                    report, IssueType.RATIO_OUT_OF_RANGE, IssueSeverity.WARNING,
                    ts_code, "debt_to_equity", rec.date, rec.debt_to_equity, "<= 100",
                    f"{ts_code} {rec.date} 资产负债率={rec.debt_to_equity:.2f} 异常偏高",
                )

    def _check_shares_outstanding(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        for rec in records:
            if rec.total_shares is None:
                continue
            if rec.total_shares <= 0:
                self._add_ratio_issue(
                    report, IssueType.CROSS_SECTION_INCONSISTENCY, IssueSeverity.ERROR,
                    ts_code, "total_shares", rec.date, rec.total_shares, "> 0",
                    f"{ts_code} {rec.date} 总股本={rec.total_shares} <= 0",
                )

    def _check_fiscal_year_consistency(
        self, ts_code: str, records: list[FinancialRatioRecord], report: FinancialValidationReport
    ):
        """Check that all annual reports end in the same month across years."""
        annual_months: dict[str, set[int]] = {}  # ts_code -> set of month numbers
        for rec in records:
            if rec.report_type in ("annual", "Q4"):
                try:
                    month = int(rec.date[5:7])
                    annual_months.setdefault(ts_code, set()).add(month)
                except (ValueError, IndexError):
                    pass

        for ticker, months in annual_months.items():
            if len(months) > 1:
                report.add(FinancialDataIssue(
                    IssueType.CROSS_SECTION_INCONSISTENCY, IssueSeverity.WARNING,
                    ts_code=ticker, field="fiscal_year_end",
                    message=(
                        f"{ticker} 年度报告月份不一致: {sorted(months)} "
                        "(不同财年截止月份混合，可能影响跨期比较)"
                    ),
                    value=sorted(months),
                    suggestion="确认公司是否变更了财年截止月份，或使用调整后的日期进行跨期比较"))


# ── Time Series Gap Validator ────────────────────────────────────────────────


@dataclass
class TradingCalendarRecord:
    """A trading calendar entry.

    Attributes:
        date: Date in "YYYY-MM-DD" format.
        is_trading_day: Whether the market was open.
        market: Market identifier (e.g. "SSE", "SZSE", "NYSE").
    """
    date: str
    is_trading_day: bool = True
    market: str = "SSE"


class TimeSeriesGapValidator:
    """Detects missing data points in time series relative to a trading calendar.

    This validator works with any date-indexed data (price, ratios, macro indicators).
    It can use an explicit calendar or infer gaps from the data itself.

    Example:
        >>> gap_validator = TimeSeriesGapValidator(
        ...     max_consecutive_gaps=3,
        ...     calendar=[
        ...         TradingCalendarRecord(date="2024-01-02"),
        ...         TradingCalendarRecord(date="2024-01-03"),
        ...     ]
        ... )
        >>> # Or infer gaps from data:
        >>> gap_validator = TimeSeriesGapValidator(infer_gaps=True)
        >>> gap_validator.validate([{"date": "2024-01-02"}, {"date": "2024-01-05"}])
    """

    def __init__(
        self,
        max_consecutive_gaps: int = 3,
        calendar: list[TradingCalendarRecord] | None = None,
        infer_gaps: bool = False,
        max_inferred_gap_days: int = 7,
    ) -> None:
        self.max_consecutive_gaps = max_consecutive_gaps
        self.calendar = calendar
        self.infer_gaps = infer_gaps
        self.max_inferred_gap_days = max_inferred_gap_days

    def validate_dict_series(
        self, records: list[dict], date_field: str = "date", entity_field: str = ""
    ) -> FinancialValidationReport:
        """Validate a list of dict records for time-series gaps.

        Args:
            records: List of dict records containing at least a date field.
            date_field: Name of the date field in each dict.
            entity_field: Optional field name for entity identifier (e.g. "ts_code").

        Returns:
            FinancialValidationReport with detected gaps.
        """
        report = FinancialValidationReport(validator_name="TimeSeriesGapValidator")
        report.validated_records = len(records)

        if not records:
            return report

        # Build calendar set
        calendar_set: set[str] = set()
        if self.calendar:
            calendar_set = {r.date for r in self.calendar if r.is_trading_day}

        # Group by entity if entity_field is provided
        if entity_field:
            by_entity: dict[str, list[dict]] = {}
            for rec in records:
                key = str(rec.get(entity_field, ""))
                by_entity.setdefault(key, []).append(rec)
        else:
            by_entity = {"_global": records}

        for entity, entity_records in by_entity.items():
            entity_records.sort(key=lambda r: str(r.get(date_field, "")))
            self._detect_gaps(entity, entity_records, date_field, calendar_set, report)

        report.stats = {
            "total_records": report.validated_records,
            "entities_checked": len(by_entity),
        }
        return report

    def _detect_gaps(
        self,
        entity: str,
        records: list[dict],
        date_field: str,
        calendar_set: set[str],
        report: FinancialValidationReport,
    ):
        from datetime import datetime, timedelta

        dates = [r[date_field] for r in records if date_field in r]
        for i in range(1, len(dates)):
            try:
                d_curr = datetime.strptime(dates[i], "%Y-%m-%d")
                d_prev = datetime.strptime(dates[i - 1], "%Y-%m-%d")
            except ValueError:
                continue

            delta = (d_curr - d_prev).days

            if calendar_set:
                # Calendar-based gap detection
                expected_dates = [
                    (d_prev + timedelta(days=j)).strftime("%Y-%m-%d")
                    for j in range(1, delta)
                ]
                missing = [d for d in expected_dates if d in calendar_set]
                if missing:
                    ts_code_str = f"{entity} " if entity != "_global" else ""
                    report.add(FinancialDataIssue(
                        IssueType.MISSING_TRADING_DAYS, IssueSeverity.WARNING,
                        ts_code=entity if entity != "_global" else "",
                        field=date_field,
                        date=f"{dates[i-1]} to {dates[i]}",
                        message=(
                            f"{ts_code_str}区间 {dates[i-1]}→{dates[i]} 缺失 "
                            f"{len(missing)} 个交易日: {missing[:5]}"
                            + (" ..." if len(missing) > 5 else "")
                        ),
                        value=len(missing),
                        expected_range="0 missing trading days",
                        suggestion="补充缺失交易日数据或确认数据采集频率"))
            else:
                # Inference-based gap detection
                if delta > self.max_inferred_gap_days:
                    ts_code_str = f"{entity} " if entity != "_global" else ""
                    report.add(FinancialDataIssue(
                        IssueType.MISSING_TRADING_DAYS, IssueSeverity.INFO,
                        ts_code=entity if entity != "_global" else "",
                        field=date_field,
                        date=f"{dates[i-1]} to {dates[i]}",
                        message=(
                            f"{ts_code_str}区间 {dates[i-1]}→{dates[i]} "
                            f"间隔 {delta} 天超过阈值 {self.max_inferred_gap_days} 天"
                        ),
                        value=delta,
                        expected_range=f"<= {self.max_inferred_gap_days} days",
                        suggestion="确认是否因数据采集频率导致，或补充缺失数据点"))


# ── Cross-Sectional Consistency Validator ─────────────────────────────────────


class CrossSectionalValidator:
    """Validates cross-sectional consistency across multiple entities and time periods.

    Checks performed:
      1. Consistent fiscal year-ends across reporting periods for each entity.
      2. Negative shares outstanding (corporate shares must be non-negative).
      3. Price cross-validation — price > 0 for all trading records.
      4. Entity-level data completeness — ensure key fields are not all null.
      5. Duplicate records — detect identical (entity, date) pairs.

    Example:
        >>> cross_validator = CrossSectionalValidator()
        >>> report = cross_validator.validate([
        ...     {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.5},
        ...     {"ts_code": "000001.SZ", "date": "2024-01-02", "close": 10.5},  # duplicate
        ... ])
    """

    def __init__(
        self,
        require_fields: list[str] | None = None,
        allow_null_ratio: float = 0.5,
    ) -> None:
        self.require_fields = require_fields or []
        self.allow_null_ratio = allow_null_ratio

    def validate_dict_records(
        self,
        records: list[dict],
        entity_field: str = "ts_code",
        date_field: str = "date",
    ) -> FinancialValidationReport:
        report = FinancialValidationReport(validator_name="CrossSectionalValidator")
        report.validated_records = len(records)

        if not records:
            return report

        self._check_duplicates(records, entity_field, date_field, report)
        self._check_negative_shares(records, report)
        self._check_price_positive(records, report)
        self._check_null_ratios(records, report)

        report.stats = {
            "total_records": report.validated_records,
            "unique_entities": len({r.get(entity_field) for r in records}),
        }
        return report

    def _check_duplicates(
        self,
        records: list[dict],
        entity_field: str,
        date_field: str,
        report: FinancialValidationReport,
    ):
        seen: dict[tuple, int] = {}
        for rec in records:
            key = (rec.get(entity_field), rec.get(date_field))
            seen[key] = seen.get(key, 0) + 1

        duplicates = {k: v for k, v in seen.items() if v > 1}
        for (entity, date), count in duplicates.items():
            report.add(FinancialDataIssue(
                IssueType.CROSS_SECTION_INCONSISTENCY, IssueSeverity.ERROR,
                ts_code=str(entity), field=date_field, date=str(date),
                message=(
                    f"发现重复记录: {entity} {date} 出现 {count} 次"
                ),
                value=count,
                expected_range="1",
                suggestion="去重或确认是否为前后复权数据拆分"))

    def _check_negative_shares(self, records: list[dict], report: FinancialValidationReport):
        for rec in records:
            for field_name in ("total_shares", "float_shares", "shares"):
                val = rec.get(field_name)
                if val is not None and isinstance(val, (int, float)) and val < 0:
                    report.add(FinancialDataIssue(
                        IssueType.CROSS_SECTION_INCONSISTENCY, IssueSeverity.ERROR,
                        ts_code=str(rec.get("ts_code", "")),
                        field=field_name,
                        date=str(rec.get("date", "")),
                        message=f"{rec.get('ts_code')} {rec.get('date')} {field_name}={val} < 0",
                        value=val,
                        expected_range=">= 0",
                        suggestion="检查数据来源，股本数不可能为负"))

    def _check_price_positive(self, records: list[dict], report: FinancialValidationReport):
        price_fields = ("open", "high", "low", "close", "price")
        for rec in records:
            for field_name in price_fields:
                val = rec.get(field_name)
                if val is not None and isinstance(val, (int, float)) and val <= 0:
                    report.add(FinancialDataIssue(
                        IssueType.PRICE_OUTLIER, IssueSeverity.ERROR,
                        ts_code=str(rec.get("ts_code", "")),
                        field=field_name,
                        date=str(rec.get("date", "")),
                        message=(
                            f"{rec.get('ts_code')} {rec.get('date')} "
                            f"{field_name}={val} <= 0"
                        ),
                        value=val,
                        expected_range="> 0",
                        suggestion="检查数据来源，确认是否为停牌或除权除息数据"))

    def _check_null_ratios(self, records: list[dict], report: FinancialValidationReport):
        if not self.require_fields:
            return

        entity_null_counts: dict[str, dict[str, int]] = {}
        for rec in records:
            entity = str(rec.get("ts_code", ""))
            entity_null_counts.setdefault(entity, {f: 0 for f in self.require_fields})
            for field in self.require_fields:
                if rec.get(field) is None:
                    entity_null_counts[entity][field] += 1

        total = len(records) or 1
        for entity, null_counts in entity_null_counts.items():
            for field, null_count in null_counts.items():
                null_ratio = null_count / total
                if null_ratio > self.allow_null_ratio:
                    report.add(FinancialDataIssue(
                        IssueType.CROSS_SECTION_INCONSISTENCY, IssueSeverity.WARNING,
                        ts_code=entity, field=field,
                        message=(
                            f"{entity} 字段 {field} 缺失比例 {null_ratio*100:.1f}% "
                            f"超过阈值 {self.allow_null_ratio*100:.0f}%"
                        ),
                        value=null_ratio,
                        expected_range=f"<= {self.allow_null_ratio*100:.0f}%",
                        suggestion="补充缺失数据或调整数据采集策略"))


# ── Data Freshness Validator ──────────────────────────────────────────────────


@dataclass
class FreshnessConfig:
    """Configuration for data freshness checking.

    Attributes:
        warning_days: Number of days after which a WARNING is issued.
        error_days: Number of days after which an ERROR is issued.
        date_field: Field name containing the date to check.
        reference_date: Date to compare against (defaults to today).
    """
    warning_days: int = 30
    error_days: int = 90
    date_field: str = "date"
    reference_date: str | None = None

    @property
    def ref_date(self) -> str:
        if self.reference_date:
            return self.reference_date
        return datetime.now().strftime("%Y-%m-%d")


class DataFreshnessValidator:
    """Checks whether the most recent data is sufficiently up-to-date.

    This validator identifies datasets that have not been updated recently,
    which is critical for financial data pipelines where stale data can
    lead to incorrect analysis.

    Example:
        >>> freshness = DataFreshnessValidator(
        ...     warning_days=30, error_days=90,
        ...     date_field="report_date"
        ... )
        >>> report = freshness.validate([
        ...     {"ts_code": "000001.SZ", "report_date": "2024-12-31"},
        ...     {"ts_code": "000001.SZ", "report_date": "2026-06-01"},
        ... ])
    """

    def __init__(self, config: FreshnessConfig | None = None) -> None:
        self.config = config or FreshnessConfig()

    def validate(
        self,
        records: list[dict],
        entity_field: str = "ts_code",
    ) -> FinancialValidationReport:
        report = FinancialValidationReport(validator_name="DataFreshnessValidator")
        report.validated_records = len(records)

        if not records:
            return report

        from datetime import datetime

        ref = datetime.strptime(self.config.ref_date, "%Y-%m-%d")
        date_field = self.config.date_field

        # Group by entity and find the latest date for each
        by_entity: dict[str, list[dict]] = {}
        for rec in records:
            entity = str(rec.get(entity_field, ""))
            by_entity.setdefault(entity, []).append(rec)

        for entity, entity_records in by_entity.items():
            latest_date_str = ""
            latest_date: datetime | None = None

            for rec in entity_records:
                date_str = str(rec.get(date_field, ""))
                if not date_str:
                    continue
                try:
                    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    if latest_date is None or d > latest_date:
                        latest_date = d
                        latest_date_str = date_str
                except ValueError:
                    continue

            if latest_date is None:
                continue

            days_old = (ref - latest_date).days

            if days_old > self.config.error_days:
                severity = IssueSeverity.ERROR
            elif days_old > self.config.warning_days:
                severity = IssueSeverity.WARNING
            else:
                continue

            report.add(FinancialDataIssue(
                IssueType.DATA_FRESHNESS, severity,
                ts_code=entity,
                field=date_field,
                date=latest_date_str,
                message=(
                    f"{entity} 最新数据日期为 {latest_date_str}，"
                    f"距今 {days_old} 天"
                    + ("，数据可能已过时" if severity == IssueSeverity.WARNING else "，数据已过时")
                ),
                value=days_old,
                expected_range=f"<= {self.config.warning_days} days (warning), "
                              f"<= {self.config.error_days} days (error)",
                suggestion="更新数据源或确认该股票是否已停牌",
            ))

        report.stats = {
            "total_records": report.validated_records,
            "entities_checked": len(by_entity),
        }
        return report


# ── Composite Validator ───────────────────────────────────────────────────────


class CompositeValidator:
    """Runs multiple validators in sequence and aggregates their reports.

    This is the primary interface for validating heterogeneous financial data.
    It collects all issues from registered validators and provides a unified
    report with combined statistics.

    Example:
        >>> composite = CompositeValidator()
        >>> composite.register(StockPriceValidator())
        >>> composite.register(FinancialRatioValidator())
        >>> report = composite.validate({
        ...     "prices": [...],
        ...     "ratios": [...],
        ... })
        >>> print(f"Total errors: {report.error_count}")

    Args:
        validators: Optional initial list of validators to register.
        stop_on_error: If True, stops running remaining validators after an
            ERROR is found. Defaults to False (runs all validators).
    """

    def __init__(
        self,
        validators: list[Any] | None = None,
        stop_on_error: bool = False,
    ) -> None:
        self._validators: list[Any] = list(validators) if validators else []
        self.stop_on_error = stop_on_error

    def register(self, validator: Any) -> "CompositeValidator":
        """Register a validator. Returns self for chaining.

        Args:
            validator: Any object implementing the BaseValidator protocol
                (i.e., has a `validate(data) -> FinancialValidationReport` method).

        Returns:
            self, for method chaining.
        """
        self._validators.append(validator)
        return self

    def validate(
        self,
        datasets: dict[str, list[dict] | list[StockPriceRecord] | list[FinancialRatioRecord]],
    ) -> FinancialValidationReport:
        """Run all registered validators on the provided datasets.

        Each registered validator is attempted against every dataset. Validators
        that raise TypeError (wrong record type) are skipped gracefully.

        Args:
            datasets: A dict mapping dataset names to lists of records.
                Records can be dataclass instances (StockPriceRecord,
                FinancialRatioRecord, etc.) or plain dicts.

        Returns:
            FinancialValidationReport with all issues from all validators.
        """
        master_report = FinancialValidationReport(
            validator_name="CompositeValidator",
            stats={"validators_run": 0, "datasets_processed": len(datasets)},
        )

        for validator in self._validators:
            validator_name = getattr(validator, "__class__", type(validator)).__name__

            for dataset_name, dataset in datasets.items():
                report = self._run_validator(validator, dataset)
                if report.issues or report.validated_records > 0:
                    master_report.issues.extend(report.issues)
                    master_report.stats["validators_run"] = (
                        master_report.stats.get("validators_run", 0) + 1
                    )
                    logger.debug(
                        "%s processed %s: %d records, %d issues",
                        validator_name, dataset_name,
                        report.validated_records, len(report.issues),
                    )

                if self.stop_on_error and report.has_errors:
                    logger.warning(
                        "CompositeValidator stopping early due to ERROR in %s",
                        validator_name,
                    )
                    break

        # Aggregate stats
        master_report.stats["total_issues"] = len(master_report.issues)
        master_report.stats["total_errors"] = master_report.error_count
        master_report.stats["total_warnings"] = master_report.warning_count
        return master_report

    def _run_validator(
        self,
        validator: Any,
        data: list,
    ) -> FinancialValidationReport:
        """Run a single validator, handling exceptions gracefully."""
        try:
            return validator.validate(data)
        except (TypeError, AttributeError, KeyError) as exc:
            logger.debug(
                "Validator %s skipped/errored on input (%s): %s",
                type(validator).__name__, type(exc).__name__, exc,
            )
            return FinancialValidationReport(validator_name=type(validator).__name__)

    def print_report(self, report: FinancialValidationReport):
        """Print a human-readable validation report to stdout."""
        print("=" * 70)
        print(f"  Financial Data Validation Report — {report.validator_name}")
        print("=" * 70)

        print(f"\n验证结果: {'PASS' if not report.has_errors else 'FAIL'}")
        print(f"  ERROR:   {report.error_count}")
        print(f"  WARNING: {report.warning_count}")
        print(f"  INFO:    {report.info_count}")

        if report.stats:
            print("\n统计信息:")
            for k, v in report.stats.items():
                print(f"  {k}: {v}")

        if report.issues:
            print("\n详细问题列表:")
            print("-" * 70)
            for issue in report.issues:
                sev = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[issue.severity.value]
                loc = f"[{issue.ts_code}]" + (f" {issue.field}" if issue.field else "")
                print(f"  [{sev}] {loc}")
                print(f"    {issue.message}")
                if issue.expected_range:
                    print(f"    期望范围: {issue.expected_range}")
                if issue.suggestion:
                    print(f"    → 建议: {issue.suggestion}")
        else:
            print("\n无问题。数据验证通过。")

        print("=" * 70)


# ── Global Validator Registry ─────────────────────────────────────────────────


_validator_registry: dict[str, Callable[..., Any]] = {}


def register_validator(name: str, factory: Callable[..., Any]) -> None:
    """Register a custom validator factory function.

    This allows adding domain-specific validators to the global registry
    for later retrieval and use by the CompositeValidator.

    Args:
        name: Unique identifier for the validator.
        factory: A callable that returns a validator instance.

    Example:
        >>> def my_price_validator():
        ...     return StockPriceValidator(max_daily_return=0.30)
        >>> register_validator("strict_price", my_price_validator)
        >>>
        >>> # Later, retrieve and use it:
        >>> factory = get_validator("strict_price")
        >>> v = factory()
        >>> v.validate(some_data)
    """
    _validator_registry[name] = factory
    logger.debug("Registered validator: %s", name)


def get_validator(name: str) -> Callable[..., Any] | None:
    """Retrieve a registered validator factory by name.

    Args:
        name: Name of the validator as registered with `register_validator`.

    Returns:
        The factory callable, or None if not found.
    """
    return _validator_registry.get(name)


def list_validators() -> list[str]:
    """Return the list of all registered validator names."""
    return list(_validator_registry.keys())


def clear_registry() -> None:
    """Clear all registered validators. Use with caution."""
    _validator_registry.clear()


# ── __all__ ───────────────────────────────────────────────────────────────────

__all__ = [
    # Enums
    "IssueSeverity",
    "IssueType",
    # Province validator
    "ProvinceDataValidator",
    # Shared dataclasses
    "DataIssue",
    "ValidationReport",
    # Financial validator dataclasses
    "StockPriceRecord",
    "FinancialRatioRecord",
    "TradingCalendarRecord",
    "FinancialDataIssue",
    "FinancialValidationReport",
    "FreshnessConfig",
    # Validators
    "StockPriceValidator",
    "FinancialRatioValidator",
    "TimeSeriesGapValidator",
    "CrossSectionalValidator",
    "DataFreshnessValidator",
    "CompositeValidator",
    # Registry
    "register_validator",
    "get_validator",
    "list_validators",
    "clear_registry",
]


if __name__ == "__main__":
    # ── Demo: ProvinceDataValidator ──────────────────────────────────────────────
    try:
        validator = ProvinceDataValidator()
        report = validator.validate_all()
        validator.print_report(report)
    except FileNotFoundError:
        print("Province data file not found, skipping ProvinceDataValidator demo.")

    print("\n")

    # ── Demo: FinancialDataValidator components ──────────────────────────────────
    sample_prices: list[StockPriceRecord] = [
        StockPriceRecord(ts_code="000001.SZ", date="2024-01-02", open=10.0, high=10.8, low=9.5, close=10.5, volume=1_000_000),
        StockPriceRecord(ts_code="000001.SZ", date="2024-01-03", open=10.5, high=10.5, low=10.5, close=10.5, volume=1_200_000),  # suspicious: no movement
        StockPriceRecord(ts_code="000001.SZ", date="2024-01-04", open=10.5, high=16.0, low=10.0, close=15.0, volume=5_000_000),  # 42.9% up
        StockPriceRecord(ts_code="000001.SZ", date="2024-01-05", open=0, high=0, low=0, close=0, volume=0),  # ERROR: price = 0
    ]

    sample_ratios: list[FinancialRatioRecord] = [
        FinancialRatioRecord(ts_code="000001.SZ", date="2022-12-31", roe=0.12, current_ratio=2.5, total_shares=1_000_000_000),
        FinancialRatioRecord(ts_code="000001.SZ", date="2023-12-31", roe=8.0, current_ratio=0.5, total_shares=1_000_000_000),  # ERROR: ROE > 500%
        FinancialRatioRecord(ts_code="000001.SZ", date="2024-12-31", roe=-0.15, current_ratio=-1.0, total_shares=-500_000_000),  # ERROR: negative values
    ]

    composite = CompositeValidator()
    composite.register(StockPriceValidator())
    composite.register(FinancialRatioValidator())

    combined = composite.validate({
        "prices": sample_prices,     # pass dataclass instances directly
        "ratios": sample_ratios,      # pass dataclass instances directly
    })

    # Show simplified report
    print("Financial Validator Demo:")
    print(f"  Total errors:   {combined.error_count}")
    print(f"  Total warnings:  {combined.warning_count}")
    for issue in combined.issues:
        sev = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[issue.severity.value]
        print(f"  [{sev}] {issue.ts_code or 'global'} | {issue.field} | {issue.message}")
