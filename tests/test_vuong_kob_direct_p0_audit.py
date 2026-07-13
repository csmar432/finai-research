"""vuong_kob direct unit tests (P0-C, audit 2026-07-12).

Direct tests for vuong_kob main classes (VuongTest, KOBDecomposition,
OaxacaBlinderDecomposition), no longer relying on vuong_test's re-export
for indirect coverage.

Also surfaces and locks in the OB decomposition bug fix: switched from the
broken Cotton-style 3-fold (non-additive) to Jann (2008) 'oaxaca threefold'
with pooled reference beta* (E + C = Gap, exactly additive).
"""
from __future__ import annotations

import numpy as np
import pytest


# ─── Module import smoke ──────────────────────────────────────────────


def test_vuong_kob_module_imports():
    from scripts.research_framework.vuong_kob import (
        VuongTest, VuongResult, KOBDecomposition, KOBResult,
        OaxacaBlinderDecomposition, OaxacaResult, _clarke_test,
        wage_decomposition,
    )
    assert VuongTest is not None
    assert VuongResult is not None
    assert KOBDecomposition is not None
    assert KOBResult is not None
    assert OaxacaBlinderDecomposition is not None
    assert OaxacaResult is not None


# ─── Dataclass field coverage ─────────────────────────────────────────


def test_vuong_result_fields():
    from scripts.research_framework.vuong_kob import VuongResult
    import dataclasses
    assert dataclasses.is_dataclass(VuongResult)
    fields = {f.name for f in dataclasses.fields(VuongResult)}
    expected = {
        "vuong_stat", "pval", "recommendation", "strength",
        "winner", "model1_name", "model2_name",
        "log_likelihood_1", "log_likelihood_2", "n_obs",
        "aic_1", "aic_2", "bic_1", "bic_2",
        "clarke_stat", "clarke_pval",
    }
    assert expected.issubset(fields), f"Missing: {expected - fields}"


def test_kob_result_fields():
    from scripts.research_framework.vuong_kob import KOBResult
    import dataclasses
    assert dataclasses.is_dataclass(KOBResult)
    fields = {f.name for f in dataclasses.fields(KOBResult)}
    expected = {
        "raw_gap", "endowments", "pricing", "interaction",
        "endowments_se", "pricing_se", "interaction_se",
        "endowments_pct", "pricing_pct", "interaction_pct",
        "decomposition_adds_up", "n_group1", "n_group2", "n_bootstrap",
    }
    assert expected.issubset(fields), f"Missing: {expected - fields}"


def test_oaxaca_result_fields():
    from scripts.research_framework.vuong_kob import OaxacaResult
    import dataclasses
    assert dataclasses.is_dataclass(OaxacaResult)
    fields = {f.name for f in dataclasses.fields(OaxacaResult)}
    expected = {
        "raw_gap", "endowments", "coefficients", "interaction",
        "share_endowments", "share_coefficients", "share_interaction",
        "n_group1", "n_group2",
    }
    assert expected.issubset(fields), f"Missing: {expected - fields}"


# ─── VuongTest behaviour ──────────────────────────────────────────────


def test_vuong_test_init():
    from scripts.research_framework.vuong_kob import VuongTest
    m = VuongTest(name1="DID", name2="RDD")
    assert m.name1 == "DID"
    assert m.name2 == "RDD"


def test_vuong_test_fit_with_residuals_returns_result():
    from scripts.research_framework.vuong_kob import VuongTest

    rng = np.random.default_rng(42)
    n = 200
    e1 = rng.normal(0, 1.0, n)
    e2 = rng.normal(0, 2.0, n)

    class M:
        pass
    m1 = M(); m1.llf = -100.0; m1.nobs = n; m1.df_model = 3
    m2 = M(); m2.llf = -150.0; m2.nobs = n; m2.df_model = 3

    vt = VuongTest(name1="Better", name2="Worse")
    result = vt.fit(m1, m2, residuals1=e1, residuals2=e2)

    assert result is not None
    assert isinstance(result.vuong_stat, float)
    assert 0.0 <= result.pval <= 1.0


