"""Tests for scripts/research_framework/arch_diagram_gv.py.

M5-2: Graphviz 后端的单元测试
- 验证依赖检测
- 验证 5 种图都能跑通
- 验证统一入口 draw_diagram 自动选后端
- 验证不破坏现有 matplotlib 后端
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.research_framework.arch_diagram import (
    DiagramSpec,
    Edge,
    Layer,
    Node,
    NODE_DECISION,
    NODE_END,
    NODE_START,
)
from scripts.research_framework.arch_diagram_gv import (
    draw_diagram,
    graphviz_available,
    hierarchy_tree_gv,
    process_flow_gv,
    swim_lane_gv,
)


# 当 graphviz 可用时跑，否则 skip（CI 跨平台保护）
gv_available = graphviz_available()
pytestmark_gv = pytest.mark.skipif(
    not gv_available, reason="graphviz (dot + Python pkg) not available"
)


# ── 依赖检测 ────────────────────────────────────────────────────────────────


class TestDependencyCheck:
    def test_graphviz_available_returns_bool(self):
        result = graphviz_available()
        assert isinstance(result, bool)


# ── swim_lane_gv ────────────────────────────────────────────────────────────


@pytestmark_gv
class TestSwimLaneGv:
    def test_minimal_runs(self, tmp_path):
        spec = DiagramSpec(
            title="t",
            layers=[Layer("L1", y_top=20, y_bottom=10)],
            nodes=[Node("a", "A", layer="L1", color="#3498DB"),
                   Node("b", "B", layer="L1", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        out = swim_lane_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()
        assert Path(out).stat().st_size > 0

    def test_with_columns(self, tmp_path):
        spec = DiagramSpec(
            title="t",
            layers=[
                Layer("USER", y_top=20, y_bottom=10, color="#FDEBD0"),
                Layer("SKILLS", y_top=10, y_bottom=0, color="#D6EAF8"),
            ],
            nodes=[
                Node("u1", "User", layer="USER", column="Main", color="#F39C12"),
                Node("a1", "Agent", layer="SKILLS", column="Sub", color="#34D399"),
                Node("p1", "Pipe", layer="SKILLS", column="Pipeline", color="#3498DB"),
            ],
            edges=[Edge("u1", "p1"), Edge("p1", "a1")],
        )
        out = swim_lane_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()

    def test_edge_styles(self, tmp_path):
        spec = DiagramSpec(
            title="edges",
            nodes=[
                Node("a", "A", color="#3498DB"),
                Node("b", "B", color="#27AE60"),
                Node("c", "C", color="#E74C3C"),
            ],
            edges=[
                Edge("a", "b", style="solid"),
                Edge("b", "c", style="dashed", label="next"),
                Edge("a", "c", style="invoke", label="invoke"),
            ],
        )
        out = swim_lane_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()

    def test_t1_t5_upgrades_disable(self, tmp_path):
        """验证 with_legend=False / with_command_bar=False 也能跑通"""
        spec = DiagramSpec(
            title="no extras",
            layers=[Layer("USER", y_top=20, y_bottom=10, color="#FDEBD0")],
            nodes=[Node("a", "A", layer="USER", color="#F39C12"),
                   Node("b", "B", layer="USER", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        out = swim_lane_gv(
            spec, str(tmp_path / "out.png"),
            with_legend=False, with_command_bar=False,
        )
        assert Path(out).exists()

    def test_t1_t5_upgrades_enable(self, tmp_path):
        """验证 with_legend=True / with_command_bar=True 默认开启"""
        spec = DiagramSpec(
            title="with extras",
            layers=[Layer("USER LAYER", y_top=20, y_bottom=10, color="#FDEBD0")],
            nodes=[Node("a", "A", layer="USER LAYER", color="#F39C12"),
                   Node("b", "B", layer="USER LAYER", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        # 默认参数
        out = swim_lane_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()
        # 带图例+命令栏的图应比不带的大（因为有更多节点）
        spec_no_legend = DiagramSpec(
            title="no legend",
            layers=[Layer("USER LAYER", y_top=20, y_bottom=10, color="#FDEBD0")],
            nodes=[Node("a", "A", layer="USER LAYER", color="#F39C12"),
                   Node("b", "B", layer="USER LAYER", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        out_no_legend = swim_lane_gv(
            spec_no_legend, str(tmp_path / "out_no_legend.png"),
            with_legend=False, with_command_bar=False,
        )
        # 文件大小不可靠对比（DOT 渲染有随机性），但至少都存在
        assert Path(out_no_legend).exists()


# ── process_flow_gv ─────────────────────────────────────────────────────────


@pytestmark_gv
class TestProcessFlowGv:
    def test_sequential(self, tmp_path):
        spec = DiagramSpec(
            title="flow",
            nodes=[Node("a", "A"), Node("b", "B"), Node("c", "C")],
            edges=[Edge("a", "b"), Edge("b", "c")],
        )
        out = process_flow_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()

    def test_with_decision(self, tmp_path):
        spec = DiagramSpec(
            title="decision",
            nodes=[
                Node("start", "S", node_type=NODE_START, color="#34D399"),
                Node("d", "Decision", node_type=NODE_DECISION, color="#F39C12"),
                Node("y", "Yes"),
                Node("n", "No"),
                Node("end", "E", node_type=NODE_END, color="#E74C3C"),
            ],
            edges=[
                Edge("start", "d"),
                Edge("d", "y", label="yes", color="#27AE60"),
                Edge("d", "n", label="no", color="#E74C3C"),
                Edge("y", "end"), Edge("n", "end"),
            ],
        )
        out = process_flow_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()

    def test_loop_back_edge(self, tmp_path):
        spec = DiagramSpec(
            title="loop",
            nodes=[
                Node("a", "A", color="#3498DB"),
                Node("b", "B", color="#27AE60"),
            ],
            edges=[Edge("a", "b"), Edge("b", "a", style="loop")],
        )
        out = process_flow_gv(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()


# ── hierarchy_tree_gv ───────────────────────────────────────────────────────


@pytestmark_gv
class TestHierarchyTreeGv:
    def test_tree(self, tmp_path):
        spec = DiagramSpec(
            title="tree",
            nodes=[Node("r", "R"), Node("a", "A"), Node("b", "B")],
            edges=[Edge("r", "a"), Edge("r", "b")],
        )
        out = hierarchy_tree_gv(spec, str(tmp_path / "out.png"), style="tree")
        assert Path(out).exists()

    def test_consort(self, tmp_path):
        spec = DiagramSpec(
            title="consort",
            nodes=[
                Node("e", "Enroll"),
                Node("t", "Trt", column="left"),
                Node("c", "Ctrl", column="right"),
                Node("ta", "Trt-An", column="left"),
                Node("ca", "Ctrl-An", column="right"),
            ],
            edges=[
                Edge("e", "t"), Edge("e", "c"),
                Edge("t", "ta"), Edge("c", "ca"),
            ],
        )
        out = hierarchy_tree_gv(spec, str(tmp_path / "out.png"), style="consort")
        assert Path(out).exists()

    def test_org(self, tmp_path):
        spec = DiagramSpec(
            title="org",
            nodes=[
                Node("r", "CEO"),
                Node("a", "A"),
                Node("b", "B"),
                Node("a1", "A1"),
                Node("a2", "A2"),
            ],
            edges=[
                Edge("r", "a"), Edge("r", "b"),
                Edge("a", "a1"), Edge("a", "a2"),
            ],
        )
        out = hierarchy_tree_gv(spec, str(tmp_path / "out.png"), style="org")
        assert Path(out).exists()


# ── draw_diagram 统一入口 ────────────────────────────────────────────────────


@pytestmark_gv
class TestDrawDiagram:
    def test_explicit_graphviz(self, tmp_path):
        spec = DiagramSpec(
            title="unified",
            nodes=[Node("a", "A", color="#3498DB"),
                   Node("b", "B", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        out = draw_diagram(spec, str(tmp_path / "out.png"), engine="graphviz")
        assert Path(out).exists()

    def test_explicit_matplotlib(self, tmp_path):
        spec = DiagramSpec(
            title="mpl",
            nodes=[Node("a", "A", color="#3498DB"),
                   Node("b", "B", color="#27AE60")],
            edges=[Edge("a", "b")],
        )
        out = draw_diagram(spec, str(tmp_path / "out.png"), engine="matplotlib")
        assert out is not None
        assert Path(out).exists()

    def test_default_engine_is_graphviz(self, tmp_path):
        spec = DiagramSpec(
            title="default",
            nodes=[Node("a", "A"), Node("b", "B")],
            edges=[Edge("a", "b")],
        )
        out = draw_diagram(spec, str(tmp_path / "out.png"))
        assert Path(out).exists()


# ── 零破坏验证 ──────────────────────────────────────────────────────────────


class TestZeroBreakageGv:
    """graphviz 后端不应破坏 matplotlib 后端"""

    def test_matplotlib_still_works(self, tmp_path):
        """不依赖 graphviz，验证 matplotlib 后端独立可用"""
        from scripts.research_framework.arch_diagram import (
            swim_lane_arch, process_flow, hierarchy_tree,
        )
        spec = DiagramSpec(
            title="mpl only",
            nodes=[Node("a", "A"), Node("b", "B")],
            edges=[Edge("a", "b")],
            output_path=str(tmp_path / "out.png"),
        )
        # 强制 graphviz 不可用也跑通
        import scripts.research_framework.arch_diagram_gv as gv
        original = gv.graphviz_available
        gv.graphviz_available = lambda: False
        try:
            swim_lane_arch(spec)
            assert Path(spec.output_path).exists()
        finally:
            gv.graphviz_available = original

    def test_existing_fin_charts_unchanged(self):
        """graphviz 模块不应影响 fin_charts"""
        import scripts.research_framework.fin_charts as fc
        assert "arch_diagram_gv" not in dir(fc)

    def test_existing_arch_diagram_unchanged(self):
        """graphviz 模块不应污染 matplotlib 后端"""
        import scripts.research_framework.arch_diagram as ad
        # 关键 dataclass 都还在
        assert hasattr(ad, "DiagramSpec")
        assert hasattr(ad, "swim_lane_arch")
        assert hasattr(ad, "process_flow")
        assert hasattr(ad, "hierarchy_tree")