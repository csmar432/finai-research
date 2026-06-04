"""Research Framework 单元测试"""
import pytest
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
