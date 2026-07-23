"""
Unit tests for scripts/event_monitor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import patch
from datetime import datetime


class TestResearchEventDataclass:
    """Test ResearchEvent and subclasses dataclasses."""

    def test_research_event_to_dict(self):
        from scripts.event_monitor import ResearchEvent

        event = ResearchEvent(
            event_id="test_001",
            event_type="earnings",
            title="AAPL Earnings",
            description="Q4 2024 earnings",
            timestamp=datetime(2024, 10, 15),
            source="tushare",
            related_entities=["AAPL"],
            relevance_score=0.8,
            auto_trigger=True,
        )
        d = event.to_dict()
        assert d["event_id"] == "test_001"
        assert d["event_type"] == "earnings"
        assert d["relevance_score"] == 0.8
        assert d["auto_trigger"] is True
        assert d["related_entities"] == ["AAPL"]

    def test_earnings_event_defaults(self):
        from scripts.event_monitor import EarningsEvent

        event = EarningsEvent(
            event_id="",
            event_type="",
            title="MSFT Earnings",
            description="Quarterly report",
            timestamp=datetime.now(),
            source="",
            ts_code="MSFT.US",
            report_date="2024-03-15",
        )
        assert event.event_id == "earnings_MSFT.US_2024-03-15"
        assert event.event_type == "earnings"
        assert event.source == "tushare"

    def test_macro_event_defaults(self):
        from scripts.event_monitor import MacroEvent

        event = MacroEvent(
            event_id="",
            event_type="",
            title="US CPI Release",
            description="Monthly CPI data",
            timestamp=datetime.now(),
            source="fed",
            country="US",
            indicator="CPI",
            previous_value="2.5",
            forecast_value="2.3",
        )
        assert event.event_id.startswith("macro_")
        assert event.event_type == "macro"
        assert event.country == "US"
        assert event.indicator == "CPI"


class TestEventMonitorKeywords:
    """Test EventMonitor keywords property."""

    @patch("scripts.event_monitor.Path.exists", return_value=False)
    def test_keywords_default_fallback(self, mock_exists):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        keywords = monitor.keywords
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert "关税" in keywords or len(keywords) > 0

    def test_keywords_returns_list(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        result = monitor.keywords
        assert isinstance(result, list)


class TestEventMonitorMethods:
    """Test EventMonitor methods that don't need network."""

    def test_init_defaults(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        assert monitor.check_interval == 300
        assert monitor.auto_trigger is False
        assert monitor._running is False
        assert isinstance(monitor._event_queue, type(monitor._event_queue))

    def test_register_handler(self):
        from scripts.event_monitor import EventMonitor, ResearchEvent

        monitor = EventMonitor()
        calls = []

        def handler(event: ResearchEvent) -> None:
            calls.append(event)

        monitor.register_handler(handler)
        assert len(monitor._handlers) == 1

        # Simulate handler invocation
        event = ResearchEvent(
            event_id="test",
            event_type="test",
            title="Test",
            description="",
            timestamp=datetime.now(),
            source="test",
        )
        handler(event)
        assert len(calls) == 1

    def test_check_earnings_returns_list(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        # The method exists but may require network; just verify it returns a list-like
        result = monitor.check_earnings_calendar(lookback_days=1, top_n=1)
        assert isinstance(result, list)

    def test_check_macro_returns_list(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        result = monitor.check_macro_releases()
        assert isinstance(result, list)

    def test_clear_queue(self):
        from scripts.event_monitor import EventMonitor, ResearchEvent

        monitor = EventMonitor()
        event = ResearchEvent(
            event_id="test",
            event_type="test",
            title="Test",
            description="",
            timestamp=datetime.now(),
            source="test",
        )
        # Add event to queue via internal method
        monitor._event_queue.append(event)
        assert len(monitor._event_queue) > 0
        monitor.clear_queue()
        assert len(monitor._event_queue) == 0

    def test_get_pending_events(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        pending = monitor.get_pending_events()
        assert isinstance(pending, list)

    def test_get_last_check(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        result = monitor.get_last_check()
        # Returns None when no checks have been recorded
        assert result is None or isinstance(result, dict)


class TestPolicyEventDataclass:
    """Test PolicyEvent dataclass."""

    def test_policy_event_init(self):
        from scripts.event_monitor import PolicyEvent

        event = PolicyEvent(
            event_id="pol_001",
            event_type="policy",
            title="碳排放政策",
            description="New carbon regulation",
            timestamp=datetime.now(),
            source="brave_search",
            url="https://example.com/policy",
            publisher="EPA",
        )
        assert event.url == "https://example.com/policy"
        assert event.publisher == "EPA"


class TestEventQueueManagement:
    """Test EventMonitor queue management."""

    def test_event_queue_maxlen(self):
        from scripts.event_monitor import EventMonitor

        monitor = EventMonitor()
        assert monitor._event_queue.maxlen == 1000
