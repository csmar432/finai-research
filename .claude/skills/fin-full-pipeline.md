# fin-full-pipeline — 经济金融研究完整流程

> **注意**：本文件是文档版本。操作版本见 `.cursor/skills/fin-full-pipeline/SKILL.md`。

## 功能

端到端的经济金融学术研究流程：
`文献综述 → 想法生成 → 新颖性验证 → 实证方法设计 → 论文大纲 → 正文写作 → 图表生成 → LaTeX编译 → 投稿前检查`

## 新增原则（2026-06-04）

### 数据优先原则

数据验证必须前移到**阶段2（想法生成）**，不等到阶段5（数据获取）。

```
传统流程（有问题）:
  想法生成 → 新颖性验证 → 实证设计 → 数据获取 ← 到这里才发现无数据！

新流程（数据优先）:
  想法生成 → 【想法-数据交叉验证】 → 新颖性验证 → 实证设计 → 数据获取 ✓
```

### 强制交互原则

- 每个阶段完成后必须停下来等待用户确认
- 模拟数据使用必须有硬中断（`InteractivePipelineCheckpoint`）
- 禁止自动继续

## 核心模块

| 模块 | 功能 |
|------|------|
| `scripts/idea_data_checker.py` | 想法-数据交叉验证 |
| `scripts/data_source_checker.py` | 数据源预检查 |
| `scripts/pipeline_checkpoint.py` | 强制交互checkpoint |

## 详见

完整操作文档：`.cursor/skills/fin-full-pipeline/SKILL.md`
