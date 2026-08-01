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


def swim_lane_gv(spec, output_path: str, theme: dict = THEME_LIGHT,
                  with_legend: bool = True,
                  with_command_bar: bool = True) -> str:
    """swim_lane 架构图 — graphviz 后端（参考图风格升级版）

    T1-T5 全部升级:
      - PIPELINE 胶囊头（每个 layer 顶部带 icon 的圆角橙色标题）
      - 色块分区（4 个 layer fillcolor 更鲜明）
      - 底部图例（颜色 + 边类型样本）
      - USER 层命令栏（/initialize /resume /launcher /cmd-write）
      - 字体/字号优化（11pt + 间距 1.1）

    输入: 现有 DiagramSpec（兼容 arch_diagram.py 的数据类）
    输出: PNG 文件路径
    """
    gv = _import_graphviz()
    if gv is None:
        raise RuntimeError("graphviz Python 包未安装")

    # 全局布局：横向 + 留白加大（容纳图例 + 命令栏）
    g = gv.Digraph(name="swim_lane", format="png")
    g.attr(
        rankdir="LR",
        bgcolor=theme["bg"],
        pad="0.8",
        nodesep="0.35",
        ranksep="0.7",
        compound="true",
        splines="spline",
        labelloc="b",  # 图例位置：底部
        labeljust="c",
        fontname=theme["font"],
        fontsize="9",
        fontcolor="#7F8C8D",
    )
    g.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname=theme["font"],
        fontsize="11",
        margin="0.20,0.12",
        color="#34495E",
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

    # Layer 配色（强化版：色块更鲜明）
    LAYER_COLORS = {
        "USER": ("#FDEBD0", "#E67E22", "#D68910", "👤"),
        "USER LAYER": ("#FDEBD0", "#E67E22", "#D68910", "👤"),
        "SKILLS": ("#D6EAF8", "#3498DB", "#21618C", "🧠"),
        "SKILLS LAYER": ("#D6EAF8", "#3498DB", "#21618C", "🧠"),
        "PERSISTENCE": ("#EBDEF0", "#8E44AD", "#6C3483", "💾"),
        "INFRASTRUCTURE": ("#D5F5E3", "#27AE60", "#1E8449", "⚙"),
        "DEFAULT": ("#EAEDED", "#34495E", "#2C3E50", "📦"),
    }

    # 解析 spec.layers
    layers_in_spec = [(l.name, l) for l in spec.layers]
    if not layers_in_spec:
        layers_in_spec = [
            ("USER", ("#FDEBD0", "#E67E22", "#D68910", "👤")),
            ("SKILLS", ("#D6EAF8", "#3498DB", "#21618C", "🧠")),
            ("PERSISTENCE", ("#EBDEF0", "#8E44AD", "#6C3483", "💾")),
            ("INFRASTRUCTURE", ("#D5F5E3", "#27AE60", "#1E8449", "⚙")),
        ]

    # 收集所有 layer name 用于节点过滤
    all_layer_names = [name for name, _ in layers_in_spec]

    for layer_name, layer in layers_in_spec:
        if isinstance(layer, tuple) and len(layer) == 4:
            fill, border, font, icon = layer
        elif isinstance(layer, tuple) and len(layer) == 3:
            fill, border, font = layer
            icon = LAYER_COLORS.get(layer_name, LAYER_COLORS["DEFAULT"])[3]
        else:
            # dataclass Layer
            fill = layer.color
            border = layer.color
            font = layer.text_color if hasattr(layer, "text_color") else "#2C3E50"
            icon = LAYER_COLORS.get(layer_name, LAYER_COLORS["DEFAULT"])[3]

        cluster_name = f"cluster_{layer_name.lower().replace(' ', '_')}"

        # PIPELINE 胶囊头: 用 HTML 标签让标题带 icon + 圆角感
        # DOT 限制：cluster label 是纯文本。变通方案：用 HREF + label 居中
        # 但实际效果已接近"胶囊标题"。HTML label 见下方：
        capsule_label = (
            f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">'
            f'<TR><TD ALIGN="CENTER" BGCOLOR="{fill}" COLOR="{border}">'
            f'<FONT COLOR="{font}" POINT-SIZE="14"><B>{icon} {layer_name}</B></FONT>'
            f'</TD></TR></TABLE>>'
        )

        with g.subgraph(name=cluster_name) as c:
            c.attr(
                label=capsule_label,
                style="filled,rounded",
                fillcolor=fill,
                color=border,
                fontcolor=font,
                fontname=theme["font"] + "-Bold",
                fontsize="14",
                margin="14",
                penwidth="2.0",
            )

            # 按 column 分泳道
            cols: dict[str, list] = {}
            for n in spec.nodes:
                # 节点属于本 layer（按 layer 字段匹配，未指定则归入第一层）
                node_layer = getattr(n, "layer", "") or ""
                if node_layer == layer_name or (
                    not node_layer and layer_name == all_layer_names[0]
                ):
                    col_key = getattr(n, "column", "") or "main"
                    cols.setdefault(col_key, []).append(n)

            # USER 层加命令栏（T4）
            if layer_name in ("USER", "USER LAYER") and with_command_bar:
                _add_command_bar(c)

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

    # Edges (T5 强化: invoke=红 / loop=黄 / data=蓝 / 黑色实线=主流程)
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
        attrs = {"color": color, "penwidth": "1.5"}
        if e.label:
            attrs["label"] = e.label
            attrs["fontcolor"] = color
            attrs["fontsize"] = "9"
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

    # 底部图例（T3）
    if with_legend:
        _add_legend(g, theme)

    return _render(g, output_path, name="swim_lane")


