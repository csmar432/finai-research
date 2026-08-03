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


# Node type constants for process_flow (M3)
NODE_PROCESS = "process"     # 默认矩形
NODE_DECISION = "decision"   # 菱形
NODE_START = "start"         # 圆角胶囊
NODE_END = "end"             # 圆角胶囊
NODE_SUBPROCESS = "subprocess"  # 带双竖线边框
NODE_DATA = "data"           # 平行四边形（用普通矩形近似）


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
    node_type: str = "process"  # M3: process/decision/start/end/subprocess/data
    x: float | None = None    # 手动坐标（None 时自动布局）
    y: float | None = None
    branch: str | None = None  # M3: 分支标识（"yes"/"no"/"a"/"b"），用于横向错开


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


def _draw_node_shape(ax, node: Node, nw: float, nh: float):
    """根据 node_type 画不同形状"""
    if node.node_type == NODE_DECISION:
        # 菱形
        cx, cy = node.x, node.y
        diamond = plt.Polygon(
            [(cx, cy + nh / 2), (cx + nw / 2, cy),
             (cx, cy - nh / 2), (cx - nw / 2, cy)],
            facecolor=spec_bg_color(ax), edgecolor=node.color, linewidth=2.0, zorder=3,
        )
        ax.add_patch(diamond)
        # 中心填色
        diamond.set_facecolor("#0F1F33")
    elif node.node_type in (NODE_START, NODE_END):
        # 胶囊形（高度更大，圆角极大）
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor=node.color, edgecolor=node.color, lw=2.0, radius=nh / 2, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=10, color="#FFFFFF",
                ha="center", va="center", fontweight="bold", zorder=4)
        return
    elif node.node_type == NODE_SUBPROCESS:
        # 双竖线边框的矩形
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor="#0F1F33", edgecolor=node.color, lw=2.0, radius=0.4, zorder=3)
        # 左/右双竖线
        for dx in (-nw / 2 + 0.5, nw / 2 - 0.5):
            ax.plot([node.x + dx, node.x + dx],
                    [node.y - nh / 2 + 0.3, node.y + nh / 2 - 0.3],
                    color=node.color, linewidth=1.2, zorder=4)
    else:
        # 默认矩形（process/data）
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor="#0F1F33", edgecolor=node.color, lw=2.0, zorder=3)
    # 标签（除 start/end 已在上面写过）
    if node.node_type not in (NODE_START, NODE_END):
        ax.text(node.x, node.y, node.label, fontsize=9,
                color="#E8EEF6", ha="center", va="center", zorder=4)
    # icon
    if node.icon:
        if node.node_type == NODE_DECISION:
            # 菱形 icon 放菱形外右上角
            ix, iy = node.x + nw / 2 + 1.5, node.y + nh / 2 + 1.5
        elif node.node_type in (NODE_START, NODE_END):
            ix, iy = node.x - nw / 2 + 1.6, node.y + nh / 2 - 1.6
        else:
            ix, iy = node.x - nw / 2 + 1.6, node.y + nh / 2 - 1.6
        ax.add_patch(Circle((ix, iy), 1.2, color=node.color, zorder=5))
        ax.text(ix, iy, node.icon, fontsize=8, color="#0A1929",
                ha="center", va="center", fontweight="bold", zorder=6)


def spec_bg_color(ax) -> str:
    """获取当前 fig 的背景色（用于菱形填充）"""
    return ax.figure.get_facecolor() if hasattr(ax, "figure") else "#0A1929"


