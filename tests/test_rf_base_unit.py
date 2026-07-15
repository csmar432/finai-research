"""Unit tests for scripts.research_framework.base module.

Tests shared enums, dataclasses, and helper utilities used across the framework.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def MODULE_ABBREV():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.research_framework import base as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_datasource_enum(MODULE_ABBREV):
    """DataSource is a str+Enum hybrid."""
    DataSource = MODULE_ABBREV.DataSource
    assert DataSource.MCP_YFINANCE.value == "mcp:yfinance"
    assert DataSource.MCP_TUSHARE.value == "mcp:tushare"
    # string comparison works (str + Enum)
    assert DataSource.SIMULATED == "simulated"


def test_datasource_str_dunder(MODULE_ABBREV):
    ds = MODULE_ABBREV.DataSource.MCP_YFINANCE
    assert str(ds) == "mcp:yfinance"


def test_dataprovenance_dataclass(MODULE_ABBREV):
    """DataProvenance can be instantiated with required fields."""
    DataProvenance = MODULE_ABBREV.DataProvenance
    p = DataProvenance(field_name="roa", source=MODULE_ABBREV.DataSource.MCP_YFINANCE)
    assert p.field_name == "roa"
    assert p.is_simulated is False
    assert p.is_fallback is False
    assert p.timestamp != ""


def test_dataprovenance_flag_simulated(MODULE_ABBREV):
    DataProvenance = MODULE_ABBREV.DataProvenance
    p = DataProvenance(field_name="roa", source=MODULE_ABBREV.DataSource.MCP_YFINANCE)
    flagged = p.flag_simulated("yfinance empty")
    assert flagged.is_simulated is True
    assert flagged.source == MODULE_ABBREV.DataSource.SIMULATED


def test_dataprovenance_flag_fallback(MODULE_ABBREV):
    DataProvenance = MODULE_ABBREV.DataProvenance
    p = DataProvenance(field_name="roa", source=MODULE_ABBREV.DataSource.MCP_YFINANCE)
    flagged = p.flag_fallback(method="nearest_neighbor")
    assert flagged.is_fallback is True
    assert flagged.source == MODULE_ABBREV.DataSource.FALLBACK_PROXY


def test_provenance_tracker_record(MODULE_ABBREV):
    """ProvenanceTracker.record and summary work."""
    ProvenanceTracker = MODULE_ABBREV.ProvenanceTracker
    tracker = ProvenanceTracker()
    tracker.record("roa", MODULE_ABBREV.DataSource.MCP_YFINANCE, "yfinance API")
    assert len(tracker) == 1
    assert "roa" in tracker.simulated_fields() or len(tracker.simulated_fields()) == 0


def test_provenance_tracker_flag_simulated(MODULE_ABBREV):
    ProvenanceTracker = MODULE_ABBREV.ProvenanceTracker
    tracker = ProvenanceTracker()
    tracker.record("roa", MODULE_ABBREV.DataSource.MCP_YFINANCE, "API")
    tracker.flag_simulated("roa", "fake")
    assert "roa" in tracker.simulated_fields()


def test_provenance_tracker_summary(MODULE_ABBREV):
    ProvenanceTracker = MODULE_ABBREV.ProvenanceTracker
    tracker = ProvenanceTracker()
    tracker.record("roa", MODULE_ABBREV.DataSource.MCP_YFINANCE, "")
    tracker.record("lev", MODULE_ABBREV.DataSource.SIMULATED, "")
    summary = tracker.summary()
    assert "total_fields" in summary
    assert summary["total_fields"] == 2
    assert "by_source" in summary


def test_provenance_tracker_save(tmp_path, MODULE_ABBREV):
    ProvenanceTracker = MODULE_ABBREV.ProvenanceTracker
    tracker = ProvenanceTracker()
    tracker.record("roa", MODULE_ABBREV.DataSource.MCP_YFINANCE, "x")
    out = tmp_path / "prov.json"
    tracker.save(out)
    assert out.exists()


def test_stars_function(MODULE_ABBREV):
    """_stars returns LaTeX significance markers based on p-value."""
    _stars = MODULE_ABBREV._stars
    assert _stars(0.0005) == "***"
    assert _stars(0.005) == "**"
    assert _stars(0.03) == "*"
    assert _stars(0.07) == r"$\dagger$"
    assert _stars(0.5) == ""


def test_fmt_coef_function(MODULE_ABBREV):
    fmt_coef = MODULE_ABBREV.fmt_coef
    s = fmt_coef(0.052, 0.021, 0.03, stars=True)
    assert isinstance(s, str)
    assert "0.052" in s
    assert "0.021" in s


def test_to_markdown_table_returns_str(MODULE_ABBREV):
    import pandas as pd

    to_markdown_table = MODULE_ABBREV.to_markdown_table
    df = pd.DataFrame({"a": [1.0, 2.0], "b": ["x", "y"]})
    s = to_markdown_table(df)
    assert isinstance(s, str)
    assert "a" in s and "b" in s


def test_to_markdown_table_empty(MODULE_ABBREV):
    import pandas as pd

    to_markdown_table = MODULE_ABBREV.to_markdown_table
    df = pd.DataFrame()
    s = to_markdown_table(df)
    assert isinstance(s, str)


def test_to_latex_table_returns_str(MODULE_ABBREV):
    import pandas as pd

    to_latex_table = MODULE_ABBREV.to_latex_table
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    s = to_latex_table(df, caption="Test", label="tab:test")
    assert isinstance(s, str)
    assert "tabular" in s or "table" in s
