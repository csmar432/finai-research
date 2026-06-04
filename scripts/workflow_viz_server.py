#!/usr/bin/env python3
"""
工作流可视化 HTTP 服务 (端口 8502)
===================================
提供：
  GET  /              → 返回 workflow_demo.html
  GET  /wf_data       → 返回当前工作流状态 JSON
  POST /wf_push        → 接收并保存工作流状态 JSON
  POST /start_pipeline → 将研究主题写入队列（由独立 Agent Runner 消费）
  GET  /wf_stream      → SSE 实时流

设计原则：
  Server 不导入任何 Agent/AI 代码，只操作 JSON 文件。
  Agent Runner 是独立进程，通过队列文件与 Server 解耦。

使用方法：
  # 终端1：启动可视化服务
  python scripts/workflow_viz_server.py

  # 终端2：启动 Agent Runner（消费队列）
  python scripts/run_research.py

  # 或一键启动两者
  python scripts/run_research.py --with-server
"""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# ── 项目路径 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
HTML_FILE = PROJECT_ROOT / "workflow_demo.html"
CACHE_FILE = PROJECT_ROOT / ".cache" / "wf_canvas_data.json"
QUEUE_FILE = PROJECT_ROOT / ".cache" / "research_queue.json"

# ── 队列操作 ────────────────────────────────────────────────────────────────
def read_queue() -> list[dict]:
    """读取研究队列。"""
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def write_queue(items: list[dict]) -> None:
    """写入研究队列。"""
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def pop_queue() -> dict | None:
    """弹出队首研究任务。"""
    items = read_queue()
    if not items:
        return None
    item = items.pop(0)
    write_queue(items)
    return item

def push_queue(item: dict) -> None:
    """追加研究任务到队列。"""
    items = read_queue()
    items.append(item)
    write_queue(items)

# ── 默认空状态 ─────────────────────────────────────────────────────────────
DEFAULT_NODES = [
    {
        "id": "input", "label": "用户请求", "type": "input", "shape": "stadium",
        "color": "#3b82f6", "status": "待执行",
        "duration_ms": 0, "tokens_used": 0, "model": "",
        "input_preview": "等待工作流启动...", "output_preview": "",
        "error": "", "iterations": 0, "tools_called": [], "citations": [],
        "feedback": "", "is_paused": False, "has_gate": False,
        "metadata": {"stage": "input", "agent_role": "", "agent_goal": "",
                     "allowed_tools": [], "max_iterations": 0, "temperature": 0.0},
    },
]
DEFAULT_DATA = {
    "nodes": DEFAULT_NODES,
    "edges": [],
    "meta": {
        "topic": "",
        "start_time": time.time(),
        "hitl_paused_at": None,
        "total_stages": 0,
        "total_gates": 0,
        "pipeline_name": "",
        "trace_summary": {},
    },
}

# 全局状态（线程安全）
_state_lock = threading.Lock()
_current_data: dict = dict(DEFAULT_DATA)
_server_start_time: float = time.time()


def load_data() -> dict:
    """加载当前工作流状态（优先从文件，其次默认）。"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "nodes" in data:
                return data
        except Exception:
            pass
    with _state_lock:
        return dict(_current_data)


def save_data(data: dict) -> None:
    """保存工作流状态。"""
    with _state_lock:
        global _current_data
        _current_data = dict(data)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_html() -> bytes:
    """读取 HTML 文件内容。"""
    if HTML_FILE.exists():
        return HTML_FILE.read_bytes()
    return b"<html><body><h1>workflow_demo.html not found</h1></body></html>"


# ── HTTP Handler ──────────────────────────────────────────────────────────────


class WFHandler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        pass

    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", "/workflow_demo.html"):
            self.send_html(get_html())

        elif path == "/wf_data":
            self.send_json(load_data())

        elif path == "/wf_stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last_data = ""
            try:
                while True:
                    current_data = json.dumps(load_data(), ensure_ascii=False)
                    if current_data != last_data:
                        payload = f"data: {current_data}\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                        last_data = current_data
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        elif path == "/status":
            uptime = time.time() - _server_start_time
            pending = read_queue()
            self.send_json({
                "status": "running",
                "uptime_seconds": round(uptime, 1),
                "data_loaded": CACHE_FILE.exists(),
                "queue_depth": len(pending),
            })

        elif path == "/queue_depth":
            self.send_json({"queue_depth": len(read_queue())})

        else:
            self.send_html(b"<h1>404 Not Found</h1>", 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/wf_push":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))
                save_data(data)
                self.send_json({"ok": True, "nodes_count": len(data.get("nodes", []))})
            except json.JSONDecodeError as e:
                self.send_json({"error": f"Invalid JSON: {e}"}, 400)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/start_pipeline":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                req = json.loads(body.decode("utf-8"))
                topic = req.get("topic", "").strip()
                if not topic:
                    self.send_json({"error": "topic is required"}, 400)
                    return

                task_id = int(time.time())
                task = {
                    "id": task_id,
                    "topic": topic,
                    "enqueued_at": time.time(),
                    "status": "queued",
                }
                push_queue(task)

                self.send_json({
                    "ok": True,
                    "message": "已加入研究队列",
                    "task_id": task_id,
                    "topic": topic,
                    "queue_depth": len(read_queue()),
                })
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/clear_queue":
            write_queue([])
            save_data(dict(DEFAULT_DATA))
            self.send_json({"ok": True})

        else:
            self.send_html(b"<h1>404 Not Found</h1>", 404)


# ── Server ──────────────────────────────────────────────────────────────────


class VisualizationServer:
    """工作流可视化 HTTP 服务。"""

    PORT = 8502
    BASE_URL = f"http://localhost:{PORT}"

    def __init__(self):
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def is_running(self) -> bool:
        if not self._running or self._server is None:
            try:
                with socket.create_connection(("localhost", self.PORT), timeout=1):
                    return True
            except Exception:
                return False
        return True

    def start(self, open_browser: bool = True) -> bool:
        if self.is_running():
            print(f"  可视化服务已运行于 {self.BASE_URL}")
            return True

        try:
            self._server = ThreadingHTTPServer(("localhost", self.PORT), WFHandler)
        except OSError as exc:
            if "Address already in use" in str(exc) or exc.errno == 48:
                print(f"  端口 {self.PORT} 已被占用，请先关闭占用进程或修改 PORT 常量")
                try:
                    import subprocess
                    result = subprocess.run(
                        ["lsof", "-i", f":{self.PORT}"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout.strip():
                        print(f"  占用进程:\n{result.stdout.strip()}")
                except Exception:
                    pass
                return False
            raise

        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

        print(f"  可视化服务已启动于 {self.BASE_URL}")
        if open_browser:
            time.sleep(0.5)
            webbrowser.open(self.BASE_URL)
            print(f"  浏览器已打开: {self.BASE_URL}")

        return True

    def _serve(self) -> None:
        try:
            while self._running:
                self._server.handle_request()
        except Exception:
            pass

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None

    @property
    def url(self) -> str:
        return self.BASE_URL


# ── CLI 入口 ────────────────────────────────────────────────────────────────


def main():
    print("=" * 50)
    print("  工作流可视化服务")
    print(f"  端口: {VisualizationServer.PORT}")
    print(f"  预览: http://localhost:{VisualizationServer.PORT}")
    print("=" * 50)

    server = VisualizationServer()
    server.start(open_browser=True)

    print("\n  按 Ctrl+C 停止服务\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  停止服务...")
        server.stop()
        print("  已停止")


if __name__ == "__main__":
    main()
