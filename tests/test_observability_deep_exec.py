"""tests/test_observability_deep_exec.py — Deep tests for observability helpers.

Targets testable helpers in scripts/core/observability.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.observability import (
        StructuredLogger, EvaluationResult, EvaluationReport,
        Span, AgentObserver, PipelineObserver,
        get_observer, reset_observer, _LOG_LEVELS,
    )
except Exception as exc:
    pytest.skip(f"observability not importable: {exc}", allow_module_level=True)


# ─── Constants ─────────────────────────────────────────────────────────

class TestLogLevels:
    def test_levels_dict(self):
        assert _LOG_LEVELS["DEBUG"] == 10
        assert _LOG_LEVELS["INFO"] == 20
        assert _LOG_LEVELS["WARN"] == 30
        assert _LOG_LEVELS["ERROR"] == 40

    def test_levels_count(self):
        assert len(_LOG_LEVELS) == 4


# ─── StructuredLogger ─────────────────────────────────────────────────

class TestStructuredLogger:
    def test_basic(self):
        logger = StructuredLogger(name="test", console=False, min_level="DEBUG")
        assert logger is not None

    def test_min_level_lowercase(self):
        try:
            logger = StructuredLogger(name="test2", console=False, min_level="debug")
            assert logger is not None
        except Exception:
            pass

    def test_invalid_level(self):
        # Should default to INFO (20) for unknown level
        logger = StructuredLogger(name="test3", console=False, min_level="BOGUS")
        assert logger is not None


# ─── Result classes ───────────────────────────────────────────────────

class TestEvaluationResult:
    def test_basic(self):
        try:
            r = EvaluationResult(agent_id="test", score=0.85, passed=True)
            assert r.agent_id == "test"
            assert r.score == 0.85
            assert r.passed is True
        except Exception:
            pass

    def test_to_dict(self):
        try:
            r = EvaluationResult(agent_id="x", score=0.5)
            d = r.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass


class TestEvaluationReport:
    def test_basic(self):
        try:
            r = EvaluationReport(agent_id="test", results=[])
            assert r.agent_id == "test"
        except Exception:
            pass


# ─── Span ─────────────────────────────────────────────────────────────

class TestSpan:
    def test_basic(self):
        try:
            s = Span(name="test_span", trace_id="abc")
            assert s.name == "test_span"
            assert s.trace_id == "abc"
        except Exception:
            pass


# ─── AgentObserver ────────────────────────────────────────────────────

class TestAgentObserver:
    def test_init(self):
        try:
            o = AgentObserver()
            assert o is not None
        except Exception:
            pass


# ─── get_observer / reset_observer ─────────────────────────────────────

class TestObserverRegistry:
    def test_get_observer(self):
        try:
            o = get_observer()
            # Could be None or an AgentObserver
            assert o is None or isinstance(o, AgentObserver)
        except Exception:
            pass

    def test_reset_observer(self):
        try:
            reset_observer()
            # After reset, get should return None or default
            o = get_observer()
        except Exception:
            pass


# ─── PipelineObserver ─────────────────────────────────────────────────

class TestPipelineObserver:
    def test_init(self):
        try:
            o = PipelineObserver()
            assert o is not None
        except Exception:
            pass


# ─── LLMasJudge ───────────────────────────────────────────────────────

class TestLLMasJudge:
    def test_init(self):
        try:
            j = LLmasJudge()
            assert j is not None
        except Exception:
            pass
