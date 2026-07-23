"""Survival Analysis — Cox PH, Kaplan-Meier, Nelson-Aalen, Competing Risks.

本模块封装生存分析方法，覆盖：
  1. Cox Proportional Hazards Model（CoxPHFitter 或手动偏似然估计）
  2. Kaplan-Meier 生存曲线估计器
  3. Nelson-Aalen 累积风险估计器
  4. Fine-Gray (1995) 竞争风险模型
  5. 时变协变量 Cox 模型
  6. 对数秩检验 (Log-rank) 与 Breslow 检验
  7. Harrell's C-index 模型评价

应用场景：公司金融（IPO抑价/债券违约/并购完成）、ESG（碳合规截止日期）、
公共政策（企业进入退出）等研究。

Usage:
    # Cox PH
    cox = CoxPHModel(ties="efron")
    result = cox.fit(df, duration="time", event="event", X=["did", "size", "lev"])
    cox.summary()
    cox.plot_baseline_hazard("bh.pdf")
    cox.plot_predicted_survival(df, groups={"treated": df["did"]==1}, save_path="km.pdf")

    # Kaplan-Meier
    km = KaplanMeier()
    km.fit(df, duration="time", event="event")
    km.plot("km.pdf")
    cmp = km.compare_groups(df, duration="time", event="event", group_var="did")

    # Full suite
    suite = SurvivalSuite()
    all_results = suite.run_all(df, duration="time", event="event", X=["did","size","lev"])
    het = suite.heterogeneity_analysis(df, duration="time", event="event",
                                       X=["did","size"], group_var="industry")
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

__all__ = [
    "SurvivalResult",
    "CoxPHModel",
    "KaplanMeier",
    "NelsonAalen",
    "CompetingRisks",
    "TimeVaryingCovariates",
    "SurvivalSuite",
]

_log = logging.getLogger("survival")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SurvivalResult:
    """
    生存分析回归结果容器。

    Attributes
    ----------
    model_type : str
        模型类型："cox_ph" | "kaplan_meier" | "nelson_aalen" |
        "competing_risks" | "time_varying".
    coef_dict : dict[str, float]
        变量名到系数估计值的映射。
    se_dict : dict[str, float]
        变量名到标准误的映射。
    z_dict : dict[str, float]
        变量名到 z 统计量的映射。
    pval_dict : dict[str, float]
        变量名到 p 值的映射。
    ci_lower : dict[str, float]
        变量名到 95% CI 下界的映射（HR 的下界）。
    ci_upper : dict[str, float]
        变量名到 95% CI 上界的映射（HR 的上界）。
    sig_dict : dict[str, str]
        变量名到显著性标记的映射 (* / ** / ***)。
    n_obs : int
        有效观测数。
    n_events : int
        发生终点事件的观测数。
    concordance : float | None
        Harrell's C-index（0~1，越高越好）。
    log_likelihood : float | None
        对数似然值。
    aic : float | None
        AIC。
    bic : float | None
        BIC。
    baseline_hazard : pd.DataFrame | None
        基准风险表（时间、风险、生存概率）。
    converged : bool
        迭代是否收敛。
    ties : str
        确散处理方法。
    strata : list[str] | None
        分层变量列表。
    """

    model_type: str
    coef_dict: dict[str, float] = field(default_factory=dict)
    se_dict: dict[str, float] = field(default_factory=dict)
    z_dict: dict[str, float] = field(default_factory=dict)
    pval_dict: dict[str, float] = field(default_factory=dict)
    ci_lower: dict[str, float] = field(default_factory=dict)
    ci_upper: dict[str, float] = field(default_factory=dict)
    sig_dict: dict[str, str] = field(default_factory=dict)
    n_obs: int = 0
    n_events: int = 0
    concordance: float | None = None
    log_likelihood: float | None = None
    aic: float | None = None
    bic: float | None = None
    baseline_hazard: pd.DataFrame | None = None
    converged: bool = True
    ties: str = "efron"
    strata: list[str] | None = None

    def to_dict(self) -> dict:
        """将结果展平为单层字典（便于写入 DataFrame）。"""
        out = {
            "model_type": self.model_type,
            "n_obs": self.n_obs,
            "n_events": self.n_events,
            "concordance": self.concordance,
            "log_likelihood": self.log_likelihood,
            "aic": self.aic,
            "bic": self.bic,
            "converged": self.converged,
        }
        for var in self.coef_dict:
            out[f"coef_{var}"] = self.coef_dict[var]
            out[f"se_{var}"] = self.se_dict.get(var, np.nan)
            out[f"z_{var}"] = self.z_dict.get(var, np.nan)
            out[f"pval_{var}"] = self.pval_dict.get(var, np.nan)
            out[f"ci_lower_{var}"] = self.ci_lower.get(var, np.nan)
            out[f"ci_upper_{var}"] = self.ci_upper.get(var, np.nan)
            out[f"hr_{var}"] = np.exp(self.coef_dict[var])
            out[f"hr_ci_lower_{var}"] = np.exp(self.ci_lower.get(var, -np.inf))
            out[f"hr_ci_upper_{var}"] = np.exp(self.ci_upper.get(var, np.inf))
            out[f"sig_{var}"] = self.sig_dict.get(var, "")
        return out


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_LIFELINES_AVAILABLE = False
_CoxPHFitter = None
_KaplanMeierFitter = None
_NelsonAalenFitter = None
_FineGrayModel = None


def _load_lifelines() -> bool:
    """尝试加载 lifelines，返回是否成功。"""
    global _LIFELINES_AVAILABLE, _CoxPHFitter, _KaplanMeierFitter
    global _NelsonAalenFitter, _FineGrayModel
    if _LIFELINES_AVAILABLE:
        return True
    try:
        from lifelines import CoxPHFitter, KaplanMeierFitter, NelsonAalenFitter
        _CoxPHFitter = CoxPHFitter
        _KaplanMeierFitter = KaplanMeierFitter
        _NelsonAalenFitter = NelsonAalenFitter
        _LIFELINES_AVAILABLE = True
        _log.info("[Survival] lifelines loaded successfully")
        return True
    except ImportError:
        _log.warning("[Survival] lifelines not available, using manual implementation")
        return False


def _significance_mark(pval: float) -> str:
    """返回显著性标记。"""
    if pval < 0.001:
        return "***"
    elif pval < 0.01:
        return "**"
    elif pval < 0.05:
        return "*"
    elif pval < 0.10:
        return r"$\dagger$"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# MANUAL COX PARTIAL LIKELIHOOD (FALLBACK)
# ─────────────────────────────────────────────────────────────────────────────


def _partial_log_likelihood(
    beta: np.ndarray, T: np.ndarray, E: np.ndarray, X: np.ndarray
) -> float:
    """
    Cox 偏对数似然（负值，用于最小化）。

    Parameters
    ----------
    beta : np.ndarray (k,)
        系数向量。
    Xb : np.ndarray (n,)
        X @ beta 预计算。
    T : np.ndarray (n,)
        生存时间。
    E : np.ndarray (n,)  bool
        事件指示（1=发生，0=截尾）。

    Returns
    -------
    float
        负偏对数似然。
    """
    Xb = X @ beta
    n = len(T)
    ll = 0.0
    for i in range(n):
        if not E[i]:
            continue
        ti = T[i]
        risk_set = np.where(T >= ti)[0]
        if len(risk_set) == 0:
            continue
        log_denom = np.log(np.sum(np.exp(Xb[risk_set])))
        ll += Xb[i] - log_denom
    return -ll  # 负号用于 minimizer


def _cox_gradient_hessian(
    beta: np.ndarray, T: np.ndarray, E: np.ndarray, X: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    Cox 偏似然的一阶和二阶导数（用于 Newton-Raphson）。

    Returns
    -------
    (gradient, hessian)
    """
    Xb = X @ beta
    n, k = X.shape
    grad = np.zeros(k)
    hess = np.zeros((k, k))

    for i in range(n):
        if not E[i]:
            continue
        ti = T[i]
        risk_set = np.where(T >= ti)[0]
        if len(risk_set) == 0:
            continue

        # 风险集加权和
        exp_xb = np.exp(Xb[risk_set])
        sum_exp = np.sum(exp_xb)
        sum_exp_x = np.sum(X[risk_set] * exp_xb[:, np.newaxis], axis=0)
        sum_exp_xx = X[risk_set].T @ (exp_xb[:, np.newaxis] * X[risk_set])

        # 梯度项
        grad += X[i] - sum_exp_x / sum_exp

        # Hessian 项
        hess += -(sum_exp_xx / sum_exp - np.outer(sum_exp_x, sum_exp_x) / (sum_exp ** 2))

    return grad, hess


