#!/usr/bin/env python3
"""
user-tushare MCP Server
=======================
A股数据（Tushare Pro），覆盖：行情/财务/融资融券/北向/指数/概念股。

Usage:
    python server.py

环境变量：
    TUSHARE_TOKEN — Tushare Pro API Token（可选，缺失时自动用 akshare）
    获取地址：https://tushare.pro/register
"""

from __future__ import annotations

__all__ = [
    "server",
    "TOOLS",
    "TOOL_HANDLERS",
    "get_ts_pro",
    "_check_token",
    "_akshare_fallback",
    "handle_get_stock_basic",
    "handle_get_daily_quote",
    "handle_get_financial_report",
    "handle_get_margin_data",
    "handle_get_index_data",
    "handle_get_concept_stocks",
    "handle_get_trade_calendar",
    "handle_get_institutional_holdings",
    "handle_get_top_holders",
    "main",
]

import json, logging, os, sys, warnings
from pathlib import Path
from typing import Any, Optional
warnings.filterwarnings("ignore")
_log = logging.getLogger("user-tushare")

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
    ts = None

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    ak = None

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
        # Return None so callers can handle gracefully (they already wrap in try/except)
        return None

    _ts_pro = ts.pro_api(token)
    return _ts_pro


def _check_token() -> str | None:
    """Return error message if token unavailable, or None if OK."""
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_KEY", "")
    if not token:
        return (
            "TUSHARE_TOKEN is not set. Will attempt akshare fallback automatically."
        )
    return None


# ── akshare Fallback Helpers ──────────────────────────────────────────────────


