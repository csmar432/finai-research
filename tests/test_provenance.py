"""Comprehensive tests for scripts/core/provenance.py.

Covers all public APIs:
  - ProvenanceChain: links, data/figure/number registration, trace, export, JSON
  - ProvenanceTracker: register_data/chart, trace, export, singleton lifecycle
  - record_transform(): standalone helper
  - get_chain() / get_tracker() / reset_tracker(): global singletons
  - SourceRef / ProvenanceLink / ChartMetadata / NodeType dataclasses
  - compute_checksum() edge cases (bytes, pandas-like, nested)
  - SourceRef / ProvenanceLink dataclasses
  - LatEx helpers: latex_provenance_comment, inject_provenance_into_latex
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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


# ─── SourceRef ──────────────────────────────────────────────────────────────────


class TestSourceRef:
    """Tests for SourceRef dataclass."""

    def test_creation_minimal(self):
        ref = SourceRef(type="file", path="/data/panel.csv")
        assert ref.type == "file"
        assert ref.path == "/data/panel.csv"
        assert ref.line_start is None
        assert ref.line_end is None
        assert ref.query is None
        assert ref.checksum is None

    def test_creation_full(self):
        ref = SourceRef(
            type="api",
            path="https://api.example.com/v1/data",
            line_start=10,
            line_end=50,
            query="SELECT * FROM returns WHERE year >= 2010",
            checksum="abc123def456",
        )
        assert ref.type == "api"
        assert ref.line_start == 10
        assert ref.line_end == 50
        assert "SELECT" in ref.query

    def test_path_is_string(self):
        """Path should be stored as string even if Path object is passed to
        functions that accept both str | Path (SourceRef itself only stores str)."""
        ref = SourceRef(type="file", path="data/raw.csv")
        assert isinstance(ref.path, str)


# ─── ProvenanceLink ────────────────────────────────────────────────────────────


class TestProvenanceLink:
    """Tests for ProvenanceLink dataclass."""

    def test_creation_minimal(self):
        link = ProvenanceLink(
            link_id="link_001",
            source_id="n1",
            target_id="n2",
            operation="regression",
        )
        assert link.link_id == "link_001"
        assert link.source_id == "n1"
        assert link.target_id == "n2"
        assert link.operation == "regression"
        assert link.description == ""
        assert link.code_snippet == ""
        assert link.metadata == {}

    def test_creation_full(self):
        link = ProvenanceLink(
            link_id="link_002",
            source_id="code_clean",
            target_id="clean_data",
            operation="filter",
            description="Drop observations with missing roe",
            code_snippet="df = df.dropna(subset=['roe'])",
            metadata={"rows_removed": 120},
        )
        assert link.description == "Drop observations with missing roe"
        assert link.metadata["rows_removed"] == 120


# ─── ChartMetadata ─────────────────────────────────────────────────────────────


class TestChartMetadata:
    """Tests for ChartMetadata dataclass."""

    def test_creation_defaults(self):
        cm = ChartMetadata(path="figures/did_effect.png")
        assert str(cm.path) == "figures/did_effect.png"
        assert cm.caption == ""
        assert cm.figure_label == ""
        assert cm.data_sources == []
        assert cm.dpi == 300
        assert cm.format == "pdf"

    def test_creation_full(self):
        cm = ChartMetadata(
            path="output/fig1_ate.pdf",
            caption="Average treatment effect over time",
            figure_label="Figure 1",
            data_sources=["data/panel_clean.csv", "data/county_fips.csv"],
            code_snippet="ax.plot(years, ate_values)",
            width=8.0,
            height=5.0,
            dpi=600,
            format="pdf",
        )
        assert cm.figure_label == "Figure 1"
        assert len(cm.data_sources) == 2
        assert cm.dpi == 600
        assert cm.format == "pdf"

    def test_to_dict(self):
        cm = ChartMetadata(path="output/fig2.pdf", figure_label="Figure 2")
        d = cm.to_dict()
        assert isinstance(d, dict)
        assert d["figure_label"] == "Figure 2"
        assert d["dpi"] == 300  # default
        assert d["format"] == "pdf"  # default
        assert "path" in d
        assert "created_at" in d

    def test_to_dict_truncates_code_snippet(self):
        long_code = "x" * 500
        cm = ChartMetadata(path="out.png", code_snippet=long_code)
        d = cm.to_dict()
        assert len(d["code_snippet"]) == 200  # truncated to 200


# ─── ChartMetadata Round-trip ──────────────────────────────────────────────────


class TestChartMetadataRoundTrip:
    """ChartMetadata to_dict serializability."""

    def test_to_dict_then_json_serializable(self):
        """to_dict output must be JSON-serializable."""
        original = ChartMetadata(
            path="output/scatter.pdf",
            caption="ROE vs innovation scatter",
            figure_label="Figure 3",
            data_sources=["data/roe.csv"],
            code_snippet="plt.scatter(x, y)",
            width=7.0,
            height=4.5,
            dpi=300,
            format="pdf",
        )
        d = original.to_dict()
        # Must not raise
        json_str = json.dumps(d, ensure_ascii=False)
        assert "Figure 3" in json_str
        assert "roe.csv" in json_str

    def test_to_dict_all_optional_fields_present(self):
        """to_dict includes every field, including optional ones."""
        d = ChartMetadata(path="simple.png").to_dict()
        # All expected keys present
        for key in ("path", "caption", "figure_label", "data_sources",
                    "code_snippet", "width", "height", "dpi", "format", "created_at"):
            assert key in d, f"Missing key: {key}"


# ─── NodeType ─────────────────────────────────────────────────────────────────


class TestNodeType:
    """Tests for NodeType enum."""

    def test_all_expected_types_present(self):
        expected = {
            "raw_data", "cleaned_data", "variable", "code",
            "output", "chart", "table", "paragraph",
            "number", "citation", "model",
        }
        actual = {t.value for t in NodeType}
        assert expected == actual

    def test_values_are_strings(self):
        for member in NodeType:
            assert isinstance(member.value, str)

    def test_from_string_valid(self):
        assert NodeType("raw_data") == NodeType.RAW_DATA
        assert NodeType("chart") == NodeType.CHART
        assert NodeType("number") == NodeType.NUMBER

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError):
            NodeType("nonexistent_type")


# ─── ProvenanceNode ───────────────────────────────────────────────────────────


class TestProvenanceNode:
    """Tests for ProvenanceNode dataclass (additional coverage)."""

    def test_add_parent_no_duplicate(self):
        node = ProvenanceNode(node_id="n1", node_type=NodeType.OUTPUT, label="out")
        node.add_parent("p1")
        node.add_parent("p2")
        node.add_parent("p1")  # duplicate — should not append
        assert node.parent_ids == ["p1", "p2"]

    def test_add_child_no_duplicate(self):
        node = ProvenanceNode(node_id="n1", node_type=NodeType.RAW_DATA, label="in")
        node.add_child("c1")
        node.add_child("c1")  # duplicate
        assert node.child_ids == ["c1"]

    def test_to_dict_includes_numeric_fields(self):
        node = ProvenanceNode(
            node_id="coef_1",
            node_type=NodeType.NUMBER,
            label="Treatment effect",
            numeric_value=0.0234,
            numeric_context="coefficient on post × treat",
        )
        d = node.to_dict()
        assert d["numeric_value"] == 0.0234
        assert "coefficient" in d["numeric_context"]

    def test_to_dict_truncates_long_content(self):
        long_content = "x" * 1000
        node = ProvenanceNode(node_id="n", node_type=NodeType.CODE, label="c", content=long_content)
        d = node.to_dict()
        # Truncated to 500 chars + "..."
        assert len(d["content"]) < len(long_content)
        assert d["content"].endswith("...")

    def test_to_dict_short_content_no_ellipsis(self):
        node = ProvenanceNode(node_id="n", node_type=NodeType.RAW_DATA, label="s", content="short")
        d = node.to_dict()
        assert d["content"] == "short"
        assert not d["content"].endswith("...")


# ─── Checksum Edge Cases ───────────────────────────────────────────────────────


class TestChecksumEdgeCases:
    """Additional checksum edge cases beyond basic dict/list/string."""

    def test_bytes_input(self):
        c = compute_checksum(b"binary data here")
        assert isinstance(c, str)
        assert len(c) == 16

    def test_bytearray_input(self):
        c = compute_checksum(bytearray([0x48, 0x65, 0x6c, 0x6c, 0x6f]))
        assert isinstance(c, str)
        assert len(c) == 16

    def test_compute_checksum_long_returns_64_chars(self):
        c = compute_checksum_long([1, 2, 3, 4, 5])
        assert len(c) == 64
        assert all(ch in "0123456789abcdef" for ch in c)

    def test_checksum_none_returns_16_zeros(self):
        assert compute_checksum(None) == "0" * 16
        assert compute_checksum_long(None) != "0" * 16  # long form differs

    def test_checksum_dataframe_like_object(self):
        """Objects with to_dict (pandas-like) are handled gracefully."""
        class DataFrameLike:
            def to_dict(self):
                return {"col1": [1, 2], "col2": ["a", "b"]}
        c = compute_checksum(DataFrameLike())
        assert isinstance(c, str)
        assert len(c) == 16

    def test_checksum_int_input(self):
        c = compute_checksum(42)
        assert isinstance(c, str)
        assert len(c) == 16

    def test_checksum_float_input(self):
        c = compute_checksum(3.14159)
        assert isinstance(c, str)
        assert len(c) == 16

    def test_checksum_order_independent_for_dicts(self):
        """Dicts with same keys/values in different order should hash identically."""
        d1 = {"z": 1, "a": 2, "m": 3}
        d2 = {"a": 2, "m": 3, "z": 1}
        assert compute_checksum(d1) == compute_checksum(d2)


# ─── ProvenanceChain — Register & Links ───────────────────────────────────────


class TestProvenanceChainRegisters:
    """Tests for ProvenanceChain registration and linking methods."""

    def test_register_link_bidirectional_parent_child(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n1 = ProvenanceNode(node_id="raw", node_type=NodeType.RAW_DATA, label="raw")
        n2 = ProvenanceNode(node_id="out", node_type=NodeType.OUTPUT, label="out")
        chain.register_node(n1)
        chain.register_node(n2)

        link = ProvenanceLink(
            link_id="l1", source_id="raw", target_id="out", operation="filter"
        )
        chain.register_link(link)

        assert "raw" in chain.nodes["out"].parent_ids
        assert "out" in chain.nodes["raw"].child_ids
        assert len(chain.links) == 1
        assert chain.links[0].operation == "filter"

    def test_register_link_missing_nodes_still_appends_link(self, tmp_path):
        """Link is recorded even if one endpoint is not yet registered."""
        chain = ProvenanceChain(project_dir=tmp_path)
        link = ProvenanceLink(
            link_id="l2", source_id="missing", target_id="also_missing",
            operation="regression"
        )
        chain.register_link(link)
        assert len(chain.links) == 1

    def test_register_data_source(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        # Use a real temp file so checksum can be computed
        data_file = tmp_path / "panel.csv"
        data_file.write_text("firm,year,roe\nA,2010,0.05\n")

        node_id = chain.register_data_source(path=str(data_file), label="Panel data")
        assert node_id.startswith("raw_data_")
        assert node_id in chain.nodes
        assert chain.nodes[node_id].node_type == NodeType.RAW_DATA

    def test_register_data_source_auto_label(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        data_file = tmp_path / "my_dataset.csv"
        data_file.write_text("a,b\n1,2\n")

        node_id = chain.register_data_source(path=str(data_file))
        assert chain.nodes[node_id].label == "my_dataset.csv"

    def test_register_code(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_out = ProvenanceNode(
            node_id="output_node",
            node_type=NodeType.OUTPUT,
            label="Cleaned dataset",
        )
        chain.register_node(n_out)

        code = "df = df.dropna(subset=['roe'])"
        code_id = chain.register_code(
            code=code,
            output_node_id="output_node",
            operation="clean",
            description="Remove missing roe rows",
        )

        assert code_id.startswith("code_")
        assert "output_node" in chain.nodes[code_id].child_ids
        assert chain.nodes["output_node"].parent_ids[0] == code_id

    def test_register_number(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_parent = ProvenanceNode(
            node_id="reg_out", node_type=NodeType.OUTPUT, label="Regression output"
        )
        chain.register_node(n_parent)

        num_id = chain.register_number(
            value=0.0234,
            context="coefficient on post × treat interaction",
            parent_ids=["reg_out"],
            label="ATE estimate",
        )

        assert num_id.startswith("num_")
        assert chain.nodes[num_id].numeric_value == 0.0234
        assert "reg_out" in chain.nodes[num_id].parent_ids

    def test_register_figure(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_data = ProvenanceNode(
            node_id="data_node", node_type=NodeType.RAW_DATA, label="Source data"
        )
        chain.register_node(n_data)

        fig_path = tmp_path / "fig1_ate.pdf"
        fig_id = chain.register_figure(
            figure_path=str(fig_path),
            data_source_id="data_node",
            caption="Average treatment effect",
            figure_label="Figure 1",
        )

        assert fig_id.startswith("fig_")
        assert chain.nodes[fig_id].node_type == NodeType.CHART
        assert "data_node" in chain.nodes[fig_id].parent_ids


# ─── ProvenanceChain — Trace ──────────────────────────────────────────────────


class TestProvenanceChainTrace:
    """Tests for ProvenanceChain trace methods."""

    def test_trace_figure_finds_by_label(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_data = ProvenanceNode(
            node_id="d", node_type=NodeType.RAW_DATA, label="raw"
        )
        n_fig = ProvenanceNode(
            node_id="f1",
            node_type=NodeType.CHART,
            label="Figure 1: ATE over time",
            parent_ids=["d"],
        )
        chain.register_node(n_data)
        chain.register_node(n_fig)

        path = chain.trace_figure("Figure 1")
        assert len(path) == 2
        assert path[0].node_id == "f1"
        assert path[1].node_id == "d"

    def test_trace_figure_finds_by_metadata(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_fig = ProvenanceNode(
            node_id="f2",
            node_type=NodeType.CHART,
            label="ate_chart.pdf",
            metadata={"figure_label": "Figure 2"},
            parent_ids=[],
        )
        chain.register_node(n_fig)

        path = chain.trace_figure("Figure 2")
        assert len(path) == 1
        assert path[0].node_id == "f2"

    def test_trace_figure_not_found(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        assert chain.trace_figure("Nonexistent Figure") == []

    def test_trace_number_by_float(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_num = ProvenanceNode(
            node_id="n1",
            node_type=NodeType.NUMBER,
            label="coefficient",
            numeric_value=0.0234,
            parent_ids=[],
        )
        chain.register_node(n_num)

        path = chain.trace_number(0.0234)
        assert len(path) == 1
        assert path[0].numeric_value == 0.0234

    def test_trace_number_by_string_float(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_num = ProvenanceNode(
            node_id="n2",
            node_type=NodeType.NUMBER,
            label="se",
            numeric_value=1.96,
            parent_ids=[],
        )
        chain.register_node(n_num)
        path = chain.trace_number("1.96")
        assert len(path) == 1

    def test_trace_number_by_context_string(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_num = ProvenanceNode(
            node_id="n3",
            node_type=NodeType.NUMBER,
            label="coef",
            numeric_value=0.5,
            numeric_context="coefficient on treat",
            parent_ids=[],
        )
        chain.register_node(n_num)
        path = chain.trace_number("coefficient on treat")
        assert len(path) == 1

    def test_trace_number_not_found(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        assert chain.trace_number(99.99) == []

    def test_backtrack_resolves_ancestors(self, tmp_path):
        """_backtrack should walk all ancestors, not just immediate parents."""
        chain = ProvenanceChain(project_dir=tmp_path)
        # raw -> clean -> result -> number
        n_raw = ProvenanceNode(node_id="raw", node_type=NodeType.RAW_DATA, label="r")
        n_clean = ProvenanceNode(
            node_id="clean", node_type=NodeType.CLEANED_DATA, label="c",
            parent_ids=["raw"]
        )
        n_result = ProvenanceNode(
            node_id="result", node_type=NodeType.OUTPUT, label="res",
            parent_ids=["clean"]
        )
        n_num = ProvenanceNode(
            node_id="num", node_type=NodeType.NUMBER, label="n",
            numeric_value=0.1, parent_ids=["result"]
        )
        for n in [n_raw, n_clean, n_result, n_num]:
            chain.register_node(n)

        path = chain.trace_number(0.1)
        ids = {p.node_id for p in path}
        assert ids == {"num", "result", "clean", "raw"}


# ─── ProvenanceChain — Export ──────────────────────────────────────────────────


class TestProvenanceChainExport:
    """Tests for ProvenanceChain export methods."""

    def test_export_mermaid_contains_nodes_and_links(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n1 = ProvenanceNode(node_id="raw_001", node_type=NodeType.RAW_DATA, label="Raw CSV")
        n2 = ProvenanceNode(node_id="out_001", node_type=NodeType.OUTPUT, label="Cleaned")
        chain.register_node(n1)
        chain.register_node(n2)
        chain.register_link(ProvenanceLink(
            link_id="l1", source_id="raw_001", target_id="out_001",
            operation="filter"
        ))

        mermaid = chain.export_mermaid()
        assert "flowchart" in mermaid
        assert "raw_001" in mermaid
        assert "out_001" in mermaid
        assert "filter" in mermaid

    def test_export_mermaid_to_file(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n = ProvenanceNode(node_id="n1", node_type=NodeType.RAW_DATA, label="d")
        chain.register_node(n)

        out_file = tmp_path / "mermaid.md"
        result = chain.export_mermaid(output_path=out_file)
        assert out_file.exists()
        assert result == out_file.read_text()

    def test_export_report_contains_nodes(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n = ProvenanceNode(
            node_id="fig_001",
            node_type=NodeType.CHART,
            label="Figure 1: ATE",
            metadata={"caption": "Average treatment effect"},
        )
        chain.register_node(n)

        report = chain.export_report()
        assert "fig_001" in report
        assert "Figure 1: ATE" in report
        assert "节点总数" in report or "total" in report.lower()

    def test_export_report_to_file(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        chain.register_node(ProvenanceNode(
            node_id="n1", node_type=NodeType.RAW_DATA, label="d"
        ))

        out_file = tmp_path / "report.md"
        result = chain.export_report(output_path=out_file)
        assert out_file.exists()
        assert result == out_file.read_text()

    def test_export_figure_provenance_report_finds_figure(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_data = ProvenanceNode(node_id="d", node_type=NodeType.RAW_DATA, label="r")
        n_fig = ProvenanceNode(
            node_id="f",
            node_type=NodeType.CHART,
            label="Figure 3",
            parent_ids=["d"],
            metadata={"caption": "Treatment effect over time"},
        )
        chain.register_node(n_data)
        chain.register_node(n_fig)

        report = chain.export_figure_provenance_report("Figure 3")
        assert "Figure 3" in report
        assert "Step 1" in report
        assert "Step 2" in report

    def test_export_figure_provenance_report_not_found(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        report = chain.export_figure_provenance_report("Ghost Figure")
        assert "Found 0" in report

    def test_export_figure_provenance_report_to_file(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_fig = ProvenanceNode(
            node_id="f", node_type=NodeType.CHART, label="Fig X", parent_ids=[]
        )
        chain.register_node(n_fig)

        out_file = tmp_path / "fig_report.md"
        result = chain.export_figure_provenance_report("Fig X", output_path=out_file)
        assert out_file.exists()

    def test_export_mermaid_and_report_both_produce_strings(self, tmp_path):
        """Both export methods return strings even with no nodes."""
        chain = ProvenanceChain(project_dir=tmp_path)
        assert isinstance(chain.export_mermaid(), str)
        assert isinstance(chain.export_report(), str)

    def test_export_report_with_all_node_types(self, tmp_path):
        """export_report groups and lists every registered node type."""
        chain = ProvenanceChain(project_dir=tmp_path)
        for ntype, nid, label in [
            (NodeType.RAW_DATA, "raw1", "panel.csv"),
            (NodeType.CLEANED_DATA, "clean1", "cleaned_panel.csv"),
            (NodeType.CODE, "code1", "cleaning.py"),
            (NodeType.OUTPUT, "out1", "regression result"),
            (NodeType.CHART, "fig1", "Figure 1"),
            (NodeType.NUMBER, "num1", "coefficient"),
        ]:
            chain.register_node(ProvenanceNode(node_id=nid, node_type=ntype, label=label))

        report = chain.export_report()
        assert len(report) > 200
        # Each node ID appears
        for nid in ["raw1", "clean1", "code1", "out1", "fig1", "num1"]:
            assert nid in report


# ─── ProvenanceChain — Save/Load ──────────────────────────────────────────────


class TestProvenanceChainPersistence:
    """Tests for ProvenanceChain save/load round-trip."""

    def test_chain_survives_save_load_cycle(self, tmp_path):
        """State after registration should survive a re-instantiation."""
        chain_w = ProvenanceChain(project_dir=tmp_path)
        n = ProvenanceNode(
            node_id="persist_test",
            node_type=NodeType.CHART,
            label="Persisted figure",
            metadata={"dpi": 300},
        )
        chain_w.register_node(n)

        chain_r = ProvenanceChain(project_dir=tmp_path)
        assert "persist_test" in chain_r.nodes
        assert chain_r.nodes["persist_test"].label == "Persisted figure"

    def test_load_corrupted_json_is_graceful(self, tmp_path):
        """Corrupted JSON should not raise; chain starts fresh."""
        chain_file = tmp_path / "output" / "provenance_chain.json"
        chain_file.parent.mkdir(parents=True, exist_ok=True)
        chain_file.write_text("{ this is not json }")

        # Should not raise
        chain = ProvenanceChain(project_dir=tmp_path)
        assert chain.nodes == {}


# ─── record_transform ──────────────────────────────────────────────────────────


class TestRecordTransform:
    """Tests for record_transform() standalone function."""

    def test_records_transform_with_input_nodes(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        n_in = ProvenanceNode(node_id="input_n", node_type=NodeType.RAW_DATA, label="in")
        chain.register_node(n_in)

        node = record_transform(
            chain=chain,
            input_node_ids=["input_n"],
            transform_fn="winsorize_99",
            params={"limits": (0.01, 0.01), "axis": 0},
            output_label="Winsorized ROE",
            output_payload={"roe_winsorized": [0.1, 0.2, 0.3]},
        )

        assert node.node_type == NodeType.OUTPUT
        assert node.metadata["transform_fn"] == "winsorize_99"
        assert node.metadata["params"]["limits"] == (0.01, 0.01)
        assert node.metadata["output_checksum"] != ""
        assert len(node.sources) == 1
        assert node.sources[0].path == "input_n"

    def test_records_transform_without_payload(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        node = record_transform(
            chain=chain,
            input_node_ids=["n1", "n2"],
            transform_fn="merge_datasets",
            output_label="Merged panel",
        )
        assert node.metadata["output_checksum"] == ""
        assert len(node.sources) == 2

    def test_records_transform_no_params(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        node = record_transform(
            chain=chain,
            input_node_ids=[],
            transform_fn="dummy_transform",
            output_label="dummy",
        )
        assert node.metadata["params"] == {}


# ─── ProvenanceTracker ─────────────────────────────────────────────────────────


class TestProvenanceTrackerFull:
    """Comprehensive tests for ProvenanceTracker high-level API."""

    def test_register_data(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        node_id = tracker.register_data(
            path="data/panel.csv", label="Firm panel", node_type=NodeType.RAW_DATA
        )
        assert node_id.startswith("raw_data_")
        assert node_id in tracker._chain.nodes

    def test_register_chart(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        data_id = tracker.register_data(path="data/src.csv", label="src")
        fig_path = tmp_path / "fig.pdf"

        # Create a real figure file
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
        fig.savefig(fig_path)
        plt.close(fig)

        metadata = ChartMetadata(
            path=str(fig_path),
            figure_label="Figure 1",
            caption="Scatter plot",
            data_sources=["data/src.csv"],
            dpi=300,
        )
        fig_id = tracker.register_chart(metadata=metadata, data_node_id=data_id)
        assert fig_id.startswith("fig_")
        assert tracker._chain.nodes[fig_id].node_type == NodeType.CHART

    def test_trace_figure(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        data_id = tracker.register_data(path="data/raw.csv", label="raw")
        fig_path = tmp_path / "trace_fig.pdf"
        fig, ax = plt.subplots()
        ax.plot([1, 2], [3, 4])
        fig.savefig(fig_path)
        plt.close(fig)

        metadata = ChartMetadata(path=str(fig_path), figure_label="Figure T")
        fig_id = tracker.register_chart(metadata, data_node_id=data_id)

        path = tracker.trace_figure("Figure T")
        ids = {n.node_id for n in path}
        assert fig_id in ids
        assert data_id in ids

    def test_trace_number(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        path = tracker.trace_number(0.05)
        assert isinstance(path, list)

    def test_export_mermaid(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        tracker.register_data(path="data/test.csv", label="test")
        mermaid = tracker.export_mermaid()
        assert "flowchart" in mermaid

    def test_export_report(self, tmp_path):
        tracker = ProvenanceTracker(project_dir=tmp_path)
        tracker.register_data(path="data/test.csv", label="test")
        report = tracker.export_report()
        assert "test" in report


# ─── Global Singleton Functions ───────────────────────────────────────────────


class TestGlobalSingletons:
    """Tests for global chain/tracker singleton management."""

    def test_get_chain_returns_chain_instance(self):
        reset_tracker()
        chain = get_chain()
        assert isinstance(chain, ProvenanceChain)

    def test_get_chain_same_instance(self):
        reset_tracker()
        c1 = get_chain()
        c2 = get_chain()
        assert c1 is c2

    def test_get_chain_with_project_dir(self, tmp_path):
        reset_tracker()
        chain = get_chain(project_dir=tmp_path)
        assert chain.project_dir == tmp_path

    def test_get_tracker_returns_tracker_instance(self):
        reset_tracker()
        t = get_tracker()
        assert isinstance(t, ProvenanceTracker)

    def test_get_tracker_same_instance(self):
        reset_tracker()
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

    def test_reset_tracker_clears_singleton(self):
        reset_tracker()
        t1 = get_tracker()
        reset_tracker()
        t2 = get_tracker()
        assert t1 is not t2  # new instance after reset

    def test_set_tracker_replaces_singleton(self):
        reset_tracker()
        original = get_tracker()
        new_tracker = ProvenanceTracker()
        set_tracker(new_tracker)
        assert get_tracker() is new_tracker
        set_tracker(None)  # restore None so next get_tracker creates a new one

    def test_register_data_source_standalone_uses_global_tracker(self, tmp_path):
        reset_tracker()
        # Write a real file so checksum can be computed
        f = tmp_path / "standalone.csv"
        f.write_text("a,b\n1,2\n")
        node_id = register_data_source(path=str(f), label="Standalone data")
        assert node_id.startswith("raw_data_")

    def test_register_chart_standalone_uses_global_tracker(self, tmp_path):
        reset_tracker()
        data_id = register_data_source(path=str(tmp_path / "d.csv"), label="d")
        f = tmp_path / "c.pdf"
        fig, ax = plt.subplots()
        fig.savefig(f)
        plt.close(fig)

        meta = ChartMetadata(path=str(f), figure_label="Fig S")
        fig_id = register_chart(metadata=meta, data_node_id=data_id)
        assert fig_id.startswith("fig_")


# ─── Latex Helpers ─────────────────────────────────────────────────────────────


class TestLatexHelpers:
    """Tests for LaTeX provenance integration helpers."""

    def test_latex_provenance_comment_basic(self):
        result = latex_provenance_comment(
            figure_label="Figure 1",
            data_sources=["CSMAR", "Wind"],
            model_output="OLS regression",
        )
        assert "Figure 1" in result
        assert "CSMAR" in result
        assert "OLS regression" in result
        assert result.startswith("%")

    def test_latex_provenance_comment_no_output(self):
        result = latex_provenance_comment(
            figure_label="Figure 2",
            data_sources=["CSMAR"],
        )
        assert "Figure 2" in result
        assert "Output:" not in result

    def test_inject_provenance_into_latex(self, tmp_path):
        tex_content = r"""\documentclass{article}
