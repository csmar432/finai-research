"""Unit tests for scripts/research_framework/panel_var.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pv():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    import importlib
    try:
        mod = importlib.import_module("scripts.research_framework.panel_var")
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scripts.research_framework.panel_var",
            "scripts/research_framework/panel_var.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["scripts.research_framework.panel_var"] = mod
        spec.loader.exec_module(mod)
    yield mod
    if _p in sys.path:
        sys.path.remove(_p)


class TestPanelVARResult:
    def test_dataclass_fields(self, pv):
        # PanelVARResult has np.array defaults that fail without args.
        # We only verify the dataclass structure without instantiation.
        import dataclasses
        fields = dataclasses.fields(pv.PanelVARResult)
        assert any(f.name == "lag_order" for f in fields)
        assert any(f.name == "y_vars" for f in fields)
        assert any(f.name == "params" for f in fields)


class TestPanelVAR:
    def test_class_exists(self, pv):
        assert hasattr(pv, "PanelVAR")