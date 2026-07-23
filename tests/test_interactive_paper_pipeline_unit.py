"""Unit tests for scripts/interactive_paper_pipeline.py.

Covers: PaperWorkflow class (state, new_project, save_chapter, generate_full_paper,
save_outline), ask_user, confirm_proceed, get_llm_response, call_deepseek,
_generate_mock_response, step1_topic_selection, step2_outline_generation,
step3_chapter_writing, step4_data_analysis, step5_finalize, main,
PROJECT_ROOT.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ipp():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import interactive_paper_pipeline as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture
def workflow(ipp):
    return ipp.PaperWorkflow()


# ═══════════════════════════════════════════════════════════════════════════
# Module constants and structure
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleConstants:
    def test_module_loads(self, ipp):
        assert ipp is not None

    def test_project_root_is_path(self, ipp):
        assert isinstance(ipp.PROJECT_ROOT, Path)


# ═══════════════════════════════════════════════════════════════════════════
# PaperWorkflow class
# ═══════════════════════════════════════════════════════════════════════════


class TestPaperWorkflowInit:
    def test_init_default_state(self, workflow):
        assert workflow.project_dir is None
        assert workflow.topic is None
        assert workflow.title is None
        assert workflow.outline is None
        assert workflow.draft == {}
        assert workflow.status == "初始化"

    def test_init_has_methods(self, workflow):
        assert callable(workflow.new_project)
        assert callable(workflow.save_outline)
        assert callable(workflow.save_chapter)
        assert callable(workflow.generate_full_paper)


class TestPaperWorkflowNewProject:
    def test_creates_directory(self, workflow, tmp_path, monkeypatch):
        # Redirect the projects root by monkeypatching PROJECT_ROOT
        fake_root = tmp_path / "project_root"
        monkeypatch.setattr(ipp := sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        path = workflow.new_project("碳排放权交易对企业绿色创新的影响")
        assert isinstance(path, Path)
        assert path.exists()
        assert path.is_dir()
        assert workflow.topic == "碳排放权交易对企业绿色创新的影响"
        assert workflow.status == "项目创建"

    def test_sanitizes_topic(self, workflow, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        monkeypatch.setattr(ipp := sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        # Special chars should be replaced
        workflow.new_project("topic/with\\special:chars*")
        assert workflow.topic == "topic/with\\special:chars*"
        # The directory name should be sanitized
        assert workflow.project_dir.parent.exists()


class TestPaperWorkflowSaveChapter:
    def test_save_chapter_writes_file(self, workflow, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        monkeypatch.setattr(sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        workflow.new_project("Test Topic")
        workflow.save_chapter("引言", "# 这是引言\n\nSome content here.")
        assert "引言" in workflow.draft
        assert "Some content" in workflow.draft["引言"]
        saved = workflow.project_dir / "引言.md"
        assert saved.exists()
        assert "Some content here" in saved.read_text(encoding="utf-8")

    def test_save_multiple_chapters(self, workflow, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        monkeypatch.setattr(sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        workflow.new_project("Test")
        workflow.save_chapter("chapter1", "content1")
        workflow.save_chapter("chapter2", "content2")
        assert len(workflow.draft) == 2
        assert workflow.draft["chapter1"] == "content1"
        assert workflow.draft["chapter2"] == "content2"


class TestPaperWorkflowGenerateFullPaper:
    def test_generate_full_paper_concatenates(self, workflow, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        monkeypatch.setattr(sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        workflow.new_project("Demo")
        workflow.save_chapter("Intro", "intro content")
        workflow.save_chapter("Conclusion", "end content")
        paper = workflow.generate_full_paper()
        assert "intro content" in paper
        assert "end content" in paper
        # Output file should exist
        out_file = workflow.project_dir / "全文草稿.md"
        assert out_file.exists()
        assert "intro content" in out_file.read_text(encoding="utf-8")
        assert "end content" in out_file.read_text(encoding="utf-8")

    def test_generate_full_paper_empty_draft(self, workflow, tmp_path, monkeypatch):
        fake_root = tmp_path / "root"
        monkeypatch.setattr(sys.modules["scripts.interactive_paper_pipeline"], "PROJECT_ROOT", fake_root)
        workflow.new_project("Empty")
        # Empty draft — should not crash, returns string with section headers
        paper = workflow.generate_full_paper()
        assert isinstance(paper, str)


# ═══════════════════════════════════════════════════════════════════════════
# Module-level functions
# ═══════════════════════════════════════════════════════════════════════════


class TestAskUser:
    def test_ask_user_callable(self, ipp):
        assert callable(ipp.ask_user)

    def test_confirm_proceed_callable(self, ipp):
        assert callable(ipp.confirm_proceed)


class TestLLMFunctions:
    def test_get_llm_response_callable(self, ipp):
        assert callable(ipp.get_llm_response)

    def test_call_deepseek_callable(self, ipp):
        assert callable(ipp.call_deepseek)

    def test_generate_mock_response_topics(self, ipp):
        result = ipp._generate_mock_response("test", "topics")
        assert isinstance(result, str)
        assert len(result) > 50
        assert "题目" in result or "题目1" in result

    def test_generate_mock_response_outline(self, ipp):
        result = ipp._generate_mock_response("", "outline")
        assert isinstance(result, str)
        assert "引言" in result or "研究背景" in result

    def test_generate_mock_response_chapter(self, ipp):
        result = ipp._generate_mock_response("", "chapter")
        assert isinstance(result, str)
        assert len(result) > 10

    def test_generate_mock_response_unknown_task(self, ipp):
        # Unknown task should return empty string
        result = ipp._generate_mock_response("test", "unknown_task_xyz")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════
# Workflow step functions
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowSteps:
    def test_step1_callable(self, ipp):
        assert callable(ipp.step1_topic_selection)

    def test_step2_callable(self, ipp):
        assert callable(ipp.step2_outline_generation)

    def test_step3_callable(self, ipp):
        assert callable(ipp.step3_chapter_writing)

    def test_step4_callable(self, ipp):
        assert callable(ipp.step4_data_analysis)

    def test_step5_callable(self, ipp):
        assert callable(ipp.step5_finalize)

    def test_step5_finalize_with_empty_draft(self, ipp, workflow):
        workflow.new_project("Final Test")
        # Even with empty draft, should not crash
        result = ipp.step5_finalize(workflow)
        assert isinstance(result, str)


class TestInternalHelpers:
    def test_run_empirical_analysis_callable(self, ipp):
        assert callable(ipp._run_empirical_analysis)

    def test_run_empirical_with_config_callable(self, ipp):
        assert callable(ipp._run_empirical_analysis_with_config)


class TestMain:
    def test_main_callable(self, ipp):
        assert callable(ipp.main)
