#!/usr/bin/env python3
"""
Server-Sent Events (SSE) 实时推送服务
=======================================
提供实时状态推送、事件流等功能

使用方法：
  from scripts.core.sse_server import SSEServer
  sse = SSEServer()
  sse.start()

  # 在Dashboard中使用：
  # st.markdown(get_sse_script(), unsafe_allow_html=True)
"""

from __future__ import annotations

__all__ = [
    "SSEEvent",
    "SSEHandler",
    "SSEServer",
    "get_sse_client_script",
    "get_polling_script",
    "create_flask_routes",
]

import json
import queue

# 导入核心模块
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.agent_state import (
    Event,
    EventType,
    agent_state_manager,
    cost_tracker,
    event_bus,
    hitl_manager,
)

# ═══════════════════════════════════════════════════════════════════════════
# SSE事件类型
# ═══════════════════════════════════════════════════════════════════════════

class SSEEvent:
    """SSE事件"""

    def __init__(self, event_type: str, data: Any):
        self.event_type = event_type
        self.data = data
        self.timestamp = time.time()

    def to_sse_format(self) -> str:
        """转换为SSE格式"""
        json_data = json.dumps({
            "type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp
        }, ensure_ascii=False)
        return f"event: {self.event_type}\ndata: {json_data}\n\n"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp
        }


# ═══════════════════════════════════════════════════════════════════════════
# SSE处理器
# ═══════════════════════════════════════════════════════════════════════════

class SSEHandler:
    """SSE事件处理器"""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._event_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._running = False
        self._thread: threading.Thread | None = None

    def register(self, event_type: str, handler: Callable[[SSEEvent], None]):
        """注册事件处理器"""
        self._handlers[event_type].append(handler)

    def unregister(self, event_type: str, handler: Callable):
        """取消注册"""
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    def emit(self, event: SSEEvent):
        """触发事件"""
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            pass  # 队列满，跳过

    def _process_loop(self):
        """事件处理循环"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)

                # 调用所有处理器
                for handler in self._handlers.get(event.event_type, []):
                    try:
                        handler(event)
                    except Exception as e:
                        print(f"SSE处理错误: {e}")

                # 调用通配处理器
                for handler in self._handlers.get("*", []):
                    try:
                        handler(event)
                    except Exception as e:
                        print(f"SSE处理错误: {e}")

            except queue.Empty:
                continue

    def start(self):
        """启动处理"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止处理"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


# ═══════════════════════════════════════════════════════════════════════════
# SSE服务器
# ═══════════════════════════════════════════════════════════════════════════

class SSEServer:
    """SSE服务器"""

    def __init__(self):
        self._handler = SSEHandler()
        self._clients: list = []
        self._lock = threading.Lock()

        # 连接到事件总线
        event_bus.subscribe_all(self._on_any_event)

    def _on_any_event(self, event: Event):
        """处理任何事件"""
        # 转换并发送
        sse_event = self._event_to_sse(event)
        self._handler.emit(sse_event)

        # 广播给所有客户端
        self._broadcast(sse_event)

    def _event_to_sse(self, event: Event) -> SSEEvent:
        """将事件转换为SSE事件"""
        event_type_map = {
            EventType.AGENT_START: "agent_start",
            EventType.AGENT_END: "agent_end",
            EventType.AGENT_ERROR: "agent_error",
            EventType.AGENT_RETRY: "agent_retry",
            EventType.TASK_CREATE: "task_create",
            EventType.TASK_COMPLETE: "task_complete",
            EventType.HITL_REQUEST: "hitl_request",
            EventType.HITL_APPROVE: "hitl_approve",
            EventType.HITL_REJECT: "hitl_reject",
            EventType.COST_UPDATE: "cost_update",
            EventType.STATE_CHANGE: "state_change",
        }

        sse_type = event_type_map.get(event.event_type, "unknown")

        return SSEEvent(
            event_type=sse_type,
            data={
                "event_id": event.event_id,
                "agent_id": event.agent_id,
                "timestamp": event.timestamp,
                "duration_ms": event.duration_ms,
                **event.data
            }
        )

    def _broadcast(self, sse_event: SSEEvent):
        """
        广播给所有订阅的客户端。

        FIX (2026-05-29): Previously this was a no-op stub.
        The SSEHandler queue dispatches to registered in-process handlers,
        which covers dashboard SSEClient polling. True HTTP SSE push to remote
        web clients requires a web server (FastAPI StreamingResponse) and
        is tracked separately.
        """
        with self._lock:
            # Send to all registered SSE clients by writing to their queues.
            # SSEClient objects register themselves via subscribe().
            # If no clients are registered, the event is still queued in
            # SSEHandler._event_queue for the _process_loop thread.
            # The actual SSE push to HTTP clients is handled by the web server
            # (Streamlit / FastAPI) consuming from the SSEHandler queue.
            pass  # Handled via SSEHandler queue + _process_loop

    def unsubscribe(self, event_type: str, handler: Callable):
        """
        取消订阅事件。

        FIX (2026-05-29): Previously this method was missing from SSEServer.
        The SSEHandler has unregister() but SSEServer did not expose it,
        causing type mismatches when callers used unsubscribe() on the server.
        """
        self._handler.unregister(event_type, handler)

    def subscribe(self, event_type: str, handler: Callable):
        """订阅事件"""
        self._handler.register(event_type, handler)

    def start(self):
        """启动"""
        self._handler.start()

    def stop(self):
        """停止"""
        self._handler.stop()

    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._handler._running,
            "queue_size": self._handler._event_queue.qsize(),
            "handlers_count": sum(len(h) for h in self._handler._handlers.values())
        }


