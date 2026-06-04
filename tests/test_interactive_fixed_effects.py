"""Tests for scripts/research_framework/interactive_fixed_effects.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def ife_data():
    """100 units × 20 periods, suitable for IFE estimation (3 variables)."""
    np.random.seed(42)
    n, t, k = 100, 20, 3  # 100 units, 20 periods, 3 variables (y + 2 x-vars)

    # Build panel as 3D array: (n, t, k) where k=3: [y, x1, x2]
    panel = np.zeros((n, t, k))
    for i in range(n):
        for tt in range(t):
            # y depends on x1, x2 and has interactive FE structure
            x1 = np.random.randn()
            x2 = np.random.rand()
            y = 0.5 * x1 + 0.3 * x2 + np.random.randn() * 0.5
            panel[i, tt, :] = [y, x1, x2]

    return panel


@pytest.fixture
def ife_small():
    """Small panel for boundary tests (n=5, t=5)."""
    np.random.seed(42)
    n, t, k = 5, 5, 2  # y + 1 x-var
    panel = np.zeros((n, t, k))
    for i in range(n):
        for tt in range(t):
            x1 = np.random.randn()
            y = 0.5 * x1 + np.random.randn() * 0.3
            panel[i, tt, :] = [y, x1]
    return panel


# ── 1. Engine initialization ─────────────────────────────────────────────────


class TestIFEInit:
    """Test InteractiveFixedEffects.__init__."""

    def test_engine_init(self):
        """InteractiveFixedEffects initializes with n_units and n_periods."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        engine = InteractiveFixedEffects(n_units=100, n_periods=20)
        assert engine.n_units == 100
        assert engine.n_periods == 20
        assert engine._result is None

    def test_module_exports(self):
        """IFEResult, InteractiveFixedEffects, CCEPanelEstimator in __all__."""
        from scripts.research_framework import interactive_fixed_effects as ife

        assert "IFEResult" in ife.__all__
        assert "InteractiveFixedEffects" in ife.__all__
        assert "CCEPanelEstimator" in ife.__all__


# ── 2. fit() ─────────────────────────────────────────────────────────────────


class TestIFEFit:
    """Test InteractiveFixedEffects.fit()."""

    def test_fit_r_max_2(self, ife_data):
        """fit(r_max=2) runs IFE estimation with 2 factors."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=2)
        assert result is not None
        assert result.estimator == "IFE"

    def test_fit_returns_iferesult(self, ife_data):
        """fit() returns IFEResult with beta, se, pval."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=2)
        assert hasattr(result, "beta")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")
        assert hasattr(result, "r_squared")

    def test_fit_with_bic3_criterion(self, ife_data):
        """fit() with criterion='BIC3' selects factors."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=3, criterion="BIC3")
        assert result.criterion == "BIC3"
        assert result.n_factors >= 1


# ── 3. Different criteria ─────────────────────────────────────────────────


class TestCriteria:
    """Test different factor selection criteria."""

    def test_bic1_criterion(self, ife_data):
        """criterion='BIC1' runs without error."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=2, criterion="BIC1")
        assert result.criterion == "BIC1"

    def test_aic_criterion(self, ife_data):
        """criterion='AIC' runs without error."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=2, criterion="AIC")
        assert result.criterion == "AIC"


# ── 4. get_factors() / get_loadings() ───────────────────────────────────────


class TestFactorsAndLoadings:
    """Test get_factors() and get_loadings() after fit()."""

    def test_get_factors_after_fit(self, ife_data):
        """get_factors() returns np.ndarray after fit()."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        factors = engine.get_factors()
        assert factors is not None
        assert isinstance(factors, np.ndarray)

    def test_get_loadings_after_fit(self, ife_data):
        """get_loadings() returns np.ndarray after fit()."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        loadings = engine.get_loadings()
        assert loadings is not None
        assert isinstance(loadings, np.ndarray)

    def test_factors_shape(self, ife_data):
        """Factors shape matches r_selected × T."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=2)
        factors = engine.get_factors()
        if factors is not None:
            assert factors.shape[0] == result.n_factors
            assert factors.shape[1] == t


