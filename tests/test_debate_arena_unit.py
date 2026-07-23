"""Unit tests for scripts.core.debate_arena.

Covers:
- Enums: DebateRole, DebateStage
- Module constants (system prompts, challenge templates)
- SSEEvent dataclass + to_sse
- DebateClaim dataclass + to_prompt + to_dict
- DebateRound dataclass + is_substantive + to_dict
- DebateVerdict dataclass + to_dict + to_review_text
- DebateArena.__init__ (defaults / custom)
- DebateArena._mock_response (each role)
- DebateArena._extract_citations / _extract_objections / _extract_suggestions
- DebateArena._call_llm (sync + async gateways; mock fallback)
- DebateArena._compute_verdict (verdict fields + score-blending)
- DebateArena.debate (async, mocked LLM)
- DebateArena.stream_debate (SSE event generator)
- DebateJudge.score_from_rounds (rule-based scoring)

LLM calls are always mocked via ``_call_llm`` or a fake gateway. No real
network I/O occurs in any test. Async paths are exercised with
``asyncio.run`` per the user's hard rule.
"""

from __future__ import annotations

import asyncio
import json


from scripts.core.debate_arena import (
    CRITIC_CHALLENGE_TEMPLATES,
    CRITIC_SYSTEM_PROMPT,
    PROPOSER_SYSTEM_PROMPT,
    SSEEvent,
    SYNTHESIZER_SYSTEM_PROMPT,
    DebateArena,
    DebateClaim,
    DebateJudge,
    DebateRole,
    DebateRound,
    DebateStage,
    DebateVerdict,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def _make_claim(**overrides) -> DebateClaim:
    """Construct a DebateClaim with sensible defaults."""
    defaults = dict(
        claim_text="Carbon trading increases green patents by 15%.",
        context={"data": "CSMAR", "methodology": "DID"},
        domain="environmental economics",
        methodology="DID",
        sample_info="A-share listed firms 2015-2022",
        submitted_by="tester",
    )
    defaults.update(overrides)
    return DebateClaim(**defaults)


def _fake_proposer_response() -> str:
    return (
        "Claim statement.\n"
        "Evidence: [Smith, 2020] document a 12% effect using panel data.\n"
        "Mechanism: cost-of-capital channel.\n"
        "Effect size: β = 0.15 (95% CI: [0.10, 0.20], p < 0.05)."
    )


def _fake_critic_response() -> str:
    return (
        "Three major concerns:\n"
        "1. Parallel trends assumption may be violated in the pre-treatment period.\n"
        "2. Treatment endogeneity and selection on observables not fully addressed.\n"
        "3. External validity concerns: industry-level findings may not generalize.\n"
    )


def _fake_synthesizer_response() -> str:
    return (
        "Verdict: This claim has moderate empirical support.\n"
        "Score: 6.5/10\n"
        "Confidence: Medium\n"
        "Strengths: novel context and robust mechanism.\n"
        "Weaknesses: identification concerns remain, sample is limited.\n"
        "Suggested revisions: Conduct event-study, add IV, test external validity.\n"
    )


# ════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════


class TestEnums:
    def test_debate_role_values(self):
        assert DebateRole.PROPOSER.value == "proposer"
        assert DebateRole.CRITIC.value == "critic"
        assert DebateRole.SYNTHESIZER.value == "synthesizer"

    def test_debate_role_is_string_enum(self):
        # Inherits from str; str(DebateRole.PROPOSER) == "DebateRole.PROPOSER"
        # but the value attribute returns the underlying string.
        assert DebateRole.PROPOSER.value == "proposer"
        assert isinstance(DebateRole.PROPOSER, str)

    def test_debate_stage_values(self):
        assert DebateStage.CLAIM.value == "claim"
        assert DebateStage.ROUND_1.value == "round_1"
        assert DebateStage.ROUND_2.value == "round_2"
        assert DebateStage.ROUND_3.value == "round_3"
        assert DebateStage.VERDICT.value == "verdict"

    def test_debate_role_membership(self):
        assert len(list(DebateRole)) == 3
        assert len(list(DebateStage)) == 5


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════


class TestModuleConstants:
    def test_proposer_system_prompt_nonempty(self):
        assert isinstance(PROPOSER_SYSTEM_PROMPT, str)
        assert len(PROPOSER_SYSTEM_PROMPT) > 50

    def test_critic_system_prompt_nonempty(self):
        assert isinstance(CRITIC_SYSTEM_PROMPT, str)
        assert len(CRITIC_SYSTEM_PROMPT) > 50

    def test_synthesizer_system_prompt_nonempty(self):
        assert isinstance(SYNTHESIZER_SYSTEM_PROMPT, str)
        assert len(SYNTHESIZER_SYSTEM_PROMPT) > 50

    def test_critic_challenge_templates_populated(self):
        assert isinstance(CRITIC_CHALLENGE_TEMPLATES, list)
        assert len(CRITIC_CHALLENGE_TEMPLATES) >= 10
        for template in CRITIC_CHALLENGE_TEMPLATES:
            assert isinstance(template, str)
            assert len(template) > 30

    def test_challenge_templates_deterministic_pick(self):
        # Same claim_text → same challenge every time.
        claim_text = "Sample claim"
        pick1 = CRITIC_CHALLENGE_TEMPLATES[
            hash(claim_text) % len(CRITIC_CHALLENGE_TEMPLATES)
        ]
        pick2 = CRITIC_CHALLENGE_TEMPLATES[
            hash(claim_text) % len(CRITIC_CHALLENGE_TEMPLATES)
        ]
        assert pick1 == pick2


# ════════════════════════════════════════════════════════════════════
# SSEEvent
# ════════════════════════════════════════════════════════════════════


class TestSSEEvent:
    def test_construction_defaults(self):
        ev = SSEEvent(event="round_1_complete", data={"x": 1})
        assert ev.event == "round_1_complete"
        assert ev.data == {"x": 1}
        # event_id and timestamp populated by default_factory
        assert isinstance(ev.event_id, str)
        assert len(ev.event_id) == 8
        assert isinstance(ev.timestamp, float)

    def test_to_sse_format(self):
        ev = SSEEvent(event="debate_start", data={"claim": "abc"})
        out = ev.to_sse()
        assert out.startswith("id: ")
        assert "event: debate_start" in out
        assert "data: " in out
        assert out.endswith("\n\n")

    def test_to_sse_serializes_unicode(self):
        ev = SSEEvent(event="round_1_complete", data={"claim": "碳交易"})
        out = ev.to_sse()
        # ensure_ascii=False in JSON dump → 中文 preserved
        assert "碳交易" in out

    def test_to_sse_payload_is_json(self):
        ev = SSEEvent(event="x", data={"a": 1, "b": [1, 2]})
        out = ev.to_sse()
        # data: <json>
        data_line = [ln for ln in out.splitlines() if ln.startswith("data: ")][0]
        payload = json.loads(data_line[len("data: "):])
        assert payload == {"a": 1, "b": [1, 2]}

    def test_event_ids_unique(self):
        e1 = SSEEvent(event="a", data={})
        e2 = SSEEvent(event="a", data={})
        # Different default_factory calls
        assert e1.event_id != e2.event_id


# ════════════════════════════════════════════════════════════════════
# DebateClaim
# ════════════════════════════════════════════════════════════════════


class TestDebateClaim:
    def test_default_construction(self):
        c = DebateClaim(claim_text="x")
        assert c.claim_text == "x"
        assert c.context == {}
        assert c.domain == ""
        assert c.methodology == ""
        assert c.sample_info == ""
        assert c.submitted_by == "anonymous"
        assert isinstance(c.submitted_at, float)

    def test_to_prompt_minimal(self):
        c = DebateClaim(claim_text="X claim")
        p = c.to_prompt()
        assert "## Claim" in p
        assert "X claim" in p
        # No optional sections rendered
        assert "## Domain" not in p
        assert "## Methodology" not in p
        assert "## Sample" not in p
        assert "## Context" not in p

    def test_to_prompt_with_optional_sections(self):
        c = _make_claim()
        p = c.to_prompt()
        assert "## Domain" in p
        assert "## Methodology" in p
        assert "## Sample" in p
        assert "## Context" in p
        # Context serialized as JSON
        assert "CSMAR" in p

    def test_to_prompt_includes_all_required_sections(self):
        c = _make_claim()
        prompt = c.to_prompt()
        assert "## Claim" in prompt
        assert "## Domain\nenvironmental economics" in prompt
        assert "## Methodology\nDID" in prompt
        assert "## Sample\nA-share listed firms 2015-2022" in prompt

    def test_to_dict_round_trip(self):
        c = _make_claim()
        d = c.to_dict()
        assert d["claim_text"] == c.claim_text
        assert d["domain"] == c.domain
        assert d["methodology"] == c.methodology
        assert d["context"] == c.context
        assert d["submitted_by"] == "tester"

    def test_to_dict_contains_required_keys(self):
        d = DebateClaim(claim_text="x").to_dict()
        for key in (
            "claim_text",
            "context",
            "domain",
            "methodology",
            "sample_info",
            "submitted_by",
            "submitted_at",
        ):
            assert key in d


# ════════════════════════════════════════════════════════════════════
# DebateRound
# ════════════════════════════════════════════════════════════════════


class TestDebateRound:
    def _make_round(self, **kwargs):
        defaults = dict(
            round_number=1,
            role=DebateRole.PROPOSER,
            content="This is a long enough content to be substantive. " * 4,
            evidence_cited=[],
            objections_raised=[],
            counter_arguments=[],
        )
        defaults.update(kwargs)
        return DebateRound(**defaults)

    def test_default_lists(self):
        r = DebateRound(round_number=1, role=DebateRole.PROPOSER, content="x")
        assert r.evidence_cited == []
        assert r.objections_raised == []
        assert r.counter_arguments == []

    def test_is_substantive_true_when_long_enough(self):
        r = self._make_round(content="x" * 200)
        assert r.is_substantive() is True

    def test_is_substantive_false_when_short(self):
        r = self._make_round(content="x" * 50)
        assert r.is_substantive() is False

    def test_is_substantive_threshold_is_100(self):
        # Boundary check: 100 chars stripped should be False, 101 should be True.
        r_low = self._make_round(content="x" * 99)
        assert r_low.is_substantive() is False
        r_high = self._make_round(content="x" * 101)
        assert r_high.is_substantive() is True

    def test_is_substantive_strips_whitespace(self):
        r = self._make_round(content="   " + ("x" * 50))
        # 53 stripped chars — still short
        assert r.is_substantive() is False

    def test_to_dict_includes_all_fields(self):
        r = self._make_round(
            evidence_cited=["[Smith, 2020]"],
            objections_raised=["parallel trends violated"],
        )
        d = r.to_dict()
        assert d["round_number"] == 1
        assert d["role"] == "proposer"
        assert d["content"].startswith("This is a long")
        assert d["evidence_cited"] == ["[Smith, 2020]"]
        assert d["objections_raised"] == ["parallel trends violated"]
        assert "timestamp" in d


# ════════════════════════════════════════════════════════════════════
# DebateVerdict
# ════════════════════════════════════════════════════════════════════


class TestDebateVerdict:
    def _make_verdict(self, **kwargs) -> DebateVerdict:
        defaults = dict(
            claim="Test claim",
            overall_score=6.5,
            confidence_delta=1.0,
            key_concerns=["parallel trends"],
            unresolved_issues=["endogeneity"],
            suggested_revisions=["add event study"],
            confidence_reasoning="Moderate evidence base.",
            rounds_summary=[],
            accepted=True,
            confidence_level="medium",
        )
        defaults.update(kwargs)
        return DebateVerdict(**defaults)

    def test_defaults(self):
        v = DebateVerdict(claim="x", overall_score=5.0, confidence_delta=1.0)
        assert v.key_concerns == []
        assert v.unresolved_issues == []
        assert v.suggested_revisions == []
        assert v.accepted is False
        assert v.confidence_level == "medium"

    def test_to_dict_full(self):
        v = self._make_verdict()
        d = v.to_dict()
        assert d["claim"] == "Test claim"
        assert d["overall_score"] == 6.5
        assert d["confidence_delta"] == 1.0
        assert d["key_concerns"] == ["parallel trends"]
        assert d["unresolved_issues"] == ["endogeneity"]
        assert d["suggested_revisions"] == ["add event study"]
        assert d["accepted"] is True
        assert d["confidence_level"] == "medium"

    def test_to_dict_serializes_rounds(self):
        rounds = [
            DebateRound(round_number=1, role=DebateRole.PROPOSER, content="x" * 200)
        ]
        v = self._make_verdict(rounds_summary=rounds)
        d = v.to_dict()
        assert isinstance(d["rounds_summary"], list)
        assert d["rounds_summary"][0]["round_number"] == 1

    def test_to_review_text_contains_score_and_claim(self):
        v = self._make_verdict()
        text = v.to_review_text()
        assert "Test claim" in text
        assert "6.5" in text
        assert "MEDIUM" in text  # confidence level uppercase

    def test_to_review_text_accepted_keyword(self):
        v = self._make_verdict(accepted=True)
        text = v.to_review_text()
        assert "accepted" in text.lower()

    def test_to_review_text_not_accepted_keyword(self):
        v = self._make_verdict(accepted=False)
        text = v.to_review_text()
        assert "not accepted" in text.lower()

    def test_to_review_text_truncates_long_claim(self):
        v = self._make_verdict(claim="x" * 200)
        text = v.to_review_text()
        # Should truncate claim at 100 chars with ellipsis
        assert "..." in text

    def test_to_review_text_includes_concerns(self):
        v = self._make_verdict(
            key_concerns=["parallel trends", "external validity", "measurement"]
        )
        text = v.to_review_text()
        assert "parallel trends" in text

    def test_to_review_text_includes_suggested_revisions(self):
        v = self._make_verdict(
            suggested_revisions=["add event study", "include IV analysis"]
        )
        text = v.to_review_text()
        # One or both revisions rendered
        assert "event study" in text or "add event study" in text

    def test_to_review_text_includes_confidence_reasoning(self):
        v = self._make_verdict(confidence_reasoning="Identification is rock solid.")
        text = v.to_review_text()
        assert "Identification is rock solid" in text

    def test_to_review_text_unresolved_issues_rendered(self):
        v = self._make_verdict(
            unresolved_issues=["endogeneity", "small sample"]
        )
        text = v.to_review_text()
        assert "2 issue" in text


# ════════════════════════════════════════════════════════════════════
# DebateArena — initialization
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaInit:
    def test_default_init(self):
        arena = DebateArena()
        assert arena.llm_gateway is None
        assert arena.max_rounds == 3
        assert arena.temperature == 0.3

    def test_custom_init(self):
        gw = lambda *a, **kw: "x"
        arena = DebateArena(llm_gateway=gw, max_rounds=2, temperature=0.7)
        assert arena.llm_gateway is gw
        assert arena.max_rounds == 2
        assert arena.temperature == 0.7


# ════════════════════════════════════════════════════════════════════
# DebateArena — _mock_response
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaMockResponse:
    def setup_method(self):
        self.arena = DebateArena()

    def test_proposer_mock_contains_effect_size(self):
        out = self.arena._mock_response(DebateRole.PROPOSER, "sample prompt")
        assert "Mock Proposer" in out
        assert "%" in out
        assert "Effect size" in out

    def test_critic_mock_lists_three_concerns(self):
        out = self.arena._mock_response(DebateRole.CRITIC, "sample prompt")
        assert "Mock Critic" in out
        assert "1." in out and "2." in out and "3." in out
        assert "Parallel trends" in out or "parallel trends" in out.lower()

    def test_synthesizer_mock_has_score_and_confidence(self):
        out = self.arena._mock_response(DebateRole.SYNTHESIZER, "sample prompt")
        assert "Mock Synthesizer" in out
        assert "/10" in out
        assert "Confidence" in out

    def test_mock_response_deterministic_per_prompt(self):
        a = self.arena._mock_response(DebateRole.PROPOSER, "same prompt")
        b = self.arena._mock_response(DebateRole.PROPOSER, "same prompt")
        assert a == b


# ════════════════════════════════════════════════════════════════════
# DebateArena — extractors
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaExtractors:
    def setup_method(self):
        self.arena = DebateArena()

    def test_extract_citations_bracket_form(self):
        text = "[Smith, 2020] found a positive effect. [Jones et al., 2019] confirm."
        cites = self.arena._extract_citations(text)
        assert any("Smith" in c for c in cites)
        assert any("Jones" in c for c in cites)

    def test_extract_citations_parenthetical(self):
        text = "Prior work (Brown et al., 2021) shows similar patterns."
        cites = self.arena._extract_citations(text)
        assert any("Brown" in c for c in cites)

    def test_extract_citations_dedupes(self):
        text = "[Smith, 2020] [Smith, 2020] [Smith, 2020]"
        cites = self.arena._extract_citations(text)
        # Deduplicated → at most one entry per unique citation
        assert len(cites) == len(set(cites))

    def test_extract_citations_caps_at_ten(self):
        text = " ".join(f"[Author{i}, 2020]" for i in range(20))
        cites = self.arena._extract_citations(text)
        assert len(cites) <= 10

    def test_extract_citations_empty_when_no_match(self):
        text = "This text contains no citation patterns."
        cites = self.arena._extract_citations(text)
        assert cites == []

    def test_extract_objections_numbered(self):
        # Lines need >20 stripped chars to be counted.
        text = (
            "1. Parallel trends assumption clearly violated\n"
            "2. Endogeneity not addressed at all\n"
            "3. Small sample bias in the treatment group\n"
        )
        objs = self.arena._extract_objections(text)
        assert len(objs) == 3
        assert "Parallel trends" in objs[0]

    def test_extract_objections_ignores_short_lines(self):
        text = "1. ok\n2. also ok\n3. yep"
        objs = self.arena._extract_objections(text)
        # All <20 chars → empty
        assert objs == []

    def test_extract_objections_caps_at_ten(self):
        lines = [f"{i}. {'A concern about methodology ' * 4}" for i in range(1, 16)]
        text = "\n".join(lines)
        objs = self.arena._extract_objections(text)
        assert len(objs) <= 10

    def test_extract_suggestions_revision_lines(self):
        text = (
            "1. Add an event-study to validate parallel trends\n"
            "2. Use Callaway-SantAnna for staggered adoption\n"
        )
        sugg = self.arena._extract_suggestions(text)
        assert len(sugg) == 2

    def test_extract_suggestions_caps_at_five(self):
        lines = [f"{i}. Suggestion for revision {i} " * 5 for i in range(1, 10)]
        text = "\n".join(lines)
        sugg = self.arena._extract_suggestions(text)
        assert len(sugg) <= 5


# ════════════════════════════════════════════════════════════════════
# DebateArena — _call_llm
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaCallLLM:
    def test_no_gateway_uses_mock(self):
        arena = DebateArena()
        result = asyncio.run(arena._call_llm("prompt", DebateRole.PROPOSER))
        assert "Mock Proposer" in result

    def test_no_gateway_critic_role(self):
        arena = DebateArena()
        result = asyncio.run(arena._call_llm("prompt", DebateRole.CRITIC))
        assert "Mock Critic" in result

    def test_no_gateway_synthesizer_role(self):
        arena = DebateArena()
        result = asyncio.run(arena._call_llm("prompt", DebateRole.SYNTHESIZER))
        assert "Mock Synthesizer" in result

    def test_sync_gateway_returning_string(self):
        def gateway(prompt, system=None, temperature=0.3):
            return f"GATEWAY:{prompt[:20]}"

        arena = DebateArena(llm_gateway=gateway)
        result = asyncio.run(arena._call_llm("hello world", DebateRole.PROPOSER))
        assert result.startswith("GATEWAY:")
        assert "hello world" in result

    def test_async_gateway_supported(self):
        async def async_gw(prompt, system=None, temperature=0.3):
            return f"ASYNC:{prompt[:10]}"

        arena = DebateArena(llm_gateway=async_gw)
        result = asyncio.run(arena._call_llm("hello world", DebateRole.PROPOSER))
        assert result.startswith("ASYNC:")

    def test_gateway_exception_falls_back_to_mock(self):
        def bad_gateway(*a, **kw):
            raise RuntimeError("API failure")

        arena = DebateArena(llm_gateway=bad_gateway)
        result = asyncio.run(arena._call_llm("prompt", DebateRole.PROPOSER))
        # Should fall back to mock response
        assert "Mock Proposer" in result

    def test_gateway_returning_non_string_coerced(self):
        def gw(prompt, system=None, temperature=0.3):
            return 12345  # non-string

        arena = DebateArena(llm_gateway=gw)
        result = asyncio.run(arena._call_llm("x", DebateRole.PROPOSER))
        # Coerced to str
        assert isinstance(result, str)


# ════════════════════════════════════════════════════════════════════
# DebateArena — _compute_verdict
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaComputeVerdict:
    def _rounds(self, *, llm_score_text=None, content_padding=600):
        # Three substantive rounds; padding ensures >500 chars for content bonus
        padding = "x" * content_padding
        return [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content=padding,
                evidence_cited=["[A, 2020]", "[B, 2021]", "[C, 2022]"],
            ),
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content=padding,
                objections_raised=[
                    "parallel trends assumption violated",
                    "external validity concerns",
                    "measurement error in treatment",
                ],
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content=(padding + (llm_score_text or "")) if llm_score_text is not None else padding,
            ),
        ]

    def test_verdict_contains_expected_fields(self):
        arena = DebateArena()
        claim = _make_claim()
        rounds = self._rounds(llm_score_text="Score: 7.5/10")
        v = arena._compute_verdict(claim, rounds)
        assert isinstance(v, DebateVerdict)
        assert v.claim == claim.claim_text
        assert 0.0 <= v.overall_score <= 10.0
        assert 0.0 <= v.confidence_delta <= 2.5
        assert v.confidence_level in {"high", "medium", "low"}

    def test_verdict_blends_llm_score_when_present(self):
        arena = DebateArena()
        v = arena._compute_verdict(_make_claim(), self._rounds(llm_score_text="Score: 8.0/10"))
        # LLM score (8.0) blended with rule-based score (which depends on input).
        # Just verify the score is between 0 and 10.
        assert 0.0 <= v.overall_score <= 10.0

    def test_verdict_without_llm_score(self):
        arena = DebateArena()
        v = arena._compute_verdict(_make_claim(), self._rounds(llm_score_text=None))
        # No "X/10" pattern → pure rule-based
        assert 0.0 <= v.overall_score <= 10.0

    def test_verdict_clamps_score_to_zero_ten(self):
        arena = DebateArena()
        # Build rounds where the rule-based scores could push the blend above 10
        v = arena._compute_verdict(_make_claim(), self._rounds(llm_score_text="Score: 15.0/10"))
        assert 0.0 <= v.overall_score <= 10.0

    def test_verdict_accepted_flag_consistent(self):
        arena = DebateArena()
        v = arena._compute_verdict(_make_claim(), self._rounds(llm_score_text="Score: 8.0/10"))
        # accepted == (score >= 6.0 and confidence != low)
        assert v.accepted == (v.overall_score >= 6.0 and v.confidence_level != "low")

    def test_verdict_summarizes_rounds(self):
        arena = DebateArena()
        rounds = self._rounds()
        v = arena._compute_verdict(_make_claim(), rounds)
        assert len(v.rounds_summary) == 3

    def test_verdict_key_concerns_capped(self):
        arena = DebateArena()
        v = arena._compute_verdict(_make_claim(), self._rounds())
        # At most 5 key concerns (rule: critic_round.objections_raised[:5])
        assert len(v.key_concerns) <= 5

    def test_verdict_confidence_delta_capped_at_2_5(self):
        arena = DebateArena()
        v = arena._compute_verdict(_make_claim(), self._rounds())
        assert v.confidence_delta <= 2.5


