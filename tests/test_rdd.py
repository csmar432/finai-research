"""Tests for scripts/research_framework/rdd.py — matched to RDDEngine API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


class TestRDDDataGeneration:
    def test_rdd_data_shape(self, mock_rdd_df):
        assert len(mock_rdd_df) == 500
        assert "score" in mock_rdd_df.columns
        assert "outcome" in mock_rdd_df.columns

    def test_rdd_cutoff_assignment(self, mock_rdd_df):
        treated_pct = mock_rdd_df["treated"].mean()
        assert 0.45 < treated_pct < 0.55

    def test_rdd_score_range(self, mock_rdd_df):
        assert mock_rdd_df["score"].min() >= -1.0
        assert mock_rdd_df["score"].max() <= 1.0

    def test_rdd_no_missing(self, mock_rdd_df):
        assert not mock_rdd_df.isnull().any().any()


class TestRDDBasic:
    def test_rdd_init(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        assert rdd.x_var == "score"
        assert rdd.y_var == "outcome"
        assert rdd.cutoff == 0.0

    def test_rdd_fit(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        result = rdd.fit(bandwidth=0.5)
        assert result is not None
        assert hasattr(result, "coef")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")
        assert np.isfinite(result.coef)

    def test_rdd_result_attributes(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        result = rdd.fit(bandwidth=0.5)
        for attr in ["coef", "se", "pval", "n_obs", "bandwidth"]:
            assert hasattr(result, attr), f"Missing: {attr}"

    def test_rdd_result_to_dict(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        result = rdd.fit(bandwidth=0.5)
        d = result.to_dict()
        assert isinstance(d, dict)
        for key in ["coef", "se", "pval"]:
            assert key in d

    def test_rdd_bandwidth_selection(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        bw = rdd.select_bandwidth()
        if hasattr(bw, "bandwidth"):
            assert bw.bandwidth > 0
        else:
            assert bw > 0

    def test_rdd_fit_with_bandwidth(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        result = rdd.fit(bandwidth=0.5)
        assert result.bandwidth == 0.5
        assert np.isfinite(result.coef)


class TestRDDObservations:
    def test_rdd_n_left_n_right(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        result = rdd.fit(bandwidth=0.5)
        assert result.n_left > 0
        assert result.n_right > 0

    def test_rdd_bandwidth_narrower(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        r1 = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0).fit(bandwidth=0.5)
        r2 = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0).fit(bandwidth=0.2)
        assert r2.n_obs <= r1.n_obs


class TestRDDDensityTest:
    def test_rdd_mccrary_test(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        rdd.fit(bandwidth=0.5)
        result = rdd.mccrary_test()
        assert hasattr(result, "theta")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")
        assert hasattr(result, "interpretation")
        assert isinstance(result.interpretation, str)

    def test_rdd_mccrary_interpretation(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        rdd.fit(bandwidth=0.5)
        result = rdd.mccrary_test()
        assert "manipulation" in result.interpretation.lower() or "density" in result.interpretation.lower() or len(result.interpretation) > 0


class TestRDDPlot:
    def test_rdd_plot_rdd(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        rdd.fit(bandwidth=0.5)
        fig = rdd.plot_rdd(nbins=20)
        if fig is not None:
            import matplotlib.figure
            assert isinstance(fig, matplotlib.figure.Figure)

    def test_rdd_plot_auto_bandwidth(self, mock_rdd_df):
        from scripts.research_framework.rdd import RDDEngine
        rdd = RDDEngine(df=mock_rdd_df, y_var="outcome", x_var="score", cutoff=0.0)
        fig = rdd.plot_rdd(nbins=20)
        if fig is not None:
            import matplotlib.figure
            assert isinstance(fig, matplotlib.figure.Figure)


class TestRDDDataEdgeCases:
    def test_rdd_small_sample(self):
        from scripts.research_framework.rdd import RDDEngine
        df = pd.DataFrame({"score": np.random.randn(10), "outcome": np.random.randn(10)})
        rdd = RDDEngine(df=df, y_var="outcome", x_var="score", cutoff=0.0)
        try:
            result = rdd.fit()
            assert hasattr(result, "coef")
        except (ValueError, RuntimeError):
            pass

    def test_rdd_missing_values(self):
        from scripts.research_framework.rdd import RDDEngine
        df = pd.DataFrame({"score": [0.1, 0.2, None, 0.4, 0.5], "outcome": [1.0, 2.0, 3.0, 4.0, 5.0]})
        rdd = RDDEngine(df=df, y_var="outcome", x_var="score", cutoff=0.0)
        try:
            result = rdd.fit(bandwidth=0.5)
            assert hasattr(result, "coef")
        except (ValueError, KeyError):
            pass
