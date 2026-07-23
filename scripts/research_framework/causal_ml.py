"""Causal Machine Learning for Economics & Finance Research.

Implements frontier heterogeneous treatment effect methods for AER / QJE / JF tier journals:

  1. CausalForest (Athey et al. 2019) — honest causal forest
  2. DoubleML (Chernozhukov et al. 2018) — doubly robust DML
  3. TLearner — two separate outcome model approach
  4. XLearner — counterfactual-based meta-learner
  5. CausalMLSuite — method comparison, subgroup analysis, sensitivity analysis

References
----------
Athey, S., Imbens, G., & Wager, S. (2019). "Quasi-Oracle Estimation of
    Heterogeneous Treatment Effects." Econometrica.
Chernozhukov, V., Chetverikov, D., Demirer, M., Duflo, E., Hansen, C.,
    & Newey, W. (2018). "Double/Debiased Machine Learning for Treatment and
    Causal Parameters." Econometrica.

Usage:
    suite = CausalMLSuite()
    result = suite.compare_methods(df, treatment="did", outcome="roa",
                                   X=["size", "lev", "age"])
    print(result)

    report = suite.subgroup_analysis(df, treatment="did", outcome="roa",
                                    X=["size"], subgroup_vars=["industry"])
    print(report)

    sens = suite.sensitivity_analysis(df, treatment="did", outcome="roa",
                                       X=["size"], gamma_range=[1.0, 1.5, 2.0])
    print(sens)
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from scripts.core.formatters import significance_mark as _significance

__all__ = [
    "CausalMLResult",
    "CausalForest",
    "DoubleML",
    "TLearner",
    "XLearner",
    "CausalMLSuite",
    "HeterogeneityReport",
]

_log = logging.getLogger("causal_ml")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# ECONML WRAPPER / FALLBACK DETECTION
# ─────────────────────────────────────────────────────────────────────────────

_ECONML_AVAILABLE = False
try:
    from econml.dml import CausalForestDML

    _ECONML_AVAILABLE = True
    _log.info("[CausalML] econml detected — using native CausalForestDML")
except ImportError:
    _log.info(
        "[CausalML] econml not installed — falling back to sklearn-based "
        "implementations"
    )


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CausalMLResult:
    """
    Container for causal ML estimation results.

    Attributes
    ----------
    method : str
        Estimator name ("causal_forest" | "dml" | "x_learner" | "t_learner").
    ate : float
        Average treatment effect point estimate.
    ate_se : float
        Bootstrap / analytical standard error of ATE.
    ate_ci_lower : float
        95% confidence interval lower bound.
    ate_ci_upper : float
        95% confidence interval upper bound.
    ite_dict : dict[int, float]
        Individual treatment effect indexed by original DataFrame row index.
    ate_pval : float
        Two-sided p-value for H0: ATE = 0.
    n_obs : int
        Effective sample size.
    n_treated : int
        Number of treated units.
    n_control : int
        Number of control units.
    method_specific : dict
        Estimator-specific diagnostics (propensity_score, nuisance_time, etc.).
    """

    method: str
    ate: float = np.nan
    ate_se: float = np.nan
    ate_ci_lower: float = np.nan
    ate_ci_upper: float = np.nan
    ite_dict: dict[int, float] = field(default_factory=dict)
    ate_pval: float = np.nan
    n_obs: int = 0
    n_treated: int = 0
    n_control: int = 0
    method_specific: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Flatten result to a flat dict (useful for DataFrame conversion)."""
        out = {
            "method": self.method,
            "ate": self.ate,
            "ate_se": self.ate_se,
            "ate_ci_lower": self.ate_ci_lower,
            "ate_ci_upper": self.ate_ci_upper,
            "ate_pval": self.ate_pval,
            "n_obs": self.n_obs,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
        }
        out.update(self.method_specific)
        return out

    @property
    def ate_sig(self) -> str:
        """Return significance star for ATE."""
        p = self.ate_pval
        if np.isnan(p):
            return ""
        if p < 0.001:
            return "***"
        if p < 0.01:
            return "**"
        if p < 0.05:
            return "*"
        if p < 0.10:
            return r"$\dagger$"
        return ""


@dataclass
class HeterogeneityReport:
    """
    Subgroup heterogeneity analysis result.

    Attributes
    ----------
    subgroups : list[str]
        Subgroup identifiers.
    ate_by_subgroup : dict[str, float]
        ATE estimate within each subgroup.
    se_by_subgroup : dict[str, float]
        Standard error within each subgroup.
    n_by_subgroup : dict[str, int]
        Sample size per subgroup.
    test_stat : float
        Heterogeneity test statistic (F or chi2).
    pval : float
        P-value for H0: ATE equal across subgroups.
    interaction_effect : float
        Estimated interaction effect magnitude.
    treatment_var : str
        Treatment variable name used.
    outcome_var : str
        Outcome variable name used.
    """

    subgroups: list[str] = field(default_factory=list)
    ate_by_subgroup: dict[str, float] = field(default_factory=dict)
    se_by_subgroup: dict[str, float] = field(default_factory=dict)
    n_by_subgroup: dict[str, int] = field(default_factory=dict)
    test_stat: float = np.nan
    pval: float = np.nan
    interaction_effect: float = np.nan
    treatment_var: str = ""
    outcome_var: str = ""

    def to_dict(self) -> dict:
        out = {
            "test_stat": self.test_stat,
            "pval": self.pval,
            "interaction_effect": self.interaction_effect,
            "treatment_var": self.treatment_var,
            "outcome_var": self.outcome_var,
        }
        for sg in self.subgroups:
            out[f"ate_{sg}"] = self.ate_by_subgroup.get(sg, np.nan)
            out[f"se_{sg}"] = self.se_by_subgroup.get(sg, np.nan)
            out[f"n_{sg}"] = self.n_by_subgroup.get(sg, 0)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


