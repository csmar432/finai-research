# 贡献指南

感谢您对 经济类科研智能体工作流 的兴趣！

## 如何贡献

### 报告问题

- 使用 GitHub Issues 报告 Bug 或功能请求
- 描述问题时包含：Python 版本、环境信息、复现步骤
- 安全问题请私下联系，不要在 Issue 中公开

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature-name`
3. 编写代码并确保测试通过：`pytest tests/` 或 `finai test`
4. 提交：`git commit -m "feat: add something useful"`
5. 推送到您的 Fork：`git push origin feature/your-feature-name`
6. 发起 Pull Request

### 代码规范

- 遵循 PEP 8，使用 `ruff check scripts/` 检查
- 所有新增功能必须有对应的测试
- 提交前运行完整测试：`pytest tests/` 或 `finai test`

### 测试要求

```bash
# 运行所有测试
pytest tests/

# 或通过 CLI（支持 --cov, --exitfirst, -k 过滤）
finai test --cov

# 运行单个模块测试
.venv/bin/python -m pytest tests/test_llm_reviewer.py -v
.venv/bin/python -m pytest tests/test_modern_did.py -v
.venv/bin/python -m pytest tests/test_checkpoint.py -v
.venv/bin/python -m pytest tests/test_event_monitor.py -v
```

## 模块说明

| 目录 | 说明 |
|------|------|
| `scripts/core/` | 核心智能体模块（Memory/Planner/ToolSelector/Reflection） |
| `scripts/` | 工具脚本（数据处理/文献管理/论文写作） |
| `scripts/research_framework/` | 研究执行层（48 个计量/可视化模块） |
| `config/` | 配置文件模板 |
| `knowledge/skills/` | 17 个 AI 技能文档（文献综述/想法生成/实证设计/论文写作等） |
| `templates/` | LaTeX/Word 输出模板 |
| `docs/` | 架构文档和实施计划 |

## 决策流程

重大变更（改变核心架构、新增主要模块）请先开 Discussion 讨论。

---

## 添加新的 MCP Server（详细指南）

我们欢迎社区贡献新的 MCP 数据源。流程如下：

### 1. 创建服务器目录

```bash
mkdir mcp_servers/user_your_server
cd mcp_servers/user_your_server
```

所有 MCP server 目录都以 `user_` 前缀命名，与上游官方 MCP server 区分。

### 2. 实现 server.py

最小可工作示例（参考 `mcp_servers/user_tushare/server.py`）：

```python
"""Your Data Source MCP Server.

短描述: 1 行
来源: 官方 API 或 数据集
"""
from mcp.server import Server
from mcp.types import TextContent, Tool
import os

app = Server("user_your_server")

@app.tool()
async def get_your_data(symbol: str) -> list[TextContent]:
    """获取 your_data 数据.

    Args:
        symbol: 数据标识符
    """
    api_key = os.environ.get("YOUR_API_KEY")
    # 调用 API 并返回结果
    return [TextContent(type="text", text=f"Data for {symbol}")]

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server
    asyncio.run(stdio_server(app))
```

### 3. 创建 Dockerfile

参考 `mcp_servers/user_tushare/Dockerfile`：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Security: non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY --chown=mcpuser:mcpuser requirements.txt server.py ./
RUN pip install --no-cache-dir -r requirements.txt

USER mcpuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:8000/health || exit 1

LABEL org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow"
LABEL org.opencontainers.image.description="Your Data Source MCP Server"
LABEL org.opencontainers.image.licenses="MIT"

CMD ["python", "server.py"]
```

### 4. 创建 requirements.txt

```
mcp>=1.1.0
requests>=2.31.0
# your-data-source-sdk
```

### 5. 添加测试

创建 `tests/test_your_server.py`：

```python
import pytest
from mcp_servers.user_your_server.server import get_your_data

@pytest.mark.asyncio
async def test_get_your_data():
    result = await get_your_data("TEST")
    assert len(result) > 0
    assert "TEST" in result[0].text
```

### 6. 更新文档

在 `README.md` 顶部 Quick Navigation 的 "MCP data sources" 章节
加一行（43 → 44），并在 `docs/external_data_sources.md` 添加服务器说明。

