# research — 启动完整研究流程

description: 启动经济金融领域的完整研究流水线（从文献综述到论文草稿）

# arguments

- `<topic>`: 研究主题（中文或英文均可）

# 描述

启动论文-研报工作流的完整端到端研究流程。

等价于：

```bash
python scripts/agent.py --goal "<topic>"
```

或直接用 AI Agent 自然语言交互：

```
"帮我研究 [你的研究方向]，发表在经济研究"
```

# 示例

```
/research 关税政策对A股出口型企业创新的影响
/research carbon trading innovation Chinese A-shares
/research ESG and cost of capital
```

# 工作流程

1. 文献综述 — arXiv / NBER / OpenAlex 搜索
2. 研究想法生成 — 8-12 个候选想法，数据验证
3. 实证设计 — DID / IV / RDD / PSM 识别策略
4. 数据获取 — `{{MCP_COUNT}}` 个 MCP 服务器自动拉取
5. 回归分析 — 38+ 种计量方法
6. 论文写作 — LaTeX 输出（JF / JFE / RFS / 经济研究）
7. 对抗性 review — 多轮迭代直到发表标准

# 环境要求

- Python 3.10+
- 大部分 MCP 服务器无需 API Key
- LaTeX（xelatex，用于中文期刊）
