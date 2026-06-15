"""ToolSelector: Tool registry and routing for the economic research agent.

Provides:
- ToolCapability registry (MCP tools + Python scripts)
- Task-type-based tool selection with cost and VPN filtering
- Fallback execution chain
- MCP and script invocation layer
"""

from __future__ import annotations

__all__ = [
    "CostTier",
    "ToolCapability",
    "ToolSelection",
]

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
    # Maps registry tool name → (actual_mcp_tool_name, serverIdentifier from SERVER_METADATA.json)
    # ⚠️ 工具名必须与 mcp_servers/<server>/SERVER_METADATA.json 中的 tools 数组一致
    MCP_TOOL_SERVER_MAP: dict[str, tuple[str, str]] = {
        # ── 学术文献 ────────────────────────────────────────────────────────────
        "arxiv": ("semantic_search", "user-arxiv"),
        "context7": ("get_context7_by_query", "user-context7"),
        "openalex": ("get_openalex_works", "user-openalex"),
        "semantic_scholar": ("search_semantic_scholar", "user-semantic-scholar"),
        "nber_wp": ("search_nber_papers", "user-nber-wp"),
        # ── 网络搜索 ─────────────────────────────────────────────────────────────
        "brave_search": ("brave_web_search", "user-brave-search"),
        # ── A股数据 ─────────────────────────────────────────────────────────────
        "tushare": ("get_daily_quote", "user-tushare"),
        "tushare_margin": ("get_margin_data", "user-tushare"),
        "tushare_financial": ("get_financial_report", "user-tushare"),
        "tushare_index": ("get_index_data", "user-tushare"),
        "tushare_stock_basic": ("get_stock_basic", "user-tushare"),
        "tushare_calendar": ("get_trade_calendar", "user-tushare"),
        "tushare_concept": ("get_concept_stocks", "user-tushare"),
        # ── CSMAR ───────────────────────────────────────────────────────────────
        "csmar_financial": ("get_csmar_financial", "user-csmar"),
        "csmar_trading": ("get_csmar_trading", "user-csmar"),
        "csmar_corporate": ("get_csmar_corporate", "user-csmar"),
        "csmar_analyst": ("get_csmar_analyst", "user-csmar"),
        # ── Wind ────────────────────────────────────────────────────────────────
        "wind_index": ("get_wind_stock_index", "user-wind"),
        "wind_bond": ("get_wind_bond_yield", "user-wind"),
        "wind_credit": ("get_wind_credit_spread", "user-wind"),
        "wind_futures": ("get_wind_futures", "user-wind"),
        # ── 美股 / 全球市场 ─────────────────────────────────────────────────────
        "yfinance": ("get_yf_quote", "user-yfinance"),
        "yfinance_hist": ("get_yf_historical", "user-yfinance"),
        "yfinance_financials": ("get_yf_financials", "user-yfinance"),
        "yfinance_options": ("get_yf_options", "user-yfinance"),
        "yfinance_etf": ("get_yf_etf_holdings", "user-yfinance"),
        "yfinance_news": ("get_yf_news", "user-yfinance"),
        "yfinance_earnings": ("get_yf_earnings", "user-yfinance"),
        "sec_edgar": ("get_sec_filings", "user-sec-edgar"),
        "sec_10k": ("get_sec_10k", "user-sec-edgar"),
        "sec_10q": ("get_sec_10q", "user-sec-edgar"),
        "sec_8k": ("get_sec_8k", "user-sec-edgar"),
        "sec_ticker": ("get_sec_cik_by_ticker", "user-sec-edgar"),
        "sec_search": ("get_sec_company_search", "user-sec-edgar"),
        # ── 研报 / 新闻 ─────────────────────────────────────────────────────────
        "eastmoney_reports": ("get_research_report", "user-eastmoney-reports"),
        "eastmoney_analyst": ("get_analyst_rank", "user-eastmoney-reports"),
        "eastmoney_news": ("get_stock_news", "user-eastmoney-reports"),
        "eastmoney_concept": ("get_board_concept", "user-eastmoney-reports"),
        "eastmoney_industry": ("get_board_industry", "user-eastmoney-reports"),
        "eastmoney_fund_nav": ("get_fund_nav", "user-eastmoney-fund"),
        "eastmoney_fund_flow": ("get_fund_flow", "user-eastmoney-fund"),
        "eastmoney_fund_holdings": ("get_fund_holdings", "user-eastmoney-fund"),
        "eastmoney_fund_perf": ("get_fund_performance", "user-eastmoney-fund"),
        "eastmoney_option_chain": ("get_option_chain", "user-eastmoney-option"),
        "eastmoney_option_greeks": ("get_option_greeks", "user-eastmoney-option"),
        "eastmoney_option_vol": ("get_option_vol", "user-eastmoney-option"),
        "eastmoney_bond_yield": ("get_bond_yield_curve", "user-eastmoney-bond"),
        "eastmoney_bond_repo": ("get_bond_repo", "user-eastmoney-bond"),
        "eastmoney_bond_spot": ("get_bond_spot", "user-eastmoney-bond"),
        # ── 外汇 / 大宗商品 / 航运 ─────────────────────────────────────────────
        "enhanced_forex": ("get_forex_spot", "user-enhanced-finance"),
        "enhanced_forex_hist": ("get_forex_hist", "user-enhanced-finance"),
        "enhanced_commodity": ("get_commodity_price", "user-enhanced-finance"),
        "enhanced_crypto": ("get_crypto_price", "user-enhanced-finance"),
        "enhanced_futures": ("get_futures_price", "user-enhanced-finance"),
        "enhanced_shipping": ("get_shipping_index", "user-enhanced-finance"),
        # ── 国债 / 经济日历 ────────────────────────────────────────────────────
        "eodhd_yield": ("get_ust_yield_rates", "user-eodhd"),
        "eodhd_indicators": ("get_economic_indicators", "user-eodhd"),
        "eodhd_events": ("get_economic_events", "user-eodhd"),
        # ── 全球宏观 ─────────────────────────────────────────────────────────────
        "wb_gdp": ("get_wb_gdp", "user-wb-data"),
        "wb_population": ("get_wb_population", "user-wb-data"),
        "wb_trade": ("get_wb_trade", "user-wb-data"),
        "wb_debt": ("get_wb_debt", "user-wb-data"),
        "wb_health": ("get_wb_health", "user-wb-data"),
        "wb_education": ("get_wb_education", "user-wb-data"),
        "wb_gender": ("get_wb_gender", "user-wb-data"),
        "imf_ifs": ("get_imf_ifs", "user-imf-data"),
        "imf_weo": ("get_imf_world_economic_outlook", "user-imf-data"),
        "imf_bop": ("get_imf_bop", "user-imf-data"),
        "oecd_gdp": ("get_oecd_gdp", "user-oecd-data"),
        "oecd_employment": ("get_oecd_employment", "user-oecd-data"),
        "oecd_trade": ("get_oecd_trade", "user-oecd-data"),
        "oecd_tfp": ("get_oecd_tfp", "user-oecd-data"),
        "bea_gdp": ("get_bea_gdp", "user-bea-data"),
        "bea_gdi": ("get_bea_gdi", "user-bea-data"),
        "bea_industry": ("get_bea_industry", "user-bea-data"),
        "bea_nipa": ("get_bea_nipa", "user-bea-data"),
        "fed_rate": ("get_fed_interest_rate", "user-fed-data"),
        "fed_fomc": ("get_fed_fomc", "user-fed-data"),
        "fed_beige": ("get_fed_beige_book", "user-fed-data"),
        "fed_yield": ("get_fed_yield_curve", "user-fed-data"),
        "ceic_macro": ("get_ceic_macro_china", "user-macro-ceic"),
        "ceic_consumer": ("get_ceic_consumer", "user-macro-ceic"),
        "ceic_industry": ("get_ceic_industry", "user-macro-ceic"),
        "ceic_trade": ("get_ceic_trade", "user-macro-ceic"),
        "macro_stats_gdp": ("get_wb_gdp_usd", "user-macro-stats"),
        "macro_stats_gdp_pc": ("get_wb_gdp_pc", "user-macro-stats"),
        "macro_stats_pop": ("get_wb_population", "user-macro-stats"),
        "macro_stats_trade": ("get_wb_trade", "user-macro-stats"),
        "macro_stats_inflation": ("get_wb_inflation", "user-macro-stats"),
        "macro_stats_unemp": ("get_wb_unemployment", "user-macro-stats"),
        "macro_stats_rd": ("get_wb_tech_rd", "user-macro-stats"),
        "macro_stats_indicator": ("get_wb_indicator", "user-macro-stats"),
        # ── 中国宏观 ─────────────────────────────────────────────────────────────
        "financial": ("get_macro_china", "user-financial"),
        "financial_cpi": ("get_macro_china", "user-financial"),
        "financial_gdp": ("get_macro_china", "user-financial"),
        "financial_m2": ("get_macro_china", "user-financial"),
        # ── 省级面板 ────────────────────────────────────────────────────────────
        "province_indicator": ("get_province_indicator", "user-province-stats"),
        "province_timeseries": ("get_province_timeseries", "user-province-stats"),
        "province_rankings": ("get_province_rankings", "user-province-stats"),
        "province_summary": ("get_province_rankings", "user-province-stats"),
        # ── 湖北省 ──────────────────────────────────────────────────────────────
        "hubei_gdp": ("get_china_gdp", "user-hubei-stats"),
        "hubei_cpi": ("get_cpi", "user-hubei-stats"),
        "hubei_ppi": ("get_ppi", "user-hubei-stats"),
        "hubei_pmi": ("get_pmi", "user-hubei-stats"),
        "hubei_m2": ("get_m2", "user-hubei-stats"),
        "hubei_fdi": ("get_fdi", "user-hubei-stats"),
        "hubei_retail": ("get_consumer_retail", "user-hubei-stats"),
        "hubei_industry": ("get_industry_production", "user-hubei-stats"),
        "hubei_tech_contract": ("get_hubei_tech_contract", "user-hubei-stats"),
        "hubei_rd": ("get_hubei_rd_funding", "user-hubei-stats"),
        "hubei_hitech": ("get_hubei_hitech", "user-hubei-stats"),
        "hubei_rd_yearly": ("get_china_gdp_yearly", "user-hubei-stats"),
        # ── 武汉市 ──────────────────────────────────────────────────────────────
        "wuhan_gdp": ("get_wuhan_gdp", "user-wuhan-stats"),
        "wuhan_industry": ("get_wuhan_industry", "user-wuhan-stats"),
        "wuhan_investment": ("get_wuhan_investment", "user-wuhan-stats"),
        "wuhan_trade": ("get_wuhan_trade", "user-wuhan-stats"),
        "wuhan_education": ("get_wuhan_education", "user-wuhan-stats"),
        "wuhan_tech": ("get_wuhan_tech", "user-wuhan-stats"),
        # ── 宏观数据聚合 ────────────────────────────────────────────────────────
        "macro_datas_rd": ("get_rd_panel", "user-macro-datas"),
        "macro_datas_tech": ("get_tech_panel", "user-macro-datas"),
        "macro_datas_industry": ("get_industry_panel", "user-macro-datas"),
        "macro_datas_edu": ("get_education_panel", "user-macro-datas"),
        "macro_datas_nsti": ("get_nsti_report", "user-macro-datas"),
        "macro_datas_nbs": ("get_nbs_fallback", "user-macro-stats"),
        # ── 新闻 / 加密货币 ────────────────────────────────────────────────────
        "newsapi": ("get_news_search", "user-newsapi"),
        "cryptocompare": ("get_cc_price", "user-cryptocompare"),
        # ── 工具类 ──────────────────────────────────────────────────────────────
        "e2b": ("e2b_run", "user-e2b-mcp"),
        "latex": ("latex_compile", "user-latex-mcp"),
        "latex_check": ("latex_check", "user-latex-mcp"),
        "latex_diff": ("latex_diff", "user-latex-mcp"),
        "latex_to_pdf": ("latex_to_pdf", "user-latex-mcp"),
        "latex_formula": ("latex_render_formula", "user-latex-mcp"),
        "latex_bibtex": ("latex_bibtex_check", "user-latex-mcp"),
        "latex_scaffold": ("latex_scaffold", "user-latex-mcp"),
        "latex_words": ("latex_count_words", "user-latex-mcp"),
        "pandas": ("pd_read", "user-pandas-mcp"),
        "pandas_describe": ("pd_describe", "user-pandas-mcp"),
        "pandas_filter": ("pd_filter", "user-pandas-mcp"),
        "pandas_merge": ("pd_merge", "user-pandas-mcp"),
        "pandas_corr": ("pd_corr_analysis", "user-pandas-mcp"),
        "pandas_sql": ("pd_sql", "user-pandas-mcp"),
        "playwright_screenshot": ("pw_screenshot", "user-playwright-mcp"),
        "playwright_navigate": ("pw_navigate", "user-playwright-mcp"),
        "playwright_scrape": ("pw_scrape_table", "user-playwright-mcp"),
        "playwright_html": ("pw_get_html", "user-playwright-mcp"),
        "playwright_click": ("pw_click", "user-playwright-mcp"),
        "playwright_download": ("pw_download", "user-playwright-mcp"),
        "filesystem_read": ("fs_read", "user-filesystem-mcp"),
        "filesystem_write": ("fs_write", "user-filesystem-mcp"),
        "filesystem_glob": ("fs_glob", "user-filesystem-mcp"),
        "filesystem_tree": ("fs_tree", "user-filesystem-mcp"),
        "filesystem_grep": ("fs_grep", "user-filesystem-mcp"),
        "filesystem_diff": ("fs_diff", "user-filesystem-mcp"),
        # ── 新增MCP（2026-06-08）────────────────────────────────────────────
        # CNRDS — 中国研究数据服务
        "cnrd_patent": ("get_cnrd_patent", "user-cnrd"),
        "cnrd_papers": ("search_cnrd_papers", "user-cnrd"),
        "cnrd_company": ("get_cnrd_company", "user-cnrd"),
        "cnrd_financial": ("get_cnrd_financial", "user-cnrd"),
        # SIPO — 国家知识产权局专利
        "sipo_patent": ("search_sipo_patent", "user-sipo"),
        "sipo_detail": ("get_patent_detail", "user-sipo"),
        "sipo_biblio": ("get_patent_bibliographic", "user-sipo"),
        "sipo_litigation": ("get_patent_litigation", "user-sipo"),
        # 第三方ESG评级
        "esg_rating": ("get_esg_rating", "user-third-party-esg"),
        "esg_trend": ("get_esg_trend", "user-third-party-esg"),
        "esg_controversy": ("get_esg_controversy", "user-third-party-esg"),
        "esg_ranking": ("get_esg_ranking", "user-third-party-esg"),
        # 中国海关进出口
        "customs_import": ("get_customs_import", "user-chinese-customs"),
        "customs_export": ("get_customs_export", "user-chinese-customs"),
        "customs_balance": ("get_customs_trade_balance", "user-chinese-customs"),
        "customs_country": ("get_customs_by_country", "user-chinese-customs"),
        # ── 中文文献 ────────────────────────────────────────────────────────────
        "chinese_literature": ("search_chinese_papers", "user-chinese-literature"),
        "chinese_paper_citations": ("get_paper_citations", "user-chinese-literature"),
        "journal_info": ("get_journal_info", "user-chinese-literature"),
        "cssci_papers": ("search_cssci_papers", "user-chinese-literature"),
    }

    # MCP tool names — set once as class-level constant
    # NOTE: This set defines which tool names are MCP-based vs script-based.
    # Registry key names here must also exist in MCP_TOOL_SERVER_MAP.
    MCP_TOOLS: frozenset[str] = frozenset({
        # 学术文献
        "arxiv", "context7", "openalex", "semantic_scholar", "nber_wp",
        # 网络搜索
        "brave_search",
        # A股
        "tushare", "tushare_margin", "tushare_financial", "tushare_index",
        "tushare_stock_basic", "tushare_calendar", "tushare_concept",
        # CSMAR
        "csmar_financial", "csmar_trading", "csmar_corporate", "csmar_analyst",
        # Wind
        "wind_index", "wind_bond", "wind_credit", "wind_futures",
        # 美股 / SEC
        "yfinance", "yfinance_hist", "yfinance_financials", "yfinance_options",
        "yfinance_etf", "yfinance_news", "yfinance_earnings",
        "sec_edgar", "sec_10k", "sec_10q", "sec_8k", "sec_ticker", "sec_search",
        # 研报 / 新闻
        "eastmoney_reports", "eastmoney_analyst", "eastmoney_news",
        "eastmoney_concept", "eastmoney_industry",
        "eastmoney_fund_nav", "eastmoney_fund_flow",
        "eastmoney_fund_holdings", "eastmoney_fund_perf",
        "eastmoney_option_chain", "eastmoney_option_greeks", "eastmoney_option_vol",
        "eastmoney_bond_yield", "eastmoney_bond_repo", "eastmoney_bond_spot",
        # 外汇 / 大宗商品
        "enhanced_forex", "enhanced_forex_hist", "enhanced_commodity",
        "enhanced_crypto", "enhanced_futures", "enhanced_shipping",
        # 国债 / 经济日历
        "eodhd_yield", "eodhd_indicators", "eodhd_events",
        # 全球宏观
        "wb_gdp", "wb_population", "wb_trade", "wb_debt",
        "wb_health", "wb_education", "wb_gender",
        "imf_ifs", "imf_weo", "imf_bop",
        "oecd_gdp", "oecd_employment", "oecd_trade", "oecd_tfp",
        "bea_gdp", "bea_gdi", "bea_industry", "bea_nipa",
        "fed_rate", "fed_fomc", "fed_beige", "fed_yield",
        "ceic_macro", "ceic_consumer", "ceic_industry", "ceic_trade",
        # 中国宏观
        "financial", "financial_cpi", "financial_gdp", "financial_m2",
        # 省级
        "province_indicator", "province_timeseries", "province_rankings", "province_summary",
        # 湖北省
        "hubei_gdp", "hubei_cpi", "hubei_ppi", "hubei_pmi",
        "hubei_m2", "hubei_fdi", "hubei_retail", "hubei_industry",
        "hubei_tech_contract", "hubei_rd", "hubei_hitech", "hubei_rd_yearly",
        # 武汉市
        "wuhan_gdp", "wuhan_industry", "wuhan_investment",
        "wuhan_trade", "wuhan_education", "wuhan_tech",
        # 宏观数据聚合
        "macro_datas_rd", "macro_datas_tech", "macro_datas_industry",
        "macro_datas_edu", "macro_datas_nsti", "macro_datas_nbs",
        "macro_stats_gdp", "macro_stats_gdp_pc", "macro_stats_pop",
        "macro_stats_trade", "macro_stats_inflation", "macro_stats_unemp",
        "macro_stats_rd", "macro_stats_indicator",
        # 新闻 / 加密货币
        "newsapi", "cryptocompare",
        # 工具类
        "e2b", "latex", "latex_check", "latex_diff", "latex_to_pdf",
        "latex_formula", "latex_bibtex", "latex_scaffold", "latex_words",
        "pandas", "pandas_describe", "pandas_filter", "pandas_merge",
        "pandas_corr", "pandas_sql",
        "playwright_screenshot", "playwright_navigate", "playwright_scrape",
        "playwright_html", "playwright_click", "playwright_download",
        "filesystem_read", "filesystem_write", "filesystem_glob",
        "filesystem_tree", "filesystem_grep", "filesystem_diff",
        # 新增MCP（2026-06-08）
        # CNRDS
        "cnrd_patent", "cnrd_papers", "cnrd_company", "cnrd_financial",
        # SIPO
        "sipo_patent", "sipo_detail", "sipo_biblio", "sipo_litigation",
        # 第三方ESG
        "esg_rating", "esg_trend", "esg_controversy", "esg_ranking",
        # 中国海关
        "customs_import", "customs_export", "customs_balance", "customs_country",
        # 中文文献
        "chinese_literature", "chinese_paper_citations", "journal_info", "cssci_papers",
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


        # ── MCP Tool Entries (with proper inputs/outputs) ───────────────────────

        # ── BEA (美国经济分析局) ───────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["bea_data"] = ToolCapability(
            name="bea_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "quarter", "component"],
            outputs=["gdp_value", "gdp_components", "gdi"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美国经济分析局GDP/GDI数据（季度/年度，GDP构成）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["bea_gdp"] = ToolCapability(
            name="bea_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "quarter", "component"],
            outputs=["gdp_value", "gdp_components"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="BEA GDP数据（季度/年度，GDP构成）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["bea_gdi"] = ToolCapability(
            name="bea_gdi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["gdi_value"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="BEA国民总收入(GDI)数据",
            callable=None,
        )

        # ── CSMAR (国泰安) ──────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["csmar"] = ToolCapability(
            name="csmar",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "report_type", "start_date", "end_date"],
            outputs=["financial_data", "market_data", "corporate_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSMAR国泰安金融数据库（需机构账号，A股财务/交易/公司数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["csmar_financial"] = ToolCapability(
            name="csmar_financial",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "report_type", "start_date", "end_date"],
            outputs=["revenue", "net_profit", "total_assets", "equity"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSMAR财务数据（利润表/资产负债表/现金流量表）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["csmar_trading"] = ToolCapability(
            name="csmar_trading",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "start_date", "end_date"],
            outputs=["daily_returns", "volume", "turnover"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSMAR交易数据（个股日频交易数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["csmar_corporate"] = ToolCapability(
            name="csmar_corporate",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code"],
            outputs=["company_name", "industry", "listing_date", "delist_date"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSMAR公司基本信息和治理数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["csmar_analyst"] = ToolCapability(
            name="csmar_analyst",
            task_types=[TaskType.DATA_FETCH],
            inputs=["analyst_name", "year"],
            outputs=["forecast_eps", "rating", "institution"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSMAR分析师数据和盈利预测",
            callable=None,
        )

        # ── e2b (云端沙箱) ──────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["e2b"] = ToolCapability(
            name="e2b",
            task_types=[TaskType.CODE],
            inputs=["code", "language", "timeout"],
            outputs=["stdout", "stderr", "execution_time"],
            priority=2,
            cost=CostTier.LOW,
            requires_vpn=False,
            description="云端Python代码执行沙箱（完全隔离，适合运行未知代码）",
            callable=None,
        )

        # ── 东方财富债券 ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eastmoney_bond"] = ToolCapability(
            name="eastmoney_bond",
            task_types=[TaskType.DATA_FETCH],
            inputs=["bond_type", "start_date", "end_date"],
            outputs=["bond_yield", "repo_rate", "spot_price"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富债券数据（国债收益率曲线/债券回购/现券交易）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_bond_yield"] = ToolCapability(
            name="eastmoney_bond_yield",
            task_types=[TaskType.DATA_FETCH],
            inputs=["bond_type", "year"],
            outputs=["yield_curve", "maturity", "yield"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国债收益率曲线（东方财富）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_bond_repo"] = ToolCapability(
            name="eastmoney_bond_repo",
            task_types=[TaskType.DATA_FETCH],
            inputs=["date"],
            outputs=["repo_rate", "volume", "term"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="银行间债券回购数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_bond_spot"] = ToolCapability(
            name="eastmoney_bond_spot",
            task_types=[TaskType.DATA_FETCH],
            inputs=["bond_code"],
            outputs=["spot_price", "volume", "bid", "ask"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="债券现券交易数据",
            callable=None,
        )

        # ── 东方财富基金 ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eastmoney_fund"] = ToolCapability(
            name="eastmoney_fund",
            task_types=[TaskType.DATA_FETCH],
            inputs=["fund_code", "start_date", "end_date"],
            outputs=["nav", "累计净值", "dividend"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富公募基金数据（净值/规模/持仓）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_fund_nav"] = ToolCapability(
            name="eastmoney_fund_nav",
            task_types=[TaskType.DATA_FETCH],
            inputs=["fund_code", "start_date", "end_date"],
            outputs=["nav", "累计净值", "dividend"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="公募基金净值数据（单位净值/累计净值/分红）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_fund_flow"] = ToolCapability(
            name="eastmoney_fund_flow",
            task_types=[TaskType.DATA_FETCH],
            inputs=["fund_code", "start_date", "end_date"],
            outputs=["申购量", "赎回量", "净申赎"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="公募基金申赎资金流向",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_fund_holdings"] = ToolCapability(
            name="eastmoney_fund_holdings",
            task_types=[TaskType.DATA_FETCH],
            inputs=["fund_code", "period"],
            outputs=["stock_code", "stock_name", "holding_ratio", "market_value"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="公募基金重仓股数据（个股持仓比例/市值）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_fund_perf"] = ToolCapability(
            name="eastmoney_fund_perf",
            task_types=[TaskType.DATA_FETCH],
            inputs=["fund_code", "start_date", "end_date"],
            outputs=["收益率", "年化收益", "最大回撤", "夏普比率"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="公募基金业绩表现（收益率/最大回撤/夏普比率）",
            callable=None,
        )

        # ── 东方财富期权 ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eastmoney_option"] = ToolCapability(
            name="eastmoney_option",
            task_types=[TaskType.DATA_FETCH],
            inputs=["underlying", "expiry_date"],
            outputs=["strike", "iv", "delta", "gamma", "theta", "vega"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富期权数据（期权链/希腊值/波动率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_option_chain"] = ToolCapability(
            name="eastmoney_option_chain",
            task_types=[TaskType.DATA_FETCH],
            inputs=["underlying", "expiry_date"],
            outputs=["strike", "call_oi", "put_oi", "call_iv", "put_iv"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="期权链数据（行使价/未平仓量/隐含波动率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_option_greeks"] = ToolCapability(
            name="eastmoney_option_greeks",
            task_types=[TaskType.DATA_FETCH],
            inputs=["underlying", "expiry_date"],
            outputs=["delta", "gamma", "theta", "vega", "rho"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="期权希腊值（Greeks: Delta/Gamma/Theta/Vega/Rho）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_option_vol"] = ToolCapability(
            name="eastmoney_option_vol",
            task_types=[TaskType.DATA_FETCH],
            inputs=["underlying", "start_date", "end_date"],
            outputs=["hv_20d", "hv_60d", "iv_mean", "iv_rank"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="期权波动率数据（历史波动率HV/隐含波动率IV/IV Rank）",
            callable=None,
        )

        # ── 宏观数据聚合 ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["education_panel"] = ToolCapability(
            name="education_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "indicator", "start_year", "end_year"],
            outputs=["province", "year", "value", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="教育面板数据（高校数量/在校生/招生/毕业）",
            callable=None,
        )

        # ── 外汇/大宗商品/航运 ─────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["enhanced_finance"] = ToolCapability(
            name="enhanced_finance",
            task_types=[TaskType.DATA_FETCH],
            inputs=["data_type", "symbol", "start_date", "end_date"],
            outputs=["forex_rates", "commodity_prices", "shipping_index"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="外汇/大宗商品/航运指数（东方财富akshare）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_forex"] = ToolCapability(
            name="enhanced_forex",
            task_types=[TaskType.DATA_FETCH],
            inputs=[],
            outputs=["currency_pair", "base", "quote", "rate", "timestamp"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="外汇即期汇率（USD/EUR/GBP/JPY/HKD/AUD对CNY，主要货币对）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_forex_hist"] = ToolCapability(
            name="enhanced_forex_hist",
            task_types=[TaskType.DATA_FETCH],
            inputs=["currency_pair", "start_date", "end_date"],
            outputs=["date", "open", "high", "low", "close"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="外汇历史走势（指定货币对USD/CNY等，日频）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_commodity"] = ToolCapability(
            name="enhanced_commodity",
            task_types=[TaskType.DATA_FETCH],
            inputs=["commodity", "start_date", "end_date"],
            outputs=["date", "price", "unit", "open", "high", "low", "close"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="大宗商品价格（黄金/白银/布伦特原油/WTI原油）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_crypto"] = ToolCapability(
            name="enhanced_crypto",
            task_types=[TaskType.DATA_FETCH],
            inputs=["symbol", "start_date", "end_date"],
            outputs=["price", "volume", "market_cap"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="加密货币价格（BTC/ETH等主流币种）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_futures"] = ToolCapability(
            name="enhanced_futures",
            task_types=[TaskType.DATA_FETCH],
            inputs=["contract", "start_date", "end_date"],
            outputs=["price", "volume", "open_interest"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="期货价格数据（商品期货/金融期货）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["enhanced_shipping"] = ToolCapability(
            name="enhanced_shipping",
            task_types=[TaskType.DATA_FETCH],
            inputs=["index_name"],
            outputs=["date", "index_value", "change_pct"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="航运指数（BDI/BCI/BPI/BDTI/BCTI，波罗的海指数）",
            callable=None,
        )

        # ── EODHD (国债/经济日历) ────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eodhd"] = ToolCapability(
            name="eodhd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "country"],
            outputs=["yield_curve", "economic_events"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="EODHD API（美国国债收益率/经济日历，需EODHD_API_KEY）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eodhd_yield"] = ToolCapability(
            name="eodhd_yield",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "start_date", "end_date"],
            outputs=["date", "1m", "3m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美国国债收益率曲线（1M-30Y各期限，每日数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eodhd_indicators"] = ToolCapability(
            name="eodhd_indicators",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator", "country", "start_date", "end_date"],
            outputs=["date", "value", "previous", "forecast"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观经济指标（EODHD，需EODHD_API_KEY）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eodhd_events"] = ToolCapability(
            name="eodhd_events",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "start_date", "end_date", "limit"],
            outputs=["date", "time", "event", "impact", "previous", "forecast", "actual"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="全球经济事件日历（CPI/FOMC/非农等，需EODHD_API_KEY）",
            callable=None,
        )

        # ── Fed Data ───────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["fed_data"] = ToolCapability(
            name="fed_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=["series_id", "start_date", "end_date"],
            outputs=["federal_funds_rate", "fomc_events", "beige_book"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美联储数据（联邦基金利率/FOMC/褐皮书/收益率曲线）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["fed_rate"] = ToolCapability(
            name="fed_rate",
            task_types=[TaskType.DATA_FETCH],
            inputs=["series_id", "start_date", "end_date"],
            outputs=["date", "federal_funds_rate", "effective_rate"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="联邦基金利率（美联储FRED数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["fed_fomc"] = ToolCapability(
            name="fed_fomc",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "include_statement"],
            outputs=["date", "meeting_type", "decision", "statement", "minutes"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="FOMC会议日程和决议（含声明全文）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["fed_beige"] = ToolCapability(
            name="fed_beige",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["date", "region", "summary", "economic_conditions"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美联储褐皮书（各地区经济状况报告）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["fed_yield"] = ToolCapability(
            name="fed_yield",
            task_types=[TaskType.DATA_FETCH],
            inputs=["start_date", "end_date"],
            outputs=["date", "1m", "3m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美联储收益率曲线数据（FRED）",
            callable=None,
        )

        # ── 文件系统 ────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["filesystem"] = ToolCapability(
            name="filesystem",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path", "operation", "content"],
            outputs=["file_content", "file_list", "write_result"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="本地文件系统操作（读/写/列表/搜索文件）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_read"] = ToolCapability(
            name="filesystem_read",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path"],
            outputs=["content", "lines", "size"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="读取本地文件内容",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_write"] = ToolCapability(
            name="filesystem_write",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path", "content"],
            outputs=["success", "bytes_written"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="写入本地文件",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_glob"] = ToolCapability(
            name="filesystem_glob",
            task_types=[TaskType.DATA_FETCH],
            inputs=["pattern", "path"],
            outputs=["file_paths"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="按模式匹配文件路径（glob）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_tree"] = ToolCapability(
            name="filesystem_tree",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path", "max_depth"],
            outputs=["tree_structure"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="显示目录树结构",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_grep"] = ToolCapability(
            name="filesystem_grep",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path", "pattern", "regex"],
            outputs=["matches", "line_numbers"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="在文件中搜索文本（grep）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["filesystem_diff"] = ToolCapability(
            name="filesystem_diff",
            task_types=[TaskType.DATA_FETCH],
            inputs=["path1", "path2"],
            outputs=["diff_lines", "added", "removed"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="比较两个文件的差异",
            callable=None,
        )

        # ── 湖北省 ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["hubei_stats"] = ToolCapability(
            name="hubei_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator", "year"],
            outputs=["province", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省宏观经济指标（GDP/CPI/PPI/PMI/M2/FDI等）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_gdp"] = ToolCapability(
            name="hubei_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["province", "year", "gdp", "gdp_growth", "gdp_yoy"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省GDP季度数据（绝对值和同比增速）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_cpi"] = ToolCapability(
            name="hubei_cpi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "cpi", "cpi_yoy"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省CPI月度数据（同比/环比）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_ppi"] = ToolCapability(
            name="hubei_ppi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "ppi", "ppi_yoy"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省PPI月度数据（工业生产者出厂价格）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_pmi"] = ToolCapability(
            name="hubei_pmi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "pmi", "new_order", "production", "employment"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省PMI月度数据（制造业采购经理指数）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_m2"] = ToolCapability(
            name="hubei_m2",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "m2", "m2_yoy"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省M2货币供应量月度数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_fdi"] = ToolCapability(
            name="hubei_fdi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "fdi", "fdi_yoy"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省FDI实际使用外资月度数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_retail"] = ToolCapability(
            name="hubei_retail",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "retail_sales", "retail_yoy"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省社会消费品零售总额月度数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_industry"] = ToolCapability(
            name="hubei_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "month"],
            outputs=["province", "date", "industrial_output", "output_yoy"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省工业增加值月度数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_tech_contract"] = ToolCapability(
            name="hubei_tech_contract",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["province", "year", "contract_value", "tech_transfer"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省技术合同成交额（科技创新指标）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_rd"] = ToolCapability(
            name="hubei_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["province", "year", "rd_expenditure", "rd_intensity"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省R&D经费投入（研发强度）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["hubei_hitech"] = ToolCapability(
            name="hubei_hitech",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["province", "year", "hitech_count", "hitech_revenue"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省高新技术企业数量和营收",
            callable=None,
        )

        # ── IMF ─────────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["imf_data"] = ToolCapability(
            name="imf_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "start_year", "end_year"],
            outputs=["country", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="IMF世界经济展望(IFS/BOP)数据（无需API Key）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["imf_ifs"] = ToolCapability(
            name="imf_ifs",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "date", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="IMF国际金融统计(IFS)数据（汇率/储备/货币供应/利率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["imf_weo"] = ToolCapability(
            name="imf_weo",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "year"],
            outputs=["country", "year", "gdp_real", "gdp_nominal", "inflation", "unemployment"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="IMF世界经济展望(WEO)数据（GDP/通胀/失业预测）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["imf_bop"] = ToolCapability(
            name="imf_bop",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "date", "current_account", "capital_account", "financial_account", "reserve"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="IMF国际收支(BOP)数据（经常账户/资本账户/金融账户/储备）",
            callable=None,
        )

        # ── 产业/技术面板 ──────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["industry_panel"] = ToolCapability(
            name="industry_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=["industry", "province", "start_year", "end_year"],
            outputs=["industry", "province", "year", "output", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="工业产业面板数据（分行业/分省份产值）",
            callable=None,
        )

        # ── LaTeX ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["latex"] = ToolCapability(
            name="latex",
            task_types=[TaskType.CODE],
            inputs=["project_dir", "tex_file", "engine", "passes"],
            outputs=["pdf_path", "page_count", "errors", "warnings"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX编译（pdflatex/bibtex，支持自动检测主文件）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_check"] = ToolCapability(
            name="latex_check",
            task_types=[TaskType.CODE],
            inputs=["tex_file", "severity_filter"],
            outputs=["issues", "line_numbers", "severity", "description"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX语法检查（行号/类型/描述）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_diff"] = ToolCapability(
            name="latex_diff",
            task_types=[TaskType.CODE],
            inputs=["tex1", "tex2"],
            outputs=["diff_text", "added", "removed"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX文件差异对比",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_to_pdf"] = ToolCapability(
            name="latex_to_pdf",
            task_types=[TaskType.CODE],
            inputs=["tex_content", "engine"],
            outputs=["pdf_data", "errors"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX源码直接转PDF（内存中）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_formula"] = ToolCapability(
            name="latex_formula",
            task_types=[TaskType.CODE],
            inputs=["formula", "format"],
            outputs=["svg_data", "png_data", "errors"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX公式渲染为SVG/PNG图片",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_bibtex"] = ToolCapability(
            name="latex_bibtex",
            task_types=[TaskType.CODE],
            inputs=["bib_file"],
            outputs=["entries", "missing_fields", "duplicates"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="BibTeX文献格式检查（缺失字段/重复条目）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_scaffold"] = ToolCapability(
            name="latex_scaffold",
            task_types=[TaskType.CODE],
            inputs=["template", "output_dir"],
            outputs=["tex_files", "bib_file"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX论文脚手架生成（IEEE/AEA/JF等模板）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["latex_words"] = ToolCapability(
            name="latex_words",
            task_types=[TaskType.CODE],
            inputs=["tex_file", "include_bibliography"],
            outputs=["word_count", "char_count", "exclude_list"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="LaTeX字数统计（正文/参考文献/图表说明）",
            callable=None,
        )

        # ── CEIC ───────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["macro_ceic"] = ToolCapability(
            name="macro_ceic",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "indicator", "start_date", "end_date"],
            outputs=["date", "value", "source"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CEIC宏观数据库（中国经济/消费者/产业/贸易数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["ceic_macro"] = ToolCapability(
            name="ceic_macro",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "indicator", "start_date", "end_date"],
            outputs=["date", "value", "yoy", "mom"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CEIC宏观经济指标",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["ceic_consumer"] = ToolCapability(
            name="ceic_consumer",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "indicator", "start_date", "end_date"],
            outputs=["date", "value", "index"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CEIC消费者信心指数",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["ceic_industry"] = ToolCapability(
            name="ceic_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "industry", "start_date", "end_date"],
            outputs=["date", "output", "capacity_utilization"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CEIC工业产业数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["ceic_trade"] = ToolCapability(
            name="ceic_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country", "start_date", "end_date"],
            outputs=["date", "exports", "imports", "trade_balance"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CEIC进出口贸易数据",
            callable=None,
        )

        # ── 宏观数据聚合 ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["macro_datas"] = ToolCapability(
            name="macro_datas",
            task_types=[TaskType.DATA_FETCH],
            inputs=["data_type", "province", "start_year", "end_year"],
            outputs=["panel_data", "province", "year", "value"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观数据聚合（R&D/科技/产业/教育面板）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats"] = ToolCapability(
            name="macro_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "start_year", "end_year"],
            outputs=["country", "year", "value"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计数据（GDP/人口/贸易/通胀/失业/科技）",
            callable=None,
        )

        # ── NBER ───────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["nber_wp"] = ToolCapability(
            name="nber_wp",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "author", "year_from", "year_to", "limit"],
            outputs=["paper_id", "title", "authors", "year", "abstract", "jEL_codes"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="NBER工作论文检索（美国国家经济研究局，免费）",
            callable=None,
        )

        # ── NBS Fallback ─────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["nbs_fallback"] = ToolCapability(
            name="nbs_fallback",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator", "start_date", "end_date"],
            outputs=["date", "value", "source"],
            priority=3,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国家统计局数据备选来源（akshare fallback）",
            callable=None,
        )

        # ── NewsAPI ───────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["newsapi"] = ToolCapability(
            name="newsapi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["query", "from_date", "to_date", "language"],
            outputs=["title", "url", "description", "published_at", "source"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="全球财经新闻检索（NewsAPI，需NEWSAPI_API_KEY）",
            callable=None,
        )

        # ── NSTI ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["nsti_report"] = ToolCapability(
            name="nsti_report",
            task_types=[TaskType.DATA_FETCH],
            inputs=["report_type", "year"],
            outputs=["report_title", "content", "source"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国家科技信息年报数据",
            callable=None,
        )

        # ── OECD ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["oecd_data"] = ToolCapability(
            name="oecd_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "year_range"],
            outputs=["country", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OECD经济数据（GDP/就业/贸易/TFP，需API Key）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["oecd_gdp"] = ToolCapability(
            name="oecd_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "year_range"],
            outputs=["country", "year", "gdp", "gdp_growth", "gdp_per_capita"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OECD GDP数据（GDP/GDP增速/人均GDP）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["oecd_employment"] = ToolCapability(
            name="oecd_employment",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "year_range"],
            outputs=["country", "year", "unemployment_rate", "employment_rate", "labor_force"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OECD就业数据（失业率/就业率/劳动参与率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["oecd_trade"] = ToolCapability(
            name="oecd_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "year_range"],
            outputs=["country", "year", "exports", "imports", "trade_balance"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OECD贸易数据（进出口/贸易余额）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["oecd_tfp"] = ToolCapability(
            name="oecd_tfp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "year_range"],
            outputs=["country", "year", "tfp_level", "tfp_growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OECD TFP（全要素生产率）数据",
            callable=None,
        )

        # ── OpenAlex ──────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["openalex"] = ToolCapability(
            name="openalex",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "per_page", "page", "filter", "sort"],
            outputs=["work_id", "title", "authors", "year", "cited_by_count", "doi", "abstract"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OpenAlex学术论文检索（2亿+论文/作者/机构，完全免费）",
            callable=None,
        )

        # ── Pandas ─────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["pandas"] = ToolCapability(
            name="pandas",
            task_types=[TaskType.ANALYSIS],
            inputs=["path", "name", "encoding"],
            outputs=["dataframe", "shape", "columns", "dtypes"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="读取CSV/JSON/Excel/Parquet文件为DataFrame",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["pandas_describe"] = ToolCapability(
            name="pandas_describe",
            task_types=[TaskType.ANALYSIS],
            inputs=["name", "columns", "percentiles"],
            outputs=["mean", "std", "min", "max", "25%", "50%", "75%", "count"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="描述性统计（均值/标准差/分位数/极值）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["pandas_filter"] = ToolCapability(
            name="pandas_filter",
            task_types=[TaskType.ANALYSIS],
            inputs=["name", "conditions", "save_as"],
            outputs=["filtered_dataframe", "rows", "shape"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="按条件筛选数据行（类似SQL WHERE）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["pandas_merge"] = ToolCapability(
            name="pandas_merge",
            task_types=[TaskType.ANALYSIS],
            inputs=["left_name", "right_name", "how", "on", "save_as"],
            outputs=["merged_dataframe", "shape", "keys"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="合并两个DataFrame（inner/left/right/outer join）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["pandas_corr"] = ToolCapability(
            name="pandas_corr",
            task_types=[TaskType.ANALYSIS],
            inputs=["name", "columns", "method"],
            outputs=["correlation_matrix", "heatmap_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="相关性分析（Pearson/Spearman/Kendall）+热力图数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["pandas_sql"] = ToolCapability(
            name="pandas_sql",
            task_types=[TaskType.ANALYSIS],
            inputs=["query", "save_as"],
            outputs=["query_result", "rows", "columns"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="使用SQL查询DataFrame（pandasql）",
            callable=None,
        )

        # ── Playwright ────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["playwright"] = ToolCapability(
            name="playwright",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "action", "selector"],
            outputs=["html", "screenshot", "table_data", "text_content"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="浏览器自动化（截图/导航/抓取表格/点击）",
            callable=None,
        )

        # ── R&D面板 ──────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["rd_panel"] = ToolCapability(
            name="rd_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "start_year", "end_year"],
            outputs=["province", "year", "rd_expenditure", "rd_intensity", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="R&D经费面板数据（分省份/分行业）",
            callable=None,
        )

        # ── SQLite ───────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["sqlite"] = ToolCapability(
            name="sqlite",
            task_types=[TaskType.DATA_FETCH],
            inputs=["db_path", "query"],
            outputs=["rows", "columns", "query_result"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SQLite数据库查询",
            callable=None,
        )

        # ── 科技面板 ─────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["tech_panel"] = ToolCapability(
            name="tech_panel",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "indicator", "start_year", "end_year"],
            outputs=["province", "year", "patent_count", "tech_transfer", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="科技创新面板数据（专利/技术合同/高新产品）",
            callable=None,
        )

        # ── World Bank ───────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["wb_data"] = ToolCapability(
            name="wb_data",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "per_page"],
            outputs=["country", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行数据（GDP/人口/健康/教育/贸易/性别，完全免费）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_gdp_pc"] = ToolCapability(
            name="wb_gdp_pc",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "gdp_per_capita_usd", "gdp_per_capita_ppp"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行人均GDP（USD和PPP）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_gdp_usd"] = ToolCapability(
            name="wb_gdp_usd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "gdp_usd", "gdp_growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行GDP（美元计）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_indicator"] = ToolCapability(
            name="wb_indicator",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行任意指标（GDP/人口/健康/教育/债务等）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_inflation"] = ToolCapability(
            name="wb_inflation",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "inflation_rate", "cpi"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行通胀数据（CPI/通胀率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_population"] = ToolCapability(
            name="wb_population",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "population", "population_growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行人口数据（总量/增长率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_tech_rd"] = ToolCapability(
            name="wb_tech_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "rd_expenditure", "rd_intensity", "patents"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行科技/R&D数据（研发支出/专利）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_trade"] = ToolCapability(
            name="wb_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "exports", "imports", "trade_gdp"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行贸易数据（出口/进口/贸易占GDP比）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_unemployment"] = ToolCapability(
            name="wb_unemployment",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "unemployment_rate", "labor_force"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行失业率数据",
            callable=None,
        )

        # ── Wind ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["wind"] = ToolCapability(
            name="wind",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "indicator", "start_date", "end_date"],
            outputs=["wind_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Wind万得金融终端数据（需Wind账号）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wind_index"] = ToolCapability(
            name="wind_index",
            task_types=[TaskType.DATA_FETCH],
            inputs=["index_code", "start_date", "end_date"],
            outputs=["date", "close", "change_pct", "volume"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Wind股票指数数据（上证/深证/沪深300等）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wind_bond"] = ToolCapability(
            name="wind_bond",
            task_types=[TaskType.DATA_FETCH],
            inputs=["bond_code", "start_date", "end_date"],
            outputs=["date", "yield", "price"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Wind债券收益率数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wind_credit"] = ToolCapability(
            name="wind_credit",
            task_types=[TaskType.DATA_FETCH],
            inputs=["bond_code", "start_date", "end_date"],
            outputs=["date", "credit_spread", "rating"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Wind信用利差数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wind_futures"] = ToolCapability(
            name="wind_futures",
            task_types=[TaskType.DATA_FETCH],
            inputs=["contract_code", "start_date", "end_date"],
            outputs=["date", "close", "volume", "open_interest"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Wind期货数据（商品期货/金融期货）",
            callable=None,
        )

        # ── 武汉市 ────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["wuhan_stats"] = ToolCapability(
            name="wuhan_stats",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator", "year"],
            outputs=["city", "year", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市统计年鉴数据（GDP/工业/投资/贸易/教育/科技）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_gdp"] = ToolCapability(
            name="wuhan_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["city", "year", "gdp", "gdp_growth", "primary", "secondary", "tertiary"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市GDP历年数据（绝对值/增速/三产结构）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_industry"] = ToolCapability(
            name="wuhan_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "industry_type"],
            outputs=["city", "year", "industry", "output", "growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市工业产值数据（分行业）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_investment"] = ToolCapability(
            name="wuhan_investment",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "investment_type"],
            outputs=["city", "year", "fixed_asset_investment", "real_estate_investment"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市固定资产投资数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_trade"] = ToolCapability(
            name="wuhan_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "trade_type"],
            outputs=["city", "year", "exports", "imports", "trade_balance"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市进出口贸易数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_education"] = ToolCapability(
            name="wuhan_education",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "education_level"],
            outputs=["city", "year", "university_count", "enrollment", "graduates"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市高等教育数据（高校/在校生/毕业生）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wuhan_tech"] = ToolCapability(
            name="wuhan_tech",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "tech_indicator"],
            outputs=["city", "year", "patents", "tech_contracts", "hitech_companies"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="武汉市科技创新数据（专利/技术合同/高新企业）",
            callable=None,
        )

        # ── Yahoo Finance ────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["yfinance"] = ToolCapability(
            name="yfinance",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker"],
            outputs=["symbol", "price", "beta", "market_cap", "pe_ratio", "dividend_yield"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance实时报价（美股/ETF/期权/期货，无API Key）",
            callable=None,
        )

        # ── Yahoo Finance (additional tools) ─────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["yfinance_hist"] = ToolCapability(
            name="yfinance_hist",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "start_date", "end_date", "interval"],
            outputs=["date", "open", "high", "low", "close", "volume", "adj_close"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance股票历史行情（日/周/月频，含调整后收盘价）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["yfinance_financials"] = ToolCapability(
            name="yfinance_financials",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "statement_type"],
            outputs=["revenue", "net_income", "total_assets", "total_liabilities", "cash", "equity"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance财务报表（利润表/资产负债表/现金流量表/比率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["yfinance_etf"] = ToolCapability(
            name="yfinance_etf",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker"],
            outputs=["holding_symbol", "holding_weight", "holding_market_value", "holding_shares"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance ETF持仓明细（个股代码/权重/市值）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["yfinance_options"] = ToolCapability(
            name="yfinance_options",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "date"],
            outputs=["expiration_date", "strike", "call_put", "open_interest", "volume", "implied_volatility"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance股票期权数据（到期日/行使价/未平仓量/隐含波动率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["yfinance_news"] = ToolCapability(
            name="yfinance_news",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker"],
            outputs=["title", "publisher", "link", "provider", "published_at"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance个股新闻",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["yfinance_earnings"] = ToolCapability(
            name="yfinance_earnings",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker"],
            outputs=["earnings_date", "eps_estimate", "eps_actual", "revenue_estimate", "revenue_actual"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Yahoo Finance财报预期（EPS预测/实际/营收预测/实际）",
            callable=None,
        )

        # ── Tushare (additional tools) ────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["tushare_financial"] = ToolCapability(
            name="tushare_financial",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "report_type", "start_date", "end_date", "period"],
            outputs=["revenue", "net_profit", "total_assets", "total_liabilities", "equity"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Tushare A股财务数据（利润表/资产负债表/现金流量表/财务指标）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["tushare_index"] = ToolCapability(
            name="tushare_index",
            task_types=[TaskType.DATA_FETCH],
            inputs=["index_code", "start_date", "end_date"],
            outputs=["date", "open", "high", "low", "close", "volume", "turnover"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Tushare A股指数行情（上证指数/深证成指/沪深300等）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["tushare_stock_basic"] = ToolCapability(
            name="tushare_stock_basic",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "list_status"],
            outputs=["ts_code", "name", "industry", "market", "list_date", "delist_date"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Tushare A股股票基本信息（代码/名称/行业/上市状态）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["tushare_calendar"] = ToolCapability(
            name="tushare_calendar",
            task_types=[TaskType.DATA_FETCH],
            inputs=["exchange", "start_date", "end_date", "is_open"],
            outputs=["cal_date", "is_open", "pretrade_date"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Tushare A股交易日历（判断某日是否开市）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["tushare_concept"] = ToolCapability(
            name="tushare_concept",
            task_types=[TaskType.DATA_FETCH],
            inputs=["concept_name"],
            outputs=["ts_code", "stock_name", "in_date"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Tushare概念板块成分股（AI/锂电池/新能源等）",
            callable=None,
        )

        # ── SEC EDGAR ───────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["sec_edgar"] = ToolCapability(
            name="sec_edgar",
            task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["cik", "form_type", "limit"],
            outputs=["form_type", "filing_date", "description", "document_url"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SEC EDGAR公告列表（10-K/10-Q/8-K等，无需API Key）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sec_10k"] = ToolCapability(
            name="sec_10k",
            task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["cik", "year"],
            outputs=["filing_date", "content", "sections", "item_1", "item_7", "item_7a"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SEC 10-K年报全文（业务/财务/风险/MD&A章节）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sec_10q"] = ToolCapability(
            name="sec_10q",
            task_types=[TaskType.DATA_FETCH],
            inputs=["cik", "year", "quarter"],
            outputs=["filing_date", "content", "financial_statements"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SEC 10-Q季报全文",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sec_8k"] = ToolCapability(
            name="sec_8k",
            task_types=[TaskType.DATA_FETCH],
            inputs=["cik", "limit"],
            outputs=["filing_date", "event_type", "content"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SEC 8-K重大事件公告（财报发布/并购/高管变动等）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sec_ticker"] = ToolCapability(
            name="sec_ticker",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker"],
            outputs=["cik", "name", "sic", "state_of_incorporation"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="通过ticker查找公司CIK编号（SEC EDGAR）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sec_search"] = ToolCapability(
            name="sec_search",
            task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["company_name", "form_type", "date_from", "date_to"],
            outputs=["cik", "name", "form_type", "filing_date", "document_url"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SEC EDGAR公司搜索（按名称/表单类型/日期范围）",
            callable=None,
        )

        # ── 东方财富研报/新闻/分析师 ─────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eastmoney_news"] = ToolCapability(
            name="eastmoney_news",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ts_code", "start_date", "end_date", "limit"],
            outputs=["title", "content", "pub_date", "source", "url"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富个股新闻（标题/内容/发布时间）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_analyst"] = ToolCapability(
            name="eastmoney_analyst",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year"],
            outputs=["rank", "analyst_name", "institution", "rating_count", "win_rate"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富券商分析师排名（年度最佳分析师）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["eastmoney_industry"] = ToolCapability(
            name="eastmoney_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["industry_code", "start_date", "end_date"],
            outputs=["industry_name", "date", "close", "change_pct", "volume"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富行业板块行情（行业涨跌/成交额）",
            callable=None,
        )

        # ── 宏观数据/World Bank (additional) ──────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["wb_gdp"] = ToolCapability(
            name="wb_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator", "per_page"],
            outputs=["country", "year", "gdp_usd", "gdp_growth", "gdp_per_capita"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行GDP数据（USD/GDP增速/人均GDP）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_population"] = ToolCapability(
            name="wb_population",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "population", "population_growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行人口数据（总量/增长率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_trade"] = ToolCapability(
            name="wb_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "exports", "imports", "trade_gdp"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行贸易数据（出口/进口/贸易占GDP比）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_debt"] = ToolCapability(
            name="wb_debt",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "total_debt", "short_term_debt", "long_term_debt"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行外债数据",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_health"] = ToolCapability(
            name="wb_health",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "life_expectancy", "fertility_rate", "co2_emissions"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行健康数据（预期寿命/生育率/CO2排放）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_education"] = ToolCapability(
            name="wb_education",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "school_enrollment", "literacy_rate"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行教育数据（入学率/识字率）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["wb_gender"] = ToolCapability(
            name="wb_gender",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "female_labor_participation", "gender_gap"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="世界银行性别数据（女性劳动参与率/性别差距指数）",
            callable=None,
        )

        # ── 宏观数据聚合 (additional) ─────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["macro_datas_rd"] = ToolCapability(
            name="macro_datas_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "start_year", "end_year"],
            outputs=["province", "year", "rd_expenditure", "rd_intensity", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="R&D面板数据（分省份研发经费和强度）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_datas_tech"] = ToolCapability(
            name="macro_datas_tech",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "start_year", "end_year"],
            outputs=["province", "year", "patents", "tech_contracts", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="科技面板数据（分省份专利和技术合同）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_datas_industry"] = ToolCapability(
            name="macro_datas_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "start_year", "end_year"],
            outputs=["province", "year", "industrial_output", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="产业面板数据（分省份工业产值）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_datas_edu"] = ToolCapability(
            name="macro_datas_edu",
            task_types=[TaskType.DATA_FETCH],
            inputs=["province", "start_year", "end_year"],
            outputs=["province", "year", "universities", "enrollment", "graduates", "panel_data"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="教育面板数据（分省份高校/在校生/毕业生）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_datas_nsti"] = ToolCapability(
            name="macro_datas_nsti",
            task_types=[TaskType.DATA_FETCH],
            inputs=["report_type", "year"],
            outputs=["report_title", "content", "source"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国家科技信息年报（NSTI报告）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_datas_nbs"] = ToolCapability(
            name="macro_datas_nbs",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator", "start_date", "end_date"],
            outputs=["date", "value", "yoy", "source"],
            priority=3,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国家统计局数据备选（NBS fallback via macro-stats）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_gdp"] = ToolCapability(
            name="macro_stats_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "gdp_usd", "gdp_growth"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计GDP（World Bank USD计）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_gdp_pc"] = ToolCapability(
            name="macro_stats_gdp_pc",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "gdp_per_capita_usd"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计人均GDP",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_pop"] = ToolCapability(
            name="macro_stats_pop",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "population"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计人口",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_trade"] = ToolCapability(
            name="macro_stats_trade",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "exports", "imports", "trade_balance"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计贸易",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_inflation"] = ToolCapability(
            name="macro_stats_inflation",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "inflation_rate"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计通胀",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_unemp"] = ToolCapability(
            name="macro_stats_unemp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "unemployment_rate"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计失业率",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_rd"] = ToolCapability(
            name="macro_stats_rd",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code"],
            outputs=["country", "year", "rd_expenditure", "rd_intensity"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计研发投入",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["macro_stats_indicator"] = ToolCapability(
            name="macro_stats_indicator",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "indicator"],
            outputs=["country", "year", "value"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观统计任意指标（GDP/人口/通胀等）",
            callable=None,
        )

        # ── CryptoCompare ──────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["cryptocompare"] = ToolCapability(
            name="cryptocompare",
            task_types=[TaskType.DATA_FETCH],
            inputs=["symbol"],
            outputs=["price", "market_cap", "volume_24h", "change_24h", "high_24h", "low_24h"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CryptoCompare加密货币实时价格（BTC/ETH等主流币种）",
            callable=None,
        )

        # ── 中国海关 ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["customs_import"] = ToolCapability(
            name="customs_import",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "start_date", "end_date"],
            outputs=["date", "country", "import_value", "import_volume"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国海关进口数据（按国别/商品分类）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["customs_export"] = ToolCapability(
            name="customs_export",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "start_date", "end_date"],
            outputs=["date", "country", "export_value", "export_volume"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国海关出口数据（按国别/商品分类）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["customs_balance"] = ToolCapability(
            name="customs_balance",
            task_types=[TaskType.DATA_FETCH],
            inputs=["start_date", "end_date"],
            outputs=["date", "trade_balance", "exports", "imports"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国海关贸易差额（进出口总额/顺差逆差）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["customs_country"] = ToolCapability(
            name="customs_country",
            task_types=[TaskType.DATA_FETCH],
            inputs=["country_code", "trade_type", "start_date", "end_date"],
            outputs=["date", "country", "trade_value", "trade_volume", "main_products"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国与特定国家的双边贸易数据",
            callable=None,
        )

        # ── CNRDS ──────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["cnrd_patent"] = ToolCapability(
            name="cnrd_patent",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name", "year", "patent_type"],
            outputs=["patent_id", "title", "application_date", "grant_date", "patent_type"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CNRDS中国研究数据服务专利数据（企业专利申请/授权）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["cnrd_papers"] = ToolCapability(
            name="cnrd_papers",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "author", "year_from", "year_to", "limit"],
            outputs=["paper_id", "title", "authors", "journal", "year", "cited_by"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CNRDS学术论文检索（经济管理领域）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["cnrd_company"] = ToolCapability(
            name="cnrd_company",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name"],
            outputs=["company_id", "name", "industry", "province", "founded_year"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CNRDS企业基本信息（公司代码/名称/行业/省份）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["cnrd_financial"] = ToolCapability(
            name="cnrd_financial",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name", "report_type", "year"],
            outputs=["revenue", "net_profit", "total_assets", "equity", "report_period"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CNRDS企业财务数据（利润表/资产负债表）",
            callable=None,
        )

        # ── SIPO ───────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["sipo_patent"] = ToolCapability(
            name="sipo_patent",
            task_types=[TaskType.DATA_FETCH],
            inputs=["query", "patent_type", "date_from", "date_to"],
            outputs=["patent_id", "title", "applicant", "inventor", "application_date", "patent_type"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="国家知识产权局专利检索（发明/实用新型/外观设计）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sipo_detail"] = ToolCapability(
            name="sipo_detail",
            task_types=[TaskType.DATA_FETCH],
            inputs=["patent_id"],
            outputs=["patent_id", "title", "abstract", "claims", "legal_status"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SIPO专利详情（摘要/权利要求书/法律状态）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sipo_biblio"] = ToolCapability(
            name="sipo_biblio",
            task_types=[TaskType.DATA_FETCH],
            inputs=["patent_id"],
            outputs=["patent_id", "applicant", "inventor", "ipc_class", "application_date", "publication_date"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SIPO专利著录项目（申请人/发明人/IPC分类）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["sipo_litigation"] = ToolCapability(
            name="sipo_litigation",
            task_types=[TaskType.DATA_FETCH],
            inputs=["patent_id"],
            outputs=["case_id", "patent_id", "litigation_type", "judgment_date", "result"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="SIPO专利诉讼数据（侵权诉讼/无效宣告）",
            callable=None,
        )

        # ── ESG ─────────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["esg_rating"] = ToolCapability(
            name="esg_rating",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name", "year"],
            outputs=["company", "year", "esg_score", "e_score", "s_score", "g_score", "rating_agency"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="企业ESG评分（环境/社会/治理三个维度）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["esg_trend"] = ToolCapability(
            name="esg_trend",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name", "start_year", "end_year"],
            outputs=["company", "year", "esg_score", "e_score", "s_score", "g_score"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="企业ESG评分趋势（多年时间序列）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["esg_controversy"] = ToolCapability(
            name="esg_controversy",
            task_types=[TaskType.DATA_FETCH],
            inputs=["company_name", "limit"],
            outputs=["company", "controversy_date", "category", "severity", "description"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="企业ESG争议事件（环境违规/社会争议/治理问题）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["esg_ranking"] = ToolCapability(
            name="esg_ranking",
            task_types=[TaskType.DATA_FETCH],
            inputs=["industry", "year", "limit"],
            outputs=["rank", "company", "esg_score", "industry"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="ESG评分行业排名（按行业分组排名）",
            callable=None,
        )

        # ── 中文文献 ────────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["chinese_literature"] = ToolCapability(
            name="chinese_literature",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "max_results"],
            outputs=["title", "authors", "journal", "year", "doi", "cited_by", "abstract"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中文文献检索（百度学术+OpenAlex，经济金融管理领域）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["chinese_paper_citations"] = ToolCapability(
            name="chinese_paper_citations",
            task_types=[TaskType.LITERATURE],
            inputs=["paper_id", "limit"],
            outputs=["cited_title", "cited_authors", "cited_year", "citation_context"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中文学术论文引用关系（被引用文献列表）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["journal_info"] = ToolCapability(
            name="journal_info",
            task_types=[TaskType.LITERATURE],
            inputs=["journal_name"],
            outputs=["journal_name", "issn", "publisher", "impact_factor", "category", "ranking"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中文期刊信息（ISSN/出版社/影响因子/分类）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["cssci_papers"] = ToolCapability(
            name="cssci_papers",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "year_from", "year_to", "limit"],
            outputs=["title", "authors", "journal", "year", "cited_by", "cssci_category"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="CSSCI来源期刊论文检索（中文社会科学引文索引）",
            callable=None,
        )

        # ── Playwright (browser automation) ──────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["playwright"] = ToolCapability(
            name="playwright",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "action", "selector"],
            outputs=["html", "screenshot", "table_data", "text_content"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="浏览器自动化（截图/导航/抓取表格/点击）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_screenshot"] = ToolCapability(
            name="playwright_screenshot",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "full_page", "selector"],
            outputs=["screenshot_base64", "width", "height"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="网页截图（指定URL，支持全页/元素截图）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_navigate"] = ToolCapability(
            name="playwright_navigate",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "wait_for", "timeout"],
            outputs=["page_title", "final_url", "load_time"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="网页导航（打开URL，等待元素加载）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_scrape"] = ToolCapability(
            name="playwright_scrape",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "table_selector", "wait_for"],
            outputs=["table_data", "headers", "rows", "columns"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="网页表格抓取（CSS选择器定位表格，返回行列数据）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_html"] = ToolCapability(
            name="playwright_html",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "selector"],
            outputs=["html_content", "text_content"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="获取网页HTML源码（支持CSS选择器提取特定元素）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_click"] = ToolCapability(
            name="playwright_click",
            task_types=[TaskType.DATA_FETCH],
            inputs=["selector", "wait_for_navigation"],
            outputs=["clicked_element", "navigation_url"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="模拟鼠标点击（点击按钮/链接，等待页面跳转）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["playwright_download"] = ToolCapability(
            name="playwright_download",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url", "save_path"],
            outputs=["file_path", "file_size", "content_type"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="下载网页资源（PDF/Excel/CSV等文件）",
            callable=None,
        )

        # ── Semantic Scholar ──────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["semantic_scholar"] = ToolCapability(
            name="semantic_scholar",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "year_from", "year_to", "limit", "open_access_only"],
            outputs=["paper_id", "title", "authors", "year", "venue", "cited_by_count", "abstract"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="Semantic Scholar学术检索（AI免费层，支持论文详情/引用/关键词提取）",
            callable=None,
        )

        # ── 中国宏观 (aliases — all map to get_macro_china) ──────────────────────
        cls.TOOL_REGISTRY_BASE["financial_cpi"] = ToolCapability(
            name="financial_cpi",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator"],
            outputs=["date", "value", "yoy", "mom"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国CPI月度数据（akshare，东方财富接口）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["financial_gdp"] = ToolCapability(
            name="financial_gdp",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator"],
            outputs=["date", "value", "yoy", "quarter"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国GDP季度数据（akshare，东方财富接口）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["financial_m2"] = ToolCapability(
            name="financial_m2",
            task_types=[TaskType.DATA_FETCH],
            inputs=["indicator"],
            outputs=["date", "value", "yoy"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="中国M2货币供应量月度数据（akshare，东方财富接口）",
            callable=None,
        )

        # ── 东方财富概念板块 ─────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["eastmoney_concept"] = ToolCapability(
            name="eastmoney_concept",
            task_types=[TaskType.DATA_FETCH],
            inputs=["data_type", "concept_name", "start_date", "end_date"],
            outputs=["concept_name", "price", "change_pct", "volume", "turnover"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富概念板块数据（板块列表/实时行情/历史走势）",
            callable=None,
        )

        # ── BEA (additional) ─────────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["bea_industry"] = ToolCapability(
            name="bea_industry",
            task_types=[TaskType.DATA_FETCH],
            inputs=["year", "industry_code"],
            outputs=["year", "industry", "value_added", "output"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="BEA产业数据（行业增加值/产出）",
            callable=None,
        )
        cls.TOOL_REGISTRY_BASE["bea_nipa"] = ToolCapability(
            name="bea_nipa",
            task_types=[TaskType.DATA_FETCH],
            inputs=["table_id", "year"],
            outputs=["year", "series", "value", "unit"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="BEA国民收入和生产账户(NIPA)数据",
            callable=None,
        )

        # ── 湖北省 (yearly alias) ────────────────────────────────────────────────
        cls.TOOL_REGISTRY_BASE["hubei_rd_yearly"] = ToolCapability(
            name="hubei_rd_yearly",
            task_types=[TaskType.DATA_FETCH],
            inputs=["start_year", "end_year"],
            outputs=["province", "year", "rd_expenditure", "rd_intensity", "rd_personnel"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="湖北省R&D经费年度面板数据（2007年至今）",
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
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

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

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = loop.run_in_executor(pool, lambda: asyncio.run(_do_call()))
                    return future.result(timeout=60)
            else:
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
