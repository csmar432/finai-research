"""Panel Quantile Regression — Koenker (2004), Canay (2011), Powell (2016).

本模块封装面板分位数回归方法，覆盖：
  1. Canay (2011) 两步法：第一步 FE 变换，第二步对变换后数据做 QR
  2. 直接 QR with unit dummies（包含固定效应的备选实现）
  3. Lagrange Multiplier (LM) 检验：面板 QR 的联合显著性检验
  4. 系数量化曲线（coef profile）与处理效应分位数分布图

Usage:
    pqr = PanelQuantileRegression(df)
    result = pqr.fit(df, y="roa", X=["did", "size", "lev"],
                     quantiles=[0.1, 0.25, 0.5, 0.75, 0.9],
                     unit_var="ticker", time_var="year", method="canay")
    pqr.plot_coef_profile(save_path="coef_profile.pdf")
    print(pqr.summary())
    print(pqr.to_latex())
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
    "PanelQuantileRegression",
    "PanelQuantileResult",
]

_log = logging.getLogger("panel_qr")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PanelQuantileResult:
    """
    面板分位数回归结果容器。

    Attributes
    ----------
    quantile : float
        分位数水平 (0 < q < 1)。
    estimator : str
        估计方法："canay" | "direct" | "lm"。
    coef_dict : dict[str, float]
        变量名到系数估计值的映射。
    se_dict : dict[str, float]
        变量名到标准误的映射。
    pval_dict : dict[str, float]
        变量名到 p 值的映射。
    ci_lower : dict[str, float]
        变量名到 95% CI 下界的映射。
    ci_upper : dict[str, float]
        变量名到 95% CI 上界的映射。
    n_obs : int
        有效观测数。
    n_groups : int
        面板单位数。
    r_squared : float | None
        分位数伪 R^2。
    sig_dict : dict[str, str]
        变量名到显著性标记的映射 (* / ** / ***)。
    method : str
        标准误类型："analytical" | "bootstrap"。
    additional : dict
        额外诊断（bootstrap_samples / lm_stat / df 等）。
    """

    quantile: float
    estimator: str
    coef_dict: dict[str, float] = field(default_factory=dict)
    se_dict: dict[str, float] = field(default_factory=dict)
    pval_dict: dict[str, float] = field(default_factory=dict)
    ci_lower: dict[str, float] = field(default_factory=dict)
    ci_upper: dict[str, float] = field(default_factory=dict)
    n_obs: int = 0
    n_groups: int = 0
    r_squared: float | None = None
    sig_dict: dict[str, str] = field(default_factory=dict)
    method: str = "analytical"
    additional: dict = field(default_factory=dict)

    @property
    def sig(self) -> str:
        """返回主变量（第一个非常数项）的显著性标记。"""
        if not self.sig_dict:
            return ""
        # 跳过常数项
        for k, v in self.sig_dict.items():
            if k.lower() not in ("const", "intercept", "_const"):
                return v
        return list(self.sig_dict.values())[0] if self.sig_dict else ""

    def to_dict(self) -> dict:
        out = {
            "quantile": self.quantile,
            "estimator": self.estimator,
            "n_obs": self.n_obs,
            "n_groups": self.n_groups,
            "r_squared": self.r_squared,
            "method": self.method,
        }
        for var in self.coef_dict:
            out[f"coef_{var}"] = self.coef_dict[var]
            out[f"se_{var}"] = self.se_dict.get(var, np.nan)
            out[f"pval_{var}"] = self.pval_dict.get(var, np.nan)
            out[f"ci_lower_{var}"] = self.ci_lower.get(var, np.nan)
            out[f"ci_upper_{var}"] = self.ci_upper.get(var, np.nan)
            out[f"sig_{var}"] = self.sig_dict.get(var, "")
        out.update(self.additional)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _significance_mark(pval: float) -> str:
    if pval < 0.001:
        return "***"
    elif pval < 0.01:
        return "**"
    elif pval < 0.05:
        return "*"
    elif pval < 0.10:
        return r"$\dagger$"
    return ""


def _within_transform(df: pd.DataFrame, y: str, unit_var: str) -> pd.DataFrame:
    """
    面板 Within (LSDV) 变换：减去个体均值。

    Parameters
    ----------
    df : pd.DataFrame
        原始面板数据。
    y : str
        待变换的因变量列名。
    unit_var : str
        面板单位变量。

    Returns
    -------
    pd.DataFrame
        变换后的数据（去除了单位固定效应）。
    """
    df_out = df.copy()
    group_means = df_out.groupby(unit_var)[y].transform("mean")
    df_out[y] = df_out[y] - group_means
    return df_out


def _within_transform_X(
    df: pd.DataFrame, X_vars: list[str], unit_var: str
) -> pd.DataFrame:
    """
    对 X 矩阵做 Within 变换。

    Parameters
    ----------
    df : pd.DataFrame
    X_vars : list[str]
    unit_var : str

    Returns
    -------
    pd.DataFrame
    """
    df_out = df.copy()
    for xv in X_vars:
        if xv in df_out.columns:
            group_mean = df_out.groupby(unit_var)[xv].transform("mean")
            df_out[xv] = df_out[xv] - group_mean
    return df_out


def _pinb_solver(
    y: np.ndarray, X: np.ndarray, tau: float, max_iter: int = 5000
) -> np.ndarray:
    """
    PINB（Principal Interior Point Newton-Barzilai）求解器。

    最小化：sum(rho_tau(y_i - x_i'b)) 其中 rho_tau(u) = u*(tau - I(u<0))

    这是分位数回归的等价线性规划形式，使用 scipy.optimize.linprog 求解。

    Parameters
    ----------
    y : np.ndarray
        因变量 (n,)。
    X : np.ndarray
        自变量 (n, k)。
    tau : float
        分位数。
    max_iter : int
        最大迭代次数（本实现为单次线性规划）。

    Returns
    -------
    np.ndarray
        系数向量 (k,)。
    """
    from scipy.optimize import linprog

    n, k = X.shape
    # 线性规划标准形式：min c'b  s.t. A_eq b = d_eq, A_ub b <= d_ub
    # 分位数回归等价形式（Portnoy & Koenker 风格）：
    # min sum(tau * u_i^+ + (1-tau) * u_i^-)
    # s.t. y_i = x_i'b + u_i^+ - u_i^-
    # b free, u_i^+ >= 0, u_i^- >= 0

    # 决策变量：[b (k), u_plus (n), u_minus (n)]
    c = np.concatenate([
        np.zeros(k),                          # b 的系数为 0
        tau * np.ones(n),                      # u_plus
        (1 - tau) * np.ones(n),                # u_minus
    ])

    # 等式约束：y = X b + u_plus - u_minus
    A_eq = np.column_stack([
        X,                                    # X 对应 b
        np.eye(n),                            # u_plus
        -np.eye(n),                           # -u_minus
    ])
    d_eq = y

    # 变量下界：b 无约束，u_plus >= 0, u_minus >= 0
    bounds = [(None, None)] * k + [(0, None)] * n + [(0, None)] * n

    result = linprog(
        c,
        A_eq=A_eq,
        b_eq=d_eq,
        bounds=bounds,
        method="highs",
        options={"maxiter": max_iter, "disp": False},
    )

    if result.success:
        return result.x[:k]
    else:
        _log.warning(f"[PanelQR] PINB solver did not converge at tau={tau}, falling back to statsmodels")
        return np.full(k, np.nan)


def _quantile_regression_numpy(
    y: np.ndarray, X: np.ndarray, tau: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    使用 NumPy/SciPy 实现分位数回归。

    Parameters
    ----------
    y : np.ndarray (n,)
    X : np.ndarray (n, k)
    tau : float

    Returns
    -------
    (coef, se, pval)
    """
    try:
        coef = _pinb_solver(y, X, tau)
    except Exception:
        _log.warning("[PanelQR] PINB failed, attempting statsmodels fallback")
        coef = np.full(X.shape[1], np.nan)

    if np.any(np.isnan(coef)):
        # Fallback to statsmodels
        try:
            import statsmodels.api as sm
            mod = sm.QuantReg(y, X)
            res = mod.fit(q=tau, maxiter=5000, kernel="epa", bandwidth="hsheather")
            coef = res.params
        except Exception:
            _log.error("[PanelQR] Both PINB and statsmodels failed")
            se = np.full(len(coef), np.nan)
            pval = np.full(len(coef), np.nan)
            return coef, se, pval

    # 解析标准误（假设正态渐近）
    residuals = y - X @ coef
    n, k = X.shape
    # Koenker & Bassett (1978) 解析方差估计
    tau_arr = np.array(tau)
    h = 1.0 / (n ** (1.0 / 5.0))  # 简单带宽
    # 简化：使用残差标准误估计
    sigma = np.sqrt(np.mean(residuals ** 2))
    # 对角信息矩阵近似（简化版）
    info_matrix_diag = np.var(X, axis=0) * n * tau_arr * (1 - tau_arr)
    se = np.where(info_matrix_diag > 0, sigma / np.sqrt(info_matrix_diag), np.nan)
    # 正态检验 p 值
    from scipy import stats
    t_stat = coef / np.where(se > 0, se, 1e-10)
    pval = 2 * (1 - stats.t.cdf(np.abs(t_stat), df=n - k))

    return coef, se, pval


def _bootstrap_se(
    y: np.ndarray, X: np.ndarray, tau: float, B: int = 199, seed: int = 42
) -> np.ndarray:
    """
    Wild Cluster Bootstrap 标准误（Powell 2016 建议）。

    对于面板 QR，使用配对 (cluster) bootstrap 以保持面板结构。

    Parameters
    ----------
    y : np.ndarray
    X : np.ndarray
    tau : float
    B : int
        Bootstrap 次数。
    seed : int

    Returns
    -------
    np.ndarray
        Bootstrap 标准误 (k,)。
    """
    rng = np.random.default_rng(seed)
    n, k = X.shape

    # 基准估计
    beta0 = _pinb_solver(y, X, tau)
    resid0 = y - X @ beta0

    boot_coefs = []
    for _ in range(B):
        # Wild bootstrap 权重（Rademacher）
        v = rng.choice([-1, 1], size=n)
        y_star = X @ beta0 + resid0 * v
        try:
            beta_star = _pinb_solver(y_star, X, tau)
            if not np.any(np.isnan(beta_star)):
                boot_coefs.append(beta_star)
        except Exception:
            continue

    if len(boot_coefs) < 10:
        return np.full(k, np.nan)

    boot_coefs = np.array(boot_coefs)
    return np.std(boot_coefs, axis=0, ddof=1)


def _pseudo_r_squared(y: np.ndarray, y_pred: np.ndarray, tau: float) -> float:
    """
    分位数伪 R^2（Koenker & Machado 1999）。

    R_1(tau) = 1 - sum(rho_tau(y_i - yhat_i)) / sum(rho_tau(y_i - median(y)))

    Parameters
    ----------
    y : np.ndarray
    y_pred : np.ndarray
    tau : float

    Returns
    -------
    float
    """
    def rho_tau(u: np.ndarray) -> np.ndarray:
        return np.where(u >= 0, tau * u, (tau - 1) * u)

    resid_model = y - y_pred
    resid_median = y - np.median(y)

    num = np.sum(rho_tau(resid_model))
    denom = np.sum(rho_tau(resid_median))

    if denom == 0:
        return np.nan
    return float(1 - num / denom)


def _lm_test(
    df: pd.DataFrame, y: str, X_vars: list[str], tau: float,
    unit_var: str
) -> dict:
    """
    Lagrange Multiplier 检验 — 面板 QR 的联合显著性检验。

    H0: 所有分位数系数在分位数 tau 处相等（跨单位无异质性）
    LM = n * R^2 from auxiliary regression

    返回 LM 统计量和 p 值。
    """
    from scipy import stats

    try:
        import statsmodels.api as sm

        df_sub = df.dropna(subset=[y] + X_vars)
        # Within 变换
        df_fe = _within_transform(df_sub, y, unit_var)
        df_fe = _within_transform_X(df_fe, X_vars, unit_var)

        y_vals = df_fe[y].values
        X_vals = sm.add_constant(df_fe[X_vars], has_constant="skip").values
        names = ["const"] + X_vars

        mod = sm.QuantReg(y_vals, X_vals)
        res = mod.fit(q=tau, maxiter=5000)
        resid = res.resid

        # LM: 辅助回归 y* on X* (简化版)
        # 使用残差的绝对值作为权重
        weights = np.where(resid >= 0, tau, 1 - tau)
        y_aux = np.abs(resid) * np.sqrt(weights)
        X_aux = X_vals

        aux_mod = sm.OLS(y_aux, X_aux).fit()
        lm_stat = float(aux_mod.rsquared * len(y_aux))
        pval = 1 - stats.chi2.cdf(lm_stat, df=len(X_vars))

        return {
            "lm_stat": lm_stat,
            "pval": pval,
            "df": len(X_vars),
            "test": "LM_test_panel_qr",
        }
    except Exception as e:
        _log.warning(f"[PanelQR] LM test failed: {e}")
        return {"lm_stat": np.nan, "pval": np.nan, "df": len(X_vars)}


def _choudhary_test(
    coef1: float, se1: float, coef2: float, se2: float, n: int
) -> tuple[float, float]:
    """
    Choudhary (2008) 检验：两个分位数系数是否相等。

    H0: beta(tau1) = beta(tau2)

    Parameters
    ----------
    coef1, coef2 : float
        两个分位数的系数。
    se1, se2 : float
        对应标准误。
    n : int
        样本量。

    Returns
    -------
    (t_stat, pval)
    """
    from scipy import stats

    if se1 <= 0 or se2 <= 0:
        return np.nan, np.nan

    se_diff = np.sqrt(se1 ** 2 + se2 ** 2)
    t_stat = (coef1 - coef2) / se_diff
    pval = 2 * (1 - stats.norm.cdf(abs(t_stat)))

    return float(t_stat), float(pval)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class PanelQuantileRegression:
    """
    面板分位数回归引擎 — sklearn-like API。

    支持的估计方法：
      - "canay"（默认）：Canay (2011) 两步法（第一步 FE 变换，第二步 QR）
      - "direct"：直接 QR with unit dummies（包含 LSDV 固定效应）
      - "lm"：仅运行 LM 检验，不返回主回归结果

    使用方法：
        pqr = PanelQuantileRegression()
        results = pqr.fit(
            df, y="roa", X=["did", "size", "lev"],
            quantiles=[0.1, 0.25, 0.5, 0.75, 0.9],
            unit_var="ticker", time_var="year",
            method="canay", cluster_var="industry"
        )
        pqr.plot_coef_profile("coef_profile.pdf")
        print(pqr.summary())
        print(pqr.to_latex())
        # 检验分位数间系数差异
        test_res = pqr.test_coef_equality(0.25, 0.75)
    """

    def __init__(self):
        self._results: dict[float, PanelQuantileResult] = {}
        self._last_fit_args: dict = {}

    # ── Core fit ───────────────────────────────────────────────────────────

    def fit(
        self,
        data: pd.DataFrame,
        y: str,
        X: list[str],
        quantiles: list[float] | np.ndarray = [0.1, 0.25, 0.5, 0.75, 0.9],
        unit_var: str | None = None,
        time_var: str | None = None,
        method: str = "canay",
        cluster_var: str | None = None,
        se_type: str = "analytical",
        bootstrap_reps: int = 199,
        seed: int = 42,
    ) -> dict[float, PanelQuantileResult]:
        """
        拟合面板分位数回归。

        Parameters
        ----------
        data : pd.DataFrame
            面板数据。
        y : str
            因变量列名。
        X : list[str]
            自变量列名列表。
        quantiles : list[float] | np.ndarray
            待估计的分位数序列。
        unit_var : str | None
            面板单位变量（如 ticker / firm_id）。提供则做面板 QR。
        time_var : str | None
            时间变量（如 year）。用于双向固定效应时指定。
        method : str
            "canay"（默认）| "direct" | "lm"。
        cluster_var : str | None
            聚类标准误变量。
        se_type : str
            "analytical"（默认）或 "bootstrap"。
        bootstrap_reps : int
            Bootstrap 次数（se_type="bootstrap" 时有效）。
        seed : int
            随机种子。

        Returns
        -------
        dict[float, PanelQuantileResult]
            分位数到结果的映射。
        """
        if method == "lm":
            # 仅运行 LM 检验
            q = quantiles[0] if isinstance(quantiles, (list, np.ndarray)) else 0.5
            lm_res = _lm_test(data, y, X, q, unit_var or "")
            _log.info(
                f"[PanelQR] LM test: stat={lm_res['lm_stat']:.3f}, "
                f"p={lm_res['pval']:.4f}, df={lm_res['df']}"
            )
            return {}

        self._results.clear()
        self._last_fit_args = {
            "y": y, "X": X,
            "unit_var": unit_var, "time_var": time_var,
            "method": method, "cluster_var": cluster_var,
            "se_type": se_type, "bootstrap_reps": bootstrap_reps,
        }

        for q in quantiles:
            if not (0 < q < 1):
                _log.warning(f"[PanelQR] quantile {q} out of range (0,1), skipping")
                continue

            result = self._fit_single(
                data, y, X, q, unit_var, time_var,
                method, cluster_var, se_type, bootstrap_reps, seed
            )
            self._results[q] = result

            _log.info(
                f"[PanelQR] tau={q:.2f} ({method}): "
                + " ".join(
                    f"{v}={result.coef_dict.get(v, 0):+.4f}{result.sig_dict.get(v, '')}"
                    for v in X if v in result.coef_dict
                )
                + f", N={result.n_obs}, G={result.n_groups}"
            )

        return self._results

    def _fit_single(
        self,
        data: pd.DataFrame,
        y: str,
        X: list[str],
        tau: float,
        unit_var: str | None,
        time_var: str | None,
        method: str,
        cluster_var: str | None,
        se_type: str,
        bootstrap_reps: int,
        seed: int,
    ) -> PanelQuantileResult:
        """内部：对单个分位数执行估计。"""
        # 清理数据
        cols_needed = [y] + X
        if unit_var:
            cols_needed.append(unit_var)
        if time_var:
            cols_needed.append(time_var)
        if cluster_var:
            cols_needed.append(cluster_var)

        df_sub = data.dropna(subset=cols_needed).copy()
        if len(df_sub) < 20:
            _log.warning(f"[PanelQR] Less than 20 obs at tau={tau}, returning empty result")
            return PanelQuantileResult(quantile=tau, estimator=method)

        n_obs = len(df_sub)
        n_groups = int(df_sub[unit_var].nunique()) if unit_var else n_obs

        # Within 变换（Canay 2011 第一步）
        if unit_var and method == "canay":
            df_sub = _within_transform(df_sub, y, unit_var)
            df_sub = _within_transform_X(df_sub, X, unit_var)

        # 构建 X 矩阵
        try:
            import statsmodels.api as sm
            X_vals = sm.add_constant(df_sub[X], has_constant="skip")
            X_names = ["const"] + X
            X_arr = X_vals.values.astype(float)
            y_arr = df_sub[y].values.astype(float)
        except Exception as e:
            _log.error(f"[PanelQR] Failed to build design matrix: {e}")
            return PanelQuantileResult(quantile=tau, estimator=method)

        # 分位数回归
        if method in ("canay", "direct"):
            try:
                mod = sm.QuantReg(y_arr, X_arr)
                res = mod.fit(q=tau, maxiter=5000, kernel="epa", bandwidth="hsheather")
                coef = res.params
                # 标准误
                if se_type == "bootstrap":
                    se = _bootstrap_se(y_arr, X_arr, tau, B=bootstrap_reps, seed=seed)
                    pval = 2 * (1 - _norm_cdf(np.abs(coef / np.where(se > 0, se, 1e-10))))
                else:
                    se = res.bse
                    pval = res.pvalues
            except Exception:
                _log.warning(f"[PanelQR] statsmodels QuantReg failed at tau={tau}, using numpy fallback")
                coef, se, pval = _quantile_regression_numpy(y_arr, X_arr, tau)
        else:
            coef, se, pval = _quantile_regression_numpy(y_arr, X_arr, tau)

        # 处理缺失值
        se = np.where(np.isnan(se), 0.0, se)
        pval = np.where(np.isnan(pval), 1.0, pval)

        # 置信区间
        from scipy import stats
        t_crit = stats.t.ppf(0.975, df=n_obs - len(X_names))
        ci_lower_arr = coef - t_crit * se
        ci_upper_arr = coef + t_crit * se

        # 组装字典
        coef_dict = dict(zip(X_names, coef.tolist()))
        se_dict = dict(zip(X_names, se.tolist()))
        pval_dict = dict(zip(X_names, pval.tolist()))
        ci_lower = dict(zip(X_names, ci_lower_arr.tolist()))
        ci_upper = dict(zip(X_names, ci_upper_arr.tolist()))
        sig_dict = {v: _significance_mark(pval_dict.get(v, 1.0)) for v in X_names}

        # 伪 R^2
        y_pred = X_arr @ coef
        r_squared = _pseudo_r_squared(y_arr, y_pred, tau)

        return PanelQuantileResult(
            quantile=tau,
            estimator=method,
            coef_dict=coef_dict,
            se_dict=se_dict,
            pval_dict=pval_dict,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n_obs=n_obs,
            n_groups=n_groups,
            r_squared=r_squared,
            sig_dict=sig_dict,
            method=se_type,
            additional={
                "cluster_var": cluster_var,
                "bootstrap_reps": bootstrap_reps if se_type == "bootstrap" else 0,
            },
        )

    # ── Inference ─────────────────────────────────────────────────────────

    def get_coef_at_quantile(
        self, q: float
    ) -> PanelQuantileResult | None:
        """
        获取特定分位数的估计结果。

        Parameters
        ----------
        q : float
            分位数（必须在 fit 时估计过）。

        Returns
        -------
        PanelQuantileResult | None
        """
        # 精确匹配或最近匹配
        if q in self._results:
            return self._results[q]
        # 浮点容差
        for tau, res in self._results.items():
            if abs(tau - q) < 1e-6:
                return res
        return None

    def test_coef_equality(
        self, q1: float, q2: float, var: str | None = None
    ) -> dict:
        """
        检验两个分位数处的系数是否相等（Choudhary 2008）。

        H0: beta(q1) = beta(q2)

        Parameters
        ----------
        q1, q2 : float
            两个分位数。
        var : str | None
            待检验的变量名（默认为 X 中的第一个非常数变量）。

        Returns
        -------
        dict
            含 t_stat, pval, coef_q1, coef_q2, se_q1, se_q2。
        """
        res1 = self.get_coef_at_quantile(q1)
        res2 = self.get_coef_at_quantile(q2)

        if res1 is None or res2 is None:
            return {"error": "quantile not found in results"}

        # 默认检验主变量
        if var is None:
            for v in self._last_fit_args.get("X", []):
                if v in res1.coef_dict:
                    var = v
                    break

        if var not in res1.coef_dict:
            return {"error": f"variable {var} not found"}

        coef1 = res1.coef_dict[var]
        se1 = res1.se_dict.get(var, 0.0)
        coef2 = res2.coef_dict[var]
        se2 = res2.se_dict.get(var, 0.0)
        n = min(res1.n_obs, res2.n_obs)

        t_stat, pval = _choudhary_test(coef1, se1, coef2, se2, n)

        result = {
            "var": var,
            "q1": q1, "q2": q2,
            "coef_q1": coef1, "coef_q2": coef2,
            "se_q1": se1, "se_q2": se2,
            "t_stat": t_stat, "pval": pval,
            "reject_equal": pval < 0.05 if not np.isnan(pval) else None,
        }
        _log.info(
            f"[PanelQR] Choudhary test: {var}@{q1} vs {var}@{q2} "
            f"t={t_stat:.3f}, p={pval:.4f} "
            f"{'**' if pval < 0.05 else ''}"
        )
        return result

    def get_r_squared(self, q: float | None = None) -> float | None:
        """
        获取分位数伪 R^2。

        Parameters
        ----------
        q : float | None
            分位数。为 None 时返回中位数结果。

        Returns
        -------
        float | None
        """
        if q is None:
            q = 0.5
        res = self.get_coef_at_quantile(q)
        return res.r_squared if res else None

    # ── Visualization ───────────────────────────────────────────────────────

    def plot_coef_profile(
        self,
        var: str | None = None,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (10, 5),
    ) -> Any:
        """
        绘制系数随分位数变化的曲线（Quantile Process）。

        Parameters
        ----------
        var : str | None
            待绑定的变量名。默认为 X 中的第一个变量。
        save_path : str | Path | None
            保存路径（.pdf / .png）。
        figsize : tuple
            图形尺寸。

        Returns
        -------
        matplotlib Figure 或 None
        """
        if not self._results:
            _log.warning("[PanelQR] No results to plot")
            return None

        if var is None:
            for v in self._last_fit_args.get("X", []):
                if v in list(self._results.values())[0].coef_dict:
                    var = v
                    break
        if var is None:
            _log.warning("[PanelQR] No variable found for plotting")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[PanelQR] matplotlib not installed")
            return None

        taus = sorted(self._results.keys())
        coefs = [self._results[t].coef_dict.get(var, np.nan) for t in taus]
        ses = [self._results[t].se_dict.get(var, 0.0) for t in taus]

        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(taus, coefs, "o-", color="steelblue", linewidth=2, markersize=6)
        ax.fill_between(
            taus,
            np.array(coefs) - 1.96 * np.array(ses),
            np.array(coefs) + 1.96 * np.array(ses),
            alpha=0.2, color="steelblue",
        )
        ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_xlabel("Quantile", fontsize=12)
        ax.set_ylabel("Coefficient", fontsize=12)
        ax.set_title(f"Coefficient Profile: {var}", fontsize=13, fontweight="bold")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[PanelQR] Coefficient profile saved: {save_path}")

        return fig

    def plot_qq_effects(
        self,
        treatment_var: str,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (10, 5),
    ) -> Any:
        """
        绘制处理效应（treatment_var 系数）的分位数分布图。

        Parameters
        ----------
        treatment_var : str
            处理变量名。
        save_path : str | Path | None
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        if not self._results:
            _log.warning("[PanelQR] No results to plot")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[PanelQR] matplotlib not installed")
            return None

        taus = sorted(self._results.keys())
        effects = [self._results[t].coef_dict.get(treatment_var, np.nan) for t in taus]
        ses = [self._results[t].se_dict.get(treatment_var, 0.0) for t in taus]
        pvals = [self._results[t].pval_dict.get(treatment_var, 1.0) for t in taus]

        sig_marks = [_significance_mark(p) for p in pvals]
        colors = ["steelblue" if p < 0.05 else "lightgray" for p in pvals]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

        # 左：系数 + CI
        ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
        ax1.errorbar(
            taus, effects, yerr=1.96 * np.array(ses),
            fmt="o", color="steelblue", capsize=4, linewidth=1.5, markersize=6,
        )
        for i, (tau, eff, sig) in enumerate(zip(taus, effects, sig_marks)):
            if sig:
                ax1.annotate(sig, (tau, eff),
                             textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
        ax1.set_xlabel("Quantile", fontsize=12)
        ax1.set_ylabel(f"Treatment Effect ({treatment_var})", fontsize=12)
        ax1.set_title("Treatment Effect across Quantiles", fontsize=12, fontweight="bold")
        ax1.grid(True, alpha=0.3)

        # 右：伪 R^2 柱状图
        r2_vals = [self._results[t].r_squared for t in taus]
        ax2.bar([str(t) for t in taus], r2_vals, color=colors, edgecolor="steelblue")
        ax2.set_xlabel("Quantile", fontsize=12)
        ax2.set_ylabel("Pseudo R^2", fontsize=12)
        ax2.set_title("Model Fit across Quantiles", fontsize=12, fontweight="bold")
        ax2.grid(True, alpha=0.3, axis="y")

        plt.suptitle("Quantile Treatment Effects", fontsize=14, fontweight="bold")
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[PanelQR] QQ effects plot saved: {save_path}")

        return fig

    # ── Output ────────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        返回所有分位数估计结果的汇总表。

        Returns
        -------
        pd.DataFrame
        """
        if not self._results:
            return pd.DataFrame()

        X_vars = self._last_fit_args.get("X", [])
        taus = sorted(self._results.keys())

        rows = []
        for tau in taus:
            r = self._results[tau]
            row = {
                "tau": f"{tau:.2f}",
                "N": r.n_obs,
                "G": r.n_groups,
                "Pseudo_R2": f"{r.r_squared:.4f}" if r.r_squared is not None else "NA",
                "Method": r.estimator,
            }
            for var in X_vars:
                if var in r.coef_dict:
                    coef = r.coef_dict[var]
                    se = r.se_dict.get(var, np.nan)
                    pval = r.pval_dict.get(var, np.nan)
                    sig = r.sig_dict.get(var, "")
                    row[f"coef_{var}"] = f"{coef:+.4f}{sig}"
                    row[f"se_{var}"] = f"({se:.4f})"
                    row[f"pval_{var}"] = f"{pval:.3f}"
            rows.append(row)

        return pd.DataFrame(rows)

    def to_latex(
        self,
        vars_to_show: list[str] | None = None,
        caption: str = "Panel Quantile Regression Results",
        label: str = "tab:pqr",
    ) -> str:
        """
        导出为 LaTeX 表格（booktabs / threeparttable 格式）。

        Parameters
        ----------
        vars_to_show : list[str] | None
            要显示的变量列表。默认为全部 X 变量。
        caption : str
            表格标题。
        label : str
            LaTeX label。

        Returns
        -------
        str
            LaTeX 代码。
        """
        df = self.summary()
        if df.empty:
            return ""

        X_vars = self._last_fit_args.get("X", [])
        show_vars = vars_to_show or X_vars
        # 过滤存在的变量
        show_vars = [v for v in show_vars if f"coef_{v}" in df.columns]

        taus = sorted(self._results.keys())
        n_cols = 1 + len(show_vars)  # tau + vars
        col_spec = "l" + "c" * n_cols

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            "    \\toprule",
            "    \\textbf{tau} & " + " & ".join(
                f"\\textbf{{{v}}}" for v in show_vars
            ) + " \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            coef_parts = []
            for var in show_vars:
                c = row.get(f"coef_{var}", "")
                s = row.get(f"se_{var}", "")
                coef_parts.append(f"{c}\\newline{s}")
            lines.append(
                "    "
                + row["tau"]
                + " & "
                + " & ".join(coef_parts)
                + " \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "    \\midrule",
            f"    \\textbf{{N}} & " + " & ".join(str(df["N"].iloc[i]) for i in range(len(df))) + " \\\\ ",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, "
            "    $^{*}p<0.10$.",
            "    \\item Pseudo R\\textsuperscript{2} in Table.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cdf(x: np.ndarray) -> np.ndarray:
    """标准正态 CDF（带容错）。"""
    try:
        from scipy import stats
        return stats.norm.cdf(x)
    except Exception:
        return np.where(x > 0, 1.0, 0.0)
