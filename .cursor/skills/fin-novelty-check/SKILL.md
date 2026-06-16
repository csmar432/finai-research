---
name: fin-novelty-check
description: 验证经济金融研究想法的新颖性。在JF、JFE、RFS、JME等顶刊及arXiv中搜索近三年文献，输出结构化新颖性报告和定位策略。
argument-hint: [研究想法或IDEA_REPORT.md路径]
---

# 研究想法新颖性验证

在顶刊数据库中系统性检索，评估研究想法的原创性，输出定位策略。

## 核心功能

- **四维评估**：相似度 / 方法差异 / 样本独特性 / 机制新颖性
- **顶刊检索**：JF / JFE / RFS / JME / arXiv / NBER
- **中文顶刊**：经济研究 / 金融研究 / 管理世界
- **综合评分**：HIGH (≥8) / MEDIUM (6-8) / LOW (<6)
- **定位策略**：差异化路径 + 潜在风险规避

## 工作流程

### Step 1: 想法解析

将研究想法拆解为 3-5 个可检验的核心主张（Claims）：

```
原始想法: "数字金融对中小企业创新的影响"

核心主张:
1. 数字金融能显著提升中小企业创新投入
2. 融资约束是主要作用机制
3. 东部地区效果强于西部地区
4. 对民营企业效果强于国有企业
```

每个 Claim 需包含：
- **变量关系**：[X] → [Y]
- **假设方向**：[正向/负向/倒U型]
- **适用情境**：[样本范围]

### Step 2: 多源并行检索

对每个 Claim 分别检索，使用以下模板：

#### JF/JFE/RFS（英文顶刊）

```python
server: user-brave-search
tool: brave_web_search
params: {
    "query": "site:jf.com digital finance SME innovation empirical"
}
# 替换: site:jfe.oxfordjournals.org, site:rfs.org
```

#### arXiv（近3年预印本）

```python
server: user-arxiv
tool: semantic_search
params: {
    "query": "digital finance AND (SME OR \"small business\") AND (innovation OR R&D) AND (2023 OR 2024 OR 2025)"
}
```

#### NBER（工作论文）

```python
server: user-nber-wp
tool: get_nber_papers
params: {
    "category": "corporate finance OR financial economics",
    "year_from": 2023
}
```

#### 中文顶刊

```python
server: user-brave-search
tool: brave_web_search
params: {
    "query": "site:er.cngp.org.cn OR site:jr.cass.org.cn 数字金融 中小企业 创新 实证"
}
# 经济研究: site:er.cngp.org.cn
# 金融研究: site:jr.cass.org.cn
# 管理世界: site:管理与世界.ajcass.com
```

#### 补充检索（更宽泛）

```python
server: user-openalex
tool: get_openalex_works
params: {
    "query": "digital finance innovation SMEs empirical",
    "per_page": 30
}
```

### Step 3: 四维评估

对每个 Claim 逐一评估：

| 维度 | 评估问题 | 评分 (1-10) |
|------|----------|-------------|
| **相似度** (S) | 已有多少研究做了一样的 X→Y？ | 1=完全相同, 10=从未做过 |
| **方法差异** (M) | 你的方法与已有研究有何不同？ | 1=方法相同, 10=全新方法 |
| **样本独特性** (U) | 数据/样本是否独特？ | 1=常用数据, 10=独有数据 |
| **机制新颖性** (N) | 机制解释是否新颖？ | 1=常见机制, 10=全新机制 |

**评估标准详解**：

**相似度 (S)**：
- 1-3：完全相同的 X→Y 已有多个顶刊研究
- 4-6：相近主题（如数字金融→创新），但 X/Y 定义不同
- 7-10：X→Y 组合从未被研究过

**方法差异 (M)**：
- 1-3：直接复用已有研究方法（如标准DID）
- 4-6：有改进（如异质性DID、动态DID）
- 7-10：引入全新方法或组合（如合成DID + 机器学习）

**样本独特性 (U)**：
- 1-3：常用数据库（AShare、Compustat）
- 4-6：独特样本（特定地区/行业/时间段）
- 7-10：独有数据（自建数据库、实地调查）

**机制新颖性 (N)**：
- 1-3：融资约束/资源获取等常见机制
- 4-6：细分机制（如融资约束的某个维度）
- 7-10：全新机制（如心理账户、数字化转型路径）

### Step 4: 综合评分

计算每个 Claim 的加权得分：

```
Claim_Score = 0.3*S + 0.25*M + 0.25*U + 0.2*N
```

**整体评分**：
- 取所有 Claim 的平均分
- 考虑最薄弱 Claim 的下限约束

**评级**：
- HIGH (≥8)：可以继续，建议在 Introduction 中明确差异化
- MEDIUM (6-8)：需要调整，建议按 Step 6 调整策略
- LOW (<6)：建议更换想法或重大调整

### Step 5: 识别竞争论文

找出与本研究最相似的 3 篇论文：

```
选择标准：
1. X→Y 组合相同或高度相似
2. 发表在同级及以上期刊
3. 时间在近5年内

对每篇论文说明：
- 为什么相似（Claim 重叠度）
- 本研究的差异化点
- 如何在 Introduction 中委婉处理
```

### Step 6: 定位策略（MEDIUM/LOW 专用）

如果评分为 MEDIUM 或 LOW，提供调整建议：

