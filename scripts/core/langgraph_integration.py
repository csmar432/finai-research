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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict, Callable, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "StateGraph",
    "LiteCheckpoint",
    "LiteAgentState",
    "is_langgraph_available",
    "get_langgraph_compile",
]


# ─── LangGraph 可用性检测 ───────────────────────────────────────────────

def is_langgraph_available() -> bool:
    """检测 LangGraph 是否已安装。"""
    try:
        import langgraph
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
        if target not in self.nodes:
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
        import uuid, time
        state = dict(initial_state) if initial_state else {}
        state.setdefault("iter_count", 0)
        state.setdefault("stage_outputs", {})
        state.setdefault("error", None)

        checkpoint_id = f"chk_{uuid.uuid4().hex[:8]}"
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
                checkpoint_id=f"{checkpoint_id}_{current_node}_{int(time.time())}",
                state=dict(state),
                node_name=current_node,
                timestamp=time.time(),
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
        import uuid, time
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
                checkpoint_id=f"stream_{uuid.uuid4().hex[:8]}",
                state=dict(state),
                node_name=current_node,
                timestamp=time.time(),
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
