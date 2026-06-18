"""
Tool Cost Tracker — extracted from tool_selector.py (P1-ARCH-1 v3 fix).

The 3,400-line tool_selector.py monolith mixes:
  - Tool registry / metadata
  - Cost tier definitions
  - Selection heuristics
  - Execution (MCP / script invocation)
  - Cost accumulation

This module extracts the cost-tracking concern so that:
  - ToolSelector can use it without bloating the selector
  - Tests can target cost logic in isolation
  - Other orchestrators can reuse the same accounting

Usage:
    from scripts.core.tool_cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.record("user-tushare", tokens=1500, latency_ms=420)
    summary = tracker.summary()  # {total_tokens, total_cost_usd, by_tool}
"""
from __future__ import annotations

__all__ = ["CostTracker", "COST_PER_1K_TOKENS_USD"]

import logging
import time
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("tool_cost_tracker")

# Per-1K-token USD cost estimates (rough, public-list prices 2024-2026).
# Override at runtime via CostTracker.set_pricing().
COST_PER_1K_TOKENS_USD: dict[str, float] = {
    "free": 0.0,
    "low": 0.0001,
    "medium": 0.001,
    "high": 0.01,
    "gpt-4": 0.03,
    "gpt-4o": 0.005,
    "claude-sonnet": 0.003,
    "claude-opus": 0.015,
    "deepseek": 0.0001,
}


@dataclass
class CostRecord:
    """Single tool invocation record."""
    tool_name: str
    timestamp: float
    tokens: int = 0
    latency_ms: float = 0.0
    cost_tier: str = "free"
    success: bool = True
    error: str | None = None


@dataclass
class CostTracker:
    """Accumulates per-tool invocation costs.

    Thread-safe enough for a single async pipeline (no locks needed if used
    from one event loop). For multi-threaded use, wrap calls with a lock.
    """
    records: list[CostRecord] = field(default_factory=list)
    _pricing: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._pricing:
            self._pricing = dict(COST_PER_1K_TOKENS_USD)

    def set_pricing(self, tier_costs: dict[str, float]) -> None:
        """Override per-1K-token cost (USD) by tier name."""
        self._pricing.update(tier_costs)

    def record(
        self,
        tool_name: str,
        tokens: int = 0,
        latency_ms: float = 0.0,
        cost_tier: str = "free",
        success: bool = True,
        error: str | None = None,
    ) -> CostRecord:
        """Append a cost record. Returns the record for chaining."""
        rec = CostRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            tokens=tokens,
            latency_ms=latency_ms,
            cost_tier=cost_tier,
            success=success,
            error=error,
        )
        self.records.append(rec)
        return rec

    def _cost_for(self, rec: CostRecord) -> float:
        rate = self._pricing.get(rec.cost_tier, self._pricing.get("free", 0.0))
        return (rec.tokens / 1000.0) * rate

    def summary(self) -> dict[str, Any]:
        """Return aggregated cost summary by tool and tier."""
        by_tool: dict[str, dict[str, Any]] = {}
        total_tokens = 0
        total_cost = 0.0
        total_latency = 0.0
        success_count = 0
        for rec in self.records:
            bucket = by_tool.setdefault(rec.tool_name, {
                "calls": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "latency_ms_sum": 0.0,
                "successes": 0,
                "errors": 0,
            })
            cost = self._cost_for(rec)
            bucket["calls"] += 1
            bucket["tokens"] += rec.tokens
            bucket["cost_usd"] += cost
            bucket["latency_ms_sum"] += rec.latency_ms
            if rec.success:
                bucket["successes"] += 1
            else:
                bucket["errors"] += 1
            total_tokens += rec.tokens
            total_cost += cost
            total_latency += rec.latency_ms
            if rec.success:
                success_count += 1
        return {
            "total_calls": len(self.records),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "total_latency_ms": total_latency,
            "success_rate": (
                success_count / len(self.records) if self.records else 1.0
            ),
            "by_tool": by_tool,
        }

    def reset(self) -> None:
        """Clear all records."""
        self.records.clear()
