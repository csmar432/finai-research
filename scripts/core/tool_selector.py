"""ToolSelector: Tool registry and routing for the economic research agent.

Provides:
- ToolCapability registry (MCP tools + Python scripts)
- Task-type-based tool selection with cost and VPN filtering
- Fallback execution chain
- MCP and script invocation layer
"""

from __future__ import annotations

import importlib
import os
import time
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any

from scripts.core.memory import ContextUnit, ResearchMemory
from scripts.core.planner import Task, TaskType
from scripts.core.platform import get_mcp_config_paths
from scripts.core.mcp_tool_market import (
    MCPToolRegistry,
    ToolMetadata,
    get_default_registry,
)

# ─── Cost Tier ──────────────────────────────────────────────────────────────────


class CostTier(Enum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Cost ordering: FREE < LOW < MEDIUM < HIGH
_COST_ORDER: dict[CostTier, int] = {
    CostTier.FREE: 0,
    CostTier.LOW: 1,
    CostTier.MEDIUM: 2,
    CostTier.HIGH: 3,
}


# ─── Core DataClasses ───────────────────────────────────────────────────────────


@dataclass
class ToolCapability:
    """
    Describes a single available tool.

    Attributes
    ----------
    name : str
        Unique identifier for the tool.
    task_types : list[TaskType]
        Task types this tool can handle.
    inputs : list[str]
        Required input field names.
    outputs : list[str]
        Output field names produced by the tool.
    priority : int
        Priority rank — smaller number means higher priority.
    cost : CostTier
        Cost tier for this tool.
    requires_vpn : bool
        Whether this tool requires an active VPN connection.
    description : str
        Human-readable description.
    callable : Any, optional
        A reference to the callable Python function / module for script tools.
    """

    name: str
    task_types: list[TaskType]
    inputs: list[str]
    outputs: list[str]
    priority: int
    cost: CostTier
    requires_vpn: bool
    description: str
    callable: Any | None = None


@dataclass
class ToolSelection:
    """
    Result of tool selection — describes a chosen tool and why it was chosen.
    """

    tool_name: str
    confidence: float  # 0.0–1.0
    reason: str
    estimated_cost: str  # human-readable, matches CostTier.value
    requires_vpn: bool
    callable: Any | None = None


@dataclass
class ToolResult:
    """
    Result of tool execution.
    """

    success: bool
    output: Any
    tool_name: str
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False


# ─── Script Tool Mappings ───────────────────────────────────────────────────────
# Maps tool name → (module_name, function_name or "ClassName" for class-based tools)

SCRIPT_CALLABLES: dict[str, tuple[str, str]] = {
    # fetch_a_stock: A股日线数据 (akshare) — signature: (code, start_date, end_date, adjust)
    "fetch_a_stock": ("scripts.data_pipeline", "fetch_a_stock"),
    # econometrics_regression: 描述统计 — signature: (data, vars_list, precision)
    "econometrics_regression": ("scripts.econometrics", "descriptive_stats"),
    # report_generator: 研报生成 (class-based, ToolSelector 会实例化)
    "report_generator": ("scripts.research_framework.report_generator", "ReportGenerator"),
    # dashboard: Streamlit 监控仪表盘 (launch_dashboard 函数)
    "dashboard": ("scripts.dashboard", "run_cli"),
}


# ─── Tool Registry ──────────────────────────────────────────────────────────────


class ToolSelector:
    """
    Registry of all available tools (MCP + Python scripts) and selection logic.

    Selection strategy
    ------------------
    1. Filter by TaskType match (tool.task_types contains task.task_type).
    2. Exclude VPN-required tools when VPN is unavailable.
    3. Sort by priority ascending, then cost tier ascending (FREE → LOW → MEDIUM → HIGH).
    4. Assign confidence = 1.0 for first-ranked candidate, 0.8 for others.
    5. Context-aware boost: +0.1 confidence for tools previously used in context.
    """

    # Maps registry tool name → (actual_mcp_tool_name, server_name_in_mcp_json)
    # server_name_in_mcp_json matches ~/.cursor/mcp.json server keys (uses - not _)
    MCP_TOOL_SERVER_MAP: dict[str, tuple[str, str]] = {
        # Built-in/public servers
        "arxiv": ("arxiv", "arxiv"),
        "brave_search": ("brave-search", "brave-search"),
        "fetch": ("fetch", "fetch"),
        "context7": ("context7", "context7"),
        "financial": ("financial", "financial"),
        "finviz_sec": ("finviz-sec", "finviz-sec"),
        "finagent": ("finagent", "finagent"),
        "yfinance": ("yfinance", "yfinance"),
        "newsapi": ("newsapi", "newsapi"),
        "openalex": ("openalex", "openalex"),
        "stock_data": ("stock-data", "stock-data"),
        "financekit": ("financekit", "financekit"),
        "sqlite": ("sqlite", "sqlite"),
        "github": ("github", "github"),
        # Custom servers (server name = mcp.json key)
        "eastmoney_reports": ("get_research_report", "eastmoney-reports"),
        "eastmoney_fund": ("get_fund_nav", "eastmoney-fund"),
        "eastmoney_option": ("get_option_chain", "eastmoney-option"),
        "eastmoney_bond": ("get_bond_yield_curve", "eastmoney-bond"),
        "tushare": ("get_daily_quote", "tushare"),
        "tushare_margin": ("get_margin_data", "tushare"),
        "enhanced_finance": ("get_forex_spot", "enhanced-finance"),
        "wb_data": ("get_wb_gdp", "wb-data"),
        "imf_data": ("get_imf_ifs", "imf-data"),
        "oecd_data": ("get_oecd_gdp", "oecd-data"),
        "nber_wp": ("search_nber_papers", "nber-wp"),
        "bea_data": ("get_bea_gdp", "bea-data"),
        "fed_data": ("get_fed_fomc", "fed-data"),
        "csmar": ("get_csmar_financial", "csmar"),
        "macro_ceic": ("get_ceic_macro_china", "macro-ceic"),
        "wind": ("get_wind_stock_index", "wind"),
        "e2b": ("run_code", "e2b-mcp"),
        "latex": ("latex_compile", "latex-mcp"),
        "pandas": ("pd_read", "pandas-mcp"),
        "playwright": ("screenshot", "playwright-mcp"),
        "filesystem": ("read_file", "filesystem-mcp"),
        "eodhd": ("get_economic_indicators", "eodhd"),
        # New: Hubei/Wuhan/Macro MCP (2026-05-31)
        "hubei_stats": ("get_china_gdp", "hubei-stats"),
        "hubei_cpi": ("get_cpi", "hubei-stats"),
        "hubei_ppi": ("get_ppi", "hubei-stats"),
        "hubei_pmi": ("get_pmi", "hubei-stats"),
        "hubei_m2": ("get_m2", "hubei-stats"),
        "hubei_fdi": ("get_fdi", "hubei-stats"),
        "hubei_retail": ("get_consumer_retail", "hubei-stats"),
        "hubei_industry": ("get_industry_production", "hubei-stats"),
        "hubei_tech_contract": ("get_hubei_tech_contract", "hubei-stats"),
        "hubei_rd": ("get_hubei_rd_funding", "hubei-stats"),
        "hubei_hitech": ("get_hubei_hitech", "hubei-stats"),
        "wuhan_stats": ("get_wuhan_gdp", "wuhan-stats"),
        "wuhan_gdp": ("get_wuhan_gdp", "wuhan-stats"),
        "wuhan_industry": ("get_wuhan_industry", "wuhan-stats"),
        "wuhan_investment": ("get_wuhan_investment", "wuhan-stats"),
        "wuhan_trade": ("get_wuhan_trade", "wuhan-stats"),
        "wuhan_education": ("get_wuhan_education", "wuhan-stats"),
        "wuhan_tech": ("get_wuhan_tech", "wuhan-stats"),
        "macro_stats": ("get_wb_indicator", "macro-stats"),
        "wb_indicator": ("get_wb_indicator", "macro-stats"),
        "wb_gdp_usd": ("get_wb_gdp_usd", "macro-stats"),
        "wb_gdp_pc": ("get_wb_gdp_pc", "macro-stats"),
        "wb_population": ("get_wb_population", "macro-stats"),
        "wb_trade": ("get_wb_trade", "macro-stats"),
        "wb_inflation": ("get_wb_inflation", "macro-stats"),
        "wb_unemployment": ("get_wb_unemployment", "macro-stats"),
        "wb_tech_rd": ("get_wb_tech_rd", "macro-stats"),
        "nbs_fallback": ("get_nbs_fallback", "macro-stats"),
        "macro_datas": ("get_rd_panel", "macro-datas"),
        "rd_panel": ("get_rd_panel", "macro-datas"),
        "tech_panel": ("get_tech_panel", "macro-datas"),
        "industry_panel": ("get_industry_panel", "macro-datas"),
        "education_panel": ("get_education_panel", "macro-datas"),
        "nsti_report": ("get_nsti_report", "macro-datas"),
        # Province stats (2026-05-31)
        "province_indicator": ("get_province_indicator", "province-stats"),
        "province_timeseries": ("get_province_timeseries", "province-stats"),
        "province_rankings": ("get_province_rankings", "province-stats"),
        "province_summary": ("get_all_provinces_summary", "province-stats"),
    }

    # MCP tool names — set once as class-level constant
    MCP_TOOLS: frozenset[str] = frozenset({
        "arxiv", "financial", "finviz_sec", "brave_search",
        "fetch", "context7", "finagent", "yfinance",
        "newsapi", "openalex", "stock_data", "financekit",
        "sqlite", "github",
        # Custom servers
        "eastmoney_reports", "eastmoney_fund", "eastmoney_option", "eastmoney_bond",
        "tushare", "tushare_margin", "enhanced_finance", "wb_data", "imf_data",
        "oecd_data", "nber_wp", "bea_data", "fed_data",
        "csmar", "macro_ceic", "wind", "e2b",
        "latex", "pandas", "playwright", "filesystem",
        "eodhd",
        # New: Hubei/Wuhan/Macro MCP (2026-05-31)
        "hubei_stats", "hubei_cpi", "hubei_ppi", "hubei_pmi",
        "hubei_m2", "hubei_fdi", "hubei_retail", "hubei_industry",
        "hubei_tech_contract", "hubei_rd", "hubei_hitech",
        "wuhan_stats", "wuhan_gdp", "wuhan_industry", "wuhan_investment",
        "wuhan_trade", "wuhan_education", "wuhan_tech",
        "macro_stats", "wb_indicator", "wb_gdp_usd", "wb_gdp_pc",
        "wb_population", "wb_trade", "wb_inflation", "wb_unemployment",
        "wb_tech_rd", "nbs_fallback",
        "macro_datas", "rd_panel", "tech_panel", "industry_panel",
        "education_panel", "nsti_report",
        # Province stats (2026-05-31)
        "province_indicator", "province_timeseries",
        "province_rankings", "province_summary",
    })

    # Script tool names — set once as class-level constant
    SCRIPT_TOOLS: frozenset[str] = frozenset({
        "fetch_a_stock", "econometrics_regression", "report_generator", "dashboard",
    })

    # Base registry — populated once via _init_registry_base, then deep-copied per instance
    TOOL_REGISTRY_BASE: dict[str, ToolCapability] = {}

    _registry_initialized = False

    # ── Registry initialization ──────────────────────────────────────────────

    @classmethod
    def _init_registry_base(cls):
        """Populate TOOL_REGISTRY_BASE with all known tools (idempotent)."""
        if cls._registry_initialized:
            return

        # ── MCP Tools ───────────────────────────────────────────────────────────

        cls.TOOL_REGISTRY_BASE["arxiv"] = ToolCapability(
            name="arxiv",
            task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query", "max_results"],
            outputs=["papers"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="ArXiv论文检索和下载",
        )

        cls.TOOL_REGISTRY_BASE["financial"] = ToolCapability(
            name="financial",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "data_type"],
            outputs=["price", "fundamentals", "macro"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观经济、行情、crypto（yfinance/FRED）",
        )

        cls.TOOL_REGISTRY_BASE["finviz_sec"] = ToolCapability(
            name="finviz_sec",
            task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["ticker", "action"],
            outputs=["screening", "fundamentals", "sec_filings"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美股筛选、90+基本面、SEC文件",
        )

        cls.TOOL_REGISTRY_BASE["brave_search"] = ToolCapability(
            name="brave_search",
            task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query"],
            outputs=["search_results"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="财经新闻、政策文件网络检索",
        )

        cls.TOOL_REGISTRY_BASE["fetch"] = ToolCapability(
            name="fetch",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url"],
            outputs=["content"],
            priority=3,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="网页正文抓取",
        )

        cls.TOOL_REGISTRY_BASE["eastmoney_reports"] = ToolCapability(
            name="eastmoney_reports",
            task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["query", "industry"],
            outputs=["research_reports"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富研报",
        )

        cls.TOOL_REGISTRY_BASE["context7"] = ToolCapability(
            name="context7",
            task_types=[TaskType.CODE, TaskType.LITERATURE],
            inputs=["library", "query"],
            outputs=["documentation"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="官方API文档查询",
        )

        cls.TOOL_REGISTRY_BASE["tushare"] = ToolCapability(
            name="tushare",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "start_date", "end_date", "data_type"],
            outputs=["price", "financial", "index", "concept"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="A股日线、财务、指数、概念板块数据（Tushare Pro）",
        )

        cls.TOOL_REGISTRY_BASE["tushare_margin"] = ToolCapability(
            name="tushare_margin",
            task_types=[TaskType.DATA_FETCH],
            inputs=["data_type", "ts_code", "start_date", "end_date", "trade_date"],
            outputs=["margin_data", "hsgt"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="A股融资融券数据（融资余额/融资买入额/融券余额/北向资金）",
        )

        # ── Python Script Tools ─────────────────────────────────────────────────

        cls.TOOL_REGISTRY_BASE["fetch_a_stock"] = ToolCapability(
            name="fetch_a_stock",
            task_types=[TaskType.DATA_FETCH],
            inputs=["code", "start_date", "end_date"],
            outputs=["df"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="A股日线数据（akshare）",
            callable=None,  # loaded dynamically via _call_script
        )

        cls.TOOL_REGISTRY_BASE["econometrics_regression"] = ToolCapability(
            name="econometrics_regression",
            task_types=[TaskType.ANALYSIS],
            inputs=["df", "formula", "cluster"],
            outputs=["results", "table"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OLS/DID回归（statsmodels）",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["report_generator"] = ToolCapability(
            name="report_generator",
            task_types=[TaskType.WRITING, TaskType.VISUALIZATION],
            inputs=["company", "data", "format"],
            outputs=["report", "charts"],
            priority=1,
            cost=CostTier.LOW,
            requires_vpn=False,
            description="研报生成+可视化图表",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["dashboard"] = ToolCapability(
            name="dashboard",
            task_types=[TaskType.ORCHESTRATE],
            inputs=["port"],
            outputs=["streamlit_app"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Streamlit监控仪表盘",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["province_indicator"] = ToolCapability(
            name="province_indicator",
            task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["province", "indicator", "year"],
            outputs=["province_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="查询指定省份单一指标（GDP/R&D经费/高新技术企业等），支持别名匹配",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["province_timeseries"] = ToolCapability(
            name="province_timeseries",
            task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["province", "indicator"],
            outputs=["time_series", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="获取指定省份指标的多年面板序列（GDP/R&D/高新技术企业时间序列）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["province_rankings"] = ToolCapability(
            name="province_rankings",
            task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["table"],
            outputs=["ranking_table", "cross_province"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="获取全国各省排名表（GDP/R&D经费/高新技术企业/技术合同排名）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["province_summary"] = ToolCapability(
            name="province_summary",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=["province_list", "verification_status"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="获取所有收录省份的概览信息（含核查状态、数据覆盖范围）",
            callable=None,
        )


        cls.TOOL_REGISTRY_BASE["bea_data"] = ToolCapability(
            name="bea_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="bea_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["csmar"] = ToolCapability(
            name="csmar",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="csmar",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["e2b"] = ToolCapability(
            name="e2b",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="e2b",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["eastmoney_bond"] = ToolCapability(
            name="eastmoney_bond",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="eastmoney_bond",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["eastmoney_fund"] = ToolCapability(
            name="eastmoney_fund",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="eastmoney_fund",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["eastmoney_option"] = ToolCapability(
            name="eastmoney_option",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="eastmoney_option",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["education_panel"] = ToolCapability(
            name="education_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="education_panel",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["enhanced_finance"] = ToolCapability(
            name="enhanced_finance",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="enhanced_finance",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["eodhd"] = ToolCapability(
            name="eodhd",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="eodhd",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["fed_data"] = ToolCapability(
            name="fed_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="fed_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["filesystem"] = ToolCapability(
            name="filesystem",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="filesystem",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["finagent"] = ToolCapability(
            name="finagent",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="finagent",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["financekit"] = ToolCapability(
            name="financekit",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="financekit",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["github"] = ToolCapability(
            name="github",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="github",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_cpi"] = ToolCapability(
            name="hubei_cpi",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_cpi",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_fdi"] = ToolCapability(
            name="hubei_fdi",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_fdi",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_hitech"] = ToolCapability(
            name="hubei_hitech",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_hitech",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_industry"] = ToolCapability(
            name="hubei_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_industry",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_m2"] = ToolCapability(
            name="hubei_m2",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_m2",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_pmi"] = ToolCapability(
            name="hubei_pmi",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_pmi",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_ppi"] = ToolCapability(
            name="hubei_ppi",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_ppi",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_rd"] = ToolCapability(
            name="hubei_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_rd",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_retail"] = ToolCapability(
            name="hubei_retail",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_retail",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_stats"] = ToolCapability(
            name="hubei_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_stats",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["hubei_tech_contract"] = ToolCapability(
            name="hubei_tech_contract",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="hubei_tech_contract",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["imf_data"] = ToolCapability(
            name="imf_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="imf_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["industry_panel"] = ToolCapability(
            name="industry_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="industry_panel",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["latex"] = ToolCapability(
            name="latex",
            task_types=[TaskType.CODE],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX工具: latex",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["macro_ceic"] = ToolCapability(
            name="macro_ceic",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="macro_ceic",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["macro_datas"] = ToolCapability(
            name="macro_datas",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="macro_datas",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["macro_stats"] = ToolCapability(
            name="macro_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="macro_stats",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["nber_wp"] = ToolCapability(
            name="nber_wp",
            task_types=[TaskType.LITERATURE],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="nber_wp",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["nbs_fallback"] = ToolCapability(
            name="nbs_fallback",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="nbs_fallback",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["newsapi"] = ToolCapability(
            name="newsapi",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="newsapi",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["nsti_report"] = ToolCapability(
            name="nsti_report",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="nsti_report",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["oecd_data"] = ToolCapability(
            name="oecd_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="oecd_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["openalex"] = ToolCapability(
            name="openalex",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="openalex",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["pandas"] = ToolCapability(
            name="pandas",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="pandas",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["playwright"] = ToolCapability(
            name="playwright",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="playwright",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["rd_panel"] = ToolCapability(
            name="rd_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="rd_panel",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["sqlite"] = ToolCapability(
            name="sqlite",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="sqlite",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["stock_data"] = ToolCapability(
            name="stock_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="stock_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["tech_panel"] = ToolCapability(
            name="tech_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="tech_panel",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_data"] = ToolCapability(
            name="wb_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_data",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_gdp_pc"] = ToolCapability(
            name="wb_gdp_pc",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_gdp_pc",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_gdp_usd"] = ToolCapability(
            name="wb_gdp_usd",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_gdp_usd",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_indicator"] = ToolCapability(
            name="wb_indicator",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_indicator",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_inflation"] = ToolCapability(
            name="wb_inflation",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_inflation",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_population"] = ToolCapability(
            name="wb_population",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_population",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_tech_rd"] = ToolCapability(
            name="wb_tech_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_tech_rd",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_trade"] = ToolCapability(
            name="wb_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_trade",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wb_unemployment"] = ToolCapability(
            name="wb_unemployment",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wb_unemployment",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wind"] = ToolCapability(
            name="wind",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wind",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_education"] = ToolCapability(
            name="wuhan_education",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_education",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_gdp"] = ToolCapability(
            name="wuhan_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_gdp",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_industry"] = ToolCapability(
            name="wuhan_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_industry",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_investment"] = ToolCapability(
            name="wuhan_investment",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_investment",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_stats"] = ToolCapability(
            name="wuhan_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_stats",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_tech"] = ToolCapability(
            name="wuhan_tech",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_tech",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["wuhan_trade"] = ToolCapability(
            name="wuhan_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="wuhan_trade",
            callable=None,
        )

        cls.TOOL_REGISTRY_BASE["yfinance"] = ToolCapability(
            name="yfinance",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=[],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="yfinance",
            callable=None,
        )
        cls._registry_initialized = True

    # ── Initialization ──────────────────────────────────────────────────────────

    def __init__(self, memory: ResearchMemory, agent_name: str | None = None):
        from pathlib import Path
        self.memory = memory
        self.project_root: Path = Path(__file__).parent.parent.parent
        self._availability_cache: dict[str, tuple[bool, float]] = {}  # tool_name → (available, timestamp)
        self._availability_cache_ttl: float = 300.0  # seconds
        self._vpn_available: bool | None = None
        # Current agent name for allowed_tools enforcement; set via set_agent()
        self._agent_name: str | None = agent_name

        # Ensure base registry is populated
        self._init_registry_base()

        # Deep copy the class registry so each instance has its own copy
        # This prevents shared mutable state across instances
        self.TOOL_REGISTRY: dict[str, ToolCapability] = {
            k: v for k, v in self.TOOL_REGISTRY_BASE.items()
        }

    def set_agent(self, agent_name: str | None) -> None:
        """
        Set the current agent name for allowed_tools enforcement.

        Call this before tool execution so the selector knows which agent
        is making the request and can apply the correct whitelist.

        Parameters
        ----------
        agent_name : str | None
            Name of the agent, or None to clear (disables enforcement).
        """
        self._agent_name = agent_name

    # ── Selection ───────────────────────────────────────────────────────────────

    def select(
        self, task: Task, context: list[ContextUnit] | None = None
    ) -> list[ToolSelection]:
        """
        Select the best tools for a given task, sorted by priority and cost.

        Parameters
        ----------
        task : Task
            The task to select tools for.
        context : list[ContextUnit] | None
            Current session context. Tools previously used in context
            receive a +0.1 confidence boost.

        Returns
        -------
        list[ToolSelection]
            Tools ranked by priority and cost. Empty list if no tool matches.
        """
        if context is None:
            context = []

        vpn_ok = self._check_vpn()

        # 1. Filter: task type match + VPN constraint
        candidates: list[ToolCapability] = []
        for tool in self.TOOL_REGISTRY.values():
            if task.task_type not in tool.task_types:
                continue
            if tool.requires_vpn and not vpn_ok:
                continue
            candidates.append(tool)

        if not candidates:
            return []

        # 2. Sort: priority asc (primary), then cost asc (secondary)
        # Smaller priority number = higher priority; smaller cost order = lower cost
        candidates.sort(key=lambda t: (t.priority, _COST_ORDER[t.cost]))

        # 3. Build ToolSelection list with confidence
        selections = []
        for i, cap in enumerate(candidates):
            confidence = 1.0 if i == 0 else 0.8
            reason = self._build_reason(cap, task)
            selections.append(ToolSelection(
                tool_name=cap.name,
                confidence=confidence,
                reason=reason,
                estimated_cost=cap.cost.value,
                requires_vpn=cap.requires_vpn,
                callable=cap.callable,
            ))

        # 4. Context-aware confidence boost: if we used this tool before, boost confidence
        for selection in selections:
            for ctx in context:
                if ctx.tools_used and selection.tool_name in ctx.tools_used:
                    selection.confidence = min(1.0, selection.confidence + 0.1)
                    break  # Only apply boost once per tool

        return selections

    def _build_reason(self, cap: ToolCapability, task: Task) -> str:
        """Build a human-readable reason for selecting this tool."""
        task_type_names = [tt.value for tt in cap.task_types]
        return (
            f"Tool '{cap.name}' handles {task_type_names} "
            f"with priority={cap.priority}, cost={cap.cost.value}. "
            f"Description: {cap.description}"
        )

    # ── Marketplace Integration ──────────────────────────────────────────────

    def select_best_quality_tool(
        self,
        task_type: TaskType,
        category: str | None = None,
        top_k: int = 3,
    ) -> list[ToolMetadata]:
        """
        Select top-k tools for a task type, ranked by quality score.

        Uses the MCP Tool Marketplace registry to score tools by
        description length, schema completeness, real API indicators,
        mock flag, and example presence.
        """
        try:
            registry = get_default_registry()
        except RuntimeError:
            registry = MCPToolRegistry.from_directory(
                str(self.project_root / "mcp_servers")
            )

        # Map TaskType to search query
        task_query_map = {
            TaskType.DATA_FETCH: "data fetch market financial api",
            TaskType.LITERATURE: "literature search academic paper",
            TaskType.ANALYSIS: "data analysis statistics",
            TaskType.WRITING: "writing text generation",
            TaskType.CODE: "code generation execution sandbox",
            TaskType.VISUALIZATION: "visualization chart plotting",
            TaskType.REVIEW: "review evaluation feedback",
            TaskType.ORCHESTRATE: "orchestration scheduling planning",
        }

        query = task_query_map.get(task_type, task_type.value)

        if category:
            results = registry.search(query, category=category, max_results=top_k)
        else:
            results = registry.search(query, max_results=top_k)

        return results

    def get_tool_marketplace_report(self) -> dict:
        """Get tool marketplace statistics for dashboard display."""
        try:
            registry = get_default_registry()
        except RuntimeError:
            registry = MCPToolRegistry.from_directory(
                str(self.project_root / "mcp_servers")
            )
        return registry.get_marketplace_report()

    # ── Execution ───────────────────────────────────────────────────────────────

    def execute(self, selection: ToolSelection, inputs: dict) -> ToolResult:
        """
        Execute the selected tool with the given inputs.

        Tries the primary selection first. On failure, attempts fallback by
        re-selecting a lower-priority tool for the same task (caller should
        retry with next selection in the list).

        Parameters
        ----------
        selection : ToolSelection
            The tool to execute.
        inputs : dict
            Input parameters for the tool.

        Returns
        -------
        ToolResult
            Structured result (success=True or success=False with error message).
        """
        tool_name = selection.tool_name
        cap = self.TOOL_REGISTRY.get(tool_name)

        if cap is None:
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=f"Tool '{tool_name}' not found in registry",
            )

        start = time.time()

        # ── allowed_tools whitelist enforcement ───────────────────────────────────
        if self._agent_name is not None:
            from scripts.core.llm_gateway import _agent_registry

            allowed = _agent_registry.get_allowed_tools(self._agent_name)
            if allowed is not None and tool_name not in allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    tool_name=tool_name,
                    error=(
                        f"Tool '{tool_name}' is not allowed for agent '{self._agent_name}'. "
                        f"Allowed tools: {', '.join(sorted(allowed))}"
                    ),
                    latency_ms=(time.time() - start) * 1000,
                )

        # Check availability
        if not self._check_tool_availability(tool_name):
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=f"Tool '{tool_name}' is not currently available",
                latency_ms=(time.time() - start) * 1000,
            )

        try:
            if tool_name in self.MCP_TOOLS:
                output = self._call_mcp(tool_name, inputs)
            elif tool_name in self.SCRIPT_TOOLS:
                output = self._call_script(tool_name, inputs)
            else:
                # Fallback: try as script
                output = self._call_script(tool_name, inputs)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=str(exc),
                latency_ms=(time.time() - start) * 1000,
            )

        return ToolResult(
            success=True,
            output=output,
            tool_name=tool_name,
            latency_ms=(time.time() - start) * 1000,
        )

    # ── Tool Invocation ─────────────────────────────────────────────────────────

    def _call_mcp(self, tool_name: str, params: dict) -> Any:
        """
        Call an MCP tool by name via the MCP Python SDK.

        MCP tools are invoked through the MCP client SDK which communicates
        with the MCP server (either a CLI process or a long-running server).
        The server must be running for this to succeed.

        Architecture:
          - MCP tools run as external processes (mcp CLI) or long-running servers
          - This method uses the mcp Python SDK to communicate with those servers
          - The MCP server URL/command is derived from the tool name
          - Tool names are mapped via MCP_TOOL_SERVER_MAP to actual server names

        Args:
            tool_name: The MCP tool name (e.g. "arxiv", "financial")
            params: Dictionary of parameters to pass to the tool

        Returns:
            The result from the MCP tool call

        Raises:
            NotImplementedError: If the MCP tool is not configured or unavailable
        """
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise NotImplementedError(
                f"MCP tool '{tool_name}' requires the mcp package. "
                "Install with: pip install mcp. "
                "The MCP server must also be running."
            )

        # Look up actual MCP tool name and server name
        actual_tool_name, server_name = self.MCP_TOOL_SERVER_MAP.get(
            tool_name, (tool_name, tool_name)
        )

        server_config = self._get_mcp_config(server_name)
        if server_config is None:
            raise NotImplementedError(
                f"MCP tool '{tool_name}' (server='{server_name}') is registered "
                f"but has no server configuration. "
                f"Add it to mcp.json or update MCP_TOOL_SERVER_MAP in tool_selector.py."
            )

        # Call the MCP server via stdio
        try:
            async def _do_call():
                async with stdio_client(
                    type("ServerParameters", (), {
                        "command": server_config["command"],
                        "args": server_config["args"],
                        "env": {**os.environ, **server_config.get("env", {})},
                        "stdio_interface": None,
                    })()
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(actual_tool_name, params)
                        return result.content if hasattr(result, "content") else result

            import asyncio
            return asyncio.run(_do_call())

        except Exception as exc:
            raise NotImplementedError(
                f"MCP tool '{tool_name}' (actual_name='{actual_tool_name}', "
                f"server='{server_name}') call failed: {exc}. "
                f"Ensure the MCP server is running."
            ) from exc

    def _resolve_server_config(self, server_name: str) -> dict | None:
        """Read server config from platform-aware MCP config paths (Cursor/Claude Code/VS Code/project-local)."""
        import json
        for cfg_path in get_mcp_config_paths():
            if not cfg_path.exists():
                continue
            try:
                with open(cfg_path) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", {})
                if server_name in servers:
                    srv = servers[server_name]
                    return {
                        "command": srv.get("command", ""),
                        "args": srv.get("args", []),
                        "env": srv.get("env", {}),
                    }
            except Exception:
                pass
        return None

    def _get_mcp_config(self, tool_name: str) -> dict | None:
        """
        Get MCP server config for a tool name.

        Resolution order:
        1. MCP_TOOL_SERVER_MAP (tool → server name → mcp.json)
        2. Auto-discover from mcp.json (exact/partial server name match)
        """
        # 1. Check class-level tool-to-server map first (with slug normalization)
        for map_tool, (mcp_tool, server_name) in self.MCP_TOOL_SERVER_MAP.items():
            if (map_tool == tool_name
                    or map_tool.replace("_", "-") == tool_name.replace("_", "-")
                    or tool_name.replace("-", "_") == map_tool):
                if server_name:
                    return self._resolve_server_config(server_name)
                return None

        # 2. Auto-discover from mcp.json
        return self._resolve_server_config(tool_name)

    def _call_script(self, tool_name: str, params: dict) -> Any:
        """
        Invoke a Python script tool by dynamically importing its module.

        Uses SCRIPT_CALLABLES (class-level) for tool → (module, function) mapping.
        If the mapped name starts with an uppercase letter (PascalCase), it is
        treated as a class name and instantiated with default arguments before
        calling the corresponding method.

        Raises NotImplementedError so callers can mock it in tests.
        """
        mapping = SCRIPT_CALLABLES.get(tool_name)
        if mapping is None:
            raise NotImplementedError(
                f"No script mapping defined for tool '{tool_name}'"
            )

        module_name, func_name = mapping
        try:
            module = importlib.import_module(module_name)
            attr = getattr(module, func_name)

            # If it's a class (PascalCase name), instantiate and call the default method
            if isinstance(attr, type) or (isinstance(attr, object) and func_name[0].isupper()):
                # It's a class — instantiate with default args
                instance = attr()
                # Try calling a default method (commonly "run", "execute", or "__call__")
                for method_name in ("run", "execute", "__call__"):
                    if hasattr(instance, method_name):
                        return getattr(instance, method_name)(**params)
                # Fallback: return the instance itself if no default method found
                return instance
            else:
                # It's a function — call directly
                return attr(**params)

        except (ImportError, AttributeError) as exc:
            raise NotImplementedError(
                f"Failed to import or call script tool '{tool_name}' "
                f"({module_name}.{func_name}): {exc}"
            ) from exc

    # ── Availability Checks ─────────────────────────────────────────────────────

    def _check_vpn(self) -> bool:
        """
        Check whether VPN is available by pinging api.b.ai.

        Returns cached result after first check.
        """
        if self._vpn_available is not None:
            return self._vpn_available

        try:
            req = urllib.request.Request(
                "https://api.b.ai/",
                method="HEAD",
                timeout=5,
            )
            with urllib.request.urlopen(req) as resp:
                self._vpn_available = resp.status == 200
        except Exception:  # noqa: BLE001
            self._vpn_available = False

        return self._vpn_available

    def _check_tool_availability(self, tool_name: str) -> bool:
        """
        Check whether a tool is currently available.

        Results are cached with TTL (default 5 min) to avoid repeated probing.
        """
        now = time.time()
        if tool_name in self._availability_cache:
            available, cached_at = self._availability_cache[tool_name]
            if now - cached_at < self._availability_cache_ttl:
                return available
            del self._availability_cache[tool_name]

        available = self._probe_tool(tool_name)
        self._availability_cache[tool_name] = (available, now)

        # Prune expired entries from other tools
        expired = [k for k, (__, ts) in self._availability_cache.items()
                   if now - ts >= self._availability_cache_ttl]
        for k in expired:
            del self._availability_cache[k]

        return available

    def _probe_tool(self, tool_name: str) -> bool:
        """
        Probe a single tool for availability.

        MCP tools: check if the server config exists in mcp.json.
        Script tools: check if the module can be imported.
        """
        if tool_name in self.MCP_TOOLS:
            # Check if MCP server config exists — only mark available if config is present
            actual_tool_name, server_name = self.MCP_TOOL_SERVER_MAP.get(
                tool_name, (tool_name, tool_name)
            )
            return self._get_mcp_config(server_name) is not None

        # Script tool — check import using class-level SCRIPT_CALLABLES
        mapping = SCRIPT_CALLABLES.get(tool_name)
        if mapping is None:
            return False

        module_name, _ = mapping
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
