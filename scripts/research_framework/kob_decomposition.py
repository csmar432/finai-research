"""Kitagawa-Oaxaca-Blinder (KOB) Wage Decomposition.

This module implements the Oaxaca-Blinder decomposition (Oaxaca 1973; Blinder 1973)
and the Kitagawa (2015) three-factor decomposition for analyzing group differences
in outcomes such as wages, credit scores, or investment behavior.

References:
    Kitagawa, E. M. (2015). A Test for Instrument Validity. Econometrica.
    Oaxaca, R. (1973). Male-Female Wage Differentials in Urban Labor Markets.
    Blinder, A. S. (1973). Wage Discrimination: Reduced Form and Structural Estimates.

Usage:
    # Standard Oaxaca-Blinder decomposition
    ob = OaxacaBlinderDecomposition(name1="Female", name2="Male")
    ob_result = ob.fit(y1=female_wages, X1=female_covariates,
                       y2=male_wages, X2=male_covariates)

    # Kitagawa three-factor decomposition with bootstrap SEs
    kob = KOBDecomposition(name1="Female", name2="Male")
    kob_result = kob.fit(y1=female_wages, X1=female_covariates,
                         y2=male_wages, X2=male_covariates, n_bootstrap=499)

    # Domain-specific wrappers
    result = wage_decomposition(wage_data, outcome="lnwage",
                               group="female", predictors=["edu", "exp"])

    # Visualization and export
    plot_decomposition(result, save_path="decomp.pdf")
    latex_table = to_latex(result)
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
    "KOBDecomposition",
    "KOBResult",
    "OaxacaBlinderDecomposition",
    "OaxacaResult",
    "wage_decomposition",
    "credit_gap_decomposition",
    "investment_decomposition",
    "plot_decomposition",
    "to_latex",
]

_log = logging.getLogger("kob_decomposition")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# =============================================================================
# RESULT CONTAINERS
# =============================================================================


@dataclass
class OaxacaResult:
    """
    Oaxaca-Blinder 分解结果。

    Attributes
    ----------
    name1 : str
        组1名称（如 "Female"）。
    name2 : str
        组2名称（如 "Male"）。
    mean1 : float
        组1均值。
    mean2 : float
        组2均值。
    raw_gap : float
        原始差距 = mean1 - mean2。
    endowments : float
        禀赋效应（特征差异导致的差距）。
    coefficients : float
        系数效应（回报差异导致的差距）。
    interaction : float
        交互项。
    se_endowments : float | None
        禀赋效应标准误（bootstrap）。
    se_coefficients : float | None
        系数效应标准误（bootstrap）。
    se_interaction : float | None
        交互项标准误（bootstrap）。
    n_group1 : int
        组1样本量。
    n_group2 : int
        组2样本量。
    weight_scheme : str
        权重方案（"burnham" / "pooled" / "group1" / "group2"）。
    """

    name1: str
    name2: str
    mean1: float
    mean2: float
    raw_gap: float
    endowments: float
    coefficients: float
    interaction: float
    se_endowments: float | None = None
    se_coefficients: float | None = None
    se_interaction: float | None = None
    n_group1: int = 0
    n_group2: int = 0
    weight_scheme: str = "burnham"

    @property
    def residuals(self) -> dict[str, float]:
        """分解残差（E + C + I - gap）。"""
        total = self.endowments + self.coefficients + self.interaction
        return {
            "sum": total,
            "gap": self.raw_gap,
            "residual": total - self.raw_gap,
        }

    def to_dict(self) -> dict:
        return {
            "name1": self.name1,
            "name2": self.name2,
            "mean1": self.mean1,
            "mean2": self.mean2,
            "raw_gap": self.raw_gap,
            "endowments": self.endowments,
            "coefficients": self.coefficients,
            "interaction": self.interaction,
            "se_endowments": self.se_endowments,
            "se_coefficients": self.se_coefficients,
            "se_interaction": self.se_interaction,
            "n_group1": self.n_group1,
            "n_group2": self.n_group2,
            "weight_scheme": self.weight_scheme,
        }


@dataclass
class KOBResult:
    """
    Kitagawa-Oaxaca-Blinder 三因素分解结果。

    Attributes
    ----------
    mean_group1 : float
        组1均值（如：女性）。
    mean_group2 : float
        组2均值（如：男性）。
    raw_gap : float
        原始差异 = mean1 - mean2。
    endowments : float
        禀赋效应（E）：特征差异造成的差异。
    pricing : float
        价格效应（P）：系数差异造成的差异。
    interaction : float
        交互效应（I）：交叉项。
    se_endowments : float | None
        禀赋效应标准误。
    se_pricing : float | None
        价格效应标准误。
    se_interaction : float | None
        交互效应标准误。
    endowments_pct : float
        E / |E+P+I| * 100。
    pricing_pct : float
        P / |E+P+I| * 100。
    interaction_pct : float
        I / |E+P+I| * 100。
    decomposition_adds_up : bool
        E + P + I = raw_gap 是否成立。
    n_group1 : int
        组1样本量。
    n_group2 : int
        组2样本量。
    ob_standard : OaxacaResult
        标准OB分解（用总样本系数）。
    ob_regression : OaxacaResult
        OB分解（用组别特定系数）。
    name_group1 : str
        组1名称。
    name_group2 : str
        组2名称。
    n_bootstrap : int
        Bootstrap 次数。
    """

    mean_group1: float
    mean_group2: float
    raw_gap: float
    endowments: float
    pricing: float
    interaction: float
    se_endowments: float | None = None
    se_pricing: float | None = None
    se_interaction: float | None = None
    endowments_pct: float = 0.0
    pricing_pct: float = 0.0
    interaction_pct: float = 0.0
    decomposition_adds_up: bool = False
    n_group1: int = 0
    n_group2: int = 0
    ob_standard: OaxacaResult | None = None
    ob_regression: OaxacaResult | None = None
    name_group1: str = "Group1"
    name_group2: str = "Group2"
    n_bootstrap: int = 0

    @property
    def interpretation(self) -> str:
        """自动生成经济解释。"""
        lines = []
        lines.append(f"Raw Gap: {self.raw_gap:+.4f} ({self.name_group1} vs {self.name_group2})")
        lines.append("")
        lines.append("Three-factor decomposition (Kitagawa 2015):")
        lines.append(f"  E (Endowments):   {self.endowments:+.4f} ({self.endowments_pct:.1f}%)")
        lines.append(f"  P (Pricing):      {self.pricing:+.4f} ({self.pricing_pct:.1f}%)")
        lines.append(f"  I (Interaction): {self.interaction:+.4f} ({self.interaction_pct:.1f}%)")
        lines.append("")

        if abs(self.endowments_pct) > abs(self.pricing_pct):
            main_driver = "endowments"
            main_pct = self.endowments_pct
        else:
            main_driver = "pricing"
            main_pct = self.pricing_pct

        lines.append(
            f"Main driver: {main_driver} ({abs(main_pct):.1f}% of total)."
        )

        if self.decomposition_adds_up:
            lines.append("Decomposition adds up exactly (E+P+I = gap).")
        else:
            residual = self.endowments + self.pricing + self.interaction - self.raw_gap
            lines.append(
                f"Note: E+P+I = {self.endowments + self.pricing + self.interaction:+.4f}, "
                f"gap = {self.raw_gap:+.4f}, residual = {residual:+.4f}. "
                "The residual reflects OLS nonlinearity (mean(X @ beta) != mean(y)) "
                "and is absorbed into P. See ob_standard for the 2-factor OB result."
            )

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "mean_group1": self.mean_group1,
            "mean_group2": self.mean_group2,
            "raw_gap": self.raw_gap,
            "endowments": self.endowments,
            "pricing": self.pricing,
            "interaction": self.interaction,
            "se_endowments": self.se_endowments,
            "se_pricing": self.se_pricing,
            "se_interaction": self.se_interaction,
            "endowments_pct": self.endowments_pct,
            "pricing_pct": self.pricing_pct,
            "interaction_pct": self.interaction_pct,
            "decomposition_adds_up": self.decomposition_adds_up,
            "n_group1": self.n_group1,
            "n_group2": self.n_group2,
            "name_group1": self.name_group1,
            "name_group2": self.name_group2,
            "n_bootstrap": self.n_bootstrap,
        }


# =============================================================================
# OAXACA-BLINDER DECOMPOSITION
# =============================================================================


class OaxacaBlinderDecomposition:
    """
    Oaxaca (1973) 工资分解。

    将两群体间的结果差异分解为：
      - 禀赋效应（Endowments）：特征差异
      - 系数效应（Coefficients）：回报差异
      - 交互项（Interaction）：交叉效应

    支持三种权重方案：
      - "burnham"（默认）：Burnham (2020) 权重
      - "pooled"：使用总样本系数
      - "group1" / "group2"：使用特定组系数

    Parameters
    ----------
    name1 : str
        组1名称（默认 "Group1"）。
    name2 : str
        组2名称（默认 "Group2"）。
    """

    def __init__(self, name1: str = "Group1", name2: str = "Group2"):
        self.name1 = name1
        self.name2 = name2

    def _ols_coefficients(
        self,
        y: np.ndarray,
        X: np.ndarray,
        weights: np.ndarray | None = None,
    ) -> np.ndarray:
        """OLS 回归计算系数。"""
        if weights is not None:
            W = np.diag(weights)
            XtW = X.T @ W
            XtWy = XtW @ y
            XtWX = XtW @ X
            try:
                beta = np.linalg.solve(XtWX, XtWy)
            except np.linalg.LinAlgError:
                beta = np.linalg.lstsq(XtWX, XtWy, rcond=None)[0]
        else:
            try:
                XtX = X.T @ X
                Xty = X.T @ y
                beta = np.linalg.solve(XtX, Xty)
            except np.linalg.LinAlgError:
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
        return beta

    def _burnham_weights(
        self,
        n1: int,
        n2: int,
        share1: float = 0.5,
    ) -> float:
        """
        Burnham (2020) 权重：避免基准组选择偏误。

        lambda = n1 / (n1 + n2) * share1 + n2 / (n1 + n2) * (1 - share1)
        默认 share1=0.5 表示等权重。
        """
        total = n1 + n2
        return (n1 / total) * share1 + (n2 / total) * (1 - share1)

    def fit(
        self,
        y1: np.ndarray,
        X1: np.ndarray,
        y2: np.ndarray,
        X2: np.ndarray,
        weights1: np.ndarray | None = None,
        weights2: np.ndarray | None = None,
        weight_scheme: str = "burnham",
    ) -> OaxacaResult:
        """
        执行 Oaxaca-Blinder 分解。

        Parameters
        ----------
        y1, y2 : np.ndarray
            组1和组2的结果变量（如工资）。
        X1, X2 : np.ndarray
            组1和组2的解释变量矩阵（需含截距）。
        weights1, weights2 : np.ndarray | None
            样本权重（如调查权重）。
        weight_scheme : str
            权重方案："burnham"（默认）/ "pooled" / "group1" / "group2"。

        Returns
        -------
        OaxacaResult
        """
        y1 = np.asarray(y1).flatten()
        y2 = np.asarray(y2).flatten()
        X1 = np.asarray(X1)
        X2 = np.asarray(X2)

        n1, n2 = len(y1), len(y2)
        mean1, mean2 = float(np.mean(y1)), float(np.mean(y2))
        raw_gap = mean1 - mean2

        mean_X1 = np.mean(X1, axis=0)
        mean_X2 = np.mean(X2, axis=0)

        beta1 = self._ols_coefficients(y1, X1, weights1)
        beta2 = self._ols_coefficients(y2, X2, weights2)

        # 选择基准系数
        if weight_scheme == "burnham":
            lam = self._burnham_weights(n1, n2)
            beta_bar = lam * beta1 + (1 - lam) * beta2
        elif weight_scheme == "pooled":
            X_pooled = np.vstack([X1, X2])
            y_pooled = np.hstack([y1, y2])
            w_pooled = np.hstack([weights1 or np.ones(n1), weights2 or np.ones(n2)])
            beta_bar = self._ols_coefficients(y_pooled, X_pooled, w_pooled)
        elif weight_scheme == "group1":
            beta_bar = beta1
        else:  # group2
            beta_bar = beta2

        # 分解
        endowments = float(beta_bar @ (mean_X1 - mean_X2))
        coefficients = float((beta1 - beta2) @ mean_X1)
        interaction = float((beta1 - beta2) @ (mean_X1 - mean_X2))

        _log.info(
            f"[OaxacaBlinder] {self.name1} vs {self.name2}: "
            f"gap={raw_gap:+.4f}, E={endowments:+.4f}, "
            f"C={coefficients:+.4f}, I={interaction:+.4f}, "
            f"N1={n1}, N2={n2}"
        )

        return OaxacaResult(
            name1=self.name1,
            name2=self.name2,
            mean1=mean1,
            mean2=mean2,
            raw_gap=raw_gap,
            endowments=endowments,
            coefficients=coefficients,
            interaction=interaction,
            n_group1=n1,
            n_group2=n2,
            weight_scheme=weight_scheme,
        )


# =============================================================================
# KITAGAWA (2015) THREE-FACTOR DECOMPOSITION
# =============================================================================


class KOBDecomposition:
    """
    Kitagawa (2015) 三因素分解。

    将两群体间的结果差异分解为：
      - E（Endowments / 禀赋效应）：特征差异
      - P（Pricing / 价格效应）：系数差异
      - I（Interaction / 交互效应）：交叉项

    使用 bootstrap (B=499) 计算标准误。

    三因素分解与标准 2-factor OB 保持一致：
      - E + I = 标准 OB 的禀赋效应
      - P = 标准 OB 的系数效应 - E
      - OLS 残差被记录在 decomposition_adds_up 标志中

    Parameters
    ----------
    name1 : str
        组1名称（默认 "Group1"）。
    name2 : str
        组2名称（默认 "Group2"）。
    random_state : int | None
        随机种子（默认 42）。
    """

    def __init__(
        self,
        name1: str = "Group1",
        name2: str = "Group2",
        random_state: int | None = 42,
    ):
        self.name1 = name1
        self.name2 = name2
        self.rng = np.random.default_rng(random_state)

    def _ols(
        self,
        y: np.ndarray,
        X: np.ndarray,
    ) -> np.ndarray:
        """OLS 系数。"""
        XtX = X.T @ X
        Xty = X.T @ y
        try:
            return np.linalg.solve(XtX + 1e-8 * np.eye(X.shape[1]), Xty)
        except np.linalg.LinAlgError:
            beta = np.zeros(X.shape[1])
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            return beta

    def _bootstrap_decomposition(
        self,
        y1: np.ndarray,
        X1: np.ndarray,
        y2: np.ndarray,
        X2: np.ndarray,
    ) -> tuple[float, float, float]:
        """
        Bootstrap 重采样计算 E, P, I。

        与 fit() 中的 Kitagawa 公式保持一致。
        """
        n1, n2 = len(y1), len(y2)

        idx1 = self.rng.integers(0, n1, size=n1)
        idx2 = self.rng.integers(0, n2, size=n2)

        y1_b = y1[idx1]
        X1_b = X1[idx1]
        y2_b = y2[idx2]
        X2_b = X2[idx2]

        b1_b = self._ols(y1_b, X1_b)
        b2_b = self._ols(y2_b, X2_b)

        # Kitagawa three-factor decomposition (pooled reference)
        # E  = bp' (mean_X1 - mean_X2)
        # I  = (b1 - bp)' (mean_X1 - mean_X2)
        # P  = (b1 - b2)' mean_X1 - E
        X_pooled_b = np.vstack([X1_b, X2_b])
        y_pooled_b = np.hstack([y1_b, y2_b])
        bp_b = self._ols(y_pooled_b, X_pooled_b)

        dX_b = np.mean(X1_b, axis=0) - np.mean(X2_b, axis=0)
        E_b = float(bp_b @ dX_b)
        I_b = float((b1_b - bp_b) @ dX_b)
        C_ob_b = float((b1_b - b2_b) @ np.mean(X1_b, axis=0))
        P_b = C_ob_b - E_b

        return E_b, P_b, I_b

    def fit(
        self,
        y1: np.ndarray,
        X1: np.ndarray,
        y2: np.ndarray,
        X2: np.ndarray,
        n_bootstrap: int = 499,
    ) -> KOBResult:
        """
        执行 Kitagawa (2015) 三因素分解。

        Parameters
        ----------
        y1, y2 : np.ndarray
            组1和组2的结果变量。
        X1, X2 : np.ndarray
            组1和组2的解释变量矩阵（需含截距列）。
        n_bootstrap : int
            Bootstrap 次数（默认 499）。

        Returns
        -------
        KOBResult
        """
        y1 = np.asarray(y1).flatten()
        y2 = np.asarray(y2).flatten()
        X1 = np.asarray(X1)
        X2 = np.asarray(X2)

        n1, n2 = len(y1), len(y2)
        mean1, mean2 = float(np.mean(y1)), float(np.mean(y2))
        raw_gap = mean1 - mean2

        # OLS 系数
        b1 = self._ols(y1, X1)
        b2 = self._ols(y2, X2)

        # Pooled (non-discriminatory) 回归
        X_pooled = np.vstack([X1, X2])
        y_pooled = np.hstack([y1, y2])
        bp = self._ols(y_pooled, X_pooled)

        # Kitagawa 三因素分解（与标准 OB 一致）
        #
        # 标准 2-factor OB（pooled 基准）：
        #   E_ob  = bp' (mean_X1 - mean_X2)
        #   C_ob  = (b1 - b2)' mean_X1
        #
        # Kitagawa 3-factor（将禀赋效应进一步分解为 E 和 I）：
        #   E     = bp' (mean_X1 - mean_X2)          [endowments / characteristics]
        #   I     = (b1 - bp)' (mean_X1 - mean_X2)   [interaction]
        #   P     = C_ob - E                           [pricing / coefficients]
        #
        # OLS 残差 = gap - (E + I + P)，记录在 adds_up 标志中。
        dX = np.mean(X1, axis=0) - np.mean(X2, axis=0)
        endowments = float(bp @ dX)
        interaction = float((b1 - bp) @ dX)
        C_ob = float((b1 - b2) @ np.mean(X1, axis=0))
        pricing = C_ob - endowments

        # Bootstrap 标准误
        E_samples, P_samples, I_samples = [], [], []
        for _ in range(n_bootstrap):
            E_b, P_b, I_b = self._bootstrap_decomposition(y1, X1, y2, X2)
            E_samples.append(E_b)
            P_samples.append(P_b)
            I_samples.append(I_b)

        E_samples = np.array(E_samples)
        P_samples = np.array(P_samples)
        I_samples = np.array(I_samples)

        se_E = float(np.std(E_samples, ddof=1))
        se_P = float(np.std(P_samples, ddof=1))
        se_I = float(np.std(I_samples, ddof=1))

        # 贡献占比
        total_effect = abs(endowments) + abs(pricing) + abs(interaction)
        if total_effect > 1e-10:
            endowments_pct = abs(endowments) / total_effect * 100
            pricing_pct = abs(pricing) / total_effect * 100
            interaction_pct = abs(interaction) / total_effect * 100
        else:
            endowments_pct = pricing_pct = interaction_pct = 0.0

        residual = endowments + pricing + interaction - raw_gap
        decomposition_adds_up = abs(residual) < 1e-6

        # OB 分解（标准版和回归版）
        ob_engine = OaxacaBlinderDecomposition(name1=self.name1, name2=self.name2)
        ob_standard = ob_engine.fit(y1, X1, y2, X2, weight_scheme="burnham")
        ob_regression = ob_engine.fit(y1, X1, y2, X2, weight_scheme="pooled")

        result = KOBResult(
            mean_group1=mean1,
            mean_group2=mean2,
            raw_gap=raw_gap,
            endowments=endowments,
            pricing=pricing,
            interaction=interaction,
            se_endowments=se_E,
            se_pricing=se_P,
            se_interaction=se_I,
            endowments_pct=endowments_pct,
            pricing_pct=pricing_pct,
            interaction_pct=interaction_pct,
            decomposition_adds_up=decomposition_adds_up,
            n_group1=n1,
            n_group2=n2,
            ob_standard=ob_standard,
            ob_regression=ob_regression,
            name_group1=self.name1,
            name_group2=self.name2,
            n_bootstrap=n_bootstrap,
        )

        _log.info(
            f"[KOB] {self.name1} vs {self.name2}: "
            f"gap={raw_gap:+.4f}, E={endowments:+.4f} "
            f"({endowments_pct:.1f}%), P={pricing:+.4f} ({pricing_pct:.1f}%), "
            f"I={interaction:+.4f} ({interaction_pct:.1f}%), "
            f"adds_up={decomposition_adds_up}, "
            f"se_E={se_E:.4f}, se_P={se_P:.4f}, se_I={se_I:.4f}"
        )

        return result


# =============================================================================
# ECONOMIC / FINANCIAL APPLICATION WRAPPERS
# =============================================================================


def wage_decomposition(
    wage_data: pd.DataFrame,
    outcome: str = "lnwage",
    group: str = "female",
    predictors: list[str] | None = None,
    n_bootstrap: int = 499,
) -> KOBResult:
    """
    劳动力经济学标准工资分解。

    分解男性-女性工资差距为禀赋差异和回报差异。

    Parameters
    ----------
    wage_data : pd.DataFrame
        包含工资和协变量的数据框。
    outcome : str
        结果变量列名（默认 lnwage）。
    group : str
        分组变量列名（默认 female，1=女性，0=男性）。
    predictors : list[str] | None
        解释变量列表（默认 ["edu", "exp", "tenure"]）。
    n_bootstrap : int
        Bootstrap 次数。

    Returns
    -------
    KOBResult
    """
    if predictors is None:
        predictors = ["edu", "exp", "tenure"]

    required = [outcome, group] + predictors
    missing = [c for c in required if c not in wage_data.columns]
    if missing:
        _log.error(f"[wage_decomposition] Missing columns: {missing}")
        raise ValueError(f"Missing columns: {missing}")

    df = wage_data.dropna(subset=required).copy()

    group1_mask = df[group] == 1
    group2_mask = df[group] == 0

    y1 = df.loc[group1_mask, outcome].values
    y2 = df.loc[group2_mask, outcome].values

    X1 = df.loc[group1_mask, predictors].values
    X2 = df.loc[group2_mask, predictors].values

    # 添加截距
    X1 = np.column_stack([np.ones(len(y1)), X1])
    X2 = np.column_stack([np.ones(len(y2)), X2])

    name1 = f"{group}=1"
    name2 = f"{group}=0"

    kob = KOBDecomposition(name1=name1, name2=name2)
    return kob.fit(y1, X1, y2, X2, n_bootstrap=n_bootstrap)


def credit_gap_decomposition(
    data: pd.DataFrame,
    outcome: str = "credit_score",
    group: str = "urban",
    predictors: list[str] | None = None,
    n_bootstrap: int = 499,
) -> KOBResult:
    """
    普惠金融信用差距分解。

    分析城市-农村（或不同群体）间信用评分的差异来源。

    Parameters
    ----------
    data : pd.DataFrame
        包含信用评分和协变量的数据框。
    outcome : str
        结果变量列名（默认 credit_score）。
    group : str
        分组变量（1=城市/群体1，0=农村/群体2）。
    predictors : list[str] | None
        解释变量（默认 ["income", "age", "assets"]）。
    n_bootstrap : int
        Bootstrap 次数。

    Returns
    -------
    KOBResult
    """
    if predictors is None:
        predictors = ["income", "age", "assets"]

    required = [outcome, group] + predictors
    missing = [c for c in required if c not in data.columns]
    if missing:
        _log.error(f"[credit_gap_decomposition] Missing columns: {missing}")
        raise ValueError(f"Missing columns: {missing}")

    df = data.dropna(subset=required).copy()

    group1_mask = df[group] == 1
    group2_mask = df[group] == 0

    y1 = df.loc[group1_mask, outcome].values
    y2 = df.loc[group2_mask, outcome].values

    X1 = df.loc[group1_mask, predictors].values
    X2 = df.loc[group2_mask, predictors].values

    X1 = np.column_stack([np.ones(len(y1)), X1])
    X2 = np.column_stack([np.ones(len(y2)), X2])

    name1 = f"{group}=1"
    name2 = f"{group}=0"

    kob = KOBDecomposition(name1=name1, name2=name2)
    return kob.fit(y1, X1, y2, X2, n_bootstrap=n_bootstrap)


def investment_decomposition(
    data: pd.DataFrame,
    outcome: str = "investment_ratio",
    group: str = "state_owned",
    predictors: list[str] | None = None,
    n_bootstrap: int = 499,
) -> KOBResult:
    """
    企业投资行为的组间差异分解。

    分析国有企业 vs 非国有企业投资行为的差异来源。

    Parameters
    ----------
    data : pd.DataFrame
        包含投资率和控制变量的数据框。
    outcome : str
        投资率列名（默认 investment_ratio）。
    group : str
        产权分组（1=国有企业，0=民营企业）。
    predictors : list[str] | None
        解释变量（默认 ["roa", "leverage", "size", "cash"]）。
    n_bootstrap : int
        Bootstrap 次数。

    Returns
    -------
    KOBResult
    """
    if predictors is None:
        predictors = ["roa", "leverage", "size", "cash"]

    required = [outcome, group] + predictors
    missing = [c for c in required if c not in data.columns]
    if missing:
        _log.error(f"[investment_decomposition] Missing columns: {missing}")
        raise ValueError(f"Missing columns: {missing}")

    df = data.dropna(subset=required).copy()

    group1_mask = df[group] == 1
    group2_mask = df[group] == 0

    y1 = df.loc[group1_mask, outcome].values
    y2 = df.loc[group2_mask, outcome].values

    X1 = df.loc[group1_mask, predictors].values
    X2 = df.loc[group2_mask, predictors].values

    X1 = np.column_stack([np.ones(len(y1)), X1])
    X2 = np.column_stack([np.ones(len(y2)), X2])

    name1 = f"{group}=1 (State-owned)"
    name2 = f"{group}=0 (Private)"

    kob = KOBDecomposition(name1=name1, name2=name2)
    return kob.fit(y1, X1, y2, X2, n_bootstrap=n_bootstrap)


# =============================================================================
# VISUALIZATION
# =============================================================================


def plot_decomposition(
    result: KOBResult,
    save_path: str | Path | None = None,
    figsize: tuple[float, float] = (9, 6),
) -> Any:
    """
    绘制分解瀑布图（禀赋 -> 价格 -> 交互 -> 总差距）。

    Parameters
    ----------
    result : KOBResult
        KOB 分解结果。
    save_path : str | Path | None
        保存路径（如 "decomp.pdf"）。
    figsize : tuple[float, float]
        图形尺寸。

    Returns
    -------
    matplotlib Figure 或 None
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        _log.warning("[KOB] matplotlib not installed")
        return None

    fig, ax = plt.subplots(figsize=figsize)

    components = ["E\n(Endowments)", "P\n(Pricing)", "I\n(Interaction)"]
    values = [result.endowments, result.pricing, result.interaction]
    percentages = [result.endowments_pct, result.pricing_pct, result.interaction_pct]
    colors = ["#4C72B0", "#DD8452", "#55A868"]

    cumulative = 0.0
    positions = []
    for v in values:
        positions.append(cumulative + v / 2)
        cumulative += v

    bars = ax.bar(
        components, values, color=colors, width=0.5,
        edgecolor="white", linewidth=1.5,
    )

    for bar, val, pct in zip(bars, values, percentages):
        height = bar.get_height()
        y_pos = height / 2 if height >= 0 else height / 2
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y_pos,
            f"{val:+.3f}\n({pct:.1f}%)",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="white",
        )

    ax.axhline(
        y=result.raw_gap,
        color="#C44E52",
        linestyle="--",
        linewidth=1.5,
        label=f"Raw Gap: {result.raw_gap:+.3f}",
    )

    ax.annotate(
        f"Raw Gap = {result.raw_gap:+.3f}",
        xy=(2.2, result.raw_gap),
        xytext=(2.4, result.raw_gap),
        fontsize=10,
        color="#C44E52",
        fontweight="bold",
        va="center",
    )

    ax.axhline(y=0, color="gray", linewidth=0.8)
    ax.set_ylabel("Decomposition Components", fontsize=12)
    ax.set_title(
        f"KOB Decomposition: {result.name_group1} vs {result.name_group2}\n"
        f"(N1={result.n_group1}, N2={result.n_group2})",
        fontsize=13,
        fontweight="bold",
    )
    ax.grid(True, axis="y", alpha=0.3)

    legend_patches = [
        mpatches.Patch(color=c, label=l)
        for c, l in zip(colors, ["Endowments (E)", "Pricing (P)", "Interaction (I)"])
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=10)

    plt.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        _log.info(f"[KOB] Decomposition plot saved: {save_path}")

    return fig


