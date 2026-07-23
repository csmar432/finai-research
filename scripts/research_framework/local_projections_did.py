"""Local Projections DiD Engine — Jordà (2005) Approach to Treatment Effects.

This module implements the Local Projections method for estimating dynamic
treatment effects in a Difference-in-Differences framework, following:

    - Jordà, O. (2005). Estimation and Inference of Impulse Responses by
      Local Projections. American Economic Review, 95(1), 161-182.
    - Ribatet, M. & others. Local projections for policy evaluation.
    - Abraham, S., Sun, L., & Zhou, X. (2023). Local Projection Methods
      for Panel Data. Working Paper.

The core idea: for each event horizon h, separately estimate the outcome
difference between treated and control groups at h periods after (or before)
the treatment event, without relying on VAR dynamics.

    y_{t+h} - y_{t-1} = alpha_h + beta_h * D_{i,t} + controls + epsilon

The estimated beta_h captures the treatment effect at horizon h.

Usage:
    engine = LocalProjectionsDIDEngine(
        df,
        outcome_var="roa",
        treatment_var="did",
        time_var="post",
        unit_var="ticker",
        cluster_var="industry",
    )
    results = engine.fit(horizons=range(-5, 6))
    engine.plot_irf(save_path="irf_event_study.pdf")
    engine.parallel_trends_test()
    engine.bootstrap_ci(B=999)
    engine.summary()
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "LocalProjectionsDIDEngine",
    "LPDIDResult",
]

_log = logging.getLogger("lp_did")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class LPDIDResult:
    """
    Local Projections DID 估计结果容器。

    Attributes
    ----------
    horizon : int
        事件期（相对处理时间）。负值表示处理前（retrospective），
        0 表示处理当期，正值表示处理后（forward/prospective）。
    coef : float
        处理效应系数估计值。
    se : float
        标准误（HC1 或聚类标准误）。
    ci_lower : float
        95% 置信区间下界。
    ci_upper : float
        95% 置信区间上界。
    pval : float
        双侧 p 值。
    n_obs : int
        该事件期回归的有效观测数。
    t_stat : float
        t 统计量。
    sig : str
        显著性标记（*** / ** / * / dagger / ""）。
    n_bootstrap : int
        Bootstrap 重复次数（如果使用了 bootstrap_ci）。
    n_treated : int
        处理组单位数。
    n_control : int
        对照组单位数。
    r_squared : float | None
        R²。
    method : str
        标准误类型（HC1 / cluster）。
    """

    horizon: int
    coef: float
    se: float
    pval: float
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    n_obs: int = 0
    t_stat: float = 0.0
    n_bootstrap: int = 0
    n_treated: int = 0
    n_control: int = 0
    r_squared: float | None = None
    method: str = "HC1"

    @property
    def sig(self) -> str:
        if self.pval < 0.001:
            return "***"
        elif self.pval < 0.01:
            return "**"
        elif self.pval < 0.05:
            return "*"
        elif self.pval < 0.10:
            return r"$\dagger$"
        return ""

    def to_dict(self) -> dict:
        return {
            "horizon": self.horizon,
            "coef": self.coef,
            "se": self.se,
            "pval": self.pval,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "t_stat": self.t_stat,
            "n_obs": self.n_obs,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
            "r_squared": self.r_squared,
            "method": self.method,
            "sig": self.sig,
            "n_bootstrap": self.n_bootstrap,
        }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _hc1_se(residuals: np.ndarray, x: np.ndarray) -> np.ndarray:
    """
    HC1 稳健标准误（MacKinnon-White 1985）。

    适用于中小样本，比 HC0 更少过度拒绝。

    Parameters
    ----------
    residuals : np.ndarray
        OLS 残差。
    x : np.ndarray
        设计矩阵。

    Returns
    -------
    np.ndarray
        参数估计量的标准误。
    """
    n, k = x.shape[0], x.shape[1]
    h = np.diag(x @ np.linalg.lstsq(x, np.eye(n), rcond=None)[0])
    h = np.clip(h, 1e-9, 1 - 1e-9)
    omega = residuals ** 2
    bread = np.linalg.inv(x.T @ x / n)
    meat = (x.T * omega) @ x / n
    vcv = bread @ meat @ bread * n / (n - k)
    return np.sqrt(np.diag(vcv))


def _build_lp_data(
    df: pd.DataFrame,
    outcome_var: str,
    treatment_var: str,
    time_var: str,
    unit_var: str,
    horizon: int,
) -> pd.DataFrame | None:
    """
    为给定事件期构建局部投影数据。

    对于 horizon = h:
      - 构造前瞻性（h >= 0）或回顾性（h < 0）的被解释变量
      - 处理变量 D_{i,t} 保持不变
      - 控制变量按原始时间索引

    Parameters
    ----------
    horizon : int
        事件期。

    Returns
    -------
    pd.DataFrame | None
        包含 y_lp（局部投影被解释变量）和原始 treatment/controls 的数据框。
    """
    df = df.copy()

    # 确认时间变量为数值型（便于加减）
    t_numeric = pd.to_numeric(df[time_var], errors="coerce")
    if t_numeric.isna().all():
        _log.warning(f"[LP-DID] {time_var} is not numeric — cannot compute horizons")
        return None

    df["_t_numeric"] = t_numeric

    # 构造局部投影被解释变量：y_{t+h} - y_{t-1}
    # 即从参照期到 h 期的累积变化
    df = df.sort_values([unit_var, time_var])

    if horizon >= 0:
        # Forward LP: outcome at t+h vs t-1
        df["_target_t"] = df["_t_numeric"] + horizon
        df_lp = df.merge(
            df[[unit_var, time_var, outcome_var]].rename(
                columns={time_var: "_target_t", outcome_var: "_y_future"}
            ),
            on=[unit_var, "_target_t"],
            how="inner",
        )
        # Baseline: t-1
        df["_base_t"] = df["_t_numeric"] - 1
        df_lp = df_lp.merge(
            df[[unit_var, "_base_t", outcome_var]].rename(
                columns={"_base_t": time_var, outcome_var: "_y_base"}
            ),
            on=[unit_var, time_var],
            how="inner",
        )
    else:
        # Backward LP: outcome at t+h vs t+1 (pre-treatment symmetric construction)
        # For h < 0, target = t + h (pre-period), base = t + 1 (immediate pre-period)
        df["_target_t"] = df["_t_numeric"] + horizon
        df_lp = df.merge(
            df[[unit_var, time_var, outcome_var]].rename(
                columns={time_var: "_target_t", outcome_var: "_y_future"}
            ),
            on=[unit_var, "_target_t"],
            how="inner",
        )
        # Baseline for backward: t+1 (symmetric to t-1 for forward)
        df["_base_t"] = df["_t_numeric"] + 1
        df_lp = df_lp.merge(
            df[[unit_var, "_base_t", outcome_var]].rename(
                columns={"_base_t": time_var, outcome_var: "_y_base"}
            ),
            on=[unit_var, time_var],
            how="inner",
        )

    if "_y_future" not in df_lp.columns or "_y_base" not in df_lp.columns:
        return None

    df_lp["_y_lp"] = df_lp["_y_future"] - df_lp["_y_base"]
    return df_lp


def _estimate_single_horizon(
    df_lp: pd.DataFrame,
    outcome_lp: str,
    treatment_var: str,
    controls: list[str],
    cluster_var: str | None,
    robust_se: bool,
    idv_type: str,
) -> dict:
    """
    对单个事件期运行 OLS 回归。

    y_lp = alpha + beta * D + controls + epsilon

    Returns
    -------
    dict
        含 coef / se / pval / ci_lower / ci_upper / t_stat / n_obs。
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return {
            "coef": np.nan, "se": np.nan, "pval": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "t_stat": np.nan, "n_obs": 0,
        }

    y = df_lp[outcome_lp].values.astype(float)
    X_parts = [np.ones((len(y), 1))]

    # Treatment variable
    D = df_lp[treatment_var].values.astype(float)
    if idv_type == "continuous":
        X_parts.append(D.reshape(-1, 1))
    else:
        X_parts.append(D.reshape(-1, 1))

    # Controls
    for ctrl in controls:
        if ctrl in df_lp.columns:
            X_parts.append(df_lp[ctrl].values.astype(float).reshape(-1, 1))

    X = np.column_stack(X_parts)
    xnames = ["const", treatment_var] + controls

    # Drop NaN rows in y
    mask = ~np.isnan(y) & ~np.isnan(D)
    X, y = X[mask], y[mask]

    if len(y) < len(xnames) + 2:
        return {
            "coef": np.nan, "se": np.nan, "pval": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "t_stat": np.nan, "n_obs": int(len(y)),
        }

    # OLS fit
    model = sm.OLS(y, X).fit()

    # Retrieve treatment coefficient (index 1)
    didx = 1
    if didx >= len(model.params):
        return {
            "coef": np.nan, "se": np.nan, "pval": np.nan,
            "ci_lower": np.nan, "ci_upper": np.nan,
            "t_stat": np.nan, "n_obs": int(len(y)),
        }

    coef = float(model.params[didx])

    # Standard errors
    if robust_se:
        # HC1 robust SE
        resid = np.asarray(model.resid)
        se_vec = _hc1_se(resid, X)
        se = float(se_vec[didx])
        cov_type = "HC1"
    elif cluster_var and cluster_var in df_lp.columns:
        groups = np.asarray(df_lp.iloc[mask][cluster_var], dtype=object)
        model_cl = sm.OLS(y, X).fit(
            cov_type="cluster",
            cov_kwds={"groups": groups},
        )
        se = float(model_cl.bse[didx])
        cov_type = "cluster"
    else:
        se = float(model.bse[didx])
        cov_type = "OLS"

    pval = float(model.pvalues[didx])
    t_stat = float(model.tvalues[didx])
    ci = np.asarray(model.conf_int())[didx]

    return {
        "coef": coef,
        "se": se,
        "pval": pval,
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "t_stat": t_stat,
        "n_obs": int(len(y)),
        "r_squared": float(model.rsquared),
        "method": cov_type,
    }


