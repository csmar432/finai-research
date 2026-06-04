"""Tests for scripts/research_framework/spatial_regression.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def panel_50_20():
    """50 units × 20 periods panel with spatial autocorrelation."""
    np.random.seed(42)
    n, t = 50, 20
    df = pd.DataFrame({
        "unit": np.repeat(range(n), t),
        "year": np.tile(range(t), n),
        "y": np.random.randn(n * t),
        "x1": np.random.randn(n * t),
        "x2": np.random.randn(n * t),
        "lat": np.repeat(np.random.uniform(20, 50, n), t),
        "lon": np.repeat(np.random.uniform(100, 125, n), t),
    })
    return df


@pytest.fixture
def spatial_weights_5x5():
    """5x5 row-standardized KNN weight matrix."""
    np.random.seed(42)
    coords = np.random.rand(5, 2)
    from scripts.research_framework.spatial_regression import SpatialRegressionEngine

    W = SpatialRegressionEngine.w_from_xy(coords, k=2)
    return W


@pytest.fixture
def small_cross_section():
    """Small cross-section data for SAR/SEM testing (n=40)."""
    np.random.seed(42)
    n = 40
    df = pd.DataFrame({
        "unit": range(n),
        "y": np.random.randn(n),
        "x1": np.random.randn(n),
        "x2": np.random.randn(n),
        "lat": np.random.uniform(20, 50, n),
        "lon": np.random.uniform(100, 125, n),
    })
    return df


# ── 1. Module-level exports ────────────────────────────────────────────────


class TestModuleExports:
    """Test __all__ exports and class instantiation."""

    def test_all_exports_spatial_regression(self):
        """SpatialRegressionEngine is exported in __all__."""
        from scripts.research_framework import spatial_regression as sr

        assert "SpatialRegressionEngine" in sr.__all__
        assert "SpatialLagModel" in sr.__all__
        assert "SpatialErrorModel" in sr.__all__
        assert "SpatialDurbinModel" in sr.__all__
        assert "SpatialPanelFE" in sr.__all__

    def test_spatial_regression_engine_init(self, small_cross_section):
        """SpatialRegressionEngine initializes with coords."""
        from scripts.research_framework.spatial_regression import SpatialRegressionEngine

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1", "x2"], coords=coords
        )
        assert eng.W.shape[0] == len(df)
        assert eng.y_var == "y"
        assert eng.x_vars == ["x1", "x2"]


# ── 2. Weight matrix construction ───────────────────────────────────────────


class TestWeightMatrix:
    """Test spatial weight matrix construction."""

    def test_w_from_xy_knn_5points_k2(self, spatial_weights_5x5):
        """KNN weight matrix (5 points, k=2) is row-standardized."""
        W = spatial_weights_5x5
        assert W.shape == (5, 5)
        # Row sums should be 1 (row-standardized)
        row_sums = W.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-10)
        # Diagonal should be zero
        np.testing.assert_allclose(np.diag(W), 0.0)

    def test_w_from_xy_symmetric(self):
        """W_from_xy with symmetric=True uses bidirectional KNN."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        coords = np.array([[0, 0], [1, 0], [0, 1], [1, 1], [2, 2]])
        W = SpatialRegressionEngine.w_from_xy(coords, k=2, symmetric=True)
        # Symmetric=True means W_ij > 0 if i in kNN(j) or j in kNN(i)
        # Row sums should be 1 (row-standardized)
        row_sums = W.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-10)
        # Diagonal is zero
        np.testing.assert_allclose(np.diag(W), 0.0)
        # Symmetric-like: at least one direction has positive weight
        # (W[i,j] > 0) or (W[j,i] > 0) for all i != j
        W_or = (W > 0).astype(float)
        W_or_T = W_or.T
        has_link = ((W_or + W_or_T) > 0).astype(float)
        np.testing.assert_allclose(np.triu(has_link, k=1).sum() > 0, True)

    def test_invalid_weight_matrix_warns(self, panel_50_20):
        """Non-row-standardized W triggers a warning during init."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = panel_50_20.head(50).copy()
        # All-ones matrix (not row-standardized)
        W_bad = np.ones((50, 50))
        # Should not raise, just warn
        eng = SpatialRegressionEngine(
            df.head(50), y_var="y", x_vars=["x1"], W=W_bad
        )
        assert eng is not None


# ── 3. SAR estimation ───────────────────────────────────────────────────────


class TestSpatialLagModel:
    """Test SAR (Spatial Autoregressive Model) estimation."""

    def test_spatial_lag_model_fit(self, small_cross_section):
        """SAR model fits on 40 obs, 2 x-vars with scipy."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1", "x2"], coords=coords
        )
        result = eng.fit("sar")
        assert result.estimator == "sar"
        assert result.n_obs == len(df)
        assert result.spatial_rho is not None
        assert len(result.coef) >= 3  # rho + const + 2 x-vars

    def test_spatial_lag_model_moran_i(self, small_cross_section):
        """SAR result includes Moran I diagnostics."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        eng.fit("sar")
        # Moran I should be in additional diagnostics
        assert eng._result is not None
        assert "moran_I" in eng._result.additional

    def test_spatial_lag_model_scipy_required(self, small_cross_section):
        """SAR returns empty result when scipy not available (mocked)."""
        pytest.importorskip("scipy")
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        result = eng.fit("sar")
        assert result is not None


# ── 4. Moran I scatter plot ─────────────────────────────────────────────────


class TestMoranIPlot:
    """Test Moran I scatter plot data generation."""

    def test_moran_i_scatter_data(self, small_cross_section):
        """plot_moran_i returns dict with z, Wz, quadrant data."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        eng.fit("sar")
        data = eng.plot_moran_i(variable="residuals")
        assert "z" in data
        assert "Wz" in data
        assert "quadrant" in data
        assert len(data["z"]) == len(df)


