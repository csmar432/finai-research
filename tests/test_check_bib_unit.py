"""Unit tests for scripts/check_bib.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.check_bib import (
    extract_bib_keys,
    extract_cite_keys,
    find_bib_files,
    strip_comments,
)


class TestStripComments:
    """strip_comments() removes comment lines."""

    def test_removes_comment_lines(self):
        text = "% this is comment\nreal content\n% another comment"
        result = strip_comments(text)
        assert "% this is comment" not in result
        assert "real content" in result

    def test_keeps_non_comment_lines(self):
        text = "line1\nline2"
        result = strip_comments(text)
        assert "line1" in result
        assert "line2" in result

    def test_indented_comment_still_stripped(self):
        text = "    % indented comment\ncontent"
        result = strip_comments(text)
        assert "% indented comment" not in result


class TestExtractCiteKeys:
    """extract_cite_keys() finds \\cite{} references."""

    def test_simple_cite(self):
        text = r"\cite{key1}"
        keys = extract_cite_keys(text)
        assert "key1" in keys

    def test_multiple_keys(self):
        text = r"\cite{key1,key2,key3}"
        keys = extract_cite_keys(text)
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys

    def test_cite_with_prefix(self):
        text = r"\cite[p.~5]{key1}"
        keys = extract_cite_keys(text)
        assert "key1" in keys

    def test_citep_command(self):
        text = r"\citep{key1}"
        keys = extract_cite_keys(text)
        assert "key1" in keys

    def test_citet_command(self):
        text = r"\citet{key1}"
        keys = extract_cite_keys(text)
        assert "key1" in keys

    def test_no_cite_returns_empty(self):
        text = "no cite here"
        keys = extract_cite_keys(text)
        assert keys == set()

    def test_ignores_comments(self):
        text = r"% \cite{ignored}" + "\n" + r"\cite{real_key}"
        keys = extract_cite_keys(text)
        assert "ignored" not in keys
        assert "real_key" in keys

    def test_key_with_colon(self):
        text = r"\cite{smith:2020}"
        keys = extract_cite_keys(text)
        assert "smith:2020" in keys


class TestExtractBibKeys:
    """extract_bib_keys() finds BibTeX entries."""

    def test_article(self):
        text = textwrap.dedent("""
            @article{key1,
              author = {X},
              title = {Y},
            }
        """)
        keys = extract_bib_keys(text)
        assert "key1" in keys

    def test_book(self):
        text = textwrap.dedent("""
            @book{book_key,
              title = {Z},
            }
        """)
        keys = extract_bib_keys(text)
        assert "book_key" in keys

    def test_multiple_entries(self):
        text = textwrap.dedent("""
            @article{key1,
              author = {X},
            }
            @book{key2,
              title = {Z},
            }
        """)
        keys = extract_bib_keys(text)
        assert "key1" in keys
        assert "key2" in keys

    def test_empty(self):
        keys = extract_bib_keys("")
        assert keys == set()


class TestFindBibFiles:
    """find_bib_files() resolves .bib file paths."""

    def test_nonexistent_tex(self, tmp_path):
        result = find_bib_files(tmp_path / "nonexistent.tex")
        assert result == []

    def test_tex_with_bibliography(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{x,}")
        tex = tmp_path / "main.tex"
        tex.write_text(r"\bibliography{refs}")
        result = find_bib_files(tex)
        assert any(p.name == "refs.bib" for p in result)

    def test_tex_with_addbibresource(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{x,}")
        tex = tmp_path / "main.tex"
        tex.write_text(r"\addbibresource{refs.bib}")
        result = find_bib_files(tex)
        assert any(p.name == "refs.bib" for p in result)
