"""Unit tests for scripts/core/model_router.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def mr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import model_router as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, mr):
        for name in [
            "TaskType",
            "ModelChoice",
            "TaskClassification",
            "ModelConfig",
            "TaskClassifier",
            "ModelSelector",
            "ModelRouter",
        ]:
            assert hasattr(mr, name), f"Missing export: {name}"


class TestTaskType:
    def test_enum_members_count(self, mr):
        members = list(mr.TaskType)
        assert len(members) >= 20

    def test_key_values(self, mr):
        assert mr.TaskType.LITERATURE_SEARCH.value == "literature_search"
        assert mr.TaskType.DRAFT_WRITING_CN.value == "draft_writing_cn"
        assert mr.TaskType.GENERAL.value == "general"

    def test_string_enum(self, mr):
        # str-based enum supports str comparison
        assert mr.TaskType.LITERATURE_SEARCH == "literature_search"
        assert isinstance(mr.TaskType.GENERAL, str)


class TestModelChoiceDataclass:
    def test_minimal_init(self, mr):
        choice = mr.ModelChoice(
            primary="deepseek_pro",
            primary_label="deepseek/deepseek_pro",
            fallback="claude_sonnet",
            fallback_label="anthropic/claude_sonnet",
            reasoning="test reasoning",
            cost_estimate="~$0.5/M",
            expected_latency="15-60s",
            task_type=mr.TaskType.GENERAL,
            confidence=0.7,
        )
        assert choice.primary == "deepseek_pro"
        assert choice.confidence == 0.7
        assert choice.task_type == mr.TaskType.GENERAL


class TestTaskClassificationDataclass:
    def test_init(self, mr):
        tc = mr.TaskClassification(
            task_type=mr.TaskType.LITERATURE_SEARCH,
            confidence=0.8,
            keywords=["搜索", "文献"],
            domain="academic_paper",
            language="cn",
        )
        assert tc.task_type == mr.TaskType.LITERATURE_SEARCH
        assert tc.confidence == 0.8
        assert tc.keywords == ["搜索", "文献"]
        assert tc.domain == "academic_paper"
        assert tc.language == "cn"

    def test_defaults(self, mr):
        tc = mr.TaskClassification(
            task_type=mr.TaskType.GENERAL,
            confidence=0.0, keywords=[], domain="", language="",
        )
        assert tc.confidence == 0.0
        assert tc.keywords == []
        assert tc.domain == ""
        assert tc.language == ""


class TestModelConfigDataclass:
    def test_init(self, mr):
        cfg = mr.ModelConfig(
            model_id="test_model",
            provider="test_provider",
            tier=2,
            strengths=["writing"],
            weaknesses=["reasoning"],
            chinese_quality=4.0,
            english_quality=4.5,
            code_quality=4.0,
            speed="medium",
            cost_tier="medium",
            max_context=128000,
            api_key_env="TEST_API_KEY",
            base_url="https://api.example.com",
        )
        assert cfg.model_id == "test_model"
        assert cfg.tier == 2
        assert cfg.max_context == 128000

    def test_is_available_false(self, mr, monkeypatch):
        cfg = mr.ModelConfig(
            model_id="m",
            provider="p",
            tier=1,
            strengths=[],
            weaknesses=[],
            chinese_quality=3.0,
            english_quality=3.0,
            code_quality=3.0,
            speed="fast",
            cost_tier="low",
            max_context=1000,
            api_key_env="UNSET_TEST_KEY_XYZ",
            base_url=None,
        )
        monkeypatch.delenv("UNSET_TEST_KEY_XYZ", raising=False)
        assert cfg.is_available() is False

    def test_is_available_true(self, mr, monkeypatch):
        cfg = mr.ModelConfig(
            model_id="m",
            provider="p",
            tier=1,
            strengths=[],
            weaknesses=[],
            chinese_quality=3.0,
            english_quality=3.0,
            code_quality=3.0,
            speed="fast",
            cost_tier="low",
            max_context=1000,
            api_key_env="TEST_KEY_SET_FOR_AVAIL",
            base_url=None,
        )
        monkeypatch.setenv("TEST_KEY_SET_FOR_AVAIL", "some_value")
        assert cfg.is_available() is True


class TestMODELSRegistry:
    def test_models_dict_present(self, mr):
        assert isinstance(mr.MODELS, dict)
        assert len(mr.MODELS) >= 5

    def test_models_known_keys(self, mr):
        for key in ["deepseek_flash", "deepseek_pro", "claude_sonnet", "claude_opus"]:
            assert key in mr.MODELS, f"Missing model: {key}"


class TestTaskClassifier:
    def test_classify_general(self, mr):
        clf = mr.TaskClassifier()
        result = clf.classify("随便聊聊")
        assert result.task_type == mr.TaskType.GENERAL

    def test_classify_literature(self, mr):
        clf = mr.TaskClassifier()
        result = clf.classify("请帮我搜索一些文献")
        assert result.task_type == mr.TaskType.LITERATURE_SEARCH
        assert result.confidence > 0

    def test_classify_chinese_language(self, mr):
        clf = mr.TaskClassifier()
        result = clf.classify("帮我综述一下中国数字金融")
        assert result.language in {"cn", "mixed", "en"}

    def test_classify_returns_classification(self, mr):
        clf = mr.TaskClassifier()
        result = clf.classify("测试文本")
        assert isinstance(result, mr.TaskClassification)


class TestModelSelector:
    def test_selector_init(self, mr):
        sel = mr.ModelSelector()
        assert sel is not None

    def test_select_general(self, mr):
        sel = mr.ModelSelector()
        cls = mr.TaskClassification(
            task_type=mr.TaskType.GENERAL, confidence=1.0, keywords=[], domain="general", language="mixed"
        )
        choice = sel.select(cls)
        assert isinstance(choice, mr.ModelChoice)
        assert choice.task_type == mr.TaskType.GENERAL
        assert choice.primary != ""

    def test_select_each_task_type(self, mr):
        sel = mr.ModelSelector()
        for tt in mr.TaskType:
            cls = mr.TaskClassification(
                task_type=tt, confidence=1.0, keywords=[], domain="general", language="mixed"
            )
            choice = sel.select(cls)
            assert choice.primary != ""
            assert choice.fallback != ""


class TestModelRouter:
    def test_init(self, mr):
        router = mr.ModelRouter()
        assert router is not None
        assert router.classifier is not None
        assert router.selector is not None

    def test_route(self, mr):
        router = mr.ModelRouter()
        choice = router.route("帮我搜索一些文献")
        assert isinstance(choice, mr.ModelChoice)
        assert choice.primary != ""

    def test_route_by_task(self, mr):
        router = mr.ModelRouter()
        choice = router.route_by_task(mr.TaskType.DRAFT_WRITING_CN)
        assert choice.task_type == mr.TaskType.DRAFT_WRITING_CN

    def test_batch_route(self, mr):
        router = mr.ModelRouter()
        choices = router.batch_route(["搜索文献", "写综述", "DID设计"])
        assert len(choices) == 3
        for c in choices:
            assert isinstance(c, mr.ModelChoice)

    def test_get_available_models(self, mr):
        router = mr.ModelRouter()
        available = router.get_available_models()
        assert isinstance(available, dict)
        assert len(available) >= 5

    def test_generate_prompt_with_context(self, mr):
        router = mr.ModelRouter()
        prompt, choice = router.generate_prompt_with_context("写一个中文论文")
        assert isinstance(prompt, str)
        assert isinstance(choice, mr.ModelChoice)
        assert "系统指令" in prompt or "路由上下文" in prompt

    def test_generate_prompt_without_routing(self, mr):
        router = mr.ModelRouter()
        prompt, choice = router.generate_prompt_with_context("你好", include_routing=False)
        assert prompt == "你好"
        assert isinstance(choice, mr.ModelChoice)
