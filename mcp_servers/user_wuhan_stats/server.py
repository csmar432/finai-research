#!/usr/bin/env python3
"""user-wuhan-stats MCP Server — 武汉统计年鉴数据。

数据源：
  - 武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/
  - 武汉市统计局官网: http://tjj.wuhan.gov.cn/
  - akshare（部分全国数据可参考）

注意：武汉统计年鉴PDF需要解析，目前通过已知数据+数据源指引提供。

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

try:
    import akshare as ak
except ImportError:
    print("ERROR: akshare required. pip install akshare", flush=True)
    sys.exit(1)

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions

server = Server("user-wuhan-stats")


def _error_json(msg: str) -> str:
    return json.dumps({"error": msg, "success": False}, ensure_ascii=False)


def _ok_json(data: dict) -> str:
    return json.dumps({"result": data, "success": True}, ensure_ascii=False)


# ─── 工具处理函数 ───────────────────────────────────────────

async def handle_wuhan_gdp(args: dict) -> list[TextContent]:
    """武汉GDP数据（已知数据+数据源）。"""
    data = {
        "note": "武汉GDP精确数据需从《武汉统计年鉴》获取",
        "数据来源": [
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/",
            "武汉市统计局: http://tjj.wuhan.gov.cn/",
            "武汉统计年鉴（国家统计局镜像）: https://data.stats.gov.cn/"
        ],
        "已知数据": [
            {"year": 2024, "value": 21106.23, "unit": "亿元", "source": "武汉市统计局", "note": "全国城市第9"},
            {"year": 2023, "value": 20011.65, "unit": "亿元", "source": "武汉市统计局", "note": "全国城市第8"},
            {"year": 2022, "value": 18866.43, "unit": "亿元", "source": "武汉市统计局"},
            {"year": 2021, "value": 17716.96, "unit": "亿元", "source": "武汉市统计局"},
            {"year": 2020, "value": 15616.06, "unit": "亿元", "source": "武汉市统计局"},
            {"year": 2019, "value": 16223.21, "unit": "亿元", "source": "武汉市统计局"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_wuhan_industry(args: dict) -> list[TextContent]:
    """武汉工业数据（已知数据+数据源）。"""
    data = {
        "note": "武汉工业精确数据需从《武汉统计年鉴》获取",
        "数据来源": [
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/",
            "武汉市经信局: http://jxw.wuhan.gov.cn/"
        ],
        "已知数据": [
            {"year": 2024, "indicator": "规模以上工业增加值增速", "value": 7.5, "unit": "%", "source": "武汉市统计局"},
            {"year": 2024, "indicator": "高技术制造业增加值", "value": 22.7, "unit": "%", "source": "武汉市统计局", "note": "对工业增长贡献率35.1%"},
            {"year": 2023, "indicator": "规模以上工业增加值增速", "value": 4.6, "unit": "%", "source": "武汉市统计局"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_wuhan_investment(args: dict) -> list[TextContent]:
    """武汉固定资产投资数据。"""
    data = {
        "note": "武汉固定资产投资数据需从《武汉统计年鉴》获取",
        "数据来源": [
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/",
            "武汉市发改委: http://fgw.wuhan.gov.cn/"
        ],
        "已知数据": [
            {"year": 2024, "indicator": "固定资产投资增速", "value": 5.0, "unit": "%", "source": "武汉市统计局"},
            {"year": 2023, "indicator": "固定资产投资增速", "value": -3.9, "unit": "%", "source": "武汉市统计局"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_wuhan_trade(args: dict) -> list[TextContent]:
    """武汉进出口贸易数据。"""
    data = {
        "note": "武汉进出口数据需从《武汉统计年鉴》或海关总署获取",
        "数据来源": [
            "武汉海关: http://wuhan.customs.gov.cn/",
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/"
        ],
        "已知数据": [
            {"year": 2024, "indicator": "进出口总额", "value": 3532.1, "unit": "亿元", "source": "武汉海关", "note": "同比+6.4%"},
            {"year": 2024, "indicator": "出口额", "value": 2193.4, "unit": "亿元", "source": "武汉海关"},
            {"year": 2024, "indicator": "进口额", "value": 1338.7, "unit": "亿元", "source": "武汉海关"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_wuhan_education(args: dict) -> list[TextContent]:
    """武汉高校教育数据。"""
    data = {
        "note": "武汉高校精确数据需从《武汉统计年鉴》获取",
        "数据来源": [
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/",
            "武汉市教育局: http://jyj.wuhan.gov.cn/"
        ],
        "已知数据": [
            {"year": 2024, "indicator": "普通高校数量", "value": 92, "unit": "所", "source": "武汉市统计局"},
            {"year": 2024, "indicator": "在校大学生数量", "value": 133.3, "unit": "万人", "source": "武汉市统计局"},
            {"year": 2024, "indicator": "武汉在校大学生", "value": 133.3, "unit": "万人", "source": "武汉市统计局", "note": "全国第一"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_wuhan_tech(args: dict) -> list[TextContent]:
    """武汉科技创新数据。"""
    data = {
        "note": "武汉科技创新数据需从《武汉统计年鉴》或武汉市科技局获取",
        "数据来源": [
            "武汉科创局: http://kjj.wuhan.gov.cn/",
            "武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/tjnj/"
        ],
        "已知数据": [
            {"year": 2024, "indicator": "技术合同成交额", "value": 1200, "unit": "亿元", "source": "武汉市科技局", "note": "估算值，需核实"},
            {"year": 2024, "indicator": "高新技术企业数量", "value": 13000, "unit": "家", "source": "武汉市科技局", "note": "中部第一"},
            {"year": 2025, "indicator": "光谷总算力", "value": 4700, "unit": "P+", "source": "数据汇", "note": "中部第一"},
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


# ─── 工具定义 ─────────────────────────────────────────────

TOOLS = [
    Tool(name="get_wuhan_gdp", description="武汉GDP历年数据（含已知数据和统计年鉴来源）",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_wuhan_industry", description="武汉规模以上工业数据（含已知数据）",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_wuhan_investment", description="武汉固定资产投资数据",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_wuhan_trade", description="武汉进出口贸易数据",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_wuhan_education", description="武汉高校教育数据",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_wuhan_tech", description="武汉科技创新数据",
         inputSchema={"type": "object", "properties": {}}),
]

TOOL_HANDLERS = {
    "get_wuhan_gdp": handle_wuhan_gdp,
    "get_wuhan_industry": handle_wuhan_industry,
    "get_wuhan_investment": handle_wuhan_investment,
    "get_wuhan_trade": handle_wuhan_trade,
    "get_wuhan_education": handle_wuhan_education,
    "get_wuhan_tech": handle_wuhan_tech,
}

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=_error_json(f"Unknown tool: {name}"))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-wuhan-stats",
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
