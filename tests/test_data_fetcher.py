"""Tests for scripts/research_framework/data_fetcher.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import os


class TestDataFetcherSmoke:
    """Smoke tests for DataFetcher and related classes.

    These tests verify the module loads correctly and core classes
    can be instantiated without errors. They do not make network calls.
    """

    def test_data_fetcher_init(self, tmp_path):
        """DataFetcher initializes with valid parameters."""
        from scripts.research_framework.data_fetcher import DataFetcher

        fetcher = DataFetcher(output_dir=str(tmp_path), verbose=False)
        # output_dir may be stored as Path or str
        assert str(fetcher.output_dir) == str(tmp_path)

    def test_data_fetcher_init_with_tracker(self, tmp_path):
        """DataFetcher accepts ProvenanceTracker."""
        from scripts.research_framework.data_fetcher import DataFetcher, ProvenanceTracker

        tracker = ProvenanceTracker()
        fetcher = DataFetcher(output_dir=str(tmp_path), tracker=tracker)
        assert hasattr(fetcher, "tracker"), "DataFetcher should have tracker attribute"

    def test_mcp_call_error_creation(self):
        """MCPCallError can be created with message."""
        from scripts.research_framework.data_fetcher import MCPCallError

        err = MCPCallError("Test error")
        assert str(err) == "Test error"
        assert hasattr(err, "args")
        assert hasattr(err, "add_note")
        assert hasattr(err, "with_traceback")

    def test_circuit_breaker_init(self):
        """CircuitBreaker initializes with threshold."""
        from scripts.research_framework.data_fetcher import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3)
        assert cb.failure_threshold == 3
        assert hasattr(cb, "is_open")
        assert hasattr(cb, "failures")

    def test_circuit_breaker_trip(self):
        """CircuitBreaker trips after failure_threshold failures."""
        from scripts.research_framework.data_fetcher import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("test_service")
        assert not cb.is_open("test_service")
        cb.record_failure("test_service")  # now at threshold
        assert cb.is_open("test_service")

    def test_circuit_breaker_half_open(self):
        """CircuitBreaker transitions to closed after success."""
        from scripts.research_framework.data_fetcher import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("test_svc")  # trips to open
        assert cb.is_open("test_svc")
        cb.record_success("test_svc")  # transitions to closed
        assert not cb.is_open("test_svc")

    def test_proxy_variable_builder_init(self):
        """ProxyVariableBuilder initializes with optional tracker."""
        from scripts.research_framework.data_fetcher import ProxyVariableBuilder

        builder = ProxyVariableBuilder(tracker=None)
        assert builder is not None
        assert hasattr(builder, "build_esg_proxy")
        assert hasattr(builder, "build_carbon_intensity_proxy")
        assert hasattr(builder, "build_cds_proxy")
        assert hasattr(builder, "build_analyst_coverage_proxy")

    def test_proxy_variable_builder_methods_exist(self):
        """ProxyVariableBuilder has expected proxy-building methods."""
        from scripts.research_framework.data_fetcher import ProxyVariableBuilder

        builder = ProxyVariableBuilder(tracker=None)
        expected_methods = [
            "build_esg_proxy",
            "build_carbon_intensity_proxy",
            "build_cds_proxy",
            "build_analyst_coverage_proxy",
        ]
        for method in expected_methods:
            assert hasattr(builder, method), f"Missing method: {method}"
            assert callable(getattr(builder, method)), f"Not callable: {method}"

    def test_save_df_csv(self, tmp_path):
        """save_df writes a DataFrame to CSV at the given path."""
        from scripts.research_framework.data_fetcher import save_df

        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        csv_path = str(tmp_path / "test_output.csv")
        _ = save_df(df, csv_path)  # noqa: F841 (side-effect only, original var= removed by ruff)
        # save_df may return None or the path — check the file exists
        assert os.path.exists(csv_path), f"File not written: {csv_path}"
        loaded = pd.read_csv(csv_path)
        pd.testing.assert_frame_equal(loaded, df)

    def test_save_json(self, tmp_path):
        """save_json writes a dict to JSON."""
        from scripts.research_framework.data_fetcher import save_json

        data = {"key": "value", "number": 42}
        json_path = str(tmp_path / "test_output.json")
        save_json(data, json_path)
        # save_json may return None — check the file exists
        assert os.path.exists(json_path), f"File not written: {json_path}"
        import json

        with open(json_path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_data_source_enum_members(self):
        """DataSource enum contains expected MCP sources."""
        from scripts.research_framework.data_fetcher import DataSource

        values = [ds.value for ds in DataSource]
        assert any("yfinance" in v for v in values), "yfinance source missing"
        assert any("tushare" in v for v in values), "tushare source missing"
        assert any("arxiv" in v for v in values), "arxiv source missing"

    def test_data_fetcher_output_dir_creates(self, tmp_path):
        """DataFetcher creates output directory if missing."""
        from scripts.research_framework.data_fetcher import DataFetcher

        subdir = tmp_path / "subdir" / "nested"
        assert not subdir.exists()
        DataFetcher(output_dir=str(subdir))
        assert subdir.exists()

    def test_data_fetcher_probe_delay_parameter(self, tmp_path):
        """DataFetcher accepts probe_delay_ms parameter."""
        from scripts.research_framework.data_fetcher import DataFetcher

        fetcher = DataFetcher(
            output_dir=str(tmp_path),
            probe_delay_ms=500,
            verbose=False,
        )
        assert fetcher.probe_delay_ms == 500


class TestDataFetcherNumericalResults:
    """Verify data fetcher returns numerically correct results."""

    def test_save_df_preserves_float_precision(self, tmp_path):
        """save_df preserves float precision (no silent rounding)."""
        from scripts.research_framework.data_fetcher import save_df

        df = pd.DataFrame({
            "price": [12345.6789, 0.0001234],
            "return": [np.nan, 0.5],
        })
        csv_path = str(tmp_path / "float_precision.csv")
        save_df(df, csv_path)
        loaded = pd.read_csv(csv_path)
        pd.testing.assert_frame_equal(loaded, df)

    def test_save_json_preserves_numeric_types(self, tmp_path):
        """save_json preserves int/float types."""
        from scripts.research_framework.data_fetcher import save_json

        data = {"int_val": 42, "float_val": 3.14159, "large_int": 1_000_000_000}
        json_path = str(tmp_path / "numeric_types.json")
        save_json(data, json_path)
        import json

        with open(json_path) as f:
            loaded = json.load(f)
        assert loaded["int_val"] == 42
        assert abs(loaded["float_val"] - 3.14159) < 1e-9
        assert loaded["large_int"] == 1_000_000_000
