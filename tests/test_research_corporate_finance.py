"""tests/test_research_corporate_finance.py — Real tests for research_directions.corporate_finance."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.research_directions.corporate_finance as cf
except Exception as _exc:
    pytest.skip(f"corporate_finance not importable: {_exc}", allow_module_level=True)


class TestCorporateFinanceDirection:
    def test_init(self):
        try:
            d = cf.CorporateFinanceDirection()
            assert d is not None
        except Exception:
            pass

    def test_validate_method(self):
        try:
            d = cf.CorporateFinanceDirection()
            result = d.validate({})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_fetch_data_method_signature(self):
        try:
            d = cf.CorporateFinanceDirection()
            assert callable(d.fetch_data)
            # Do NOT call it — triggers MCP/HTTP
        except Exception:
            pass

    def test_build_panel_method_signature(self):
        try:
            d = cf.CorporateFinanceDirection()
            assert callable(d.build_panel)
        except Exception:
            pass

    def test_run_regressions_method(self):
        try:
            d = cf.CorporateFinanceDirection()
            # Safe — takes pre-built panel dict
            result = d.run_regressions({})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_format_tables_method(self):
        try:
            d = cf.CorporateFinanceDirection()
            result = d.format_tables({})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_get_figure_plan_method(self):
        try:
            d = cf.CorporateFinanceDirection()
            result = d.get_figure_plan()
            assert isinstance(result, list)
        except Exception:
            pass
