"""Tests for scripts/research_framework/journal_templates_multilang.py"""
import pytest


class TestMultiLangTemplates:
    def test_loads_all_templates(self):
        from scripts.research_framework.journal_templates_multilang import get_multilang_templates
        templates = get_multilang_templates()
        assert len(templates) == 5
        assert "JPE" in templates
        assert "RES" in templates
        assert "JoMa" in templates
        assert "ZWiSt" in templates
        assert "JNS" in templates

    def test_get_template_by_code(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JPE")
        assert t is not None
        assert t.journal_code == "JPE"
        assert t.full_name == "Journal of Political Economy"

    def test_case_insensitive(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t1 = get_template("jpe")
        t2 = get_template("JPE")
        _ = get_template("Jpe")  # noqa: F841 (side-effect only, original var= removed by ruff)
        assert t1 is not None and t2 is not None
        assert t1.journal_code == t2.journal_code

    def test_list_templates(self):
        from scripts.research_framework.journal_templates_multilang import list_multilang_templates
        templates = list_multilang_templates()
        assert len(templates) == 5
        assert all("journal_code" in t for t in templates)
        assert all("full_name" in t for t in templates)


class TestJPETemplate:
    def test_jpe_structure(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JPE")
        assert t.style.value == "japanese"
        assert t.paper_class == "article"
        assert len(t.sections) >= 8
        assert t.jEL_codes
        assert t.word_limit == 15000
        assert t.review_style == "double_blind"
        assert t.resubmission_allowed is True
        # Notes contain "double-blind review" — check substring match, not list membership
        assert any("double-blind" in n.lower() for n in t.notes)

    def test_jpe_sections_include_intro(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JPE")
        section_texts = " ".join(t.sections).lower()
        assert "introduction" in section_texts or "1." in " ".join(t.sections)

    def test_jpe_format_latex_preamble(self):
        from scripts.research_framework.journal_templates_multilang import (
            get_template, format_latex_preamble
        )
        t = get_template("JPE")
        preamble = format_latex_preamble(t)
        assert r"\documentclass" in preamble
        assert "Journal of Political Economy" in preamble
        assert r"\bibliography" in preamble


class TestRESTemplate:
    def test_res_no_resubmission(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("RES")
        assert t.resubmission_allowed is False
        assert t.review_style == "double_blind"
        assert t.page_limit == 50

    def test_res_supplementary_material(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("RES")
        assert t.supplementary_online_label == "Supplementary Material"
        section_texts = " ".join(t.sections).lower()
        assert "supplementary" in section_texts


class TestJoMaTemplate:
    def test_joma_monte_carlo(self):
        from scripts.research_framework.journal_templates_multilang import get_multilang_templates
        t = get_multilang_templates()["JoMa"]
        assert t.review_style == "single_blind"
        section_texts = " ".join(t.sections).lower()
        assert "monte carlo" in section_texts


class TestZWiStTemplate:
    def test_zwist_german_language(self):
        from scripts.research_framework.journal_templates_multilang import get_multilang_templates
        t = get_multilang_templates()["ZWiSt"]
        assert t.language == "german"
        assert t.second_language == "english"
        section_texts = " ".join(t.sections).lower()
        assert "zusammenfassung" in section_texts or "einleitung" in section_texts
        assert t.references_label == "Literatur"
        assert t.appendix_label == "Anhang"
        assert any("german" in n.lower() for n in t.notes)


class TestJNSTemplate:
    def test_jns_page_limit(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JNS")
        assert t.page_limit == 40
        assert t.review_style == "single_blind"
        assert "japan" in t.full_name.lower()


class TestTemplateHelpers:
    def test_format_word_limit_note(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JPE")
        note = t.format_word_limit_note()
        assert "15,000" in note or "word" in note.lower()

    def test_to_dict(self):
        from scripts.research_framework.journal_templates_multilang import get_template
        t = get_template("JPE")
        d = t.to_dict()
        assert d["journal_code"] == "JPE"
        assert d["style"] == "japanese"
        assert "sections" in d
        assert "word_limit" in d
        assert "citation_style" in d

    def test_jel_codes_exist(self):
        from scripts.research_framework.journal_templates_multilang import get_multilang_templates
        templates = get_multilang_templates()
        for code in ["JPE", "RES", "JoMa", "ZWiSt", "JNS"]:
            t = templates[code]
            assert isinstance(t.jEL_codes, list)


class TestIntegrationWithBase:
    def test_multilang_integrates_with_base(self):
        # Verify the multilang templates work with the base template system
        from scripts.journal_template import get_all_templates, get_template as get_base
        all_t = get_all_templates()
        assert "JPE" in all_t
        assert "RES" in all_t
        assert "JoMa" in all_t
        assert "ZWiSt" in all_t
        assert "JNS" in all_t
        # Base templates should still work
        base_jf = get_base("JF")
        assert base_jf is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
