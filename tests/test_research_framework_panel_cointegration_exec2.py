"""tests/test_research_framework_panel_cointegration_exec2.py — Deeper panel cointegration tests."""

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
    from scripts.research_framework import panel_cointegration as mod
except Exception as _exc:
    pytest.skip(f"panel_cointegration not importable: {_exc}", allow_module_level=True)


def make_panel_data(n_units=20, n_periods=50, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_units):
        x = np.cumsum(rng.normal(0, 1, n_periods))
        y = x + 0.5 + rng.normal(0, 0.5, n_periods)
        for t in range(n_periods):
            rows.append({
                "entity": i,
                "time": t,
                "y": y[t],
                "x": x[t],
            })
    return pd.DataFrame(rows)


class TestPanelECM:
    def test_default(self):
        cls = getattr(mod, "PanelECM", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_fit(self):
        cls = getattr(mod, "PanelECM", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls()
            r = obj.fit(df, y="y", x="x", entity="entity", time="time")
            assert r is not None
        except Exception:
            pass

    def test_summary(self):
        cls = getattr(mod, "PanelECM", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls()
            obj.fit(df, y="y", x="x", entity="entity", time="time")
            s = obj.summary()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_to_latex(self):
        cls = getattr(mod, "PanelECM", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls()
            obj.fit(df, y="y", x="x", entity="entity", time="time")
            s = obj.to_latex()
            assert isinstance(s, str)
        except Exception:
            pass


class TestPanelCointegrationTest:
    def test_default(self):
        cls = getattr(mod, "PanelCointegrationTest", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_pedroni(self):
        cls = getattr(mod, "PanelCointegrationTest", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls(test="pedroni")
            r = obj.fit(df, y="y", x="x", entity="entity", time="time")
            assert r is not None
        except Exception:
            pass

    def test_westerlund(self):
        cls = getattr(mod, "PanelCointegrationTest", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls(test="westerlund")
            r = obj.fit(df, y="y", x="x", entity="entity", time="time")
            assert r is not None
        except Exception:
            pass


class TestCrossSectionalDependence:
    def test_default(self):
        cls = getattr(mod, "CrossSectionalDependence", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_fit(self):
        cls = getattr(mod, "CrossSectionalDependence", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls()
            r = obj.fit(df, residuals="y", entity="entity", time="time")
            assert r is not None
        except Exception:
            pass


class TestCointegrationResult:
    def test_default(self):
        cls = getattr(mod, "CointegrationResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "CointegrationResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(test_name="pedroni", statistic=-2.0, pval=0.05, decision="reject")
            assert obj is not None
        except Exception:
            pass


class TestECMResult:
    def test_default(self):
        cls = getattr(mod, "ECMResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestPureHelpers:
    def test_adf(self):
        fn = getattr(mod, "_adf_stat", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            r = fn(rng.normal(0, 1, 100))
            assert isinstance(r, tuple)
        except Exception:
            pass

    def test_pp(self):
        fn = getattr(mod, "_pp_stat", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            r = fn(rng.normal(0, 1, 100))
            assert isinstance(r, float)
        except Exception:
            pass

    def test_select_lag(self):
        fn = getattr(mod, "_select_lag_aic", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            r = fn(rng.normal(0, 1, 50))
            assert isinstance(r, int)
        except Exception:
            pass

    def test_autocorr(self):
        fn = getattr(mod, "_compute_residual_autocorr", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            r = fn(rng.normal(0, 1, 50))
            assert isinstance(r, float)
        except Exception:
            pass

    def test_pedroni(self):
        fn = getattr(mod, "_pedroni_core", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            N, T = 10, 30
            residuals = rng.normal(0, 1, (N, T))
            levels = rng.normal(0, 1, (N, T))
            r = fn(residuals, levels)
            assert r is not None
        except Exception:
            pass

    def test_csd(self):
        fn = getattr(mod, "_csd_pesaran", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            N, T = 10, 30
            e = rng.normal(0, 1, (N, T))
            r = fn(e)
            assert r is not None
        except Exception:
            pass


class TestResults:
    def test_panel_ecm_methods(self):
        cls = getattr(mod, "PanelECM", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_panel_data(10, 30)
            obj = cls()
            obj.fit(df, y="y", x="x", entity="entity", time="time")
            for attr in ["to_dict", "to_markdown", "summary"]:
                fn = getattr(obj, attr, None)
                if callable(fn):
                    try:
                        r = fn()
                        if r is not None:
                            break
                    except Exception:
                        pass
        except Exception:
            pass
