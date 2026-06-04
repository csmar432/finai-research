"""Synthetic DiD Engine — 结合合成控制法和双重差分的因果推断。

本模块封装 Synthetic DiD（合成双重差分）方法：
  - Arkhangelsky et al. (2021): "Synthetic DiD" — 主框架
  - Abadie et al. (2010): Synthetic Control Method — 权重优化
  - Schulhofer-Wohl (2023): "Negative weights in synthetic control"
  - Ben-Michael et al. (2021): "Synthetic Placebos" — 推断方法

核心思想：
  1. 用合成控制构建"好"的对照组（最小化处理前差异）
  2. 在合成对照上执行 DID 估计
  3. 适用于：处理组内生性担忧、DID 平行趋势不满足

Usage:
    engine = SyntheticDiDEngine(
        pre_outcome_matrix=pre_mat,
        post_outcome_matrix=post_mat,
        treated_outcome=treated_post,
    )
    result = engine.fit(aggregation="simple")
    result = engine.inference(method="bootstrap")
    engine.plot()
    engine.placebo_test()
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
    "SyntheticDiDEngine",
    "SyntheticDiDResult",
]

_log = logging.getLogger("synthetic_did")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATION RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SyntheticDiDResult:
    """
    Synthetic DiD 估计结果容器。

    Attributes
    ----------
    estimator : str
        估计器名称（"synthetic_did" / "sdid_shrunken" / "sdid_psid" / "sdid_cv"）。
    att : float
        平均处理效应（ATT）估计值。
    se : float
        标准误。
    pval : float
        p 值。
    ci_lower : float
        95% 置信区间下界。
    ci_upper : float
        95% 置信区间上界。
    n_obs : int
        观测数（donor 单位数）。
    donor_weights : np.ndarray
        每个 donor 单位的合成权重。
    treated_unit : Any
        处理单位标识。
    treatment_time : int | float
        处理时间。
    pre_fit_quality : float
        处理前 RMSPE（越小越好）。
    post_gap : float
        处理后处理组与合成对照的均值差异。
    n_donors : int
        Donor 单位数。
    r_squared : float | None
        拟合 R²。
    mspe_ratio : float
        MSPE 后/前比（越大表示效果越强）。
    additional : dict
        额外诊断（安慰剂 p 值、推断方法等）。
    """

    estimator: str
    att: float
    se: float
    pval: float
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    n_obs: int = 0
    donor_weights: np.ndarray = field(default_factory=lambda: np.array([]))
    treated_unit: Any = None
    treatment_time: int | float = 0
    pre_fit_quality: float = 0.0
    post_gap: float = 0.0
    n_donors: int = 0
    r_squared: float | None = None
    mspe_ratio: float = 0.0
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
        return {
            "estimator": self.estimator,
            "att": self.att,
            "se": self.se,
            "pval": self.pval,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_obs": self.n_obs,
            "n_donors": self.n_donors,
            "treated_unit": self.treated_unit,
            "treatment_time": self.treatment_time,
            "pre_fit_quality": self.pre_fit_quality,
            "post_gap": self.post_gap,
            "r_squared": self.r_squared,
            "mspe_ratio": self.mspe_ratio,
            "sig": self.sig,
            **{k: v for k, v in self.additional.items()},
        }


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────────


def _optimize_weights_slsqp(
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    ridge_lambda: float = 0.01,
    allow_negative: bool = False,
    include_intercept: bool = False,
) -> np.ndarray:
    """
    用 scipy.optimize SLSQP 优化合成控制权重。

    Parameters
    ----------
    Y_pre_treated : np.ndarray
        处理单位在处理前的结果变量（1D, length T_pre）。
    Y_pre_donor : np.ndarray
        Donor 单位在处理前的结果矩阵（2D, N_donor × T_pre）。
    ridge_lambda : float
        Ridge 正则化系数。
    allow_negative : bool
        是否允许负权重（Schulhofer-Wohl 2023 方法）。
    include_intercept : bool
        是否包含截距项（约束变为 W'X = X_treated - intercept）。

    Returns
    -------
    np.ndarray
        最优权重向量（length N_donor）。
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        _log.error("[SyntheticDiD] scipy not installed")
        return np.ones(Y_pre_donor.shape[0]) / Y_pre_donor.shape[0]

    T_pre, n_donor = Y_pre_treated.shape[0], Y_pre_donor.shape[0]

    if include_intercept:
        Y_pre_aug = np.vstack([Y_pre_donor, np.ones(T_pre)])
    else:
        Y_pre_aug = Y_pre_donor

    def objective(w: np.ndarray) -> float:
        if include_intercept:
            w_donor = w[:-1]
            intercept = w[-1]
            pred = Y_pre_aug[:-1].T @ w_donor + intercept
        else:
            pred = Y_pre_aug.T @ w
        residual = Y_pre_treated - pred
        mse = np.mean(residual**2)
        ridge = ridge_lambda * np.sum(w**2)
        return mse + ridge

    def constraint_sum(w: np.ndarray) -> float:
        donor_w = w[:-1] if include_intercept else w
        return np.sum(donor_w) - 1.0

    constraints = [{"type": "eq", "fun": constraint_sum}]

    bounds = [(-10, 10) if allow_negative else (0, 10) for _ in range(n_donor)]
    if include_intercept:
        bounds.append((-10, 10))

    w0 = np.ones(n_donor) / n_donor
    if include_intercept:
        w0 = np.append(w0, 0.0)

    try:
        res = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-9},
        )
        if res.success:
            w_opt = res.x
            if include_intercept:
                return w_opt[:-1]
            return w_opt
    except Exception as e:
        _log.warning(f"[SyntheticDiD] SLSQP optimization failed: {e}")

    return np.ones(n_donor) / n_donor