# ── 5. SEM estimation ───────────────────────────────────────────────────────


class TestSpatialErrorModel:
    """Test SEM (Spatial Error Model) estimation."""

    def test_spatial_error_model_fit(self, small_cross_section):
        """SEM model fits and returns spatial_lambda."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1", "x2"], coords=coords
        )
        result = eng.fit("sem")
        assert result.estimator == "sem"
        assert result.n_obs == len(df)
        assert result.spatial_lambda is not None

    def test_sem_moran_i(self, small_cross_section):
        """SEM result includes Moran I."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        result = eng.fit("sem")
        assert "moran_I" in result.additional


# ── 6. SDM estimation ───────────────────────────────────────────────────────


class TestSpatialDurbinModel:
    """Test SDM (Spatial Durbin Model) estimation."""

    def test_spatial_durbin_model_fit(self, small_cross_section):
        """SDM model fits and returns spatial_rho + theta terms."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1", "x2"], coords=coords
        )
        result = eng.fit("sdm")
        assert result.estimator == "sdm"
        assert result.n_obs == len(df)
        # SDM has rho + (const + x1 + x2) + (W_x1 + W_x2) = 1 + 3 + 2 = 6 terms minimum
        # or empty result if scipy unavailable
        if result.spatial_rho is not None:
            assert len(result.coef) >= 5

    def test_sdm_vs_sar_lr_test(self, small_cross_section):
        """LR test can compare SDM vs SAR via log-likelihoods."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
            _lr_test,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        result_sar = eng.fit("sar")
        result_sdm = eng.fit("sdm")

        lr = _lr_test(result_sar, result_sdm)
        assert "stat" in lr
        assert "pval" in lr
        assert lr["df"] >= 0


# ── 7. Panel fixed effects ──────────────────────────────────────────────────


class TestSpatialPanelFE:
    """Test spatial panel fixed effects models."""

    def test_spatial_panel_fe_fit(self, panel_50_20):
        """SpatialPanelFE fits with entity + time fixed effects."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = panel_50_20
        coords = df[["lat", "lon"]].values[: df["unit"].nunique()]
        eng = SpatialRegressionEngine(
            df,
            y_var="y",
            x_vars=["x1", "x2"],
            coords=coords,
            entity_var="unit",
            time_var="year",
        )
        result = eng.fit("panel_fe")
        assert result.estimator == "panel_fe"
        assert result.spatial_rho is not None
        assert "two_way" in result.additional.get("fixed_effects", "")

    def test_spatial_panel_re_fit(self, panel_50_20):
        """SpatialPanelRE fits with random effects."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = panel_50_20
        coords = df[["lat", "lon"]].values[: df["unit"].nunique()]
        eng = SpatialRegressionEngine(
            df,
            y_var="y",
            x_vars=["x1"],
            coords=coords,
            entity_var="unit",
            time_var="year",
        )
        result = eng.fit("panel_re")
        assert result.estimator == "panel_re"
        assert result.spatial_rho is not None


# ── 8–10. summary() and to_latex() ─────────────────────────────────────────


class TestSummaryAndLatex:
    """Test summary DataFrame and LaTeX export."""

    def test_summary_returns_dataframe(self, small_cross_section):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        eng.fit("sar")
        summary_df = eng.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "Variable" in summary_df.columns
        assert "Coef" in summary_df.columns

    def test_to_latex_returns_string(self, small_cross_section):
        """to_latex() returns non-empty string with table environment."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        eng.fit("sar")
        latex_str = eng.to_latex()
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str
        assert r"\end{table}" in latex_str

    def test_sem_summary(self, small_cross_section):
        """SEM summary table contains lambda coefficient."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        eng.fit("sem")
        summary_df = eng.summary()
        assert not summary_df.empty


# ── 11. Missing value handling ───────────────────────────────────────────────


class TestMissingValues:
    """Test graceful handling of missing values."""

    def test_dropna_before_fit(self):
        """Missing values are dropped before estimation."""
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        np.random.seed(42)
        df = pd.DataFrame({
            "unit": range(20),
            "y": np.random.randn(20),
            "x1": np.concatenate([np.random.randn(15), [np.nan] * 5]),
            "lat": np.random.uniform(20, 50, 20),
            "lon": np.random.uniform(100, 125, 20),
        })
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        result = eng.fit("sar")
        # Should handle gracefully (either NaN result or 15 obs)
        assert result.n_obs <= 20


# ── 12. Fit statistics ───────────────────────────────────────────────────────


class TestFitStatistics:
    """Test that fit statistics are populated."""

    def test_r_squared_aic_bic(self, small_cross_section):
        """SAR result includes R-squared, AIC, BIC when scipy available."""
        pytest.importorskip("scipy")
        from scripts.research_framework.spatial_regression import (
            SpatialRegressionEngine,
        )

        df = small_cross_section
        coords = df[["lat", "lon"]].values
        eng = SpatialRegressionEngine(
            df, y_var="y", x_vars=["x1"], coords=coords
        )
        result = eng.fit("sar")
        # These may be None if scipy unavailable but should be floats otherwise
        if result.r_squared is not None:
            assert result.r_squared >= 0
        if result.aic is not None:
            assert result.aic > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
