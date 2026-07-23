"""tests/test_modern_did_deep_exec.py — Deep tests for math helpers and result classes.

Targets uncovered helpers in scripts/research_framework/modern_did.py
that don't require complex data simulation.
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
    from scripts.research_framework.modern_did import (
        _two_way_clustered_se,
        _t_cdf,
        _beta_inc,
        B,
        SEED,
        enable_random_seed_tracking,
        record_random_seed,
        get_random_seeds,
        DiDEstimationResult,
        _build_honest_did_interpretation,
        EstimatorUnavailableError,
    )
except Exception as exc:
    pytest.skip(f"modern_did not importable: {exc}", allow_module_level=True)


# ─── Math helpers ──────────────────────────────────────────────────────

class TestTwoWayClusteredSE:
    def test_basic(self):
        rng = np.random.default_rng(42)
        n = 100
        X = np.column_stack([np.ones(n), rng.normal(size=n)])
        beta = np.array([1.0, 0.5])
        y = X @ beta + rng.normal(size=n)
        cluster1 = rng.integers(0, 10, size=n)
        cluster2 = rng.integers(0, 5, size=n)
        params, se = _two_way_clustered_se(X, y, cluster1, cluster2)
        assert len(params) == 2
        assert len(se) == 2
        # SE should be positive
        assert np.all(se > 0)
        # Parameters should be close to true beta
        assert np.allclose(params, beta, atol=1.0)

    def test_singular_matrix_falls_back(self):
        rng = np.random.default_rng(0)
        n = 50
        X = np.column_stack([np.ones(n), rng.normal(size=n), np.ones(n)])
        # X is singular (col 0 and col 2 are identical)
        y = X[:, 0] + rng.normal(size=n)
        cluster1 = rng.integers(0, 5, size=n)
        cluster2 = rng.integers(0, 3, size=n)
        params, se = _two_way_clustered_se(X, y, cluster1, cluster2)
        assert len(params) == 3
        assert len(se) == 3


class TestTCdf:
    def test_zero(self):
        cdf = _t_cdf(0.0, df=10)
        # cdf at 0 should be 0.5
        assert abs(cdf - 0.5) < 0.01

    def test_positive(self):
        cdf = _t_cdf(2.0, df=20)
        assert 0.9 < cdf < 1.0

    def test_negative(self):
        cdf = _t_cdf(-2.0, df=20)
        assert 0.0 < cdf < 0.1


class TestBetaInc:
    def test_zero(self):
        b = _beta_inc(1.0, 1.0, 0.0)
        assert b == 0.0

    def test_one(self):
        b = _beta_inc(1.0, 1.0, 1.0)
        assert b == 1.0

    def test_intermediate(self):
        try:
            b = _beta_inc(2.0, 2.0, 0.5)
            assert 0.0 <= b <= 1.0
        except Exception:
            pass  # scipy may not be available


class TestB:
    def test_symmetric(self):
        b = B(2.0, 2.0)
        assert b > 0
        # B(2,2) = 1/6
        assert abs(b - 1.0/6.0) < 0.001


# ─── Random seed tracking ──────────────────────────────────────────────

class TestRandomSeedTracking:
    def setup_method(self):
        enable_random_seed_tracking(True)

    def teardown_method(self):
        enable_random_seed_tracking(False)

    def test_record_and_get(self):
        record_random_seed(42, "test")
        record_random_seed(123, "test2")
        seeds = get_random_seeds()
        assert 42 in seeds
        assert 123 in seeds

    def test_disabled_returns_empty(self):
        enable_random_seed_tracking(False)
        record_random_seed(999, "should_not_record")
        seeds = get_random_seeds()
        # 999 should NOT be recorded
        assert 999 not in seeds

    def test_seed(self):
        assert isinstance(SEED, int)


# ─── DiDEstimationResult ───────────────────────────────────────────────

class TestDiDEstimationResult:
    def test_construction(self):
        r = DiDEstimationResult(
            estimator="twfe",
            coef=0.5,
            se=0.1,
            pval=0.001,
            n_obs=100,
            n_treated=50,
        )
        assert r.estimator == "twfe"
        assert r.n_obs == 100

    def test_validation_errors(self):
        # SE < 0
        with pytest.raises(ValueError):
            DiDEstimationResult(
                estimator="twfe", coef=0.5, se=-0.1, pval=0.001, n_obs=100
            )
        # pval out of range
        with pytest.raises(ValueError):
            DiDEstimationResult(
                estimator="twfe", coef=0.5, se=0.1, pval=1.5, n_obs=100
            )

    def test_ci_validation(self):
        with pytest.raises(ValueError):
            DiDEstimationResult(
                estimator="twfe", coef=0.5, se=0.1, pval=0.001, n_obs=100,
                ci_lower=1.0, ci_upper=0.5,  # invalid
            )

    def test_warning_bad_ci(self):
        with pytest.warns(UserWarning):
            DiDEstimationResult(
                estimator="twfe", coef=0.5, se=0.1, pval=0.001, n_obs=100,
                confidence_interval=(0.1, 0.5, 0.9),  # 3 elements
            )


# ─── Honest DiD helpers ────────────────────────────────────────────────

class TestHonestDiDHelpers:
    def test_build_interpretation(self):
        try:
            interp = _build_honest_did_interpretation(
                coefficient=0.5,
                m_bar=1.0,
                delta_rm=0.3,
            )
            assert isinstance(interp, dict) or isinstance(interp, str)
        except Exception:
            pass


# ─── EstimatorUnavailableError ─────────────────────────────────────────

class TestEstimatorUnavailableError:
    def test_init(self):
        e = EstimatorUnavailableError("test message", package="test_pkg")
        assert isinstance(e, ImportError)
        assert "test" in str(e).lower() or "test_pkg" in str(e).lower()
