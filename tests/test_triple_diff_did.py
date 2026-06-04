"""Tests for scripts/research_framework/triple_diff_did.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def ddd_data():
    """50 firms × 12 years × 3 industries (3-way panel)."""
    np.random.seed(42)
    n, t, ind = 50, 12, 3

    data = []
    for firm in range(n):
        is_treated = firm < 20
        for year in range(t):
            post = 1 if year >= 6 else 0
            treatment = 1 if is_treated and year >= 6 else 0
            for industry in range(ind):
                y = (
                    0.05
                    + 0.01 * year
                    + 0.02 * treatment
                    + 0.01 * industry
                    + np.random.normal(0, 0.02)
                )
                data.append({
                    "firm": firm,
                    "year": year,
                    "industry": industry,
                    "y": y,
                    "did": float(treatment),
                    "post": float(post),
                    "size": np.random.uniform(18, 22),
                    "lev": np.random.uniform(0.2, 0.8),
                })
    return pd.DataFrame(data)


# ── 1. Engine initialization ───────────────────────────────────────────────────


class TestTripleDiffInit:
    """Test TripleDiffDIDEngine.__init__."""

    def test_engine_init(self, ddd_data):
        """TripleDiffDIDEngine initializes correctly."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        assert eng.y_var == "y"
        assert eng.treat_var == "did"
        assert eng.time_var == "post"
        assert eng.unit_var == "firm"
        assert eng.group3_var == "industry"

    def test_module_exports(self):
        """TripleDiffDIDEngine and DDDResult are in __all__."""
        from scripts.research_framework import triple_diff_did as tddd

        assert "TripleDiffDIDEngine" in tddd.__all__
        assert "DDDResult" in tddd.__all__


# ── 2. fit() ─────────────────────────────────────────────────────────────────


class TestTripleDiffFit:
    """Test TripleDiffDIDEngine.fit()."""

    def test_fit_returns_ddd_result(self, ddd_data):
        """fit() returns DDDResult with coef, se, pval."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        result = eng.fit()
        assert hasattr(result, "coef")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")
        assert result.estimator == "ddd_ols"

    def test_fit_with_controls(self, ddd_data):
        """fit() accepts control variables."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        result = eng.fit(x_vars=["size", "lev"])
        assert result is not None

    def test_fit_insufficient_data(self):
        """fit() handles insufficient data gracefully."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        # Too few observations
        df = pd.DataFrame({
            "firm": [0, 1, 2, 3],
            "year": [0, 0, 1, 1],
            "y": np.random.randn(4),
            "did": [0, 0, 1, 1],
            "post": [0, 0, 1, 1],
            "industry": [0, 1, 0, 1],
        })
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        result = eng.fit()
        # Should return an empty-ish result without crashing
        assert result is not None


# ── 3. get_hte() ─────────────────────────────────────────────────────────────


class TestHeterogeneousEffects:
    """Test get_hte() for heterogeneous treatment effects by group3."""

    def test_get_hte_returns_dataframe(self, ddd_data):
        """get_hte() returns DataFrame with group3, coef, se, pval."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        hte_df = eng.get_hte()
        assert isinstance(hte_df, pd.DataFrame)
        assert "group3" in hte_df.columns
        assert "coef" in hte_df.columns
        assert "se" in hte_df.columns

    def test_get_hte_has_significance_column(self, ddd_data):
        """get_hte() includes sig column for significance markers."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        hte_df = eng.get_hte()
        assert "sig" in hte_df.columns


# ── 4. get_event_study() ──────────────────────────────────────────────────────


class TestEventStudy:
    """Test get_event_study() for event-study DDD."""

    def test_get_event_study(self, ddd_data):
        """get_event_study([-3, 3]) returns DataFrame with horizon/coef/se."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        es_df = eng.get_event_study(horizons=[-3, -2, -1, 1, 2, 3])
        assert isinstance(es_df, pd.DataFrame)
        assert "horizon" in es_df.columns
        assert "coef" in es_df.columns


# ── 5. sensitivity_placebo() ────────────────────────────────────────────────


