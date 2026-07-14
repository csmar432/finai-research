"""Tests for scripts/core/chart_factory.py — ChartRegistry and dataclasses."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.chart_factory import (
        ChartRecord,
        ChartRegistry,
        AdvancedChartFactory,
        CHART_TYPES,
        ACADEMIC_STYLE,
        CB_PALETTE,
        _apply_style,
    )
except Exception as _exc:
    pytest.skip(f"chart_factory not importable: {_exc}", allow_module_level=True)


class TestChartRecord:
    def test_required_fields(self):
        """ChartRecord must accept all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            record = ChartRecord(
                chart_id="c1",
                chart_type="sankey",
                title="Revenue Flow",
                output_path=Path(tmpdir) / "sankey.pdf",
                data_sources=["Bloomberg", "CSMAR"],
                code_snapshot="import matplotlib.pyplot as plt",
            )
            assert record.chart_id == "c1"
            assert record.chart_type == "sankey"
            assert record.dpi == 300  # default
            assert record.format == "pdf"  # default

    def test_to_dict(self):
        """to_dict() must serialize all fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            record = ChartRecord(
                chart_id="c2",
                chart_type="funnel",
                title="Conversion Funnel",
                output_path=Path(tmpdir) / "funnel.pdf",
                data_sources=["internal"],
                code_snapshot="code",
                dpi=300,
                format="png",
            )
            d = record.to_dict()
            assert d["chart_id"] == "c2"
            assert d["chart_type"] == "funnel"
            assert d["dpi"] == 300
            assert d["format"] == "png"


class TestChartRegistry:
    def test_init_default_path(self):
        """ChartRegistry must initialize with a default path."""
        registry = ChartRegistry()
        assert registry.records == []

    def test_register_adds_record(self):
        """register() must add record to the list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.jsonl"
            registry = ChartRegistry(registry_path=path)
            record = ChartRecord(
                chart_id="r1",
                chart_type="alluvial",
                title="Industry Flow",
                output_path=Path(tmpdir) / "alluvial.pdf",
                data_sources=["test"],
                code_snapshot="code",
            )
            registry.register(record)
            assert len(registry.records) == 1
            assert registry.records[0].chart_id == "r1"

    def test_find_by_type(self):
        """find_by_type() must return matching records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            for chart_type in ["sankey", "funnel", "sankey"]:
                record = ChartRecord(
                    chart_id=f"r_{chart_type}",
                    chart_type=chart_type,
                    title="T",
                    output_path=Path(tmpdir) / f"{chart_type}.pdf",
                    data_sources=["test"],
                    code_snapshot="code",
                )
                registry.register(record)
            results = registry.find_by_type("sankey")
            assert len(results) == 2

    def test_find_by_source(self):
        """find_by_source() must return records with matching data source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            record = ChartRecord(
                chart_id="r_src",
                chart_type="funnel",
                title="T",
                output_path=Path(tmpdir) / "funnel.pdf",
                data_sources=["CSMAR", "Wind"],
                code_snapshot="code",
            )
            registry.register(record)
            results = registry.find_by_source("CSMAR")
            assert len(results) == 1
            results2 = registry.find_by_source("Bloomberg")
            assert len(results2) == 0


class TestConstants:
    def test_chart_types_contains_sankey(self):
        """CHART_TYPES must include sankey."""
        assert "sankey" in CHART_TYPES

    def test_academic_style_dpi(self):
        """ACADEMIC_STYLE must set 300 DPI."""
        assert ACADEMIC_STYLE.get("figure.dpi") == 300

    def test_cb_palette_nonempty(self):
        """CB_PALETTE must be non-empty."""
        assert len(CB_PALETTE) > 0
        assert all(isinstance(c, str) for c in CB_PALETTE)


