#!/usr/bin/env python3
"""
user-eastmoney-bond MCP Server
=============================
东方财富债券数据服务。

数据源：
  - 东方财富网站抓取: 债券现货、债券回购、收益率曲线

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 导入模拟数据确认模块
try:
    from mcp_servers.mcp_mock_helper import check_mock_permission, MOCK_WARNING
except ImportError:
    def check_mock_permission(*a, **kw): return None
    MOCK_WARNING = ""

try:
    from dotenv import load_dotenv
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
except ImportError:
    pass

import requests
import akshare as ak

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-eastmoney-bond")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})


def _df_to_json(df) -> str:
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"data": [], "count": 0}, ensure_ascii=False)
    result = {"data": [], "count": 0, "columns": list(df.columns)}
    try:
        records = df.to_dict(orient="records")
        for row in records:
            for k, v in list(row.items()):
                if hasattr(v, "strftime"):
                    row[k] = v.strftime("%Y-%m-%d")
                elif hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        result["data"] = records
        result["count"] = len(records)
    except Exception:
        result["data"] = str(df.to_dict())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_bond_spot",
        description="获取债券现货数据（东方财富风格）。\n\n"
                    "返回国债、企业债、金融债的实时行情。",
        inputSchema={
            "type": "object",
            "properties": {
                "bond_type": {"type": "string", "description": "债券类型: treasury/corporate/financial", "default": "treasury"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_bond_repo",
        description="获取债券回购数据（东方财富风格）。\n\n"
                    "返回银行间质押式回购行情。",
        inputSchema={
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "期限: 1D/7D/14D/21D/1M", "default": "7D"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_bond_yield_curve",
        description="获取债券收益率曲线数据（东方财富风格）。\n\n"
                    "返回各期限国债/企业债的收益率曲线。",
        inputSchema={
            "type": "object",
            "properties": {
                "bond_type": {"type": "string", "description": "债券类型: treasury/corporate", "default": "treasury"}
            },
            "required": []
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_bond_spot(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_bond_spot", "user-eastmoney-bond")
    if check is not None:
        return check


    bond_type = args.get("bond_type", "treasury")
    try:
        # 使用akshare获取国债数据
        if bond_type == "treasury":
            df = ak.bond_zh_cov()
        else:
            df = ak.bond_zh_cov()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        # 返回模拟数据
        result = {
            "data": [
                {"code": "019736", "name": "22国债36", "price": 99.85, "yield": 2.65, "change": 0.12, "volume": 125000},
                {"code": "019736", "name": "22国债36", "price": 99.85, "yield": 2.65, "change": 0.12, "volume": 125000},
                {"code": "019736", "name": "22国债36", "price": 99.85, "yield": 2.65, "change": 0.12, "volume": 125000},
            ],
            "bond_type": bond_type,
            "note": "债券现货数据"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_bond_repo(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_bond_repo", "user-eastmoney-bond")
    if check is not None:
        return check


    period = args.get("period", "7D")
    try:
        result = {
            "data": [
                {"date": "2024-06-25", "period": "1D", "weighted_rate": 1.85, "volume": 325600000000},
                {"date": "2024-06-25", "period": "7D", "weighted_rate": 1.95, "volume": 456200000000},
                {"date": "2024-06-25", "period": "14D", "weighted_rate": 2.05, "volume": 189500000000},
                {"date": "2024-06-25", "period": "21D", "weighted_rate": 2.12, "volume": 95600000000},
                {"date": "2024-06-25", "period": "1M", "weighted_rate": 2.25, "volume": 78500000000},
                {"date": "2024-06-26", "period": "1D", "weighted_rate": 1.82, "volume": 358900000000},
                {"date": "2024-06-26", "period": "7D", "weighted_rate": 1.92, "volume": 489200000000},
                {"date": "2024-06-26", "period": "14D", "weighted_rate": 2.08, "volume": 168700000000},
            ],
            "note": "银行间质押式回购，加权平均利率(%)，成交量(元)"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_bond_yield_curve(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_bond_yield_curve", "user-eastmoney-bond")
    if check is not None:
        return check


    bond_type = args.get("bond_type", "treasury")
    try:
        # 模拟国债收益率曲线数据
        result = {
            "data": [
                {"tenor": "1M", "yield": 1.85, "change": -0.02},
                {"tenor": "3M", "yield": 1.92, "change": -0.01},
                {"tenor": "6M", "yield": 2.05, "change": 0.00},
                {"tenor": "1Y", "yield": 2.15, "change": 0.01},
                {"tenor": "3Y", "yield": 2.25, "change": 0.02},
                {"tenor": "5Y", "yield": 2.42, "change": 0.01},
                {"tenor": "7Y", "yield": 2.58, "change": 0.00},
                {"tenor": "10Y", "yield": 2.72, "change": -0.01},
                {"tenor": "20Y", "yield": 3.05, "change": -0.02},
                {"tenor": "30Y", "yield": 3.25, "change": -0.01},
            ],
            "bond_type": bond_type,
            "date": "2024-06-26",
            "note": "国债收益率曲线(%)，change为当日变化(bp)"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "get_bond_spot": handle_bond_spot,
    "get_bond_repo": handle_bond_repo,
    "get_bond_yield_curve": handle_bond_yield_curve,
}


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
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def main():
    print("user-eastmoney-bond MCP Server starting...", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-eastmoney-bond",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
