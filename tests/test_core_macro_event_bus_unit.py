"""Unit tests for scripts/core/macro_event_bus.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def meb():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import macro_event_bus as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestMacroEvent:
    def test_init(self, meb):
        e = meb.MacroEvent(
            event_type="CPI",
            timestamp=1234567890.0,
            country="US",
            indicator="CPI",
            value=3.2,
            previous=3.5,
            change=-0.3,
            change_pct=-0.0857,
        )
        assert e.event_type == "CPI"
        assert e.unit == ""


class TestCrossMarketResult:
    def test_init(self, meb):
        r = meb.CrossMarketResult(
            correlation_matrix={("US", "EU"): 0.85},
            lead_lag_relationships={"US->EU": 1},
            regime="risk_on",
            risk_sentiment="positive",
            contagion_events=[],
            regime_confidence=0.85,
        )
        assert r.regime == "risk_on"


class TestNowcastResult:
    def test_init(self, meb):
        r = meb.NowcastResult(
            target="GDP",
            period="2024Q3",
            point_estimate=2.5,
            lower_80=2.3,
            upper_80=2.7,
            lower_95=2.2,
            upper_95=2.8,
            components={"consumption": 1.5, "investment": 0.8},
            model_info={"method": "dynamic_factor"},
            confidence=0.85,
            last_updated="2024-12-01",
        )
        assert r.target == "GDP"
        assert r.confidence == 0.85