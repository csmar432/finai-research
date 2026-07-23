"""Unit tests for scripts/core/agent_pipeline_lg.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def apl():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import agent_pipeline_lg as a
    yield a
    if _p in sys.path:
        sys.path.remove(_p)


class TestLangGraphPipeline:
    def test_init(self, apl):
        pipeline = apl.LangGraphPipeline(
            orchestrator=None,
            use_langgraph_runtime=False,
            checkpoint_dir="/tmp/checkpoints",
        )
        assert pipeline.checkpoint_dir == "/tmp/checkpoints"
        assert pipeline.use_langgraph_runtime is False
