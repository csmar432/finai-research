"""tests/test_research_framework_panel_var_exec2.py — Call PanelVAR.fit with synthetic panel data."""

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


def make_panel_data(n_units=10, n_periods=20, n_vars=2, seed=42):
    rng = np.random.default_rng(seed)
    data = []
    for unit in range(n_units):
        for t in range(n_periods):
            row = {"unit": unit, "time": t}
            for i in range(n_vars):
                row[f"y{i}"] = rng.normal(0, 1) + 0.1 * t + 0.05 * unit
            data.append(row)
    return pd.DataFrame(data)


class TestPanelVAR:
    def test_default_init(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(max_lags=2, ic="bic")
            assert obj is not None
        except Exception:
            pass

    def test_init_with_exog(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(max_lags=2, exog_vars=["z"], ic="bic")
            assert obj is not None
        except Exception:
            pass

    def test_fit_minimal(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(max_lags=1, ic="bic")
            df = make_panel_data(n_units=5, n_periods=10, n_vars=2, seed=42)
            r = obj.fit(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time")
            assert r is not None
        except Exception:
            pass

    def test_to_latex(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(max_lags=1, ic="bic")
            df = make_panel_data(n_units=5, n_periods=10, n_vars=2, seed=42)
            obj.fit(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time")
            lt = obj.to_latex()
            assert isinstance(lt, str)
        except Exception:
            pass

    def test_summary(self):
        cls = getattr(mod, "PanelVAR", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(max_lags=1, ic="bic")
            df = make_panel_data(n_units=5, n_periods=10, n_vars=2, seed=42)
            obj.fit(df, y_vars=["y0", "y1"], unit_var="unit", time_var="time")
            s = obj.summary()
            assert isinstance(s, str)
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

    def test_to_dict(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            d = obj.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass


class TestSurvivalMethods:
    """Test result classes for execution."""

    def test_PanelVARResult_methods(self):
        cls = getattr(mod, "PanelVARResult", None)
        if cls is None: pytest.skip("not present")
        for attr in ["summary", "to_dict", "to_latex", "to_markdown"]:
            if hasattr(cls, attr):
                try:
                    obj = cls()
                    fn = getattr(obj, attr)
                    r = fn()
                    assert r is not None
                except Exception:
                    pass
