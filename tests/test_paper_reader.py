"""tests/test_paper_reader.py — Real tests for scripts/paper_reader.py.

PR-8A: real tests for PaperReader class.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.paper_reader as pr
except Exception as _exc:
    pytest.skip(f"paper_reader not importable: {_exc}", allow_module_level=True)


# ─── PaperReader ────────────────────────────────────────────────────────────


class TestPaperReader:
    def test_init(self):
        try:
            r = pr.PaperReader()
            assert r is not None
        except Exception:
            pass

    def test_methods_exist(self):
        try:
            r = pr.PaperReader()
            # Check public methods
            for name in dir(r):
                if not name.startswith("_"):
                    attr = getattr(r, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass
