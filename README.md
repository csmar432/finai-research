# 金融AI研究工作流

一个极简、高效的本地工作流，服务于金融AI学术研究和研报生成。

## 架构原则

**以 Cursor 本地 Claude 为核心，外部 AI 仅作补充。**

```
Cursor Agent（本地 Claude）
  └── 直接对话、代码、分析、写作 — 无需任何配置
  └── 若需脚本批处理 → scripts/ai_router.py → B.AI / DeepSeek
```

---

## 3分钟上手

### 1. 配置 API Key（仅脚本批处理需要）

Keys 放在项目根目录 `.env.local`（已在 .gitignore，不会提交）：

```bash
# .env.local（勿提交）
B_AI_API_KEY=sk-xxx        # B.AI 中转（需 VPN）：gpt-5.5 / claude-4.6 / gemini-3.1-pro
DEEPSEEK_API_KEY=sk-xxx    # DeepSeek 直连（无需 VPN）：deepseek-chat / deepseek-reasoner
FRED_API_KEY=xxx           # FRED 宏观数据（免费）：https://fred.stlouisfed.org
```

### 2. 安装依赖

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 直接在 Cursor 里说话

直接在 Cursor 对话框中用自然语言调用所有功能，Cursor Claude 本地处理。

---

## 可用工具速查

| 你说什么 | AI 自动完成 |
|---|---|
| "帮我检索XX领域文献，做综述" | arXiv 检索→下载→解析→生成综述 |
| "设计一篇深度学习量化交易论文大纲" | 研究问题+创新点+章节概要 |
| "写一篇完整论文" | 端到端生成全文 |
| "分析苹果公司财务数据" | MCP 获取数据→研报生成 |
| "获取茅台近一年日线数据" | akshare A股数据 + 特征工程 |
| "批量情感分析这100条新闻" | LLMProcessor 脚本批处理（外部AI） |

---

## AI 角色定位

| 调用方式 | AI 模型 | 用途 |
|---|---|---|
| **Cursor 直接对话** | Claude（本地，无消耗） | 所有日常任务（默认） |
| **脚本批处理** | B.AI gpt-5.5（需VPN） | 批量情感/摘要/代码 |
| **脚本批处理** | DeepSeek（直连，无需VPN） | 中文写作/简单问答 |

## Agent 使用（命令行）

```bash
# 分析苹果公司财务数据
python scripts/agent.py --goal "分析苹果公司2024年财务数据并生成研报"

# 检索文献并做综述
python scripts/agent.py --goal "检索深度学习量化交易方向的最新文献，做综述"

# 继续上次会话（追问）
python scripts/agent.py --resume

# 查看所有会话状态
python scripts/agent.py --list

# 查看会话状态
python scripts/agent.py --status

# 运行核心模块测试
python scripts/agent.py --test
```

程序化调用：

```python
from scripts.core.session import ResearchSession, SessionConfig

session = ResearchSession(SessionConfig(
    session_id="茅台财务分析",
    user_goal="分析茅台2024年财务数据并生成研报",
    workspace_root=".",
    verbose=True,
))
result = session.run("分析茅台2024年财务数据")
print(result["summary"])
```

---

## 目录结构

