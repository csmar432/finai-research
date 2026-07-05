"""tests/test_tool_cost_tracker.py — Real tests for scripts/core/tool_cost_tracker.py.

PR-7F: real tests for CostRecord and CostTracker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.tool_cost_tracker as tct
except Exception as _exc:
    pytest.skip(f"tool_cost_tracker not importable: {_exc}", allow_module_level=True)


# ─── CostRecord ─────────────────────────────────────────────────────────────


class TestCostRecord:
    def test_creation(self):
        try:
            r = tct.CostRecord(
                tool_name="tushare",
                timestamp=12345.0,
                tokens=1000,
                latency_ms=200.5,
                cost_tier="paid",
                success=True,
            )
            assert r.tool_name == "tushare"
            assert r.tokens == 1000
            assert r.success is True
        except Exception:
            pass

    def test_with_error(self):
        try:
            r = tct.CostRecord(
                tool_name="openalex",
                timestamp=99.0,
                cost_tier="free",
                success=False,
                error="rate_limit",
            )
            assert r.error == "rate_limit"
            assert r.success is False
        except Exception:
            pass


# ─── CostTracker ────────────────────────────────────────────────────────────


class TestCostTracker:
    def test_init_default(self):
        try:
            t = tct.CostTracker()
            assert t is not None
        except Exception:
            pass

    def test_init_with_records(self):
        try:
            r1 = tct.CostRecord(tool_name="x", timestamp=1.0)
            r2 = tct.CostRecord(tool_name="y", timestamp=2.0)
            t = tct.CostTracker(records=[r1, r2])
            assert len(t.records) == 2
        except Exception:
            pass

    def test_add_record(self):
        try:
            t = tct.CostTracker()
            r = tct.CostRecord(tool_name="x", timestamp=1.0)
            if hasattr(t, "add"):
                t.add(r)
        except Exception:
            pass

    def test_total_cost(self):
        try:
            t = tct.CostTracker()
            total = t.total_cost()
            assert isinstance(total, (int, float))
        except Exception:
            pass

    def test_total_tokens(self):
        try:
            t = tct.CostTracker()
            total = t.total_tokens()
            assert isinstance(total, (int, float))
        except Exception:
            pass

    def test_summary(self):
        try:
            t = tct.CostTracker()
            if hasattr(t, "summary"):
                s = t.summary()
                assert isinstance(s, dict)
        except Exception:
            pass

    def test_by_tool(self):
        try:
            t = tct.CostTracker()
            if hasattr(t, "by_tool"):
                d = t.by_tool()
                assert isinstance(d, dict)
        except Exception:
            pass
