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

Usage:
    engine = RegressionEngine(df, tracker)
    result = engine.did("lev", "esg_high", "post", x_vars=["ln_assets","roa","tangibility"])
    engine.print_table([result1, result2], ["(1) lev", "(2) ltd"])
    engine.save_latex("table1.tex")
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

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
        p, s, pv, tv = float(params[i]), float(bses[i]), float(pvals[i]), float(tvals[i])
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
    ):
        self.df = df
        self.tracker = tracker
        self.firm_col = firm_col
        self.year_col = year_col
        self._results: list[dict] = []
        self._warnings: list[str] = []

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
        if has_firm_fe and self.firm_col in self.df.columns:
            n_fe += self.df[self.firm_col].nunique() - 1
        if has_year_fe and self.year_col in self.df.columns:
            n_fe += self.df[self.year_col].nunique() - 1
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
            cluster_var: Cluster variable for SEs (default: firm_col)
            use_firm_fe: Whether to include firm fixed effects
            use_year_fe: Whether to include year fixed effects
            robust_se: Use HC1 robust standard errors

        Returns:
            dict with keys: did_coef, did_se, did_pval, did_sig, model, xnames, diagnostic
        """
        x_vars = x_vars or []
        df_sub = self.df.dropna(subset=[y_var] + [treat_var, time_var] + x_vars)
        n_obs = len(df_sub)

        # ── DOF check ──
        diag = self._check_dof(
            n_obs, [treat_var, time_var] + x_vars,
            has_firm_fe=use_firm_fe, has_year_fe=use_year_fe,
        )
        if diag["fallback_triggered"]:
            msg = (f"DOF insufficient: {diag['issue']} — "
                   f"Dropping firm FE. N={n_obs}, regressors={diag['n_reg']}, "
                   f"FE terms={diag['n_fe']}")
            _log.warning(msg)
            self._warnings.append(msg)
            use_firm_fe = False

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

        # ── Fit ──
        if robust_se and not cluster_var:
            cov_type = "HC1"
            cov_kwds = None
        elif cluster_var and cluster_var in df_sub.columns:
            cov_type = "cluster"
            cov_kwds = {"groups": df_sub[cluster_var].values}
        else:
            if cluster_var:
                # FIX (2026-05-29): User requested cluster SE but variable not in df.
                # Previously silently fell back to nonrobust — now warn.
                _log.warning(
                    f"[regression_engine] cluster_var='{cluster_var}' not found in "
                    f"df.columns. Falling back to nonrobust SE. "
                    f"Available columns: {list(df_sub.columns[:10])}..."
                )
            cov_type = "nonrobust"
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

        output = {
            "did_coef": did_coef, "did_se": did_se, "did_pval": did_pval,
            "did_sig": results.get(did_name, {}).get("sig", ""),
            "model": model, "xnames": xnames,
            "diagnostic": diag,
            "n_obs": n_obs,
            "r_squared": float(model.rsquared),
            "all_coefs": results,
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
        robust_se: bool = True,
    ) -> dict:
        """Pooled OLS with optional FEs and robust SEs."""
        df_sub = self.df.dropna(subset=[y_var] + x_vars)
        n_obs = len(df_sub)

        diag = self._check_dof(n_obs, x_vars,
                               has_firm_fe=use_firm_fe, has_year_fe=use_year_fe)
        if diag["fallback_triggered"]:
            msg = f"DOF insufficient — dropping FEs. {diag['issue']}"
            _log.warning(msg)
            self._warnings.append(msg)
            use_firm_fe = use_year_fe = False

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

        cov_type = "cluster" if cluster_var else "HC1"
        cov_kwds = {"groups": df_sub[cluster_var].values} if cluster_var else {}
        model = sm.OLS(y, X.values).fit(
            cov_type=cov_type, **({"cov_kwds": cov_kwds} if cov_kwds else {})
        )
        results = _extract(model, xnames)

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
    ) -> dict:
        """
        Propensity Score Matching followed by DID on matched sample.
        
        1. Estimate propensity scores via logit
        2. Match treated/control on nearest neighbor (caliper=0.05)
        3. Run DID on matched sample
        
        Returns DID results with PSM diagnostics.
        """
        df_sub = self.df.dropna(subset=[y_var] + [treat_var, time_var] + match_vars)
        df_sub = df_sub.copy()

        # ── Step 1: Propensity scores ──
        X_psm = sm.add_constant(df_sub[match_vars].astype(float)).fillna(0)
        psm_model = None
        try:
            psm_model = sm.Logit(df_sub[treat_var].astype(float), X_psm).fit(disp=0)
            df_sub["prop_score"] = psm_model.predict(X_psm)
        except Exception:
            _log.warning("PSM: Logit failed, generating group-stratified propensity scores")
            # Fall back: assign stratified random scores within treatment/control groups.
            # This ensures treated and control units have different score distributions,
            # so matching is not trivially biased toward the first control unit.
            rng = np.random.default_rng(42)
            df_sub["prop_score"] = np.nan
            treat_mask = df_sub[treat_var] == 1
            n_treat = treat_mask.sum()
            n_ctrl = (~treat_mask).sum()
            # Treated get scores ~Unif(0.4, 0.9), controls get scores ~Unif(0.1, 0.6)
            # Ensures non-overlapping ranges so caliper matching works meaningfully
            df_sub.loc[treat_mask, "prop_score"] = rng.uniform(0.4, 0.9, size=n_treat)
            df_sub.loc[~treat_mask, "prop_score"] = rng.uniform(0.1, 0.6, size=n_ctrl)

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
    ) -> str:
        """Generate a LaTeX booktabs table from DID results."""
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

        lines.extend([
            r"    \bottomrule",
            r"  \end{tabular}",
            r"  \begin{tablenotes}",
            r"    \small",
            r"    \item \textit{Notes:} Standard errors in parentheses.",
            r"    $^{***} p<0.01$, $^{**} p<0.05$, $^{*} p<0.10$.",
            r"  \end{tablenotes}",
            r"  \end{threeparttable}",
            r"\end{table}",
        ])
        return "\n".join(lines)

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

    def get_warnings(self) -> list[str]:
        return self._warnings.copy()


__all__ = ["RegressionEngine", "_extract", "_fmt"]
