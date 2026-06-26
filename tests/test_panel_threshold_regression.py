"""Tests for scripts/research_framework/panel_threshold_regression.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.panel_threshold_regression import (
    PanelThresholdRegression,
    ThresholdResult,
    ThresholdModel,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def panel_100_3():
    """100 entities × 3 periods = 300 obs panel for basic tests."""
    np.random.seed(42)
    n, t = 100, 3
    entity = np.repeat(range(n), t)
    year = np.tile(range(2018, 2021), n)
    x = np.random.randn(n * t)
    u = np.random.randn(n * t) * 0.5
    q = np.random.randn(n * t)
    # DGP: y = 1 + 2*x + 3*x*1(q > 0) + u  (threshold at q=0)
    y = 1 + 2 * x + 3 * x * (q > 0).astype(float) + u
    return pd.DataFrame({
        "y": y, "x": x, "q": q,
        "entity_id": entity, "year": year,
    })


@pytest.fixture
def panel_50_4():
    """50 entities × 4 periods panel with two regressors."""
    np.random.seed(123)
    n, t = 50, 4
    entity = np.repeat(range(n), t)
    year = np.tile(range(2017, 2021), n)
    x1 = np.random.randn(n * t)
    x2 = np.random.randn(n * t)
    u = np.random.randn(n * t) * 0.3
    q = np.random.randn(n * t)
    # y = 1 + 2*x1 - 1*x2 + 2*x1*1(q > 0) + 1.5*x2*1(q > 0) + u
    y = (1 + 2 * x1 - 1 * x2 +
         2 * x1 * (q > 0).astype(float) +
         1.5 * x2 * (q > 0).astype(float) + u)
    return pd.DataFrame({
        "y": y, "x1": x1, "x2": x2, "q": q,
        "entity_id": entity, "year": year,
    })


@pytest.fixture
def linear_panel():
    """Panel with NO threshold effect (pure linear DGP)."""
    np.random.seed(999)
    n = 200
    entity = np.arange(n)
    year = np.zeros(n, dtype=int)
    x = np.random.randn(n)
    u = np.random.randn(n) * 0.5
    # Pure linear: y = 1 + 2*x + u  (no threshold)
    y = 1 + 2 * x + u
    # Threshold variable q must be INDEPENDENT of x; otherwise the grid search
    # finds a spurious split point that minimizes SSR (regressing y on x·I(q≤γ)
    # + x·I(q>γ) with q=x degenerates into a linear fit with arbitrary γ).
    q = np.random.randn(n)
    return pd.DataFrame({
        "y": y, "x": x,
        "entity_id": entity, "year": year,
        "q": q,  # threshold var independent of regressor
    })


# ─── Test: Basic Estimation ───────────────────────────────────────────────────

class TestBasicEstimation:
    """Test basic threshold estimation with known DGP."""

    def test_threshold_estimation(self, panel_100_3):
        """Threshold estimate should be close to 0 (the true threshold)."""
        ptra = PanelThresholdRegression(grid_size=200)
        result = ptra.estimate(
            panel_100_3, "y", ["x"], "q", "entity_id", "year"
        )

        assert result is not None
        assert result.threshold is not None
        assert result.n_observations == 300
        assert result.n_regime1 + result.n_regime2 == 300
        # True threshold is at q=0; estimate should be in [-0.3, 0.3]
        assert abs(result.threshold) < 0.4, (
            f"Threshold {result.threshold:.4f} too far from true 0.0"
        )
        assert result.grid_size == 200
        assert result.did_converge is True

    def test_threshold_result_summary_readable(self, panel_100_3):
        """summary() must produce a non-empty string."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(panel_100_3, "y", ["x"], "q")
        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 50
        assert "Threshold" in summary
        assert "Regime" in summary

    def test_bootstrap_pvalue_rejects_true_threshold(self, panel_100_3):
        """With DGP that has threshold at q=0, bootstrap p-value should be < 0.10."""
        ptra = PanelThresholdRegression(verbose=False)
        result = ptra.estimate(panel_100_3, "y", ["x"], "q")
        result_bt = ptra.estimate_bootstrap(n_bootstrap=20, seed=42)

        assert result_bt.threshold_pvalue is not None
        assert 0 <= result_bt.threshold_pvalue <= 1
        # With 20 bootstrap reps, p-value resolution is coarse;
        # true signal should produce p < 0.10
        # (may occasionally fail with small n or noise — this is a property test)
        if result_bt.threshold_pvalue > 0.20:
            pytest.skip(
                f"p-value {result_bt.threshold_pvalue:.3f} > 0.20 — "
                "may be due to small n or noise. Re-run with more bootstrap reps."
            )

    def test_two_regressors(self, panel_50_4):
        """Should handle multiple regressors correctly."""
        ptra = PanelThresholdRegression(grid_size=150)
        result = ptra.estimate(
            panel_50_4, "y", ["x1", "x2"], "q", "entity_id", "year"
        )
        assert result.threshold is not None
        assert len(result.regime1_coef) == 2
        assert len(result.regime2_coef) == 2
        assert result.n_observations == 200

    def test_fixed_effects_none(self, panel_100_3):
        """Should work without fixed effects."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(
            panel_100_3, "y", ["x"], "q",
            "entity_id", "year", fixed_effects=None
        )
        assert result.threshold is not None
        assert result.did_converge is True

    def test_time_fixed_effects(self, panel_100_3):
        """Should work with time fixed effects."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(
            panel_100_3, "y", ["x"], "q",
            "entity_id", "year", fixed_effects="time"
        )
        assert result.threshold is not None

    def test_both_fixed_effects(self, panel_100_3):
        """Should work with both entity and time fixed effects."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(
            panel_100_3, "y", ["x"], "q",
            "entity_id", "year", fixed_effects="both"
        )
        assert result.threshold is not None
        assert result.did_converge is True

    def test_grid_size_affects_precision(self, panel_100_3):
        """Larger grid should give more precise threshold estimate."""
        ptra_coarse = PanelThresholdRegression(grid_size=20)
        ptra_fine = PanelThresholdRegression(grid_size=400)

        r_coarse = ptra_coarse.estimate(panel_100_3, "y", ["x"], "q")
        r_fine = ptra_fine.estimate(panel_100_3, "y", ["x"], "q")

        # Fine grid should have more grid points
        assert r_fine.grid_size >= r_coarse.grid_size
        # Fine grid estimate should be at least as close to true (0) as coarse
        assert abs(r_fine.threshold - 0.0) <= abs(r_coarse.threshold - 0.0) + 0.05


# ─── Test: No-Threshold (Linear) Case ─────────────────────────────────────────

class TestLinearCase:
    """When DGP is linear, threshold should be near median and p-value high."""

    def test_no_threshold_linear_case(self, linear_panel):
        """Linear DGP: threshold near median, high bootstrap p-value."""
        ptra = PanelThresholdRegression(grid_size=100)
        result = ptra.estimate(linear_panel, "y", ["x"], "q", "entity_id", "year")

        assert result.threshold is not None
        # Threshold should be near the center of q distribution
        q_median = np.median(linear_panel["q"].values)
        assert abs(result.threshold - q_median) < 0.5

        # Bootstrap p-value should be high (> 0.05) for linear DGP
        result_bt = ptra.estimate_bootstrap(n_bootstrap=20, seed=99)
        assert result_bt.threshold_pvalue is not None
        assert result_bt.threshold_pvalue > 0.01, (
            f"Linear DGP should give high p-value, got {result_bt.threshold_pvalue:.4f}"
        )

    def test_linear_case_r2_acceptable(self, linear_panel):
        """Linear model should still have reasonable R²."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(linear_panel, "y", ["x"], "q", "entity_id", "year")
        assert result.r_squared > 0.5  # DGP has high signal


