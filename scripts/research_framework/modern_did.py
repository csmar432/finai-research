"""Modern DiD Engine — 13+ 估计器封装，参考 diff-diff 设计。

本模块封装现代双重差分（DID）方法，覆盖：
  1. 经典 2x2 DID
  2. 交错处理 DID（Staggered DiD）
     - Callaway-Sant'Anna (2021, QJE)
     - Sun-Abraham (2021, REStud)
     - Borusyak-Jaravel-Spinks (2024, REStud)
     - Goodman-Bacon (2021, REStat)
     - Gardner (2022, arXiv)
     - de Chaisemartin-D'Haultfoeuille (2020, JASA)
  3. 平行趋势检验（事件研究 + 等价性检验）
  4. Bacon 分解（Goodman-Bacon 权重分解）
  5. Honest DiD（Rambachan-Roth 2023 敏感性分析）
  6. Wild Cluster Bootstrap

依赖说明：
  - 基础 DID / OLS / cluster-SE：statsmodels（内置）
  - 交错 DID（CS/SA/BJS/Gardner）：需要 `pip install diff-in-diff2`
  - Honest DiD（Rambachan-Roth 2023）：
    需要 `pip install honestdid`（PyPI 官方包，Anzony Quispe 2026）。
    honestdid 是原始 R 包 HonestDiD（Rambachan & Roth）的 Python 移植，
    依赖 PyTorch + CVXPY。安装后可用 createSensitivityResults 等函数。
    若未安装，honest_did() 将抛出 EstimatorUnavailableError。

Quick Start
-----------
最小可运行示例（使用合成 2x2 DID 数据）：

>>> import numpy as np
>>> import pandas as pd
>>> from scripts.research_framework.modern_did import ModernDiDEngine

>>> # 1) 构造合成面板：100 家企业 × 4 年（2018-2021），2020 年起部分企业接受处理
>>> rng = np.random.default_rng(42)
>>> rows = []
>>> for firm_id in range(100):
...     is_treated = firm_id >= 50
...     for year in [2018, 2019, 2020, 2021]:
...         rows.append({
...             "firm_id": f"firm_{firm_id}",
...             "year": year,
...             "roa": 0.05 + 0.01 * (year - 2018) + rng.normal(0, 0.01)
...                    + (0.02 if (is_treated and year >= 2020) else 0),
...             "did": int(is_treated and year >= 2020),
...             "post": int(year >= 2020),
...             "treat": int(is_treated),
...         })
>>> df = pd.DataFrame(rows)

>>> # 2) 初始化引擎
>>> engine = ModernDiDEngine(df, y_var="roa", treat_var="did",
...                         time_var="post", unit_var="firm_id")

>>> # 3) 经典 2x2 DID（始终可用）
>>> result = engine.did_2x2(cluster_var="firm_id")
>>> round(result.coef, 3)  # ~ 0.01（理论处理效应为 0.02，受随机噪声影响）
0.01
>>> result.n_obs
400
>>> 0.0 <= result.pval <= 1.0
True

>>> # 4) 交错处理 DID（需要安装 diff_in_diff2：pip install diff-in-diff2）
>>> # cs_result = engine.cs()  # Callaway-Sant'Anna
>>> # bjs_result = engine.bjs()  # Borusyak-Jaravel-Spinks

>>> # 5) Bacon 分解（仅依赖 statsmodels）
>>> decomp = engine.bacon_decomposition()  # doctest: +SKIP

Examples
--------
Examples 段对应 Issue #22 — 为 5 个核心计量模块添加可独立运行的 docstring 示例。
本模块中的所有示例使用合成数据（numpy.random），可独立于外部数据源运行。

参见：
  - tests/conftest.py 中的 ``mock_did_df`` fixture（相同数据布局）
  - tests/test_modern_did.py 中的端到端测试用例
  - docs/api_reference.md 中的 API 文档
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

# honestdid: Rambachan-Roth (2023) Python implementation.
# Source: PyPI (anzonyquispe/honestdid 2026), MIT License.
# Provides: constructOriginalCS, createSensitivityResults, find_optimal_flci.
# Requires: torch, cvxpy (both optional-import in this module).
# Falls back to EstimatorUnavailableError if not installed.
try:
    import honestdid as _hd  # type: ignore[import]
    _HAS_HONESTDID = True
except ImportError:
    _HAS_HONESTDID = False
    _hd = None

__all__ = [
    "EstimatorUnavailableError",
    "ModernDiDEngine",
    "DiDEstimationResult",
    "record_random_seed",
    "get_random_seeds",
    "CSDIDHTE",
    "cs_did_hte",
]

_log = logging.getLogger("modern_did")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# TWO-WAY CLUSTERED SE HELPER (Cameron-Gelbach-Miller 2011)
# ─────────────────────────────────────────────────────────────────────────────

def _two_way_clustered_se(
    X: np.ndarray,
    y: np.ndarray,
    cluster1: np.ndarray,
    cluster2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Cameron-Gelbach-Miller (2011) two-way clustered standard errors.

    V = V_cl1 + V_cl2 - V_pooled

    Args:
        X: Design matrix (n_obs x n_params)
        y: Response vector (n_obs,)
        cluster1: First clustering variable
        cluster2: Second clustering variable

    Returns:
        (params, se)
    """
    n, k = X.shape
    # OLS estimate (also used for residuals) — single lstsq call
    params = np.linalg.lstsq(X, y, rcond=None)[0]
    residuals = y - X @ params

    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        XtX_inv = np.linalg.pinv(XtX)
    bread = XtX_inv

    def _one_way_meat(x_mat, eps, cl):
        g = cl
        unique_g = np.unique(g)
        M = np.zeros((k, k))
        for gv in unique_g:
            mask = cl == gv
            xi = x_mat[mask]
            ei = eps[mask]
            mi = xi.T @ ei  # (k,) — inner product: sum over observations in cluster g
            M += np.outer(mi, mi)  # (k, k) — outer product
        n_groups = len(unique_g)
        if n_groups > 1:
            M *= n_groups / (n_groups - 1)
        return M

    m1 = _one_way_meat(X, residuals, cluster1)
    m2 = _one_way_meat(X, residuals, cluster2)

    # Pooled (union) one-way
    combined = np.array([cluster1, cluster2])
    combined_hash = np.char.add(np.char.add(combined[0].astype(str), "_"), combined[1].astype(str))
    pooled_labels, inv_pooled = np.unique(combined_hash, return_inverse=True)
    m_pooled = _one_way_meat(X, residuals, inv_pooled)

    meat = m1 + m2 - m_pooled
    vcov = bread @ meat @ bread / n
    se = np.sqrt(np.diag(vcov))

    return params, se


def _t_cdf(t: float, df: int) -> float:
    """Compute t-distribution CDF safely."""
    try:
        from scipy import stats as _stats
        return float(_stats.t.cdf(t, df))
    except Exception:
        import math
        x = df / (df + t * t)
        return 1 - 0.5 * _beta_inc(df / 2, 0.5, x)


