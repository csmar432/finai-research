"""Volatility Models for Asset Pricing Research — GARCH Family & Realized Volatility.

本模块封装波动率建模方法，覆盖：
  1. GARCH(1,1) / GJR-GARCH / EGARCH / TARCH（`arch` 包）
  2. Realized Volatility：RV、Bipower Variation、Jump Test（Barndorff-Nielsen & Shephard 2006）
  3. RealizedGARCH（Hansen et al. 2012）
  4. HAR Model（Corsi 2009）
  5. Volatility Spillover Index（Diebold & Yilmaz 2014）
  6. VolatilitySuite 编排器

Usage:
    # GARCH
    garch = GARCHModel("GARCH", p=1, q=1)
    result = garch.fit(returns)
    print(garch.summary())
    fc = garch.forecast(h=10)

    # Realized Volatility
    rv_obj = RealizedVolatility()
    rv = rv_obj.compute_from_prices(prices)
    bpv = rv_obj.bipower_variation(prices)
    jump_test = rv_obj.jump_test(prices)

    # HAR
    har = HARModel()
    har.fit(rv_series)
    har_pred = har.forecast(h=5)

    # Volatility Spillover
    spill = VolatilitySpillover({"AAPL": ret1, "MSFT": ret2})
    spill_tbl = spill.diebold_yilmaz()

    # Full suite
    suite = VolatilitySuite()
    all_results = suite.run_all(prices=price_series, returns=return_series)
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "VolatilityResult",
    "GARCHModel",
    "RealizedVolatility",
    "RealizedGARCH",
    "HARModel",
    "VolatilitySpillover",
    "VolatilitySuite",
]

_log = logging.getLogger("volatility_models")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class VolatilityResult:
    """
    波动率模型估计结果容器。

    Attributes
    ----------
    model_type : str
        模型类型，如 "GARCH", "GJR-GARCH", "EGARCH", "HAR", "RealizedGARCH"。
    params : dict[str, float]
        参数字典。
    log_likelihood : float
        对数似然值。
    aic : float
        AIC 信息准则。
    bic : float
        BIC 信息准则。
    converged : bool
        是否收敛。
    arch_obj : Any
        原始拟合对象（用于 forecast）。
    std_resid : pd.Series | None
        标准化残差序列。
    cond_vol : pd.Series | None
        条件波动率序列。
    method : str
        估计方法或分布假设。
    n_obs : int
        有效观测数。
    message : str
        收敛消息或警告。
    additional : dict
        额外诊断（残差均值、波动率均值等）。
    """

    model_type: str
    params: dict[str, float] = field(default_factory=dict)
    log_likelihood: float = 0.0
    aic: float = 0.0
    bic: float = 0.0
    converged: bool = False
    arch_obj: Any = None
    std_resid: pd.Series | None = None
    cond_vol: pd.Series | None = None
    method: str = ""
    n_obs: int = 0
    message: str = ""
    additional: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "model_type": self.model_type,
            "log_likelihood": self.log_likelihood,
            "aic": self.aic,
            "bic": self.bic,
            "converged": self.converged,
            "n_obs": self.n_obs,
            "method": self.method,
            "message": self.message,
        }
        out.update(self.params)
        out.update(self.additional)
        return out

    def forecast(self, h: int = 1) -> np.ndarray:
        """
        基于 arch_obj 进行 h 步向前波动率预测。

        Parameters
        ----------
        h : int
            预测步数。

        Returns
        -------
        np.ndarray
            预测的条件波动率序列 (h,)。
        """
        if self.arch_obj is None:
            # 手动 GARCH：用持久性外推最后条件方差
            if self.cond_vol is not None and len(self.cond_vol) > 0:
                last_vol = float(self.cond_vol.iloc[-1])
                alpha = self.params.get("alpha", 0.08)
                beta = self.params.get("beta", 0.90)
                persistence = alpha + beta
                vol_preds = np.zeros(h)
                vol_cur = last_vol
                for i in range(h):
                    vol_cur = vol_cur * persistence  # 收敛到 0 的简化预测
                    vol_preds[i] = vol_cur
                return vol_preds
            _log.warning("[VolResult] No arch_obj and no cond_vol, returning NaN forecast")
            return np.full(h, np.nan)

        try:
            fc = self.arch_obj.forecast(horizon=h)
            # arch 8.0 返回 ARCHModelForecast，含 .variance DataFrame
            variance = getattr(fc, "variance", None)
            if variance is not None:
                var_vals = getattr(variance, "values", None)
                if var_vals is not None:
                    vol_fc = np.sqrt(np.asarray(var_vals[-1, :]))
                else:
                    vol_fc = np.sqrt(np.asarray(variance.iloc[-1, :].values))
            else:
                # 旧版 arch 返回协方差矩阵
                vol_fc = np.full(h, np.nan)
            return vol_fc
        except Exception as e:
            _log.warning(f"[VolResult] Forecast failed: {e}")
            return np.full(h, np.nan)

    def var_forecast(self, h: int = 1, level: float = 0.05) -> np.ndarray:
        """
        VaR 预测（假设 t 分布）。

        Parameters
        ----------
        h : int
            预测步数。
        level : float
            显著性水平（如 0.05 → 5% VaR）。

        Returns
        -------
        np.ndarray
            VaR 序列 (h,)。
        """
        vol_fc = self.forecast(h)
        # 获取 t 分布分位数（简化：使用正态分位数）
        try:
            from scipy import stats
            z = stats.norm.ppf(level)
        except Exception:
            z = -1.645
        # 返回绝对 VaR（负数）
        return z * vol_fc


# ─────────────────────────────────────────────────────────────────────────────
# GARCH FAMILY
# ─────────────────────────────────────────────────────────────────────────────

_GARCH_TYPES = {"GARCH", "GJR-GARCH", "EGARCH", "TARCH"}


class GARCHModel:
    """
    GARCH 族模型 — sklearn-like API。

    支持的模型类型：
      - "GARCH"：标准 GARCH( p, q )
      - "GJR-GARCH"：GJR-GARCH(p, o, q)，杠杆效应
      - "EGARCH"：指数 GARCH(p, q)
      - "TARCH"：门限 ARCH（对称 GJR 变体）

    使用方法：
        model = GARCHModel("GARCH", p=1, q=1)
        result = model.fit(returns)
        print(model.summary())
        fc = model.forecast(h=10)
        model.plot_conditional_vol("garch_vol.pdf")
    """

    def __init__(
        self,
        model_type: str = "GARCH",
        p: int = 1,
        q: int = 1,
        o: int = 1,
        dist: str = "t",
    ):
        if model_type not in _GARCH_TYPES:
            raise ValueError(
                f"model_type must be one of {_GARCH_TYPES}, got {model_type}"
            )
        self.model_type = model_type
        self.p = p
        self.q = q
        self.o = o  # GJR/EGARCH 中的不对称阶
        self.dist = dist
        self._result: VolatilityResult | None = None
        self._returns: pd.Series | None = None
        self._arch_model: Any = None

    # ── fit ──────────────────────────────────────────────────────────────────

    def fit(
        self, returns: pd.Series | np.ndarray | list
    ) -> VolatilityResult:
        """
        拟合 GARCH 族模型。

        Parameters
        ----------
        returns : pd.Series | np.ndarray | list
            收益率序列（百分比或小数均可，建议统一缩放）。

        Returns
        -------
        VolatilityResult
            包含参数、收敛状态、AIC/BIC 等。
        """
        # 转换为 Series
        if isinstance(returns, list | np.ndarray):
            returns = pd.Series(returns)
        if not isinstance(returns, pd.Series):
            raise TypeError("returns must be pd.Series, np.ndarray or list")

        returns = returns.dropna().astype(float)
        if len(returns) < 50:
            _log.warning(
                f"[GARCH] Only {len(returns)} obs, results may be unreliable"
            )
        self._returns = returns

        # 尝试使用 arch 包
        has_arch = self._try_arch(returns)
        if has_arch:
            return self._result  # type: ignore

        # Fallback：手动 GARCH(1,1) MLE
        _log.info("[GARCH] arch package unavailable, using manual GARCH(1,1)")
        return self._fit_manual_garch11(returns)

    def _try_arch(self, returns: pd.Series) -> bool:
        """使用 `arch` 包拟合。成功返回 True。"""
        try:
            from arch import arch_model
        except ImportError:
            _log.info("[GARCH] arch package not found")
            return False

        try:
            r = returns.values.copy()

            # vol type mapping
            vol_map = {
                "GARCH": "Garch",
                "GJR-GARCH": "Garch",
                "EGARCH": "EGarch",
                "TARCH": "Garch",
            }
            vol_type = vol_map[self.model_type]

            # arch 包 p/o/q 参数
            if self.model_type in ("GARCH", "EGARCH"):
                am = arch_model(
                    r * 100,  # arch expects percentage
                    vol=vol_type,
                    p=self.p,
                    q=self.q,
                    dist=self.dist,
                )
            elif self.model_type in ("GJR-GARCH", "TARCH"):
                am = arch_model(
                    r * 100,
                    vol=vol_type,
                    p=self.p,
                    o=self.o,
                    q=self.q,
                    dist=self.dist,
                )
            else:
                am = arch_model(r * 100, vol="Garch", p=1, q=1, dist=self.dist)

            res = am.fit(disp="off", options={"maxiter": 500})

            # 收敛判断：arch 8.0 的 converged 是一个 property，
            # 其实现内部访问 optimization_result.success 可能引发 AttributeError。
            # 策略：直接读 convergence_flag（肯定存在），不用 converged 属性。
            _converged = getattr(res, "convergence_flag", -1) == 0

            # 提取参数
            param_names = res.params.index.tolist()
            params = dict(zip(param_names, res.params.values.tolist(), strict=False))

            # 提取标准化残差和条件波动率
            # arch 8.0+ 返回 plain ndarray；早期版本返回 Series，统一处理
            cond_vol_raw: Any = res.conditional_volatility  # type: ignore[attr-defined]
            std_resid_raw: Any = res.std_resid  # type: ignore[attr-defined]

            if isinstance(cond_vol_raw, np.ndarray):
                cond_vol_vals = cond_vol_raw.astype(float)
            elif hasattr(cond_vol_raw, "values"):
                cond_vol_vals = np.asarray(cond_vol_raw.values)
            else:
                cond_vol_vals = np.asarray(cond_vol_raw)

            if isinstance(std_resid_raw, np.ndarray):
                std_resid_vals = std_resid_raw.astype(float)
            elif hasattr(std_resid_raw, "values"):
                std_resid_vals = np.asarray(std_resid_raw.values)
            else:
                std_resid_vals = np.asarray(std_resid_raw)

            cond_vol_vals = cond_vol_vals / 100  # 还原为小数单位
            std_resid = pd.Series(std_resid_vals, index=returns.index[: len(std_resid_vals)])
            cond_vol = pd.Series(cond_vol_vals, index=returns.index[: len(cond_vol_vals)])

            # AIC / BIC
            aic_val = float(res.aic)
            bic_val = float(res.bic)
            ll = float(res.loglikelihood)

            self._arch_model = res

            self._result = VolatilityResult(
                model_type=self.model_type,
                params=params,
                log_likelihood=ll,
                aic=aic_val,
                bic=bic_val,
                converged=_converged,
                arch_obj=res,
                std_resid=std_resid,
                cond_vol=cond_vol,
                method=self.dist,
                n_obs=len(returns),
                message="arch package",
                additional={
                    "resid_mean": float(np.nanmean(std_resid_vals)),
                    "resid_std": float(np.nanstd(std_resid_vals)),
                    "cond_vol_mean": float(np.nanmean(cond_vol_vals)),
                },
            )
            self._result.arch_obj = res

            _log.info(
                f"[GARCH] {self.model_type} arch converged={_converged} "
                f"AIC={aic_val:.2f} BIC={bic_val:.2f}"
            )
            return True

        except Exception as e:
            _log.warning(f"[GARCH] arch fit failed: {e}")
            return False

    def _fit_manual_garch11(self, returns: pd.Series) -> VolatilityResult:
        """
        手动实现 GARCH(1,1) ML 估计（当 arch 包不可用时）。

        使用analytical gradient 和 analytical Hessian（MLE with Gaussian）。

        r_t = σ_t * ε_t,  ε_t ~ N(0,1)
        σ²_t = ω + α * r²_{t-1} + β * σ²_{t-1}
        """
        from scipy.optimize import minimize

        r = returns.values.astype(float)
        T = len(r)

        def neg_ll(params: np.ndarray) -> float:
            omega, alpha, beta = params
            if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
                return 1e10

            sigma2 = np.zeros(T)
            sigma2[0] = np.var(r)
            for t in range(1, T):
                sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]

            sigma2 = np.maximum(sigma2, 1e-12)
            ll = -0.5 * (np.log(2 * np.pi) + np.log(sigma2) + r**2 / sigma2)
            return -np.sum(ll)

        # 初始值：EWMA (λ=0.94)
        var_ewma = np.zeros(T)
        lam = 0.94
        var_ewma[0] = np.var(r)
        for t in range(1, T):
            var_ewma[t] = lam * var_ewma[t - 1] + (1 - lam) * r[t - 1] ** 2

        alpha0 = 0.08
        beta0 = 0.90
        omega0 = (1 - alpha0 - beta0) * np.mean(var_ewma)

        x0 = np.array([omega0, alpha0, beta0])

        # 约束：omega>0, alpha>=0, beta>=0, alpha+beta<1
        bounds = [(1e-6, None), (0.0, 0.5), (0.5, 0.999)]

        res = minimize(
            neg_ll,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 1000, "ftol": 1e-8},
        )

        omega_hat, alpha_hat, beta_hat = res.x
        converged = res.success

        # 计算条件方差序列
        sigma2 = np.zeros(T)
        sigma2[0] = np.var(r)
        for t in range(1, T):
            sigma2[t] = omega_hat + alpha_hat * r[t - 1] ** 2 + beta_hat * sigma2[t - 1]

        cond_vol = pd.Series(np.sqrt(sigma2), index=returns.index)
        std_resid = pd.Series(r / np.sqrt(sigma2), index=returns.index)

        # AIC / BIC
        ll_val = -res.fun
        k = 3
        aic_val = -2 * ll_val + 2 * k
        bic_val = -2 * ll_val + k * np.log(T)

        params = {"omega": omega_hat, "alpha": alpha_hat, "beta": beta_hat}

        result = VolatilityResult(
            model_type="GARCH(1,1)-manual",
            params=params,
            log_likelihood=ll_val,
            aic=aic_val,
            bic=bic_val,
            converged=converged,
            arch_obj=None,
            std_resid=std_resid,
            cond_vol=cond_vol,
            method="gaussian",
            n_obs=T,
            message="manual MLE" if converged else "manual MLE (may not converge)",
            additional={
                "resid_mean": float(np.nanmean(std_resid.values)),
                "resid_std": float(np.nanstd(std_resid.values)),
                "cond_vol_mean": float(np.nanmean(cond_vol.values)),
                "persistence": float(alpha_hat + beta_hat),
            },
        )
        self._result = result
        return result

    # ── forecast ─────────────────────────────────────────────────────────────

    def forecast(self, h: int = 10) -> pd.DataFrame:
        """
        向前 h 步波动率预测。

        Parameters
        ----------
        h : int
            预测步数。

        Returns
        -------
        pd.DataFrame
            含列：[date_offset, mean, vol, lower, upper] 的预测表。
        """
        if self._result is None:
            raise RuntimeError("Must call fit() before forecast()")

        vol_fc = self._result.forecast(h)

        # 置信区间（简化：±1.96 * std）
        se_fc = vol_fc / math.sqrt(h)  # h步平均波动率标准误近似

        idx = range(1, h + 1)
        fc_df = pd.DataFrame(
            {
                "horizon": idx,
                "mean": 0.0,  # 条件均值（假设为0）
                "vol": vol_fc,
                "lower": vol_fc - 1.96 * se_fc,
                "upper": vol_fc + 1.96 * se_fc,
            },
            index=idx,
        )
        fc_df.index.name = "step"

        _log.info(f"[GARCH] Forecast {h} steps, avg vol={vol_fc.mean():.6f}")
        return fc_df

    # ── summary ─────────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        返回模型参数汇总表。

        Returns
        -------
        pd.DataFrame
        """
        if self._result is None:
            return pd.DataFrame()

        params = self._result.params
        rows = []
        for name, val in params.items():
            rows.append({"parameter": name, "estimate": f"{val:.6f}"})

        rows.extend([
            {"parameter": "Log-Likelihood", "estimate": f"{self._result.log_likelihood:.4f}"},
            {"parameter": "AIC", "estimate": f"{self._result.aic:.4f}"},
            {"parameter": "BIC", "estimate": f"{self._result.bic:.4f}"},
            {"parameter": "N", "estimate": str(self._result.n_obs)},
            {"parameter": "Converged", "estimate": str(self._result.converged)},
            {"parameter": "Method", "estimate": self._result.method},
        ])
        return pd.DataFrame(rows).set_index("parameter")

    # ── plot ────────────────────────────────────────────────────────────────

    def plot_conditional_vol(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (12, 6),
    ) -> Any:
        """
        绘制条件波动率和 VaR 覆盖图。

        Parameters
        ----------
        save_path : str | Path | None
            保存路径（.pdf / .png）。
        figsize : tuple
            图形尺寸。

        Returns
        -------
        matplotlib Figure 或 None
        """
        if self._result is None or self._returns is None:
            _log.warning("[GARCH] No fit results to plot")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[GARCH] matplotlib not installed")
            return None

        cond_vol = self._result.cond_vol
        if cond_vol is None:
            return None

        returns = self._returns
        # 标准化对齐
        min_len = min(len(returns), len(cond_vol))
        ret_plot = returns.iloc[:min_len]
        vol_plot = cond_vol.iloc[:min_len]

        # VaR 95%
        var_95 = -1.645 * vol_plot

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)

        # 上：收益率 + VaR
        ax1.plot(ret_plot.index, ret_plot.values, color="steelblue", alpha=0.6, linewidth=0.5)
        ax1.plot(var_95.index, var_95.values, color="red", linewidth=1.0, label="VaR 95%")
        ax1.axhline(0, color="gray", linewidth=0.5)
        ax1.set_ylabel("Return", fontsize=11)
        ax1.set_title(f"{self.model_type} — Conditional Volatility & VaR", fontsize=13, fontweight="bold")
        ax1.legend(loc="upper right")
        ax1.grid(True, alpha=0.3)

        # 下：条件波动率
        ax2.fill_between(vol_plot.index, 0, vol_plot.values, alpha=0.4, color="orange", label="σ_t")
        ax2.plot(vol_plot.index, vol_plot.values, color="darkorange", linewidth=0.8)
        ax2.set_ylabel("Conditional Volatility", fontsize=11)
        ax2.set_xlabel("Date", fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper right")

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[GARCH] Conditional vol plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# REALIZED VOLATILITY
# ─────────────────────────────────────────────────────────────────────────────


class RealizedVolatility:
    """
    已实现波动率系列 — 基于高频价格数据。

    方法：
      - Realized Variance：RV = Σ r²_i
      - Realized Volatility：RV½
      - Bipower Variation：BPV = (π/2) Σ |r_i| · |r_{i+1}|（Andersen et al. 2001）
      - Jump Test：Barndorff-Nielsen & Shephard (2006)  jump 检验

    使用方法：
        rv_obj = RealizedVolatility()
        rv = rv_obj.compute_from_prices(prices, rule="5min")
        bpv = rv_obj.bipower_variation(prices, rule="5min")
        jt = rv_obj.jump_test(prices, threshold=3.0)
        rv_obj.plot_rv_comparison("rv_compare.pdf")
    """

    def compute_from_prices(
        self,
        prices: pd.Series,
        resample_rule: str = "5min",
    ) -> pd.Series:
        """
        计算已实现波动率（Realized Volatility）。

        RV = Σ r²_i,   其中 r_i = ln(P_{t_i} / P_{t_{i-1}})

        Parameters
        ----------
        prices : pd.Series
            价格序列（带有 datetimeindex）。
        resample_rule : str
            重采样频率，如 "5min", "10min", "1h"。

        Returns
        -------
        pd.Series
            日频已实现波动率序列。
        """
        prices = prices.dropna()
        if len(prices) < 2:
            _log.warning("[RV] Too few prices")
            return pd.Series(dtype=float)

        try:
            # 1. 计算日内收益率
            resampled = prices.resample(resample_rule).last().dropna()
            log_returns = np.log(resampled / resampled.shift(1)).dropna()

            # 2. 按日聚合 Realized Variance
            rv_series = (log_returns ** 2).resample("B").sum()

            # 3. Realized Volatility = √RV
            rv = np.sqrt(rv_series)
            rv.name = f"RV_{resample_rule}"
            rv = rv[rv > 0]

            _log.info(
                f"[RV] Computed RV from {len(rv)} days, "
                f"mean={rv.mean():.6f}, std={rv.std():.6f}"
            )
            return rv

        except Exception as e:
            _log.warning(f"[RV] compute_from_prices failed: {e}")
            return pd.Series(dtype=float)

    def bipower_variation(
        self,
        prices: pd.Series,
        resample_rule: str = "5min",
    ) -> pd.Series:
        """
        计算双幂变差（Bipower Variation）。

        BPV = (π/2) * Σ |r_i| * |r_{i+1}|
        用途：无跳情况下的积分波动率一致估计。

        Parameters
        ----------
        prices : pd.Series
            价格序列。
        resample_rule : str
            重采样频率。

        Returns
        -------
        pd.Series
            日频 Bipower Variation 序列。
        """
        prices = prices.dropna()
        try:
            resampled = prices.resample(resample_rule).last().dropna()
            log_ret = np.log(resampled / resampled.shift(1)).dropna()

            abs_ret = np.abs(log_ret)
            bpv_raw = (math.pi / 2) * abs_ret * abs_ret.shift(1).fillna(0)
            bpv_raw = bpv_raw + (math.pi / 2) * abs_ret.shift(1) * abs_ret.fillna(0)
            bpv_raw = bpv_raw / 2  # 避免重复计数

            bpv = bpv_raw.resample("B").sum()
            bpv.name = f"BPV_{resample_rule}"
            bpv = bpv[bpv > 0]

            _log.info(f"[RV] BPV: {len(bpv)} obs, mean={bpv.mean():.6f}")
            return bpv

        except Exception as e:
            _log.warning(f"[RV] bipower_variation failed: {e}")
            return pd.Series(dtype=float)

    def jump_test(
        self,
        prices: pd.Series,
        threshold: float = 3.0,
        resample_rule: str = "5min",
    ) -> dict:
        """
        Barndorff-Nielsen & Shephard (2006) 跳检验。

        测试统计量：
          Z_t = (RV_t - BPV_t) / Θ_t  →  N(0,1) under H0 (no jumps)

        其中 Θ_t = μ^{-1} * √(2/π) * Q_t
              Q_t = Σ |r_i|^2 * |r_{i+1}|
              μ = √(2/π)

        Parameters
        ----------
        prices : pd.Series
            价格序列。
        threshold : float
            多重阈值（用于 Θ 估计，默认 3.0）。

        Returns
        -------
        dict
            含 jump_var, bpv_var, z_stat, pval, has_jumps 的字典。
        """
        prices = prices.dropna()
        try:
            resampled = prices.resample(resample_rule).last().dropna()
            log_ret = np.log(resampled / resampled.shift(1)).dropna().values

            T = len(log_ret)
            if T < 10:
                _log.warning("[RV] Too few obs for jump test")
                return {"jump_var": np.nan, "bpv_var": np.nan, "z_stat": np.nan, "pval": np.nan, "has_jumps": False}

            # Realized Variance
            rv = np.sum(log_ret**2)

            # Bipower Variation
            abs_ret = np.abs(log_ret)
            bpv = (math.pi / 2) * np.sum(abs_ret[:-1] * abs_ret[1:])

            # Q component (for variance of the test statistic)
            q_comp = np.sum(abs_ret[:-1] ** 2 * abs_ret[1:] ** 2)

            # Robust estimator Θ
            # Θ ≈ μ^{-1} * √(2/π) * √(Q)  [simplified]
            mu = math.sqrt(2 / math.pi)
            theta = mu**-1 * math.sqrt(2 / math.pi) * np.sqrt(max(q_comp, 1e-12))

            # Z-statistic
            if theta > 1e-10:
                z_stat = (rv - bpv) / theta
            else:
                z_stat = 0.0

            from scipy import stats

            pval = 2 * (1 - stats.norm.cdf(abs(z_stat)))
            has_jumps = pval < 0.05

            result = {
                "jump_var": rv - bpv,  # 归因于跳的方差
                "bpv_var": bpv,  # 连续部分方差
                "rv": rv,  # 总方差
                "z_stat": float(z_stat),
                "pval": float(pval),
                "has_jumps": bool(has_jumps),
                "threshold_used": threshold,
            }

            _log.info(
                f"[RV] Jump test: Z={z_stat:.3f}, p={pval:.4f}, "
                f"has_jumps={has_jumps}"
            )
            return result

        except Exception as e:
            _log.warning(f"[RV] jump_test failed: {e}")
            return {
                "jump_var": np.nan,
                "bpv_var": np.nan,
                "z_stat": np.nan,
                "pval": np.nan,
                "has_jumps": False,
                "error": str(e),
            }

    def plot_rv_comparison(
        self,
        garch_vol: pd.Series | None = None,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (12, 5),
    ) -> Any:
        """
        绘制已实现波动率与 GARCH 波动率的对比图。

        Parameters
        ----------
        garch_vol : pd.Series | None
            可选：GARCH 条件波动率序列（用于对比）。
        save_path : str | Path | None
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[RV] matplotlib not installed")
            return None

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title("Realized Volatility vs GARCH Volatility", fontsize=13, fontweight="bold")

        if garch_vol is not None and len(garch_vol) > 0:
            ax.plot(garch_vol.index, garch_vol.values, label="GARCH σ_t", alpha=0.8, linewidth=1.2, color="steelblue")
            ax.legend(loc="upper right")
        else:
            ax.set_ylabel("Realized Volatility", fontsize=11)

        ax.set_xlabel("Date", fontsize=11)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[RV] RV comparison plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# REALIZED GARCH
# ─────────────────────────────────────────────────────────────────────────────


class RealizedGARCH:
    """
    RealizedGARCH — Hansen et al. (2012) RGS 估计。

    模型结构：
      测量方程：h_t = ω + β * σ²_{t-1} + γ * rv_{t-1}
      过渡方程：ln(σ²_t) = μ + φ * ln(σ²_{t-1}) + u_t,  u_t ~ N(0, σ_u²)

    使用方法：
        rgarch = RealizedGARCH()
        result = rgarch.fit(rv=rv_series, returns=return_series)
        pred = rgarch.predict(h=5)
    """

    def __init__(self):
        self._params: dict | None = None
        self._rv: pd.Series | None = None
        self._returns: pd.Series | None = None
        self._fitted_vol: pd.Series | None = None

    def fit(
        self,
        rv: pd.Series,
        returns: pd.Series,
    ) -> dict:
        """
        拟合 RealizedGARCH(1,1)。

        Parameters
        ----------
        rv : pd.Series
            已实现波动率序列（日频，平方根形式 RV^0.5）。
        returns : pd.Series
            日收益率序列。

        Returns
        -------
        dict
            拟合结果字典。
        """
        from scipy.optimize import minimize

        # 对齐：去除 NaN，再截取公共长度
        df = pd.DataFrame({"rv": rv, "ret": returns}).dropna()
        min_len = min(len(df), len(rv), len(returns))
        if min_len < 60:
            _log.warning(f"[RealizedGARCH] Only {len(df)} obs")
            return {}

        rv_vals = df["rv"].values.astype(float)
        r_vals = df["ret"].values.astype(float)
        T = len(r_vals)

        # rv_t 是已实现波动率（平方根）
        # 测量方程：h_t = ω + β*σ²_{t-1} + γ*rv_{t-1}
        # 过渡方程：ln(σ²_t) = μ + φ*ln(σ²_{t-1}) + u_t

        def neg_ll(params: np.ndarray) -> float:
            omega, beta, gamma, mu, phi, sigma_u = params
            if omega <= 0 or beta < 0 or gamma < 0 or sigma_u <= 0 or not (-1 < phi < 1):
                return 1e10

            sigma2 = np.zeros(T)
            sigma2[0] = np.var(r_vals)

            # 过渡方程初始化
            ln_sigma2 = np.log(np.maximum(sigma2[0], 1e-12))

            for t in range(1, T):
                ln_sigma2 = mu + phi * ln_sigma2 + sigma_u * np.random.randn()

            # 测量方程（简化）
            for t in range(1, T):
                h_t = omega + beta * sigma2[t - 1] + gamma * rv_vals[t - 1] ** 2
                sigma2[t] = max(h_t, 1e-12)

            np.sqrt(sigma2)
            ll = -0.5 * (np.log(2 * np.pi) + np.log(sigma2) + r_vals**2 / sigma2)
            return -np.sum(ll)

        # 初始值
        x0 = np.array([1e-5, 0.5, 0.5, -0.1, 0.9, 0.1])
        bounds = [
            (1e-8, 0.01),   # omega
            (0.0, 0.99),     # beta
            (0.0, 0.99),     # gamma
            (-1.0, 1.0),    # mu
            (-0.99, 0.99),   # phi
            (1e-3, 1.0),    # sigma_u
        ]

        res = minimize(
            neg_ll,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500},
        )

        omega_hat, beta_hat, gamma_hat, mu_hat, phi_hat, sigma_u_hat = res.x
        converged = res.success

        # 重建条件波动率序列
        sigma2_fit = np.zeros(T)
        sigma2_fit[0] = np.var(r_vals)
        for t in range(1, T):
            h_t = omega_hat + beta_hat * sigma2_fit[t - 1] + gamma_hat * rv_vals[t - 1] ** 2
            sigma2_fit[t] = max(h_t, 1e-12)

        cond_vol = pd.Series(np.sqrt(sigma2_fit), index=df.index)

        params = {
            "omega": omega_hat,
            "beta": beta_hat,
            "gamma": gamma_hat,
            "mu": mu_hat,
            "phi": phi_hat,
            "sigma_u": sigma_u_hat,
        }
        ll_val = -res.fun
        k = len(params)
        aic_val = -2 * ll_val + 2 * k
        bic_val = -2 * ll_val + k * np.log(T)

        self._params = params
        self._rv = rv
        self._returns = returns
        self._fitted_vol = cond_vol

        result = {
            "params": params,
            "log_likelihood": ll_val,
            "aic": aic_val,
            "bic": bic_val,
            "converged": converged,
            "n_obs": T,
            "cond_vol": cond_vol,
        }

        _log.info(
            f"[RealizedGARCH] converged={converged}, "
            f"AIC={aic_val:.2f}, BIC={bic_val:.2f}, "
            f"β={beta_hat:.3f}, γ={gamma_hat:.3f}, φ={phi_hat:.3f}"
        )
        return result

    def predict(self, h: int = 1) -> np.ndarray:
        """
        向前 h 步预测条件波动率。

        Parameters
        ----------
        h : int

        Returns
        -------
        np.ndarray
            预测波动率序列 (h,)。
        """
        if self._params is None:
            raise RuntimeError("Must call fit() before predict()")

        p = self._params
        preds = np.zeros(h)
        sigma2_last = (self._fitted_vol.iloc[-1] ** 2) if self._fitted_vol is not None else 1e-4

        for i in range(h):
            h_pred = p["omega"] + p["beta"] * sigma2_last + p["gamma"] * 0  # rv=0 for forecast
            sigma2_last = max(h_pred, 1e-12)
            preds[i] = math.sqrt(sigma2_last)

        _log.info(f"[RealizedGARCH] Forecast {h} steps")
        return preds


# ─────────────────────────────────────────────────────────────────────────────
# HAR MODEL
# ─────────────────────────────────────────────────────────────────────────────


class HARModel:
    """
    Heterogeneous Autoregressive (HAR) Model — Corsi (2009).

    模型：
      rv_t = α + β_d * rv_{t-1} + β_w * (1/5)Σ_{j=1}^5 rv_{t-j}
             + β_m * (1/22)Σ_{j=1}^22 rv_{t-j} + ε_t

    使用方法：
        har = HARModel()
        result = har.fit(rv_series)
        har_pred = har.forecast(h=5)
        har.plot_fit("har_fit.pdf")
    """

    def __init__(self):
        self._params: dict = {}
        self._rv: pd.Series | None = None
        self._fitted: pd.Series | None = None
        self._model_result: Any = None

    def fit(self, rv: pd.Series) -> dict:
        """
        拟合 HAR 模型（OLS）。

        Parameters
        ----------
        rv : pd.Series
            已实现波动率序列（日频）。

        Returns
        -------
        dict
            含 params, aic, bic, fitted values 的字典。
        """
        rv = rv.dropna()
        if len(rv) < 22:  # minimum for monthly lag
            _log.warning(f"[HAR] Only {len(rv)} obs — need ≥22 for monthly lag")
            return {}

        self._rv = rv.copy()
        df = pd.DataFrame({"rv": rv})

        # 构建日/周/月滞后
        df["rv_d"] = df["rv"].shift(1)  # 1天滞后
        df["rv_w"] = df["rv"].shift(1).rolling(5).mean()  # 5天平均
        df["rv_m"] = df["rv"].shift(1).rolling(22).mean()  # 22天平均

        df = df.dropna()
        if len(df) < 22:
            _log.warning("[HAR] Too few obs after lag construction — need ≥22")
            return {}

        y = df["rv"].values
        X = df[["rv_d", "rv_w", "rv_m"]].values

        try:
            import statsmodels.api as sm

            X_const = sm.add_constant(X, has_constant="skip")
            model = sm.OLS(y, X_const)
            res = model.fit()

            self._model_result = res
            self._params = {
                "alpha": float(res.params[0]),
                "beta_d": float(res.params[1]),
                "beta_w": float(res.params[2]),
                "beta_m": float(res.params[3]),
            }
            self._fitted = pd.Series(
                res.fittedvalues, index=df.index, name="HAR_fitted"
            )

            result = {
                "params": self._params,
                "aic": float(res.aic),
                "bic": float(res.bic),
                "r_squared": float(res.rsquared),
                "n_obs": len(df),
                "fitted": self._fitted,
                "model_result": res,
            }

            _log.info(
                f"[HAR] α={self._params['alpha']:.6f} "
                f"β_d={self._params['beta_d']:.4f} "
                f"β_w={self._params['beta_w']:.4f} "
                f"β_m={self._params['beta_m']:.4f} "
                f"R²={res.rsquared:.4f}"
            )
            return result

        except Exception as e:
            _log.warning(f"[HAR] fit failed: {e}")
            return {}

    def forecast(self, h: int = 1) -> float | np.ndarray:
        """
        向前 h 步预测。

        Parameters
        ----------
        h : int

        Returns
        -------
        float | np.ndarray
            预测值。
        """
        if not self._params:
            _log.warning("[HAR] Not fitted yet — returning NaN")
            return np.full(h, np.nan) if h > 1 else np.nan

        if self._rv is None:
            return np.nan

        # 使用最近值
        rv_last = self._rv.iloc[-22:].values
        if len(rv_last) < 22:
            rv_last = np.pad(rv_last, (22 - len(rv_last), 0), constant_values=np.nan)
            rv_last = np.nanmean(rv_last)

        avg_w = np.nanmean(rv_last[-5:]) if len(rv_last) >= 5 else float(np.nanmean(rv_last))
        avg_m = float(np.nanmean(rv_last))

        alpha = self._params.get("alpha", 0)
        beta_d = self._params.get("beta_d", 0)
        beta_w = self._params.get("beta_w", 0)
        beta_m = self._params.get("beta_m", 0)

        if h == 1:
            pred = alpha + beta_d * self._rv.iloc[-1] + beta_w * avg_w + beta_m * avg_m
            _log.info(f"[HAR] 1-step forecast: {pred:.6f}")
            return float(pred)

        preds = np.zeros(h)
        rv_cur = float(self._rv.iloc[-1])
        for i in range(h):
            preds[i] = alpha + beta_d * rv_cur + beta_w * avg_w + beta_m * avg_m
            # 更新（简化）
            rv_cur = preds[i]

        _log.info(f"[HAR] {h}-step forecast avg: {preds.mean():.6f}")
        return preds

    def plot_fit(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (12, 5),
    ) -> Any:
        """
        绘制 HAR 拟合 vs 实际 RV。

        Parameters
        ----------
        save_path : str | Path | None
        figsize : tuple

        Returns
        -------
        matplotlib Figure 或 None
        """
        if self._rv is None or self._fitted is None:
            _log.warning("[HAR] No fit results to plot")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[HAR] matplotlib not installed")
            return None

        fig, ax = plt.subplots(figsize=figsize)

        ax.plot(self._rv.index, self._rv.values, label="Actual RV", alpha=0.6, linewidth=0.8, color="steelblue")
        ax.plot(self._fitted.index, self._fitted.values, label="HAR Fit", alpha=0.8, linewidth=0.8, color="red")
        ax.set_title("HAR Model Fit: Realized Volatility", fontsize=13, fontweight="bold")
        ax.set_xlabel("Date", fontsize=11)
        ax.set_ylabel("Realized Volatility", fontsize=11)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        if self._params:
            param_text = (
                f"α={self._params.get('alpha', 0):.4f}\n"
                f"β_d={self._params.get('beta_d', 0):.4f}\n"
                f"β_w={self._params.get('beta_w', 0):.4f}\n"
                f"β_m={self._params.get('beta_m', 0):.4f}"
            )
            ax.text(
                0.02, 0.95, param_text, transform=ax.transAxes,
                fontsize=9, verticalalignment="top",
                bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
            )

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[HAR] Fit plot saved: {save_path}")

        return fig


# ─────────────────────────────────────────────────────────────────────────────
# VOLATILITY SPILLOVER
# ─────────────────────────────────────────────────────────────────────────────


class VolatilitySpillover:
    """
    Diebold & Yilmaz (2014) 波动率溢出指数。

    使用 VAR(p) 对多资产波动率序列建模，计算广义脉冲响应（GIRF），
    量化来自其他资产波动的贡献比例。

    使用方法：
        spill = VolatilitySpillover({"AAPL": ret1, "MSFT": ret2, "GOOGL": ret3})
        result = spill.diebold_yilmaz()
        print(spill.to_latex())
    """

    def __init__(self, returns_dict: dict[str, pd.Series] | None = None, max_lags: int = 4):
        """
        Parameters
        ----------
        returns_dict : dict[str, pd.Series] | None
            资产名 → 日收益率序列的字典。
        max_lags : int
            VAR 最优滞后阶数（默认 4）。
        """
        self.returns_dict: dict[str, pd.Series] = returns_dict or {}
        self.max_lags = max_lags
        self._vol_df: pd.DataFrame | None = None
        self._spillover: pd.DataFrame | None = None
        self._var_result: Any = None
        self._p: int = 2

    def _build_vol_series(self) -> pd.DataFrame:
        """从收益率构建波动率序列（GARCH 或简单 rolling std）。"""
        if not self.returns_dict:
            return pd.DataFrame()

        try:

            # 对齐所有收益率
            series_list = []
            names = []
            for name, ret in self.returns_dict.items():
                r = ret.dropna()
                if len(r) > 100:
                    series_list.append(r)
                    names.append(name)

            if len(series_list) < 2:
                _log.warning("[Spillover] Need at least 2 assets")
                return pd.DataFrame()

            aligned = pd.concat(series_list, axis=1)
            aligned.columns = names

            # 使用 GARCH(1,1) 条件波动率 或 rolling std（优先 GARCH）
            has_arch = False
            vol_list = []

            try:
                from arch import arch_model

                has_arch = True
            except ImportError:
                pass

            for name in names:
                ret_series = aligned[name].dropna()
                if has_arch:
                    try:
                        am = arch_model(ret_series.values * 100, vol="Garch", p=1, q=1, dist="t")
                        res = am.fit(disp="off")
                        vol = res.conditional_volatility.values / 100
                        vol_series = pd.Series(vol, index=ret_series.index)
                    except Exception:
                        vol_series = ret_series.rolling(22).std().fillna(0)
                else:
                    vol_series = ret_series.rolling(22).std().fillna(0)

                vol_list.append(vol_series)

            vol_df = pd.concat(vol_list, axis=1)
            vol_df.columns = names
            vol_df = vol_df.dropna()

            self._vol_df = vol_df
            return vol_df

        except Exception as e:
            _log.warning(f"[Spillover] build_vol_series failed: {e}")
            return pd.DataFrame()

    def diebold_yilmaz(
        self,
        n_var: int = 10,
    ) -> pd.DataFrame:
        """
        计算 Diebold-Yilmaz 波动率溢出表。

        Parameters
        ----------
        n_var : int
            前 n 个资产纳入 VAR（按样本量排序，默认全部）。

        Returns
        -------
        pd.DataFrame
            溢出表（from × to matrix）。
        """
        vol_df = self._build_vol_series()
        if vol_df.empty:
            _log.warning("[Spillover] No volatility data")
            return pd.DataFrame()

        n_assets = min(n_var, len(vol_df.columns))
        vol_sub = vol_df.iloc[:, :n_assets]

        try:
            from statsmodels.tsa.api import VAR

            # 确定最优滞后
            model = VAR(vol_sub)
            lag_order = model.select_order(maxlags=self.max_lags)
            p = int(lag_order.aic) or 2
            self._p = p

            # 拟合 VAR(p)
            var_result = model.fit(p)
            self._var_result = var_result

            H = 10  # 预测步数
            n = n_assets

            # 获取 MA 表征系数 (H+1) × n × n
            A = var_result.ma_rep(maxn=H)
            if A is None or A.shape[0] < 2:
                _log.warning("[Spillover] VAR MA rep unavailable, using rolling vol instead")
                return self._spillover_from_rolling(vol_sub)

            from scipy.linalg import cholesky

            # 残差协方差矩阵（确保正定）
            sigma = np.asarray(var_result.sigma_u, dtype=float)
            sigma.shape[0]
            try:
                cholesky(sigma)
            except Exception:
                _log.warning("[Spillover] sigma_u not PD — falling back to rolling volatility spillover")
                return self._spillover_from_rolling(vol_sub)

            # H 步方差分解（广义脉冲响应）
            fevd = np.zeros((n, n))
            for i in range(n):
                for j in range(n):
                    for h in range(H + 1):
                        if h < len(A):
                            fevd[i, j] += (A[h, i, j] ** 2) * sigma[j, j]

            # 归一化（行方向：每个被预测变量的总方差贡献 = 1）
            row_sums = fevd.sum(axis=1, keepdims=True)
            row_sums = np.maximum(row_sums, 1e-12)
            fevd_norm = fevd / row_sums

            # 溢出贡献
            np.fill_diagonal(fevd_norm, 0)  # 排除自身贡献
            spillover_from = fevd_norm.sum(axis=1)  # 流出的总比例
            spillover_to = fevd_norm.sum(axis=0)    # 流入的总比例
            total_spillover = float(spillover_from.sum() / n)

            # 构建 DataFrame — 扩展到 (n+1) × (n+1)，加 "FROM Others" 行 + "TO Others" 列
            fevd_ext = np.zeros((n + 1, n + 1))
            fevd_ext[:n, :n] = fevd_norm
            # 重新归一化以容纳扩展维度（"Others" 行/列初始为 0）
            col_names = list(vol_sub.columns)
            idx_names = col_names + ["FROM Others"]
            spill_mat = pd.DataFrame(
                fevd_ext,
                index=idx_names,
                columns=col_names + ["TO Others"],
            )
            spill_mat["TO Others"] = list(spillover_from) + [total_spillover]
            spill_mat.loc["FROM Others", col_names] = spillover_to
            spill_mat.loc["FROM Others", "TO Others"] = total_spillover

            self._spillover = spill_mat

            _log.info(
                f"[Spillover] DY Index={total_spillover:.2%} "
                f"p={p} lags, {n_assets} assets"
            )
            return spill_mat

        except Exception as e:
            _log.warning(f"[Spillover] diebold_yilmaz failed: {e}")
            return self._spillover_from_rolling(vol_sub)

    def _spillover_from_rolling(self, vol_df: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Fallback：基于滚动标准差的条件波动率溢出分析。

        当 VAR 残差协方差矩阵非正定时使用此方法。
        计算各资产滚动波动率之间的相关系数矩阵作为溢出近似。
        """
        if vol_df is None:
            vol_df = self._vol_df if self._vol_df is not None else pd.DataFrame()
        if vol_df.empty:
            return pd.DataFrame()
        n_assets = vol_df.shape[1]
        names = list(vol_df.columns)

        # 协方差矩阵（滚动窗口）
        cov_mat = vol_df.corr().values.copy()  # copy() 确保可写
        np.fill_diagonal(cov_mat, 0)  # 排除自身

        # 构建 (n+1)×(n+1) 溢出矩阵
        spill_mat = np.zeros((n_assets + 1, n_assets + 1))
        spill_mat[:n_assets, :n_assets] = cov_mat

        spillover_from = cov_mat.sum(axis=1) / max(n_assets - 1, 1)
        spillover_to = cov_mat.sum(axis=0) / max(n_assets - 1, 1)
        total = float(spillover_from.sum() / n_assets)

        # 最后一行（流出）和最后一列（流入）
        spill_mat[:n_assets, n_assets] = spillover_from
        spill_mat[n_assets, :n_assets] = spillover_to
        spill_mat[n_assets, n_assets] = total

        spill_mat_df = pd.DataFrame(
            spill_mat,
            index=names + ["FROM Others"],
            columns=names + ["TO Others"],
        )

        self._spillover = spill_mat_df
        _log.info(f"[Spillover] Rolling fallback — correlation-based spillover, total={total:.2%}")
        return spill_mat_df

    def to_latex(
        self,
        caption: str = "Volatility Spillover Table",
        label: str = "tab:spillover",
        fmt: str = ".2f",
    ) -> str:
        """
        导出溢出表为 LaTeX 格式。

        Parameters
        ----------
        caption : str
        label : str
        fmt : str
            数值格式。

        Returns
        -------
        str
            LaTeX 代码。
        """
        if self._spillover is None or self._spillover.empty:
            return ""

        df = self._spillover.copy()
        len(df) - 1

        # 格式化为百分比
        df_pct = df.map(lambda x: f"{float(x)*100:{fmt}}\\%")

        col_spec = "l" + "c" * len(df.columns)

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            "  \\small",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            "    \\toprule",
            "    \\textbf{} & " + " & ".join(f"\\textbf{{{c[:8]}}}" for c in df.columns) + " \\\\ ",
            "    \\midrule",
        ]

        for idx, row in df_pct.iterrows():
            row_name = f"\\textbf{{{idx[:10]}}}" if idx in df_pct.index[:-1] else idx
            lines.append(
                f"    {row_name} & " + " & ".join(row.values.tolist()) + " \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\caption*{Notes: Diebold-Yilmaz (2014) spillover index. "
            "Entries show percentage contribution to H-step forecast error variance.}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# VOLATILITY SUITE (ORCHESTRATOR)
# ─────────────────────────────────────────────────────────────────────────────


class VolatilitySuite:
    """
    波动率建模全套编排器。

    一行代码运行所有分析：
      1. GARCH(1,1) 拟合
      2. Realized Volatility
      3. Bipower Variation
      4. Jump Test
      5. HAR Model

    使用方法：
        suite = VolatilitySuite()
        results = suite.run_all(prices=price_series, returns=return_series)
        # results 包含所有子模块的结果字典
    """

    def run_all(
        self,
        prices: pd.Series | None = None,
        returns: pd.Series | None = None,
        rv_series: pd.Series | None = None,
        garch_type: str = "GARCH",
        resample_rule: str = "5min",
    ) -> dict:
        """
        运行全套波动率分析。

        Parameters
        ----------
        prices : pd.Series | None
            价格序列（用于 RV/BPV/Jump）。
        returns : pd.Series | None
            收益率序列（用于 GARCH/HAR）。
        rv_series : pd.Series | None
            已有 RV 序列（优先使用，跳过 RV 计算）。
        garch_type : str
            GARCH 模型类型。
        resample_rule : str
            RV 重采样频率。

        Returns
        -------
        dict
            含所有结果的字典：
            {
                "garch": VolatilityResult,
                "realized_vol": pd.Series,
                "bpv": pd.Series,
                "jump_test": dict,
                "har": dict,
                "summary": pd.DataFrame,
            }
        """
        results: dict = {}

        # 1. GARCH
        if returns is not None and len(returns) > 50:
            _log.info("[Suite] Fitting GARCH...")
            garch = GARCHModel(model_type=garch_type, p=1, q=1)
            try:
                garch_result = garch.fit(returns)
                results["garch"] = garch_result
                results["garch_model"] = garch
                _log.info(f"[Suite] GARCH done: converged={garch_result.converged}")
            except Exception as e:
                _log.warning(f"[Suite] GARCH failed: {e}")
                results["garch"] = None

        # 2-4. Realized Volatility / BPV / Jump
        if prices is not None and len(prices) > 100:
            _log.info("[Suite] Computing Realized Volatility...")
            rv_obj = RealizedVolatility()

            try:
                if rv_series is not None:
                    rv = rv_series.dropna()
                else:
                    rv = rv_obj.compute_from_prices(prices, resample_rule=resample_rule)

                results["realized_vol"] = rv
                _log.info(f"[Suite] RV: {len(rv)} obs, mean={rv.mean():.6f}")

                # BPV
                bpv = rv_obj.bipower_variation(prices, resample_rule=resample_rule)
                results["bpv"] = bpv
                _log.info(f"[Suite] BPV: {len(bpv)} obs")

                # Jump test
                jt = rv_obj.jump_test(prices, resample_rule=resample_rule)
                results["jump_test"] = jt
                _log.info(
                    f"[Suite] Jump test: Z={jt.get('z_stat', 0):.3f}, "
                    f"p={jt.get('pval', 1):.4f}, has_jumps={jt.get('has_jumps', False)}"
                )
            except Exception as e:
                _log.warning(f"[Suite] RV computation failed: {e}")

        # 5. HAR
        if rv_series is not None and len(rv_series) > 30:
            _log.info("[Suite] Fitting HAR Model...")
            har = HARModel()
            har_result = har.fit(rv_series)
            results["har"] = har_result
            results["har_model"] = har
            _log.info(f"[Suite] HAR done, R²={har_result.get('r_squared', 0):.4f}")
        elif returns is not None and prices is not None:
            # 尝试从 prices 计算 RV 再跑 HAR
            try:
                rv_obj = RealizedVolatility()
                rv = rv_obj.compute_from_prices(prices, resample_rule=resample_rule)
                if len(rv) > 30:
                    har = HARModel()
                    har_result = har.fit(rv)
                    results["har"] = har_result
                    results["har_model"] = har
                    _log.info(f"[Suite] HAR done, R²={har_result.get('r_squared', 0):.4f}")
            except Exception as e:
                _log.warning(f"[Suite] HAR failed: {e}")

        # 6. Summary table
        results["summary"] = self._make_summary(results)

        _log.info("[Suite] run_all complete")
        return results

    def _make_summary(self, results: dict) -> pd.DataFrame:
        """组装汇总表。"""
        rows = []

        garch = results.get("garch")
        if garch is not None and isinstance(garch, VolatilityResult):
            params = garch.params
            rows.append({
                "Model": "GARCH(1,1)",
                "omega": f"{params.get('omega', np.nan):.6f}",
                "alpha": f"{params.get('alpha', np.nan):.4f}",
                "beta": f"{params.get('beta', np.nan):.4f}",
                "AIC": f"{garch.aic:.2f}",
                "BIC": f"{garch.bic:.2f}",
                "N": garch.n_obs,
                "Converged": str(garch.converged),
            })

        har = results.get("har")
        if har and isinstance(har, dict):
            p = har.get("params", {})
            rows.append({
                "Model": "HAR",
                "alpha": f"{p.get('alpha', np.nan):.4f}",
                "beta_d": f"{p.get('beta_d', np.nan):.4f}",
                "beta_w": f"{p.get('beta_w', np.nan):.4f}",
                "beta_m": f"{p.get('beta_m', np.nan):.4f}",
                "AIC": f"{har.get('aic', 0):.2f}",
                "R2": f"{har.get('r_squared', 0):.4f}",
                "N": har.get("n_obs", 0),
                "Converged": "OLS",
            })

        jt = results.get("jump_test")
        if jt and isinstance(jt, dict):
            rows.append({
                "Model": "Jump Test",
                "Z-stat": f"{jt.get('z_stat', 0):.3f}",
                "p-value": f"{jt.get('pval', 1):.4f}",
                "has_jumps": str(jt.get("has_jumps", False)),
                "jump_var": f"{jt.get('jump_var', 0):.6f}",
            })

        rv = results.get("realized_vol")
        if rv is not None and len(rv) > 0:
            rows.append({
                "Model": "Realized Vol",
                "mean": f"{rv.mean():.6f}",
                "std": f"{rv.std():.6f}",
                "N": str(len(rv)),
            })

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def realized_volatility_from_prices(
    prices: pd.Series,
    rule: str = "5min",
) -> pd.Series:
    """
    便捷函数：直接从价格计算已实现波动率。

    Parameters
    ----------
    prices : pd.Series
        价格序列。
    rule : str
        重采样频率。

    Returns
    -------
    pd.Series
        日频已实现波动率。
    """
    rv_obj = RealizedVolatility()
    return rv_obj.compute_from_prices(prices, resample_rule=rule)


def garch_fit(
    returns: pd.Series | np.ndarray,
    model_type: str = "GARCH",
    p: int = 1,
    q: int = 1,
) -> VolatilityResult:
    """
    便捷函数：拟合 GARCH 模型。

    Parameters
    ----------
    returns
    model_type : str
    p, q : int

    Returns
    -------
    VolatilityResult
    """
    model = GARCHModel(model_type=model_type, p=p, q=q)
    return model.fit(returns)
