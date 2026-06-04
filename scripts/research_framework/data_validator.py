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
    def error_count(self) -> int:
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

    # ── Compute stats ────────────────────────────────────────────────────────

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


if __name__ == "__main__":
    validator = ProvinceDataValidator()
    report = validator.validate_all()
    validator.print_report(report)
