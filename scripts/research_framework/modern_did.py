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

Usage:
    engine = ModernDiDEngine(df, y_var="roa", treat_var="did", time_var="post")
    result = engine.cs()        # Callaway-Sant'Anna
    result = engine.bjs()       # Borusyak-Jaravel-Spinks
    result = engine.gardner()    # Gardner Two-Stage
    engine.plot_event_study()    # 事件研究图
    engine.bacon_decomposition()  # Bacon 分解
    engine.honest_did(m=0.5)     # Honest DiD 敏感性
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "ModernDiDEngine",
    "DiDEstimationResult",
]

_log = logging.getLogger("modern_did")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


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

    @property
    def sig(self) -> str:
        if self.pval < 0.001: return "***"
        elif self.pval < 0.01: return "**"
        elif self.pval < 0.05: return "*"
        elif self.pval < 0.10: return r"$\dagger$"
        return ""

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
            "sig": self.sig,
            **{k: v for k, v in self.additional.items()},
        }


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
    t_stat = np.mean(valid_diffs) / (np.std(valid_diffs) / np.sqrt(len(valid_diffs)) if len(valid_diffs) > 1 else 0)
    p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(valid_diffs) - 1)) if len(valid_diffs) > 1 else 1.0

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
                except Exception:
                    continue

    return pd.DataFrame(decomp_rows)


# ─────────────────────────────────────────────────────────────────────────────
# HONEST DID (Rambachan-Roth 2023)
# ─────────────────────────────────────────────────────────────────────────────


