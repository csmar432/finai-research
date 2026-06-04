"""Enhanced Parallel Analyst Agents for Financial Research.

Reference: FinResearchAgent's 6 parallel analyst agents.

This module implements specialized analyst agents that work in parallel
to analyze different aspects of a financial instrument:

1. Fundamental Market Analyst - Industry trends, macro factors
2. Fundamental Financial Analyst - Financial statements, profitability, Dupont analysis
3. Competitive Analyst - Porter's Five Forces, moat analysis
4. Risk Analyst - Risk factors, tail risks, scenario analysis
5. Valuation Analyst - DCF, comparables, scenario valuation
6. Earnings Quality Analyst - Accruals, cash flow matching, Jones model

Enhancements (2026-05-25):
- P0-1: FundamentalFinancial杜邦分析自动化
- P0-1: Valuation分析师DCF多情景自动化
- P0-1: EarningsQuality分析师Jones模型
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Analyst Types ───────────────────────────────────────────────────────────────


class AnalystType(Enum):
    """Types of financial analysts."""
    FUNDAMENTAL_MARKET = "fundamental_market"
    FUNDAMENTAL_FINANCIAL = "fundamental_financial"
    COMPETITIVE = "competitive"
    RISK = "risk"
    VALUATION = "valuation"
    EARNINGS_QUALITY = "earnings_quality"


@dataclass
class AnalystConfig:
    """Configuration for an analyst agent."""
    analyst_type: AnalystType
    name: str
    role: str
    focus_areas: list[str]
    tools: list[str]
    max_iterations: int = 3
    temperature: float = 0.7


@dataclass
class AnalystResult:
    """Result from an analyst agent."""
    analyst_type: AnalystType
    status: str
    findings: dict[str, Any]
    confidence: float
    key_points: list[str]
    warnings: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class CompositeAnalysis:
    """Combined results from all analysts."""
    ticker: str
    timestamp: float
    analyst_results: dict[AnalystType, AnalystResult]
    consensus_view: str
    divergent_views: list[str]
    confidence: float
    total_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp,
            "analyst_results": {
                k.value: {
                    "status": v.status,
                    "findings": v.findings,
                    "confidence": v.confidence,
                    "key_points": v.key_points,
                    "warnings": v.warnings,
                }
                for k, v in self.analyst_results.items()
            },
            "consensus_view": self.consensus_view,
            "divergent_views": self.divergent_views,
            "confidence": self.confidence,
            "total_latency_ms": self.total_latency_ms,
        }


# ─── Analyst Agent Configurations ───────────────────────────────────────────────


ANALYST_CONFIGS: dict[AnalystType, AnalystConfig] = {
    AnalystType.FUNDAMENTAL_MARKET: AnalystConfig(
        analyst_type=AnalystType.FUNDAMENTAL_MARKET,
        name="基本面市场分析师",
        role="基本面市场分析师，专注于行业趋势和宏观经济因素分析",
        focus_areas=[
            "行业生命周期阶段",
            "市场规模和增长潜力",
            "宏观经济环境影响",
            "政策环境分析",
            "行业周期性",
        ],
        tools=["brave_search", "fetch", "fred"],
        max_iterations=2,
    ),
    AnalystType.FUNDAMENTAL_FINANCIAL: AnalystConfig(
        analyst_type=AnalystType.FUNDAMENTAL_FINANCIAL,
        name="财务分析师",
        role="财务分析师，专注于财务报表和盈利能力分析",
        focus_areas=[
            "收入质量和增长趋势",
            "毛利率和净利率分析",
            "资产效率(ROA, ROIC)",
            "现金流质量",
            "财务杠杆和偿债能力",
        ],
        tools=["financial", "yfinance", "akshare"],
        max_iterations=2,
    ),
    AnalystType.COMPETITIVE: AnalystConfig(
        analyst_type=AnalystType.COMPETITIVE,
        name="竞争分析分析师",
        role="竞争分析专家，专注于竞争格局和护城河分析",
        focus_areas=[
            "波特五力分析",
            "竞争格局演变",
            "护城河来源",
            "替代品威胁",
            "行业集中度变化",
        ],
        tools=["brave_search", "fetch"],
        max_iterations=2,
    ),
    AnalystType.RISK: AnalystConfig(
        analyst_type=AnalystType.RISK,
        name="风险分析师",
        role="风险分析专家，专注于风险识别和量化",
        focus_areas=[
            "经营风险识别",
            "财务风险评估",
            "市场风险因素",
            "尾部风险分析",
            "风险缓解措施",
        ],
        tools=["brave_search", "fetch"],
        max_iterations=2,
    ),
    AnalystType.VALUATION: AnalystConfig(
        analyst_type=AnalystType.VALUATION,
        name="估值分析师",
        role="估值专家，专注于多方法估值分析",
        focus_areas=[
            "DCF估值",
            "可比公司法估值",
            "相对估值倍数",
            "情景分析",
            "估值驱动因素敏感性",
        ],
        tools=["financial", "yfinance"],
        max_iterations=2,
    ),
    AnalystType.EARNINGS_QUALITY: AnalystConfig(
        analyst_type=AnalystType.EARNINGS_QUALITY,
        name="盈利质量分析师",
        role="盈利质量专家，专注于盈余质量评估",
        focus_areas=[
            "应计项目分析",
            "现金流与净利润匹配",
            "收入确认政策",
            "非经常性损益识别",
            "盈余管理迹象",
        ],
        tools=["sec_edgar", "financial"],
        max_iterations=2,
    ),
}


# ════════════════════════════════════════════════════════════════════════════════
# P0-1: Enhanced Financial Analysis - Dupont & Ratio Analysis
# ════════════════════════════════════════════════════════════════════════════════


@dataclass
class DupontDecomposition:
    """杜邦分析分解结果"""
    company: str
    year: int
    roe: float  # 净资产收益率
    net_margin: float  # 净利率
    asset_turnover: float  # 资产周转率
    equity_multiplier: float  # 权益乘数
    roa: float  # 资产收益率
    comparison: dict  # 与行业/公司历史对比


class EnhancedFinancialAnalyst:
    """
    增强版财务分析师 - 实现杜邦分析自动化

    功能：
    1. 自动获取财务数据（通过MCP或数据管道）
    2. 杜邦分析三因素分解：ROE = 净利率 × 资产周转率 × 权益乘数
    3. 与行业平均和历史趋势对比（从 config/industry_benchmarks.json 加载）
    4. 输出异常预警
    """

    _BENCHMARK_CACHE: dict | None = None

    def __init__(self, gateway=None, benchmarks_path: str | None = None):
        self.gateway = gateway
        self._benchmarks_path = benchmarks_path

    @classmethod
    def _load_benchmarks(cls, benchmarks_path: str | None = None) -> dict:
        """Load industry benchmarks from JSON config, with fallback to defaults."""
        if cls._BENCHMARK_CACHE is not None:
            return cls._BENCHMARK_CACHE

        if benchmarks_path is None:
            benchmarks_path = str(
                Path(__file__).parent.parent.parent / "config" / "industry_benchmarks.json"
            )
        try:
            import json
            data = json.loads(Path(benchmarks_path).read_text(encoding="utf-8"))
            # Normalize: support both flat keys and nested `industries` block
            if "industries" in data:
                cls._BENCHMARK_CACHE = data["industries"]
            else:
                # Legacy flat format
                cls._BENCHMARK_CACHE = {
                    k: v for k, v in data.items() if not k.startswith("_")
                }
            return cls._BENCHMARK_CACHE
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback hardcoded values (legacy flat format)
            return {
                "tech": {"roe": (5, 15, 30), "net_margin": (2, 12, 30), "roa": (2, 8, 18)},
                "finance": {"roe": (5, 12, 22), "net_margin": (15, 30, 50), "roa": (0.3, 1.2, 2.5)},
                "manufacturing": {"roe": (6, 12, 22), "net_margin": (2, 6, 15), "roa": (2, 6, 12)},
                "retail": {"roe": (5, 15, 30), "net_margin": (1, 4, 12), "roa": (2, 6, 15)},
                "healthcare": {"roe": (8, 16, 28), "net_margin": (5, 12, 25), "roa": (4, 10, 20)},
                "energy": {"roe": (3, 10, 20), "net_margin": (1, 5, 15), "roa": (1, 5, 12)},
                "real_estate": {"roe": (3, 8, 18), "net_margin": (2, 8, 20), "roa": (1, 3, 8)},
                "default": {"roe": (5, 12, 25), "net_margin": (2, 8, 20), "roa": (2, 6, 15)},
            }

    async def analyze_financial_health(
        self,
        ticker: str,
        financial_data: dict,
        industry: str = "default",
    ) -> dict:
        """
        综合财务健康分析

        Parameters
        ----------
        ticker : str
            股票代码
        financial_data : dict
            财务数据，应包含：
            - income_statement: 利润表
            - balance_sheet: 资产负债表
            - cash_flow: 现金流量表
        industry : str
            行业分类，用于对比

        Returns
        -------
        dict
            包含杜邦分析和预警的完整报告
        """
        # 提取财务指标
        income = financial_data.get("income_statement", {})
        balance = financial_data.get("balance_sheet", {})
        cash_flow = financial_data.get("cash_flow", {})

        # 计算核心财务指标
        revenue = income.get("revenue", income.get("total_revenue", 0))
        net_income = income.get("net_income", income.get("total_net_income", 0))
        total_assets = balance.get("total_assets", 0)
        equity = balance.get("total_equity", balance.get("shareholders_equity", 0))
        cfo = cash_flow.get("operating_cash_flow", cash_flow.get("cash_from_operations", 0))
        gross_profit = income.get("gross_profit", 0)
        ebit = income.get("ebit", income.get("operating_income", 0))

        # 避免除零
        revenue = max(revenue, 1)
        total_assets = max(total_assets, 1)
        equity = max(equity, 1)

        # ── 杜邦分析 ──────────────────────────────────────────────────────
        net_margin = net_income / revenue if revenue else 0
        asset_turnover = revenue / total_assets if total_assets else 0
        equity_multiplier = total_assets / equity if equity else 0
        roa = net_income / total_assets if total_assets else 0
        roe = net_income / equity if equity else 0

        # ── 盈利能力分析 ─────────────────────────────────────────────────
        gross_margin = gross_profit / revenue if revenue else 0
        ebit_margin = ebit / revenue if revenue else 0
        operating_margin = income.get("operating_income", 0) / revenue if revenue else 0

        # ── 偿债能力分析 ────────────────────────────────────────────────
        current_assets = balance.get("current_assets", 0)
        current_liabilities = balance.get("current_liabilities", 0)
        total_liabilities = balance.get("total_liabilities", balance.get("total_current_liabilities", 0))
        total_debt = balance.get("total_debt", balance.get("long_term_debt", 0))

        current_ratio = current_assets / current_liabilities if current_liabilities else 0
        debt_ratio = total_liabilities / total_assets if total_assets else 0
        interest_coverage = ebit / balance.get("interest_expense", 1) if balance.get("interest_expense", 0) else 0

        # ── 现金流分析 ──────────────────────────────────────────────────
        capex = abs(cash_flow.get("capex", cash_flow.get("capital_expenditure", 0)))
        free_cash_flow = cfo - capex if cfo else -capex
        cash_flow_ratio = cfo / net_income if net_income else 0

        # ── 预警检查 ────────────────────────────────────────────────────
        warnings = self._check_warnings(
            roe=roe,
            net_margin=net_margin,
            current_ratio=current_ratio,
            debt_ratio=debt_ratio,
            cash_flow_ratio=cash_flow_ratio,
            interest_coverage=interest_coverage,
        )

        # ── 与行业对比 ─────────────────────────────────────────────────
        benchmark = self._load_benchmarks(self._benchmarks_path).get(industry, self._load_benchmarks(self._benchmarks_path).get("default", {}))
        industry_comparison = self._compare_to_industry(
            roe=roe, net_margin=net_margin, roa=roa,
            benchmark=benchmark, industry=industry
        )

        return {
            # 杜邦分解
            "dupont": {
                "roe": round(roe * 100, 2),
                "net_margin": round(net_margin * 100, 2),
                "asset_turnover": round(asset_turnover, 2),
                "equity_multiplier": round(equity_multiplier, 2),
                "roa": round(roa * 100, 2),
                "formula": f"ROE = {net_margin:.1%} × {asset_turnover:.2f} × {equity_multiplier:.2f}",
            },
            # 盈利能力
            "profitability": {
                "gross_margin": round(gross_margin * 100, 2),
                "operating_margin": round(operating_margin * 100, 2),
                "ebit_margin": round(ebit_margin * 100, 2),
                "net_margin": round(net_margin * 100, 2),
            },
            # 偿债能力
            "solvency": {
                "current_ratio": round(current_ratio, 2),
                "debt_ratio": round(debt_ratio * 100, 2),
                "interest_coverage": round(interest_coverage, 2),
            },
            # 现金流
            "cash_flow": {
                "operating_cash_flow": cfo,
                "capex": capex,
                "free_cash_flow": free_cash_flow,
                "cash_flow_ratio": round(cash_flow_ratio, 2),
            },
            # 预警
            "warnings": warnings,
            # 行业对比
            "industry_comparison": industry_comparison,
        }

    def _check_warnings(
        self,
        roe: float,
        net_margin: float,
        current_ratio: float,
        debt_ratio: float,
        cash_flow_ratio: float,
        interest_coverage: float,
    ) -> list[str]:
        """检查财务指标异常并生成预警"""
        warnings = []

        if roe < 0:
            warnings.append("⚠️ 亏损：净资产收益率为负")
        elif roe < 5:
            warnings.append("⚠️ 低回报：ROE低于5%，盈利能力较弱")

        if net_margin < 0:
            warnings.append("⚠️ 亏损：净利率为负")
        elif net_margin < 2:
            warnings.append("⚠️ 低利润率：净利率低于2%")

        if current_ratio < 1:
            warnings.append("⚠️ 流动性风险：流动比率低于1，短期偿债压力")
        elif current_ratio < 1.5:
            warnings.append("⚠️ 流动性偏弱：流动比率低于1.5")

        if debt_ratio > 80:
            warnings.append("⚠️ 高杠杆：资产负债率超过80%，财务风险较高")
        elif debt_ratio > 60:
            warnings.append("⚠️ 偏高杠杆：资产负债率超过60%")

        if cash_flow_ratio < 0.5:
            warnings.append("⚠️ 现金流质量：经营现金流/净利润低于50%，需关注")
        elif cash_flow_ratio < 0.8:
            warnings.append("⚠️ 现金流质量：经营现金流/净利润低于80%")

        if interest_coverage < 1:
            warnings.append("⚠️ 利息覆盖不足：EBIT/利息支出 < 1")
        elif interest_coverage < 2:
            warnings.append("⚠️ 利息覆盖偏弱：EBIT/利息支出 < 2")

        return warnings if warnings else ["✅ 无明显异常"]

    def _compare_to_industry(
        self,
        roe: float,
        net_margin: float,
        roa: float,
        benchmark: dict,
        industry: str,
    ) -> dict:
        """与行业平均进行对比"""

        def _detect_range(b: dict, key: str) -> tuple:
            """Normalize a benchmark entry to (low, median, high) tuple.

            Supports both legacy flat format:  [5, 15, 30]  (percent values)
            and new nested format:             {"p25": 0.05, "median": 0.15, "p75": 0.30}  (decimal)
            """
            val = b.get(key)
            if val is None:
                return (0, 100, 200)  # No data available
            if isinstance(val, (list, tuple)):
                # Legacy: [low, median, high] in percentage points
                return (val[0], val[len(val) // 2], val[-1])
            if isinstance(val, dict):
                # New format: {"p25": ..., "median": ..., "p75": ...}
                p25 = val.get("p25", val.get("median", 0))
                median = val.get("median", val.get("p50", p25))
                p75 = val.get("p75", val.get("median", median))
                return (p25 * 100, median * 100, p75 * 100)
            return (0, 100, 200)

        def in_range(value: float, range_tuple: tuple) -> str:
            low, high = range_tuple[0], range_tuple[-1]
            if value < low:
                return "↓ 低于行业"
            elif value > high:
                return "↑ 高于行业"
            else:
                return "✓ 行业正常"

        roe_bench = _detect_range(benchmark, "roe")
        nm_bench = _detect_range(benchmark, "net_margin")
        roa_bench = _detect_range(benchmark, "roa")

        return {
            "industry": industry,
            "roe": {
                "value": round(roe * 100, 2),
                "status": in_range(roe * 100, roe_bench),
                "p25": roe_bench[0],
                "median": roe_bench[1],
                "p75": roe_bench[2],
            },
            "net_margin": {
                "value": round(net_margin * 100, 2),
                "status": in_range(net_margin * 100, nm_bench),
                "p25": nm_bench[0],
                "median": nm_bench[1],
                "p75": nm_bench[2],
            },
            "roa": {
                "value": round(roa * 100, 2),
                "status": in_range(roa * 100, roa_bench),
                "p25": roa_bench[0],
                "median": roa_bench[1],
                "p75": roa_bench[2],
            },
        }


# ════════════════════════════════════════════════════════════════════════════════
# P0-1: Enhanced Valuation - Multi-Scenario DCF
# ════════════════════════════════════════════════════════════════════════════════


@dataclass
class DCFScenario:
    """DCF情景分析"""
    name: str
    revenue_growth: float  # 营收增长率
    operating_margin: float  # 营业利润率
    terminal_growth: float  # 永续增长率
    wacc: float  # 加权平均资本成本
    equity_value: float  # 股权价值
    target_price: float  # 目标价
    upside: float  # 上涨空间


class EnhancedValuationAnalyst:
    """
    增强版估值分析师 - 实现多情景DCF自动化

    功能：
    1. 三情景DCF（乐观/基准/悲观）
    2. 可比公司法（市盈率、市净率、市销率）
    3. 敏感性分析矩阵
    4. 估值区间输出
    """

    def __init__(self, gateway=None):
        self.gateway = gateway

    def _extract_tax_rate(self, income: dict) -> tuple[float, str]:
        """Extract effective tax rate from income statement.

        Tries: income_tax / pretax_income, then falls back to statutory rates.
        Returns (tax_rate, source) tuple.
        """
        pretax_income = income.get(
            "pretax_income",
            income.get("income_before_tax",
            income.get("ebt", 0))
        )
        income_tax = income.get(
            "income_tax",
            income.get("tax_expense", 0)
        )
        if pretax_income and pretax_income > 0:
            tax_rate = min(max(income_tax / pretax_income, 0), 1)
            if tax_rate > 0:
                return tax_rate, "income_statement"

        # Fallback: Chinese statutory corporate tax (25%, 15% for high-tech, 10% for small)
        effective_rate = income.get("effective_tax_rate")
        if effective_rate and 0 < effective_rate <= 1:
            return effective_rate, "effective_rate_reported"

        return 0.25, "default_corporate_tax"

    def _compute_net_debt_ratio(self, balance: dict) -> tuple[float, str]:
        """Compute net debt ratio from balance sheet.

        Net debt = total_debt - cash_and_equivalents
        Returns (net_debt_ratio, source) tuple.
        """
        total_debt = balance.get(
            "total_debt",
            balance.get("short_term_borrowing",
            balance.get("long_term_debt", 0))
        )
        total_assets = balance.get("total_assets", 0)
        if not total_assets or total_assets <= 0:
            return 0.1, "default"

        cash = balance.get(
            "cash_and_equivalents",
            balance.get("cash",
            balance.get("monetary_fund", 0))
        )
        net_debt = max(total_debt - cash, 0)
        net_debt_ratio = net_debt / total_assets

        if net_debt_ratio > 0:
            return net_debt_ratio, "balance_sheet"

        # Alternative: total liabilities / total assets as debt ratio
        total_liabilities = balance.get("total_liabilities", 0)
        if total_liabilities and total_assets:
            ratio = total_liabilities / total_assets
            if 0 < ratio < 1:
                return ratio, "liabilities_to_assets"

        return 0.1, "default"

    def _compute_wacc_from_data(
        self,
        financial_data: dict,
        risk_free_rate: float = 0.03,
        market_risk_premium: float = 0.055,
        cost_of_debt: float = 0.05,
    ) -> tuple[float, str, str]:
        """Compute WACC from CAPM and capital structure.

        WACC = E/V * Re + D/V * Rd * (1 - T)

        Where Re = Rf + Beta * ERP (CAPM cost of equity).

        Parameters
        ----------
        financial_data : dict
            Contains income_statement, balance_sheet, optional beta, cost_of_debt.
        risk_free_rate : float
            Risk-free rate (default 3%, 10Y CNY government bond yield).
        market_risk_premium : float
            Market risk premium (default 5.5%).
        cost_of_debt : float
            Pre-tax cost of debt (default 5%).

        Returns
        -------
        tuple
            (wacc, wacc_source, note)
        """
        balance = financial_data.get("balance_sheet", {})
        income = financial_data.get("income_statement", {})

        # Capital structure
        total_assets = balance.get("total_assets", 0)
        equity_val = balance.get(
            "total_equity",
            balance.get("shareholders_equity", 0)
        )
        total_debt = balance.get(
            "total_debt",
            balance.get("short_term_borrowing",
            balance.get("long_term_debt", 0))
        )

        if not total_assets or total_assets <= 0:
            return 0.09, "default", "Insufficient data for WACC computation"

        E_over_V = equity_val / total_assets if equity_val else 0.5
        D_over_V = 1 - E_over_V

        # Cost of equity via CAPM
        beta = financial_data.get("beta")
        if beta is None:
            # Try to derive from balance sheet leverage (simplified)
            if total_debt > 0 and equity_val > 0:
                asset_beta = 0.85  # Unlevered beta assumption
                leverage_ratio = 1 + total_debt / max(equity_val, 1)
                beta = asset_beta * leverage_ratio
            else:
                beta = 1.0  # Market beta fallback

        cost_of_equity = risk_free_rate + beta * market_risk_premium

        # Tax rate
        tax_rate, _ = self._extract_tax_rate(income)

        # Cost of debt
        debt_rate = financial_data.get("cost_of_debt", cost_of_debt)

        # WACC formula
        wacc = E_over_V * cost_of_equity + D_over_V * debt_rate * (1 - tax_rate)

        note = (
            f"WACC = E/V*Re + D/V*Rd*(1-T) = "
            f"{E_over_V:.0%}*{cost_of_equity:.2%} + "
            f"{D_over_V:.0%}*{debt_rate:.2%}*(1-{tax_rate:.0%})"
        )
        return max(wacc, 0.05), "computed_capm", note

    async def analyze_valuation(
        self,
        ticker: str,
        financial_data: dict,
        market_data: dict,
        current_price: float = None,
    ) -> dict:
        """
        综合估值分析

        Parameters
        ----------
        ticker : str
            股票代码
        financial_data : dict
            财务数据
        market_data : dict
            市场数据（股价、市值等）
        current_price : float
            当前股价

        Returns
        -------
        dict
            包含DCF、可比公司、敏感性分析的完整报告
        """
        income = financial_data.get("income_statement", {})
        balance = financial_data.get("balance_sheet", {})

        # 提取基础数据
        revenue = income.get("revenue", income.get("total_revenue", 0))
        net_income = income.get("net_income", income.get("total_net_income", 0))
        equity = balance.get("total_equity", balance.get("shareholders_equity", 0))
        shares = market_data.get("shares_outstanding", income.get("shares_outstanding", 1))
        shares = max(shares, 1)

        # 当前价格
        if current_price is None:
            market_cap = market_data.get("market_cap", market_data.get("market_capitalization", 0))
            current_price = market_cap / shares if market_cap and shares > 1 else 0

        # ── DCF估值 ──────────────────────────────────────────────────────
        dcf_results, dcf_warnings = await self._dcf_valuation(
            ticker=ticker,
            revenue=revenue,
            net_income=net_income,
            current_price=current_price,
            financial_data=financial_data,  # Pass actual data for WACC/tax extraction
        )

        # ── 可比公司法 ────────────────────────────────────────────────────
        comp_results = await self._comparable_analysis(
            ticker=ticker,
            financial_data=financial_data,
            market_data=market_data,
            current_price=current_price,
        )

        # ── 敏感性分析 ────────────────────────────────────────────────────
        sensitivity = await self._sensitivity_analysis(
            base_value=dcf_results.get("base_case", {}).get("equity_value", 0),
            revenue=revenue,
            base_wacc=dcf_results.get("base_case", {}).get("wacc", 0.10),
        )

        # ── 综合估值区间 ──────────────────────────────────────────────────
        valuation_summary = self._summarize_valuation(
            dcf_results=dcf_results,
            comp_results=comp_results,
            current_price=current_price,
        )

        return {
            "dcf_scenarios": dcf_results,
            "dcf_warnings": dcf_warnings,
            "comparable_companies": comp_results,
            "sensitivity_matrix": sensitivity,
            "valuation_summary": valuation_summary,
        }

    async def _dcf_valuation(
        self,
        ticker: str,
        revenue: float,
        net_income: float,
        current_price: float,
        financial_data: dict | None = None,
    ) -> tuple[dict, list]:
        """
        多情景DCF估值

        DCF公式：
        V = Σ(FCFt / (1+WACC)^t) + TV / (1+WACC)^n

        其中：
        - FCFt = FCF in year t
        - TV = 终值 = FCFn × (1+g) / (WACC - g)
        - WACC = 加权平均资本成本
        - g = 永续增长率
        """
        scenarios = [
            # 乐观情景
            {
                "name": "乐观情景",
                "revenue_growth": 0.20,  # 20%营收增长
                "operating_margin": 0.20,  # 20%营业利润率
                "terminal_growth": 0.03,  # 3%永续增长
                "wacc": 0.09,  # 9% WACC
            },
            # 基准情景
            {
                "name": "基准情景",
                "revenue_growth": 0.12,  # 12%营收增长
                "operating_margin": 0.15,  # 15%营业利润率
                "terminal_growth": 0.025,  # 2.5%永续增长
                "wacc": 0.10,  # 10% WACC
            },
            # 悲观情景
            {
                "name": "悲观情景",
                "revenue_growth": 0.05,  # 5%营收增长
                "operating_margin": 0.10,  # 10%营业利润率
                "terminal_growth": 0.02,  # 2%永续增长
                "wacc": 0.12,  # 12% WACC
            },
        ]

        results = {}
        warnings = []
        for scenario in scenarios:
            equity_value, target_price, shares_source, provenance = self._calculate_dcf(
                revenue=revenue,
                revenue_growth=scenario["revenue_growth"],
                operating_margin=scenario["operating_margin"],
                terminal_growth=scenario["terminal_growth"],
                wacc=scenario["wacc"],
                financial_data=financial_data,
            )

            upside = (target_price / current_price - 1) if current_price > 0 else 0

            results[scenario["name"]] = {
                "revenue_growth": scenario["revenue_growth"],
                "operating_margin": scenario["operating_margin"],
                "terminal_growth": scenario["terminal_growth"],
                "wacc": provenance.get("wacc_used", scenario["wacc"]),
                "wacc_source": provenance.get("wacc_source", "scenario_default"),
                "tax_rate": provenance.get("tax_rate_used", 0.25),
                "equity_value": round(equity_value, 2),
                "target_price": round(target_price, 2),
                "upside": round(upside * 100, 2),
                "provenance": provenance,
            }

            if shares_source == "default_assumption":
                warnings.append(f"⚠️ {scenario['name']}使用默认股本假设")

            if provenance.get("wacc_source") == "default":
                warnings.append(f"⚠️ {scenario['name']} WACC使用默认值，建议从市场获取真实beta计算")

        return results, warnings

    def _calculate_dcf(
        self,
        revenue: float,
        revenue_growth: float,
        operating_margin: float,
        terminal_growth: float,
        wacc: float,
        years: int = 5,
        financial_data: dict | None = None,
    ) -> tuple[float, float, str, dict]:
        """
        Compute DCF valuation.

        Returns (equity_value, target_price, shares_source, provenance).
        """
        fin_data = financial_data or {}

        income = fin_data.get("income_statement", {})
        balance = fin_data.get("balance_sheet", {})

        # ── Tax rate: extract via dedicated method ─────────────────────
        tax_rate, tax_source = self._extract_tax_rate(income)
        provenance = {
            "source": "computed",
            "tax_rate_used": tax_rate,
            "tax_source": tax_source,
        }

        # ── Net debt ratio: extract via dedicated method ───────────────
        net_debt_ratio, nd_source = self._compute_net_debt_ratio(balance)
        provenance["net_debt_source"] = nd_source

        # ── WACC: compute via CAPM if data available ──────────────────
        if fin_data:
            wacc_computed, wacc_src, wacc_note = self._compute_wacc_from_data(fin_data)
            if wacc_src == "computed_capm" and wacc_computed > 0:
                wacc = wacc_computed
                provenance["wacc_source"] = "computed_capm"
                provenance["wacc_note"] = wacc_note
            else:
                provenance["wacc_source"] = "scenario_default"
                provenance["wacc_note"] = wacc_note
        else:
            provenance["wacc_source"] = "scenario_default"

        provenance["wacc_used"] = wacc

        # ── Project FCFs ─────────────────────────────────────────────
        fcf_list = []
        for year in range(1, years + 1):
            # Project FCF using simplified FCF margin model.
            # FCF = Revenue × Operating Margin × (1 - Tax Rate) × FCF Margin
            # where FCF Margin ≈ 0.7 assumes ~30% of operating cash flow goes toward
            # capex, working capital changes, and other non-operating costs.
            # This is a rough approximation suitable for illustrative valuations;
            # for production use, extract actual capex and depreciation from financials.
            projected_revenue = revenue * (1 + revenue_growth) ** year
            fcf = projected_revenue * operating_margin * (1 - tax_rate) * 0.7
            fcf_list.append(fcf)

        # ── Discount ──────────────────────────────────────────────────
        pv_fcf = sum(
            fcf / (1 + wacc) ** year
            for year, fcf in enumerate(fcf_list, 1)
        )

        # ── Terminal value ────────────────────────────────────────────
        terminal_fcf = fcf_list[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        pv_terminal = terminal_value / (1 + wacc) ** years

        # ── Equity value ─────────────────────────────────────────────
        enterprise_value = pv_fcf + pv_terminal

        shares = getattr(self, '_last_shares', None)
        shares_source: str
        if shares is None:
            shares = 1e8
            shares_source = "default_assumption"
            logger.warning("DCF: no shares data, using 1e8 — for illustration only")
        else:
            shares_source = "provided"

        equity_value = enterprise_value * (1 - net_debt_ratio)

        return equity_value, equity_value / shares, shares_source, provenance

    async def _comparable_analysis(
        self,
        ticker: str,
        financial_data: dict,
        market_data: dict,
        current_price: float,
    ) -> dict:
        """
        可比公司法估值

        使用市盈率、市净率、市销率三种方法
        """
        income = financial_data.get("income_statement", {})
        balance = financial_data.get("balance_sheet", {})

        # 提取指标
        net_income = income.get("net_income", income.get("total_net_income", 0))
        equity = balance.get("total_equity", balance.get("shareholders_equity", 0))
        revenue = income.get("revenue", income.get("total_revenue", 0))
        shares = market_data.get("shares_outstanding", income.get("shares_outstanding", None))
        if shares is None:
            shares = 1e8
            logger.warning(f"可比公司法：ticker={ticker} 未提供股本，默认使用1e8，结果仅供参考")

        eps = net_income / shares if shares else 0
        bvps = equity / shares if shares else 0
        ps = current_price / (revenue / shares) if revenue and shares else 0

        # 行业可比公司估值倍数（示例值，实际应从数据源获取）
        sector_multiples = {
            "pe": {"median": 20, "low": 12, "high": 35},
            "pb": {"median": 3, "low": 1.5, "high": 8},
            "ps": {"median": 5, "low": 2, "high": 15},
        }

        return {
            "pe": {
                "trailing_pe": round(current_price / eps, 2) if eps else None,
                "forward_pe": None,  # 需要前瞻EPS
                "sector_median": sector_multiples["pe"]["median"],
                "sector_range": [sector_multiples["pe"]["low"], sector_multiples["pe"]["high"]],
                "valuation_range": self._calculate_valuation_range(eps, sector_multiples["pe"]),
            },
            "pb": {
                "current_pb": round(current_price / bvps, 2) if bvps else None,
                "sector_median": sector_multiples["pb"]["median"],
                "sector_range": [sector_multiples["pb"]["low"], sector_multiples["pb"]["high"]],
                "valuation_range": self._calculate_valuation_range(bvps, sector_multiples["pb"]),
            },
            "ps": {
                "current_ps": round(ps, 2),
                "sector_median": sector_multiples["ps"]["median"],
                "sector_range": [sector_multiples["ps"]["low"], sector_multiples["ps"]["high"]],
            },
        }

    def _calculate_valuation_range(self, base_value: float, multiples: dict) -> dict:
        """计算估值区间"""
        low_price = base_value * multiples["low"]
        high_price = base_value * multiples["high"]
        return {
            "low": round(low_price, 2),
            "high": round(high_price, 2),
            "median": round(base_value * multiples["median"], 2),
        }

    async def _sensitivity_analysis(
        self,
        base_value: float,
        revenue: float,
        base_wacc: float,
    ) -> dict:
        """
        敏感性分析矩阵

        分析WACC和永续增长率变化对估值的影响
        """
        terminal_growths = [0.015, 0.02, 0.025, 0.03, 0.035]
        waccs = [0.08, 0.09, 0.10, 0.11, 0.12]

        matrix = []
        for tg in terminal_growths:
            row = []
            for wacc in waccs:
                # 简化计算
                if wacc <= tg:
                    row.append(None)  # 无效组合
                else:
                    # 调整终值
                    adj_value = base_value * (1 + (tg - 0.025)) / (1 + (wacc - base_wacc))
                    row.append(round(adj_value, 0))
            matrix.append({
                "terminal_growth": f"{tg:.1%}",
                "values": row,
            })

        return {
            "wacc_range": [f"{w:.0%}" for w in waccs],
            "terminal_growth_range": [f"{tg:.1%}" for tg in terminal_growths],
            "sensitivity_matrix": matrix,
        }

    def _summarize_valuation(
        self,
        dcf_results: dict,
        comp_results: dict,
        current_price: float,
    ) -> dict:
        """综合估值汇总"""
        # 收集各方法的目标价
        target_prices = []

        # DCF各情景
        for scenario, data in dcf_results.items():
            target_prices.append({
                "method": f"DCF-{scenario}",
                "price": data["target_price"],
                "upside": data["upside"],
            })

        # 可比公司法
        for method, data in comp_results.items():
            if "valuation_range" in data and data["valuation_range"]:
                range_data = data["valuation_range"]
                target_prices.append({
                    "method": f"可比-{method.upper()}",
                    "price": range_data.get("median", 0),
                    "upside": round((range_data.get("median", current_price) / current_price - 1) * 100, 2) if current_price else 0,
                })

        # 计算综合估值
        avg_target = sum(tp["price"] for tp in target_prices) / len(target_prices) if target_prices else current_price
        avg_upside = sum(tp["upside"] for tp in target_prices) / len(target_prices) if target_prices else 0

        # 估值区间
        all_prices = [tp["price"] for tp in target_prices if tp["price"]]
        low_price = min(all_prices) if all_prices else current_price
        high_price = max(all_prices) if all_prices else current_price

        return {
            "current_price": current_price,
            "average_target": round(avg_target, 2),
            "average_upside": round(avg_upside, 2),
            "valuation_range": {
                "low": round(low_price, 2),
                "high": round(high_price, 2),
            },
            "method_results": target_prices,
            "recommendation": self._generate_recommendation(avg_upside),
        }

    def _generate_recommendation(self, upside: float) -> str:
        """基于上涨空间生成推荐"""
        if upside > 30:
            return "强烈推荐 (Strong Buy)"
        elif upside > 15:
            return "推荐 (Buy)"
        elif upside > 0:
            return "持有 (Hold)"
        elif upside > -15:
            return "减持 (Reduce)"
        else:
            return "卖出 (Sell)"


# ════════════════════════════════════════════════════════════════════════════════
# P0-1: Enhanced Earnings Quality - Jones Model
# ════════════════════════════════════════════════════════════════════════════════


@dataclass
class AccrualsAnalysis:
    """应计项目分析结果"""
    year: int
    total_accruals: float  # 总应计项目
    abnormal_accruals: float  # 非正常应计项目
    discretionary_accruals: float  # 可操控应计项目
    is_suspicious: bool  # 是否可疑


class EnhancedEarningsQualityAnalyst:
    """
    增强版盈利质量分析师 - 实现Jones模型

    功能：
    1. 修正Jones模型计算非正常应计项目
    2. 现金流与净利润匹配分析
    3. 非经常性损益识别
    4. 盈余管理预警
    """

    def __init__(self, gateway=None):
        self.gateway = gateway

    async def analyze_earnings_quality(
        self,
        ticker: str,
        financial_data: dict,
        years: list = None,
    ) -> dict:
        """
        综合盈利质量分析

        Parameters
        ----------
        ticker : str
            股票代码
        financial_data : dict
            多年财务数据，格式：
            {
                2023: {income_statement, balance_sheet, cash_flow},
                2022: {...},
                ...
            }
        years : list
            分析的年份列表

        Returns
        -------
        dict
            包含应计项目分析、现金流匹配、非经常性损益的完整报告
        """
        if years is None:
            years = sorted(financial_data.keys(), reverse=True)

        # ── 应计项目分析 ─────────────────────────────────────────────────
        accruals_results = await self._calculate_accruals(financial_data, years)

        # ── 现金流匹配分析 ────────────────────────────────────────────────
        cash_flow_match = await self._analyze_cash_flow_match(financial_data, years)

        # ── 非经常性损益分析 ──────────────────────────────────────────────
        non_recurring = await self._identify_non_recurring_items(financial_data, years)

        # ── 盈余管理预警 ──────────────────────────────────────────────────
        warnings = self._generate_warnings(accruals_results, cash_flow_match, non_recurring)

        # ── 综合评分 ──────────────────────────────────────────────────────
        quality_score = self._calculate_quality_score(accruals_results, cash_flow_match, non_recurring)

        return {
            "accruals_analysis": accruals_results,
            "cash_flow_match": cash_flow_match,
            "non_recurring_items": non_recurring,
            "warnings": warnings,
            "earnings_quality_score": quality_score,
        }

    async def _calculate_accruals(
        self,
        financial_data: dict,
        years: list,
    ) -> list[AccrualsAnalysis]:
        """
        修正Jones模型计算非正常应计项目

        修正Jones模型：
        TA/AT-1 = α1(1/AT-1) + α2(ΔREV/AT-1 - ΔREC/AT-1) + α3(PPE/AT-1) + ε

        其中：
        - TA = 总应计项目 = NI - CFO
        - AT = 期初总资产
        - ΔREV = 营业收入变动
        - ΔREC = 应收账款变动
        - PPE = 固定资产净值
        - ε = 非正常应计项目
        """
        results = []
        sorted_years = sorted(years, reverse=True)

        for i, year in enumerate(sorted_years[:-1]):
            prev_year = sorted_years[i + 1] if i + 1 < len(sorted_years) else None
            if prev_year is None:
                continue

            curr_data = financial_data.get(year, {})
            prev_data = financial_data.get(prev_year, {})

            # 获取财务指标
            curr_income = curr_data.get("income_statement", {})
            curr_balance = curr_data.get("balance_sheet", {})
            curr_cash = curr_data.get("cash_flow", {})

            prev_balance = prev_data.get("balance_sheet", {})

            # 计算各变量
            ni = curr_income.get("net_income", 0)
            cfo = curr_cash.get("operating_cash_flow", 0)
            at_minus_1 = prev_balance.get("total_assets", 1)  # 期初总资产
            at_minus_1 = max(at_minus_1, 1)

            # 总应计项目 = 净利润 - 经营现金流
            ta = ni - cfo

            # ΔREV
            revenue = curr_income.get("revenue", 0)
            prev_income = prev_data.get("income_statement", {})
            prev_revenue = prev_income.get("revenue", 0)
            delta_rev = revenue - prev_revenue

            # ΔREC
            ar = curr_balance.get("accounts_receivable", 0)
            prev_ar = prev_balance.get("accounts_receivable", 0)
            delta_rec = ar - prev_ar

            # PPE
            ppe = curr_balance.get("property_plant_equipment", curr_balance.get("fixed_assets", 0))

            # 标准化
            ta_norm = ta / at_minus_1
            delta_rev_norm = delta_rev / at_minus_1
            delta_rec_norm = delta_rec / at_minus_1
            ppe_norm = ppe / at_minus_1

            # 简化：使用行业平均系数估算非正常应计项目
            # 实际应用中应使用回归分析确定系数
            normal_accruals = ta_norm * 0.6  # 简化假设
            abnormal_accruals = ta_norm - normal_accruals

            # 可操控应计项目（简化）
            discretionary = abnormal_accruals * 0.5

            # 预警阈值：|异常应计项目| > 0.05 为可疑
            is_suspicious = abs(abnormal_accruals) > 0.05

            results.append({
                "year": year,
                "net_income": ni,
                "operating_cash_flow": cfo,
                "total_accruals": ta,
                "total_accruals_norm": round(ta_norm * 100, 2),  # 百分比
                "abnormal_accruals_norm": round(abnormal_accruals * 100, 2),
                "discretionary_accruals_norm": round(discretionary * 100, 2),
                "is_suspicious": is_suspicious,
                "interpretation": self._interpret_accruals(abnormal_accruals),
            })

        return results

    def _interpret_accruals(self, abnormal_accruals: float) -> str:
        """解释应计项目含义"""
        if abnormal_accruals > 0.05:
            return "↑ 正向异常：可能存在收入虚增或费用少计"
        elif abnormal_accruals < -0.05:
            return "↓ 负向异常：可能存在大额冲销或收入虚减"
        else:
            return "✓ 正常范围内"

    async def _analyze_cash_flow_match(
        self,
        financial_data: dict,
        years: list,
    ) -> dict:
        """
        分析现金流与净利润的匹配度

        关键指标：
        - 经营现金流/净利润比率（应接近1）
        - 净利润现金含量（现金净流量/净利润）
        """
        results = []
        suspicious_years = []

        for year in years:
            data = financial_data.get(year, {})
            income = data.get("income_statement", {})
            cash_flow = data.get("cash_flow", {})

            ni = income.get("net_income", 0)
            cfo = cash_flow.get("operating_cash_flow", 0)

            if ni == 0:
                ratio = None
            else:
                ratio = cfo / ni

            # 判断匹配度
            if ratio is not None:
                if ratio < 0:
                    status = "❌ 现金流与净利润严重不匹配（可能存在操纵）"
                    suspicious_years.append(year)
                elif ratio < 0.5:
                    status = "⚠️ 现金流偏低，盈利质量存疑"
                elif ratio < 0.8:
                    status = "⚠️ 现金流偏弱"
                elif ratio <= 1.5:
                    status = "✓ 现金流正常"
                else:
                    status = "✓ 现金流充沛"

                results.append({
                    "year": year,
                    "net_income": ni,
                    "operating_cash_flow": cfo,
                    "ratio": round(ratio, 2) if ratio else None,
                    "status": status,
                })

        return {
            "yearly_analysis": results,
            "suspicious_years": suspicious_years,
            "overall_assessment": "存在盈利质量风险" if suspicious_years else "现金流匹配度良好",
        }

    async def _identify_non_recurring_items(
        self,
        financial_data: dict,
        years: list,
    ) -> dict:
        """
        识别非经常性损益项目

        非经常性损益包括：
        - 资产处置收益/损失
        - 政府补助
        - 投资收益
        - 公允价值变动损益
        - 营业外收支
        """
        results = []

        for year in years:
            data = financial_data.get(year, {})
            income = data.get("income_statement", {})

            # 提取非经常性项目
            non_recurring_items = {
                "asset_disposal": income.get("asset_disposal_gain", income.get("gain_on_disposal", 0)),
                "government_grants": income.get("government_grants", income.get("subsidy_income", 0)),
                "investment_income": income.get("investment_income", income.get("income_from_investments", 0)),
                "fair_value_change": income.get("fair_value_change", income.get("gain_from_fair_value", 0)),
                "non_operating": income.get("non_operating_income", 0) - income.get("non_operating_expense", 0),
            }

            total_non_recurring = sum(abs(v) for v in non_recurring_items.values())
            ni = income.get("net_income", 1)
            ni = max(abs(ni), 1)  # 避免除零

            # 计算非经常性损益占比
            non_recurring_ratio = total_non_recurring / abs(ni)

            # 判断是否依赖非经常性损益
            if non_recurring_ratio > 0.5:
                assessment = "⚠️ 高度依赖非经常性损益，主营业务盈利能力存疑"
            elif non_recurring_ratio > 0.2:
                assessment = "⚠️ 非经常性损益占比较高"
            else:
                assessment = "✓ 盈利主要来自经常性业务"

            results.append({
                "year": year,
                "items": non_recurring_items,
                "total_non_recurring": total_non_recurring,
                "ratio": round(non_recurring_ratio * 100, 2),
                "assessment": assessment,
            })

        return {
            "yearly_analysis": results,
            "summary": self._summarize_non_recurring(results),
        }

    def _summarize_non_recurring(self, results: list) -> str:
        """汇总非经常性损益分析"""
        if not results:
            return "数据不足"

        high_dependency_years = [
            r["year"] for r in results
            if r["ratio"] > 50
        ]

        if high_dependency_years:
            return f"⚠️ {len(high_dependency_years)}年高度依赖非经常性损益: {high_dependency_years}"
        else:
            return "✓ 盈利主要来自经常性业务，盈利质量良好"

    def _generate_warnings(
        self,
        accruals_results: list,
        cash_flow_match: dict,
        non_recurring: dict,
    ) -> list[str]:
        """生成综合预警"""
        warnings = []

        # 应计项目预警
        suspicious_accruals = [r for r in accruals_results if r.get("is_suspicious")]
        if suspicious_accruals:
            years = [r["year"] for r in suspicious_accruals]
            warnings.append(f"⚠️ 应计项目异常：{len(years)}年存在可疑应计项目 {years}")

        # 现金流预警
        if cash_flow_match.get("suspicious_years"):
            warnings.append(f"⚠️ 现金流异常：{cash_flow_match['suspicious_years']}年现金流与净利润不匹配")

        # 非经常性损益预警
        summary = non_recurring.get("summary", "")
        if "⚠️" in summary:
            warnings.append(f"⚠️ 非经常性损益：{summary}")

        return warnings if warnings else ["✅ 盈利质量无明显异常"]

    def _calculate_quality_score(
        self,
        accruals_results: list,
        cash_flow_match: dict,
        non_recurring: dict,
    ) -> dict:
        """
        计算盈利质量综合评分（0-100）

        评分维度：
        - 应计项目（30分）
        - 现金流匹配（40分）
        - 非经常性损益（30分）
        """
        # 应计项目评分
        suspicious_count = sum(1 for r in accruals_results if r.get("is_suspicious"))
        accruals_score = max(0, 30 - suspicious_count * 10)

        # 现金流评分
        suspicious_cf = len(cash_flow_match.get("suspicious_years", []))
        cf_score = max(0, 40 - suspicious_cf * 15)

        # 非经常性损益评分
        non_recurring_results = non_recurring.get("yearly_analysis", [])
        high_dependency = sum(1 for r in non_recurring_results if r.get("ratio", 0) > 50)
        nr_score = max(0, 30 - high_dependency * 10)

        total_score = accruals_score + cf_score + nr_score

        # 评级
        if total_score >= 90:
            rating = "AAA"
            interpretation = "盈利质量优秀"
        elif total_score >= 75:
            rating = "AA"
            interpretation = "盈利质量良好"
        elif total_score >= 60:
            rating = "A"
            interpretation = "盈利质量中等"
        elif total_score >= 40:
            rating = "B"
            interpretation = "盈利质量一般，存在风险"
        else:
            rating = "C"
            interpretation = "盈利质量较差，存在重大风险"

        return {
            "total_score": total_score,
            "rating": rating,
            "interpretation": interpretation,
            "components": {
                "accruals_score": accruals_score,
                "cash_flow_score": cf_score,
                "non_recurring_score": nr_score,
            },
        }


# ════════════════════════════════════════════════════════════════════════════════
# Original Base Analyst Agent (Enhanced with specialized subclasses)
# ════════════════════════════════════════════════════════════════════════════════


class BaseAnalystAgent:
    """Base class for analyst agents."""

    def __init__(self, config: AnalystConfig, gateway=None):
        self.config = config
        self.gateway = gateway

    async def analyze(
        self,
        ticker: str,
        context: dict[str, Any],
    ) -> AnalystResult:
        """Run the analyst agent."""
        start = time.time()
        findings = {}
        key_points = []
        warnings = []

        try:
            # Step 1: Gather relevant data
            data = await self._gather_data(ticker, context)

            # Step 2: Analyze each focus area
            for focus_area in self.config.focus_areas:
                analysis = await self._analyze_focus(focus_area, data, ticker)
                findings[focus_area] = analysis.get("result", "")
                key_points.extend(analysis.get("key_points", []))
                warnings.extend(analysis.get("warnings", []))

            # Step 3: Synthesize findings
            synthesis = await self._synthesize(findings, ticker)

            return AnalystResult(
                analyst_type=self.config.analyst_type,
                status="success",
                findings={
                    **findings,
                    "synthesis": synthesis,
                    "data_sources": list(data.keys()),
                },
                confidence=self._calculate_confidence(findings, warnings),
                key_points=key_points[:5],
                warnings=warnings[:3],
                latency_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"Analyst {self.config.name} failed: {e}")
            return AnalystResult(
                analyst_type=self.config.analyst_type,
                status="error",
                findings={"error": str(e)},
                confidence=0.0,
                key_points=[],
                warnings=[f"分析失败: {str(e)}"],
                latency_ms=(time.time() - start) * 1000,
            )

    async def _gather_data(
        self,
        ticker: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Gather relevant data for analysis."""
        return {
            "market_data": context.get("market_data", {}),
            "financial_data": context.get("financial_data", {}),
            "news": context.get("news", []),
        }

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """Analyze a specific focus area."""
        return {
            "result": f"Analysis of {focus_area} for {ticker}",
            "key_points": [f"Key insight on {focus_area}"],
            "warnings": [],
        }

    async def _synthesize(
        self,
        findings: dict[str, Any],
        ticker: str,
    ) -> str:
        """Synthesize findings into a summary."""
        return f"Summary of {self.config.name} analysis for {ticker}"

    def _calculate_confidence(
        self,
        findings: dict[str, Any],
        warnings: list[str],
    ) -> float:
        """Calculate confidence score based on completeness and warnings."""
        completeness = len(findings) / len(self.config.focus_areas) if self.config.focus_areas else 0
        warning_penalty = min(len(warnings) * 0.1, 0.3)
        return max(0.0, completeness - warning_penalty)


