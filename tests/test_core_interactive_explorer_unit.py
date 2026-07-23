"""Unit tests for scripts/core/interactive_explorer.py.

Focused on dataclasses and class existence — large module (821 lines)
with streamlit/plotly UI classes that require browser frameworks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ie():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import interactive_explorer as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, ie):
        for name in [
            "DIDEventStudyConfig",
            "PanelFEConfig",
            "DiagnosticsConfig",
            "DIDEventStudyExplorer",
            "PanelFEVisualizer",
            "RegressionDiagnosticsExplorer",
            "TimeSeriesDecomposer",
            "run_explorer_app",
        ]:
            assert hasattr(ie, name), f"Missing export: {name}"


class TestDIDEventStudyConfig:
    def test_default_init(self, ie):
        cfg = ie.DIDEventStudyConfig()
        assert cfg.pre_means == {}
        assert cfg.post_means == {}
        assert cfg.pre_ctrl_means == {}
        assert cfg.post_ctrl_means == {}
        assert cfg.treat_label == "Treatment"
        assert cfg.ctrl_label == "Control"
        assert cfg.event_time is None
        assert cfg.ylabel == "Outcome"
        assert cfg.title == "Event Study"
        assert cfg.ci_level == 0.95

    def test_full_init(self, ie):
        cfg = ie.DIDEventStudyConfig(
            pre_means={"-3": 1.0, "-2": 1.1, "-1": 1.2},
            post_means={"0": 2.0, "1": 2.1, "2": 2.2},
            pre_ctrl_means={"-3": 0.9, "-2": 1.0, "-1": 1.05},
            post_ctrl_means={"0": 1.5, "1": 1.6, "2": 1.7},
            pre_ses={"-3": 0.1},
            post_ses={"0": 0.2},
            treat_label="Treat",
            ctrl_label="Ctrl",
            event_time=[-3, -2, -1, 0, 1, 2],
            ylabel="Y",
            title="Test",
            ci_level=0.99,
        )
        assert cfg.pre_means["-3"] == 1.0
        assert cfg.ci_level == 0.99
        assert cfg.event_time == [-3, -2, -1, 0, 1, 2]


class TestPanelFEConfig:
    def test_default_init(self, ie):
        cfg = ie.PanelFEConfig()
        assert cfg.entity_var == "entity"
        assert cfg.time_var == "time"
        assert cfg.dep_var == "y"
        assert cfg.fe_entity is True
        assert cfg.fe_time is True
        assert cfg.cluster_var is None
        assert cfg.n_entities == 0
        assert cfg.n_time == 0

    def test_full_init(self, ie):
        cfg = ie.PanelFEConfig(
            entity_var="firm_id",
            time_var="year",
            dep_var="TFP",
            fe_entity=True,
            fe_time=True,
            cluster_var="firm_id",
            n_entities=1000,
            n_time=15,
        )
        assert cfg.entity_var == "firm_id"
        assert cfg.n_entities == 1000
        assert cfg.n_time == 15


class TestDiagnosticsConfig:
    def test_required_fields(self, ie):
        cfg = ie.DiagnosticsConfig(
            y=[1.0, 2.0, 3.0],
            fitted=[1.1, 2.1, 2.9],
            residuals=[-0.1, -0.1, 0.1],
        )
        assert cfg.y == [1.0, 2.0, 3.0]
        assert cfg.fitted == [1.1, 2.1, 2.9]
        assert cfg.residuals == [-0.1, -0.1, 0.1]
        assert cfg.leverage is None
        assert cfg.cooksd is None
        assert cfg.hdi_low is None
        assert cfg.hdi_high is None
        assert cfg.obs_labels is None
        assert cfg.n_covariates == 1

    def test_full_init(self, ie):
        cfg = ie.DiagnosticsConfig(
            y=[1.0, 2.0],
            fitted=[1.1, 2.1],
            residuals=[-0.1, -0.1],
            leverage=[0.1, 0.2],
            cooksd=[0.01, 0.02],
            hdi_low=[0.5, 1.5],
            hdi_high=[1.5, 2.5],
            obs_labels=["obs1", "obs2"],
            n_covariates=5,
        )
        assert cfg.leverage == [0.1, 0.2]
        assert cfg.obs_labels == ["obs1", "obs2"]
        assert cfg.n_covariates == 5


class TestExplorerClasses:
    def test_classes_exist(self, ie):
        assert ie.DIDEventStudyExplorer is not None
        assert ie.PanelFEVisualizer is not None
        assert ie.RegressionDiagnosticsExplorer is not None
        assert ie.TimeSeriesDecomposer is not None

    def test_main_function_exists(self, ie):
        assert callable(ie.main)
        assert callable(ie.run_explorer_app)


class TestDIDEventStudyExplorer:
    def test_init_with_config(self, ie):
        cfg = ie.DIDEventStudyConfig()
        explorer = ie.DIDEventStudyExplorer(cfg)
        assert explorer.config is cfg

    def test_z_score_95(self, ie):
        cfg = ie.DIDEventStudyConfig(ci_level=0.95)
        explorer = ie.DIDEventStudyExplorer(cfg)
        assert explorer._z_score == 1.96

    def test_z_score_99(self, ie):
        cfg = ie.DIDEventStudyConfig(ci_level=0.99)
        explorer = ie.DIDEventStudyExplorer(cfg)
        assert explorer._z_score == 2.576
