"""Unit tests for scripts/cleanup_paper_index.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def cpi():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import cleanup_paper_index
    yield cleanup_paper_index
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestIsGarbageEntry:
    def test_empty_title_garbage(self, cpi):
        assert cpi.is_garbage_entry({"title": "", "id": "x"}) is True

    def test_dash_title_garbage(self, cpi):
        assert cpi.is_garbage_entry({"title": "--", "id": "x"}) is True

    def test_id_underscore_0519_garbage(self, cpi):
        assert cpi.is_garbage_entry({"title": "Some valid long title", "id": "_0519"}) is True

    def test_short_title_garbage(self, cpi):
        assert cpi.is_garbage_entry({"title": "abc", "id": "x"}) is True

    def test_long_meaningful_title(self, cpi):
        assert cpi.is_garbage_entry({
            "title": "This is a long meaningful title that should not be garbage",
            "id": "x123"
        }) is False

    def test_garbage_prefix(self, cpi):
        assert cpi.is_garbage_entry({
            "title": "作者**：some author",
            "id": "x"
        }) is True

    def test_paper_title_prefix(self, cpi):
        assert cpi.is_garbage_entry({
            "title": "1. 论文标题：**Sample",
            "id": "x"
        }) is True


class TestHasMeaningfulContent:
    def test_valid_entry_has_content(self, cpi):
        """Title > 50 chars and no garbage markers → meaningful."""
        entry = {"title": "A real paper title that is genuinely meaningful and long enough to count here", "id": "x1"}
        assert len(entry["title"]) > 50
        assert cpi.has_meaningful_content(entry) is True

    def test_garbage_entry_no_content(self, cpi):
        entry = {"title": "", "id": "x"}
        assert cpi.has_meaningful_content(entry) is False

