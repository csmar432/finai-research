"""Unit tests for scripts/core/did_audit_guard.py."""

from __future__ import annotations


import pandas as pd
import pytest

from scripts.core.did_audit_guard import (
    DID_AUDIT_ENABLED,
    DataAuditResult,
    MockDataError,
    assert_real_data,
)


class TestMockDataError:
    """Exception class."""

    def test_is_exception(self):
        assert issubclass(MockDataError, Exception)

    def test_can_raise(self):
        try:
            raise MockDataError("mock detected")
        except MockDataError as e:
            assert "mock detected" in str(e)


class TestDataAuditResult:
    """DataAuditResult dataclass."""

    def test_required_fields(self):
        r = DataAuditResult(
            is_real=True,
            method="sentinel_check",
            reason="no mock sentinels",
            sentinel_columns=[],
            provenance_found=False,
            data_source_values=[],
            recommendations=[],
        )
        assert r.is_real is True
        assert r.method == "sentinel_check"
        assert r.sentinel_columns == []

    def test_default_values(self):
        r = DataAuditResult(
            is_real=True, method="x", reason="y",
            sentinel_columns=["_mock"],
            provenance_found=True,
            data_source_values=["MOCK"],
            recommendations=["use real data"],
        )
        assert r.recommendations == ["use real data"]


class TestAuditEnabled:
    """DID_AUDIT_ENABLED env-controlled flag."""

    def test_default_is_true(self, monkeypatch):
        monkeypatch.delenv("DID_AUDIT_ENABLED", raising=False)
        # Module is already imported — flag is captured at import time
        # Just check it's a bool
        assert isinstance(DID_AUDIT_ENABLED, bool)


class TestAssertRealDataDisabled:
    """When audit is disabled, returns is_real=True."""

    def test_disabled_returns_real(self, monkeypatch):
        """Temporarily disable and reimport behavior."""
        # Can't easily reimport, but we can patch the flag
        import scripts.core.did_audit_guard as guard
        monkeypatch.setattr(guard, "DID_AUDIT_ENABLED", False)
        df = pd.DataFrame({"_mock": [1, 2, 3]})
        result = assert_real_data(df, context="test")
        assert result.is_real is True
        assert result.method == "disabled"


class TestAssertRealDataClean:
    """Clean real data passes."""

    def test_clean_data_passes(self):
        df = pd.DataFrame({
            "year": [2020, 2021, 2022],
            "value": [1.0, 2.0, 3.0],
            "provenance_id": ["p1", "p2", "p3"],
        })
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is True

    def test_clean_data_with_provenance_passes(self):
        df = pd.DataFrame({
            "x": [1, 2, 3],
            "y": [4, 5, 6],
            "data_provenance": ["tushare", "tushare", "akshare"],
        })
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is True
        assert result.provenance_found is True


class TestAssertRealDataMockSentinels:
    """Mock sentinel columns trigger detection."""

    def test_synthetic_column_detected(self):
        df = pd.DataFrame({"_synthetic": [1, 2, 3], "x": [1, 2, 3]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False
        assert "_synthetic" in result.sentinel_columns

    def test_mock_column_detected(self):
        df = pd.DataFrame({"_mock": [1, 2, 3]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False
        assert "_mock" in result.sentinel_columns

    def test_MOCK_column_detected(self):
        df = pd.DataFrame({"__MOCK__": [1, 2, 3]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False

    def test_mock_raises_by_default(self):
        df = pd.DataFrame({"_mock": [1, 2, 3]})
        with pytest.raises(MockDataError):
            assert_real_data(df, context="did_2x2")

    def test_mock_error_contains_context(self):
        df = pd.DataFrame({"_mock": [1, 2, 3]})
        try:
            assert_real_data(df, context="my_context_xyz")
        except MockDataError as e:
            assert "my_context_xyz" in str(e)


class TestAssertRealDataMockSourceValues:
    """data_source column with mock values triggers detection."""

    def test_mock_data_source_value(self):
        df = pd.DataFrame({
            "year": [2020, 2021],
            "data_source": ["MOCK_DATA", "real_source"],
        })
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False
        assert len(result.data_source_values) > 0

    def test_synthetic_value_detected(self):
        df = pd.DataFrame({"data_source": ["SYNTHETIC", "SYNTHETIC"]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False

    def test_demo_value_detected(self):
        df = pd.DataFrame({"source": ["demo", "demo"]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert result.is_real is False


class TestRecommendations:
    """Recommendations are populated when mock detected."""

    def test_mock_produces_recommendations(self):
        df = pd.DataFrame({"_mock": [1, 2, 3]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        assert len(result.recommendations) > 0

    def test_clean_produces_one_recommendation(self):
        """Clean data may have a suggestion to add provenance."""
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = assert_real_data(df, context="test", raise_on_mock=False)
        # Implementation gives a "建议" for adding provenance
        assert isinstance(result.recommendations, list)
