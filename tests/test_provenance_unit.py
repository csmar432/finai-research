"""Unit tests for scripts/core/provenance.py"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from scripts.core.provenance import (
    ChartMetadata,
    NodeType,
    ProvenanceChain,
    ProvenanceLink,
    ProvenanceNode,
    ProvenanceTracker,
    SourceRef,
    compute_checksum,
    compute_checksum_long,
    get_chain,
    get_tracker,
    inject_provenance_into_latex,
    latex_provenance_comment,
    record_transform,
    register_chart,
    register_data_source,
    reset_tracker,
    set_tracker,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for file-based tests."""
    return tmp_path


@pytest.fixture
def chain(temp_dir):
    """Create a fresh ProvenanceChain for each test."""
    reset_tracker()
    return ProvenanceChain(project_dir=str(temp_dir / "provenance"))


@pytest.fixture
def tracker(temp_dir):
    """Create a fresh ProvenanceTracker for each test."""
    reset_tracker()
    return ProvenanceTracker(project_dir=str(temp_dir / "provenance"))


# ─── NodeType Enum Tests ────────────────────────────────────────────────────


class TestNodeType:
    """Tests for the NodeType enum."""

    @pytest.mark.parametrize(
        "member,expected_value",
        [
            (NodeType.RAW_DATA, "raw_data"),
            (NodeType.CLEANED_DATA, "cleaned_data"),
            (NodeType.VARIABLE, "variable"),
            (NodeType.CODE, "code"),
            (NodeType.OUTPUT, "output"),
            (NodeType.CHART, "chart"),
            (NodeType.TABLE, "table"),
            (NodeType.PARAGRAPH, "paragraph"),
            (NodeType.NUMBER, "number"),
            (NodeType.CITATION, "citation"),
            (NodeType.MODEL, "model"),
        ],
    )
    def test_node_type_values(self, member, expected_value):
        """Verify all NodeType enum values are correct."""
        assert member.value == expected_value

    def test_node_type_count(self):
        """Verify NodeType has exactly 11 members."""
        assert len(NodeType) == 11


# ─── SourceRef Tests ───────────────────────────────────────────────────────


class TestSourceRef:
    """Tests for the SourceRef dataclass."""

    def test_source_ref_all_fields(self):
        """Test SourceRef with all fields."""
        src = SourceRef(
            type="file",
            path="/data/input.csv",
            line_start=10,
            line_end=20,
            query="SELECT * FROM table",
            checksum="abc123",
        )
        assert src.type == "file"
        assert src.path == "/data/input.csv"
        assert src.line_start == 10
        assert src.line_end == 20
        assert src.query == "SELECT * FROM table"
        assert src.checksum == "abc123"

    def test_source_ref_minimal(self):
        """Test SourceRef with only required fields."""
        src = SourceRef(type="api", path="https://api.example.com/data")
        assert src.type == "api"
        assert src.path == "https://api.example.com/data"
        assert src.line_start is None
        assert src.line_end is None
        assert src.query is None
        assert src.checksum is None

    def test_source_ref_defaults(self):
        """Test SourceRef default values."""
        src = SourceRef(type="db", path="postgres://localhost/mydb")
        assert src.type == "db"
        assert src.path == "postgres://localhost/mydb"
        assert src.line_start is None
        assert src.line_end is None
        assert src.query is None
        assert src.checksum is None


# ─── ProvenanceNode Tests ──────────────────────────────────────────────────