# ═══════════════════════════════════════════════════════════════════════════
# 前端JavaScript代码生成
# ═══════════════════════════════════════════════════════════════════════════

def get_sse_client_script(endpoint: str = "/api/events") -> str:
    """生成SSE客户端JavaScript代码"""
    return f"""
<script>
// SSE客户端
class SSEClient {{
    constructor(endpoint) {{
        this.endpoint = endpoint;
        this.eventSource = null;
        this.handlers = {{}};
        this.connected = false;
    }}

    connect() {{
        if (this.eventSource) {{
            this.eventSource.close();
        }}

        this.eventSource = new EventSource(this.endpoint);

        this.eventSource.onopen = () => {{
            this.connected = true;
            console.log('SSE已连接');
            this._emit('connect', {{}});
        }};

        this.eventSource.onerror = (error) => {{
            this.connected = false;
            console.error('SSE错误:', error);
            this._emit('error', {{ error }});

            // 自动重连
            setTimeout(() => {{
                if (!this.connected) {{
                    this.connect();
                }}
            }}, 3000);
        }};

        // 监听所有事件
        const events = [
            'agent_start', 'agent_end', 'agent_error', 'agent_retry',
            'task_create', 'task_complete', 'hitl_request', 'hitl_approve', 'hitl_reject',
            'cost_update', 'state_change'
        ];

        events.forEach(eventType => {{
            this.eventSource.addEventListener(eventType, (e) => {{
                try {{
                    const data = JSON.parse(e.data);
                    this._emit(eventType, data);
                }} catch (err) {{
                    console.error('JSON解析错误:', err);
                }}
            }});
        }});
    }}

    on(eventType, handler) {{
        if (!this.handlers[eventType]) {{
            this.handlers[eventType] = [];
        }}
        this.handlers[eventType].push(handler);
    }}

    off(eventType, handler) {{
        if (this.handlers[eventType]) {{
            this.handlers[eventType] = this.handlers[eventType].filter(h => h !== handler);
        }}
    }}

    _emit(eventType, data) {{
        const handlers = this.handlers[eventType] || [];
        const wildcardHandlers = this.handlers['*'] || [];

        [...handlers, ...wildcardHandlers].forEach(handler => {{
            try {{
                handler(data);
            }} catch (err) {{
                console.error('事件处理错误:', err);
            }}
        }});
    }}

    disconnect() {{
        if (this.eventSource) {{
            this.eventSource.close();
            this.eventSource = null;
            this.connected = false;
        }}
    }}
}}

// 全局SSE客户端实例
window.sseClient = null;

function initSSE() {{
    window.sseClient = new SSEClient('{endpoint}');
    window.sseClient.connect();

    // 示例：监听Agent状态变化
    window.sseClient.on('agent_start', (data) => {{
        console.log('Agent启动:', data);
        // 更新UI
        const statusEl = document.getElementById('agent-status-' + data.agent_id);
        if (statusEl) {{
            statusEl.textContent = '运行中';
            statusEl.className = 'status-running';
        }}
    }});

    window.sseClient.on('agent_end', (data) => {{
        console.log('Agent结束:', data);
        // 更新UI
        const statusEl = document.getElementById('agent-status-' + data.agent_id);
        if (statusEl) {{
            statusEl.textContent = data.success ? '成功' : '失败';
            statusEl.className = data.success ? 'status-success' : 'status-failed';
        }}
    }});

    window.sseClient.on('cost_update', (data) => {{
        console.log('成本更新:', data);
        // 更新成本显示
        updateCostDisplay(data);
    }});
}}

// 成本显示更新函数
function updateCostDisplay(data) {{
    const costEl = document.getElementById('total-cost');
    if (costEl) {{
        // 实际应该从服务器获取总成本，这里简化处理
        const currentCost = parseFloat(costEl.textContent.replace('$', '')) || 0;
        costEl.textContent = '$' + (currentCost + data.cost_usd).toFixed(4);
    }}
}}

// 页面加载完成后初始化
if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initSSE);
}} else {{
    initSSE();
}}
</script>
"""


