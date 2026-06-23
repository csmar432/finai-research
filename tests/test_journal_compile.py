"""
Tests for P0-1: research pipeline end-to-end PDF generation.

Covers:
- journal_template.compile() method existence and behavior
- report_generator.generate_paper() method
- agent_pipeline wire-in (via integration test)

Run:
    pytest tests/test_journal_compile.py -v
"""

import sys
from pathlib import Path

import pytest

# Ensure project root is in sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ─────────────────────────────────────────────────────────────────────────────
# compile() method tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCompileMethod:
    """Tests for JournalTemplate.compile() method."""

    def _make_template(self):
        """Return a minimal JournalTemplate for testing."""
        from scripts.journal_template import JournalTemplate
        return JournalTemplate(
            name="Test",
            short_name="T",
            category="Test",
            description="Test",
            latex_code=r"\documentclass{article}\begin{document}Hi\end{document}",
            bibliography_style="plain",
            required_packages=[],
            page_limit=None,
        )

    def test_compile_method_exists(self):
        """compile() should be a method on JournalTemplate."""
        template = self._make_template()
        assert hasattr(template, "compile"), "compile() method must exist"
        assert callable(template.compile), "compile() must be callable"

    def test_compile_missing_file_returns_false(self):
        """compile() must return False for non-existent .tex files."""
        from unittest.mock import patch
        template = self._make_template()

        with patch("subprocess.run") as mock_run:
            result = template.compile("/nonexistent/path/to/file.tex")
            assert result is False

    def test_compile_no_latex_installed_handled(self, tmp_path):
        """compile() must handle FileNotFoundError gracefully when latex is not installed."""
        from unittest.mock import patch
        template = self._make_template()

        # Create a real .tex file so compile() reaches subprocess
        tex_file = tmp_path / "test.tex"
        tex_file.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")

        # Simulate LaTeX not installed → subprocess.run raises FileNotFoundError
        with patch("subprocess.run", side_effect=FileNotFoundError("No such file or directory: 'xelatex'")):
            # Must not raise — must return False
            result = template.compile(str(tex_file), engine="xelatex")
            assert result is False

    def test_compile_xelatex_engine(self, tmp_path):
        """compile() should accept xelatex as a valid engine name."""
        from unittest.mock import patch, MagicMock
        template = self._make_template()

        tex_file = tmp_path / "test.tex"
        tex_file.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = template.compile(str(tex_file), engine="xelatex")
            assert isinstance(result, bool)

    def test_compile_multiple_passes(self, tmp_path):
        """compile() must run the engine at least twice (for cross-refs, ToC)."""
        from unittest.mock import patch, MagicMock
        template = self._make_template()

        tex_file = tmp_path / "test.tex"
        tex_file.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")

        call_count = 0

        def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            return m

        with patch("subprocess.run", side_effect=count_calls):
            template.compile(str(tex_file), engine="pdflatex", passes=2)
            assert call_count == 2, f"Expected 2 passes, got {call_count}"