class TestProvenanceNode:
    """Tests for the ProvenanceNode dataclass."""

    def test_provenance_node_required_fields(self):
        """Test ProvenanceNode with only required fields."""
        node = ProvenanceNode(
            node_id="test_node_001",
            node_type=NodeType.RAW_DATA,
            label="Test Data",
        )
        assert node.node_id == "test_node_001"
        assert node.node_type == NodeType.RAW_DATA
        assert node.label == "Test Data"
        assert node.created_at is not None
        assert node.sources == []
        assert node.content == ""
        assert node.numeric_value is None
        assert node.numeric_context == ""
        assert node.parent_ids == []
        assert node.child_ids == []
        assert node.metadata == {}
        assert node.version == "1.0"

    def test_provenance_node_all_fields(self):
        """Test ProvenanceNode with all fields populated."""
        sources = [SourceRef(type="file", path="/data/test.csv")]
        node = ProvenanceNode(
            node_id="test_node_002",
            node_type=NodeType.NUMBER,
            label="Regression Coefficient",
            sources=sources,
            content="y = beta_1 * x + epsilon",
            numeric_value=0.0234,
            numeric_context="Table 2, Column (3)",
            parent_ids=["raw_data_001"],
            child_ids=["fig_001"],
            metadata={"p_value": 0.001, "std_error": 0.005},
            version="2.0",
        )
        assert node.node_id == "test_node_002"
        assert node.node_type == NodeType.NUMBER
        assert node.sources == sources
        assert node.numeric_value == 0.0234
        assert node.parent_ids == ["raw_data_001"]
        assert node.child_ids == ["fig_001"]
        assert node.metadata == {"p_value": 0.001, "std_error": 0.005}
        assert node.version == "2.0"

    def test_add_parent(self):
        """Test add_parent method."""
        node = ProvenanceNode(
            node_id="child_node",
            node_type=NodeType.OUTPUT,
            label="Child Node",
        )
        node.add_parent("parent_1")
        assert "parent_1" in node.parent_ids

        # Adding same parent twice should not duplicate
        node.add_parent("parent_1")
        assert node.parent_ids.count("parent_1") == 1

        node.add_parent("parent_2")
        assert len(node.parent_ids) == 2

    def test_add_child(self):
        """Test add_child method."""
        node = ProvenanceNode(
            node_id="parent_node",
            node_type=NodeType.CLEANED_DATA,
            label="Parent Node",
        )
        node.add_child("child_1")
        assert "child_1" in node.child_ids

        node.add_child("child_1")  # no duplicate
        assert node.child_ids.count("child_1") == 1

        node.add_child("child_2")
        assert len(node.child_ids) == 2

    def test_to_dict(self):
        """Test to_dict method."""
        sources = [SourceRef(type="file", path="/data/test.csv", checksum="hash123")]
        node = ProvenanceNode(
            node_id="node_dict_test",
            node_type=NodeType.CODE,
            label="Code Snippet",
            sources=sources,
            content="print('hello')",
            numeric_value=None,
            numeric_context="",
            parent_ids=["p1"],
            child_ids=["c1"],
            metadata={"author": "test"},
            version="1.0",
        )
        d = node.to_dict()

        assert d["node_id"] == "node_dict_test"
        assert d["node_type"] == "code"
        assert d["label"] == "Code Snippet"
        assert d["created_at"] is not None
        assert len(d["sources"]) == 1
        assert d["sources"][0]["path"] == "/data/test.csv"
        assert d["parent_ids"] == ["p1"]
        assert d["child_ids"] == ["c1"]
        assert d["metadata"] == {"author": "test"}

    def test_to_dict_truncates_long_content(self):
        """Test that to_dict truncates content over 500 characters."""
        long_content = "x = " + "a" * 600
        node = ProvenanceNode(
            node_id="long_node",
            node_type=NodeType.CODE,
            label="Long Content",
            content=long_content,
        )
        d = node.to_dict()
        assert len(d["content"]) < len(long_content)
        assert d["content"].endswith("...")


# ─── ProvenanceLink Tests ──────────────────────────────────────────────────


class TestProvenanceLink:
    """Tests for the ProvenanceLink dataclass."""

    def test_provenance_link_required_only(self):
        """Test ProvenanceLink with only required fields."""
        link = ProvenanceLink(
            link_id="link_001",
            source_id="source_node",
            target_id="target_node",
            operation="regression",
        )
        assert link.link_id == "link_001"
        assert link.source_id == "source_node"
        assert link.target_id == "target_node"
        assert link.operation == "regression"
        assert link.description == ""
        assert link.code_snippet == ""
        assert link.metadata == {}

    def test_provenance_link_all_fields(self):
        """Test ProvenanceLink with all fields populated."""
        link = ProvenanceLink(
            link_id="link_002",
            source_id="code_node",
            target_id="output_node",
            operation="filter",
            description="Filter out outliers",
            code_snippet="df[df['value'] < 100]",
            metadata={"threshold": 100},
        )
        assert link.description == "Filter out outliers"
        assert link.code_snippet == "df[df['value'] < 100]"
        assert link.metadata == {"threshold": 100}


# ─── ChartMetadata Tests ───────────────────────────────────────────────────


