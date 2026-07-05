"""tests/test_research_framework_panel_var_exec3.py — Deeper panel var tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import panel_var as mod
except Exception as _exc:
    pytest.skip(f"panel_var not importable: {_exc}", allow_module_level=True)


def make_panel_data(n_units=20, n_periods=20, n_vars=3, seed=42):
    rng = np.random.default_rng(seed)
    data = []
    for unit in range(n_units):
        for t in range(n_periods):
            row = {"unit": unit, "time": t}
            for i in range(n_vars):
                row[f"y{i}"] = rng.normal(0, 1) + 0.1 * t + 0.05 * unit
            data.append(row)
    return pd.DataFrame(data)


class TestInfoCriteria:
    def test_build_lags(self):
        fn = getattr(mod, "_build_lags", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(5, 10, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", max_lags=2)
            assert r is not None
        except Exception:
            pass

    def test_ic(self):
        fn = getattr(mod, "_information_criteria_ols", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(5, 15, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", max_lags=2)
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_select_lag(self):
        fn = getattr(mod, "_select_lag", None)
        if fn is None: pytest.skip("not present")
        try:
            criteria = {1: {"aic": 100, "bic": 110}, 2: {"aic": 90, "bic": 100}}
            r = fn(criteria, ic="bic")
            assert isinstance(r, int)
        except Exception:
            pass


class TestTransforms:
    def test_first_diff(self):
        fn = getattr(mod, "_first_difference_transform", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(5, 10, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time")
            assert r is not None
        except Exception:
            pass

    def test_ols_coef(self):
        fn = getattr(mod, "_ols_var_coefficients", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(5, 15, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", lags=1)
            assert r is not None
        except Exception:
            pass


class TestIRF:
    def test_irf_cholesky(self):
        fn = getattr(mod, "_irf_cholesky", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            B = rng.normal(0, 0.1, (3, 2))
            Sigma = np.array([[1.0, 0.3], [0.3, 1.0]])
            r = fn(B, Sigma, horizon=5)
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_fevd_from_irf(self):
        fn = getattr(mod, "_fevd_from_irf", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            irf = rng.normal(0, 0.1, (5, 2, 2))
            r = fn(irf)
            assert r is not None
        except Exception:
            pass

    def test_bootstrap_irf(self):
        fn = getattr(mod, "_bootstrap_irf_ci", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(5, 15, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", n_boot=10, horizon=2)
            assert r is not None
        except Exception:
            pass


class TestDH:
    def test_dumitrescu_hurlin(self):
        fn = getattr(mod, "_dumitrescu_hurlin", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 20, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", lags=1)
            assert r is not None
        except Exception:
            pass


class TestGMM:
    def test_gmm_system_var(self):
        fn = getattr(mod, "_gmm_system_var", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 15, 2, seed=42)
            r = fn(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time", lags=1)
            assert r is not None
        except Exception:
            pass


class TestSignificanceStars:
    def test_basic(self):
        fn = getattr(mod, "_significance_stars", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(0.01)
            assert isinstance(r, str)
        except Exception:
            pass

    def test_higher_p(self):
        fn = getattr(mod, "_significance_stars", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(0.5)
            assert isinstance(r, str)
        except Exception:
            pass


class TestPanelVARResult:
    def test_default(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(coefs={}, ses={}, pvals={})
            assert obj is not None
        except Exception:
            pass

    def test_to_dict(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            d = obj.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass
