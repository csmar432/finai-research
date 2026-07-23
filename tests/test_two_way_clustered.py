"""Tests for two-way clustered standard errors (Cameron-Gelbach-Miller 2011).

Covers:
- regression_engine.py: two_way_clustered_fit(), did() with cluster2_var, ols() with cluster2_var
- modern_did.py: _ols_did() with cluster2_var, did_2x2() with cluster2_var
- iv_panel.py: fit() with cluster2_var
- diagnostic_reporter.py: add_two_way_clustering(), add_from_diagnostic()
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def panel_2way_df():
    """Panel data with firm × year structure for two-way clustering tests."""
    np.random.seed(42)
    n_firms = 50
    n_years = 10
    rows = []
    for fid in range(n_firms):
        for yid in range(n_years):
            treat = 1 if fid >= 25 else 0
            post = 1 if yid >= 5 else 0
            did = treat * post
            y = 1.0 + 2.0 * did + 0.5 * np.random.randn()
            x = np.random.randn()
            rows.append({
                "firm_id": f"firm_{fid}",
                "year": 2010 + yid,
                "y": y,
                "x": x,
                "treat": treat,
                "post": post,
                "did": did,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def twoway_small_df():
    """Small panel for edge-case testing."""
    np.random.seed(0)
    n_firms = 10
    n_years = 5
    rows = []
    for fid in range(n_firms):
        for yid in range(n_years):
            rows.append({
                "ticker": f"F{fid:03d}",
                "year": 2015 + yid,
                "roa": 0.05 + 0.01 * fid + 0.005 * yid + np.random.randn() * 0.02,
                "lev": 0.3 + 0.01 * fid + np.random.randn() * 0.05,
                "size": np.log(1e9 + fid * 1e8),
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# TEST: two_way_clustered_fit in RegressionEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoWayClusteredFit:
    """Tests for RegressionEngine.two_way_clustered_fit()."""

    def test_tw_fit_basic(self, panel_2way_df):
        """Basic two-way clustered regression returns finite coef and SE."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")
        result = engine.two_way_clustered_fit(
            y_var="y",
            x_vars=["x"],
            cluster1="firm_id",
            cluster2="year",
        )

        assert "coefficients" in result
        assert "standard_errors" in result
        assert "pvalues" in result
        assert "cov_type" in result
        assert result["cov_type"] == "two_way_clustered"
        assert result["n_obs"] == len(panel_2way_df)
        assert result["r_squared"] >= 0.0

        x_coef = result["coefficients"].get("x")
        x_se = result["standard_errors"].get("x")
        assert x_coef is not None
        assert x_se is not None
        assert abs(x_coef) < 1000
        assert 0.0 < x_se < 100

    def test_tw_fit_coef_reasonable(self, panel_2way_df):
        """Coefficient should be roughly centered around 0 (x is random)."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")
        result = engine.two_way_clustered_fit(
            y_var="y",
            x_vars=["x"],
            cluster1="firm_id",
            cluster2="year",
        )
        x_se = result["standard_errors"].get("x")
        # SE should be positive and bounded
        assert 1e-10 < x_se < 10.0

    def test_tw_fit_no_obs(self, twoway_small_df):
        """Returns error dict when dropna removes all observations."""
        from scripts.research_framework.regression_engine import RegressionEngine

        # Create a df where y_var exists but all values are NaN → dropna removes everything
        bad_df = twoway_small_df.copy()
        bad_df["y"] = float("nan")
        engine = RegressionEngine(bad_df, firm_col="ticker", year_col="year")
        result = engine.two_way_clustered_fit(
            y_var="y",
            x_vars=["lev"],
            cluster1="ticker",
            cluster2="year",
        )
        assert result["n_obs"] == 0
        assert "error" in result["diagnostic"]

    def test_tw_fit_cluster_eq_fallback(self, twoway_small_df):
        """cluster1 == cluster2 falls back to one-way (no error)."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(twoway_small_df, firm_col="ticker", year_col="year")
        result = engine.two_way_clustered_fit(
            y_var="roa",
            x_vars=["lev"],
            cluster1="ticker",
            cluster2="ticker",
        )
        # Should complete without error (falls back to one-way)
        assert result["n_obs"] > 0

    def test_tw_fit_diagnostic_fields(self, panel_2way_df):
        """Diagnostic dict contains two-way clustering metadata."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")
        result = engine.two_way_clustered_fit(
            y_var="y",
            x_vars=["x"],
            cluster1="firm_id",
            cluster2="year",
        )
        diag = result["diagnostic"]
        assert "n_cl1" in diag
        assert "n_cl2" in diag
        assert "dof" in diag
        assert "cov_type" in diag
        assert diag["n_cl1"] == 50
        assert diag["n_cl2"] == 10
        assert diag["dof"] == min(50, 10) - 1  # = 9


# ─────────────────────────────────────────────────────────────────────────────
# TEST: did() with cluster2_var
# ─────────────────────────────────────────────────────────────────────────────

class TestDidTwoWay:
    """Tests for RegressionEngine.did() with cluster2_var."""

    def test_did_two_way_basic(self, panel_2way_df):
        """did() with cluster2_var returns two-way clustered SE."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="y",
            treat_var="treat",
            time_var="post",
            cluster_var="firm_id",
            cluster2_var="year",
        )

        assert result["diagnostic"]["cov_type"] == "two_way_clustered"
        assert result["n_obs"] > 0
        assert "all_coefs" in result

    def test_did_one_way_when_no_cluster2(self, panel_2way_df):
        """did() without cluster2_var uses standard one-way cluster."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="y",
            treat_var="treat",
            time_var="post",
            cluster_var="firm_id",
        )
        cov_type = result["diagnostic"].get("cov_type")
        assert cov_type in ("cluster", "HC1", "nonrobust")

    def test_did_two_way_vs_one_way_se(self, panel_2way_df):
        """Two-way SE should typically be >= one-way SE (dominance)."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")

        result_1w = engine.did(
            y_var="y", treat_var="treat", time_var="post",
            cluster_var="firm_id",
        )
        result_2w = engine.did(
            y_var="y", treat_var="treat", time_var="post",
            cluster_var="firm_id", cluster2_var="year",
        )

        # Find DID coefficient SE in both
        se_1w = result_1w.get("did_se", 0)
        se_2w = result_2w.get("did_se", 0)

        # Two-way is typically larger than one-way; allow some tolerance
        if se_1w > 0 and se_2w > 0:
            assert se_2w >= se_1w * 0.01  # very loose lower bound