class TestChartMetadata:
    """Tests for the ChartMetadata dataclass."""

    def test_chart_metadata_required_only(self):
        """Test ChartMetadata with only required path field."""
        meta = ChartMetadata(path="/figures/fig1.pdf")
        assert meta.path == "/figures/fig1.pdf"
        assert meta.caption == ""
        assert meta.figure_label == ""
        assert meta.data_sources == []
        assert meta.code_snippet == ""
        assert meta.width == 0
        assert meta.height == 0
        assert meta.dpi == 300
        assert meta.format == "pdf"
        assert meta.created_at is not None

    def test_chart_metadata_all_fields(self):
        """Test ChartMetadata with all fields populated."""
        meta = ChartMetadata(
            path="/figures/fig2.png",
            caption="Treatment Effect Over Time",
            figure_label="Figure 3",
            data_sources=["/data/regression_results.csv"],
            code_snippet="sns.lineplot(x='year', y='effect')",
            width=8.5,
            height=6.0,
            dpi=600,
            format="png",
        )
        assert meta.caption == "Treatment Effect Over Time"
        assert meta.figure_label == "Figure 3"
        assert meta.data_sources == ["/data/regression_results.csv"]
        assert meta.code_snippet == "sns.lineplot(x='year', y='effect')"
        assert meta.width == 8.5
        assert meta.height == 6.0
        assert meta.dpi == 600
        assert meta.format == "png"

    def test_chart_metadata_to_dict(self):
        """Test ChartMetadata.to_dict method."""
        meta = ChartMetadata(
            path="/figures/fig3.pdf",
            caption="Summary Statistics",
            figure_label="Table 1",
            data_sources=["/data/summary.csv"],
            code_snippet="describe()",
            width=6.0,
            height=4.0,
            dpi=300,
            format="pdf",
        )
        d = meta.to_dict()

        assert d["path"] == "/figures/fig3.pdf"
        assert d["caption"] == "Summary Statistics"
        assert d["figure_label"] == "Table 1"
        assert d["data_sources"] == ["/data/summary.csv"]
        assert d["code_snippet"] == "describe()"
        assert d["width"] == 6.0
        assert d["height"] == 4.0
        assert d["dpi"] == 300
        assert d["format"] == "pdf"

    def test_chart_metadata_to_dict_truncates_code(self):
        """Test that to_dict truncates code_snippet over 200 chars."""
        long_code = "# " + "comment " * 50
        meta = ChartMetadata(path="/fig.pdf", code_snippet=long_code)
        d = meta.to_dict()
        assert len(d["code_snippet"]) <= 200


# ─── compute_checksum Tests ────────────────────────────────────────────────


class TestComputeChecksum:
    """Tests for compute_checksum and compute_checksum_long functions."""

    def test_checksum_none(self):
        """Test checksum of None returns all zeros."""
        result = compute_checksum(None)
        assert result == "0" * 16
        assert len(result) == 16

    def test_checksum_dict(self):
        """Test checksum of dict."""
        data = {"key": "value", "number": 42}
        result = compute_checksum(data)
        assert len(result) == 16
        assert result.isalnum()

    def test_checksum_list(self):
        """Test checksum of list."""
        data = [1, 2, 3, "test"]
        result = compute_checksum(data)
        assert len(result) == 16

    def test_checksum_string(self):
        """Test checksum of string."""
        result = compute_checksum("hello world")
        assert len(result) == 16

    def test_checksum_bytes(self):
        """Test checksum of bytes."""
        result = compute_checksum(b"binary data")
        assert len(result) == 16

    def test_checksum_consistency(self):
        """Test that same input produces same checksum."""
        data = {"consistent": "data", "value": 123}
        result1 = compute_checksum(data)
        result2 = compute_checksum(data)
        assert result1 == result2

    def test_checksum_different_inputs(self):
        """Test that different inputs produce different checksums."""
        result1 = compute_checksum({"a": 1})
        result2 = compute_checksum({"a": 2})
        assert result1 != result2

    def test_checksum_long(self):
        """Test compute_checksum_long returns 64-char hash."""
        result = compute_checksum_long("test data")
        assert len(result) == 64
        assert result.isalnum()


# ─── ProvenanceChain Tests ─────────────────────────────────────────────────


