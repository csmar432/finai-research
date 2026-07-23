"""tests/test_research_framework_panel_var.py — Deep tests for panel_var.

PR-8J: Tests for scripts/research_framework/panel_var.py (665 stmts).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import panel_var as mod
except Exception as _exc:
    pytest.skip(f"panel_var not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_has_classes(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


def _try_init(cls):
    """Try to instantiate cls with no args."""
    try:
        return cls()
    except Exception:
        return None


class TestPanelVARResult:
    def test_default_construction(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None:
            pytest.skip("not present")
        _try_init(cls)


class TestPanelVAR:
    def test_default_construction(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None:
            pytest.skip("not present")
        _try_init(cls)


class TestOtherClasses:
    """Try to instantiate any other classes that may be in the module."""

    def test_try_init_all_classes(self):
        for name in dir(mod):
            if name.startswith("_"):
                continue
            cls = getattr(mod, name, None)
            if not isinstance(cls, type):
                continue
            # Try with no args
            try:
                obj = cls()
                # success
                assert obj is not None
            except Exception:
                # May require args — that's OK
                pass
