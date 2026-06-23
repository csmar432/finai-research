"""Tests for scripts/research_framework/iv_panel.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import scipy.stats as stats


def _have_linearmodels() -> bool:
    try:
        import linearmodels  # noqa: F401
        return True
    except ImportError:
        return False


class TestPanelDiagnostic:
    def test_panel_diagnostic_str_reject(self):
        from scripts.research_framework.iv_panel import PanelDiagnostic

        d = PanelDiagnostic(
            test_name="Weak Instrument F",
            statistic=15.0,
            p_value=0.002,
            conclusion="reject_H0",
        )
        s = str(d)
        assert "Weak Instrument F" in s
        assert "15.0000" in s
        assert "reject_H0" in s

    def test_panel_diagnostic_str_fail_to_reject(self):
        from scripts.research_framework.iv_panel import PanelDiagnostic

        d = PanelDiagnostic(
            test_name="Sargan Test",
            statistic=2.1,
            p_value=0.72,
            conclusion="fail_to_reject_H0",
        )
        s = str(d)
        assert "Sargan Test" in s
        assert "fail_to_reject_H0" in s


class TestKleibergenPaapRK:
    def test_kp_rk_f_strong_instrument(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 500
        Z = rng.normal(0, 1, (N, 2))
        X = 0.5 * Z[:, [0]] + 0.3 * Z[:, [1]] + rng.normal(0, 0.3, (N, 1))
        y = 2.0 * X.flatten() + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X.flatten(), "Z1": Z[:, 0], "Z2": Z[:, 1],
            "id": range(N), "year": [2020] * N,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                        unit_var="id", time_var="year")
        kp_f, kp_p = model._kleibergen_paap_rk_f(
            y.astype(float), X.astype(float), Z.astype(float), None
        )
        assert isinstance(kp_f, float)
        assert isinstance(kp_p, float)
        assert kp_f > 10, f"Strong instrument should give KP-F > 10, got {kp_f}"
        assert kp_p < 0.05

    def test_kp_rk_f_underidentified(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(99)
        y = rng.normal(0, 1, 50)
        X = rng.normal(0, 1, (50, 2))
        Z = rng.normal(0, 1, (50, 1))

        model = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"],
                        iv_vars=["z"], unit_var="id", time_var="year")
        kp_f, kp_p = model._kleibergen_paap_rk_f(y, X, Z, None)
        assert np.isnan(kp_f)
        assert np.isnan(kp_p)


class TestAndersonRubinF:
    def test_ar_f_rejects_nonzero_beta(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(77)
        N, K = 300, 1
        Z = rng.normal(0, 1, (N, 2))
        X = 0.6 * Z[:, [0]] + rng.normal(0, 0.4, (N, K))
        y = 3.0 * X.flatten() + rng.normal(0, 0.5, N)
        beta_iv = np.array([3.0])

        model = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"],
                        iv_vars=["z1", "z2"], unit_var="id", time_var="year")
        ar_f = model._anderson_rubin_f(y, X, Z, beta_iv, None)
        assert isinstance(ar_f, float)
        assert not np.isnan(ar_f)

    def test_ar_f_underidentified(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(88)
        y = rng.normal(0, 1, 30)
        X = rng.normal(0, 1, (30, 2))
        Z = rng.normal(0, 1, (30, 1))
        beta = np.array([0.0, 0.0])

        model = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"],
                        iv_vars=["z"], unit_var="id", time_var="year")
        ar_f = model._anderson_rubin_f(y, X, Z, beta, None)
        assert np.isnan(ar_f)


class TestFormatFMBSummary:
    def test_format_fmb_summary_empty(self):
        from scripts.research_framework.iv_panel import _format_fmb_summary

        result = _format_fmb_summary({})
        assert result == ""

    def test_format_fmb_summary_single_var(self):
        from scripts.research_framework.iv_panel import _format_fmb_summary

        result = _format_fmb_summary({"roa": {"mean_coef": 0.0523}})
        assert "roa=0.0523" in result


class TestIVPanelEdgeCases:
    def test_prepare_data_drops_na(self):
        from scripts.research_framework.iv_panel import IVPanel

        df = pd.DataFrame({
            "y": [1.0, 2.0, np.nan, 4.0],
            "X": [0.5, np.nan, 0.3, 0.4],
            "Z": [1.0, 1.0, 1.0, 1.0],
            "id": [1, 2, 3, 4],
            "year": [2020] * 4,
        })
        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                        unit_var="id", time_var="year")
        prepared = model._prepare_data()
        assert len(prepared) == 2

    def test_fit_returns_none_on_empty_data(self):
        from scripts.research_framework.iv_panel import IVPanel

        df = pd.DataFrame({
            "y": [np.nan, np.nan], "X": [np.nan, np.nan],
            "Z": [1.0, 1.0], "id": [1, 2], "year": [2020, 2021],
        })
        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                        unit_var="id", time_var="year")
        result = model.fit()
        assert result is None

    def test_get_diagnostics_empty(self):
        from scripts.research_framework.iv_panel import IVPanel

        model = IVPanel(pd.DataFrame(), y_var="y", x_vars=["X"], iv_vars=["Z"],
                        unit_var="id", time_var="year")
        diags = model.get_diagnostics()
        assert isinstance(diags, list)
        assert len(diags) == 0


class TestDynamicPanelDiagnostics:
    def test_dynamic_panel_diagnostics_to_dict(self):
        from scripts.research_framework.iv_panel import DynamicPanelDiagnostics

        diag = DynamicPanelDiagnostics(
            ar1_stat=2.1, ar1_pval=0.018,
            ar2_stat=0.9, ar2_pval=0.37,
            sargan_stat=5.2, sargan_pval=0.16,
            hansen_stat=5.2, hansen_pval=0.16,
            n_instruments=8, n_obs=400,
        )
        d = diag.to_dict()
        assert d["AR(1) Z"] == 2.1
        assert d["n_obs"] == 400

    def test_dynamic_panel_diagnostics_interpretation(self):
        from scripts.research_framework.iv_panel import DynamicPanelDiagnostics

        diag = DynamicPanelDiagnostics(
            ar1_stat=2.1, ar1_pval=0.018,
            ar2_stat=0.9, ar2_pval=0.37,
            sargan_stat=5.2, sargan_pval=0.16,
            hansen_stat=5.2, hansen_pval=0.16,
            n_instruments=8, n_obs=400,
        )
        interp = diag.interpretation
        assert "AR(1)" in interp
        assert "AR(2)" in interp


class TestAR2Test:
    def test_ar2_order1_positive_autocorr(self):
        from scripts.research_framework.iv_panel import test_ar2

        rng = np.random.default_rng(123)
        n = 200
        eps = rng.normal(0, 1, n)
        res = np.zeros(n)
        res[0] = eps[0]
        for t in range(1, n):
            res[t] = 0.5 * res[t - 1] + eps[t]

        result = test_ar2(res, order=2)
        assert not np.isnan(result["stat"])
        assert result["stat"] > 0

    def test_ar2_insufficient_data(self):
        from scripts.research_framework.iv_panel import test_ar2

        result = test_ar2(np.array([1.0, 2.0]), order=2)
        assert np.isnan(result["stat"])


class TestSarganTest:
    def test_sargan_insufficient_observations(self):
        from scripts.research_framework.iv_panel import _sargan_test

        rng = np.random.default_rng(42)
        resid = rng.normal(0, 1, 30)
        instruments = rng.normal(0, 1, (30, 5))
        stat, pval, df = _sargan_test(resid, instruments)
        assert np.isnan(stat)

    def test_sargan_exact_identification(self):
        from scripts.research_framework.iv_panel import _sargan_test

        rng = np.random.default_rng(42)
        resid = rng.normal(0, 1, 200)
        instruments = rng.normal(0, 1, (200, 2))
        stat, pval, df = _sargan_test(resid, instruments)
        assert df == 1
        assert not np.isnan(stat)


class TestRunDynamicPanelDiagnostics:
    def test_run_dynamic_panel_warns_on_small_sample(self, caplog):
        from scripts.research_framework.iv_panel import run_dynamic_panel_diagnostics

        rng = np.random.default_rng(42)
        n = 30  # below 50 threshold
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "x1": rng.normal(0, 1, n),
            "x2": rng.normal(0, 1, n),
            "firm": [f"f{i}" for i in range(n)],
            "year": [2018, 2019, 2020] * (n // 3),
        })

        with caplog.at_level("WARNING"):
            diag = run_dynamic_panel_diagnostics(
                df, y_var="y", x_vars=["x1", "x2"],
                entity_var="firm", time_var="year", max_lags=2,
            )

        # Should warn about small sample
        assert any("50" in r.message for r in caplog.records)
        # Function returns n_obs=0 with NaN stats for n < 50
        assert diag.n_obs == 0


@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestIVPanelWithLinearmodels:
    def test_fit_2sls_basic(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 500
        Z = rng.normal(0, 1, N)
        X = 0.5 * Z + rng.normal(0, 0.5, N)
        y = 1.0 + 2.0 * X + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X, "Z": Z,
            "id": range(N), "year": [2020] * N,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                        unit_var="id", time_var="year")
        result = model.fit(method="iv")
        assert result is not None
        assert hasattr(result, "params")

    def test_fit_liml_method(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 400
        Z = rng.normal(0, 1, (N, 2))
        X = 0.4 * Z[:, [0]] + 0.3 * Z[:, [1]] + rng.normal(0, 0.4, (N, 1))
        y = 1.5 + 2.0 * X.flatten() + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X.flatten(), "Z1": Z[:, 0], "Z2": Z[:, 1],
            "id": range(N), "year": [2020] * N,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                        unit_var="id", time_var="year")
        result = model.fit(method="liml")
        assert result is not None

    def test_fit_with_w_vars(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 300
        Z = rng.normal(0, 1, N)
        X = 0.5 * Z + rng.normal(0, 0.5, N)
        y = 1.0 + 2.0 * X + 0.3 * rng.normal(0, 1, N) + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X, "Z": Z, "W": rng.normal(0, 1, N),
            "id": range(N), "year": [2020] * N,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                        w_vars=["W"], unit_var="id", time_var="year")
        result = model.fit()
        assert result is not None

    def test_two_way_clustering(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 200
        firms = 50
        years = 4
        firm_ids = np.repeat(range(firms), years)
        year_ids = np.tile(range(years), firms)
        Z = rng.normal(0, 1, N)
        X = 0.5 * Z + rng.normal(0, 0.5, N)
        y = 1.0 + 2.0 * X + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X, "Z": Z,
            "id": firm_ids, "year": year_ids,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                        unit_var="id", time_var="year")
        result = model.fit(cluster_var="id", cluster2_var="year")
        assert result is not None

    def test_diagnostics_run(self):
        from scripts.research_framework.iv_panel import IVPanel

        rng = np.random.default_rng(42)
        N = 500
        Z = rng.normal(0, 1, (N, 2))
        X = 0.5 * Z[:, [0]] + 0.3 * Z[:, [1]] + rng.normal(0, 0.3, (N, 1))
        y = 2.0 * X.flatten() + rng.normal(0, 0.5, N)
        df = pd.DataFrame({
            "y": y, "X": X.flatten(), "Z1": Z[:, 0], "Z2": Z[:, 1],
            "id": range(N), "year": [2020] * N,
        })

        model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                        unit_var="id", time_var="year")
        result = model.fit()
        assert result is not None

        diags = model.get_diagnostics()
        assert isinstance(diags, list)
        assert len(diags) >= 2

        f_stats = [d for d in diags if "Weak Instrument" in d.test_name]
        assert len(f_stats) >= 1
        kp_diags = [d for d in diags if "Kleibergen" in d.test_name]
        assert len(kp_diags) >= 1


@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestDynamicGMM:
    def test_dynamic_gmm_init(self):
        from scripts.research_framework.iv_panel import DynamicGMM

        rng = np.random.default_rng(42)
        n = 90  # divisible by 3
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "x": rng.normal(0, 1, n),
            "firm": list(range(n)),
            "year": np.tile([2018, 2019, 2020], n // 3),
        })

        gmm = DynamicGMM(df, y_var="y", x_vars=["x"],
                          unit_var="firm", time_var="year")
        assert gmm.y_var == "y"
        assert gmm.x_vars == ["x"]
        assert gmm.unit_var == "firm"
        assert gmm.time_var == "year"


@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestFamaMacBeth:
    def test_fama_macBeth_init(self):
        from scripts.research_framework.iv_panel import FamaMacBeth

        rng = np.random.default_rng(42)
        n = 90  # divisible by 3
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "x": rng.normal(0, 1, n),
            "firm": list(range(n)),
            "year": np.tile([2018, 2019, 2020], n // 3),
        })

        fb = FamaMacBeth(df, y_var="y", x_vars=["x"],
                         unit_var="firm", time_var="year")
        assert fb.y_var == "y"
        assert fb.x_vars == ["x"]
        assert fb.unit_var == "firm"
        assert fb.time_var == "year"

    def test_fama_macBeth_fit_returns_dict(self):
        from scripts.research_framework.iv_panel import FamaMacBeth

        rng = np.random.default_rng(42)
        n_firms, n_years = 50, 5
        records = []
        for firm in range(n_firms):
            for year in range(2018, 2018 + n_years):
                records.append({
                    "y": rng.normal(0, 1),
                    "x": rng.normal(0, 1),
                    "firm": firm, "year": year,
                })
        df = pd.DataFrame(records)

        fb = FamaMacBeth(df, y_var="y", x_vars=["x"],
                         unit_var="firm", time_var="year")
        result = fb.fit()
        assert isinstance(result, dict)

    def test_fama_macBeth_summary_dataframe(self):
        from scripts.research_framework.iv_panel import FamaMacBeth

        rng = np.random.default_rng(42)
        n_firms, n_years = 40, 4
        records = []
        for firm in range(n_firms):
            for year in range(2018, 2018 + n_years):
                records.append({
                    "y": rng.normal(0, 1),
                    "x": rng.normal(0, 1),
                    "firm": firm, "year": year,
                })
        df = pd.DataFrame(records)

        fb = FamaMacBeth(df, y_var="y", x_vars=["x"],
                         unit_var="firm", time_var="year")
        fb.fit()
        summary = fb.summary()
        assert isinstance(summary, pd.DataFrame)

    def test_fama_macBeth_to_latex(self):
        from scripts.research_framework.iv_panel import FamaMacBeth

        rng = np.random.default_rng(42)
        n_firms, n_years = 30, 3
        records = []
        for firm in range(n_firms):
            for year in range(2018, 2018 + n_years):
                records.append({
                    "y": rng.normal(0, 1),
                    "x": rng.normal(0, 1),
                    "firm": firm, "year": year,
                })
        df = pd.DataFrame(records)

        fb = FamaMacBeth(df, y_var="y", x_vars=["x"],
                         unit_var="firm", time_var="year")
        fb.fit()
        latex = fb.to_latex()
        assert isinstance(latex, str)
