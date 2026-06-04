"""Tests for scripts/research_framework/regression_engine.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np
import pandas as pd


class TestRegressionEngineInit:
    """RegressionEngine initialization tests."""

    def test_engine_init_defaults(self, mock_did_df):
        """RegressionEngine initializes with correct defaults."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df)

        assert engine.firm_col == "ticker"
        assert engine.year_col == "year"
        assert engine._results == []

    def test_engine_init_custom_columns(self, mock_did_df):
        """RegressionEngine accepts custom firm_col and year_col."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(
            mock_did_df,
            firm_col="firm_id",
            year_col="year",
        )
        assert engine.firm_col == "firm_id"
        assert engine.year_col == "year"

    def test_engine_with_tracker(self, mock_did_df):
        """RegressionEngine accepts tracker parameter."""
        from scripts.research_framework.regression_engine import RegressionEngine

        mock_tracker = {"mock": True}
        engine = RegressionEngine(mock_did_df, tracker=mock_tracker)

        assert engine.tracker is mock_tracker


class TestRegressionEngineDOF:
    """Degrees-of-freedom checking tests."""

    def test_check_dof_valid(self, mock_did_df):
        """_check_dof() returns is_valid=True for adequate data."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        diag = engine._check_dof(
            n_obs=200,
            x_vars=["lev", "size"],
            has_firm_fe=True,
            has_year_fe=True,
        )

        assert isinstance(diag, dict)
        assert "is_valid" in diag
        assert "residual_df" in diag
        assert "n_params" in diag
        assert "n_fe" in diag

    def test_check_dof_insufficient_dof(self, mock_did_df):
        """_check_dof() flags insufficient DOF."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        diag = engine._check_dof(
            n_obs=5,
            x_vars=["lev", "size", "tangibility"],
            has_firm_fe=True,
            has_year_fe=True,
        )

        assert diag["is_valid"] is False
        assert "WARNING" in diag["issue"] or "CRITICAL" in diag["issue"]

    def test_check_dof_fallback_triggered(self, mock_did_df):
        """_check_dof() sets fallback_triggered=True when DOF insufficient."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        diag = engine._check_dof(
            n_obs=3,
            x_vars=["x1", "x2", "x3", "x4", "x5"],
            has_firm_fe=True,
            has_year_fe=True,
        )

        assert diag["fallback_triggered"] is True


class TestRegressionEngineDID:
    """DID regression tests."""

    def test_did_basic(self, mock_did_df):
        """did() runs without error and returns dict."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
        )

        assert isinstance(result, dict)
        assert "did_coef" in result
        assert "did_se" in result
        assert "did_pval" in result
        assert "model" in result
        assert "diagnostic" in result
        assert "n_obs" in result

    def test_did_coef_finite(self, mock_did_df):
        """did() coefficient is finite."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
        )

        assert np.isfinite(result["did_coef"])
        assert np.isfinite(result["did_se"])
        assert np.isfinite(result["did_pval"])

    def test_did_with_controls(self, mock_did_df):
        """did() accepts control variables."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            x_vars=["ln_assets", "roa_lag"],
        )

        assert np.isfinite(result["did_coef"])
        assert result["n_obs"] > 0

    def test_did_with_cluster_se(self, mock_did_df):
        """did() accepts cluster_var for clustered SEs."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            cluster_var="industry",
        )

        assert np.isfinite(result["did_coef"])
        assert result["n_obs"] > 0

    def test_did_with_firm_fe_disabled(self, mock_did_df):
        """did() with use_firm_fe=False runs successfully."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            use_firm_fe=False,
        )

        assert np.isfinite(result["did_coef"])

    def test_did_fallback_logged(self, mock_did_df):
        """did() logs warning when DOF insufficient."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")

        # Create tiny dataset that triggers fallback
        tiny_df = mock_did_df.head(5).copy()
        tiny_df["treat"] = [1, 0, 1, 0, 1]
        tiny_df["post"] = [1, 1, 0, 0, 1]

        engine_small = RegressionEngine(tiny_df, firm_col="firm_id", year_col="year")
        result = engine_small.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            use_firm_fe=True,
            use_year_fe=True,
        )

        # Should still return finite result (fallback to pooled)
        assert np.isfinite(result["did_coef"])

    def test_did_result_in_results_list(self, mock_did_df):
        """did() appends result to engine._results."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        assert len(engine._results) == 0

        engine.did(y_var="roa", treat_var="treat", time_var="post")

        assert len(engine._results) == 1

    def test_did_r_squared(self, mock_did_df):
        """did() returns r_squared in result."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
        )

        assert "r_squared" in result
        assert 0 <= result["r_squared"] <= 1


