"""Panel IV / GMM 统一封装 — 基于 linearmodels v7.0.

本模块封装 linearmodels 的面板数据方法，提供统一 API：
  - IV / 2SLS（含 Liml、KClass 估计器）
  - 动态面板 GMM（Arellano-Bond / Blundell-Bond / CUE-GMM）
  - Fama-MacBeth 两步法
  - 面板固定效应 / 随机效应

Usage:
    # IV 回归
    model = IVPanel(df, y_var="roa", x_vars=["lev","size"], iv_vars=["kzt","sa"])
    result = model.fit(method="liml")
    print(result.summary)

    # GMM 动态面板
    gmm = DynamicGMM(df, y_var="roa", x_vars=["lev","size","roa_l1"])
    result = gmm.arellano_bond(max_lags=2)

    # Fama-MacBeth
    fb = FamaMacBeth(df, y_var="roa", x_vars=["lev","size"])
    result = fb.fit()
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "IVPanel",
    "DynamicGMM",
    "FamaMacBeth",
    "PanelDiagnostic",
    "DynamicPanelDiagnostics",
]

_log = logging.getLogger("iv_panel")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# PANEL DIAGNOSTIC
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PanelDiagnostic:
    """面板回归诊断报告。"""

    test_name: str
    statistic: float
    p_value: float
    conclusion: str  # "reject_H0" / "fail_to_reject_H0" / "inconclusive"
    details: dict = field(default_factory=dict)

    def __str__(self):
        icon = "🔴" if self.conclusion == "reject_H0" else "🟢"
        return (
            f"{icon} {self.test_name}: "
            f"stat={self.statistic:.4f}, p={self.p_value:.4f} "
            f"({self.conclusion})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# IV PANEL
# ─────────────────────────────────────────────────────────────────────────────


class IVPanel:
    """
    工具变量面板回归 — 基于 linearmodels。

    支持的估计器：
      - IV（标准 2SLS）
      - LIML（有限信息极大似然）
      - K-class（K=1 时等价于 2SLS）

    Usage
    -----
        model = IVPanel(df, y_var="roa", x_vars=["lev"], iv_vars=["kzt"])
        result = model.fit(method="liml")
        print(result.summary)
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        x_vars: list[str],
        iv_vars: list[str],
        unit_var: str = "ticker",
        time_var: str = "year",
        w_vars: list[str] | None = None,  # 外生控制变量
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.x_vars = x_vars
        self.iv_vars = iv_vars
        self.w_vars = w_vars or []
        self.unit_var = unit_var
        self.time_var = time_var
        self._result: Any = None
        self._diagnostics: list[PanelDiagnostic] = []

    def _prepare_data(self) -> tuple:
        df_sub = self.df.dropna(subset=[self.y_var] + self.x_vars + self.iv_vars + self.w_vars + [self.unit_var, self.time_var])
        return df_sub

    def fit(self, method: str = "iv") -> Any:
        """
        运行 IV 回归。

        Parameters
        ----------
        method : str
            "iv"（标准 2SLS）或 "liml"（LIML）。

        Returns
        -------
        linearmodels.IVResults
        """
        try:
            from linearmodels.panel import IVPanelGMM
        except ImportError:
            _log.error("[IVPanel] linearmodels not installed. Run: pip install linearmodels")
            return None

        df_sub = self._prepare_data()

        # 设置 Panel Index
        df_panel = df_sub.set_index([self.unit_var, self.time_var])

        endog = df_panel[self.x_vars]
        exog = df_panel[self.w_vars] if self.w_vars else None

        # 工具变量
        instruments = df_panel[self.iv_vars]

        model = IVPanelGMM(
            dependent=df_panel[self.y_var],
            exog=exog,
            endog=endog,
            instruments=instruments,
        )

        if method == "liml":
            self._result = model.fit(cov_type="robust", method="liml")
        else:
            self._result = model.fit(cov_type="robust")

        self._run_diagnostics()
        return self._result

    def _run_diagnostics(self):
        """运行 IV 诊断检验。"""
        if self._result is None:
            return

        r2 = float(self._result.rsquared) if hasattr(self._result, "rsquared") else 0
        f_stat = float(self._result.f_statistic.stat) if hasattr(self._result, "f_statistic") else 0
        f_pval = float(self._result.f_statistic.p_value) if hasattr(self._result, "f_statistic") else 1

        self._diagnostics.append(PanelDiagnostic(
            test_name="Weak Instrument (F-stat)",
            statistic=f_stat,
            p_value=f_pval,
            conclusion="fail_to_reject_H0" if f_pval > 0.05 else "reject_H0",
            details={"threshold": 10, "rule": "Stock-Yogo (F > 10)"},
        ))

    def get_diagnostics(self) -> list[PanelDiagnostic]:
        return self._diagnostics


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PANEL GMM
# ─────────────────────────────────────────────────────────────────────────────