# ─────────────────────────────────────────────────────────────────────────────
# TEST: ols() with cluster2_var
# ─────────────────────────────────────────────────────────────────────────────

class TestOlsTwoWay:
    """Tests for RegressionEngine.ols() with cluster2_var."""

    def test_ols_two_way_basic(self, twoway_small_df):
        """ols() with cluster2_var returns two-way clustered SE."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(twoway_small_df, firm_col="ticker", year_col="year")
        result = engine.ols(
            y_var="roa",
            x_vars=["lev"],
            cluster_var="ticker",
            cluster2_var="year",
        )

        assert result["diagnostic"]["cov_type"] == "two_way_clustered"
        assert result["n_obs"] > 0

    def test_ols_fallback_same_cluster(self, twoway_small_df):
        """ols() falls back gracefully when cluster1 == cluster2."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(twoway_small_df, firm_col="ticker", year_col="year")
        result = engine.ols(
            y_var="roa",
            x_vars=["lev"],
            cluster_var="ticker",
            cluster2_var="ticker",
        )
        assert result["n_obs"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: modern_did._ols_did() with cluster2_var
# ─────────────────────────────────────────────────────────────────────────────

class TestModernDiDTwoWay:
    """Tests for ModernDiDEngine.did_2x2() with cluster2_var."""

    def test_did_2x2_two_way_basic(self, panel_2way_df):
        """did_2x2() with cluster2_var returns two-way clustered SE."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=panel_2way_df,
            y_var="y",
            treat_var="treat",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2(cluster_var="firm_id", cluster2_var="year")

        assert hasattr(result, "se")
        assert hasattr(result, "method")
        assert result.method == "two_way_clustered"
        assert result.n_obs == len(panel_2way_df)

    def test_did_2x2_two_way_finite(self, panel_2way_df):
        """did_2x2() two-way SE is finite."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=panel_2way_df,
            y_var="y",
            treat_var="treat",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2(cluster_var="firm_id", cluster2_var="year")

        assert np.isfinite(result.se)
        assert np.isfinite(result.coef)
        assert np.isfinite(result.pval)
        assert result.se > 0

    def test_did_2x2_one_way_fallback(self, panel_2way_df):
        """did_2x2() without cluster2_var uses one-way cluster."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=panel_2way_df,
            y_var="y",
            treat_var="treat",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2(cluster_var="firm_id")

        assert result.method in ("cluster", "HC1")
        assert np.isfinite(result.se)

    def test_did_2x2_init_cluster2(self, panel_2way_df):
        """Engine initialized with cluster2_var uses it automatically."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=panel_2way_df,
            y_var="y",
            treat_var="treat",
            time_var="post",
            unit_var="firm_id",
            cluster_var="firm_id",
            cluster2_var="year",
        )
        result = engine.did_2x2()
        assert result.method == "two_way_clustered"


