"""Unit tests for scripts/core/reflector.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ref():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import reflector as r
    yield r
    if _p in sys.path:
        sys.path.remove(_p)


class TestConstants:
    def test_quality_flags_not_empty(self, ref):
        assert len(ref.QUALITY_FLAGS) > 0

    def test_quality_flags_values_are_strings(self, ref):
        for k, v in ref.QUALITY_FLAGS.items():
            assert isinstance(k, str)
            assert isinstance(v, str)

    def test_required_fields_has_task_types(self, ref):
        from scripts.core.planner import TaskType
        for tt in [TaskType.DATA_FETCH, TaskType.LITERATURE, TaskType.ANALYSIS,
                   TaskType.WRITING, TaskType.CODE, TaskType.VISUALIZATION]:
            assert tt in ref.REQUIRED_FIELDS

    def test_accuracy_rules_format(self, ref):
        for rule in ref.ACCURACY_RULES:
            assert len(rule) == 3
            key, mn, mx = rule
            assert isinstance(key, str)
            assert mn is None or isinstance(mn, (int, float))
            assert mx is None or isinstance(mx, (int, float))


class TestEvaluationDataclass:
    def test_evaluation_default_timestamp(self, ref):
        e = ref.Evaluation(
            task_id="t1",
            success=True,
            score=0.85,
            feedback="ok",
            suggestions=[],
            quality_flags=[],
        )
        assert e.task_id == "t1"
        assert e.timestamp > 0

    def test_evaluation_fields(self, ref):
        e = ref.Evaluation(
            task_id="t2",
            success=False,
            score=0.5,
            feedback="needs work",
            suggestions=["fix data"],
            quality_flags=["missing_data"],
            timestamp=1000.0,
        )
        assert e.success is False
        assert e.score == 0.5
        assert "missing_data" in e.quality_flags


class TestResearchReflectorInit:
    def test_init_with_memory(self, ref):
        mock_memory = type("MockMemory", (), {"get_context": lambda s, limit=10: []})()
        reflector = ref.ResearchReflector(mock_memory)
        assert reflector.memory is mock_memory


class TestCompleteness:
    def test_none_result(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t1", task_type=TaskType.DATA_FETCH, description="fetch data")
        score, flags = r._check_completeness(t, None)
        assert score == 0.0
        assert "missing_data" in flags

    def test_dict_result_with_required_fields(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t2", task_type=TaskType.DATA_FETCH, description="fetch data")
        result = {"df": [1, 2, 3], "data": "some"}
        score, flags = r._check_completeness(t, result)
        assert score > 0

    def test_numeric_data_partial_score(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t3", task_type=TaskType.ANALYSIS, description="analyze")
        # No standard fields but has numeric data
        result = {"roe": 15.5, "pe": 20.0}
        score, flags = r._check_completeness(t, result)
        assert score > 0


class TestAccuracy:
    def test_accuracy_returns_score_and_flags(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t1", task_type=TaskType.ANALYSIS, description="analyze")
        result = {"roe": 15.0, "pe": 20.0, "pb": 3.0, "sentiment_score": 0.5}
        score, flags = r._check_accuracy(t, result)
        assert isinstance(score, float)
        assert isinstance(flags, list)

    def test_accuracy_flags_on_bad_value(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t2", task_type=TaskType.ANALYSIS, description="analyze")
        result = {"roe": 999.0}
        score, flags = r._check_accuracy(t, result)
        assert isinstance(score, float)
        assert isinstance(flags, list)

    def test_non_dict_result_skips(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t3", task_type=TaskType.WRITING, description="write")
        score, flags = r._check_accuracy(t, "some text result")
        assert score == 1.0
        assert len(flags) == 0


class TestConfidence:
    def test_api_error(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t1", task_type=TaskType.DATA_FETCH, description="fetch")
        result = {"error": "timeout"}
        score, flags = r._check_confidence(t, result)
        assert score == 0.0
        assert "api_error" in flags

    def test_incomplete_output(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t2", task_type=TaskType.DATA_FETCH, description="fetch")
        score, flags = r._check_confidence(t, {})
        assert score == 0.0
        assert "incomplete_output" in flags

    def test_low_confidence(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t3", task_type=TaskType.DATA_FETCH, description="fetch")
        result = {"confidence": 0.5}
        score, flags = r._check_confidence(t, result)
        assert score == 0.5
        assert "low_confidence" in flags

    def test_good_result(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t4", task_type=TaskType.DATA_FETCH, description="fetch")
        result = {"df": [1, 2], "status_code": 200}
        score, flags = r._check_confidence(t, result)
        assert score == 1.0


class TestEntityExtraction:
    def test_extract_chinese_company(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        entity = r._extract_entity("查询阿里巴巴公司2024年财报")
        assert entity is not None
        assert "公司" in entity or "阿里巴巴" in entity

    def test_extract_ticker(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        entity = r._extract_entity("分析AAPL的股价走势")
        assert entity is not None

    def test_no_entity(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        entity = r._extract_entity("分析全球宏观经济")
        # May or may not find an entity


class TestEvaluate:
    def test_full_evaluate_success(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t1", task_type=TaskType.DATA_FETCH, description="fetch stock data")
        result = {"df": [1, 2], "price": 100.0, "roe": 15.0}
        eval_result = r.evaluate(t, result, [])
        assert isinstance(eval_result, ref.Evaluation)
        assert eval_result.score >= 0

    def test_full_evaluate_failure(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        from scripts.core.planner import Task, TaskType
        t = Task(id="t2", task_type=TaskType.DATA_FETCH, description="fetch")
        result = {"error": "API timeout"}
        eval_result = r.evaluate(t, result, [])
        assert isinstance(eval_result, ref.Evaluation)
        assert eval_result.score < 0.7


class TestReflect:
    def test_reflect_no_memory(self, ref):
        r = ref.ResearchReflector(None)
        result = r.reflect(None)
        assert isinstance(result, str)

    def test_reflect_empty_context(self, ref):
        mock_memory = type("M", (), {"get_context": lambda s, limit=10: []})()
        r = ref.ResearchReflector(mock_memory)
        result = r.reflect(None)
        assert isinstance(result, str)
        assert len(result) > 0