class TestPlaceboTest:
    """Test sensitivity_placebo() for placebo检验."""

    def test_placebo_small_n(self, ddd_data):
        """sensitivity_placebo(n=10) returns DataFrame."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        placebo_df = eng.sensitivity_placebo(n_simulations=10, random_seed=42)
        assert isinstance(placebo_df, pd.DataFrame)
        assert "coef" in placebo_df.columns

    def test_placebo_adds_summary_attr(self, ddd_data):
        """placebo_df.attrs contains summary statistics."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        placebo_df = eng.sensitivity_placebo(n_simulations=5, random_seed=42)
        assert hasattr(placebo_df, "attrs")
        assert "summary" in placebo_df.attrs


# ── 6. synthetic_did() ───────────────────────────────────────────────────────


class TestSyntheticDDD:
    """Test synthetic_did() for Synthetic DDD."""

    def test_synthetic_did_no_donor_pool(self):
        """synthetic_did() handles missing donor pool gracefully."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        # Only treated units, no control units
        df = pd.DataFrame({
            "firm": list(range(10)),
            "year": [0] * 5 + [1] * 5,
            "y": np.random.randn(10),
            "did": [1] * 5 + [1] * 5,  # all treated
            "post": [0] * 5 + [1] * 5,
            "industry": [0] * 5 + [1] * 5,
        })
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        # Should not crash
        result = eng.synthetic_did()
        assert isinstance(result, dict)
        assert "att" in result

    def test_synthetic_did_returns_dict(self, ddd_data):
        """synthetic_did() returns dict with att, weights, placebo_pval."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        result = eng.synthetic_did()
        assert isinstance(result, dict)
        assert "att" in result


# ── 7. plot_hte() ──────────────────────────────────────────────────────────


class TestPlotHTE:
    """Test plot_hte() forest plot."""

    def test_plot_hte_returns_figure_or_none(self, ddd_data):
        """plot_hte() returns matplotlib Figure or None."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        eng.get_hte()
        fig = eng.plot_hte()  # No save_path
        # Returns Figure or None (depends on matplotlib)
        assert fig is None or hasattr(fig, "savefig")


# ── 8–9. summary() and to_latex() ──────────────────────────────────────────


class TestSummaryAndLatex:
    """Test summary() and to_latex()."""

    def test_summary_returns_dataframe(self, ddd_data):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        summary_df = eng.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "Coef" in summary_df.columns

    def test_to_latex_returns_string(self, ddd_data):
        """to_latex() returns non-empty LaTeX string."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        latex_str = eng.to_latex()
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str

    def test_summary_empty_if_no_fit(self):
        """summary() returns empty DataFrame before fit()."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = pd.DataFrame({
            "firm": [0, 1],
            "year": [0, 0],
            "y": [0.1, 0.2],
            "did": [0, 1],
            "post": [0, 1],
            "industry": [0, 1],
        })
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        summary_df = eng.summary()
        assert isinstance(summary_df, pd.DataFrame)


# ── 10. Invalid group3_var ─────────────────────────────────────────────────


class TestInvalidInputs:
    """Test handling of invalid inputs."""

    def test_invalid_group3_var(self):
        """Non-existent group3_var handles gracefully."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = pd.DataFrame({
            "firm": [0, 1, 2, 3],
            "year": [0, 0, 1, 1],
            "y": np.random.randn(4),
            "did": [0, 0, 1, 1],
            "post": [0, 0, 1, 1],
        })
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="nonexistent_col",
        )
        # Should not crash during init; fit may return empty result
        result = eng.fit()
        assert result is not None


# ── Additional: get_2way_did ───────────────────────────────────────────────


class TestTwoWayDID:
    """Test get_2way_did() for 2-way DID within specific group3."""

    def test_get_2way_did(self, ddd_data):
        """get_2way_did(group3_value) returns DDDResult."""
        from scripts.research_framework.triple_diff_did import (
            TripleDiffDIDEngine,
        )

        df = ddd_data
        eng = TripleDiffDIDEngine(
            df=df,
            y_var="y",
            treat_var="did",
            time_var="post",
            unit_var="firm",
            group3_var="industry",
        )
        eng.fit()
        result = eng.get_2way_did(group3_value=0)
        assert hasattr(result, "coef")
        assert hasattr(result, "se")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
