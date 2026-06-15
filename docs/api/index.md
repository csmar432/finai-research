# API Reference · Sphinx 自动生成的 API 文档

> Sphinx 配置见 [`conf.py`](conf.py)
> 构建: `cd docs && sphinx-build -b html api/ api/_build/html`

## 文档范围

| 模块 | 路径 | 描述 |
|------|------|------|
| Agent Orchestrator | `scripts/core/orchestrator.py` | 主智能体编排器 |
| LLM Gateway | `scripts/core/llm_gateway.py` | LLM 调用抽象层 |
| Provenance Tracker | `scripts/core/provenance.py` | 数据溯源追踪 |
| MCP Tool Registry | `scripts/core/mcp_tool_market.py` | MCP 工具市场 |
| Reviewer | `scripts/core/llm_reviewer.py` | 对抗性评审 |
| Econometrics Rule Engine | `scripts/research_framework/econometrics_extended.py` | 计量方法规则引擎 |
| Modern DID | `scripts/research_framework/modern_did.py` | 现代 DID 集合 |
| Synthetic Control | `scripts/research_framework/synthetic_control.py` | 合成控制 |
| Event Monitor | `scripts/event_monitor.py` | 事件监控 |

## 自动生成

Sphinx 在每次 push 时自动生成（通过 `.github/workflows/docs.yml`）。

## 本地构建

```bash
# 安装 sphinx
pip install sphinx sphinx-rtd-theme myst-parser

# 构建 HTML
cd docs
sphinx-build -b html api/ api/_build/html

# 浏览器打开
open api/_build/html/index.html
```
