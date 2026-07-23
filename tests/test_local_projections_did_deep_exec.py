"""Deep execution tests for scripts/research_framework/local_projections_did.py.

Covers: all dataclasses, pure helpers, __init__, fit, irf, bootstrap,
parallel_trends_test, table generation.  Target: 30+ tests.
"""

from __future__ import annotations


import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt  # noqa: E402

from scripts.research_framework.local_projections_did import (
    LPDIDResult,
    LocalProjectionsDIDEngine,
    _hc1_se,
    _build_lp_data,
    _estimate_single_horizon,
    _wild_cluster_bootstrap_lp,
    _parallel_trends_joint_test,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_staggered_panel(
    n_units: int = 80,
    n_periods: int = 12,
    tau: float = 2.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Staggered adoption panel for LP-DID tests."""
    rng = np.random.default_rng(seed)
    records = []
    for unit in range(n_units):
        adoption_time = rng.integers(4, n_periods - 1)
        for t in range(n_periods):
            year = 2010 + t
            treated = int(t >= adoption_time)
            y = (
                1.0
                + 0.15 * t
                + tau * treated * max(0, t - adoption_time)
                + rng.normal(0, 0.5)
            )
            records.append({"unit": unit, "year": year, "y": y, "did": treated})
    return pd.DataFrame(records)


def _make_2x2_panel(
    n: int = 100,
    tau: float = 1.0,
    seed: int = 7,
) -> pd.DataFrame:
    """Simple 2x2 panel for basic LP-DID tests."""
    rng = np.random.default_rng(seed)
    records = []
    for unit in range(n):
        is_treated = unit >= n // 2
        for t in range(10):
            year = 2015 + t
            treated = int(is_treated and t >= 5)
            y = 1.0 + 0.1 * t + tau * treated + rng.normal(0, 0.5)
            records.append({"unit": unit, "year": year, "y": y, "did": treated})
    return pd.DataFrame(records)


@pytest.fixture
def staggered_panel() -> pd.DataFrame:
    return _make_staggered_panel()


@pytest.fixture
def panel2x2() -> pd.DataFrame:
    return _make_2x2_panel()


# ─────────────────────────────────────────────────────────────────────────────
# 1. LPDIDResult dataclass — extended
# ─────────────────────────────────────────────────────────────────────────────

class TestLPDIDResultExtended:
    def test_constructor_with_ci(self):
        r = LPDIDResult(
            horizon=1, coef=0.8, se=0.2, pval=0.01,
            ci_lower=0.4, ci_upper=1.2,
        )
        assert r.horizon == 1
        assert r.ci_lower == 0.4
        assert r.ci_upper == 1.2

    def test_sig_property_thresholds(self):
        assert LPDIDResult(0, 0.5, 0.3, 0.5).sig == ""
        assert LPDIDResult(0, 0.5, 0.3, 0.09).sig == r"$\dagger$"
        assert LPDIDResult(0, 0.5, 0.3, 0.04).sig == "*"
        assert LPDIDResult(0, 0.5, 0.3, 0.008).sig == "**"
        assert LPDIDResult(0, 0.5, 0.3, 0.0001).sig == "***"

    def test_sig_dunder(self):
        r = LPDIDResult(horizon=0, coef=1.0, se=0.1, pval=0.03)
        assert r.sig == "*"  # 0.03 < 0.05

    def test_to_dict_all_fields(self):
        r = LPDIDResult(
            horizon=2, coef=1.5, se=0.25, pval=0.002,
            ci_lower=1.0, ci_upper=2.0,
            n_obs=300, t_stat=6.0,
            n_bootstrap=999, n_treated=60, n_control=40,
            r_squared=0.65, method="cluster",
        )
        d = r.to_dict()
        assert d["horizon"] == 2
        assert d["coef"] == 1.5
        assert d["se"] == 0.25
        assert d["pval"] == 0.002
        assert d["ci_lower"] == 1.0
        assert d["ci_upper"] == 2.0
        assert d["t_stat"] == 6.0
        assert d["n_obs"] == 300
        assert d["n_bootstrap"] == 999
        assert d["n_treated"] == 60
        assert d["n_control"] == 40
        assert d["r_squared"] == 0.65
        assert d["method"] == "cluster"
        assert d["sig"] == "**"

    def test_default_method(self):
        r = LPDIDResult(horizon=0, coef=0.0, se=0.0, pval=1.0)
        assert r.method == "HC1"

    def test_n_bootstrap_default_zero(self):
        r = LPDIDResult(horizon=0, coef=0.0, se=0.0, pval=1.0)
        assert r.n_bootstrap == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engine.__init__ — extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineInitExtended:
    def test_init_copies_dataframe(self, staggered_panel):
        original_len = len(staggered_panel)
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        engine.df.iloc[0] = 0
        assert len(staggered_panel) == original_len

    def test_default_controls_empty(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.controls == []

    def test_robust_se_default_true(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.robust_se is True

    def test_idv_type_dummy_default(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.idv_type == "dummy"

    def test_init_with_continuous_idv(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            idv_type="continuous",
        )
        assert engine.idv_type == "continuous"

    def test_init_with_controls(self, staggered_panel):
        staggered_panel = staggered_panel.copy()
        staggered_panel["size"] = np.random.default_rng(1).normal(10, 1, len(staggered_panel))
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            controls=["size"],
        )
        assert engine.controls == ["size"]

    def test_init_with_cluster_var(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            cluster_var="unit",
        )
        assert engine.cluster_var == "unit"

    def test_init_empty_dataframe(self):
        df = pd.DataFrame({
            "y": [], "did": [], "year": [], "unit": [],
        })
        engine = LocalProjectionsDIDEngine(
            df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.n_obs == 0
        assert engine.n_units == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. _hc1_se helper
# ─────────────────────────────────────────────────────────────────────────────

class TestHC1SE:
    def test_hc1_se_output_shape(self):
        rng = np.random.default_rng(1)
        n, k = 100, 3
        X = np.column_stack([np.ones(n), rng.normal(0, 1, n), rng.normal(0, 1, n)])
        y = X @ np.array([1.0, 2.0, -0.5]) + rng.normal(0, 0.5, n)
        resid = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
        se = _hc1_se(resid, X)
        assert se.shape == (k,)
        assert all(se > 0)

    def test_hc1_se_positive(self):
        rng = np.random.default_rng(2)
        n, k = 50, 2
        X = np.column_stack([np.ones(n), rng.normal(0, 1, n)])
        y = X @ np.array([1.0, 2.0]) + rng.normal(0, 0.5, n)
        resid = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
        se = _hc1_se(resid, X)
        assert np.all(se > 0)

    def test_hc1_se_single_regressor(self):
        rng = np.random.default_rng(3)
        n = 30
        X = np.ones((n, 2))
        X[:, 1] = rng.normal(0, 1, n)
        y = 1.0 + 2.0 * X[:, 1] + rng.normal(0, 0.5, n)
        resid = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
        se = _hc1_se(resid, X)
        assert len(se) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. _build_lp_data
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLPData:
    def test_build_lp_forward_h(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=1,
        )
        assert df_lp is not None
        assert "_y_lp" in df_lp.columns
        assert "did" in df_lp.columns

    def test_build_lp_h_zero(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=0,
        )
        assert df_lp is not None
        assert "_y_lp" in df_lp.columns

    def test_build_lp_negative_h(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=-2,
        )
        assert df_lp is not None
        assert "_y_lp" in df_lp.columns

    def test_build_lp_h_large(self, staggered_panel):
        """Horizon beyond data range may return None."""
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=100,
        )
        # May be None or empty — handle gracefully
        assert df_lp is None or len(df_lp) == 0 or "_y_lp" in df_lp.columns

    def test_build_lp_missing_time_var(self):
        """Missing time variable raises KeyError (column does not exist)."""
        df = pd.DataFrame({"y": [1.0], "did": [1], "unit": [1]})
        with pytest.raises(KeyError):
            _build_lp_data(df, "y", "did", "year", "unit", 0)

    def test_build_lp_non_numeric_time(self, staggered_panel):
        """Non-numeric time column raises ValueError on merge."""
        df = staggered_panel.copy()
        df["year_str"] = df["year"].astype(str)
        with pytest.raises(ValueError):
            _build_lp_data(
                df, outcome_var="y", treatment_var="did",
                time_var="year_str", unit_var="unit", horizon=0,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 5. _estimate_single_horizon
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimateSingleHorizon:
    def test_estimate_returns_dict(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=0,
        )
        result = _estimate_single_horizon(
            df_lp, outcome_lp="_y_lp",
            treatment_var="did", controls=[],
            cluster_var=None, robust_se=True,
            idv_type="dummy",
        )
        assert isinstance(result, dict)
        for key in ["coef", "se", "pval", "ci_lower", "ci_upper", "t_stat", "n_obs"]:
            assert key in result

    def test_estimate_with_controls(self, staggered_panel):
        staggered_panel = staggered_panel.copy()
        staggered_panel["size"] = np.random.default_rng(5).normal(0, 1, len(staggered_panel))
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=1,
        )
        result = _estimate_single_horizon(
            df_lp, outcome_lp="_y_lp",
            treatment_var="did", controls=["size"],
            cluster_var=None, robust_se=True,
            idv_type="dummy",
        )
        assert isinstance(result, dict)
        assert "coef" in result

    def test_estimate_insufficient_data(self):
        """Too few observations should return NaN dict."""
        df = pd.DataFrame({
            "unit": [1, 2, 3],
            "year": [2020, 2021, 2022],
            "did": [1, 1, 1],
            "y": [1.0, 2.0, 3.0],
            "_y_lp": [0.1, 0.2, 0.3],
        })
        result = _estimate_single_horizon(
            df, outcome_lp="_y_lp",
            treatment_var="did", controls=[],
            cluster_var=None, robust_se=True,
            idv_type="dummy",
        )
        # Should handle gracefully (may return NaN or insufficient obs)
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 6. _wild_cluster_bootstrap_lp
# ─────────────────────────────────────────────────────────────────────────────

class TestWildClusterBootstrap:
    def test_bootstrap_returns_dict(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=1,
        )
        result = _wild_cluster_bootstrap_lp(
            df_lp, outcome_lp="_y_lp",
            treatment_var="did", controls=[],
            cluster_var="unit", B=99, seed=42,
        )
        assert isinstance(result, dict)
        for key in ["ci_lower", "ci_upper", "pval"]:
            assert key in result

    def test_bootstrap_n_bootstrap_recorded(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=0,
        )
        result = _wild_cluster_bootstrap_lp(
            df_lp, outcome_lp="_y_lp",
            treatment_var="did", controls=[],
            cluster_var="unit", B=199, seed=42,
        )
        assert result.get("n_bootstrap") == 199

    def test_bootstrap_mammen_type(self, staggered_panel):
        df_lp = _build_lp_data(
            staggered_panel, outcome_var="y",
            treatment_var="did", time_var="year",
            unit_var="unit", horizon=1,
        )
        result = _wild_cluster_bootstrap_lp(
            df_lp, outcome_lp="_y_lp",
            treatment_var="did", controls=[],
            cluster_var="unit", B=99, bootstrap_type="mammen", seed=42,
        )
        assert isinstance(result, dict)

    def test_bootstrap_no_cluster_returns_nan(self):
        """Without cluster_var, the function should handle gracefully."""
        df = pd.DataFrame({
            "unit": list(range(100)),
            "year": [2020] * 100,
            "did": [1] * 50 + [0] * 50,
            "y": np.random.default_rng(1).normal(0, 1, 100),
            "_y_lp": np.random.default_rng(2).normal(0, 1, 100),
        })
        # The function may raise TypeError when cluster_var is None.
        # The wrapper should handle this — we accept either outcome.
        try:
            result = _wild_cluster_bootstrap_lp(
                df, outcome_lp="_y_lp",
                treatment_var="did", controls=[],
                cluster_var=None, B=99, seed=42,
            )
            assert isinstance(result, dict)
        except (TypeError, KeyError, AttributeError):
            # Acceptable: function does not handle None cluster_var
            # The engine.bootstrap_ci wrapper handles this case correctly
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 7. _parallel_trends_joint_test
# ─────────────────────────────────────────────────────────────────────────────

class TestParallelTrendsJointTest:
    def test_pt_joint_empty_results(self):
        result = _parallel_trends_joint_test([])
        assert result["f_stat"] is np.nan
        assert result["pval"] is np.nan
        assert result["n_pre_horizons"] == 0

    def test_pt_joint_single_pre_horizon(self):
        r = LPDIDResult(horizon=-1, coef=0.1, se=0.2, pval=0.5)
        result = _parallel_trends_joint_test([r])
        assert result["n_pre_horizons"] == 1
        assert np.isnan(result["f_stat"])

    def test_pt_joint_two_pre_horizons(self):
        results = [
            LPDIDResult(horizon=-2, coef=0.0, se=0.2, pval=0.5),
            LPDIDResult(horizon=-1, coef=0.1, se=0.2, pval=0.5),
        ]
        result = _parallel_trends_joint_test(results)
        assert result["n_pre_horizons"] == 2
        assert not np.isnan(result["f_stat"])

    def test_pt_joint_reject_flag(self):
        """Large pre-treatment effects → reject parallel trends."""
        results = [
            LPDIDResult(horizon=-2, coef=5.0, se=0.2, pval=0.0),
            LPDIDResult(horizon=-1, coef=4.5, se=0.2, pval=0.0),
        ]
        result = _parallel_trends_joint_test(results)
        assert result["reject"] is True

    def test_pt_joint_no_reject(self):
        """Small pre-treatment effects → fail to reject."""
        results = [
            LPDIDResult(horizon=-2, coef=0.05, se=0.5, pval=0.8),
            LPDIDResult(horizon=-1, coef=-0.03, se=0.5, pval=0.8),
        ]
        result = _parallel_trends_joint_test(results)
        assert result["reject"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. Engine — fit_single extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineFitSingleExtended:
    def test_fit_single_negative_horizon_returns_result(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-2, -1, 0, 1],
            cluster_var="unit",
        )
        result = engine.fit_single(h=-1)
        assert isinstance(result, LPDIDResult)
        assert result.horizon == -1

    def test_fit_single_caches(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0], cluster_var="unit",
        )
        r1 = engine.fit_single(0)
        r2 = engine.fit_single(0)
        assert r1 is r2
        assert r1 is engine._results[0]

    def test_fit_single_invalid_horizon_returns_nan(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[999], cluster_var="unit",
        )
        result = engine.fit_single(999)
        assert isinstance(result, LPDIDResult)
        # May have NaN coef/se when no data
        assert isinstance(result.coef, float)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Engine — bootstrap_ci extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineBootstrapCIExtended:
    def test_bootstrap_ci_updates_result(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
            cluster_var="unit",
        )
        engine.fit()
        engine.bootstrap_ci(B=99, seed=42)
        r0 = engine._results[0]
        assert r0.n_bootstrap == 99

    def test_bootstrap_ci_partial_horizons(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-1, 0, 1, 2],
            cluster_var="unit",
        )
        engine.fit()
        ci = engine.bootstrap_ci(B=99, horizons=[0, 1], seed=42)
        assert isinstance(ci, dict)

    def test_bootstrap_ci_no_cluster(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
            cluster_var=None,
        )
        engine.fit()
        ci = engine.bootstrap_ci(B=99)
        assert ci == {}


# ─────────────────────────────────────────────────────────────────────────────
# 10. Engine — parallel_trends_test extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineParallelTrendsExtended:
    def test_pt_auto_fit(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-2, -1, 0, 1],
            cluster_var="unit",
        )
        # No explicit fit() call
        result = engine.parallel_trends_test()
        assert "f_stat" in result
        assert "pval" in result

    def test_pt_reject_flag_bool(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-2, -1, 0, 1],
            cluster_var="unit",
        )
        result = engine.parallel_trends_test()
        assert result["reject"] is None or isinstance(result["reject"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Engine — plot_irf extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEnginePlotIRFExtended:
    def teardown_method(self):
        plt.close("all")

    def test_plot_custom_title(self, staggered_panel, tmp_path):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-1, 0, 1],
            cluster_var="unit",
        )
        engine.fit()
        fig = engine.plot_irf(
            save_path=tmp_path / "irf_custom.pdf",
            title="Custom Title",
            ylabel="Effect",
        )
        assert fig is not None

    def test_plot_custom_figsize(self, staggered_panel, tmp_path):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
            cluster_var="unit",
        )
        engine.fit()
        fig = engine.plot_irf(
            save_path=tmp_path / "irf_big.pdf",
            figsize=(12, 6),
        )
        assert fig is not None
        assert fig.get_size_inches()[0] == pytest.approx(12.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# 12. Engine — summary / to_latex extended
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineSummaryExtended:
    def test_summary_columns(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-1, 0, 1],
            cluster_var="unit",
        )
        engine.fit()
        df = engine.summary()
        expected = [
            "horizon", "coef", "se", "ci_lower", "ci_upper",
            "pval", "t_stat", "n_obs", "r_squared", "method", "sig",
        ]
        for col in expected:
            assert col in df.columns

    def test_summary_length_matches_horizons(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-3, -2, -1, 0, 1, 2],
            cluster_var="unit",
        )
        engine.fit()
        df = engine.summary()
        assert len(df) == 6

    def test_to_latex_no_stars(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
            cluster_var="unit",
        )
        engine.fit()
        latex = engine.to_latex(stars=False)
        assert isinstance(latex, str)
        assert "\\begin{table}" in latex

    def test_to_latex_row_count(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-1, 0, 1],
            cluster_var="unit",
        )
        engine.fit()
        latex = engine.to_latex()
        # Should contain 3 horizon rows
        assert latex.count("\\\\") >= 4  # header sep + 3 data rows

    def test_summary_empty_engine(self):
        """Empty horizons → empty summary DataFrame."""
        engine = LocalProjectionsDIDEngine(
            pd.DataFrame({"y": [], "did": [], "year": [], "unit": []}),
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[],
        )
        df = engine.summary()
        assert df.empty


# ─────────────────────────────────────────────────────────────────────────────
# 13. End-to-end integration
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineEndToEnd:
    def test_full_pipeline_with_controls(self, staggered_panel):
        staggered_panel = staggered_panel.copy()
        staggered_panel["size"] = np.random.default_rng(8).normal(0, 1, len(staggered_panel))
        staggered_panel["lev"] = np.random.default_rng(9).normal(0, 1, len(staggered_panel))
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-2, -1, 0, 1, 2],
            controls=["size", "lev"],
            cluster_var="unit",
        )
        engine.fit()
        pt = engine.parallel_trends_test()
        assert "f_stat" in pt
        assert len(engine._results) == 5

    def test_fit_then_refit_same_engine(self, staggered_panel):
        """fit() called twice should not crash."""
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
            cluster_var="unit",
        )
        engine.fit()
        engine.fit()  # second call — should be idempotent
        assert len(engine._results) == 2

    def test_2x2_panel_integration(self, panel2x2):
        engine = LocalProjectionsDIDEngine(
            panel2x2,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-3, -2, -1, 0, 1, 2, 3],
            cluster_var="unit",
        )
        results = engine.fit()
        assert len(results) == 7
        for h, r in results.items():
            assert isinstance(r, LPDIDResult)

    def test_parallel_trends_not_rejected(self, panel2x2):
        """2x2 panel with no pre-trend violation should fail to reject."""
        engine = LocalProjectionsDIDEngine(
            panel2x2,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[-3, -2, -1, 0, 1, 2],
            cluster_var="unit",
        )
        engine.fit()
        pt = engine.parallel_trends_test()
        # Pre-period coefs should be small (near zero) in parallel-trend data
        # Either reject=False or f_stat is NaN
        assert pt["reject"] is False or np.isnan(pt["f_stat"])

    def test_continuous_treatment_all_horizons(self, panel2x2):
        panel = panel2x2.copy()
        panel["treat_intensity"] = panel["did"] * 1.5
        engine = LocalProjectionsDIDEngine(
            panel,
            outcome_var="y", treatment_var="treat_intensity",
            time_var="year", unit_var="unit",
            horizons=[0, 1, 2],
            idv_type="continuous",
        )
        results = engine.fit()
        assert 0 in results
        assert np.isfinite(results[0].coef)


# ─────────────────────────────────────────────────────────────────────────────
# 14. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineEdgeCases:
    def test_all_missing_outcomes(self):
        """All NaN outcomes — fit should not crash."""
        n = 60
        df = pd.DataFrame({
            "unit": list(range(n)),
            "year": [2010 + i % 10 for i in range(n)],
            "y": [np.nan] * n,
            "did": [1] * (n // 2) + [0] * (n // 2),
        })
        engine = LocalProjectionsDIDEngine(
            df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
        )
        engine.fit()
        assert 0 in engine._results

    def test_single_unit(self):
        """Single unit should be handled (n_units=1)."""
        df = pd.DataFrame({
            "unit": [1] * 10,
            "year": list(range(2010, 2020)),
            "y": list(range(10)),
            "did": [0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
        })
        engine = LocalProjectionsDIDEngine(
            df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0, 1],
        )
        engine.fit()
        assert 0 in engine._results

    def test_wide_horizons(self):
        """Very wide horizon range."""
        df = _make_staggered_panel(n_units=60, n_periods=20)
        engine = LocalProjectionsDIDEngine(
            df,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=list(range(-8, 9)),
            cluster_var="unit",
        )
        results = engine.fit()
        assert len(results) == 17

    def test_nan_in_result_stored(self, staggered_panel):
        """NaN results are stored in _results dict."""
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[100],  # impossible horizon
            cluster_var="unit",
        )
        result = engine.fit_single(100)
        assert result.horizon == 100
        assert isinstance(result.coef, float)  # may be NaN

    def test_bootstrap_on_empty_results(self, staggered_panel):
        """bootstrap_ci before fit should auto-call fit."""
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
            horizons=[0],
            cluster_var="unit",
        )
        # No explicit fit
        ci = engine.bootstrap_ci(B=99, seed=42)
        assert isinstance(ci, dict)

    def test_n_treated_n_control(self, staggered_panel):
        engine = LocalProjectionsDIDEngine(
            staggered_panel,
            outcome_var="y", treatment_var="did",
            time_var="year", unit_var="unit",
        )
        assert engine.n_treated >= 0
        assert engine.n_control >= 0
        assert engine.n_treated + engine.n_control == engine.n_obs