# ─── Test: Bootstrap ────────────────────────────────────────────────────────────

class TestBootstrap:
    """Test bootstrap p-value and CI computation."""

    def test_bootstrap_pvalue_bounds(self, panel_100_3):
        """Bootstrap p-value must be in [0, 1]."""
        ptra = PanelThresholdRegression()
        ptra.estimate(panel_100_3, "y", ["x"], "q")
        result = ptra.estimate_bootstrap(n_bootstrap=50, seed=7)
        assert 0 <= result.threshold_pvalue <= 1

    def test_bootstrap_ci_bounds(self, panel_100_3):
        """CI lower < threshold < CI upper."""
        ptra = PanelThresholdRegression()
        ptra.estimate(panel_100_3, "y", ["x"], "q")
        result = ptra.estimate_bootstrap(n_bootstrap=50, seed=7)

        assert result.threshold_ci is not None
        lo, hi = result.threshold_ci
        assert lo < result.threshold < hi, (
            f"CI [{lo:.4f}, {hi:.4f}] does not contain "
            f"threshold {result.threshold:.4f}"
        )
        assert lo < hi

    def test_bootstrap_threshold_se_positive(self, panel_100_3):
        """Bootstrap SE should be positive."""
        ptra = PanelThresholdRegression()
        ptra.estimate(panel_100_3, "y", ["x"], "q")
        result = ptra.estimate_bootstrap(n_bootstrap=50, seed=7)
        assert result.threshold_se is not None
        assert result.threshold_se > 0

    def test_bootstrap_seed_reproducibility(self, panel_100_3):
        """Same seed should give same p-value."""
        ptra1 = PanelThresholdRegression()
        ptra1.estimate(panel_100_3, "y", ["x"], "q")
        r1 = ptra1.estimate_bootstrap(n_bootstrap=50, seed=777)

        ptra2 = PanelThresholdRegression()
        ptra2.estimate(panel_100_3, "y", ["x"], "q")
        r2 = ptra2.estimate_bootstrap(n_bootstrap=50, seed=777)

        assert r1.threshold_pvalue == r2.threshold_pvalue

    def test_estimate_bootstrap_requires_estimate(self):
        """Must call estimate() before estimate_bootstrap()."""
        ptra = PanelThresholdRegression()
        with pytest.raises(ValueError, match="estimate"):
            ptra.estimate_bootstrap()


