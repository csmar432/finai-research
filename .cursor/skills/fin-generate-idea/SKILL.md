---
name: fin-generate-idea
description: 针对经济金融研究方向的创意生成与评估。生成8-12个可发表的研究idea，过滤后在数据可行的情况下进行小规模实证验证，输出排序后的研究想法报告。
argument-hint: [research-field]
---

# 经济金融研究想法生成器

针对研究方向 `$ARGUMENTS` 生成 8-12 个排序研究想法，经过数据可行性筛选后输出推荐名单。

## 流程概览

```
研究方向输入
     ↓
阶段1: 研究领域解析 + 约束提取
     ↓
阶段2: 文献提取 — 使用 MCP 获取高影响力论文
     ↓
阶段3: 缺口分析 — 识别领域内"未完成"的工作
     ↓
阶段4: 想法生成 — 基于文献生成 8-12 个想法
     ↓
阶段5: 【强制】数据可行性筛选 — 对每个想法运行数据源检查
     ↓
阶段6: 过滤标记 — 无数据路径的想法标记"需授权模拟"
     ↓
阶段7: 综合排序 — noverlty × 0.4 + data × 0.3 + publish × 0.3
     ↓
输出: IDEA_REPORT.md
```

## 触发条件

当用户明确要求生成具体研究想法时触发，例如：

- "有什么关于[领域]的研究想法"
- "生成[领域]的研究idea"
- "帮我找[领域]的研究方向"
- "我想研究[主题]，有什么新想法"

## 输出文件

```
output/fin-ideas/
├── IDEA_REPORT.md         ← 完整想法报告（8-12个想法，含评分）
├── IDEA_DATA_CHECK.md     ← 数据可行性检查结果
└── IDEA_CANDIDATES.md     ← 精简版（TOP 3-5）
```

## 阶段详解

### 阶段1: 研究领域解析

#### 1.1 解析研究领域

识别研究方向所属的宏观领域：

| 领域 | 核心关键词 | 典型研究问题 |
|------|----------|-------------|
| 绿色金融 | ESG、碳排放、绿色债券、气候风险、绿色信贷 | 绿色政策效果、环境信息披露 |
| 数字金融 | Fintech、数字支付、互联网金融、API银行 | 数字普惠、金融科技赋能 |
| 碳经济学 | 碳交易、碳配额、碳关税、减排激励 | 碳市场效率、政策有效性 |
| 宏观金融 | 货币政策传导、金融周期、系统性风险 | 政策传导机制、金融稳定 |
| 公司金融 | 融资约束、资本结构、公司治理、并购 | 融资决策优化、公司价值 |
| 资产定价 | 因子模型、异常收益、机构投资者 | 定价因子、收益预测 |
| 行为金融 | 投资者情绪、散户行为、羊群效应 | 行为偏差、市场效率 |
| 金融科技 | 区块链、数字货币、开放银行 | 新技术应用、模式创新 |

#### 1.2 提取约束

从用户输入中提取约束条件：

```python
constraints = {
    "target_journal": "JF/JFE/RFS/经济研究/金融研究/...",
    "method_preference": "DID/IV/RDD/机器学习/...",
    "data_preference": "A股/美股/宏观/...",
    "time_range": "2010-2024/特定事件窗口/...",
    "sample_restriction": "创业板/国有企业/...",
}
```

### 阶段2: 文献提取

#### 2.1 MCP 多源检索

**必须按以下顺序执行检索**：

```yaml
# 第1步：NBER 工作论文（优先）
CallMcpTool: user-nber-wp -> search_nber_papers
  query: "[研究领域] + China + empirical"
  year_from: 2023

# 第2步：OpenAlex（250M+论文）
CallMcpTool: user-openalex -> get_openalex_works
  query: "[研究领域] + [核心机制] + China"
  per_page: 30

# 第3步：中文顶刊（A股必查）
CallMcpTool: user-brave-search -> brave_web_search
  query: "经济研究 金融研究 管理世界 [核心关键词]"
  num_results: 15

# 第4步：ArXiv（方法论文）
CallMcpTool: user-arxiv -> semantic_search
  query: "[研究领域] + empirical methods China"
  max_results: 15
```

#### 2.2 高影响力论文筛选

从检索结果中筛选高影响力论文：