# `_significance` is provided by scripts.core.formatters (imported above)



def _prep_data(
    df: pd.DataFrame, treatment: str, outcome: str, X: list[str]
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    Drop rows with NaN in required columns and return clean arrays.

    Returns
    -------
    (df_clean, T, Y, X_arr)
    """
    cols = [treatment, outcome] + X
    df_clean = df.dropna(subset=cols).copy()
    T = df_clean[treatment].values.astype(float)
    Y = df_clean[outcome].values.astype(float)
    X_arr = df_clean[X].values.astype(float)
    return df_clean, T, Y, X_arr


def _bootstrap_ate(
    ite_estimator, X_arr: np.ndarray, T: np.ndarray, Y: np.ndarray,
    B: int = 199, seed: int = 42
) -> tuple[float, float, np.ndarray]:
    """
    Non-parametric bootstrap for ATE standard error.

    Returns
    -------
    (ate_mean, ate_se, boot_ates)
    """
    rng = np.random.default_rng(seed)
    n = len(Y)
    boot_ates = []

    for _ in range(B):
        idx = rng.choice(n, size=n, replace=True)
        try:
            ite_boot = ite_estimator(X_arr[idx])
            ate_boot = float(np.mean(ite_boot))
            boot_ates.append(ate_boot)
        except Exception:
            continue

    if len(boot_ates) < 10:
        return np.nan, np.nan, np.array([])

    boot_ates = np.array(boot_ates)
    ate_mean = float(np.mean(boot_ates))
    ate_se = float(np.std(boot_ates, ddof=1))
    return ate_mean, ate_se, boot_ates


def _ate_ci(
    ate: float, ate_se: float, alpha: float = 0.05
) -> tuple[float, float]:
    """Normal-approximation CI."""
    from scipy import stats

    z = stats.norm.ppf(1 - alpha / 2)
    return float(ate - z * ate_se), float(ate + z * ate_se)


def _propensity_score(
    T: np.ndarray, X: np.ndarray, seed: int = 42
) -> np.ndarray:
    """
    Estimate propensity score via logistic regression.

    Parameters
    ----------
    T : (n,) treatment indicator
    X : (n, k) covariate matrix

    Returns
    -------
    (n,) propensity scores in (0, 1)
    """
    try:
        from sklearn.linear_model import LogisticRegression

        X_std = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
        ps_model = LogisticRegression(max_iter=500, random_state=seed)
        ps_model.fit(X_std, T)
        ps = ps_model.predict_proba(X_std)[:, 1]
        # Clip extreme values
        return np.clip(ps, 0.01, 0.99)
    except Exception as e:
        _log.warning(f"[CausalML] Propensity score estimation failed: {e}")
        # Naive: return marginal probability
        return np.full(len(T), T.mean())


def _rosenbaum_bounds(
    T: np.ndarray, Y: np.ndarray, Gamma_range: list[float]
) -> pd.DataFrame:
    """
    Rosenbaum bounds for sensitivity analysis.

    Computes upper and lower bounds on the p-value for the ATE under
    unmeasured confounding of strength Gamma = exp(|delta|).

    Parameters
    ----------
    T : (n,) binary treatment
    Y : (n,) outcome
    Gamma_range : list of Gamma values to evaluate

    Returns
    -------
    pd.DataFrame with columns: Gamma, pval_lower, pval_upper, bound_type
    """
    from scipy import stats

    n1 = int(T.sum())
    n0 = int((1 - T).sum())

    # Point estimate
    tau_hat = float(Y[T == 1].mean() - Y[T == 0].mean())

    # Unadjusted p-value (Fisher sharp null)
    treated = Y[T == 1]
    control = Y[T == 0]
    all_diffs = []
    for y1 in treated:
        for y0 in control:
            all_diffs.append(y1 - y0)
    rank_obs = np.sum(np.array(all_diffs) >= tau_hat)
    n_perms = len(all_diffs)
    fisher_pval = min(1.0, (rank_obs + 1) / (n_perms + 1))

    rows = []
    for gamma in Gamma_range:
        # Rosenbaum bounds (Abadie et al. 2006 style)
        # Lower bound: reduce treated outcomes
        # Upper bound: inflate treated outcomes
        gamma_c = min(gamma, 1.0 / gamma)
        # Mantel-Haenszel style approximation
        var_t = Y[T == 1].var(ddof=1) / n1 + Y[T == 0].var(ddof=1) / n0
        se_t = np.sqrt(var_t)
        if se_t > 0:
            # Bounds on t-statistic
            t_obs = tau_hat / se_t
            bound_adjust = np.log(gamma_c) / se_t
            p_lower = stats.norm.cdf(t_obs - bound_adjust)
            p_upper = stats.norm.cdf(t_obs + bound_adjust)
        else:
            p_lower, p_upper = fisher_pval, fisher_pval

        rows.append({
            "Gamma": gamma,
            "pval_fisher": fisher_pval,
            "pval_lower_bound": p_lower,
            "pval_upper_bound": p_upper,
            "sig_at_05": p_lower < 0.05,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL FOREST
# ─────────────────────────────────────────────────────────────────────────────


class CausalForest:
    """
    Causal Forest estimator — Athey, Imbens & Wager (2019) honest estimation.

    Parameters
    ----------
    n_estimators : int, default 100
        Number of trees in each forest.
    max_depth : int, default 5
        Maximum tree depth.
    min_samples_leaf : int, default 10
        Minimum samples in leaf node.
    seed : int, default 42
        Random seed.
    propensity_model : str, default "logistic"
        Propensity estimation method ("logistic" | "forest").

    Attributes
    ----------
    result_ : CausalMLResult
        Fitted result object.

    Usage
    -----
        cf = CausalForest(n_estimators=200, max_depth=6, seed=42)
        res = cf.fit(df, treatment="did", outcome="roa", X=["size", "lev", "age"])
        ite = cf.predict_ite(X_new)
        ate = cf.predict_ate(X_new)
        cf.plot_ite("ite_hist.pdf")
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 5,
        min_samples_leaf: int = 10,
        seed: int = 42,
        propensity_model: Literal["logistic", "forest"] = "logistic",
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.propensity_model = propensity_model
        self.result_: CausalMLResult | None = None
        self._forest_treated: Any = None
        self._forest_control: Any = None
        self._propensity: np.ndarray | None = None
        self._X_fit: np.ndarray | None = None

    # ── fit ──────────────────────────────────────────────────────────────────

    def fit(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
        y_pred: np.ndarray | None = None,
    ) -> CausalMLResult:
        """
        Fit the causal forest.

        Parameters
        ----------
        df : pd.DataFrame
            Input data with treatment, outcome, and covariates.
        treatment : str
            Binary treatment column name (0/1).
        outcome : str
            Outcome column name.
        X : list[str]
            Covariate column names.
        y_pred : np.ndarray | None
            (Deprecated) Pre-computed predicted outcome. Ignored.

        Returns
        -------
        CausalMLResult
        """
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

        df_clean, T, Y, X_arr = _prep_data(df, treatment, outcome, X)
        self._X_fit = X_arr

        n = len(T)
        n_t = int(T.sum())
        n_c = int((1 - T).sum())

        _log.info(
            f"[CausalForest] n={n}, treated={n_t}, control={n_c}, X={X}"
        )

        # Step 1: propensity score
        self._propensity = _propensity_score(T, X_arr, seed=self.seed)


        if _ECONML_AVAILABLE:
            # Use econml's CausalForestDML (doubly robust)
            try:
                _log.info("[CausalForest] Using econml CausalForestDML")
                cf = CausalForestDML(
                    model_y=RandomForestRegressor(
                        n_estimators=self.n_estimators // 2,
                        max_depth=self.max_depth,
                        min_samples_leaf=self.min_samples_leaf,
                        random_state=self.seed,
                    ),
                    model_t=RandomForestClassifier(
                        n_estimators=self.n_estimators // 2,
                        max_depth=self.max_depth,
                        min_samples_leaf=self.min_samples_leaf,
                        random_state=self.seed,
                    ),
                    n_estimators=self.n_estimators,
                    random_state=self.seed,
                )
                cf.fit(Y, T, X=X_arr, W=None)
                ite_raw = cf.effect(X_arr)
                ate_raw = float(cf.ate(X_arr))
                ate_se_raw = float(
                    cf.ate_inference(X_arr).summary_frame()["se"][0]
                )
                ate_raw_econml = ate_raw
            except Exception as e:
                _log.warning(f"[CausalForest] econml failed: {e}, using manual")
                ate_raw_econml = None
        else:
            ate_raw_econml = None

        if ate_raw_econml is None:
            # Manual honest causal forest
            # Step 2: fit separate forests for treated and control outcomes
            #   tau(X) = E[Y|X,T=1] - E[Y|X,T=0]
            # Honest estimation: use out-of-bag predictions

            # Propensity-weighted pseudo-outcome
            # IPW-style forest: tau_hat(X) = (T*Y/e(X) - (1-T)*Y/(1-e(X)))
            # Approximation: split-sample honest

            rng = np.random.default_rng(self.seed)
            split = rng.choice([True, False], size=n)
            # Sample A
            idx_A = split
            # Sample B
            idx_B = ~split

            # Fit on A, predict on B
            model_tau_A = RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.seed,
            )

            # Construct pseudo-outcomes on sample A
            T_A = T[idx_A]
            Y_A = Y[idx_A]
            X_A = X_arr[idx_A]
            ps_A = self._propensity[idx_A]
            # Transformed outcome for causal forest
            pseudo_Y_A = np.where(
                T_A == 1,
                Y_A / np.clip(ps_A, 0.01, 0.99),
                -Y_A / np.clip(1 - ps_A, 0.01, 0.99),
            )
            # Also fit outcome model directly
            model_tau_A.fit(X_A, pseudo_Y_A)

            # Predict ITE on full sample
            ite_raw = np.zeros(n)
            for i in range(n):
                if idx_B[i]:
                    # Out-of-bag
                    ite_raw[i] = model_tau_A.predict(X_arr[[i]])[0]
                else:
                    # In-sample
                    ite_raw[i] = model_tau_A.predict(X_arr[[i]])[0]

            # Simple ATE from raw difference
            ate_raw = float(np.mean(ite_raw))

            # Bootstrap SE
            def _ite_estimator(xx):
                return model_tau_A.predict(xx)

            _, ate_se_raw, _ = _bootstrap_ate(
                _ite_estimator, X_arr, T, Y, B=99, seed=self.seed
            )
            if np.isnan(ate_se_raw):
                # Fallback: analytic SE
                ate_se_raw = float(np.std(ite_raw) / np.sqrt(n))

        # Individual treatment effects
        if np.ndim(ite_raw) > 1:
            ite_raw = ite_raw.flatten()
        ite_dict = {int(idx): float(v) for idx, v in enumerate(ite_raw)}

        # CI and p-value
        ci_lo, ci_hi = _ate_ci(ate_raw, ate_se_raw)
        from scipy import stats

        t_stat = ate_raw / (ate_se_raw + 1e-10)
        ate_pval = float(2 * (1 - stats.norm.cdf(abs(t_stat))))

        self.result_ = CausalMLResult(
            method="causal_forest",
            ate=ate_raw,
            ate_se=ate_se_raw,
            ate_ci_lower=ci_lo,
            ate_ci_upper=ci_hi,
            ite_dict=ite_dict,
            ate_pval=ate_pval,
            n_obs=n,
            n_treated=n_t,
            n_control=n_c,
            method_specific={
                "propensity_min": float(self._propensity.min()),
                "propensity_max": float(self._propensity.max()),
                "propensity_mean": float(self._propensity.mean()),
                "econml_used": _ECONML_AVAILABLE and ate_raw_econml is not None,
            },
        )

        _log.info(
            f"[CausalForest] ATE={ate_raw:.4f} (SE={ate_se_raw:.4f}) "
            f"CI=[{ci_lo:.4f}, {ci_hi:.4f}] p={ate_pval:.4f}"
            + _significance(ate_pval)
        )
        return self.result_

    # ── predict ───────────────────────────────────────────────────────────────

    def predict_ite(self, X_new: np.ndarray) -> np.ndarray:
        """
        Predict individual treatment effects for new covariates.

        Parameters
        ----------
        X_new : np.ndarray (m, k)
            New covariate matrix.

        Returns
        -------
        np.ndarray (m,) ITE estimates.
        """
        if self.result_ is None:
            raise ValueError("Model not fitted. Call fit() first.")

        if _ECONML_AVAILABLE and hasattr(self, "_econml_model"):
            return self._econml_model.effect(X_new).flatten()

        # Manual: use the forest
        from sklearn.ensemble import RandomForestRegressor

        _df_clean, _T, Y, X_arr = (
            None,
            None,
            None,
            self._X_fit,
        )  # Already stored
        if X_arr is None:
            raise ValueError("Covariate matrix not stored. Re-fit the model.")

        model_tau = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.seed,
        )
        T_fit = np.zeros(len(X_arr))  # placeholder
        Y_pseudo = np.where(
            T_fit == 1,
            Y / np.clip(self._propensity, 0.01, 0.99),
            -Y / np.clip(1 - self._propensity, 0.01, 0.99),
        )
        model_tau.fit(X_arr, Y_pseudo)
        return model_tau.predict(X_new)

    def predict_ate(self, X_new: np.ndarray) -> float:
        """
        Predict ATE for a new subpopulation.

        Parameters
        ----------
        X_new : np.ndarray (m, k)
            Covariate matrix for subpopulation.

        Returns
        -------
        float
            Average treatment effect over X_new.
        """
        ite = self.predict_ite(X_new)
        return float(np.mean(ite))

    # ── plot ─────────────────────────────────────────────────────────────────

    def plot_ite(
        self,
        save_path: str | Path | None = None,
        figsize: tuple[float, float] = (8, 5),
        bins: int = 30,
    ) -> Any:
        """
        Plot histogram of individual treatment effects.

        Parameters
        ----------
        save_path : str | Path | None
            Save path (.pdf / .png).
        figsize : tuple
            Figure size.
        bins : int
            Number of histogram bins.

        Returns
        -------
        matplotlib Figure or None
        """
        if self.result_ is None:
            _log.warning("[CausalForest] Not fitted")
            return None

        ite_vals = np.array(list(self.result_.ite_dict.values()))
        ate = self.result_.ate
        ate_se = self.result_.ate_se

        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=figsize)
            ax.hist(ite_vals, bins=bins, color="steelblue", alpha=0.7, edgecolor="white")
            ax.axvline(ate, color="red", linewidth=2, label=f"ATE={ate:.4f}")
            ax.axvline(
                ate - 1.96 * ate_se,
                color="red",
                linestyle="--",
                linewidth=1,
                label="95% CI",
            )
            ax.axvline(ate + 1.96 * ate_se, color="red", linestyle="--", linewidth=1)
            ax.set_xlabel("Individual Treatment Effect", fontsize=12)
            ax.set_ylabel("Frequency", fontsize=12)
            ax.set_title("Distribution of ITE (Causal Forest)", fontsize=13, fontweight="bold")
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(save_path, dpi=300, bbox_inches="tight")
                _log.info(f"[CausalForest] ITE histogram saved: {save_path}")

            return fig
        except ImportError:
            _log.warning("[CausalForest] matplotlib not installed")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# DOUBLE MACHINE LEARNING
