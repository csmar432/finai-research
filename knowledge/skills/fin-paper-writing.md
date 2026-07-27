# fin-paper-writing — 论文写作编排器

根据 `PAPER_OUTLINE.md` 和 `REFINED_DESIGN.md` 编排调用各子模块，管理版本并确保章节间的一致性，从大纲到可投稿稿件。

## 功能

### 编排流程

```
Phase A: 正文写作    → fin-paper-draft（生成各章节 .tex）
Phase B: 图表生成    → fin-paper-figure（生成 figures/）
Phase C: 一致性检查  → 图表/表格/公式编号对齐 + 语言质量检查
Phase D: 对抗性Review → fin-review-loop（循环直到通过）
Phase E: LaTeX编译   → fin-paper-convert
Phase F: 投稿前检查  → fin-submit-check
```

### 版本管理

- `VERSION_MANIFEST.md` — 版本日志（含语言质量维度）
- `CHAPTER_STATUS.md` — 各章节状态（含语言质量检查字段）
- `CONSISTENCY_CHECK.md` — 一致性检查报告

### 语言质量检查（Phase C 新增）

每章节完成后，必须执行语言质量检查：

```bash
python scripts/paper_language_checker.py draft_v1/xxx.tex
```

检查项：
- AI 味关键词：全文 0 次
- 底气指数：结论段满足 ≥1 项（具体数字/经济规模/机制描述/对比发现）
- 表格引导句：每表前后 ≥3 句
- 图表注释：每图 ≥1 句解读

**语言质量检查不通过的章节，不得进入 Review 环节。**

### Checkpoint 控制

- 每阶段完成后暂停，等待确认
- `HUMAN_CHECKPOINT: false` 时全自动运行

## 行为控制

| 标志 | 默认 | 说明 |
|------|------|------|
| `AUTO_PROCEED` | `false` | 自动选最优 |
| `HUMAN_CHECKPOINT` | `true` | 每阶段暂停 |
| `REVIEWER_DIFFICULTY` | `standard` | review 严格程度 |

## 调用方式

```
"写一篇关于碳排放权交易的实证论文，目标期刊经济研究"
```