| 筛选标准 | 阈值 | 原因 |
|---------|------|------|
| 期刊层次 | JF/JFE/RFS/JME/QJE + 中文顶刊 | 质量保证 |
| 引用量 | 前 20% 或 >50 次引用 | 经时间检验 |
| 发表时间 | 近 5 年为主 | 前沿性 |
| 方法可靠性 | 识别策略清晰 | 可参照 |

#### 2.3 文献结构化提取

对每篇核心文献提取：

```markdown
## 文献卡片

- **标题**: [论文标题]
- **期刊**: [期刊名]
- **年份**: [发表年份]
- **作者**: [作者列表]
- **核心发现**: [1-2句话]
- **方法**: [DID/IV/RDD/...]
- **数据**: [数据集描述]
- **研究缺口**: [从该论文的 limitation 或 future work 中提取]
```

### 阶段3: 缺口分析

#### 3.1 缺口识别框架

使用以下框架系统识别研究缺口：

| 缺口类型 | 描述 | 识别方法 |
|---------|------|---------|
| 理论缺口 | 某理论预测在特定场景未被验证 | 文献中"我们尚不清楚..." |
| 方法缺口 | 某方法在特定场景未被使用 | 方法 vs 市场组合矩阵 |
| 数据缺口 | 某数据集未被用于某研究问题 | 新数据源 vs 研究问题 |
| 场景缺口 | 某发现未在特定市场验证 | 市场 vs 机制组合矩阵 |
| 机制缺口 | 某传导路径未被检验 | 机制链条中的空白 |

#### 3.2 缺口输出模板

```markdown
## 已识别研究缺口

### 缺口 1: [缺口名称]
- **类型**: [理论/方法/数据/场景/机制]
- **描述**: [具体描述]
- **为什么重要**: [理论和实践意义]
- **可行性**: [数据和方法是否可行]

### 缺口 2: [缺口名称]
...
```

### 阶段4: 想法生成

#### 4.1 生成提示词

使用 LLM 生成基于文献的研究想法：

```
你是一名经济金融领域顶级学者。请基于以下文献综述和研究缺口，
生成8-12个可发表的研究想法。

【研究领域】
[领域名称]

【核心文献】
[文献卡片列表]

【已识别的研究缺口】
1. [缺口1]
2. [缺口2]
...

【约束条件】
- 目标期刊: [期刊]
- 偏好方法: [方法]
- 数据偏好: [数据]

【生成要求】
1. 每个想法必须对应一个或多个研究缺口
2. 明确识别策略（DID/IV/RDD/面板/机器学习）
3. 明确所需核心数据
4. 指出边际贡献（理论/方法/数据）
5. 评估发表潜力
6. 基于文献给出"初步信号"（支持假设的已有证据）
```

#### 4.2 想法格式

每个想法必须按以下格式输出：

```markdown
## Idea N: [标题]

### 基本信息
- **研究缺口**: [对应缺口编号]
- **研究问题**: [一句话描述]
- **核心机制**: [因果传导路径]

### 方法设计
- **识别策略**: [方法]
- **关键识别假设**: [假设内容]
- **估计方法**: [模型]

### 数据需求
- **核心数据集**: [数据源]
- **时间范围**: [样本期]
- **关键变量**: [Y, X, 控制变量]

### 边际贡献
- **理论**: [理论贡献]
- **方法**: [方法贡献]
- **数据**: [数据贡献]

### 发表潜力
- **目标期刊**: [期刊]
- **新颖性**: [高/中/低]
- **可行性**: [高/中/低]

### 初步信号
- **文献支持**: [支持假设的已有文献]
- **机制合理性**: [1-5评分]
```

### 阶段5: 数据可行性筛选（强制）

**对每个想法执行数据源检查**

#### 5.1 调用 IdeaDataValidator

```python
from scripts.idea_data_checker import quick_check, IdeaDataValidator

# 准备想法列表
ideas = [
    {
        "id": f"idea_{i}",
        "title": "[想法标题]",
        "description": "[描述]",
        "keywords": "[关键词列表]",
    }
    for i in range(1, 13)
]

# 执行数据可行性检查
report = quick_check(ideas)
```

#### 5.2 筛选逻辑

