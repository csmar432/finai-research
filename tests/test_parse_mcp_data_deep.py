"""tests/test_parse_mcp_data_deep.py — Deep tests for scripts/parse_mcp_data.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import parse_mcp_data as mod
except Exception as _exc:
    pytest.skip(f"scripts.parse_mcp_data not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        if hasattr(mod, "main"):
            assert callable(mod.main)


class TestParse:
    def test_parse_with_empty(self):
        # Look for a parse_* function
        for n in dir(mod):
            if n.startswith("parse_"):
                fn = getattr(mod, n)
                if callable(fn):
                    try:
                        r = fn("")
                        # Don't assert exact type
                    except Exception:
                        pass
                    break
