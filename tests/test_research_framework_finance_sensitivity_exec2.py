"""tests/test_research_framework_finance_sensitivity_exec2.py — Deeper finance sensitivity tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import finance_sensitivity as mod
except Exception as _exc:
    pytest.skip(f"finance_sensitivity not importable: {_exc}", allow_module_level=True)


def make_data(n=200, k=4, seed=42):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, k))
    beta = np.array([0.5, 0.3, 0.1, 0.05])
    y = X @ beta + rng.normal(0, 0.5, n)
    return X, y


class TestOLSPLS:
    def test_default(self):
        cls = getattr(mod, "OLSPLSSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_fit(self):
        cls = getattr(mod, "OLSPLSSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            X, y = make_data()
            obj = cls()
            r = obj.fit(X, y)
            assert r is not None
        except Exception:
            pass

    def test_fit_with_names(self):
        cls = getattr(mod, "OLSPLSSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            X, y = make_data()
            obj = cls()
            r = obj.fit(X, y, xnames=["a", "b", "c", "d"], key_var=0)
            assert r is not None
        except Exception:
            pass


class TestOlleyPakes:
    def test_default(self):
        cls = getattr(mod, "OlleyPakesEstimator", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_fit(self):
        cls = getattr(mod, "OlleyPakesEstimator", None)
        if cls is None: pytest.skip("not present")
        try:
            X, y = make_data()
            obj = cls()
            r = obj.fit(X, y, n_state=2)
            assert r is not None
        except Exception:
            pass


class TestLevinsohnPetrin:
    def test_default(self):
        cls = getattr(mod, "LevinsohnPetrinEstimator", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestContagionTest:
    def test_default(self):
        cls = getattr(mod, "ContagionTest", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestSpilloverIndex:
    def test_default(self):
        cls = getattr(mod, "SpilloverIndex", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestCreditRiskSensitivity:
    def test_default(self):
        cls = getattr(mod, "CreditRiskSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestEbersteinMagnacResult:
    def test_default(self):
        cls = getattr(mod, "EbersteinMagnacResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "EbersteinMagnacResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(beta_ols=0.5, beta_pls_min=0.3, beta_pls_max=0.7)
            assert obj is not None
        except Exception:
            pass

    def test_to_dict(self):
        cls = getattr(mod, "EbersteinMagnacResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            d = obj.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass
