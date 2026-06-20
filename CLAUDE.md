# 论文-研报工作流 · FinResearch Agent

> 经济金融领域 AI 研究助手。从研究想法到可投稿论文，集成 MCP 数据获取、因果推断、LaTeX 排版和对抗性 review 循环。

> **适用工具**: Claude Code · GitHub Copilot · Cursor（通用 AI 编码工具均可）

---

## 一句话

**"告诉我研究主题，我帮你：从文献综述 → 想法生成 → 实证设计 → 论文草稿 → LaTeX 编译，全自动。"**

---

## 快速开始

不需要记命令。直接说研究方向：

```
"我想研究关税政策对A股出口型企业创新的影响，设计一篇发表在经济研究的实证论文"
"帮我做数字金融领域的文献综述"
"有什么新的研究想法关于企业ESG表现和融资成本"
```

或用脚本直接运行：

```bash
python scripts/research_framework/pipeline.py --topic "碳排放权交易对企业绿色创新的影响"
python scripts/research_framework/pipeline.py --topic "..."
pytest tests/ -v
```

---

## 自动启动流程（每次对话必须执行）

```
用户打开对话
        ↓
① 问候 + 能力介绍（固定文案，不跳过）
        ↓
② 后台运行 python scripts/health_check.py --json
        ↓
③ 检查 MCP 注册状态：python scripts/register_mcp_servers.py --list（轻量）
        ↓
  ┌─ API Key 缺失 → 简短提示（不阻塞）
  ├─ LLM 不可用 → 询问是否继续
  └─ MCP 未注册 → 提示用户运行 `python scripts/register_mcp_servers.py`（不阻塞）
        ↓
④ 等待研究方向 → 用户描述 → 开始研究
```

**第一步问候是强制要求**，不要跳过。直接开始工作会显得突兀。

---

## 核心能力

### 数据获取（MCP，43个服务器）

| 你要什么 | 用这个 MCP |
|---------|-----------|
| A股行情/财务/融资融券 | `user-tushare`（需 TUSHARE_TOKEN）|
| 中国宏观（GDP/CPI/M2）| `user-financial` |
| 美联储/FOMC | `user-fed-data` |
| 世界银行宏观 | `user-wb-data` |
| IMF数据 | `user-imf-data` |
| OECD数据 | `user-oecd-data` |
| 美国经济分析局GDP | `user-bea-data` |
| 国债收益率/经济日历 | `user-eodhd`（需Key）或 `user-fed-data` |
| 美股/ETF/期权/财务 | `user-yfinance` |
| 研报/新闻/板块/分析师 | `user-eastmoney-reports` |
| 公募基金 | `user-eastmoney-fund` |
| 债券数据 | `user-eastmoney-bond` |
| 期权数据 | `user-eastmoney-option` |
| 外汇/航运/大宗商品 | `user-enhanced-finance` |
| 加密货币 | `user-cryptocompare` |
| SEC 10-K/10-Q/8-K | `user-sec-edgar` |
| 学术论文（全文）| `user-openalex`、`user-arxiv`、`user-context7`、`user-semantic-scholar` |
| NBER工作论文 | `user-nber-wp` |
| 中文文献（CSSCI/CNKI）| `user-chinese-literature`、`user-wanfang`、`user-csmar` |
| 中国专利数据 | `user-sipo` |
| 中国海关数据 | `user-chinese-customs` |
| Wind数据 | `user-wind`（需账号）|
| CSMAR国泰安 | `user-csmar`（需Key）|
| CEIC宏观 | `user-macro-ceic` |
| 省级/市级统计 | `user-province-stats`、`user-hubei-stats`、`user-wuhan-stats` |
| 新闻搜索 | `user-newsapi`（需Key）、`user-brave-search`（需Key）|
| 云端代码执行 | `user-e2b-mcp`（需Key）|
| 浏览器自动化 | `user-playwright-mcp` |
| 数据处理 | `user-pandas-mcp` |
| LaTeX排版检查 | `user-latex-mcp` |
| 文件系统操作 | `user-filesystem-mcp` |

