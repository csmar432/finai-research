"""Unit tests for scripts/paper_full_pipeline.py.

Covers: load_empirical_data, build_paper_prompt, generate_paper, de_ai_polish,
generate_word, _launch_dashboard, main, _fallback_csv_data, _get_from_keychain,
_KEYCHAIN_MAP, constants (PROJECT_ROOT, OUTPUT_DIR, CACHE_DIR, DE_AI_PROMPT,
TARIFF_RESULTS).
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pfp():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import paper_full_pipeline as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_project_root_is_path(self, pfp):
        assert isinstance(pfp.PROJECT_ROOT, Path)

    def test_output_dir_is_path(self, pfp):
        assert isinstance(pfp.OUTPUT_DIR, Path)

    def test_cache_dir_is_path(self, pfp):
        assert isinstance(pfp.CACHE_DIR, Path)

    def test_tariff_results_is_path(self, pfp):
        assert isinstance(pfp.TARIFF_RESULTS, Path)

    def test_de_ai_prompt_nonempty_string(self, pfp):
        assert isinstance(pfp.DE_AI_PROMPT, str)
        assert len(pfp.DE_AI_PROMPT) > 100

    def test_de_ai_prompt_mentions_ai_removal(self, pfp):
        # Should explicitly mention AI writing removal
        assert "AI" in pfp.DE_AI_PROMPT or "去AI" in pfp.DE_AI_PROMPT or "润色" in pfp.DE_AI_PROMPT


class TestKeychainMap:
    def test_keychain_map_is_dict(self, pfp):
        assert isinstance(pfp._KEYCHAIN_MAP, dict)

    def test_keychain_map_has_deepseek(self, pfp):
        assert "DEEPSEEK_API_KEY" in pfp._KEYCHAIN_MAP

    def test_keychain_map_values_are_tuples(self, pfp):
        for v in pfp._KEYCHAIN_MAP.values():
            assert isinstance(v, tuple)
            assert len(v) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════


class TestKeychainReader:
    def test_get_from_keychain_callable(self, pfp):
        assert callable(pfp._get_from_keychain)

    def test_get_from_keychain_returns_none_for_missing(self, pfp):
        # Non-existent service should return None
        result = pfp._get_from_keychain("nonexistent_service_xyz", "nonexistent_account")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Step functions
# ═══════════════════════════════════════════════════════════════════════════


class TestStepFunctions:
    def test_load_empirical_data_callable(self, pfp):
        assert callable(pfp.load_empirical_data)

    def test_load_empirical_data_signature(self, pfp):
        sig = inspect.signature(pfp.load_empirical_data)
        # No required args (returns dict)
        assert len([p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]) == 0

    def test_build_paper_prompt_signature(self, pfp):
        sig = inspect.signature(pfp.build_paper_prompt)
        assert "data" in sig.parameters

    def test_generate_paper_callable(self, pfp):
        assert callable(pfp.generate_paper)

    def test_generate_paper_signature(self, pfp):
        sig = inspect.signature(pfp.generate_paper)
        assert "data" in sig.parameters
        assert "use_cache" in sig.parameters

    def test_de_ai_polish_callable(self, pfp):
        assert callable(pfp.de_ai_polish)

    def test_de_ai_polish_signature(self, pfp):
        sig = inspect.signature(pfp.de_ai_polish)
        assert "paper" in sig.parameters
        assert "use_cache" in sig.parameters

    def test_generate_word_signature(self, pfp):
        sig = inspect.signature(pfp.generate_word)
        assert "paper" in sig.parameters

    def test_launch_dashboard_callable(self, pfp):
        assert callable(pfp._launch_dashboard)


# ═══════════════════════════════════════════════════════════════════════════
# build_paper_prompt behavior
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildPaperPrompt:
    def test_empty_data_returns_string(self, pfp):
        data = {
            "descriptive_md": "",
            "core_findings_md": "",
            "did_summary_md": "",
            "heterogeneity_md": "",
            "mediation_md": "",
        }
        result = pfp.build_paper_prompt(data)
        assert isinstance(result, str)
        assert len(result) > 500
        # Should contain structural hints
        assert "论文" in result or "摘要" in result

    def test_data_appears_in_prompt(self, pfp):
        data = {
            "descriptive_md": "TABLE_DESC_MARKER",
            "core_findings_md": "CORE_FINDINGS_MARKER",
            "did_summary_md": "DID_SUMMARY_MARKER",
            "heterogeneity_md": "HET_MARKER",
            "mediation_md": "MED_MARKER",
        }
        result = pfp.build_paper_prompt(data)
        assert "TABLE_DESC_MARKER" in result
        assert "CORE_FINDINGS_MARKER" in result
        assert "DID_SUMMARY_MARKER" in result
        assert "HET_MARKER" in result
        assert "MED_MARKER" in result

    def test_prompt_contains_structural_sections(self, pfp):
        data = {
            "descriptive_md": "",
            "core_findings_md": "",
            "did_summary_md": "",
            "heterogeneity_md": "",
            "mediation_md": "",
        }
        result = pfp.build_paper_prompt(data)
        # Should reference standard paper sections
        assert "摘要" in result or "abstract" in result.lower()
        assert "结论" in result or "稳健性" in result


# ═══════════════════════════════════════════════════════════════════════════
# Fallback CSV data loader
# ═══════════════════════════════════════════════════════════════════════════


class TestFallbackCsvData:
    def test_function_exists(self, pfp):
        assert callable(pfp._fallback_csv_data)

    def test_returns_dict(self, pfp):
        result = pfp._fallback_csv_data()
        assert isinstance(result, dict)
        # Either empty (no legacy CSVs) or contains expected keys
        if result:
            assert any(k in result for k in [
                "core_findings_md",
                "did_summary_md",
                "heterogeneity_md",
                "mediation_md",
                "descriptive_md",
                "robustness_md",
            ])


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


class TestMain:
    def test_function_exists(self, pfp):
        assert callable(pfp.main)

    def test_main_signature(self, pfp):
        sig = inspect.signature(pfp.main)
        # Should take no required args
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        assert len(required) == 0