def _akshare_fallback(data_type: str, **kwargs) -> dict | None:
    """
    Call akshare as a fallback when Tushare token is not available.

    Returns a dict with:
      - result: the data
      - source: "akshare (automatic fallback)"
      - columns: column names
      - count: row count

    Returns None if akshare is not installed or the call fails.
    """
    if not AKSHARE_AVAILABLE or ak is None:
        return None

    try:
        if data_type == "daily_quote":
            symbol = kwargs.get("ts_code", "")
            period = kwargs.get("period", "daily")
            start = kwargs.get("start_date", "")
            end = kwargs.get("end_date", "")
            adjust = kwargs.get("adjust", "")

            # Convert ts_code to akshare format: 000001.SZ → 000001
            symbol_ak = symbol.replace(".SZ", "").replace(".SH", "")
            period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
            period_ak = period_map.get(period, "daily")

            df = ak.stock_zh_a_hist(
                symbol=symbol_ak,
                period=period_ak,
                start_date=start,
                end_date=end,
                adjust=adjust or "qfq",
            )
            if df is None or df.empty:
                return {"result": {"data": [], "count": 0, "columns": []},
                        "success": True, "source": "akshare (automatic fallback)",
                        "note": "No data returned from akshare"}

            # Rename columns to Tushare-like format
            col_map = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "vol",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_chg",
                "涨跌额": "change",
                "换手率": "turnover",
            }
            df = df.rename(columns=col_map)

            records = df.to_dict(orient="records")
            for row in records:
                for k, v in list(row.items()):
                    if hasattr(v, "strftime"):
                        row[k] = v.strftime("%Y-%m-%d")
                    elif hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {
                "result": {"data": records, "count": len(records),
                           "columns": list(df.columns)},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Data from akshare (free). Tushare Pro data may differ in coverage and fields.",
            }

        elif data_type == "financial_report":
            symbol = kwargs.get("ts_code", "")
            symbol_ak = symbol.replace(".SZ", "").replace(".SH", "")

            df = ak.stock_financial_analysis_indicator(symbol=symbol_ak)
            if df is None or df.empty:
                return {"result": {"data": [], "count": 0, "columns": []},
                        "success": True, "source": "akshare (automatic fallback)",
                        "note": "No financial data from akshare"}

            col_map = {
                "股票代码": "ts_code",
                "公告日期": "ann_date",
                "报告日期": "end_date",
                "净资产收益率(%)": "roe",
                "资产收益率(%)": "roa",
                "销售毛利率(%)": "gross_profit_margin",
                "销售净利率(%)": "net_profit_margin",
                "资产负债率(%)": "debt_to_assets",
                "流动比率": "current_ratio",
                "速动比率": "quick_ratio",
                "基本每股收益": "basic_eps",
                "稀释每股收益": "diluted_eps",
                "每股净资产": "bps",
                "每股经营现金流": "ocfps",
            }
            df = df.rename(columns=col_map)
            records = df.to_dict(orient="records")
            for row in records:
                for k, v in list(row.items()):
                    if hasattr(v, "strftime"):
                        row[k] = v.strftime("%Y-%m-%d")
                    elif hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {
                "result": {"data": records, "count": len(records),
                           "columns": list(df.columns)},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Financial indicators from akshare. Tushare Pro offers more complete financial statements.",
            }

        elif data_type == "margin":
            symbol = kwargs.get("ts_code", "")
            symbol_ak = symbol.replace(".SZ", "").replace(".SH", "") if symbol else ""

            if not symbol_ak:
                return {
                    "result": {"data": [], "count": 0, "columns": []},
                    "success": True,
                    "source": "akshare (automatic fallback)",
                    "note": "Margin data by stock requires ts_code parameter in akshare fallback mode",
                }

            df = ak.stock_margin_detail(symbol=symbol_ak)
            if df is None or df.empty:
                return {"result": {"data": [], "count": 0, "columns": []},
                        "success": True, "source": "akshare (automatic fallback)",
                        "note": "No margin data from akshare"}

            col_map = {
                "股票代码": "ts_code",
                "日期": "trade_date",
                "融资余额": "balance",
                "融资买入额": "buy_balance",
                "融资偿还额": "repay_balance",
                "融券余额": "sec_balance",
                "融券卖出量": "sec_sell_vol",
                "融券偿还量": "sec_repay_vol",
            }
            df = df.rename(columns=col_map)
            records = df.to_dict(orient="records")
            for row in records:
                for k, v in list(row.items()):
                    if hasattr(v, "strftime"):
                        row[k] = v.strftime("%Y-%m-%d")
                    elif hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {
                "result": {"data": records, "count": len(records),
                           "columns": list(df.columns)},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Margin detail from akshare. Tushare Pro margin data may have different coverage.",
            }

        elif data_type == "hsgt":
            try:
                df = ak.stock_hsgt_north_net_flow_in(indicator="北向资金")
                if df is not None and not df.empty:
                    records = df.to_dict(orient="records")
                    return {
                        "result": {"data": records, "count": len(records),
                                   "columns": list(df.columns)},
                        "success": True,
                        "source": "akshare (automatic fallback)",
                        "note": "HSGT northbound flow from akshare.",
                    }
            except Exception:
                pass
            return {
                "result": {"data": [], "count": 0, "columns": []},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "HSGT data not available via akshare fallback",
            }

        elif data_type == "index_data":
            symbol = kwargs.get("ts_code", "")
            symbol_ak = symbol.replace(".SH", "").replace(".SZ", "")
            try:
                df = ak.stock_zh_index_daily(symbol=f"sh{symbol_ak}")
                if df is None or df.empty:
                    return {"result": {"data": [], "count": 0, "columns": []},
                            "success": True, "source": "akshare (automatic fallback)"}
                col_map = {
                    "日期": "trade_date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "vol",
                    "成交额": "amount",
                }
                df = df.rename(columns=col_map)
                records = df.to_dict(orient="records")
                for row in records:
                    for k, v in list(row.items()):
                        if hasattr(v, "strftime"):
                            row[k] = v.strftime("%Y-%m-%d")
                        elif hasattr(v, "isoformat"):
                            row[k] = v.isoformat()
                return {
                    "result": {"data": records, "count": len(records),
                               "columns": list(df.columns)},
                    "success": True,
                    "source": "akshare (automatic fallback)",
                    "note": "Index data from akshare.",
                }
            except Exception:
                return {
                    "result": {"data": [], "count": 0, "columns": []},
                    "success": True,
                    "source": "akshare (automatic fallback)",
                    "note": "Index data not available via akshare fallback",
                }

        elif data_type == "trade_calendar":
            try:
                df = ak.tool_trade_date_hist_sina()
                if df is not None and not df.empty:
                    records = df.to_dict(orient="records")
                    return {
                        "result": {"data": records, "count": len(records),
                                   "columns": list(df.columns)},
                        "success": True,
                        "source": "akshare (automatic fallback)",
                        "note": "Trade calendar from akshare.",
                    }
            except Exception:
                pass
            return {
                "result": {"data": [], "count": 0, "columns": []},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Trade calendar not available via akshare fallback",
            }

        elif data_type == "institutional_holdings":
            ts_code = kwargs.get("ts_code", "")
            start_date = kwargs.get("start_date", "20180101")
            end_date = kwargs.get("end_date", "")
            holder_type = kwargs.get("holder_type", "all")
            try:
                symbol = ts_code.replace(".SZ", "").replace(".SH", "")
                df = ak.stock_shareholder_change(indicator="机构持股", symbol=symbol)
                if df is not None and not df.empty:
                    if start_date:
                        df = df[df["公告日期"] >= start_date]
                    if end_date:
                        df = df[df["公告日期"] <= end_date]
                    records = df.head(50).to_dict(orient="records")
                    return {
                        "result": {"data": records, "count": len(records),
                                   "columns": list(df.columns)},
                        "success": True,
                        "source": "akshare (automatic fallback)",
                        "note": "Institutional holdings ratio from akshare. "
                                "Detailed type breakdown (QFII/fund/trust/broker) requires Tushare Pro.",
                    }
            except Exception:
                pass
            return {
                "result": {"data": [], "count": 0, "columns": []},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Institutional holdings not available via akshare fallback",
            }

        elif data_type == "top_holders":
            ts_code = kwargs.get("ts_code", "")
            try:
                symbol = ts_code.replace(".SZ", "").replace(".SH", "")
                market = "sh" if ".SH" in ts_code.upper() else "sz"
                df = ak.stock_top10_shareholder_em(symbol=symbol, indicator="十大流通股东")
                if df is not None and not df.empty:
                    records = df.head(10).to_dict(orient="records")
                    return {
                        "result": {"data": records, "count": len(records),
                                   "columns": list(df.columns)},
                        "success": True,
                        "source": "akshare (automatic fallback)",
                        "note": "Top-10 shareholders from akshare (东方财富). "
                                "Tushare Pro offers more detailed holder type classification.",
                    }
            except Exception:
                pass
            return {
                "result": {"data": [], "count": 0, "columns": []},
                "success": True,
                "source": "akshare (automatic fallback)",
                "note": "Top holders not available via akshare fallback",
            }

        else:
            return None

    except Exception as e:
        return {
            "result": {"data": [], "count": 0, "columns": []},
            "success": False,
            "source": "akshare (automatic fallback)",
            "error": str(e),
        }


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
    Tool(
        name="get_institutional_holdings",
        description="获取A股机构投资者持股数据（按机构类型：QFII/基金/社保/券商/信托）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "股票代码（格式：000001.SZ）"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期（格式：YYYYMMDD），默认20180101"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期（格式：YYYYMMDD），默认最新"
                },
                "holder_type": {
                    "type": "string",
                    "description": "机构类型过滤：qfii/fund/trust/broker/social_security/all",
                    "enum": ["qfii", "fund", "trust", "broker", "social_security", "all"],
                    "default": "all"
                },
                "period": {
                    "type": "string",
                    "description": "报告期类型：season（季报）/ann（年报）",
                    "enum": ["season", "ann"],
                    "default": "season"
                }
            },
            "required": ["ts_code"]
        }
    ),
    Tool(
        name="get_top_holders",
        description="获取上市公司前10大股东信息（股东名称/持股数量/持股比例/股东性质）。使用 Tushare Pro API。",
        inputSchema={
            "type": "object",
            "properties": {
                "ts_code": {
                    "type": "string",
                    "description": "股票代码（格式：000001.SZ）"
                },
                "ann_date": {
                    "type": "string",
                    "description": "公告日期（格式：YYYYMMDD），默认最新一期"
                }
            },
            "required": ["ts_code"]
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
    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:  # token IS available
        try:
            pro = get_ts_pro()
            if pro is not None:
                result = _safe_call(pro, "stock_basic",
                                     exchange=args.get("exchange"),
                                     list_status=args.get("list_status", "L"))
                return [TextContent(type="text", text=result)]
        except Exception as e:
            _log.warning(f"handle_get_stock_basic: Tushare call failed: {e}")

    # akshare fallback for stock basic info
    if AKSHARE_AVAILABLE and ak is not None:
        try:
            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                df = df.rename(columns={
                    "code": "ts_code",
                    "name": "name",
                })
                # Add exchange suffix
                if "ts_code" in df.columns:
                    df["exchange"] = df["ts_code"].apply(
                        lambda x: "SZSE" if x.startswith(("000", "002", "003", "300")) else "SSE"
                    )
                records = df.to_dict(orient="records")
                return [TextContent(type="text", text=json.dumps({
                    "result": {"data": records, "count": len(records),
                               "columns": list(df.columns)},
                    "success": True,
                    "source": "akshare (automatic fallback)",
                    "note": "Stock basic info from akshare (free). Full IPO details require Tushare Pro.",
                }, ensure_ascii=False))]
        except Exception as e:
            _log.warning(f"handle_get_stock_basic: akshare fallback failed: {e}")

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "TUSHARE_TOKEN not available and akshare fallback failed",
         "hint": "Install akshare: pip install akshare"},
        "get_stock_basic"))]


