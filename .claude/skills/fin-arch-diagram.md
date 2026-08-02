# fin-arch-diagram — 架构图/流程图/层次图生成

为 PPT 汇报和技术文档生成研究/项目架构图、流程图、层次图。**不依赖数据**，
**不阻塞论文流水线**，用户主动触发。

## 功能

### 三种图类型

| 类型 | 用途 | 函数 |
|------|------|------|
| `swim_lane` | 系统架构（多层 + 泳道） | `swim_lane_gv()` |
| `process_flow` | 业务流程（决策菱形 + 分支 + 循环） | `process_flow_gv()` |
| `hierarchy_tree` | 树状/层级（树/CONSORT/组织架构） | `hierarchy_tree_gv()` |

### 双后端

| 后端 | 风格 | 依赖 |
|------|------|------|
| `graphviz`（默认） | ~92% 接近 draw.io | `brew install graphviz` + `pip install graphviz` |
| `matplotlib` | 基础 | 零系统依赖 |

graphviz 不可用时自动 fallback 到 matplotlib。

## 触发条件

- **关键词**: `架构图` `流程图` `层次图` `swim_lane` `process_flow` `hierarchy`
- **Skill 语法**: `Skill: fin-arch-diagram "[描述]"`

## 推荐用法

```python
from scripts.research_framework.arch_diagram_gv import draw_diagram
from scripts.research_framework.arch_diagram import (
    DiagramSpec, Node, Edge, Layer,
)

spec = DiagramSpec(
    title="系统架构",
    layers=[
        Layer("USER LAYER", y_top=70, y_bottom=55, color="#FDEBD0", text_color="#D68910"),
        Layer("SKILLS LAYER", y_top=53, y_bottom=38, color="#D6EAF8", text_color="#21618C"),
    ],
    nodes=[
        Node("u1", "Users", layer="USER LAYER", color="#E67E22", icon="U"),
        Node("p1", "Pipeline", layer="SKILLS LAYER", color="#3498DB", icon="1"),
    ],
    edges=[
        Edge("u1", "p1", label="调用"),
    ],
)

# 默认 graphviz 后端
out = draw_diagram(spec, "output/figures/arch.png")

# 显式 matplotlib 后端
out = draw_diagram(spec, "out.png", engine="matplotlib")
```

## 5 张参考 demo

```bash
python scripts/research_framework/arch_diagram_demos.py
```

输出（graphviz 后端，浅色风格）：
- `demo_arch_finresearch_gv.png` — 系统架构
- `demo_hierarchy_pipeline_gv.png` — 8 步流水线
- `demo_process_flow_gv.png` — 决策菱形 + 分支
- `demo_consort_gv.png` — CONSORT 流程
- `demo_org_chart_gv.png` — 组织架构

## 与 fin-viz-launch 的区别

| 场景 | 用这个 |
|------|--------|
| 画 PPT 系统架构图 | **fin-arch-diagram** |
| 画 PPT 流程图 | **fin-arch-diagram** |
| 画论文 DID 平行趋势图 | fin-viz-launch |
| 画论文相关性热力图 | fin-paper-figure |

**核心区别**：架构图不依赖数据，数据图表依赖数据。

## 依赖项

- `scripts/research_framework/arch_diagram.py` (matplotlib 后端)
- `scripts/research_framework/arch_diagram_gv.py` (graphviz 后端)
- `scripts/research_framework/arch_diagram_demos.py` (5 张 demo)

## 跨平台

- macOS / Linux / Windows 全兼容
- graphviz 安装: macOS `brew install graphviz` / Linux `apt install graphviz` / Windows `choco install graphviz`
- graphviz 不可用时自动 fallback 到 matplotlib，不抛异常
