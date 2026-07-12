# Copilot Instructions for 论文-研报工作流

> This file provides GitHub Copilot with project context and instructions.
> Place in `.github/copilot-instructions.md` at the repository root.
>
> **适用工具**: GitHub Copilot · Claude Code · Codex（通用 AI 编码工具均可）

## 项目概述

**论文-研报工作流 (FinResearch Agent)** 是经济金融领域的 AI 研究助手，自动化从文献综述到可投稿论文的全流程。

- **语言**: Python 3.10+
- **数据**: MCP (Model Context Protocol) 服务器，`{{MCP_COUNT}}` 个数据源（见 `scripts/count_mcp.py`）
- **关键**: 大部分数据源无需 API Key（世界银行、IMF、OECD 等免费数据）

---

## 自动启动流程（每次对话必须执行）

```
用户打开对话
        ↓
① 问候 + 能力介绍（固定文案，不跳过）
        ↓
② 后台运行 python scripts/health_check.py --json
        ↓
  ┌─ API Key 缺失 → 简短提示（不阻塞）
  ├─ LLM 不可用 → 询问是否继续
  └─ 系统就绪 → 等待研究方向
        ↓
③ 询问研究方向 → 用户描述 → 开始研究
```

**第一步问候是强制要求**，不要跳过。直接开始工作会显得突兀。

### 诊断交互（三平台统一）

1. 运行诊断脚本，打印四类问题分类报告
2. 读取 `InteractionResult` 结构
3. 在**对话中**向用户展示问题，等待回复
4. 根据用户回复执行操作

**API Key 缺失**：AI 在对话中询问，用户回复后执行配置或继续
**LLM 不可用**：AI 在对话中展示问题 + 修复步骤，询问是否继续

> Claude Code 和 Codex 不支持 `input()`，必须通过对话交互。

---

## 项目结构

```
scripts/
├── health_check.py           # 系统诊断（每次启动时运行）
├── setup_wizard.py          # 交互式配置向导
├── agent_pipeline.py        # 主编排器
├── research_framework/      # 研究执行层（30个模块）
│   ├── pipeline.py         # 研究执行
│   ├── modern_did.py       # 现代 DID
│   ├── regression_engine.py  # OLS/DID/PSM/IV/GMM
│   ├── fin_charts.py      # matplotlib 图表（≥300 DPI）
│   └── data_fetcher.py    # MCP 数据获取
├── core/                   # Agent 编排模块
├── research_directions/     # 研究方向（12个）
mcp_servers/               # `{{MCP_COUNT}}` 个 MCP 数据服务器
knowledge/skills/           # 17 个技能文档（真相源）
```

---

## 关键能力

### 数据获取（MCP）

| 数据类型 | MCP 服务器 | 需要 Key |
|---------|-----------|---------|
| A股行情/财务 | `user-tushare` | TUSHARE_TOKEN |
| 中国宏观 | `user-financial` | 无 |
| 美联储/FOMC | `user-fed-data` | 无 |
| 世界银行 | `user-wb-data` | 无 |
| IMF | `user-imf-data` | 无 |
| OECD | `user-oecd-data` | 无 |
| 国债收益率 | `user-eodhd` | EODHD_API_KEY |
| 研报/新闻 | `user-eastmoney-reports` | 无 |
| 外汇/大宗 | `user-enhanced-finance` | 无 |
| NBER Working Papers | `user-nber-wp` | 无 |

> 大部分 MCP **无需 API Key**，直接调用即可。

### 【核心原则】数据优先

**数据验证必须前移到想法生成阶段，不等到数据获取阶段**

```
传统流程（有缺陷）：
想法生成 → 新颖性验证 → 实证设计 → 数据获取 ← 到这里才发现无数据！

改进流程（当前）：
想法生成 → 【想法-数据交叉验证】→ 数据已确认可行 → 继续

脚本：`scripts/idea_data_checker.py` — 想法生成后立即检查数据可行性
```

**禁止静默模拟数据**：真实数据不可用时，必须停下来让用户选择（补充数据/授权模拟/更换主题）

### 计量方法（49种）

- **DID**: Callaway-SantAnna, Sun-Abraham, Borusyak, Goodman-Bacon, dCdH
- **合成控制**: Abel, Arkhangelsky
- **RDD**: 精确/模糊/局部线性
- **IV/2SLS**: 面板 IV、Jackknife IV
- **Panel GMM**: Arellano-Bond、Blundell-Bond
- **其他**: 空间回归、三重差分、面板分位数、交互固定效应、局部投影、Event Study

### 论文写作

- LaTeX 输出（41种期刊模板）
- JF/JFE/RFS/AER 等英文顶刊
- 经济研究/金融研究/管理世界/会计研究 等中文顶刊
- 多轮对抗性 review

### 图表生成

- matplotlib / seaborn / plotly
- ≥300 DPI，PDF/SVG/PNG
- 20种专业金融图表预设

---

## 可用技能（17个）

技能文档在 `knowledge/skills/`（Claude Code/Copilot 通过读取这些文件工作）：

