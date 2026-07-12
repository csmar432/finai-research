---
name: fin-paper-writing
description: 经济金融论文写作编排器。根据PAPER_OUTLINE.md和REFINED_DESIGN.md，编排调用fin-paper-draft（正文写作）、fin-paper-figure（图表生成）、fin-review-loop（review循环），管理版本并确保章节间的一致性。
argument-hint: [outline-reference]
---

# 经济金融论文写作编排器

编排从大纲到可投稿论文的全流程，管理章节间的引用一致性和版本迭代。

## 触发条件

**触发关键词**：`写论文`、`paper writing`、`论文写作`、`开始写作`

## 与 fin-full-pipeline 的关系

`fin-full-pipeline` 负责"研究"阶段（lit→idea→novelty→design），
本技能负责"写作"阶段（outline→draft→figure→review→convert）。

```
fin-full-pipeline 终点
       ↓ PAPER_OUTLINE.md + REFINED_DESIGN.md
fin-paper-writing（写作编排）
       ↓
┌──────────────────────────────────────────┐
│ 阶段A: 正文写作 (fin-paper-draft)         │
│   → 生成 draft_v{N}/introduction.tex     │
│       ↓ checkpoint                       │
│ 阶段B: 图表生成 (fin-paper-figure)       │
│   → 生成 draft_v{N}/figures/*.pdf       │
│       ↓ checkpoint                       │
│ 阶段C: 整合检查（章节一致性）              │
│   → 验证引用、表编号、图编号              │
│       ↓ checkpoint                       │
│ 阶段D: 对抗性Review (fin-review-loop)    │
│   → 多轮review直到达标                   │
│       ↓ checkpoint                       │
│ 阶段E: 编译 (fin-paper-convert)          │
│   → 生成 main.pdf                        │
│       ↓                                  │
│ 阶段F: 投稿前检查 (fin-submit-check)      │
│   → SUBMIT_CHECK_REPORT.md              │
└──────────────────────────────────────────┘
       ↓
输出: draft_v{N}/main.pdf（可投稿）
```

## 前置条件检查

### Phase A: Pre-writing Checklist

在开始写作前，验证以下文件存在：

| 检查项 | 文件路径 | 说明 |
|--------|----------|------|
| [ ] 论文大纲 | `output/fin-manuscript/PAPER_OUTLINE.md` | 章节结构和内容要点 |
| [ ] 研究设计 | `output/fin-refinement/REFINED_DESIGN.md` | 变量定义、识别策略 |
| [ ] 实证结果 | `output/fin-experiments/results/` | 表格/图表文件 |
| [ ] 参考文献 | `draft_v{N}/references.bib` | BibTeX格式 |
| [ ] 研究简报 | `FIN_BRIEF.md` | 目标期刊、语言 |

**如果任何文件缺失，停止并提示用户先完成前置步骤。**

## 章节写作顺序（关键原则）

### Phase B: Chapter Writing Order

**始终使用此顺序，不要按论文的自然顺序写：**

```
推荐顺序（而非论文顺序）：
1. Data & Methodology → 先写方法，数据最清晰
2. Descriptive Statistics → 紧跟方法
3. Main Results → 结果最清晰，容易写
4. Mechanism Analysis → 如果有
5. Heterogeneity Analysis → 如果有
6. Robustness Checks → 紧凑汇总
7. Conclusion → 有全篇在手，总结更全面（最难）
8. Introduction → 最后写intro，知道全貌，贡献更清晰
9. Literature Review & Hypotheses → H1/H2/H3框架
10. Abstract → 写完所有章节后，自然形成摘要
```

**为什么这样排序？**
- 方法和数据是基础，写完就清楚论文的"做什么"
- 结果是论文核心，先写建立信心
- 结论需要全篇在手，最后写才能全面总结
- 引言需要知道结论，才能准确描述贡献
- 摘要需要知道全文，才能精炼概括

## 编排协调

### Phase C: Orchestration

编排调用以下子技能：

```python
# 协调关系图：
fin-paper-writing (编排器)
    │
    ├──→ fin-paper-draft (正文写作)
    │       每个章节独立生成
    │
    ├──→ fin-paper-figure (图表生成)
    │       图表生成后与正文交叉引用
    │
    ├──→ fin-ref-paper (参考文献管理)
    │       确保引用格式一致
    │
    └──→ fin-review-loop (Review循环)
            每章节完成后Review
```