# ════════════════════════════════════════════════════════════════════════════════
# Specialized Analyst Agents
# ════════════════════════════════════════════════════════════════════════════════


class EnhancedFundamentalFinancialAgent(BaseAnalystAgent):
    """增强版财务分析师 - 集成杜邦分析"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)
        self._enhanced_analyst = EnhancedFinancialAnalyst(gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对财务分析师的特殊分析"""
        financial_data = data.get("financial_data", {})
        industry = data.get("industry", "default")

        if "资产效率" in focus_area or "ROA" in focus_area or "ROIC" in focus_area:
            # 使用增强版杜邦分析
            result = await self._enhanced_analyst.analyze_financial_health(
                ticker=ticker,
                financial_data=financial_data,
                industry=industry,
            )
            dupont = result.get("dupont", {})

            return {
                "result": f"杜邦分解：{dupont.get('formula', 'N/A')}\n"
                          f"ROE: {dupont.get('roe', 0):.2f}% | "
                          f"ROA: {dupont.get('roa', 0):.2f}%",
                "key_points": [
                    f"ROE = {dupont.get('roe', 0):.2f}%（{'高于' if dupont.get('roe', 0) > 10 else '低于'}行业平均）",
                    f"净利率: {dupont.get('net_margin', 0):.2f}%",
                    f"资产周转率: {dupont.get('asset_turnover', 0):.2f}x",
                ],
                "warnings": result.get("warnings", []),
            }

        # 其他分析保持通用
        return await super()._analyze_focus(focus_area, data, ticker)


