"""mcp_servers — FastMCP data server package.

Each subpackage is a self-contained MCP server (FastMCP 2.x):

    user_eastmoney_reports/   — 东方财富研报/新闻/分析师排名
    user_eastmoney_fund/      — 基金数据（净值/持仓/业绩）
    user_eastmoney_bond/      — 债券数据（收益率曲线/现券/回购）
    user_eastmoney_option/    — 期权数据（希腊值/波动率/链）
    user_financial/           — 全球宏观数据（WB API / akshare）
    user_enhanced_finance/    — 外汇/航运指数/白银/期货
    user_tushare/            — A股行情/财务/融资融券（需Token）
    user_bea_data/           — 美国经济分析局数据
    user_wb_data/            — 世界银行指标数据
    user_imf_data/           — IMF世界经济展望
    user_oecd_data/          — OECD经济数据
    user_fed_data/           — 美联储数据（利率/FOMC/褐皮书）
    user_eodhd/              — EOD Historical Data（宏观/日历）
    user_csmar/              — CSMAR 国泰安金融数据库
    user_nber_wp/            — NBER Working Papers
    user_province_stats/     — 中国省级统计数据
    user_hubei_stats/        — 湖北省统计数据
    user_macro_stats/        — 中国宏观统计（国家统计局/世界银行）
    user_macro_ceic/         — CEIC 全球经济数据库
    user_macro_datas/        — 宏观面板数据（教育/R&D/科技）
    user_wind/               — Wind 万得金融终端
    user_yfinance/           — 美股财务/ESG（yfinance）
    user_financial/          — 全球宏观（World Bank）
    user_enhanced_finance/   — 外汇/大宗商品
    user_playwright_mcp/     — Playwright 浏览器自动化
    user_filesystem_mcp/     — 文件系统操作

Each server exposes a `mcp` FastMCP instance that can be run directly:
    python -m mcp_servers.user_eastmoney_reports.server

Or via docker-compose (see docker-compose.yml).

All servers follow the FastMCP 2.x plugin convention:
    server.py must expose a `mcp: FastMCP` instance at module level.
    tools/*.json define tool schemas.
    SERVER_METADATA.json describes the server (id, name, description).
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# List of available server IDs (for dynamic discovery)
AVAILABLE_SERVERS: list[str] = [
    "user_eastmoney_reports",
    "user_eastmoney_fund",
    "user_eastmoney_bond",
    "user_eastmoney_option",
    "user_financial",
    "user_enhanced_finance",
    "user_tushare",
    "user_bea_data",
    "user_wb_data",
    "user_imf_data",
    "user_oecd_data",
    "user_fed_data",
    "user_eodhd",
    "user_csmar",
    "user_nber_wp",
    "user_province_stats",
    "user_hubei_stats",
    "user_macro_stats",
    "user_macro_ceic",
    "user_macro_datas",
    "user_wind",
    "user_yfinance",
    "user_playwright_mcp",
    "user_filesystem_mcp",
    # ── 新增（2026-06-04）────────────────────────────────────
    "user_context7",      # 学术论文全文（ArXiv/DOI）
    "user_openalex",      # 学术元数据（2亿+成果）
    "user_sec_edgar",    # 美国SEC公告
    "user_cryptocompare", # 加密货币
    "user_newsapi",      # 财经新闻聚合
]


def get_server_path(server_name: str) -> Path:
    """Get the directory path for a server."""
    return Path(__file__).parent / server_name


def list_available_servers() -> list[str]:
    """Return list of server IDs that have a server.py file."""
    available = []
    for name in AVAILABLE_SERVERS:
        server_file = get_server_path(name) / "server.py"
        if server_file.exists():
            available.append(name)
    return available


__all__ = [
    "AVAILABLE_SERVERS",
    "get_server_path",
    "list_available_servers",
]
