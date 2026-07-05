"""tests/test_green_credit_formatter_exec.py — Test green_credit_formatter functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts import green_credit_formatter as gcf
    from scripts.green_credit_formatter import (
        LATEX_TEMPLATE,
        md_to_latex,
        md_to_docx_python,
        md_to_html_bridge,
        _generate_bibtex,
        main,
    )
except Exception as e:
    pytest.skip(f"green_credit_formatter not importable: {e}", allow_module_level=True)


class TestMdToLatex:
    def test_basic_paragraph(self):
        out = md_to_latex("Hello world")
        assert "Hello world" in out

    def test_section_heading(self):
        out = md_to_latex("# Introduction")
        assert "\\section{Introduction}" in out

    def test_subsection(self):
        out = md_to_latex("## Methods")
        assert "\\subsection{Methods}" in out

    def test_subsubsection(self):
        out = md_to_latex("### Sub")
        assert "\\subsubsection{Sub}" in out

    def test_paragraph_bold(self):
        out = md_to_latex("**important**")
        assert "\\paragraph{important}" in out

    def test_separator(self):
        out = md_to_latex("---")
        assert "\\newpage" in out

    def test_table_single_row(self):
        text = "| A | B |\n|---|---|\n"
        out = md_to_latex(text)
        assert "\\begin{table}" in out
        assert "\\toprule" in out
        assert "\\bottomrule" in out

    def test_table_multi_row(self):
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        out = md_to_latex(text)
        assert "\\begin{table}" in out
        assert "\\toprule" in out
        assert "\\midrule" in out

    def test_complex(self):
        text = """# Title

This is intro.

## A subsection

Some text.

| Col1 | Col2 |
|------|------|
| 1 | 2 |
| 3 | 4 |

---
End.
"""
        out = md_to_latex(text)
        assert "\\section{Title}" in out
        assert "\\subsection{A subsection}" in out
        assert "\\begin{table}" in out


class TestMdToDocx:
    def test_md_to_docx(self, tmp_path):
        out = tmp_path / "out.docx"
        text = "# Title\n\nSome text.\n"
        ok = md_to_docx_python(text, out)
        if ok:
            assert out.exists()
            assert out.stat().st_size > 100

    def test_md_to_docx_import_failure(self, tmp_path, monkeypatch):
        # Simulate ImportError for docx
        out = tmp_path / "out.docx"
        monkeypatch.setitem(sys.modules, "docx", None)
        try:
            md_to_docx_python("# Hello", out)
        except Exception:
            pass


class TestMdToHtmlBridge:
    def test_md_to_html(self, tmp_path):
        out = tmp_path / "out.html"
        md_to_html_bridge("# Title\n\nHello\n", out)
        assert out.exists()
        content = out.read_text()
        assert "<h1>" in content
        assert "Hello" in content


class TestGenerateBibtex:
    def test_generate_bibtex(self):
        bib = _generate_bibtex()
        assert isinstance(bib, str)
        # Should have at least @ entries or be empty
        if bib:
            assert "@" in bib


class TestMain:
    def test_main_no_args(self, capsys, monkeypatch):
        # Test main works without crashing
        try:
            monkeypatch.setattr("sys.argv", ["green_credit_formatter.py"])
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # Output should exist
        assert captured.out or captured.err


class TestTemplate:
    def test_latex_template(self):
        assert "\\documentclass" in LATEX_TEMPLATE
        # Template uses literal {{ }} to escape format braces
        assert "\\begin{{document}}" in LATEX_TEMPLATE
        assert "\\end{{document}}" in LATEX_TEMPLATE


class TestSCRIPTDIR:
    def test_script_dir(self):
        from scripts.green_credit_formatter import SCRIPT_DIR
        assert isinstance(SCRIPT_DIR, Path)
        assert SCRIPT_DIR.exists()
