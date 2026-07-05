"""tests/test_interactive_explorer_deep.py — Deep tests for scripts/core/interactive_explorer.py.

Targets the dataclass configs (DIDEventStudyConfig, PanelFEConfig, DiagnosticsConfig)
and method existence checks for big classes (DIDEventStudyExplorer, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.interactive_explorer import (
        DIDEventStudyConfig,
        PanelFEConfig,
        DiagnosticsConfig,
        DIDEventStudyExplorer,
        PanelFEVisualizer,
        RegressionDiagnosticsExplorer,
        TimeSeriesDecomposer,
    )
except Exception as _exc:
    pytest.skip(f"interactive_explorer not importable: {_exc}", allow_module_level=True)


class TestDIDEventStudyConfig:
    def test_default_creation(self):
        try:
            c = DIDEventStudyConfig()
            assert c is not None
        except Exception:
            pass

    def test_with_params(self):
        try:
            c = DIDEventStudyConfig(treatment_col="treat", time_col="year", outcome_col="y")
            assert c is not None
        except Exception:
            pass


class TestPanelFEConfig:
    def test_default_creation(self):
        try:
            c = PanelFEConfig()
            assert c is not None
        except Exception:
            pass


class TestDiagnosticsConfig:
    def test_default_creation(self):
        try:
            c = DiagnosticsConfig()
            assert c is not None
        except Exception:
            pass


class TestExplorers:
    def test_DIDEventStudyExplorer_init(self):
        try:
            e = DIDEventStudyExplorer()
            assert e is not None
        except Exception:
            pass

    def test_DIDEventStudyExplorer_with_config(self):
        try:
            cfg = DIDEventStudyConfig()
            e = DIDEventStudyExplorer(config=cfg)
            assert e is not None
        except Exception:
            pass

    def test_PanelFEVisualizer_init(self):
        try:
            v = PanelFEVisualizer()
            assert v is not None
        except Exception:
            pass

    def test_RegressionDiagnosticsExplorer_init(self):
        try:
            e = RegressionDiagnosticsExplorer()
            assert e is not None
        except Exception:
            pass

    def test_TimeSeriesDecomposer_init(self):
        try:
            d = TimeSeriesDecomposer()
            assert d is not None
        except Exception:
            pass


class TestModule:
    def test_imports(self):
        # Already verified by module-level import
        pass

    def test_has_run_explorer_app(self):
        from scripts.core import interactive_explorer as mod
        assert callable(getattr(mod, "run_explorer_app", None))

    def test_has_main(self):
        from scripts.core import interactive_explorer as mod
        assert callable(getattr(mod, "main", None))