def test_vuong_test_empty_result_on_garbage_input():
    from scripts.research_framework.vuong_kob import VuongTest

    class BadModel:
        pass

    vt = VuongTest()
    result = vt.fit(BadModel(), BadModel())
    assert result is not None
    assert np.isnan(result.vuong_stat) or result.vuong_stat == 0.0


def test_vuong_result_to_dict_round_trip():
    from scripts.research_framework.vuong_kob import VuongResult
    r = VuongResult(
        vuong_stat=2.5, pval=0.01, recommendation="M1 better",
        strength="Strong", winner="Model1",
        log_likelihood_1=-100.0, log_likelihood_2=-150.0, n_obs=200,
        aic_1=100.0, aic_2=110.0, bic_1=105.0, bic_2=115.0,
        clarke_stat=120, clarke_pval=0.02,
    )
    d = r.to_dict()
    assert d["vuong_stat"] == 2.5
    assert d["winner"] == "Model1"
    assert d["aic_1"] == 100.0
    assert d["clarke_pval"] == 0.02


def test_vuong_result_to_latex_contains_table():
    from scripts.research_framework.vuong_kob import VuongResult
    r = VuongResult(
        vuong_stat=2.5, pval=0.01, recommendation="M1 better",
        strength="Strong", winner="M1",
        log_likelihood_1=-100.0, log_likelihood_2=-150.0, n_obs=200,
        aic_1=100.0, aic_2=110.0, bic_1=105.0, bic_2=115.0,
        clarke_stat=120, clarke_pval=0.02,
        model1_name="OLS", model2_name="Logit",
    )
    latex = r.to_latex()
    assert "\\begin{table}" in latex
    assert "\\end{table}" in latex
    assert "Vuong" in latex
    assert "OLS" in latex


def test_vuong_result_sig_property():
    """sig is a property (not method), pval -> ***/**/*/''."""
    from scripts.research_framework.vuong_kob import VuongResult
    base = dict(
        log_likelihood_1=-100, log_likelihood_2=-150, n_obs=200,
        aic_1=100, aic_2=110, bic_1=105, bic_2=115,
        clarke_stat=120, clarke_pval=0.5,
        recommendation="", strength="", winner="",
        model1_name="A", model2_name="B",
    )
    r001 = VuongResult(vuong_stat=2.5, pval=0.0005, **base)
    r05 = VuongResult(vuong_stat=2.0, pval=0.005, **base)
    r10 = VuongResult(vuong_stat=1.5, pval=0.05, **base)
    r30 = VuongResult(vuong_stat=1.0, pval=0.30, **base)
    assert r001.sig == "***"
    assert r05.sig == "**"
    assert r10.sig == "*"
    assert r30.sig == ""


# ─── Clarke test helper ───────────────────────────────────────────────


def test_clarke_test_balanced_returns_high_pval():
    from scripts.research_framework.vuong_kob import _clarke_test
    rng = np.random.default_rng(0)
    diff = rng.normal(0, 1, 500)
    stat, pval = _clarke_test(diff)
    assert 0.0 <= pval <= 1.0
    assert pval > 0.05


def test_clarke_test_strongly_asymmetric_returns_low_pval():
    from scripts.research_framework.vuong_kob import _clarke_test
    diff = np.ones(100)
    stat, pval = _clarke_test(diff)
    assert pval < 0.001


def test_clarke_test_empty_returns_neutral():
    from scripts.research_framework.vuong_kob import _clarke_test
    stat, pval = _clarke_test(np.array([]))
    assert stat == 0.0
    assert pval == 1.0


# ─── Oaxaca (Jann 2008 threefold, exactly additive) ───────────────────


