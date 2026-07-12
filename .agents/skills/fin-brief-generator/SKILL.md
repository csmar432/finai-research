---
name: fin-brief-generator
description: 根据用户输入或已有研究输出（文献综述/想法报告/新颖性报告），自动生成或更新FIN_BRIEF.md，减少用户填写负担。
trigger: "生成简报|FIN_BRIEF|brief|研究简报|简报"
version: 1.0.0
created: 2026-06-13
tags: [brief, research, metadata, outline, generator]
---

# fin-brief-generator

根据用户输入或已有研究输出（文献综述/想法报告/新颖性报告），自动生成或更新FIN_BRIEF.md，减少用户填写负担。

## 触发条件

- 关键词: `生成简报` `FIN_BRIEF` `brief` `研究简报` `简报` `研究概要`
- Skill语法: `Skill: fin-brief-generator`
- 前置条件: 可选 — 已有研究输出文件

## 三种工作模式

### 模式一：推理模式 (Inference Mode)

当项目中已有研究输出文件时，从现有文件中自动推断字段值。

**输入文件优先级**:
```
1. output/fin-literature/LIT_REVIEW.md       → 提取研究领域、方法、文献缺口
2. output/fin-ideas/IDEA_REPORT.md           → 提取候选想法、评分
3. output/fin-novelty/NOVELTY_REPORT.md      → 提取定位策略
4. output/fin-refinement/REFINED_DESIGN.md  → 提取研究设计细节
```

**执行流程**:

```python
from scripts.brief_generator import BriefGenerator, InferenceMode

generator = BriefGenerator(project_root=".")

# 推理模式：从现有文件推断
brief = generator.generate_from_outputs(mode=InferenceMode)

# 仅向用户展示未知字段
unknown_fields = brief.get_unknown_fields()
print(f"需要您补充 {len(unknown_fields)} 个字段:")
for field in unknown_fields:
    print(f"  - {field}")
```

**示例**:
```
已推断字段: 12/17
- 研究主题: 碳排放权交易对企业绿色创新的影响 ✅
- 因果推断方法: 双重差分法 (DID) ✅
- 目标期刊: 经济研究 ✅

需补充字段: 5/17
- 主要作者: ?
- 协作者: ?
- 资助机构: ?
- 文献综述截止日期: ?
- 初稿截止日期: ?
```

### 模式二：问卷模式 (Questionnaire Mode)

当有部分信息时，通过结构化问卷收集缺失信息。

**问卷流程**:

```python
from scripts.brief_generator import QuestionnaireMode

generator = BriefGenerator(project_root=".")

# 运行问卷
answers = generator.run_questionnaire(
    questions=[
        {
            "id": "topic",
            "question": "研究主题是什么？请用一句话描述",
            "type": "text",
            "required": True,
        },
        {
            "id": "journal",
            "question": "目标期刊是哪个？",
            "type": "choice",
            "options": ["JF", "JFE", "RFS", "经济研究", "金融研究", "管理世界", "其他"],
            "required": True,
        },
        {
            "id": "data_source",
            "question": "主要数据来源是什么？",
            "type": "choice",
            "options": ["Tushare/A股", "CSMAR", "Wind", "Yfinance/美股", "手动收集", "其他"],
            "required": True,
        },
        {
            "id": "method",
            "question": "有偏好的研究方法吗？",
            "type": "choice",
            "options": ["DID", "IV/2SLS", "RDD", "合成控制", "PSM", "面板GMM", "无偏好"],
            "required": False,
        },
    ],
    interactive=True,  # 对话式问卷
)
```

**问卷示例对话**:

```
问: 研究主题是什么？请用一句话描述
答: 碳排放权交易试点对企业绿色创新的影响

问: 目标期刊是哪个？
答: 经济研究

问: 主要数据来源是什么？
答: Tushare/A股

问: 有偏好的研究方法吗？
答: DID
```

### 模式三：快速问答模式 (Quick Q&A Mode)

从零开始，单次对话收集最基本信息，立即生成简报。

```python
from scripts.brief_generator import QuickQAMode

# 快速问答 — 仅3个核心问题
generator = QuickQAMode()

brief = generator.generate(
    topic="碳排放权交易对企业绿色创新的影响",
    journal="经济研究",
    authors="张三",
)
```

## FIN_BRIEF.md 结构

生成的文件结构如下：