| 问题类型 | 调整策略 |
|----------|----------|
| 相似度过高 | 聚焦细分样本（特定行业/地区/规模） |
| 方法无差异 | 引入新方法或数据来源 |
| 样本无独特性 | 使用独有数据或组合多个数据库 |
| 机制常见 | 挖掘新机制或异质性分析 |

**定位策略模板**：

```
本研究与 [竞争论文] 的区别：
1. [维度1]: [本研究做法] vs [竞争论文做法]
2. [维度2]: ...
3. [维度3]: ...

Contribution 重申：
- 本研究首次在 [样本/情境] 下检验 [X→Y]
- 采用 [新方法/改进方法] 解决了 [问题]
- 发现 [新机制/异质性模式]
```

### Step 7: 生成报告

#### output/fin-novelty/NOVELTY_REPORT.md

```markdown
# 新颖性报告: [研究想法标题]

> 评估日期: [日期]
> 评估者: fin-novelty-check

## 整体评级: HIGH / MEDIUM / LOW
## 综合评分: X/10

---

## 研究想法摘要

**核心主张**：
1. [主张1]
2. [主张2]
3. [主张3]

**预期贡献**：
- 理论贡献: [1-2句话]
- 实证贡献: [1-2句话]
- 政策贡献: [1-2句话]

---

## 主张分析

| 主张 | 相似度(S) | 方法(M) | 样本(U) | 机制(N) | 单项得分 | 权重分 |
|------|-----------|---------|---------|---------|----------|--------|
| 1. X→Y | 7 | 8 | 6 | 5 | 6.55 | 0.30 |
| 2. M中介 | 6 | 7 | 8 | 7 | 6.95 | 0.25 |
| 3. 异质性 | 8 | 6 | 7 | 8 | 7.30 | 0.25 |
| 4. [样本] | 9 | 8 | 7 | 8 | 8.15 | 0.20 |

**加权综合得分**: 7.19/10

---

## 顶刊检索结果

### JF/JFE/RFS
- [竞争论文1] — [期刊] [年份] — [相似点] / [差异点]
- [竞争论文2] — ...

### arXiv / NBER
- [预印本1] — [年份] — [相似点] / [差异点]

### 中文顶刊
- [文献1] — [期刊] [年份] — [相似点] / [差异点]

---

## Top 3 竞争论文

### 1. [Citation]
**期刊**: [期刊名] | **年份**: [年份]
**相似点**: [为什么与本研究重叠]
**差异点**: [本研究的独特之处]
**在 Introduction 中的处理**: [如何委婉地承认相关研究同时指出差异]

### 2. [Citation]
...

### 3. [Citation]
...

---

## 审稿人风险评估

| 风险 | 审稿人可能质疑 | 缓解策略 |
|------|---------------|----------|
| R1 | "这个选题太老了" | 强调样本/方法/情境的独特性 |
| R2 | "方法没有新意" | 展示方法改进或新方法应用 |
| R3 | "数据不够独特" | 说明数据来源的不可替代性 |

---

## 定位策略

[仅当 MEDIUM/LOW 时填写]

### 当前问题
- 相似度较高维度: [维度]
- 需要改进方向: [方向]

### 建议调整
1. **样本聚焦**: [具体建议]
2. **方法改进**: [具体建议]
3. **机制挖掘**: [具体建议]

### 差异化定位
```
本研究的核心差异化：
- [差异1]: [具体说明]
- [差异2]: [具体说明]
```

---

## 建议期刊

根据研究主题和评分建议目标期刊：
- [期刊1] — [理由]
- [期刊2] — [理由]

---

## 下一步

- [ ] 如果 HIGH：可直接进入 `fin-experiment-design`
- [ ] 如果 MEDIUM：按调整建议修改想法后重新评估
- [ ] 如果 LOW：建议重新生成想法或更换研究方向
```

**Checkpoint**：向用户展示报告，询问是否继续：

```markdown
## 新颖性评估完成

**评级**: HIGH (7.8/10)
**核心风险**: 相似度中等，需加强方法差异

**是否继续**？
 [1] 继续 — 进入实验设计 (`fin-experiment-design`)
 [2] 调整 — 按建议调整想法后重新评估
 [3] 更换 — 重新生成研究想法
```

## MCP 工具快速参考

| 数据源 | 工具 | 查询模板 |
|--------|------|----------|
| JF | `brave_web_search` | `site:jf.com [keywords]` |
| JFE | `brave_web_search` | `site:jfe.oxfordjournals.org [keywords]` |
| arXiv | `semantic_search` | `[topic] AND [method] AND (2023 OR 2024 OR 2025)` |
| NBER | `get_nber_papers` | category, year_from=2023 |
| OpenAlex | `get_openalex_works` | query, per_page=30 |
| 论文全文 | `get_context7_by_query` | query, max_results |

## 与其他技能的关系

- **上游**：
  - `fin-generate-idea` → 输出候选想法供验证
  - `fin-lit-review` → 文献综述为新颖性判断提供依据
- **下游**：
  - `fin-experiment-design` → 新颖性验证通过后进入设计
  - `fin-paper-writing` → 在 Introduction 中引用竞争论文

## 注意事项

1. **评分是主观的**：基于检索结果的定性评估，需结合实际文献
2. **HIGH 不代表无风险**：高评分仍需在 Introduction 中妥善处理竞争文献
3. **中文顶刊同样重要**：经济研究/金融研究/管理世界的相关研究必须检索
4. **预印本也是竞争**：arXiv/NBER 工作论文代表最新进展
5. **评分阈值灵活**：可根据目标期刊调整（如 RFS 可接受 MEDIUM）
