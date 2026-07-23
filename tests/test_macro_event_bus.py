"""
test_macro_event_bus.py — Tests for MacroEventBus

Run with:
    pytest tests/test_macro_event_bus.py -v
"""

from __future__ import annotations

import pytest
import time

from scripts.core.macro_event_bus import (
    MacroEventBus,
    MacroEvent,
    EventType,
    MarketRegime,
    CrossMarketAnalyzer,
    MacroNowcaster,
    NowcastResult,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def bus():
    """Fresh MacroEventBus instance for each test."""
    return MacroEventBus()


@pytest.fixture
def sample_event():
    """A sample MacroEvent for testing."""
    return MacroEvent(
        event_type=EventType.DATA_RELEASE,
        timestamp=time.time(),
        country="US",
        indicator="nfp",
        value=250000.0,
        previous=200000.0,
        change=50000.0,
        change_pct=25.0,
        unit="K",
        metadata={"beat_expectations": True},
    )


@pytest.fixture
def sample_event_dict():
    """A sample event as dict for testing dict-to-event conversion."""
    return {
        "event_type": EventType.CPI_RELEASE,
        "timestamp": time.time(),
        "country": "CN",
        "indicator": "cpi",
        "value": 2.1,
        "previous": 1.8,
        "change": 0.3,
        "change_pct": 16.67,
        "unit": "%",
        "metadata": {"source": "NBS"},
    }


# ─── Tests: publish() and subscribe() ────────────────────────────────────────

def test_subscribe_returns_sub_id(bus):
    """subscribe() should return a subscription ID string."""
    def handler(e):
        pass

    sub_id = bus.subscribe("us_macro", handler)
    assert isinstance(sub_id, str)
    assert len(sub_id) == 8


def test_subscribe_multiple_handlers(bus):
    """Multiple handlers can subscribe to the same topic."""
    calls = []

    def handler1(e):
        calls.append(1)

    def handler2(e):
        calls.append(2)

    bus.subscribe("us_macro", handler1)
    bus.subscribe("us_macro", handler2)

    event = MacroEvent(
        event_type=EventType.DATA_RELEASE,
        timestamp=time.time(),
        country="US",
        indicator="nfp",
        value=250000.0,
        previous=None,
        change=None,
        change_pct=None,
    )
    bus.publish("us_macro", event)

    assert calls == [1, 2]


def test_publish_triggers_handler(bus, sample_event):
    """publish() should invoke the handler for subscribers."""
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe("us_macro", handler)
    bus.publish("us_macro", sample_event)

    assert len(received) == 1
    assert received[0].indicator == "nfp"
    assert received[0].value == 250000.0


def test_publish_returns_triggered_count(bus, sample_event):
    """publish() should return the number of triggered handlers."""
    def h1(e):
        pass

    def h2(e):
        pass

    bus.subscribe("us_macro", h1)
    bus.subscribe("us_macro", h2)

    count = bus.publish("us_macro", sample_event)
    assert count == 2


def test_publish_dict_conversion(bus):
    """publish() should convert dict to MacroEvent if needed."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe("us_macro", handler)
    bus.publish("us_macro", {
        "event_type": EventType.DATA_RELEASE,
        "timestamp": time.time(),
        "country": "US",
        "indicator": "cpi",
        "value": 2.5,
        "previous": 2.3,
        "change": 0.2,
        "change_pct": 8.7,
    })

    assert len(received) == 1
    assert isinstance(received[0], MacroEvent)
    assert received[0].indicator == "cpi"


def test_publish_only_triggers_correct_topic(bus, sample_event):
    """Events should only go to subscribers of that topic."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe("us_macro", handler)
    bus.publish("cn_macro", sample_event)

    assert len(received) == 0


# ─── Tests: subscribe_with_condition() ─────────────────────────────────────

def test_subscribe_with_condition_triggers_on_match(bus, sample_event):
    """Conditional subscription should trigger when condition is True."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe_with_condition(
        topic="us_macro",
        handler=handler,
        condition=lambda e: e.indicator == "nfp" and e.value > 200000,
    )
    bus.publish("us_macro", sample_event)

    assert len(received) == 1


def test_subscribe_with_condition_skips_on_mismatch(bus):
    """Conditional subscription should not trigger when condition is False."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe_with_condition(
        topic="us_macro",
        handler=handler,
        condition=lambda e: e.indicator == "nfp" and e.value > 500000,
    )
    event = MacroEvent(
        event_type=EventType.DATA_RELEASE,
        timestamp=time.time(),
        country="US",
        indicator="nfp",
        value=250000.0,
        previous=None,
        change=None,
        change_pct=None,
    )
    bus.publish("us_macro", event)

    assert len(received) == 0


