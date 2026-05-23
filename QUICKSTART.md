# 快速开始

## 只需 3 步，立刻用起来

### 第一步：在 Cursor 里说话

所有功能通过自然语言触发，不需要记命令。

### 第二步：配置 API Key（仅脚本批处理需要，Cursor 对话无需配置）

Keys 放在项目根目录 `.env.local`（已在 .gitignore）：

```bash
B_AI_API_KEY=sk-xxx        # B.AI 中转（需 VPN）
DEEPSEEK_API_KEY=sk-xxx    # DeepSeek 直连（无需 VPN）
FRED_API_KEY=xxx            # FRED 宏观数据（免费）
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

脚本对应：`scripts/paper_write.py` + `scripts/paper_submit.py`

---

## 场景二：金融分析（A股+美股）

```
"获取茅台近一年的日线数据"
"分析苹果 AAPL 的财务数据"
"用 Finviz 筛选 PE<30 的科技股"
```

MCP 对应：`financial-mcp`（yfinance） + `akshare`（`scripts/data_pipeline.py`）

---

## 场景三：文献研究

```
"检索近三年 arXiv 上深度学习量化交易方向的论文"
"帮我下载并总结这篇论文的核心贡献"
```

MCP 对应：`arxiv-mcp` + `fetch-mcp`

---

## AI 角色定位（以 Cursor Claude 为核心）

| 调用方式 | AI 模型 | 用途 |
|---|---|---|
| Cursor 直接对话 | Claude（本地） | 所有日常任务（默认） |
| 脚本批处理 | B.AI gpt-5.5（需VPN） | 批量情感/摘要/代码 |
| 脚本批处理 | DeepSeek（直连，无需VPN） | 中文写作/简单问答 |

---

## MCP 工具速查

| 你说什么 | MCP 工具 |
|---------|----------|
| "搜索财经新闻" | `brave-search` |
| "获取某只股票数据" | `financial` / `finviz-sec` |
| "检索 arXiv 论文" | `arxiv` |
| "抓取这个网页内容" | `fetch` |
| "查询官方 API 文档" | `context7` |
| "用 SQL 分析数据" | `sqlite` |
| "创建任务清单" | `todo` |
| "记住我的研究背景" | `memory` |
| "管理 GitHub 仓库" | `github` |

---

## 新增功能说明（本次更新）

### 1. A股数据支持（akshare）
无需 API Key，直接获取 A股日线、财务报表、指数、板块数据：
```python
from scripts.data_pipeline import fetch_a_stock, add_return_features
df = fetch_a_stock("000001.SZ", "2024-01-01", "2025-01-01")
df = add_return_features(df)
```

### 2. 多模型路由（已激活）
DeepSeek + Claude 协同工作，不再全部走 DeepSeek。英文润色/代码生成自动路由到 Claude。

### 3. 论文脚本合并
原来 9 个论文脚本 → 合并为 2 个：
- `paper_write.py` — 选题→大纲→章节→全文
- `paper_submit.py` — 润色→查重→格式检查→投稿信

---

## 常见问题

**Q: 每次都要粘贴角色提示吗？**
A: 不需要。Cursor 的规则（`.cursor/rules/`）已保存角色设定。

**Q: 如何获取 A股数据？**
A: `python scripts/data_pipeline.py` 直接运行，输入数字 1 即获取演示数据。
