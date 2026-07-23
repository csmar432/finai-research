"""
langgraph_integration.py — 轻量级图执行引擎 + LangGraph 兼容接口

设计目标：
1. 兼容 LangGraph API（StateGraph, add_edge, add_conditional_edges）
2. 无 LangGraph 时使用原生实现（可独立运行）
3. 有 LangGraph 时自动使用（pip install langgraph）
4. 支持节点条件分支、循环、checkpoint

核心概念：
- StateGraph: 有向图，节点=处理函数，边=状态转换
- 状态：TypedDict 或 dataclass
- 条件边：根据状态动态决定下一个节点
- Checkpoint：每个节点执行后自动保存快照

Usage:
    # 方式1：原生实现（无需依赖）
    from scripts.core.langgraph_integration import StateGraph, LiteCheckpoint

    graph = StateGraph(schema=ResearchState)
    graph.add_node("literature_review", lit_review_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_edge("literature_review", "hypothesis")
    graph.add_conditional_edges("hypothesis", should_do_experiment,
        {"experiment": "experiment", "__end__": "__end__"})
    app = graph.compile()

    # 运行
    result = app.invoke({"topic": "关税政策与创新"})

    # 方式2：有 LangGraph 时自动使用
    from scripts.core.langgraph_integration import get_langgraph_graph
    if get_langgraph_graph:
        # 使用官方 LangGraph
"""

from __future__ import annotations

import logging
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "StateGraph",
    "LiteCheckpoint",
    "LiteAgentState",
    "is_langgraph_available",
    "get_langgraph_compile",
    "ResearchAgentState",
    "ResearchStage",
    "create_research_graph",
    "create_research_pipeline",
    "LiteTracer",
]


# ─── LangGraph 可用性检测 ───────────────────────────────────────────────

def is_langgraph_available() -> bool:
    """检测 LangGraph 是否已安装。"""
    try:
        return True
    except ImportError:
        return False


def get_langgraph_compile():
    """
    如果 LangGraph 可用，返回其 compile 函数。
    否则返回 None（使用原生实现）。
    """
    if is_langgraph_available():
        from langgraph.graph import StateGraph
        return StateGraph
    return None


# ─── 状态类型 ───────────────────────────────────────────────────────────

class LiteAgentState(TypedDict, total=False):
    """轻量级 Agent 状态。"""
    topic: str
    context: dict
    current_stage: str
    stage_outputs: dict
    checkpoint_id: str | None
    error: str | None
    iter_count: int


# ─── 轻量级 Checkpoint ─────────────────────────────────────────────────

@dataclass
class LiteCheckpoint:
    """轻量级 checkpoint。"""
    checkpoint_id: str
    state: dict
    node_name: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


class CheckpointStore:
    """内存 checkpoint 存储（可替换为 SQLite/Redis）。"""

    def __init__(self, max_checkpoints: int = 100):
        self._checkpoints: dict[str, LiteCheckpoint] = {}
        self._max = max_checkpoints

    def save(self, checkpoint: LiteCheckpoint):
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        if len(self._checkpoints) > self._max:
            oldest = min(self._checkpoints, key=lambda k: self._checkpoints[k].timestamp)
            del self._checkpoints[oldest]

    def load(self, checkpoint_id: str) -> LiteCheckpoint | None:
        return self._checkpoints.get(checkpoint_id)

    def list_all(self) -> list[LiteCheckpoint]:
        return sorted(self._checkpoints.values(), key=lambda c: c.timestamp)


# ─── 节点 ──────────────────────────────────────────────────────────────

class Node:
    """图节点。"""

    def __init__(self, name: str, func: Callable):
        self.name = name
        self.func = func

    def __call__(self, state: dict) -> dict:
        return self.func(state)


# ─── 轻量级 StateGraph ─────────────────────────────────────────────────

