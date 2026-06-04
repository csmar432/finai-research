#!/usr/bin/env python3
"""
user-tushare MCP Server
=======================
A股数据（Tushare Pro），覆盖：行情/财务/融资融券/北向/指数/概念股。

Usage:
    python server.py

环境变量：
    TUSHARE_TOKEN — Tushare Pro API Token（必需）
    获取地址：https://tushare.pro/register
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

# ── 路径设置 ────────────────────────────────────────────────────────────────
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

# ── 依赖检查 ───────────────────────────────────────────────────────────────
try:
    import tushare as ts
except ImportError:
    print("ERROR: tushare is required. Install with: pip install tushare", flush=True)
    sys.exit(1)

# ── MCP Server 框架 ────────────────────────────────────────────────────────
try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package is required. Install with: pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-tushare")

# ── Tushare Pro 实例 ──────────────────────────────────────────────────────

_ts_pro: Optional[object] = None


def get_ts_pro():
    global _ts_pro
    if _ts_pro is not None:
        return _ts_pro

    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_KEY", "")
    if not token:
        raise ValueError(
            "TUSHARE_TOKEN environment variable is not set.\n"
            "Get your free token at https://tushare.pro/register"
        )
    _ts_pro = ts.pro_api(token)
    return _ts_pro


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_stock_basic",
        description="获取A股股票基础信息列表，包括代码、名称、上市日期、行业等。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "exchange": {
                    "type": "string",
                    "description": "交易所代码",
                    "enum": ["", "SSE", "SZSE", "BSE"]
                },
                "list_status": {
                    "type": "string",
                    "description": "上市状态，L上市 D退市 P暂停",
                    "enum": ["L", "D", "P"],
                    "default": "L"
                }
            }
        }
    ),
    Tool(
        name="get_daily_quote",
        description="获取A股日线行情数据（开盘/收盘/最高/最低/成交量/成交额）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "股票代码，如 000001.SZ"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期 YYYYMMDD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期 YYYYMMDD"
                },
                "trade_date": {
                    "type": "string",
                    "description": "指定交易日 YYYYMMDD"
                }
            },
            "required": ["ts_code"]
        }
    ),
    Tool(
        name="get_financial_report",
        description="获取A股财务数据（利润表/资产负债表/现金流量表/财务指标）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "股票代码"
                },
                "report_type": {
                    "type": "string",
                    "description": "报表类型",
                    "enum": ["income", "balance", "cashflow", "fina_indicator"]
                },
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
                "period": {"type": "string", "description": "报告期 YYYYMMDD，如 20231231"}
            },
            "required": ["ts_code", "report_type"]
        }
    ),
    Tool(
        name="get_margin_data",
        description="获取融资融券数据（融资余额/融资买入额/融券余额/北向资金）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "description": "数据类型",
                    "enum": ["margin", "margin_detail", "hsgt"]
                },
                "ts_code": {"type": "string", "description": "股票代码（margin_detail 时需要）"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
                "trade_date": {"type": "string", "description": "指定交易日 YYYYMMDD"}
            },
            "required": ["data_type"]
        }
    ),
    Tool(
        name="get_index_data",
        description="获取A股指数数据（日线行情/基础信息）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "指数代码，如 000001.SH（上证指数）"
                },
                "trade_date": {"type": "string", "description": "交易日期 YYYYMMDD"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
                "data_type": {
                    "type": "string",
                    "description": "数据类型",
                    "enum": ["daily", "basic"],
                    "default": "daily"
                }
            }
        }
    ),
    Tool(
        name="get_concept_stocks",
        description="获取概念股板块信息（概念列表/成分股）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "concept_name": {"type": "string", "description": "概念名称"},
                "ts_code": {"type": "string", "description": "股票代码"}
            }
        }
    ),
    Tool(
        name="get_trade_calendar",
        description="获取A股交易日历。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "exchange": {
                    "type": "string",
                    "description": "交易所",
                    "enum": ["SSE", "SZSE"]
                },
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
                "is_open": {
                    "type": "string",
                    "description": "是否交易",
                    "enum": ["0", "1"]
                }
            }
        }
    ),
]


# ── 数据处理 ───────────────────────────────────────────────────────────────

def _safe_json_response(data: Any, tool_name: str = "") -> str:
    """Standardized response format for all MCP tools.
    - Success: {"result": <data>, "success": True}
    - Error:   {"error": <message>, "success": False}
    """
    if isinstance(data, dict) and "error" in data:
        return json.dumps({"error": data["error"], "success": False, "tool": tool_name}, ensure_ascii=False)
    if isinstance(data, dict) and "result" in data:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps({"result": data, "success": True, "tool": tool_name}, ensure_ascii=False)


def _df_to_json(df) -> str:
    """Convert DataFrame to JSON string with standardized success wrapper."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"result": {"data": [], "count": 0}, "success": True}, ensure_ascii=False)
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
    except Exception as e:
        return _safe_json_response({"error": str(e)}, "unknown")
    return _safe_json_response(result, "unknown")


def _safe_call(pro, method_name: str, **kwargs) -> str:
    """Safe Tushare Pro API call with consistent error response."""
    method = getattr(pro, method_name, None)
    if not method:
        return _safe_json_response({"error": f"Tushare has no method: {method_name}"}, method_name)
    try:
        df = method(**{k: v for k, v in kwargs.items() if v is not None and v != ""})
        return _df_to_json(df)
    except Exception as e:
        return _safe_json_response({"error": str(e)}, method_name)


