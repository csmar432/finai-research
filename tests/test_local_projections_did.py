"""Tests for scripts/research_framework/local_projections_did.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def lp_did_data():
    """50 firms × 15 years, treatment starts at year 8."""
    np.random.seed(42)
    n, t = 50, 15
    treat_year = 8

    data = []
    for firm in range(n):
        is_treated = firm < 20  # first 20 firms are treated
        for year in range(t):
            post = 1 if year >= treat_year else 0
            did = is_treated * post
            # ROA with treatment effect
            roa = (
                0.05
                + 0.01 * year
                + 0.03 * did
                + np.random.normal(0, 0.02)
            )
            data.append({
                "firm": firm,
                "year": year,
                "roa": roa,
                "did": did,
                "size": np.random.uniform(18, 22),
                "lev": np.random.uniform(0.2, 0.8),
                "industry": f"ind_{firm % 5}",
            })
    return pd.DataFrame(data)


# ── 1. Engine initialization ────────────────────────────────────────────────────


class TestLocalProjectionsDIDInit:
    """Test LocalProjectionsDIDEngine.__init__."""

    def test_engine_init_default(self, lp_did_data):
        """Engine initializes with required parameters."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            cluster_var="industry",
        )
        assert eng.outcome_var == "roa"
        assert eng.treatment_var == "did"
        assert eng.time_var == "year"
        assert eng.unit_var == "firm"

    def test_engine_default_horizons(self, lp_did_data):
        """Default horizons are range(-5, 6)."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
        )
        assert eng.horizons == list(range(-5, 6))

    def test_module_exports(self):
        """LocalProjectionsDIDEngine and LPDIDResult are exported."""
        from scripts.research_framework import local_projections_did as lpdid

        assert "LocalProjectionsDIDEngine" in lpdid.__all__
        assert "LPDIDResult" in lpdid.__all__


# ── 2. fit() across horizons ──────────────────────────────────────────────────


class TestLPDIDFit:
    """Test fit() across multiple horizons."""

    def test_fit_all_horizons(self, lp_did_data):
        """fit(range(-3, 4)) returns results for all horizons."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            cluster_var="industry",
            horizons=list(range(-3, 4)),
        )
        results = eng.fit(horizons=list(range(-3, 4)))
        assert len(results) == 7
        assert all(h in results for h in range(-3, 4))

    def test_fit_result_has_expected_fields(self, lp_did_data):
        """fit() result (LPDIDResult) has coef, se, pval, ci_lower, ci_upper."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0],
        )
        results = eng.fit()
        assert 0 in results
        r = results[0]
        assert hasattr(r, "coef")
        assert hasattr(r, "se")
        assert hasattr(r, "pval")
        assert hasattr(r, "ci_lower")
        assert hasattr(r, "ci_upper")

    def test_fit_h0_horizon(self, lp_did_data):
        """h=0 is the treatment period (boundary case)."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0],
        )
        results = eng.fit()
        assert 0 in results


# ── 3. fit_single ─────────────────────────────────────────────────────────────


class TestLPDIDFitSingle:
    """Test fit_single() for a single horizon."""

    def test_fit_single_h2(self, lp_did_data):
        """fit_single(2) returns LPDIDResult for horizon h=2."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
        )
        result = eng.fit_single(2)
        assert result.horizon == 2
        assert isinstance(result.coef, float)

    def test_fit_single_returns_result(self, lp_did_data):
        """fit_single returns LPDIDResult."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
        )
        result = eng.fit_single(1)
        assert hasattr(result, "coef")
        assert hasattr(result, "se")


# ── 4. Bootstrap CI ─────────────────────────────────────────────────────────


class TestBootstrapCI:
    """Test bootstrap_ci() for confidence intervals."""

    def test_bootstrap_ci_small(self, lp_did_data):
        """bootstrap_ci(B=99) returns CI dict."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            cluster_var="industry",
            horizons=[0],
        )
        eng.fit()
        ci_result = eng.bootstrap_ci(B=99)
        # May return empty if no cluster_var or scipy missing
        assert isinstance(ci_result, dict)

    def test_bootstrap_without_cluster_warns(self, lp_did_data):
        """bootstrap_ci without cluster_var logs a warning."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            cluster_var=None,  # No cluster var
            horizons=[0],
        )
        eng.fit()
        # Should not crash
        ci_result = eng.bootstrap_ci(B=10)
        assert isinstance(ci_result, dict)


# ── 5. Parallel trends test ───────────────────────────────────────────────────


