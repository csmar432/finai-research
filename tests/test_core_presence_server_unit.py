"""Unit tests for scripts/core/presence_server.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ps():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import presence_server as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestPresenceEvent:
    def test_init(self, ps):
        event = ps.PresenceEvent(
            event_type="edit",
            paper_id="p1",
            user_id="u1",
            section="abstract",
            cursor_position=42,
        )
        assert event.event_type == "edit"
        assert event.metadata == {}
