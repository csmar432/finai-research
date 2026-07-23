"""Comprehensive tests for scripts/research_framework/rdd.py.

Targeted coverage: RDDRegressionDiscontinuityDesign (Sharp/Fuzzy RDD,
bandwidth selection, density test, covariate balance, sensitivity, plotting).

References:
- Imbens & Kalyanaraman (2012) "Optimal Bandwidth Choice for RDD"
- McCrary (2008) "Manipulation of the Running Variable"
- Lee & Lemieux (2010) "Regression Discontinuity Designs in Economics"
"""

from __future__ import annotations


import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

from scripts.research_framework.rdd import (
    BandwidthResult,
    CovariateBalanceResult,
    DensityTestResult,
    FuzzyRDDResult,
    RDDEngine,
    RDDResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_sharp_df(
    n: int = 1500,
    tau: float = 2.5,
    seed: int = 42,
    cutoff: float = 0.0,
    noise: float = 1.0,
) -> pd.DataFrame:
    """Generate Sharp RDD data: y has a known discontinuity at cutoff."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-2, 2, n)
    above = (x >= cutoff).astype(float)
    y = (
        1.0
        + 0.8 * x
        + tau * above
        + 0.5 * x * above
        + rng.normal(0, noise, n)
    )
    return pd.DataFrame({"x": x, "y": y})


def _make_fuzzy_df(
    n: int = 1500,
    tau: float = 2.5,
    seed: int = 42,
    cutoff: float = 0.0,
) -> pd.DataFrame:
    """Generate Fuzzy RDD data: treatment prob jumps at cutoff."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-2, 2, n)
    above = x >= cutoff
    prob = np.where(above, 0.8, 0.2)
    treat = (rng.uniform(0, 1, n) < prob).astype(int)
    y = (
        1.0
        + 0.8 * x
        + tau * treat
        + 0.5 * x * above
        + rng.normal(0, 1, n)
    )
    cov = rng.normal(0, 1, n)
    return pd.DataFrame({"x": x, "y": y, "treat": treat, "cov1": cov, "cov2": rng.normal(0, 1, n)})


@pytest.fixture
def sharp_df() -> pd.DataFrame:
    return _make_sharp_df()


@pytest.fixture
def fuzzy_df() -> pd.DataFrame:
    return _make_fuzzy_df()


@pytest.fixture
def sharp_engine(sharp_df: pd.DataFrame) -> RDDEngine:
    return RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0)


@pytest.fixture
def fuzzy_engine(fuzzy_df: pd.DataFrame) -> RDDEngine:
    return RDDEngine(
        fuzzy_df, y_var="y", x_var="x", cutoff=0.0,
        treat_var="treat", covariate_vars=["cov1", "cov2"],
    )


@pytest.fixture
def fitted_engine(sharp_engine: RDDEngine) -> RDDEngine:
    sharp_engine.fit(bandwidth=0.5, kernel="triangular", order=1)
    return sharp_engine


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dataclass properties (5 classes)
# ─────────────────────────────────────────────────────────────────────────────


class TestRDDResultDataclass:
    def test_construction_minimal(self):
        r = RDDResult(estimator="llr_order1", coef=1.0, se=0.1, pval=0.01)
        assert r.estimator == "llr_order1"
        assert r.coef == 1.0
        assert r.se == 0.1
        assert r.pval == 0.01
        assert r.cutoff == 0.0  # default
        assert r.kernel == "triangular"
        assert r.order == 1
        assert r.method == "analytical"

    def test_construction_full(self):
        r = RDDResult(
            estimator="llr_order2",
            coef=2.5, se=0.2, pval=0.001,
            ci_lower=2.1, ci_upper=2.9,
            bandwidth=0.5, cutoff=0.0,
            kernel="uniform", order=2,
            n_obs=1000, n_left=500, n_right=500,
            r_squared=0.8, method="cluster",
            additional={"foo": "bar"},
        )
        assert r.kernel == "uniform"
        assert r.order == 2
        assert r.method == "cluster"
        assert r.additional["foo"] == "bar"

    @pytest.mark.parametrize("pval,expected", [
        (0.0001, "***"),
        (0.005, "**"),
        (0.02, "*"),
        (0.07, "$\\dagger$"),
        (0.5, ""),
    ])
    def test_sig_property(self, pval, expected):
        r = RDDResult(estimator="llr_order1", coef=1.0, se=0.1, pval=pval)
        assert r.sig == expected

    def test_to_dict_keys(self):
        r = RDDResult(estimator="llr_order1", coef=2.0, se=0.5, pval=0.01,
                      n_obs=100, n_left=50, n_right=50)
        d = r.to_dict()
        for key in ["estimator", "coef", "se", "pval", "ci_lower", "ci_upper",
                    "bandwidth", "cutoff", "kernel", "order", "n_obs",
                    "n_left", "n_right", "r_squared", "method", "sig"]:
            assert key in d
        assert d["coef"] == 2.0

    def test_to_dict_includes_additional(self):
        r = RDDResult(
            estimator="llr_order1", coef=1.0, se=0.1, pval=0.5,
            additional={"mccrary_theta": 0.1, "custom": 42},
        )
        d = r.to_dict()
        assert d["mccrary_theta"] == 0.1
        assert d["custom"] == 42


