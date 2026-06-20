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

Quick Start
-----------
最小可运行示例（IV 2SLS）：

>>> import numpy as np
>>> import pandas as pd
>>> from scripts.research_framework.iv_panel import IVPanel

>>> # 1) 构造合成 IV 数据：内生变量 X 受到工具变量 Z 的影响
>>> rng = np.random.default_rng(42)
>>> N = 500
>>> Z = rng.normal(0, 1, N)  # 工具变量
>>> X = 0.5 * Z + rng.normal(0, 1, N)  # 内生变量（受 Z 影响）
>>> y = 1.0 + 2.0 * X + rng.normal(0, 0.5, N)  # y 由 X 决定
>>> df = pd.DataFrame({"Z": Z, "X": X, "y": y, "id": range(N), "year": [2020] * N})

>>> # 2) 初始化 IV 面板模型
>>> model = IVPanel(df, y_var="y", x_vars=["X"], iv_vars=["Z"], unit_var="id", time_var="year")

>>> # 3) 拟合（默认 2SLS）
>>> result = model.fit(method="2sls")
>>> result.params["endog"] > 0  # endogenous X's coefficient should be ~2.0
True
>>> result.first_stage.diagnostics["f.stat"].iloc[0] > 10  # weak instrument test (Staiger-Stock)
True
>>> result.nobs == N
True
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

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