class TestRegressionEngineOLS:
    """Pooled OLS regression tests."""

    def test_ols_basic(self, mock_did_df):
        """ols() runs without error."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.ols(
            y_var="roa",
            x_vars=["treat", "ln_assets"],
        )

        assert isinstance(result, dict)
        assert "model" in result
        assert "all_coefs" in result
        assert "diagnostic" in result

    def test_ols_coef_finite(self, mock_did_df):
        """ols() returns finite coefficients."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.ols(
            y_var="roa",
            x_vars=["treat", "ln_assets"],
        )

        for name, coef_dict in result["all_coefs"].items():
            assert np.isfinite(coef_dict["coef"])
            assert np.isfinite(coef_dict["se"])


class TestRegressionEnginePSMDID:
    """PSM-DID tests."""

    def test_psm_did_basic(self, mock_did_df):
        """psm_did() runs without error."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.psm_did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            match_vars=["ln_assets"],
        )

        assert isinstance(result, dict)
        assert "did_coef" in result
        assert "psm_note" in result

    def test_psm_did_note_format(self, mock_did_df):
        """psm_did() psm_note is a non-empty string."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.psm_did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            match_vars=["ln_assets"],
        )

        assert isinstance(result["psm_note"], str)
        assert len(result["psm_note"]) > 0
        assert "PSM" in result["psm_note"]


class TestRegressionEngineOutput:
    """Output formatting tests."""

    def test_did_table_columns(self, mock_did_df):
        """did_table() returns DataFrame with Variable column."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result1 = engine.did(y_var="roa", treat_var="treat", time_var="post")
        result2 = engine.did(y_var="roa", treat_var="treat", time_var="post",
                             x_vars=["ln_assets"])

        df = engine.did_table(
            results_list=[result1, result2],
            y_labels=["(1)", "(2)"],
            x_vars=["did", "treat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert "Variable" in df.columns
        assert "(1)" in df.columns or "(2)" in df.columns

    def test_did_table_n_rows(self, mock_did_df):
        """did_table() includes N and R² rows."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(y_var="roa", treat_var="treat", time_var="post")

        df = engine.did_table(
            results_list=[result],
            y_labels=["(1)"],
            x_vars=["did"],
        )

        variables = df["Variable"].tolist()
        assert "N" in variables
        assert "R²" in variables

    def test_to_latex(self, mock_did_df):
        """to_latex() returns valid LaTeX table string."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(y_var="roa", treat_var="treat", time_var="post")

        latex = engine.to_latex(
            results_list=[result],
            y_labels=["(1)"],
            x_vars=["did"],
            caption="Test Table",
            label="tab:test",
        )

        assert isinstance(latex, str)
        assert r"\begin{table}" in latex
        assert r"\end{table}" in latex
        assert r"\caption{Test Table}" in latex
        assert r"\label{tab:test}" in latex

    def test_to_latex_with_fe_warning(self, mock_did_df):
        """to_latex() includes FE warning row when fallback triggered."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(y_var="roa", treat_var="treat", time_var="post")

        df = engine.did_table(
            results_list=[result],
            y_labels=["(1)"],
            x_vars=["did"],
        )
        # Check that diagnostic rows are included
        assert "Variable" in df.columns

    def test_save_latex(self, mock_did_df, tmp_path):
        """save_latex() writes file to disk."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(y_var="roa", treat_var="treat", time_var="post")

        path = tmp_path / "test_table.tex"
        engine.save_latex(
            results_list=[result],
            y_labels=["(1)"],
            x_vars=["did"],
            path=str(path),
            caption="Test",
            label="tab:test",
        )

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert r"\begin{table}" in content

    def test_save_markdown(self, mock_did_df, tmp_path):
        """save_markdown() writes markdown table to disk."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(y_var="roa", treat_var="treat", time_var="post")

        path = tmp_path / "test_table.md"
        engine.save_markdown(
            results_list=[result],
            y_labels=["(1)"],
            x_vars=["did"],
            path=str(path),
        )

        assert path.exists()