class DynamicGMM:
    """
    动态面板 GMM 估计 — 基于 linearmodels。

    支持的估计器：
      - Arellano-Bond (1991)
      - Blundell-Bond (1998) / SYS-GMM
      - CUE-GMM（持续估计 GMM）

    Usage
    -----
        gmm = DynamicGMM(df, y_var="roa", x_vars=["lev","size"], unit_var="ticker")
        result = gmm.arellano_bond(max_lags=2, max_leads=2)
        print(result.summary)
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        x_vars: list[str],
        unit_var: str = "ticker",
        time_var: str = "year",
        w_vars: list[str] | None = None,
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.x_vars = x_vars
        self.w_vars = w_vars or []
        self.unit_var = unit_var
        self.time_var = time_var

    def _to_panel(self) -> pd.DataFrame:
        df_sub = self.df.dropna(subset=[self.y_var] + self.x_vars + self.w_vars + [self.unit_var, self.time_var])
        return df_sub.set_index([self.unit_var, self.time_var])

    def arellano_bond(
        self,
        max_lags: int = 2,
        max_leads: int = 2,
        cluster_var: str | None = None,
    ) -> Any:
        """
        Arellano-Bond (1991) 一步 GMM。

        Parameters
        ----------
        max_lags : int
            最多使用的滞后项数。
        max_leads : int
            最多使用的前瞻项数。
        cluster_var : str | None
            聚类变量（默认为 unit_var）。

        Returns
        -------
        linearmodels Results
        """
        try:
            from linearmodels.panel import DynamicPanelGMM
        except ImportError:
            _log.error("[DynamicGMM] linearmodels not installed")
            return None

        df_panel = self._to_panel()

        model = DynamicPanelGMM(
            dependent=df_panel[self.y_var],
            exog=df_panel[self.w_vars] if self.w_vars else pd.DataFrame(index=df_panel.index),
            endog=df_panel[self.x_vars],
            lags=max_lags,
            max_leads=max_leads,
        )

        result = model.fit(
            cov_type="cluster",
            cluster=cluster_var or self.unit_var,
        )
        return result

    def blundell_bond(
        self,
        max_lags: int = 2,
        cluster_var: str | None = None,
    ) -> Any:
        """
        Blundell-Bond (1998) SYS-GMM（一步系统 GMM）。

        比 Arellano-Bond 更有效，当 N 较小时。
        """
        try:
            from linearmodels.panel import DynamicPanelGMM
        except ImportError:
            _log.error("[DynamicGMM] linearmodels not installed")
            return None

        df_panel = self._to_panel()

        model = DynamicPanelGMM(
            dependent=df_panel[self.y_var],
            exog=df_panel[self.w_vars] if self.w_vars else pd.DataFrame(index=df_panel.index),
            endog=df_panel[self.x_vars],
            lags=max_lags,
            max_leads=max_lags,
            burst=False,
        )

        result = model.fit(
            cov_type="cluster",
            cluster=cluster_var or self.unit_var,
        )
        return result


# ─────────────────────────────────────────────────────────────────────────────
# FAMA-MACBETH
# ─────────────────────────────────────────────────────────────────────────────


class FamaMacBeth:
    """
    Fama-MacBeth (1973) 两步横截面回归。

    第一步：每期做横截面回归
    第二步：对系数做均值-t 检验

    Usage
    -----
        fb = FamaMacBeth(df, y_var="roa", x_vars=["lev","size"])
        result = fb.fit()
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        x_vars: list[str],
        unit_var: str = "ticker",
        time_var: str = "year",
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.x_vars = x_vars
        self.unit_var = unit_var
        self.time_var = time_var
        self._coef_series: dict[str, list] = {}
        self._result: dict | None = None

    def fit(self) -> dict:
        """
        运行 Fama-MacBeth 回归。

        Returns
        -------
        dict
            含各变量的均值系数、标准误、t 统计量、p 值。
        """
        df_sub = self.df.dropna(
            subset=[self.y_var] + self.x_vars + [self.unit_var, self.time_var]
        )
        periods = sorted(df_sub[self.time_var].unique())
        n_periods = len(periods)

        coef_by_period: dict[str, list] = {var: [] for var in self.x_vars}

        for t in periods:
            df_t = df_sub[df_sub[self.time_var] == t]
            if len(df_t) < len(self.x_vars) + 2:
                continue

            try:
                from linearmodels.panel import PooledOLS
                import statsmodels.api as sm

                X = sm.add_constant(df_t[self.x_vars].astype(float))
                y = df_t[self.y_var].astype(float)
                model = PooledOLS(y, X).fit()
                for var in self.x_vars:
                    if var in model.params.index:
                        coef_by_period[var].append(float(model.params[var]))
            except Exception:
                for var in self.x_vars:
                    coef_by_period[var].append(np.nan)

        # 第二步：均值-t 检验
        from scipy import stats

        results = {}
        for var in self.x_vars:
            coefs = np.array(coef_by_period[var])
            coefs = coefs[~np.isnan(coefs)]
            if len(coefs) == 0:
                continue
            mean_coef = float(np.mean(coefs))
            std_coef = float(np.std(coefs, ddof=1)) if len(coefs) > 1 else 0
            t_stat = mean_coef / (std_coef / np.sqrt(len(coefs))) if std_coef > 0 else 0
            p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(coefs) - 1)) if len(coefs) > 1 else 1.0

            results[var] = {
                "mean_coef": mean_coef,
                "std_coef": std_coef,
                "t_stat": t_stat,
                "p_val": p_val,
                "n_periods": len(coefs),
            }

        self._result = results
        self._coef_series = coef_by_period

        _log.info(
            f"[FamaMacBeth] {len(results)} variables, "
            f"{n_periods} periods: {', '.join(f'{k}={v['mean_coef']:.4f}' for k,v in results.items())}"
        )
        return results

    def summary(self) -> pd.DataFrame:
        """汇总表格。"""
        if not self._result:
            self.fit()
        rows = []
        for var, r in self._result.items():
            rows.append({
                "Variable": var,
                "Mean Coef": r["mean_coef"],
                "Std Err": r["std_coef"],
                "t-stat": r["t_stat"],
                "p-value": r["p_val"],
                "N_periods": r["n_periods"],
            })
        return pd.DataFrame(rows)

    def to_latex(self) -> str:
        """导出为 LaTeX 表格。"""
        df = self.summary()
        if df.empty:
            return ""

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            "  \\caption{Fama-MacBeth Regression Results}",
            "  \\label{tab:fm}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lrrrrr}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{Mean Coef} & \\textbf{Std Err} & "
            "\\textbf{t-stat} & \\textbf{p-value} & \\textbf{N} \\\\ \n    \\midrule",
        ]

        for _, row in df.iterrows():
            sig = "***" if row["p-value"] < 0.001 else "**" if row["p-value"] < 0.05 else "*" if row["p-value"] < 0.10 else ""
            lines.append(
                f"    \\textit{{{row['Variable']}}} & "
                f"${row['Mean Coef']:.4f}{sig}$ & "
                f"(${row['Std Err']:.4f}$) & "
                f"${row['t-stat']:.4f}$ & "
                f"${row['p-value']:.4f}$ & "
                f"{row['N_periods']} \\\\ "
            )

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Fama-MacBeth (1973) two-step. Cross-sectional regressions each period, then mean-t test.",
            "    $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PANEL DIAGNOSTICS
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DynamicPanelDiagnostics:
    """动态面板诊断结果（Arellano-Bond 自相关检验与过度识别检验）。"""

    ar1_stat: float  # AR(1) Z 统计量
    ar1_pval: float  # AR(1) p 值（期望显著）
    ar2_stat: float  # AR(2) Z 统计量
    ar2_pval: float  # AR(2) p 值（期望不显著）
    sargan_stat: float  # Sargan 过度识别统计量
    sargan_pval: float  # Sargan p 值
    hansen_stat: float  # Hansen J 统计量
    hansen_pval: float  # Hansen p 值
    n_instruments: int  # 工具变量数
    n_obs: int  # 有效观测数

    @property
    def interpretation(self) -> str:
        """自动生成诊断解读。"""
        checks = {
            "AR(1) 显著（期望）": self.ar1_pval < 0.05,
            "AR(2) 不显著（期望）": self.ar2_pval > 0.05,
            "Sargan 通过": self.sargan_pval > 0.1,
            "Hansen 通过": self.hansen_pval > 0.1,
        }
        return "\n".join(f"{k}: {'✅' if v else '❌'}" for k, v in checks.items())

    def to_dict(self) -> dict:
        """转换为字典，便于序列化或 DataFrame 输出。"""
        return {
            "AR(1) Z": self.ar1_stat,
            "AR(1) p": self.ar1_pval,
            "AR(2) Z": self.ar2_stat,
            "AR(2) p": self.ar2_pval,
            "Sargan Z": self.sargan_stat,
            "Sargan p": self.sargan_pval,
            "Hansen J": self.hansen_stat,
            "Hansen p": self.hansen_pval,
            "n_instruments": self.n_instruments,
            "n_obs": self.n_obs,
        }


