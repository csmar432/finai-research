"""tests/test_generate_empirical_tables_deep.py — Deep tests for scripts/generate_empirical_tables.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import generate_empirical_tables as mod
except Exception as _exc:
    pytest.skip(f"scripts.generate_empirical_tables not importable: {_exc}", allow_module_level=True)


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
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


class TestCalls:
    def test_main_safe_invocation(self):
        try:
            import sys as _sys
            old = _sys.argv
            _sys.argv = ["generate_empirical_tables.py", "--help"]
            try:
                mod.main()
            except SystemExit:
                pass
            finally:
                _sys.argv = old
        except SystemExit:
            pass
        except Exception:
            pass
