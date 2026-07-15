"""Unit tests for scripts/paper_versioning.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pv():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import paper_versioning as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestVersionInfo:
    def test_init(self, pv):
        v = pv.VersionInfo(
            commit_hash="abc123",
            short_hash="abc1",
            message="Initial commit",
            author="Smith",
            timestamp="2024-01-01T00:00:00",
            files_changed=10,
        )
        assert v.commit_hash == "abc123"
        assert v.short_hash == "abc1"
        assert v.tags == []
        assert v.insertions == 0


class TestDiffInfo:
    def test_init(self, pv):
        d = pv.DiffInfo(
            old_version="v1",
            new_version="v2",
            files_changed=["main.tex"],
            hunks=[{"line": 1, "text": "diff"}],
        )
        assert d.old_version == "v1"
        assert d.new_version == "v2"


class TestPaperVersionControl:
    def test_init(self, pv):
        vcs = pv.PaperVersionControl()
        assert vcs is not None
