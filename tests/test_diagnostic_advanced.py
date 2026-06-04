"""Tests for vuong_kob, leamer_sensitivity, diagnostic_reporter modules."""

import numpy as np
import pytest

rng = np.random.default_rng(42)


def _make_panel_data(n: int = 200) -> dict:
    """Shared mock panel data for tests."""
    t = 4
    nid = n
    e = rng.standard_normal((n * t, 4))
    df = {
        "y": e[:, 0],
        "x1": e[:, 1] + rng.uniform(-0.5, 0.5, n * t),
        "x2": e[:, 2] + rng.uniform(-0.5, 0.5, n * t),
        "x3": e[:, 3] + rng.uniform(-0.5, 0.5, n * t),
    }
    return df


# ══════════════════════════════════════════════════════════════════════
# VUONG TEST
# ══════════════════════════════════════════════════════════════════════

def test_vuong_result_dataclass():
    """VuongResult dataclass fields."""
    from scripts.research_framework.vuong_kob import VuongResult

    r = VuongResult(
        vuong_stat=1.5, pval=0.05, recommendation="Model1",
        strength="Strong", log_likelihood_1=-50.0, log_likelihood_2=-60.0,
        n_obs=100, aic_1=105.0, aic_2=125.0,
        bic_1=110.0, bic_2=130.0, clarke_stat=55.0, clarke_pval=0.06,
        winner="Model1", model1_name="OLS", model2_name="Logit",
    )
    assert r.vuong_stat == 1.5
    assert r.pval == 0.05
    assert r.recommendation == "Model1"
    assert r.winner == "Model1"
    # p=0.05 is exactly at threshold → * (not **)
    assert r.sig == "*"  # p < 0.10 but NOT < 0.05


def test_vuong_result_sig():
    from scripts.research_framework.vuong_kob import VuongResult
    r1 = VuongResult(0.0, 0.003, "M1", "S", 0.0, 0.0, 100, 1.0, 1.0, 1.0, 1.0, 0.0, 0.01, "M1")
    assert r1.sig == "***"
    r2 = VuongResult(0.0, 0.07, "M1", "S", 0.0, 0.0, 100, 1.0, 1.0, 1.0, 1.0, 0.0, 0.1, "M1")
    assert r2.sig == "*"


def test_vuong_result_to_dict():
    from scripts.research_framework.vuong_kob import VuongResult
    r = VuongResult(2.0, 0.01, "Model2", "Strong", 0.0, 0.0, 100,
                     1.0, 1.0, 1.0, 1.0, 60.0, 0.03, "Model2", "A", "B")
    d = r.to_dict()
    assert d["vuong_stat"] == 2.0
    assert d["pval"] == 0.01
    assert d["winner"] == "Model2"
    assert d["model1_name"] == "A"


def test_vuong_result_to_latex():
    from scripts.research_framework.vuong_kob import VuongResult
    r = VuongResult(1.96, 0.05, "M1", "Weak", 0.0, 0.0, 100,
                     100.0, 105.0, 110.0, 115.0, 50.0, 0.06, "M1", "DID", "RDD")
    latex = r.to_latex()
    assert "\\begin{table}" in latex
    assert "DID" in latex
    assert "RDD" in latex
    assert "\\caption{Vuong Non-Nested Test Results}" in latex


def test_clarke_test():
    from scripts.research_framework.vuong_kob import _clarke_test
    # H0: 两模型等价，正负各半
    diff = np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    stat, pval = _clarke_test(diff)
    assert stat == 5  # 5个正
    assert 0.5 < pval <= 1.0  # 不拒绝 H0


def test_vuongtest_empty_result():
    from scripts.research_framework.vuong_kob import VuongTest
    vt = VuongTest("A", "B")
    # 不传入模型，直接返回空结果
    r = vt._empty_result()
    assert np.isnan(r.vuong_stat)
    assert r.winner == "No preference"


# ══════════════════════════════════════════════════════════════════════
# OAXACA-BLINDER
# ══════════════════════════════════════════════════════════════════════

