"""Integration tests for scripts/core/provenance.py"""

from scripts.core.provenance import (
    ProvenanceChain,
    ProvenanceNode,
    compute_checksum,
    compute_checksum_long,
    NodeType,
)


class TestProvenanceNode:
    """Tests for ProvenanceNode."""

    def test_node_creation(self):
        """ProvenanceNode can be created with required args."""
        node = ProvenanceNode(node_id="n1", node_type=NodeType.RAW_DATA, label="Raw CSV")
        assert node.node_type == NodeType.RAW_DATA
        assert node.node_id == "n1"
        assert node.label == "Raw CSV"

    def test_node_with_all_fields(self):
        """ProvenanceNode accepts all optional fields."""
        node = ProvenanceNode(
            node_id="n2",
            node_type=NodeType.CODE,
            label="Data cleaning script",
            content="import pandas as pd",
            metadata={"lines": 50},
        )
        assert node.node_type == NodeType.CODE
        assert node.label == "Data cleaning script"
        assert node.content == "import pandas as pd"
        assert node.metadata["lines"] == 50

    def test_node_add_parent(self):
        """add_parent appends parent_id without duplicates."""
        node = ProvenanceNode(node_id="n3", node_type=NodeType.OUTPUT, label="Reg output")
        node.add_parent("n1")
        node.add_parent("n2")
        node.add_parent("n1")  # duplicate
        assert node.parent_ids == ["n1", "n2"]

    def test_node_add_child(self):
        """add_child appends child_id without duplicates."""
        node = ProvenanceNode(node_id="n1", node_type=NodeType.RAW_DATA, label="input")
        node.add_child("n2")
        node.add_child("n3")
        node.add_child("n2")  # duplicate
        assert node.child_ids == ["n2", "n3"]

    def test_node_to_dict(self):
        """to_dict returns a serializable dict."""
        node = ProvenanceNode(
            node_id="n4",
            node_type=NodeType.CHART,
            label="ROC Curve",
            metadata={"dpi": 300},
        )
        d = node.to_dict()
        assert isinstance(d, dict)
        assert d["node_id"] == "n4"
        assert d["node_type"] == "chart"
        assert d["label"] == "ROC Curve"
        assert d["metadata"]["dpi"] == 300


class TestProvenanceChain:
    """Tests for ProvenanceChain."""

    def test_chain_creation(self, tmp_path):
        """ProvenanceChain initializes with empty state."""
        chain = ProvenanceChain(project_dir=tmp_path)
        assert chain.nodes == {}
        assert chain.links == []

    def test_register_node(self, tmp_path):
        """register_node adds node to chain and returns node_id."""
        chain = ProvenanceChain(project_dir=tmp_path)
        node = ProvenanceNode(node_id="n5", node_type=NodeType.RAW_DATA, label="Raw CSV")
        node_id = chain.register_node(node)
        assert node_id == "n5"
        assert node_id in chain.nodes
        assert chain.nodes[node_id] is node

    def test_register_multiple_nodes(self, tmp_path):
        """Multiple nodes can be registered."""
        chain = ProvenanceChain(project_dir=tmp_path)
        n1 = ProvenanceNode(node_id="n1", node_type=NodeType.RAW_DATA, label="raw")
        n2 = ProvenanceNode(node_id="n2", node_type=NodeType.CODE, label="clean")
        n3 = ProvenanceNode(node_id="n3", node_type=NodeType.OUTPUT, label="result")
        chain.register_node(n1)
        chain.register_node(n2)
        chain.register_node(n3)
        assert len(chain.nodes) == 3

    def test_register_node_overwrites_existing(self, tmp_path):
        """register_node silently overwrites an existing node with the same id."""
        chain = ProvenanceChain(project_dir=tmp_path)
        n1 = ProvenanceNode(node_id="fixed_id", node_type=NodeType.RAW_DATA, label="first")
        n2 = ProvenanceNode(node_id="fixed_id", node_type=NodeType.CODE, label="second")
        chain.register_node(n1)
        chain.register_node(n2)  # silently overwrites
        assert chain.nodes["fixed_id"].label == "second"


class TestNodeTypes:
    """Tests for NodeType enum."""

    def test_node_type_values(self):
        """NodeType enum has expected variants."""
        assert NodeType.RAW_DATA in NodeType
        assert NodeType.CLEANED_DATA in NodeType
        assert NodeType.CODE in NodeType
        assert NodeType.OUTPUT in NodeType
        assert NodeType.CHART in NodeType
        assert NodeType.TABLE in NodeType

    def test_node_type_is_enum(self):
        """NodeType values are all strings."""
        for member in NodeType:
            assert isinstance(member.value, str)