# ── 工具处理函数 ───────────────────────────────────────────────────────────

async def handle_get_stock_basic(args: dict) -> list[TextContent]:
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_stock_basic"))]
    result = _safe_call(pro, "stock_basic",
                         exchange=args.get("exchange"),
                         list_status=args.get("list_status", "L"))
    return [TextContent(type="text", text=result)]


async def handle_get_daily_quote(args: dict) -> list[TextContent]:
    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response({"error": "ts_code is required"}, "get_daily_quote"))]
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_daily_quote"))]
    if args.get("trade_date"):
        result = _safe_call(pro, "daily", ts_code=ts_code,
                             trade_date=args["trade_date"])
    else:
        result = _safe_call(pro, "daily", ts_code=ts_code,
                             start_date=args.get("start_date"),
                             end_date=args.get("end_date"))
    return [TextContent(type="text", text=result)]


async def handle_get_financial_report(args: dict) -> list[TextContent]:
    ts_code = args.get("ts_code", "")
    report_type = args.get("report_type", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response({"error": "ts_code is required"}, "get_financial_report"))]
    if not report_type:
        return [TextContent(type="text", text=_safe_json_response({"error": "report_type is required"}, "get_financial_report"))]
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_financial_report"))]
    method_map = {
        "income": "income",
        "balance": "balancesheet",
        "cashflow": "cashflow",
        "fina_indicator": "fina_indicator",
    }
    method_name = method_map.get(report_type, report_type)
    result = _safe_call(pro, method_name,
                         ts_code=ts_code,
                         start_date=args.get("start_date"),
                         end_date=args.get("end_date"),
                         period=args.get("period"))
    return [TextContent(type="text", text=result)]


async def handle_get_margin_data(args: dict) -> list[TextContent]:
    data_type = args.get("data_type", "")
    if not data_type:
        return [TextContent(type="text", text=_safe_json_response({"error": "data_type is required"}, "get_margin_data"))]
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_margin_data"))]
    method_map = {
        "margin": "margin",
        "margin_detail": "margin_detail",
        "hsgt": "moneyflow_hsgt",
    }
    method_name = method_map.get(data_type, data_type)
    result = _safe_call(pro, method_name,
                         ts_code=args.get("ts_code"),
                         trade_date=args.get("trade_date"),
                         start_date=args.get("start_date"),
                         end_date=args.get("end_date"))
    return [TextContent(type="text", text=result)]


async def handle_get_index_data(args: dict) -> list[TextContent]:
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_index_data"))]
    data_type = args.get("data_type", "daily")
    if data_type == "basic":
        result = _safe_call(pro, "index_basic", ts_code=args.get("ts_code"))
    else:
        if args.get("trade_date"):
            result = _safe_call(pro, "index_daily", ts_code=args["ts_code"],
                                 trade_date=args["trade_date"])
        else:
            result = _safe_call(pro, "index_daily", ts_code=args["ts_code"],
                                 start_date=args.get("start_date"),
                                 end_date=args.get("end_date"))
    return [TextContent(type="text", text=result)]


async def handle_get_concept_stocks(args: dict) -> list[TextContent]:
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_concept_stocks"))]
    try:
        if args.get("ts_code"):
            result = _safe_call(pro, "concept_detail", ts_code=args["ts_code"])
        elif args.get("concept_name"):
            df_concept = pro.concept()
            match = df_concept[df_concept["name"].str.contains(args["concept_name"], na=False)]
            if match.empty:
                return [TextContent(type="text", text=_safe_json_response(
                    {"error": f"概念 '{args['concept_name']}' 未找到"}, "get_concept_stocks"))]
            concept_id = match.iloc[0]["id"]
            result = _safe_call(pro, "concept_detail", id=concept_id)
        else:
            result = _safe_call(pro, "concept")
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_concept_stocks"))]


async def handle_get_trade_calendar(args: dict) -> list[TextContent]:
    try:
        pro = get_ts_pro()
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_trade_calendar"))]
    result = _safe_call(pro, "trade_cal",
                         exchange=args.get("exchange"),
                         start_date=args.get("start_date"),
                         end_date=args.get("end_date"),
                         is_open=args.get("is_open"))
    return [TextContent(type="text", text=result)]


TOOL_HANDLERS = {
    "get_stock_basic": handle_get_stock_basic,
    "get_daily_quote": handle_get_daily_quote,
    "get_financial_report": handle_get_financial_report,
    "get_margin_data": handle_get_margin_data,
    "get_index_data": handle_get_index_data,
    "get_concept_stocks": handle_get_concept_stocks,
    "get_trade_calendar": handle_get_trade_calendar,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown tool: {name}"}, name))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, name))]


async def main():
    print("user-tushare MCP Server starting...", flush=True)

    try:
        get_ts_pro()
        print("Tushare Pro connected successfully", flush=True)
    except ValueError as e:
        print(f"Warning: {e}", flush=True)
        print("   The server will start but tools will return errors until TUSHARE_TOKEN is set.", flush=True)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="user-tushare",
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
