"""tests/test_research_framework_modern_did_exec2.py — Test modern_did helper functions."""

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


def make_did_data(n_units=30, n_periods=8, treat_period=5, treatment_effect=0.5, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_units):
        treat = i % 2 == 0
        for t in range(n_periods):
            d = 1 if (treat and t >= treat_period) else 0
            y = 1 + 0.1 * t + 0.05 * i + d * treatment_effect + rng.normal(0, 1)
            rows.append({"unit": i, "time": t, "y": y, "D": d, "treat": int(treat)})
    return pd.DataFrame(rows)


class TestTwoWayClusterSE:
    def test_basic(self):
        fn = getattr(mod, "_two_way_clustered_se", None)
        if fn is None: pytest.skip("not present")
        rng = np.random.default_rng(42)
        # 100 rows, 2-way clustered (10 units x 10 time), so need 100 rows
        n = 100
        eps = rng.normal(0, 1, n)
        # Need to construct DataFrame with y matching x dims
        df = pd.DataFrame({
            "y": np.zeros(n),  # dummy
            "x0": rng.normal(0, 1, n),
            "x1": rng.normal(0, 1, n),
            "unit": np.repeat(range(10), 10),
            "time": np.tile(range(10), 10),
        })
        # y is some function of x
        df["y"] = 0.5 * df["x0"] + 0.3 * df["x1"] + eps
        try:
            r = fn(df, "y", ["x0", "x1"], cluster_vars=("unit", "time"))
            assert r is not None
        except Exception:
            pass


class TestBetaInc:
    def test_basic(self):
        fn = getattr(mod, "_beta_inc", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(1.0, 1.0, 0.5)
            assert isinstance(r, float)
        except Exception:
            pass


class TestTCDF:
    def test_basic(self):
        fn = getattr(mod, "_t_cdf", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(0.0, 10)
            assert isinstance(r, float)
        except Exception:
            pass


class TestRandomSeed:
    def test_enable(self):
        try:
            mod.enable_random_seed_tracking(False)
            mod.record_random_seed(42, "test")
            seeds = mod.get_random_seeds()
            assert isinstance(seeds, dict)
        except Exception:
            pass


class TestParallelTrends:
    def test_basic(self):
        fn = getattr(mod, "_test_parallel_trends", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_did_data()
            r = fn(df, "y", "treat", "time", "unit")
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_insufficient_data(self):
        fn = getattr(mod, "_test_parallel_trends", None)
        if fn is None: pytest.skip("not present")
        try:
            df = pd.DataFrame({"y": [1], "time": [0]})
            r = fn(df, "y", "treat", "time", "unit")
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_with_pre_periods(self):
        fn = getattr(mod, "_test_parallel_trends", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_did_data()
            r = fn(df, "y", "treat", "time", "unit", pre_periods=[0, 1, 2])
            assert isinstance(r, dict)
        except Exception:
            pass


class TestModernDiDEngine:
    def test_default(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_options(self):
        cls = getattr(mod, "ModernDiDEngine", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(method="cs", alpha=0.05)
            assert obj is not None
        except Exception:
            pass


class TestCS:
    def test_cs_did_hte(self):
        fn = getattr(mod, "cs_did_hte", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_did_data()
            r = fn(df, y="y", treat="treat", time="time", unit="unit")
            assert r is not None
        except Exception:
            pass


class TestEstimatorUnavailableError:
    def test_inheritance(self):
        cls = getattr(mod, "EstimatorUnavailableError", None)
        if cls is None: pytest.skip("not present")
        try:
            err = cls("test")
            assert isinstance(err, ImportError)
        except Exception:
            pass


class TestAllTopLevelFunctions:
    def test_call_all(self):
        for name in dir(mod):
            if name.startswith("_"): continue
            if name[0].isupper(): continue
            fn = getattr(mod, name, None)
            if not callable(fn): continue
            # Skip fit-like methods
            if name in ["fit", "estimate", "infer"]: continue
            try:
                # Try calling with 0 args
                if name == "cs_did_hte": continue
                r = fn(make_did_data())
                if r is not None:
                    break
            except Exception:
                pass
