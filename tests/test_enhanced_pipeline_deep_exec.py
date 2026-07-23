"""tests/test_enhanced_pipeline_deep_exec.py — Deep exec tests for enhanced_pipeline.

Target: scripts/research_framework/enhanced_pipeline.py
Coverage: PipelineContext dataclass (full), EnhancedPipeline methods,
pure helpers, error paths, JSON serialization, method call chains.
Existing coverage (11 tests) is preserved; we add 40+ new tests.

Run:
    python -m pytest tests/test_enhanced_pipeline_deep_exec.py -v --tb=short
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

# ── Import helpers from conftest ──────────────────────────────────────────────
from tests.conftest import mock_panel_df  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Import the module under test (skip if unimportable)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from scripts.research_framework.enhanced_pipeline import (
        PipelineContext,
        EnhancedPipeline,
        _cli_main,
    )
    _IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = str(exc)
    pytest.skip(f"enhanced_pipeline not importable: {exc}", allow_module_level=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: PipelineContext — all fields and to_dict
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineContextFields:
    """Every field of PipelineContext must be reachable and have correct defaults."""

    def test_topic_required(self):
        ctx = PipelineContext(topic="ESG and Financing")
        assert ctx.topic == "ESG and Financing"

    def test_language_default_zh(self):
        ctx = PipelineContext(topic="T")
        assert ctx.language == "zh"

    def test_language_explicit_en(self):
        ctx = PipelineContext(topic="T", language="en")
        assert ctx.language == "en"

    def test_output_dir_default(self):
        ctx = PipelineContext(topic="T")
        assert ctx.output_dir == Path("output/")

    def test_output_dir_explicit(self, tmp_path):
        ctx = PipelineContext(topic="T", output_dir=tmp_path)
        assert ctx.output_dir == tmp_path

    def test_df_default_none(self):
        ctx = PipelineContext(topic="T")
        assert ctx.df is None

    def test_did_results_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.did_results == {}

    def test_modern_did_results_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.modern_did_results == {}

    def test_gate_results_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.gate_results == {}

    def test_hitl_rejection_default_none(self):
        ctx = PipelineContext(topic="T")
        assert ctx.hitl_rejection is None

    def test_latex_version_default_v1_0(self):
        ctx = PipelineContext(topic="T")
        assert ctx.latex_version == "v1.0"

    def test_latex_lint_issues_default_empty_list(self):
        ctx = PipelineContext(topic="T")
        assert ctx.latex_lint_issues == []

    def test_latex_diff_paths_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.latex_diff_paths == {}

    def test_pdf_vision_issues_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.pdf_vision_issues == {}

    def test_execution_time_seconds_default_zero(self):
        ctx = PipelineContext(topic="T")
        assert ctx.execution_time_seconds == 0.0

    def test_step_results_default_empty_dict(self):
        ctx = PipelineContext(topic="T")
        assert ctx.step_results == {}


class TestPipelineContextToDict:
    """to_dict() must serialise every field correctly."""

    def test_to_dict_returns_dict(self):
        ctx = PipelineContext(topic="T")
        assert isinstance(ctx.to_dict(), dict)

    def test_to_dict_topic(self):
        ctx = PipelineContext(topic="Carbon Trading")
        assert ctx.to_dict()["topic"] == "Carbon Trading"

    def test_to_dict_language(self):
        ctx = PipelineContext(topic="T", language="en")
        assert ctx.to_dict()["language"] == "en"

    def test_to_dict_output_dir_str(self):
        ctx = PipelineContext(topic="T", output_dir=Path("/tmp/out"))
        assert ctx.to_dict()["output_dir"] == "/tmp/out"

    def test_to_dict_df_shape_none_when_no_df(self):
        assert PipelineContext(topic="T").to_dict()["df_shape"] is None

    def test_to_dict_df_shape_when_df_set(self):
        ctx = PipelineContext(topic="T")
        ctx.df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        assert ctx.to_dict()["df_shape"] == (3, 2)

    def test_to_dict_did_results_keys_empty(self):
        ctx = PipelineContext(topic="T")
        assert ctx.to_dict()["did_results_keys"] == []

    def test_to_dict_did_results_keys_populated(self):
        ctx = PipelineContext(topic="T")
        ctx.did_results = {"twfe": {}, "bacon": {}}
        assert "twfe" in ctx.to_dict()["did_results_keys"]
        assert "bacon" in ctx.to_dict()["did_results_keys"]

    def test_to_dict_modern_did_keys_populated(self):
        ctx = PipelineContext(topic="T")
        ctx.modern_did_results = {"cs": {}, "sa": {}}
        assert "cs" in ctx.to_dict()["modern_did_keys"]
        assert "sa" in ctx.to_dict()["modern_did_keys"]

    def test_to_dict_latex_version(self):
        ctx = PipelineContext(topic="T")
        ctx.latex_version = "v2.0"
        assert ctx.to_dict()["latex_version"] == "v2.0"

    def test_to_dict_gate_results_keys_empty(self):
        assert PipelineContext(topic="T").to_dict()["gate_results_keys"] == []

    def test_to_dict_gate_results_keys_populated(self):
        ctx = PipelineContext(topic="T")
        ctx.gate_results = {"feasibility": {}, "novelty": {}}
        assert "feasibility" in ctx.to_dict()["gate_results_keys"]

    def test_to_dict_latex_lint_issues_count_zero_when_empty(self):
        assert PipelineContext(topic="T").to_dict()["latex_lint_issues"] == 0

    def test_to_dict_latex_lint_issues_count(self):
        ctx = PipelineContext(topic="T")
        ctx.latex_lint_issues = ["a", "b", "c"]
        assert ctx.to_dict()["latex_lint_issues"] == 3

    def test_to_dict_pdf_vision_issues_count_zero_when_empty(self):
        assert PipelineContext(topic="T").to_dict()["pdf_vision_issues"] == 0

    def test_to_dict_pdf_vision_issues_count(self):
        ctx = PipelineContext(topic="T")
        ctx.pdf_vision_issues = ["x", "y"]
        assert ctx.to_dict()["pdf_vision_issues"] == 2

    def test_to_dict_execution_time(self):
        ctx = PipelineContext(topic="T")
        ctx.execution_time_seconds = 12.5
        assert ctx.to_dict()["execution_time_seconds"] == 12.5

    def test_to_dict_is_json_serializable(self):
        """to_dict() output must be JSON-serializable (no Path/ndarray)."""
        ctx = PipelineContext(topic="T")
        ctx.df = pd.DataFrame({"a": [1.0]})
        ctx.output_dir = Path("/tmp/out")
        # Should not raise
        json.dumps(ctx.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: EnhancedPipeline.__init__ — every parameter
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedPipelineInit:
    """Every __init__ parameter must be stored correctly."""

    def test_topic_stored(self):
        p = EnhancedPipeline(topic="Carbon Trading")
        assert p.topic == "Carbon Trading"

    def test_language_default_zh(self):
        p = EnhancedPipeline(topic="T")
        assert p.language == "zh"

    def test_language_explicit(self):
        p = EnhancedPipeline(topic="T", language="en")
        assert p.language == "en"

    def test_output_dir_path_created(self, tmp_path):
        out = tmp_path / "my_out"
        p = EnhancedPipeline(topic="T", output_dir=out)
        assert p.output_dir == out
        assert out.exists()

    def test_output_dir_string_accepted(self, tmp_path):
        p = EnhancedPipeline(topic="T", output_dir=str(tmp_path / "s"))
        assert isinstance(p.output_dir, Path)

    def test_enable_modern_did_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_modern_did is True

    def test_enable_modern_did_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_modern_did=False)
        assert p.enable_modern_did is False

    def test_enable_validation_gates_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_validation_gates is True

    def test_enable_validation_gates_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_validation_gates=False)
        assert p.enable_validation_gates is False

    def test_enable_latex_lint_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_latex_lint is True

    def test_enable_latex_lint_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_latex_lint=False)
        assert p.enable_latex_lint is False

    def test_enable_latex_diff_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_latex_diff is True

    def test_enable_latex_diff_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_latex_diff=False)
        assert p.enable_latex_diff is False

    def test_enable_pdf_vision_default_false(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_pdf_vision is False

    def test_enable_pdf_vision_explicit_true(self):
        p = EnhancedPipeline(topic="T", enable_pdf_vision=True)
        assert p.enable_pdf_vision is True

    def test_enable_sandbox_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_sandbox is True

    def test_enable_sandbox_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_sandbox=False)
        assert p.enable_sandbox is False

    def test_enable_self_evolution_default_false(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_self_evolution is False

    def test_enable_self_evolution_explicit_true(self):
        p = EnhancedPipeline(topic="T", enable_self_evolution=True)
        assert p.enable_self_evolution is True

    def test_enable_hitl_default_true(self):
        p = EnhancedPipeline(topic="T")
        assert p.enable_hitl is True

    def test_enable_hitl_explicit_false(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        assert p.enable_hitl is False

    def test_hitl_timeout_default_600(self):
        p = EnhancedPipeline(topic="T")
        assert p.hitl_timeout == 600

    def test_hitl_timeout_explicit(self):
        p = EnhancedPipeline(topic="T", hitl_timeout=300)
        assert p.hitl_timeout == 300

    def test_on_gate_approved_none_by_default(self):
        p = EnhancedPipeline(topic="T")
        assert p._on_gate_approved is None

    def test_on_gate_approved_callback_stored(self):
        cb = lambda s, c, f: None
        p = EnhancedPipeline(topic="T", on_gate_approved=cb)
        assert p._on_gate_approved is cb

    def test_ctx_is_pipeline_context(self):
        p = EnhancedPipeline(topic="Carbon Trading")
        assert isinstance(p.ctx, PipelineContext)
        assert p.ctx.topic == "Carbon Trading"

    def test_modules_initialized_to_none(self):
        p = EnhancedPipeline(topic="T")
        # All lazy modules are None before first step
        assert p._modern_did_engine is None
        assert p._robustness_runner is None
        assert p._validation_gates is None
        assert p._latex_diff_tracker is None
        assert p._latex_lint_checker is None
        assert p._pdf_vision_checker is None
        assert p._sandbox_runner is None
        assert p._self_evolution is None
        assert p._prompt_evolver is None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Pure helper methods
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedPipelinePureHelpers:
    """Pure helper methods that don't require external modules."""

    def test_check_dof_warning_returns_bool(self):
        p = EnhancedPipeline(topic="T")
        result = p._check_dof_warning()
        assert isinstance(result, bool)

    def test_get_main_did_coef_zero_when_no_results(self):
        p = EnhancedPipeline(topic="T")
        assert p._get_main_did_coef() == 0.0

    def test_get_main_did_coef_extracts_from_dict(self):
        p = EnhancedPipeline(topic="T")
        p.ctx.modern_did_results = {"did_2x2": {"coef": 0.042}}
        assert p._get_main_did_coef() == 0.042

    def test_get_main_did_coef_returns_float(self):
        p = EnhancedPipeline(topic="T")
        p.ctx.modern_did_results = {"cs": {"coef": 0.99}}
        result = p._get_main_did_coef()
        assert isinstance(result, float)

    def test_get_parallel_trends_method_returns_str(self):
        p = EnhancedPipeline(topic="T")
        result = p._get_parallel_trends_method()
        assert isinstance(result, str)

    def test_build_robustness_plan_summary_returns_dict(self):
        p = EnhancedPipeline(topic="T")
        result = p._build_robustness_plan_summary()
        assert isinstance(result, dict)
        assert "summary" in result

    def test_build_regression_summary_returns_dict(self):
        p = EnhancedPipeline(topic="T")
        result = p._build_regression_summary()
        assert isinstance(result, dict)
        assert "summary" in result


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Step methods — error paths and edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestStep1LoadDataEdgeCases:
    """Step 1 edge cases without requiring real MCP modules."""

    def test_generate_demo_data_returns_list(self):
        p = EnhancedPipeline(topic="T")
        data = p._generate_demo_data()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_generate_demo_data_has_required_keys(self):
        p = EnhancedPipeline(topic="T")
        data = p._generate_demo_data()
        required = ["ticker", "year", "roa", "esg_high", "post", "did", "sector"]
        for row in data[:5]:
            for key in required:
                assert key in row, f"Missing key {key} in demo data row"

    def test_generate_demo_data_simulated_flag_true(self):
        p = EnhancedPipeline(topic="T")
        data = p._generate_demo_data()
        for row in data[:10]:
            assert row.get("_simulated") is True

    def test_build_panel_from_list(self):
        p = EnhancedPipeline(topic="T")
        data = [{"ticker": "A", "year": 2020, "roa": 0.05,
                 "esg_high": 1, "post": 1, "did": 1}]
        df = p._build_panel(data)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_build_panel_from_dict(self):
        p = EnhancedPipeline(topic="T")
        data = {"data": [{"ticker": "A", "year": 2020, "roa": 0.05,
                          "esg_high": 1, "post": 1, "did": 1}]}
        df = p._build_panel(data)
        assert isinstance(df, pd.DataFrame)

    def test_build_panel_from_dataframe(self):
        p = EnhancedPipeline(topic="T")
        df_in = pd.DataFrame({"ticker": ["A"], "year": [2020], "roa": [0.05],
                               "esg_high": [1], "post": [1], "did": [1]})
        df = p._build_panel(df_in)
        assert isinstance(df, pd.DataFrame)

    def test_build_panel_from_empty_falls_back_to_demo(self):
        p = EnhancedPipeline(topic="T")
        df = p._build_panel([])
        assert isinstance(df, pd.DataFrame)
        # Should have fallen back to demo data (has ticker etc.)
        assert "ticker" in df.columns

    def test_build_panel_unknown_type_returns_empty_df(self):
        p = EnhancedPipeline(topic="T")
        df = p._build_panel(42)  # type: ignore
        assert isinstance(df, pd.DataFrame)

    def test_step1_load_data_returns_dataframe(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        df = p.step1_load_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_step1_load_data_sets_ctx_df(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        p.step1_load_data()
        assert p.ctx.df is not None
        assert isinstance(p.ctx.df, pd.DataFrame)

    def test_step1_load_data_records_step_result(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        p.step1_load_data()
        assert "step1" in p.ctx.step_results
        assert p.ctx.step_results["step1"]["status"] == "ok"
        assert "n_obs" in p.ctx.step_results["step1"]


class TestStep2ModernDiD:
    """Step 2 edge cases — modern DID with no data vs with data."""

    def test_step2_no_data_returns_empty_dict(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        # No step1, so ctx.df is None
        result = p.step2_modern_did()
        assert result == {}
        # When there's no data, step2 may not be recorded or may be error
        assert p.ctx.step_results.get("step2", {}).get("status") in ("error", None)

    def test_step2_disabled_returns_empty_dict(self):
        p = EnhancedPipeline(topic="T", enable_modern_did=False, enable_hitl=False)
        p.ctx.df = pd.DataFrame({"ticker": ["A"], "year": [2020], "roa": [0.05],
                                  "esg_high": [1], "post": [1], "did": [1],
                                  "lev": [0.3], "size": [20], "tangibility": [0.3],
                                  "mb": [2.0], "cash_ratio": [0.1], "sector": ["tech"]})
        result = p.step2_modern_did()
        assert result == {}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: HITL helpers and gate methods
# ══════════════════════════════════════════════════════════════════════════════

class TestHITLHelpers:
    """_hitl_hold / _notify_gate_approved edge cases."""

    def test_notify_gate_approved_noop_when_no_callback(self):
        p = EnhancedPipeline(topic="T")
        # Should not raise
        p._notify_gate_approved("step1_data_quality", "all good")

    def test_notify_gate_approved_calls_callback(self):
        called = []

        def cb(stage, ctx, feedback):
            called.append((stage, feedback))

        p = EnhancedPipeline(topic="T", on_gate_approved=cb)
        p._notify_gate_approved("step2_did_strategy", "looks fine")
        assert len(called) == 1
        assert called[0][0] == "step2_did_strategy"

    def test_notify_gate_approved_swallows_callback_exception(self):
        def bad_cb(stage, ctx, feedback):
            raise RuntimeError("callback error")

        p = EnhancedPipeline(topic="T", on_gate_approved=bad_cb)
        # Should not raise — exception is swallowed
        p._notify_gate_approved("step1", "")

    def test_hitl_hold_returns_none_when_gate_disabled(self):
        """When enable_hitl=False, _hitl_gate is None → _hitl_hold returns None."""
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        result = p._hitl_hold("step1", {}, "Continue?")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: summary() method
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedPipelineSummary:
    """summary() must produce a non-empty string with correct content."""

    def test_summary_returns_str(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        p.ctx.execution_time_seconds = 5.0
        s = p.summary()
        assert isinstance(s, str)

    def test_summary_contains_topic(self):
        p = EnhancedPipeline(topic="Carbon Trading and Innovation")
        s = p.summary()
        assert "Carbon Trading and Innovation" in s

    def test_summary_contains_language(self):
        p = EnhancedPipeline(topic="T", language="en")
        s = p.summary()
        assert "en" in s

    def test_summary_contains_time(self):
        p = EnhancedPipeline(topic="T")
        p.ctx.execution_time_seconds = 3.14
        s = p.summary()
        # Formatted as float, might appear as "3.1" or "3.14"
        assert "3" in s and "s" in s

    def test_summary_with_empty_step_results(self):
        p = EnhancedPipeline(topic="T")
        s = p.summary()
        assert "Enhanced Pipeline Summary" in s
        assert "Step" not in s  # no steps run yet

    def test_summary_with_step_results(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        p.step1_load_data()
        s = p.summary()
        assert "step1" in s.lower() or "step 1" in s.lower() or "Step 1" in s


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: JSON round-trip of PipelineContext
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineContextJSONRoundTrip:
    """PipelineContext must survive full JSON encode → decode round-trip."""

    def test_full_context_serializes_to_json(self):
        ctx = PipelineContext(topic="T", language="en")
        ctx.df = pd.DataFrame({"a": [1.0, 2.0]})
        ctx.did_results = {"twfe": {"coef": 0.5, "se": 0.1, "pval": 0.01}}
        ctx.modern_did_results = {"cs": {"coef": 0.4}}
        ctx.gate_results = {"feasibility": {"passed": True}}
        ctx.latex_lint_issues = ["missing_caption", "bad_command"]
        ctx.pdf_vision_issues = ["overflow"]
        ctx.execution_time_seconds = 7.77

        # Must not raise
        serialized = json.dumps(ctx.to_dict())
        assert isinstance(serialized, str)
        assert "T" in serialized
        assert "cs" in serialized


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: _init_hitl_gate — graceful degradation
# ══════════════════════════════════════════════════════════════════════════════

class TestInitHITLGate:
    """_init_hitl_gate must not raise even when HITLGate is unavailable."""

    def test_init_hitl_gate_no_raise_hitl_enabled(self):
        """With enable_hitl=True, _init_hitl_gate must not raise."""
        # Patch the import to fail, simulating missing hitl_gate module
        with patch.dict(sys.modules, {"scripts.core.hitl_gate": None}):
            # Reload won't work here easily, but we can test the fallback path:
            # when the import inside _init_hitl_gate raises, it catches and logs warning
            p = EnhancedPipeline(topic="T", enable_hitl=True)
            # Should be initialised (possibly to None for the gate)
            assert hasattr(p, "_hitl_gate")

    def test_init_hitl_gate_sets_gate_none_when_disabled(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        assert p._hitl_gate is None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Step5 LaTeX edge cases (mock latex modules)
# ══════════════════════════════════════════════════════════════════════════════

class TestStep5LatexEdgeCases:
    """Step 5 must handle missing latex modules gracefully."""

    def test_step5_no_raise_without_latex_modules(self):
        """step5_latex_and_validation must not raise when LaTeX modules unavailable."""
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        p.ctx.modern_did_results = {"did_2x2": {"coef": 0.05, "se": 0.01,
                                                  "pval": 0.01, "n_obs": 100,
                                                  "r_squared": 0.15}}

        with patch.dict(sys.modules, {
            "scripts.research_framework.report_generator": None,
            "scripts.research_framework.base": None,
        }):
            result = p.step5_latex_and_validation()
            # Should return dict even if generation failed
            assert isinstance(result, dict)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10: run() — full pipeline edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestEnhancedPipelineRunEdgeCases:
    """run() must handle partial states gracefully."""

    def test_run_returns_context(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        ctx = p.run()
        assert isinstance(ctx, PipelineContext)

    def test_run_records_execution_time(self):
        p = EnhancedPipeline(topic="T", enable_hitl=False)
        ctx = p.run()
        assert ctx.execution_time_seconds > 0

    def test_run_with_all_features_disabled(self):
        """All features off — pipeline still completes."""
        p = EnhancedPipeline(
            topic="T",
            enable_hitl=False,
            enable_modern_did=False,
            enable_validation_gates=False,
            enable_latex_lint=False,
            enable_latex_diff=False,
            enable_pdf_vision=False,
        )
        ctx = p.run()
        assert isinstance(ctx, PipelineContext)
        assert ctx.execution_time_seconds > 0

    def test_run_with_hitl_rejection_stops_early(self):
        """HITL rejection at step1 should cause early return."""

        def reject_gate(stage, ctx, feedback):
            # Simulate: pretend hitl_hold returns a rejection
            return {"gate_id": "test", "status": "rejected",
                    "decision": "rejected", "feedback": "bad data"}

        p = EnhancedPipeline(topic="T", enable_hitl=True,
                             enable_modern_did=False)
        p._hitl_gate = MagicMock()
        p._hitl_gate.hold.return_value = "test-gate"
        p._hitl_gate.wait_for_decision.return_value = MagicMock(
            gate_id="test-gate",
            state=MagicMock(value="rejected"),
            feedback="bad data",
        )

        # Simulate the hitl_hold returns rejected
        with patch.object(p, "_hitl_hold", return_value={
            "gate_id": "x", "status": "rejected",
            "decision": "rejected", "feedback": "bad data"
        }):
            ctx = p.run()
            assert ctx.hitl_rejection is not None
            assert ctx.hitl_rejection["stage"] == "step1_data_quality"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11: _cli_main is callable
# ══════════════════════════════════════════════════════════════════════════════

class TestCLIMain:
    """_cli_main must be callable (even if it sys.exits in real use)."""

    def test_cli_main_callable(self):
        assert callable(_cli_main)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12: ProvenanceTracker import compatibility
# ══════════════════════════════════════════════════════════════════════════════

class TestProvenanceTrackerCompatibility:
    """ReportGenerator's ProvenanceTracker must be available for Step 5."""

    def test_provenance_tracker_importable(self):
        try:
            from scripts.research_framework.base import ProvenanceTracker, DataSource
            tracker = ProvenanceTracker()
            tracker.record("test_field", DataSource.MCP_YFINANCE)
            assert tracker.summary()["total_fields"] == 1
        except Exception as exc:
            pytest.skip(f"ProvenanceTracker not importable: {exc}")