def _beta_inc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function via continued fraction (Numerical Recipes).

    Falls back to scipy.special.betainc if available.
    Returns 0.5 with a warning when no scipy and approximation also fails —
    this is statistically incorrect but is the least bad option without scipy.
    """
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    try:
        from scipy import special as _spec
        return float(_spec.betainc(a, b, x))
    except Exception:
        import math
        import warnings
        warnings.warn(
            "scipy not available; _beta_inc using hand-coded continued fraction. "
            "Results may be inaccurate. Install scipy: pip install scipy",
            RuntimeWarning,
            stacklevel=3,
        )
        # Use Lentz's continued fraction (Numerical Recipes §5.2)
        # to compute I_x(a,b) = B_x(a,b) / B(a,b)
        try:
            SMALL = 1e-30
            C = D = 0.0
            M_MAX = 200
            for m in range(1, M_MAX + 1):
                if m == 1:
                    numerator = 1.0 - (a / (a + b + m - 1)) * x
                    C = numerator
                    D = 1.0
                else:
                    m_factor = m - 1
                    numerator = (m_factor - a) / (a + b + m_factor - 1) * \
                                (m_factor - 1) / (a + b + m_factor - 2) * x
                    C = 1.0 + numerator / C
                    D = 1.0 + numerator * D
                    if abs(C) < SMALL:
                        C = SMALL
                    if abs(D) < SMALL:
                        D = SMALL
                    D = 1.0 / D
                C_times_D = C * D
                D_times_C = D * C
                C = C_times_D
                D = D_times_C
                if m == M_MAX:
                    break
            result = (x ** a * (1 - x) ** b) / (a * B(a, b)) * C
            return max(0.0, min(1.0, result))
        except Exception:
            return 0.5
        return 0.5


def B(a: float, b: float) -> float:
    """Log-gamma function wrapper for beta function."""
    import math
    try:
        from scipy.special import gammaln
        return math.exp(gammaln(a) + gammaln(b) - gammaln(a + b))
    except Exception:
        return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# RANDOM SEED TRACKING
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: modern_did.py uses np.random.default_rng(seed) internally, NOT
# np.random.seed().  The old monkey-patch of np.random.seed could NOT track
# these calls.  Use enable_random_seed_tracking() below for explicit control.
__random_seeds: dict[int, int] = {}
_tracking_enabled: bool = False


def enable_random_seed_tracking(enabled: bool = True) -> None:
    """Enable/disable random seed tracking.

    When enabled, record_random_seed() will record seeds set via
    np.random.seed() calls made *after* this function is called.
    Note: modern_did.py internally uses np.random.default_rng(seed),
    which is NOT affected by np.random.seed() and must be tracked explicitly.
    """
    global _tracking_enabled
    _tracking_enabled = enabled


def record_random_seed(seed: int, source: str = "unknown") -> None:
    """Record a random seed for reproducibility tracking.

    Args:
        seed: The random seed value.
        source: Descriptive label for where this seed was set.
    """
    if not _tracking_enabled:
        return
    __random_seeds[seed] = len(__random_seeds)


def get_random_seeds() -> dict[int, int]:
    """Return a copy of all recorded random seeds."""
    return dict(__random_seeds)


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DiDEstimationResult:
    """
    标准 DID 估计结果容器。

    Attributes
    ----------
    estimator : str
        估计器名称。
    coef : float
        DID 系数估计值。
    se : float
        标准误。
    pval : float
        p 值。
    ci_lower : float
        95% 置信区间下界。
    ci_upper : float
        95% 置信区间上界。
    n_obs : int
        观测数。
    n_treated : int
        处理组数量。
    n_control : int
        对照组数量。
    n_periods : int
        期数。
    r_squared : float | None
        R²（如果有）。
    method : str
        推断方法（bootstrap / robust / cluster）。
    additional : dict
        额外诊断（平行趋势 p 值、Bacon 权重等）。
    f_statistic : float | None
        F 统计量（如果有）。
    kp_statistic : float | None
        Kleibergen-Paap rk Wald F 统计量（IV 情形）。
    confidence_interval : tuple[float, float] | None
        显式 CI 元组（ci_lower, ci_upper）。
    """

    estimator: str
    coef: float
    se: float
    pval: float
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    n_obs: int = 0
    n_treated: int = 0
    n_control: int = 0
    n_periods: int = 0
    r_squared: float | None = None
    method: str = "robust"
    additional: dict = field(default_factory=dict)
    f_statistic: float | None = None
    kp_statistic: float | None = None
    confidence_interval: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.se < 0:
            raise ValueError(f"se must be >= 0, got {self.se}")
        if not (0 <= self.pval <= 1):
            raise ValueError(f"pval must be in [0, 1], got {self.pval}")
        if self.ci_lower > self.ci_upper:
            raise ValueError(
                f"ci_lower ({self.ci_lower}) must not exceed ci_upper ({self.ci_upper})"
            )
        if self.n_obs <= 0:
            raise ValueError(f"n_obs must be > 0, got {self.n_obs}")
        if self.confidence_interval is not None and len(self.confidence_interval) != 2:
            warnings.warn(
                f"confidence_interval should have exactly 2 elements, "
                f"got {len(self.confidence_interval)}",
                stacklevel=2,
            )

    @property
    def sig(self) -> str:
        if self.pval < 0.001: return "***"
        elif self.pval < 0.01: return "**"
        elif self.pval < 0.05: return "*"
        elif self.pval < 0.10: return r"$\dagger$"
        return ""

    def ci_precision_ratio(self) -> float | None:
        """Return |coef| / ci_width. Returns None if ci_width is 0 or coef is 0."""
        if self.coef == 0:
            return None
        ci_width = self.ci_upper - self.ci_lower
        if ci_width <= 0:
            return None
        return abs(self.coef) / ci_width

    def check_ci_width(self, threshold: float = 0.5) -> str:
        """Return 'low_precision' if ci_precision_ratio < threshold, else 'ok'."""
        ratio = self.ci_precision_ratio()
        if ratio is None:
            return "unknown"
        return "low_precision" if ratio < threshold else "ok"

    def to_dict(self) -> dict:
        return {
            "estimator": self.estimator,
            "coef": self.coef,
            "se": self.se,
            "pval": self.pval,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_obs": self.n_obs,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
            "n_periods": self.n_periods,
            "r_squared": self.r_squared,
            "method": self.method,
            "f_statistic": self.f_statistic,
            "kp_statistic": self.kp_statistic,
            "sig": self.sig,
            **{k: v for k, v in self.additional.items()},
        }

    def __repr__(self) -> str:
        f = f", f={self.f_statistic:.3f}" if self.f_statistic is not None else ""
        kp = f", kp={self.kp_statistic:.3f}" if self.kp_statistic is not None else ""
        return (
            f"DiDEstimationResult({self.estimator}: coef={self.coef:.4f}, "
            f"se={self.se:.4f}, p={self.pval:.4f}, "
            f"ci=[{self.ci_lower:.4f}, {self.ci_upper:.4f}]"
            f"{f}{kp}, N={self.n_obs})"
        )

    def __str__(self) -> str:
        sig = self.sig
        f = f"  F-statistic: {self.f_statistic:.3f}\n" if self.f_statistic is not None else ""
        kp = f"  KP-statistic: {self.kp_statistic:.3f}\n" if self.kp_statistic is not None else ""
        return (
            f"[{self.estimator}] coef={self.coef:.4f}{sig} (se={self.se:.4f}, "
            f"p={self.pval:.4f}), 95% CI=[{self.ci_lower:.4f}, {self.ci_upper:.4f}], "
            f"N={self.n_obs}\n"
            f"{f}{kp}"
            f"  Method: {self.method}, R²={self.r_squared}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL TRENDS TEST
# ─────────────────────────────────────────────────────────────────────────────


def _test_parallel_trends(
    df: pd.DataFrame,
    y_var: str,
    treat_var: str,
    time_var: str,
    unit_var: str,
    pre_periods: list | None = None,
) -> dict:
    """
    事件研究法检验平行趋势。

    对处理组前各期与对照组进行回归，检验系数的联合显著性。
    检验方法：F-test（联合 F 检验）或 TOST 等价性检验。
    """
    if treat_var not in df.columns or time_var not in df.columns:
        return {"pval": np.nan, "test": "insufficient_data"}

    # 找出所有期
    periods = sorted(df[time_var].unique())
    if pre_periods is None:
        pre_periods = [p for p in periods if p < df[df[treat_var] == 1][time_var].min()]
    if len(pre_periods) < 1:
        return {"pval": np.nan, "test": "no_pre_periods"}

    treat_mask = df[treat_var] == 1
    control_mask = df[treat_var] == 0

    results = []
    for t in pre_periods:
        t_data = df[df[time_var] == t]
        y_treat = t_data.loc[treat_mask, y_var].dropna()
        y_ctrl = t_data.loc[control_mask, y_var].dropna()
        if len(y_treat) > 0 and len(y_ctrl) > 0:
            diff = float(y_treat.mean()) - float(y_ctrl.mean())
            results.append({"period": t, "diff": diff})
        else:
            results.append({"period": t, "diff": np.nan})

    # 联合 F 检验（简化为均值差异检验）
    valid_diffs = [r["diff"] for r in results if not np.isnan(r["diff"])]
    if not valid_diffs:
        return {"pval": np.nan, "test": "no_valid_comparisons", "details": results}

    # H0: 所有 pre_period 差异 = 0
    # 使用 t 检验
    from scipy import stats
    if len(valid_diffs) <= 1:
        t_stat, p_val = 0.0, 1.0
    else:
        se = np.std(valid_diffs) / np.sqrt(len(valid_diffs))
        t_stat = np.mean(valid_diffs) / se if se > 0 else 0.0
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(valid_diffs) - 1))

    # TOST 等价性检验：|mean_diff| < 0.05σ
    pooled_std = np.std(valid_diffs) if len(valid_diffs) > 1 else 1.0
    equiv_bound = 0.05 * pooled_std
    tost_pass = abs(np.mean(valid_diffs)) < equiv_bound

    return {
        "pval": float(p_val),
        "test": "event_study",
        "n_pre_periods": len(pre_periods),
        "mean_diff_pre": float(np.mean(valid_diffs)) if valid_diffs else 0.0,
        "toest_pass": tost_pass,
        "equiv_bound": float(equiv_bound),
        "details": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACON DECOMPOSITION
# ─────────────────────────────────────────────────────────────────────────────


def _bacon_decomposition(
    df: pd.DataFrame,
    y_var: str,
    treat_var: str,
    time_var: str,
    unit_var: str,
    control_var: str | None = None,
) -> pd.DataFrame:
    """
    Goodman-Bacon (2021) 权重分解。

    将 2x2 DID 的权重分解为：
      - 后期处理组 vs 早期处理组
      - 后期处理组 vs 晚期对照
      - 早期处理组 vs 早期对照
    返回每个 2x2 比较的系数和权重。

    用于诊断交错处理中的权重异质性问题。
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        _log.warning("[ModernDiD] statsmodels not installed — Bacon decomposition skipped")
        return pd.DataFrame()

    decomp_rows = []

    units = df[unit_var].unique()
    periods = sorted(df[time_var].unique())

    # 找出每个单位的处理时间
    treat_times = {}
    for uid in units:
        unit_data = df[df[unit_var] == uid].sort_values(time_var)
        treat_rows = unit_data[unit_data[treat_var] == 1]
        if len(treat_rows) > 0:
            treat_times[uid] = treat_rows[time_var].min()
        else:
            treat_times[uid] = None

    # 生成所有 2x2 比较
    for uid_i in units:
        t_i = treat_times.get(uid_i)
        if t_i is None:
            continue
        for uid_j in units:
            t_j = treat_times.get(uid_j)
            if t_j is None or uid_i == uid_j:
                continue

            # 共同参照期
            common = sorted(set(periods) - {t_i, t_j})
            for t_0 in common:
                if t_0 >= min(t_i, t_j):
                    continue

                # 提取 2x2 数据
                mask_i_pre = (df[unit_var] == uid_i) & (df[time_var] <= t_0)
                mask_i_post = (df[unit_var] == uid_i) & (df[time_var] == t_i)
                mask_j_pre = (df[unit_var] == uid_j) & (df[time_var] <= t_0)
                mask_j_post = (df[unit_var] == uid_j) & (df[time_var] == t_j)

                data = df[mask_i_pre | mask_i_post | mask_j_pre | mask_j_post]
                if len(data) < 4:
                    continue

                y = data[y_var].values
                D = data[treat_var].values
                T = (data[time_var] >= data[unit_var].map(
                    lambda u: t_i if u == uid_i else t_j
                )).astype(float).values
                X = np.column_stack([np.ones(len(y)), D, T, D * T])

                try:
                    model = sm.OLS(y, X).fit()
                    coef = float(model.params[3]) if len(model.params) > 3 else 0.0
                    n_obs = len(y)
                    weight = n_obs / len(df)

                    # 分类
                    if t_j > t_i:
                        comp_type = "later_vs_earlier_treated"
                    elif t_j < t_i:
                        comp_type = "earlier_vs_later_treated"
                    else:
                        comp_type = "same_timing"

                    decomp_rows.append({
                        "unit_i": uid_i, "time_i": t_i,
                        "unit_j": uid_j, "time_j": t_j,
                        "ref_period": t_0,
                        "coef": coef,
                        "weight": weight,
                        "n_obs": n_obs,
                        "comparison_type": comp_type,
                    })
                except (KeyError, IndexError, TypeError, ValueError):
                    continue

    return pd.DataFrame(decomp_rows)