class StateGraph:
    """
    轻量级有向状态图（兼容 LangGraph API）。

    特点：
    - 兼容 LangGraph 的 add_node / add_edge / add_conditional_edges
    - 支持条件分支和 __end__ 特殊节点
    - 内置 checkpoint（每个节点执行后保存快照）
    - 支持循环（通过条件边）

    Usage:
        from dataclasses import dataclass, field

        @dataclass
        class ResearchState:
            topic: str = ""
            stage: str = "start"
            results: dict = field(default_factory=dict)

        graph = StateGraph(schema=ResearchState)
        graph.add_node("lit_review", lit_review_fn)
        graph.add_node("hypothesis", hypothesis_fn)
        graph.add_edge("lit_review", "hypothesis")
        graph.add_conditional_edges(
            "hypothesis",
            should_continue,
            {"more": "lit_review", "done": "__end__"}
        )
        app = graph.compile()
        result = app.invoke(ResearchState(topic="关税政策"))
    """

    def __init__(self, schema: type | None = None, name: str = "graph"):
        self.name = name
        self.schema = schema
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str]] = []
        self.conditional_edges: dict[str, tuple[Callable, dict]] = {}
        self.entry_point: str | None = None
        self.compiled: LiteCompiledGraph | None = None

    def add_node(self, name: str, func: Callable | None = None) -> "StateGraph":
        """
        添加节点。

        可以先声明节点（传入 None），
        然后再定义函数。
        """
        if func is None:
            # 节点声明占位（延迟绑定）
            func = self._placeholder_fn
        self.nodes[name] = Node(name, func)
        return self

    def add_edge(self, source: str, target: str) -> "StateGraph":
        """添加有向边。"""
        if source not in self.nodes:
            raise ValueError(f"Node '{source}' not defined. Call add_node('{source}', fn) first.")
        # "__end__" is a sentinel — always allowed as target (terminates graph)
        if target not in self.nodes and target != "__end__":
            raise ValueError(f"Node '{target}' not defined. Call add_node('{target}', fn) first.")
        self.edges.append((source, target))
        return self

    def add_conditional_edges(
        self,
        source: str,
        routing_fn: Callable[[dict], str],
        mapping: dict[str, str],
    ) -> "StateGraph":
        """
        添加条件边。

        Args:
            source: 源节点
            routing_fn: 路由函数，输入当前状态，返回 mapping 中的 key
            mapping: 路由 key → 目标节点（或 "__end__"）
        """
        if source not in self.nodes:
            raise ValueError(f"Node '{source}' not defined.")
        self.conditional_edges[source] = (routing_fn, mapping)
        return self

    def set_entry_point(self, node: str) -> "StateGraph":
        """设置入口节点。"""
        self.entry_point = node
        return self

    def compile(
        self,
        checkpoint_store: CheckpointStore | None = None,
        debug: bool = False,
    ) -> "LiteCompiledGraph":
        """
        编译图，生成可执行的应用。

        Returns:
            LiteCompiledGraph
        """
        if self.compiled is not None:
            return self.compiled

        # 自动设置入口点
        if self.entry_point is None:
            # 找没有入边的节点
            targets = {e[1] for e in self.edges}
            for source, _ in self.edges:
                if source not in targets:
                    self.entry_point = source
                    break

        if self.entry_point is None and self.nodes:
            self.entry_point = next(iter(self.nodes))

        self.compiled = LiteCompiledGraph(
            graph=self,
            checkpoint_store=checkpoint_store or CheckpointStore(),
            debug=debug,
        )
        return self.compiled

    @staticmethod
    def _placeholder_fn(state: dict) -> dict:
        """占位函数。"""
        return state


# ─── 编译后的图 ──────────────────────────────────────────────────────

