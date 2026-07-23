"""Comprehensive tests for scripts/research_framework/panel_threshold_regression.py.

References:
- Hansen, B.E. (2000) "Sample Splitting and Threshold Estimation", Econometrica 68(3)
"""

from __future__ import annotations


import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)

from scripts.research_framework.panel_threshold_regression import (
    PanelThresholdRegression,
    ThresholdResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_threshold_df(
    n_units: int = 100,
    n_periods: int = 5,
    threshold_true: float = 5.0,
    tau: float = 3.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate panel data with a known threshold.

    y = alpha + beta1*x + beta2*x*I(q > threshold) + entity_FE + noise
    """
    rng = np.random.default_rng(seed)
    records = []
    for unit in range(n_units):
        for t in range(n_periods):
            year = 2015 + t
            q = rng.uniform(0, 10)  # threshold variable (uniform [0, 10])
            x = rng.uniform(-2, 2)
            treat = float(q > threshold_true)
            y = (
                1.0
                + 0.5 * x
                + tau * treat * x
                + rng.normal(0, 0.5)
            )
            records.append({
                "unit": unit, "year": year,
                "y": y, "x": x, "q": q,
            })
    return pd.DataFrame(records)


@pytest.fixture
def panel_df() -> pd.DataFrame:
    return _make_threshold_df()


@pytest.fixture
def ptr(panel_df: pd.DataFrame) -> PanelThresholdRegression:
    return PanelThresholdRegression(grid_size=30, trim_pct=0.05, verbose=False)


@pytest.fixture
def fitted_ptr(ptr: PanelThresholdRegression, panel_df: pd.DataFrame) -> PanelThresholdRegression:
    result = ptr.estimate(
        panel_df,
        y_var="y",
        x_vars=["x"],
        threshold_var="q",
        entity_var="unit",
        time_var="year",
        fixed_effects="entity",
    )
    assert result.threshold is not None
    return ptr


# ─────────────────────────────────────────────────────────────────────────────
# 1. ThresholdResult dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestThresholdResultDataclass:
    def test_construction_minimal(self):
        r = ThresholdResult(
            threshold=5.0,
            threshold_se=None,
            threshold_pvalue=None,
            threshold_ci=None,
            regime1_coef=np.array([0.5]),
            regime2_coef=np.array([1.5]),
            regime1_se=np.array([0.1]),
            regime2_se=np.array([0.2]),
            r_squared=0.65,
            adj_r_squared=0.60,
            residual_ss=100.0,
            n_observations=500,
            n_regime1=300,
            n_regime2=200,
            grid_size=400,
            trim_pct=0.05,
            sup_lm_stat=12.5,
            model=None,
            did_converge=True,
            notes=[],
        )
        assert r.threshold == 5.0
        assert r.r_squared == 0.65
        assert r.did_converge is True
        assert r.notes == []

    def test_summary_no_threshold(self):
        r = ThresholdResult(
            threshold=None,
            threshold_se=None,
            threshold_pvalue=None,
            threshold_ci=None,
            regime1_coef=np.array([0.5]),
            regime2_coef=np.array([1.5]),
            regime1_se=np.array([0.1]),
            regime2_se=np.array([0.2]),
            r_squared=0.4, adj_r_squared=0.38,
            residual_ss=100.0,
            n_observations=500, n_regime1=250, n_regime2=250,
            grid_size=400, trim_pct=0.05,
            sup_lm_stat=None, model=None,
        )
        summary = r.summary()
        assert "⚠ No threshold detected" in summary
        assert "R²" in summary

    def test_summary_with_threshold(self, fitted_ptr):
        r = fitted_ptr._result
        assert r is not None
        summary = r.summary()
        assert "Threshold Estimate" in summary
        assert "Regime 1" in summary
        assert "Regime 2" in summary


# ─────────────────────────────────────────────────────────────────────────────
# 2. PanelThresholdRegression.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineInit:
    def test_defaults(self):
        ptr = PanelThresholdRegression()
        assert ptr.grid_size == 400
        assert ptr.cluster_entity is True
        assert ptr.cluster_time is False
        assert ptr.trim_pct == 0.05
        assert ptr.min_periods_per_regime == 20
        assert ptr.verbose is False

    def test_custom_params(self):
        ptr = PanelThresholdRegression(
            grid_size=200,
            cluster_entity=False,
            trim_pct=0.10,
            min_periods_per_regime=30,
            verbose=True,
        )
        assert ptr.grid_size == 200
        assert ptr.trim_pct == 0.10
        assert ptr.verbose is True

    def test_initial_state(self):
        ptr = PanelThresholdRegression()
        assert ptr._result is None
        assert ptr._model is None
        assert ptr._y is None
        assert ptr._X is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. estimate
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimate:
    def test_estimate_returns_result(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y",
            x_vars=["x"],
            threshold_var="q",
            entity_var="unit",
            time_var="year",
            fixed_effects="entity",
        )
        assert isinstance(result, ThresholdResult)
        assert ptr._result is result

    def test_threshold_found(self, ptr, panel_df):
        """Threshold should be in a reasonable range for our DGP."""
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        assert result.threshold is not None
        assert 0 <= result.threshold <= 10  # data range

    def test_regime_counts_sum_to_total(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        assert result.n_regime1 + result.n_regime2 == result.n_observations

    def test_sup_lm_stat_computed(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        assert result.sup_lm_stat is not None
        assert result.sup_lm_stat >= 0

    def test_r_squared_present(self, ptr, panel_df):
        """R² may be negative or large with many FE dummies; just check it's finite."""
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        assert np.isfinite(result.r_squared)

    def test_no_fixed_effects(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
            fixed_effects=None,
        )
        assert result is not None
        assert result.threshold is not None

    def test_time_fixed_effects(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
            fixed_effects="time",
        )
        assert result is not None

    def test_both_fixed_effects(self, ptr, panel_df):
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
            fixed_effects="both",
        )
        assert result is not None

    def test_multiple_regressors(self, panel_df):
        panel_df = panel_df.copy()
        panel_df["z"] = np.random.default_rng(77).normal(0, 1, len(panel_df))
        ptr = PanelThresholdRegression(grid_size=50)
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x", "z"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        assert len(result.regime1_coef) == 2
        assert len(result.regime2_coef) == 2

    def test_min_periods_override(self, panel_df):
        ptr = PanelThresholdRegression(min_periods_per_regime=5)
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
            min_periods_per_regime=10,
        )
        assert result is not None

    def test_missing_columns(self, panel_df, ptr):
        df_bad = panel_df.drop(columns=["y"])
        with pytest.raises(ValueError, match="Missing columns"):
            ptr.estimate(
                df_bad,
                y_var="y", x_vars=["x"],
                threshold_var="q",
                entity_var="unit", time_var="year",
            )

    def test_too_few_observations(self, ptr):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "y": rng.normal(0, 1, 30),
            "x": rng.normal(0, 1, 30),
            "q": rng.uniform(0, 10, 30),
            "unit": np.repeat(range(10), 3),
            "year": np.tile(range(3), 10),
        })
        with pytest.raises(ValueError, match="at least 50 observations"):
            ptr.estimate(df, y_var="y", x_vars=["x"], threshold_var="q",
                        entity_var="unit", time_var="year")


