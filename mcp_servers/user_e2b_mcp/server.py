#!/usr/bin/env python3
"""
user-e2b-mcp — 云端代码执行沙箱 MCP 服务器
==========================================
通过 E2B 云端沙箱安全执行 Python 代码，防止恶意代码危害本地系统。

安装依赖：
    pip install e2b-code-interpreter mcp
    # 获取 API Key: https://e2b.dev/dashboard

重要：
    - E2B Python SDK (e2b-code-interpreter) 仅支持 Python 代码执行
    - JavaScript 执行已移除（E2B 不支持）
    - run_code 返回 Execution 对象，输出在 .logs.stdout / .logs.stderr
    - sandbox.run_command() 返回 CommandResult 对象

Usage:
    python server.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
except ImportError:
    pass

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. Run: pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-e2b-mcp")

# ── 配置 ───────────────────────────────────────────────────────────────────────
E2B_API_KEY = ""
TIMEOUT_SECONDS = 30

# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="e2b_run",
        description="在云端沙箱中执行 Python 代码（完全隔离的安全执行环境）。\n\n"
                    "功能：超时控制、包安装、stdout/stderr 捕获。\n"
                    "注意：需要 E2B_API_KEY（从 https://e2b.dev 获取）。\n"
                    "注意：E2B 仅支持 Python，不支持 JavaScript。",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"},
                "timeout": {"type": "integer", "description": "超时秒数（默认30）", "default": 30},
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "执行前安装的包列表，如 ['numpy', 'pandas']",
                },
                "network": {"type": "boolean", "description": "允许网络访问", "default": True},
            },
            "required": ["code"],
        },
    ),
    Tool(
        name="e2b_install",
        description="在沙箱中预安装 Python 包（后续 e2b_run 可用）。",
        inputSchema={
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要安装的包名列表",
                },
                "timeout": {"type": "integer", "description": "超时秒数（默认60）", "default": 60},
            },
            "required": ["packages"],
        },
    ),
    Tool(
        name="e2b_status",
        description="检查 E2B 沙箱服务状态和配额。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="e2b_safe_eval",
        description="安全的数学/表达式求值（不需要 E2B，本地执行）。",
        inputSchema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式或简单 Python 表达式"},
                "data": {"type": "object", "description": "变量上下文"},
            },
            "required": ["expression"],
        },
    ),
]


# ── 工具处理器 ─────────────────────────────────────────────────────────────

async def handle_e2b_run(args: dict) -> list[TextContent]:
    code = args.get("code", "")
    timeout = args.get("timeout", TIMEOUT_SECONDS)
    packages = args.get("packages", [])
    network = args.get("network", True)

    if not E2B_API_KEY:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "E2B_API_KEY not set. Get one at https://e2b.dev/dashboard",
            "code_preview": code[:200] if code else "",
        }, ensure_ascii=False))]

    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "e2b-code-interpreter not installed. Run: pip install e2b-code-interpreter",
        }, ensure_ascii=False))]

    try:
        async with Sandbox.create(api_key=E2B_API_KEY, timeout=timeout) as sandbox:
            # 预安装包
            if packages:
                for pkg in packages:
                    cmd_result = await sandbox.run_command(f"pip install {pkg}", timeout=60)
                    if cmd_result.exit_code != 0:
                        return [TextContent(type="text", text=json.dumps({
                            "success": False,
                            "error": f"Failed to install {pkg}: {cmd_result.stdout}",
                            "stderr": cmd_result.stderr,
                        }, ensure_ascii=False))]

            # 执行代码
            start = time.time()
            execution = await sandbox.run_code(code, timeout=timeout)
            elapsed = time.time() - start

            # 提取输出（E2B Execution.logs 是列表）
            logs = execution.logs if hasattr(execution, 'logs') else []
            stdout_parts = []
            stderr_parts = []
            for log in logs:
                if hasattr(log, 'is_stderr') and log.is_stderr:
                    stderr_parts.append(str(log.text) if hasattr(log, 'text') else str(log))
                else:
                    stdout_parts.append(str(log.text) if hasattr(log, 'text') else str(log))

            stdout = "\n".join(stdout_parts)
            stderr = "\n".join(stderr_parts)

            # 检查是否有错误
            has_error = (
                hasattr(execution, 'error') and execution.error is not None
            ) or execution.exit_code != 0

            return [TextContent(type="text", text=json.dumps({
                "success": not has_error,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": execution.exit_code if hasattr(execution, 'exit_code') else 1,
                "error": str(execution.error) if has_error and hasattr(execution, 'error') else None,
                "elapsed_seconds": round(elapsed, 2),
                "sandbox": "e2b-code-interpreter",
            }, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }, ensure_ascii=False))]


async def handle_e2b_install(args: dict) -> list[TextContent]:
    packages = args.get("packages", [])
    timeout = args.get("timeout", 60)

    if not E2B_API_KEY:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "E2B_API_KEY not set",
        }, ensure_ascii=False))]

    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "e2b-code-interpreter not installed. Run: pip install e2b-code-interpreter",
        }, ensure_ascii=False))]

    try:
        async with Sandbox.create(api_key=E2B_API_KEY, timeout=timeout) as sandbox:
            results = []
            for pkg in packages:
                cmd_result = await sandbox.run_command(f"pip install {pkg}", timeout=timeout)
                results.append({
                    "package": pkg,
                    "success": cmd_result.exit_code == 0,
                    "stdout": cmd_result.stdout,
                    "stderr": cmd_result.stderr,
                })

            all_success = all(r["success"] for r in results)
            return [TextContent(type="text", text=json.dumps({
                "success": all_success,
                "packages": results,
                "message": f"Installed {sum(r['success'] for r in results)}/{len(results)} packages",
            }, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False))]


async def handle_e2b_status(args: dict) -> list[TextContent]:
    if not E2B_API_KEY:
        return [TextContent(type="text", text=json.dumps({
            "configured": False,
            "message": "E2B_API_KEY not set. Get one at https://e2b.dev/dashboard",
        }, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({
        "configured": True,
        "message": "E2B configured. API key found.",
        "note": "Check https://e2b.dev/dashboard for quota info",
    }, ensure_ascii=False))]


async def handle_e2b_safe_eval(args: dict) -> list[TextContent]:
    """安全的本地表达式求值（不需要 E2B）。"""
    expression = args.get("expression", "")
    data = args.get("data", {})

    # 白名单：只允许安全操作
    allowed_chars = set(
        "0123456789+-*/()., []abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ_=><!|&%@#$'"
    )
    if not all(c in allowed_chars for c in expression):
        return [TextContent(type="text", text=json.dumps({
            "error": "Expression contains disallowed characters",
        }))]

    try:
        import math
        ctx: dict[str, Any] = {
            "__builtins__": {},
            "math": math,
            "abs": abs, "min": min, "max": max, "sum": sum,
            "round": round, "pow": pow, "len": len,
            "str": str, "int": int, "float": float,
            "bool": bool, "list": list, "dict": dict, "tuple": tuple,
            "True": True, "False": False, "None": None,
        }
        ctx.update(data)
        result = eval(expression, ctx)
        return [TextContent(type="text", text=json.dumps({
            "expression": expression,
            "result": result,
            "type": type(result).__name__,
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "expression": expression,
        }))]


TOOL_HANDLERS = {
    "e2b_run": handle_e2b_run,
    "e2b_install": handle_e2b_install,
    "e2b_status": handle_e2b_status,
    "e2b_safe_eval": handle_e2b_safe_eval,
}


# ── MCP Server Entry ────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def main():
    global E2B_API_KEY
    E2B_API_KEY = os.environ.get("E2B_API_KEY", "")

    key_status = "configured" if E2B_API_KEY else "NOT CONFIGURED"
    print(f"user-e2b-mcp starting... E2B: {key_status} (get key at https://e2b.dev/dashboard)", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-e2b-mcp",
                server_version="1.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