```python
def filter_ideas_by_feasibility(report: ValidationReport) -> dict:
    """根据数据可行性筛选想法"""

    # 分类
    available = [r for r in report.idea_results
                 if r.feasibility == Feasibility.AVAILABLE]

    partial = [r for r in report.idea_results
               if r.feasibility == Feasibility.PARTIALLY_AVAILABLE]

    gap = [r for r in report.idea_results
           if r.feasibility == Feasibility.DATA_GAP]

    auth = [r for r in report.idea_results
            if r.feasibility == Feasibility.REQUIRES_AUTH]

    return {
        "green": available,      # 可立即推荐
        "yellow": partial,       # 可推进但需补充
        "red": gap,             # 需先补充数据
        "orange": auth,         # 需授权模拟
    }
```

### 阶段6: 用户授权决策

**橙色标签的想法需要用户明确授权才能进入推荐名单**

#### 6.1 展示授权请求

```
⚠️ 以下想法需要您授权使用模拟数据：

想法 9: [标题]
- 所需数据: [数据描述]
- 缺失原因: [原因]
- 授权后果: 研究结果不能用于正式发表

想法 10: [标题]
...

──────────────────────────────────────────────
请选择：
  (1) 授权模拟 — 使用模拟数据继续（结果不能发表）
  (2) 跳过模拟想法 — 仅推荐数据可行的想法
  (3) 补充数据 — 稍后补充真实数据后再评估
```

#### 6.2 标记处理

```python
# 用户授权后，标记为可推荐
authorized_ideas = [idea for idea in ideas if idea.get("authorized_synthetic")]

# 未授权的想法标记为"需授权"
for idea in ideas:
    if idea.get("feasibility") == Feasibility.REQUIRES_AUTH and not idea.get("authorized_synthetic"):
        idea["status"] = "REQUIRES_AUTH"
        idea["recommendation"] = "需用户授权使用模拟数据"
```

### 阶段7: 综合排序

#### 7.1 评分公式

```
综合评分 = 新颖性评分 × 0.4 + 数据可行性评分 × 0.3 + 发表潜力评分 × 0.3
```

| 维度 | 权重 | 评分标准 |
|-----|-----|---------|
| 新颖性 | 40% | 高=10, 中=7, 低=4 |
| 数据可行性 | 30% | 可行=10, 部分=6, 缺口=0, 模拟=3 |
| 发表潜力 | 30% | 顶刊=10, 一区=8, 二区=6 |

#### 7.2 排序输出

```python
def rank_ideas(ideas: list[dict], report: ValidationReport) -> list[dict]:
    """综合排序想法"""

    # 构建评分查找表
    score_map = {r.idea["id"]: r.feasibility_score for r in report.idea_results}

    ranked = []
    for idea in ideas:
        novelty = {"high": 10, "medium": 7, "low": 4}.get(idea.get("novelty"), 5)
        data_score = score_map.get(idea["id"], 0) * 10  # 转换为10分制
        publish = {"top": 10, "first": 8, "second": 6}.get(idea.get("journal_tier"), 5)

        composite = novelty * 0.4 + data_score * 0.3 + publish * 0.3

        idea["composite_score"] = round(composite, 1)
        ranked.append(idea)

    return sorted(ranked, key=lambda x: x["composite_score"], reverse=True)
```

## 输出格式

### IDEA_REPORT.md 模板

