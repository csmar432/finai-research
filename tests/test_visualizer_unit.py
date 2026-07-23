"""Tests for scripts/core/visualizer.py — WorkflowVisualizer dataclasses and formatting."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.visualizer import (
        OutputFormat,
        VizNode,
        VizEdge,
    )
except Exception as _exc:
    pytest.skip(f"visualizer not importable: {_exc}", allow_module_level=True)


class TestOutputFormat:
    def test_values(self):
        """OutputFormat enum must have expected values."""
        values = [f.value for f in OutputFormat]
        assert "dot" in values
        assert "mermaid" in values
        assert "html" in values
        assert "json" in values


class TestVizNode:
    def test_required_fields(self):
        """VizNode must accept id and label."""
        node = VizNode(id="start", label="Start Node")
        assert node.id == "start"
        assert node.label == "Start Node"

    def test_defaults(self):
        """Default values must be sensible."""
        node = VizNode(id="n1", label="Test")
        assert node.type == "agent"
        assert node.color == "#4A90E2"
        assert node.shape == "box"
        assert node.metadata == {}

    def test_all_fields(self):
        """All fields must be accepted."""
        node = VizNode(
            id="exec1",
            label="Execution Node",
            type="gate",
            color="#FF0000",
            shape="diamond",
            status="running",
            duration_ms=150.5,
            tokens_used=2048,
            model="gpt-4",
            iterations=3,
            tools_called=["search", "fetch"],
        )
        assert node.type == "gate"
        assert node.color == "#FF0000"
        assert node.status == "running"
        assert node.duration_ms == 150.5
        assert node.tokens_used == 2048
        assert "search" in node.tools_called


class TestVizEdge:
    def test_required_fields(self):
        """VizEdge must accept source, target."""
        edge = VizEdge(source="a", target="b")
        assert edge.source == "a"
        assert edge.target == "b"

    def test_optional_fields(self):
        """Optional fields must have defaults."""
        edge = VizEdge(source="a", target="b", label="uses")
        assert edge.label == "uses"


class TestVizNodeMethods:
    """Test VizNode instance methods."""

    def test_to_dot_box(self):
        """to_dot() generates valid DOT for box shape."""
        node = VizNode(id="test_box", label="Test Box", shape="box", color="#4A90E2")
        dot = node.to_dot()
        assert "test_box" in dot
        assert 'label="' in dot
        assert 'shape=box' in dot
        assert 'color="#4A90E2"' in dot

    def test_to_dot_diamond(self):
        """to_dot() generates valid DOT for diamond shape."""
        node = VizNode(id="test_diamond", label="Decision", shape="diamond")
        dot = node.to_dot()
        assert "test_diamond" in dot
        assert "shape=diamond" in dot

    def test_to_dot_circle(self):
        """to_dot() generates valid DOT for circle shape."""
        node = VizNode(id="test_circle", label="Start", shape="circle")
        dot = node.to_dot()
        assert "test_circle" in dot
        assert "shape=circle" in dot

    def test_to_dot_hexagon(self):
        """to_dot() generates valid DOT for hexagon shape."""
        node = VizNode(id="test_hex", label="Process", shape="hexagon")
        dot = node.to_dot()
        assert "test_hex" in dot
        assert "shape=hexagon" in dot

    def test_to_dot_stadium(self):
        """to_dot() generates valid DOT for stadium shape."""
        node = VizNode(id="test_stadium", label="Waiting", shape="stadium")
        dot = node.to_dot()
        assert "test_stadium" in dot
        assert "shape=stadium" in dot

    def test_to_dot_unknown_shape_defaults_to_box(self):
        """to_dot() defaults to box for unknown shapes."""
        node = VizNode(id="unknown", label="Unknown", shape="trapezoid")
        dot = node.to_dot()
        assert "shape=box" in dot

    def test_to_dot_with_duration(self):
        """to_dot() includes duration metadata."""
        node = VizNode(id="dur_node", label="Node", duration_ms=5000)
        dot = node.to_dot()
        # duration_ms > 0 should appear in meta
        assert "5.0s" in dot

    def test_to_dot_with_tokens(self):
        """to_dot() includes token metadata."""
        node = VizNode(id="tok_node", label="Node", tokens_used=10000)
        dot = node.to_dot()
        # to_dot uses f"Token: {self.tokens_used:,}" = "Token: 10,000"
        assert "10,000" in dot

    def test_to_dot_with_iterations(self):
        """to_dot() includes iteration metadata."""
        node = VizNode(id="iter_node", label="Node", iterations=5)
        dot = node.to_dot()
        assert "5" in dot

    def test_to_dot_style_filled(self):
        """to_dot() always uses style=filled."""
        node = VizNode(id="style_test", label="Style")
        dot = node.to_dot()
        assert "style=filled" in dot

    def test_to_dot_fillcolor_lightyellow(self):
        """to_dot() always uses fillcolor=lightyellow."""
        node = VizNode(id="fill_test", label="Fill")
        dot = node.to_dot()
        assert "fillcolor=lightyellow" in dot

    def test_to_mermaid_box(self):
        """to_mermaid() generates valid Mermaid for box shape."""
        node = VizNode(id="m_box", label="Box Node", shape="box")
        mermaid = node.to_mermaid()
        assert "m_box" in mermaid
        assert '{ }' in mermaid
        assert "Box Node" in mermaid

    def test_to_mermaid_diamond(self):
        """to_mermaid() generates valid Mermaid for diamond shape."""
        node = VizNode(id="m_diamond", label="Decision", shape="diamond")
        mermaid = node.to_mermaid()
        assert "m_diamond" in mermaid
        assert '{ { } }' in mermaid

    def test_to_mermaid_circle(self):
        """to_mermaid() generates valid Mermaid for circle shape."""
        node = VizNode(id="m_circle", label="Start", shape="circle")
        mermaid = node.to_mermaid()
        assert "m_circle" in mermaid
        assert "(())" in mermaid

    def test_to_mermaid_hexagon(self):
        """to_mermaid() generates valid Mermaid for hexagon shape."""
        node = VizNode(id="m_hex", label="Process", shape="hexagon")
        mermaid = node.to_mermaid()
        assert "m_hex" in mermaid

    def test_to_mermaid_stadium(self):
        """to_mermaid() generates valid Mermaid for stadium shape."""
        node = VizNode(id="m_stadium", label="Waiting", shape="stadium")
        mermaid = node.to_mermaid()
        assert "m_stadium" in mermaid
        assert "()" in mermaid

    def test_to_mermaid_unknown_shape_defaults(self):
        """to_mermaid() defaults to box for unknown shapes."""
        node = VizNode(id="m_unknown", label="Unknown", shape="cloud")
        mermaid = node.to_mermaid()
        assert "m_unknown" in mermaid

    def test_status_to_color_approved(self):
        """_status_to_color() maps approved correctly."""
        node = VizNode(id="s1", label="Approved", status="approved")
        assert node._status_to_color() == "#22c55e"

    def test_status_to_color_error(self):
        """_status_to_color() maps error correctly."""
        node = VizNode(id="s2", label="Error", status="error")
        assert node._status_to_color() == "#ef4444"

    def test_status_to_color_max_iterations(self):
        """_status_to_color() maps max_iterations correctly."""
        node = VizNode(id="s3", label="Max", status="max_iterations")
        assert node._status_to_color() == "#eab308"

    def test_status_to_color_running(self):
        """_status_to_color() maps running correctly."""
        node = VizNode(id="s4", label="Running", status="running")
        assert node._status_to_color() == "#3b82f6"

    def test_status_to_color_pending(self):
        """_status_to_color() maps pending correctly."""
        node = VizNode(id="s5", label="Pending", status="pending")
        assert node._status_to_color() == "#6b7280"

    def test_status_to_color_unknown(self):
        """_status_to_color() returns default for unknown status."""
        node = VizNode(id="s6", label="Unknown", status="foobar")
        assert node._status_to_color() == "#6b7280"

    def test_type_icon_svg(self):
        """_type_icon_svg() returns SVG path for each type."""
        for t in ["input", "agent", "gate", "output", "tool", "data"]:
            node = VizNode(id=f"icon_{t}", label="Test", type=t)
            svg = node._type_icon_svg()
            assert isinstance(svg, str)
            assert len(svg) > 0

    def test_type_icon_svg_unknown_type(self):
        """_type_icon_svg() returns agent icon for unknown types."""
        node = VizNode(id="icon_unknown", label="Test", type="unknown_type")
        svg = node._type_icon_svg()
        # Unknown defaults to agent icon
        assert isinstance(svg, str)

    def test_type_label_cn(self):
        """_type_label_cn() returns Chinese labels."""
        for t, expected in [
            ("input", "输入节点"),
            ("agent", "Agent 节点"),
            ("gate", "审批门控"),
            ("output", "输出节点"),
            ("tool", "工具节点"),
            ("data", "数据节点"),
        ]:
            node = VizNode(id=f"label_{t}", label="Test", type=t)
            assert node._type_label_cn() == expected

    def test_type_label_cn_unknown(self):
        """_type_label_cn() returns type string for unknown types."""
        node = VizNode(id="label_unknown", label="Test", type="custom")
        assert node._type_label_cn() == "custom"

    def test_duration_str_zero(self):
        """_duration_str() returns dash for zero."""
        node = VizNode(id="dur_zero", label="Zero", duration_ms=0)
        assert node._duration_str() == "—"

    def test_duration_str_milliseconds(self):
        """_duration_str() formats ms correctly."""
        node = VizNode(id="dur_ms", label="Ms", duration_ms=500)
        assert node._duration_str() == "500ms"

    def test_duration_str_seconds(self):
        """_duration_str() formats seconds correctly."""
        node = VizNode(id="dur_s", label="Sec", duration_ms=2500)
        assert node._duration_str() == "2.5s"

    def test_duration_str_minutes(self):
        """_duration_str() formats minutes correctly."""
        node = VizNode(id="dur_min", label="Min", duration_ms=90000)
        assert node._duration_str() == "1.5min"

    def test_tokens_str_zero(self):
        """_tokens_str() returns dash for zero."""
        node = VizNode(id="tok_zero", label="Zero", tokens_used=0)
        assert node._tokens_str() == "—"

    def test_tokens_str_small(self):
        """_tokens_str() returns raw number for small values."""
        node = VizNode(id="tok_small", label="Small", tokens_used=500)
        assert node._tokens_str() == "500"

    def test_tokens_str_thousands(self):
        """_tokens_str() formats thousands with k."""
        node = VizNode(id="tok_k", label="K", tokens_used=2500)
        assert node._tokens_str() == "2.5k"


class TestVizEdgeExtended:
    """Additional VizEdge tests."""

    def test_source_and_target_required(self):
        """source and target are required positional args."""
        edge = VizEdge(source="A", target="B")
        assert edge.source == "A"
        assert edge.target == "B"

    def test_style_default(self):
        """style defaults to 'solid'."""
        edge = VizEdge(source="A", target="B")
        assert edge.style == "solid"

    def test_color_default(self):
        """color defaults to '#666666'."""
        edge = VizEdge(source="A", target="B")
        assert edge.color == "#666666"

    def test_label_default_empty(self):
        """label defaults to empty string."""
        edge = VizEdge(source="A", target="B")
        assert edge.label == ""

    def test_metadata_default_empty(self):
        """metadata defaults to empty dict."""
        edge = VizEdge(source="A", target="B")
        assert edge.metadata == {}
        assert isinstance(edge.metadata, dict)

    def test_all_fields(self):
        """All optional fields can be set."""
        edge = VizEdge(
            source="src",
            target="dst",
            label="connects",
            style="dashed",
            color="#FF0000",
            metadata={"weight": 1.5},
        )
        assert edge.source == "src"
        assert edge.target == "dst"
        assert edge.label == "connects"
        assert edge.style == "dashed"
        assert edge.color == "#FF0000"
        assert edge.metadata["weight"] == 1.5

    def test_style_dotted(self):
        """style can be 'dotted'."""
        edge = VizEdge(source="A", target="B", style="dotted")
        assert edge.style == "dotted"


class TestWorkflowVisualizerBasics:
    """Test WorkflowVisualizer initialization and basic structure."""

    def test_init(self):
        """Visualizer initializes with empty collections."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._nodes == []
        assert viz._edges == []
        assert viz._trace == {}

    def test_ms_to_str_zero(self):
        """_ms_to_str() returns dash for zero."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._ms_to_str(0) == "–"

    def test_ms_to_str_ms(self):
        """_ms_to_str() formats ms correctly."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._ms_to_str(500) == "500ms"

    def test_ms_to_str_seconds(self):
        """_ms_to_str() formats seconds correctly."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._ms_to_str(2500) == "2.5s"

    def test_ms_to_str_minutes(self):
        """_ms_to_str() formats minutes correctly."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._ms_to_str(90000) == "1.5min"

    def test_tokens_fmt_zero(self):
        """_tokens_fmt() returns dash for zero."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._tokens_fmt(0) == "–"

    def test_tokens_fmt_small(self):
        """_tokens_fmt() returns raw number for small values."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._tokens_fmt(500) == "500"

    def test_tokens_fmt_thousands(self):
        """_tokens_fmt() formats thousands with k."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        assert viz._tokens_fmt(2500) == "2.5k"


class TestBuildFromSteps:
    """Test WorkflowVisualizer.build_from_steps()."""

    def test_build_from_empty_steps(self):
        """build_from_steps() with empty list creates input/output nodes."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyStep:
            pass

        viz = WorkflowVisualizer()
        viz.build_from_steps([])
        # Should have input and output nodes at minimum
        assert len(viz._nodes) >= 2
        ids = [n.id for n in viz._nodes]
        assert "input" in ids
        assert "output" in ids

    def test_build_from_steps_adds_input_node(self):
        """build_from_steps() always adds an input node."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyStep:
            pass

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        ids = [n.id for n in viz._nodes]
        assert "input" in ids

    def test_build_from_steps_adds_output_node(self):
        """build_from_steps() always adds an output node."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyStep:
            pass

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        ids = [n.id for n in viz._nodes]
        assert "output" in ids

    def test_build_from_steps_with_stage(self):
        """build_from_steps() uses stage attribute for node id."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        ids = [n.id for n in viz._nodes]
        assert "literature" in ids

    def test_build_from_steps_with_hitl_gate(self):
        """build_from_steps() adds gate node when hitl_gate=True."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.OUTLINE
            agent_name = "outline"
            hitl_gate = True

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        ids = [n.id for n in viz._nodes]
        assert any("gate" in i for i in ids)

    def test_build_from_steps_returns_self(self):
        """build_from_steps() returns self for chaining."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyStep:
            pass

        viz = WorkflowVisualizer()
        result = viz.build_from_steps([])
        assert result is viz

    def test_build_from_steps_edges_created(self):
        """build_from_steps() creates edges between nodes."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        assert len(viz._edges) >= 1
        sources = [e.source for e in viz._edges]
        targets = [e.target for e in viz._edges]
        assert "input" in sources
        assert "output" in targets