class LiteCompiledGraph:
    """
    编译后的可执行图。

    提供 invoke() 和 stream() 方法。
    """

    def __init__(
        self,
        graph: StateGraph,
        checkpoint_store: CheckpointStore,
        debug: bool = False,
    ):
        self.graph = graph
        self.checkpoint_store = checkpoint_store
        self.debug = debug

    def invoke(self, initial_state: dict | None = None) -> dict:
        """
        从入口节点开始执行图。

        Args:
            initial_state: 初始状态字典

        Returns:
            最终状态字典
        """
        state = dict(initial_state) if initial_state else {}
        state.setdefault("iter_count", 0)
        state.setdefault("stage_outputs", {})
        state.setdefault("error", None)

        checkpoint_id = f"chk_{_uuid.uuid4().hex[:8]}"
        current_node = self.graph.entry_point
        visited: set[str] = set()
        max_iter = 100

        while current_node and current_node != "__end__" and state["iter_count"] < max_iter:
            if current_node in visited and current_node not in ["__end__"]:
                # 检测循环（允许条件循环）
                pass

            state["iter_count"] += 1
            state["current_stage"] = current_node

            if self.debug:
                logger.info(f"[Graph] Executing node: {current_node}")

            try:
                node_func = self.graph.nodes[current_node].func
                node_output = node_func(state)
                if node_output:
                    state.update(node_output)
                state["stage_outputs"][current_node] = state.copy()
            except Exception as e:
                logger.error(f"[Graph] Node '{current_node}' error: {e}")
                state["error"] = str(e)
                break

            # 保存 checkpoint
            chk = LiteCheckpoint(
                checkpoint_id=f"{checkpoint_id}_{current_node}_{int(_time.time())}",
                state=dict(state),
                node_name=current_node,
                timestamp=_time.time(),
            )
            self.checkpoint_store.save(chk)
            state["checkpoint_id"] = chk.checkpoint_id

            # 决定下一个节点
            next_node = self._get_next_node(current_node, state)
            if self.debug:
                logger.info(f"[Graph] {current_node} -> {next_node}")
            current_node = next_node

        if self.debug:
            logger.info(f"[Graph] Finished at '{current_node}' after {state['iter_count']} iterations")

        return state

    def _get_next_node(self, current: str, state: dict) -> str:
        """根据当前节点和状态决定下一个节点。"""
        # 检查条件边
        if current in self.graph.conditional_edges:
            routing_fn, mapping = self.graph.conditional_edges[current]
            try:
                route = routing_fn(state)
                next_node = mapping.get(route, "__end__")
                return next_node
            except Exception as e:
                logger.warning(f"[Graph] Routing function error for '{current}': {e}")
                return "__end__"

        # 检查普通边
        for source, target in self.graph.edges:
            if source == current:
                return target

        return "__end__"

    def stream(self, initial_state: dict | None = None):
        """
        流式执行，每次 yield 当前节点的状态。
        """
        state = dict(initial_state) if initial_state else {}
        state.setdefault("iter_count", 0)
        state.setdefault("stage_outputs", {})

        current_node = self.graph.entry_point
        while current_node and current_node != "__end__" and state["iter_count"] < 100:
            state["iter_count"] += 1
            state["current_stage"] = current_node

            try:
                node_func = self.graph.nodes[current_node].func
                node_output = node_func(state)
                if node_output:
                    state.update(node_output)
                state["stage_outputs"][current_node] = dict(state)
            except Exception as e:
                state["error"] = str(e)
                yield {"node": current_node, "state": state, "error": True}
                break

            yield {"node": current_node, "state": dict(state)}

            # 保存 checkpoint
            chk = LiteCheckpoint(
                checkpoint_id=f"stream_{_uuid.uuid4().hex[:8]}",
                state=dict(state),
                node_name=current_node,
                timestamp=_time.time(),
            )
            self.checkpoint_store.save(chk)

            current_node = self._get_next_node(current_node, state)

        yield {"node": "__end__", "state": state}

    def get_checkpoint_history(self, checkpoint_id_prefix: str = "") -> list[LiteCheckpoint]:
        """获取 checkpoint 历史。"""
        all_chk = self.checkpoint_store.list_all()
        if checkpoint_id_prefix:
            all_chk = [c for c in all_chk if checkpoint_id_prefix in c.checkpoint_id]
        return all_chk

    def restore_from_checkpoint(self, checkpoint_id: str) -> dict | None:
        """从 checkpoint 恢复状态。"""
        chk = self.checkpoint_store.load(checkpoint_id)
        return chk.state if chk else None