class EnhancedValuationAgent(BaseAnalystAgent):
    """增强版估值分析师 - 集成DCF"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)
        self._enhanced_analyst = EnhancedValuationAnalyst(gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对估值分析师的特殊分析"""
        financial_data = data.get("financial_data", {})
        market_data = data.get("market_data", {})
        current_price = market_data.get("current_price", 0)

        if "DCF" in focus_area or "估值" in focus_area:
            result = await self._enhanced_analyst.analyze_valuation(
                ticker=ticker,
                financial_data=financial_data,
                market_data=market_data,
                current_price=current_price,
            )

            summary = result.get("valuation_summary", {})
            scenarios = result.get("dcf_scenarios", {})

            key_points = []
            for scenario_name, scenario_data in scenarios.items():
                tp = scenario_data.get("target_price", 0)
                upside = scenario_data.get("upside", 0)
                key_points.append(f"{scenario_name}: 目标价 {tp:.2f}元 ({upside:+.1f}%)")

            return {
                "result": f"估值摘要：当前价 {current_price:.2f}元\n"
                          f"平均目标价: {summary.get('average_target', 0):.2f}元 "
                          f"({summary.get('average_upside', 0):+.1f}%)\n"
                          f"估值区间: [{summary.get('valuation_range', {}).get('low', 0):.2f}, "
                          f"{summary.get('valuation_range', {}).get('high', 0):.2f}]\n"
                          f"推荐: {summary.get('recommendation', 'N/A')}",
                "key_points": key_points,
                "warnings": [],
            }

        return await super()._analyze_focus(focus_area, data, ticker)