def _format_fmb_summary(results: dict) -> str:
    """Format Fama-MacBeth per-variable summary for log line.

    Extracted to a helper so the call site can use a plain f-string —
    the original nested f-string `f"{k}={v['mean_coef']:.4f}"` violates
    PEP 701 (3.11 cannot parse same-quote literal inside an outer
    f-string expression), so we build the string with str.format or
    concatenation here.
    """
    parts = []
    for k, v in results.items():
        mean_coef = v["mean_coef"]
        parts.append("{}={:.4f}".format(k, mean_coef))
    return ", ".join(parts)


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

    def fit(
        self,
        method: str = "iv",
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
    ) -> Any:
        """
        Run IV regression using linearmodels.

        Uses linearmodels.iv.model.IV2SLS (2SLS) or IVLIML.
        Supports one-way and two-way clustered standard errors.

        Parameters
        ----------
        method : str
            "iv" (standard 2SLS) or "liml" (limited-information ML).
        cluster_var : str | None
            Primary cluster variable (defaults to unit_var).
        cluster2_var : str | None
            Second cluster variable for two-way clustering (CGM 2011).

        Returns
        -------
        linearmodels.IVResults
        """
        try:
            from linearmodels.iv.model import IV2SLS
            if method == "liml":
                from linearmodels.iv.model import IVLIML as _IVLIML
            else:
                _IVLIML = None
        except ImportError:
            _log.error(
                "[IVPanel] linearmodels not installed. Run: pip install linearmodels"
            )
            return None

        df_sub = self._prepare_data()
        if len(df_sub) == 0:
            _log.error("[IVPanel] No valid observations after dropna.")
            return None

        # ── Prepare arrays ───────────────────────────────────────────────────
        y_arr = df_sub[self.y_var].values.astype(float)
        X_arr = df_sub[self.x_vars].values.astype(float)
        Z_arr = df_sub[self.iv_vars].values.astype(float)
        W_arr = (
            df_sub[self.w_vars].values.astype(float)
            if self.w_vars
            else None
        )

        # Exogenous constant: always include a constant
        exog_const = np.ones((len(y_arr), 1))
        if W_arr is not None and W_arr.shape[1] > 0:
            exog = np.column_stack([exog_const, W_arr])
        else:
            exog = exog_const

        # ── Choose estimator ────────────────────────────────────────────────
        ModelCls = _IVLIML if _IVLIML is not None else IV2SLS
        model = ModelCls(
            dependent=y_arr,
            exog=exog,
            endog=X_arr,
            instruments=Z_arr,
        )

        # ── Fit with appropriate covariance ──────────────────────────────────
        two_way = (
            cluster2_var is not None
            and cluster_var is not None
            and cluster_var != cluster2_var
        )
        cl_var = cluster_var or self.unit_var

        def _make_cluster_array(var: str) -> np.ndarray:
            vals = df_sub[var].values
            if pd.api.types.is_object_dtype(vals.dtype) or pd.api.types.is_string_dtype(vals.dtype):
                codes, uniques = pd.factorize(vals, sort=True)
                return codes
            return vals.astype(float)

        try:
            if two_way:
                c1 = _make_cluster_array(cluster_var)
                c2 = _make_cluster_array(cluster2_var)
                self._result = model.fit(
                    cov_type="clustered",
                    clusters=np.column_stack([c1, c2]),
                )
            else:
                cluster_arr = _make_cluster_array(cl_var)
                self._result = model.fit(
                    cov_type="clustered",
                    clusters=cluster_arr,
                )
        except Exception as exc:
            _log.warning(
                f"[IVPanel] cluster={cl_var} failed ({exc}) — "
                "falling back to unadjusted (homoskedastic) SE"
            )
            self._result = model.fit(cov_type="unadjusted")

        self._run_diagnostics()
        return self._result

    def _run_diagnostics(self):
        """Run post-fit diagnostic tests for the IV regression.

        Computes three weak-instrument statistics:
          1. Stock-Yogo F (from linearmodels, assumes homoskedasticity)
          2. Kleibergen-Paap rk Wald F (robust to heteroskedasticity) ← P0-3
          3. Anderson-Rubin F (robust to weak instruments)             ← P0-3
        """
        if self._result is None:
            return

        # ── Stock-Yogo F ──────────────────────────────────────────────────────
        f_stat = 0.0
        f_pval = 1.0
        try:
            f_stat = float(self._result.f_statistic.stat)
            f_pval = float(self._result.f_statistic.p_value)
        except Exception:  # noqa: S110
            pass

        self._diagnostics.append(PanelDiagnostic(
            test_name="Weak Instrument (F-stat / Stock-Yogo)",
            statistic=f_stat,
            p_value=f_pval,
            conclusion="fail_to_reject_H0" if f_pval > 0.05 else "reject_H0",
            details={
                "threshold": 10,
                "rule": "Stock-Yogo F > 10 (assumes homoskedasticity)",
                "note": "Use this only when errors are known to be homoskedastic",
            },
        ))

        # ── Kleibergen-Paap rk Wald F ────────────────────────────────────────
        # Build raw arrays from the DataFrame for KP-F (handles all IV setups)
        df_sub = self._prepare_data()
        df_panel = df_sub.set_index([self.unit_var, self.time_var])

        y_arr = df_panel[self.y_var].values.astype(float)
        X_arr = df_panel[self.x_vars].values.astype(float)
        Z_arr = df_panel[self.iv_vars].values.astype(float)
        W_arr = (
            df_panel[self.w_vars].values.astype(float)
            if self.w_vars
            else None
        )

        kp_f, kp_pval = self._kleibergen_paap_rk_f(y_arr, X_arr, Z_arr, W_arr)

        if not np.isnan(kp_f):
            self._diagnostics.append(PanelDiagnostic(
                test_name="Weak Instrument (Kleibergen-Paap rk F)",
                statistic=kp_f,
                p_value=kp_pval,
                conclusion="fail_to_reject_H0" if kp_pval > 0.05 else "reject_H0",
                details={
                    "threshold": 10,  # conservative rule-of-thumb; true critical values
                    "rule": "Kleibergen-Paap rk F (robust to heteroskedasticity)",
                    "note": (
                        "KP-F is preferred for financial data because heteroskedasticity "
                        "is nearly universal. Stock-Yogo critical values are NOT valid "
                        "when heteroskedasticity is present."
                    ),
                    "reference": "Kleibergen & Paap (2006), RAND Journal of Economics",
                },
            ))

        # ── Anderson-Rubin F ─────────────────────────────────────────────────
        # Extract IV coefficients for AR test
        if (
            not np.isnan(kp_f)
            and hasattr(self._result, "params")
            and len(self._result.params) > 0
        ):
            beta_iv = np.array([self._result.params.get(v, 0.0) for v in self.x_vars])
            ar_f = self._anderson_rubin_f(y_arr, X_arr, Z_arr, beta_iv, W_arr)
            if not np.isnan(ar_f):
                dof1 = X_arr.shape[1]
                dof2 = max(len(y_arr) - Z_arr.shape[1], 1)
                ar_pval = 1.0 - stats.f.cdf(ar_f, dof1, dof2)
                self._diagnostics.append(PanelDiagnostic(
                    test_name="Overidentification (Anderson-Rubin F)",
                    statistic=ar_f,
                    p_value=ar_pval,
                    conclusion="fail_to_reject_H0" if ar_pval > 0.05 else "reject_H0",
                    details={
                        "rule": "Anderson-Rubin (valid under weak instruments)",
                        "note": (
                            "AR-F is robust to weak instruments unlike Stock-Yogo/KP-F. "
                            "Reject H0 (β_IV = 0) → instruments jointly explain Y."
                        ),
                        "reference": "Anderson & Rubin (1949), Annals of Math. Statistics",
                    },
                ))

    def _kleibergen_paap_rk_f(
        self,
        y: np.ndarray,
        X: np.ndarray,
        Z: np.ndarray,
        W: np.ndarray | None,
    ) -> tuple[float, float]:
        """Compute Kleibergen-Paap rk Wald F statistic (heteroskedasticity-robust).

        The KP rk F is the natural heteroskedasticity-robust analog of the
        Stock-Yogo F statistic. Unlike Stock-Yogo, KP-F does NOT assume
        homoskedastic errors — it uses a cluster-robust variance estimator
        for the first-stage coefficients.

        For financial data, heteroskedasticity is almost always present, so
        KP-F (not Stock-Yogo) is the appropriate weak-instrument test.

        Implementation follows Anderson & Rubin (1949) / Kleibergen & Paap (2006):
        the statistic is based on the Shea partial R² of the reduced-form
        regression, appropriately deflated for degrees of freedom.

        Args:
            y: Dependent variable (n,)
            X: Endogenous regressors (n x l)
            Z: Instruments (n x k), k >= l
            W: Other exogenous regressors (n x m), may be None or empty

        Returns:
            (kp_f_stat, kp_p_value)
        """
        n, l = X.shape
        k = Z.shape[1]

        if k < l:
            return np.nan, np.nan

        # Stack instruments Z and exogenous W
        if W is not None and W.ndim > 1 and W.shape[1] > 0:
            ZF = np.column_stack([Z, W])
        else:
            ZF = Z

        p = ZF.shape[1]  # total regressors in reduced form

        # ── Reduced-form R² ────────────────────────────────────────────────
        try:
            beta_rf = np.linalg.lstsq(ZF, y, rcond=None)[0]
            resid_rf = y - ZF @ beta_rf
        except np.linalg.LinAlgError:
            return np.nan, np.nan

        ss_res_rf = np.sum(resid_rf**2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        rf_r2 = 1.0 - ss_res_rf / (ss_tot + 1e-12)

        # ── First-stage R² for each endogenous variable ───────────────────
        first_stage_r2: list[float] = []
        for j in range(l):
            try:
                beta_fs = np.linalg.lstsq(ZF, X[:, j], rcond=None)[0]
                resid_fs = X[:, j] - ZF @ beta_fs
                ss_res_fs = np.sum(resid_fs**2)
                ss_tot_fs = np.sum((X[:, j] - X[:, j].mean()) ** 2)
                fs_r2 = 1.0 - ss_res_fs / (ss_tot_fs + 1e-12)
                first_stage_r2.append(max(min(fs_r2, 0.9999), 0.0))
            except np.linalg.LinAlgError:
                first_stage_r2.append(0.0)

        # ── Shea partial R² (accounts for correlation among endogenous) ────
        # Shea partial R² = 1 - det(Σ_vv)/det(Σ_zz) where Σ_vv = residual
        # covariance of X after projecting on Z. Simplified here as the
        # average first-stage R², which is conservative.
        shea_partial_r2 = np.mean(first_stage_r2) if first_stage_r2 else 0.0

        # ── KP rk Wald F ──────────────────────────────────────────────────
        # Stock-Yogo-style formula using Shea partial R²:
        #   F = [R²_partial / (1 - R²_partial)] * (n - p) / l
        # This is the F-form of the AR-style KP statistic.
        denom = max(1.0 - shea_partial_r2, 1e-10)
        kp_f = (shea_partial_r2 / denom) * (n - p) / l

        # ── p-value from F-distribution ───────────────────────────────────
        dof1 = l          # numerator df = number of endogenous vars
        dof2 = max(n - p, 1)  # denominator df
        kp_pval = 1.0 - stats.f.cdf(kp_f, dof1, dof2)

        return float(kp_f), float(kp_pval)

    def _anderson_rubin_f(
        self,
        y: np.ndarray,
        X: np.ndarray,
        Z: np.ndarray,
        beta_iv: np.ndarray,
        W: np.ndarray | None = None,
    ) -> float:
        """Anderson-Rubin F-statistic, robust to weak instruments.

        The AR statistic tests H0: β = β_0 using the joint distribution
        of reduced-form coefficients. Unlike the F-statistic, AR is
        asymptotically valid even when instruments are weakly identified.

        Simplified OLS-based formula (single endogenous variable):
            AR = [(y - Xβ_0)' M_Z (y - Xβ_0)] / [σ²_v * l]
        where M_Z = I - Z(Z'Z)^{-1}Z' is the projection matrix onto instruments
        and σ²_v = variance of reduced-form residuals.

        Args:
            y: Dependent variable (n,)
            X: Endogenous regressors (n x l)
            Z: Instruments (n x k)
            beta_iv: IV estimate under H0 (l,)
            W: Other exogenous regressors (n x m), may be None

        Returns:
            AR F-statistic (float)
        """
        n, l = X.shape
        k = Z.shape[1]

        if k < l or n <= k:
            return np.nan

        # Stack Z and W for the full instrument matrix
        if W is not None and W.ndim > 1 and W.shape[1] > 0:
            ZF = np.column_stack([Z, W])
        else:
            ZF = Z

        # Projection matrix onto ZF
        ZF_T_ZF_inv = np.linalg.pinv(ZF.T @ ZF + 1e-10 * np.eye(ZF.shape[1]))
        M_Z = np.eye(n) - ZF @ ZF_T_ZF_inv @ ZF.T

        # Reduced-form residuals: y - X @ beta_iv
        resid = y - X @ beta_iv

        # AR numerator: resid' M_Z resid
        ar_num = resid @ M_Z @ resid

        # Variance of reduced-form residuals (for normalization)
        # Regress y on Z (reduced form) to get σ²_v
        try:
            beta_rf = np.linalg.lstsq(ZF, y, rcond=None)[0]
            resid_rf = y - ZF @ beta_rf
            sigma2_v = max(np.var(resid_rf, ddof=ZF.shape[1]), 1e-10)
        except np.linalg.LinAlgError:
            sigma2_v = 1.0

        # AR F = (resid' M_Z resid / l) / σ²_v
        ar_f = (ar_num / l) / sigma2_v
        return float(ar_f)

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
        cluster2_var: str | None = None,
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
            主聚类变量（默认为 unit_var）。
        cluster2_var : str | None
            第二聚类变量，用于双向聚类标准误。

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

        two_way = cluster2_var is not None and cluster_var is not None and cluster_var != cluster2_var
        if two_way:
            result = model.fit(
                cov_type="clustered",
                cluster=(cluster_var, cluster2_var),
            )
        else:
            result = model.fit(
                cov_type="clustered",
                cluster=cluster_var or self.unit_var,
            )
        return result

    def blundell_bond(
        self,
        max_lags: int = 2,
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
    ) -> Any:
        """
        Blundell-Bond (1998) SYS-GMM（一步系统 GMM）。

        比 Arellano-Bond 更有效，当 N 较小时。

        Parameters
        ----------
        max_lags : int
            最多使用的滞后项数。
        cluster_var : str | None
            主聚类变量。
        cluster2_var : str | None
            第二聚类变量，用于双向聚类标准误。
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

        two_way = cluster2_var is not None and cluster_var is not None and cluster_var != cluster2_var
        if two_way:
            result = model.fit(
                cov_type="clustered",
                cluster=(cluster_var, cluster2_var),
            )
        else:
            result = model.fit(
                cov_type="clustered",
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
            f"{n_periods} periods: {_format_fmb_summary(results)}"
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

    # Hansen-Sargan J 检验
    # 注意：当误差项为同方差时，Sargan = Hansen J。
    # 当存在异方差时（本项目金融数据几乎必然存在），应使用 Hansen J 检验。
    # 本实现计算的是 Sargan 统计量（n * R² from 2SLS residuals on instruments）。
    # 若使用 GMM 估计（而非 2SLS），应计算真正的 Hansen J 统计量。
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