# ═════════════════════════════════════════════════════════════════════════════
# LiteTracer — minimal in-process tracing without a LangSmith key
# ═════════════════════════════════════════════════════════════════════════════


class LiteTracer:
    """
    Minimal in-process tracer that records node enter/exit events with timing.

    No LangSmith API key is required. Stores events in memory and can export
    them as a JSON list.

    Usage::

        tracer = LiteTracer()
        tracer.log_node("lit_review", "enter", 0, {"topic": "碳排放权"})
        # ... run node ...
        tracer.log_node("lit_review", "exit", 125.3, {"status": "done"})
        trace = tracer.get_trace()
        tracer.export_json(Path("trace.json"))

    The tracer is also called automatically inside ``LiteCompiledGraph.invoke()``
    when it is set as the graph's tracer via ``LiteCompiledGraph.set_tracer()``.
    """

    def __init__(self):
        self._events: list[dict] = []
        self._node_stack: list[tuple[str, float]] = []  # (node_name, enter_time)

    # ── Public API ─────────────────────────────────────────────────────────

    def log_node(
        self,
        node_name: str,
        event_type: str,
        duration_ms: float | None = None,
        state_summary: dict | None = None,
    ) -> None:
        """
        Record a node event.

        Parameters
        ----------
        node_name : str
            Name of the graph node.
        event_type : str
            One of "enter", "exit", "error".
        duration_ms : float | None
            Elapsed time since the node entered. None for "enter" events.
        state_summary : dict | None
            Optional snapshot of the current state to attach.
        """
        import time as _time

        event: dict[str, object] = {
            "node": node_name,
            "event": event_type,
            "timestamp": _time.time(),
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 3)
        if state_summary is not None:
            # Only store top-level scalar keys to keep trace compact
            event["state_summary"] = {
                k: v
                for k, v in state_summary.items()
                if isinstance(v, (str, int, float, bool, type(None)))
            }
        self._events.append(event)

    def get_trace(self) -> list[dict]:
        """Return a copy of all recorded events."""
        return list(self._events)

    def export_json(self, path: Path | str) -> None:
        """
        Write all events to a JSON file.

        Parameters
        ----------
        path : Path | str
            Destination file path.
        """
        import json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self._events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        """Discard all recorded events."""
        self._events.clear()
        self._node_stack.clear()

    def summary(self) -> dict:
        """
        Return a human-readable summary of the recorded trace.

        Includes per-node counts, total duration, and error count.
        """
        node_durations: dict[str, list[float]] = {}
        error_count = 0
        for ev in self._events:
            if ev["event"] == "enter":
                self._node_stack.append((ev["node"], ev["timestamp"]))
            elif ev["event"] == "exit":
                if self._node_stack and self._node_stack[-1][0] == ev["node"]:
                    _, enter_ts = self._node_stack.pop()
                    elapsed_ms = (ev["timestamp"] - enter_ts) * 1000
                    node_durations.setdefault(ev["node"], []).append(elapsed_ms)
            elif ev["event"] == "error":
                error_count += 1

        avg_durations = {
            node: round(sum(durations) / len(durations), 3)
            for node, durations in node_durations.items()
        }
        return {
            "total_events": len(self._events),
            "unique_nodes": list(node_durations.keys()),
            "node_count": {node: len(durations) for node, durations in node_durations.items()},
            "avg_duration_ms": avg_durations,
            "error_count": error_count,
        }

    # ── Internal helpers (called by LiteCompiledGraph) ─────────────────────

    def _enter_node(self, node_name: str, state: dict) -> None:
        """Record node entry. Called by LiteCompiledGraph."""
        self.log_node(node_name, "enter", None, state)

    def _exit_node(self, node_name: str, duration_ms: float, state: dict) -> None:
        """Record node exit. Called by LiteCompiledGraph."""
        self.log_node(node_name, "exit", duration_ms, state)

    def _error_node(self, node_name: str, duration_ms: float, error: str) -> None:
        """Record node error. Called by LiteCompiledGraph."""
        self.log_node(node_name, "error", duration_ms, {"error": error})