class EnhancedEarningsQualityAgent(BaseAnalystAgent):
    """增强版盈利质量分析师 - 集成Jones模型"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)
        self._enhanced_analyst = EnhancedEarningsQualityAnalyst(gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对盈利质量分析师的特殊分析"""
        financial_data = data.get("financial_data", {})
        years = sorted(financial_data.keys(), reverse=True)

        if "应计" in focus_area or "盈余" in focus_area or "盈利质量" in focus_area:
            result = await self._enhanced_analyst.analyze_earnings_quality(
                ticker=ticker,
                financial_data=financial_data,
                years=years,
            )

            quality_score = result.get("earnings_quality_score", {})
            warnings = result.get("warnings", [])

            return {
                "result": f"盈利质量评分: {quality_score.get('rating', 'N/A')} "
                          f"({quality_score.get('total_score', 0):.0f}/100)\n"
                          f"评估: {quality_score.get('interpretation', 'N/A')}\n"
                          f"分项得分: 应计项目 {quality_score.get('components', {}).get('accruals_score', 0)}/30 | "
                          f"现金流 {quality_score.get('components', {}).get('cash_flow_score', 0)}/40 | "
                          f"非经常性损益 {quality_score.get('components', {}).get('non_recurring_score', 0)}/30",
                "key_points": [
                    f"盈利质量评级: {quality_score.get('rating', 'N/A')}",
                    f"综合评分: {quality_score.get('total_score', 0):.0f}分",
                ],
                "warnings": warnings,
            }

        return await super()._analyze_focus(focus_area, data, ticker)


