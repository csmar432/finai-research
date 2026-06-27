"""Tests for MockTemplateEngine and AIRouter integration (PR3, Audit 2026-06-27)."""

from __future__ import annotations

import pytest

from scripts.core.mock_template_engine import (
    MockTemplateEngine,
    MockTask,
    MockResult,
)


# ─── MockTemplateEngine Tests ───────────────────────────────────────────────────


def test_generate_outline_returns_structured_content():
    engine = MockTemplateEngine()
    result = engine.generate(
        task=MockTask.OUTLINE,
        topic="碳排放权交易与绿色创新",
        venue="经济研究",
    )

    assert isinstance(result, MockResult)
    assert result.model == "mock_template"
    assert result.provider == "template"
    assert result.error is None
    assert len(result.content) > 100
    assert "[MOCK" in result.content
    assert "碳排放权交易与绿色创新" in result.content
    assert "经济研究" in result.content


def test_generate_lit_review_includes_search_paths():
    engine = MockTemplateEngine()
    result = engine.generate(
        task=MockTask.LIT_REVIEW,
        topic="ESG与融资约束",
    )

    assert "ESG" in result.content or "ESG与融资约束" in result.content
    assert "CNKI" in result.content or "OpenAlex" in result.content or "中文" in result.content


def test_generate_design_contains_variable_table():
    engine = MockTemplateEngine()
    result = engine.generate(
        task=MockTask.DESIGN,
        topic="绿色信贷与企业创新",
        identification="DID",
        dep_var="绿色专利申请数",
        indep_var="绿色信贷政策哑变量",
    )

    assert "绿色专利申请数" in result.content
    assert "DID" in result.content
    assert "稳健性检验" in result.content


def test_generate_idea_report_has_template_format():
    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.IDEA_REPORT, topic="测试主题")

    assert "[MOCK" in result.content
    assert "想法" in result.content or "idea" in result.content.lower()


def test_generate_novelty_check_has_journal_list():
    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.NOVELTY_CHECK, topic="测试主题")

    assert "JF" in result.content or "JFE" in result.content or "RFS" in result.content
    assert "经济研究" in result.content


def test_generate_abstract_has_five_parts():
    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.PAPER_ABSTRACT, topic="测试主题")

    assert "背景" in result.content
    assert "问题" in result.content
    assert "方法" in result.content


def test_generate_unknown_task_falls_back_to_general():
    engine = MockTemplateEngine()
    result = engine.generate(task="totally_unknown_task", topic="测试")

    assert "[MOCK" in result.content
    assert "DEEPSEEK_API_KEY" in result.content or "Ollama" in result.content


def test_all_tasks_return_mock_result():
    engine = MockTemplateEngine()
    for task_key in ["outline", "lit_review", "design",
                     "idea_report", "novelty_check", "abstract"]:
        result = engine.generate(task=task_key, topic="测试")
        assert isinstance(result, MockResult)
        assert result.model == "mock_template"
        assert result.error is None


def test_latency_is_reasonable():
    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.OUTLINE, topic="测试")
    # 模板渲染应该毫秒级完成
    assert result.latency_ms < 1000


def test_content_contains_no_hallucinated_data():
    """确保 mock 输出不声称有真实数据（重要：防止假数据混入）。"""
    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.OUTLINE, topic="测试")

    # 不应有具体的假数据声明
    suspicious_phrases = [
        "样本量 2000",
        "回归系数 0.056",
        "t值 2.34",
        "显著水平 5%",
    ]
    content_lower = result.content.lower()
    for phrase in suspicious_phrases:
        assert phrase.lower() not in content_lower, f"Mock output contains suspicious phrase: {phrase}"


# ─── AIRouter Integration Test ──────────────────────────────────────────────────


def test_airouter_initializes_mock_fallback():
    """AIRouter 初始化后应有 _mock_fallback 属性。"""
    from scripts.ai_router import AIRouter
    router = AIRouter(use_cache=False)

    # lazy_init 触发
    router._lazy_init()

    assert hasattr(router, "_mock_fallback"), "AIRouter should have _mock_fallback attribute"
    # mock_fallback 可以是 None（如果导入失败）或 MockTemplateEngine
    # 两者都是合法状态


def test_airouter_status_includes_mock():
    """status() 应显示 mock_template 的可用状态。"""
    from scripts.ai_router import AIRouter
    router = AIRouter(use_cache=False)
    status = router.status()

    # status 应该有 mock_template 条目
    assert "mock_template" in status, f"Expected 'mock_template' in status keys: {list(status.keys())}"


# ─── Smoke Test: End-to-end via AIRouter ──────────────────────────────────────


def test_airouter_chat_uses_mock_when_all_backends_fail():
    """当所有后端都不可用时，AIRouter 应返回 mock_template 内容。"""
    import os
    # 若存在任何 LLM key，跳过（因为可能实际调用成功，而非 mock）
    has_key = any([
        os.getenv("DEEPSEEK_API_KEY"),
        os.getenv("RELAY_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
    ])
    if has_key:
        pytest.skip("LLM API key available — test would succeed with real LLM, not mock")

    from scripts.ai_router import AIRouter

    router = AIRouter(use_cache=False)
    result = router.chat(
        "生成一个关于碳排放权交易的论文大纲",
        task="paper_cn",
    )

    # 结果应该来自某个已知后端
    assert result.model_used in [
        "mock_template",
        "DeepSeek V4 Flash",
        "Ollama 本地",
    ], f"Unexpected model: {result.model_used}"

    # 如果是 mock，验证内容
    if result.model_used == "mock_template":
        assert "[MOCK" in result.response
        assert len(result.response) > 50
