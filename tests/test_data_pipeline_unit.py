"""Unit tests for scripts/data_pipeline.py."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.data_pipeline import load_data, preprocess_data


class TestLoadData:
    """load_data() reads files."""

    def test_csv_load(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n3,4\n")
        df = load_data(path)
        assert len(df) == 2
        assert "a" in df.columns

    def test_unsupported_format_raises(self, tmp_path):
        path = tmp_path / "data.xyz"
        path.write_text("data")
        with pytest.raises(ValueError):
            load_data(path)

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_data(tmp_path / "nonexistent.csv")

    def test_txt_load(self, tmp_path):
        path = tmp_path / "data.txt"
        path.write_text("a\n1\n2\n")
        df = load_data(path)
        assert len(df) >= 1

    def test_parquet_load(self, tmp_path):
        pytest.importorskip("pyarrow")
        path = tmp_path / "data.parquet"
        df_orig = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        df_orig.to_parquet(path)
        df = load_data(path)
        assert (df["x"] == [1, 2, 3]).all()


class TestPreprocessData:
    """preprocess_data() cleans DataFrames."""

    def test_empty_returns_empty(self):
        df = pd.DataFrame()
        result = preprocess_data(df)
        assert len(result) == 0

    def test_drops_all_null_rows(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, None, 6]})
        result = preprocess_data(df)
        assert len(result) == 2

    def test_converts_date_column(self):
        df = pd.DataFrame({"date": ["2020-01-01", "2020-02-01"], "x": [1, 2]})
        result = preprocess_data(df)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])

    def test_converts_chinese_date_column(self):
        df = pd.DataFrame({"日期": ["2020-01-01", "2020-02-01"], "x": [1, 2]})
        result = preprocess_data(df)
        assert pd.api.types.is_datetime64_any_dtype(result["日期"])

    def test_drops_high_null_columns(self):
        """Columns with >50% nulls should be dropped."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})
        result = preprocess_data(df)
        assert "b" not in result.columns
        assert "a" in result.columns

    def test_keeps_low_null_columns(self):
        """Columns with <50% nulls should be kept."""
        df = pd.DataFrame({"a": [1, None, 3]})
        result = preprocess_data(df)
        assert "a" in result.columns

    def test_returns_copy(self):
        """Should not modify the original."""
        df = pd.DataFrame({"a": [1, 2, 3]})
        original_len = len(df)
        preprocess_data(df)
        assert len(df) == original_len
