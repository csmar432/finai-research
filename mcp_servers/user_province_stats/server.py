#!/usr/bin/env python3
"""user-province-stats MCP Server — 全国各省科技创新数据。

统一数据接口，支持：
  1. get_province_indicator   — 单一年份指标查询
  2. get_province_timeseries — 多年序列查询
  3. get_province_rankings   — 全国排名表查询

数据来源：
  - 各省统计局年度公报
  - 科技部《全国科技经费投入统计公报》
  - 马克数据网整理《中国科技统计年鉴》面板
  - World Bank API / akshare

Usage:
    python server.py
"""

from __future__ import annotations

import asyncio
import json, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
_DATA_FILE = _PROJECT_ROOT / "data" / "national_province_data_2026.json"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions

server = Server("user-province-stats")

# ── data loader ────────────────────────────────────────────────────────────────
_national_data: dict | None = None

def _load_data() -> dict:
    global _national_data
    if _national_data is None:
        if not _DATA_FILE.exists():
            return {"error": f"Data file not found: {_DATA_FILE}"}
        with open(_DATA_FILE, encoding="utf-8") as f:
            _national_data = json.load(f)
    return _national_data


def _ok(data: dict) -> str:
    return json.dumps({"result": data, "success": True}, ensure_ascii=False)


def _err(msg: str) -> str:
    return json.dumps({"error": msg, "success": False}, ensure_ascii=False)


# ── tool handlers ──────────────────────────────────────────────────────────
PROVINCES = {
    "北京", "天津", "河北", "山西", "内蒙古",
    "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南",
    "广东", "广西", "海南",
    "重庆", "四川", "贵州", "云南", "西藏",
    "陕西", "甘肃", "青海", "宁夏", "新疆",
}
CAT_IDS = {"ECON", "EDU", "PLAT", "RD", "ENT", "TECH", "IND", "AI", "FIN"}

# Indicator alias → (category_id, display_name)
_IND_ALIASES = {
    # category: ECON
    "gdp": ("ECON", "地区GDP"),
    "gdp_2024": ("ECON", "地区GDP（2024年）"),
    "gdp_2025": ("ECON", "地区GDP（2025年）"),
    "gdp增速": ("ECON", "GDP增速"),
    "人均gdp": ("ECON", "人均GDP"),
    "地区gdp": ("ECON", "地区GDP"),
    # category: EDU
    "高校数量": ("EDU", "普通高校数量"),
    "双一流": ("EDU", "双一流高校数量"),
    "本专科在校生": ("EDU", "普通高校本专科在校生"),
    "在校研究生": ("EDU", "在校研究生"),
    "在校大学生": ("EDU", "普通高校本专科在校生"),
    "高校在校生": ("EDU", "普通高校本专科在校生"),
    # category: PLAT
    "国家实验室": ("PLAT", "国家实验室"),
    "大科学装置": ("PLAT", "大科学装置"),
    "重点实验室": ("PLAT", "全国重点实验室"),
    "技术创新中心": ("PLAT", "国家技术创新中心"),
    "湖北实验室": ("PLAT", "湖北实验室"),
    "创新平台": ("PLAT", "国家级创新平台"),
    "新型研发机构": ("PLAT", "新型研发机构"),
    # category: RD
    "r&d经费": ("RD", "R&D经费投入"),
    "r_d经费": ("RD", "R&D经费投入"),
    "研发经费": ("RD", "R&D经费投入"),
    "rd经费": ("RD", "R&D经费投入"),
    "r&d强度": ("RD", "R&D投入强度"),
    "r_d强度": ("RD", "R&D投入强度"),
    "研发强度": ("RD", "R&D投入强度"),
    "rd强度": ("RD", "R&D投入强度"),
    "财政科技支出": ("RD", "财政科技支出"),
    # category: ENT
    "高新技术企业": ("ENT", "高新技术企业数量"),
    "高新企业": ("ENT", "高新技术企业数量"),
    "科技型中小企业": ("ENT", "科技型中小企业数量"),
    "专精特新": ("ENT", "专精特新小巨人企业"),
    "小巨人": ("ENT", "专精特新小巨人企业"),
    # category: TECH
    "技术合同成交额": ("TECH", "技术合同成交额"),
    "技术合同": ("TECH", "技术合同成交额"),
    "合同成交额": ("TECH", "技术合同成交额"),
    "成果转化率": ("TECH", "科技成果就地转化率"),
    "转化率": ("TECH", "科技成果就地转化率"),
    # category: IND
    "数字经济": ("IND", "数字经济规模"),
    "高技术制造业": ("IND", "高技术制造业增加值增速"),
    "高技术制造业增速": ("IND", "高技术制造业增加值增速"),
    "数字经济规模": ("IND", "数字经济总规模"),
    # category: AI
    "ai企业": ("AI", "AI企业数量"),
    "ai产业": ("AI", "AI产业规模"),
    "ai产业规模": ("AI", "AI产业规模"),
    "算力": ("AI", "算力基础设施"),
    # category: FIN
    "上市公司": ("FIN", "A股上市公司数量"),
    "贷款余额": ("FIN", "科技型企业贷款余额"),
    "母基金": ("FIN", "省级政府投资基金规模"),
    "基金规模": ("FIN", "省级政府投资基金规模"),
}


