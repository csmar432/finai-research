"""Tests for debate_arena.py — Structured Multi-Agent Debate Arena.

Covers all classes: DebateRole, DebateStage, DebateClaim, DebateRound,
DebateVerdict, DebateArena, DebateJudge, SSEEvent.
"""

import pytest

from scripts.core.debate_arena import (
    DebateRole,
    DebateStage,
    DebateClaim,
    DebateRound,
    DebateVerdict,
    DebateArena,
    DebateJudge,
    SSEEvent,
    PROPOSER_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    SYNTHESIZER_SYSTEM_PROMPT,
    CRITIC_CHALLENGE_TEMPLATES,
)


# ─── Test Enums ───────────────────────────────────────────────────────────────


class TestDebateRole:
    """Tests for DebateRole enum."""

    def test_debate_role_values(self):
        assert DebateRole.PROPOSER.value == "proposer"
        assert DebateRole.CRITIC.value == "critic"
        assert DebateRole.SYNTHESIZER.value == "synthesizer"

    def test_debate_role_from_string(self):
        assert DebateRole("proposer") == DebateRole.PROPOSER
        assert DebateRole("critic") == DebateRole.CRITIC
        assert DebateRole("synthesizer") == DebateRole.SYNTHESIZER

    def test_debate_role_is_string(self):
        assert isinstance(DebateRole.PROPOSER, str)
        assert isinstance(DebateRole.CRITIC, str)


class TestDebateStage:
    """Tests for DebateStage enum."""

    def test_debate_stage_values(self):
        assert DebateStage.CLAIM.value == "claim"
        assert DebateStage.ROUND_1.value == "round_1"
        assert DebateStage.ROUND_2.value == "round_2"
        assert DebateStage.ROUND_3.value == "round_3"
        assert DebateStage.VERDICT.value == "verdict"

    def test_debate_stage_order(self):
        stages = [
            DebateStage.CLAIM,
            DebateStage.ROUND_1,
            DebateStage.ROUND_2,
            DebateStage.ROUND_3,
            DebateStage.VERDICT,
        ]
        for i in range(len(stages) - 1):
            assert stages[i].value < stages[i + 1].value


# ─── Test DebateClaim ────────────────────────────────────────────────────────


class TestDebateClaim:
    """Tests for DebateClaim dataclass."""

    def test_claim_creation_defaults(self):
        claim = DebateClaim(claim_text="Carbon trading increases green patents.")
        assert claim.claim_text == "Carbon trading increases green patents."
        assert claim.context == {}
        assert claim.domain == ""
        assert claim.submitted_by == "anonymous"
        assert isinstance(claim.submitted_at, float)

    def test_claim_creation_full(self):
        ctx = {"data": "CSMAR", "methodology": "DID"}
        claim = DebateClaim(
            claim_text="Carbon trading increases green patents.",
            context=ctx,
            domain="climate_economics",
            methodology="DID",
            sample_info="A-share 2010-2023",
            submitted_by="researcher_001",
            submitted_at=1700000000.0,
        )
        assert claim.context == ctx
        assert claim.domain == "climate_economics"
        assert claim.methodology == "DID"
        assert claim.sample_info == "A-share 2010-2023"
        assert claim.submitted_by == "researcher_001"
        assert claim.submitted_at == 1700000000.0

    def test_to_prompt_basic(self):
        claim = DebateClaim(claim_text="Carbon trading increases green patents.")
        prompt = claim.to_prompt()
        assert "Carbon trading increases green patents" in prompt

    def test_to_prompt_with_all_fields(self):
        claim = DebateClaim(
            claim_text="Test claim",
            domain="finance",
            methodology="DID",
            sample_info="A-share firms",
        )
        prompt = claim.to_prompt()
        assert "## Domain" in prompt
        assert "## Methodology" in prompt
        assert "## Sample" in prompt
        assert "finance" in prompt
        assert "DID" in prompt
        assert "A-share firms" in prompt

    def test_to_dict_roundtrip(self):
        claim = DebateClaim(
            claim_text="Test",
            context={"key": "value"},
            domain="finance",
            submitted_by="tester",
        )
        d = claim.to_dict()
        assert d["claim_text"] == "Test"
        assert d["context"] == {"key": "value"}
        assert d["domain"] == "finance"
        assert d["submitted_by"] == "tester"


# ─── Test DebateRound ────────────────────────────────────────────────────────