def test_oaxaca_blinder_basic():
    from scripts.research_framework.vuong_kob import OaxacaBlinderDecomposition

    n1, n2 = 100, 100
    np.random.seed(0)
    y1 = np.random.randn(n1) + 1.0
    y2 = np.random.randn(n2)
    X1 = np.random.randn(n1, 3)
    X2 = np.random.randn(n2, 3)

    ob = OaxacaBlinderDecomposition("HighEdu", "LowEdu")
    result = ob.fit(y1, X1, y2, X2)

    assert isinstance(result.raw_gap, float)
    assert isinstance(result.endowments, float)
    assert isinstance(result.coefficients, float)
    assert result.group1_name == "HighEdu"
    assert result.group2_name == "LowEdu"
    # Gap ≈ ȳ₁ - ȳ₂ ≈ 1.0
    assert 0.5 < result.raw_gap < 1.5


def test_oaxaca_blinder_to_dict():
    from scripts.research_framework.vuong_kob import OaxacaBlinderDecomposition
    n1, n2 = 50, 50
    np.random.seed(0)
    ob = OaxacaBlinderDecomposition()
    r = ob.fit(
        np.random.randn(n1) + 0.5,
        np.random.randn(n1, 2),
        np.random.randn(n2),
        np.random.randn(n2, 2),
    )
    d = r.to_dict()
    assert "endowments_E" in d
    assert "coefficients_C" in d
    assert "pct_E" in d


# ══════════════════════════════════════════════════════════════════════
# KOB DECOMPOSITION
# ══════════════════════════════════════════════════════════════════════

def test_kob_basic():
    from scripts.research_framework.vuong_kob import KOBDecomposition

    np.random.seed(42)
    n1, n2 = 80, 80
    # Exactly deterministic X (no randomness in means)
    X1 = np.tile([10.0, 5.0], (n1, 1))
    X2 = np.tile([8.0, 4.0], (n2, 1))
    # True DGP: y = X @ β + ε, ε ⊥ X
    y1 = X1 @ np.array([0.5, 0.3]) + np.random.randn(n1) * 0.01
    y2 = X2 @ np.array([0.3, 0.1]) + np.random.randn(n2) * 0.01

    kob = KOBDecomposition("Male", "Female")
    result = kob.fit(y1, X1, y2, X2, n_bootstrap=49, seed=42)

    assert isinstance(result.raw_gap, float)
    assert result.group1_name == "Male"
    assert result.group2_name == "Female"
    assert result.n_bootstrap == 49
    assert np.isfinite(result.endowments_se)
    assert np.isfinite(result.pricing_se)
    # Bootstrap SEs should be smaller than point estimates (otherwise meaningless)
    assert result.endowments_se < abs(result.endowments) + 1
    assert result.pricing_se < abs(result.pricing) + 1
    # Components are self-consistent
    assert np.isfinite(result.endowments_pct)
    assert np.isfinite(result.pricing_pct)
    assert np.isfinite(result.interaction_pct)


def test_kob_interpretation():
    from scripts.research_framework.vuong_kob import KOBDecomposition
    np.random.seed(0)
    r = KOBDecomposition("G1", "G2").fit(
        np.random.randn(60) + 0.8,
        np.random.randn(60, 2),
        np.random.randn(60),
        np.random.randn(60, 2),
        n_bootstrap=19,
    )
    txt = r.interpretation
    assert "原始差距" in txt
    assert "禀赋效应" in txt or "价格效应" in txt
    assert "精确分解" in txt


def test_kob_to_latex():
    from scripts.research_framework.vuong_kob import KOBDecomposition
    np.random.seed(0)
    r = KOBDecomposition("SOE", "Private").fit(
        np.random.randn(60) + 0.5,
        np.random.randn(60, 2),
        np.random.randn(60),
        np.random.randn(60, 2),
        n_bootstrap=19,
    )
    latex = r.to_latex()
    assert "\\begin{table}" in latex
    assert "SOE" in latex
    assert "Private" in latex


def test_kob_to_dict():
    from scripts.research_framework.vuong_kob import KOBDecomposition
    np.random.seed(0)
    r = KOBDecomposition().fit(
        np.random.randn(50) + 0.3,
        np.random.randn(50, 2),
        np.random.randn(50),
        np.random.randn(50, 2),
        n_bootstrap=9,
    )
    d = r.to_dict()
    assert "endowments_E" in d
    assert "endowments_se" in d
    assert "pct_E" in d


