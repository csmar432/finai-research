#!/usr/bin/env python3
"""
研究任务 Runner
================
从队列文件 (.cache/research_queue.json) 消费研究任务，
运行 Agent Pipeline，并将实时状态推送到可视化服务器 (8502)。

使用方式：
    # 独立运行（消费队列）
    python scripts/run_research.py

    # 同时启动可视化服务器
    python scripts/run_research.py --with-server

    # 运行特定研究主题（不写入队列，直接执行）
    python scripts/run_research.py --topic "关税政策对中国出口企业的影响"
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from pathlib import Path

# ── 项目路径 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
QUEUE_FILE = PROJECT_ROOT / ".cache" / "research_queue.json"
CACHE_FILE = PROJECT_ROOT / ".cache" / "wf_canvas_data.json"
SERVER_URL = "http://localhost:8502"
POLL_INTERVAL = 2.0  # 秒

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  状态推送
# ═══════════════════════════════════════════════════════════════════════════════

def _http_post(url: str, data: dict, timeout: float = 5.0) -> dict | None:
    """POST JSON 到服务器，返回响应 dict，失败返回 None。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.debug("HTTP POST failed: %s", e)
        return None


def _push_wf_state(nodes: list, edges: list, meta: dict) -> None:
    """将工作流状态推送到可视化服务器。"""
    payload = {"nodes": nodes, "edges": edges, "meta": meta}
    _http_post(f"{SERVER_URL}/wf_push", payload)


def _load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def _save_queue(items: list[dict]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _pop_queue() -> dict | None:
    items = _load_queue()
    if not items:
        return None
    item = items.pop(0)
    _save_queue(items)
    return item


# ═══════════════════════════════════════════════════════════════════════════════
#  工作流 Payload 构建
# ═══════════════════════════════════════════════════════════════════════════════

_STATUS_CN = {
    "running": "运行中", "approved": "已完成", "success": "已完成",
    "error": "执行失败", "max_iterations": "迭代超限",
    "pending": "待执行", "revised": "已修订",
}
_STAGE_META = {
    "outline":    {"label": "大纲设计", "color": "#9B59B6"},
    "literature": {"label": "文献综述", "color": "#3498DB"},
    "plotting":   {"label": "图表生成", "color": "#E67E22"},
    "writing":    {"label": "论文写作", "color": "#27AE60"},
    "refinement": {"label": "修改润色", "color": "#E74C3C"},
    "evaluation":  {"label": "质量评估", "color": "#1ABC9C"},
}


def build_initial_payload(topic: str) -> dict:
    """构建初始5阶段状态（全部待执行）。"""
    nodes = [
        {
            "id": "input", "label": "用户请求", "type": "input",
            "color": "#3b82f6", "status": "已完成",
            "duration_ms": 0, "tokens_used": 0, "model": "",
            "input_preview": topic, "output_preview": "", "error": "",
            "iterations": 0, "tools_called": [], "citations": [],
            "feedback": "", "is_paused": False, "has_gate": False,
            "metadata": {"stage": "input", "agent_role": "", "agent_goal": "",
                         "allowed_tools": [], "max_iterations": 0, "temperature": 0.0},
        },
    ]
    edges = []
    stage_ids = list(_STAGE_META.keys())
    prev = "input"
    for sid in stage_ids:
        nodes.append({
            "id": sid, "label": _STAGE_META[sid]["label"], "type": "agent",
            "color": _STAGE_META[sid]["color"], "status": "待执行",
            "duration_ms": 0, "tokens_used": 0, "model": "",
            "input_preview": "", "output_preview": "", "error": "",
            "iterations": 0, "tools_called": [], "citations": [],
            "feedback": "", "is_paused": False, "has_gate": False,
            "metadata": {"stage": sid, "agent_role": _STAGE_META[sid]["label"],
                         "agent_goal": "", "allowed_tools": [], "max_iterations": 3},
        })
        edges.append({"source": prev, "target": sid, "type": "sequential", "color": "#94a3b8"})
        prev = sid

    nodes.append({
        "id": "output", "label": "最终结果", "type": "output",
        "color": "#22c55e", "status": "待执行",
        "duration_ms": 0, "tokens_used": 0, "model": "",
        "input_preview": "", "output_preview": "", "error": "",
        "iterations": 0, "tools_called": [], "citations": [],
        "feedback": "", "is_paused": False, "has_gate": False,
        "metadata": {"stage": "output"},
    })
    edges.append({"source": prev, "target": "output", "type": "sequential", "color": "#94a3b8"})

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "topic": topic,
            "start_time": time.time(),
            "hitl_paused_at": None,
            "total_stages": len(stage_ids),
            "total_gates": 0,
            "pipeline_name": "paper_pipeline",
            "trace_summary": {},
        },
    }