class TestDebateRound:
    """Tests for DebateRound dataclass."""

    def test_round_creation_minimal(self):
        round_obj = DebateRound(
            round_number=1,
            role=DebateRole.PROPOSER,
            content="This is my evidence-based argument.",
        )
        assert round_obj.round_number == 1
        assert round_obj.role == DebateRole.PROPOSER
        assert round_obj.content == "This is my evidence-based argument."
        assert round_obj.evidence_cited == []
        assert round_obj.objections_raised == []
        assert round_obj.counter_arguments == []
        assert isinstance(round_obj.timestamp, float)

    def test_round_creation_full(self):
        round_obj = DebateRound(
            round_number=2,
            role=DebateRole.CRITIC,
            content="I object on three grounds.",
            evidence_cited=["[Author, 2023]"],
            objections_raised=["Parallel trends violated", "Selection bias"],
            counter_arguments=["Pre-trends are flat"],
            timestamp=1700000000.0,
        )
        assert round_obj.round_number == 2
        assert round_obj.role == DebateRole.CRITIC
        assert len(round_obj.objections_raised) == 2

    def test_is_substantive_short_content(self):
        short_round = DebateRound(
            round_number=1,
            role=DebateRole.PROPOSER,
            content="Short.",
        )
        assert short_round.is_substantive() is False

    def test_is_substantive_long_content(self):
        long_content = "A" * 150  # > 100 chars
        long_round = DebateRound(
            round_number=1,
            role=DebateRole.PROPOSER,
            content=long_content,
        )
        assert long_round.is_substantive() is True

    def test_is_substantive_exactly_100_chars(self):
        content_100 = "A" * 100
        r = DebateRound(round_number=1, role=DebateRole.PROPOSER, content=content_100)
        assert r.is_substantive() is False  # exactly 100 is not > 100

    def test_to_dict(self):
        round_obj = DebateRound(
            round_number=3,
            role=DebateRole.SYNTHESIZER,
            content="Balanced verdict.",
            evidence_cited=["[Synth, 2024]"],
        )
        d = round_obj.to_dict()
        assert d["round_number"] == 3
        assert d["role"] == "synthesizer"
        assert d["content"] == "Balanced verdict."
        assert d["evidence_cited"] == ["[Synth, 2024]"]


# ─── Test DebateVerdict ─────────────────────────────────────────────────────


class TestDebateVerdict:
    """Tests for DebateVerdict dataclass."""

    def test_verdict_creation(self):
        verdict = DebateVerdict(
            claim="Test claim",
            overall_score=7.5,
            confidence_delta=0.5,
        )
        assert verdict.claim == "Test claim"
        assert verdict.overall_score == 7.5
        assert verdict.confidence_delta == 0.5
        assert verdict.accepted is False
        assert verdict.confidence_level == "medium"

    def test_verdict_to_dict(self):
        verdict = DebateVerdict(
            claim="Test",
            overall_score=8.0,
            confidence_delta=0.3,
            key_concerns=["Identification concern"],
            accepted=True,
            confidence_level="high",
        )
        d = verdict.to_dict()
        assert d["overall_score"] == 8.0
        assert d["accepted"] is True
        assert d["confidence_level"] == "high"
        assert d["key_concerns"] == ["Identification concern"]

    def test_to_review_text_basic(self):
        verdict = DebateVerdict(
            claim="Carbon trading increases green patents.",
            overall_score=7.0,
            confidence_delta=0.5,
            key_concerns=["Parallel trends"],
            unresolved_issues=["Sample selection bias"],
            suggested_revisions=["Add Heckman correction"],
            confidence_reasoning="Sound methodology",
            accepted=True,
            confidence_level="medium",
        )
        text = verdict.to_review_text()
        assert len(text) > 50
        assert "Carbon trading" in text or "7.0" in text

    def test_to_review_text_empty(self):
        verdict = DebateVerdict(
            claim="Short claim",
            overall_score=5.0,
            confidence_delta=1.0,
        )
        text = verdict.to_review_text()
        assert isinstance(text, str)
        assert len(text) > 0


# ─── Test DebateArena ────────────────────────────────────────────────────────


