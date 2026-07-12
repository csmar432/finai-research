# 论文-研报工作流 · 配置指南

> 完整的开发环境配置和数据获取设置指南。

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [API Key Configuration](#2-api-key-configuration)
3. [MCP Server Setup](#3-mcp-server-setup)
4. [Optional: Ollama Local Model](#4-optional-ollama-local-model)
5. [Testing Your Setup](#5-testing-your-setup)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Environment Setup

### System Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ (3.12 recommended) | Required |
| pip | Latest | Comes with Python |
| Git | Any recent version | For version control |

### Setup with conda

```bash
# Create conda environment
conda create -n finai python=3.12
conda activate finai

# Install the package and all common optional integrations
# extras includes Tushare, akshare, yfinance, MCP, dashboards, and document processing.
pip install -e ".[extras]"           # 推荐方式（支持 entry points）
# 或仅安装依赖：
pip install -e ".[extras]" --no-deps 2>&1 || pip install -e ".[extras]"
```

### Setup with venv

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
# .venv\Scripts\activate

# Install the package and all common optional integrations
pip install -e ".[extras]"
```

### Verify Installation

```bash
python --version  # Should show Python 3.11+
pip list | head -20  # Check installed packages
```

---

## 2. API Key Configuration

All API keys are stored in the `.env` file in the project root. **Never commit this file.**

### Creating the .env File

### Configuration File

```bash
# Copy the example file → 创建 .env.local（不被 git 跟踪）
cp .env.example .env.local

# Edit with your actual keys
nano .env.local  # or any text editor
```

> **优先级说明**：`.env.local` 优先级高于 `.env`，系统自动加载。`.env` 可被 git 跟踪，`.env.local` 不会被跟踪。

### 首次运行配置向导（推荐）

```bash
# 交互式引导 — 根据研究方向推荐配置项
python scripts/setup_wizard.py --guided

# 查看当前配置状态
python scripts/setup_wizard.py --status
```

配置向导会自动：
1. 检测当前 `.env` / `.env.local` 中的已配置项
2. 询问你的研究方向（A 股 / 宏观 / 实证论文 / 量化 / 研报）
3. 推荐需要配置的 API Key 和 MCP 服务器
4. 允许选择性配置（必需 / 推荐 / 可选）
5. 保存到 `.env.local`



### Required Keys

| Key | Required | Service | Get Key From |
|-----|----------|---------|--------------|
| `DEEPSEEK_API_KEY` | **Recommended** | DeepSeek LLM (Chinese tasks) | [console.deepseek.com](https://console.deepseek.com) |
| `RELAY_API_KEY` | Optional | GPT/Claude via relay | B.AI, OpenRouter, etc. |

### Optional Keys (for Data)

| Key | Required | Service | Get Key From |
|-----|----------|---------|--------------|
| `TUSHARE_TOKEN` | Optional | A-share data (full access) | [tushare.pro](https://tushare.pro/register) |
| `EODHD_API_KEY` | Optional | Macro data (yield curve, calendar) | [eodhd.com](https://eodhd.com) |
| `FRED_API_KEY` | Optional | US macro (GDP, CPI) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `BRAVE_SEARCH_API_KEY` | Optional | Web search | [brave.com/search/api](https://brave.com/search/api/) |

### Example .env File

```bash
# AI Models (required for LLM features)
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
RELAY_API_KEY=your-relay-key-here

# Data Sources (optional)
TUSHARE_TOKEN=your-tushare-token
EODHD_API_KEY=your-eodhd-key
FRED_API_KEY=your-fred-key

# Other Services
BRAVE_SEARCH_API_KEY=your-brave-key
```

### Key Priority

You only need **one** AI key to start:
- `DEEPSEEK_API_KEY` — Recommended for Chinese research
- `RELAY_API_KEY` — For English writing (GPT/Claude)

The system will automatically route tasks to the appropriate model.

---

## 3. MCP Server Setup

### Overview

The system includes 43 MCP servers providing financial data:

| Category | Servers |
|----------|---------|
| **A-shares** | `user-tushare`, `user-csmar`, `user-wind`, `user-eastmoney-reports`, `user-eastmoney-fund`, `user-eastmoney-bond`, `user-eastmoney-option` |
| **Macro** | `user-financial`, `user-wb-data`, `user-imf-data`, `user-oecd-data`, `user-bea-data`, `user-fed-data`, `user-macro-ceic`, `user-macro-datas`, `user-macro-stats` |
| **US Stocks** | `user-yfinance`, `user-eodhd`, `user-sec-edgar` |
| **Academic** | `user-arxiv`, `user-nber-wp`, `user-openalex`, `user-context7`, `user-semantic-scholar`, `user-chinese-literature` |
| **Provincial Stats** | `user-province-stats`, `user-hubei-stats`, `user-wuhan-stats` |
| **Utilities** | `user-filesystem-mcp`, `user-latex-mcp`, `user-e2b-mcp`, `user-pandas-mcp`, `user-playwright-mcp` |

Most servers require no API key. See [docs/tutorials/04-mcp-marketplace.md](docs/tutorials/04-mcp-marketplace.md) for the complete catalog.

### Cursor MCP Integration

1. Open Cursor Settings → MCP
2. Add new MCP server for each you want to use
3. Or use the auto-registration script:

```bash
python scripts/register_mcp_servers.py --all
```

### Manual Server Registration

Add to Cursor MCP settings:

```json
{
  "mcpServers": {
    "user-tushare": {
      "command": "python",
      "args": ["mcp_servers/user_tushare/server.py"]
    },
    "user-financial": {
      "command": "python",
      "args": ["mcp_servers/user_financial/server.py"]
    }
  }
}
```

### Server-Specific Setup

#### user-tushare (A股数据)

```bash
# Tushare is included in the extras dependency group
pip install -e ".[extras]"
# To install only the client instead: pip install "tushare>=1.4.0,<2.0"

# Configure token
echo "TUSHARE_TOKEN=your-tushare-token" >> .env
```

#### user-financial (全球宏观)

```bash
# No additional setup needed
# Uses World Bank API (free) + akshare (free)
```

#### user-eodhd (EOD Historical Data)

```bash
# Install
pip install eodhd

# Configure key
echo "EODHD_API_KEY=your-eodhd-api-key" >> .env
```

---

## 4. Optional: Ollama Local Model

For offline usage or cost savings, set up Ollama with local models.

### Installation

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or via Homebrew (macOS)
brew install ollama
```

### Start Ollama

```bash
ollama serve
```

### Pull Models

```bash
# Chinese-optimized model
ollama pull qwen2.5:7b

# English model
ollama pull llama3.2:3b
```

### Configure in .env

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b
```

### Update ai_router.py

Add Ollama to the model pool in `scripts/ai_router.py`:

```python
OLLAMA_CONFIG = {
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
}
```

---

## 5. Testing Your Setup

### Run All Tests

```bash
cd /path/to/论文-研报工作流
python -m pytest tests/ -v --tb=short
```

### Test Individual Components

```bash
# Test LLM connectivity
python scripts/agent.py --test

# Test MCP registry
python scripts/core/mcp_tool_market.py --report

# Test data fetching
# 测试数据获取（通过 Python API）
from scripts.research_framework.data_fetcher import DataFetcher
fetcher = DataFetcher()

# Test literature search (use AI Agent or research_framework pipeline)
python scripts/research_framework/pipeline.py --topic "carbon trading innovation"
```

### Test Paper Pipeline

```bash
# Generate a test paper
python scripts/agent.py --goal "测试：AI在金融领域的应用"
```

### Verify Dashboard

```bash
streamlit run scripts/dashboard.py --server.port 8050
# Open http://localhost:8050 in browser
```

---

## 6. Troubleshooting

### Common Issues

#### 1. Module Not Found

```
ModuleNotFoundError: No module named 'xxx'
```

**Solution**: Install missing package

```bash
pip install xxx
```

#### 2. API Key Not Found

```
KeyError: 'DEEPSEEK_API_KEY'
```

**Solution**: Ensure `.env` file exists and contains the key

```bash
cat .env | grep DEEPSEEK_API_KEY
```

#### 3. MCP Tool Unavailable

```
MCP tool unavailable
```

**Solution**: 
1. Check Cursor MCP settings
2. Restart Cursor
3. Or use script fallback:

```python
from scripts.research_framework.data_fetcher import DataFetcher
fetcher = DataFetcher()
data = fetcher.get_stock_data("000001.SZ")
```

#### 4. LaTeX Compilation Failed

```
! LaTeX Error: File 'xxx.sty' not found.
```

**Solution**: Install missing LaTeX packages

```bash
# macOS
brew install --cask mactex

# Ubuntu/Debian
sudo apt install texlive-latex-extra
```

#### 5. Data Fetch Failed

```
ConnectionError: Failed to fetch data
```

**Solutions**:
- Check internet connection
- Verify API key is valid
- Try alternative data source
- Use cached/fallback data

#### 6. Virtual Environment Issues

```
pip install fails with permission error
```

**Solution**: Use virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[extras]"
```

### Getting Help

1. Check existing issues: [GitHub Issues](https://github.com/csmar432/finai-research/issues)
2. Run with verbose logging:

```bash
python scripts/agent.py --goal "xxx" --verbose
```

3. Check logs in `logs/` directory

---

## Quick Reference

### Essential Commands

```bash
# Full dev setup
pip install -e ".[dev]"
# Run tests
make test
# Lint code
make lint
# Health check
make health
```

### File Locations

| File | Purpose |
|------|---------|
| `.env` | API keys (not committed) |
| `.env.example` | Template for .env |
| `config/llm_config.json` | Model configuration |
| `config/project_config.json` | Project settings |
| `output/` | Output directory |
| `data/` | Input data directory |
| `logs/` | Log files |

---

## Next Steps

- [Quick Start Tutorial](docs/tutorials/01-quickstart.md)
- [API Reference](docs/api_reference.md)
- [MCP Marketplace Tutorial](docs/tutorials/04-mcp-marketplace.md)