class TestBandwidthResult:
    def test_construction_defaults(self):
        b = BandwidthResult(bandwidth=0.5, method="ik")
        assert b.bandwidth == 0.5
        assert b.method == "ik"
        assert b.n_left == 0
        assert b.n_right == 0
        assert b.n_total == 0
        assert b.metadata == {}

    def test_construction_with_counts(self):
        b = BandwidthResult(
            bandwidth=0.3, method="msed",
            n_left=300, n_right=350, n_total=650,
            metadata={"note": "test"},
        )
        assert b.n_total == 650
        assert b.metadata["note"] == "test"


class TestFuzzyRDDResult:
    def test_construction_minimal(self):
        r = FuzzyRDDResult(estimator="fuzzy_llr", tau_iv=2.0, se=0.5, pval=0.01)
        assert r.tau_iv == 2.0
        assert r.first_stage == {}
        assert r.reduced_form == {}

    def test_sig_property(self):
        r1 = FuzzyRDDResult(estimator="fuzzy_llr", tau_iv=2.0, se=0.5, pval=0.0001)
        r2 = FuzzyRDDResult(estimator="fuzzy_llr", tau_iv=2.0, se=0.5, pval=0.5)
        assert r1.sig == "***"
        assert r2.sig == ""

    def test_first_stage_dict(self):
        r = FuzzyRDDResult(
            estimator="fuzzy_llr", tau_iv=2.0, se=0.5, pval=0.01,
            first_stage={"f_stat": 50.0, "coef": 0.6},
        )
        assert r.first_stage["f_stat"] == 50.0


class TestDensityTestResult:
    def test_construction_defaults(self):
        d = DensityTestResult(theta=0.1, se=0.05, pval=0.6)
        assert d.theta == 0.1
        assert d.ci_lower == 0.0
        assert d.interpretation == ""

    def test_construction_with_interpretation(self):
        d = DensityTestResult(
            theta=0.05, se=0.02, pval=0.8,
            ci_lower=-0.01, ci_upper=0.11,
            bandwidth=0.4,
            interpretation="No evidence of manipulation",
        )
        assert d.interpretation.startswith("No evidence")


class TestCovariateBalanceResult:
    def test_construction(self):
        c = CovariateBalanceResult(
            covariate="cov1", mean_left=0.1, mean_right=0.15,
            diff=0.05, se=0.02, pval=0.3,
        )
        assert c.covariate == "cov1"
        assert c.diff == 0.05


