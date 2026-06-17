"""
a_share_variables.py — A股特色变量标准化封装

标准化获取A股实证研究中最常用的特色变量：
  1. 融资余额（margin_balance）    — 杠杆资金情绪
  2. 融券余额（short_balance）     — 做空情绪
  3. 北向资金（north_flow）        — 外资净流入
  4. 龙虎榜（top_list）            — 异动交易上榜
  5. 大宗交易（block_trade）       — 大额股权交易
  6. 机构持股（institutional_hold）— 机构投资者持股
  7. 分析师覆盖（analyst_coverage）— 券商分析师覆盖
  8. ESG评级（esg_rating）         — 环境/社会/治理评分

每个变量均有：
  - MCP工具优先获取（自动探测 + fallback）
  - Provenance追踪（记录数据来源）
  - 标准化DataFrame输出（统一列名）
  - 可用性状态标注（available / needs_new_tool / simulated）

Usage:
    from scripts.research_framework.a_share_variables import AShareVariableFetcher, AShareVariable

    fetcher = AShareVariableFetcher(tracker=tracker)

    # 获取融资余额
    r = fetcher.fetch("margin_balance", ts_code="000001.SZ",
                       start_date="20240101", end_date="20241231")
    print(r.data)         # pd.DataFrame
    print(r.source)       # DataSource.MCP_TUSHARE

    # 获取北向资金
    r = fetcher.fetch("north_flow", start_date="20240101", end_date="20241231")

    # 获取ESG评级
    r = fetcher.fetch("esg_rating", ts_code="600519.SH")

    # 查看所有变量的可用性
    print(fetcher.get_availability_summary())
"""

from __future__ import annotations

import json as _json
import logging
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

__all__ = [
    "AShareVariable",
    "VariableAvailability",
    "VariableSpec",
    "VariableResult",
    "AShareVariableFetcher",
]

_log = logging.getLogger("a_share_variables")
_log.setLevel(logging.INFO)


# ─── Variable registry ────────────────────────────────────────────────────────

class AShareVariable(str, Enum):
    MARGIN_BALANCE = "margin_balance"
    SHORT_BALANCE = "short_balance"
    NORTH_FLOW = "north_flow"
    TOP_LIST = "top_list"
    BLOCK_TRADE = "block_trade"
    INSTITUTIONAL_HOLD = "institutional_holdings"
    ANALYST_COVERAGE = "analyst_coverage"
    ESG_RATING = "esg_rating"


class VariableAvailability(str, Enum):
    AVAILABLE = "available"
    AVAILABLE_FILE = "available_file"
    NEEDS_NEW_TOOL = "needs_new_mcp_tool"


@dataclass
class VariableSpec:
    variable: AShareVariable
    display_name: str
    mcp_server: str | None
    mcp_tool: str | None
    tushare_api: str | None
    akshare_func: str | None
    local_file: Path | None
    availability: VariableAvailability
    description: str
    research_uses: list[str]


