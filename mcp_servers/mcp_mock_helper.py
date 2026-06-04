#!/usr/bin/env python3
"""
MCP Mock 确认机制 — 统一工具
========================================
所有模拟/演示数据服务器统一引用此模块：
  1. 标识为模拟数据（_MOCK = True）
  2. 提供统一确认检查（check_mock_permission）
  3. 提供统一响应包装（mock_response）

用法：
    from mcp_mock_helper import MOCK_TOOLS, check_mock_permission

    # 在工具处理函数中：
    def handle_xxx(args):
        result = check_mock_permission(args, "tool_name")
        if result:  # 返回了确认提示，不需要继续
            return result
        # 继续执行业务逻辑...

    # 工具定义中加入：
    TOOLS = MOCK_TOOLS + [...]  # 自动带上警告描述
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────────────────

# 跳过确认的批准关键词（用户只要在请求中出现这些词，就认为是已授权）
APPROVAL_KEYWORDS = [
    "确认", "确认使用", "确认调用", "确认执行", "已授权",
    "confirm", "proceed", "ok", "yes", "y",
    "忽略", "跳过", "忽略警告", "忽略确认",
    "ignore", "skip", "force",
    "我知道", "我确认", "我同意",
]

# 模拟数据提示语（会注入到每个工具描述中）
MOCK_WARNING = (
    "\n\n[模拟数据警告] 此工具返回的是演示/模拟数据，非真实API数据。"
    " 数据不代表真实市场情况，如需真实数据请：\n"
    "  1. 配置相应的 API Key（如 FRED_API_KEY、CSMAR账号等）\n"
    "  2. 或使用同类无Key工具（如 user-financial）\n"
    "  3. 或使用 user-playwright-mcp 从网页直接抓取\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# 确认检查
# ─────────────────────────────────────────────────────────────────────────────

def check_mock_permission(
    args: dict,
    tool_name: str,
    server_name: str,
    request_context: Optional[str] = None,
) -> Optional[list]:
    """
    检查是否允许执行模拟数据工具。

    逻辑：
      1. 如果 MCP_MOCK_MODE=disabled → 拒绝，返回错误
      2. 如果 MCP_MOCK_MODE=allow → 直接通过
      3. 如果 MCP_MOCK_MODE=confirm（默认）→ 检查请求上下文是否含批准关键词
      4. 如果请求含批准关键词 → 通过
      5. 否则 → 返回确认提示，要求用户明确授权

    Args:
        args: 工具参数字典
        tool_name: 工具名
        server_name: 服务器名（用于错误消息）
        request_context: 可选，LLM请求中的上下文描述

    Returns:
        None → 检查通过，继续执行业务逻辑
        list[TextContent] → 检查未通过，返回确认提示/错误，调用方应直接返回
    """
    from mcp.types import TextContent

    mode = os.environ.get("MCP_MOCK_MODE", "confirm").lower()

    if mode == "disabled":
        return [TextContent(type="text", text=json.dumps({
            "error": f"[{server_name}] 模拟数据已被禁用（ MCP_MOCK_MODE=disabled）",
            "tool": tool_name,
            "status": "disabled",
            "suggestion": "请配置真实 API Key，或切换 MCP_MOCK_MODE=confirm",
            "data_source": "MOCK_DISABLED",
        }, ensure_ascii=False))]

    if mode == "allow":
        # 允许模式：直接通过，不做任何提示
        return None

    # confirm 模式（默认）
    # 检查请求上下文是否含批准关键词
    ctx = request_context or ""
    ctx_lower = ctx.lower()
    approved = any(kw in ctx_lower for kw in APPROVAL_KEYWORDS)

    if approved:
        return None  # 通过

    # 未通过，显示确认提示
    tool_display = f"{server_name}.{tool_name}"
    msg = (
        f"您正在调用模拟数据工具 [{tool_display}]，该工具返回的是演示数据，非真实数据。\n\n"
        f"调用将不消耗任何 API 配额，但结果仅供参考。\n\n"
        f"如需继续，请明确说：\n"
        f'  - "确认使用模拟数据" / "确认调用" / "确认"\n'
        f'  - "忽略警告" / "忽略确认"\n'
        f'  - "我知道，这是模拟数据"\n\n'
        f"如需真实数据，请：\n"
        f"  1. 配置对应 API Key（TUSHARE_TOKEN / FRED_API_KEY / EODHD_API_KEY 等）\n"
        f"  2. 或改用无Key工具（user-financial / user-enhanced-finance 等）\n"
        f"  3. 或用 user-playwright-mcp 从网页抓取\n"
    )
    return [TextContent(type="text", text=json.dumps({
        "status": "confirmation_required",
        "tool": tool_display,
        "message": msg,
        "args": {k: str(v)[:100] for k, v in args.items()},
        "data_source": "MOCK_CONFIRMATION_REQUIRED",
        "hint": "在 .env 中设置 MCP_MOCK_MODE=allow 跳过确认，或 MCP_MOCK_MODE=disabled 完全禁用",
    }, ensure_ascii=False, indent=2))]


# ─────────────────────────────────────────────────────────────────────────────
# 响应包装
# ─────────────────────────────────────────────────────────────────────────────

def mock_response(data: Any, tool_name: str, note: str = "") -> str:
    """
    将模拟数据包装为标准响应，并附加元数据。

    返回格式：
    {
        "result": <data>,
        "success": True,
        "tool": <tool_name>,
        "data_source": "MOCK",
        "mock_warning": <warning message>,
        "note": <note>
    }
    """
    result = {
        "result": data,
        "success": True,
        "tool": tool_name,
        "data_source": "MOCK",
        "note": note,
    }
    if note:
        result["mock_warning"] = (
            f"⚠️ 此数据来自模拟数据源 [{tool_name}]，非真实API数据。{note}"
        )
    return json.dumps(result, ensure_ascii=False, default=str)


def mock_error(message: str, tool_name: str, suggestion: str = "") -> str:
    """模拟数据错误响应。"""
    result = {
        "error": message,
        "tool": tool_name,
        "data_source": "MOCK",
        "status": "error",
    }
    if suggestion:
        result["suggestion"] = suggestion
    return json.dumps(result, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# 工具元数据增强（自动给工具描述添加警告）
# ─────────────────────────────────────────────────────────────────────────────

def enrich_tool_description(tool_desc: str) -> str:
    """给工具描述附加模拟数据警告。"""
    if MOCK_WARNING in tool_desc:
        return tool_desc  # 避免重复追加
    return tool_desc + MOCK_WARNING


# ─────────────────────────────────────────────────────────────────────────────
# 快速生成带确认的模拟工具处理器
# ─────────────────────────────────────────────────────────────────────────────

async def make_mock_handler(
    tool_name: str,
    server_name: str,
    data_provider,  # callable(args) -> data
    note: str = "",
):
    """
    快速创建一个带确认检查的模拟数据处理器。

    用法示例：
        async def my_data_provider(args):
            return {"key": "value"}

        handler = make_mock_handler(
            "get_xxx",
            "my-server",
            my_data_provider,
            note="数据来源于演示"
        )
        TOOL_HANDLERS["get_xxx"] = handler
    """
    from mcp.types import TextContent as TC

    async def handler(args: dict) -> list[TextContent]:
        check = check_mock_permission(args, tool_name, server_name)
        if check is not None:
            return check

        try:
            data = data_provider(args)
            return [TC(type="text", text=mock_response(data, tool_name, note))]
        except Exception as e:
            return [TC(type="text", text=mock_error(str(e), tool_name))]

    return handler


# ─────────────────────────────────────────────────────────────────────────────
# 服务器元信息（供 llm_gateway 等消费方使用）
# ─────────────────────────────────────────────────────────────────────────────

SERVER_INFO = {
    "type": "mock_data_server",
    "description": "模拟数据服务器，返回演示/示例数据",
    "requires_confirmation": True,
    "modes": {
        "disabled": "完全禁用，返回错误",
        "confirm": "（默认）调用前需用户确认",
        "allow": "直接放行，无需确认",
    },
    "env_var": "MCP_MOCK_MODE",
    "approval_keywords": APPROVAL_KEYWORDS,
}