class TestProvenanceChain:
    """Tests for the ProvenanceChain class."""

    def test_init_default_dir(self, temp_dir):
        """Test ProvenanceChain initialization with default project_dir."""
        chain = ProvenanceChain(project_dir=None)
        assert chain.project_dir == Path("output")

    def test_init_custom_dir(self, temp_dir):
        """Test ProvenanceChain initialization with custom directory."""
        custom_dir = temp_dir / "custom_provenance"
        chain = ProvenanceChain(project_dir=str(custom_dir))
        assert chain.project_dir == custom_dir
        assert chain.nodes == {}
        assert chain.links == []

    def test_register_node_generates_id(self, chain):
        """Test that register_node generates ID if node_id is empty."""
        node = ProvenanceNode(
            node_id="",
            node_type=NodeType.RAW_DATA,
            label="Auto Generated ID",
        )
        returned_id = chain.register_node(node)
        assert returned_id.startswith("raw_data_")
        assert returned_id in chain.nodes

    def test_register_node_preserves_id(self, chain):
        """Test that register_node preserves existing node_id."""
        node = ProvenanceNode(
            node_id="my_custom_id",
            node_type=NodeType.CODE,
            label="Custom ID Node",
        )
        returned_id = chain.register_node(node)
        assert returned_id == "my_custom_id"
        assert "my_custom_id" in chain.nodes

    def test_register_link(self, chain):
        """Test registering a link between two nodes."""
        node1 = ProvenanceNode(
            node_id="node_a",
            node_type=NodeType.RAW_DATA,
            label="Node A",
        )
        node2 = ProvenanceNode(
            node_id="node_b",
            node_type=NodeType.OUTPUT,
            label="Node B",
        )
        chain.register_node(node1)
        chain.register_node(node2)

        link = ProvenanceLink(
            link_id="link_a_b",
            source_id="node_a",
            target_id="node_b",
            operation="process",
        )
        chain.register_link(link)

        assert len(chain.links) == 1
        assert "node_b" in chain.nodes["node_a"].child_ids
        assert "node_a" in chain.nodes["node_b"].parent_ids

    def test_register_data_source(self, chain, temp_dir):
        """Test register_data_source convenience method."""
        # Create a temp file to get checksum
        data_file = temp_dir / "test_data.csv"
        data_file.write_text("col1,col2\n1,2\n3,4")

        node_id = chain.register_data_source(
            path=str(data_file),
            node_type=NodeType.RAW_DATA,
            label="Test Data CSV",
        )
        assert node_id.startswith("raw_data_")
        assert node_id in chain.nodes

    def test_register_code(self, chain):
        """Test register_code creates code node and link."""
        # First create an output node
        output_node = ProvenanceNode(
            node_id="output_node",
            node_type=NodeType.OUTPUT,
            label="Regression Output",
        )
        chain.register_node(output_node)

        code = "import statsmodels.api as sm; result = sm.OLS(y, X).fit()"
        code_id = chain.register_code(
            code=code,
            output_node_id="output_node",
            operation="regression",
            description="OLS regression",
        )
        assert code_id.startswith("code_")
        assert "output_node" in chain.nodes[code_id].child_ids

    def test_register_number(self, chain):
        """Test register_number creates NUMBER node."""
        # Create a parent node first
        parent = ProvenanceNode(
            node_id="parent_node",
            node_type=NodeType.OUTPUT,
            label="Regression Output",
        )
        chain.register_node(parent)

        node_id = chain.register_number(
            value=0.0234,
            context="Table 2, Column (3)",
            parent_ids=["parent_node"],
            label="Treatment Effect",
        )
        assert node_id.startswith("num_")
        node = chain.nodes[node_id]
        assert node.node_type == NodeType.NUMBER
        assert node.numeric_value == 0.0234

    def test_register_figure(self, chain):
        """Test register_figure creates CHART node."""
        # Create a parent data node
        data_node = ProvenanceNode(
            node_id="data_node",
            node_type=NodeType.RAW_DATA,
            label="Input Data",
        )
        chain.register_node(data_node)

        fig_id = chain.register_figure(
            figure_path="/figures/output/figure1.pdf",
            data_source_id="data_node",
            caption="Treatment Effect Over Time",
            figure_label="Figure 1",
        )
        assert fig_id.startswith("fig_")
        node = chain.nodes[fig_id]
        assert node.node_type == NodeType.CHART
        assert node.metadata["caption"] == "Treatment Effect Over Time"

    def test_trace_figure_not_found(self, chain):
        """Test trace_figure returns empty list when figure not found."""
        result = chain.trace_figure("NonExistentFigure")
        assert result == []

    def test_trace_figure_found(self, chain):
        """Test trace_figure returns path to figure."""
        # Create chain: raw_data -> figure
        data_node = ProvenanceNode(
            node_id="raw_data_001",
            node_type=NodeType.RAW_DATA,
            label="Input Data",
        )
        chain.register_node(data_node)

        fig_node = ProvenanceNode(
            node_id="fig_001",
            node_type=NodeType.CHART,
            label="Figure 1: Treatment Effect",
            parent_ids=["raw_data_001"],
        )
        chain.register_node(fig_node)
        chain.nodes["raw_data_001"].add_child("fig_001")

        result = chain.trace_figure("Figure 1")
        assert len(result) == 2
        assert result[0].node_id == "fig_001"
        assert result[1].node_id == "raw_data_001"

    def test_trace_number_float(self, chain):
        """Test trace_number with float value."""
        node = ProvenanceNode(
            node_id="num_001",
            node_type=NodeType.NUMBER,
            label="Coefficient",
            numeric_value=0.0234,
            parent_ids=["parent_001"],
        )
        parent = ProvenanceNode(
            node_id="parent_001",
            node_type=NodeType.OUTPUT,
            label="Parent Output",
        )
        chain.register_node(parent)
        chain.register_node(node)

        result = chain.trace_number(0.0234)
        assert len(result) >= 1
        assert any(n.node_id == "num_001" for n in result)

    def test_trace_number_string(self, chain):
        """Test trace_number with string value."""
        node = ProvenanceNode(
            node_id="num_002",
            node_type=NodeType.NUMBER,
            label="Coefficient",
            numeric_context="Table 2 shows the coefficient is 0.0456",
            numeric_value=0.0456,
        )
        chain.register_node(node)

        result = chain.trace_number("0.0456")
        assert len(result) >= 1

    def test_trace_number_not_found(self, chain):
        """Test trace_number returns empty when not found."""
        result = chain.trace_number(999.999)
        assert result == []

    def test_export_mermaid(self, chain):
        """Test export_mermaid generates valid mermaid code."""
        node = ProvenanceNode(
            node_id="test_node",
            node_type=NodeType.RAW_DATA,
            label="Test Data",
        )
        chain.register_node(node)

        mermaid = chain.export_mermaid()
        assert "```mermaid" in mermaid
        assert "flowchart LR" in mermaid
        assert "test_node" in mermaid

    def test_export_mermaid_with_output(self, chain, temp_dir):
        """Test export_mermaid writes to file."""
        node = ProvenanceNode(
            node_id="export_test",
            node_type=NodeType.CODE,
            label="Code to Export",
        )
        chain.register_node(node)

        output_path = temp_dir / "mermaid.md"
        result = chain.export_mermaid(output_path=output_path)
        assert output_path.exists()
        assert "export_test" in result

    def test_export_report(self, chain):
        """Test export_report generates markdown report."""
        node = ProvenanceNode(
            node_id="report_node",
            node_type=NodeType.NUMBER,
            label="Key Result",
            numeric_value=1.234,
            numeric_context="Main regression coefficient",
        )
        chain.register_node(node)

        report = chain.export_report()
        # Check for key Chinese characters that indicate report was generated
        assert "Provenance" in report or "追溯报告" in report
        assert "report_node" in report
        assert "1.234000" in report

    def test_export_report_with_output(self, chain, temp_dir):
        """Test export_report writes to file."""
        node = ProvenanceNode(
            node_id="report_output_node",
            node_type=NodeType.OUTPUT,
            label="Output Node",
        )
        chain.register_node(node)

        output_path = temp_dir / "report.md"
        result = chain.export_report(output_path=output_path)
        assert output_path.exists()
        assert "# Provenance 追溯报告" in result

    def test_export_figure_provenance_report(self, chain):
        """Test export_figure_provenance_report."""
        # Create figure chain
        data_node = ProvenanceNode(
            node_id="data_for_fig",
            node_type=NodeType.RAW_DATA,
            label="Figure Data",
        )
        chain.register_node(data_node)

        # Set figure_label in metadata so trace_figure can find it
        fig_node = ProvenanceNode(
            node_id="fig_report",
            node_type=NodeType.CHART,
            label="Report Figure",
            parent_ids=["data_for_fig"],
            metadata={"caption": "Test Figure Caption", "figure_label": "fig_report"},
        )
        chain.register_node(fig_node)
        chain.nodes["data_for_fig"].add_child("fig_report")

        result = chain.export_figure_provenance_report("fig_report")
        assert "Provenance Report: fig_report" in result
        assert "data_for_fig" in result

    def test_save_and_load(self, chain, temp_dir):
        """Test that chain state persists via _save/_load."""
        node = ProvenanceNode(
            node_id="persist_node",
            node_type=NodeType.OUTPUT,
            label="Persistent Node",
        )
        chain.register_node(node)

        # Create new chain instance with same directory
        chain2 = ProvenanceChain(project_dir=str(temp_dir / "provenance"))
        assert "persist_node" in chain2.nodes

    def test_load_corrupted_file(self, chain, temp_dir):
        """Test that _load handles corrupted JSON gracefully."""
        chain_path = chain._chain_path
        chain_path.parent.mkdir(parents=True, exist_ok=True)
        chain_path.write_text("not valid json{{{", encoding="utf-8")

        # Should not raise, just start fresh
        new_chain = ProvenanceChain(project_dir=str(temp_dir / "provenance"))
        assert new_chain.nodes == {}
        assert new_chain.links == []

    def test_dict_to_node(self, chain):
        """Test _dict_to_node deserializes correctly."""
        data_node = ProvenanceNode(
            node_id="dict_test",
            node_type=NodeType.CODE,
            label="Dict Test",
            content="test code",
            numeric_value=3.14,
        )
        chain.register_node(data_node)

        # Get the dict representation
        node_dict = data_node.to_dict()
        # Deserialize via _dict_to_node
        restored = chain._dict_to_node(node_dict)

        assert restored.node_id == "dict_test"
        assert restored.node_type == NodeType.CODE
        assert restored.label == "Dict Test"
        assert restored.content == "test code"
        assert restored.numeric_value == 3.14

    def test_file_hash_existing_file(self, chain, temp_dir):
        """Test _file_hash returns hash for existing file."""
        test_file = temp_dir / "hash_test.txt"
        test_file.write_bytes(b"test content for hashing")

        hash_result = ProvenanceChain._file_hash(test_file)
        assert len(hash_result) == 16
        assert hash_result.isalnum()

    def test_file_hash_nonexistent_file(self, chain):
        """Test _file_hash returns empty string for nonexistent file."""
        result = ProvenanceChain._file_hash(Path("/nonexistent/path/file.txt"))
        assert result == ""


