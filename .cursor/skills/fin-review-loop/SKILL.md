---
name: fin-review-loop
description: 经济金融论文的对抗性review循环。对草稿进行多轮严格评审，检查实证严谨性、方法正确性、理论贡献和写作质量，给出可操作的修改建议。（AI review 不能替代同行评审，草稿必须经研究者核实后投稿。）
trigger: "review|评审|审稿|检查论文"
version: 1.0.0
created: 2026-06-13
tags: [paper, review, adversarial, quality]
---

# fin-review-loop

经济金融论文的对抗性review循环。对草稿进行多轮严格评审，检查实证严谨性、方法正确性、理论贡献和写作质量，给出可操作的修改建议。（AI review 不能替代同行评审，草稿必须经研究者核实后投稿。）

## 触发条件

- 关键词: `review` `评审` `审稿` `检查论文` `对抗性review` `论文检查`
- Skill语法: `Skill: fin-review-loop`

## 评分维度与权重

| 维度 | 权重 | 通过阈值 |
|------|------|---------|
| 新颖性 (Novelty) | 30% | >= 6.0 |
| 实证严谨性 (Empirical Rigour) | 30% | >= 6.0 |
| 文献覆盖 (Literature Coverage) | 15% | >= 5.0 |
| 写作清晰 (Writing Clarity) | 15% | >= 5.0 |
| 学术影响 (Academic Impact) | 10% | >= 5.0 |

## 评审难度级别

- `standard`: 模拟标准学术审稿人
- `strict`: 模拟顶刊审稿人 (JF/JFE 级别)
- `nightmare`: 模拟严苛批评型审稿人 (如被拒稿后的防御性检查)

## 评审难度示例

### standard
- 发现问题时会给出温和建议
- 接受主流方法选择
- 关注核心贡献是否清晰

### strict
- 要求所有实证细节完备
- 质疑识别策略的每一步
- 检查文献是否覆盖最新顶刊

### nightmare
- 预设论文会被拒，准备攻击
- 寻找方法论上的致命缺陷
- 模拟最严格的匿名审稿人

## 停止条件 (立即终止评审并报告用户)

满足以下任一条件时，立即停止评审：
- **新颖性 < 6.0** → 建议重新评估研究定位
- **实证严谨性 < 6.0** → 必须修复实证问题才能继续
- **已达到最大评审轮次 (4轮)**

## 评审流程

### 第一步：解析论文

1. 读取 `output/fin-manuscript/` 下的所有 `.tex` 文件
2. 提取论文结构：Introduction, Literature Review, Data, Methodology, Results, Conclusion
3. 如文件不存在，扫描项目根目录和 `papers/` 目录

### 第二步：诊断性检查

自动运行以下检查：

```
□ 平行趋势检验结果是否存在
□ 稳健性检验 >= 6 种
□ 异质性分析是否包含
□ 机制分析是否包含
□ 参考文献是否包含近3年顶刊论文
□ 变量定义表是否完整
□ 数据来源是否标注
□ 实证方法选择是否合理
```

### 第三步：逐维度评分

对每个维度进行 1-10 分评分，并说明理由：

| 维度 | 评分 | 理由 |
|------|------|------|
| 新颖性 | X | 边际贡献是什么？与现有文献区别？ |
| 实证严谨性 | X | 识别策略是否合理？数据是否可靠？ |
| 文献覆盖 | X | 是否覆盖最新顶刊？经典文献？ |
| 写作清晰 | X | 逻辑是否清晰？论证是否连贯？ |
| 学术影响 | X | 对该领域的潜在影响？引用潜力？ |

### 第四步：生成逐节反馈

为论文每个章节生成具体、可操作的反馈：

```
### Introduction
- 问题: 边际贡献描述不够具体
- 建议: 明确说明与X论文的区别，本文的增量贡献是什么

### Data & Methodology
- 问题: 平行趋势图缺少统计显著性标注
- 建议: 在图中标注pre-treatment各期系数的置信区间

### Results
- 问题: 基准回归系数解读不够严谨
- 建议: 添加经济显著性解释（1个标准差变动对应Y变化X%）
```

### 第五步：识别审稿人攻击点

识别论文中最可能被审稿人攻击的弱点：

```
## 审稿人攻击点
1. [高风险] 审稿人会质疑平行趋势假设——需要pre-trends test p值
2. [中风险] 样本期间选择——为何选择2012-2022年？
3. [低风险] 稳健性检验中未包含安慰剂检验
```

### 第六步：生成修订计划

生成 `REVISION_PLAN.md`，按优先级列出修复项：

```markdown
# 修订计划 — Round N

## 优先级 P0 (必须修复)
1. [实证] 添加平行趋势检验的p值到图中
2. [实证] 补充安慰剂检验

## 优先级 P1 (强烈建议)
1. [写作] 明确边际贡献表述
2. [文献] 补充近3年JF/JFE论文引用

## 优先级 P2 (可选优化)
1. [写作] 优化摘要结构
2. [格式] 检查参考文献格式
```

### 第七步：等待用户确认修订

```
[CHECKPOINT] 评审完成。请确认：
1. 接受修订计划 → 开始修订
2. 修改修订计划 → 告知修改内容
3. 终止评审 → 记录当前状态
```

### 第八步：重复评审

修订完成后，重新运行评审流程。重复直到通过所有阈值或达到停止条件。

## 输出格式

```markdown
# Review Report — Round N

## Overall Score: X/10 (WEIGHTED)

## Dimension Scores
| Dimension | Score | Pass? |
|-----------|-------|-------|
| Novelty | 7.5 | ✅ |
| Rigour | 6.0 | ✅ |
| Literature | 7.0 | ✅ |
| Clarity | 6.5 | ✅ |
| Impact | 7.0 | ✅ |

## Diagnostic Checks
| Check | Status |
|-------|--------|
| Parallel trends test | ✅ |
| Robustness >= 6 types | ✅ |
| Heterogeneity analysis | ✅ |
| Mechanism analysis | ✅ |
| Recent top-journal refs | ✅ |

## Section-by-Section Feedback

### Introduction
- Issue: 边际贡献描述不够具体
- Suggestion: 明确说明与X论文的区别

### Data & Methodology
- Issue: 平行趋势图缺少统计显著性标注
- Suggestion: 在图中标注pre-treatment各期系数的置信区间

## Reviewer Attack Vectors
1. [HIGH RISK] 审稿人会质疑平行趋势假设——需要pre-trends test p-value
2. [MEDIUM RISK] 样本期间选择——为何选择2012-2022年？

## PASS/FAIL/REVISION NEEDED
```

## 输出文件

- `output/fin-review/REVIEW_REPORT_ROUND_N.md` — 本轮评审报告
- `output/fin-review/REVISION_PLAN.md` — 修订计划

## 依赖项

- `scripts/research_framework/modern_did.py` — DID诊断工具
- `scripts/research_framework/robustness_runner.py` — 稳健性检验运行器
- `scripts/journal_template.py` — 期刊格式验证

## 约束

1. 每轮评审必须完整执行所有8个步骤
2. 停止条件满足时必须立即报告，不得继续评审
3. 反馈必须具体、可操作，避免泛泛而谈
4. 攻击点识别必须基于真实审稿人行为模式
5. 修订计划必须标注优先级 (P0/P1/P2)
