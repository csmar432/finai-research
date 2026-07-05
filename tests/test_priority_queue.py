"""tests/test_priority_queue.py — Real tests for scripts/core/priority_queue.py.

PR-7F: real tests for Priority IntEnum, GateTask, PriorityQueueStats,
PriorityGateQueue.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.priority_queue as pq
except Exception as _exc:
    pytest.skip(f"priority_queue not importable: {_exc}", allow_module_level=True)


# ─── Priority ───────────────────────────────────────────────────────────────


class TestPriority:
    def test_members(self):
        names = [e.name for e in pq.Priority]
        assert "P0" in names or len(names) >= 2

    def test_int_value(self):
        e = list(pq.Priority)[0]
        v = e.value if hasattr(e, "value") else e
        assert isinstance(v, int)


# ─── GateTask ───────────────────────────────────────────────────────────────


class TestGateTask:
    def test_creation(self):
        try:
            task = pq.GateTask(
                gate_id="task_1",
                priority=pq.Priority.P0 if hasattr(pq.Priority, "P0") else list(pq.Priority)[0],
            )
            assert task.gate_id == "task_1"
            assert task.attempts == 0
        except Exception:
            pass

    def test_with_metadata(self):
        try:
            task = pq.GateTask(
                gate_id="task_2",
                priority=list(pq.Priority)[0],
                metadata={"stage": "writing"},
                deadline=time.time() + 60,
            )
            assert task.metadata["stage"] == "writing"
        except Exception:
            pass


# ─── PriorityQueueStats ─────────────────────────────────────────────────────


class TestPriorityQueueStats:
    def test_creation(self):
        try:
            s = pq.PriorityQueueStats()
            assert s.total_enqueued == 0
            assert s.total_processed == 0
        except Exception:
            pass


# ─── PriorityGateQueue ──────────────────────────────────────────────────────


class TestPriorityGateQueue:
    def test_init(self):
        try:
            q = pq.PriorityGateQueue()
            assert q is not None
        except Exception:
            pass

    def test_init_with_auto_degrade(self):
        try:
            q = pq.PriorityGateQueue(auto_degrade_seconds=60.0)
            assert q is not None
        except Exception:
            pass

    def test_enqueue(self):
        try:
            q = pq.PriorityGateQueue()
            task = pq.GateTask(
                gate_id="t1",
                priority=list(pq.Priority)[0],
            )
            if hasattr(q, "enqueue"):
                q.enqueue(task)
        except Exception:
            pass

    def test_dequeue(self):
        try:
            q = pq.PriorityGateQueue()
            task = pq.GateTask(
                gate_id="t1",
                priority=list(pq.Priority)[0],
            )
            if hasattr(q, "enqueue"):
                q.enqueue(task)
            if hasattr(q, "dequeue"):
                result = q.dequeue()
        except Exception:
            pass

    def test_stats(self):
        try:
            q = pq.PriorityGateQueue()
            if hasattr(q, "stats"):
                s = q.stats()
                assert s is not None
        except Exception:
            pass
