"""Tests for mediation_test.py — Baron-Kenny / Sobel / Bootstrap CI / Joint Significance."""

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.mediation_test import MediationTest, MediationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mediation_data():
    """
    Simulated data where:
      x -> m: a = 0.5
      m -> y: b = 0.3
      x -> y (direct): 0.5
    Therefore indirect effect = 0.5 * 0.3 = 0.15
    """
    np.random.seed(42)
    n = 500
    x = np.random.randn(n)
    m = 0.5 * x + np.random.randn(n) * 0.5
    y = 0.3 * m + 0.5 * x + np.random.randn(n) * 0.5
    return pd.DataFrame({"x": x, "m": m, "y": y})


@pytest.fixture
def no_mediation_data():
    """
    Simulated data where m does NOT affect y (b = 0).
    Indirect effect should be approximately zero.
    """
    np.random.seed(123)
    n = 300
    x = np.random.randn(n)
    m = 0.5 * x + np.random.randn(n) * 0.5
    y = 0.5 * x + np.random.randn(n) * 0.5  # direct effect only
    return pd.DataFrame({"x": x, "m": m, "y": y})


# ---------------------------------------------------------------------------
# Test: Sobel — basic indirect effect detection
# ---------------------------------------------------------------------------

def test_sobel_basic(mediation_data):
    """Sobel should detect a positive indirect effect of ~0.15."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.sobel()

    assert isinstance(result, MediationResult)
    assert result.method == "Sobel"
    assert result.indirect_effect > 0
    assert abs(result.indirect_effect - 0.15) < 0.08
    assert result.indirect_se is not None
    assert 0 < result.indirect_pvalue < 1
    assert "Sobel" in result.conclusions


# ---------------------------------------------------------------------------
# Test: Bootstrap CI
# ---------------------------------------------------------------------------

def test_bootstrap_ci(mediation_data):
    """Bootstrap CI should NOT cover zero when a true indirect effect exists."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.bootstrap_ci(n_bootstrap=2000, seed=42)

    assert isinstance(result, MediationResult)
    assert result.method == "Bootstrap CI"
    assert result.n_bootstrap == 2000
    assert result.ci_lower is not None
    assert result.ci_upper is not None
    # CI should be entirely positive (or entirely negative) when effect is real
    assert result.ci_lower > 0 or result.ci_upper < 0, \
        "Bootstrap CI should exclude zero for a true indirect effect"
    assert result.conclusions["Bootstrap"] is True


def test_bootstrap_ci_no_effect(no_mediation_data):
    """Bootstrap CI should cover zero when there is no indirect effect."""
    mt = MediationTest(no_mediation_data, "x", "y", "m")
    result = mt.bootstrap_ci(n_bootstrap=2000, seed=99)

    # With no true effect, CI should contain zero (or be very close)
    assert result.ci_lower <= 0 <= result.ci_upper or abs(result.indirect_effect) < 0.03


# ---------------------------------------------------------------------------
# Test: Baron-Kenny conclusions
# ---------------------------------------------------------------------------

def test_baron_kenny_conclusions(mediation_data):
    """Baron-Kenny should classify mediation as present when paths are significant."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.baron_kenny()

    assert isinstance(result, MediationResult)
    assert result.method == "Baron-Kenny"
    assert result.alpha != 0, "Total effect should be non-zero"
    assert result.indirect_effect != 0
    assert "Baron-Kenny" in result.conclusions


def test_baron_kenny_no_mediation(no_mediation_data):
    """When M does not affect Y, Baron-Kenny should not support mediation."""
    mt = MediationTest(no_mediation_data, "x", "y", "m")
    result = mt.baron_kenny()

    # gamma (path b) should be near zero
    assert abs(result.gamma) < 0.05


# ---------------------------------------------------------------------------
# Test: run_all returns all four methods
# ---------------------------------------------------------------------------

def test_run_all_returns_all_methods(mediation_data):
    """run_all() should return results for all four methods."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    results = mt.run_all(n_bootstrap=1000)

    assert set(results.keys()) == {
        "Baron-Kenny",
        "Sobel",
        "Bootstrap CI",
        "Joint Significance",
    }
    for name, r in results.items():
        assert isinstance(r, MediationResult)
        assert r.method == name
        assert r.indirect_effect is not None


# ---------------------------------------------------------------------------
# Test: no-mediation case — indirect effect near zero
# ---------------------------------------------------------------------------

def test_no_mediation_case(no_mediation_data):
    """When M has no effect on Y, indirect effect should be near zero."""
    mt = MediationTest(no_mediation_data, "x", "y", "m")
    result = mt.sobel()

    assert abs(result.indirect_effect) < 0.05, \
        "Indirect effect should be near zero when m does not affect y"


# ---------------------------------------------------------------------------
# Test: summary output is readable
# ---------------------------------------------------------------------------

def test_summary_output(mediation_data):
    """summary() should produce non-empty, readable text."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.sobel()
    summary = result.summary()

    assert isinstance(summary, str)
    assert len(summary) > 50
    assert "Mediation Analysis" in summary
    assert "Indirect Effect" in summary
    assert "Sobel" in summary


# ---------------------------------------------------------------------------
# Test: is_significant helper
# ---------------------------------------------------------------------------

def test_is_significant_helper(mediation_data):
    """is_significant() should return True for Sobel when indirect is real."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.sobel()

    assert result.is_significant("Sobel") is True
    assert result.is_significant(method="unknown_method", alpha_level=0.05) is False


# ---------------------------------------------------------------------------
# Test: proportion_mediated bounds
# ---------------------------------------------------------------------------

def test_proportion_mediated_valid(mediation_data):
    """proportion_mediated should be between 0 and 1 (or None) for valid mediation."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.sobel()

    if result.proportion_mediated is not None:
        assert 0 <= result.proportion_mediated <= 1


# ---------------------------------------------------------------------------
# Test: joint significance test
# ---------------------------------------------------------------------------

def test_joint_significance_method(mediation_data):
    """Joint Significance should detect both a and b paths as significant."""
    mt = MediationTest(mediation_data, "x", "y", "m")
    result = mt.joint_significance_test()

    assert isinstance(result, MediationResult)
    assert result.method == "Joint Significance"
    assert "Joint Sig" in result.conclusions
    assert result.indirect_effect is not None


# ---------------------------------------------------------------------------
# Test: clustered bootstrap (edge case)
# ---------------------------------------------------------------------------

def test_clustered_bootstrap(mediation_data):
    """Clustered bootstrap should run without error."""
    df = mediation_data.copy()
    # Assign fake cluster IDs
    df["cluster"] = (df.index // 10).astype(str)
    mt = MediationTest(df, "x", "y", "m", cluster_var="cluster")
    result = mt.bootstrap_ci(n_bootstrap=500, seed=42)

    assert result.ci_lower is not None
    assert result.ci_upper is not None
    assert result.n_bootstrap == 500