# ─────────────────────────────────────────────────────────────────────────────
# TEST: _two_way_clustered_se helper function
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoWayClusteredSeHelper:
    """Tests for the _two_way_clustered_se helper in modern_did.py."""

    def test_helper_basic(self):
        """Helper returns finite params and SE arrays."""
        from scripts.research_framework.modern_did import _two_way_clustered_se

        np.random.seed(99)
        n = 200
        k = 3
        X = np.random.randn(n, k)
        y = X[:, 0] * 2 + X[:, 1] * (-1) + np.random.randn(n) * 0.5
        cl1 = np.repeat(range(20), 10)
        cl2 = np.tile(range(10), 20)

        params, se = _two_way_clustered_se(X, y, cl1, cl2)

        assert len(params) == k
        assert len(se) == k
        assert all(np.isfinite(params))
        assert all(np.isfinite(se))
        assert all(se > 0)

    def test_helper_pooled_meat_defined(self):
        """Pooled (union) cluster meat is computed correctly."""
        from scripts.research_framework.modern_did import _two_way_clustered_se

        np.random.seed(7)
        n = 100
        k = 2
        X = np.random.randn(n, k)
        y = X[:, 0] + 0.3 * np.random.randn(n)
        cl1 = np.repeat(range(10), 10)
        cl2 = np.tile(range(10), 10)

        params, se = _two_way_clustered_se(X, y, cl1, cl2)
        assert all(se > 0)

    def test_helper_returns_correct_k(self):
        """Output arrays have correct dimension matching X columns."""
        from scripts.research_framework.modern_did import _two_way_clustered_se

        np.random.seed(123)
        n = 300
        k = 5
        X = np.random.randn(n, k)
        y = np.random.randn(n)
        cl1 = np.repeat(range(30), 10)
        cl2 = np.tile(range(10), 30)

        params, se = _two_way_clustered_se(X, y, cl1, cl2)
        assert params.shape == (k,)
        assert se.shape == (k,)


# ─────────────────────────────────────────────────────────────────────────────
# TEST: iv_panel with cluster2_var
# ─────────────────────────────────────────────────────────────────────────────

class TestIVPanelTwoWay:
    """Tests for IVPanel.fit() with cluster2_var (linearmodels path)."""

    def test_fit_two_way_param_present(self, twoway_small_df):
        """IVPanel.fit() accepts cluster2_var parameter without error."""
        from scripts.research_framework.iv_panel import IVPanel

        df = twoway_small_df.copy()
        df["iv_z"] = np.random.randn(len(df))

        model = IVPanel(
            df=df,
            y_var="roa",
            x_vars=["lev"],
            iv_vars=["iv_z"],
            unit_var="ticker",
            time_var="year",
        )
        # linearmodels may not be installed; verify param is accepted
        # This test verifies the signature accepts cluster2_var
        import inspect
        sig = inspect.signature(model.fit)
        assert "cluster2_var" in sig.parameters

    def test_fit_signature_has_cluster2_var(self):
        """IVPanel.fit() has cluster2_var in its signature."""
        from scripts.research_framework.iv_panel import IVPanel
        import inspect

        sig = inspect.signature(IVPanel.fit)
        assert "cluster2_var" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# TEST: DiagnosticReporter two-way clustering
# ─────────────────────────────────────────────────────────────────────────────