> **注意**：以下 MCP 需要付费账号或 API Key 才能获取真实数据：
> - `user-tushare` — Tushare Pro Token（年费约 600-2000 元人民币）
> - `user-wind` — Wind 账号（机构付费，个人研究者通常无法获取）
> - `user-csmar` — CSMAR 国泰安（机构账号，通常需高校/机构购买）
> - `user-wanfang` / `user-cnki` — 需要机构网络权限或账号
> - `user-eodhd` — EODHD API Key（免费注册有每日额度限制）
> - `user-brave-search` — Brave Search API Key（免费注册每月有限额）
> - `user-newsapi` — NewsAPI Key（免费注册有限额）
> - `user-yfinance` / `user-sec-edgar` — 免费，无需 Key

### 计量方法（约30种独立算法，JF/JFE/RFS 标准）

> **重要说明**：以下方法中，标注 🔗 的依赖 `linearmodels`、`diff-in-diff2` 等第三方包；标注 ⭐ 的为独立 Python 实现。
> 数量为近似值，因部分估计器（如 TWFE × 3 种 SE × bootstrap 变体）存在重复计数。
>
> **独立验证状态**：标准 DID、Bacon 分解、CS(2021)、事件研究、空间回归（部分）有独立测试文件；其他方法的正确性依赖 statsmodels/linearmodels 间接保证。

- ⭐ **标准 DID**: 2x2 OLS + cluster-robust SE（HC0/HC1/CR0/CR1/CGM）
- ⭐ **事件研究**: pre/post 可视化 + 平行趋势检验
- ⭐ **Bacon 分解**: Goodman-Bacon (2021) 权重分解
- 🔗 **交错 DID**: Callaway-SantAnna (QJE 2021) — 需要 `pip install diff-in-diff2`；Sun-Abraham (REStud 2021)；Borusyak-Jaravel-Spinks (REStud 2024)；dCdH
- 🔗 **合成控制**: Abel (JASA 2016)；Arkhangelsky (Science 2021)
- ⭐ **RDD**: 精确/模糊/局部线性（三角核/均匀核）
- 🔗 **IV/2SLS**: 面板 IV、Jackknife IV — 依赖 `linearmodels`
- 🔗 **Panel GMM**: Arellano-Bond、Blundell-Bond — 依赖 `linearmodels`
- ⭐ **三重差分**: Triple-DiD（处理效应异质性稳健）
- ⭐ **面板分位数**: 固定效应分位数回归
- ⭐ **交互固定效应**: Bai (2009) 交互固定效应
- ⭐ **局部投影 DID**: Jordà (2005) 局部投影
- ⭐ **空间回归**: SAR/SEM/SDM/SLX — 部分依赖 `libpysal`
- ⭐ **敏感性分析**: Wild Cluster Bootstrap、Leamer 边界、异质性分析
  - Honest DiD (Rambachan-Roth 2023)：需 `pip install honestdid`；Rambachan & Roth (2023) REStud 的 Python 实现，提供 DeltaSD 和 DeltaRM 两种敏感性框架；旧版 homebrew 近似公式已移除（不正确）
- 🔗 **其他**: 面板门槛回归（Hansen 2000）、TVP-VAR、离散选择、因果森林 — 依赖 `linearmodels`/`sklearn`

### 论文写作

- LaTeX 输出（52种期刊格式（EN/ZH 44种+JP/DE 8种额外格式），EN/ZH: 经济研究/金融研究/JF/JFE/RFS 等，JP: Japanese Economic Review 等，DE: ZWiSt/AStA 等）
- JF / JFE / RFS / JAE / JPE / Econometrica 等英文顶刊
- 经济研究 / 金融研究 / 管理世界 / 会计研究 等中文顶刊
- 多轮对抗性 review 循环

### 图表生成