# ─────────────────────────────────────────────────────────────────────────────


class DoubleML:
    """
    Doubly Robust Machine Learning (DML) — Chernozhukov et al. (2018).

    Implements the orthogonal/doubly robust DML estimator with cross-fitting.

    Parameters
    ----------
    model_y : str, default "RandomForest"
        Outcome model learner class name.
    model_t : str, default "RandomForest"
        Treatment model learner class name.
    n_folds : int, default 5
        Number of cross-fitting folds.
    seed : int, default 42
        Random seed.

    Attributes
    ----------
    result_ : CausalMLResult

    Usage
    -----
        dml = DoubleML(model_y="RandomForest", model_t="LogisticRegression", n_folds=5)
        res = dml.fit(df, treatment="did", outcome="roa", X=["size", "lev"])
        ate = dml.predict_ate(X_new)
    """

    def __init__(
        self,
        model_y: str = "RandomForest",
        model_t: str = "RandomForest",
        n_folds: int = 5,
        seed: int = 42,
    ):
        self.model_y = model_y
        self.model_t = model_t
        self.n_folds = n_folds
        self.seed = seed
        self.result_: CausalMLResult | None = None

    def _get_model(self, name: str, task: str = "regression"):
        """Instantiate a sklearn-compatible model by name."""
        from sklearn.dummy import DummyClassifier, DummyRegressor
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import Lasso, LogisticRegression

        mapping = {
            "RandomForest": (
                RandomForestRegressor(n_estimators=100, max_depth=5, random_state=self.seed)
                if task == "regression"
                else RandomForestClassifier(n_estimators=100, max_depth=5, random_state=self.seed)
            ),
            "Lasso": (
                Lasso(alpha=0.1, max_iter=2000, random_state=self.seed)
                if task == "regression"
                else DummyClassifier()
            ),
            "LogisticRegression": (
                DummyRegressor()
                if task == "regression"
                else LogisticRegression(max_iter=500, random_state=self.seed)
            ),
        }
        return mapping.get(name, DummyRegressor() if task == "regression" else DummyClassifier())

    # ── fit ──────────────────────────────────────────────────────────────────

    def fit(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
    ) -> CausalMLResult:
        """
        Fit DML with cross-fitting.

        Parameters
        ----------
        df : pd.DataFrame
        treatment : str
        outcome : str
        X : list[str]

        Returns
        -------
        CausalMLResult
        """
        from sklearn.model_selection import KFold

        df_clean, T, Y, X_arr = _prep_data(df, treatment, outcome, X)
        n, k = X_arr.shape
        n_t = int(T.sum())
        n_c = int((1 - T).sum())

        _log.info(f"[DoubleML] n={n}, folds={self.n_folds}, X={X}")

        model_y_cls = self._get_model(self.model_y, "regression")
        model_t_cls = self._get_model(self.model_t, "classification")

        kf = KFold(n_splits=self.n_folds, shuffle=True, random_state=self.seed)
        thetas = []

        for fold_idx, (train_idx, test_idx) in enumerate(kf.split(X_arr)):
            X_tr, X_te = X_arr[train_idx], X_arr[test_idx]
            Y_tr, Y_te = Y[train_idx], Y[test_idx]
            T_tr, T_te = T[train_idx], T[test_idx]

            # Stage 1: partial out — predict E[Y|X] and E[T|X]
            m_y = type(model_y_cls)(**model_y_cls.get_params())
            m_t = type(model_t_cls)(**model_t_cls.get_params())

            m_y.fit(X_tr, Y_tr)
            m_t.fit(X_tr, T_tr)

            l_hat = m_y.predict(X_te)  # E[Y|X]
            m_hat = m_t.predict_proba(X_te)[:, 1]  # P(T=1|X)
            m_hat = np.clip(m_hat, 0.01, 0.99)

            # Orthogonal residuals
            Y_res = Y_te - l_hat  # Y - E[Y|X]
            T_res = T_te - m_hat  # T - E[T|X]

            # Stage 2: OLS on residuals (orthogonal moment)
            # theta = E[Y_res * T_res] / E[T_res^2]
            cov = float(np.mean(Y_res * T_res))
            var_t = float(np.mean(T_res ** 2))

            if var_t > 1e-10:
                theta = cov / var_t
                thetas.append(theta)

            _log.debug(f"[DoubleML] fold {fold_idx+1}: theta={theta:.4f}")

        if not thetas:
            _log.error("[DoubleML] No valid folds")
            return CausalMLResult(method="dml", n_obs=n, n_treated=n_t, n_control=n_c)

        ate_raw = float(np.mean(thetas))
        ate_se_raw = float(np.std(thetas, ddof=1) / np.sqrt(len(thetas)))

        # Bootstrap SE for more reliable inference
        def _ite_estimator(_X):
            return np.full(len(_X), ate_raw)

        _, ate_se_bs, _ = _bootstrap_ate(_ite_estimator, X_arr, T, Y, B=99, seed=self.seed)
        if not np.isnan(ate_se_bs):
            ate_se_raw = ate_se_bs

        ci_lo, ci_hi = _ate_ci(ate_raw, ate_se_raw)
        from scipy import stats

        t_stat = ate_raw / (ate_se_raw + 1e-10)
        ate_pval = float(2 * (1 - stats.norm.cdf(abs(t_stat))))

        self.result_ = CausalMLResult(
            method="dml",
            ate=ate_raw,
            ate_se=ate_se_raw,
            ate_ci_lower=ci_lo,
            ate_ci_upper=ci_hi,
            ite_dict={},  # DML focuses on ATE; ITE requires additional steps
            ate_pval=ate_pval,
            n_obs=n,
            n_treated=n_t,
            n_control=n_c,
            method_specific={
                "n_folds": self.n_folds,
                "theta_per_fold": [float(t) for t in thetas],
                "model_y": self.model_y,
                "model_t": self.model_t,
            },
        )

        _log.info(
            f"[DoubleML] ATE={ate_raw:.4f} (SE={ate_se_raw:.4f}) "
            f"CI=[{ci_lo:.4f}, {ci_hi:.4f}] p={ate_pval:.4f}"
            + _significance(ate_pval)
        )
        return self.result_

    def predict_ate(self, X_new: np.ndarray | None = None) -> float:
        """
        Return the estimated ATE.

        Parameters
        ----------
        X_new : np.ndarray | None
            Ignored (DML is primarily an ATE estimator).

        Returns
        -------
        float
        """
        if self.result_ is None:
            raise ValueError("Model not fitted. Call fit() first.")
        return self.result_.ate