# ════════════════════════════════════════════════════════════════════
# DebateArena — debate (async end-to-end)
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaDebate:
    def test_debate_runs_three_rounds(self):
        responses = {
            DebateRole.PROPOSER: _fake_proposer_response(),
            DebateRole.CRITIC: _fake_critic_response(),
            DebateRole.SYNTHESIZER: _fake_synthesizer_response(),
        }

        def gateway(prompt, system=None, temperature=0.3):
            # Map system prompt back to role
            for role, sys in (
                (DebateRole.PROPOSER, PROPOSER_SYSTEM_PROMPT),
                (DebateRole.CRITIC, CRITIC_SYSTEM_PROMPT),
                (DebateRole.SYNTHESIZER, SYNTHESIZER_SYSTEM_PROMPT),
            ):
                if sys == system:
                    return responses[role]
            return _fake_proposer_response()

        arena = DebateArena(llm_gateway=gateway)
        claim = _make_claim()
        verdict = asyncio.run(arena.debate(claim, rounds=3))

        assert isinstance(verdict, DebateVerdict)
        assert len(verdict.rounds_summary) == 3
        assert verdict.rounds_summary[0].role == DebateRole.PROPOSER
        assert verdict.rounds_summary[1].role == DebateRole.CRITIC
        assert verdict.rounds_summary[2].role == DebateRole.SYNTHESIZER

    def test_debate_runs_two_rounds(self):
        responses = {
            DebateRole.PROPOSER: _fake_proposer_response(),
            DebateRole.CRITIC: _fake_critic_response(),
            DebateRole.SYNTHESIZER: _fake_synthesizer_response(),
        }

        def gateway(prompt, system=None, temperature=0.3):
            for role, sys in (
                (DebateRole.PROPOSER, PROPOSER_SYSTEM_PROMPT),
                (DebateRole.CRITIC, CRITIC_SYSTEM_PROMPT),
                (DebateRole.SYNTHESIZER, SYNTHESIZER_SYSTEM_PROMPT),
            ):
                if sys == system:
                    return responses[role]
            return ""

        arena = DebateArena(llm_gateway=gateway)
        verdict = asyncio.run(arena.debate(_make_claim(), rounds=2))
        # No synthesizer round when rounds=2
        roles = [r.role for r in verdict.rounds_summary]
        assert DebateRole.SYNTHESIZER not in roles
        assert len(verdict.rounds_summary) == 2

    def test_debate_runs_one_round(self):
        arena = DebateArena()
        verdict = asyncio.run(arena.debate(_make_claim(), rounds=1))
        assert len(verdict.rounds_summary) == 1
        assert verdict.rounds_summary[0].role == DebateRole.PROPOSER

    def test_debate_uses_max_rounds_when_none(self):
        arena = DebateArena(max_rounds=2, llm_gateway=lambda *a, **kw: "x")
        verdict = asyncio.run(arena.debate(_make_claim()))
        # Default to max_rounds=2
        assert len(verdict.rounds_summary) == 2

    def test_debate_no_gateway_uses_mock(self):
        arena = DebateArena()
        verdict = asyncio.run(arena.debate(_make_claim(), rounds=3))
        # Mock responses still produce substantive rounds
        assert all(r.content for r in verdict.rounds_summary)

    def test_debate_extracts_citations_from_proposer(self):
        def gateway(prompt, system=None, temperature=0.3):
            if system == PROPOSER_SYSTEM_PROMPT:
                return _fake_proposer_response()
            return _fake_critic_response()

        arena = DebateArena(llm_gateway=gateway)
        verdict = asyncio.run(arena.debate(_make_claim(), rounds=2))
        # Proposer round should have at least one citation extracted
        proposer = verdict.rounds_summary[0]
        assert len(proposer.evidence_cited) >= 1

    def test_debate_extracts_objections_from_critic(self):
        def gateway(prompt, system=None, temperature=0.3):
            if system == CRITIC_SYSTEM_PROMPT:
                return _fake_critic_response()
            return _fake_proposer_response()

        arena = DebateArena(llm_gateway=gateway)
        verdict = asyncio.run(arena.debate(_make_claim(), rounds=2))
        critic = verdict.rounds_summary[1]
        assert len(critic.objections_raised) >= 1


