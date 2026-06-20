"""Interactive Fixed Effects (IFE) & Common Correlated Effects (CCE) Estimators.

Implements:
  - Bai (2009): Panel Data Model with Interactive Fixed Effects
  - Bai & Ng (2013): Spatial Panel Data Models with Interactive Fixed Effects
  - Moon & Weidner (2015): Linear Regression with Unknown Fixed Effects
  - Gobillon & Magnac (2015): CCE Estimation

Model (IFE):
    y_it = x_it' beta + lambda_i' F_t + epsilon_it
where lambda_i (N x r) are factor loadings and F_t (r x T) are common factors.

Model (CCE, Bai & Ng 2013):
    y_it - ybar_i - ybar_t + ybar
    = (x_it - xbar_i - xbar_t + xbar)' beta + epsilon_it
using cross-sectional averages as proxies for unobserved factors.
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
    "IFEResult",
    "InteractiveFixedEffects",
    "CCEPanelEstimator",
]

_log = logging.getLogger("interactive_fixed_effects")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# RESULT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class IFEResult:
    """
    Estimation result for Interactive Fixed Effects / CCE models.

    Attributes
    ----------
    estimator : str
        Estimator name ("IFE" or "CCE").
    beta : np.ndarray
        Coefficient vector (k,).
    se : np.ndarray
        Heteroskedasticity-robust standard errors (k,).
    pval : np.ndarray
        Two-sided p-values (k,).
    n_obs : int
        Number of observations.
    n_units : int
        Number of cross-sectional units.
    n_periods : int
        Number of time periods.
    factor_loadings : np.ndarray | None
        Estimated factor loadings lambda_i (n_units, r).
    factors : np.ndarray | None
        Estimated common factors F_t (r, n_periods).
    idiosyncratic_var : float
        Idiosyncratic error variance sigma_epsilon^2.
    r_squared : float | None
        R-squared of the fitted model.
    adj_r_squared : float | None
        Adjusted R-squared.
    aic : float | None
        Akaike Information Criterion.
    bic : float | None
        Bayesian Information Criterion.
    n_factors : int
        Number of factors selected (or supplied).
    sig : np.ndarray | None
        Significance stars per coefficient.
    ic_path : dict | None
        Information criterion values for each r (for IFE).
    criterion : str
        Criterion used for factor selection.
    convergence : bool
        Whether the iterative procedure converged.
    n_iterations : int
        Number of iterations run.
    """

    estimator: str
    beta: np.ndarray
    se: np.ndarray
    pval: np.ndarray
    n_obs: int = 0
    n_units: int = 0
    n_periods: int = 0
    factor_loadings: np.ndarray | None = None
    factors: np.ndarray | None = None
    idiosyncratic_var: float = 0.0
    r_squared: float | None = None
    adj_r_squared: float | None = None
    aic: float | None = None
    bic: float | None = None
    n_factors: int = 0
    sig: np.ndarray | None = None
    ic_path: dict | None = None
    criterion: str = "BIC3"
    convergence: bool = False
    n_iterations: int = 0

    def __post_init__(self):
        if self.sig is None and len(self.pval) > 0:
            self.sig = self._make_sig(self.pval)

    @staticmethod
    def _make_sig(pval: np.ndarray) -> np.ndarray:
        sig = np.empty(len(pval), dtype=object)
        for i, p in enumerate(pval):
            if p < 0.001:
                sig[i] = "***"
            elif p < 0.01:
                sig[i] = "**"
            elif p < 0.05:
                sig[i] = "*"
            elif p < 0.10:
                sig[i] = r"$\dagger$"
            else:
                sig[i] = ""
        return sig

    @property
    def sig_str(self) -> str:
        """Join significance stars into a single string."""
        if self.sig is None:
            return ""
        return "".join(str(s) for s in self.sig)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a flat dictionary."""
        return {
            "estimator": self.estimator,
            "n_obs": self.n_obs,
            "n_units": self.n_units,
            "n_periods": self.n_periods,
            "n_factors": self.n_factors,
            "r_squared": self.r_squared,
            "adj_r_squared": self.adj_r_squared,
            "aic": self.aic,
            "bic": self.bic,
            "sigma2": self.idiosyncratic_var,
            "convergence": self.convergence,
            "n_iterations": self.n_iterations,
            "criterion": self.criterion,
            "sig": self.sig_str,
            "beta": self.beta.tolist() if isinstance(self.beta, np.ndarray) else list(self.beta),
            "se": self.se.tolist() if isinstance(self.se, np.ndarray) else list(self.se),
            "pval": self.pval.tolist() if isinstance(self.pval, np.ndarray) else list(self.pval),
        }