# ─── record_transform Tests ─────────────────────────────────────────────────


class TestRecordTransform:
    """Tests for the record_transform function."""

    def test_record_transform_basic(self, chain):
        """Test basic record_transform functionality."""
        # Create input node
        input_node = ProvenanceNode(
            node_id="input_node",
            node_type=NodeType.RAW_DATA,
            label="Raw Input",
        )
        chain.register_node(input_node)

        result = record_transform(
            chain=chain,
            input_node_ids=["input_node"],
            transform_fn="winsorize_99",
            params={"lower": 0.01, "upper": 0.99},
            output_label="Winsorized Data",
            output_payload={"winsorized": True},
        )

        assert result.node_type == NodeType.OUTPUT
        assert result.metadata["transform_fn"] == "winsorize_99"
        assert result.metadata["params"] == {"lower": 0.01, "upper": 0.99}
        assert result.metadata["output_checksum"] != ""

    def test_record_transform_no_payload(self, chain):
        """Test record_transform without output_payload."""
        input_node = ProvenanceNode(
            node_id="input_only",
            node_type=NodeType.RAW_DATA,
            label="Input Only",
        )
        chain.register_node(input_node)

        result = record_transform(
            chain=chain,
            input_node_ids=["input_only"],
            transform_fn="simple_filter",
            output_label="Filtered",
        )

        assert result.metadata["output_checksum"] == ""


