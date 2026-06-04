#!/usr/bin/env python3
"""
user-eastmoney-reports MCP Server
=================================
东方财富研报与数据 — 研报/新闻/概念板块/行业板块/分析师排名。
使用 akshare 实现，无需 API Key。

Usage:
    python server.py
"""

from __future__ import annotations

import json, os, sys, warnings
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
    import akshare as ak
except ImportError:
    print("ERROR: akshare required. pip install akshare", flush=True)
    sys.exit(1)

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-eastmoney-reports")

TOOLS = [
    Tool(
        name="get_research_report",
        description="获取券商研报数据（个股研报列表）。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "股票代码，如 000001.SZ（默认 000001.SZ）",
                    "default": "000001.SZ",
                },
            }
        }
    ),
    Tool(
        name="get_stock_news",
        description="获取个股新闻/公告。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "股票代码"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
                "max_results": {"type": "integer", "default": 20}
            }
        }
    ),
    Tool(
        name="get_board_concept",
        description="获取概念板块数据（板块列表/行情/历史走势）。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "description": "数据类型",
                    "enum": ["names", "spot", "hist"]
                },
                "concept_name": {"type": "string", "description": "概念名称（hist时需要）"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            }
        }
    ),
    Tool(
        name="get_board_industry",
        description="获取行业板块数据（行业列表/行情/历史走势）。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "description": "数据类型",
                    "enum": ["names", "spot", "hist"]
                },
                "industry_name": {"type": "string", "description": "行业名称（hist时需要）"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            }
        }
    ),
    Tool(
        name="get_analyst_rank",
        description="获取券商分析师排名。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份"}
            }
        }
    ),
]


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


async def handle_research_report(args: dict) -> list[TextContent]:
    try:
        df = ak.stock_research_report_em(
            symbol=args.get("ts_code", "000001.SZ"),
        )
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_research_report"))]


async def handle_stock_news(args: dict) -> list[TextContent]:
    try:
        df = ak.stock_news_em(symbol=args.get("ts_code", ""))
        # Apply date filtering if provided (akshare stock_news_em doesn't support it natively)
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        if start_date and "datetime" in df.columns:
            df = df[df["datetime"] >= str(start_date)]
        if end_date and "datetime" in df.columns:
            df = df[df["datetime"] <= str(end_date)]
        df = df.head(args.get("max_results", 20))
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_stock_news"))]


async def handle_board_concept(args: dict) -> list[TextContent]:
    data_type = args.get("data_type", "names")
    try:
        if data_type == "names":
            df = ak.stock_board_concept_name_em()
        elif data_type == "spot":
            df = ak.stock_board_concept_spot_em()
        elif data_type == "hist":
            name = args.get("concept_name", "")
            if not name:
                return [TextContent(type="text", text=_safe_json_response({"error": "concept_name required for hist"}, "get_board_concept"))]
            names_df = ak.stock_board_concept_name_em()
            match = names_df[names_df["板块名称"].str.contains(name, na=False)]
            if match.empty:
                return [TextContent(type="text", text=_safe_json_response({"error": f"概念 '{name}' 未找到"}, "get_board_concept"))]
            code = match.iloc[0]["板块代码"]
            df = ak.stock_board_concept_hist_em(symbol=code,
                                                 start_date=args.get("start_date"),
                                                 end_date=args.get("end_date"))
        else:
            return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown data_type: {data_type}"}, "get_board_concept"))]
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_board_concept"))]


async def handle_board_industry(args: dict) -> list[TextContent]:
    data_type = args.get("data_type", "names")
    try:
        if data_type == "names":
            df = ak.stock_board_industry_name_em()
        elif data_type == "spot":
            df = ak.stock_board_industry_spot_em()
        elif data_type == "hist":
            name = args.get("industry_name", "")
            if not name:
                return [TextContent(type="text", text=_safe_json_response({"error": "industry_name required for hist"}, "get_board_industry"))]
            names_df = ak.stock_board_industry_name_em()
            match = names_df[names_df["板块名称"].str.contains(name, na=False)]
            if match.empty:
                return [TextContent(type="text", text=_safe_json_response({"error": f"行业 '{name}' 未找到"}, "get_board_industry"))]
            code = match.iloc[0]["板块代码"]
            df = ak.stock_board_industry_hist_em(symbol=code,
                                                  start_date=args.get("start_date"),
                                                  end_date=args.get("end_date"))
        else:
            return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown data_type: {data_type}"}, "get_board_industry"))]
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_board_industry"))]


async def handle_analyst_rank(args: dict) -> list[TextContent]:
    try:
        df = ak.stock_analyst_rank_em(year=args.get("year", 2024))
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_analyst_rank"))]


TOOL_HANDLERS = {
    "get_research_report": handle_research_report,
    "get_stock_news": handle_stock_news,
    "get_board_concept": handle_board_concept,
    "get_board_industry": handle_board_industry,
    "get_analyst_rank": handle_analyst_rank,
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
    print(f"user-eastmoney-reports MCP Server starting... (akshare {ak.__version__})", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-eastmoney-reports",
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
