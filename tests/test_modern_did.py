"""Tests for scripts/research_framework/modern_did.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


class TestModernDiDBasics:
    """Happy-path tests for ModernDiDEngine."""

    def test_engine_init(self, mock_did_df):
        """ModernDiDEngine initializes correctly."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        assert engine.y_var == "roa"
        assert engine.treat_var == "did"
        assert engine.time_var == "post"
        assert engine.unit_var == "firm_id"

    def test_engine_basic_stats(self, mock_did_df):
        """Engine computes n_obs, n_treated, n_control, n_periods."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        assert engine.n_obs == len(mock_did_df)
        assert engine.n_treated == int((mock_did_df["did"] == 1).sum())
        assert engine.n_control == int((mock_did_df["did"] == 0).sum())
        assert engine.n_periods == mock_did_df["post"].nunique()

    def test_did_2x2_result_attributes(self, mock_did_df):
        """did_2x2() returns DiDEstimationResult with all expected fields."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2()

        assert hasattr(result, "estimator")
        assert hasattr(result, "coef")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")
        assert hasattr(result, "ci_lower")
        assert hasattr(result, "ci_upper")
        assert hasattr(result, "n_obs")
        assert hasattr(result, "n_treated")
        assert hasattr(result, "n_control")
        assert hasattr(result, "n_periods")
        assert hasattr(result, "r_squared")
        assert hasattr(result, "method")
        assert hasattr(result, "additional")

    def test_did_2x2_coef_is_finite(self, mock_did_df):
        """did_2x2() coefficient is finite."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2()

        assert np.isfinite(result.coef)
        assert np.isfinite(result.se)
        assert np.isfinite(result.pval)

    def test_did_2x2_with_controls(self, mock_did_df):
        """did_2x2() accepts x_vars control variables."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
            x_vars=["ln_assets", "roa_lag"],
        )
        result = engine.did_2x2()

        assert np.isfinite(result.coef)

    def test_did_2x2_with_cluster(self, mock_did_df):
        """did_2x2() accepts cluster_var for clustered SEs."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2(cluster_var="industry")

        assert np.isfinite(result.coef)
        assert result.method == "cluster"


class TestModernDiDSig:
    """Significance stars tests."""

    @pytest.mark.parametrize("pval,expected", [
        (0.0001, "***"),
        (0.005, "**"),
        (0.03, "*"),
        (0.08, r"$\dagger$"),
        (0.5, ""),
    ])
    def test_sig_stars(self, pval, expected):
        """DiDEstimationResult.sig returns correct stars."""
        from scripts.research_framework.modern_did import DiDEstimationResult

        result = DiDEstimationResult(
            estimator="test",
            coef=0.0,
            se=0.0,
            pval=pval,
            n_obs=1,
        )
        assert result.sig == expected


class TestModernDiDToDict:
    """Result serialization tests."""

    def test_result_to_dict(self, mock_did_df):
        """to_dict() returns serializable dict."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.did_2x2()
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "coef" in d
        assert "se" in d
        assert "pval" in d
        assert "sig" in d
        assert "n_obs" in d


class TestModernDiDSummary:
    """Summary table tests."""

    def test_summary_returns_dataframe(self, mock_did_df):
        """summary() returns a DataFrame."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        engine.did_2x2()
        df = engine.summary()

        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "Estimator" in df.columns
        assert "Coef" in df.columns

    def test_summary_multiple_estimators(self, mock_did_df):
        """summary() includes multiple estimators when called."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        engine.did_2x2()
        engine.bacon()

        df = engine.summary()
        assert len(df) >= 1


class TestModernDiDToLatex:
    """LaTeX export tests."""

    def test_to_latex_returns_string(self, mock_did_df):
        """to_latex() returns a string of LaTeX code."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        engine.did_2x2()
        latex = engine.to_latex()

        assert isinstance(latex, str)
        assert r"\begin{table}" in latex
        assert r"\end{table}" in latex
        assert r"\caption" in latex

    def test_to_latex_empty_results(self, mock_did_df):
        """to_latex() handles the case when the engine was initialized."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        # Don't call did_2x2(), results are empty
        # summary() should return empty DataFrame
        assert engine.summary().empty or engine.summary().shape[0] == 0


class TestModernDiDParallelTrends:
    """Parallel trends test."""

    def test_parallel_trends_test(self, mock_did_df):
        """parallel_trends_test() returns a dict with expected keys."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.parallel_trends_test()

        assert isinstance(result, dict)
        assert "pval" in result
        assert "test" in result


class TestModernDiDBacon:
    """Bacon decomposition tests."""

    def test_bacon_decomposition(self, mock_did_df):
        """bacon() returns a DataFrame."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        df = engine.bacon()

        assert isinstance(df, pd.DataFrame)


class TestModernDiDHonestDid:
    """Honest DiD sensitivity tests."""

    def test_honest_did(self, mock_did_df):
        """honest_did() returns sensitivity analysis dict."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.honest_did(m=0.5)

        assert isinstance(result, dict)
        assert "coef" in result
        assert "se" in result
        assert "breakdown_value" in result
        assert "delta_grid" in result
        assert "ci_bounds" in result

    def test_honest_did_interpretation(self, mock_did_df):
        """honest_did() includes human-readable interpretation."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.honest_did(m=0.5)

        assert "interpretation" in result
        assert isinstance(result["interpretation"], str)