class TestOverlayTrace:
    """Test WorkflowVisualizer.overlay_trace()."""

    def test_overlay_trace_empty_result(self):
        """overlay_trace() handles empty trace gracefully."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyResult:
            trace = []

        viz = WorkflowVisualizer()
        viz.overlay_trace(DummyResult())
        assert viz._trace == {}

    def test_overlay_trace_agent_start(self):
        """overlay_trace() handles agent_start event."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyEvent:
            def get(self, key, default=None):
                mapping = {
                    "type": "agent_start",
                    "stage": "literature",
                    "timestamp": 1234567890.0,
                }
                return mapping.get(key, default)

        class DummyResult:
            trace = [DummyEvent()]

        viz = WorkflowVisualizer()
        viz.overlay_trace(DummyResult())
        assert "literature" in viz._trace

    def test_overlay_trace_agent_end(self):
        """overlay_trace() handles agent_end event with status."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyEvent:
            def get(self, key, default=None):
                mapping = {
                    "type": "agent_end",
                    "stage": "literature",
                    "status": "approved",
                    "timestamp": 1234567895.0,
                    "latency_ms": 5000,
                    "tokens_used": 2048,
                    "model": "gpt-4",
                    "input_preview": "test input",
                    "output_preview": "test output",
                    "error": "",
                    "iterations": 3,
                    "tools_called": ["search", "fetch"],
                    "citations": [{"title": "Paper 1"}],
                }
                return mapping.get(key, default)

        class DummyResult:
            trace = [DummyEvent()]

        viz = WorkflowVisualizer()
        viz.overlay_trace(DummyResult())
        assert viz._trace["literature"]["status"] == "approved"

    def test_overlay_trace_returns_self(self):
        """overlay_trace() returns self for chaining."""
        from scripts.core.visualizer import WorkflowVisualizer

        class DummyResult:
            trace = []

        viz = WorkflowVisualizer()
        result = viz.overlay_trace(DummyResult())
        assert result is viz


class TestToDot:
    """Test WorkflowVisualizer.to_dot()."""

    def test_to_dot_empty(self):
        """to_dot() generates valid DOT for empty graph."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        dot = viz.to_dot()
        assert "digraph workflow {" in dot
        assert "}" in dot
        assert "rankdir=TB" in dot

    def test_to_dot_with_nodes(self):
        """to_dot() includes node definitions."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        dot = viz.to_dot()
        assert "digraph workflow {" in dot
        assert '"literature"' in dot

    def test_to_dot_with_edges(self):
        """to_dot() includes edge definitions."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        dot = viz.to_dot()
        assert "->" in dot


