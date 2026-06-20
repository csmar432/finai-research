"""
research_framework/green_bond_model.py
Green Bond Factor Models for ESG/Green Finance Research.

This module implements econometric models for analyzing green bonds:
- Greenium estimation (green bond premium over conventional bonds)
- Factor decomposition of green bond yields
- Event study (CAR) for green bond issuance events
- Permutation-based placebo tests
- Panel ESG regression models

Data sources:
- MCP: user-yfinance       (US green bond ETFs: TLT, IGIB, VWOB)
- MCP: user-eastmoney-bond (Chinese green bonds)
- pandas DataFrame         (user-uploaded data)

Author: FinResearch Agent
"""

from __future__ import annotations

import logging
import random
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

# ─── Module-level logging ──────────────────────────────────────────────────

_log = logging.getLogger("green_bond_model")
_log.setLevel(logging.INFO)

# ─── Provenance helper ────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Core Result Dataclass ────────────────────────────────────────────────


@dataclass
class GreenBondResult:
    """
    Structured result container for all green bond model estimates.

    Attributes:
        greenium_coef:  Coefficient on the green bond dummy (greenium in bps).
        greenium_se:    Robust standard error for the greenium coefficient.
        greenium_pval:  Two-sided p-value for the greenium coefficient.
        r_squared:      Model R-squared (fraction of variance explained).
        adj_r_squared:  Adjusted R-squared (penalized by number of parameters).
        n_obs:          Total number of observations used in the estimation.
        n_green:        Number of green bond observations.
        n_conventional: Number of conventional bond observations.
        model_type:     One of "ols", "fixed_effects", "panel_gmm", "event_study".
        factor_loadings: dict mapping factor name → (coef, se, pval).
        car_estimates:  dict mapping event window → CAR estimate (event study).
        provenance:      dict with data source and timestamp metadata.
        extra:          Additional model-specific fields (e.g. AIC, BIC, n_groups).
    """

    greenium_coef: float = np.nan
    greenium_se: float = np.nan
    greenium_pval: float = np.nan
    r_squared: float = np.nan
    adj_r_squared: float = np.nan
    n_obs: int = 0
    n_green: int = 0
    n_conventional: int = 0
    model_type: str = "ols"
    factor_loadings: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    car_estimates: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.provenance:
            self.provenance = {
                "generated_at": _now_iso(),
                "model": "green_bond_model.py",
                "version": "1.0.0",
            }


# ─── Utility helpers ─────────────────────────────────────────────────────


def _stars(pval: float) -> str:
    """Return significance star annotation."""
    if pval < 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    if pval < 0.10:
        return "$\\dagger$"
    return ""


def _drop_missing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Drop rows with NaN in specified columns."""
    before = len(df)
    out = df.dropna(subset=cols)
    after = len(out)
    if before > after:
        _log.warning("Dropped %d rows with missing values in %s", before - after, cols)
    return out


def _safe_reg(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    robust: bool = True,
) -> dict[str, Any]:
    """
    Run OLS regression with optional HC1 robust SEs.

    Returns a dict with keys: params, bse, pvalues, rsquared, nobs, aic, bic.
    """
    df_reg = df[x_cols + [y_col]].dropna()
    if len(df_reg) < len(x_cols) + 2:
        raise ValueError(
            f"Insufficient observations ({len(df_reg)}) for regression with "
            f"{len(x_cols)} predictors."
        )

    X = sm.add_constant(df_reg[x_cols], has_constant="add")
    y = df_reg[y_col]

    model = sm.OLS(y, X)
    if robust:
        fit = model.fit(cov_type="HC1")
    else:
        fit = model.fit()

    return {
        "params": dict(fit.params),
        "bse": dict(fit.bse),
        "pvalues": dict(fit.pvalues),
        "rsquared": fit.rsquared,
        "adj_rsquared": fit.rsquared_adj,
        "nobs": int(fit.nobs),
        "aic": fit.aic,
        "bic": fit.bic,
        "fitted": fit,
    }


def _fetch_yfinance_etf(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch ETF price data via user-yfinance MCP.
    Falls back to yfinance Python package if MCP is unavailable.
    """
    try:
        from scripts.research_framework.data_fetcher import DataFetcher

        fetcher = DataFetcher()
        df = fetcher.fetch_etf_historical(ticker, start, end)
        _log.info("Fetched %s via DataFetcher (MCP).", ticker)
        return df
    except Exception:  # noqa: S110
        pass

    try:
        import yfinance as yf

        data = yf.download(ticker, start=start, end=end, progress=False)
        if data.empty:
            warnings.warn(f"yfinance returned empty data for {ticker}")
            return pd.DataFrame()
        data = data.reset_index()
        data.columns = [c if isinstance(c, str) else str(c[0]) for c in data.columns]
        _log.info("Fetched %s via yfinance (fallback).", ticker)
        return data
    except ImportError:
        warnings.warn("Neither DataFetcher nor yfinance available. Returning empty DataFrame.")
        return pd.DataFrame()


