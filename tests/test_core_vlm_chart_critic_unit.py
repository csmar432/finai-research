"""Minimal unit tests for scripts/core/vlm_chart_critic.py.

Covers the small surface of the VLM chart critic module:
- dataclasses: FigureCritique, CritiqueSession
- provider classes: VLMProvider (Protocol), OpenAIVLMProvider, AnthropicVLMProvider
- helper: _resolve_vlm_provider
- JSON parsing helper FigureCritique.from_json_response

Heavy methods (critique_figure with subprocess + LLM refinement) are
NOT exercised.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def vlm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import vlm_chart_critic as v
    yield v
    if _p in sys.path:
        sys.path.remove(_p)


# ───────────────────────── module surface ─────────────────────────


class TestVLMModuleSurface:
    def test_imports(self, vlm):
        assert vlm is not None

    def test_all_list_matches(self, vlm):
        assert set(vlm.__all__) == {
            "VLMProvider",
            "OpenAIVLMProvider",
            "AnthropicVLMProvider",
            "_resolve_vlm_provider",
        }

    def test_classes_exist(self, vlm):
        assert dataclasses.is_dataclass(vlm.FigureCritique)
        assert dataclasses.is_dataclass(vlm.CritiqueSession)
        # VLMProvider is a Protocol-like class
        assert isinstance(vlm.VLMProvider, type)
        assert isinstance(vlm.OpenAIVLMProvider, type)
        assert isinstance(vlm.AnthropicVLMProvider, type)


# ───────────────────────── FigureCritique ─────────────────────────


class TestFigureCritique:
    def test_defaults(self, vlm):
        c = vlm.FigureCritique()
        assert c.score == 0.0
        assert c.strengths == []
        assert c.weaknesses == []
        assert c.suggestions == []
        assert c.verdict == "revise"
        assert c.raw_response == ""

    def test_init_with_fields(self, vlm):
        c = vlm.FigureCritique(
            score=8.5,
            strengths=["clear"],
            weaknesses=["small font"],
            suggestions=["use 12pt"],
            verdict="accept",
            raw_response="ok",
        )
        assert c.score == pytest.approx(8.5)
        assert c.strengths == ["clear"]
        assert c.weaknesses == ["small font"]
        assert c.suggestions == ["use 12pt"]
        assert c.verdict == "accept"

    def test_fields(self, vlm):
        names = {f.name for f in dataclasses.fields(vlm.FigureCritique)}
        assert names == {
            "score", "strengths", "weaknesses", "suggestions",
            "verdict", "raw_response",
        }


class TestFigureCritiqueFromJSON:
    def test_from_plain_json(self, vlm):
        raw = json.dumps({
            "score": 7.5,
            "strengths": ["a", "b"],
            "weaknesses": ["c"],
            "suggestions": ["d"],
            "verdict": "revise",
        })
        c = vlm.FigureCritique.from_json_response(raw)
        assert c.score == pytest.approx(7.5)
        assert c.strengths == ["a", "b"]
        assert c.weaknesses == ["c"]
        assert c.suggestions == ["d"]
        assert c.verdict == "revise"
        assert c.raw_response == raw

    def test_from_markdown_json_block(self, vlm):
        raw = (
            "Here is my critique:\n\n"
            "```json\n"
            '{"score": 9.0, "verdict": "accept", "strengths": ["s"], '
            '"weaknesses": [], "suggestions": []}\n'
            "```\n"
        )
        c = vlm.FigureCritique.from_json_response(raw)
        assert c.score == pytest.approx(9.0)
        assert c.verdict == "accept"
        assert c.strengths == ["s"]

    def test_from_invalid_json(self, vlm):
        c = vlm.FigureCritique.from_json_response("not json at all")
        assert c.verdict == "error"
        assert "not json" in c.raw_response

    def test_from_error_dict(self, vlm):
        raw = json.dumps({"error": "API_KEY missing"})
        c = vlm.FigureCritique.from_json_response(raw)
        assert c.verdict == "error"
        assert c.raw_response == raw

    def test_defaults_filled_when_keys_missing(self, vlm):
        raw = json.dumps({"score": 5.0})
        c = vlm.FigureCritique.from_json_response(raw)
        assert c.score == pytest.approx(5.0)
        assert c.strengths == []
        assert c.verdict == "revise"  # default


# ───────────────────────── CritiqueSession ─────────────────────────


class TestCritiqueSession:
    def test_init_minimal(self, vlm):
        critique = vlm.FigureCritique(score=8.0, verdict="accept")
        s = vlm.CritiqueSession(
            iteration=1,
            critique=critique,
        )
        assert s.iteration == 1
        assert s.critique is critique
        assert s.refinement_code is None
        assert s.latency_ms == 0.0
        assert s.output_path is None

    def test_init_full(self, vlm):
        critique = vlm.FigureCritique(score=6.0, verdict="revise")
        out = Path("/tmp/foo.png")
        s = vlm.CritiqueSession(
            iteration=2,
            critique=critique,
            refinement_code="plt.title('x')",
            latency_ms=150.5,
            output_path=out,
        )
        assert s.iteration == 2
        assert s.refinement_code == "plt.title('x')"
        assert s.latency_ms == pytest.approx(150.5)
        assert s.output_path is out


# ───────────────────────── VLM providers ─────────────────────────


class TestOpenAIVLMProvider:
    def test_init_default_model(self, vlm, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = vlm.OpenAIVLMProvider()
        assert p.model == "gpt-4o"
        assert p.api_key == ""

    def test_init_explicit(self, vlm, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        p = vlm.OpenAIVLMProvider(api_key="sk-explicit", model="gpt-4-vision")
        assert p.api_key == "sk-explicit"
        assert p.model == "gpt-4-vision"

    def test_analyze_no_key_returns_error(self, vlm, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = vlm.OpenAIVLMProvider()
        out = p.analyze_figure(b"\x89PNG fake", "critique this")
        data = json.loads(out)
        assert "error" in data
        assert "OPENAI_API_KEY" in data["error"]


class TestAnthropicVLMProvider:
    def test_init_default_model(self, vlm, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = vlm.AnthropicVLMProvider()
        assert "claude" in p.model
        assert p.api_key == ""

    def test_init_explicit(self, vlm, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test-456")
        p = vlm.AnthropicVLMProvider(
            api_key="ant-explicit",
            model="claude-3-opus-20240229",
        )
        assert p.api_key == "ant-explicit"
        assert p.model == "claude-3-opus-20240229"

    def test_analyze_no_key_returns_error(self, vlm, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = vlm.AnthropicVLMProvider()
        out = p.analyze_figure(b"\x89PNG fake", "critique this")
        data = json.loads(out)
        assert "error" in data
        assert "ANTHROPIC_API_KEY" in data["error"]


class TestResolveVLMProvider:
    def test_resolve_openai_string(self, vlm, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = vlm._resolve_vlm_provider("openai")
        assert isinstance(p, vlm.OpenAIVLMProvider)
        assert p.api_key == ""

    def test_resolve_anthropic_string(self, vlm, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = vlm._resolve_vlm_provider("anthropic")
        assert isinstance(p, vlm.AnthropicVLMProvider)

    def test_resolve_passthrough_instance(self, vlm):
        original = vlm.OpenAIVLMProvider(api_key="k", model="m")
        resolved = vlm._resolve_vlm_provider(original)
        assert resolved is original

    def test_resolve_unknown_raises(self, vlm):
        with pytest.raises(ValueError):
            vlm._resolve_vlm_provider("nonsense-provider")

    def test_resolve_case_insensitive(self, vlm, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = vlm._resolve_vlm_provider("OpenAI")
        assert isinstance(p, vlm.OpenAIVLMProvider)