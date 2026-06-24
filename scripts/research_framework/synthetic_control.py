"""Synthetic Control Method — Abadie et al. (2010, 2015) and Augmented SC (Abadie 2021).

Implements:
  1. Data preprocessing (treated unit + donor pool)
  2. Optimized weight estimation (scipy.optimize, minimize pre-treatment fit error)
  3. Synthetic control construction (weighted average of donor units)
  4. Placebo tests (unit-by-unit and period-by-period)
  5. Permutation inference (ratio WA/RMSE statistics)
  6. RMSPE ratio (post/pre treatment periods)
  7. Placebo figure visualization
  8. MSPE-based inference
  9. Donor weight interpretability report

Usage:
    engine = SyntheticControlEngine(df, y_var="gdp_per_capita",
                                   unit_var="state", time_var="year",
                                   treat_unit="california",
                                   treat_period=1989)
    result = engine.fit()
    engine.plot_placebo(save_path="placebo.png")
    inference = engine.inference(n_placebos=999)

Quick Start
-----------
最小可运行示例（California-style 合成控制数据）：

>>> import numpy as np
>>> import pandas as pd
>>> from scripts.research_framework.synthetic_control import SyntheticControlEngine

>>> # 1) 构造合成数据：1 treated unit + 4 donor units × 20 年（1980-1999）
>>> years = list(range(1980, 2000))  # 1989 = treatment year
>>> rows = []
>>> donor_units = ["texas", "new_york", "ohio", "pennsylvania"]
>>> for unit in ["california"] + donor_units:
...     rng = np.random.default_rng(hash(unit) % (2**32))
...     base = rng.normal(0, 1, len(years)).cumsum()
...     is_treated = unit == "california"
...     for i, year in enumerate(years):
...         treat_add = 5.0 if (is_treated and year >= 1989) else 0.0
...         rows.append({
...             "state": unit,
...             "year": year,
...             "gdp_per_capita": 30 + base[i] + treat_add,
...             "pop_density": 100 + i * 0.5,
...             "invest_rate": 0.2 + 0.001 * i,
...         })
>>> df = pd.DataFrame(rows)

>>> # 2) 初始化合成控制引擎
>>> engine = SyntheticControlEngine(
...     df=df,
...     y_var="gdp_per_capita",
...     unit_var="state",
...     time_var="year",
...     treat_unit="california",
...     treat_period=1989,
...     x_vars=["pop_density", "invest_rate"],
... )

>>> # 3) 拟合权重
>>> result = engine.fit()
>>> isinstance(result.rmspe_ratio, float)
True
>>> result.n_post_periods == 11  # 1989-1999 inclusive
True
>>> result.n_donors == 4  # 4 donor units
True

References:
    Abadie, A., Diamond, A., & Hainmueller, J. (2010). Synthetic Control... JASA.
    Abadie, A., Diamond, A., & Hainmueller, J. (2015). Comparative... JASA.
    Abadie, A. (2021). Using Synthetic Controls: Feasibility... AER.
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
    "SyntheticControlEngine",
    "SCEstimationResult",
]

_log = logging.getLogger("synthetic_control")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SCEstimationResult:
    """
    Synthetic Control estimation result container.

    Attributes
    ----------
    treat_unit : str
        Treated unit name.
    treat_period : int | float
        First treatment period.
    donor_weights : np.ndarray
        Weight for each donor unit (sum to 1, non-negative).
    donor_names : list[str]
        Names of donor units corresponding to weights.
    pre_mspe : float
        Mean Squared Prediction Error on pre-treatment periods.
    post_mspe : float
        Mean Squared Prediction Error on post-treatment periods.
    rmspe_ratio : float
        Ratio = post_mspe / pre_mspe (inference statistic).
    effect_path : np.ndarray
        Time path of treatment effects (treated - synthetic).
    synthetic_path : np.ndarray
        Synthetic control time path.
    treated_path : np.ndarray
        Treated unit time path.
    time_index : list
        Time periods corresponding to paths.
    r_squared_pre : float | None
        In-sample R-squared on pre-treatment periods.
    n_donors : int
        Number of donor units.
    n_pre_periods : int
        Number of pre-treatment periods.
    n_post_periods : int
        Number of post-treatment periods.
    augment : bool
        Whether augmented SC was used.
    additional : dict
        Extra diagnostics (placebo results, permutation p-values, etc.).
    """

    treat_unit: str
    treat_period: int | float
    donor_weights: np.ndarray = field(default_factory=lambda: np.array([]))
    donor_names: list = field(default_factory=list)
    pre_mspe: float = 0.0
    post_mspe: float = 0.0
    rmspe_ratio: float = 0.0
    effect_path: np.ndarray = field(default_factory=lambda: np.array([]))
    synthetic_path: np.ndarray = field(default_factory=lambda: np.array([]))
    treated_path: np.ndarray = field(default_factory=lambda: np.array([]))
    time_index: list = field(default_factory=list)
    r_squared_pre: float | None = None
    n_donors: int = 0
    n_pre_periods: int = 0
    n_post_periods: int = 0
    augment: bool = False
    additional: dict = field(default_factory=dict)

    @property
    def sig(self) -> str:
        ratio = self.rmspe_ratio
        if ratio > 20: return "***"
        elif ratio > 10: return "**"
        elif ratio > 5: return "*"
        elif ratio > 2: return r"$\dagger$"
        return ""

    def to_dict(self) -> dict:
        return {
            "treat_unit": self.treat_unit,
            "treat_period": self.treat_period,
            "pre_mspe": self.pre_mspe,
            "post_mspe": self.post_mspe,
            "rmspe_ratio": self.rmspe_ratio,
            "r_squared_pre": self.r_squared_pre,
            "n_donors": self.n_donors,
            "n_pre_periods": self.n_pre_periods,
            "n_post_periods": self.n_post_periods,
            "augment": self.augment,
            "sig": self.sig,
            **{k: v for k, v in self.additional.items()},
        }

    def donor_report(self) -> pd.DataFrame:
        """Return donor weight table sorted by weight descending."""
        if len(self.donor_weights) == 0:
            return pd.DataFrame()
        df = pd.DataFrame({
            "donor": self.donor_names,
            "weight": self.donor_weights,
        })
        return df.sort_values("weight", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _optimize_weights(
    Y_treated_pre: np.ndarray,
    Y_donors_pre: np.ndarray,
    augment: bool = False,
    ridge_lambda: float = 0.0,
) -> tuple[np.ndarray, float]:
    """
    Optimize donor weights to minimize pre-treatment prediction error.

    Min_{w >= 0, sum(w)=1} ||Y_treated_pre - Y_donors_pre @ w||^2

    Uses scipy.optimize.minimize with SLSQP (sequential least squares
    programming) which supports equality/inequality constraints.

    When augment=True, adds a ridge penalty term to improve conditioning
    (approximates Augmented SC, Abadie 2021).

    Parameters
    ----------
    Y_treated_pre : np.ndarray, shape (n_pre,)
        Treated unit outcome in pre-treatment periods.
    Y_donors_pre : np.ndarray, shape (n_pre, n_donors)
        Donor outcomes in pre-treatment periods.
    augment : bool
        Whether to use augmented SC (ridge regularization).
    ridge_lambda : float
        Ridge penalty weight (used only when augment=True).

    Returns
    -------
    w : np.ndarray, shape (n_donors,)
        Optimal donor weights.
    pre_mspe : float
        Pre-treatment MSPE (Mean Squared Prediction Error).
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        _log.error("[SC] scipy.optimize not available")
        w = np.ones(Y_donors_pre.shape[1]) / Y_donors_pre.shape[1]
        pre_mspe = float(np.mean((Y_treated_pre - Y_donors_pre @ w) ** 2))
        return w, pre_mspe

    n_donors = Y_donors_pre.shape[1]

    def objective(w: np.ndarray) -> float:
        pred = Y_donors_pre @ w
        sse = np.sum((Y_treated_pre - pred) ** 2)
        if augment and ridge_lambda > 0:
            sse += ridge_lambda * np.sum(w**2)
        return sse

    # Constraint: weights sum to 1
    eq_constraint = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

    # Bounds: non-negative weights
    bounds = [(0.0, 1.0) for _ in range(n_donors)]

    # Initial guess: equal weights
    w0 = np.ones(n_donors) / n_donors

    result = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=eq_constraint,
        options={"maxiter": 2000, "ftol": 1e-10},
    )

    if not result.success:
        _log.warning(f"[SC] Optimization did not converge: {result.message}")

    w = result.x
    w = np.maximum(w, 0.0)
    w = w / (w.sum() + 1e-12)  # re-normalize

    pre_mspe = float(np.mean((Y_treated_pre - Y_donors_pre @ w) ** 2))
    return w, pre_mspe


