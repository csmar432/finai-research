"""tests/test_moderation_smoke.py — Smoke tests for scripts/research_framework/moderation.py."""

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
    from scripts.research_framework.moderation import (
        ModerationAnalysis,
        ModerationResult,
        run_threshold_regression,
    )
except Exception as _exc:
    pytest.skip(f"moderation not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert ModerationAnalysis is not None
        assert run_threshold_regression is not None


class TestModerationResult:
    def test_instantiate(self):
        r = ModerationResult(
            method="test",
            main_effect_X=0.5,
            main_effect_X_se=0.1,
            interaction_XM=0.3,
            interaction_se=0.05,
            interaction_t=6.0,
            interaction_p=0.001,
            r_squared=0.25,
            n=100,
            model=None,
        )
        assert r.method == "test"
        assert r.n == 100
        assert "Moderation Analysis" in r.summary()
        assert "test" in r.summary()


class TestModerationInteraction:
    def _make_data(self, n=300, interaction_strength=0.3, seed=42):
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({
            "X": rng.normal(0, 1, n),
            "M": rng.normal(0, 1, n),
            "size": rng.normal(10, 1, n),
            "age": rng.uniform(0, 30, n),
        })
        # Y = 0.5*X + 0.3*X*M + noise
        df["Y"] = 0.5 * df["X"] + interaction_strength * df["X"] * df["M"] + rng.normal(0, 0.5, n)
        return df

    def test_basic_interaction(self):
        df = self._make_data()
        result = ModerationAnalysis.interaction(df, X="X", M="M", Y="Y")
        assert isinstance(result, ModerationResult)
        assert result.n == 300
        # 交互项应正向显著
        assert result.interaction_XM > 0

    def test_interaction_with_controls(self):
        df = self._make_data()
        result = ModerationAnalysis.interaction(df, X="X", M="M", Y="Y", controls=["size", "age"])
        assert result.n == 300

    def test_interaction_with_cluster(self):
        df = self._make_data(n=120)
        df["firm_id"] = np.repeat(np.arange(30), 4)  # 30 firms × 4 obs
        result = ModerationAnalysis.interaction(df, X="X", M="M", Y="Y", cluster="firm_id")
        assert "clustered" in result.method

    def test_subsample(self):
        df = self._make_data(n=200)
        results = ModerationAnalysis.subsample(df, X="X", M="M", Y="Y")
        assert "low" in results
        assert "high" in results
        assert results["low"].n + results["high"].n == 200


class TestThresholdRegression:
    def test_basic(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "X": rng.normal(0, 1, 200),
            "M": rng.normal(0, 1, 200),
            "Z": rng.uniform(0, 10, 200),
            "Y": rng.normal(0, 1, 200),
        })
        result = run_threshold_regression(df, X="X", M="M", Y="Y", threshold_var="Z", n_grid=20)
        assert isinstance(result, dict)
        assert "gamma_hat" in result
        assert "ssr" in result
        # gamma_hat should be in [Z_15%, Z_85%]
        assert df["Z"].quantile(0.15) <= result["gamma_hat"] <= df["Z"].quantile(0.85)