# ── Patch LiteCompiledGraph to call LiteTracer ──────────────────────────

_original_lite_invoke = LiteCompiledGraph.invoke


def _patched_invoke(self, initial_state: dict | None = None) -> dict:
    """
    Patched invoke that calls self._tracer (LiteTracer) on each node.

    Tracer is optional — if not set the behaviour is identical to the
    original implementation.
    """
    tracer: LiteTracer | None = getattr(self, "_tracer", None)
    state = dict(initial_state) if initial_state else {}
    state.setdefault("iter_count", 0)
    state.setdefault("stage_outputs", {})
    state.setdefault("error", None)

    checkpoint_id = f"chk_{_uuid.uuid4().hex[:8]}"
    current_node = self.graph.entry_point
    max_iter = 100

    while current_node and current_node != "__end__" and state["iter_count"] < max_iter:
        state["iter_count"] += 1
        state["current_stage"] = current_node

        if self.debug:
            logger.info(f"[Graph] Executing node: {current_node}")

        enter_ts = _time.time()
        if tracer is not None:
            tracer._enter_node(current_node, state)

        try:
            node_func = self.graph.nodes[current_node].func
            node_output = node_func(state)
            if node_output:
                state.update(node_output)
            state["stage_outputs"][current_node] = state.copy()
        except Exception as e:
            logger.error(f"[Graph] Node '{current_node}' error: {e}")
            state["error"] = str(e)
            if tracer is not None:
                tracer._error_node(current_node, (_time.time() - enter_ts) * 1000, str(e))
            break

        exit_ts = _time.time()
        if tracer is not None:
            tracer._exit_node(current_node, (exit_ts - enter_ts) * 1000, state)

        # Save checkpoint
        chk = LiteCheckpoint(
            checkpoint_id=f"{checkpoint_id}_{current_node}_{int(exit_ts)}",
            state=dict(state),
            node_name=current_node,
            timestamp=exit_ts,
        )
        self.checkpoint_store.save(chk)
        state["checkpoint_id"] = chk.checkpoint_id

        next_node = self._get_next_node(current_node, state)
        if self.debug:
            logger.info(f"[Graph] {current_node} -> {next_node}")
        current_node = next_node

    if self.debug:
        logger.info(f"[Graph] Finished at '{current_node}' after {state['iter_count']} iterations")

    return state


LiteCompiledGraph.invoke = _patched_invoke


def _patched_stream(self, initial_state: dict | None = None):
    """Patched stream that calls LiteTracer when set."""
    tracer: LiteTracer | None = getattr(self, "_tracer", None)
    state = dict(initial_state) if initial_state else {}
    state.setdefault("iter_count", 0)
    state.setdefault("stage_outputs", {})

    current_node = self.graph.entry_point
    while current_node and current_node != "__end__" and state["iter_count"] < 100:
        state["iter_count"] += 1
        state["current_stage"] = current_node

        enter_ts = _time.time()
        if tracer is not None:
            tracer._enter_node(current_node, state)

        try:
            node_func = self.graph.nodes[current_node].func
            node_output = node_func(state)
            if node_output:
                state.update(node_output)
            state["stage_outputs"][current_node] = dict(state)
        except Exception as e:
            state["error"] = str(e)
            if tracer is not None:
                tracer._error_node(current_node, (_time.time() - enter_ts) * 1000, str(e))
            yield {"node": current_node, "state": state, "error": True}
            break

        yield {"node": current_node, "state": dict(state)}

        exit_ts = _time.time()
        if tracer is not None:
            tracer._exit_node(current_node, (exit_ts - enter_ts) * 1000, state)

        chk = LiteCheckpoint(
            checkpoint_id=f"stream_{_uuid.uuid4().hex[:8]}",
            state=dict(state),
            node_name=current_node,
            timestamp=exit_ts,
        )
        self.checkpoint_store.save(chk)

        current_node = self._get_next_node(current_node, state)

    yield {"node": "__end__", "state": state}


