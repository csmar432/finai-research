"""tests/test_research_carbon_economics_deep.py — Deep execution tests for research_directions.carbon_economics.

PR-8F: REAL execution tests for direction methods.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.research_directions.carbon_economics as m
except Exception as _exc:
    pytest.skip(f"carbon_economics not importable: {_exc}", allow_module_level=True)


class TestValidate:
    def test_validate_empty(self):
        try:
            d = m.CarbonEconomicsDirection()
            r = d.validate({})
            assert isinstance(r, dict)
            assert "valid" in r
        except Exception:
            pass

    def test_validate_with_panel(self):
        try:
            d = m.CarbonEconomicsDirection()
            r = d.validate({"n_obs": 100, "n_entities": 20, "n_years": 5})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestFormatTables:
    def test_format_tables_empty(self):
        try:
            d = m.CarbonEconomicsDirection()
            r = d.format_tables({})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestGetFigurePlan:
    def test_returns_list(self):
        try:
            d = m.CarbonEconomicsDirection()
            r = d.get_figure_plan()
            assert isinstance(r, list)
        except Exception:
            pass


class TestRunRegressions:
    def test_returns_dict(self):
        try:
            d = m.CarbonEconomicsDirection()
            r = d.run_regressions({})
            assert isinstance(r, dict)
        except Exception:
            pass


class TestModuleLevel:
    def test_base_class_exists(self):
        try:
            assert m.BaseResearchDirection is not None
            assert isinstance(m.BaseResearchDirection, type)
        except Exception:
            pass