# ─── Global Singleton Tests ────────────────────────────────────────────────


class TestGlobalSingleton:
    """Tests for global singleton functions."""

    def test_get_chain_creates_singleton(self):
        """Test that get_chain returns same instance."""
        reset_tracker()
        chain1 = get_chain()
        chain2 = get_chain()
        assert chain1 is chain2

    def test_get_chain_with_custom_dir(self, temp_dir):
        """Test get_chain with custom project_dir."""
        reset_tracker()
        chain = get_chain(project_dir=str(temp_dir / "custom"))
        assert chain.project_dir == temp_dir / "custom"

    def test_set_and_get_tracker(self):
        """Test set_tracker and get_tracker."""
        reset_tracker()
        custom_tracker = ProvenanceTracker(project_dir="test_dir")
        set_tracker(custom_tracker)

        retrieved = get_tracker()
        assert retrieved is custom_tracker

    def test_set_tracker_none(self):
        """Test set_tracker(None) resets tracker."""
        reset_tracker()
        tracker = get_tracker()
        set_tracker(None)
        # After setting None, get_tracker should create new instance
        new_tracker = get_tracker()
        assert new_tracker is not tracker

    def test_reset_tracker(self):
        """Test reset_tracker clears global instances."""
        reset_tracker()
        chain1 = get_chain()
        tracker1 = get_tracker()

        reset_tracker()

        # After reset, get_chain and get_tracker should return new instances
        chain2 = get_chain()
        tracker2 = get_tracker()
        assert chain1 is not chain2
        assert tracker1 is not tracker2


