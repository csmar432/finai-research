"""Smoke tests for scripts/factor_models.py

P3-audit-2026-07-04: factor_models.py 之前 0% 覆盖（834 stmts，最大 0% 文件）。
覆盖核心类构造 / 工具函数 / 显著性星号 / 一行回归，绕过完整拟合。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 把 scripts/ 加进 sys.path
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from scripts.factor_models import (  # noqa: E402
    BaseFactorModel,
    Carhart4,
    CrossSectionalRegression,
    FactorModelComparison,
    FactorModelResult,
    FamaFrench3,
    FamaFrench5,
    FF6_with_Q,
    GMMEstimator,
    LassoFactorSelector,
    TimeSeriesRegression,
    ESGAlphaTest,
    _stars,
    _grs_test,
)


# ── _stars 工具函数 ─────────────────────────────────────────────────────


def test_stars_thresholds():
    """p 值→星号标注"""
    assert _stars(0.0001) == "***"
    assert _stars(0.001) == "***"
    assert _stars(0.005) == "**"
    assert _stars(0.01) == "**"
    assert _stars(0.03) == "*"
    assert _stars(0.05) == "*"
    assert _stars(0.1) == r"$\dagger$"
    assert _stars(0.2) == ""  # > 0.1 无标注


# ── 因子模型类构造 + factors 字段 ──────────────────────────────────────


def test_fama_french3_attributes():
    ff3 = FamaFrench3()
    assert ff3.name == "FF3"
    assert ff3.factors == ["MKT", "SMB", "HML"]
    assert "MKT" in ff3.factor_labels


def test_carhart4_attributes():
    c = Carhart4()
    assert c.name == "Carhart4"
    assert "UMD" in c.factors or "MOM" in c.factors  # momentum factor


def test_fama_french5_attributes():
    f5 = FamaFrench5()
    assert f5.name == "FF5"
    assert "RMW" in f5.factors
    assert "CMA" in f5.factors


def test_ff6_with_q_attributes():
    f6 = FF6_with_Q()
    assert f6.name == "FF6" or "FF6" in f6.name


# ── FactorModelResult 序列化 ──────────────────────────────────────────


def test_factor_model_result_init():
    r = FactorModelResult(name="test")
    assert r.name == "test"
    assert r.models == []
    assert r.coefs == []
    assert r._alpha is None
    assert r._betas is None


def test_factor_model_result_add_model_and_to_csv(tmp_path: Path):
    """add_model + to_csv 完整链路。"""
    r = FactorModelResult(name="test")
    coef_df = pd.DataFrame({
        "factor": ["MKT", "SMB"],
        "coef": [1.0, 0.5],
        "t_stat": [5.0, 2.5],
        "p_value": [0.001, 0.02],
    })
    r.add_model(coef_df, n_obs=100, r2=0.6, dep_var="port1")
    out = tmp_path / "result.csv"
    r.to_csv(out)
    assert out.exists()
    text = out.read_text()
    assert "MKT" in text
    assert "port1" in text or "model" in text


def test_factor_model_result_to_markdown_minimal():
    """to_markdown 输出表格字符串。coef_df 需要以 factor 为 index, 含 coef/se/pval 列。"""
    r = FactorModelResult(name="md")
    coef_df = pd.DataFrame(
        {
            "coef": [1.0],
            "se": [0.2],
            "pval": [0.001],
        },
        index=pd.Index(["MKT"], name="factor"),
    )
    r.add_model(coef_df, n_obs=60, r2=0.5, dep_var="A")
    md = r.to_markdown()
    assert isinstance(md, str)
    assert "MKT" in md
    assert "1.0000" in md or "1.0" in md


# ── TimeSeriesRegression 基本构造 ─────────────────────────────────────


def test_time_series_regression_init():
    ts = TimeSeriesRegression()
    assert ts.result is None or hasattr(ts, "result")


def test_cross_sectional_regression_init():
    cs = CrossSectionalRegression()
    # 内部属性：result / risk_premia / grs_stat / grs_pval
    assert hasattr(cs, "result")
    assert hasattr(cs, "risk_premia")
    assert hasattr(cs, "grs_stat")
    assert hasattr(cs, "grs_pval")


def test_gmm_estimator_init():
    g = GMMEstimator()
    assert hasattr(g, "fit") or hasattr(g, "estimate")


def test_lasso_factor_selector_init():
    l = LassoFactorSelector()
    assert hasattr(l, "fit")


def test_esg_alpha_test_init():
    esg = ESGAlphaTest()
    assert hasattr(esg, "fit") or hasattr(esg, "test")


def test_factor_model_comparison_init():
    c = FactorModelComparison()
    assert hasattr(c, "compare") or hasattr(c, "run")


# ── BaseFactorModel 数据校验 ─────────────────────────────────────────


def test_base_factor_model_validate_data_raises_on_empty_dates():
    """日期不重叠时 raise ValueError。"""
    bm = BaseFactorModel()
    bm.factors = ["MKT"]
    returns = pd.DataFrame({"A": [0.01, 0.02]}, index=pd.date_range("2024-01-01", periods=2))
    factors = pd.DataFrame({"MKT": [0.01]}, index=pd.date_range("2023-01-01", periods=1))
    with pytest.raises(ValueError, match="没有共同的日期索引"):
        bm._validate_data(returns, factors)


def test_base_factor_model_validate_data_raises_on_missing_factor():
    bm = BaseFactorModel()
    bm.factors = ["MKT", "SMB"]
    returns = pd.DataFrame({"A": [0.01]}, index=pd.date_range("2024-01-01", periods=1))
    factors = pd.DataFrame({"MKT": [0.01]}, index=pd.date_range("2024-01-01", periods=1))
    with pytest.raises(ValueError, match="缺少因子"):
        bm._validate_data(returns, factors)


def test_base_factor_model_validate_data_ok():
    bm = BaseFactorModel()
    bm.factors = ["MKT"]
    returns = pd.DataFrame({"A": [0.01, 0.02]}, index=pd.date_range("2024-01-01", periods=2))
    factors = pd.DataFrame({"MKT": [0.01, 0.02]}, index=pd.date_range("2024-01-01", periods=2))
    r, f = bm._validate_data(returns, factors)
    assert len(r) == 2
    assert "MKT" in f.columns


# ── GRS test 直接调用（不需要依赖网络） ──────────────────────────────


def test_grs_test_returns_tuple():
    """GRS 检验返回 (F-stat, p-value) 元组。"""
    rng = np.random.default_rng(42)
    n_assets = 3
    n_periods = 60
    n_factors = 2
    # 零假设下 alpha = 0。alphas N x 1, mean_excess K x 1
    alphas = np.zeros((n_assets, 1))
    cov_alpha = np.eye(n_assets) * 0.01
    mean_excess = rng.normal(0, 0.01, (n_factors, 1))
    cov_excess = np.eye(n_factors) * 0.01
    F, p = _grs_test(alphas, cov_alpha, mean_excess, cov_excess, n_periods, n_assets, n_factors)
    assert isinstance(F, float)
    assert isinstance(p, float)
    # 零假设下 F 应该接近 0，p 接近 1
    assert p > 0.05
    assert F >= 0


def test_grs_test_rejects_significant_alphas():
    """alpha 显著时 GRS 应该拒绝零假设。"""
    rng = np.random.default_rng(42)
    n_assets = 3
    n_periods = 60
    n_factors = 2
    alphas = np.array([[0.05], [-0.05], [0.05]])  # 显著 alpha, N x 1
    cov_alpha = np.eye(n_assets) * 0.0001  # 低方差（alpha 估计精确）
    mean_excess = rng.normal(0, 0.01, (n_factors, 1))
    cov_excess = np.eye(n_factors) * 0.01
    F, p = _grs_test(alphas, cov_alpha, mean_excess, cov_excess, n_periods, n_assets, n_factors)
    assert F > 0
    # alpha 显著 + 低方差 → GRS 拒绝零假设（p < 0.05）
    assert p < 0.05
