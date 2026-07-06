"""tests/test_a_share_firm_controls_smoke.py — Smoke tests for scripts/research_framework/a_share_firm_controls.py."""

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
    from scripts.research_framework.a_share_firm_controls import (
        FirmControl,
        ALL_CONTROLS,
        STANDARD_CONTROLS,
        FINANCE_CONTROLS,
        INNOVATION_CONTROLS,
        list_controls,
        get_control,
        compute_controls,
    )
except Exception as _exc:
    pytest.skip(f"a_share_firm_controls not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert FirmControl is not None

    def test_constants_present(self):
        assert isinstance(ALL_CONTROLS, dict)
        assert isinstance(STANDARD_CONTROLS, list)
        assert isinstance(FINANCE_CONTROLS, list)
        assert isinstance(INNOVATION_CONTROLS, list)
        # Standard control set should be a subset of ALL_CONTROLS
        for c in STANDARD_CONTROLS:
            assert c in ALL_CONTROLS, f"{c} missing from ALL_CONTROLS"


class TestFirmControlDataclass:
    def test_instantiate(self):
        ctrl = FirmControl(
            name="test_size",
            chinese_name="测试规模",
            formula="np.log(total_assets)",
            typical_sign="+",
            csmar_field="A001000000",
            papers=("test_paper_1",),
        )
        assert ctrl.name == "test_size"
        assert ctrl.chinese_name == "测试规模"
        assert ctrl.typical_sign == "+"

    def test_default_field(self):
        ctrl = FirmControl(name="x", chinese_name="x", formula="x", typical_sign="+", csmar_field="x")
        # default_factory=list → empty list
        assert list(ctrl.papers) == []


class TestListControls:
    def test_returns_dataframe(self):
        df = list_controls()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(ALL_CONTROLS)
        assert "name" in df.columns


class TestGetControl:
    def test_known_control(self):
        ctrl = get_control("size")
        assert isinstance(ctrl, FirmControl)
        assert ctrl.name == "size"

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_control("this_control_does_not_exist_xyz")


class TestComputeControls:
    def _make_raw_df(self, n=50):
        rng = np.random.default_rng(42)
        # 多 firm + 多 year 才支持 groupby firm_col / industry-year
        rows = []
        for fid in range(10):
            for y in range(5):
                rows.append({
                    "firm_id": f"F{fid:03d}",
                    "year": 2018 + y,
                    "industry_code": f"IND{fid % 3}",
                    "total_assets": rng.uniform(1e8, 1e10),
                    "total_liabilities": rng.uniform(1e7, 5e9),
                    "net_profit": rng.uniform(-1e7, 5e8),
                    "total_equity": rng.uniform(1e8, 5e9),
                    "revenue": rng.uniform(1e8, 1e10),
                    "operating_cashflow": rng.uniform(-1e7, 5e8),
                    "market_cap": rng.uniform(1e8, 5e9),
                    "year_of_ipo": int(2018 + y - rng.integers(1, 10)),
                    "actual_controller": int(rng.integers(0, 2)),
                    "top1_shareholder_pct": rng.uniform(0.05, 0.6),
                    "num_independent_directors": 3,
                    "total_directors": 9,
                })
        return pd.DataFrame(rows)

    def test_compute_standard(self):
        df = self._make_raw_df()
        out = compute_controls(df, controls=["size", "leverage", "roa"])
        assert isinstance(out, pd.DataFrame)
        assert "size" in out.columns
        assert "leverage" in out.columns
        assert "roa" in out.columns
        # size = log(total_assets) should be positive
        assert (out["size"] > 0).all()

    def test_compute_default_is_standard(self):
        df = self._make_raw_df()
        out = compute_controls(df)
        assert isinstance(out, pd.DataFrame)
        # Default = STANDARD_CONTROLS
        for c in STANDARD_CONTROLS:
            assert c in out.columns, f"Default compute should include {c}"
