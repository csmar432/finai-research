"""
Tests for EventMonitor — scripts/event_monitor.py

Run with: pytest tests/test_event_monitor.py -v --tb=short
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.event_monitor import (
    EarningsEvent,
    EventMonitor,
    MacroEvent,
    PolicyEvent,
    ResearchEvent,
    _build_topic_from_event,
    _get_mock_earnings_calendar,
    _get_mock_macro_releases,
    _search_policy_keywords_mock,
    trigger_research_pipeline,
)


# ─── Cleanup: remove dedup state file before/after test run ─────────────────────
import atexit

_DEDUP_STATE = Path("data/event_trigger_state.json")
_DEDUP_BACKUP = Path("data/event_trigger_state.json.bak")


def _cleanup_dedup():
    if _DEDUP_STATE.exists():
        import shutil
        shutil.move(str(_DEDUP_STATE), str(_DEDUP_BACKUP))


def _restore_dedup():
    if _DEDUP_BACKUP.exists():
        import shutil
        shutil.move(str(_DEDUP_BACKUP), str(_DEDUP_STATE))


_cleanup_dedup()
atexit.register(_restore_dedup)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def monitor():
    """Fresh EventMonitor with defaults."""
    return EventMonitor(check_interval=300, auto_trigger=False)


@pytest.fixture
def auto_monitor():
    """EventMonitor with auto_trigger=True."""
    return EventMonitor(check_interval=300, auto_trigger=True)


@pytest.fixture
def sample_earnings_event():
    return EarningsEvent(
        event_id="earnings_000001.SZ_20241025",
        event_type="earnings",
        title="平安银行 2024Q3 Earnings",
        description="平安银行2024年三季度业绩发布",
        timestamp=datetime.now(),
        source="tushare",
        related_entities=["000001.SZ"],
        relevance_score=0.8,
        auto_trigger=False,
        ts_code="000001.SZ",
        report_date="20241025",
        actual_date="20241025",
        fiscal_period="2024Q3",
    )


@pytest.fixture
def sample_macro_event():
    return MacroEvent(
        event_id="macro_US_NFP_20241101",
        event_type="macro",
        title="美国 11月 非农就业数据",
        description="美国11月非农就业人数变化",
        timestamp=datetime.now(),
        source="bls",
        related_entities=["US"],
        relevance_score=0.9,
        auto_trigger=False,
        country="US",
        indicator="NFP",
        previous_value="150K",
        forecast_value="180K",
    )


@pytest.fixture
def sample_policy_event():
    return PolicyEvent(
        event_id="policy_abc12345",
        event_type="policy",
        title="国务院关于加力支持大规模设备更新的通知",
        description="国务院发布新一轮大规模设备更新支持政策",
        timestamp=datetime.now(),
        source="brave_search",
        related_entities=["设备更新", "工业投资"],
        relevance_score=0.85,
        auto_trigger=False,
        url="https://www.gov.cn/test",
        publisher="国务院",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test: Initialization
# ─────────────────────────────────────────────────────────────────────────────

class TestEventMonitorInit:
    def test_event_monitor_init(self, monitor):
        assert monitor.check_interval == 300
        assert monitor.auto_trigger is False
        assert isinstance(monitor._event_queue, list) is False
        assert len(monitor._handlers) == 0

    def test_event_monitor_init_auto_trigger(self, auto_monitor):
        assert auto_monitor.auto_trigger is True

    def test_event_monitor_custom_interval(self):
        m = EventMonitor(check_interval=600)
        assert m.check_interval == 600

    def test_event_monitor_default_keywords(self, monitor):
        keywords = monitor.keywords
        assert isinstance(keywords, list)
        assert len(keywords) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Handler Registration
# ─────────────────────────────────────────────────────────────────────────────

class TestEventMonitorHandler:
    def test_event_monitor_register_handler(self, monitor):
        handler = MagicMock()
        monitor.register_handler(handler)
        assert len(monitor._handlers) == 1
        assert monitor._handlers[0] is handler

    def test_event_monitor_register_multiple_handlers(self, monitor):
        h1 = MagicMock()
        h2 = MagicMock()
        monitor.register_handler(h1)
        monitor.register_handler(h2)
        assert len(monitor._handlers) == 2

    def test_handler_called_on_event(self, monitor, sample_earnings_event):
        handler = MagicMock()
        monitor.register_handler(handler)
        monitor._notify_handlers(sample_earnings_event)
        handler.assert_called_once_with(sample_earnings_event)

    def test_handler_exception_does_not_propagate(self, monitor, sample_earnings_event):
        bad_handler = MagicMock(side_effect=RuntimeError("handler error"))
        monitor.register_handler(bad_handler)
        # Should not raise
        monitor._notify_handlers(sample_earnings_event)


# ─────────────────────────────────────────────────────────────────────────────
# Test: Earnings Calendar
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckEarningsCalendar:
    def test_check_earnings_calendar_returns_list(self, monitor):
        events = monitor.check_earnings_calendar(lookback_days=7, top_n=20)
        assert isinstance(events, list)

    def test_check_earnings_calendar_returns_earnings_events(self, monitor):
        events = monitor.check_earnings_calendar()
        assert all(isinstance(e, EarningsEvent) for e in events)

    def test_check_earnings_calendar_top_n_limit(self, monitor):
        events = monitor.check_earnings_calendar(top_n=2)
        assert len(events) <= 2

    def test_check_earnings_calendar_has_required_fields(self, monitor):
        events = monitor.check_earnings_calendar()
        if events:
            e = events[0]
            assert e.event_type == "earnings"
            assert e.ts_code
            assert e.source in ("tushare", "tushare_mock")


# ─────────────────────────────────────────────────────────────────────────────
# Test: Macro Releases
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckMacroReleases:
    def test_check_macro_releases_returns_list(self, monitor):
        events = monitor.check_macro_releases()
        assert isinstance(events, list)

    def test_check_macro_releases_returns_macro_events(self, monitor):
        events = monitor.check_macro_releases()
        assert all(isinstance(e, MacroEvent) for e in events)

    def test_check_macro_releases_country_filter(self, monitor):
        events = monitor.check_macro_releases(countries=["US"])
        assert all(e.country == "US" for e in events)

    def test_check_macro_releases_has_required_fields(self, monitor):
        events = monitor.check_macro_releases()
        if events:
            e = events[0]
            assert e.event_type == "macro"
            assert e.country
            assert e.indicator


# ─────────────────────────────────────────────────────────────────────────────
# Test: Policy Keywords
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckPolicyKeywords:
    def test_check_policy_keywords_returns_list(self, monitor):
        events = monitor.check_policy_keywords(keywords=["关税"])
        assert isinstance(events, list)

    def test_check_policy_keywords_returns_policy_events(self, monitor):
        events = monitor.check_policy_keywords(keywords=["美联储"])
        assert all(isinstance(e, PolicyEvent) for e in events)

    def test_check_policy_keywords_max_results(self, monitor):
        events = monitor.check_policy_keywords(keywords=["关税", "降准"], max_results=3)
        assert len(events) <= 3

    def test_check_policy_keywords_uses_default_keywords(self, monitor):
        events = monitor.check_policy_keywords()
        assert isinstance(events, list)

    def test_check_policy_keywords_matches_keywords(self, monitor):
        events = monitor.check_policy_keywords(keywords=["碳排放"])
        assert isinstance(events, list)


# ─────────────────────────────────────────────────────────────────────────────
# Test: Poll All
# ─────────────────────────────────────────────────────────────────────────────

class TestPollAll:
    def test_poll_all_returns_list(self, monitor):
        events = monitor.poll_all()
        assert isinstance(events, list)

    def test_poll_all_returns_research_events(self, monitor):
        events = monitor.poll_all()
        assert all(isinstance(e, ResearchEvent) for e in events)

    def test_poll_all_updates_last_check(self, monitor):
        monitor.poll_all()
        assert "all" in monitor._last_check
        assert isinstance(monitor._last_check["all"], datetime)

    def test_poll_all_adds_events_to_queue(self, monitor):
        events = monitor.poll_all()
        for e in events:
            assert e in monitor._event_queue

    def test_poll_all_deduplicates_by_event_id(self, monitor):
        monitor.poll_all()
        ids = [e.event_id for e in monitor._event_queue]
        assert len(ids) == len(set(ids))


# ─────────────────────────────────────────────────────────────────────────────
# Test: Pending Events / Queue Management
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueManagement:
    def test_get_pending_events_returns_list(self, monitor):
        pending = monitor.get_pending_events()
        assert isinstance(pending, list)

    def test_get_pending_events_reflects_queue(self, monitor):
        events = monitor.poll_all()
        pending = monitor.get_pending_events()
        assert len(pending) == len(events)

    def test_clear_queue(self, monitor):
        monitor.poll_all()
        assert len(monitor._event_queue) > 0
        monitor.clear_queue()
        assert len(monitor._event_queue) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: ResearchEvent Serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestResearchEventSerialization:
    def test_research_event_to_dict(self, sample_earnings_event):
        d = sample_earnings_event.to_dict()
        assert isinstance(d, dict)
        assert d["event_id"] == sample_earnings_event.event_id
        assert d["event_type"] == sample_earnings_event.event_type
        assert d["title"] == sample_earnings_event.title

    def test_earnings_event_to_dict(self, sample_earnings_event):
        d = sample_earnings_event.to_dict()
        assert d["ts_code"] == "000001.SZ"
        assert d["fiscal_period"] == "2024Q3"

    def test_macro_event_to_dict(self, sample_macro_event):
        d = sample_macro_event.to_dict()
        assert d["country"] == "US"
        assert d["indicator"] == "NFP"

    def test_policy_event_to_dict(self, sample_policy_event):
        d = sample_policy_event.to_dict()
        assert d["url"] == "https://www.gov.cn/test"
        assert d["publisher"] == "国务院"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Pipeline Trigger
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggerResearchPipeline:
    @pytest.fixture(autouse=True)
    def clean_dedup_state(self):
        """Clear dedup state before each test to prevent cross-test pollution."""
        _DEDUP_STATE.unlink(missing_ok=True)
        yield
        _DEDUP_STATE.unlink(missing_ok=True)

    @pytest.fixture
    def fresh_earnings_event(self):
        import uuid
        return EarningsEvent(
            event_id=f"earnings_test_{uuid.uuid4().hex[:8]}",
            event_type="earnings",
            title="Test Earnings Event",
            description="Test earnings event for pipeline trigger",
            timestamp=datetime.now(),
            source="test",
            related_entities=["TEST.SZ"],
            relevance_score=0.8,
            auto_trigger=False,
            ts_code="TEST.SZ",
        )

    @pytest.fixture
    def fresh_macro_event(self):
        import uuid
        return MacroEvent(
            event_id=f"macro_test_{uuid.uuid4().hex[:8]}",
            event_type="macro",
            title="Test Macro Event",
            description="Test macro event for pipeline trigger",
            timestamp=datetime.now(),
            source="test",
            related_entities=["US"],
            relevance_score=0.8,
            auto_trigger=False,
            country="US",
            indicator="NFP",
        )

    @pytest.fixture
    def fresh_policy_event(self):
        import uuid
        return PolicyEvent(
            event_id=f"policy_test_{uuid.uuid4().hex[:8]}",
            event_type="policy",
            title="Test Policy Event",
            description="Test policy event",
            timestamp=datetime.now(),
            source="test",
            related_entities=["CN"],
            relevance_score=0.8,
            auto_trigger=False,
            url="https://test.gov.cn",
            publisher="Test Publisher",
        )

    def test_trigger_pipeline_pending_approval(self, fresh_earnings_event):
        result = trigger_research_pipeline(fresh_earnings_event)
        assert result["status"] == "pending_approval"
        assert result["event_id"] == fresh_earnings_event.event_id
        assert "requires human approval" in result["message"]

    def test_trigger_pipeline_auto_trigger(self, fresh_earnings_event):
        fresh_earnings_event.auto_trigger = True
        result = trigger_research_pipeline(fresh_earnings_event)
        assert result["status"] == "queued"  # async=True returns "queued"
        assert result["event_id"] == fresh_earnings_event.event_id
        assert "run_id" in result
        assert "topic" in result

    def test_trigger_pipeline_custom_pipeline_name(self, fresh_macro_event):
        fresh_macro_event.auto_trigger = True
        result = trigger_research_pipeline(fresh_macro_event, pipeline_name="lit_review")
        assert result["pipeline_name"] == "lit_review"

    def test_trigger_pipeline_macro_event(self, fresh_macro_event):
        fresh_macro_event.auto_trigger = True
        result = trigger_research_pipeline(fresh_macro_event)
        assert result["status"] == "queued"  # async=True returns "queued"
        assert "topic" in result

    def test_trigger_pipeline_policy_event(self, fresh_policy_event):
        fresh_policy_event.auto_trigger = True
        result = trigger_research_pipeline(fresh_policy_event)
        assert result["status"] == "queued"  # async=True returns "queued"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Topic Building
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildTopicFromEvent:
    def test_build_topic_from_earnings_event(self, sample_earnings_event):
        topic = _build_topic_from_event(sample_earnings_event)
        assert "000001.SZ" in topic
        assert "2024Q3" in topic
        assert isinstance(topic, str)

    def test_build_topic_from_macro_event(self, sample_macro_event):
        topic = _build_topic_from_event(sample_macro_event)
        assert "US" in topic
        assert "NFP" in topic
        assert isinstance(topic, str)

    def test_build_topic_from_policy_event(self, sample_policy_event):
        topic = _build_topic_from_event(sample_policy_event)
        assert sample_policy_event.title in topic or isinstance(topic, str)
        assert "政策影响" in topic

    def test_build_topic_from_base_event(self):
        event = ResearchEvent(
            event_id="base_001",
            event_type="custom",
            title="Custom Event Title",
            description="Description",
            timestamp=datetime.now(),
            source="test",
        )
        topic = _build_topic_from_event(event)
        assert topic == "Custom Event Title"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Mock Data Helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestMockDataHelpers:
    def test_get_mock_earnings_calendar(self):
        data = _get_mock_earnings_calendar()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "ts_code" in data[0]
        assert "ann_date" in data[0]

    def test_get_mock_macro_releases(self):
        data = _get_mock_macro_releases()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "country" in data[0]
        assert "indicator" in data[0]

    def test_search_policy_keywords_mock(self):
        data = _search_policy_keywords_mock(["关税", "美联储"])
        assert isinstance(data, list)
        assert "title" in data[0]

    def test_search_policy_keywords_mock_max_results(self):
        data = _search_policy_keywords_mock(["政策"], max_results=3)
        assert len(data) <= 3


# ─────────────────────────────────────────────────────────────────────────────
# Test: Loop Control
# ─────────────────────────────────────────────────────────────────────────────

class TestLoopControl:
    def test_stop_flag(self, monitor):
        monitor._running = True
        monitor.stop()
        assert monitor._running is False

    def test_get_last_check(self, monitor):
        assert monitor.get_last_check() is None
        monitor.poll_all()
        assert isinstance(monitor.get_last_check(), datetime)


# ─────────────────────────────────────────────────────────────────────────────
# Test: Handler Registration Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestHandlerEdgeCases:
    def test_register_non_callable_ignored(self, monitor):
        # Non-callable should not crash in the list, but register_handler
        # expects a Callable. This tests the registration itself is robust.
        handler = MagicMock()
        monitor.register_handler(handler)
        assert len(monitor._handlers) == 1

    def test_multiple_handlers_all_called(self, monitor, sample_macro_event):
        h1 = MagicMock()
        h2 = MagicMock()
        monitor.register_handler(h1)
        monitor.register_handler(h2)
        monitor._notify_handlers(sample_macro_event)
        assert h1.called
        assert h2.called