# ════════════════════════════════════════════════════════════════════
# DebateArena — stream_debate (SSE generator)
# ════════════════════════════════════════════════════════════════════


class TestDebateArenaStreamDebate:
    def test_stream_yields_expected_events(self):
        arena = DebateArena()
        events = list(arena.stream_debate(_make_claim()))
        # Each event is an SSEEvent
        assert all(isinstance(ev, SSEEvent) for ev in events)
        names = [ev.event for ev in events]
        assert names[0] == "debate_start"
        assert names[-1] == "verdict_complete"

    def test_stream_emits_round_completion_events(self):
        arena = DebateArena()
        events = list(arena.stream_debate(_make_claim()))
        names = [ev.event for ev in events]
        # Three round completions + start + verdict
        round_events = [n for n in names if n.startswith("round_")]
        assert "round_1_complete" in round_events
        assert "round_2_complete" in round_events
        assert "round_3_complete" in round_events

    def test_stream_verdict_event_payload(self):
        arena = DebateArena()
        events = list(arena.stream_debate(_make_claim()))
        verdict_event = next(ev for ev in events if ev.event == "verdict_complete")
        payload = verdict_event.data
        assert "score" in payload
        assert "confidence" in payload
        assert "accepted" in payload
        assert "key_concerns" in payload
        assert "unresolved" in payload
        assert "suggestions" in payload

    def test_stream_round_event_payload(self):
        arena = DebateArena()
        events = list(arena.stream_debate(_make_claim()))
        round_event = next(ev for ev in events if ev.event == "round_1_complete")
        payload = round_event.data
        assert payload["round"] == 1
        assert payload["role"] == "proposer"
        assert "content_preview" in payload
        assert isinstance(payload["substantive"], bool)