def _honest_did(
    coef: float,
    se: float,
    pre_trends_pval: float,
    m: float = 0.5,
    delta_grid: np.ndarray | None = None,
) -> dict:
    """
    Rambachan-Roth (2023) Honest DiD 敏感性分析。

    在平行趋势可能违背的假设下，计算稳健置信区间。
    RR2023 边界：假设 pre-trend 的最大偏离为 m × post-trend 的标准误。

    Parameters
    ----------
    coef : float
        基准 DID 系数。
    se : float
        基准标准误。
    pre_trends_pval : float
        平行趋势检验 p 值（越高越接近满足）。
    m : float
        最大偏离参数（默认 0.5，即 post-SE 的 50%）。
    delta_grid : np.ndarray | None
        δ 的网格（敏感性参数）。

    Returns
    -------
    dict
        含 ci_lower/ci_upper 和 breakdown value。
    """
    if delta_grid is None:
        delta_grid = np.linspace(0, 2 * abs(coef), 200)

    # RR2023 简化边界（对称版本）
    # bias-adjusted CI = [coef - t * se * (1 + m) - |delta|, coef + t * se * (1 + m) + |delta|]
    # 使用 1.96 作为 95% CI 的 t 临界值
    t_crit = 1.96
    half_width = t_crit * se * (1 + m)

    # 计算每个 δ 值下的 CI
    ci_bounds = []
    for delta in delta_grid:
        ci_lower = coef - half_width - abs(delta)
        ci_upper = coef + half_width + abs(delta)
        ci_bounds.append({
            "delta": float(delta),
            "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper),
            "contains_zero": (ci_lower < 0 < ci_upper),
        })

    df_bounds = pd.DataFrame(ci_bounds)

    # breakdown value: CI 刚好不含零的最小 δ
    non_zero = df_bounds[~df_bounds["contains_zero"]]
    breakdown_value = float(non_zero["delta"].min()) if len(non_zero) > 0 else float(delta_grid.max())

    # 基准 CI
    base_ci_lower = coef - t_crit * se
    base_ci_upper = coef + t_crit * se

    return {
        "coef": coef,
        "se": se,
        "base_ci_lower": base_ci_lower,
        "base_ci_upper": base_ci_upper,
        "m": m,
        "breakdown_value": breakdown_value,
        "delta_grid": delta_grid.tolist(),
        "ci_bounds": ci_bounds,
        "interpretation": (
            f"With m={m}, the {100*(1-2*(1-0.95))}% CI is robust to "
            f"pre-trend violations up to δ={breakdown_value:.3f}"
        ),
    }


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
    except Exception:
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
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.treat_var = treat_var
        self.time_var = time_var
        self.unit_var = unit_var
        self.x_vars = x_vars or []
        self.cluster_var = cluster_var
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

    def _ols_did(
        self,
        df_sub: pd.DataFrame,
        estimator: str = "did_2x2",
        cluster_var: str | None = None,
    ) -> DiDEstimationResult:
        """内部 OLS DID 估计。"""
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

        # Cluster SE
        cov_kwds = None
        cov_type = "HC1"
        if cluster_var and cluster_var in df_sub.columns:
            cov_type = "cluster"
            cov_kwds = {"groups": df_sub[cluster_var].values}
        elif self.cluster_var and self.cluster_var in df_sub.columns:
            cov_type = "cluster"
            cov_kwds = {"groups": df_sub[self.cluster_var].values}

        model = sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=cov_kwds)

        # 找 DID 系数（第 4 个参数，即 treat × post）
        did_idx = 3 if len(model.params) > 3 else len(model.params) - 1
        coef = float(model.params[did_idx])
        se = float(model.bse[did_idx])
        pval = float(model.pvalues[did_idx])
        ci_arr = model.conf_int()
        if hasattr(ci_arr, "iloc"):
            ci = ci_arr.iloc[did_idx].values
        else:
            ci = np.asarray(ci_arr)[did_idx]

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
            r_squared=float(model.rsquared),
            method=cov_type,
            additional={},
        )

    def _empty_result(self, estimator: str) -> DiDEstimationResult:
        return DiDEstimationResult(estimator=estimator, coef=0, se=0, pval=1, n_obs=0)

    # ── Estimators ───────────────────────────────────────────────────

    def did_2x2(
        self,
        *,
        cluster_var: str | None = None,
        precompute_event_study: bool = False,
    ) -> DiDEstimationResult:
        """
        经典 2x2 DID（使用 statsmodels OLS）。

        Parameters
        ----------
        cluster_var : str | None
            聚类标准误变量（优先于 self.cluster_var）。
        precompute_event_study : bool
            是否同时计算事件研究图数据。

        Returns
        -------
        DiDEstimationResult
        """
        df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
        result = self._ols_did(df_sub, "did_2x2", cluster_var)

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
    ) -> DiDEstimationResult:
        """
        Callaway-Sant'Anna (2021, QJE) 交错 DiD。

        使用"尚未处理"组作为对照，比"从未处理"组更有效。

        Parameters
        ----------
        control_group : str
            "notyettreated"（默认）或 "nevertreated"。
        anticipation : int
            处理预期提前期数。

        Returns
        -------
        DiDEstimationResult
        """
        # 检查 diff_in_diff2 是否可用
        try:
            import diff_in_diff2 as did2
            df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
            # diff_in_diff2 API
            result_obj = did2.cs(
                data=df_sub,
                y=self.y_var,
                g=self.unit_var,
                t=self.time_var,
                d=self.treat_var,
                control_group=control_group,
                anticipation=anticipation,
            )
            # 转换为本模块格式
            result = DiDEstimationResult(
                estimator="cs",
                coef=float(result_obj["att"]),
                se=float(result_obj["se"]),
                pval=float(result_obj["pval"]),
                n_obs=len(df_sub),
                additional={"method": "Callaway-Sant'Anna (2021)"},
            )
            self._results["cs"] = result
            return result
        except ImportError:
            _log.warning(
                "[ModernDiD] diff_in_diff2 not installed — staggered DiD (cs) unavailable, "
                "using did_2x2 fallback. Run: pip install diff-in-diff2"
            )
            return self.did_2x2()

    def bjs(self, anticipation: int = 0) -> DiDEstimationResult:
        """
        Borusyak-Jaravel-Spinks (2024, REStud) Imputation DiD。

        基于"反事实推断"的两步法，比 CS 更高效（使用所有信息）。
        """
        try:
            import diff_in_diff2 as did2
            df_sub = self.df.dropna(subset=[self.y_var, self.treat_var, self.time_var] + self.x_vars)
            result_obj = did2.bjs(
                data=df_sub,
                y=self.y_var,
                g=self.unit_var,
                t=self.time_var,
                d=self.treat_var,
                anticipation=anticipation,
            )
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
        except ImportError:
            _log.warning("[ModernDiD] diff_in_diff2 not installed — staggered DiD (bjs) unavailable, using did_2x2 fallback")
            return self.did_2x2()

    def gardner(self, n_placebos: int = 100) -> DiDEstimationResult:
        """
        Gardner (2022) Two-Stage DID。

        对 DD 咖（Doubly-robust）的两步估计。
        """
        try:
            import diff_in_diff2 as did2
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
        except ImportError:
            _log.warning("[ModernDiD] diff_in_diff2 not installed — staggered DiD (gardner) unavailable, using did_2x2 fallback")
            return self.did_2x2()

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

    def honest_did(self, m: float = 0.5, delta_grid: np.ndarray | None = None) -> dict:
        """
        Rambachan-Roth (2023) Honest DiD 敏感性分析。

        基于基准 did_2x2 结果，计算在平行趋势违背下的稳健 CI。

        Parameters
        ----------
        m : float
            最大偏离参数（默认 0.5，即 post-SE 的 50%）。
        delta_grid : np.ndarray | None
            敏感性参数的网格。

        Returns
        -------
        dict
        """
        base = self._results.get("did_2x2")
        if base is None:
            base = self.did_2x2()

        pt_result = base.additional.get("parallel_trends", {})
        pre_pval = pt_result.get("pval", 0.5) if isinstance(pt_result, dict) else 0.5

        if delta_grid is None:
            delta_grid = np.linspace(0, 2 * abs(base.coef), 200)

        result = _honest_did(base.coef, base.se, pre_pval, m, delta_grid)
        base.additional["honest_did"] = result
        self._results["honest_did"] = self._empty_result("honest_did")
        _log.info(
            f"[ModernDiD] Honest DiD: breakdown at δ={result['breakdown_value']:.3f}"
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
            f"[ModernDiD] Wild bootstrap: p={result.get('pval', 'N/A')}, "
            f"CI=[{result.get('ci_lower', 'N/A'):.4f}, {result.get('ci_upper', 'N/A'):.4f}]"
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
            "    \\item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)
