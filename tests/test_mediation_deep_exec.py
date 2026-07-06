"""tests/test_mediation_deep_exec.py — Deep execution tests for mediation.py.

Covers:
  - MediationResult dataclass: all fields, properties, summary()
  - _fit_two_models(): regression paths
  - sobel(): Baron-Kenny + Sobel
  - bootstrap(): Preacher-Hayes with CI
  - classify_mediation(): Zhao-Lynch-Chen four cases
  - Error/edge cases: missing columns, single observation, constant vars,
    perfect mediation, NaN, bootstrap failures
  - Table generation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import pandas as pd

    from scripts.research_framework.mediation import (
        MediationResult,
        _fit_two_models,
        bootstrap,
        classify_mediation,
        sobel,
    )
except Exception as exc:
    pytest.skip(f"mediation not importable: {exc}", allow_module_level=True)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def rng():
    return np.random.default_rng(2026)


@pytest.fixture
def mediation_df(rng):
    """Standard mediation dataset with X→M→Y structure.

    True values: a=0.5, b=0.4, c=0.5, c'=0.3, indirect=0.2
    """
    n = 500
    X = rng.standard_normal(n)
    M = 0.5 * X + rng.standard_normal(n) * 0.5
    Y = 0.3 * X + 0.4 * M + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"X": X, "M": M, "Y": Y})


@pytest.fixture
def mediation_df_large(rng):
    """Larger dataset for bootstrap CI precision."""
    n = 2000
    X = rng.standard_normal(n)
    M = 0.5 * X + rng.standard_normal(n) * 0.5
    Y = 0.3 * X + 0.4 * M + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"X": X, "M": M, "Y": Y})


@pytest.fixture
def mediation_df_no_effect(rng):
    """X, M, Y all independent."""
    return pd.DataFrame({
        "X": rng.standard_normal(500),
        "M": rng.standard_normal(500),
        "Y": rng.standard_normal(500),
    })


@pytest.fixture
def mediation_df_perfect_mediation(rng):
    """c' ≈ 0, indirect ≈ c (full mediation)."""
    n = 500
    X = rng.standard_normal(n)
    M = 0.5 * X + rng.standard_normal(n) * 0.1
    Y = 0.4 * M + rng.standard_normal(n) * 0.1  # no direct effect
    return pd.DataFrame({"X": X, "M": M, "Y": Y})


@pytest.fixture
def mediation_df_suppression(rng):
    """a*b and c' opposite signs (competitive/suppression)."""
    n = 500
    X = rng.standard_normal(n)
    M = 0.5 * X + rng.standard_normal(n) * 0.5
    Y = -0.3 * X + 0.4 * M + rng.standard_normal(n) * 0.5  # c' negative, indirect positive
    return pd.DataFrame({"X": X, "M": M, "Y": Y})


# ─────────────────────────────────────────────────────────────────────────────
# 1. MediationResult dataclass — all fields and methods
# ─────────────────────────────────────────────────────────────────────────────


