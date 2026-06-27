"""Tests for DID Audit Guard (PR5, Audit 2026-06-27)."""

from __future__ import annotations

import os
import pandas as pd
import pytest

from scripts.core.did_audit_guard import (
    MockDataError,
    assert_real_data,
    audit_file,
    DataAuditResult,
    DID_AUDIT_ENABLED,
    _audit_dataframe,
)


# ─── Mock Data Fixtures ───────────────────────────────────────────────────────


def make_mock_df() -> pd.DataFrame:
    return pd.DataFrame({
        "firm": ["A", "B", "C", "D"],
        "year": [2018, 2019, 2020, 2021],
        "y": [1.0, 2.0, 3.0, 4.0],
        "_synthetic": [True, True, True, True],
    })


def make_mock_df_by_value() -> pd.DataFrame:
    return pd.DataFrame({
        "firm": ["A", "B", "C"],
        "year": [2018, 2019, 2020],
        "y": [1.0, 2.0, 3.0],
        "data_source": ["MOCK_DATA(DEMO)", "akshare", "tushare"],
    })


def make_real_df() -> pd.DataFrame:
    return pd.DataFrame({
        "firm": ["A", "B", "C", "D"],
        "year": [2018, 2019, 2020, 2021],
        "y": [1.0, 2.0, 3.0, 4.0],
        "provenance_id": ["prov-001", "prov-002", "prov-003", "prov-004"],
    })


def make_mixed_df() -> pd.DataFrame:
    return pd.DataFrame({
        "firm": ["A", "B"],
        "year": [2020, 2021],
        "y": [1.0, 2.0],
        "_mock": [True, False],
    })


# ─── Core Tests ────────────────────────────────────────────────────────────────


def test_real_data_passes():
    df = make_real_df()
    result = assert_real_data(df, "test")
    assert result.is_real is True


def test_synthetic_column_fails():
    df = make_mock_df()
    with pytest.raises(MockDataError):
        assert_real_data(df, "did_2x2")


def test_mock_value_in_source_column_fails():
    df = make_mock_df_by_value()
    with pytest.raises(MockDataError):
        assert_real_data(df, "cs_did")


def test_provenance_only_overrides_when_no_sentinel():
    df1 = pd.DataFrame({
        "firm": ["A"], "year": [2020], "y": [1.0],
        "provenance_id": ["prov-001"],
    })
    result1 = _audit_dataframe(df1, "test")
    assert result1.is_real is True
    assert result1.provenance_found is True

    df2 = pd.DataFrame({
        "firm": ["A"], "year": [2020], "y": [1.0],
        "_synthetic": [True],
        "provenance_id": ["prov-001"],
    })
    result2 = _audit_dataframe(df2, "test")
    assert result2.is_real is False
    assert result2.provenance_found is True


def test_mixed_mock_real_blocks():
    df = make_mixed_df()
    with pytest.raises(MockDataError):
        assert_real_data(df, "any_did")


def test_audit_result_has_recommendations():
    df = make_mock_df()
    result = _audit_dataframe(df, "test")
    assert len(result.recommendations) > 0


def test_raise_false_returns_result_not_exception():
    df = make_mock_df()
    result = assert_real_data(df, "test", raise_on_mock=False)
    assert result.is_real is False
    assert len(result.sentinel_columns) > 0


# ─── File-level Tests ──────────────────────────────────────────────────────────


def test_audit_file_nonexistent_returns_false(tmp_path):
    result = audit_file(tmp_path / "nonexistent.csv")
    assert result.is_real is False


def test_audit_csv_with_sentinel_blocks(tmp_path):
    csv_file = tmp_path / "mock_data.csv"
    df = make_mock_df()
    df.to_csv(csv_file, index=False)
    result = audit_file(csv_file)
    assert result.is_real is False
    assert "_synthetic" in result.sentinel_columns


def test_audit_csv_real_passes(tmp_path):
    csv_file = tmp_path / "real_data.csv"
    df = make_real_df()
    df.to_csv(csv_file, index=False)
    result = audit_file(csv_file)
    assert result.is_real is True


def test_audit_unsupported_format(tmp_path):
    txt_file = tmp_path / "data.txt"
    txt_file.write_text("a,b\n1,2\n")
    result = audit_file(txt_file)
    assert result.is_real is False


# ─── Sentinel Detection ───────────────────────────────────────────────────────


def test_detects_multiple_sentinel_columns():
    df = pd.DataFrame({
        "firm": ["A", "B"],
        "year": [2020, 2021],
        "y": [1.0, 2.0],
        "_synthetic": [True, True],
        "_mock": [True, True],
        "_sim": [True, True],
    })
    result = _audit_dataframe(df, "test")
    assert len(result.sentinel_columns) >= 3


def test_case_insensitive_sentinel_detection():
    df = pd.DataFrame({
        "firm": ["A"],
        "year": [2020],
        "y": [1.0],
        "_SYNTHETIC": [True],
    })
    result = _audit_dataframe(df, "test")
    assert len(result.sentinel_columns) > 0


def test_detects_mock_in_data_source():
    df = pd.DataFrame({
        "firm": ["A", "B"],
        "data_source": ["MOCK_DATA(DEMO)", "akshare"],
        "y": [1.0, 2.0],
    })
    result = _audit_dataframe(df, "test")
    assert len(result.data_source_values) > 0


# ─── Audit Guard Integration ─────────────────────────────────────────────────


def test_decorator_blocks_mock_call():
    from scripts.core.did_audit_guard import audit_did_call

    @audit_did_call
    def fake_did(df):
        return "DID result"

    df = make_mock_df()
    with pytest.raises(MockDataError):
        fake_did(df)


def test_decorator_allows_real_call():
    from scripts.core.did_audit_guard import audit_did_call

    @audit_did_call
    def fake_did(df):
        return "DID result"

    df = make_real_df()
    result = fake_did(df)
    assert result == "DID result"


def test_disabled_audit_reads_env_var():
    import scripts.core.did_audit_guard as dag
    old = dag.DID_AUDIT_ENABLED
    dag.DID_AUDIT_ENABLED = False
    os.environ["DID_AUDIT_ENABLED"] = "false"

    df = make_mock_df()
    result = dag.assert_real_data(df, "test", raise_on_mock=False)
    assert result.method == "disabled"

    dag.DID_AUDIT_ENABLED = old
    os.environ.pop("DID_AUDIT_ENABLED", None)


# ─── Error Message Quality ────────────────────────────────────────────────────


def test_mock_data_error_contains_context():
    df = make_mock_df()
    try:
        assert_real_data(df, "did_2x2")
        pytest.fail("Should have raised MockDataError")
    except MockDataError as e:
        msg = str(e)
        assert "did_2x2" in msg
        assert "synthetic" in msg.lower() or "mock" in msg.lower()
        assert "禁止" in msg or "正式" in msg or "演示" in msg