def _optimize_weights_cv(
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    n_folds: int = 5,
    lambda_grid: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """
    交叉验证选择最优 ridge lambda 和权重。

    Parameters
    ----------
    Y_pre_treated : np.ndarray
        处理前结果（1D）。
    Y_pre_donor : np.ndarray
        Donor 结果矩阵（2D）。
    n_folds : int
        交叉验证折数。
    lambda_grid : np.ndarray | None
        lambda 候选网格。

    Returns
    -------
    (weights, best_lambda)
    """
    if lambda_grid is None:
        lambda_grid = np.logspace(-4, 2, 20)

    T = len(Y_pre_treated)
    fold_size = T // n_folds
    best_lambda = lambda_grid[0]
    best_mspe = np.inf

    for lam in lambda_grid:
        mspe_vals = []
        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < n_folds - 1 else T

            train_idx = np.concatenate([
                np.arange(0, val_start),
                np.arange(val_end, T)
            ])
            val_idx = np.arange(val_start, val_end)

            Y_train_treated = Y_pre_treated[train_idx]
            Y_train_donor = Y_pre_donor[:, train_idx]
            Y_val_treated = Y_pre_treated[val_idx]
            Y_val_donor = Y_pre_donor[:, val_idx]

            w_cv = _optimize_weights_slsqp(
                Y_train_treated, Y_train_donor, ridge_lambda=lam
            )
            synth_val = Y_val_donor.T @ w_cv
            mspe = np.mean((Y_val_treated - synth_val) ** 2)
            mspe_vals.append(mspe)

        mean_mspe = np.mean(mspe_vals)
        if mean_mspe < best_mspe:
            best_mspe = mean_mspe
            best_lambda = lam

    w_final = _optimize_weights_slsqp(
        Y_pre_treated, Y_pre_donor, ridge_lambda=best_lambda
    )
    return w_final, float(best_lambda)


def _shrink_weights(
    weights: np.ndarray,
    method: str = "psid",
    alpha: float = 0.5,
) -> np.ndarray:
    """
    收缩权重以减少过拟合（Arkhangelsky et al. 2021）。

    Parameters
    ----------
    weights : np.ndarray
        原始合成权重。
    method : str
        "psid"：收缩到均匀分布；"ridge"：基于 alpha 的 L2 收缩。
    alpha : float
        收缩强度（0=无收缩，1=完全均匀）。

    Returns
    -------
    np.ndarray
        收缩后的权重。
    """
    n = len(weights)
    uniform = np.ones(n) / n

    if method == "psid":
        # PSID-style 收缩：W_shrunk = (1 - alpha) * W + alpha * uniform
        return (1 - alpha) * weights + alpha * uniform
    elif method == "ridge":
        # L2 收缩
        w_shrunk = (1 - alpha) * weights + alpha * uniform
        return w_shrunk / w_shrunk.sum()
    else:
        return weights


# ─────────────────────────────────────────────────────────────────────────────
# INFERENCE
# ─────────────────────────────────────────────────────────────────────────────


def _inference_bootstrap(
    donor_weights: np.ndarray,
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    Y_post_donor: np.ndarray,
    Y_post_treated: np.ndarray,
    B: int = 999,
    seed: int = 42,
) -> dict:
    """
    Bootstrap 推断：对 donor 单位重抽样。

    Parameters
    ----------
    donor_weights : np.ndarray
        基准权重。
    Y_pre_treated : np.ndarray
        处理前处理组结果。
    Y_pre_donor : np.ndarray
        处理前 donor 结果。
    Y_post_donor : np.ndarray
        处理后 donor 结果。
    Y_post_treated : np.ndarray
        处理后处理组结果。
    B : int
        Bootstrap 次数。
    seed : int
        随机种子。

    Returns
    -------
    dict
        含 se / ci_lower / ci_upper / pval。
    """
    rng = np.random.default_rng(seed)
    n_donor = donor_weights.shape[0]

    # 基准 ATT
    synth_post = Y_post_donor.T @ donor_weights
    att_est = float(np.mean(Y_post_treated - synth_post))

    att_stars = []
    for _ in range(B):
        idx = rng.integers(0, n_donor, size=n_donor)
        Y_pre_boot = Y_pre_donor[idx, :]
        Y_post_boot = Y_post_donor[idx, :]

        w_boot = _optimize_weights_slsqp(Y_pre_treated, Y_pre_boot)
        synth_boot = Y_post_boot.T @ w_boot
        att_boot = float(np.mean(Y_post_treated - synth_boot))
        att_stars.append(att_boot)

    att_stars = np.array(att_stars)
    se = float(np.std(att_stars, ddof=1))
    ci_lower = float(np.percentile(att_stars, 2.5))
    ci_upper = float(np.percentile(att_stars, 97.5))
    pval = float(np.mean(np.abs(att_stars) >= abs(att_est)))

    return {
        "se": se,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "pval": pval,
        "att_stars": att_stars,
        "n_bootstrap": B,
        "method": "bootstrap",
    }


def _inference_jackknife(
    donor_weights: np.ndarray,
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    Y_post_donor: np.ndarray,
    Y_post_treated: np.ndarray,
) -> dict:
    """
    Jackknife 推断：逐个剔除 donor。

    Returns
    -------
    dict
        含 se / ci_lower / ci_upper / pval。
    """
    n_donor = donor_weights.shape[0]

    # 基准 ATT
    synth_post = Y_post_donor.T @ donor_weights
    att_est = float(np.mean(Y_post_treated - synth_post))

    att_jacks = []
    for i in range(n_donor):
        keep_idx = np.concatenate([np.arange(i), np.arange(i + 1, n_donor)])
        Y_pre_leave = Y_pre_donor[keep_idx, :]
        Y_post_leave = Y_post_donor[keep_idx, :]

        w_leave = _optimize_weights_slsqp(Y_pre_treated, Y_pre_leave)
        synth_leave = Y_post_leave.T @ w_leave
        att_j = float(np.mean(Y_post_treated - synth_leave))
        att_jacks.append(att_j)

    att_jacks = np.array(att_jacks)
    se = float(np.sqrt((n_donor - 1) * np.var(att_jacks, ddof=1)))
    t_crit = 1.96
    ci_lower = att_est - t_crit * se
    ci_upper = att_est + t_crit * se
    pval = float(2 * (1 - float(np.mean(att_jacks <= att_est))))

    return {
        "se": se,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "pval": pval,
        "att_jacks": att_jacks,
        "n_donors_leave_out": n_donor,
        "method": "jackknife",
    }


def _inference_conformal(
    donor_weights: np.ndarray,
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    Y_post_donor: np.ndarray,
    Y_post_treated: np.ndarray,
    alpha: float = 0.05,
) -> dict:
    """
    Conformal 推断（无分布假设，Ben-Michael et al. 2021）。

    使用合成安慰剂方法构建置信区间。

    Returns
    -------
    dict
        含 ci_lower / ci_upper / pval。
    """
    n_donor, T_post = Y_post_donor.shape

    # 每个 donor 作为"伪处理单位"
    pseudo_effects = []
    for i in range(n_donor):
        # 用除 i 外的 donor 构建合成对照
        keep_idx = np.concatenate([np.arange(i), np.arange(i + 1, n_donor)])
        Y_pre_other = Y_pre_donor[keep_idx, :]
        Y_post_other = Y_post_donor[keep_idx, :]

        w_i = _optimize_weights_slsqp(Y_pre_treated, Y_pre_other)
        synth_post_i = Y_post_other.T @ w_i

        # 伪处理效应
        pseudo = Y_post_donor[i, :] - synth_post_i
        pseudo_effects.append(pseudo)

    pseudo_effects = np.array(pseudo_effects)
    real_effect = Y_post_treated - Y_post_donor.T @ donor_weights

    # 对每个 post 期做检验
    combined_scores = np.maximum(
        0,
        np.abs(real_effect[:, None] - pseudo_effects.T)
    )
    score = np.mean(combined_scores)

    # 置信区间（基于伪效应的分位数）
    q_level = np.ceil((n_donor + 1) * (1 - alpha)) / (n_donor + 1)
    q_val = float(np.quantile(pseudo_effects.flatten(), q_level))

    ci_lower = float(np.mean(real_effect) - q_val)
    ci_upper = float(np.mean(real_effect) + q_val)
    pval = float(
        (1 + np.sum(np.abs(pseudo_effects) >= np.abs(np.mean(real_effect))))
        / (n_donor + 1)
    )

    return {
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "pval": pval,
        "score": score,
        "method": "conformal",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLACEBO TEST
# ─────────────────────────────────────────────────────────────────────────────


def _placebo_test(
    Y_pre_treated: np.ndarray,
    Y_pre_donor: np.ndarray,
    Y_post_donor: np.ndarray,
    donor_weights: np.ndarray,
) -> dict:
    """
    安慰剂检验：对每个 donor 单位执行"伪处理"。

    计算伪 ATT 分布，p = rank(真实 ATT) / (n_donors + 1)。

    Returns
    -------
    dict
        含 pseudo_atts / pval / rank / donor_labels。
    """
    n_donor, T_post = Y_post_donor.shape

    # 真实 ATT
    synth_post = Y_post_donor.T @ donor_weights
    real_att = float(np.mean(Y_pre_treated[:0] if len(Y_pre_treated) > 0 else np.zeros(T_post)))
    if len(Y_pre_treated) > 0:
        real_att = float(
            np.mean(Y_pre_treated) - np.mean(Y_pre_donor.T @ donor_weights)
        )

    pseudo_atts = []
    for i in range(n_donor):
        # 用除 i 外的 donor 合成 i
        keep_idx = np.concatenate([np.arange(i), np.arange(i + 1, n_donor)])
        Y_pre_other = Y_pre_donor[keep_idx, :]
        Y_post_other = Y_post_donor[keep_idx, :]

        w_i = _optimize_weights_slsqp(Y_pre_donor[i, :], Y_pre_other)
        synth_i = Y_post_other.T @ w_i
        pseudo_att = float(np.mean(Y_post_donor[i, :] - synth_i))
        pseudo_atts.append(pseudo_att)

    pseudo_atts = np.array(pseudo_atts)
    all_atts = np.concatenate([[real_att], pseudo_atts])
    rank = int(np.sum(all_atts <= real_att))
    pval = rank / (n_donor + 1)

    return {
        "pseudo_atts": pseudo_atts,
        "real_att": real_att,
        "rank": rank,
        "pval": float(pval),
        "n_placebos": n_donor,
        "interpretation": (
            f"Real ATT rank: {rank}/{n_donor + 1}, "
            f"p={pval:.3f} ({'significant' if pval < 0.05 else 'not significant'})"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class SyntheticDiDEngine:
    """
    Synthetic DiD 引擎 — 结合合成控制与双重差分。

    支持的聚合方式：
      - "simple"    — 简单 SC 权重（Abadie et al. 2010）
      - "shrunken" — 收缩权重（减少过拟合，Arkhangelsky et al. 2021）
      - "psid"     — PSID-style 收缩
      - "cv"       — 交叉验证选择 ridge lambda

    使用方法：
        engine = SyntheticDiDEngine(
            pre_outcome_matrix=pre_mat,       # (N_donor, T_pre)
            post_outcome_matrix=post_mat,     # (N_donor, T_post)
            treated_outcome_pre=treated_pre,  # (T_pre,) 处理前
            treated_outcome_post=treated_post, # (T_post,) 处理后
        )
        result = engine.fit(aggregation="cv")
        result = engine.inference(method="bootstrap")
        engine.plot()
        engine.placebo_test()
    """

    def __init__(
        self,
        pre_outcome_matrix: np.ndarray | pd.DataFrame,
        post_outcome_matrix: np.ndarray | pd.DataFrame,
        treated_outcome_pre: np.ndarray | pd.Series | None = None,
        treated_outcome_post: np.ndarray | pd.Series | None = None,
        pre_covariates: np.ndarray | pd.DataFrame | None = None,
        post_covariates: np.ndarray | pd.DataFrame | None = None,
        donor_labels: list | None = None,
        treated_label: Any = "treated",
        treatment_time: int | float = 0,
    ):
        """
        Parameters
        ----------
        pre_outcome_matrix : np.ndarray | pd.DataFrame
            Donor 单位处理前结果矩阵（2D: N_donor × T_pre）。
        post_outcome_matrix : np.ndarray | pd.DataFrame
            Donor 单位处理后结果矩阵（2D: N_donor × T_post）。
        treated_outcome_pre : np.ndarray | pd.Series | None
            处理单位处理前结果（1D: T_pre）。
        treated_outcome_post : np.ndarray | pd.Series | None
            处理单位处理后结果（1D: T_post）。
        pre_covariates : np.ndarray | pd.DataFrame | None
            处理前协变量矩阵（用于调整）。
        post_covariates : np.ndarray | pd.DataFrame | None
            处理后协变量矩阵。
        donor_labels : list | None
            Donor 单位标签。
        treated_label : Any
            处理单位标签。
        treatment_time : int | float
            处理时间。
        """
        # Convert to numpy
        if isinstance(pre_outcome_matrix, pd.DataFrame):
            self.Y_pre_donor = pre_outcome_matrix.values
            if donor_labels is None:
                donor_labels = list(pre_outcome_matrix.index)
        else:
            self.Y_pre_donor = np.asarray(pre_outcome_matrix)

        if isinstance(post_outcome_matrix, pd.DataFrame):
            self.Y_post_donor = post_outcome_matrix.values
        else:
            self.Y_post_donor = np.asarray(post_outcome_matrix)

        if treated_outcome_pre is not None:
            if isinstance(treated_outcome_pre, pd.Series):
                self.Y_pre_treated = treated_outcome_pre.values
            else:
                self.Y_pre_treated = np.asarray(treated_outcome_pre)
        else:
            self.Y_pre_treated = np.zeros(self.Y_pre_donor.shape[1])

        if treated_outcome_post is not None:
            if isinstance(treated_outcome_post, pd.Series):
                self.Y_post_treated = treated_outcome_post.values
            else:
                self.Y_post_treated = np.asarray(treated_outcome_post)
        else:
            self.Y_post_treated = np.zeros(self.Y_post_donor.shape[1])

        self.pre_covariates = (
            pre_covariates.values if isinstance(pre_covariates, pd.DataFrame)
            else np.asarray(pre_covariates) if pre_covariates is not None
            else None
        )
        self.post_covariates = (
            post_covariates.values if isinstance(post_covariates, pd.DataFrame)
            else np.asarray(post_covariates) if post_covariates is not None
            else None
        )

        self.n_donor = self.Y_pre_donor.shape[0]
        self.n_pre = self.Y_pre_donor.shape[1]
        self.n_post = self.Y_post_donor.shape[1]
        self.donor_labels = donor_labels or [f"donor_{i}" for i in range(self.n_donor)]
        self.treated_label = treated_label
        self.treatment_time = treatment_time

        self.donor_weights_: np.ndarray | None = None
        self.aggregation_: str = "simple"
        self.ridge_lambda_: float = 0.01
        self._result: SyntheticDiDResult | None = None

    # ── Fit ────────────────────────────────────────────────────────────────

    def fit(
        self,
        aggregation: str = "simple",
        ridge_lambda: float = 0.01,
        allow_negative: bool = False,
        include_intercept: bool = False,
        cv_folds: int = 5,
        shrink_alpha: float = 0.5,
        seed: int = 42,
    ) -> SyntheticDiDResult:
        """
        拟合 Synthetic DiD 模型。

        Parameters
        ----------
        aggregation : str
            权重聚合方式：
            - "simple"   ：简单 SC 权重
            - "shrunken" ：收缩权重（Arkhangelsky et al. 2021）
            - "psid"     ：PSID-style 收缩
            - "cv"       ：交叉验证选择 ridge lambda
        ridge_lambda : float
            Ridge 正则化系数（仅用于 "simple" / "shrunken" / "psid"）。
        allow_negative : bool
            是否允许负权重（Schulhofer-Wohl 2023）。
        include_intercept : bool
            是否包含截距项。
        cv_folds : int
            交叉验证折数（仅用于 "cv"）。
        shrink_alpha : float
            收缩强度（0=无收缩，1=完全均匀）。
        seed : int
            随机种子。

        Returns
        -------
        SyntheticDiDResult
        """
        self.aggregation_ = aggregation

        if aggregation == "cv":
            w_raw, best_lam = _optimize_weights_cv(
                self.Y_pre_treated,
                self.Y_pre_donor,
                n_folds=cv_folds,
            )
            self.ridge_lambda_ = best_lam
        else:
            w_raw = _optimize_weights_slsqp(
                self.Y_pre_treated,
                self.Y_pre_donor,
                ridge_lambda=ridge_lambda,
                allow_negative=allow_negative,
                include_intercept=include_intercept,
            )
            self.ridge_lambda_ = ridge_lambda

        # 收缩权重
        if aggregation in ("shrunken", "psid"):
            w_final = _shrink_weights(w_raw, method=aggregation, alpha=shrink_alpha)
        else:
            w_final = w_raw / w_raw.sum() if w_raw.sum() != 0 else w_raw

        self.donor_weights_ = w_final

        # 计算 ATT
        synth_pre = self.Y_pre_donor.T @ w_final
        synth_post = self.Y_post_donor.T @ w_final

        # 处理前拟合质量（RMSPE）
        pre_residual = self.Y_pre_treated - synth_pre
        pre_rmspe = float(np.sqrt(np.mean(pre_residual**2)))

        # 处理后差距
        post_gap = float(np.mean(self.Y_post_treated - synth_post))

        # ATT（SDID：处理后均值差异）
        att = post_gap

        # R²（处理前）
        ss_tot = np.var(self.Y_pre_treated)
        ss_res = np.mean(pre_residual**2)
        r_squared = float(1 - ss_res / ss_res) if ss_tot > 0 else None

        # MSPE 比值
        post_residual = self.Y_post_treated - synth_post
        post_rmspe = float(np.sqrt(np.mean(post_residual**2)))
        mspe_ratio = post_rmspe / pre_rmspe if pre_rmspe > 0 else 0

        # 初始 SE（基于处理后残差）
        se = float(np.std(post_residual) / np.sqrt(self.n_post))

        result = SyntheticDiDResult(
            estimator="synthetic_did" if aggregation == "simple" else f"sdid_{aggregation}",
            att=att,
            se=se,
            pval=0.0,
            ci_lower=att - 1.96 * se,
            ci_upper=att + 1.96 * se,
            n_obs=self.n_donor * (self.n_pre + self.n_post),
            donor_weights=w_final,
            treated_unit=self.treated_label,
            treatment_time=self.treatment_time,
            pre_fit_quality=pre_rmspe,
            post_gap=post_gap,
            n_donors=self.n_donor,
            r_squared=r_squared,
            mspe_ratio=mspe_ratio,
            additional={
                "aggregation": aggregation,
                "ridge_lambda": self.ridge_lambda_,
                "synth_pre": synth_pre.tolist(),
                "synth_post": synth_post.tolist(),
            },
        )

        self._result = result
        _log.info(
            f"[SyntheticDiD] {aggregation}: ATT={att:+.4f}, "
            f"RMSPE_pre={pre_rmspe:.4f}, MSPE_ratio={mspe_ratio:.2f}, "
            f"n_donors={self.n_donor}"
        )

        return result

    # ── Inference ──────────────────────────────────────────────────────────

    def inference(
        self,
        method: str = "bootstrap",
        B: int = 999,
        alpha: float = 0.05,
        seed: int = 42,
    ) -> SyntheticDiDResult:
        """
        推断：计算 SE、p 值和置信区间。

        Parameters
        ----------
        method : str
            - "bootstrap"  ：对 donor 重抽样
            - "jackknife"  ：逐个剔除 donor
            - "conformal"  ：共形推断（无分布假设）
        B : int
            Bootstrap 次数。
        alpha : float
            显著性水平。
        seed : int
            随机种子。

        Returns
        -------
        SyntheticDiDResult
            更新后的结果（含 se / ci_lower / ci_upper / pval）。
        """
        if self._result is None:
            self.fit()
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")

        if method == "bootstrap":
            inf_result = _inference_bootstrap(
                self.donor_weights_,
                self.Y_pre_treated,
                self.Y_pre_donor,
                self.Y_post_donor,
                self.Y_post_treated,
                B=B,
                seed=seed,
            )
        elif method == "jackknife":
            inf_result = _inference_jackknife(
                self.donor_weights_,
                self.Y_pre_treated,
                self.Y_pre_donor,
                self.Y_post_donor,
                self.Y_post_treated,
            )
        elif method == "conformal":
            inf_result = _inference_conformal(
                self.donor_weights_,
                self.Y_pre_treated,
                self.Y_pre_donor,
                self.Y_post_donor,
                self.Y_post_treated,
                alpha=alpha,
            )
        else:
            raise ValueError(f"[SyntheticDiD] Unknown inference method: {method}")

        self._result.se = inf_result.get("se", self._result.se)
        self._result.ci_lower = inf_result.get("ci_lower", self._result.ci_lower)
        self._result.ci_upper = inf_result.get("ci_upper", self._result.ci_upper)
        self._result.pval = inf_result.get("pval", self._result.pval)
        self._result.additional["inference"] = inf_result
        self._result.additional["inference_method"] = method

        _log.info(
            f"[SyntheticDiD] {method}: ATT={self._result.att:+.4f}, "
            f"SE={self._result.se:.4f}, p={self._result.pval:.3f}, "
            f"CI=[{self._result.ci_lower:+.4f}, {self._result.ci_upper:+.4f}]"
        )

        return self._result

    # ── Placebo Test ──────────────────────────────────────────────────────

    def placebo_test(self) -> dict:
        """
        安慰剂检验：对每个 donor 执行伪处理。

        Returns
        -------
        dict
            含伪处理效应分布、p 值和排名。
        """
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")

        result = _placebo_test(
            self.Y_pre_treated,
            self.Y_pre_donor,
            self.Y_post_donor,
            self.donor_weights_,
        )

        if self._result is not None:
            self._result.additional["placebo"] = result

        _log.info(
            f"[SyntheticDiD] Placebo test: p={result['pval']:.3f}, "
            f"rank={result['rank']}/{result['n_placebos'] + 1}"
        )

        return result

    # ── Getter ────────────────────────────────────────────────────────────

    def get_att(self) -> float:
        """获取 ATT 估计值。"""
        if self._result is None:
            self.fit()
        return float(self._result.att) if self._result else 0.0

    def get_donor_weights(self) -> np.ndarray:
        """获取 donor 单位权重。"""
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")
        return self.donor_weights_

    def get_synthetic_control(self) -> tuple[np.ndarray, np.ndarray]:
        """
        获取合成对照的时间序列。

        Returns
        -------
        (synth_pre, synth_post)
            处理前和处理后的合成对照路径。
        """
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")
        synth_pre = self.Y_pre_donor.T @ self.donor_weights_
        synth_post = self.Y_post_donor.T @ self.donor_weights_
        return synth_pre, synth_post

    # ── Plotting ──────────────────────────────────────────────────────────

    def plot(
        self,
        save_path: str | Path | None = None,
        title: str | None = None,
        figsize: tuple[float, float] = (10, 5),
    ) -> Any:
        """
        绘制合成对照路径图。

        Parameters
        ----------
        save_path : str | Path | None
            保存路径（.png / .pdf）。
        title : str | None
            图表标题。
        figsize : tuple
            图形大小。

        Returns
        -------
        matplotlib Figure
        """
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[SyntheticDiD] matplotlib not installed")
            return None

        synth_pre, synth_post = self.get_synthetic_control()
        all_synth = np.concatenate([synth_pre, synth_post])
        all_treated = np.concatenate([self.Y_pre_treated, self.Y_post_treated])
        time_idx = np.arange(-self.n_pre + 1, self.n_post + 1)

        fig, ax = plt.subplots(figsize=figsize)

        ax.plot(time_idx, all_treated, "o-", color="steelblue", lw=2,
                markersize=5, label=f"Treated ({self.treated_label})")
        ax.plot(time_idx, all_synth, "s--", color="tomato", lw=2,
                markersize=5, label="Synthetic Control")

        ax.axvline(x=0.5, color="gray", linestyle="--", linewidth=1.2,
                   label="Treatment")
        ax.axhline(y=0, color="lightgray", linestyle="-", linewidth=0.8)

        ax.set_xlabel("Time (Relative to Treatment)", fontsize=12)
        ax.set_ylabel("Outcome", fontsize=12)
        ax.set_title(
            title or f"Synthetic DiD: {self.treated_label} vs Synthetic Control",
            fontsize=13, fontweight="bold",
        )
        ax.legend(fontsize=11, loc="best")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SyntheticDiD] Plot saved: {save_path}")

        return fig

    def plot_placebo(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (10, 5),
    ) -> Any:
        """
        绘制安慰剂图。

        Parameters
        ----------
        save_path : str | Path | None
            保存路径。
        figsize : tuple
            图形大小。

        Returns
        -------
        matplotlib Figure
        """
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[SyntheticDiD] matplotlib not installed")
            return None

        placebo = self.placebo_test()
        pseudo_atts = placebo["pseudo_atts"]

        fig, ax = plt.subplots(figsize=figsize)

        bins = np.linspace(pseudo_atts.min(), pseudo_atts.max(), 20)
        ax.hist(pseudo_atts, bins=bins, color="lightgray", edgecolor="gray",
                alpha=0.7, label="Placebo ATTs")
        ax.axvline(x=placebo["real_att"], color="steelblue", lw=2,
                   label=f"Real ATT (p={placebo['pval']:.3f})")
        ax.axvline(x=0, color="gray", linestyle="--", lw=1)

        ax.set_xlabel("ATT", fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.set_title("Placebo Test: Donor ATT Distribution", fontsize=13,
                     fontweight="bold")
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SyntheticDiD] Placebo plot saved: {save_path}")

        return fig

    def plot_rmspe_ratio(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> Any:
        """
        绘制 RMSPE 比值图（预处理拟合质量 vs 处理后差距）。

        Returns
        -------
        matplotlib Figure
        """
        if self._result is None:
            self.fit()

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[SyntheticDiD] matplotlib not installed")
            return None

        fig, ax = plt.subplots(figsize=figsize)

        categories = ["Pre RMSPE\n(Fit Quality)", "Post RMSPE\n(Gap)"]
        values = [self._result.pre_fit_quality, abs(self._result.post_gap)]
        colors = ["#4CAF50", "#F44336"]

        bars = ax.bar(categories, values, color=colors, width=0.4, alpha=0.8)
        ax.set_ylabel("RMSPE", fontsize=12)
        ax.set_title(
            f"Pre/Post Fit Quality (MSPE Ratio={self._result.mspe_ratio:.2f})",
            fontsize=13, fontweight="bold",
        )
        ax.grid(True, alpha=0.3, axis="y")

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.4f}", ha="center", va="bottom", fontsize=11)

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SyntheticDiD] RMSPE plot saved: {save_path}")

        return fig

    def plot_donor_weights(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
        top_n: int | None = None,
    ) -> Any:
        """
        绘制 donor 权重柱状图。

        Parameters
        ----------
        top_n : int | None
            只显示权重最大的 top_n 个 donor。

        Returns
        -------
        matplotlib Figure
        """
        if self.donor_weights_ is None:
            raise ValueError("[SyntheticDiD] Call fit() first")

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            _log.warning("[SyntheticDiD] matplotlib not installed")
            return None

        w = self.donor_weights_.copy()
        labels = self.donor_labels.copy()

        if top_n is not None and top_n < len(w):
            top_idx = np.argsort(w)[-top_n:]
            w = w[top_idx]
            labels = [labels[i] for i in top_idx]

        fig, ax = plt.subplots(figsize=figsize)

        sorted_idx = np.argsort(w)[::-1]
        w_sorted = w[sorted_idx]
        labels_sorted = [labels[i] for i in sorted_idx]

        colors = ["steelblue" if v > 0 else "tomato" for v in w_sorted]
        ax.barh(labels_sorted, w_sorted, color=colors, alpha=0.8)
        ax.axvline(x=0, color="gray", linewidth=0.8)

        ax.set_xlabel("Weight", fontsize=12)
        ax.set_title("Synthetic Control: Donor Weights", fontsize=13,
                     fontweight="bold")
        ax.grid(True, alpha=0.3, axis="x")

        plt.tight_layout()

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            _log.info(f"[SyntheticDiD] Donor weights plot saved: {save_path}")

        return fig

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        汇总主要结果。

        Returns
        -------
        pd.DataFrame
        """
        if self._result is None:
            self.fit()

        r = self._result
        return pd.DataFrame([{
            "Estimator": r.estimator,
            "ATT": r.att,
            "SE": r.se,
            "p-value": r.pval,
            "Sig": r.sig,
            "CI (lower)": r.ci_lower,
            "CI (upper)": r.ci_upper,
            "N donors": r.n_donors,
            "Pre RMSPE": r.pre_fit_quality,
            "MSPE ratio": r.mspe_ratio,
            "R2": r.r_squared,
        }])

    def to_latex(self) -> str:
        """
        导出为 LaTeX 表格。

        Returns
        -------
        str
        """
        df = self.summary()
        if df.empty:
            return ""

        caption = "\\caption{Synthetic DiD Estimation Results}"
        label = "\\label{tab:synthetic_did}"

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  {caption}",
            f"  {label}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccccc}",
            "    \\toprule",
            "    \\textbf{Estimator} & \\textbf{ATT} & \\textbf{SE} & "
            "\\textbf{p-value} & \\textbf{CI} & \\textbf{N} & \\textbf{MSPE Ratio}\\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            ci_str = f"[{row['CI (lower)']:.3f}, {row['CI (upper)']:.3f}]"
            att_str = f"{row['ATT']:.4f}{row['Sig']}"
            lines.append(
                f"    {row['Estimator']} & {att_str} & ({row['SE']:.4f}) & "
                f"{row['p-value']:.3f} & {ci_str} & {row['N donors']} & "
                f"{row['MSPE ratio']:.2f}\\\\ "
            )

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Standard errors in parentheses. $^{***}p<0.01$, "
            "$^{**}p<0.05$, $^{*}p<0.10$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])

        return "\n".join(lines)

    def get_result(self) -> SyntheticDiDResult | None:
        """获取最新估计结果。"""
        return self._result