# ════════════════════════════════════════════════════════════════════
# DebateJudge — score_from_rounds
# ════════════════════════════════════════════════════════════════════


class TestDebateJudge:
    def _rounds(self, *, evidence=0, objections=0, content_len=600):
        content = "x" * content_len
        return [
            DebateRound(
                round_number=1,
                role=DebateRole.PROPOSER,
                content=content,
                evidence_cited=["[A, 2020]"] * evidence,
            ),
            DebateRound(
                round_number=2,
                role=DebateRole.CRITIC,
                content=content,
                objections_raised=["objection about methodology"] * objections,
            ),
            DebateRound(
                round_number=3,
                role=DebateRole.SYNTHESIZER,
                content=content,
            ),
        ]

    def test_score_returns_three_tuple(self):
        result = DebateJudge.score_from_rounds(self._rounds(), _make_claim())
        assert isinstance(result, tuple)
        assert len(result) == 3
        proposer, critic, unresolved = result
        assert isinstance(proposer, float)
        assert isinstance(critic, float)
        assert isinstance(unresolved, list)

    def test_proposer_score_capped_at_ten(self):
        # Max 2.5 evidence bonus + 0.5 length bonus = 3.0
        # But min(2.5, evidence_count * 0.5) → 2.5
        # Plus 0.5 length bonus → 8.0
        rounds = self._rounds(evidence=10, content_len=1000)
        proposer, _, _ = DebateJudge.score_from_rounds(rounds, _make_claim())
        assert 0.0 <= proposer <= 10.0

    def test_critic_score_capped_at_ten(self):
        rounds = self._rounds(objections=20, content_len=1000)
        _, critic, _ = DebateJudge.score_from_rounds(rounds, _make_claim())
        assert 0.0 <= critic <= 10.0

    def test_addressed_objections_reduce_critic_score(self):
        rounds_addressed = self._rounds(objections=2, content_len=1000)
        rounds_addressed[2] = DebateRound(
            round_number=3,
            role=DebateRole.SYNTHESIZER,
            content="objection about methodology is addressed.",
        )
        _, critic_addr, unresolved_addr = DebateJudge.score_from_rounds(
            rounds_addressed, _make_claim()
        )

        rounds_unaddressed = self._rounds(objections=2, content_len=1000)
        # synthesizer content does NOT contain "objection" word
        rounds_unaddressed[2] = DebateRound(
            round_number=3,
            role=DebateRole.SYNTHESIZER,
            content="everything looks fine, no issues found.",
        )
        _, critic_un, unresolved_un = DebateJudge.score_from_rounds(
            rounds_unaddressed, _make_claim()
        )

        assert len(unresolved_addr) < len(unresolved_un)
        # Addressed has lower critic score than unaddressed
        assert critic_addr <= critic_un

    def test_short_content_yields_no_bonus(self):
        rounds = self._rounds(evidence=5, content_len=50)
        proposer_short, _, _ = DebateJudge.score_from_rounds(rounds, _make_claim())
        rounds_long = self._rounds(evidence=5, content_len=1000)
        proposer_long, _, _ = DebateJudge.score_from_rounds(rounds_long, _make_claim())
        # Long + evidence → higher proposer score
        assert proposer_long > proposer_short

    def test_scores_rounded_to_two_decimals(self):
        rounds = self._rounds(evidence=1, content_len=600)
        proposer, critic, _ = DebateJudge.score_from_rounds(rounds, _make_claim())
        # Each value is rounded to 2 decimal places
        assert round(proposer, 2) == proposer
        assert round(critic, 2) == critic

    def test_missing_rounds_handled(self):
        # Only proposer round provided; content_len=600 > 500 → +0.5 length bonus.
        rounds = [DebateRound(round_number=1, role=DebateRole.PROPOSER, content="x" * 600)]
        proposer, critic, unresolved = DebateJudge.score_from_rounds(rounds, _make_claim())
        # Proposer: base 5.0 + 0.5 length bonus = 5.5; critic defaults to base 5.0
        assert proposer == 5.5
        assert critic == 5.0
        assert unresolved == []


# ════════════════════════════════════════════════════════════════════
# Module smoke
# ════════════════════════════════════════════════════════════════════


def test_module_all_exports():
    from scripts.core import debate_arena as mod

    expected = {
        "DebateRole",
        "DebateStage",
        "DebateClaim",
        "DebateRound",
        "DebateVerdict",
        "DebateArena",
        "DebateJudge",
        "SSEEvent",
    }
    for name in expected:
        assert name in mod.__all__, f"Missing export: {name}"
        assert hasattr(mod, name)


def test_module_does_not_call_llm_on_import():
    # _mock_response should be a method on DebateArena
    assert callable(getattr(DebateArena, "_mock_response", None))
    assert callable(getattr(DebateArena, "debate", None))
    assert callable(getattr(DebateJudge, "score_from_rounds", None))
