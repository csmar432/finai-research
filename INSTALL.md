# FinAI Research Workflow · 安装指南

> 本文档涵盖所有支持的安装方式、常见错误及解决方案。
> 快速上手请直接看 [README.md](README.md) 的 Quick Start 部分。

---

## 目录

1. [安装方式](#1-安装方式)
2. [虚拟环境](#2-虚拟环境)
3. [API Key 配置](#3-api-key-配置)
4. [MCP 服务器](#4-mcp-服务器)
5. [本地模型（可选）](#5-本地模型可选)
6. [常见问题](#6-常见问题)

---

## 1. 安装方式

### 方式 A：PyPI wheel（推荐普通用户）

```bash
# Debian/Ubuntu：先创建虚拟环境（避免 PEP 668 冲突）
python3 -m venv .venv && source .venv/bin/activate

# 安装核心功能（不含 fastapi/streamlit，不会触发 PyJWT/apt 冲突）
pip install "finai-research-workflow[extras]"

# 如需 Web UI（SSE Dashboard / Streamlit）：
pip install "finai-research-workflow[web]"

# 或一次性安装全部（含 extras + web）：
pip install "finai-research-workflow[extras,web]"
```

> **为什么 fastapi/streamlit 需要单独安装？**
> 这两个包会传递依赖 `PyJWT`，而 Debian/Ubuntu 用 apt 管理系统的 `python3-jwt`，
> 两者版本不兼容会触发 PEP 668 阻断错误。将它们拆分到 `[web]` extra 后，
> 默认安装不再拉 PyJWT，从根本上解决了"每次安装都要卸组件"的问题。

### 方式 B：源码克隆（推荐贡献者 / 需改代码的用户）

```bash
git clone https://github.com/csmar432/finai-research.git
cd finai-research
pip install -e ".[extras]"
```

---

## 2. 虚拟环境

**强烈建议始终使用虚拟环境**，避免污染系统 Python。

```bash
# 创建
python3 -m venv .venv

# 激活（Linux / macOS）
source .venv/bin/activate

# 激活（Windows PowerShell）
.\.venv\Scripts\Activate.ps1

# 验证
which python  # 应指向 .venv/bin/python
python --version  # 3.10 / 3.11 / 3.12 之一
```

> **为什么 Debian/Ubuntu 上直接 `pip install` 会失败？**
> 系统 Python 被 APT 管理，`pip install` 会触发 PEP 668 错误：
> "externally-managed-environment"。解决方案：使用虚拟环境（`venv`）
> 或 `pip install --break-system-packages`。

---

## 3. API Key 配置

核心功能只需要 `DEEPSEEK_API_KEY`（DeepSeek 直连，免费，额度充足）。

```bash
# 方式 1：在 .env 文件中（项目根目录）
echo "DEEPSEEK_API_KEY=sk-xxxx" >> .env

# 方式 2：在 .env.local 中（不会被 git 提交，推荐）
echo "DEEPSEEK_API_KEY=sk-xxxx" >> .env.local

# 方式 3：环境变量（适用于 CI / Docker）
export DEEPSEEK_API_KEY=sk-xxxx

# 验证配置（wheel 安装后）
finai-doctor
```

> **PyPI wheel 安装时 .env 应该放哪里？**
> wheel 模式下，`.env` 应该放在**你运行 `finai-pipeline` 的工作目录**（cwd）。
> 如果想放在项目目录，用 `FINAI_PROJECT_ROOT=/path/to/your/project finai-pipeline`。
> `finai-doctor` 会告诉你每个 key 的来源。

可选 API Key：

| Key | 用途 | 是否必需 |
|-----|------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek LLM（免费，直连） | **推荐配置** |
| `OPENAI_API_KEY` | OpenAI GPT-4 | 可选 |
| `ANTHROPIC_API_KEY` | Anthropic Claude | 可选 |
| `TUSHARE_TOKEN` | A 股财务/行情数据 | 可选（akshare 免费备选） |
| `FRED_API_KEY` | 美联储经济数据 | 可选 |
| `BRAVE_SEARCH_API_KEY` | 网络搜索 | 可选 |

---

## 4. MCP 服务器

43 个 MCP 服务器（28 个完全免费，无需 Key）：

```bash
# 自动注册所有 MCP 服务器到 Cursor
python scripts/register_mcp_servers.py

# 查看注册状态
python scripts/register_mcp_servers.py --list
```

免费数据源（无需配置）：

- **A股/宏观**：`user-financial`（akshare）
- **美股/ETF**：`user-yfinance`
- **SEC 年报**：`user-sec-edgar`
- **学术论文**：`user-openalex` / `user-arxiv` / `user-context7`
- **全球宏观**：`user-wb-data` / `user-imf-data` / `user-oecd-data`

付费数据源（按需配置，pipelines 会给出非阻断提示）：

- `user-tushare`（需 Tushare Pro Token，年费约 600-2000 元）
- `user-wind`（需 Wind 账号，机构付费）

---

## 5. 本地模型（可选）

不需要 OpenAI/DeepSeek Key，用 Ollama 本地模型：

```bash
# 安装 Ollama
brew install ollama      # macOS
# 或参考 https://ollama.ai

# 下载模型
ollama pull deepseek-coder

# 启动服务
ollama serve

# pipeline 会自动检测 Ollama 并使用
```

---

## 6. 常见问题

### Q: pip install 报错 "externally-managed-environment"

**原因**：Debian/Ubuntu 的系统 Python 不允许直接 pip install。

**解决**：使用虚拟环境：
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "finai-research-workflow[extras]"
```

### Q: pip install 报错 "python3-jwt conflicts"

**原因**：系统上已有 apt 的 `python3-jwt`，pip 安装 fastapi 时传递依赖 PyJWT 版本冲突。

**解决**：用 `pip install finai-research-workflow[extras]` 不含 fastapi，或使用虚拟环境。

### Q: 找不到 .env，pipeline 报 "未配置 LLM"

**原因**：wheel 安装后 `.env` 没有放在工作目录。

**解决**：
```bash
# 检查配置
finai-doctor

# 或直接设置环境变量
export DEEPSEEK_API_KEY=sk-xxxx
```

### Q: finai-pipeline 退出码 4

**原因**：`--strict-llm`（默认开启）检测到未配置 LLM，直接退出而非静默降级。

**解决**：配置 `DEEPSEEK_API_KEY` 或加 `--no-strict-llm` 临时绕过。

### Q: macOS 上 Python 3.13 找不到命令

**原因**：Python 3.13 可能未在 PATH 中。

**解决**：
```bash
# 用完整路径或 homebrew 路径
/opt/homebrew/bin/python3
# 或
python3.12
```
