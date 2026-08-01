"""Tests for scripts/research_framework/arch_diagram.py.

M5: 验证 3 种图都能跑通 + 数据类基本行为 + 不破坏现有 fin_charts/chart_factory。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.research_framework.arch_diagram import (
    Column,
    DiagramSpec,
    Edge,
    Layer,
    Node,
    NODE_DECISION,
    NODE_END,
    NODE_START,
    NODE_SUBPROCESS,
    hierarchy_tree,
    process_flow,
    swim_lane_arch,
)


class TestDataClasses:
    """数据类基本行为"""

    def test_node_defaults(self):
        n = Node(id="a", label="A")
        assert n.id == "a"
        assert n.label == "A"
        assert n.layer == ""
        assert n.column == ""
        assert n.color == "#2DD4BF"
        assert n.icon is None
        assert n.node_type == "process"
        assert n.x is None and n.y is None

    def test_node_with_all_fields(self):
        n = Node(
            id="x", label="X", layer="L1", column="c1",
            color="#FF0000", icon="1", node_type=NODE_DECISION,
            x=10.0, y=20.0, branch="yes",
        )
        assert n.node_type == NODE_DECISION
        assert n.branch == "yes"

    def test_edge_defaults(self):
        e = Edge(src="a", dst="b")
        assert e.src == "a" and e.dst == "b"
        assert e.style == "solid"
        assert e.arrow == "->"

    def test_layer_defaults(self):
        layer = Layer(name="L", y_top=10, y_bottom=5)
        assert layer.color == "#13233D"

    def test_column_defaults(self):
        c = Column(name="Col", x_left=0, x_right=10)
        assert c.dashed is True

    def test_diagramspec_defaults(self):
        spec = DiagramSpec(title="t")
        assert spec.width == 100.0
        assert spec.height == 60.0
        assert spec.bg_color == "#0A1929"
        assert spec.show_legend is True


class TestSwimLaneArch:
    """swim_lane_arch() 跑通测试"""

    def test_minimal_runs(self, tmp_path):
        spec = DiagramSpec(
            title="test",
            output_path=str(tmp_path / "out.png"),
            layers=[Layer("L1", y_top=20, y_bottom=10)],
            column_specs=[Column("C1", x_left=0, x_right=100)],
            nodes=[Node("a", "A", x=20, y=15), Node("b", "B", x=80, y=15)],
            edges=[Edge("a", "b")],
        )
        swim_lane_arch(spec)
        assert Path(spec.output_path).exists()
        assert Path(spec.output_path).stat().st_size > 0

    def test_with_icons_and_labels(self, tmp_path):
        spec = DiagramSpec(
            title="icon test",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("a", "A", color="#F5B700", icon="1", x=25, y=30),
                Node("b", "B", color="#34D399", icon="2", x=75, y=30),
            ],
            edges=[
                Edge("a", "b", label="link", style="dashed", color="#FBBF24"),
            ],
        )
        swim_lane_arch(spec)
        assert Path(spec.output_path).exists()


class TestProcessFlow:
    """process_flow() 跑通测试"""

    def test_minimal_sequential(self, tmp_path):
        spec = DiagramSpec(
            title="flow",
            output_path=str(tmp_path / "out.png"),
            nodes=[Node("a", "A"), Node("b", "B"), Node("c", "C")],
            edges=[Edge("a", "b"), Edge("b", "c")],
        )
        process_flow(spec)
        assert Path(spec.output_path).exists()

    def test_with_decision_and_branch(self, tmp_path):
        spec = DiagramSpec(
            title="decision",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("start", "S", node_type=NODE_START, color="#34D399"),
                Node("d", "Decision", node_type=NODE_DECISION, color="#FBBF24"),
                Node("y", "Yes path", branch="yes"),
                Node("n", "No path", branch="no"),
                Node("end", "E", node_type=NODE_END, color="#F87171"),
            ],
            edges=[
                Edge("start", "d"),
                Edge("d", "y", label="yes"),
                Edge("d", "n", label="no"),
                Edge("y", "end"),
                Edge("n", "end", style="dashed"),
            ],
        )
        process_flow(spec)
        assert Path(spec.output_path).exists()

    def test_with_subprocess(self, tmp_path):
        spec = DiagramSpec(
            title="sub",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("a", "Main", node_type="process"),
                Node("sub", "Subprocess", node_type=NODE_SUBPROCESS),
                Node("c", "Continue", node_type="process"),
            ],
            edges=[Edge("a", "sub"), Edge("sub", "c")],
        )
        process_flow(spec)
        assert Path(spec.output_path).exists()


class TestHierarchyTree:
    """hierarchy_tree() 跑通测试 + 3 种 style"""

    def test_default_tree(self, tmp_path):
        spec = DiagramSpec(
            title="tree",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("root", "R"),
                Node("a", "A"),
                Node("b", "B"),
                Node("a1", "A1"),
                Node("a2", "A2"),
            ],
            edges=[
                Edge("root", "a"), Edge("root", "b"),
                Edge("a", "a1"), Edge("a", "a2"),
            ],
        )
        hierarchy_tree(spec, style="tree")
        assert Path(spec.output_path).exists()

    def test_consort(self, tmp_path):
        spec = DiagramSpec(
            title="consort",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("e", "Enroll", layer=0),
                Node("r", "Random", layer=1),
                Node("t", "Trt", layer=1, column="left"),
                Node("c", "Ctrl", layer=1, column="right"),
                Node("ta", "Trt Analysis", layer=2, column="left"),
                Node("ca", "Ctrl Analysis", layer=2, column="right"),
            ],
            edges=[
                Edge("e", "r"),
                Edge("r", "t"), Edge("r", "c"),
                Edge("t", "ta"), Edge("c", "ca"),
            ],
        )
        hierarchy_tree(spec, style="consort")
        assert Path(spec.output_path).exists()

    def test_org(self, tmp_path):
        spec = DiagramSpec(
            title="org",
            output_path=str(tmp_path / "out.png"),
            nodes=[
                Node("root", "CEO"),
                Node("a", "VP-A"),
                Node("b", "VP-B"),
                Node("a1", "A-1"),
                Node("a2", "A-2"),
            ],
            edges=[
                Edge("root", "a"), Edge("root", "b"),
                Edge("a", "a1"), Edge("a", "a2"),
            ],
        )
        hierarchy_tree(spec, style="org")
        assert Path(spec.output_path).exists()


class TestZeroBreakage:
    """验证不破坏现有 fin_charts / chart_factory"""

    def test_fin_charts_imports_normally(self):
        from scripts.research_framework.fin_charts import (
            FinancialChartFactory, CHART_PRESETS,
        )
        assert len(CHART_PRESETS) == 20
        assert FinancialChartFactory is not None

    def test_chart_factory_imports_normally(self):
        from scripts.core.chart_factory import (
            AdvancedChartFactory, CHART_TYPES,
        )
        assert len(CHART_TYPES) >= 12
        assert AdvancedChartFactory is not None

    def test_no_namespace_pollution(self):
        """arch_diagram 不应注入到 fin_charts/chart_factory 模块"""
        import scripts.research_framework.fin_charts as fc
        import scripts.core.chart_factory as cf
        assert "arch_diagram" not in dir(fc)
        assert "arch_diagram" not in dir(cf)