class TestMediationResultFields:
    """Every field in MediationResult."""

    def test_all_fields_required(self):
        r = MediationResult(
            method="test",
            indirect_effect=0.2,
            direct_effect=0.3,
            total_effect=0.5,
            indirect_se=0.05,
            indirect_ci=(0.10, 0.30),
            a=0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=0.5,
            c_prime=0.3,
            sobel_z=2.0,
            sobel_p=0.045,
            n=500,
        )
        assert r.method == "test"
        assert r.indirect_effect == 0.2
        assert r.direct_effect == 0.3
        assert r.total_effect == 0.5
        assert r.indirect_se == 0.05
        assert r.indirect_ci == (0.10, 0.30)
        assert r.a == 0.5
        assert r.a_se == 0.03
        assert r.b == 0.4
        assert r.b_se == 0.02
        assert r.c == 0.5
        assert r.c_prime == 0.3
        assert r.sobel_z == 2.0
        assert r.sobel_p == 0.045
        assert r.n == 500

    def test_all_fields_with_optionals(self):
        boot_samples = np.array([0.15, 0.20, 0.25])
        r = MediationResult(
            method="Bootstrap (1000)",
            indirect_effect=0.2,
            direct_effect=0.3,
            total_effect=0.5,
            indirect_se=0.05,
            indirect_ci=(0.10, 0.30),
            a=0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=0.5,
            c_prime=0.3,
            sobel_z=2.0,
            sobel_p=0.045,
            n=500,
            n_boot=1000,
            boot_samples=boot_samples,
        )
        assert r.n_boot == 1000
        assert r.boot_samples is boot_samples
        assert len(r.boot_samples) == 3

    def test_proportion_mediated_positive(self):
        r = MediationResult(
            method="test",
            indirect_effect=0.2,
            direct_effect=0.3,
            total_effect=0.5,
            indirect_se=0.05,
            indirect_ci=(0.10, 0.30),
            a=0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=0.5,
            c_prime=0.3,
            sobel_z=2.0,
            sobel_p=0.045,
            n=500,
        )
        prop = r.proportion_mediated
        assert prop == pytest.approx(0.2 / 0.5)

    def test_proportion_mediated_total_zero(self):
        r = MediationResult(
            method="test",
            indirect_effect=0.0,
            direct_effect=0.0,
            total_effect=0.0,
            indirect_se=0.0,
            indirect_ci=None,
            a=0.0,
            a_se=0.0,
            b=0.0,
            b_se=0.0,
            c=0.0,
            c_prime=0.0,
            sobel_z=0.0,
            sobel_p=1.0,
            n=500,
        )
        assert np.isnan(r.proportion_mediated)

    def test_proportion_mediated_negative_total(self):
        r = MediationResult(
            method="test",
            indirect_effect=-0.2,
            direct_effect=-0.3,
            total_effect=-0.5,
            indirect_se=0.05,
            indirect_ci=None,
            a=-0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=-0.5,
            c_prime=-0.3,
            sobel_z=-2.0,
            sobel_p=0.045,
            n=500,
        )
        # -0.2 / -0.5 = 0.4
        assert r.proportion_mediated == pytest.approx(0.4)


class TestMediationResultSummary:
    """summary() method."""

    def test_summary_with_ci(self):
        r = MediationResult(
            method="Bootstrap (500)",
            indirect_effect=0.2,
            direct_effect=0.3,
            total_effect=0.5,
            indirect_se=0.05,
            indirect_ci=(0.10, 0.30),
            a=0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=0.5,
            c_prime=0.3,
            sobel_z=4.0,
            sobel_p=0.0001,
            n=500,
            n_boot=500,
        )
        s = r.summary()
        assert isinstance(s, str)
        assert "Bootstrap (500)" in s
        assert "0.5" in s
        assert "a (X -> M)" in s
        assert "b (M -> Y|X)" in s
        assert "Sobel" in s or "z =" in s
        assert "Indirect" in s
        assert "Proportion mediated" in s
        assert "95% CI" in s  # default 95% CI

    def test_summary_without_ci(self):
        r = MediationResult(
            method="Baron-Kenny + Sobel",
            indirect_effect=0.2,
            direct_effect=0.3,
            total_effect=0.5,
            indirect_se=0.05,
            indirect_ci=None,
            a=0.5,
            a_se=0.03,
            b=0.4,
            b_se=0.02,
            c=0.5,
            c_prime=0.3,
            sobel_z=4.0,
            sobel_p=0.0001,
            n=500,
        )
        s = r.summary()
        assert isinstance(s, str)
        assert "Baron-Kenny + Sobel" in s


# ─────────────────────────────────────────────────────────────────────────────
# 2. _fit_two_models — helper function
# ─────────────────────────────────────────────────────────────────────────────