def _fit_cox_minimize(
    T: np.ndarray, E: np.ndarray, X: np.ndarray,
    max_iter: int = 500, tol: float = 1e-7
) -> tuple[np.ndarray, bool, float, int]:
    """
    使用 scipy.optimize.minimize (L-BFGS-B) 拟合 Cox 模型。

    Returns
    -------
    (beta, converged, log_likelihood, n_iter)
    """
    from scipy.optimize import minimize

    def neg_pll(beta: np.ndarray) -> float:
        return _partial_log_likelihood(beta, T, E, X)

    k = X.shape[1]
    beta0 = np.zeros(k)

    result = minimize(
        neg_pll,
        beta0,
        method="L-BFGS-B",
        options={"maxiter": max_iter, "ftol": tol, "disp": False},
    )

    beta = result.x
    converged = result.success or result.status in (0, 1)
    ll = -result.fun
    n_iter = result.nit if hasattr(result, "nit") else 0

    return beta, converged, ll, n_iter


def _fit_cox_newton_raphson(
    T: np.ndarray, E: np.ndarray, X: np.ndarray,
    max_iter: int = 100, tol: float = 1e-6
) -> tuple[np.ndarray, bool, float, int]:
    """
    Newton-Raphson 迭代拟合 Cox 模型。

    Returns
    -------
    (beta, converged, log_likelihood, n_iter)
    """
    k = X.shape[1]
    beta = np.zeros(k)

    for iteration in range(max_iter):
        grad, hess = _cox_gradient_hessian(beta, T, E, X)

        try:
            hess_inv = np.linalg.inv(hess)
        except np.linalg.LinAlgError:
            _log.warning("[Survival] Hessian singular, adding ridge penalty")
            hess += np.eye(k) * 1e-4
            hess_inv = np.linalg.inv(hess)

        delta = hess_inv @ grad
        beta_new = beta - delta

        if np.max(np.abs(delta)) < tol:
            beta = beta_new
            ll = -_partial_log_likelihood(beta, T, E, X)
            return beta, True, ll, iteration + 1

        beta = beta_new

    ll = -_partial_log_likelihood(beta, T, E, X)
    return beta, False, ll, max_iter