def process_flow(spec: DiagramSpec) -> None:
    """业务流程图
    M3 完整功能:
      - 节点类型: process / decision(菱形) / start / end(胶囊) / subprocess(双竖线)
      - 分支: 节点带 branch 字段，自动横向错开
      - 多线型箭头 + 边标签
      - 子流程嵌套（subprocess 节点 + 后续 nodes 缩进）
    """
    fig, ax = plt.subplots(figsize=(11, 13), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 自动布局: 按 nodes 顺序排列，根据 branch 横向错开
    n = len(spec.nodes)
    if n == 0:
        return

    # 决策节点后立即分支: 遇到 decision 后所有 nodes 按 branch 分组
    # 主列 x=spec.width/2, 分支 x=主列±offset
    main_x = spec.width / 2
    branch_offset = spec.width * 0.18

    # 先按出现顺序分配 y（主时间轴）
    spacing = (spec.height - 12) / max(n, 1)
    box_w, box_h = 26.0, spacing - 1.5

    branch_stack: dict[str, float] = {}  # branch -> x offset 计数
    for i, node in enumerate(spec.nodes):
        node.y = spec.height - 6 - (i + 0.5) * spacing
        if node.branch is None:
            node.x = main_x
        else:
            # 同 branch 沿用相同 x, 新 branch 在另一侧
            if node.branch in branch_stack:
                node.x = main_x + branch_stack[node.branch]
            else:
                # 交替 yes/no, a/b
                if not branch_stack:
                    node.x = main_x + branch_offset
                else:
                    # 取已有 branch 的反方向
                    xs = list(branch_stack.values())
                    if all(x > 0 for x in xs):
                        node.x = main_x - branch_offset
                    else:
                        node.x = main_x + branch_offset
                branch_stack[node.branch] = node.x - main_x

    # 节点
    for node in spec.nodes:
        if node.node_type == NODE_DECISION:
            nw, nh = box_w * 0.7, box_h
        elif node.node_type in (NODE_START, NODE_END):
            nw, nh = box_w * 0.6, box_h
        else:
            nw, nh = box_w, box_h
        _draw_node_shape(ax, node, nw, nh)

    # 连线（端点: process 用上下沿，decision 用四个角）
    by_id = {n.id: n for n in spec.nodes}
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        src, dst = by_id[e.src], by_id[e.dst]
        # 端点选择
        x1, y1 = _pick_endpoint(src, dst, "src")
        x2, y2 = _pick_endpoint(dst, src, "dst")
        style = "-|>" if e.arrow == "->" else ("<|-" if e.arrow == "<-" else "<|-|>")
        _arrow(ax, x1, y1, x2, y2, color=e.color, lw=1.6, style=style, ls=e.style)
        # 边标签（决策标签如 yes/no）
        if e.label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(
                mx, my, e.label, fontsize=8, color=node_color_for(e.color),
                ha="center", va="center", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc=spec.bg_color,
                          ec=e.color, lw=0.8),
                zorder=5,
            )

    ax.text(
        spec.width / 2, spec.height - 4, spec.title,
        fontsize=18, color="#2DD4BF", ha="center", fontweight="bold",
    )

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def _pick_endpoint(node: Node, other: Node, role: str) -> tuple[float, float]:
    """根据节点类型和方向选端点"""
    dx = other.x - node.x
    dy = other.y - node.y
    nw, nh = 13.0, 4.5  # 平均尺寸估算
    if node.node_type == NODE_DECISION:
        # 菱形：从四个角出发
        if abs(dx) > abs(dy):
            x = node.x + (nw * 0.35 if dx > 0 else -nw * 0.35)
            y = node.y + dy * (nw * 0.35) / max(abs(dx), 0.1)
        else:
            x = node.x + dx * (nh * 0.5) / max(abs(dy), 0.1)
            y = node.y + (nh * 0.5 if dy > 0 else -nh * 0.5)
        return x, y
    elif node.node_type in (NODE_START, NODE_END):
        nw, nh = 16.0, 4.5
        x = node.x + (nw / 2 if dx > 0 else -nw / 2 if dx < 0 else 0)
        y = node.y + (nh / 2 if dy > 0 else -nh / 2 if dy < 0 else 0)
        return x, y
    else:
        # 普通矩形: 上下沿
        if abs(dy) > abs(dx):
            y = node.y + (nh / 2 if dy > 0 else -nh / 2)
            x = node.x
        else:
            x = node.x + (nw / 2 if dx > 0 else -nw / 2)
            y = node.y
        return x, y


def node_color_for(c: str) -> str:
    """边标签颜色（亮化背景色上的可读性）"""
    return "#E8EEF6" if c.lower() in ("#0a1929", "#0f1f33", "#16273d", "#1b3355") else c


