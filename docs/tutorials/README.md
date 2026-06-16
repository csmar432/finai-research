# Tutorials · 教程

> 从零开始掌握「论文-研报工作流」的完整使用路径。

> **📌 Language note / 语言说明**
>
> 教程采用"**中文优先**"策略：
> - **Tutorial 1 (快速入门)**: 全中文，是新手必读
> - **Tutorial 2-5**: 主体英文（因示例代码含较多英文 API/库名，中英混杂影响可读性）
>
> 如需中文版本，请参考 [`使用指南.md`](../../使用指南.md) 的对应章节。如发现翻译错误或希望贡献中文版本，欢迎提 PR。
>
> Tutorials adopt a "**Chinese-first**" policy:
> - **Tutorial 1 (Quickstart)**: Chinese only — required reading for new users
> - **Tutorials 2-5**: English-dominant (because example code contains many English APIs; mixed CN/EN hurts readability)
>
> For Chinese versions, see [`使用指南.md`](../../使用指南.md). PRs welcome for any translation improvements.

---

## 教程目录

| # | 教程 | 内容 | 预计时长 |
|---|------|------|---------|
| 1 | [快速入门](01-quickstart.md) | 5分钟配置 + 运行第一个研究流程 | 5 分钟 |
| 2 | [金融研究报告](02-financial-report.md) | 使用脚本生成研报 + 数据获取 | 15 分钟 |
| 3 | [研究方向设计](03-research-directions.md) | 发现研究想法 + 数据验证 | 20 分钟 |
| 4 | [MCP 工具市场](04-mcp-marketplace.md) | 41个数据服务器的安装与使用 | 30 分钟 |
| 5 | [事件驱动研究](05-event-driven-research.md) | 宏观事件监控 + 自动触发研究 | 30 分钟 |

---

## 推荐学习路径

### 路径 A：快速体验（30 分钟）

```
1. 快速入门        → 配置环境，运行演示流程
2. 金融研究报告    → 生成一份研报
3. MCP 工具市场    → 了解可用的数据源
```

### 路径 B：完整研究流程（2 小时）

```
1. 快速入门        → 配置环境
2. 研究方向设计    → 发现研究想法
3. MCP 工具市场    → 配置所需数据源
4. 事件驱动研究    → 掌握自动化研究能力
```

---

## 前置条件

所有教程的前置条件相同：

- Python 3.11+
- `.env` 中配置至少一个 LLM API Key
- 按[快速入门](01-quickstart.md)完成依赖安装

---

## 快速参考

| 操作 | 命令 |
|------|------|
| 健康检查 | `python scripts/health_check.py` |
| 运行研报 | `python scripts/demo_research_report.py` |
| 运行测试 | `python -m pytest tests/ -q` |
| MCP 诊断 | `python scripts/mcp_diagnostic.py` |
| 查看帮助 | `python scripts/agent_pipeline.py --help` |

---

## 故障排查

遇到问题时：

1. 查看 [FAQ.md](../../FAQ.md)（30 个常见问题）
2. 运行 `python scripts/health_check.py --verify` 获取详细诊断
3. 检查 [.env.example](../../.env.example) 确认 API Key 配置
