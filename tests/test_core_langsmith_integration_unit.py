"""Unit tests for scripts/core/langsmith_integration.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def li():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import langsmith_integration as l
    yield l
    if _p in sys.path:
        sys.path.remove(_p)


class TestLocalSpan:
    def test_init(self, li):
        span = li.LocalSpan(
            span_id="s1",
            trace_id="t1",
            name="llm_call",
            start_time=1234567890.0,
            end_time=1234567891.0,
        )
        assert span.span_id == "s1"
        assert span.name == "llm_call"
