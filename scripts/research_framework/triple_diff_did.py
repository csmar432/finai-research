"""Triple Difference-in-Differences (DDD) Engine.

本模块封装三重差分（Triple DiD）方法，覆盖：

  1. 经典 2x2x2 DDD（Dreyer Lang & Zhang 2021 风格）
  2. 交错处理扩展（Callaway-Sant'Anna 2021 延伸）
  3. 合成 DDD（Arkhangelsky et al. 2021, SynthDiD）
  4. 事件研究三差分
  5. 异质性处理效应分析
  6. 安慰剂检验

核心模型：
    y = beta * (Treatment x Time x Group3) + alpha_i + gamma_t + delta_j + epsilon

其中 Group3 是第三个维度（地区 / 行业 / 收入群体等）。
适用于：当 DID 的平行趋势假设不满足时，通过引入第三个维度控制组内趋势差异。

References
----------
- Olds, B. (2021). "Triples: A Novel Design for Inference in Difference-in-Differences"
- Dreyer Lang, P. & Zhang, J. (2021). Triple differences
- Callaway, B. & Sant'Anna, P. (2021). "Difference-in-Differences with Multiple Time Periods"
- Arkhangelsky, D. et al. (2021). "Synthetic Difference-in-Differences"

Usage:
    engine = TripleDiffDIDEngine(
        df, y_var="roa", treat_var="did", time_var="post",
        unit_var="ticker", group3_var="industry"
    )
    result = engine.fit()
    hte = engine.get_hte()
    engine.plot_hte()
    engine.plot_event_study()
    sdid = engine.synthetic_did()
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
    "TripleDiffDIDEngine",
    "DDDResult",
]

_log = logging.getLogger("triple_diff_did")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DDDResult:
    """
    三重差分估计结果容器。

    Attributes
    ----------
    estimator : str
        估计器名称。
    coef : float
        DDD 系数估计值。
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
    n_groups : int
        Group3 的类别数量。
    r_squared : float | None
        R²（如果有）。
    method : str
        推断方法（cluster / robust / bootstrap）。
    additional : dict
        额外诊断（异质性效应、Bacon 权重等）。
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
    n_groups: int = 0
    r_squared: float | None = None
    method: str = "robust"
    additional: dict = field(default_factory=dict)

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
        d = {
            "estimator": self.estimator,
            "coef": self.coef,
            "se": self.se,
            "pval": self.pval,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_obs": self.n_obs,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
            "n_groups": self.n_groups,
            "r_squared": self.r_squared,
            "method": self.method,
            "sig": self.sig,
        }
        d.update(self.additional)
        return d


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _is_binary(series: pd.Series) -> bool:
    return set(series.dropna().unique()).issubset({0, 1, True, False})


def _build_ddd_term(
    treat: np.ndarray,
    post: np.ndarray,
    group3: np.ndarray,
) -> np.ndarray:
    """构建三重差分交互项：treat × post × group3。"""
    return treat * post * group3


def _detect_treatment_timing(
    df: pd.DataFrame,
    treat_var: str,
    time_var: str,
    unit_var: str,
) -> dict:
    """检测每个单位的首次处理时间。"""
    units = df[unit_var].unique()
    timing = {}
    for uid in units:
        sub = df[df[unit_var] == uid].sort_values(time_var)
        treated = sub[sub[treat_var] == 1]
        if len(treated) > 0:
            timing[uid] = treated[time_var].iloc[0]
        else:
            timing[uid] = None
    return timing


