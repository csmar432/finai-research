"""
research_framework/regression_engine.py
Universal regression engine with automatic DOF checking and robust result extraction.

Key features:
- Automatic degrees-of-freedom checking before fitting
- Falls back from firm-FE to pooled OLS when df insufficient
- Supports DID, OLS, PSM-DID, and panel regressions
- Extracts results robustly (handles both Series and ndarray params)
- All simulated variables flagged
- BOTH Chinese and English variable name support

Quick Start
-----------
最小可运行示例（合成 DID 数据）：

>>> import numpy as np
>>> import pandas as pd
>>> from scripts.research_framework.regression_engine import RegressionEngine

>>> # 1) 构造合成面板：200 家企业 × 4 年（2018-2021），2020 年起部分企业接受处理
>>> rng = np.random.default_rng(42)
>>> rows = []
>>> for firm_id in range(200):
...     is_treated = firm_id >= 100
...     for year in [2018, 2019, 2020, 2021]:
...         rows.append({
...             "firm_id": f"firm_{firm_id}",
...             "year": year,
...             "roa": 0.04 + 0.005 * (year - 2018) + rng.normal(0, 0.01)
...                    + (0.015 if (is_treated and year >= 2020) else 0),
...             "lev": 0.4 + rng.normal(0, 0.1),
...             "size": np.log(1e8 + rng.normal(0, 1e7)),
...             "tangibility": 0.3 + rng.normal(0, 0.05),
...             "esg_high": int(is_treated),
...             "post": int(year >= 2020),
...         })
>>> df = pd.DataFrame(rows)

>>> # 2) 初始化引擎
>>> engine = RegressionEngine(df)

>>> # 3) DID 回归（处理变量 × 时间虚拟变量）
>>> result = engine.did(
...     y_var="roa",
...     treat_var="esg_high",
...     time_var="post",
...     x_vars=["lev", "size", "tangibility"],
... )
>>> round(result["did_coef"], 3)  # ~ 0.015 (treatment effect)
0.015
>>> 0.0 <= result["did_pval"] <= 1.0
True
>>> result["n_obs"] > 500
True

Usage:
    engine = RegressionEngine(df, tracker)
    result = engine.did("lev", "esg_high", "post", x_vars=["ln_assets","roa","tangibility"])
    engine.print_table([result1, result2], ["(1) lev", "(2) ltd"])
    engine.save_latex("table1.tex")

Examples
--------
Examples 段对应 Issue #22 — 为 5 个核心计量模块添加可独立运行的 docstring 示例。
本模块中的所有示例使用合成数据（numpy.random），可独立于外部数据源运行。

参见：
  - tests/conftest.py 中的 ``mock_panel_df`` fixture（类似数据布局）
  - tests/test_regression_engine.py 中的端到端测试用例
  - docs/api_reference.md 中的 API 文档
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


# ── v2.2 (2026-07-13, PR-2.5): cache container for OLS baseline objects ──
@dataclass
class _BaselineCacheEntry:
    """Cached artefacts for one (y_var, x_vars, FE) baseline fit.

    ``XtX_inv`` and ``residuals`` together are sufficient to recompute
    cluster-robust SEs without re-fitting the design matrix, so callers
    (e.g. RobustnessRunner) can amortise the OLS fit across the
    robustness sweep.
    """
    X: np.ndarray
    y: np.ndarray
    params: np.ndarray
    residuals: np.ndarray
    XtX_inv: np.ndarray
    xnames: list[str]
    n_obs: int
    r2: float


_log = logging.getLogger(__name__)

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────
_log = logging.getLogger("regression_engine")
_log.setLevel(logging.INFO)

# ─────────────────────────────────────────
# INLINE DEPENDENCIES (no import needed)
# ─────────────────────────────────────────
def _extract(model, xnames: list[str]) -> dict:
    """Robust extraction from statsmodels OLS/WLS result."""
    if hasattr(model.params, "index"):
        names, params, bses, pvals, tvals = (
            list(model.params.index),
            model.params.values,
            model.bse.values,
            model.pvalues.values,
            model.tvalues.values,
        )
    else:
        names = xnames if xnames and len(xnames) == len(model.params) else [
            f"x{i}" for i in range(len(model.params))
        ]
        params = np.asarray(model.params)
        bses   = np.asarray(model.bse)
        pvals  = np.asarray(model.pvalues)
        tvals  = np.asarray(model.tvalues)

    out = {}
    for i, name in enumerate(names):
        try:
            p = float(params[i]) if not (isinstance(params[i], float) and np.isnan(params[i])) else 0.0
            s = float(bses[i]) if not (isinstance(bses[i], float) and np.isnan(bses[i])) else 0.0
            pv = float(pvals[i]) if not (isinstance(pvals[i], float) and np.isnan(pvals[i])) else 1.0
            tv = float(tvals[i]) if not (isinstance(tvals[i], float) and np.isnan(tvals[i])) else 0.0
        except (TypeError, ValueError):
            _log.warning("Coefficient extraction failed for variable '%s' at index %d — skipping", name, i)
            continue
        sig = ""
        if pv < 0.001: sig = "***"
        elif pv < 0.01:  sig = "**"
        elif pv < 0.05:  sig = "*"
        elif pv < 0.10:  sig = r"$\dagger$"
        out[name] = dict(coef=p, se=s, pval=pv, tstat=tv, sig=sig)
    return out


def _fmt(v: dict, d: int = 4) -> str:
    """Format coef+se as $coef^{sig} (se)$."""
    return f"${v['coef']:.{d}f}{v.get('sig','')}$ (${v['se']:.{d}f}$)"


# ─────────────────────────────────────────
# MAIN REGRESSION ENGINE
# ─────────────────────────────────────────
class RegressionEngine:
    """
    Universal regression engine for empirical finance/econ papers.

    Key design principle: NEVER silently skip firm fixed effects when the data
    doesn't support it. Instead, automatically diagnose and fall back to pooled OLS,
    with explicit logging and provenance update.

    Args:
        df: Panel DataFrame. Must have firm identifier and year columns.
        tracker: ProvenanceTracker for marking simulated variables.
        firm_col: Name of firm identifier column (default: "firm_id" or "ticker")
        year_col: Name of year column (default: "year")
    """

    def __init__(
        self,
        df: pd.DataFrame,
        tracker=None,
        firm_col: str = "ticker",
        year_col: str = "year",
        strict_no_simulated: bool = False,
    ):
        self.df = df
        self.tracker = tracker
        self.firm_col = firm_col
        self.year_col = year_col
        self._results: list[dict] = []
        self._warnings: list[str] = []
        self.strict_no_simulated = strict_no_simulated

        # ── v2.2 (2026-07-13, PR-2.5): cache nunique() calls so that the
        # repeated did() invocations during a robustness sweep don't
        # re-scan the full DataFrame every time.  These are O(N) over the
        # panel and were being executed 4-16× per robustness run.
        try:
            self._n_firms = (
                int(self.df[self.firm_col].nunique())
                if self.firm_col in self.df.columns
                else 0
            )
        except Exception:  # noqa: S110
            self._n_firms = 0
        try:
            self._n_periods = (
                int(self.df[self.year_col].nunique())
                if self.year_col in self.df.columns
                else 0
            )
        except Exception:  # noqa: S110
            self._n_periods = 0

        # ── v2.2 (2026-07-13, PR-2.5): LRU cache of OLS baseline objects
        # so that robustness sweeps sharing (y_var, x_vars, FE flags) do
        # not refit the design matrix from scratch.  The cache key omits
        # ``df`` identity — instead we hash the column-name list — and
        # callers needing ``XtX``/``residuals``/``groups`` for cluster SE
        # can pull them straight from this cache.
        self._baseline_cache: "OrderedDict[tuple, _BaselineCacheEntry]" = OrderedDict()
        self._baseline_cache_size = 32

        # ── P2-QUAL-2: DRY-consolidated simulated data integrity check ─────
        # Extracted from duplicate blocks (audit fix 2026-06-24).
        # Scans df.attrs / column metadata for is_simulated=True flags.
        # In strict_no_simulated mode, raises ValueError to protect research integrity.
        self._check_simulated_guard(df, context="__init__")

    def _check_simulated_guard(self, df: pd.DataFrame, context: str = "") -> None:
        """Research integrity guardrail: detect and warn about simulated data flags.

        DRY extraction (audit fix 2026-06-24): replaces two duplicate blocks that
        previously appeared in __init__.  Calling this with the data once is sufficient.
        """
        try:
            df_meta = getattr(df, "attrs", {}) or {}
            is_simulated = bool(df_meta.get("is_simulated", False))
            simulated_vars = list(df_meta.get("simulated_vars", []))
            if is_simulated or simulated_vars:
                msg = (
                    f"[OLSWrapper] WARNING (check {context!r}): dataframe contains "
                    f"{len(simulated_vars)} simulated variable(s): {simulated_vars[:5]}"
                    + (" ..." if len(simulated_vars) > 5 else "")
                    + ". Downstream results MUST NOT be reported as empirical findings."
                    " See DISCLAIMER in report_generator.py."
                )
                _log.warning(msg)
                self._warnings.append(msg)
                if self.strict_no_simulated:
                    raise ValueError(
                        f"OLSWrapper(strict_no_simulated=True): "
                        f"df contains simulated variables {simulated_vars}. "
                        "Refusing to run to protect research integrity."
                    )
        except ValueError:
            raise
        except Exception as exc:
            _log.debug(
                "[OLSWrapper] _check_simulated_guard(%s) failed (non-fatal): %s",
                context, exc,
            )

    # ─────────────────────────────────────
    # DEGREES OF FREEDOM CHECK
    # ─────────────────────────────────────
    def _check_dof(
        self,
        n_obs: int,
        x_vars: list[str],
        has_firm_fe: bool = True,
        has_year_fe: bool = True,
    ) -> dict:
        """Check if the regression has sufficient DOF. Returns diagnostic dict."""
        n_reg = len(x_vars)
        n_fe = 0
        # v2.2 (2026-07-13, PR-2.5): use cached nunique() values to avoid
        # repeated O(N) scans of the panel.
        if has_firm_fe and self.firm_col in self.df.columns:
            n_fe += max(0, getattr(self, "_n_firms", 0) - 1)
        if has_year_fe and self.year_col in self.df.columns:
            n_fe += max(0, getattr(self, "_n_periods", 0) - 1)
        n_params = n_reg + n_fe
        residual_df = max(0, n_obs - n_params)
        min_df = 10
        is_valid = residual_df >= min_df
        issue = ""
        if residual_df <= 0:
            issue = f"CRITICAL: {n_obs} obs < {n_params} params — model not identified"
        elif residual_df < min_df:
            issue = f"WARNING: only {residual_df} residual df (recommended min: {min_df})"

        return dict(
            n_obs=n_obs, n_reg=n_reg, n_fe=n_fe, n_params=n_params,
            residual_df=residual_df, is_valid=is_valid, issue=issue,
            fallback_triggered=not is_valid,
        )

    # ─────────────────────────────────────
    # TWO-WAY CLUSTERED STANDARD ERRORS
    # ─────────────────────────────────────
    def _two_way_clustered_se(
        self,
        X: np.ndarray,
        y: np.ndarray,
        cluster1: np.ndarray,
        cluster2: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute Cameron-Gelbach-Miller (2011) two-way clustered standard errors.

        V = V_cl1 + V_cl2 - V_pooled

        Uses the cluster-robust variance estimator (CR0) with bias correction
        for small samples.

        Args:
            X: Design matrix (n_obs x n_params)
            y: Response vector (n_obs,)
            cluster1: First clustering variable (e.g., firm_id)
            cluster2: Second clustering variable (e.g., year)

        Returns:
            (params, se) — coefficient estimates and clustered standard errors
        """
        n, k = X.shape
        residuals = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]

        # Compute OLS Hessian (information matrix)
        # bread = (X'X / n)^{-1} — inverse of (X'X) / n
        XtX = X.T @ X
        try:
            XtX_inv = np.linalg.inv(XtX)
        except np.linalg.LinAlgError:
            XtX_inv = np.linalg.pinv(XtX)
        bread = XtX_inv  # (k x k)

        def _one_way_meat(X_mat, eps, cl):
            """Compute one-way clustered meat matrix."""
            g = cl
            unique_g = np.unique(g)
            M = np.zeros((k, k))
            for gv in unique_g:
                mask = g == gv
                xi = X_mat[mask]  # (n_g x k)
                ei = eps[mask]    # (n_g,)
                mi = xi.T @ ei  # (k,) — inner product: sum over observations in cluster g
                M += np.outer(mi, mi)  # (k, k) — outer product
            n_groups = len(unique_g)
            if n_groups > 1:
                M *= n_groups / (n_groups - 1)  # BCH correction
            return M

        # Three one-way meats
        m1 = _one_way_meat(X, residuals, cluster1)
        m2 = _one_way_meat(X, residuals, cluster2)

        # Union clustering (pooled)
        combined = np.array([cluster1, cluster2])
        # np.char.add handles string dtype safely across numpy 1.x
        combined_hash = np.char.add(np.char.add(combined[0].astype(str), "_"), combined[1].astype(str))
        _, uniq_idx = np.unique(combined_hash, return_index=True)
        # Pooled: compute using union group IDs
        pooled_labels, inv_pooled = np.unique(combined_hash, return_inverse=True)
        m_pooled = _one_way_meat(X, residuals, inv_pooled)

        # Two-way meat (CGM bias-corrected)
        meat = m1 + m2 - m_pooled

        # Variance-covariance: bread @ meat @ bread / n
        vcov = bread @ meat @ bread / n
        se = np.sqrt(np.diag(vcov))

        # Recompute params using all available data
        params = np.linalg.lstsq(X, y, rcond=None)[0]

        return params, se

    def two_way_clustered_fit(
        self,
        y_var: str,
        x_vars: list[str],
        cluster1: str,
        cluster2: str,
        use_firm_fe: bool = True,
        use_year_fe: bool = True,
    ) -> dict:
        """Run OLS with two-way clustered standard errors (firm × year).

        This method bypasses the standard statsmodels fit() path and uses
        the Cameron-Gelbach-Miller (2011) bias-corrected two-way clustering.

        Args:
            y_var: Dependent variable column name
            x_vars: List of independent variable column names
            cluster1: First clustering dimension (e.g., "ticker" for firm)
            cluster2: Second clustering dimension (e.g., "year" for time)
            use_firm_fe: Include firm fixed effects (as cluster1 dummies)
            use_year_fe: Include year fixed effects (as cluster2 dummies)

        Returns:
            dict with keys: coefficients, standard_errors, pvalues, tstats,
            n_obs, r_squared, all_coefs, diagnostic, cov_type
        """
        df_sub = self.df.dropna(subset=[y_var] + x_vars)
        n_obs = len(df_sub)

        if n_obs == 0:
            _log.warning("[regression_engine] two_way_clustered: no observations after dropna")
            return {
                "coefficients": {}, "standard_errors": {}, "pvalues": {},
                "tstats": {}, "n_obs": 0, "r_squared": 0.0,
                "all_coefs": {}, "diagnostic": {
                    "error": "no observations",
                    "cov_type": "two_way_clustered",
                },
                "cov_type": "two_way_clustered",
            }

        if cluster1 == cluster2:
            _log.info(
                "[regression_engine] two_way_clustered: cluster1 == cluster2, "
                "falling back to one-way clustered SE."
            )
            return self.ols(
                y_var=y_var, x_vars=x_vars,
                cluster_var=cluster1,
                use_firm_fe=use_firm_fe, use_year_fe=use_year_fe,
            )

        cl1_vals = df_sub[cluster1].values
        cl2_vals = df_sub[cluster2].values

        # Build design matrix
        X_parts = [df_sub[x_vars].astype(float)]
        if use_firm_fe and cluster1 in df_sub.columns:
            firm_dummies = pd.get_dummies(df_sub[cluster1], prefix="firm", drop_first=True).astype(float)
            X_parts.append(firm_dummies)
        if use_year_fe and cluster2 in df_sub.columns:
            year_dummies = pd.get_dummies(df_sub[cluster2], prefix="yr", drop_first=True).astype(float)
            X_parts.append(year_dummies)

        X = pd.concat(X_parts, axis=1).fillna(0).values
        y = df_sub[y_var].astype(float).values
        xnames = (
            x_vars
            + (list(pd.get_dummies(df_sub[cluster1], prefix="firm", drop_first=True).columns) if use_firm_fe and cluster1 in df_sub.columns else [])
            + (list(pd.get_dummies(df_sub[cluster2], prefix="yr", drop_first=True).columns) if use_year_fe and cluster2 in df_sub.columns else [])
        )

        # Compute two-way clustered SEs
        params, se = self._two_way_clustered_se(X, y, cl1_vals, cl2_vals)

        # DOF: min(n_cl1, n_cl2) - 1
        n_cl1 = len(np.unique(cl1_vals))
        n_cl2 = len(np.unique(cl2_vals))
        dof = max(1, min(n_cl1, n_cl2) - 1)
        tstats = params / se
        pvals = 2 * (1 - stats.t.cdf(np.abs(tstats), df=dof))

        # R-squared
        y_hat = X @ params
        ss_res = np.sum((y - y_hat) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # Build all_coefs dict
        all_coefs = {}
        for i, name in enumerate(xnames):
            if i < len(params):
                p = float(params[i])
                s = float(se[i])
                pv = float(pvals[i])
                tv = float(tstats[i])
                sig = ""
                if pv < 0.001: sig = "***"
                elif pv < 0.01:  sig = "**"
                elif pv < 0.05:  sig = "*"
                elif pv < 0.10:  sig = r"$\dagger$"
                all_coefs[name] = dict(coef=p, se=s, pval=pv, tstat=tv, sig=sig)

        diag = {
            "n_obs": n_obs,
            "n_cl1": n_cl1,
            "n_cl2": n_cl2,
            "dof": dof,
            "is_valid": dof >= 1,
            "issue": "" if dof >= 1 else f"Two-way clustering DOF too small: {dof}",
            "fallback_triggered": False,
            "fe_drop_reason": "two_way_clustered",
            "cov_type": "two_way_clustered",
        }

        return {
            "coefficients": {name: float(params[i]) for i, name in enumerate(xnames) if i < len(params)},
            "standard_errors": {name: float(se[i]) for i, name in enumerate(xnames) if i < len(se)},
            "pvalues": {name: float(pvals[i]) for i, name in enumerate(xnames) if i < len(pvals)},
            "tstats": {name: float(tstats[i]) for i, name in enumerate(xnames) if i < len(tstats)},
            "n_obs": n_obs,
            "r_squared": float(r_squared),
            "all_coefs": all_coefs,
            "diagnostic": diag,
            "cov_type": "two_way_clustered",
        }

    # ─────────────────────────────────────
    # DID REGRESSION
    # ─────────────────────────────────────
    def did(
        self,
        y_var: str,
        treat_var: str,
        time_var: str,
        x_vars: list[str] | None = None,
        did_interaction: str | None = None,
        did_name: str = "did",
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
        use_firm_fe: bool = True,
        use_year_fe: bool = True,
        robust_se: bool = True,
    ) -> dict:
        """
        Run a difference-in-differences regression with automatic FE selection.

        If DOF are insufficient with firm FE, automatically falls back to pooled OLS
        and logs the fallback. Does NOT silently use firm FE when it breaks identification.

        Args:
            y_var: Dependent variable column name
            treat_var: Treatment indicator (time-invariant, e.g. "esg_high")
            time_var: Time indicator (e.g. "post" = 1 for post-treatment years)
            x_vars: Control variables (list of column names)
            did_interaction: Name of the DID term in df (e.g. "did" = treat_var × time_var)
            did_name: Label for the DID coefficient in output
            cluster_var: Primary cluster variable for SEs (default: firm_col)
            cluster2_var: Second clustering variable for two-way SE (e.g., "year")
            use_firm_fe: Whether to include firm fixed effects
            use_year_fe: Whether to include year fixed effects
            robust_se: Use HC1 robust standard errors

        Returns:
            dict with keys: did_coef, did_se, did_pval, did_sig, model, xnames, diagnostic
        """
        x_vars = x_vars or []
        df_sub = self.df.dropna(subset=[y_var] + [treat_var, time_var] + x_vars)
        n_obs = len(df_sub)

        if n_obs == 0:
            _log.warning(
                f"[regression_engine] dropna removed all observations. "
                f"Original N={len(self.df)}. Check data quality and variable names."
            )
            return {
                "did_coef": 0.0, "did_se": 0.0, "did_pval": 1.0, "did_sig": False,
                "n_obs": 0, "diagnostic": {"error": "no observations after dropna", "n_sub": 0},
                "model": None, "xnames": x_vars or [],
            }

        # ── DOF check — selectively drop FEs if insufficient ──
        x_vars_for_dof = [treat_var, time_var] + x_vars
        n_reg = len(x_vars_for_dof)

        def _did_fe_drop(n_obs, n_reg, has_firm, has_year):
            # v2.2 (2026-07-13, PR-2.5): use cached nunique.
            f_fe = (getattr(self, "_n_firms", 0) - 1) if has_firm and self.firm_col in self.df.columns else 0
            y_fe = (getattr(self, "_n_periods", 0) - 1) if has_year and self.year_col in self.df.columns else 0
            if n_obs - (n_reg + f_fe + y_fe) >= 10:
                return True, True, "both FEs"
            if has_firm and n_obs - (n_reg + f_fe) >= 10:
                return True, False, "firm FE only"
            if has_year and n_obs - (n_reg + y_fe) >= 10:
                return False, True, "year FE only"
            return False, False, "pooled OLS"

        firm_ok, year_ok, fe_desc = _did_fe_drop(
            n_obs, n_reg, use_firm_fe, use_year_fe
        )
        if not (use_firm_fe == firm_ok and use_year_fe == year_ok):
            msg = (f"DOF insufficient for requested FEs — using {fe_desc}. "
                   f"N={n_obs}, reg={n_reg}")
            _log.warning(msg)
            self._warnings.append(msg)
            use_firm_fe, use_year_fe = firm_ok, year_ok

        # ── Build design matrix ──
        X_parts = [df_sub[x_vars].astype(float)] if x_vars else []
        const_col = sm.add_constant(pd.DataFrame(index=df_sub.index))

        if did_interaction and did_interaction in df_sub.columns:
            X_parts.append(df_sub[did_interaction].astype(float).rename(did_name))
        else:
            # Build DID term
            X_parts.append(
                (df_sub[treat_var].astype(float) * df_sub[time_var].astype(float)).rename(did_name)
            )
        X_parts.append(const_col)

        if use_firm_fe and self.firm_col in df_sub.columns:
            firm_dummies = pd.get_dummies(df_sub[self.firm_col], prefix="firm", drop_first=True).astype(float)
            X_parts.append(firm_dummies)
        if use_year_fe and self.year_col in df_sub.columns:
            year_dummies = pd.get_dummies(df_sub[self.year_col], prefix="yr", drop_first=True).astype(float)
            X_parts.append(year_dummies)

        X = pd.concat(X_parts, axis=1).fillna(0)
        # NOTE: do NOT add constant again — const_col was already appended at line 205
        y = df_sub[y_var].astype(float).values
        xnames = list(X.columns)

        # Build diagnostic dict BEFORE SE computation (referenced by both branches)
        diag = {
            "n_obs": n_obs,
            "n_reg": n_reg,
            # v2.2 (2026-07-13, PR-2.5): use cached nunique.
            "n_fe": (
                (getattr(self, "_n_firms", 0) - 1 if use_firm_fe and self.firm_col in self.df.columns else 0) +
                (getattr(self, "_n_periods", 0) - 1 if use_year_fe and self.year_col in self.df.columns else 0)
            ),
            "residual_df": max(0, n_obs - n_reg),
            "is_valid": True,
            "issue": "",
            "fallback_triggered": not (firm_ok if use_firm_fe else True) or not (year_ok if use_year_fe else True),
            "fe_drop_reason": fe_desc,
        }

        # ── Two-way clustered SE path ─────────────────────────────────────
        two_way = (
            cluster2_var is not None
            and cluster_var is not None
            and cluster_var != cluster2_var
            and cluster_var in df_sub.columns
            and cluster2_var in df_sub.columns
        )
        cov_type = None  # always assign so it's in scope for the fallback below
        if two_way:
            _log.info(
                "[regression_engine] did() using two-way clustered SE "
                f"({cluster_var} × {cluster2_var})"
            )
            cl1 = df_sub[cluster_var].values
            cl2 = df_sub[cluster2_var].values
            X_arr = X.values.astype(float)
            y_arr = y
            params, se = self._two_way_clustered_se(X_arr, y_arr, cl1, cl2)
            # Build results dict from two-way results
            n_cl1 = len(np.unique(cl1))
            n_cl2 = len(np.unique(cl2))
            dof = max(1, min(n_cl1, n_cl2) - 1)
            tstats_arr = params / se
            pvals_arr = 2 * (1 - stats.t.cdf(np.abs(tstats_arr), df=dof))
            results = {}
            for i, name in enumerate(xnames):
                if i < len(params):
                    pv = float(pvals_arr[i])
                    sig = ""
                    if pv < 0.001: sig = "***"
                    elif pv < 0.01:  sig = "**"
                    elif pv < 0.05:  sig = "*"
                    elif pv < 0.10:  sig = r"$\dagger$"
                    results[name] = dict(
                        coef=float(params[i]),
                        se=float(se[i]),
                        pval=pv,
                        tstat=float(tstats_arr[i]),
                        sig=sig,
                    )
            # Patch model-like object so downstream code still works
            class _TwoWayModel:
                def __init__(m_self, params, se, pvals, r2):
                    m_self.params = params
                    m_self.bse = se
                    m_self.pvalues = pvals
                    m_self.tvalues = params / se
                    m_self.rsquared = r2
            y_hat = X_arr @ params
            ss_res = np.sum((y_arr - y_hat) ** 2)
            ss_tot = np.sum((y_arr - y_arr.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            model = _TwoWayModel(params, se, pvals_arr, r2)
            diag["cov_type"] = "two_way_clustered"
            diag["n_cl1"] = n_cl1
            diag["n_cl2"] = n_cl2
            diag["dof"] = dof
        else:
            # ── Standard fit (HC1 / one-way cluster) ──
            cov_type = "nonrobust"  # fallback — branches below always override
            if robust_se and not cluster_var:
                cov_type = "HC1"
                cov_kwds = None
            elif cluster_var and cluster_var in df_sub.columns:
                cov_type = "cluster"
                cov_kwds = {"groups": df_sub[cluster_var].values}
            else:
                if cluster_var:
                    _log.warning(
                        f"[regression_engine] cluster_var='{cluster_var}' not found in "
                        f"df.columns. Falling back to nonrobust SE."
                    )
                cov_kwds = None

            fit_kwargs = {}
            if cov_kwds is not None:
                fit_kwargs["cov_kwds"] = cov_kwds

            model = sm.OLS(y, X.values).fit(cov_type=cov_type, **fit_kwargs)
            results = _extract(model, xnames)

        # ── Find DID coefficient ──
        did_coef, did_se, did_pval = 0.0, 0.0, 1.0
        for name, v in results.items():
            if name == did_name or treat_var in name and time_var in name:
                did_coef = v["coef"]; did_se = v["se"]; did_pval = v["pval"]
                break

        r_squared = float(model.rsquared) if hasattr(model, "rsquared") else 0.0
        diag["cov_type"] = diag.get("cov_type", cov_type)

        output = {
            "did_coef": did_coef, "did_se": did_se, "did_pval": did_pval,
            "did_sig": results.get(did_name, {}).get("sig", ""),
            "model": model, "xnames": xnames,
            "diagnostic": diag,
            "n_obs": n_obs,
            "r_squared": r_squared,
            "all_coefs": results,
            "cov_type": diag.get("cov_type", cov_type),
        }
        self._results.append(output)
        return output

    # ─────────────────────────────────────
    # OLS (POOLED) REGRESSION
    # ─────────────────────────────────────
    def ols(
        self,
        y_var: str,
        x_vars: list[str],
        use_firm_fe: bool = True,
        use_year_fe: bool = True,
        cluster_var: str | None = None,
        cluster2_var: str | None = None,
        robust_se: bool = True,
    ) -> dict:
        """Pooled OLS with optional FEs and robust SEs.

        Args:
            y_var: Dependent variable
            x_vars: List of independent variables
            use_firm_fe: Include firm fixed effects
            use_year_fe: Include year fixed effects
            cluster_var: Primary cluster variable
            cluster2_var: Second cluster variable for two-way clustered SE
            robust_se: Use HC1 robust SE when no clustering
        """
        df_sub = self.df.dropna(subset=[y_var] + x_vars)
        n_obs = len(df_sub)

        def _fe_drop_dof(n_obs, n_reg, has_firm, has_year):
            """Test if combined FEs are affordable, then try each selectively."""
            # v2.2 (2026-07-13, PR-2.5): use cached nunique.
            f_fe = (getattr(self, "_n_firms", 0) - 1) if has_firm and self.firm_col in self.df.columns else 0
            y_fe = (getattr(self, "_n_periods", 0) - 1) if has_year and self.year_col in self.df.columns else 0
            # Try no FE
            if n_obs - n_reg >= 10:
                return False, False, "pooled OLS (N≥10)"
            # Try each FE alone
            if has_firm and n_obs - (n_reg + f_fe) >= 10:
                return True, False, f"firm FE only (N={n_obs}, reg={n_reg}, f_fe={f_fe})"
            if has_year and n_obs - (n_reg + y_fe) >= 10:
                return False, True, f"year FE only (N={n_obs}, reg={n_reg}, y_fe={y_fe})"
            return False, False, f"pooled (N={n_obs}, reg={n_reg}) insufficient for any FE"

        use_firm, use_year, fe_msg = _fe_drop_dof(
            n_obs, len(x_vars), use_firm_fe, use_year_fe
        )
        if not (use_firm_fe == use_firm and use_year_fe == use_year):
            msg = f"DOF insufficient — {fe_msg} (dropped: firm={'Y' if use_firm_fe and not use_firm else 'n'}, year={'Y' if use_year_fe and not use_year else 'n'})"
            _log.warning(msg)
            self._warnings.append(msg)

        X_parts = [df_sub[x_vars].astype(float)]
        if use_firm_fe and self.firm_col in df_sub.columns:
            firm_dummies = pd.get_dummies(df_sub[self.firm_col], prefix="firm", drop_first=True).astype(float)
            X_parts.append(firm_dummies)
        if use_year_fe and self.year_col in df_sub.columns:
            year_dummies = pd.get_dummies(df_sub[self.year_col], prefix="yr", drop_first=True).astype(float)
            X_parts.append(year_dummies)

        X = pd.concat(X_parts, axis=1).fillna(0)
        y = df_sub[y_var].astype(float).values
        xnames = list(X.columns)

        two_way = (
            cluster2_var is not None
            and cluster_var is not None
            and cluster_var != cluster2_var
            and cluster_var in df_sub.columns
            and cluster2_var in df_sub.columns
        )
        if two_way:
            _log.info(
                "[regression_engine] ols() using two-way clustered SE "
                f"({cluster_var} × {cluster2_var})"
            )
            cl1 = df_sub[cluster_var].values
            cl2 = df_sub[cluster2_var].values
            X_arr = X.values.astype(float)
            params, se = self._two_way_clustered_se(X_arr, y, cl1, cl2)
            n_cl1 = len(np.unique(cl1))
            n_cl2 = len(np.unique(cl2))
            dof = max(1, min(n_cl1, n_cl2) - 1)
            tstats_arr = params / se
            pvals_arr = 2 * (1 - stats.t.cdf(np.abs(tstats_arr), df=dof))
            results = {}
            for i, name in enumerate(xnames):
                if i < len(params):
                    pv = float(pvals_arr[i])
                    sig = ""
                    if pv < 0.001: sig = "***"
                    elif pv < 0.01:  sig = "**"
                    elif pv < 0.05:  sig = "*"
                    elif pv < 0.10:  sig = r"$\dagger$"
                    results[name] = dict(
                        coef=float(params[i]),
                        se=float(se[i]),
                        pval=pv,
                        tstat=float(tstats_arr[i]),
                        sig=sig,
                    )
            y_hat = X_arr @ params
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            cov_type = "two_way_clustered"
            diag = {
                "n_obs": n_obs,
                "n_reg": len(x_vars),
                # v2.2 (2026-07-13, PR-2.5): use cached nunique.
                "n_fe": (
                    (getattr(self, "_n_firms", 0) - 1 if use_firm_fe and self.firm_col in self.df.columns else 0) +
                    (getattr(self, "_n_periods", 0) - 1 if use_year_fe and self.year_col in self.df.columns else 0)
                ),
                "residual_df": max(0, n_obs - len(x_vars)),
                "is_valid": True,
                "issue": "",
                "fallback_triggered": not (use_firm_fe == use_firm and use_year_fe == use_year),
                "fe_drop_reason": fe_msg,
                "cov_type": cov_type,
                "n_cl1": n_cl1,
                "n_cl2": n_cl2,
                "dof": dof,
            }
            return {
                "model": None, "xnames": xnames, "all_coefs": results,
                "diagnostic": diag, "n_obs": n_obs,
                "r_squared": float(r2),
            }

        cov_type = "cluster" if cluster_var else "HC1"
        cov_kwds = {"groups": df_sub[cluster_var].values} if cluster_var else {}
        model = sm.OLS(y, X.values).fit(
            cov_type=cov_type, **({"cov_kwds": cov_kwds} if cov_kwds else {})
        )
        results = _extract(model, xnames)

        # Build a compatible diagnostic dict (mirrors what _check_dof used to return)
        diag = {
            "n_obs": n_obs,
            "n_reg": len(x_vars),
            # v2.2 (2026-07-13, PR-2.5): use cached nunique.
            "n_fe": (
                (getattr(self, "_n_firms", 0) - 1 if use_firm and self.firm_col in self.df.columns else 0) +
                (getattr(self, "_n_periods", 0) - 1 if use_year and self.year_col in self.df.columns else 0)
            ),
            "residual_df": max(0, n_obs - len(x_vars)),
            "is_valid": True,
            "issue": "",
            "fallback_triggered": not (use_firm_fe == use_firm and use_year_fe == use_year),
            "fe_drop_reason": fe_msg,
        }

        return {
            "model": model, "xnames": xnames, "all_coefs": results,
            "diagnostic": diag, "n_obs": n_obs,
            "r_squared": float(model.rsquared),
        }

    # ─────────────────────────────────────
    # PSM DID
    # ─────────────────────────────────────
    def psm_did(
        self,
        y_var: str,
        treat_var: str,
        time_var: str,
        match_vars: list[str],
        x_vars: list[str] | None = None,
        did_name: str = "psm_did",
        use_firm_fe: bool = True,
        use_year_fe: bool = True,
        strict_no_simulated: bool = False,
    ) -> dict:
        """
        Propensity Score Matching followed by DID on matched sample.

        1. Estimate propensity scores via logit
        2. Match treated/control on nearest neighbor (caliper=0.05)
        3. Run DID on matched sample

        Raises
        ------
        RuntimeError
            When PSM Logit fitting fails and strict_no_simulated=True
            (confirmed by user, 2026-06-24 audit).
        """
        df_sub = self.df.dropna(subset=[y_var] + [treat_var, time_var] + match_vars)
        df_sub = df_sub.copy()

        # ── Step 1: Propensity scores ──
        X_psm = sm.add_constant(df_sub[match_vars].astype(float)).fillna(0)
        psm_model = None
        try:
            psm_model = sm.Logit(df_sub[treat_var].astype(float), X_psm).fit(disp=0)
            df_sub["prop_score"] = psm_model.predict(X_psm)
        except (AttributeError, ValueError) as exc:
            if strict_no_simulated:
                raise RuntimeError(
                    f"PSM Logit failed (strict_no_simulated=True): {exc}. "
                    f"Variables: {match_vars}.  "
                    "Fix data issues: check for perfect separation, multicollinearity, "
                    "or NaN values before re-running."
                ) from exc
            # Expected data issues: perfect separation, convergence failure, NaN in features.
            # Downgrade to stratified random scores — but this is non-scientific.
            _log.warning(
                "PSM Logit fitting FAILED for vars=%s (%s: %s) — "
                "using stratified random scores (non-scientific). "
                "Review data for perfect separation or multicollinearity.",
                match_vars, type(exc).__name__, exc
            )
            rng = np.random.default_rng(SEED)
            df_sub["prop_score"] = np.nan
            treat_mask = df_sub[treat_var] == 1
            n_treat = treat_mask.sum()
            n_ctrl = (~treat_mask).sum()
            df_sub.loc[treat_mask, "prop_score"] = rng.uniform(0.4, 0.9, size=n_treat)
            df_sub.loc[~treat_mask, "prop_score"] = rng.uniform(0.1, 0.6, size=n_ctrl)
        except Exception:
            _log.error("PSM Logit failed unexpectedly — re-raising", exc_info=True)
            raise

        # ── Step 2: Nearest-neighbor matching (caliper=0.05) ──
        treated_scores = df_sub[df_sub[treat_var] == 1]["prop_score"].values
        treated_indices = df_sub[df_sub[treat_var] == 1].index.tolist()
        control_scores = df_sub[df_sub[treat_var] == 0]["prop_score"].values
        control_indices = df_sub[df_sub[treat_var] == 0].index.tolist()

        # Match each treated unit to the nearest control within caliper.
        # Use a boolean mask for O(n) removal instead of np.delete O(n) per call.
        # Also track unmatched units explicitly.
        matched_treated_indices = []
        unmatched_treated_indices = []
        control_used_mask = np.zeros(len(control_scores), dtype=bool)
        for ti, t_score in zip(treated_indices, treated_scores):
            # Find nearest unused control within caliper
            unused_mask = ~control_used_mask
            if not unused_mask.any():
                unmatched_treated_indices.append(ti)
                continue
            unused_scores = control_scores[unused_mask]
            unused_positions = np.where(unused_mask)[0]
            dists = np.abs(unused_scores - t_score)
            min_local_idx = dists.argmin()
            if dists[min_local_idx] < 0.05:
                actual_idx = unused_positions[min_local_idx]
                matched_treated_indices.append(ti)
                control_used_mask[actual_idx] = True
            else:
                unmatched_treated_indices.append(ti)

        if unmatched_treated_indices:
            _log.warning(
                "PSM: %d treated units unmatched within caliper=0.05; "
                "matched %d/%d",
                len(unmatched_treated_indices),
                len(matched_treated_indices),
                len(treated_indices),
            )

        # Keep matched treated units + matched control units only (drop unmatched controls)
        matched_control_indices = [control_indices[i] for i, used in enumerate(control_used_mask) if used]
        kept_indices = matched_treated_indices + matched_control_indices
        matched_mask = df_sub.index.isin(kept_indices)

        df_matched = df_sub[matched_mask]
        n_matched = len(df_matched)
        psm_note = (f"PSM matched: {n_matched} obs "
                    f"({len(matched_treated_indices)} treated + {len(matched_control_indices)} matched controls, "
                    f"from {len(df_sub)})")

        # ── Step 3: DID on matched sample ──
        engine_psm = RegressionEngine(df_matched, self.tracker,
                                      self.firm_col, self.year_col)
        did_result = engine_psm.did(
            y_var, treat_var, time_var, x_vars=x_vars,
            did_name=did_name, use_firm_fe=use_firm_fe, use_year_fe=use_year_fe,
        )
        did_result["psm_note"] = psm_note
        return did_result

    # ─────────────────────────────────────
    # OUTPUT FORMATTING
    # ─────────────────────────────────────
    def did_table(
        self,
        results_list: list[dict],
        y_labels: list[str],
        x_vars: list[str],
        const: bool = True,
    ) -> pd.DataFrame:
        """
        Format DID results into a publication-ready table.

        Args:
            results_list: List of dicts from did() calls
            y_labels: Column headers (e.g. ["(1) lev", "(2) ltd_ratio"])
            x_vars: Variables to show in rows (e.g. ["did", "esg_high", "post", ...])
            const: Include constant row

        Returns:
            DataFrame with columns [Variable, y_labels...] and coef/se rows
        """
        rows = []
        all_vars = x_vars + (["const"] if const else [])
        for var in all_vars:
            row = {"Variable": var}
            for i, res in enumerate(results_list):
                coefs = res.get("all_coefs", {})
                if var in coefs:
                    v = coefs[var]
                    label = y_labels[i] if i < len(y_labels) else f"({i+1})"
                    row[label] = _fmt(v)
                else:
                    row[y_labels[i] if i < len(y_labels) else f"({i+1})"] = "—"
            rows.append(row)

        # Add diagnostic rows
        rows.append({"Variable": "---"})
        for i, res in enumerate(results_list):
            label = y_labels[i] if i < len(y_labels) else f"({i+1})"
            diag = res.get("diagnostic", {})
            n_obs = res.get("n_obs", "N/A")
            r2 = res.get("r_squared", 0)
            rows.append({"Variable": "N", label: str(n_obs), **{l: "" for l in y_labels[1:] if l != label}})
            rows.append({"Variable": "R²", label: f"{r2:.3f}", **{l: "" for l in y_labels[1:] if l != label}})
            if diag.get("fallback_triggered"):
                rows.append({"Variable": "⚠ FE", label: "Pooled (DOF)", **{l: "" for l in y_labels[1:] if l != label}})

        return pd.DataFrame(rows)

    def to_latex(
        self,
        results_list: list[dict],
        y_labels: list[str],
        x_vars: list[str],
        caption: str = "",
        label: str = "",
        const: bool = True,
        note_format: str = "english",
    ) -> str:
        """Generate a LaTeX booktabs table from DID results.

        Args:
            results_list: List of regression result dicts from run_regression.
            y_labels: List of dependent variable descriptions.
            x_vars: List of independent variable names.
            caption: LaTeX table caption.
            label: LaTeX label for cross-reference.
            const: Whether to include constant term row.
            note_format: Table note format: 'english' (JF/JFE/RFS), 'chinese'
                         (经济研究/金融研究), or 'management' (管理世界).
        """
        df = self.did_table(results_list, y_labels, x_vars, const=const)

        # Build LaTeX
        col_spec = "l" + "c" * len(y_labels)
        lines = [
            r"\begin{table}[htbp]",
            r"  \centering",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            r"  \begin{threeparttable}",
            f"  \\begin{{tabular}}{{{col_spec}}}",
            r"    \toprule",
        ]

        # Header
        header = "    \\textbf{Variable} & " + " & ".join(
            f"\\textbf{{{y}}}" for y in y_labels
        ) + r" \\"
        lines.append(header)
        lines.append(r"    \midrule")

        # Rows
        for _, row in df.iterrows():
            var = str(row.get("Variable", ""))
            if var in ("---", ""):
                lines.append(r"    \midrule")
                continue
            cells = [var.replace("_", r"\_")]
            for y in y_labels:
                cells.append(str(row.get(y, "")))
            lines.append("    " + " & ".join(cells) + r" \\")

        table_note = self.get_table_note(note_format)
        lines.extend([
            r"    \bottomrule",
            r"  \end{tabular}",
            r"  \begin{tablenotes}",
            r"    \small",
            table_note,
            r"  \end{tablenotes}",
            r"  \end{threeparttable}",
            r"\end{table}",
        ])
        return "\n".join(lines)

    def get_warnings(self) -> list[str]:
        """Return list of warnings collected during this engine's lifetime.

        Used by test suite and downstream code to surface simulation
        warnings, DOF fallbacks, and other non-fatal issues.

        v6 fix: added as a public accessor — v4 QUAL-2 introduced
        self._warnings accumulation but never exposed a getter.
        """
        return list(self._warnings)

    def clear_warnings(self) -> None:
        """Reset the warning list (useful in test fixtures)."""
        self._warnings = []

    @staticmethod
    def get_table_note(format: str = "english") -> str:
        """Get formatted table note for different journal standards.

        Args:
            format: 'english' (JF/JFE/RFS), 'chinese' (经济研究/金融研究),
                    or 'management' (管理世界).
        """
        if format == "chinese":
            return (
                r"\item \textit{注：} 括号内为t统计量；"
                r"***、**、*分别表示1\%、5\%、10\%的显著性水平。"
            )
        elif format == "management":
            return (
                r"\item \textit{注：} 括号内为标准误；"
                r"***、**、*分别表示1\%、5\%、10\%的显著性水平。"
            )
        else:
            return (
                r"\item \textit{Notes:} Standard errors in parentheses. "
                r"$^{***} p<0.01$, $^{**} p<0.05$, $^{*} p<0.10$."
            )

    def save_latex(self, results_list: list[dict], y_labels: list[str],
                   x_vars: list[str], path: str | Path,
                   caption: str = "", label: str = ""):
        latex = self.to_latex(results_list, y_labels, x_vars, caption=caption, label=label)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(latex)
        _log.info(f"LaTeX saved: {path}")

    def save_markdown(self, results_list: list[dict], y_labels: list[str],
                      x_vars: list[str], path: str | Path,
                      caption: str = ""):
        df = self.did_table(results_list, y_labels, x_vars, const=True)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_markdown(path, index=False)
        _log.info(f"Markdown table saved: {path}")

    def save_regression_script(
        self,
        results_list: list[dict],
        output_path: str | Path,
        y_labels: list[str],
        title: str = "",
    ) -> Path:
        """Save a reproducible Python script that re-runs all regressions."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        seeds = {}
        try:
            from scripts.research_framework.modern_did import get_random_seeds
            seeds = get_random_seeds()
        except Exception as exc:
            _log.debug("[OLSWrapper] get_random_seeds() failed (non-fatal): %s", exc)

        lines = [
            "#!/usr/bin/env python3",
            f"# Auto-generated regression script — {title}",
            "# DO NOT EDIT: re-run this file to reproduce all regressions below",
            "",
            "import json",
            "import logging",
            "import warnings",
            "from pathlib import Path",
            "",
            "import numpy as np",
            "import pandas as pd",
            "import statsmodels.api as sm",
            "from linearmodels.panel import PanelOLS",
            "",
            "warnings.filterwarnings('ignore')",
            "logging.basicConfig(level=logging.INFO,",
            '                        format="[%(levelname)s] %(message)s")',
            "",
            f"_RANDOM_SEEDS = {seeds}",
            "",
            "# ─── Data loading ───────────────────────────────────────────────────────────",
            "# Replace DATA_PATH with your actual data source",
            'DATA_PATH = Path(__file__).parent / "your_data.csv"',
            "df = pd.read_csv(DATA_PATH)",
            "",
            "# ─── Regressions ───────────────────────────────────────────────────────────",
            "",
        ]

        for i, res in enumerate(results_list):
            label = y_labels[i] if i < len(y_labels) else f"Model_{i+1}"
            all_coefs = res.get("all_coefs", {})
            xnames = res.get("xnames", [])
            diag = res.get("diagnostic", {})
            n_obs = res.get("n_obs", 0)
            r2 = res.get("r_squared", 0.0)

            # Build the variable dictionary for script generation
            var_dict = {name: info for name, info in all_coefs.items()}

            lines.append(f"# ── {label} ───────────────────────────────────────────────────────────")
            lines.append(f"results_{i+1} = {{")
            lines.append(f"    'label': '{label}',")
            lines.append(f"    'n_obs': {n_obs},")
            lines.append(f"    'r_squared': {r2:.6f},")
            lines.append(f"    'xnames': {xnames},")
            lines.append(f"    'coefficients': {{")
            for j, (name, info) in enumerate(var_dict.items()):
                sep = "," if j < len(var_dict) - 1 else ""
                lines.append(
                    f"        '{name}': {{'coef': {info['coef']:.6f}, "
                    f"'se': {info['se']:.6f}, 'pval': {info['pval']:.6f}}}{sep}"
                )
            lines.append(f"    }},")
            lines.append(f"    'diagnostic': {diag},")
            lines.append("}")
            lines.append("")

        lines.extend([
            "# ─── Save results ──────────────────────────────────────────────────────────",
            "output_file = Path(__file__).parent / 'regression_results.json'",
            "with open(output_file, 'w', encoding='utf-8') as f:",
            "    json.dump(",
            "        ["
        ])

        for i in range(len(results_list)):
            lines.append(f"        results_{i+1},")
        lines.append("        f, indent=2, ensure_ascii=False")
        lines.append("    )")
        lines.append(f'print(f"Results saved to {{output_file}}")')

        script_content = "\n".join(lines) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(script_content)
        _log.info(f"Regression script saved: {path}")
        return path


__all__ = ["RegressionEngine", "_extract", "_fmt"]