```markdown
# 研究想法报告

**研究方向**: [方向]
**生成日期**: [日期]
**想法总数**: N个

## 执行摘要

[3-5句话总结推荐想法]

## TOP 3 推荐想法

### 想法 1: [标题] ⭐⭐⭐
**综合评分**: X.X/10 | **数据可行性**: 🟢 可行

| 维度 | 评分 |
|------|------|
| 新颖性 | X/10 |
| 数据可行性 | X/10 |
| 发表潜力 | X/10 |
| **综合** | **X.X/10** |

- **研究问题**: [一句话]
- **研究缺口**: [对应缺口]
- **识别策略**: [方法]
- **核心数据**: [数据源]
- **边际贡献**: [创新点]
- **文献支持**: [支持假设的已有文献]
- **初步信号**: [支持/不支持/待验证]

---

### 想法 2: [标题] ⭐⭐
**综合评分**: X.X/10 | **数据可行性**: 🟡 部分可行

| 维度 | 评分 |
|------|------|
| 新颖性 | X/10 |
| 数据可行性 | X/10 |
| 发表潜力 | X/10 |
| **综合** | **X.X/10** |

- **研究问题**: [一句话]
- **研究缺口**: [对应缺口]
- **识别策略**: [方法]
- **核心数据**: [数据源]
- **边际贡献**: [创新点]
- **数据缺口**: [缺失的数据]
- **补充方案**: [如何获取]

---

### 想法 3: [标题] ⭐
**综合评分**: X.X/10 | **数据可行性**: 🟡 部分可行

[同上结构]

---

## 所有想法列表

| 排名 | 想法 | 综合评分 | 新颖性 | 数据可行 | 发表潜力 | 状态 |
|------|------|---------|--------|---------|---------|------|
| 1 | 想法1 | 9.2 | 高 | 🟢 可行 | 顶刊 | 推荐 |
| 2 | 想法2 | 8.5 | 高 | 🟡 部分 | 一区 | 推荐 |
| 3 | 想法3 | 8.1 | 中 | 🟢 可行 | 顶刊 | 推荐 |
| 4 | 想法4 | 7.2 | 中 | 🟡 部分 | 一区 | 待补充 |
| 5 | 想法5 | 6.8 | 高 | 🔴 缺口 | 一区 | 待数据 |
| 6 | 想法6 | 5.5 | 中 | 🟠 模拟 | 二区 | 需授权 |
| ... | ... | ... | ... | ... | ... | ... |

## 数据需求汇总

### 🟢 可直接使用
- [数据源]: [描述]

### 🟡 需补充
- [数据源]: [描述] → [如何获取]

### 🔴 需获取
- [数据源]: [描述] → [获取方式]

## 下一步

1. 选择一个想法进入新颖性验证（fin-novelty-check）
2. 或选择多个想法进入实验设计（fin-experiment-design）
3. 或返回补充数据后再评估

## 方法论提示

[针对本领域的常用识别策略建议]
```

## IdeaDataValidator 快速参考

### 一行调用

```python
from scripts.idea_data_checker import quick_check

ideas = [
    {"id": "1", "title": "想法1", "description": "描述", "keywords": ["关键词"]},
    # ...
]

report = quick_check(ideas)
```

### 逐个验证

```python
from scripts.idea_data_checker import IdeaDataValidator

validator = IdeaDataValidator(ideas)
report = validator.validate_all()
validator.print_report(report)

# 访问结果
for result in report.idea_results:
    print(f"{result.idea['title']}: {result.feasibility.value}")
    print(f"  Score: {result.feasibility_score:.1f}")
    print(f"  Recommendation: {result.recommendation}")
```

### 解读可行性状态

| Feasibility | 含义 | 颜色 | 建议操作 |
|-------------|-----|-----|---------|
| `AVAILABLE` | 数据完全可行 | 🟢 | 可立即推荐 |
| `PARTIALLY_AVAILABLE` | 部分数据缺失 | 🟡 | 可推进但需补充 |
| `DATA_GAP` | 数据缺口严重 | 🔴 | 需先获取数据 |
| `REQUIRES_AUTH` | 需授权模拟 | 🟠 | 需用户明确授权 |

## MCP 工具快速索引

| 需求 | MCP Server | 工具 | 优先级 |
|------|------------|------|--------|
| NBER 工作论文 | `user-nber-wp` | `search_nber_papers` | 高 |
| OpenAlex 论文 | `user-openalex` | `get_openalex_works` | 高 |
| ArXiv 论文 | `user-arxiv` | `semantic_search` | 中 |
| 中文文献 | `user-brave-search` | `brave_web_search` | 高 |
| 论文全文 | `user-context7` | `get_context7_by_query` | 中 |
| 研报 | `user-eastmoney-reports` | `get_research_report` | 低 |

## 关键约束

1. **每个想法必须基于文献**：不能凭空生成想法
2. **数据可行性是硬过滤**：无数据路径的想法不进推荐名单
3. **模拟数据需要授权**：未授权的模拟想法必须标记
4. **评分必须透明**：展示所有维度的评分和权重
5. **中文顶刊不可忽视**：A股研究中中文文献是重要先例来源
6. **新颖性评估必须具体**：不能只说"新颖"，要指出具体增量贡献

## 快速命令

```bash
# 完整流程
python scripts/research_framework/pipeline.py \
    --topic "研究方向" \
    --mode generate_idea \
    --output output/fin-ideas/

# 仅想法生成
python scripts/research_framework/pipeline.py \
    --topic "研究方向" \
    --mode generate_idea \
    --skip_validation

# 仅数据验证
python scripts/idea_data_checker.py \
    --ideas-file output/fin-ideas/IDEA_REPORT.md
```