class TestConstants:
    def test_chart_types_contains_sankey(self):
        """CHART_TYPES must include sankey."""
        assert "sankey" in CHART_TYPES

    def test_academic_style_dpi(self):
        """ACADEMIC_STYLE must set 300 DPI."""
        assert ACADEMIC_STYLE.get("figure.dpi") == 300

    def test_cb_palette_nonempty(self):
        """CB_PALETTE must be non-empty."""
        assert len(CB_PALETTE) > 0
        assert all(isinstance(c, str) for c in CB_PALETTE)

    def test_chart_types_all_keys(self):
        """CHART_TYPES must have all expected chart type keys."""
        expected = {
            "sankey", "funnel", "alluvial", "consort",
            "dendrogram", "circos", "sunburst", "chord",
            "sankey_micro", "ensemble_ribbon", "ridgeline", "waffle",
        }
        assert set(CHART_TYPES.keys()) == expected

    def test_chart_types_values_are_strings(self):
        """CHART_TYPES values must be non-empty strings."""
        for k, v in CHART_TYPES.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
            assert len(v) > 0

    def test_academic_style_has_required_keys(self):
        """ACADEMIC_STYLE must contain all required matplotlib keys."""
        required_keys = {
            "figure.dpi", "savefig.dpi", "font.family", "font.size",
            "axes.titlesize", "axes.labelsize", "xtick.labelsize",
            "ytick.labelsize", "legend.fontsize", "axes.spines.top",
            "axes.spines.right", "axes.linewidth", "pdf.fonttype", "ps.fonttype",
        }
        for key in required_keys:
            assert key in ACADEMIC_STYLE, f"Missing key: {key}"

    def test_academic_style_spine_values(self):
        """Spine visibility must be False."""
        assert ACADEMIC_STYLE["axes.spines.top"] is False
        assert ACADEMIC_STYLE["axes.spines.right"] is False

    def test_academic_style_fonttype(self):
        """PDF/PS fonttype must be 42 (embedded fonts)."""
        assert ACADEMIC_STYLE["pdf.fonttype"] == 42
        assert ACADEMIC_STYLE["ps.fonttype"] == 42

    def test_academic_style_dpi_values(self):
        """DPI must be 300 for academic quality."""
        assert ACADEMIC_STYLE["figure.dpi"] == 300
        assert ACADEMIC_STYLE["savefig.dpi"] == 300

    def test_cb_palette_all_hex_colors(self):
        """CB_PALETTE entries must be valid hex color strings."""
        for c in CB_PALETTE:
            assert c.startswith("#")
            assert len(c) == 7
            int(c[1:], 16)  # raises ValueError if invalid

    def test_cb_palette_count(self):
        """CB_PALETTE must have at least 8 colors."""
        assert len(CB_PALETTE) >= 8


class TestApplyStyle:
    """Test _apply_style helper."""

    def test_apply_style_with_matplotlib(self):
        """_apply_style must not raise when matplotlib is available."""
        try:
            import matplotlib
        except ImportError:
            return  # skip if matplotlib not available
        import matplotlib.pyplot as plt
        _apply_style(plt)
        # Just verify it doesn't raise

    def test_apply_style_graceful_on_error(self):
        """_apply_style must not propagate exceptions."""
        # Pass a non-matplotlib object to trigger the except branch
        class FakePlt:
            pass

        _apply_style(FakePlt())  # must not raise


