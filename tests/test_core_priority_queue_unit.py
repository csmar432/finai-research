"""Unit tests for scripts/core/priority_queue.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pq():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import priority_queue as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestGateTask:
    def test_init(self, pq):
        task = pq.GateTask(
            gate_id="g1",
            priority=pq.Priority.P1_HIGH,
        )
        assert task.gate_id == "g1"
        assert task.attempts == 0
        assert task.deadline is None
        assert task.metadata == {}


class TestPriorityQueueStats:
    def test_init(self, pq):
        stats = pq.PriorityQueueStats()
        assert stats.total_enqueued == 0
        assert stats.avg_wait_seconds == 0.0


class TestPriorityGateQueue:
    def test_init(self, pq):
        q = pq.PriorityGateQueue()
        assert q is not None
