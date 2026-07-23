"""Tests for scripts/research_framework/negative_result_handler.py"""

from __future__ import annotations

from scripts.research_framework.negative_result_handler import (
    SIG_NULL,
    SIG_STRONG,
    SIG_WEAK,
    NegativeResultVerdict,
    assess_result,
    classify_significance,
)


def test_classify_significance():
    assert classify_significance(0.01) == SIG_STRONG
    assert classify_significance(0.049) == SIG_STRONG
    assert classify_significance(0.05) == SIG_WEAK
    assert classify_significance(0.09) == SIG_WEAK
    assert classify_significance(0.10) == SIG_NULL
    assert classify_significance(0.80) == SIG_NULL


def test_null_result_blocks_writing_when_nothing_done():
    # Mirrors the audited Codex paper: p=0.804, TWFE, nothing supplementary done.
    verdict = assess_result(
        baseline_p=0.804,
        baseline_coef=-0.26,
        did_type="twfe",
        is_staggered=True,
    )
    assert isinstance(verdict, NegativeResultVerdict)
    assert verdict.significance == SIG_NULL
    assert verdict.should_block_writing is True
    # A4/A5/C2/A6/C5 must be present
    codes = {a.code for a in verdict.required_actions}
    assert {"A4", "A5", "C2", "A6", "C5"}.issubset(codes)


def test_null_result_unblocks_when_all_done():
    verdict = assess_result(
        baseline_p=0.804,
        baseline_coef=-0.26,
        did_type="twfe",
        is_staggered=True,
        has_modern_did=True,
        has_mechanism=True,
        has_heterogeneity=True,
        has_spatial=True,
        has_placebo=True,
    )
    assert verdict.should_block_writing is False
    assert verdict.missing_actions() == []


def test_modern_did_type_autodetected():
    # did_type="cs" should count as modern DID → A4 auto-satisfied
    verdict = assess_result(
        baseline_p=0.80,
        baseline_coef=-0.26,
        did_type="cs",
        is_staggered=True,
        has_mechanism=True,
        has_heterogeneity=True,
        has_spatial=True,
        has_placebo=True,
    )
    a4 = [a for a in verdict.required_actions if a.code == "A4"]
    assert a4 and a4[0].done is True
    assert verdict.should_block_writing is False


def test_non_staggered_skips_a4():
    verdict = assess_result(
        baseline_p=0.80,
        baseline_coef=-0.26,
        did_type="twfe",
        is_staggered=False,
    )
    codes = {a.code for a in verdict.required_actions}
    assert "A4" not in codes


def test_strong_result_does_not_block():
    verdict = assess_result(
        baseline_p=0.001,
        baseline_coef=0.5,
        did_type="twfe",
        is_staggered=True,
    )
    assert verdict.significance == SIG_STRONG
    assert verdict.should_block_writing is False


def test_forbidden_narratives_for_null():
    verdict = assess_result(baseline_p=0.80, baseline_coef=-0.26)
    assert verdict.forbidden_narratives
    assert any("显著促进" in n for n in verdict.forbidden_narratives)


def test_weak_result_narratives():
    verdict = assess_result(
        baseline_p=0.06,
        baseline_coef=1.2,
        did_type="twfe",
        is_staggered=True,
    )
    assert verdict.significance == SIG_WEAK
    assert verdict.allowed_narratives
    assert verdict.forbidden_narratives


def test_render_smoke():
    verdict = assess_result(baseline_p=0.804, baseline_coef=-0.26)
    text = verdict.render()
    assert "负显著结果处理器" in text
    assert "A5" in text


def test_summary_message():
    verdict = assess_result(baseline_p=0.804, baseline_coef=-0.26)
    assert "阻止写作" in verdict.summary_message
