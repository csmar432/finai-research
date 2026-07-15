"""Unit tests for scripts/ai_router.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ar():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import ai_router as a
    yield a
    if _p in sys.path:
        sys.path.remove(_p)


class TestAIResult:
    def test_init(self, ar):
        r = ar.AIResult(
            response="Analysis complete",
            model_used="gpt-4",
            model_key="openai",
            task_type="analysis",
            latency_ms=1500.0,
        )
        assert r.response == "Analysis complete"
        assert r.latency_ms == 1500.0


class TestLLMCallResult:
    def test_init(self, ar):
        r = ar.LLMCallResult(
            content="Research paper summary",
            model="gpt-4",
            provider="openai",
            latency_ms=2000.0,
            tokens_used=500,
        )
        assert r.content == "Research paper summary"
        assert r.tokens_used == 500


class TestCacheManager:
    def test_init(self, ar):
        cm = ar.CacheManager()
        assert cm is not None
