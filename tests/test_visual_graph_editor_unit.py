"""Unit tests for scripts/core/visual_graph_editor.py.

Covers: NodeType, PipelineNode, PipelineEdge, PipelineGraph, PipelineBuilder,
load_pipeline, and quick_build.

Test conventions:
  - Synthetic data only — no network calls.
  - Uses tmp_path fixture for file I/O where needed.
  - Deterministic, no timing dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.visual_graph_editor import (
    NodeType,
    PipelineBuilder,
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    load_pipeline,
    quick_build,
)


# ═══════════════════════════════════════════════════════════════════════════
# NodeType Enum
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeType:
    """Tests for the NodeType enum."""

    @pytest.mark.parametrize(
        "member,expected_value",
        [
            (NodeType.AGENT, "agent"),
            (NodeType.GATE, "gate"),
            (NodeType.MERGE, "merge"),
            (NodeType.SPLIT, "split"),
            (NodeType.INPUT, "input"),
            (NodeType.OUTPUT, "output"),
        ],
    )
    def test_node_type_values(self, member, expected_value):
        assert member.value == expected_value

    def test_node_type_count(self):
        assert len(NodeType) == 6


# ═══════════════════════════════════════════════════════════════════════════
# PipelineNode Dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineNode:
    """Tests for the PipelineNode dataclass."""

    def test_init_required_fields(self):
        node = PipelineNode("node1", NodeType.AGENT, "OutlineAgent")
        assert node.id == "node1"
        assert node.node_type == NodeType.AGENT
        assert node.label == "OutlineAgent"
        assert node.config == {}
        assert node.position is None

    def test_init_all_fields(self):
        node = PipelineNode(
            id="node2",
            node_type=NodeType.GATE,
            label="HITL Gate",
            config={"after_agent": "literature", "enabled": True},
            position=(1.0, 2.5),
        )
        assert node.id == "node2"
        assert node.node_type == NodeType.GATE
        assert node.label == "HITL Gate"
        assert node.config == {"after_agent": "literature", "enabled": True}
        assert node.position == (1.0, 2.5)

    def test_init_defaults(self):
        node = PipelineNode("default_test", NodeType.INPUT, "Input")
        assert node.config == {}
        assert node.position is None


# ═══════════════════════════════════════════════════════════════════════════
# PipelineEdge Dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineEdge:
    """Tests for the PipelineEdge dataclass."""

    def test_init_required_fields(self):
        edge = PipelineEdge(source="node_a", target="node_b")
        assert edge.source == "node_a"
        assert edge.target == "node_b"
        assert edge.condition is None

    def test_init_with_condition(self):
        edge = PipelineEdge(
            source="task1",
            target="task2",
            condition="if score > 7",
        )
        assert edge.source == "task1"
        assert edge.target == "task2"
        assert edge.condition == "if score > 7"


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Init & CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphInit:
    def test_init_name(self):
        graph = PipelineGraph(name="paper_pipeline")
        assert graph.name == "paper_pipeline"

    def test_init_empty_nodes_edges(self):
        graph = PipelineGraph(name="empty")
        assert graph.nodes == []
        assert graph.edges == []


class TestPipelineGraphAddNode:
    def test_add_node_success(self):
        graph = PipelineGraph(name="test")
        node = PipelineNode("outline", NodeType.AGENT, "OutlineAgent")
        graph.add_node(node)
        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "outline"

    def test_add_node_duplicate_raises(self):
        graph = PipelineGraph(name="test")
        node1 = PipelineNode("dup", NodeType.AGENT, "Agent1")
        node2 = PipelineNode("dup", NodeType.AGENT, "Agent2")
        graph.add_node(node1)
        with pytest.raises(ValueError, match="already exists"):
            graph.add_node(node2)


class TestPipelineGraphAddEdge:
    def test_add_edge_success(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "AgentA"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "AgentB"))
        graph.add_edge("a", "b")
        assert len(graph.edges) == 1
        assert graph.edges[0].source == "a"
        assert graph.edges[0].target == "b"

    def test_add_edge_missing_source_raises(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("b", NodeType.AGENT, "AgentB"))
        with pytest.raises(ValueError, match="Source node .* does not exist"):
            graph.add_edge("ghost", "b")

    def test_add_edge_missing_target_raises(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "AgentA"))
        with pytest.raises(ValueError, match="Target node .* does not exist"):
            graph.add_edge("a", "ghost")

    def test_add_edge_with_condition(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "AgentA"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "AgentB"))
        graph.add_edge("a", "b", condition="on_failure")
        assert graph.edges[0].condition == "on_failure"


class TestPipelineGraphRemoveNode:
    def test_remove_node(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_edge("a", "b")
        graph.remove_node("a")
        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "b"
        assert len(graph.edges) == 0

    def test_remove_node_removes_connected_edges(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_node(PipelineNode("c", NodeType.AGENT, "C"))
        graph.add_edge("a", "b")
        graph.add_edge("a", "c")
        graph.remove_node("a")
        assert len(graph.edges) == 0


class TestPipelineGraphGetNode:
    def test_get_node_found(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("found", NodeType.AGENT, "FoundAgent"))
        result = graph.get_node("found")
        assert result is not None
        assert result.id == "found"

    def test_get_node_not_found(self):
        graph = PipelineGraph(name="test")
        result = graph.get_node("nonexistent")
        assert result is None


class TestPipelineGraphSuccessorsPredecessors:
    def test_successors(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_node(PipelineNode("c", NodeType.AGENT, "C"))
        graph.add_edge("a", "b")
        graph.add_edge("a", "c")
        result = graph.successors("a")
        ids = {n.id for n in result}
        assert ids == {"b", "c"}

    def test_predecessors(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_node(PipelineNode("c", NodeType.AGENT, "C"))
        graph.add_edge("a", "c")
        graph.add_edge("b", "c")
        result = graph.predecessors("c")
        ids = {n.id for n in result}
        assert ids == {"a", "b"}

    def test_successors_none(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("isolated", NodeType.AGENT, "I"))
        result = graph.successors("isolated")
        assert result == []

    def test_predecessors_none(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("root", NodeType.INPUT, "Input"))
        result = graph.predecessors("root")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Cycle Detection & Reachability
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphHasCycle:
    def test_no_cycle_simple_chain(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_node(PipelineNode("c", NodeType.AGENT, "C"))
        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        assert graph._has_cycle() is False

    def test_no_cycle_diamond(self):
        graph = PipelineGraph(name="test")
        for n in [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]:
            graph.add_node(PipelineNode(n[0], NodeType.AGENT, n[1]))
        graph.add_edge("a", "b")
        graph.add_edge("a", "c")
        graph.add_edge("b", "d")
        graph.add_edge("c", "d")
        assert graph._has_cycle() is False

    def test_has_cycle_simple(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_edge("a", "b")
        graph.add_edge("b", "a")
        assert graph._has_cycle() is True

    def test_has_cycle_three_node_loop(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_node(PipelineNode("c", NodeType.AGENT, "C"))
        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        graph.add_edge("c", "a")
        assert graph._has_cycle() is True

    def test_no_cycle_empty_graph(self):
        graph = PipelineGraph(name="empty")
        assert graph._has_cycle() is False


class TestPipelineGraphReachableNodes:
    def test_reachable_from_start(self):
        graph = PipelineGraph(name="test")
        for n in [("a", "A"), ("b", "B"), ("c", "C")]:
            graph.add_node(PipelineNode(n[0], NodeType.AGENT, n[1]))
        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        result = graph._reachable_nodes("a")
        assert result == {"a", "b", "c"}

    def test_reachable_isolated_node(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("isolated", NodeType.AGENT, "I"))
        result = graph._reachable_nodes("isolated")
        assert result == {"isolated"}

    def test_reachable_nonexistent_start(self):
        graph = PipelineGraph(name="test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        # Implementation adds start to reachable set even if not a real node
        result = graph._reachable_nodes("ghost")
        assert result == {"ghost"}


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphValidate:
    def test_validate_empty_graph(self):
        graph = PipelineGraph(name="empty")
        warnings = graph.validate()
        assert warnings == []

    def test_validate_valid_pipeline(self):
        graph = PipelineGraph(name="valid")
        graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))
        graph.add_node(PipelineNode("outline", NodeType.AGENT, "OutlineAgent"))
        graph.add_node(PipelineNode("output", NodeType.OUTPUT, "Output"))
        graph.add_edge("input", "outline")
        graph.add_edge("outline", "output")
        warnings = graph.validate()
        assert warnings == []

    def test_validate_cycle_error(self):
        graph = PipelineGraph(name="cyclic")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        graph.add_node(PipelineNode("b", NodeType.AGENT, "B"))
        graph.add_edge("a", "b")
        graph.add_edge("b", "a")
        warnings = graph.validate()
        assert any("cycle" in w.lower() for w in warnings)

    def test_validate_unreachable_nodes(self):
        graph = PipelineGraph(name="unreachable")
        graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))
        graph.add_node(PipelineNode("reachable", NodeType.AGENT, "R"))
        graph.add_node(PipelineNode("unreachable", NodeType.AGENT, "U"))
        graph.add_edge("input", "reachable")
        warnings = graph.validate()
        assert any("unreachable" in w.lower() for w in warnings)

    def test_validate_dead_end_warning(self):
        graph = PipelineGraph(name="deadend")
        graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))
        graph.add_node(PipelineNode("orphan", NodeType.AGENT, "O"))
        graph.add_edge("input", "orphan")
        warnings = graph.validate()
        assert any("dead end" in w.lower() or "no successors" in w.lower() for w in warnings)

    def test_validate_multiple_outputs_warning(self):
        graph = PipelineGraph(name="multi_output")
        graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))
        graph.add_node(PipelineNode("out1", NodeType.OUTPUT, "Out1"))
        graph.add_node(PipelineNode("out2", NodeType.OUTPUT, "Out2"))
        graph.add_edge("input", "out1")
        graph.add_edge("input", "out2")
        warnings = graph.validate()
        assert any("multiple output" in w.lower() for w in warnings)


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Serialization
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphToDict:
    def test_to_dict_basic(self):
        graph = PipelineGraph(name="dict_test")
        graph.add_node(PipelineNode(
            "outline", NodeType.AGENT, "OutlineAgent",
            config={"agent_name": "OutlineAgent", "hitl": False},
        ))
        graph.add_node(PipelineNode(
            "literature", NodeType.GATE, "HITL Gate",
            config={"after_agent": "outline"},
        ))
        graph.add_edge("outline", "literature", condition="on_success")
        d = graph.to_dict()
        assert d["name"] == "dict_test"
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 1
        assert d["edges"][0]["source"] == "outline"
        assert d["edges"][0]["target"] == "literature"
        assert d["edges"][0]["condition"] == "on_success"


class TestPipelineGraphToJson:
    def test_to_json_returns_string(self):
        graph = PipelineGraph(name="json_test")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        result = graph.to_json()
        assert isinstance(result, str)
        data = json.loads(result)
        assert data["name"] == "json_test"

    def test_to_json_writes_file(self, tmp_path):
        graph = PipelineGraph(name="file_test")
        graph.add_node(PipelineNode("x", NodeType.INPUT, "X"))
        path = tmp_path / "graph.json"
        result = graph.to_json(path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == "file_test"


class TestPipelineGraphToYamlDict:
    def test_to_yaml_dict_structure(self):
        graph = PipelineGraph(name="yaml_test")
        graph.add_node(PipelineNode(
            "outline", NodeType.AGENT, "OutlineAgent",
            config={"agent_name": "OutlineAgent", "hitl": False},
        ))
        graph.add_node(PipelineNode(
            "literature", NodeType.AGENT, "LiteratureAgent",
            config={"agent_name": "LiteratureAgent", "hitl": True},
        ))
        result = graph.to_yaml_dict()
        assert "pipelines" in result
        assert "yaml_test" in result["pipelines"]
        pipeline = result["pipelines"]["yaml_test"]
        assert pipeline["name"] == "yaml_test"
        assert len(pipeline["steps"]) == 2
        assert pipeline["steps"][0]["agent"] == "OutlineAgent"
        assert pipeline["steps"][0]["hitl_gate"] is False
        assert pipeline["steps"][1]["hitl_gate"] is True


class TestPipelineGraphToMarkdown:
    def test_to_markdown_structure(self):
        graph = PipelineGraph(name="md_test")
        graph.add_node(PipelineNode("outline", NodeType.AGENT, "OutlineAgent"))
        graph.add_node(PipelineNode("literature", NodeType.AGENT, "LitAgent"))
        graph.add_edge("outline", "literature", condition="on_success")
        md = graph.to_markdown()
        assert "# Pipeline: md_test" in md
        assert "outline" in md
        assert "literature" in md
        assert "on_success" in md
        assert "| ID |" in md


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Visualization (mock-safe)
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphVisualize:
    def test_visualize_without_deps_warns(self, caplog):
        graph = PipelineGraph(name="noviz")
        graph.add_node(PipelineNode("a", NodeType.AGENT, "A"))
        # Force _HAS_VISUAL = False by patching
        import scripts.core.visual_graph_editor as vge
        original = vge._HAS_VISUAL
        vge._HAS_VISUAL = False
        try:
            graph.visualize()
        finally:
            vge._HAS_VISUAL = original
        assert any("not available" in r.message.lower() for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════
# PipelineGraph — Class Methods
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineGraphFromAgentsYaml:
    def test_from_agents_yaml_basic(self, tmp_path):
        yaml_content = """