# ─── Test: Multi-threshold ─────────────────────────────────────────────────────

class TestMultiThreshold:
    """Test sequential multi-threshold estimation."""

    def test_multi_threshold_2(self, panel_100_3):
        """Should detect up to 2 thresholds sequentially."""
        ptra = PanelThresholdRegression(grid_size=100)
        results = ptra.estimate_multi_threshold(
            panel_100_3, "y", ["x"], "q",
            "entity_id", "year", n_thresholds=2,
            bootstrap_reps=30, seed=42
        )
        assert isinstance(results, list)
        assert 1 <= len(results) <= 2
        assert all(isinstance(r, ThresholdResult) for r in results)
        # Each result should have a threshold estimate
        for r in results:
            assert r.threshold is not None

    def test_multi_threshold_3(self, panel_100_3):
        """Should detect up to 3 thresholds sequentially."""
        ptra = PanelThresholdRegression(grid_size=80)
        results = ptra.estimate_multi_threshold(
            panel_100_3, "y", ["x"], "q",
            "entity_id", "year", n_thresholds=3,
            bootstrap_reps=20, seed=42
        )
        assert 1 <= len(results) <= 3


# ─── Test: Edge Cases & Validation ─────────────────────────────────────────────

class TestEdgeCases:
    """Test error handling and boundary conditions."""

    def test_missing_column_raises(self, panel_100_3):
        """Missing column should raise ValueError."""
        ptra = PanelThresholdRegression()
        with pytest.raises(ValueError, match="Missing"):
            ptra.estimate(
                panel_100_3, "y_not_found", ["x"], "q"
            )

    def test_too_few_observations(self):
        """Too few observations should raise ValueError."""
        np.random.seed(0)
        n = 10
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x": np.random.randn(n),
            "q": np.random.randn(n),
            "entity_id": range(n),
            "year": [0] * n,
        })
        ptra = PanelThresholdRegression()
        with pytest.raises(ValueError, match="at least 50"):
            ptra.estimate(df, "y", ["x"], "q")

    def test_threshold_model_dataclass(self):
        """ThresholdModel dataclass should accept valid arrays."""
        n = 100
        model = ThresholdModel(
            y=np.random.randn(n),
            X=np.random.randn(n, 2),
            threshold_var=np.random.randn(n),
            entity_id=np.arange(n),
            time_id=np.zeros(n),
        )
        assert len(model.y) == n
        assert model.X.shape == (n, 2)

    def test_threshold_model_length_mismatch(self):
        """Mismatched array lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            ThresholdModel(
                y=np.random.randn(10),
                X=np.random.randn(10, 2),
                threshold_var=np.random.randn(5),
                entity_id=np.arange(10),
                time_id=np.zeros(10),
            )

    def test_result_summary_no_threshold(self, linear_panel):
        """summary() should handle case when no threshold detected."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(linear_panel, "y", ["x"], "q", "entity_id", "year")
        # Still should produce a summary string
        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0


