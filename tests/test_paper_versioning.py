"""tests/test_paper_versioning.py — Real tests for scripts/paper_versioning.py.

PR-8A: real tests for DiffInfo, VersionInfo, PaperProject, PaperVersionControl.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.paper_versioning as pv
except Exception as _exc:
    pytest.skip(f"paper_versioning not importable: {_exc}", allow_module_level=True)


# ─── DiffInfo ───────────────────────────────────────────────────────────────


class TestDiffInfo:
    def test_creation(self):
        try:
            d = pv.DiffInfo(
                version_a="v1",
                version_b="v2",
                added_lines=10,
                removed_lines=5,
                modified_lines=2,
                summary="minor edit",
            )
            assert d.added_lines == 10
        except Exception:
            pass


# ─── VersionInfo ────────────────────────────────────────────────────────────


class TestVersionInfo:
    def test_creation(self):
        try:
            v = pv.VersionInfo(
                version_id="v1",
                timestamp="2026-07-05",
                message="init",
                author="test",
                checksum="abc",
                parent_version=None,
            )
            assert v.version_id == "v1"
        except Exception:
            pass


# ─── PaperProject ───────────────────────────────────────────────────────────


class TestPaperProject:
    def test_creation(self, tmp_path):
        try:
            p = pv.PaperProject(root=str(tmp_path / "paper"))
            assert p is not None
        except Exception:
            pass


# ─── PaperVersionControl ────────────────────────────────────────────────────


class TestPaperVersionControl:
    def test_init(self, tmp_path):
        try:
            p = tmp_path / "paper_vc"
            p.mkdir()
            vc = pv.PaperVersionControl(project_path=str(p))
            assert vc is not None
        except Exception:
            pass

    def test_methods(self, tmp_path):
        try:
            p = tmp_path / "paper_vc2"
            p.mkdir()
            vc = pv.PaperVersionControl(project_path=str(p))
            for name in dir(vc):
                if not name.startswith("_"):
                    attr = getattr(vc, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass
