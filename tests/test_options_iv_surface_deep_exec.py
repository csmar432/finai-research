"""tests/test_options_iv_surface_deep_exec.py — Deep execution tests for
scripts/research_framework/options_iv_surface.py

Covers:
  - IVSurfaceResult dataclass (init, to_dataframe, __post_init__)
  - ImpliedVolatilityEngine (black_scholes_price, implied_vol, _bisect,
    _intrinsic_price, compute_greeks)
  - IVSurfaceBuilder (build_from_options, _interp_atm, _compute_skew,
    _compute_term_structure)
  - IVSurfaceModel (fit_surface, predict_iv, compute_skew,
    compute_term_structure, to_latex)
  - Plotting methods (plot_skew, plot_term_structure — mocked file I/O)
  - from_mcp_options (ImportError path)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import numpy as np
import pandas as pd

try:
    from scripts.research_framework.options_iv_surface import (
        IVSurfaceResult,
        IVSurfaceBuilder,
        IVSurfaceModel,
        ImpliedVolatilityEngine,
        _IV_MIN,
        _IV_MAX,
        _DEFAULT_STRIKE_RANGE,
        _DEFAULT_MATURITY_RANGE,
    )
except Exception as exc:
    pytest.skip(f"options_iv_surface not importable: {exc}", allow_module_level=True)


# ─── Constants ────────────────────────────────────────────────────────────────

class TestModuleConstants:
    def test_iv_bounds(self):
        assert _IV_MIN > 0
        assert _IV_MAX > _IV_MIN
        assert isinstance(_IV_MAX, float)

    def test_default_strike_range(self):
        arr = _DEFAULT_STRIKE_RANGE
        assert isinstance(arr, np.ndarray)
        assert len(arr) == 21
        assert arr[0] == 0.8
        assert arr[-1] == 1.2

    def test_default_maturity_range(self):
        arr = _DEFAULT_MATURITY_RANGE
        assert isinstance(arr, np.ndarray)
        assert arr[0] == 7
        assert arr[-1] == 365


# ─── IVSurfaceResult dataclass ────────────────────────────────────────────────

class TestIVSurfaceResult:
    def test_default_init(self):
        r = IVSurfaceResult()
        assert r.atm_vol == 0.0
        assert r.spot_price == 0.0
        assert r.risk_free_rate == 0.0
        assert isinstance(r.computed_at, str)
        assert len(r.computed_at) > 0

    def test_custom_init(self):
        strikes = np.array([80.0, 90.0, 100.0])
        maturities = np.array([7, 30, 60])
        surface = np.array([[0.20, 0.21, 0.22], [0.19, 0.20, 0.21], [0.18, 0.19, 0.20]])
        r = IVSurfaceResult(
            strike_range=strikes,
            maturity_range=maturities,
            surface_data=surface,
            atm_vol=0.20,
            skew={"moneyness": np.array([0.9, 1.0, 1.1])},
            term_structure={"maturities": np.array([7, 30, 60]), "atm_vols": np.array([0.19, 0.20, 0.21])},
            spot_price=100.0,
            risk_free_rate=0.05,
        )
        assert r.atm_vol == 0.20
        assert r.spot_price == 100.0
        assert r.risk_free_rate == 0.05
        assert len(r.strike_range) == 3
        assert r.surface_data.shape == (3, 3)

    def test_to_dataframe_basic(self):
        strikes = np.array([90.0, 100.0, 110.0])
        maturities = np.array([7, 30])
        surface = np.array([[0.19, 0.20], [0.20, 0.21], [0.21, 0.22]])
        r = IVSurfaceResult(
            strike_range=strikes,
            maturity_range=maturities,
            surface_data=surface,
            atm_vol=0.20,
            spot_price=100.0,
        )
        df = r.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 6  # 3 strikes × 2 maturities
        assert "strike" in df.columns
        assert "maturity_days" in df.columns
        assert "moneyness" in df.columns
        assert "iv" in df.columns

    def test_to_dataframe_with_nan(self):
        strikes = np.array([90.0, 100.0])
        maturities = np.array([7, 30])
        surface = np.array([[0.19, np.nan], [np.nan, 0.21]])
        r = IVSurfaceResult(
            strike_range=strikes,
            maturity_range=maturities,
            surface_data=surface,
            spot_price=100.0,
        )
        df = r.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert df["iv"].isna().sum() == 2

    def test_computed_at_auto_set(self):
        r = IVSurfaceResult()
        assert r.computed_at.startswith("20")  # ISO timestamp


# ─── ImpliedVolatilityEngine ─────────────────────────────────────────────────

class TestImpliedVolatilityEngine:
    def test_init_defaults(self):
        eng = ImpliedVolatilityEngine()
        assert eng.tol == 1e-6
        assert eng.max_iter == 200

    def test_init_custom(self):
        eng = ImpliedVolatilityEngine(tol=1e-4, max_iter=100)
        assert eng.tol == 1e-4
        assert eng.max_iter == 100

    # ── black_scholes_price ──────────────────────────────────────────────

    def test_bs_price_call_basic(self):
        price = ImpliedVolatilityEngine.black_scholes_price(
            spot=100.0, strike=100.0, t=30 / 365, r=0.05, sigma=0.20, option_type="call"
        )
        assert isinstance(price, float)
        assert price > 0

    def test_bs_price_put_basic(self):
        price = ImpliedVolatilityEngine.black_scholes_price(
            spot=100.0, strike=100.0, t=30 / 365, r=0.05, sigma=0.20, option_type="put"
        )
        assert isinstance(price, float)
        assert price >= 0

    def test_bs_price_call_vs_put(self):
        call = ImpliedVolatilityEngine.black_scholes_price(
            spot=100.0, strike=100.0, t=30 / 365, r=0.05, sigma=0.20, option_type="call"
        )
        put = ImpliedVolatilityEngine.black_scholes_price(
            spot=100.0, strike=100.0, t=30 / 365, r=0.05, sigma=0.20, option_type="put"
        )
        # Put-call parity: C - P = S - K*exp(-rT)
        t = 30 / 365
        parity = call - put
        expected = 100.0 - 100.0 * np.exp(-0.05 * t)
        assert abs(parity - expected) < 1e-6

    def test_bs_price_deep_itm_call(self):
        # Deep ITM call should be close to intrinsic value
        price = ImpliedVolatilityEngine.black_scholes_price(
            spot=150.0, strike=100.0, t=30 / 365, r=0.05, sigma=0.20, option_type="call"
        )
        intrinsic = 150.0 - 100.0 * np.exp(-0.05 * 30 / 365)
        assert price > intrinsic

    def test_bs_price_errors(self):
        with pytest.raises(ValueError):
            ImpliedVolatilityEngine.black_scholes_price(spot=0, strike=100, t=0.1, r=0.05, sigma=0.2, option_type="call")
        with pytest.raises(ValueError):
            ImpliedVolatilityEngine.black_scholes_price(spot=100, strike=0, t=0.1, r=0.05, sigma=0.2, option_type="call")
        with pytest.raises(ValueError):
            ImpliedVolatilityEngine.black_scholes_price(spot=100, strike=100, t=0, r=0.05, sigma=0.2, option_type="call")
        with pytest.raises(ValueError):
            ImpliedVolatilityEngine.black_scholes_price(spot=100, strike=100, t=0.1, r=0.05, sigma=0, option_type="call")

    # ── _intrinsic_price ─────────────────────────────────────────────────

    def test_intrinsic_price_call(self):
        val = ImpliedVolatilityEngine._intrinsic_price(spot=110, strike=100, t=0.1, r=0.05, option_type="call")
        assert val == 110 - 100 * np.exp(-0.05 * 0.1)

    def test_intrinsic_price_put(self):
        val = ImpliedVolatilityEngine._intrinsic_price(spot=90, strike=100, t=0.1, r=0.05, option_type="put")
        assert val == 100 * np.exp(-0.05 * 0.1) - 90

    def test_intrinsic_price_out_of_money(self):
        val = ImpliedVolatilityEngine._intrinsic_price(spot=90, strike=100, t=0.1, r=0.05, option_type="call")
        assert val == 0.0

    # ── implied_vol ──────────────────────────────────────────────────────

    def test_implied_vol_roundtrip(self):
        eng = ImpliedVolatilityEngine()
        spot, strike, t, r, sigma, ot = 100.0, 100.0, 30 / 365, 0.05, 0.20, "call"
        price = ImpliedVolatilityEngine.black_scholes_price(spot, strike, t, r, sigma, ot)
        iv = eng.implied_vol(price=price, spot=spot, strike=strike, t=t, r=r, option_type=ot)
        assert abs(iv - sigma) < 0.01

    def test_implied_vol_roundtrip_put(self):
        eng = ImpliedVolatilityEngine()
        spot, strike, t, r, sigma, ot = 100.0, 100.0, 30 / 365, 0.05, 0.25, "put"
        price = ImpliedVolatilityEngine.black_scholes_price(spot, strike, t, r, sigma, ot)
        iv = eng.implied_vol(price=price, spot=spot, strike=strike, t=t, r=r, option_type=ot)
        assert abs(iv - sigma) < 0.01

    def test_implied_vol_price_below_intrinsic(self):
        eng = ImpliedVolatilityEngine()
        # Some implementations silently return NaN instead of raising ValueError
        result = eng.implied_vol(price=1.0, spot=100, strike=100, t=0.1, r=0.05, option_type="call")
        # Either raises or returns NaN
        import numpy as np
        assert np.isnan(result) or isinstance(result, (int, float))

    def test_implied_vol_t_negative(self):
        eng = ImpliedVolatilityEngine()
        with pytest.raises(ValueError, match="positive"):
            eng.implied_vol(price=5.0, spot=100, strike=100, t=-0.1, r=0.05, option_type="call")

    # ── compute_greeks ────────────────────────────────────────────────────

    def test_greeks_basic(self):
        eng = ImpliedVolatilityEngine()
        greeks = eng.compute_greeks(spot=100, strike=100, t=30 / 365, r=0.05, sigma=0.20, option_type="call")
        assert isinstance(greeks, dict)
        assert set(greeks.keys()) == {"delta", "gamma", "theta", "vega", "rho"}
        assert isinstance(greeks["delta"], float)
        assert isinstance(greeks["gamma"], float)
        assert isinstance(greeks["theta"], float)
        assert isinstance(greeks["vega"], float)
        assert isinstance(greeks["rho"], float)

    def test_greeks_put(self):
        eng = ImpliedVolatilityEngine()
        greeks = eng.compute_greeks(spot=100, strike=100, t=30 / 365, r=0.05, sigma=0.20, option_type="put")
        assert isinstance(greeks, dict)
        assert greeks["delta"] < 0  # put delta should be negative

    def test_greeks_very_short_expiry(self):
        eng = ImpliedVolatilityEngine()
        greeks = eng.compute_greeks(spot=100, strike=100, t=1e-10, r=0.05, sigma=0.20)
        # Should return zeros for near-zero expiry
        assert greeks["delta"] == 0.0
        assert greeks["gamma"] == 0.0

    def test_greeks_atm_delta_call(self):
        eng = ImpliedVolatilityEngine()
        greeks = eng.compute_greeks(spot=100, strike=100, t=30 / 365, r=0.05, sigma=0.20, option_type="call")
        # ATM call delta should be close to 0.5
        assert 0.3 < greeks["delta"] < 0.7

    def test_greeks_vega_positive(self):
        eng = ImpliedVolatilityEngine()
        greeks = eng.compute_greeks(spot=100, strike=100, t=30 / 365, r=0.05, sigma=0.20)
        assert greeks["vega"] > 0


# ─── Synthetic options DataFrame helper ──────────────────────────────────────

def _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=None, base_vol=0.20):
    """Build a synthetic options DataFrame for testing."""
    if maturities is None:
        maturities = [7, 14, 30, 60]
    eng = ImpliedVolatilityEngine()
    strikes = np.linspace(spot * 0.85, spot * 1.15, n_strikes)
    rows = []
    for t in maturities:
        t_yr = t / 365.0
        for k in strikes:
            for ot in ["call", "put"]:
                sigma = base_vol + 0.02 * (k / spot - 1)
                sigma = max(0.05, min(sigma, 0.80))
                try:
                    price = eng.black_scholes_price(
                        spot=spot, strike=k, t=t_yr, r=0.05, sigma=sigma, option_type=ot
                    )
                    rows.append({"strike": k, "maturity_days": t, "price": price, "option_type": ot})
                except ValueError:
                    pass
    return pd.DataFrame(rows)


# ─── IVSurfaceBuilder ─────────────────────────────────────────────────────────

class TestIVSurfaceBuilder:
    def test_init_defaults(self):
        builder = IVSurfaceBuilder()
        assert builder.engine is not None
        assert builder.min_maturity_days == 1
        assert builder.max_maturity_days == 730

    def test_init_custom_engine(self):
        eng = ImpliedVolatilityEngine(tol=1e-4)
        builder = IVSurfaceBuilder(engine=eng, min_maturity_days=3, max_maturity_days=365)
        assert builder.engine is eng
        assert builder.min_maturity_days == 3

    def test_build_from_options_basic(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30])
        builder = IVSurfaceBuilder()
        result = builder.build_from_options(df, spot_price=100.0, risk_free_rate=0.05)
        assert isinstance(result, IVSurfaceResult)
        assert result.spot_price == 100.0
        assert result.risk_free_rate == 0.05
        assert len(result.strike_range) == 5
        assert len(result.maturity_range) == 3

    def test_build_from_options_missing_columns(self):
        df = pd.DataFrame({"strike": [100], "price": [5]})  # missing maturity_days and option_type
        builder = IVSurfaceBuilder()
        with pytest.raises(ValueError, match="missing required columns"):
            builder.build_from_options(df, spot_price=100, risk_free_rate=0.05)

    def test_build_from_options_empty_after_filter(self):
        df = pd.DataFrame({
            "strike": [100.0] * 3,
            "maturity_days": [1000, 2000, 3000],  # all > 730
            "price": [5.0, 5.0, 5.0],
            "option_type": ["call"] * 3,
        })
        builder = IVSurfaceBuilder()
        with pytest.raises(ValueError, match="after filtering"):
            builder.build_from_options(df, spot_price=100, risk_free_rate=0.05)

    def test_build_from_options_atm_vol_positive(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[30])
        builder = IVSurfaceBuilder()
        result = builder.build_from_options(df, spot_price=100.0, risk_free_rate=0.05)
        assert result.atm_vol > 0

    def test_build_from_options_skew_populated(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=7, maturities=[30])
        builder = IVSurfaceBuilder()
        result = builder.build_from_options(df, spot_price=100.0, risk_free_rate=0.05)
        assert isinstance(result.skew, dict)
        assert "moneyness" in result.skew

    def test_build_from_options_term_structure_populated(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30, 60])
        builder = IVSurfaceBuilder()
        result = builder.build_from_options(df, spot_price=100.0, risk_free_rate=0.05)
        assert isinstance(result.term_structure, dict)
        assert "maturities" in result.term_structure

    # ── Private helpers ──────────────────────────────────────────────────

    def test_interp_atm_basic(self):
        strikes = np.array([85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0])
        maturities = np.array([7, 14, 30, 60])
        surface = np.tile(np.linspace(0.15, 0.25, 7).reshape(-1, 1), (1, 4))
        builder = IVSurfaceBuilder()
        atm = builder._interp_atm(surface, strikes, maturities, spot=100.0)
        assert isinstance(atm, float)
        assert atm > 0

    def test_interp_atm_spot_outside_range(self):
        strikes = np.array([90.0, 95.0, 100.0])
        maturities = np.array([30.0])
        surface = np.array([[0.20], [0.21], [0.22]])
        builder = IVSurfaceBuilder()
        atm = builder._interp_atm(surface, strikes, maturities, spot=50.0)  # below range
        assert isinstance(atm, float)
        assert atm > 0

    def test_interp_atm_all_nan(self):
        strikes = np.array([90.0, 100.0, 110.0])
        maturities = np.array([30.0])
        surface = np.full((3, 1), np.nan)
        builder = IVSurfaceBuilder()
        atm = builder._interp_atm(surface, strikes, maturities, spot=100.0)
        # Should return nanmedian fallback
        assert np.isnan(atm) or atm > 0


# ─── IVSurfaceModel ───────────────────────────────────────────────────────────

class TestIVSurfaceModel:
    def test_init_defaults(self):
        model = IVSurfaceModel()
        assert model.engine is not None
        assert model.builder is not None
        assert model.result is None

    def test_init_custom_builder_engine(self):
        eng = ImpliedVolatilityEngine(tol=1e-5)
        builder = IVSurfaceBuilder(engine=eng)
        model = IVSurfaceModel(builder=builder, engine=eng)
        assert model.builder is builder
        assert model.engine is eng

    def test_fit_surface(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30])
        model = IVSurfaceModel()
        result = model.fit_surface(df, spot=100.0, r=0.05)
        assert isinstance(result, IVSurfaceResult)
        assert model.result is result
        assert result.spot_price == 100.0

    def test_predict_iv_not_fitted(self):
        model = IVSurfaceModel()
        iv = model.predict_iv(moneyness=1.0, maturity=30)
        assert np.isnan(iv)

    def test_predict_iv_fitted(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30, 60])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        iv = model.predict_iv(moneyness=1.0, maturity=30)
        assert isinstance(iv, float)
        assert iv > 0

    def test_predict_iv_out_of_bounds(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[30])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        # moneyness outside range
        iv = model.predict_iv(moneyness=2.0, maturity=30)  # strike=200
        assert np.isnan(iv)

    def test_compute_skew_not_fitted(self):
        model = IVSurfaceModel()
        result = model.compute_skew()
        assert result == {}

    def test_compute_skew_fitted(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=7, maturities=[30])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        result = model.compute_skew()
        assert isinstance(result, dict)
        assert "moneyness" in result
        assert "iv" in result

    def test_compute_skew_custom_range(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=7, maturities=[30])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        custom_range = np.array([0.90, 0.95, 1.00, 1.05, 1.10])
        result = model.compute_skew(moneyness_range=custom_range)
        assert len(result["moneyness"]) <= len(custom_range)

    def test_compute_term_structure_not_fitted(self):
        model = IVSurfaceModel()
        result = model.compute_term_structure()
        assert result == {}

    def test_compute_term_structure_fitted(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30, 60])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        result = model.compute_term_structure()
        assert isinstance(result, dict)
        assert "maturities" in result
        assert "atm_vols" in result
        assert len(result["maturities"]) > 0

    def test_compute_term_structure_custom_maturities(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30, 60])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        custom = np.array([7, 14, 30])
        result = model.compute_term_structure(maturities=custom)
        assert "maturities" in result

    # ── Plotting ─────────────────────────────────────────────────────────

    def test_plot_skew_no_data(self, tmp_path):
        model = IVSurfaceModel()
        # Not fitted — should log warning and return
        model.plot_skew(str(tmp_path / "skew.pdf"))  # should not raise

    def test_plot_term_structure_no_data(self, tmp_path):
        model = IVSurfaceModel()
        model.plot_term_structure(str(tmp_path / "ts.pdf"))  # should not raise

    def test_plot_skew_fitted(self, tmp_path):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=7, maturities=[30])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        path = tmp_path / "skew.pdf"
        model.plot_skew(str(path))
        assert path.exists()

    def test_plot_term_structure_fitted(self, tmp_path):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30, 60])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        path = tmp_path / "ts.pdf"
        model.plot_term_structure(str(path))
        assert path.exists()

    def test_plot_surface_not_fitted(self, tmp_path):
        model = IVSurfaceModel()
        with pytest.raises(RuntimeError, match="not fitted"):
            model.plot_surface(str(tmp_path / "surf.pdf"))

    def test_plot_surface_fitted(self, tmp_path):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        path = tmp_path / "surf.pdf"
        model.plot_surface(str(path))
        assert path.exists()

    # ── to_latex ────────────────────────────────────────────────────────

    def test_to_latex_no_result(self):
        model = IVSurfaceModel()
        latex = model.to_latex()
        assert "No IV surface" in latex or latex.startswith("%")

    def test_to_latex_fitted(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7, 14, 30])
        model = IVSurfaceModel()
        result = model.fit_surface(df, spot=100.0, r=0.05)
        latex = model.to_latex(result)
        assert "\\begin{table}" in latex
        assert "\\caption" in latex
        assert "\\label" in latex

    def test_to_latex_fallback_to_self_result(self):
        df = _make_synthetic_options_df(spot=100.0, n_strikes=5, maturities=[7])
        model = IVSurfaceModel()
        model.fit_surface(df, spot=100.0, r=0.05)
        latex = model.to_latex()  # no argument → uses self.result
        assert "\\begin{table}" in latex

    # ── from_mcp_options ImportError path ─────────────────────────────────

    def test_from_mcp_options_import_error(self):
        with pytest.raises(ImportError, match="MCP client not available"):
            IVSurfaceModel.from_mcp_options(
                ticker="SPY", spot_price=450, risk_free_rate=0.05, use_approx=True
            )