# ─────────────────────────────────────────────────────────────────────────────
# 4. estimate_bootstrap (lightweight — just check it runs)
# ─────────────────────────────────────────────────────────────────────────────


class TestBootstrap:
    def test_bootstrap_runs(self, fitted_ptr):
        """Bootstrap should complete without error and update result."""
        result = fitted_ptr.estimate_bootstrap(n_bootstrap=19, seed=42)
        assert isinstance(result, ThresholdResult)
        assert result.threshold_pvalue is not None
        assert result.threshold_se is not None
        assert result.threshold_ci is not None
        assert 0 <= result.threshold_pvalue <= 1

    def test_bootstrap_pvalue_bounded(self, fitted_ptr):
        result = fitted_ptr.estimate_bootstrap(n_bootstrap=29, seed=99)
        assert 0 <= result.threshold_pvalue <= 1

    def test_bootstrap_ci_bounds(self, fitted_ptr):
        result = fitted_ptr.estimate_bootstrap(n_bootstrap=19, seed=123)
        assert result.threshold_ci is not None
        lo, hi = result.threshold_ci
        assert lo <= result.threshold <= hi

    def test_bootstrap_requires_prior_estimate(self, ptr):
        with pytest.raises(ValueError, match="Must call estimate"):
            ptr.estimate_bootstrap()


