"""
Mediation Analysis (中介效应分析)
===================================

.. deprecated:: 1.8.6
    This module is **DEPRECATED** as of 2026-07-12 (audit_fix_2026_07_12).
    It is retained for backward compatibility only.

**Recommended replacement**:
  Use the canonical class-based implementation:
  ``from scripts.research_framework.mediation_test import MediationTest, MediationResult``

  ``MediationTest`` provides the same analyses (Baron-Kenny / Sobel / Bootstrap /
  Joint Significance) with a unified, class-based API and a richer ``MediationResult``
  dataclass (``alpha/beta/gamma/delta`` fields, ``ci_lower/ci_upper`` confidence
  intervals). The free-function API of this module (``sobel()``, ``bootstrap()``,
  ``classify_mediation()``) is functionally redundant with ``MediationTest.fit()``.

**Migration**:
  Old (this module): ``MediationAnalysis.bootstrap(df, X='X', M='M', Y='Y')``
  New:               ``MediationTest(df, outcome='Y', treatment='X', mediator='M').fit()``

Three implementations (deprecated):
  1. Baron-Kenny (1986) - 4-step, classical
  2. Bootstrap confidence intervals (Preacher & Hayes, 2004, 2008)
  3. Sobel test (1982) - approximate z-test

References:
  - Baron & Kenny (1986) "The Moderator-Mediator Variable Distinction in
    Social Psychological Research"
  - Preacher & Hayes (2004) "SPSS and SAS procedures for estimating
    indirect effects in simple mediation models"
  - Preacher & Hayes (2008) "Asymptotic and resampling strategies for
    assessing and comparing indirect effects in multiple mediator models"
  - Sobel (1982) "Asymptotic confidence intervals for indirect effects
    in structural equation models"
  - Zhao, Lynch & Chen (2010) "Reconsidering Baron and Kenny"

Usage:
  >>> # DEPRECATED:
  >>> from scripts.research_framework.mediation import MediationAnalysis
  >>> result = MediationAnalysis.bootstrap(df, X='X', M='M', Y='Y', n_boot=1000)
  >>> print(result.summary())
  >>> # RECOMMENDED:
  >>> from scripts.research_framework.mediation_test import MediationTest
  >>> result = MediationTest(df, outcome='Y', treatment='X', mediator='M').fit()
"""

from __future__ import annotations

import warnings

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm


warnings.warn(
    "scripts.research_framework.mediation is DEPRECATED as of v1.8.6 "
    "(2026-07-12). Use scripts.research_framework.mediation_test.MediationTest "
    "for the canonical class-based implementation. This module will be removed "
    "in v1.10.0.",
    DeprecationWarning,
    stacklevel=2,
)


# ─────────────────────────────────────────────────────────────────────
# 1. Result dataclass
# ─────────────────────────────────────────────────────────────────────


