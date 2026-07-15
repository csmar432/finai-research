"""Unit tests for scripts/core/llm_gateway.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def lg():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import llm_gateway as l
    yield l
    if _p in sys.path:
        sys.path.remove(_p)


class TestCostStats:
    def test_init(self, lg):
        stats = lg.CostStats()
        assert stats.total_calls == 0
        assert stats.total_cost_usd == 0.0


class TestLLMCallResult:
    def test_init(self, lg):
        r = lg.LLMCallResult(
            response="Test response",
            model_used="deepseek-chat",
            model_key="deepseek",
            task_type="research",
            latency_ms=500,
        )
        assert r.response == "Test response"
        assert r.cached is False
        assert r.tokens_used == 0


class TestMCPResult:
    def test_init(self, lg):
        r = lg.MCPResult(
            success=True,
            data={"key": "value"},
            error=None,
            server="user-tushare",
            tool="get_daily_quote",
            latency_ms=200.0,
        )
        assert r.success is True
        assert r.server == "user-tushare"
        assert r.is_mock is False