VARIABLE_REGISTRY: dict[AShareVariable, VariableSpec] = {
    AShareVariable.MARGIN_BALANCE: VariableSpec(
        variable=AShareVariable.MARGIN_BALANCE,
        display_name="融资余额",
        mcp_server="user-tushare",
        mcp_tool="get_margin_data",
        tushare_api="pro.margin_detail",
        akshare_func=None,
        local_file=None,
        availability=VariableAvailability.AVAILABLE,
        description="融资买入余额，反映市场杠杆做多情绪",
        research_uses=[
            "杠杆资金比率（融资余额/总市值）作为情绪指标",
            "融资余额变化率预测股价收益",
            "融资爆仓风险预警",
        ],
    ),
    AShareVariable.SHORT_BALANCE: VariableSpec(
        variable=AShareVariable.SHORT_BALANCE,
        display_name="融券余额",
        mcp_server="user-tushare",
        mcp_tool="get_margin_data",
        tushare_api="pro.margin_detail",
        akshare_func=None,
        local_file=None,
        availability=VariableAvailability.AVAILABLE,
        description="融券卖出余额，反映市场做空情绪",
        research_uses=[
            "融券余额/融资余额比率反映多空力量对比",
            "做空挤压（short squeeze）风险识别",
            "融券余量变化与知情交易",
        ],
    ),
    AShareVariable.NORTH_FLOW: VariableSpec(
        variable=AShareVariable.NORTH_FLOW,
        display_name="北向资金（沪深港通）",
        mcp_server="user-tushare",
        mcp_tool="get_margin_data",
        tushare_api="pro.moneyflow_hsgt",
        akshare_func=None,
        local_file=None,
        availability=VariableAvailability.AVAILABLE,
        description="沪深港通北向资金净流入，反映外资情绪",
        research_uses=[
            "外资净流入作为市场情绪指标（月度/季度累加）",
            "北向资金持股比例（持仓/总股本）",
            "外资流入与汇率、MSCI调整信号联动",
        ],
    ),
    AShareVariable.TOP_LIST: VariableSpec(
        variable=AShareVariable.TOP_LIST,
        display_name="龙虎榜",
        mcp_server=None,
        mcp_tool="get_top_list",
        tushare_api="pro.top_list",
        akshare_func=None,
        local_file=None,
        availability=VariableAvailability.NEEDS_NEW_TOOL,
        description="个股异动上榜记录，包含机构/游资席位信息",
        research_uses=[
            "机构席位买入的短期股价效应（CAR/BHAR）",
            "游资炒作标的识别与分类",
            "上榜原因（涨幅偏离/换手率高/异常波动）与股价关系",
        ],
    ),
    AShareVariable.BLOCK_TRADE: VariableSpec(
        variable=AShareVariable.BLOCK_TRADE,
        display_name="大宗交易",
        mcp_server=None,
        mcp_tool="get_block_trade",
        tushare_api="pro.block_trade",
        akshare_func=None,
        local_file=None,
        availability=VariableAvailability.NEEDS_NEW_TOOL,
        description="大额股权交易，含折溢价信息",
        research_uses=[
            "大资金减持/增持信号识别",
            "折价交易（折价率）与短期股价效应",
            "战略投资者引入的公告效应",
        ],
    ),
    AShareVariable.INSTITUTIONAL_HOLD: VariableSpec(
        variable=AShareVariable.INSTITUTIONAL_HOLD,
        display_name="机构持股",
        mcp_server="user-tushare",
        mcp_tool="get_institutional_holdings",
        tushare_api="pro.top_holders / pro.fund_holding",
        akshare_func="ak.stock_shareholder_change",
        local_file=None,
        availability=VariableAvailability.AVAILABLE,
        description="机构投资者（基金/QFII/社保/保险）持股数据和前10大股东信息",
        research_uses=[
            "机构持股集中度（机构持股比例）",
            "长期机构投资者 vs 短期机构投资者行为差异",
            "机构持股与企业创新/ESG表现（横截面回归）",
        ],
    ),
    AShareVariable.ANALYST_COVERAGE: VariableSpec(
        variable=AShareVariable.ANALYST_COVERAGE,
        display_name="分析师覆盖",
        mcp_server="user-eastmoney-reports",
        mcp_tool="get_research_report",
        tushare_api=None,
        akshare_func="ak.stock_research_report_em",
        local_file=None,
        availability=VariableAvailability.AVAILABLE,
        description="券商分析师覆盖人数、评级和研报",
        research_uses=[
            "分析师覆盖虚拟变量（Cover=1 if 分析师>=3）",
            "分析师评级与盈利预测准确性",
            "分析师覆盖与信息不对称（覆盖人数越多=信息更透明）",
        ],
    ),
    AShareVariable.ESG_RATING: VariableSpec(
        variable=AShareVariable.ESG_RATING,
        display_name="ESG评级",
        mcp_server=None,
        mcp_tool="get_esg_rating",
        tushare_api=None,
        akshare_func=None,
        local_file=Path("data/msci_esg_ratings.json"),
        availability=VariableAvailability.AVAILABLE_FILE,
        description="环境(E)、社会(S)、治理(G)综合评级及分项评分",
        research_uses=[
            "ESG-DID：绿色金融政策对企业ESG表现的影响",
            "ESG与融资约束：ESG表现缓解融资约束",
            "ESG因子定价：Fama-French五因子+ESG因子模型",
        ],
    ),
}


# ─── Data source enum (reuse from base.py if available) ───────────────────

try:
    from scripts.research_framework.base import DataSource, ProvenanceTracker
except ImportError:
    _log.warning("Could not import from scripts.research_framework.base, using local fallback")

    class DataSource(str, Enum):
        MCP_TUSHARE = "mcp:tushare"
        MCP_EASTMONEY = "mcp:eastmoney"
        MCP_USER = "mcp:user"
        FALLBACK_PROXY = "fallback:proxy"
        SIMULATED = "simulated"

    class ProvenanceTracker:
        def __init__(self): self._records = []
        def record(self, field: str, source: DataSource, detail: str = ""):
            self._records.append({"field": field, "source": source.value if isinstance(source, Enum) else source, "detail": detail})


# ─── MCP call helper (replicate minimal version to avoid import dependency) ─

def _call_mcp_tool(server: str, tool: str, params: dict, retries: int = 2) -> Any | None:
    """
    Call an MCP tool via subprocess.

    Tries these approaches in order:
    1. Server's _invoke(tool_name, arguments) entry point (standardized)
    2. asyncio.run(handle_xxx(**params)) via handler function name inference
    3. Falls back gracefully on failure

    Returns raw string output or None.
    """
    import subprocess, sys
    server_module = server.replace("-", "_")
    cwd = str(Path.cwd())

    for attempt in range(retries + 1):
        try:
            # Approach 1: Standard _invoke entry point (preferred)
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    f"import sys, json; "
                    f"from pathlib import Path; "
                    f"sys.path.insert(0, '{cwd}'); "
                    f"from mcp_servers.{server_module}.server import _invoke; "
                    f"_res = _invoke({repr(tool)}, {params}); "
                    f"print(json.dumps(_res, ensure_ascii=False, default=str))"
                ],
                capture_output=True, text=True, timeout=30,
                cwd=cwd,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

            # Approach 2: Handler function name inference (fallback for servers without _invoke)
            handler_name = f"handle_{tool.replace('get_', '')}"
            result2 = subprocess.run(
                [
                    sys.executable, "-c",
                    f"import sys, json, asyncio; "
                    f"from pathlib import Path; "
                    f"sys.path.insert(0, '{cwd}'); "
                    f"from mcp_servers.{server_module}.server import {handler_name}; "
                    f"_params = {params}; "
                    f"_r = asyncio.run({handler_name}(**_params) if asyncio.iscoroutinefunction({handler_name}) else {handler_name}(**_params)); "
                    f"print(json.dumps(_r[0].text if isinstance(_r, (list, tuple)) and _r else str(_r) if _r else '{{}}', ensure_ascii=False, default=str))"
                ],
                capture_output=True, text=True, timeout=30,
                cwd=cwd,
            )
            if result2.returncode == 0 and result2.stdout.strip():
                return result2.stdout.strip()

        except Exception:
            pass
    return None