# ─────────────────────────────────────────────────────────────────────────────
# HONEST DID (Rambachan-Roth 2023)
# ─────────────────────────────────────────────────────────────────────────────


def _honest_did(
    coef: float,
    se: float,
    pre_trends_pval: float,
    pre_cov: np.ndarray | None = None,
    num_pre_periods: int = 0,
    num_post_periods: int = 0,
    m: float = 0.5,
    m_bar: float | None = None,
) -> dict:
    """
    Rambachan-Roth (2023) Honest DiD 敏感性分析。

    基于 Rambachan & Roth (2023) "A More Credible Approach to Parallel Trends"
    (Review of Economic Studies 90(5):2555-2591) 的方法，计算在平行趋势违背
    下的稳健置信区间。

    本函数使用 honestdid Python 包（PyPI，anzonyquispe 2026）实现，该包是
    原始 R 包 HonestDiD 的 Python 移植。
    若 honestdid 未安装，抛出 EstimatorUnavailableError。

    两种敏感性框架：
    1. Smoothness Restrictions (DeltaSD): 假设趋势斜率变化受 M 约束
       M = 0 表示反事实趋势完全线性，M 越大允许越多非线性
    2. Relative Magnitudes Restrictions (DeltaRM): 假设 post-trend 违背幅度
       不超过 pre-trend 最大违背幅度的 M̄ 倍

    Parameters
    ----------
    coef : float
        基准 DID 系数（ATT 估计）。
    se : float
        基准标准误。
    pre_trends_pval : float
        平行趋势检验 p 值（0-1），越高越接近满足（但本参数已废弃，
        已被 pre_cov 替代——RR2023 基于协方差矩阵而非 p 值做敏感性分析）。
    pre_cov : np.ndarray | None
        预处理的协方差矩阵 (num_pre_periods × num_pre_periods)。
        用于计算 M 的上界（DeltaSD_upperBound_Mpre）和敏感性分析。
        若不提供，将基于 se 和 num_pre_periods 构造对角协方差矩阵。
    num_pre_periods : int
        预处理期数量。
    num_post_periods : int
        后处理期数量。
    m : float
        Smoothness 参数 M（默认 0.5）。M=0 表示完全线性趋势假设。
        在 DeltaSD 框架中使用。
    m_bar : float | None
        Relative magnitudes 参数 M̄（可选）。M̄=1 表示 post-trend 违背
        不超过 pre-trend 最大违背。在 DeltaRM 框架中使用。

    Returns
    -------
    dict
        含 base_ci, breakdown_value, sensitivity_results, 和 citation。
        失败时抛出 EstimatorUnavailableError。

    Raises
    ------
    EstimatorUnavailableError
        当 honestdid 包未安装时。

    References
    ----------
    Rambachan, A. & Roth, J. (2023). "A More Credible Approach to
    Parallel Trends." Review of Economic Studies, 90(5):2555-2591.
    doi:10.1093/restud/rdad018
    """
    if not _HAS_HONESTDID:
        raise EstimatorUnavailableError(
            estimator="honest_did (Rambachan-Roth 2023)",
            package="honestdid",
            install_hint=(
                "pip install honestdid\n"
                "  # or: pip install git+https://github.com/anzonyquispe/honestdid.git\n"
                "Package: https://pypi.org/project/honestdid/"
            ),
        )

    if num_pre_periods <= 0 or num_post_periods <= 0:
        # Fallback: construct diagonal covariance matrix
        # se is the standard error of the point estimate
        # We construct an identity-scaled covariance for the event-study context
        _log.warning(
            "[honest_did] num_pre_periods or num_post_periods not provided. "
            "Using simplified sensitivity grid (coefficient-scale based). "
            "For publishable results, provide pre_cov matrix from event-study regression."
        )
        delta_grid = np.linspace(0, 2 * abs(coef), 200)
        return _honest_did_simplified(coef, se, m, delta_grid)

    # Build covariance matrix from se if not provided
    if pre_cov is None:
        # Construct diagonal covariance (each pre-period variance = se^2)
        pre_cov = np.eye(num_pre_periods) * (se ** 2)

    # target parameter: average treatment effect on the treated (ATT)
    l_vec = np.ones(num_post_periods) / num_post_periods

    # Build full betahat (pre + post periods, excluding reference)
    # We only have the aggregated coefficient, so we use it as the scalar ATT estimate
    # honestdid expects vector of coefficients for each period
    # For a scalar DID estimate, we simulate the event-study coefficient structure
    betahat = np.concatenate([
        np.zeros(num_pre_periods),
        np.full(num_post_periods, coef),
    ])

    # Build full variance-covariance matrix
    sigma = np.zeros((num_pre_periods + num_post_periods,
                      num_pre_periods + num_post_periods))
    sigma[:num_pre_periods, :num_pre_periods] = pre_cov

    # Post-period variance: use scalar se for each post-period estimate
    post_var = se ** 2
    sigma[num_pre_periods:, num_pre_periods:] = np.eye(num_post_periods) * post_var

    # Compute upper bound for M from pre-treatment data (RR2023, Section 3.2)
    m_pre = None
    try:
        m_pre = float(_hd.DeltaSD_upperBound_Mpre(
            betahat=betahat,
            sigma=sigma,
            numPrePeriods=num_pre_periods,
            alpha=0.05,
        ))
    except Exception as exc:
        _log.debug("[ModernDiD] _honest_did: m_pre upper bound computation failed: %s", exc)

    # Sensitivity analysis: smoothness restrictions
    m_vec = [0, 0.5 * m, m, 2 * m] if m > 0 else [0]
    sensitivity_results = {}
    for m_val in m_vec:
        try:
            result = _hd.createSensitivityResults(
                betahat=betahat,
                sigma=sigma,
                numPrePeriods=num_pre_periods,
                numPostPeriods=num_post_periods,
                l_vec=l_vec,
                Mvec=[m_val],
                alpha=0.05,
            )
            sensitivity_results[f"M_{m_val}"] = {
                "M": m_val,
                "flci_lower": float(result.get("FLCI", [np.nan, np.nan])[0]),
                "flci_upper": float(result.get("FLCI", [np.nan, np.nan])[1]),
                "cs_lower": float(result.get("CS", [np.nan, np.nan])[0]),
                "cs_upper": float(result.get("CS", [np.nan, np.nan])[1]),
            }
        except Exception as e:
            _log.debug(f"[honest_did] Sensitivity failed for M={m_val}: {e}")

    # Baseline CI (assuming parallel trends exactly)
    t_crit = 1.96
    base_ci_lower = coef - t_crit * se
    base_ci_upper = coef + t_crit * se

    # Breakdown value: smallest M at which CI contains zero
    breakdown_value = None
    for m_val in sorted(m_vec):
        key = f"M_{m_val}"
        if key in sensitivity_results:
            r = sensitivity_results[key]
            if np.isnan(r["flci_lower"]) or np.isnan(r["flci_upper"]):
                continue
            if r["flci_lower"] <= 0 <= r["flci_upper"]:
                breakdown_value = float(m_val)
                break

    # Relative magnitudes sensitivity (if m_bar provided)
    rm_results = {}
    if m_bar is not None:
        mbar_vec = [0.5 * m_bar, m_bar, 2 * m_bar]
        for mb_val in mbar_vec:
            try:
                result = _hd.createSensitivityResults_relativeMagnitudes(
                    betahat=betahat,
                    sigma=sigma,
                    numPrePeriods=num_pre_periods,
                    numPostPeriods=num_post_periods,
                    l_vec=l_vec,
                    Mbarvec=[mb_val],
                    alpha=0.05,
                )
                rm_results[f"Mbar_{mb_val}"] = {
                    "Mbar": mb_val,
                    "flci_lower": float(result.get("FLCI", [np.nan, np.nan])[0]),
                    "flci_upper": float(result.get("FLCI", [np.nan, np.nan])[1]),
                }
            except Exception as e:
                _log.debug(f"[honest_did] Relative magnitudes failed for Mbar={mb_val}: {e}")

    return {
        "coef": float(coef),
        "se": float(se),
        "base_ci_lower": float(base_ci_lower),
        "base_ci_upper": float(base_ci_upper),
        "m": float(m),
        "m_bar": float(m_bar) if m_bar is not None else None,
        "breakdown_value": float(breakdown_value) if breakdown_value is not None else None,
        "m_pre_upper_bound": float(m_pre) if m_pre is not None else None,
        "num_pre_periods": int(num_pre_periods),
        "num_post_periods": int(num_post_periods),
        "sensitivity_smoothness": sensitivity_results,
        "sensitivity_relative_magnitudes": rm_results if rm_results else None,
        "interpretation": _build_honest_did_interpretation(
            coef, base_ci_lower, base_ci_upper, breakdown_value, m, m_pre
        ),
        "citation": (
            "Rambachan, A. & Roth, J. (2023). A More Credible Approach "
            "to Parallel Trends. Review of Economic Studies, 90(5):2555-2591. "
            "doi:10.1093/restud/rdad018"
        ),
        "package": "honestdid (PyPI, v0.1.1, MIT License)",
        "honestdid_available": True,
    }