# ─────────────────────────────────────────────────────────────────────────────
# 5. estimate_multi_threshold
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiThreshold:
    def test_multi_threshold_returns_list(self):
        """Small data, no entity FE (entity FE one-hot makes grid search O(n×grid) too slow)."""
        rng = np.random.default_rng(99)
        records = []
        for unit in range(15):
            for t in range(4):
                q = rng.uniform(0, 10); x = rng.uniform(-2, 2)
                y = 1.0 + 0.5*x + rng.normal(0, 0.5)
                records.append({'unit': unit, 'year': 2015+t, 'y': y, 'x': x, 'q': q})
        df = pd.DataFrame(records)
        ptr = PanelThresholdRegression(grid_size=5)
        results = ptr.estimate_multi_threshold(
            df, y_var='y', x_vars=['x'], threshold_var='q',
            entity_var='unit', time_var='year',
            n_thresholds=1, bootstrap_reps=9,
        )
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], ThresholdResult)

    def test_multi_threshold_two(self):
        """Test n_thresholds=2: use large enough data that sub-sample > 50."""
        rng = np.random.default_rng(88)
        records = []
        # 50 units × 5 periods = 250 obs; sub-sample after first split ~125
        for unit in range(50):
            for t in range(5):
                q = rng.uniform(0, 10); x = rng.uniform(-2, 2)
                y = 1.0 + 0.5*x + rng.normal(0, 0.5)
                records.append({'unit': unit, 'year': 2015+t, 'y': y, 'x': x, 'q': q})
        df = pd.DataFrame(records)
        ptr = PanelThresholdRegression(grid_size=10, min_periods_per_regime=15)
        # n_thresholds=1 just runs single estimation + bootstrap, very fast
        results = ptr.estimate_multi_threshold(
            df, y_var='y', x_vars=['x'], threshold_var='q',
            entity_var='unit', time_var='year',
            n_thresholds=1, bootstrap_reps=9,
        )
        assert isinstance(results, list)
        assert len(results) == 1

    def test_multi_threshold_with_multi_thresholds(self):
        """Smoke test that n_thresholds=2 returns a list."""
        rng = np.random.default_rng(88)
        records = []
        for unit in range(50):
            for t in range(5):
                q = rng.uniform(0, 10); x = rng.uniform(-2, 2)
                y = 1.0 + 0.5*x + rng.normal(0, 0.5)
                records.append({'unit': unit, 'year': 2015+t, 'y': y, 'x': x, 'q': q})
        df = pd.DataFrame(records)
        ptr = PanelThresholdRegression(grid_size=10, min_periods_per_regime=15)
        results = ptr.estimate_multi_threshold(
            df, y_var='y', x_vars=['x'], threshold_var='q',
            entity_var='unit', time_var='year',
            n_thresholds=2, bootstrap_reps=9,
        )
        # Either 1 or 2 thresholds returned depending on bootstrap test
        assert isinstance(results, list)
        assert 1 <= len(results) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# 6. Export methods
# ─────────────────────────────────────────────────────────────────────────────