### 7. 提交 PR

```bash
git checkout -b feature/user-your-server
git add mcp_servers/user_your_server/ tests/test_your_server.py
git commit -m "feat(mcp): add user_your_server for [data domain]"
git push origin feature/user-your-server
# 在 GitHub 上发 PR
```

### MCP 设计原则

- ✅ **数据源独立** — 每个 MCP server 是独立的 Python 进程
- ✅ **4 层 fallback** — `data_fetcher.py` 会按 Tier 1 (CSMAR/Wind) → Tier 2 (Tushare) → Tier 3 (akshare) → Tier 4 (yfinance/synthetic) 降级
- ✅ **Graceful degradation** — 无 API key 时返回 `None` 而非崩溃
- ✅ **Cache** — 本地 SQLite 缓存 7 天
- ✅ **Provenance** — 记录 source + timestamp + commit hash

---

## 添加新的 Econometric Method

参考 `scripts/research_framework/` 下的现有模块（如 `modern_did.py`）：

1. 创建一个 `xxx_method.py`，**类设计**清晰（输入 → 输出 dataclass）
2. 添加 `tests/test_xxx_method.py`，**至少 20 个单元测试** + 1 个集成测试
3. 在 `scripts/research_framework/__init__.py` 导出
4. 更新 `README.md` "42 econometric methods" 计数
5. 添加一个 `docs/methods/xxx_method.md` 用户文档

### 方法质量标准

- [ ] 接受 `pandas.DataFrame` 输入（与现有生态兼容）
- [ ] 返回 dataclass（不是 tuple/dict）
- [ ] 支持 `cluster-robust SE` 至少 1 种
- [ ] 支持 bootstrap inference 至少 1 种
- [ ] 引用至少 1 篇学术论文（论文必须真实存在）
- [ ] 至少 1 个端到端 example

---

## 添加新的 AI Skill

参考 `knowledge/skills/fin-paper-draft/SKILL.md` 的结构：

1. 创建 `knowledge/skills/fin-your-skill/SKILL.md`
2. 顶部必须有 YAML frontmatter (name + description)
3. 中间是 "When to use" 段落（具体触发场景）
4. 然后是 "Inputs" / "Outputs" 段
5. 最后是 "Example" 段（真实使用场景）
6. 在 `CLAUDE.md` "Available Skills" 表格中加一行

---

## 添加新的 Journal Template

参考 `scripts/research_framework/journal_template.py`：

1. 在 `_TEMPLATES` 字典加新条目
2. 提供 4 个函数：`get_template()`, `compile_to_pdf()`, `validate_submission()`, `cover_letter()`
3. 在 `scripts/journal_template.py --list` 输出中验证出现
4. 在 `README.md` "45 journal templates" 段落加一行
5. 添加测试到 `tests/test_journal_template.py`

---

## 添加新的 Knowledge Skill（Cursor 专用）

Cursor 的 skills 在 `.cursor/skills/`:

1. 创建 `.cursor/skills/fin-your-skill/SKILL.md`
2. 同 `knowledge/skills/` 的规范
3. **加同步脚本**：`scripts/sync_cursor_skills.py` 把 `knowledge/skills/` 复制到 `.cursor/skills/`

---

## 维护者审查清单

Maintainer 在合并前会检查：

- [ ] 代码通过 `ruff check scripts/ tests/`
- [ ] 测试通过 `pytest tests/ -v`
- [ ] 文档已更新（README / 使用指南 / docs/）
- [ ] CHANGELOG.md 加 Unreleased 段
- [ ] 没有真实身份信息泄露（邮箱、姓名、本地路径）
- [ ] 没有 git 元数据泄露（PAT、私人 repo URL）

---

## 行为准则

- 尊重他人，提供建设性反馈
- 聚焦技术讨论，避免人身攻击
- 帮助新人 — 这是开源社区的核心

---

## 联系方式

- 🐛 **Bug / Feature**: GitHub Issues
- 💬 **讨论 / 问题**: GitHub Discussions
- 🔒 **安全问题**: GitHub Security Advisories
- 📧 **核心维护者**: 见 `MAINTAINERS.md`（如有）
