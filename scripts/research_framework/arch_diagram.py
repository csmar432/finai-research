"""
arch_diagram.py — 架构/流程/层次图生成器（M1 骨架）

提供三类拓扑可视化能力（数据驱动 + 模板化）：
  - swim_lane_arch()    分层泳道架构图（如系统架构图）
  - process_flow()      业务流程图（含分支/决策）
  - hierarchy_tree()    层次结构图（树状/CONSORT/organizational）

设计原则:
  - 数据驱动：一份 nodes/edges/layers 配置出一张图
  - 不破坏现有模块：独立文件，不修改 fin_charts.py / chart_factory.py
  - 学术风格：默认配色与项目 fin_charts.py 一致
  - 中文字体：Hiragino Sans GB / STHeiti（macOS 内置）

M1 范围: 骨架版本（每种图一个最简实现，验证管线通）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

matplotlib.rcParams["font.sans-serif"] = [
    "Hiragino Sans GB", "STHeiti", "PingFang SC", "Arial Unicode MS",
]
matplotlib.rcParams["axes.unicode_minus"] = False


# ── Public data classes ───────────────────────────────────────────────────────


@dataclass
class Node:
    """架构图中的一个节点"""

    id: str
    label: str
    layer: str = ""           # 所属横向层（如 "User"、"Skills"）
    column: str = ""          # 所属纵向泳道（如 "Sub-agents"）
    color: str = "#2DD4BF"    # 节点主色
    icon: str | None = None   # 可选编号（如 "1"、"A"）
    x: float | None = None    # 手动坐标（None 时自动布局）
    y: float | None = None


@dataclass
class Edge:
    """节点之间的连线"""

    src: str
    dst: str
    label: str = ""
    style: str = "solid"      # solid / dashed / dotted
    arrow: str = "->"         # -> / <- / <->
    color: str = "#8FA3B8"


@dataclass
class Layer:
    """横向分层带"""

    name: str
    y_top: float
    y_bottom: float
    color: str = "#13233D"
    text_color: str = "#E8EEF6"


@dataclass
class Column:
    """纵向泳道（swim lane）"""

    name: str
    x_left: float
    x_right: float
    color: str = "#0F1F33"
    text_color: str = "#8FA3B8"
    dashed: bool = True  # 是否画虚线分隔


@dataclass
class DiagramSpec:
    """完整图配置"""

    title: str
    width: float = 100.0
    height: float = 60.0
    layers: list[Layer] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)   # 纵向泳道名（仅 swim_lane 用）
    column_specs: list[Column] = field(default_factory=list)  # M2: 泳道完整定义
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    bg_color: str = "#0A1929"
    show_legend: bool = True
    output_path: str = ""


# ── Internal helpers ──────────────────────────────────────────────────────────


def _clean(ax, w: float, h: float) -> None:
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def _box(ax, x, y, w, h, facecolor, edgecolor, lw=2.0, radius=0.6, zorder=3):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.3,rounding_size={radius}",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, zorder=zorder,
    )
    ax.add_patch(box)
    return box


def _arrow(ax, x1, y1, x2, y2, color="#8FA3B8", lw=2.0, style="-|>", zorder=2, ls="-"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=14,
        color=color, linewidth=lw, zorder=zorder, linestyle=ls,
        shrinkA=2, shrinkB=2,
    ))


def _node_center(node: Node, default_w=10.0, default_h=4.0):
    """节点中心坐标（手填优先，否则 None）"""
    if node.x is not None and node.y is not None:
        return node.x, node.y
    return None  # 留给具体图类型做自动布局


# ── M1 骨架函数（最简实现）─────────────────────────────────────────────────


def swim_lane_arch(spec: DiagramSpec) -> None:
    """分层泳道架构图
    M2 完整功能:
      - 横向 layer 带（背景填充 + 标题）
      - 纵向泳道分隔（column_specs，dashed 边界 + 顶部标题）
      - 节点 + 编号圆形 icon
      - 多线型箭头（solid / dashed / dotted）+ 双向
      - 底部图例（颜色 / 线型 / 图标）
    """
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 1. 横向 layer 带（背景）
    for layer in spec.layers:
        _box(
            ax, 0, layer.y_bottom, spec.width, layer.y_top - layer.y_bottom,
            facecolor=layer.color, edgecolor="none", radius=0, zorder=1,
        )
        ax.text(
            1.5, (layer.y_top + layer.y_bottom) / 2, layer.name,
            fontsize=10, color=layer.text_color, fontweight="bold",
            va="center", zorder=4,
        )

    # 2. 纵向泳道分隔（column_specs）
    for col in spec.column_specs:
        # 顶部泳道标题
        ax.text(
            (col.x_left + col.x_right) / 2, spec.height - 1.5, col.name,
            fontsize=10, color=col.text_color, ha="center",
            fontweight="bold", style="italic", zorder=4,
        )
        # 分隔虚线
        if col.dashed:
            x_divide = col.x_right
            ax.plot(
                [x_divide, x_divide], [1, spec.height - 3],
                color="#3A506B", linewidth=1.0, linestyle="--", zorder=2,
            )

    # 3. 节点 + 编号圆形 icon
    nw, nh = 10.0, 4.5
    by_id: dict[str, tuple[float, float]] = {}
    for node in spec.nodes:
        if node.x is None or node.y is None:
            continue
        _box(
            ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
            facecolor=spec.bg_color, edgecolor=node.color, lw=2.0, zorder=3,
        )
        ax.text(
            node.x, node.y, node.label, fontsize=9,
            color="#E8EEF6", ha="center", va="center",
            wrap=True, zorder=4,
        )
        # 编号圆形 icon
        if node.icon:
            ax.add_patch(Circle(
                (node.x - nw / 2 + 1.6, node.y + nh / 2 - 1.6), 1.2,
                color=node.color, zorder=5,
            ))
            ax.text(
                node.x - nw / 2 + 1.6, node.y + nh / 2 - 1.6, node.icon,
                fontsize=8, color="#0A1929",
                ha="center", va="center", fontweight="bold", zorder=6,
            )
        by_id[node.id] = (node.x, node.y)

    # 4. 多线型箭头
    arrow_style_map = {
        "->": "-|>", "<-": "<|-", "<->": "<|-|>",
    }
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        x1, y1 = by_id[e.src]
        x2, y2 = by_id[e.dst]
        style = arrow_style_map.get(e.arrow, "-|>")
        _arrow(
            ax, x1, y1, x2, y2,
            color=e.color, lw=1.8, style=style, ls=e.style,
        )
        # 可选: 边标签
        if e.label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(
                mx, my, e.label, fontsize=7, color="#8FA3B8",
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc=spec.bg_color,
                          ec="#3A506B", lw=0.5),
                zorder=5,
            )

    # 5. 标题
    ax.text(
        spec.width / 2, spec.height - 0.5, spec.title,
        fontsize=16, color="#2DD4BF", ha="center", fontweight="bold",
    )

    # 6. 图例（自动生成）
    if spec.show_legend:
        _render_legend(ax, spec)

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def _render_legend(ax, spec: DiagramSpec) -> None:
    """自动渲染底部图例"""
    # 收集: 节点颜色 / 边线型 / 编号 icon
    legend_y = 4.5
    legend_x = 3.0

    ax.text(
        legend_x, legend_y + 2, "图例",
        fontsize=9, color="#E8EEF6", fontweight="bold", zorder=10,
    )

    items = []

    # 节点颜色样本
    seen_colors: set[str] = set()
    for node in spec.nodes:
        if node.color not in seen_colors:
            seen_colors.add(node.color)
            items.append(("node", node.color, ""))
    for kind, color, label in items[:5]:
        _box(
            ax, legend_x - 0.5, legend_y, 1.5, 1.2,
            facecolor=spec.bg_color, edgecolor=color, lw=1.5, zorder=10,
        )
    legend_x += 4

    # 边线型样本
    line_styles = [("solid", "实线 · 主流程"),
                   ("dashed", "虚线 · 旁路/反馈"),
                   ("dotted", "点线 · 可选")]
    for style, label in line_styles:
        ax.plot(
            [legend_x, legend_x + 3], [legend_y + 0.6, legend_y + 0.6],
            color="#8FA3B8", linewidth=1.5, linestyle=style, zorder=10,
        )
        ax.text(
            legend_x + 3.5, legend_y + 0.6, label,
            fontsize=7, color="#E8EEF6", va="center", zorder=10,
        )
        legend_x += 12

    # 编号 icon 样本
    ax.text(
        legend_x, legend_y + 0.6, "编号 = 步骤顺序",
        fontsize=7, color="#E8EEF6", va="center", zorder=10,
    )
    ax.add_patch(Circle(
        (legend_x + 14, legend_y + 0.6), 0.8,
        color="#2DD4BF", zorder=10,
    ))
    ax.text(
        legend_x + 14, legend_y + 0.6, "N",
        fontsize=6, color="#0A1929",
        ha="center", va="center", fontweight="bold", zorder=11,
    )


def process_flow(spec: DiagramSpec) -> None:
    """业务流程图（M1: 纵向顺序排列节点 + 连线）"""
    fig, ax = plt.subplots(figsize=(10, 12), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 自动布局：按 nodes 顺序纵向排列
    n = len(spec.nodes)
    if n == 0:
        return
    spacing = (spec.height - 12) / n
    box_w, box_h = 28.0, spacing - 2.0

    for i, node in enumerate(spec.nodes):
        node.x = spec.width / 2
        node.y = spec.height - 6 - (i + 0.5) * spacing

    for node in spec.nodes:
        _box(ax, node.x - box_w / 2, node.y - box_h / 2, box_w, box_h,
             facecolor=spec.bg_color, edgecolor=node.color, lw=2.0, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=10,
                color="#E8EEF6", ha="center", va="center", zorder=4)
        if node.icon:
            ax.add_patch(Circle(
                (node.x - box_w / 2 + 1.8, node.y + box_h / 2 - 1.8), 1.2,
                color=node.color, zorder=5,
            ))
            ax.text(node.x - box_w / 2 + 1.8, node.y + box_h / 2 - 1.8,
                    node.icon, fontsize=9, color="#0A1929",
                    ha="center", va="center", fontweight="bold", zorder=6)

    # 连线
    for e in spec.edges:
        for node in spec.nodes:
            if node.id == e.src:
                x1, y1 = node.x, node.y - box_h / 2
            if node.id == e.dst:
                x2, y2 = node.x, node.y + box_h / 2
        _arrow(ax, x1, y1, x2, y2, color=e.color, ls=e.style)

    ax.text(spec.width / 2, spec.height - 4, spec.title,
            fontsize=18, color="#2DD4BF", ha="center", fontweight="bold")

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def hierarchy_tree(spec: DiagramSpec) -> None:
    """层次结构图（M1: 树状，每层水平居中排列）"""
    fig, ax = plt.subplots(figsize=(13, 8), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 自动布局: 按 layer 分组
    by_layer: dict[str, list[Node]] = {}
    for node in spec.nodes:
        by_layer.setdefault(node.layer, []).append(node)
    layers_sorted = sorted(by_layer.keys())

    n_levels = max(len(layers_sorted), 1)
    spacing = (spec.height - 12) / n_levels

    for li, layer_name in enumerate(layers_sorted):
        nodes = by_layer[layer_name]
        m = len(nodes)
        if m == 0:
            continue
        box_w = min(20.0, (spec.width - 10) / m - 2.0)
        total_w = m * box_w + (m - 1) * 4
        x_start = (spec.width - total_w) / 2 + box_w / 2
        for ni, node in enumerate(nodes):
            node.x = x_start + ni * (box_w + 4)
            node.y = spec.height - 6 - (li + 0.5) * spacing

    # 节点
    for node in spec.nodes:
        box_w = 18.0
        box_h = spacing - 2.0
        _box(ax, node.x - box_w / 2, node.y - box_h / 2, box_w, box_h,
             facecolor=spec.bg_color, edgecolor=node.color, lw=2.0, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=9,
                color="#E8EEF6", ha="center", va="center", zorder=4)

    # 连线（parent 用 layer 隐含关系：上一层 → 下一层，按顺序连接）
    # M1 简化：用 edges 配置
    by_id = {n.id: (n.x, n.y) for n in spec.nodes}
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        x1, y1 = by_id[e.src]
        x2, y2 = by_id[e.dst]
        # 父子线：从源节点底部到目标节点顶部
        _arrow(ax, x1, y1 - 3, x2, y2 + 3, color=e.color, ls=e.style)

    # 层标签
    for li, layer_name in enumerate(layers_sorted):
        ax.text(2, spec.height - 6 - (li + 0.5) * spacing, layer_name,
                fontsize=10, color="#8FA3B8", va="center", fontweight="bold")

    ax.text(spec.width / 2, spec.height - 4, spec.title,
            fontsize=18, color="#2DD4BF", ha="center", fontweight="bold")

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


# ── M1 demo ──────────────────────────────────────────────────────────────────


def _demo_finresearch_arch() -> str:
    """Demo 1: FinResearch Agent 系统架构图（M2 完整版）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_arch_finresearch.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="FinResearch Agent · 系统架构（demo）",
        width=100, height=70,
        column_specs=[
            Column("Sub-agents", 4, 36, color="#0F1F33"),
            Column("Pipelines", 36, 70, color="#0F1F33"),
            Column("Domain Knowledge", 70, 96, color="#0F1F33"),
        ],
        layers=[
            Layer("User Interface", y_top=66, y_bottom=58, color="#16273D"),
            Layer("Skills Layer", y_top=57, y_bottom=42, color="#1B3355"),
            Layer("Persistence Layer", y_top=41, y_bottom=26, color="#16273D"),
            Layer("Infrastructure", y_top=25, y_bottom=10, color="#1B3355"),
        ],
        nodes=[
            # User
            Node("u1", "Researchers", "User Interface",
                 color="#F5B700", icon="U", x=20, y=62),
            Node("u2", "HitL Reviewer", "User Interface",
                 color="#F5B700", icon="U", x=83, y=62),
            # Sub-agents
            Node("a1", "Orchestrator", "Skills Layer", "Sub-agents",
                 color="#34D399", icon="1", x=10, y=52),
            Node("a2", "Ideator", "Skills Layer", "Sub-agents",
                 color="#34D399", icon="2", x=22, y=52),
            Node("a3", "Reviewer", "Skills Layer", "Sub-agents",
                 color="#34D399", icon="3", x=10, y=46),
            Node("a4", "Tool-User", "Skills Layer", "Sub-agents",
                 color="#34D399", icon="4", x=22, y=46),
            # Pipelines
            Node("p1", "fin-full-\npipeline", "Skills Layer", "Pipelines",
                 color="#2DD4BF", icon="1", x=44, y=49),
            Node("p2", "fin-lit-\nreview", "Skills Layer", "Pipelines",
                 color="#2DD4BF", icon="2", x=55, y=49),
            Node("p3", "fin-novelty-\ncheck", "Skills Layer", "Pipelines",
                 color="#2DD4BF", icon="3", x=66, y=49),
            # Domain Knowledge (skill docs/knowledge base)
            Node("d1", "SKILL.md\n×17", "Skills Layer", "Domain Knowledge",
                 color="#A78BFA", icon="K", x=83, y=49),
            Node("d2", "knowledge/\nskills", "Skills Layer", "Domain Knowledge",
                 color="#A78BFA", icon="K", x=83, y=44),
            # Persistence
            Node("s1", "Checkpoint", "Persistence Layer", "Pipelines",
                 color="#F472B6", icon="D", x=40, y=33),
            Node("s2", "Provenance", "Persistence Layer", "Pipelines",
                 color="#F472B6", icon="P", x=55, y=33),
            Node("s3", "BibTeX Cache", "Persistence Layer", "Domain Knowledge",
                 color="#F472B6", icon="B", x=83, y=33),
            # Infrastructure
            Node("i1", "MCP ×43", "Infrastructure", "Pipelines",
                 color="#38BDF8", icon="M", x=50, y=17),
            Node("i2", "LLM\n(DeepSeek)", "Infrastructure", "Domain Knowledge",
                 color="#38BDF8", icon="L", x=83, y=17),
        ],
        edges=[
            Edge("u1", "p1"),
            Edge("p1", "a1", label="dispatch"),
            Edge("a1", "a2", style="dashed"),
            Edge("a2", "a3", style="dashed"),
            Edge("p1", "p2"),
            Edge("p2", "p3"),
            Edge("p3", "p1", label="loop", style="dashed"),
            Edge("p3", "u2", label="HITL", style="dashed"),
            Edge("a1", "d1", label="read"),
            Edge("p1", "s1"),
            Edge("p2", "s1", style="dashed"),
            Edge("p3", "s2"),
            Edge("d1", "s3", style="dashed"),
            Edge("s1", "i1"),
            Edge("s2", "i1", style="dashed"),
            Edge("s2", "i2"),
            Edge("s3", "i2", style="dashed"),
        ],
    )
    swim_lane_arch(spec)
    return out