async def handle_get_daily_quote(args: dict) -> list[TextContent]:
    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response({"error": "ts_code is required"}, "get_daily_quote"))]

    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:  # token IS available
        try:
            pro = get_ts_pro()
            if pro is not None:
                if args.get("trade_date"):
                    result = _safe_call(pro, "daily", ts_code=ts_code,
                                         trade_date=args["trade_date"])
                else:
                    result = _safe_call(pro, "daily", ts_code=ts_code,
                                         start_date=args.get("start_date"),
                                         end_date=args.get("end_date"))
                return [TextContent(type="text", text=result)]
        except Exception as e:
            _log.warning(f"handle_get_daily_quote: Tushare call failed: {e}")

    # Fallback to akshare
    fallback = _akshare_fallback(
        "daily_quote",
        ts_code=ts_code,
        period="daily",
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        adjust="qfq",
    )
    if fallback:
        return [TextContent(type="text", text=json.dumps(fallback, ensure_ascii=False))]

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "Both Tushare and akshare unavailable. "
                  "Install akshare: pip install akshare",
         "hint": "For free A-share data, install akshare: pip install akshare"},
        "get_daily_quote"))]


async def handle_get_financial_report(args: dict) -> list[TextContent]:
    ts_code = args.get("ts_code", "")
    report_type = args.get("report_type", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response({"error": "ts_code is required"}, "get_financial_report"))]
    if not report_type:
        return [TextContent(type="text", text=_safe_json_response({"error": "report_type is required"}, "get_financial_report"))]

    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:  # token IS available
        try:
            pro = get_ts_pro()
            if pro is not None:
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
        except Exception as e:
            _log.warning(f"handle_get_financial_report: Tushare call failed: {e}")

    # Fallback to akshare
    fallback = _akshare_fallback(
        "financial_report",
        ts_code=ts_code,
        report_type=report_type,
    )
    if fallback:
        return [TextContent(type="text", text=json.dumps(fallback, ensure_ascii=False))]

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "Both Tushare and akshare unavailable. Install akshare: pip install akshare",
         "hint": "For free A-share financial data, install akshare: pip install akshare"},
        "get_financial_report"))]


