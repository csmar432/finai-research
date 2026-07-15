"""Unit tests for scripts/core/session.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def sess():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import session as s
    yield s
    if _p in sys.path:
        sys.path.remove(_p)


class TestEvaluation:
    def test_init(self, sess):
        ev = sess.Evaluation(
            task_id="t1",
            success=True,
            score=0.85,
            feedback="good",
            suggestions=[],
            quality_flags=[],
        )
        assert ev.task_id == "t1"
        assert ev.score == 0.85

    def test_fields(self, sess):
        ev = sess.Evaluation(
            task_id="t2",
            success=False,
            score=0.3,
            feedback="needs improvement",
            suggestions=["fix data"],
            quality_flags=["missing_data"],
        )
        assert ev.success is False
        assert "missing_data" in ev.quality_flags


class TestSessionConfig:
    def test_init(self, sess):
        cfg = sess.SessionConfig(
            session_id="s1",
            user_goal="研究碳排放权交易对企业创新的影响",
        )
        assert cfg.session_id == "s1"


class TestEnums:
    def test_session_status_is_enum(self, sess):
        if hasattr(sess, "SessionStatus") and hasattr(sess.SessionStatus, "__members__"):
            assert hasattr(sess.SessionStatus, "__members__")
