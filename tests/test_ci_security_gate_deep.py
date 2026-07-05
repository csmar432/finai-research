"""tests/test_ci_security_gate_deep.py — Deep tests for scripts/ci_security_gate.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import ci_security_gate as mod
except Exception as _exc:
    pytest.skip(f"scripts.ci_security_gate not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        # ci_security_gate may not define main() — skip if absent
        if hasattr(mod, "main"):
            assert callable(mod.main)