pipelines:
  test_pipeline:
    name: test_pipeline
    steps:
      - agent: OutlineAgent
        stage: OUTLINE
        hitl_gate: false
      - agent: LiteratureAgent
        stage: LITERATURE
        hitl_gate: true
"""
        yaml_path = tmp_path / "agents.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        graph = PipelineGraph.from_agents_yaml(yaml_path)
        assert graph.name == "test_pipeline"
        node_ids = {n.id for n in graph.nodes}
        assert "input" in node_ids
        assert "outline" in node_ids
        assert "literature" in node_ids
        assert "output" in node_ids

    def test_from_agents_yaml_no_pipelines_key_raises(self, tmp_path):
        yaml_path = tmp_path / "invalid.yaml"
        yaml_path.write_text("agents:\n  - name: x\n", encoding="utf-8")
        with pytest.raises(ValueError, match="No 'pipelines' key"):
            PipelineGraph.from_agents_yaml(yaml_path)

    def test_from_agents_yaml_preserves_hitl(self, tmp_path):
        yaml_content = """
pipelines:
  hitl_test:
    name: hitl_test
    steps:
      - agent: WriteAgent
        stage: WRITE
        hitl_gate: true
"""
        yaml_path = tmp_path / "hitl.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        graph = PipelineGraph.from_agents_yaml(yaml_path)
        lit_node = graph.get_node("write")
        assert lit_node is not None
        assert lit_node.config.get("hitl") is True


class TestPipelineGraphFromDict:
    def test_from_dict_roundtrip(self):
        graph_original = PipelineGraph(name="roundtrip")
        graph_original.add_node(PipelineNode(
            "node1", NodeType.AGENT, "Agent1",
            config={"key": "value"},
            position=(0.5, 1.0),
        ))
        graph_original.add_node(PipelineNode(
            "node2", NodeType.AGENT, "Agent2",
        ))
        graph_original.add_edge("node1", "node2")
        d = graph_original.to_dict()
        graph_restored = PipelineGraph.from_dict(d)
        assert graph_restored.name == "roundtrip"
        assert len(graph_restored.nodes) == 2
        assert graph_restored.nodes[0].config.get("key") == "value"
        assert len(graph_restored.edges) == 1

    def test_from_dict_missing_fields(self):
        graph = PipelineGraph.from_dict({"name": "minimal"})
        assert graph.name == "minimal"
        assert graph.nodes == []
        assert graph.edges == []


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — add_agent
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderAddAgent:
    def test_add_agent_basic(self):
        builder = PipelineBuilder("builder_test")
        result = builder.add_agent("outline", "OutlineAgent")
        assert result is builder
        assert builder.graph.get_node("outline") is not None

    def test_add_agent_with_hitl(self):
        builder = PipelineBuilder("hitl_test")
        builder.add_agent("lit", "LiteratureAgent", hitl=True)
        node = builder.graph.get_node("lit")
        assert node.config.get("hitl") is True

    def test_add_agent_with_extra_config(self):
        builder = PipelineBuilder("extra_test")
        builder.add_agent("task", "TaskAgent", timeout=300, retries=3)
        node = builder.graph.get_node("task")
        assert node.config.get("timeout") == 300
        assert node.config.get("retries") == 3


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — then
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderThen:
    def test_then_basic(self):
        builder = PipelineBuilder("then_test")
        builder.add_agent("first", "FirstAgent")
        result = builder.then("second", "SecondAgent")
        assert result is builder
        assert builder.graph.get_node("second") is not None
        assert len(builder.graph.edges) == 1

    def test_then_chains_correctly(self):
        builder = PipelineBuilder("chain_test")
        builder.add_agent("a", "AAgent").then("b", "BAgent").then("c", "CAgent")
        edge_targets = {e.target for e in builder.graph.edges}
        assert edge_targets == {"b", "c"}

    def test_then_no_previous_agent_raises(self):
        builder = PipelineBuilder("no_prev")
        with pytest.raises(ValueError, match="no previous agent"):
            builder.then("orphan", "OrphanAgent")


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — with_hitl
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderWithHitl:
    def test_with_hitl_adds_gate_node(self):
        builder = PipelineBuilder("hitl_gate_test")
        builder.add_agent("lit", "LiteratureAgent").then("next", "NextAgent")
        builder.with_hitl("lit")
        gate_node = builder.graph.get_node("lit_hitl_gate")
        assert gate_node is not None
        assert gate_node.node_type == NodeType.GATE

    def test_with_hitl_rewires_edges(self):
        builder = PipelineBuilder("rewire_test")
        builder.add_agent("a", "AAgent").then("b", "BAgent")
        builder.with_hitl("a")
        # Old a->b edge should be replaced by a->gate->b
        edge_pairs = {(e.source, e.target) for e in builder.graph.edges}
        assert ("a", "b") not in edge_pairs
        assert ("a", "a_hitl_gate") in edge_pairs
        assert ("a_hitl_gate", "b") in edge_pairs

    def test_with_hitl_no_successor_adds_edge(self):
        builder = PipelineBuilder("no_succ_test")
        builder.add_agent("solo", "SoloAgent")
        builder.with_hitl("solo")
        gate_node = builder.graph.get_node("solo_hitl_gate")
        assert gate_node is not None
        edge_targets = {e.target for e in builder.graph.edges}
        assert "solo_hitl_gate" in edge_targets


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — parallel
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderParallel:
    def test_parallel_adds_split_and_merge(self):
        builder = PipelineBuilder("parallel_test")
        builder.add_agent("start", "StartAgent")
        # parallel() wires from "start" to split, then split to each agent,
        # then each agent to merge — agents must be added as nodes first
        builder.graph.add_node(PipelineNode("branch_a", NodeType.AGENT, "BranchA"))
        builder.graph.add_node(PipelineNode("branch_b", NodeType.AGENT, "BranchB"))
        builder.parallel(["branch_a", "branch_b"], after="start")
        node_ids = {n.id for n in builder.graph.nodes}
        assert "split_start" in node_ids
        assert "merge_start" in node_ids
        assert "branch_a" in node_ids
        assert "branch_b" in node_ids

    def test_parallel_wires_correctly(self):
        builder = PipelineBuilder("wire_test")
        builder.add_agent("root", "RootAgent")
        builder.graph.add_node(PipelineNode("task1", NodeType.AGENT, "Task1"))
        builder.graph.add_node(PipelineNode("task2", NodeType.AGENT, "Task2"))
        builder.parallel(["task1", "task2"], after="root")
        edge_pairs = {(e.source, e.target) for e in builder.graph.edges}
        assert ("root", "split_root") in edge_pairs
        assert ("split_root", "task1") in edge_pairs
        assert ("split_root", "task2") in edge_pairs
        assert ("task1", "merge_root") in edge_pairs
        assert ("task2", "merge_root") in edge_pairs


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — on_failure
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderOnFailure:
    def test_on_failure_adds_conditional_edge(self):
        builder = PipelineBuilder("fail_test")
        builder.add_agent("risky", "RiskyAgent")
        # on_failure creates edge to fallback_agent - it must exist as a node
        builder.graph.add_node(PipelineNode("fallback", NodeType.AGENT, "FallbackAgent"))
        builder.on_failure("fallback")
        edges = [(e.source, e.target, e.condition) for e in builder.graph.edges]
        assert ("risky", "fallback", "on_failure") in edges

    def test_on_failure_no_op_without_agent(self):
        builder = PipelineBuilder("no_agent")
        result = builder.on_failure("backup")
        assert result is builder
        assert len(builder.graph.edges) == 0


# ═══════════════════════════════════════════════════════════════════════════
# PipelineBuilder — build
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineBuilderBuild:
    def test_build_adds_input_output(self):
        builder = PipelineBuilder("io_test")
        builder.add_agent("a", "AAgent").then("b", "BAgent")
        graph = builder.build()
        node_ids = {n.id for n in graph.nodes}
        assert "input" in node_ids
        assert "output" in node_ids

    def test_build_wires_input_to_first(self):
        builder = PipelineBuilder("wire_first")
        builder.add_agent("first", "FirstAgent")
        graph = builder.build()
        edge_targets = {e.target for e in graph.edges}
        assert "first" in edge_targets

    def test_build_wires_last_to_output(self):
        builder = PipelineBuilder("wire_last")
        builder.add_agent("last", "LastAgent")
        graph = builder.build()
        edge_sources = {e.source for e in graph.edges}
        assert "last" in edge_sources

    def test_build_no_duplicates_if_input_exists(self):
        builder = PipelineBuilder("no_dup")
        builder.add_agent("a", "AAgent")
        # Manually add input node
        builder.graph.add_node(PipelineNode("input", NodeType.INPUT, "CustomInput"))
        graph = builder.build()
        input_nodes = [n for n in graph.nodes if n.id == "input"]
        assert len(input_nodes) == 1


class TestPipelineBuilderFirstAgent:
    def test_first_agent_returns_first_agent(self):
        builder = PipelineBuilder("first_test")
        builder.add_agent("a", "AAgent").then("b", "BAgent")
        result = builder._first_agent()
        assert result == "a"

    def test_first_agent_none_when_empty(self):
        builder = PipelineBuilder("empty_first")
        result = builder._first_agent()
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Module-level Functions
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadPipeline:
    def test_load_pipeline_basic(self, tmp_path):
        yaml_content = """