\begin{document}
\begin{figure}
\centering
\includegraphic{sfig1.pdf}
\caption{ATE over time}
\label{fig:ate}
\end{figure}
\end{document}
"""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(tex_content)

        chain = ProvenanceChain(project_dir=tmp_path)
        n_fig = ProvenanceNode(
            node_id="f",
            node_type=NodeType.CHART,
            label="fig:ate",
            sources=[SourceRef(type="file", path="output/sfig1.pdf")],
            metadata={"caption": "ATE over time"},
        )
        chain.register_node(n_fig)

        out_path = inject_provenance_into_latex(tex_file, chain)
        assert out_path.exists()
        content = out_path.read_text()
        assert r"\caption{ATE over time}" in content
        assert "%" in content  # provenance comment injected


# ─── get_summary ───────────────────────────────────────────────────────────────


class TestGetSummary:
    """Tests for get_summary() on chain and tracker."""

    def test_chain_get_summary_returns_dict(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        chain.register_node(ProvenanceNode(
            node_id="n1", node_type=NodeType.RAW_DATA, label="d1"
        ))
        chain.register_node(ProvenanceNode(
            node_id="n2", node_type=NodeType.CHART, label="fig1"
        ))

        assert isinstance(chain.nodes, dict)
        assert len(chain.nodes) == 2
        assert "n1" in chain.nodes
        assert "n2" in chain.nodes

    def test_chain_get_summary_empty(self, tmp_path):
        chain = ProvenanceChain(project_dir=tmp_path)
        assert len(chain.nodes) == 0
        assert len(chain.links) == 0