- matplotlib / seaborn / plotly
- 20种专业金融图表预设
- 输出格式：PDF / SVG / PNG（≥300 DPI）
- 数据溯源追踪（provenance）

---

## 项目结构

```
scripts/
├── agent_pipeline.py              # 主入口：端到端流水线
├── research_framework/           # 研究执行层（47个模块）
│   ├── pipeline.py            # 标准流水线
│   ├── modern_did.py          # 现代 DID（CS/SunAb/Borusyak/GB/dCdH）
│   ├── synthetic_control.py  # 合成控制法（Abadie et al. 2010）
│   ├── synthetic_did.py       # 合成DID（Arkhangelsky et al. 2021）
│   ├── local_projections_did.py  # 局部投影DID（Jordà 2005）
│   ├── triple_diff_did.py    # 三重差分DID
│   ├── panel_quantile_regression.py  # 面板分位数回归
│   ├── interactive_fixed_effects.py  # 交互固定效应（Bai 2009）
│   ├── spatial_regression.py  # 空间回归（SDM/SAR/SEM）
│   ├── iv_panel.py           # IV/Panel/GMM
│   ├── rdd.py                # 断点回归（RDD）
│   ├── regression_engine.py   # DID/OLS/PSM/GMM
│   ├── fin_charts.py         # 20种专业金融图表
│   ├── data_fetcher.py       # MCP数据获取（7层fallback）
│   ├── report_generator.py    # LaTeX/Word双格式
│   └── robustness_runner.py   # 18类稳健性检验
├── core/                         # Agent编排层（89个非测试模块）
│   ├── provenance.py            # 数据溯源追踪
│   ├── checkpoint.py             # 断点续传
│   ├── event_monitor.py          # 宏观事件监控（NFP/CPI/FOMC）
│   └── mcp_tool_market.py        # MCP工具市场
└── research_directions/          # 研究方向（12个）
    ├── digital_finance.py          # 数字金融
    ├── green_finance.py            # 绿色金融
    ├── carbon_economics.py         # 碳经济学
    ├── corporate_finance.py        # 公司金融
    ├── macro_finance.py            # 宏观金融
    ├── asset_pricing.py            # 资产定价
    ├── behavioral_finance.py        # 行为金融
    ├── fintech_innovation.py        # 金融科技创新
    ├── real_estate_finance.py      # 房地产金融
    ├── international_finance.py    # 国际金融
    └── political_economy_finance.py # 政治经济学

mcp_servers/                      # 43个MCP数据服务器
output/                           # 输出目录
├── fin-literature/              # 文献综述
├── fin-ideas/                   # 研究想法
├── fin-novelty/                # 新颖性验证
├── fin-refinement/              # 研究设计
├── fin-experiments/             # 实证结果
├── fin-review/                 # 对抗性review
└── fin-manuscript/             # 论文草稿
```

---

## 关键入口脚本

| 脚本 | 功能 |
|------|------|
| `scripts/agent_pipeline.py` | 完整流水线（主题 → 论文 PDF）|
| `scripts/health_check.py` | 系统健康检查（每次启动前必运行）|
| `scripts/idea_data_checker.py` | 想法-数据交叉验证（**新**）|
| `scripts/data_source_checker.py` | 数据源预检查（**新**）|
| `scripts/pipeline_checkpoint.py` | 强制交互 checkpoint（**新**）|
| `scripts/setup_wizard.py --guided` | 交互式配置向导 |
| `scripts/register_mcp_servers.py --list` | 列出 43 个 MCP 自动注册状态（首次必须跑）|
| `scripts/register_mcp_servers.py` | 一键注册所有 MCP 到 `~/.cursor/mcp.json` |
| `scripts/research_framework/pipeline.py` | 研究执行层 |
| `scripts/research_framework/modern_did.py` | 现代 DID 回归 |
| `scripts/research_framework/fin_charts.py` | 专业金融图表 |
| `scripts/research_framework/report_generator.py` | LaTeX 论文生成 |
| `scripts/demo_research_report.py` | 演示研报生成（**已修复静默fallback**）|
| `scripts/journal_template.py --list` | 列出所有期刊模板 |
| `scripts/event_monitor.py --test` | 测试事件监控 |

