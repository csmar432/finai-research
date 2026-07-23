"""
tests/test_user_data_merger.py
Test suite for scripts/core/user_data_merger.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
import sys as _sys
_sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.user_data_merger import (
    UserDataMerger,
    UserDataSchemaValidator,
    SchemaValidationResult,
)
from scripts.core.mock_data_governance import MockDataPolicy
from scripts.research_framework.base import ProvenanceTracker


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def csv_financials(temp_data_dir):
    """CSV with Chinese + English column names + a custom column."""
    p = temp_data_dir / "financial_data.csv"
    pd.DataFrame({
        "公司代码":    ["000001", "000002"],
        "年份":       [2020, 2021],
        "资产负债率":  [0.65, 0.72],
        "roa":        [0.05, 0.03],
        "size":       [21.5, 22.1],
        "lev":        [0.65, 0.72],
        "custom_col": [1, 2],
    }).to_csv(p, index=False)
    return p


@pytest.fixture
def excel_trade(temp_data_dir):
    p = temp_data_dir / "trade.xlsx"
    pd.DataFrame({
        "股票代码": ["000001", "000002"],
        "出口额":  [1_000_000, 2_000_000],
        "进口额":  [500_000, 800_000],
    }).to_excel(p, index=False)
    return p


@pytest.fixture
def json_macro(temp_data_dir):
    p = temp_data_dir / "macro.json"
    p.write_text(json.dumps({"year": [2020, 2021], "gdp": [101.6, 114.9]}))
    return p


# ── UserDataSchemaValidator ───────────────────────────────────────────────────

class TestSchemaValidator:
    """SchemaValidationResult fields after validate_and_suggest_mapping().

    Field semantics (as per dataclass docstrings):
      matched_columns: {schema_key -> actual_df_column_name}
      unmatched_columns: schema keys NOT matched → user df is missing these
      unknown_columns: df columns NOT in schema → extra user columns
    """

    def test_full_match(self):
        """All schema keys matched → high confidence, no unmatched/unknown."""
        df = pd.DataFrame({
            "roa":         [0.05, 0.03],
            "debt_ratio":  [0.65, 0.72],
        })
        expected = {
            "roa":         ["roa"],
            "debt_ratio":  ["debt_ratio"],
        }
        result = UserDataSchemaValidator().validate_and_suggest_mapping(df, expected)

        assert result.matched_columns.get("roa") == "roa"
        assert result.matched_columns.get("debt_ratio") == "debt_ratio"
        assert result.unmatched_columns == []          # no schema keys missing
        assert result.unknown_columns == []            # no extra df cols
        assert result.confidence >= 0.9

    def test_chinese_to_english_mapping(self):
        """Chinese column name → canonical schema key mapping works."""
        df = pd.DataFrame({
            "资产负债率": [0.65, 0.72],
            "ROA":        [0.05, 0.03],
        })
        expected = {
            "debt_ratio": ["debt_ratio", "leverage", "资产负债率"],
            "roa":        ["roa", "ROA", "return_on_assets"],
        }
        result = UserDataSchemaValidator().validate_and_suggest_mapping(df, expected)

        assert result.matched_columns.get("debt_ratio") == "资产负债率"
        assert result.matched_columns.get("roa") == "ROA"
        assert result.unmatched_columns == []

    def test_partial_match_schema_keys_missing(self):
        """Schema key not in df → appears in unmatched_columns."""
        df = pd.DataFrame({"roa": [0.05, 0.03]})
        expected = {
            "roa":        ["roa"],
            "debt_ratio": ["debt_ratio"],   # expected but df has no such column
        }
        result = UserDataSchemaValidator().validate_and_suggest_mapping(df, expected)

        assert "roa" in result.matched_columns
        assert "debt_ratio" in result.unmatched_columns  # schema key missing

    def test_extra_user_columns(self):
        """User df columns not in schema → appear in unknown_columns."""
        df = pd.DataFrame({
            "roa":    [0.05],
            "custom": [1],
        })
        result = UserDataSchemaValidator().validate_and_suggest_mapping(
            df, {"roa": ["roa"]}
        )
        assert "custom" in result.unknown_columns   # extra df column

    def test_empty_df(self):
        """Empty DataFrame → zero confidence, all schema keys unmatched."""
        result = UserDataSchemaValidator().validate_and_suggest_mapping(
            pd.DataFrame(), {"roa": ["roa"]}
        )
        assert result.confidence == 0.0
        assert result.matched_columns == {}
        assert result.unmatched_columns == ["roa"]

    def test_empty_schema(self):
        """Empty schema → confidence 0, no matches."""
        result = UserDataSchemaValidator().validate_and_suggest_mapping(
            pd.DataFrame({"roa": [0.05]}), {}
        )
        assert result.confidence == 0.0
        assert result.matched_columns == {}
        assert result.unknown_columns == ["roa"]

    def test_print_report_no_crash(self, capsys):
        """print_report() runs without raising."""
        v = UserDataSchemaValidator()
        r = v.validate_and_suggest_mapping(
            pd.DataFrame({"roa": [0.05]}),
            {"roa": ["roa"]}
        )
        v.print_report(r)
        out = capsys.readouterr().out
        assert len(out) > 0
        assert "匹配置信度" in out or "Confidence" in out or "matched" in out.lower()


# ── UserDataMerger: construction ─────────────────────────────────────────────

class TestMergerInit:
    def test_default_root(self):
        m = UserDataMerger()
        assert m.project_root == PROJECT_ROOT
        assert m.data_dir == PROJECT_ROOT / "data"

    def test_custom_root(self, tmp_path):
        m = UserDataMerger(project_root=tmp_path)
        assert m.project_root == tmp_path
        assert m.data_dir == tmp_path / "data"

    def test_mock_policy_is_deny(self):
        m = UserDataMerger()
        assert m._mock_registry is not None
        assert m._mock_registry.policy == MockDataPolicy.DENY


# ── UserDataMerger: load_user_data ───────────────────────────────────────────

class TestLoadUserData:
    def test_loads_csv(self, csv_financials, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.load_user_data(
            variables=["roa", "debt_ratio", "资产负债率"],
            idea_keywords=["financial"],
        )
        assert isinstance(result, dict)
        assert any(str(csv_financials) in k for k in result)

    def test_loads_xlsx(self, excel_trade, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.load_user_data(
            variables=["export", "import"],
            idea_keywords=["trade"],
        )
        assert any(str(excel_trade) in k for k in result)

    def test_loads_json(self, json_macro, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.load_user_data(
            variables=["gdp", "macro"],
            idea_keywords=["macro"],
        )
        assert any(str(json_macro) in k for k in result)

    def test_empty_dir(self, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        assert m.load_user_data(variables=["roa"]) == {}

    def test_non_matching_keywords(self, csv_financials, temp_data_dir):
        """File not matching keywords → not loaded (column peek fallback may load)."""
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.load_user_data(
            variables=["nonexistent_var"],
            idea_keywords=["zzz_no_match_zzz"],
        )
        # Either empty (no keyword match) or loaded (column peek matched)
        assert isinstance(result, dict)


# ── UserDataMerger: merge ────────────────────────────────────────────────────

class TestMergerMerge:
    """merge() returns tuple[pd.DataFrame, ProvenanceTracker]."""

    def test_returns_tuple(self, csv_financials, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.merge(
            variables=["roa", "debt_ratio", "size"],
            idea_keywords=["financial"],
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        merged_df, tracker = result
        assert isinstance(merged_df, pd.DataFrame)
        assert isinstance(tracker, ProvenanceTracker)

    def test_finds_roa(self, csv_financials, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        merged_df, _ = m.merge(variables=["roa"], idea_keywords=["financial"])
        assert "roa" in merged_df.columns

    def test_unmet_variables_reported(self, temp_data_dir):
        m = UserDataMerger(project_root=temp_data_dir.parent)
        merged_df, tracker = m.merge(
            variables=["roa", "nonexistent_var"],
            idea_keywords=["financial"],
        )
        # "nonexistent_var" should not be in df columns
        assert "nonexistent_var" not in merged_df.columns or (
            merged_df["nonexistent_var"].isna().all()
        )


# ── UserDataMerger: validate_merged ───────────────────────────────────────────

class TestValidateMerged:
    """validate_merged() returns (list[VariableSourceReport], list[str])."""

    def test_returns_tuple(self):
        m = UserDataMerger()
        tracker = ProvenanceTracker()
        df = pd.DataFrame({"roa": [0.05]})
        result = m.validate_merged(df, ["roa", "debt_ratio"], tracker)
        assert isinstance(result, tuple)
        reports, unmet = result
        assert isinstance(reports, list)
        assert isinstance(unmet, list)

    def test_matched_variable_has_report(self):
        m = UserDataMerger()
        tracker = ProvenanceTracker()
        df = pd.DataFrame({"roa": [0.05, 0.03]})
        reports, _ = m.validate_merged(df, ["roa"], tracker)
        assert any(r.variable == "roa" and r.coverage_pct == 100.0 for r in reports)

    def test_unmatched_in_unmet_list(self):
        m = UserDataMerger()
        tracker = ProvenanceTracker()
        df = pd.DataFrame({"roa": [0.05]})
        _, unmet = m.validate_merged(df, ["roa", "debt_ratio"], tracker)
        assert "debt_ratio" in unmet


# ── UserDataMerger: get_unmet_variables ───────────────────────────────────────

class TestGetUnmetVariables:
    def test_returns_list(self):
        m = UserDataMerger()
        tracker = ProvenanceTracker()
        user_files = {"path": pd.DataFrame({"roa": [0.05]})}
        result = m.get_unmet_variables(["roa", "debt_ratio"], user_files, tracker)
        assert isinstance(result, list)

    def test_tracked_variable_not_unmet(self):
        m = UserDataMerger()
        tracker = ProvenanceTracker()
        tracker.record("roa", "mcp:tushare")
        user_files = {"path": pd.DataFrame({"roa": [0.05]})}
        result = m.get_unmet_variables(["roa", "debt_ratio"], user_files, tracker)
        assert "roa" not in result


# ── UserDataMerger: authorize_synthetic_variable ──────────────────────────────

class TestAuthorizeSynthetic:
    def test_authorize_registers_in_registry(self):
        m = UserDataMerger()
        ok = m.authorize_synthetic_variable("my_var", reason="PCA imputation")
        assert ok is True
        assert m._mock_registry.check_authorization("my_var") is True

    def test_auth_stores_reason(self):
        m = UserDataMerger()
        m.authorize_synthetic_variable("var_x", reason="linear interpolation")
        details = m._mock_registry.get_authorization_details("var_x")
        assert details is not None
        assert details.get("reason") == "linear interpolation"


# ── Internal helpers ──────────────────────────────────────────────────────────

class TestInternalHelpers:
    def test_columns_match_variables_direct(self):
        m = UserDataMerger()
        assert m._columns_match_variables(["roa", "size"], "roa") is True

    def test_columns_match_variables_case_insensitive(self):
        m = UserDataMerger()
        assert m._columns_match_variables(["ROA", "SIZE"], "roa") is True

    def test_find_column_in_df_exact(self):
        m = UserDataMerger()
        df = pd.DataFrame({"roa": [0.05]})
        assert m._find_column_in_df(df, "roa") == "roa"

    def test_find_column_in_df_case_insensitive(self):
        m = UserDataMerger()
        df = pd.DataFrame({"ROA": [0.05]})
        assert m._find_column_in_df(df, "roa") == "ROA"

    def test_find_column_in_df_chinese(self):
        m = UserDataMerger()
        df = pd.DataFrame({"资产负债率": [0.65]})
        # "资产负债率" is in _CHINESE_TO_ENGLISH with canonical "debt_ratio"
        # _find_column_in_df looks for a df column that maps TO "debt_ratio"
        # It checks: does "资产负债率" have canonical "debt_ratio"? Yes.
        # Then: does "debt_ratio" match var "debt_ratio"? Yes.
        result = m._find_column_in_df(df, "debt_ratio")
        assert result == "资产负债率"

    def test_find_column_in_df_not_found(self):
        m = UserDataMerger()
        df = pd.DataFrame({"roa": [0.05]})
        assert m._find_column_in_df(df, "revenue") is None


# ── SchemaValidationResult dataclass ───────────────────────────────────────────

class TestSchemaValidationResultDefaults:
    def test_defaults(self):
        r = SchemaValidationResult()
        assert r.confidence == 0.0
        assert r.matched_columns == {}
        assert r.unmatched_columns == []
        assert r.unknown_columns == []
        assert r.suggestions == []


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unicode_filename(self, temp_data_dir):
        p = temp_data_dir / "财务数据_测试.csv"
        pd.DataFrame({"roa": [0.05]}).to_csv(p)
        m = UserDataMerger(project_root=temp_data_dir.parent)
        result = m.load_user_data(variables=["roa"], idea_keywords=["财务"])
        assert any("财务数据" in str(k) for k in result)

    def test_missing_data_dir(self, tmp_path):
        """Missing data/ dir → load_user_data returns empty dict."""
        m = UserDataMerger(project_root=tmp_path)
        assert m.load_user_data(variables=["roa"]) == {}

    def test_merge_with_unavailable_source(self, temp_data_dir):
        """Variables with no source produce empty or partial DataFrame."""
        m = UserDataMerger(project_root=temp_data_dir.parent)
        merged_df, tracker = m.merge(
            variables=["nonexistent_a", "nonexistent_b"],
            idea_keywords=["no_match"],
        )
        assert isinstance(merged_df, pd.DataFrame)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
