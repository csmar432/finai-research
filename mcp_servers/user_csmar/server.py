#!/usr/bin/env python3
"""
user-csmar MCP Server
=====================
CSMAR国泰安金融数据库风格。

注意：CSMAR需要机构账号，本服务器提供模拟数据用于演示。

数据源：
  - 模拟数据（实际CSMAR需机构账号）

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

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-csmar")


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_csmar_financial",
        description="获取CSMAR财务报表数据。\n\n"
                    "返回A股上市公司财务报表（利润表、资产负债表、现金流量表）。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "股票代码，如 000001.SZ"},
                "report_type": {"type": "string", "description": "报告类型: income/balance/cash_flow", "default": "income"},
                "year": {"type": "integer", "description": "年份，如 2024"}
            },
            "required": ["ts_code"]
        }
    ),
    Tool(
        name="get_csmar_corporate",
        description="获取CSMAR公司治理数据。\n\n"
                    "返回股权结构、董事会信息、高管薪酬等。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "股票代码"},
                "info_type": {"type": "string", "description": "信息类型: ownership/board/compensation", "default": "ownership"}
            },
            "required": ["ts_code"]
        }
    ),
    Tool(
        name="get_csmar_trading",
        description="获取CSMAR交易数据。\n\n"
                    "返回个股日频交易数据（开盘价、收盘价、成交量等）。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "股票代码"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            },
            "required": ["ts_code"]
        }
    ),
    Tool(
        name="get_csmar_analyst",
        description="获取CSMAR分析师数据。\n\n"
                    "返回分析师预测数据、评级信息、盈利预测等。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "股票代码"},
                "analyst_name": {"type": "string", "description": "分析师姓名（可选）"}
            },
            "required": []
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_financial(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_financial", "user-csmar")
    if check is not None:
        return check


    ts_code = args.get("ts_code", "")
    report_type = args.get("report_type", "income")
    year = args.get("year", 2024)
    
    if not ts_code:
        return [TextContent(type="text", text=json.dumps({"error": "ts_code is required"}))]
    
    try:
        if report_type == "income":
            result = {
                "ts_code": ts_code,
                "report_type": "income_statement",
                "year": year,
                "data": [
                    {"item": "营业收入", "amount": 35000000000, "yoy": 12.5},
                    {"item": "营业成本", "amount": 25000000000, "yoy": 10.2},
                    {"item": "营业利润", "amount": 8500000000, "yoy": 18.5},
                    {"item": "净利润", "amount": 6800000000, "yoy": 15.8},
                    {"item": "归母净利润", "amount": 6200000000, "yoy": 16.2},
                    {"item": "基本每股收益", "amount": 1.85, "yoy": 14.5},
                ]
            }
        elif report_type == "balance":
            result = {
                "ts_code": ts_code,
                "report_type": "balance_sheet",
                "year": year,
                "data": [
                    {"item": "总资产", "amount": 280000000000, "yoy": 8.5},
                    {"item": "总负债", "amount": 150000000000, "yoy": 6.2},
                    {"item": "所有者权益", "amount": 130000000000, "yoy": 11.5},
                    {"item": "流动资产", "amount": 180000000000, "yoy": 9.8},
                    {"item": "非流动资产", "amount": 100000000000, "yoy": 6.5},
                    {"item": "资产负债率", "amount": 53.57, "unit": "%"},
                ]
            }
        else:
            result = {
                "ts_code": ts_code,
                "report_type": "cash_flow",
                "year": year,
                "data": [
                    {"item": "经营活动现金流", "amount": 12000000000, "yoy": 25.6},
                    {"item": "投资活动现金流", "amount": -5000000000, "yoy": -15.2},
                    {"item": "筹资活动现金流", "amount": -3000000000, "yoy": 8.5},
                    {"item": "期末现金", "amount": 45000000000, "yoy": 18.5},
                ]
            }
        result["note"] = "CSMAR财务报表数据，金额单位：元"
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_corporate(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_corporate", "user-csmar")
    if check is not None:
        return check


    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=json.dumps({"error": "ts_code is required"}))]
    
    try:
        info_type = args.get("info_type", "ownership")
        if info_type == "ownership":
            result = {
                "ts_code": ts_code,
                "info_type": "ownership_structure",
                "data": [
                    {"holder": "国家资本", "shares": 6500000000, "ratio": 35.5},
                    {"holder": "境内法人", "shares": 4200000000, "ratio": 22.9},
                    {"holder": "境内自然人", "shares": 3800000000, "ratio": 20.7},
                    {"holder": "外资", "shares": 2500000000, "ratio": 13.6},
                    {"holder": "其他", "shares": 1330000000, "ratio": 7.3},
                ]
            }
        elif info_type == "board":
            result = {
                "ts_code": ts_code,
                "info_type": "board_info",
                "data": {
                    "board_size": 11,
                    "independent_ratio": 36.4,
                    "executives": [
                        {"name": "张三", "position": "董事长", "tenure": 8},
                        {"name": "李四", "position": "总经理", "tenure": 6},
                        {"name": "王五", "position": "财务总监", "tenure": 5},
                    ]
                }
            }
        else:
            result = {
                "ts_code": ts_code,
                "info_type": "compensation",
                "data": {
                    "top_management_total": 25000000,
                    "avg_compensation": 3500000,
                    "equity_incentive": 5800000,
                }
            }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_trading(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_trading", "user-csmar")
    if check is not None:
        return check


    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=json.dumps({"error": "ts_code is required"}))]
    
    try:
        result = {
            "ts_code": ts_code,
            "data": [
                {"date": "2024-01-02", "open": 12.35, "high": 12.68, "low": 12.28, "close": 12.56, "volume": 85620000, "amount": 1075000000},
                {"date": "2024-01-03", "open": 12.58, "high": 12.75, "low": 12.45, "close": 12.62, "volume": 78450000, "amount": 991500000},
                {"date": "2024-01-04", "open": 12.60, "high": 12.88, "low": 12.55, "close": 12.85, "volume": 92560000, "amount": 1185600000},
                {"date": "2024-01-05", "open": 12.82, "high": 12.95, "low": 12.68, "close": 12.72, "volume": 68920000, "amount": 878500000},
                {"date": "2024-01-08", "open": 12.70, "high": 12.85, "low": 12.55, "close": 12.78, "volume": 75890000, "amount": 969200000},
            ],
            "note": "CSMAR日频交易数据，价格单位：元，成交量单位：股，金额单位：元"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_analyst(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_analyst", "user-csmar")
    if check is not None:
        return check


    ts_code = args.get("ts_code", "")
    analyst_name = args.get("analyst_name", "")
    
    try:
        result = {
            "ts_code": ts_code or "样本股票",
            "data": [
                {"analyst": "分析师A", "broker": "中金公司", "date": "2024-06-15", "rating": "买入", "target_price": 15.80, "eps_forecast": {"2024": 1.25, "2025": 1.45}},
                {"analyst": "分析师B", "broker": "国泰君安", "date": "2024-06-10", "rating": "增持", "target_price": 14.50, "eps_forecast": {"2024": 1.20, "2025": 1.38}},
                {"analyst": "分析师C", "broker": "中信证券", "date": "2024-06-05", "rating": "买入", "target_price": 16.20, "eps_forecast": {"2024": 1.28, "2025": 1.52}},
            ],
            "note": "CSMAR分析师预测数据"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "get_csmar_financial": handle_financial,
    "get_csmar_corporate": handle_corporate,
    "get_csmar_trading": handle_trading,
    "get_csmar_analyst": handle_analyst,
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
    print("user-csmar MCP Server starting... (demo data)", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-csmar",
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