def test_oaxaca_additive_decomposition_with_intercept():
    """Jann (2008) decomposition with constant column: E + C = Gap exactly."""
    from scripts.research_framework.vuong_kob import OaxacaBlinderDecomposition

    rng = np.random.default_rng(42)
    n = 300
    # X must include intercept column for additivity (OLS mean = β'X̄ only if
    # the intercept is in X; otherwise residuals absorb the mean shift).
    X1 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 3))])
    X2 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 3))])
    y1 = X1[:, 1:] @ np.array([1.0, 0.5, 0.3]) + 2.0 + rng.normal(0, 0.5, n)
    y2 = X2[:, 1:] @ np.array([1.0, 0.5, 0.3]) + 2.0 + 1.5 + rng.normal(0, 0.5, n)

    ob = OaxacaBlinderDecomposition(name1="G1", name2="G2")
    result = ob.fit(y1, X1, y2, X2)

    assert result.n_group1 == n
    assert result.n_group2 == n
    # E + C + I = raw_gap exactly (Jann parametrization: interaction absorbed
    # into C, so I = 0 by construction; total still equals gap).
    reconstructed = result.endowments + result.coefficients + result.interaction
    assert abs(reconstructed - result.raw_gap) < 1e-6, (
        f"OB non-additive: E+C+I={reconstructed:.6f} vs gap={result.raw_gap:.6f}"
    )


def test_oaxaca_zero_gap_when_groups_identical():
    from scripts.research_framework.vuong_kob import OaxacaBlinderDecomposition

    rng = np.random.default_rng(0)
    n = 200
    X = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 3))])
    beta = np.array([2.0, 1.0, 0.5, 0.3])
    y = X @ beta + rng.normal(0, 0.5, n)

    ob = OaxacaBlinderDecomposition(name1="A", name2="B")
    result = ob.fit(y, X, y, X)

    assert abs(result.raw_gap) < 0.1
    assert abs(result.endowments) < 0.1
    assert abs(result.coefficients) < 0.1


def test_oaxaca_endowments_share_direction():
    """当 group1 特征更高时, 禀赋效应 E 应为正 (贡献于 group1 的更高平均)."""
    from scripts.research_framework.vuong_kob import OaxacaBlinderDecomposition

    rng = np.random.default_rng(1)
    n = 400
    # group1 特征均值更高
    X1 = np.hstack([np.ones((n, 1)), rng.normal(2.0, 1, (n, 3))])
    X2 = np.hstack([np.ones((n, 1)), rng.normal(0.0, 1, (n, 3))])
    y1 = X1[:, 1:] @ np.array([1.0, 0.5, 0.3]) + 0.0 + rng.normal(0, 0.3, n)
    y2 = X2[:, 1:] @ np.array([1.0, 0.5, 0.3]) + 0.0 + rng.normal(0, 0.3, n)

    ob = OaxacaBlinderDecomposition()
    result = ob.fit(y1, X1, y2, X2)

    # group1 特征更高 → ȳ1 > ȳ2 → raw_gap > 0
    assert result.raw_gap > 0
    # 禀赋效应 E = β*(X̄1-X̄2) 应当反映这个优势, 符号 > 0 (主要由禀赋贡献)
    assert result.endowments > 0


# ─── KOB (Kitagawa 2015 three-factor with bootstrap SE) ───────────────


def test_kob_decomposition_basic_additivity():
    from scripts.research_framework.vuong_kob import KOBDecomposition

    rng = np.random.default_rng(42)
    n = 200
    X1 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 2))])
    X2 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 2))])
    y1 = X1[:, 1:] @ np.array([1.0, 0.5]) + 2.0 + rng.normal(0, 0.5, n)
    y2 = X2[:, 1:] @ np.array([1.0, 0.5]) + 2.0 + 1.0 + rng.normal(0, 0.5, n)

    kob = KOBDecomposition(name1="Group1", name2="Group2")
    result = kob.fit(y1, X1, y2, X2, n_bootstrap=49, seed=0)

    assert result.n_group1 == n
    assert result.n_group2 == n
    assert result.n_bootstrap == 49
    # OB-based KOB: E + P + I = Gap (Jann-form exactly additive)
    reconstructed = result.endowments + result.pricing + result.interaction
    assert abs(reconstructed - result.raw_gap) < 0.01
    assert result.decomposition_adds_up is True