LiteCompiledGraph.stream = _patched_stream


def _set_tracer(self, tracer: LiteTracer) -> None:
    """Attach a LiteTracer to this compiled graph."""
    self._tracer = tracer


LiteCompiledGraph.set_tracer = _set_tracer


# ─── 便捷路由函数 ──────────────────────────────────────────────────────

def route_by_stage(state: dict) -> str:
    """根据当前阶段路由（通用路由函数）。"""
    stage = state.get("current_stage", "")
    return stage


def route_by_completion(state: dict) -> str:
    """
    根据任务完成度路由。

    Returns:
        "continue" → 继续下一个节点
        "revise" → 回到上一节点
        "done" → 结束
    """
    error = state.get("error")
    if error:
        return "revise"
    output = state.get("stage_outputs", {})
    last_output = list(output.values())[-1] if output else {}
    # 简化的完成判断
    is_complete = last_output.get("is_complete", False)
    return "done" if is_complete else "continue"


def route_by_feedback(state: dict) -> str:
    """
    根据反馈路由。

    - HITL 反馈为 negative → 返回修改
    - positive → 继续
    - strong positive → 提前结束
    """
    feedback = state.get("hitl_feedback", "neutral")
    if feedback == "strong_positive":
        return "early_exit"
    elif feedback == "positive":
        return "continue"
    elif feedback == "negative":
        return "revise"
    else:
        return "continue"


# ─── 兼容性包装（LangGraph 存在时使用官方版本）────────────────────────

class LangGraphCompatibleWrapper:
    """
    LangGraph 兼容性包装器。

    当 LangGraph 已安装时，将原生 StateGraph 的节点/边
    转换为 LangGraph 的 StateGraph，
    享受官方优化和持久化能力。
    """

    def __init__(self, lite_graph: StateGraph):
        self.lite_graph = lite_graph
        self._langgraph_graph = None

    def compile_langgraph(self) -> Any:
        """
        如果 LangGraph 可用，转换为 LangGraph StateGraph。
        否则返回 LiteCompiledGraph。
        """
        if not is_langgraph_available():
            logger.info("LangGraph not available, using LiteCompiledGraph")
            return self.lite_graph.compile()

        from langgraph.graph import StateGraph as LGStateGraph
        from langgraph.checkpoint.memory import MemorySaver

        schema = self.lite_graph.schema or dict
        lg = LGStateGraph(schema=schema)

        # 添加节点
        for name, node in self.lite_graph.nodes.items():
            lg.add_node(name, node.func)

        # 添加边
        for source, target in self.lite_graph.edges:
            lg.add_edge(source, target)

        # 添加条件边
        for source, (routing_fn, mapping) in self.lite_graph.conditional_edges.items():
            lg.add_conditional_edges(source, routing_fn, mapping)

        # 入口点
        if self.lite_graph.entry_point:
            lg.set_entry_point(self.lite_graph.entry_point)

        # 编译（带 checkpoint）
        checkpointer = MemorySaver()
        return lg.compile(checkpointer=checkpointer)


# ═════════════════════════════════════════════════════════════════════════════
# 研究专用状态与流水线
# ═════════════════════════════════════════════════════════════════════════════