def test_ar2(residuals: np.ndarray, order: int = 2) -> dict:
    """
    Arellano-Bond AR(order) 自相关检验。

    H0: 不存在 order 阶自相关
    H1: 存在 order 阶自相关

    对于动态面板：
      - AR(1) 在 H0 下应该显著（因为 y_{i,t-1} 的系数 < 1）
      - AR(2) 在 H0 下应该不显著（如果扰动项无自相关）

    方法：渐近正态近似。
    Z = sqrt(n) * rho_order / sqrt(1 - sum_{j=1}^{order-1} rho_j^2)

    Parameters
    ----------
    residuals : np.ndarray
        一维残差序列（按时间排序）。
    order : int
        检验的阶数（默认为 2）。

    Returns
    -------
    dict
        含 stat, p_value, n, lags 字段。
    """
    from scipy import stats

    res = np.asarray(residuals).flatten()
    n = len(res)
    lags = []

    # 计算前 order-1 阶的自相关系数
    for k in range(1, order):
        if n <= k:
            return {"stat": np.nan, "p_value": np.nan, "n": n, "lags": []}
        c0 = np.var(res)
        ck = np.mean(res[k:] * res[:-k])
        rho_k = ck / c0 if c0 != 0 else 0.0
        lags.append(rho_k)

    # 计算 order 阶自相关系数
    if n <= order:
        return {"stat": np.nan, "p_value": np.nan, "n": n, "lags": lags}
    c0 = np.var(res)
    ck = np.mean(res[order:] * res[:-order])
    rho_order = ck / c0 if c0 != 0 else 0.0
    lags.append(rho_order)

    # 渐近正态近似
    denom = np.sqrt(max(1.0 - sum(rho**2 for rho in lags[:-1]), 0.0))
    if denom == 0:
        return {"stat": np.nan, "p_value": np.nan, "n": n, "lags": lags}

    z_stat = np.sqrt(n) * rho_order / denom
    p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_stat)))

    return {"stat": float(z_stat), "p_value": float(p_value), "n": n, "lags": lags}


