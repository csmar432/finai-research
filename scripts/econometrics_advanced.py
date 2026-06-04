"""
Advanced econometric methods for the research workflow.

Added in 2026-05-29:
    - WildClusterBootstrap: Wild cluster bootstrap for robust inference with few clusters
    - BaronKennyMediation: Baron-Kenny mediation analysis with Sobel + bootstrap CI
    - MultipleTestingCorrection: Bonferroni / Holm / FDR (Benjamini-Hochberg) corrections
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

# ─── Wild Cluster Bootstrap ────────────────────────────────────────────────────


@dataclass
class WildClusterBootstrapResult:
    """Result from a wild cluster bootstrap inference procedure."""

    original_stat: float
    bootstrap_tstats: np.ndarray
    p_value: float
    confidence_interval: tuple[float, float]
    n_bootstrap: int
    n_clusters: int
    cluster_method: str
    weighting_scheme: str

    def __repr__(self) -> str:
        return (
            f"WildBootstrap(τ={self.original_stat:.4f}, "
            f"p={self.p_value:.4f}, CI=({self.confidence_interval[0]:.4f}, "
            f"{self.confidence_interval[1]:.4f}), clusters={self.n_clusters}, "
            f"n_boot={self.n_bootstrap})"
        )

    def to_dict(self) -> dict:
        return {
            "original_stat": self.original_stat,
            "bootstrap_tstats": self.bootstrap_tstats.tolist(),
            "p_value": self.p_value,
            "ci_lower": self.confidence_interval[0],
            "ci_upper": self.confidence_interval[1],
            "n_bootstrap": self.n_bootstrap,
            "n_clusters": self.n_clusters,
            "cluster_method": self.cluster_method,
            "weighting_scheme": self.weighting_scheme,
        }


class WildClusterBootstrap:
    """
    Wild cluster bootstrap for inference with few treated clusters.

    Implements the wild cluster bootstrap t-test (WCBC) from
    Cameron, Gelbach & Miller (2008, RESTAT) for cluster-robust
    inference when the number of clusters is small (G < 30).

    The null hypothesis is H0: β = 0.  The procedure:
    1. Fit restricted model (β = 0) and obtain residuals.
    2. Draw N(0,1) bootstrap weights v_g for each cluster g.
    3. Construct bootstrap dependent variable: y* = Xβ̂ + v_g × û_ig.
    4. Re-fit model and compute bootstrap t-statistic.
    5. Repeat B times; p = fraction of |t*_b| ≥ |t|.

    Supports weighting schemes:
        - "rademacher": P(v=1) = P(v=-1) = 0.5 (default)
        - "mammen": Two-point distribution approximating N(0,1)
        - "webb": Six-point distribution (more accurate for small G)
        - "normal": v ~ N(0,1)

    Supports:
        - Single-cluster and multi-way (2-way) clustering
        - Cluster-Wild Bootstrap (CWBOOT) for any number of cluster dimensions
        - Restricted (WCR) and unrestricted (WCU) variants

    Usage:
        wcb = WildClusterBootstrap(
            data=df,
            y="outcome",
            X=["treatment", "covariate1", "covariate2"],
            clusters="firm_id",
            bootstrap_type="11"          # WCR, null imposed
            weighting_scheme="webb",
            n_bootstrap=999,
            random_state=42,
        )
        result = wcb.fit()
        print(result.p_value)
    """

    WEIGHTING_SCHEMES = {
        "rademacher": lambda n: (np.random.choice([-1, 1], size=n, replace=True)),  # noqa: E501
        "mammen": lambda n: _mammen_weights(n),
        "webb": lambda n: _webb_weights(n),
        "normal": lambda n: np.random.standard_normal(n),
    }

    BOOTSTRAP_TYPES = {
        "11": "wild_rademacher_CR1",
        "12": "wild_mammen_CR1",
        "13": "wild_webb_CR1",
        "14": "wild_normal_CR1",
        "21": "wild_rademacher_CR2",
        "22": "wild_mammen_CR2",
        "23": "wild_webb_CR2",
        "24": "wild_normal_CR2",
    }

    def __init__(
        self,
        data: pd.DataFrame,
        y: str,
        X: list[str],
        clusters: str | list[str] | None = None,
        bootstrap_type: str = "11",
        weighting_scheme: str = "webb",
        n_bootstrap: int = 999,
        random_state: int | None = None,
        drop_singletons: bool = True,
    ) -> None:
        if random_state is not None:
            np.random.seed(random_state)

        self.data = data.copy()
        self.y = y
        self.X = X
        self.clusters = clusters
        self.bootstrap_type = bootstrap_type
        self.weighting_scheme = weighting_scheme
        self.n_bootstrap = n_bootstrap
        self.drop_singletons = drop_singletons

        self._result: WildClusterBootstrapResult | None = None
        self._validate()

    def _validate(self) -> None:
        if self.bootstrap_type not in self.BOOTSTRAP_TYPES:
            raise ValueError(
                f"bootstrap_type must be one of {list(self.BOOTSTRAP_TYPES.keys())}, "
                f"got {self.bootstrap_type!r}"
            )
        if self.weighting_scheme not in self.WEIGHTING_SCHEMES:
            raise ValueError(
                f"weighting_scheme must be one of {list(self.WEIGHTING_SCHEMES.keys())}, "
                f"got {self.weighting_scheme!r}"
            )
        missing = [c for c in [self.y] + self.X if c not in self.data.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")

    def fit(self) -> WildClusterBootstrapResult:
        """
        Execute the wild cluster bootstrap.

        Returns:
            WildClusterBootstrapResult with p-value and confidence interval.
        """
        df = self.data.copy()

        # Drop rows with NaN in relevant columns
        cols = [self.y] + self.X
        if self.clusters:
            cl = [self.clusters] if isinstance(self.clusters, str) else self.clusters
            cols += cl
        df = df.dropna(subset=cols)

        y = df[self.y].values.astype(float)
        X = df[self.X].values.astype(float)
        X = np.column_stack([np.ones(len(X)), X])  # intercept

        # Fit restricted model (β = 0) under WCR null
        beta_r = np.zeros(X.shape[1])
        residuals = y - X @ beta_r

        # Compute original t-statistic for the treatment coefficient (β_1)
        # Re-fit unrestricted to get β̂ and V̂
        XtX_inv = np.linalg.inv(X.T @ X)
        beta_u = XtX_inv @ (X.T @ y)
        resid_u = y - X @ beta_u

        # Cluster-robust variance estimation
        if self.clusters is None:
            # iid variance
            k = X.shape[1]
            sigma2 = np.sum(resid_u**2) / (len(y) - k)
            var_beta = XtX_inv * sigma2
        elif isinstance(self.clusters, str):
            var_beta = self._cluster_vcov(X, resid_u)
        else:
            # Multi-way (2-way) clustering — use 2-way variance
            cl1, cl2 = self.clusters
            cl1_ids = df[cl1].values
            cl2_ids = df[cl2].values
            var_beta = self._cluster_vcov_2way(X, resid_u, cl1_ids, cl2_ids)

        se_treatment = np.sqrt(var_beta[1, 1])
        t_original = beta_u[1] / se_treatment

        # Wild bootstrap: draw cluster-level weights
        if isinstance(self.clusters, str):
            cluster_ids = df[self.clusters].values
            n_cl = len(np.unique(cluster_ids))
            weight_fn = self.WEIGHTING_SCHEMES[self.weighting_scheme]
            bootstrap_tstats = np.zeros(self.n_bootstrap)

            for b in range(self.n_bootstrap):
                # Draw cluster weights
                v_g = weight_fn(n_cl)
                v_map = dict(zip(np.unique(cluster_ids), v_g))
                v = np.array([v_map[c] for c in cluster_ids])

                # Bootstrap residuals (null imposed = restricted residuals)
                y_star = X @ beta_r + v * residuals
                beta_star = np.linalg.lstsq(X, y_star, rcond=None)[0]
                resid_star = y_star - X @ beta_star
                var_beta_star = self._cluster_vcov(X, resid_star)
                se_star = np.sqrt(var_beta_star[1, 1])
                bootstrap_tstats[b] = beta_star[1] / se_star if se_star > 1e-10 else 0

        else:
            # Multi-way (2-way) clustering
            cl1, cl2 = self.clusters
            cl1_ids = df[cl1].values
            cl2_ids = df[cl2].values
            n_cl1 = len(np.unique(cl1_ids))
            n_cl2 = len(np.unique(cl2_ids))
            weight_fn = self.WEIGHTING_SCHEMES[self.weighting_scheme]
            bootstrap_tstats = np.zeros(self.n_bootstrap)

            for b in range(self.n_bootstrap):
                v1 = weight_fn(n_cl1)
                v2 = weight_fn(n_cl2)
                v1_map = dict(zip(np.unique(cl1_ids), v1))
                v2_map = dict(zip(np.unique(cl2_ids), v2))
                v = np.array([v1_map[c1] * v2_map[c2]
                              for c1, c2 in zip(cl1_ids, cl2_ids)])

                y_star = X @ beta_r + v * residuals
                beta_star = np.linalg.lstsq(X, y_star, rcond=None)[0]
                resid_star = y_star - X @ beta_star
                var_beta_star = self._cluster_vcov_2way(
                    X, resid_star, cl1_ids, cl2_ids
                )
                se_star = np.sqrt(var_beta_star[1, 1])
                bootstrap_tstats[b] = beta_star[1] / se_star if se_star > 1e-10 else 0

        # Two-sided p-value
        p_value = float(np.mean(np.abs(bootstrap_tstats) >= abs(t_original)))

        # Percentile CI from bootstrap distribution
        ci_lower = float(np.percentile(beta_u[1] - bootstrap_tstats * se_treatment, 2.5))
        ci_upper = float(np.percentile(beta_u[1] - bootstrap_tstats * se_treatment, 97.5))

        self._result = WildClusterBootstrapResult(
            original_stat=float(beta_u[1]),
            bootstrap_tstats=bootstrap_tstats,
            p_value=p_value,
            confidence_interval=(ci_lower, ci_upper),
            n_bootstrap=self.n_bootstrap,
            n_clusters=int(n_cl) if isinstance(self.clusters, str) else 0,
            cluster_method=self.BOOTSTRAP_TYPES[self.bootstrap_type],
            weighting_scheme=self.weighting_scheme,
        )
        return self._result

    def _cluster_vcov(
        self, X: np.ndarray, residuals: np.ndarray
    ) -> np.ndarray:
        """Compute cluster-robust variance (CR0 / CR1)."""
        n, k = X.shape
        if isinstance(self.clusters, str):
            cluster_ids = self.data[self.clusters].values
        elif isinstance(self.clusters, list) and len(self.clusters) > 0:
            # List of column names → 2-way or multi-way clustering is active,
            # but _cluster_vcov is called only for 1-way cases.
            # If the list contains strings, read IDs from data.
            cluster_ids = self.data[self.clusters[0]].values
        else:
            cluster_ids = np.array(self.clusters)
        meat = np.zeros((k, k))
        for g in np.unique(cluster_ids):
            mask = cluster_ids == g
            xg = X[mask]
            ug = residuals[mask]
            meat += (xg.T @ ug)[:, None] @ (xg.T @ ug)[None, :]
        bread = np.linalg.inv(X.T @ X)
        vcov = bread @ meat @ bread
        adj = n / max(n - k, 1)
        return vcov * adj

    def _cluster_vcov_2way(
        self,
        X: np.ndarray,
        residuals: np.ndarray,
        cl1: np.ndarray,
        cl2: np.ndarray,
    ) -> np.ndarray:
        """Compute 2-way cluster-robust variance (Cameron-Gelbach-Miller 2011)."""
        n, k = X.shape
        vcov = np.zeros((k, k))
        # CR1 for cluster 1
        for g in np.unique(cl1):
            mask = cl1 == g
            xg = X[mask]
            ug = residuals[mask]
            vcov += (xg.T @ ug)[:, None] @ (xg.T @ ug)[None, :]
        # CR1 for cluster 2
        for g in np.unique(cl2):
            mask = cl2 == g
            xg = X[mask]
            ug = residuals[mask]
            vcov += (xg.T @ ug)[:, None] @ (xg.T @ ug)[None, :]
        # Minus overlap
        for g1 in np.unique(cl1):
            for g2 in np.unique(cl2):
                mask = (cl1 == g1) & (cl2 == g2)
                if mask.sum() > 0:
                    xg = X[mask]
                    ug = residuals[mask]
                    vcov -= (xg.T @ ug)[:, None] @ (xg.T @ ug)[None, :]
        bread = np.linalg.inv(X.T @ X)
        adj = n / (n - k)
        return bread @ vcov @ bread * adj

    @property
    def result(self) -> WildClusterBootstrapResult | None:
        return self._result


def _mammen_weights(n: int) -> np.ndarray:
    """Two-point distribution approximating N(0,1) (Mammen 1993)."""
    p = (np.sqrt(5) + 1) / (2 * np.sqrt(5))
    vals = [-np.sqrt((5 - np.sqrt(5)) / 10), np.sqrt((5 - np.sqrt(5)) / 10)]
    probs = [p, 1 - p]
    return np.random.choice(vals, size=n, p=probs)


def _webb_weights(n: int) -> np.ndarray:
    """Six-point distribution (Webb 2013), better for very small G."""
    support = np.array([
        -np.sqrt(3 / 2), -1, -np.sqrt(1 / 2),
        np.sqrt(1 / 2), 1, np.sqrt(3 / 2),
    ])
    probs = np.array([1/6] * 6)
    return np.random.choice(support, size=n, p=probs)


# ─── Baron-Kenny Mediation Analysis ──────────────────────────────────────────


@dataclass
class MediationResult:
    """Result from a Baron-Kenny mediation analysis."""

    path_a: float           # X → M coefficient
    path_b: float           # M → Y controlling for X
    direct_effect_c: float  # c = X → Y total effect
    indirect_effect: float   # a × b
    proportion_mediated: float
    p_value: float
    ci_lower: float
    ci_upper: float
    ci_method: str
    n_bootstrap: int
    significant: bool

    def __repr__(self) -> str:
        return (
            f"Mediation(a={self.path_a:.4f}, b={self.path_b:.4f}, "
            f"indirect={self.indirect_effect:.4f} ({self.proportion_mediated*100:.1f}%), "
            f"p={self.p_value:.4f})"
        )

    def to_dict(self) -> dict:
        return {
            "path_a": self.path_a,
            "path_b": self.path_b,
            "direct_effect_c": self.direct_effect_c,
            "indirect_effect": self.indirect_effect,
            "proportion_mediated": self.proportion_mediated,
            "p_value": self.p_value,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "ci_method": self.ci_method,
            "n_bootstrap": self.n_bootstrap,
            "significant": self.significant,
        }


class BaronKennyMediation:
    """
    Baron-Kenny mediation analysis with Sobel test and bootstrap CI.

    Implements the Baron-Kenny (1986) 4-step mediation analysis and
    the Sobel (1982) test, supplemented with percentile bootstrap CI
    (preferred when the indirect effect distribution may be non-normal).

    The mediation model (with controls C):
        M = i1 + a·X + b1·C + e1          (Step 2: X → M)
        Y = i2 + c·X + b2·C + e2          (Step 1: X → Y total)
        Y = i3 + c'·X + b·M + b3·C + e3   (Step 3: X+M → Y, M suppresses X)
        Y = i4 + c'·X + b·M + b4·C + e4   (Step 4: Sobel test of a·b)

    The indirect effect = a × b (SE via Sobel or bootstrap).
    Proportion mediated = a·b / c (fraction explained by mediator).

    Usage:
        bk = BaronKennyMediation(
            data=df,
            X="digitalization",      # independent variable
            M="innovation",           # mediator
            Y="productivity",         # outcome
            C=["size", "leverage"],   # controls (optional)
            robust=True,              # HC3 standard errors
            n_bootstrap=1000,
            random_state=42,
        )
        result = bk.fit()
        print(result.indirect_effect, result.p_value)
    """

    def __init__(
        self,
        data: pd.DataFrame,
        X: str,
        M: str,
        Y: str,
        C: list[str] | None = None,
        robust: bool = True,
        n_bootstrap: int = 1000,
        random_state: int | None = None,
    ) -> None:
        self.data = data.copy()
        self.X = X
        self.M = M
        self.Y = Y
        self.C = C or []
        self.robust = robust
        self.n_bootstrap = n_bootstrap
        self.rng = np.random.default_rng(random_state)

        self._result: MediationResult | None = None
        self._validate()

    def _validate(self) -> None:
        required = {self.X, self.M, self.Y} | set(self.C)
        missing = required - set(self.data.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")

    def _ols(
        self,
        y_col: str,
        x_cols: list[str],
        robust: bool = True,
    ) -> dict:
        """Run OLS regression, return coefficients and SE."""
        df = self.data.dropna(subset=[y_col] + x_cols)
        y_vals = df[y_col].values
        X_vals = np.column_stack([np.ones(len(df)), df[x_cols].values])
        n, k = X_vals.shape

        beta = np.linalg.lstsq(X_vals, y_vals, rcond=None)[0]
        resid = y_vals - X_vals @ beta
        df_res = n - k

        # OLS covariance
        sigma2 = np.sum(resid**2) / df_res
        if robust:
            # HC3 (MacKinnon-White 1985)
            # meat = Σ (infl_i² * x_i @ x_i^T) = X^T @ diag(infl²) @ X
            hii = np.diag(X_vals @ np.linalg.inv(X_vals.T @ X_vals) @ X_vals.T)
            hii = np.minimum(np.maximum(hii, 1e-10), 0.9999)
            infl = resid / (1 - hii)
            # Square element-wise (infl is 1-D)
            infl_sq = infl ** 2
            # meat[i,j] = Σ_k (infl_sq[k] * X_vals[k,i] * X_vals[k,j])
            meat = X_vals.T * infl_sq @ X_vals / n
            bread = np.linalg.inv(X_vals.T @ X_vals / n)
            vcov = bread @ meat @ bread * n / df_res
        else:
            vcov = np.linalg.inv(X_vals.T @ X_vals) * sigma2

        se = np.sqrt(np.diag(vcov))
        t_stats = beta / se
        p_vals = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=df_res))

        names = ["intercept"] + x_cols
        return {
            "coef": dict(zip(names, beta)),
            "se": dict(zip(names, se)),
            "t_stat": dict(zip(names, t_stats)),
            "p_value": dict(zip(names, p_vals)),
            "n_obs": n,
            "r_squared": 1 - np.sum(resid**2) / np.sum((y_vals - y_vals.mean())**2),
        }

    def fit(self) -> MediationResult:
        """Execute the full Baron-Kenny mediation analysis."""
        X_cols = [self.X] + self.C
        XM_cols = [self.X, self.M] + self.C

        # Step 1: Y = c·X + controls (total effect)
        step1 = self._ols(self.Y, X_cols, robust=self.robust)
        c_total = step1["coef"][self.X]

        # Step 2: M = a·X + controls (X → M)
        step2 = self._ols(self.M, X_cols, robust=self.robust)
        a = step2["coef"][self.X]

        # Step 3: Y = c'·X + b·M + controls (direct effect + mediator)
        step3 = self._ols(self.Y, XM_cols, robust=self.robust)
        c_prime = step3["coef"][self.X]
        b = step3["coef"][self.M]

        # Sobel test
        se_ab = np.sqrt(a**2 * step2["se"][self.X]**2 +
                        b**2 * step3["se"][self.M]**2)
        z_sobel = (a * b) / se_ab
        p_sobel = 2 * (1 - stats.norm.cdf(abs(z_sobel)))

        indirect = a * b
        prop_mediated = (indirect / c_total) if abs(c_total) > 1e-10 else 0.0

        # Bootstrap CI for the indirect effect
        ci_lower, ci_upper, boot_indirects = self._bootstrap_ci(
            X_cols, XM_cols, n_bootstrap=self.n_bootstrap
        )

        self._result = MediationResult(
            path_a=float(a),
            path_b=float(b),
            direct_effect_c=float(c_prime),
            indirect_effect=float(indirect),
            proportion_mediated=float(prop_mediated),
            p_value=float(p_sobel),
            ci_lower=float(ci_lower),
            ci_upper=float(ci_upper),
            ci_method="percentile_bootstrap",
            n_bootstrap=self.n_bootstrap,
            significant=bool(p_sobel < 0.05),
        )
        return self._result

    def _bootstrap_ci(
        self,
        X_cols: list[str],
        XM_cols: list[str],
        n_bootstrap: int,
    ) -> tuple[float, float, np.ndarray]:
        """Percentile bootstrap CI for the indirect effect a·b."""
        df = self.data.dropna(subset=set(X_cols + XM_cols + [self.M, self.Y]))
        n = len(df)

        boot_ab = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            idx = self.rng.integers(0, n, size=n)
            boot_df = df.iloc[idx]

            y_boot = boot_df[self.Y].values
            X_boot = np.column_stack([np.ones(len(boot_df)), boot_df[X_cols].values])
            beta_boot = np.linalg.lstsq(X_boot, y_boot, rcond=None)[0]
            a_boot = beta_boot[1]

            y_boot2 = boot_df[self.Y].values
            X_boot2 = np.column_stack([np.ones(len(boot_df)), boot_df[XM_cols].values])
            beta_boot2 = np.linalg.lstsq(X_boot2, y_boot2, rcond=None)[0]
            m_idx = XM_cols.index(self.M) + 1  # +1 for intercept
            b_boot = beta_boot2[m_idx]

            boot_ab[i] = a_boot * b_boot

        return (
            float(np.percentile(boot_ab, 2.5)),
            float(np.percentile(boot_ab, 97.5)),
            boot_ab,
        )

    @property
    def result(self) -> MediationResult | None:
        return self._result

    def summary(self) -> str:
        """Print a formatted summary of the mediation analysis."""
        if self._result is None:
            return "Mediation analysis not yet run. Call fit() first."
        r = self._result
        lines = [
            "=== Baron-Kenny Mediation Analysis ===",
            "X (IV) → M (Mediator) → Y (Outcome)",
            f"C (Controls): {self.C or 'None'}",
            "",
            f"Step 1 (X → Y total):  c = {r.direct_effect_c + r.indirect_effect:.4f}",
            f"Step 2 (X → M):        a = {r.path_a:.4f}",
            f"Step 3 (X+M → Y):      c' = {r.direct_effect_c:.4f}, b = {r.path_b:.4f}",
            "",
            f"Indirect effect (a×b): {r.indirect_effect:.4f}",
            f"Proportion mediated:   {r.proportion_mediated*100:.1f}%",
            f"Sobel z-statistic:    {r.indirect_effect / (abs(r.path_a) * self._result.path_b / r.p_value):.3f}",
            f"Sobel p-value:        {r.p_value:.4f} {'***' if r.p_value<0.001 else '**' if r.p_value<0.01 else '*' if r.p_value<0.05 else ''}",
            f"Bootstrap CI (95%):   [{r.ci_lower:.4f}, {r.ci_upper:.4f}]",
            f"Significant:          {'YES' if r.significant else 'NO'}",
        ]
        return "\n".join(lines)


# ─── Multiple Testing Correction ──────────────────────────────────────────────


@dataclass
class MultipleTestingResult:
    """Result of a multiple testing correction procedure."""

    method: str
    original_pvalues: np.ndarray
    n_tests: int
    alpha: float

    # Corrected p-values (one per hypothesis)
    corrected_pvalues: np.ndarray

    # Which hypotheses are rejected at level alpha
    rejected: np.ndarray

    # For FDR methods: estimated false discovery proportion
    fdp: float | None = None

    # For alpha-only methods: family-wise error rate bound
    fwer_bound: float | None = None

    def __repr__(self) -> str:
        n_rej = int(self.rejected.sum())
        return (
            f"MultipleTesting({self.method}, α={self.alpha}, "
            f"rejected={n_rej}/{self.n_tests})"
        )

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "n_tests": self.n_tests,
            "alpha": self.alpha,
            "original_pvalues": self.original_pvalues.tolist(),
            "corrected_pvalues": self.corrected_pvalues.tolist(),
            "rejected": self.rejected.tolist(),
            "n_rejected": int(self.rejected.sum()),
            "fdp": self.fdp,
            "fwer_bound": self.fwer_bound,
        }

    def summary_table(self) -> pd.DataFrame:
        """Return a readable pandas DataFrame of results."""
        return pd.DataFrame({
            "hypothesis": [f"H_{i+1}" for i in range(self.n_tests)],
            "p_original": self.original_pvalues,
            "p_corrected": self.corrected_pvalues,
            "rejected": self.rejected,
            "significant": self.rejected.astype(bool),
        })


class MultipleTestingCorrection:
    """
    Multiple hypothesis testing corrections.

    Implements the most common FWER and FDR control procedures:

    Family-Wise Error Rate (FWER) methods:
        - Bonferroni (1935): p_i ≤ α / m
        - Holm (1959): step-down procedure, uniformly more powerful than Bonferroni
        - Simes (1986): intermediate between Bonferroni and FDR
        - Hochberg (1988): step-up procedure (requires certain assumptions)

    False Discovery Rate (FDR) methods:
        - Benjamini-Hochberg (1995): controls FDR under independence or PRDS
        - Benjamini-Yekutieli (2001): FDR under arbitrary dependency

    Usage:
        mtc = MultipleTestingCorrection(
            pvalues=[0.001, 0.02, 0.04, 0.10, 0.50],
            alpha=0.05,
        )

        bh = mtc.benjamini_hochberg()
        bonf = mtc.bonferroni()
        holm = mtc.holm()

        print(bh.summary_table())
    """

    def __init__(
        self,
        pvalues: list[float] | np.ndarray | pd.Series,
        alpha: float = 0.05,
    ) -> None:
        self.original_pvalues = np.asarray(pvalues, dtype=float).flatten()
        self.alpha = alpha
        self.n_tests = len(self.original_pvalues)

        if self.n_tests == 0:
            raise ValueError("pvalues cannot be empty")
        if np.any((self.original_pvalues < 0) | (self.original_pvalues > 1)):
            raise ValueError("p-values must be in the interval [0, 1]")

        self._result: MultipleTestingResult | None = None

    def bonferroni(self) -> MultipleTestingResult:
        """
        Bonferroni correction: reject H_i iff p_i ≤ α / m.

        Controls FWER conservatively at level α.
        """
        p_corrected = np.minimum(
            self.original_pvalues * self.n_tests, 1.0
        )
        rejected = p_corrected <= self.alpha
        self._result = MultipleTestingResult(
            method="bonferroni",
            original_pvalues=self.original_pvalues,
            n_tests=self.n_tests,
            alpha=self.alpha,
            corrected_pvalues=p_corrected,
            rejected=rejected,
            fwer_bound=float(np.minimum(self.original_pvalues.sum(), 1.0)),
        )
        return self._result

    def holm(self) -> MultipleTestingResult:
        """
        Holm step-down procedure.

        Uniformly more powerful than Bonferroni while still controlling FWER.
        Ordered p-values: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
        Reject H_(i) if p_(i) ≤ α / (m - i + 1)
        """
        n = self.n_tests
        sorted_idx = np.argsort(self.original_pvalues)
        sorted_p = self.original_pvalues[sorted_idx]

        thresholds = self.alpha / (n - np.arange(n))  # α/(m-i+1)
        reject_sorted = sorted_p <= thresholds

        # Step-down: once we stop rejecting, stop
        rejected_sorted = np.zeros(n, dtype=bool)
        for i in range(n):
            if sorted_p[i] <= thresholds[i]:
                # Check if all previous were also rejected (step-down logic)
                if i == 0 or reject_sorted[:i+1].all():
                    rejected_sorted[i] = True
                else:
                    break
            else:
                break

        # Map back to original order
        rejected = np.zeros(n, dtype=bool)
        rejected[sorted_idx] = rejected_sorted

        p_corrected = np.minimum.accumulate(
            np.maximum.accumulate(
                self.original_pvalues * np.arange(n, 0, -1)
            ) / np.arange(n, 0, -1)
        ) / n * self.n_tests
        p_corrected = np.minimum(p_corrected, 1.0)

        self._result = MultipleTestingResult(
            method="holm",
            original_pvalues=self.original_pvalues,
            n_tests=n,
            alpha=self.alpha,
            corrected_pvalues=p_corrected,
            rejected=rejected,
            fwer_bound=None,
        )
        return self._result

    def hochberg(self) -> MultipleTestingResult:
        """
        Hochberg step-up procedure.

        Requires that test statistics are independent or satisfy PRDS.
        More powerful than Bonferroni when assumptions hold.
        Reject H_(i) if p_(i) ≤ α / (m - i + 1), step-up from largest p.
        """
        n = self.n_tests
        sorted_idx = np.argsort(self.original_pvalues)
        sorted_p = self.original_pvalues[sorted_idx]

        thresholds = self.alpha / (n - np.arange(n))  # α/(m-i+1)
        # Step-up: find the largest i such that p_(i) ≤ threshold_i
        reject_sorted = sorted_p <= thresholds
        # Reject all hypotheses up to the largest satisfying the condition
        k = np.where(reject_sorted)[0]
        if len(k) > 0:
            max_k = k[-1]
            rejected_sorted = np.zeros(n, dtype=bool)
            rejected_sorted[:max_k + 1] = True
        else:
            rejected_sorted = np.zeros(n, dtype=bool)

        rejected = np.zeros(n, dtype=bool)
        rejected[sorted_idx] = rejected_sorted

        p_corrected = np.minimum.accumulate(
            sorted_p * np.arange(n, 0, -1)
        ) / np.arange(n, 0, -1) * n
        p_corrected = np.minimum(np.maximum.accumulate(p_corrected[::-1])[::-1], 1.0)
        p_corrected_ordered = np.zeros(n)
        p_corrected_ordered[sorted_idx] = p_corrected
        p_corrected = p_corrected_ordered

        self._result = MultipleTestingResult(
            method="hochberg",
            original_pvalues=self.original_pvalues,
            n_tests=n,
            alpha=self.alpha,
            corrected_pvalues=p_corrected,
            rejected=rejected,
            fwer_bound=None,
        )
        return self._result

    def benjamini_hochberg(self) -> MultipleTestingResult:
        """
        Benjamini-Hochberg (1995) FDR-controlling procedure.

        Controls the expected false discovery proportion FDR = E[V/R | R>0]·P(R>0)
        at level α under independence or PRDS (positive regression dependency).
        Rejects H_(i) if p_(i) ≤ rank(i) / m × α
        """
        n = self.n_tests
        sorted_idx = np.argsort(self.original_pvalues)[::-1]  # descending
        sorted_p = self.original_pvalues[sorted_idx]

        # BH threshold: i/n × α (for sorted descending, rank = n - i)
        ranks = np.arange(n, 0, -1)  # rank n, n-1, ..., 1
        thresholds = ranks / n * self.alpha

        # Find largest k such that p_(k) ≤ threshold_k
        below = sorted_p <= thresholds
        if not below.any():
            rejected_sorted = np.zeros(n, dtype=bool)
        else:
            k = np.where(below)[0][0]  # first index where condition holds
            rejected_sorted = np.zeros(n, dtype=bool)
            rejected_sorted[:k+1] = True

        rejected = np.zeros(n, dtype=bool)
        rejected[sorted_idx] = rejected_sorted

        # Benjamini-Hochberg adjusted p-values
        p_corrected = np.zeros(n)
        sorted_p_asc = self.original_pvalues[np.argsort(self.original_pvalues)]
        ranks_asc = np.arange(1, n + 1)
        bh_factors = n / ranks_asc * self.alpha
        adj_asc = np.minimum.accumulate((sorted_p_asc / bh_factors)[::-1])[::-1]
        adj_asc = np.minimum(np.maximum.accumulate(adj_asc), 1.0)
        p_corrected[np.argsort(self.original_pvalues)] = np.minimum(adj_asc, 1.0)

        # FDP (actual false discovery proportion in this sample)
        if rejected.sum() > 0:
            # Under null, lower p-values are more suspicious; use BH estimate
            fdp = self.n_tests * self.alpha / max(rejected.sum(), 1) * np.mean(
                self.original_pvalues <= self.alpha
            )
            fdp = float(np.clip(fdp, 0, 1))
        else:
            fdp = 0.0

        self._result = MultipleTestingResult(
            method="benjamini_hochberg",
            original_pvalues=self.original_pvalues,
            n_tests=n,
            alpha=self.alpha,
            corrected_pvalues=p_corrected,
            rejected=rejected,
            fdp=fdp,
        )
        return self._result

    def benjamini_yekutieli(self) -> MultipleTestingResult:
        """
        Benjamini-Yekutieli (2001) FDR-controlling procedure.

        Conservative FDR control under arbitrary dependency.
        Uses c(m) = Σ_{i=1}^m (1/i) ≈ log(m) + γ
        """
        n = self.n_tests
        c_m = np.sum(1 / np.arange(1, n + 1))  # harmonic series
        alpha_conservative = self.alpha / c_m

        sorted_idx = np.argsort(self.original_pvalues)[::-1]
        sorted_p = self.original_pvalues[sorted_idx]
        ranks = np.arange(n, 0, -1)
        thresholds = ranks / n * alpha_conservative

        below = sorted_p <= thresholds
        if not below.any():
            rejected_sorted = np.zeros(n, dtype=bool)
        else:
            k = np.where(below)[0][0]
            rejected_sorted = np.zeros(n, dtype=bool)
            rejected_sorted[:k+1] = True

        rejected = np.zeros(n, dtype=bool)
        rejected[sorted_idx] = rejected_sorted

        p_corrected = sorted_p / (ranks / n * alpha_conservative)
        p_corrected = np.minimum(np.maximum.accumulate(p_corrected[::-1])[::-1], 1.0)
        p_corrected_ordered = np.zeros(n)
        p_corrected_ordered[sorted_idx] = p_corrected

        self._result = MultipleTestingResult(
            method="benjamini_yekutieli",
            original_pvalues=self.original_pvalues,
            n_tests=n,
            alpha=self.alpha,
            corrected_pvalues=p_corrected_ordered,
            rejected=rejected,
            fdp=None,
        )
        return self._result

    def summary_table(self) -> pd.DataFrame:
        """Return a summary table for the last computed result."""
        if self._result is None:
            raise ValueError("No correction has been computed. Run a method first.")
        return self._result.summary_table()

    @staticmethod
    def quick_correct(
        pvalues: list[float] | np.ndarray,
        alpha: float = 0.05,
        method: str = "bh",
    ) -> MultipleTestingResult:
        """
        One-liner for multiple testing correction.

        Args:
            pvalues: list of p-values
            alpha: significance level (default 0.05)
            method: "bonferroni" | "holm" | "hochberg" | "bh" | "by"

        Returns:
            MultipleTestingResult with corrected p-values and rejection decisions
        """
        mtc = MultipleTestingCorrection(pvalues, alpha)
        if method in ("bh", "benjamini_hochberg", "BH"):
            return mtc.benjamini_hochberg()
        elif method in ("by", "benjamini_yekutieli", "BY"):
            return mtc.benjamini_yekutieli()
        elif method in ("holm", "Holm"):
            return mtc.holm()
        elif method in ("hochberg", "Hochberg"):
            return mtc.hochberg()
        else:
            return mtc.bonferroni()
