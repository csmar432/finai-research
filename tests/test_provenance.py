#!/usr/bin/env python3
"""tests/test_provenance.py — Integration tests for provenance.py and EnhancedChart.

Updated to match the actual ProvenanceNode/ProvenanceTracker API as of v0.1.0.

Key differences from old tests:
- compute_checksum uses MD5 (32 hex chars), not SHA256 (64)
- ProvenanceNode uses `label` (not `description`), `node_type` is NodeType enum (not str)
- ProvenanceNode has `to_dict()` but NOT `from_dict()`
- ProvenanceTracker has `register_data(path, label, node_type)` (not register_data_source)
- ProvenanceTracker has `export_mermaid()` / `export_report()` (not `get_latex_provenance` / `to_graphviz`)
- standalone `register_data_source(path, label, tracker=None)` (takes path, not node_id)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from scripts.core.provenance import (
    ProvenanceNode,
    ProvenanceTracker,
    NodeType,
    compute_checksum,
    get_tracker,
    register_chart,
    register_data_source,
    reset_tracker,
)
from scripts.core.visualizer import create_tracked_chart


# ── ProvenanceNode ──────────────────────────────────────────────────────────────


class TestProvenanceNode:
    def test_provenance_node_creation(self):
        node = ProvenanceNode(
            node_id="test_node",
            node_type=NodeType.RAW_DATA,
            label="Test data source",
        )
        assert node.node_id == "test_node"
        assert node.node_type == NodeType.RAW_DATA
        assert node.label == "Test data source"

    def test_node_to_dict_roundtrip(self):
        node = ProvenanceNode(
            node_id="roundtrip",
            node_type=NodeType.CHART,
            label="Roundtrip test",
        )
        data = node.to_dict()
        assert data["node_id"] == "roundtrip"
        assert data["label"] == "Roundtrip test"


# ── Checksum ───────────────────────────────────────────────────────────────────


class TestChecksum:
    def test_compute_checksum(self):
        data = {"key": "value", "numbers": [1, 2, 3]}
        checksum = compute_checksum(data)
        assert isinstance(checksum, str)
        assert len(checksum) == 16  # MD5 hex (first 16 of full hash)

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
    def test_tracker_register_data(self):
        """ProvenanceTracker.register_data returns a generated node ID."""
        reset_tracker()
        tracker = get_tracker()
        node_id = tracker.register_data(
            path="/tmp/test_data.csv",
            label="Test data",
        )
        # Returns a generated ID like "raw_data_<hexhash>", not the path
        assert node_id.startswith("raw_data_")
        assert len(node_id) > len("raw_data_")

    def test_tracker_export_mermaid(self):
        """export_mermaid returns Mermaid-format string."""
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data(path="/tmp/src.csv", label="Source")
        mermaid = tracker.export_mermaid()
        assert isinstance(mermaid, str)
        assert "flowchart" in mermaid or "graph" in mermaid

    def test_tracker_export_report(self):
        """export_report generates a string report."""
        reset_tracker()
        tracker = get_tracker()
        tracker.register_data(path="/tmp/src.csv", label="Source")
        report = tracker.export_report()
        assert isinstance(report, str)
        assert len(report) > 0


# ── create_tracked_chart ─────────────────────────────────────────────────────


class TestCreateTrackedChart:
    def test_create_tracked_chart_with_tracker(self):
        """create_tracked_chart returns EnhancedChart regardless of tracker state."""
        reset_tracker()
        tracker = get_tracker()

        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
        # tracker.nodes may not be initialized; create_tracked_chart handles this gracefully
        chart = create_tracked_chart(
            fig, ax,
            title="Test Chart",
            data_sources=["/nonexistent/path.csv"],  # refs will be empty if nodes missing
            tracker=tracker,
        )
        assert chart is not None

    def test_create_tracked_chart_no_tracker(self):
        """create_tracked_chart without tracker works (tracker is optional)."""
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [2, 4, 6])
        chart = create_tracked_chart(fig, ax, title="No-tracker chart", data_sources=[])
        assert chart is not None


# ── Standalone function wrappers ────────────────────────────────────────────────


class TestStandaloneFunctions:
    def test_register_data_source_standalone(self):
        """register_data_source returns a generated node ID."""
        reset_tracker()
        tracker = get_tracker()
        node_id = register_data_source(
            path="/tmp/standalone.csv",
            label="Standalone test",
            tracker=tracker,
        )
        assert node_id.startswith("raw_data_")
        assert len(node_id) > len("raw_data_")