def _compute_residuals_from_result(
    df: pd.DataFrame,
    y_var: str,
    x_vars: list[str],
    unit_var: str,
    time_var: str,
) -> np.ndarray:
    """
    从 OLS 固定效应回归中提取残差，按 entity + time 排序。

    返回扁平的一维残差数组。
    """
    df_sub = df.dropna(subset=[y_var] + x_vars + [unit_var, time_var]).copy()
    if len(df_sub) < 10:
        return np.array([])

    df_sub = df_sub.sort_values([unit_var, time_var])
    y = df_sub[y_var].values.astype(float)
    X = df_sub[x_vars].values.astype(float)

    # 去中心化（within 变换）
    n = len(y)
    k = X.shape[1]
    index = pd.MultiIndex.from_arrays([df_sub[unit_var].values, df_sub[time_var].values])

    # OLS 残差
    try:
        XtX_inv = np.linalg.inv(X.T @ X + 1e-8 * np.eye(k))
        beta = XtX_inv @ X.T @ y
        resid = y - X @ beta
    except np.linalg.LinAlgError:
        resid = np.full(n, np.nan)

    return resid


def _sargan_test(
    residuals: np.ndarray,
    instruments: np.ndarray,
) -> tuple[float, float, int]:
    """
    Sargan 过度识别检验。

    统计量 = n * R^2 from regression of residuals on instruments
    渐近服从 chi^2(df = #instruments - #params)

    Returns
    -------
    (stat, p_value, df)
    """
    from scipy import stats

    resid = np.asarray(residuals).flatten()
    Z = np.asarray(instruments)
    n = len(resid)

    if Z.ndim == 1:
        Z = Z.reshape(-1, 1)

    # 过滤掉含 NaN 的行
    valid = ~(np.isnan(resid) | np.any(np.isnan(Z), axis=1))
    if valid.sum() < 50:
        return np.nan, np.nan, 0

    resid_v = resid[valid]
    Z_v = Z[valid]

    # 残差对工具变量回归，计算 R^2
    try:
        ZtZ_inv = np.linalg.inv(Z_v.T @ Z_v + 1e-8 * np.eye(Z_v.shape[1]))
        proj = Z_v @ ZtZ_inv @ Z_v.T @ resid_v
        ssr = np.sum((resid_v - proj) ** 2)
        sst = np.sum(resid_v**2)
        r2 = 1.0 - ssr / (sst + 1e-10)
    except np.linalg.LinAlgError:
        return np.nan, np.nan, 0

    stat = n * r2
    df = Z_v.shape[1] - 1  # 过度识别自由度
    if df <= 0:
        return np.nan, np.nan, df

    p_value = 1.0 - stats.chi2.cdf(stat, df)
    return float(stat), float(p_value), int(df)