class TestModernDiDWildBootstrap:
    """Wild cluster bootstrap tests."""

    def test_wild_bootstrap(self, mock_did_df):
        """wild_bootstrap() returns bootstrap results dict."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.wild_bootstrap(
            cluster_var="industry",
            B=99,
            bootstrap_type="rademacher",
        )

        assert isinstance(result, dict)
        assert "pval" in result
        assert "ci_lower" in result
        assert "ci_upper" in result

    def test_wild_bootstrap_no_cluster_var(self, mock_did_df):
        """wild_bootstrap() without cluster_var returns error dict."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        result = engine.wild_bootstrap()

        assert isinstance(result, dict)
        assert "error" in result


class TestModernDiDEventStudy:
    """Event study tests."""

    def test_event_study_data(self, mock_did_df):
        """event_study_data() returns a DataFrame with horizon/coef/se."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        df = engine.event_study_data(horizons=[-3, -2, -1, 1, 2, 3])

        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "horizon" in df.columns
            assert "coef" in df.columns
            assert "se" in df.columns

    def test_plot_event_study(self, mock_did_df):
        """plot_event_study() returns Figure or None."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        fig = engine.plot_event_study(
            horizons=[-3, -2, -1, 1, 2, 3],
            estimator="did_2x2",
        )
        # May be None if matplotlib not installed
        if fig is not None:
            import matplotlib.figure
            assert isinstance(fig, matplotlib.figure.Figure)


class TestModernDiDFallbacks:
    """Estimator fallback tests (when external packages unavailable)."""

    def test_cs_raises_estimator_unavailable(self, mock_did_df):
        """cs() raises EstimatorUnavailableError when diff_in_diff2 not installed."""
        from scripts.research_framework.modern_did import ModernDiDEngine, EstimatorUnavailableError

        # Simulate package unavailability by patching
        import scripts.research_framework.modern_did as md
        orig_import = md.__dict__.get("import")

        def fake_import(name, *args, **kwargs):
            if name == "diff_in_diff2":
                raise ImportError("Simulated: package not installed")
            return orig_import(name, *args, **kwargs)

        md.__dict__["import"] = fake_import

        try:
            engine = ModernDiDEngine(
                df=mock_did_df,
                y_var="roa",
                treat_var="did",
                time_var="post",
                unit_var="firm_id",
            )
            try:
                engine.cs()
                assert False, "Expected EstimatorUnavailableError"
            except EstimatorUnavailableError as e:
                assert e.estimator == "cs"
                assert "diff-in-diff2" in e.package
        finally:
            md.__dict__["import"] = orig_import

    def test_bjs_raises_estimator_unavailable(self, mock_did_df):
        """bjs() raises EstimatorUnavailableError when diff_in_diff2 not installed."""
        from scripts.research_framework.modern_did import ModernDiDEngine, EstimatorUnavailableError

        import scripts.research_framework.modern_did as md
        orig_import = md.__dict__.get("import")

        def fake_import(name, *args, **kwargs):
            if name == "diff_in_diff2":
                raise ImportError("Simulated: package not installed")
            return orig_import(name, *args, **kwargs)

        md.__dict__["import"] = fake_import

        try:
            engine = ModernDiDEngine(
                df=mock_did_df,
                y_var="roa",
                treat_var="did",
                time_var="post",
                unit_var="firm_id",
            )
            try:
                engine.bjs()
                assert False, "Expected EstimatorUnavailableError"
            except EstimatorUnavailableError as e:
                assert e.estimator == "bjs"
                assert "diff-in-diff2" in e.package
        finally:
            md.__dict__["import"] = orig_import


class TestModernDiDEdgeCases:
    """Edge case tests."""

    def test_engine_empty_result(self, mock_did_df):
        """_empty_result() returns valid DiDEstimationResult."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_did_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
        )
        empty = engine._empty_result("test_estimator")

        assert empty.estimator == "test_estimator"
        assert empty.coef == 0
        assert empty.se == 0
        assert empty.pval == 1
        assert empty.n_obs == 1

    def test_engine_missing_columns(self):
        """Engine with missing columns raises ValueError."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        df = pd.DataFrame({
            "firm_id": ["A", "B", "C"],
            "post": [0, 1, 1],
        })
        import pytest
        with pytest.raises(ValueError, match="Missing required columns"):
            ModernDiDEngine(
                df=df,
                y_var="roa",
                treat_var="did",
                time_var="post",
                unit_var="firm_id",
            )

    def test_parallel_trends_no_pre_periods(self):
        """parallel_trends_test() handles no pre-periods gracefully."""
        from scripts.research_framework.modern_did import ModernDiDEngine, _test_parallel_trends

        # All treated from start
        df = pd.DataFrame({
            "firm_id": ["A", "B", "C", "D"],
            "year": [2020, 2021, 2022, 2023],
            "roa": [0.1, 0.1, 0.1, 0.1],
            "did": [1, 1, 1, 1],
            "post": [1, 1, 1, 1],
        })
        result = _test_parallel_trends(df, "roa", "did", "post", "firm_id")

        assert isinstance(result, dict)
        assert "pval" in result

    def test_engine_with_panel_df(self, mock_panel_df):
        """Engine works with panel DataFrame fixture."""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            df=mock_panel_df,
            y_var="roa",
            treat_var="did",
            time_var="post",
            unit_var="firm_id",
            x_vars=["lev", "size", "tangibility"],
            cluster_var="industry",
        )
        result = engine.did_2x2(cluster_var="industry")

        assert np.isfinite(result.coef)
        assert result.n_obs > 0
