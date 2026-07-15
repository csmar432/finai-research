"""Unit tests for scripts/pipeline_checkpoint.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import pipeline_checkpoint as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestStage:
    def test_stages(self, pc):
        assert pc.Stage.IDEA_GENERATION in pc.Stage
        assert pc.Stage.LITERATURE_REVIEW in pc.Stage


class TestDecisionOption:
    def test_init(self, pc):
        opt = pc.DecisionOption(
            option_id="opt1",
            label="Approve",
            description="Continue with current plan",
            is_destructive=False,
            requires_authorization=False,
        )
        assert opt.option_id == "opt1"
        assert opt.is_destructive is False


class TestStageResult:
    def test_init(self, pc):
        r = pc.StageResult(
            stage=pc.Stage.IDEA_GENERATION,
            success=True,
        )
        assert r.success is True
        assert r.output_files == []
        assert r.used_synthetic_data is False
