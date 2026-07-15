"""Unit tests for scripts/core/prompt_evolution.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pe():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import prompt_evolution as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestPromptEvolutionRecord:
    def test_init(self, pe):
        rec = pe.PromptEvolutionRecord(
            timestamp=1000.0,
            agent_name="analyst",
            task_type="data_fetch",
            prompt="Fetch stock data",
            output="data loaded",
            quality=0.9,
        )
        assert rec.agent_name == "analyst"
        assert rec.quality == 0.9


class TestPromptEvolver:
    def test_init(self, pe):
        evolver = pe.PromptEvolver()
        assert evolver is not None
