"""Unit tests for scripts/econometrics.py (stub)."""

from __future__ import annotations


from scripts.econometrics import (
    DIDRegression,
    DiagnosticSuite,
    EvaluationResult,
    RegressionTable,
)


class TestRegressionTable:
    """RegressionTable stub dataclass."""

    def test_default_construct(self):
        r = RegressionTable()
        assert r.data is None

    def test_with_data(self):
        r = RegressionTable(data={"x": 1})
        assert r.data["x"] == 1


class TestDiagnosticSuite:
    """DiagnosticSuite stub dataclass."""

    def test_default_construct(self):
        d = DiagnosticSuite()
        assert d.data is None

    def test_with_data(self):
        d = DiagnosticSuite(data=[1, 2, 3])
        assert d.data == [1, 2, 3]


class TestDIDRegression:
    """DIDRegression stub dataclass."""

    def test_default_construct(self):
        d = DIDRegression()
        assert d.data is None


class TestEvaluationResult:
    """EvaluationResult stub dataclass — has specific fields."""

    def test_default_construct(self):
        e = EvaluationResult()
        assert e.score == 0.0
        assert e.recommendation == "Unknown"
        assert e.details == {}

    def test_with_data(self):
        e = EvaluationResult(score=0.9, recommendation="Approve", details={"x": 1})
        assert e.score == 0.9
        assert e.recommendation == "Approve"
        assert e.details["x"] == 1


class TestImportStubsAreAvailable:
    """Verify the stubs are importable (regression for deleted module)."""

    def test_imports_work(self):
        """Should be able to import all stub classes."""
        from scripts import econometrics
        assert hasattr(econometrics, "RegressionTable")
        assert hasattr(econometrics, "DiagnosticSuite")
        assert hasattr(econometrics, "DIDRegression")
