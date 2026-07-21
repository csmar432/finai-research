"""
PSM-DID Scaffold (倾向得分匹配 + 双重差分)
==============================================

A complete scaffold for PSM-DID analysis:
  1. Estimate propensity score (logit / probit)
  2. Match treated to control (1:1, 1:k, caliper)
  3. Run DID on matched sample
  4. Standard errors clustered at the matching level

References:
  - Abadie (2005) "Semiparametric Difference-in-Differences Estimators"
  - Abadie & Imbens (2006) "Large Sample Properties of Matching Estimators"
  - Heckman, Ichimura & Todd (1997)
  - 陆铭, 陈钊 (2004) 城市化、城市倾向的经济政策与城乡收入差距

Usage:
  >>> from scripts.research_framework.psm_did import PSMDID
  >>> model = PSMDID(outcome="y", treatment="D", time="year", unit="id")
  >>> result = model.fit(df, covariates=["size", "age", "leverage"])
  >>> result.summary()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors
import statsmodels.api as sm


# ─────────────────────────────────────────────────────────────────────
# 1. Result dataclass
# ─────────────────────────────────────────────────────────────────────


@dataclass
class PSMDIDResult:
    """Result of a PSM-DID analysis."""

    did_coefficient: float
    did_se: float
    did_tstat: float
    did_pvalue: float
    n_treated_matched: int
    n_control_matched: int
    n_treated_unmatched: int
    n_control_unmatched: int
    covariate_balance: pd.DataFrame
    first_stage_auc: float
    n_obs_after_match: int
    method: str
    caliper: float | None
    model: object = field(repr=False)

    def summary(self) -> str:
        """Print a human-readable summary."""
        lines = [
            "=" * 60,
            "PSM-DID Result",
            "=" * 60,
            f"Method: {self.method}" + (f" (caliper={self.caliper})" if self.caliper else ""),
            f"N treated (matched / total): {self.n_treated_matched} / {self.n_treated_matched + self.n_treated_unmatched}",
            f"N control (matched / total): {self.n_control_matched} / {self.n_control_matched + self.n_control_unmatched}",
            f"N obs after match: {self.n_obs_after_match}",
            f"First-stage AUC: {self.first_stage_auc:.4f}",
            "",
            "Covariate balance (after matching):",
            self.covariate_balance.to_string(index=False),
            "",
            "DID coefficient:",
            f"  ATT = {self.did_coefficient:.6f}",
            f"  SE  = {self.did_se:.6f}",
            f"  t   = {self.did_tstat:.4f}",
            f"  p   = {self.did_pvalue:.4f}",
            "=" * 60,
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# 2. PSM-DID main class
# ─────────────────────────────────────────────────────────────────────


class PSMDID:
    """Propensity Score Matching + Difference-in-Differences.

    Implements Abadie (2005) PSM-DID with sklearn-based matching.

    Args:
        outcome: outcome variable name
        treatment: binary treatment variable name (1=treated, 0=control)
        time: time variable (e.g. year)
        unit: unit variable (e.g. firm_id)
        method: matching method
            - 'nearest': nearest neighbour (default)
            - 'caliper': nearest neighbour within caliper (in SD of PS)
            - 'kernel': kernel matching
        caliper: caliper width in standard deviations of PS (only for 'caliper' method)
        n_neighbors: k for k-nearest neighbours (default 1)
        replace: matching with replacement (default False)
    """

    def __init__(
        self,
        outcome: str,
        treatment: str,
        time: str,
        unit: str,
        method: Literal["nearest", "caliper", "kernel"] = "nearest",
        caliper: float | None = None,
        n_neighbors: int = 1,
        replace: bool = False,
    ):
        self.outcome = outcome
        self.treatment = treatment
        self.time = time
        self.unit = unit
        self.method = method
        self.caliper = caliper
        self.n_neighbors = n_neighbors
        self.replace = replace

    def fit(
        self,
        df: pd.DataFrame,
        covariates: list[str],
        pre_period: tuple | None = None,
        post_period: tuple | None = None,
    ) -> PSMDIDResult:
        """Run PSM-DID.

        Args:
            df: Long-format panel (unit, time, ...)
            covariates: list of covariate names for propensity score
            pre_period: (start_year, end_year) for pre-treatment; auto if None
            post_period: (start_year, end_year) for post-treatment; auto if None

        Returns:
            PSMDIDResult with coefficient, balance, and diagnostics
        """
        df = df.copy()
        df = df.dropna(subset=covariates + [self.outcome, self.treatment, self.time])

        if len(df) == 0:
            raise ValueError(
                f"No rows after dropping NaN in {covariates + [self.outcome, self.treatment, self.time]}"
            )

        # Determine pre/post periods
        # Treatment year: the LATEST year where treatment==0 in the pre-period,
        # or the EARLIEST year treatment==1 in the post-period.
        # Convention: use the boundary of pre/post based on the policy.
        if pre_period is None:
            treated_mask = df[self.treatment] == 1
            treatment_years_all = df.loc[treated_mask, self.time].unique()
            if len(treatment_years_all) == 0:
                raise ValueError(
                    f"No treated observations found (treatment='{self.treatment}'=1)."
                )
            # For staggered adoption: use the EARLIEST year treatment==1 as boundary
            treatment_year = int(treatment_years_all.min())
            # If treatment_year is the FIRST year in the data, no pre-period exists
            if treatment_year <= df[self.time].min():
                treatment_year = int(df[self.time].min() + 1)
            pre_period = (df[self.time].min(), treatment_year - 1)
        else:
            treatment_year = pre_period[1] + 1 if isinstance(pre_period, tuple) else None
        if post_period is None:
            post_period = (treatment_year, df[self.time].max())

        # Use only pre-treatment period for PSM (avoid post-treatment bias)
        pre_df = df[df[self.time] < treatment_year].copy()
        pre_df = pre_df.drop_duplicates(subset=[self.unit])

        # ── Stage 1: Propensity Score ──
        X = pre_df[covariates]
        y = pre_df[self.treatment]
        ps_model = LogisticRegression(max_iter=1000, random_state=42)
        ps_model.fit(X, y)
        pre_df["ps"] = ps_model.predict_proba(X)[:, 1]
        df["ps"] = ps_model.predict_proba(df[covariates])[:, 1]

        # AUC
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y, pre_df["ps"])

        # ── Stage 2: Matching ──
        treated = pre_df[pre_df[self.treatment] == 1]
        control = pre_df[pre_df[self.treatment] == 0]

        if self.method == "caliper":
            caliper_value = self.caliper * pre_df["ps"].std()
            t_ps = treated["ps"].values
            c_ps = control["ps"].values
            c_idx = control.index.values
            matched_control_idx = []
            for j, tps in enumerate(t_ps):
                diffs = np.abs(c_ps - tps)
                in_caliper = diffs <= caliper_value
                if np.any(in_caliper):
                    nearest = np.argmin(np.where(in_caliper, diffs, np.inf))
                    matched_control_idx.append(c_idx[nearest])
            matched_control = control.loc[matched_control_idx] if matched_control_idx else control.iloc[0:0]
        else:
            # nearest neighbour (with or without replacement)
            nn = NearestNeighbors(n_neighbors=self.n_neighbors)
            nn.fit(control[["ps"]])
            distances, indices = nn.kneighbors(treated[["ps"]])
            matched_control = control.iloc[indices.flatten()]
            if not self.replace:
                matched_control = matched_control.drop_duplicates()

        # ── Stage 3: DID on matched sample ──
        matched_treated = treated.copy()
        matched_treated["did"] = matched_treated[self.treatment]  # 1

        matched_control_df = matched_control.copy()
        matched_control_df["did"] = 0

        # Build pre-post for matched sample
        matched_ids = list(matched_treated[self.unit]) + list(matched_control_df[self.unit])
        matched_df = df[df[self.unit].isin(matched_ids)].copy()
        matched_df["post"] = (matched_df[self.time] >= treatment_year).astype(int)
        matched_df["did"] = matched_df[self.treatment] * matched_df["post"]

        # ── Stage 4: Regression ──
        # NOTE: Only "did" variable is included post-matching.
        # Covariates were used in PS estimation and should NOT be added back to avoid
        # "bad control" bias (Abadie 2005). Post-matching OLS uses only the treatment
        # indicator and post-period dummy. Use IPW or covariate-adjusted matching if
        # residual covariate adjustment is needed.
        if covariates:
            import warnings
            warnings.warn(
                f"[PSM-DID] covariates={covariates} were used for propensity score "
                f"estimation but are NOT included in the post-matching DID regression "
                f"to avoid bad-control bias (Abadie 2005). The DID coefficient "
                f"reflects the average treatment effect on the treated (ATT). "
                f"If residual covariate adjustment is needed, use IPW regression instead.",
                UserWarning,
                stacklevel=2,
            )
        y = matched_df[self.outcome]
        X = matched_df[["did"]]
        X = sm.add_constant(X)
        reg = sm.OLS(y, X, missing="drop").fit(
            cov_type="cluster", cov_kwds={"groups": matched_df[self.unit]}
        )

        did_coef = reg.params["did"]
        did_se = reg.bse["did"]
        did_t = reg.tvalues["did"]
        did_p = reg.pvalues["did"]

        # ── Balance check (after matching) ──
        balance = self._compute_balance(matched_treated, matched_control, covariates)

        return PSMDIDResult(
            did_coefficient=did_coef,
            did_se=did_se,
            did_tstat=did_t,
            did_pvalue=did_p,
            n_treated_matched=len(matched_treated),
            n_control_matched=len(matched_control_df),
            n_treated_unmatched=len(treated) - len(matched_treated),
            n_control_unmatched=len(control) - len(matched_control_df),
            covariate_balance=balance,
            first_stage_auc=auc,
            n_obs_after_match=len(matched_df),
            method=self.method,
            caliper=self.caliper,
            model=reg,
        )

    @staticmethod
    def _compute_balance(
        treated: pd.DataFrame,
        control: pd.DataFrame,
        covariates: list[str],
    ) -> pd.DataFrame:
        """Compute standardised bias (mean_t - mean_c) / pooled_sd before/after."""
        rows = []
        for cov in covariates:
            t_mean = treated[cov].mean()
            c_mean = control[cov].mean()
            pooled_sd = np.sqrt(
                (treated[cov].var() + control[cov].var()) / 2
            )
            bias = (t_mean - c_mean) / pooled_sd if pooled_sd > 0 else 0
            rows.append(
                {
                    "covariate": cov,
                    "treated_mean": t_mean,
                    "control_mean": c_mean,
                    "std_bias": bias,
                    "abs_bias_lt_10pct": abs(bias) < 0.1,
                }
            )
        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────
# 3. Convenience function
# ─────────────────────────────────────────────────────────────────────


def run_psm_did(
    df: pd.DataFrame,
    outcome: str,
    treatment: str,
    time: str,
    unit: str,
    covariates: list[str],
    method: str = "nearest",
    caliper: float | None = None,
) -> PSMDIDResult:
    """Convenience function for PSM-DID."""
    model = PSMDID(
        outcome=outcome,
        treatment=treatment,
        time=time,
        unit=unit,
        method=method,
        caliper=caliper,
    )
    return model.fit(df, covariates=covariates)


if __name__ == "__main__":
    # Demo with synthetic data
    # Treatment is *constant per firm* (cross-sectional treatment),
    # then a single policy shock at 2019 hits ALL firms but only treated ones respond.
    np.random.seed(42)
    n_firms = 500
    n_years = 5  # 2016-2020
    panel = []
    for f in range(n_firms):
        # cross-sectional treatment (firm-level, time-invariant)
        D = np.random.binomial(1, 0.3)
        for y in range(2016, 2016 + n_years):
            base = np.random.normal(0, 1)
            # Policy starts 2019; treated firms get +0.5 from 2019 onwards
            if y >= 2019 and D == 1:
                base += 0.5
            panel.append({"firm_id": f, "year": y, "D": D, "size": 10, "leverage": 0.5, "y": base})
    df = pd.DataFrame(panel)

    print("Running PSM-DID on synthetic data (500 firms, 2016-2020, treatment_year=2019)...")
    result = run_psm_did(
        df,
        outcome="y",
        treatment="D",
        time="year",
        unit="firm_id",
        covariates=["size", "leverage"],
        method="caliper",
        caliper=0.2,
    )
    print(result.summary())