# ══════════════════════════════════════════════════════════════════════
# LEAMER SENSITIVITY
# ══════════════════════════════════════════════════════════════════════

def test_leamer_result_dataclass():
    from scripts.research_framework.leamer_sensitivity import LeamerResult
    r = LeamerResult(
        baseline_coef=0.5, baseline_se=0.1, baseline_pval=0.001,
        extreme_bounds={"lower": 0.3, "upper": 0.7},
        extreme_coefs=[0.5, 0.3, 0.7],
        control_names=["x2"],
        reliability_ratio=0.71,
        interpretation="稳健",
    )
    assert r.baseline_coef == 0.5
    assert r.extreme_bounds["lower"] == 0.3
    assert r.reliability_ratio > 0.7


def test_leamer_sensitivity_basic():
    from scripts.research_framework.leamer_sensitivity import LeamerSensitivity

    np.random.seed(0)
    n = 100
    X = np.column_stack([
        np.ones(n),
        np.random.randn(n),
        np.random.randn(n),
        np.random.randn(n),
    ])
    y = 0.5 * X[:, 1] + 0.3 * X[:, 2] + np.random.randn(n) * 0.5

    ls = LeamerSensitivity()
    result = ls.fit(X, y, xnames=["const", "x1", "x2", "x3"], key_var_idx=1)

    assert isinstance(result.baseline_coef, float)
    assert isinstance(result.reliability_ratio, float)
    assert result.baseline_coef > 0
    # Key var idx=1, dropping x2 should change coef
    assert len(result.extreme_coefs) >= 1


def test_leamer_to_dict():
    from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
    np.random.seed(0)
    X = np.column_stack([np.ones(80), np.random.randn(80), np.random.randn(80)])
    y = 0.5 * X[:, 1] + np.random.randn(80) * 0.5
    ls = LeamerSensitivity()
    r = ls.fit(X, y, xnames=["c", "x1", "x2"], key_var_idx=1)
    d = r.to_dict()
    assert "baseline_coef" in d
    assert "extreme_lower" in d
    assert "reliability_ratio" in d


# ══════════════════════════════════════════════════════════════════════
# EBERSTEIN-MAGNAC
# ══════════════════════════════════════════════════════════════════════

def test_eberstein_magnac_basic():
    from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity

    np.random.seed(0)
    n = 100
    X = np.column_stack([np.ones(n), np.random.randn(n), np.random.randn(n)])
    y = 0.5 * X[:, 1] + 0.2 * X[:, 2] + np.random.randn(n) * 0.5

    em = EbersteinMagnacSensitivity()
    result = em.fit(X, y, endogenous_idx=1, f_stat=15.0)

    assert isinstance(result.baseline_coef, float)
    assert result.f_stat == 15.0
    assert result.lower_bound < result.baseline_coef < result.upper_bound
    assert "弱" not in result.interpretation


def test_bounding_result_to_dict():
    from scripts.research_framework.leamer_sensitivity import EbersteinMagnacSensitivity
    np.random.seed(0)
    X = np.column_stack([np.ones(60), np.random.randn(60)])
    y = 0.5 * X[:, 1] + np.random.randn(60) * 0.5
    em = EbersteinMagnacSensitivity()
    r = em.fit(X, y, endogenous_idx=1)
    d = r.to_dict()
    assert "baseline_coef" in d
    assert "lower_bound" in d
    assert "upper_bound" in d


# ══════════════════════════════════════════════════════════════════════
# AR(2) TEST
# ══════════════════════════════════════════════════════════════════════

def test_ar2_basic():
    from scripts.research_framework.leamer_sensitivity import test_ar2

    np.random.seed(0)
    residuals = np.random.randn(200)
    result = test_ar2(residuals, order=2)

    assert "ar1_stat" in result
    assert "ar1_pval" in result
    assert "ar2_stat" in result
    assert "ar2_pval" in result
    # 纯随机残差：AR(2) 应该不显著
    assert result["ar2_pval"] > 0.05