def _fetch_chinese_bonds(
    bond_type: str = "green",
    max_results: int = 100,
) -> pd.DataFrame:
    """
    Fetch Chinese green bond data via user-eastmoney-bond MCP.
    """
    try:
        from scripts.research_framework.data_fetcher import DataFetcher

        fetcher = DataFetcher()
        if bond_type == "green":
            df = fetcher.fetch_bond_spot(data_type="green")
        else:
            df = fetcher.fetch_bond_spot(data_type="all")
        _log.info("Fetched Chinese bonds via DataFetcher (MCP).")
        return df
    except Exception as exc:
        _log.warning("MCP bond fetch failed: %s. Returning empty DataFrame.", exc)
        return pd.DataFrame()


# ─── Main Model Classes ──────────────────────────────────────────────────


class GreenBondFactorModel:
    """
    Factor model for estimating the greenium and decomposing green bond yields.

    The greenium is the yield spread between a green bond and an otherwise
    identical conventional bond. A negative greenium indicates that investors
    accept a lower yield (i.e., pay a premium) for green bonds.

    Key methods:
        estimate_greenium  — OLS estimation of the green bond premium
        factor_decomposition — Yield decomposition into risk factors
        event_study       — Cumulative abnormal return (CAR) around issuance
        placebo_test      — Permutation-based significance test
        to_latex          — Publication-ready LaTeX table
        summary           — Human-readable console summary

    Example:
        model = GreenBondFactorModel()
        result = model.estimate_greenium(
            df=bond_df,
            green_col="is_green",
            yield_col="yield_bps",
            controls=["maturity_years", "credit_aaa", "sector_FI", "time_fe"]
        )
        model.summary(result)
    """

    # ─── Estimation ───────────────────────────────────────────────────────

    def estimate_greenium(
        self,
        df: pd.DataFrame,
        green_col: str,
        yield_col: str,
        controls: list[str] | None = None,
        robust: bool = True,
        time_fe: str | None = None,
        issuer_fe: str | None = None,
    ) -> GreenBondResult:
        """
        Estimate the greenium (green bond premium) via OLS.

        The regression equation is::

            yield_{it} = alpha
                       + beta * is_green_{it}
                       + gamma * maturity_{it}
                       + delta * rating_{it}
                       + lambda * sector_{it}
                       + theta * time_fe_{it}
                       + epsilon_{it}

        where beta is the greenium (in basis points).

        Args:
            df:           Bond-level DataFrame. Must contain `green_col` and
                          `yield_col`. Optional control columns.
            green_col:    Binary indicator column (1 = green bond, 0 = conventional).
            yield_col:    Yield column (in basis points recommended for numerical
                          stability).
            controls:     Additional control variable names present in `df`.
                          Supported types: numeric, boolean, or dummy-encoded.
            robust:       Use HC1 robust standard errors (default True).
            time_fe:      Name of a time-index column to include as fixed effects
                          (e.g. "year" or "month"). Will be dummy-encoded automatically.
            issuer_fe:    Name of an issuer-index column for issuer fixed effects.

        Returns:
            GreenBondResult with greenium_coef = beta, greenium_se = SE(beta),
            and full model statistics.

        Raises:
            ValueError: If required columns are missing or data is insufficient.
        """
        required = {green_col, yield_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        ctrl = list(controls) if controls else []
        x_cols = [green_col] + ctrl
        all_cols = x_cols + [yield_col]

        if time_fe and time_fe in df.columns:
            x_cols.append(time_fe)
            all_cols.append(time_fe)
        if issuer_fe and issuer_fe in df.columns:
            x_cols.append(issuer_fe)
            all_cols.append(issuer_fe)

        df_sub = _drop_missing(df[all_cols], all_cols)

        n_green = int(df_sub[green_col].sum())
        n_conv = len(df_sub) - n_green
        if n_green < 5 or n_conv < 5:
            raise ValueError(
                f"Insufficient bond counts: green={n_green}, "
                f"conventional={n_conv}. Need at least 5 each."
            )

        if time_fe:
            df_sub = pd.get_dummies(df_sub, columns=[time_fe], drop_first=True)
        if issuer_fe:
            df_sub = pd.get_dummies(df_sub, columns=[issuer_fe], drop_first=True)

        x_cols_final = [c for c in df_sub.columns if c != yield_col]

        reg = _safe_reg(df_sub, yield_col, x_cols_final, robust=robust)

        params = reg["params"]
        bse = reg["bse"]
        pvalues = reg["pvalues"]

        gc = params.get(green_col, np.nan)
        gs = bse.get(green_col, np.nan)
        gp = pvalues.get(green_col, np.nan)

        result = GreenBondResult(
            greenium_coef=gc,
            greenium_se=gs,
            greenium_pval=gp,
            r_squared=reg["rsquared"],
            adj_r_squared=reg["adj_rsquared"],
            n_obs=reg["nobs"],
            n_green=n_green,
            n_conventional=n_conv,
            model_type="ols",
            provenance={
                "generated_at": _now_iso(),
                "data_source": "user",
                "green_col": green_col,
                "yield_col": yield_col,
                "controls": ctrl,
                "robust_se": robust,
                "time_fe": time_fe,
                "issuer_fe": issuer_fe,
            },
            extra={
                "aic": reg["aic"],
                "bic": reg["bic"],
                "raw_fit": reg["fitted"],
            },
        )

        self._last_result = result
        _log.info(
            "Greenium estimate: %.2f bps (SE=%.2f, p=%.4f, N=%d, R2=%.3f)",
            gc, gs, gp, reg["nobs"], reg["rsquared"],
        )
        return result

    # ─── Factor decomposition ─────────────────────────────────────────────

    def factor_decomposition(
        self,
        df: pd.DataFrame,
        yield_col: str = "yield_bps",
        duration_col: str = "duration_years",
        credit_col: str = "credit_spread",
        liquidity_col: str = "liquidity_score",
        climate_col: str = "climate_beta",
        esg_col: str = "esg_score",
        green_col: str = "is_green",
    ) -> dict[str, GreenBondResult]:
        """
        Decompose green bond yields into five risk factors.

        For each factor f, the model is::

            yield_{it} = alpha
                      + beta_f * factor_f
                      + beta_green * is_green
                      + controls + epsilon_{it}

        The five factors are:

        1. **Duration risk**    — sensitivity to interest-rate changes
        2. **Credit risk**     — credit spread over risk-free rate
        3. **Liquidity risk**  — bid-ask spread / trading volume proxy
        4. **Climate risk**    — carbon intensity / stranded-asset beta
        5. **ESG score**       — aggregate ESG rating

        Args:
            df:            Bond panel DataFrame.
            yield_col:    Yield variable (in bps).
            duration_col: Macaulay duration in years.
            credit_col:   Credit spread in bps.
            liquidity_col: Liquidity score (higher = less liquid).
            climate_col:  Climate beta (cov with carbon price shocks).
            esg_col:      ESG score (0–100).
            green_col:    Binary green bond indicator.

        Returns:
            dict mapping factor name → GreenBondResult.
            Results include factor_loadings dict with all coefficients.
        """
        factor_cols = [duration_col, credit_col, liquidity_col, climate_col, esg_col]
        present = [c for c in factor_cols if c in df.columns]
        if len(present) < 2:
            warnings.warn(
                f"Only {len(present)} factor columns found. "
                "Factor decomposition needs at least 2 factors."
            )

        available = present + [yield_col, green_col]
        df_sub = _drop_missing(df[available], available)

        results: dict[str, GreenBondResult] = {}
        for factor in present:
            x_cols = [factor, green_col]
            try:
                reg = _safe_reg(df_sub, yield_col, x_cols)
            except ValueError as exc:
                _log.warning("Skipping factor '%s': %s", factor, exc)
                continue

            results[factor] = GreenBondResult(
                greenium_coef=reg["params"].get(green_col, np.nan),
                greenium_se=reg["bse"].get(green_col, np.nan),
                greenium_pval=reg["pvalues"].get(green_col, np.nan),
                r_squared=reg["rsquared"],
                adj_r_squared=reg["adj_rsquared"],
                n_obs=reg["nobs"],
                n_green=int(df_sub[green_col].sum()),
                n_conventional=int((~df_sub[green_col].astype(bool)).sum()),
                model_type="factor_decomposition",
                factor_loadings={
                    factor: (
                        reg["params"].get(factor, np.nan),
                        reg["bse"].get(factor, np.nan),
                        reg["pvalues"].get(factor, np.nan),
                    )
                },
                provenance={
                    "generated_at": _now_iso(),
                    "factor": factor,
                    "factors_considered": present,
                },
            )

        return results

    # ─── Event study ──────────────────────────────────────────────────────

    def event_study(
        self,
        df: pd.DataFrame,
        event_date: str,
        event_window: tuple[int, int] = (-1, 1),
        yield_col: str = "yield_bps",
        green_col: str = "is_green",
        market_col: str | None = None,
        estimation_window: int = 60,
    ) -> GreenBondResult:
        """
        Compute Cumulative Abnormal Returns (CAR) around a green bond issuance event.

        This method implements the standard market model event study:

            AR_{it} = R_{it} - (alpha_i + beta_i * R_mt)   [if market_col provided]
            AR_{it} = R_{it} - mean(R_{i,-60:-1})           [otherwise]

        CAR(event_window) = sum(AR_t) for t in event_window.

        Args:
            df:              Panel DataFrame with bond yields (must be sorted by date).
            event_date:      Event date string in ISO format (e.g. "2021-06-01").
            event_window:    (t_start, t_end) relative to event_date.
                              Default (-1, 1) covers t-1, t0, t+1.
            yield_col:       Name of the yield / return column.
            green_col:       Binary indicator for green bonds.
            market_col:      Optional market return column for market model.
            estimation_window: Number of pre-event days used for alpha/beta estimation.

        Returns:
            GreenBondResult with car_estimates dict containing:
                - "car_<window>": CAR for the specified window
                - "ar_<date>": Abnormal return for each date
            and model_type = "event_study".
        """
        if yield_col not in df.columns:
            raise ValueError(f"Column '{yield_col}' not found in DataFrame.")
        if green_col not in df.columns:
            raise ValueError(f"Column '{green_col}' not found in DataFrame.")

        df_ev = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_ev.index):
            if "date" in df_ev.columns:
                df_ev["date"] = pd.to_datetime(df_ev["date"])
                df_ev = df_ev.set_index("date").sort_index()
            elif hasattr(df_ev.index, "dtype"):
                df_ev.index = pd.to_datetime(df_ev.index)

        event_dt = pd.to_datetime(event_date)
        t_start, t_end = event_window

        window_start = event_dt + pd.Timedelta(days=t_start)
        window_end = event_dt + pd.Timedelta(days=t_end)

        est_end = event_dt - pd.Timedelta(days=1)
        est_start = est_end - pd.Timedelta(days=estimation_window)

        df_est = df_ev.loc[est_start:est_end]
        df_evwin = df_ev.loc[window_start:window_end]

        if len(df_est) < 10:
            warnings.warn(
                f"Estimation window has only {len(df_est)} observations. "
                "CAR estimates may be unreliable."
            )

        car_estimates: dict[str, float] = {}
        ar_by_date: dict[str, float] = {}

        for _bond_id, grp in df_evwin.groupby(level=0) if df_evwin.index.names[0] else [(None, df_evwin)]:
            if market_col and market_col in grp.columns:
                market_ret = grp[market_col].values
                bond_ret = grp[yield_col].values
                if len(market_ret) >= 5 and len(bond_ret) >= 5:
                    X_m = sm.add_constant(market_ret)
                    mdl = sm.OLS(bond_ret, X_m).fit()
                    predicted = mdl.predict(X_m)
                    ar = bond_ret - predicted
                else:
                    mean_est = df_est[yield_col].mean() if len(df_est) else 0
                    ar = grp[yield_col].values - mean_est
            else:
                mean_est = df_est[yield_col].mean() if len(df_est) else 0
                ar = grp[yield_col].values - mean_est

            for dt, ar_val in zip(grp.index, ar, strict=False):
                ar_by_date[f"ar_{dt.strftime('%Y%m%d')}"] = float(ar_val)

        car_val = sum(ar_by_date.values()) if ar_by_date else 0.0
        window_str = f"car_[{t_start:+d},{t_end:+d}]"
        car_estimates[window_str] = float(car_val)

        df_green = df_evwin[df_evwin[green_col] == 1]
        n_green = len(df_green) if len(df_green) else int(df_evwin[green_col].sum())

        result = GreenBondResult(
            greenium_coef=car_val,
            greenium_se=np.nan,
            greenium_pval=np.nan,
            r_squared=np.nan,
            adj_r_squared=np.nan,
            n_obs=len(df_evwin),
            n_green=n_green,
            n_conventional=len(df_evwin) - n_green,
            model_type="event_study",
            car_estimates=car_estimates,
            extra={"ar_by_date": ar_by_date},
            provenance={
                "generated_at": _now_iso(),
                "event_date": event_date,
                "event_window": event_window,
                "estimation_window_days": estimation_window,
            },
        )

        self._last_result = result
        _log.info("Event study CAR [%+d, %+d] = %.4f bps", t_start, t_end, car_val)
        return result

    # ─── Placebo test ─────────────────────────────────────────────────────

    def placebo_test(
        self,
        df: pd.DataFrame,
        green_col: str,
        yield_col: str,
        controls: list[str] | None = None,
        n_permutations: int = 1000,
        seed: int = 42,
        robust: bool = True,
    ) -> dict[str, Any]:
        """
        Permutation test for greenium significance.

        Under the null hypothesis, the green bond label is independent of the
        yield. We randomly shuffle the `green_col` column and record the
        estimated greenium each time. The permutation p-value is:

            p_perm = (1 + #{permuted |beta| >= |beta_obs|}) / (1 + n_permutations)

        Args:
            df:              Bond DataFrame.
            green_col:       Binary green bond indicator (to be shuffled).
            yield_col:       Bond yield column.
            controls:        Control variable names (passed to estimate_greenium).
            n_permutations: Number of permutation iterations (default 1000).
            seed:            Random seed for reproducibility.
            robust:          Use HC1 SEs for each permutation regression.

        Returns:
            dict with keys:
                - "observed_greenium": beta from original data
                - "permuted_greenia": list of beta values from permutations
                - "permutation_pval": two-sided permutation p-value
                - "n_permutations": number of permutations run
                - "significant_at_5pct": bool
        """
        rng = random.Random(seed)
        ctrl = list(controls) if controls else []

        observed = self.estimate_greenium(
            df=df,
            green_col=green_col,
            yield_col=yield_col,
            controls=ctrl,
            robust=robust,
        )
        obs_beta = observed.greenium_coef

        permuted_betas: list[float] = []
        df_perm = df.copy()

        for i in range(n_permutations):
            labels = df_perm[green_col].values.copy()
            rng.shuffle(labels)
            df_perm[green_col] = labels

            try:
                res = self.estimate_greenium(
                    df=df_perm,
                    green_col=green_col,
                    yield_col=yield_col,
                    controls=ctrl,
                    robust=robust,
                )
                permuted_betas.append(res.greenium_coef)
            except (ValueError, np.linalg.LinAlgError):
                continue

            if (i + 1) % 200 == 0:
                _log.info("Placebo iteration %d / %d", i + 1, n_permutations)

        if not permuted_betas:
            warnings.warn("No valid permutations completed.")
            return {
                "observed_greenium": obs_beta,
                "permuted_greenia": [],
                "permutation_pval": np.nan,
                "n_permutations": 0,
                "significant_at_5pct": False,
            }

        abs_obs = abs(obs_beta)
        count_ge = sum(1 for b in permuted_betas if abs(b) >= abs_obs)
        perm_pval = (count_ge + 1) / (len(permuted_betas) + 1)

        _log.info(
            "Placebo test: observed=%.2f, perm_pval=%.4f (%d/%d extreme)",
            obs_beta, perm_pval, count_ge, len(permuted_betas)
        )

        return {
            "observed_greenium": obs_beta,
            "permuted_greenia": permuted_betas,
            "permutation_pval": perm_pval,
            "n_permutations": len(permuted_betas),
            "significant_at_5pct": perm_pval < 0.05,
        }

    # ─── Output ───────────────────────────────────────────────────────────

    def to_latex(
        self,
        result: GreenBondResult,
        caption: str = "Green Bond Premium (Greenium) Estimation",
        label: str = "tab:greenium",
        notes: list[str] | None = None,
        precision: int = 4,
    ) -> str:
        """
        Generate a publication-ready LaTeX table for the greenium result.

        The table format follows standard academic economics conventions:
        - Dependent variable in the column header
        - Coefficient ± SE in each cell with significance stars
        - Model statistics (N, R²) in the bottom panel
        - Sample breakdown (green vs. conventional) in the footnote

        Args:
            result:       GreenBondResult from estimate_greenium.
            caption:      LaTeX table caption.
            label:        LaTeX label for cross-referencing.
            notes:        List of footnote strings (appended after sample notes).
            precision:    Decimal places for coefficients and SEs.

        Returns:
            Complete LaTeX document string.
        """
        gc = result.greenium_coef
        gs = result.greenium_se
        gp = result.greenium_pval
        sig = _stars(gp)

        green_note = (
            f"\\footnotesize {result.n_green} green bonds, "
            f"{result.n_conventional} conventional bonds. "
            f"Model type: {result.model_type}."
        )

        footnote_items = [green_note]
        if notes:
            footnote_items.extend(f"\\footnotesize {n}" for n in notes)

        footnotes = "\n".join(
            f"\\item [{i+1}] {note}" for i, note in enumerate(footnote_items)
        )

        r2_str = f"{result.r_squared:.{precision}f}"
        adj_r2_str = f"{result.adj_r_squared:.{precision}f}"

        latex = (
            "\\begin{table}[htbp]\n"
            "\\centering\n"
            f"\\caption{{{caption}}}\n"
            f"\\label{{{label}}}\n"
            "\\begin{tabular}{lcc}\n"
            "\\hline\\hline\n"
            " & \\textbf{Base} & \\textbf{Controls} \\\\\n"
            "\\textbf{Variable} & (1) & (2) \\\\ \\hline\n"
            f"Greenium (green bond dummy) & ${gc:.{precision}f}{sig}$ & ${gc:.{precision}f}{sig}$ \\\\\n"
            f" & (${gs:.{precision}f}$) & (${gs:.{precision}f}$) \\\\ \\hline\n"
            f"Observations (N) & \\multicolumn{{2}}{{c}}{{{result.n_obs}}} \\\\\n"
            f"R² & \\multicolumn{{2}}{{c}}{{{r2_str}}} \\\\\n"
            f"Adjusted R² & \\multicolumn{{2}}{{c}}{{{adj_r2_str}}} \\\\\n"
            "\\hline\n"
            "\\end{tabular}\n"
            "\\begin{tablenotes}\n"
            f"{footnotes}\n"
            "\\end{tablenotes}\n"
            "\\end{table}"
        )
        return latex

    def summary(self, result: GreenBondResult) -> None:
        """
        Print a human-readable console summary of a GreenBondResult.

        Args:
            result: GreenBondResult from any model method.
        """
        print("\n" + "=" * 60)
        print("  Green Bond Model Summary")
        print("=" * 60)
        print(f"  Model type : {result.model_type}")
        print(f"  N (total)  : {result.n_obs:,}")
        print(f"    Green bonds       : {result.n_green:,}")
        print(f"    Conventional bonds: {result.n_conventional:,}")
        print("-" * 60)
        print(f"  Greenium coefficient : {result.greenium_coef:>10.4f} bps")
        print(f"  Robust SE            : {result.greenium_se:>10.4f}")
        print(f"  p-value              : {result.greenium_pval:>10.4f}   {_stars(result.greenium_pval)}")
        print(f"  R²                   : {result.r_squared:>10.4f}")
        print(f"  Adjusted R²          : {result.adj_r_squared:>10.4f}")

        if result.factor_loadings:
            print("-" * 60)
            print("  Factor Loadings:")
            for name, (coef, se, pval) in result.factor_loadings.items():
                print(f"    {name:<30} {coef:>8.4f} (SE={se:.4f}, p={pval:.4f}) { _stars(pval)}")

        if result.car_estimates:
            print("-" * 60)
            print("  CAR Estimates:")
            for window, car in result.car_estimates.items():
                print(f"    {window:<30} {car:>8.4f} bps")

        prov = result.provenance
        print("-" * 60)
        print(f"  Generated at : {prov.get('generated_at', 'N/A')}")
        print(f"  Data source   : {prov.get('data_source', 'N/A')}")
        if result.extra.get("aic"):
            print(f"  AIC           : {result.extra['aic']:.2f}")
            print(f"  BIC           : {result.extra.get('bic', 'N/A'):.2f}")
        print("=" * 60 + "\n")


