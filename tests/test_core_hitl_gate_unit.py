"""Unit tests for scripts/core/hitl_gate.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def hg():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import hitl_gate as h
    yield h
    if _p in sys.path:
        sys.path.remove(_p)


class TestGateState:
    def test_states(self, hg):
        assert hg.GateState.PENDING in hg.GateState
        assert hg.GateState.APPROVED in hg.GateState
        assert hg.GateState.REJECTED in hg.GateState


class TestApprovalRecord:
    def test_init(self, hg):
        r = hg.ApprovalRecord(
            gate_id="g1",
            stage="experiment_design",
        )
        assert r.gate_id == "g1"
        assert r.state == hg.GateState.PENDING
        assert r.feedback == ""
        assert r.decided_at is None
