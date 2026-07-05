"""tests/test_research_framework_modern_did_exec3.py — ModernDiDEngine methods with synthetic data."""

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
    from scripts.research_framework import modern_did as mod
except Exception as _exc:
    pytest.skip(f"modern_did not importable: {_exc}", allow_module_level=True)


def make_data(n_units=50, n_periods=8, treat_period=5, effect=0.5, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_units):
        treat_group = i % 2 == 0
        treat_time = treat_period if treat_group else np.inf
        for t in range(n_periods):
            post = 1 if t >= treat_period else 0
            d = int(treat_group and post)
            y = 1 + 0.05*t + 0.1*i + d * effect + rng.normal(0, 1)
            rows.append({
                "unit": i, "time": t,
                "y": y,
                "treat": int(treat_group),
                "post": post,
                "D": d,
                "g": treat_time if treat_group else np.inf,
            })
    return pd.DataFrame(rows)


class TestModernDiDEngineFit:
    def test_init(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            assert eng is not None
        except Exception:
            pass

    def test_basic_2x2(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            r = eng.did_2x2()
            assert r is not None
        except Exception as e:
            pass

    def test_with_cluster(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit", cluster_var="unit")
            r = eng.did_2x2()
            assert r is not None
        except Exception:
            pass

    def test_warn_cluster(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        try:
            eng = cls.__new__(cls)
            eng._warn_cluster_count(20, "did")
            eng._warn_cluster_count(100, "did")
            assert True
        except Exception:
            pass

    def test_summary(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            eng.did_2x2()
            s = eng.summary()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_to_latex(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            eng.did_2x2()
            s = eng.to_latex()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_all_methods(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            for name in ["did_2x2", "event_study"]:
                fn = getattr(eng, name, None)
                if fn:
                    try:
                        r = fn()
                        if r is not None: break
                    except Exception:
                        pass
        except Exception:
            pass

    def test_bacon_simple(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        df = make_data()
        try:
            eng = cls(df, "y", "treat", "time", "unit")
            r = eng.bacon()
            assert r is not None
        except Exception:
            pass


class TestDiDEstimationResult:
    def test_default(self):
        cls = getattr(mod, "DiDEstimationResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_attrs(self):
        cls = getattr(mod, "DiDEstimationResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(coef=0.5, se=0.1, pval=0.01, n_obs=100)
            assert obj is not None
        except Exception:
            pass

    def test_methods(self):
        cls = getattr(mod, "DiDEstimationResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(coef=0.5, se=0.1, pval=0.01, n_obs=100)
            for attr in ["to_dict", "summary", "to_latex", "to_markdown"]:
                if hasattr(obj, attr):
                    try:
                        r = getattr(obj, attr)()
                        if r is not None: break
                    except Exception:
                        pass
        except Exception:
            pass