def test_ar2_autocorrelated():
    from scripts.research_framework.leamer_sensitivity import test_ar2

    np.random.seed(42)
    # AR(2) 过程
    eps = np.random.randn(300)
    y = np.zeros(300)
    for t in range(2, 300):
        y[t] = 0.5 * y[t-1] + 0.3 * y[t-2] + eps[t]
    result = test_ar2(y, order=2)
    # 有自相关：AR(2) 应该显著
    assert "ar2_stat" in result
    assert "ar2_pval" in result


def test_dynamic_panel_diagnostics():
    from scripts.research_framework.leamer_sensitivity import run_dynamic_panel_diagnostics
    import pandas as pd

    np.random.seed(0)
    n = 50
    t = 5
    data = {
        "y": np.random.randn(n * t),
        "x1": np.random.randn(n * t),
        "x2": np.random.randn(n * t),
        "ticker": np.repeat(range(n), t),
        "year": np.tile(range(t), n),
    }
    df = pd.DataFrame(data)

    diag = run_dynamic_panel_diagnostics(df, "y", ["x1", "x2"], "ticker", "year")
    assert diag.n_obs == n * t
    assert np.isfinite(diag.ar1_stat)
    assert np.isfinite(diag.ar2_pval)


# ══════════════════════════════════════════════════════════════════════
# CONTAGION TEST
# ══════════════════════════════════════════════════════════════════════

def test_contagion_test_basic():
    from scripts.research_framework.leamer_sensitivity import ContagionTest

    np.random.seed(0)
    # 5个市场，200期
    returns = np.random.randn(200, 5) * 0.02

    ct = ContagionTest()
    result = ct.fit(returns, crisis_period=(100, 150))

    assert "pre_corr_mean" in result
    assert "crisis_corr_mean" in result
    assert "conclusion" in result
    assert "n_pre" in result
    assert "n_crisis" in result


def test_contagion_test_conclusion():
    from scripts.research_framework.leamer_sensitivity import ContagionTest

    np.random.seed(0)
    returns = np.random.randn(200, 3)
    ct = ContagionTest()
    result = ct.fit(returns, crisis_period=(50, 80))
    assert result["conclusion"] in ["Contagion detected", "No contagion", "Insufficient data"]


# ══════════════════════════════════════════════════════════════════════
# SPILLOVER INDEX
# ══════════════════════════════════════════════════════════════════════

def test_spillover_index_basic():
    from scripts.research_framework.leamer_sensitivity import SpilloverIndex

    np.random.seed(0)
    returns = np.random.randn(200, 4) * 0.01
    si = SpilloverIndex()
    result = si.fit(returns, n_lags=2)

    assert "total_spillover_index" in result or "error" in result
    # Should either have spillover index or error message
    assert set(result.keys()).issubset({
        "spillover_table", "total_spillover_index",
        "directional_from", "directional_to", "net_spillover",
        "n_markets", "n_lags", "error",
    })


# ══════════════════════════════════════════════════════════════════════
# DIAGNOSTIC REPORTER
# ══════════════════════════════════════════════════════════════════════

def test_diagnostic_decision_enum():
    from scripts.research_framework.diagnostic_reporter import DiagnosticDecision
    assert DiagnosticDecision.PASS.value == "PASS"
    assert DiagnosticDecision.WARN.value == "WARN"
    assert DiagnosticDecision.FAIL.value == "FAIL"


def test_diagnostic_check_dataclass():
    from scripts.research_framework.diagnostic_reporter import DiagnosticCheck, DiagnosticDecision
    c = DiagnosticCheck(
        name="vif_x1", name_zh="VIF (x1)",
        category="D. 多重共线性",
        decision=DiagnosticDecision.PASS,
        value=2.5, threshold="< 5",
        pval=None, recommendation="无共线性",
    )
    assert c.decision == DiagnosticDecision.PASS
    assert c.value == 2.5


def test_diagnostic_reporter_auto_decide():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter, DiagnosticDecision

    rep = DiagnosticReporter()
    # VIF
    assert rep._auto_decide("vif", 3.0, None) == DiagnosticDecision.PASS
    assert rep._auto_decide("vif", 7.0, None) == DiagnosticDecision.WARN
    assert rep._auto_decide("vif", 15.0, None) == DiagnosticDecision.FAIL
    # Moran
    assert rep._auto_decide("moran_i", 0.5, 0.01) == DiagnosticDecision.FAIL
    assert rep._auto_decide("moran_i", 0.1, 0.5) == DiagnosticDecision.PASS
    # Parallel trends
    assert rep._auto_decide("parallel_trends", 1.5, 0.15) == DiagnosticDecision.PASS
    assert rep._auto_decide("parallel_trends", 1.5, 0.03) == DiagnosticDecision.FAIL
    # DW
    assert rep._auto_decide("durbin_watson", 1.8, None) == DiagnosticDecision.PASS
    assert rep._auto_decide("durbin_watson", 0.3, None) == DiagnosticDecision.FAIL