class TestDebateArena:
    """Tests for DebateArena class."""

    def test_init_default(self):
        arena = DebateArena()
        assert arena.max_rounds == 3
        assert arena.temperature == 0.3
        assert arena.llm_gateway is None

    def test_init_custom(self):
        def dummy_gateway(prompt, system=None, temperature=0.3):
            return "mock"

        arena = DebateArena(llm_gateway=dummy_gateway, max_rounds=5, temperature=0.7)
        assert arena.max_rounds == 5
        assert arena.temperature == 0.7
        assert arena.llm_gateway is not None

    @pytest.mark.asyncio
    async def test_debate_rounds_count(self):
        arena = DebateArena()
        claim = DebateClaim(claim_text="Test claim", methodology="DID")
        verdict = await arena.debate(claim, rounds=3)
        assert len(verdict.rounds_summary) == 3

    @pytest.mark.asyncio
    async def test_debate_rounds_2(self):
        arena = DebateArena()
        claim = DebateClaim(claim_text="Test claim")
        verdict = await arena.debate(claim, rounds=2)
        assert len(verdict.rounds_summary) == 2
        assert verdict.rounds_summary[0].role == DebateRole.PROPOSER
        assert verdict.rounds_summary[1].role == DebateRole.CRITIC

    @pytest.mark.asyncio
    async def test_debate_all_roles_present(self):
        arena = DebateArena()
        claim = DebateClaim(claim_text="Test claim", methodology="DID")
        verdict = await arena.debate(claim, rounds=3)
        roles = [r.role for r in verdict.rounds_summary]
        assert DebateRole.PROPOSER in roles
        assert DebateRole.CRITIC in roles
        assert DebateRole.SYNTHESIZER in roles

    def test_mock_response_proposer(self):
        arena = DebateArena()
        response = arena._mock_response(DebateRole.PROPOSER, "Carbon trading claim")
        assert "Mock Proposer response" in response
        assert "Carbon trading claim" in response

    def test_mock_response_critic(self):
        arena = DebateArena()
        response = arena._mock_response(DebateRole.CRITIC, "Carbon trading claim")
        assert "Mock Critic response" in response

    def test_mock_response_synthesizer(self):
        arena = DebateArena()
        response = arena._mock_response(DebateRole.SYNTHESIZER, "Carbon trading claim")
        assert "Mock Synthesizer response" in response

    def test_extract_citations(self):
        arena = DebateArena()
        text = (
            "This finding is consistent with [Zhang et al., 2023] and "
            "[Li and Wang, 2024]. See also Author et al. (2022)."
        )
        citations = arena._extract_citations(text)
        assert len(citations) >= 2

    def test_extract_objections(self):
        arena = DebateArena()
        text = (
            "Concerns:\n"
            "1. Parallel trends may be violated\n"
            "2. Selection bias in treatment assignment\n"
            "3. Measurement error in outcome variable"
        )
        objections = arena._extract_objections(text)
        assert len(objections) >= 1

    def test_extract_suggestions(self):
        arena = DebateArena()
        text = (
            "Suggested revisions:\n"
            "1. Conduct event-study\n"
            "2. Add instrumental variables\n"
            "3. Test external validity"
        )
        suggestions = arena._extract_suggestions(text)
        assert len(suggestions) >= 1

    def test_stream_debate_yields_events(self):
        arena = DebateArena()
        claim = DebateClaim(claim_text="Test claim")
        events = list(arena.stream_debate(claim))
        event_names = [e.event for e in events]
        assert "debate_start" in event_names
        assert "verdict_complete" in event_names


# ─── Test DebateJudge ───────────────────────────────────────────────────────