def test_kob_bootstrap_se_positive():
    from scripts.research_framework.vuong_kob import KOBDecomposition

    rng = np.random.default_rng(7)
    n = 100
    X = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 2))])
    y1 = X[:, 1:] @ np.array([1.0, 0.5]) + rng.normal(0, 0.5, n)
    y2 = X[:, 1:] @ np.array([1.5, 1.0]) + 0.5 + rng.normal(0, 0.5, n)

    kob = KOBDecomposition()
    result = kob.fit(y1, X, y2, X, n_bootstrap=29, seed=42)

    assert result.endowments_se >= 0
    assert result.pricing_se >= 0
    assert result.interaction_se >= 0


def test_kob_result_percentages_sum_to_100():
    from scripts.research_framework.vuong_kob import KOBDecomposition

    rng = np.random.default_rng(0)
    n = 150
    X1 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 3))])
    X2 = np.hstack([np.ones((n, 1)), rng.normal(0, 1, (n, 3))])
    y1 = X1[:, 1:] @ np.array([1.0, 0.5, 0.2]) + 2.0 + rng.normal(0, 0.3, n)
    y2 = X2[:, 1:] @ np.array([1.0, 0.5, 0.2]) + 2.0 + 2.0 + rng.normal(0, 0.3, n)

    kob = KOBDecomposition()
    result = kob.fit(y1, X1, y2, X2, n_bootstrap=29, seed=1)

    pct_sum = result.endowments_pct + result.pricing_pct + result.interaction_pct
    assert abs(pct_sum - 100.0) < 1.0, f"Percentages don't sum: {pct_sum:.2f}"


def test_kob_to_latex_contains_required_components():
    from scripts.research_framework.vuong_kob import KOBResult
    r = KOBResult(
        raw_gap=1.0, endowments=0.5, pricing=0.3, interaction=0.2,
        endowments_se=0.1, pricing_se=0.1, interaction_se=0.05,
        endowments_pct=50.0, pricing_pct=30.0, interaction_pct=20.0,
        decomposition_adds_up=True, n_group1=100, n_group2=100,
        n_bootstrap=199, group1_name="A", group2_name="B",
    )
    latex = r.to_latex()
    assert "\\begin{table}" in latex
    assert "Endowment" in latex
    assert "Price" in latex
    assert "Interaction" in latex
    assert "Bootstrap" in latex


# ─── Convenience wrappers ─────────────────────────────────────────────


def test_wage_decomposition_runs():
    from scripts.research_framework.vuong_kob import wage_decomposition
    import pandas as pd
    rng = np.random.default_rng(42)
    n = 300
    df = pd.DataFrame({
        "lnwage": rng.normal(2.5, 0.4, n),
        "female": rng.integers(0, 2, n),
        "edu": rng.normal(12, 2, n),
        "exp": rng.normal(10, 5, n),
        "tenure": rng.normal(5, 3, n),
    })
    result = wage_decomposition(df, outcome="lnwage", group="female",
                                predictors=["edu", "exp", "tenure"])
    assert result.n_group1 + result.n_group2 == n


def test_wage_decomposition_handles_small_sample():
    from scripts.research_framework.vuong_kob import wage_decomposition
    import pandas as pd
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "lnwage": rng.normal(2.5, 0.4, 60),
        "female": rng.integers(0, 2, 60),
        "edu": rng.normal(12, 2, 60),
        "exp": rng.normal(10, 5, 60),
        "tenure": rng.normal(5, 3, 60),
    })
    result = wage_decomposition(df)
    assert result is not None
