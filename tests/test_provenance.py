#!/usr/bin/env python3
"""tests/test_provenance.py — Integration tests for provenance.py and EnhancedChart."""

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import json
import tempfile
import uuid

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from scripts.core.provenance import (
    ProvenanceNode,
    ProvenanceTracker,
    compute_checksum,
    get_tracker,
    register_chart,
    register_data_source,
    reset_tracker,
)
from scripts.core.visualizer import EnhancedChart, create_tracked_chart


# ── ProvenanceNode ──────────────────────────────────────────────────────────────


class TestProvenanceNode:
    def test_provenance_node_creation(self):
        node = ProvenanceNode(
            node_id="test_node",
            node_type="data_source",
            description="Test data source",
            mcp_server="test-server",
            mcp_tool="test_tool",
        )
        assert node.node_id == "test_node"
        assert node.node_type == "data_source"
        assert node.description == "Test data source"
        assert node.mcp_server == "test-server"
        assert node.mcp_tool == "test_tool"
        assert node.timestamp != ""

    def test_node_to_dict_roundtrip(self):
        node = ProvenanceNode(
            node_id="roundtrip",
            node_type="chart",
            description="Roundtrip test",
        )
        data = node.to_dict()
        restored = ProvenanceNode.from_dict(data)
        assert restored.node_id == node.node_id
        assert restored.node_type == node.node_type
        assert restored.description == node.description


# ── Checksum ───────────────────────────────────────────────────────────────────


class TestChecksum:
    def test_compute_checksum(self):
        data = {"key": "value", "numbers": [1, 2, 3]}
        checksum = compute_checksum(data)
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256 hex

    def test_checksum_consistency(self):
        data = {"a": 1, "b": 2}
        c1 = compute_checksum(data)
        c2 = compute_checksum(data)
        assert c1 == c2

    def test_checksum_different_data(self):
        c1 = compute_checksum({"x": 1})
        c2 = compute_checksum({"x": 2})
        assert c1 != c2


# ── ProvenanceTracker ──────────────────────────────────────────────────────────


class TestTracker:
    def test_tracker_register_data_source(self):
        reset_tracker()
        tracker = get_tracker()
        ds_id = tracker.register_data_source(
            node_id="ds_test",
            source="MCP:test",
            mcp_server="test-server",
            mcp_tool="get_test",
            description="Test data source",
        )
        assert ds_id == "ds_test"
        node = tracker.get_node("ds_test")
        assert node is not None
        assert node.node_type == "data_source"
        assert node.mcp_server == "test-server"

    def test_tracker_register_chart(self):
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data_source(node_id="ds1", description="Data source 1")
        chart_id = tracker.register_chart(
            node_id="chart_test",
            title="Test Chart",
            data_source_ref="ds1",
            chart_type="line",
        )
        assert chart_id == "chart_test"
        node = tracker.get_node("chart_test")
        assert node is not None
        assert node.node_type == "chart"
        assert "ds1" in node.parent_ids

    def test_tracker_lineage(self):
        reset_tracker()
        tracker = get_tracker()
        ds_id = tracker.register_data_source(node_id="ds_lineage", description="Root data")
        trans_id = tracker.register_transformation(
            node_id="trans_lineage",
            transformation="filter",
            parent_ids=[ds_id],
            description="Filtered data",
        )
        chart_id = tracker.register_chart(
            node_id="chart_lineage",
            title="Lineage Chart",
            data_source_ref="trans_lineage",
        )
        lineage = tracker.get_lineage(chart_id)
        ids = [n.node_id for n in lineage]
        assert "ds_lineage" in ids
        assert "trans_lineage" in ids
        assert "chart_lineage" in ids

    def test_get_latex_provenance(self):
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data_source(node_id="ds_latex", description="Test source")
        tracker.register_chart(
            node_id="chart_latex",
            title="LaTeX Test Chart",
            data_source_ref="ds_latex",
        )
        latex = tracker.get_latex_provenance()
        assert "\\provenance" in latex or "Data:" in latex or "session" in latex

    def test_to_graphviz(self):
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data_source(node_id="gv_ds", description="GV Source")
        tracker.register_chart(
            node_id="gv_chart",
            title="GV Chart",
            data_source_ref="gv_ds",
        )
        dot = tracker.to_graphviz()
        assert "digraph" in dot
        assert "gv_ds" in dot
        assert "gv_chart" in dot


# ── EnhancedChart ──────────────────────────────────────────────────────────────