async def handle_get_margin_data(args: dict) -> list[TextContent]:
    data_type = args.get("data_type", "")
    if not data_type:
        return [TextContent(type="text", text=_safe_json_response({"error": "data_type is required"}, "get_margin_data"))]

    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:  # token IS available
        try:
            pro = get_ts_pro()
            if pro is not None:
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
        except Exception as e:
            _log.warning(f"handle_get_margin_data: Tushare call failed: {e}")

    # Fallback to akshare
    ak_data_type = "hsgt" if data_type == "hsgt" else ("margin" if data_type == "margin" else "margin")
    fallback = _akshare_fallback(
        ak_data_type,
        ts_code=args.get("ts_code"),
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
    )
    if fallback:
        return [TextContent(type="text", text=json.dumps(fallback, ensure_ascii=False))]

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "Both Tushare and akshare unavailable. Install akshare: pip install akshare",
         "hint": "For free A-share margin data, install akshare: pip install akshare"},
        "get_margin_data"))]


async def handle_get_index_data(args: dict) -> list[TextContent]:
    if err := _check_token():
        return [TextContent(type="text", text=_safe_json_response(
            {"error": err, "hint": "Use akshare (user-financial MCP) as free fallback."}, "get_index_data"))]
    try:
        pro = get_ts_pro()
        if pro is None:
            return [TextContent(type="text", text=_safe_json_response(
                {"error": "TUSHARE_TOKEN not available"}, "get_index_data"))]
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
    if err := _check_token():
        return [TextContent(type="text", text=_safe_json_response(
            {"error": err, "hint": "Use akshare (user-financial MCP) as free fallback."}, "get_concept_stocks"))]
    try:
        pro = get_ts_pro()
        if pro is None:
            return [TextContent(type="text", text=_safe_json_response(
                {"error": "TUSHARE_TOKEN not available"}, "get_concept_stocks"))]
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
    if err := _check_token():
        return [TextContent(type="text", text=_safe_json_response(
            {"error": err, "hint": "Use akshare (user-financial MCP) as free fallback."}, "get_trade_calendar"))]
    try:
        pro = get_ts_pro()
        if pro is None:
            return [TextContent(type="text", text=_safe_json_response(
                {"error": "TUSHARE_TOKEN not available"}, "get_trade_calendar"))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_trade_calendar"))]
    result = _safe_call(pro, "trade_cal",
                         exchange=args.get("exchange"),
                         start_date=args.get("start_date"),
                         end_date=args.get("end_date"),
                         is_open=args.get("is_open"))
    return [TextContent(type="text", text=result)]


async def handle_get_institutional_holdings(args: dict) -> list[TextContent]:
    """Fetch institutional holdings data by holder type (QFII/fund/trust/broker/social_security)."""
    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response(
            {"error": "ts_code is required"}, "get_institutional_holdings"))]

    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:
        try:
            pro = get_ts_pro()
            if pro is not None:
                # Use top_holders as the primary Tushare API for institutional data
                # Filter by holder_type via holder_name keyword matching
                holder_type = args.get("holder_type", "all")
                ann_date = args.get("end_date") or None

                df = pro.top_holders(ts_code=ts_code, ann_date=ann_date)
                if df is not None and not df.empty:
                    if holder_type != "all":
                        type_keywords = {
                            "qfii": ["QFII", "合格境外", "RQFII"],
                            "fund": ["基金", "ETF", "公募基金", "华夏", "易方达", "嘉实", "南方", "博时", "广发"],
                            "trust": ["信托", "信托公司"],
                            "broker": ["券商", "证券", "经纪"],
                            "social_security": ["社保"],
                        }
                        keywords = type_keywords.get(holder_type, [])
                        if keywords:
                            mask = df["holder_name"].str.contains("|".join(keywords), na=False)
                            df = df[mask]

                    result = {
                        "result": {"data": df.to_dict(orient="records"),
                                   "count": len(df), "columns": list(df.columns)},
                        "success": True,
                        "source": "tushare",
                    }
                    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        except Exception as e:
            _log.warning(f"handle_get_institutional_holdings: Tushare call failed: {e}")

    # Fallback to akshare
    fallback = _akshare_fallback(
        "institutional_holdings",
        ts_code=ts_code,
        start_date=args.get("start_date", "20180101"),
        end_date=args.get("end_date"),
        holder_type=args.get("holder_type", "all"),
    )
    if fallback:
        return [TextContent(type="text", text=json.dumps(fallback, ensure_ascii=False))]

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "Both Tushare and akshare unavailable. Install akshare: pip install akshare",
         "hint": "Tushare Pro institutional holdings requires premium subscription. "
                 "akshare provides free institutional holding ratio data."},
        "get_institutional_holdings"))]


