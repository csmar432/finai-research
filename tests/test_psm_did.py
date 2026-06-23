"""Tests for scripts/research_framework/psm_did.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.psm_did import (
    PSMDID, PSMDIDResult, run_psm_did
)


class TestPSMDIDResult:
    def test_result_summary(self):
        balance = pd.DataFrame({
            "covariate": ["size", "leverage"],
            "treated_mean": [10.5, 0.45],
            "control_mean": [10.2, 0.44],
            "std_bias": [0.05, 0.02],
            "abs_bias_lt_10pct": [True, True],
        })

        result = PSMDIDResult(
            did_coefficient=0.52,
            did_se=0.18,
            did_tstat=2.89,
            did_pvalue=0.004,
            n_treated_matched=150,
            n_control_matched=150,
            n_treated_unmatched=20,
            n_control_unmatched=30,
            covariate_balance=balance,
            first_stage_auc=0.78,
            n_obs_after_match=300,
            method="caliper",
            caliper=0.2,
            model=object(),
        )

        s = result.summary()
        assert "PSM-DID Result" in s
        assert "caliper=0.2" in s
        assert "ATT = 0.520000" in s
        assert "SE  = 0.180000" in s
        assert "AUC" in s


class TestPSMDIDBalance:
    def test_compute_balance(self):
        treated = pd.DataFrame({
            "size": [10.0, 11.0, 10.5],
            "lev": [0.4, 0.5, 0.45],
        })
        control = pd.DataFrame({
            "size": [10.1, 10.9, 10.4],
            "lev": [0.41, 0.49, 0.44],
        })

        balance = PSMDID._compute_balance(treated, control, ["size", "lev"])
        assert isinstance(balance, pd.DataFrame)
        assert len(balance) == 2
        assert "covariate" in balance.columns
        assert "std_bias" in balance.columns
        assert "abs_bias_lt_10pct" in balance.columns
        assert all(balance["abs_bias_lt_10pct"])


class TestPSMDIDEdgeCases:
    def test_fit_empty_dataframe_keyerror(self):
        model = PSMDID(outcome="y", treatment="D", time="year", unit="id")
        df = pd.DataFrame({"y": [np.nan]})
        # No columns for covariates, treatment, time, unit → KeyError
        with pytest.raises(KeyError):
            model.fit(df, covariates=["x"])

    def test_fit_no_treated_raises(self):
        df = pd.DataFrame({
            "y": [1.0, 2.0, 3.0],
            "D": [0, 0, 0],
            "year": [2018, 2019, 2020],
            "id": [1, 2, 3],
            "x": [1.0, 2.0, 3.0],
        })
        model = PSMDID(outcome="y", treatment="D", time="year", unit="id")
        with pytest.raises(ValueError, match="No treated observations"):
            model.fit(df, covariates=["x"])

    def test_fit_no_na_rows(self):
        rng = np.random.default_rng(42)
        n = 300
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "D": rng.integers(0, 2, n),
            "year": [2016 + i % 6 for i in range(n)],
            "id": range(n),
            "x1": rng.normal(10, 2, n),
            "x2": rng.normal(0.5, 0.2, n),
        })

        model = PSMDID(outcome="y", treatment="D", time="year", unit="id")
        result = model.fit(df, covariates=["x1", "x2"])
        assert isinstance(result, PSMDIDResult)
        assert result.n_obs_after_match >= 0


class TestPSMDIDWithExogenousCovariates:
    def test_fit_with_covariates(self):
        rng = np.random.default_rng(42)
        n = 500
        D = rng.binomial(1, 0.3, n)
        treatment_year = 2019

        records = []
        for i in range(n):
            for y in range(2016, 2021):
                base = rng.normal(0, 1)
                if y >= treatment_year and D[i] == 1:
                    base += 0.5
                records.append({
                    "firm_id": i,
                    "year": y,
                    "D": D[i],
                    "size": 10 + rng.normal(0, 0.5),
                    "leverage": 0.4 + rng.normal(0, 0.05),
                    "y": base,
                })

        df = pd.DataFrame(records)

        model = PSMDID(outcome="y", treatment="D", time="year", unit="firm_id")
        result = model.fit(
            df, covariates=["size", "leverage"],
            pre_period=(2016, 2018), post_period=(2019, 2020),
        )

        assert isinstance(result, PSMDIDResult)
        assert result.n_obs_after_match > 0
        assert 0 < result.first_stage_auc <= 1
        assert result.did_coefficient > 0
        assert abs(result.did_tstat) > 1.0


class TestPSMCaliperMethod:
    def test_caliper_method(self):
        rng = np.random.default_rng(42)
        n = 300
        D = rng.binomial(1, 0.3, n)

        records = []
        for i in range(n):
            for y in range(2016, 2021):
                records.append({
                    "firm_id": i,
                    "year": y,
                    "D": D[i],
                    "x1": rng.normal(10, 2),
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)

        model = PSMDID(
            outcome="y", treatment="D", time="year", unit="firm_id",
            method="caliper", caliper=0.25,
        )
        result = model.fit(df, covariates=["x1"])

        assert isinstance(result, PSMDIDResult)
        assert result.method == "caliper"
        assert result.caliper == 0.25


class TestPSMDIDNearestNeighbour:
    def test_nearest_neighbour(self):
        rng = np.random.default_rng(42)
        n = 400
        D = rng.binomial(1, 0.4, n)

        records = []
        for i in range(n):
            for y in range(2015, 2020):
                records.append({
                    "firm_id": i,
                    "year": y,
                    "D": D[i],
                    "size": rng.normal(10, 2),
                    "y": rng.normal(0, 1),
                })
        df = pd.DataFrame(records)

        model = PSMDID(
            outcome="y", treatment="D", time="year", unit="firm_id",
            method="nearest", n_neighbors=2,
        )
        result = model.fit(df, covariates=["size"])

        assert isinstance(result, PSMDIDResult)
        assert result.method == "nearest"


class TestPSMDIDKernelMethod:
    def test_kernel_method(self):
        rng = np.random.default_rng(42)
        n = 400
        df = pd.DataFrame({
            "y": rng.normal(0, 1, n),
            "D": rng.integers(0, 2, n),
            "year": rng.integers(2016, 2022, n),
            "id": range(n),
            "x1": rng.normal(10, 2, n),
            "x2": rng.normal(0.5, 0.2, n),
        })

        model = PSMDID(
            outcome="y", treatment="D", time="year", unit="id",
            method="kernel",
        )
        result = model.fit(df, covariates=["x1", "x2"])
        assert isinstance(result, PSMDIDResult)
        assert result.method == "kernel"


class TestRunPSMDID:
    def test_run_psm_did_convenience(self):
        rng = np.random.default_rng(42)
        n = 400
        D = rng.binomial(1, 0.35, n)

        records = []
        for i in range(n):
            for y in range(2016, 2021):
                base = rng.normal(0, 1)
                if y >= 2019 and D[i] == 1:
                    base += 0.4
                records.append({
                    "firm_id": i, "year": y, "D": D[i],
                    "x1": rng.normal(10, 2),
                    "x2": rng.normal(0.5, 0.1),
                    "y": base,
                })
        df = pd.DataFrame(records)

        result = run_psm_did(
            df, outcome="y", treatment="D",
            time="year", unit="firm_id",
            covariates=["x1", "x2"],
            method="nearest",
        )

        assert isinstance(result, PSMDIDResult)
        assert result.n_obs_after_match > 0