class TestEnhancedChart:
    def test_enhanced_chart_creation(self):
        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="Test Chart",
            data_provenance=["ds1", "ds2"],
            chart_type="line",
            figure_number="1",
            source_notes="Test notes",
        )
        assert chart.title == "Test Chart"
        assert chart.chart_type == "line"
        assert chart.figure_number == "1"
        assert chart.source_notes == "Test notes"
        assert chart.data_provenance == ["ds1", "ds2"]
        plt.close(fig)

    def test_enhanced_chart_latex_comment(self):
        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="My Chart",
            data_provenance=["source_a", "source_b"],
            chart_type="bar",
            figure_number="2",
        )
        latex = chart.get_latex_provenance_comment()
        assert "\\provenance" in latex or "provenance" in latex
        assert "source_a" in latex
        assert "source_b" in latex
        plt.close(fig)

    def test_enhanced_chart_mermaid(self):
        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="Mermaid Test",
            data_provenance=["ds_x", "ds_y"],
        )
        mermaid = chart.get_mermaid_lineage()
        assert "flowchart" in mermaid
        assert "ds_x" in mermaid
        assert "ds_y" in mermaid
        plt.close(fig)

    def test_enhanced_chart_to_dict(self):
        fig, ax = plt.subplots()
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="Dict Test",
            data_provenance=["ds1"],
            chart_type="scatter",
            figure_number="3",
            source_notes="Notes here",
        )
        d = chart.to_dict()
        assert d["title"] == "Dict Test"
        assert d["chart_type"] == "scatter"
        assert d["figure_number"] == "3"
        assert d["data_provenance"] == ["ds1"]
        plt.close(fig)


# ── create_tracked_chart ────────────────────────────────────────────────────────


class TestCreateTrackedChart:
    def test_create_tracked_chart(self):
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data_source(
            node_id="tracked_ds",
            description="Tracked data source",
        )
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        chart = create_tracked_chart(
            fig=fig,
            ax=ax,
            title="Tracked Line Chart",
            data_sources=["tracked_ds"],
            tracker=tracker,
            chart_type="line",
            figure_number="4",
        )
        assert isinstance(chart, EnhancedChart)
        assert chart.title == "Tracked Line Chart"
        assert chart.chart_type == "line"
        assert chart.figure_number == "4"
        assert chart.data_provenance == ["tracked_ds"]
        plt.close(fig)

    def test_create_tracked_chart_no_tracker(self):
        reset_tracker()
        fig, ax = plt.subplots()
        chart = create_tracked_chart(
            fig=fig,
            ax=ax,
            title="No Tracker Chart",
            data_sources=["ds1"],
            tracker=None,
            chart_type="bar",
        )
        assert isinstance(chart, EnhancedChart)
        assert chart.title == "No Tracker Chart"
        plt.close(fig)


# ── save_with_provenance ───────────────────────────────────────────────────────


class TestSaveWithProvenance:
    def test_enhanced_chart_save_with_provenance(self):
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [4, 5, 6])
        chart = EnhancedChart(
            fig=fig,
            ax=ax,
            title="Save Test Chart",
            data_provenance=["save_ds1"],
            chart_type="line",
            figure_number="5",
            source_notes="Save test notes",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_chart.png"
            chart.save_with_provenance(out_path, dpi=100)

            assert out_path.exists()
            sidecar = Path(str(out_path) + ".provenance.json")
            assert sidecar.exists()

            prov_data = json.loads(sidecar.read_text(encoding="utf-8"))
            assert prov_data["title"] == "Save Test Chart"
            assert prov_data["chart_type"] == "line"
            assert prov_data["figure_number"] == "5"
            assert prov_data["data_provenance"] == ["save_ds1"]
            assert "latex_comment" in prov_data

        plt.close(fig)


# ── Decorators ─────────────────────────────────────────────────────────────────


class TestDecorators:
    def test_register_data_source_decorator(self):
        reset_tracker()
        tracker = get_tracker()

        @register_data_source(
            source="MCP:decorated",
            mcp_server="test-server",
            mcp_tool="get_decorated",
            description="Decorated data source",
        )
        def fetch_data(x):
            return {"x": x}

        result = fetch_data(42)
        assert result == {"x": 42}
        # Check that nodes were registered
        data_nodes = [
            n for n in tracker.nodes.values() if n.node_type == "data_source"
        ]
        assert len(data_nodes) >= 1

    def test_register_chart_decorator(self):
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data_source(
            node_id="deco_ds",
            description="Decorator data source",
        )

        @register_chart(
            node_id="deco_chart",
            title="Decorator Chart",
            data_source="deco_ds",
            chart_type="line",
            tracker=tracker,
        )
        def make_chart():
            fig, ax = plt.subplots()
            ax.plot([1, 2], [1, 2])
            return fig

        fig = make_chart()
        assert tracker.get_node("deco_chart") is not None
        plt.close(fig)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