| 技能 | 功能 |
|------|------|
| `fin-full-pipeline` | 端到端研究流水线 |
| `fin-idea-discovery` | 研究想法发现 + 数据验证 |
| `fin-lit-review` | 系统性文献综述 |
| `fin-generate-idea` | 8-12 个排序想法 |
| `fin-novelty-check` | 新颖性验证（顶刊查重）|
| `fin-experiment-design` | DID/IV/RD/PSM 完整方案 |
| `fin-paper-writing` | 论文写作编排 |
| `fin-paper-draft` | 正文生成（LaTeX）|
| `fin-paper-plan` | 大纲生成 |
| `fin-paper-figure` | 图表生成（≥300 DPI）|
| `fin-paper-convert` | LaTeX 编译 |
| `fin-review-loop` | 多轮对抗性 review |
| `fin-submit-check` | 投稿前检查 |
| `fin-data-acquisition` | MCP 数据 + 回归脚本 |
| `fin-brief-generator` | 生成 FIN_BRIEF.md |
| `fin-ref-paper` | BibTeX 参考文献 |
| `fin-viz-launch` | 自然语言 → 学术图表 |

---

## 如何帮助用户

### 开始新研究项目

1. 运行 `python scripts/health_check.py` 诊断系统状态
2. 理解研究问题
3. 通过 MCP 工具搜索文献
4. 设计识别策略
5. 通过 MCP 服务器获取数据
6. 运行回归（`scripts/research_framework/`）
7. 生成 LaTeX 手稿

### 金融分析

1. 用 `user-tushare` 获取 A股数据
2. 用 `user-wb-data` / `user-imf-data` 获取宏观数据
3. 用 `scripts/research_framework/fin_charts.py` 生成图表

### 计量分析

1. 导入 `scripts.research_framework.regression_engine`
2. 用 `modern_did.py` 做现代 DID
3. 通过 `robustness_runner.py` 做稳健性检验

---

## 环境变量

参考 `.env.example`。主要变量：

| 变量 | 必需 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 推荐 | DeepSeek 直连（中文最优）|
| `RELAY_API_KEY` | 可选 | B.AI 中转（GPT/Claude）|
| `TUSHARE_TOKEN` | A股必需 | Tushare Pro Token |
| `EODHD_API_KEY` | 美宏观可选 | EODHD |
| `BRAVE_SEARCH_API_KEY` | 搜索可选 | Brave Search |

---

## 8 步研究流程

无论使用哪个 AI 工具，工作流一致：

| 步骤 | 入口命令 | 输出 |
|---|---|---|
| 0. 系统自检 | `python scripts/health_check.py --json` | 状态报告 |
| 1. 研究想法 | `python scripts/agent_pipeline.py --topic "..."` | `output/fin-ideas/IDEA_REPORT.md` |
| 1.5 想法-数据 | `python scripts/idea_data_checker.py --idea-file <path>` | 可行性报告 |
| 2. 文献综述 | `python scripts/literature_download.py --query "..."` | `output/fin-literature/` |
| 3. 新颖性验证 | `python scripts/agent_pipeline.py --topic "..." --novelty-check` | `output/fin-novelty/NOVELTY_REPORT.md` |
| 4. 实证设计 | `python scripts/research_framework/pipeline.py --mode design --topic "..."` | `output/fin-refinement/REFINED_DESIGN.md` |
| 5. 数据获取 | `python scripts/universal_data_fetcher.py fetch --data-type a_stock_financial` | CSV / Parquet |
| 6. 论文写作 | `python scripts/agent_pipeline.py --topic "..." --venue "经济研究"` | `output/fin-manuscript/` |
| 7. 对抗性 Review | `python scripts/core/llm_reviewer.py --draft paper.md --no-llm` | `output/fin-review/round_N/` |

---

## 关键入口脚本速查

| 脚本 | 用途 | 必填参数 |
|---|---|---|
| `scripts/health_check.py` | 系统自检 | `--json` |
| `scripts/setup_wizard.py` | 交互式配置向导 | `--guided` |
| `scripts/register_mcp_servers.py` | 注册 MCP 服务器 | `--profile academic` |
| `scripts/agent_pipeline.py` | 端到端流水线 / 新颖性检查 | `--topic "..."` |
| `scripts/idea_data_checker.py` | 想法-数据交叉验证 | `--idea-file <path>` |
| `scripts/literature_download.py` | 文献综述下载 | `--query "..."` |
| `scripts/research_framework/pipeline.py` | 研究执行 | `--mode design\|full\|review` |
| `scripts/universal_data_fetcher.py` | 数据获取 | `fetch --data-type ...` |
| `scripts/core/llm_reviewer.py` | 对抗性 Review | `--draft <path>` |

---

## 故障排查

### ModuleNotFoundError: No module named 'scripts'

项目已添加 `scripts/core/_bootstrap.py` 自动注入 `sys.path`。如果仍报此错误：

```bash
# 方案 A：editable install
pip install -e .

# 方案 B：手动 PYTHONPATH
PYTHONPATH=. python scripts/agent_pipeline.py --topic "..."
```

### 平台检测不到

```bash
python -c "from scripts.core.ide_platform import PLATFORM; print(PLATFORM)"
```

应输出 `cursor` / `claude_code` / `vscode` / `generic` 之一。

### MCP 服务器没注册

```bash
python scripts/register_mcp_servers.py --list
python scripts/register_mcp_servers.py --profile academic
```

---

## 约束

- **禁止编造数据** — 始终使用 MCP 工具或用户提供的数据文件
- **引用必须标注来源和日期**
- 中文顶刊遵循各自的 LaTeX 模板
- 运行 `pytest tests/` 验证改动
