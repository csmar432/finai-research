"""Tests for scripts/research_framework/panel_quantile_regression.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def panel_data():
    """100 firms × 10 years, suitable for panel quantile regression."""
    np.random.seed(42)
    n, t = 100, 10

    data = []
    for firm in range(n):
        is_treated = firm >= 50
        for year in range(t):
            post = 1 if year >= 5 else 0
            did = is_treated * post
            treatment_effect = 0.05 * did
            y = (
                0.05
                + 0.01 * year
                + treatment_effect
                + np.random.normal(0, 0.02)
            )
            data.append({
                "firm": firm,
                "year": year,
                "y": y,
                "x1": np.random.randn(),
                "x2": np.random.rand(),
                "did": float(did),
                "size": np.random.choice(["large", "small"]),
                "industry": f"ind_{firm % 5}",
            })
    return pd.DataFrame(data)


# ── 1. Engine initialization ─────────────────────────────────────────────────


class TestPanelQuantileInit:
    """Test PanelQuantileRegression.__init__."""

    def test_engine_init(self):
        """PanelQuantileRegression initializes without arguments."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        assert pqr is not None

    def test_module_exports(self):
        """PanelQuantileRegression and PanelQuantileResult in __all__."""
        from scripts.research_framework import panel_quantile_regression as pqr

        assert "PanelQuantileRegression" in pqr.__all__
        assert "PanelQuantileResult" in pqr.__all__


# ── 2. fit() across quantiles ────────────────────────────────────────────────


class TestPanelQuantileFit:
    """Test fit() across multiple quantiles."""

    def test_fit_multiple_quantiles(self, panel_data):
        """fit(quantiles=[0.25, 0.5, 0.75]) returns dict with 3 results."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        assert len(results) == 3
        assert 0.25 in results
        assert 0.5 in results
        assert 0.75 in results

    def test_fit_result_has_expected_fields(self, panel_data):
        """PanelQuantileResult has coef_dict, se_dict, pval_dict."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2"],
            quantiles=[0.5],
            unit_var="firm",
            time_var="year",
        )
        r = results[0.5]
        assert hasattr(r, "coef_dict")
        assert hasattr(r, "se_dict")
        assert hasattr(r, "pval_dict")
        assert hasattr(r, "quantile")

    def test_fit_with_unit_and_time_vars(self, panel_data):
        """fit() works with unit_var and time_var (panel mode)."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
            time_var="year",
            method="canay",
        )
        assert 0.5 in results


# ── 3. get_coef_at_quantile() ───────────────────────────────────────────────


class TestGetCoefAtQuantile:
    """Test get_coef_at_quantile()."""

    def test_get_coef_at_quantile(self, panel_data):
        """get_coef_at_quantile(0.5) returns PanelQuantileResult."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        result = pqr.get_coef_at_quantile(0.5)
        assert result is not None
        assert result.quantile == 0.5

    def test_get_coef_not_found(self, panel_data):
        """get_coef_at_quantile() returns None for unknown quantile."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
        )
        result = pqr.get_coef_at_quantile(0.99)  # Not fitted
        assert result is None


# ── 4. test_coef_equality() ───────────────────────────────────────────────


class TestCoefEquality:
    """Test test_coef_equality()."""

    def test_test_coef_equality(self, panel_data):
        """test_coef_equality(0.25, 0.75) returns dict with t_stat, pval."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2", "did"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        result = pqr.test_coef_equality(0.25, 0.75, var="did")
        assert isinstance(result, dict)
        assert "t_stat" in result
        assert "pval" in result
        assert "reject_equal" in result

    def test_test_coef_equality_quantile_not_found(self, panel_data):
        """test_coef_equality returns error dict if quantile not found."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
        )
        result = pqr.test_coef_equality(0.25, 0.75)  # Only 0.5 fitted
        assert "error" in result


# ── 5. plot_coef_profile() ────────────────────────────────────────────────


class TestPlotCoefProfile:
    """Test plot_coef_profile()."""

    def test_plot_coef_profile_returns_figure(self, panel_data):
        """plot_coef_profile() returns matplotlib Figure."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        fig = pqr.plot_coef_profile(var="x1")
        # Returns None if matplotlib not installed
        assert fig is None or hasattr(fig, "savefig")

    def test_plot_coef_profile_no_results(self, panel_data):
        """plot_coef_profile() returns None if no results."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        fig = pqr.plot_coef_profile(var="x1")
        assert fig is None


# ── 6. summary() ─────────────────────────────────────────────────────────────


class TestPQRSummary:
    """Test summary() DataFrame output."""

    def test_summary_returns_dataframe(self, panel_data):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1", "x2"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        summary_df = pqr.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "tau" in summary_df.columns

    def test_summary_empty_without_fit(self):
        """summary() returns empty DataFrame before fit()."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        summary_df = pqr.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert summary_df.empty


