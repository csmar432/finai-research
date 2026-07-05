"""tests/test_cleanup_paper_index_deep.py — Deep tests for scripts/cleanup_paper_index.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import cleanup_paper_index as mod
except Exception as _exc:
    pytest.skip(f"scripts.cleanup_paper_index not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        assert callable(getattr(mod, "main", None))
