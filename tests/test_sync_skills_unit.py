"""Unit tests for scripts/sync_skills.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ss():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import sync_skills
    yield sync_skills
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestSyncDocs:
    def test_copy_new_file(self, ss, tmp_path, monkeypatch):
        ssot = tmp_path / "ssot"
        ssot.mkdir()
        (ssot / "skill_a.md").write_text("content a")
        mirror = tmp_path / "mirror"
        monkeypatch.setattr(ss, "SSOT_DOCS", ssot)
        copied, updated, removed = ss.sync_docs(mirror)
        assert copied == 1
        assert (mirror / "skill_a.md").exists()

    def test_no_copy_when_identical(self, ss, tmp_path, monkeypatch):
        ssot = tmp_path / "ssot"
        ssot.mkdir()
        (ssot / "skill_a.md").write_text("content")
        mirror = tmp_path / "mirror"
        mirror.mkdir()
        (mirror / "skill_a.md").write_text("content")
        monkeypatch.setattr(ss, "SSOT_DOCS", ssot)
        copied, updated, removed = ss.sync_docs(mirror)
        assert copied == 0
        assert updated == 0

    def test_update_when_different(self, ss, tmp_path, monkeypatch):
        ssot = tmp_path / "ssot"
        ssot.mkdir()
        (ssot / "skill_a.md").write_text("new content")
        mirror = tmp_path / "mirror"
        mirror.mkdir()
        (mirror / "skill_a.md").write_text("old content")
        monkeypatch.setattr(ss, "SSOT_DOCS", ssot)
        copied, updated, removed = ss.sync_docs(mirror)
        assert updated == 1
        assert (mirror / "skill_a.md").read_text() == "new content"

    def test_remove_extra_files(self, ss, tmp_path, monkeypatch):
        """Files in mirror but not in SSOT are removed."""
        ssot = tmp_path / "ssot"
        ssot.mkdir()
        mirror = tmp_path / "mirror"
        mirror.mkdir()  # Must exist for `mirror.glob` to work
        (mirror / "extra.md").write_text("x")
        monkeypatch.setattr(ss, "SSOT_DOCS", ssot)
        copied, updated, removed = ss.sync_docs(mirror)
        assert removed == 1
        assert not (mirror / "extra.md").exists()

    def test_missing_ssot_returns_zeros(self, ss, tmp_path, monkeypatch):
        monkeypatch.setattr(ss, "SSOT_DOCS", tmp_path / "noexist")
        mirror = tmp_path / "mirror"
        copied, updated, removed = ss.sync_docs(mirror)
        assert (copied, updated, removed) == (0, 0, 0)


class TestSyncOps:
    def test_copy_new_skill(self, ss, tmp_path, monkeypatch):
        ssot = tmp_path / "ssot_ops"
        ssot.mkdir()
        skill_dir = ssot / "skill_a"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Skill A")
        monkeypatch.setattr(ss, "SSOT_OPS", ssot)
        mirror = tmp_path / "mirror_ops"
        copied, updated, removed = ss.sync_ops(mirror)
        assert (mirror / "skill_a" / "SKILL.md").exists()

    def test_no_skill_md_in_dir_skipped(self, ss, tmp_path, monkeypatch):
        ssot = tmp_path / "ssot_ops"
        ssot.mkdir()
        no_skill_dir = ssot / "no_skill"
        no_skill_dir.mkdir()
        (no_skill_dir / "README.md").write_text("readme")
        monkeypatch.setattr(ss, "SSOT_OPS", ssot)
        mirror = tmp_path / "mirror_ops"
        ss.sync_ops(mirror)
        # No SKILL.md → not synced
        assert not (mirror / "no_skill").exists()

    def test_missing_ssot_returns_zeros(self, ss, tmp_path, monkeypatch):
        monkeypatch.setattr(ss, "SSOT_OPS", tmp_path / "noexist")
        copied, updated, removed = ss.sync_ops(tmp_path / "mirror")
        assert (copied, updated, removed) == (0, 0, 0)

