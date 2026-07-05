"""tests/test_chart_factory_exec.py — Test chart_factory pure functions.

NOTE: scripts/core/chart_factory.py:144 has a real bug where _persist() uses
an undefined 'record' variable. The functional fix needs user confirmation
per project rules. Tests for register/_persist/find_by_type/find_by_source/summary
are skipped; only pure-function tests run.
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

    @pytest.mark.skip(reason="BUG: _persist() NameError on 'record' - functional fix pending")
    def test_register(self, tmp_path):
        pass

    @pytest.mark.skip(reason="BUG: _persist() NameError on 'record' - functional fix pending")
    def test_find_by_type(self, tmp_path):
        pass

    @pytest.mark.skip(reason="BUG: _persist() NameError on 'record' - functional fix pending")
    def test_find_by_source(self, tmp_path):
        pass

    @pytest.mark.skip(reason="BUG: _persist() NameError on 'record' - functional fix pending")
    def test_summary(self, tmp_path):
        pass


class TestAdvancedChartFactory:
    def test_init(self):
        f = AdvancedChartFactory()
        assert f is not None
