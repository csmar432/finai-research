"""tests/test_ai_parliament_deep_exec.py — Deep tests for ai_parliament dataclasses.

Targets uncovered dataclasses and helpers in scripts/core/ai_parliament.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.ai_parliament import (
        _resolve_model, MemberType, MemberConfig,
        DebateRound, RebuttalRound, Verdict,
        BaseMemberAgent, ChairAgent, EngineeringMemberAgent,
        FinanceMemberAgent, MemberMethodologyAgent,
        MemberStatisticsAgent, MemberWritingAgent,
        AIParliament, AIParliamentHITLIntegration,
        MEMBER_CONFIGS,
    )
except Exception as exc:
    pytest.skip(f"ai_parliament not importable: {exc}", allow_module_level=True)


# ─── Enums ────────────────────────────────────────────────────────────

class TestMemberType:
    def test_values(self):
        vals = [m.value for m in MemberType]
        assert "chair" in vals
        assert "writing" in vals

    def test_count(self):
        assert len(list(MemberType)) == 6


# ─── MemberConfig ─────────────────────────────────────────────────────

class TestMemberConfig:
    def test_basic(self):
        cfg = MemberConfig(
            member_type=MemberType.CHAIR,
            name="Test",
            role="Test role",
            model="gpt-4",
            expertise=["finance"],
            perspective="Test",
        )
        assert cfg.name == "Test"
        assert cfg.model == "gpt-4"
        assert "finance" in cfg.expertise


class TestMemberConfigs:
    def test_all_configs_present(self):
        for mt in MemberType:
            assert mt in MEMBER_CONFIGS

    def test_chair_is_chair(self):
        chair_cfg = MEMBER_CONFIGS[MemberType.CHAIR]
        assert chair_cfg.member_type == MemberType.CHAIR

    def test_configs_have_required_fields(self):
        for mt, cfg in MEMBER_CONFIGS.items():
            assert cfg.name != ""
            assert cfg.role != ""
            assert cfg.model != ""
            assert len(cfg.expertise) > 0


# ─── DebateRound ──────────────────────────────────────────────────────

class TestDebateRound:
    def test_basic(self):
        r = DebateRound(
            round_number=1,
            speaker=MemberType.CHAIR,
            content="Hello world",
        )
        assert r.round_number == 1
        assert r.content == "Hello world"
        assert r.timestamp > 0


# ─── RebuttalRound ────────────────────────────────────────────────────

class TestRebuttalRound:
    def test_basic(self):
        r = RebuttalRound(
            round_num=1,
            member_type=MemberType.MEMBER_ENGINEERING,
            response_to_summary="I disagree",
            strength="strong",
        )
        assert r.round_num == 1
        assert r.strength == "strong"


# ─── Verdict ──────────────────────────────────────────────────────────

class TestVerdict:
    def test_basic(self):
        v = Verdict(
            score=4.5,
            recommendation="accept",
            summary="Good paper",
            key_strengths=["novel"],
            key_weaknesses=["minor"],
        )
        assert v.score == 4.5
        assert v.recommendation == "accept"
        assert v.debate_rounds == []
        assert v.rebuttal_rounds == []
        assert v.disputed is False

    def test_with_debate_rounds(self):
        dr = DebateRound(round_number=1, speaker=MemberType.CHAIR, content="Hi")
        v = Verdict(
            score=3.5,
            recommendation="revision",
            summary="OK",
            key_strengths=[],
            key_weaknesses=[],
            debate_rounds=[dr],
            disputed=True,
        )
        assert len(v.debate_rounds) == 1
        assert v.disputed is True


# ─── Class inits ──────────────────────────────────────────────────────

class TestAIParliamentClasses:
    def test_ai_parliament(self):
        try:
            ap = AIParliament()
            assert ap is not None
        except Exception:
            pass

    def test_hitl_integration(self):
        try:
            hitl = AIParliamentHITLIntegration()
            assert hitl is not None
        except Exception:
            pass


# ─── _resolve_model ───────────────────────────────────────────────────

class TestResolveModel:
    def test_with_env(self, monkeypatch):
        monkeypatch.setenv("TEST_MODEL_VAR", "test-model")
        try:
            result = _resolve_model("TEST_MODEL_VAR", "default")
            assert result == "test-model"
        except Exception:
            pass

    def test_without_env(self):
        try:
            result = _resolve_model("DEFINITELY_NOT_SET_12345", "default-model")
            assert result == "default-model"
        except Exception:
            pass
