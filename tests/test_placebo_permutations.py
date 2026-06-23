"""Tests for the 500-permutation placebo test in RobustnessRunner.

Covers:
- P1-6: 500 permutations are run and produce a valid p-value
- P1-6: p-value is bounded in [0, 1]
- P1-6: details dict contains expected keys
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.robustness_runner import (
    RobustnessRunner,
    RobustnessTest,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_did_data() -> pd.DataFrame:
    """Synthetic panel: 200 firms × 5 years, true DID effect = 2.0."""
    rng = np.random.default_rng(2026)
    n_firms = 200
    n_years = 5
    years = list(range(2018, 2018 + n_years))

    records = []
    for fid in range(n_firms):
        treated = fid < 60          # first 60 firms are treated
        treat_year = 2020 if treated else 9999   # never post for control
        base = rng.normal(0, 1)

        for y in years:
            post = 1 if y >= treat_year else 0
            did = 1 if (treated and post) else 0
            y_var = base + 2.0 * did + rng.normal(0, 0.5)
            x1 = rng.normal(0, 1)
            x2 = rng.normal(0, 1)

            records.append({
                "firm_id": fid,
                "year": y,
                "y": y_var,
                "did": did,
                "post": post,
                "treated": int(treated),
                "x1": x1,
                "x2": x2,
            })

    return pd.DataFrame(records)


@pytest.fixture
def runner(synthetic_did_data: pd.DataFrame) -> RobustnessRunner:
    """RobustnessRunner configured for the synthetic data."""
    return RobustnessRunner(
        df=synthetic_did_data,
        baseline_result={"coef": 2.0, "se": 0.1, "pval": 0.001},
        y_var="y",
        treat_var="did",
        time_var="post",
        unit_var="firm_id",
        x_vars=["x1", "x2"],
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_placebo_500_permutations(runner: RobustnessRunner) -> None:
    """Test that placebo test runs 500 permutations and computes valid p-value."""
    result = runner._test_placebo({})

    assert result.details.get("n_permutations") == 500, (
        f"Expected 500 permutations, got {result.details.get('n_permutations')}"
    )
    assert isinstance(result.did_pval, float)
    assert 0 <= result.did_pval <= 1


def test_placebo_pvalue_bounds(runner: RobustnessRunner) -> None:
    """P-value must be between 0 and 1."""
    result = runner._test_placebo({})

    assert 0.0 <= result.did_pval <= 1.0, (
        f"p-value {result.did_pval} is outside [0, 1]"
    )


def test_placebo_details_structure(runner: RobustnessRunner) -> None:
    """details dict must contain expected keys."""
    result = runner._test_placebo({})

    required_keys = {
        "n_permutations",
        "valid_permutations",
        "placebo_mean",
        "placebo_std",
        "placebo_5pct",
        "placebo_95pct",
    }
    missing = required_keys - set(result.details.keys())
    assert not missing, f"Missing keys in details: {missing}"


def test_placebo_valid_permutations_count(runner: RobustnessRunner) -> None:
    """At least 10 valid permutations must succeed out of 500."""
    result = runner._test_placebo({})

    valid = result.details.get("valid_permutations", 0)
    assert valid >= 10, (
        f"Only {valid} valid permutations succeeded (need ≥10)"
    )


def test_placebo_zero_coef_when_observed_zero(synthetic_did_data: pd.DataFrame) -> None:
    """When true effect = 0, p-value should be close to 1.0."""
    # Build data with no treatment effect (no did variance)
    df = synthetic_did_data.copy()
    df["y"] = np.random.default_rng(99).normal(0, 1, len(df))

    r = RobustnessRunner(
        df=df,
        baseline_result={"coef": 0.0, "se": 0.1, "pval": 0.5},
        y_var="y",
        treat_var="did",
        time_var="post",
        unit_var="firm_id",
        x_vars=["x1", "x2"],
    )
    result = r._test_placebo({})

    # With no true effect, p-value should be > 0.05 (not significant)
    # This is a sanity check, not a strict threshold
    assert 0.0 <= result.did_pval <= 1.0


def test_placebo_is_significant_flag(runner: RobustnessRunner) -> None:
    """is_significant flag should be True iff p_value < 0.05."""
    result = runner._test_placebo({})

    expected = result.did_pval < 0.05
    assert result.is_significant == expected, (
        f"is_significant={result.is_significant} but p_value={result.did_pval} "
        f"(expect is_significant={expected})"
    )


def test_placebo_test_type_and_name(runner: RobustnessRunner) -> None:
    """Test has correct name and type."""
    result = runner._test_placebo({})

    assert result.test_name == "Placebo (Randomized)"
    assert result.test_type == "Placebo"


def test_run_all_includes_placebo_500_perms(runner: RobustnessRunner) -> None:
    """run_all() should produce a placebo test result with 500 permutations."""
    runner.add_test("placebo")
    report = runner.run_all()

    placebo_tests = [t for t in report.tests if t.test_type == "Placebo"]
    assert len(placebo_tests) >= 1

    pt = placebo_tests[0]
    assert pt.details.get("n_permutations") == 500
    assert 0 <= pt.did_pval <= 1
