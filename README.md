# 论文-研报工作流 · FinResearch Agent

> 经济金融领域 AI 学术研究工作流 — 从研究想法到可投稿论文。集成 MCP 数据获取、因果推断（DID/IV/PSM/GMM）、LaTeX 排版和对抗性 review 循环。

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://pypi.org/project/finai-research-workflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/finai-research-workflow?color=blue)](https://pypi.org/project/finai-research-workflow/)
[![PyPI downloads](https://img.shields.io/pypi/dm/finai-research-workflow?color=blue)](https://pypi.org/project/finai-research-workflow/)
[![arXiv](https://img.shields.io/badge/arXiv-cs.AI-b31b1b.svg)](https://arxiv.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/YOUR_USERNAME/finai-research-workflow/ci.yml?branch=main&label=CI)](https://github.com/YOUR_USERNAME/finai-research-workflow/actions)
[![docs](https://img.shields.io/github/actions/workflow/status/YOUR_USERNAME/finai-research-workflow/docs.yml?branch=main&label=docs)](https://github.com/YOUR_USERNAME/finai-research-workflow/actions)
[![GitHub stars](https://img.shields.io/github/stars/YOUR_USERNAME/finai-research-workflow?style=social)](https://github.com/YOUR_USERNAME/finai-research-workflow/stargazers)

---

## Who Is This For?

| Audience | Use Case |
|----------|----------|
| **PhD students / researchers** | Design empirical studies, run econometric analysis, generate LaTeX manuscripts for JF/JFE/RFS/经济研究/金融研究 |
| **Finance professors** | Automate literature reviews, track policy experiments, benchmark against published papers |
| **Graduate students** | Learn econometric methods (DID/IV/RDD) with automated validation and robustness checks |
| **Quantitative analysts** | Access A-share data, run factor analysis, generate institutional-grade research reports |
| **AI/ML researchers** | Explore LLM applications in financial research automation, provenance tracking, HITL design |

> **Not sure?** If you've ever spent days downloading data, running regressions, formatting LaTeX tables, or searching for related work — this tool is for you.

---

## Show Me What It Does

Describe your research in plain Chinese — the agent handles the rest:

```
帮我研究关税政策对A股出口型企业创新的影响，设计一篇发表在经济研究的实证论文
```

**What the agent produces automatically:**

| Stage | Output |
|-------|--------|
| Literature Review | Citation graph + gap analysis (arXiv / NBER / OpenAlex / JF / JFE / RFS) |
| Research Design | DID/IV/RDD identification strategy + data sourcing plan |
| Empirical Analysis | 33 econometric methods, automated robustness tests (18 types) |
| Paper Draft | LaTeX manuscript in journal format (JF/JFE/RFS/经济研究/金融研究/管理世界) |
| Review Loop | Adversarial review until submission-ready |

**Architecture overview:**

![Architecture Diagram](.github/demo/architecture-diagram.svg)
*Multi-agent pipeline: User Input → Cursor Agent → 5-Stage Research Pipeline → 34 MCP Servers → 33 Econometric Methods → LaTeX Paper*

> **Note:** Screenshots and demo videos coming soon. The project is actively maintained.

---

## What is This?

**论文-研报工作流** is a local AI-powered research workflow that helps you:

- **Write academic papers** — From literature review to LaTeX submission (JF/JFE/RFS/经济研究/金融研究/管理世界)
- **Generate research reports** — Institutional-grade financial analysis for A-shares and global markets
- **Run empirical analysis** — DID, IV, PSM, Panel GMM with automated validation
- **Access financial data** — A-shares, US stocks, macro indicators via 34 MCP data servers (most require no API key)

> Architecture principle: **Cursor Claude (local) as the core, external AI as supplement.**

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Agent Pipeline** | Orchestrates 5-paper agents (outline → literature → plotting → writing → refinement) |
| **34 MCP Data Servers** | A-share (Tushare), macro (World Bank, IMF, OECD), US stocks (yfinance), academic (arXiv, NBER, OpenAlex) — most require no API key |
| **33 Econometric Methods** | DID (5 variants), RDD, synthetic control, panel GMM, spatial regression, IV/2SLS — JF/JFE/RFS standard |
| **Provenance Tracking** | Full data lineage from raw API to final chart/table |
| **HITL Gates** | Human-in-the-loop approval at critical pipeline stages |
| **6 Financial Analysts** | Parallel analysis: fundamental, valuation, risk, earnings, competitive, macro |
| **Self-Evolution** | Continuous improvement based on task outcomes |
| **34 Journal Templates** | JFE/JF/RFS + 28 Chinese journals (经济研究/金融研究/管理世界/会计研究 etc.) |

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Clone the repository
git clone https://github.com/finai-research/finai-research-workflow.git
cd finai-research-workflow

# 2. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Configure API key (at least one required)
cp .env.example .env
# Edit .env and add: DEEPSEEK_API_KEY=sk-your-key
# Other supported: ANTHROPIC_API_KEY, OPENAI_API_KEY

# 4. Run your first research pipeline
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"

# Or use Cursor Agent (recommended) for the full interactive workflow
```

### Via Cursor (Recommended)

Simply describe your research goal in natural language:

```
帮我分析碳排放权交易对企业绿色创新的影响，设计一篇实证论文，发表在经济研究
```

Cursor Agent will automatically call all necessary modules.

---

## Architecture

The system uses a **layered agent architecture** with Cursor Agent as the orchestrator:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Cursor Agent (Local Claude)                            │
│                                                                          │
│   Natural Language → Multi-Agent Pipeline → LaTeX Paper + PDF             │
│   "帮我研究关税政策对创新的影响，发表在经济研究"                            │
└──────────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐
│   scripts/core/  │  │   34 MCP Servers │  │  research_framework/      │
│                 │  │                  │  │                          │
│  Memory         │  │  A-shares        │  │  modern_did.py            │
│  Planner        │  │  US Stocks       │  │  synthetic_control.py     │
│  ToolSelector   │  │  Global Macro    │  │  rdd.py                   │
│  Reflector      │  │  Academic Papers │  │  regression_engine.py     │
│  Orchestrator   │  │  News/Reports    │  │  fin_charts.py            │
│  HITL Gates     │  │  Forex/Commodity │  │  a_share_variables.py     │
│  Self-Evolution │  │  ...             │  │  policy_database.py       │
└─────────────────┘  └─────────────────┘  └──────────────────────────┘
```

**Key numbers:** 34 MCP servers · 33 econometric methods · 16 Skills · 38 test files · >200 test cases

---

## MCP Tools Overview

| MCP Server | Function | API Key Required |
|------------|----------|-----------------|
| **user-tushare** | A-share data (quotes, financials, margin) | Yes |
| **user-financial** | Global macro (GDP/CPI/M2 via World Bank + akshare) | No |
| **user-eodhd** | US macro (yield curve, economic calendar) | Yes |
| **user-eastmoney-reports** | Research reports, news, analyst rankings | No |
| **user-yfinance** | US stock financials, ESG data | No |
| **user-finviz-sec** | Stock screening, SEC filings | No |
| **user-enhanced-finance** | Forex, shipping indices, commodities | No |
| **user-arxiv** | Academic paper search and download | No |
| **user-brave-search** | Web search for news and research | Yes |
| **user-wb-data** | World Bank Data API | No |
| **user-imf-data** | IMF Data API | No |
| **user-nber-wp** | NBER Working Papers | No |
| **user-fed-data** | Federal Reserve Data (FOMC, Beige Book) | No |
| **user-bea-data** | Bureau of Economic Analysis | No |
| **user-oecd-data** | OECD Data API | No |

See [MCP Tool Marketplace Tutorial](docs/tutorials/04-mcp-marketplace.md) for details.

---

## Tutorials

| Tutorial | Description | Time |
|----------|-------------|------|
| [01 - Quick Start](docs/tutorials/01-quickstart.md) | Setup and run your first pipeline | 5 min |
| [02 - Financial Reports](docs/tutorials/02-financial-report.md) | Generate institutional research reports | 10 min |
| [03 - Research Directions](docs/tutorials/03-research-directions.md) | Design empirical studies with DID/RDD/IV | 15 min |
| [04 - MCP Marketplace](docs/tutorials/04-mcp-marketplace.md) | Discover and add MCP tools | 15 min |
| [05 - Event-Driven Research](docs/tutorials/05-event-driven-research.md) | Automate research via event monitoring | 20 min |

---

## Documentation

| Document | Description |
|----------|-------------|
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | Environment setup, API keys, Docker |
| [USAGE_GUIDE.md](USAGE_GUIDE.md) | Complete usage guide (Chinese) |
| [QUICKSTART.md](QUICKSTART.md) | 5-minute quick start |
| [CLAUDE.md](CLAUDE.md) | Agent configuration and capabilities |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [docs/tutorials/](docs/tutorials/) | Step-by-step tutorials |
| [docs/api_reference.md](docs/api_reference.md) | API documentation |

---

## Common Commands

```bash
# Paper pipeline
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"

# Financial report
python scripts/demo_research_report.py --stock 000001.SZ

# MCP tool marketplace
python scripts/core/mcp_tool_market.py --search "gdp" --report

# Event monitor
python scripts/event_monitor.py --interval 300 --test

# Literature review
python scripts/literature_manager.py --search "carbon trading innovation"

# Journal template
python scripts/journal_template.py --list
python scripts/journal_template.py --generate JFE output/paper.tex

# Dashboard
streamlit run scripts/dashboard.py --server.port 8050
```

---

## Data Coverage

| Market | Source | Data Types |
|--------|--------|------------|
| **A-shares** | akshare (free) / Tushare Pro | Daily quotes, financials, margin, north flow |
| **US Stocks** | yfinance + Finviz (free) | Quotes, financials, ESG, options, SEC filings |
| **Macro (Global)** | World Bank + IMF + OECD (free) | GDP, CPI, population, trade, debt |
| **Macro (China)** | akshare + NBS (free) | CPI, PPI, PMI, M2, FDI, retail sales |
| **Macro (US)** | FRED + BEA + Fed (free) | NIPA, FOMC, Beige Book, yield curve |
| **Fixed Income** | EODHD (key) / akshare (free) | Treasury yields, bond prices, credit spreads |
| **Forex & Commodities** | akshare + Enhanced Finance (free) | FX rates, shipping indices, precious metals |
| **Research Reports** | 东方财富 (free) | Analyst reports, news, sector analysis |
| **Academic** | arXiv + NBER (free) | Working papers, citations |

---

## Extending the System

### Adding a New MCP Server

1. Create directory: `mcp_servers/user_your_server/`
2. Add `SERVER_METADATA.json`
3. Add tool definitions in `tools/*.json`
4. Register in Cursor MCP settings
5. Rebuild registry: `python scripts/core/mcp_tool_market.py --dir mcp_servers`

See [MCP Marketplace Tutorial](docs/tutorials/04-mcp-marketplace.md) for full guide.

### Adding a New Research Direction

1. Create file: `scripts/research_directions/your_topic.py`
2. Define `ResearchDirection` class with:
   - Research questions
   - Data requirements
   - Hypothesis derivation
   - Empirical strategy
3. Add to `scripts/research_directions/__init__.py`

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Built on [Night Owl Research Agent (NORA)](https://github.com/GRIND-Lab-Core/night_owl_research_agent) design patterns
- Inspired by [PaperOrchestra](https://github.com/google-research/paper-orchestra) multi-agent architecture
- Data powered by akshare, yfinance, World Bank API, and Tushare Pro

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=YOUR_USERNAME/finai-research-workflow&type=Timeline)](https://star-history.com/#YOUR_USERNAME/finai-research-workflow&Timeline)

---

## Built With

| Layer | Technology |
|-------|------------|
| **AI Orchestration** | Cursor Agent, Claude API, OpenAI API, Anthropic API |
| **Data (34 servers)** | akshare, yfinance, World Bank API, IMF API, Tushare Pro |
| **Econometrics** | statsmodels, linearmodels, scipy |
| **Visualization** | matplotlib, seaborn, plotly |
| **Pipeline** | Python 3.10+, DuckDB, FastAPI, Streamlit |
| **Testing** | pytest, ruff |
| **Documentation** | MkDocs Material |
| **Containerization** | Docker, Docker Compose |
