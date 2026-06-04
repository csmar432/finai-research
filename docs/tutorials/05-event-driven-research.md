# Tutorial 5: Event-Driven Research

> Automatically monitor financial events and trigger research pipelines.

---

## What is Event-Driven Research?

Event-driven research automates the research workflow by:

1. **Monitoring** — Watching for events (earnings, macro releases, policy changes)
2. **Detecting** — Identifying significant events matching your interests
3. **Triggering** — Launching research pipelines automatically
4. **Delivering** — Generating and delivering research reports

```
┌─────────────────────────────────────────────────────────────┐
│                      EventMonitor                            │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Earnings │  │  Macro   │  │ Policy   │  │ Custom   │  │
│  │ Calendar │  │ Releases │  │ Keywords │  │ Keywords │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │             │         │
│       └─────────────┴─────────────┴─────────────┘         │
│                           │                                │
│                    ┌──────▼──────┐                        │
│                    │  Research   │                        │
│                    │  Pipeline   │                        │
│                    └─────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## EventMonitor Class

### Initialization

```python
from scripts.event_monitor import EventMonitor

monitor = EventMonitor(
    check_interval=300,   # Check every 5 minutes
    auto_trigger=False,  # Require human approval before running pipeline
    config_path="config/project_config.json"
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `check_interval` | int | 300 | Seconds between polling cycles |
| `auto_trigger` | bool | False | Auto-run pipeline without approval |
| `config_path` | str | `config/project_config.json` | Project configuration file |

---

## Running the Monitor

### Test Mode (one-shot, no loop)

```bash
python scripts/event_monitor.py --interval 60 --test
```

### Production Mode (continuous)

```bash
# Run continuously, checking every 5 minutes
python scripts/event_monitor.py --interval 300

# Run with auto-trigger (no approval required)
python scripts/event_monitor.py --interval 300 --auto-trigger

# Custom policy keywords
python scripts/event_monitor.py --interval 300 --keywords 关税 美联储 降准
```

> Note: there is **no `--check-once` flag**. Use `--test` for a one-shot check.

### CLI Help

```bash
python scripts/event_monitor.py --help
```

---

## Supported Event Types

### 1. Earnings Calendar

```python
from scripts.event_monitor import EventMonitor, EarningsEvent

monitor = EventMonitor(check_interval=300)

def on_earnings(event: EarningsEvent):
    print(f"Earnings released: {event.ts_code} — {event.fiscal_period}")
    # Trigger research pipeline here

monitor.register_handler(on_earnings)
events = monitor.check_earnings_calendar(lookback_days=7, top_n=20)
# Returns: list[EarningsEvent] with ts_code, ann_date, fiscal_period
```

**Detects**: Quarterly earnings releases, annual reports (via tushare).

> Requires `TUSHARE_TOKEN` to be set. Without it, returns mock data
> (`source="tushare_mock"`).

### 2. Macro Releases

```python
from scripts.event_monitor import EventMonitor, MacroEvent

monitor = EventMonitor(check_interval=300)

def on_macro(event: MacroEvent):
    print(f"Macro event: {event.country} {event.indicator}")

monitor.register_handler(on_macro)

# Check all countries
events = monitor.check_macro_releases()

# Filter by country
events = monitor.check_macro_releases(countries=["US", "CN"])
# Returns: list[MacroEvent] with country, indicator, release_date
```

**Detects**: GDP, CPI, PPI, PMI, NFP, FOMC announcements.

> Currently returns mock data (MCP integration planned). Each event has
> `source="fed"`/`"nbs"`/`"bls"` depending on origin.

### 3. Policy Keywords

```python
from scripts.event_monitor import EventMonitor, PolicyEvent

monitor = EventMonitor(check_interval=300)

def on_policy(event: PolicyEvent):
    print(f"Policy: {event.title} — {event.url}")

monitor.register_handler(on_policy)

# Check with default keywords (from config or ["关税","美联储","碳排放","降准","财政政策"])
events = monitor.check_policy_keywords()

# Search with custom keywords
events = monitor.check_policy_keywords(
    keywords=["碳排放权交易", "绿色金融", "数字人民币"],
    max_results=10
)
# Returns: list[PolicyEvent] with title, url, publisher
```

---

## Handler Registration

The `EventMonitor` uses a **single unified handler** pattern. All event types
flow through the same handler function, which you register with `register_handler()`.

> **Do NOT use `add_event_handler(event_type=...)`** — that method does not exist.
> **Do NOT use `add_custom_event()`** — that method does not exist.
> **Do NOT use `monitor.start()`** — use `monitor.run_loop()` instead.

```python
from scripts.event_monitor import EventMonitor
from scripts.event_monitor import EarningsEvent, MacroEvent, PolicyEvent

monitor = EventMonitor(check_interval=300)

def my_handler(event):
    """Single handler for all event types."""
    print(f"[{event.event_type.upper()}] {event.title} from {event.source}")
    if isinstance(event, EarningsEvent):
        print(f"  Stock: {event.ts_code}, Period: {event.fiscal_period}")
    elif isinstance(event, MacroEvent):
        print(f"  Country: {event.country}, Indicator: {event.indicator}")
    elif isinstance(event, PolicyEvent):
        print(f"  Publisher: {event.publisher}, URL: {event.url}")

monitor.register_handler(my_handler)
```

---

## Pipeline Integration

### Triggering Research Pipeline

```python
from scripts.event_monitor import EventMonitor, trigger_research_pipeline

monitor = EventMonitor(check_interval=300, auto_trigger=False)

def on_event(event):
    result = trigger_research_pipeline(event, pipeline_name="research_report")
    print(result)

monitor.register_handler(on_event)

# Trigger with auto_trigger=True events
events = monitor.poll_all()
# Returns list[ResearchEvent] and also populates internal queue
```

`trigger_research_pipeline()` returns:

```python
# When auto_trigger=False (default):
{"status": "pending_approval", "event_id": "...", "message": "..."}

# When auto_trigger=True:
{"status": "triggered", "pipeline_run_id": "...", "topic": "...", "message": "..."}
```

### Integrating with AgentPipeline

```python
from scripts.event_monitor import EventMonitor
from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

monitor = EventMonitor(check_interval=300, auto_trigger=False)
pipeline = AgentPipeline(config=AgentPipelineConfig(topic=""))

def on_event(event):
    from scripts.event_monitor import _build_topic_from_event
    topic = _build_topic_from_event(event)
    config = AgentPipelineConfig(topic=topic)
    pipeline.config = config
    result = pipeline.run(topic=topic)
    print(f"Pipeline done: {result.success}")

monitor.register_handler(on_event)

# Run one cycle
events = monitor.poll_all()
```

---

## ResearchEvent Structure

Each event type has its own dataclass with specific fields:

### EarningsEvent

```python
from scripts.event_monitor import EarningsEvent
from datetime import datetime

event = EarningsEvent(
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
print(f"{event.ts_code} — {event.fiscal_period}")  # 000001.SZ — 2024Q3
```

### MacroEvent

```python
from scripts.event_monitor import MacroEvent
from datetime import datetime

event = MacroEvent(
    event_id="macro_US_NFP_20241101",
    event_type="macro",
    title="美国 11月 非农就业数据",
    description="美国11月非农就业人数变化",
    timestamp=datetime.now(),
    source="bls",
    country="US",
    indicator="NFP",
    previous_value="150K",
    forecast_value="180K",
    report_date="2024-11-01",
)
print(f"{event.country} {event.indicator}: {event.previous_value} → {event.forecast_value}")
```

### PolicyEvent

```python
from scripts.event_monitor import PolicyEvent
from datetime import datetime

event = PolicyEvent(
    event_id="policy_abc12345",
    event_type="policy",
    title="国务院关于加力支持大规模设备更新的通知",
    description="国务院发布新一轮大规模设备更新支持政策",
    timestamp=datetime.now(),
    source="brave_search",
    url="https://www.gov.cn/test",
    publisher="国务院",
)
print(f"{event.publisher}: {event.title}")
```

---

## Queue Management

> **Do NOT use `get_events()`, `get_history()`, or `clear_events()`** —
> those methods do not exist.

```python
# Get all pending events in the queue
events = monitor.get_pending_events()

# Clear the queue
monitor.clear_queue()

# Check last poll timestamp
last = monitor.get_last_check()          # last "all" poll
last_us = monitor.get_last_check("US")  # last US-specific poll
```

---

## Configuration File

### project_config.json

The `check_interval` and policy keywords can be configured via
`config/project_config.json`:

```json
{
  "research": {
    "policy_keywords": ["碳排放权交易", "绿色金融", "数字人民币", "降准", "财政政策"]
  },
  "event_monitor": {
    "check_interval": 300,
    "auto_trigger": false
  }
}
```

---

## Example: Earnings Season Research

```python
"""
Automatically analyze research reports during earnings season.
"""

from scripts.event_monitor import (
    EventMonitor, EarningsEvent,
    trigger_research_pipeline, _build_topic_from_event
)
from scripts.demo_research_report import run_demo_pipeline

monitor = EventMonitor(check_interval=600)  # Check every 10 minutes

def on_earnings_release(event: EarningsEvent):
    """Trigger research when earnings are released."""
    print(f"Earnings released for {event.ts_code} — {event.fiscal_period}")

    # Run demo pipeline
    result = run_demo_pipeline(
        ts_code=event.ts_code,
        output_dir="papers/earnings"
    )
    print(f"Report generated: {result['status']}")
    return result

monitor.register_handler(on_earnings_release)

# One-shot test: poll once and process
events = monitor.poll_all()
print(f"Found {len(events)} events")
for event in events:
    if isinstance(event, EarningsEvent):
        on_earnings_release(event)

# For continuous monitoring, run in a background thread:
# import threading
# threading.Thread(target=monitor.run_loop, daemon=True).start()
```

---

## Best Practices

1. **Set reasonable intervals**: Don't check too frequently (API rate limits).
   Default is 300s (5 minutes).
2. **Use approval gates**: Set `auto_trigger=False` for important pipelines
   so human review happens before expensive LLM calls.
3. **Deduplicate events**: `poll_all()` avoids adding duplicate event_ids
   to the queue automatically.
4. **Handle exceptions**: Handler exceptions are caught silently by
   `_notify_handlers()`. Use `try/except` inside your handler for robustness.
5. **Graceful fallback**: When `TUSHARE_TOKEN` is not set, earnings calendar
   returns mock data. Always check `event.source` to know if data is real.

---

## Next Steps

- [API Reference: EventMonitor](../api_reference.md#eventmonitor)
- [Tutorial 2: Financial Research Report](02-financial-report.md)
- [Setup Guide: MCP Server Configuration](../SETUP_GUIDE.md)
