---
name: fin-arch-diagram
description: 生成研究/项目架构图、流程图、层次图（swim_lane / process_flow / hierarchy_tree）。适合 PPT 汇报、技术文档、综述插图。输出风格接近 draw.io，可选 graphviz（高质量）/ matplotlib（零依赖）双后端。
trigger: "架构图|架构|流程图|流程|层次图|层次|swim_lane|process_flow|hierarchy|画架构|生成架构图|绘制流程图|绘制架构图|画一个流程图|组织架构图|架构示意图|系统架构图"
version: 1.0.0
created: 2026-08-02
tags: [visualization, architecture, diagram, graphviz, swim-lane, process-flow, hierarchy, ppt, presentation]
---

# fin-arch-diagram

生成高质量架构/流程/层次图，专为 PPT 汇报和技术文档插图设计。
**不依赖数据**（与 fin-viz-launch / fin-paper-figure 的"数据图表"互补），
**不阻塞论文流水线**（用户主动触发）。

## 触发条件

- **关键词**: `架构图` `架构` `流程图` `流程` `层次图` `层次`
  `swim_lane` `process_flow` `hierarchy` `画架构`
  `生成架构图` `绘制流程图` `绘制架构图`
  `画一个流程图` `组织架构图` `架构示意图` `系统架构图`
- **Skill 语法**: `Skill: fin-arch-diagram "[描述]"`
- **前置条件**: 无需数据 / 无需 DataFrame

## 三种图类型

| 类型 | 用途 | 函数 | graphviz 风格 |
|------|------|------|--------------|
| `swim_lane` | 系统架构（多层 + 泳道） | `swim_lane_gv()` | ✅ ~92% 接近 draw.io |
| `process_flow` | 业务流程（决策菱形 + 分支 + 循环） | `process_flow_gv()` | ✅ 决策菱形 + yes/no 边 |
| `hierarchy_tree` | 树状/层级（树/CONSORT/组织架构） | `hierarchy_tree_gv()` | ✅ tree/consort/org 三风格 |

## 推荐用法（PPT 制作最常用）

```python
from scripts.research_framework.arch_diagram_gv import draw_diagram
from scripts.research_framework.arch_diagram import (
    DiagramSpec, Node, Edge, Layer,
)

# 例：生成 FinResearch Agent 系统架构图
spec = DiagramSpec(
    title="FinResearch Agent · 系统架构",
    layers=[
        Layer("USER LAYER", y_top=70, y_bottom=55, color="#FDEBD0", text_color="#D68910"),
        Layer("SKILLS LAYER", y_top=53, y_bottom=38, color="#D6EAF8", text_color="#21618C"),
        Layer("PERSISTENCE", y_top=36, y_bottom=21, color="#EBDEF0", text_color="#6C3483"),
        Layer("INFRASTRUCTURE", y_top=19, y_bottom=4, color="#D5F5E3", text_color="#1E8449"),
    ],
    nodes=[
        Node("u1", "Researchers", layer="USER LAYER", color="#E67E22", icon="U"),
        Node("u2", "HitL Reviewer", layer="USER LAYER", color="#E67E22", icon="U"),
        Node("a1", "Orchestrator", layer="SKILLS LAYER", column="Sub-agents",
             color="#1ABC9C", icon="1"),
        Node("p1", "fin-full-pipeline", layer="SKILLS LAYER", column="Pipelines",
             color="#3498DB", icon="1"),
        # ... 更多节点
    ],
    edges=[
        Edge("u1", "p1"),
        Edge("p1", "a1", label="dispatch", style="invoke"),
        Edge("a1", "u2", label="HITL", style="invoke"),
        # ... 更多边
    ],
)

# 默认 graphviz 后端（接近 draw.io 风格）
out = draw_diagram(spec, "output/figures/finresearch_arch.png")
print(f"生成: {out}")

# 显式指定后端
out = draw_diagram(spec, "out.png", engine="graphviz")    # 高质量 (推荐)
out = draw_diagram(spec, "out.png", engine="matplotlib")  # 零系统依赖
```

## 5 张参考 demo（直接看效果）

```bash
python scripts/research_framework/arch_diagram_demos.py
```

输出（graphviz 后端，浅色风格）：
- `output/figures/demo_arch_finresearch_gv.png` — 系统架构 4 层 × 3 泳道
- `output/figures/demo_hierarchy_pipeline_gv.png` — 8 步研究流水线
- `output/figures/demo_process_flow_gv.png` — 决策菱形 + yes/no 分支 + 自循环
- `output/figures/demo_consort_gv.png` — CONSORT 样本筛选
- `output/figures/demo_org_chart_gv.png` — 组织架构（纵向）

