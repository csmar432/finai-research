# 论文-研报工作流 · 使用指南

> 全面介绍如何配置、启动和高效使用本系统。

---

## 目录

1. [系统概览](#1-系统概览)
2. [安装配置](#2-安装配置)
3. [核心工作流](#3-核心工作流)
4. [MCP 数据配置](#4-mcp-数据配置)
5. [实证分析流程](#5-实证分析流程)
6. [论文写作流程](#6-论文写作流程)
7. [高级功能](#7-高级功能)
8. [常见问题](#8-常见问题)

---

## 1. 系统概览

### 1.1 系统架构

```
用户（自然语言）
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│              Cursor Agent (本地 Claude)                    │
│         自然语言 → 意图理解 → 模块编排 → 论文/研报       │
└─────────────────────────────────────────────────────────┘
    │
    ├── scripts/core/          核心Agent模块（70个）
    │   ├── agent_loader.py    Agent加载
    │   ├── agent_state.py     状态管理
    │   ├── memory.py          三层记忆
    │   ├── planner.py         任务分解
    │   ├── orchestrator.py    流水线编排
    │   ├── model_router.py    模型路由
    │   ├── llm_reviewer.py   LLM评审
    │   ├── hitl_gate.py      人工审核门
    │   └── self_evolution.py 自我进化
    │
    ├── scripts/research_framework/   研究执行层（10个）
    │   ├── pipeline.py        标准流水线
    │   ├── enhanced_pipeline.py  增强流水线
    │   ├── data_fetcher.py    数据获取 + 7层fallback
    │   ├── data_validator.py  数据验证
    │   ├── regression_engine.py  DID/OLS/PSM/IV/GMM
    │   ├── modern_did.py      现代DID（EventStudy/SDID/HDRD）
    │   ├── iv_panel.py        IV/Panel/GMM
    │   ├── robustness_runner.py  稳健性检验
    │   └── report_generator.py  LaTeX/Word双格式
    │
    ├── scripts/research_directions/  研究方向（6个）
    │   ├── digital_finance.py    数字金融
    │   ├── green_finance.py      绿色金融/ESG
    │   ├── macro_finance.py      宏观金融
    │   ├── asset_pricing.py     资产定价
    │   ├── corporate_finance.py 公司金融
    │   └── carbon_economics.py   碳经济学
    │
    └── mcp_servers/           MCP数据服务器（28个）
        ├── user-tushare/      A股数据
        ├── user-financial/    全球宏观
        ├── user-eodhd/        美国宏观
        ├── user-eastmoney_*/  东方财富系
        ├── user-wb-data/      世界银行
        ├── user-imf-data/     IMF数据
        ├── user-yfinance/     美股
        ├── user-arxiv/        学术论文
        ├── user-nber-wp/      NBER
        └── ...（共28个）
```

### 1.2 核心能力矩阵

| 能力 | 模块 | 状态 |
|------|------|------|
| 文献检索与综述 | `literature_vector_store.py` | ✅ |
| 研究想法生成 | `research_directions/` | ✅ |
| 新颖性验证 | 语义相似度 + MCP搜索 | ✅ |
| 实证方法设计 | `modern_did.py`, `iv_panel.py` | ✅ |
| 数据获取 | `data_fetcher.py` + 28个MCP | ✅ |
| 回归分析 | `regression_engine.py` | ✅ |
| 稳健性检验 | `robustness_runner.py` | ✅ |
| 论文写作 | `report_generator.py` + LaTeX | ✅ |
| 图表生成 | matplotlib + seaborn | ✅ |
| PDF检查 | `pdf_vision_check.py` | ✅ |
| LaTeX质量 | `latex_lint.py`, `latex_diff.py` | ✅ |
| 对抗性Review | `reviewer_calibrator.py` | ✅ |
| 自主实验 | `autonomy_loop.py` + BFTS | ✅ |
| 跨会话知识 | `cross_session_knowledge.py` | ✅ |
| 断点续传 | `checkpoint_pipeline_integration.py` | ✅ |
| 事件驱动 | `macro_event_bus.py` | ✅ |
| 自我进化 | `self_evolution.py` | ✅ |

---

## 2. 安装配置

### 2.1 基础安装

```bash
cd /Users/xuzheyi/Desktop/论文-研报工作流

# 创建虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 核心安装
pip install -e .

# 配置API密钥（至少需要一个）
echo "DEEPSEEK_API_KEY=sk-your-key" > .env
```

### 2.2 按需扩展安装

```bash
# 向量文献库（RAG + 语义检索）
pip install -e ".[rag]"

# VLM图表评估（深度学习）
pip install -e ".[deep-learning]"

# 计量经济扩展（DID/IV/GMM/面板）
pip install -e ".[econometrics]"

# 云端代码执行（安全沙箱）
pip install -e ".[sandbox]"
# 需额外设置 E2B_API_KEY

# 浏览器自动化（动态网页抓取）
pip install -e ".[browser]"
# 安装后需运行：playwright install chromium

# 全量安装
pip install -e ".[all]"

# 从 requirements 文件安装
pip install -r requirements-optional.txt
```

### 2.3 Cursor Agent 配置

在 Cursor 设置中添加 MCP 服务器：

1. **打开 Cursor Settings** → **MCP Servers**
2. **添加服务器**（两种方式）:

**方式 A: 复用已配置的 MCP（推荐）**

```json
{
  "mcpServers": {
    "user-tushare": { "command": "uvicorn", "args": ["mcp_servers.user_tushare.server:app", "--port", "8765"] },
    "user-financial": { "command": "uvicorn", "args": ["mcp_servers.user_financial.server:app", "--port", "8766"] },
    "user-eodhd": { "command": "uvicorn", "args": ["mcp_servers.user_eodhd.server:app", "--port", "8767"] }
  }
}
```

**方式 B: 使用独立 MCP 服务器目录**

```bash
# 启动所有MCP服务器
cd mcp_servers
docker-compose up -d
```

### 2.4 环境变量配置

复制并编辑 `.env.example`:

```bash
cp .env.example .env
```

主要环境变量：

```bash
# 必需（至少一个）
DEEPSEEK_API_KEY=sk-xxx          # DeepSeek API（推荐，免费额度充足）
OPENAI_API_KEY=sk-xxx            # OpenAI GPT-4

# 可选
ANTHROPIC_API_KEY=sk-ant-xxx    # Claude（VLM图表检查需要）
TUSHARE_TOKEN=xxx                # Tushare Pro（A股数据）
E2B_API_KEY=xxx                 # E2B云端沙箱
FRED_API_KEY=xxx                # 美联储数据
WB_API_KEY=xxx                  # 世界银行
```

---

## 3. 核心工作流

### 3.1 工作流总览

```
用户输入研究主题
        │
        ▼
┌──────────────────────────────────────────┐
│          ① 想法发现 (fin-idea-discovery)    │
│  文献综述 → 想法生成 → 新颖性验证 → 实证设计 │
└──────────────────────────────────────────┘
        │ [Checkpoint: 用户确认方向]
        ▼
┌──────────────────────────────────────────┐
│          ② 论文写作 (fin-paper-writing)    │
│  大纲 → 写作 → 图表 → Review → 精修       │
└──────────────────────────────────────────┘
        │ [Checkpoint: 用户审阅]
        ▼
┌──────────────────────────────────────────┐
│          ③ 格式转换 (fin-paper-convert)    │
│  LaTeX编译 → PDF检查 → 匿名处理           │
└──────────────────────────────────────────┘
        │
        ▼
    论文PDF
```

### 3.2 完整端到端流程

```
Skill: fin-full-pipeline "关税政策对A股出口型企业创新的影响"
```

这会依次执行：

1. **文献综述** (`fin-lit-review`): 搜索近5年相关文献，构建引文网络
2. **想法生成** (`fin-generate-idea`): 生成8-12个研究想法，筛选数据可行的方向
3. **新颖性验证** (`fin-novelty-check`): 在JF/JFE/RFS中搜索，确认无重复
4. **实证设计** (`fin-experiment-design`): 选择DID/IV/PSM，确定控制变量
5. **数据获取** (`fin-data-acquisition`): 通过MCP获取数据，自动填充变量
6. **论文大纲** (`fin-paper-plan`): 生成结构化大纲（Introduction → Conclusion）
7. **正文写作** (`fin-paper-draft`): 分章节写作，确保学术规范
8. **图表生成** (`fin-paper-figure`): matplotlib生成高质量图表（≥300 DPI）
9. **对抗性Review** (`fin-review-loop`): 多轮严格评审
10. **LaTeX编译** (`fin-paper-convert`): 生成PDF

### 3.3 分步执行

如果需要更细粒度控制，可以分步执行：

```bash
# Step 1: 文献综述
Skill: fin-lit-review "碳排放权交易制度 绿色创新 DID"

# Step 2: 想法生成
Skill: fin-generate-idea "碳排放权交易制度 绿色创新"

# Step 3: 新颖性验证（选定Idea后）
Skill: fin-novelty-check "碳排放权交易对企业绿色创新的影响——基于DID的实证研究"

# Step 4: 实证方法设计
Skill: fin-experiment-design "碳排放权交易对企业绿色创新的影响"

# Step 5: 数据获取
Skill: fin-data-acquisition "REFINED_DESIGN.md"

# Step 6: 论文大纲
Skill: fin-paper-plan "碳排放权交易对企业绿色创新的影响"

# Step 7: 正文写作
Skill: fin-paper-draft "PAPER_OUTLINE.md"

# Step 8: 图表生成
Skill: fin-paper-figure "FIGURE_PLAN.md"

# Step 9: Review循环
Skill: fin-review-loop "fin-manuscript/draft_v1/"

# Step 10: LaTeX编译
Skill: fin-paper-convert "fin-manuscript/draft_v2/"
```

---

## 4. MCP 数据配置

### 4.1 MCP 数据获取优先级

```
需求 → MCP工具（优先）→ data/目录（用户提供）→ 模拟数据（仅演示）
```

### 4.2 主要 MCP 工具速查

**宏观经济指标**

```python
# 全球GDP
server: user-wb-data
tool: get_wb_indicator
params: { "country_code": "CHN", "indicator": "wb_gdp_usd" }

# 中国CPI/M2/GDP
server: user-financial
tool: get_macro_china
params: { "indicator": "cpi" }

# 美国国债收益率曲线
server: user-eodhd
tool: get_ust_yield_rates
params: { "year": 2025 }

# 美联储利率/FOMC
server: user-fed-data
tool: get_fed_interest_rate
params: { "years": 5 }
```

**A股数据**

```python
# 行情/财务（需Tushare Token）
server: user-tushare
tool: get_daily_quote
params: { "ts_code": "000001.SZ", "start_date": "20200101", "end_date": "20241231" }

# 研报/新闻/分析师
server: user-eastmoney-reports
tool: get_research_report
params: { "ts_code": "000001.SZ", "max_results": 20 }

# 北向资金
server: user-stock-data
tool: stock_north_flow
params: { "market": "all" }
```

**外汇/大宗商品**

```python
server: user-enhanced-finance
tool: get_forex_hist
params: { "currency_pair": "USD/CNY", "start_date": "20200101", "end_date": "20241231" }

server: user-enhanced-finance
tool: get_shipping_index
params: { "index_name": "bdi" }
```

### 4.3 组合数据获取

`data_fetcher.py` 支持 7 层 fallback 链：

```python
# 优先级：MCP工具 → akshare缓存 → CSMAR → Wind → 模拟数据
fetcher = DataFetcher()
data = await fetcher.fetch(
    source="gdp_growth",
    region="china",
    freq="quarterly",
    start_date="2018-01-01",
    end_date="2024-12-31"
)
```

---

## 5. 实证分析流程

### 5.1 计量方法支持

| 方法 | 模块 | 适用场景 |
|------|------|---------|
| 标准DID | `regression_engine.py` | 政策前后对照 |
| 事件研究法 | `modern_did.py` | 动态效应估计 |
| 交错DID (Callaway & Sant'Anna) | `modern_did.py` | 不同处理时间 |
| 堆叠DID (Sun & Abraham) | `modern_did.py` | 异质性处理效应 |
| 鞘基DID | `modern_did.py` | 高维固定效应 |
| 外生IV | `iv_panel.py` | 内生性处理 |
| 面板数据 | `iv_panel.py` | 双向固定效应 |
| GMM | `iv_panel.py` | 动态面板 |
| PSM-DID | `regression_engine.py` | 选择偏差 |
| RDD | `regression_engine.py` | 断点回归 |

### 5.2 标准回归流程

```python
from scripts.research_framework.regression_engine import RegressionEngine

engine = RegressionEngine()
result = await engine.run_did(
    treatment_var="carbon_trade",
    outcome_var="green_innovation",
    unit_var="stock_code",
    time_var="year",
    controls=["size", "leverage", "roa", "age"],
    fixed_effects=["industry", "year"],
    cluster="industry"
)
print(result.summary())
```

### 5.3 稳健性检验清单

`robustness_runner.py` 自动执行：

- [ ] 替换被解释变量
- [ ] 改变样本区间
- [ ] 排除直辖市/特殊地区
- [ ] 控制交互固定效应
- [ ] 改变聚类层级
- [ ] PSM配对后回归
- [ ] 工具变量法
- [ ] 滞后效应检验

---

## 6. 论文写作流程

### 6.1 期刊格式支持

**英文顶刊**

| 期刊 | 结构 | 字数 | 格式 |
|------|------|------|------|
| JF | 6节 | ~40,000 | AEA |
| JFE | 6节 | ~40,000 | JFE |
| RFS | 6节 | ~45,000 | RFS |
| JME | 6节 | ~35,000 | JME |

**中文顶刊**

| 期刊 | 结构 | 字数 | 格式 |
|------|------|------|------|
| 经济研究 | 6节 | ~20,000 | CTeX |
| 金融研究 | 6节 | ~20,000 | CTeX |
| 管理世界 | 6节 | ~15,000 | CTeX |

### 6.2 模板使用

```bash
# 列出所有模板
python scripts/journal_template.py --list

# 生成指定模板
python scripts/journal_template.py --generate JFE output/paper.tex
python scripts/journal_template.py --generate 经济研究 output/paper.tex

# 生成带数据的模板
python scripts/journal_template.py --generate JFE output/paper.tex \
  --data data/finance/regression_results.csv
```

### 6.3 LaTeX 质量检查

```bash
# 实时语法检查
python scripts/core/latex_lint.py data/test_templates/经济研究.tex

# 版本diff追踪
python scripts/core/latex_diff.py output/draft_v1/main.tex output/draft_v2/main.tex

# PDF视觉检查（需VLM）
python scripts/core/pdf_vision_check.py output/draft_v2/main.pdf
```

---

## 7. 高级功能

### 7.1 事件驱动自动化

监控宏观事件，自动触发研究流程：

```bash
python scripts/event_monitor.py \
  --interval 300 \
  --events "NFP,CPI,FOMC,GDP" \
  --topic "宏观事件冲击"
```

支持的宏观事件：

| 事件 | 代码 | 影响市场 |
|------|------|---------|
| 非农就业 | NFP | 美股/美债/黄金 |
| CPI/PPI | CPI | 全球 |
| FOMC利率 | FOMC | 全球 |
| GDP增速 | GDP | 本币资产 |
| 制造业PMI | PMI | A股/工业品 |

### 7.2 向量文献库

构建本地文献向量库，支持语义检索：

```bash
# 初始化文献库
python scripts/core/literature_vector_store.py \
  --init \
  --papers data/papers/ \
  --chunk-level section

# 语义搜索
python scripts/core/literature_vector_store.py \
  --query "碳排放权交易 绿色创新" \
  --top-k 10
```

### 7.3 跨会话知识积累

自动积累历史研究洞察，跨会话复用：

```python
from scripts.core.cross_session_knowledge import CrossSessionKnowledge

ck = CrossSessionKnowledge()
ck.add_insight("DID平行趋势检验应包含事件前3期", source="文献")
ck.add_insight("碳排放权试点地区处理效应最强", source="实证")

# 检索相关洞察
insights = ck.retrieve("绿色创新 实证方法")
```

### 7.4 自主实验循环 (BFTS)

自动发现假设、生成实验、执行验证：

```python
from scripts.core.autonomy_loop import BFTSLoop

loop = BFTSLoop(topic="碳排放权对企业创新的影响")
result = await loop.run()
# 自动: 提出假设 → 设计实验 → 执行回归 → 分析结果
```

### 7.5 自我进化

基于任务结果自动改进系统：

```python
from scripts.core.self_evolution import SelfEvolution

se = SelfEvolution()
se.record_outcome(task_id="xxx", success=True, feedback="")
se.evolve_prompts()   # 根据成功案例优化prompt
se.evolve_gates()     # 根据判断准确性校准门控
se.generate_report()  # 生成进化报告
```

---

## 8. 常见问题

### Q1: 启动时报错 `ModuleNotFoundError`

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 重新安装
pip install -e .
```

### Q2: MCP 数据获取失败

1. 检查 API Key 配置：`cat .env`
2. 检查 MCP 服务器状态：`python scripts/core/mcp_tool_market.py --status`
3. 使用 fallback 数据源（无需 API Key）

### Q3: LaTeX 编译失败

```bash
# 检查 LaTeX 环境
which xelatex
which pdflatex

# macOS 安装
brew install --cask mactex

# 运行语法检查
python scripts/core/latex_lint.py your_paper.tex
```

### Q4: 计量回归结果不显著

1. 检查数据质量：`python scripts/research_framework/data_validator.py`
2. 尝试不同控制变量组合
3. 使用工具变量处理内生性
4. 检查是否存在样本选择偏差

### Q5: 如何添加自定义研究方向？

```python
# 1. 创建研究方向文件
# scripts/research_directions/custom_topic.py

from scripts.research_directions.base import ResearchDirection

class CustomTopic(ResearchDirection):
    name = "custom_topic"
    description = "自定义研究主题"

    def get_research_questions(self):
        return [
            "研究问题1",
            "研究问题2"
        ]

    def get_data_requirements(self):
        return {
            "required": ["变量A", "变量B"],
            "optional": ["变量C"]
        }
```

### Q6: 如何使用 Cursor Agent？

在 Cursor 中打开项目后，直接发送自然语言指令：

```
帮我设计一篇关于数字人民币对商业银行效率影响的实证论文，发表在金融研究，目标期刊字数2万字左右。
```

Cursor Agent 会自动调用所有必要的模块并完成全流程。
