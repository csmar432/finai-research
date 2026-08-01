"""
arch_diagram_gv.py — Graphviz 后端的架构/流程/层次图生成器

设计目标：
  - 输出风格接近 draw.io / Lucidchart 风格（浅色 + 彩色填充 + 圆角胶囊）
  - 与 arch_diagram.py（matplotlib 后端）共用同一 DiagramSpec 数据驱动 API
  - 跨平台：依赖系统 graphviz（macOS brew / Linux apt / Windows choco）
  - 自动 fallback：当 graphviz 不可用时返回警告，调用方应捕获并使用 matplotlib 后端

DOT 特性使用：
  - rankdir="LR" 横向布局
  - subgraph cluster_X 分层 / 泳道
  - HTML 标签实现彩色卡片 + 图标替身（Unicode 符号）
  - 多边样式：实线 / 虚线 / 点线 / 反向

限制：
  - 图标只能做到 Unicode 符号级别（机器人 🤖、文档 📄、齿轮 ⚙️）
  - 自动布局由 graphviz 控制，无法精确像素级控制
  - 中文需 fontname 配置（CJK 字体名）
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Optional

_log = logging.getLogger("arch_diagram_gv")
_log.setLevel(logging.INFO)


# ── 依赖检查 + fallback 警告 ────────────────────────────────────────────────


def _check_graphviz() -> Optional[str]:
    """检查系统是否安装了 graphviz (dot 命令)。返回 dot 路径或 None。"""
    dot = shutil.which("dot")
    if dot:
        return dot
    _log.warning(
        "graphviz (dot) 未在 PATH 中找到。请安装：\n"
        "  macOS:  brew install graphviz\n"
        "  Linux:  sudo apt install graphviz\n"
        "  Win:    choco install graphviz"
    )
    return None


def _check_python_pkg() -> bool:
    """检查 graphviz Python 包是否安装。"""
    try:
        import graphviz  # noqa: F401
        return True
    except ImportError:
        _log.warning(
            "graphviz Python 包未安装。请运行：pip install graphviz"
        )
        return False


def graphviz_available() -> bool:
    """对外接口：graphviz 是否可用。"""
    return _check_graphviz() is not None and _check_python_pkg()


# ── 配色方案（浅色 + 彩色填充，参考图风格）───────────────────────────────────

# 浅色背景 + 高饱和填充框，模仿 draw.io 风格
THEME_LIGHT = {
    "bg": "#FFFFFF",
    "user": ("#FDEBD0", "#F39C12", "#D68910"),       # 橙
    "skills": ("#D6EAF8", "#3498DB", "#21618C"),     # 蓝
    "persist": ("#EBDEF0", "#8E44AD", "#6C3483"),    # 紫
    "infra": ("#D5F5E3", "#27AE60", "#1E8449"),      # 绿
    "edge_main": "#5D6D7E",        # 主流程 灰
    "edge_invoke": "#E74C3C",      # 调用  红
    "edge_loop": "#F1C40F",        # 循环  黄
    "edge_data": "#2980B9",        # 数据  蓝
    "font": "Helvetica",
    "font_cn": "Hiragino Sans GB",  # macOS CJK
}


def _palette_for_color(hex_color: str, theme: dict = THEME_LIGHT) -> str:
    """简化: 直接返回节点颜色，让 graphviz 处理配色"""
    return hex_color


# ── DOT 生成器 ──────────────────────────────────────────────────────────────


def _import_graphviz():
    """延迟导入 graphviz，便于 fallback"""
    try:
        import graphviz
        return graphviz
    except ImportError:
        return None


def _make_digraph(name: str, theme: dict = THEME_LIGHT):
    """创建带统一样式的 Digraph"""
    gv = _import_graphviz()
    if gv is None:
        raise RuntimeError("graphviz Python 包未安装")
    g = gv.Digraph(name=name, format="png")
    g.attr(
        rankdir="LR",
        bgcolor=theme["bg"],
        pad="0.5",
        nodesep="0.4",
        ranksep="0.8",
        splines="spline",
        compound="true",
    )
    g.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname=theme["font"],
        fontsize="10",
        margin="0.15,0.08",
        color="#2C3E50",
        penwidth="1.0",
    )
    g.attr(
        "edge",
        color=theme["edge_main"],
        arrowsize="0.7",
        fontname=theme["font"],
        fontsize="9",
        penwidth="1.2",
    )
    return g


def _node_icon(node) -> str:
    """节点 icon Unicode 符号"""
    icon_map = {
        "U": "👤",      # user
        "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤",  # 数字编号
        "?": "❓",       # decision
        "S": "▶",       # start
        "E": "■",       # end
        "K": "📚",       # knowledge
        "D": "💾",       # data
        "P": "📋",       # provenance
        "B": "📖",       # bibtex
        "M": "🔌",       # MCP
        "L": "🧠",       # LLM
    }
    if node.icon in icon_map:
        return icon_map[node.icon]
    # 默认根据 node_type 选
    type_map = {
        "decision": "❓",
        "start": "▶",
        "end": "■",
        "subprocess": "⊕",
        "data": "💾",
    }
    return type_map.get(node.node_type, "")


def _hex_to_light(hex_color: str, alpha: float = 0.3) -> str:
    """根据 hex 颜色生成浅色填充版（用于卡片 fillcolor）
    简化: 直接用 hex + 透明，但 graphviz 不支持 alpha，统一返回原色稍降饱和
    """
    # 简单实现: 返回原色 (graphviz fillcolor 不支持 alpha)
    # 在 draw 时通过 fontcolor 区分
    return hex_color


# ── swim_lane 横向布局版 ────────────────────────────────────────────────────


def swim_lane_gv(spec, output_path: str, theme: dict = THEME_LIGHT) -> str:
    """swim_lane 架构图 — graphviz 后端（横向布局 + 浅色风格）

    输入: 现有 DiagramSpec（兼容 arch_diagram.py 的数据类）
    输出: PNG 文件路径
    """
    gv = _import_graphviz()
    if gv is None:
        raise RuntimeError("graphviz Python 包未安装")

    # 横向布局：左→右
    g = gv.Digraph(name="swim_lane", format="png")
    g.attr(
        rankdir="LR",
        bgcolor=theme["bg"],
        pad="0.5",
        nodesep="0.35",
        ranksep="0.6",
        compound="true",
        splines="spline",
    )
    g.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname=theme["font"],
        fontsize="10",
        margin="0.18,0.10",
        color="#2C3E50",
        penwidth="1.2",
    )
    g.attr(
        "edge",
        color=theme["edge_main"],
        arrowsize="0.8",
        fontname=theme["font"],
        fontsize="9",
        penwidth="1.4",
    )

    # 为每个 layer 创建 cluster
    layers_in_spec = [(l.name, l) for l in spec.layers]
    if not layers_in_spec:
        # 默认 4 层
        layers_in_spec = [
            ("USER", ("#FDEBD0", "#F39C12", "#D68910")),
            ("SKILLS", ("#D6EAF8", "#3498DB", "#21618C")),
            ("PERSISTENCE", ("#EBDEF0", "#8E44AD", "#6C3483")),
            ("INFRASTRUCTURE", ("#D5F5E3", "#27AE60", "#1E8449")),
        ]

    for layer_name, layer in layers_in_spec:
        if isinstance(layer, tuple):
            fill, border, font = layer
        else:
            fill, border, font = (
                layer.color,
                layer.color,
                layer.text_color if hasattr(layer, "text_color") else "#2C3E50",
            )
        cluster_name = f"cluster_{layer_name.lower().replace(' ', '_')}"
        with g.subgraph(name=cluster_name) as c:
            c.attr(
                label=layer_name,
                style="filled,rounded",
                fillcolor=fill,
                color=border,
                fontcolor=font,
                fontname=theme["font"] + "-Bold",
                fontsize="12",
                margin="12",
                penwidth="1.5",
            )
            # 在 cluster 内放节点（用 column 分泳道）
            cols: dict[str, list] = {}
            for n in spec.nodes:
                if (hasattr(n, "layer") and n.layer == layer_name) or (
                    not hasattr(n, "layer") or not n.layer
                ):
                    col_key = getattr(n, "column", "") or "main"
                    cols.setdefault(col_key, []).append(n)

            for col_key, ns in cols.items():
                if len(cols) > 1 and col_key != "main":
                    sub_name = f"{cluster_name}_{col_key}"
                    with c.subgraph(name=sub_name) as sc:
                        sc.attr(
                            label=col_key,
                            style="dashed,rounded",
                            color=border,
                            fontcolor=font,
                            fontname=theme["font"],
                            fontsize="10",
                            margin="8",
                        )
                        for n in ns:
                            _add_node_html(sc, n, theme)
                else:
                    for n in ns:
                        _add_node_html(c, n, theme)

    # Edges
    edge_color_map = {
        "solid": (theme["edge_main"], None),
        "dashed": (theme["edge_main"], "dashed"),
        "dotted": (theme["edge_main"], "dotted"),
        "invoke": (theme["edge_invoke"], "dashed"),
        "loop": (theme["edge_loop"], "dashed"),
        "data": (theme["edge_data"], None),
    }
    for e in spec.edges:
        color, style = edge_color_map.get(e.style, edge_color_map["solid"])
        if e.color and e.color.startswith("#"):
            color = e.color
        attrs = {"color": color, "label": e.label} if e.label else {"color": color}
        if style:
            attrs["style"] = style
        if e.arrow == "<-":
            attrs["dir"] = "back"
        elif e.arrow == "<->":
            attrs["dir"] = "both"
        try:
            g.edge(e.src, e.dst, **attrs)
        except Exception as ex:
            _log.warning(f"边 {e.src}->{e.dst} 跳过: {ex}")

    return _render(g, output_path, name="swim_lane")


def _add_node_html(cluster, node, theme: dict):
    """添加节点（用 HTML 标签实现彩色卡片 + icon + label 多行）"""
    icon = _node_icon(node)
    label_html = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">'
    label_html += f'<TR><TD ALIGN="CENTER">{icon}</TD></TR>' if icon else ""
    label_html += f'<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="10">{node.label}</FONT></TD></TR>'
    label_html += "</TABLE>>"

    # 填充: 浅色填充 = 原色但用 white 背景 + 彩色边框（更接近参考图）
    fillcolor = "white"
    border = node.color if node.color else "#3498DB"
    fontcolor = "#2C3E50"

    try:
        cluster.node(
            node.id,
            label=label_html,
            fillcolor=fillcolor,
            color=border,
            fontcolor=fontcolor,
        )
    except Exception as ex:
        _log.warning(f"节点 {node.id} 渲染失败: {ex}")


# ── process_flow 流程图 ──────────────────────────────────────────────────────


def process_flow_gv(spec, output_path: str, theme: dict = THEME_LIGHT) -> str:
    """process_flow 流程图 — graphviz 后端

    支持节点类型:
      - process:    默认矩形
      - decision:   菱形 (diamond)
      - start/end:  椭圆 (ellipse)
      - subprocess: note 形状（带下划线）
    """
    gv = _import_graphviz()
    if gv is None:
        raise RuntimeError("graphviz Python 包未安装")

    g = gv.Digraph(name="process_flow", format="png")
    g.attr(
        rankdir="TB",
        bgcolor=theme["bg"],
        pad="0.5",
        nodesep="0.4",
        ranksep="0.6",
    )
    g.attr(
        "node",
        fontname=theme["font"],
        fontsize="10",
        margin="0.15,0.10",
        penwidth="1.2",
    )
    g.attr(
        "edge",
        color=theme["edge_main"],
        arrowsize="0.8",
        fontname=theme["font"],
        fontsize="9",
        penwidth="1.4",
    )

    # 节点形状映射
    shape_map = {
        "process": "box",
        "decision": "diamond",
        "start": "ellipse",
        "end": "ellipse",
        "subprocess": "note",
        "data": "parallelogram",
    }
    style_map = {
        "process": "filled,rounded",
        "decision": "filled",
        "start": "filled",
        "end": "filled",
        "subprocess": "filled",
        "data": "filled",
    }
    for n in spec.nodes:
        nt = getattr(n, "node_type", "process") or "process"
        shape = shape_map.get(nt, "box")
        style = style_map.get(nt, "filled,rounded")
        fillcolor = n.color if n.color else "#3498DB"
        fontcolor = "white" if nt in ("start", "end") else "#2C3E50"

        # 用 HTML 标签让节点支持多行 + icon
        icon = _node_icon(n)
        # HTML 转义: graphviz HTML 标签里 > < & 需要转义
        def _esc(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        label_html = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">'
        if icon:
            label_html += f'<TR><TD ALIGN="CENTER">{icon}</TD></TR>'
        for line in n.label.split("\n"):
            label_html += f'<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="10">{_esc(line)}</FONT></TD></TR>'
        label_html += "</TABLE>>"

        try:
            g.node(
                n.id,
                label=label_html,
                shape=shape,
                style=style,
                fillcolor=fillcolor,
                fontcolor=fontcolor,
                color="#2C3E50",
            )
        except Exception as ex:
            _log.warning(f"节点 {n.id} 渲染失败: {ex}")

    # Edges（带分支偏移以避免重叠）
    edge_color_map = {
        "solid": (theme["edge_main"], None),
        "dashed": (theme["edge_main"], "dashed"),
        "dotted": (theme["edge_main"], "dotted"),
        "invoke": (theme["edge_invoke"], "dashed"),
        "loop": (theme["edge_loop"], "dashed"),
        "data": (theme["edge_data"], None),
    }
    for e in spec.edges:
        color, style = edge_color_map.get(e.style, edge_color_map["solid"])
        if e.color and e.color.startswith("#"):
            color = e.color
        attrs = {}
        if e.label:
            attrs["label"] = e.label
            attrs["fontcolor"] = color
        attrs["color"] = color
        if style:
            attrs["style"] = style
        if e.arrow == "<-":
            attrs["dir"] = "back"
        elif e.arrow == "<->":
            attrs["dir"] = "both"
        try:
            g.edge(e.src, e.dst, **attrs)
        except Exception as ex:
            _log.warning(f"边 {e.src}->{e.dst} 跳过: {ex}")

    return _render(g, output_path, name="process_flow")


# ── hierarchy_tree 三种风格 ──────────────────────────────────────────────────


def hierarchy_tree_gv(spec, output_path: str, style: str = "tree",
                       theme: dict = THEME_LIGHT) -> str:
    """hierarchy_tree — graphviz 后端

    style:
      - "tree":    横向树状
      - "consort": 双向臂（CONSORT 流程图风格）
      - "org":     垂直组织架构
    """
    gv = _import_graphviz()
    if gv is None:
        raise RuntimeError("graphviz Python 包未安装")

    g = gv.Digraph(name=f"hierarchy_{style}", format="png")
    if style == "org":
        g.attr(rankdir="TB", bgcolor=theme["bg"], nodesep="0.25",
               ranksep="0.5")
    elif style == "consort":
        g.attr(rankdir="TB", bgcolor=theme["bg"], nodesep="0.4",
               ranksep="0.6")
    else:
        g.attr(rankdir="LR", bgcolor=theme["bg"], nodesep="0.3",
               ranksep="0.6")
    g.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname=theme["font"],
        fontsize="10",
        margin="0.15,0.08",
        penwidth="1.2",
        fillcolor="white",
        color="#3498DB",
    )
    g.attr(
        "edge",
        color="#5D6D7E",
        arrowsize="0.7",
        fontname=theme["font"],
        fontsize="9",
        penwidth="1.0",
    )

    # 节点：HTML 标签
    for n in spec.nodes:
        fillcolor = "white"
        border = n.color if n.color else "#3498DB"
        label_html = f'<{{{"<BR/>".join(n.label.split(chr(10)))}>}}'
        try:
            g.node(
                n.id,
                label=n.label.replace("\n", "<BR/>"),
                fillcolor=fillcolor,
                color=border,
                shape="box",
                style="filled,rounded",
            )
        except Exception as ex:
            _log.warning(f"节点 {n.id} 渲染失败: {ex}")

    # Edges
    for e in spec.edges:
        attrs = {"color": e.color} if e.color and e.color.startswith("#") else {}
        if e.label:
            attrs["label"] = e.label
        if e.style == "dashed":
            attrs["style"] = "dashed"
        elif e.style == "dotted":
            attrs["style"] = "dotted"
        if e.arrow == "<-":
            attrs["dir"] = "back"
        try:
            g.edge(e.src, e.dst, **attrs)
        except Exception as ex:
            _log.warning(f"边 {e.src}->{e.dst} 跳过: {ex}")

    return _render(g, output_path, name=f"hierarchy_{style}")


# ── 统一渲染入口 ─────────────────────────────────────────────────────────────


def _render(g, output_path: str, name: str = "diagram") -> str:
    """调用 graphviz 渲染并返回最终 PNG 路径"""
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = Path(output_path).stem
    try:
        # cleanup=True 删掉中间 .gv 文件
        result = g.render(filename=out_name, directory=str(out_dir), cleanup=True)
        _log.info(f"[OK] graphviz 渲染: {result}")
        return str(result)
    except Exception as ex:
        _log.error(f"graphviz 渲染失败: {ex}")
        raise


# ── 公开 fallback 包装 ────────────────────────────────────────────────────────


def safe_render(gv_func, spec, output_path: str, **kwargs) -> Optional[str]:
    """graphviz 不可用时返回 None，由调用方 fallback"""
    if not graphviz_available():
        warnings.warn(
            f"graphviz 不可用，{gv_func.__name__} 跳过。请安装 graphviz 后重试。"
        )
        return None
    try:
        return gv_func(spec, output_path, **kwargs)
    except Exception as ex:
        warnings.warn(f"{gv_func.__name__} 渲染失败: {ex}")
        return None


# ── 统一入口（双后端切换）───────────────────────────────────────────────────


def draw_diagram(
    spec,
    output_path: str,
    engine: str = "graphviz",
    style: str = "tree",
    **kwargs,
) -> str:
    """统一入口：根据 engine 自动选择 matplotlib 或 graphviz 后端。

    engine:
      - "graphviz" (默认): 高质量，输出接近 draw.io 风格
      - "matplotlib": 纯 Python 备选（零系统依赖）

    当 graphviz 不可用时，自动 fallback 到 matplotlib（不抛异常）。
    """
    if engine == "graphviz" and graphviz_available():
        # 选择具体的图函数
        if "hierarchy" in kwargs.get("_kind", "") or style in ("tree", "consort", "org"):
            if style in ("tree", "consort", "org"):
                return hierarchy_tree_gv(spec, output_path, style=style)
        # 默认走 swim_lane 横向版
        try:
            # 如果 spec 没有 layers 但只有 nodes+edges（典型 process_flow），
            # 用 process_flow_gv
            if hasattr(spec, "_kind"):
                kind = spec._kind
            else:
                kind = kwargs.pop("_kind", "")
            if kind == "process":
                return process_flow_gv(spec, output_path)
            if kind in ("tree", "consort", "org"):
                return hierarchy_tree_gv(spec, output_path, style=kind)
            return swim_lane_gv(spec, output_path)
        except Exception as ex:
            warnings.warn(f"graphviz 后端失败，回退 matplotlib: {ex}")

    # matplotlib 后端（fallback 或显式选择）
    from scripts.research_framework.arch_diagram import (
        swim_lane_arch,
        process_flow,
        hierarchy_tree,
    )
    # 输出路径转 matplotlib 期望的形式
    spec.output_path = output_path
    # 根据 spec 字段猜测图类型
    has_decision = any(
        getattr(n, "node_type", "process") != "process"
        for n in spec.nodes
    )
    if has_decision:
        process_flow(spec)
        return output_path
    if spec.layers or spec.column_specs:
        swim_lane_arch(spec)
        return output_path
    # 默认 hierarchy_tree
    hierarchy_tree(spec, style=style)
    return output_path