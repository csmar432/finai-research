#!/usr/bin/env python3
"""user-hubei-stats MCP Server — 湖北省统计年鉴数据。

数据源：
  - akshare: 全国及部分省份GDP/CPI/PPI等宏观数据
  - 湖北省统计局官网: https://tjj.hubei.gov.cn/
  - 武汉统计年鉴PDF: http://tjj.wuhan.gov.cn/

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings
from pathlib import Path
from typing import Any
warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print("ERROR: akshare required. pip install akshare", flush=True)
    sys.exit(1)

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions

server = Server("user-hubei-stats")

# ─── 辅助函数 ───────────────────────────────────────────────


def _df_to_json(df: Any) -> str:
    """将 DataFrame 转换为标准 JSON 响应格式。"""
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"result": {"data": [], "count": 0}, "success": True}, ensure_ascii=False)
    records = df.to_dict(orient="records")
    for row in records:
        for k, v in row.items():
            if hasattr(v, "strftime"):
                row[k] = v.strftime("%Y-%m-%d")
            elif hasattr(v, "isoformat"):
                row[k] = v.isoformat()
    return json.dumps({"result": {"data": records, "count": len(records), "columns": list(df.columns)}, "success": True}, ensure_ascii=False)


def _error_json(msg: str) -> str:
    return json.dumps({"error": msg, "success": False}, ensure_ascii=False)


# ─── 工具处理函数 ───────────────────────────────────────────

async def handle_china_gdp(args: dict) -> list[TextContent]:
    """获取全国GDP季度数据（2006年至今）。"""
    try:
        df = ak.macro_china_gdp()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_china_gdp_yearly(args: dict) -> list[TextContent]:
    """获取全国GDP年度数据。"""
    try:
        df = ak.macro_china_gdp_yearly()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_cpi(args: dict) -> list[TextContent]:
    """获取中国CPI月度数据。"""
    try:
        df = ak.macro_china_cpi_monthly()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_ppi(args: dict) -> list[TextContent]:
    """获取中国PPI月度数据。"""
    try:
        df = ak.macro_china_ppi_monthly()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_pmi(args: dict) -> list[TextContent]:
    """获取中国PMI月度数据（官方+财新）。"""
    try:
        df = ak.macro_china_pmi()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_m2(args: dict) -> list[TextContent]:
    """获取中国M2货币供应量年度数据。"""
    try:
        df = ak.macro_china_m2_yearly()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_fdi(args: dict) -> list[TextContent]:
    """获取中国FDI月度数据。"""
    try:
        df = ak.macro_china_fdi()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_consumer_retail(args: dict) -> list[TextContent]:
    """获取中国社会消费品零售总额数据。"""
    try:
        df = ak.macro_china_consumer_goods_retail()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_industry_pmi(args: dict) -> list[TextContent]:
    """获取中国工业增加值增速数据。"""
    try:
        df = ak.macro_china_industrial_production_yoy()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def handle_tech_contract(args: dict) -> list[TextContent]:
    """技术合同成交额数据（注：akshare暂无此数据，返回手动录入说明）。"""
    note = {
        "note": "akshare暂无技术合同分省数据",
        "湖北省数据来源": [
            "湖北省科技厅官网: https://kjt.hubei.gov.cn/",
            "湖北省统计年鉴: https://tjj.hubei.gov.cn/tjsj/tjnj/",
            "马克数据网: https://www.macrodatas.cn/ (付费面板数据)"
        ],
        "已知数据": [
            {"year": 2025, "value": 6100, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2024, "value": 5504.29, "unit": "亿元", "source": "湖北省统计局《2024年统计公报》", "note": "合同70327项，同比+14.6%"},
            {"year": 2023, "value": 4802.24, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2022, "value": 3017.86, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2021, "value": 2111.63, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2020, "value": 1686.95, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2019, "value": 1237.0, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板", "note": "来源：马克数据网整理年鉴数据"},
        ]
    }
    return [TextContent(type="text", text=json.dumps({"result": note, "success": True}, ensure_ascii=False))]


async def handle_rd_funding(args: dict) -> list[TextContent]:
    """湖北R&D经费数据（注：akshare暂无分省数据，返回已知数据+替代来源）。"""
    note = {
        "note": "akshare暂无湖北R&D分省数据，以下为已核实数据",
        "湖北省数据来源": [
            "湖北省科技厅官网: https://kjt.hubei.gov.cn/",
            "马克数据网《中国科技统计年鉴》面板: https://www.macrodatas.cn/",
            "科技部《全国科技经费投入公报》: https://www.most.gov.cn/kjtj/"
        ],
        "已知数据": [
            {"year": 2024, "value": 1408.2, "unit": "亿元", "source": "湖北省科技厅", "note": "同比+12.2%，增幅全国第3"},
            {"year": 2023, "value": 1257.0, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2022, "value": 1161.3, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2021, "value": 1045.3, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2020, "value": 902.3, "unit": "亿元", "source": "湖北省科技厅"},
            {"year": 2019, "value": 860.9, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板", "note": "马克数据网整理年鉴数据"},
            {"year": 2018, "value": 773.0, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2017, "value": 700.63, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2016, "value": 614.9, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2015, "value": 532.5, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2010, "value": 350.2, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2007, "value": 112.5, "unit": "亿元", "source": "马克数据网《中国科技统计年鉴》面板"},
        ],
        "历年R&D强度说明": "官方仅公布增幅+0.19pp（2024年），修订后强度值未公布"
    }
    return [TextContent(type="text", text=json.dumps({"result": note, "success": True}, ensure_ascii=False))]


async def handle_hitech_companies(args: dict) -> list[TextContent]:
    """湖北高新技术企业数据（注：akshare暂无，返回已知数据+替代来源）。"""
    note = {
        "note": "akshare暂无湖北高新技术企业分省数据",
        "湖北省数据来源": [
            "湖北省科技厅高新技术企业认定: https://kjt.hubei.gov.cn/",
            "国家高新技术企业认定管理工作网: https://www.innocom.gov.cn/",
            "马克数据网: https://www.macrodatas.cn/"
        ],
        "已知数据": [
            {"year": 2024, "value": 30000, "unit": "家", "source": "湖北省科技厅/湖北日报", "note": "中部第1，五年增长2.9倍（较2019年）"},
            {"year": 2023, "value": 25000, "unit": "家", "source": "湖北省科技厅"},
            {"year": 2021, "value": 14560, "unit": "家", "source": "湖北省科技厅"},
            {"year": 2020, "value": 10404, "unit": "家", "source": "湖北省科技厅"},
            {"year": 2019, "value": 7893, "unit": "家", "source": "马克数据网《中国科技统计年鉴》面板", "note": "口径：有效期内认定总数"},
            {"year": 2018, "value": 6590, "unit": "家", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2016, "value": 3317, "unit": "家", "source": "马克数据网《中国科技统计年鉴》面板"},
            {"year": 2012, "value": 1577, "unit": "家", "source": "马克数据网《中国科技统计年鉴》面板"},
        ]
    }
    return [TextContent(type="text", text=json.dumps({"result": note, "success": True}, ensure_ascii=False))]


# ─── 工具定义 ─────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_china_gdp",
        description="获取全国GDP季度数据（2006年至今），含GDP绝对值和同比增速",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回全国GDP季度序列"
        }
    ),
    Tool(
        name="get_china_gdp_yearly",
        description="获取全国GDP年度数据",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回全国GDP年度序列"
        }
    ),
    Tool(
        name="get_cpi",
        description="获取中国CPI月度数据（同比/环比）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回CPI月度序列"
        }
    ),
    Tool(
        name="get_ppi",
        description="获取中国PPI月度数据（生产资料/生活资料）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回PPI月度序列"
        }
    ),
    Tool(
        name="get_pmi",
        description="获取中国PMI月度数据（官方+财新）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回PMI月度序列"
        }
    ),
    Tool(
        name="get_m2",
        description="获取中国M2货币供应量年度数据",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回M2年度序列"
        }
    ),
    Tool(
        name="get_fdi",
        description="获取中国FDI月度实际使用外资数据",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回FDI月度序列"
        }
    ),
    Tool(
        name="get_consumer_retail",
        description="获取中国社会消费品零售总额月度数据",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回零售总额月度序列"
        }
    ),
    Tool(
        name="get_industry_production",
        description="获取中国工业增加值增速月度数据",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回工业增加值增速月度序列"
        }
    ),
    Tool(
        name="get_hubei_tech_contract",
        description="湖北技术合同成交额（注：akshare暂无分省数据，返回已知数据和替代来源）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回已知湖北技术合同数据"
        }
    ),
    Tool(
        name="get_hubei_rd_funding",
        description="湖北R&D经费投入（注：akshare暂无分省数据，返回已知数据和替代来源）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回已知湖北R&D数据"
        }
    ),
    Tool(
        name="get_hubei_hitech",
        description="湖北高新技术企业数量（注：akshare暂无分省数据，返回已知数据和替代来源）",
        inputSchema={
            "type": "object",
            "properties": {},
            "description": "无参数，返回已知湖北高新技术企业数据"
        }
    ),
]

TOOL_HANDLERS = {
    "get_china_gdp": handle_china_gdp,
    "get_china_gdp_yearly": handle_china_gdp_yearly,
    "get_cpi": handle_cpi,
    "get_ppi": handle_ppi,
    "get_pmi": handle_pmi,
    "get_m2": handle_m2,
    "get_fdi": handle_fdi,
    "get_consumer_retail": handle_consumer_retail,
    "get_industry_production": handle_industry_pmi,
    "get_hubei_tech_contract": handle_tech_contract,
    "get_hubei_rd_funding": handle_rd_funding,
    "get_hubei_hitech": handle_hitech_companies,
}

# ─── MCP 回调 ───────────────────────────────────────────────

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
                server_name="user-hubei-stats",
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
