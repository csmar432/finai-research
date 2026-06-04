# 快速入门（5分钟）

> 本教程帮助你快速配置并运行第一个研究流程。

---

## 前置条件

- **Python 3.11+**（推荐 Python 3.12）
- **API Key 配置**：在 `.env` 中配置至少一个 LLM API key

### 必需的环境变量

在项目根目录创建 `.env` 文件：

```bash
# DeepSeek（推荐，中文研究首选）
DEEPSEEK_API_KEY=sk-你的DeepSeekKey

# 或 Relay 中转（支持 GPT/Claude）
RELAY_API_KEY=你的RelayKey
```

---

## 安装依赖

```bash
# 在项目根目录下执行
cd .

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -e .           # 推荐方式（支持 entry points）
# 或安装开发依赖：
pip install -e ".[dev]"    # 包含 pytest, ruff, jupyter
# 或安装全量依赖：
pip install -e ".[all]"    # 包含 RAG/深度学习/沙箱等所有可选功能
```

> **提示**：如果安装失败，尝试 `pip install --upgrade pip` 后重试。

---

## 运行第一个研究流程

### 完整论文生成

```bash
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"
```

预期行为：
1. 系统自动检索相关文献
2. 生成研究大纲
3. 获取数据并运行实证分析
4. 生成 LaTeX 论文草稿
5. 输出到 `papers/` 目录

### 查看帮助

```bash
python scripts/agent_pipeline.py --help
```

---

## 使用 Cursor Agent（推荐方式）

最简单的方式是直接在 Cursor 对话框中用自然语言描述你的研究需求：

```
帮我分析碳排放权交易对企业绿色创新的影响，设计一篇实证论文
```

Cursor Agent 会自动调用所有必要的模块完成研究任务。

---

## 目录结构

```
论文-研报工作流/
├── papers/          ← 论文输出目录
├── data/           ← 数据输入目录
├── scripts/        ← 核心脚本
│   ├── core/       ← 智能体核心模块
│   └── research_framework/  ← 研究框架
├── mcp_servers/    ← MCP 数据工具
└── knowledge/      ← 知识库
```

---

## 常见问题

### 1. API Key 未设置

**错误**：`KeyError: 'DEEPSEEK_API_KEY'`

**解决**：确保在 `.env` 文件中正确配置了 API key：

```bash
DEEPSEEK_API_KEY=sk-你的真实Key值
```

### 2. MCP 工具不可用

**错误**：`MCP tool unavailable`

**解决**：在 Cursor 设置中检查 MCP 服务器是否已启用。也可以直接用脚本层获取数据：

```python
from scripts.core.analyst_agents import TushareDataAgent

agent = TushareDataAgent(default_ts_code="000001.SZ")
data = agent.get_daily_quote(ts_code="000001.SZ")
# 或使用研报演示脚本获取模拟数据：
# python scripts/demo_research_report.py --stock 000001.SZ --output papers
```

### 3. 虚拟环境问题

**错误**：`Module not found`

**解决**：确保已激活虚拟环境：

```bash
source .venv/bin/activate
```

### 4. LaTeX 编译失败

**解决**：安装 TeX Live（macOS 可用 Homebrew）：

```bash
brew install --cask mactex  # macOS
```

---

## 下一步

- [Tutorial 2: 金融研究报告写作](02-financial-report.md)
- [Tutorial 4: MCP 工具市场](04-mcp-marketplace.md)
- [API 参考文档](../api_reference.md)