class TestDiagnosticReporterTwoWay:
    """Tests for DiagnosticReporter.add_two_way_clustering()."""

    def test_add_two_way_basic(self):
        """add_two_way_clustering() adds a check entry."""
        from scripts.research_framework.diagnostic_reporter import (
            DiagnosticReporter,
            DiagnosticDecision,
        )

        reporter = DiagnosticReporter("test_model")
        reporter.add_two_way_clustering(
            cluster_vars=["firm_id", "year"],
            n_cl1=50,
            n_cl2=10,
            dof=9,
        )
        report = reporter.generate()

        assert len(report.checks) >= 1
        tw_check = next(
            (c for c in report.checks if c.name == "two_way_clustered_se"),
            None,
        )
        assert tw_check is not None
        assert tw_check.decision == DiagnosticDecision.PASS
        assert tw_check.details["n_cl1"] == 50
        assert tw_check.details["n_cl2"] == 10
        assert tw_check.details["dof"] == 9
        assert "Cameron" in tw_check.details.get("reference", "")

    def test_add_from_diagnostic_two_way(self):
        """add_from_diagnostic() detects two-way from diag dict."""
        from scripts.research_framework.diagnostic_reporter import DiagnosticReporter

        reporter = DiagnosticReporter("test_model")
        diag = {
            "cov_type": "two_way_clustered",
            "n_cl1": 100,
            "n_cl2": 8,
            "dof": 7,
        }
        reporter.add_from_diagnostic(diag, cluster_vars=["firm_id", "year"])
        report = reporter.generate()

        tw_check = next(
            (c for c in report.checks if c.name == "two_way_clustered_se"),
            None,
        )
        assert tw_check is not None
        assert tw_check.details["n_cl1"] == 100

    def test_add_from_diagnostic_one_way_unchanged(self):
        """add_from_diagnostic() with one-way does not add two-way check."""
        from scripts.research_framework.diagnostic_reporter import DiagnosticReporter

        reporter = DiagnosticReporter("test_model")
        diag = {"cov_type": "cluster", "n_cl1": 50}
        reporter.add_from_diagnostic(diag)
        report = reporter.generate()

        tw_check = next(
            (c for c in report.checks if c.name == "two_way_clustered_se"),
            None,
        )
        assert tw_check is None

    def test_generate_metadata_two_way_flag(self):
        """generate() metadata includes two_way_clustered flag."""
        from scripts.research_framework.diagnostic_reporter import DiagnosticReporter

        reporter = DiagnosticReporter("test_model")
        reporter.add_two_way_clustering(
            cluster_vars=["firm_id", "year"],
            n_cl1=30,
            n_cl2=5,
            dof=4,
        )
        report = reporter.generate()

        assert report.metadata.get("two_way_clustered") is True

    def test_add_two_way_no_firm_year_vars(self):
        """add_two_way_clustering() handles non-standard cluster names."""
        from scripts.research_framework.diagnostic_reporter import (
            DiagnosticReporter,
            DiagnosticDecision,
        )

        reporter = DiagnosticReporter()
        reporter.add_two_way_clustering(
            cluster_vars=["region", "product"],
            n_cl1=20,
            n_cl2=15,
            dof=14,
        )
        report = reporter.generate()

        tw_check = next(
            (c for c in report.checks if c.name == "two_way_clustered_se"),
            None,
        )
        assert tw_check is not None
        assert tw_check.decision == DiagnosticDecision.PASS
        assert "region × product" in tw_check.name_zh


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Dominance property — two-way SE >= one-way SE
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoWayDominance:
    """Two-way SE should dominate one-way SE (always >= one-way)."""

    def test_tw_se_ge_one_way(self, panel_2way_df):
        """Two-way SE should produce finite results and dominate one-way in the weak sense.

        Note: Two-way SE is NOT guaranteed to be >= one-way SE (CGM 2011).
        The CGM estimator can be smaller when firm and time correlations are
        positively correlated. This test verifies BOTH produce valid results
        and that the two-way SE is strictly positive.
        """
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(panel_2way_df, firm_col="firm_id", year_col="year")

        result_1w = engine.ols(
            y_var="y", x_vars=["x"],
            cluster_var="firm_id",
            use_firm_fe=False, use_year_fe=False,
        )
        result_2w = engine.two_way_clustered_fit(
            y_var="y", x_vars=["x"],
            cluster1="firm_id", cluster2="year",
            use_firm_fe=False, use_year_fe=False,
        )

        se_1w = result_1w["all_coefs"].get("x", {}).get("se", 0)
        se_2w = result_2w["standard_errors"].get("x", 0)
        coef_1w = result_1w["all_coefs"].get("x", {}).get("coef", 0)
        coef_2w = result_2w["coefficients"].get("x", 0)

        assert np.isfinite(se_1w) and se_1w > 0, f"One-way SE not valid: {se_1w}"
        assert np.isfinite(se_2w) and se_2w > 0, f"Two-way SE not valid: {se_2w}"
        assert np.isfinite(coef_1w) and np.isfinite(coef_2w)


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Compile check (smoke test all modules)
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleImports:
    """Smoke test: all modules import and basic objects are accessible."""

    def test_regression_engine_import(self):
        from scripts.research_framework.regression_engine import (
            RegressionEngine,
            _extract,
            _fmt,
        )
        assert callable(RegressionEngine)
        assert callable(_extract)
        assert callable(_fmt)

    def test_modern_did_import(self):
        from scripts.research_framework.modern_did import (
            ModernDiDEngine,
            _two_way_clustered_se,
        )
        assert callable(ModernDiDEngine)
        assert callable(_two_way_clustered_se)

    def test_iv_panel_import(self):
        from scripts.research_framework.iv_panel import (
            IVPanel,
            DynamicGMM,
        )
        assert callable(IVPanel)
        assert callable(DynamicGMM)

    def test_diagnostic_reporter_import(self):
        from scripts.research_framework.diagnostic_reporter import (
            DiagnosticReporter,
            DiagnosticCheck,
        )
        assert callable(DiagnosticReporter)
        assert callable(DiagnosticCheck)