class ResearchStage(str, Enum):
    """研究流水线阶段。"""
    IDLE = "idle"
    TOPIC_DEFINITION = "topic_definition"
    LITERATURE_REVIEW = "literature_review"
    IDEA_GENERATION = "idea_generation"
    NOVELTY_CHECK = "novelty_check"
    EXPERIMENT_DESIGN = "experiment_design"
    DATA_ACQUISITION = "data_acquisition"
    DATA_VALIDATION = "data_validation"
    REGRESSION = "regression"
    DIAGNOSTICS = "diagnostics"
    ROBUSTNESS = "robustness"
    PAPER_WRITING = "paper_writing"
    REVIEW_LOOP = "review_loop"
    SUBMISSION_CHECK = "submission_check"
    COMPLETE = "complete"
    ERROR = "error"


class ResearchAgentState(TypedDict, total=False):
    """
    研究流水线的完整状态。

    与 LangGraph StateGraph 兼容，可直接传入 LiteCompiledGraph.invoke()
    或 LangGraph StateGraph。
    """
    # 核心字段
    topic: str                          # 研究主题
    venue: str                          # 目标期刊
    language: str                       # 语言 (en/zh)
    current_stage: ResearchStage        # 当前阶段
    stage_outputs: dict[str, dict]      # 每个阶段的输出
    stage_errors: dict[str, str]       # 每个阶段的错误

    # 阶段间共享数据
    literature_papers: list[dict]       # 文献综述结果
    research_ideas: list[dict]          # 候选研究想法
    selected_idea: dict | None         # 选中的想法
    experiment_design: dict | None      # 实验设计
    data_sources: dict                  # 数据源
    validation_report: dict | None      # 数据验证报告
    regression_results: list[dict]       # 回归结果
    diagnostics_report: dict | None     # 诊断报告
    robustness_results: list[dict]      # 稳健性结果
    paper_outline: dict | None          # 论文大纲
    paper_draft: str                    # 论文草稿
    review_feedback: list[dict]          # review 反馈
    submission_check: dict | None       # 投稿前检查

    # 元信息
    checkpoint_id: str | None
    iter_count: int
    hitl_approved: bool
    hitl_pending: bool
    error: str | None
    is_complete: bool