async def handle_get_top_holders(args: dict) -> list[TextContent]:
    """Fetch top-10 shareholders for a listed company."""
    ts_code = args.get("ts_code", "")
    if not ts_code:
        return [TextContent(type="text", text=_safe_json_response(
            {"error": "ts_code is required"}, "get_top_holders"))]

    # Try Tushare Pro first (only if token is available)
    token_err = _check_token()
    if token_err is None:
        try:
            pro = get_ts_pro()
            if pro is not None:
                ann_date = args.get("ann_date") or None
                df = pro.top_holders(ts_code=ts_code, ann_date=ann_date)
                if df is not None and not df.empty:
                    result = {
                        "result": {"data": df.to_dict(orient="records"),
                                   "count": len(df), "columns": list(df.columns)},
                        "success": True,
                        "source": "tushare",
                    }
                    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        except Exception as e:
            _log.warning(f"handle_get_top_holders: Tushare call failed: {e}")

    # Fallback to akshare
    fallback = _akshare_fallback("top_holders", ts_code=ts_code)
    if fallback:
        return [TextContent(type="text", text=json.dumps(fallback, ensure_ascii=False))]

    return [TextContent(type="text", text=_safe_json_response(
        {"error": "Both Tushare and akshare unavailable. Install akshare: pip install akshare",
         "hint": "Top holders data requires Tushare Pro or akshare (东方财富 source)."},
        "get_top_holders"))]