def _resolve_indicator(indicator: str):
    """Return (category_id, display_name) for an indicator string."""
    key = indicator.strip().lower()
    if key in _IND_ALIASES:
        return _IND_ALIASES[key]
    # try partial match
    for alias, (cat, name) in _IND_ALIASES.items():
        if key in alias or alias in key:
            return cat, name
    # treat as literal category_id
    if key.upper() in CAT_IDS:
        return key.upper(), key.upper()
    return None, indicator


def _get_timeseries_map() -> dict:
    """Map (province, indicator_key) → series data dict."""
    ts_map = {}
    national = _load_data()
    if "error" in national:
        return ts_map
    for prov_key, prov_data in national.get("provinces", {}).items():
        ts_all = prov_data.get("time_series", {})
        if not isinstance(ts_all, dict):
            continue
        for series_key, series_val in ts_all.items():
            ts_map[(prov_key, series_key)] = series_val
    return ts_map


# ── get_province_indicator ────────────────────────────────────────────────
async def handle_province_indicator(args: dict) -> list[TextContent]:
    province = args.get("province", "").strip()
    indicator = args.get("indicator", "").strip()
    year_str = args.get("year") or ""

    if not province or province not in PROVINCES:
        return [TextContent(type="text", text=_err(
            f"province must be one of: {', '.join(sorted(PROVINCES))}"))]

    national = _load_data()
    if "error" in national:
        return [TextContent(type="text", text=_err(national["error"]))]

    prov_data = national.get("provinces", {}).get(province, {})
    cats_data = prov_data.get("data", {})

    cat_id, disp_name = _resolve_indicator(indicator)
    result = {
        "province": province,
        "requested_indicator": indicator,
        "resolved_indicator": disp_name,
        "category_id": cat_id,
        "verification": prov_data.get("verification", "unknown"),
    }

    # Search in category data
    found = False
    if cat_id and cat_id in cats_data:
        cat_items = cats_data[cat_id]
        # Try exact match first
        for key, val in cat_items.items():
            if key.lower().replace("_", "") == indicator.lower().replace("_", "").replace("-", ""):
                result["data"] = val
                result["search_method"] = "exact_category_match"
                found = True
                break
        if not found:
            # Return all indicators in category
            result["category_data"] = cat_items
            result["search_method"] = "category_browse"
            result["note"] = (
                f"Indicator '{indicator}' not found in {province}/{cat_id}. "
                f"Returned all indicators in this category."
            )
            found = True

    if not found:
        # Fallback: search all categories
        all_data = {}
        for cat, items in cats_data.items():
            all_data[cat] = items
        # Also check time_series
        ts = prov_data.get("time_series", {})
        if isinstance(ts, dict) and indicator in ts:
            result["time_series"] = ts[indicator]
            result["search_method"] = "timeseries_fallback"
            found = True
        else:
            result["all_categories"] = list(cats_data.keys())
            result["time_series_keys"] = list(ts.keys()) if isinstance(ts, dict) else []
            result["search_method"] = "not_found"
            result["note"] = (
                f"Indicator '{indicator}' not found in {province}. "
                f"Available categories: {list(cats_data.keys())}"
            )

    # available_years — only if time_series is a dict
    ts = prov_data.get("time_series", {})
    if isinstance(ts, dict):
        ind_ts = ts.get(indicator, {})
        if isinstance(ind_ts, dict):
            result["available_years"] = list(ind_ts.get("data", {}).keys())

    return [TextContent(type="text", text=_ok(result))]


