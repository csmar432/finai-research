---
name: fin-lit-review
description: 经济金融领域的系统性文献综述。整合 Semantic Scholar + ArXiv + OpenAlex + NBER 构建引文网络，识别研究缺口，生成结构化文献地图。
argument-hint: [研究主题或PICO关键词]
---

# 经济金融系统性文献综述

整合多源学术数据库，构建引文网络，识别研究缺口。

## 核心功能

- **多源并行检索**：OpenAlex / ArXiv / NBER / 百度学术
- **PRISMA 筛选流程**：Inclusion/Exclusion 标准透明
- **引文网络构建**：NetworkX 有向图，可视化知识结构
- **研究缺口识别**：LLM 分析 + 人工标注
- **结构化输出**：LIT_REVIEW.md / LIT_SUMMARY.md / CITATION_GRAPH.json

## 工作流程

### Step 1: PICO 解析

将研究问题拆解为 PICO 四要素：

```
P (Population): 研究对象 — 企业/投资者/银行/政府
I (Intervention): 处理变量 — 政策/工具/事件
C (Comparator): 对照组 — 处理前/未受政策影响
O (Outcome): 结果变量 — 创新/绩效/风险/效率
```

示例输入：`"碳排放权交易对企业绿色创新的影响"`
→ PICO: P=制造业企业, I=碳排放权交易试点, C=非试点企业, O=绿色专利/研发投入

### Step 2: 多源并行检索

使用以下 MCP 工具并行搜索：

#### OpenAlex（优先，推荐 50 篇）

```python
server: user-openalex
tool: get_openalex_works
params: {
    "query": "carbon trading OR carbon emission trading green innovation",
    "per_page": 50,
    "sort": "citation_count"
}
```

#### ArXiv（预印本，最新方法）

```python
server: user-arxiv
tool: semantic_search
params: {
    "query": "carbon trading innovation policy effect DID",
    "max_results": 30
}
```

#### NBER（工作论文，高质量）

```python
server: user-nber-wp
tool: get_nber_papers
params: {
    "category": "corporate finance OR environmental economics",
    "year_from": 2021
}
```

#### 中文文献（百度学术 + CNKI）

```python
server: user-brave-search
tool: brave_web_search
params: {
    "query": "碳排放权交易 绿色创新 DID 双重差分 经济研究"
}
```

#### 研报补充（东方财富）

```python
server: user-eastmoney-reports
tool: get_stock_news
params: {
    "ts_code": "000001.SZ",
    "limit": 20
}
# 用于补充行业背景，不作为核心文献
```

### Step 3: PRISMA 筛选

对检索到的所有文献应用筛选标准：

```
Inclusion Criteria:
✓ 实证研究（排除纯理论/综述）
✓ 经济金融领域（或跨学科应用）
✓ 英文/中文全文可获取
✓ 2000年后发表

Exclusion Criteria:
✗ 纯工程/技术类研究（非金融视角）
✗ 无DOI/无法溯源
✗ 样本量<100 或 方法严重缺陷
✗ 与研究问题无关
```

**Checkpoint**：筛选完成后，向用户展示筛选数量统计：

```markdown
## PRISMA 筛选结果

- 检索总数: [N]
- 去重后: [N]
- 标题/摘要筛选排除: [N]
- 全文筛选排除: [N]
- 最终纳入: [N]

是否继续生成文献综述？
 [1] 继续
 [2] 调整筛选标准
 [3] 补充更多文献
```

### Step 4: 引文网络构建

使用 `scripts/citation_graph.py` 构建知识图谱：

```python
from scripts.citation_graph import CitationGraphBuilder

builder = CitationGraphBuilder()
graph = builder.build(papers)  # papers: list of dict with title/doi/cite_count

# 提取高影响力文献
influential = builder.get_influential_papers(top_n=20)

# 提取引文聚类（研究主题簇）
clusters = builder.get_citation_clusters()

# 导出 JSON
graph_json = builder.to_json()
```

输出结构：

```json
{
  "nodes": [
    {"id": "doi", "title": "...", "year": 2023, "journal": "JFE", "cite_count": 150}
  ],
  "edges": [
    {"source": "doi1", "target": "doi2", "weight": 5}
  ],
  "clusters": [
    {"cluster_id": 1, "theme": "碳交易政策评估", "papers": ["doi1", "doi2"]}
  ]
}
```

