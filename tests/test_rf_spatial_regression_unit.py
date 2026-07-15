"""Unit tests for scripts.research_framework.spatial_regression module.

The module is very large (2000+ lines) so the tests focus on dataclass /
constructor-level coverage and basic structural helpers. Full model fitting
(MLE / GMM) is intentionally out of scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def MODULE_ABBREV():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.research_framework import spatial_regression as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_module_imports(MODULE_ABBREV):
    assert MODULE_ABBREV is not None
    assert MODULE_ABBREV.__name__ == "scripts.research_framework.spatial_regression"


def test_module_all_exports(MODULE_ABBREV):
    assert hasattr(MODULE_ABBREV, "__all__")
    expected = [
        "SpatialRegressionEngine",
        "SpatialEstimationResult",
        "SpatialLagModel",
        "SpatialErrorModel",
        "SpatialDurbinModel",
        "SpatialPanelRE",
        "SpatialPanelFE",
    ]
    for name in expected:
        assert name in MODULE_ABBREV.__all__, f"Missing in __all__: {name}"


def test_spatial_estimation_result_dataclass(MODULE_ABBREV):
    import dataclasses

    SpatialEstimationResult = MODULE_ABBREV.SpatialEstimationResult
    assert dataclasses.is_dataclass(SpatialEstimationResult)
    fields = [f.name for f in dataclasses.fields(SpatialEstimationResult)]
    expected = [
        "estimator",
        "coef",
        "se",
        "pval",
        "ci_lower",
        "ci_upper",
        "n_obs",
        "r_squared",
        "log_likelihood",
        "aic",
        "bic",
        "spatial_rho",
        "spatial_lambda",
        "sig",
        "variable_names",
        "additional",
    ]
    for name in expected:
        assert name in fields, f"Missing field: {name}"


def test_spatial_estimation_result_minimal_init(MODULE_ABBREV):
    import numpy as np

    SpatialEstimationResult = MODULE_ABBREV.SpatialEstimationResult
    coef = np.array([0.1, 0.2])
    se = np.array([0.05, 0.05])
    pval = np.array([0.04, 0.001])
    ci_l = np.array([0.0, 0.1])
    ci_u = np.array([0.2, 0.3])
    r = SpatialEstimationResult(
        estimator="sar",
        coef=coef,
        se=se,
        pval=pval,
        ci_lower=ci_l,
        ci_upper=ci_u,
        n_obs=100,
        variable_names=["x1", "x2"],
    )
    assert r.estimator == "sar"
    assert r.n_obs == 100
    assert r.spatial_rho is None
    assert r.spatial_lambda is None
    assert r.r_squared is None
    assert r.log_likelihood is None


def test_spatial_estimation_result_sig_auto_computed(MODULE_ABBREV):
    """__post_init__ populates sig from pval when None."""
    import numpy as np

    SpatialEstimationResult = MODULE_ABBREV.SpatialEstimationResult
    r = SpatialEstimationResult(
        estimator="sar",
        coef=np.array([0.1, 0.2]),
        se=np.array([0.05, 0.05]),
        pval=np.array([0.0001, 0.5]),
        ci_lower=np.array([0.0, 0.1]),
        ci_upper=np.array([0.2, 0.3]),
        n_obs=100,
        variable_names=["x1", "x2"],
    )
    assert r.sig is not None
    assert len(r.sig) == 2


def test_spatial_estimation_result_sig_str(MODULE_ABBREV):
    import numpy as np

    SpatialEstimationResult = MODULE_ABBREV.SpatialEstimationResult
    r = SpatialEstimationResult(
        estimator="sar",
        coef=np.array([0.1]),
        se=np.array([0.05]),
        pval=np.array([0.0001]),
        ci_lower=np.array([0.0]),
        ci_upper=np.array([0.2]),
        n_obs=10,
        variable_names=["x1"],
    )
    assert "***" in r.sig_str


def test_spatial_estimation_result_to_dict(MODULE_ABBREV):
    import numpy as np

    SpatialEstimationResult = MODULE_ABBREV.SpatialEstimationResult
    r = SpatialEstimationResult(
        estimator="sar",
        coef=np.array([0.1, 0.2]),
        se=np.array([0.05, 0.05]),
        pval=np.array([0.04, 0.5]),
        ci_lower=np.array([0.0, 0.1]),
        ci_upper=np.array([0.2, 0.3]),
        n_obs=50,
        variable_names=["x1", "x2"],
        spatial_rho=0.3,
        spatial_lambda=None,
    )
    out = r.to_dict()
    assert out["estimator"] == "sar"
    assert out["n_obs"] == 50
    assert out["spatial_rho"] == 0.3
    assert out["spatial_lambda"] is None
    assert out["coef_x1"] == 0.1
    assert out["se_x1"] == 0.05
    assert out["pval_x1"] == 0.04


def test_spatial_lag_model_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialLagModel, type)


def test_spatial_error_model_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialErrorModel, type)


def test_spatial_durbin_model_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialDurbinModel, type)


def test_spatial_panel_re_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialPanelRE, type)


def test_spatial_panel_fe_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialPanelFE, type)


def test_spatial_regression_engine_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SpatialRegressionEngine, type)


def test_row_standardize_helper(MODULE_ABBREV):
    import numpy as np

    _row_standardize = MODULE_ABBREV._row_standardize
    W = np.array([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]])
    Ws = _row_standardize(W)
    # Each row should sum to 1
    row_sums = Ws.sum(axis=1)
    assert np.allclose(row_sums, 1.0)


def test_row_standardize_handles_isolated_node(MODULE_ABBREV):
    """An isolated node (all-zero row) should not divide by zero."""
    import numpy as np

    _row_standardize = MODULE_ABBREV._row_standardize
    W = np.array([[1.0, 1.0], [0.0, 0.0]])
    Ws = _row_standardize(W)
    # First row sums to 1, isolated row stays at (0, 0)
    assert np.allclose(Ws[0].sum(), 1.0)
    assert np.allclose(Ws[1], 0.0)


def test_build_knn_weights_callable(MODULE_ABBREV):
    assert callable(MODULE_ABBREV._build_knn_weights)


def test_build_knn_weights_basic(MODULE_ABBREV):
    import numpy as np

    _build_knn_weights = MODULE_ABBREV._build_knn_weights
    coords = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [0.0, 1.0],
        ]
    )
    W = _build_knn_weights(coords, k=1)
    assert W.shape == (4, 4)
    # Diagonal must be zero (no self-loops)
    assert np.allclose(np.diag(W), 0.0)


def test_morans_i_helper_callable(MODULE_ABBREV):
    """A Moran's I function is exposed."""
    found = False
    for name in dir(MODULE_ABBREV):
        if "moran" in name.lower():
            found = True
            break
    assert found, "Expected a Moran's I helper function in spatial_regression"


def test_module_classes_are_types(MODULE_ABBREV):
    """All public classes are types (not instances)."""
    for name in (
        "SpatialRegressionEngine",
        "SpatialLagModel",
        "SpatialErrorModel",
        "SpatialDurbinModel",
        "SpatialPanelRE",
        "SpatialPanelFE",
    ):
        assert isinstance(getattr(MODULE_ABBREV, name), type), f"{name} is not a class"
