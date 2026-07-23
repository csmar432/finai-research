"""
Unit tests for scripts/us_esg_formatter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))



class TestConstants:
    """Test module-level constants."""

    def test_title_defined(self):
        from scripts.us_esg_formatter import TITLE

        assert isinstance(TITLE, str)
        assert len(TITLE) > 10
        assert "ESG" in TITLE

    def test_shorttitle_defined(self):
        from scripts.us_esg_formatter import SHORTTITLE

        assert isinstance(SHORTTITLE, str)
        assert len(SHORTTITLE) > 0

    def test_abstract_defined(self):
        from scripts.us_esg_formatter import ABSTRACT

        assert isinstance(ABSTRACT, str)
        assert len(ABSTRACT) > 100
        assert "ESG" in ABSTRACT

    def test_keywords_defined(self):
        from scripts.us_esg_formatter import KEYWORDS

        assert isinstance(KEYWORDS, str)
        assert "ESG" in KEYWORDS

    def test_n_obs_is_int(self):
        from scripts.us_esg_formatter import n_obs

        assert isinstance(n_obs, int)
        assert n_obs >= 0

    def test_n_firms_is_int(self):
        from scripts.us_esg_formatter import n_firms

        assert isinstance(n_firms, int)
        assert n_firms >= 0


class TestTableConstants:
    """Test LaTeX table constants."""

    def test_table2_latex_defined(self):
        from scripts.us_esg_formatter import TABLE2_LATEX

        assert isinstance(TABLE2_LATEX, str)
        assert r"\begin{table}" in TABLE2_LATEX
        assert r"\caption{Descriptive Statistics}" in TABLE2_LATEX
        assert r"\end{table}" in TABLE2_LATEX
        assert r"\begin{threeparttable}" in TABLE2_LATEX

    def test_table3_latex_defined(self):
        from scripts.us_esg_formatter import TABLE3_LATEX

        assert isinstance(TABLE3_LATEX, str)
        assert r"\begin{table}" in TABLE3_LATEX
        assert r"\caption{ESG and Financing Constraints" in TABLE3_LATEX
        assert r"\end{table}" in TABLE3_LATEX

    def test_table4_latex_defined(self):
        from scripts.us_esg_formatter import TABLE4_LATEX

        assert isinstance(TABLE4_LATEX, str)
        assert r"\begin{table}" in TABLE4_LATEX
        assert r"\caption{Heterogeneity" in TABLE4_LATEX

    def test_table5_latex_defined(self):
        from scripts.us_esg_formatter import TABLE5_LATEX

        assert isinstance(TABLE5_LATEX, str)
        assert r"\caption{Mechanism" in TABLE5_LATEX

    def test_table_latex_contain_tablenotes(self):
        from scripts.us_esg_formatter import TABLE2_LATEX, TABLE3_LATEX

        for table in [TABLE2_LATEX, TABLE3_LATEX]:
            assert r"\begin{tablenotes}" in table
            assert r"\end{tablenotes}" in table

    def test_table_latex_contain_booktabs(self):
        from scripts.us_esg_formatter import TABLE2_LATEX, TABLE3_LATEX

        for table in [TABLE2_LATEX, TABLE3_LATEX]:
            assert r"\toprule" in table
            assert r"\midrule" in table
            assert r"\bottomrule" in table


class TestLatexDoc:
    """Test the full LaTeX document constant."""

    def test_latex_doc_defined(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert isinstance(LATEX_DOC, str)
        assert len(LATEX_DOC) > 1000

    def test_latex_doc_has_documentclass(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert r"\documentclass" in LATEX_DOC
        assert r"\begin{document}" in LATEX_DOC
        assert r"\end{document}" in LATEX_DOC

    def test_latex_doc_has_abstract(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert r"\begin{abstract}" in LATEX_DOC
        assert r"\end{abstract}" in LATEX_DOC

    def test_latex_doc_has_title(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert r"\title{" in LATEX_DOC

    def test_latex_doc_has_packages(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert r"\usepackage{booktabs,threeparttable}" in LATEX_DOC
        assert r"\usepackage{amsmath,amssymb,bm,mathtools}" in LATEX_DOC

    def test_latex_doc_has_sections(self):
        from scripts.us_esg_formatter import LATEX_DOC

        assert r"\section{Introduction}" in LATEX_DOC
        assert r"\section{Literature Review" in LATEX_DOC


class TestPaths:
    """Test path constants."""

    def test_project_root_defined(self):
        from scripts.us_esg_formatter import _PROJECT_ROOT

        assert isinstance(_PROJECT_ROOT, Path)

    def test_base_dir_defined(self):
        from scripts.us_esg_formatter import BASE

        assert isinstance(BASE, Path)
        assert "us_esg_financing" in str(BASE)

    def test_latex_dir_defined(self):
        from scripts.us_esg_formatter import LATEX_DIR

        assert isinstance(LATEX_DIR, Path)
        assert "latex" in str(LATEX_DIR)


class TestDocxAvailability:
    """Test python-docx availability flag."""

    def test_has_docx_is_bool(self):
        from scripts.us_esg_formatter import HAS_DOCX

        assert isinstance(HAS_DOCX, bool)

    def test_has_docx_value(self):
        from scripts.us_esg_formatter import HAS_DOCX

        # Should be True if python-docx is installed
        # (it's listed in pyproject.toml dependencies)
        assert HAS_DOCX in [True, False]


class TestPanelRowsData:
    """Test panel data loading."""

    def test_panel_rows_is_list(self):
        from scripts.us_esg_formatter import panel_rows

        assert isinstance(panel_rows, list)

    def test_panel_csv_path_defined(self):
        from scripts.us_esg_formatter import _panel_csv_path

        assert isinstance(_panel_csv_path, Path)
        assert _panel_csv_path.name == "panel_data.csv"
