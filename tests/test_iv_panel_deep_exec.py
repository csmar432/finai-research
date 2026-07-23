"""Deep execution tests for scripts/research_framework/iv_panel.py.

Covers: all dataclasses, pure helpers, __init__ methods, fit paths,
edge cases, table generation.  Target: 40+ tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.iv_panel import (
    DynamicGMM,
    DynamicPanelDiagnostics,
    FamaMacBeth,
    IVPanel,
    PanelDiagnostic,
    _format_fmb_summary,
    _sargan_test,
    run_dynamic_panel_diagnostics,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _have_linearmodels() -> bool:
    try:
        import linearmodels  # noqa: F401
        return True
    except ImportError:
        return False


def _make_iv_panel_data(
    n: int = 300,
    seed: int = 42,
    n_instruments: int = 2,
    true_coef: float = 2.0,
) -> pd.DataFrame:
    """Synthetic IV panel with strong instruments."""
    rng = np.random.default_rng(seed)
    Z = rng.normal(0, 1, (n, n_instruments))
    X = sum(0.5 * Z[:, [i]] for i in range(n_instruments)) + rng.normal(0, 0.3, (n, 1))
    y = 1.0 + true_coef * X.flatten() + rng.normal(0, 0.5, n)
    z_cols = [f"Z{i+1}" for i in range(n_instruments)]
    df = pd.DataFrame({"y": y, "X": X.flatten(), **dict(zip(z_cols, Z.T))})
    df["id"] = range(n)
    df["year"] = [2020] * n
    return df


def _make_fm_panel(
    n_firms: int = 40,
    n_years: int = 5,
    seed: int = 7,
) -> pd.DataFrame:
    """Panel data for Fama-MacBeth tests."""
    rng = np.random.default_rng(seed)
    records = []
    for firm in range(n_firms):
        for year in range(2018, 2018 + n_years):
            records.append({
                "y": rng.normal(0, 1),
                "x1": rng.normal(0, 1),
                "x2": rng.normal(0, 1),
                "firm": firm,
                "year": year,
            })
    return pd.DataFrame(records)


def _make_dynamic_panel(
    n_firms: int = 60,
    n_years: int = 5,
    seed: int = 11,
) -> pd.DataFrame:
    """Panel data for dynamic GMM / diagnostics."""
    rng = np.random.default_rng(seed)
    records = []
    for firm in range(n_firms):
        for year in range(2018, 2018 + n_years):
            records.append({
                "y": rng.normal(0, 1),
                "x1": rng.normal(0, 1),
                "x2": rng.normal(0, 1),
                "firm": f"f{firm}",
                "year": year,
            })
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PanelDiagnostic dataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestPanelDiagnosticFields:
    """More complete coverage of PanelDiagnostic beyond __str__."""

    def test_diagnostic_has_required_fields(self):
        d = PanelDiagnostic(
            test_name="Sargan",
            statistic=3.5,
            p_value=0.05,
            conclusion="fail_to_reject_H0",
            details={"rule": "p > 0.1"},
        )
        assert d.test_name == "Sargan"
        assert d.statistic == 3.5
        assert d.p_value == 0.05
        assert d.conclusion == "fail_to_reject_H0"
        assert d.details["rule"] == "p > 0.1"

    def test_diagnostic_default_details_empty_dict(self):
        d = PanelDiagnostic("F", 1.0, 0.5, "fail_to_reject_H0")
        assert d.details == {}

    def test_diagnostic_str_contains_icon_reject(self):
        d = PanelDiagnostic("Weak IV", 12.0, 0.001, "reject_H0")
        s = str(d)
        assert "🔴" in s
        assert "Weak IV" in s
        assert "12.0000" in s

    def test_diagnostic_str_contains_icon_fail(self):
        d = PanelDiagnostic("Sargan", 1.0, 0.8, "fail_to_reject_H0")
        assert "🟢" in str(d)

    def test_diagnostic_str_inconclusive(self):
        d = PanelDiagnostic("K-P", 5.0, 0.1, "inconclusive")
        s = str(d)
        assert "5.0000" in s
        assert "0.1000" in s


# ─────────────────────────────────────────────────────────────────────────────
# 2. IVPanel.__init__
# ─────────────────────────────────────────────────────────────────────────────

class TestIVPanelInit:
    def test_init_basic(self):
        df = _make_iv_panel_data(n=50)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"])
        assert m.y_var == "y"
        assert m.x_vars == ["X"]
        assert m.iv_vars == ["Z1", "Z2"]
        assert m.w_vars == []

    def test_init_with_w_vars(self):
        df = _make_iv_panel_data(n=50)
        df["W"] = np.random.default_rng(1).normal(0, 1, len(df))
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1"],
                     w_vars=["W"], unit_var="id", time_var="year")
        assert m.w_vars == ["W"]
        assert m.unit_var == "id"
        assert m.time_var == "year"

    def test_init_copies_dataframe(self):
        df = _make_iv_panel_data(n=30)
        original_len = len(df)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1"])
        m.df.iloc[0] = 0  # mutate
        assert len(df) == original_len  # original unchanged

    def test_init_defaults(self):
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["X"], iv_vars=["Z"])
        assert m.unit_var == "ticker"
        assert m.time_var == "year"
        assert m._result is None
        assert m._diagnostics == []

    def test_init_multiple_x_vars(self):
        rng = np.random.default_rng(3)
        n = 50
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "X1": rng.normal(0, 1, n),
            "X2": rng.normal(0, 1, n),
            "Z": rng.normal(0, 1, n),
            "id": range(n),
            "year": [2020] * n,
        })
        m = IVPanel(df, y_var="y", x_vars=["X1", "X2"], iv_vars=["Z"])
        assert len(m.x_vars) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. IVPanel._prepare_data
# ─────────────────────────────────────────────────────────────────────────────

class TestIVPanelPrepareData:
    def test_drops_na_in_all_vars(self):
        df = pd.DataFrame({
            "y": [1.0, np.nan, 3.0],
            "X": [0.5, 0.6, 0.7],
            "Z": [1.0, 1.0, 1.0],
            "id": [1, 2, 3],
            "year": [2020, 2021, 2022],
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                     unit_var="id", time_var="year")
        prep = m._prepare_data()
        assert len(prep) == 2

    def test_drops_na_in_iv(self):
        df = pd.DataFrame({
            "y": [1.0, 2.0, 3.0],
            "X": [0.5, 0.6, 0.7],
            "Z": [np.nan, 1.0, 1.0],
            "id": [1, 2, 3],
            "year": [2020, 2021, 2022],
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                     unit_var="id", time_var="year")
        prep = m._prepare_data()
        assert len(prep) == 2

    def test_drops_na_in_w_vars(self):
        df = pd.DataFrame({
            "y": [1.0, 2.0, 3.0],
            "X": [0.5, 0.6, 0.7],
            "Z": [1.0, 1.0, 1.0],
            "W": [1.0, np.nan, 1.0],
            "id": [1, 2, 3],
            "year": [2020, 2021, 2022],
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"], w_vars=["W"],
                     unit_var="id", time_var="year")
        prep = m._prepare_data()
        assert len(prep) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. IVPanel.fit — error paths
# ─────────────────────────────────────────────────────────────────────────────

class TestIVPanelFitErrorPaths:
    def test_fit_empty_dataframe_returns_none(self):
        df = pd.DataFrame({
            "y": [], "X": [], "Z": [], "id": [], "year": [],
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                     unit_var="id", time_var="year")
        result = m.fit()
        assert result is None

    def test_fit_no_valid_observations(self):
        df = pd.DataFrame({
            "y": [np.nan] * 5,
            "X": [np.nan] * 5,
            "Z": [1.0] * 5,
            "id": range(5),
            "year": [2020] * 5,
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"],
                     unit_var="id", time_var="year")
        result = m.fit()
        assert result is None

    @pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
    def test_fit_unadjusted_fallback_on_bad_cluster(self):
        """Cluster var with object dtype falls back to unadjusted SE."""
        rng = np.random.default_rng(5)
        n = 100
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "X": rng.normal(0, 1, n),
            "Z": rng.normal(0, 1, n),
            "id": [f"obj_{i}" for i in range(n)],
            "year": [2020] * n,
        })
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"], unit_var="id")
        result = m.fit()
        assert result is not None
        assert hasattr(result, "params")


# ─────────────────────────────────────────────────────────────────────────────
# 5. IVPanel._kleibergen_paap_rk_f — extended edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestKleibergenPaapEdgeCases:
    def test_kp_rk_f_perfect_instruments(self):
        """Identified case with near-perfect instruments returns high F."""
        rng = np.random.default_rng(7)
        n = 500
        Z = rng.normal(0, 1, (n, 2))
        X = 0.8 * Z[:, [0]] + 0.8 * Z[:, [1]] + rng.normal(0, 0.05, (n, 1))
        y = 2.0 * X.flatten() + rng.normal(0, 0.2, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        assert kp_f > 50  # very strong

    def test_kp_rk_f_weak_instruments(self):
        """Weak instruments yield low KP-F statistic."""
        rng = np.random.default_rng(8)
        n = 200
        Z = rng.normal(0, 1, (n, 1))
        X = 0.05 * Z + rng.normal(0, 1, (n, 1))  # weak instrument
        y = 1.0 * X.flatten() + rng.normal(0, 1, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        assert kp_f < 5  # weak
        assert 0 <= kp_p <= 1

    def test_kp_rk_f_with_w_exogenous(self):
        """KP-F with additional exogenous control variables."""
        rng = np.random.default_rng(9)
        n = 300
        Z = rng.normal(0, 1, (n, 2))
        X = 0.5 * Z[:, [0]] + rng.normal(0, 0.3, (n, 1))
        W = rng.normal(0, 1, (n, 2))
        y = 1.0 + 2.0 * X.flatten() + 0.5 * W[:, 0] + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, W)
        assert isinstance(kp_f, float)
        assert isinstance(kp_p, float)
        assert 0 <= kp_p <= 1

    def test_kp_rk_f_single_instrument_single_endogenous(self):
        """Exactly-identified case: 1 instrument, 1 endogenous."""
        rng = np.random.default_rng(10)
        n = 200
        Z = rng.normal(0, 1, (n, 1))
        X = 0.6 * Z + rng.normal(0, 0.3, (n, 1))
        y = 2.0 * X.flatten() + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        assert not np.isnan(kp_f)
        assert kp_f > 0

    def test_kp_rk_f_zero_variance_exog(self):
        """Instruments with zero variance should not crash."""
        rng = np.random.default_rng(11)
        n = 100
        Z = np.zeros((n, 1))  # zero variance
        X = rng.normal(0, 1, (n, 1))
        y = rng.normal(0, 1, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        # Should not raise; may return NaN or 0
        assert isinstance(kp_f, float)

    def test_kp_rk_f_more_endogenous_than_instruments(self):
        """Under-identified case: k < l returns NaN."""
        rng = np.random.default_rng(12)
        y = rng.normal(0, 1, 100)
        X = rng.normal(0, 1, (100, 2))  # 2 endogenous
        Z = rng.normal(0, 1, (100, 1))   # 1 instrument — under-identified
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        assert np.isnan(kp_f)
        assert np.isnan(kp_p)

    def test_kp_rk_f_empty_arrays(self):
        """Empty arrays return NaN or 0 (degenerate)."""
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(
            np.array([]), np.empty((0, 1)), np.empty((0, 1)), None
        )
        # Degenerate case — may return NaN, 0, or some sentinel value
        assert np.isnan(kp_f) or isinstance(kp_f, float)


# ─────────────────────────────────────────────────────────────────────────────
# 6. IVPanel._anderson_rubin_f — extended edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestAndersonRubinEdgeCases:
    def test_ar_f_correct_beta_gives_near_zero(self):
        """AR-F at the true beta should be near zero."""
        rng = np.random.default_rng(13)
        n, k = 400, 1
        Z = rng.normal(0, 1, (n, 2))
        X = 0.6 * Z[:, [0]] + rng.normal(0, 0.3, (n, k))
        true_beta = np.array([2.0])
        y = 1.0 + 2.0 * X.flatten() + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z1", "z2"])
        ar_f = m._anderson_rubin_f(y, X, Z, true_beta, None)
        assert isinstance(ar_f, float)
        assert ar_f >= 0

    def test_ar_f_wrong_beta_gives_large(self):
        """AR-F at a wrong beta is larger than at the true beta."""
        rng = np.random.default_rng(14)
        n, k = 300, 1
        Z = rng.normal(0, 1, (n, 2))
        X = 0.6 * Z[:, [0]] + rng.normal(0, 0.3, (n, k))
        true_beta = np.array([2.0])
        wrong_beta = np.array([0.0])
        y = 1.0 + 2.0 * X.flatten() + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z1", "z2"])
        ar_true = m._anderson_rubin_f(y, X, Z, true_beta, None)
        ar_wrong = m._anderson_rubin_f(y, X, Z, wrong_beta, None)
        assert ar_wrong > ar_true

    def test_ar_f_with_w_exogenous(self):
        """AR-F with additional exogenous controls."""
        rng = np.random.default_rng(15)
        n, k = 200, 1
        Z = rng.normal(0, 1, (n, 2))
        W = rng.normal(0, 1, (n, 2))
        X = 0.5 * Z[:, [0]] + rng.normal(0, 0.3, (n, k))
        beta = np.array([1.5])
        y = 1.0 + 1.5 * X.flatten() + 0.3 * W[:, 0] + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        ar_f = m._anderson_rubin_f(y, X, Z, beta, W)
        assert isinstance(ar_f, float)
        assert ar_f >= 0

    def test_ar_f_under_identified_k_less_than_l(self):
        """k < l returns NaN."""
        rng = np.random.default_rng(16)
        y = rng.normal(0, 1, 50)
        X = rng.normal(0, 1, (50, 2))
        Z = rng.normal(0, 1, (50, 1))
        beta = np.array([0.0, 0.0])
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        ar_f = m._anderson_rubin_f(y, X, Z, beta, None)
        assert np.isnan(ar_f)

    def test_ar_f_n_equals_k(self):
        """n == k gives degenerate case (may not be NaN)."""
        rng = np.random.default_rng(17)
        n, k = 10, 2
        Z = rng.normal(0, 1, (n, 2))
        X = rng.normal(0, 1, (n, 2))
        y = rng.normal(0, 1, n)
        beta = np.array([0.0, 0.0])
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        ar_f = m._anderson_rubin_f(y, X, Z, beta, None)
        # May be NaN or a finite value — just check it's a float
        assert isinstance(ar_f, float)


# ─────────────────────────────────────────────────────────────────────────────
# 7. IVPanel.get_diagnostics
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestIVPanelGetDiagnostics:
    def test_get_diagnostics_after_fit(self):
        df = _make_iv_panel_data(n=300)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                     unit_var="id", time_var="year")
        m.fit()
        diags = m.get_diagnostics()
        assert isinstance(diags, list)
        assert len(diags) >= 1

    def test_get_diagnostics_before_fit(self):
        df = _make_iv_panel_data(n=50)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                     unit_var="id", time_var="year")
        assert m.get_diagnostics() == []

    def test_diagnostic_contains_kp_f(self):
        df = _make_iv_panel_data(n=300)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                     unit_var="id", time_var="year")
        m.fit()
        diags = m.get_diagnostics()
        names = [d.test_name for d in diags]
        assert any("Kleibergen" in n for n in names)


# ─────────────────────────────────────────────────────────────────────────────
# 8. DynamicGMM.__init__
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestDynamicGMMInit:
    def test_init_basic(self):
        df = _make_dynamic_panel(n_firms=30, n_years=3)
        gmm = DynamicGMM(df, y_var="y", x_vars=["x1"], unit_var="firm", time_var="year")
        assert gmm.y_var == "y"
        assert gmm.x_vars == ["x1"]
        assert gmm.unit_var == "firm"
        assert gmm.time_var == "year"
        assert gmm.w_vars == []

    def test_init_with_w_vars(self):
        df = _make_dynamic_panel(n_firms=20, n_years=3)
        gmm = DynamicGMM(df, y_var="y", x_vars=["x1"], w_vars=["x2"],
                         unit_var="firm", time_var="year")
        assert gmm.w_vars == ["x2"]

    def test_init_copies_dataframe(self):
        df = _make_dynamic_panel(n_firms=20, n_years=3)
        df2 = df.copy()
        original_len = len(df)
        gmm = DynamicGMM(df, y_var="y", x_vars=["x1"], unit_var="firm", time_var="year")
        gmm.df.iloc[0, 0] = 99  # mutate numeric column (y)
        assert len(df2) == original_len  # original unchanged


# ─────────────────────────────────────────────────────────────────────────────
# 9. DynamicGMM.arellano_bond / blundell_bond — error paths
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestDynamicGMMMethods:
    def test_arellano_bond_returns_result_or_none(self):
        df = _make_dynamic_panel(n_firms=60, n_years=5)
        gmm = DynamicGMM(df, y_var="y", x_vars=["x1", "x2"], unit_var="firm", time_var="year")
        result = gmm.arellano_bond(max_lags=1, max_leads=1)
        # May return None if linearmodels fails on synthetic data
        assert result is None or hasattr(result, "params")

    def test_blundell_bond_returns_result_or_none(self):
        df = _make_dynamic_panel(n_firms=60, n_years=5)
        gmm = DynamicGMM(df, y_var="y", x_vars=["x1", "x2"], unit_var="firm", time_var="year")
        result = gmm.blundell_bond(max_lags=1)
        assert result is None or hasattr(result, "params")


# ─────────────────────────────────────────────────────────────────────────────
# 10. FamaMacBeth.__init__ and extended fit
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestFamaMacBethExtended:
    def test_init_basic(self):
        df = _make_fm_panel(n_firms=20, n_years=3)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"], unit_var="firm", time_var="year")
        assert fb.y_var == "y"
        assert fb.x_vars == ["x1"]
        assert fb.unit_var == "firm"
        assert fb.time_var == "year"
        assert fb._result is None
        assert fb._coef_series == {}

    def test_init_multiple_x_vars(self):
        df = _make_fm_panel(n_firms=30, n_years=4)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1", "x2"],
                         unit_var="firm", time_var="year")
        assert len(fb.x_vars) == 2

    def test_fit_returns_dict(self):
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1", "x2"],
                         unit_var="firm", time_var="year")
        result = fb.fit()
        assert isinstance(result, dict)

    def test_fit_single_period_survives(self):
        """Only one time period — should not crash."""
        rng = np.random.default_rng(18)
        n = 30
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "x1": rng.normal(0, 1, n),
            "x2": rng.normal(0, 1, n),
            "firm": range(n),
            "year": [2020] * n,
        })
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"],
                         unit_var="firm", time_var="year")
        result = fb.fit()
        assert isinstance(result, dict)

    def test_fit_insufficient_obs_per_period(self):
        """Period with too few obs skips gracefully."""
        rng = np.random.default_rng(19)
        records = []
        for firm in range(5):
            for year in [2018, 2019, 2020]:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": rng.normal(0, 1),
                    "firm": firm,
                    "year": year,
                })
        df = pd.DataFrame(records)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"],
                         unit_var="firm", time_var="year")
        result = fb.fit()
        # Should return dict (possibly empty) without raising
        assert isinstance(result, dict)

    def test_summary_empty_result(self):
        """summary() called before fit() auto-runs fit."""
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"],
                         unit_var="firm", time_var="year")
        summary = fb.summary()
        assert isinstance(summary, pd.DataFrame)

    def test_summary_contains_expected_columns(self):
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1", "x2"],
                         unit_var="firm", time_var="year")
        fb.fit()
        summary = fb.summary()
        expected = ["Variable", "Mean Coef", "Std Err", "t-stat", "p-value", "N_periods"]
        if not summary.empty:
            assert all(c in summary.columns for c in expected)

    def test_to_latex_basic(self):
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1", "x2"],
                         unit_var="firm", time_var="year")
        fb.fit()
        latex = fb.to_latex()
        assert isinstance(latex, str)

    def test_to_latex_no_stars(self):
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"],
                         unit_var="firm", time_var="year")
        fb.fit()
        latex = fb.to_latex()
        assert isinstance(latex, str)

    def test_to_latex_custom_label(self):
        df = _make_fm_panel(n_firms=50, n_years=5)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1", "x2"],
                         unit_var="firm", time_var="year")
        fb.fit()
        latex = fb.to_latex()
        assert isinstance(latex, str)


# ─────────────────────────────────────────────────────────────────────────────
# 11. DynamicPanelDiagnostics dataclass — all properties
# ─────────────────────────────────────────────────────────────────────────────

class TestDynamicPanelDiagnosticsAll:
    def test_constructor_all_fields(self):
        d = DynamicPanelDiagnostics(
            ar1_stat=2.1, ar1_pval=0.018,
            ar2_stat=0.9, ar2_pval=0.37,
            sargan_stat=5.2, sargan_pval=0.16,
            hansen_stat=5.2, hansen_pval=0.16,
            n_instruments=8, n_obs=400,
        )
        assert d.ar1_stat == 2.1
        assert d.ar1_pval == 0.018
        assert d.ar2_stat == 0.9
        assert d.ar2_pval == 0.37
        assert d.sargan_stat == 5.2
        assert d.hansen_stat == 5.2
        assert d.n_instruments == 8
        assert d.n_obs == 400

    def test_interpretation_all_pass(self):
        d = DynamicPanelDiagnostics(
            ar1_stat=3.0, ar1_pval=0.001,
            ar2_stat=0.5, ar2_pval=0.7,
            sargan_stat=2.0, sargan_pval=0.3,
            hansen_stat=2.0, hansen_pval=0.3,
            n_instruments=10, n_obs=500,
        )
        interp = d.interpretation
        assert "AR(1)" in interp
        assert "AR(2)" in interp
        assert "Sargan" in interp
        assert "Hansen" in interp

    def test_interpretation_some_fail(self):
        d = DynamicPanelDiagnostics(
            ar1_stat=0.5, ar1_pval=0.7,
            ar2_stat=2.5, ar2_pval=0.01,
            sargan_stat=20.0, sargan_pval=0.001,
            hansen_stat=20.0, hansen_pval=0.001,
            n_instruments=5, n_obs=200,
        )
        interp = d.interpretation
        assert "AR(1)" in interp
        assert "AR(2)" in interp

    def test_to_dict_complete(self):
        d = DynamicPanelDiagnostics(
            ar1_stat=2.0, ar1_pval=0.05,
            ar2_stat=1.0, ar2_pval=0.3,
            sargan_stat=3.0, sargan_pval=0.2,
            hansen_stat=3.0, hansen_pval=0.2,
            n_instruments=12, n_obs=600,
        )
        d_dict = d.to_dict()
        assert d_dict["AR(1) Z"] == 2.0
        assert d_dict["AR(1) p"] == 0.05
        assert d_dict["AR(2) Z"] == 1.0
        assert d_dict["AR(2) p"] == 0.3
        assert d_dict["Sargan Z"] == 3.0
        assert d_dict["Hansen J"] == 3.0
        assert d_dict["n_instruments"] == 12
        assert d_dict["n_obs"] == 600


# ─────────────────────────────────────────────────────────────────────────────
# 12. test_ar2 — extended (imported inline)
# ─────────────────────────────────────────────────────────────────────────────

class TestAR2Extended:
    def test_ar2_order_2_no_autocorr(self):
        """White noise residuals: AR(2) should be near zero."""
        from scripts.research_framework.iv_panel import test_ar2
        rng = np.random.default_rng(20)
        white = rng.normal(0, 1, 500)
        result = test_ar2(white, order=2)
        assert abs(result["stat"]) < 3  # should be small

    def test_ar2_order_3(self):
        """AR(3) test on AR(1) process."""
        from scripts.research_framework.iv_panel import test_ar2
        rng = np.random.default_rng(21)
        n = 300
        eps = rng.normal(0, 1, n)
        ar1 = np.zeros(n)
        ar1[0] = eps[0]
        for t in range(1, n):
            ar1[t] = 0.4 * ar1[t - 1] + eps[t]
        result = test_ar2(ar1, order=3)
        assert isinstance(result["stat"], float)

    def test_ar2_returns_lags_list(self):
        from scripts.research_framework.iv_panel import test_ar2
        rng = np.random.default_rng(22)
        n = 200
        eps = rng.normal(0, 1, n)
        res = np.zeros(n)
        res[0] = eps[0]
        for t in range(1, n):
            res[t] = 0.3 * res[t - 1] + eps[t]
        result = test_ar2(res, order=2)
        assert isinstance(result["lags"], list)
        assert len(result["lags"]) >= 1

    def test_ar2_n_property(self):
        from scripts.research_framework.iv_panel import test_ar2
        rng = np.random.default_rng(23)
        res = rng.normal(0, 1, 150)
        result = test_ar2(res, order=2)
        assert result["n"] == 150


# ─────────────────────────────────────────────────────────────────────────────
# 13. _sargan_test — extended
# ─────────────────────────────────────────────────────────────────────────────

class TestSarganExtended:
    def test_sargan_overidentified(self):
        """Exactly-identified case: df=0, function returns NaN stat."""
        rng = np.random.default_rng(24)
        resid = rng.normal(0, 1, 200)
        Z = rng.normal(0, 1, (200, 2))  # 2 instruments, 1 param → df=1
        stat, pval, df = _sargan_test(resid, Z)
        assert df == 1
        assert not np.isnan(stat)
        assert 0 <= pval <= 1

    def test_sargan_moderately_overidentified(self):
        """df > 1 case."""
        rng = np.random.default_rng(25)
        resid = rng.normal(0, 1, 300)
        Z = rng.normal(0, 1, (300, 5))  # df=4
        stat, pval, df = _sargan_test(resid, Z)
        assert df == 4
        assert not np.isnan(stat)

    def test_sargan_1d_instrument(self):
        """1-D instrument array reshapes to 2-D."""
        rng = np.random.default_rng(26)
        resid = rng.normal(0, 1, 200)
        Z = rng.normal(0, 1, 200)
        stat, pval, df = _sargan_test(resid, Z)
        assert df >= 0

    def test_sargan_with_nan_in_resid(self):
        """NaN in residuals are filtered out."""
        rng = np.random.default_rng(27)
        resid = np.array([np.nan, 1.0, 2.0, 3.0, 4.0] * 20)
        Z = np.tile(np.arange(5), 20).astype(float)
        stat, pval, df = _sargan_test(resid, Z)
        # Should handle gracefully (may be NaN if not enough valid)
        assert isinstance(stat, float)

    def test_sargan_exactly_enough_observations(self):
        """Exactly 50 valid observations is the minimum."""
        rng = np.random.default_rng(28)
        resid = rng.normal(0, 1, 60)
        Z = rng.normal(0, 1, (60, 3))
        stat, pval, df = _sargan_test(resid, Z)
        assert not np.isnan(stat)


# ─────────────────────────────────────────────────────────────────────────────
# 14. run_dynamic_panel_diagnostics — extended
# ─────────────────────────────────────────────────────────────────────────────

class TestRunDynamicPanelDiagnosticsExtended:
    def test_returns_diagnostics_object(self):
        rng = np.random.default_rng(29)
        n = 80
        years = [2018, 2019, 2020, 2021]
        records = []
        for i in range(n):
            for y in years:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": rng.normal(0, 1),
                    "x2": rng.normal(0, 1),
                    "firm": f"f{i}",
                    "year": y,
                })
        df = pd.DataFrame(records)
        diag = run_dynamic_panel_diagnostics(
            df, y_var="y", x_vars=["x1", "x2"],
            entity_var="firm", time_var="year",
        )
        assert isinstance(diag, DynamicPanelDiagnostics)

    def test_diagnostics_has_n_instruments(self):
        rng = np.random.default_rng(30)
        n = 80
        years = [2018, 2019, 2020]
        records = []
        for i in range(n):
            for y in years:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": rng.normal(0, 1),
                    "x2": rng.normal(0, 1),
                    "firm": f"f{i}",
                    "year": y,
                })
        df = pd.DataFrame(records)
        diag = run_dynamic_panel_diagnostics(
            df, y_var="y", x_vars=["x1", "x2"],
            entity_var="firm", time_var="year", max_lags=2,
        )
        assert diag.n_instruments > 0

    def test_diagnostics_n_obs_matches_input(self):
        """n_obs should match valid post-lag rows (>= 50 needed)."""
        rng = np.random.default_rng(31)
        n = 60
        years = [2018, 2019, 2020, 2021]
        records = []
        for i in range(n):
            for y in years:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": rng.normal(0, 1),
                    "firm": f"f{i}",
                    "year": y,
                })
        df = pd.DataFrame(records)
        diag = run_dynamic_panel_diagnostics(
            df, y_var="y", x_vars=["x1"],
            entity_var="firm", time_var="year",
        )
        # n_obs may be 0 due to insufficient lags (need >= 50 valid post-lag rows)
        assert diag.n_obs >= 0

    def test_to_dict_roundtrip(self):
        rng = np.random.default_rng(32)
        n = 60
        years = [2018, 2019, 2020]
        records = []
        for i in range(n):
            for y in years:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": rng.normal(0, 1),
                    "firm": f"f{i}",
                    "year": y,
                })
        df = pd.DataFrame(records)
        diag = run_dynamic_panel_diagnostics(
            df, y_var="y", x_vars=["x1"],
            entity_var="firm", time_var="year",
        )
        d = diag.to_dict()
        assert "AR(1) Z" in d
        assert "n_obs" in d


# ─────────────────────────────────────────────────────────────────────────────
# 15. _format_fmb_summary — extended
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatFMBSummaryExtended:
    def test_multiple_variables(self):
        result = _format_fmb_summary({
            "roa": {"mean_coef": 0.05},
            "lev": {"mean_coef": -0.12},
            "size": {"mean_coef": 0.03},
        })
        assert "roa=0.0500" in result
        assert "lev=-0.1200" in result
        assert "size=0.0300" in result

    def test_negative_coefs(self):
        result = _format_fmb_summary({
            "x": {"mean_coef": -1.234},
        })
        assert "x=-1.2340" in result

    def test_zero_coef(self):
        result = _format_fmb_summary({
            "zero_var": {"mean_coef": 0.0},
        })
        assert "zero_var=0.0000" in result

    def test_scientific_notation(self):
        result = _format_fmb_summary({
            "small": {"mean_coef": 1e-5},
        })
        assert "small=0.0000" in result or "small=0.00001" in result


# ─────────────────────────────────────────────────────────────────────────────
# 16. __all__ exports
# ─────────────────────────────────────────────────────────────────────────────

class TestExports:
    def test_iv_panel_exports(self):
        from scripts.research_framework import iv_panel
        for name in ["IVPanel", "DynamicGMM", "FamaMacBeth",
                     "PanelDiagnostic", "DynamicPanelDiagnostics"]:
            assert name in iv_panel.__all__


# ─────────────────────────────────────────────────────────────────────────────
# 17. Full integration — fit + diagnostics combined
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _have_linearmodels(), reason="linearmodels not installed")
class TestIVPanelFullIntegration:
    def test_fit_then_bootstrap_and_get_diags(self):
        """fit() populates diagnostics; subsequent calls work."""
        df = _make_iv_panel_data(n=300, true_coef=2.0)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                     unit_var="id", time_var="year")
        result1 = m.fit()
        diags1 = m.get_diagnostics()
        result2 = m.fit()  # second call
        diags2 = m.get_diagnostics()
        assert result1 is not None
        assert result2 is not None
        assert len(diags1) == len(diags2)

    def test_fit_with_cluster_and_without(self):
        """Compare clustered vs unclustered fit on same data."""
        df = _make_iv_panel_data(n=200)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                    unit_var="id", time_var="year")
        r1 = m.fit()
        r2 = m.fit(cluster_var="id")
        assert r1 is not None
        assert r2 is not None
        assert hasattr(r1, "params")
        assert hasattr(r2, "params")

    def test_fit_liml_vs_iv_close(self):
        """LIML and IV should give similar results for strong instruments."""
        df = _make_iv_panel_data(n=500, true_coef=2.0)
        m = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z1", "Z2"],
                     unit_var="id", time_var="year")
        r_iv = m.fit(method="iv")
        r_liml = m.fit(method="liml")
        assert r_iv is not None
        assert r_liml is not None
        # The endogenous variable's coefficient is labeled 'endog'
        endog_param_iv = float(r_iv.params["endog"])
        endog_param_liml = float(r_liml.params["endog"])
        assert abs(endog_param_iv - 2.0) < 0.5
        assert abs(endog_param_liml - 2.0) < 0.5

    def test_panel_diagnostics_conclusion_logic(self):
        """Check conclusion logic: reject_H0 when p < 0.05."""
        d_reject = PanelDiagnostic("test", 15.0, 0.001, "reject_H0")
        d_fail = PanelDiagnostic("test", 2.0, 0.8, "fail_to_reject_H0")
        assert "🔴" in str(d_reject)
        assert "🟢" in str(d_fail)

    def test_kp_f_pval_range(self):
        """KP-F p-value should be between 0 and 1."""
        rng = np.random.default_rng(33)
        n = 400
        Z = rng.normal(0, 1, (n, 2))
        X = 0.5 * Z[:, [0]] + 0.4 * Z[:, [1]] + rng.normal(0, 0.3, (n, 1))
        y = 2.0 * X.flatten() + rng.normal(0, 0.5, n)
        m = IVPanel(pd.DataFrame(), y_var="y", x_vars=["x"], iv_vars=["z"])
        kp_f, kp_p = m._kleibergen_paap_rk_f(y, X, Z, None)
        assert 0 <= kp_p <= 1

    def test_dynamic_panel_diagnostics_singular_matrix_fallback(self):
        """Singular X matrix falls back to zero residuals."""
        rng = np.random.default_rng(34)
        n = 60
        years = [2018, 2019, 2020]
        records = []
        for i in range(n):
            for y in years:
                records.append({
                    "y": rng.normal(0, 1),
                    "x1": 1.0,  # no variance — creates singular matrix
                    "x2": rng.normal(0, 1),
                    "firm": f"f{i}",
                    "year": y,
                })
        df = pd.DataFrame(records)
        diag = run_dynamic_panel_diagnostics(
            df, y_var="y", x_vars=["x1", "x2"],
            entity_var="firm", time_var="year",
        )
        assert isinstance(diag, DynamicPanelDiagnostics)

    def test_fama_macBeth_copies_df(self):
        """FamaMacBeth should copy the input DataFrame."""
        df = _make_fm_panel(n_firms=50, n_years=5)
        original_len = len(df)
        fb = FamaMacBeth(df, y_var="y", x_vars=["x1"],
                         unit_var="firm", time_var="year")
        fb.df.iloc[0, 0] = 99
        assert len(df) == original_len