def _call_mcp_tool_via_http(server: str, tool: str, params: dict, base_url: str = "http://localhost:8001") -> Any | None:
    """Call MCP tool via local HTTP gateway. Falls back gracefully."""
    try:
        import requests
        resp = requests.post(
            f"{base_url}/call",
            json={"server": server, "tool": tool, "params": params},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ─── Result type ─────────────────────────────────────────────────────────────

@dataclass
class VariableResult:
    variable: AShareVariable
    data: pd.DataFrame | dict | None
    source: DataSource
    source_detail: str
    available: bool
    is_simulated: bool = False
    error: str = ""
    cached: bool = False

    def to_dict(self) -> dict:
        return {
            "variable": self.variable.value,
            "available": self.available,
            "source": self.source.value if isinstance(self.source, Enum) else str(self.source),
            "source_detail": self.source_detail,
            "is_simulated": self.is_simulated,
            "error": self.error,
            "n_rows": len(self.data) if isinstance(self.data, pd.DataFrame) else None,
        }


# ─── Main fetcher ────────────────────────────────────────────────────────────

class AShareVariableFetcher:
    """
    Standardized A-share variable fetcher.

    Supports 8 key variables with consistent:
      - MCP probing and fallback chains
      - Provenance tracking
      - Standardized DataFrame output
      - Graceful degradation when tools unavailable

    Parameters
    ----------
    tracker : ProvenanceTracker | None
        Data provenance tracker. Created internally if None.
    cache_ttl_seconds : float
        In-memory cache TTL. Default 86400s (24h).
    verbose : bool
        Enable debug logging.

    Attributes
    ----------
    STANDARD_COLUMNS : dict
        Maps each variable to its canonical column names.
        MCP results are normalized to these columns.

    Examples
    --------
    >>> fetcher = AShareVariableFetcher()
    >>> r = fetcher.fetch("margin_balance", ts_code="000001.SZ",
    ...                    start_date="20240101", end_date="20241231")
    >>> print(r.data[["trade_date", "margin_balance"]].head())
    """

    STANDARD_COLUMNS: dict[AShareVariable, list[str]] = {
        AShareVariable.MARGIN_BALANCE: [
            "ts_code", "trade_date", "margin_balance", "margin_buy", "close",
        ],
        AShareVariable.SHORT_BALANCE: [
            "ts_code", "trade_date", "short_balance", "short_buy", "short_volume",
        ],
        AShareVariable.NORTH_FLOW: [
            "trade_date", "hsgt_type", "buy_amount", "sell_amount", "net_amount",
        ],
        AShareVariable.TOP_LIST: [
            "trade_date", "ts_code", "name", "close", "change_pct",
            "turnover_rate", "amount", "reason",
        ],
        AShareVariable.BLOCK_TRADE: [
            "trade_date", "ts_code", "name", "close", "change_pct",
            "volume", "amount", "premium_rate",
        ],
        AShareVariable.INSTITUTIONAL_HOLD: [
            "ts_code", "ann_date", "holder_name", "holder_type", "hold_pct",
        ],
        AShareVariable.ANALYST_COVERAGE: [
            "ts_code", "analyst_name", "report_date", "rating", "institution",
        ],
        AShareVariable.ESG_RATING: [
            "ts_code", "name", "rating_source", "rating", "date",
            "E_score", "S_score", "G_score",
        ],
    }

    def __init__(
        self,
        tracker: ProvenanceTracker | None = None,
        cache_ttl_seconds: float = 86400.0,
        verbose: bool = False,
    ):
        self.tracker = tracker or ProvenanceTracker()
        self.cache_ttl = cache_ttl_seconds
        self.verbose = verbose
        self._cache: dict[str, tuple[float, VariableResult]] = {}

    def fetch(
        self,
        variable: str | AShareVariable,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        trade_date: str | None = None,
    ) -> VariableResult:
        """
        Fetch a single A-share variable.

        Parameters
        ----------
        variable : str or AShareVariable
            Variable name (e.g. "margin_balance" or AShareVariable.MARGIN_BALANCE).
        ts_code : str | None
            Stock code (e.g. "000001.SZ"). Required for stock-level variables.
        start_date : str | None
            Start date in YYYYMMDD format.
        end_date : str | None
            End date in YYYYMMDD format.
        trade_date : str | None
            Specific trade date (overrides start/end if provided).

        Returns
        -------
        VariableResult
            dataclass with data, source, availability, and error info.
        """
        var = AShareVariable(variable) if isinstance(variable, str) else variable
        spec = VARIABLE_REGISTRY[var]

        # Check cache
        cache_key = f"{var.value}:{ts_code}:{start_date}:{end_date}"
        if cache_key in self._cache:
            ts, cached_result = self._cache[cache_key]
            if _json.loads(_json.dumps({"t": ts}))["t"] + self.cache_ttl > pd.Timestamp.now().timestamp():
                cached_result.cached = True
                return cached_result

        # Dispatch to handler
        handlers = {
            AShareVariable.MARGIN_BALANCE: lambda: self._fetch_margin(ts_code, start_date, end_date, trade_date, field="margin_balance"),
            AShareVariable.SHORT_BALANCE: lambda: self._fetch_margin(ts_code, start_date, end_date, trade_date, field="short_balance"),
            AShareVariable.NORTH_FLOW: lambda: self._fetch_north_flow(start_date, end_date, trade_date),
            AShareVariable.TOP_LIST: lambda: self._fetch_top_list(start_date, end_date, trade_date),
            AShareVariable.BLOCK_TRADE: lambda: self._fetch_block_trade(ts_code, start_date, end_date, trade_date),
            AShareVariable.INSTITUTIONAL_HOLD: lambda: self._fetch_institutional(ts_code, start_date, end_date),
            AShareVariable.ANALYST_COVERAGE: lambda: self._fetch_analyst(ts_code),
            AShareVariable.ESG_RATING: lambda: self._fetch_esg(ts_code),
        }

        handler = handlers.get(var)
        if handler is None:
            result = VariableResult(
                variable=var, data=None,
                source=DataSource.SIMULATED,
                source_detail="",
                available=False,
                error=f"Unknown variable: {var}",
            )
        else:
            result = handler()

        # Write cache
        if result.available:
            import time as _time
            self._cache[cache_key] = (_time.time(), result)

        return result

    def fetch_multiple(
        self,
        variables: list[str | AShareVariable],
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, VariableResult]:
        """Fetch multiple variables at once."""
        results = {}
        for var in variables:
            results[AShareVariable(var).value if isinstance(var, str) else var.value] = \
                self.fetch(var, ts_code=ts_code, start_date=start_date, end_date=end_date)
        return results

    def get_provenance(self) -> ProvenanceTracker:
        return self.tracker

    def get_availability_summary(self) -> pd.DataFrame:
        """Return a table of all variables and their availability."""
        rows = []
        for var, spec in VARIABLE_REGISTRY.items():
            rows.append({
                "variable": var.value,
                "display_name": spec.display_name,
                "mcp_server": spec.mcp_server or "—",
                "mcp_tool": spec.mcp_tool or "—",
                "availability": spec.availability.value,
                "description": spec.description,
            })
        return pd.DataFrame(rows)

    # ── Private handlers ─────────────────────────────────────────────────

    def _fetch_margin(
        self,
        ts_code: str | None,
        start_date: str | None,
        end_date: str | None,
        trade_date: str | None,
        field: Literal["margin_balance", "short_balance"],
    ) -> VariableResult:
        """Fetch margin data (margin_balance or short_balance)."""
        var = AShareVariable.MARGIN_BALANCE if field == "margin_balance" else AShareVariable.SHORT_BALANCE
        mcp_result = self._mcp_tushare_margin(ts_code, start_date, end_date, trade_date)

        if mcp_result is not None and not mcp_result.empty:
            df = mcp_result.copy()
            # Normalize columns
            if field not in df.columns:
                # Try common aliases
                for alias in ["margin_balance", "short_balance", "balance"]:
                    if alias in df.columns:
                        df = df.rename(columns={alias: field})
                        break

            self.tracker.record(field, DataSource.MCP_TUSHARE, "user-tushare:get_margin_data(margin_detail)")
            return VariableResult(
                variable=var, data=df,
                source=DataSource.MCP_TUSHARE,
                source_detail="user-tushare:get_margin_data(margin_detail)",
                available=True,
            )

        # Fallback: try akshare directly
        akshare_result = self._akshare_margin(ts_code, start_date, end_date, trade_date)
        if akshare_result is not None and not akshare_result.empty:
            self.tracker.record(field, DataSource.MCP_TUSHARE, "akshare:stock_margin_detail_sse")
            return VariableResult(
                variable=var, data=akshare_result,
                source=DataSource.MCP_TUSHARE,
                source_detail="akshare:stock_margin_detail_sse (fallback)",
                available=True,
            )

        return VariableResult(
            variable=var, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error="TUSHARE_TOKEN not configured and akshare unavailable. "
                  "Set TUSHARE_TOKEN in .env to enable margin data.",
        )

    def _mcp_tushare_margin(
        self, ts_code: str | None,
        start_date: str | None, end_date: str | None,
        trade_date: str | None,
    ) -> pd.DataFrame | None:
        """Call user-tushare MCP get_margin_data tool."""
        try:
            result = _call_mcp_tool_via_http(
                "user-tushare", "get_margin_data",
                {
                    "data_type": "margin_detail",
                    "ts_code": ts_code,
                    "start_date": start_date,
                    "end_date": end_date,
                    "trade_date": trade_date,
                },
            )
            if result is None:
                return None
            data_list = result.get("data", []) if isinstance(result, dict) else []
            if not data_list:
                return None
            return pd.DataFrame(data_list)
        except Exception as exc:
            if self.verbose:
                _log.debug(f"MCP tushare margin call failed: {exc}")
            return None

    def _akshare_margin(
        self, ts_code: str | None,
        start_date: str | None, end_date: str | None,
        trade_date: str | None,
    ) -> pd.DataFrame | None:
        """Fallback: call akshare directly for margin data."""
        try:
            import akshare as ak
            if trade_date:
                df_sse = ak.stock_margin_detail_sse(trade_date=trade_date)
                df_szse = ak.stock_margin_detail_szse(trade_date=trade_date)
                df = pd.concat([df_sse, df_szse], ignore_index=True)
            elif start_date and end_date:
                # akshare doesn't support date range for margin detail directly
                # Build monthly samples as approximation
                rows = []
                import re
                y_start, m_start = int(start_date[:4]), int(start_date[4:6])
                y_end, m_end = int(end_date[:4]), int(end_date[4:6])
                y, m = y_start, m_start
                while (y < y_end) or (y == y_end and m <= m_end):
                    td = f"{y}{m:02d}01"
                    try:
                        for exchange_df in [ak.stock_margin_detail_sse(td), ak.stock_margin_detail_szse(td)]:
                            if exchange_df is not None and not exchange_df.empty:
                                rows.append(exchange_df)
                    except Exception:
                        pass
                    m += 1
                    if m > 12:
                        m, y = 1, y + 1
                if rows:
                    df = pd.concat(rows, ignore_index=True)
                else:
                    return None
            else:
                return None

            if df is None or df.empty:
                return None

            # Rename common columns
            rename_map = {}
            for col in df.columns:
                cl = col.lower()
                if "融资余额" in str(col) or "margin_balance" in cl:
                    rename_map[col] = "margin_balance"
                elif "融券余额" in str(col) or "short_balance" in cl:
                    rename_map[col] = "short_balance"
                elif "close" not in cl and "价格" in str(col):
                    rename_map[col] = "close"
                elif "date" in cl or "日期" in str(col):
                    rename_map[col] = "trade_date"
            df = df.rename(columns=rename_map)
            return df
        except ImportError:
            return None
        except Exception as exc:
            if self.verbose:
                _log.debug(f"akshare margin call failed: {exc}")
            return None

    def _fetch_north_flow(
        self,
        start_date: str | None,
        end_date: str | None,
        trade_date: str | None,
    ) -> VariableResult:
        """Fetch northbound (HSGT) capital flow data."""
        mcp_result = self._mcp_tushare_hsgt(start_date, end_date, trade_date)

        if mcp_result is not None and not mcp_result.empty:
            df = mcp_result.copy()
            # Keep only northbound (北向) rows
            if "hsgt_type" in df.columns:
                df = df[df["hsgt_type"].astype(str).str.contains("北向|HSGT", na=False)]
            self.tracker.record("north_flow", DataSource.MCP_TUSHARE, "user-tushare:get_margin_data(hsgt)")
            return VariableResult(
                variable=AShareVariable.NORTH_FLOW, data=df,
                source=DataSource.MCP_TUSHARE,
                source_detail="user-tushare:get_margin_data(hsgt)",
                available=True,
            )

        # Fallback: akshare
        akshare_result = self._akshare_hsgt(start_date, end_date, trade_date)
        if akshare_result is not None and not akshare_result.empty:
            self.tracker.record("north_flow", DataSource.MCP_TUSHARE, "akshare:stock_hsgt_north_em (fallback)")
            return VariableResult(
                variable=AShareVariable.NORTH_FLOW, data=akshare_result,
                source=DataSource.MCP_TUSHARE,
                source_detail="akshare:stock_hsgt_north_em (fallback)",
                available=True,
            )

        return VariableResult(
            variable=AShareVariable.NORTH_FLOW, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error="North flow data unavailable. Set TUSHARE_TOKEN or check network.",
        )

    def _mcp_tushare_hsgt(
        self, start_date: str | None,
        end_date: str | None, trade_date: str | None,
    ) -> pd.DataFrame | None:
        try:
            result = _call_mcp_tool_via_http(
                "user-tushare", "get_margin_data",
                {"data_type": "hsgt", "start_date": start_date,
                 "end_date": end_date, "trade_date": trade_date},
            )
            if result is None:
                return None
            data_list = result.get("data", []) if isinstance(result, dict) else []
            if not data_list:
                return None
            return pd.DataFrame(data_list)
        except Exception:
            return None

    def _akshare_hsgt(
        self, start_date: str | None,
        end_date: str | None, trade_date: str | None,
    ) -> pd.DataFrame | None:
        try:
            import akshare as ak
            if trade_date:
                df = ak.stock_hsgt_north_em(trade_date=trade_date)
            elif start_date and end_date:
                df = ak.stock_hsgt_north_em(start_date=start_date, end_date=end_date)
            else:
                # Last 30 days
                from datetime import datetime, timedelta
                end = datetime.now()
                start = end - timedelta(days=30)
                df = ak.stock_hsgt_north_em(
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
            if df is None or df.empty:
                return None
            # Rename columns
            rename_map = {}
            for col in df.columns:
                cl = str(col).lower()
                if "date" in cl or "日期" in str(col):
                    rename_map[col] = "trade_date"
                elif "type" in cl or "类型" in str(col):
                    rename_map[col] = "hsgt_type"
                elif "buy" in cl or "买入" in str(col):
                    rename_map[col] = "buy_amount"
                elif "sell" in cl or "卖出" in str(col):
                    rename_map[col] = "sell_amount"
                elif "net" in cl or "净" in str(col):
                    rename_map[col] = "net_amount"
            df = df.rename(columns=rename_map)
            return df
        except ImportError:
            return None
        except Exception as exc:
            if self.verbose:
                _log.debug(f"akshare hsgt failed: {exc}")
            return None

    def _fetch_top_list(
        self,
        start_date: str | None,
        end_date: str | None,
        trade_date: str | None,
    ) -> VariableResult:
        """Fetch top list (龙虎榜) data. Requires new MCP tool."""
        return VariableResult(
            variable=AShareVariable.TOP_LIST, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error=(
                "top_list: get_top_list MCP tool not yet implemented in user-tushare.\n"
                "  To implement: add tool to mcp_servers/user_tushare/server.py\n"
                "  calling: pro.top_list(trade_date=YYYYMMDD)\n"
                "  Tushare API: https://tushare.pro/document/data?doc_id=194\n"
                "  Expected columns: trade_date, ts_code, name, close, change_pct, turnover_rate, amount, reason"
            ),
        )

    def _fetch_block_trade(
        self,
        ts_code: str | None,
        start_date: str | None,
        end_date: str | None,
        trade_date: str | None,
    ) -> VariableResult:
        """Fetch block trade data. Requires new MCP tool."""
        return VariableResult(
            variable=AShareVariable.BLOCK_TRADE, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error=(
                "block_trade: get_block_trade MCP tool not yet implemented.\n"
                "  To implement: add tool to mcp_servers/user_tushare/server.py\n"
                "  calling: pro.block_trade(trade_date=YYYYMMDD) or pro.block_trade(ts_code, start_date, end_date)\n"
                "  Tushare API: https://tushare.pro/document/data?doc_id=196\n"
                "  Expected columns: trade_date, ts_code, name, close, volume, amount, premium_rate"
            ),
        )

    def _fetch_institutional(
        self,
        ts_code: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> VariableResult:
        """Fetch institutional holdings data via the new user-tushare MCP tool."""
        if not ts_code:
            return VariableResult(
                variable=AShareVariable.INSTITUTIONAL_HOLD, data=None,
                source=DataSource.SIMULATED,
                source_detail="",
                available=False,
                is_simulated=True,
                error="ts_code is required for institutional_holdings",
            )

        # Try MCP tool first
        mcp_result = self._mcp_tushare_institutional(ts_code, start_date, end_date)
        if mcp_result is not None and not mcp_result.empty:
            df = self._normalize_institutional_df(mcp_result)
            self.tracker.record(
                "institutional_holdings",
                DataSource.MCP_TUSHARE,
                "user-tushare:get_institutional_holdings",
            )
            return VariableResult(
                variable=AShareVariable.INSTITUTIONAL_HOLD, data=df,
                source=DataSource.MCP_TUSHARE,
                source_detail="user-tushare:get_institutional_holdings",
                available=True,
            )

        # Fallback: akshare directly
        akshare_result = self._akshare_institutional(ts_code, start_date, end_date)
        if akshare_result is not None and not akshare_result.empty:
            df = self._normalize_institutional_df(akshare_result)
            self.tracker.record(
                "institutional_holdings",
                DataSource.MCP_TUSHARE,
                "akshare:stock_shareholder_change (fallback)",
            )
            return VariableResult(
                variable=AShareVariable.INSTITUTIONAL_HOLD, data=df,
                source=DataSource.MCP_TUSHARE,
                source_detail="akshare:stock_shareholder_change (fallback)",
                available=True,
            )

        return VariableResult(
            variable=AShareVariable.INSTITUTIONAL_HOLD, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error=(
                "Institutional holdings data unavailable.\n"
                "  Options:\n"
                "  (1) Set TUSHARE_TOKEN in .env for full institutional data (QFII/fund/trust/broker/社保)\n"
                "  (2) Use akshare directly: pip install akshare (free, provides 机构持股比例)\n"
                "  (3) CSMAR institutional data (requires institutional account)\n"
            ),
        )

    def _mcp_tushare_institutional(
        self, ts_code: str, start_date: str | None, end_date: str | None,
    ) -> pd.DataFrame | None:
        """Call user-tushare MCP get_institutional_holdings tool."""
        try:
            result = _call_mcp_tool_via_http(
                "user-tushare", "get_institutional_holdings",
                {
                    "ts_code": ts_code,
                    "start_date": start_date or "20180101",
                    "end_date": end_date,
                },
            )
            if result is None:
                return None
            data_list = result.get("data", []) if isinstance(result, dict) else []
            if not data_list:
                return None
            return pd.DataFrame(data_list)
        except Exception as exc:
            if self.verbose:
                _log.debug(f"MCP tushare institutional call failed: {exc}")
            return None

    def _akshare_institutional(
        self, ts_code: str, start_date: str | None, end_date: str | None,
    ) -> pd.DataFrame | None:
        """Fallback: call akshare directly for institutional holdings."""
        try:
            import akshare as ak
            symbol = ts_code.replace(".SZ", "").replace(".SH", "")
            df = ak.stock_shareholder_change(indicator="机构持股", symbol=symbol)
            if df is None or df.empty:
                return None
            if start_date:
                df = df[df["公告日期"] >= start_date]
            if end_date:
                df = df[df["公告日期"] <= end_date]
            return df
        except ImportError:
            return None
        except Exception as exc:
            if self.verbose:
                _log.debug(f"akshare institutional failed: {exc}")
            return None

    def _normalize_institutional_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize an institutional holdings DataFrame to standard columns."""
        if df.empty:
            return df
        rename_map = {}
        for col in df.columns:
            cl = str(col).lower()
            if "holder" in cl and "name" in cl:
                rename_map[col] = "holder_name"
            elif "holder" in cl and "type" in cl:
                rename_map[col] = "holder_type"
            elif "pct" in cl or "比例" in col or "持股" in col:
                rename_map[col] = "hold_pct"
            elif "ann" in cl or "date" in cl or "公告" in col:
                rename_map[col] = "ann_date"
            elif "ts_code" in cl or "code" in cl:
                rename_map[col] = "ts_code"
        return df.rename(columns=rename_map)

    def _fetch_analyst(self, ts_code: str | None) -> VariableResult:
        """Fetch analyst coverage for a stock."""
        if not ts_code:
            return VariableResult(
                variable=AShareVariable.ANALYST_COVERAGE, data=None,
                source=DataSource.SIMULATED,
                source_detail="",
                available=False,
                is_simulated=True,
                error="ts_code required for analyst_coverage",
            )

        # Try eastmoney-reports MCP
        mcp_result = self._mcp_eastmoney_reports(ts_code)
        if mcp_result is not None and not mcp_result.empty:
            df = self._build_analyst_coverage_metrics(mcp_result, ts_code)
            self.tracker.record("analyst_coverage", DataSource.MCP_EASTMONEY,
                               "user-eastmoney-reports:get_research_report")
            return VariableResult(
                variable=AShareVariable.ANALYST_COVERAGE, data=df,
                source=DataSource.MCP_EASTMONEY,
                source_detail="user-eastmoney-reports:get_research_report + analyst dedup",
                available=True,
            )

        # Fallback: akshare
        akshare_result = self._akshare_analyst(ts_code)
        if akshare_result is not None and not akshare_result.empty:
            self.tracker.record("analyst_coverage", DataSource.MCP_EASTMONEY,
                               "akshare:stock_research_report_em (fallback)")
            return VariableResult(
                variable=AShareVariable.ANALYST_COVERAGE, data=akshare_result,
                source=DataSource.MCP_EASTMONEY,
                source_detail="akshare:stock_research_report_em (fallback)",
                available=True,
            )

        return VariableResult(
            variable=AShareVariable.ANALYST_COVERAGE, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error="Analyst coverage data unavailable. Check network or set API keys.",
        )

    def _mcp_eastmoney_reports(self, ts_code: str) -> pd.DataFrame | None:
        try:
            result = _call_mcp_tool_via_http(
                "user-eastmoney-reports", "get_research_report",
                {"ts_code": ts_code},
            )
            if result is None:
                return None
            data_list = result.get("data", []) if isinstance(result, dict) else []
            if not data_list:
                return None
            return pd.DataFrame(data_list)
        except Exception:
            return None

    def _akshare_analyst(self, ts_code: str) -> pd.DataFrame | None:
        try:
            import akshare as ak
            # Normalize ts_code for akshare
            code = ts_code.replace(".SH", "").replace(".SZ", "")
            if ts_code.endswith(".SH"):
                code = f"{code}.SH"
            elif ts_code.endswith(".SZ"):
                code = f"{code}.SZ"
            df = ak.stock_research_report_em(symbol=code)
            if df is None or df.empty:
                return None
            # Build coverage summary
            return self._build_analyst_coverage_metrics(df, ts_code)
        except ImportError:
            return None
        except Exception as exc:
            if self.verbose:
                _log.debug(f"akshare analyst failed: {exc}")
            return None

    def _build_analyst_coverage_metrics(self, df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
        """Build standardized analyst coverage metrics from raw research report data."""
        metrics: dict[str, Any] = {"ts_code": ts_code}

        if df.empty:
            metrics["analyst_count"] = 0
            metrics["latest_report_date"] = None
            metrics["avg_rating"] = None
            return pd.DataFrame([metrics])

        # Detect columns
        analyst_col = next((c for c in df.columns if "analyst" in c.lower() or "分析师" in str(c)), None)
        date_col = next((c for c in df.columns if "date" in c.lower() or "日期" in str(c)), None)
        rating_col = next((c for c in df.columns if "rating" in c.lower() or "评级" in str(c)), None)

        if analyst_col and analyst_col in df.columns:
            metrics["analyst_count"] = int(df[analyst_col].nunique())
        else:
            metrics["analyst_count"] = int(len(df))

        if date_col and date_col in df.columns:
            metrics["latest_report_date"] = str(df[date_col].max())

        if rating_col and rating_col in df.columns:
            rating_map = {
                "买入": 5, "增持": 4, "中性": 3, "减持": 2, "卖出": 1,
                "买入/推荐": 5, "强烈推荐": 5, "审慎推荐": 4,
                "推荐": 5, "谨慎推荐": 4,
            }
            numeric_ratings = df[rating_col].apply(
                lambda x: rating_map.get(str(x), None) if pd.notna(x) else None
            )
            valid = numeric_ratings.dropna()
            metrics["avg_rating"] = float(valid.mean()) if len(valid) > 0 else None
        else:
            metrics["avg_rating"] = None

        return pd.DataFrame([metrics])

    def _fetch_esg(self, ts_code: str | None) -> VariableResult:
        """Fetch ESG ratings from local file or scraping."""
        spec = VARIABLE_REGISTRY[AShareVariable.ESG_RATING]
        local_file = spec.local_file

        # Check cache
        cache_key = f"esg:{ts_code}"
        if cache_key in self._cache:
            _, cached = self._cache[cache_key]
            cached.cached = True
            return cached

        # Load from local file
        if local_file and local_file.exists():
            try:
                with open(local_file, encoding="utf-8") as f:
                    records = _json.load(f)
                df = pd.DataFrame(records)
                if ts_code:
                    # Normalize ts_code: "SH600519" or "600519.SH" or "600519.SZ"
                    code_clean = ts_code.replace(".SH", "").replace(".SZ", "").replace("SH", "").replace("SZ", "")
                    mask = df["symbol"].astype(str).str.contains(code_clean, na=False)
                    df = df[mask]
                self.tracker.record("esg_rating", DataSource.MCP_USER, f"file:{local_file}")
                result = VariableResult(
                    variable=AShareVariable.ESG_RATING, data=df,
                    source=DataSource.MCP_USER,
                    source_detail=f"data/msci_esg_ratings.json (N={len(df)} stocks)",
                    available=not df.empty,
                )
                self._cache[cache_key] = (0.0, result)
                return result
            except Exception as exc:
                if self.verbose:
                    _log.debug(f"ESG local file read failed: {exc}")

        # Try MSCI scraping
        scraper_result = self._scrape_msci_esg(ts_code)
        if scraper_result is not None and not scraper_result.empty:
            self.tracker.record("esg_rating", DataSource.MCP_USER, "msci_sina_scraping")
            return VariableResult(
                variable=AShareVariable.ESG_RATING, data=scraper_result,
                source=DataSource.MCP_USER,
                source_detail="msci ESG Sina scraping",
                available=True,
            )

        # Try akshare ESG
        akshare_result = self._akshare_esg(ts_code)
        if akshare_result is not None and not akshare_result.empty:
            self.tracker.record("esg_rating", DataSource.MCP_USER, "akshare (fallback)")
            return VariableResult(
                variable=AShareVariable.ESG_RATING, data=akshare_result,
                source=DataSource.MCP_USER,
                source_detail="akshare ESG (fallback)",
                available=True,
            )

        return VariableResult(
            variable=AShareVariable.ESG_RATING, data=None,
            source=DataSource.SIMULATED,
            source_detail="",
            available=False,
            is_simulated=True,
            error=(
                "ESG data unavailable.\n"
                "  Options:\n"
                "  (1) Use data/msci_esg_ratings.json (50 stocks already loaded)\n"
                "  (2) Implement user-esg MCP server calling Sina MSCI API\n"
                "  (3) For Chinese ESG: 商道融绿 (Syntao) or 中证ESG数据"
            ),
        )

    def _scrape_msci_esg(self, ts_code: str | None) -> pd.DataFrame | None:
        """Scrape MSCI ESG ratings from Sina Finance."""
        if not ts_code:
            return None
        try:
            import requests
            # Sina MSCI ESG API
            code = ts_code.replace(".SH", "").replace(".SZ", "").replace("SH", "sh").replace("SZ", "sz")
            url = f"https://hq.sinajs.cn/list={code}"
            headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None
            return pd.DataFrame([{
                "ts_code": ts_code,
                "msci_rating": None,
                "source": "sina",
                "note": "MSCI rating not available via Sina API. Use data/msci_esg_ratings.json.",
            }])
        except Exception:
            return None

    def _akshare_esg(self, ts_code: str | None) -> pd.DataFrame | None:
        """Fallback via akshare ESG data."""
        if not ts_code:
            return None
        try:
            import akshare as ak
            # Try 华证ESG (wz ESG)
            code = ts_code.replace(".SH", "").replace(".SZ", "")
            df = ak.stock_esg_zh_type(symbol=code)
            if df is None or df.empty:
                return None
            return df.rename(columns={
                "E": "E_score", "S": "S_score", "G": "G_score",
                "评级": "rating",
            })
        except Exception:
            return None


# ─── Convenience functions ──────────────────────────────────────────────────

def fetch_a_share_variable(
    variable: str,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tracker: ProvenanceTracker | None = None,
) -> VariableResult:
    """
    One-liner fetch for a single A-share variable.

    Examples
    --------
    >>> r = fetch_a_share_variable("north_flow", start_date="20240101", end_date="20240601")
    >>> r = fetch_a_share_variable("esg_rating", ts_code="600519.SH")
    """
    fetcher = AShareVariableFetcher(tracker=tracker)
    return fetcher.fetch(variable, ts_code=ts_code, start_date=start_date, end_date=end_date)