```
工作流搭建/
├── config/
│   ├── llm_config.json     ← LLM API Key 配置模板（实际 Key 在 .env.local）
│   ├── ai_router.json      ← AI 路由映射
│   └── project_config.json  ← 项目元配置
├── scripts/
│   ├── core/                   ← ★ 核心智能体模块（四模块）
│   │   ├── memory.py          ← 三层记忆（Context/短期/长期SQLite）
│   │   ├── planner.py         ← 任务分解+拓扑排序+4级回退
│   │   ├── tool_selector.py   ← 工具注册表+自主路由（13个工具）
│   │   ├── reflector.py       ← 四维评估+反馈循环
│   │   └── session.py         ← 会话管理（串联四模块）
│   ├── agent.py              ← 统一 CLI 入口（推荐使用）
│   ├── ai_router.py          ← 外部 AI 路由（B.AI/DeepSeek，作为补充）
│   ├── data_pipeline.py       ← A股/美股数据+特征工程
│   ├── literature_search.py   ← 文献检索→综述生成
│   ├── literature_manager.py  ← 文献库管理
│   ├── paper_reader.py       ← 论文下载→AI分析→问答
│   ├── paper_write.py        ← 论文全流程（大纲→章节→全文整合）
│   ├── paper_submit.py       ← 润色→查重→LaTeX检查→投稿信
│   ├── paper_visualizer.py   ← 图表生成
│   ├── paper_tools.py        ← 论文工具集
│   ├── report_generator.py   ← 研报生成
│   ├── econometrics.py        ← OLS/DID回归+稳健性检验
│   ├── model_train.py        ← 模型训练框架
│   └── generate_empirical_tables.py ← 实证表格生成
├── prompts/                ← 提示词模板（15个）
│   ├── 01_研究员角色.md    ← 学术研究员
│   ├── 02_分析师角色.md    ← 金融分析师
│   ├── 03_论文写手角色.md  ← 论文写作助手
│   └── 04-15_*.md         ← 各章节写作提示词
├── knowledge/              ← 知识库
│   ├── papers/            ← 文献索引
│   ├── papers_fulltext/   ← 论文原文
│   ├── reviews/           ← 文献综述
│   ├── outlines/          ← 论文大纲
│   ├── chapters/          ← 章节草稿
│   └── output/            ← 润色后论文
├── templates/              ← 模板
│   └── research_report.md ← 研报模板（国泰君安/中金格式）
├── mcp_servers/
│   ├── financial-mcp-server/  ← 金融数据 MCP（yfinance/FRED/CoinGecko/SEC）
│   └── finviz-sec-mcp/        ← Finviz+SEC MCP（美股筛选/板块分析）
├── .cursor/rules/         ← Cursor 调度规则
├── requirements.txt       ← Python 依赖
├── QUICKSTART.md         ← 快速开始
└── README.md             ← 本文件
```

---

## 核心脚本速查

### 论文写作（一个脚本搞定）

```bash
# 完整流程：选题→大纲→7章节→全文整合
python scripts/paper_write.py --topic "深度学习 量化交易" --venue "NeurIPS" --save

# 仅生成大纲
python scripts/paper_write.py --step outline --topic "大模型 金融文档" --save

# 仅生成引言+相关工作
python scripts/paper_write.py --step intro --topic "强化学习 做市商"

# 整合已有章节为完整论文
python scripts/paper_write.py --assemble --topic "论文主题"

# 润色+查重+投稿信
python scripts/paper_submit.py paper.md --polish english intensive --plagiarism-check
python scripts/paper_submit.py paper.md --venue NeurIPS --cover-letter
python scripts/paper_submit.py paper.md --response-letter "审稿意见..."
```

### 金融数据（A股+美股）

```bash
# 获取A股日线（akshare，无需API Key）
python -c "
from scripts.data_pipeline import fetch_a_stock, add_return_features
df = fetch_a_stock('000001.SZ', '2024-01-01', '2025-01-01')
df = add_return_features(df)
df = add_moving_averages(df)
print(df.tail())
"

# 获取美股数据（yfinance）
python -c "
from scripts.data_pipeline import fetch_us_stock
df = fetch_us_stock('AAPL', '2024-01-01', '2025-01-01')
print(df.tail())
"

# 获取A股板块行情
python -c "
from scripts.data_pipeline import fetch_a_sector
df = fetch_a_sector('新能源')
print(df.head())
"
```

---

## AI 路由策略（已激活）

```
┌──────────────────────────────────────────────────────┐
│                    Cursor（本地 Claude）               │
│                                                      │
│              日常对话 / 复杂推理 / 代码分析               │
└──────────────────────────────────────────────────────┘
                           +
┌──────────────────────────────────────────────────────┐
│              脚本层 ai_router.py                     │
│                                                      │
│  任务分类器 → 自动识别任务类型                        │
│        ↓                                            │
│  多模型路由 → 分配最优模型                           │
│        ↓                                            │
│  ┌──────────────┐  ┌──────────────┐              │
│  │  DeepSeek     │  │  B.AI 中转    │              │
│  │  (直连)       │  │  (统一 Key)   │              │
│  │               │  └──────┬───────┘              │
│  │  中文写作      │         │                      │
│  │  快速检索      │    ┌────┴────┐                 │
│  │  简单问答      │    ▼         ▼                 │
│  └──────────────┘  GPT-5.5  Gemini-3.1-Pro         │
│                  (代码/英文)   (推理/长文本)           │
└──────────────────────────────────────────────────────┘
```

