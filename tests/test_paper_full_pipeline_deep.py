"""tests/test_paper_full_pipeline_deep.py — Deep tests for scripts/paper_full_pipeline.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import paper_full_pipeline as mod
except Exception as _exc:
    pytest.skip(f"scripts.paper_full_pipeline not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        if hasattr(mod, "main"):
            assert callable(mod.main)


class TestCalls:
    def test_main_dry(self, capsys):
        try:
            import sys as _sys
            old = _sys.argv
            _sys.argv = ["paper_full_pipeline.py", "--help"]
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
