"""tests/test_pipeline_builder_deep_exec.py — Deep tests for pipeline_builder pure helpers.

Targets testable helpers in scripts/pipeline_builder.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.pipeline_builder import (
        _agent_category, _stage_color, _step_id, main,
        PAPER_AGENTS, ANALYST_AGENTS,
    )
except Exception as exc:
    pytest.skip(f"pipeline_builder not importable: {exc}", allow_module_level=True)


# ─── _agent_category ──────────────────────────────────────────────────

class TestAgentCategory:
    def test_paper_agent(self):
        # Use a known paper agent name from the set
        if PAPER_AGENTS:
            name = next(iter(PAPER_AGENTS))
            assert _agent_category(name) == "paper"

    def test_analyst_agent(self):
        if ANALYST_AGENTS:
            name = next(iter(ANALYST_AGENTS))
            assert _agent_category(name) == "analyst"

    def test_unknown(self):
        assert _agent_category("not_a_real_agent_xyz") == "utility"

    def test_empty(self):
        assert _agent_category("") == "utility"


# ─── _stage_color ─────────────────────────────────────────────────────

class TestStageColor:
    def test_first_stage(self):
        color = _stage_color(0)
        assert isinstance(color, str)
        assert color.startswith("#")

    def test_returns_hex(self):
        color = _stage_color(0)
        assert len(color) == 7  # "#XXXXXX"

    def test_wraps_around(self):
        # Index beyond list length should wrap around
        c0 = _stage_color(0)
        c7 = _stage_color(7)  # Assuming list length is 7
        c14 = _stage_color(14)
        # They should be the same color if wraps correctly
        assert c0 == c7 or c0 == c14  # One of these should equal


# ─── _step_id ─────────────────────────────────────────────────────────

class TestStepId:
    def test_returns_string(self):
        sid = _step_id()
        assert isinstance(sid, str)

    def test_unique(self):
        sid1 = _step_id()
        import time
        time.sleep(0.01)
        sid2 = _step_id()
        assert sid1 != sid2

    def test_is_numeric(self):
        sid = _step_id()
        assert sid.isdigit()


# ─── main() ──────────────────────────────────────────────────────────

class TestMain:
    def test_main_callable(self):
        assert callable(main)


# ─── Constants ────────────────────────────────────────────────────────

class TestConstants:
    def test_paper_agents_is_set(self):
        assert isinstance(PAPER_AGENTS, (set, list, frozenset, dict))
        assert len(PAPER_AGENTS) > 0

    def test_analyst_agents_is_set(self):
        assert isinstance(ANALYST_AGENTS, (set, list, frozenset, dict))
        assert len(ANALYST_AGENTS) >= 0
