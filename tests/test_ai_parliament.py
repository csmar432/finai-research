"""Tests for scripts/core/ai_parliament.py"""
import pytest
from unittest.mock import MagicMock, patch
from scripts.core.ai_parliament import (
    MemberType, DebateRound, RebuttalRound, Verdict, AIParliament, AIParliamentHITLIntegration,
)


def _make_mock_gateway():
    """Create a mock LLM gateway that works without patching the module."""
    mock_gw = MagicMock()
    mock_gw.generate.return_value = MagicMock(response="Mock response")
    return mock_gw


class TestMemberType:
    def test_all_6_member_types_defined(self):
        assert MemberType.CHAIR.value == "chair"
        assert MemberType.MEMBER_ENGINEERING.value == "member_engineering"
        assert MemberType.MEMBER_FINANCE.value == "member_finance"
        assert MemberType.MEMBER_METHODOLOGY.value == "methodology"
        assert MemberType.MEMBER_STATISTICS.value == "statistics"
        assert MemberType.MEMBER_WRITING.value == "writing"
        assert len(MemberType) == 6


class TestDebateRound:
    def test_debate_round_creation(self):
        dr = DebateRound(round_number=1, speaker=MemberType.CHAIR, content="Test opening")
        assert dr.round_number == 1
        assert dr.speaker == MemberType.CHAIR
        assert dr.content == "Test opening"

    def test_debate_round_with_timestamp(self):
        dr = DebateRound(round_number=0, speaker=MemberType.MEMBER_ENGINEERING, content="Engineering response")
        assert dr.timestamp > 0


class TestRebuttalRound:
    def test_rebuttal_round_creation(self):
        rr = RebuttalRound(
            round_num=-1,
            member_type=MemberType.MEMBER_FINANCE,
            response_to_summary="Finance rebuttal",
            strength="strong",
        )
        assert rr.round_num == -1
        assert rr.member_type == MemberType.MEMBER_FINANCE
        assert rr.strength == "strong"


class TestVerdict:
    def test_verdict_creation(self):
        v = Verdict(
            score=4.0,
            recommendation="accept",
            summary="Strong paper",
            key_strengths=["novel method"],
            key_weaknesses=["sample size"],
        )
        assert v.score == 4.0
        assert v.recommendation == "accept"

    def test_verdict_disputed_property(self):
        v = Verdict(
            score=3.0,
            recommendation="revision",
            summary="Mixed views",
            key_strengths=[],
            key_weaknesses=[],
            disputed=False,
        )
        assert v.disputed is False

    def test_verdict_with_debate_rounds(self):
        dr = DebateRound(round_number=1, speaker=MemberType.MEMBER_ENGINEERING, content="Arg1")
        rr = RebuttalRound(round_num=-1, member_type=MemberType.MEMBER_FINANCE,
                           response_to_summary="Rebuttal", strength="moderate")
        v = Verdict(
            score=3.5,
            recommendation="revision",
            summary="Test",
            key_strengths=[],
            key_weaknesses=[],
            debate_rounds=[dr],
            rebuttal_rounds=[rr],
        )
        assert len(v.debate_rounds) == 1
        assert len(v.rebuttal_rounds) == 1

    def test_verdict_all_arguments_field(self):
        v = Verdict(
            score=3.0,
            recommendation="revision",
            summary="Test",
            key_strengths=[],
            key_weaknesses=[],
            all_arguments=["arg1", "arg2"],
        )
        assert len(v.all_arguments) == 2