def hierarchy_tree(spec: DiagramSpec, style: str = "tree") -> None:
    """层次结构图
    M4 完整功能:
      style="tree": 标准树状（父节点居中，子节点均匀排列）
      style="consort": CONSORT 流程图（根→两臂→逐级 drop-out/排除）
      style="org": 组织架构图（顶层居中，逐层扩展）
    """
    if style == "consort":
        _hierarchy_consort(spec)
    elif style == "org":
        _hierarchy_org(spec)
    else:
        _hierarchy_tree_default(spec)


def _hierarchy_tree_default(spec: DiagramSpec) -> None:
    """标准树状层次图（M1 版升级: 任意父子边，自动按层归类）"""
    fig, ax = plt.subplots(figsize=(13, 8), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 拓扑层级: BFS 从入度为 0 的节点开始
    in_degree = {n.id: 0 for n in spec.nodes}
    children: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    roots: list[str] = []
    for e in spec.edges:
        if e.src in children and e.dst in children:
            children[e.src].append(e.dst)
            in_degree[e.dst] += 1
    for n in spec.nodes:
        if in_degree[n.id] == 0:
            roots.append(n.id)

    # BFS 算层
    layer_of: dict[str, int] = {}
    queue: list[tuple[str, int]] = [(r, 0) for r in roots]
    while queue:
        node_id, lvl = queue.pop(0)
        layer_of[node_id] = lvl
        for c in children[node_id]:
            queue.append((c, lvl + 1))

    # 按层分组
    by_layer: dict[int, list[Node]] = {}
    for n in spec.nodes:
        lvl = layer_of.get(n.id, 0)
        by_layer.setdefault(lvl, []).append(n)

    n_levels = max(by_layer.keys()) + 1 if by_layer else 1
    spacing = (spec.height - 12) / max(n_levels, 1)

    # 自动布局: 每层节点均匀排列
    for lvl in sorted(by_layer.keys()):
        nodes = by_layer[lvl]
        m = len(nodes)
        box_w = min(20.0, (spec.width - 10) / m - 2.0)
        total_w = m * box_w + max(m - 1, 0) * 4
        x_start = (spec.width - total_w) / 2 + box_w / 2
        for ni, node in enumerate(nodes):
            node.x = x_start + ni * (box_w + 4)
            node.y = spec.height - 6 - (lvl + 0.5) * spacing

    # 节点
    for node in spec.nodes:
        box_w = 18.0
        box_h = spacing - 2.0
        _box(ax, node.x - box_w / 2, node.y - box_h / 2, box_w, box_h,
             facecolor="#0F1F33", edgecolor=node.color, lw=2.0, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=9,
                color="#E8EEF6", ha="center", va="center", zorder=4)

    # 连线: 父子连线，从父底中央 → 子顶中央
    by_id = {n.id: (n.x, n.y) for n in spec.nodes}
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        x1, y1 = by_id[e.src]
        x2, y2 = by_id[e.dst]
        _arrow(ax, x1, y1 - 3, x2, y2 + 3, color=e.color, lw=1.6, ls=e.style)

    # 层标签
    for lvl in sorted(by_layer.keys()):
        ax.text(2, spec.height - 6 - (lvl + 0.5) * spacing, f"L{lvl}",
                fontsize=10, color="#8FA3B8", va="center", fontweight="bold")

    ax.text(spec.width / 2, spec.height - 4, spec.title,
            fontsize=18, color="#2DD4BF", ha="center", fontweight="bold")

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def _hierarchy_consort(spec: DiagramSpec) -> None:
    """CONSORT 流程图（干预组 vs 对照组，左右两臂）"""
    fig, ax = plt.subplots(figsize=(14, 9), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # CONSORT 假设: 第 1 层是入组总样本（居中）
    # 第 2 层: 左臂（干预）/右臂（对照）
    # 第 3 层: 各臂下：分析样本 / 排除原因
    by_layer: dict[int, list[Node]] = {}
    for n in spec.nodes:
        by_layer.setdefault(n.layer, []).append(n)

    layers_sorted = sorted(by_layer.keys())
    n_levels = len(layers_sorted)
    spacing = (spec.height - 14) / max(n_levels, 1)

    # 第 1 层（入组）: 居中
    if 0 in by_layer:
        n0 = by_layer[0][0]
        n0.x = spec.width / 2
        n0.y = spec.height - 6 - 0.5 * spacing

    # 第 2 层（随机分组）: 居中一个节点 + 左干预 / 右对照
    if 1 in by_layer:
        arm_x_left = spec.width * 0.25
        arm_x_right = spec.width * 0.75
        # 找到 column="left"/"right" 的节点，剩余居中
        left_candidates = [n for n in by_layer[1] if n.column == "left"]
        right_candidates = [n for n in by_layer[1] if n.column == "right"]
        center_candidates = [n for n in by_layer[1]
                             if n.column not in ("left", "right")]
        for n in left_candidates:
            n.x = arm_x_left
            n.y = spec.height - 6 - 1.5 * spacing
        for n in right_candidates:
            n.x = arm_x_right
            n.y = spec.height - 6 - 1.5 * spacing
        for n in center_candidates:
            n.x = spec.width / 2
            n.y = spec.height - 6 - 1.5 * spacing

    # 第 3 层起（分析/排除）: 各自居中于左右两臂
    for lvl in layers_sorted[2:]:
        if 1 in by_layer and len(by_layer[1]) >= 2:
            parent_x_left = by_layer[1][0].x
            parent_x_right = by_layer[1][1].x
        else:
            parent_x_left = spec.width * 0.25
            parent_x_right = spec.width * 0.75
        nodes = by_layer[lvl]
        # 按 layer/column 字段分组到左右臂
        left_nodes = [n for n in nodes if n.column != "right"]
        right_nodes = [n for n in nodes if n.column == "right"]
        # 若未指定 column，按数量均分
        if not right_nodes and left_nodes and len(left_nodes) > len(nodes) / 2:
            half = len(nodes) // 2
            left_nodes = nodes[:half]
            right_nodes = nodes[half:]
        for node in left_nodes:
            node.x = parent_x_left
            node.y = spec.height - 6 - (lvl + 0.5) * spacing
        for node in right_nodes:
            node.x = parent_x_right
            node.y = spec.height - 6 - (lvl + 0.5) * spacing

    # 节点绘制
    for node in spec.nodes:
        nw = 26.0
        nh = spacing - 2.5
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor="#0F1F33", edgecolor=node.color, lw=2.2, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=9,
                color="#E8EEF6", ha="center", va="center", zorder=4)

    # 连线: 父子 + 横线 drop-out
    by_id = {n.id: (n.x, n.y) for n in spec.nodes}
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            continue
        x1, y1 = by_id[e.src]
        x2, y2 = by_id[e.dst]
        _arrow(ax, x1, y1 - 3, x2, y2 + 3, color=e.color, lw=1.6, ls=e.style)

    # 臂标签
    if 1 in by_layer and len(by_layer[1]) >= 2:
        for node in by_layer[1][:2]:
            lbl = "干预组" if node.x < spec.width / 2 else "对照组"
            ax.text(node.x, node.y + spacing / 2 + 1, lbl,
                    fontsize=11, color=node.color, ha="center",
                    fontweight="bold")

    ax.text(spec.width / 2, spec.height - 4, spec.title,
            fontsize=18, color="#2DD4BF", ha="center", fontweight="bold")

    fig.savefig(spec.output_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def _hierarchy_org(spec: DiagramSpec) -> None:
    """组织架构图（顶层居中，逐层扩展，子节点均匀分布）"""
    fig, ax = plt.subplots(figsize=(14, 8.5), dpi=200)
    fig.patch.set_facecolor(spec.bg_color)
    _clean(ax, spec.width, spec.height)

    # 拓扑层级
    in_degree = {n.id: 0 for n in spec.nodes}
    children: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    roots: list[str] = []
    for e in spec.edges:
        if e.src in children and e.dst in children:
            children[e.src].append(e.dst)
            in_degree[e.dst] += 1
    for n in spec.nodes:
        if in_degree[n.id] == 0:
            roots.append(n.id)

    layer_of: dict[str, int] = {}
    queue: list[tuple[str, int]] = [(r, 0) for r in roots]
    while queue:
        node_id, lvl = queue.pop(0)
        layer_of[node_id] = lvl
        for c in children[node_id]:
            queue.append((c, lvl + 1))

    by_layer: dict[int, list[Node]] = {}
    for n in spec.nodes:
        lvl = layer_of.get(n.id, 0)
        by_layer.setdefault(lvl, []).append(n)

    n_levels = max(by_layer.keys()) + 1 if by_layer else 1
    spacing = (spec.height - 12) / max(n_levels, 1)

    # 顶层居中单节点（若是 org chart 第 0 层应有 1 个 CEO）
    for lvl in sorted(by_layer.keys()):
        nodes = by_layer[lvl]
        m = len(nodes)
        nw = min(22.0, (spec.width - 10) / m - 2.0)
        total_w = m * nw + max(m - 1, 0) * 3
        x_start = (spec.width - total_w) / 2 + nw / 2
        for ni, node in enumerate(nodes):
            node.x = x_start + ni * (nw + 3)
            node.y = spec.height - 6 - (lvl + 0.5) * spacing

    # 节点绘制
    for node in spec.nodes:
        nw = 20.0
        nh = spacing - 2.5
        _box(ax, node.x - nw / 2, node.y - nh / 2, nw, nh,
             facecolor="#0F1F33", edgecolor=node.color, lw=2.0, zorder=3)
        ax.text(node.x, node.y, node.label, fontsize=10,
                color="#E8EEF6", ha="center", va="center",
                fontweight="bold", zorder=4)

    # 连线: 父子线，含中间竖线+横线（org chart 风格）
    by_id = {n.id: (n.x, n.y) for n in spec.nodes}
    # 先按父分组
    by_parent: dict[str, list[str]] = {}
    for e in spec.edges:
        if e.src in by_id and e.dst in by_id:
            by_parent.setdefault(e.src, []).append(e.dst)

    for parent_id, child_ids in by_parent.items():
        if parent_id not in by_id:
            continue
        px, py = by_id[parent_id]
        child_xs = [by_id[c][0] for c in child_ids if c in by_id]
        if not child_xs:
            continue
        # 父节点底部 → 父节点下方水平线
        h_line_y = py - 3
        ax.plot([px, px], [h_line_y, h_line_y - 1],
                color="#8FA3B8", linewidth=1.4, zorder=2)
        # 水平线
        ax.plot([min(child_xs), max(child_xs)], [h_line_y - 1, h_line_y - 1],
                color="#8FA3B8", linewidth=1.4, zorder=2)
        # 每个子节点垂直连线
        for c in child_ids:
            if c not in by_id:
                continue
            cx, cy = by_id[c]
            ax.plot([cx, cx], [h_line_y - 1, cy + 3],
                    color="#8FA3B8", linewidth=1.4, zorder=2)
            # 箭头
            ax.add_patch(FancyArrowPatch(
                (cx, cy + 3), (cx, cy + 3.1),
                arrowstyle="-|>", mutation_scale=10,
                color="#8FA3B8", linewidth=1.4, zorder=3,
            ))

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


def _demo_consort() -> str:
    """Demo 4: M4 CONSORT 流程图（干预/对照 + drop-out）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_consort.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="样本筛选与分组 CONSORT 流程图（M4 demo）",
        width=100, height=80,
        output_path=out,
        nodes=[
            Node("enroll", "入组总样本\nN = 5,820",
                 layer=0, color="#2DD4BF"),
            Node("rand", "随机分组", layer=1, color="#A78BFA"),
            Node("trt", "干预组\nn = 2,910",
                 layer=1, column="left", color="#34D399"),
            Node("ctl", "对照组\nn = 2,910",
                 layer=1, column="right", color="#FB923C"),
            Node("trt_ex", "排除：\n数据缺失 (n=128)\n非A股 (n=42)",
                 layer=2, column="left", color="#F87171"),
            Node("trt_an", "分析样本\nn = 2,740",
                 layer=2, column="left", color="#34D399"),
            Node("ctl_ex", "排除：\n数据缺失 (n=131)\n非A股 (n=39)",
                 layer=2, column="right", color="#F87171"),
            Node("ctl_an", "分析样本\nn = 2,740",
                 layer=2, column="right", color="#34D399"),
        ],
        edges=[
            Edge("enroll", "rand"),
            Edge("rand", "trt"), Edge("rand", "ctl"),
            Edge("trt", "trt_ex"), Edge("trt", "trt_an"),
            Edge("ctl", "ctl_ex"), Edge("ctl", "ctl_an"),
        ],
    )
    hierarchy_tree(spec, style="consort")
    return out


def _demo_org_chart() -> str:
    """Demo 5: M4 组织架构图（树状 + 中间横线）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_org_chart.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="FinResearch Agent · 模块组织架构（M4 demo）",
        width=100, height=80,
        output_path=out,
        nodes=[
            Node("root", "FinResearch Agent", color="#F5B700"),
            Node("core", "Core Layer\n87 modules", color="#2DD4BF"),
            Node("rf", "Research Framework\n47 methods", color="#34D399"),
            Node("mcp", "MCP ×43", color="#A78BFA"),
            Node("lit", "Literature Pipeline", color="#38BDF8"),
            Node("data", "Data Fetcher", color="#FB923C"),
            Node("paper", "Paper Generator", color="#F472B6"),
            Node("skill", "Skill Registry\n17 skills", color="#A78BFA"),
            Node("hl", "HitL Checkpoint", color="#FBBF24"),
        ],
        edges=[
            Edge("root", "core"), Edge("root", "rf"), Edge("root", "mcp"),
            Edge("core", "skill"), Edge("core", "hl"),
            Edge("rf", "lit"), Edge("rf", "data"), Edge("rf", "paper"),
        ],
    )
    hierarchy_tree(spec, style="org")
    return out


def _demo_process_flow() -> str:
    """Demo 3: M3 业务流程图（含决策菱形/分支）"""
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/output/figures/demo_process_flow.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    spec = DiagramSpec(
        title="文献检索流程（含决策菱形与分支，M3 demo）",
        width=100, height=80,
        output_path=out,
        nodes=[
            Node("start", "开始检索", node_type=NODE_START, color="#34D399", icon="S"),
            Node("q", "输入研究主题", color="#38BDF8", icon="1"),
            Node("fetch", "调用 MCP\n多源检索", color="#A78BFA", icon="2"),
            Node("enough", "文献数 ≥ 30?", node_type=NODE_DECISION,
                 color="#FBBF24", icon="?"),
            Node("aug", "扩展检索词\n补充检索", color="#FB923C", icon="3", branch="no"),
            Node("dedup", "去重 + 排序", color="#F472B6", icon="4"),
            Node("cite", "构建引文网络", color="#2DD4BF", icon="5"),
            Node("save", "保存至\nLIT_REVIEW.md", color="#10B981", icon="6"),
            Node("end", "完成", node_type=NODE_END, color="#F87171", icon="E"),
        ],
        edges=[
            Edge("start", "q"),
            Edge("q", "fetch"),
            Edge("fetch", "enough"),
            Edge("enough", "dedup", label="yes", color="#34D399"),
            Edge("enough", "aug", label="no", color="#F87171"),
            Edge("aug", "fetch", style="dashed"),
            Edge("dedup", "cite"),
            Edge("cite", "save"),
            Edge("save", "end"),
        ],
    )
    process_flow(spec)
    return out


if __name__ == "__main__":
    p1 = _demo_finresearch_arch()
    p2 = _demo_pipeline_hierarchy()
    p3 = _demo_process_flow()
    p4 = _demo_consort()
    p5 = _demo_org_chart()
    print(f"[OK] {p1}")
    print(f"[OK] {p2}")
    print(f"[OK] {p3}")
    print(f"[OK] {p4}")
    print(f"[OK] {p5}")
    print("M4 demo 完成: 5 张示例图")
    print("  - swim_lane (M2)")
    print("  - hierarchy_tree default (M4 升级: 任意父子边)")
    print("  - process_flow (M3)")
    print("  - hierarchy_tree consort (M4)")
    print("  - hierarchy_tree org (M4)")