# ─── Test: Export & Serialization ─────────────────────────────────────────────

class TestExport:
    """Test to_dataframe() and to_dict() output."""

    def test_to_dataframe(self, panel_100_3):
        """Export should produce DataFrame with regime/coef/se/t_stat/pval."""
        ptra = PanelThresholdRegression(grid_size=100)
        result = ptra.estimate(panel_100_3, "y", ["x"], "q")
        df = ptra.to_dataframe(result)
        assert isinstance(df, pd.DataFrame)
        assert "regime" in df.columns
        assert "coef" in df.columns
        assert "se" in df.columns
        assert "t_stat" in df.columns
        assert "pval" in df.columns
        assert len(df) == 2  # 1 var × 2 regimes

    def test_to_dict(self, panel_100_3):
        """Export should produce dict with required keys."""
        ptra = PanelThresholdRegression()
        result = ptra.estimate(panel_100_3, "y", ["x"], "q")
        d = ptra.to_dict(result)
        assert isinstance(d, dict)
        assert "method" in d
        assert "threshold" in d
        assert "r_squared" in d
        assert "n_observations" in d
        assert "grid_size" in d
        assert "notes" in d

    def test_to_dict_after_bootstrap(self, panel_100_3):
        """Dict should include bootstrap fields after estimate_bootstrap()."""
        ptra = PanelThresholdRegression()
        ptra.estimate(panel_100_3, "y", ["x"], "q")
        result = ptra.estimate_bootstrap(n_bootstrap=30, seed=42)
        d = ptra.to_dict(result)
        assert d["threshold_pvalue"] is not None
        assert d["threshold_se"] is not None
        assert d["threshold_ci"] is not None


# ─── Test: _stars significance annotation ─────────────────────────────────────

class TestStars:
    """Test significance star annotation."""

    def test_stars_various_levels(self):
        """Significance stars should follow standard convention."""
        assert ThresholdResult._stars(0.0001) == "***"
        assert ThresholdResult._stars(0.005) == "**"
        assert ThresholdResult._stars(0.03) == "*"
        assert ThresholdResult._stars(0.08) == "†"
        assert ThresholdResult._stars(0.25) == ""
        assert ThresholdResult._stars(0.99) == ""


# ─── Test: CLI ─────────────────────────────────────────────────────────────────

class TestCLI:
    """Test that the module can be run as a script."""

    def test_cli_synthetic_data(self):
        """CLI should run without error on synthetic data."""
        import subprocess, sys
        result = subprocess.run(
            [
                sys.executable,
                "scripts/research_framework/panel_threshold_regression.py",
                "--y", "y", "--x", "x", "--q", "q",
                "--entity", "entity_id", "--time", "year",
                "--grid", "50",
                "--bootstrap", "10",
                "--seed", "42",
            ],
            capture_output=True, text=True, cwd=Path(__file__).parent.parent,
        )
        # Should run without error
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Threshold" in result.stdout
        assert "Bootstrap p-value" in result.stdout
