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
class DiagramSpec:
    """完整图配置"""

    title: str
    width: float = 100.0
    height: float = 60.0
    layers: list[Layer] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)   # 纵向泳道名（仅 swim_lane 用）
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
    """分层泳道架构图（M1: 仅画横向 layer 带 + 节点 + 连线）"""
    fig, ax = plt.subplots(figsize=(14, 7), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 横向 layer 带
    for layer in spec.layers:
        _box(
            ax, 0, layer.y_bottom, spec.width, layer.y_top - layer.y_bottom,
            facecolor=layer.color, edgecolor="none", radius=0, zorder=1,
        )
        ax.text(
            2, (layer.y_top + layer.y_bottom) / 2, layer.name,
            fontsize=11, color=layer.text_color, fontweight="bold",
            va="center", zorder=4,
        )

    # 节点（手填坐标；M1 暂不自动布局）
    for node in spec.nodes:
        if node.x is None or node.y is None:
            continue
        nw, nh = 10.0, 4.0
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor=spec.bg_color, edgecolor=node.color, lw=2.0, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=9,
                color="#E8EEF6", ha="center", va="center", zorder=4)

    # 连线
    pos = {(n.id, n.label): (n.x, n.y) for n in spec.nodes
           if n.x is not None and n.y is not None}
    # 反查用：(id) -> (x, y)
    by_id = {n.id: (n.x, n.y) for n in spec.nodes
             if n.x is not None and n.y is not None}
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        x1, y1 = by_id[e.src]
        x2, y2 = by_id[e.dst]
        _arrow(ax, x1, y1, x2, y2, color=e.color, ls=e.style)

    ax.text(spec.width / 2, spec.height - 2, spec.title,
            fontsize=18, color="#2DD4BF", ha="center", fontweight="bold")

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


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
    """Demo 1: FinResearch Agent 系统架构图（贴近参考图风格）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_arch_finresearch.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="FinResearch Agent · 系统架构（demo）",
        output_path=out,
        layers=[
            Layer("User Interface", y_top=58, y_bottom=50, color="#16273D"),
            Layer("Skills Layer", y_top=49, y_bottom=36, color="#1B3355"),
            Layer("Persistence Layer", y_top=35, y_bottom=22, color="#16273D"),
            Layer("Infrastructure", y_top=21, y_bottom=8, color="#1B3355"),
        ],
        nodes=[
            Node("u1", "Researchers", "User Interface", color="#F5B700", x=25, y=54),
            Node("u2", "HitL Reviewer", "User Interface", color="#F5B700", x=75, y=54),
            Node("s1", "fin-full-pipeline", "Skills Layer", color="#2DD4BF", x=15, y=42.5),
            Node("s2", "fin-lit-review", "Skills Layer", color="#2DD4BF", x=37, y=42.5),
            Node("s3", "fin-novelty-check", "Skills Layer", color="#2DD4BF", x=59, y=42.5),
            Node("s4", "fin-paper-draft", "Skills Layer", color="#2DD4BF", x=81, y=42.5),
            Node("p1", "Checkpoint Store", "Persistence Layer", color="#A78BFA", x=30, y=28.5),
            Node("p2", "Provenance Log", "Persistence Layer", color="#A78BFA", x=70, y=28.5),
            Node("i1", "MCP Servers ×43", "Infrastructure", color="#38BDF8", x=20, y=14.5),
            Node("i2", "LLM (DeepSeek)", "Infrastructure", color="#38BDF8", x=50, y=14.5),
            Node("i3", "LaTeX / Tectonic", "Infrastructure", color="#38BDF8", x=80, y=14.5),
        ],
        edges=[
            Edge("u1", "s1"), Edge("u1", "s2"),
            Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", "s4"),
            Edge("s4", "u2", style="dashed"),
            Edge("s1", "p1", style="dashed"), Edge("s3", "p1"),
            Edge("s4", "p2"), Edge("s2", "p2", style="dashed"),
            Edge("p1", "i1"), Edge("p1", "i2"),
            Edge("p2", "i3"), Edge("i2", "s4", style="dashed"),
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
    print("M1 demo 完成: 2 张示例图")
