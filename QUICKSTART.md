# 快速开始

## 只需 3 步，立刻用起来

### 环境准备（重要！先看这一步）

**强烈建议使用虚拟环境**，否则 Debian/Ubuntu 会报 PEP 668 冲突：

```bash
# 创建虚拟环境（只要做一次）
python3 -m venv .venv && source .venv/bin/activate

# 确认环境激活
which python  # 应指向 .venv/bin/python

# 安装（wheel 安装推荐）
pip install "finai-research-workflow[extras]"
```

> **为什么不直接 pip install？**
> Debian/Ubuntu 用 apt 管理系统的 Python，直接 pip install 会触发
> "externally-managed-environment" 错误。使用虚拟环境即可解决。

### 第一步：在 Cursor 里说话

所有功能通过自然语言触发，不需要记命令。

### 第二步：配置 API Key（仅脚本批处理需要，Cursor 对话无需配置）

Keys 放在项目根目录 `.env`（已在 .gitignore）：

```bash
DEEPSEEK_API_KEY=sk-xxx    # DeepSeek 直连（无需 VPN）：中文写作/代码/分析，速度快
RELAY_API_KEY=xxx          # B.AI 中转：GPT/Claude 模型，英文写作/翻译质量最佳
FRED_API_KEY=xxx           # FRED 宏观数据（免费）
ALPHA_VANTAGE_API_KEY=xxx  # 美股技术指标（免费额度 25次/天）
TIINGO_API_KEY=xxx         # 美股基本面数据
```

> Cursor 直接对话使用本地 Claude，无需任何 Key 配置。

### 第三步：直接开口

---

## 场景一：写论文（一步完成）

```
"帮我设计一篇深度学习量化交易论文的大纲，目标 NeurIPS"
"写一篇完整论文"
"润色这篇论文的英文"
```

脚本对应：`scripts/agent_pipeline.py` 或直接用 AI Agent 自然语言交互

> 推荐直接用 AI Agent，只需描述研究方向即可。

---

## 场景二：金融分析（A股+美股）

```
"获取茅台近一年的日线数据"
"分析苹果 AAPL 的财务数据"
"用 Finviz 筛选 PE<30 的科技股"
```

MCP 对应：`user-tushare`（A股）+ `user-yfinance`（美股）+ `user-financial`（中国宏观）

---

## 场景三：文献研究

```
"检索近三年 arXiv 上深度学习量化交易方向的论文"
"帮我下载并总结这篇论文的核心贡献"
```

MCP 对应：`user-arxiv` + `fetch`

---

## AI 模型 — 自动寻优 + 手动指定

系统内置 AI Router，**只需配置 Key，系统自动选最优模型**（中文→DeepSeek，英文→GPT/Claude）。

### 自动寻优（默认）

| 任务类型 | 首选模型 | 备选模型 |
|---------|---------|---------|
| 中文研究/论文 | DeepSeek V4 Flash（直连） | GPT-5.4-Mini（B.AI） |
| 英文写作/翻译 | GPT-5.4-Mini / Claude Sonnet 4.6（B.AI） | DeepSeek V4 Flash |
| 深度推理 | Claude Opus 4.7（B.AI） | DeepSeek V4 Pro |
| 数学/推理 | DeepSeek R1（直连） | Claude Opus 4.7 |
| 备选兜底 | Ollama 本地模型（需自行部署） | — |

### 手动指定（可选）

```python
from scripts.ai_router import AIRouter
router = AIRouter()
router.chat("任务", model="deepseek")       # 强制 DeepSeek
router.chat("任务", model="gpt5")           # 强制 GPT-5.4-Mini
router.chat("任务", model="claude-sonnet")  # 强制 Claude Sonnet
router.chat("任务", model="claude-opus")    # 强制 Claude Opus
```

### B.AI Relay 实测模型（2026-05-29）

| 模型 | 状态 |
|------|------|
| `gpt-5.4-mini` | ✅ 可用 |
| `claude-sonnet-4.6` | ✅ 可用 |
| `claude-opus-4.7` | ✅ 可用 |
| `deepseek-v4-flash` / `deepseek-v4-pro` | ✅ 可用 |
| `glm-5.1` / `kimi-k2.5` | ✅ 可用 |
| `gemini-*` 系列 | ❌ 返回空内容，暂不支持 |

中转 API 支持任何兼容 OpenAI 格式的服务（B.AI / Groq / OpenRouter 等），只需修改 `.env` 中的 `RELAY_BASE_URL`。

---

## MCP 工具速查

| 你说什么 | MCP 工具 |
|---------|----------|
| "搜索财经新闻" | `brave-search` |
| "获取某只股票数据" | `user-tushare` / `user-yfinance` / `user-financial` |
| "检索 arXiv 论文" | `arxiv` |
| "抓取这个网页内容" | `fetch` |
| "查询官方 API 文档" | `context7` |
| "用 SQL 分析数据" | `sqlite` |
| "创建任务清单" | `todo` |
| "记住我的研究背景" | `memory` |
| "管理 GitHub 仓库" | `github` |

---

## 常见问题

**Q: 每次都要粘贴角色提示吗？**
A: 不需要。Cursor 的规则（`.cursor/rules/`）已保存角色设定。

**Q: 如何获取 A股数据？**
A: 直接在 Cursor 中描述需求，例如 `"获取茅台2024年的日线数据"`，AI Agent 会自动调用 `user-tushare` MCP 获取真实数据。

**Q: 如何更换中转 API 厂商？**
A: 修改 `.env` 中的 `RELAY_BASE_URL`，可以是 B.AI、Groq、OpenRouter 等任何兼容 OpenAI 格式的服务。