@dataclass
class MediationResult:
    """Result of a mediation analysis.

    .. deprecated:: 1.8.6
        Use ``MediationResult`` from ``scripts.research_framework.mediation_test``
        instead. Field names differ: this version uses ``indirect_effect`` /
        ``direct_effect`` / ``total_effect`` / ``indirect_ci``; the canonical
        version uses ``alpha`` / ``beta`` / ``gamma`` / ``delta`` / ``ci_lower``
        / ``ci_upper``.
    """

    method: str
    indirect_effect: float  # a*b
    direct_effect: float    # c'
    total_effect: float     # c
    indirect_se: float
    indirect_ci: tuple  # (lower, upper)
    a: float  # X -> M
    a_se: float
    b: float  # M -> Y (controlling X)
    b_se: float
    c: float  # X -> Y (total)
    c_prime: float  # X -> Y (controlling M)
    sobel_z: float
    sobel_p: float
    n: int
    n_boot: int | None = None
    boot_samples: np.ndarray = field(default=None, repr=False)

    @property
    def proportion_mediated(self) -> float:
        """Proportion of total effect mediated."""
        if self.total_effect == 0:
            return np.nan
        return self.indirect_effect / self.total_effect

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"Mediation Analysis ({self.method})",
            "=" * 60,
            f"N = {self.n}",
            f"Bootstrap samples: {self.n_boot}",
            "",
            "Path coefficients:",
            f"  a (X -> M):   {self.a:.6f}  (SE = {self.a_se:.6f})",
            f"  b (M -> Y|X): {self.b:.6f}  (SE = {self.b_se:.6f})",
            f"  c (X -> Y):   {self.c:.6f}",
            f"  c' (X -> Y|M): {self.c_prime:.6f}",
            "",
            "Effects:",
            f"  Total effect (c):    {self.total_effect:.6f}",
            f"  Direct effect (c'):  {self.direct_effect:.6f}",
            f"  Indirect (a*b):      {self.indirect_effect:.6f}",
            f"  Proportion mediated: {self.proportion_mediated:.4f}",
            "",
            "Inference:",
            f"  Sobel z = {self.sobel_z:.4f}, p = {self.sobel_p:.4f}",
        ]
        if self.indirect_ci is not None:
            lines.append(
                f"  Bootstrap {100-int((1-0.95)*100)}% CI: "
                f"[{self.indirect_ci[0]:.6f}, {self.indirect_ci[1]:.6f}]"
            )
        lines.append("=" * 60)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# 2. Helper: fit 2 OLS models
# ─────────────────────────────────────────────────────────────────────


def _fit_two_models(
    df: pd.DataFrame, X: str, M: str, Y: str
) -> tuple:
    """Fit M ~ X and Y ~ X + M, return (a, b, c, c') with standard errors."""
    # Path a: M = a0 + a*X + e1
    Xa = sm.add_constant(df[[X]])
    reg_a = sm.OLS(df[M], Xa).fit()
    a = reg_a.params[X]
    a_se = reg_a.bse[X]

    # Path c: Y = c0 + c*X + e2 (total)
    reg_c = sm.OLS(df[Y], Xa).fit()
    c = reg_c.params[X]

    # Paths b, c': Y = d0 + c'*X + b*M + e3
    Xbc = sm.add_constant(df[[X, M]])
    reg_bc = sm.OLS(df[Y], Xbc).fit()
    c_prime = reg_bc.params[X]
    b = reg_bc.params[M]
    b_se = reg_bc.params[M] if hasattr(reg_bc, 'bse') else 0
    if hasattr(reg_bc, 'bse'):
        b_se = reg_bc.bse[M]

    return a, a_se, b, b_se, c, c_prime


# ─────────────────────────────────────────────────────────────────────
# 3. Sobel test
# ─────────────────────────────────────────────────────────────────────


def sobel(df: pd.DataFrame, X: str, M: str, Y: str) -> MediationResult:
    """Classical Baron-Kenny + Sobel test (no bootstrap)."""
    a, a_se, b, b_se, c, c_prime = _fit_two_models(df, X, M, Y)
    indirect = a * b

    # Sobel standard error: sqrt(b^2 * SE_a^2 + a^2 * SE_b^2)
    sobel_se = np.sqrt(b**2 * a_se**2 + a**2 * b_se**2)
    sobel_z = indirect / sobel_se if sobel_se > 0 else 0
    from scipy import stats
    sobel_p = 2 * (1 - stats.norm.cdf(abs(sobel_z)))

    return MediationResult(
        method="Baron-Kenny + Sobel",
        indirect_effect=indirect,
        direct_effect=c_prime,
        total_effect=c,
        indirect_se=sobel_se,
        indirect_ci=None,
        a=a,
        a_se=a_se,
        b=b,
        b_se=b_se,
        c=c,
        c_prime=c_prime,
        sobel_z=sobel_z,
        sobel_p=sobel_p,
        n=len(df),
    )


# ─────────────────────────────────────────────────────────────────────
# 4. Bootstrap mediation
# ─────────────────────────────────────────────────────────────────────


