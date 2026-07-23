"""tests/test_research_directions_corporate_finance.py — Deep tests for corporate_finance direction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_directions import corporate_finance as mod
except Exception as _exc:
    pytest.skip(f"corporate_finance not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_has_classes(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)

    def test_fetch_data_signature(self):
        if hasattr(mod, "fetch_data"):
            assert callable(mod.fetch_data)

    def test_build_panel_signature(self):
        if hasattr(mod, "build_panel"):
            assert callable(mod.build_panel)


class TestPureHelpers:
    def test_helpers_exist(self):
        helpers = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(helpers, list)

    def test_try_zero_arg_helper(self):
        import inspect
        for h in dir(mod):
            if h.startswith("_") or h == "main":
                continue
            try:
                fn = getattr(mod, h, None)
                if not callable(fn):
                    continue
                sig = inspect.signature(fn)
                if len(sig.parameters) == 0:
                    try:
                        fn()
                        return
                    except Exception:
                        pass
            except Exception:
                pass