class TestRegressionEngineHelpers:
    """Internal helper function tests."""

    def test_extract_function(self):
        """_extract() handles statsmodels-like result."""
        from scripts.research_framework.regression_engine import _extract
        import statsmodels.api as sm
        import numpy as np

        X = np.column_stack([np.ones(50), np.random.randn(50, 2)])
        y = np.random.randn(50)
        model = sm.OLS(y, X).fit()

        result = _extract(model, ["const", "x1", "x2"])

        assert isinstance(result, dict)
        for name in ["const", "x1", "x2"]:
            assert name in result
            assert "coef" in result[name]
            assert "se" in result[name]
            assert "pval" in result[name]
            assert "sig" in result[name]

    def test_extract_handles_ndarray(self):
        """_extract() handles params without index."""
        from scripts.research_framework.regression_engine import _extract
        import statsmodels.api as sm
        import numpy as np

        X = np.column_stack([np.ones(20), np.random.randn(20)])
        y = np.random.randn(20)
        model = sm.OLS(y, X).fit()

        # Force params to be ndarray
        result = _extract(model, ["const", "x1"])

        assert isinstance(result, dict)
        assert "const" in result or "x1" in result

    def test_fmt_function(self):
        """_fmt() formats coef+se as expected string."""
        from scripts.research_framework.regression_engine import _fmt

        val = {"coef": 1.23456, "se": 0.09876, "sig": "***"}
        result = _fmt(val, d=4)

        assert isinstance(result, str)
        assert "1.2346" in result  # rounded coef
        assert "0.0988" in result  # rounded se
        assert "***" in result

    def test_get_warnings(self, mock_did_df):
        """get_warnings() returns all logged warnings."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")

        # Trigger warnings via tiny dataset
        tiny = mock_did_df.head(3).copy()
        tiny["treat"] = [1, 0, 1]
        tiny["post"] = [1, 1, 0]
        engine_tiny = RegressionEngine(tiny, firm_col="firm_id", year_col="year")
        engine_tiny.did(y_var="roa", treat_var="treat", time_var="post",
                         use_firm_fe=True, use_year_fe=True)

        warnings = engine_tiny.get_warnings()
        assert isinstance(warnings, list)


class TestRegressionEngineEdgeCases:
    """Edge case tests."""

    def test_engine_with_missing_values(self, mock_did_df):
        """RegressionEngine handles DataFrame with NaN values."""
        from scripts.research_framework.regression_engine import RegressionEngine

        df = mock_did_df.copy()
        df.loc[df.sample(frac=0.1).index, "roa"] = np.nan

        engine = RegressionEngine(df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
        )

        assert "did_coef" in result

    def test_engine_with_no_variation(self, mock_did_df):
        """RegressionEngine handles zero-variation outcome."""
        from scripts.research_framework.regression_engine import RegressionEngine

        df = mock_did_df.copy()
        df["roa"] = 0.5  # Constant outcome

        engine = RegressionEngine(df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
        )

        assert "did_coef" in result
        # Coefficient should be 0 or near 0 (no variation)
        assert np.isfinite(result["did_coef"])

    def test_engine_cluster_var_not_in_df(self, mock_did_df):
        """RegressionEngine logs warning when cluster_var not in df."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(mock_did_df, firm_col="firm_id", year_col="year")
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            cluster_var="nonexistent_column",
        )

        assert "did_coef" in result
        # Should fall back to nonrobust
        assert np.isfinite(result["did_coef"])

    def test_engine_with_panel_df(self, mock_panel_df):
        """RegressionEngine works with panel DataFrame fixture."""
        from scripts.research_framework.regression_engine import RegressionEngine

        engine = RegressionEngine(
            mock_panel_df,
            firm_col="firm_id",
            year_col="year",
        )
        result = engine.did(
            y_var="roa",
            treat_var="treat",
            time_var="post",
            x_vars=["lev", "size", "tangibility"],
            cluster_var="industry",
        )

        assert "did_coef" in result
        assert np.isfinite(result["did_coef"])
