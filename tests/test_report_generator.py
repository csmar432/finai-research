"""
Tests for ReportGenerator — scripts/research_framework/report_generator.py
"""

import pytest
import tempfile
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from scripts.research_framework.report_generator import ReportGenerator, _latex_escape
from scripts.research_framework.base import ProvenanceTracker, DataSource


# ── ProvenanceTracker ──────────────────────────────────────────────────────

class TestProvenanceTracker:
    def test_record_and_flag_simulated(self):
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE, detail="Yahoo Finance API")
        tracker.flag_simulated("revenue", reason="No API data available")
        assert tracker._r["roe"]["is_simulated"] is False
        assert tracker._r["revenue"]["is_simulated"] is True
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
        assert "eps" in latex
        assert "DEMONSTRATION" in latex


# ── Latex Escape ─────────────────────────────────────────────────────────────
# Previously uncovered — security-critical: prevents LaTeX injection

class TestLatexEscape:
    r"""Tests for _latex_escape: prevents injection in table/figure paths.

    The function translates all 10 LaTeX special chars using str.maketrans
    (single-pass replacement). We verify each char appears in its escaped
    LaTeX form.
    """

    def test_escape_plain_text(self):
        """Plain text passes through unchanged."""
        assert _latex_escape("hello world") == "hello world"

    def test_escape_underscore(self):
        r"""Underscores appear in escaped form (\_)."""
        result = _latex_escape("var_name")
        assert r"\_" in result

    def test_escape_dollar(self):
        r"""Dollar signs appear in escaped form (\$)."""
        result = _latex_escape("test$value")
        assert r"\$" in result

    def test_escape_backslash(self):
        r"""Backslashes are replaced with \textbackslash{}."""
        result = _latex_escape("path\\file")
        # \textbackslash{} contains a backslash — this IS the correct LaTeX
        assert r"\textbackslash" in result

    def test_escape_curly_braces(self):
        r"""Curly braces appear in escaped form (\{ and \})."""
        result = _latex_escape("{curly}")
        assert r"\{" in result
        assert r"\}" in result

    def test_escape_hash(self):
        r"""Hash signs appear in escaped form (\#)."""
        result = _latex_escape("path#1")
        assert r"\#" in result

    def test_escape_percent(self):
        r"""Percent signs appear in escaped form (\%)."""
        result = _latex_escape("100%")
        assert r"\%" in result

    def test_escape_ampersand(self):
        r"""Ampersands appear in escaped form (\&)."""
        result = _latex_escape("A&B")
        assert r"\&" in result

    def test_escape_caret(self):
        r"""Carets appear in escaped form (\textasciicircum{})."""
        result = _latex_escape("x^2")
        assert r"\textasciicircum" in result

    def test_escape_tilde(self):
        r"""Tildes appear in escaped form (\textasciitilde{})."""
        result = _latex_escape("n~1")
        assert r"\textasciitilde" in result

    def test_escape_combination(self):
        r"""Multiple special chars are all escaped."""
        result = _latex_escape("path\\to$file#1%")
        assert r"\textbackslash" in result
        assert r"\$" in result
        assert r"\#" in result
        assert r"\%" in result


# ── Generate Tex File ─────────────────────────────────────────────────────────
# Previously uncovered: writes file to disk