def bootstrap(
    df: pd.DataFrame,
    X: str,
    M: str,
    Y: str,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> MediationResult:
    """Bootstrap confidence interval for indirect effect (Preacher-Hayes).

    Args:
        df: data
        X: independent variable
        M: mediator
        Y: dependent variable
        n_boot: number of bootstrap samples
        ci: confidence level (default 0.95)
        seed: random seed

    Returns:
        MediationResult with bootstrap CI for indirect effect
    """
    rng = np.random.default_rng(seed)

    # Point estimates from full sample
    a, a_se, b, b_se, c, c_prime = _fit_two_models(df, X, M, Y)
    indirect = a * b

    # Sobel (for fallback)
    sobel_se = np.sqrt(b**2 * a_se**2 + a**2 * b_se**2)
    sobel_z = indirect / sobel_se if sobel_se > 0 else 0
    from scipy import stats
    sobel_p = 2 * (1 - stats.norm.cdf(abs(sobel_z)))

    # Bootstrap
    boot_indirect = np.zeros(n_boot)
    n = len(df)
    for i in range(n_boot):
        sample = df.sample(n=n, replace=True, random_state=int(rng.integers(0, 1_000_000)))
        try:
            a_b, _, b_b, _, _, _ = _fit_two_models(sample, X, M, Y)
            boot_indirect[i] = a_b * b_b
        except Exception:
            boot_indirect[i] = np.nan

    # Drop NaNs
    boot_indirect = boot_indirect[~np.isnan(boot_indirect)]

    # Percentile CI
    alpha = 1 - ci
    lower = np.percentile(boot_indirect, 100 * alpha / 2)
    upper = np.percentile(boot_indirect, 100 * (1 - alpha / 2))

    return MediationResult(
        method=f"Bootstrap ({n_boot})",
        indirect_effect=indirect,
        direct_effect=c_prime,
        total_effect=c,
        indirect_se=sobel_se,
        indirect_ci=(lower, upper),
        a=a,
        a_se=a_se,
        b=b,
        b_se=b_se,
        c=c,
        c_prime=c_prime,
        sobel_z=sobel_z,
        sobel_p=sobel_p,
        n=len(df),
        n_boot=n_boot,
        boot_samples=boot_indirect,
    )


# ─────────────────────────────────────────────────────────────────────
# 5. Modern / Ze Chen et al. (2010) - report all 4 cases
# ─────────────────────────────────────────────────────────────────────


def classify_mediation(result: MediationResult) -> str:
    """Classify mediation type per Zhao, Lynch & Chen (2010).

    - Complementary: a*b and c' same sign
    - Competitive: a*b and c' opposite signs (suppression)
    - Indirect-only: a*b significant, c' not significant (full mediation)
    - Direct-only: a*b not significant, c' significant (no mediation)
    - No-effect: neither significant
    """
    indirect_sig = result.sobel_p < 0.05
    direct_sig = abs(result.c_prime) > 0  # crude; use se in production
    same_sign = np.sign(result.indirect_effect) == np.sign(result.c_prime)

    if indirect_sig and not direct_sig:
        return "Full mediation (indirect-only)"
    elif indirect_sig and same_sign:
        return "Complementary mediation"
    elif indirect_sig and not same_sign:
        return "Competitive mediation (suppression)"
    elif not indirect_sig and direct_sig:
        return "No mediation (direct-only)"
    else:
        return "No effect"


if __name__ == "__main__":
    # Demo with synthetic data
    np.random.seed(42)
    n = 500
    df = pd.DataFrame(
        {
            "X": np.random.normal(0, 1, n),
            "M": np.random.normal(0, 1, n),
            "Y": np.random.normal(0, 1, n),
        }
    )
    df["M"] = 0.5 * df["X"] + np.random.normal(0, 0.5, n)
    df["Y"] = 0.3 * df["X"] + 0.4 * df["M"] + np.random.normal(0, 0.5, n)
    # True: a=0.5, b=0.4, c=0.5, c'=0.3, indirect=0.2

    print("Bootstrap mediation analysis (1000 samples)...")
    result = bootstrap(df, X="X", M="M", Y="Y", n_boot=1000)
    print(result.summary())
    print(f"\nMediation type: {classify_mediation(result)}")
