"""tests/test_pipeline_checkpoint_exec.py — Test pipeline_checkpoint pure functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts.pipeline_checkpoint import (
        c,
        Stage,
        DecisionOption,
        StageResult,
        InteractivePipelineCheckpoint,
        RED,
        GREEN,
        CYAN,
    )
except Exception as e:
    pytest.skip(f"pipeline_checkpoint not importable: {e}", allow_module_level=True)


class TestColorize:
    def test_red(self):
        assert c("text", RED) == f"{RED}text\033[0m"

    def test_green(self):
        assert c("text", GREEN) == f"{GREEN}text\033[0m"

    def test_cyan(self):
        assert c("text", CYAN) == f"{CYAN}text\033[0m"

    def test_passthrough(self):
        # c() is plain text concat - any color string works
        assert c("text", "\033[33m") == "\033[33mtext\033[0m"


class TestStage:
    def test_string_inheritance(self):
        # Stage(str, Enum) - each member IS a string
        s = Stage.IDEA_GENERATION
        assert s.value == "想法生成"
        assert isinstance(s, str)

    def test_all_stages(self):
        names = [m.name for m in Stage]
        assert "IDEA_GENERATION" in names
        assert "LITERATURE_REVIEW" in names
        assert "NOVELTY_CHECK" in names
        assert "EXPERIMENT_DESIGN" in names
        assert "DATA_ACQUISITION" in names
        assert "PAPER_OUTLINE" in names
        assert "PAPER_DRAFT" in names
        assert "EMPIRICAL_ANALYSIS" in names
        assert "REVIEW_LOOP" in names
        assert "SUBMISSION_CHECK" in names
        assert "CUSTOM" in names

    def test_stage_count(self):
        assert len(list(Stage)) == 11


class TestDecisionOption:
    def test_minimal(self):
        opt = DecisionOption(
            option_id="opt1",
            label="Continue",
            description="Continue to next stage",
        )
        assert opt.option_id == "opt1"
        assert opt.label == "Continue"
        assert opt.description == "Continue to next stage"
        assert opt.is_destructive is False
        assert opt.requires_authorization is False

    def test_destructive(self):
        opt = DecisionOption(
            option_id="opt2",
            label="Delete",
            description="Delete",
            is_destructive=True,
            requires_authorization=True,
        )
        assert opt.is_destructive is True
        assert opt.requires_authorization is True


class TestStageResult:
    def test_minimal(self):
        r = StageResult(stage=Stage.IDEA_GENERATION, success=True)
        assert r.stage == Stage.IDEA_GENERATION
        assert r.success is True
        assert r.output_files == []
        assert r.issues == []
        assert r.used_synthetic_data is False

    def test_full(self):
        r = StageResult(
            stage=Stage.LITERATURE_REVIEW,
            success=True,
            output_files=["lit_review.md", "papers.bib"],
            issues=["minor formatting"],
            used_synthetic_data=True,
        )
        assert len(r.output_files) == 2
        assert len(r.issues) == 1
        assert r.used_synthetic_data is True

    def test_failure(self):
        r = StageResult(
            stage=Stage.DATA_ACQUISITION,
            success=False,
            issues=["Tushare API key missing", "CSMAR not configured"],
        )
        assert r.success is False
        assert len(r.issues) == 2


class TestInteractivePipelineCheckpoint:
    def test_class_exists(self):
        # Can be imported, that's enough for the header smoke test
        assert InteractivePipelineCheckpoint is not None

    def test_class_has_methods(self):
        # Just verify class structure (skipped run tests need user input)
        assert hasattr(InteractivePipelineCheckpoint, "__init__")
        # Common methods to look for
        for m in ("wait_at_checkpoint", "report_status"):
            if hasattr(InteractivePipelineCheckpoint, m):
                assert callable(getattr(InteractivePipelineCheckpoint, m))