class EnhancedMarketAnalyst(BaseAnalystAgent):
    """增强版市场分析师 - 集成宏观/政策/行业周期分析"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对市场分析师的特殊分析"""
        market_data = data.get("market_data", {})
        news = data.get("news", [])

        if "宏观" in focus_area or "经济" in focus_area or "GDP" in focus_area:
            prompt = f"""作为市场分析师，请分析以下公司/行业的宏观环境。

公司/行业: {ticker}
宏观关注点: {focus_area}

已知宏观数据: {market_data.get('macro_summary', '无')}

请从以下维度进行分析:
1. 当前宏观周期阶段（复苏/繁荣/滞胀/衰退）
2. 货币政策影响
3. 财政政策影响
4. 行业与宏观的相关性

请给出简洁的分析结论。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "政策" in focus_area:
            prompt = f"""作为市场分析师，请分析政策环境对以下公司/行业的影响。

公司/行业: {ticker}
新闻摘要: {'; '.join(str(n) for n in news[:5])}

请分析:
1. 近期重大政策变化
2. 政策对该行业的直接/间接影响
3. 政策不确定性风险

请给出简洁结论。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "行业" in focus_area or "周期" in focus_area or "市场规模" in focus_area:
            prompt = f"""作为市场分析师，请分析以下行业的市场规模和周期特征。

行业: {ticker}

请分析:
1. 行业所处生命周期阶段（导入期/成长期/成熟期/衰退期）
2. 市场规模估算
3. 行业周期性特征
4. 增长驱动因素

请给出结构化分析。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        return await super()._analyze_focus(focus_area, data, ticker)

    async def _llm_analyze(self, prompt: str) -> dict:
        """Use LLM for structured analysis."""
        if self.gateway:
            try:
                result = self.gateway.generate(prompt, task_hint="financial_analysis")
                text = result.response
                return {
                    "analysis": text[:500],
                    "key_points": [line.strip() for line in text.split("\n") if line.strip()][:3],
                    "warnings": [],
                }
            except Exception as e:
                logger.warning(f"Market analyst LLM call failed: {e}")
        return {"analysis": "分析不可用", "key_points": [], "warnings": [str(e)]}


class EnhancedCompetitiveAnalyst(BaseAnalystAgent):
    """增强版竞争分析分析师 - 集成波特五力和护城河分析"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对竞争分析的特殊分析"""
        market_data = data.get("market_data", {})
        news = data.get("news", [])

        if "波特" in focus_area or "五力" in focus_area:
            prompt = f"""作为竞争分析专家，请对以下公司进行波特五力分析。

公司: {ticker}

请分析以下五力:
1. 行业内现有竞争（竞争强度、主要对手、市场集中度）
2. 新进入者威胁（进入壁垒、高度/规模经济、品牌忠诚度）
3. 替代品威胁（替代品数量、价格性能比、用户转换成本）
4. 供应商议价能力（集中度、替代供应、转换成本）
5. 买家议价能力（集中度、信息透明度、转换成本）

请给出结构化分析。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "护城河" in focus_area or "壁垒" in focus_area:
            prompt = f"""作为竞争分析专家，请评估以下公司的护城河来源。