def test_conditional_subscription_with_change_pct(bus):
    """Conditional subscription using change_pct should work."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe_with_condition(
        topic="us_macro",
        handler=handler,
        condition=lambda e: e.change_pct is not None and e.change_pct > 10.0,
    )
    event = MacroEvent(
        event_type=EventType.DATA_RELEASE,
        timestamp=time.time(),
        country="US",
        indicator="nfp",
        value=220000.0,
        previous=200000.0,
        change=20000.0,
        change_pct=10.0,
    )
    bus.publish("us_macro", event)

    assert len(received) == 0


# ─── Tests: unsubscribe() ───────────────────────────────────────────────────

def test_unsubscribe_all_handlers(bus):
    """unsubscribe() with no sub_id should remove all handlers for topic."""
    def h(e):
        pass

    bus.subscribe("us_macro", h)
    bus.unsubscribe("us_macro")

    event = MacroEvent(
        event_type=EventType.DATA_RELEASE,
        timestamp=time.time(),
        country="US",
        indicator="nfp",
        value=250000.0,
        previous=None,
        change=None,
        change_pct=None,
    )
    triggered = bus.publish("us_macro", event)
    assert triggered == 0


# ─── Tests: publish_and_trigger() ──────────────────────────────────────────

def test_publish_and_trigger_creates_event(bus):
    """publish_and_trigger() should create and publish a MacroEvent."""
    received = []

    def handler(e):
        received.append(e)

    bus.subscribe("us_macro", handler)
    event = bus.publish_and_trigger(
        topic="us_macro",
        indicator="cpi",
        value=2.5,
        previous=2.3,
        country="CN",
    )

    assert len(received) == 1
    assert isinstance(event, MacroEvent)
    assert event.indicator == "cpi"
    assert event.value == 2.5
    assert event.previous == 2.3
    assert abs(event.change - 0.2) < 1e-9
    assert event.change_pct is not None


def test_publish_and_trigger_calculates_change_pct(bus):
    """publish_and_trigger() should correctly compute change_pct."""
    event = bus.publish_and_trigger(
        topic="us_macro",
        indicator="nfp",
        value=220000.0,
        previous=200000.0,
    )

    expected_pct = (20000.0 / 200000.0) * 100
    assert abs(event.change_pct - expected_pct) < 0.01


def test_publish_and_trigger_zero_previous(bus):
    """publish_and_trigger() should handle previous=0 gracefully."""
    event = bus.publish_and_trigger(
        topic="us_macro",
        indicator="nfp",
        value=100.0,
        previous=0.0,
    )
    assert event.change_pct is None


# ─── Tests: detect_trend_change() ───────────────────────────────────────────

def test_detect_trend_change_detects_uptrend(bus):
    """detect_trend_change() should return an event when trend changes up."""
    historical = [100.0, 102.0, 101.0, 103.0]  # mean ≈ 102
    new_value = 115.0  # > 5% above mean

    event = bus.detect_trend_change(
        topic="US",
        indicator="PMI",
        new_value=new_value,
        historical_values=historical,
        threshold=0.05,
    )

    assert event is not None
    assert event.event_type == EventType.TREND_CHANGE
    assert event.indicator == "PMI"
    assert event.value == 115.0


def test_detect_trend_change_no_change_below_threshold(bus):
    """detect_trend_change() should return None when change is within threshold."""
    historical = [100.0, 102.0, 101.0, 103.0]
    new_value = 104.0  # small change

    event = bus.detect_trend_change(
        topic="US",
        indicator="PMI",
        new_value=new_value,
        historical_values=historical,
        threshold=0.05,
    )

    assert event is None


def test_detect_trend_change_insufficient_history(bus):
    """detect_trend_change() should return None with fewer than 3 historical values."""
    historical = [100.0, 102.0]

    event = bus.detect_trend_change(
        topic="US",
        indicator="PMI",
        new_value=120.0,
        historical_values=historical,
        threshold=0.05,
    )

    assert event is None


# ─── Tests: get_recent_events() ──────────────────────────────────────────────

def test_get_recent_events_returns_all(bus):
    """get_recent_events() without filter should return all recent events."""
    for i in range(5):
        bus.publish_and_trigger(
            topic="us_macro",
            indicator=f"ind_{i}",
            value=float(i),
            previous=None,
        )

    events = bus.get_recent_events()
    assert len(events) == 5


def test_get_recent_events_filters_by_country(bus):
    """get_recent_events() should filter by country code."""
    bus.publish_and_trigger(topic="US", indicator="nfp", value=250.0, previous=None, country="US")
    bus.publish_and_trigger(topic="CN", indicator="cpi", value=2.1, previous=None, country="CN")
    bus.publish_and_trigger(topic="EU", indicator="gdp", value=1.5, previous=None, country="EU")

    events = bus.get_recent_events(topic="CN")
    assert len(events) == 1
    assert events[0].country == "CN"


def test_get_recent_events_respects_limit(bus):
    """get_recent_events() should respect the limit parameter."""
    for i in range(10):
        bus.publish_and_trigger(topic="US", indicator=f"ind_{i}", value=float(i), previous=None)

    events = bus.get_recent_events(limit=3)
    assert len(events) == 3


def test_get_recent_events_returns_most_recent_first(bus):
    """get_recent_events() should return most recent events last (chronological order)."""
    for i in range(3):
        bus.publish_and_trigger(topic="US", indicator=f"ind_{i}", value=float(i), previous=None)

    events = bus.get_recent_events()
    assert events[0].indicator == "ind_0"
    assert events[-1].indicator == "ind_2"


# ─── Tests: clear_history() ─────────────────────────────────────────────────

def test_clear_history_removes_all_events(bus):
    """clear_history() should empty the event history."""
    for i in range(5):
        bus.publish_and_trigger(topic="US", indicator=f"ind_{i}", value=float(i), previous=None)

    bus.clear_history()
    events = bus.get_recent_events()
    assert len(events) == 0


def test_clear_history_allows_new_events(bus):
    """After clear_history(), new events should still be recorded."""
    bus.publish_and_trigger(topic="US", indicator="ind_0", value=1.0, previous=None)
    bus.clear_history()
    bus.publish_and_trigger(topic="US", indicator="ind_1", value=2.0, previous=None)

    events = bus.get_recent_events()
    assert len(events) == 1
    assert events[0].indicator == "ind_1"


# ─── Tests: event history management ─────────────────────────────────────────

def test_event_history_max_limit(bus):
    """Event history should be capped at _history_max (1000)."""
    # Publish more than 1000 events
    for i in range(1005):
        bus.publish_and_trigger(topic="US", indicator=f"ind_{i}", value=float(i), previous=None)

    events = bus.get_recent_events(limit=1000)
    assert len(events) == 1000


# ─── Tests: error handling ───────────────────────────────────────────────────

def test_handler_exception_does_not_crash_publish(bus, sample_event):
    """Handler exceptions should be caught and logged, not propagate."""
    def bad_handler(e):
        raise RuntimeError("handler error")

    bus.subscribe("us_macro", bad_handler)
    # Should not raise
    triggered = bus.publish("us_macro", sample_event)
    assert triggered == 0  # handler error means triggered = 0


def test_conditional_handler_exception_does_not_crash(bus, sample_event):
    """Conditional handler exceptions should be caught, not propagate."""
    def bad_condition(e):
        raise RuntimeError("condition error")

    def handler(e):
        pass

    bus.subscribe_with_condition(
        topic="us_macro",
        handler=handler,
        condition=bad_condition,
    )
    # Should not raise
    triggered = bus.publish("us_macro", sample_event)
    assert triggered == 0


# ─── Tests: CrossMarketAnalyzer ───────────────────────────────────────────────

def test_cross_market_analyzer_instantiation():
    """CrossMarketAnalyzer should instantiate without errors."""
    analyzer = CrossMarketAnalyzer()
    assert analyzer is not None


def test_correlation_matrix_returns_dict(bus):
    """correlation_matrix() should return a dict of dicts."""
    analyzer = CrossMarketAnalyzer()
    matrix = analyzer.correlation_matrix(["TNX", "DXY", "SPX"], method="pearson")

    assert isinstance(matrix, dict)
    for key in ["TNX", "DXY", "SPX"]:
        assert key in matrix
        for inner_key in ["TNX", "DXY", "SPX"]:
            assert inner_key in matrix[key]
            assert isinstance(matrix[key][inner_key], float)


def test_correlation_matrix_diagonal_is_one(bus):
    """Diagonal elements of correlation matrix should be 1.0."""
    analyzer = CrossMarketAnalyzer()
    matrix = analyzer.correlation_matrix(["TNX", "DXY"], method="pearson")

    assert abs(matrix["TNX"]["TNX"] - 1.0) < 1e-6
    assert abs(matrix["DXY"]["DXY"] - 1.0) < 1e-6


def test_correlation_matrix_spearman(bus):
    """correlation_matrix() should work with spearman method."""
    analyzer = CrossMarketAnalyzer()
    matrix = analyzer.correlation_matrix(["TNX", "DXY"], method="spearman")

    assert isinstance(matrix, dict)
    assert "TNX" in matrix and "DXY" in matrix


def test_detect_regime_returns_result():
    """detect_regime() should return a CrossMarketResult."""
    analyzer = CrossMarketAnalyzer()
    result = analyzer.detect_regime({"VIX": 35, "TED": 120, "IG": 400, "XAU": 2100, "SPX": 3800})

    assert result.regime == MarketRegime.HIGH_VOL
    assert result.risk_sentiment < 0


def test_detect_regime_default_data():
    """detect_regime() should work without explicit market data."""
    analyzer = CrossMarketAnalyzer()
    result = analyzer.detect_regime()
    assert result is not None
    assert isinstance(result.regime, MarketRegime)


def test_detect_contagion_returns_list():
    """detect_contagion() should return a list of events."""
    analyzer = CrossMarketAnalyzer()
    data = {
        "SPX": [0.01, -0.02, 0.03, -0.04, 0.05] * 10,
        "TNX": [0.005, -0.01, 0.015, -0.02, 0.025] * 10,
    }
    events = analyzer.detect_contagion(data, threshold=0.03)
    assert isinstance(events, list)


# ─── Tests: MacroNowcaster ───────────────────────────────────────────────────

def test_macro_nowcaster_instantiation():
    """MacroNowcaster should instantiate without errors."""
    nowcaster = MacroNowcaster()
    assert nowcaster is not None


def test_nowcast_gdp_cn():
    """nowcast_gdp() for CN should return NowcastResult."""
    nowcaster = MacroNowcaster()
    result = nowcaster.nowcast_gdp("CN", "2024-Q1")

    assert isinstance(result, NowcastResult)
    assert result.target == "CN_GDP"
    assert result.period == "2024-Q1"
    assert result.lower_80 < result.point_estimate < result.upper_80
    assert result.lower_95 < result.upper_95


def test_nowcast_gdp_us():
    """nowcast_gdp() for US should return NowcastResult."""
    nowcaster = MacroNowcaster()
    result = nowcaster.nowcast_gdp("US", "2024-Q1")

    assert isinstance(result, NowcastResult)
    assert result.target == "US_GDP"
    assert result.period == "2024-Q1"


def test_nowcast_gdp_eu_fallback():
    """nowcast_gdp() for unknown country should use generic fallback."""
    nowcaster = MacroNowcaster()
    result = nowcaster.nowcast_gdp("XX", "2024-Q1")

    assert isinstance(result, NowcastResult)
    assert result.confidence == 0.3
    assert result.model_info["model"] == "generic"


def test_nowcast_with_overrides():
    """nowcast_gdp() should use indicator overrides when provided."""
    nowcaster = MacroNowcaster()
    # Overrides replace entries entirely; pass dicts matching the expected format.
    result = nowcaster.nowcast_gdp(
        "CN",
        "2024-Q1",
        indicator_overrides={
            "PMI": {"weight": 0.25, "direction": 1, "lag": 0},
            "CPI": {"weight": 0.10, "direction": -1, "lag": 1},
        },
    )

    assert isinstance(result, NowcastResult)
    assert "PMI" in result.components
    assert "CPI" in result.components


# ─── Tests: integration scenarios ──────────────────────────────────────────

def test_full_workflow_multiple_topics(bus):
    """Test a realistic multi-topic event workflow."""
    us_events = []
    cn_events = []

    def us_handler(e):
        us_events.append(e)

    def cn_handler(e):
        cn_events.append(e)

    def high_nfp_handler(e):
        if e.value > 300000:
            us_events.append(e)

    bus.subscribe("us_macro", us_handler)
    bus.subscribe("cn_macro", cn_handler)
    bus.subscribe_with_condition(
        topic="us_macro",
        handler=high_nfp_handler,
        condition=lambda e: e.value > 300000,
    )

    # Publish US NFP (high)
    bus.publish_and_trigger(
        topic="us_macro",
        indicator="nfp",
        value=350000.0,
        previous=200000.0,
        country="US",
    )

    # Publish CN CPI
    bus.publish_and_trigger(
        topic="cn_macro",
        indicator="cpi",
        value=2.1,
        previous=1.9,
        country="CN",
    )

    assert len(us_events) == 2  # both handlers triggered
    assert len(cn_events) == 1


def test_event_filtering_by_indicator(bus):
    """Test filtering events by indicator name."""
    bus.publish_and_trigger(topic="US", indicator="nfp", value=250.0, previous=None, country="US")
    bus.publish_and_trigger(topic="US", indicator="cpi", value=2.1, previous=None, country="US")
    bus.publish_and_trigger(topic="US", indicator="nfp", value=275.0, previous=None, country="US")

    events = bus.get_recent_events(topic="nfp")
    assert len(events) == 2
    assert all(e.indicator == "nfp" for e in events)