---

## 可用技能（18个）

技能文档在 `.claude/skills/`（Claude Code）、`.github/skills/`（Copilot）和 `knowledge/skills/`（真相源）。在 Cursor 中直接用 `Skill:` 语法触发。

| 技能 | 功能 |
|------|------|
| `fin-full-pipeline` | 端到端流水线（主题 → 论文 PDF）|
| `fin-idea-discovery` | 想法发现 + 数据验证 |
| `fin-lit-review` | 系统性文献综述 |
| `fin-generate-idea` | 8-12 个排序想法（含实证验证）|
| `fin-novelty-check` | 新颖性验证（JF/JFE/RFS 查重）|
| `fin-experiment-design` | 完整实证设计（DID/IV/RD/PSM）|
| `fin-paper-writing` | 论文写作编排 |
| `fin-paper-draft` | 正文生成（LaTeX）|
| `fin-paper-plan` | 大纲生成（52种期刊模板）|
| `fin-paper-figure` | 图表生成（≥300 DPI，20+类型）|
| `fin-paper-convert` | LaTeX 编译 |
| `fin-review-loop` | 多轮对抗性 review |
| `fin-submit-check` | 投稿前检查 |
| `fin-data-acquisition` | 数据获取 + 回归脚本生成 |
| `fin-brief-generator` | 生成 `FIN_BRIEF.md` |
| `fin-ref-paper` | BibTeX 参考文献管理 |
| `fin-viz-launch` | 自然语言 → 学术图表 |

---

## 核心原则

1. **数据优先** — 数据验证前移到想法生成阶段，不编造，不等到阶段5才发现无数据
2. **数据溯源** — 每次数据获取记录来源和时间戳
3. **禁止静默Fallback** — 模拟数据必须经用户明确授权才可使用
4. **强制交互Checkpoint** — 每阶段完成后暂停，等待用户确认，不自动继续
5. **生成-评审分离** — 写作和 review 由不同模块处理
6. **中文顶刊标准** — 经济研究 / 金融研究 / 管理世界（含稳健性检验）

---

## 研究流程（8步）

```
第0步  系统自检     → python scripts/health_check.py → 确认工具就绪
第1步  研究想法     → 描述方向 → 8-12个候选想法 → 确认
第1.5步想法-数据交叉验证 → idea_data_checker.py → 用户决策（补充数据/授权模拟/更换）→ 确认
第2步  文献综述     → literature_download.py + arxiv/openalex/semantic_scholar MCP → 引文网络 → 识别研究缺口
第3步  新颖性验证   → agent_pipeline.py --topic "..." (内部触发 NoveltyGate + llm_reviewer) → JF/JFE/RFS/arXiv/NBER 检索 → 输出新颖性评分 → 确认
第4步  实证设计     → research_framework/pipeline.py → DID/IV/RDD → REFINED_DESIGN.md → data_source_checker.py → 确认
第5步  数据获取     → universal_data_fetcher.py → 43个MCP → Python/Stata脚本 → 确认
第6步  论文写作     → research_framework/report_generator.py → 大纲 → 正文 → 图表 → LaTeX草稿
第7步  对抗性Review → core/llm_reviewer.py → 多轮严格评审 → 达到发表标准
```

### 关键入口速查

