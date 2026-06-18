#!/usr/bin/env python3
"""
MCP Server Base Classes — shared protocol wrapping for 43 server.py files.

This module provides reusable building blocks for all MCP data source servers.
The goal is to reduce duplication of:
  - MCP server initialization (Server(), list_tools, call_tool decorators)
  - Standardized JSON error/success response formatting
  - Common startup logging and fallback handling
  - Environment variable loading (.env files)

Usage example (in any user_*/server.py):
    from mcp_servers.base import (
        create_mcp_server,
        text_response,
        error_response,
        safe_json_dumps,
        load_env,
    )

    server = create_mcp_server("user-myserver", version="1.0.0")
    TOOL_HANDLERS = {
        "my_tool": handle_my_tool,
    }
    register_tool_dispatcher(server, TOOL_HANDLERS)

    async def main():
        async with stdio_server() as (r, w):
            await server.run(r, w, ...)

This module is opt-in: existing servers continue to work unchanged.
New servers are encouraged to use the helpers for consistency.

Reference: ARCH-3 in the v3 review (43 server.py files had no shared base class).
"""
from __future__ import annotations

__all__ = [
    "create_mcp_server",
    "register_tool_dispatcher",
    "text_response",
    "error_response",
    "safe_json_dumps",
    "load_env",
    "init_logger",
    "check_optional_dep",
]

import json
import logging
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Callable, Optional

warnings.filterwarnings("ignore")


def init_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger with consistent formatting."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
        )
        log.addHandler(handler)
    log.setLevel(level)
    return log


def load_env(project_root: Optional[Path] = None) -> bool:
    """Load .env file from project root if python-dotenv is available.

    Returns True if .env was found and loaded, False otherwise.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    if project_root is None:
        # Default: two levels up from this file (mcp_servers/base.py → project root)
        project_root = Path(__file__).resolve().parent.parent

    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
        return True
    return False


def safe_json_dumps(obj: Any, ensure_ascii: bool = False) -> str:
    """Safely serialize obj to JSON, falling back to repr() for non-serializable values."""
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii, default=str)
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"serialization failed: {exc}", "raw": repr(obj)[:500]})


def text_response(payload: Any, tool_name: str = "") -> list:
    """Wrap a payload as an MCP TextContent list response.

    Args:
        payload: dict / list / str to serialize
        tool_name: optional tool name for error context
    """
    from mcp.types import TextContent  # type: ignore[import-not-found]

    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, dict) and len(payload) == 1 and "error" in payload and tool_name:
        text = safe_json_dumps({"tool": tool_name, **payload})
    else:
        text = safe_json_dumps(payload)
    return [TextContent(type="text", text=text)]


def error_response(message: str, tool_name: str = "", hint: str = "") -> list:
    """Generate a standardized error response.

    Returns a list of TextContent with a structured error dict.
    """
    payload: dict[str, Any] = {"error": message, "success": False}
    if hint:
        payload["hint"] = hint
    if tool_name:
        payload["tool"] = tool_name
    return text_response(payload)


def create_mcp_server(name: str, version: str = "1.0.0"):
    """Create an MCP Server instance with consistent error handling.

    Returns a Server object. Raises RuntimeError if mcp package is unavailable.
    """
    try:
        from mcp.server import Server  # type: ignore[import-not-found]
    except ImportError:
        raise RuntimeError(
            "mcp package is required. Install with: pip install mcp"
        )
    return Server(name)


def register_tool_dispatcher(server, tool_handlers: dict) -> None:
    """Register list_tools() and call_tool() decorators on the given server.

    Args:
        server: an MCP Server instance (from create_mcp_server)
        tool_handlers: dict mapping tool_name → async handler (name, arguments) -> list[TextContent]
    """
    from mcp.server.models import InitializationOptions  # type: ignore[import-not-found]
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]
    from mcp.types import Tool, TextContent  # type: ignore[import-not-found]

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        # Lazy import: TOOLS is defined in each server.py after handlers
        return getattr(server, "_TOOLS", [])

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = tool_handlers.get(name)
        if not handler:
            return error_response(f"Unknown tool: {name}", name)
        try:
            return await handler(arguments)
        except Exception as exc:
            return error_response(
                f"{type(exc).__name__}: {exc}",
                tool_name=name,
                hint="Check server logs for traceback",
            )


def check_optional_dep(module_name: str, install_cmd: str) -> tuple[bool, Any]:
    """Check if an optional dependency is available.

    Returns (is_available, module_or_none).
    Use this in server.py to gracefully degrade when optional libs are missing.
    """
    try:
        mod = __import__(module_name)
        return True, mod
    except ImportError:
        return False, None


def main_starter(
    server_name: str,
    version: str = "1.0.0",
    capabilities: Optional[dict] = None,
) -> Callable:
    """Decorator factory for the standard MCP server main() entrypoint.

    Returns a decorator that turns a setup function into a runnable async main().

    Usage:
        @main_starter("user-myserver", version="1.0.0")
        async def setup():
            print("user-myserver ready", flush=True)
    """
    from mcp.server.models import InitializationOptions  # type: ignore[import-not-found]
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]

    def decorator(setup_fn: Callable) -> Callable:
        async def wrapper():
            print(f"{server_name} MCP Server starting...", flush=True)
            try:
                await setup_fn()
            except Exception as exc:
                print(f"[{server_name}] setup failed: {exc}", flush=True)
            async with stdio_server() as (read_stream, write_stream):
                # Server reference is captured via closure on the global server var
                from mcp.server import Server  # type: ignore[import-not-found]
                srv: Server = Server(server_name)
                await srv.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name=server_name,
                        server_version=version,
                        capabilities=srv.get_capabilities(
                            notification_options=None,
                            experimental_capabilities=capabilities or {},
                        ),
                    ),
                )
        return wrapper

    return decorator
