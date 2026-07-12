# fin-lit-review — 系统性文献综述

对经济金融研究领域进行系统性文献综述，整合多个学术数据库构建引文网络，识别研究缺口。

## 功能

1. **多源学术搜索**（按可用性）：
   - NBER Working Papers（免费，无需 Key）
   - Brave Search（网络搜索，需 BRAVE_SEARCH_API_KEY）
   - OpenAlex（学术元数据，免费）
   - 本地引文图谱脚本

2. **引文网络构建**
   - `scripts/citation_graph.py` — 构建引用关系图
   - 识别高影响力论文和新兴方向

3. **文献筛选**
   - 按期刊级别过滤（Top 5 / Top 10 / 中文顶刊）
   - 按引用量排序
   - 按发表年份过滤

## 输出

| 文件 | 说明 |
|------|------|
| `output/fin-literature/LIT_REVIEW.md` | 完整文献综述 |
| `output/fin-literature/LIT_SUMMARY.md` | 精简版（3页）|
| `output/fin-literature/CITATION_GRAPH.json` | 引文网络图 |

## 调用方式

```
"帮我综述一下关税对中国宏观经济影响的研究文献"
"做一下绿色金融和ESG研究的文献地图"
"综述一下中美贸易战对企业出口影响的相关文献"
```

## 关键脚本

- `scripts/citation_graph.py` — 引文网络构建
- `scripts/literature_download.py` — 论文批量下载（支持 OpenAlex/NBER）
- MCP 工具：`user-nber-wp`（NBER Working Papers）、`user-openalex`（学术元数据）
- WebSearch：`user-brave-search`（需 BRAVE_SEARCH_API_KEY，已在 .env.local 中配置）

## 调用方式（Claude Code / 其他 AI 工具）

直接用自然语言描述需求，AI 会自动编排各阶段：

```
"帮我从零开始研究碳排放权交易对企业绿色创新的影响，发表在经济研究"
```

## 内部模块

| 模块 | 功能 |
|------|------|
| `scripts/agent_pipeline.py` | 主编排器 |
| `scripts/research_framework/pipeline.py` | 研究执行层 |
| `scripts/research_framework/modern_did.py` | 现代 DID |
| `scripts/research_framework/regression_engine.py` | 回归引擎 |

## 行为控制

- 每阶段结束后暂停，等待确认
- 可通过 `FIN_BRIEF.md` 中的 `AUTO_PROCEED: true` 跳过确认
- Review 难度可选：`REVIEWER_DIFFICULTY: standard|strict|nightmare`