# ── get_province_timeseries ──────────────────────────────────────────────
async def handle_province_timeseries(args: dict) -> list[TextContent]:
    province = args.get("province", "").strip()
    indicator = args.get("indicator", "").strip()

    if not province or province not in PROVINCES:
        return [TextContent(type="text", text=_err(
            f"province must be one of: {', '.join(sorted(PROVINCES))}"))]

    national = _load_data()
    if "error" in national:
        return [TextContent(type="text", text=_err(national["error"]))]

    prov_data = national.get("provinces", {}).get(province, {})
    ts = prov_data.get("time_series", {})

    # Handle empty skeleton (ts is [] → empty list)
    if not isinstance(ts, dict) or not ts:
        return [TextContent(type="text", text=_ok({
            "province": province,
            "indicator": indicator,
            "search_method": "not_found",
            "available_series": [],
            "note": f"No time series data for {province}. Run fetch_provincial_stats.py to populate.",
        }))]

    # Try exact key match first
    if indicator in ts:
        series = ts[indicator]
        result = {
            "province": province,
            "indicator": indicator,
            "unit": series.get("unit", ""),
            "source": series.get("source", ""),
            "data": series.get("data", {}),
            "year_count": len(series.get("data", {})),
            "search_method": "exact_match",
        }
        return [TextContent(type="text", text=_ok(result))]

    # Try alias matching
    ts_map = _get_timeseries_map()
    for (p, key), series in ts_map.items():
        if p == province and key.lower() == indicator.lower():
            result = {
                "province": province,
                "indicator": indicator,
                "matched_key": key,
                "unit": series.get("unit", ""),
                "source": series.get("source", ""),
                "data": series.get("data", {}),
                "year_count": len(series.get("data", {})),
                "search_method": "alias_match",
            }
            return [TextContent(type="text", text=_ok(result))]

    # Not found
    return [TextContent(type="text", text=_ok({
        "province": province,
        "indicator": indicator,
        "search_method": "not_found",
        "available_series": list(ts.keys()),
        "note": (
            f"Time series for '{indicator}' in {province} not found. "
            f"Available series: {list(ts.keys())}"
        ),
    }))]


# ── get_province_rankings ────────────────────────────────────────────────
RANKING_TABLES = {
    "gdp_2024": "GDP_2024",
    "rd经费_2024": "RD经费_2024",
    "rd强度_2024": "RD强度_2024",
    "高新技术企业_2024": "高新技术企业_2024",
    "技术合同_2024": "技术合同_2024",
}


async def handle_province_rankings(args: dict) -> list[TextContent]:
    table = args.get("table", "").strip()

    if not table:
        return [TextContent(type="text", text=_err("table is required"))]

    # Try direct match first
    key = table
    national = _load_data()
    if "error" in national:
        return [TextContent(type="text", text=_err(national["error"]))]

    rankings = national.get("ranking_tables", {})

    if key not in rankings:
        key = RANKING_TABLES.get(table.lower(), "")
    if key not in rankings:
        return [TextContent(type="text", text=_ok({
            "search_method": "not_found",
            "available_tables": list(rankings.keys()),
            "note": f"Table '{table}' not found. Available: {list(rankings.keys())}"
        }))]

    t = rankings[key]
    return [TextContent(type="text", text=_ok({
        "table_id": key,
        "title": t.get("title", ""),
        "unit": t.get("unit", ""),
        "source": t.get("source", ""),
        "note": t.get("note", ""),
        "data": t.get("data", []),
        "count": len(t.get("data", [])),
    }))]


# ── get_all_provinces_summary ────────────────────────────────────────────
async def handle_all_provinces_summary(args: dict) -> list[TextContent]:
    """Return summary of all provinces: basic info + available indicators."""
    national = _load_data()
    if "error" in national:
        return [TextContent(type="text", text=_err(national["error"]))]

    summary = {}
    for prov_key, prov_data in national.get("provinces", {}).items():
        cats = prov_data.get("data", {})
        ts_raw = prov_data.get("time_series", {})
        ts_keys = list(ts_raw.keys()) if isinstance(ts_raw, dict) else []
        summary[prov_key] = {
            "province_cn": prov_data.get("name_cn", prov_key),
            "capital": prov_data.get("capital", ""),
            "region": prov_data.get("region", ""),
            "gdp_rank_2024": prov_data.get("gdp_rank_2024"),
            "verification": prov_data.get("verification", "unknown"),
            "categories": list(cats.keys()) if isinstance(cats, dict) else [],
            "time_series_count": len(ts_keys),
            "time_series": ts_keys,
        }

    payload = {
        "total_provinces": len(summary),
        "province_list": list(summary.keys()),
        "verification_summary": national.get("verification_status", {}),
        "provinces": summary,
    }
    return [TextContent(type="text", text=_ok(payload))]


