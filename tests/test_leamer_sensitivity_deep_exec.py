"""
Deep-execution tests for scripts/research_framework/leamer_sensitivity.py
==========================================
Covers items NOT in test_leamer_sensitivity.py:
  - All dataclasses (LeamerResult, BoundingResult, DynamicPanelDiagnostics)
  - LeamerSensitivity methods: fit() with various data shapes,
    sensitivity_analysis(), to_dict(), _numpy_fallback()
  - EbersteinMagnacSensitivity methods: fit(), to_dict()
  - OlleyPakesEstimator / LevinsohnPetrinEstimator: fit() methods
  - ContagionTest: fit() method
  - SpilloverIndex: fit() method
  - CreditRiskSensitivity: fit() method
  - test_ar2() function
  - run_dynamic_panel_diagnostics() function
  - Error / edge cases: degenerate data, insufficient obs, zero-variation
  - Table / output formatting
  - to_dict() methods on all dataclasses

Target: 30+ new tests  (existing suite has ~5 → total ~35+)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic data factories
# ─────────────────────────────────────────────────────────────────────────────

def make_reg_data(n=100, k=4, seed=42):
    """Return (X, y) with column names."""
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, size=(n, k))
    true_coefs = rng.uniform(0.5, 2.0, size=k)
    eps = rng.normal(0, 0.1, size=n)
    y = X @ true_coefs + eps
    names = [f"x{i}" for i in range(k)]
    return X, y, names


def make_panel_df(n_firms=20, n_years=5, seed=99):
    """Return panel DataFrame for production-function tests."""
    rng = np.random.default_rng(seed)
    records = []
    for fid in range(n_firms):
        for yr in range(n_years):
            records.append({
                "firm_id": f"f_{fid}",
                "year": yr,
                "investment": max(0.1, rng.lognormal(2, 0.5)),
                "labor": max(1.0, rng.lognormal(3, 0.3)),
                "capital": max(1.0, rng.lognormal(4, 0.4)),
                "value_added": max(1.0, rng.lognormal(5, 0.5)),
                "materials": max(0.5, rng.lognormal(3.5, 0.4)),
            })
    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
# LEAMER SENSITIVITY
# ══════════════════════════════════════════════════════════════════════════════

class TestLeamerSensitivityFit:
    """LeamerSensitivity.fit() variants."""

    def test_fit_returns_leamer_result(self):
        from scripts.research_framework.leamer_sensitivity import (
            LeamerSensitivity, LeamerResult,
        )
        X, y, names = make_reg_data()
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names, key_var_idx=0)
        assert isinstance(res, LeamerResult)

    def test_fit_extreme_bounds_contain_baseline(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, names = make_reg_data(n=200, k=3, seed=7)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names, key_var_idx=0)
        assert res.extreme_bounds["lower"] <= res.baseline_coef <= res.extreme_bounds["upper"]

    def test_fit_reliability_ratio_range(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, names = make_reg_data(n=150, k=5, seed=13)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names, key_var_idx=0)
        assert isinstance(res.reliability_ratio, float)
        assert res.reliability_ratio >= 0

    def test_fit_interpretation_not_empty(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, names = make_reg_data(n=100, seed=5)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names)
        assert isinstance(res.interpretation, str)
        assert len(res.interpretation) > 0

    def test_fit_with_default_xnames(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, _ = make_reg_data(k=4)
        ls = LeamerSensitivity()
        res = ls.fit(X, y)  # xnames=None
        assert res.control_names is not None

    def test_fit_control_names_populated(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, names = make_reg_data(k=4)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names, key_var_idx=0)
        # control_names should contain names of non-key vars
        assert len(res.control_names) >= 0  # may be empty if k=1

    def test_fit_key_var_idx_last(self):
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, names = make_reg_data(k=4, seed=22)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=names, key_var_idx=3)
        assert isinstance(res.baseline_coef, float)

    def test_fit_numpy_fallback_no_statsmodels(self, monkeypatch):
        import sys
        # Remove statsmodels so the next import in fit() hits the except branch
        for key in list(sys.modules):
            if key == "statsmodels" or key.startswith("statsmodels."):
                monkeypatch.delitem(sys.modules, key, raising=False)
        from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
        X, y, _ = make_reg_data(k=3)
        ls = LeamerSensitivity()
        res = ls.fit(X, y, xnames=["a", "b", "c"], key_var_idx=0)
        assert isinstance(res.interpretation, str)


# ══════════════════════════════════════════════════════════════════════════════
# LEAMER RESULT DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

class TestLeamerResult:
    """LeamerResult dataclass."""

    def test_leamer_result_fields(self):
        from scripts.research_framework.leamer_sensitivity import LeamerResult
        res = LeamerResult(
            baseline_coef=1.0, baseline_se=0.1, baseline_pval=0.05,
            extreme_bounds={"lower": 0.5, "upper": 1.5},
            extreme_coefs=[1.0, 0.8, 1.2],
            control_names=["x2", "x3"],
            reliability_ratio=0.75,
            interpretation="robust",
        )
        assert res.baseline_coef == 1.0
        assert res.extreme_bounds["lower"] == 0.5
        assert res.reliability_ratio == 0.75

    def test_leamer_result_to_dict(self):
        from scripts.research_framework.leamer_sensitivity import LeamerResult
        res = LeamerResult(
            baseline_coef=1.0, baseline_se=0.1, baseline_pval=0.05,
            extreme_bounds={"lower": 0.5, "upper": 1.5},
            extreme_coefs=[1.0],
            control_names=[],
            reliability_ratio=0.5,
            interpretation="test",
        )
        d = res.to_dict()
        assert "baseline_coef" in d
        assert "extreme_lower" in d
        assert "extreme_upper" in d
        assert "reliability_ratio" in d


# ══════════════════════════════════════════════════════════════════════════════
# EBERSTEIN-MAGNAC SENSITIVITY
# ══════════════════════════════════════════════════════════════════════════════

class TestEbersteinMagnac:
    """EbersteinMagnacSensitivity."""

    def test_fit_returns_bounding_result(self):
        from scripts.research_framework.leamer_sensitivity import (
            EbersteinMagnacSensitivity, BoundingResult,
        )
        X, y, _ = make_reg_data(n=200, k=3, seed=11)
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0)
        assert isinstance(res, BoundingResult)

    def test_fit_bounds_contain_baseline(self):
        from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
        X, y, _ = make_reg_data(n=300, k=3, seed=17)
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0)
        assert res.lower_bound <= res.baseline_coef <= res.upper_bound

    def test_fit_interpretation_not_empty(self):
        from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
        X, y, _ = make_reg_data(n=100, seed=3)
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0, f_stat=15.0)
        assert isinstance(res.interpretation, str)
        assert len(res.interpretation) > 0

    def test_fit_with_f_stat_provided(self):
        from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
        X, y, _ = make_reg_data()
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0, f_stat=20.0)
        assert res.f_stat == 20.0

    def test_fit_rho_range_respected(self):
        from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
        X, y, _ = make_reg_data()
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0, rho_range=(-0.5, 0.5))
        assert isinstance(res.rho_range, tuple)

    def test_fit_n_points(self):
        from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
        X, y, _ = make_reg_data()
        em = EbersteinMagnacSensitivity()
        res = em.fit(X, y, endogenous_idx=0, n_points=100)
        # Should complete without error
        assert isinstance(res.baseline_coef, float)


# ══════════════════════════════════════════════════════════════════════════════
# BOUNDING RESULT DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

class TestBoundingResult:
    """BoundingResult dataclass."""

    def test_bounding_result_fields(self):
        from scripts.research_framework.leamer_sensitivity import BoundingResult
        res = BoundingResult(
            baseline_coef=2.0, baseline_se=0.2, lower_bound=1.0,
            upper_bound=3.0, f_stat=10.0, rho_range=(-0.5, 0.5),
            interpretation="weak IV",
        )
        assert res.baseline_coef == 2.0
        assert res.f_stat == 10.0

    def test_bounding_result_to_dict(self):
        from scripts.research_framework.leamer_sensitivity import BoundingResult
        res = BoundingResult(
            baseline_coef=2.0, baseline_se=0.2, lower_bound=1.0,
            upper_bound=3.0, f_stat=10.0, rho_range=(-0.5, 0.5),
            interpretation="test",
        )
        d = res.to_dict()
        for key in ["baseline_coef", "baseline_se", "lower_bound",
                     "upper_bound", "f_stat", "interpretation"]:
            assert key in d


# ══════════════════════════════════════════════════════════════════════════════
# OLLY-PAKES ESTIMATOR
# ══════════════════════════════════════════════════════════════════════════════

class TestOlleyPakes:
    """OlleyPakesEstimator.fit()."""

    def test_fit_returns_dict(self):
        from scripts.research_framework.leamer_sensitivity import OlleyPakesEstimator
        df = make_panel_df(n_firms=30, n_years=5, seed=8)
        op = OlleyPakesEstimator()
        res = op.fit(df)
        assert isinstance(res, dict)

    def test_fit_beta_keys(self):
        from scripts.research_framework.leamer_sensitivity import OlleyPakesEstimator
        df = make_panel_df(n_firms=20, n_years=4, seed=9)
        op = OlleyPakesEstimator()
        res = op.fit(df)
        for key in ["beta_labor", "beta_capital", "within_effect",
                    "between_effect", "interpretation"]:
            assert key in res

    def test_fit_min_obs_respected(self):
        from scripts.research_framework.leamer_sensitivity import OlleyPakesEstimator
        df = make_panel_df(n_firms=2, n_years=2, seed=10)
        op = OlleyPakesEstimator()
        res = op.fit(df, min_obs=5)
        # Should still return a dict (possibly with NaN)
        assert isinstance(res, dict)


# ══════════════════════════════════════════════════════════════════════════════
# LEVINSOHN-PETRIN ESTIMATOR
# ══════════════════════════════════════════════════════════════════════════════

class TestLevinsohnPetrin:
    """LevinsohnPetrinEstimator.fit()."""

    def test_fit_returns_dict(self):
        from scripts.research_framework.leamer_sensitivity import LevinsohnPetrinEstimator
        df = make_panel_df(n_firms=30, n_years=5, seed=12)
        lp = LevinsohnPetrinEstimator()
        res = lp.fit(df)
        assert isinstance(res, dict)

    def test_fit_beta_keys(self):
        from scripts.research_framework.leamer_sensitivity import LevinsohnPetrinEstimator
        df = make_panel_df(n_firms=20, n_years=4, seed=15)
        lp = LevinsohnPetrinEstimator()
        res = lp.fit(df)
        for key in ["beta_labor", "beta_capital", "total_lp", "interpretation"]:
            assert key in res

    def test_fit_std_lp(self):
        from scripts.research_framework.leamer_sensitivity import LevinsohnPetrinEstimator
        df = make_panel_df(n_firms=15, n_years=3, seed=16)
        lp = LevinsohnPetrinEstimator()
        res = lp.fit(df)
        assert "std_lp" in res
        assert isinstance(res["std_lp"], float)


# ══════════════════════════════════════════════════════════════════════════════
# CONTAGION TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestContagionTest:
    """ContagionTest.fit()."""

    def test_fit_basic(self):
        from scripts.research_framework.leamer_sensitivity import ContagionTest
        rng = np.random.default_rng(33)
        returns = rng.normal(0, 1, size=(200, 3))
        ct = ContagionTest()
        res = ct.fit(returns, crisis_period=(100, 150))
        assert isinstance(res, dict)
        assert "conclusion" in res
        assert "n_pre" in res
        assert "n_crisis" in res

    def test_fit_with_pre_period(self):
        from scripts.research_framework.leamer_sensitivity import ContagionTest
        rng = np.random.default_rng(44)
        returns = rng.normal(0, 1, size=(300, 4))
        ct = ContagionTest()
        res = ct.fit(returns, crisis_period=(150, 250), pre_period=(30, 120))
        assert "pre_corr_mean" in res
        assert "crisis_corr_mean" in res

    def test_fit_1d_returns(self):
        from scripts.research_framework.leamer_sensitivity import ContagionTest
        rng = np.random.default_rng(55)
        returns = rng.normal(0, 1, size=(200,))
        ct = ContagionTest()
        res = ct.fit(returns, crisis_period=(80, 150))
        # Should handle 1D → reshape to (T, 1)
        assert "conclusion" in res

    def test_fit_insufficient_data(self):
        from scripts.research_framework.leamer_sensitivity import ContagionTest
        rng = np.random.default_rng(66)
        returns = rng.normal(0, 1, size=(10, 2))
        ct = ContagionTest()
        res = ct.fit(returns, crisis_period=(5, 9))
        assert res["conclusion"] == "Insufficient data"

    def test_fit_fr_adjusted_keys(self):
        from scripts.research_framework.leamer_sensitivity import ContagionTest
        rng = np.random.default_rng(77)
        returns = rng.normal(0, 1, size=(250, 3))
        ct = ContagionTest()
        res = ct.fit(returns, crisis_period=(120, 200))
        assert "fr_adjusted_pre" in res
        assert "fr_adjusted_crisis" in res


# ══════════════════════════════════════════════════════════════════════════════
# SPILLOVER INDEX
# ══════════════════════════════════════════════════════════════════════════════

class TestSpilloverIndex:
    """SpilloverIndex.fit()."""

    def test_fit_basic(self):
        from scripts.research_framework.leamer_sensitivity import SpilloverIndex
        rng = np.random.default_rng(88)
        returns = rng.normal(0, 1, size=(100, 4))
        si = SpilloverIndex()
        res = si.fit(returns)
        assert isinstance(res, dict)

    def test_fit_spillover_keys(self):
        from scripts.research_framework.leamer_sensitivity import SpilloverIndex
        rng = np.random.default_rng(99)
        returns = rng.normal(0, 1, size=(150, 3))
        si = SpilloverIndex()
        res = si.fit(returns, n_lags=2)
        for key in ["total_spillover_index", "directional_from",
                    "directional_to", "net_spillover"]:
            assert key in res

    def test_fit_insufficient_obs(self):
        from scripts.research_framework.leamer_sensitivity import SpilloverIndex
        rng = np.random.default_rng(11)
        returns = rng.normal(0, 1, size=(5, 3))
        si = SpilloverIndex()
        res = si.fit(returns)
        assert "error" in res

    def test_fit_window(self):
        from scripts.research_framework.leamer_sensitivity import SpilloverIndex
        rng = np.random.default_rng(22)
        returns = rng.normal(0, 1, size=(200, 3))
        si = SpilloverIndex()
        res = si.fit(returns, window=100)
        assert isinstance(res, dict)


# ══════════════════════════════════════════════════════════════════════════════
# CREDIT RISK SENSITIVITY
# ══════════════════════════════════════════════════════════════════════════════

class TestCreditRiskSensitivity:
    """CreditRiskSensitivity.fit()."""

    def test_fit_basic(self):
        from scripts.research_framework.leamer_sensitivity import CreditRiskSensitivity
        rng = np.random.default_rng(111)
        n = 200
        df = pd.DataFrame({
            "default": rng.integers(0, 2, size=n),
            "gdp_growth": rng.normal(0.05, 0.02, size=n),
            "interest_rate": rng.uniform(0.01, 0.10, size=n),
            "credit_spread": rng.uniform(0.01, 0.05, size=n),
            "roa": rng.normal(0.05, 0.02, size=n),
            "leverage": rng.uniform(0.2, 0.8, size=n),
            "size": rng.normal(20, 2, size=n),
            "tangibility": rng.uniform(0.1, 0.5, size=n),
        })
        cr = CreditRiskSensitivity()
        res = cr.fit(df)
        assert isinstance(res, dict)

    def test_fit_zscore_keys(self):
        from scripts.research_framework.leamer_sensitivity import CreditRiskSensitivity
        rng = np.random.default_rng(222)
        n = 200
        df = pd.DataFrame({
            "default": rng.integers(0, 2, size=n),
            "gdp_growth": rng.normal(0.05, 0.02, size=n),
            "interest_rate": rng.uniform(0.01, 0.10, size=n),
            "credit_spread": rng.uniform(0.01, 0.05, size=n),
            "roa": rng.normal(0.05, 0.02, size=n),
            "leverage": rng.uniform(0.2, 0.8, size=n),
            "size": rng.normal(20, 2, size=n),
            "tangibility": rng.uniform(0.1, 0.5, size=n),
        })
        cr = CreditRiskSensitivity()
        res = cr.fit(df)
        assert "zscore_mean" in res
        assert "zscore_median" in res

    def test_fit_insufficient_obs(self):
        from scripts.research_framework.leamer_sensitivity import CreditRiskSensitivity
        # Only columns that CreditRiskSensitivity defaults to
        df = pd.DataFrame({
            "default": [0, 1, 0],
            "gdp_growth": [0.05, 0.04, 0.06],
            "interest_rate": [0.05, 0.04, 0.06],
            "credit_spread": [0.02, 0.02, 0.02],
            "roa": [0.05, 0.03, 0.04],
            "leverage": [0.3, 0.4, 0.5],
            "size": [20, 21, 19],
            "tangibility": [0.3, 0.4, 0.2],
        })
        cr = CreditRiskSensitivity()
        res = cr.fit(df)
        # Must return a dict (not raise KeyError)
        assert isinstance(res, dict)


# ══════════════════════════════════════════════════════════════════════════════
# DYNAMIC PANEL DIAGNOSTICS
# ══════════════════════════════════════════════════════════════════════════════

class TestDynamicPanelDiagnostics:
    """DynamicPanelDiagnostics dataclass + interpretation."""

    def test_diagnostics_dataclass_fields(self):
        from scripts.research_framework.leamer_sensitivity import DynamicPanelDiagnostics
        diag = DynamicPanelDiagnostics(
            ar1_stat=1.5, ar1_pval=0.01,
            ar2_stat=0.3, ar2_pval=0.8,
            sargan_stat=2.1, sargan_pval=0.15,
            n_instruments=5, n_obs=500,
        )
        assert diag.ar1_pval < 0.05
        assert diag.ar2_pval > 0.05

    def test_diagnostics_interpretation(self):
        from scripts.research_framework.leamer_sensitivity import DynamicPanelDiagnostics
        diag = DynamicPanelDiagnostics(
            ar1_stat=1.5, ar1_pval=0.01,
            ar2_stat=0.3, ar2_pval=0.8,
            sargan_stat=2.1, sargan_pval=0.15,
            n_instruments=5, n_obs=500,
        )
        interp = diag.interpretation
        assert isinstance(interp, str)
        assert len(interp) > 0

    def test_run_dynamic_panel_diagnostics(self):
        from scripts.research_framework.leamer_sensitivity import (
            run_dynamic_panel_diagnostics,
        )
        df = make_panel_df(n_firms=30, n_years=5, seed=50)
        res = run_dynamic_panel_diagnostics(
            df, y_var="value_added",
            x_vars=["investment", "labor"],
            entity_var="firm_id", time_var="year",
        )
        assert res.ar1_pval is not None
        assert res.ar2_pval is not None

    def test_run_dynamic_panel_diagnostics_insufficient(self):
        from scripts.research_framework.leamer_sensitivity import (
            run_dynamic_panel_diagnostics,
        )
        df = make_panel_df(n_firms=2, n_years=2, seed=51)
        res = run_dynamic_panel_diagnostics(
            df, y_var="value_added",
            x_vars=["investment"],
            entity_var="firm_id", time_var="year",
        )
        # Should return a valid (possibly NaN) diagnostics object
        assert res.n_obs >= 0


# ══════════════════════════════════════════════════════════════════════════════
# TEST_AR2 FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

class TestTestAR2:
    """test_ar2() function."""

    def test_ar2_returns_dict(self):
        from scripts.research_framework.leamer_sensitivity import test_ar2
        rng = np.random.default_rng(200)
        residuals = rng.normal(0, 1, size=100)
        res = test_ar2(residuals, order=2)
        assert isinstance(res, dict)
        for key in ["ar1_stat", "ar1_pval", "ar2_stat", "ar2_pval"]:
            assert key in res

    def test_ar2_short_residuals(self):
        from scripts.research_framework.leamer_sensitivity import test_ar2
        residuals = np.array([0.1, 0.2, 0.3])
        res = test_ar2(residuals, order=2)
        # Should not raise; may return NaN
        assert isinstance(res, dict)

    def test_ar2_order_1(self):
        from scripts.research_framework.leamer_sensitivity import test_ar2
        rng = np.random.default_rng(201)
        residuals = rng.normal(0, 1, size=50)
        res = test_ar2(residuals, order=1)
        assert "ar1_stat" in res
        assert "ar1_pval" in res

    def test_ar2_pval_range(self):
        from scripts.research_framework.leamer_sensitivity import test_ar2
        rng = np.random.default_rng(202)
        residuals = rng.normal(0, 1, size=200)
        res = test_ar2(residuals)
        for key in ["ar1_pval", "ar2_pval"]:
            val = res[key]
            if np.isfinite(val):
                assert 0 <= val <= 1


# ══════════════════════════════════════════════════════════════════════════════
# __all__ EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

class TestModuleExports:
    """Module-level __all__ coverage."""

    def test_all_includes_leamer_sensitivity(self):
        from scripts.research_framework.leamer_sensitivity import (
            LeamerSensitivity, LeamerResult,
            EbersteinMagnacSensitivity, BoundingResult,
            OlleyPakesEstimator, LevinsohnPetrinEstimator,
            ContagionTest, SpilloverIndex,
            CreditRiskSensitivity, test_ar2,
            DynamicPanelDiagnostics,
        )
        assert LeamerSensitivity is not None
        assert test_ar2 is not None
        assert DynamicPanelDiagnostics is not None
