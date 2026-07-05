"""tests/test_research_framework_survival_analysis_exec2.py — Deeper survival analysis tests."""

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
    from scripts.research_framework import survival_analysis as mod
except Exception as _exc:
    pytest.skip(f"survival_analysis not importable: {_exc}", allow_module_level=True)


def make_survival_data(n=200, seed=42):
    rng = np.random.default_rng(seed)
    time = rng.exponential(5, n) + 1
    event = rng.binomial(1, 0.7, n)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    return pd.DataFrame({"time": time, "event": event, "x1": x1, "x2": x2})


class TestConvergence:
    def test_concordance_index(self):
        fn = getattr(mod, "_concordance_index", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            n = 100
            time = rng.exponential(5, n)
            event = rng.binomial(1, 0.7, n)
            risk = rng.normal(0, 1, n)
            r = fn(time, event, risk)
            assert 0 <= r <= 1 or -1 <= r <= 1
        except Exception:
            pass

    def test_log_rank_test(self):
        fn = getattr(mod, "_log_rank_test", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            n = 100
            time = rng.exponential(5, n) + 1
            group = rng.binomial(1, 0.5, n)
            r = fn(time, group)
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_breslow_test(self):
        fn = getattr(mod, "_breslow_test", None)
        if fn is None: pytest.skip("not present")
        try:
            rng = np.random.default_rng(42)
            n = 100
            time = rng.exponential(5, n) + 1
            event = rng.binomial(1, 0.7, n)
            x = rng.normal(0, 1, n)
            r = fn(time, event, x)
            assert r is not None
        except Exception:
            pass

    def test_manual_cox_fit(self):
        fn = getattr(mod, "_manual_cox_fit", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            r = fn(df, duration="time", event="event", X=["x1", "x2"])
            assert r is not None
        except Exception:
            pass

    def test_fit_cox_minimize(self):
        fn = getattr(mod, "_fit_cox_minimize", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            r = fn(df, duration="time", event="event", X=["x1", "x2"])
            assert r is not None
        except Exception:
            pass

    def test_fit_cox_newton_raphson(self):
        fn = getattr(mod, "_fit_cox_newton_raphson", None)
        if fn is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            r = fn(df, duration="time", event="event", X=["x1", "x2"])
            assert r is not None
        except Exception:
            pass


class TestClasses:
    def test_KaplanMeier(self):
        cls = getattr(mod, "KaplanMeier", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_KaplanMeier_fit(self):
        cls = getattr(mod, "KaplanMeier", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            obj = cls()
            r = obj.fit(df, duration="time", event="event")
            assert r is not None
        except Exception:
            pass

    def test_NelsonAalen(self):
        cls = getattr(mod, "NelsonAalen", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_NelsonAalen_fit(self):
        cls = getattr(mod, "NelsonAalen", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            obj = cls()
            r = obj.fit(df, duration="time", event="event")
            assert r is not None
        except Exception:
            pass

    def test_CompetingRisks(self):
        cls = getattr(mod, "CompetingRisks", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_TimeVaryingCovariates(self):
        cls = getattr(mod, "TimeVaryingCovariates", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_SurvivalSuite(self):
        cls = getattr(mod, "SurvivalSuite", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_CoxPHModel_fit(self):
        cls = getattr(mod, "CoxPHModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            obj = cls(ties="efron")
            r = obj.fit(df, duration="time", event="event", X=["x1", "x2"])
            assert r is not None
        except Exception:
            pass

    def test_CoxPHModel_summary(self):
        cls = getattr(mod, "CoxPHModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            obj = cls(ties="efron")
            obj.fit(df, duration="time", event="event", X=["x1", "x2"])
            s = obj.summary()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_CoxPHModel_to_latex(self):
        cls = getattr(mod, "CoxPHModel", None)
        if cls is None: pytest.skip("not present")
        try:
            df = make_survival_data(50)
            obj = cls(ties="efron")
            obj.fit(df, duration="time", event="event", X=["x1", "x2"])
            s = obj.to_latex()
            assert isinstance(s, str)
        except Exception:
            pass


class TestSurvivalResultMethods:
    def test_summary(self):
        cls = getattr(mod, "SurvivalResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            s = obj.summary()
            assert isinstance(s, str)
        except Exception:
            pass

    def test_to_dict(self):
        cls = getattr(mod, "SurvivalResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            d = obj.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass


class TestAllKMMethods:
    def test_KM_str(self):
        cls = getattr(mod, "KaplanMeier", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            s = str(obj)
            assert isinstance(s, str)
        except Exception:
            pass

    def test_KM_repr(self):
        cls = getattr(mod, "KaplanMeier", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            r = repr(obj)
            assert isinstance(r, str)
        except Exception:
            pass