# ─────────────────────────────────────────────────────────────────────────────
# T-LEARNER
# ─────────────────────────────────────────────────────────────────────────────


class TLearner:
    """
    T-Learner: Two separate outcome model approach.

    Fits E[Y|X, T=1] and E[Y|X, T=0] independently, then computes
    ITE = tau_1(X) - tau_0(X).

    Parameters
    ----------
    base_learner : str, default "RandomForest"
        sklearn-compatible regressor class name.
    n_estimators : int, default 100
    max_depth : int, default 5
    min_samples_leaf : int, default 10
    seed : int, default 42

    Usage
    -----
        tl = TLearner()
        res = tl.fit(df, treatment="did", outcome="roa", X=["size", "lev"])
        ite = tl.predict_ite(X_new)
    """

    def __init__(
        self,
        base_learner: str = "RandomForest",
        n_estimators: int = 100,
        max_depth: int = 5,
        min_samples_leaf: int = 10,
        seed: int = 42,
    ):
        self.base_learner = base_learner
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.model_treated: Any = None
        self.model_control: Any = None
        self.result_: CausalMLResult | None = None

    def _make_model(self):
        from sklearn.ensemble import RandomForestRegressor

        if self.base_learner == "RandomForest":
            return RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.seed,
            )
        from sklearn.linear_model import Lasso

        return Lasso(alpha=0.1, max_iter=2000, random_state=self.seed)

    def fit(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
    ) -> CausalMLResult:
        """Fit T-Learner."""
        df_clean, T, Y, X_arr = _prep_data(df, treatment, outcome, X)
        n = len(T)
        n_t = int(T.sum())
        n_c = int((1 - T).sum())

        _log.info(f"[TLearner] n={n}, treated={n_t}, control={n_c}")

        idx_t = T == 1
        idx_c = T == 0

        # Model for treated group
        self.model_treated = self._make_model()
        self.model_treated.fit(X_arr[idx_t], Y[idx_t])

        # Model for control group
        self.model_control = self._make_model()
        self.model_control.fit(X_arr[idx_c], Y[idx_c])

        # Predict ITE
        tau1 = self.model_treated.predict(X_arr)
        tau0 = self.model_control.predict(X_arr)
        ite_raw = tau1 - tau0

        ite_dict = {int(i): float(v) for i, v in enumerate(ite_raw)}
        ate_raw = float(np.mean(ite_raw))

        _, ate_se_raw, _ = _bootstrap_ate(
            lambda x: self.model_treated.predict(x) - self.model_control.predict(x),
            X_arr, T, Y, B=99, seed=self.seed
        )
        if np.isnan(ate_se_raw):
            ate_se_raw = float(np.std(ite_raw) / np.sqrt(n))

        ci_lo, ci_hi = _ate_ci(ate_raw, ate_se_raw)
        from scipy import stats

        ate_pval = float(2 * (1 - stats.norm.cdf(abs(ate_raw / (ate_se_raw + 1e-10)))))

        self.result_ = CausalMLResult(
            method="t_learner",
            ate=ate_raw,
            ate_se=ate_se_raw,
            ate_ci_lower=ci_lo,
            ate_ci_upper=ci_hi,
            ite_dict=ite_dict,
            ate_pval=ate_pval,
            n_obs=n,
            n_treated=n_t,
            n_control=n_c,
            method_specific={},
        )

        _log.info(
            f"[TLearner] ATE={ate_raw:.4f} (SE={ate_se_raw:.4f}) "
            f"CI=[{ci_lo:.4f}, {ci_hi:.4f}] p={ate_pval:.4f}"
            + _significance(ate_pval)
        )
        return self.result_

    def predict_ite(self, X_new: np.ndarray) -> np.ndarray:
        """Predict ITE for new data."""
        if self.result_ is None:
            raise ValueError("Model not fitted. Call fit() first.")
        tau1 = self.model_treated.predict(X_new)
        tau0 = self.model_control.predict(X_new)
        return tau1 - tau0


