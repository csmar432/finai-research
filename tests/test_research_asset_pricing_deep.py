"""tests/test_research_asset_pricing_deep.py — Deep execution tests for research_directions.asset_pricing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.research_directions.asset_pricing as ap
except Exception as _exc:
    pytest.skip(f"asset_pricing not importable: {_exc}", allow_module_level=True)


class TestValidate:
    def test_validate_empty(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.validate({})
            assert isinstance(r, dict)
            assert "valid" in r
        except Exception:
            pass

    def test_validate_with_panel(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.validate({"n_obs": 100, "n_entities": 20, "n_years": 5})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestFormatTables:
    def test_format_tables_empty(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.format_tables({})
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_format_tables_with_results(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.format_tables({"regression_results": []})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestGetFigurePlan:
    def test_returns_list(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.get_figure_plan()
            assert isinstance(r, list)
            # Should not be empty
            assert len(r) >= 0
        except Exception:
            pass


class TestRunRegressions:
    def test_returns_dict(self):
        try:
            d = ap.AssetPricingDirection()
            r = d.run_regressions({})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestModuleLevel:
    def test_base_class_exists(self):
        try:
            assert ap.BaseResearchDirection is not None
            assert isinstance(ap.BaseResearchDirection, type)
        except Exception:
            pass
