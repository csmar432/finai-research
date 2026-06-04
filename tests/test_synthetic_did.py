"""Tests for scripts/research_framework/synthetic_did.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def sdid_data():
    """10 donors × 20 pre-periods + 10 post-periods, 1 treated unit."""
    np.random.seed(42)
    n_donor = 10
    t_pre, t_post = 20, 10

    # Donor pool: each donor is a time series
    donor_pre = np.random.randn(n_donor, t_pre)
    donor_post = np.random.randn(n_donor, t_post)

    # Treated unit (post has positive shock)
    treated_pre = donor_pre[0] + np.random.randn(t_pre) * 0.2
    treated_post = donor_post[0] + np.random.randn(t_post) * 0.5 + 1.0

    return donor_pre, donor_post, treated_pre, treated_post


# ── 1. Engine initialization ─────────────────────────────────────────────────


class TestSyntheticDiDInit:
    """Test SyntheticDiDEngine.__init__."""

    def test_engine_init(self, sdid_data):
        """SyntheticDiDEngine initializes with arrays."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        assert engine.n_donor == 10
        assert engine.n_pre == 20
        assert engine.n_post == 10

    def test_module_exports(self):
        """SyntheticDiDEngine and SyntheticDiDResult in __all__."""
        from scripts.research_framework import synthetic_did as sdid

        assert "SyntheticDiDEngine" in sdid.__all__
        assert "SyntheticDiDResult" in sdid.__all__


# ── 2. fit() ────────────────────────────────────────────────────────────────


class TestSyntheticDiDFit:
    """Test SyntheticDiDEngine.fit()."""

    def test_fit_returns_result(self, sdid_data):
        """fit() returns SyntheticDiDResult with att."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        result = engine.fit()
        assert hasattr(result, "att")
        assert hasattr(result, "se")
        assert hasattr(result, "pval")

    def test_fit_estimator_name(self, sdid_data):
        """fit() result estimator is 'synthetic_did'."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        result = engine.fit()
        assert result.estimator == "synthetic_did"


# ── 3. get_att() ──────────────────────────────────────────────────────────


class TestATTGetter:
    """Test get_att()."""

    def test_get_att(self, sdid_data):
        """get_att() returns float ATT."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        att = engine.get_att()
        assert isinstance(att, float)


# ── 4. Placebo test ───────────────────────────────────────────────────────


class TestPlaceboTest:
    """Test placebo_test()."""

    def test_placebo_small_n(self, sdid_data):
        """placebo_test(n=5) returns dict with pseudo_atts."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        # Note: internal placebo_test() doesn't take n param; it uses all donors
        result = engine.placebo_test()
        assert isinstance(result, dict)
        assert "pseudo_atts" in result
        assert "pval" in result

    def test_placebo_has_rank(self, sdid_data):
        """placebo_test() returns dict with rank."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        result = engine.placebo_test()
        assert "rank" in result
        assert "n_placebos" in result


# ── 5. inference() jackknife ──────────────────────────────────────────────


class TestInference:
    """Test inference() methods."""

    def test_inference_jackknife(self, sdid_data):
        """inference(method='jackknife') updates result with SE/pval."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        result = engine.inference(method="jackknife")
        assert result.se > 0 or np.isnan(result.se)
        assert hasattr(result, "pval")

    def test_inference_conformal(self, sdid_data):
        """inference(method='conformal') returns result with CI."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        result = engine.inference(method="conformal")
        assert hasattr(result, "ci_lower")
        assert hasattr(result, "ci_upper")


# ── 6. get_donor_weights() ───────────────────────────────────────────────


class TestDonorWeights:
    """Test get_donor_weights()."""

    def test_get_donor_weights(self, sdid_data):
        """get_donor_weights() returns np.ndarray of length n_donor."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        weights = engine.get_donor_weights()
        assert isinstance(weights, np.ndarray)
        assert len(weights) == 10

    def test_weights_sum_to_one(self, sdid_data):
        """Donor weights sum approximately to 1."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        weights = engine.get_donor_weights()
        np.testing.assert_allclose(weights.sum(), 1.0, atol=1e-6)


# ── 7. plot() ─────────────────────────────────────────────────────────────


class TestPlotMethods:
    """Test plotting methods."""

    def test_plot_returns_figure_or_none(self, sdid_data):
        """plot() returns matplotlib Figure or None (no file saved)."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        fig = engine.plot()  # No save_path
        # Either returns Figure or None
        assert fig is None or hasattr(fig, "savefig")

    def test_plot_placebo(self, sdid_data):
        """plot_placebo() runs without error."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        fig = engine.plot_placebo()  # No save_path
        assert fig is None or hasattr(fig, "savefig")


# ── 8–9. summary() and to_latex() ───────────────────────────────────────


class TestSummaryAndLatex:
    """Test summary() DataFrame and to_latex()."""

    def test_summary_returns_dataframe(self, sdid_data):
        """summary() returns non-empty DataFrame."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        summary_df = engine.summary()
        assert isinstance(summary_df, pd.DataFrame)
        assert not summary_df.empty
        assert "ATT" in summary_df.columns

    def test_to_latex_returns_string(self, sdid_data):
        """to_latex() returns non-empty LaTeX string."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        latex_str = engine.to_latex()
        assert isinstance(latex_str, str)
        assert len(latex_str) > 0
        assert r"\begin{table}" in latex_str

    def test_summary_before_fit(self, sdid_data):
        """summary() calls fit() if not yet fitted."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        # Don't call fit() first
        summary_df = engine.summary()
        assert isinstance(summary_df, pd.DataFrame)