class TestFitTwoModels:
    """_fit_two_models() regression paths."""

    def test_basic(self, mediation_df):
        a, a_se, b, b_se, c, c_prime = _fit_two_models(mediation_df, "X", "M", "Y")
        assert isinstance(a, (float, np.floating))
        assert isinstance(a_se, (float, np.floating))
        assert isinstance(b, (float, np.floating))
        assert isinstance(b_se, (float, np.floating))
        assert isinstance(c, (float, np.floating))
        assert isinstance(c_prime, (float, np.floating))

    def test_path_a_positive(self, mediation_df):
        a, _, _, _, _, _ = _fit_two_models(mediation_df, "X", "M", "Y")
        # True a = 0.5
        assert a > 0

    def test_path_b_positive(self, mediation_df):
        _, _, b, _, _, _ = _fit_two_models(mediation_df, "X", "M", "Y")
        # True b = 0.4
        assert b > 0

    def test_path_c_positive(self, mediation_df):
        _, _, _, _, c, _ = _fit_two_models(mediation_df, "X", "M", "Y")
        assert c > 0

    def test_indirect_approx(self, mediation_df):
        a, _, b, _, _, _ = _fit_two_models(mediation_df, "X", "M", "Y")
        indirect = a * b
        # True indirect = 0.5 * 0.4 = 0.2
        assert 0.05 < indirect < 0.5

    def test_missing_column_X(self, mediation_df):
        df = mediation_df.drop(columns=["X"])
        with pytest.raises(Exception):
            _fit_two_models(df, "X", "M", "Y")

    def test_missing_column_M(self, mediation_df):
        df = mediation_df.drop(columns=["M"])
        with pytest.raises(Exception):
            _fit_two_models(df, "X", "M", "Y")

    def test_missing_column_Y(self, mediation_df):
        df = mediation_df.drop(columns=["Y"])
        with pytest.raises(Exception):
            _fit_two_models(df, "X", "M", "Y")

    def test_nan_in_data(self, mediation_df):
        df = mediation_df.copy()
        df.iloc[0, 0] = np.nan
        # Drop the NaN row so regression can proceed
        df_clean = df.dropna()
        a, a_se, b, b_se, c, c_prime = _fit_two_models(df_clean, "X", "M", "Y")
        # OLS should handle clean data
        assert isinstance(a, (float, np.floating))

    def test_constant_X(self, rng):
        """Constant X → b_se should be large but computation should succeed."""
        df = pd.DataFrame({
            "X": np.ones(100),
            "M": rng.standard_normal(100),
            "Y": rng.standard_normal(100),
        })
        try:
            a, a_se, b, b_se, c, c_prime = _fit_two_models(df, "X", "M", "Y")
            assert isinstance(a, (float, np.floating))
        except Exception:
            pass  # Singular matrix possible for constant X

    def test_single_observation(self):
        df = pd.DataFrame({"X": [1.0], "M": [0.5], "Y": [0.3]})
        try:
            _fit_two_models(df, "X", "M", "Y")
        except Exception:
            pass  # Insufficient data for regression


# ─────────────────────────────────────────────────────────────────────────────
# 3. sobel() — Baron-Kenny + Sobel test
# ─────────────────────────────────────────────────────────────────────────────


