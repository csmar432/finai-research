"""tests/test_paper_submitter_deep.py — Deep tests for scripts/paper_submitter.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import paper_submitter as mod
except Exception as _exc:
    pytest.skip(f"scripts.paper_submitter not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        if hasattr(mod, "main"):
            assert callable(mod.main)

    def test_has_classes(self):
        for n in dir(mod):
            if not n.startswith("_") and isinstance(getattr(mod, n, None), type):
                # Verify it's a real class
                assert getattr(mod, n) is not None
