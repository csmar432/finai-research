"""tests/test_design_doc.py — Real tests for scripts/research_framework/design_doc.py.

Covers:
  - First record() → version 1, changed_fields == ["initial"].
  - Second record() with changed title → version 2, "title" in changed_fields.
  - data_sources list changes correctly detected.
  - No-op record → changed_fields == [].
  - has_diverged() False when only cosmetic/no changes; True when title or method changed.
  - render_evolution_markdown() contains the table header and version rows.
  - Persistence: tmp_path → record 2 snapshots → new instance → load() → 2 history.
  - print_report runs without error.
"""
from __future__ import annotations

import io
import json
import sys
import contextlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_framework.design_doc import (
    DesignDocVersioning,
    DesignSnapshot,
    new_versioning,
    MATERIAL_FIELDS,
    TRACKED_FIELDS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def baseline_kwargs():
    """A consistent baseline design for snapshot diffing."""
    return dict(
        title="碳排放权交易对企业绿色创新的影响",
        dependent_variable="ln_green_patents",
        sample="2015-2022年A股重污染行业上市公司",
        identification_method="DID (双重差分)",
        data_sources=["tushare", "csmar"],
    )


# ─── Test: Snapshot basics ──────────────────────────────────────────────────


class TestDesignSnapshot:
    def test_as_dict_returns_all_fields(self):
        snap = DesignSnapshot(
            version=1,
            timestamp="2026-07-12T10:00:00+00:00",
            title="T",
            dependent_variable="Y",
            sample="S",
            identification_method="DID",
            data_sources=["tushare"],
            change_reason="initial",
            changed_fields=["initial"],
        )
        d = snap.as_dict()
        assert d["version"] == 1
        assert d["title"] == "T"
        assert d["data_sources"] == ["tushare"]
        assert d["changed_fields"] == ["initial"]

    def test_as_dict_copies_mutables(self):
        """as_dict must not expose internal lists for external mutation."""
        snap = DesignSnapshot(
            version=1, timestamp="t", title="t", dependent_variable="y",
            sample="s", identification_method="m", data_sources=["a"],
        )
        d = snap.as_dict()
        d["data_sources"].append("b")
        assert snap.data_sources == ["a"]


# ─── Test: record() version numbering & changed_fields ──────────────────────


class TestRecordVersioning:
    def test_first_record_is_version_one_with_initial(self, baseline_kwargs):
        v = DesignDocVersioning()
        s = v.record(change_reason="初次设定", **baseline_kwargs)
        assert s.version == 1
        assert s.changed_fields == ["initial"]
        assert "initial" in s.changed_fields

    def test_second_record_with_title_change(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "碳排放权交易对GTFP的影响"
        s = v.record(change_reason="主题调整", **updated)
        assert s.version == 2
        assert "title" in s.changed_fields
        assert "initial" not in s.changed_fields

    def test_data_sources_change_detected(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["data_sources"] = ["user-financial", "china_statistical_yearbook"]
        s = v.record(change_reason="数据源替换", **updated)
        assert s.version == 2
        assert "data_sources" in s.changed_fields

    def test_data_sources_reordering_detected(self, baseline_kwargs):
        """List equality is order-sensitive — reordering counts as a change."""
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["data_sources"] = ["csmar", "tushare"]  # reversed
        s = v.record(change_reason="调整顺序", **updated)
        assert "data_sources" in s.changed_fields

    def test_noop_record_has_empty_changed_fields(self, baseline_kwargs, capsys):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        s = v.record(change_reason="复查无变更", **baseline_kwargs)
        assert s.version == 2
        assert s.changed_fields == []
        # Should print a note
        captured = capsys.readouterr()
        assert "无字段变更" in captured.out or "no field changes" in captured.out.lower()

    def test_multiple_changes_in_one_record(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "新主题"
        updated["dependent_variable"] = "gtfp"
        updated["identification_method"] = "Spatial DID"
        s = v.record(change_reason="三处修改", **updated)
        assert "title" in s.changed_fields
        assert "dependent_variable" in s.changed_fields
        assert "identification_method" in s.changed_fields
        assert "sample" not in s.changed_fields
        assert "data_sources" not in s.changed_fields

    def test_timestamp_is_iso8601_utc(self, baseline_kwargs):
        v = DesignDocVersioning()
        s = v.record(**baseline_kwargs)
        # Must be ISO8601-like with timezone
        assert "T" in s.timestamp
        assert s.timestamp.endswith("+00:00") or s.timestamp.endswith("Z")


# ─── Test: latest / history ─────────────────────────────────────────────────


class TestQuery:
    def test_history_empty_initially(self):
        v = DesignDocVersioning()
        assert v.history() == []
        assert v.latest() is None

    def test_history_returns_copy(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        h = v.history()
        h.clear()
        # Internal list untouched
        assert len(v.history()) == 1

    def test_latest_returns_last_snapshot(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "新主题"
        s2 = v.record(**updated)
        assert v.latest() is s2
        assert v.latest().title == "新主题"


# ─── Test: has_diverged ─────────────────────────────────────────────────────


class TestHasDiverged:
    def test_empty_history_not_diverged(self):
        v = DesignDocVersioning()
        assert v.has_diverged() is False

    def test_single_version_not_diverged(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        assert v.has_diverged() is False

    def test_only_sample_change_not_diverged(self, baseline_kwargs):
        """Sample change alone is non-material → has_diverged remains False."""
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["sample"] = "2010-2023年A股全行业"
        v.record(**updated)
        assert v.has_diverged() is False

    def test_only_data_sources_change_not_diverged(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["data_sources"] = ["wind"]
        v.record(**updated)
        assert v.has_diverged() is False

    def test_title_change_diverged(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "完全不同的题目"
        v.record(**updated)
        assert v.has_diverged() is True

    def test_method_change_diverged(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["identification_method"] = "IV (2SLS)"
        v.record(**updated)
        assert v.has_diverged() is True

    def test_dependent_variable_change_diverged(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["dependent_variable"] = "roa"
        v.record(**updated)
        assert v.has_diverged() is True

    def test_noop_record_does_not_count_as_divergence(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        v.record(**baseline_kwargs)
        assert v.has_diverged() is False


# ─── Test: render_evolution_markdown ────────────────────────────────────────


class TestRenderMarkdown:
    def test_empty_history(self):
        v = DesignDocVersioning()
        md = v.render_evolution_markdown()
        assert "## 研究设计演变轨迹 (Design Evolution Trail)" in md
        assert "尚无" in md or "_" in md

    def test_single_version_says_stable(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        md = v.render_evolution_markdown()
        assert "## 研究设计演变轨迹 (Design Evolution Trail)" in md
        assert "保持稳定" in md or "无重大变更" in md
        assert baseline_kwargs["title"] in md

    def test_multiple_versions_have_table(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "新题目"
        v.record(change_reason="主题切换", **updated)
        md = v.render_evolution_markdown()
        assert "| 版本 | 时间 | 变更字段 | 变更原因 |" in md
        assert "| v1 |" in md
        assert "| v2 |" in md
        assert "title" in md
        assert "主题切换" in md
        # Latest design summary
        assert "当前设计（v2" in md
        assert "新题目" in md

    def test_markdown_escapes_pipe_in_reason(self, baseline_kwargs):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "X"
        v.record(change_reason="a|b|c", **updated)
        md = v.render_evolution_markdown()
        # The pipe in the reason must be escaped
        assert "a\\|b\\|c" in md


# ─── Test: Persistence (JSONL) ───────────────────────────────────────────────


class TestPersistence:
    def test_persist_and_reload(self, tmp_path, baseline_kwargs):
        v1 = DesignDocVersioning(project_dir=tmp_path)
        v1.record(change_reason="initial", **baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "Persistence test 2"
        v1.record(change_reason="second", **updated)

        # File must exist
        path = tmp_path / "design_history.jsonl"
        assert path.exists()
        raw = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(raw) == 2
        # Each line must be valid JSON
        for line in raw:
            json.loads(line)

        # New instance on same dir
        v2 = DesignDocVersioning(project_dir=tmp_path)
        v2.load()
        assert len(v2.history()) == 2
        assert v2.history()[0].version == 1
        assert v2.history()[1].version == 2
        assert v2.history()[1].title == "Persistence test 2"
        assert v2.history()[1].change_reason == "second"

    def test_load_missing_file_does_not_raise(self, tmp_path):
        v = DesignDocVersioning(project_dir=tmp_path)
        # File doesn't exist yet
        v.load()
        assert v.history() == []

    def test_no_project_dir_means_no_persistence(self, baseline_kwargs):
        v = DesignDocVersioning()  # no project_dir
        snap = v.record(**baseline_kwargs)
        assert v.persistence_path is None
        # Still works in-memory
        assert len(v.history()) == 1

    def test_persistence_preserves_changed_fields(self, tmp_path, baseline_kwargs):
        v1 = DesignDocVersioning(project_dir=tmp_path)
        v1.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["data_sources"] = ["wind"]
        v1.record(change_reason="swap source", **updated)

        v2 = DesignDocVersioning(project_dir=tmp_path)
        v2.load()
        assert v2.history()[0].changed_fields == ["initial"]
        assert "data_sources" in v2.history()[1].changed_fields


# ─── Test: print_report ─────────────────────────────────────────────────────


class TestPrintReport:
    def test_empty_history_runs(self, capsys):
        v = DesignDocVersioning()
        v.print_report()  # must not raise
        out = capsys.readouterr().out
        assert "尚无" in out or "═" in out

    def test_single_version_runs(self, baseline_kwargs, capsys):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        v.print_report()  # must not raise
        out = capsys.readouterr().out
        assert "v1" in out

    def test_diverged_prints_warning(self, baseline_kwargs, capsys):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        updated = baseline_kwargs.copy()
        updated["title"] = "新主题"
        v.record(**updated)
        v.print_report()
        out = capsys.readouterr().out
        # Warning message must appear when diverged
        assert "实质性变更" in out or "披露演变轨迹" in out

    def test_stable_runs_without_warning(self, baseline_kwargs, capsys):
        v = DesignDocVersioning()
        v.record(**baseline_kwargs)
        v.record(**baseline_kwargs)  # no-op
        v.print_report()
        out = capsys.readouterr().out
        # No warning text on stable case
        assert "披露演变轨迹" not in out


# ─── Test: convenience factory ───────────────────────────────────────────────


class TestConvenience:
    def test_new_versioning_returns_instance(self):
        v = new_versioning()
        assert isinstance(v, DesignDocVersioning)

    def test_new_versioning_with_project_dir(self, tmp_path):
        v = new_versioning(project_dir=tmp_path)
        assert v.persistence_path == tmp_path / "design_history.jsonl"


# ─── Test: import sanity ─────────────────────────────────────────────────────


def test_imports():
    """Smoke test for the verification command in the spec."""
    from scripts.research_framework.design_doc import (
        DesignDocVersioning,
        DesignSnapshot,
        new_versioning,
    )
    assert DesignDocVersioning is not None
    assert DesignSnapshot is not None
    assert new_versioning is not None