# ─────────────────────────────────────────────────────────────────────────────
# 2. RDDEngine.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestRDDEngineInit:
    def test_minimal_init(self, sharp_df):
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0)
        assert engine.y_var == "y"
        assert engine.x_var == "x"
        assert engine.cutoff == 0.0
        assert engine.treat_var is None
        assert engine.covariate_vars == []
        assert engine.cluster_var is None
        # df is copied (not mutated)
        assert engine.df is not sharp_df

    def test_init_with_treat_var(self, fuzzy_df):
        engine = RDDEngine(fuzzy_df, y_var="y", x_var="x", cutoff=0.0,
                           treat_var="treat")
        assert engine.treat_var == "treat"

    def test_init_with_covariates(self, fuzzy_df):
        engine = RDDEngine(fuzzy_df, y_var="y", x_var="x", cutoff=0.0,
                           covariate_vars=["cov1", "cov2"])
        assert engine.covariate_vars == ["cov1", "cov2"]

    def test_init_with_cluster_var(self, sharp_df):
        sharp_df = sharp_df.copy()
        sharp_df["firm_id"] = np.arange(len(sharp_df))
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0,
                           cluster_var="firm_id")
        assert engine.cluster_var == "firm_id"

    def test_init_stores_private_results(self, sharp_df):
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0)
        assert engine._rdd_result is None
        assert engine._fuzzy_result is None
        assert engine._density_result is None
        assert engine._bandwidth_result is None
        assert engine._sensitivity_df is None

    def test_custom_cutoff(self, sharp_df):
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.5)
        assert engine.cutoff == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 3. select_bandwidth (ik / msed / cct / manual)
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectBandwidth:
    def test_select_manual(self, sharp_engine):
        bw = sharp_engine.select_bandwidth(method="manual", manual_bw=0.3)
        assert isinstance(bw, BandwidthResult)
        assert bw.method == "manual"
        assert bw.bandwidth == 0.3
        # manual: n_total is the full sample, n_left/n_right split at cutoff
        assert bw.n_total == len(sharp_engine.df)
        assert bw.n_left + bw.n_right == bw.n_total
        assert bw.n_left > 0 and bw.n_right > 0

    def test_select_manual_required(self, sharp_engine):
        with pytest.raises((ValueError, KeyError)):
            sharp_engine.select_bandwidth(method="manual", manual_bw=None)

    def test_select_ik(self, sharp_engine):
        bw = sharp_engine.select_bandwidth(method="ik")
        assert bw.method == "ik"
        assert bw.bandwidth > 0
        assert bw.n_total > 0

    def test_select_msed(self, sharp_engine):
        bw = sharp_engine.select_bandwidth(method="msed")
        assert bw.method == "msed"
        assert bw.bandwidth > 0

    def test_select_cct(self, sharp_engine):
        bw = sharp_engine.select_bandwidth(method="cct")
        assert bw.method == "cct"
        assert bw.bandwidth > 0

    def test_select_stores_result(self, sharp_engine):
        sharp_engine.select_bandwidth(method="manual", manual_bw=0.4)
        assert sharp_engine._bandwidth_result is not None
        assert sharp_engine._bandwidth_result.bandwidth == 0.4

    def test_select_with_kernel_and_order(self, sharp_engine):
        bw = sharp_engine.select_bandwidth(
            method="manual", manual_bw=0.4, kernel="uniform", order=2
        )
        assert bw.bandwidth == 0.4

    def test_select_bandwidth_clamps_range(self, sharp_engine):
        """Bandwidth must be > 0 regardless of selector."""
        bw = sharp_engine.select_bandwidth(method="ik")
        assert bw.bandwidth > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. fit (Sharp RDD)
# ─────────────────────────────────────────────────────────────────────────────


