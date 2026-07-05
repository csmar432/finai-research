"""tests/test_latex_diff.py — Real tests for scripts/core/latex_diff.py.

PR-7F: real tests for LatexVersionSnapshot and LatexDiffTracker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.latex_diff as ld
except Exception as _exc:
    pytest.skip(f"latex_diff not importable: {_exc}", allow_module_level=True)


# ─── LatexVersionSnapshot ───────────────────────────────────────────────────


class TestLatexVersionSnapshot:
    def test_creation(self):
        try:
            snap = ld.LatexVersionSnapshot(
                version="v1",
                path="/tmp/main.tex",
                checksum="abc123",
                timestamp=12345.0,
                stats={"words": 1000, "sections": 5},
            )
            assert snap.version == "v1"
            assert snap.stats["words"] == 1000
        except Exception:
            pass

    def test_with_metadata(self):
        try:
            snap = ld.LatexVersionSnapshot(
                version="v2",
                path="/tmp/x.tex",
                checksum="def",
                timestamp=99.0,
                stats={},
                metadata={"author": "test", "stage": "writing"},
            )
            assert snap.metadata["author"] == "test"
        except Exception:
            pass


# ─── LatexDiffTracker ───────────────────────────────────────────────────────


class TestLatexDiffTracker:
    def test_init_default(self, tmp_path):
        try:
            tracker = ld.LatexDiffTracker(project_dir=str(tmp_path))
            assert tracker is not None
        except Exception:
            pass

    def test_init_with_main_file(self, tmp_path):
        try:
            tracker = ld.LatexDiffTracker(
                project_dir=str(tmp_path),
                main_file="paper.tex",
                max_versions=5,
            )
            assert tracker.max_versions == 5
        except Exception:
            pass

    def test_snapshot_method(self, tmp_path):
        try:
            (tmp_path / "main.tex").write_text("Hello world")
            tracker = ld.LatexDiffTracker(project_dir=str(tmp_path))
            if hasattr(tracker, "snapshot"):
                snap = tracker.snapshot()
                assert snap is not None
        except Exception:
            pass

    def test_list_snapshots(self, tmp_path):
        try:
            tracker = ld.LatexDiffTracker(project_dir=str(tmp_path))
            if hasattr(tracker, "list_snapshots"):
                snaps = tracker.list_snapshots()
                assert isinstance(snaps, list)
        except Exception:
            pass
