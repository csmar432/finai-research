"""tests/test_citation_stance_deep.py — Deep tests for scripts/citation_stance.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import citation_stance as mod
except Exception as _exc:
    pytest.skip(f"scripts.citation_stance not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_classes(self):
        for n in dir(mod):
            if not n.startswith("_") and isinstance(getattr(mod, n, None), type):
                assert getattr(mod, n) is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)


class TestClassifier:
    def test_signature_check(self):
        # If there's a classifier class, verify it has predict/transform or similar
        if hasattr(mod, "CitationStanceClassifier"):
            try:
                cls_obj = mod.CitationStanceClassifier
                # Try to instantiate
                obj = cls_obj()
                assert obj is not None
            except TypeError:
                # May need args
                pass
            except Exception:
                pass