公司: {ticker}

请分析以下护城河类型:
1. 无形资产（品牌、专利、特许经营权）
2. 转换成本
3. 网络效应
4. 成本优势（流程、地点、规模经济）

请量化各护城河的强度（强/中/弱）。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "竞争" in focus_area or "集中度" in focus_area or "格局" in focus_area:
            prompt = f"""作为竞争分析专家，请分析行业竞争格局演变。

公司: {ticker}
市场数据: {market_data.get('summary', '无')}

请分析:
1. 行业竞争格局（分散/集中/双寡头/完全竞争）
2. 近3年竞争格局变化趋势
3. 主要竞争者的战略动向

请给出结构化分析。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        return await super()._analyze_focus(focus_area, data, ticker)

    async def _llm_analyze(self, prompt: str) -> dict:
        if self.gateway:
            try:
                result = self.gateway.generate(prompt, task_hint="financial_analysis")
                text = result.response
                return {
                    "analysis": text[:500],
                    "key_points": [line.strip() for line in text.split("\n") if line.strip()][:3],
                    "warnings": [],
                }
            except Exception as e:
                logger.warning(f"Competitive analyst LLM call failed: {e}")
        return {"analysis": "分析不可用", "key_points": [], "warnings": [str(e)]}


class EnhancedRiskAnalyst(BaseAnalystAgent):
    """增强版风险分析师 - 集成多维度风险量化"""

    def __init__(self, config: AnalystConfig, gateway=None):
        super().__init__(config, gateway)

    async def _analyze_focus(
        self,
        focus_area: str,
        data: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any]:
        """针对风险分析的特殊分析"""
        financial_data = data.get("financial_data", {})
        market_data = data.get("market_data", {})
        news = data.get("news", [])

        if "经营" in focus_area or "运营" in focus_area:
            prompt = f"""作为风险分析师，请识别以下公司的经营风险。

