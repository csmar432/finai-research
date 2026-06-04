"""Observability layer for the research agent pipeline.

Provides:
- Structured JSON logging (ELK-compatible)
- OpenTelemetry tracing with span management
- LangSmith integration for LLM tracing
- Prometheus-compatible metrics collection
- LLM-as-Judge evaluation framework

Usage:
    from scripts.core.observability import AgentObserver

    observer = AgentObserver(
        enable_langsmith=True,
        enable_otel=True,
        langsmith_api_key="...",
        otel_endpoint="http://localhost:4317",
    )

    with observer.start_span("data_analysis", agent="analyst"):
        result = gateway.generate(prompt)

    scores = observer.evaluate(test_cases)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Package Availability ───────────────────────────────────────────────────────

_OTEL_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    pass

# LangSmithTracer lives in langsmith_integration.py; provide a stub here so
# scripts/core/__init__.py can import it without triggering a circular import.
class LangSmithTracer:
    pass

# ─── Import centralized LangSmith tracer ─────────────────────────────────────
# Lazy import to avoid circular dependency at module load time
def _get_langsmith_tracer() -> Any:
    from scripts.core.langsmith_integration import get_tracer
    return get_tracer()


# ─── Structured Logging ─────────────────────────────────────────────────────────

_LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_LOGGER_NAME = "finai.observability"


class StructuredLogger:
    """
    JSON-formatted logger compatible with ELK stack.

    Output fields: timestamp, level, agent, task_id, session_id,
                   duration_ms, event_type, message, **extra
    """

    def __init__(
        self,
        name: str = _LOGGER_NAME,
        log_file: str = ".cache/logs/observability.jsonl",
        console: bool = True,
        min_level: str = "INFO",
    ):
        self.logger = logging.getLogger(name)
        level_val = _LOG_LEVELS.get(min_level.upper(), 20)
        self.logger.setLevel(level_val)
        self.logger.handlers.clear()

        self._session_id: str | None = None
        self._agent: str | None = None
        self._task_id: str | None = None
        self._lock = threading.Lock()

        # File handler (JSONL)
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(fh)

        # Console handler
        if console:
            ch = logging.StreamHandler()
            ch.setLevel(logging.WARNING)
            ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            self.logger.addHandler(ch)

    def bind(self, session_id: str | None = None, agent: str | None = None,
             task_id: str | None = None):
        """Set context vars for subsequent log entries."""
        self._session_id = session_id
        self._agent = agent
        self._task_id = task_id

    def log(self, level: str, message: str, **kwargs):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "agent": self._agent,
            "session_id": self._session_id,
            "task_id": self._task_id,
            "event_type": kwargs.pop("event_type", "log"),
            "message": message,
            **kwargs,
        }
        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, json.dumps(record, ensure_ascii=False, default=str))

    def debug(self, msg: str, **kw): self.log("DEBUG", msg, **kw)
    def info(self, msg: str, **kw): self.log("INFO", msg, **kw)
    def warn(self, msg: str, **kw): self.log("WARN", msg, **kw)
    def error(self, msg: str, **kw): self.log("ERROR", msg, **kw)


# ─── OpenTelemetry Tracing ─────────────────────────────────────────────────────

class OTelTracer:
    """
    Wrapper around OpenTelemetry SDK.

    Falls back to no-op operations if otel is not installed.
    """

    def __init__(self, service_name: str = "research-agent",
                 endpoint: str | None = None):
        self._enabled = _OTEL_AVAILABLE
        self._service_name = service_name
        self._provider: Any = None
        self._tracer: Any = None

        if self._enabled:
            resource = Resource.create({"service.name": service_name})
            self._provider = TracerProvider(resource=resource)

            if endpoint:
                try:
                    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
                    self._provider.add_span_processor(BatchSpanProcessor(exporter))
                except Exception:
                    pass
            else:
                self._provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )

            trace.set_tracer_provider(self._provider)
            self._tracer = trace.get_tracer(service_name)

    def start_span(self, name: str, **attrs) -> OtelSpan:
        if not self._enabled:
            return OtelSpan(None)
        try:
            span = self._tracer.start_span(name)
            for k, v in attrs.items():
                if v is not None:
                    span.set_attribute(k, str(v) if not isinstance(v, (int, float, bool)) else v)
            return OtelSpan(span)
        except Exception:
            return OtelSpan(None)

    @property
    def enabled(self) -> bool:
        return self._enabled


class OtelSpan:
    """Context manager for an OpenTelemetry span."""

    def __init__(self, _span: Any):
        self._span = _span
        self._start: float | None = None

    def __enter__(self):
        if self._span is not None:
            self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        if self._span is not None:
            if args[0] is not None and self._start is not None:
                self._span.set_status(Status(StatusCode.ERROR))
                duration_ms = (time.perf_counter() - self._start) * 1000
                self._span.set_attribute("error.duration_ms", duration_ms)
            self._span.end()

    def set_attribute(self, key: str, value: Any):
        if self._span is not None:
            self._span.set_attribute(key, value)

    def set_status(self, status: str):
        if self._span is not None and _OTEL_AVAILABLE:
            code = StatusCode.OK if status == "ok" else StatusCode.ERROR
            self._span.set_status(Status(code))

    def end(self):
        if self._span is not None:
            self._span.end()


# ─── Metrics Collection ─────────────────────────────────────────────────────────

class MetricsCollector:
    """
    In-process metrics: counters, histograms, gauges.

    Supports Prometheus text format export.
    """

    def __init__(self):
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    # Counters
    def inc(self, name: str, value: float = 1.0):
        with self._lock:
            self._counters[name] += value

    def cache_hit(self):
        self.inc("llm_cache_hits_total")

    def cache_miss(self):
        self.inc("llm_cache_misses_total")

    def record_error(self, label: str = "general"):
        self.inc(f"error_total{{type=\"{label}\"}}")

    # Histograms
    def observe(self, name: str, value: float):
        with self._lock:
            self._histograms[name].append(value)

    def record_latency(self, name: str, ms: float):
        self.observe(name, ms)
        self.observe(f"{name}_sec", ms / 1000)

    def record_tokens(self, count: int):
        self.observe("tokens_used_total", count)

    def record_cost(self, usd: float):
        self.observe("cost_usd_total", usd)

    # Gauges
    def set_gauge(self, name: str, value: float):
        with self._lock:
            self._gauges[name] = value

    def set_active_agents(self, count: int):
        self.set_gauge("active_agents", count)

    def set_queue_depth(self, depth: int):
        self.set_gauge("queue_depth", depth)

    # Export
    def prometheus_text(self) -> str:
        """Export all metrics in Prometheus text format."""
        with self._lock:
            lines = ["# HELP finai_info FinAI Research Agent metrics"]
            lines.append("# TYPE finai_info gauge")
            lines.append('finai_info{service="research-agent"} 1\n')

            for name, val in self._counters.items():
                safe_name = name.replace("{", "_").replace("}", "").replace('"', "")
                lines.append(f"# TYPE {safe_name} counter")
                lines.append(f"{safe_name} {val}\n")

            for name, vals in self._histograms.items():
                if not vals:
                    continue
                safe_name = name.replace("{", "_").replace("}", "").replace('"', "")
                lines.append(f"# TYPE {safe_name} histogram")
                lines.append(f"# HELP {safe_name}")
                total = sum(vals)
                lines.append(f"{safe_name}_sum {total}")
                lines.append(f"{safe_name}_count {len(vals)}")
                for pct in [50, 90, 95, 99]:
                    sorted_vals = sorted(vals)
                    idx = int(len(sorted_vals) * pct / 100)
                    lines.append(f"{safe_name}_p{pct} {sorted_vals[min(idx, len(sorted_vals)-1)]}")
                lines.append("")

            for name, val in self._gauges.items():
                safe_name = name.replace("{", "_").replace("}", "").replace('"', "")
                lines.append(f"# TYPE {safe_name} gauge")
                lines.append(f"{safe_name} {val}\n")

            return "\n".join(lines)


# ─── LLM-as-Judge Evaluation ───────────────────────────────────────────────────

@dataclass
class EvaluationResult:
    """Result of evaluating a single test case."""
    test_id: str
    input_: str
    expected: str
    actual: str
    accuracy: float
    citation_f1: float
    coherence_score: float
    completeness_score: float
    judge_reasoning: str
    passed: bool


@dataclass
class EvaluationReport:
    """Full evaluation report for a test suite."""
    total_cases: int
    passed_cases: int
    accuracy: float
    avg_citation_f1: float
    avg_coherence: float
    avg_completeness: float
    cases: list[EvaluationResult]


class LLMasJudge:
    """
    LLM-as-Judge evaluator using the AI router for actual scoring.

    Requires the AI router to be initialized with API keys.
    """

    def __init__(self, judge_model: str = "gpt-4o-mini"):
        self._judge_model = judge_model
        self._router = None
        try:
            from scripts.ai_router import AI
            self._router = AI
        except ImportError:
            pass

    def _extract_citations(self, text: str) -> set[str]:
        """Extract citation markers like [1], (Smith et al., 2020), [#123]."""
        import re
        patterns = [
            r'\[\d+\]',           # [1], [42]
            r'\(\w+ et al\., \d{4}\)',  # (Smith et al., 2020)
            r'\(#\d+\)',          # #123
            r'\[[\w\s]+, \d{4}\]',  # [Smith, 2020]
        ]
        cites = set()
        for pat in patterns:
            cites.update(re.findall(pat, text))
        return cites

    def _score_citation_f1(self, expected: str, actual: str) -> float:
        """Compute F1 between expected and actual citations."""
        exp_cites = self._extract_citations(expected)
        act_cites = self._extract_citations(actual)
        if not exp_cites and not act_cites:
            return 1.0
        if not exp_cites:
            return 0.0
        if not act_cites:
            return 0.0
        prec = len(exp_cites & act_cites) / len(act_cites) if act_cites else 0
        rec = len(exp_cites & act_cites) / len(exp_cites) if exp_cites else 0
        if prec + rec == 0:
            return 0.0
        return 2 * prec * rec / (prec + rec)

    def _score_coherence(self, text: str) -> float:
        """Simple heuristic coherence score based on structure."""
        if not text:
            return 0.0
        score = 1.0
        # Penalize if very short
        if len(text) < 50:
            score *= 0.5
        # Penalize if no paragraph breaks (seems like a run-on)
        if "\n\n" not in text and len(text) > 200:
            score *= 0.8
        return min(1.0, score)

    def _score_completeness(self, text: str, expected_keys: list[str]) -> float:
        """Check if text contains expected key concepts."""
        if not expected_keys:
            return 1.0
        text_lower = text.lower()
        found = sum(1 for k in expected_keys if k.lower() in text_lower)
        return found / len(expected_keys)

    def _llm_judge(
        self, test_id: str, input_: str, expected: str, actual: str
    ) -> dict[str, Any]:
        """
        Use LLM to judge quality and provide reasoning.

        Falls back to heuristics if router unavailable.
        """
        if self._router is None:
            return self._heuristic_judge(test_id, input_, expected, actual)

        try:
            prompt = f"""You are evaluating a research agent's output.

Test Case: {test_id}
Input: {input_}
Expected: {expected}
Actual Output: {actual}

Score the output on these dimensions (0.0 to 1.0):
1. accuracy: Does the output correctly address the input?
2. coherence_score: Is the output well-structured and clear?
3. completeness_score: Is the output complete and thorough?

Also explain your reasoning in 1-2 sentences.

Respond as JSON: {{"accuracy": float, "coherence_score": float, "completeness_score": float, "reasoning": str}}
"""
            result = self._router.chat(
                user_input=prompt,
                system_prompt="You are a strict academic evaluator. Respond only with valid JSON.",
                model=self._judge_model,
                temperature=0.0,
            )
            import json
            scores = json.loads(result.response)
            return {
                "accuracy": float(scores.get("accuracy", 0.5)),
                "coherence_score": float(scores.get("coherence_score", 0.5)),
                "completeness_score": float(scores.get("completeness_score", 0.5)),
                "reasoning": scores.get("reasoning", ""),
            }
        except Exception:
            return self._heuristic_judge(test_id, input_, expected, actual)

    def _heuristic_judge(
        self, test_id: str, input_: str, expected: str, actual: str
    ) -> dict[str, Any]:
        """Fallback heuristic scoring when LLM judge is unavailable."""
        citation_f1 = self._score_citation_f1(expected, actual)
        coherence = self._score_coherence(actual)
        completeness = self._score_completeness(actual, expected.split()[:5])

        # Basic text similarity as accuracy proxy
        exp_words = set(expected.lower().split())
        act_words = set(actual.lower().split())
        overlap = len(exp_words & act_words)
        total = len(exp_words | act_words)
        accuracy = overlap / total if total > 0 else 0.0

        return {
            "accuracy": accuracy,
            "coherence_score": coherence,
            "completeness_score": completeness,
            "reasoning": f"Heuristic fallback: accuracy={accuracy:.2f}, "
                         f"citation_f1={citation_f1:.2f}",
        }

    def evaluate_case(
        self,
        test_id: str,
        input_: str,
        expected: str,
        actual: str,
        expected_citations: list[str] | None = None,
    ) -> EvaluationResult:
        """Evaluate a single test case."""
        scores = self._llm_judge(test_id, input_, expected, actual)
        citation_f1 = self._score_citation_f1(expected, actual)
        coherence = scores.get("coherence_score", 0.5)
        completeness = scores.get("completeness_score", 0.5)
        accuracy = scores.get("accuracy", 0.5)

        # Override completeness if expected_citations provided
        if expected_citations:
            completeness = self._score_completeness(actual, expected_citations)

        passed = accuracy >= 0.7 and coherence >= 0.5 and completeness >= 0.5

        return EvaluationResult(
            test_id=test_id,
            input_=input_,
            expected=expected,
            actual=actual,
            accuracy=accuracy,
            citation_f1=citation_f1,
            coherence_score=coherence,
            completeness_score=completeness,
            judge_reasoning=scores.get("reasoning", ""),
            passed=passed,
        )

    def evaluate_suite(
        self,
        test_cases: list[dict],
        output_extractor: Callable[[Any], str] | None = None,
    ) -> EvaluationReport:
        """
        Run evaluation against a list of test cases.

        Each test_case dict should have:
        - id: str
        - input: str
        - expected: str
        - actual: str or callable -> str
        - expected_citations: list[str] (optional)
        """
        results: list[EvaluationResult] = []
        for tc in test_cases:
            actual = tc.get("actual")
            if callable(output_extractor) and actual is None:
                actual = output_extractor(tc.get("input"))
            if actual is None:
                actual = tc.get("output", "")

            result = self.evaluate_case(
                test_id=tc.get("id", str(uuid.uuid4())[:8]),
                input_=tc.get("input", ""),
                expected=tc.get("expected", ""),
                actual=str(actual),
                expected_citations=tc.get("expected_citations"),
            )
            results.append(result)

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        return EvaluationReport(
            total_cases=total,
            passed_cases=passed,
            accuracy=passed / total if total > 0 else 0.0,
            avg_citation_f1=sum(r.citation_f1 for r in results) / total if total > 0 else 0.0,
            avg_coherence=sum(r.coherence_score for r in results) / total if total > 0 else 0.0,
            avg_completeness=sum(r.completeness_score for r in results) / total if total > 0 else 0.0,
            cases=results,
        )


# ─── Main Facade ───────────────────────────────────────────────────────────────

class Span:
    """
    Unified span context manager wrapping OTel + structured logger.

    Usage:
        with observer.start_span("task_name", agent="analyst") as span:
            span.set_attribute("task_type", "data_analysis")
            # ... do work ...
    """

    def __init__(self, otel_span: OtelSpan, struct_logger: StructuredLogger,
                 name: str, **attrs):
        self._otel = otel_span
        self._logger = struct_logger
        self._name = name
        self._attrs = attrs
        self._start_ms: float = 0

    def __enter__(self):
        self._start_ms = time.perf_counter()
        self._otel.__enter__()
        self._logger.info(f"span_start:{self._name}", event_type="span_start", **self._attrs)
        return self

    def __exit__(self, *args):
        duration_ms = (time.perf_counter() - self._start_ms) * 1000
        if args[0] is not None:
            self._logger.error(
                f"span_error:{self._name}", event_type="span_error",
                duration_ms=duration_ms, exception=str(args[0]),
            )
            self._otel.set_status("error")
        else:
            self._logger.info(
                f"span_end:{self._name}", event_type="span_end",
                duration_ms=duration_ms,
            )
        self._otel.__exit__(*args)

    def set_attribute(self, key: str, value: Any):
        self._otel.set_attribute(key, value)
        self._logger.debug(f"span_attr:{self._name}", event_type="span_attr",
                          attribute_key=key, attribute_value=value)


class AgentObserver:
    """
    Main observability facade — single entry point for all monitoring.

    Combines structured logging, OpenTelemetry tracing, LangSmith tracing,
    and metrics collection. Gracefully degrades when dependencies are unavailable.

    Usage:
        observer = AgentObserver(
            enable_langsmith=True,
            enable_otel=True,
            langsmith_api_key="...",
        )

        with observer.start_span("data_fetch", agent="data_agent"):
            result = fetch_data()
    """

    def __init__(
        self,
        enable_langsmith: bool = True,
        enable_otel: bool = True,
        enable_json_logging: bool = True,
        langsmith_api_key: str | None = None,
        otel_endpoint: str | None = None,
        service_name: str = "research-agent",
        session_id: str | None = None,
    ):
        # Context
        self._session_id = session_id or str(uuid.uuid4())
        self._lock = threading.Lock()

        # Sub-systems
        self._logger: StructuredLogger | None = None
        if enable_json_logging:
            try:
                self._logger = StructuredLogger()
                self._logger.bind(session_id=self._session_id)
            except Exception:
                self._logger = None

        self._otel = OTelTracer(service_name=service_name, endpoint=otel_endpoint) if enable_otel else None

        self._langsmith = None
        if enable_langsmith:
            try:
                self._langsmith = _get_langsmith_tracer()
            except Exception:
                self._langsmith = None

        self._metrics = MetricsCollector()
        self._evaluator = LLMasJudge()

        # Active span stack (for nested spans)
        self._span_stack: list[Span] = []

    # ── Context ───────────────────────────────────────────────────────────────

    def set_context(self, agent: str | None = None, task_id: str | None = None):
        """Update the bound context for logging."""
        if self._logger:
            self._logger.bind(agent=agent, task_id=task_id)

    @property
    def session_id(self) -> str:
        return self._session_id

    # ── Spans ───────────────────────────────────────────────────────────────

    def start_span(self, name: str, **attrs) -> Span:
        """Start a new tracing span."""
        otel_span = self._otel.start_span(name, **attrs) if self._otel else OtelSpan(None)
        span = Span(otel_span, self._logger or self._fallback_logger(), name, **attrs)
        with self._lock:
            self._span_stack.append(span)
        return span

    def _fallback_logger(self) -> StructuredLogger:
        """Dummy logger when structured logging is disabled."""
        logger = StructuredLogger() if self._logger is None else self._logger
        return logger

    # ── Logging ─────────────────────────────────────────────────────────────

    def log(self, level: str, message: str, **kwargs):
        """Log a structured message."""
        if self._logger:
            self._logger.log(level, message, **kwargs)
        else:
            lvl = getattr(logging, level.upper(), logging.INFO)
            logging.log(lvl, message)

    def debug(self, msg: str, **kw): self.log("DEBUG", msg, **kw)
    def info(self, msg: str, **kw): self.log("INFO", msg, **kw)
    def warn(self, msg: str, **kw): self.log("WARN", msg, **kw)
    def error(self, msg: str, **kw): self.log("ERROR", msg, **kw)

    # ── LLM Call Recording ──────────────────────────────────────────────────

    def record_llm_call(
        self,
        prompt: str,
        response: str,
        model: str,
        latency_ms: float,
        cost_usd: float,
        tokens_used: int | None = None,
        agent: str | None = None,
        task_id: str | None = None,
    ):
        """Record an LLM call across all enabled backends."""
        # Metrics
        self._metrics.inc("llm_calls_total")
        self._metrics.record_latency("llm_latency_ms", latency_ms)
        self._metrics.record_cost(cost_usd)
        if tokens_used is not None:
            self._metrics.record_tokens(tokens_used)

        # LangSmith tracing via centralized tracer
        if self._langsmith:
            try:
                self._langsmith.trace(
                    name=f"llm_call/{model}",
                    tags=[agent] if agent else None,
                    metadata={
                        "session_id": self._session_id,
                        "agent": agent,
                        "latency_ms": latency_ms,
                        "cost_usd": cost_usd,
                        "model": model,
                    },
                )
            except Exception:
                pass

        # Structured log
        self.info(
            f"llm_call: {model}",
            event_type="llm_call",
            model=model,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens=tokens_used,
            agent=agent,
            task_id=task_id,
        )

    def record_cache_hit(self):
        self._metrics.cache_hit()

    def record_cache_miss(self):
        self._metrics.cache_miss()

    def record_error(self, label: str = "general", message: str = ""):
        self._metrics.record_error(label)
        self.error(f"error: {message}", event_type="error", error_type=label)

    # ── Metrics ──────────────────────────────────────────────────────────────

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        return self._metrics.prometheus_text()

    # ── Evaluation ───────────────────────────────────────────────────────────

    def evaluate(self, test_cases: list[dict]) -> dict:
        """
        Run evaluation suite against test cases.

        Parameters
        ----------
        test_cases : list[dict]
            Each dict must contain: id, input, expected, actual.
            Optional: expected_citations, tags.

        Returns
        -------
        dict
            Full evaluation report as a dict.
        """
        report = self._evaluator.evaluate_suite(test_cases)
        return asdict(report)

    def log_evaluation_report(self, report: dict):
        """Log evaluation results to structured logger."""
        self.info(
            f"evaluation_complete: {report['passed_cases']}/{report['total_cases']} passed",
            event_type="evaluation",
            total_cases=report["total_cases"],
            passed_cases=report["passed_cases"],
            accuracy=report["accuracy"],
            avg_citation_f1=report["avg_citation_f1"],
            avg_coherence=report["avg_coherence"],
            avg_completeness=report["avg_completeness"],
        )

    # ── Decorator ───────────────────────────────────────────────────────────

    def observed(self, name: str | None = None, agent: str | None = None):
        """
        Decorator to wrap any function with a tracing span.

        Usage:
            @observer.observed("data_fetch")
            def fetch_data(query: str):
                ...
        """
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_span(span_name, agent=agent,
                                     function=func.__name__) as span:
                    sig = inspect.signature(func)
                    try:
                        bound = sig.bind(*args, **kwargs)
                    except Exception:
                        bound = {}
                    for k, v in list(bound.arguments.items())[:5]:
                        span.set_attribute(f"arg_{k}", str(v)[:200])
                    try:
                        result = func(*args, **kwargs)
                        self._metrics.inc(f"{func.__module__}.{func.__name__}_calls_total")
                        return result
                    except Exception as exc:
                        self.record_error(type(exc).__name__, str(exc))
                        raise

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self.start_span(span_name, agent=agent,
                                     function=func.__name__) as span:
                    sig = inspect.signature(func)
                    try:
                        bound = sig.bind(*args, **kwargs)
                    except Exception:
                        bound = {}
                    for k, v in list(bound.arguments.items())[:5]:
                        span.set_attribute(f"arg_{k}", str(v)[:200])
                    try:
                        result = await func(*args, **kwargs)
                        self._metrics.inc(f"{func.__module__}.{func.__name__}_calls_total")
                        return result
                    except Exception as exc:
                        self.record_error(type(exc).__name__, str(exc))
                        raise

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper

        return decorator


# ─── LLMGateway Integration ─────────────────────────────────────────────────────

def wrap_llm_gateway(gateway: Any, observer: AgentObserver) -> Any:
    """
    Wrap an LLMGateway with the AgentObserver.

    Records all LLM calls to the observer automatically.
    Returns the same gateway object (mutated in-place).

    Usage:
        observer = AgentObserver()
        gateway = wrap_llm_gateway(LLMGateway(memory), observer)
        # All gateway.generate() calls are now automatically traced
    """
    _original_generate = gateway.generate

    @functools.wraps(_original_generate)
    def _wrapped_generate(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = _original_generate(*args, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            observer.record_llm_call(
                prompt=kwargs.get("prompt", args[0] if args else ""),
                response=result.response,
                model=result.model_used,
                latency_ms=latency_ms,
                cost_usd=gateway.stats.total_cost_usd
                - getattr(_wrapped_generate, "_last_cost", 0),
                tokens_used=int(latency_ms / 50),
                agent=kwargs.get("agent"),
            )
            _wrapped_generate._last_cost = gateway.stats.total_cost_usd
            if result.cached:
                observer.record_cache_hit()
            else:
                observer.record_cache_miss()
            return result
        except Exception as exc:
            observer.record_error("llm_call", str(exc))
            raise

    gateway.generate = _wrapped_generate
    return gateway


def wrap_tool_selector(selector: Any, observer: AgentObserver) -> Any:
    """
    Wrap a ToolSelector with the AgentObserver.

    Records tool selections and executions.
    Returns the same selector object (mutated in-place).

    Usage:
        observer = AgentObserver()
        selector = wrap_tool_selector(ToolSelector(memory), observer)
        # All selector.select() and selector.execute() calls are traced
    """
    _orig_select = selector.select
    _orig_execute = selector.execute

    def _wrapped_select(task, context=None):
        with observer.start_span(f"tool_select:{task.task_type.value}",
                                 task_type=task.task_type.value):
            result = _orig_select(task, context)
            observer._metrics.inc("tool_selections_total")
            for sel in result:
                observer.debug(f"tool_selected: {sel.tool_name}",
                              event_type="tool_selection",
                              tool=sel.tool_name,
                              confidence=sel.confidence)
            return result

    def _wrapped_execute(selection, inputs):
        with observer.start_span(f"tool_exec:{selection.tool_name}",
                                 tool=selection.tool_name,
                                 cost_tier=selection.estimated_cost):
            try:
                result = _orig_execute(selection, inputs)
                observer._metrics.inc(f"tool_executions_total{{tool=\"{selection.tool_name}\"}}")
                observer._metrics.record_latency(f"tool_latency_ms{{tool=\"{selection.tool_name}\"}}",
                                                  result.latency_ms)
                if not result.success:
                    observer.record_error(f"tool_{selection.tool_name}", result.error or "unknown")
                return result
            except Exception as exc:
                observer.record_error(f"tool_{selection.tool_name}", str(exc))
                raise

    selector.select = _wrapped_select
    selector.execute = _wrapped_execute
    return selector


# ─── Global Singleton ─────────────────────────────────────────────────────────

_default_observer: AgentObserver | None = None
_observer_lock = threading.Lock()


def get_observer(
    enable_langsmith: bool = True,
    enable_otel: bool = True,
    **kwargs,
) -> AgentObserver:
    """Get or create the global AgentObserver singleton."""
    global _default_observer
    with _observer_lock:
        if _default_observer is None:
            _default_observer = AgentObserver(
                enable_langsmith=enable_langsmith,
                enable_otel=enable_otel,
                **kwargs,
            )
        return _default_observer


def reset_observer():
    """Reset the global singleton (useful for testing)."""
    global _default_observer
    with _observer_lock:
        _default_observer = None


# ═══════════════════════════════════════════════════════════════════════════
# Auto-Instrumentation & Orchestrator Tracing (竞品分析增强)
# ═══════════════════════════════════════════════════════════════════════════

def wrap_orchestrator(orchestrator: Any, observer: AgentObserver) -> Any:
    """
    Wrap an AgentOrchestrator with automatic OTel tracing for every pipeline stage.

    Each pipeline step (outline → literature → plotting → writing → refinement)
    becomes a named span. HITL gates, failures, and stage transitions are
    all recorded as span attributes.

    Usage:
        observer = get_observer()
        orchestrator = wrap_orchestrator(AgentOrchestrator(gateway), observer)

        # Now run_pipeline() automatically traces every stage
        result = orchestrator.run_pipeline("paper", steps=..., input_data={...})
        # Or stream with full observability:
        events = orchestrator.run_pipeline_streaming("paper", steps=..., input_data={...})
    """
    _orig_run = orchestrator.run_pipeline
    _orig_run_impl = orchestrator._run_pipeline_impl

    def _wrapped_run(pipeline_name, steps, input_data, **kwargs):
        total = len([s for s in steps if not getattr(s, "skip", False)])
        for i, step in enumerate(steps):
            if getattr(step, "skip", False):
                continue
            stage_name = getattr(step, "stage", None)
            agent_name = getattr(step, "agent_name", "")
            step_id = stage_name.value if stage_name else agent_name

            with observer.start_span(
                f"pipeline.stage:{step_id}",
                pipeline=pipeline_name,
                stage=step_id,
                step_index=i,
                total_steps=total,
            ) as span:
                try:
                    # Run the step (this calls _run_pipeline_impl which is also traced)
                    result = _orig_run(pipeline_name, steps, input_data, **kwargs)
                    span.set_attribute("pipeline.stage.completed", True)
                    span.set_attribute("pipeline.stage.success", result.success)
                    return result
                except Exception as exc:
                    observer.record_error(f"pipeline.stage.{step_id}", str(exc))
                    span.set_attribute("pipeline.stage.error", str(exc))
                    raise

    def _wrapped_run_impl(pipeline_name, steps, input_data, parallel, max_workers,
                         _resume_from_step=0, _resume_context=None, **kwargs):
        with observer.start_span(
            f"pipeline.run:{pipeline_name}",
            pipeline=pipeline_name,
            parallel=parallel,
            max_workers=max_workers,
        ) as span:
            try:
                result = _orig_run_impl(
                    pipeline_name, steps, input_data, parallel, max_workers,
                    _resume_from_step=_resume_from_step,
                    _resume_context=_resume_context,
                    **kwargs
                )
                span.set_attribute("pipeline.success", result.success)
                span.set_attribute("pipeline.hitl_paused",
                                   result.hitl_paused_at is not None)
                span.set_attribute("pipeline.stages_completed",
                                   len(result.stage_results))
                observer.metrics().record_latency(
                    "pipeline_latency_ms", result.total_latency_ms
                )
                return result
            except Exception as exc:
                observer.record_error("pipeline.run", str(exc))
                raise

    orchestrator.run_pipeline = _wrapped_run
    orchestrator._run_pipeline_impl = _wrapped_run_impl
    return orchestrator


def auto_instrument(
    gateway: Any,
    selector: Any | None = None,
    orchestrator: Any | None = None,
    enable_langsmith: bool = True,
    enable_otel: bool = True,
    **kwargs,
) -> tuple[Any, AgentObserver]:
    """
    Auto-instrument all major components at once.

    Wraps gateway, tool selector, and orchestrator with the AgentObserver,
    enabling full distributed tracing across the entire stack.

    Usage:
        gateway, observer = auto_instrument(
            LLMGateway(memory=None),
            ToolSelector(memory, gateway),
            AgentOrchestrator(gateway),
        )
        # Now every LLM call, tool call, and pipeline stage is traced
    """
    observer = AgentObserver(
        enable_langsmith=enable_langsmith,
        enable_otel=enable_otel,
        **kwargs,
    )
    if gateway is not None:
        wrap_llm_gateway(gateway, observer)
    if selector is not None:
        wrap_tool_selector(selector, observer)
    if orchestrator is not None:
        wrap_orchestrator(orchestrator, observer)
    return gateway, observer


class PipelineObserver:
    """
    Pipeline-level metrics collector for benchmarking.

    Tracks per-stage latency, pass/fail rates, token consumption,
    and HITL gate frequency — useful for comparing pipeline quality
    across different paper types or configurations.
    """

    def __init__(self, observer: AgentObserver | None = None):
        self._observer = observer
        self._stage_metrics: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "success": 0, "fail": 0,
            "total_latency_ms": 0.0, "hitl_pauses": 0,
        })

    def record_stage(self, stage: str, latency_ms: float,
                      success: bool, hitl_paused: bool = False):
        m = self._stage_metrics[stage]
        m["count"] += 1
        m["total_latency_ms"] += latency_ms
        if success:
            m["success"] += 1
        else:
            m["fail"] += 1
        if hitl_paused:
            m["hitl_pauses"] += 1
        if self._observer:
            self._observer.metrics().record_latency(
                f"stage.{stage}.latency_ms", latency_ms
            )

    def summary(self) -> dict:
        """Return aggregated statistics."""
        return {
            stage: {
                "count": m["count"],
                "success_rate": m["success"] / max(m["count"], 1),
                "avg_latency_ms": m["total_latency_ms"] / max(m["count"], 1),
                "hitl_pause_rate": m["hitl_pauses"] / max(m["count"], 1),
            }
            for stage, m in self._stage_metrics.items()
        }

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = ["# HELP pipeline_stage_info Pipeline stage metrics"]
        lines.append("# TYPE pipeline_stage_info gauge")
        for stage, m in self._stage_metrics.items():
            lines.append(
                f'pipeline_stage_info{{stage="{stage}",'
                f'metric="count"}} {m["count"]}'
            )
            lines.append(
                f'pipeline_stage_info{{stage="{stage}",'
                f'metric="success_rate"}} {m["success"] / max(m["count"], 1):.4f}'
            )
            lines.append(
                f'pipeline_stage_info{{stage="{stage}",'
                f'metric="avg_latency_ms"}} {m["total_latency_ms"] / max(m["count"], 1):.1f}'
            )
        return "\n".join(lines)