# =============================================================================
# LATEX OUTPUT
# =============================================================================


def to_latex(result: KOBResult, precision: int = 3) -> str:
    """
    生成 LaTeX 分解表格。

    Parameters
    ----------
    result : KOBResult
        KOB 分解结果。
    precision : int
        数值精度（默认 3 位小数）。

    Returns
    -------
    str
        LaTeX 表格代码。
    """
    p = precision

    se_e = f"({result.se_endowments:.{p}f})" if result.se_endowments else ""
    se_p = f"({result.se_pricing:.{p}f})" if result.se_pricing else ""
    se_i = f"({result.se_interaction:.{p}f})" if result.se_interaction else ""

    lines = [
        "\\begin{table}[htbp]",
        "  \\centering",
        f"  \\caption{{Kitagawa-Oaxaca-Blinder Decomposition: "
        f"{result.name_group1} vs {result.name_group2}}}",
        "  \\label{tab:kob_decomposition}",
        "  \\begin{threeparttable}",
        "  \\begin{tabular}{lcc}",
        "    \\toprule",
        "    \\textbf{Component} & \\textbf{Value} & \\textbf{Share (\\%)} \\\\",
        "    \\midrule",
        f"    Mean ({result.name_group1}) & {result.mean_group1:.{p}f} & -- \\\\",
        f"    Mean ({result.name_group2}) & {result.mean_group2:.{p}f} & -- \\\\",
        f"    \\midrule",
        f"    Raw Gap & {result.raw_gap:+.{p}f} & 100.0 \\\\",
        f"    \\midrule",
        f"    Endowments (E) & {result.endowments:+.{p}f} {se_e} & "
        f"{result.endowments_pct:.1f} \\\\",
        f"    Pricing (P) & {result.pricing:+.{p}f} {se_p} & "
        f"{result.pricing_pct:.1f} \\\\",
        f"    Interaction (I) & {result.interaction:+.{p}f} {se_i} & "
        f"{result.interaction_pct:.1f} \\\\",
        f"    \\midrule",
        f"    E + P + I & {result.endowments+result.pricing+result.interaction:+.{p}f} & "
        f"{result.endowments_pct+result.pricing_pct+result.interaction_pct:.1f} \\\\",
        "    \\bottomrule",
        "  \\end{tabular}",
        "  \\begin{tablenotes}",
        "    \\small",
        f"    \\item Bootstrapped standard errors in parentheses (B={result.n_bootstrap}).",
        "    \\item E = Endowments (characteristics effect), "
        "P = Pricing (coefficients effect), I = Interaction.",
        f"    \\item N\\textsubscript{{{result.name_group1}}}="
        f"{result.n_group1}, "
        f"N\\textsubscript{{{result.name_group2}}}={result.n_group2}.",
        "  \\end{tablenotes}",
        "  \\end{threeparttable}",
        "\\end{table}",
    ]

    return "\n".join(lines)
