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
3. 编写代码并确保测试通过：`python scripts/agent.py --test`
4. 提交：`git commit -m "feat: add something useful"`
5. 推送到您的 Fork：`git push origin feature/your-feature-name`
6. 发起 Pull Request

### 代码规范

- 遵循 PEP 8，使用 `ruff check scripts/` 检查
- 所有新增功能必须有对应的测试
- 提交前运行完整测试：`python scripts/agent.py --test`

### 测试要求

```bash
# 运行所有测试
python scripts/agent.py --test

# 运行单个模块测试
.venv/bin/python -m pytest scripts/core/test_memory.py -v
.venv/bin/python -m pytest scripts/core/test_planner.py -v
.venv/bin/python -m pytest scripts/core/test_tool_selector.py -v
.venv/bin/python -m pytest scripts/core/test_reflector.py -v
.venv/bin/python -m pytest scripts/core/test_session.py -v
```

## 模块说明

| 目录 | 说明 |
|------|------|
| `scripts/core/` | 核心智能体模块（Memory/Planner/ToolSelector/Reflection） |
| `scripts/` | 工具脚本（数据处理/文献管理/论文写作） |
| `config/` | 配置文件模板 |
| `prompts/` | 提示词模板 |
| `templates/` | LaTeX/Word 输出模板 |
| `docs/` | 架构文档和实施计划 |

## 决策流程

重大变更（改变核心架构、新增主要模块）请先开 Discussion 讨论。
