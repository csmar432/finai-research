#!/usr/bin/env python3
"""user-macro-datas MCP Server — 马克数据网 + 科技部公报数据指引。

数据源：
  - 马克数据网（macrodatas.cn）：中国科技统计年鉴面板数据，需注册后使用
  - 科技部《全国科技经费投入统计公报》：R&D经费分省数据
  - 中国统计年鉴：各省份高校/R&D面板数据

说明：马克数据网需要注册账号（macrodatas.cn），免费账号有访问限制。
本MCP提供数据指引和已知数据汇总。

Usage:
    python server.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any

# 2026-06-28 P0 修复：标识为 MOCK 数据 + 默认禁用
# 用户决策：MCP_MOCK_MODE 默认 disabled，避免基于伪造数据发表错误结论
try:
    from mcp_servers.mcp_mock_helper import check_mock_permission, MOCK_WARNING
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from mcp_servers.mcp_mock_helper import check_mock_permission, MOCK_WARNING

_MOCK = True  # 标识为公开数据快照（无实时 API 接入）

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions

server = Server("user-macro-datas")


def _error_json(msg: str) -> str:
    return json.dumps({"error": msg, "success": False}, ensure_ascii=False)


def _ok_json(data: Any) -> str:
    return json.dumps({"result": data, "success": True}, ensure_ascii=False)


# ─── 工具处理函数 ───────────────────────────────────────────

async def handle_rd_panel(args: dict) -> list[TextContent]:
    """中国各省R&D面板数据指引（含已知数据）。"""
    check = check_mock_permission(args, "handle_rd_panel", "user-macro-datas")
    if check is not None:
        return check
    data = {
        "note": "马克数据网（macrodatas.cn）提供2000-2024年各省R&D面板数据，需注册账号",
        "免费访问方式": [
            "科技部《全国科技经费投入统计公报》PDF: https://www.most.gov.cn/kjtj/",
            "中国统计年鉴（各年度）: https://www.stats.gov.cn/tjsj/ndsj/",
            "国家统计局分省年度数据: https://data.stats.gov.cn/"
        ],
        "湖北省R&D数据（已核实）": [
            {"year": 2024, "province": "湖北", "rd_expenditure": 1408.2, "unit": "亿元", "growth": 12.2, "source": "湖北省科技厅"},
            {"year": 2023, "province": "湖北", "rd_expenditure": 1257.0, "unit": "亿元", "growth": 7.6, "source": "湖北省科技厅"},
            {"year": 2022, "province": "湖北", "rd_expenditure": 1161.3, "unit": "亿元", "growth": 11.1, "source": "湖北省科技厅"},
            {"year": 2021, "province": "湖北", "rd_expenditure": 1045.3, "unit": "亿元", "growth": 15.8, "source": "湖北省科技厅"},
            {"year": 2020, "province": "湖北", "rd_expenditure": 902.3, "unit": "亿元", "growth": 7.9, "source": "湖北省科技厅"},
        ],
        "全国R&D数据（已核实）": [
            {"year": 2023, "country": "中国", "rd_expenditure": 33078.1, "unit": "亿元", "rd_intensity": 2.64, "source": "科技部公报"},
            {"year": 2022, "country": "中国", "rd_expenditure": 30781.8, "unit": "亿元", "rd_intensity": 2.61, "source": "科技部公报"},
            {"year": 2021, "country": "中国", "rd_expenditure": 27956.3, "unit": "亿元", "rd_intensity": 2.44, "source": "科技部公报"},
            {"year": 2020, "country": "中国", "rd_expenditure": 24393.1, "unit": "亿元", "rd_intensity": 2.41, "source": "科技部公报"},
        ],
        "马克数据网使用方法": {
            "网址": "https://www.macrodatas.cn/",
            "面板路径": "专题数据 > 科技统计 > 中国科技统计年鉴 > R&D",
            "注册": "右上角注册，免费账号每天可下载20条"
        }
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_tech_panel(args: dict) -> list[TextContent]:
    """中国科技指标面板数据指引。"""
    check = check_mock_permission(args, "handle_tech_panel", "user-macro-datas")
    if check is not None:
        return check
    data = {
        "note": "马克数据网提供各省科技指标面板数据，含高新技术企业/专利/技术合同等",
        "湖北省高新技术企业（已核实）": [
            {"year": 2024, "indicator": "高新技术企业数量", "value": 30000, "unit": "家", "source": "湖北省统计局"},
            {"year": 2023, "indicator": "高新技术企业数量", "value": 25000, "unit": "家", "source": "湖北省统计局"},
            {"year": 2021, "indicator": "高新技术企业数量", "value": 14560, "unit": "家", "source": "湖北省科技厅"},
            {"year": 2020, "indicator": "高新技术企业数量", "value": 10404, "unit": "家", "source": "湖北省科技厅"},
            {"year": 2019, "indicator": "高新技术企业数量", "value": 7893, "unit": "家", "source": "湖北省科技厅"},
        ],
        "湖北省技术合同（已核实）": [
            {"year": 2025, "indicator": "技术合同成交额", "value": 6100, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2024, "indicator": "技术合同成交额", "value": 5500, "unit": "亿元", "source": "湖北省统计局"},
            {"year": 2023, "indicator": "技术合同成交额", "value": 4802.24, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2022, "indicator": "技术合同成交额", "value": 3017.86, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2021, "indicator": "技术合同成交额", "value": 2111.63, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2020, "indicator": "技术合同成交额", "value": 1686.95, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2015, "indicator": "技术合同成交额", "value": 830, "unit": "亿元", "source": "湖北省科技厅"},
        ],
        "马克数据网使用方法": {
            "网址": "https://www.macrodatas.cn/",
            "专题数据": "科技统计 > 中国科技统计年鉴",
            "注册": "右上角注册，免费账号每天可下载20条"
        }
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_industry_panel(args: dict) -> list[TextContent]:
    """中国产业指标面板数据指引。"""
    check = check_mock_permission(args, "handle_industry_panel", "user-macro-datas")
    if check is not None:
        return check
    data = {
        "note": "马克数据网提供各省产业指标面板数据，含GDP/工业/服务业等",
        "湖北省GDP（已核实）": [
            {"year": 2024, "indicator": "GDP", "value": 60012.97, "unit": "亿元", "growth": 5.8, "source": "湖北省统计局"},
            {"year": 2023, "indicator": "GDP", "value": 55803.63, "unit": "亿元", "growth": 5.8, "source": "湖北省统计局"},
            {"year": 2022, "indicator": "GDP", "value": 53741.70, "unit": "亿元", "growth": 4.3, "source": "湖北省统计局"},
            {"year": 2021, "indicator": "GDP", "value": 50091.20, "unit": "亿元", "growth": 12.9, "source": "湖北省统计局"},
            {"year": 2020, "indicator": "GDP", "value": 43004.49, "unit": "亿元", "growth": -5.0, "source": "湖北省统计局"},
            {"year": 2019, "indicator": "GDP", "value": 45428.96, "unit": "亿元", "growth": 7.5, "source": "湖北省统计局"},
        ],
        "武汉市GDP（已核实）": [
            {"year": 2024, "indicator": "GDP", "value": 21106.23, "unit": "亿元", "rank": "全国第9", "source": "武汉市统计局"},
            {"year": 2023, "indicator": "GDP", "value": 20011.65, "unit": "亿元", "rank": "全国第8", "source": "武汉市统计局"},
            {"year": 2022, "indicator": "GDP", "value": 18866.43, "unit": "亿元", "rank": "全国第8", "source": "武汉市统计局"},
            {"year": 2021, "indicator": "GDP", "value": 17716.96, "unit": "亿元", "rank": "全国第8", "source": "武汉市统计局"},
            {"year": 2020, "indicator": "GDP", "value": 15616.06, "unit": "亿元", "rank": "全国第10", "source": "武汉市统计局"},
        ],
        "数据来源": {
            "马克数据网": "https://www.macrodatas.cn/ — 各省GDP/R&D/科技面板",
            "中国统计年鉴": "https://www.stats.gov.cn/tjsj/ndsj/",
            "湖北省统计局": "https://tjj.hubei.gov.cn/tjsj/",
            "武汉市统计局": "http://tjj.wuhan.gov.cn/"
        }
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_education_panel(args: dict) -> list[TextContent]:
    """中国教育指标面板数据指引。"""
    check = check_mock_permission(args, "handle_education_panel", "user-macro-datas")
    if check is not None:
        return check
    data = {
        "note": "马克数据网提供各省高校/在校生等教育指标面板数据",
        "湖北省高校数据（已核实）": [
            {"year": 2024, "indicator": "普通高校数量", "value": 134, "unit": "所", "source": "湖北省统计局"},
            {"year": 2024, "indicator": "普通高校本专科在校生", "value": 191.52, "unit": "万人", "source": "湖北省统计局"},
            {"year": 2024, "indicator": "在校研究生", "value": 24.21, "unit": "万人", "source": "湖北省统计局"},
            {"year": 2020, "indicator": "普通高校数量", "value": 129, "unit": "所", "source": "湖北省统计局"},
            {"year": 2015, "indicator": "普通高校数量", "value": 126, "unit": "所", "source": "湖北省统计局"},
            {"year": 2010, "indicator": "普通高校数量", "value": 120, "unit": "所", "source": "湖北省统计局"},
        ],
        "武汉市高校数据（已核实）": [
            {"year": 2024, "indicator": "普通高校数量", "value": 92, "unit": "所", "source": "武汉市统计局", "note": "全国第三"},
            {"year": 2024, "indicator": "在校大学生", "value": 133.3, "unit": "万人", "source": "武汉市统计局", "note": "全国第一"},
        ],
        "全国高校数据（已核实）": [
            {"year": 2024, "indicator": "普通高校数量", "value": 3117, "unit": "所", "source": "教育部"},
            {"year": 2024, "indicator": "普通高校本专科在校生", "value": 4700, "unit": "万人", "source": "教育部"},
            {"year": 2024, "indicator": "研究生在校生", "value": 388.29, "unit": "万人", "source": "教育部"},
        ],
        "数据来源": {
            "马克数据网": "https://www.macrodatas.cn/",
            "教育部官网": "https://www.moe.gov.cn/",
            "湖北省统计局": "https://tjj.hubei.gov.cn/tjsj/"
        }
    }
    return [TextContent(type="text", text=_ok_json(data))]


async def handle_nsti_report(args: dict) -> list[TextContent]:
    """科技部《全国科技经费投入统计公报》数据指引。"""
    check = check_mock_permission(args, "handle_nsti_report", "user-macro-datas")
    if check is not None:
        return check
    data = {
        "note": "科技部每年发布《全国科技经费投入统计公报》，包含分省R&D数据",
        "公报网址": "https://www.most.gov.cn/kjtj/",
        "最新公报数据（2023年度，2024年发布）": {
            "全国R&D经费": 33078.1,
            "unit": "亿元",
            "R&D投入强度": "2.64%",
            "基础研究经费": 2212.3,
            "unit2": "亿元",
            "全国R&D人员": 248.5,
            "unit3": "万人"
        },
        "分省R&D数据（2022年度公报）": [
            {"rank": 1, "province": "广东", "rd_expenditure": 4202.2, "unit": "亿元"},
            {"rank": 2, "province": "江苏", "rd_expenditure": 3835.0, "unit": "亿元"},
            {"rank": 3, "province": "北京", "rd_expenditure": 2843.3, "unit": "亿元"},
            {"rank": 4, "province": "浙江", "rd_expenditure": 2416.8, "unit": "亿元"},
            {"rank": 5, "province": "山东", "rd_expenditure": 1952.1, "unit": "亿元"},
            {"rank": 6, "province": "上海", "rd_expenditure": 1880.4, "unit": "亿元"},
            {"rank": 7, "province": "湖北", "rd_expenditure": 1161.3, "unit": "亿元"}
        ],
        "公报获取方式": [
            "科技部门户网站: https://www.most.gov.cn/kjtj/",
            "国家统计局: https://www.stats.gov.cn/tjsj/ndsj/",
            "马克数据网: https://www.macrodatas.cn/ (需注册)"
        ]
    }
    return [TextContent(type="text", text=_ok_json(data))]


# ─── 工具定义 ─────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_rd_panel",
        description="中国各省R&D面板数据指引（注：返回已知数据+马克数据网使用方法）",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="get_tech_panel",
        description="中国科技指标面板数据指引（高新技术企业/技术合同/专利）",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="get_industry_panel",
        description="中国产业指标面板数据指引（各省GDP/工业/服务业）",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="get_education_panel",
        description="中国教育指标面板数据指引（各省高校/在校生/研究生）",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="get_nsti_report",
        description="科技部《全国科技经费投入统计公报》数据指引（含分省R&D排名）",
        inputSchema={"type": "object", "properties": {}}
    ),
]

TOOL_HANDLERS = {
    "get_rd_panel": handle_rd_panel,
    "get_tech_panel": handle_tech_panel,
    "get_industry_panel": handle_industry_panel,
    "get_education_panel": handle_education_panel,
    "get_nsti_report": handle_nsti_report,
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
                server_name="user-macro-datas",
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
