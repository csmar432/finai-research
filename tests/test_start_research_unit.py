"""Unit tests for scripts/start_research.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def sr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import start_research as s
    yield s
    if _p in sys.path:
        sys.path.remove(_p)


class TestResearchProfile:
    def test_init(self, sr):
        profile = sr.ResearchProfile(topic="Carbon trading and innovation")
        assert profile.topic == "Carbon trading and innovation"
        assert profile.question_type == ""
        assert profile.venue == ""


class TestCommands:
    def test_cmd_new_research(self, sr):
        assert callable(sr.cmd_new_research)

    def test_cmd_resume(self, sr):
        assert callable(sr.cmd_resume)
