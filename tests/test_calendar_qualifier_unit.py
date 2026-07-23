"""Unit tests for scripts/research_framework/calendar_qualifier.py."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def cq():
    sys.path.insert(0, str(SCRIPTS_DIR))
    from research_framework import calendar_qualifier as c
    yield c
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestCnHolidays:
    def test_returns_set(self, cq):
        holidays = cq._cn_holidays()
        assert isinstance(holidays, set)
        assert len(holidays) > 0

    def test_contains_known_holidays(self, cq):
        holidays = cq._cn_holidays()
        assert date(2020, 1, 1) in holidays
        assert date(2020, 10, 1) in holidays

    def test_spring_festival_included(self, cq):
        holidays = cq._cn_holidays()
        assert date(2020, 1, 24) in holidays
        assert date(2021, 2, 11) in holidays

    def test_returns_same_set_on_repeat_call(self, cq):
        s1 = cq._cn_holidays()
        s2 = cq._cn_holidays()
        assert s1 is s2  # Should return same cached object

    def test_contains_national_day_week(self, cq):
        holidays = cq._cn_holidays()
        for d in range(1, 8):
            assert date(2023, 10, d) in holidays


class TestCalendarQualification:
    def test_dataclass_fields(self, cq):
        q = cq.CalendarQualification(
            firm="AAPL", event_date=datetime(2020, 1, 1), qualified=True, reason="ok"
        )
        assert q.firm == "AAPL"
        assert q.qualified is True
        assert q.reason == "ok"


class TestQualifyFirmEvents:
    def test_regular_trading_day_qualified(self, cq):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "event_date": pd.to_datetime(["2020-03-15"]),
            "ret": [0.01],
        })
        result = cq.qualify_firm_events(df)
        assert bool(result.iloc[0]["qualified"]) is True

    def test_holiday_disqualified(self, cq):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "event_date": pd.to_datetime(["2020-01-01"]),
            "ret": [0.01],
        })
        result = cq.qualify_firm_events(df)
        assert bool(result.iloc[0]["qualified"]) is False
        assert "holiday" in str(result.iloc[0]["disqualify_reason"])

    def test_string_date_parsed(self, cq):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "event_date": ["2020-03-15"],
            "ret": [0.01],
        })
        result = cq.qualify_firm_events(df)
        assert bool(result.iloc[0]["qualified"]) is True

    def test_multiple_rows(self, cq):
        df = pd.DataFrame({
            "ticker": ["AAPL", "MSFT", "GOOG"],
            "event_date": pd.to_datetime(["2020-01-01", "2020-03-15", "2020-10-08"]),
            "ret": [0.01, 0.02, 0.03],
        })
        result = cq.qualify_firm_events(df)
        assert len(result) == 3
        assert bool(result.iloc[0]["qualified"]) is False  # Jan 1 holiday
        assert bool(result.iloc[1]["qualified"]) is True   # Mar 15 trading
        assert bool(result.iloc[2]["qualified"]) is True  # Oct 8 trading

    def test_custom_holidays(self, cq):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "event_date": pd.to_datetime(["2020-03-15"]),
            "ret": [0.01],
        })
        custom_holidays = {date(2020, 3, 15)}
        result = cq.qualify_firm_events(df, holidays=custom_holidays)
        assert bool(result.iloc[0]["qualified"]) is False

    def test_custom_columns(self, cq):
        df = pd.DataFrame({
            "company": ["AAPL"],
            "event_dt": pd.to_datetime(["2020-03-15"]),
            "return": [0.01],
        })
        result = cq.qualify_firm_events(df, firm_col="company", date_col="event_dt")
        assert len(result) == 1


class TestAggregateQualifications:
    def test_empty_df(self, cq):
        df = pd.DataFrame({
            "firm": [],
            "event_date": pd.to_datetime([]),
            "qualified": pd.Series([], dtype=bool),
            "disqualify_reason": pd.Series([], dtype="string"),
        })
        result = cq.aggregate_qualifications(df)
        assert result["n_total"] == 0
        assert result["n_qualified"] == 0
        assert result["n_disqualified"] == 0

    def test_all_qualified(self, cq):
        df = pd.DataFrame({
            "firm": ["A", "B"],
            "event_date": pd.to_datetime(["2020-03-15", "2020-04-15"]),
            "qualified": pd.Series([True, True]),
            "disqualify_reason": pd.Series(["", ""], dtype="string"),
        })
        result = cq.aggregate_qualifications(df)
        assert result["n_total"] == 2
        assert result["n_qualified"] == 2
        assert result["n_disqualified"] == 0

    def test_counts_disqualified(self, cq):
        df = pd.DataFrame({
            "firm": ["A", "B", "C"],
            "event_date": pd.to_datetime(["2020-01-01", "2020-03-15", "2020-10-01"]),
            "qualified": pd.Series([False, True, False]),
            "disqualify_reason": pd.Series(
                ["holiday_on_event_day", "", "holiday_on_event_day"], dtype="string"
            ),
        })
        result = cq.aggregate_qualifications(df)
        assert result["n_total"] == 3
        assert result["n_qualified"] == 1
        assert result["n_disqualified"] == 2
        assert "holiday_on_event_day" in result["disqualify_reasons"]

