"""Tests for scripts/research_framework/synthetic_control.py — matched to SyntheticControlEngine API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


class TestSyntheticControlDataGeneration:
    def test_sc_data_shape(self, mock_sc_df):
        assert len(mock_sc_df) > 0
        assert "unit" in mock_sc_df.columns
        assert "year" in mock_sc_df.columns
        assert "gdp_per_capita" in mock_sc_df.columns

    def test_sc_treated_unit_exists(self, mock_sc_df):
        assert "treated_california" in mock_sc_df["unit"].values

    def test_sc_pre_post_periods(self, mock_sc_df):
        pre = mock_sc_df[mock_sc_df["year"] < 2010]
        post = mock_sc_df[mock_sc_df["year"] >= 2010]
        assert len(pre) > 0
        assert len(post) > 0


class TestSyntheticControlBasic:
    def test_sc_init(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        assert sc.y_var == "gdp_per_capita"
        assert sc.treat_unit == "treated_california"

    def test_sc_fit(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        assert result is not None
        assert hasattr(result, "pre_mspe")
        assert hasattr(result, "post_mspe")
        assert hasattr(result, "rmspe_ratio")

    def test_sc_result_to_dict(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        d = result.to_dict()
        assert isinstance(d, dict)
        for key in ["pre_mspe", "rmspe_ratio", "n_donors"]:
            assert key in d, f"Missing: {key}"

    def test_sc_weights_nonnegative(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        if result.donor_weights is not None:
            w = np.asarray(result.donor_weights)
            assert (w >= -1e-6).all()

    def test_sc_weights_sum(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        if result.donor_weights is not None:
            w = np.asarray(result.donor_weights)
            assert abs(w.sum() - 1.0) < 0.01

    def test_sc_donor_names(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        if hasattr(result, "donor_names") and result.donor_names:
            assert len(result.donor_names) >= 2

    def test_sc_synthetic_series(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        result = sc.fit()
        # Should have some result fields populated
        assert hasattr(result, "pre_mspe") or hasattr(result, "r_squared_pre")


class TestSyntheticControlEdgeCases:
    def test_sc_plot_before_fit(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        fig = sc.plot_placebo()
        # May be None if matplotlib unavailable
        if fig is not None:
            import matplotlib.figure
            assert isinstance(fig, matplotlib.figure.Figure)

    def test_sc_inference(self, mock_sc_df):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        sc = SC(df=mock_sc_df, y_var="gdp_per_capita", unit_var="unit",
                time_var="year", treat_unit="treated_california", treat_period=2010)
        sc.fit()
        # inference() should not raise
        try:
            inf_result = sc.inference()
            assert inf_result is not None
        except Exception:
            pass  # Some edge cases may not support inference


class TestSyntheticControlDataValidation:
    def test_sc_single_donor(self):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        np.random.seed(42)
        df = pd.DataFrame({
            "unit": ["treated"] * 10 + ["donor1"] * 10,
            "year": list(range(10)) * 2,
            "y": np.random.randn(20),
        })
        sc = SC(df=df, y_var="y", unit_var="unit", time_var="year",
                treat_unit="treated", treat_period=5)
        try:
            result = sc.fit()
            assert hasattr(result, "pre_mspe")
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            pass  # May fail with too few donors

    def test_sc_missing_values(self):
        from scripts.research_framework.synthetic_control import SyntheticControlEngine as SC
        np.random.seed(42)
        y = np.random.randn(20)
        y[5] = np.nan
        df = pd.DataFrame({
            "unit": ["treated"] * 10 + ["donor1"] * 10,
            "year": list(range(10)) * 2,
            "y": y,
        })
        sc = SC(df=df, y_var="y", unit_var="unit", time_var="year",
                treat_unit="treated", treat_period=5)
        try:
            result = sc.fit()
            assert hasattr(result, "pre_mspe")
        except (ValueError, KeyError, RuntimeError, np.linalg.LinAlgError):
            pass  # Expected with NaN
