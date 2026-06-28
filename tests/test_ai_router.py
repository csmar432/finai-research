"""AI Router 单元测试（无需真实API调用）"""
import pytest
from scripts.ai_router import Task, ModelKey, _TASK_ROUTING


class TestTaskEnum:
    def test_task_enum_values(self):
        assert Task.RESEARCH.value == "research"
        assert Task.CODE.value == "code"
        assert Task.TRANSLATION.value == "translation"

    def test_task_classification_examples(self):
        from scripts.ai_router import TaskClassifier
        classifier = TaskClassifier()

        examples = [
            # Classifier maps financial analysis to RESEARCH (broad model)
            # "生成一份光伏行业的研究报告框架" -> REPORT_CN (correct)
            ("生成一份光伏行业的研究报告框架", Task.REPORT_CN),
            ("帮我搜一下强化学习在量化交易中的文献", Task.LITERATURE),
            ("证明傅里叶变换的逆定理", Task.MATH_REASONING),
        ]

        for text, expected in examples:
            result = classifier.classify(text)
            assert result == expected, f"'{text}' should be {expected}, got {result}"


class TestModelKeyEnum:
    def test_model_key_values(self):
        assert "gpt" in ModelKey.GPT_4O.value
        assert "deepseek" in ModelKey.DEEPSEEK_FLASH.value

    def test_task_routing_has_all_tasks(self):
        for task in Task:
            assert task in _TASK_ROUTING, f"Task {task} not in _TASK_ROUTING"
            keys = _TASK_ROUTING[task]
            assert len(keys) > 0, f"Task {task} has no model keys"
            assert all(isinstance(k, ModelKey) for k in keys)

    def test_task_routing_keys_exist(self):
        for task, keys in _TASK_ROUTING.items():
            for key in keys:
                assert hasattr(ModelKey, key.name), f"ModelKey.{key.name} does not exist"