```markdown
# 研究简报 (FIN_BRIEF)

> 生成时间: 2026-06-13
> 版本: 1.0.0
> 状态: draft | in_progress | completed

---

## 基本信息

- **研究主题**: [topic]
- **目标期刊**: [journal]
- **研究类型**: [实证研究/综述/方法论/案例研究]
- **语言**: [中文/英文/双语]
- **预估字数**: [字数] 字

## 研究团队

- **主要作者**: [name]
- **协作者**: [names]
- **资助机构**: [funding]
- **伦理审批**: [IRB approval if applicable]

## 研究设计

- **因果推断方法**: [DID/IV/RDD/合成控制/PSM/面板GMM/其他]
- **识别策略**: [描述识别策略]
- **样本期间**: [start_year] - [end_year]
- **样本量**: [N firms/observations]
- **数据来源**:
  - [source_1]: [description]
  - [source_2]: [description]

## 变量定义

### 因变量
| 变量名 | 定义 | 数据来源 |
|--------|------|----------|
| [var_1] | [definition] | [source] |

### 自变量/核心解释变量
| 变量名 | 定义 | 数据来源 |
|--------|------|----------|
| [var_1] | [definition] | [source] |

### 控制变量
| 变量名 | 定义 | 数据来源 |
|--------|------|----------|
| [var_1] | [definition] | [source] |

## 实证方法

- **基准模型**: [模型描述]
- **固定效应**: [FE combination]
- **标准误**: [Clustering]
- **稳健性检验**: [list]
- **异质性分析**: [list]
- **机制分析**: [list]

## 行为控制

```yaml
AUTO_PROCEED: false        # 强制交互checkpoint
HUMAN_CHECKPOINT: true     # 每阶段暂停
REVIEWER_DIFFICULTY: strict # standard/strict/nightmare
LANGUAGE: zh              # zh/en/both
FALLBACK_SIMULATED_DATA: false  # 禁止静默使用模拟数据
```

## 时间线

| 阶段 | 截止日期 | 状态 |
|------|----------|------|
| 文献综述 | [date] | pending |
| 新颖性验证 | [date] | pending |
| 实证设计 | [date] | pending |
| 数据获取 | [date] | pending |
| 论文写作 | [date] | pending |
| 初稿完成 | [date] | pending |
| 投稿目标 | [date] | pending |

## 里程碑

- [ ] [ ] [date] 阶段1完成
- [ ] [ ] [date] 阶段2完成
- [ ] [ ] [date] 初稿完成

## 备注

[Any additional notes]

---

## 元数据

```yaml
generated_by: fin-brief-generator
version: 1.0.0
created: 2026-06-13
updated: 2026-06-13
parent_outputs:
  - LIT_REVIEW.md
  - IDEA_REPORT.md
  - NOVELTY_REPORT.md
  - REFINED_DESIGN.md
```
```

## 增强工具 (2026-06)

```python
from scripts.research_framework import (
    PolicyDatabase,           # 23个中国准自然实验政策数据库
    AShareVariableFetcher,    # 8个A股特殊变量
    FinancialChartFactory,     # 20个图表模板
)

# ============ 政策数据库 ============
pd = PolicyDatabase()

# 按领域搜索政策
carbon_policies = pd.get_policies(domain="carbon")
# 返回: [Policy(id=..., name=..., year=..., description=...)]

# 按关键词搜索
matching = pd.search("绿色创新")
# 返回: [Policy(...), ...]

# 获取政策详情
detail = pd.get_policy_detail("carbon_trading_pilot")
# 返回: PolicyDetail(start_year=..., provinces=[...], intensity=...)

# ============ A股特殊变量 ============
f = AShareVariableFetcher()

# 获取研发投入强度
rd = f.get_rd_intensity(["000001.SZ", "600000.SH"], years=["2018-2022"])

# 获取ESG评分
esg = f.get_esg_rating(["000001.SZ"], source="华证")

# 获取分析师覆盖
coverage = f.get_analyst_coverage(["000001.SZ"])

# ============ 图表工厂 ============
factory = FinancialChartFactory(output_dir="figures/")

# 预设图表
fig = factory.plot("parallel_trends", df,
    time_var="year",
    treat_var="treat",
    y_var="innovation",
    save_path="figures/parallel_trends.pdf")

# 自定义图表
fig = factory.plot_custom(
    chart_type="scatter",
    data=df,
    x="size",
    y="roa",
    color="treat",
    title="企业规模与盈利能力",
    xlabel="企业规模 (对数)",
    ylabel="ROA",
)
```

## 交互流程

```
[模式检测] 检测到项目已有研究输出文件

检测到的文件:
✅ output/fin-literature/LIT_REVIEW.md
✅ output/fin-ideas/IDEA_REPORT.md
✅ output/fin-novelty/NOVELTY_REPORT.md

[推理模式] 正在从现有文件推断字段...

推断结果:
- 研究主题: 碳排放权交易对企业绿色创新的影响
- 目标期刊: 经济研究
- 因果推断方法: 双重差分法 (DID)
- 样本期间: 2012-2022
- 数据来源: Tushare + 手动整理碳交易数据

需要您补充:
1. 主要作者: [请输入]
2. 协作者: [请输入] (可选)
3. 资助机构: [请输入] (可选)
4. 文献综述截止日期: [请输入]
5. 初稿截止日期: [请输入]
6. 投稿目标日期: [请输入]

请回答以上问题，或输入"跳过"使用默认值。
```

## 输出文件

- `FIN_BRIEF.md` — 研究简报主文件 (项目根目录)
- `FIN_BRIEF_BACKUP_v{n}.md` — 每次更新的备份

## 依赖项

- `scripts/brief_generator.py` — 简报生成器核心
- `scripts/research_framework/policy_database.py` — 政策数据库
- `scripts/research_framework/asvare_variable_fetcher.py` — A股变量获取
- `scripts/research_framework/fin_charts.py` — 图表工厂

## 约束

1. **推理优先** — 有现有输出时，自动推断而非重复询问
2. **最小输入** — 问卷只问必要信息，其他自动推断
3. **版本备份** — 每次更新前备份旧版本
4. **字段验证** — 期刊名必须匹配已知列表
5. **行为控制必填** — AUTO_PROCEED 等字段不能留空
