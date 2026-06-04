"""Fact Checker Agent for Financial Reports.

Reference: FinResearchAgent's dual-layer verification mechanism.

This module provides comprehensive validation for financial reports:
- Numerical accuracy checks
- Citation verification
- Logical consistency
- Temporal consistency
- Unit consistency
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Must fix
    WARNING = "warning"  # Should fix
    INFO = "info"        # Consider fixing


@dataclass
class ValidationIssue:
    """A single validation issue."""
    issue_type: str
    severity: IssueSeverity
    message: str
    location: str = ""
    suggestion: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report for a document."""
    document_type: str
    overall_status: str  # "PASS", "FAIL", "WARN"
    score: float  # 0.0 - 1.0
    issues: list[ValidationIssue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.overall_status == "PASS"

    @property
    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == IssueSeverity.WARNING for i in self.issues)

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)

    def finalize(self):
        """Finalize the report, computing summary statistics."""
        self.summary = {
            "total": len(self.issues),
            "errors": sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR),
            "warnings": sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING),
            "info": sum(1 for i in self.issues if i.severity == IssueSeverity.INFO),
        }

        if self.has_errors:
            self.overall_status = "FAIL"
            self.score = max(0.0, 1.0 - len(self.issues) * 0.1)
        elif self.has_warnings:
            self.overall_status = "WARN"
            self.score = max(0.5, 1.0 - len(self.issues) * 0.05)
        else:
            self.overall_status = "PASS"
            self.score = 1.0


# ─── Validation Rules ────────────────────────────────────────────────────────────


class ValidationRule:
    """Base class for validation rules."""

    def __init__(self, name: str, severity: IssueSeverity = IssueSeverity.WARNING):
        self.name = name
        self.severity = severity

    def validate(self, text: str) -> list[ValidationIssue]:
        raise NotImplementedError


class NumericalRangeRule(ValidationRule):
    """Check if numerical values are within reasonable ranges."""

    RANGES = {
        # Financial ratios (percentage)
        "roe": (0, 100),
        "roa": (-50, 50),
        "gross_margin": (0, 100),
        "net_margin": (-50, 50),
        "debt_ratio": (0, 200),
        "current_ratio": (0, 20),
        "quick_ratio": (0, 20),
        # Growth rates (percentage)
        "revenue_growth": (-100, 1000),
        "profit_growth": (-500, 1000),
        "eps_growth": (-500, 1000),
        # Others
        "pe_ratio": (0, 500),
        "pb_ratio": (0, 100),
        "peg_ratio": (-10, 50),
        "dividend_yield": (0, 30),
        "payout_ratio": (0, 150),
    }

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        for ratio_name, (min_val, max_val) in self.RANGES.items():
            # Look for percentage values in context
            pattern = rf"{ratio_name}[^:]*?(\d+\.?\d*)\s*%"
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                value = float(match.group(1))
                if not (min_val <= value <= max_val):
                    issues.append(ValidationIssue(
                        issue_type="numerical_range",
                        severity=self.severity,
                        message=f"{ratio_name.upper()} = {value}% 超出合理范围 [{min_val}%, {max_val}%]",
                        location=match.group(0)[:50],
                        suggestion="请核实该数值的准确性",
                        evidence=[f"原始文本: {match.group(0)}"],
                    ))

        return issues


class YoYQoQLogicRule(ValidationRule):
    """Check YoY and QoQ growth logic consistency."""

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        # Extract all YoY growth rates
        yoy_pattern = r"(?:同比|YoY|year-over-year)[^\d]*(\d+\.?\d*)\s*%"
        yoy_matches = re.findall(yoy_pattern, text.lower())

        # Extract all QoQ growth rates
        qoq_pattern = r"(?:环比|QoQ|quarter-over-quarter)[^\d]*(\d+\.?\d*)\s*%"
        qoq_matches = re.findall(qoq_pattern, text.lower())

        # Check for impossible combinations
        # e.g., Q4 growth > Q1 growth but overall year growth < Q4 growth
        if len(yoy_matches) >= 2:
            yoy_values = [float(v) for v in yoy_matches]
            # If multiple YoY values exist, they should be roughly consistent
            if len(yoy_values) > 1:
                max_diff = max(yoy_values) - min(yoy_values)
                if max_diff > 50:
                    issues.append(ValidationIssue(
                        issue_type="yoy_logic",
                        severity=IssueSeverity.WARNING,
                        message=f"同比增长率差异过大: {max_diff:.1f}个百分点，可能存在数据错误",
                        suggestion="请核实各季度/期间的同比增长率",
                    ))

        return issues


