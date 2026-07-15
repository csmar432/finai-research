"""Unit tests for scripts/idea_data_checker.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def idc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import idea_data_checker as i
    yield i
    if _p in sys.path:
        sys.path.remove(_p)


class TestFeasibility:
    def test_levels(self, idc):
        assert idc.Feasibility.AVAILABLE in idc.Feasibility
        assert idc.Feasibility.DATA_GAP in idc.Feasibility


class TestGapReason:
    def test_reasons(self, idc):
        assert idc.GapReason.REQUIRES_API_KEY in idc.GapReason
        assert idc.GapReason.REQUIRES_INSTITUTION in idc.GapReason


class TestDataSourceAvailability:
    def test_init(self, idc):
        avail = idc.DataSourceAvailability(
            data_type="daily_quote",
            feasibility=idc.Feasibility.AVAILABLE,
            gap_reason=idc.GapReason.REQUIRES_API_KEY,
            available_sources=["tushare"],
            unavailable_sources=["wind"],
            what_is_missing="No wind data",
            how_to_get="Register Tushare",
            how_to_get_url="https://tushare.pro",
            how_to_get_cost=0.0,
            can_use_synthetic=False,
        )
        assert avail.data_type == "daily_quote"
        assert "tushare" in avail.available_sources