**调用方式**（Cursor Skill语法）：

```markdown
<!-- 写方法论章节 -->
Skill: fin-paper-draft
"methodology"

<!-- 生成图表 -->
Skill: fin-paper-figure
"main_results"

<!-- 管理参考文献 -->
Skill: fin-ref-paper
"update"

<!-- Review章节 -->
Skill: fin-review-loop
"methodology_v1"
```

## 版本管理

### Phase D: Version Management

#### VERSION_MANIFEST.md

维护版本变更记录：

```markdown
# 版本清单

**论文标题**: [标题]
**目标期刊**: [期刊]
**当前版本**: draft_v{N}

## 版本历史

| 版本 | 日期 | 主要变更 | 作者 |
|------|------|---------|------|
| draft_v1 | 2026-06-13 | 初始草稿 | Agent |
| draft_v2 | 2026-06-14 | 补充机制检验 | Agent |
| draft_v3 | 2026-06-15 | 根据Review修改引言 | Human |

## 当前状态

| 章节 | 状态 | 字数 | 最后修改 |
|------|------|------|---------|
| introduction.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 1,234 | 2026-06-13 |
| literature.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 2,345 | 2026-06-13 |
| methodology.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 1,567 | 2026-06-12 |
| results.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 3,210 | 2026-06-12 |
| robustness.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 890 | 2026-06-13 |
| conclusion.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 678 | 2026-06-13 |
| abstract.tex | [DRAFT/REVIEWING/REVISED/FINAL] | 250 | 2026-06-13 |
| references.bib | [DRAFT/REVIEWING/REVISED/FINAL] | — | 2026-06-13 |
```

#### CHAPTER_STATUS.md

追踪每个章节的详细状态：

```markdown
# 章节状态追踪

## 章节详情

### introduction.tex
- **状态**: DRAFT
- **字数**: 1,234
- **创建时间**: 2026-06-13 10:00
- **最后修改**: 2026-06-13 14:30
- **Review轮次**: 0
- **检查清单**: 
  - [x] 动机充分
  - [x] 3个贡献点清晰
  - [ ] 字数符合期刊要求
  - [x] Roadmap包含
- **备注**: 需补充第3个贡献点

### methodology.tex
- **状态**: REVIEWING
- **字数**: 1,567
- **Review轮次**: 1
- **Review反馈**: 通过
```

#### 版本迭代流程

当需要重大修改时：

```markdown
## 创建新版本流程

1. 将 draft_v{N}/ 复制为 draft_v{N+1}/
2. 在 VERSION_MANIFEST.md 中记录：
   | draft_v{N+1} | [日期] | [修改原因] | Agent/User |
3. 在 CHAPTER_STATUS.md 中标记需修改的章节为"重写"
4. 执行修改
5. 重新执行 阶段C（一致性检查）→ 阶段D（Review）→ 阶段E（编译）→ 阶段F（检查）
```

## 一致性检查

### Phase E: Consistency Checks

每章节完成后，自动执行以下检查：

#### 检查1：图表编号一致性

| 图编号 | FIGURE_PLAN中的位置 | 正文引用 | 状态 |
|--------|-------------------|---------|------|
| fig1_sample | 3.1（样本构建） | `\ref{fig1_sample}` in §3.1 | ✅/❌ |
| fig2_trend | 3.2（描述统计） | `\ref{fig2_trend}` in §3.2 | ✅/❌ |
| fig3_main | 4.1（主结果） | `\ref{fig3_main}` in §4.1 | ✅/❌ |
| fig4_hetero | 4.3（异质性） | `\ref{fig4_hetero}` in §4.3 | ✅/❌ |
| fig5_mechanism | 4.4（机制） | `\ref{fig5_mechanism}` in §4.4 | ✅/❌ |
| fig6_placebo | 4.5（稳健性） | `\ref{fig6_placebo}` in §4.5 | ✅/❌ |

#### 检查2：表格编号一致性

| 表编号 | TABLE_PLAN中的位置 | 正文引用 | 状态 |
|--------|-------------------|---------|------|
| tab:var_def | 3.2（变量定义） | `\ref{tab:var_def}` | ✅/❌ |
| tab:summary | 3.3（描述性统计） | `\ref{tab:summary}` | ✅/❌ |
| tab:main | 4.1（主回归） | `\ref{tab:main}` | ✅/❌ |
| tab:heterogeneity | 4.3（异质性） | `\ref{tab:heterogeneity}` | ✅/❌ |
| tab:robustness | 4.5（稳健性） | `\ref{tab:robustness}` | ✅/❌ |