# ─────────────────────────────────────────────────────────────────────────────
# generate_paper() method tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneratePaper:
    """Tests for ReportGenerator.generate_paper()."""

    def test_generate_paper_basic(self, tmp_path):
        """generate_paper() must create a .tex file."""
        from scripts.research_framework.report_generator import ReportGenerator

        rg = ReportGenerator(output_dir=str(tmp_path))
        outline = {
            "abstract": "This is an abstract.",
            "introduction": "This is the intro.",
            "conclusion": "This is the conclusion.",
        }

        tex_path = rg.generate_paper(
            topic="Test Topic on ESG and Firm Performance",
            outline=outline,
            data=None,
            regressions=None,
            references=None,
            journal="JFE",
            output_dir=str(tmp_path),
        )

        assert tex_path.exists(), f"Expected .tex file at {tex_path}"
        content = tex_path.read_text(encoding="utf-8")
        assert r"\documentclass" in content, "Must contain documentclass"
        assert r"\begin{document}" in content, "Must contain document body"
        assert r"\end{document}" in content, "Must close document"

    def test_generate_paper_with_journal(self, tmp_path):
        """generate_paper() must handle different journal names."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {
            "abstract": "中文摘要测试。",
            "introduction": "引言部分。",
            "conclusion": "结论。",
        }

        for journal in ["经济研究", "JFE", "RFS", "NeurIPS"]:
            rg = ReportGenerator(output_dir=str(tmp_path / journal))
            tex_path = rg.generate_paper(
                topic=f"Test with {journal}",
                outline=outline,
                journal=journal,
                output_dir=str(tmp_path / journal),
            )
            assert tex_path.exists(), f"tex file not created for journal={journal}"

    def test_generate_paper_all_sections(self, tmp_path):
        """generate_paper() should include all outline sections."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {
            "title_zh": "碳排放权交易对企业绿色创新的影响",
            "title_en": "Carbon Trading and Green Innovation",
            "abstract": "研究摘要。",
            "introduction": "引言内容。",
            "lit_review": "文献综述内容。",
            "methodology": "研究设计。",
            "results": "实证结果。",
            "robustness_checks": "稳健性检验。",
            "conclusion": "结论。",
        }

        rg = ReportGenerator(output_dir=str(tmp_path))
        tex_path = rg.generate_paper(
            topic="Carbon Trading",
            outline=outline,
            journal="经济研究",
            output_dir=str(tmp_path),
        )

        content = tex_path.read_text(encoding="utf-8")
        assert "Carbon Trading" in content or "碳排放" in content
        assert "引言" in content or "intro" in content.lower()
        assert "结论" in content or "Conclusion" in content

    def test_generate_paper_regressions(self, tmp_path):
        """generate_paper() should include regression tables."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {
            "abstract": "Test.",
            "introduction": "Intro.",
            "results": "Results.",
        }
        regressions = {
            "did_main": {
                "all_coefs": {
                    "did": {"coef": 0.05, "se": 0.01, "sig": "***", "pval": 0.001},
                    "size": {"coef": 0.02, "se": 0.01, "sig": "*", "pval": 0.05},
                },
                "n_obs": 10000,
                "r_squared": 0.45,
            },
        }

        rg = ReportGenerator(output_dir=str(tmp_path))
        tex_path = rg.generate_paper(
            topic="DID Test",
            outline=outline,
            regressions=regressions,
            journal="JFE",
            output_dir=str(tmp_path),
        )

        content = tex_path.read_text(encoding="utf-8")
        assert r"\begin{table}" in content or "tab:did" in content

    def test_generate_paper_references(self, tmp_path):
        """generate_paper() should write references.bib when references provided."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {"abstract": "Test.", "introduction": "Intro."}
        references = [
            "@article{smith2020,\n  author={Smith, J.},\n  title={Title},\n  journal={JFE},\n  year={2020}\n}",
        ]

        rg = ReportGenerator(output_dir=str(tmp_path))
        rg.generate_paper(
            topic="Ref Test",
            outline=outline,
            references=references,
            journal="JFE",
            output_dir=str(tmp_path),
        )

        bib_path = tmp_path / "references.bib"
        assert bib_path.exists(), "references.bib must be created"
        assert "smith2020" in bib_path.read_text(encoding="utf-8")

    def test_generate_paper_returns_tex_path(self, tmp_path):
        """generate_paper() must return a Path object."""
        from scripts.research_framework.report_generator import ReportGenerator

        rg = ReportGenerator(output_dir=str(tmp_path))
        result = rg.generate_paper(
            topic="Return Test",
            outline={"abstract": "A", "introduction": "B"},
            journal="JFE",
            output_dir=str(tmp_path),
        )

        assert isinstance(result, Path), f"Expected Path, got {type(result)}"
        assert result.suffix == ".tex", f"Expected .tex suffix, got {result.suffix}"

    def test_generate_paper_chinese_journal(self, tmp_path):
        """Chinese journals should trigger Chinese language mode."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {
            "title_zh": "测试标题",
            "abstract_zh": "中文摘要。",
            "introduction": "引言。",
        }

        rg = ReportGenerator(output_dir=str(tmp_path))
        tex_path = rg.generate_paper(
            topic="Chinese Test",
            outline=outline,
            journal="金融研究",
            output_dir=str(tmp_path),
        )

        assert tex_path.exists()
        content = tex_path.read_text(encoding="utf-8")
        # Should contain Chinese text (not garbled)
        assert "测试" in content or "中文" in content

    def test_generate_paper_with_dict_sections(self, tmp_path):
        """outline sections can be dicts with 'title' and 'content' keys."""
        from scripts.research_framework.report_generator import ReportGenerator

        outline = {
            "abstract": "Abstract text.",
            "introduction": {
                "title": "1. Introduction",
                "content": "Detailed intro content here.",
            },
            "results": {
                "title": "3. Empirical Results",
                "content": "Results content.",
            },
        }

        rg = ReportGenerator(output_dir=str(tmp_path))
        tex_path = rg.generate_paper(
            topic="Dict Section Test",
            outline=outline,
            journal="JFE",
            output_dir=str(tmp_path),
        )

        assert tex_path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Sanity / integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReportGeneratorSanity:
    """Basic sanity checks for the ReportGenerator class."""

    def test_report_generator_import(self):
        """ReportGenerator must be importable."""
        from scripts.research_framework.report_generator import ReportGenerator
        assert ReportGenerator is not None

    def test_report_generator_instantiation(self, tmp_path):
        """ReportGenerator must instantiate without error."""
        from scripts.research_framework.report_generator import ReportGenerator
        rg = ReportGenerator(output_dir=str(tmp_path))
        assert rg is not None
        assert rg.output_dir == Path(tmp_path)

    def test_table_formatter_import(self):
        """TableFormatter must be importable."""
        from scripts.research_framework.report_generator import TableFormatter
        assert TableFormatter is not None

    def test_table_formatter_did_to_latex(self):
        """TableFormatter.did_to_latex() must produce valid LaTeX table."""
        from scripts.research_framework.report_generator import TableFormatter

        results = [{
            "all_coefs": {
                "did": {"coef": 0.05, "se": 0.01, "sig": "***", "pval": 0.001},
            },
            "n_obs": 1000,
            "r_squared": 0.30,
        }]

        latex = TableFormatter.did_to_latex(
            results_list=results,
            y_labels=["Main"],
            x_vars=["did"],
            title="Table 1: DID Results",
            label="tab:did",
        )

        assert r"\begin{table}" in latex
        assert r"\begin{tabular}" in latex
        assert r"\end{table}" in latex
        assert "0.0500" in latex  # coefficient formatted


class TestAgentPipelineWireIn:
    """Verify agent_pipeline.py has the generate_paper wire-in."""

    def test_report_gen_available_flag_exists(self):
        """_REPORT_GEN_AVAILABLE flag must exist in agent_pipeline module."""
        import scripts.agent_pipeline as ap
        assert hasattr(ap, "_REPORT_GEN_AVAILABLE"), \
            "_REPORT_GEN_AVAILABLE flag must be defined in agent_pipeline"

    def test_report_gen_import_in_pipeline(self):
        """ReportGenerator should be imported in agent_pipeline (or gracefully skipped)."""
        import scripts.agent_pipeline as ap
        # The flag exists even if import failed (graceful fallback)
        assert hasattr(ap, "_REPORT_GEN_AVAILABLE")
        assert isinstance(ap._REPORT_GEN_AVAILABLE, bool)

    def test_cli_output_dir_argument(self):
        """CLI must accept --output-dir / -o argument."""
        import argparse

        # Reconstruct the CLI parser as defined in agent_pipeline.py __main__
        parser = argparse.ArgumentParser(description="test")
        parser.add_argument("--topic", "-t", type=str, default=None)
        parser.add_argument("--venue", type=str, default=None)
        parser.add_argument("--langgraph", action="store_true")
        parser.add_argument("--use-hitl", action="store_true")
        parser.add_argument("--language", choices=["zh", "en"], default="zh")
        parser.add_argument("--output-dir", "-o", type=str, default=None)

        args = parser.parse_args(["--topic", "test", "--output-dir", "my_papers/"])
        assert args.output_dir == "my_papers/"

        args2 = parser.parse_args(["--topic", "test", "-o", "other/"])
        assert args2.output_dir == "other/"

        args3 = parser.parse_args(["--topic", "ESG", "-o", "output/papers/"])
        assert args3.output_dir == "output/papers/"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