pipelines:
  loaded:
    name: loaded
    steps:
      - agent: OutlineAgent
        stage: OUTLINE
"""
        yaml_path = tmp_path / "agents.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        graph = load_pipeline(yaml_path)
        assert graph.name == "loaded"
        assert len(graph.nodes) >= 2


class TestQuickBuild:
    def test_quick_build_single_agent(self):
        graph = quick_build("quick1", "outline")
        assert graph.name == "quick1"
        assert graph.get_node("outline") is not None

    def test_quick_build_multiple_agents(self):
        graph = quick_build("quick2", "outline", "literature", "writing")
        assert graph.get_node("outline") is not None
        assert graph.get_node("literature") is not None
        assert graph.get_node("writing") is not None
        # build() auto-wires INPUT→first→...→last→OUTPUT, so edge_targets
        # includes all agent ids AND the "output" node
        edge_targets = {e.target for e in graph.edges}
        assert "outline" in edge_targets
        assert "literature" in edge_targets
        assert "writing" in edge_targets
        assert "output" in edge_targets

    def test_quick_build_validates(self):
        graph = quick_build("valid_quick", "a", "b")
        warnings = graph.validate()
        assert warnings == []


# ═══════════════════════════════════════════════════════════════════════════
# Integration-style: Full Pipeline Construction
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipelineConstruction:
    """Integration tests for the full fluent pipeline construction."""

    def test_full_fluent_pipeline(self):
        graph = (
            PipelineBuilder("paper_pipeline")
            .add_agent("outline", "OutlineAgent")
            .then("literature", "LiteratureReviewAgent")
            .with_hitl("literature")
            .then("plotting", "PlottingAgent")
            .then("writing", "SectionWritingAgent")
            .then("refinement", "RefinementAgent")
            .build()
        )
        assert graph.name == "paper_pipeline"
        node_ids = {n.id for n in graph.nodes}
        assert "input" in node_ids
        assert "output" in node_ids
        assert "literature_hitl_gate" in node_ids
        # Validate should pass (no cycles, all reachable)
        warnings = graph.validate()
        cycle_warnings = [w for w in warnings if "cycle" in w.lower()]
        assert cycle_warnings == []

    def test_pipeline_with_parallel_branches(self):
        builder = PipelineBuilder("parallel_pipeline")
        builder.add_agent("split_point", "SplitAgent")
        # parallel() wires to existing agent nodes passed in the agents list;
        # pre-create the branch nodes
        builder.graph.add_node(PipelineNode("branch_a", NodeType.AGENT, "BranchA"))
        builder.graph.add_node(PipelineNode("branch_b", NodeType.AGENT, "BranchB"))
        builder.parallel(["branch_a", "branch_b"], after="split_point")
        assert builder.graph.get_node("split_point") is not None
        assert builder.graph.get_node("branch_a") is not None
        assert builder.graph.get_node("branch_b") is not None
        assert builder.graph._has_cycle() is False

    def test_pipeline_serialization_roundtrip(self):
        graph = (
            PipelineBuilder("roundtrip")
            .add_agent("a", "AAgent")
            .then("b", "BAgent", hitl=True)
            .build()
        )
        d = graph.to_dict()
        restored = PipelineGraph.from_dict(d)
        assert restored.name == graph.name
        assert len(restored.nodes) == len(graph.nodes)
        assert len(restored.edges) == len(graph.edges)


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases & Robustness
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_graph_with_unicode_node_ids(self):
        graph = PipelineGraph(name="unicode")
        graph.add_node(PipelineNode("节点_α", NodeType.AGENT, "AlphaAgent"))
        assert graph.get_node("节点_α") is not None
        d = graph.to_json()
        assert "节点_α" in d

    def test_graph_validate_isolated_gate_allowed(self):
        graph = PipelineGraph(name="gate_only")
        graph.add_node(PipelineNode("gate", NodeType.GATE, "Gate"))
        warnings = graph.validate()
        # Gates are allowed to be dead ends
        dangling_warnings = [w for w in warnings if "no successors" in w.lower()]
        assert len(dangling_warnings) == 0

    def test_node_position_preserved_in_to_dict(self):
        graph = PipelineGraph(name="pos_test")
        graph.add_node(PipelineNode("pos_node", NodeType.AGENT, "P",
                                    position=(10.5, 20.5)))
        d = graph.to_dict()
        assert d["nodes"][0]["position"] == (10.5, 20.5)

    def test_from_dict_preserves_position(self):
        graph = PipelineGraph(name="pos_restore")
        graph.add_node(PipelineNode("p", NodeType.AGENT, "P", position=(1.0, 2.0)))
        restored = PipelineGraph.from_dict(graph.to_dict())
        restored_node = restored.get_node("p")
        assert restored_node.position == (1.0, 2.0)

    def test_builder_then_with_extra_config(self):
        builder = PipelineBuilder("config_test")
        builder.add_agent("a", "A")
        builder.then("b", "B", priority=5, retries=2)
        b_node = builder.graph.get_node("b")
        assert b_node.config.get("priority") == 5
        assert b_node.config.get("retries") == 2