# ─── Tracker Facade Tests ──────────────────────────────────────────────────


class TestProvenanceTracker:
    """Tests for the ProvenanceTracker facade class."""

    def test_tracker_register_data(self, tracker, temp_dir):
        """Test tracker.register_data."""
        data_file = temp_dir / "tracker_data.csv"
        data_file.write_text("x,y\n1,2\n3,4")

        node_id = tracker.register_data(
            path=str(data_file),
            label="Tracker Data",
            node_type=NodeType.RAW_DATA,
        )
        assert node_id.startswith("raw_data_")

    def test_tracker_register_chart(self, tracker, temp_dir):
        """Test tracker.register_chart with ChartMetadata."""
        # First register data
        data_file = temp_dir / "chart_data.csv"
        data_file.write_text("x,y\n1,2\n3,4")
        data_node_id = tracker.register_data(
            path=str(data_file),
            label="Chart Data Source",
        )

        # Create chart metadata
        metadata = ChartMetadata(
            path="/figures/scatter.pdf",
            caption="Scatter Plot",
            figure_label="Figure 2",
            data_sources=[str(data_file)],
        )

        fig_id = tracker.register_chart(metadata, data_node_id)
        assert fig_id.startswith("fig_")

    def test_tracker_trace_figure(self, tracker):
        """Test tracker.trace_figure delegates to chain."""
        # This should return empty list when no figures exist
        result = tracker.trace_figure("NonExistent")
        assert result == []

    def test_tracker_trace_number(self, tracker):
        """Test tracker.trace_number delegates to chain."""
        result = tracker.trace_number(123.45)
        assert result == []

    def test_tracker_export_mermaid(self, tracker):
        """Test tracker.export_mermaid delegates to chain."""
        result = tracker.export_mermaid()
        assert "```mermaid" in result

    def test_tracker_export_report(self, tracker):
        """Test tracker.export_report delegates to chain."""
        result = tracker.export_report()
        assert "# Provenance 追溯报告" in result


