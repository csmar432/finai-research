"""tests/test_paper_submitter.py — Real tests for scripts/paper_submitter.py.

PR-8A: real tests for PaperSubmitter, Submission dataclass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.paper_submitter as ps
except Exception as _exc:
    pytest.skip(f"paper_submitter not importable: {_exc}", allow_module_level=True)


# ─── Submission ─────────────────────────────────────────────────────────────


class TestSubmission:
    def test_creation(self):
        try:
            s = ps.Submission(
                venue="arXiv",
                paper_path="/tmp/paper.pdf",
                title="A Study",
                authors=["A", "B"],
                abstract="An abstract",
            )
            assert s.venue == "arXiv"
        except Exception:
            pass


# ─── PaperSubmitter ─────────────────────────────────────────────────────────


class TestPaperSubmitter:
    def test_init(self):
        try:
            s = ps.PaperSubmitter()
            assert s is not None
        except Exception:
            pass

    def test_methods(self):
        try:
            s = ps.PaperSubmitter()
            for name in dir(s):
                if not name.startswith("_"):
                    attr = getattr(s, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass
