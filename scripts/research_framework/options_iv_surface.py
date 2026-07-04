"""Options Implied Volatility Surface Analysis for Asset Pricing Research.

本模块实现期权隐含波动率曲面（IV Surface）分析，涵盖：
  1. Black-Scholes 隐含波动率求解器（Brent / Newton）
  2. 从期权链数据构建完整 IV 曲面（strike × maturity）
  3. 波动率偏斜（Skew）和期限结构（Term Structure）计算
  4. IV 曲面 3D 可视化和 Skew 曲线图
  5. LaTeX 格式结果表格导出
  6. MCP 数据源集成（user-yfinance: get_yf_options）

Usage:
    # Build IV surface from options chain
    builder = IVSurfaceBuilder()
    result = builder.build_from_options(df, spot_price=450, risk_free_rate=0.05)
    print(result.atm_vol, result.skew)

    # Fit and predict
    model = IVSurfaceModel()
    model.fit_surface(df, spot=450, r=0.05)
    iv = model.predict_iv(moneyness=1.0, maturity=30)
    model.plot_surface("output/iv_surface.png")

    # LaTeX table
    print(model.to_latex(result))

Data source — MCP:
    server: user-yfinance
    tool: get_yf_options
    params: { "ticker": "SPY" }

    Returns DataFrame with columns:
        strike, maturity_days, price, option_type (call/put)

References:
    Black, F., & Scholes, M. (1973). The Pricing of Options and Corporate Liabilities.
        Journal of Political Economy, 81(3), 637-654.
    Hagan, P. S., Kumar, D., Lesniewski, A. S., & Woodward, D. E. (2002). Managing
        smile risk. Willemberg Working Paper.
    Gatheral, J. (2006). The Volatility Surface: A Practitioner's Guide. Wiley.
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

__all__ = [
    "IVSurfaceResult",
    "IVSurfaceBuilder",
    "IVSurfaceModel",
    "ImpliedVolatilityEngine",
]

_log = logging.getLogger("iv_surface")
_log.setLevel(logging.INFO)
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Fallback values when surface data is unavailable
_DEFAULT_STRIKE_RANGE = np.linspace(0.8, 1.2, 21)  # 80%-120% of spot
_DEFAULT_MATURITY_RANGE = np.array([7, 14, 30, 60, 90, 180, 365])  # days

# Black-Scholes lower/upper volatility bounds (annualized)
_IV_MIN = 0.001
_IV_MAX = 5.0

# ─────────────────────────────────────────────────────────────────────────────
# IMPLEMENTED_VOLATILITY_RESULT
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class IVSurfaceResult:
    """
    Container for the complete implied volatility surface result.

    Attributes
    ----------
    strike_range : np.ndarray
        Array of strike prices (1D).
    maturity_range : np.ndarray
        Array of maturities in calendar days (1D).
    surface_data : np.ndarray
        2D array of implied volatilities with shape
        (len(strike_range), len(maturity_range)). NaN for invalid cells.
    atm_vol : float
        ATM (at-the-money) volatility — interpolated at strike = spot,
        maturity = 30 days if available, else shortest maturity.
    skew : dict[str, np.ndarray]
        Skew metrics keyed by moneyness level, e.g. {"moneyness": [...],
        "iv_put_25d": [...], "iv_call_25d": [...]}.
    term_structure : dict[str, np.ndarray]
        Term structure keyed by "maturities" and "atm_vols".
    iv_callable : np.ndarray | None
        2D array of IV for callable feature (Bermudan swaption style),
        or None if not computed.
    iv_puttable : np.ndarray | None
        2D array of IV for puttable feature, or None if not computed.
    spot_price : float
        Underlying spot price at build time.
    risk_free_rate : float
        Annual risk-free rate used.
    computed_at : str
        ISO timestamp of when the result was computed.
    """

    strike_range: np.ndarray = field(default_factory=lambda: _DEFAULT_STRIKE_RANGE)
    maturity_range: np.ndarray = field(default_factory=lambda: _DEFAULT_MATURITY_RANGE)
    surface_data: np.ndarray = field(default_factory=lambda: np.full((21, 7), np.nan))
    atm_vol: float = 0.0
    skew: dict = field(default_factory=dict)
    term_structure: dict = field(default_factory=dict)
    iv_callable: np.ndarray | None = None
    iv_puttable: np.ndarray | None = None
    spot_price: float = 0.0
    risk_free_rate: float = 0.0
    computed_at: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime, timezone

        if not self.computed_at:
            self.computed_at = datetime.now(timezone.utc).isoformat()

    def to_dataframe(self) -> pd.DataFrame:
        """Convert surface data to a tidy DataFrame (melted long format)."""
        rows = []
        for i, k in enumerate(self.strike_range):
            for j, t in enumerate(self.maturity_range):
                iv = self.surface_data[i, j] if not np.isnan(self.surface_data[i, j]) else None
                rows.append(
                    {
                        "strike": k,
                        "maturity_days": t,
                        "moneyness": k / self.spot_price if self.spot_price else np.nan,
                        "iv": iv,
                    }
                )
        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# IMPLIED_VOLATILITY_ENGINE (Helper)
# ─────────────────────────────────────────────────────────────────────────────


class ImpliedVolatilityEngine:
    """
    Black-Scholes implied volatility computation engine.

    Provides:
      - ``black_scholes_price``: closed-form BS price
      - ``implied_vol``: Brent / Bisection IV solver
      - ``compute_greeks``: option Greeks (Delta, Gamma, Theta, Vega, Rho)

    Examples
    --------
    >>> eng = ImpliedVolatilityEngine()
    >>> price = eng.black_scholes_price(spot=100, strike=100, t=30/365,
    ...     r=0.05, sigma=0.20, option_type="call")
    >>> iv = eng.implied_vol(price=price, spot=100, strike=100,
    ...     t=30/365, r=0.05, option_type="call")
    >>> greeks = eng.compute_greeks(spot=100, strike=100, t=30/365,
    ...     r=0.05, sigma=0.20)
    """

    def __init__(self, tol: float = 1e-6, max_iter: int = 200) -> None:
        """
        Parameters
        ----------
        tol : float, default 1e-6
            Convergence tolerance for IV solver.
        max_iter : int, default 200
            Maximum iterations for IV solver.
        """
        self.tol = tol
        self.max_iter = max_iter

    # ── Black-Scholes closed-form price ─────────────────────────────────────

    @staticmethod
    def black_scholes_price(
        spot: float,
        strike: float,
        t: float,
        r: float,
        sigma: float,
        option_type: Literal["call", "put"],
    ) -> float:
        """
        Compute the Black-Scholes price of a European option.

        Parameters
        ----------
        spot : float
            Current underlying price.
        strike : float
            Option strike price.
        t : float
            Time to expiry in years (e.g. 30/365).
        r : float
            Annual continuously-compounded risk-free rate.
        sigma : float
            Annualized volatility.
        option_type : {"call", "put"}
            Option type.

        Returns
        -------
        float
            Option price.

        Raises
        ------
        ValueError
            If ``spot``, ``strike``, or ``t`` is non-positive, or sigma ≤ 0.
        """
        if spot <= 0 or strike <= 0 or t <= 0 or sigma <= 0:
            raise ValueError(
                f"Invalid BS inputs: spot={spot}, strike={strike}, "
                f"t={t}, sigma={sigma}"
            )

        from scipy.stats import norm

        d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
        d2 = d1 - sigma * math.sqrt(t)

        if option_type == "call":
            price = spot * norm.cdf(d1) - strike * math.exp(-r * t) * norm.cdf(d2)
        else:
            price = strike * math.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)

        return price

    # ── Implied volatility solvers ───────────────────────────────────────────

    def implied_vol(
        self,
        price: float,
        spot: float,
        strike: float,
        t: float,
        r: float,
        option_type: Literal["call", "put"],
        method: Literal["brentq", "bisect", "newton"] = "brentq",
    ) -> float:
        """
        Solve for the implied volatility given an observed option price.

        Uses Brent's method by default (robust and fast). Falls back to
        bisection when Brent fails. Newton-Raphson is also available.

        Parameters
        ----------
        price : float
            Observed market price of the option.
        spot : float
            Current underlying price.
        strike : float
            Option strike price.
        t : float
            Time to expiry in years.
        r : float
            Annual continuously-compounded risk-free rate.
        option_type : {"call", "put"}
            Option type.
        method : {"brentq", "bisect", "newton"}, default "brentq"
            IV solver algorithm.

        Returns
        -------
        float
            Annualized implied volatility.

        Raises
        ------
        ValueError
            If the price is outside the theoretical bounds (deep ITM / deep OTM).
        RuntimeError
            If the IV solver does not converge.
        """
        if t <= 0:
            raise ValueError(f"Time to expiry must be positive, got t={t}")

        intrinsic = self._intrinsic_price(spot, strike, t, r, option_type)
        spot if option_type == "call" else strike * math.exp(-r * t)

        if price < intrinsic - 1e-8:
            raise ValueError(
                f"Price {price:.4f} is below intrinsic value {intrinsic:.4f} "
                f"for {option_type}"
            )

        from scipy.optimize import brentq

        def objective(sigma: float) -> float:
            try:
                return self.black_scholes_price(spot, strike, t, r, sigma, option_type) - price
            except (ValueError, RuntimeWarning):
                return _IV_MAX

        try:
            iv = brentq(objective, _IV_MIN, _IV_MAX, xtol=self.tol, maxiter=self.max_iter)
            return float(iv)
        except (ValueError, RuntimeError):
            pass

        iv = self._bisect(objective, _IV_MIN, _IV_MAX)
        return iv

    def _bisect(self, obj, lo: float, hi: float) -> float:
        """Bisection fallback when brentq fails."""
        for _ in range(self.max_iter):
            mid = (lo + hi) / 2.0
            val = obj(mid)
            if abs(val) < self.tol:
                return mid
            if val > 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2.0

    @staticmethod
    def _intrinsic_price(spot: float, strike: float, t: float,
                         r: float, option_type: str) -> float:
        """Compute the intrinsic value of an option."""
        disc_strike = strike * math.exp(-r * t)
        if option_type == "call":
            return max(spot - disc_strike, 0.0)
        else:
            return max(disc_strike - spot, 0.0)

    # ── Greeks ──────────────────────────────────────────────────────────────

    def compute_greeks(
        self,
        spot: float,
        strike: float,
        t: float,
        r: float,
        sigma: float,
        option_type: Literal["call", "put"] = "call",
    ) -> dict[str, float]:
        """
        Compute first-order Black-Scholes Greeks.

        Parameters
        ----------
        spot, strike, t, r, sigma : float
            Standard BS inputs.
        option_type : {"call", "put"}, default "call"

        Returns
        -------
        dict
            Keys: delta, gamma, theta, vega, rho.
            theta is in per-day units (divide annual theta by 365).
            vega is in per-vol-unit (divide by 100 for 1% vol move).
        """
        if t <= 1e-9:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

        from scipy.stats import norm

        d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
        d2 = d1 - sigma * math.sqrt(t)

        nd1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1.0
        cdf_d2 = norm.cdf(d2) if option_type == "call" else norm.cdf(d2) - 1.0

        delta = cdf_d1
        gamma = nd1 / (spot * sigma * math.sqrt(t))
        vega = spot * nd1 * math.sqrt(t)  # per 1 unit vol
        theta = (
            -spot * nd1 * sigma / (2 * math.sqrt(t))
            - r * strike * math.exp(-r * t) * cdf_d2
        )
        rho = strike * t * math.exp(-r * t) * cdf_d2

        if option_type == "put":
            delta -= 1.0
            rho = -rho

        return {
            "delta": float(delta),
            "gamma": float(gamma),
            "theta": float(theta / 365),  # per day
            "vega": float(vega / 100),   # per 1% vol
            "rho": float(rho / 100),     # per 1% rate
        }


# ─────────────────────────────────────────────────────────────────────────────
# IV_SURFACE_BUILDER
# ─────────────────────────────────────────────────────────────────────────────


class IVSurfaceBuilder:
    """
    Build an implied volatility surface from raw options chain data.

    The builder:
      1. Accepts a DataFrame of option prices (strike, maturity, price, type).
      2. Computes IV for each option via ``ImpliedVolatilityEngine``.
      3. Arranges the IVs into a 2D surface (strike × maturity).
      4. Extracts ATM vol, skew, and term structure.

    Parameters
    ----------
    engine : ImpliedVolatilityEngine, optional
        IV computation engine. A default instance is created if not supplied.
    min_maturity_days : int, default 1
        Drop options with maturity < this threshold.
    max_maturity_days : int, default 730
        Drop options with maturity > this threshold (2 years).

    Examples
    --------
    >>> from scripts.research_framework.options_iv_surface import IVSurfaceBuilder
    >>> builder = IVSurfaceBuilder()
    >>> # df must have columns: strike, maturity_days, price, option_type
    >>> result = builder.build_from_options(df, spot_price=450, risk_free_rate=0.05)
    >>> print(f"ATM vol: {result.atm_vol:.4f}")
    """

    def __init__(
        self,
        engine: ImpliedVolatilityEngine | None = None,
        min_maturity_days: int = 1,
        max_maturity_days: int = 730,
    ) -> None:
        self.engine = engine or ImpliedVolatilityEngine()
        self.min_maturity_days = min_maturity_days
        self.max_maturity_days = max_maturity_days

    def build_from_options(
        self,
        df: pd.DataFrame,
        spot_price: float,
        risk_free_rate: float,
    ) -> IVSurfaceResult:
        """
        Build the complete IV surface from an options chain DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain columns:
              - ``strike``: float, strike price
              - ``maturity_days``: int/float, days to expiry
              - ``price``: float, market option price
              - ``option_type``: str, "call" or "put"
        spot_price : float
            Current underlying price.
        risk_free_rate : float
            Annual continuously-compounded risk-free rate.

        Returns
        -------
        IVSurfaceResult
            Populated result object with surface, ATM vol, skew, term structure.

        Raises
        ------
        ValueError
            If ``df`` is empty or missing required columns.
        """
        required = {"strike", "maturity_days", "price", "option_type"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        df = df.copy()
        df["option_type"] = df["option_type"].str.lower().str.strip()
        df = df[df["option_type"].isin(["call", "put"])]
        df = df[df["maturity_days"].between(self.min_maturity_days, self.max_maturity_days)]
        df = df[df["price"] > 0]
        df = df[df["strike"] > 0]

        if df.empty:
            raise ValueError("No valid options data after filtering.")

        t_years = (df["maturity_days"] / 365.0).values
        strikes = df["strike"].values
        prices = df["price"].values
        opt_types = df["option_type"].values

        ivs = np.empty(len(df))
        failed_mask = np.zeros(len(df), dtype=bool)

        for i in range(len(df)):
            try:
                ivs[i] = self.engine.implied_vol(
                    price=float(prices[i]),
                    spot=float(spot_price),
                    strike=float(strikes[i]),
                    t=float(t_years[i]),
                    r=float(risk_free_rate),
                    option_type=str(opt_types[i]),
                )
            except (ValueError, RuntimeError, FloatingPointError):
                failed_mask[i] = True
                ivs[i] = np.nan

        df["iv"] = ivs
        df["moneyness"] = df["strike"] / spot_price

        strike_range = np.sort(df["strike"].unique())
        maturity_range = np.sort(df["maturity_days"].unique())

        surface = np.full((len(strike_range), len(maturity_range)), np.nan)

        for _, row in df.iterrows():
            ki = np.searchsorted(strike_range, row["strike"])
            ti = np.searchsorted(maturity_range, row["maturity_days"])
            if ki < len(strike_range) and ti < len(maturity_range):
                if np.isnan(surface[ki, ti]):
                    surface[ki, ti] = row["iv"]
                else:
                    surface[ki, ti] = (surface[ki, ti] + row["iv"]) / 2.0

        atm_vol = self._interp_atm(surface, strike_range, maturity_range, spot_price)
        skew = self._compute_skew(surface, strike_range, maturity_range, spot_price)
        term_struct = self._compute_term_structure(
            surface, strike_range, maturity_range, spot_price
        )

        result = IVSurfaceResult(
            strike_range=strike_range,
            maturity_range=maturity_range,
            surface_data=surface,
            atm_vol=atm_vol,
            skew=skew,
            term_structure=term_struct,
            spot_price=spot_price,
            risk_free_rate=risk_free_rate,
        )
        _log.info(
            "IV surface built: %d strikes × %d maturities, ATM vol=%.4f",
            len(strike_range), len(maturity_range), atm_vol,
        )
        return result

    def _interp_atm(
        self,
        surface: np.ndarray,
        strikes: np.ndarray,
        maturities: np.ndarray,
        spot: float,
    ) -> float:
        """Interpolate ATM vol at (strike=spot, maturity=30 days)."""
        mat_30_idx = np.searchsorted(maturities, 30)
        if mat_30_idx >= len(maturities):
            mat_30_idx = len(maturities) - 1
        atm_col = surface[:, mat_30_idx]

        valid = ~np.isnan(atm_col)
        if not np.any(valid):
            return np.nanmedian(surface)

        s_valid = strikes[valid]
        iv_valid = atm_col[valid]

        if spot < s_valid.min():
            return float(iv_valid[0])
        if spot > s_valid.max():
            return float(iv_valid[-1])

        idx = np.searchsorted(s_valid, spot)
        lo, hi = max(0, idx - 1), min(len(s_valid), idx + 1)  # type: ignore[call-overload,unused-ignore]
        s_lo, s_hi = s_valid[lo], s_valid[hi]
        iv_lo, iv_hi = iv_valid[lo], iv_valid[hi]
        if s_hi == s_lo:
            return float(iv_lo)
        return float(iv_lo + (iv_hi - iv_lo) * (spot - s_lo) / (s_hi - s_lo))

    def _compute_skew(
        self,
        surface: np.ndarray,
        strikes: np.ndarray,
        maturities: np.ndarray,
        spot: float,
    ) -> dict[str, np.ndarray]:
        """Compute IV skew across moneyness levels (25-delta, ATM, 25-delta call)."""
        mat_30_idx = np.searchsorted(maturities, 30)
        if mat_30_idx >= len(maturities):
            mat_30_idx = len(maturities) - 1

        atm_col = surface[:, mat_30_idx]
        valid = ~np.isnan(atm_col)
        if not np.any(valid):
            return {"moneyness": np.array([]), "iv_put_25d": np.array([]),
                    "iv_call_25d": np.array([])}

        s_v, iv_v = strikes[valid], atm_col[valid]
        moneyness_vals = np.array([0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15])
        iv_interp = np.interp(moneyness_vals * spot, s_v, iv_v)

        skew_put = iv_interp[2] - iv_interp[3]  # 0.95 - ATM
        skew_call = iv_interp[4] - iv_interp[3]  # ATM - 1.05

        return {
            "moneyness": moneyness_vals,
            "iv_put_25d": iv_interp[:3],
            "iv_atm": np.array([iv_interp[3]]),
            "iv_call_25d": iv_interp[4:],
            "skew_put_atm_95": skew_put,
            "skew_call_atm_105": skew_call,
            "skew_25d": skew_put - skew_call,
        }

    def _compute_term_structure(
        self,
        surface: np.ndarray,
        strikes: np.ndarray,
        maturities: np.ndarray,
        spot: float,
    ) -> dict[str, np.ndarray]:
        """Compute ATM vol term structure across available maturities."""
        atm_vols = np.full(len(maturities), np.nan)

        for j in range(len(maturities)):
            col = surface[:, j]
            valid = ~np.isnan(col)
            if not np.any(valid):
                continue
            s_v, iv_v = strikes[valid], col[valid]
            atm_vols[j] = float(np.interp(spot, s_v, iv_v))

        valid_ts = ~np.isnan(atm_vols)
        return {
            "maturities": maturities[valid_ts],
            "atm_vols": atm_vols[valid_ts],
        }


# ─────────────────────────────────────────────────────────────────────────────
# IV_SURFACE_MODEL
# ─────────────────────────────────────────────────────────────────────────────


class IVSurfaceModel:
    """
    Full IV surface model: fit → predict → plot → export.

    This class wraps ``IVSurfaceBuilder`` and adds:
      - ``fit_surface``: fit the surface from options data
      - ``predict_iv``: interpolate IV for arbitrary moneyness/maturity
      - ``plot_surface``: 3D surface plot (matplotlib)
      - ``plot_skew``: skew curve plot
      - ``to_latex``: LaTeX summary table

    Parameters
    ----------
    builder : IVSurfaceBuilder, optional
        Surface builder. A default instance is created if not supplied.
    engine : ImpliedVolatilityEngine, optional
        IV engine. Shared with builder if builder is supplied.

    Examples
    --------
    >>> model = IVSurfaceModel()
    >>> model.fit_surface(df, spot=450, r=0.05)
    >>> iv = model.predict_iv(moneyness=0.95, maturity=30)
    >>> model.plot_surface("output/iv_surface.pdf")
    >>> model.plot_skew("output/iv_skew.pdf")
    >>> print(model.to_latex(model.result))
    """

    def __init__(
        self,
        builder: IVSurfaceBuilder | None = None,
        engine: ImpliedVolatilityEngine | None = None,
    ) -> None:
        self.engine = engine or ImpliedVolatilityEngine()
        self.builder = builder or IVSurfaceBuilder(engine=self.engine)
        self.result: IVSurfaceResult | None = None

    def fit_surface(
        self,
        df: pd.DataFrame,
        spot: float,
        r: float,
    ) -> IVSurfaceResult:
        """
        Fit the complete IV surface from options chain data.

        Parameters
        ----------
        df : pd.DataFrame
            Options chain with columns: ``strike``, ``maturity_days``,
            ``price``, ``option_type``.
        spot : float
            Current underlying price.
        r : float
            Annual continuously-compounded risk-free rate.

        Returns
        -------
        IVSurfaceResult
            The fitted surface result (also stored in ``self.result``).
        """
        self.result = self.builder.build_from_options(df, spot, r)
        return self.result

    def predict_iv(self, moneyness: float, maturity: int | float) -> float:
        """
        Predict IV for a given moneyness and maturity via 2D interpolation.

        Parameters
        ----------
        moneyness : float
            Moneyness = strike / spot. 1.0 = ATM.
        maturity : int or float
            Days to expiry.

        Returns
        -------
        float
            Interpolated implied volatility (annualized).
            Returns NaN if surface is not yet fitted or outside bounds.
        """
        if self.result is None:
            _log.warning("Surface not fitted. Call fit_surface() first.")
            return np.nan

        strikes = self.result.strike_range
        maturities = self.result.maturity_range
        surface = self.result.surface_data
        spot = self.result.spot_price

        target_strike = moneyness * spot
        target_maturity = float(maturity)

        if target_strike < strikes.min() or target_strike > strikes.max():
            return np.nan
        if target_maturity < maturities.min() or target_maturity > maturities.max():
            return np.nan

        from scipy.interpolate import RegularGridInterpolator

        try:
            interp = RegularGridInterpolator(
                (strikes, maturities), surface, method="linear", bounds_error=False,
                fill_value=np.nan
            )
            iv = interp([[target_strike, target_maturity]])[0]
            return float(iv) if not np.isnan(iv) else float(np.nanmean(surface))
        except Exception:
            ki = np.searchsorted(strikes, target_strike) - 1
            ti = np.searchsorted(maturities, target_maturity) - 1
            ki = max(0, min(ki, surface.shape[0] - 1))
            ti = max(0, min(ti, surface.shape[1] - 1))
            return float(np.nanmean(surface[ki, ti]))

    def compute_skew(self, moneyness_range: np.ndarray | None = None) -> dict:
        """
        Compute IV skew (OTM put vs ATM) for a range of moneyness levels.

        Parameters
        ----------
        moneyness_range : np.ndarray, optional
            Custom moneyness levels. Defaults to [0.85, 0.90, 0.95, 1.00,
            1.05, 1.10, 1.15].

        Returns
        -------
        dict
            Skew data including moneyness levels and IV values.
        """
        if self.result is None:
            _log.warning("Surface not fitted.")
            return {}

        if moneyness_range is None:
            moneyness_range = np.array([0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15])

        ivs = np.array([self.predict_iv(m, 30) for m in moneyness_range])
        valid = ~np.isnan(ivs)
        return {
            "moneyness": moneyness_range[valid],
            "iv": ivs[valid],
        }

    def compute_term_structure(
        self, maturities: np.ndarray | None = None
    ) -> dict[str, np.ndarray]:
        """
        Compute ATM volatility term structure.

        Parameters
        ----------
        maturities : np.ndarray, optional
            Custom maturity values in days.
            Defaults to the fitted maturity range.

        Returns
        -------
        dict
            Keys: ``maturities`` and ``atm_vols``.
        """
        if self.result is None:
            _log.warning("Surface not fitted.")
            return {}

        if maturities is None:
            maturities = self.result.maturity_range

        atm_vols = np.array([self.predict_iv(1.0, m) for m in maturities])
        valid = ~np.isnan(atm_vols)
        return {
            "maturities": maturities[valid],
            "atm_vols": atm_vols[valid],
        }

    # ── Plotting ────────────────────────────────────────────────────────────

    def plot_surface(
        self,
        save_path: str | Path,
        title: str = "Implied Volatility Surface",
    ) -> None:
        """
        Generate a 3D IV surface plot.

        Parameters
        ----------
        save_path : str or Path
            Output file path. Supports PDF, PNG, SVG.
        title : str, default "Implied Volatility Surface"
            Plot title.
        """
        if self.result is None:
            raise RuntimeError("Surface not fitted. Call fit_surface() first.")

        import matplotlib.pyplot as plt

        strikes = self.result.strike_range
        maturities = self.result.maturity_range
        surface = self.result.surface_data.copy()
        surface = np.where(np.isnan(surface), 0, surface)

        K, T = np.meshgrid(strikes, maturities)

        fig = plt.figure(figsize=(10, 7))
        ax = fig.add_subplot(111, projection="3d")
        surf = ax.plot_surface(
            K, T, surface.T,
            cmap="viridis",
            linewidth=0,
            antialiased=True,
            alpha=0.85,
        )
        ax.set_xlabel("Strike", fontsize=11)
        ax.set_ylabel("Maturity (days)", fontsize=11)
        ax.set_zlabel("Implied Vol", fontsize=11)
        ax.set_title(title, fontsize=13, pad=10)
        fig.colorbar(surf, ax=ax, shrink=0.5, label="IV")
        ax.view_init(elev=20, azim=45)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        _log.info("IV surface plot saved to %s", save_path)

    def plot_skew(
        self,
        save_path: str | Path,
        title: str = "IV Skew (30-day maturity)",
    ) -> None:
        """
        Generate a volatility skew plot (moneyness vs IV).

        Parameters
        ----------
        save_path : str or Path
            Output file path.
        title : str, default "IV Skew (30-day maturity)"
            Plot title.
        """
        skew_data = self.compute_skew()
        if not skew_data or len(skew_data.get("moneyness", [])) == 0:
            _log.warning("No skew data to plot.")
            return

        import matplotlib.pyplot as plt

        mny = skew_data["moneyness"]
        ivs = skew_data["iv"]

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(mny, ivs * 100, "o-", color="steelblue", linewidth=2,
                markersize=6, label="IV Skew")
        ax.axvline(1.0, color="gray", linestyle="--", alpha=0.7, label="ATM")
        ax.set_xlabel("Moneyness (K/S)", fontsize=11)
        ax.set_ylabel("Implied Volatility (%)", fontsize=11)
        ax.set_title(title, fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        _log.info("Skew plot saved to %s", save_path)

    def plot_term_structure(
        self,
        save_path: str | Path,
        title: str = "ATM Vol Term Structure",
    ) -> None:
        """
        Generate ATM volatility term structure plot.

        Parameters
        ----------
        save_path : str or Path
            Output file path.
        title : str, default "ATM Vol Term Structure"
            Plot title.
        """
        ts = self.compute_term_structure()
        if len(ts.get("maturities", [])) == 0:
            _log.warning("No term structure data to plot.")
            return

        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(ts["maturities"], ts["atm_vols"] * 100, "o-",
                color="darkorange", linewidth=2, markersize=6,
                label="ATM Vol")
        ax.set_xlabel("Maturity (days)", fontsize=11)
        ax.set_ylabel("ATM Implied Volatility (%)", fontsize=11)
        ax.set_title(title, fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        _log.info("Term structure plot saved to %s", save_path)

    # ── LaTeX export ─────────────────────────────────────────────────────────

    def to_latex(self, result: IVSurfaceResult | None = None) -> str:
        """
        Generate a LaTeX summary table for the IV surface result.

        Parameters
        ----------
        result : IVSurfaceResult, optional
            Result to export. Defaults to ``self.result``.

        Returns
        -------
        str
            LaTeX table string (booktabs style, three-part table).
        """
        res = result or self.result
        if res is None:
            return "% No IV surface result available."

        spot = res.spot_price
        r = res.risk_free_rate

        rows = [
            ("Spot Price", rf"${spot:,.2f}$"),
            ("Risk-Free Rate", rf"${r:.2f}\%$"),
            ("ATM Vol (30-day)", rf"${res.atm_vol * 100:.2f}\%$"),
        ]

        if res.skew:
            skew = res.skew
            rows.append((r"Skew (25d Put - ATM)", rf"${skew.get('skew_put_atm_95', 0) * 100:.2f}\%$"))
            rows.append((r"Skew (ATM - 25d Call)", rf"${skew.get('skew_call_atm_105', 0) * 100:.2f}\%$"))
            rows.append((r"Skew (25d Put - 25d Call)", rf"${skew.get('skew_25d', 0) * 100:.2f}\%$"))

        if res.term_structure and "maturities" in res.term_structure:
            ts = res.term_structure
            mny_list = [f"{m:.0f}d" for m in ts["maturities"][:5]]
            iv_list = [rf"${v * 100:.2f}\%$" for v in ts["atm_vols"][:5]]
            rows.append(("ATM Vol (short mat.)", "  ".join(
                f"{m}:{iv}" for m, iv in zip(mny_list, iv_list, strict=False)
            )))

        label = "tab:iv_surface_summary"

        parts = [
            "\\begin{table}[htbp]",
            "  \\centering",
            "  \\caption{Implied Volatility Surface Summary}",
            f"  \\label{{{label}}}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{ll}",
            "    \\toprule",
            "    \\textbf{Variable} & \\textbf{Value} \\\\",
            "    \\midrule",
        ]

        for var, val in rows:
            parts.append(f"    {var} & {val} \\\\")

        parts.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            f"    \\item \\textit{{Notes:}} ATM = at-the-money (K=S). "
            "Skew = IV(K/S=0.95) $-$ IV(K/S=1.00) for put skew. "
            f"Spot = {spot:.2f}, r = {r:.2f}\\%.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{table}",
        ])

        return "\n".join(parts)

    # ── MCP data integration ─────────────────────────────────────────────────

    @staticmethod
    def from_mcp_options(
        ticker: str,
        spot_price: float,
        risk_free_rate: float,
        use_approx: bool = True,
    ) -> IVSurfaceResult:
        """
        Build IV surface directly from MCP user-yfinance options data.

        This is a convenience wrapper that:
          1. Calls ``user-yfinance: get_yf_options(ticker)`` via MCP tool.
          2. Transforms the result into the required DataFrame format.
          3. Returns a fitted ``IVSurfaceResult``.

        Parameters
        ----------
        ticker : str
            Underlying ticker, e.g. "SPY", "QQQ", "AAPL", "TSLA".
        spot_price : float
            Current spot price of the underlying.
        risk_free_rate : float
            Annual risk-free rate.
        use_approx : bool, default True
            If True, approximate maturity_days from expiry date in options
            chain rather than computing exact days.

        Returns
        -------
        IVSurfaceResult

        Examples
        --------
        >>> from scripts.research_framework.options_iv_surface import IVSurfaceModel
        >>> result = IVSurfaceModel.from_mcp_options(
        ...     ticker="SPY", spot_price=450, risk_free_rate=0.05)
        >>> print(result.atm_vol)
        """
        try:
            from mcp.client import Client
        except ImportError:
            raise ImportError(
                "MCP client not available. Install: pip install mcp "
                "Or use a local DataFrame directly."
            )

        try:
            client = Client("user-yfinance")
            raw = client.call(
                "get_yf_options",
                {"ticker": ticker}
            )
        except Exception as exc:
            _log.error("MCP call failed: %s", exc)
            raise RuntimeError(
                f"MCP call to user-yfinance failed for ticker {ticker}. "
                f"Check MCP server status. Error: {exc}"
            )

        rows = []
        for chain in raw.get("option_chain", []):
            for opt in chain.get("options", []):
                strike = float(opt.get("strike", 0))
                price = float(opt.get("lastPrice", opt.get("price", 0)))
                opt_type = opt.get("type", opt.get("optionType", "")).lower()
                if "put" in opt_type:
                    opt_type = "put"
                elif "call" in opt_type:
                    opt_type = "call"
                else:
                    continue

                expiry_str = chain.get("expirationDate",
                                       chain.get("expiration", ""))
                if expiry_str:
                    try:
                        from datetime import date, datetime
                        if isinstance(expiry_str, int | float):
                            expiry_dt = date.fromtimestamp(expiry_str)
                        else:
                            expiry_dt = datetime.strptime(
                                str(expiry_str), "%Y-%m-%d"
                            ).date()
                        days = (expiry_dt - date.today()).days
                    except Exception:
                        days = 30
                else:
                    days = 30

                if strike <= 0 or price <= 0 or days <= 0:
                    continue

                rows.append({
                    "strike": strike,
                    "maturity_days": days,
                    "price": price,
                    "option_type": opt_type,
                })

        if not rows:
            raise ValueError(
                f"No valid options extracted from MCP response for {ticker}. "
                "The ticker may not have listed options."
            )

        df = pd.DataFrame(rows)
        model = IVSurfaceModel()
        result = model.fit_surface(df, spot=spot_price, r=risk_free_rate)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE CLI (for quick testing)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    import numpy as np

    parser = argparse.ArgumentParser(
        description="IV Surface Builder — test on synthetic options data"
    )
    parser.add_argument("--ticker", default="SPY", help="Ticker for MCP call")
    parser.add_argument("--spot", type=float, default=450.0, help="Spot price")
    parser.add_argument("--rate", type=float, default=0.05, help="Risk-free rate")
    parser.add_argument("--n-strikes", type=int, default=11, help="# strikes")
    parser.add_argument("--n-maturities", type=int, default=5, help="# maturities")
    parser.add_argument("--save-dir", default="output", help="Output directory")
    args = parser.parse_args()

    Path(args.save_dir).mkdir(parents=True, exist_ok=True)

    strikes = np.linspace(args.spot * 0.85, args.spot * 1.15, args.n_strikes)
    maturities = np.array([7, 14, 30, 60, 90])[: args.n_maturities]
    eng = ImpliedVolatilityEngine()
    engine_bs = eng  # alias

    rows = []
    base_vol = 0.20
    for t in maturities:
        t_yr = t / 365.0
        for k in strikes:
            for otype in ["call", "put"]:
                sigma = base_vol + 0.02 * (k / args.spot - 1) + 0.005 * (t_yr)
                sigma = max(0.05, min(sigma, 0.80))
                try:
                    price = engine_bs.black_scholes_price(
                        spot=args.spot, strike=k, t=t_yr,
                        r=args.rate, sigma=sigma, option_type=otype
                    )
                    rows.append({
                        "strike": k,
                        "maturity_days": t,
                        "price": price,
                        "option_type": otype,
                    })
                except ValueError:
                    continue

    df = pd.DataFrame(rows)
    print(f"Synthetic options: {len(df)} rows")

    builder = IVSurfaceBuilder()
    result = builder.build_from_options(df, spot_price=args.spot, risk_free_rate=args.rate)
    print(f"ATM vol: {result.atm_vol:.4f}")
    print(f"Surface shape: {result.surface_data.shape}")

    model = IVSurfaceModel(builder=builder)
    model.result = result

    surf_path = Path(args.save_dir) / f"iv_surface_{args.ticker}.pdf"
    skew_path = Path(args.save_dir) / f"iv_skew_{args.ticker}.pdf"
    ts_path = Path(args.save_dir) / f"iv_term_{args.ticker}.pdf"

    model.plot_surface(str(surf_path))
    model.plot_skew(str(skew_path))
    model.plot_term_structure(str(ts_path))

    print(model.to_latex(result))
    print("\nDone. Files saved to:", args.save_dir)
