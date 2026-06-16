# AI 工具启动指南 / AI Tool Start Guide

> 本项目同时支持 **Cursor / Claude Code / GitHub Copilot (Codex)** 三种 AI 编码工具。
> 选择你最常用的那个，按对应步骤启动即可。

| 工具 | 入口文件 | 状态 |
|---|---|---|
| **Cursor** | `QUICKSTART.md` + `.cursor/rules/` | 最完善（5 个角色规则 + 19 个 Skill） |
| **Claude Code** | `CLAUDE.md` + `.claude/skills/` | 完整（自动启动流程 + 8 步研究流程） |
| **GitHub Copilot / Codex** | `.github/copilot-instructions.md` + `.github/skills/` | 基础（symlink 共享 Skills） |

---

## 1. Cursor

### 启动步骤

```bash
# 1. 克隆项目
git clone https://github.com/csmar432/FinAI-Research-Workflow.git
cd FinAI-Research-Workflow

# 2. 安装
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. 配置（首次）
python scripts/setup_wizard.py --guided
python scripts/health_check.py --json

# 4. 在 Cursor 中打开
cursor .
```

### 在 Cursor 中使用

打开项目后，直接在 **AI 对话框**输入研究主题即可。例如：

```
我想研究数字金融对企业创新的影响，目标是《经济研究》
```

或者显式调用 Skill：

```
Skill: fin-full-pipeline
```

更多 Skill 列表见 [`.cursor/skills/`](../.cursor/skills/)。

### 关键文件

- `QUICKSTART.md` — 快速开始
- `.cursor/rules/*.mdc` — 5 个角色规则
- `.cursor/commands/` — 5 个命令快捷方式
- `.cursor/skills/` — 19 个 Skill

---

## 2. Claude Code

### 启动步骤

```bash
# 1. 安装 Claude Code
# 见 https://docs.claude.com/claude-code

# 2. 克隆项目
git clone https://github.com/csmar432/FinAI-Research-Workflow.git
cd FinAI-Research-Workflow

# 3. 安装依赖
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 4. 配置（首次）
python scripts/setup_wizard.py --guided
python scripts/health_check.py --json

# 5. 在 Claude Code 中打开
claude
```

### 在 Claude Code 中使用

Claude Code 会自动读取 `CLAUDE.md` 并执行自动启动流程（问候 + 诊断 + 询问研究方向）。直接描述研究主题：

```
我研究关税冲击对A股出口企业创新的影响
```

### 关键文件

- `CLAUDE.md` — 主入口（最完善：自动启动 + 8 步流程 + MCP 详细表格）
- `AGENTS.md` — 备用入口
- `.claude/commands/` — 4 个命令
- `.claude/skills/` → `knowledge/skills/`（symlink，17 个 Skill）

---

## 3. GitHub Copilot / Codex

### 启动步骤

```bash
# 1. 克隆项目
git clone https://github.com/csmar432/FinAI-Research-Workflow.git
cd FinAI-Research-Workflow

# 2. 安装依赖
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. 配置（首次）
python scripts/setup_wizard.py --guided
python scripts/health_check.py --json

# 4. 在 VS Code 中打开（含 GitHub Copilot Chat 扩展）
code .
```

### 在 Copilot / Codex 中使用

打开项目后，Copilot 会自动读取 `.github/copilot-instructions.md`。在 Copilot Chat 中输入研究主题：

```
@workspace 帮我研究数字金融对企业创新的影响
```

或使用 Copilot CLI：

```bash
gh copilot explain "scripts/agent_pipeline.py 怎么用"
```

### 关键文件

- `.github/copilot-instructions.md` — Copilot/Codex 入口
- `.github/skills/` → `knowledge/skills/`（symlink，17 个 Skill）
- `.github/workflows/` — CI 配置

---

## 4. 通用工作流（哪个工具都一样）

不论使用哪个工具，**8 步研究流程**一致：