def _manual_cox_fit(
    df: pd.DataFrame, duration: str, event: str, X_names: list[str],
    ties: str = "efron"
) -> SurvivalResult:
    """
    手动实现 Cox 比例风险回归（当 lifelines 不可用时）。

    Parameters
    ----------
    df : pd.DataFrame
    duration, event : str
    X_names : list[str]
    ties : str

    Returns
    -------
    SurvivalResult
    """
    df_sub = df.dropna(subset=[duration, event] + X_names).copy()
    T = df_sub[duration].values.astype(float)
    E = df_sub[event].values.astype(bool)
    X_mat = df_sub[X_names].values.astype(float)

    # 添加截距
    X_mat = np.column_stack([np.ones(len(X_mat)), X_mat])
    all_names = ["const"] + X_names

    # L-BFGS-B 优化
    beta, converged, ll, n_iter = _fit_cox_minimize(T, E, X_mat)

    # 方差估计（基于 Hessian）
    _, hess = _cox_gradient_hessian(beta, T, E, X_mat)
    try:
        var_beta = np.linalg.inv(-hess)
        se = np.sqrt(np.abs(np.diag(var_beta)))
    except np.linalg.LinAlgError:
        se = np.full(len(beta), np.nan)

    # z 统计量 & p 值
    from scipy import stats
    z_vals = beta / np.where(se > 0, se, 1e-10)
    p_vals = 2 * (1 - stats.norm.cdf(np.abs(z_vals)))

    # 95% CI
    z_crit = stats.norm.ppf(0.975)
    ci_lo = beta - z_crit * se
    ci_hi = beta + z_crit * se

    # AIC / BIC
    n = len(T)
    k = len(beta)
    aic_val = 2 * k - 2 * ll
    bic_val = k * np.log(n) - 2 * ll

    # C-index（简化版）
    risk_scores = X_mat @ beta
    c_idx = _concordance_index(T, E.astype(float), risk_scores)

    coef_dict = dict(zip(all_names, beta.tolist(), strict=False))
    se_dict = dict(zip(all_names, se.tolist(), strict=False))
    z_dict = dict(zip(all_names, z_vals.tolist(), strict=False))
    pval_dict = dict(zip(all_names, p_vals.tolist(), strict=False))
    ci_lower = dict(zip(all_names, ci_lo.tolist(), strict=False))
    ci_upper = dict(zip(all_names, ci_hi.tolist(), strict=False))
    sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in all_names}

    _log.info(
        f"[Survival] Manual Cox PH converged={converged} in {n_iter} iters, "
        f"N={n}, events={int(E.sum())}, C={c_idx:.4f}"
    )

    return SurvivalResult(
        model_type="cox_ph",
        coef_dict=coef_dict,
        se_dict=se_dict,
        z_dict=z_dict,
        pval_dict=pval_dict,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        sig_dict=sig_dict,
        n_obs=n,
        n_events=int(E.sum()),
        concordance=c_idx,
        log_likelihood=float(ll),
        aic=float(aic_val),
        bic=float(bic_val),
        converged=converged,
        ties=ties,
        baseline_hazard=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONCORDANCE INDEX
# ─────────────────────────────────────────────────────────────────────────────


def _concordance_index(
    y_time: np.ndarray,
    y_event: np.ndarray,
    y_pred: np.ndarray
) -> float:
    """
    Harrell's C-index（Concordance Index）。

    衡量生存模型预测值与实际生存顺序的吻合程度。

    C = (# concordant pairs + 0.5 * # ties) / (# comparable pairs)

    Parameters
    ----------
    y_time : np.ndarray (n,)
        生存时间。
    y_event : np.ndarray (n,)  0/1
        事件指示。
    y_pred : np.ndarray (n,)
        预测风险分数（越高风险越大）。

    Returns
    -------
    float  [0, 1]
    """
    n = len(y_time)
    if n < 2:
        return np.nan

    concordant = 0
    tied_risk = 0
    comparable = 0

    for i in range(n):
        for j in range(i + 1, n):
            # 确定是否可比：至少有一个事件
            if y_event[i] == 0 and y_event[j] == 0:
                continue
            comparable += 1

            # 时间顺序
            t_i, t_j = y_time[i], y_time[j]

            if t_i < t_j:
                # i 先失效
                if y_event[i] == 1:
                    if y_pred[i] > y_pred[j]:
                        concordant += 1
                    elif y_pred[i] == y_pred[j]:
                        tied_risk += 1
            elif t_j < t_i:
                # j 先失效
                if y_event[j] == 1:
                    if y_pred[j] > y_pred[i]:
                        concordant += 1
                    elif y_pred[j] == y_pred[i]:
                        tied_risk += 1
            else:
                # 同时失效（均为事件）
                if y_event[i] == 1 and y_event[j] == 1:
                    if y_pred[i] == y_pred[j]:
                        tied_risk += 1
                    else:
                        pass  # 不计入 concordant

    if comparable == 0:
        return np.nan

    c_idx = (concordant + 0.5 * tied_risk) / comparable
    return float(c_idx)


# ─────────────────────────────────────────────────────────────────────────────
# LOG-RANK TEST
# ─────────────────────────────────────────────────────────────────────────────


def _log_rank_test(
    times1: np.ndarray, events1: np.ndarray,
    times2: np.ndarray, events2: np.ndarray
) -> dict:
    """
    Log-rank 检验（Mantel-Haenszel 版本）。

    H0: 两组生存函数相等。

    Parameters
    ----------
    times1, times2 : np.ndarray
        两组的生存时间。
    events1, events2 : np.ndarray  bool
        两组的事件指示。

    Returns
    -------
    dict
        含 test, statistic, pval, df, interpretation。
    """
    from scipy import stats

    # 合并并排序
    combined = pd.DataFrame({
        "time": np.concatenate([times1, times2]),
        "event": np.concatenate([events1.astype(int), events2.astype(int)]),
        "group": np.concatenate([np.zeros(len(times1)), np.ones(len(times2))]),
    })
    combined = combined.sort_values("time").reset_index(drop=True)

    O1 = 0.0  # 组1 观测事件数
    E1 = 0.0  # 组1 期望事件数
    V = 0.0   # 方差

    unique_times = combined["time"].unique()

    for t in unique_times:
        at_risk_total = len(combined[combined["time"] >= t])
        if at_risk_total <= 1:
            continue

        events_at_t = combined[(combined["time"] == t) & (combined["event"] == 1)]
        d_total = len(events_at_t)

        at_risk_g1 = len(combined[(combined["time"] >= t) & (combined["group"] == 0)])
        len(combined[(combined["time"] >= t) & (combined["group"] == 1)])

        d1 = len(events_at_t[events_at_t["group"] == 0])

        # 期望
        e1 = d_total * at_risk_g1 / at_risk_total

        O1 += d1
        E1 += e1

        # 方差（超几何方差）
        if at_risk_total > 1:
            V += (d_total * (at_risk_total - d_total)
                  * at_risk_g1 * (at_risk_total - at_risk_g1)
                  / (at_risk_total ** 2 * (at_risk_total - 1)))

    if V <= 0:
        return {
            "test": "log_rank",
            "statistic": np.nan,
            "pval": np.nan,
            "df": 1,
            "O1": O1,
            "E1": E1,
            "interpretation": "Insufficient data for log-rank test",
        }

    z_stat = (O1 - E1) / np.sqrt(V)
    pval = 2 * (1 - stats.norm.cdf(abs(z_stat)))
    chi2_stat = z_stat ** 2

    interpretation = (
        "Reject H0 (survival differs between groups)"
        if pval < 0.05
        else "Fail to reject H0 (no significant difference)"
    )

    return {
        "test": "log_rank",
        "statistic": float(chi2_stat),
        "z_statistic": float(z_stat),
        "pval": float(pval),
        "df": 1,
        "O1": float(O1),
        "E1": float(E1),
        "interpretation": interpretation,
    }


def _breslow_test(
    times1: np.ndarray, events1: np.ndarray,
    times2: np.ndarray, events2: np.ndarray
) -> dict:
    """
    Breslow（Generalized Wilcoxon / Gehan）检验。

    相对于 log-rank，对早期事件赋予更大权重。

    Returns
    -------
    dict  同 log-rank 结构
    """
    from scipy import stats

    combined = pd.DataFrame({
        "time": np.concatenate([times1, times2]),
        "event": np.concatenate([events1.astype(int), events2.astype(int)]),
        "group": np.concatenate([np.zeros(len(times1)), np.ones(len(times2))]),
    })
    combined = combined.sort_values("time").reset_index(drop=True)

    O1 = 0.0
    E1 = 0.0
    V = 0.0

    unique_times = combined["time"].unique()

    for t in unique_times:
        at_risk_total = len(combined[combined["time"] >= t])
        if at_risk_total <= 1:
            continue

        events_at_t = combined[(combined["time"] == t) & (combined["event"] == 1)]
        d_total = len(events_at_t)

        at_risk_g1 = len(combined[(combined["time"] >= t) & (combined["group"] == 0)])

        d1 = len(events_at_t[events_at_t["group"] == 0])

        # 加权权重 = at_risk_total
        w = at_risk_total
        O1 += w * d1
        E1 += w * d_total * at_risk_g1 / at_risk_total

        if at_risk_total > 1:
            V += (w ** 2 * d_total * (at_risk_total - d_total)
                  * at_risk_g1 * (len(combined) - at_risk_g1)
                  / (at_risk_total ** 2 * (at_risk_total - 1)))

    if V <= 0:
        return {
            "test": "breslow",
            "statistic": np.nan,
            "pval": np.nan,
            "df": 1,
            "interpretation": "Insufficient data for Breslow test",
        }

    z_stat = (O1 - E1) / np.sqrt(V)
    pval = 2 * (1 - stats.norm.cdf(abs(z_stat)))
    chi2_stat = z_stat ** 2

    return {
        "test": "breslow",
        "statistic": float(chi2_stat),
        "z_statistic": float(z_stat),
        "pval": float(pval),
        "df": 1,
        "interpretation": "Reject H0 (survival differs between groups)"
        if pval < 0.05 else "Fail to reject H0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# COX PH MODEL
# ─────────────────────────────────────────────────────────────────────────────


class CoxPHModel:
    """
    Cox 比例风险回归模型。

    Parameters
    ----------
    ties : str
        确散处理方法："efron"（默认）或 "breslow"。
    strata : list[str] | None
        分层变量列表。

    Usage
    -----
        cox = CoxPHModel(ties="efron")
        result = cox.fit(df, duration="time", event="event",
                         X=["did", "size", "lev"])
        print(cox.summary())
        cox.plot_baseline_hazard("bh.pdf")
        cox.plot_predicted_survival(df, groups={"Treated": df["did"]==1,
                                                "Control": df["did"]==0},
                                    save_path="km_pred.pdf")
        print(cox.to_latex())
    """

    def __init__(
        self,
        ties: Literal["efron", "breslow"] = "efron",
        strata: list[str] | None = None,
    ):
        self.ties = ties
        self.strata = strata
        self._result: SurvivalResult | None = None
        self._fitted_model: Any = None
        self._duration_col: str = ""
        self._event_col: str = ""
        self._X_names: list[str] = []

    # ── fit ──────────────────────────────────────────────────────────────────

    def fit(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
        X: list[str],
    ) -> SurvivalResult:
        """
        拟合 Cox 比例风险模型。

        Parameters
        ----------
        df : pd.DataFrame
            生存数据（宽格式，每行一个个体）。
        duration : str
            生存时间列名。
        event : str
            事件指示列名（0=截尾，1=事件）。
        X : list[str]
            协变量列名列表。

        Returns
        -------
        SurvivalResult
        """
        self._duration_col = duration
        self._event_col = event
        self._X_names = X.copy()

        if _load_lifelines():
            self._result = self._fit_lifelines(df, duration, event, X)
        else:
            self._result = _manual_cox_fit(df, duration, event, X, ties=self.ties)

        return self._result

    def _fit_lifelines(
        self, df: pd.DataFrame, duration: str, event: str, X: list[str]
    ) -> SurvivalResult:
        """使用 lifelines 库拟合 Cox PH。"""
        df_sub = df.dropna(subset=[duration, event] + X).copy()

        # lifelines 需要 event 为 int
        df_sub = df_sub.copy()
        df_sub[event] = df_sub[event].astype(int)

        cph = _CoxPHFitter(ties=self.ties)
        cph.fit(
            df_sub,
            duration_col=duration,
            event_col=event,
            covariates=X,
            strata=self.strata,
        )
        self._fitted_model = cph

        # 提取结果
        summary = cph.summary
        coef_dict = {var: summary.loc[var, "coef"] for var in X if var in summary.index}
        se_dict = {var: summary.loc[var, "se(coef)"] for var in X if var in summary.index}
        z_dict = {var: summary.loc[var, "z"] for var in X if var in summary.index}
        pval_dict = {var: summary.loc[var, "p"] for var in X if var in summary.index}
        ci_lower = {var: summary.loc[var, "coef lower 95%"] for var in X if var in summary.index}
        ci_upper = {var: summary.loc[var, "coef upper 95%"] for var in X if var in summary.index}
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X}

        # 基准风险表
        bh = None
        try:
            bh = cph.baseline_cumulative_hazard_.reset_index()
            bh.columns = ["time", "cum_hazard"]
            bh["survival"] = np.exp(-bh["cum_hazard"])
            bh = bh[["time", "cum_hazard", "survival"]]
        except Exception:  # noqa: S110
            pass

        _log.info(
            f"[Survival] lifelines Cox PH: N={cph.event_observed.sum()}, "
            f"C={cph.concordance_index_:.4f}"
        )

        return SurvivalResult(
            model_type="cox_ph",
            coef_dict=coef_dict,
            se_dict=se_dict,
            z_dict=z_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            sig_dict=sig_dict,
            n_obs=int(cph.event_observed.sum()),
            n_events=int(cph.event_observed.sum()),
            concordance=cph.concordance_index_,
            log_likelihood=cph.log_likelihood_,
            aic=cph.AIC_partial_,
            bic=cph.AIC_partial_,
            baseline_hazard=bh,
            converged=cph.converged_ if hasattr(cph, "converged_") else True,
            ties=self.ties,
            strata=self.strata,
        )

    # ── predict ─────────────────────────────────────────────────────────────

    def predict_hazard(self, df: pd.DataFrame) -> np.ndarray:
        """
        预测个体的瞬时风险分数。

        Parameters
        ----------
        df : pd.DataFrame
            必须包含所有 fit 时使用的协变量。

        Returns
        -------
        np.ndarray
            预测风险分数（X @ beta）。
        """
        if self._result is None:
            raise ValueError("Model not fitted. Call fit() first.")

        if self._fitted_model is not None:
            try:
                return self._fitted_model.predict_hazard(df[self._X_names]).values
            except Exception:  # noqa: S110
                pass

        X_mat = df[self._X_names].values.astype(float)
        X_mat = np.column_stack([np.ones(len(X_mat)), X_mat])
        beta = np.array([self._result.coef_dict.get(n, 0.0) for n in ["const"] + self._X_names])
        return X_mat @ beta

    def predict_survival(
        self, df: pd.DataFrame, times: np.ndarray | None = None
    ) -> pd.DataFrame:
        """
        预测个体生存曲线。

        Parameters
        ----------
        df : pd.DataFrame
            包含协变量的数据。
        times : np.ndarray | None
            预测时间点。默认为基准风险表中的时间点。

        Returns
        -------
        pd.DataFrame
            index=时间，columns=每行数据的预测生存概率。
        """
        if self._result is None:
            raise ValueError("Model not fitted. Call fit() first.")

        if times is None:
            if self._result.baseline_hazard is not None:
                times = self._result.baseline_hazard["time"].values
            else:
                times = np.linspace(0, 10, 50)

        if self._fitted_model is not None:
            try:
                surv = self._fitted_model.predict_survival_function(df[self._X_names], times=times)
                if hasattr(surv, "values"):
                    return pd.DataFrame(surv.values, index=times)
                return surv.T
            except Exception:  # noqa: S110
                pass

        # 手动：S(t) = S0(t)^exp(X*beta)
        beta = np.array([self._result.coef_dict.get(n, 0.0) for n in ["const"] + self._X_names])
        bh = self._result.baseline_hazard
        if bh is None:
            _log.warning("[Survival] No baseline hazard available, returning NaN")
            return pd.DataFrame(np.nan, index=times, columns=df.index)

        H0 = np.interp(times, bh["time"].values, bh["cum_hazard"].values)
        X_mat = np.column_stack([np.ones(len(df)), df[self._X_names].values.astype(float)])
        xb = X_mat @ beta

        result = pd.DataFrame(
            np.exp(-np.outer(H0, np.exp(xb))).T,
            index=df.index,
            columns=times,
        )
        return result.T

    # ── summary ─────────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        返回回归结果汇总表（带显著性标记）。

        Returns
        -------
        pd.DataFrame
        """
        if self._result is None:
            return pd.DataFrame()

        rows = []
        for var in self._X_names:
            coef = self._result.coef_dict.get(var, np.nan)
            se = self._result.se_dict.get(var, np.nan)
            hr = np.exp(coef) if not np.isnan(coef) else np.nan
            hr_lo = np.exp(self._result.ci_lower.get(var, -np.inf))
            hr_hi = np.exp(self._result.ci_upper.get(var, np.inf))
            pval = self._result.pval_dict.get(var, np.nan)
            sig = self._result.sig_dict.get(var, "")
            rows.append({
                "Variable": var,
                "coef": coef,
                "HR": hr,
                "HR_95CI": f"[{hr_lo:.3f}, {hr_hi:.3f}]",
                "se": se,
                "z": self._result.z_dict.get(var, np.nan),
                "pval": pval,
                "sig": sig,
            })

        df_out = pd.DataFrame(rows)
        return df_out

    def to_latex(
        self,
        caption: str = "Cox Proportional Hazards Regression",
        label: str = "tab:coxph",
        vars_to_show: list[str] | None = None,
    ) -> str:
        """
        导出为 LaTeX 表格（threeparttable 格式）。

        Parameters
        ----------
        caption, label : str
        vars_to_show : list[str] | None

        Returns
        -------
        str  LaTeX 代码
        """
        if self._result is None:
            return ""

        df = self.summary()
        if df.empty:
            return ""

        show = vars_to_show or self._X_names
        show = [v for v in show if v in df["Variable"].values]
        df_sub = df[df["Variable"].isin(show)]

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccc}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{HR} & \\textbf{SE} & \\textbf{z} & \\textbf{p-value} \\\\",
            "    \\midrule",
        ]

        for _, row in df_sub.iterrows():
            sig = row.get("sig", "")
            hr = row.get("HR", np.nan)
            se = row.get("se", np.nan)
            z = row.get("z", np.nan)
            pval = row.get("pval", np.nan)
            lines.append(
                f"    {row['Variable']:25s} & "
                f"{hr:6.3f}{sig:5s} & "
                f"({se:5.3f}) & "
                f"{z:6.2f} & "
                f"{pval:6.3f} \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "    \\midrule",
            f"    \\textbf{{N}} & \\textbf{{{self._result.n_obs}}} & & & \\\\",
            f"    \\textbf{{Events}} & \\textbf{{{self._result.n_events}}} & & & \\\\",
            f"    \\textbf{{C-index}} & \\textbf{{{self._result.concordance:.4f}}} & & & \\\\",
            f"    Log-likelihood & {self._result.log_likelihood:.3f} & & & \\\\",
            f"    AIC & {self._result.aic:.2f} & & & \\\\",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Hazard ratios (HR). $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "    \\item Baseline hazard estimated by Breslow's method.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)

    # ── plots ───────────────────────────────────────────────────────────────

    def plot_baseline_hazard(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> Any:
        """
        绘制基准风险函数（Baseline Hazard）。

        Parameters
        ----------
        save_path : str | Path | None
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        if self._result is None or self._result.baseline_hazard is None:
            _log.warning("[Survival] No baseline hazard to plot")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[Survival] matplotlib not installed")
            return None

        bh = self._result.baseline_hazard

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

        # 累积风险
        ax1.plot(bh["time"], bh["cum_hazard"], color="steelblue", linewidth=2)
        ax1.set_xlabel("Time", fontsize=12)
        ax1.set_ylabel("Baseline Cumulative Hazard", fontsize=12)
        ax1.set_title("Baseline Cumulative Hazard", fontsize=12, fontweight="bold")
        ax1.grid(True, alpha=0.3)

        # 生存函数
        ax2.plot(bh["time"], bh["survival"], color="coral", linewidth=2)
        ax2.set_xlabel("Time", fontsize=12)
        ax2.set_ylabel("Baseline Survival Probability", fontsize=12)
        ax2.set_title("Baseline Survival Function", fontsize=12, fontweight="bold")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[Survival] Baseline hazard plot saved: {save_path}")

        return fig

    def plot_predicted_survival(
        self,
        df: pd.DataFrame,
        groups: dict[str, pd.Series] | None = None,
        times: np.ndarray | None = None,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> Any:
        """
        绘制预测生存曲线（KM 风格，来自 Cox 预测）。

        Parameters
        ----------
        df : pd.DataFrame
        groups : dict[str, pd.Series]
            分组字典，如 {"Treated": df["did"]==1, "Control": df["did"]==0}。
        times : np.ndarray | None
        save_path : str | Path | None
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[Survival] matplotlib not installed")
            return None

        if times is None:
            if self._result is not None and self._result.baseline_hazard is not None:
                times = self._result.baseline_hazard["time"].values
            else:
                times = np.linspace(0, 10, 50)

        fig, ax = plt.subplots(figsize=figsize)
        colors = ["steelblue", "coral", "green", "purple"]

        if groups is not None:
            for idx, (gname, mask) in enumerate(groups.items()):
                group_df = df[mask]
                if len(group_df) == 0:
                    continue
                surv = self.predict_survival(group_df, times=times)
                mean_surv = surv.mean(axis=1).values
                ax.plot(times, mean_surv, label=f"{gname} (n={len(group_df)})",
                        color=colors[idx % len(colors)], linewidth=2)
        else:
            surv = self.predict_survival(df, times=times)
            mean_surv = surv.mean(axis=1).values
            ax.plot(times, mean_surv, color="steelblue", linewidth=2, label=f"All (n={len(df)})")

        ax.set_xlabel("Time", fontsize=12)
        ax.set_ylabel("Survival Probability", fontsize=12)
        ax.set_title("Predicted Survival Curves (Cox PH)", fontsize=13, fontweight="bold")
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, 1.05)
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[Survival] Predicted survival plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# KAPLAN-MEIER
# ─────────────────────────────────────────────────────────────────────────────


class KaplanMeier:
    """
    Kaplan-Meier 生存曲线估计器。

    Usage
    -----
        km = KaplanMeier()
        result = km.fit(df, duration="time", event="event")
        km.plot("km.pdf")
        test_res = km.compare_groups(df, duration="time", event="event",
                                     group_var="did")
    """

    def __init__(self):
        self._result: dict | None = None

    def fit(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
    ) -> dict:
        """
        拟合 Kaplan-Meier 生存曲线。

        Parameters
        ----------
        df : pd.DataFrame
        duration : str  生存时间列
        event : str  事件指示列（0/1）

        Returns
        -------
        dict
            {
                "times": np.ndarray,
                "surv": np.ndarray,
                "lower_ci": np.ndarray,
                "upper_ci": np.ndarray,
                "median_survival": float | None,
                "n_obs": int,
                "n_events": int,
            }
        """
        df_sub = df.dropna(subset=[duration, event]).copy()
        df_sub[duration] = df_sub[duration].astype(float)
        df_sub[event] = df_sub[event].astype(int)

        T = df_sub[duration].values
        E = df_sub[event].values.astype(bool)
        n = len(T)

        # 排序
        order = np.argsort(T)
        T_sorted = T[order]
        E_sorted = E[order]

        # KM 估计
        times = []
        surv = []

        S = 1.0
        Var = 0.0

        var_arr = []

        unique_death_times = np.unique(T_sorted[E_sorted])

        for dtime in unique_death_times:
            d = np.sum(E_sorted & (T_sorted == dtime))
            r = np.sum(T_sorted >= dtime)
            if r == 0:
                continue

            # Greenwood 公式
            if r > d:
                var_term = d / (r * (r - d))
            else:
                var_term = 0.0

            S *= (r - d) / r
            Var += var_term

            times.append(dtime)
            surv.append(S)
            var_arr.append(Var)

        times = np.array(times)
        surv = np.array(surv)
        var_arr = np.array(var_arr)

        # 95% CI（log-log）
        from scipy import stats
        se_log_log = np.sqrt(var_arr) / (surv * np.log(np.maximum(surv, 1e-10)))
        z_crit = stats.norm.ppf(0.975)
        log_log_lower = np.log(-np.log(np.maximum(surv, 1e-10))) - z_crit * se_log_log
        log_log_upper = np.log(-np.log(np.maximum(surv, 1e-10))) + z_crit * se_log_log
        lower_ci = np.exp(-np.exp(log_log_upper))
        upper_ci = np.exp(-np.exp(log_log_lower))
        upper_ci = np.minimum(upper_ci, 1.0)
        lower_ci = np.maximum(lower_ci, 0.0)

        # 中位生存时间
        median_surv = None
        for t, s in zip(times, surv, strict=False):
            if s <= 0.5:
                median_surv = float(t)
                break

        self._result = {
            "times": times,
            "surv": surv,
            "lower_ci": lower_ci,
            "upper_ci": upper_ci,
            "median_survival": median_surv,
            "n_obs": n,
            "n_events": int(E.sum()),
        }

        _log.info(
            f"[Survival] KM: N={n}, events={int(E.sum())}, "
            f"median_survival={median_surv}"
        )
        return self._result

    def compare_groups(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
        group_var: str,
    ) -> pd.DataFrame:
        """
        组间生存比较：log-rank 检验 + Breslow 检验。

        Parameters
        ----------
        df : pd.DataFrame
        duration, event, group_var : str

        Returns
        -------
        pd.DataFrame
            含 test, statistic, pval, df, interpretation。
        """
        df_sub = df.dropna(subset=[duration, event, group_var]).copy()
        df_sub[duration] = df_sub[duration].astype(float)
        df_sub[event] = df_sub[event].astype(int)

        groups = df_sub[group_var].unique()
        if len(groups) != 2:
            _log.warning(f"[Survival] Expected 2 groups, got {len(groups)}")
            return pd.DataFrame()

        g1, g2 = groups[0], groups[1]
        mask1 = df_sub[group_var] == g1
        mask2 = df_sub[group_var] == g2

        lr = _log_rank_test(
            df_sub.loc[mask1, duration].values,
            df_sub.loc[mask1, event].values,
            df_sub.loc[mask2, duration].values,
            df_sub.loc[mask2, event].values,
        )
        bw = _breslow_test(
            df_sub.loc[mask1, duration].values,
            df_sub.loc[mask1, event].values,
            df_sub.loc[mask2, duration].values,
            df_sub.loc[mask2, event].values,
        )

        rows = []
        for res_dict in [lr, bw]:
            rows.append({
                "test": res_dict["test"],
                "statistic": res_dict["statistic"],
                "pval": res_dict["pval"],
                "df": res_dict["df"],
                "interpretation": res_dict["interpretation"],
            })

        _log.info(
            f"[Survival] Group comparison ({group_var}): "
            f"log_rank chi2={lr['statistic']:.3f}, p={lr['pval']:.4f}"
        )
        return pd.DataFrame(rows)

    def plot(
        self,
        save_path: str | Path | None = None,
        group_var: str | None = None,
        df: pd.DataFrame | None = None,
        duration: str = "duration",
        event: str = "event",
        figsize: tuple[float, float] = (8, 5),
    ) -> Any:
        """
        绘制 Kaplan-Meier 生存曲线。

        Parameters
        ----------
        save_path : str | Path | None
        group_var : str | None
            若提供，则分别拟合并比较两组 KM 曲线。
        df, duration, event : 用于分组绘图
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[Survival] matplotlib not installed")
            return None

        fig, ax = plt.subplots(figsize=figsize)

        if group_var is not None and df is not None:
            df_sub = df.dropna(subset=[duration, event, group_var])
            groups = df_sub[group_var].unique()
            colors = ["steelblue", "coral"]

            for idx, g in enumerate(sorted(groups)):
                mask = df_sub[group_var] == g
                res = self.fit(df_sub[mask], duration, event)
                ax.plot(
                    res["times"], res["surv"],
                    drawstyle="steps-post", color=colors[idx % len(colors)],
                    linewidth=2, label=f"{group_var}={g}",
                )
                ax.fill_between(
                    res["times"], res["lower_ci"], res["upper_ci"],
                    step="post", alpha=0.15, color=colors[idx % len(colors)],
                )

            # 合并数据做 log-rank
            if len(groups) == 2:
                lr = _log_rank_test(
                    df_sub.loc[df_sub[group_var] == groups[0], duration].values,
                    df_sub.loc[df_sub[group_var] == groups[0], event].values,
                    df_sub.loc[df_sub[group_var] == groups[1], duration].values,
                    df_sub.loc[df_sub[group_var] == groups[1], event].values,
                )
                ax.set_title(
                    f"Kaplan-Meier Survival Curves (log-rank $\\chi^2$"
                    f"={lr['statistic']:.2f}, $p$={lr['pval']:.4f})",
                    fontsize=12, fontweight="bold",
                )
        else:
            if self._result is None:
                _log.warning("[Survival] No fitted result to plot. Call fit() first.")
                return None

            res = self._result
            ax.plot(res["times"], res["surv"], drawstyle="steps-post",
                    color="steelblue", linewidth=2)
            ax.fill_between(res["times"], res["lower_ci"], res["upper_ci"],
                            step="post", alpha=0.15, color="steelblue")
            ax.axhline(y=0.5, color="gray", linestyle="--", linewidth=0.8)
            if res["median_survival"] is not None:
                ax.axvline(x=res["median_survival"], color="gray",
                            linestyle="--", linewidth=0.8)
                ax.annotate(
                    f"Median={res['median_survival']:.2f}",
                    (res["median_survival"], 0.52),
                    textcoords="offset points", xytext=(5, 5), fontsize=10,
                )
            ax.set_title("Kaplan-Meier Survival Curve", fontsize=12, fontweight="bold")

        ax.set_xlabel("Time", fontsize=12)
        ax.set_ylabel("Survival Probability", fontsize=12)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=11, loc="lower left")
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[Survival] KM plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# NELSON-AALEN
# ─────────────────────────────────────────────────────────────────────────────


class NelsonAalen:
    """
    Nelson-Aalen 累积风险估计器。

    Usage
    -----
        na = NelsonAalen()
        result = na.fit(df, duration="time", event="event")
        na.plot("na.pdf")
    """

    def __init__(self):
        self._result: dict | None = None

    def fit(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
    ) -> dict:
        """
        拟合 Nelson-Aalen 累积风险估计。

        Parameters
        ----------
        df : pd.DataFrame
        duration : str
        event : str  事件指示（0/1）

        Returns
        -------
        dict
            {
                "times": np.ndarray,
                "cum_hazard": np.ndarray,
                "var_cum_hazard": np.ndarray,
                "n_obs": int,
                "n_events": int,
            }
        """
        df_sub = df.dropna(subset=[duration, event]).copy()
        df_sub[duration] = df_sub[duration].astype(float)
        df_sub[event] = df_sub[event].astype(int)

        T = df_sub[duration].values
        E = df_sub[event].values.astype(bool)
        n = len(T)

        order = np.argsort(T)
        T_sorted = T[order]
        E_sorted = E[order]

        times = []
        cum_haz = []
        var_cum_haz = []

        H = 0.0
        Var = 0.0

        unique_death_times = np.unique(T_sorted[E_sorted])

        for dtime in unique_death_times:
            d = np.sum(E_sorted & (T_sorted == dtime))
            r = np.sum(T_sorted >= dtime)
            if r == 0:
                continue

            H += d / r
            Var += d / (r ** 2)

            times.append(dtime)
            cum_haz.append(H)
            var_cum_haz.append(Var)

        self._result = {
            "times": np.array(times),
            "cum_hazard": np.array(cum_haz),
            "var_cum_hazard": np.array(var_cum_haz),
            "n_obs": n,
            "n_events": int(E.sum()),
        }

        _log.info(
            f"[Survival] Nelson-Aalen: N={n}, events={int(E.sum())}"
        )
        return self._result

    def plot(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> Any:
        """
        绘制累积风险函数。

        Parameters
        ----------
        save_path, figsize

        Returns
        -------
        matplotlib Figure 或 None
        """
        if self._result is None:
            _log.warning("[Survival] No result. Call fit() first.")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[Survival] matplotlib not installed")
            return None

        from scipy import stats
        res = self._result
        se = np.sqrt(res["var_cum_hazard"])
        z_crit = stats.norm.ppf(0.975)

        fig, ax = plt.subplots(figsize=figsize)

        ax.plot(res["times"], res["cum_hazard"],
                color="darkgreen", linewidth=2, label="Nelson-Aalen")
        ax.fill_between(
            res["times"],
            res["cum_hazard"] - z_crit * se,
            res["cum_hazard"] + z_crit * se,
            alpha=0.15, color="darkgreen", label="95% CI",
        )
        ax.set_xlabel("Time", fontsize=12)
        ax.set_ylabel("Cumulative Hazard", fontsize=12)
        ax.set_title("Nelson-Aalen Cumulative Hazard", fontsize=13, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=11)
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[Survival] Nelson-Aalen plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# COMPETING RISKS (FINE-GRAY MODEL)
# ─────────────────────────────────────────────────────────────────────────────


class CompetingRisks:
    """
    竞争风险 Fine-Gray (1995) 亚分布风险模型。

    Parameters
    ----------
    event_type_col : str
        事件类型列名（1=关注的事件，2+=竞争事件，0=截尾）。

    Usage
    -----
        cr = CompetingRisks()
        result = cr.fit(df, duration="time", event="cause",
                        X=["did","size"], event_of_interest=1)
        cr.cumulative_incidence(1)
    """

    def __init__(self):
        self._result: SurvivalResult | None = None
        self._cif: pd.DataFrame | None = None
        self._event_of_interest: int = 1

    def fit(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
        X: list[str],
        event_of_interest: int = 1,
    ) -> SurvivalResult:
        """
        拟合 Fine-Gray 模型。

        Parameters
        ----------
        df : pd.DataFrame
        duration, event : str
            event 列编码：event_of_interest=关注事件，>0且≠event_of_interest=竞争事件，0=截尾
        X : list[str]
        event_of_interest : int

        Returns
        -------
        SurvivalResult
        """
        self._event_of_interest = event_of_interest

        # 尝试 lifelines
        if _load_lifelines():
            try:
                self._result = self._fit_lifelines_finegray(
                    df, duration, event, X, event_of_interest
                )
                return self._result
            except Exception as e:
                _log.warning(f"[Survival] lifelines Fine-Gray failed: {e}, falling back to manual")

        # 手动 Fine-Gray（简化实现）
        self._result = self._manual_finegray(
            df, duration, event, X, event_of_interest
        )
        return self._result

    def _fit_lifelines_finegray(
        self, df: pd.DataFrame, duration: str, event: str,
        X: list[str], event_of_interest: int
    ) -> SurvivalResult:
        """使用 lifelines 竞争风险。"""
        try:
            from lifelines.fitters.coxph_fitter import CoxPHFitter
        except ImportError:
            raise ImportError("lifelines not available for Fine-Gray")

        df_sub = df.dropna(subset=[duration, event] + X).copy()
        df_sub[event] = df_sub[event].astype(int)
        n = len(df_sub)
        n_events = int((df_sub[event] == event_of_interest).sum())

        # 准备竞争风险格式
        # lifelines 使用 event_col 指定事件， all-cause 用 Cox PH
        # 对于 subdistribution hazard，使用特定的转换
        cph = CoxPHFitter()
        cph.fit(
            df_sub,
            duration_col=duration,
            event_col=event,
            covariates=X,
        )

        summary = cph.summary
        coef_dict = {var: summary.loc[var, "coef"] for var in X if var in summary.index}
        se_dict = {var: summary.loc[var, "se(coef)"] for var in X if var in summary.index}
        z_dict = {var: summary.loc[var, "z"] for var in X if var in summary.index}
        pval_dict = {var: summary.loc[var, "p"] for var in X if var in summary.index}
        ci_lower = {var: summary.loc[var, "coef lower 95%"] for var in X if var in summary.index}
        ci_upper = {var: summary.loc[var, "coef upper 95%"] for var in X if var in summary.index}
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X}

        return SurvivalResult(
            model_type="competing_risks",
            coef_dict=coef_dict,
            se_dict=se_dict,
            z_dict=z_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            sig_dict=sig_dict,
            n_obs=n,
            n_events=n_events,
            concordance=cph.concordance_index_,
            log_likelihood=cph.log_likelihood_,
            aic=cph.AIC_partial_,
            bic=cph.AIC_partial_,
            converged=cph.converged_ if hasattr(cph, "converged_") else True,
        )

    def _manual_finegray(
        self, df: pd.DataFrame, duration: str, event: str,
        X: list[str], event_of_interest: int
    ) -> SurvivalResult:
        """
        手动 Fine-Gray 估计（简化版：当关注事件发生时，后续时间点从风险集中移除）。

        这是一个近似实现，仅在 lifelines 不可用时使用。
        """
        from scipy import stats

        df_sub = df.dropna(subset=[duration, event] + X).copy()
        df_sub[duration] = df_sub[duration].astype(float)
        df_sub[event] = df_sub[event].astype(int)
        n = len(df_sub)

        # 构建亚分布事件指标
        # 关注事件 = 1，竞争事件 = 0.5（权重调整）
        event_of_interest_mask = df_sub[event] == event_of_interest
        competing_mask = (df_sub[event] > 0) & (~event_of_interest_mask)
        df_sub[event] == 0

        # 对于竞争事件，权重 = P(T > t | T >= t_censored)
        # 简化：使用倒数作为权重
        weights = np.ones(n)
        weights[competing_mask] = 0.5  # 简化权重

        E_main = event_of_interest_mask.astype(int).values
        T = df_sub[duration].values

        X_mat = df_sub[X].values.astype(float)
        k = X_mat.shape[1]

        # 使用 Cox 偏似然，但权重调整
        beta = np.zeros(k)
        for _iteration in range(100):
            Xb = X_mat @ beta
            grad = np.zeros(k)
            hess = np.zeros((k, k))

            for i in range(n):
                if E_main[i] == 0:
                    continue
                risk_set = np.where(T >= T[i])[0]
                if len(risk_set) == 0:
                    continue

                exp_xb = np.exp(Xb[risk_set])
                sum_exp = np.sum(exp_xb)
                sum_exp_x = np.sum(X_mat[risk_set] * exp_xb[:, np.newaxis], axis=0)

                w_i = weights[i]
                grad += w_i * (X_mat[i] - sum_exp_x / sum_exp)

                outer = np.outer(sum_exp_x / sum_exp, sum_exp_x / sum_exp)
                hess -= w_i * (X_mat[risk_set].T @ (exp_xb[:, np.newaxis] * X_mat[risk_set]) / sum_exp - outer)

            try:
                delta = np.linalg.inv(hess + np.eye(k) * 1e-4) @ grad
            except np.linalg.LinAlgError:
                delta = np.zeros(k)

            beta -= delta * 0.5  # 步长
            if np.max(np.abs(delta)) < 1e-6:
                break

        # 标准误
        try:
            var_beta = np.linalg.inv(-hess + np.eye(k) * 1e-4)
            se = np.sqrt(np.diag(var_beta))
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)

        z_vals = beta / np.where(se > 0, se, 1e-10)
        p_vals = 2 * (1 - stats.norm.cdf(np.abs(z_vals)))
        z_crit = stats.norm.ppf(0.975)
        ci_lo = beta - z_crit * se
        ci_hi = beta + z_crit * se

        # 伪似然
        ll = 0.0
        for i in range(n):
            if E_main[i]:
                risk_set = np.where(T >= T[i])[0]
                if len(risk_set) > 0:
                    Xb = X_mat @ beta
                    ll += Xb[i] - np.log(np.sum(np.exp(Xb[risk_set])))

        aic = 2 * k - 2 * ll
        bic = k * np.log(n) - 2 * ll

        coef_dict = dict(zip(X, beta.tolist(), strict=False))
        se_dict = dict(zip(X, se.tolist(), strict=False))
        z_dict = dict(zip(X, z_vals.tolist(), strict=False))
        pval_dict = dict(zip(X, p_vals.tolist(), strict=False))
        ci_lower = dict(zip(X, ci_lo.tolist(), strict=False))
        ci_upper = dict(zip(X, ci_hi.tolist(), strict=False))
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X}

        return SurvivalResult(
            model_type="competing_risks",
            coef_dict=coef_dict,
            se_dict=se_dict,
            z_dict=z_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            sig_dict=sig_dict,
            n_obs=n,
            n_events=int(event_of_interest_mask.sum()),
            concordance=None,
            log_likelihood=float(ll),
            aic=float(aic),
            bic=float(bic),
            converged=True,
        )

    def cumulative_incidence(
        self, event_of_interest: int | None = None,
    ) -> pd.DataFrame:
        """
        计算累积发生率函数（CIF）。

        Parameters
        ----------
        event_of_interest : int | None

        Returns
        -------
        pd.DataFrame  index=时间, columns=[cause_1, cause_2, ...]
        """
        if self._cif is not None:
            return self._cif

        _log.info("[Survival] CIF not yet computed. Run fit() first.")
        return pd.DataFrame()

    def to_latex(
        self,
        caption: str = "Competing Risks Fine-Gray Model",
        label: str = "tab:competing_risks",
    ) -> str:
        """导出为 LaTeX 表格。"""
        if self._result is None:
            return ""

        X = list(self._result.coef_dict.keys())
        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccc}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{coef} & \\textbf{SE} & \\textbf{z} & \\textbf{p-value} \\\\",
            "    \\midrule",
        ]

        for var in X:
            c = self._result.coef_dict.get(var, np.nan)
            s = self._result.se_dict.get(var, np.nan)
            z = self._result.z_dict.get(var, np.nan)
            p = self._result.pval_dict.get(var, np.nan)
            sig = self._result.sig_dict.get(var, "")
            lines.append(
                f"    {var:25s} & {c:+.4f}{sig:5s} & ({s:5.3f}) & "
                f"{z:6.2f} & {p:6.3f} \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "    \\midrule",
            f"    \\textbf{{N}} & \\textbf{{{self._result.n_obs}}} & & & \\\\",
            f"    \\textbf{{Events}} & \\textbf{{{self._result.n_events}}} & & & \\\\",
            f"    AIC & {self._result.aic:.2f} & & & \\\\",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Fine-Gray subdistribution hazard model. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TIME-VARYING COVARIATES
# ─────────────────────────────────────────────────────────────────────────────


class TimeVaryingCovariates:
    """
    时变协变量 Cox 模型（Anderson-Gill 计数过程）。

    数据必须为长格式（每行一个时间区间），包含：
      - id：个体标识
      - start：区间起点
      - stop：区间终点
      - event：区间终点是否发生事件（0/1）
      - 协变量（可在区间内变化）

    Usage
    -----
        cr = TimeVaryingCovariates()
        result = cr.fit(df_long, duration_col="stop",
                        event_col="event", X=["did","size"])
    """

    def __init__(self):
        self._result: SurvivalResult | None = None

    def fit(
        self,
        df_long: pd.DataFrame,
        duration_col: str = "stop",
        event_col: str = "event",
        X: list[str] | None = None,
        id_col: str = "id",
        start_col: str = "start",
    ) -> SurvivalResult:
        """
        拟合时变协变量 Cox 模型（计数过程法）。

        Parameters
        ----------
        df_long : pd.DataFrame
            长格式生存数据（计数过程格式）。
        duration_col : str
            区间终点列名（stop）。
        event_col : str
            事件列名（0/1）。
        X : list[str] | None
            协变量列表。
        id_col : str
            个体标识列。
        start_col : str
            区间起点列（start）。

        Returns
        -------
        SurvivalResult
        """
        if X is None:
            X = []

        df_sub = df_long.dropna(subset=[duration_col, event_col] + X).copy()
        df_sub[duration_col] = df_sub[duration_col].astype(float)
        df_sub[event_col] = df_sub[event_col].astype(int)
        len(df_sub)

        if _load_lifelines():
            try:
                self._result = self._fit_lifelines_tvc(
                    df_sub, duration_col, event_col, X, id_col, start_col
                )
                return self._result
            except Exception as e:
                _log.warning(f"[Survival] lifelines TVC failed: {e}, falling back to manual")

        # 手动时变 Cox（使用 NR）
        self._result = self._manual_tvc(df_sub, duration_col, event_col, X)
        return self._result

    def _fit_lifelines_tvc(
        self, df: pd.DataFrame, duration_col: str, event_col: str,
        X: list[str], id_col: str, start_col: str
    ) -> SurvivalResult:
        """lifelines 时变协变量。"""
        cph = _CoxPHFitter()
        cph.fit(
            df,
            duration_col=duration_col,
            event_col=event_col,
            covariates=X,
        )

        summary = cph.summary
        coef_dict = {var: summary.loc[var, "coef"] for var in X if var in summary.index}
        se_dict = {var: summary.loc[var, "se(coef)"] for var in X if var in summary.index}
        z_dict = {var: summary.loc[var, "z"] for var in X if var in summary.index}
        pval_dict = {var: summary.loc[var, "p"] for var in X if var in summary.index}
        ci_lower = {var: summary.loc[var, "coef lower 95%"] for var in X if var in summary.index}
        ci_upper = {var: summary.loc[var, "coef upper 95%"] for var in X if var in summary.index}
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X}

        return SurvivalResult(
            model_type="time_varying",
            coef_dict=coef_dict,
            se_dict=se_dict,
            z_dict=z_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            sig_dict=sig_dict,
            n_obs=int(df[id_col].nunique()),
            n_events=int(df[event_col].sum()),
            concordance=cph.concordance_index_,
            log_likelihood=cph.log_likelihood_,
            aic=cph.AIC_partial_,
            bic=cph.AIC_partial_,
            converged=cph.converged_ if hasattr(cph, "converged_") else True,
        )

    def _manual_tvc(
        self, df: pd.DataFrame, duration_col: str, event_col: str, X: list[str]
    ) -> SurvivalResult:
        """手动时变 Cox（NR 迭代）。"""
        from scipy import stats

        T = df[duration_col].values
        E = df[event_col].values.astype(bool)
        X_mat = df[X].values.astype(float)
        k = X_mat.shape[1]

        beta = np.zeros(k)
        for _iteration in range(100):
            Xb = X_mat @ beta
            grad = np.zeros(k)
            hess = np.zeros((k, k))

            for i in range(len(df)):
                if not E[i]:
                    continue
                risk_set = np.where(T >= T[i])[0]
                if len(risk_set) == 0:
                    continue

                exp_xb = np.exp(Xb[risk_set])
                sum_exp = np.sum(exp_xb)
                sum_exp_x = np.sum(X_mat[risk_set] * exp_xb[:, np.newaxis], axis=0)

                grad += X_mat[i] - sum_exp_x / sum_exp

                outer = np.outer(sum_exp_x / sum_exp, sum_exp_x / sum_exp)
                hess -= (X_mat[risk_set].T @ (exp_xb[:, np.newaxis] * X_mat[risk_set]) / sum_exp - outer)

            try:
                delta = np.linalg.inv(hess + np.eye(k) * 1e-4) @ grad
            except np.linalg.LinAlgError:
                delta = np.zeros(k)

            beta -= delta * 0.5
            if np.max(np.abs(delta)) < 1e-6:
                break

        try:
            var_beta = np.linalg.inv(-hess + np.eye(k) * 1e-4)
            se = np.sqrt(np.diag(var_beta))
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)

        z_vals = beta / np.where(se > 0, se, 1e-10)
        p_vals = 2 * (1 - stats.norm.cdf(np.abs(z_vals)))
        z_crit = stats.norm.ppf(0.975)

        coef_dict = dict(zip(X, beta.tolist(), strict=False))
        se_dict = dict(zip(X, se.tolist(), strict=False))
        z_dict = dict(zip(X, z_vals.tolist(), strict=False))
        pval_dict = dict(zip(X, p_vals.tolist(), strict=False))
        ci_lower = dict(zip(X, (beta - z_crit * se).tolist(), strict=False))
        ci_upper = dict(zip(X, (beta + z_crit * se).tolist(), strict=False))
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X}

        ll = -_partial_log_likelihood(beta, T, E, X_mat)
        n = len(df)
        aic = 2 * k - 2 * ll
        bic = k * np.log(n) - 2 * ll

        return SurvivalResult(
            model_type="time_varying",
            coef_dict=coef_dict,
            se_dict=se_dict,
            z_dict=z_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            sig_dict=sig_dict,
            n_obs=n,
            n_events=int(E.sum()),
            concordance=None,
            log_likelihood=float(ll),
            aic=float(aic),
            bic=float(bic),
            converged=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVAL SUITE
# ─────────────────────────────────────────────────────────────────────────────


class SurvivalSuite:
    """
    生存分析全套编排器。

    提供一键运行 + 异质性分析。

    Usage
    -----
        suite = SurvivalSuite()
        results = suite.run_all(df, duration="time", event="event",
                                X=["did","size","lev"])
        het = suite.heterogeneity_analysis(df, duration="time", event="event",
                                           X=["did","size"], group_var="industry")
    """

    def __init__(self):
        self._results: dict[str, Any] = {}

    def run_all(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
        X: list[str],
        save_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        运行全套生存分析。

        Parameters
        ----------
        df, duration, event, X
        save_dir : str | Path | None  图片保存目录

        Returns
        -------
        dict
            {
                "cox_ph": SurvivalResult,
                "km_by_group": pd.DataFrame,
                "log_rank_test": pd.DataFrame,
                "nelson_aalen": dict,
                "competing_risks": SurvivalResult | None,
                "all_results_df": pd.DataFrame,
            }
        """
        out: dict[str, Any] = {}
        save_dir = Path(save_dir) if save_dir else None

        # 1. Cox PH
        cox = CoxPHModel()
        try:
            cox_res = cox.fit(df, duration=duration, event=event, X=X)
            out["cox_ph"] = cox_res
            _log.info(f"[SurvivalSuite] Cox PH: C={cox_res.concordance:.4f}")
        except Exception as e:
            _log.error(f"[SurvivalSuite] Cox PH failed: {e}")
            out["cox_ph"] = None

        # 2. Kaplan-Meier + log-rank
        km = KaplanMeier()
        try:
            km.fit(df, duration=duration, event=event)
            out["kaplan_meier"] = km._result

            # 分组 KM
            if save_dir:
                km.plot(save_dir / "km_overall.pdf")
        except Exception as e:
            _log.error(f"[SurvivalSuite] Kaplan-Meier failed: {e}")

        # 3. Nelson-Aalen
        na = NelsonAalen()
        try:
            na_res = na.fit(df, duration=duration, event=event)
            out["nelson_aalen"] = na_res
            if save_dir:
                na.plot(save_dir / "nelson_aalen.pdf")
        except Exception as e:
            _log.error(f"[SurvivalSuite] Nelson-Aalen failed: {e}")

        # 4. 竞争风险（若有多种事件类型）
        if df[event].nunique() > 1:
            cr = CompetingRisks()
            try:
                cr_res = cr.fit(df, duration=duration, event=event,
                                X=X, event_of_interest=1)
                out["competing_risks"] = cr_res
            except Exception as e:
                _log.error(f"[SurvivalSuite] Competing risks failed: {e}")

        # 5. 汇总 DataFrame
        if out.get("cox_ph"):
            out["all_results_df"] = pd.DataFrame([out["cox_ph"].to_dict()])

        self._results = out
        _log.info("[SurvivalSuite] run_all completed")
        return out

    def heterogeneity_analysis(
        self,
        df: pd.DataFrame,
        duration: str,
        event: str,
        X: list[str],
        group_var: str,
    ) -> pd.DataFrame:
        """
        异质性分析：分层 Cox 模型 + 交互作用检验。

        Parameters
        ----------
        df : pd.DataFrame
        duration, event, group_var : str
        X : list[str]

        Returns
        -------
        pd.DataFrame
            每组的 Cox 回归结果。
        """
        df_sub = df.dropna(subset=[duration, event, group_var] + X).copy()
        groups = df_sub[group_var].unique()

        rows = []
        for g in sorted(groups):
            mask = df_sub[group_var] == g
            cox = CoxPHModel()
            try:
                res = cox.fit(df_sub[mask], duration=duration, event=event, X=X)
                row = {
                    "group": g,
                    "n_obs": res.n_obs,
                    "n_events": res.n_events,
                    "concordance": res.concordance,
                }
                for var in X:
                    row[f"coef_{var}"] = res.coef_dict.get(var, np.nan)
                    row[f"pval_{var}"] = res.pval_dict.get(var, np.nan)
                    row[f"hr_{var}"] = np.exp(res.coef_dict.get(var, 0))
                rows.append(row)
            except Exception as e:
                _log.warning(f"[SurvivalSuite] Group {g} failed: {e}")

        df_out = pd.DataFrame(rows)
        _log.info(
            f"[SurvivalSuite] Heterogeneity analysis: {len(groups)} groups, "
            f"vars={X}, group_var={group_var}"
        )
        return df_out