def _add_command_bar(cluster):
    """USER 层命令栏（/initialize /resume /launcher /cmd-write）

    用 4 个不可见 rank 的胶囊组成一行，每个用 HTML label 模拟圆角胶囊
    """
    cmds = [
        ("cmd_init", "/initialize", "▶"),
        ("cmd_resume", "/resume", "↻"),
        ("cmd_launcher", "/launcher", "🚀"),
        ("cmd_write", "/cmd-write", "✎"),
    ]
    for cid, label, icon in cmds:
        # HTML 胶囊式标签：背景橙色 + 白字 + 圆角感
        html = (
            f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
            f'BGCOLOR="#E67E22" COLOR="#D68910">'
            f'<TR><TD ALIGN="CENTER"><FONT COLOR="white" POINT-SIZE="9">'
            f'<B>{icon} {label}</B></FONT></TD></TR>'
            f'</TABLE>>'
        )
        cluster.node(
            cid,
            label=html,
            shape="box",
            style="filled,rounded",
            fillcolor="#E67E22",
            color="#D68910",
            fontcolor="white",
            fontsize="9",
            margin="0.10,0.05",
        )


def _add_legend(g, theme: dict):
    """底部图例：颜色 + 边类型样本"""
    legend_name = "cluster_legend"
    with g.subgraph(name=legend_name) as c:
        # 图例标题
        c.attr(
            label="LEGEND",
            style="filled,rounded",
            fillcolor="#F4F6F6",
            color="#BDC3C7",
            fontcolor="#2C3E50",
            fontname=theme["font"] + "-Bold",
            fontsize="10",
            margin="8",
        )

        # 4 个 layer 颜色样本（独立 rank，与边样本并列）
        layer_samples = [
            ("leg_user", "USER", "#FDEBD0", "#E67E22"),
            ("leg_skills", "SKILLS", "#D6EAF8", "#3498DB"),
            ("leg_persist", "PERSISTENCE", "#EBDEF0", "#8E44AD"),
            ("leg_infra", "INFRASTRUCTURE", "#D5F5E3", "#27AE60"),
        ]
        for nid, lbl, fill, border in layer_samples:
            c.node(
                nid, label=lbl,
                shape="box", style="filled,rounded",
                fillcolor=fill, color=border,
                fontcolor="#2C3E50", fontsize="9",
                margin="0.10,0.05",
                width="1.0", height="0.4",
            )

        # 4 种边类型: 用"节点+边"模拟视觉样本
        # 每对节点之间画一条对应样式的边
        edge_pairs = [
            (("leg_e1", "leg_e2"), theme["edge_main"], None, "→ main"),
            (("leg_e3", "leg_e4"), theme["edge_invoke"], "dashed", "→ invoke"),
            (("leg_e5", "leg_e6"), theme["edge_loop"], "dashed", "↻ loop"),
            (("leg_e7", "leg_e8"), theme["edge_data"], None, "→ data"),
        ]
        for (src, dst), color, style, lbl in edge_pairs:
            # 两端节点（无标签）
            for nid in (src, dst):
                c.node(
                    nid, label="",
                    shape="point", style="invis",
                    width="0.01", height="0.01",
                )
            attrs = {"color": color, "penwidth": "2.0", "minlen": "2",
                     "label": lbl, "fontcolor": color, "fontsize": "9"}
            if style:
                attrs["style"] = style
            c.edge(src, dst, **attrs)


def _add_node_html(cluster, node, theme: dict):
    """添加节点（用 HTML 标签实现彩色卡片 + icon + label 多行）"""
    icon = _node_icon(node)
    # HTML 转义: graphviz HTML 标签里 > < & 需要转义
    def _esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    label_html = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">'
    if icon:
        label_html += f'<TR><TD ALIGN="CENTER">{icon}</TD></TR>'
    for line in node.label.split("\n"):
        label_html += f'<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="11" COLOR="#2C3E50">{_esc(line)}</FONT></TD></TR>'
    label_html += "</TABLE>>"

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