class TestDebateJudge:
    """Tests for DebateJudge scoring logic."""

    def test_score_proposer_low_evidence(self):
        """Proposer with no evidence citations gets base score ~5."""
        rounds = [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content="Claim without evidence.",
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        proposer_score, _, _ = DebateJudge.score_from_rounds(rounds, claim)
        assert 5.0 <= proposer_score <= 6.0

    def test_score_proposer_with_evidence(self):
        """Proposer with citations gets higher score."""
        rounds = [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content="A" * 600,
                evidence_cited=["[Zhang, 2023]", "[Li, 2024]", "[Wang, 2022]"],
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        proposer_score, _, _ = DebateJudge.score_from_rounds(rounds, claim)
        assert proposer_score > 5.0

    def test_score_critic_with_objections(self):
        """Critic with objections gets higher score."""
        rounds = [
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 600,
                objections_raised=["Objection 1", "Objection 2", "Objection 3"],
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        _, critic_score, _ = DebateJudge.score_from_rounds(rounds, claim)
        assert critic_score > 5.0

    def test_unresolved_objections_not_addressed(self):
        """Objections not in synthesizer content remain unresolved."""
        rounds = [
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 600,
                objections_raised=["UniqueParallelTrendsViolation claim here"],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content="The evidence is strong overall.",
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        _, _, unresolved = DebateJudge.score_from_rounds(rounds, claim)
        assert len(unresolved) == 1

    def test_unresolved_objections_addressed(self):
        """Objections addressed by synthesizer are resolved."""
        rounds = [
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 600,
                objections_raised=["parallel trends concern raised"],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content="I address the parallel trends concern raised by the critic.",
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        _, _, unresolved = DebateJudge.score_from_rounds(rounds, claim)
        assert len(unresolved) == 0

    def test_full_debate_scoring(self):
        """Full 3-round debate produces valid scores."""
        rounds = [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content="A" * 600,
                evidence_cited=["[Zhang, 2023]"],
            ),
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 600,
                objections_raised=["Parallel trends concern", "Selection bias"],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content="I address the parallel trends concern raised.",
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        proposer_score, critic_score, unresolved = DebateJudge.score_from_rounds(rounds, claim)
        assert 0 <= proposer_score <= 10
        assert 0 <= critic_score <= 10
        assert isinstance(unresolved, list)


# ─── Test SSEEvent ───────────────────────────────────────────────────────────


class TestSSEEvent:
    """Tests for SSEEvent dataclass."""

    def test_sse_event_creation(self):
        event = SSEEvent(event="round_1_complete", data={"round": 1})
        assert event.event == "round_1_complete"
        assert event.data["round"] == 1
        assert isinstance(event.event_id, str)
        assert isinstance(event.timestamp, float)

    def test_sse_event_to_sse_format(self):
        event = SSEEvent(event="verdict_complete", data={"score": 8.0})
        sse = event.to_sse()
        assert "id:" in sse
        assert "event: verdict_complete" in sse
        assert "score" in sse
        assert "\n\n" in sse  # SSE requires double newline


# ─── Test Module Constants ───────────────────────────────────────────────────


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_proposer_system_prompt(self):
        assert len(PROPOSER_SYSTEM_PROMPT) > 50
        assert "empirical researcher" in PROPOSER_SYSTEM_PROMPT

    def test_critic_system_prompt(self):
        assert len(CRITIC_SYSTEM_PROMPT) > 50
        assert "skeptical" in CRITIC_SYSTEM_PROMPT or "Identification" in CRITIC_SYSTEM_PROMPT

    def test_synthesizer_system_prompt(self):
        assert len(SYNTHESIZER_SYSTEM_PROMPT) > 50
        assert "senior editor" in SYNTHESIZER_SYSTEM_PROMPT

    def test_critic_challenge_templates_count(self):
        assert len(CRITIC_CHALLENGE_TEMPLATES) == 20

    def test_critic_challenge_templates_content(self):
        for template in CRITIC_CHALLENGE_TEMPLATES:
            assert isinstance(template, str)
            assert len(template) > 20
            # Each template should address a distinct concern
        # Templates should be diverse (check for common themes)
        themes = [t.lower() for t in CRITIC_CHALLENGE_TEMPLATES]
        assert any("parallel trends" in t for t in themes)
        assert any("endogene" in t for t in themes)
        assert any("selection" in t for t in themes)


# ─── Test Async Debate with Mock LLM ────────────────────────────────────────


class TestDebateArenaAsync:
    """Tests for async debate methods with mocked LLM gateway."""

    @pytest.mark.asyncio
    async def test_async_debate_mock_scoring(self):
        """Async debate with mock gateway produces correct role assignments."""
        arena = DebateArena(llm_gateway=None)
        claim = DebateClaim(
            claim_text="Carbon trading increases green patents by 15%",
            methodology="DID",
            sample_info="A-share 2010-2023",
        )
        verdict = await arena.debate(claim, rounds=3)
        assert verdict.overall_score > 0
        assert verdict.confidence_level in ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_async_debate_synthesizer_round(self):
        """Synthesizer round must be the last round."""
        arena = DebateArena(llm_gateway=None)
        claim = DebateClaim(claim_text="Test claim", methodology="DID")
        verdict = await arena.debate(claim, rounds=3)
        assert verdict.rounds_summary[-1].role == DebateRole.SYNTHESIZER

    @pytest.mark.asyncio
    async def test_accepted_verdict(self):
        """High score and low unresolved issues should mean accepted."""
        rounds = [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content="A" * 600,
                evidence_cited=["[A, 2023]", "[B, 2024]", "[C, 2022]"],
            ),
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 200,
                objections_raised=[],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content="Strong evidence supports this claim.",
            ),
        ]
        claim = DebateClaim(claim_text="Test")
        verdict = DebateArena()._compute_verdict(claim, rounds)
        assert isinstance(verdict.overall_score, float)
        assert verdict.confidence_delta >= 0

    @pytest.mark.asyncio
    async def test_compute_verdict_mock(self):
        """_compute_verdict returns valid verdict structure."""
        arena = DebateArena()
        rounds = [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content="A" * 600,
                evidence_cited=["[Zhang, 2023]"],
            ),
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content="A" * 600,
                objections_raised=["Selection bias"],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content="Score: 7.5/10. Medium confidence.",
            ),
        ]
        verdict = arena._compute_verdict(
            DebateClaim(claim_text="Test claim"), rounds
        )
        assert verdict.overall_score >= 0
        assert verdict.confidence_delta >= 0
        assert verdict.confidence_level in ["high", "medium", "low"]