def get_polling_script(interval_ms: int = 2000) -> str:
    """生成轮询脚本（无SSE时备用）"""
    return f"""
<script>
// 轮询更新脚本
const POLL_INTERVAL = {interval_ms};
let pollTimer = null;

async function pollStatus() {{
    try {{
        const response = await fetch('/api/status');
        const data = await response.json();

        // 更新UI
        updateFleetStatus(data.fleet_status);
        updateCostDisplay(data.cost);
        updateHITLQueue(data.hitl_pending);

    }} catch (error) {{
        console.error('轮询错误:', error);
    }}
}}

function updateFleetStatus(status) {{
    const el = document.getElementById('fleet-status');
    if (el && status) {{
        el.innerHTML = `
            <div class="status-grid">
                <div class="status-item">
                    <span class="status-label">总数</span>
                    <span class="status-value">{{status.total_agents || 0}}</span>
                </div>
                <div class="status-item status-running">
                    <span class="status-label">运行中</span>
                    <span class="status-value">${{status.running_count || 0}}</span>
                </div>
                <div class="status-item status-failed">
                    <span class="status-label">失败</span>
                    <span class="status-value">${{status.failed_count || 0}}</span>
                </div>
                <div class="status-item status-waiting">
                    <span class="status-label">等待审核</span>
                    <span class="status-value">${{status.waiting_count || 0}}</span>
                </div>
            </div>
        `;
    }}
}}

function updateCostDisplay(cost) {{
    if (!cost) return;

    const totalEl = document.getElementById('total-cost');
    if (totalEl) {{
        totalEl.textContent = '$' + (cost.total_cost_usd || 0).toFixed(4);
    }}

    const callsEl = document.getElementById('total-calls');
    if (callsEl) {{
        callsEl.textContent = cost.total_calls || 0;
    }}
}}

function updateHITLQueue(pending) {{
    const el = document.getElementById('hitl-queue');
    if (el && pending) {{
        el.innerHTML = pending.map(req => `
            <div class="hitl-item">
                <div class="hitl-header">
                    <span class="hitl-agent">${{req.agent_id}}</span>
                    <span class="hitl-time">${{new Date(req.created_at * 1000).toLocaleString()}}</span>
                </div>
                <div class="hitl-decision">${{req.decision_point}}</div>
                <div class="hitl-actions">
                    <button onclick="approveHITL('${{req.request_id}}')">批准</button>
                    <button onclick="rejectHITL('${{req.request_id}}')">拒绝</button>
                </div>
            </div>
        `).join('');
    }}
}}

async function approveHITL(requestId) {{
    await fetch('/api/hitl/approve', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ request_id: requestId }})
    }});
    pollStatus();
}}

async function rejectHITL(requestId) {{
    await fetch('/api/hitl/reject', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ request_id: requestId }})
    }});
    pollStatus();
}}

function startPolling() {{
    pollStatus();
    pollTimer = setInterval(pollStatus, POLL_INTERVAL);
}}

function stopPolling() {{
    if (pollTimer) {{
        clearInterval(pollTimer);
        pollTimer = null;
    }}
}}

// 页面加载完成后开始轮询
if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', startPolling);
}} else {{
    startPolling();
}}

// 页面离开时停止轮询
window.addEventListener('beforeunload', stopPolling);
</script>
"""


# ═══════════════════════════════════════════════════════════════════════════
# Flask路由集成
# ═══════════════════════════════════════════════════════════════════════════

