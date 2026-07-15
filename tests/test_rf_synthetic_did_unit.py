"""Unit tests for scripts.research_framework.synthetic_did module."""

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
    from scripts.research_framework import synthetic_did as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_module_imports(MODULE_ABBREV):
    assert MODULE_ABBREV is not None
    assert MODULE_ABBREV.__name__ == "scripts.research_framework.synthetic_did"


def test_module_all_exports(MODULE_ABBREV):
    assert hasattr(MODULE_ABBREV, "__all__")
    assert "SyntheticDiDEngine" in MODULE_ABBREV.__all__
    assert "SyntheticDiDResult" in MODULE_ABBREV.__all__


def test_synthetic_did_result_dataclass(MODULE_ABBREV):
    import dataclasses

    SyntheticDiDResult = MODULE_ABBREV.SyntheticDiDResult
    assert dataclasses.is_dataclass(SyntheticDiDResult)
    fields = [f.name for f in dataclasses.fields(SyntheticDiDResult)]
    expected = [
        "estimator",
        "att",
        "se",
        "pval",
        "ci_lower",
        "ci_upper",
        "n_obs",
        "donor_weights",
        "treated_unit",
        "treatment_time",
        "pre_fit_quality",
        "post_gap",
        "n_donors",
        "r_squared",
        "mspe_ratio",
        "additional",
    ]
    for name in expected:
        assert name in fields, f"Missing field: {name}"


def test_synthetic_did_result_minimal_init(MODULE_ABBREV):
    import numpy as np

    SyntheticDiDResult = MODULE_ABBREV.SyntheticDiDResult
    weights = np.array([0.4, 0.3, 0.3])
    r = SyntheticDiDResult(
        estimator="synthetic_did",
        att=0.12,
        se=0.04,
        pval=0.003,
        donor_weights=weights,
        additional={"method": "bootstrap"},
    )
    assert r.estimator == "synthetic_did"
    assert r.att == 0.12
    assert r.se == 0.04
    assert r.pval == 0.003
    assert r.ci_lower == 0.0
    assert r.ci_upper == 0.0
    assert r.n_obs == 0
    assert r.treated_unit is None
    assert r.treatment_time == 0
    assert r.additional == {"method": "bootstrap"}
    assert len(r.donor_weights) == 3


def test_synthetic_did_result_sig_property(MODULE_ABBREV):
    """sig property returns significance stars based on pval."""
    SyntheticDiDResult = MODULE_ABBREV.SyntheticDiDResult
    # p < 0.001 → ***
    r1 = SyntheticDiDResult(
        estimator="synthetic_did", att=0.1, se=0.04, pval=0.0001, donor_weights=[]
    )
    assert r1.sig == "***"
    # p < 0.01 → **
    r2 = SyntheticDiDResult(
        estimator="synthetic_did", att=0.1, se=0.04, pval=0.005, donor_weights=[]
    )
    assert r2.sig == "**"
    # p < 0.05 → *
    r3 = SyntheticDiDResult(
        estimator="synthetic_did", att=0.1, se=0.04, pval=0.02, donor_weights=[]
    )
    assert r3.sig == "*"
    # p < 0.10 → dagger
    r4 = SyntheticDiDResult(
        estimator="synthetic_did", att=0.1, se=0.04, pval=0.07, donor_weights=[]
    )
    assert "dagger" in r4.sig or r4.sig == r"$\dagger$"
    # p >= 0.10 → empty
    r5 = SyntheticDiDResult(
        estimator="synthetic_did", att=0.1, se=0.04, pval=0.5, donor_weights=[]
    )
    assert r5.sig == ""


def test_synthetic_did_result_to_dict(MODULE_ABBREV):
    import numpy as np

    SyntheticDiDResult = MODULE_ABBREV.SyntheticDiDResult
    r = SyntheticDiDResult(
        estimator="synthetic_did",
        att=0.1,
        se=0.04,
        pval=0.05,
        donor_weights=np.array([0.5, 0.5]),
        treated_unit="CA",
        treatment_time=2013,
        n_donors=2,
    )
    out = r.to_dict()
    assert out["estimator"] == "synthetic_did"
    assert out["att"] == 0.1
    assert out["se"] == 0.04
    assert out["pval"] == 0.05
    assert out["treated_unit"] == "CA"
    assert out["treatment_time"] == 2013
    assert out["n_donors"] == 2
    assert "sig" in out


def test_synthetic_did_engine_class(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV.SyntheticDiDEngine, type)


def test_synthetic_did_engine_init(MODULE_ABBREV):
    import numpy as np

    SyntheticDiDEngine = MODULE_ABBREV.SyntheticDiDEngine
    pre = np.random.RandomState(0).normal(size=(5, 4))
    post = np.random.RandomState(1).normal(size=(5, 4))
    eng = SyntheticDiDEngine(
        pre_outcome_matrix=pre,
        post_outcome_matrix=post,
        treatment_time=5,
    )
    assert eng.treatment_time == 5


def test_optimize_weights_slsqp_callable(MODULE_ABBREV):
    assert callable(MODULE_ABBREV._optimize_weights_slsqp)


def test_optimize_weights_slsqp_simple(MODULE_ABBREV):
    """Simple weight optimization with perfect match returns weights matching treated."""
    import numpy as np

    _optimize_weights_slsqp = MODULE_ABBREV._optimize_weights_slsqp
    # Two donors: donor[0] perfectly matches treated, donor[1] doesn't
    Y_pre_treated = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    Y_pre_donor = np.array(
        [
            [1.0, 2.0, 3.0, 4.0, 5.0],  # perfect match
            [10.0, 20.0, 30.0, 40.0, 50.0],  # off
        ]
    )
    weights = _optimize_weights_slsqp(Y_pre_treated, Y_pre_donor)
    assert weights.shape == (2,)
    # First donor should dominate
    assert weights[0] > weights[1]
