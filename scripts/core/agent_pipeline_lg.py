"""
agent_pipeline_lg.py — LangGraph-backed pipeline with checkpoint + observability.

Bridges the native ``AgentOrchestrator`` with the ``LiteCompiledGraph`` from
``langgraph_integration.py``, adding:

* ``LangGraphPipeline`` — wraps ``create_research_graph()`` and connects it to
  the existing ``AgentOrchestrator``.
* ``checkpoint_to_lg()`` — migrates ``CheckpointManager`` snapshots to the
  ``LiteCompiledGraph`` memory-checkpoint store.
* ``lg_to_observability()`` — streams node events into ``LangSmithTracer``.
* ``run_with_langgraph()`` — async entry point; uses LangGraph when available,
  falls back to the native pipeline.
* ``invoke_with_trace()`` — runs a single node with LiteTracer instrumentation.

Code style follows the existing project conventions:
  ``from __future__ import annotations``, dataclass-based, ``_log = logging.getLogger``.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.core.langgraph_integration import (
        LiteCompiledGraph,
        LiteTracer,
    )
    from scripts.core.langsmith_integration import LangSmithTracer
    from scripts.core.orchestrator import AgentOrchestrator

_log = logging.getLogger("langgraph_pipeline")

# LangGraph availability guard
_LANGGRAPH_AVAILABLE = False
_LANGGRAPH_COMPILE = None
try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph as _LGStateGraph

    _LANGGRAPH_AVAILABLE = True
    _log.info("LangGraph runtime detected — using official LangGraph pipeline.")
except ImportError:
    _log.debug("LangGraph not installed — using native LiteCompiledGraph pipeline.")

__all__ = [
    "LangGraphPipeline",
    "checkpoint_to_lg",
    "lg_to_observability",
    "run_with_langgraph",
    "invoke_with_trace",
]


# ══════════════════════════════════════════════════════════════════════════════
# LangGraphPipeline
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class LangGraphPipeline:
    """
    Bridges the LiteCompiledGraph (from ``langgraph_integration.py``) with the
    existing ``AgentOrchestrator`` while providing LangGraph-compatible
    checkpoint persistence and observability.

    Parameters
    ----------
    orchestrator : AgentOrchestrator
        The existing orchestrator whose agents will be invoked at each graph node.
    use_langgraph_runtime : bool
        If True and LangGraph is installed, compile the graph using the official
        LangGraph runtime (with MemorySaver checkpoint).  Defaults to True when
        LangGraph is available.
    checkpoint_dir : str | Path
        Base directory for persistent checkpoint files written by
        ``CheckpointManager``.  Passed to ``CheckpointManager`` when converting
        checkpoints from that format.
    tracer : LiteTracer | None
        Optional LiteTracer instance to attach to the compiled graph so that
        every node execution is recorded.  If None a fresh ``LiteTracer`` is
        created automatically.

    Example
    -------
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agent_pipeline_lg import LangGraphPipeline

        orch = AgentOrchestrator(gateway)
        pipeline = LangGraphPipeline(orchestrator=orch)
        result = pipeline.run_sync(topic="碳排放权交易与绿色创新", venue="经济研究")
    """

    orchestrator: AgentOrchestrator
    use_langgraph_runtime: bool = field(default_factory=lambda: _LANGGRAPH_AVAILABLE)
    checkpoint_dir: str | Path = "data/checkpoints"
    _tracer: LiteTracer | None = field(default=None, repr=False)
    _graph: Any = field(default=None, init=False, repr=False)
    _compiled: LiteCompiledGraph | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        from scripts.core.langgraph_integration import (
            LiteTracer,
            create_research_graph,
        )

        self._tracer = self._tracer or LiteTracer()
        self._build_graph(create_research_graph)

    def _build_graph(self, graph_factory) -> None:
        """
        Build and compile the StateGraph.

        Parameters
        ----------
        graph_factory : callable
            A callable (taking no arguments) that returns a ``StateGraph``.
            Typically ``create_research_graph``.
        """
        from scripts.core.langgraph_integration import (
            CheckpointStore,
            StateGraph,
        )

        lite_graph: StateGraph = graph_factory()

        if self.use_langgraph_runtime and _LANGGRAPH_AVAILABLE:
            # Wrap the native graph nodes in the official LangGraph runtime
            wrapper = self._wrap_in_langgraph(lite_graph)
            compiled = wrapper.compile() if hasattr(wrapper, "compile") else wrapper
            _log.info(
                "LangGraph pipeline compiled (runtime=official, nodes=%d)",
                len(lite_graph.nodes),
            )
        else:
            # Use the native LiteCompiledGraph with in-memory checkpoints
            store = CheckpointStore()
            compiled: LiteCompiledGraph = lite_graph.compile(
                checkpoint_store=store,
                debug=False,
            )
            _log.info(
                "LiteCompiledGraph pipeline compiled (nodes=%d)",
                len(lite_graph.nodes),
            )

        # Attach LiteTracer so every node invocation is recorded
        compiled.set_tracer(self._tracer)

        self._graph = lite_graph
        self._compiled = compiled

    def _wrap_in_langgraph(self, lite_graph) -> Any:
        """
        Convert a native StateGraph to an official LangGraph StateGraph.

        Parameters
        ----------
        lite_graph : StateGraph

        Returns
        -------
        LangGraph StateGraph (compiled with MemorySaver)
        """
        schema = lite_graph.schema or dict
        lg = _LGStateGraph(schema=schema)

        for name, node in lite_graph.nodes.items():
            lg.add_node(name, node.func)

        for source, target in lite_graph.edges:
            lg.add_edge(source, target)

        for source, (routing_fn, mapping) in lite_graph.conditional_edges.items():
            lg.add_conditional_edges(source, routing_fn, mapping)

        if lite_graph.entry_point:
            lg.set_entry_point(lite_graph.entry_point)

        checkpointer = MemorySaver()
        return lg.compile(checkpointer=checkpointer)

    # ── Public API ─────────────────────────────────────────────────────────

    def run_sync(
        self,
        topic: str,
        venue: str = "经济研究",
        language: str = "zh",
        initial_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the pipeline synchronously.

        Parameters
        ----------
        topic : str
            Research topic string.
        venue : str
            Target journal name.
        language : str
            "en" or "zh".
        initial_context : dict | None
            Extra keys to merge into the initial graph state.

        Returns
        -------
        dict
            Final graph state after all nodes have executed.
        """

        initial_state: dict[str, Any] = {
            "topic": topic,
            "venue": venue,
            "language": language,
            "current_stage": "topic_definition",
            "stage_outputs": {},
            "stage_errors": {},
            "iter_count": 0,
            "error": None,
            "is_complete": False,
        }
        if initial_context:
            initial_state.update(initial_context)

        result = self._compiled.invoke(initial_state)
        return result

    async def run_async(
        self,
        topic: str,
        venue: str = "经济研究",
        language: str = "zh",
        initial_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the pipeline asynchronously (no-op shim — actual execution is sync).

        LangGraph's native API is synchronous; we wrap in asyncio to match
        the async entry point contract used by ``run_with_langgraph``.
        """
        import concurrent.futures

        def _run():
            return self.run_sync(
                topic=topic,
                venue=venue,
                language=language,
                initial_context=initial_context,
            )

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _run)
        return result

    def get_trace(self) -> list[dict]:
        """Return the full LiteTracer event log."""
        return self._tracer.get_trace()

    def export_trace(self, path: str | Path) -> None:
        """Export the trace log to a JSON file."""
        self._tracer.export_json(path)

    def get_tracer(self) -> LiteTracer:
        """Return the attached LiteTracer instance."""
        return self._tracer

    def summary(self) -> dict:
        """Return a human-readable summary of the trace."""
        return self._tracer.summary()


# ══════════════════════════════════════════════════════════════════════════════
# checkpoint_to_lg — migrate CheckpointManager snapshots → LiteCompiledGraph
# ══════════════════════════════════════════════════════════════════════════════


def checkpoint_to_lg(
    pipeline_id: str,
    checkpoint_manager: Any,
    compiled_graph: LiteCompiledGraph,
) -> dict[str, Any]:
    """
    Migrate the latest checkpoint from ``CheckpointManager`` into the
    ``LiteCompiledGraph`` in-memory checkpoint store.

    After migration the graph can be resumed from the exact state that
    ``CheckpointManager`` persisted to disk.

    Parameters
    ----------
    pipeline_id : str
        Unique identifier used when saving checkpoints.
    checkpoint_manager : CheckpointManager
        Instance whose ``load_latest()`` will be called.
    compiled_graph : LiteCompiledGraph
        Target compiled graph whose ``checkpoint_store`` will receive the snapshots.

    Returns
    -------
    dict
        ``{"migrated": n, "latest_checkpoint_id": str}`` where *n* is the number
        of checkpoints migrated.
    """
    from scripts.core.checkpoint import CheckpointManager, PipelineCheckpoint
    from scripts.core.langgraph_integration import CheckpointStore, LiteCheckpoint

    if not isinstance(checkpoint_manager, CheckpointManager):
        _log.warning(
            "[checkpoint_to_lg] checkpoint_manager is not a CheckpointManager — skipping"
        )
        return {"migrated": 0, "latest_checkpoint_id": ""}

    checkpoints: list[PipelineCheckpoint] = checkpoint_manager.list_checkpoints(
        pipeline_id, limit=100
    )
    if not checkpoints:
        _log.info("[checkpoint_to_lg] No checkpoints found for pipeline %s", pipeline_id)
        return {"migrated": 0, "latest_checkpoint_id": ""}

    if not isinstance(compiled_graph.checkpoint_store, CheckpointStore):
        _log.warning(
            "[checkpoint_to_lg] compiled_graph.checkpoint_store is not a CheckpointStore"
        )
        return {"migrated": 0, "latest_checkpoint_id": ""}

    migrated = 0
    for cp in checkpoints:
        lg_chk = LiteCheckpoint(
            checkpoint_id=cp.checkpoint_id,
            state=cp.context,
            node_name=cp.completed_stages[-1] if cp.completed_stages else "unknown",
            timestamp=cp.timestamp,
            metadata={
                "pipeline_id": cp.pipeline_id,
                "pipeline_name": cp.pipeline_name,
                "completed_stages": cp.completed_stages,
                "completed_stage_index": cp.completed_stage_index,
            },
        )
        compiled_graph.checkpoint_store.save(lg_chk)
        migrated += 1

    latest_id = checkpoints[0].checkpoint_id
    _log.info(
        "[checkpoint_to_lg] Migrated %d checkpoints for pipeline %s (latest=%s)",
        migrated,
        pipeline_id,
        latest_id,
    )
    return {"migrated": migrated, "latest_checkpoint_id": latest_id}


# ══════════════════════════════════════════════════════════════════════════════
# lg_to_observability — stream LangGraph node events → LangSmithTracer
# ══════════════════════════════════════════════════════════════════════════════


def lg_to_observability(
    tracer: LangSmithTracer,
    lite_tracer: LiteTracer,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Stream all events recorded by ``LiteTracer`` into ``LangSmithTracer``.

    This lets the local in-process trace be visible in LangSmith's UI
    (when ``LANGSMITH_API_KEY`` is configured) without re-running the graph.

    Parameters
    ----------
    tracer : LangSmithTracer
        LangSmith tracer that will receive the events.
    lite_tracer : LiteTracer
        Source tracer whose ``get_trace()`` events will be forwarded.
    run_id : str | None
        Optional LangSmith run ID to associate the events with.  If None a new
        run is started and its ID returned.

    Returns
    -------
    dict
        ``{"streamed": n, "run_id": str}`` where *n* is the number of events forwarded.
    """
    events = lite_tracer.get_trace()
    if not events:
        return {"streamed": 0, "run_id": run_id or ""}

    started_here = False
    if run_id is None:
        run_id = tracer.start_trace(name="lg_to_observability")
        started_here = True

    for ev in events:
        metadata = {
            "node": ev.get("node"),
            "event": ev.get("event"),
            "duration_ms": ev.get("duration_ms"),
        }
        if "state_summary" in ev:
            metadata["state_summary"] = ev["state_summary"]
        tracer.start_trace(name=f"lg_node:{ev.get('node')}", metadata=metadata)
        tracer.end_trace(run_id)

    if started_here:
        tracer.end_trace(run_id)

    _log.info(
        "[lg_to_observability] Streamed %d events to LangSmith (run_id=%s)",
        len(events),
        run_id,
    )
    return {"streamed": len(events), "run_id": run_id}


# ══════════════════════════════════════════════════════════════════════════════
# run_with_langgraph — async entry point
# ══════════════════════════════════════════════════════════════════════════════


async def run_with_langgraph(
    topic: str,
    venue: str = "经济研究",
    language: str = "zh",
    use_langgraph: bool | None = None,
) -> dict[str, Any]:
    """
    Async entry point that selects the appropriate pipeline at runtime.

    When ``use_langgraph`` is True and LangGraph is installed, the official
    LangGraph runtime is used.  Otherwise the native LiteCompiledGraph pipeline
    runs.  If LangGraph is installed but ``use_langgraph`` is False the native
    pipeline is also used.

    Parameters
    ----------
    topic : str
        Research topic string.
    venue : str
        Target journal name.
    language : str
        "en" or "zh".
    use_langgraph : bool | None
        Override for LangGraph usage.  None (default) means auto-detect:
        use LangGraph if it is installed.

    Returns
    -------
    dict
        Final pipeline state.
    """
    from scripts.core.llm_gateway import LLMGateway
    from scripts.core.orchestrator import AgentOrchestrator

    if use_langgraph is None:
        use_langgraph = _LANGGRAPH_AVAILABLE

    gateway = LLMGateway()
    orchestrator = AgentOrchestrator(gateway)

    pipeline = LangGraphPipeline(
        orchestrator=orchestrator,
        use_langgraph_runtime=use_langgraph,
    )

    result = await pipeline.run_async(
        topic=topic,
        venue=venue,
        language=language,
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# invoke_with_trace — single-node execution with tracing
# ══════════════════════════════════════════════════════════════════════════════


def invoke_with_trace(
    node_name: str,
    node_func: Any,
    stage_outputs: dict[str, dict] | None = None,
    topic: str = "",
    venue: str = "经济研究",
    language: str = "zh",
) -> tuple[dict[str, Any], LiteTracer]:
    """
    Invoke a single graph node with LiteTracer instrumentation and timing.

    This is useful for testing individual nodes in isolation or for running a
    single step of the pipeline while capturing its timing and state.

    Parameters
    ----------
    node_name : str
        Name of the node (used as the trace label).
    node_func : callable
        The node function to execute.  Must accept a dict state and return a dict.
    stage_outputs : dict | None
        Initial ``stage_outputs`` to seed the state with.
    topic : str
        Research topic string (seeded in the initial state).
    venue : str
        Target journal name (seeded in the initial state).
    language : str
        Language string (seeded in the initial state).

    Returns
    -------
    (final_state, LiteTracer)
        Tuple of the updated state after the node executed and the tracer
        holding the enter/exit events with timing.
    """
    from scripts.core.langgraph_integration import LiteTracer

    tracer = LiteTracer()
    state: dict[str, Any] = {
        "topic": topic,
        "venue": venue,
        "language": language,
        "current_stage": node_name,
        "stage_outputs": dict(stage_outputs) if stage_outputs else {},
        "iter_count": 0,
        "error": None,
        "is_complete": False,
    }

    start_ts = _time.time()
    tracer.log_node(node_name, "enter", None, state)

    try:
        output = node_func(state)
        if output:
            state.update(output)
        state["stage_outputs"][node_name] = dict(state)
        duration_ms = (_time.time() - start_ts) * 1000
        tracer.log_node(node_name, "exit", duration_ms, state)
    except Exception as exc:
        duration_ms = (_time.time() - start_ts) * 1000
        tracer.log_node(node_name, "error", duration_ms, {"error": str(exc)})
        state["error"] = str(exc)

    return state, tracer
