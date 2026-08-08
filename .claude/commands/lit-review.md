# lit-review — 系统性文献综述

description: 对指定研究主题进行系统性文献综述，构建引文网络

# arguments

- `<topic>`: 研究主题（中文或英文均可）

# 描述

运行文献综述流水线，使用 MCP 工具搜索学术论文并构建引文网络。

等价于：

```bash
python scripts/literature_download.py "<topic>" --source arxiv,semantic,openalex --limit 25
# or Skill: fin-lit-review
```

# MCP 数据源

| 数据源 | 覆盖范围 |
|--------|----------|
| `user-arxiv` | cs.AI / cs.LG / q-fin.GN |
| `user-nber-wp` | NBER Working Papers |
| `user-semantic-scholar` | 2亿+学术论文 |
| `user-openalex` | 学术引用图谱 |
| `user-brave-search` | 中文期刊（经济研究/金融研究）|

# 输出

- `output/fin-literature/LIT_REVIEW.md` — 结构化文献综述
- `output/fin-literature/CITATION_GRAPH.json` — 引文网络图
