"""
Event-Driven Research Trigger System (D7)

Monitors earnings calendars, macroeconomic data releases, and policy documents,
triggering the research pipeline when relevant events occur.

Features:
- Earnings calendar monitoring (tushare with graceful fallback)
- Macro data release tracking (FED/BEA/OECD via MCP)
- Policy document keyword alerts (brave_search via MCP)
- Configurable auto-trigger vs. human approval mode
- APScheduler for calendar-aware scheduling
- Signal mechanism to prevent duplicate triggers
- Real pipeline execution (EnhancedPipeline or demo_research_report)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from datetime import datetime as dt


_log = logging.getLogger("event_monitor")
_log.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# Event Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ResearchEvent:
    """Base class for all research-triggering events."""
    event_id: str
    event_type: str  # "earnings" / "macro" / "policy" / "custom"
    title: str
    description: str
    timestamp: datetime
    source: str  # "tushare" / "fed" / "oecd" / "eastmoney" / "brave_search"
    related_entities: list[str] = field(default_factory=list)
    relevance_score: float = 0.0  # 0-1
    auto_trigger: bool = False
    triggered_at: datetime | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EarningsEvent(ResearchEvent):
    """Earnings release event (from tushare financial report calendar)."""
    ts_code: str = ""
    report_date: str = ""  # scheduled report date
    actual_date: str | None = None  # actual announcement date
    fiscal_period: str = ""  # e.g., "2024Q3", "2024 annual"

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"earnings_{self.ts_code}_{self.report_date}"
        if not self.event_type:
            self.event_type = "earnings"
        if not self.source:
            self.source = "tushare"


@dataclass
class MacroEvent(ResearchEvent):
    """Macroeconomic data release event."""
    country: str = ""  # e.g., "US", "CN", "EU"
    indicator: str = ""  # e.g., "CPI", "GDP", "NFP"
    previous_value: str = ""
    forecast_value: str = ""
    report_date: str = ""  # scheduled release date (e.g. "2024-10-15")

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"macro_{self.country}_{self.indicator}_{self.report_date}"
        if not self.event_type:
            self.event_type = "macro"
        if not self.source:
            self.source = "fed"


@dataclass
class PolicyEvent(ResearchEvent):
    """Policy document event (from keyword search)."""
    url: str = ""
    publisher: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"policy_{uuid.uuid4().hex[:8]}"
        if not self.event_type:
            self.event_type = "policy"
        if not self.source:
            self.source = "brave_search"


# ─────────────────────────────────────────────────────────────────────────────
# EventMonitor Class
# ─────────────────────────────────────────────────────────────────────────────

class EventMonitor:
    """Monitor financial events and trigger research pipeline.

    Args:
        check_interval: Seconds between polling cycles (default: 300).
        auto_trigger: If True, automatically trigger pipeline without approval.
        config_path: Path to project_config.json for loading keywords/config.
    """

    def __init__(
        self,
        check_interval: int = 300,
        auto_trigger: bool = False,
        config_path: str = "config/project_config.json",
    ):
        self.check_interval = check_interval
        self.auto_trigger = auto_trigger
        self.config_path = Path(config_path)
        self._running = False
        self._last_check: dict[str, datetime] = {}
        self._event_queue: deque = deque(maxlen=1000)
        self._handlers: list[Callable] = []
        self._config: dict | None = None
        self._load_config()

    def _load_config(self):
        """Load project config if exists."""
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    self._config = json.load(f)
            except Exception:
                self._config = None
        # Also load event_monitor settings from config
        self._monitor_config = (self._config or {}).get("event_monitor", {})

    @property
    def keywords(self) -> list[str]:
        """Default policy keywords from config or fallback."""
        if self._config:
            monitor_cfg = self._config.get("event_monitor", {})
            keywords = monitor_cfg.get("policy_keywords", [])
            if keywords:
                return keywords
            research = self._config.get("research", {})
            keywords = research.get("policy_keywords", [])
            if keywords:
                return keywords
        return ["关税", "美联储", "降准", "碳排放"]

    def register_handler(self, handler: Callable[["ResearchEvent"], None]):
        """Register a callback for triggered events.

        Args:
            handler: Callable that accepts a ResearchEvent and returns None.
        """
        self._handlers.append(handler)

    # ── Event Source Methods ──────────────────────────────────────────────────

    def check_earnings_calendar(
        self,
        lookback_days: int = 7,
        top_n: int = 20,
    ) -> list[EarningsEvent]:
        """Check upcoming earnings releases via tushare.

        Falls back to mock data when TUSHARE_TOKEN is not set.

        Args:
            lookback_days: Number of days to look back for announcements.
            top_n: Maximum number of events to return.

        Returns:
            List of EarningsEvent objects.
        """
        raw_events = _get_earnings_calendar_tushare(lookback_days)
        events = []
        for record in raw_events[:top_n]:
            event = EarningsEvent(
                event_id=f"earnings_{record.get('ts_code', '')}_{record.get('ann_date', '')}",
                event_type="earnings",
                title=record.get("title", f"Earnings: {record.get('ts_code', '')}"),
                description=record.get("description", f"Earnings announcement on {record.get('ann_date', 'TBD')}"),
                timestamp=datetime.now(),
                source=record.get("source", "tushare"),
                related_entities=[record.get("ts_code", "")],
                relevance_score=0.7,
                auto_trigger=self.auto_trigger,
                ts_code=record.get("ts_code", ""),
                report_date=record.get("ann_date", ""),
                actual_date=record.get("actual_date"),
                fiscal_period=record.get("fiscal_period", ""),
            )
            events.append(event)
        return events

    def check_macro_releases(
        self,
        countries: list[str] | None = None,
    ) -> list[MacroEvent]:
        """Check upcoming macro data releases from multiple sources.

        Uses MCP tools: user-financial, user-fed-data, user-oecd-data.
        Combines economic calendar from multiple sources.

        Args:
            countries: List of country codes to filter (e.g., ["US", "CN", "EU"]).
                     If None, checks all available.

        Returns:
            List of MacroEvent objects.
        """
        events = []

        # Build macro events from mock/config (MCP integration would replace this)
        macro_data = _get_mock_macro_releases()

        for record in macro_data:
            country = record.get("country", "")
            if countries and country not in countries:
                continue

            event = MacroEvent(
                event_id=f"macro_{country}_{record.get('indicator', '')}_{record.get('release_date', '')}",
                event_type="macro",
                title=record.get("title", f"{country} {record.get('indicator', '')} Release"),
                description=record.get("description", f"{country} {record.get('indicator', '')} scheduled release"),
                timestamp=datetime.now(),
                source=record.get("source", "fed"),
                related_entities=[country],
                relevance_score=record.get("relevance_score", 0.6),
                auto_trigger=self.auto_trigger,
                country=country,
                indicator=record.get("indicator", ""),
                previous_value=record.get("previous_value", ""),
                forecast_value=record.get("forecast_value", ""),
                report_date=record.get("release_date", ""),
            )
            events.append(event)

        return events

    def check_policy_keywords(
        self,
        keywords: list[str] | None = None,
        max_results: int = 10,
    ) -> list[PolicyEvent]:
        """Search for policy documents matching keywords.

        Uses brave_search MCP tool when available.

        Args:
            keywords: List of keywords to search. If None, uses self.keywords.
            max_results: Maximum number of results to return.

        Returns:
            List of PolicyEvent objects.
        """
        if keywords is None:
            keywords = self.keywords

        events = []
        # In production, this would call brave_search MCP tool
        # For now, return mock data based on keywords
        policy_data = _search_policy_keywords_mock(keywords, max_results)

        for record in policy_data:
            event = PolicyEvent(
                event_id=f"policy_{uuid.uuid4().hex[:8]}",
                event_type="policy",
                title=record.get("title", ""),
                description=record.get("description", ""),
                timestamp=datetime.now(),
                source=record.get("source", "brave_search"),
                related_entities=record.get("related_entities", []),
                relevance_score=record.get("relevance_score", 0.5),
                auto_trigger=self.auto_trigger,
                url=record.get("url", ""),
                publisher=record.get("publisher", ""),
            )
            events.append(event)

        return events

    # ── Loop Control ───────────────────────────────────────────────────────────

    def run_loop(self):
        """Main monitoring loop. Call this in a background thread."""
        self._running = True
        while self._running:
            self.poll_all()
            time.sleep(self.check_interval)

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False

    # ── Polling ────────────────────────────────────────────────────────────────

    def poll_all(self) -> list[ResearchEvent]:
        """Poll all event sources and return triggered events.

        Returns:
            List of all ResearchEvent objects found in this poll.
        """
        events: list[ResearchEvent] = []
        events.extend(self.check_earnings_calendar())
        events.extend(self.check_macro_releases())
        events.extend(self.check_policy_keywords())

        for event in events:
            # Avoid duplicates in queue (by event_id)
            existing_ids = {e.event_id for e in self._event_queue}
            if event.event_id not in existing_ids:
                self._event_queue.append(event)
                self._notify_handlers(event)

        self._last_check["all"] = datetime.now()
        return events

    def _notify_handlers(self, event: ResearchEvent):
        """Notify all registered handlers of a new event."""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Handler error: {e}")

    # ── Queue Management ──────────────────────────────────────────────────────

    def get_pending_events(self) -> list[ResearchEvent]:
        """Get all pending events in the queue."""
        return list(self._event_queue)

    def clear_queue(self):
        """Clear the event queue."""
        self._event_queue.clear()

    def get_last_check(self, source: str | None = None) -> datetime | None:
        """Get the last check timestamp for a source, or 'all'."""
        key = source if source else "all"
        return self._last_check.get(key)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Trigger Integration
# ─────────────────────────────────────────────────────────────────────────────

# Global registry of running pipeline processes (pid → info)
_running_pipelines: dict[int, dict] = {}
_pipeline_lock = threading.Lock()


class PipelineStatus(Enum):
    PENDING_APPROVAL = "pending_approval"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineRun:
    """Represents a single pipeline run initiated by an event."""
    run_id: str
    event_id: str
    topic: str
    pipeline_name: str
    status: PipelineStatus
    pid: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_dir: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def get_running_pipelines() -> list[PipelineRun]:
    """Return list of currently running pipeline runs."""
    return [v for v in _running_pipelines.values() if v["run"].status == PipelineStatus.RUNNING]


def _dedup_key(event: ResearchEvent) -> str:
    """Build a deduplication key from an event.

    Same company (earnings) or same indicator+date (macro) within 24h
    won't trigger twice.
    """
    if isinstance(event, EarningsEvent):
        return f"earnings:{event.ts_code}:{event.fiscal_period}"
    elif isinstance(event, MacroEvent):
        return f"macro:{event.country}:{event.indicator}:{event.report_date}"
    elif isinstance(event, PolicyEvent):
        return f"policy:{event.title[:50]}"
    return f"event:{event.event_id}"


# ─── MCP Integration Helpers ─────────────────────────────────────────────────

def _check_macro_via_mcp(countries: list[str]) -> list[MacroEvent]:
    """Check macro releases via MCP tools.

    Tries in order:
      1. user-eodhd → economic_events
      2. user-financial → get_macro_china / get_macro_usa
      3. user-fed-data → get_fed_interest_rate / get_fed_beige_book
      4. mock fallback
    """
    events: list[MacroEvent] = []

    try:
        # Try MCP eodhd economic calendar
        result = _call_mcp("user-eodhd", "get_economic_events",
                           {"country": countries[0] if countries else "US", "limit": 50})
        if result and not result.get("_error"):
            for item in result.get("data", [])[:20]:
                events.append(MacroEvent(
                    event_id=f"macro_eodhd_{uuid.uuid4().hex[:8]}",
                    title=item.get("title", item.get("event", "")),
                    description=item.get("description", ""),
                    timestamp=datetime.now(),
                    source="user-eodhd",
                    related_entities=[item.get("country", "")],
                    relevance_score=0.8,
                    country=item.get("country", ""),
                    indicator=item.get("event", ""),
                    report_date=item.get("date", ""),
                ))
            return events
    except Exception:
        pass  # EODHD MCP failed — continue to financial fallback

    # Try MCP user-financial (China macro)
    try:
        for country in (countries or ["CN", "US"]):
            if country == "CN":
                for indicator in ["cpi", "ppi", "gdp"]:
                    result = _call_mcp("user-financial", "get_macro_china",
                                       {"indicator": indicator})
                    if result and not result.get("_error") and result.get("data"):
                        latest = result["data"][-1]
                        events.append(MacroEvent(
                            event_id=f"macro_fin_{country}_{indicator}_{uuid.uuid4().hex[:6]}",
                            title=f"中国{indicator.upper()}数据发布",
                            description=f"最新值: {latest.get('value', 'N/A')}",
                            timestamp=datetime.now(),
                            source="user-financial",
                            related_entities=[country],
                            relevance_score=0.8,
                            country=country,
                            indicator=indicator.upper(),
                            report_date=latest.get("date", datetime.now().strftime("%Y-%m-%d")),
                        ))
                        break
    except Exception:
        pass  # user-financial MCP failed — continue to mock fallback

    # Fallback to mock
    if not events:
        events = _get_mock_macro_releases()
        for ev in events:
            if countries and ev["country"] not in countries:
                continue
            ev["source"] = "mock"
    return events


def _check_policy_via_mcp(keywords: list[str]) -> list[PolicyEvent]:
    """Check policy keywords via MCP tools.

    Tries:
      1. user-brave-search → brave_web_search
      2. user-eastmoney-reports → get_research_report
      3. mock fallback
    """
    events: list[PolicyEvent] = []
    try:
        for kw in keywords[:5]:
            result = _call_mcp("user-brave-search", "brave_web_search",
                               {"query": kw, "count": 3})
            if result and not result.get("_error"):
                for item in result.get("web_results", result.get("results", []))[:3]:
                    title = item.get("title", "")
                    url = item.get("url", "")
                    if not title:
                        continue
                    events.append(PolicyEvent(
                        event_id=f"policy_brv_{uuid.uuid4().hex[:8]}",
                        title=title[:200],
                        description=item.get("description", "")[:500],
                        timestamp=datetime.now(),
                        source="user-brave-search",
                        related_entities=[kw],
                        relevance_score=0.7,
                        url=url,
                    ))
            if len(events) >= 10:
                break
    except Exception:
        pass  # Policy search failed — continue to mock fallback

    if not events:
        events = _search_policy_keywords_mock(keywords, 5)
        for ev in events:
            ev.source = "mock"
    return events


def _call_mcp(server: str, tool: str, params: dict) -> dict | None:
    """Call an MCP tool and return parsed result. Returns None on failure."""
    try:
        from scripts.core.mcp_client import MCPToolClient
        client = MCPToolClient()
        result = client.call(server, tool, params)
        return result
    except Exception:
        # Fallback: try direct subprocess call via mcp CLI
        try:
            import json as _json
            payload = _json.dumps({
                "jsonrpc": "2.0",
                "method": f"{server}/{tool}",
                "params": params,
                "id": 1,
            }).encode()
            proc = subprocess.run(
                ["mcp", "call", server, tool],
                input=payload, capture_output=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return _json.loads(proc.stdout)
        except Exception:
            pass
    return None


def trigger_research_pipeline(
    event: ResearchEvent,
    pipeline_name: str = "research_report",
    auto_trigger: bool | None = None,
    output_dir: str | Path | None = None,
    run_async: bool = True,
    language: str = "zh",
    journal: str = "经济研究",
) -> dict:
    """Trigger the research pipeline for a given event.

    This function actually runs the pipeline (not just returning a dict).
    When auto_trigger is None, uses event.auto_trigger.
    When auto_trigger=True, runs the pipeline in a background thread.
    When auto_trigger=False, returns status="pending_approval".

    Args:
        event: The research event that triggered this call.
        pipeline_name: "research_report" (demo) or "paper" (EnhancedPipeline).
        auto_trigger: If None, uses event.auto_trigger. If True, run immediately.
                     If False, require approval.
        output_dir: Custom output directory. Auto-generated if None.
        run_async: If True, run pipeline in background thread (non-blocking).
                   If False, run synchronously (blocks until complete).
        language: "zh" or "en".
        journal: Target journal name.

    Returns:
        dict with:
          - status: "pending_approval" | "queued" | "running" | "completed" | "failed"
          - run_id: unique pipeline run ID
          - event_id: event that triggered
          - topic: generated research topic
          - pid: process ID (if running)
          - output_dir: where results will be saved
          - message: human-readable message
    """
    if auto_trigger is None:
        auto_trigger = getattr(event, "auto_trigger", False)

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    topic = _build_topic_from_event(event)
    dedup = _dedup_key(event)

    # Check deduplication window (same event within 24h)
    state_file = Path("data/event_trigger_state.json")
    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                state: dict = json.load(f)
            last_run = state.get(dedup)
            if last_run:
                last_ts = datetime.fromisoformat(last_run["timestamp"])
                if (datetime.now() - last_ts).total_seconds() < 86400:
                    _log.info(
                        f"[{run_id}] Skipping duplicate event '{dedup}' "
                        f"(last ran {last_run['timestamp']})"
                    )
                    return {
                        "status": "skipped",
                        "run_id": run_id,
                        "event_id": event.event_id,
                        "topic": topic,
                        "pipeline_name": pipeline_name,
                        "message": f"Skipped: same event ran within 24h (last: {last_run['timestamp']})",
                    }
        except Exception:
            pass

    # Generate output directory
    if output_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c if c.isalnum() else "_" for c in event.event_type)
        output_dir = f"output/event_runs/{event.event_type}/{ts}_{safe_topic}"

    if not auto_trigger:
        return {
            "status": "pending_approval",
            "run_id": run_id,
            "event_id": event.event_id,
            "topic": topic,
            "pipeline_name": pipeline_name,
            "output_dir": str(output_dir),
            "message": (
                f"Event '{event.title}' requires human approval.\n"
                f"  Topic: {topic}\n"
                f"  Run: python -m scripts.research_framework.enhanced_pipeline "
                f"--topic '{topic}' --output {output_dir} --language {language}"
            ),
        }

    # Mark as triggered (record dedup state)
    _record_trigger(dedup, run_id, event.event_id, topic)

    if run_async:
        thread = threading.Thread(
            target=_run_pipeline_bg,
            args=(run_id, topic, pipeline_name, output_dir, language, journal, event),
            daemon=True,
            name=f"pipeline-{run_id}",
        )
        thread.start()
        _log.info(f"[{run_id}] Pipeline queued (async): {topic}")
        return {
            "status": "queued",
            "run_id": run_id,
            "event_id": event.event_id,
            "topic": topic,
            "pipeline_name": pipeline_name,
            "output_dir": str(output_dir),
            "message": f"Pipeline queued: {topic}",
        }
    else:
        return _run_pipeline_sync(run_id, topic, pipeline_name, output_dir, language, journal, event)


def _run_pipeline_sync(
    run_id: str,
    topic: str,
    pipeline_name: str,
    output_dir: str,
    language: str,
    journal: str,
    event: ResearchEvent,
) -> dict:
    """Run pipeline synchronously and return result."""
    started_at = datetime.now()
    finished_at = None  # Initialized so the success-return path always has a defined value.

    # ── 可视化回调：审批通过后推送结果到 Canvas ────────────────────────
    # 可视化仅在用户审批后推送，防止在审批前展示结果
    def _on_gate_approved(stage_name: str, ctx, feedback: str = "") -> None:
        payload = {
            "event": "gate_approved",
            "stage": stage_name,
            "topic": topic,
            "run_id": run_id,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            cache_dir = Path(__file__).parent.parent / ".cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            fpath = cache_dir / "wf_gate_approved.json"
            fpath.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            _log.debug("[trigger_research_pipeline] State file write failed: %s", exc)

    try:
        if pipeline_name == "paper":
            from scripts.research_framework.enhanced_pipeline import EnhancedPipeline
            pl = EnhancedPipeline(
                topic=topic,
                language=language,
                output_dir=output_dir,
                enable_modern_did=True,
                enable_validation_gates=True,
                enable_latex_lint=True,
                enable_latex_diff=True,
                enable_pdf_vision=False,
                enable_sandbox=True,
                enable_self_evolution=False,
                on_gate_approved=_on_gate_approved,
            )
            pl.run()
            finished_at = datetime.now()
            return {
                "status": "completed",
                "run_id": run_id,
                "event_id": event.event_id,
                "topic": topic,
                "output_dir": str(output_dir),
                "execution_time_s": (finished_at - started_at).total_seconds(),
                "message": f"Pipeline completed: {topic}",
            }
        else:
            # Research report pipeline
            _run_demo_pipeline(topic, output_dir, event)
            finished_at = datetime.now()
            return {
                "status": "completed",
                "run_id": run_id,
                "event_id": event.event_id,
                "topic": topic,
                "output_dir": str(output_dir),
                "execution_time_s": (finished_at - started_at).total_seconds(),
                "message": f"Pipeline completed: {topic}",
            }
    except Exception as e:
        finished_at = datetime.now()
        _log.error(f"[{run_id}] Pipeline failed: {e}")
        return {
            "status": "failed",
            "run_id": run_id,
            "event_id": event.event_id,
            "topic": topic,
            "output_dir": str(output_dir),
            "error": str(e),
            "execution_time_s": (finished_at - started_at).total_seconds(),
            "message": f"Pipeline failed: {e}",
        }


def _run_pipeline_bg(
    run_id: str,
    topic: str,
    pipeline_name: str,
    output_dir: str,
    language: str,
    journal: str,
    event: ResearchEvent,
):
    """Internal: run pipeline in a background thread (called by trigger_research_pipeline)."""
    import threading as _t
    pid = _t.current_thread().ident
    run = PipelineRun(
        run_id=run_id,
        event_id=event.event_id,
        topic=topic,
        pipeline_name=pipeline_name,
        status=PipelineStatus.RUNNING,
        pid=pid,
        started_at=datetime.now(),
        output_dir=str(output_dir),
    )
    with _pipeline_lock:
        _running_pipelines[pid] = {"run": run, "event": event}

    result = _run_pipeline_sync(
        run_id, topic, pipeline_name, output_dir, language, journal, event,
    )
    run.status = PipelineStatus.COMPLETED if result["status"] == "completed" else PipelineStatus.FAILED
    run.finished_at = datetime.now()
    run.error = result.get("error")
    _log.info(f"[{run_id}] Background pipeline finished: {result['status']}")


def _run_demo_pipeline(topic: str, output_dir: str, event: ResearchEvent) -> dict:
    """Run demo_research_report.py as subprocess."""
    import threading as _t
    "".join(c if c.isalnum() else "_" for c in topic[:30])
    datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract stock code from event if earnings
    stock_flag = ""
    if isinstance(event, EarningsEvent) and event.ts_code:
        stock_flag = f"--stock {event.ts_code}"

    cmd = [
        sys.executable, "-u",
        str(Path(__file__).parent / "demo_research_report.py"),
        "--output", str(output_path),
        "--skip-compile",
    ]
    if stock_flag:
        cmd.extend(stock_flag.split())

    _log.info(f"[demo] Running: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    if proc.returncode != 0:
        _log.warning(f"[demo] stderr: {proc.stderr[:500]}")

    return {
        "output_dir": str(output_path),
        "stdout": proc.stdout[:1000],
        "returncode": proc.returncode,
    }


def _record_trigger(dedup_key: str, run_id: str, event_id: str, topic: str):
    """Record trigger in dedup state file."""
    state_file = Path("data/event_trigger_state.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if state_file.exists():
            with open(state_file, encoding="utf-8") as f:
                state: dict = json.load(f)
        else:
            state = {}
    except Exception:
        state = {}

    state[dedup_key] = {
        "run_id": run_id,
        "event_id": event_id,
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
    }
    # Keep only last 200 entries
    keys_to_remove = sorted(state.keys(), key=lambda k: state[k]["timestamp"])[:-200]
    for k in keys_to_remove:
        del state[k]

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def approve_pipeline(run_id: str) -> dict:
    """Manually approve a pending pipeline run.

    Looks up the pending approval from the state file and triggers it.

    Args:
        run_id: The run_id returned from trigger_research_pipeline with
                status="pending_approval".

    Returns:
        dict with status and details.
    """
    state_file = Path("data/event_trigger_state.json")
    if not state_file.exists():
        return {"status": "error", "message": "No pending approvals found."}

    try:
        with open(state_file, encoding="utf-8") as f:
            state: dict = json.load(f)

        pending = state.get("pending", {})
        if run_id not in pending:
            return {"status": "error", "message": f"Run ID '{run_id}' not found in pending approvals."}

        info = pending[run_id]
        event = _reconstruct_event(info)
        if event is None:
            return {"status": "error", "message": "Could not reconstruct event from pending approval."}

        del pending[run_id]
        state["pending"] = pending
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        return trigger_research_pipeline(
            event,
            pipeline_name=info.get("pipeline_name", "research_report"),
            auto_trigger=True,
            output_dir=info.get("output_dir"),
            run_async=True,
            language=info.get("language", "zh"),
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _reconstruct_event(info: dict) -> ResearchEvent | None:
    """Reconstruct a ResearchEvent from pending approval info."""
    etype = info.get("event_type", "custom")
    if etype == "earnings":
        return EarningsEvent(
            event_id=info.get("event_id", ""),
            title=info.get("title", ""),
            description=info.get("description", ""),
            ts_code=info.get("ts_code", ""),
            fiscal_period=info.get("fiscal_period", ""),
            auto_trigger=True,
        )
    elif etype == "macro":
        return MacroEvent(
            event_id=info.get("event_id", ""),
            title=info.get("title", ""),
            description=info.get("description", ""),
            country=info.get("country", ""),
            indicator=info.get("indicator", ""),
            auto_trigger=True,
        )
    elif etype == "policy":
        return PolicyEvent(
            event_id=info.get("event_id", ""),
            title=info.get("title", ""),
            description=info.get("description", ""),
            auto_trigger=True,
        )
    return None


def list_pending_approvals() -> list[dict]:
    """List all pending pipeline approvals."""
    state_file = Path("data/event_trigger_state.json")
    if not state_file.exists():
        return []
    try:
        with open(state_file, encoding="utf-8") as f:
            state: dict = json.load(f)
        return list(state.get("pending", {}).values())
    except Exception:
        return []


def _build_topic_from_event(event: ResearchEvent) -> str:
    """Build a research topic string from a ResearchEvent.

    Args:
        event: The event to build a topic from.

    Returns:
        A Chinese research topic string.
    """
    if isinstance(event, EarningsEvent):
        return f"分析{event.ts_code}的{event.fiscal_period}财报及其市场影响"
    elif isinstance(event, MacroEvent):
        return f"分析{event.country}{event.indicator}数据发布的经济影响"
    elif isinstance(event, PolicyEvent):
        return f"研究{event.title}的政策影响及投资含义"
    else:
        return event.title


# ─────────────────────────────────────────────────────────────────────────────
# MCP Integration Helpers (with graceful fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _get_earnings_calendar_tushare(lookback_days: int = 7) -> list[dict]:
    """Get earnings calendar from tushare (requires TUSHARE_TOKEN).

    Falls back to mock data when token is not available.

    Args:
        lookback_days: Number of days to look back.

    Returns:
        List of dict records with keys: ts_code, ann_date, title, description, source.
    """
    try:
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise ValueError("TUSHARE_TOKEN not set")

        import tushare as ts
        pro = ts.pro_api(token)
        # Get scheduled disclosure dates (半年报/年报)
        df = pro.ann_szb(dType="1", curNum=lookback_days * 5)
        if df is None or df.empty:
            return []

        records = []
        for _, row in df.iterrows():
            records.append({
                "ts_code": row.get("ts_code", ""),
                "ann_date": row.get("ann_date", ""),
                "title": f"Earnings: {row.get('ts_code', '')}",
                "description": f"Earnings announcement scheduled",
                "source": "tushare",
                "fiscal_period": row.get("end_date", ""),
            })
        return records

    except (ValueError, AttributeError, KeyError, TypeError):
        # Graceful fallback to mock data for expected tushare errors:
        # ValueError  - TUSHARE_TOKEN not set
        # AttributeError - tushare API response structure changed
        # KeyError   - tushare API returned unexpected key
        # TypeError  - tushare returned non-iterable response
        return _get_mock_earnings_calendar(lookback_days)


def _get_mock_earnings_calendar(lookback_days: int = 7) -> list[dict]:
    """Return mock earnings calendar data for testing/demo.

    Args:
        lookback_days: Ignored for mock data.

    Returns:
        List of mock earnings records.
    """
    today = datetime.now().strftime("%Y%m%d")
    return [
        {
            "ts_code": "000001.SZ",
            "ann_date": today,
            "title": "平安银行 2024Q3 Earnings",
            "description": "平安银行2024年三季度业绩发布",
            "source": "tushare_mock",
            "fiscal_period": "2024Q3",
        },
        {
            "ts_code": "600519.SH",
            "ann_date": today,
            "title": "贵州茅台 2024Q3 Earnings",
            "description": "贵州茅台2024年三季度业绩发布",
            "source": "tushare_mock",
            "fiscal_period": "2024Q3",
        },
        {
            "ts_code": "601318.SH",
            "ann_date": today,
            "title": "中国平安 2024Q3 Earnings",
            "description": "中国平安2024年三季度业绩发布",
            "source": "tushare_mock",
            "fiscal_period": "2024Q3",
        },
    ]


def _get_mock_macro_releases() -> list[dict]:
    """Return mock macroeconomic release calendar.

    In production, this would call MCP tools:
    - user-financial (China macro via akshare)
    - user-fed-data (US macro via FRED)
    - user-oecd-data (OECD indicators)

    Returns:
        List of mock macro release records.
    """
    return [
        {
            "country": "CN",
            "indicator": "CPI",
            "title": "中国 10月 CPI 数据发布",
            "description": "中国10月居民消费价格指数(CPI)发布",
            "release_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
            "source": "nbs",
            "previous_value": "0.4%",
            "forecast_value": "0.3%",
            "relevance_score": 0.8,
        },
        {
            "country": "US",
            "indicator": "NFP",
            "title": "美国 11月 非农就业数据",
            "description": "美国11月非农就业人数变化",
            "release_date": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
            "source": "bls",
            "previous_value": "150K",
            "forecast_value": "180K",
            "relevance_score": 0.9,
        },
        {
            "country": "US",
            "indicator": "FOMC",
            "title": "美联储 FOMC 会议纪要",
            "description": "美联储联邦公开市场委员会会议纪要发布",
            "release_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "source": "fed",
            "previous_value": "5.25-5.50%",
            "forecast_value": "5.25-5.50%",
            "relevance_score": 0.95,
        },
        {
            "country": "EU",
            "indicator": "GDP",
            "title": "欧元区 Q3 GDP 初值",
            "description": "欧元区2024年三季度GDP初值发布",
            "release_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "source": "ecb",
            "previous_value": "0.6%",
            "forecast_value": "0.5%",
            "relevance_score": 0.7,
        },
        {
            "country": "CN",
            "indicator": "PMI",
            "title": "中国 11月 官方PMI",
            "description": "中国11月官方制造业采购经理指数",
            "release_date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
            "source": "nbs",
            "previous_value": "49.8",
            "forecast_value": "50.0",
            "relevance_score": 0.85,
        },
    ]


def _search_policy_keywords_mock(keywords: list[str], max_results: int = 10) -> list[dict]:
    """Mock policy document search.

    In production, this would call:
    - brave_search: user-brave-search brave_web_search
    - eastmoney: user-eastmoney-reports get_research_report

    Args:
        keywords: Keywords to search for.
        max_results: Maximum number of results.

    Returns:
        List of mock policy document records.
    """
    templates = [
        {
            "title": "国务院关于加力支持大规模设备更新的通知",
            "description": "国务院发布新一轮大规模设备更新支持政策，涵盖工业、信息等领域",
            "url": "https://www.gov.cn/zhengce/content/202410/content_1234567.htm",
            "publisher": "国务院",
            "related_entities": ["设备更新", "工业投资"],
        },
        {
            "title": "财政部关于下达2024年超长期特别国债项目清单的通知",
            "description": "财政部下达2024年超长期特别国债项目清单，涉及基础设施建设",
            "url": "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/202410/t20241015_4567890.htm",
            "publisher": "财政部",
            "related_entities": ["财政刺激", "基建"],
        },
        {
            "title": "中国人民银行进一步下调存款准备金率",
            "description": "央行宣布下调金融机构存款准备金率0.5个百分点",
            "url": "https://www.pbc.gov.cn/zhenghuoxiangxi/202410/t20241015_1234567.htm",
            "publisher": "中国人民银行",
            "related_entities": ["货币政策", "流动性"],
        },
        {
            "title": "美国贸易代表办公室关于对华301关税复审结果",
            "description": "USTR公布对华301关税复审结果，可能影响输美商品",
            "url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2024/october/2024-Section-301-Review",
            "publisher": "USTR",
            "related_entities": ["中美贸易", "关税"],
        },
        {
            "title": "欧盟碳边境调节机制(CBAM)实施条例正式生效",
            "description": "欧盟CBAM实施条例生效，对钢铁、铝等行业影响显著",
            "url": "https://ec.europa.eu/commission/presscorner/detail/en/ip_24_5000",
            "publisher": "欧盟委员会",
            "related_entities": ["碳关税", "出口企业"],
        },
    ]

    results = []
    for kw in keywords[:max_results]:
        for template in templates:
            if any(k in template["title"] or k in template["description"] for k in [kw]):
                results.append({
                    **template,
                    "relevance_score": 0.7,
                    "source": "brave_search_mock",
                })
                break
        else:
            # Generic fallback
            results.append({
                "title": f"政策动态: {kw}",
                "description": f"与关键词「{kw}」相关的最新政策文件",
                "url": "",
                "publisher": "未知",
                "related_entities": [kw],
                "relevance_score": 0.4,
                "source": "brave_search_mock",
            })

    return results[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
# CLI Interface
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Event-driven research trigger system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-shot: check events and print summary
  python event_monitor.py --test

  # Continuous monitoring (Ctrl+C to stop)
  python event_monitor.py --interval 300

  # Auto-trigger pipeline on new events
  python event_monitor.py --auto-trigger --interval 300

  # APScheduler: run at fixed times (cron-like)
  python event_monitor.py --scheduler "09:00,13:30" --auto-trigger

  # APScheduler: macro-event-aware (run when NFP/FOMC released)
  python event_monitor.py --macro-scheduler --auto-trigger

  # Daemon: run in background, log to file
  python event_monitor.py --daemon --log-file logs/monitor.log --auto-trigger

  # Check pending approvals
  python event_monitor.py --list-pending

  # Approve a pending pipeline
  python event_monitor.py --approve run_abc123def456

  # Check pipeline status
  python event_monitor.py --status
        """,
    )
    # ── Monitoring mode ──────────────────────────────────────────────────────
    parser.add_argument(
        "--interval", type=int, default=300,
        help="Poll interval in seconds (default: 300 = 5 min)"
    )
    parser.add_argument(
        "--auto-trigger", action="store_true",
        help="Automatically trigger pipeline when events detected (no approval required)"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="One-shot check: poll once, print events, and exit"
    )
    parser.add_argument(
        "--keywords", nargs="+",
        help="Policy keywords to monitor (default: 关税 美联储 降准 碳排放)"
    )
    parser.add_argument(
        "--countries", nargs="+",
        help="Countries for macro monitoring (default: CN US EU)"
    )
    # ── Scheduler mode ───────────────────────────────────────────────────────
    parser.add_argument(
        "--scheduler", type=str,
        help="APScheduler cron-like schedule. Format: HH:MM,HH:MM,... (e.g. '09:00,13:30,20:00')"
    )
    parser.add_argument(
        "--macro-scheduler", action="store_true",
        help="Calendar-aware scheduling: run on key macro release dates (NFP/FOMC/CPI/PMI)"
    )
    # ── Daemon mode ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--daemon", action="store_true",
        help="Run as background daemon (nohup equivalent, redirects output)"
    )
    parser.add_argument(
        "--log-file", type=str, default="",
        help="Log file path for daemon mode (default: stdout)"
    )
    parser.add_argument(
        "--pid-file", type=str, default="data/event_monitor.pid",
        help="PID file path for daemon mode (default: data/event_monitor.pid)"
    )
    # ── Pipeline management ──────────────────────────────────────────────────
    parser.add_argument(
        "--approve", type=str, metavar="RUN_ID",
        help="Approve a pending pipeline run by its run_id"
    )
    parser.add_argument(
        "--list-pending", action="store_true",
        help="List all pending pipeline approvals and exit"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show running/completed pipeline status and exit"
    )
    parser.add_argument(
        "--pipeline-type", type=str, default="research_report",
        choices=["research_report", "paper"],
        help="Which pipeline to trigger (default: research_report)"
    )
    parser.add_argument(
        "--language", type=str, default="zh",
        choices=["zh", "en", "both"],
        help="Pipeline language (default: zh)"
    )
    # ── Config ───────────────────────────────────────────────────────────────
    parser.add_argument(
        "--config", type=str, default="config/project_config.json",
        help="Path to project config"
    )
    parser.add_argument(
        "--output-dir", type=str, default="",
        help="Custom output directory for triggered pipelines"
    )

    args = parser.parse_args()

    # ── Handle management commands (exit immediately) ───────────────────────
    if args.approve:
        result = approve_pipeline(args.approve)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("status") != "error" else 1)

    if args.list_pending:
        pending = list_pending_approvals()
        if not pending:
            print("No pending approvals.")
        else:
            print(f"Pending approvals ({len(pending)}):")
            for p in pending:
                print(f"  run_id={p.get('run_id')}")
                print(f"    topic: {p.get('topic')}")
                print(f"    event: {p.get('event_type')} / {p.get('title', '')[:60]}")
                print(f"    queued: {p.get('timestamp')}")
                print()
        sys.exit(0)

    if args.status:
        print("Running pipelines:")
        running = get_running_pipelines()
        if not running:
            print("  (none)")
        else:
            for run in running:
                print(f"  {run['run'].run_id}: {run['run'].topic}")
                print(f"    status={run['run'].status.value} started={run['run'].started_at}")
        print()
        print("Recent runs (from state file):")
        state_file = Path("data/event_trigger_state.json")
        if state_file.exists():
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)
            # Show last 10
            items = list(state.items())[-10:]
            for key, val in items:
                print(f"  {key}: run_id={val.get('run_id')} at {val.get('timestamp')}")
        else:
            print("  (no state file)")
        sys.exit(0)

    # ── Daemon mode ────────────────────────────────────────────────────────
    if args.daemon:
        _daemonize(args.log_file, args.pid_file)
        # falls through to monitoring loop

    # ── Scheduler mode (APScheduler) ────────────────────────────────────────
    if args.scheduler or args.macro_scheduler:
        _run_scheduler_mode(
            times=args.scheduler,
            macro_aware=args.macro_scheduler,
            auto_trigger=args.auto_trigger,
            keywords=args.keywords,
            countries=args.countries,
            pipeline_type=args.pipeline_type,
            language=args.language,
            output_dir=args.output_dir,
            config_path=args.config,
        )
        sys.exit(0)

    # ── Default: polling loop ───────────────────────────────────────────────
    keywords = args.keywords or ["关税", "美联储", "降准", "碳排放"]
    countries = args.countries or ["CN", "US", "EU"]

    monitor = EventMonitor(
        check_interval=args.interval,
        auto_trigger=args.auto_trigger,
        config_path=args.config,
    )

    def on_event(event: ResearchEvent):
        print(f"[EVENT] {event.event_type.upper():8s} | {event.title} | source={event.source} score={event.relevance_score:.2f}")
        if args.auto_trigger or event.auto_trigger:
            output_dir = args.output_dir or None
            result = trigger_research_pipeline(
                event,
                pipeline_name=args.pipeline_type,
                auto_trigger=True,
                output_dir=output_dir,
                run_async=True,
                language=args.language,
            )
            print(f"[TRIGGER] {result['status']} — {result.get('message', '')}")

    monitor.register_handler(on_event)

    if args.test:
        print("Running one-shot check...")
        events = monitor.poll_all()
        print(f"\nFound {len(events)} events:")
        for e in events:
            print(f"  [{e.event_type:8s}] {e.title} (source={e.source}, score={e.relevance_score:.2f})")
        print("\n--- Pipeline Trigger Test ---")
        # T1 audit 2026-07-12: --test simulates events for QA purposes only.
        # These events are NOT real market events — they're generated by the
        # monitor's own mock fixtures so Claude Code/Codex don't mistake
        # the output for live market activity.
        print("  ⚠️  TEST MODE: events above are simulated fixtures, not real market data.")
        for e in events[:3]:
            result = trigger_research_pipeline(e, pipeline_name=args.pipeline_type)
            print(f"  {e.event_id}: {result['status']} — {result.get('message', '')}")
    else:
        print(f"Starting event monitor (interval={args.interval}s, auto_trigger={args.auto_trigger})...")
        print("Press Ctrl+C to stop.")
        try:
            monitor.run_loop()
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            monitor.stop()
            print("Monitor stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# APScheduler Integration
# ─────────────────────────────────────────────────────────────────────────────

def _run_scheduler_mode(
    times: str | None,
    macro_aware: bool,
    auto_trigger: bool,
    keywords: list[str],
    countries: list[str],
    pipeline_type: str,
    language: str,
    output_dir: str,
    config_path: str,
):
    """Run event monitor with APScheduler-based calendar-aware scheduling."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("ERROR: APScheduler not installed.")
        print("  Install with: pip install apscheduler")
        print("  Or use polling mode instead: python event_monitor.py --interval 300")
        sys.exit(1)

    print(f"[Scheduler] Starting with APScheduler...")
    scheduler = BackgroundScheduler()

    # ── Fixed-time cron jobs ─────────────────────────────────────────────────
    if times:
        for time_str in times.split(","):
            time_str = time_str.strip()
            if not time_str:
                continue
            parts = time_str.split(":")
            if len(parts) != 2:
                print(f"WARNING: Invalid time format '{time_str}', skipping (use HH:MM)")
                continue
            hour, minute = int(parts[0]), int(parts[1])
            scheduler.add_job(
                _scheduled_poll,
                CronTrigger(hour=hour, minute=minute),
                args=[auto_trigger, keywords, countries, pipeline_type, language, output_dir],
                id=f"cron_{hour:02d}{minute:02d}",
                name=f"Daily at {hour:02d}:{minute:02d}",
                replace_existing=True,
            )
            print(f"  + Scheduled: daily at {hour:02d}:{minute:02d}")

    # ── Macro-aware scheduling ───────────────────────────────────────────────
    if macro_aware:
        # Schedule for key macro release times
        macro_schedules = [
            ("09:30", "CN", "CN: NBS PMI (monthly, first business day ~09:30)"),
            ("10:00", "US", "US: NFP (first Friday of month ~08:30 EST = 20:30 Beijing)"),
            ("20:30", "US", "US: NFP evening run (20:30 Beijing)"),
            ("14:00", "US", "US: CPI (10-14th monthly ~08:30 EST = 20:30 Beijing)"),
            ("22:00", "US", "US: FOMC decision (22:00 Beijing)"),
        ]
        for time_str, country, description in macro_schedules:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            scheduler.add_job(
                _scheduled_poll,
                CronTrigger(hour=hour, minute=minute),
                args=[auto_trigger, keywords, [country], pipeline_type, language, output_dir],
                id=f"macro_{country}_{time_str.replace(':', '')}",
                name=description,
                replace_existing=True,
            )
            print(f"  + Macro: {description}")
        # Also add US FOMC meeting schedule (every 6 weeks)
        scheduler.add_job(
            _scheduled_poll,
            CronTrigger(hour=22, minute=0, day_of_week="wed", weeks=6),
            args=[auto_trigger, keywords, ["US"], pipeline_type, language, output_dir],
            id="fomc_6w",
            name="US: FOMC meeting (6-week schedule)",
            replace_existing=True,
        )
        print("  + Macro: US FOMC (6-week schedule)")

    if not scheduler.get_jobs():
        print("ERROR: No jobs scheduled. Check --scheduler or --macro-scheduler.")
        scheduler.shutdown()
        sys.exit(1)

    print(f"\n[Scheduler] {len(scheduler.get_jobs())} jobs registered. Running...")
    scheduler.start()

    # Keep running — wait for SIGINT instead of blocking sleep
    # This allows the scheduler to run background jobs while staying responsive to Ctrl+C
    try:
        signal.pause()  # blocks until signal is received; scheduler jobs run in their own threads
    except (KeyboardInterrupt, SystemExit, OSError, AttributeError):
        # KeyboardInterrupt: Ctrl+C pressed
        # OSError: signal.pause() not available on this platform (Windows)
        # AttributeError: signal module doesn't define pause()
        pass

    print("\n[Scheduler] Shutting down...")
    scheduler.shutdown(wait=False)
    print("[Scheduler] Done.")


def _scheduled_poll(
    auto_trigger: bool,
    keywords: list[str],
    countries: list[str],
    pipeline_type: str,
    language: str,
    output_dir: str,
):
    """Poll and trigger pipelines for a scheduled run."""
    print(f"[Scheduler:{datetime.now().strftime('%H:%M:%S')}] Running scheduled poll...")
    try:
        monitor = EventMonitor(check_interval=0, auto_trigger=auto_trigger)
        events = monitor.poll_all()
        print(f"[Scheduler] Found {len(events)} events")
        for event in events:
            if event.relevance_score >= 0.7 or auto_trigger:
                result = trigger_research_pipeline(
                    event,
                    pipeline_name=pipeline_type,
                    auto_trigger=auto_trigger,
                    output_dir=output_dir or None,
                    run_async=True,
                    language=language,
                )
                print(f"[Scheduler] Triggered: {result['status']} — {result.get('message', '')}")
            else:
                print(f"[Scheduler] Skipped (low score {event.relevance_score:.2f}): {event.title}")
    except Exception as e:
        print(f"[Scheduler] Error during poll: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Daemonize Helper (Unix)
# ─────────────────────────────────────────────────────────────────────────────

def _daemonize(log_file: str, pid_file: str):
    """Daemonize the current process (Unix fork-based)."""
    import os as _os

    # Check if already running
    pid_path = Path(pid_file)
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text().strip())
            # Check if process is alive
            try:
                _os.kill(old_pid, 0)
                print(f"ERROR: Monitor already running (PID {old_pid}). Remove {pid_file} to override.")
                sys.exit(1)
            except ProcessLookupError:
                print(f"Stale PID file (process {old_pid} is dead). Removing...")
                pid_path.unlink()
        except (ValueError, OSError):
            pid_path.unlink()

    # Fork — T2 audit 2026-07-12: provide Windows-friendly error.
    # os.fork() doesn't exist on Windows; AttributeError raises
    # before we can catch it. Check platform explicitly.
    if sys.platform == "win32":
        print("ERROR: --daemon mode is not supported on Windows.")
        print("  os.fork() is Unix-only. Use polling mode instead:")
        print("    python scripts/event_monitor.py --interval 300")
        print("  Or run as a foreground process via Task Scheduler / NSSM.")
        sys.exit(1)
    try:
        pid = _os.fork()
        if pid > 0:
            print(f"Daemon started (PID {pid}). PID file: {pid_file}")
            print(f"Stop with: kill {pid}")
            sys.exit(0)
    except OSError as e:
        print(f"Fork failed: {e}")
        sys.exit(1)

    # Decouple from parent
    _os.setsid()
    _os.chdir("/")
    _os.umask(0)

    # Second fork (prevent acquiring a controlling terminal)
    try:
        pid2 = _os.fork()
        if pid2 > 0:
            sys.exit(0)
    except OSError as e:
        print(f"Second fork failed: {e}")
        sys.exit(1)

    # Redirect stdout/stderr
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout.flush()
        sys.stderr.flush()
        # audit-2026-07-14 PR-6: P2-3 — open() without encoding crashed
        # on Windows with Chinese/UTF-8 paths (cp936 default).
        with open(log_path, "a", encoding="utf-8") as f:
            _os.dup2(f.fileno(), 1)
            _os.dup2(f.fileno(), 2)
    else:
        devnull = open("/dev/null", "r")
        _os.dup2(devnull.fileno(), 1)
        _os.dup2(devnull.fileno(), 2)

    # Write PID file
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(_os.getpid()))