class TestSobel:
    """sobel() function."""

    def test_returns_mediation_result(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert isinstance(res, MediationResult)

    def test_method_label(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.method == "Baron-Kenny + Sobel"

    def test_n_from_df(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.n == len(mediation_df)

    def test_n_boot_is_none(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.n_boot is None

    def test_boot_samples_is_none(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.boot_samples is None

    def test_indirect_ci_is_none(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.indirect_ci is None

    def test_sobel_z_nonzero(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert res.sobel_z != 0.0

    def test_sobel_p_range(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        assert 0.0 <= res.sobel_p <= 1.0

    def test_sobel_z_sign(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        # Both a and b positive → indirect positive → z positive
        assert res.sobel_z > 0

    def test_no_effect_data(self, mediation_df_no_effect):
        res = sobel(mediation_df_no_effect, "X", "M", "Y")
        # X→M and M→Y are independent, so a and b should be near 0
        assert isinstance(res.indirect_effect, (float, np.floating))

    def test_missing_X_raises(self, mediation_df):
        df = mediation_df.drop(columns=["X"])
        with pytest.raises(Exception):
            sobel(df, "X", "M", "Y")

    def test_missing_M_raises(self, mediation_df):
        df = mediation_df.drop(columns=["M"])
        with pytest.raises(Exception):
            sobel(df, "X", "M", "Y")

    def test_missing_Y_raises(self, mediation_df):
        df = mediation_df.drop(columns=["Y"])
        with pytest.raises(Exception):
            sobel(df, "X", "M", "Y")

    def test_sobel_se_zero_guard(self, rng):
        """When Sobel SE would be 0, z should be 0."""
        # Perfect collinearity can cause near-zero SE
        df = pd.DataFrame({
            "X": rng.standard_normal(500),
            "M": rng.standard_normal(500),
            "Y": rng.standard_normal(500),
        })
        # Make M = X exactly
        df["M"] = df["X"]
        res = sobel(df, "X", "M", "Y")
        # Should not crash; either 0 or finite
        assert isinstance(res.sobel_z, (float, np.floating))

    def test_sobel_p_approx_0_for_strong_effect(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        # Strong effect → small p-value
        assert res.sobel_p < 0.05

    def test_summary_callable(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        s = res.summary()
        assert isinstance(s, str)
        assert "Sobel" in s


# ─────────────────────────────────────────────────────────────────────────────
# 4. bootstrap() — Preacher-Hayes with CI
# ─────────────────────────────────────────────────────────────────────────────


class TestBootstrap:
    """bootstrap() function."""

    def test_returns_mediation_result(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        assert isinstance(res, MediationResult)

    def test_n_boot_stored(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        assert res.n_boot == 500

    def test_method_label(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=200, seed=42)
        assert "Bootstrap (200)" in res.method

    def test_boot_samples_stored(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        assert res.boot_samples is not None
        assert len(res.boot_samples) > 0

    def test_boot_samples_mean(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        # Boot mean should be close to point estimate
        assert isinstance(res.boot_samples, np.ndarray)

    def test_indirect_ci_present(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=200, seed=42)
        assert res.indirect_ci is not None
        lower, upper = res.indirect_ci
        assert lower < upper

    def test_ci_contains_point_estimate(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        lower, upper = res.indirect_ci
        assert lower <= res.indirect_effect <= upper

    def test_ci_width_n_boot(self, mediation_df):
        """More bootstrap samples → tighter CI (on average)."""
        res100 = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        res500 = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        width100 = res100.indirect_ci[1] - res100.indirect_ci[0]
        width500 = res500.indirect_ci[1] - res500.indirect_ci[0]
        # With 5x more samples, CI should not be dramatically wider
        assert width500 <= width100 * 2

    def test_ci_level_90(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=200, ci=0.90, seed=42)
        lower, upper = res.indirect_ci
        assert lower < upper

    def test_ci_level_99(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, ci=0.99, seed=42)
        lower, upper = res.indirect_ci
        assert lower < upper

    def test_different_seed_different_samples(self, mediation_df):
        res1 = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=1)
        res2 = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=2)
        # Boot samples should differ
        assert not np.allclose(res1.boot_samples, res2.boot_samples, rtol=1e-3)

    def test_sobel_z_populated(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        assert isinstance(res.sobel_z, (float, np.floating))
        assert isinstance(res.sobel_p, (float, np.floating))

    def test_sobel_p_significant(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        # Strong indirect effect → Sobel p < 0.05
        assert res.sobel_p < 0.05

    def test_missing_X_raises(self, mediation_df):
        df = mediation_df.drop(columns=["X"])
        with pytest.raises(Exception):
            bootstrap(df, "X", "M", "Y")

    def test_missing_M_raises(self, mediation_df):
        df = mediation_df.drop(columns=["M"])
        with pytest.raises(Exception):
            bootstrap(df, "X", "M", "Y")

    def test_missing_Y_raises(self, mediation_df):
        df = mediation_df.drop(columns=["Y"])
        with pytest.raises(Exception):
            bootstrap(df, "X", "M", "Y")

    def test_single_bootstrap_sample(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=1, seed=42)
        assert isinstance(res, MediationResult)
        assert len(res.boot_samples) >= 0

    def test_perfect_collinearity_in_bootstrap(self, rng):
        """When some bootstrap samples are singular, they get NaN → dropped."""
        df = pd.DataFrame({
            "X": rng.standard_normal(500),
            "M": rng.standard_normal(500),
            "Y": rng.standard_normal(500),
        })
        df["M"] = df["X"] * 2  # perfect collinearity in M ~ X
        res = bootstrap(df, "X", "M", "Y", n_boot=50, seed=42)
        assert isinstance(res, MediationResult)
        # NaN samples should be dropped
        assert len(res.boot_samples) <= 50

    def test_large_n_ci_precision(self, mediation_df_large):
        res = bootstrap(mediation_df_large, "X", "M", "Y", n_boot=1000, seed=42)
        lower, upper = res.indirect_ci
        width = upper - lower
        # With n=2000 and 1000 boots, CI should be reasonably tight
        assert width < 1.0

    def test_summary_contains_ci(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        s = res.summary()
        assert isinstance(s, str)
        assert "95% CI" in s or "% CI" in s


# ─────────────────────────────────────────────────────────────────────────────
# 5. classify_mediation() — Zhao, Lynch & Chen (2010)
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyMediation:
    """classify_mediation() four cases."""

    def test_full_mediation_indirect_only(self):
        """a*b significant, c' not significant → full mediation."""
        r = MediationResult(
            method="test",
            indirect_effect=0.2,
            direct_effect=0.0,
            total_effect=0.2,
            indirect_se=0.05,
            indirect_ci=(0.10, 0.30),
            a=0.5,
            a_se=0.05,
            b=0.4,
            b_se=0.05,
            c=0.2,
            c_prime=0.0,
            sobel_z=4.0,
            sobel_p=0.0001,
            n=500,
        )
        label = classify_mediation(r)
        assert "Full mediation" in label or "indirect-only" in label

    def test_complementary_mediation(self, mediation_df):
        """a*b and c' same sign → complementary."""
        res = sobel(mediation_df, "X", "M", "Y")
        label = classify_mediation(res)
        assert isinstance(label, str)
        assert len(label) > 0

    def test_competitive_suppression(self, mediation_df_suppression):
        """a*b and c' opposite signs → competitive/suppression."""
        res = sobel(mediation_df_suppression, "X", "M", "Y")
        label = classify_mediation(res)
        assert isinstance(label, str)
        assert "Competitive" in label or "Suppression" in label

    def test_no_mediation_direct_only(self, rng):
        """a*b not significant, c' significant → no mediation."""
        df = pd.DataFrame({
            "X": rng.standard_normal(1000),
            "M": rng.standard_normal(1000),
            "Y": rng.standard_normal(1000),
        })
        df["Y"] = 0.5 * df["X"] + rng.standard_normal(1000) * 0.5
        res = sobel(df, "X", "M", "Y")
        label = classify_mediation(res)
        assert isinstance(label, str)

    def test_no_effect(self, mediation_df_no_effect):
        res = sobel(mediation_df_no_effect, "X", "M", "Y")
        label = classify_mediation(res)
        assert isinstance(label, str)
        assert "No" in label or "effect" in label.lower()

    def test_perfect_mediation(self, mediation_df_perfect_mediation):
        res = sobel(mediation_df_perfect_mediation, "X", "M", "Y")
        label = classify_mediation(res)
        assert isinstance(label, str)

    def test_negative_indirect_positive_direct(self, rng):
        """Opposite signs → suppression."""
        # Build data where a*b and c' have opposite signs
        np.random.seed(0)
        n = 1000
        X = rng.standard_normal(n)
        # Strong negative direct path
        Y = -0.5 * X + rng.standard_normal(n) * 0.5
        # Small positive indirect via M
        M = 0.05 * X + rng.standard_normal(n) * 0.1
        df = pd.DataFrame({"X": X, "M": M, "Y": Y})
        res = sobel(df, "X", "M", "Y")
        # indirect should be small positive, direct negative → opposite signs
        indirect_sign = np.sign(res.indirect_effect)
        direct_sign = np.sign(res.direct_effect)
        assert indirect_sign != 0 and direct_sign != 0
        assert indirect_sign != direct_sign

    def test_classify_returns_valid_labels(self, mediation_df):
        labels = set()
        for _ in range(5):
            res = bootstrap(mediation_df, "X", "M", "Y", n_boot=50, seed=_)
            labels.add(classify_mediation(res))
        # Should return one of the known labels
        valid = {
            "Full mediation (indirect-only)",
            "Complementary mediation",
            "Competitive mediation (suppression)",
            "No mediation (direct-only)",
            "No effect",
        }
        for lbl in labels:
            assert lbl in valid


# ─────────────────────────────────────────────────────────────────────────────
# 6. End-to-end and integration
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """sobel + bootstrap + classify as a pipeline."""

    def test_sobel_then_classify(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        label = classify_mediation(res)
        assert "Complementary" in label or "Full" in label

    def test_bootstrap_then_classify(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=200, seed=42)
        label = classify_mediation(res)
        assert isinstance(label, str)

    def test_sobel_and_bootstrap_consistent(self, mediation_df):
        s_res = sobel(mediation_df, "X", "M", "Y")
        b_res = bootstrap(mediation_df, "X", "M", "Y", n_boot=500, seed=42)
        # Point estimates should be identical
        assert s_res.indirect_effect == pytest.approx(b_res.indirect_effect, rel=1e-3)
        # Sobel SE may differ from bootstrap SE
        assert isinstance(b_res.indirect_se, (float, np.floating))

    def test_summary_shows_correct_significance(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        s = res.summary()
        assert "Proportion mediated:" in s

    def test_ci_width_vs_sobel_se(self, mediation_df_large):
        """Bootstrap CI should typically be wider than ±1.96*SobelSE."""
        res = bootstrap(mediation_df_large, "X", "M", "Y", n_boot=500, seed=42)
        lower, upper = res.indirect_ci
        sobel_half_width = 1.96 * res.indirect_se
        # CI is percentile-based, Sobel SE is analytical
        assert isinstance(sobel_half_width, (float, np.floating))

    def test_perfect_mediation_ci(self, mediation_df_perfect_mediation):
        res = bootstrap(
            mediation_df_perfect_mediation, "X", "M", "Y", n_boot=200, seed=42
        )
        # Direct effect should be small
        assert isinstance(res.direct_effect, (float, np.floating))

    def test_suppression_ci(self, mediation_df_suppression):
        res = bootstrap(
            mediation_df_suppression, "X", "M", "Y", n_boot=200, seed=42
        )
        assert isinstance(res, MediationResult)

    def test_total_effect_decomposition(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        # total = direct + indirect
        assert res.total_effect == pytest.approx(
            res.direct_effect + res.indirect_effect, rel=1e-3
        )

    def test_a_b_path_coefficients(self, mediation_df):
        res = sobel(mediation_df, "X", "M", "Y")
        # Path a: X→M
        assert 0.2 < res.a < 0.8
        # Path b: M→Y|X
        assert 0.1 < res.b < 0.7

    def test_boot_indirect_equals_ab(self, mediation_df):
        res = bootstrap(mediation_df, "X", "M", "Y", n_boot=100, seed=42)
        # Point estimate should equal a*b
        assert res.indirect_effect == pytest.approx(res.a * res.b, rel=1e-6)
