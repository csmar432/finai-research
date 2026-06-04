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

Usage:
    # Basic usage
    from scripts.agent_pipeline import AgentPipeline
    pipeline = AgentPipeline()
    result = pipeline.run("LLM在金融时间序列预测中的应用", venue="NeurIPS 2025")

    # Streaming
    async for event in pipeline.stream("..."):
        print(event.event_type, event.data)

    # Benchmark
    from scripts.core.benchmark import BenchmarkEvaluator
    evaluator = BenchmarkEvaluator(gateway)
    evaluator.run_benchmark_suite()

Canvas可视化：
    运行期间可在 Cursor 中打开 workflow-progress.canvas.tsx 查看实时进度。
    Python 端通过 localStorage 推送数据（JSON），Canvas 每2秒轮询一次。
"""

import json
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.core.platform import (
    PROJECT_ROOT,
    get_canvas_file_path,
    is_canvas_available,
)


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
        except Exception:
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
        except Exception:
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
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    except Exception:
        pass

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
    except Exception:
        pass




def _print_canvas_hint(stage: str, detail: str = "") -> None:
    """
    在终端打印 Canvas 链接横幅，并将状态写入缓存文件供 Agent 读取。
    """
    banner = _build_canvas_banner(stage, detail)
    print(banner)

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
    except Exception:
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
        except Exception:
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
    timestamp: float = field(default_factory=time.time)


# ─── Pipeline Result ───────────────────────────────────────────────────────────


@dataclass
class AgentPipelineResult:
    """Result of a complete agent pipeline run."""
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
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "topic": self.config.topic,
                "venue": self.config.venue,
                "research_field": self.config.research_field,
            },
            "success": self.success,
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

    def __init__(self, config: AgentPipelineConfig | None = None):
        self.config = config or AgentPipelineConfig(topic="")
        self._gateway: LLMGateway | None = None
        self._orchestrator: AgentOrchestrator | None = None
        self._verifier: CitationVerifier | None = None
        self._evolution: SelfEvolutionEngine | None = None
        self._hitl_gate: HITLGate | None = None
        self._memory = None
        self._initialized = False
        self._current_steps: list = []

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
            cache_dir=str(output_dir / ".cache" / "citations"),
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

        self._initialized = True

        # Auto-start visualization server (non-blocking, background thread)
        self._start_viz_server_if_needed()

    def _start_viz_server_if_needed(self) -> bool:
        """启动可视化服务（如未运行）。"""
        try:
            from scripts.workflow_viz_server import VisualizationServer
            viz_server = VisualizationServer()
            viz_url = "http://localhost:8502"
            if viz_server.start(open_browser=False):
                print(f"  可视化服务已就绪: {viz_url}")
                return True
        except Exception:
            pass
        return False

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

        Returns
        -------
        AgentPipelineResult
            Full pipeline result with all stage outputs.
        """
        start_time = time.time()
        self._ensure_initialized()

        # ── 首次运行配置检测 ────────────────────────────────────────────────
        # 基于研究方向自动推荐配置项（不阻断，只提示）
        topic_for_check = (topic or self.config.topic or "")
        self._check_and_suggest_setup(topic_for_check)

        # ── Canvas 可视化启动提示 ───────────────────────────────────────
        viz_url = "http://localhost:8502"
        _print_canvas_hint(
            "研究工作流已启动！",
            f"可视化: {viz_url}"
        )

        # Auto-launch Streamlit dashboard
        if self.config.auto_dashboard:
            project_root = Path(__file__).parent.parent
            DashboardLauncher.launch(project_root)

        # Override config
        if topic:
            self.config.topic = topic
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)

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
        }

        orchestrator_result = self._orchestrator.run_pipeline(
            pipeline_name="paper_pipeline",
            steps=steps,
            input_data=input_data,
        )

        # Push live data to Canvas for real-time visualization
        hitl_gates: dict = {}
        if (self._orchestrator._hitl_gate and
                hasattr(self._orchestrator._hitl_gate, "_pending") and
                self._orchestrator._hitl_gate._pending):
            hitl_gates = dict(self._orchestrator._hitl_gate._pending)

        push_wf_to_canvas(
            steps,
            orchestrator_result.stage_results,
            topic=self.config.topic or "",
            hitl_gates=hitl_gates if hitl_gates else None,
            trace=orchestrator_result.trace,
            hitl_paused_at=orchestrator_result.hitl_paused_at.value if orchestrator_result.hitl_paused_at else None,
        )

        # Extract results
        result = AgentPipelineResult(
            config=self.config,
            orchestrator_result=orchestrator_result,
            total_latency_ms=(time.time() - start_time) * 1000,
            success=orchestrator_result.success,
        )

        if PipelineStage.OUTLINE in orchestrator_result.stage_results:
            result.outline = orchestrator_result.stage_results[PipelineStage.OUTLINE].output

        if PipelineStage.LITERATURE in orchestrator_result.stage_results:
            lit_result = orchestrator_result.stage_results[PipelineStage.LITERATURE]
            result.literature = lit_result.output

        if PipelineStage.PLOTTING in orchestrator_result.stage_results:
            result.plotting = orchestrator_result.stage_results[PipelineStage.PLOTTING].output

        if PipelineStage.WRITING in orchestrator_result.stage_results:
            result.writing = orchestrator_result.stage_results[PipelineStage.WRITING].output

        if PipelineStage.REFINEMENT in orchestrator_result.stage_results:
            result.refinement = orchestrator_result.stage_results[PipelineStage.REFINEMENT].output

        # Evolution events
        if self._evolution:
            result.evolution_events = self._evolution.get_history()

        # HITL approvals
        if self._hitl_gate:
            result.hitl_approvals = self._hitl_gate.get_history()

        # Visualization
        if self.config.visualize:
            result.visualization_path = self._generate_visualization(
                steps, orchestrator_result
            )

        # ── Canvas 可视化完成提示 ─────────────────────────────────────
        done_count = sum(
            1 for s in orchestrator_result.stage_results.values()
            if getattr(s, "status", None) == "approved"
        )
        total_count = len(steps)
        _print_canvas_hint(
            f"研究工作流已完成！({done_count}/{total_count} 阶段)",
            f"总耗时: {(time.time() - start_time):.1f}s | 可视化: http://localhost:8502"
        )

        return result

    def _check_and_suggest_setup(self, topic: str = "") -> None:
        """基于研究方向检测配置状态并给出提示。

        仅提示，不阻断。帮助用户了解还缺哪些配置。
        """
        try:
            from scripts.setup_wizard import check_and_guide_setup
        except ImportError:
            return  # setup_wizard 不可用时静默跳过

        result = check_and_guide_setup(topic=topic)
        if not result.get("needs_setup"):
            return

        missing = result.get("missing", [])
        guidance = result.get("guidance", "")

        # 打印配置提示（ASCII 美化格式）
        separator = "=" * 60
        print(f"\n{separator}")
        print("  [配置提示] 研究工作流配置检测")
        print(separator)

        if guidance:
            # 分段打印，每段不超过 58 字符
            for line in guidance.split("\n"):
                if line.strip():
                    print(f"  {line}")

        # 打印快速配置命令
        print(f"\n  快速配置: python scripts/setup_wizard.py --guided")
        print(f"  查看状态: python scripts/setup_wizard.py --status")
        print(separator)
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
        """Approve a HITL-paused step and resume pipeline."""
        if self._hitl_gate is None:
            return {"error": "HITL not enabled"}
        return self._orchestrator.approve_step(stage, feedback)

    def reject_step(self, stage: PipelineStage, feedback: str) -> dict:
        """Reject a HITL-paused step."""
        if self._hitl_gate is None:
            return {"error": "HITL not enabled"}
        return self._orchestrator.reject_step(stage, feedback)

    def get_pending_approvals(self) -> list:
        """Get all pending HITL approvals."""
        if self._hitl_gate:
            return self._hitl_gate.get_pending()
        return []

    def resume_pipeline(self, paused_result) -> "AgentPipelineResult":
        """
        Resume a HITL-paused pipeline after approval.

        Usage:
            # After user approves via approve_step():
            result = pipeline.resume_pipeline(orchestrator_result)
        """
        # Re-run orchestrator from the pause point
        orchestrator_result = self._orchestrator.resume_pipeline(
            paused_result, self._current_steps
        )

        # Extract results (same as run() for completed stages)
        result = AgentPipelineResult(
            config=self.config,
            orchestrator_result=orchestrator_result,
            total_latency_ms=0.0,  # incremental
            success=orchestrator_result.success,
        )

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

        sr = _LiveUpdateResult(status, node_data)
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
        from scripts.core.benchmark import BenchmarkEvaluator

        self._ensure_initialized()
        evaluator = BenchmarkEvaluator(self._gateway)

        output_dir = self.config.output_dir
        if output_dir is None:
            output_dir = Path("output")
        elif isinstance(output_dir, str):
            output_dir = Path(output_dir)

        results = evaluator.run_benchmark_suite(
            task_ids=task_ids,
            output_dir=str(output_dir / "benchmark"),
        )

        return {
            "task_count": len(results),
            "avg_overall": sum(r.overall for r in results.values()) / len(results) if results else 0,
            "results": {
                tid: {"overall": r.overall, "citation_f1": r.citation_f1}
                for tid, r in results.items()
            },
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

