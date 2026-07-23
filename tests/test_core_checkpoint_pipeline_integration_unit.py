"""Unit tests for scripts/core/checkpoint_pipeline_integration.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def cpi():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import checkpoint_pipeline_integration as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, cpi):
        for name in [
            "CheckpointedEnhancedPipeline",
            "CheckpointCLI",
            "checkpoint_resume",
        ]:
            assert hasattr(cpi, name), f"Missing export: {name}"


class TestCheckpointedEnhancedPipeline:
    def test_init_defaults(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        assert pipeline.config == {}
        assert pipeline.enable_checkpoint is True
        assert pipeline.checkpoint_dir == "data/checkpoints"
        assert pipeline.checkpoint_every == 1
        assert pipeline.auto_resume is True
        assert pipeline._on_gate_approved is None
        assert pipeline._checkpoint_manager is None
        assert pipeline._pipeline is None

    def test_init_with_config(self, cpi):
        cfg = {"topic": "test", "language": "en"}
        pipeline = cpi.CheckpointedEnhancedPipeline(
            config=cfg,
            enable_checkpoint=False,
            checkpoint_dir="/tmp/cp_test",
            checkpoint_every=5,
            auto_resume=False,
        )
        assert pipeline.config == cfg
        assert pipeline.enable_checkpoint is False
        assert pipeline.checkpoint_dir == "/tmp/cp_test"
        assert pipeline.checkpoint_every == 5
        assert pipeline.auto_resume is False

    def test_init_with_callback(self, cpi):
        cb = lambda x: x
        pipeline = cpi.CheckpointedEnhancedPipeline(on_gate_approved=cb)
        assert pipeline._on_gate_approved is cb

    def test_sanitise_id(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        assert pipeline._sanitise_id("my_pipeline") == "my_pipeline"
        assert pipeline._sanitise_id("my pipeline") == "my_pipeline"
        assert pipeline._sanitise_id("my/pipeline") == "my_pipeline"
        assert pipeline._sanitise_id("my.pipeline") == "my.pipeline"
        # Chinese chars stay as-is (or are sanitized; just ensure no crash)
        sanitized = pipeline._sanitise_id("中文测试")
        assert isinstance(sanitized, str)
        assert len(sanitized) >= 1

    def test_get_default_steps(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        steps = pipeline._get_default_steps("test topic")
        assert isinstance(steps, list)
        assert "literature_review" in steps
        assert "paper_draft" in steps

    def test_make_result(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        ctx = {"topic": "t", "result_x": "ok"}
        sr = {"stage1": {"result": "done"}}
        result = pipeline._make_result(ctx, sr, "my_pipe")
        assert result["pipeline_name"] == "my_pipe"
        assert result["context"] == ctx
        assert result["stage_results"] == sr
        assert result["completed"] is True
        assert "timestamp" in result

    def test_get_econ_gate_questions(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        # Known stages return non-default questions
        assert "数据质量审核" in pipeline._get_econ_gate_question("load_data")
        assert "DID" in pipeline._get_econ_gate_question("modern_did")
        assert "稳健性" in pipeline._get_econ_gate_question("robustness")
        assert "LaTeX" in pipeline._get_econ_gate_question("latex_and_validation")
        # Unknown step returns generic question
        generic = pipeline._get_econ_gate_question("unknown_step_xyz")
        assert "unknown_step_xyz" in generic

    def test_build_step_content_empty(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        # Use a simple object without ctx attribute
        class FakePipeline:
            pass
        content = pipeline._build_step_content("test_step", {"topic": "carbon"}, FakePipeline())
        assert content["step"] == "test_step"
        assert content["topic"] == "carbon"

    def test_build_step_content_with_ctx(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        import pandas as pd

        class FakePipeline:
            class ctx:
                df = pd.DataFrame({"a": [1, 2, 3]})
                modern_did_results = {"r1": 1.0}
                robustness_report = {"rb1": 2.0}
        content = pipeline._build_step_content(
            "test", {"topic": "t"}, FakePipeline()
        )
        assert content["n_obs"] == 3
        assert content["n_did_results"] == 1
        assert content["n_robustness"] == 1

    def test_collect_hitl_state_returns_none_when_no_manager(self, cpi, monkeypatch):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        # When agent_state is unavailable, the try/except returns None
        # We don't want to actually import it if not available, but the
        # method swallows exceptions, so it should return None safely.
        result = pipeline._collect_hitl_state()
        # Either None (no pending or import failed) or dict
        assert result is None or isinstance(result, dict)

    def test_make_result_timestamp_is_float(self, cpi):
        pipeline = cpi.CheckpointedEnhancedPipeline()
        result = pipeline._make_result({}, {}, "p")
        assert isinstance(result["timestamp"], float)


class TestCheckpointCLI:
    def test_init(self, cpi):
        cli = cpi.CheckpointCLI()
        assert cli.checkpoint_dir == "data/checkpoints"
        assert cli.manager is not None

    def test_init_custom_dir(self, cpi):
        cli = cpi.CheckpointCLI(checkpoint_dir="/tmp/cp_test_dir")
        assert cli.checkpoint_dir == "/tmp/cp_test_dir"

    def test_sanitise(self, cpi):
        cli = cpi.CheckpointCLI()
        assert cli._sanitise("my_pipe") == "my_pipe"
        assert cli._sanitise("my pipe") == "my_pipe"

    def test_format_time(self, cpi):
        cli = cpi.CheckpointCLI()
        formatted = cli._format_time(1700000000.0)
        assert isinstance(formatted, str)
        # Should look like YYYY-MM-DD HH:MM:SS
        assert len(formatted) == 19
        assert formatted[4] == "-"
        assert formatted[10] == " "


class TestConvenienceFunctions:
    def test_checkpoint_resume_callable(self, cpi):
        assert callable(cpi.checkpoint_resume)

    def test_checkpoint_list_callable(self, cpi):
        # Note: not in __all__ but should exist as a sibling function
        assert hasattr(cpi, "checkpoint_list")
        assert callable(cpi.checkpoint_list)