# ─── Convenience Function Tests ────────────────────────────────────────────


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_register_chart_function(self, temp_dir):
        """Test register_chart convenience function."""
        reset_tracker()
        tracker = ProvenanceTracker(project_dir=str(temp_dir))

        # Register data first
        data_file = temp_dir / "convenience_data.csv"
        data_file.write_text("a,b\n1,2")

        data_node_id = register_data_source(
            path=str(data_file),
            node_type=NodeType.RAW_DATA,
            label="Convenience Data",
            tracker=tracker,
        )

        # Now register chart
        metadata = ChartMetadata(
            path="/figures/test.pdf",
            figure_label="Figure Test",
        )
        fig_id = register_chart(metadata, data_node_id, tracker=tracker)
        assert fig_id.startswith("fig_")

    def test_register_data_source_function(self, temp_dir):
        """Test register_data_source convenience function."""
        reset_tracker()
        tracker = ProvenanceTracker(project_dir=str(temp_dir))

        data_file = temp_dir / "source_func.csv"
        data_file.write_text("col\nval")

        node_id = register_data_source(
            path=str(data_file),
            node_type=NodeType.CLEANED_DATA,
            label="Cleaned Data",
            tracker=tracker,
        )
        assert node_id.startswith("cleaned_data_")

    def test_latex_provenance_comment(self):
        """Test latex_provenance_comment generates correct LaTeX."""
        result = latex_provenance_comment(
            figure_label="Figure 1",
            data_sources=["CSMAR", "Wind"],
            model_output="OLS",
        )
        # Output is in LaTeX comment format with semicolons
        assert "Figure 1" in result
        assert "CSMAR" in result
        assert "Wind" in result
        assert "OLS" in result
        assert result.startswith("%")

    def test_latex_provenance_comment_no_output(self):
        """Test latex_provenance_comment without model_output."""
        result = latex_provenance_comment(
            figure_label="Figure 2",
            data_sources=["Manual Collection"],
        )
        assert "Figure 2" in result
        assert "Manual Collection" in result


# ─── inject_provenance_into_latex Tests ─────────────────────────────────────


class TestInjectProvenance:
    """Tests for inject_provenance_into_latex function."""

    def test_inject_provenance_basic(self, chain, temp_dir):
        """Test basic LaTeX provenance injection."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\begin{figure}
    \centering
    \includegraphics{test.pdf}
    \caption{Treatment Effect Over Time}
    \label{fig:effect}
\end{figure}
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content, encoding="utf-8")

        # Create matching chart node
        chart_node = ProvenanceNode(
            node_id="fig_eff",
            node_type=NodeType.CHART,
            label="fig:effect",
            sources=[SourceRef(type="file", path="/data/effect.csv")],
            metadata={"caption": "Treatment Effect Over Time"},
        )
        chain.register_node(chart_node)

        result_path = inject_provenance_into_latex(tex_file, chain)
        assert result_path.exists()

        result_content = result_path.read_text(encoding="utf-8")
        assert "Treatment Effect Over Time" in result_content

    def test_inject_provenance_no_matching_figure(self, chain, temp_dir):
        """Test injection when no matching figure node exists."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\begin{figure}
    \caption{Untracked Figure}
\end{figure}
\end{document}
"""
        tex_file = temp_dir / "test2.tex"
        tex_file.write_text(tex_content, encoding="utf-8")

        result_path = inject_provenance_into_latex(tex_file, chain)
        result_content = result_path.read_text(encoding="utf-8")

        # Original caption should be preserved
        assert "Untracked Figure" in result_content


# ─── Backtrack and Forward Trace Tests ───────────────────────────────────


class TestBacktrackForwardTrace:
    """Tests for internal _backtrack and _forward_trace methods."""

    def test_backtrack_multiple_parents(self, chain):
        """Test backtracking through nodes with multiple parents."""
        # Create a diamond dependency structure
        root = ProvenanceNode(node_id="root", node_type=NodeType.RAW_DATA, label="Root")
        chain.register_node(root)

        child1 = ProvenanceNode(
            node_id="child1", node_type=NodeType.CLEANED_DATA, label="Child 1", parent_ids=["root"]
        )
        chain.register_node(child1)
        chain.nodes["root"].add_child("child1")

        child2 = ProvenanceNode(
            node_id="child2", node_type=NodeType.CLEANED_DATA, label="Child 2", parent_ids=["root"]
        )
        chain.register_node(child2)
        chain.nodes["root"].add_child("child2")

        # Backtrack from child1 should include root
        path = chain._backtrack("child1")
        assert len(path) >= 2
        ids = {n.node_id for n in path}
        assert "root" in ids
        assert "child1" in ids

    def test_forward_trace(self, chain):
        """Test forward tracing from root to leaves."""
        root = ProvenanceNode(node_id="source", node_type=NodeType.RAW_DATA, label="Source")
        chain.register_node(root)

        child = ProvenanceNode(
            node_id="dest", node_type=NodeType.OUTPUT, label="Destination", parent_ids=["source"]
        )
        chain.register_node(child)
        chain.nodes["source"].add_child("dest")

        path = chain._forward_trace("source")
        ids = {n.node_id for n in path}
        assert "source" in ids
        assert "dest" in ids
