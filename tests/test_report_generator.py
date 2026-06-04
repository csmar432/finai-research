"""
Tests for ReportGenerator — scripts/research_framework/report_generator.py
"""

import pytest
import tempfile
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.research_framework.report_generator import ReportGenerator
from scripts.research_framework.base import ProvenanceTracker, DataSource


# ── ProvenanceTracker ──────────────────────────────────────────────────────

class TestProvenanceTracker:
    def test_record_and_flag_simulated(self):
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE, detail="Yahoo Finance API")
        tracker.flag_simulated("revenue", reason="No API data available")
        assert tracker._r["roe"]["is_simulated"] is False
        assert tracker._r["revenue"]["is_simulated"] is True
        # source resolves to string value at class def time
        assert tracker._r["revenue"]["source"] == DataSource.SIMULATED

    def test_flag_simulated_creates_new_field(self):
        tracker = ProvenanceTracker()
        tracker.flag_simulated("eps", reason="No data")
        assert "eps" in tracker._r
        assert tracker._r["eps"]["is_simulated"] is True

    def test_flag_fallback(self):
        tracker = ProvenanceTracker()
        tracker.record("market_cap", DataSource.MCP_USER)
        tracker.flag_fallback("market_cap", method="proxy_from_share_price")
        assert tracker._r["market_cap"]["is_fallback"] is True

    def test_simulated_fields_returns_only_simulated(self):
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE)
        tracker.flag_simulated("revenue", "demo")
        tracker.flag_simulated("eps", "demo")
        sim = tracker.simulated_fields()
        assert "revenue" in sim
        assert "eps" in sim
        assert "roe" not in sim

    def test_summary_counts(self):
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE)
        tracker.record("revenue", DataSource.MCP_YFINANCE)
        tracker.flag_simulated("eps", "demo")
        summary = tracker.summary()
        assert summary["total_fields"] == 3
        assert summary["simulated"] == 1
        assert DataSource.MCP_YFINANCE in summary["by_source"]


# ── ReportGenerator ──────────────────────────────────────────────────────────

class TestReportGenerator:
    def test_add_section(self):
        gen = ReportGenerator(output_dir=tempfile.mkdtemp())
        gen.add_section("Introduction", "This is the intro content.")
        assert len(gen._sections) == 1
        assert gen._sections[0]["title"] == "Introduction"

    def test_add_table(self):
        gen = ReportGenerator(output_dir=tempfile.mkdtemp())
        import pandas as pd
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        gen.add_table("tab:test", df, caption_en="Test Table")
        assert len(gen._tables) == 1
        assert gen._tables[0]["label"] == "tab:test"

    def test_set_title_and_abstract(self):
        gen = ReportGenerator(output_dir=tempfile.mkdtemp())
        gen.set_title("测试标题", "Test Title")
        gen.set_abstract("测试摘要", "Test Abstract")
        assert gen._metadata["title_zh"] == "测试标题"
        assert gen._metadata["title_en"] == "Test Title"
        assert gen._metadata["abstract_zh"] == "测试摘要"

    def test_language_switch(self):
        gen = ReportGenerator(output_dir=tempfile.mkdtemp(), language="en")
        gen.set_title("测试", "Test")
        lines = gen._build_tex_content()
        # English title should appear in output
        assert any("Test" in line for line in lines)

        gen.set_language("zh")
        lines_zh = gen._build_tex_content()
        assert any("测试" in line for line in lines_zh)

    def test_save_manifest(self):
        tmp = tempfile.mkdtemp()
        gen = ReportGenerator(output_dir=tmp, language="en")
        gen.set_title("Test", "Test Title")
        gen.save_manifest({"extra_field": "test_value"})
        manifest_path = Path(tmp) / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["n_sections"] == 0
        assert data["extra_field"] == "test_value"

    def test_provenance_appendix_with_simulated_data(self):
        tmp = tempfile.mkdtemp()
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE)
        tracker.flag_simulated("eps", "demo data")
        gen = ReportGenerator(output_dir=tmp, provenance_tracker=tracker)
        latex = gen._build_provenance_appendix()
        assert "SIMULATED" in latex or "simulated" in latex.lower()
        assert "eps" in latex  # Simulated field name appears
        assert "DEMONSTRATION" in latex  # Actual output contains "DEMONSTRATION ONLY"