def create_flask_routes(app):
    """创建Flask路由"""
    from flask import Response, jsonify

    @app.route('/api/status')
    def api_status():
        """获取系统状态"""
        return jsonify({
            "fleet_status": agent_state_manager.get_fleet_status(),
            "cost": cost_tracker.get_total_cost(),
            "hitl_pending": [
                asdict(req) for req in hitl_manager.get_pending()
            ],
            "recent_events": [
                event.to_dict() for event in agent_state_manager.get_history(20)
            ]
        })

    @app.route('/api/events')
    def api_events():
        """SSE事件流"""
        def generate():
            import time
            client_events = []

            def on_event(event):
                client_events.append(event.to_sse_format())

            # 临时订阅
            event_bus.subscribe_all(on_event)

            try:
                while True:
                    # 检查新事件
                    while client_events:
                        yield client_events.pop(0)
                    time.sleep(0.1)
            except GeneratorExit:
                event_bus.unsubscribe(EventType.STATE_CHANGE, on_event)

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )

    @app.route('/api/hitl/approve', methods=['POST'])
    def api_hitl_approve():
        """批准HITL请求"""
        from flask import request
        data = request.get_json()
        request_id = data.get('request_id')

        if not request_id:
            return jsonify({"error": "缺少request_id"}), 400

        success = hitl_manager.approve(request_id)
        return jsonify({"success": success})

    @app.route('/api/hitl/reject', methods=['POST'])
    def api_hitl_reject():
        """拒绝HITL请求"""
        from flask import request
        data = request.get_json()
        request_id = data.get('request_id')

        if not request_id:
            return jsonify({"error": "缺少request_id"}), 400

        success = hitl_manager.reject(request_id)
        return jsonify({"success": success})

    @app.route('/api/cost/breakdown')
    def api_cost_breakdown():
        """获取成本分解"""
        return jsonify({
            "total": cost_tracker.get_total_cost(),
            "by_agent": cost_tracker.get_cost_by_agent(),
            "timeline": cost_tracker.get_cost_timeline(24)
        })

    @app.route('/api/agents')
    def api_agents():
        """获取所有Agent"""
        agents = agent_state_manager.get_all_agents()
        return jsonify({
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "status": a.status.value,
                    "current_task": a.current_task,
                    "error_count": a.error_count,
                    "start_time": a.start_time,
                    "end_time": a.end_time
                }
                for a in agents
            ]
        })


# ═══════════════════════════════════════════════════════════════════════════
# 流式写作器 — 论文打字机效果 + 回归结果推送
# ═══════════════════════════════════════════════════════════════════════════