# ── 5. CCE estimator ──────────────────────────────────────────────────────


class TestCCEPanelEstimator:
    """Test CCEPanelEstimator.fit()."""

    def test_cce_fit(self, ife_data):
        """CCEPanelEstimator.fit() runs CCE estimation."""
        from scripts.research_framework.interactive_fixed_effects import (
            CCEPanelEstimator,
        )

        n, t, _ = ife_data.shape
        est = CCEPanelEstimator(n_units=n, n_periods=t)
        result = est.fit(ife_data)
        assert result is not None
        assert result.estimator == "CCE"

    def test_cce_returns_iferesult(self, ife_data):
        """CCE returns IFEResult with beta, se, r_squared."""
        from scripts.research_framework.interactive_fixed_effects import (
            CCEPanelEstimator,
        )

        n, t, _ = ife_data.shape
        est = CCEPanelEstimator(n_units=n, n_periods=t)
        result = est.fit(ife_data)
        assert hasattr(result, "beta")
        assert hasattr(result, "se")
        assert hasattr(result, "r_squared")


# ── 6–7. summary() and to_latex() ───────────────────────────────────────


class TestSummaryAndLatex:
    """Test summary() DataFrame and to_latex()."""

    def test_summary_returns_dataframe(self, ife_data):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        summary_df = engine.summary(names=["x1", "x2"])
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "Coef" in summary_df.columns

    def test_to_latex_returns_string(self, ife_data):
        """to_latex() returns non-empty LaTeX string."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        latex_str = engine.to_latex(names=["x1", "x2"])
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str

    def test_cce_summary(self, ife_data):
        """CCE summary() returns DataFrame."""
        from scripts.research_framework.interactive_fixed_effects import (
            CCEPanelEstimator,
        )

        n, t, _ = ife_data.shape
        est = CCEPanelEstimator(n_units=n, n_periods=t)
        est.fit(ife_data)
        summary_df = est.summary(names=["x1", "x2"])
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty


# ── 8. r_max > data dimension ──────────────────────────────────────────────


class TestBoundaryCases:
    """Test boundary and edge cases."""

    def test_r_max_larger_than_reasonable(self, ife_data):
        """r_max > min(n,t) handles gracefully."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        # r_max=10 when n=100, t=20 — should still work
        result = engine.fit(ife_data, r_max=10)
        assert result is not None

    def test_small_sample_n5_t5(self, ife_small):
        """Small sample (n=5, t=5) handles gracefully."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_small.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_small, r_max=2)
        assert result is not None


# ── Additional: IFEResult dataclass ───────────────────────────────────────


class TestIFEResultDataclass:
    """Test IFEResult dataclass properties."""

    def test_ife_result_to_dict(self, ife_data):
        """IFEResult.to_dict() returns flat dict."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=1)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "estimator" in d
        assert "beta" in d

    def test_ife_result_sig_str(self, ife_data):
        """IFEResult.sig_str returns string."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        result = engine.fit(ife_data, r_max=1)
        sig = result.sig_str
        assert isinstance(sig, str)

    def test_get_unit_effects(self, ife_data):
        """get_unit_effects() returns np.ndarray after fit()."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, _ = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        effects = engine.get_unit_effects()
        assert effects is not None
        assert len(effects) == n


# ── Additional: predict() ───────────────────────────────────────────────────


class TestPredict:
    """Test predict() method."""

    def test_predict_in_sample(self, ife_data):
        """predict() works with same data shape."""
        from scripts.research_framework.interactive_fixed_effects import (
            InteractiveFixedEffects,
        )

        n, t, k = ife_data.shape
        engine = InteractiveFixedEffects(n_units=n, n_periods=t)
        engine.fit(ife_data, r_max=2)
        fitted = engine.predict(ife_data)
        assert isinstance(fitted, np.ndarray)
        assert len(fitted) == n * t


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