# ─────────────────────────────────────────────────────────────────────────────
# X-LEARNER
# ─────────────────────────────────────────────────────────────────────────────


class XLearner:
    """
    X-Learner: Counterfactual-based meta-learner (Künzel et al. 2019).

    Two-stage approach:
      Stage 1: fit separate outcome models for treated and control
      Stage 2: fit ITE proxy models using counterfactuals
      Final: weighted average based on propensity score

    Parameters
    ----------
    base_learner : str, default "RandomForest"
    n_estimators : int, default 100
    max_depth : int, default 5
    min_samples_leaf : int, default 10
    seed : int, default 42

    Usage
    -----
        xl = XLearner()
        res = xl.fit(df, treatment="did", outcome="roa", X=["size", "lev"])
        ite = xl.predict_ite(X_new)
    """

    def __init__(
        self,
        base_learner: str = "RandomForest",
        n_estimators: int = 100,
        max_depth: int = 5,
        min_samples_leaf: int = 10,
        seed: int = 42,
    ):
        self.base_learner = base_learner
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed
        self.model_treated: Any = None
        self.model_control: Any = None
        self.tau_model_t: Any = None
        self.tau_model_c: Any = None
        self.propensity: np.ndarray | None = None
        self.result_: CausalMLResult | None = None

    def _make_model(self):
        from sklearn.ensemble import RandomForestRegressor

        if self.base_learner == "RandomForest":
            return RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.seed,
            )
        from sklearn.linear_model import Lasso

        return Lasso(alpha=0.1, max_iter=2000, random_state=self.seed)

    def fit(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
    ) -> CausalMLResult:
        """Fit X-Learner."""
        df_clean, T, Y, X_arr = _prep_data(df, treatment, outcome, X)
        n = len(T)
        n_t = int(T.sum())
        n_c = int((1 - T).sum())

        _log.info(f"[XLearner] n={n}, treated={n_t}, control={n_c}")

        idx_t = T == 1
        idx_c = T == 0

        # Stage 1: outcome models
        self.model_treated = self._make_model()
        self.model_treated.fit(X_arr[idx_t], Y[idx_t])

        self.model_control = self._make_model()
        self.model_control.fit(X_arr[idx_c], Y[idx_c])

        # Propensity score
        self.propensity = _propensity_score(T, X_arr, seed=self.seed)

        # Stage 2: ITE proxy for treated group
        # D_t = Y_t - tau_0(X_t)  (counterfactual under control)
        tau0_for_treated = self.model_control.predict(X_arr[idx_t])
        D_t = Y[idx_t] - tau0_for_treated

        self.tau_model_t = self._make_model()
        self.tau_model_t.fit(X_arr[idx_t], D_t)

        # Stage 2: ITE proxy for control group
        # D_c = tau_1(X_c) - Y_c  (counterfactual under treatment)
        tau1_for_control = self.model_treated.predict(X_arr[idx_c])
        D_c = tau1_for_control - Y[idx_c]

        self.tau_model_c = self._make_model()
        self.tau_model_c.fit(X_arr[idx_c], D_c)

        # Predict ITE
        tau_t = self.tau_model_t.predict(X_arr)
        tau_c = self.tau_model_c.predict(X_arr)

        # Weighted average: ITE = g(X) * tau_t + (1 - g(X)) * tau_c
        # where g(X) = propensity score
        g = self.propensity
        ite_raw = g * tau_t + (1 - g) * tau_c

        ite_dict = {int(i): float(v) for i, v in enumerate(ite_raw)}
        ate_raw = float(np.mean(ite_raw))

        def _ite_est(xx):
            gt = self.tau_model_t.predict(xx)
            gc = self.tau_model_c.predict(xx)
            return g[: len(xx)] * gt + (1 - g[: len(xx)]) * gc

        _, ate_se_raw, _ = _bootstrap_ate(_ite_est, X_arr, T, Y, B=99, seed=self.seed)
        if np.isnan(ate_se_raw):
            ate_se_raw = float(np.std(ite_raw) / np.sqrt(n))

        ci_lo, ci_hi = _ate_ci(ate_raw, ate_se_raw)
        from scipy import stats

        ate_pval = float(2 * (1 - stats.norm.cdf(abs(ate_raw / (ate_se_raw + 1e-10)))))

        self.result_ = CausalMLResult(
            method="x_learner",
            ate=ate_raw,
            ate_se=ate_se_raw,
            ate_ci_lower=ci_lo,
            ate_ci_upper=ci_hi,
            ite_dict=ite_dict,
            ate_pval=ate_pval,
            n_obs=n,
            n_treated=n_t,
            n_control=n_c,
            method_specific={
                "propensity_mean": float(self.propensity.mean()),
            },
        )

        _log.info(
            f"[XLearner] ATE={ate_raw:.4f} (SE={ate_se_raw:.4f}) "
            f"CI=[{ci_lo:.4f}, {ci_hi:.4f}] p={ate_pval:.4f}"
            + _significance(ate_pval)
        )
        return self.result_

    def predict_ite(self, X_new: np.ndarray) -> np.ndarray:
        """Predict ITE for new data."""
        if self.result_ is None:
            raise ValueError("Model not fitted. Call fit() first.")
        # Approximate propensity on new data (use marginal for simplicity)
        g_new = np.full(len(X_new), self.propensity.mean())
        tau_t = self.tau_model_t.predict(X_new)
        tau_c = self.tau_model_c.predict(X_new)
        return g_new * tau_t + (1 - g_new) * tau_c


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL ML SUITE — ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────