class TestAIParliamentInit:
    def test_parliament_initializes_6_members(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        assert MemberType.CHAIR in parliament.members
        assert MemberType.MEMBER_ENGINEERING in parliament.members
        assert MemberType.MEMBER_FINANCE in parliament.members
        assert MemberType.MEMBER_METHODOLOGY in parliament.members
        assert MemberType.MEMBER_STATISTICS in parliament.members
        assert MemberType.MEMBER_WRITING in parliament.members
        assert len(parliament.members) == 6

    def test_max_rounds_from_env(self):
        with patch.dict("os.environ", {"PARLIAMENT_MAX_ROUNDS": "5"}):
            parliament = AIParliament(gateway=_make_mock_gateway())
            assert parliament.max_rounds == 5

    def test_max_rounds_default(self):
        with patch.dict("os.environ", {}, clear=True):
            parliament = AIParliament(gateway=_make_mock_gateway())
            assert parliament.max_rounds == 3

    def test_gateway_assignment(self):
        mock_gw = _make_mock_gateway()
        parliament = AIParliament(gateway=mock_gw)
        assert parliament.gateway is mock_gw


class TestVerdictFormatting:
    def test_format_verdict_accept(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        v = Verdict(
            score=4.5,
            recommendation="accept",
            summary="Excellent paper",
            key_strengths=["Strong methodology", "Novel contribution"],
            key_weaknesses=[],
        )
        formatted = parliament.format_verdict(v)
        assert "accept" in formatted.lower()
        assert "4.5" in formatted

    def test_format_verdict_disputed(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        v = Verdict(
            score=3.0,
            recommendation="revision",
            summary="Mixed reviews",
            key_strengths=[],
            key_weaknesses=["Sample concerns"],
            disputed=True,
        )
        formatted = parliament.format_verdict(v)
        # disputed flag should appear
        assert "争议" in formatted or "disputed" in formatted.lower() or "⚠️" in formatted

    def test_format_verdict_reject(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        v = Verdict(
            score=1.5,
            recommendation="reject",
            summary="Significant flaws",
            key_strengths=[],
            key_weaknesses=["Methodology errors", "Data issues"],
        )
        formatted = parliament.format_verdict(v)
        assert "reject" in formatted.lower()


class TestAIParliamentHITL:
    def test_hitl_integration_initializes(self):
        hitl = AIParliamentHITLIntegration()
        assert hitl.parliament is not None
        assert hasattr(hitl, "_decision_history")
        assert isinstance(hitl._decision_history, list)

    def test_hitl_integration_with_custom_parliament(self):
        custom_parliament = MagicMock()
        hitl = AIParliamentHITLIntegration(parliament=custom_parliament)
        assert hitl.parliament is custom_parliament

    def test_get_decision_stats_empty(self):
        hitl = AIParliamentHITLIntegration()
        stats = hitl.get_decision_stats()
        assert "total_decisions" in stats
        assert stats["total_decisions"] == 0

    def test_calculate_confidence_high(self):
        hitl = AIParliamentHITLIntegration()
        verdict_mock = MagicMock()
        verdict_mock.recommendation = "accept"
        verdict_mock.debate_rounds = [
            DebateRound(round_number=1, speaker=MemberType.MEMBER_ENGINEERING, content="Good"),
            DebateRound(round_number=1, speaker=MemberType.MEMBER_FINANCE, content="Good"),
            DebateRound(round_number=2, speaker=MemberType.MEMBER_ENGINEERING, content="Good"),
        ]
        verdict_mock.disputed = False

        confidence = hitl._calculate_confidence(verdict_mock)
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0

    def test_calculate_confidence_disputed_penalty(self):
        hitl = AIParliamentHITLIntegration()
        verdict_mock = MagicMock()
        verdict_mock.recommendation = "revision"
        verdict_mock.debate_rounds = []
        verdict_mock.disputed = True

        confidence = hitl._calculate_confidence(verdict_mock)
        # disputed should apply a penalty
        assert confidence < 0.7

    def test_create_hitl_approval_creates_dict(self):
        hitl = AIParliamentHITLIntegration()
        hitl.hitl_gate = MagicMock()
        hitl.hitl_gate.hold.return_value = "gate_001"

        verdict = {
            "score": 4.0,
            "recommendation": "accept",
            "summary": "Good paper",
            "key_strengths": ["Methodology"],
            "key_weaknesses": [],
            "confidence": 0.85,
        }

        gate_id = hitl.create_hitl_approval(verdict, stage="review")
        assert gate_id == "gate_001"
        hitl.hitl_gate.hold.assert_called_once()


class TestMemberConfigs:
    def test_member_configs_defined(self):
        from scripts.core.ai_parliament import MEMBER_CONFIGS
        assert len(MEMBER_CONFIGS) == 6
        for mtype in MemberType:
            assert mtype in MEMBER_CONFIGS
            cfg = MEMBER_CONFIGS[mtype]
            assert cfg.member_type == mtype
            assert cfg.name
            assert cfg.role
            assert cfg.model


class TestAIParliamentDebateAsync:
    @pytest.mark.asyncio
    async def test_debate_returns_verdict(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        paper = {"title": "Test Paper", "abstract": "A test abstract."}

        # Mock all member responses to avoid actual LLM calls
        async def mock_opening(p):
            return "Opening statement"

        async def mock_respond(ctx):
            return "Member response"

        async def mock_final(ctx):
            return {"score": 4.0, "recommendation": "accept", "summary": "Good",
                    "key_strengths": [], "key_weaknesses": [], "_error": False}

        for member_type, member in parliament.members.items():
            member.opening_statement = mock_opening
            member.respond = mock_respond
            member.final_statement = mock_final

        verdict = await parliament.debate(paper, rounds=1)

        assert isinstance(verdict, Verdict)
        assert verdict.score == 4.0
        assert verdict.recommendation == "accept"
        assert isinstance(verdict.debate_rounds, list)

    @pytest.mark.asyncio
    async def test_debate_with_rounds_override(self):
        parliament = AIParliament(gateway=_make_mock_gateway())

        async def mock_opening(p):
            return "Opening"

        async def mock_respond(ctx):
            return "Response"

        async def mock_final(ctx):
            return {"score": 3.0, "recommendation": "revision", "summary": "Test",
                    "key_strengths": [], "key_weaknesses": [], "_error": False}

        for member_type, member in parliament.members.items():
            member.opening_statement = mock_opening
            member.respond = mock_respond
            member.final_statement = mock_final

        paper = {"title": "Test", "abstract": "Abstract"}
        verdict = await parliament.debate(paper, rounds=2)
        assert isinstance(verdict, Verdict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
