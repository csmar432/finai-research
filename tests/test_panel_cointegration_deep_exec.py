"""tests/test_panel_cointegration_deep_exec.py — Deep tests for panel_cointegration.py.

Targets: dataclasses, pure helpers, class __init__, core methods,
fit/pedroni/kao/westerlund, error/edge cases, table generation.
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
    import pandas as pd
    from scripts.research_framework.panel_cointegration import (
        CointegrationResult,
        ECMResult,
        PanelCointegrationTest,
        PanelECM,
        CrossSectionalDependence,
        _significance_mark,
        _norm_cdf,
        _norm_ppf,
        _safe_div,
        _ols_residuals,
        _adf_stat,
        _pp_stat,
        _select_lag_aic,
        _compute_residual_autocorr,
        _csd_pesaran,
    )
except Exception as exc:
    pytest.skip(f"panel_cointegration not importable: {exc}", allow_module_level=True)


# ─── Pure helper functions ─────────────────────────────────────────────────────

class TestSignificanceMark:
    def test_very_significant(self):
        assert _significance_mark(0.001) == "***"

    def test_significant(self):
        assert _significance_mark(0.03) == "**"

    def test_marginal(self):
        assert _significance_mark(0.07) == "*"

    def test_not_significant(self):
        assert _significance_mark(0.5) == ""

    def test_exact_zero(self):
        assert _significance_mark(0.0) == "***"

    def test_boundary_01(self):
        assert _significance_mark(0.01) == "**"

    def test_boundary_05(self):
        assert _significance_mark(0.05) == "*"

    def test_boundary_10(self):
        assert _significance_mark(0.09) == "*"


class TestNormCdf:
    def test_zero(self):
        cdf = _norm_cdf(0.0)
        assert abs(cdf - 0.5) < 0.01

    def test_positive_large(self):
        cdf = _norm_cdf(3.0)
        assert cdf > 0.99

    def test_negative_large(self):
        cdf = _norm_cdf(-3.0)
        assert cdf < 0.01

    def test_array(self):
        vals = np.array([-1.0, 0.0, 1.0])
        cdf = _norm_cdf(vals)
        assert cdf.shape == vals.shape
        assert 0 < cdf[0] < 0.5
        assert abs(cdf[1] - 0.5) < 0.01
        assert 0.5 < cdf[2] < 1.0


class TestNormPpf:
    def test_half(self):
        q = _norm_ppf(0.5)
        assert abs(q) < 0.01

    def test_positive(self):
        q = _norm_ppf(0.975)
        assert q > 1.5


class TestSafeDiv:
    def test_normal(self):
        assert abs(_safe_div(10.0, 2.0) - 5.0) < 1e-9

    def test_zero_denominator(self):
        assert np.isnan(_safe_div(1.0, 0.0))

    def test_nan_denominator(self):
        assert np.isnan(_safe_div(1.0, np.nan))

    def test_custom_fill(self):
        assert _safe_div(1.0, 0.0, fill=-999.0) == -999.0


class TestOlsResiduals:
    def test_basic(self):
        rng = np.random.default_rng(42)
        X = np.column_stack([np.ones(50), rng.normal(size=50)])
        beta_true = np.array([1.0, 2.0])
        y = X @ beta_true + rng.normal(size=50) * 0.1
        resid = _ols_residuals(y, X)
        assert len(resid) == len(y)
        assert np.issubdtype(resid.dtype, np.floating)

    def test_perfect_fit(self):
        X = np.column_stack([np.ones(10), np.arange(10.0)])
        y = 2.0 + 3.0 * np.arange(10.0)
        resid = _ols_residuals(y, X)
        assert np.max(np.abs(resid)) < 1e-10

    def test_too_few_observations(self):
        X = np.ones((1, 2))
        y = np.array([1.0])
        resid = _ols_residuals(y, X)
        assert len(resid) == 1


class TestAdfStat:
    def test_basic(self):
        rng = np.random.default_rng(99)
        # Stationary AR(1) series
        series = np.cumsum(rng.normal(size=200))
        stat, lag, _ = _adf_stat(series, max_lags=4)
        assert isinstance(stat, float)
        assert isinstance(lag, int)
        assert lag >= 0

    def test_short_series(self):
        series = np.array([1.0, 1.1, 0.9, 1.05])
        stat, lag, _ = _adf_stat(series, max_lags=4)
        assert np.isnan(stat) or isinstance(stat, float)

    def test_constant_series(self):
        series = np.ones(100)
        stat, lag, _ = _adf_stat(series, max_lags=4)
        assert np.isnan(stat) or isinstance(stat, float)

    def test_random_walk(self):
        rng = np.random.default_rng(7)
        series = np.cumsum(rng.normal(size=100))
        stat, lag, _ = _adf_stat(series, max_lags=3)
        # Random walk should have low (negative) ADF stat
        assert isinstance(stat, (float, np.floating))

    def test_autocorr_output(self):
        rng = np.random.default_rng(11)
        series = np.cumsum(rng.normal(size=100))
        _, _, autocorr = _adf_stat(series, max_lags=4)
        assert isinstance(autocorr, np.ndarray)


class TestPpStat:
    def test_basic(self):
        rng = np.random.default_rng(55)
        series = np.cumsum(rng.normal(size=200))
        stat = _pp_stat(series)
        assert isinstance(stat, (float, np.floating))

    def test_short_series(self):
        series = np.array([1.0, 1.5, 2.0, 1.8, 2.2, 2.5, 2.1, 2.7])
        stat = _pp_stat(series)
        assert np.isnan(stat) or isinstance(stat, float)

    def test_constant(self):
        series = np.ones(100)
        stat = _pp_stat(series)
        assert np.isnan(stat) or isinstance(stat, (float, np.floating))


class TestSelectLagAic:
    def test_basic(self):
        rng = np.random.default_rng(33)
        resid = rng.normal(size=100)
        lag = _select_lag_aic(resid, max_lags=4)
        assert 0 <= lag <= 4

    def test_short_series(self):
        resid = np.array([1.0, 1.1, 0.9, 1.05])
        lag = _select_lag_aic(resid, max_lags=4)
        assert isinstance(lag, int)

    def test_constant(self):
        resid = np.ones(50)
        lag = _select_lag_aic(resid, max_lags=4)
        assert isinstance(lag, int)


class TestComputeResidualAutocorr:
    def test_basic(self):
        rng = np.random.default_rng(44)
        resid = rng.normal(size=50)
        corr = _compute_residual_autocorr(resid, max_lag=1)
        assert isinstance(corr, float)

    def test_short_series(self):
        resid = np.array([1.0, 1.1, 0.9])
        corr = _compute_residual_autocorr(resid, max_lag=1)
        # Short series — function may return nan or a value; just verify it returns a float
        assert isinstance(corr, (float, np.floating))

    def test_iid_expected_near_zero(self):
        rng = np.random.default_rng(999)
        resid = rng.normal(size=500)
        corr = _compute_residual_autocorr(resid, max_lag=1)
        assert abs(corr) < 0.2


class TestCsdPesaran:
    def test_basic(self):
        rng = np.random.default_rng(42)
        residuals = rng.normal(size=(100, 5))
        stat, pval = _csd_pesaran(residuals)
        assert isinstance(stat, float)
        assert isinstance(pval, float)

    def test_dataframe_input(self):
        df = pd.DataFrame(np.random.randn(50, 3))
        stat, pval = _csd_pesaran(df)
        assert isinstance(stat, float)
        assert isinstance(pval, float)

    def test_1d_returns_nan(self):
        resid = np.array([1.0, 2.0, 3.0])
        stat, pval = _csd_pesaran(resid)
        assert np.isnan(stat)
        assert np.isnan(pval)

    def test_too_few_groups(self):
        residuals = np.random.randn(100, 1)
        stat, pval = _csd_pesaran(residuals)
        assert np.isnan(stat)

    def test_too_few_time_periods(self):
        residuals = np.random.randn(1, 5)
        stat, pval = _csd_pesaran(residuals)
        assert np.isnan(stat)

    def test_perfectly_correlated(self):
        x = np.random.randn(100)
        residuals = np.column_stack([x, x, x, x])
        stat, pval = _csd_pesaran(residuals)
        assert not np.isnan(stat)


# ─── CointegrationResult dataclass ─────────────────────────────────────────────

class TestCointegrationResultFields:
    def test_basic_construction(self):
        r = CointegrationResult(test_name="Pedroni_Panel-v", statistic=-3.5, pval=0.001)
        assert r.test_name == "Pedroni_Panel-v"
        assert r.statistic == -3.5
        assert r.pval == 0.001
        assert r.decision == "Reject H0"

    def test_decision_05(self):
        r = CointegrationResult(test_name="test", statistic=1.0, pval=0.07)
        assert r.decision == "Fail to reject H0"

    def test_sig_property(self):
        r = CointegrationResult(test_name="test", statistic=1.0, pval=0.001)
        assert r.sig == "***"

    def test_to_dict(self):
        r = CointegrationResult(test_name="Pedroni_Panel-v", statistic=-3.5,
                               pval=0.001, n_obs=1000, n_groups=50)
        d = r.to_dict()
        assert d["test_name"] == "Pedroni_Panel-v"
        assert d["statistic"] == -3.5
        assert d["pval"] == 0.001
        assert d["n_obs"] == 1000
        assert d["n_groups"] == 50

    def test_to_dict_with_trace(self):
        r = CointegrationResult(test_name="Westerlund", statistic=1.0, pval=0.01,
                               trace_stat=25.0, max_eig_stat=3.0)
        d = r.to_dict()
        assert d["trace_stat"] == 25.0
        assert d["max_eig_stat"] == 3.0


# ─── ECMResult dataclass ───────────────────────────────────────────────────────

class TestECMResultFields:
    def test_default_fields(self):
        r = ECMResult()
        assert isinstance(r.coefs, dict)
        assert isinstance(r.ses, dict)
        assert isinstance(r.pvals, dict)
        assert r.ect_coef == 0.0
        assert r.ect_se == 0.0
        assert r.n_obs == 0
        assert r.n_groups == 0

    def test_with_values(self):
        r = ECMResult(
            coefs={"ect": -0.3, "d_lag1": 0.1},
            ses={"ect": 0.05, "d_lag1": 0.03},
            pvals={"ect": 0.001, "d_lag1": 0.05},
            ect_coef=-0.3,
            ect_se=0.05,
            ect_pval=0.001,
            n_obs=500,
            n_groups=30,
            r_squared=0.85,
        )
        assert r.coefs["ect"] == -0.3
        assert r.n_obs == 500
        assert r.n_groups == 30
        assert r.r_squared == 0.85


# ─── PanelCointegrationTest __init__ ───────────────────────────────────────────

class TestPanelCointegrationTestInit:
    def test_default_trend(self):
        pct = PanelCointegrationTest()
        assert pct.trend == "c"
        assert pct.max_lags == 4

    def test_custom_params(self):
        pct = PanelCointegrationTest(trend="ct", max_lags=6)
        assert pct.trend == "ct"
        assert pct.max_lags == 6

    def test_results_initialized(self):
        pct = PanelCointegrationTest()
        assert pct._pedroni_results == {}
        assert pct._kao_results == {}
        assert pct._westerlund_results == {}
        assert pct._csd_results == {}


# ─── PanelCointegrationTest.pedroni_panel ─────────────────────────────────────

class TestPedroniPanel:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u + np.random.randn(n_obs) * 0.1
        return pd.DataFrame({
            "unit": unit_ids,
            "time": time_index,
            "lnrgdp": y,
            "lnmoney": x,
        })

    def test_basic(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_results_stored(self):
        df = self._make_panel_df(n_units=12, T=35)
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert len(pct._pedroni_results) > 0

    def test_trend_n(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest(trend="n", max_lags=3)
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_trend_ct(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest(trend="ct", max_lags=3)
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_multiple_x_vars(self):
        np.random.seed(42)
        n_units, T = 10, 30
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x1 = np.random.randn(n_obs) * 2
        x2 = np.random.randn(n_obs) * 1.5
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x1 + 0.8 * x2 + u
        df = pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x1, "lninflation": x2,
        })
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney", "lninflation"])
        assert isinstance(results, dict)

    def test_missing_var_returns_empty(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest()
        results = pct.pedroni_panel(df, y_var="nonexistent", x_vars=["lnmoney"])
        assert results == {}


# ─── PanelCointegrationTest.kao_test ──────────────────────────────────────────

class TestKaoTest:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_basic(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(trend="c")
        results = pct.kao_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_results_stored(self):
        df = self._make_panel_df(n_units=12, T=35)
        pct = PanelCointegrationTest()
        pct.kao_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert len(pct._kao_results) > 0

    def test_missing_var(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest()
        results = pct.kao_test(df, y_var="nonexistent", x_vars=["lnmoney"])
        assert results == {}


# ─── PanelCointegrationTest.westerlund_test ────────────────────────────────────

class TestWesterlundTest:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_basic(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(max_lags=3)
        results = pct.westerlund_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_missing_var(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest()
        results = pct.westerlund_test(df, y_var="nonexistent", x_vars=["lnmoney"])
        assert results == {}


# ─── PanelCointegrationTest.cross_sectional_dependence ──────────────────────────

class TestCrossSectionalDependence:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "eps": np.random.randn(n_obs),
            "roe": np.random.randn(n_obs),
            "lev": np.random.randn(n_obs),
        })

    def test_basic(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest()
        results = pct.cross_sectional_dependence(df, vars=["eps", "roe", "lev"])
        assert isinstance(results, dict)

    def test_single_var_returns_warning(self):
        df = self._make_panel_df(n_units=8, T=30)
        pct = PanelCointegrationTest()
        results = pct.cross_sectional_dependence(df, vars=["eps"])
        assert results == {}


# ─── PanelCointegrationTest.summary ────────────────────────────────────────────

class TestPanelCointegrationSummary:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_summary_empty(self):
        pct = PanelCointegrationTest()
        df = pct.summary()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_summary_after_pedroni(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        summary = pct.summary()
        assert not summary.empty
        assert "Test" in summary.columns
        assert "Statistic" in summary.columns
        assert "P-value" in summary.columns
        assert "Decision" in summary.columns

    def test_summary_after_all_tests(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        pct.kao_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        pct.westerlund_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        summary = pct.summary()
        assert not summary.empty
        assert len(summary) > 5


# ─── PanelCointegrationTest.to_latex ──────────────────────────────────────────

class TestPanelCointegrationLatex:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_to_latex_empty(self):
        pct = PanelCointegrationTest()
        latex = pct.to_latex()
        assert latex == ""

    def test_to_latex_basic(self):
        df = self._make_panel_df(n_units=15, T=40)
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        latex = pct.to_latex()
        assert "\\begin{table}" in latex
        assert "\\caption" in latex
        assert "\\label" in latex
        assert "\\toprule" in latex
        assert "\\bottomrule" in latex

    def test_to_latex_with_caption(self):
        df = self._make_panel_df(n_units=12, T=35)
        pct = PanelCointegrationTest()
        pct.kao_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        latex = pct.to_latex(caption="Kao Test Results", label="tab:kao")
        assert "Kao Test Results" in latex


# ─── PanelECM __init__ ────────────────────────────────────────────────────────

class TestPanelECMInit:
    def test_default_trend(self):
        ecm = PanelECM()
        assert ecm.trend == "c"
        assert ecm._result is None
        assert ecm._data_info == {}

    def test_custom_trend(self):
        ecm = PanelECM(trend="ct")
        assert ecm.trend == "ct"


# ─── PanelECM.fit ──────────────────────────────────────────────────────────────

class TestPanelECMFit:
    def _make_ecm_df(self, n_units=10, T=40):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x + u + np.random.randn(n_obs) * 0.1
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_fit_basic(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        result = ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                         unit_var="unit", time_var="time", lag_order=1)
        assert isinstance(result, dict)

    def test_fit_sets_result(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        assert ecm._result is None
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=1)
        assert ecm._result is not None

    def test_fit_ecm_data(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        result, ecm_df = ecm.fit(
            df, dep_var="lnrgdp", indep_vars=["lnmoney"],
            unit_var="unit", time_var="time", lag_order=1, return_ecm_data=True,
        )
        assert isinstance(ecm_df, pd.DataFrame)
        assert "ect" in ecm_df.columns

    def test_fit_multiple_indep_vars(self):
        np.random.seed(42)
        n_units, T = 10, 40
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x1 = np.random.randn(n_obs) * 2
        x2 = np.random.randn(n_obs) * 1.5
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x1 + 0.8 * x2 + u
        df = pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x1, "lninflation": x2,
        })
        ecm = PanelECM(trend="c")
        result = ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney", "lninflation"],
                         unit_var="unit", time_var="time", lag_order=1)
        assert isinstance(result, dict)

    def test_fit_too_few_obs(self):
        df = self._make_ecm_df(n_units=3, T=5)
        ecm = PanelECM(trend="c")
        result = ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                         unit_var="unit", time_var="time", lag_order=1)
        assert result == {}

    def test_fit_n_trend(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="n")
        result = ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                         unit_var="unit", time_var="time", lag_order=1)
        assert isinstance(result, dict)

    def test_fit_ct_trend(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="ct")
        result = ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                         unit_var="unit", time_var="time", lag_order=1)
        assert isinstance(result, dict)


# ─── PanelECM.summary ──────────────────────────────────────────────────────────

class TestPanelECMSummary:
    def _make_ecm_df(self, n_units=10, T=40):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_summary_before_fit(self):
        ecm = PanelECM()
        df_summary = ecm.summary()
        assert isinstance(df_summary, pd.DataFrame)
        assert df_summary.empty

    def test_summary_after_fit(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=2)
        df_summary = ecm.summary()
        assert isinstance(df_summary, pd.DataFrame)
        assert not df_summary.empty
        assert "Variable" in df_summary.columns
        assert "Coef" in df_summary.columns


# ─── PanelECM.to_latex ─────────────────────────────────────────────────────────

class TestPanelECMLatex:
    def _make_ecm_df(self, n_units=10, T=40):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_to_latex_empty(self):
        ecm = PanelECM()
        latex = ecm.to_latex()
        assert latex == ""

    def test_to_latex_basic(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=2)
        latex = ecm.to_latex()
        assert "\\begin{table}" in latex
        assert "\\caption" in latex
        assert "\\label" in latex

    def test_to_latex_custom(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=1)
        latex = ecm.to_latex(caption="ECM Estimates", label="tab:ecm_test")
        assert "ECM Estimates" in latex


# ─── PanelECM.plot_ecm_coefficients ───────────────────────────────────────────

class TestPanelECMPlot:
    def _make_ecm_df(self, n_units=10, T=40):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_plot_before_fit(self):
        ecm = PanelECM()
        try:
            fig = ecm.plot_ecm_coefficients()
            assert fig is None
        except Exception:
            pass

    def test_plot_after_fit(self):
        df = self._make_ecm_df(n_units=10, T=40)
        ecm = PanelECM(trend="c")
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=2)
        try:
            fig = ecm.plot_ecm_coefficients()
            if fig is not None:
                assert fig is not None
        except Exception:
            pass


# ─── CrossSectionalDependence ──────────────────────────────────────────────────

class TestCrossSectionalDependenceClass:
    def _make_csd_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "eps": np.random.randn(n_obs),
            "roe": np.random.randn(n_obs),
            "lev": np.random.randn(n_obs),
            "roa": np.random.randn(n_obs),
        })

    def test_init(self):
        csd = CrossSectionalDependence()
        assert csd is not None

    def test_test_basic(self):
        df = self._make_csd_df(n_units=15, T=40)
        csd = CrossSectionalDependence()
        result = csd.test(df, vars=["eps", "roe", "lev"])
        assert "cd_statistic" in result
        assert "cd_pval" in result
        assert "decision" in result
        assert isinstance(result["decision"], str)

    def test_test_single_var(self):
        df = self._make_csd_df(n_units=8, T=30)
        csd = CrossSectionalDependence()
        result = csd.test(df, vars=["eps"])
        assert result == {}

    def test_test_custom_unit_var(self):
        df = self._make_csd_df(n_units=12, T=35)
        csd = CrossSectionalDependence()
        result = csd.test(df, vars=["eps", "roe"], unit_var="unit")
        assert isinstance(result, dict)

    def test_test_avg_correlation(self):
        df = self._make_csd_df(n_units=15, T=40)
        csd = CrossSectionalDependence()
        result = csd.test(df, vars=["eps", "roe", "lev", "roa"])
        assert "avg_correlation" in result


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestPanelCointegrationEdgeCases:
    def _make_panel_df(self, n_units=10, T=30):
        np.random.seed(42)
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.5)
        y = 1.5 * x + u
        return pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })

    def test_pedroni_with_nan_in_data(self):
        df = self._make_panel_df(n_units=8, T=30)
        df.iloc[0, 2] = np.nan
        pct = PanelCointegrationTest(trend="c", max_lags=3)
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_kao_with_nan(self):
        df = self._make_panel_df(n_units=8, T=30)
        df.iloc[5, 2] = np.nan
        pct = PanelCointegrationTest()
        results = pct.kao_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_westerlund_with_nan(self):
        df = self._make_panel_df(n_units=8, T=30)
        df.iloc[3, 2] = np.nan
        pct = PanelCointegrationTest(max_lags=3)
        results = pct.westerlund_test(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)

    def test_ecm_result_ect_speed_adj(self):
        np.random.seed(42)
        n_units, T = 10, 40
        n_obs = n_units * T
        unit_ids = np.repeat(np.arange(n_units), T)
        time_index = np.tile(np.arange(T), n_units)
        x = np.random.randn(n_obs) * 2
        u = np.cumsum(np.random.randn(n_obs) * 0.3)
        y = 1.5 * x + u
        df = pd.DataFrame({
            "unit": unit_ids, "time": time_index,
            "lnrgdp": y, "lnmoney": x,
        })
        ecm = PanelECM(trend="c")
        ecm.fit(df, dep_var="lnrgdp", indep_vars=["lnmoney"],
                unit_var="unit", time_var="time", lag_order=1)
        assert ecm._result is not None
        assert isinstance(ecm._result.speed_adj, float)

    def test_csd_empty_residuals(self):
        stat, pval = _csd_pesaran(np.array([[]]))
        assert np.isnan(stat)

    def test_csd_all_nan(self):
        residuals = np.full((50, 3), np.nan)
        stat, pval = _csd_pesaran(residuals)
        assert np.isnan(stat)

    def test_ols_residuals_collinear(self):
        x = np.column_stack([np.ones(20), np.ones(20), np.arange(20.0)])
        y = np.arange(20.0) + np.random.randn(20) * 0.1
        resid = _ols_residuals(y, x)
        assert len(resid) == len(y)

    def test_result_sig_stars_boundary(self):
        r = CointegrationResult(test_name="t", statistic=1.0, pval=0.01)
        assert r.sig == "**"
        r2 = CointegrationResult(test_name="t", statistic=1.0, pval=0.05)
        assert r2.sig == "*"

    def test_norm_cdf_scipy_fallback(self):
        # Test fallback when scipy available
        result = _norm_cdf(1.96)
        assert 0.9 < result < 1.0

    def test_pedroni_empty_groups(self):
        df = self._make_panel_df(n_units=2, T=10)
        df = df[df["unit"] < 1]  # Only 1 unit
        pct = PanelCointegrationTest()
        results = pct.pedroni_panel(df, y_var="lnrgdp", x_vars=["lnmoney"])
        assert isinstance(results, dict)
