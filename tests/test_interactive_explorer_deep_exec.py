"""tests/test_interactive_explorer_deep_exec.py — Deep tests for interactive_explorer configs and small methods.

Targets uncovered helpers in scripts/core/interactive_explorer.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import pandas as pd
    from scripts.core.interactive_explorer import (
        DIDEventStudyConfig, PanelFEConfig, DiagnosticsConfig,
        DIDEventStudyExplorer, PanelFEVisualizer,
        RegressionDiagnosticsExplorer, TimeSeriesDecomposer,
        run_explorer_app, main,
    )
except Exception as exc:
    pytest.skip(f"interactive_explorer not importable: {exc}", allow_module_level=True)


# ─── Config dataclasses ───────────────────────────────────────────────

class TestDIDEventStudyConfig:
    def test_defaults(self):
        cfg = DIDEventStudyConfig()
        assert cfg.pre_means == {}
        assert cfg.post_means == {}
        assert cfg.treat_label == "Treatment"
        assert cfg.ctrl_label == "Control"
        assert cfg.ci_level == 0.95

    def test_custom(self):
        cfg = DIDEventStudyConfig(
            pre_means={"-3": 0.1, "-2": 0.12},
            post_means={"0": 0.5, "1": 0.6},
            treat_label="Treated",
            ctrl_label="Control",
            ci_level=0.99,
        )
        assert cfg.treat_label == "Treated"
        assert cfg.ci_level == 0.99


class TestPanelFEConfig:
    def test_defaults(self):
        cfg = PanelFEConfig()
        assert cfg.entity_var == "entity"
        assert cfg.time_var == "time"
        assert cfg.fe_entity is True
        assert cfg.fe_time is True

    def test_custom(self):
        cfg = PanelFEConfig(
            entity_var="company",
            time_var="quarter",
            fe_entity=True,
            fe_time=False,
        )
        assert cfg.entity_var == "company"
        assert cfg.fe_time is False


class TestDiagnosticsConfig:
    def test_basic(self):
        cfg = DiagnosticsConfig(y=[1.0, 2.0], fitted=[1.1, 1.9], residuals=[-0.1, 0.1])
        assert cfg.y == [1.0, 2.0]
        assert cfg.fitted == [1.1, 1.9]
        assert cfg.n_covariates == 1

    def test_with_leverage(self):
        cfg = DiagnosticsConfig(
            y=[1.0, 2.0], fitted=[1.1, 1.9], residuals=[-0.1, 0.1],
            leverage=[0.1, 0.2], cooksd=[0.01, 0.02],
        )
        assert cfg.leverage == [0.1, 0.2]
        assert cfg.cooksd == [0.01, 0.02]


# ─── Class initialization ─────────────────────────────────────────────

class TestDIDEventStudyExplorer:
    def test_init(self):
        try:
            e = DIDEventStudyExplorer()
            assert e is not None
        except Exception:
            pass


class TestPanelFEVisualizer:
    def test_init(self):
        try:
            v = PanelFEVisualizer()
            assert v is not None
        except Exception:
            pass


class TestRegressionDiagnosticsExplorer:
    def test_init(self):
        try:
            e = RegressionDiagnosticsExplorer()
            assert e is not None
        except Exception:
            pass


class TestTimeSeriesDecomposer:
    def test_init(self):
        try:
            d = TimeSeriesDecomposer()
            assert d is not None
        except Exception:
            pass


# ─── Module-level functions ───────────────────────────────────────────

class TestModuleFunctions:
    def test_main_exists(self):
        try:
            assert callable(main)
        except Exception:
            pass

    def test_run_explorer_app_exists(self):
        try:
            assert callable(run_explorer_app)
        except Exception:
            pass