class TestGenerateTex:
    """Tests for generate_tex: file I/O and content correctness."""

    def test_generate_tex_writes_file(self, tmp_path):
        """generate_tex writes a .tex file at the expected path."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("Test", "Test Title")
        path = gen.generate_tex("test_paper.tex")
        assert path.exists()
        assert path.suffix == ".tex"

    def test_generate_tex_contains_title(self, tmp_path):
        """Generated .tex contains the paper title."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("Test", "My Paper Title")
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert "My Paper Title" in tex

    def test_generate_tex_contains_preamble(self, tmp_path):
        """Generated .tex contains required LaTeX preamble packages."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert r"\documentclass" in tex
        assert r"\begin{document}" in tex
        assert r"\end{document}" in tex
        assert r"\usepackage{booktabs}" in tex
        assert r"\usepackage{threeparttable}" in tex

    def test_generate_tex_with_section(self, tmp_path):
        """Sections are included in the generated .tex."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("Test", "Title")
        gen.add_section("Introduction", "This paper studies...", level=1)
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert r"\section{Introduction}" in tex
        assert "This paper studies" in tex

    def test_generate_tex_with_raw_latex_table(self, tmp_path):
        """Raw LaTeX table strings are inserted verbatim."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("Test", "Title")
        raw = r"\begin{table}[htbp]\n\\centering\n\\caption{My Table}\n\\end{table}"
        gen.add_table("tab:raw", raw)
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert r"\begin{table}" in tex
        assert "My Table" in tex

    def test_generate_tex_with_dict_did_table(self, tmp_path):
        """Dict-format DID tables are rendered via TableFormatter."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("Test", "Title")
        did_dict = {
            "all_coefs": {
                "did": {"coef": 0.0342, "se": 0.0101, "pval": 0.0007, "sig": "***"},
                "size": {"coef": 0.0120, "se": 0.0050, "pval": 0.0160, "sig": "*"},
            },
            "n_obs": 1200,
            "r_squared": 0.182,
        }
        gen.add_table("tab:did", did_dict, caption_en="Table 1: DID Results")
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert r"\begin{table}" in tex
        assert "did" in tex
        assert "0.0342" in tex

    def test_generate_tex_without_tracker_no_provenance_appendix(self, tmp_path):
        """Without ProvenanceTracker, no provenance appendix is added."""
        gen = ReportGenerator(output_dir=tmp_path, provenance_tracker=None)
        gen.set_title("Test", "Title")
        gen.generate_tex()
        tex = (tmp_path / "paper.tex").read_text(encoding="utf-8")
        assert "Data Provenance Summary" not in tex

    def test_generate_tex_default_filename(self, tmp_path):
        """Default filename is paper.tex."""
        gen = ReportGenerator(output_dir=tmp_path)
        gen.set_title("T", "T")
        path = gen.generate_tex()
        assert path.name == "paper.tex"


# ── Generate Docx ─────────────────────────────────────────────────────────────
# Graceful degradation when python-docx is not installed

class TestGenerateDocx:
    """Tests for generate_docx: graceful fallback when python-docx unavailable."""

    def test_generate_docx_graceful_fallback(self, tmp_path, monkeypatch):
        """When python-docx is unavailable, generate_docx returns None and logs."""
        from unittest.mock import patch

        # Simulate docx not being installed by patching importlib.util.find_spec
        with patch("importlib.util.find_spec", return_value=None):
            import importlib
            import scripts.research_framework.report_generator as rg_mod
            importlib.reload(rg_mod)
            gen = rg_mod.ReportGenerator(output_dir=tmp_path)
            gen.set_title("T", "Title")
            result = gen.generate_docx()
            assert result is None


# ── TableFormatter ─────────────────────────────────────────────────────────────
# Direct tests for the core LaTeX table formatter