class TemporalConsistencyRule(ValidationRule):
    """Check temporal consistency of events and data."""

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        # Extract dates and events
        date_pattern = r"(\d{4})年(\d{1,2})月?(\d{0,2})日?"
        dates = re.findall(date_pattern, text)

        if len(dates) >= 2:
            # Convert to comparable format
            parsed_dates = []
            for year, month, day in dates:
                month = int(month) if month else 1
                day = int(day) if day else 1
                parsed_dates.append((int(year), month, day))

            # Check chronological order
            for i in range(len(parsed_dates) - 1):
                d1, d2 = parsed_dates[i], parsed_dates[i + 1]
                if d1 > d2:
                    issues.append(ValidationIssue(
                        issue_type="temporal",
                        severity=IssueSeverity.ERROR,
                        message=f"时间顺序错误: {''.join(map(str, d1))} 晚于 {''.join(map(str, d2))}",
                        suggestion="请检查事件发生的时间顺序",
                    ))

        return issues


class UnitConsistencyRule(ValidationRule):
    """Check unit consistency throughout the document."""

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        # Common unit patterns
        unit_patterns = [
            (r"(\d+\.?\d*)\s*万元", "万元"),
            (r"(\d+\.?\d*)\s*亿元", "亿元"),
            (r"(\d+\.?\d*)\s*百万", "百万"),
            (r"(\d+\.?\d*)\s*十亿", "十亿"),
            (r"(\d+\.?\d*)\s*万亿", "万亿"),
        ]

        found_units = {}
        for pattern, unit_name in unit_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                value = float(match.group(1))
                if unit_name in found_units:
                    # Check for large jumps suggesting unit confusion
                    if value < found_units[unit_name] * 0.01 or value > found_units[unit_name] * 100:
                        # Could be mixing millions/billions
                        issues.append(ValidationIssue(
                            issue_type="unit",
                            severity=IssueSeverity.WARNING,
                            message=f"数值 {match.group(0)} 与同单位数值差异较大，可能存在单位混淆",
                            location=match.group(0)[:30],
                            suggestion="请确认单位使用的一致性",
                        ))
                else:
                    found_units[unit_name] = value

        return issues


class CitationFormatRule(ValidationRule):
    """Check citation format validity."""

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        # DOI pattern
        doi_pattern = r"10\.\d{4,}/[^\s]+"
        dois = re.findall(doi_pattern, text)

        # ArXiv ID pattern
        arxiv_pattern = r"arXiv:(\d{4}\.\d{4,})"
        arxiv_ids = re.findall(arxiv_pattern, text)

        # Check DOI validity
        for doi in dois:
            if not re.match(r"10\.\d{4,}/[a-zA-Z0-9\.\-/]+", doi):
                issues.append(ValidationIssue(
                    issue_type="citation_format",
                    severity=IssueSeverity.WARNING,
                    message=f"DOI格式可能不正确: {doi}",
                    suggestion="请使用标准DOI格式: 10.xxxx/xxxxx",
                ))

        # Check ArXiv ID validity
        for arxiv_id in arxiv_ids:
            if not re.match(r"\d{4}\.\d{4,}", arxiv_id):
                issues.append(ValidationIssue(
                    issue_type="citation_format",
                    severity=IssueSeverity.WARNING,
                    message=f"ArXiv ID格式可能不正确: {arxiv_id}",
                    suggestion="请使用标准ArXiv格式: YYYY.NNNNN",
                ))

        return issues


class MathConsistencyRule(ValidationRule):
    """Check mathematical consistency of formulas and calculations."""

    def validate(self, text: str) -> list[ValidationIssue]:
        issues = []

        # Check for common financial formula patterns
        # ROE = Net Income / Equity
        roe_pattern = r"ROE\s*[=≈]\s*(\d+\.?\d*)\s*%"
        roe_matches = re.findall(roe_pattern, text)

        # Net Margin + Gross Margin sanity check
        net_margin_pattern = r"净利率\s*[=≈]\s*(\d+\.?\d*)\s*%"
        gross_margin_pattern = r"毛利率\s*[=≈]\s*(\d+\.?\d*)\s*%"

        net_matches = re.findall(net_margin_pattern, text)
        gross_matches = re.findall(gross_margin_pattern, text)

        if net_matches and gross_matches:
            net = float(net_matches[0])
            gross = float(gross_matches[0])
            if net > gross:
                issues.append(ValidationIssue(
                    issue_type="math",
                    severity=IssueSeverity.ERROR,
                    message=f"净利率({net}%)不应大于毛利率({gross}%)",
                    suggestion="请核实净利率和毛利率的计算",
                ))

        return issues


# ─── Fact Checker Agent ────────────────────────────────────────────────────────


