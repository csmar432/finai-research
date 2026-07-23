"""Unit tests for scripts/core/latex_diff.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ld():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import latex_diff as l
    yield l
    if _p in sys.path:
        sys.path.remove(_p)


class TestLatexVersionSnapshot:
    def test_init(self, ld):
        snap = ld.LatexVersionSnapshot(
            version="v1",
            path="/tmp/paper.tex",
            checksum="abc123",
            timestamp=1234567890.0,
            stats={"lines": 100},
        )
        assert snap.version == "v1"
        assert snap.metadata == {}


class TestLatexDiffTracker:
    def test_init(self, ld, tmp_path):
        tracker = ld.LatexDiffTracker(project_dir=str(tmp_path))
        assert tracker is not None