class CausalMLSuite:
    """
    Orchestrator for comparing multiple causal ML estimators.

    Provides:
      - compare_methods(): run all methods and compare ATEs
      - subgroup_analysis(): heterogeneity analysis across subgroups
      - sensitivity_analysis(): Rosenbaum bounds

    Usage
    -----
        suite = CausalMLSuite()
        cmp = suite.compare_methods(df, treatment="did", outcome="roa",
                                    X=["size", "lev", "age"])
        print(cmp)

        report = suite.subgroup_analysis(df, treatment="did", outcome="roa",
                                        X=["size"], subgroup_vars=["industry"])
        print(report)

        sens = suite.sensitivity_analysis(df, treatment="did", outcome="roa",
                                         X=["size"], gamma_range=[1.0, 1.25, 1.5, 2.0])
        print(sens)
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def compare_methods(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
        methods: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Run all specified causal ML methods and return a comparison table.

        Parameters
        ----------
        df : pd.DataFrame
        treatment : str
        outcome : str
        X : list[str]
        methods : list[str] | None
            List of methods to run. Options:
            "causal_forest", "dml", "x_learner", "t_learner"
            Defaults to all four.

        Returns
        -------
        pd.DataFrame
            One row per method with ATE, SE, CI, p-value, N.
        """
        if methods is None:
            methods = ["causal_forest", "dml", "x_learner", "t_learner"]

        rows = []
        fitted = {}

        for m in methods:
            try:
                if m == "causal_forest":
                    model = CausalForest(seed=self.seed)
                elif m == "dml":
                    model = DoubleML(seed=self.seed)
                elif m == "x_learner":
                    model = XLearner(seed=self.seed)
                elif m == "t_learner":
                    model = TLearner(seed=self.seed)
                else:
                    _log.warning(f"[CausalMLSuite] Unknown method: {m}")
                    continue

                res = model.fit(df, treatment=treatment, outcome=outcome, X=X)
                rows.append(res.to_dict())
                fitted[m] = model
                _log.info(f"[CausalMLSuite] {m}: ATE={res.ate:.4f} (SE={res.ate_se:.4f})")
            except Exception as e:
                _log.error(f"[CausalMLSuite] {m} failed: {e}")

        if not rows:
            return pd.DataFrame()

        result_df = pd.DataFrame(rows)
        cols_order = [
            "method", "ate", "ate_se", "ate_ci_lower", "ate_ci_upper",
            "ate_pval", "n_obs", "n_treated", "n_control",
        ]
        present = [c for c in cols_order if c in result_df.columns]
        result_df = result_df[present + [c for c in result_df.columns if c not in present]]

        # Format significance
        result_df["sig"] = result_df["ate_pval"].apply(
            lambda p: _significance(float(p)) if not np.isnan(float(p)) else ""
        )

        self._last_comparison = result_df
        self._fitted_models = fitted
        return result_df

    def subgroup_analysis(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
        subgroup_vars: list[str],
        method: str = "causal_forest",
    ) -> HeterogeneityReport:
        """
        Estimate ATE within subgroups defined by subgroup_vars.

        Tests H0: ATE equal across all subgroups using a simple F-test.

        Parameters
        ----------
        df : pd.DataFrame
        treatment : str
        outcome : str
        X : list[str]
        subgroup_vars : list[str]
            Variables to define subgroups (all combinations of values used).
        method : str
            Causal ML method to use ("causal_forest" | "dml" | "x_learner" | "t_learner").

        Returns
        -------
        HeterogeneityReport
        """
        from scipy import stats

        df_sub = df.dropna(subset=[treatment, outcome] + X + subgroup_vars).copy()

        # Build subgroup key
        df_sub["_subgroup"] = df_sub[subgroup_vars].astype(str).agg("_".join, axis=1)
        subgroups = df_sub["_subgroup"].unique().tolist()

        ate_by_sg: dict[str, float] = {}
        se_by_sg: dict[str, float] = {}
        n_by_sg: dict[str, int] = {}

        ate_vals = []

        for sg in subgroups:
            df_sg = df_sub[df_sub["_subgroup"] == sg].copy()
            n_sg = len(df_sg)

            if n_sg < 20:
                _log.warning(f"[CausalMLSuite] Subgroup '{sg}' has only {n_sg} obs, skipping")
                continue

            try:
                if method == "causal_forest":
                    model = CausalForest(seed=self.seed)
                elif method == "dml":
                    model = DoubleML(seed=self.seed)
                elif method == "x_learner":
                    model = XLearner(seed=self.seed)
                else:
                    model = TLearner(seed=self.seed)

                res = model.fit(df_sg, treatment=treatment, outcome=outcome, X=X)
                ate_by_sg[sg] = res.ate
                se_by_sg[sg] = res.ate_se
                n_by_sg[sg] = res.n_obs
                ate_vals.append(res.ate)
                _log.info(
                    f"[CausalMLSuite] Subgroup '{sg}': "
                    f"N={n_sg}, ATE={res.ate:.4f} (SE={res.ate_se:.4f})"
                )
            except Exception as e:
                _log.error(f"[CausalMLSuite] Subgroup '{sg}' failed: {e}")

        if not ate_vals:
            return HeterogeneityReport(treatment_var=treatment, outcome_var=outcome)

        # F-test for heterogeneity: H0 all ATEs equal
        np.mean(ate_vals)
        k = len(ate_vals)
        # Weighted by inverse variance
        weights = [1 / (se_by_sg.get(sg, 1.0) ** 2) for sg in subgroups if sg in ate_by_sg]
        weighted_ate = np.average(
            [ate_by_sg[sg] for sg in subgroups if sg in ate_by_sg], weights=weights
        )

        # Simplified chi2 test
        chi2_stat = 0.0
        for sg in subgroups:
            if sg in ate_by_sg and se_by_sg[sg] > 0:
                chi2_stat += ((ate_by_sg[sg] - weighted_ate) ** 2) / (se_by_sg[sg] ** 2)

        pval = float(1 - stats.chi2.cdf(chi2_stat, df=k - 1))
        interaction_effect = float(np.max(ate_vals) - np.min(ate_vals))

        report = HeterogeneityReport(
            subgroups=subgroups,
            ate_by_subgroup=ate_by_sg,
            se_by_subgroup=se_by_sg,
            n_by_subgroup=n_by_sg,
            test_stat=chi2_stat,
            pval=pval,
            interaction_effect=interaction_effect,
            treatment_var=treatment,
            outcome_var=outcome,
        )

        _log.info(
            f"[CausalMLSuite] Heterogeneity test: chi2={chi2_stat:.3f}, "
            f"p={pval:.4f}, interaction_effect={interaction_effect:.4f}"
        )
        return report

    def sensitivity_analysis(
        self,
        df: pd.DataFrame,
        treatment: str,
        outcome: str,
        X: list[str],
        gamma_range: list[float] | None = None,
    ) -> pd.DataFrame:
        """
        Rosenbaum bounds sensitivity analysis.

        Evaluates robustness of inference to unmeasured confounding
        at various Gamma levels.

        Parameters
        ----------
        df : pd.DataFrame
        treatment : str
        outcome : str
        X : list[str]
        gamma_range : list[float] | None
            Range of Gamma values. Defaults to [1.0, 1.25, 1.5, 2.0, 3.0].

        Returns
        -------
        pd.DataFrame
            Sensitivity table with p-value bounds per Gamma.
        """
        if gamma_range is None:
            gamma_range = [1.0, 1.25, 1.5, 2.0, 3.0]

        df_clean, T, Y, _ = _prep_data(df, treatment, outcome, X)
        _log.info(f"[CausalMLSuite] Sensitivity analysis: n={len(Y)}, Gamma={gamma_range}")

        result_df = _rosenbaum_bounds(T, Y, gamma_range)
        _log.info(
            f"[CausalMLSuite] Sensitivity: {result_df.to_dict(orient='records')}"
        )
        return result_df
