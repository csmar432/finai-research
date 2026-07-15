"""Unit tests for scripts/paper_tools.py (pure helper functions)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pt():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import paper_tools as p
    yield p
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestInitLatexProjectValidation:
    def test_unknown_template_raises(self, pt):
        with pytest.raises(ValueError, match="未知模板"):
            pt.init_latex_project("my_paper", template="nonexistent")

    def test_empty_name_raises(self, pt):
        with pytest.raises(ValueError, match="不能为空"):
            pt.init_latex_project("   ")

    def test_path_traversal_raises(self, pt):
        with pytest.raises(ValueError, match="不能包含路径"):
            pt.init_latex_project("../etc/passwd")

    def test_dot_prefix_raises(self, pt):
        with pytest.raises(ValueError, match="不能包含路径"):
            pt.init_latex_project(".hidden")

    def test_slash_normalized(self, pt):
        """Slashes are sanitized to underscores, not rejected."""
        result = pt.init_latex_project("foo/bar")
        assert isinstance(result, dict)
        # Should not raise ValueError

    def test_dots_normalized(self, pt):
        """Dots are sanitized, not rejected."""
        result = pt.init_latex_project("my.paper")
        assert isinstance(result, dict)


class TestPaperTemplates:
    def test_known_templates(self, pt):
        for name in ("acl", "ieee", "ctex"):
            assert name in pt.PAPER_TEMPLATES
            assert isinstance(pt.PAPER_TEMPLATES[name], Path)

    def test_project_dir_resolved(self, pt):
        assert pt.PROJECT_DIR.is_absolute()


class TestHelperFunctions:
    def test_ngram_hash_returns_consistent(self, pt):
        h1 = pt.compute_ngram_hash("hello world")
        h2 = pt.compute_ngram_hash("hello world")
        assert h1 == h2

    def test_ngram_hash_returns_same_for_same_text(self, pt):
        h1 = pt.compute_ngram_hash("hello world")
        h2 = pt.compute_ngram_hash("hello world")
        assert h1 == h2

    def test_ngram_hash_returns_set(self, pt):
        h = pt.compute_ngram_hash("hello world")
        assert isinstance(h, (set, frozenset))