def _wild_cluster_bootstrap_lp(
    df_lp: pd.DataFrame,
    outcome_lp: str,
    treatment_var: str,
    controls: list[str],
    cluster_var: str,
    B: int = 999,
    bootstrap_type: str = "rademacher",
    seed: int = 42,
) -> dict:
    """
    Wild Cluster Bootstrap（Wu 1986 / Mammen 1993）为单个 horizon 生成置信区间。

    适用于聚类数较少（< 50）的情况。

    Returns
    -------
    dict
        含 ci_lower / ci_upper / pval / n_bootstrap。
    """
    try:
        pass
    except ImportError:
        return {"ci_lower": np.nan, "ci_upper": np.nan, "pval": np.nan}

    try:
        import statsmodels.api as sm
    except ImportError:
        return {"ci_lower": np.nan, "ci_upper": np.nan, "pval": np.nan}

    y = df_lp[outcome_lp].values.astype(float)
    D = df_lp[treatment_var].values.astype(float)

    X_parts = [np.ones((len(y), 1)), D.reshape(-1, 1)]
    for ctrl in controls:
        if ctrl in df_lp.columns:
            X_parts.append(df_lp[ctrl].values.astype(float).reshape(-1, 1))
    X = np.column_stack(X_parts)

    mask = ~np.isnan(y) & ~np.isnan(D)
    X, y = X[mask], y[mask]
    groups = np.asarray(df_lp.iloc[mask][cluster_var], dtype=object)

    if len(y) < 4:
        return {"ci_lower": np.nan, "ci_upper": np.nan, "pval": np.nan}

    # Point estimate
    model = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    beta = float(model.params[1])
    beta_se = float(model.bse[1])

    if beta_se == 0 or np.isnan(beta_se):
        return {"ci_lower": np.nan, "ci_upper": np.nan, "pval": np.nan}

    # Bootstrap
    rng = np.random.default_rng(seed)
    clusters = np.unique(groups)
    t_stars = []

    for _ in range(B):
        if bootstrap_type == "rademacher":
            v = rng.choice([-1, 1], size=len(clusters))
        elif bootstrap_type == "mammen":
            v = rng.choice([-1, 1], size=len(clusters)) * rng.choice(
                [-(np.sqrt(5) - 1) / 2, (np.sqrt(5) + 1) / 2], size=len(clusters)
            )
        else:
            v = rng.standard_normal(size=len(clusters))

        cluster_map = dict(zip(clusters, v))
        groups_arr = np.asarray(groups, dtype=object)
        weights = np.array([cluster_map.get(g, 1.0) for g in groups_arr])

        residuals = np.asarray(model.resid)
        y_star = np.asarray(model.fittedvalues) + residuals * weights

        try:
            m_star = sm.OLS(y_star, X).fit()
            t_stars.append(float(m_star.params[1]))
        except Exception:
            continue

    t_stars = np.array(t_stars)
    if len(t_stars) == 0:
        return {"ci_lower": np.nan, "ci_upper": np.nan, "pval": np.nan}

    # Percentile CI
    alpha = 0.05
    ci_lower = float(np.percentile(t_stars, 100 * alpha / 2))
    ci_upper = float(np.percentile(t_stars, 100 * (1 - alpha / 2)))

    # Bootstrap p value
    pval = float(np.mean(np.abs(t_stars - beta) >= abs(beta / beta_se)))

    return {
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "pval": pval,
        "n_bootstrap": B,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL TRENDS TEST (Joint F-test on Pre-treatment Horizons)
# ─────────────────────────────────────────────────────────────────────────────


def _parallel_trends_joint_test(results: list[LPDIDResult]) -> dict:
    """
    对所有处理前 horizons 的系数进行联合 F 检验。

    H0: 所有 pre-period 系数 = 0（平行趋势成立）。

    Returns
    -------
    dict
        含 f_stat / pval / n_pre_horizons / reject（是否拒绝 H0）。
    """
    pre_results = [r for r in results if r.horizon < 0]
    if len(pre_results) < 2:
        return {"f_stat": np.nan, "pval": np.nan, "n_pre_horizons": len(pre_results)}

    coefs = np.array([r.coef for r in pre_results])
    ses = np.array([r.se for r in pre_results])

    # Remove NaN
    valid = ~(np.isnan(coefs) | np.isnan(ses))
    coefs, ses = coefs[valid], ses[valid]

    if len(coefs) < 2:
        return {"f_stat": np.nan, "pval": np.nan, "n_pre_horizons": len(pre_results)}

    # Wald test statistic: sum(beta_i^2 / se_i^2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wald = np.sum((coefs / ses) ** 2)

    k = len(coefs)
    # Approximate F-test with k and large df
    try:
        from scipy import stats
        pval = 1 - stats.chi2.cdf(wald, df=k)
    except Exception:
        pval = np.nan

    return {
        "f_stat": float(wald),
        "pval": float(pval),
        "n_pre_horizons": k,
        "reject": bool(pval < 0.05) if not np.isnan(pval) else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class LocalProjectionsDIDEngine:
    """
    Local Projections DID 引擎 — Jordà (2005) 方法。

    对每个事件期 h 独立估计 y_{t+h} - y_{t-1} 对处理变量的回归，
    得到动态处理效应路径（IRF-style event study）。

    与传统 VAR-based IRF 不同，局部投影不施加动态结构假设，
    估计更稳健，特别适合：

      1. 交错处理的动态效应（Jordà 2005 风格的事件研究图）
      2. 异质性处理效应（不同 horizon 不同系数）
      3. 面板数据的稳健推断（支持聚类 + Wild Bootstrap）

    Parameters
    ----------
    df : pd.DataFrame
        面板数据。
    outcome_var : str
        结果变量列名。
    treatment_var : str
        处理变量列名（二值或连续）。
    time_var : str
        时间变量列名（数值型，用于计算 horizon）。
    unit_var : str
        单位标识列名（公司 / 省份等）。
    horizons : list[int]
        事件期列表，如 range(-5, 6)。
    controls : list[str]
        额外控制变量。
    cluster_var : str | None
        聚类变量（用于标准误）。
    idv_type : str
        "dummy"（二值处理）或 "continuous"（连续处理强度）。
    robust_se : bool
        是否使用 HC1 稳健标准误。

    Usage
    -----
    >>> engine = LocalProjectionsDIDEngine(
    ...     df, outcome_var="roa", treatment_var="did",
    ...     time_var="year", unit_var="ticker",
    ...     cluster_var="industry", horizons=range(-5, 6),
    ...     controls=["size", "lev"],
    ... )
    >>> results = engine.fit()
    >>> engine.plot_irf(save_path="irf.pdf")
    >>> engine.parallel_trends_test()
    >>> engine.bootstrap_ci(B=999)
    >>> engine.summary()
    >>> print(engine.to_latex())
    """

    def __init__(
        self,
        df: pd.DataFrame,
        outcome_var: str,
        treatment_var: str,
        time_var: str,
        unit_var: str,
        horizons: list | None = None,
        controls: list[str] | None = None,
        cluster_var: str | None = None,
        idv_type: str = "dummy",
        robust_se: bool = True,
    ):
        self.df = df.copy()
        self.outcome_var = outcome_var
        self.treatment_var = treatment_var
        self.time_var = time_var
        self.unit_var = unit_var
        self.horizons = horizons if horizons is not None else list(range(-5, 6))
        self.controls = controls or []
        self.cluster_var = cluster_var
        self.idv_type = idv_type
        self.robust_se = robust_se
        self._results: dict[int, LPDIDResult] = {}
        self._bootstrap_cis: dict[int, dict] = {}
        self._parallel_trends: dict | None = None

        # Basic statistics
        self.n_obs = len(df)
        self.n_treated = int((df[treatment_var] == 1).sum()) if treatment_var in df.columns else 0
        self.n_control = int((df[treatment_var] == 0).sum()) if treatment_var in df.columns else 0
        self.n_units = int(df[unit_var].nunique())
        self.n_periods = int(df[time_var].nunique())

    # ── Single Horizon ───────────────────────────────────────────────────────

    def fit_single(self, h: int) -> LPDIDResult:
        """
        估计单个事件期的处理效应。

        Parameters
        ----------
        h : int
            事件期（相对时间）。

        Returns
        -------
        LPDIDResult
        """
        # Return cached result if already computed
        if h in self._results:
            return self._results[h]

        _log.info(f"[LP-DID] Fitting horizon h={h}")

        df_lp = _build_lp_data(
            self.df, self.outcome_var, self.treatment_var,
            self.time_var, self.unit_var, h,
        )

        if df_lp is None or len(df_lp) == 0:
            _log.warning(f"[LP-DID] No data for horizon h={h}")
            result = LPDIDResult(
                horizon=h,
                coef=np.nan, se=np.nan, pval=np.nan,
                n_obs=0, t_stat=np.nan,
                n_treated=self.n_treated,
                n_control=self.n_control,
            )
            self._results[h] = result
            return result

        est = _estimate_single_horizon(
            df_lp, "_y_lp", self.treatment_var,
            self.controls, self.cluster_var,
            self.robust_se, self.idv_type,
        )

        result = LPDIDResult(
            horizon=h,
            coef=est["coef"],
            se=est["se"],
            pval=est["pval"],
            ci_lower=est["ci_lower"],
            ci_upper=est["ci_upper"],
            n_obs=est["n_obs"],
            t_stat=est["t_stat"],
            n_treated=self.n_treated,
            n_control=self.n_control,
            r_squared=est.get("r_squared"),
            method=est.get("method", "HC1"),
        )

        self._results[h] = result
        _log.info(
            f"[LP-DID] h={h}: coef={result.coef:+.4f} "
            f"(se={result.se:.4f}, p={result.pval:.3f}), N={result.n_obs}"
        )
        return result

    # ── All Horizons ───────────────────────────────────────────────────────

    def fit(self, horizons: list | None = None) -> dict[int, LPDIDResult]:
        """
        估计所有事件期的处理效应。

        Parameters
        ----------
        horizons : list[int] | None
            事件期列表（默认使用 self.horizons）。

        Returns
        -------
        dict[int, LPDIDResult]
            以 horizon 为键的结果字典。
        """
        if horizons is None:
            horizons = self.horizons

        _log.info(f"[LP-DID] Fitting {len(horizons)} horizons: {horizons}")

        for h in horizons:
            if h not in self._results:
                self.fit_single(h)

        return self._results

    # ── Bootstrap CI ────────────────────────────────────────────────────────

    def bootstrap_ci(
        self,
        B: int = 999,
        bootstrap_type: str = "rademacher",
        horizons: list | None = None,
        seed: int = 42,
    ) -> dict[int, dict]:
        """
        Wild Cluster Bootstrap 生成逐 horizon 的置信区间。

        当聚类数较少（< 50）时，替代 t 分布推断。

        Parameters
        ----------
        B : int
            Bootstrap 重复次数（默认 999）。
        bootstrap_type : str
            "rademacher"（默认）/ "mammen" / "webb"。
        horizons : list[int] | None
            要 bootstrap 的 horizons。
        seed : int
            随机种子。

        Returns
        -------
        dict[int, dict]
            每个 horizon 的 bootstrap CI。
        """
        if horizons is None:
            horizons = self.horizons

        if not self._results:
            self.fit(horizons)

        if not self.cluster_var:
            _log.warning("[LP-DID] bootstrap_ci requires cluster_var — skipping")
            return {}

        _log.info(f"[LP-DID] Bootstrap CI: B={B}, type={bootstrap_type}")

        for h in horizons:
            if h not in self._results:
                continue

            df_lp = _build_lp_data(
                self.df, self.outcome_var, self.treatment_var,
                self.time_var, self.unit_var, h,
            )

            if df_lp is None:
                continue

            ci_dict = _wild_cluster_bootstrap_lp(
                df_lp, "_y_lp", self.treatment_var,
                self.controls, self.cluster_var,
                B=B, bootstrap_type=bootstrap_type, seed=seed,
            )

            if not np.isnan(ci_dict.get("ci_lower", np.nan)):
                self._results[h].ci_lower = ci_dict["ci_lower"]
                self._results[h].ci_upper = ci_dict["ci_upper"]
                self._results[h].n_bootstrap = ci_dict.get("n_bootstrap", B)
                # Also update p-value from bootstrap if available
                if "pval" in ci_dict:
                    self._results[h].pval = ci_dict["pval"]

            self._bootstrap_cis[h] = ci_dict

        _log.info(f"[LP-DID] Bootstrap CI completed for {len(self._bootstrap_cis)} horizons")
        return self._bootstrap_cis

    # ── Parallel Trends Test ────────────────────────────────────────────────

    def parallel_trends_test(self) -> dict:
        """
        平行趋势联合检验。

        对所有 pre-treatment horizons 的系数进行联合 F 检验。

        Returns
        -------
        dict
            含 f_stat / pval / n_pre_horizons / reject。
        """
        if not self._results:
            self.fit()

        result_list = list(self._results.values())
        self._parallel_trends = _parallel_trends_joint_test(result_list)

        _log.info(
            f"[LP-DID] Parallel trends (joint F-test): "
            f"F={self._parallel_trends['f_stat']:.3f}, "
            f"p={self._parallel_trends['pval']:.3f}, "
            f"pre-periods={self._parallel_trends['n_pre_horizons']}"
        )
        return self._parallel_trends

    # ── IRF Plot ───────────────────────────────────────────────────────────

    def plot_irf(
        self,
        horizons: list | None = None,
        save_path: str | Path | None = None,
        title: str = "Local Projections DID: Dynamic Treatment Effects",
        ylabel: str = "Treatment Effect",
        figsize: tuple[float, float] = (9, 5.5),
    ) -> Any:
        """
        绘制事件研究图（IRF 风格）。

        Parameters
        ----------
        horizons : list[int] | None
            要绑定的 horizons。
        save_path : str | Path | None
            保存路径（.pdf / .png）。
        title : str
            图标题。
        ylabel : str
            y 轴标签。
        figsize : tuple
            图形尺寸。

        Returns
        -------
        matplotlib Figure | None
        """
        if horizons is None:
            horizons = self.horizons

        if not self._results:
            self.fit(horizons)

        data = self.summary()

        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=figsize)

            ax.axhline(y=0, color="dimgray", linestyle="--", linewidth=1.0, zorder=1)
            ax.axvline(x=-0.5, color="silver", linestyle="--", linewidth=0.8, zorder=1)

            # Plot forward horizons (h >= 0) in steelblue
            post_data = data[data["horizon"] >= 0]
            pre_data = data[data["horizon"] < 0]

            if len(post_data) > 0:
                ax.errorbar(
                    post_data["horizon"], post_data["coef"],
                    yerr=1.96 * post_data["se"],
                    fmt="o-", color="steelblue", capsize=5,
                    linewidth=2.0, markersize=7, label="Post-treatment",
                    zorder=3,
                )
                ax.fill_between(
                    post_data["horizon"],
                    post_data["ci_lower"], post_data["ci_upper"],
                    alpha=0.12, color="steelblue",
                )

            # Plot pre horizons (h < 0) in gray
            if len(pre_data) > 0:
                ax.errorbar(
                    pre_data["horizon"], pre_data["coef"],
                    yerr=1.96 * pre_data["se"],
                    fmt="o--", color="gray", capsize=5,
                    linewidth=1.5, markersize=6, label="Pre-treatment",
                    zorder=2,
                )

            # Significance markers
            for _, row in data.iterrows():
                if row["pval"] < 0.05 and not np.isnan(row["coef"]):
                    ax.annotate(
                        "*" if row["pval"] < 0.05 else "",
                        (row["horizon"], row["ci_upper"] + 0.03 * abs(row["coef"]) if abs(row["coef"]) > 0 else 0.05),
                        ha="center", fontsize=8, color="steelblue",
                    )

            ax.set_xlabel("Event Time (Horizon)", fontsize=12)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_title(title, fontsize=13, fontweight="bold")
            ax.set_xticks(sorted(data["horizon"].unique()))
            ax.grid(True, alpha=0.25, linestyle="-", linewidth=0.5)
            ax.legend(fontsize=10, loc="best")
            plt.tight_layout()

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(save_path, dpi=300, bbox_inches="tight")
                _log.info(f"[LP-DID] IRF plot saved: {save_path}")

            return fig

        except ImportError:
            _log.warning("[LP-DID] matplotlib not installed")
            return None

    # ── Summary Table ──────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        汇总所有 horizon 的估计结果。

        Returns
        -------
        pd.DataFrame
            含 horizon / coef / se / ci_lower / ci_upper / pval / t_stat / n_obs / r_squared。
        """
        if not self._results:
            self.fit()

        rows = []
        for h in sorted(self._results.keys()):
            r = self._results[h]
            rows.append({
                "horizon": r.horizon,
                "coef": r.coef,
                "se": r.se,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
                "pval": r.pval,
                "t_stat": r.t_stat,
                "n_obs": r.n_obs,
                "r_squared": r.r_squared,
                "method": r.method,
                "sig": r.sig,
            })

        return pd.DataFrame(rows)

    def to_latex(
        self,
        caption: str = "Dynamic Treatment Effects: Local Projections DID",
        label: str = "tab:lp_did",
        stars: bool = True,
    ) -> str:
        """
        导出为 LaTeX 表格（booktabs 风格）。

        Parameters
        ----------
        caption : str
            表格标题。
        label : str
            LaTeX 标签。
        stars : bool
            是否添加显著性星号。

        Returns
        -------
        str
            LaTeX 表格代码。
        """
        df = self.summary()
        if df.empty:
            return ""

        col_spec = "l" + "c" * len(df.columns)
        star_note = " \\hspace{1em} $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$" if stars else ""

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            "    \\toprule",
            "    \\textbf{Horizon} & " + " & ".join(
                f"\\textbf{{{c}}}" for c in df.columns[1:]
            ) + " \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            vals = []
            for c in df.columns[1:]:
                if c == "coef":
                    v = f"{row[c]:.4f}{row['sig'] if stars and 'sig' in row else ''}"
                elif c == "se":
                    v = f"({row[c]:.4f})"
                elif c in ("pval", "r_squared"):
                    _v = row[c]
                    try:
                        v = f"{float(_v):.3f}" if not pd.isna(_v) else "—"
                    except (TypeError, ValueError):
                        v = str(_v) if not pd.isna(_v) else "—"
                elif c == "sig":
                    continue
                else:
                    _v = row[c]
                    try:
                        v = f"{float(_v):.4f}" if not pd.isna(_v) else "—"
                    except (TypeError, ValueError):
                        v = str(_v) if not pd.isna(_v) else "—"
                vals.append(v)
            lines.append(
                "    \\textit{" + str(row["horizon"]) + "} & " + " & ".join(vals) + " \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "    \\midrule",
            f"    \\textbf{{N}} & " + " & ".join(str(n) for n in df["n_obs"].values) + " \\\\ ",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            f"    \\item Standard errors in parentheses.{star_note}",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)