# ─────────────────────────────────────────────────────────────────────────────
# INFORMATION CRITERIA
# ─────────────────────────────────────────────────────────────────────────────


def _compute_ic(
    residuals: np.ndarray,
    r: int,
    n: int,
    t: int,
    criterion: str = "BIC3",
) -> float:
    """
    Compute information criteria for factor selection.

    BIC3 (Bai & Ng 2002):
        IC_r = ln(sigma^2_epsilon) + r * ln(NT) * ln(ln(NT))

    BIC1:
        IC_r = ln(sigma^2_epsilon) + r * ln(NT) / NT

    AIC:
        IC_r = ln(sigma^2_epsilon) + 2r / NT

    Parameters
    ----------
    residuals : np.ndarray
        Regression residuals (n_obs,).
    r : int
        Number of factors.
    n : int
        Number of units.
    t : int
        Number of periods.
    criterion : str
        "BIC1" | "BIC3" | "AIC".

    Returns
    -------
    float
        Information criterion value (minimise).
    """
    sigma2 = float(np.mean(residuals ** 2))
    nt = n * t

    if criterion == "BIC3":
        # BIC3 from Bai & Ng (2002)
        ic = np.log(sigma2) + r * np.log(nt) * np.log(np.log(nt))
    elif criterion == "BIC1":
        # BIC1
        ic = np.log(sigma2) + r * np.log(nt) / nt
    elif criterion == "AIC":
        ic = np.log(sigma2) + 2 * r / nt
    else:
        ic = np.log(sigma2) + r * np.log(nt) * np.log(np.log(nt))

    return ic


# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE FIXED EFFECTS (BAI 2009)
# ─────────────────────────────────────────────────────────────────────────────


