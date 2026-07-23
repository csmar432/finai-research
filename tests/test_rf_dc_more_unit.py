"""Unit tests for several research_framework dataclasses.

Covers: panel_cointegration, panel_threshold_regression, triple_diff_did,
local_projections_did, survival_analysis, volatility_models,
time_varying_models, modern_did, robustness_runner.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import(modname, filepath):
    """Import module robustly for CI xdist subprocesses."""
    import importlib
    try:
        return importlib.import_module(modname)
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(modname, filepath)
        m = importlib.util.module_from_spec(spec)
        sys.modules[modname] = m
        spec.loader.exec_module(m)
        return m


@pytest.fixture
def pc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.panel_cointegration",
                  "scripts/research_framework/panel_cointegration.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def ptr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.panel_threshold_regression",
                  "scripts/research_framework/panel_threshold_regression.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def td():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.triple_diff_did",
                  "scripts/research_framework/triple_diff_did.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def lp():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.local_projections_did",
                  "scripts/research_framework/local_projections_did.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def sa():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.survival_analysis",
                  "scripts/research_framework/survival_analysis.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def vm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.volatility_models",
                  "scripts/research_framework/volatility_models.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def tvm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.time_varying_models",
                  "scripts/research_framework/time_varying_models.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def md():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.modern_did",
                  "scripts/research_framework/modern_did.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def rr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.robustness_runner",
                  "scripts/research_framework/robustness_runner.py")
    if _p in sys.path:
        sys.path.remove(_p)


class TestPanelVARResult:
    """Already covered by test_rf_panel_var_unit.py."""

class TestPanelCointegration:
    def test_cointegration_result_class_exists(self, pc):
        assert hasattr(pc, "CointegrationResult")

    def test_ecm_result_class_exists(self, pc):
        assert hasattr(pc, "ECMResult")


class TestPanelThresholdRegression:
    def test_threshold_model_class_exists(self, ptr):
        assert hasattr(ptr, "ThresholdModel")

    def test_threshold_result_class_exists(self, ptr):
        assert hasattr(ptr, "ThresholdResult")


class TestTripleDiffDID:
    def test_ddd_result_class_exists(self, td):
        assert hasattr(td, "DDDResult")


class TestLocalProjectionsDID:
    def test_lpdid_result_class_exists(self, lp):
        assert hasattr(lp, "LPDIDResult")


class TestSurvivalAnalysis:
    def test_survival_result_class_exists(self, sa):
        assert hasattr(sa, "SurvivalResult")


class TestVolatilityModels:
    def test_volatility_result_class_exists(self, vm):
        assert hasattr(vm, "VolatilityResult")


class TestTimeVaryingModels:
    def test_dccgarch_result_class_exists(self, tvm):
        assert hasattr(tvm, "DCCGARCHResult")

    def test_tvpvar_result_class_exists(self, tvm):
        assert hasattr(tvm, "TVPVARResult")


class TestModernDID:
    def test_did_estimation_result_class_exists(self, md):
        assert hasattr(md, "DiDEstimationResult")


class TestRobustnessRunner:
    def test_robustness_report_class_exists(self, rr):
        assert hasattr(rr, "RobustnessReport")

    def test_robustness_test_class_exists(self, rr):
        assert hasattr(rr, "RobustnessTest")