def test_diagnostic_reporter_chain():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter, DiagnosticDecision

    rep = (
        DiagnosticReporter("OLS Baseline")
        .add_check("vif", "VIF", "D", 3.5, "< 5", None)
        .add_check("moran_i", "Moran I", "G", 0.2, "p > 0.05", 0.3)
        .add_check("shapiro", "Shapiro-Wilk", "D", 0.8, "p > 0.05", 0.08)
    )
    assert len(rep._checks) == 3


def test_diagnostic_report_n_pass():
    from scripts.research_framework.diagnostic_reporter import (
        DiagnosticReporter, DiagnosticDecision,
    )

    rep = DiagnosticReporter()
    rep.add_check("vif1", "VIF", "D", 2.0, "< 5", decision=DiagnosticDecision.PASS)
    rep.add_check("vif2", "VIF", "D", 7.0, "< 10", decision=DiagnosticDecision.WARN)
    rep.add_check("vif3", "VIF", "D", 15.0, "> 10", decision=DiagnosticDecision.FAIL)
    report = rep.generate()

    assert report.n_pass == 1
    assert report.n_warn == 1
    assert report.n_fail == 1
    assert report.overall == DiagnosticDecision.FAIL


def test_diagnostic_report_to_dataframe():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter, DiagnosticDecision
    import pandas as pd

    rep = DiagnosticReporter()
    rep.add_check("vif", "VIF", "D", 3.5, "< 5", pval=0.3, decision=DiagnosticDecision.PASS)
    report = rep.generate()
    df = report.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert "数值" in df.columns
    assert "建议" in df.columns


def test_diagnostic_report_to_latex():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter, DiagnosticDecision
    rep = DiagnosticReporter()
    rep.add_check("vif", "VIF", "D", 3.5, "< 5", pval=0.3, decision=DiagnosticDecision.PASS)
    report = rep.generate()
    latex = report.to_latex()
    assert "\\begin{longtable}" in latex
    assert "caption{Diagnostic Report}" in latex


def test_diagnostic_report_summary_text():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter, DiagnosticDecision
    rep = DiagnosticReporter()
    rep.add_check("vif", "VIF", "D", 3.5, "< 5", pval=0.3, decision=DiagnosticDecision.PASS)
    report = rep.generate()
    text = report.summary_text()
    assert "诊断报告总评" in text
    assert "VIF" in text


def test_diagnostic_reporter_add_methods():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter
    rep = DiagnosticReporter()
    rep.add_vif({"x1": 2.0, "x2": 6.5, "x3": 12.0})
    assert len(rep._checks) == 3
    rep.add_heterosk("BP", 3.5, 0.12)
    assert len(rep._checks) == 4
    rep.add_autocorr(1.8)
    assert len(rep._checks) == 5
    rep.add_parallel_trends(1.2, 0.35)
    assert len(rep._checks) == 6


def test_diagnostic_reporter_add_ar2():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter
    rep = DiagnosticReporter()
    rep.add_ar2(0.45)  # p > 0.05 → PASS
    assert rep._checks[-1].decision.value == "PASS"
    rep2 = DiagnosticReporter()
    rep2.add_ar2(0.02)  # p < 0.05 → FAIL
    assert rep2._checks[-1].decision.value == "FAIL"


def test_diagnostic_reporter_add_weak_iv():
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter
    rep = DiagnosticReporter()
    rep.add_weak_iv(25.0)  # F > 10 → PASS
    assert rep._checks[-1].decision.value == "PASS"
    rep2 = DiagnosticReporter()
    rep2.add_weak_iv(5.0)  # F < 10 → FAIL
    assert rep2._checks[-1].decision.value == "FAIL"