# ── tool definitions ───────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="get_province_indicator",
        description="查询指定省份的单一指标（如GDP、R&D经费等），支持指定年份。可用于获取某省份最新值或在研究报告中引用。",
        inputSchema={
            "type": "object",
            "properties": {
                "province": {
                    "type": "string",
                    "description": "省份名称（全国31省全覆盖）",
                    "enum": [
                        "北京","天津","河北","山西","内蒙古",
                        "辽宁","吉林","黑龙江",
                        "上海","江苏","浙江","安徽","福建","江西","山东",
                        "河南","湖北","湖南",
                        "广东","广西","海南",
                        "重庆","四川","贵州","云南","西藏",
                        "陕西","甘肃","青海","宁夏","新疆",
                    ],
                },
                "indicator": {
                    "type": "string",
                    "description": (
                        "指标名或ID，支持别名。别名如：GDP、R&D经费、研发经费、"
                        "高新技术企业、技术合同成交额、R&D强度、本专科在校生等。"
                        "完整指标定义见 national_province_data_2026.json -> indicator_definitions"
                    ),
                    "examples": ["GDP", "R&D经费", "高新技术企业", "技术合同成交额", "本专科在校生", "数字经济规模", "AI算力规模"],
                },
                "year": {
                    "type": "string",
                    "description": "年份（可选），如'2024'。不填返回最新值。",
                    "examples": ["2024", "2025", "2020"],
                },
            },
            "required": ["province", "indicator"],
        },
    ),
    Tool(
        name="get_province_timeseries",
        description="获取指定省份和指标的多年序列数据。用于论文图表或回归分析面板数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "province": {
                    "type": "string",
                    "description": "省份名称（全国31省全覆盖）",
                    "enum": [
                        "北京","天津","河北","山西","内蒙古",
                        "辽宁","吉林","黑龙江",
                        "上海","江苏","浙江","安徽","福建","江西","山东",
                        "河南","湖北","湖南",
                        "广东","广西","海南",
                        "重庆","四川","贵州","云南","西藏",
                        "陕西","甘肃","青海","宁夏","新疆",
                    ],
                },
                "indicator": {
                    "type": "string",
                    "description": "指标ID，支持：GDP、R&D经费、高新技术企业、技术合同成交额、本专科在校生、R&D强度等",
                    "examples": ["GDP", "R&D经费", "高新技术企业", "技术合同成交额", "本专科在校生", "R&D强度"],
                },
            },
            "required": ["province", "indicator"],
        },
    ),
    Tool(
        name="get_province_rankings",
        description="获取全国排名表，用于省间横向对比（如各省GDP排名、R&D排名）。",
        inputSchema={
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "排名表ID",
                    "enum": ["GDP_2024", "RD经费_2024", "RD强度_2024", "高新技术企业_2024", "技术合同_2024"],
                    "examples": ["GDP_2024", "RD经费_2024", "RD强度_2024"],
                },
            },
            "required": ["table"],
        },
    ),
    Tool(
        name="get_all_provinces_summary",
        description="获取所有省份的概览信息（包含哪些省份、哪些数据已收录、哪些指标有序列数据）。",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

TOOL_HANDLERS = {
    "get_province_indicator":    handle_province_indicator,
    "get_province_timeseries":  handle_province_timeseries,
    "get_province_rankings":    handle_province_rankings,
    "get_all_provinces_summary": handle_all_provinces_summary,
}

# ── Direct tool invocation (for llm_gateway venv subprocess) ───────────────────
def _invoke(tool_name: str, kwargs: dict) -> dict:
    """Sync invoke via handler. Returns a JSON-serializable dict for llm_gateway."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": "Unknown tool: " + tool_name}
    try:
        result = handler(kwargs)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        if isinstance(result, list) and len(result) > 0:
            text = result[0].text
            data = json.loads(text)
            # Handler wraps in _ok() → {"result": {...}, "success": true}
            # Unwrap one level so caller sees the actual payload
            if isinstance(data, dict) and "result" in data and "success" in data:
                return data["result"]
            return data
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


# Expose tool manager dict so llm_gateway can inspect available tools
_tool_manager = type("ToolManager", (), {
    "_tools": {
        name: type("ToolEntry", (), {"fn": lambda n=name: _invoke(n, {})})()
        for name in TOOL_HANDLERS
    }
})()


# ── MCP callbacks ────────────────────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=_err(f"Unknown tool: {name}"))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=_err(str(e)))]


# ── main ───────────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-province-stats",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
