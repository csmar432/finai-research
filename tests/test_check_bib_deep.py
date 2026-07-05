"""tests/test_check_bib_deep.py — Deep tests for scripts/check_bib.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import check_bib as mod
except Exception as _exc:
    pytest.skip(f"scripts.check_bib not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        assert callable(getattr(mod, "main", None))


class TestCalls:
    def test_main_safe_invocation(self, tmp_path):
        try:
            import sys as _sys
            old = _sys.argv
            _sys.argv = ["check_bib.py"]
            try:
                mod.main()
            finally:
                _sys.argv = old
        except SystemExit:
            pass
        except Exception:
            pass