#### 检查3：假设与结果一致性

| 假设 | 章节位置 | 结果位置 | 对应结论 | 状态 |
|------|---------|---------|---------|------|
| H1 | §2.3 | §4.1 | [结论] | ✅/❌ |
| H2 | §2.3 | §4.3 | [结论] | ✅/❌ |
| H3 | §2.3 | §4.4 | [结论] | ✅/❌ |

#### 检查4：引用一致性

- [ ] 所有 `\cite{}` 都在 `references.bib` 中存在
- [ ] 引用格式统一（JF风格/GB-T-7714）
- [ ] 无"幽灵引用"（引用但无对应条目）

## 输出文件结构

```
output/fin-manuscript/draft_v{N}/
├── introduction.tex      # 引言
├── literature.tex         # 文献综述与假说
├── methodology.tex        # 数据与实证方法
├── results.tex            # 实证结果
├── robustness.tex         # 稳健性检验
├── conclusion.tex         # 结论
├── abstract.tex           # 摘要
├── references.bib         # 参考文献
├── tables/                # 表格文件
│   ├── tab1_var_def.tex
│   ├── tab2_summary.tex
│   └── ...
├── figures/               # 图表文件
│   ├── fig1_sample.pdf
│   ├── fig2_trend.pdf
│   └── ...
├── VERSION_MANIFEST.md    # 版本清单
├── CHAPTER_STATUS.md      # 章节状态
├── CONSISTENCY_CHECK.md   # 一致性检查报告
└── main.pdf              # 编译后的PDF
```

## Checkpoint（检查点）

**每个Phase完成后必须暂停，等待用户确认：**

| 检查点 | 内容 | 用户操作 |
|--------|------|----------|
| Phase A完成 | 所有前置文件验证 | 确认开始写作 |
| 每章节完成 | 章节草稿生成 | Review通过后继续 |
| Phase C完成 | 一致性检查报告 | 确认无问题 |
| Phase D完成 | Review通过报告 | 确认进入编译 |
| Phase E完成 | PDF编译成功 | 确认格式 |
| Phase F完成 | 投稿检查报告 | 确认提交 |

## Review重点（按章节）

| 章节 | Review重点 |
|------|-----------|
| introduction | 动机是否充分？贡献是否夸大？字数是否合规？ |
| literature | 文献覆盖是否完整？假设推导是否有理论支撑？ |
| methodology | 识别策略是否合理？数据处理是否透明？ |
| results | 表格解读是否准确？经济意义讨论是否充分？ |
| conclusion | 是否过度推断？局限性是否诚实？ |

## 控制标志

| 标志 | 默认值 | 说明 |
|------|--------|------|
| STRICT_MODE | `true` | 每章写完后必须通过检查清单才能继续 |
| REVIEW_ROUNDS | `4` | 最大review轮次 |
| AUTO_COMPILE | `false` | 每次章节修改后是否自动编译 |
| VERSION_CONTROL | `true` | 重大修改是否自动创建新版本 |
| CHECKPOINT_ENABLED | `true` | 每个Phase后是否暂停等待确认 |

## 关键原则

1. **方法论先写**。先写methodology和results，有助于理清思路，避免intro空洞。
2. **章节独立追踪**。每个章节有自己的状态、字数、最后修改时间。
3. **一致性是底线**。图表编号、表编号、公式编号必须在正文和计划文件中完全一致。
4. **Review在整合后**。等图表和正文都写完再做Review，避免重复Review。
5. **版本是审计记录**。每次重大修改都要记录变更原因和审查意见采纳情况。
6. **中文论文写作顺序略有不同**。中文期刊常按顺序写（引言→文献→方法→结果→结论）。
7. **写作过程要记录**。在VERSION_MANIFEST.md中实时更新状态。
8. **终稿前必须通过submit-check**。格式和匿名性是编辑初审的门槛。
9. **占位符规则**。首次生成用`[coef]`、`[se]`、`[N]`占位，由数据填充。
10. **每次保存后自动更新状态**。章节完成、修改、保存后立即更新CHAPTER_STATUS.md。
