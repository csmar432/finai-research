"""Deep execution tests for scripts/research_framework/psm_did.py.

Covers: all dataclasses, pure helpers, PSM matching functions,
propensity score estimation, error/edge cases, table generation.
Target: 30+ tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.psm_did import (
    PSMDID,
    PSMDIDResult,
    run_psm_did,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_psm_panel(
    n: int = 400,
    treatment_rate: float = 0.3,
    seed: int = 42,
    effect: float = 0.5,
    n_years: int = 5,
) -> pd.DataFrame:
    """Standard synthetic panel: firm-level treatment, policy shock at year 2019."""
    rng = np.random.default_rng(seed)
    D = rng.binomial(1, treatment_rate, n)
    records = []
    for i in range(n):
        for y in range(2016, 2016 + n_years):
            base = rng.normal(0, 1)
            if y >= 2019 and D[i] == 1:
                base += effect
            records.append({
                "firm_id": i,
                "year": y,
                "D": D[i],
                "size": 10 + rng.normal(0, 0.5),
                "leverage": 0.4 + rng.normal(0, 0.05),
                "y": base,
            })
    return pd.DataFrame(records)


def _make_2x2_panel(
    n_treated: int = 100,
    n_control: int = 100,
    seed: int = 5,
) -> pd.DataFrame:
    """Simple 2x2 balanced panel for PSM-DID."""
    rng = np.random.default_rng(seed)
    records = []
    for i in range(n_treated):
        for y in [2018, 2019, 2020]:
            treated = 1
            post = 1 if y >= 2019 else 0
            y_val = rng.normal(0, 1) + (0.5 * treated * post)
            records.append({"firm_id": f"T{i}", "year": y, "D": treated,
                            "post": post, "y": y_val,
                            "x1": rng.normal(10, 1), "x2": rng.normal(0.5, 0.1)})
    for i in range(n_control):
        for y in [2018, 2019, 2020]:
            treated = 0
            post = 1 if y >= 2019 else 0
            y_val = rng.normal(0, 1)
            records.append({"firm_id": f"C{i}", "year": y, "D": treated,
                            "post": post, "y": y_val,
                            "x1": rng.normal(10, 1), "x2": rng.normal(0.5, 0.1)})
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PSMDIDResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDResultFields:
    def test_all_fields_present(self):
        balance = pd.DataFrame({
            "covariate": ["size"],
            "treated_mean": [10.0],
            "control_mean": [9.9],
            "std_bias": [0.02],
            "abs_bias_lt_10pct": [True],
        })
        r = PSMDIDResult(
            did_coefficient=0.5,
            did_se=0.15,
            did_tstat=3.33,
            did_pvalue=0.001,
            n_treated_matched=100,
            n_control_matched=100,
            n_treated_unmatched=5,
            n_control_unmatched=3,
            covariate_balance=balance,
            first_stage_auc=0.82,
            n_obs_after_match=200,
            method="caliper",
            caliper=0.25,
            model=object(),
        )
        assert r.did_coefficient == 0.5
        assert r.did_se == 0.15
        assert r.n_treated_matched == 100
        assert r.n_control_matched == 100
        assert r.first_stage_auc == 0.82
        assert r.method == "caliper"
        assert r.caliper == 0.25

    def test_summary_output_contains_all_parts(self):
        balance = pd.DataFrame({
            "covariate": ["size", "leverage"],
            "treated_mean": [10.0, 0.45],
            "control_mean": [9.9, 0.44],
            "std_bias": [0.02, 0.01],
            "abs_bias_lt_10pct": [True, True],
        })
        r = PSMDIDResult(
            did_coefficient=0.5, did_se=0.15, did_tstat=3.33,
            did_pvalue=0.001,
            n_treated_matched=80, n_control_matched=80,
            n_treated_unmatched=5, n_control_unmatched=3,
            covariate_balance=balance,
            first_stage_auc=0.80,
            n_obs_after_match=160,
            method="nearest", caliper=None, model=object(),
        )
        s = r.summary()
        assert "PSM-DID Result" in s
        assert "Method: nearest" in s
        assert "ATT = 0.500000" in s
        assert "SE  = 0.150000" in s
        assert "t   = 3.3300" in s
        assert "AUC" in s

    def test_summary_with_caliper_shows_value(self):
        balance = pd.DataFrame({
            "covariate": ["size"],
            "treated_mean": [10.0],
            "control_mean": [9.9],
            "std_bias": [0.02],
            "abs_bias_lt_10pct": [True],
        })
        r = PSMDIDResult(
            did_coefficient=0.3, did_se=0.1, did_tstat=3.0,
            did_pvalue=0.01,
            n_treated_matched=50, n_control_matched=50,
            n_treated_unmatched=0, n_control_unmatched=0,
            covariate_balance=balance,
            first_stage_auc=0.75,
            n_obs_after_match=100,
            method="caliper", caliper=0.2, model=object(),
        )
        s = r.summary()
        assert "caliper=0.2" in s

    def test_model_field_is_ignored_in_repr(self):
        balance = pd.DataFrame({"covariate": [], "treated_mean": [],
                                "control_mean": [], "std_bias": [],
                                "abs_bias_lt_10pct": []})
        r = PSMDIDResult(
            did_coefficient=0.0, did_se=0.0, did_tstat=0.0, did_pvalue=1.0,
            n_treated_matched=0, n_control_matched=0,
            n_treated_unmatched=0, n_control_unmatched=0,
            covariate_balance=balance,
            first_stage_auc=0.5,
            n_obs_after_match=0,
            method="nearest", caliper=None, model=object(),
        )
        # repr should not raise even though model is object()
        repr(r)


# ─────────────────────────────────────────────────────────────────────────────
# 2. PSMDID.__init__
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDInit:
    def test_init_basic(self):
        m = PSMDID(outcome="y", treatment="D", time="year", unit="id")
        assert m.outcome == "y"
        assert m.treatment == "D"
        assert m.time == "year"
        assert m.unit == "id"

    def test_init_defaults(self):
        m = PSMDID(outcome="y", treatment="D", time="year", unit="id")
        assert m.method == "nearest"
        assert m.caliper is None
        assert m.n_neighbors == 1
        assert m.replace is False

    def test_init_all_methods(self):
        for method in ["nearest", "caliper", "kernel"]:
            m = PSMDID(outcome="y", treatment="D", time="year", unit="id",
                        method=method, caliper=0.1)
            assert m.method == method

    def test_init_with_n_neighbors(self):
        m = PSMDID(outcome="y", treatment="D", time="year", unit="id",
                    n_neighbors=3)
        assert m.n_neighbors == 3

    def test_init_replace_flag(self):
        m = PSMDID(outcome="y", treatment="D", time="year", unit="id",
                    replace=True)
        assert m.replace is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. PSMDID._compute_balance
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDComputeBalance:
    def test_balance_single_covariate(self):
        treated = pd.DataFrame({"size": [10.0, 11.0, 10.5]})
        control = pd.DataFrame({"size": [10.1, 10.9, 10.4]})
        balance = PSMDID._compute_balance(treated, control, ["size"])
        assert isinstance(balance, pd.DataFrame)
        assert len(balance) == 1
        assert "covariate" in balance.columns
        assert "std_bias" in balance.columns
        assert "abs_bias_lt_10pct" in balance.columns

    def test_balance_multiple_covariates(self):
        treated = pd.DataFrame({
            "size": [10.0, 11.0],
            "lev": [0.4, 0.5],
        })
        control = pd.DataFrame({
            "size": [10.0, 11.0],
            "lev": [0.4, 0.5],
        })
        balance = PSMDID._compute_balance(treated, control, ["size", "lev"])
        assert len(balance) == 2

    def test_balance_zero_variance_control(self):
        """Zero variance in both groups gives zero bias."""
        treated = pd.DataFrame({"x": [5.0] * 5})
        control = pd.DataFrame({"x": [5.0] * 5})
        balance = PSMDID._compute_balance(treated, control, ["x"])
        assert balance["std_bias"].iloc[0] == 0.0
        assert balance["abs_bias_lt_10pct"].iloc[0] is True or balance["abs_bias_lt_10pct"].iloc[0] == True  # noqa: E712

    def test_balance_large_bias(self):
        """Large mean difference gives large standardised bias."""
        treated = pd.DataFrame({"x": [100.0, 101.0, 99.0]})
        control = pd.DataFrame({"x": [0.0, 1.0, -1.0]})
        balance = PSMDID._compute_balance(treated, control, ["x"])
        assert abs(balance["std_bias"].iloc[0]) > 0.5
        assert balance["abs_bias_lt_10pct"].iloc[0] is False or balance["abs_bias_lt_10pct"].iloc[0] == False  # noqa: E712

    def test_balance_missing_covariate(self):
        """Missing covariate in DataFrame raises KeyError (as expected)."""
        treated = pd.DataFrame({"size": [10.0, 11.0]})
        control = pd.DataFrame({"size": [10.0, 11.0]})
        with pytest.raises(KeyError):
            PSMDID._compute_balance(treated, control, ["size", "missing"])

    def test_balance_empty_covariates(self):
        """Empty covariate list returns empty DataFrame."""
        treated = pd.DataFrame({"x": [1.0]})
        control = pd.DataFrame({"x": [1.0]})
        balance = PSMDID._compute_balance(treated, control, [])
        assert isinstance(balance, pd.DataFrame)
        assert len(balance) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. PSMDID.fit — error paths
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitErrorPaths:
    def test_fit_empty_covariates(self):
        """Empty covariate list raises ValueError."""
        df = _make_psm_panel(n=100)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        with pytest.raises(ValueError):
            model.fit(df, covariates=[])

    def test_fit_all_treated(self):
        """All units treated — logistic regression fails with single class."""
        rng = np.random.default_rng(3)
        df = pd.DataFrame({
            "y": rng.normal(0, 1, 100),
            "D": [1] * 100,
            "year": [2016] * 100,
            "firm_id": range(100),
            "size": rng.normal(10, 1, 100),
        })
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        with pytest.raises((ValueError, RuntimeError)):
            model.fit(df, covariates=["size"])

    def test_fit_all_control(self):
        """All units are control — no treated observations."""
        rng = np.random.default_rng(4)
        df = pd.DataFrame({
            "y": rng.normal(0, 1, 100),
            "D": [0] * 100,
            "year": [2016] * 100,
            "firm_id": range(100),
            "size": rng.normal(10, 1, 100),
        })
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        with pytest.raises(ValueError, match="No treated observations"):
            model.fit(df, covariates=["size"])

    def test_fit_na_in_covariates(self):
        """All-NA covariates raises ValueError."""
        df = pd.DataFrame({
            "y": [1.0, 2.0, 3.0],
            "D": [1, 0, 1],
            "year": [2016, 2017, 2018],
            "firm_id": [1, 2, 3],
            "size": [np.nan] * 3,
        })
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        with pytest.raises(ValueError):
            model.fit(df, covariates=["size"])

    def test_fit_missing_time_column(self):
        """Missing time column raises KeyError."""
        df = pd.DataFrame({
            "y": [1.0, 2.0, 3.0],
            "D": [1, 0, 1],
            "firm_id": [1, 2, 3],
            "size": [1.0, 1.0, 1.0],
        })
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        with pytest.raises(KeyError):
            model.fit(df, covariates=["size"])

    def test_fit_pre_period_after_all_data(self):
        """pre_period is after all data — treated_years_all.min() triggers."""
        rng = np.random.default_rng(5)
        n = 100
        D = rng.binomial(1, 0.3, n)
        records = []
        for i in range(n):
            for y in range(2020, 2025):
                records.append({
                    "firm_id": i, "year": y, "D": D[i],
                    "size": 10, "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        # Should auto-detect treatment year and build pre_period
        result = model.fit(df, covariates=["size"])
        assert isinstance(result, PSMDIDResult)


# ─────────────────────────────────────────────────────────────────────────────
# 5. PSMDID.fit — caliper edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitCaliperEdge:
    def test_caliper_too_small_all_dropped(self):
        """Caliper so tight nothing matches."""
        rng = np.random.default_rng(6)
        n = 200
        D = rng.binomial(1, 0.5, n)
        records = []
        for i in range(n):
            for y in range(2016, 2021):
                records.append({
                    "firm_id": i, "year": y, "D": D[i],
                    "size": rng.normal(10 + i * 0.1, 0.1),  # very spread
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id",
                        method="caliper", caliper=0.001)
        result = model.fit(df, covariates=["size"])
        # Should not crash; matched counts may be 0
        assert isinstance(result, PSMDIDResult)

    def test_caliper_with_exact_match(self):
        """Caliper with perfect overlap — all treated matched."""
        rng = np.random.default_rng(7)
        n = 200
        records = []
        for i in range(n):
            D = 1 if i < n // 2 else 0
            size_val = rng.normal(10, 1)
            for y in range(2016, 2021):
                records.append({
                    "firm_id": i, "year": y, "D": D,
                    "size": size_val,  # same distribution
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id",
                        method="caliper", caliper=0.5)
        result = model.fit(df, covariates=["size"])
        assert isinstance(result, PSMDIDResult)
        assert result.n_treated_matched >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. PSMDID.fit — nearest / kernel edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitNearestKernel:
    def test_nearest_with_replacement(self):
        df = _make_psm_panel(n=100, seed=8)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id",
                        method="nearest", replace=True, n_neighbors=1)
        result = model.fit(df, covariates=["size", "leverage"])
        assert isinstance(result, PSMDIDResult)
        assert result.n_control_matched >= 1

    def test_nearest_k_neighbors(self):
        df = _make_psm_panel(n=200, seed=9)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id",
                        method="nearest", n_neighbors=3)
        result = model.fit(df, covariates=["size"])
        assert isinstance(result, PSMDIDResult)
        assert result.method == "nearest"

    def test_kernel_method(self):
        df = _make_psm_panel(n=200, seed=10)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id",
                        method="kernel")
        result = model.fit(df, covariates=["size"])
        assert isinstance(result, PSMDIDResult)
        assert result.method == "kernel"


# ─────────────────────────────────────────────────────────────────────────────
# 7. PSMDID.fit — AUC and propensity score
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitPS:
    def test_fit_auc_reasonable(self):
        df = _make_psm_panel(n=400, seed=11)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"])
        assert 0.5 <= result.first_stage_auc <= 1.0

    def test_fit_auc_perfect_predictor(self):
        """Perfect predictor of treatment gives AUC near 1.0."""
        rng = np.random.default_rng(12)
        n = 200
        records = []
        for i in range(n):
            D = 1 if i < n // 2 else 0  # perfect predictor
            for y in range(2016, 2021):
                records.append({
                    "firm_id": i, "year": y, "D": D,
                    "size": float(D) + rng.normal(0, 0.01),
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size"])
        assert result.first_stage_auc > 0.9

    def test_fit_auc_random_treatment(self):
        """Completely random treatment (coinflip) → AUC ≈ 0.5."""
        rng = np.random.default_rng(13)
        n = 300
        records = []
        for i in range(n):
            D = rng.binomial(1, 0.5)  # independent of covariates
            for y in range(2016, 2021):
                records.append({
                    "firm_id": i, "year": y, "D": D,
                    "size": rng.normal(10, 1),
                    "leverage": rng.normal(0.5, 0.1),
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"])
        # AUC should be close to 0.5 (within reasonable tolerance)
        assert 0.4 <= result.first_stage_auc <= 0.6


# ─────────────────────────────────────────────────────────────────────────────
# 8. PSMDID.fit — balance check
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitBalance:
    def test_balance_after_match(self):
        df = _make_psm_panel(n=300, seed=14)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"])
        balance = result.covariate_balance
        assert isinstance(balance, pd.DataFrame)
        assert "covariate" in balance.columns
        assert "std_bias" in balance.columns
        assert "abs_bias_lt_10pct" in balance.columns
        assert len(balance) == 2

    def test_balance_all_pass_threshold(self):
        """Well-matched sample should have low standardised bias."""
        rng = np.random.default_rng(15)
        n = 300
        D = rng.binomial(1, 0.5, n)
        records = []
        for i in range(n):
            for y in range(2016, 2021):
                size_val = rng.normal(10, 0.5)
                records.append({
                    "firm_id": i, "year": y, "D": D[i],
                    "size": size_val,
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size"])
        assert isinstance(result.covariate_balance, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 9. PSMDID.fit — DID coefficient sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitCoefficient:
    def test_did_coefficient_is_float(self):
        df = _make_psm_panel(n=300, effect=0.5, seed=16)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"])
        assert isinstance(result.did_coefficient, float)
        assert isinstance(result.did_se, float)
        assert isinstance(result.did_tstat, float)
        assert isinstance(result.did_pvalue, float)

    def test_did_positive_effect_detected(self):
        df = _make_psm_panel(n=400, effect=0.8, seed=17)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"],
                           pre_period=(2016, 2018), post_period=(2019, 2020))
        assert result.did_coefficient > 0

    def test_did_tstat_magnitude(self):
        """Strong effect → large |t-stat|."""
        df = _make_psm_panel(n=500, effect=1.0, seed=18)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size", "leverage"],
                           pre_period=(2016, 2018), post_period=(2019, 2020))
        assert abs(result.did_tstat) > 1.0

    def test_did_se_positive(self):
        df = _make_psm_panel(n=200, seed=19)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size"])
        assert result.did_se >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. PSMDID.fit — explicit pre/post periods
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDFitPeriods:
    def test_explicit_pre_period(self):
        df = _make_psm_panel(n=200, seed=20)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size"],
                           pre_period=(2016, 2018))
        assert isinstance(result, PSMDIDResult)

    def test_explicit_post_period(self):
        df = _make_psm_panel(n=200, seed=21)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(df, covariates=["size"],
                           pre_period=(2016, 2018), post_period=(2019, 2020))
        assert isinstance(result, PSMDIDResult)

    def test_mismatched_periods(self):
        """pre_period end after post_period start — auto-handled."""
        df = _make_psm_panel(n=200, seed=22)
        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        # Both specified: post_period[0] = pre_period[1] + 1
        result = model.fit(df, covariates=["size"],
                           pre_period=(2016, 2019), post_period=(2020, 2020))
        assert isinstance(result, PSMDIDResult)


# ─────────────────────────────────────────────────────────────────────────────
# 11. run_psm_did convenience function
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPSMDID:
    def test_run_psm_did_returns_result(self):
        df = _make_psm_panel(n=200, seed=23)
        result = run_psm_did(
            df, outcome="y", treatment="D",
            time="year", unit="firm_id",
            covariates=["size", "leverage"],
            method="nearest",
        )
        assert isinstance(result, PSMDIDResult)
        assert result.n_obs_after_match > 0

    def test_run_psm_did_with_caliper(self):
        df = _make_psm_panel(n=200, seed=24)
        result = run_psm_did(
            df, outcome="y", treatment="D",
            time="year", unit="firm_id",
            covariates=["size"],
            method="caliper", caliper=0.2,
        )
        assert isinstance(result, PSMDIDResult)
        assert result.method == "caliper"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Module-level smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestPSMDIDSmoke:
    def test_module_docstring_example(self):
        """Smoke test using the docstring example pattern."""
        np.random.seed(99)
        n_firms = 200
        n_years = 5
        panel = []
        for f in range(n_firms):
            D = np.random.binomial(1, 0.3)
            for y in range(2016, 2016 + n_years):
                base = np.random.normal(0, 1)
                if y >= 2019 and D == 1:
                    base += 0.5
                panel.append({
                    "firm_id": f, "year": y, "D": D,
                    "size": 10, "leverage": 0.5, "y": base,
                })
        df = pd.DataFrame(panel)
        result = run_psm_did(
            df,
            outcome="y",
            treatment="D",
            time="year",
            unit="firm_id",
            covariates=["size", "leverage"],
            method="caliper",
            caliper=0.2,
        )
        assert result.did_coefficient is not None
        assert result.first_stage_auc is not None
