# Tutorial 2: Writing a Financial Research Report

> Learn how to generate professional financial research reports for A-shares and global markets.

---

## Overview

The financial report pipeline generates institutional-grade research reports with:

- Executive Summary
- Financial Analysis (ROE, cash flows, DuPont analysis)
- Valuation (DCF, comparable multiples)
- Risk Assessment
- Investment Recommendation

---

## Pipeline Architecture

```
User Input (stock code, topic)
    │
    ├── TushareDataAgent ──→ A-share market data
    ├── YFinanceAgent ──────→ US stock data
    ├── MacroDataAgent ─────→ GDP, CPI, interest rates
    │
    ├── ParallelAnalystOrchestrator
    │   ├── FundamentalAnalyst ──→ Financial health
    │   ├── ValuationAnalyst ────→ DCF / Multiples
    │   ├── RiskAnalyst ─────────→ Risk factors
    │   ├── EarningsAnalyst ──────→ Earnings quality
    │   ├── CompetitiveAnalyst ───→ Competitive position
    │   └── MacroAnalyst ─────────→ Macro sensitivity
    │
    └── ResearchReportAgent ──→ Final report
```

---

## Using TushareDataAgent

> **Note**: TushareDataAgent requires `TUSHARE_TOKEN` in your `.env` file
> (not `TUSHARE_API_KEY`). Register at https://tushare.pro/register.

```python
from scripts.core.analyst_agents import TushareDataAgent

agent = TushareDataAgent(default_ts_code="000001.SZ")

# A-share daily quotes
quote = agent.get_daily_quote(
    ts_code="000001.SZ",
    start_date="20230101",
    end_date="20241231"
)

# Index data
index_data = agent.get_index_data(
    ts_code="000001.SH",   # 上证指数
    start_date="20230101",
    end_date="20241231"
)

# Financial statements
fin_data = agent.get_financial_report(
    ts_code="000001.SZ",
    report_type="income"   # income / balance / cash_flow
)

# Margin data (融资融券); data_type: margin_detail / margin / short_margin
margin = agent.get_margin_data(data_type="margin_detail")

# Stock list (获取所有股票基本信息)
stocks = agent.get_stock_basic()

# Trading calendar
calendar = agent.get_trade_calendar(start_date="20240101", end_date="20241231")

# Concept stocks (concept board)
concept = agent.get_concept_stocks(board_name="AI语料")
```

**All methods require `TUSHARE_TOKEN` to be set.** When the token is not
available, MCP calls gracefully return mock data (marked with `_mock=True`).

---

## Running the Demo

### Basic Demo

```bash
python scripts/demo_research_report.py --stock 000001.SZ
```

### With Custom Output Directory

```bash
python scripts/demo_research_report.py \
    --stock 000001.SZ \
    --output papers
```

> `--output` is a directory, not a file. A TeX file will be created at
> `papers/demo_000001_SZ.tex`. There is no `--format` flag — PDF
> compilation is attempted automatically (requires TeX Live installed).

### Command-line Help

```bash
python scripts/demo_research_report.py --help
```

---

## Report Structure

### 1. Executive Summary

One-page overview with:
- Investment thesis (一句话结论)
- Key financial highlights
- Valuation and recommendation

### 2. Financial Analysis

| Metric | Formula | Value |
|--------|---------|-------|
| ROE | Net Income / Equity | 12.5% |
| Net Profit Margin | Net Income / Revenue | 35.2% |
| Asset Turnover | Revenue / Assets | 0.45x |
| Financial Leverage | Assets / Equity | 2.8x |

### 3. Valuation

Three methods integrated:
- **DCF**: Discounted cash flow with scenario analysis
- **Comparables**: P/E, P/B, EV/EBITDA multiples
- **Dividend Discount Model**: For dividend-paying stocks

### 4. Risk Factors

- Industry-specific risks
- Macroeconomic sensitivity
- Policy risks
- Operational risks

### 5. Recommendation

| Rating | Criteria |
|--------|----------|
| Buy | Upside > 20% |
| Hold | -10% < Upside < 20% |
| Sell | Upside < -10% |

---

## Customizing Templates

### Using Chinese Journal Templates

```python
from scripts.journal_template import JournalTemplate, get_template

# 经济研究
template = get_template("经济研究")

# 金融研究
template = get_template("金融研究")

# 管理世界
template = get_template("管理世界")
```

### List Available Templates

```bash
python scripts/journal_template.py --list
```

### Generate Template File

```bash
python scripts/journal_template.py --generate JFE output/paper.tex
```

---

## Programmatic Usage

```python
import asyncio
from scripts.core.analyst_agents import ParallelAnalystOrchestrator
from scripts.core.llm_gateway import LLMGateway

async def analyze_stock(ticker: str):
    gateway = LLMGateway()
    orchestrator = ParallelAnalystOrchestrator(gateway=gateway)

    # Run parallel analysis (6 analysts concurrently)
    context = {
        "financial_data": {...},   # pre-fetched financial data
        "market_data": {...},      # pre-fetched market data
    }
    result = await orchestrator.run_parallel_analysis(
        ticker=ticker,
        context=context,
        analyst_types=["fundamental_financial", "valuation", "risk"],
    )

    print(f"Consensus: {result.consensus_view}")
    print(f"Confidence: {result.confidence:.2f}")
    return result

# Execute
result = asyncio.run(analyze_stock("000001.SZ"))
```

> The `run_parallel_analysis()` method is `async`. Use `asyncio.run()` or
> `await` in an async context. Do **not** use `orchestrator.analyze()`
> or `orchestrator.generate_report()` — these methods do not exist.

---

## Data Sources

| Source | Data Type | API Key Required |
|--------|-----------|------------------|
| **Tushare** | A-share quotes, financials, margin | Yes (`TUSHARE_TOKEN`) |
| **akshare** | A-share free data | No |
| **yfinance** | US stocks | No |
| **EODHD** | Macro indicators | Yes (`EODHD_API_KEY`) |

---

## Next Steps

- [Tutorial 4: MCP Tool Marketplace](04-mcp-marketplace.md)
- [Tutorial 5: Event-Driven Research](05-event-driven-research.md)
- [API Reference: AgentOrchestrator](../api_reference.md#agentorchestrator)