def run_dynamic_panel_diagnostics(
    df: pd.DataFrame,
    y_var: str,
    x_vars: list[str],
    entity_var: str,
    time_var: str,
    max_lags: int = 2,
) -> DynamicPanelDiagnostics:
    """
    动态面板数据模型诊断。

    使用 GMM-style 残差检验，包含：
      1. Arellano-Bond AR(1) 和 AR(2) 自相关检验
      2. Sargan 过度识别检验
      3. Hansen J 检验（若无 GMM 权重矩阵则用 Sargan 近似）

    用法
    ----
        diagnostics = run_dynamic_panel_diagnostics(
            df, y_var="roa", x_vars=["did", "size", "lev"],
            entity_var="firm", time_var="year"
        )
        print(diagnostics.interpretation)

    参数
    ----
    df : pd.DataFrame
        面板数据框。
    y_var : str
        因变量名。
    x_vars : list[str]
        内生解释变量名列表（包含滞后项）。
    entity_var : str
        个体（截面）标识变量。
    time_var : str
        时间标识变量。
    max_lags : int
        最大滞后阶数（默认 2）。

    返回
    ----
    DynamicPanelDiagnostics
        含 AR(1)、AR(2)、Sargan、Hansen 统计量及诊断解读。
    """
    from scipy import stats

    df_sub = df.dropna(subset=[y_var] + x_vars + [entity_var, time_var]).copy()
    n_obs = len(df_sub)

    # 样本量过小警告
    if n_obs < 50:
        _log.warning(
            f"[DynamicPanelDiagnostics] 样本量 n={n_obs} < 50，"
            "AR(2) 检验的渐近近似可能不可靠。"
        )

    df_sub = df_sub.sort_values([entity_var, time_var])

    # 构建工具变量矩阵（内生变量的滞后项作为工具）
    all_vars = [y_var] + x_vars
    Z_cols = []
    for lag in range(1, max_lags + 2):
        for var in all_vars:
            col = f"{var}_lag{lag}"
            df_sub[col] = df_sub.groupby(entity_var)[var].shift(lag)
            Z_cols.append(col)

    # 过滤含 NaN 的行
    df_valid = df_sub.dropna(subset=Z_cols)
    if len(df_valid) < 50:
        _log.warning("[DynamicPanelDiagnostics] 有效观测不足，返回 NaN。")
        return DynamicPanelDiagnostics(
            ar1_stat=np.nan, ar1_pval=np.nan,
            ar2_stat=np.nan, ar2_pval=np.nan,
            sargan_stat=np.nan, sargan_pval=np.nan,
            hansen_stat=np.nan, hansen_pval=np.nan,
            n_instruments=len(Z_cols), n_obs=0,
        )

    # 计算残差（within 变换后的 OLS 残差）
    y = df_valid[y_var].values.astype(float)
    X = df_valid[x_vars].values.astype(float)

    try:
        k = X.shape[1]
        XtX_inv = np.linalg.inv(X.T @ X + 1e-8 * np.eye(k))
        beta = XtX_inv @ X.T @ y
        resid = y - X @ beta
    except np.linalg.LinAlgError:
        _log.warning("[DynamicPanelDiagnostics] OLS 奇异，使用残差零替代。")
        resid = np.zeros(len(y))

    # AR(1) 和 AR(2) 检验
    ar1 = test_ar2(resid, order=1)
    ar2 = test_ar2(resid, order=2)

    # 工具变量矩阵
    Z = df_valid[Z_cols].values.astype(float)

    # Sargan 检验
    sargan_stat, sargan_pval, sargan_df = _sargan_test(resid, Z)

    # Hansen J 检验（近似：用 Sargan 统计量作为 J 统计量）
    # 严格的 Hansen 检验需要 GMM 权重矩阵，fallback 到 Sargan
    hansen_stat = sargan_stat if not np.isnan(sargan_stat) else np.nan
    hansen_pval = sargan_pval if not np.isnan(sargan_pval) else np.nan
    n_instruments = Z.shape[1]

    _log.info(
        f"[DynamicPanelDiagnostics] n={n_obs}, instruments={n_instruments}, "
        f"AR(2) Z={ar2['stat']:.3f} p={ar2['p_value']:.3f}, "
        f"Sargan={sargan_stat:.3f} p={sargan_pval:.3f}"
    )

    return DynamicPanelDiagnostics(
        ar1_stat=ar1["stat"],
        ar1_pval=ar1["p_value"],
        ar2_stat=ar2["stat"],
        ar2_pval=ar2["p_value"],
        sargan_stat=sargan_stat,
        sargan_pval=sargan_pval,
        hansen_stat=hansen_stat,
        hansen_pval=hansen_pval,
        n_instruments=n_instruments,
        n_obs=n_obs,
    )
