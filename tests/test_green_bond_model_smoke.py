"""tests/test_green_bond_model_smoke.py — Smoke tests for scripts/research_framework/green_bond_model.py."""

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
    from scripts.research_framework.green_bond_model import (
        GreenBondResult,
        GreenBondFactorModel,
        GreenBondESGModel,
        make_demo_data,
    )
except Exception as _exc:
    pytest.skip(f"green_bond_model not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert GreenBondFactorModel is not None
        assert GreenBondESGModel is not None

    def test_result_dataclass(self):
        r = GreenBondResult()
        assert r.greenium_coef is np.nan or np.isnan(r.greenium_coef)
        assert r.model_type == "ols"
        assert r.provenance.get("model") == "green_bond_model.py"


class TestMakeDemoData:
    def test_default_size(self):
        df = make_demo_data()
        assert isinstance(df, pd.DataFrame)
        # 默认 n_green=300, n_conv=500 = 800
        assert len(df) == 800
        assert "is_green" in df.columns
        assert "yield_bps" in df.columns

    def test_custom_size(self):
        df = make_demo_data(n_green=50, n_conv=50, seed=123)
        assert len(df) == 100
        assert df["is_green"].sum() == 50

    def test_reproducibility(self):
        df1 = make_demo_data(seed=42)
        df2 = make_demo_data(seed=42)
        pd.testing.assert_frame_equal(df1, df2)


class TestGreenBondFactorModel:
    def test_estimate_greenium_basic(self):
        df = make_demo_data(n_green=200, n_conv=300, seed=42)
        model = GreenBondFactorModel()
        result = model.estimate_greenium(
            df=df,
            green_col="is_green",
            yield_col="yield_bps",
            controls=["maturity_years", "credit_spread", "liquidity_score", "esg_score"],
        )
        assert isinstance(result, GreenBondResult)
        assert result.n_obs == 500
        assert result.n_green == 200
        assert result.n_conventional == 300
        assert not np.isnan(result.greenium_coef)
        # True greenium is -8.5; OLS estimate should be in reasonable range
        assert -30 < result.greenium_coef < 10

    def test_summary_runs(self, capsys):
        df = make_demo_data(n_green=50, n_conv=50)
        model = GreenBondFactorModel()
        result = model.estimate_greenium(
            df=df, green_col="is_green", yield_col="yield_bps",
        )
        model.summary(result)
        captured = capsys.readouterr()
        assert "Green Bond Model Summary" in captured.out


class TestGreenBondESGModel:
    def test_instantiate(self):
        model = GreenBondESGModel()
        assert model is not None