公司: {ticker}
财务摘要: {financial_data.get('summary', '无')}
新闻: {'; '.join(str(n) for n in news[:3])}

请分析:
1. 收入集中度风险（大客户依赖）
2. 成本结构风险（固定成本占比）
3. 供应链风险
4. 技术/产品过时风险
5. 管理层风险

请量化各风险等级（高/中/低）。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "财务" in focus_area or "杠杆" in focus_area or "偿债" in focus_area:
            prompt = f"""作为风险分析师，请评估以下公司的财务风险。

公司: {ticker}
财务数据: {financial_data.get('summary', '无')}

请分析:
1. 资产负债率及趋势
2. 流动比率/速动比率
3. 利息保障倍数
4. 净债务/EBITDA
5. 信用评级（如有）

请量化财务风险等级。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        if "市场" in focus_area or "尾部" in focus_area or "风险因素" in focus_area:
            prompt = f"""作为风险分析师，请评估以下公司的市场风险。

公司: {ticker}
市场数据: {market_data.get('summary', '无')}

请分析:
1. 股价波动率（历史波动率估算）
2. Beta系数（如可计算）
3. 行业系统性风险
4. 宏观经济敏感性
5. 尾部风险（最大单日跌幅估算）

请量化市场风险等级。"""
            result = await self._llm_analyze(prompt)
            return {
                "result": result.get("analysis", ""),
                "key_points": result.get("key_points", []),
                "warnings": result.get("warnings", []),
            }

        return await super()._analyze_focus(focus_area, data, ticker)

    async def _llm_analyze(self, prompt: str) -> dict:
        if self.gateway:
            try:
                result = self.gateway.generate(prompt, task_hint="financial_analysis")
                text = result.response
                return {
                    "analysis": text[:500],
                    "key_points": [line.strip() for line in text.split("\n") if line.strip()][:3],
                    "warnings": [],
                }
            except Exception as e:
                logger.warning(f"Risk analyst LLM call failed: {e}")
        return {"analysis": "分析不可用", "key_points": [], "warnings": [str(e)]}


# ════════════════════════════════════════════════════════════════════════════════
# Analyst Factory Registry
# ════════════════════════════════════════════════════════════════════════════════


class AnalystFactory:
    """
    分析师工厂类 - 使用注册表模式，支持运行时扩展

    使用方法：
        # 注册新的分析师类型
        AnalystFactory.register(AnalystType.CUSTOM, CustomAnalystAgent)

        # 创建分析师
        agent = AnalystFactory.create(AnalystType.CUSTOM, config, gateway)
    """

    _registry: dict[AnalystType, type[BaseAnalystAgent]] = {
        AnalystType.FUNDAMENTAL_MARKET: EnhancedMarketAnalyst,
        AnalystType.FUNDAMENTAL_FINANCIAL: EnhancedFundamentalFinancialAgent,
        AnalystType.COMPETITIVE: EnhancedCompetitiveAnalyst,
        AnalystType.RISK: EnhancedRiskAnalyst,
        AnalystType.VALUATION: EnhancedValuationAgent,
        AnalystType.EARNINGS_QUALITY: EnhancedEarningsQualityAgent,
    }

    @classmethod
    def register(cls, analyst_type: AnalystType, agent_class: type[BaseAnalystAgent]) -> None:
        """注册新的分析师类型"""
        cls._registry[analyst_type] = agent_class

    @classmethod
    def create(cls, analyst_type: AnalystType, config: AnalystConfig, gateway=None) -> BaseAnalystAgent:
        """创建分析师实例"""
        agent_class = cls._registry.get(analyst_type, BaseAnalystAgent)
        return agent_class(config, gateway)

    @classmethod
    def is_enhanced(cls, analyst_type: AnalystType) -> bool:
        """检查是否为增强版分析师"""
        enhanced_types = {
            AnalystType.FUNDAMENTAL_MARKET,
            AnalystType.FUNDAMENTAL_FINANCIAL,
            AnalystType.COMPETITIVE,
            AnalystType.RISK,
            AnalystType.VALUATION,
            AnalystType.EARNINGS_QUALITY,
        }
        return analyst_type in enhanced_types


# Parallel Analyst Orchestrator
# ════════════════════════════════════════════════════════════════════════════════


class ParallelAnalystOrchestrator:
    """
    Orchestrates parallel analysis by multiple specialist agents.

    Reference: FinResearchAgent's approach where 6 analyst agents
    run simultaneously to analyze different aspects.
    """

    def __init__(self, gateway=None, timeout: float = 30.0):
        """
        Initialize orchestrator.

        Parameters
        ----------
        gateway : object
            LLM gateway for agent calls
        timeout : float
            Timeout in seconds for each analyst (default 30s)
        """
        self.gateway = gateway
        self.timeout = timeout
        self.analysts: dict[AnalystType, BaseAnalystAgent] = {}
        self._initialize_analysts()

    def _initialize_analysts(self):
        """Initialize all analyst agents using factory pattern."""
        for analyst_type, config in ANALYST_CONFIGS.items():
            self.analysts[analyst_type] = AnalystFactory.create(analyst_type, config, self.gateway)

    async def run_parallel_analysis(
        self,
        ticker: str,
        context: dict[str, Any],
        analyst_types: list[AnalystType] | None = None,
        max_workers: int = 6,
    ) -> CompositeAnalysis:
        """
        Run parallel analysis by multiple analysts.
        """
        start = time.time()

        if analyst_types is None:
            analyst_types = list(ANALYST_CONFIGS.keys())

        tasks = []
        for analyst_type in analyst_types:
            if analyst_type in self.analysts:
                tasks.append(
                    self.analysts[analyst_type].analyze(ticker, context)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyst_results = {}
        for analyst_type, result in zip(analyst_types, results):
            if isinstance(result, Exception):
                analyst_results[analyst_type] = AnalystResult(
                    analyst_type=analyst_type,
                    status="error",
                    findings={"error": str(result)},
                    confidence=0.0,
                    key_points=[],
                    warnings=[f"Agent failed: {str(result)}"],
                )
            else:
                analyst_results[analyst_type] = result

        consensus, divergences = self._generate_consensus(analyst_results)

        confidences = [r.confidence for r in analyst_results.values() if r.status == "success"]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return CompositeAnalysis(
            ticker=ticker,
            timestamp=time.time(),
            analyst_results=analyst_results,
            consensus_view=consensus,
            divergent_views=divergences,
            confidence=overall_confidence,
            total_latency_ms=(time.time() - start) * 1000,
        )

    def _generate_consensus(
        self,
        results: dict[AnalystType, AnalystResult],
    ) -> tuple[str, list[str]]:
        """Generate consensus view and identify divergences."""
        all_key_points = []
        for result in results.values():
            if result.status == "success":
                all_key_points.extend(result.key_points)

        consensus = f"Based on {len(results)} analyst perspectives"

        divergences = []
        for result in results.values():
            if result.warnings:
                divergences.extend([
                    f"{result.analyst_type.value}: {w}"
                    for w in result.warnings[:2]
                ])

        return consensus, divergences[:5]

    def get_analyst(self, analyst_type: AnalystType) -> BaseAnalystAgent | None:
        """Get a specific analyst agent."""
        return self.analysts.get(analyst_type)

    def list_analysts(self) -> list[str]:
        """List all available analyst types."""
        return [a.value for a in ANALYST_CONFIGS.keys()]


# ─── CLI Interface ──────────────────────────────────────────────────────────────


async def main():
    """CLI interface for parallel analysts."""
    import argparse

    parser = argparse.ArgumentParser(description="Enhanced Parallel Analyst Agents")
    parser.add_argument("--ticker", type=str, required=True, help="Stock ticker")
    parser.add_argument("--analysts", type=str, help="Comma-separated analyst types")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    args = parser.parse_args()

    if args.analysts:
        analyst_types = [AnalystType(at) for at in args.analysts.split(",")]
    else:
        analyst_types = None

    orchestrator = ParallelAnalystOrchestrator()

    result = await orchestrator.run_parallel_analysis(
        ticker=args.ticker,
        context={},
        analyst_types=analyst_types,
    )

    if args.format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"# {args.ticker} 分析报告")
        print("")
        print(f"**综合置信度**: {result.confidence:.1%}")
        print(f"**总耗时**: {result.total_latency_ms:.0f}ms")
        print("")
        print("## 分析师结果")
        for analyst_type, analyst_result in result.analyst_results.items():
            status_icon = "✅" if analyst_result.status == "success" else "❌"
            print("")
            print(f"### {status_icon} {analyst_type.value}")
            print(f"置信度: {analyst_result.confidence:.1%}")
            if analyst_result.key_points:
                print("关键发现:")
                for point in analyst_result.key_points:
                    print(f"  - {point}")
            if analyst_result.warnings:
                print("警告:")
                for warning in analyst_result.warnings:
                    print(f"  - {warning}")



# ════════════════════════════════════════════════════════════════════════════════
# TushareDataAgent — A股专用数据 Agent
# ════════════════════════════════════════════════════════════════════════════════


class TushareDataAgent:
    """
    A股专用数据获取 Agent。

    通过 MCP 调用 Tushare Pro API 获取：
    - 日线行情（开盘/收盘/最高/最低/成交量/成交额）
    - 财务数据（利润表/资产负债表/现金流量表）
    - 股票基本信息（名称/行业/上市状态）
    - 融资融券数据
    - 指数数据
    - 北向资金

    使用方式：
        agent = TushareDataAgent()
        quote = agent.get_daily_quote("000001.SZ", "20240101", "20241231")
        fin = agent.get_financial_report("000001.SZ", "income")
    """

    def __init__(self, ts_code: str | None = None, auto_convert: bool = True):
        """
        Args:
            ts_code: 默认股票代码（可覆盖）
            auto_convert: 是否自动转换数据格式为分析友好格式
        """
        self.default_ts_code = ts_code
        self.auto_convert = auto_convert

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_daily_quote(
        self,
        ts_code: str | None = None,
        start_date: str = "",
        end_date: str = "",
        trade_date: str = "",
    ) -> dict:
        """
        获取A股日线行情数据。

        Args:
            ts_code: 股票代码，如 000001.SZ
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            trade_date: 指定交易日（优先于日期范围）

        Returns:
            dict，含 data/list 和 columns
        """
        code = ts_code or self.default_ts_code
        if not code:
            return {"_error": True, "message": "ts_code is required"}

        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_daily_quote",
            {"ts_code": code, "start_date": start_date, "end_date": end_date, "trade_date": trade_date},
        )
        return self._handle_result(result, "日线行情")

    def get_index_data(
        self,
        ts_code: str,
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """获取指数日线数据（支持沪深300/上证指数等）。"""
        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_index_data",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
        )
        return self._handle_result(result, "指数行情")

    def get_margin_data(self, data_type: str = "margin_detail") -> dict:
        """
        获取融资融券数据。

        Args:
            data_type: margin_detail | margin_total | hsgt
        """
        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_margin_data",
            {"data_type": data_type},
        )
        return self._handle_result(result, "融资融券")

    # ── Financial Data ───────────────────────────────────────────────────────

    def get_financial_report(
        self,
        ts_code: str | None = None,
        report_type: str = "income",
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """
        获取A股财务数据。

        Args:
            ts_code: 股票代码
            report_type: income | balance | cashflow | fina_indicator
            start_date: 开始日期
            end_date: 结束日期
        """
        code = ts_code or self.default_ts_code
        if not code:
            return {"_error": True, "message": "ts_code is required"}

        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_financial_report",
            {
                "ts_code": code,
                "report_type": report_type,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        return self._handle_result(result, "财务数据")

    def get_stock_basic(
        self,
        exchange: str = "",
        list_status: str = "L",
    ) -> dict:
        """
        获取股票基本信息列表。

        Args:
            exchange: SSE | SZSE | BSE | ""（全部）
            list_status: L（上市）| D（退市）| P（暂停）
        """
        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_stock_basic",
            {"exchange": exchange, "list_status": list_status},
        )
        return self._handle_result(result, "股票信息")

    def get_trade_calendar(
        self,
        start_date: str = "",
        end_date: str = "",
        exchange: str = "SSE",
    ) -> dict:
        """获取交易日历。"""
        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_trade_calendar",
            {"start_date": start_date, "end_date": end_date, "exchange": exchange},
        )
        return self._handle_result(result, "交易日历")

    def get_concept_stocks(self, category: str = "") -> dict:
        """获取概念股列表。"""
        from scripts.core.llm_gateway import call_mcp_tool
        result = call_mcp_tool(
            "user-tushare",
            "get_concept_stocks",
            {"category": category},
        )
        return self._handle_result(result, "概念股")

    # ── Helper ───────────────────────────────────────────────────────────────

    def _handle_result(self, result, data_name: str) -> dict:
        """统一处理 MCP 调用结果。"""
        if not result.success:
            return {
                "_error": True,
                "message": f"{data_name}获取失败: {result.error}",
                "is_mock": result.is_mock,
            }

        data = result.data or {}
        if data.get("_error"):
            return {"_error": True, "message": data.get("message", "unknown"), "is_mock": result.is_mock}

        if result.is_mock:
            data["_mock_warning"] = (
                f"⚠️ {data_name}数据来自模拟数据（非真实API）。"
                "请在 .env 中配置 TUSHARE_TOKEN 以获取真实数据。"
            )

        data["_is_mock"] = result.is_mock
        return data

    def get_full_analysis(
        self,
        ts_code: str | None = None,
        start_date: str = "20230101",
        end_date: str = "20241231",
    ) -> dict:
        """
        获取完整分析所需数据（行情+财务+融资融券）。

        Returns dict with keys: quote, financial_income, financial_balance,
        financial_cashflow, margin, is_mock_warning
        """
        code = ts_code or self.default_ts_code
        if not code:
            return {"_error": True, "message": "ts_code is required"}

        return {
            "quote": self.get_daily_quote(code, start_date, end_date),
            "financial_income": self.get_financial_report(code, "income", start_date, end_date),
            "financial_balance": self.get_financial_report(code, "balance", start_date, end_date),
            "financial_cashflow": self.get_financial_report(code, "cashflow", start_date, end_date),
            "margin": self.get_margin_data("margin_detail"),
            "stock_basic": self.get_stock_basic(exchange=""),
        }


if __name__ == "__main__":
    asyncio.run(main())