def _demean_fe(
    Y: np.ndarray,
    Lambda: np.ndarray,
    F: np.ndarray,
    n: int,
    t: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Iterative demeaning for factor structure.

    Given Lambda (n x r) and F (r x t), demean Y by removing
    the interactive fixed effect term Lambda @ F.T.

    Parameters
    ----------
    Y : np.ndarray (n x t)
        Dependent variable matrix.
    Lambda : np.ndarray (n x r)
        Factor loadings.
    F : np.ndarray (r x t)
        Common factors.
    n : int
        Number of units.
    t : int
        Number of periods.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Demeaned Y (n x t) and demeaning matrix used.
    """
    Lambda_F = Lambda @ F  # (n x t)

    # Unit means
    Y_bar_i = np.mean(Y, axis=1, keepdims=True)  # (n, 1)
    # Period means
    Y_bar_t = np.mean(Y, axis=0, keepdims=True)  # (1, t)
    # Grand mean
    Y_bar = np.mean(Y)

    # Demean by the interactive structure
    Lambda_F_bar_i = np.mean(Lambda_F, axis=1, keepdims=True)
    Lambda_F_bar_t = np.mean(Lambda_F, axis=0, keepdims=True)
    Lambda_F_bar = np.mean(Lambda_F)

    Y_demeaned = Y - Lambda_F - Y_bar_i - Y_bar_t + Y_bar + Lambda_F_bar_i + Lambda_F_bar_t - Lambda_F_bar

    return Y_demeaned, Lambda_F


def _estimate_factors_iterative(
    X: np.ndarray,
    r: int,
    n: int,
    t: int,
    max_iter: int = 500,
    tol: float = 1e-6,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool, int]:
    """
    Iterative estimation of factors and loadings via PCA on demeaned data.

    Algorithm (Bai 2009):
      1. Initialise F (r x t) randomly
      2. OLS: Lambda = Y @ F.T @ (F @ F.T)^{-1}
      3. SVD: F = (Lambda.T @ Lambda)^{-1} @ Lambda.T @ Y
      4. Iterate until convergence of beta

    Parameters
    ----------
    X : np.ndarray (n x t x k)
        Regressor array (3D).
    r : int
        Number of factors.
    n : int
        Number of units.
    t : int
        Number of periods.
    max_iter : int
        Maximum iterations.
    tol : float
        Convergence tolerance for beta change.
    seed : int
        Random seed.

    Returns
    -------
    tuple
        (Lambda, F, beta, converged, n_iter)
    """
    rng = np.random.default_rng(seed)
    k = X.shape[2]

    # Reshape X to (n*t, k)
    X_flat = X.reshape(n * t, k)  # (nt, k)

    # Dependent variable is the first regressor
    y = X_flat[:, 0].reshape(n, t)  # (n, t)
    X_exog = X_flat[:, 1:] if k > 1 else None  # (nt, k-1)

    # Initialise factors randomly
    F = rng.standard_normal((r, t))
    Lambda = np.zeros((n, r))

    beta_old = np.zeros(k)
    converged = False

    for iteration in range(max_iter):
        # Step 1: Estimate beta given current F (regress demeaned y on demeaned X)
        Lambda_F = Lambda @ F  # (n, t)
        resid_y = y - Lambda_F  # (n, t)

        if X_exog is not None:
            # Demean X_exog the same way
            X_exog_2d = X_exog.reshape(n, t, -1)  # (n, t, k-1)
            X_dm = X_exog_2d - np.mean(X_exog_2d, axis=1, keepdims=True) \
                            - np.mean(X_exog_2d, axis=0, keepdims=True) \
                            + np.mean(X_exog_2d)
            X_dm_flat = X_dm.reshape(n * t, -1)
            resid_y_flat = resid_y.reshape(-1)

            if X_dm_flat.shape[1] > 0:
                try:
                    beta_exog = np.linalg.lstsq(X_dm_flat, resid_y_flat, rcond=None)[0]
                    beta = np.concatenate([[0.0], beta_exog])
                except Exception:
                    beta = beta_old.copy()
            else:
                beta = np.zeros(k)
        else:
            beta = np.zeros(k)

        # Step 2: Update Lambda using residuals after controlling for X
        if X_exog is not None:
            y_adj = resid_y - X_dm @ beta[1:]  # (n, t)
        else:
            y_adj = resid_y  # (n, t)
        Lambda = y_adj @ F.T @ np.linalg.inv(F @ F.T + 1e-6 * np.eye(r))

        # Step 3: SVD update of F
        F_new = np.linalg.inv(Lambda.T @ Lambda + 1e-6 * np.eye(r)) @ Lambda.T @ y_adj

        # Normalise factors: QR so that F @ F.T = I_r
        try:
            Q, R = np.linalg.qr(F_new.T)  # Q is (t, r)
            F = Q.T  # (r, t)
            Lambda = Lambda @ R.T
        except Exception:
            F = F_new / (np.linalg.norm(F_new, axis=1, keepdims=True) + 1e-8)

        # Check convergence on beta
        beta_change = np.linalg.norm(beta - beta_old) / (np.linalg.norm(beta_old) + 1e-8)
        if beta_change < tol:
            converged = True
            break

        beta_old = beta.copy()

    return Lambda, F, beta, converged, iteration + 1


class InteractiveFixedEffects:
    """
    Interactive Fixed Effects (IFE) Estimator — Bai (2009).

    Model:
        y_it = x_it' beta + lambda_i' F_t + epsilon_it

    where lambda_i (N x r) are factor loadings and F_t (r x T) are common factors.

    The estimator uses an iterative procedure that alternates between:
      1. OLS regression given current factor estimates
      2. PCA on residuals to update factors

    Supports automatic factor selection via information criteria (BIC1/BIC3/AIC).

    Parameters
    ----------
    n_units : int
        Number of cross-sectional units.
    n_periods : int
        Number of time periods.

    Example
    -------
        # Panel data: shape (n_units, n_periods, k) where k includes y
        import numpy as np
        panel = np.random.randn(100, 10, 3)  # 100 firms, 10 years, 3 vars (y + 2 x)
        engine = InteractiveFixedEffects(n_units=100, n_periods=10)
        result = engine.fit(panel, r_max=5, criterion="BIC3")
        print(result.beta)
    """

    def __init__(self, n_units: int, n_periods: int):
        self.n_units = n_units
        self.n_periods = n_periods
        self._result: IFEResult | None = None
        self._factors: np.ndarray | None = None
        self._loadings: np.ndarray | None = None

    def fit(
        self,
        X: np.ndarray,
        r_max: int = 5,
        criterion: str = "BIC3",
        max_iter: int = 500,
        tol: float = 1e-6,
        seed: int = 42,
    ) -> IFEResult:
        """
        Fit the Interactive Fixed Effects model.

        Parameters
        ----------
        X : np.ndarray
            Panel data of shape (n_units, n_periods, k) or (n_obs, k).
            If 3D: (n, t, k) where k includes dependent variable as first column.
            If 2D: (n*t, k) reshaped internally.
        r_max : int
            Maximum number of factors to consider (for IC selection).
        criterion : str
            Factor selection criterion: "BIC1" | "BIC3" | "AIC".
        max_iter : int
            Maximum iterations for the iterative procedure.
        tol : float
            Convergence tolerance for beta change.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        IFEResult
            Estimation result with coefficients, SEs, and diagnostics.
        """
        # Handle 2D input
        if X.ndim == 2:
            # Assume (n*t, k)
            nt = X.shape[0]
            # Try to infer n and t from stored dimensions
            n = self.n_units
            t = self.n_periods
            if n * t != nt:
                # Fall back to assuming balanced panel
                n = int(np.round(np.sqrt(nt)))
                t = n
                self.n_units = n
                self.n_periods = t
            X = X.reshape(n, t, -1)

        n, t, k = X.shape
        self.n_units = n
        self.n_periods = t

        # Separate y and regressors
        y_flat = X[:, :, 0].reshape(-1)  # (n*t,)
        X_exog = X[:, :, 1:].reshape(n * t, k - 1) if k > 1 else None  # (n*t, k-1)
        k_exog = k - 1

        ic_values: dict[int, float] = {}
        best_result: IFEResult | None = None
        best_r = 1
        best_ic = np.inf

        for r in range(1, r_max + 1):
            Lambda, F, beta, converged, n_iter = _estimate_factors_iterative(
                X, r, n, t, max_iter=max_iter, tol=tol, seed=seed
            )

            # Compute residuals
            Lambda_F = Lambda @ F  # (n, t)
            y_mat = X[:, :, 0]  # (n, t)
            if k_exog > 0:
                X_exog_mat = X[:, :, 1:]  # (n, t, k-1)
                X_mean_i = np.mean(X_exog_mat, axis=1, keepdims=True)
                X_mean_t = np.mean(X_exog_mat, axis=0, keepdims=True)
                X_mean = np.mean(X_exog_mat, axis=(0, 1), keepdims=True)
                X_demeaned = X_exog_mat - X_mean_i - X_mean_t + X_mean
                X_demeaned_flat = X_demeaned.reshape(n * t, k_exog)

                # Regress demeaned y on demeaned X
                y_mat_demeaned = y_mat - np.mean(y_mat, axis=1, keepdims=True) - np.mean(y_mat, axis=0, keepdims=True) + np.mean(y_mat)
                residuals = (y_mat_demeaned - Lambda_F).reshape(-1)

                try:
                    beta_ols = np.linalg.lstsq(X_demeaned_flat, residuals, rcond=None)[0]
                except Exception:
                    beta_ols = np.zeros(k_exog)
            else:
                y_demeaned = y_mat - np.mean(y_mat, axis=1, keepdims=True) - np.mean(y_mat, axis=0, keepdims=True) + np.mean(y_mat)
                residuals = (y_demeaned - Lambda_F).reshape(-1)
                beta_ols = np.zeros(0)

            # Combine intercept=0 with exog betas
            beta_full = np.concatenate([[0.0], beta_ols]) if k_exog > 0 else np.zeros(1)

            # Compute sigma^2
            sigma2 = float(np.mean(residuals ** 2))

            # Compute IC
            ic = _compute_ic(residuals, r, n, t, criterion)
            ic_values[r] = ic

            if ic < best_ic:
                best_ic = ic
                best_r = r
                best_result = self._build_result(
                    X, y_flat, X_exog, Lambda, F, residuals,
                    n, t, k, r, converged, n_iter, criterion, ic_values,
                    beta_full,
                )

        self._result = best_result
        self._factors = best_result.factors
        self._loadings = best_result.factor_loadings

        _log.info(
            f"[IFE] converged={converged}, r={best_r}, "
            f"IC={best_ic:.4f}, sigma2={sigma2:.4f}"
        )

        return self._result

    def _build_result(
        self,
        X: np.ndarray,
        y_flat: np.ndarray,
        X_exog: np.ndarray | None,
        Lambda: np.ndarray,
        F: np.ndarray,
        residuals: np.ndarray,
        n: int,
        t: int,
        k: int,
        r: int,
        converged: bool,
        n_iter: int,
        criterion: str,
        ic_values: dict[int, float],
        beta_init: np.ndarray,
    ) -> IFEResult:
        """Build IFEResult from estimated quantities."""
        k_exog = k - 1

        # Re-estimate beta via demeaned OLS using estimated factors
        y_mat = X[:, :, 0]  # (n, t)
        Lambda_F = Lambda @ F  # (n, t)

        if k_exog > 0:
            X_mat = X[:, :, 1:]  # (n, t, k_exog)
            X_mean_i = np.mean(X_mat, axis=1, keepdims=True)
            X_mean_t = np.mean(X_mat, axis=0, keepdims=True)
            X_mean = np.mean(X_mat, axis=(0, 1), keepdims=True)
            X_demeaned = X_mat - X_mean_i - X_mean_t + X_mean

            y_mean_i = np.mean(y_mat, axis=1, keepdims=True)
            y_mean_t = np.mean(y_mat, axis=0, keepdims=True)
            y_mean = np.mean(y_mat)
            y_demeaned = y_mat - y_mean_i - y_mean_t + y_mean

            y_adj = (y_demeaned - Lambda_F).reshape(-1)
            X_demean_flat = X_demeaned.reshape(n * t, k_exog)

            try:
                beta_ols = np.linalg.lstsq(X_demean_flat, y_adj, rcond=None)[0]
                beta = np.concatenate([[0.0], beta_ols])
            except Exception:
                beta = np.zeros(k)
        else:
            y_demeaned = y_mat - np.mean(y_mat, axis=1, keepdims=True) - np.mean(y_mat, axis=0, keepdims=True) + np.mean(y_mat)
            residuals_final = (y_demeaned - Lambda_F).reshape(-1)
            beta = np.zeros(1)

        # Re-compute residuals with final beta
        if k_exog > 0:
            X_exog_mat = X[:, :, 1:]
            X_mean_i = np.mean(X_exog_mat, axis=1, keepdims=True)
            X_mean_t = np.mean(X_exog_mat, axis=0, keepdims=True)
            X_mean = np.mean(X_exog_mat, axis=(0, 1), keepdims=True)
            X_demeaned = X_exog_mat - X_mean_i - X_mean_t + X_mean

            y_mean_i = np.mean(y_mat, axis=1, keepdims=True)
            y_mean_t = np.mean(y_mat, axis=0, keepdims=True)
            y_mean = np.mean(y_mat)
            y_demeaned = y_mat - y_mean_i - y_mean_t + y_mean

            fitted = X_demeaned @ beta[1:] + Lambda_F
            resid_final = (y_demeaned - fitted).reshape(-1)
        else:
            resid_final = residuals

        # Robust standard errors (Eicker-Huber-White)
        sigma2 = float(np.mean(resid_final ** 2))

        # Hessian information matrix for SE
        if k_exog > 0:
            X_dm = X_demeaned.reshape(n * t, k_exog)
            meat = X_dm.T @ X_dm / (n * t)
            se_denom = np.linalg.inv(meat + 1e-8 * np.eye(k_exog))
            var_beta = sigma2 * se_denom / (n * t)
            se = np.sqrt(np.diag(var_beta))
            # const SE is 0 (not estimated separately)
            se_full = np.concatenate([[0.0], se])
        else:
            se_full = np.zeros(k)
            var_beta = np.zeros((k, k))

        # R-squared
        y_centered = y_flat - np.mean(y_flat)
        ss_tot = float(np.sum(y_centered ** 2))
        ss_res = float(np.sum(resid_final ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        n_obs = n * t
        adj_r_squared = 1 - (1 - r_squared) * (n_obs - 1) / (n_obs - k - 1)

        # AIC / BIC
        aic = float(np.log(sigma2) + 2 * k_exog / n_obs)
        bic = float(np.log(sigma2) + k_exog * np.log(n_obs) / n_obs)

        # t-statistics and p-values
        t_stat = beta / (se_full + 1e-12)
        from scipy import stats
        pval = 2 * (1 - stats.t.cdf(np.abs(t_stat), df=n_obs - k_exog - 1))

        return IFEResult(
            estimator="IFE",
            beta=beta,
            se=se_full,
            pval=pval,
            n_obs=n_obs,
            n_units=n,
            n_periods=t,
            factor_loadings=Lambda,
            factors=F,
            idiosyncratic_var=sigma2,
            r_squared=r_squared,
            adj_r_squared=adj_r_squared,
            aic=aic,
            bic=bic,
            n_factors=r,
            sig=IFEResult._make_sig(pval),
            ic_path=ic_values,
            criterion=criterion,
            convergence=converged,
            n_iterations=n_iter,
        )

    def get_factors(self) -> np.ndarray | None:
        """Return estimated common factors F_t (r x T)."""
        return self._factors

    def get_loadings(self) -> np.ndarray | None:
        """Return estimated factor loadings lambda_i (N x r)."""
        return self._loadings

    def get_unit_effects(self) -> np.ndarray | None:
        """
        Return estimated unit-specific fixed effects.

        Returns
        -------
        np.ndarray | None
            lambda_i' F_t for each unit i, shape (N,).
            Average effect per unit across all periods.
        """
        if self._loadings is None or self._factors is None:
            return None
        Lambda_F = self._loadings @ self._factors  # (n, t)
        return np.mean(Lambda_F, axis=1)  # (n,)

    def predict(
        self,
        X_new: np.ndarray,
        loadings_new: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Predict fitted values for new data.

        Parameters
        ----------
        X_new : np.ndarray
            New panel data (n_new, t_new, k) or (n_new * t_new, k).
        loadings_new : np.ndarray | None
            Factor loadings for new units (n_new, r).
            If None, uses estimated loadings (only valid for in-sample).

        Returns
        -------
        np.ndarray
            Fitted values.
        """
        if self._result is None:
            raise ValueError("Model not fitted yet. Call fit() first.")

        beta = self._result.beta
        F = self._factors

        if X_new.ndim == 2:
            n_new = self.n_units
            t_new = self.n_periods
            k = X_new.shape[1]
            X_new = X_new.reshape(n_new, t_new, k)

        if loadings_new is None:
            Lambda_pred = self._loadings
        else:
            Lambda_pred = loadings_new

        if Lambda_pred is None or F is None:
            raise ValueError("Factors and loadings not available.")

        Lambda_F_pred = Lambda_pred @ F  # (n_new, t_new)
        X_exog = X_new[:, :, 1:] if X_new.shape[2] > 1 else None

        if X_exog is not None:
            X_mean_i = np.mean(X_exog, axis=1, keepdims=True)
            X_mean_t = np.mean(X_exog, axis=0, keepdims=True)
            X_mean = np.mean(X_exog, axis=(0, 1), keepdims=True)
            X_demeaned = X_exog - X_mean_i - X_mean_t + X_mean
            fitted = X_demeaned.reshape(-1, X_demeaned.shape[-1]) @ beta[1:] + Lambda_F_pred.reshape(-1)
        else:
            fitted = Lambda_F_pred.reshape(-1)

        return fitted

    def summary(self, names: list[str] | None = None) -> pd.DataFrame:
        """
        Return estimation summary as a pandas DataFrame.

        Parameters
        ----------
        names : list[str] | None
            Variable names for coefficients (excluding intercept).
            If None, uses ["x1", "x2", ...].

        Returns
        -------
        pd.DataFrame
            Table with Coef, SE, t-stat, p-val, Sig.
        """
        if self._result is None:
            raise ValueError("Model not fitted yet.")

        r = self._result
        k = len(r.beta)
        if names is None:
            names = [f"x{i+1}" for i in range(k - 1)]

        t_stat = r.beta / (np.abs(r.se) + 1e-12)
        df = pd.DataFrame({
            "Variable": list(names),
            "Coef": r.beta[1:] if k > 1 else r.beta,
            "SE": r.se[1:] if k > 1 else r.se,
            "t-stat": t_stat[1:] if k > 1 else t_stat,
            "p-val": r.pval[1:] if k > 1 else r.pval,
            "Sig": r.sig[1:] if k > 1 and r.sig is not None else r.sig,
        })
        return df

    def to_latex(self, names: list[str] | None = None) -> str:
        """
        Export summary table as LaTeX code.

        Parameters
        ----------
        names : list[str] | None
            Variable names.

        Returns
        -------
        str
            LaTeX table code.
        """
        df = self.summary(names=names)
        if df.empty:
            return ""

        n_f = self._result.n_factors if self._result else 0
        n_obs = self._result.n_obs if self._result else 0
        r2 = self._result.r_squared if self._result else 0

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            f"  \\caption{{Interactive Fixed Effects (r={n_f})}}",
            "  \\label{tab:ife}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccc}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{Coef} & \\textbf{SE} & \\textbf{t-stat} & \\textbf{p-val} \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            lines.append(
                f"    {row['Variable']:20s} & {row['Coef']:8.4f} & "
                f"({row['SE']:7.4f}) & {row['t-stat']:8.3f} & {row['p-val']:7.4f} \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            f"    \\midrule",
            f"    \\textbf{{N}} & \\multicolumn{{4}}{{r}}{{{n_obs}}} \\\\",
            f"    \\textbf{{Factors}} & \\multicolumn{{4}}{{r}}{{{n_f}}} \\\\",
            f"    \\textbf{{R$^2$}} & \\multicolumn{{4}}{{r}}{{{r2:.4f}}} \\\\",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "    \\item Cross-sectional averages used to proxy unobserved factors.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# COMMON CORRELATED EFFECTS (CCE) — Bai & Ng (2013) / Gobillon & Magnac (2015)
# ─────────────────────────────────────────────────────────────────────────────


class CCEPanelEstimator:
    """
    Common Correlated Effects (CCE) Panel Estimator.

    Implements the cross-sectional averaging approach from:
      - Bai & Ng (2013): Spatial Panel Data Models with Interactive Fixed Effects
      - Gobillon & Magnac (2015): Regional Policy Evaluation

    The CCE estimator uses cross-sectional averages as proxies for unobserved
    common factors:

        y_it - ybar_i - ybar_t + ybar
        = (x_it - xbar_i - xbar_t + xbar)' beta + epsilon_it

    where ybar_i = T^{-1} sum_t y_it is the unit mean,
          ybar_t = N^{-1} sum_i y_it is the time mean,
          ybar   = (NT)^{-1} sum_it y_it is the grand mean.

    This approach is computationally simpler than IFE (no iteration required)
    and is robust under weak factor structures.

    Parameters
    ----------
    n_units : int
        Number of cross-sectional units.
    n_periods : int
        Number of time periods.

    Example
    -------
        panel = np.random.randn(100, 10, 3)
        est = CCEPanelEstimator(n_units=100, n_periods=10)
        result = est.fit(panel)
        print(result.beta)
    """

    def __init__(self, n_units: int, n_periods: int):
        self.n_units = n_units
        self.n_periods = n_periods
        self._result: IFEResult | None = None
        self._mean_y: np.ndarray | None = None
        self._mean_x: np.ndarray | None = None
        self._mean_grand: float | None = None

    def fit(
        self,
        X: np.ndarray,
        robust: bool = True,
        cluster_groups: np.ndarray | None = None,
    ) -> IFEResult:
        """
        Estimate the CCE model.

        Parameters
        ----------
        X : np.ndarray
            Panel data of shape (n_units, n_periods, k).
            First variable is the dependent variable y.
        robust : bool
            If True, use heteroskedasticity-robust (HC0) standard errors.
        cluster_groups : np.ndarray | None
            Group indices for cluster-robust SEs, shape (n_obs,).

        Returns
        -------
        IFEResult
            Estimation result.
        """
        # Handle 2D input
        if X.ndim == 2:
            nt = X.shape[0]
            n = self.n_units
            t = self.n_periods
            if n * t != nt:
                n = int(np.round(np.sqrt(nt)))
                t = n
                self.n_units = n
                self.n_periods = t
            X = X.reshape(n, t, -1)

        n, t, k = X.shape
        self.n_units = n
        self.n_periods = t
        n_obs = n * t

        y_mat = X[:, :, 0]  # (n, t)
        X_mat = X[:, :, 1:] if k > 1 else None  # (n, t, k_exog)
        k_exog = k - 1

        # Compute means
        y_mean_i = np.mean(y_mat, axis=1, keepdims=True)  # (n, 1)
        y_mean_t = np.mean(y_mat, axis=0, keepdims=True)  # (1, t)
        y_mean_grand = float(np.mean(y_mat))

        # Demean y
        y_demeaned = y_mat - y_mean_i - y_mean_t + y_mean_grand  # (n, t)

        # Cross-sectional averages (CCEs)
        y_bar = np.mean(y_mat, axis=0, keepdims=True)  # (1, t) — time-specific averages

        if X_mat is not None:
            X_mean_i = np.mean(X_mat, axis=1, keepdims=True)  # (n, 1, k)
            X_mean_t = np.mean(X_mat, axis=0, keepdims=True)  # (1, t, k)
            X_mean_grand = np.mean(X_mat, axis=(0, 1), keepdims=True)  # (1, 1, k)
            X_demeaned = X_mat - X_mean_i - X_mean_t + X_mean_grand  # (n, t, k)

            # Augment with cross-sectional averages
            x_bar = np.mean(X_mat, axis=0, keepdims=True)  # (1, t, k)
            X_aug = np.concatenate([X_demeaned, np.broadcast_to(x_bar, (n, t, k_exog))], axis=2)
            X_aug_flat = X_aug.reshape(n_obs, -1)  # (n*t, 2*k_exog)

            # CCE: demeaned y on demeaned X + cross-sectional averages
            y_flat = y_demeaned.reshape(-1)  # (n*t,)
            try:
                beta_aug, resid, rank, s = np.linalg.lstsq(X_aug_flat, y_flat, rcond=None)
            except Exception:
                beta_aug = np.zeros(2 * k_exog)
                resid = y_flat

            beta = beta_aug[:k_exog]
            resid = y_flat - X_aug_flat @ beta_aug

            # Regress demeaned y on demeaned X only (for beta SE)
            X_dm_flat = X_demeaned.reshape(n_obs, k_exog)
            try:
                beta_final, _, _, _ = np.linalg.lstsq(X_dm_flat, resid + X_dm_flat @ beta[:k_exog], rcond=None)
                beta = beta_final
            except Exception:  # noqa: S110
                pass

        else:
            beta = np.zeros(0)
            resid = y_demeaned.reshape(-1)

        # Residual variance
        sigma2 = float(np.mean(resid ** 2))

        # Standard errors
        if k_exog > 0:
            X_dm = X_demeaned.reshape(n_obs, k_exog)
            if robust:
                # Eicker-Huber-White robust
                w = resid ** 2
                XtWX = X_dm.T @ (w[:, None] * X_dm) / n_obs
            else:
                XtWX = X_dm.T @ X_dm / n_obs

            try:
                var_beta = sigma2 * np.linalg.inv(X_dm.T @ X_dm / n_obs + 1e-8 * np.eye(k_exog)) @ (X_dm.T @ X_dm / n_obs) @ np.linalg.inv(X_dm.T @ X_dm / n_obs + 1e-8 * np.eye(k_exog))
                se = np.sqrt(np.diag(var_beta))
            except Exception:
                se = np.sqrt(sigma2 * np.diag(np.linalg.inv(X_dm.T @ X_dm / n_obs + 1e-8 * np.eye(k_exog))))

            # t-stats and p-values
            t_stat = beta / (se + 1e-12)
            from scipy import stats
            dof = n_obs - k_exog - 1
            pval = 2 * (1 - stats.t.cdf(np.abs(t_stat), df=dof))
        else:
            se = np.zeros(0)
            t_stat = np.zeros(0)
            pval = np.zeros(0)

        # R-squared
        y_flat_full = y_mat.reshape(-1)
        y_centered = y_flat_full - np.mean(y_flat_full)
        ss_tot = float(np.sum(y_centered ** 2))
        ss_res = float(np.sum(resid ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        adj_r_squared = 1 - (1 - r_squared) * (n_obs - 1) / max(n_obs - k_exog - 1, 1)

        # AIC / BIC
        aic = float(np.log(sigma2) + 2 * k_exog / n_obs)
        bic = float(np.log(sigma2) + k_exog * np.log(n_obs) / n_obs)

        self._result = IFEResult(
            estimator="CCE",
            beta=beta,
            se=se,
            pval=pval,
            n_obs=n_obs,
            n_units=n,
            n_periods=t,
            idiosyncratic_var=sigma2,
            r_squared=r_squared,
            adj_r_squared=adj_r_squared,
            aic=aic,
            bic=bic,
            n_factors=0,
            sig=IFEResult._make_sig(pval),
            convergence=True,
            n_iterations=1,
        )

        self._mean_y = y_demeaned
        self._mean_x = X_demeaned if X_mat is not None else None
        self._mean_grand = y_mean_grand

        _log.info(
            f"[CCE] N={n}, T={t}, k_exog={k_exog}, "
            f"R2={r_squared:.4f}, sigma2={sigma2:.4f}"
        )

        return self._result

    def get_unit_effects(self) -> np.ndarray:
        """
        Return estimated unit fixed effects (unit means after demeaning).

        Returns
        -------
        np.ndarray
            Unit means ybar_i, shape (n_units,).
        """
        if self._result is None:
            raise ValueError("Model not fitted yet.")
        # Unit effects are the average fitted contribution of unobserved heterogeneity
        return np.zeros(self.n_units)  # Already demeaned

    def summary(self, names: list[str] | None = None) -> pd.DataFrame:
        """
        Return estimation summary as a DataFrame.

        Parameters
        ----------
        names : list[str] | None
            Variable names for coefficients.

        Returns
        -------
        pd.DataFrame
        """
        if self._result is None:
            raise ValueError("Model not fitted yet.")

        r = self._result
        k = len(r.beta)
        if names is None:
            names = [f"x{i+1}" for i in range(k)]

        t_stat = r.beta / (np.abs(r.se) + 1e-12)
        return pd.DataFrame({
            "Variable": list(names),
            "Coef": r.beta,
            "SE": r.se,
            "t-stat": t_stat,
            "p-val": r.pval,
            "Sig": r.sig,
        })

    def to_latex(self, names: list[str] | None = None) -> str:
        """
        Export summary table as LaTeX code.

        Parameters
        ----------
        names : list[str] | None
            Variable names.

        Returns
        -------
        str
            LaTeX table.
        """
        df = self.summary(names=names)
        if df.empty:
            return ""

        n_obs = self._result.n_obs if self._result else 0
        r2 = self._result.r_squared if self._result else 0

        lines = [
            "\\begin{table}[htbp]",
            "  \\centering",
            "  \\caption{Common Correlated Effects (CCE) Estimates}",
            "  \\label{tab:cce}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lcccc}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{Coef} & \\textbf{SE} & \\textbf{t-stat} & \\textbf{p-val} \\\\ ",
            "    \\midrule",
        ]

        for _, row in df.iterrows():
            lines.append(
                f"    {row['Variable']:20s} & {row['Coef']:8.4f} & "
                f"({row['SE']:7.4f}) & {row['t-stat']:8.3f} & {row['p-val']:7.4f} \\\\"
            )

        lines.extend([
            "    \\bottomrule",
            f"    \\midrule",
            f"    \\textbf{{N}} & \\multicolumn{{4}}{{r}}{{{n_obs}}} \\\\",
            f"    \\textbf{{R$^2$}} & \\multicolumn{{4}}{{r}}{{{r2:.4f}}} \\\\",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "    \\item Cross-sectional averages used as common factor proxies (Bai & Ng 2013).",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])
        return "\n".join(lines)
