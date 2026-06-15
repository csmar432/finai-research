# Examples · 可运行示例

本目录包含**独立可运行**的示例，展示项目核心能力。

| # | 示例 | 内容 | 难度 |
|---|---|---|---|
| 1 | [01-quickstart-pipeline.py](01-quickstart-pipeline.py) | 5 行代码跑完整研究流水线 | ⭐ |
| 2 | [02-did-analysis.py](02-did-analysis.py) | Callaway-Sant'Anna DID 实证 | ⭐⭐ |
| 3 | [03-paper-latex.py](03-paper-latex.py) | 自动生成可投稿 LaTeX 论文 | ⭐⭐ |
| 4 | [04-mcp-data-fetch.py](04-mcp-data-fetch.py) | 从 49 MCP 服务器拉取数据 | ⭐ |
| 5 | [05-charts-figures.py](05-charts-figures.py) | 20+ 种学术金融图表 | ⭐ |

## 🚀 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置 API Key
cp .env.example .env
# 填入 DEEPSEEK_API_KEY（必需）

# 3. 运行任一示例
python examples/01-quickstart-pipeline.py
```

## 📊 输出位置

所有示例的输出（论文、图表、数据）保存到 `output/examples/` 目录。

## 🔧 自定义

每个示例都是**可修改的起点**。在示例代码顶部修改配置，然后：

```bash
python examples/<name>.py
```

## 📚 详细文档

- 使用指南: [使用指南.md](../使用指南.md)
- API 参考: [docs/api_reference.md](../docs/api_reference.md)
- 技能文档: [knowledge/skills/](../knowledge/skills/)
