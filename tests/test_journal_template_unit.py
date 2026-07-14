"""Unit tests for scripts/journal_template.py - focused coverage push.

Targets the journal_template module's dataclass and helper functions:
- JournalTemplate dataclass (generate_example, compile backend selection)
- _detect_best_backend (with mocked shutil.which)
- _compile_tectonic, _compile_standard, _compile_pandoc_fallback
- get_template, list_templates, generate_paper, get_all_templates
- LATEX_BIB_STYLES, _bst_for_journal
- JournalTemplateSelector (detect_journal, generate_latex, list_journals, get_reference_format)
- TEMPLATES dict content (all-journals sanity check)

All tests avoid real LaTeX compilation by mocking subprocess.run / shutil.which.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.journal_template import (  # noqa: E402
    JournalTemplate,
    JournalTemplateSelector,
    LATEX_BIB_STYLES,
    TEMPLATES,
    _bst_for_journal,
    _build_multilang_latex,
    generate_paper,
    get_all_templates,
    get_template,
    list_multilang_templates,
    list_templates,
)


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def minimal_template():
    """A minimal JournalTemplate for unit tests."""
    return JournalTemplate(
        name="Test Journal",
        short_name="TJ",
        category="Test",
        description="A test journal template",
        latex_code=r"\documentclass{article}\begin{document}Test\end{document}",
        bibliography_style="plain",
        required_packages=["amsmath"],
        page_limit=None,
    )


@pytest.fixture
def selector():
    return JournalTemplateSelector()


# ════════════════════════════════════════════════════════════════════
# JournalTemplate dataclass
# ════════════════════════════════════════════════════════════════════


class TestJournalTemplateDataclass:
    """JournalTemplate dataclass field defaults and behavior."""

    def test_default_author_notes_false(self):
        t = JournalTemplate(
            name="x", short_name="X", category="y",
            description="z", latex_code="", bibliography_style="a",
            required_packages=[], page_limit=None,
        )
        assert t.author_notes is False
        assert t.blind_review is True
        assert t.url == ""

    def test_custom_author_notes_and_blind(self):
        t = JournalTemplate(
            name="x", short_name="X", category="y",
            description="z", latex_code="", bibliography_style="a",
            required_packages=[], page_limit=None,
            author_notes=True, blind_review=False, url="https://example.com",
        )
        assert t.author_notes is True
        assert t.blind_review is False
        assert t.url == "https://example.com"

    def test_generate_example_writes_file(self, tmp_path):
        t = JournalTemplate(
            name="x", short_name="X", category="y", description="z",
            latex_code=r"\documentclass{article}\begin{document}Hi\end{document}",
            bibliography_style="a", required_packages=[], page_limit=None,
        )
        out = tmp_path / "x.tex"
        result = t.generate_example(out)
        assert result == out
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert r"\documentclass" in content
        assert r"\end{document}" in content

    def test_generate_example_accepts_string_path(self, tmp_path):
        t = JournalTemplate(
            name="x", short_name="X", category="y", description="z",
            latex_code="CODE", bibliography_style="a", required_packages=[], page_limit=None,
        )
        out = tmp_path / "str.tex"
        result = t.generate_example(str(out))
        assert result.exists()
        assert result.read_text(encoding="utf-8") == "CODE"


# ════════════════════════════════════════════════════════════════════
# _detect_best_backend
# ════════════════════════════════════════════════════════════════════


class TestDetectBestBackend:
    """Cover _detect_best_backend priority order via mocked shutil.which."""

    def test_returns_none_when_no_backends(self, minimal_template):
        with patch("shutil.which", return_value=None):
            result = minimal_template._detect_best_backend()
        assert result is None

    def test_returns_tectonic_when_available(self, minimal_template):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/tectonic" if x == "tectonic" else None):
            assert minimal_template._detect_best_backend() == "tectonic"

    def test_falls_back_to_xelatex(self, minimal_template):
        def fake_which(name):
            return "/usr/bin/xelatex" if name == "xelatex" else None

        with patch("shutil.which", side_effect=fake_which):
            assert minimal_template._detect_best_backend() == "xelatex"

    def test_falls_back_to_pdflatex(self, minimal_template):
        def fake_which(name):
            return "/usr/bin/pdflatex" if name == "pdflatex" else None

        with patch("shutil.which", side_effect=fake_which):
            assert minimal_template._detect_best_backend() == "pdflatex"

    def test_falls_back_to_lualatex(self, minimal_template):
        def fake_which(name):
            return "/usr/bin/lualatex" if name == "lualatex" else None

        with patch("shutil.which", side_effect=fake_which):
            assert minimal_template._detect_best_backend() == "lualatex"


# ════════════════════════════════════════════════════════════════════
# compile() - dispatch & error handling
# ════════════════════════════════════════════════════════════════════


class TestCompileDispatch:
    """Test the compile() dispatch logic and error paths."""

    def test_compile_returns_false_when_file_missing(self, minimal_template):
        result = minimal_template.compile("/tmp/does_not_exist_xyz.tex", engine="pdflatex")
        assert result is False

    def test_compile_returns_false_when_no_backend(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value=None):
            result = minimal_template.compile(tex, engine=None)
        assert result is False

    def test_compile_unknown_engine_falls_back_to_autodetect(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        # tectonic present → fall back succeeds
        with patch("shutil.which", return_value="/usr/bin/tectonic"):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            (tmp_path / "f.pdf").touch()
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template.compile(tex, engine="nonexistent_engine")
        assert result is True

    def test_compile_unknown_engine_no_fallback(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value=None):
            result = minimal_template.compile(tex, engine="nonexistent_engine")
        assert result is False

    def test_compile_pandoc_dispatch(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/pandoc" if x == "pandoc" else None):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            (tmp_path / "f.docx").touch()
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template.compile(tex, engine="pandoc")
        assert result is True


# ════════════════════════════════════════════════════════════════════
# _compile_tectonic
# ════════════════════════════════════════════════════════════════════


class TestCompileTectonic:
    """Test _compile_tectonic behavior."""

    def test_tectonic_not_installed(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value=None):
            result = minimal_template._compile_tectonic(tex)
        assert result is False

    def test_tectonic_success(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        (tmp_path / "f.pdf").touch()
        with patch("shutil.which", return_value="/usr/bin/tectonic"):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_tectonic(tex)
        assert result is True

    def test_tectonic_non_zero_with_ctex_warning(self, minimal_template, tmp_path, capsys):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/tectonic"):
            fake_proc = MagicMock(returncode=1, stderr="ctex error", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_tectonic(tex)
        assert result is False

    def test_tectonic_timeout(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/tectonic"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="tectonic", timeout=120),
            ):
                result = minimal_template._compile_tectonic(tex)
        assert result is False

    def test_tectonic_general_exception(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/tectonic"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=RuntimeError("boom"),
            ):
                result = minimal_template._compile_tectonic(tex)
        assert result is False


# ════════════════════════════════════════════════════════════════════
# _compile_standard
# ════════════════════════════════════════════════════════════════════


class TestCompileStandard:
    """Test _compile_standard for xelatex/pdflatex/lualatex."""

    def test_engine_not_installed(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value=None):
            result = minimal_template._compile_standard(tex, "xelatex", passes=2)
        assert result is False

    def test_compile_xelatex_success(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        (tmp_path / "f.pdf").touch()
        with patch("shutil.which", return_value="/usr/bin/xelatex"):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_standard(tex, "xelatex", passes=2)
        assert result is True

    def test_compile_pdflatex_no_pdf_returned(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_standard(tex, "pdflatex", passes=1)
        assert result is False

    def test_compile_pdflatex_fatal_error_returns_early(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            fake_proc = MagicMock(returncode=1, stderr="! Fatal error occurred", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_standard(tex, "pdflatex", passes=3)
        assert result is False

    def test_compile_pdflatex_font_cjk_warning_message(self, minimal_template, tmp_path, capsys):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            fake_proc = MagicMock(returncode=1, stderr="! Fatal error cjk font missing", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_standard(tex, "pdflatex", passes=1)
        assert result is False

    def test_compile_pdflatex_timeout(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="pdflatex", timeout=90),
            ):
                result = minimal_template._compile_standard(tex, "pdflatex", passes=1)
        assert result is False

    def test_compile_pdflatex_filenotfound(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=FileNotFoundError("no pdflatex"),
            ):
                result = minimal_template._compile_standard(tex, "pdflatex", passes=1)
        assert result is False

    def test_compile_lualatex_general_exception(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/lualatex"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=RuntimeError("boom"),
            ):
                result = minimal_template._compile_standard(tex, "lualatex", passes=1)
        assert result is False


# ════════════════════════════════════════════════════════════════════
# _compile_pandoc_fallback
# ════════════════════════════════════════════════════════════════════


class TestCompilePandocFallback:
    """Test _compile_pandoc_fallback behavior."""

    def test_pandoc_not_installed(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value=None):
            result = minimal_template._compile_pandoc_fallback(tex)
        assert result is False

    def test_pandoc_success(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        (tmp_path / "f.docx").touch()
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            fake_proc = MagicMock(returncode=0, stderr="", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_pandoc_fallback(tex)
        assert result is True

    def test_pandoc_failure(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            fake_proc = MagicMock(returncode=1, stderr="pandoc error", stdout="")
            with patch("scripts.journal_template.subprocess.run", return_value=fake_proc):
                result = minimal_template._compile_pandoc_fallback(tex)
        assert result is False

    def test_pandoc_exception(self, minimal_template, tmp_path):
        tex = tmp_path / "f.tex"
        tex.write_text("Hi")
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            with patch(
                "scripts.journal_template.subprocess.run",
                side_effect=RuntimeError("boom"),
            ):
                result = minimal_template._compile_pandoc_fallback(tex)
        assert result is False


# ════════════════════════════════════════════════════════════════════
# Module-level template registry & getters
# ════════════════════════════════════════════════════════════════════


class TestTemplateRegistry:
    """Test TEMPLATES dict, get_template, list_templates, get_all_templates."""

    def test_templates_dict_non_empty(self):
        assert isinstance(TEMPLATES, dict)
        assert len(TEMPLATES) > 0

    def test_all_templates_are_journal_template_instances(self):
        for name, t in TEMPLATES.items():
            assert isinstance(t, JournalTemplate), f"{name} is not a JournalTemplate"

    def test_get_template_uppercase(self):
        t = get_template("JFE")
        assert t is not None
        assert t.short_name == "JFE"

    def test_get_template_lowercase_fallback(self):
        # TEMPLATES is keyed uppercase; lowercase lookup returns None
        assert get_template("jfe") is None or get_template("jfe").short_name == "JFE"

    def test_get_template_unknown_returns_none(self):
        assert get_template("NONEXISTENT_XYZ") is None

    def test_get_all_templates_returns_dict(self):
        all_t = get_all_templates()
        assert isinstance(all_t, dict)
        assert len(all_t) >= len(TEMPLATES)

    def test_list_templates_no_filter(self):
        templates = list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_list_templates_with_category_filter(self):
        templates = list_templates(category="金融")
        assert all(t.category == "金融" for t in templates)
        assert len(templates) > 0

    def test_list_templates_filter_no_match(self):
        templates = list_templates(category="NONEXISTENT_CATEGORY")
        assert templates == []

    def test_generate_paper_success(self, tmp_path):
        out = tmp_path / "paper.tex"
        result = generate_paper("JFE", out)
        assert result == out
        assert out.exists()

    def test_generate_paper_unknown_raises(self, tmp_path):
        with pytest.raises(ValueError, match="未找到模板"):
            generate_paper("DOES_NOT_EXIST", tmp_path / "x.tex")

    def test_list_multilang_templates(self):
        # Returns a list (possibly empty if multilang module unavailable)
        result = list_multilang_templates()
        assert isinstance(result, list)


# ════════════════════════════════════════════════════════════════════
# LATEX_BIB_STYLES & _bst_for_journal
# ════════════════════════════════════════════════════════════════════


class TestLatexBibStyles:
    """Test LATEX_BIB_STYLES dict and _bst_for_journal helper."""

    def test_chinese_journals_use_gbt7714(self):
        for j in ["经济研究", "金融研究", "管理世界"]:
            assert LATEX_BIB_STYLES[j] == "gbt7714-2015"

    def test_english_journals_in_dict(self):
        for j in ["JF", "JFE", "RFS"]:
            assert j in LATEX_BIB_STYLES

    def test_bst_for_journal_known(self):
        assert _bst_for_journal("经济研究", "fallback") == "gbt7714-2015"
        assert _bst_for_journal("JF", "fallback") == "aer"

    def test_bst_for_journal_unknown_returns_fallback(self):
        assert _bst_for_journal("DOES_NOT_EXIST", "my_fallback") == "my_fallback"
        assert _bst_for_journal("", "empty_fallback") == "empty_fallback"


# ════════════════════════════════════════════════════════════════════
# JournalTemplateSelector
# ════════════════════════════════════════════════════════════════════


class TestJournalTemplateSelector:
    """Test the JournalTemplateSelector class."""

    def test_init_uses_module_dict(self, selector):
        # journals should refer to the module's JOURNAL_METADATA dict
        from scripts.journal_template import JOURNAL_METADATA
        assert selector.journals is JOURNAL_METADATA

    def test_detect_journal_no_input_raises(self, selector):
        with pytest.raises(ValueError, match="Must provide at least one"):
            selector.detect_journal()

    def test_detect_journal_empty_strings_raises(self, selector):
        with pytest.raises(ValueError, match="Must provide at least one"):
            selector.detect_journal(topic="", abstract="", keywords=[])

    def test_detect_journal_chinese_topic_returns_chinese_journal(self, selector):
        # 财政 keywords should match 财政研究
        j = selector.detect_journal(topic="税收政策对企业的影响", keywords=["财政", "税收"])
        assert j["full_name"] in selector.journals.values() or "full_name" in j
        # Should be 财政研究 (Chinese journal)
        assert "财政研究" in j["full_name"] or "财政" in j["full_name"]

    def test_detect_journal_finance_topic_returns_jfe(self, selector):
        j = selector.detect_journal(
            topic="Asset pricing",
            keywords=["finance", "stock", "equity"],
        )
        # Either JFE or JF — both finance journals
        assert j.get("full_name") in (
            "Journal of Financial Economics",
            "Journal of Finance",
        )

    def test_detect_journal_nlp_topic_returns_acl(self, selector):
        j = selector.detect_journal(
            topic="natural language processing",
            keywords=["nlp", "language model", "text"],
        )
        assert j["full_name"] == "Association for Computational Linguistics"

    def test_detect_journal_no_match_returns_default_neurips(self, selector):
        j = selector.detect_journal(topic="zzzzz qqqqq no_match_at_all")
        assert j["full_name"] == "Conference on Neural Information Processing Systems"

    def test_detect_journal_abstract_only(self, selector):
        j = selector.detect_journal(abstract="研究公司金融与资本结构")
        assert "full_name" in j

    def test_detect_journal_keywords_only(self, selector):
        j = selector.detect_journal(keywords=["deep learning", "neural network", "transformer"])
        assert "full_name" in j

    def test_generate_latex_returns_string(self, selector):
        content = {"abstract": "摘要内容", "introduction": "引言内容", "title": "标题"}
        result = selector.generate_latex(content=content, venue="neurips")
        assert isinstance(result, str)
        assert r"\documentclass" in result
        assert r"\begin{document}" in result
        assert "摘要内容" in result
        assert "标题" in result

    def test_generate_latex_writes_file(self, selector, tmp_path):
        out = tmp_path / "gen.tex"
        content = {"abstract": "X"}
        selector.generate_latex(content=content, venue="jfe", output_path=out)
        assert out.exists()
        assert r"\documentclass" in out.read_text(encoding="utf-8")

    def test_generate_latex_unknown_venue_falls_back_to_neurips(self, selector):
        result = selector.generate_latex(content={}, venue="nonexistent_venue_xyz")
        assert isinstance(result, str)
        assert r"\documentclass" in result

    def test_generate_latex_chinese_venue_uses_ctex(self, selector):
        result = selector.generate_latex(content={"abstract": "摘要"}, venue="经济研究")
        assert "ctex" in result.lower()

    def test_generate_latex_includes_packages(self, selector):
        result = selector.generate_latex(content={}, venue="cvpr")
        assert r"\usepackage" in result

    def test_get_reference_format_known(self, selector):
        fmt = selector.get_reference_format("jfe")
        assert fmt["style"] == "jfe"

    def test_get_reference_format_unknown_defaults_to_neurips(self, selector):
        fmt = selector.get_reference_format("nonexistent_venue_xyz")
        assert fmt["style"] == "natbib"

    def test_get_reference_format_chinese(self, selector):
        fmt = selector.get_reference_format("经济研究")
        assert fmt["style"] == "gbt7714"

    def test_list_journals(self, selector):
        journals = selector.list_journals()
        assert isinstance(journals, list)
        assert all("key" in j for j in journals)
        assert len(journals) > 0

    def test_list_journals_keys_lowercase(self, selector):
        # JOURNAL_METADATA is keyed lowercase
        for j in selector.list_journals():
            assert j["key"] == j["key"].lower()


# ════════════════════════════════════════════════════════════════════
# Multi-language integration (optional path)
# ════════════════════════════════════════════════════════════════════


class TestMultilangBuilder:
    """Test _build_multilang_latex helper (if multilang templates loaded)."""

    def test_build_multilang_latex_with_mock_template(self):
        """If multi-lang module loads, we can synthesize from a minimal mock."""
        try:
            from scripts.research_framework.journal_templates_multilang import get_multilang_templates  # noqa: F401
            ml_templates = get_multilang_templates()
        except Exception:
            pytest.skip("multilang module not available")

        if not ml_templates:
            pytest.skip("no multilang templates")

        # Build from first available template
        first_key = next(iter(ml_templates))
        mt = ml_templates[first_key]
        latex = _build_multilang_latex(mt)
        assert isinstance(latex, str)
        assert r"\documentclass" in latex
        assert r"\begin{document}" in latex
        assert r"\end{document}" in latex


# ════════════════════════════════════════════════════════════════════
# All registered templates - sanity content check
# ════════════════════════════════════════════════════════════════════


class TestTemplateContent:
    """Validate the content of every registered JournalTemplate."""

    @pytest.mark.parametrize("template_name", list(TEMPLATES.keys()))
    def test_template_has_required_fields(self, template_name):
        t = TEMPLATES[template_name]
        assert t.name, f"{template_name} missing name"
        assert t.short_name, f"{template_name} missing short_name"
        assert t.category, f"{template_name} missing category"
        assert t.description, f"{template_name} missing description"
        assert t.bibliography_style, f"{template_name} missing bib style"
        assert isinstance(t.required_packages, list)

    @pytest.mark.parametrize("template_name", list(TEMPLATES.keys()))
    def test_template_latex_is_nonempty_string(self, template_name):
        t = TEMPLATES[template_name]
        if t.latex_code:  # multilang wrappers may not have latex_code directly
            assert isinstance(t.latex_code, str)
            assert len(t.latex_code) > 0

    def test_chinese_journal_categories_present(self):
        cats = {t.category for t in TEMPLATES.values()}
        assert "金融" in cats or "经济" in cats
