"""AdversarialQA strict mode config flag 测试。

P1 修复 2026-06-28:
- 默认 loose（向后兼容）
- 设置 ADVERSARIAL_QA_STRICT=1 启用 strict mode（>=5 问题 + >=3 hard）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def reset_env():
    if "ADVERSARIAL_QA_STRICT" in os.environ:
        del os.environ["ADVERSARIAL_QA_STRICT"]
    yield
    if "ADVERSARIAL_QA_STRICT" in os.environ:
        del os.environ["ADVERSARIAL_QA_STRICT"]


def test_loose_mode_passes_with_1_question():
    """loose 模式: 任何问题都通过（向后兼容）"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    qs = [{"dimension": "x", "question": "q", "difficulty": "easy"}]
    assert _evaluate_qa_pass(qs, strict_mode=False) is True


def test_loose_mode_fails_with_0_questions():
    """loose 模式: 0 问题失败"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    assert _evaluate_qa_pass([], strict_mode=False) is False


def test_strict_mode_passes_with_5_hard():
    """strict 模式: 5 个 hard 问题通过"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    qs = [{"dimension": f"x{i}", "question": "q", "difficulty": "hard"} for i in range(5)]
    assert _evaluate_qa_pass(qs, strict_mode=True) is True


def test_strict_mode_fails_with_5_easy():
    """strict 模式: 5 个 easy 问题不通过（hard 不足）"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    qs = [{"dimension": f"x{i}", "question": "q", "difficulty": "easy"} for i in range(5)]
    assert _evaluate_qa_pass(qs, strict_mode=True) is False


def test_strict_mode_fails_with_3_questions():
    """strict 模式: < 5 问题不通过"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    qs = [{"dimension": "x", "question": "q", "difficulty": "hard"}] * 3
    assert _evaluate_qa_pass(qs, strict_mode=True) is False


def test_strict_mode_passes_with_5_mixed_3_hard():
    """strict 模式: 5 个混合问题有 3 个 hard 通过"""
    from scripts.core.specialized_agents import _evaluate_qa_pass

    qs = [
        {"dimension": "x", "question": "q", "difficulty": "hard"},
        {"dimension": "x", "question": "q", "difficulty": "hard"},
        {"dimension": "x", "question": "q", "difficulty": "hard"},
        {"dimension": "x", "question": "q", "difficulty": "easy"},
        {"dimension": "x", "question": "q", "difficulty": "medium"},
    ]
    assert _evaluate_qa_pass(qs, strict_mode=True) is True


def test_agent_default_loose():
    """默认 (env unset) → loose 模式"""
    from scripts.core.specialized_agents import AdversarialQAAgent

    agent = AdversarialQAAgent()
    assert agent.strict_mode is False


def test_agent_strict_via_env():
    """ADVERSARIAL_QA_STRICT=1 → strict 模式"""
    from scripts.core.specialized_agents import AdversarialQAAgent

    os.environ["ADVERSARIAL_QA_STRICT"] = "1"
    agent = AdversarialQAAgent()
    assert agent.strict_mode is True


def test_agent_strict_via_env_true():
    """ADVERSARIAL_QA_STRICT=true → strict 模式"""
    from scripts.core.specialized_agents import AdversarialQAAgent

    os.environ["ADVERSARIAL_QA_STRICT"] = "true"
    agent = AdversarialQAAgent()
    assert agent.strict_mode is True


def test_agent_strict_via_constructor():
    """显式传 strict_mode=True 覆盖 env"""
    from scripts.core.specialized_agents import AdversarialQAAgent

    os.environ["ADVERSARIAL_QA_STRICT"] = "0"
    agent = AdversarialQAAgent(strict_mode=True)
    assert agent.strict_mode is True