class TestChecksum:
    """Tests for checksum functions."""

    def test_compute_checksum_dict(self):
        """compute_checksum returns 16-char short hash for dict input."""
        c = compute_checksum({"key": "value", "num": 42})
        assert isinstance(c, str)
        assert len(c) == 16  # short hash (v3 enhancement; full SHA-256 via compute_checksum_long)

    def test_compute_checksum_list(self):
        """compute_checksum returns consistent hash for list."""
        c1 = compute_checksum([1, 2, 3])
        c2 = compute_checksum([1, 2, 3])
        assert c1 == c2
        assert len(c1) == 16

    def test_compute_checksum_string(self):
        """compute_checksum returns consistent hash for string."""
        c = compute_checksum("hello world")
        assert isinstance(c, str)
        assert len(c) == 16

    def test_compute_checksum_none(self):
        """compute_checksum handles None input."""
        c = compute_checksum(None)
        assert c == "0" * 16

    def test_compute_checksum_deterministic(self):
        """compute_checksum is deterministic across calls."""
        data = {"a": 1, "b": [2, 3], "c": "text"}
        results = [compute_checksum(data) for _ in range(5)]
        assert len(set(results)) == 1  # all identical

    def test_compute_checksum_long(self):
        """compute_checksum_long returns 64-char full SHA-256."""
        c = compute_checksum_long({"key": "value"})
        assert isinstance(c, str)
        assert len(c) == 64
        assert all(ch in "0123456789abcdef" for ch in c)

    def test_checksum_distinguishes_input(self):
        """Different inputs produce different checksums."""
        c1 = compute_checksum({"x": 1})
        c2 = compute_checksum({"x": 2})
        c3 = compute_checksum({"y": 1})
        assert c1 != c2
        assert c1 != c3
        assert c2 != c3

    def test_checksum_long_distinguishes_input(self):
        """compute_checksum_long distinguishes different inputs."""
        c1 = compute_checksum_long({"x": 1})
        c2 = compute_checksum_long({"x": 2})
        assert c1 != c2

    def test_checksum_with_nested_data(self):
        """compute_checksum handles nested data structures."""
        data = {"level1": {"level2": {"level3": [1, 2, {"a": 3}]}}}
        c = compute_checksum(data)
        assert isinstance(c, str)
        assert len(c) == 16


class TestProvenanceRoundTrip:
    """Integration: register nodes, verify chain integrity."""

    def test_node_to_dict_roundtrip(self):
        """ProvenanceNode.to_dict() produces a serializable dict."""
        node = ProvenanceNode(
            node_id="n6",
            node_type=NodeType.CHART,
            label="ROC Curve",
            metadata={"dpi": 300},
        )
        d = node.to_dict()
        assert isinstance(d, dict)
        assert d["node_type"] == "chart"
        assert d["label"] == "ROC Curve"
        assert d["metadata"]["dpi"] == 300

    def test_chain_register_with_auto_id(self, tmp_path):
        """register_node auto-generates node_id when node_id is empty."""
        chain = ProvenanceChain(project_dir=tmp_path)
        node = ProvenanceNode(node_id="", node_type=NodeType.OUTPUT, label="output")
        returned_id = chain.register_node(node)
        assert returned_id.startswith("output_")
        assert returned_id in chain.nodes

    def test_chain_parent_child_relationship(self, tmp_path):
        """Nodes can form parent-child relationships via add_parent/add_child."""
        chain = ProvenanceChain(project_dir=tmp_path)
        n1 = ProvenanceNode(node_id="data", node_type=NodeType.RAW_DATA, label="raw")
        n2 = ProvenanceNode(node_id="clean", node_type=NodeType.CLEANED_DATA, label="cleaned")
        n3 = ProvenanceNode(node_id="result", node_type=NodeType.OUTPUT, label="result")

        # Build relationships BEFORE registering
        n2.add_parent("data")
        n1.add_child("clean")
        n3.add_parent("clean")
        n3.add_parent("data")
        n2.add_child("result")
        n1.add_child("result")

        chain.register_node(n1)
        chain.register_node(n2)
        chain.register_node(n3)

        assert chain.nodes["data"].child_ids == ["clean", "result"]
        assert chain.nodes["clean"].parent_ids == ["data"]
        assert chain.nodes["clean"].child_ids == ["result"]
        assert set(chain.nodes["result"].parent_ids) == {"clean", "data"}