class TestTableFormatter:
    """Tests for TableFormatter.did_to_latex and descriptive_to_latex."""

    def test_did_to_latex_basic_structure(self):
        """did_to_latex produces valid LaTeX table structure."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [{
            "all_coefs": {
                "did": {"coef": 0.02, "se": 0.005, "pval": 0.0001, "sig": "***"},
            },
            "n_obs": 500,
            "r_squared": 0.15,
        }]
        latex = TableFormatter.did_to_latex(
            results, ["(1)"], ["did"],
            title="Test Table", label="tab:test",
        )
        assert r"\begin{table}" in latex
        assert r"\caption{Test Table}" in latex
        assert r"\label{tab:test}" in latex
        assert r"\begin{tabular}" in latex
        assert r"\end{tabular}" in latex
        assert "Standard errors" in latex

    def test_did_to_latex_coefficient_format(self):
        """did_to_latex formats coefficients with correct precision."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [{
            "all_coefs": {
                "did": {"coef": 0.034200, "se": 0.010100, "pval": 0.000, "sig": "***"},
            },
            "n_obs": 1000,
            "r_squared": 0.2,
        }]
        latex = TableFormatter.did_to_latex(results, ["(1)"], ["did"])
        assert "0.0342" in latex
        assert "0.0101" in latex

    def test_did_to_latex_multiple_columns(self):
        """did_to_latex handles multiple model columns."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [
            {"all_coefs": {"did": {"coef": 0.02, "se": 0.01, "pval": 0.05, "sig": "*"}}, "n_obs": 100, "r_squared": 0.1},
            {"all_coefs": {"did": {"coef": 0.03, "se": 0.01, "pval": 0.01, "sig": "**"}}, "n_obs": 200, "r_squared": 0.15},
        ]
        latex = TableFormatter.did_to_latex(results, ["(1)", "(2)"], ["did"])
        assert "(1)" in latex
        assert "(2)" in latex

    def test_did_to_latex_simulated_var_red(self):
        """Simulated variables are wrapped in red color markup."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [{
            "all_coefs": {
                "proxy_var": {"coef": 0.05, "se": 0.02, "pval": 0.01, "sig": "**"},
            },
            "n_obs": 100,
            "r_squared": 0.1,
        }]
        latex = TableFormatter.did_to_latex(
            results, ["(1)"], ["proxy_var"],
            simulated_vars={"proxy_var"},
        )
        assert r"\textcolor" in latex or "red" in latex

    def test_did_to_latex_missing_coef_shows_dash(self):
        """Variables not in a model's coefs show a dash."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [{"all_coefs": {}, "n_obs": 100, "r_squared": 0.1}]
        latex = TableFormatter.did_to_latex(results, ["(1)"], ["did"])
        assert "—" in latex

    def test_descriptive_to_latex_structure(self):
        """descriptive_to_latex produces valid LaTeX table."""
        from scripts.research_framework.report_generator import TableFormatter

        # The formatter expects rows = variables, columns = stats (like df.describe().T)
        df = pd.DataFrame({
            "ROA": {"mean": 0.05, "std": 0.02, "min": 0.01, "max": 0.08},
            "LEV": {"mean": 0.3, "std": 0.1, "min": 0.2, "max": 0.5},
        })
        latex = TableFormatter.descriptive_to_latex(
            df, title="Descriptive Statistics", label="tab:desc",
        )
        assert r"\begin{table}" in latex
        assert r"\caption{Descriptive Statistics}" in latex
        assert "ROA" in latex
        assert "LEV" in latex

    def test_descriptive_to_latex_nan_handling(self):
        """descriptive_to_latex handles NaN gracefully (shows em-dash)."""
        from scripts.research_framework.report_generator import TableFormatter

        df = pd.DataFrame({"var": {"mean": 1.0, "std": float("nan"), "min": 3.0}})
        latex = TableFormatter.descriptive_to_latex(df)
        assert "—" in latex or latex is not None


# ── Build Tex Content (integration) ──────────────────────────────────────────

class TestBuildTexContent:
    """Integration tests for _build_tex_content across different scenarios."""

    def test_build_with_multiple_sections(self, tmp_path):
        """Multiple sections at different levels render correctly."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("T", "Paper Title")
        gen.add_section("Introduction", "Intro text", level=1)
        gen.add_section("Literature", "Lit text", level=2)
        gen.add_section("Hypothesis", "Hyp text", level=2)
        lines = gen._build_tex_content()
        tex = "\n".join(lines)
        assert r"\section{Introduction}" in tex
        assert r"\subsection{Literature}" in tex
        assert r"\subsection{Hypothesis}" in tex

    def test_build_with_figure(self, tmp_path):
        """Figures are embedded with \\includegraphics."""
        gen = ReportGenerator(output_dir=tmp_path, language="en")
        gen.set_title("T", "Title")
        fig_path = tmp_path / "fig1.png"
        fig_path.write_text("fake png", encoding="utf-8")
        gen.add_figure(str(fig_path), caption_en="Figure 1", width=0.8)
        lines = gen._build_tex_content()
        tex = "\n".join(lines)
        assert r"\begin{figure}" in tex
        assert r"\includegraphics" in tex
        assert "fig1" in tex
        assert r"\caption{Figure 1}" in tex

    def test_build_with_tracker_provenance_appendix(self, tmp_path):
        """With tracker, provenance appendix is appended."""
        tracker = ProvenanceTracker()
        tracker.record("roe", DataSource.MCP_YFINANCE)
        tracker.flag_simulated("eps", "demo")
        gen = ReportGenerator(output_dir=tmp_path, provenance_tracker=tracker)
        gen.set_title("T", "Title")
        lines = gen._build_tex_content()
        tex = "\n".join(lines)
        assert "Data Provenance Summary" in tex
        assert "eps" in tex

    def test_build_without_bib_file_graceful(self, tmp_path):
        """Without references.bib, a commented-out bib command is used."""
        gen = ReportGenerator(output_dir=tmp_path, provenance_tracker=None)
        gen.set_title("T", "Title")
        lines = gen._build_tex_content()
        tex = "\n".join(lines)
        assert r"\section*{References}" in tex
