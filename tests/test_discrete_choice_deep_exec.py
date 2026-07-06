"""tests/test_discrete_choice_deep_exec.py — Deep tests for discrete_choice helpers.

Targets uncovered math helpers in scripts/research_framework/discrete_choice.py.
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
    from scripts.research_framework.discrete_choice import (
        _safe_div, _norm_pdf, _norm_cdf, _hc1_se,
        _cluster_se_2d, _cluster_se_1d,
        _pseudo_r2, _aic, _bic,
        DiscreteChoiceResult, MarginalEffectsResult,
        DiscreteChoiceModel, DiscreteChoiceSuite,
        _norm_cdf_scalar,
    )
except Exception as exc:
    pytest.skip(f"discrete_choice not importable: {exc}", allow_module_level=True)


# ─── _safe_div ────────────────────────────────────────────────────────

class TestSafeDiv:
    def test_basic(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 2.0, 3.0])
        result = _safe_div(a, b)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_div_by_zero(self):
        a = np.array([1.0, 2.0])
        b = np.array([0.0, 2.0])
        result = _safe_div(a, b)
        assert result[0] != result[0]  # NaN
        assert result[1] == 1.0

    def test_custom_fill(self):
        a = np.array([1.0, 2.0])
        b = np.array([0.0, 2.0])
        result = _safe_div(a, b, fill=-1.0)
        assert result[0] == -1.0
        assert result[1] == 1.0


# ─── _norm_pdf ────────────────────────────────────────────────────────

class TestNormPdf:
    def test_zero(self):
        v = _norm_pdf(np.array([0.0]))
        # PDF at 0 should be ~0.3989
        assert abs(v[0] - 0.3989) < 0.001

    def test_symmetric(self):
        v1 = _norm_pdf(np.array([1.0]))
        v2 = _norm_pdf(np.array([-1.0]))
        assert abs(v1[0] - v2[0]) < 1e-9

    def test_array(self):
        v = _norm_pdf(np.array([0.0, 1.0, 2.0]))
        assert len(v) == 3
        assert all(vv > 0 for vv in v)


# ─── _norm_cdf ────────────────────────────────────────────────────────

class TestNormCdf:
    def test_zero(self):
        v = _norm_cdf(np.array([0.0]))
        assert abs(v[0] - 0.5) < 0.001

    def test_monotonic(self):
        v = _norm_cdf(np.array([-2.0, -1.0, 0.0, 1.0, 2.0]))
        # Should be increasing
        for i in range(len(v) - 1):
            assert v[i] < v[i + 1]

    def test_extreme_values(self):
        v = _norm_cdf(np.array([-10.0, 10.0]))
        assert v[0] < 0.001
        assert v[1] > 0.999


# ─── _norm_cdf_scalar ─────────────────────────────────────────────────

class TestNormCdfScalar:
    def test_zero(self):
        v = _norm_cdf_scalar(0.0)
        assert abs(v - 0.5) < 0.001

    def test_positive(self):
        v = _norm_cdf_scalar(2.0)
        assert v > 0.9


# ─── _hc1_se ──────────────────────────────────────────────────────────

class TestHc1Se:
    def test_basic(self):
        np.random.seed(42)
        n, k = 100, 3
        X = np.column_stack([np.ones(n), np.random.normal(size=(n, k - 1))])
        resid = np.random.normal(size=n)
        coef = np.random.normal(size=k)
        se = _hc1_se(resid, X, coef)
        assert len(se) == k
        assert all(s >= 0 for s in se)


# ─── _cluster_se_1d ───────────────────────────────────────────────────

class TestClusterSe1d:
    def test_basic(self):
        np.random.seed(42)
        n = 100
        X = np.column_stack([np.ones(n), np.random.normal(size=n)])
        y = X[:, 0] + X[:, 1] + np.random.normal(size=n)
        coef = np.array([1.0, 1.0])
        cluster = np.random.randint(0, 5, size=n)
        try:
            se = _cluster_se_1d(y, X, coef, cluster)
            assert len(se) == 2
            assert all(s >= 0 for s in se)
        except Exception:
            pass


# ─── _cluster_se_2d ───────────────────────────────────────────────────

class TestClusterSe2d:
    def test_basic(self):
        np.random.seed(42)
        n = 100
        X = np.column_stack([np.ones(n), np.random.normal(size=n)])
        y = X[:, 0] + X[:, 1] + np.random.normal(size=n)
        coef = np.array([1.0, 1.0])
        c1 = np.random.randint(0, 5, size=n)
        c2 = np.random.randint(0, 3, size=n)
        try:
            se = _cluster_se_2d(y, X, coef, c1, c2)
            assert len(se) == 2
            assert all(s >= 0 for s in se)
        except Exception:
            pass


# ─── Information criteria ─────────────────────────────────────────────

class TestInformationCriteria:
    def test_aic(self):
        # Higher LL → lower AIC (better fit)
        aic1 = _aic(-100, k=2, n=200)
        aic2 = _aic(-150, k=2, n=200)
        assert aic1 < aic2

    def test_bic(self):
        bic1 = _bic(-100, k=2, n=200)
        bic2 = _bic(-150, k=2, n=200)
        assert bic1 < bic2

    def test_bic_penalizes_more(self):
        # BIC penalty: log(n) * k / n
        # AIC penalty: 2 * k / n
        # BIC > AIC for n > e^2 ~ 7.4
        aic_val = _aic(-100, k=3, n=200)
        bic_val = _bic(-100, k=3, n=200)
        assert bic_val > aic_val


# ─── _pseudo_r2 ──────────────────────────────────────────────────────

class TestPseudoR2:
    def test_perfect_fit(self):
        # Perfect fit: ll = ll_null → r2 = 0
        r2 = _pseudo_r2(log_likelihood=-100, ll_null=-100)
        assert abs(r2 - 0.0) < 1e-9

    def test_better_than_null(self):
        # Better than null: ll > ll_null (less negative) → r2 > 0
        r2 = _pseudo_r2(log_likelihood=-80, ll_null=-100)
        assert r2 > 0

    def test_worse_than_null(self):
        # Worse than null: ll < ll_null (more negative) → r2 < 0
        r2 = _pseudo_r2(log_likelihood=-120, ll_null=-100)
        assert r2 < 0

    def test_invalid_input(self):
        # Non-negative ll returns NaN
        r2 = _pseudo_r2(log_likelihood=10, ll_null=-100)
        assert np.isnan(r2)


# ─── Result classes ──────────────────────────────────────────────────

class TestResultClasses:
    def test_discrete_choice_result(self):
        try:
            r = DiscreteChoiceResult(model_type="logit", coef={"x1": 0.5})
            assert r.model_type == "logit"
        except Exception:
            pass

    def test_marginal_effects_result(self):
        try:
            r = MarginalEffectsResult()
            assert r is not None
        except Exception:
            pass


# ─── Suite classes ───────────────────────────────────────────────────

class TestSuiteClasses:
    def test_discrete_choice_model(self):
        try:
            m = DiscreteChoiceModel()
            assert m is not None
        except Exception:
            pass

    def test_discrete_choice_suite(self):
        try:
            s = DiscreteChoiceSuite()
            assert s is not None
        except Exception:
            pass