| 步骤 | 入口命令 | 输出 |
|---|---|---|
| 0. 系统自检 | `python scripts/health_check.py --json` | 状态报告 |
| 1. 研究想法 | `python scripts/agent_pipeline.py --topic "..."` | `output/fin-ideas/IDEA_REPORT.md` |
| 1.5 想法-数据 | `python scripts/idea_data_checker.py --idea-file <path>` | 可行性报告 |
| 2. 文献综述 | `python scripts/literature_download.py --query "..."` | `output/fin-literature/` |
| 3. 新颖性验证 | `python scripts/agent_pipeline.py --topic "..." --novelty-check` | `output/fin-novelty/NOVELTY_REPORT.md` |
| 4. 实证设计 | `python scripts/research_framework/pipeline.py --mode design --topic "..."` | `output/fin-refinement/REFINED_DESIGN.md` |
| 5. 数据获取 | `python scripts/universal_data_fetcher.py fetch --data-type a_stock_financial --ts-code 000001.SZ` | CSV / Parquet |
| 6. 论文写作 | `python scripts/agent_pipeline.py --topic "..." --venue "经济研究"` | `output/fin-manuscript/` |
| 7. 对抗性 Review | `python scripts/core/llm_reviewer.py --draft paper.md --no-llm` | `output/fin-review/round_N/` |

---

## 5. Skills 速查

17 个 Skill 通过 `knowledge/skills/` 共享，三种工具都能用：

| Skill | 用途 |
|---|---|
| `fin-full-pipeline` | 完整端到端流水线 |
| `fin-idea-discovery` | 想法发现 + 数据验证 |
| `fin-lit-review` | 系统性文献综述 |
| `fin-generate-idea` | 8-12 个排序想法 |
| `fin-novelty-check` | 新颖性验证（JF/JFE/RFS 查重）|
| `fin-experiment-design` | 完整实证设计（DID/IV/RD/PSM）|
| `fin-paper-writing` | 论文写作编排 |
| `fin-paper-draft` | 正文生成（LaTeX）|
| `fin-paper-plan` | 大纲生成（41 种期刊模板）|
| `fin-paper-figure` | 图表生成（≥300 DPI，20+类型）|
| `fin-paper-convert` | LaTeX 编译 |
| `fin-review-loop` | 多轮对抗性 review |
| `fin-submit-check` | 投稿前检查 |
| `fin-data-acquisition` | MCP 数据获取 |
| `fin-brief-generator` | 生成 `FIN_BRIEF.md` |
| `fin-ref-paper` | BibTeX 参考文献管理 |
| `fin-viz-launch` | 自然语言 → 学术图表 |

---

## 6. 跨平台差异一览

| 功能 | Cursor | Claude Code | Copilot / Codex |
|---|---|---|---|
| 自动读取入口文件 | ✅ `.cursor/rules/` | ✅ `CLAUDE.md` | ✅ `.github/copilot-instructions.md` |
| Skill 触发 | `Skill: <name>` | 自然语言 | 自然语言 |
| Commands 快捷 | ✅ 5 个 | ✅ 4 个 | ❌（不支持 commands）|
| Agent 模式 | ✅ `literature-scout` | ✅ | ❌ |
| HITL 审批门 | ✅ `--use-hitl` | ✅ | ⚠️ 手动确认 |
| LangGraph 后端 | ✅ `--langgraph` | ✅ | ✅ |
| MCP 自动注册 | ✅ `register_mcp_servers.py` | ✅ | ✅ |
| **特性** | **图形化最佳** | **CLI 自动化最佳** | **VS Code 集成最佳** |

---

## 7. 故障排查

### 入口脚本报 `ModuleNotFoundError: No module named 'scripts'`

修法：项目已添加 `_bootstrap.py` 自动注入 `sys.path`。如果仍报此错误：

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

应该输出 `cursor` / `claude_code` / `vscode` / `generic` 之一。

### MCP 服务器没注册

```bash
python scripts/register_mcp_servers.py --list
python scripts/register_mcp_servers.py --profile academic
```

### 没有任何 AI 工具

所有功能都是纯 Python 脚本，无需 AI 工具即可使用：

```bash
python scripts/health_check.py --json
python scripts/research_framework/pipeline.py --mode design --topic "..."
python scripts/universal_data_fetcher.py diagnose
```

---

## 8. 推荐组合

| 场景 | 推荐工具 |
|---|---|
| 学术写作 + LaTeX 排版 | **Cursor**（图形化最好）|
| CI/CD 自动化 + 批量研究 | **Claude Code**（CLI 最强）|
| VS Code 重度用户 | **GitHub Copilot**（IDE 集成）|
| 离线/无 LLM 环境 | **纯 Python 脚本**（任何工具都不需要）|
