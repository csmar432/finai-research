"""Unit tests for scripts/paper_submitter.py."""
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
    from scripts import paper_submitter as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestSubmission:
    def test_init(self, ps):
        sub = ps.Submission(
            submission_id="sub1",
            paper_title="Carbon Trading and Innovation",
            venue="JF",
            status="draft",
        )
        assert sub.submission_id == "sub1"
        assert sub.submitted_at is None
        assert sub.files == {}