| 任务类型 | 模型 | 通道 | 原因 |
|---------|------|------|------|
| 文献检索/综述 | DeepSeek | 直连 | 快、便宜 |
| 中文论文/研报 | DeepSeek | 直连 | 中文能力强 |
| 英文润色/翻译 | GPT-5.5 | B.AI | 英文质量最高 |
| 代码生成/分析 | GPT-5.5 | B.AI | 代码能力最强 |
| 数学推理 | Gemini-3.1-Pro | B.AI | 推理能力最强 |
| 数据分析 | GPT-5.5 | B.AI | 分析能力强 |
| 长上下文/多模态 | Gemini-3.1-Pro | B.AI | 超长文本理解 |

---

## MCP 工具

| MCP | 用途 | 状态 |
|-----|------|------|
| `finviz-sec` | 美股筛选、SEC文件、内幕交易 | ✅ 已验证 |
| `financial` | 股票、外汇、加密货币、宏观经济 | ✅ 已验证 |
| `finagent` | Yahoo Finance 市场数据 | ✅ 已验证 |
| `brave-search` | 财经新闻、研报搜索 | ✅ Key 已配置 |
| `arxiv` | 学术论文检索与下载 | ✅ 已验证 |
| `fetch` | 网页正文抓取 | ✅ 已验证 |
| `context7` | 官方文档实时查询 | ✅ 已验证 |
| `sqlite` | SQL 分析 CSV/Excel | ✅ 已验证 |
| `todo` | 研究任务管理 | ✅ 已验证 |
| `memory` | 跨会话记忆 | ✅ 已验证 |
| `github` | 代码仓库管理 | ✅ Token 已配置 |

---

## 数据源覆盖

| 市场 | 数据源 | 数据类型 |
|------|--------|----------|
| **A股** | akshare（免费，无 Key）| 日线、财务报表、指数、板块 |
| **美股** | yfinance + Finviz（免费）| 行情、财务、期权、筛选 |
| **宏观** | FRED + SEC EDGAR（免费）| GDP、CPI、利率、国债 |
| **加密** | CoinGecko（免费）| 币种价格、行情 |
| **论文** | arXiv（免费）| 检索、下载、全文 |

---

## 安装依赖

```bash
cd /Users/xuzheyi/Desktop/工作流搭建
pip install -r requirements.txt
```

新增依赖（本次更新）：
- `akshare==1.14.20` — A股数据
- `yfinance==0.2.40` — 美股数据
- `anthropic==7.0.0` — Claude SDK（用于 ai_router 多模型路由）

---

## 外接 API Key 配置

### 已配置
| 服务 | 状态 | 配置位置 |
|------|------|---------|
| DeepSeek | ✅ 已配置真实 Key | `config/llm_config.json` |
| Brave Search | ✅ MCP 已配置 | Cursor MCP 设置 |
| GitHub | ✅ Token 可用 | Cursor MCP 设置 |
| Claude | ✅ 通过 Cursor 直接使用 | 无需额外配置 |
| GPT-4o | ⏳ 待配置 | `config/llm_config.json` |
| Gemini | ⏳ 待配置 | `config/llm_config.json`（base_url 已预设）|

### 待配置的 Key（按需填入）

**FRED API Key**（解锁宏观数据：GDP、CPI、利率、国债收益率等）
1. 访问 https://fred.stlouisfed.org/docs/api/api_key.html 免费注册
2. 将 Key 填入 `mcp_servers/financial-mcp-server/.env`：
   ```
   FRED_API_KEY=你的Key
   ```

**其他可选 Key**（`mcp_servers/financial-mcp-server/.env` 中已预设占位符）：
- `ALPHA_VANTAGE_API_KEY` — 股票日内数据（免费额度 25次/天）
- `TIINGO_API_KEY` — 高质量历史数据（50次/小时）
- `POLYGON_API_KEY` — 实时+历史数据（5次/分钟）
- `COINGECKO_API_KEY` — 加密货币数据（30次/分钟）
