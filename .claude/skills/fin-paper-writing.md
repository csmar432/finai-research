# fin-paper-writing — 论文写作编排器

根据 `PAPER_OUTLINE.md` 和 `REFINED_DESIGN.md` 编排调用各子模块，管理版本并确保章节间的一致性，从大纲到可投稿稿件。

## 功能

### 编排流程

```
Phase A: 正文写作    → fin-paper-draft（生成各章节 .tex）
Phase B: 图表生成    → fin-paper-figure（生成 figures/）
Phase C: 一致性检查  → 图表/表格/公式编号对齐
Phase D: 对抗性Review → fin-review-loop（循环直到通过）
Phase E: LaTeX编译   → fin-paper-convert
Phase F: 投稿前检查  → fin-submit-check
```

### 版本管理

- `VERSION_MANIFEST.md` — 版本日志
- `CHAPTER_STATUS.md` — 各章节状态
- `CONSISTENCY_CHECK.md` — 一致性检查报告

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
