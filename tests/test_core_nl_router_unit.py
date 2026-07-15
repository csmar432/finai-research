"""Unit tests for scripts/core/nl_router.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def nl():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import nl_router as n
    yield n
    if _p in sys.path:
        sys.path.remove(_p)


class TestNLCapability:
    def test_exists(self, nl):
        assert hasattr(nl, "NLCapability")
        assert nl.NLCapability is not None


class TestNLExecutionResult:
    def test_init(self, nl):
        r = nl.NLExecutionResult(
            plans=[],
            dataframe=None,
            raw_results={},
            summary="Test summary",
            total_time_ms=100.0,
        )
        assert r.summary == "Test summary"
        assert r.total_time_ms == 100.0


class TestToolCallPlan:
    def test_init(self, nl):
        cap = nl.NLCapability("data_fetch", "Fetch data")
        plan = nl.ToolCallPlan(
            step_id="s1",
            capability=cap,
            args={"ticker": "000001.SZ"},
        )
        assert plan.step_id == "s1"
        assert plan.description == ""
        assert plan.mode == "sequential"