class FactCheckerAgent:
    """
    Fact Checker Agent for validating financial reports.

    Reference: FinResearchAgent's dual-layer verification mechanism
    with Fact Checker and Review Agent.

    This agent performs comprehensive validation:
    1. Numerical accuracy checks
    2. Citation verification
    3. Logical consistency
    4. Temporal consistency
    5. Unit consistency
    6. Mathematical formulas
    """

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.validation_rules: list[ValidationRule] = [
            NumericalRangeRule("数值范围检验", IssueSeverity.ERROR),
            YoYQoQLogicRule("同比环比逻辑", IssueSeverity.WARNING),
            TemporalConsistencyRule("时间线一致性", IssueSeverity.WARNING),
            UnitConsistencyRule("单位一致性", IssueSeverity.WARNING),
            CitationFormatRule("引用格式", IssueSeverity.INFO),
            MathConsistencyRule("数学公式", IssueSeverity.ERROR),
        ]

    def check_report(self, report: str, document_type: str = "financial_report") -> ValidationReport:
        """
        Validate a complete financial report.

        Parameters
        ----------
        report : str
            The report text to validate.
        document_type : str
            Type of document (financial_report, research_paper, etc.)

        Returns
        -------
        ValidationReport
            Complete validation report with issues and score.
        """
        validation_report = ValidationReport(
            document_type=document_type,
            overall_status="PASS",
            score=1.0,
            metadata={
                "length_chars": len(report),
                "length_words": len(report.split()),
            },
        )

        # Run all validation rules
        for rule in self.validation_rules:
            try:
                issues = rule.validate(report)
                for issue in issues:
                    validation_report.add_issue(issue)
            except Exception as e:
                logger.error(f"Rule {rule.name} failed: {e}")

        # Finalize the report
        validation_report.finalize()

        return validation_report

    def check_section(self, section: str, section_name: str = "") -> ValidationReport:
        """Validate a single section."""
        return self.check_report(section, f"section_{section_name}")

    def check_numerical_accuracy(self, report: str) -> list[ValidationIssue]:
        """Run only numerical accuracy checks."""
        rule = NumericalRangeRule("数值范围检验")
        return rule.validate(report)

    def check_citations(self, report: str) -> list[ValidationIssue]:
        """Run only citation checks."""
        rule = CitationFormatRule("引用格式")
        return rule.validate(report)

    def format_report(self, validation_report: ValidationReport) -> str:
        """Format validation report for display."""
        lines = []

        # Header
        status_icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(
            validation_report.overall_status, "❓"
        )
        lines.append(f"# 验证报告 {status_icon}")
        lines.append("")
        lines.append(f"**状态**: {validation_report.overall_status}")
        lines.append(f"**评分**: {validation_report.score:.1%}")
        lines.append("")

        # Summary
        if validation_report.summary["total"] > 0:
            lines.append("## 问题摘要")
            lines.append(f"- 总计: {validation_report.summary['total']}")
            lines.append(f"- 错误: {validation_report.summary['errors']}")
            lines.append(f"- 警告: {validation_report.summary['warnings']}")
            lines.append(f"- 提示: {validation_report.summary['info']}")
            lines.append("")

        # Detailed issues
        if validation_report.issues:
            lines.append("## 详细问题")

            # Group by severity
            by_severity = {}
            for issue in validation_report.issues:
                severity = issue.severity.value
                if severity not in by_severity:
                    by_severity[severity] = []
                by_severity[severity].append(issue)

            for severity in [IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO]:
                severity_name = severity.value
                if severity_name in by_severity:
                    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity_name, "")
                    lines.append(f"### {icon} {severity_name.upper()}")
                    for issue in by_severity[severity_name]:
                        lines.append(f"- **[{issue.issue_type}]** {issue.message}")
                        if issue.location:
                            lines.append(f"  - 位置: {issue.location}")
                        if issue.suggestion:
                            lines.append(f"  - 建议: {issue.suggestion}")

        return "\n".join(lines)

    def generate_fix_suggestions(self, validation_report: ValidationReport) -> str:
        """Generate LLM prompt for fixing issues."""
        if not validation_report.issues:
            return "所有验证项通过，无需修复。"

        suggestions = ["请根据以下问题修复报告:\n"]

        for i, issue in enumerate(validation_report.issues, 1):
            suggestions.append(f"{i}. [{issue.issue_type}] {issue.message}")
            if issue.suggestion:
                suggestions.append(f"   建议: {issue.suggestion}")
            suggestions.append("")

        return "\n".join(suggestions)


# ─── CLI Interface ──────────────────────────────────────────────────────────────


def main():
    """CLI interface for fact checker."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Fact Checker Agent")
    parser.add_argument("--text", type=str, help="Text to validate")
    parser.add_argument("--file", type=str, help="File to validate")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    # Get text to validate
    if args.text:
        text = args.text
    elif args.file:
        from pathlib import Path
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("Please provide --text or --file")
        sys.exit(1)

    # Run validation
    checker = FactCheckerAgent()
    report = checker.check_report(text)

    # Output
    if args.format == "json":
        import json
        print(json.dumps({
            "status": report.overall_status,
            "score": report.score,
            "summary": report.summary,
            "issues": [
                {
                    "type": i.issue_type,
                    "severity": i.severity.value,
                    "message": i.message,
                    "location": i.location,
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(checker.format_report(report))


if __name__ == "__main__":
    main()
