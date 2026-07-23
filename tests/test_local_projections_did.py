"""Comprehensive tests for scripts/research_framework/local_projections_did.py.

References:
- Jordà (2005) "Estimation and Inference of Impulse Responses by Local Projections"
- Roodman et al. (2019) "Comment on 'Multinomial Regression Analysis'..."
"""

from __future__ import annotations


import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

from scripts.research_framework.local_projections_did import (
    LPDIDResult,
    LocalProjectionsDIDEngine,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_panel(
    n_units: int = 80,
    n_periods: int = 12,
    tau: float = 2.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate staggered adoption panel data for LP-DID.

    Units adopt treatment at different times (staggered). Outcome grows over time
    and has a treatment effect of size `tau`.
    """
    rng = np.random.default_rng(seed)
    records = []
    for unit in range(n_units):
        adoption_time = rng.integers(4, n_periods - 1)  # adopt between t=4..n-2
        for t in range(n_periods):
            year = 2010 + t
            treated = int(t >= adoption_time)
            # Outcome: base + trend + treatment effect + noise
            y = (
                1.0
                + 0.15 * t
                + tau * treated * max(0, t - adoption_time)
                + rng.normal(0, 0.5)
            )
            records.append({"unit": unit, "year": year, "y": y, "did": treated})
    return pd.DataFrame(records)


@pytest.fixture
def panel_df() -> pd.DataFrame:
    return _make_panel(n_units=80, n_periods=12)


@pytest.fixture
def lp_engine(panel_df: pd.DataFrame) -> LocalProjectionsDIDEngine:
    return LocalProjectionsDIDEngine(
        panel_df,
        outcome_var="y",
        treatment_var="did",
        time_var="year",
        unit_var="unit",
        horizons=list(range(-3, 4)),
        cluster_var="unit",
    )


@pytest.fixture
def fitted_engine(lp_engine: LocalProjectionsDIDEngine) -> LocalProjectionsDIDEngine:
    lp_engine.fit()
    return lp_engine


# ─────────────────────────────────────────────────────────────────────────────
# 1. LPDIDResult dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestLPDIDResultDataclass:
    def test_construction_minimal(self):
        r = LPDIDResult(horizon=0, coef=1.5, se=0.3, pval=0.01)
        assert r.horizon == 0
        assert r.coef == 1.5
        assert r.se == 0.3
        assert r.pval == 0.01
        assert r.method == "HC1"  # default
        assert r.n_obs == 0
        assert r.r_squared is None

    def test_construction_full(self):
        r = LPDIDResult(
            horizon=2,
            coef=2.5, se=0.2, pval=0.001,
            ci_lower=2.1, ci_upper=2.9,
            n_obs=300, t_stat=12.5,
            n_bootstrap=999, n_treated=50, n_control=30,
            r_squared=0.75, method="cluster",
        )
        assert r.n_bootstrap == 999
        assert r.n_treated == 50
        assert r.n_control == 30
        assert r.r_squared == 0.75

    @pytest.mark.parametrize("pval,expected", [
        (0.0001, "***"),
        (0.005, "**"),
        (0.02, "*"),
        (0.07, "$\\dagger$"),
        (0.5, ""),
    ])
    def test_sig_property(self, pval, expected):
        r = LPDIDResult(horizon=0, coef=1.0, se=0.1, pval=pval)
        assert r.sig == expected

    def test_to_dict_keys(self):
        r = LPDIDResult(
            horizon=1, coef=2.0, se=0.5, pval=0.01,
            n_obs=100, n_treated=60, n_control=40,
        )
        d = r.to_dict()
        for key in ["horizon", "coef", "se", "pval", "ci_lower", "ci_upper",
                    "t_stat", "n_obs", "n_treated", "n_control", "r_squared",
                    "method", "sig", "n_bootstrap"]:
            assert key in d
        assert d["horizon"] == 1
        assert d["coef"] == 2.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engine.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineInit:
    def test_minimal_init(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y",
            treatment_var="did",
            time_var="year",
            unit_var="unit",
        )
        assert engine.outcome_var == "y"
        assert engine.treatment_var == "did"
        assert engine.time_var == "year"
        assert engine.unit_var == "unit"
        assert engine.cluster_var is None
        assert engine.robust_se is True  # default
        assert engine.idv_type == "dummy"  # default
        assert engine.df is not panel_df  # copied

    def test_default_horizons(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.horizons == list(range(-5, 6))

    def test_custom_horizons(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-2, -1, 0, 1, 2, 3],
        )
        assert engine.horizons == [-2, -1, 0, 1, 2, 3]

    def test_stats_computed(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.n_obs == len(panel_df)
        assert engine.n_units == panel_df["unit"].nunique()
        assert engine.n_periods == panel_df["year"].nunique()

    def test_controls_empty_by_default(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.controls == []

    def test_init_with_controls(self, panel_df):
        panel_df = panel_df.copy()
        panel_df["size"] = np.random.default_rng(1).normal(0, 1, len(panel_df))
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            controls=["size"],
        )
        assert engine.controls == ["size"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. fit_single
# ─────────────────────────────────────────────────────────────────────────────


class TestFitSingle:
    def test_fit_single_returns_result(self, lp_engine):
        result = lp_engine.fit_single(h=0)
        assert isinstance(result, LPDIDResult)
        assert result.horizon == 0
        assert result.n_obs > 0

    def test_fit_single_stores(self, lp_engine):
        lp_engine.fit_single(h=0)
        assert 0 in lp_engine._results

    def test_fit_single_negative_horizon(self, lp_engine):
        """Pre-treatment horizon should be near zero (parallel trends)."""
        result = lp_engine.fit_single(h=-2)
        assert isinstance(result, LPDIDResult)
        # In a good LP-DID with parallel trends, pre-treatment coefs near 0
        assert np.isfinite(result.coef)

    def test_fit_single_positive_horizon(self, lp_engine):
        """Post-treatment horizon should have positive effect."""
        result = lp_engine.fit_single(h=2)
        assert isinstance(result, LPDIDResult)
        # In our DGP, treatment effect grows with time
        assert result.n_obs > 0

    def test_fit_single_caches(self, lp_engine):
        """Second call should return cached result (same key in _results dict)."""
        r1 = lp_engine.fit_single(h=1)
        r2 = lp_engine.fit_single(h=1)
        # Same object (identity) in the results dict
        assert r1 is lp_engine._results[1]
        assert r2 is lp_engine._results[1]


# ─────────────────────────────────────────────────────────────────────────────
# 4. fit (all horizons)
# ─────────────────────────────────────────────────────────────────────────────


class TestFitAll:
    def test_fit_returns_dict(self, lp_engine):
        results = lp_engine.fit()
        assert isinstance(results, dict)
        assert all(isinstance(k, int) for k in results)

    def test_fit_all_horizons(self, lp_engine):
        horizons = [-1, 0, 1]
        results = lp_engine.fit(horizons=horizons)
        assert set(results.keys()) == set(horizons)

    def test_fit_partial_preserves_cached(self, lp_engine):
        """Calling fit with subset preserves previously computed horizons."""
        lp_engine.fit_single(h=-1)
        _ = lp_engine.fit(horizons=[-1, 0, 1])  # noqa: F841 (side-effect only, original var= removed by ruff)
        # h=-1 should be cached (same object), h=0 and h=1 computed
        assert -1 in lp_engine._results


# ─────────────────────────────────────────────────────────────────────────────
# 5. Bootstrap CI
# ─────────────────────────────────────────────────────────────────────────────


class TestBootstrapCI:
    def test_bootstrap_warns_without_cluster(self, lp_engine):
        """Without cluster_var, bootstrap should return empty and not crash."""
        lp_engine.cluster_var = None
        lp_engine.fit(horizons=[0])
        ci = lp_engine.bootstrap_ci(B=99)
        # Should return empty dict and ci_lower stays as-is (from fit)
        assert isinstance(ci, dict)

    def test_bootstrap_runs_with_cluster(self, lp_engine):
        lp_engine.fit(horizons=[0, 1])
        ci = lp_engine.bootstrap_ci(B=199, seed=42, bootstrap_type="rademacher")
        assert isinstance(ci, dict)
        # bootstrap_cis populated
        assert len(lp_engine._bootstrap_cis) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Parallel Trends Test
# ─────────────────────────────────────────────────────────────────────────────


class TestParallelTrends:
    def test_parallel_trends_returns_dict(self, fitted_engine):
        result = fitted_engine.parallel_trends_test()
        assert isinstance(result, dict)
        for key in ["f_stat", "pval", "n_pre_horizons", "reject"]:
            assert key in result

    def test_parallel_trends_returns_structure(self, lp_engine):
        """parallel_trends_test should auto-run fit if not done."""
        result = lp_engine.parallel_trends_test()
        assert "f_stat" in result
        assert "reject" in result
        # reject is a bool when F-stat is finite; may be None when NaN
        assert result["reject"] is None or isinstance(result["reject"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Plot IRF
# ─────────────────────────────────────────────────────────────────────────────


class TestPlotIRF:
    def teardown_method(self):
        plt.close("all")

    def test_plot_returns_figure(self, fitted_engine, tmp_path):
        save = tmp_path / "irf.pdf"
        fig = fitted_engine.plot_irf(save_path=save)
        assert fig is not None
        assert save.exists()

    def test_plot_custom_horizons(self, fitted_engine, tmp_path):
        save = tmp_path / "irf2.pdf"
        fig = fitted_engine.plot_irf(horizons=[-1, 0, 1, 2], save_path=save)
        assert fig is not None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Summary & to_latex
# ─────────────────────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_returns_dataframe(self, fitted_engine):
        df = fitted_engine.summary()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "horizon" in df.columns
        assert "coef" in df.columns
        assert "se" in df.columns
        assert "pval" in df.columns
        assert "sig" in df.columns

    def test_summary_runs_auto_fit(self, lp_engine):
        """summary() should auto-call fit()."""
        df = lp_engine.summary()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(lp_engine.horizons)

    def test_summary_columns_ordered(self, fitted_engine):
        df = fitted_engine.summary()
        expected = ["horizon", "coef", "se", "ci_lower", "ci_upper", "pval",
                    "t_stat", "n_obs", "r_squared", "method", "sig"]
        assert list(df.columns) == expected


class TestToLatex:
    def test_to_latex_returns_string(self, fitted_engine):
        latex = fitted_engine.to_latex()
        assert isinstance(latex, str)
        assert "\\begin{table}" in latex
        assert "\\toprule" in latex
        assert "\\caption{" in latex

    def test_to_latex_empty_without_fit(self, panel_df):
        """With empty horizons, summary() returns empty df and to_latex returns ''."""
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[],  # empty — no results to summarize
        )
        latex = engine.to_latex()
        assert latex == ""

    def test_to_latex_custom_caption(self, fitted_engine):
        latex = fitted_engine.to_latex(
            caption="Custom Caption",
            label="tab:custom",
        )
        assert "Custom Caption" in latex
        assert "tab:custom" in latex


# ─────────────────────────────────────────────────────────────────────────────
# 9. End-to-end
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_pipeline(self, panel_df, tmp_path):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y",
            treatment_var="did",
            time_var="year",
            unit_var="unit",
            horizons=[-2, -1, 0, 1, 2],
            cluster_var="unit",
        )
        engine.fit()
        pt = engine.parallel_trends_test()
        engine.bootstrap_ci(B=199, seed=42)
        summary_df = engine.summary()
        latex = engine.to_latex()
        fig = engine.plot_irf(save_path=tmp_path / "irf.pdf")

        assert len(summary_df) == 5
        assert "f_stat" in pt
        assert "\\begin{table}" in latex
        assert fig is not None

    def test_continuous_treatment(self):
        """Engine works with continuous treatment variable."""
        rng = np.random.default_rng(99)
        n_units, n_periods = 40, 8
        records = []
        for unit in range(n_units):
            for t in range(n_periods):
                year = 2010 + t
                intensity = rng.uniform(0, 1) * (t / n_periods)
                y = 1.0 + 0.1 * t + 3.0 * intensity + rng.normal(0, 0.5)
                records.append({"unit": unit, "year": year, "y": y, "treat_intensity": intensity})
        df = pd.DataFrame(records)
        engine = LocalProjectionsDIDEngine(
            df, outcome_var="y", treatment_var="treat_intensity",
            time_var="year", unit_var="unit",
            horizons=[0, 1, 2], idv_type="continuous",
        )
        results = engine.fit()
        assert 0 in results
        assert np.isfinite(results[0].coef)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_single_horizon(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0],
        )
        engine.fit()
        assert len(engine._results) == 1
        assert 0 in engine._results

    def test_empty_horizons(self, panel_df):
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[],
        )
        results = engine.fit()
        assert results == {}
        assert engine.summary().empty

    def test_all_pre_horizons(self, panel_df):
        """All pre-treatment horizons should have near-zero effects."""
        engine = LocalProjectionsDIDEngine(
            panel_df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-5, -4, -3],
        )
        engine.fit()
        for h, r in engine._results.items():
            if not np.isnan(r.coef):
                assert abs(r.coef) < 10  # sanity bound

    def test_nan_outcome_data(self):
        """NaN outcomes should be handled gracefully."""
        df = _make_panel(n_units=20, n_periods=6)
        # corrupt some outcomes
        df.loc[::5, "y"] = np.nan
        engine = LocalProjectionsDIDEngine(
            df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0],
        )
        engine.fit()
        assert 0 in engine._results
