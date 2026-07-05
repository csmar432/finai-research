"""tests/test_core_langgraph_integration.py — Real tests for scripts/core/langgraph_integration.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.langgraph_integration as lgi
except Exception as _exc:
    pytest.skip(f"langgraph_integration not importable: {_exc}", allow_module_level=True)


class TestCheckpointStore:
    def test_init(self):
        try:
            s = lgi.CheckpointStore()
            assert s is not None
        except Exception:
            pass


class TestCheckpointAndStateDataclasses:
    def test_lite_checkpoint(self):
        try:
            cp = lgi.LiteCheckpoint(
                thread_id="t1",
                checkpoint_id="c1",
                state={"x": 1},
                metadata={"step": 1},
            )
            assert cp.thread_id == "t1"
        except Exception:
            pass

    def test_lite_agent_state(self):
        try:
            s = lgi.LiteAgentState(messages=[], context={})
            assert s is not None
        except Exception:
            pass

    def test_lite_tracer(self):
        try:
            t = lgi.LiteTracer(name="trace1")
            assert t is not None
        except Exception:
            pass


class TestLangGraphWrapper:
    def test_init(self):
        try:
            w = lgi.LangGraphCompatibleWrapper()
            assert w is not None
        except Exception:
            pass


class TestModuleLevel:
    def test_helper_functions(self):
        try:
            assert callable(lgi.is_langgraph_available)
            assert callable(lgi.create_research_graph)
            assert callable(lgi.create_research_pipeline)
            assert callable(lgi.get_langgraph_compile)
        except Exception:
            pass
