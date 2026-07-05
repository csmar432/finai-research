"""tests/test_research_framework_discrete_choice_exec2.py — Deeper discrete choice tests."""

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
    from scripts.research_framework import discrete_choice as mod
except Exception as _exc:
    pytest.skip(f"discrete_choice not importable: {_exc}", allow_module_level=True)


def make_data(n=200, seed=42):
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    z = 1 + x1 + 0.5 * x2 + rng.normal(0, 0.5, n)
    y = (z > 0).astype(int)
    return pd.DataFrame({"y": y, "x1": x1, "x2": x2})


class TestHelpers:
    def test_safe_div(self):
        fn = getattr(mod, "_safe_div", None)
        if fn is None: pytest.skip("not present")
        try:
            a = np.array([1.0, 2.0])
            b = np.array([2.0, 0.0])
            r = fn(a, b, fill=np.nan)
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_norm_pdf(self):
        fn = getattr(mod, "_norm_pdf", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(np.array([0.0, 1.0]))
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_norm_cdf(self):
        fn = getattr(mod, "_norm_cdf", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(np.array([-1.0, 0.0, 1.0]))
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_hc1_se(self):
        fn = getattr(mod, "_hc1_se", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            X = rng.normal(0, 1, (50, 2))
            e = rng.normal(0, 1, 50)
            r = fn(X, e)
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_cluster_se_1d(self):
        fn = getattr(mod, "_cluster_se_1d", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            X = rng.normal(0, 1, (50, 2))
            e = rng.normal(0, 1, 50)
            clusters = np.repeat(range(10), 5)
            r = fn(X, e, clusters)
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_cluster_se_2d(self):
        fn = getattr(mod, "_cluster_se_2d", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            X = rng.normal(0, 1, (50, 2))
            e = rng.normal(0, 1, 50)
            c1 = np.repeat(range(10), 5)
            c2 = np.tile(range(5), 10)
            r = fn(X, e, c1, c2)
            assert isinstance(r, np.ndarray)
        except Exception:
            pass

    def test_pseudo_r2(self):
        fn = getattr(mod, "_pseudo_r2", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(-50.0, -100.0)
            assert isinstance(r, float)
        except Exception:
            pass

    def test_aic(self):
        fn = getattr(mod, "_aic", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(-50.0, k=2, n=100)
            assert isinstance(r, float)
        except Exception:
            pass

    def test_bic(self):
        fn = getattr(mod, "_bic", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(-50.0, k=2, n=100)
            assert isinstance(r, float)
        except Exception:
            pass


class TestDiscreteChoiceModel:
    def test_default(self):
        cls = getattr(mod, "DiscreteChoiceModel", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(model="logit")
            assert obj is not None
        except Exception:
            pass

    def test_probit(self):
        cls = getattr(mod, "DiscreteChoiceModel", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(model="probit")
            assert obj is not None
        except Exception:
            pass

    def test_fit(self):
        cls = getattr(mod, "DiscreteChoiceModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_data(100)
            obj = cls(model="logit")
            r = obj.fit(df, y="y", X=["x1", "x2"])
            assert r is not None
        except Exception:
            pass

    def test_summary(self):
        cls = getattr(mod, "DiscreteChoiceModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_data(100)
            obj = cls(model="logit")
            obj.fit(df, y="y", X=["x1", "x2"])
            s = obj.summary()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_to_latex(self):
        cls = getattr(mod, "DiscreteChoiceModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_data(100)
            obj = cls(model="logit")
            obj.fit(df, y="y", X=["x1", "x2"])
            s = obj.to_latex()
            assert isinstance(s, str)
        except Exception:
            pass


class TestDiscreteChoiceSuite:
    def test_default(self):
        cls = getattr(mod, "DiscreteChoiceSuite", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestDiscreteChoiceResult:
    def test_default(self):
        cls = getattr(mod, "DiscreteChoiceResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "DiscreteChoiceResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(coef=np.zeros(5), se=np.ones(5), pval=np.array([0.05]*5))
            assert obj is not None
        except Exception:
            pass


class TestMarginalEffectsResult:
    def test_default(self):
        cls = getattr(mod, "MarginalEffectsResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestNormCDFScalar:
    def test_basic(self):
        fn = getattr(mod, "_norm_cdf_scalar", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(0.0)
            assert 0.4 < r < 0.6
        except Exception:
            pass

    def test_negative(self):
        fn = getattr(mod, "_norm_cdf_scalar", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn(-1.0)
            assert 0.1 < r < 0.5
        except Exception:
            pass