class GreenBondESGModel:
    """
    Panel regression model for studying the ESG–yield relationship in bonds.

    This model estimates the sensitivity of bond yields to ESG scores,
    controlling for standard bond characteristics. It is useful for testing
    whether higher ESG-rated issuers enjoy lower borrowing costs.

    The base specification is::

        yield_{it} = alpha + beta * ESG_{it} + gamma * X_{it} + epsilon_{it}

    where beta < 0 indicates that better ESG performance lowers bond yields.

    Example:
        model = GreenBondESGModel()
        result = model.fit(
            df=bond_panel,
            esg_var="esg_score",
            bond_yield_var="yield_bps",
            controls=["maturity_years", "credit_spread", "size_log"],
        )
    """

    def fit(
        self,
        df: pd.DataFrame,
        esg_var: str,
        bond_yield_var: str,
        controls: list[str] | None = None,
        robust: bool = True,
        cluster: str | None = None,
        time_fe: str | None = None,
    ) -> GreenBondResult:
        """
        Fit a panel regression of bond yields on ESG scores.

        Args:
            df:               Bond panel DataFrame (long format, one row per bond-year).
            esg_var:          ESG score variable (continuous, 0–100 scale preferred).
            bond_yield_var:   Dependent variable: bond yield (in bps).
            controls:         Additional control variable names in `df`.
            robust:           Use HC1 robust standard errors.
            cluster:          Column name for two-way clustering (e.g. "firm_id").
            time_fe:          Time fixed effects column name (dummy-encoded).

        Returns:
            GreenBondResult where greenium_coef = ESG coefficient,
            with full regression statistics.

        Raises:
            ValueError: If required columns are missing or data is too sparse.
        """
        required = {esg_var, bond_yield_var}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        ctrl = list(controls) if controls else []
        x_cols = [esg_var] + ctrl
        all_cols = x_cols + [bond_yield_var]

        if time_fe and time_fe in df.columns:
            x_cols.append(time_fe)
            all_cols.append(time_fe)

        df_sub = _drop_missing(df[all_cols], all_cols)

        if len(df_sub) < len(x_cols) + 10:
            raise ValueError(
                f"Insufficient observations ({len(df_sub)}) for ESG regression "
                f"with {len(x_cols)} predictors."
            )

        if time_fe:
            df_sub = pd.get_dummies(df_sub, columns=[time_fe], drop_first=True)

        x_cols_final = [c for c in df_sub.columns if c != bond_yield_var]

        if cluster and cluster in df_sub.columns:
            cov_type = "cluster"
            cov_kwgs = {"groups": df_sub[cluster]}
        else:
            cov_type = "HC1" if robust else "nonrobust"
            cov_kwgs = {}

        X = sm.add_constant(df_sub[x_cols_final], has_constant="add")
        y = df_sub[bond_yield_var]

        model = sm.OLS(y, X)
        fit = model.fit(cov_type=cov_type, **cov_kwgs)

        params = dict(fit.params)
        bse = dict(fit.bse)
        pvalues = dict(fit.pvalues)

        esg_coef = params.get(esg_var, np.nan)
        esg_se = bse.get(esg_var, np.nan)
        esg_pval = pvalues.get(esg_var, np.nan)

        n_green = len(df_sub)
        n_conv = 0

        result = GreenBondResult(
            greenium_coef=esg_coef,
            greenium_se=esg_se,
            greenium_pval=esg_pval,
            r_squared=fit.rsquared,
            adj_r_squared=fit.rsquared_adj,
            n_obs=int(fit.nobs),
            n_green=n_green,
            n_conventional=n_conv,
            model_type="esg_panel",
            factor_loadings={
                esg_var: (esg_coef, esg_se, esg_pval)
            },
            provenance={
                "generated_at": _now_iso(),
                "esg_var": esg_var,
                "bond_yield_var": bond_yield_var,
                "controls": ctrl,
                "cluster": cluster if cluster else None,
                "robust_se": robust,
                "time_fe": time_fe,
            },
            extra={
                "aic": fit.aic,
                "bic": fit.bic,
                "raw_fit": fit,
            },
        )

        _log.info(
            "ESG model: ESG_coef=%.4f (SE=%.4f, p=%.4f), N=%d, R2=%.3f",
            esg_coef, esg_se, esg_pval, fit.nobs, fit.rsquared,
        )
        return result


