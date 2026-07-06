"""经济金融领域高级敏感性分析模块。

本模块封装以下估计器：
  1. OLSPLSSensitivity — Eberstein-Magnac (1991) OLS vs PLS 敏感性分析
  2. OlleyPakesEstimator — Olley-Pakes (1996) 半参数生产率分解
  3. LevinsohnPetrinEstimator — Levinsohn-Petrin (2003) 半参数生产率估计
  4. ContagionTest — Forbes-Rigobon (2002) 金融危机传染检验
  5. CreditRiskSensitivity — 信用风险敏感性分析与压力测试
  6. SpilloverIndex — Diebold-Yilmaz (2014) 波动率溢出指数

Usage:
    # OLS-PLS 敏感性
    sen = OLSPLSSensitivity()
    result = sen.fit(X, y, key_var=0)

    # OP 生产率分解
    op = OlleyPakesEstimator()
    res = op.fit(df, investment="inv", labor="emp", capital="k", output="va")

    # 传染检验
    ct = ContagionTest()
    res = ct.fit(returns, crisis_period=(100, 150), pre_period=(0, 99))

    # 信用风险
    cr = CreditRiskSensitivity()
    res = cr.fit(df, default_var="default", macro_vars=["gdp_growth", "rate"])

    # 溢出指数
    si = SpilloverIndex()
    res = si.fit(returns, n_lags=4, window=120)
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
    "OLSPLSSensitivity",
    "EbersteinMagnacResult",
    "OlleyPakesEstimator",
    "LevinsohnPetrinEstimator",
    "ContagionTest",
    "SpilloverIndex",
    "CreditRiskSensitivity",
]

_log = logging.getLogger("finance_sensitivity")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# EBERSTEIN-MAGNAC RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class EbersteinMagnacResult:
    """
    Eberstein-Magnac (1991) OLS-PLS 敏感性分析结果容器。

    Attributes
    ----------
    coef_ols : float
        OLS 基准系数。
    se_ols : float
        OLS 标准误。
    pls_coefs : dict[int, float]
        各成分数下的 PLS 系数 {n_components: coef}。
    reliability_ratio : float
        可靠性比率 = |beta_OLS| / max|beta_PLS(r) - beta_OLS|。
    credible_interval : tuple[float, float]
        95% 可信区间 [lower, upper]。
    is_robust : bool
        可靠性比率 > 0.8 时为 True。
    key_var_name : str
        关键变量名。
    all_coefs : pd.DataFrame
        所有估计系数的 DataFrame。
    """

    coef_ols: float
    se_ols: float
    pls_coefs: dict[int, float]
    reliability_ratio: float
    credible_interval: tuple[float, float]
    is_robust: bool
    key_var_name: str
    all_coefs: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def sig(self) -> str:
        if self.se_ols == 0:
            return ""
        from scipy import stats
        t = abs(self.coef_ols) / self.se_ols
        p = 2 * (1 - stats.t.cdf(t, df=1000))
        if p < 0.001:
            return "***"
        elif p < 0.01:
            return "**"
        elif p < 0.05:
            return "*"
        elif p < 0.10:
            return r"$\dagger$"
        return ""

    def to_dict(self) -> dict:
        return {
            "coef_ols": self.coef_ols,
            "se_ols": self.se_ols,
            "reliability_ratio": self.reliability_ratio,
            "credible_interval_lower": self.credible_interval[0],
            "credible_interval_upper": self.credible_interval[1],
            "is_robust": self.is_robust,
            "key_var": self.key_var_name,
            "sig": self.sig,
        }


# ─────────────────────────────────────────────────────────────────────────────
# OLS-PLS SENSITIVITY (Eberstein-Magnac 1991)
# ─────────────────────────────────────────────────────────────────────────────


class OLSPLSSensitivity:
    """OLS vs PLS（主成分回归）敏感性分析。

    当存在测量误差或遗漏变量时，OLS 和 PLS（主成分）给出系数边界。
    PLS 通过降维减少测量误差效应。
    两者的差距给出了一个敏感性范围。

    Reference
    ---------
    Eberstein, M. & Magnac, T. (1991). "A sensitivity analysis of the effect
    of measurement error on the estimates of a model with intercorrelated
    regressors."
    """

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        xnames: list[str] | None = None,
        key_var: int = 0,
        n_components: int | list[int] | None = None,
    ) -> EbersteinMagnacResult:
        """
        Eberstein-Magnac (1991) OLS-PLS 敏感性分析。

        1. OLS 基准回归 → beta_OLS
        2. PLS 回归（不同成分数 r = 1, 2, ..., k-1）→ beta_PLS(r)
        3. 可信区间 = [min(beta_PLS), max(beta_PLS)]
        4. 可靠性比率 = |beta_OLS| / max|beta_PLS(r) - beta_OLS|

        当可靠性比率 > 0.8 时，结果被认为稳健。

        Parameters
        ----------
        X : np.ndarray
            自变量矩阵 (n_obs, n_vars)。
        y : np.ndarray
            因变量向量 (n_obs,)。
        xnames : list[str] | None
            变量名列表。
        key_var : int
            关键变量的列索引。
        n_components : int | list[int] | None
            PLS 成分数，默认 1..(k-1)。

        Returns
        -------
        EbersteinMagnacResult
        """
        try:
            import statsmodels.api as sm
            from sklearn.cross_decomposition import PLSRegression
            from sklearn.preprocessing import StandardScaler
        except ImportError as e:
            _log.error(f"[OLSPLSSensitivity] Required package missing: {e}")
            return self._empty_result(key_var, xnames)

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)

        n_obs, n_vars = X.shape
        if xnames is None:
            xnames = [f"x{i}" for i in range(n_vars)]
        if n_obs < n_vars + 5:
            _log.warning(
                f"[OLSPLSSensitivity] n_obs={n_obs} < n_vars+5={n_vars+5}, results may be unreliable"
            )

        # 1. OLS 基准
        X_ols = sm.add_constant(X)
        try:
            model_ols = sm.OLS(y, X_ols).fit()
        except Exception as e:
            _log.error(f"[OLSPLSSensitivity] OLS failed: {e}")
            return self._empty_result(key_var, xnames)

        coef_ols = float(model_ols.params[key_var + 1])  # +1 for constant
        se_ols = float(model_ols.bse[key_var + 1])
        key_var_name = xnames[key_var] if key_var < len(xnames) else f"x{key_var}"

        # 2. PLS 回归（不同成分数）
        if n_components is None:
            max_comp = max(1, n_vars - 1)
            component_range = list(range(1, max_comp + 1))
        elif isinstance(n_components, int):
            component_range = [n_components]
        else:
            component_range = list(n_components)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        pls_coefs: dict[int, float] = {}
        all_rows = [{"method": "OLS", key_var_name: coef_ols, "SE": se_ols}]

        for r in component_range:
            if r >= n_vars:
                continue
            try:
                pls = PLSRegression(n_components=r)
                pls.fit(X_scaled, y)
                # PLS coef in original scale
                coef_scaled = pls.coef_.ravel()
                coef_raw = coef_scaled[key_var] / scaler.scale_[key_var]
                pls_coefs[r] = float(coef_raw)
                all_rows.append({
                    "method": f"PLS(r={r})",
                    key_var_name: float(coef_raw),
                    "SE": np.nan,
                })
            except Exception as e:
                _log.warning(f"[OLSPLSSensitivity] PLS(r={r}) failed: {e}")
                continue

        # 3. 可信区间
        if pls_coefs:
            pls_values = list(pls_coefs.values())
            ci_lower = min(coef_ols, min(pls_values))
            ci_upper = max(coef_ols, max(pls_values))
        else:
            ci_lower = ci_upper = coef_ols

        # 4. 可靠性比率
        if pls_coefs:
            max_diff = max(abs(v - coef_ols) for v in pls_coefs.values())
        else:
            max_diff = 1.0

        if max_diff > 0:
            reliability_ratio = min(abs(coef_ols) / max_diff, 10.0)
        else:
            reliability_ratio = 10.0 if abs(coef_ols) > 0 else 1.0

        is_robust = reliability_ratio > 0.8

        all_coefs = pd.DataFrame(all_rows)

        _log.info(
            f"[OLSPLSSensitivity] OLS coef={coef_ols:+.4f}, "
            f"reliability_ratio={reliability_ratio:.3f}, robust={is_robust}"
        )

        return EbersteinMagnacResult(
            coef_ols=coef_ols,
            se_ols=se_ols,
            pls_coefs=pls_coefs,
            reliability_ratio=reliability_ratio,
            credible_interval=(ci_lower, ci_upper),
            is_robust=is_robust,
            key_var_name=key_var_name,
            all_coefs=all_coefs,
        )

    def _empty_result(self, key_var: int, xnames: list[str] | None) -> EbersteinMagnacResult:
        name = xnames[key_var] if xnames and key_var < len(xnames) else f"x{key_var}"
        return EbersteinMagnacResult(
            coef_ols=np.nan,
            se_ols=np.nan,
            pls_coefs={},
            reliability_ratio=np.nan,
            credible_interval=(np.nan, np.nan),
            is_robust=False,
            key_var_name=name,
        )


# ─────────────────────────────────────────────────────────────────────────────
# OLLEY-PAKES ESTIMATOR (1996)
# ─────────────────────────────────────────────────────────────────────────────


class OlleyPakesEstimator:
    """Olley-Pakes (1996) 半参数生产率分解。

    全要素生产率 (TFP) 分解为：
      - OP生产率（由投资决定的内生选择）
      - 组内效应（企业间TFP差异）
      - 组间效应（产业结构变化）

    常用于：企业面板数据分析（工业企业数据库、中国统计年鉴）

    Reference
    ---------
    Olley, G. S. & Pakes, A. (1996). "The Dynamics of Productivity in the
    Telecommunications Equipment Industry." Econometrica.
    """

    def fit(
        self,
        df: pd.DataFrame,
        investment: str = "investment",
        labor: str = "labor",
        capital: str = "capital",
        output: str = "value_added",
        entity_var: str = "firm_id",
        time_var: str = "year",
        min_obs: int = 3,
    ) -> dict:
        """
        Olley-Pakes 半参数两步法。

        第一步（investment demand）：
            log I_it = phi(log K_it) + chi_t
            用多项式近似 phi(·)，估计 chi_hat_t（时间效应代理）

        第二步（productivity equation）：
            log Y_it = beta_l log L_it + beta_k log K_it + omega_it + epsilon_it
            其中 omega_it = E[omega_it | omega_{it-1}] + xi_it（semi-martingale）
            用投资 I_{it} 作为 omega_{it} 的代理

        分解：
            TFP = mean(omega_hat_it) + (firm_effect) + (selection_term)

        Parameters
        ----------
        df : pd.DataFrame
            企业面板数据。
        investment : str
            投资变量名。
        labor : str
            劳动投入变量名。
        capital : str
            资本存量变量名。
        output : str
            产出/增加值变量名。
        entity_var : str
            企业标识变量名。
        time_var : str
            时间变量名。
        min_obs : int
            企业最小观测数。

        Returns
        -------
        dict
        """
        try:
            import statsmodels.api as sm
        except ImportError:
            _log.error("[OlleyPakes] statsmodels not installed")
            return {"error": "statsmodels required"}

        df = df.copy()

        required = [investment, labor, capital, output, entity_var, time_var]
        for col in required:
            if col not in df.columns:
                _log.error(f"[OlleyPakes] Column '{col}' not found")
                return {"error": f"Column '{col}' not found"}

        # 对数变换
        for col in [investment, labor, capital, output]:
            df[f"ln_{col}"] = np.log(df[col].clip(lower=1e-10))

        # 过滤有效观测
        df = df.dropna(subset=[f"ln_{investment}", f"ln_{labor}",
                                f"ln_{capital}", f"ln_{output}"])

        # 企业内排序
        df = df.sort_values([entity_var, time_var])

        # 过滤最小观测数
        entity_counts = df.groupby(entity_var).size()
        valid_entities = entity_counts[entity_counts >= min_obs].index
        df = df[df[entity_var].isin(valid_entities)]

        if len(df) < 50:
            _log.warning(f"[OlleyPakes] Only {len(df)} obs after filtering")

        n_obs = len(df)
        n_firms = df[entity_var].nunique()

        # ── Step 1: Investment equation ────────────────────────────────
        # phi(K_it) = sum_{j=0}^p a_j * (ln K_it)^j
        # 使用 3 阶多项式
        degree = 3
        ln_cap = df[f"ln_{capital}"].values

        # 构造多项式特征
        poly_features = np.column_stack([ln_cap ** j for j in range(degree + 1)])
        poly_df = pd.DataFrame(
            poly_features,
            columns=[f"poly_{j}" for j in range(degree + 1)],
            index=df.index,
        )

        # 回归 phi(K_it) on poly(K_it) + time dummies
        X1_cols = [f"poly_{j}" for j in range(degree + 1)]
        time_dummies = pd.get_dummies(df[time_var], prefix="t", drop_first=True)
        X1 = pd.concat([poly_df[X1_cols], time_dummies], axis=1)
        y1 = df[f"ln_{investment}"].values

        try:
            model1 = sm.OLS(y1, sm.add_constant(X1.values.astype(float))).fit()
        except Exception as e:
            _log.error(f"[OlleyPakes] Step 1 failed: {e}")
            return {"error": str(e)}

        # 提取时间效应 chi_t
        # params: [const, poly_0..poly_3, time_dummies...]
        time_cols = [c for c in X1.columns if str(c).startswith("t_")]
        time_effects: dict[int, float] = {}
        n_poly = degree + 1
        for i, col in enumerate(time_cols):
            param_idx = 1 + n_poly + i  # skip const (0) + poly
            if param_idx < len(model1.params):
                time_effects[int(str(col).split("_")[1])] = float(model1.params[param_idx])

        # ── Step 2: Productivity equation ──────────────────────────────
        # ln Y_it = beta_l ln L_it + beta_k ln K_it + omega_it + epsilon_it
        # omega_it 由投资代理

        df["omega_it"] = (
            df[f"ln_{investment}"]
            - model1.params[0]  # constant
            - sum(model1.params[j + 1] * (df[f"ln_{capital}"] ** j) for j in range(1, degree + 1))
        )

        # 滞后 omega
        df["omega_lag1"] = df.groupby(entity_var)["omega_it"].shift(1)

        # 当期 omega（用于回归）
        df["omega_current"] = df["omega_it"]

        # 过滤缺失值
        df_step2 = df.dropna(subset=["omega_lag1", f"ln_{labor}", f"ln_{capital}", "omega_current"])

        y2 = df_step2[f"ln_{output}"].values
        X2 = sm.add_constant(
            np.column_stack([
                df_step2[f"ln_{labor}"].values,
                df_step2[f"ln_{capital}"].values,
                df_step2["omega_lag1"].values,
                df_step2["omega_current"].values,
            ])
        )

        try:
            model2 = sm.OLS(y2, X2).fit()
        except Exception as e:
            _log.error(f"[OlleyPakes] Step 2 failed: {e}")
            return {"error": str(e)}

        beta_l = float(model2.params[1])
        beta_k = float(model2.params[2])

        # ── TFP 分解 ──────────────────────────────────────────────────
        # omega_hat = omega_lag1 + selection_term（近似）
        omega_hat = df_step2["omega_lag1"].values + (
            df_step2["omega_current"].values - df_step2["omega_lag1"].values
        ) * 0.5  # 简化的 selection term

        # 组内均值
        firm_omega = pd.Series(omega_hat, index=df_step2.index).groupby(df_step2[entity_var]).mean()

        # 总均值
        mean_omega = np.mean(omega_hat)

        # 组内方差
        within_var = float(np.nanvar(omega_hat - firm_omega.reindex(df_step2[entity_var]).values))

        # 组间方差（产业结构贡献）
        between_var = float(np.nanvar(firm_omega.values))

        # Olley-Pakes 协方差分解
        total_var = within_var + between_var
        op_cov = float(
            np.nanmean(
                (firm_omega.reindex(df_step2[entity_var]).values - mean_omega)
                * (omega_hat - mean_omega)
            )
        )

        # TFP 分布
        tfp_series = pd.Series(omega_hat, index=df_step2.index)
        tfp_p25 = float(tfp_series.quantile(0.25))
        tfp_p50 = float(tfp_series.median())
        tfp_p75 = float(tfp_series.quantile(0.75))

        result = {
            "beta_labor": beta_l,
            "beta_capital": beta_k,
            "step1_time_effects": time_effects,
            "n_obs": n_obs,
            "n_firms": n_firms,
            "n_periods": int(df[time_var].nunique()),
            "tfp": {
                "mean": float(mean_omega),
                "within_var": within_var,
                "between_var": between_var,
                "total_var": total_var,
                "op_covariance": op_cov,
                "p25": tfp_p25,
                "p50": tfp_p50,
                "p75": tfp_p75,
            },
            "tfp_series": tfp_series,
            "firm_tfp": firm_omega,
            "r_squared_step2": float(model2.rsquared),
            "note": (
                "Olley-Pakes decomposition: TFP = mean(omega) + "
                "within-firm + between-firm + selection"
            ),
        }

        _log.info(
            f"[OlleyPakes] beta_l={beta_l:.3f}, beta_k={beta_k:.3f}, "
            f"n_firms={n_firms}, op_cov={op_cov:.4f}"
        )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# LEVINSOHN-PETRIN ESTIMATOR (2003)
# ─────────────────────────────────────────────────────────────────────────────


class LevinsohnPetrinEstimator:
    """Levinsohn-Petrin (2003) 半参数生产率估计。

    与 OP 的区别：用中间投入 M_it 代替投资 I_it 作为生产率代理。
    优势：当企业有零投资时仍然可用。

    Reference
    ---------
    Levinsohn, J. & Petrin, A. (2003). "Estimating Production Functions Using
    Inputs to Control for Unobservables." REStud.
    """

    def fit(
        self,
        df: pd.DataFrame,
        intermediate_input: str = "intermediate",
        labor: str = "labor",
        capital: str = "capital",
        output: str = "value_added",
        entity_var: str = "firm_id",
        time_var: str = "year",
        min_obs: int = 3,
    ) -> dict:
        """
        Levinsohn-Petrin 半参数两步法。

        与 Olley-Pakes 类似，但使用中间投入（原材料、电力等）代替投资。
        适用于零投资企业。

        Parameters
        ----------
        df : pd.DataFrame
            企业面板数据。
        intermediate_input : str
            中间投入变量名。
        labor : str
            劳动投入变量名。
        capital : str
            资本存量变量名。
        output : str
            产出/增加值变量名。
        entity_var : str
            企业标识变量名。
        time_var : str
            时间变量名。
        min_obs : int
            企业最小观测数。

        Returns
        -------
        dict
        """
        try:
            import statsmodels.api as sm
        except ImportError:
            _log.error("[LevinsohnPetrin] statsmodels not installed")
            return {"error": "statsmodels required"}

        df = df.copy()

        required = [intermediate_input, labor, capital, output, entity_var, time_var]
        for col in required:
            if col not in df.columns:
                _log.error(f"[LevinsohnPetrin] Column '{col}' not found")
                return {"error": f"Column '{col}' not found"}

        # 对数变换
        log_vars = [intermediate_input, labor, capital, output]
        for col in log_vars:
            df[f"ln_{col}"] = np.log(df[col].clip(lower=1e-10))

        # 过滤有效观测
        df = df.dropna(subset=[f"ln_{intermediate_input}", f"ln_{labor}",
                                f"ln_{capital}", f"ln_{output}"])

        df = df.sort_values([entity_var, time_var])

        entity_counts = df.groupby(entity_var).size()
        valid_entities = entity_counts[entity_counts >= min_obs].index
        df = df[df[entity_var].isin(valid_entities)]

        n_obs = len(df)
        n_firms = df[entity_var].nunique()

        # ── Step 1: Intermediate input demand ─────────────────────────
        # ln M_it = phi(ln K_it) + chi_t
        degree = 3
        ln_cap = df[f"ln_{capital}"].values

        poly_features = np.column_stack([ln_cap ** j for j in range(degree + 1)])
        time_dummies = pd.get_dummies(df[time_var], prefix="t", drop_first=True)

        X1 = pd.concat([
            pd.DataFrame(poly_features, index=df.index),
            time_dummies,
        ], axis=1)

        y1 = df[f"ln_{intermediate_input}"].values

        try:
            model1 = sm.OLS(y1, sm.add_constant(X1.values.astype(float))).fit()
        except Exception as e:
            _log.error(f"[LevinsohnPetrin] Step 1 failed: {e}")
            return {"error": str(e)}

        time_effects: dict[int, float] = {}
        n_poly = degree + 1
        time_cols = [c for c in X1.columns if str(c).startswith("t_")]
        for i, col in enumerate(time_cols):
            param_idx = 1 + n_poly + i
            if param_idx < len(model1.params):
                time_effects[int(str(col).split("_")[1])] = float(model1.params[param_idx])

        # ── Step 2: Productivity equation ──────────────────────────────
        # omega_hat from intermediate input proxy
        df["omega_it"] = (
            df[f"ln_{intermediate_input}"]
            - model1.params[0]
            - sum(model1.params[j + 1] * (df[f"ln_{capital}"] ** j) for j in range(1, degree + 1))
        )

        df["omega_lag1"] = df.groupby(entity_var)["omega_it"].shift(1)
        df["omega_current"] = df["omega_it"]

        df_step2 = df.dropna(subset=["omega_lag1", f"ln_{labor}", f"ln_{capital}", "omega_current"])

        y2 = df_step2[f"ln_{output}"].values
        X2 = sm.add_constant(
            np.column_stack([
                df_step2[f"ln_{labor}"].values,
                df_step2[f"ln_{capital}"].values,
                df_step2["omega_lag1"].values,
                df_step2["omega_current"].values,
            ])
        )

        try:
            model2 = sm.OLS(y2, X2).fit()
        except Exception as e:
            _log.error(f"[LevinsohnPetrin] Step 2 failed: {e}")
            return {"error": str(e)}

        beta_l = float(model2.params[1])
        beta_k = float(model2.params[2])

        omega_hat = df_step2["omega_lag1"].values + (
            df_step2["omega_current"].values - df_step2["omega_lag1"].values
        ) * 0.5

        firm_omega = pd.Series(omega_hat, index=df_step2.index).groupby(df_step2[entity_var]).mean()
        mean_omega = np.mean(omega_hat)
        within_var = float(np.nanvar(omega_hat - firm_omega.reindex(df_step2[entity_var]).values))
        between_var = float(np.nanvar(firm_omega.values))

        tfp_series = pd.Series(omega_hat, index=df_step2.index)

        result = {
            "beta_labor": beta_l,
            "beta_capital": beta_k,
            "step1_time_effects": time_effects,
            "n_obs": n_obs,
            "n_firms": n_firms,
            "n_periods": int(df[time_var].nunique()),
            "tfp": {
                "mean": float(mean_omega),
                "within_var": within_var,
                "between_var": between_var,
                "total_var": within_var + between_var,
                "p25": float(tfp_series.quantile(0.25)),
                "p50": float(tfp_series.median()),
                "p75": float(tfp_series.quantile(0.75)),
            },
            "tfp_series": tfp_series,
            "firm_tfp": firm_omega,
            "r_squared_step2": float(model2.rsquared),
            "note": "LP uses intermediate input as productivity proxy (vs investment in OP)",
        }

        _log.info(
            f"[LevinsohnPetrin] beta_l={beta_l:.3f}, beta_k={beta_k:.3f}, "
            f"n_firms={n_firms}"
        )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# CONTAGION TEST (Forbes-Rigobon 2002)
# ─────────────────────────────────────────────────────────────────────────────


class ContagionTest:
    """金融危机传染效应检验。

    检验一个市场的危机是否"传染"到其他市场。

    Reference
    ---------
    Forbes, K. & Rigobon, R. (2002). "No Contagion, Only Interdependence."
    Journal of Finance.
    """

    def fit(
        self,
        returns: np.ndarray,
        crisis_period: tuple[int, int],
        pre_period: tuple[int, int],
        test_type: str = "forbes_rigobon",
    ) -> dict:
        """
        Forbes-Rigobon (2002) 传染检验。

        1. 相关性断点检验（相关性是否在危机期间显著上升？）
        2. 条件相关性与无条件相关性比较（Forbes-Rigobon 调整）
        3. 溢出指数（见 SpilloverIndex）

        Parameters
        ----------
        returns : np.ndarray
            收益率矩阵 (T, n)，n 个市场。
        crisis_period : tuple[int, int]
            危机期间（start, end）索引。
        pre_period : tuple[int, int]
            危机前（start, end）索引。
        test_type : str
            "forbes_rigobon"（默认）或 "simple"。

        Returns
        -------
        dict
        """
        from scipy import stats

        returns = np.asarray(returns, dtype=float)
        T, n = returns.shape

        cs, ce = crisis_period
        ps, pe = pre_period

        if cs < 0 or ce > T or ps < 0 or pe > T:
            _log.error("[ContagionTest] Period indices out of bounds")
            return {"error": "Invalid period indices"}

        returns_crisis = returns[cs:ce]
        returns_pre = returns[ps:pe]

        # 无条件相关系数矩阵（全样本）
        unconditional_corr = np.corrcoef(returns.T)

        # 危机期间相关系数矩阵
        crisis_corr = np.corrcoef(returns_crisis.T) if len(returns_crisis) > n else None

        # 危机前相关系数矩阵
        pre_corr = np.corrcoef(returns_pre.T) if len(returns_pre) > n else None

        if crisis_corr is None or pre_corr is None:
            return {
                "error": "Insufficient observations for correlation estimation",
                "n_crisis": len(returns_crisis),
                "n_pre": len(returns_pre),
            }

        # Forbes-Rigobon 调整
        # 调整后的相关系数 rho_adj = rho_full / sqrt(var_crise / var_full)
        var_full = np.var(returns, axis=0)
        var_crisis = np.var(returns_crisis, axis=0)
        var_ratio = np.sqrt(var_crisis / var_full)
        var_ratio = np.clip(var_ratio, 0.01, 10.0)

        # 调整公式：对角线外的元素
        fr_adjusted_corr = unconditional_corr.copy()
        for i in range(n):
            for j in range(n):
                if i != j:
                    adj = unconditional_corr[i, j] / np.sqrt(var_ratio[i] * var_ratio[j])
                    fr_adjusted_corr[i, j] = np.clip(adj, -1.0, 1.0)

        # 传染统计量：危机期 vs 危机前的相关系数差异
        corr_diff = crisis_corr - pre_corr
        # 统计量：max|corr_diff|（或均值）
        contagion_stat = float(np.nanmax(np.abs(corr_diff - np.diag(np.diag(corr_diff)))))

        # Bootstrap p 值
        B = 999
        rng = np.random.default_rng(42)
        boot_stats = []

        combined = np.vstack([returns_pre, returns_crisis])
        for _ in range(B):
            idx = rng.integers(0, len(combined), size=len(combined))
            boot_sample = combined[idx]
            boot_pre = boot_sample[:len(returns_pre)]
            boot_crisis = boot_sample[len(returns_pre):]

            if len(boot_crisis) > n and len(boot_pre) > n:
                boot_corr_crisis = np.corrcoef(boot_crisis.T)
                boot_corr_pre = np.corrcoef(boot_pre.T)
                boot_diff = boot_corr_crisis - boot_corr_pre
                boot_max = float(np.nanmax(np.abs(boot_diff - np.diag(np.diag(boot_diff)))))
                boot_stats.append(boot_max)

        boot_stats = np.array(boot_stats)
        pval = float(np.mean(boot_stats >= contagion_stat)) if len(boot_stats) > 0 else np.nan

        # 结论
        if pval < 0.05 and contagion_stat > 0.1:
            conclusion = "Contagion detected"
        elif pval > 0.10:
            conclusion = "No contagion"
        else:
            conclusion = "Inconclusive"

        result = {
            "unconditional_corr": unconditional_corr,
            "crisis_corr": crisis_corr,
            "pre_corr": pre_corr,
            "fr_adjusted_corr": fr_adjusted_corr,
            "corr_diff": corr_diff,
            "contagion_stat": contagion_stat,
            "pval": pval,
            "conclusion": conclusion,
            "n_crisis": len(returns_crisis),
            "n_pre": len(returns_pre),
            "n_markets": n,
        }

        _log.info(
            f"[ContagionTest] contagion_stat={contagion_stat:.4f}, "
            f"p={pval:.3f}, {conclusion}"
        )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# SPILLOVER INDEX (Diebold-Yilmaz 2014)
# ─────────────────────────────────────────────────────────────────────────────


class SpilloverIndex:
    """Diebold-Yilmaz (2014) 波动率溢出指数。

    衡量金融市场中不同市场/行业之间的波动率溢出程度。

    Reference
    ---------
    Diebold, F. X. & Yilmaz, K. (2014). "On the Network Topology of
    Variance Decompositions." J Econometrics.
    """

    def fit(
        self,
        returns: np.ndarray,
        n_lags: int = 4,
        window: int = 120,
    ) -> dict:
        """
        Diebold-Yilmaz 波动率溢出指数。

        方法：
          1. 用 VAR(p) 分解方差
          2. 计算来自其他市场的方差贡献比例
          3. 溢出指数 = 外部贡献 / 总方差 * 100

        Parameters
        ----------
        returns : np.ndarray
            收益率矩阵 (T, n)，n 个市场/资产。
        n_lags : int
            VAR 滞后阶数（默认 4）。
        window : int
            滚动窗口大小（默认 120 天）。

        Returns
        -------
        dict
        """
        returns = np.asarray(returns, dtype=float)
        T, n = returns.shape

        if T < window + n_lags + 10:
            _log.warning(
                f"[SpilloverIndex] T={T} < window+lags={window+n_lags}, results may be unreliable"
            )

        try:
            from statsmodels.tsa.api import VAR
        except ImportError:
            _log.error("[SpilloverIndex] statsmodels.tsa.api.VAR not available")
            return {"error": "statsmodels VAR required"}

        # 用对数收益率的平方作为波动率代理
        vol = np.abs(returns) ** 2

        # 滚动窗口 VAR 估计
        spillover_tables = []
        total_indices = []
        directional_from_list = []
        directional_to_list = []

        for start in range(0, T - window, 10):  # 每 10 天滚动一次
            end = start + window
            vol_win = vol[start:end]

            try:
                model = VAR(vol_win)
                results = model.fit(maxlags=n_lags, ic=None)
                results.irf(periods=10)

                # 方差分解（10 步ahead）
                fevd = results.fevd(periods=10)
                # fevd.decomp[i, j, k] = 市场 i 的 j 步预测误差方差中，来自市场 k 的比例
                decomp = fevd.decomp  # shape: (n, n, n)

                # 溢出贡献矩阵
                spillover_contrib = np.zeros((n, n))
                for i in range(n):
                    for j in range(n):
                        spillover_contrib[i, j] = float(np.mean(decomp[i, :, j]))

                # 总溢出指数
                total_spillover = (
                    100
                    * (np.sum(spillover_contrib) - np.trace(spillover_contrib))
                    / np.sum(spillover_contrib)
                    * n
                    / (n - 1)
                )

                # 方向性溢出（From）
                directional_from = 100 * (np.sum(spillover_contrib, axis=1) - np.diag(spillover_contrib)) / np.sum(spillover_contrib)

                # 方向性溢出（To）
                directional_to = 100 * (np.sum(spillover_contrib, axis=0) - np.diag(spillover_contrib)) / np.sum(spillover_contrib)

                # 净溢出
                directional_from - directional_to

                spillover_tables.append(spillover_contrib)
                total_indices.append(total_spillover)
                directional_from_list.append(directional_from)
                directional_to_list.append(directional_to)

            except Exception as e:
                _log.warning(f"[SpilloverIndex] Rolling window {start}:{end} failed: {e}")
                continue

        if not spillover_tables:
            return {"error": "No valid rolling windows"}

        # 平均值
        avg_spillover = np.mean(spillover_tables, axis=0)
        avg_total = float(np.mean(total_indices))
        avg_from = np.mean(directional_from_list, axis=0)
        avg_to = np.mean(directional_to_list, axis=0)
        avg_net = avg_from - avg_to

        # 构建表格
        spillover_df = pd.DataFrame(
            avg_spillover,
            index=[f"M{i}" for i in range(n)],
            columns=[f"M{i}" for i in range(n)],
        )
        spillover_df["From others"] = avg_from
        spillover_df.index = [f"M{i}" for i in range(n)]

        result = {
            "spillover_table": spillover_df,
            "total_spillover_index": avg_total,
            "directional_spillover_from": avg_from,
            "directional_spillover_to": avg_to,
            "net_spillover": avg_net,
            "n_markets": n,
            "window": window,
            "n_lags": n_lags,
            "n_windows": len(spillover_tables),
            "time_series_total": total_indices,
        }

        _log.info(
            f"[SpilloverIndex] total_spillover={avg_total:.1f}%, "
            f"n_markets={n}, n_windows={len(spillover_tables)}"
        )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# CREDIT RISK SENSITIVITY
# ─────────────────────────────────────────────────────────────────────────────


class CreditRiskSensitivity:
    """信用风险敏感性与宏观因素检验。

    检验：
      1. Z-score 财务困境概率
      2. 宏观因素（GDP增速、利率、信用利差）对违约率的敏感性
      3. 压力测试：极端情景下的违约率预测

    Reference
    ---------
    Altman, E. (1968). "Financial Ratios... Z-score."
    Merton, R. (1974). "On the Pricing of Corporate Debt."
    """

    def fit(
        self,
        df: pd.DataFrame,
        default_var: str = "default",
        macro_vars: list[str] | None = None,
        firm_vars: list[str] | None = None,
        method: str = "probit",
    ) -> dict:
        """
        信用风险敏感性分析。

        - Z-score = (ROA + equity/assets) / sigma_ROA
        - Merton DD = (ln(V/A) + (r + 0.5 sigma^2)T) / (sigma V sqrt(T))
        - Probit default probability

        Parameters
        ----------
        df : pd.DataFrame
            企业面板数据。
        default_var : str
            违约指示变量名（0/1）。
        macro_vars : list[str] | None
            宏观变量列表（如 ["gdp_growth", "interest_rate"]）。
        firm_vars : list[str]
            企业特征变量列表。
        method : str
            "probit"（默认）或 "logit"。

        Returns
        -------
        dict
        """
        try:
            import statsmodels.api as sm
            from scipy import stats as scipy_stats
        except ImportError:
            _log.error("[CreditRiskSensitivity] Required package missing")
            return {"error": "statsmodels or scipy required"}

        df = df.copy()

        if firm_vars is None:
            firm_vars = ["roa", "leverage", "size", "tangibility"]

        if macro_vars is None:
            macro_vars = []

        # ── Z-score ────────────────────────────────────────────────────
        if "roa" in df.columns:
            roa = df["roa"].values
            roa_std = float(np.nanstd(roa))
            if roa_std > 0:
                df["z_score"] = (roa + df.get("equity_ratio", 0)) / roa_std
            else:
                df["z_score"] = 3.0  # fallback

        # ── Merton Default Distance ─────────────────────────────────────
        if all(k in df.columns for k in ["total_assets", "market_cap", "debt"]):
            V = np.clip(df["total_assets"].values, a_min=1e-10, a_max=None)
            D = np.clip(df["debt"].values, a_min=1e-10, a_max=None)
            sigma_V = df.get("asset_volatility", pd.Series(np.ones(len(df)) * 0.2)).values

            r = 0.05  # 无风险利率假设
            T = 1.0

            df["merton_dd"] = (
                np.log(V / D) + (r + 0.5 * sigma_V**2) * T
            ) / (sigma_V * np.sqrt(T))

        # ── 分布统计 ───────────────────────────────────────────────────
        zscore_series = df["z_score"].dropna() if "z_score" in df.columns else pd.Series()
        dd_series = df["merton_dd"].dropna() if "merton_dd" in df.columns else pd.Series()

        zscore_dist = {
            "mean": float(zscore_series.mean()) if len(zscore_series) > 0 else np.nan,
            "std": float(zscore_series.std()) if len(zscore_series) > 0 else np.nan,
            "p25": float(zscore_series.quantile(0.25)) if len(zscore_series) > 0 else np.nan,
            "p50": float(zscore_series.median()) if len(zscore_series) > 0 else np.nan,
            "p75": float(zscore_series.quantile(0.75)) if len(zscore_series) > 0 else np.nan,
        }

        dd_dist = {
            "mean": float(dd_series.mean()) if len(dd_series) > 0 else np.nan,
            "std": float(dd_series.std()) if len(dd_series) > 0 else np.nan,
            "p25": float(dd_series.quantile(0.25)) if len(dd_series) > 0 else np.nan,
            "p50": float(dd_series.median()) if len(dd_series) > 0 else np.nan,
            "p75": float(dd_series.quantile(0.75)) if len(dd_series) > 0 else np.nan,
        }

        # ── Probit / Logit 回归 ─────────────────────────────────────────
        all_vars = firm_vars + macro_vars
        available_vars = [v for v in all_vars if v in df.columns]

        reg_df = df.dropna(subset=[default_var] + available_vars)
        y = reg_df[default_var].values.astype(int)
        X_raw = reg_df[available_vars].values.astype(float)

        if len(reg_df) < 30 or X_raw.shape[1] < 1:
            return {
                "error": "Insufficient data for regression",
                "zscore_distribution": zscore_dist,
                "dd_distribution": dd_dist,
            }

        X = sm.add_constant(X_raw)
        xnames = ["const"] + available_vars

        try:
            if method == "probit":
                model = sm.Probit(y, X).fit(disp=False)
            else:
                model = sm.Logit(y, X).fit(disp=False, method="bfgs")
        except Exception as e:
            _log.error(f"[CreditRiskSensitivity] {method} failed: {e}")
            return {"error": str(e)}

        # 边际效应
        from scipy.stats import norm
        z = model.params @ X.T
        if method == "probit":
            pdf_phi = norm.pdf(z)
        else:
            pdf_phi = np.exp(z) / (1 + np.exp(z)) ** 2

        model.predict(X)
        marginal_effects = {}
        for i, name in enumerate(xnames):
            me = float(np.mean(pdf_phi * model.params[i]))
            marginal_effects[name] = me

        # 宏观敏感性
        macro_sensitivity = {
            v: marginal_effects.get(v, 0.0)
            for v in macro_vars
            if v in available_vars
        }

        # ── 压力测试 ───────────────────────────────────────────────────
        stress_test = {}
        if "gdp_growth" in available_vars:
            gdp_mean = float(reg_df["gdp_growth"].mean())
            gdp_std = float(reg_df["gdp_growth"].std())

            for scenario, gdp_shock in [("mild_recession", gdp_mean - gdp_std),
                                         ("severe_recession", gdp_mean - 2 * gdp_std),
                                         ("baseline", gdp_mean)]:
                # 模拟 GDP 冲击下的违约率
                x_stress = X.copy()
                gdp_idx = available_vars.index("gdp_growth") + 1
                x_stress[:, gdp_idx] = gdp_shock

                pred_prob = model.predict(x_stress)
                stress_test[scenario] = {
                    "gdp_assumption": gdp_shock,
                    "predicted_default_rate": float(np.mean(pred_prob)),
                    "p25_default_rate": float(np.percentile(pred_prob, 25)),
                    "p75_default_rate": float(np.percentile(pred_prob, 75)),
                }

        # ── 基准违约率 ─────────────────────────────────────────────────
        base_default_rate = float(np.mean(y))

        result = {
            "method": method,
            "n_obs": len(reg_df),
            "n_default": int(np.sum(y)),
            "base_default_rate": base_default_rate,
            "coefficients": dict(zip(xnames, model.params.tolist())),
            "marginal_effects": marginal_effects,
            "zscore_distribution": zscore_dist,
            "dd_distribution": dd_dist,
            "macro_sensitivity": macro_sensitivity,
            "stress_test": stress_test,
            "pseudo_r_squared": float(getattr(model, "prsquared", np.nan)),
            "aic": float(getattr(model, "aic", np.nan)),
            "bic": float(getattr(model, "bic", np.nan)),
        }

        _log.info(
            f"[CreditRiskSensitivity] n={len(reg_df)}, "
            f"default_rate={base_default_rate:.3f}, method={method}"
        )

        return result
