"""Unit tests for scripts/core/user_data_merger.py.

Focused on dataclasses, helper functions, and class existence —
large module (444 lines) with pandas DataFrame logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def udm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import user_data_merger as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, udm):
        for name in [
            "SchemaValidationResult",
            "VariableSourceReport",
            "MergeResult",
            "_c",
            "_normalize",
            "_fuzzy_match",
        ]:
            assert hasattr(udm, name), f"Missing export: {name}"


class TestHelperFunctions:
    def test_c_colorizes(self, udm):
        result = udm._c("hello", "\033[91m")
        assert "hello" in result
        # Should contain color code and reset code
        assert "\033[91m" in result
        assert "\033[0m" in result

    def test_normalize_lowercase(self, udm):
        assert udm._normalize("ROA") == "roa"
        assert udm._normalize("RoA") == "roa"

    def test_normalize_canonical_mapping(self, udm):
        # leverage and debt_ratio both map to "leverage"
        assert udm._normalize("leverage") == "leverage"
        assert udm._normalize("debt_ratio") == "leverage"
        # rd → rd_intensity
        assert udm._normalize("rd") == "rd_intensity"
        assert udm._normalize("rd_intensity") == "rd_intensity"
        # patent → patent_count
        assert udm._normalize("patent") == "patent_count"

    def test_normalize_unknown(self, udm):
        assert udm._normalize("unknown_field_xyz") == "unknown_field_xyz"

    def test_fuzzy_match_exact(self, udm):
        matched, names = udm._fuzzy_match("roa", ["roa", "roe"])
        assert matched is True
        assert "roa" in names

    def test_fuzzy_match_no_match(self, udm):
        matched, names = udm._fuzzy_match("xyz_unique", ["abc", "def"])
        assert matched is False
        assert names == []

    def test_fuzzy_match_substring(self, udm):
        # "rd" is substring of "rd_intensity"
        matched, names = udm._fuzzy_match("rd", ["rd_intensity"])
        assert matched is True

    def test_find_canonical_for_chinese_known(self, udm):
        result = udm._find_canonical_for_chinese("资产负债率")
        assert "debt_ratio" in result or "leverage" in result

    def test_find_canonical_for_chinese_unknown(self, udm):
        result = udm._find_canonical_for_chinese("未知字段X")
        assert result == []

    def test_find_canonical_substring_match(self, udm):
        # "总资产" should match the "总资产" key
        result = udm._find_canonical_for_chinese("公司总资产")
        assert "total_assets" in result or "assets" in result


class TestSchemaValidationResult:
    def test_default_init(self, udm):
        r = udm.SchemaValidationResult()
        assert r.matched_columns == {}
        assert r.unmatched_columns == []
        assert r.unknown_columns == []
        assert r.suggestions == []
        assert r.confidence == 0.0
        assert r.file_name == ""

    def test_full_init(self, udm):
        r = udm.SchemaValidationResult(
            matched_columns={"TFP": "tfp_op"},
            unmatched_columns=["col_x"],
            unknown_columns=["Y_var"],
            suggestions=["map TFP → tfp_op"],
            confidence=0.85,
            file_name="data.csv",
        )
        assert r.matched_columns == {"TFP": "tfp_op"}
        assert r.confidence == 0.85
        assert r.file_name == "data.csv"


class TestVariableSourceReport:
    def test_required_init(self, udm):
        r = udm.VariableSourceReport(variable="TFP", source="akshare")
        assert r.variable == "TFP"
        assert r.source == "akshare"
        assert r.file_path == ""
        assert r.coverage_pct == 0.0
        assert r.row_count == 0
        assert r.is_simulated is False
        assert r.note == ""

    def test_full_init(self, udm):
        r = udm.VariableSourceReport(
            variable="TFP",
            source="user_file",
            file_path="/data/test.csv",
            coverage_pct=95.5,
            row_count=1000,
            is_simulated=True,
            note="partial match",
        )
        assert r.file_path == "/data/test.csv"
        assert r.coverage_pct == 95.5
        assert r.row_count == 1000
        assert r.is_simulated is True
        assert r.note == "partial match"


class TestMergeResult:
    def test_init(self, udm):
        import pandas as pd
        from scripts.research_framework.base import ProvenanceTracker

        df = pd.DataFrame({"a": [1, 2, 3]})
        tracker = ProvenanceTracker()
        r = udm.MergeResult(merged_df=df, tracker=tracker)
        assert r.merged_df is df
        assert r.tracker is tracker
        assert r.source_report == []
        assert r.unmet_variables == []
        assert r.user_files_used == []
        assert r.mcp_sources_used == []
        assert r.confidence == 0.0


class TestUserDataMerger:
    def test_class_exists(self, udm):
        assert udm.UserDataMerger is not None

    def test_init_default_root(self, udm):
        merger = udm.UserDataMerger()
        assert merger is not None
        assert merger.project_root.exists()
        assert merger.data_dir == merger.project_root / "data"

    def test_init_custom_root(self, udm, tmp_path):
        merger = udm.UserDataMerger(project_root=tmp_path)
        assert merger.project_root == tmp_path
        assert merger.data_dir == tmp_path / "data"


class TestUserDataSchemaValidator:
    def test_class_exists(self, udm):
        assert udm.UserDataSchemaValidator is not None


class TestKnownRealSources:
    def test_known_sources_set(self, udm):
        assert isinstance(udm._KNOWN_REAL_SOURCES, set)
        assert "tushare" in udm._KNOWN_REAL_SOURCES
        assert "akshare" in udm._KNOWN_REAL_SOURCES
        assert "yfinance" in udm._KNOWN_REAL_SOURCES
        assert "wind" in udm._KNOWN_REAL_SOURCES


class TestChineseMappings:
    def test_chinese_to_english_dict(self, udm):
        assert isinstance(udm._CHINESE_TO_ENGLISH, dict)
        assert "资产负债率" in udm._CHINESE_TO_ENGLISH
        assert "ROA" in udm._CHINESE_TO_ENGLISH or "roa" in udm._CHINESE_TO_ENGLISH
        assert "净利润" in udm._CHINESE_TO_ENGLISH


class TestQuickValidate:
    def test_quick_validate_callable(self, udm):
        assert callable(udm.quick_validate)