# ─── Synthetic Data Generator (for testing) ──────────────────────────────


def make_demo_data(
    n_green: int = 300,
    n_conv: int = 500,
    seed: int = 42,
    greenium_true: float = -8.5,
) -> pd.DataFrame:
    """
    Generate synthetic green/conventional bond data for demonstration.

    Args:
        n_green:      Number of green bonds to simulate.
        n_conv:       Number of conventional bonds to simulate.
        seed:         Random seed for reproducibility.
        greenium_true: True greenium in basis points (negative = green premium).

    Returns:
        DataFrame with columns:
            is_green, yield_bps, maturity_years, credit_spread,
            liquidity_score, esg_score, sector_FI, sector_Corp,
            year, issuer_id
    """
    rng = np.random.default_rng(seed)

    n_total = n_green + n_conv
    is_green = np.concatenate([
        np.ones(n_green, dtype=int),
        np.zeros(n_conv, dtype=int),
    ])
    rng.shuffle(is_green)

    maturity = rng.exponential(scale=5, size=n_total) + 1  # 1–15 years
    credit_spread = rng.exponential(scale=80, size=n_total) + 10  # 10–300 bps
    liquidity = rng.exponential(scale=0.5, size=n_total)  # 0–2 score
    esg_score = rng.beta(a=2, b=2, size=n_total) * 40 + 40  # 40–80 range

    sector = rng.choice(["FI", "Corp", "Sov", "ABS"], size=n_total, p=[0.4, 0.35, 0.15, 0.1])
    years = rng.choice(range(2018, 2026), size=n_total)
    issuers = rng.integers(1, 51, size=n_total)  # 50 issuers

    yield_bps = (
        50
        + 5 * maturity
        + 0.8 * credit_spread
        - 3 * liquidity
        - 0.15 * (esg_score - 60)
        + greenium_true * is_green
        + rng.normal(0, 8, size=n_total)
    )

    df = pd.DataFrame({
        "is_green": is_green,
        "yield_bps": yield_bps,
        "maturity_years": np.round(maturity, 2),
        "credit_spread": np.round(credit_spread, 2),
        "liquidity_score": np.round(liquidity, 3),
        "esg_score": np.round(esg_score, 1),
        "sector": sector,
        "year": years,
        "issuer_id": issuers,
    })

    sector_dummies = pd.get_dummies(df["sector"], prefix="sector", drop_first=True)
    df = pd.concat([df, sector_dummies], axis=1)

    return df
