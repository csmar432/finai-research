"""MCP Tool Client — 通用 MCP 协议客户端（占位 stub）。

P0 修复 2026-06-28: 此模块之前在 event_monitor.py 中被 try-import 但不存在，
导致 _call_mcp 直接走 subprocess fallback（隐藏能力缺失）。

T10 修复 2026-07-12: 调用付费 MCP（tushare/csmar/wind/cnki/wanfang 等）时,
如果对应 API Key 未配置，自动打印 🟡 非阻塞警告 + 引导用户配置.
- 警告只打印 1 次 (进程内去重)
- 不抛异常，不阻断 (用户按需配置)
- 可用 FINAI_SUPPRESS_PAID_WARNINGS=1 全局关闭

本模块提供:
- MCPToolClient 类，统一调用任意 MCP server/tool
- 自动选择通信方式：
  1. Python 进程内调用（如果 MCP 包已 import）
  2. subprocess 调用 mcp CLI（fallback）
  3. 返回 None 表示完全失败（与之前行为一致）
- 完整 NotImplementedError 提示用户升级到具体 MCP server 实现
"""
from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class MCPToolClient:
    """通用 MCP 工具调用客户端（占位 stub）。

    当前实现仅保留 subprocess fallback 路径，
    完整 Python 进程内 MCP 协议实现仍在研发中（v0.2）。
    """

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def call(self, server: str, tool: str, params: Optional[dict] = None) -> Optional[dict]:
        """调用 MCP 工具。

        Args:
            server: MCP 服务器标识（如 "user-tushare"）
            tool: 工具名（如 "get_daily_quote"）
            params: 工具参数字典

        Returns:
            解析后的 JSON 响应字典；调用失败时返回 None

        T10 fix (2026-07-12): paid-source warning is emitted here BEFORE
        the subprocess call, so users see the warning even if subprocess
        fails (which is the most common failure mode for paid MCPs whose
        key is missing). The warning is non-blocking — execution continues.
        """
        params = params or {}
        # ── T10: paid-source proactive warning (non-blocking) ────────────
        try:
            from scripts.core.paid_source_notifier import paid_notifier
            paid_notifier.warn_if_paid(
                server, tool,
                reason=f"调用 {server}/{tool} 时 API Key 未配置, 将由 fallback 链接管",
            )
        except Exception:
            # Notifier failures must never break MCP calls
            pass

        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": f"{server}/{tool}",
            "params": params,
            "id": 1,
        }).encode()

        try:
            proc = subprocess.run(
                ["mcp", "call", server, tool],
                input=payload,
                capture_output=True,
                timeout=self.timeout,
            )
            if proc.returncode == 0 and proc.stdout:
                return json.loads(proc.stdout.decode())
            logger.warning(
                "MCP call %s/%s returned %s: %s",
                server, tool, proc.returncode, proc.stderr.decode()[:200],
            )
            return None
        except FileNotFoundError:
            logger.warning("MCP CLI not installed (pip install mcp)")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("MCP call %s/%s timed out after %ss", server, tool, self.timeout)
            return None
        except Exception as exc:
            logger.warning("MCP call %s/%s failed: %s", server, tool, exc)
            return None


__all__ = ["MCPToolClient"]
