"""Unit tests for scripts/core/time_travel.py."""
from __future__ import annotations

import sys, time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def tt():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import time_travel as t
    yield t
    if _p in sys.path:
        sys.path.remove(_p)


class TestDataclasses:
    def test_state_snapshot_default(self, tt):
        snap = tt.StateSnapshot(
            snapshot_id="s1",
            agent_id="a1",
            timestamp=1000.0,
            state_type="running",
            state_data={"step": 1},
        )
        assert snap.snapshot_id == "s1"
        assert snap.parent_snapshot_id is None
        assert snap.metadata == {}

    def test_state_snapshot_full(self, tt):
        snap = tt.StateSnapshot(
            snapshot_id="s2",
            agent_id="a2",
            timestamp=2000.0,
            state_type="decision",
            state_data={"x": 1},
            parent_snapshot_id="s1",
            metadata={"tag": "test"},
        )
        assert snap.parent_snapshot_id == "s1"
        assert snap.metadata["tag"] == "test"

    def test_decision_record(self, tt):
        rec = tt.DecisionRecord(
            decision_id="d1",
            agent_id="a1",
            timestamp=3000.0,
            decision_point="choose_model",
            options=[{"model": "gpt4"}, {"model": "claude"}],
            chosen=0,
            reasoning="faster",
            context={"speed": 1},
        )
        assert rec.chosen == 0
        assert len(rec.options) == 2

    def test_execution_trace(self, tt):
        snap = tt.StateSnapshot("s1", "a1", 1000.0, "running", {})
        trace = tt.ExecutionTrace(
            trace_id="t1",
            agent_id="a1",
            start_time=1000.0,
            end_time=2000.0,
            snapshots=[snap],
            decisions=[],
            final_state={"result": "ok"},
        )
        assert trace.trace_id == "t1"
        assert len(trace.snapshots) == 1

    def test_execution_trace_with_none_end(self, tt):
        trace = tt.ExecutionTrace(
            trace_id="t2",
            agent_id="a2",
            start_time=500.0,
            end_time=None,
            snapshots=[],
            decisions=[],
            final_state=None,
        )
        assert trace.end_time is None
        assert trace.final_state is None


class TestDebuggerInit:
    def test_init_default(self, tt):
        dbg = tt.TimeTravelDebugger()
        assert dbg.db_path is not None
        # db_path should be a Path or string
        assert str(dbg.db_path)

    def test_init_with_custom_db(self, tt, tmp_path):
        db_path = tmp_path / "custom.db"
        dbg = tt.TimeTravelDebugger(db_path=str(db_path))
        assert str(dbg.db_path) == str(db_path)


class TestSnapshotOperations:
    def test_take_and_get_snapshot(self, tt):
        dbg = tt.TimeTravelDebugger()
        snap = dbg.take_snapshot("agent1", "running", {"k": "v"})
        assert snap.snapshot_id is not None
        assert snap.state_data["k"] == "v"
        retrieved = dbg.get_snapshot(snap.snapshot_id)
        assert retrieved is not None
        assert retrieved.snapshot_id == snap.snapshot_id

    def test_get_nonexistent_snapshot(self, tt):
        dbg = tt.TimeTravelDebugger()
        assert dbg.get_snapshot("nonexistent") is None


class TestDecisionOperations:
    def test_record_and_get_decisions(self, tt):
        dbg = tt.TimeTravelDebugger()
        rec = dbg.record_decision(
            "a1", "pick_model", [{"id": 1}], 0, "first"
        )
        assert rec is not None
        assert rec.decision_point == "pick_model"
        decisions = dbg.get_decisions()
        assert len(decisions) >= 1


class TestTraceOperations:
    def test_start_and_get_trace(self, tt):
        dbg = tt.TimeTravelDebugger()
        trace_id = dbg.start_trace("agent1")
        assert trace_id is not None
        retrieved = dbg.get_trace(trace_id)
        assert retrieved is not None
        assert retrieved.trace_id == trace_id

    def test_end_trace(self, tt):
        dbg = tt.TimeTravelDebugger()
        trace_id = dbg.start_trace("agent2")
        dbg.end_trace(final_state={"result": "done"})
        retrieved = dbg.get_trace(trace_id)
        assert retrieved is not None
        assert retrieved.end_time is not None

    def test_get_nonexistent_trace(self, tt):
        dbg = tt.TimeTravelDebugger()
        assert dbg.get_trace("nonexistent") is None


class TestAnalysis:
    def test_analyze_trace(self, tt):
        dbg = tt.TimeTravelDebugger()
        trace_id = dbg.start_trace("a1")
        result = dbg.analyze_trace(trace_id)
        assert result is not None
        assert "total_snapshots" in result or "total_decisions" in result

    def test_analyze_nonexistent_trace(self, tt):
        dbg = tt.TimeTravelDebugger()
        result = dbg.analyze_trace("nonexistent")
        assert result is not None