TOOL_HANDLERS = {
    "get_stock_basic": handle_get_stock_basic,
    "get_daily_quote": handle_get_daily_quote,
    "get_financial_report": handle_get_financial_report,
    "get_margin_data": handle_get_margin_data,
    "get_index_data": handle_get_index_data,
    "get_concept_stocks": handle_get_concept_stocks,
    "get_trade_calendar": handle_get_trade_calendar,
    "get_institutional_holdings": handle_get_institutional_holdings,
    "get_top_holders": handle_get_top_holders,
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
    print("user-tushare MCP Server starting...", file=sys.stderr, flush=True)

    # Check what data sources are available
    has_token = bool(os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_KEY", ""))
    if has_token:
        try:
            get_ts_pro()
            print("Tushare Pro connected successfully", flush=True)
        except Exception as e:
            print(f"Warning: Tushare Pro connection failed: {e}", flush=True)
            print("   Falling back to akshare (free) for A-share data.", flush=True)
    else:
        print("TUSHARE_TOKEN not set.", flush=True)
        if AKSHARE_AVAILABLE:
            print("   Using akshare (free) for A-share data as fallback.", flush=True)
        else:
            print("   WARNING: akshare not installed. Install with: pip install akshare", flush=True)
            print("   Tools will return errors until at least one data source is available.", flush=True)

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