class TestChartRecordExtended:
    """Additional ChartRecord tests beyond the basics."""

    def test_metadata_default_empty_dict(self):
        """metadata defaults to empty dict."""
        with tempfile.TemporaryDirectory():
            record = ChartRecord(
                chart_id="m1",
                chart_type="sankey",
                title="T",
                output_path=Path("x.pdf"),
                data_sources=["a"],
                code_snapshot="code",
            )
            assert record.metadata == {}
            assert isinstance(record.metadata, dict)

    def test_to_dict_includes_metadata(self):
        """to_dict must include metadata field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            record = ChartRecord(
                chart_id="m2",
                chart_type="sankey",
                title="T",
                output_path=Path(tmpdir) / "x.pdf",
                data_sources=["b"],
                code_snapshot="code",
                metadata={"key": "value"},
            )
            d = record.to_dict()
            assert "metadata" in d
            assert d["metadata"]["key"] == "value"

    def test_to_dict_data_sources(self):
        """to_dict must serialize data_sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            record = ChartRecord(
                chart_id="m3",
                chart_type="sankey",
                title="T",
                output_path=Path(tmpdir) / "x.pdf",
                data_sources=["CSMAR", "Wind", "Tushare"],
                code_snapshot="code",
            )
            d = record.to_dict()
            assert d["data_sources"] == ["CSMAR", "Wind", "Tushare"]
            assert len(d["data_sources"]) == 3

    def test_to_dict_output_path_is_string(self):
        """to_dict must convert output_path to string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "output.pdf"
            record = ChartRecord(
                chart_id="m4",
                chart_type="sankey",
                title="T",
                output_path=p,
                data_sources=[],
                code_snapshot="code",
            )
            d = record.to_dict()
            assert isinstance(d["output_path"], str)
            assert d["output_path"] == str(p)

    def test_all_defaults_explicitly(self):
        """Verify all default values."""
        with tempfile.TemporaryDirectory():
            record = ChartRecord(
                chart_id="x",
                chart_type="type",
                title="T",
                output_path=Path("x.pdf"),
                data_sources=[],
                code_snapshot="code",
            )
            assert record.dpi == 300
            assert record.format == "pdf"
            assert record.metadata == {}

    def test_format_pdf(self):
        """Custom format 'png' must be stored."""
        with tempfile.TemporaryDirectory():
            record = ChartRecord(
                chart_id="x",
                chart_type="type",
                title="T",
                output_path=Path("x.pdf"),
                data_sources=[],
                code_snapshot="code",
                format="png",
            )
            assert record.format == "png"
            d = record.to_dict()
            assert d["format"] == "png"

    def test_code_snapshot_stored(self):
        """code_snapshot must be accessible."""
        with tempfile.TemporaryDirectory():
            code = "import matplotlib.pyplot as plt\nplt.savefig(...)"
            record = ChartRecord(
                chart_id="x",
                chart_type="type",
                title="T",
                output_path=Path("x.pdf"),
                data_sources=[],
                code_snapshot=code,
            )
            assert record.code_snapshot == code


class TestChartRegistryExtended:
    """Additional ChartRegistry tests beyond the basics."""

    def test_registry_default_path_created(self):
        """Registry must create parent directory for default path."""
        import os
        registry = ChartRegistry()
        # The default path should have its parent directory created
        assert registry._path.parent.exists()

    def test_registry_custom_path(self):
        """Registry must accept custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "custom.jsonl"
            registry = ChartRegistry(registry_path=path)
            assert registry._path == path

    def test_register_persists_to_file(self):
        """register() must write to the registry file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "r.jsonl"
            registry = ChartRegistry(registry_path=path)
            record = ChartRecord(
                chart_id="p1",
                chart_type="sankey",
                title="T",
                output_path=Path(tmpdir) / "x.pdf",
                data_sources=["test"],
                code_snapshot="code",
            )
            registry.register(record)
            assert path.exists()
            content = path.read_text()
            assert "p1" in content
            assert "sankey" in content

    def test_find_by_type_no_match(self):
        """find_by_type returns empty list when no match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            results = registry.find_by_type("nonexistent")
            assert results == []

    def test_find_by_source_no_match(self):
        """find_by_source returns empty list when no match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            results = registry.find_by_source("NoSource")
            assert results == []

    def test_find_by_source_partial_match(self):
        """find_by_source matches within data_sources list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            record = ChartRecord(
                chart_id="r_src",
                chart_type="funnel",
                title="T",
                output_path=Path(tmpdir) / "f.pdf",
                data_sources=["CSMAR"],
                code_snapshot="code",
            )
            registry.register(record)
            results = registry.find_by_source("CSMAR")
            assert len(results) == 1
            assert results[0].chart_id == "r_src"

    def test_summary_empty(self):
        """summary() returns correct structure when empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            s = registry.summary()
            assert s["total"] == 0
            assert s["by_type"] == {}

    def test_summary_with_records(self):
        """summary() counts by type correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            for i in range(3):
                registry.register(ChartRecord(
                    chart_id=f"s{i}",
                    chart_type="sankey" if i < 2 else "funnel",
                    title="T",
                    output_path=Path(tmpdir) / f"x{i}.pdf",
                    data_sources=[],
                    code_snapshot="code",
                ))
            s = registry.summary()
            assert s["total"] == 3
            assert s["by_type"]["sankey"] == 2
            assert s["by_type"]["funnel"] == 1

    def test_multiple_registers(self):
        """Multiple register() calls accumulate records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "r.jsonl")
            for i in range(5):
                registry.register(ChartRecord(
                    chart_id=f"r{i}",
                    chart_type="sankey",
                    title="T",
                    output_path=Path(tmpdir) / f"x{i}.pdf",
                    data_sources=["test"],
                    code_snapshot="code",
                ))
            assert len(registry.records) == 5

    def test_records_list_isolated(self):
        """Each registry has its own isolated records list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            r1 = ChartRegistry(registry_path=Path(tmpdir) / "r1.jsonl")
            r2 = ChartRegistry(registry_path=Path(tmpdir) / "r2.jsonl")
            r1.register(ChartRecord(
                chart_id="only_in_r1",
                chart_type="sankey",
                title="T",
                output_path=Path(tmpdir) / "x.pdf",
                data_sources=[],
                code_snapshot="code",
            ))
            assert len(r1.records) == 1
            assert len(r2.records) == 0


