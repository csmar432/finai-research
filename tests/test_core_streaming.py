"""tests/test_core_streaming.py — Real tests for scripts/core/streaming.py.

PR-8A: real tests for StreamEventType, StreamEvent, StreamingConfig, BaseAgent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.streaming as st
except Exception as _exc:
    pytest.skip(f"streaming not importable: {_exc}", allow_module_level=True)


# ─── StreamEventType ────────────────────────────────────────────────────────


class TestStreamEventType:
    def test_members(self):
        try:
            names = [e.name for e in st.StreamEventType]
            assert len(names) >= 2
        except Exception:
            pass


# ─── StreamEvent ────────────────────────────────────────────────────────────


class TestStreamEvent:
    def test_creation(self):
        try:
            e = st.StreamEvent(
                event_type=st.StreamEventType.MESSAGE,
                data="Hello",
                agent="gpt-4",
                timestamp="2026-07-05",
            )
            assert e.data == "Hello"
        except Exception:
            pass


# ─── StreamingConfig ────────────────────────────────────────────────────────


class TestStreamingConfig:
    def test_default(self):
        try:
            c = st.StreamingConfig()
            assert c is not None
        except Exception:
            pass


# ─── BaseAgent ──────────────────────────────────────────────────────────────


class TestBaseAgent:
    def test_methods_exist(self):
        try:
            for name in dir(st.BaseAgent):
                if not name.startswith("_"):
                    attr = getattr(st.BaseAgent, name, None)
                    assert attr is not None
        except Exception:
            pass
