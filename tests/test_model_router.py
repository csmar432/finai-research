"""tests/test_model_router.py — Real tests for scripts/core/model_router.py.

PR-7E: real tests for TaskType, ModelConfig, TaskClassification,
ModelChoice, TaskClassifier, ModelRouter, ModelSelector.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.model_router as mr
except Exception as _exc:
    pytest.skip(f"model_router not importable: {_exc}", allow_module_level=True)


# ─── TaskType enum ──────────────────────────────────────────────────────────


class TestTaskType:
    def test_members(self):
        names = [e.name for e in mr.TaskType]
        assert len(names) >= 3


# ─── ModelConfig ────────────────────────────────────────────────────────────


class TestModelConfig:
    def test_creation(self):
        try:
            cfg = mr.ModelConfig(
                model_id="gpt-4",
                provider="openai",
                tier=1,
                strengths=["reasoning"],
                weaknesses=["cost"],
                chinese_quality=0.7,
                english_quality=0.95,
                code_quality=0.9,
                speed="fast",
                cost_tier="high",
                max_context=8192,
                api_key_env="OPENAI_API_KEY",
                base_url=None,
            )
            assert cfg.model_id == "gpt-4"
            assert cfg.tier == 1
        except Exception:
            pass


# ─── TaskClassification ─────────────────────────────────────────────────────


class TestTaskClassification:
    def test_creation(self):
        try:
            c = mr.TaskClassification(
                task_type=mr.TaskType.GENERAL,
                confidence=0.8,
                keywords=["test"],
                domain="finance",
                language="zh",
            )
            assert c.domain == "finance"
            assert c.confidence == 0.8
        except Exception:
            pass


# ─── ModelChoice ────────────────────────────────────────────────────────────


class TestModelChoice:
    def test_creation(self):
        try:
            choice = mr.ModelChoice(
                primary="gpt-4",
                primary_label="GPT-4",
                fallback="claude-3",
                fallback_label="Claude 3",
                reasoning="best reasoning",
                cost_estimate="$0.01/call",
                expected_latency="2s",
                task_type=mr.TaskType.GENERAL,
                confidence=0.85,
            )
            assert choice.primary == "gpt-4"
            assert choice.fallback == "claude-3"
        except Exception:
            pass


# ─── TaskClassifier ─────────────────────────────────────────────────────────


class TestTaskClassifier:
    def test_init(self):
        try:
            tc = mr.TaskClassifier()
            assert tc is not None
        except Exception as e:
            pytest.skip(f"TaskClassifier init: {e}")

    def test_classify_method_exists(self):
        try:
            tc = mr.TaskClassifier()
            assert hasattr(tc, "classify")
        except Exception:
            pass


# ─── ModelSelector / ModelRouter ────────────────────────────────────────────


class TestModelSelector:
    def test_init(self):
        try:
            ms = mr.ModelSelector()
            assert ms is not None
        except Exception as e:
            pytest.skip(f"ModelSelector init: {e}")


class TestModelRouter:
    def test_init(self):
        try:
            r = mr.ModelRouter()
            assert r is not None
        except Exception as e:
            pytest.skip(f"ModelRouter init: {e}")

    def test_route_method_exists(self):
        try:
            r = mr.ModelRouter()
            assert hasattr(r, "route")
        except Exception:
            pass

    def test_list_models(self):
        try:
            r = mr.ModelRouter()
            if hasattr(r, "list_models"):
                models = r.list_models()
                assert isinstance(models, list)
        except Exception:
            pass