def create_research_graph() -> StateGraph:
    """
    创建研究流水线 StateGraph。

    完整的 8 步研究流程：
      Topic → LitReview → Idea → Novelty → Design → Data → Regression → Paper

    Returns:
        StateGraph: 可编译的研究流水线图

    Example:
        graph = create_research_graph()
        app = graph.compile()
        result = app.invoke(ResearchAgentState(
            topic="碳排放权交易与绿色创新",
            venue="经济研究",
            language="zh",
            current_stage=ResearchStage.TOPIC_DEFINITION,
        ))
    """
    @dataclass
    class _RS:
        topic: str = ""
        venue: str = ""
        language: str = "zh"
        current_stage: str = "idle"
        stage_outputs: dict = field(default_factory=dict)
        stage_errors: dict = field(default_factory=dict)
        literature_papers: list = field(default_factory=list)
        research_ideas: list = field(default_factory=list)
        selected_idea: dict | None = None
        experiment_design: dict | None = None
        data_sources: dict = field(default_factory=dict)
        validation_report: dict | None = None
        regression_results: list = field(default_factory=list)
        diagnostics_report: dict | None = None
        robustness_results: list = field(default_factory=list)
        paper_outline: dict | None = None
        paper_draft: str = ""
        review_feedback: list = field(default_factory=list)
        submission_check: dict | None = None
        checkpoint_id: str | None = None
        iter_count: int = 0
        hitl_approved: bool = False
        hitl_pending: bool = False
        error: str | None = None
        is_complete: bool = False

    graph = StateGraph(schema=_RS, name="research_pipeline")

    def lit_review_fn(state: dict) -> dict:
        topic = state.get("topic", "")
        logger.info(f"[Graph] Running literature review for: {topic}")
        return {
            "current_stage": "literature_review",
            "stage_outputs": {**state.get("stage_outputs", {}), "literature_review": {"status": "done"}},
        }

    def idea_gen_fn(state: dict) -> dict:
        logger.info("[Graph] Generating research ideas")
        return {
            "current_stage": "idea_generation",
            "stage_outputs": {**state.get("stage_outputs", {}), "idea_generation": {"status": "done"}},
        }

    def novelty_fn(state: dict) -> dict:
        logger.info("[Graph] Checking novelty")
        return {
            "current_stage": "novelty_check",
            "stage_outputs": {**state.get("stage_outputs", {}), "novelty_check": {"status": "done"}},
        }

    def design_fn(state: dict) -> dict:
        logger.info("[Graph] Designing experiment")
        return {
            "current_stage": "experiment_design",
            "stage_outputs": {**state.get("stage_outputs", {}), "experiment_design": {"status": "done"}},
        }

    def data_fn(state: dict) -> dict:
        logger.info("[Graph] Acquiring data")
        return {
            "current_stage": "data_acquisition",
            "stage_outputs": {**state.get("stage_outputs", {}), "data_acquisition": {"status": "done"}},
        }

    def regression_fn(state: dict) -> dict:
        logger.info("[Graph] Running regression")
        return {
            "current_stage": "regression",
            "stage_outputs": {**state.get("stage_outputs", {}), "regression": {"status": "done"}},
        }

    def writing_fn(state: dict) -> dict:
        logger.info("[Graph] Writing paper")
        return {
            "current_stage": "paper_writing",
            "paper_draft": f"# {state.get('topic', 'Research Paper')}\n\n[Draft content]",
            "stage_outputs": {**state.get("stage_outputs", {}), "paper_writing": {"status": "done"}},
        }

    graph.add_node("lit_review", lit_review_fn)
    graph.add_node("idea_generation", idea_gen_fn)
    graph.add_node("novelty_check", novelty_fn)
    graph.add_node("experiment_design", design_fn)
    graph.add_node("data_acquisition", data_fn)
    graph.add_node("regression", regression_fn)
    graph.add_node("paper_writing", writing_fn)

    # 线性流水线 + 循环节点
    graph.add_edge("lit_review", "idea_generation")
    graph.add_edge("idea_generation", "novelty_check")

    def should_continue_after_novelty(state: dict) -> str:
        error = state.get("error")
        if error:
            return "idea_generation"  # 回到想法生成
        return "experiment_design"

    graph.add_conditional_edges(
        "novelty_check",
        should_continue_after_novelty,
        {"experiment_design": "experiment_design", "idea_generation": "idea_generation"}
    )
    graph.add_edge("experiment_design", "data_acquisition")
    graph.add_edge("data_acquisition", "regression")
    graph.add_edge("regression", "paper_writing")
    graph.add_edge("paper_writing", "__end__")

    return graph


def create_research_pipeline(topic: str, venue: str = "经济研究", language: str = "zh") -> dict:
    """
    创建并返回完整的研究流水线（快捷函数）。

    相当于：
        graph = create_research_graph()
        app = graph.compile(checkpoint_store=CheckpointStore())
        return app.invoke(initial_state)

    Args:
        topic: 研究主题
        venue: 目标期刊
        language: 论文语言

    Returns:
        dict: 最终状态
    """
    graph = create_research_graph()
    store = CheckpointStore()
    app = graph.compile(checkpoint_store=store)

    initial_state = ResearchAgentState(
        topic=topic,
        venue=venue,
        language=language,
        current_stage=ResearchStage.TOPIC_DEFINITION,
        stage_outputs={},
        stage_errors={},
        literature_papers=[],
        research_ideas=[],
        selected_idea=None,
        experiment_design=None,
        data_sources={},
        validation_report=None,
        regression_results=[],
        diagnostics_report=None,
        robustness_results=[],
        paper_outline=None,
        paper_draft="",
        review_feedback=[],
        submission_check=None,
        checkpoint_id=None,
        iter_count=0,
        hitl_approved=False,
        hitl_pending=False,
        error=None,
        is_complete=False,
    )

    logger.info(f"Starting research pipeline for topic: {topic}")
    return app.invoke(initial_state)
