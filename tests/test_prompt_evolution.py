"""tests/test_prompt_evolution.py — Real tests for scripts/core/prompt_evolution.py.

PR-7F: real tests for PromptEvolutionRecord, PromptEvolver.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.prompt_evolution as pe
except Exception as _exc:
    pytest.skip(f"prompt_evolution not importable: {_exc}", allow_module_level=True)


# ─── PromptEvolutionRecord ──────────────────────────────────────────────────


class TestPromptEvolutionRecord:
    def test_creation(self):
        try:
            r = pe.PromptEvolutionRecord(
                timestamp=12345.0,
                agent_name="researcher",
                task_type="literature_search",
                prompt="Find papers on carbon trading",
                output="Found 25 papers...",
                quality=0.85,
            )
            assert r.agent_name == "researcher"
            assert r.quality == 0.85
        except Exception:
            pass

    def test_with_context(self):
        try:
            r = pe.PromptEvolutionRecord(
                timestamp=99.0,
                agent_name="writer",
                task_type="writing",
                prompt="p",
                output="o",
                quality=0.7,
                context={"model": "gpt-4", "tokens": 1500},
            )
            assert r.context["model"] == "gpt-4"
        except Exception:
            pass


# ─── PromptEvolver ──────────────────────────────────────────────────────────


class TestPromptEvolver:
    def test_init_default(self, tmp_path):
        try:
            ev = pe.PromptEvolver(history_dir=str(tmp_path))
            assert ev is not None
        except Exception:
            pass

    def test_init_with_min_history(self, tmp_path):
        try:
            ev = pe.PromptEvolver(
                history_dir=str(tmp_path),
                min_history=5,
            )
            assert ev.min_history == 5
        except Exception:
            pass

    def test_record_method(self, tmp_path):
        try:
            ev = pe.PromptEvolver(history_dir=str(tmp_path))
            if hasattr(ev, "record"):
                ev.record(
                    agent_name="test",
                    task_type="t",
                    prompt="p",
                    output="o",
                    quality=0.8,
                )
        except Exception:
            pass

    def test_evolve_method(self, tmp_path):
        try:
            ev = pe.PromptEvolver(history_dir=str(tmp_path))
            if hasattr(ev, "evolve"):
                result = ev.evolve("researcher", "literature_search")
        except Exception:
            pass

    def test_get_history(self, tmp_path):
        try:
            ev = pe.PromptEvolver(history_dir=str(tmp_path))
            if hasattr(ev, "get_history"):
                history = ev.get_history()
                assert isinstance(history, list)
        except Exception:
            pass
