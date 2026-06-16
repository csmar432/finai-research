"""
Moderation Analysis (调节效应分析)
====================================

Three implementations:
  1. Interaction term (standard)
  2. Subsample analysis (split by moderator)
  3. Threshold regression (Hansen 2000)

References:
  - Baron & Kenny (1986) "The Moderator-Mediator Variable Distinction"
  - Aiken, West & Reno (1991) "Multiple Regression: Testing and Interpreting Interactions"
  - Hansen (2000) "Sample Splitting and Threshold Estimation"
  - 温忠麟, 侯杰泰, 张雷 (2005) 调节效应与中介效应的比较和应用

Usage:
  >>> from scripts.research_framework.moderation import ModerationAnalysis
  >>> result = ModerationAnalysis.interaction(df, X='X', M='M', Y='Y', controls=['size', 'age'])
  >>> print(result.summary())
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass
class ModerationResult:
    """Result of a moderation analysis."""

    method: str
    main_effect_X: float
    main_effect_X_se: float
    interaction_XM: float
    interaction_se: float
    interaction_t: float
    interaction_p: float
    r_squared: float
    n: int
    model: object

    def summary(self) -> str:
        return (
            "=" * 60
            + f"\nModeration Analysis ({self.method})\n"
            + "=" * 60
            + f"\nN = {self.n}, R^2 = {self.r_squared:.4f}\n"
            + f"\nMain effect of X: {self.main_effect_X:.6f} (SE = {self.main_effect_X_se:.6f})"
            + f"\nInteraction X*M:  {self.interaction_XM:.6f} (SE = {self.interaction_se:.6f})"
            + f"\n  t = {self.interaction_t:.4f}, p = {self.interaction_p:.4f}\n"
            + "=" * 60
        )


class ModerationAnalysis:
    """Moderation analysis: does M moderate the X -> Y relationship?"""

    @staticmethod
    def interaction(
        df: pd.DataFrame,
        X: str,
        M: str,
        Y: str,
        controls: list[str] | None = None,
        cluster: str | None = None,
    ) -> ModerationResult:
        """Standard interaction-term approach.

        Model: Y = b0 + b1*X + b2*M + b3*X*M + controls + e
        Test H0: b3 = 0 (no moderation)

        Args:
            df: data
            X: independent variable
            M: moderator (should be mean-centered for interpretability)
            Y: dependent variable
            controls: list of control variable names
            cluster: optional column name to cluster standard errors

        Returns:
            ModerationResult
        """
        if controls is None:
            controls = []
        df = df.copy()

        # Center X and M (for interpretability of main effects)
        df["_X"] = df[X] - df[X].mean()
        df["_M"] = df[M] - df[M].mean()
        df["_X_M"] = df["_X"] * df["_M"]

        # Build regression
        predictors = ["_X", "_M", "_X_M"] + controls
        X_mat = sm.add_constant(df[predictors])
        y = df[Y]

        if cluster is not None:
            model = sm.OLS(y, X_mat, missing="drop").fit(
                cov_type="cluster", cov_kwds={"groups": df[cluster]}
            )
        else:
            model = sm.OLS(y, X_mat, missing="drop").fit()

        return ModerationResult(
            method="Interaction term" + (" (clustered)" if cluster else ""),
            main_effect_X=model.params["_X"],
            main_effect_X_se=model.bse["_X"],
            interaction_XM=model.params["_X_M"],
            interaction_se=model.bse["_X_M"],
            interaction_t=model.tvalues["_X_M"],
            interaction_p=model.pvalues["_X_M"],
            r_squared=model.rsquared,
            n=int(model.nobs),
            model=model,
        )

    @staticmethod
    def subsample(
        df: pd.DataFrame,
        X: str,
        M: str,
        Y: str,
        split_var: str | None = None,
        split_quantile: float = 0.5,
        controls: list[str] | None = None,
    ) -> dict[str, ModerationResult]:
        """Subsample analysis: split sample by M, run separately.

        Useful when the moderation is non-linear or interaction is hard to interpret.

        Args:
            df: data
            X, Y: as before
            M: moderator to split on
            split_var: column to split by (defaults to M)
            split_quantile: where to split (default 0.5 = median)
            controls: list of controls

        Returns:
            Dict with 'low' and 'high' ModerationResults
        """
        if controls is None:
            controls = []
        if split_var is None:
            split_var = M

        threshold = df[split_var].quantile(split_quantile)
        low_df = df[df[split_var] <= threshold].copy()
        high_df = df[df[split_var] > threshold].copy()

        results = {}
        for label, sub_df in [("low", low_df), ("high", high_df)]:
            predictors = [X] + controls
            X_mat = sm.add_constant(sub_df[predictors])
            y = sub_df[Y]
            model = sm.OLS(y, X_mat, missing="drop").fit()

            results[label] = ModerationResult(
                method=f"Subsample ({label})",
                main_effect_X=model.params[X],
                main_effect_X_se=model.bse[X],
                interaction_XM=np.nan,
                interaction_se=np.nan,
                interaction_t=np.nan,
                interaction_p=model.pvalues[X],
                r_squared=model.rsquared,
                n=int(model.nobs),
                model=model,
            )
        return results


def run_threshold_regression(
    df: pd.DataFrame,
    X: str,
    M: str,
    Y: str,
    threshold_var: str,
    n_grid: int = 100,
    trim: float = 0.15,
    controls: list[str] | None = None,
) -> dict:
    """Hansen (2000) threshold regression.

    Searches for a threshold value gamma such that the slope of Y on X
    differs above vs below gamma.

    Args:
        df: data
        X: independent variable
        Y: dependent variable
        threshold_var: the variable on which we look for a threshold
        n_grid: number of candidate thresholds
        trim: trim fraction (0.15 = ignore lowest and highest 15% of threshold_var)
        controls: list of controls (kept on both sides)

    Returns:
        Dict with 'gamma_hat' (optimal threshold), 'ssr' (sum of squared residuals)
    """
    if controls is None:
        controls = []

    sorted_thresholds = df[threshold_var].quantile([trim, 1 - trim]).values
    candidates = np.linspace(sorted_thresholds[0], sorted_thresholds[1], n_grid)

    best_gamma = None
    best_ssr = np.inf

    for gamma in candidates:
        df = df.copy()
        df["_X1"] = np.where(df[threshold_var] <= gamma, df[X], 0)
        df["_X2"] = np.where(df[threshold_var] > gamma, df[X], 0)

        predictors = ["_X1", "_X2"] + controls
        X_mat = sm.add_constant(df[predictors])
        y = df[Y]
        model = sm.OLS(y, X_mat, missing="drop").fit()
        ssr = model.ssr

        if ssr < best_ssr:
            best_ssr = ssr
            best_gamma = gamma

    return {
        "gamma_hat": best_gamma,
        "ssr": best_ssr,
        "n_candidates": n_grid,
    }


if __name__ == "__main__":
    np.random.seed(42)
    n = 500
    df = pd.DataFrame(
        {
            "X": np.random.normal(0, 1, n),
            "M": np.random.normal(0, 1, n),
            "Y": np.random.normal(0, 1, n),
            "size": np.random.normal(10, 1, n),
            "age": np.random.uniform(0, 30, n),
        }
    )
    df["Y"] = 0.5 * df["X"] + 0.3 * df["X"] * df["M"] + np.random.normal(0, 0.5, n)

    print("Interaction-term moderation analysis...")
    result = ModerationAnalysis.interaction(
        df, X="X", M="M", Y="Y", controls=["size", "age"]
    )
    print(result.summary())
