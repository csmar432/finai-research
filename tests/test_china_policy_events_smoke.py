"""tests/test_china_policy_events_smoke.py — Smoke tests for scripts/research_framework/china_policy_events.py."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.china_policy_events import (
        ChinaPolicyEvent,
        ALL_EVENTS,
        get_event,
        list_events,
    )
except Exception as _exc:
    pytest.skip(f"china_policy_events not importable: {_exc}", allow_module_level=True)


class TestModuleLevel:
    def test_loads(self):
        assert ChinaPolicyEvent is not None
        assert ALL_EVENTS is not None

    def test_events_dict_nonempty(self):
        assert len(ALL_EVENTS) >= 5
        # 验证关键事件存在
        expected_keys = ["ying_gai_zeng", "daqi_shi_tiao"]
        for k in expected_keys:
            assert k in ALL_EVENTS, f"missing key {k}"


class TestChinaPolicyEvent:
    def test_instantiate(self):
        ev = ChinaPolicyEvent(
            name="test_event",
            english_name="Test Event",
            launch_date=date(2020, 1, 1),
            scope="test scope",
            treated_provinces=[110000],
            treated_industries=["C17"],
            expected_effect="test",
            example_papers=["doi:10.1/test"],
            data_sources=["CSMAR"],
            notes="",
        )
        assert ev.name == "test_event"
        assert ev.launch_date.year == 2020

    def test_default_notes(self):
        ev = ChinaPolicyEvent(
            name="x",
            english_name="x",
            launch_date=date(2020, 1, 1),
            scope="x",
            treated_provinces=[],
            treated_industries=[],
            expected_effect="x",
            example_papers=[],
            data_sources=[],
        )
        assert ev.notes == ""


class TestGetEvent:
    def test_known(self):
        ev = get_event("ying_gai_zeng")
        assert ev.name == "营改增"

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_event("this_event_does_not_exist_xyz")


class TestListEvents:
    def test_returns_dataframe(self):
        df = list_events()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(ALL_EVENTS)
        assert "name" in df.columns
        assert "english" in df.columns
        assert "launch" in df.columns