def update_node_status(nodes: list, node_id: str, status: str,
                        duration_ms: int = 0, tokens_used: int = 0,
                        model: str = "", input_preview: str = "",
                        output_preview: str = "", error: str = "",
                        iterations: int = 0, tools_called: list = None,
                        citations: list = None, feedback: str = "") -> None:
    """更新指定节点的状态。"""
    for n in nodes:
        if n["id"] == node_id:
            n["status"] = _STATUS_CN.get(status, status)
            n["duration_ms"] = duration_ms
            n["tokens_used"] = tokens_used
            n["model"] = model
            n["input_preview"] = input_preview[:300] if input_preview else ""
            n["output_preview"] = output_preview[:500] if output_preview else ""
            n["error"] = error[:200] if error else ""
            n["iterations"] = iterations
            n["tools_called"] = tools_called or []
            n["citations"] = citations or []
            n["feedback"] = feedback[:200] if feedback else ""
            break


# ═══════════════════════════════════════════════════════════════════════════════
#  Agent Pipeline 包装
# ═══════════════════════════════════════════════════════════════════════════════

def run_agent_pipeline(topic: str) -> None:
    """运行完整的 Agent Pipeline，实时推送状态到可视化服务器。"""
    log.info("开始研究: %s", topic)

    # 构建初始状态并推送
    payload = build_initial_payload(topic)
    nodes = payload["nodes"]
    edges = payload["edges"]
    meta = payload["meta"]

    _push_wf_state(nodes, edges, meta)
    log.info("已推送初始状态: %d 个节点", len(nodes))

    try:
        # 懒加载，避免启动时导入所有模块
        from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

        cfg = AgentPipelineConfig(
            topic=topic,
            visualize=False,   # 我们自己推送状态
            auto_dashboard=False,
        )
        pipeline = AgentPipeline(config=cfg)

        # ── Stage 1: Outline ───────────────────────────────────────────────
        log.info("[1/5] 大纲设计...")
        update_node_status(nodes, "outline", "running")
        _push_wf_state(nodes, edges, meta)

        outline_result = ""
        try:
            # 模拟调用（实际需要 LLM API Key 配置）
            result = _call_agent_safely(pipeline, "outline", topic)
            if result:
                outline_result = result.get("output", "")
                update_node_status(
                    nodes, "outline", result.get("status", "approved"),
                    duration_ms=result.get("duration_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    model=result.get("model", ""),
                    output_preview=outline_result,
                    feedback=result.get("feedback", ""),
                )
            else:
                update_node_status(nodes, "outline", "error", error="LLM API 未配置或调用失败")
        except Exception as e:
            log.warning("Outline agent failed: %s", e)
            update_node_status(nodes, "outline", "error", error=str(e))
        _push_wf_state(nodes, edges, meta)

        # ── Stage 2: Literature ───────────────────────────────────────────
        log.info("[2/5] 文献综述...")
        update_node_status(nodes, "literature", "running")
        _push_wf_state(nodes, edges, meta)

        literature_result = ""
        try:
            # 传入 outline 阶段的输出作为上下文
            result = _call_agent_safely(pipeline, "literature", topic, context=outline_result)
            if result:
                literature_result = result.get("output", "")
                update_node_status(
                    nodes, "literature", result.get("status", "approved"),
                    duration_ms=result.get("duration_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    model=result.get("model", ""),
                    output_preview=literature_result,
                    citations=result.get("citations", []),
                )
            else:
                update_node_status(nodes, "literature", "error", error="LLM API 未配置或调用失败")
        except Exception as e:
            log.warning("Literature agent failed: %s", e)
            update_node_status(nodes, "literature", "error", error=str(e))
        _push_wf_state(nodes, edges, meta)

        # ── Stage 3: Plotting ───────────────────────────────────────────────
        log.info("[3/5] 图表生成...")
        update_node_status(nodes, "plotting", "running")
        _push_wf_state(nodes, edges, meta)

        plotting_result = ""
        try:
            # 传入 outline 和 literature 的输出作为上下文
            combined_context = f"## Outline\n{outline_result}\n\n## Literature Review\n{literature_result}"
            result = _call_agent_safely(pipeline, "plotting", topic, context=combined_context)
            if result:
                plotting_result = result.get("output", "")
                update_node_status(
                    nodes, "plotting", result.get("status", "approved"),
                    duration_ms=result.get("duration_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    output_preview=plotting_result,
                )
            else:
                update_node_status(nodes, "plotting", "error", error="LLM API 未配置或调用失败")
        except Exception as e:
            log.warning("Plotting agent failed: %s", e)
            update_node_status(nodes, "plotting", "error", error=str(e))
        _push_wf_state(nodes, edges, meta)

        # ── Stage 4: Writing ───────────────────────────────────────────────
        log.info("[4/5] 论文写作...")
        update_node_status(nodes, "writing", "running")
        _push_wf_state(nodes, edges, meta)

        writing_result = ""
        try:
            # 传入所有前序阶段的输出作为上下文
            full_context = f"## Outline\n{outline_result}\n\n## Literature Review\n{literature_result}\n\n## Plotting Results\n{plotting_result}"
            result = _call_agent_safely(pipeline, "writing", topic, context=full_context)
            if result:
                writing_result = result.get("output", "")
                update_node_status(
                    nodes, "writing", result.get("status", "approved"),
                    duration_ms=result.get("duration_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    model=result.get("model", ""),
                    output_preview=writing_result,
                )
            else:
                update_node_status(nodes, "writing", "error", error="LLM API 未配置或调用失败")
        except Exception as e:
            log.warning("Writing agent failed: %s", e)
            update_node_status(nodes, "writing", "error", error=str(e))
        _push_wf_state(nodes, edges, meta)

        # ── Stage 5: Refinement ────────────────────────────────────────────
        log.info("[5/5] 修改润色...")
        update_node_status(nodes, "refinement", "running")
        _push_wf_state(nodes, edges, meta)

        try:
            # 传入完整论文草稿作为上下文
            full_context = f"## Outline\n{outline_result}\n\n## Literature Review\n{literature_result}\n\n## Plotting Results\n{plotting_result}\n\n## Draft Paper\n{writing_result}"
            result = _call_agent_safely(pipeline, "refinement", topic, context=full_context)
            if result:
                update_node_status(
                    nodes, "refinement", result.get("status", "approved"),
                    duration_ms=result.get("duration_ms", 0),
                    tokens_used=result.get("tokens_used", 0),
                    output_preview=result.get("output", ""),
                    feedback=result.get("feedback", ""),
                )
            else:
                update_node_status(nodes, "refinement", "error", error="LLM API 未配置或调用失败")
        except Exception as e:
            log.warning("Refinement agent failed: %s", e)
            update_node_status(nodes, "refinement", "error", error=str(e))
        _push_wf_state(nodes, edges, meta)

        # ── Output ─────────────────────────────────────────────────────────
        update_node_status(nodes, "output", "已完成")
        _push_wf_state(nodes, edges, meta)
        log.info("研究完成: %s", topic)

    except Exception as e:
        log.error("Agent pipeline 初始化失败: %s", e)
        import traceback
        traceback.print_exc()


def _call_agent_safely(pipeline, agent_name: str, topic: str, context: str = "") -> dict | None:
    """安全调用 agent，避免因 API Key 缺失导致整体崩溃。
    
    Args:
        pipeline: AgentPipeline 实例
        agent_name: agent 名称 (outline/literature/plotting/writing/refinement)
        topic: 研究主题
        context: 前序阶段的输出，作为上下文传递给 agent
    """
    try:
        from scripts.core.orchestrator import PipelineStage

        stage_map = {
            "outline": PipelineStage.OUTLINE,
            "literature": PipelineStage.LITERATURE,
            "plotting": PipelineStage.PLOTTING,
            "writing": PipelineStage.WRITING,
            "refinement": PipelineStage.REFINEMENT,
        }
        stage = stage_map.get(agent_name)
        if not stage:
            return None

        # 尝试直接调用 orchestrator 的单个 agent
        orch = pipeline._orchestrator
        agent = orch.get_agent(agent_name)
        if not agent:
            return None

        import time as _time
        start = _time.time()
        # 传递 topic 和 context（previous_output）
        run_input = {
            "topic": topic,
            "context": context,
            "previous_output": context,
        }
        result = agent.run(run_input)
        elapsed = int((_time.time() - start) * 1000)

        output_str = ""
        if result.output:
            if isinstance(result.output, dict):
                import json as _json
                output_str = _json.dumps(result.output, ensure_ascii=False)[:500]
            else:
                output_str = str(result.output)[:500]

        return {
            "status": result.status,
            "duration_ms": elapsed,
            "tokens_used": getattr(result, "tokens_used", 0),
            "model": "",
            "output": output_str,
            "feedback": getattr(result, "feedback", "") or "",
            "citations": getattr(result, "citations", []) or [],
            "iterations": getattr(result, "iterations", 0),
        }
    except Exception as e:
        log.debug("_call_agent_safely failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  队列消费循环
# ═══════════════════════════════════════════════════════════════════════════════

def consume_loop(poll_interval: float = POLL_INTERVAL) -> None:
    """持续检查队列，有任务则执行。"""
    log.info("队列消费循环已启动 (每 %.1fs 检查一次)", poll_interval)
    log.info("提示: 打开 http://localhost:8502 查看可视化")

    while True:
        task = _pop_queue()
        if task:
            topic = task.get("topic", "")
            task_id = task.get("id", "?")
            log.info("取出任务 #%s: %s", task_id, topic[:50])
            try:
                run_agent_pipeline(topic)
            except Exception as e:
                log.error("任务 #%s 执行失败: %s", task_id, e)
                import traceback
                traceback.print_exc()
        else:
            # 无任务时等待并心跳（避免空转）
            time.sleep(poll_interval)


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="研究 Runner：消费队列并运行 Agent Pipeline")
    parser.add_argument("--topic", "-t", type=str, default="",
                        help="直接运行指定研究主题（不写入队列）")
    parser.add_argument("--with-server", action="store_true",
                        help="同时启动可视化服务器")
    parser.add_argument("--poll", type=float, default=POLL_INTERVAL,
                        help=f"队列轮询间隔（秒，默认 {POLL_INTERVAL}）")
    args = parser.parse_args()

    # 直接指定主题 → 立即执行
    if args.topic:
        run_agent_pipeline(args.topic.strip())
        return

    # 启动可视化服务器
    if args.with_server:
        log.info("启动可视化服务器...")
        try:
            from scripts.workflow_viz_server import VisualizationServer
            server = VisualizationServer()
            t = threading.Thread(target=server.start, kwargs={"open_browser": True}, daemon=True)
            t.start()
            time.sleep(1)
        except Exception as e:
            log.warning("无法启动可视化服务器: %s", e)

    # 进入消费循环
    consume_loop(poll_interval=args.poll)


if __name__ == "__main__":
    main()