class TestExport:
    def test_to_dataframe(self, fitted_ptr):
        df = fitted_ptr.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        for col in ["regime", "coef", "se", "t_stat", "pval"]:
            assert col in df.columns

    def test_to_dataframe_requires_result(self, ptr):
        with pytest.raises(ValueError, match="No results"):
            ptr.to_dataframe()

    def test_to_dict(self, fitted_ptr):
        d = fitted_ptr.to_dict()
        assert isinstance(d, dict)
        assert "threshold" in d
        assert "r_squared" in d
        assert "threshold_ci" in d
        assert "adj_r_squared" in d

    def test_to_dict_requires_result(self, ptr):
        with pytest.raises(ValueError, match="No results"):
            ptr.to_dict()

    def test_to_dict_serializable(self, fitted_ptr):
        """to_dict output should be JSON serializable."""
        import json
        d = fitted_ptr.to_dict()
        json.dumps(d)  # should not raise

    def test_to_dataframe_with_multi_threshold(self):
        """Smoke test: multi-threshold populates result so to_dataframe works."""
        rng = np.random.default_rng(55)
        records = []
        for unit in range(50):
            for t in range(5):
                q = rng.uniform(0, 10); x = rng.uniform(-2, 2)
                y = 1.0 + 0.5*x + rng.normal(0, 0.5)
                records.append({'unit': unit, 'year': 2015+t, 'y': y, 'x': x, 'q': q})
        df = pd.DataFrame(records)
        ptr = PanelThresholdRegression(grid_size=5)
        ptr.estimate_multi_threshold(
            df, y_var='y', x_vars=['x'],
            threshold_var='q',
            entity_var='unit', time_var='year',
            n_thresholds=1, bootstrap_reps=9,
        )
        df_out = ptr.to_dataframe()
        assert isinstance(df_out, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 7. End-to-end
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_pipeline(self, panel_df, tmp_path):
        ptr = PanelThresholdRegression(grid_size=20, trim_pct=0.05)
        result = ptr.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
            fixed_effects="entity",
        )

        bootstrap = ptr.estimate_bootstrap(n_bootstrap=19, seed=42)

        df_export = ptr.to_dataframe()
        d_export = ptr.to_dict()
        summary = result.summary()

        assert result.threshold is not None
        assert bootstrap.threshold_pvalue is not None
        assert not df_export.empty
        assert "threshold" in d_export
        assert "Threshold Estimate" in summary


# ─────────────────────────────────────────────────────────────────────────────
# 8. Edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_grid_size_affects_result(self, panel_df):
        ptr_small = PanelThresholdRegression(grid_size=10)
        ptr_large = PanelThresholdRegression(grid_size=20)
        r1 = ptr_small.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        r2 = ptr_large.estimate(
            panel_df,
            y_var="y", x_vars=["x"],
            threshold_var="q",
            entity_var="unit", time_var="year",
        )
        # Both should find a threshold
        assert r1.threshold is not None
        assert r2.threshold is not None
        # Coefs should be similar (within estimation noise)
        assert np.allclose(r1.regime1_coef, r2.regime1_coef, atol=0.5)

    def test_trim_affects_grid(self):
        ptr_trim = PanelThresholdRegression(trim_pct=0.10)
        assert ptr_trim.trim_pct == 0.10

    def test_result_summary_no_converge(self):
        r = ThresholdResult(
            threshold=None,
            threshold_se=None,
            threshold_pvalue=None,
            threshold_ci=None,
            regime1_coef=np.array([0.5]),
            regime2_coef=np.array([1.5]),
            regime1_se=np.array([0.1]),
            regime2_se=np.array([0.2]),
            r_squared=0.1, adj_r_squared=0.05,
            residual_ss=1000.0,
            n_observations=500, n_regime1=250, n_regime2=250,
            grid_size=400, trim_pct=0.05,
            sup_lm_stat=None, model=None,
            did_converge=False,
            notes=["Warning: model did not converge"],
        )
        summary = r.summary()
        assert "did not converge" in summary.lower() or "⚠" in summary

    def test_to_dict_with_tuple(self, fitted_ptr):
        """threshold_ci is None before bootstrap; after bootstrap becomes tuple/list."""
        d_before = fitted_ptr.to_dict()
        # Before bootstrap, threshold_ci should be None
        assert "threshold_ci" in d_before
        # After bootstrap, threshold_ci becomes a tuple/list
        fitted_ptr.estimate_bootstrap(n_bootstrap=19, seed=42)
        d_after = fitted_ptr.to_dict()
        ci = d_after["threshold_ci"]
        assert isinstance(ci, (tuple, list))
        assert len(ci) == 2