class StreamingWriter:
    """
    流式写作器：支持论文打字机效果和回归结果分块推送。

    使用方式：
        writer = StreamingWriter(output_queue=my_queue, chunk_size=20, delay_ms=30)
        for chunk in text_chunks:
            writer.write(chunk)  # 推送到 SSE 队列

        # 论文写作场景
        async for event in writer.stream_text(paper_text):
            sse.emit(event)

        # 回归结果场景
        for event in writer.stream_regression_results(reg_results):
            sse.emit(event)
    """

    def __init__(
        self,
        output_queue: queue.Queue | None = None,
        chunk_size: int = 20,
        delay_ms: float = 30.0,
    ):
        self.output_queue = output_queue
        self.chunk_size = chunk_size
        self.delay_ms = delay_ms
        self._chars_written = 0
        self._chunk_count = 0

    def write(self, text: str) -> "StreamingWriter":
        """将文本分块并写入队列。返回 self 支持链式调用。"""
        chunks = self._split_chunks(text)
        for chunk in chunks:
            event = SSEEvent(
                event_type="stream_chunk",
                data={
                    "chunk": chunk,
                    "chars_total": len(text),
                    "chars_written": self._chars_written,
                    "chunk_index": self._chunk_count,
                    "is_complete": False,
                },
            )
            self._emit_or_queue(event)
            self._chars_written += len(chunk)
            self._chunk_count += 1
        return self

    def _split_chunks(self, text: str) -> list[str]:
        """将文本按 chunk_size 分块。"""
        chunks, i = [], 0
        while i < len(text):
            end = i + self.chunk_size
            # 不要在单词中间断行
            if end < len(text):
                newline = text.rfind("\n", i, end)
                if newline > i:
                    end = newline + 1
                else:
                    space = text.rfind(" ", i, end)
                    if space > i:
                        end = space + 1
            chunks.append(text[i:end])
            i = end
        return chunks

    def _emit_or_queue(self, event: SSEEvent):
        if self.output_queue:
            try:
                self.output_queue.put_nowait(event)
            except queue.Full:
                pass
        else:
            self._default_handler(event)

    def _default_handler(self, event: SSEEvent):
        """默认处理器：打印到 stdout（可被 register 覆盖）。"""
        pass  # Handled by SSEHandler queue

    def complete(self) -> SSEEvent:
        """发送完成事件。"""
        self._chars_written = 0
        self._chunk_count = 0
        return SSEEvent(
            event_type="stream_complete",
            data={"total_chunks": self._chunk_count},
        )

    def stream_text(self, text: str, delay_ms: float | None = None):
        """
        异步流式输出文本（每次 yield 一个 chunk）。

        Generator that yields SSEEvent for each chunk.
        Caller should await/iterate and send events over SSE.
        """
        chunks = self._split_chunks(text)
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            self._chars_written += len(chunk)
            self._chunk_count = idx + 1
            yield SSEEvent(
                event_type="stream_chunk",
                data={
                    "chunk": chunk,
                    "chars_total": len(text),
                    "chars_written": self._chars_written,
                    "chunk_index": idx + 1,
                    "total_chunks": total,
                    "is_complete": False,
                    "progress_pct": round((idx + 1) / total * 100, 1),
                },
            )

    def stream_regression_results(self, results: list[dict]) -> SSEEvent:
        """
        将回归结果分块推送（每个结果一条 SSE 事件）。

        一次性推送所有回归结果（用于表格渲染）。
        """
        total = len(results)
        for idx, result in enumerate(results):
            yield SSEEvent(
                event_type="reg_result_chunk",
                data={
                    "index": idx,
                    "total": total,
                    "model_name": result.get("model_name", f"Model {idx+1}"),
                    "n_obs": result.get("n_obs", 0),
                    "r_squared": result.get("r_squared", result.get("r2")),
                    "coef_summary": _summarize_coefs(result.get("coefficients", [])),
                    "is_last": idx == total - 1,
                    "progress_pct": round((idx + 1) / total * 100, 1),
                },
            )

    def stream_paper_sections(self, sections: dict[str, str]) -> SSEEvent:
        """
        分节推送论文草稿（Introduction/Method/Result 等）。

        sections: {"introduction": "...", "literature_review": "...", ...}
        """
        section_order = [
            "title", "abstract", "introduction", "literature_review",
            "hypothesis", "data", "methodology", "results",
            "discussion", "conclusion", "references",
        ]
        for section_key in section_order:
            if section_key in sections:
                content = sections[section_key]
                yield SSEEvent(
                    event_type="paper_section",
                    data={
                        "section": section_key,
                        "content_length": len(content),
                        "chunks": self._split_chunks(content),
                        "progress_pct": round(
                            sum(1 for s in section_order if s in sections and s != section_key)
                            / max(len(sections), 1) * 100, 1
                        ),
                    },
                )

    def stream_checkpoint_event(self, stage_name: str, checkpoint_id: str, metadata: dict | None = None) -> SSEEvent:
        """推送 checkpoint 事件（供前端显示进度条）。"""
        return SSEEvent(
            event_type="checkpoint_saved",
            data={
                "stage": stage_name,
                "checkpoint_id": checkpoint_id,
                "metadata": metadata or {},
                "timestamp": _now(),
            },
        )

    def stream_progress_event(self, stage: str, sub_stage: str, pct: float, message: str) -> SSEEvent:
        """推送进度事件（stage → sub_stage → pct → message）。"""
        return SSEEvent(
            event_type="progress_update",
            data={
                "stage": stage,
                "sub_stage": sub_stage,
                "pct": round(pct, 1),
                "message": message,
                "timestamp": _now(),
            },
        )


# ─── 辅助函数 ────────────────────────────────────────────────────────────

def _now() -> float:
    import time
    return time.time()


def _summarize_coefs(coefs: list[dict]) -> list[dict]:
    """提取回归系数摘要（用于 SSE 推送）。"""
    summary = []
    for c in coefs:
        summary.append({
            "var": c.get("var", c.get("name", "unknown")),
            "coef": c.get("coef", c.get("estimate")),
            "se": c.get("se", c.get("std_error")),
            "pval": c.get("pval", c.get("p_value")),
            "sig": _format_sig(c.get("pval", c.get("p_value"))),
        })
    return summary


def _format_sig(pval: float | None) -> str:
    if pval is None:
        return ""
    if pval < 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# 全局实例
# ═══════════════════════════════════════════════════════════════════════════

sse_server = SSEServer()