### Step 5: 质量评级

对纳入文献按期刊层级评级：

| 等级 | 期刊示例 | 权重 |
|------|---------|------|
| Top 5 | JF / JPE / Econometrica | 5 |
| Top 10 | JFE / RFS / JME / 金融研究 | 4 |
| Top 30 | JAE / JDE / 经济研究 / 管理世界 | 3 |
| 普通 | 其他SSCI/CSSCI | 2 |
| Working Paper | NBER / arXiv | 1 |

### Step 6: 研究缺口识别

使用 LLM 分析引文网络，识别：

1. **理论缺口**：现有理论无法解释的现象
2. **方法缺口**：现有方法的局限性
3. **样本缺口**：研究样本的局限（地区/行业/时间）
4. **机制缺口**：中介/调节机制未被充分探讨
5. **情境缺口**：特定情境（新兴市场、数字经济等）研究不足

LLM 分析提示词：

```
你是一个经济金融领域专家。基于以下文献列表和引文网络，
识别出3-5个最主要的研究缺口，并说明：
1. 每个缺口的现状（现有研究做了什么）
2. 为什么是缺口（未解决什么问题）
3. 对该研究方向的启示
```

### Step 7: 生成输出文件

#### output/fin-literature/LIT_REVIEW.md

```markdown
# 系统性文献综述: [研究主题]

> 综述日期: [日期]
> 检索来源: OpenAlex + ArXiv + NBER + 百度学术
> 纳入文献: [N] 篇

## 1. 研究概述
[研究问题定义 + PICO]

## 2. 理论框架
[理论基础：X理论、Y理论...]

## 3. 主要实证文献

### 3.1 [主题分组1]
| 文献 | 期刊 | 方法 | 样本 | 核心发现 |
|------|------|------|------|----------|
| ... | ... | ... | ... | ... |

### 3.2 [主题分组2]
...

## 4. 研究方法趋势
[按方法分类的文献分布]

## 5. 引文网络分析
[高影响力文献 + 聚类结构]

## 6. 研究缺口
1. [缺口1]
2. [缺口2]
3. [缺口3]

## 7. 未来研究方向
[基于缺口的建议]

## 参考文献
[BibTeX 格式]
```

#### output/fin-literature/LIT_SUMMARY.md

三页executive summary，供快速阅读：

```markdown
# 文献综述摘要: [研究主题]

## 一句话结论
[研究领域现状的一句话概括]

## 核心发现（Top 5）
1. [发现1]
2. [发现2]
...

## 主要研究方法
[DID / IV / RDD / PSM 分布]

## 最大研究缺口
[最值得切入的研究空白]

## 对本研究的启示
[基于综述的3个具体建议]
```

#### output/fin-literature/CITATION_GRAPH.json

引文网络完整数据（用于后续可视化）。

## MCP 工具快速参考

| 数据源 | 工具 | 参数 |
|--------|------|------|
| OpenAlex | `get_openalex_works` | query, per_page=50, sort=citation_count |
| ArXiv | `semantic_search` | query, max_results=30 |
| NBER | `get_nber_papers` | category, year_from |
| 中文检索 | `brave_web_search` | query |
| 论文全文 | `get_context7_by_arxiv` | arxiv_id |
| 中文文献 | `search_chinese_papers` | query, per_page |
| CSSCI | `search_cssci_papers` | query |

## 与其他技能的关系

- **上游**：无（独立使用或配合用户描述）
- **下游**：
  - `fin-generate-idea` → 基于研究缺口生成想法
  - `fin-novelty-check` → 验证想法新颖性
  - `fin-paper-writing` → 基于综述撰写引言

## 注意事项

1. **中文文献优先百度学术/知网**：英文数据库对中文政策研究覆盖不足
2. **NBER 是高质量补充**：工作论文往往代表最新方法
3. **研报仅作背景补充**：研报不作为学术文献纳入
4. **PRISMA 流程透明**：Checkpoint 展示筛选数量，用户可调整
5. **引文网络需要DOI**：优先使用有DOI的文献构建网络