class TestParallelTrendsTest:
    """Test parallel_trends_test() joint F-test."""

    def test_parallel_trends_joint_test(self, lp_did_data):
        """parallel_trends_test() returns dict with f_stat, pval."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            cluster_var="industry",
            horizons=list(range(-3, 4)),
        )
        eng.fit()
        result = eng.parallel_trends_test()
        assert "f_stat" in result
        assert "pval" in result

    def test_parallel_trends_no_pre_horizons(self, lp_did_data):
        """Handles case with no pre-treatment horizons."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0, 1, 2],  # No pre-treatment
        )
        eng.fit()
        result = eng.parallel_trends_test()
        assert "f_stat" in result


# ── 6. IRF plot ──────────────────────────────────────────────────────────────


class TestIRFPlot:
    """Test plot_irf() IRF event study figure."""

    def test_plot_irf_returns_figure_or_none(self, lp_did_data):
        """plot_irf() returns matplotlib Figure or None (no file saved)."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=list(range(-2, 4)),
        )
        eng.fit()
        fig = eng.plot_irf()  # No save_path
        # Either returns a Figure or None (matplotlib may not be installed)
        import matplotlib

        if matplotlib.use != "agg":
            import matplotlib.pyplot as plt

            plt.close("all")

    def test_plot_irf_data_from_summary(self, lp_did_data):
        """IRF plot uses summary() data internally."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[-1, 0, 1],
        )
        eng.fit()
        summary_df = eng.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert "horizon" in summary_df.columns


# ── 7. summary() ─────────────────────────────────────────────────────────────


class TestLPDIDSummary:
    """Test summary() DataFrame output."""

    def test_summary_returns_dataframe(self, lp_did_data):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[-1, 0, 1],
        )
        eng.fit()
        summary_df = eng.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "horizon" in summary_df.columns
        assert "coef" in summary_df.columns
        assert "se" in summary_df.columns

    def test_summary_pre_trends(self, lp_did_data):
        """summary() includes pre-treatment horizons."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=list(range(-3, 3)),
        )
        eng.fit()
        summary_df = eng.summary()
        assert (summary_df["horizon"] < 0).any()  # pre-treatment


# ── 8. to_latex() ────────────────────────────────────────────────────────────


class TestLPDIDLatex:
    """Test to_latex() LaTeX export."""

    def test_to_latex_returns_string(self, lp_did_data):
        """to_latex() returns non-empty string with table environment."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[-1, 0, 1],
        )
        eng.fit()
        latex_str = eng.to_latex()
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str

    def test_to_latex_empty_if_no_results(self):
        """to_latex() handles case with too few obs gracefully."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = pd.DataFrame({
            "firm": [0, 1],
            "year": [0, 0],
            "roa": [0.1, 0.2],
            "did": [0, 1],
        })
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0],
        )
        # to_latex() calls summary() -> fit() internally
        # Should not crash; returns string (may be empty or valid LaTeX)
        latex_str = eng.to_latex()
        assert isinstance(latex_str, str)


# ── 9. Horizon=0 boundary ───────────────────────────────────────────────────


class TestBoundaryHorizon:
    """Test horizon=0 boundary case."""

    def test_horizon_0_result(self, lp_did_data):
        """h=0 returns LPDIDResult without crashing."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = lp_did_data
        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0],
        )
        result = eng.fit_single(0)
        assert result.horizon == 0
        # Should not be NaN (or should handle gracefully)
        assert isinstance(result.coef, float)


# ── 10. Missing data handling ───────────────────────────────────────────────


class TestMissingData:
    """Test graceful handling of missing values."""

    def test_missing_values_ignored(self):
        """Missing values in outcome are handled gracefully."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = pd.DataFrame({
            "firm": list(range(20)) * 3,
            "year": [0] * 20 + [1] * 20 + [2] * 20,
            "roa": list(np.random.randn(60)),
            "did": [1, 0] * 30,
        })
        # Introduce some NaN
        df.loc[5, "roa"] = np.nan
        df.loc[15, "roa"] = np.nan

        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            horizons=[0],
        )
        # Should not crash
        result = eng.fit_single(0)
        assert hasattr(result, "coef")

    def test_fit_with_nan_in_controls(self):
        """fit() handles NaN in control variables."""
        from scripts.research_framework.local_projections_did import (
            LocalProjectionsDIDEngine,
        )

        df = pd.DataFrame({
            "firm": list(range(20)) * 2,
            "year": [0] * 20 + [1] * 20,
            "roa": np.random.randn(40),
            "did": [1, 0] * 20,
            "size": list(np.random.randn(35)) + [np.nan] * 5,
        })

        eng = LocalProjectionsDIDEngine(
            df=df,
            outcome_var="roa",
            treatment_var="did",
            time_var="year",
            unit_var="firm",
            controls=["size"],
            horizons=[0],
        )
        # Should not crash
        eng.fit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