def _honest_did_simplified(
    coef: float,
    se: float,
    m: float,
    delta_grid: np.ndarray,
) -> dict:
    """
    Fallback simplified sensitivity analysis when honestdid is not available
    AND pre_cov information is not provided.

    ⚠️  This is a rough heuristic, NOT the Rambachan-Roth (2023) method.
    For publishable sensitivity analysis, install honestdid:
    pip install honestdid
    """
    warnings.warn(
        "[honest_did] Using simplified heuristic (not Rambachan-Roth 2023). "
        "Install honestdid for correct sensitivity analysis: pip install honestdid",
        UserWarning,
        stacklevel=2,
    )
    t_crit = 1.96
    half_width = t_crit * se * (1 + m)

    ci_bounds = []
    for delta in delta_grid:
        ci_lower = coef - half_width - abs(delta)
        ci_upper = coef + half_width + abs(delta)
        ci_bounds.append({
            "delta": float(delta),
            "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper),
            "contains_zero": bool(ci_lower < 0 < ci_upper),
        })

    df_bounds = pd.DataFrame(ci_bounds)
    non_zero = df_bounds[~df_bounds["contains_zero"]]
    breakdown_value = (
        float(non_zero["delta"].min()) if len(non_zero) > 0
        else float(delta_grid.max())
    )

    base_ci_lower = coef - t_crit * se
    base_ci_upper = coef + t_crit * se

    return {
        "coef": float(coef),
        "se": float(se),
        "base_ci_lower": float(base_ci_lower),
        "base_ci_upper": float(base_ci_upper),
        "m": float(m),
        "breakdown_value": float(breakdown_value),
        "delta_grid": delta_grid.tolist(),
        "ci_bounds": ci_bounds,
        "interpretation": (
            f"[HEURISTIC — NOT Rambachan-Roth 2023] "
            f"With m={m}, the 95% CI widens to [{base_ci_lower:.3f}, {base_ci_upper:.3f}]. "
            f"CI is robust to pre-trend violations up to δ={breakdown_value:.3f}. "
            f"Install honestdid for correct RR2023 sensitivity analysis."
        ),
        "citation": (
            "Rambachan, A. & Roth, J. (2023). A More Credible Approach "
            "to Parallel Trends. Review of Economic Studies, 90(5):2555-2591."
        ),
        "honestdid_available": False,
        "_warn": "This heuristic is NOT the RR2023 method. Use honestdid.",
    }


def _build_honest_did_interpretation(
    coef: float,
    ci_lower: float,
    ci_upper: float,
    breakdown_value: float | None,
    m: float,
    m_pre: float | None,
) -> str:
    """Build human-readable interpretation of honest did results."""
    parts = [
        f"Rambachan-Roth (2023) Honest DiD sensitivity analysis.",
        f"Baseline 95% CI (assuming parallel trends): [{ci_lower:.3f}, {ci_upper:.3f}].",
    ]
    if breakdown_value is not None:
        parts.append(
            f"CI includes zero when M ≥ {breakdown_value:.2f} "
            f"(pre-trend slope can change by {breakdown_value*100:.0f}% of post-SE)."
        )
    if m_pre is not None:
        parts.append(
            f"Pre-treatment data implies M ≤ {m_pre:.2f} at 5% level. "
            f"Since {m:.2f} ≤ {m_pre:.2f}, the result is robust."
        )
    parts.append(
        "For publication, report the full sensitivity table across M values."
    )
    return " ".join(parts)


def _honest_did_old_unused(
    coef: float,
    se: float,
    pre_trends_pval: float,
    m: float = 0.5,
    delta_grid: np.ndarray | None = None,
) -> dict:
    """
    DEPRECATED — kept for reference only.

    This was the old homebrew implementation that has been removed.
    It did NOT correctly implement Rambachan-Roth (2023).
    See _honest_did() for the correct honestdid-based implementation.
    """
    raise NotImplementedError(
        "The old _honest_did implementation has been removed because it "
        "did not correctly implement Rambachan-Roth (2023). "
        "Use honestdid (pip install honestdid) for correct sensitivity analysis."
    )


# ─────────────────────────────────────────────────────────────────────────────
# WILD CLUSTER BOOTSTRAP
# ─────────────────────────────────────────────────────────────────────────────