def _demo_pipeline_hierarchy() -> str:
    """Demo 2: 8 步研究流水线层次图（树状）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_hierarchy_pipeline.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="研究流水线 · 8 步层次图（demo）",
        output_path=out,
        nodes=[
            Node("root", "研究流水线", layer="L0", color="#F5B700"),
            Node("p1", "1. 文献综述", layer="L1", color="#38BDF8"),
            Node("p2", "2. 想法生成", layer="L1", color="#A78BFA"),
            Node("p3", "3. 新颖性验证", layer="L1", color="#F472B6"),
            Node("p4", "4. 实证设计", layer="L1", color="#2DD4BF"),
            Node("p5", "5. 数据获取", layer="L1", color="#34D399"),
            Node("p6", "6. 实证分析", layer="L1", color="#FBBF24"),
            Node("p7", "7. 论文写作", layer="L1", color="#FB923C"),
            Node("p8", "8. 对抗评审", layer="L1", color="#F87171"),
            Node("c1", "Idea 数据可行性", layer="L2", color="#94A3B8"),
            Node("c2", "DID/IV/RDD 选型", layer="L2", color="#94A3B8"),
            Node("c3", "MCP 43 数据源", layer="L2", color="#94A3B8"),
            Node("c4", "300 DPI 图表", layer="L2", color="#94A3B8"),
        ],
        edges=[
            Edge("root", "p1"), Edge("root", "p2"), Edge("root", "p3"),
            Edge("root", "p4"), Edge("root", "p5"), Edge("root", "p6"),
            Edge("root", "p7"), Edge("root", "p8"),
            Edge("p2", "c1"), Edge("p4", "c2"), Edge("p5", "c3"), Edge("p6", "c4"),
        ],
    )
    hierarchy_tree(spec)
    return out


if __name__ == "__main__":
    p1 = _demo_finresearch_arch()
    p2 = _demo_pipeline_hierarchy()
    print(f"[OK] {p1}")
    print(f"[OK] {p2}")
    print("M2 demo 完成: 2 张示例图（swim_lane M2 版 + hierarchy_tree M1 版）")