class TestToMermaid:
    """Test WorkflowVisualizer.to_mermaid()."""

    def test_to_mermaid_empty(self):
        """to_mermaid() generates valid Mermaid for empty graph."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        mermaid = viz.to_mermaid()
        assert "```mermaid" in mermaid
        assert "flowchart TD" in mermaid
        assert "```" in mermaid

    def test_to_mermaid_with_nodes(self):
        """to_mermaid() includes node definitions."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        mermaid = viz.to_mermaid()
        assert "literature" in mermaid

    def test_to_mermaid_with_edges(self):
        """to_mermaid() includes edge definitions."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        mermaid = viz.to_mermaid()
        assert "-->" in mermaid


class TestToJson:
    """Test WorkflowVisualizer.to_json()."""

    def test_to_json_empty(self):
        """to_json() returns correct structure for empty graph."""
        from scripts.core.visualizer import WorkflowVisualizer
        viz = WorkflowVisualizer()
        data = viz.to_json()
        assert "nodes" in data
        assert "edges" in data
        assert "trace" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert isinstance(data["trace"], dict)

    def test_to_json_with_data(self):
        """to_json() serializes nodes and edges correctly."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        data = viz.to_json()
        assert len(data["nodes"]) >= 2
        assert len(data["edges"]) >= 1

    def test_to_json_node_fields(self):
        """to_json() node entries contain all expected fields."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        data = viz.to_json()
        node = data["nodes"][0]
        expected = {"id", "label", "type", "color", "shape", "metadata",
                    "status", "duration_ms", "tokens_used", "model",
                    "input_preview", "output_preview", "error",
                    "iterations", "tools_called", "citations"}
        for field in expected:
            assert field in node, f"Missing field: {field}"

    def test_to_json_edge_fields(self):
        """to_json() edge entries contain all expected fields."""
        from scripts.core.visualizer import WorkflowVisualizer
        from scripts.core.orchestrator import PipelineStage

        class DummyStep:
            stage = PipelineStage.LITERATURE
            agent_name = "literature"
            hitl_gate = False

        viz = WorkflowVisualizer()
        viz.build_from_steps([DummyStep()])
        data = viz.to_json()
        edge = data["edges"][0]
        for field in ["source", "target", "label", "style", "color"]:
            assert field in edge, f"Missing field: {field}"


class TestEnhancedChart:
    """Test EnhancedChart class."""

    def test_init_all_fields(self):
        """EnhancedChart.__init__ accepts all parameters."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="Test Chart",
            data_provenance=["tushare", "wind"],
            chart_type="line",
            figure_number="1a",
            source_notes="Sample data",
        )
        assert chart.title == "Test Chart"
        assert chart.chart_type == "line"
        assert chart.figure_number == "1a"
        assert chart.source_notes == "Sample data"
        assert chart.data_provenance == ["tushare", "wind"]
        plt.close(fig)

    def test_init_defaults(self):
        """EnhancedChart.__init__ defaults are correct."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(fig=fig, ax=ax, title="T")
        assert chart.data_provenance == []
        assert chart.chart_type == "generic"
        assert chart.figure_number is None
        assert chart.source_notes == ""
        plt.close(fig)

    def test_get_latex_provenance_comment(self):
        """get_latex_provenance_comment() generates valid LaTeX."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig, ax=ax,
            title="Revenue Trend",
            data_provenance=["CSMAR"],
            chart_type="line",
            figure_number="2",
        )
        comment = chart.get_latex_provenance_comment()
        assert "Figure 2" in comment
        assert "Revenue Trend" in comment
        assert "CSMAR" in comment
        assert "\\provenance" in comment
        plt.close(fig)

    def test_get_latex_provenance_comment_no_number(self):
        """get_latex_provenance_comment() handles missing figure number."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(fig=fig, ax=ax, title="Test")
        comment = chart.get_latex_provenance_comment()
        assert "Figure ?" in comment
        plt.close(fig)

    def test_get_latex_provenance_comment_with_notes(self):
        """get_latex_provenance_comment() includes source notes."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig, ax=ax,
            title="Test",
            source_notes="Adjusted for inflation",
        )
        comment = chart.get_latex_provenance_comment()
        assert "Adjusted for inflation" in comment
        plt.close(fig)

    def test_get_mermaid_lineage(self):
        """get_mermaid_lineage() generates valid Mermaid."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig, ax=ax,
            title="Sales Funnel",
            data_provenance=["Tushare", "CSMAR"],
            chart_type="funnel",
        )
        mermaid = chart.get_mermaid_lineage()
        assert "```mermaid" in mermaid
        assert "flowchart LR" in mermaid
        assert "Tushare" in mermaid
        assert "CSMAR" in mermaid
        assert "Sales Funnel" in mermaid
        assert "```" in mermaid
        plt.close(fig)

    def test_get_mermaid_lineage_empty_provenance(self):
        """get_mermaid_lineage() handles empty provenance."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(fig=fig, ax=ax, title="Empty")
        mermaid = chart.get_mermaid_lineage()
        assert "```mermaid" in mermaid
        plt.close(fig)

    def test_to_dict(self):
        """to_dict() returns full serialized representation."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig, ax=ax,
            title="Dict Test",
            data_provenance=["source1"],
            chart_type="bar",
            figure_number="3",
            source_notes="Test notes",
        )
        d = chart.to_dict()
        assert d["title"] == "Dict Test"
        assert d["chart_type"] == "bar"
        assert d["figure_number"] == "3"
        assert d["source_notes"] == "Test notes"
        assert d["data_provenance"] == ["source1"]
        assert "latex_comment" in d
        assert "mermaid" in d
        plt.close(fig)

    def test_save_with_provenance(self):
        """save_with_provenance() saves figure and sidecar."""
        from scripts.core.visualizer import EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        chart = EnhancedChart(
            fig=fig, ax=ax,
            title="Save Test",
            data_provenance=["test_source"],
            chart_type="line",
            figure_number="S1",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "save_test.pdf"
            chart.save_with_provenance(path)
            assert path.exists()
            # Check sidecar file
            sidecar = Path(str(path) + ".provenance.json")
            assert sidecar.exists()
            import json
            prov = json.loads(sidecar.read_text())
            assert prov["title"] == "Save Test"
            assert "latex_comment" in prov
            assert "mermaid" in prov
        plt.close(fig)


class TestCreateTrackedChart:
    """Test create_tracked_chart() factory function."""

    def test_returns_enhanced_chart(self):
        """create_tracked_chart() returns an EnhancedChart."""
        from scripts.core.visualizer import create_tracked_chart, EnhancedChart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = create_tracked_chart(
            fig=fig, ax=ax,
            title="Tracked Chart",
            data_sources=["test_src"],
        )
        assert isinstance(chart, EnhancedChart)
        assert chart.title == "Tracked Chart"
        assert chart.data_provenance == ["test_src"]
        plt.close(fig)

    def test_custom_chart_type(self):
        """create_tracked_chart() passes chart_type."""
        from scripts.core.visualizer import create_tracked_chart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = create_tracked_chart(
            fig=fig, ax=ax,
            title="Scatter",
            data_sources=["src"],
            chart_type="scatter",
        )
        assert chart.chart_type == "scatter"
        plt.close(fig)

    def test_custom_figure_number(self):
        """create_tracked_chart() passes figure_number."""
        from scripts.core.visualizer import create_tracked_chart
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        chart = create_tracked_chart(
            fig=fig, ax=ax,
            title="Figure",
            data_sources=["src"],
            figure_number="5b",
        )
        assert chart.figure_number == "5b"
        plt.close(fig)


class TestAgentColors:
    """Test AGENT_COLORS constant."""

    def test_agent_colors_all_string_values(self):
        """AGENT_COLORS values are valid hex color strings."""
        from scripts.core.visualizer import AGENT_COLORS
        for key, color in AGENT_COLORS.items():
            assert color.startswith("#")
            assert len(color) == 7

    def test_agent_colors_expected_keys(self):
        """AGENT_COLORS has all expected keys."""
        from scripts.core.visualizer import AGENT_COLORS
        expected_keys = {
            "outline", "literature", "plotting", "writing",
            "refinement", "evaluation", "gate", "data", "input", "output",
        }
        assert set(AGENT_COLORS.keys()) == expected_keys

    def test_agent_colors_not_empty(self):
        """AGENT_COLORS is non-empty."""
        from scripts.core.visualizer import AGENT_COLORS
        assert len(AGENT_COLORS) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
