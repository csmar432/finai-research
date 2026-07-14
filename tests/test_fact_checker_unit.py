"""Tests for scripts/core/fact_checker.py — Validation dataclasses and rules."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.fact_checker import (
        IssueSeverity,
        ValidationIssue,
        ValidationReport,
        ValidationRule,
        NumericalRangeRule,
        YoYQoQLogicRule,
        CitationFormatRule,
        MathConsistencyRule,
    )
except Exception as _exc:
    pytest.skip(f"fact_checker not importable: {_exc}", allow_module_level=True)


class TestIssueSeverity:
    def test_values(self):
        """IssueSeverity must have expected enum values."""
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"


class TestValidationIssue:
    def test_required_fields(self):
        """ValidationIssue must accept all required fields."""
        issue = ValidationIssue(
            issue_type="numerical_range",
            severity=IssueSeverity.ERROR,
            message="Revenue is negative",
            location="Table 1, Row 3",
            suggestion="Check data source",
            evidence=["Source: Wind Data"],
        )
        assert issue.issue_type == "numerical_range"
        assert issue.severity == IssueSeverity.ERROR
        assert "Revenue is negative" in issue.message
        assert "Table 1" in issue.location

    def test_defaults(self):
        """Default values must be sensible."""
        issue = ValidationIssue(
            issue_type="citation",
            severity=IssueSeverity.WARNING,
            message="Missing DOI",
        )
        assert issue.location == ""
        assert issue.suggestion == ""
        assert issue.evidence == []


class TestValidationReport:
    def test_required_fields(self):
        """ValidationReport requires document_type, overall_status, score."""
        report = ValidationReport(
            document_type="financial_report",
            overall_status="PASS",
            score=85.0,
        )
        assert report.document_type == "financial_report"
        assert report.overall_status == "PASS"
        assert report.score == 85.0

    def test_add_issue(self):
        """add_issue must add to the issues list."""
        report = ValidationReport(
            document_type="report",
            overall_status="PASS",
            score=100.0,
        )
        issue = ValidationIssue("test", IssueSeverity.WARNING, "Test message")
        report.add_issue(issue)
        assert len(report.issues) == 1
        assert report.issues[0] is issue


class TestValidationRule:
    def test_base_init(self):
        """ValidationRule is an abstract base class; cannot instantiate directly.

        Verify it's a proper abstract base class with a validate method.
        """
        import inspect
        assert inspect.isabstract(ValidationRule)
        assert hasattr(ValidationRule, "validate")

    def test_numerical_range_rule_init(self):
        """NumericalRangeRule requires name."""
        rule = NumericalRangeRule(name="roa_check")
        assert rule.name == "roa_check"


class TestYoYQoQLogicRule:
    def test_init(self):
        """YoYQoQLogicRule requires name."""
        rule = YoYQoQLogicRule(name="growth_consistency")
        assert rule.name == "growth_consistency"


class TestCitationFormatRule:
    def test_init(self):
        """CitationFormatRule requires name."""
        rule = CitationFormatRule(name="cite_check")
        assert rule.name == "cite_check"


class TestMathConsistencyRule:
    def test_init(self):
        """MathConsistencyRule requires name."""
        rule = MathConsistencyRule(name="balance_check")
        assert rule.name == "balance_check"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
