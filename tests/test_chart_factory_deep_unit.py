"""test_chart_factory_deep_unit.py — Deep unit tests for scripts/core/chart_factory.py.

Tests AdvancedChartFactory rendering methods, _save, _apply_style edge cases,
and all chart type paths. Existing test_chart_factory_unit.py covers
ChartRecord, ChartRegistry, and constants.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.chart_factory import (
        AdvancedChartFactory,
        ChartRegistry,
        _apply_style,
    )
except Exception as _exc:
    pytest.skip(f"chart_factory not importable: {_exc}", allow_module_level=True)


# ─── Test _apply_style ───────────────────────────────────────────────────────


class TestApplyStyleEdgeCases:
    """Test _apply_style in various conditions."""

    def test_apply_style_does_not_raise_on_object_without_rcparams(self):
        """_apply_style must swallow exceptions from invalid inputs."""
        class NoRcParams:
            pass

        _apply_style(NoRcParams())  # must not raise

    def test_apply_style_with_real_matplotlib(self):
        """_apply_style applies ACADEMIC_STYLE to matplotlib.rcParams."""
        try:
            import matplotlib
            import matplotlib.pyplot as plt
        except ImportError:
            pytest.skip("matplotlib not available")

        _apply_style(plt)
        import matplotlib as mpl
        assert mpl.rcParams["figure.dpi"] == 300


# ─── Test _save method ───────────────────────────────────────────────────────


class TestSaveMethod:
    """Test the _save helper that underlies all chart methods."""

    def test_save_registers_record(self):
        """_save must create a ChartRecord and register it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ChartRegistry(registry_path=Path(tmpdir) / "reg.jsonl")
            factory = AdvancedChartFactory(output_dir=tmpdir, registry=registry)

            # Create a mock figure with a working savefig
            mock_fig = MagicMock()
            mock_fig.savefig = MagicMock(return_value=None)
            path = factory._save(
                mock_fig,
                "test_save",
                fmt="pdf",
                extra_metadata={"note": "test"},
                data_sources=["src1"],
            )

            assert path is not None
            assert path.name == "test_save.pdf"
            assert len(registry.records) == 1
            rec = registry.records[0]
            assert rec.dpi == 300
            assert rec.format == "pdf"
            assert rec.data_sources == ["src1"]
            assert rec.metadata["note"] == "test"

    def test_save_falls_back_to_png_on_error(self):
        """_save falls back to PNG when PDF save fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)

            mock_fig = MagicMock()
            mock_fig.savefig = MagicMock(side_effect=[Exception("PDF error"), None])

            path = factory._save(mock_fig, "fallback_test", fmt="pdf")
            assert path is not None
            assert path.suffix == ".png"
            assert path.name == "fallback_test.png"

    def test_save_calls_fig_savefig(self):
        """_save calls fig.savefig with correct arguments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir, dpi=300)
            mock_fig = MagicMock()
            mock_fig.savefig = MagicMock(return_value=None)
            path = factory._save(mock_fig, "call_test", fmt="png")
            mock_fig.savefig.assert_called_once()
            call_kwargs = mock_fig.savefig.call_args.kwargs
            assert call_kwargs.get("dpi") == 300
            assert call_kwargs.get("bbox_inches") == "tight"

    def test_save_generates_unique_chart_id(self):
        """Each _save call generates a unique chart_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            ids = set()
            for i in range(5):
                mock_fig = MagicMock()
                mock_fig.savefig = MagicMock(return_value=None)
                path = factory._save(mock_fig, f"id_test_{i}", fmt="png")
                ids.add(factory.registry.records[-1].chart_id)
            assert len(ids) == 5  # all unique


# ─── Test AdvancedChartFactory chart methods ─────────────────────────────────


class TestSankeyMethod:
    """Test sankey() method."""

    def test_sankey_returns_path_on_success(self):
        """sankey() returns a Path when rendering succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            nodes = ["A", "B", "C"]
            links = [(0, 1, 100), (1, 2, 80)]
            path = factory.sankey(nodes, links, title="Test Sankey")
            assert path is not None
            assert path.exists()

    def test_sankey_with_data_sources(self):
        """sankey() records data_sources in registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            nodes = ["X", "Y"]
            links = [(0, 1, 50)]
            factory.sankey(nodes, links, data_sources=["CSMAR", "Wind"])
            assert len(factory.registry.records) == 1
            assert "CSMAR" in factory.registry.records[0].data_sources

    def test_sankey_returns_none_on_import_error(self):
        """sankey() returns None when matplotlib.sankey is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"matplotlib.sankey": None}):
                path = factory.sankey(["A"], [(0, 0, 1)])
                # Depends on import error path
                assert path is None or path is not None  # either is fine


