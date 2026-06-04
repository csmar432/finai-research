# Tutorial 4: MCP Tool Marketplace

> Discover, search, and add new MCP tools for your research workflow.

---

## What is the MCP Tool Marketplace?

The MCP Tool Marketplace is a registry that indexes all MCP servers in `mcp_servers/`. Each server provides specialized tools for:

- Financial data (stocks, fundamentals, derivatives)
- Macroeconomic indicators (GDP, CPI, interest rates)
- Academic research (arXiv, NBER working papers)
- News and market sentiment

---

## Using MCPToolRegistry

### Python API

```python
from scripts.core.mcp_tool_market import MCPToolRegistry

# Build registry from mcp_servers/ directory
registry = MCPToolRegistry.from_directory("mcp_servers")

# Search for tools
results = registry.search("gdp", category="macro_data")
for tool in results:
    print(f"{tool.mcp_server}::{tool.name}")
    print(f"  Score: {tool.quality_score}")
    print(f"  Description: {tool.description[:80]}...")

# Get tools by category
macro_tools = registry.get_by_category("macro_data")

# Get tools by server
tushare_tools = registry.get_by_server("user-tushare")

# Generate marketplace report
report = registry.get_marketplace_report()
print(f"Total tools: {report['total_tools']}")
print(f"Top 5: {report['top_5_by_quality']}")
```

### CLI Interface

```bash
# Show all tools
python scripts/core/mcp_tool_market.py --dir mcp_servers

# Search for specific tools
python scripts/core/mcp_tool_market.py --search "gdp" --report

# Filter by category
python scripts/core/mcp_tool_market.py --category financial

# Show tools from a specific server
python scripts/core/mcp_tool_market.py --server user-tushare

# Export as JSON
python scripts/core/mcp_tool_market.py --json > registry.json
```

---

## Quality Scoring

Tools are scored 0.0–1.0 based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Description | 0.2 | Rich, non-empty description (>10 chars) |
| Schema | 0.2 | Has input schema with properties |
| Real API | 0.3 | No mock/demo signals |
| Examples | 0.1 | Has usage examples in description |
| **Total** | **1.0** | |

### Score Interpretation

| Score Range | Quality Level |
|-------------|---------------|
| 0.8–1.0 | High quality: real API, complete schema, examples |
| 0.5–0.8 | Medium quality: some documentation, may be partial |
| 0.0–0.5 | Low quality: mock, incomplete, or minimal |

---

## Tool Categories

| Category | Description | Example Servers |
|----------|-------------|-----------------|
| `financial` | A-share data, financial statements | `user-tushare`, `user-eastmoney` |
| `macro_data` | GDP, CPI, M2, interest rates | `user-financial`, `user-wb-data` |
| `market_data` | Quotes, yields, derivatives | `user-eodhd`, `user-enhanced-finance` |
| `academic` | Working papers, literature | `user-arxiv`, `user-nber-wp` |
| `utility` | File operations, LaTeX, code execution | `user-filesystem-mcp`, `user-latex-mcp` |

---

## Adding New MCP Tools

### Step 1: Create Server Directory

```
mcp_servers/
└── user_your_server/
    ├── SERVER_METADATA.json
    └── tools/
        ├── your_tool_1.json
        └── your_tool_2.json
```

### Step 2: Create SERVER_METADATA.json

```json
{
  "name": "user_your_server",
  "description": "Your custom data source for research",
  "version": "1.0.0",
  "author": "Your Name",
  "capabilities": ["stock_data", "financial_statements"],
  "requires_api_key": false
}
```

### Step 3: Create Tool Definitions

```json
// tools/get_stock_quote.json
{
  "name": "get_stock_quote",
  "description": "Get real-time stock quote for a given ticker. For example, params: {ticker: '000001.SZ'} returns current price, volume, and bid/ask spread.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "ticker": {
        "type": "string",
        "description": "Stock ticker code, e.g. '000001.SZ'"
      },
      "market": {
        "type": "string",
        "description": "Market: 'CN' for China, 'US' for US"
      }
    },
    "required": ["ticker"]
  }
}
```

### Step 4: Register Server in Cursor

Add to `.cursor/settings.json` or Cursor MCP settings:

```json
{
  "mcpServers": {
    "user_your_server": {
      "command": "python",
      "args": ["mcp_servers/user_your_server/server.py"]
    }
  }
}
```

### Step 5: Rebuild Registry

```bash
python scripts/core/mcp_tool_market.py --dir mcp_servers --search "your_tool"
```

---

## MCP Tool Usage Examples

### Getting Macro Data

```python
# Use via MCP
server: user-financial
tool: get_macro_china
params: { "indicator": "gdp" }

# Or via Python
from scripts.research_framework.data_fetcher import DataFetcher

fetcher = DataFetcher()
gdp_data = fetcher.get_macro_data("china_gdp")
```

### Getting Stock Data

```python
# A-share via Tushare (requires API key)
server: user-tushare
tool: get_daily_quote
params: { "ts_code": "000001.SZ", "start_date": "20240101" }

# US stocks via yfinance
server: user-yfinance
tool: get_financials
params: { "symbol": "AAPL" }
```

### Getting Research Reports

```python
server: user-eastmoney-reports
tool: get_research_report
params: { "ts_code": "000001.SZ", "max_results": 20 }
```

---

## Marketplace Report Example

```json
{
  "total_tools": 142,
  "total_servers": 25,
  "by_category": {
    "financial": 38,
    "macro_data": 45,
    "market_data": 28,
    "academic": 12,
    "utility": 19
  },
  "category_avg_quality": {
    "market_data": 0.72,
    "macro_data": 0.68,
    "financial": 0.65,
    "academic": 0.55,
    "utility": 0.45
  },
  "requires_api_key": 8,
  "mock_tools": 15,
  "top_5_by_quality": [
    {"server": "user-wb-data", "name": "get_wb_indicator", "score": 0.95},
    {"server": "user-eodhd", "name": "get_ust_yield_rates", "score": 0.92},
    ...
  ]
}
```

---

## Next Steps

- [Tutorial 5: Event-Driven Research](05-event-driven-research.md)
- [API Reference: MCPToolRegistry](../api_reference.md#mcptoolregistry)
- [Setup Guide: MCP Server Configuration](../SETUP_GUIDE.md)
