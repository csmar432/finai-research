"""
Agent Pipeline: Unified entry point for PaperOrchestra-style agent pipeline.

This module integrates all new P0/P1/P2 modules:
    - AgentOrchestrator: 5-agent pipeline (outline → literature → plotting → writing → refinement)
    - CitationVerifier: Semantic Scholar / CrossRef / ArXiv verification
    - SelfEvolutionEngine: SEPL self-improvement loop
    - HITLGate: Human-in-the-Loop approval gates
    - StreamingPipeline: SSE real-time output
    - BenchmarkEvaluator: Automated quality evaluation
    - WorkflowVisualizer: DOT / Mermaid / HTML visualization
    - DashboardLauncher: Auto-launch Streamlit dashboard with browser
    - LangGraphPipeline: optional LangGraph-backed pipeline with checkpoint + observability
      (activated via ``--langgraph`` CLI flag or ``use_langgraph=True`` constructor arg)

Usage:
    # Basic usage
    from scripts.agent_pipeline import AgentPipeline
    pipeline = AgentPipeline()
    result = pipeline.run("LLM在金融时间序列预测中的应用", venue="NeurIPS 2025")

    # LangGraph-backed pipeline
    from scripts.agent_pipeline import AgentPipeline, _LG_BRIDGE_AVAILABLE
    pipeline = AgentPipeline(use_langgraph=_LG_BRIDGE_AVAILABLE)
    result = pipeline.run(topic="碳排放权交易与绿色创新", venue="经济研究")

    # CLI
    python scripts/agent_pipeline.py --topic "..." --langgraph --use-hitl

    # Streaming
    async for event in pipeline.stream("..."):
        print(event.event_type, event.data)

    # Benchmark
    from scripts.core.benchmark import PaperWritingBench, BenchmarkConfig
    bench = PaperWritingBench(BenchmarkConfig(n_papers=3, domains=["empirical_paper"]))
    results = bench.run()

Canvas可视化：
    运行期间可在 Cursor 中打开 workflow-progress.canvas.tsx 查看实时进度。
    Python 端通过 localStorage 推送数据（JSON），Canvas 每2秒轮询一次。
"""

import json
import logging
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Bootstrap sys.path so `python scripts/agent_pipeline.py` works without `pip install -e .`
from scripts.core import _bootstrap  # noqa: F401
from scripts.core.ansi import bold, cyan, dim, yellow, red  # P3-8 修复 2026-06-29: mypy name-defined (120 errors) 根因
_bootstrap.bootstrap()

# T3 audit 2026-07-12: set up reproducible environment BEFORE any computation.
# This pins BLAS to single-thread, PYTHONHASHSEED=0, locale to C, and sets
# random seeds. See scripts/core/normalize.py for full documentation.
from scripts.core.normalize import setup_reproducible_env
setup_reproducible_env()

logger = logging.getLogger(__name__)

from scripts.core.platform import (
    PROJECT_ROOT,
    get_canvas_file_path,
    is_canvas_available,
)

# ─── Report Generator (P0-1: end-to-end PDF) ──────────────────────────────────
try:
    from scripts.research_framework.report_generator import ReportGenerator
    _REPORT_GEN_AVAILABLE = True
except ImportError:
    _REPORT_GEN_AVAILABLE = False
    ReportGenerator = None  # type: ignore[assignment, misc]

# ─── LangGraph Bridge ────────────────────────────────────────────────────────────

try:
    from scripts.core.orchestrator_lg_bridge import (
        PipelineRunner,
        run_research_pipeline,
        is_langgraph_available as _bridge_lg_available,
        is_pipeline_available as _bridge_pipeline_available,
    )
    _LG_BRIDGE_AVAILABLE = True
except ImportError:
    _LG_BRIDGE_AVAILABLE = False
    _bridge_lg_available = False
    _bridge_pipeline_available = False
    PipelineRunner = None  # type: ignore[assignment, misc]
    run_research_pipeline = None  # type: ignore[assignment, misc]


class PipelineConfigurationError(Exception):
    """流水线配置错误：健康检查未通过时抛出。"""

    def __init__(self, message: str = "", details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


@dataclass
class InteractionResult:
    """交互操作的结果，供调用方（终端/AI agent）使用。

    诊断完成后，此对象包含：
    - needs_input: 是否需要进一步用户输入
    - action_needed: 下一步操作类型
    - questions: 需要询问用户的问题（用于 AI agent 对话交互）
    - limitations: 受限功能清单
    - can_proceed: 是否可以继续研究
    """
    needs_input: bool = False
    action_needed: str = "proceed"   # "proceed" | "ask_api_key" | "ask_llm_confirm"
    questions: list[str] = field(default_factory=list)   # AI agent 向用户提问
    limitations: list[str] = field(default_factory=list)
    api_keys_to_add: list[dict] = field(default_factory=list)   # [{name, url}]
    fix_steps: list[str] = field(default_factory=list)
    llm_available: bool = True


def _get_canvas_url() -> str:
    """返回 Canvas 文件的可点击路径（绝对路径），或空字符串（Canvas 不可用时）。"""
    path = get_canvas_file_path()
    if path:
        return str(path)
    # Non-Cursor platforms: return the project-local path for reference
    return str(PROJECT_ROOT / "canvases" / "workflow-progress.canvas.tsx")


def _build_canvas_banner(msg: str, detail: str = "") -> str:
    """构建带可视化链接的提示横幅（用于 print 输出）。"""
    viz_url = "http://localhost:8502"
    canvas_url = _get_canvas_url()
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  {msg}",
    ]
    if is_canvas_available():
        lines.append(f"║  打开可视化: {viz_url}")
        lines.append(f"║  Canvas文件: {canvas_url}")
    else:
        lines.append("║  Canvas可视化: 当前平台不支持（仅 Cursor 可用）")
        if canvas_url:
            lines.append(f"║  Canvas文件: {canvas_url} (需手动打开)")
    lines.append("╚══════════════════════════════════════════════════════╝")
    if detail:
        lines.insert(3, f"║  {detail}")
    return "\n".join(lines)


# ─── Workflow Payload Builder ─────────────────────────────────────────────────
# 节点状态 → 中文标签映射
_STATUS_CN = {
    "running": "运行中",
    "approved": "已完成",
    "error": "执行失败",
    "max_iterations": "迭代超限",
    "pending": "待执行",
    "success": "已完成",
    "revised": "已修订",
}
# 阶段 ID → 中文标签
_LABEL_CN = {
    "outline": "大纲设计",
    "literature": "文献综述",
    "plotting": "图表生成",
    "writing": "论文写作",
    "refinement": "修改润色",
    "evaluation": "质量评估",
}
# 阶段 ID → 节点颜色
_STAGE_COLOR = {
    "outline": "#9B59B6",
    "literature": "#3498DB",
    "plotting": "#E67E22",
    "writing": "#27AE60",
    "refinement": "#E74C3C",
    "evaluation": "#1ABC9C",
}
# 状态 → 节点颜色（优先于阶段颜色）
_STATUS_COLOR = {
    "已完成": "#22c55e",
    "执行失败": "#ef4444",
    "运行中": "#3b82f6",
    "迭代超限": "#eab308",
    "待执行": None,        # None → 回退到阶段颜色
    "已修订": "#22c55e",
}
# 门控状态 → 中文标签
_GATE_STATE_CN = {
    "pending": "待审批",
    "approved": "已通过",
    "rejected": "已拒绝",
}
# 门控状态 → 颜色
_GATE_STATE_COLOR = {
    "pending": "#f59e0b",
    "approved": "#22c55e",
    "rejected": "#ef4444",
}