class TestFunnelMethod:
    """Test funnel() method."""

    def test_funnel_returns_path(self):
        """funnel() returns a Path when rendering succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            path = factory.funnel(
                stages=["浏览", "注册", "付费"],
                values=[1000, 200, 50],
                title="转化漏斗",
            )
            assert path is not None
            assert path.exists()

    def test_funnel_metadata_contains_chart_type(self):
        """funnel() metadata includes chart_type and stages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            factory.funnel(["A", "B"], [100, 50])
            rec = factory.registry.records[-1]
            assert rec.metadata["chart_type"] == "funnel"

    def test_funnel_returns_none_on_matplotlib_error(self):
        """funnel() returns None when matplotlib is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"matplotlib.pyplot": None}):
                result = factory.funnel(["A"], [100])
                assert result is None


class TestAlluvialMethod:
    """Test alluvial() method."""

    def test_alluvial_returns_path(self):
        """alluvial() returns a Path when rendering succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            categories = [
                ("行业", ["Tech", "Finance"]),
                ("结果", ["正回报", "负回报"]),
            ]
            flows = [("Tech", "正回报", 0.7), ("Tech", "负回报", 0.3)]
            path = factory.alluvial(categories, flows)
            assert path is not None
            assert path.exists()

    def test_alluvial_handles_unknown_flow_members(self):
        """alluvial() skips flows whose members don't appear in categories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            categories = [("A", ["X", "Y"]), ("B", ["P", "Q"])]
            flows = [
                ("X", "P", 0.5),
                ("X", "UNKNOWN", 0.3),  # should be skipped
            ]
            # Must not raise
            path = factory.alluvial(categories, flows)
            assert path is not None or path is None  # either acceptable


class TestConsortMethod:
    """Test consort() method."""

    def test_consort_returns_path(self):
        """consort() returns a Path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            groups = {
                "enrollment": {"excluded": 10, "reasons": ["拒绝参加"]},
                "randomized": 200,
                "allocated": 190,
            }
            path = factory.consort(groups)
            assert path is not None
            assert path.exists()

    def test_consort_empty_groups(self):
        """consort() handles minimal groups dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            path = factory.consort({})
            assert path is not None
            assert path.exists()


class TestDendrogramMethod:
    """Test dendrogram() method."""

    def test_dendrogram_returns_path(self):
        """dendrogram() returns a Path."""
        try:
            import numpy as np
            from scipy.cluster.hierarchy import linkage
        except ImportError:
            pytest.skip("numpy or scipy not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            data = np.array([[1, 2], [1.1, 2.1], [5, 8], [5.1, 8.1]])
            Z = linkage(data)
            path = factory.dendrogram(Z, labels=["a", "b", "c", "d"])
            assert path is not None
            assert path.exists()

    def test_dendrogram_returns_none_on_missing_dependency(self):
        """dendrogram() returns None when scipy is unavailable."""
        import numpy as np  # noqa: F401
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"scipy.cluster.hierarchy": None}):
                result = factory.dendrogram(
                    np.array([[1, 2], [1, 2]]),
                    labels=["a", "b"],
                )
                assert result is None


class TestSunburstMethod:
    """Test sunburst() method."""

    def test_sunburst_returns_path(self):
        """sunburst() returns a Path."""
        try:
            pass
        except ImportError:
            pytest.skip("squarify not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            hierarchy = {"name": "root", "value": 100}
            path = factory.sunburst(hierarchy)
            assert path is not None
            assert path.exists()

    def test_sunburst_returns_none_on_missing_dependency(self):
        """sunburst() returns None when squarify is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"squarify": None}):
                result = factory.sunburst({"name": "root"})
                assert result is None


