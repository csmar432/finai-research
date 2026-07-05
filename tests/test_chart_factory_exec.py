"""tests/test_chart_factory_exec.py — Test chart_factory pure functions.

Tests for ChartRegistry (register, _persist, find_by_type, find_by_source, summary).
Bug fix in scripts/core/chart_factory.py:_persist() to accept record parameter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts.core import chart_factory as cf
    from scripts.core.chart_factory import (
        ChartRecord,
        ACADEMIC_STYLE,
        CB_PALETTE,
        _apply_style,
        ChartRegistry,
        AdvancedChartFactory,
    )
except Exception as e:
    pytest.skip(f"chart_factory not importable: {e}", allow_module_level=True)


class TestChartRecord:
    def test_default(self):
        r = ChartRecord(
            chart_id="c1",
            chart_type="line",
            title="Test",
            output_path=Path("/tmp/c.pdf"),
            data_sources=["s1"],
            code_snapshot="plt.plot()",
        )
        assert r.dpi == 300
        assert r.format == "pdf"
        assert r.metadata == {}

    def test_to_dict(self):
        r = ChartRecord(
            chart_id="c1",
            chart_type="bar",
            title="T",
            output_path=Path("/tmp/c.pdf"),
            data_sources=["s1", "s2"],
            code_snapshot="plt.bar()",
            dpi=150,
            format="png",
            metadata={"k": "v"},
        )
        d = r.to_dict()
        assert d["chart_id"] == "c1"
        assert d["chart_type"] == "bar"
        assert d["dpi"] == 150
        assert d["format"] == "png"
        assert d["metadata"] == {"k": "v"}
        assert d["data_sources"] == ["s1", "s2"]


class TestConstants:
    def test_academic_style(self):
        assert isinstance(ACADEMIC_STYLE, dict)
        assert "figure.dpi" in ACADEMIC_STYLE
        assert ACADEMIC_STYLE["figure.dpi"] == 300

    def test_cb_palette(self):
        assert isinstance(CB_PALETTE, list)
        assert len(CB_PALETTE) >= 4
        for color in CB_PALETTE:
            assert color.startswith("#")


class TestApplyStyle:
    def test_apply_style(self):
        import matplotlib
        # Should not raise
        _apply_style(None)
        # Check that dpi was set
        assert matplotlib.rcParams.get("figure.dpi") == 300


class TestChartRegistry:
    """Tests skipped: _persist() has NameError on 'record'."""

    def test_init_default(self):
        reg = ChartRegistry()
        assert reg.records == []

    def test_init_custom(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        reg = ChartRegistry(registry_path=path)
        assert reg._path == path

    def test_register(self, tmp_path):
        path = tmp_path / "reg.jsonl"
        reg = ChartRegistry(registry_path=path)
        r = ChartRecord(
            chart_id="c1", chart_type="line", title="T",
            output_path=tmp_path / "c.pdf", data_sources=["s1"],
            code_snapshot="plot",
        )
        reg.register(r)
        assert len(reg.records) == 1
        assert path.exists()
        content = path.read_text()
        assert "c1" in content

    def test_find_by_type(self, tmp_path):
        reg = ChartRegistry(registry_path=tmp_path / "reg.jsonl")
        r1 = ChartRecord("c1", "line", "t", tmp_path / "a", ["s"], "code")
        r2 = ChartRecord("c2", "bar", "t", tmp_path / "b", ["s"], "code")
        r3 = ChartRecord("c3", "line", "t", tmp_path / "c", ["s"], "code")
        reg.register(r1)
        reg.register(r2)
        reg.register(r3)
        lines = reg.find_by_type("line")
        assert len(lines) == 2
        bars = reg.find_by_type("bar")
        assert len(bars) == 1

    def test_find_by_source(self, tmp_path):
        reg = ChartRegistry(registry_path=tmp_path / "reg.jsonl")
        r1 = ChartRecord("c1", "line", "t", tmp_path / "a", ["s1", "s2"], "code")
        r2 = ChartRecord("c2", "bar", "t", tmp_path / "b", ["s2"], "code")
        reg.register(r1)
        reg.register(r2)
        assert len(reg.find_by_source("s1")) == 1
        assert len(reg.find_by_source("s2")) == 2

    def test_summary(self, tmp_path):
        reg = ChartRegistry(registry_path=tmp_path / "reg.jsonl")
        reg.register(ChartRecord("c1", "line", "t", tmp_path / "a", ["s"], "code"))
        reg.register(ChartRecord("c2", "bar", "t", tmp_path / "b", ["s"], "code"))
        s = reg.summary()
        assert s["total"] == 2
        assert s["by_type"]["line"] == 1
        assert s["by_type"]["bar"] == 1


class TestAdvancedChartFactory:
    def test_init(self):
        f = AdvancedChartFactory()
        assert f is not None