# ── 10. Aggregation modes ─────────────────────────────────────────────────


class TestAggregationModes:
    """Test different aggregation modes."""

    def test_aggregation_shrunken(self, sdid_data):
        """aggregation='shrunken' runs without error."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        result = engine.fit(aggregation="shrunken")
        assert result.estimator in ("synthetic_did", "sdid_shrunken")

    def test_aggregation_psid(self, sdid_data):
        """aggregation='psid' runs without error."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        result = engine.fit(aggregation="psid")
        assert result is not None

    def test_aggregation_cv(self, sdid_data):
        """aggregation='cv' (cross-validation) runs without error."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        result = engine.fit(aggregation="cv")
        assert result is not None


# ── 11. get_synthetic_control() ───────────────────────────────────────────


class TestGetSyntheticControl:
    """Test get_synthetic_control()."""

    def test_get_synthetic_control(self, sdid_data):
        """get_synthetic_control() returns (pre_synth, post_synth) tuples."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        synth_pre, synth_post = engine.get_synthetic_control()
        assert len(synth_pre) == 20
        assert len(synth_post) == 10


# ── 12. get_result() ──────────────────────────────────────────────────────


class TestGetResult:
    """Test get_result()."""

    def test_get_result(self, sdid_data):
        """get_result() returns SyntheticDiDResult or None."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=donor_pre,
            post_outcome_matrix=donor_post,
            treated_outcome_pre=treated_pre,
            treated_outcome_post=treated_post,
        )
        engine.fit()
        result = engine.get_result()
        assert result is not None
        assert hasattr(result, "att")


# ── 13. DataFrame input ───────────────────────────────────────────────────


class TestDataFrameInput:
    """Test that SyntheticDiDEngine accepts DataFrame inputs."""

    def test_pandas_dataframe_input(self, sdid_data):
        """Engine accepts pandas DataFrame for pre/post outcome matrices."""
        from scripts.research_framework.synthetic_did import SyntheticDiDEngine

        donor_pre, donor_post, treated_pre, treated_post = sdid_data

        # Convert to DataFrame
        pre_df = pd.DataFrame(
            donor_pre, columns=[f"t{i}" for i in range(donor_pre.shape[1])]
        )
        post_df = pd.DataFrame(
            donor_post, columns=[f"t{i}" for i in range(donor_post.shape[1])]
        )
        treated_pre_series = pd.Series(treated_pre)
        treated_post_series = pd.Series(treated_post)

        engine = SyntheticDiDEngine(
            pre_outcome_matrix=pre_df,
            post_outcome_matrix=post_df,
            treated_outcome_pre=treated_pre_series,
            treated_outcome_post=treated_post_series,
        )
        assert engine.n_donor == 10
        assert engine.n_pre == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