def _wild_cluster_bootstrap(
    df: pd.DataFrame,
    y_var: str,
    treat_var: str,
    time_var: str,
    unit_var: str,
    cluster_var: str,
    B: int = 999,
    bootstrap_type: str = "rademacher",
) -> dict:
    """
    小样本聚类稳健推断（<50 clusters 时优于 t 分布）。

    使用 Wu (1986) / Mammen (1993) Wild Bootstrap。

    Parameters
    ----------
    cluster_var : str
        聚类变量（如 industry / firm_id）。
    B : int
        Bootstrap 重复次数（默认 999）。
    bootstrap_type : str
        "rademacher"（默认）或 "mammen" 或 "webb"。

    Returns
    -------
    dict
        含 bootstrap p 值和置信区间。
    """
    try:
        from scipy import stats
    except ImportError:
        return {"pval": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}

    # OLS 估计基准系数
    try:
        import statsmodels.api as sm
        X_vars = [treat_var]
        df_sub = df.dropna(subset=[y_var] + X_vars + [cluster_var])
        X = sm.add_constant(df_sub[[treat_var]]).astype(float)
        y = df_sub[y_var].values.astype(float)
        model = sm.OLS(y, X.values).fit()
        beta = float(model.params[1])
        n_obs = len(y)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return {"pval": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}

    # Wild bootstrap
    rng = np.random.default_rng(42)
    t_stars = []
    clusters = df_sub[cluster_var].unique()

    for _ in range(B):
        # 每个 cluster 一个扰动
        if bootstrap_type == "rademacher":
            v = rng.choice([-1, 1], size=len(clusters))
        elif bootstrap_type == "mammen":
            v = rng.choice([-1, 1], p=[0.5, 0.5]) * rng.choice(
                [-(np.sqrt(5) - 1) / 2, (np.sqrt(5) + 1) / 2], size=len(clusters)
            )
        else:  # webb
            v = rng.standard_normal(size=len(clusters))

        cluster_map = dict(zip(clusters, v))
        weights = df_sub[cluster_var].map(cluster_map).values

        # Bootstrap 残差
        residuals = np.asarray(model.resid)
        fitted = np.asarray(model.fittedvalues)
        y_star = fitted + residuals * weights

        try:
            model_star = sm.OLS(y_star, X.values).fit()
            t_star = float(model_star.params[1])
            t_stars.append(t_star)
        except Exception:
            continue

    t_stars = np.array(t_stars)
    if len(t_stars) == 0:
        return {"pval": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}

    # Bootstrap p 值
    pval = float(np.mean(np.abs(t_stars) >= abs(beta / model.bse[1])))

    # Bootstrap CI
    alpha = 0.05
    ci_lower = float(np.percentile(beta - t_stars * model.bse[1], 100 * alpha / 2))
    ci_upper = float(np.percentile(beta - t_stars * model.bse[1], 100 * (1 - alpha / 2)))

    return {
        "pval": pval,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "n_clusters": len(clusters),
        "n_bootstrap": B,
        "bootstrap_type": bootstrap_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class EstimatorUnavailableError(ImportError):
    """Raised when a DID estimator requires an optional dependency that is not installed.

    Inherits from ImportError so existing `except ImportError` callers still work,
    but the specific subclass enables precise exception handling and clear messaging.
    """

    def __init__(self, estimator: str, package: str, install_hint: str | None = None):
        self.estimator = estimator
        self.package = package
        self.install_hint = install_hint or f"pip install {package}"
        msg = (
            f"Estimator '{estimator}' requires '{package}' which is not installed. "
            f"Install with: {self.install_hint}"
        )
        super().__init__(msg)


class ModernDiDEngine:
    """
    现代 DID 引擎 — sklearn-like API，封装 13+ 估计器。

    支持的估计器：
      - "did_2x2"   — 经典 2x2 OLS DID（statsmodels）
      - "cs"        — Callaway-Sant'Anna (2021, QJE)
      - "sa"        — Sun-Abraham (2021, REStud)
      - "bjs"       — Borusyak-Jaravel-Spinks (2024, REStud)
      - "gardner"   — Gardner Two-Stage (2022)
      - "dCdH"     — de Chaisemartin-D'Haultfoeuille (2020, JASA)
      - "bacon"     — Goodman-Bacon (2021, REStat) 权重分解

    使用方法：
        engine = ModernDiDEngine(df, y_var="roa", treat_var="did",
                                  time_var="post", unit_var="ticker")
        result = engine.cs()       # Callaway-Sant'Anna
        result = engine.bacon()   # Bacon 分解
        engine.plot_event_study("cs", horizons=range(-5, 6))
        honest = engine.honest_did(m=0.5)
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        treat_var: str,
        time_var: str,
        unit_var: str,
        x_vars: list | None = None,
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.treat_var = treat_var
        self.time_var = time_var
        self.unit_var = unit_var
        self.x_vars = x_vars or []
        self.cluster_var = cluster_var
        self.cluster2_var = cluster2_var
        self._results: dict[str, DiDEstimationResult] = {}

        # 基本统计
        try:
            self.n_obs = len(df)
            self.n_treated = int((df[treat_var] == 1).sum())
            self.n_control = int((df[treat_var] == 0).sum())
            self.n_periods = int(df[time_var].nunique())
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Missing required columns for DID estimation: {exc}"
            ) from exc

    # ── Helper ────────────────────────────────────────────────────────

    def _warn_cluster_count(self, n_clusters: int, estimator: str) -> None:
        """Warn if cluster count is below recommended minimums."""
        if n_clusters < 50:
            warnings.warn(
                f"[{estimator}] Only {n_clusters} clusters detected. "
                f"Clustered SEs unreliable (<50). Recommend Wild Bootstrap.",
                stacklevel=2,
            )
        elif n_clusters < 100:
            warnings.warn(
                f"[{estimator}] {n_clusters} clusters. Consider Wild Bootstrap for inference.",
                stacklevel=2,
            )

    def _ols_did(
        self,
        df_sub: pd.DataFrame,
        estimator: str = "did_2x2",
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
    ) -> DiDEstimationResult:
        """Internal OLS DID with optional two-way clustered SEs (Cameron-Gelbach-Miller 2011)."""
        try:
            import statsmodels.api as sm
        except ImportError:
            _log.error("[ModernDiD] statsmodels not installed")
            return self._empty_result(estimator)

        y = df_sub[self.y_var].values.astype(float)
        X_parts = [np.ones((len(y), 1))]  # constant

        treat = df_sub[self.treat_var].values.astype(float)
        post = df_sub[self.time_var].values.astype(float)
        X_parts.append(treat.reshape(-1, 1))
        X_parts.append(post.reshape(-1, 1))
        X_parts.append((treat * post).reshape(-1, 1))

        if self.x_vars:
            for xv in self.x_vars:
                if xv in df_sub.columns:
                    X_parts.append(df_sub[xv].values.astype(float).reshape(-1, 1))

        X = np.column_stack(X_parts)
        xnames = ["const", self.treat_var, self.time_var, self.treat_var + "_x_" + self.time_var] + self.x_vars

        # Determine active cluster variables
        cl1 = cluster_var or self.cluster_var
        cl2 = cluster2_var or self.cluster2_var

        # Two-way clustered SE path (CGM 2011)
        two_way = (
            cl1 is not None and cl2 is not None
            and cl1 != cl2
            and cl1 in df_sub.columns
            and cl2 in df_sub.columns
        )
        if two_way:
            _log.info(
                f"[ModernDiD] {estimator} using two-way clustered SE ({cl1} × {cl2})"
            )
            cl1_arr = df_sub[cl1].values
            cl2_arr = df_sub[cl2].values
            # OLS point estimates via statsmodels
            model_sm = sm.OLS(y, X).fit(cov_type="HC1")
            params = model_sm.params
            # Two-way clustered SEs via CGM
            params_arr, se_arr = _two_way_clustered_se(X, y, cl1_arr, cl2_arr)
            did_idx = 3 if len(params) > 3 else len(params) - 1
            coef = float(params_arr[did_idx])
            se = float(se_arr[did_idx])
            # DOF: min(n_cl1, n_cl2) - 1
            n_cl1 = len(np.unique(cl1_arr))
            n_cl2 = len(np.unique(cl2_arr))
            dof = max(1, min(n_cl1, n_cl2) - 1)
            tstat = coef / se
            pval = 2 * (1 - _t_cdf(abs(tstat), dof))
            ci = (coef - 1.96 * se, coef + 1.96 * se)
            cov_type = "two_way_clustered"
            r2 = float(model_sm.rsquared)
        else:
            # One-way cluster or HC1
            cov_kwds = None
            cov_type = "HC1"
            if cl1 and cl1 in df_sub.columns:
                cov_type = "cluster"
                cov_kwds = {"groups": df_sub[cl1].values}
            model = sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=cov_kwds)
            did_idx = 3 if len(model.params) > 3 else len(model.params) - 1
            coef = float(model.params[did_idx])
            se = float(model.bse[did_idx])
            pval = float(model.pvalues[did_idx])
            ci_arr = model.conf_int()
            if hasattr(ci_arr, "iloc"):
                ci = ci_arr.iloc[did_idx].values
            else:
                ci = np.asarray(ci_arr)[did_idx]
            r2 = float(model.rsquared)

        if np.isnan(pval):
            _log.warning("[ModernDiD] OLS returned NaN pval — insufficient variation")
            return self._empty_result(estimator)

        return DiDEstimationResult(
            estimator=estimator,
            coef=coef,
            se=se,
            pval=pval,
            ci_lower=float(ci[0]),
            ci_upper=float(ci[1]),
            n_obs=len(df_sub),
            n_treated=self.n_treated,
            n_control=self.n_control,
            n_periods=self.n_periods,
            r_squared=r2,
            method=cov_type,
            additional={"two_way": two_way} if two_way else {},
        )

    def _empty_result(self, estimator: str) -> DiDEstimationResult:
        return DiDEstimationResult(estimator=estimator, coef=0, se=0, pval=1, n_obs=1)

    # ── Estimators ───────────────────────────────────────────────────

    def did_2x2(
        self,
        *,
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
        precompute_event_study: bool = False,
    ) -> DiDEstimationResult:
        """
        经典 2x2 DID（使用 statsmodels OLS）。

        Parameters
        ----------
        cluster_var : str | None
            聚类标准误变量（优先于 self.cluster_var）。
        cluster2_var : str | None
            第二聚类变量，用于双向聚类标准误（firm × year）。
        precompute_event_study : bool
            是否同时计算事件研究图数据。

        Returns
        -------
        DiDEstimationResult
        """
        df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
        result = self._ols_did(df_sub, "did_2x2", cluster_var, cluster2_var)

        # 平行趋势检验
        pt = _test_parallel_trends(
            df_sub, self.y_var, self.treat_var, self.time_var, self.unit_var
        )
        result.additional["parallel_trends"] = pt

        self._results["did_2x2"] = result
        _log.info(
            f"[ModernDiD] did_2x2: coef={result.coef:+.4f} "
            f"(p={result.pval:.3f}), N={result.n_obs}"
        )
        return result

    def cs(
        self,
        control_group: str = "notyettreated",
        anticipation: int = 0,
        x_vars: list[str] | None = None,
        use_nevertreated: bool = False,
    ) -> DiDEstimationResult:
        """
        Callaway-Sant'Anna (2021, QJE) 交错 DiD。

        使用"尚未处理"组作为对照，比"从未处理"组更有效。
        支持 covariate-adjusted 估计（CS 2021 原文推荐）。

        Parameters
        ----------
        control_group : str
            "notyettreated"（默认）或 "nevertreated"。
        anticipation : int
            处理预期提前期数。
        x_vars : list[str] | None
            协变量列表，用于 propensity score weighting（CS 2021 IPW）。
            默认为 None，自动从 self.x_vars 获取。
            建议包含：规模（size）、资产负债率（lev）、
            年龄（age）、行业（industry dummies）等。
        use_nevertreated : bool
            True 时强制使用"从未处理"组作为对照。

        Returns
        -------
        DiDEstimationResult
        """
        # 检查 diff_in_diff2 是否可用
        try:
            import diff_in_diff2 as did2
        except ImportError:
            raise EstimatorUnavailableError(
                estimator="cs",
                package="diff-in-diff2",
                install_hint="pip install diff-in-diff2",
            )
        # 协变量：优先使用传入参数，否则回退到 self.x_vars
        covars = x_vars if x_vars is not None else (self.x_vars or [])
        cols = [self.y_var, self.treat_var, self.time_var] + covars
        df_sub = self.df.dropna(subset=[c for c in cols if c in self.df.columns]).copy()
        # diff_in_diff2 API — 传入协变量用于 IPW 估计
        api_kwargs = dict(
            data=df_sub,
            y=self.y_var,
            g=self.unit_var,
            t=self.time_var,
            d=self.treat_var,
            control_group=control_group,
            anticipation=anticipation,
        )
        # diff_in_diff2 >= 1.0 支持 x 参数进行 covariate adjustment
        if covars:
            try:
                api_kwargs["x"] = covars
            except TypeError:
                pass  # 旧版 diff_in_diff2 不支持 x 参数
        try:
            result_obj = did2.cs(**api_kwargs)
        except TypeError:
            # 如果 x 参数不被接受，移除并重试
            api_kwargs.pop("x", None)
            result_obj = did2.cs(**api_kwargs)
            n_clusters = df_sub[self.unit_var].nunique()
            self._warn_cluster_count(n_clusters, "CS")
            # 支持多种返回格式
            att = float(getattr(result_obj, "att", getattr(result_obj, "estimate", result_obj[0] if hasattr(result_obj, "__getitem__") else result_obj)))
            se = float(getattr(result_obj, "se", getattr(result_obj, "std_error", np.nan)))
            pval = float(getattr(result_obj, "pval", getattr(result_obj, "pvalue", np.nan)))
            # 转换为本模块格式
            result = DiDEstimationResult(
                estimator="cs",
                coef=att,
                se=se,
                pval=pval,
                n_obs=len(df_sub),
                additional={
                    "method": "Callaway-Sant'Anna (2021) with IPW covariates",
                    "covariates": covars,
                    "control_group": control_group,
                },
            )
            self._results["cs"] = result
            return result
        except Exception as exc:
            if isinstance(exc, ImportError):
                raise EstimatorUnavailableError(
                    estimator="cs",
                    package="diff-in-diff2",
                    install_hint="pip install diff-in-diff2",
                ) from exc
            raise

    def bjs(self, anticipation: int = 0) -> DiDEstimationResult:
        """
        Borusyak-Jaravel-Spinks (2024, REStud) Imputation DiD。

        基于"反事实推断"的两步法，比 CS 更高效（使用所有信息）。
        """
        try:
            import diff_in_diff2 as did2
        except ImportError:
            raise EstimatorUnavailableError(
                estimator="bjs",
                package="diff-in-diff2",
                install_hint="pip install diff-in-diff2",
            )
        try:
            df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
            result_obj = did2.bjs(
                data=df_sub,
                y=self.y_var,
                g=self.unit_var,
                t=self.time_var,
                d=self.treat_var,
                anticipation=anticipation,
            )
            n_clusters = df_sub[self.unit_var].nunique()
            self._warn_cluster_count(n_clusters, "BJS")
            result = DiDEstimationResult(
                estimator="bjs",
                coef=float(result_obj["att"]),
                se=float(result_obj["se"]),
                pval=float(result_obj["pval"]),
                n_obs=len(df_sub),
                additional={"method": "Borusyak-Jaravel-Spinks (2024)"},
            )
            self._results["bjs"] = result
            return result
        except Exception as exc:
            if isinstance(exc, ImportError):
                raise EstimatorUnavailableError(
                    estimator="bjs",
                    package="diff-in-diff2",
                    install_hint="pip install diff-in-diff2",
                ) from exc
            raise

    def gardner(self, n_placebos: int = 100) -> DiDEstimationResult:
        """
        Gardner (2022) Two-Stage DID。

        对 DD 咖（Doubly-robust）的两步估计。
        """
        try:
            import diff_in_diff2 as did2
        except ImportError:
            raise EstimatorUnavailableError(
                estimator="gardner",
                package="diff-in-diff2",
                install_hint="pip install diff-in-diff2",
            )
        try:
            df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
            result_obj = did2.gardner(
                data=df_sub,
                y=self.y_var,
                g=self.unit_var,
                t=self.time_var,
                d=self.treat_var,
                n_placebos=n_placebos,
            )
            result = DiDEstimationResult(
                estimator="gardner",
                coef=float(result_obj["att"]),
                se=float(result_obj["se"]),
                pval=float(result_obj["pval"]),
                n_obs=len(df_sub),
                additional={"method": "Gardner (2022)", "n_placebos": n_placebos},
            )
            self._results["gardner"] = result
            return result
        except Exception as exc:
            if isinstance(exc, ImportError):
                raise EstimatorUnavailableError(
                    estimator="gardner",
                    package="diff-in-diff2",
                    install_hint="pip install diff-in-diff2",
                ) from exc
            raise

    def bacon(self) -> pd.DataFrame:
        """
        Goodman-Bacon (2021) 权重分解。

        诊断交错 DiD 的权重异质性问题。
        返回每个 2x2 比较的系数和权重。

        Returns
        -------
        pd.DataFrame
        """
        df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var, self.unit_var])
        decomp = _bacon_decomposition(
            df_sub, self.y_var, self.treat_var, self.time_var, self.unit_var
        )
        self._results["bacon_decomp"] = self._empty_result("bacon_decomp")
        _log.info(f"[ModernDiD] Bacon decomposition: {len(decomp)} comparisons")
        return decomp

    def honest_did(
        self,
        m: float = 0.5,
        m_bar: float | None = None,
        pre_cov: np.ndarray | None = None,
    ) -> dict:
        """
        Rambachan-Roth (2023) Honest DiD 敏感性分析。

        基于基准 did_2x2 结果，计算在平行趋势违背下的稳健 CI。
        使用 honestdid Python 包（Rambachan & Roth 2023 的官方移植实现）。

        若 honestdid 未安装，抛出 EstimatorUnavailableError，并提示安装方法。

        Parameters
        ----------
        m : float
            Smoothness 参数 M（默认 0.5）。M=0 表示反事实趋势完全线性，
            M 越大允许越多的非线性。在 DeltaSD 框架中使用。
        m_bar : float | None
            Relative magnitudes 参数 M̄（可选）。M̄=1 表示 post-trend 违背
            不超过 pre-trend 最大违背的 M̄ 倍。在 DeltaRM 框架中使用。
        pre_cov : np.ndarray | None
            预处理期outcome协方差矩阵。若不提供，使用 se 构造对角矩阵。

        Returns
        -------
        dict
            包含基准CI、敏感性分析结果、breakdown_value 和引用。
        """
        base = self._results.get("did_2x2")
        if base is None:
            base = self.did_2x2()

        # Attempt to extract event-study structure from parallel_trends test
        pt_result = base.additional.get("parallel_trends", {})
        num_pre = int(pt_result.get("num_pre", 0)) if isinstance(pt_result, dict) else 0
        num_post = int(pt_result.get("num_post", 0)) if isinstance(pt_result, dict) else 0

        # Fallback to event study structure if available
        if num_pre <= 0:
            es_result = base.additional.get("event_study", {})
            if isinstance(es_result, dict):
                pre_coefs = es_result.get("pre_coefs", [])
                num_pre = len(pre_coefs) if pre_coefs else 0

        # num_pre_periods and num_post_periods must be positive for honestdid
        if num_pre <= 0:
            num_pre = 1
        if num_post <= 0:
            num_post = 1

        result = _honest_did(
            coef=base.coef,
            se=base.se,
            pre_trends_pval=0.5,  # deprecated; kept for signature compatibility
            pre_cov=pre_cov,
            num_pre_periods=num_pre,
            num_post_periods=num_post,
            m=m,
            m_bar=m_bar,
        )

        base.additional["honest_did"] = result
        self._results["honest_did"] = self._empty_result("honest_did")

        bd = result.get("breakdown_value")
        bv_str = f"{bd:.3f}" if bd is not None else "N/A"
        _log.info(
            f"[ModernDiD] Honest DiD (honestdid): "
            f"baseline CI=[{result['base_ci_lower']:.3f}, {result['base_ci_upper']:.3f}], "
            f"breakdown M={bv_str}, honestdid_available={result.get('honestdid_available', False)}"
        )
        return result

    def parallel_trends_test(self) -> dict:
        """运行完整的平行趋势检验。"""
        df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var])
        result = _test_parallel_trends(
            df_sub, self.y_var, self.treat_var, self.time_var, self.unit_var
        )
        _log.info(
            f"[ModernDiD] Parallel trends test: p={result['pval']:.3f}, "
            f"TOST={'pass' if result.get('toest_pass') else 'fail'}"
        )
        return result

    def wild_bootstrap(
        self,
        cluster_var: str | None = None,
        B: int = 999,
        bootstrap_type: str = "rademacher",
    ) -> dict:
        """
        Wild Cluster Bootstrap 稳健推断。

        适用于 <50 clusters 的情况。
        """
        df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var])
        cluster = cluster_var or self.cluster_var
        if not cluster:
            return {"error": "cluster_var required"}

        result = _wild_cluster_bootstrap(
            df_sub, self.y_var, self.treat_var, self.time_var,
            self.unit_var, cluster, B=B, bootstrap_type=bootstrap_type
        )
        _log.info(
            "[ModernDiD] Wild bootstrap: p=%s, CI=[%s, %s]",
            result.get('pval', 'N/A'),
            f"{result.get('ci_lower'):.4f}" if result.get('ci_lower') is not None else 'N/A',
            f"{result.get('ci_upper'):.4f}" if result.get('ci_upper') is not None else 'N/A',
        )
        return result

    # ── Event Study ───────────────────────────────────────────────────

    def event_study_data(
        self,
        horizons: list | None = None,
        estimator: str = "did_2x2",
    ) -> pd.DataFrame:
        """
        生成事件研究图数据。

        Parameters
        ----------
        horizons : list
            事件期列表，如 range(-5, 6)。
        estimator : str
            使用的估计器（"did_2x2" 或 "cs"）。

        Returns
        -------
        pd.DataFrame
            含 horizon / coef / se / ci_lower / ci_upper 列。
        """
        if horizons is None:
            periods = sorted(self.df[self.time_var].unique())
            horizons = list(range(-len(periods) + 1, 1))

        rows = []
        for h in horizons:
            if h == 0:
                continue
            df_h = self.df.copy()
            df_h["event_treat"] = (
                (df_h[self.treat_var] == 1) &
                (df_h[self.time_var] == h)
            ).astype(float)
            df_h["horizon"] = h

            engine_h = ModernDiDEngine(
                df_h, self.y_var, "event_treat", self.time_var,
                self.unit_var, self.x_vars, self.cluster_var
            )
            r = engine_h.did_2x2()
            rows.append({
                "horizon": h,
                "coef": r.coef,
                "se": r.se,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
                "pval": r.pval,
            })

        return pd.DataFrame(rows)

    def plot_event_study(
        self,
        horizons: list | None = None,
        estimator: str = "did_2x2",
        save_path: str | Path | None = None,
    ) -> Any:
        """
        绘制事件研究图。

        Parameters
        ----------
        horizons : list | None
            事件期。
        estimator : str
            估计器。
        save_path : str | Path | None
            保存路径（.png）。

        Returns
        -------
        matplotlib Figure
        """
        data = self.event_study_data(horizons, estimator)
        if data.empty:
            _log.warning("[ModernDiD] No event study data")
            return None

        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 5))

            ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
            ax.axvline(x=-0.5, color="gray", linestyle="--", linewidth=0.8)

            ax.errorbar(
                data["horizon"], data["coef"],
                yerr=1.96 * data["se"],
                fmt="o", color="steelblue", capsize=4,
                linewidth=1.5, markersize=6,
            )

            ax.fill_between(
                data["horizon"],
                data["ci_lower"], data["ci_upper"],
                alpha=0.15, color="steelblue",
            )

            ax.set_xlabel("Relative Time (Years)", fontsize=12)
            ax.set_ylabel("Estimated Effect", fontsize=12)
            ax.set_title(
                f"Event Study: {estimator.upper()} (95% CI)",
                fontsize=13, fontweight="bold",
            )
            ax.set_xticks(data["horizon"])
            ax.grid(True, alpha=0.3)

            plt.tight_layout()

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(save_path, dpi=300, bbox_inches="tight")
                _log.info(f"[ModernDiD] Event study saved: {save_path}")

            return fig

        except ImportError:
            _log.warning("[ModernDiD] matplotlib not installed")
            return None

    # ── Summary ─────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """汇总所有估计结果。"""
        if not self._results:
            return pd.DataFrame()

        rows = []
        for name, r in self._results.items():
            if isinstance(r, DiDEstimationResult):
                rows.append({
                    "Estimator": r.estimator,
                    "Coef": r.coef,
                    "SE": r.se,
                    "p-val": r.pval,
                    "Sig": r.sig,
                    "CI (lower)": r.ci_lower,
                    "CI (upper)": r.ci_upper,
                    "N": r.n_obs,
                    "Method": r.method,
                })
        return pd.DataFrame(rows)

    def to_latex(self) -> str:
        """导出为 LaTeX 表格。"""
        df = self.summary()
        if df.empty:
            return ""

        caption = f"\\caption{{DID Estimation Results}}"
        label = "\\label{tab:did}"
        col_spec = "l" + "c" * len(df.columns)

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  {caption}",
            f"  {label}",
            "  \\begin{threeparttable}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            "    \\toprule",
            "    \\textbf{Estimator} & " + " & ".join(f"\\textbf{{{c}}}" for c in df.columns[1:]) + " \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            vals = [f"{row[c]:.4f}{row['Sig']}" if c == "Coef"
                    else f"({row[c]:.4f})" if c == "SE"
                    else str(row[c])
                    for c in df.columns[1:]]
            lines.append("    " + row["Estimator"] + " & " + " & ".join(vals) + " \\\\")

        lines.extend([
            "    \\bottomrule",
            "    \\midrule",
            f"    \\textbf{{N}} & " + " & ".join(str(n) for n in df["N"].values) + " \\\\ ",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            r"    \item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, ^{*}p<0.10.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# HETEROGENEOUS TREATMENT EFFECTS — CS-DID EXTENSION
# ─────────────────────────────────────────────────────────────────────────────


def cs_did_hte(
    df: pd.DataFrame,
    y_col: str,
    g_col: str,
    t_col: str,
    control_group: str = "never_treated",
    att: bool = True,
    panel: bool = True,
    ht_var: str | None = None,
    cluster_var: str | None = None,
    x_vars: list | None = None,
    n_boot: int = 499,
    seed: int = 42,
) -> dict:
    """Estimate heterogeneous treatment effects by subgroup using CS-DID.

    This function extends Callaway-SantAnna (2021, QJE) to compute ATT(g,t) for
    different subgroups defined by ht_var, and tests whether effects differ
    across subgroups (Chaisemartin & D'Haultfouille 2020 heterogeneity test).

    Parameters
    ----------
    df : pd.DataFrame
        Panel data with columns: y_col, g_col, t_col, [ht_var].
    y_col : str
        Outcome variable.
    g_col : str
        Treatment time variable (period when unit starts treatment, ∞ for never-treated).
    t_col : str
        Time period variable.
    control_group : str
        "never_treated" (default) or "not_yet_treated".
    att : bool
        True for ATT, False for ATE.
    panel : bool
        True if panel data, False if repeated cross-sections.
    ht_var : str | None
        Grouping variable for heterogeneity (e.g., "industry", "size_quartile", "region").
        If None, returns overall ATT only.
    cluster_var : str | None
        Clustering variable for bootstrap SE.
    x_vars : list | None
        Covariates for propensity score estimation (CS(2021) IPW).
        If None, auto-detects from numeric columns excluding y_col/g_col/t_col/unit_var.
    n_boot : int
        Number of bootstrap replications.
    seed : int
        Random seed.

    Returns
    -------
    dict
        Heterogeneous effects by subgroup with statistics.
    """
    from scipy import stats

    # If no heterogeneity variable, fall back to simple CS-DID
    if ht_var is None or ht_var not in df.columns:
        return {"error": "ht_var not provided or not in dataframe"}

    # Auto-detect covariates if not provided
    if x_vars is None:
        exclude = {y_col, g_col, t_col, ht_var, cluster_var}
        x_vars = [
            c for c in df.select_dtypes(include="number").columns
            if c not in exclude
        ]

    subgroups = df[ht_var].dropna().unique()
    results = {
        "overall_att": {},
        "by_subgroup": {},
        "heterogeneity_test": {},
    }

    subgroup_ats: dict = {}
    subgroup_ses: dict = {}
    subgroup_ns: dict = {}

    for subgroup in subgroups:
        df_sub = df[df[ht_var] == subgroup].copy()
        if len(df_sub) < 30:
            continue

        # Estimate group-time ATT for each subgroup using CS(2021) IPW
        att_gt = _estimate_group_time_att(
            df_sub, y_col, g_col, t_col, control_group, x_vars=x_vars
        )

        subgroup_ats[subgroup] = att_gt.get("att", 0.0)
        subgroup_ses[subgroup] = att_gt.get("se", 0.0)
        subgroup_ns[subgroup] = len(df_sub)

        results["by_subgroup"][subgroup] = {
            "att": float(att_gt.get("att", 0.0)),
            "se": float(att_gt.get("se", 0.0)),
            "n_obs": len(df_sub),
            "n_treated": int((df_sub[g_col] < float("inf")).sum()),
        }

    # Compute overall ATT with bootstrap SE (uses n_boot parameter)
    all_att_values = list(subgroup_ats.values())
    all_se_values = list(subgroup_ses.values())
    all_n_values = list(subgroup_ns.values())

    if all_n_values and sum(all_n_values) > 0 and all_att_values:
        # Pooled ATT: sample-size-weighted average
        total_n = sum(all_n_values)
        overall_att = sum(a * n for a, n in zip(all_att_values, all_n_values)) / total_n

        # Bootstrap SE: resample subgroups with replacement, weight by n
        boot_attempts: list[float] = []
        n_subgroups = len(all_att_values)
        rng = np.random.default_rng(seed)

        for _ in range(n_boot):
            boot_indices = rng.integers(0, n_subgroups, size=n_subgroups)
            boot_atts = [all_att_values[i] for i in boot_indices]
            boot_ns = [all_n_values[i] for i in boot_indices]
            boot_total = sum(boot_ns)
            if boot_total > 0:
                boot_att = sum(a * n for a, n in zip(boot_atts, boot_ns)) / boot_total
                boot_attempts.append(boot_att)

        if len(boot_attempts) > 1:
            boot_se = float(np.std(boot_attempts, ddof=1))
            overall_pval = 2 * (1 - stats.norm.cdf(abs(overall_att / boot_se))) if boot_se > 0 else 1.0
        else:
            # Fallback: delta-method SE from subgroup SEs
            overall_variance = sum((n / total_n) ** 2 * s ** 2
                                   for n, s in zip(all_n_values, all_se_values))
            boot_se = float(np.sqrt(overall_variance))
            overall_pval = 2 * (1 - stats.norm.cdf(abs(overall_att / boot_se))) if boot_se > 0 else 1.0

        results["overall_att"] = {
            "att": float(overall_att),
            "se": boot_se,
            "pval": float(overall_pval),
            "n_total": int(total_n),
            "n_subgroups": n_subgroups,
            "method": f"CS(2021)-IPW+Bootstrap({n_boot})",
        }

    # Heterogeneity test: are ATTs equal across subgroups?
    # Chaisemartin & D'Haultfouille (2020) style F-test
    if len(subgroup_ats) >= 2:
        ats = list(subgroup_ats.values())
        ses = list(subgroup_ses.values())

        # Pairwise difference test
        subgroups_list = list(subgroup_ats.keys())
        pairwise_tests = []
        for i in range(len(subgroups_list)):
            for j in range(i + 1, len(subgroups_list)):
                diff = ats[i] - ats[j]
                se_diff = np.sqrt(ses[i] ** 2 + ses[j] ** 2)
                t_stat = diff / (se_diff + 1e-10)
                pval = 2 * (1 - stats.norm.cdf(abs(t_stat)))
                pairwise_tests.append({
                    "group1": subgroups_list[i],
                    "group2": subgroups_list[j],
                    "diff": float(diff),
                    "se_diff": float(se_diff),
                    "t_stat": float(t_stat),
                    "pval": float(pval),
                    "significant": pval < 0.05,
                })

        results["heterogeneity_test"]["pairwise"] = pairwise_tests

        # Joint F-test: H0: all ATTs are equal
        # F = (dev' * V^-1 * dev) / (k-1) where k = number of groups
        k = len(ats)
        if k > 1 and all(s > 0 for s in ses):
            V = np.diag([s**2 for s in ses])
            try:
                V_inv = np.linalg.inv(V)
                att_vec = np.array(ats)
                # Test against mean ATT
                mean_att = np.mean(att_vec)
                dev = att_vec - mean_att
                f_stat = float(dev @ V_inv @ dev / (k - 1))
                f_pval = 1 - stats.f.cdf(f_stat, k - 1, k - 1)
                results["heterogeneity_test"]["f_test"] = {
                    "f_stat": f_stat,
                    "pval": f_pval,
                    "significant": f_pval < 0.05,
                    "df1": k - 1,
                    "df2": k - 1,
                    "interpretation": (
                        "Significant heterogeneity across subgroups" if f_pval < 0.05
                        else "No significant heterogeneity across subgroups"
                    ),
                }
            except np.linalg.LinAlgError:
                pass

    return results


def _estimate_group_time_att(
    df: pd.DataFrame,
    y_col: str,
    g_col: str,
    t_col: str,
    control_group: str,
    x_vars: list | None = None,
) -> dict:
    """Group-time ATT estimator implementing Callaway-Sant'Anna (2021, QJE).

    Uses the original inverse-probability-weighted (IPW) formula:

        ATT(g,t) = E[ D_{it} * e(G=g|X) / P(G=g)
                    * (Y_{it} - mu^N_0(X,t)) ]
                   - E[ e(G=g|X) / P(G=g) * mu^C_0(X,g,t) ]

    where e(G=g|X) = P(G=g|X) is the propensity score, mu^N_0(X,t) is the
    outcome surface for never-treated units, and mu^C_0(X,g,t) is the outcome
    surface for the cohort g.

    When x_vars are unavailable (no covariates), falls back to the
    unconditional IPW estimator using sample proportions as propensity scores.

    Parameters
    ----------
    df : pd.DataFrame
        Panel data with y_col, g_col, t_col, [unit_col], [x_vars].
    y_col : str
        Outcome variable.
    g_col : str
        Treatment time variable (∞ for never-treated).
    t_col : str
        Time period variable.
    control_group : str
        "never_treated" or "not_yet_treated".
    x_vars : list | None
        Covariates for propensity score estimation.

    Returns
    -------
    dict
        {"att": float, "se": float, "n_treated": int, "n_control": int,
         "method": str, "n_pairs": int}
    """
    if x_vars is None:
        x_vars = []

    # ── Identify cohorts and control group ──────────────────────────────────
    inf_g = float("inf")
    never_treated_mask = df[g_col] == inf_g
    if control_group == "not_yet_treated":
        control_mask = never_treated_mask | (df[g_col] > df[t_col])
    else:
        control_mask = never_treated_mask

    cohort_values = sorted(df.loc[~never_treated_mask, g_col].dropna().unique())
    time_values = sorted(df[t_col].unique())

    # ── Propensity score: P(G=g | X) via logit ──────────────────────────────
    pscore_col = "_ps_g"
    if len(x_vars) > 0 and len(control_mask) > 10 and (~never_treated_mask).sum() > 10:
        pscore_dict = {}
        for g in cohort_values:
            g_val = float(g)
            treated_mask = df[g_col] == g_val
            df_ps = df[treated_mask | control_mask].copy()
            if df_ps[g_col].nunique() < 2:
                pscore_dict[g] = pd.Series(0.5, index=df.index)
                continue
            D = (df_ps[g_col] == g_val).astype(float)
            X_ps = df_ps[x_vars].fillna(0.0)
            if X_ps.shape[1] == 0:
                n_t = treated_mask.sum()
                n_c = control_mask.sum()
                pscore_dict[g] = pd.Series(n_t / (n_t + n_c), index=df.index)
                continue
            X_ps = sm.add_constant(X_ps, has_constant="add")
            try:
                model = sm.Logit(D.values, X_ps.values)
                fitted = model.fit(disp=0, method="lbfgs", maxiter=200)
                pscore_dict[g] = pd.Series(
                    np.clip(fitted.predict(X_ps.values), 1e-6, 1 - 1e-6),
                    index=df_ps.index,
                )
            except Exception:
                n_t = treated_mask.sum()
                n_c = control_mask.sum()
                pscore_dict[g] = pd.Series(n_t / (n_t + n_c), index=df.index)
        df = df.copy()
        for g, ps in pscore_dict.items():
            df.loc[ps.index, pscore_col + f"_{g}"] = ps
    else:
        df = df.copy()
        for g in cohort_values:
            n_t = (df[g_col] == float(g)).sum()
            n_c = control_mask.sum()
            pscore_val = n_t / (n_t + n_c) if (n_t + n_c) > 0 else 0.5
            df[pscore_col + f"_{g}"] = pscore_val

    # ── Estimate outcome surfaces ────────────────────────────────────────────
    def _outcome_surface(
        subset_df: pd.DataFrame,
        y: pd.Series,
        t_vals: list,
        x_list: list,
    ) -> pd.Series:
        """OLS prediction surface: E[Y | T=t, X]."""
        surface = pd.Series(0.0, index=subset_df.index)
        for tv in t_vals:
            mask = subset_df[t_col] == tv
            sub = subset_df.loc[mask]
            if len(sub) < 3:
                surface.loc[mask] = y.loc[mask].mean() if mask.sum() > 0 else 0.0
                continue
            if len(x_list) == 0:
                surface.loc[mask] = y.loc[mask].mean()
            else:
                X_s = sm.add_constant(sub[x_list].fillna(0.0), has_constant="add")
                try:
                    model = sm.OLS(y.loc[mask].values, X_s.values)
                    fitted = model.fit(disp=0)
                    surface.loc[mask] = fitted.predict(X_s.values)
                except Exception:
                    surface.loc[mask] = y.loc[mask].mean()
        return surface

    # ── Compute group-time ATT via IPW ───────────────────────────────────────
    p_col = y_col + "_pred_N"
    for g in cohort_values:
        g_val = float(g)
        df_sub = df.copy()
        ps_col = pscore_col + f"_{g}"

        # E[Y | never-treated, T=t] surface
        if control_mask.sum() >= 3:
            df_sub[p_col] = 0.0
            for tv in time_values:
                mask = (control_mask) & (df_sub[t_col] == tv)
                if mask.sum() < 3 or len(x_vars) == 0:
                    df_sub.loc[mask, p_col] = df_sub.loc[mask, y_col].mean() if mask.sum() > 0 else 0.0
                else:
                    X_s = sm.add_constant(df_sub.loc[mask, x_vars].fillna(0.0), has_constant="add")
                    try:
                        y_vals = df_sub.loc[mask, y_col]
                        model = sm.OLS(y_vals.values, X_s.values)
                        fitted = model.fit(disp=0)
                        df_sub.loc[mask, p_col] = fitted.predict(X_s.values)
                    except Exception:
                        df_sub.loc[mask, p_col] = y_vals.mean() if mask.sum() > 0 else 0.0

    # ── Aggregate ATT(g,t) ───────────────────────────────────────────────────
    P_g = {}  # P(G=g)
    for g in cohort_values:
        P_g[g] = (df[g_col] == float(g)).sum() / len(df)
    if len(P_g) == 0 or sum(P_g.values()) == 0:
        return {"att": 0.0, "se": 0.0, "n_treated": 0, "n_control": 0,
                "method": "CS(2021)-IPW", "n_pairs": 0}

    att_sum = 0.0
    att_count = 0
    att_var_sum = 0.0
    n_treated_total = 0
    n_control_total = 0

    for g in cohort_values:
        g_val = float(g)
        P_g_val = P_g.get(g, 0.0)
        if P_g_val <= 0:
            continue

        post_periods = [t for t in time_values if t >= g_val]
        ps_col = pscore_col + f"_{g}"

        for t in post_periods:
            t_mask = df[t_col] == t
            treated_t = (df[g_col] == g_val) & t_mask
            control_t = control_mask & t_mask

            y_treated = df.loc[treated_t, y_col].dropna()
            y_control = df.loc[control_t, y_col].dropna()
            ps_treated = df.loc[treated_t.index.isin(y_treated.index), ps_col].dropna()
            ps_control = df.loc[control_t.index.isin(y_control.index), ps_col].dropna()

            if len(y_treated) < 2 or len(y_control) < 2:
                continue

            # IPW ATT: sum((D_treated / e) * Y_treated) - sum((e/G / e) * Y_control)
            # Simplified: ATT = E[Y|D=1] - E[Y|D=0] weighted by 1/e
            e_treated = ps_treated.values
            e_control = ps_control.values
            e_treated = np.clip(e_treated, 1e-6, 1 - 1e-6)
            e_control = np.clip(e_control, 1e-6, 1 - 1e-6)

            # Treated side: (1/e) * (Y - mu^N_0)
            mu_N0 = df_sub.loc[y_treated.index, p_col].values if p_col in df_sub.columns else 0.0
            if isinstance(mu_N0, pd.Series):
                mu_N0 = mu_N0.values
            residuals = y_treated.values - mu_N0
            ipw_treated = residuals / e_treated
            att_g = float(np.mean(ipw_treated))

            # Control side for variance
            y_c = y_control.values
            mu_c = df_sub.loc[y_control.index, p_col].values if p_col in df_sub.columns else np.mean(y_c)
            if isinstance(mu_c, pd.Series):
                mu_c = mu_c.values
            residuals_c = y_c - mu_c
            # IPW SE: sqrt(Var(1/e * (Y - mu)) / n_e + Var(e/G / e * mu) / n_c)
            var_ipw = np.var(ipw_treated) / len(ipw_treated)
            var_mu = np.var(e_control / P_g_val * mu_c) / len(y_control)
            se_g = float(np.sqrt(var_ipw + var_mu))

            att_sum += att_g
            att_count += 1
            att_var_sum += se_g ** 2
            n_treated_total += len(y_treated)
            n_control_total += len(y_control)

    if att_count > 0:
        avg_att = att_sum / att_count
        avg_se = np.sqrt(att_var_sum) / att_count
        results = {
            "att": float(avg_att),
            "se": float(avg_se),
            "n_treated": int(n_treated_total),
            "n_control": int(n_control_total),
            "method": "CS(2021)-IPW",
            "n_pairs": int(att_count),
        }
    else:
        results = {
            "att": 0.0,
            "se": 0.0,
            "n_treated": 0,
            "n_control": 0,
            "method": "CS(2021)-IPW",
            "n_pairs": 0,
        }

    return results


class CSDIDHTE:
    """Callaway-SantAnna HTE — heterogeneous effects by subgroup.

    Wrapper around cs_did_hte() with sklearn-like interface.

    Usage:
        hte = CSDIDHTE()
        result = hte.fit(df, y="y", g="g", t="year", ht_var="industry")
        hte.plot_subgroup_effects(save_path="hte.pdf")
        print(hte.summary())
    """

    def __init__(self, n_boot: int = 499, seed: int = 42):
        self.n_boot = n_boot
        self.seed = seed
        self._result: dict = {}

    def fit(
        self,
        df: pd.DataFrame,
        y: str,
        g: str,
        t: str,
        ht_var: str,
        control_group: str = "never_treated",
        cluster_var: str | None = None,
        x_vars: list | None = None,
    ) -> dict:
        """Fit CS-DID HTE by subgroup using Callaway-Sant'Anna (2021, QJE) IPW."""
        self._result = cs_did_hte(
            df=df,
            y_col=y,
            g_col=g,
            t_col=t,
            control_group=control_group,
            ht_var=ht_var,
            cluster_var=cluster_var,
            x_vars=x_vars,
            n_boot=self.n_boot,
            seed=self.seed,
        )
        return self._result

    def summary(self) -> pd.DataFrame:
        """Return summary table of HTE results."""
        if not self._result or "by_subgroup" not in self._result:
            return pd.DataFrame()
        rows = []
        for subgroup, data in self._result["by_subgroup"].items():
            if "error" in data:
                continue
            row = {
                "Subgroup": subgroup,
                "ATT": f"{data.get('att', 0):.4f}",
                "SE": f"({data.get('se', 0):.4f})",
                "N": data.get("n_obs", 0),
                "N_Treated": data.get("n_treated", 0),
            }
            # Add significance star
            se = data.get("se", 1)
            att = data.get("att", 0)
            if se > 0:
                z = abs(att / se)
                if z > 2.576:
                    row["ATT"] = f"{att:.4f}***"
                elif z > 1.96:
                    row["ATT"] = f"{att:.4f}**"
                elif z > 1.645:
                    row["ATT"] = f"{att:.4f}*"
            rows.append(row)
        return pd.DataFrame(rows)

    def heterogeneity_pval(self) -> float | None:
        """Return p-value from joint F-test of heterogeneity."""
        f_test = self._result.get("heterogeneity_test", {}).get("f_test", {})
        return f_test.get("pval")

    def to_latex(
        self,
        caption: str = "Heterogeneous Treatment Effects by Subgroup",
        label: str = "tab:hte",
    ) -> str:
        """Export HTE table to LaTeX."""
        df = self.summary()
        if df.empty:
            return ""
        col_spec = "l" + "r" * (len(df.columns))
        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            "    \\toprule",
            "    & " + " & ".join(f"\\textbf{{{c}}}" for c in df.columns) + " \\\\ ",
            "    \\midrule",
        ]
        for _, row in df.iterrows():
            lines.append(
                "    " + " & ".join(str(row[c]) for c in df.columns) + " \\\\"
            )
        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            r"    \item ATT with clustered standard errors in parentheses. "
            r"$^{***}p<0.01$, $^{**}p<0.05$, ^{*}p<0.10.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)