# ─────────────────────────────────────────────────────────────────────────────
# AUGMENTED SYNTHETIC CONTROL (Abadie 2021)
# ─────────────────────────────────────────────────────────────────────────────


def _augmented_sc(
    Y_treated_pre: np.ndarray,
    Y_donors_pre: np.ndarray,
    Y_treated_post: np.ndarray,
    Y_donors_post: np.ndarray,
    ridge_lambda: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Augmented Synthetic Control (Abadie 2021).

    Solves a regularized optimization that includes:
      1. Pre-period fit (synthetic control)
      2. Ridge penalty on weights
      3. Intercept term to capture systematic deviations

    This improves over plain SC when:
      - Donor pool is small relative to pre-periods
      - Pre-period fit is poor
      - There are unit-level heterogeneity not captured by SC

    Parameters
    ----------
    Y_treated_pre, Y_treated_post : np.ndarray
        Treated unit outcomes in pre and post periods.
    Y_donors_pre, Y_donors_post : np.ndarray
        Donor unit outcomes in pre and post periods.
    ridge_lambda : float
        Ridge penalty weight.

    Returns
    -------
    w : np.ndarray
        Augmented donor weights.
    intercept : float
        Intercept term (can be used to adjust predictions).
    """
    n_pre = len(Y_treated_pre)
    n_donors = Y_donors_pre.shape[1]

    # Design matrix: [Y_donors_pre, 1] (intercept as extra column)
    X_pre = np.column_stack([Y_donors_pre, np.ones(n_pre)])
    X_post = np.column_stack([Y_donors_post, np.ones(len(Y_treated_post))])

    n_vars = n_donors + 1  # donors + intercept

    def objective(params: np.ndarray) -> float:
        w = params[:n_donors]
        alpha = params[n_donors]
        pred = X_pre @ params
        sse = np.sum((Y_treated_pre - pred) ** 2)
        sse += ridge_lambda * np.sum(w**2)
        return sse

    from scipy.optimize import minimize

    eq_constraint = {"type": "eq", "fun": lambda p: np.sum(p[:n_donors]) - 1.0}
    bounds = [(0.0, 1.0) for _ in range(n_donors)] + [(-np.inf, np.inf)]

    result = minimize(
        objective,
        np.concatenate([np.ones(n_donors) / n_donors, np.zeros(1)]),
        method="SLSQP",
        bounds=bounds,
        constraints=eq_constraint,
        options={"maxiter": 2000},
    )

    if not result.success:
        _log.warning(f"[SC] Augmented SC optimization: {result.message}")

    w = np.maximum(result.x[:n_donors], 0.0)
    w = w / (w.sum() + 1e-12)
    alpha = float(result.x[n_donors])

    return w, alpha


# ─────────────────────────────────────────────────────────────────────────────
# PLACEBO TESTS
# ─────────────────────────────────────────────────────────────────────────────


def _unit_placebo(
    df: pd.DataFrame,
    unit_col: str,
    time_col: str,
    y_col: str,
    treat_unit: str,
    treat_period: Any,
    donor_names: list[str],
    augment: bool = False,
) -> dict:
    """
    Placebo test: treat each donor unit as pseudo-treated.

    Computes RMSPE ratio for a pseudo-treated unit using the same
    donor weights (excluding the pseudo-treated from its own pool).
    """
    units = list(df[unit_col].unique())

    if unit_col == treat_unit or unit_col not in donor_names:
        return {"unit": unit_col, "rmspe_ratio": np.nan, "pre_mspe": np.nan, "post_mspe": np.nan}

    # Donor pool excluding this unit
    pseudo_donors = [d for d in donor_names if d != unit_col]
    if len(pseudo_donors) < 1:
        return {"unit": unit_col, "rmspe_ratio": np.nan, "pre_mspe": np.nan, "post_mspe": np.nan}

    # Get pre/post data
    df_pre = df[(df[time_col] < treat_period) & (df[unit_col].isin([unit_col] + pseudo_donors))]
    df_post = df[(df[time_col] >= treat_period) & (df[unit_col].isin([unit_col] + pseudo_donors))]

    if len(df_pre) == 0 or len(df_post) == 0:
        return {"unit": unit_col, "rmspe_ratio": np.nan, "pre_mspe": np.nan, "post_mspe": np.nan}

    # Pivot
    try:
        treated_pre_vals = df_pre[df_pre[unit_col] == unit_col].sort_values(time_col)[y_col].values
        treated_post_vals = df_post[df_post[unit_col] == unit_col].sort_values(time_col)[y_col].values

        donor_pre_matrix = df_pre[df_pre[unit_col].isin(pseudo_donors)].pivot_table(
            index=time_col, columns=unit_col, values=y_col, aggfunc="first"
        ).sort_index().values

        donor_post_matrix = df_post[df_post[unit_col].isin(pseudo_donors)].pivot_table(
            index=time_col, columns=unit_col, values=y_col, aggfunc="first"
        ).sort_index().values

        if len(treated_pre_vals) < 2 or len(donor_pre_matrix) < 2:
            return {"unit": unit_col, "rmspe_ratio": np.nan, "pre_mspe": np.nan, "post_mspe": np.nan}

        # Re-estimate weights for this pseudo-treatment
        if augment:
            w, _ = _augmented_sc(
                treated_pre_vals, donor_pre_matrix,
                treated_post_vals, donor_post_matrix,
            )
        else:
            w, _ = _optimize_weights(treated_pre_vals, donor_pre_matrix, augment=False)

        # Compute MSPE
        synth_pre = donor_pre_matrix @ w
        synth_post = donor_post_matrix @ w

        pre_mspe = float(np.mean((treated_pre_vals - synth_pre) ** 2))
        post_mspe = float(np.mean((treated_post_vals - synth_post) ** 2))
        rmspe_ratio = post_mspe / (pre_mspe + 1e-12) if pre_mspe > 0 else np.nan

    except Exception:
        return {"unit": unit_col, "rmspe_ratio": np.nan, "pre_mspe": np.nan, "post_mspe": np.nan}

    return {
        "unit": unit_col,
        "rmspe_ratio": rmspe_ratio,
        "pre_mspe": pre_mspe,
        "post_mspe": post_mspe,
    }


def _period_placebo(
    Y_treated: np.ndarray,
    Y_donors: np.ndarray,
    time_index: list,
    weights: np.ndarray,
    treat_period_idx: int,
) -> list[dict]:
    """
    Period-by-period placebo: sequentially treat each pre-treatment period
    as pseudo-treatment and compute RMSPE ratio.
    """
    results = []
    n_periods = len(time_index)

    for t_idx in range(n_periods):
        if t_idx >= treat_period_idx:
            continue  # only pre-treatment pseudo-treatment periods

        pseudo_treat_idx = t_idx
        pseudo_donors_pre = Y_donors[:pseudo_treat_idx + 1, :]
        pseudo_treated_pre = Y_treated[:pseudo_treat_idx + 1]

        if len(pseudo_treated_pre) < 2 or pseudo_donors_pre.shape[1] < 1:
            continue

        w, pre_mspe = _optimize_weights(pseudo_treated_pre, pseudo_donors_pre)

        # Compute post-MSPE (relative to actual post period)
        if pseudo_treat_idx + 1 < len(Y_treated):
            post_vals = Y_treated[pseudo_treat_idx + 1:]
            post_synth = Y_donors[pseudo_treat_idx + 1:, :] @ w
            post_mspe = float(np.mean((post_vals - post_synth) ** 2))
        else:
            post_mspe = np.nan

        rmspe_ratio = post_mspe / (pre_mspe + 1e-12) if pre_mspe > 0 else np.nan
        results.append({
            "pseudo_treat_period": time_index[t_idx],
            "pseudo_treat_idx": t_idx,
            "rmspe_ratio": rmspe_ratio,
            "pre_mspe": pre_mspe,
            "post_mspe": post_mspe,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PERMUTATION INFERENCE
# ─────────────────────────────────────────────────────────────────────────────


def _permutation_inference(
    df: pd.DataFrame,
    unit_col: str,
    time_col: str,
    y_col: str,
    treat_unit: str,
    treat_period: Any,
    donor_names: list[str],
    augment: bool = False,
    n_placebos: int | None = None,
) -> dict:
    """
    Permutation inference: compute RMSPE ratio for every donor unit.

    Returns the rank of the treated unit's RMSPE ratio among all units,
    which gives a non-parametric p-value.
    """
    units = [u for u in df[unit_col].unique() if u in donor_names or u == treat_unit]
    if n_placebos is not None:
        units = [treat_unit] + [u for u in donor_names if u != treat_unit][:n_placebos]

    ratios = {}
    for unit in units:
        res = _unit_placebo(
            df, unit_col, time_col, y_col,
            unit, treat_period, donor_names, augment=augment,
        )
        ratios[unit] = res.get("rmspe_ratio", np.nan)

    ratios = {k: v for k, v in ratios.items() if not np.isnan(v)}
    if not ratios:
        return {"p_value": np.nan, "n_valid": 0, "ratios": {}}

    treated_ratio = ratios.get(treat_unit, np.nan)
    rank = sum(1 for v in ratios.values() if v >= treated_ratio)
    p_value = rank / len(ratios)

    return {
        "p_value": float(p_value),
        "n_valid": len(ratios),
        "rank": int(rank),
        "treated_ratio": float(treated_ratio) if not np.isnan(treated_ratio) else None,
        "ratios": {k: float(v) for k, v in ratios.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class SyntheticControlEngine:
    """
    Synthetic Control Method — sklearn-like API.

    Implements Abadie et al. (2010, 2015) SC and Abadie (2021) Augmented SC.

    Parameters
    ----------
    df : pd.DataFrame
        Long-format panel data with unit, time, and outcome columns.
    y_var : str
        Outcome variable column name.
    unit_var : str
        Unit identifier column name.
    time_var : str
        Time period column name.
    treat_unit : str
        Name of the treated unit.
    treat_period : int | float
        First treatment period (inclusive).
    x_vars : list[str] | None
        Additional predictor variables for augmented SC (covariates).
        When provided, these are used in addition to outcome predictors.
    augment : bool
        Use augmented SC (Abadie 2021) with ridge regularization.
    ridge_lambda : float
        Ridge penalty for augmented SC (default 1.0).
    min_donors : int
        Minimum number of donor units required (default 2).

    Usage
    -----
        engine = SyntheticControlEngine(df, y_var="gdp_per_capita",
                                       unit_var="state", time_var="year",
                                       treat_unit="california", treat_period=1989)
        result = engine.fit()
        engine.plot_placebo(save_path="placebo.png")
        inference = engine.inference(n_placebos=999)

        # Multi-treatment: estimate one at a time
        for unit in treated_units:
            eng = SyntheticControlEngine(df, y_var="y", unit_var="unit",
                                         time_var="year", treat_unit=unit,
                                         treat_period=2000)
            result = eng.fit()
    """

    def __init__(
        self,
        df: pd.DataFrame,
        y_var: str,
        unit_var: str,
        time_var: str,
        treat_unit: str,
        treat_period: int | float,
        x_vars: list[str] | None = None,
        augment: bool = False,
        ridge_lambda: float = 1.0,
        min_donors: int = 2,
    ):
        self.df = df.copy()
        self.y_var = y_var
        self.unit_var = unit_var
        self.time_var = time_var
        self.treat_unit = treat_unit
        self.treat_period = treat_period
        self.x_vars = x_vars or []
        self.augment = augment
        self.ridge_lambda = ridge_lambda
        self.min_donors = min_donors
        self._result: SCEstimationResult | None = None

        # Validate
        if treat_unit not in df[unit_var].values:
            raise ValueError(f"[SC] treat_unit '{treat_unit}' not found in {unit_var}")
        if treat_period not in df[time_var].values:
            raise ValueError(f"[SC] treat_period {treat_period} not found in {time_var}")

        # Pre/post split
        self.time_index = sorted(df[time_var].unique())
        self.treat_period_idx = self.time_index.index(treat_period)

        self._pre_times = [t for t in self.time_index if t < treat_period]
        self._post_times = [t for t in self.time_index if t >= treat_period]

        # Donor pool: all units except treated
        self.donor_names = [
            u for u in df[unit_var].unique()
            if u != treat_unit
        ]

        if len(self.donor_names) < self.min_donors:
            _log.warning(
                f"[SC] Only {len(self.donor_names)} donors found (min={self.min_donors})"
            )

    # ── Internal data prep ─────────────────────────────────────────────────

    def _build_matrices(self) -> dict:
        """Build pre/post outcome matrices for treated and donors."""
        df_pre = self.df[self.df[self.time_var] < self.treat_period].copy()
        df_post = self.df[self.df[self.time_var] >= self.treat_period].copy()

        if df_pre.empty or df_post.empty:
            raise ValueError("[SC] Empty pre or post period data")

        # Treated unit series
        treat_pre = df_pre[df_pre[self.unit_var] == self.treat_unit].sort_values(self.time_var)
        treat_post = df_post[df_post[self.unit_var] == self.treat_unit].sort_values(self.time_var)

        Y_treated_pre = treat_pre[self.y_var].values.astype(float)
        Y_treated_post = treat_post[self.y_var].values.astype(float)

        # Donor matrix (pivot: time x donor)
        donor_pre_pivot = df_pre[df_pre[self.unit_var].isin(self.donor_names)].pivot_table(
            index=self.time_var, columns=self.unit_var, values=self.y_var, aggfunc="first"
        ).sort_index()

        donor_post_pivot = df_post[df_post[self.unit_var].isin(self.donor_names)].pivot_table(
            index=self.time_var, columns=self.unit_var, values=self.y_var, aggfunc="first"
        ).sort_index()

        # Align columns (some donors may not appear in all periods)
        all_donor_units = list(set(donor_pre_pivot.columns) | set(donor_post_pivot.columns))
        for u in all_donor_units:
            if u not in donor_pre_pivot.columns:
                donor_pre_pivot[u] = np.nan
            if u not in donor_post_pivot.columns:
                donor_post_pivot[u] = np.nan

        donor_pre_pivot = donor_pre_pivot[all_donor_units]
        donor_post_pivot = donor_post_pivot[all_donor_units]

        Y_donors_pre = donor_pre_pivot.values.astype(float)
        Y_donors_post = donor_post_pivot.values.astype(float)

        return {
            "Y_treated_pre": Y_treated_pre,
            "Y_treated_post": Y_treated_post,
            "Y_donors_pre": Y_donors_pre,
            "Y_donors_post": Y_donors_post,
            "donor_units": all_donor_units,
            "pre_times": sorted(donor_pre_pivot.index.tolist()),
            "post_times": sorted(donor_post_pivot.index.tolist()),
        }

    # ── Core fit ───────────────────────────────────────────────────────────

    def _warn_if_nonstationary(
        self,
        Y_treated_pre: np.ndarray,
        Y_donors_pre: np.ndarray,
        donor_units: list,
    ) -> None:
        """Warn if treated or any donor series is I(1) (non-stationary).

        Synthetic control assumes the outcome series is stationary (or
        cointegrated with the donor pool). Without stationarity, the
        pre-treatment fit is spurious and post-treatment effects are biased.

        Uses Augmented Dickey-Fuller (statsmodels). Skips if statsmodels
        unavailable or series too short (<8 obs).
        """
        try:
            from statsmodels.tsa.stattools import adfuller
        except ImportError:
            return  # statsmodels missing — silently skip
        import warnings as _w

        def _is_stationary(series: np.ndarray) -> bool:
            arr = np.asarray(series, dtype=float).ravel()
            arr = arr[~np.isnan(arr)]
            if len(arr) < 8:
                return True  # too short to test
            try:
                pval = adfuller(arr, autolag="AIC")[1]
                return pval < 0.05  # reject unit root ⇒ stationary
            except Exception:
                return True  # test failed — don't block user

        flagged = []
        if not _is_stationary(Y_treated_pre):
            flagged.append(f"treated({self.treat_unit})")
        # Check donors but cap at first 10 to keep warnings short
        for i, unit in enumerate(donor_units[:10]):
            if i >= Y_donors_pre.shape[1]:
                break
            if not _is_stationary(Y_donors_pre[:, i]):
                flagged.append(f"donor({unit})")
        if flagged:
            _w.warn(
                f"[SyntheticControl] ADF test (α=0.05) suggests non-stationarity "
                f"in: {', '.join(flagged[:5])}"
                f"{' ...' if len(flagged) > 5 else ''}. "
                f"SC weights are biased when treated/donor series are I(1) but "
                f"not cointegrated. Consider differencing, taking logs, or using "
                f"a cointegration-based estimator (e.g., Pesaran 2015).",
                UserWarning,
                stacklevel=2,
            )

    def fit(self) -> SCEstimationResult:
        """
        Estimate synthetic control weights.

        Returns
        -------
        SCEstimationResult
        """
        mats = self._build_matrices()
        Y_treated_pre = mats["Y_treated_pre"]
        Y_donors_pre = mats["Y_donors_pre"]
        Y_treated_post = mats["Y_treated_post"]
        Y_donors_post = mats["Y_donors_post"]
        donor_units = mats["donor_units"]

        # ── Stationarity pre-check (advisory) ──
        # SC weights assume the outcome series is stationary (or cointegrated with
        # the donor pool). ADF test on treated pre-period + donor series; emit a
        # warning if any series is I(1) at 5% (i.e., likely non-stationary).
        self._warn_if_nonstationary(Y_treated_pre, Y_donors_pre, donor_units)

        if self.augment:
            weights, intercept = _augmented_sc(
                Y_treated_pre, Y_donors_pre,
                Y_treated_post, Y_donors_post,
                ridge_lambda=self.ridge_lambda,
            )
        else:
            weights, _ = _optimize_weights(
                Y_treated_pre, Y_donors_pre,
                augment=False,
            )
            intercept = 0.0

        # Synthetic and effect paths
        synth_pre = Y_donors_pre @ weights + intercept
        synth_post = Y_donors_post @ weights + intercept

        # Pre MSPE
        pre_mspe = float(np.mean((Y_treated_pre - synth_pre) ** 2))
        post_mspe = float(np.mean((Y_treated_post - synth_post) ** 2))
        rmspe_ratio = post_mspe / (pre_mspe + 1e-12) if pre_mspe > 0 else np.nan

        # R-squared on pre periods
        ss_tot = np.sum((Y_treated_pre - Y_treated_pre.mean()) ** 2)
        ss_res = np.sum((Y_treated_pre - synth_pre) ** 2)
        r2_pre = float(1 - ss_res / (ss_tot + 1e-12)) if ss_tot > 0 else None

        # Full time paths (align by index)
        full_treated = np.concatenate([Y_treated_pre, Y_treated_post])
        full_synthetic = np.concatenate([synth_pre, synth_post])
        full_effect = full_treated - full_synthetic
        full_time = mats["pre_times"] + mats["post_times"]

        self._result = SCEstimationResult(
            treat_unit=self.treat_unit,
            treat_period=self.treat_period,
            donor_weights=weights,
            donor_names=donor_units,
            pre_mspe=pre_mspe,
            post_mspe=post_mspe,
            rmspe_ratio=rmspe_ratio,
            effect_path=full_effect,
            synthetic_path=full_synthetic,
            treated_path=full_treated,
            time_index=full_time,
            r_squared_pre=r2_pre,
            n_donors=len(donor_units),
            n_pre_periods=len(mats["pre_times"]),
            n_post_periods=len(mats["post_times"]),
            augment=self.augment,
            additional={"intercept": intercept, "ridge_lambda": self.ridge_lambda},
        )

        _log.info(
            f"[SC] {self.treat_unit}: pre_mspe={pre_mspe:.6f}, "
            f"post_mspe={post_mspe:.6f}, ratio={rmspe_ratio:.2f}, "
            f"n_donors={len(donor_units)}"
        )

        return self._result

    # ── Inference ──────────────────────────────────────────────────────────

    def inference(
        self,
        n_placebos: int | None = None,
        unit_placebo: bool = True,
        period_placebo: bool = True,
    ) -> dict:
        """
        Run placebo tests and permutation inference.

        Parameters
        ----------
        n_placebos : int | None
            Limit permutation tests to n_placebos random donors.
        unit_placebo : bool
            Run unit-by-unit placebo tests.
        period_placebo : bool
            Run period-by-period placebo tests.

        Returns
        -------
        dict
            Contains permutation p-value, unit placebo results, and period results.
        """
        if self._result is None:
            self.fit()

        mats = self._build_matrices()
        result = {"treat_unit": self.treat_unit}

        # Permutation (unit-by-unit)
        if unit_placebo:
            perm = _permutation_inference(
                self.df, self.unit_var, self.time_var, self.y_var,
                self.treat_unit, self.treat_period,
                self.donor_names, augment=self.augment,
                n_placebos=n_placebos,
            )
            result["permutation"] = perm

            # Also compute full unit placebo table
            placebo_rows = []
            for unit in self.donor_names:
                r = _unit_placebo(
                    self.df, self.unit_var, self.time_var, self.y_var,
                    unit, self.treat_period, self.donor_names,
                    augment=self.augment,
                )
                placebo_rows.append(r)
            result["unit_placebo_df"] = pd.DataFrame(placebo_rows)

        # Period-by-period placebo
        if period_placebo:
            period_results = _period_placebo(
                np.concatenate([mats["Y_treated_pre"], mats["Y_treated_post"]]),
                np.vstack([mats["Y_donors_pre"], mats["Y_donors_post"]]),
                mats["pre_times"] + mats["post_times"],
                self._result.donor_weights,
                len(mats["pre_times"]),
            )
            result["period_placebo"] = period_results
            result["period_placebo_df"] = pd.DataFrame(period_results)

        self._result.additional["inference"] = result
        _log.info(
            f"[SC] Inference: p={result.get('permutation', {}).get('p_value', 'N/A')}, "
            f"rank={result.get('permutation', {}).get('rank', 'N/A')}"
        )
        return result

    # ── Plots ─────────────────────────────────────────────────────────────

    def plot_placebo(
        self,
        n_top_donors: int = 30,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (10, 6),
    ) -> Any:
        """
        Plot synthetic control time path with placebo units.

        Parameters
        ----------
        n_top_donors : int
            Maximum number of placebo units to show.
        save_path : str | Path | None
            Save figure to this path (.png, .pdf).
        figsize : tuple
            Figure size.

        Returns
        -------
        matplotlib Figure or None
        """
        if self._result is None:
            self.fit()

        try:
            import matplotlib.pyplot as plt
            import matplotlib.lines as mlines
        except ImportError:
            _log.warning("[SC] matplotlib not installed")
            return None

        fig, ax = plt.subplots(figsize=figsize)

        r = self._result
        treat_idx = self.treat_period_idx

        # Plot placebo units (donor paths)
        unit_placebo = r.additional.get("inference", {}).get("unit_placebo_df")
        if unit_placebo is not None and not unit_placebo.empty:
            top_placebos = unit_placebo.dropna(subset=["rmspe_ratio"]).nlargest(
                n_top_donors, "rmspe_ratio"
            )
            for _, row in top_placebos.iterrows():
                unit = row["unit"]
                unit_data = self.df[self.df[self.unit_var] == unit].sort_values(self.time_var)
                if len(unit_data) == len(r.time_index):
                    ax.plot(
                        r.time_index, unit_data[self.y_var].values,
                        color="lightgray", linewidth=0.5, alpha=0.6, zorder=1,
                    )

        # Treated unit
        ax.plot(
            r.time_index, r.treated_path,
            color="black", linewidth=2.5, label=f"Treated ({r.treat_unit})", zorder=3,
        )

        # Synthetic control
        ax.plot(
            r.time_index, r.synthetic_path,
            color="crimson", linewidth=2.0, linestyle="--",
            label="Synthetic Control", zorder=3,
        )

        # Treatment effect area
        effect_color = "crimson"
        ax.fill_between(
            r.time_index, r.treated_path, r.synthetic_path,
            where=(np.array(r.time_index) >= r.treat_period),
            alpha=0.2, color=effect_color, label="Treatment Effect",
            zorder=2,
        )

        # Vertical line at treatment period
        ax.axvline(
            x=r.treat_period, color="black", linestyle=":", linewidth=1.2,
            zorder=4,
        )

        # Annotation
        post_mask = [t >= r.treat_period for t in r.time_index]
        avg_effect = float(np.mean(np.array(r.effect_path)[post_mask]))
        ax.annotate(
            f"Avg Effect: {avg_effect:+.3f}",
            xy=(r.time_index[len(r.time_index) // 2], max(r.treated_path[-1], r.synthetic_path[-1])),
            fontsize=9, color="crimson",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="lightgray"),
        )

        ax.set_xlabel(f"{self.time_var.capitalize()}", fontsize=12)
        ax.set_ylabel(self.y_var, fontsize=12)
        ax.set_title(
            f"Synthetic Control: {r.treat_unit} vs Synthetic Counterfactual",
            fontsize=13, fontweight="bold",
        )

        # Legend
        handles = [
            mlines.Line2D([], [], color="black", linewidth=2.5,
                          label=f"Treated ({r.treat_unit})"),
            mlines.Line2D([], [], color="crimson", linewidth=2.0, linestyle="--",
                          label="Synthetic Control"),
            mlines.Line2D([], [], color="lightgray", linewidth=0.8,
                          label="Placebo Units"),
            plt.fill_between([], [], alpha=0.2, color="crimson",
                             label="Treatment Effect"),
        ]
        ax.legend(handles=handles, loc="best", fontsize=9)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SC] Placebo figure saved: {save_path}")

        return fig

    def plot_donor_weights(
        self,
        top_n: int = 20,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 6),
    ) -> Any:
        """
        Plot horizontal bar chart of donor unit weights.

        Parameters
        ----------
        top_n : int
            Show top N donors by weight.
        save_path : str | Path | None
            Save figure.
        figsize : tuple
            Figure size.

        Returns
        -------
        matplotlib Figure or None
        """
        if self._result is None:
            self.fit()

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[SC] matplotlib not installed")
            return None

        weight_df = self._result.donor_report()
        if weight_df.empty:
            _log.warning("[SC] No donor weights to plot")
            return None

        weight_df = weight_df.head(top_n)

        fig, ax = plt.subplots(figsize=figsize)
        colors = [
            "crimson" if w > 0.1 else "steelblue" if w > 0 else "lightgray"
            for w in weight_df["weight"].values
        ]
        bars = ax.barh(
            weight_df["donor"].astype(str), weight_df["weight"],
            color=colors, edgecolor="white",
        )
        ax.axvline(x=0, color="black", linewidth=0.8)
        ax.set_xlabel("Donor Weight", fontsize=12)
        ax.set_ylabel("Donor Unit", fontsize=12)
        ax.set_title(
            f"Donor Weights: Synthetic Control for {self._result.treat_unit}",
            fontsize=13, fontweight="bold",
        )
        ax.invert_yaxis()
        ax.grid(True, axis="x", alpha=0.3)

        # Add weight labels
        for bar, w in zip(bars, weight_df["weight"].values):
            ax.text(
                bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
                f"{w:.3f}", va="center", fontsize=8,
            )

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SC] Donor weights figure saved: {save_path}")

        return fig

    def plot_rmspe_ratio(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (9, 5),
    ) -> Any:
        """
        Plot RMSPE ratio distribution for permutation inference.

        Shows the treated unit's ratio relative to all placebo units.
        """
        if self._result is None:
            self.fit()

        inference = self._result.additional.get("inference", {})
        perm = inference.get("permutation", {})
        ratios = perm.get("ratios", {})

        if not ratios:
            _log.warning("[SC] No permutation results — run inference() first")
            return None

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return None

        fig, ax = plt.subplots(figsize=figsize)

        units = list(ratios.keys())
        values = list(ratios.values())
        colors = ["crimson" if u == self.treat_unit else "steelblue" for u in units]

        sorted_idx = np.argsort(values)[::-1]
        ax.bar(
            [str(units[i]) for i in sorted_idx],
            [values[i] for i in sorted_idx],
            color=[colors[i] for i in sorted_idx],
            edgecolor="white",
        )

        ax.axhline(
            y=ratios.get(self.treat_unit, 0),
            color="crimson", linestyle="--", linewidth=1.2,
            label=f"Treated ratio: {ratios.get(self.treat_unit, 0):.2f}",
        )

        p_val = perm.get("p_value", np.nan)
        if not np.isnan(p_val):
            ax.set_title(
                f"RMSPE Ratio: Permutation Inference (p={p_val:.3f})",
                fontsize=13, fontweight="bold",
            )
        else:
            ax.set_title("RMSPE Ratio: Permutation Inference", fontsize=13, fontweight="bold")

        ax.set_xlabel("Unit", fontsize=11)
        ax.set_ylabel("RMSPE Ratio (Post / Pre)", fontsize=11)
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, axis="y", alpha=0.3)
        ax.legend()

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SC] RMSPE ratio figure saved: {save_path}")

        return fig

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """Summarize SC results."""
        if self._result is None:
            self.fit()

        r = self._result
        perm = r.additional.get("inference", {}).get("permutation", {})

        return pd.DataFrame([{
            "Treat Unit": r.treat_unit,
            "Treat Period": r.treat_period,
            "N Donors": r.n_donors,
            "N Pre Periods": r.n_pre_periods,
            "N Post Periods": r.n_post_periods,
            "Pre MSPE": r.pre_mspe,
            "Post MSPE": r.post_mspe,
            "RMSPE Ratio": r.rmspe_ratio,
            "R2 (Pre)": r.r_squared_pre,
            "Perm p-value": perm.get("p_value", np.nan),
            "Perm Rank": perm.get("rank", np.nan),
            "Method": "Augmented SC" if r.augment else "SC",
        }])

    def to_latex(self) -> str:
        """Export summary to LaTeX table."""
        df = self.summary()
        if df.empty:
            return ""

        caption = f"\\caption{{Synthetic Control: {self.treat_unit}}}"
        label = "\\label{tab:sc}"

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  {caption}",
            f"  {label}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lc}",
            "    \\toprule",
            "    \\textbf{Statistic} & \\textbf{Value} \\\\ ",
            "    \\midrule",
        ]

        col_map = {
            "Treat Unit": "Treat Unit",
            "Treat Period": "Treat Period",
            "N Donors": "N Donors",
            "Pre MSPE": "Pre MSPE",
            "Post MSPE": "Post MSPE",
            "RMSPE Ratio": "RMSPE Ratio",
            "R2 (Pre)": "R$^2$ (Pre)",
            "Perm p-value": "Perm. p-value",
        }

        for _, row in df.iterrows():
            for col, label_text in col_map.items():
                val = row.get(col, "")
                if isinstance(val, float):
                    lines.append(f"    {label_text} & {val:.4f} \\\\")
                else:
                    lines.append(f"    {label_text} & {val} \\\\")

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Pre / Post MSPE = Mean Squared Prediction Error.",
            "    \\item RMSPE Ratio = Post MSPE / Pre MSPE.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)