| 阶段 | 入口脚本 | 调用方式 |
|---|---|---|
| 0. 系统自检 | `scripts/health_check.py` | `python scripts/health_check.py --json` |
| 1. 想法生成 | `scripts/agent_pipeline.py` | `--topic "..."` |
| 1.5 想法-数据 | `scripts/idea_data_checker.py` | `--idea-file <path>` |
| 2. 文献综述 | `scripts/literature_download.py` | `--query "..."` |
| **3. 新颖性** | `scripts/agent_pipeline.py` | `--topic "..."` （内部 Stage: novelty-check，使用 `scripts/core/evolution_gate.py::NoveltyGate`） |
| 4. 实证设计 | `scripts/research_framework/pipeline.py` | `--mode design --refined-design <path>` |
| 5. 数据获取 | `scripts/universal_data_fetcher.py` | `--sources tushare,eastmoney` |
| 6. 论文写作 | `scripts/research_framework/report_generator.py` | `--outline <path>` |
| 7. Review | `scripts/core/llm_reviewer.py` | `--draft <path>` |
| Checkpoint 工具 | `scripts/checkpoint.py` | `from scripts.checkpoint import InteractivePipelineCheckpoint` |

---

## 环境变量

参考 `.env.example`，主要变量：

| 变量 | 必需 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 推荐 | DeepSeek 直连（中文写作/代码/分析）|
| `RELAY_API_KEY` | 可选 | B.AI 中转（GPT/Claude）|
| `TUSHARE_TOKEN` | A股必需 | Tushare Pro Token |
| `EODHD_API_KEY` | 美宏观可选 | EODHD |
| `FRED_API_KEY` | 美宏观可选 | FRED |
| `BRAVE_SEARCH_API_KEY` | 搜索可选 | Brave Search |

---

## 工具适配说明

本项目为三个 AI 编码工具提供完整支持：

| 目录 | 适用工具 | 说明 |
|------|---------|------|
| `scripts/` / `mcp_servers/` / `tests/` | 全部工具 | 核心业务逻辑，无 IDE 依赖 |
| `CLAUDE.md` | Claude Code（主要）/ Cursor / Codex | 项目主入口 |
| `.claude/` | Claude Code | 命令 + 技能文档 |
| `.cursor/rules/` | Cursor | 角色规则（analyst/paper_writer/researcher/mcp_tools/system-init）|
| `.cursor/skills/` | Cursor | 17 个 Skill 文件（原生 Skill 系统）|
| `.cursor/agents/` | Cursor | Agent 指令（literature-scout）|
| `.github/copilot-instructions.md` | GitHub Copilot | Copilot 指令文件 |
| `knowledge/skills/` | Claude Code / Copilot | 17 个技能文档（真相源，不含 README.md；目录副本到 .claude/skills/ 和 .github/skills/）|

## Skill: 语法（Cursor 专用）

在 Cursor 中，使用 `Skill:` 语法触发自动化流程。例如：

```
Skill: fin-full-pipeline
```
触发端到端流水线（主题 → 论文 PDF）。

可用的 Skill 语法：
- `Skill: fin-full-pipeline` — 完整流水线
- `Skill: fin-idea-discovery` — 想法发现 + 数据验证
- `Skill: fin-lit-review` — 系统性文献综述
- `Skill: fin-generate-idea` — 8-12 个排序想法
- `Skill: fin-novelty-check` — 新颖性验证
- `Skill: fin-experiment-design` — DID/IV/RDD 方案设计
- `Skill: fin-paper-writing` — 论文写作编排
- `Skill: fin-paper-draft` — 正文生成（LaTeX）
- `Skill: fin-paper-figure` — 图表生成
- `Skill: fin-review-loop` — 对抗性 review
- `Skill: fin-data-acquisition` — MCP 数据获取
- `Skill: fin-brief-generator` — 生成 FIN_BRIEF.md

直接用自然语言描述需求也可以正常工作，Skill 语法是快捷方式。

---

## 参考架构

- [Night Owl Research Agent (NORA)](https://github.com/GRIND-Lab-Core/night_owl_research_agent)
- [PaperOrchestra (Google)](https://github.com/google-research/paper-orchestra)
- [ARK (KAUST)](https://github.com/kaust-ark/ARK)
- [Qiongli (穷理)](https://github.com/jxpeng98/qiongli)
