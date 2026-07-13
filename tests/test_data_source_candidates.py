"""tests/test_data_source_candidates.py — Real tests for
   scripts/research_framework/data_source_candidates.py.

Coverage:
- weighted_total math is correct for a known CandidateScore
- availability enum → sub-score mapping (all 5 values)
- license string → openness mapping (CC BY / CC0 / unknown / proprietary / MIT)
- ranking sorts descending by weighted_total
- requires_user_decision True with 2 viable, False with 1 viable
- recommended = top-ranked candidate, but requires_user_decision stays True
- build_registry convenience function returns a CandidateRegistryResult
- print_report runs without error (stdout captured)
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.data_source_candidates import (
        CandidateRegistryResult,
        CandidateScore,
        DataSourceCandidate,
        DataSourceCandidateRegistry,
        SourceAvailability,
        build_registry,
    )
except Exception as _exc:  # pragma: no cover
    pytest.skip(f"data_source_candidates not importable: {_exc}", allow_module_level=True)


# ─── SourceAvailability enum ─────────────────────────────────────────────────


class TestSourceAvailabilityEnum:
    def test_all_values_present(self):
        names = {e.name for e in SourceAvailability}
        assert names == {
            "PUBLIC_FREE",
            "PUBLIC_REGISTER",
            "RESTRICTED_LOGIN",
            "PAID",
            "UNAVAILABLE",
        }

    def test_string_inheritance(self):
        assert isinstance(SourceAvailability.PUBLIC_FREE, str)
        assert SourceAvailability.PUBLIC_FREE.value == "public_free"
        assert SourceAvailability.UNAVAILABLE.value == "unavailable"


# ─── CandidateScore math ──────────────────────────────────────────────────────


class TestCandidateScoreMath:
    def test_all_zeros(self):
        s = CandidateScore(0.0, 0.0, 0.0, 0.0, 0.0)
        assert s.weighted_total == pytest.approx(0.0, abs=1e-9)

    def test_all_ones(self):
        s = CandidateScore(1.0, 1.0, 1.0, 1.0, 1.0)
        assert s.weighted_total == pytest.approx(1.0, abs=1e-9)

    def test_weights_sum_to_one(self):
        # default weights must sum to 1.0 (per spec: .25 + .15 + .2 + .25 + .15)
        s = CandidateScore(0.0, 0.0, 0.0, 0.0, 0.0)
        assert sum(s.weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_known_weighted_sum(self):
        # 0.25*1.0 + 0.15*0.5 + 0.20*0.8 + 0.25*0.6 + 0.15*0.4
        # = 0.25 + 0.075 + 0.16 + 0.15 + 0.06 = 0.695
        s = CandidateScore(1.0, 0.5, 0.8, 0.6, 0.4)
        assert s.weighted_total == pytest.approx(0.695, abs=1e-9)

    def test_clamping_high(self):
        # > 1.0 should be clamped, not exploded
        s = CandidateScore(2.0, 2.0, 2.0, 2.0, 2.0)
        assert s.weighted_total == pytest.approx(1.0, abs=1e-9)

    def test_clamping_low(self):
        s = CandidateScore(-1.0, -1.0, -1.0, -1.0, -1.0)
        assert s.weighted_total == pytest.approx(0.0, abs=1e-9)

    def test_as_dict_keys(self):
        s = CandidateScore(1.0, 1.0, 1.0, 1.0, 1.0)
        d = s.as_dict()
        for k in (
            "availability",
            "license_openness",
            "coverage_match",
            "indicator_fit",
            "credibility",
            "weighted_total",
            "weights",
        ):
            assert k in d
        assert d["weighted_total"] == pytest.approx(1.0, abs=1e-9)


# ─── Availability enum → sub-score mapping ────────────────────────────────────


class TestAvailabilityMapping:
    @pytest.mark.parametrize(
        "avail,expected",
        [
            (SourceAvailability.PUBLIC_FREE, 1.0),
            (SourceAvailability.PUBLIC_REGISTER, 0.8),
            (SourceAvailability.RESTRICTED_LOGIN, 0.4),
            (SourceAvailability.PAID, 0.3),
            (SourceAvailability.UNAVAILABLE, 0.0),
        ],
    )
    def test_mapping(self, avail, expected):
        c = DataSourceCandidate(
            name="x",
            url="http://x",
            availability=avail,
            license="unknown",
            temporal_coverage="",
            geographic_coverage="",
            indicator_description="",
        )
        score = DataSourceCandidateRegistry("test").score_candidate(c)
        assert score.availability == pytest.approx(expected, abs=1e-9)


# ─── License string → openness mapping ────────────────────────────────────────


class TestLicenseMapping:
    @pytest.mark.parametrize(
        "license_str,expected_bracket",
        [
            ("CC BY 4.0", (0.9, 1.0)),
            ("CC BY-SA 4.0", (0.9, 1.0)),
            ("CC0 1.0", (0.9, 1.0)),
            ("Public Domain", (0.9, 1.0)),
            ("MIT License", (0.85, 1.0)),
            ("Apache 2.0", (0.85, 1.0)),
            ("Unknown", (0.3, 0.5)),
            ("", (0.3, 0.5)),
            ("restricted", (0.15, 0.25)),
            ("proprietary", (0.15, 0.25)),
            ("All Rights Reserved", (0.15, 0.25)),
        ],
    )
    def test_license_subscore_brackets(self, license_str, expected_bracket):
        c = DataSourceCandidate(
            name="x",
            url="http://x",
            availability=SourceAvailability.PUBLIC_FREE,
            license=license_str,
            temporal_coverage="",
            geographic_coverage="",
            indicator_description="",
        )
        score = DataSourceCandidateRegistry("test").score_candidate(c)
        lo, hi = expected_bracket
        assert lo <= score.license_openness <= hi, (
            f"license={license_str!r} got {score.license_openness}, "
            f"expected in [{lo}, {hi}]"
        )

    def test_none_license_is_safe(self):
        c = DataSourceCandidate(
            name="x",
            url="http://x",
            availability=SourceAvailability.PUBLIC_FREE,
            license=None,  # type: ignore[arg-type]
            temporal_coverage="",
            geographic_coverage="",
            indicator_description="",
        )
        score = DataSourceCandidateRegistry("test").score_candidate(c)
        # None should be treated like empty string → ~0.4 (unknown)
        assert 0.3 <= score.license_openness <= 0.5


# ─── Ranking ──────────────────────────────────────────────────────────────────


def _mk(name: str, avail: SourceAvailability, license_: str, preset: str = "neutral") -> DataSourceCandidate:
    """Helper: build candidate with predictable score profile.

    preset:
        - "neutral":  all sub-scores 0.5 (default)
        - "high":     coverage/indicator/credibility = 1.0
        - "low":      coverage/indicator/credibility = 0.1
    """
    if preset == "high":
        sub = {"coverage_match": 1.0, "indicator_fit": 1.0, "credibility": 1.0}
    elif preset == "low":
        sub = {"coverage_match": 0.1, "indicator_fit": 0.1, "credibility": 0.1}
    else:
        sub = {"coverage_match": 0.5, "indicator_fit": 0.5, "credibility": 0.5}
    return DataSourceCandidate(
        name=name,
        url=f"http://{name}",
        availability=avail,
        license=license_,
        temporal_coverage="2010–2023",
        geographic_coverage="China",
        indicator_description=f"indicator for {name}",
        score=CandidateScore(
            availability=0.0,  # placeholder; registry auto-overrides from availability
            license_openness=0.0,  # placeholder; registry auto-overrides from license
            coverage_match=sub["coverage_match"],
            indicator_fit=sub["indicator_fit"],
            credibility=sub["credibility"],
        ),
    )


class TestRanking:
    def test_sorts_descending_by_weighted_total(self):
        reg = DataSourceCandidateRegistry("research")
        a = _mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high")
        b = _mk("B", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "neutral")
        c = _mk("C", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low")
        for x in (a, b, c):
            reg.add_candidate(x)

        result = reg.rank()
        scores = [cand.score.weighted_total for cand in result.candidates]
        assert scores == sorted(scores, reverse=True)
        # High > neutral > low
        assert result.candidates[0].name == "A"
        assert result.candidates[2].name == "C"

    def test_unavailable_does_not_dominate(self):
        # An UNAVAILABLE candidate (availability=0.0) should rank below any viable
        reg = DataSourceCandidateRegistry("research")
        reg.add_candidate(_mk("dead", SourceAvailability.UNAVAILABLE, "CC BY 4.0", "high"))
        reg.add_candidate(_mk("alive", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low"))
        result = reg.rank()
        assert result.candidates[0].name == "alive"
        assert result.candidates[0].score.availability == pytest.approx(1.0)

    def test_empty_registry_returns_empty_result(self):
        reg = DataSourceCandidateRegistry("nothing")
        result = reg.rank()
        assert result.candidates == []
        assert result.recommended is None
        assert result.requires_user_decision is False

    def test_recommended_is_top_ranked(self):
        reg = DataSourceCandidateRegistry("research")
        reg.add_candidate(_mk("Lo", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low"))
        reg.add_candidate(_mk("Hi", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high"))
        result = reg.rank()
        assert result.recommended is not None
        assert result.recommended.name == "Hi"

    def test_rank_is_idempotent(self):
        reg = DataSourceCandidateRegistry("research")
        reg.add_candidate(_mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        reg.add_candidate(_mk("B", SourceAvailability.PUBLIC_FREE, "MIT"))
        first = reg.rank()
        second = reg.rank()
        assert [c.name for c in first.candidates] == [c.name for c in second.candidates]
        assert first.summary_message == second.summary_message


# ─── requires_user_decision semantics ─────────────────────────────────────────


class TestRequiresUserDecision:
    def test_true_with_two_viable_candidates(self):
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        reg.add_candidate(_mk("B", SourceAvailability.PUBLIC_REGISTER, "unknown"))
        result = reg.rank()
        assert result.requires_user_decision is True

    def test_false_when_only_one_viable(self):
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("alive", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        reg.add_candidate(_mk("dead1", SourceAvailability.UNAVAILABLE, "CC BY 4.0"))
        reg.add_candidate(_mk("dead2", SourceAvailability.UNAVAILABLE, "MIT"))
        result = reg.rank()
        assert result.requires_user_decision is False
        # recommended must still be the only viable one
        assert result.recommended is not None
        assert result.recommended.name == "alive"

    def test_false_when_zero_viable(self):
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("dead1", SourceAvailability.UNAVAILABLE, "CC BY 4.0"))
        reg.add_candidate(_mk("dead2", SourceAvailability.UNAVAILABLE, "MIT"))
        result = reg.rank()
        assert result.requires_user_decision is False

    def test_recommended_top_but_user_decision_required(self):
        # Even when a clear winner exists, requires_user_decision must stay True
        # because >1 viable candidate → never auto-commit.
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("clear_winner", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high"))
        reg.add_candidate(_mk("also_ok", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low"))
        result = reg.rank()
        assert result.requires_user_decision is True
        assert result.recommended.name == "clear_winner"


# ─── build_registry convenience ───────────────────────────────────────────────


class TestBuildRegistryConvenience:
    def test_returns_result(self):
        candidates = [
            _mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"),
            _mk("B", SourceAvailability.PUBLIC_REGISTER, "unknown"),
        ]
        result = build_registry("some research need", candidates)
        assert isinstance(result, CandidateRegistryResult)
        assert result.research_need == "some research need"

    def test_build_registry_ranked(self):
        candidates = [
            _mk("low", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low"),
            _mk("high", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high"),
        ]
        result = build_registry("r", candidates)
        assert result.candidates[0].name == "high"
        assert result.requires_user_decision is True

    def test_build_registry_empty(self):
        result = build_registry("r", [])
        assert result.candidates == []
        assert result.requires_user_decision is False


# ─── print_report runs without error ──────────────────────────────────────────


class TestPrintReport:
    def test_print_report_with_two_viable(self, capsys):
        reg = DataSourceCandidateRegistry("test research")
        reg.add_candidate(_mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high"))
        reg.add_candidate(_mk("B", SourceAvailability.PUBLIC_REGISTER, "unknown", "neutral"))
        # Should not raise
        reg.print_report()
        captured = capsys.readouterr().out
        assert "A" in captured
        assert "B" in captured
        assert "需用户决策" in captured or "user decision" in captured.lower()

    def test_print_report_with_explicit_result(self, capsys):
        reg = DataSourceCandidateRegistry("test")
        reg.add_candidate(_mk("only", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high"))
        reg.add_candidate(_mk("dead", SourceAvailability.UNAVAILABLE, "CC BY 4.0"))
        result = reg.rank()
        # Build a fresh registry to call print_report with explicit arg
        reg2 = DataSourceCandidateRegistry("test")
        reg2.print_report(result)
        captured = capsys.readouterr().out
        assert "only" in captured

    def test_print_report_empty_registry_does_not_crash(self, capsys):
        reg = DataSourceCandidateRegistry("nothing")
        # No candidates → no crash
        reg.print_report()
        out = capsys.readouterr().out
        assert "数据源候选评分卡" in out or "Candidate Scorecard" in out or "无候选" in out

    def test_print_report_no_exception_via_redirect(self):
        # Belt-and-suspenders: also try via redirect_stdout
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("x", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            reg.print_report()
        out = buf.getvalue()
        assert isinstance(out, str)
        assert len(out) > 50  # at least some output


# ─── DataSourceCandidate dataclass basics ─────────────────────────────────────


class TestCandidateDataclass:
    def test_required_only(self):
        c = DataSourceCandidate(
            name="X",
            url="http://x",
            availability=SourceAvailability.PUBLIC_FREE,
            license="CC BY 4.0",
            temporal_coverage="2010–",
            geographic_coverage="CN",
            indicator_description="x",
        )
        assert c.name == "X"
        assert c.citation == ""
        assert c.notes == ""
        assert c.score is None

    def test_with_score(self):
        sc = CandidateScore(0.5, 0.5, 0.5, 0.5, 0.5)
        c = DataSourceCandidate(
            name="X",
            url="http://x",
            availability=SourceAvailability.PUBLIC_FREE,
            license="CC BY 4.0",
            temporal_coverage="",
            geographic_coverage="",
            indicator_description="",
            citation="doi:10.x/y",
            notes="extra",
            score=sc,
        )
        assert c.score is sc
        assert c.citation == "doi:10.x/y"


# ─── add_candidate dedup by name ──────────────────────────────────────────────


class TestAddCandidate:
    def test_add_same_name_replaces(self):
        reg = DataSourceCandidateRegistry("r")
        first = _mk("Dup", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "low")
        second = _mk("Dup", SourceAvailability.PUBLIC_FREE, "CC BY 4.0", "high")
        reg.add_candidate(first)
        reg.add_candidate(second)
        # Only one candidate with name "Dup"
        names = [c.name for c in reg._candidates]
        assert names.count("Dup") == 1
        # The second (high) should have replaced the first
        assert reg._candidates[0].score.weighted_total > first.score.weighted_total

    def test_add_distinct_names(self):
        reg = DataSourceCandidateRegistry("r")
        reg.add_candidate(_mk("A", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        reg.add_candidate(_mk("B", SourceAvailability.PUBLIC_FREE, "CC BY 4.0"))
        assert len(reg._candidates) == 2
