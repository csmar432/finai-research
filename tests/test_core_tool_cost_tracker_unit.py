"""Unit tests for scripts/core/tool_cost_tracker.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def tct():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import tool_cost_tracker as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, tct):
        assert hasattr(tct, "CostTracker")
        assert hasattr(tct, "COST_PER_1K_TOKENS_USD")


class TestPricingConstants:
    def test_pricing_dict_exists(self, tct):
        assert isinstance(tct.COST_PER_1K_TOKENS_USD, dict)

    def test_free_tier_is_zero(self, tct):
        assert tct.COST_PER_1K_TOKENS_USD["free"] == 0.0

    def test_known_tiers(self, tct):
        for tier in ["low", "medium", "high", "gpt-4", "claude-sonnet", "deepseek"]:
            assert tier in tct.COST_PER_1K_TOKENS_USD


class TestCostRecordDataclass:
    def test_init(self, tct):
        rec = tct.CostRecord(tool_name="test_tool", timestamp=1000.0)
        assert rec.tool_name == "test_tool"
        assert rec.timestamp == 1000.0
        assert rec.tokens == 0
        assert rec.latency_ms == 0.0
        assert rec.cost_tier == "free"
        assert rec.success is True
        assert rec.error is None

    def test_init_with_error(self, tct):
        rec = tct.CostRecord(
            tool_name="t", timestamp=1000.0,
            tokens=100, latency_ms=50.0,
            cost_tier="medium", success=False, error="boom",
        )
        assert rec.error == "boom"
        assert rec.success is False


class TestCostTrackerDataclass:
    def test_init_default_pricing(self, tct):
        tracker = tct.CostTracker()
        assert tracker.records == []
        assert "free" in tracker._pricing
        assert "gpt-4" in tracker._pricing

    def test_set_pricing_override(self, tct):
        tracker = tct.CostTracker()
        tracker.set_pricing({"custom": 0.5})
        assert tracker._pricing["custom"] == 0.5
        # Existing keys remain
        assert "free" in tracker._pricing

    def test_record_returns_record(self, tct):
        tracker = tct.CostTracker()
        rec = tracker.record("tool1", tokens=1000, latency_ms=200.0, cost_tier="medium")
        assert rec.tool_name == "tool1"
        assert rec.tokens == 1000
        assert rec.cost_tier == "medium"
        assert rec in tracker.records

    def test_record_appends(self, tct):
        tracker = tct.CostTracker()
        tracker.record("a", tokens=100)
        tracker.record("b", tokens=200)
        tracker.record("c", tokens=300)
        assert len(tracker.records) == 3

    def test_summary_empty(self, tct):
        tracker = tct.CostTracker()
        s = tracker.summary()
        assert s["total_calls"] == 0
        assert s["total_tokens"] == 0
        assert s["total_cost_usd"] == 0.0
        assert s["total_latency_ms"] == 0.0
        assert s["success_rate"] == 1.0  # default success rate for no records
        assert s["by_tool"] == {}

    def test_summary_aggregates(self, tct):
        tracker = tct.CostTracker()
        tracker.record("tool_a", tokens=1000, latency_ms=100.0, cost_tier="low")
        tracker.record("tool_a", tokens=2000, latency_ms=200.0, cost_tier="low", success=False)
        tracker.record("tool_b", tokens=500, latency_ms=50.0, cost_tier="medium")
        s = tracker.summary()
        assert s["total_calls"] == 3
        assert s["total_tokens"] == 3500
        assert s["total_latency_ms"] == 350.0
        assert "tool_a" in s["by_tool"]
        assert "tool_b" in s["by_tool"]
        assert s["by_tool"]["tool_a"]["calls"] == 2
        assert s["by_tool"]["tool_a"]["successes"] == 1
        assert s["by_tool"]["tool_a"]["errors"] == 1
        assert s["by_tool"]["tool_b"]["calls"] == 1
        # success_rate = 2/3
        assert abs(s["success_rate"] - (2/3)) < 1e-9

    def test_summary_cost_calculation(self, tct):
        tracker = tct.CostTracker()
        # Low tier: 0.0001 / 1K tokens → 1000 tokens = 0.0001 USD
        tracker.record("tool_a", tokens=1000, cost_tier="low")
        s = tracker.summary()
        assert abs(s["total_cost_usd"] - 0.0001) < 1e-9

    def test_summary_free_tier(self, tct):
        tracker = tct.CostTracker()
        tracker.record("t", tokens=100000, cost_tier="free")
        s = tracker.summary()
        assert s["total_cost_usd"] == 0.0

    def test_reset_clears_records(self, tct):
        tracker = tct.CostTracker()
        tracker.record("t", tokens=100)
        tracker.record("t2", tokens=200)
        assert len(tracker.records) == 2
        tracker.reset()
        assert len(tracker.records) == 0

    def test_unknown_tier_falls_back_to_free(self, tct):
        tracker = tct.CostTracker()
        tracker.record("t", tokens=1000, cost_tier="unknown_tier_xyz")
        s = tracker.summary()
        # Should fall back to "free" pricing (0.0)
        assert s["total_cost_usd"] == 0.0

    def test_cost_for_internal(self, tct):
        tracker = tct.CostTracker()
        rec = tct.CostRecord("t", 1000.0, tokens=1000, cost_tier="high")
        # high tier is 0.01 per 1K → 1000 tokens = 0.01 USD
        cost = tracker._cost_for(rec)
        assert abs(cost - 0.01) < 1e-9