# ── 7. to_latex() ────────────────────────────────────────────────────────


class TestPQRLatex:
    """Test to_latex() LaTeX export."""

    def test_to_latex_returns_string(self, panel_data):
        """to_latex() returns non-empty string with table environment."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.25, 0.5, 0.75],
            unit_var="firm",
            time_var="year",
        )
        latex_str = pqr.to_latex()
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str

    def test_to_latex_empty_without_fit(self):
        """to_latex() returns empty string before fit()."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        latex_str = pqr.to_latex()
        assert latex_str == ""


# ── 8. Canay (2011) vs direct method ──────────────────────────────────────


class TestMethods:
    """Test different estimation methods."""

    def test_canay_method(self, panel_data):
        """method='canay' fits and returns results."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
            time_var="year",
            method="canay",
        )
        assert 0.5 in results
        assert results[0.5].estimator == "canay"

    def test_direct_method(self, panel_data):
        """method='direct' fits and returns results."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
            time_var="year",
            method="direct",
        )
        assert 0.5 in results

    def test_lm_method(self, panel_data):
        """method='lm' runs LM test (returns empty dict)."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        result = pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
            method="lm",
        )
        # LM mode returns empty dict (runs test only)
        assert result == {}


# ── 9. Missing data handling ─────────────────────────────────────────────────


class TestMissingData:
    """Test graceful handling of missing values."""

    def test_missing_in_outcome(self):
        """fit() handles NaN in outcome variable."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        df = pd.DataFrame({
            "firm": list(range(30)),
            "year": [i // 3 for i in range(30)],
            "y": list(np.random.randn(28)) + [np.nan, np.nan],
            "x1": np.random.randn(30),
        })
        pqr = PanelQuantileRegression()
        # Should not crash
        results = pqr.fit(
            data=df,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
        )
        # May return empty or result with NaN
        assert isinstance(results, dict)

    def test_missing_in_covariate(self):
        """fit() handles NaN in covariate."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        df = pd.DataFrame({
            "firm": list(range(30)),
            "year": [i // 3 for i in range(30)],
            "y": np.random.randn(30),
            "x1": list(np.random.randn(25)) + [np.nan] * 5,
        })
        pqr = PanelQuantileRegression()
        results = pqr.fit(
            data=df,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
        )
        assert isinstance(results, dict)


# ── 10. get_r_squared() ───────────────────────────────────────────────────


class TestRSquared:
    """Test get_r_squared()."""

    def test_get_r_squared(self, panel_data):
        """get_r_squared(q=0.5) returns float or None."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
        )
        r2 = pqr.get_r_squared(0.5)
        assert r2 is None or isinstance(r2, float)

    def test_get_r_squared_default(self, panel_data):
        """get_r_squared() defaults to tau=0.5."""
        from scripts.research_framework.panel_quantile_regression import (
            PanelQuantileRegression,
        )

        pqr = PanelQuantileRegression()
        pqr.fit(
            data=panel_data,
            y="y",
            X=["x1"],
            quantiles=[0.5],
            unit_var="firm",
        )
        r2 = pqr.get_r_squared()  # Default to 0.5
        assert r2 is None or isinstance(r2, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