class TestAdvancedChartFactoryBasics:
    """Test AdvancedChartFactory initialization and non-rendering methods."""

    def test_init_defaults(self):
        """Factory must initialize with sensible defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert factory.output_dir == Path(tmpdir)
            assert factory.dpi == 300
            assert isinstance(factory.registry, ChartRegistry)

    def test_init_custom_dpi(self):
        """Factory must accept custom dpi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir, dpi=150)
            assert factory.dpi == 150

    def test_init_custom_registry(self):
        """Factory must accept custom registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_reg = ChartRegistry(registry_path=Path(tmpdir) / "custom.jsonl")
            factory = AdvancedChartFactory(output_dir=tmpdir, registry=custom_reg)
            assert factory.registry is custom_reg

    def test_summary(self):
        """summary() delegates to registry.summary()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            s = factory.summary()
            assert "total" in s
            assert "by_type" in s

    def test_funnel_method_exists(self):
        """funnel() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.funnel)

    def test_funnel_method_exists(self):
        """funnel() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.funnel)

    def test_alluvial_method_exists(self):
        """alluvial() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.alluvial)

    def test_consort_method_exists(self):
        """consort() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.consort)

    def test_dendrogram_method_exists(self):
        """dendrogram() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.dendrogram)

    def test_sunburst_method_exists(self):
        """sunburst() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.sunburst)

    def test_ridgeline_method_exists(self):
        """ridgeline() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.ridgeline)

    def test_waffle_method_exists(self):
        """waffle() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.waffle)

    def test_ensemble_ribbon_method_exists(self):
        """ensemble_ribbon() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.ensemble_ribbon)

    def test_save_all_formats_method_exists(self):
        """save_all_formats() must be callable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert callable(factory.save_all_formats)

    def test_output_dir_pathlib(self):
        """output_dir must be a Path object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert isinstance(factory.output_dir, Path)

    def test_output_dir_created(self):
        """output_dir must be created on init."""
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_figures"
            factory = AdvancedChartFactory(output_dir=new_dir)
            assert new_dir.exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
