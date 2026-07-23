"""Research Framework 单元测试"""
from scripts.research_framework.base import DataSource, ProvenanceTracker
from scripts.research_rag import Chunk


class TestDataSource:
    def test_datasource_values(self):
        assert DataSource.MCP_YFINANCE == "mcp:yfinance"
        assert DataSource.MCP_TUSHARE == "mcp:tushare"
        assert DataSource.MCP_EASTMONEY == "mcp:eastmoney"
        assert DataSource.FALLBACK_PROXY == "fallback:proxy"
        assert DataSource.SIMULATED == "simulated"
        assert DataSource.MANUAL == "manual"

    def test_datasource_is_string(self):
        assert isinstance(DataSource.MCP_YFINANCE, str)


class TestProvenanceTracker:
    def test_provenance_record(self):
        tracker = ProvenanceTracker()
        tracker.record("gdp_china", DataSource.MCP_EODHD, "GDP from EODHD API")
        summary = tracker.summary()
        assert summary["total_fields"] == 1
        # get() requires a key
        record = tracker.get("gdp_china")
        assert record["source"] == "mcp:eodhd"

    def test_provenance_flag_simulated(self):
        tracker = ProvenanceTracker()
        tracker.flag_simulated("roa", "yfinance returned empty")
        record = tracker.get("roa")
        assert record["is_simulated"] is True
        assert record["note"] == "yfinance returned empty"

    def test_provenance_multiple_records(self):
        tracker = ProvenanceTracker()
        tracker.record("field1", DataSource.SIMULATED, "no data")
        tracker.record("field2", DataSource.MANUAL, "user provided")
        summary = tracker.summary()
        assert summary["total_fields"] == 2
        assert summary["by_source"]["simulated"] == 1
        assert summary["by_source"]["manual"] == 1


class TestChunk:
    def test_chunk_creation(self):
        chunk = Chunk(
            id="test_001",
            content="This is a test chunk.",
            paper_id="paper_001",
            section="introduction",
        )
        assert chunk.id == "test_001"
        assert chunk.content == "This is a test chunk."

    def test_chunk_serialization(self):
        chunk = Chunk(id="t1", content="test")
        data = chunk.to_dict()
        assert data["id"] == "t1"
        assert data["content"] == "test"

    def test_chunk_from_dict(self):
        data = {"id": "t2", "content": "test2", "paper_id": "p1"}
        chunk = Chunk.from_dict(data)
        assert chunk.id == "t2"
        assert chunk.content == "test2"


# ── audit-2026-07-04 PR-1 follow-up: real coverage for base.py ─────────────
# PR-1 raised --fail-under to 30; CI reported 26.8% (3.2pp gap).
# Rather than lower the threshold, add real tests for code that has zero
# coverage today (DataProvenance, ProvenanceTracker full API, _stars helper).
# These tests do NOT inflate coverage with import-only smoke — they call
# methods with multiple inputs to exercise real code paths.

from scripts.research_framework.base import DataProvenance, _stars  # noqa: E402


class TestDataProvenance:
    """Tests for DataProvenance dataclass + flag_simulated/flag_fallback."""

    def test_post_init_sets_timestamp(self):
        # When no timestamp is given, __post_init__ auto-fills with UTC ISO.
        prov = DataProvenance(field_name="x", source="mcp:yfinance")
        assert prov.timestamp != ""
        assert "T" in prov.timestamp  # ISO 8601 has T separator

    def test_post_init_preserves_given_timestamp(self):
        prov = DataProvenance(
            field_name="x", source="mcp:yfinance", timestamp="2024-01-01T00:00:00Z"
        )
        assert prov.timestamp == "2024-01-01T00:00:00Z"

    def test_flag_simulated_keeps_field_name(self):
        prov = DataProvenance(field_name="gdp", source="mcp:eodhd")
        flagged = prov.flag_simulated("API quota exceeded")
        assert flagged.field_name == "gdp"
        assert flagged.is_simulated is True
        assert flagged.note == "API quota exceeded"
        assert flagged.source_detail == prov.source_detail

    def test_flag_fallback_keeps_field_name(self):
        prov = DataProvenance(field_name="gdp", source="mcp:eodhd")
        flagged = prov.flag_fallback("proxy=lag_y")
        assert flagged.field_name == "gdp"
        assert flagged.is_fallback is True
        assert flagged.is_simulated is False  # does not cascade

    def test_str_mixin_value(self):
        # DataSource inherits from str, so its str() == its value
        assert str(DataSource.MCP_YFINANCE) == "mcp:yfinance"


class TestStars:
    """Tests for _stars significance helper.

    Per the docstring:
        *** : p < 0.001  (so p == 0.001 stays ***)
        **  : p < 0.01   (so p == 0.01 falls through to *)
        *   : p < 0.05
        †   : p < 0.10
        ""  : p >= 0.10
    """

    def test_stars_0001(self):
        assert _stars(0.0001) == "***"

    def test_stars_001_boundary(self):
        # Boundary: 0.001 stays *** (uses <=)
        assert _stars(0.001) == "***"

    def test_stars_005(self):
        # 0.005 is < 0.01, so **
        assert _stars(0.005) == "**"

    def test_stars_01_boundary(self):
        # 0.01 is NOT < 0.01, falls through to < 0.05, so *
        assert _stars(0.01) == "*"

    def test_stars_03(self):
        # 0.03 is < 0.05, so *
        assert _stars(0.03) == "*"

    def test_stars_05_boundary(self):
        # 0.05 is NOT < 0.05, falls through to < 0.10, so †
        assert _stars(0.05) == r"$\dagger$"

    def test_stars_08(self):
        # 0.08 is < 0.10, so †
        assert _stars(0.08) == r"$\dagger$"

    def test_stars_above(self):
        # 0.5 and beyond: empty
        assert _stars(0.5) == ""
        assert _stars(1.0) == ""