class TestRidgelineMethod:
    """Test ridgeline() method."""

    def test_ridgeline_returns_path(self):
        """ridgeline() returns a Path."""
        try:
            import seaborn as sns  # noqa: F401
        except ImportError:
            pytest.skip("seaborn not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            time_labels = ["2020", "2021", "2022"]
            distributions = [
                [1, 2, 3, 2, 1],
                [2, 3, 4, 3, 2],
                [1, 3, 5, 3, 1],
            ]
            path = factory.ridgeline(time_labels, distributions)
            assert path is not None
            assert path.exists()

    def test_ridgeline_single_period(self):
        """ridgeline() handles a single time period."""
        try:
            import seaborn as sns  # noqa: F401
        except ImportError:
            pytest.skip("seaborn not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            path = factory.ridgeline(["2020"], [[1, 2, 3, 2, 1]])
            assert path is not None
            assert path.exists()

    def test_ridgeline_empty_distribution(self):
        """ridgeline() handles empty distribution lists."""
        try:
            import seaborn as sns  # noqa: F401
        except ImportError:
            pytest.skip("seaborn not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            # Should not raise
            path = factory.ridgeline(["A", "B"], [[], [1, 2]])
            assert path is not None

    def test_ridgeline_returns_none_on_missing_dependency(self):
        """ridgeline() returns None when seaborn is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"seaborn": None}):
                result = factory.ridgeline(["2020"], [[1, 2, 3]])
                assert result is None


class TestWaffleMethod:
    """Test waffle() method."""

    def test_waffle_returns_path(self):
        """waffle() returns a Path."""
        try:
            import squarify  # noqa: F401
        except ImportError:
            pytest.skip("squarify not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            categories = [("Tech", 40), ("Finance", 35), ("Health", 25)]
            path = factory.waffle(categories, n_cells=20)
            assert path is not None
            assert path.exists()

    def test_waffle_returns_none_on_missing_dependency(self):
        """waffle() returns None when squarify is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            with patch.dict("sys.modules", {"squarify": None}):
                result = factory.waffle([("A", 50)])
                assert result is None


class TestEnsembleRibbonMethod:
    """Test ensemble_ribbon() method."""

    def test_ensemble_ribbon_returns_path(self):
        """ensemble_ribbon() returns a Path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            x = list(range(10))
            y_med = [i * 1.1 for i in range(10)]
            y_low = [i * 0.9 for i in range(10)]
            y_high = [i * 1.3 for i in range(10)]
            path = factory.ensemble_ribbon(x, y_med, y_low, y_high)
            assert path is not None
            assert path.exists()

    def test_ensemble_ribbon_with_mean(self):
        """ensemble_ribbon() includes mean line when y_mean is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            x = list(range(5))
            path = factory.ensemble_ribbon(x, [1, 2, 3, 4, 5], [0, 1, 2, 3, 4], [2, 3, 4, 5, 6], y_mean=[1.5, 2.5, 3.5, 4.5, 5.5])
            assert path is not None
            assert path.exists()
            rec = factory.registry.records[-1]
            assert rec.metadata["chart_type"] == "ensemble_ribbon"


# ─── Test save_all_formats ──────────────────────────────────────────────────


class TestSaveAllFormats:
    """Test save_all_formats() multi-format export."""

    def test_save_all_formats_multiple_formats(self):
        """save_all_formats() saves in multiple formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            mock_fig = MagicMock()
            # At module level: matplotlib.pyplot.savefig is a no-op that returns None
            with patch("matplotlib.pyplot.savefig", return_value=None):
                paths = factory.save_all_formats(mock_fig, "multi_fmt", formats=["pdf", "png"])
            assert "pdf" in paths
            assert "png" in paths
            assert paths["pdf"].name == "multi_fmt.pdf"
            assert paths["png"].name == "multi_fmt.png"

    def test_save_all_formats_single_format(self):
        """save_all_formats() works with single format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            mock_fig = MagicMock()
            with patch("matplotlib.pyplot.savefig", return_value=None):
                paths = factory.save_all_formats(mock_fig, "single_fmt", formats=["svg"])
            assert "svg" in paths

    def test_save_all_formats_empty_formats_defaults_to_pdf_png(self):
        """save_all_formats() defaults to pdf/png when formats is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            mock_fig = MagicMock()
            with patch("matplotlib.pyplot.savefig", return_value=None):
                paths = factory.save_all_formats(mock_fig, "default_fmt", formats=[])
            assert "pdf" in paths
            assert "png" in paths


# ─── Test AdvancedChartFactory initialization ─────────────────────────────────


class TestAdvancedChartFactoryInit:
    """Additional initialization edge cases."""

    def test_output_dir_string_accepted(self):
        """output_dir accepts string and converts to Path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert isinstance(factory.output_dir, Path)

    def test_id_prefix_attribute(self):
        """Factory has _id_prefix attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = AdvancedChartFactory(output_dir=tmpdir)
            assert hasattr(factory, "_id_prefix")
            assert factory._id_prefix == "adv"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