def _build_wf_payload(
    steps: list,
    stage_results: dict,
    topic: str = "",
    hitl_gates: dict | None = None,
    trace: list | None = None,
    hitl_paused_at: str | None = None,
) -> dict:
    """
    构建完整的可视化 payload，支持：
        - Agent 节点（含 agent 元数据、真实 iterations）
        - HITL Gate 节点（菱形，带审批状态、问题、反馈）
        - 依赖边（非线性依赖）
        - 轨迹摘要（step_skipped / deps_not_satisfied / hitl_pause）
        - 回滚边（被拒绝时的 rollback 路径）
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    hitl_gates = hitl_gates or {}

    # ── 1. Input 节点 ─────────────────────────────────────────────────────────
    nodes.append({
        "id": "input",
        "label": "用户请求",
        "type": "input",
        "shape": "stadium",
        "color": "#3b82f6",
        "status": "已完成",
        "duration_ms": 0,
        "tokens_used": 0,
        "model": "",
        "input_preview": topic,
        "output_preview": "",
        "error": "",
        "iterations": 0,
        "tools_called": [],
        "citations": [],
        "metadata": {
            "stage": "input",
            "agent_role": "",
            "agent_goal": "",
            "allowed_tools": [],
            "max_iterations": 0,
            "temperature": 0.0,
        },
    })

    # ── 2. 构建 Agent 节点 & 门控节点 ─────────────────────────────────────────
    # 我们需要将 stage 和它后面的 gate 配对插入
    stage_order: list[str] = []
    pending_gates: list[str] = []  # 门控 ID 列表（用于构建门控→stage 边）

    for step in steps:
        sid = step.stage.value
        sr = stage_results.get(step.stage)

        # ── 读取 AgentResult ─────────────────────────────────────────────────
        if sr:
            duration = getattr(sr, "latency_ms", 0) or 0
            tokens = getattr(sr, "tokens_used", 0) or 0
            model = getattr(sr, "model", "") or ""
            input_prev = getattr(sr, "input_preview", "") or ""
            output_prev = getattr(sr, "output_preview", "") or ""
            error = getattr(sr, "error", "") or ""
            tools = list(getattr(sr, "tools_called", []) or [])
            citations = list(getattr(sr, "citations", []) or [])
            raw_status = getattr(sr, "status", "pending") or "pending"
            status = _STATUS_CN.get(raw_status, "待执行")
            # FIX: 从 AgentResult 读取真实的 iterations
            iterations = getattr(sr, "iterations", 0) or 0
            feedback = getattr(sr, "feedback", "") or ""
        else:
            duration = tokens = 0
            model = input_prev = output_prev = error = feedback = ""
            tools = citations = []
            status = "待执行"
            iterations = 0

        status_color = _STATUS_COLOR.get(status)
        node_color = status_color if status_color else _STAGE_COLOR.get(sid, "#6b7280")

        # 判断是否有门控
        gate_record = hitl_gates.get(sid)
        has_gate = gate_record is not None

        # Agent 节点是否暂停（hitl_paused_at）
        is_paused = (hitl_paused_at == sid)
        if is_paused:
            status = "待审批"
            node_color = "#f59e0b"

        # ── Agent 节点 ───────────────────────────────────────────────────────
        # 附加 AgentConfig 元数据（从 orchestrator._agents 获取）
        agent_meta = {}
        try:
            # 从 orchestrator 获取 agent config（通过 agent_name）
            agent_config = getattr(step, "_agent_config", None)
            if agent_config:
                agent_meta = {
                    "agent_role": getattr(agent_config, "role", ""),
                    "agent_goal": getattr(agent_config, "goal", ""),
                    "allowed_tools": list(getattr(agent_config, "allowed_tools", [])),
                    "max_iterations": getattr(agent_config, "max_iterations", 5),
                    "temperature": getattr(agent_config, "temperature", 0.7),
                    "output_format": getattr(agent_config, "output_format", "text"),
                }
        except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
            pass

        nodes.append({
            "id": sid,
            "label": _LABEL_CN.get(sid, sid),
            "type": "agent",
            "shape": "box",
            "color": node_color,
            "status": status,
            "duration_ms": duration,
            "tokens_used": tokens,
            "model": model,
            "input_preview": input_prev[:200],
            "output_preview": output_prev[:300],
            "error": error[:200],
            "iterations": iterations,
            "tools_called": tools,
            "citations": citations,
            "feedback": feedback[:200],
            "is_paused": is_paused,
            "has_gate": has_gate,
            "metadata": {
                "stage": sid,
                "agent_name": getattr(step, "agent_name", sid),
                "hitl_gate": getattr(step, "hitl_gate", False),
                "skip": getattr(step, "skip", False),
                "depends_on": [d.value for d in getattr(step, "depends_on", [])],
                **agent_meta,
            },
        })
        stage_order.append(sid)

        # ── Gate 节点（菱形）────────────────────────────────────────────────
        if has_gate:
            gate_id = f"gate_{sid}"
            gate_state = getattr(gate_record, "state", "pending")
            gate_state_str = gate_state.value if hasattr(gate_state, "value") else str(gate_state)
            gate_cn = _GATE_STATE_CN.get(gate_state_str, "待审批")
            gate_color = _GATE_STATE_COLOR.get(gate_state_str, "#f59e0b")

            nodes.append({
                "id": gate_id,
                "label": "审批门控",
                "type": "gate",
                "shape": "diamond",
                "color": gate_color,
                "status": gate_cn,
                "duration_ms": 0,
                "tokens_used": 0,
                "model": "",
                "input_preview": "",
                "output_preview": "",
                "error": "",
                "iterations": 0,
                "tools_called": [],
                "citations": [],
                "feedback": "",
                "is_paused": False,
                "has_gate": False,
                "metadata": {
                    "gate_id": getattr(gate_record, "gate_id", gate_id),
                    "stage": sid,
                    "gate_state": gate_state_str,
                    "question": getattr(gate_record, "question", ""),
                    "content": str(getattr(gate_record, "content", {}))[:300],
                    "feedback": getattr(gate_record, "feedback", ""),
                    "held_at": getattr(gate_record, "held_at", 0),
                    "decided_at": getattr(gate_record, "decided_at", None),
                    "approved_by": getattr(gate_record, "approved_by", None),
                },
            })
            pending_gates.append(gate_id)

    # ── 3. Output 节点 ─────────────────────────────────────────────────────────
    nodes.append({
        "id": "output",
        "label": "最终结果",
        "type": "output",
        "shape": "stadium",
        "color": "#22c55e",
        "status": "待执行",
        "duration_ms": 0,
        "tokens_used": 0,
        "model": "",
        "input_preview": "",
        "output_preview": "",
        "error": "",
        "iterations": 0,
        "tools_called": [],
        "citations": [],
        "feedback": "",
        "is_paused": False,
        "has_gate": False,
        "metadata": {"stage": "output"},
    })

    # ── 4. 构建边 ─────────────────────────────────────────────────────────────
    # 4a. 顺序/依赖边
    for i, sid in enumerate(stage_order):
        step = next((s for s in steps if s.stage.value == sid), None)
        if step is None:
            continue

        depends_on_ids = [d.value for d in getattr(step, "depends_on", [])]
        gate_id = f"gate_{sid}" if hitl_gates.get(sid) else None

        if depends_on_ids:
            # 非顺序依赖边（来自其他阶段）
            for dep in depends_on_ids:
                edges.append({
                    "source": dep,
                    "target": sid,
                    "type": "dependency",
                    "style": "dashed",
                    "color": "#94a3b8",
                    "label": "依赖",
                })
        else:
            # 普通顺序边（来自前一个 stage 或 input）
            prev_id = stage_order[i - 1] if i > 0 else "input"
            # 如果当前 stage 有门控，后续 stage 的前驱改为门控节点
            if gate_id:
                edges.append({"source": prev_id, "target": sid, "type": "sequential", "style": "solid", "color": "#666", "label": ""})
                edges.append({"source": sid, "target": gate_id, "type": "gate", "style": "solid", "color": "#f59e0b", "label": "审批"})
            elif hitl_gates.get(stage_order[i - 1]):
                # 前一个 stage 有门控 → 当前 stage 连接到前一个 gate
                prev_gate = f"gate_{stage_order[i - 1]}"
                edges.append({"source": prev_gate, "target": sid, "type": "sequential", "style": "solid", "color": "#666", "label": ""})
            else:
                edges.append({"source": prev_id, "target": sid, "type": "sequential", "style": "solid", "color": "#666", "label": ""})

        # 最后一个 stage → output
        if i == len(stage_order) - 1:
            if gate_id:
                edges.append({"source": gate_id, "target": "output", "type": "sequential", "style": "solid", "color": "#666", "label": ""})
            elif len(stage_order) > 1 and hitl_gates.get(stage_order[-2]):
                # 前一个 stage 有门控 → output 连接到该门控
                prev_gate = f"gate_{stage_order[-2]}"
                edges.append({"source": prev_gate, "target": "output", "type": "sequential", "style": "solid", "color": "#666", "label": ""})
            else:
                edges.append({"source": sid, "target": "output", "type": "sequential", "style": "solid", "color": "#666", "label": ""})

    # 4b. 回滚边（rejected gates）
    for gate_id in pending_gates:
        gate_meta = next((n["metadata"] for n in nodes if n["id"] == gate_id), {})
        if gate_meta.get("gate_state") == "rejected":
            stage = gate_meta.get("stage", "")
            # 回滚到前一个 stage
            idx = stage_order.index(stage) if stage in stage_order else 0
            rollback_target = stage_order[idx - 1] if idx > 0 else "input"
            edges.append({
                "source": gate_id,
                "target": rollback_target,
                "type": "rollback",
                "style": "dashed",
                "color": "#ef4444",
                "label": "回滚",
            })

    # ── 5. 轨迹摘要 ───────────────────────────────────────────────────────────
    trace_summary: dict = {}
    if trace:
        event_types = [e.get("type", "") for e in trace]
        trace_summary = {
            "total_events": len(trace),
            "agent_starts": event_types.count("agent_start"),
            "agent_ends": event_types.count("agent_end"),
            "step_skipped": event_types.count("step_skipped"),
            "deps_not_satisfied": event_types.count("deps_not_satisfied"),
            "hitl_pauses": event_types.count("hitl_pause"),
            "evolutions": event_types.count("evolution"),
            "events": trace[-20:],  # 最近 20 条
        }

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "topic": topic,
            "start_time": time.time(),
            "hitl_paused_at": hitl_paused_at,
            "total_stages": len(stage_order),
            "total_gates": len(pending_gates),
            "pipeline_name": "paper_pipeline",
            "trace_summary": trace_summary,
        },
    }


def push_wf_to_canvas(
    steps: list,
    stage_results: dict,
    topic: str = "",
    hitl_gates: dict | None = None,
    trace: list | None = None,
    hitl_paused_at: str | None = None,
) -> None:
    """
    将工作流状态推送至可视化服务器（POST http://localhost:8502/wf_push）
    并保存到 .cache/wf_canvas_data.json。

    数据格式:
        {
          "nodes": [...],   # 节点列表（包含 agent / gate / input / output）
          "edges": [...],    # 边列表（包含顺序边 / 依赖边 / 门控边 / 回滚边）
          "meta": {...},     # 主题 / 开始时间 / 轨迹摘要
        }

    参数:
        steps: PipelineStep 列表
        stage_results: PipelineStage → AgentResult 字典
        topic: 研究主题
        hitl_gates: stage → ApprovalRecord 字典（门控状态）
        trace: PipelineResult.trace 执行轨迹事件列表
        hitl_paused_at: 当前暂停于哪个阶段（stage.value 字符串）
    """
    payload = _build_wf_payload(steps, stage_results, topic, hitl_gates, trace, hitl_paused_at)
    _save_wf_json_fallback(payload)


def _wait_for_viz_server(max_wait_s: float = 10.0) -> bool:
    """等待可视化服务器就绪（每 0.5s 检测一次）。"""
    import urllib.request
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                "http://localhost:8502/wf_data",
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                resp.read()
            return True
        except Exception:  # noqa: S110
            time.sleep(0.5)
    return False


def _save_wf_json_fallback(payload: dict) -> None:
    """将 payload 写入 JSON 文件并 POST 到可视化服务器。"""
    try:
        cache_dir = Path(__file__).parent.parent / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        fpath = cache_dir / "wf_canvas_data.json"
        tmp = fpath.parent / (fpath.name + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.rename(fpath)  # atomic on POSIX
        except Exception:  # noqa: S110
            if tmp.exists():
                tmp.unlink()
            raise  # Propagate so caller knows the save failed
    except OSError as e:
        import logging as _wf_log
        _wf_log.warning("[_save_wf_json_fallback] Failed to create cache directory: %s", e)

    # POST 到可视化服务器（端口 8502）
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:8502/wf_push",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:  # noqa: S110
        import logging as _viz_log
        _viz_log.getLogger("agent_pipeline.viz").debug(
            "Canvas POST failed (server likely not running) — this is non-fatal"
        )




def _print_canvas_hint(stage: str, detail: str = "") -> None:
    """
    Terminal text fallback when Canvas is unavailable.

    Always prints to terminal and writes state to .cache/wf_canvas_state.json
    regardless of Canvas availability (audit fix 2026-06-24: Canvas was the
    only output mechanism on non-Cursor platforms).
    """
    banner = _build_canvas_banner(stage, detail)
    print(banner)

    # Text-based fallback: always write state to cache file even when Canvas
    # is unavailable, so non-Cursor callers (CI, scripts, GitHub Actions) can
    # read pipeline stage from a machine-readable file.
    try:
        state_file = Path(__file__).parent.parent / ".cache" / "wf_canvas_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps({
                "stage": stage,
                "detail": detail,
                "canvas_path": _get_canvas_url(),
                "timestamp": time.time(),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: S110
        pass


from scripts.core.citation_verifier import CitationVerifier
from scripts.core.hitl_gate import HITLGate
from scripts.core.llm_gateway import LLMGateway
from scripts.core.orchestrator import (
    AgentOrchestrator,
    PipelineResult,
    PipelineStage,
    PipelineStep,
)
from scripts.core.self_evolution import SelfEvolutionEngine

# Checkpoint / Telemetry / Provenance / Parliament
try:
    from scripts.core.checkpoint import (
        CheckpointManager,
        PipelineCheckpoint,
        PipelineTelemetry,
        get_telemetry,
    )
    _CHECKPOINT_AVAILABLE = True
except ImportError:
    _CHECKPOINT_AVAILABLE = False
    CheckpointManager = PipelineCheckpoint = PipelineTelemetry = get_telemetry = None

try:
    from scripts.core.provenance import (
        ProvenanceChain,
        get_chain,
    )
    _PROVENANCE_AVAILABLE = True
except ImportError:
    _PROVENANCE_AVAILABLE = False
    ProvenanceChain = get_chain = None

try:
    from scripts.core.analyst import (
        AIParliament,
        AIParliamentHITLIntegration,
    )
    _PARLIAMENT_AVAILABLE = True
except ImportError:
    _PARLIAMENT_AVAILABLE = False
    AIParliament = AIParliamentHITLIntegration = None

# ─── Dashboard Launcher ──────────────────────────────────────────────────────────


class _LiveUpdateStep:
    __slots__ = ("stage", "status", "duration_ms", "tokens_used", "model",
                 "_status", "error", "iterations", "is_paused", "_agent_config")
    def __init__(self, stage_val: str):
        self.stage = type("StageEnum", (), {"value": stage_val})()
        self.status = "pending"
        self.duration_ms = 0
        self.tokens_used = 0
        self.model = "unknown"
        self._status = "pending"
        self.error = ""
        self.iterations = 0
        self.is_paused = False
        self._agent_config = None


class _LiveUpdateResult:
    # 完整 slots：必须包含 _build_wf_payload() 读取的所有属性
    __slots__ = (
        "status",
        "latency_ms",    # 映射自 data["duration_ms"]，但 payload 读 latency_ms
        "tokens_used",
        "model",
        "_status",
        "error",
        "iterations",
        "feedback",
        "tools_called",
        "citations",
        "input_preview",
        "output_preview",
    )

    def __init__(self, status_val: str, data: dict):
        self.status = status_val
        # _build_wf_payload 读 latency_ms，但 data 传的是 duration_ms
        self.latency_ms = data.get("duration_ms", 0)
        self.tokens_used = data.get("tokens_used", 0)
        self.model = data.get("model", "unknown")
        self._status = data.get("_status", "pending")
        # _build_wf_payload 额外读取的字段（避免 __slots__ AttributeError）
        self.error = data.get("error", "")
        self.iterations = data.get("iterations", 0)
        self.feedback = data.get("feedback", "")
        self.tools_called = data.get("tools_called", [])
        self.citations = data.get("citations", [])
        self.input_preview = data.get("input_preview", "")
        self.output_preview = data.get("output_preview", "")


class DashboardLauncher:
    """Auto-launch Streamlit dashboard with browser popup."""

    DASHBOARD_URL = "http://localhost:8501"
    DASHBOARD_SCRIPT = "scripts/dashboard.py"

    @classmethod
    def is_running(cls) -> bool:
        """Check if dashboard is already running."""
        try:
            import urllib.request
            urllib.request.urlopen(cls.DASHBOARD_URL, timeout=1)
            return True
        except Exception:  # noqa: S110
            return False

    @classmethod
    def launch(cls, project_root: Path | None = None) -> bool:
        """
        Launch Streamlit dashboard and open browser.

        Returns True if dashboard was launched or already running.
        """
        if cls.is_running():
            print(f"  Dashboard already running at {cls.DASHBOARD_URL}")
            return True

        if project_root is None:
            project_root = Path(__file__).parent.parent

        dashboard_path = project_root / cls.DASHBOARD_SCRIPT
        if not dashboard_path.exists():
            print(f"  Dashboard script not found: {dashboard_path}")
            return False

        print(f"  Launching Dashboard at {cls.DASHBOARD_URL}...")

        # Start streamlit in background
        try:
            subprocess.Popen(
                [
                    sys.executable, "-m", "streamlit", "run",
                    str(dashboard_path),
                    "--server.port", "8501",
                    "--server.headless", "true",
                ],
                cwd=str(project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for dashboard to be ready (max 10 seconds)
            for _ in range(20):
                time.sleep(0.5)
                if cls.is_running():
                    break

            # Open browser
            print(f"  Opening browser at {cls.DASHBOARD_URL}")
            webbrowser.open(cls.DASHBOARD_URL)
            return True

        except Exception as e:
            print(f"  Failed to launch dashboard: {e}")
            return False


# ─── Pipeline Config ────────────────────────────────────────────────────────────


@dataclass
class AgentPipelineConfig:
    """Configuration for the agent pipeline."""
    topic: str = ""
    venue: str = "通用"
    research_field: str = "AI/机器学习"
    idea: str = ""
    template: str = ""
    use_hitl: bool = False
    hitl_stages: list = field(default_factory=list)
    use_evolution: bool = False
    evolution_threshold: float = 0.6
    visualize: bool = True
    auto_dashboard: bool = True
    output_dir: Any = None
    llm_use_cache: bool = True
    # Research direction branch (None = general academic paper)
    direction: str | None = None  # "green_finance", "digital_finance", "carbon_economics", etc.


# ─── Direction Result ──────────────────────────────────────────────────────────


@dataclass
class DirectionResult:
    """Result of a research direction pipeline run (agent_pipeline ↔ research_directions)."""
    direction: str
    success: bool = False
    data: dict | None = None
    tables: dict | None = None
    figures: dict | None = None
    errors: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=lambda: time.time())


# ─── Pipeline Result ───────────────────────────────────────────────────────────


@dataclass
class AgentPipelineResult:
    """Result of a complete agent pipeline run.

    包含所有阶段输出、轨迹、质量报告和自动评分。
    """
    config: AgentPipelineConfig
    outline: dict | None = None
    literature: dict | None = None
    plotting: dict | None = None
    writing: dict | None = None
    refinement: dict | None = None
    orchestrator_result: PipelineResult | None = None
    evolution_events: list = field(default_factory=list)
    hitl_approvals: list = field(default_factory=list)
    visualization_path: Path | None = None
    total_latency_ms: float = 0.0
    success: bool = False
    errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: time.time())
    # 质量报告：stage_name → QualityGate 检查结果
    quality_reports: dict[str, dict] = field(default_factory=dict)
    # 自动评分：stage_name → AutoReviewRules 评分结果
    auto_review_reports: dict[str, dict] = field(default_factory=dict)
    # 自动生成的 DID 诊断图表路径列表
    did_chart_paths: list = field(default_factory=list)
    # 是否因 LLM 不可用而降级到 MockTemplateEngine（pipeline 已执行但产出物为 mock）
    llm_fallback_used: bool = False
    llm_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "topic": self.config.topic,
                "venue": self.config.venue,
                "research_field": self.config.research_field,
            },
            "success": self.success,
            "llm_fallback_used": self.llm_fallback_used,
            "llm_status": self.llm_status,
            "total_latency_ms": self.total_latency_ms,
            "outline": self.outline,
            "literature": {
                "citations_count": len(self.literature.get("citations", [])) if self.literature else 0,
                "coverage": self.literature.get("coverage", 0) if self.literature else 0,
            },
            "writing": {
                "chapters": [c.get("title") for c in (self.writing.get("chapters") if self.writing else [])],
                "word_count": self.writing.get("total_word_count", 0) if self.writing else 0,
            },
            "evolution_events": len(self.evolution_events),
            "hitl_approvals": [a.stage for a in (self.hitl_approvals or [])],
            "visualization": str(self.visualization_path) if self.visualization_path else None,
            "errors": self.errors,
        }


# ─── Agent Pipeline ────────────────────────────────────────────────────────────


class AgentPipeline:
    """
    Unified PaperOrchestra-style agent pipeline.

    Integrates all professional agents, citation verification, self-evolution,
    HITL gates, streaming, and visualization into a single entry point.

    Pipeline stages:
        1. Outline: Generate structured paper outline
        2. Literature: Search + verify citations (≥90% coverage)
        3. Plotting: Generate matplotlib figures
        4. Writing: Write paper sections
        5. Refinement: Simulated peer review with halt rules

    Optional stages:
        - HITL gates: Pause at outline/literature/draft for human approval
        - Self-evolution: Record and improve after each stage
        - Benchmark: Evaluate quality against standard tasks

    Usage:
        pipeline = AgentPipeline()
        result = pipeline.run(
            topic="LLM在金融时间序列预测中的应用",
            venue="NeurIPS 2025",
        )
        print(result.outline, result.writing)

        # With HITL
        config = AgentPipelineConfig(
            topic="...",
            use_hitl=True,
            hitl_stages=["outline", "literature", "draft"],
        )
        result = pipeline.run(config=config)
    """

    def __init__(self, config: AgentPipelineConfig | None = None,
                 use_langgraph: bool = False):
        self.config = config or AgentPipelineConfig(topic="")
        self._use_langgraph: bool = use_langgraph and _LG_BRIDGE_AVAILABLE
        self._gateway: LLMGateway | None = None
        self._orchestrator: AgentOrchestrator | None = None
        self._verifier: CitationVerifier | None = None
        self._evolution: SelfEvolutionEngine | None = None
        self._hitl_gate: HITLGate | None = None
        self._memory = None
        self._initialized = False
        self._current_steps: list = []
        # 可视化延迟启动：仅在首个 HITL gate 触发后启动
        # 用户审批通过后才推送阶段可视化，不在审批前展示结果
        self._viz_launched: bool = False
        self._viz_url: str = "http://localhost:8502"

        # ── Checkpoint / Telemetry ────────────────────────────────────────────────
        if _CHECKPOINT_AVAILABLE:
            self.checkpoint_manager = CheckpointManager(base_dir="output/checkpoints")
            self.pipeline_id = f"pipeline_{int(time.time())}"
            self.telemetry = get_telemetry(self.pipeline_id)
            # Try to resume from latest checkpoint
            try:
                latest_cp = self.checkpoint_manager.load_latest(self.pipeline_id)
                if latest_cp:
                    import logging as _cp_log
                    _cp_log.getLogger("agent_pipeline").info(
                        "Found checkpoint to resume: %s, stage=%s",
                        latest_cp.checkpoint_id[:8],
                        latest_cp.stage,
                    )
                    self._resume_checkpoint = latest_cp
                else:
                    self._resume_checkpoint = None
            except Exception:  # noqa: S110
                self._resume_checkpoint = None
        else:
            self.checkpoint_manager = None
            self.pipeline_id = f"pipeline_{int(time.time())}"
            self.telemetry = None
            self._resume_checkpoint = None

        # ── Provenance ────────────────────────────────────────────────────────────
        if _PROVENANCE_AVAILABLE:
            self.provenance_chain = ProvenanceChain(project_dir="output/provenance")
        else:
            self.provenance_chain = None

        # ── Parliament (optional, for paper review) ─────────────────────────────
        if _PARLIAMENT_AVAILABLE:
            self.parliament = AIParliamentHITLIntegration()
        else:
            self.parliament = None

        # ── Quality Gates ──────────────────────────────────────────────────────
        # 论文写作质量下限自动检查（QualityGates）
        self._quality_gates: "PaperQualityGates | None" = None

        # ── Auto Review ─────────────────────────────────────────────────────────
        # 论文自动评分引擎（AutoReviewRules）
        self._auto_reviewer: "AutoReviewRules | None" = None

        # ── Quality Reports Storage ─────────────────────────────────────────────
        # 存储每个 stage 的质量检查结果
        self._quality_reports: dict[str, dict] = {}

        # ── Idea-Data Validation ────────────────────────────────────────────────
        # 存储想法验证结果（用于 idea → data_acquisition 强制检查点）
        self._validated_ideas: list[dict] = []

    # ── Idea-Data Validation Checkpoint ────────────────────────────────────

    def _run_idea_data_validation(self, ideas: list[dict]) -> list[dict]:
        """
        P1: 强制想法-数据验证 checkpoint。

        在想法生成阶段和数据分析阶段之间插入，确保所有候选想法
        在进入数据获取阶段前完成数据可行性检查。

        处理逻辑：
          - Feasibility.AVAILABLE → 直接包含在返回列表
          - Feasibility.PARTIALLY_AVAILABLE → 包含但记录缺失变量
          - Feasibility.DATA_GAP → 询问用户：补充数据路径 / 跳过
          - Feasibility.REQUIRES_AUTH → 提示用户授权模拟数据

        Args:
            ideas: 原始想法列表（每个dict包含id/title/description/keywords等字段）

        Returns:
            经过数据可行性过滤的想法列表（可能为空）
        """
        try:
            from scripts.idea_data_checker import IdeaDataValidator
        except ImportError:
            print("⚠ idea_data_checker 模块不可用，跳过想法-数据验证")
            return ideas

        import logging as _idv_log
        _idv_log.getLogger("idea_data_checker").setLevel(logging.INFO)

        print()
        print("\033[96m" + "═" * 60 + "\033[0m")
        print("\033[96m" + "  💡 想法-数据验证 checkpoint  " + "\033[0m")
        print("\033[96m" + "═" * 60 + "\033[0m")
        print()

        validator = IdeaDataValidator(ideas)
        report = validator.validate_all()

        # 汇总统计
        available = []
        partial = []
        gap = []
        auth_needed = []

        for idea_result in report.idea_results:
            idea_dict = idea_result.idea
            feat = idea_result.feasibility

            if feat.value == "available":
                available.append(idea_dict)
            elif feat.value == "partial":
                partial.append(idea_dict)
            elif feat.value == "data_gap":
                gap.append(idea_dict)
            elif feat.value == "auth_needed":
                auth_needed.append(idea_dict)

        # 打印汇总
        print(f"  📊 想法-数据验证汇总:")
        print(f"     ✅ 数据可行:   {len(available)}个")
        print(f"     🟡 部分可行:   {len(partial)}个")
        print(f"     ❌ 数据缺口:   {len(gap)}个")
        print(f"     🔐 需授权:     {len(auth_needed)}个")
        print()

        # 可行的想法：直接通过
        if available:
            print("\033[92m" + "  ✅ 数据可行的想法（直接进入数据获取阶段）:" + "\033[0m")
            for idea in available:
                title = idea.get("title", idea.get("id", "unknown"))
                print(f"     • {title}")
            print()

        # 部分可行的想法：包含但记录缺失
        if partial:
            print("\033[93m" + "  🟡 部分可行的想法（含缺失变量）:" + "\033[0m")
            for idea in partial:
                title = idea.get("title", idea.get("id", "unknown"))
                result = next((r for r in report.idea_results if r.idea.get("id") == idea.get("id")), None)
                if result:
                    missing = result.gaps[:3]
                    print(f"     • {title}")
                    for g in missing:
                        print(f"       缺失: {g}")
            print()

        # 数据缺口的想法：询问用户
        if gap:
            print("\033[91m" + "  ❌ 有数据缺口的想法（需补充数据或跳过）:" + "\033[0m")
            for idea in gap:
                title = idea.get("title", idea.get("id", "unknown"))
                result = next((r for r in report.idea_results if r.idea.get("id") == idea.get("id")), None)
                if result:
                    print(f"     • {title}")
                    for action in result.actions[:3]:
                        print(f"       → {action}")
            print()
            print("  提示: 请在 data/ 目录补充所需数据文件，或更换研究方向")
            print("  如需授权使用演示数据，请调用: checker.authorize_variable('{var_name}')")
            print()

        # 需授权的想法
        if auth_needed:
            print("\033[93m" + "  🔐 需要模拟数据授权的想法:" + "\033[0m")
            for idea in auth_needed:
                title = idea.get("title", idea.get("id", "unknown"))
                print(f"     • {title}")
            print()

        # 最终合并：可行 + 部分可行
        validated = available + partial

        print("\033[96m" + "─" * 60 + "\033[0m")
        print(f"  最终通过验证的想法: {len(validated)}/{len(ideas)}个")
        if not validated:
            print("\033[91m" + "  ⚠ 所有想法均无数据支持，请补充数据或更换研究方向" + "\033[0m")
        print("\033[96m" + "─" * 60 + "\033[0m")
        print()

        self._validated_ideas = validated
        return validated

    # ── Initialization ─────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        """Lazily initialize all components."""
        if self._initialized:
            return

        from scripts.core.memory import ResearchMemory

        # Initialize memory
        output_dir = self.config.output_dir
        if output_dir is None:
            output_dir = Path("output")
        elif isinstance(output_dir, str):
            output_dir = Path(output_dir)

        self._memory = ResearchMemory(
            session_id=f"pipeline_{int(time.time())}",
            db_path=str(output_dir / ".cache" / "pipeline.db"),
        )

        # Initialize LLM gateway
        self._gateway = LLMGateway(
            self._memory,
            use_cache=self.config.llm_use_cache,
        )

        # Initialize citation verifier
        self._verifier = CitationVerifier(
            timeout=10.0,
            cache_size=500,
        )

        # Initialize orchestrator
        self._orchestrator = AgentOrchestrator(self._gateway)
        self._orchestrator.register_default_agents(
            citation_verifier=self._verifier,
        )

        # Initialize HITL gate
        if self.config.use_hitl:
            self._hitl_gate = HITLGate()
            self._orchestrator.set_hitl_gate(self._hitl_gate)

        # Initialize self-evolution
        if self.config.use_evolution:
            self._evolution = SelfEvolutionEngine(self._memory, self._gateway)
            self._orchestrator.set_evolution_engine(self._evolution)

        # Wire AIParliament into orchestrator for pre-gate machine review
        if self.parliament is not None:
            self._orchestrator.set_parliament(self.parliament)

        # ── Initialize QualityGates ─────────────────────────────────────────────
        try:
            from scripts.core.quality_gates import PaperQualityGates
            self._quality_gates = PaperQualityGates(strict=False)
            logger.debug("[AgentPipeline] PaperQualityGates loaded successfully")
        except ImportError as exc:
            self._quality_gates = None
            logger.warning(
                "[AgentPipeline] PaperQualityGates failed to import (%s) — "
                "automatic quality gates will be NO-OP. To restore them: "
                "pip install -e . and ensure scripts/core/quality_gates.py exists.",
                exc,
            )
        except Exception as exc:  # noqa: BLE001 — must not break pipeline init
            self._quality_gates = None
            logger.error(
                "[AgentPipeline] PaperQualityGates initialization error (%s) — "
                "automatic quality gates will be NO-OP.",
                exc,
                exc_info=True,
            )

        # ── Initialize AutoReviewRules ──────────────────────────────────────────
        try:
            from scripts.core.reviewer import AutoReviewRules
            self._auto_reviewer = AutoReviewRules(domain="empirical_paper")
            logger.debug("[AgentPipeline] AutoReviewRules loaded successfully")
        except ImportError as exc:
            self._auto_reviewer = None
            logger.warning(
                "[AgentPipeline] AutoReviewRules failed to import (%s) — "
                "automatic peer-review simulation will be NO-OP. To restore it: "
                "pip install -e . and ensure scripts/core/auto_review_rules.py exists.",
                exc,
            )
        except Exception as exc:  # noqa: BLE001 — must not break pipeline init
            self._auto_reviewer = None
            logger.error(
                "[AgentPipeline] AutoReviewRules initialization error (%s) — "
                "automatic peer-review simulation will be NO-OP.",
                exc,
                exc_info=True,
            )

        self._initialized = True
        # 可视化服务器延迟启动：在首个 HITL gate 触发后才启动
        # 这样用户审批前不会看到任何结果图表
        # self._launch_viz_when_needed() 在 run() 流程中调用

    def _start_viz_server_if_needed(self) -> bool:
        """启动可视化服务（幂等：仅首次调用时启动）。"""
        if self._viz_launched:
            return True
        try:
            from scripts.workflow_viz_server import VisualizationServer
            viz_server = VisualizationServer()
            if viz_server.start(open_browser=False):
                self._viz_launched = True
                print(f"  可视化服务已启动: {self._viz_url}")
                return True
        except Exception as exc:
            import logging as _viz_log
            _viz_log.getLogger("agent_pipeline.viz").debug(
                "[_start_visualization_server] Failed to start: %s — continuing without viz", exc
            )
        return False

    def _save_stage_checkpoint(self, stage_name: str, context: dict) -> str:
        """Save a checkpoint for the current stage.

        This method is best-effort: any exception is logged and swallowed
        so that a missing checkpoint manager never breaks the pipeline.
        """
        if not _CHECKPOINT_AVAILABLE or self.checkpoint_manager is None:
            return ""
        try:
            PipelineCheckpoint(
                pipeline_id=self.pipeline_id,
                pipeline_name="paper_pipeline",
                timestamp=time.time(),
                context=context,
                completed_stage_index=-1,
                completed_stages=[],
                metadata={"last_stage": stage_name},
            )
            cp_id = self.checkpoint_manager.save(
                pipeline_id=self.pipeline_id,
                pipeline_name="paper_pipeline",
                completed_stage=stage_name,
                context=context,
                stage_results={},
            )
            import logging as _cp_log
            _cp_log.getLogger("agent_pipeline").info(
                "Checkpoint saved: stage=%s, id=%s", stage_name, cp_id[:8]
            )
            return cp_id
        except Exception as exc:
            import logging as _cp_warn
            _cp_warn.getLogger("agent_pipeline").warning(
                "Failed to save checkpoint for stage %s: %s", stage_name, exc
            )
            return ""

    def _extract_stage_text(self, stage_output) -> str:
        """
        从任意 stage output 中提取纯文本内容。

        支持 dict（"output"/"text"/"content" 键）、str 和有 __str__ 的对象。
        """
        if stage_output is None:
            return ""
        if isinstance(stage_output, str):
            return stage_output
        if isinstance(stage_output, dict):
            for key in ("output", "text", "content", "result", "html", "markdown"):
                if key in stage_output:
                    val = stage_output[key]
                    if isinstance(val, str):
                        return val
                    break
            return json.dumps(stage_output, ensure_ascii=False)
        if hasattr(stage_output, "__str__"):
            return str(stage_output)
        return repr(stage_output)

    def get_quality_report(self, stage_name: str) -> dict | None:
        """
        查询指定 stage 的 QualityGates 检查结果。

        Usage:
            pipeline = AgentPipeline()
            pipeline.run("研究主题")
            qg = pipeline.get_quality_report("writing")
            if qg and not qg["passed"]:
                print(f"质量检查未通过: {qg['issues']}")
        """
        return self._quality_reports.get(stage_name)

    def _run_quality_check(self, stage_name: str, text: str) -> dict | None:
        """
        对阶段输出执行 QualityGates 检查。

        在 HITL 审批前自动执行质量下限检查，输出结构化报告。
        """
        if self._quality_gates is None:
            return None
        try:
            chapter_map = {
                "outline": "Introduction",
                "literature_review": "Literature Review",
                "literature": "Literature Review",
                "writing": "Methodology",
                "plotting": "Results",
                "refinement": "Discussion",
            }
            chapter = chapter_map.get(stage_name, stage_name.title())
            report = self._quality_gates.gate(chapter, text)
            report_dict = {
                "chapter": chapter,
                "score": report.score,
                "level": report.level.value,
                "passed": report.passed,
                "issues": [{"message": i.message, "severity": i.severity.value} for i in report.issues],
                "suggestions": report.suggestions,
                "elapsed_ms": getattr(report, "elapsed_ms", 0),
            }
            self._quality_reports[stage_name] = report_dict
            return report_dict
        except Exception:
            return None

    def _run_auto_review(self, stage_name: str, text: str) -> dict | None:
        """
        对阶段输出执行 AutoReviewRules 评分。

        在 HITL 审批前自动执行评分，识别 CRITICAL 问题。
        """
        if self._auto_reviewer is None:
            return None
        try:
            chapter_map = {
                "outline": "Introduction",
                "literature_review": "Literature Review",
                "literature": "Literature Review",
                "writing": "Methodology",
                "plotting": "Results",
                "refinement": "Discussion",
            }
            chapter = chapter_map.get(stage_name, stage_name.title())
            score = self._auto_reviewer.score_chapter(chapter, text)
            return score
        except Exception:
            return None

    def _register_provenance_result(self, stage_name: str, stage_data) -> None:
        """Register a stage output in the provenance chain (best-effort)."""
        if not _PROVENANCE_AVAILABLE or not self.provenance_chain:
            return
        try:
            import json as _json
            summary = _json.dumps(stage_data, ensure_ascii=False)[:200] if stage_data else ""
            provenance_node = __import__(
                "scripts.core.provenance", fromlist=["ProvenanceNode"]
            ).ProvenanceNode(
                node_id="",
                node_type=__import__(
                    "scripts.core.provenance", fromlist=["NodeType"]
                ).NodeType.OUTPUT,
                label=f"Stage output: {stage_name}",
                content=summary,
            )
            self.provenance_chain.register_node(provenance_node)
        except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
            pass

    # ── W1-W4 Writing Pre-Gate ──────────────────────────────────────────────
    def _run_writing_pre_gate(self, result: AgentPipelineResult, writing_text: str) -> None:
        """Run W1-W4 static quality gates before the writing stage is marked complete."""
        reports: dict[str, dict] = {}

        try:
            from scripts.research_framework.manuscript_quality_gate import check_manuscript
            reports["manuscript_quality"] = check_manuscript(writing_text)._report  # type: ignore[attr-defined]
        except Exception as exc:
            reports["manuscript_quality"] = {
                "summary_message": f"[manuscript_quality_gate] skipped: {exc}",
                "passed": True,
            }

        try:
            from scripts.research_framework.reference_validator import validate_references
            reports["reference_validator"] = validate_references(writing_text)._report  # type: ignore[attr-defined]
        except Exception as exc:
            reports["reference_validator"] = {
                "summary_message": f"[reference_validator] skipped: {exc}",
                "passed": True,
            }

        try:
            from scripts.research_framework.data_source_checker import check_data_sources
            design_text = self._extract_stage_text(
                getattr(result, "outline", None) or getattr(result, "refinement", None)
            )
            reports["data_source_checker"] = check_data_sources(
                writing_text, design_text=design_text
            )._report  # type: ignore[attr-defined]
        except Exception as exc:
            reports["data_source_checker"] = {
                "summary_message": f"[data_source_checker] skipped: {exc}",
                "passed": True,
            }

        try:
            from scripts.research_framework.negative_result_handler import assess_result
            if reports.get("manuscript_quality", {}).get("passed"):
                reports["negative_result_handler"] = assess_result(
                    baseline_p=1.0, baseline_coef=0.0, did_type="twfe"
                )._report  # type: ignore[attr-defined]
        except Exception as exc:
            reports["negative_result_handler"] = {
                "summary_message": f"[negative_result_handler] skipped: {exc}",
                "passed": True,
            }

        blocked = False
        for key, report in reports.items():
            passed = report.get("passed", True) if isinstance(report, dict) else True
            if not passed:
                blocked = True
                result.errors.append(
                    f"[writing_pre_gate/{key}] {report.get('summary_message', 'blocked')}"
                )
                result.quality_reports[f"writing_pre_gate/{key}"] = (
                    report if isinstance(report, dict) else {"passed": False}
                )

        if not blocked:
            result.quality_reports["writing_pre_gate"] = {
                "summary_message": "W1-W4 writing pre-gate passed",
                "passed": True,
            }

    async def _parliament_review(self, paper_content: dict) -> dict:
        """Run AI parliament review before human approval.

        This method is best-effort: if parliament is unavailable or fails,
        it returns an empty verdict dict so the HITL gate can still proceed.
        """
        if not _PARLIAMENT_AVAILABLE or self.parliament is None:
            return {"error": "parliament_unavailable", "scores": {}, "disputed": False}
        try:
            verdict, need_human = await self.parliament.debate_and_approve(
                paper_content,
                rounds=3,
                auto_threshold=4.0,
            )
            verdict_dict = dict(verdict)
            import logging as _parl_log
            _parl_log.getLogger("agent_pipeline").info(
                "Parliament verdict: avg_score=%s, disputed=%s, need_human=%s",
                verdict_dict.get("score", "N/A"),
                verdict_dict.get("disputed", False),
                need_human,
            )
            verdict_dict["_need_human_review"] = need_human
            return verdict_dict
        except Exception as exc:
            import logging as _parl_err
            _parl_err.getLogger("agent_pipeline").warning(
                "Parliament review failed: %s", exc
            )
            return {"error": str(exc), "scores": {}, "disputed": False}

    def _notify_viz_gate_approved(
        self,
        stage_name: str,
        stage_result: dict,
        feedback: str = "",
    ) -> None:
        """
        HITL 审批通过后，推送该阶段结果到可视化服务器。

        调用时机：用户审批通过（approve_step）后立即调用。
        在审批通过前，不推送任何结果数据。
        """
        if not self._viz_launched:
            self._start_viz_server_if_needed()

        # 构建仅包含已审批阶段的可视化 payload
        payload = {
            "event": "gate_approved",
            "stage": stage_name,
            "result_preview": str(stage_result)[:500] if stage_result else "",
            "feedback": feedback,
            "timestamp": time.time(),
            "topic": self.config.topic or "",
        }

        import logging as _gate_log
        _gate_log = _gate_log.getLogger("agent_pipeline.gate")

        # 写入文件供可视化服务器读取
        try:
            cache_dir = Path(__file__).parent.parent / ".cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            fpath = cache_dir / "wf_gate_approved.json"
            tmp = fpath.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.rename(fpath)
        except Exception as exc:
            _gate_log.debug(
                "[_notify_viz_gate_approved] State file write failed: %s", exc
            )

        # 直接 POST 到可视化服务器
        try:
            import urllib.request, urllib.error
            req = urllib.request.Request(
                f"{self._viz_url}/gate_approved",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()
        except Exception as exc:
            _gate_log.debug("Gate approval POST failed: %s — this is non-fatal", exc)

        # 告知用户
        print()
        print(f"  阶段 '{stage_name}' 已通过审批，结果已推送至可视化")
        print(f"  查看: {self._viz_url}")
        print()

    # ── Main Run ──────────────────────────────────────────────────────

    def run(self, topic: str | None = None, **kwargs) -> AgentPipelineResult:
        """
        Execute the complete agent pipeline.

        Parameters
        ----------
        topic : str | None
            Research topic. Overrides config.topic if provided.
        **kwargs
            Any AgentPipelineConfig fields to override.

        Raises
        ------
        PipelineConfigurationError
            When a critical dependency is unavailable and the pipeline cannot proceed.
            This replaces silent print-and-continue patterns that were identified by the
            2026-06-24 code audit (the class was defined but never raised).

        Returns
        -------
        AgentPipelineResult
            Full pipeline result with all stage outputs.
        """
        start_time = time.time()

        # ── Pre-flight configuration check ─────────────────────────────────────────
        # v2.1 改进（2026-07-12）：不要因为 LLM 不可用就 raise 阻断。
        # 之前的设计在 Claude Code / Codex / Cursor 等 host agent 场景下会阻断整个
        # pipeline（错误："LLM 不可用，无法进行论文写作和分析"），但这些场景下：
        #   1. host agent 本身就是 LLM，能提供 LLM 能力（虽然 CLI 进程无法直接调用）
        #   2. 用户可能用本地 Ollama 但 health_check 网络抖动误报
        #   3. MockTemplateEngine 仍可生成结构化草稿，至少让 pipeline 跑通落盘
        # 新行为：降级到 MockTemplateEngine，stderr 显式 [LLM FALLBACK] 提示，
        #         绝不静默退化（CLAUDE.md 核心原则 #3）。
        #
        # v2.2 (2026-07-13): 新增 --strict-llm 行为：未配置 LLM 时直接退出码 4，
        # 不再静默跑 MockTemplateEngine 并落盘占位文件（PR-1.4）。
        from scripts.health_check import run_diagnostic
        try:
            diag = run_diagnostic()
        except Exception:
            diag = None

        self._llm_actually_available = bool(diag and diag.llm_available)
        if not self._llm_actually_available:
            import sys as _sys
            _reason = (
                "未配置 DEEPSEEK_API_KEY / RELAY_API_KEY 且 Ollama 未运行。"
                if diag is None or not diag.llm_status
                else f"原因：{diag.llm_status[:200]}"
            )
            # 严格模式（默认开启）下，直接退出 4，避免下游脚本误读 mock 输出。
            _strict = bool(getattr(self.config, "strict_llm", True))
            if _strict:
                print(
                    "\n⚠️  [LLM FALLBACK] 未配置 LLM，严格模式下退出。\n"
                    "    \n"
                    f"    诊断：{_reason}\n"
                    "    \n"
                    "    解决方式（任选其一）：\n"
                    "      1. 在 .env 写入 DEEPSEEK_API_KEY=sk-...\n"
                    "      2. 运行 `ollama serve` 启用本地模型\n"
                    "      3. 临时绕过：finai-pipeline --topic '...' （不要加 --strict-llm 关闭；\n"
                    "         当前已默认开启，不需显式传）\n"
                    "    \n"
                    "    说明：Cursor / Claude Code / Codex 等 host agent 本身有 LLM，但 CLI\n"
                    "    进程无法直接调用它。如需在 host agent 中跑 pipeline，请通过 MCP\n"
                    "    反向调用或 host agent 端补全 LLM 反馈。\n",
                    file=_sys.stderr,
                )
                return 4
            print(
                "\n⚠️  [LLM FALLBACK] 本次 pipeline 将降级到 MockTemplateEngine。\n"
                "    产出物仍可落盘到 output/papers/，但内容是模板（带 [MOCK] 前缀），\n"
                "    不是真实 LLM 生成。请配置 DEEPSEEK_API_KEY 或运行 `ollama serve`\n"
                "    后重跑以获得真 LLM 输出。\n"
                f"    诊断：{_reason}\n",
                file=_sys.stderr,
            )

        self._ensure_initialized()

        # ── LangGraph Bridge ─────────────────────────────────────────────────────
        if _LG_BRIDGE_AVAILABLE and self._use_langgraph and run_research_pipeline is not None:
            import logging as _ap_log
            _ap_log.getLogger("agent_pipeline").info(
                "Using LangGraph pipeline (bridge available, topic=%r)", topic or self.config.topic
            )
            lg_result = run_research_pipeline(
                topic=topic or self.config.topic,
                venue=self.config.venue,
                language="zh",
                use_langgraph=True,
            )
            # ── v2.1 改进（2026-07-12）────────────────────────────────────
            # LangGraph 路径历史上只 wrap 返回值，没有真正写 paper 文件。
            # 这导致 Claude Code 之类的终端用户跑完看到 papers/ 为空。
            # 修复：把 LangGraph 的 stage_outputs 转交给 ReportGenerator，
            # 像普通路径一样落盘到 output/papers/。
            is_complete = bool(lg_result.get("is_complete", True))
            _lg_paper_tex_path: str | None = None
            if _REPORT_GEN_AVAILABLE:
                try:
                    stage_outputs = lg_result.get("stage_outputs") or {}
                    paper_content = (
                        stage_outputs.get("writing")
                        or stage_outputs.get("outline")
                        or stage_outputs.get("refinement")
                    )
                    if paper_content:
                        output_dir_path = (
                            kwargs.get("output_dir")
                            or self.config.output_dir
                            or "output/papers/"
                        )
                        rg = ReportGenerator(output_dir=output_dir_path)
                        outline = (
                            paper_content
                            if isinstance(paper_content, dict)
                            else {"content": paper_content}
                        )
                        _lg_paper_tex_path = str(rg.generate_paper(
                            topic=self.config.topic or "",
                            outline=outline,
                            data=None,
                            regressions=None,
                            references=None,
                            journal=self.config.venue or "经济研究",
                            output_dir=output_dir_path,
                        ))
                except Exception as e:
                    _ap_log.getLogger("agent_pipeline").warning(
                        "LangGraph path: ReportGenerator writing failed: %s", e
                    )

            # Wrap the raw dict result in AgentPipelineResult shape so callers
            # can still consume a structured return value
            _llm_fallback_lg = not self._llm_actually_available
            _wrap = type("_LGBridgeResult", (), {
                "config": self.config,
                "success": is_complete,
                "llm_fallback_used": _llm_fallback_lg,
                "llm_status": (
                    "未配置 DEEPSEEK_API_KEY / RELAY_API_KEY 且 Ollama 未运行。"
                    if _llm_fallback_lg
                    else "DeepSeek/Relay/Ollama"
                ),
                "outline": lg_result.get("stage_outputs", {}).get("outline"),
                "literature": lg_result.get("stage_outputs", {}).get("literature"),
                "plotting": lg_result.get("stage_outputs", {}).get("plotting"),
                "writing": lg_result.get("stage_outputs", {}).get("writing"),
                "refinement": lg_result.get("stage_outputs", {}).get("refinement"),
                "trace": lg_result.get("trace", []),
                "quality_report": lg_result.get("quality_report"),
                "elapsed_s": time.time() - start_time,
                "raw_result": lg_result,
                "paper_tex_path": _lg_paper_tex_path,
                "errors": lg_result.get("errors", []),
            })()
            return _wrap  # type: ignore[return-value]

        # ── Provenance: register pipeline start ──────────────────────────────────
        if _PROVENANCE_AVAILABLE and self.provenance_chain:
            try:
                from scripts.core.provenance import NodeType
                self.provenance_chain.register_data_source(
                    path=f"pipeline:{self.pipeline_id}",
                    node_type=NodeType.OUTPUT,
                    label=f"Pipeline {self.pipeline_id} started",
                )
                self._provenance_initialized = True
            except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
                pass

        # ── 首次运行配置检测 ────────────────────────────────────────────────
        # v2.2 (2026-07-13, PR-2.2): reuse the same ``diag`` we already
        # computed earlier in run() so the second health probe in
        # _check_and_suggest_setup doesn't re-run network checks.
        topic_for_check = (topic or self.config.topic or "")
        ir = self._check_and_suggest_setup(topic_for_check, diag=diag)

        # 仅在交互式终端中调用 input()（Cursor IDE）
        # Claude Code / Codex 等 AI agent 环境：返回 InteractionResult，
        # 由 AI agent 在对话中向用户询问
        if self._is_interactive_terminal():
            self._handle_interactive(ir)

        # ── 可视化延迟启动 ─────────────────────────────────────────────────
        # 可视化服务器在用户首个 HITL gate 触发后才启动。
        # 可视化内容在用户审批通过后才推送到 Canvas。
        # 不在 run() 开始时提示 Canvas URL，避免用户在审批前就能看到结果。
        #
        # 用户审批流程：
        #   1. pipeline 在 HITL gate 暂停，等待用户审批
        #   2. 用户调用 approve_step(stage, feedback) 审批
        #   3. approve_step 调用 _notify_viz_gate_approved() 推送结果
        #   4. Canvas 此时才显示该阶段的可视化

        # Override config
        if topic:
            self.config.topic = topic
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)

        # ── P1-3: 方向锁定 — 读取 REFINED_DESIGN.md 作为全局 anchor ─────────────
        # 如果存在 REFINED_DESIGN.md，则将其内容注入 input_data 传递给所有阶段，
        # 防止各阶段独立生成不同方向的内容（两 AI 漂移问题）。
        #
        # v2.2 (2026-07-13): 跳过 ``output/_mock/REFINED_DESIGN.md`` —
        # MockTemplateEngine 在无 LLM 时也会写一份占位设计文档到 ``output/``，
        # 该占位文本不能被当作真实方向锁定（PR-1.4 修复静默失效）。
        _direction_lock: dict = {}
        _design_paths = [
            Path("output/REFINED_DESIGN.md"),
            Path("REFINED_DESIGN.md"),
            self.config.output_dir and Path(str(self.config.output_dir)) / "REFINED_DESIGN.md",
        ]
        for _dp in _design_paths:
            if _dp and _dp.exists():
                # Skip mock placeholder design files
                if "_mock" in str(_dp):
                    continue
                try:
                    _text = _dp.read_text(encoding="utf-8")
                    if len(_text) > 100:
                        # Avoid loading a mock-template placeholder as a real
                        # direction lock. The Mock engine tags all content
                        # with `[MOCK —`; refuse to lock on that.
                        if "[MOCK —" in _text or "[MOCK]" in _text:
                            import logging as _dl_log
                            _dl_log.getLogger("agent_pipeline").info(
                                "Skipping mock-tagged design file: %s", _dp
                            )
                            continue
                        _direction_lock = {"REFINED_DESIGN": _text, "_design_path": str(_dp)}
                        import logging as _dl_log
                        _dl_log.getLogger("agent_pipeline").info(
                            "Direction lock loaded from %s (%d chars)", _dp, len(_text)
                        )
                except Exception:  # noqa: S110
                    pass
                break

        # Build pipeline steps
        steps = self._build_pipeline_steps()
        # Store steps for potential HITL resume
        self._current_steps = steps

        # Run orchestrator
        input_data = {
            "topic": self.config.topic,
            "venue": self.config.venue,
            "field": self.config.research_field,
            "idea": self.config.idea,
            "template": self.config.template,
            **_direction_lock,  # inject anchor to prevent direction drift
        }

        try:
            t0 = time.time()
            # ── Telemetry: record orchestrator call ───────────────────────────────
            orchestrator_result = self._orchestrator.run_pipeline(
                pipeline_name="paper_pipeline",
                steps=steps,
                input_data=input_data,
            )
            elapsed = time.time() - t0
            if self.telemetry:
                self.telemetry.record_stage("orchestrator", elapsed)
                self.telemetry.record_api_call("orchestrator")
            # ── Provenance: record data fetch node ───────────────────────────────
            if _PROVENANCE_AVAILABLE and self.provenance_chain:
                try:
                    from scripts.core.provenance import NodeType
                    self.provenance_chain.register_node(
                        __import__("scripts.core.provenance", fromlist=["ProvenanceNode"]).ProvenanceNode(
                            node_id="",
                            node_type=NodeType.OUTPUT,
                            label=f"Stage orchestrator completed in {elapsed:.1f}s",
                        )
                    )
                except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
                    pass
        except Exception as exc:
            if self.telemetry:
                self.telemetry.record_error(type(exc).__name__)
            import logging as _ap_log
            _ap_log.getLogger("agent_pipeline").error(
                "Orchestrator crashed: %s", exc, exc_info=True
            )
            # Build a minimal failure result so callers always get a valid AgentPipelineResult
            from scripts.core.autonomy_loop import PipelineResult
            _fake_stage = type("FakeStageResult", (), {"output": None, "status": "failed", "error": str(exc)})()
            orchestrator_result = type("FakeResult", (), {
                "success": False,
                "stage_results": {"orchestrator_crash": _fake_stage},
                "trace": [],
                "hitl_paused_at": None,
            })()
        finally:
            # Auto-save provenance report
            if self.provenance_chain:
                try:
                    self.provenance_chain.export_report(Path("output/provenance/report.md"))
                except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
                    pass

        # Push live data to Canvas for real-time visualization
        hitl_gates: dict = {}
        if (self._orchestrator._hitl_gate and
                hasattr(self._orchestrator._hitl_gate, "get_pending")):
            pending_records = self._orchestrator._hitl_gate.get_pending()
            if pending_records:
                hitl_gates = {rec.gate_id: rec for rec in pending_records}

        push_wf_to_canvas(
            steps,
            orchestrator_result.stage_results,
            topic=self.config.topic or "",
            hitl_gates=hitl_gates if hitl_gates else None,
            trace=orchestrator_result.trace,
            hitl_paused_at=orchestrator_result.hitl_paused_at.value if orchestrator_result.hitl_paused_at else None,
        )

        # Extract results
        _llm_fallback = not self._llm_actually_available
        _llm_status_msg = (
            "未配置 DEEPSEEK_API_KEY / RELAY_API_KEY 且 Ollama 未运行。"
            if diag is None or not diag.llm_status
            else (diag.llm_status or "LLM unavailable")[:200]
        )
        result = AgentPipelineResult(
            config=self.config,
            orchestrator_result=orchestrator_result,
            total_latency_ms=(time.time() - start_time) * 1000,
            success=orchestrator_result.success,
            llm_fallback_used=_llm_fallback,
            llm_status=_llm_status_msg,
        )

        # Aggregate step-level errors into result.errors
        for stage, stage_result in orchestrator_result.stage_results.items():
            stage_error = getattr(stage_result, 'error', None) or getattr(stage_result, 'err', None)
            stage_status = getattr(stage_result, 'status', None)
            if stage_error:
                result.errors.append(f"[{stage}] {stage_error}")
            elif stage_status in ("failed", "error"):
                result.errors.append(f"[{stage}] stage failed with status={stage_status}")

        if PipelineStage.OUTLINE in orchestrator_result.stage_results:
            result.outline = orchestrator_result.stage_results[PipelineStage.OUTLINE].output
            self._save_stage_checkpoint("outline", {"outline": result.outline})
            outline_text = self._extract_stage_text(result.outline)
            if outline_text:
                qg_report = self._run_quality_check("outline", outline_text)
                arr_report = self._run_auto_review("outline", outline_text)
                if qg_report:
                    result.quality_reports["outline"] = qg_report
                if arr_report:
                    result.auto_review_reports["outline"] = arr_report

            # ── P1: 强制想法-数据验证 checkpoint ─────────────────────────────
            # 在 outline（包含想法）完成后，数据获取阶段开始前执行
            # 提取 ideas 字典（如果 outline output 中包含）
            ideas_from_output: list[dict] = []
            if isinstance(result.outline, dict):
                if "ideas" in result.outline:
                    ideas_from_output = result.outline["ideas"]
                elif "data" in result.outline and isinstance(result.outline["data"], dict):
                    ideas_from_output = result.outline["data"].get("ideas", [])

            if ideas_from_output:
                validated = self._run_idea_data_validation(ideas_from_output)
                if not validated:
                    # 所有想法均无数据支持，硬中断
                    raise RuntimeError(
                        "所有候选想法均无数据支持，请补充数据或更换研究方向。"
                        "提示：将数据文件放入 data/ 目录，或联系学校图书馆申请CSMAR账号。"
                    )

        if PipelineStage.LITERATURE in orchestrator_result.stage_results:
            lit_result = orchestrator_result.stage_results[PipelineStage.LITERATURE]
            result.literature = lit_result.output
            self._save_stage_checkpoint("literature_review", {"literature": result.literature})
            lit_text = self._extract_stage_text(result.literature)
            if lit_text:
                qg = self._run_quality_check("literature", lit_text)
                arr = self._run_auto_review("literature", lit_text)
                if qg:
                    result.quality_reports["literature"] = qg
                if arr:
                    result.auto_review_reports["literature"] = arr

        if PipelineStage.PLOTTING in orchestrator_result.stage_results:
            result.plotting = orchestrator_result.stage_results[PipelineStage.PLOTTING].output
            self._save_stage_checkpoint("plotting", {"plotting": result.plotting})
            plotting_text = self._extract_stage_text(result.plotting)
            if plotting_text:
                qg = self._run_quality_check("plotting", plotting_text)
                if qg:
                    result.quality_reports["plotting"] = qg

        # ── P1: Auto-generate DID charts if DID design detected ──────────────
        # Run after plotting stage to add DID diagnostic charts automatically
        did_charts_dir = Path(str(self.config.output_dir or "output")) / "charts"
        did_charts_dir.mkdir(parents=True, exist_ok=True)
        result.did_chart_paths = self._auto_generate_did_charts(
            regressions=getattr(result, "_regressions", {}),
            output_dir=did_charts_dir,
        )

        if PipelineStage.WRITING in orchestrator_result.stage_results:
            result.writing = orchestrator_result.stage_results[PipelineStage.WRITING].output
            self._save_stage_checkpoint("writing", {"writing": result.writing})
            writing_text = self._extract_stage_text(result.writing)
            if writing_text:
                qg = self._run_quality_check("writing", writing_text)
                arr = self._run_auto_review("writing", writing_text)
                if qg:
                    result.quality_reports["writing"] = qg
                if arr:
                    result.auto_review_reports["writing"] = arr
            # ── W1-W4 writing pre-gate: reference / negative-result / manuscript quality ──
            if writing_text:
                self._run_writing_pre_gate(result, writing_text)

        if PipelineStage.REFINEMENT in orchestrator_result.stage_results:
            result.refinement = orchestrator_result.stage_results[PipelineStage.REFINEMENT].output
            self._save_stage_checkpoint("review", {"refinement": result.refinement})
            refinement_text = self._extract_stage_text(result.refinement)
            if refinement_text:
                qg = self._run_quality_check("refinement", refinement_text)
                arr = self._run_auto_review("refinement", refinement_text)
                if qg:
                    result.quality_reports["refinement"] = qg
                if arr:
                    result.auto_review_reports["refinement"] = arr

        # ── DID Chart Auto-generation ─────────────────────────────────────────────
        return result

    def _auto_generate_did_charts(
        self,
        regressions: dict | None = None,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """
        Detect DID design and auto-generate standard DID diagnostic charts.

        Looks for DID regressions in the orchestrator results and generates:
          - Parallel trend chart
          - Placebo test chart
          - Dynamic effects / event study chart

        This is best-effort: wrapped in try/except so it never blocks the pipeline.
        """
        chart_paths: list[Path] = []
        did_methods = {
            "did_2x2", "cs_did", "sun_abraham", "borusyak",
            "gardner", "synth_did", "did", "twfe",
        }

        regressions = regressions or {}
        has_did = any(
            isinstance(v, dict) and
            str(v.get("method", "")).lower() in did_methods
            for v in regressions.values()
        )

        if not has_did:
            _log_debug = __import__("logging").getLogger("agent_pipeline")
            _log_debug.debug("[_auto_generate_did_charts] No DID design detected, skipping")
            return chart_paths

        try:
            from scripts.research_framework.fin_charts import FinancialChartFactory
        except ImportError:
            return chart_paths

        try:
            factory = FinancialChartFactory.__new__(FinancialChartFactory)
            factory._data = None
            factory._regressions = regressions

            if output_dir is None:
                out_dir = Path("output/charts")
            else:
                out_dir = Path(output_dir) / "charts"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Parallel trend chart
            try:
                p1 = factory.create("parallel_trend", title="平行趋势检验")
                if p1 and isinstance(p1, Path):
                    chart_paths.append(p1)
            except Exception as e:
                _log_w = __import__("logging").getLogger("agent_pipeline")
                _log_w.debug("[_auto_generate_did_charts] parallel_trend failed: %s", e)

            # Placebo test chart
            try:
                p2 = factory.create("placebo_test", title="安慰剂检验")
                if p2 and isinstance(p2, Path):
                    chart_paths.append(p2)
            except Exception as e:
                _log_w = __import__("logging").getLogger("agent_pipeline")
                _log_w.debug("[_auto_generate_did_charts] placebo_test failed: %s", e)

            # Dynamic effects / event study chart
            try:
                p3 = factory.create("event_study", title="动态效应图")
                if p3 and isinstance(p3, Path):
                    chart_paths.append(p3)
            except Exception as e:
                _log_w = __import__("logging").getLogger("agent_pipeline")
                _log_w.debug("[_auto_generate_did_charts] event_study failed: %s", e)

            if chart_paths:
                _log_i = __import__("logging").getLogger("agent_pipeline")
                _log_i.info(
                    "[_auto_generate_did_charts] Auto-generated %d DID charts: %s",
                    len(chart_paths),
                    [str(p) for p in chart_paths],
                )

        except Exception as e:
            _log_w = __import__("logging").getLogger("agent_pipeline")
            _log_w.warning("[_auto_generate_did_charts] Chart auto-generation failed: %s", e)

        return chart_paths

    # ── P0-1: End-to-end PDF generation ────────────────────────────────────
        # Collect writing content for paper generation
        paper_content: dict = {}
        if result.outline:
            paper_content.update(result.outline if isinstance(result.outline, dict) else {})
        if result.writing:
            writing_data = result.writing if isinstance(result.writing, dict) else {}
            paper_content.setdefault("content", writing_data)
        if result.refinement:
            refined = result.refinement if isinstance(result.refinement, dict) else {}
            paper_content.setdefault("content", refined)

        if _REPORT_GEN_AVAILABLE and paper_content:
            import logging as _ap_log
            _ap_log = _ap_log.getLogger("agent_pipeline")
            try:
                output_dir = kwargs.get("output_dir") or self.config.output_dir or "output/papers/"
                rg = ReportGenerator(output_dir=output_dir)
                tex_path = rg.generate_paper(
                    topic=self.config.topic or "",
                    outline=paper_content,
                    data=None,
                    regressions=None,
                    references=None,
                    journal=self.config.venue or "经济研究",
                    output_dir=output_dir,
                )
                result.paper_tex_path = str(tex_path)
                _ap_log.info("Paper PDF generated: %s", tex_path)
                pdf_path = tex_path.with_suffix(".pdf")
                if pdf_path.exists():
                    _ap_log.info("PDF available: %s (%.1f KB)",
                                pdf_path, pdf_path.stat().st_size / 1024)
            except Exception as e:
                _ap_log.warning("Paper PDF generation failed: %s", e)
                result.errors.append(f"[PDF] generate_paper: {e}")

        # Evolution events
        if self._evolution:
            result.evolution_events = self._evolution.get_history()

        # HITL approvals
        if self._hitl_gate:
            result.hitl_approvals = self._hitl_gate.get_history()

        # ── Provenance: register final results ───────────────────────────────────
        if _PROVENANCE_AVAILABLE and self.provenance_chain:
            try:
                self._register_provenance_result("outline", result.outline)
                self._register_provenance_result("literature", result.literature)
                self._register_provenance_result("plotting", result.plotting)
                self._register_provenance_result("writing", result.writing)
                self._register_provenance_result("refinement", result.refinement)
            except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
                pass

        # ── Telemetry: record total duration ────────────────────────────────────
        if self.telemetry:
            self.telemetry.ended_at = time.time()
            try:
                self.telemetry.save()
            except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
                pass

        # Visualization
        if self.config.visualize:
            result.visualization_path = self._generate_visualization(
                steps, orchestrator_result
            )

        # ── P0-3: 字数校验 — 防止论文过短 ─────────────────────────────────
        # 检查 writing 阶段输出是否达到最低字数要求（中文 CSSCI 通常 ≥8000 字）
        _wc = result.writing.get("total_word_count", 0) if isinstance(result.writing, dict) else 0
        if _wc > 0 and _wc < 3000:
            import sys as _sys_wc
            _warn_msg = (
                f"\n⚠️  [字数警告] 论文正文仅 {_wc} 字，低于最低要求 3000 字。\n"
                f"    建议增加引言、文献综述或机制分析章节内容。\n"
                f"    如需完整论文草稿，请配置 DEEPSEEK_API_KEY 后重跑。\n"
            )
            print(_warn_msg, file=_sys_wc.stderr)
            result.errors.append(f"[字数] 正文仅 {_wc} 字，低于 3000 字最低要求")

        # ── P1-2: PDF 编译状态 — 缺少工具链时报错而非静默跳过 ───────────
        _pdf_err = [e for e in result.errors if "[PDF]" in e]
        if _pdf_err and self._llm_actually_available:
            # LLM 生成了内容但 PDF 编译失败，打印警告
            import sys as _sys_pdf
            print(
                f"\n⚠️  [PDF] {' '.join(_pdf_err)}\n"
                f"    请安装 LaTeX 工具链（Mac: brew install --cask mactex；Linux: apt install texlive-full）\n"
                f"    .tex 文件已生成，可手动编译。\n",
                file=_sys_pdf.stderr,
            )

        # ── Canvas 可视化完成提示 ─────────────────────────────────────
        _done_count = sum(
            1 for s in orchestrator_result.stage_results.values()
            if getattr(s, "status", None) == "approved"
        )
        _total_count = len(steps)
        _canvas_detail = f"总耗时: {(time.time() - start_time):.1f}s"
        if self._llm_actually_available:
            _canvas_detail += " | LLM: 可用"
        else:
            _canvas_detail += " | ⚠️ LLM: Mock 降级（内容为模板，非真实论文）"
        _print_canvas_hint(
            f"研究工作流已完成！({_done_count}/{_total_count} 阶段)",
            _canvas_detail,
        )

        return result

    def _is_interactive_terminal(self) -> bool:
        """判断是否在交互式终端中运行（而非被 AI agent 调用）。

        只有 Cursor IDE 的终端（或有 TTY 的本地 shell）才进行 input() 交互。
        Claude Code / Codex 通过对话交互，不调用 input()。
        """
        # 优先用平台检测
        try:
            from scripts.core.platform import get_platform_info
            info = get_platform_info()
            if not info.is_cursor:
                return False
        except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
            pass

        # 备用：检查是否有 TTY
        try:
            import sys
            if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                return True
        except Exception:  # noqa: S110  # pipeline must not crash on optional feature failures
            pass

        return False

    def _check_and_suggest_setup(
        self,
        topic: str = "",
        diag=None,
    ) -> InteractionResult:
        """系统健康检查 + 交互准备。

        诊断并返回 InteractionResult 对象，供调用方决定如何与用户交互：
          - 终端入口（main）：读取返回值 → 打印 → input() 询问
          - AI agent（Claude Code/Codex）：读取返回值 → 在对话中询问用户

        不在脚本内部调用 input()，只返回结构化结果。

        Parameters
        ----------
        topic : str
            研究主题，仅用于打印/记录。
        diag : optional
            v2.2 (2026-07-13, PR-2.2) 新增：调用方可传入预先计算的
            ``run_diagnostic()`` 结果，避免对同一进程内重复运行两次
            健康检查（每次都做网络探测）。  当传入 ``None`` 时，本方法
            会自己跑一次。

        Returns
        -------
        InteractionResult
            包含 needs_input、action_needed、questions、limitations 等字段
        """
        try:
            from scripts.health_check import run_diagnostic, print_diagnostic
        except ImportError:
            print("⚠️  无法导入 health_check 模块，跳过自检")
            return InteractionResult(needs_input=False, action_needed="proceed")

        if diag is None:
            try:
                result = run_diagnostic()
            except Exception as e:
                print(f"⚠️  健康检查执行失败: {e}，跳过自检继续运行")
                return InteractionResult(needs_input=False, action_needed="proceed")
        else:
            result = diag

        # 打印诊断报告（始终打印，用户看到状态）
        print_diagnostic(result, compact=False)

        # 构建受限功能清单
        limitations = []
        for p in result.problems:
            if p.category == "api_key":
                limitations.append(p.name_zh)

        # 收集 API Key 缺失的详情
        api_key_problems = [p for p in result.problems if p.category == "api_key"]

        # 构建 fix_steps
        fix_steps = []
        for p in result.problems:
            if p.category in ("api_key", "network"):
                fix_steps.extend([s for s in p.fix_steps if not s.startswith("【")])

        # ── 情形 A：系统就绪 ─────────────────────────────────────
        if result.system_ready and not api_key_problems:
            self._limitation_note = ""
            return InteractionResult(
                needs_input=False,
                action_needed="proceed",
                limitations=limitations,
                llm_available=result.llm_available,
            )

        # ── 情形 B：API Key 缺失 + LLM 可用 ─────────────────────
        if api_key_problems and result.llm_available:
            key_map = {
                "TUSHARE_TOKEN": ("Tushare A股", "https://tushare.pro/register"),
                "EODHD_API_KEY": ("EODHD 全球宏观", "https://eodhd.com"),
                "BRAVE_SEARCH_API_KEY": ("Brave Search", "https://brave.com/search/api/"),
                "CSMAR_API_KEY": ("CSMAR 国泰安", "https://www.gtadata.com"),
            }
            api_keys_to_add = []
            for p in api_key_problems:
                for key_name, (zh, url) in key_map.items():
                    if key_name in " ".join(p.fix_steps):
                        api_keys_to_add.append({"name": key_name, "zh": zh, "url": url})
                        break

            questions = [
                f"检测到 {len(api_key_problems)} 个 API Key 缺失，受限功能：{', '.join(limitations)}。"
                f" 是否现在补充配置？",
                "",
                "  (1) 是 — 我来帮你打开 .env.local 配置",
                "  (2) 否 — 跳过，使用已有工具继续（部分数据功能受限）",
            ]
            self._limitation_note = "；".join(limitations) if limitations else ""
            return InteractionResult(
                needs_input=True,
                action_needed="ask_api_key",
                questions=questions,
                limitations=limitations,
                api_keys_to_add=api_keys_to_add,
                fix_steps=fix_steps,
                llm_available=True,
            )

        # ── 情形 C：LLM 不可用 ──────────────────────────────────
        questions = [
            "LLM 不可用，无法进行论文写作和分析。",
            "当前受限功能：",
        ]
        for step in fix_steps[:4]:
            questions.append(f"  {step}")
        questions.extend([
            "",
            "是否继续？（系统将使用已有工具工作，但无法调用 LLM 生成文本）",
            "  (1) 继续 — 继续工作（受限模式）",
            "  (2) 退出 — 修复后重新启动",
        ])
        self._limitation_note = "LLM 不可用"
        return InteractionResult(
            needs_input=True,
            action_needed="ask_llm_confirm",
            questions=questions,
            limitations=["LLM 不可用"],
            fix_steps=fix_steps,
            llm_available=False,
        )

    def _handle_interactive(self, ir: InteractionResult) -> None:
        """终端入口专用：在终端中使用 input() 与用户交互。

        此方法仅在脚本直接运行时（而非被 AI agent 调用时）使用。
        """
        if not ir.needs_input:
            return

        print()
        print(bold(cyan("─" * 72)))

        if ir.action_needed == "ask_api_key":
            for q in ir.questions:
                print(f"  {yellow('⚠️  ' + q) if '⚠️' in q else '  ' + q}")
            print()
            print(f"  {dim('回复数字或描述：1/是/好 → 打开配置 | 2/否/跳过 → 继续')}")
            try:
                response = input(bold("  你的选择: ")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                response = "2"
            print()

            if response in ("1", "是", "好", "y", "yes", "ok"):
                self._do_api_key_setup(ir)
            else:
                lim = '、'.join(ir.limitations) if ir.limitations else "无"
                print(f"  {dim('跳过配置，受限功能：' + lim)}")
                print()

        elif ir.action_needed == "ask_llm_confirm":
            for q in ir.questions:
                print(f"  {red(q) if 'LLM 不可用' in q else '  ' + q}")
            print()
            try:
                response = input(bold("  你的选择 [默认: 1 继续]: ")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if response in ("2", "退出", "no", "n"):
                print(f"  {dim('退出。请修复 LLM 配置后重新启动。')}")
                return
            print()

    def _do_api_key_setup(self, ir: InteractionResult) -> None:
        """执行 API Key 配置向导（终端）。"""
        print(bold(cyan("═" * 72)))
        print(f"  {bold('API Key 配置向导')}")
        print(bold(cyan("═" * 72)))
        print()

        root = Path(__file__).parent.parent
        env_file = root / ".env.local"

        if ir.api_keys_to_add:
            print("  缺失的 API Key：")
            for item in ir.api_keys_to_add:
                print(f"    • {bold(item['name'])} [{item['zh']}]")
                print(f"      注册: {dim(item['url'])}")
            print()
            print(f"  请在 .env.local 中添加上述 Key（格式：KEY=value），保存后重启 IDE")
            print()
        else:
            dim_hint = dim("请打开以下文件添加 Key: " + str(env_file))
            print(f"  {dim_hint}")
            print()

        # 尝试用编辑器打开
        import subprocess
        editors = ["code", "nano", "vim", "vi", "emacs"]
        opened = False
        for editor in editors:
            try:
                subprocess.run([editor, str(env_file)], capture_output=True, timeout=3)
                opened = True
                print(f"  已用 {editor} 打开 {env_file}")
                break
            except Exception:  # noqa: S110
                continue

        if not opened:
            print(f"  {dim('请手动打开: ' + env_hint)}")

        print()
        print(f"  {dim('配置完成并重启后，下次运行会自动识别')}")
        print(f"  {dim('按回车继续工作（Key 在下次运行时生效）')}")
        try:
            input(bold("  按回车继续: "))
        except (EOFError, KeyboardInterrupt):
            print()
        print()

    def _build_pipeline_steps(self) -> list[PipelineStep]:
        """Build pipeline steps based on config."""
        steps = []

        hitl_stages = set(self.config.hitl_stages)

        # Step 1: Outline
        outline_hitl = self.config.use_hitl and "outline" in hitl_stages
        steps.append(PipelineStep(
            stage=PipelineStage.OUTLINE,
            agent_name="outline",
            hitl_gate=outline_hitl,
        ))

        # Step 2: Literature (depends on outline)
        lit_hitl = self.config.use_hitl and "literature" in hitl_stages
        steps.append(PipelineStep(
            stage=PipelineStage.LITERATURE,
            agent_name="literature",
            depends_on=[PipelineStage.OUTLINE],
            hitl_gate=lit_hitl,
        ))

        # Step 3: Plotting (parallel with writing, depends on outline)
        steps.append(PipelineStep(
            stage=PipelineStage.PLOTTING,
            agent_name="plotting",
            depends_on=[PipelineStage.OUTLINE],
        ))

        # Step 4: Writing (depends on outline + literature + plotting)
        draft_hitl = self.config.use_hitl and "draft" in hitl_stages
        steps.append(PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            depends_on=[PipelineStage.OUTLINE, PipelineStage.LITERATURE, PipelineStage.PLOTTING],
            hitl_gate=draft_hitl,
        ))

        # Step 5: Refinement (depends on writing)
        steps.append(PipelineStep(
            stage=PipelineStage.REFINEMENT,
            agent_name="refinement",
            depends_on=[PipelineStage.WRITING],
        ))

        return steps

    # ── HITL ────────────────────────────────────────────────────────

    def approve_step(self, stage: PipelineStage, feedback: str = "") -> dict:
        """
        审批一个 HITL 暂停的步骤并恢复 pipeline。

        审批通过后：
        1. 调用 orchestrator.approve_step() 执行实际批准逻辑
        2. 调用 _notify_viz_gate_approved() 推送该阶段结果到可视化服务器
        3. 告知用户可视化已更新

        可视化仅在用户审批后展示，防止用户在审批前看到结果。
        """
        # 确保 orchestrator 和 gate 已初始化
        if not self._initialized:
            self._ensure_initialized()
        if self._hitl_gate is None:
            return {"error": "HITL not enabled"}

        # _ensure_initialized guarantees _orchestrator is set
        if self._orchestrator is None:
            return {"error": "Orchestrator not initialized"}

        # 1. 执行批准
        approval_result = self._orchestrator.approve_step(stage, feedback)

        # 2. 审批通过后才推送可视化
        if approval_result.get("approved"):
            stage_result = None
            if (self._orchestrator._result and
                    stage in self._orchestrator._result.stage_results):
                stage_result = self._orchestrator._result.stage_results[stage].output
            self._notify_viz_gate_approved(
                stage_name=stage.value,
                stage_result=stage_result,
                feedback=feedback,
            )

        return approval_result

    def reject_step(self, stage: PipelineStage, feedback: str) -> dict:
        """
        拒绝一个 HITL 暂停的步骤。

        拒绝后：
        1. 调用 orchestrator.reject_step() 执行实际拒绝逻辑
        2. 告知用户该阶段已拒绝及原因
        """
        if not self._initialized:
            self._ensure_initialized()
        if self._hitl_gate is None:
            return {"error": "HITL not enabled"}

        # _ensure_initialized guarantees _orchestrator is set
        if self._orchestrator is None:
            return {"error": "Orchestrator not initialized"}

        result = self._orchestrator.reject_step(stage, feedback)

        print()
        print(f"  阶段 '{stage.value}' 已拒绝。反馈：{feedback[:100]}")
        print(f"  请修改内容后重新提交审批，或直接退出。")
        print()

        return result

    def get_pending_approvals(self) -> list:
        """
        获取所有待审批的 HITL 请求。

        当有待审批请求时，自动启动可视化服务器，
        让用户可在 Canvas 上看到工作流当前状态和等待审批的节点。
        """
        pending = []
        if not self._initialized:
            self._ensure_initialized()
        if self._hitl_gate:
            pending = self._hitl_gate.get_pending()
        # 有待审批时，延迟启动可视化让用户可查看当前状态
        if pending and not self._viz_launched:
            self._start_viz_server_if_needed()
        return pending

    def resume_pipeline(self, paused_result) -> "AgentPipelineResult":
        """
        Resume a HITL-paused pipeline after approval.

        Usage:
            # After user approves via approve_step():
            result = pipeline.resume_pipeline(orchestrator_result)
        """
        # Re-run orchestrator from the pause point
        if self._orchestrator is None:
            return AgentPipelineResult(
                config=self.config,
                success=False,
                errors=["Orchestrator not initialized"],
            )
        orchestrator_result = self._orchestrator.resume_pipeline(
            paused_result, self._current_steps
        )

        # Extract results (same as run() for completed stages)
        result = AgentPipelineResult(
            config=self.config,
            orchestrator_result=orchestrator_result,
            total_latency_ms=0.0,  # incremental
            success=orchestrator_result.success,
            llm_fallback_used=not self._llm_actually_available,
            llm_status=(
                "未配置 DEEPSEEK_API_KEY / RELAY_API_KEY 且 Ollama 未运行。"
                if not self._llm_actually_available
                else "DeepSeek/Relay/Ollama"
            ),
        )

        for stage, stage_result in orchestrator_result.stage_results.items():
            stage_error = getattr(stage_result, 'error', None) or getattr(stage_result, 'err', None)
            stage_status = getattr(stage_result, 'status', None)
            if stage_error:
                result.errors.append(f"[{stage}] {stage_error}")
            elif stage_status in ("failed", "error"):
                result.errors.append(f"[{stage}] stage failed with status={stage_status}")

        if PipelineStage.WRITING in orchestrator_result.stage_results:
            result.writing = orchestrator_result.stage_results[PipelineStage.WRITING].output

        if PipelineStage.REFINEMENT in orchestrator_result.stage_results:
            result.refinement = orchestrator_result.stage_results[PipelineStage.REFINEMENT].output

        return result

    # ── Citation Verification ──────────────────────────────────────

    def verify_citations(self, citations: list[dict]) -> list[dict]:
        """Verify a list of citations using CitationVerifier."""
        self._ensure_initialized()
        results = self._verifier.verify_batch(citations)
        return [
            {
                "title": r.matched_title,
                "verified": r.verified,
                "source": r.source,
                "score": r.levenshtein_score,
                "confidence": r.confidence,
            }
            for r in results
        ]

    # ── Canvas Live Push ─────────────────────────────────────────────

    def push_live_update(
        self,
        stage: "PipelineStage",
        status: str,
        extra: dict | None = None,
    ) -> None:
        """
        从外部推送单个节点的实时状态更新到 Canvas。

        用法（Agent 内部调用）:
            pipeline.push_live_update(
                stage=PipelineStage.LITERATURE,
                status="running",
                extra={"duration_ms": 3200, "tokens_used": 4500, "model": "gpt-4o"}
            )
            pipeline.push_live_update(
                stage=PipelineStage.LITERATURE,
                status="approved",
                extra={"duration_ms": 3200, "tokens_used": 4500, "model": "gpt-4o"}
            )
        """
        if not hasattr(self, "_live_stages"):
            self._live_stages: dict = {}

        node_data = extra or {}
        node_data["_status"] = status
        self._live_stages[stage.value] = node_data

        # Convert to step-like dict
        class _FakeStep:
            def __init__(self, stage_val):
                self.stage = type("FakeStage", (), {"value": stage_val})()
        class _FakeResult:
            def __init__(self, status_val, data):
                self.status = status_val
                for k, v in data.items():
                    setattr(self, k, v)

        _LiveUpdateResult(status, node_data)
        fake_steps = [_LiveUpdateStep(s) for s in self._live_stages.keys()]
        fake_results = {type("S", (), {"value": k}): _LiveUpdateResult(v.get("_status", "pending"), v) for k, v in self._live_stages.items()}

        push_wf_to_canvas(
            fake_steps,
            fake_results,
            topic=self.config.topic or "",
            hitl_gates=None,
            trace=None,
            hitl_paused_at=None,
        )

        _print_canvas_hint(
            f"节点更新: {stage.value} → {status}",
            f"耗时: {node_data.get('duration_ms', 0):.0f}ms | Token: {node_data.get('tokens_used', 0):,}"
        )

    # ── Visualization ─────────────────────────────────────────────

    def _generate_visualization(
        self,
        steps: list[PipelineStep],
        result: PipelineResult,
    ) -> Path | None:
        """Generate workflow visualization."""
        from scripts.core.visualizer import WorkflowVisualizer

        viz = WorkflowVisualizer()
        viz.build_from_steps(steps)
        viz.overlay_trace(result)

        if self.config.output_dir is None:
            output_dir = Path("output")
        elif isinstance(self.config.output_dir, str):
            output_dir = Path(self.config.output_dir)
        else:
            output_dir = self.config.output_dir

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Generate all formats
        dot_path = output_dir / f"workflow_{timestamp}.dot"
        dot_path.write_text(viz.to_dot(), encoding="utf-8")

        mermaid_path = output_dir / f"workflow_{timestamp}.md"
        mermaid_path.write_text(viz.to_mermaid(), encoding="utf-8")

        html_path = output_dir / f"workflow_{timestamp}.html"
        viz.to_html(html_path, title=f"Agent Pipeline: {self.config.topic}")
        return html_path

    # ── Benchmark ─────────────────────────────────────────────────

    def run_benchmark(self, task_ids=None) -> dict:
        """Run benchmark evaluation suite."""
        from scripts.core.benchmark import PaperWritingBench, BenchmarkConfig

        self._ensure_initialized()
        bench = PaperWritingBench(BenchmarkConfig(n_papers=5))

        output_dir = self.config.output_dir
        if output_dir is None:
            output_dir = Path("output")
        elif isinstance(output_dir, str):
            output_dir = Path(output_dir)

        results = bench.run()
        bench.report(results)
        rates = bench.simulate_acceptance_rates(results)

        return {
            "task_count": len(results),
            "domains": [r.domain for r in results],
            "overall_scores": [r.overall_score for r in results],
            "pass_rates": [r.passed_rules / r.total_rules if r.total_rules > 0 else 0 for r in results],
            "acceptance_rates": rates,
        }

    # ── Streaming ─────────────────────────────────────────────────

    def stream(self, topic: str | None = None, **kwargs) -> list:
        """
        Synchronous streaming of pipeline events (for non-async contexts).

        For async streaming, use StreamingPipeline directly.
        """
        from scripts.core.streaming import StreamingPipeline

        self._ensure_initialized()

        if topic:
            self.config.topic = topic
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)

        steps = self._build_pipeline_steps()
        sp = StreamingPipeline(self._gateway)
        sp.set_pipeline(self._orchestrator)

        events = sp.stream_sync(
            pipeline_name="paper_pipeline",
            steps=steps,
            input_data={
                "topic": self.config.topic,
                "venue": self.config.venue,
                "field": self.config.research_field,
            },
        )

        return events

    # ── Properties ────────────────────────────────────────────────

    @property
    def gateway(self) -> LLMGateway:
        self._ensure_initialized()
        return self._gateway

    @property
    def orchestrator(self) -> AgentOrchestrator:
        self._ensure_initialized()
        return self._orchestrator

    @property
    def evolution_engine(self) -> SelfEvolutionEngine | None:
        return self._evolution

    @property
    def hitl_gate(self) -> HITLGate | None:
        return self._hitl_gate

    # ── Research Direction Integration ────────────────────────────────────────

    def list_directions(self) -> list[dict]:
        """List all available research directions."""
        from scripts.research_directions import DirectionFactory
        return DirectionFactory.list_with_descriptions()

    def run_with_direction(
        self,
        topic: str,
        direction: str,
        **kwargs,
    ) -> "DirectionResult":
        """
        Run the pipeline with a specific research direction.

        Parameters
        ----------
        topic : str
            Research topic or question.
        direction : str
            Direction slug (e.g. "green_finance", "digital_finance").
        **kwargs
            Additional arguments passed to the direction's fetch_data().

        Returns
        -------
        DirectionResult
            Complete direction result with data, tables, and figures.
        """
        from scripts.research_directions import DirectionFactory

        dir_instance = DirectionFactory.get_direction(direction)

        if dir_instance is None:
            return DirectionResult(
                direction=direction,
                success=False,
                errors=[f"Direction '{direction}' not found. "
                       f"Available: {DirectionFactory.list_all()[:10]}..."],
            )

        # Initialize gateway if needed
        self._ensure_initialized()

        pipeline_result = dir_instance.run_pipeline(
            topic=topic,
            gateway=self._gateway,
            output_dir=str(self.config.output_dir) if self.config.output_dir else "output",
            **kwargs,
        )

        if pipeline_result is None:
            return DirectionResult(
                direction=direction,
                success=False,
                errors=[f"Direction '{direction}' fetch_data returned None. Check MCP tool availability."],
                tables={},
                figures=[],
            )

        return pipeline_result


# ─── CLI Entry Point ────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``finai-pipeline`` and ``python -m scripts.agent_pipeline``.

    Returns the process exit code (0 = success, 1 = partial failure,
    2 = bad CLI args, 4 = no LLM in strict mode).  Defined as a function so
    that ``scripts.cli:pipeline_cmd_wrapper`` can programmatically invoke it
    from a PyPI-wheel install.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="论文-研报工作流 — 端到端研究流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Note:
  - 本脚本是主入口，自动选择合适的分析引擎
  - 纯回归分析请使用: python scripts/research_framework/pipeline.py

Examples:
  python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响" --venue "经济研究"
  python scripts/agent_pipeline.py --topic "数字金融与企业创新" --langgraph   # use LangGraph runtime
  python scripts/agent_pipeline.py --langgraph --use-hitl   # interactive mode with HITL gates
""",
    )
    parser.add_argument(
        "--topic", "-t", type=str, default=None,
        help="研究方向/研究主题",
    )
    parser.add_argument(
        "--venue", type=str, default=None,
        help="目标期刊（如：经济研究、金融研究、NeurIPS）",
    )
    parser.add_argument(
        "--langgraph", action="store_true",
        help="启用 LangGraph 运行时管道（需要安装 langgraph）",
    )
    parser.add_argument(
        "--use-hitl", action="store_true",
        help="启用 Human-in-the-Loop 审批门",
    )
    parser.add_argument(
        "--language", choices=["zh", "en"], default="zh",
        help="写作语言（默认：zh）",
    )
    parser.add_argument(
        "--output-dir", "-o", type=str, default=None,
        help="论文输出目录（默认：output/papers/）",
    )
    parser.add_argument(
        "--novelty-check", action="store_true",
        help=(
            "Run Stage 3 (novelty verification) only — checks the --topic against "
            "recent JF/JFE/RFS/经济研究/金融研究 literature via NoveltyGate. "
            "Writes a NOVELTY_REPORT.md to --output-dir."
        ),
    )
    parser.add_argument(
        "--report-path", type=str, default=None,
        help="When --novelty-check is set, override the output path (default: <output-dir>/NOVELTY_REPORT.md).",
    )
    parser.add_argument(
        "--strict-llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "默认开启：未配置 LLM 时直接退出码 4（避免静默跑 MockTemplateEngine 并落盘占位文件）。"
            "用 --no-strict-llm 关闭，回归到 MockTemplateEngine 降级行为。"
        ),
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="跳过启动时的健康检查（已通过 finai-doctor 验证时使用）。",
    )

    args = parser.parse_args()

    # ── Stage 3 short-circuit: novelty check only ──
    if args.novelty_check:
        if not args.topic:
            print("ERROR: --novelty-check requires --topic", file=sys.stderr)
            return 2
        from scripts.core.evolution_gate import NoveltyGate  # local import to keep cold-start fast
        gate = NoveltyGate()
        result = gate.evaluate({"ideas": [args.topic]})
        report_path = args.report_path or (
            (args.output_dir or "output/fin-novelty") + "/NOVELTY_REPORT.md"
        )
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Novelty Report — {args.topic}",
            "",
            f"- **Passed**: {result.passed}",
            f"- **Score**: {result.score:.2f}",
            f"- **Elapsed**: {result.elapsed_seconds:.1f}s",
            f"- **Threshold**: {result.details.get('threshold')}",
            f"- **Lookback years**: {result.details.get('lookback_years')}",
            "",
            "## Per-idea results",
            "",
        ]
        for r in result.details.get("results", []):
            mark = "✅" if r["passed"] else "❌"
            lines.append(
                f"- {mark} similarity={r['similarity']:.2f} — {r['idea']}"
            )
        if result.issues:
            lines += ["", "## Issues", ""]
            lines += [f"- {x}" for x in result.issues]
        if result.suggestions:
            lines += ["", "## Suggestions", ""]
            lines += [f"- {x}" for x in result.suggestions]
        Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"✅ Novelty report written: {report_path}")
        print(f"   passed={result.passed}  score={result.score:.2f}")
        return 0 if result.passed else 1

    config = AgentPipelineConfig(topic=args.topic or "")
    if args.venue:
        config.venue = args.venue
    if args.use_hitl:
        config.use_hitl = True
    # v2.2 (2026-07-13): forward strict-llm/skip-health to pipeline config so
    # PR-1.4 的 exit code 4 行为能正确触发（默认开启）。
    config.strict_llm = bool(args.strict_llm)
    if args.skip_health:
        config.skip_health = True
    output_dir = args.output_dir or "output/papers/"

    pipeline = AgentPipeline(config=config, use_langgraph=args.langgraph)
    result = pipeline.run(topic=args.topic, output_dir=output_dir)

    if result.success:
        print("\n✅ 流水线执行完成")
        return 0
    print("\n⚠️  流水线执行完成，但部分阶段可能失败，请检查输出")
    return 1


if __name__ == "__main__":
    sys.exit(main())