## 节点 (Node) 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 唯一标识，用于 Edge 引用 |
| `label` | str | 显示文字（支持 `\n` 多行） |
| `color` | str | 边框色 hex（如 `#3498DB`） |
| `icon` | str | icon Unicode 字符（U=👤, 1-5=①-⑤, ?=❓, S=▶, E=■, K=📚, D=💾, P=📋, M=🔌, L=🧠） |
| `layer` | str | 所属 layer 名称 |
| `column` | str | 所属泳道名称（layer 内的纵向分隔） |

## 边 (Edge) 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `src` / `dst` | str | 源/目标节点 id |
| `label` | str | 边标签文字 |
| `style` | str | `solid`/`dashed`/`dotted`/`invoke`（红）/`loop`（黄）/`data`（蓝） |
| `arrow` | str | `->`（默认）/`<-`（反向）/`<->`（双向） |
| `color` | str | 自定义边颜色（覆盖 style 默认色） |

## Layer 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | Layer 名称（也作 cluster key） |
| `y_top` / `y_bottom` | int | 兼容 matplotlib 后端的纵向范围（graphviz 后端自动忽略） |
| `color` | str | Layer 背景填充色 hex |
| `text_color` | str | Layer 标题文字色 hex |

## 双后端行为对照

| 维度 | matplotlib 后端 | graphviz 后端（默认） |
|------|----------------|----------------------|
| 系统依赖 | ❌ 纯 Python | ⚠️ 需 `brew install graphviz` + `pip install graphviz` |
| 自动布局 | ❌ 手动坐标 | ✅ graphviz 智能布局 |
| 视觉风格 | 基础 | ⭐⭐⭐⭐ 接近 draw.io |
| 用户体感 | 简单但粗糙 | 专业、像素级对齐 |
| Fallback | — | graphviz 不可用时自动 fallback 到 matplotlib |

**cross-platform**: macOS / Linux / Windows 全兼容。
graphviz 不可用时 `draw_diagram()` 会自动警告并 fallback，不抛异常。

## 在 agent_pipeline 中可选自动生成

论文流水线 PLOTTING 阶段完成时，可通过 CLI flag 触发自动生成：

```bash
python scripts/agent_pipeline.py --topic "数字金融与企业创新" --auto-arch
```

- **默认**: 不生成（避免无意义 IO）
- **开启后**: 在 `output/arch_diagrams/` 输出架构图
- **失败**: 不阻塞流水线（best-effort 模式）

## 何时用 fin-arch-diagram vs fin-viz-launch

| 场景 | 用这个 |
|------|--------|
| 画 PPT 用系统架构图 | **fin-arch-diagram** ← 本文 |
| 画 PPT 用研究流程图 | **fin-arch-diagram** ← 本文 |
| 画 PPT 用组织架构图 | **fin-arch-diagram** ← 本文 |
| 画论文 DID 平行趋势图 | fin-viz-launch |
| 画论文 PSM 倾向得分图 | fin-viz-launch |
| 画论文相关性热力图 | fin-paper-figure |

**核心区别**：
- 架构图 = **不依赖数据**的"结构图"
- 数据图表 = **依赖数据**的"统计图"

## 输出规范

```
output/
├── figures/
│   └── finresearch_arch.png    # graphviz 后端 PNG（≥300 DPI 等价）
└── arch_diagrams/              # agent_pipeline --auto-arch 输出
    └── arch_<topic>_<timestamp>.png
```

## 约束

1. **不阻塞流水线** — 所有生成失败都 best-effort，不抛异常
2. **自动 fallback** — graphviz 不可用时自动回退 matplotlib
3. **可重复运行** — 同一 spec 输出相同结果（DOT 渲染确定性）
4. **跨平台** — macOS / Linux / Windows 统一行为

## 依赖项

- `scripts/research_framework/arch_diagram.py` — matplotlib 后端 (1038 行)
- `scripts/research_framework/arch_diagram_gv.py` — graphviz 后端 (新增)
- `scripts/research_framework/arch_diagram_demos.py` — 5 张 demo runner
- 系统命令 `dot` (graphviz) — 已验证 macOS `brew install graphviz`

## 注意事项

⚠️ 图标使用 Unicode emoji（👤📚💾🔌🧠 等），不同操作系统的 emoji 字体可能略有差异。
macOS 默认支持；Linux 需安装 `noto-coloremoji`；Windows 11+ 自带 Segoe UI Emoji。
如果对图标一致性要求严格，可改为图标编号（`icon="1"` 等）。