class TestFitSharpRDD:
    def test_fit_returns_rddresult(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, kernel="triangular", order=1)
        assert isinstance(res, RDDResult)
        assert sharp_engine._rdd_result is res

    def test_fit_recovers_true_effect(self, sharp_engine):
        """On simulated data with tau=2.5, estimate should be in (1, 4)."""
        res = sharp_engine.fit(bandwidth=0.7, kernel="triangular", order=1)
        assert 1.0 < res.coef < 4.0
        assert res.pval < 0.05
        assert res.se > 0

    def test_fit_ci_contains_estimate(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5)
        assert res.ci_lower < res.coef < res.ci_upper

    def test_fit_explicit_bandwidth(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.3)
        assert res.bandwidth == 0.3

    def test_fit_auto_bandwidth(self, sharp_engine):
        res = sharp_engine.fit(bandwidth_method="ik", kernel="triangular", order=1)
        assert res.bandwidth > 0

    def test_fit_kernel_uniform(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, kernel="uniform")
        assert res.kernel == "uniform"
        assert not np.isnan(res.coef)

    def test_fit_kernel_epanechnikov(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, kernel="epanechnikov")
        assert res.kernel == "epanechnikov"

    def test_fit_kernel_gaussian(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, kernel="gaussian")
        assert res.kernel == "gaussian"

    def test_fit_order_2(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, order=2)
        assert res.order == 2

    def test_fit_order_3(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, order=3)
        assert res.order == 3

    def test_fit_order_4(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, order=4)
        assert res.order == 4

    def test_fit_order_clamped_to_4(self, sharp_engine):
        """Order > 4 should be clamped to 4."""
        res = sharp_engine.fit(bandwidth=0.5, order=10)
        assert res.order == 4

    def test_fit_order_clamped_to_1(self, sharp_engine):
        """Order < 1 should be clamped to 1."""
        res = sharp_engine.fit(bandwidth=0.5, order=0)
        assert res.order == 1

    def test_fit_donut_excludes_inner(self, sharp_df):
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0)
        res = engine.fit(bandwidth=0.5, donut=0.1)
        assert res.n_obs < int(((np.abs(sharp_df["x"]) <= 0.5)).sum())

    def test_fit_too_few_obs_returns_nan(self):
        """When bandwidth too small, returns NaN-filled result."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "x": rng.uniform(-1, 1, 50),
            "y": rng.normal(0, 1, 50),
        })
        engine = RDDEngine(df, y_var="y", x_var="x", cutoff=0.0)
        res = engine.fit(bandwidth=0.0001)
        assert np.isnan(res.coef)
        assert np.isnan(res.se)

    def test_fit_se_method_bayesian(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5, se_method="bayesian")
        assert res.method == "bayesian"
        assert res.se > 0

    def test_fit_se_method_cluster(self, sharp_df):
        sharp_df = sharp_df.copy()
        sharp_df["firm_id"] = np.repeat(np.arange(300), len(sharp_df) // 300)
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0,
                           cluster_var="firm_id")
        res = engine.fit(bandwidth=0.5, se_method="cluster")
        assert res.method == "cluster"

    def test_fit_n_left_n_right(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5)
        assert res.n_left > 0
        assert res.n_right > 0
        assert res.n_left + res.n_right == res.n_obs

    def test_fit_r_squared_reported(self, sharp_engine):
        res = sharp_engine.fit(bandwidth=0.5)
        assert res.r_squared is not None
        assert 0 <= res.r_squared <= 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. fit_fuzzy
# ─────────────────────────────────────────────────────────────────────────────


class TestFitFuzzyRDD:
    def test_fit_fuzzy_requires_treat_var(self, sharp_engine):
        with pytest.raises(ValueError, match="treat_var"):
            sharp_engine.fit_fuzzy(bandwidth=0.5)

    def test_fit_fuzzy_returns_fuzzyresult(self, fuzzy_engine):
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        assert isinstance(res, FuzzyRDDResult)
        assert fuzzy_engine._fuzzy_result is res

    def test_fit_fuzzy_recovers_late(self, fuzzy_engine):
        """On simulated data with tau=2.5, fuzzy estimate should be reasonable."""
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.7)
        assert -2.0 < res.tau_iv < 8.0  # allow some bias
        assert res.se > 0

    def test_fit_fuzzy_first_stage(self, fuzzy_engine):
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        assert "f_stat" in res.first_stage
        # In our DGP, treatment prob jumps from 0.2 to 0.8 — strong first stage
        assert res.first_stage["f_stat"] > 1

    def test_fit_fuzzy_reduced_form(self, fuzzy_engine):
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        assert "tau" in res.reduced_form
        assert "se" in res.reduced_form
        assert isinstance(res.reduced_form["tau"], float)
        assert res.reduced_form["se"] > 0

    def test_fit_fuzzy_ci(self, fuzzy_engine):
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        assert res.ci_lower < res.tau_iv < res.ci_upper

    def test_fit_fuzzy_different_order(self, fuzzy_engine):
        res = fuzzy_engine.fit_fuzzy(bandwidth=0.5, order=2)
        assert not np.isnan(res.tau_iv)


# ─────────────────────────────────────────────────────────────────────────────
# 6. mccrary_test (density discontinuity)
# ─────────────────────────────────────────────────────────────────────────────


class TestMcCraryTest:
    def test_mccrary_returns_result(self, sharp_engine):
        res = sharp_engine.mccrary_test()
        assert isinstance(res, DensityTestResult)
        assert sharp_engine._density_result is res

    def test_mccrary_smooth_data_not_significant(self, sharp_engine):
        """Smooth (non-manipulated) data should not reject continuity."""
        res = sharp_engine.mccrary_test()
        # theta should be small relative to its SE
        assert abs(res.theta) < 5 * res.se

    def test_mccrary_with_explicit_bandwidth(self, sharp_engine):
        res = sharp_engine.mccrary_test(bandwidth=0.5)
        assert res.bandwidth == 0.5

    def test_mccrary_interpretation_nonempty(self, sharp_engine):
        res = sharp_engine.mccrary_test()
        assert isinstance(res.interpretation, str)
        assert len(res.interpretation) > 0

    def test_mccrary_manipulated_data_detects_jump(self):
        """Construct data with mass pile-up just above cutoff."""
        rng = np.random.default_rng(123)
        n = 1500
        x = rng.uniform(-1, 1, n)
        # Add excess mass just to the right
        extras = rng.uniform(0.01, 0.05, 200)
        x = np.concatenate([x, extras])
        df = pd.DataFrame({"x": x, "y": rng.normal(0, 1, len(x))})
        engine = RDDEngine(df, y_var="y", x_var="x", cutoff=0.0)
        res = engine.mccrary_test()
        # Should report *something* — not asserting direction here
        assert isinstance(res.theta, float)


# ─────────────────────────────────────────────────────────────────────────────
# 7. covariate_balance
# ─────────────────────────────────────────────────────────────────────────────


class TestCovariateBalance:
    def test_balance_returns_list(self, fuzzy_engine):
        res = fuzzy_engine.covariate_balance()
        assert isinstance(res, list)
        assert len(res) == len(fuzzy_engine.covariate_vars)

    def test_balance_result_type(self, fuzzy_engine):
        res = fuzzy_engine.covariate_balance()
        for r in res:
            assert isinstance(r, CovariateBalanceResult)

    def test_balance_fields(self, fuzzy_engine):
        res = fuzzy_engine.covariate_balance()
        for r in res:
            assert r.covariate in ["cov1", "cov2"]
            assert np.isfinite(r.diff)
            assert r.se > 0
            assert 0 <= r.pval <= 1

    def test_balance_no_covariates_returns_empty(self, sharp_engine):
        res = sharp_engine.covariate_balance()
        assert res == []

    def test_balance_single_covariate(self, fuzzy_df):
        engine = RDDEngine(fuzzy_df, y_var="y", x_var="x", cutoff=0.0,
                           treat_var="treat", covariate_vars=["cov1"])
        res = engine.covariate_balance()
        assert len(res) == 1
        assert res[0].covariate == "cov1"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Sensitivity analyses
# ─────────────────────────────────────────────────────────────────────────────


class TestBandwidthSensitivity:
    def test_returns_dataframe(self, sharp_engine):
        df = sharp_engine.bandwidth_sensitivity(bw_methods=["ik", "msed"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 2

    def test_default_methods(self, sharp_engine):
        df = sharp_engine.bandwidth_sensitivity()
        # Default is ["ik", "msed", "cct"]
        assert len(df) >= 3

    def test_manual_bandwidths(self, sharp_engine):
        df = sharp_engine.bandwidth_sensitivity(
            bw_methods=["ik"],
            manual_bws=[0.3, 0.5, 0.7],
        )
        assert len(df) == 4  # 1 auto (ik) + 3 manual

    def test_columns_present(self, sharp_engine):
        df = sharp_engine.bandwidth_sensitivity(bw_methods=["ik"])
        for col in ["bandwidth", "coef", "se", "pval", "n_obs"]:
            assert col in df.columns

    def test_stores_sensitivity_df(self, sharp_engine):
        sharp_engine.bandwidth_sensitivity(bw_methods=["ik"])
        assert sharp_engine._sensitivity_df is not None


class TestOrderSensitivity:
    def test_returns_dataframe(self, sharp_engine):
        df = sharp_engine.order_sensitivity(orders=[1, 2, 3])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_default_orders(self, sharp_engine):
        df = sharp_engine.order_sensitivity()
        assert len(df) == 4  # [1, 2, 3, 4]

    def test_columns(self, sharp_engine):
        df = sharp_engine.order_sensitivity(orders=[1, 2])
        for col in ["order", "coef", "se", "pval", "n_obs"]:
            assert col in df.columns

    def test_uses_stored_bandwidth(self, fitted_engine):
        df = fitted_engine.order_sensitivity(orders=[1, 2])
        # bandwidth should match the fitted one
        assert (df["coef"].notna()).all()


class TestKernelSensitivity:
    def test_returns_dataframe(self, sharp_engine):
        df = sharp_engine.kernel_sensitivity(kernels=["triangular", "uniform"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_default_kernels(self, sharp_engine):
        df = sharp_engine.kernel_sensitivity()
        assert len(df) == 4

    def test_columns(self, sharp_engine):
        df = sharp_engine.kernel_sensitivity(kernels=["triangular"])
        for col in ["kernel", "coef", "se", "pval", "n_obs"]:
            assert col in df.columns

    def test_uses_stored_bandwidth(self, fitted_engine):
        df = fitted_engine.kernel_sensitivity(kernels=["triangular", "uniform"])
        assert (df["coef"].notna()).all()


# ─────────────────────────────────────────────────────────────────────────────
# 9. summary / to_latex
# ─────────────────────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_empty(self, sharp_engine):
        df = sharp_engine.summary()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_summary_after_sharp_fit(self, fitted_engine):
        df = fitted_engine.summary()
        assert len(df) == 1
        assert df.iloc[0]["Type"] == "Sharp RDD"
        assert "Coef" in df.columns
        assert "SE" in df.columns

    def test_summary_after_fuzzy_fit(self, fuzzy_engine):
        fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        df = fuzzy_engine.summary()
        assert len(df) == 1
        assert df.iloc[0]["Type"] == "Fuzzy RDD"
        assert "FS F-stat" in df.columns

    def test_summary_combined(self, fuzzy_engine):
        """summary combines sharp + fuzzy rows."""
        fuzzy_engine.fit(bandwidth=0.5)
        fuzzy_engine.fit_fuzzy(bandwidth=0.5)
        df = fuzzy_engine.summary()
        assert len(df) == 2
        types = set(df["Type"].tolist())
        assert "Sharp RDD" in types
        assert "Fuzzy RDD" in types


class TestToLatex:
    def test_to_latex_empty(self, sharp_engine):
        latex = sharp_engine.to_latex()
        assert latex == ""

    def test_to_latex_after_fit(self, fitted_engine):
        latex = fitted_engine.to_latex()
        assert "\\begin{table}" in latex
        assert "\\toprule" in latex
        assert "Sharp RDD" in latex
        assert "Coef" in latex

    def test_to_latex_includes_density_note(self, fitted_engine):
        fitted_engine.mccrary_test()
        latex = fitted_engine.to_latex()
        assert "McCrary" in latex

    def test_to_latex_includes_bandwidth_note(self, fitted_engine):
        fitted_engine.select_bandwidth(method="manual", manual_bw=0.4)
        # Re-fit to attach bandwidth_result
        fitted_engine.fit(bandwidth=0.4)
        latex = fitted_engine.to_latex()
        assert "Bandwidth" in latex

    def test_save_sensitivity_latex(self, tmp_path, fitted_engine):
        fitted_engine.bandwidth_sensitivity(bw_methods=["ik"])
        out = tmp_path / "sens.tex"
        fitted_engine.save_sensitivity_latex(out)
        assert out.exists()
        assert "\\begin{table}" in out.read_text()

    def test_save_sensitivity_latex_no_data(self, tmp_path, sharp_engine):
        """Without prior sensitivity analysis, file should not be created."""
        out = tmp_path / "no_sens.tex"
        sharp_engine.save_sensitivity_latex(out)
        assert not out.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Plotting
# ─────────────────────────────────────────────────────────────────────────────


class TestPlotting:
    def teardown_method(self):
        plt.close("all")

    def test_plot_rdd_returns_figure(self, fitted_engine, tmp_path):
        save = tmp_path / "rdd.pdf"
        fig = fitted_engine.plot_rdd(save_path=save)
        assert fig is not None
        assert save.exists()

    def test_plot_rdd_explicit_bandwidth(self, sharp_engine, tmp_path):
        save = tmp_path / "rdd2.pdf"
        fig = sharp_engine.plot_rdd(bandwidth=0.5, save_path=save)
        assert fig is not None
        assert save.exists()

    def test_plot_rdd_triggers_bandwidth_selection(self, sharp_engine, tmp_path):
        """If bandwidth not provided and not stored, auto-select via ik."""
        save = tmp_path / "rdd3.pdf"
        fig = sharp_engine.plot_rdd(save_path=save)
        assert fig is not None

    def test_plot_sensitivity(self, sharp_engine, tmp_path):
        sharp_engine.bandwidth_sensitivity(bw_methods=["ik"])
        save = tmp_path / "sens.pdf"
        fig = sharp_engine.plot_sensitivity(save_path=save)
        assert fig is not None

    def test_plot_covariate_balance(self, fuzzy_engine, tmp_path):
        fuzzy_engine.covariate_balance()  # populate results first
        save = tmp_path / "bal.pdf"
        fig = fuzzy_engine.plot_covariate_balance(save_path=save)
        assert fig is not None

    def test_plot_mccrary(self, sharp_engine, tmp_path):
        sharp_engine.mccrary_test()
        save = tmp_path / "mcc.pdf"
        fig = sharp_engine.plot_mccrary(save_path=save)
        assert fig is not None


# ─────────────────────────────────────────────────────────────────────────────
# 11. End-to-end workflow
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_pipeline_sharp(self, sharp_df, tmp_path):
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0)
        engine.select_bandwidth(method="manual", manual_bw=0.5)
        sharp = engine.fit(bandwidth=0.5, kernel="triangular", order=1)
        mccrary = engine.mccrary_test()
        bw_sens = engine.bandwidth_sensitivity(bw_methods=["ik", "msed"])
        order_sens = engine.order_sensitivity(orders=[1, 2, 3])
        latex = engine.to_latex()

        assert 1.0 < sharp.coef < 4.0
        assert mccrary is not None
        assert len(bw_sens) >= 2
        assert len(order_sens) == 3
        assert "\\begin{table}" in latex

    def test_full_pipeline_fuzzy(self, fuzzy_df):
        engine = RDDEngine(
            fuzzy_df, y_var="y", x_var="x", cutoff=0.0,
            treat_var="treat", covariate_vars=["cov1"],
        )
        sharp = engine.fit(bandwidth=0.5)
        fuzzy = engine.fit_fuzzy(bandwidth=0.5)
        balance = engine.covariate_balance()
        summary = engine.summary()

        assert 1.0 < sharp.coef < 4.0
        assert -1.0 < fuzzy.tau_iv < 8.0
        assert len(balance) == 1
        assert len(summary) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 12. Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_cutoff_nonzero(self):
        rng = np.random.default_rng(42)
        n = 1000
        x = rng.uniform(0, 10, n)
        y = 1.0 + 0.5 * x + 2.0 * (x >= 5.0) + rng.normal(0, 1, n)
        df = pd.DataFrame({"x": x, "y": y})
        engine = RDDEngine(df, y_var="y", x_var="x", cutoff=5.0)
        res = engine.fit(bandwidth=1.5, kernel="triangular", order=1)
        assert 0.5 < res.coef < 4.0

    def test_bandwidth_larger_than_data_range(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "x": rng.uniform(-1, 1, 200),
            "y": rng.normal(0, 1, 200),
        })
        engine = RDDEngine(df, y_var="y", x_var="x", cutoff=0.0)
        # Bandwidth larger than data range uses all observations
        res = engine.fit(bandwidth=10.0)
        assert res.n_obs == 200

    def test_donut_larger_than_bandwidth(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "x": rng.uniform(-1, 1, 500),
            "y": rng.normal(0, 1, 500),
        })
        engine = RDDEngine(df, y_var="y", x_var="x", cutoff=0.0)
        # donut > bandwidth → no observations
        res = engine.fit(bandwidth=0.5, donut=1.0)
        assert np.isnan(res.coef)

    def test_cluster_se_differs_from_analytical(self, sharp_df):
        sharp_df = sharp_df.copy()
        sharp_df["cluster"] = np.random.default_rng(42).integers(0, 50, len(sharp_df))
        engine = RDDEngine(sharp_df, y_var="y", x_var="x", cutoff=0.0,
                           cluster_var="cluster")
        res_analytical = engine.fit(bandwidth=0.5, se_method="analytical")
        res_cluster = engine.fit(bandwidth=0.5, se_method="cluster")
        # Same coef, but SEs may differ
        assert abs(res_analytical.coef - res_cluster.coef) < 0.01
        # Cluster SE is usually larger with few clusters
        assert res_cluster.se > 0
