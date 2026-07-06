"""tests/test_china_carbon_events_smoke.py — Smoke tests for scripts/research_framework/china_carbon_events.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.china_carbon_events import (
        CHINA_NATIONAL_ETS,
        CHINA_PILOT_ETS,
        CarbonETSConfig,
        build_carbon_ets_panel,
        carbon_ets_regression_template,
    )
except Exception as _exc:
    pytest.skip(f"china_carbon_events not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert CarbonETSConfig is not None
        assert build_carbon_ets_panel is not None

    def test_constants_present(self):
        assert isinstance(CHINA_NATIONAL_ETS, dict)
        assert "policy_name" in CHINA_NATIONAL_ETS
        assert "launch_date" in CHINA_NATIONAL_ETS

    def test_pilot_table(self):
        assert isinstance(CHINA_PILOT_ETS, pd.DataFrame)
        assert len(CHINA_PILOT_ETS) > 0
        assert "province_code" in CHINA_PILOT_ETS.columns


class TestCarbonETSConfig:
    def test_default(self):
        cfg = CarbonETSConfig()
        assert cfg.treatment_year == 2021
        assert cfg.use_pilots is False
        assert cfg.cluster_level == "firm"
        assert isinstance(cfg.covariates, list)
        assert len(cfg.covariates) > 0

    def test_custom(self):
        cfg = CarbonETSConfig(treatment_year=2013, use_pilots=True, cluster_level="province")
        assert cfg.treatment_year == 2013
        assert cfg.use_pilots is True
        assert cfg.cluster_level == "province"


class TestBuildPanel:
    def _make_panel(self, n_provinces=10, n_years=5):
        rng_data = []
        for p in range(110000, 110000 + n_provinces * 10000, 10000):
            for y in range(2018, 2018 + n_years):
                rng_data.append({"province_code": p, "year": y, "firm_id": f"F{p}-{y}"})
        return pd.DataFrame(rng_data)

    def test_national_default(self):
        df = self._make_panel(n_provinces=5, n_years=3)
        out = build_carbon_ets_panel(df)
        assert "is_treated" in out.columns
        assert "post" in out.columns
        assert "did" in out.columns
        # 默认 national ETS → 全部省份 treated
        assert out["is_treated"].sum() == len(out)
        # 2021 前 post=0, 2021+ post=1
        assert (out.loc[out["year"] < 2021, "post"] == 0).all()
        assert (out.loc[out["year"] >= 2021, "post"] == 1).all()
        # did = is_treated * post
        assert (out["did"] == out["is_treated"] * out["post"]).all()

    def test_pilot_mode(self):
        df = self._make_panel(n_provinces=8, n_years=5)
        cfg = CarbonETSConfig(use_pilots=True, treatment_year=2014)
        out = build_carbon_ets_panel(df, config=cfg)
        # 试点模式：只有 CHINA_PILOT_ETS 里的省份 treated
        pilot_codes = set(CHINA_PILOT_ETS["province_code"].tolist())
        treated_provinces = set(out.loc[out["is_treated"] == 1, "province_code"].unique())
        assert treated_provinces.issubset(pilot_codes)


class TestRegressionTemplate:
    def test_returns_string(self):
        tmpl = carbon_ets_regression_template()
        assert isinstance(tmpl, str)
        assert "Carbon ETS" in tmpl or "carbon_ets" in tmpl.lower()
        assert "import" in tmpl