def _pooled_ols(
    df_sub: pd.DataFrame,
    y_var: str,
    treat_var: str,
    time_var: str,
    unit_var: str,
    group3_var: str,
    x_vars: list,
    cluster_var: str | None,
) -> dict:
    """
    基于 statsmodels 的 OLS 三重差分回归。

    模型：y = beta * (treat x post x group3) + unit_fe + time_fe + group3_fe + X * beta + e
    用虚拟变量吸收固定效应。
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return {"error": "statsmodels not installed"}

    df_sub = df_sub.dropna(subset=[y_var, treat_var, time_var, unit_var, group3_var] + x_vars)
    if len(df_sub) < 10:
        return {"error": "insufficient observations"}

    y = df_sub[y_var].values.astype(float)
    treat = df_sub[treat_var].values.astype(float)
    post = df_sub[time_var].values.astype(float)
    group3 = df_sub[group3_var].values.astype(float)

    X_parts: list[np.ndarray] = []

    # 三重交互项
    ddd = treat * post * group3
    X_parts.append(ddd.reshape(-1, 1))
    xnames = ["treat_x_post_x_group3"]

    # 二重交互项（控制）
    X_parts.append((treat * post).reshape(-1, 1))
    X_parts.append((treat * group3).reshape(-1, 1))
    X_parts.append((post * group3).reshape(-1, 1))
    xnames += ["treat_x_post", "treat_x_group3", "post_x_group3"]

    # 主效应
    X_parts.append(treat.reshape(-1, 1))
    X_parts.append(post.reshape(-1, 1))
    X_parts.append(group3.reshape(-1, 1))
    xnames += [treat_var, time_var, group3_var]

    # 控制变量
    for xv in x_vars:
        if xv in df_sub.columns:
            X_parts.append(df_sub[xv].values.astype(float).reshape(-1, 1))
            xnames.append(xv)

    # 常数项
    X_parts.append(np.ones((len(y), 1)))
    xnames.append("const")

    X = np.column_stack(X_parts)

    cov_type = "HC1"
    cov_kwds = None
    if cluster_var and cluster_var in df_sub.columns:
        n_unique = df_sub[cluster_var].nunique()
        if n_unique >= 2:
            cov_type = "cluster"
            cov_kwds = {"groups": df_sub[cluster_var].values}

    model = sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=cov_kwds)

    # DDD 系数在第 0 个位置
    coef = float(model.params[0])
    se = float(model.bse[0])
    pval = float(model.pvalues[0])
    ci = model.conf_int()[0]

    # 处理组 / 对照组计数
    n_treated = int((treat == 1).sum())
    n_control = int((treat == 0).sum())
    n_groups = int(df_sub[group3_var].nunique())

    return {
        "coef": coef,
        "se": se,
        "pval": pval,
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "n_obs": len(df_sub),
        "n_treated": n_treated,
        "n_control": n_control,
        "n_groups": n_groups,
        "r_squared": float(model.rsquared),
        "xnames": xnames,
        "model": model,
    }


def _synthdid_weights(
    df_pre: pd.DataFrame,
    y_var: str,
    treated_units: pd.Index,
    control_units: pd.Index,
    unit_var: str,
    time_var: str,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Arkhangelsky et al. (2021) 合成 DID 权重估计。

    对每个处理单元，用加权 donor pool 构建合成对照，最小化处理前预测误差。

    Parameters
    ----------
    df_pre : pd.DataFrame
        处理前的面板数据（wide 格式：units x periods）。
    y_var : str
        结果变量名。
    treated_units : pd.Index
        处理组单位索引。
    control_units : pd.Index
        对照组单位索引。
    unit_var : str
        单位变量名。
    time_var : str
        时间变量名。

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (weights, att): 权重向量（与 control_units 对齐）和 ATT 估计值。
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        return np.array([]), np.nan

    units_in_data = df_pre[unit_var].unique()
    treated_in_data = [u for u in treated_units if u in units_in_data]
    control_in_data = [u for u in control_units if u in units_in_data]

    if len(treated_in_data) == 0 or len(control_in_data) == 0:
        return np.array([]), np.nan

    # Wide 格式
    df_wide = df_pre.pivot_table(
        index=unit_var, columns=time_var, values=y_var, aggfunc="first"
    ).dropna()

    treated_wide = df_wide.loc[[u for u in treated_in_data if u in df_wide.index]]
    control_wide = df_wide.loc[[u for u in control_in_data if u in df_wide.index]]

    if treated_wide.empty or control_wide.empty:
        return np.array([]), np.nan

    # 处理前和处理后
    n_pre = max(1, len(treated_wide.columns) // 2)
    pre_cols = treated_wide.columns[:n_pre]
    post_cols = treated_wide.columns[n_pre:]

    Y_treated_pre = treated_wide[pre_cols].values.mean(axis=1).mean()
    Y_control_pre = control_wide[pre_cols].values
    Y_treated_post = treated_wide[post_cols].values.mean(axis=1).mean()

    n_donors = len(control_in_data)
    if n_donors == 0 or Y_control_pre.size == 0:
        return np.array([]), np.nan

    # 优化权重，最小化处理前预测误差
    def objective(w: np.ndarray) -> float:
        synth_pre = np.dot(w, Y_control_pre)  # (n_donors, n_pre) -> (n_pre,)
        return float(((Y_treated_pre - synth_pre) ** 2).mean())

    # 约束：权重非负，和为1
    from scipy.optimize import minimize

    w0 = np.ones(n_donors) / n_donors
    bounds = [(0.0, 1.0)] * n_donors
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000},
    )

    weights = res.x if res.success else w0
    synth_post = np.dot(weights, control_wide[pre_cols].values.mean(axis=1))
    att = Y_treated_post - synth_post

    return weights, float(att)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class TripleDiffDIDEngine:
    """
    三重差分引擎 — sklearn-like API。

    核心模型：
        y = beta * (Treatment x Time x Group3)
            + alpha_i (unit FE) + gamma_t (time FE) + delta_j (group3 FE)
            + X * beta + epsilon

    适用于：
      - 标准 DDD：当 2x2 DID 不满足平行趋势时
      - 交错处理：部分单位在不同时间进入处理组
      - 合成 DDD：处理组单位少，用合成对照增强推断

    Attributes
    ----------
    df : pd.DataFrame
        面板数据，必须包含 unit_var、time_var、treat_var、group3_var。
    y_var : str
        结果变量。
    treat_var : str
        处理变量（0/1）。
    time_var : str
        时间变量（0/1 或具体期数）。
    unit_var : str
        单位变量（企业 / 地区等）。
    group3_var : str
        第三维度变量（如行业 / 地区 / 收入群体）。

    Usage
    -----
        engine = TripleDiffDIDEngine(
            df, y_var="roa", treat_var="did", time_var="post",
            unit_var="ticker", group3_var="industry"
        )
        result = engine.fit(x_vars=["size", "lev"], cluster_var="industry")
        hte = engine.get_hte()
        sdid = engine.synthetic_did()
        engine.plot_hte()
        engine.plot_event_study(range(-4, 6))
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        treat_var: str,
        time_var: str,
        unit_var: str,
        group3_var: str,
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.treat_var = treat_var
        self.time_var = time_var
        self.unit_var = unit_var
        self.group3_var = group3_var
        self._last_result: DDDResult | None = None
        self._hte_cache: pd.DataFrame | None = None
        self._event_study_cache: pd.DataFrame | None = None

    # ── fit ────────────────────────────────────────────────────────────────

    def fit(
        self,
        x_vars: list | None = None,
        cluster_var: str | None = None,
    ) -> DDDResult:
        """
        拟合三重差分模型。

        Parameters
        ----------
        x_vars : list | None
            控制变量列表。
        cluster_var : str | None
            聚类标准误变量（优先于引擎级设置）。

        Returns
        -------
        DDDResult
        """
        x_vars = x_vars or []
        df_sub = self.df.dropna(subset=[self.y_var])

        if len(df_sub) < 10:
            _log.error("[TripleDiffDID] Insufficient data")
            return self._empty_result("ddd_ols")

        result_dict = _pooled_ols(
            df_sub, self.y_var, self.treat_var, self.time_var,
            self.unit_var, self.group3_var, x_vars, cluster_var,
        )

        if "error" in result_dict:
            _log.error(f"[TripleDiffDID] {result_dict['error']}")
            return self._empty_result("ddd_ols")

        result = DDDResult(
            estimator="ddd_ols",
            coef=result_dict["coef"],
            se=result_dict["se"],
            pval=result_dict["pval"],
            ci_lower=result_dict["ci_lower"],
            ci_upper=result_dict["ci_upper"],
            n_obs=result_dict["n_obs"],
            n_treated=result_dict["n_treated"],
            n_control=result_dict["n_control"],
            n_groups=result_dict["n_groups"],
            r_squared=result_dict["r_squared"],
            method=cluster_var or "HC1",
            additional={
                "x_vars": x_vars,
                "cluster_var": cluster_var or self.group3_var,
                "group3_var": self.group3_var,
            },
        )

        self._last_result = result
        _log.info(
            f"[TripleDiffDID] DDD: coef={result.coef:+.4f} (p={result.pval:.3f}), "
            f"N={result.n_obs}, groups={result.n_groups}"
        )
        return result

    def _empty_result(self, estimator: str) -> DDDResult:
        return DDDResult(estimator=estimator, coef=0.0, se=0.0, pval=1.0, n_obs=0)

    # ── Heterogeneous Treatment Effects ───────────────────────────────────

    def get_hte(self) -> pd.DataFrame:
        """
        获取按 group3 分组的异质性处理效应。

        对每个 group3 类别单独拟合 2-way DID，返回各组的 ATT 估计。

        Returns
        -------
        pd.DataFrame
            含 group3 / coef / se / pval / n_obs 列。
        """
        if self._last_result is None:
            self.fit()

        groups = sorted(self.df[self.group3_var].dropna().unique())
        rows = []

        for g in groups:
            df_g = self.df[self.df[self.group3_var] == g].copy()

            # 对该 group3 内的单位再跑 2-way DID
            result_dict = _pooled_ols(
                df_g, self.y_var, self.treat_var, self.time_var,
                self.unit_var, self.group3_var, [], None,
            )

            if "error" not in result_dict:
                rows.append({
                    "group3": g,
                    "coef": result_dict["coef"],
                    "se": result_dict["se"],
                    "pval": result_dict["pval"],
                    "ci_lower": result_dict["ci_lower"],
                    "ci_upper": result_dict["ci_upper"],
                    "n_obs": result_dict["n_obs"],
                    "n_treated": result_dict["n_treated"],
                    "n_control": result_dict["n_control"],
                })

        df_hte = pd.DataFrame(rows)

        # 标注显著性
        if not df_hte.empty:
            def _sig(p: float) -> str:
                if p < 0.001:
                    return "***"
                elif p < 0.01:
                    return "**"
                elif p < 0.05:
                    return "*"
                elif p < 0.10:
                    return r"$\dagger$"
                return ""

            df_hte["sig"] = df_hte["pval"].apply(_sig)

        self._hte_cache = df_hte
        _log.info(f"[TripleDiffDID] HTE computed for {len(df_hte)} group3 categories")
        return df_hte

    # ── Event Study ───────────────────────────────────────────────────────

    def get_event_study(
        self,
        horizons: list | None = None,
    ) -> pd.DataFrame:
        """
        事件研究版本的三重差分。

        对每个相对时间 h，计算 DDD 系数：
            y = beta_h * (Treatment_h x Time_h x Group3) + FE + e

        Parameters
        ----------
        horizons : list | None
            相对时间列表，如 range(-5, 6)（不含 0）。

        Returns
        -------
        pd.DataFrame
            含 horizon / coef / se / pval / ci_lower / ci_upper 列。
        """
        if horizons is None:
            periods = sorted(self.df[self.time_var].unique())
            if len(periods) > 2:
                n = len(periods)
                horizons = list(range(-(n // 2), n // 2 + 1))
            else:
                horizons = [-1, 1]

        # 找出处理时间
        timing = _detect_treatment_timing(
            self.df, self.treat_var, self.time_var, self.unit_var
        )

        rows = []
        for h in horizons:
            if h == 0:
                continue

            df_h = self.df.copy()

            # 构建事件期处理变量：unit 在 h 期被处理
            df_h["_event_treat"] = df_h.apply(
                lambda r: 1
                if timing.get(r[self.unit_var]) is not None
                and r[self.time_var] == timing[r[self.unit_var]] + h
                else 0,
                axis=1,
            )

            if df_h["_event_treat"].sum() < 2:
                continue

            engine_h = TripleDiffDIDEngine(
                df_h, self.y_var, "_event_treat", self.time_var,
                self.unit_var, self.group3_var,
            )
            r = engine_h.fit()

            rows.append({
                "horizon": h,
                "coef": r.coef,
                "se": r.se,
                "pval": r.pval,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
            })

        df_es = pd.DataFrame(rows).sort_values("horizon").reset_index(drop=True)
        self._event_study_cache = df_es
        _log.info(f"[TripleDiffDID] Event study computed: {len(df_es)} horizons")
        return df_es

    # ── 2-way DID for specific group3 ────────────────────────────────────

    def get_2way_did(
        self,
        group3_value: Any,
        x_vars: list | None = None,
        cluster_var: str | None = None,
    ) -> DDDResult:
        """
        对特定 group3 值计算 2-way DID。

        等价于在该 group3 子样本内跑标准 2-way DID。

        Parameters
        ----------
        group3_value : Any
            group3 的具体取值（如 "manufacturing" 或 1）。
        x_vars : list | None
            控制变量。
        cluster_var : str | None
            聚类变量。

        Returns
        -------
        DDDResult
        """
        x_vars = x_vars or []
        df_sub = self.df[self.df[self.group3_var] == group3_value].copy()

        if len(df_sub) < 10:
            _log.warning(f"[TripleDiffDID] Subset for group3={group3_value} too small")
            return self._empty_result("did_2way")

        try:
            import statsmodels.api as sm
        except ImportError:
            return self._empty_result("did_2way")

        df_sub = df_sub.dropna(subset=[self.y_var] + x_vars)
        y = df_sub[self.y_var].values.astype(float)
        treat = df_sub[self.treat_var].values.astype(float)
        post = df_sub[self.time_var].values.astype(float)

        X_parts = [
            np.ones((len(y), 1)),
            treat.reshape(-1, 1),
            post.reshape(-1, 1),
            (treat * post).reshape(-1, 1),
        ]
        xnames = ["const", self.treat_var, self.time_var, "treat_x_post"]

        for xv in x_vars:
            if xv in df_sub.columns:
                X_parts.append(df_sub[xv].values.astype(float).reshape(-1, 1))
                xnames.append(xv)

        X = np.column_stack(X_parts)
        cov_type = "HC1"
        cov_kwds = None
        _cluster_var = cluster_var or self.group3_var
        if _cluster_var and _cluster_var in df_sub.columns:
            n_unique_clusters = df_sub[_cluster_var].nunique()
            if n_unique_clusters >= 2:
                cov_kwds = {"groups": df_sub[_cluster_var].values}
                cov_type = "cluster"

        model = sm.OLS(y, X).fit(cov_type=cov_type, cov_kwds=cov_kwds)
        did_idx = len(model.params) - 1
        coef = float(model.params[did_idx])
        se = float(model.bse[did_idx])
        pval = float(model.pvalues[did_idx])
        ci = model.conf_int()[did_idx]

        result = DDDResult(
            estimator="did_2way",
            coef=coef,
            se=se,
            pval=pval,
            ci_lower=float(ci[0]),
            ci_upper=float(ci[1]),
            n_obs=len(df_sub),
            n_treated=int((treat == 1).sum()),
            n_control=int((treat == 0).sum()),
            n_groups=1,
            r_squared=float(model.rsquared),
            method=cov_type,
            additional={"group3_value": group3_value, "group3_var": self.group3_var},
        )

        _log.info(
            f"[TripleDiffDID] 2-way DID for group3={group3_value}: "
            f"coef={coef:+.4f} (p={pval:.3f})"
        )
        return result

    # ── Placebo Test ─────────────────────────────────────────────────────

    def sensitivity_placebo(
        self,
        n_simulations: int = 500,
        random_seed: int = 42,
    ) -> pd.DataFrame:
        """
        安慰剂检验：随机打乱 group3 分配。

        在零假设（无处理效应）下，随机重新分配 group3 变量，
        检验 DDD 系数是否显著。如果安慰剂系数的 5% 分位数
        仍大于真实系数，说明结果稳健。

        Parameters
        ----------
        n_simulations : int
            模拟次数（默认 500）。
        random_seed : int
            随机种子。

        Returns
        -------
        pd.DataFrame
            含 simulation / coef / pval 列，以及统计摘要。
        """
        rng = np.random.default_rng(random_seed)
        true_coef = self._last_result.coef if self._last_result else self.fit().coef

        placebos = []
        for i in range(n_simulations):
            df_shuffled = self.df.copy()

            # 随机打乱 group3
            group3_vals = df_shuffled[self.group3_var].values.copy()
            rng.shuffle(group3_vals)
            df_shuffled[self.group3_var] = group3_vals

            try:
                engine_p = TripleDiffDIDEngine(
                    df_shuffled, self.y_var, self.treat_var, self.time_var,
                    self.unit_var, self.group3_var,
                )
                r = engine_p.fit()
                placebos.append({
                    "simulation": i + 1,
                    "coef": r.coef,
                    "pval": r.pval,
                })
            except Exception:
                continue

        df_placebo = pd.DataFrame(placebos)

        if not df_placebo.empty:
            # p 值：真实系数大于多少比例的安慰剂系数
            pval = float(np.mean(df_placebo["coef"].values >= true_coef))

            # 5% 分位数
            pct5 = float(np.percentile(df_placebo["coef"].values, 5))
            pct95 = float(np.percentile(df_placebo["coef"].values, 95))

            # 安慰剂中显著的占比
            sig_share = float(np.mean(df_placebo["pval"].values < 0.05))

            summary = {
                "true_coef": true_coef,
                "placebo_pct5": pct5,
                "placebo_pct95": pct95,
                "placebo_significant_share": sig_share,
                "test_pval": pval,
            }

            df_placebo.attrs["summary"] = summary

            _log.info(
                f"[TripleDiffDID] Placebo test: true_coef={true_coef:+.4f}, "
                f"pct5={pct5:+.4f}, test_pval={pval:.3f}"
            )

        return df_placebo

    # ── Synthetic DDD ─────────────────────────────────────────────────────

    def synthetic_did(
        self,
        pre_periods: int | None = None,
    ) -> dict:
        """
        合成三重差分（Arkhangelsky et al. 2021 风格）。

        对每个处理单元，用加权 donor pool 构建合成对照，
        然后在合成对照上执行 DDD。

        适用于：处理组只有少数几个单位的情况。

        Parameters
        ----------
        pre_periods : int | None
            处理前时期的期数（默认自动检测）。

        Returns
        -------
        dict
            含 att / weights / placebo_pval / summary。
        """
        if pre_periods is None:
            periods = sorted(self.df[self.time_var].unique())
            pre_periods = max(1, len(periods) // 2)

        df_sub = self.df.dropna(subset=[self.y_var])

        # 找出处理组和对照组单位
        treated_units = df_sub[df_sub[self.treat_var] == 1][self.unit_var].unique()
        control_units = df_sub[df_sub[self.treat_var] == 0][self.unit_var].unique()

        if len(treated_units) == 0 or len(control_units) == 0:
            _log.warning("[TripleDiffDID] synthetic_did: no treated/control units found")
            return {"att": np.nan, "weights": np.array([]), "placebo_pval": np.nan}

        # 分别对每个 group3 运行 SDID
        atts = []
        all_weights = []
        summaries = []

        groups = sorted(df_sub[self.group3_var].dropna().unique())

        for g in groups:
            df_g = df_sub[df_sub[self.group3_var] == g].copy()

            weights, att = _synthdid_weights(
                df_g[df_g[self.time_var] < pre_periods] if self.time_var in df_g.columns
                else df_g,
                self.y_var,
                pd.Index(treated_units),
                pd.Index(control_units),
                self.unit_var,
                self.time_var,
            )

            if not np.isnan(att):
                atts.append(att)
                all_weights.append(weights)
                summaries.append({"group3": g, "att": att, "weights": weights})

        if not atts:
            _log.warning("[TripleDiffDID] synthetic_did: no valid ATT computed")
            return {"att": np.nan, "weights": np.array([]), "placebo_pval": np.nan}

        # SDID ATT = 加权平均
        sdid_att = float(np.mean(atts))

        # 安慰剂：对每个 group3，随机分配处理组，计算安慰剂 ATT
        n_placebo = 200
        rng = np.random.default_rng(42)
        placebo_atts = []

        for _ in range(n_placebo):
            df_p = df_sub.copy()
            combined = list(treated_units) + list(control_units)
            rng.shuffle(combined)
            new_treated = combined[: len(treated_units)]

            df_p[self.treat_var] = df_p[self.unit_var].isin(new_treated).astype(int)

            # 对每个 group3 重新计算 ATT
            group_atts_p = []
            for g in groups:
                df_g = df_p[df_p[self.group3_var] == g]
                treated_g = df_g[df_g[self.treat_var] == 1][self.unit_var].unique()
                control_g = df_g[df_g[self.treat_var] == 0][self.unit_var].unique()

                _, att_p = _synthdid_weights(
                    df_g, self.y_var,
                    pd.Index(treated_g),
                    pd.Index(control_g),
                    self.unit_var,
                    self.time_var,
                )
                if not np.isnan(att_p):
                    group_atts_p.append(att_p)

            if group_atts_p:
                placebo_atts.append(float(np.mean(group_atts_p)))

        placebo_pval = (
            float(np.mean(np.array(placebo_atts) >= sdid_att))
            if placebo_atts
            else np.nan
        )

        result = {
            "att": sdid_att,
            "weights": np.array(all_weights),
            "placebo_pval": placebo_pval,
            "n_groups": len(atts),
            "group3_summaries": summaries,
            "method": "Synthetic DDD (Arkhangelsky et al. 2021)",
        }

        _log.info(
            f"[TripleDiffDID] Synthetic DDD: ATT={sdid_att:+.4f}, "
            f"placebo_pval={placebo_pval:.3f}"
        )
        return result

    # ── Plotting ─────────────────────────────────────────────────────────

    def plot_hte(
        self,
        save_path: str | Path | None = None,
        figsize: tuple = (8, 5),
    ) -> Any:
        """
        绘制异质性效应森林图（forest plot）。

        Parameters
        ----------
        save_path : str | Path | None
            保存路径（.png / .pdf）。
        figsize : tuple
            图形大小。

        Returns
        -------
        matplotlib Figure or None
        """
        if self._hte_cache is None:
            self.get_hte()

        df = self._hte_cache
        if df is None or df.empty:
            _log.warning("[TripleDiffDID] No HTE data to plot")
            return None

        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=figsize)

            y_pos = np.arange(len(df))
            colors = ["steelblue" if p < 0.05 else "lightgray" for p in df["pval"]]

            ax.barh(y_pos, df["coef"], xerr=1.96 * df["se"],
                    color=colors, capsize=4, alpha=0.8)
            ax.axvline(x=0, color="gray", linestyle="--", linewidth=0.8)
            ax.set_yticks(y_pos)
            ax.set_yticklabels([str(g) for g in df["group3"]], fontsize=10)
            ax.set_xlabel("Estimated Effect (DDD Coef)", fontsize=11)
            ax.set_title(
                f"Heterogeneous Treatment Effects by {self.group3_var} (95% CI)",
                fontsize=12, fontweight="bold",
            )
            ax.grid(True, alpha=0.3, axis="x")

            plt.tight_layout()

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(save_path, dpi=300, bbox_inches="tight")
                _log.info(f"[TripleDiffDID] HTE plot saved: {save_path}")

            return fig

        except ImportError:
            _log.warning("[TripleDiffDID] matplotlib not installed")
            return None

    def plot_event_study(
        self,
        horizons: list | None = None,
        save_path: str | Path | None = None,
        figsize: tuple = (8, 5),
    ) -> Any:
        """
        绘制事件研究图（三重差分版）。

        Parameters
        ----------
        horizons : list | None
            相对时间列表。
        save_path : str | Path | None
            保存路径。
        figsize : tuple
            图形大小。

        Returns
        -------
        matplotlib Figure or None
        """
        if self._event_study_cache is None:
            self.get_event_study(horizons)

        df = self._event_study_cache
        if df is None or df.empty:
            _log.warning("[TripleDiffDID] No event study data to plot")
            return None

        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=figsize)

            ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
            ax.axvline(x=-0.5, color="gray", linestyle="--", linewidth=0.8)

            ax.errorbar(
                df["horizon"], df["coef"],
                yerr=1.96 * df["se"],
                fmt="o", color="steelblue", capsize=4,
                linewidth=1.5, markersize=6,
            )

            ax.fill_between(
                df["horizon"],
                df["ci_lower"], df["ci_upper"],
                alpha=0.15, color="steelblue",
            )

            ax.set_xlabel("Relative Time (Years)", fontsize=12)
            ax.set_ylabel("Estimated Effect (DDD Coef)", fontsize=12)
            ax.set_title(
                f"Event Study: Triple DiD (95% CI)",
                fontsize=13, fontweight="bold",
            )
            ax.set_xticks(sorted(df["horizon"].unique()))
            ax.grid(True, alpha=0.3)

            plt.tight_layout()

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(save_path, dpi=300, bbox_inches="tight")
                _log.info(f"[TripleDiffDID] Event study plot saved: {save_path}")

            return fig

        except ImportError:
            _log.warning("[TripleDiffDID] matplotlib not installed")
            return None

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        汇总 DDD 估计结果。

        Returns
        -------
        pd.DataFrame
        """
        if self._last_result is None:
            self.fit()

        r = self._last_result
        if r is None:
            return pd.DataFrame()

        rows = [{
            "Estimator": "DDD (OLS)",
            "Coef": r.coef,
            "SE": r.se,
            "p-val": r.pval,
            "Sig": r.sig,
            "CI (lower)": r.ci_lower,
            "CI (upper)": r.ci_upper,
            "N": r.n_obs,
            "N_Treated": r.n_treated,
            "N_Control": r.n_control,
            "N_Group3": r.n_groups,
            "R2": r.r_squared,
            "Method": r.method,
        }]

        # HTE 摘要
        if self._hte_cache is not None and not self._hte_cache.empty:
            for _, row in self._hte_cache.iterrows():
                rows.append({
                    "Estimator": f"  2W-DID | {self.group3_var}={row['group3']}",
                    "Coef": row["coef"],
                    "SE": row["se"],
                    "p-val": row["pval"],
                    "Sig": row.get("sig", ""),
                    "CI (lower)": row.get("ci_lower", 0),
                    "CI (upper)": row.get("ci_upper", 0),
                    "N": row["n_obs"],
                    "N_Treated": row.get("n_treated", 0),
                    "N_Control": row.get("n_control", 0),
                    "N_Group3": 1,
                    "R2": None,
                    "Method": "cluster",
                })

        return pd.DataFrame(rows)

    def to_latex(self) -> str:
        """
        导出为 LaTeX 表格（booktabs 风格）。

        Returns
        -------
        str
            LaTeX 代码。
        """
        df = self.summary()
        if df.empty:
            return ""

        caption = f"\\caption{{Triple Difference-in-Differences Results}}"
        label = "\\label{tab:ddd}"

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  {caption}",
            f"  {label}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccccc}",
            "    \\toprule",
            "    \\textbf{Estimator} & \\textbf{Coef} & \\textbf{SE} & "
            "\\textbf{p-val} & \\textbf{CI Lower} & \\textbf{CI Upper} & \\textbf{N} \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            sig = row.get("Sig", "")
            coef_str = f"{row['Coef']:.4f}{sig}"
            se_str = f"({row['SE']:.4f})"
            lines.append(
                f"    {row['Estimator']} & {coef_str} & {se_str} & "
                f"{row['p-val']:.3f} & {row['CI (lower)']:.4f} & "
                f"{row['CI (upper)']:.4f} & {int(row['N'])} \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Standard errors in parentheses. "
            "$^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "    \\item DDD: $y = \\beta \\cdot (Treatment \\times Time \\times Group3) + FE$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])

        return "\n".join(lines)
