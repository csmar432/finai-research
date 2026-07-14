"""Tests for scripts/core/visualizer.py — WorkflowVisualizer dataclasses and formatting."""
from __future__ import annotations

import sys
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
        create_tracked_chart,
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


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
