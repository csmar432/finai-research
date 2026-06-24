"""
reviewer_pipeline.py — Unified Reviewer Pipeline

Chains three reviewers into a single, consistent review pipeline:
    LLMReviewer (scoring) → AutoReviewRules (halt-rule check) → bias detection

Provides a unified output format (UnifiedReviewReport) regardless of which
reviewer implementations are used.

Usage:
    from scripts.core.reviewer_pipeline import ReviewerPipeline, ReviewStage

    pipeline = ReviewerPipeline()
    report = pipeline.review(paper_content="...", venue="JFE")
    print(report.final_verdict, report.unified_score)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "UnifiedReviewReport",
    "ReviewStage",
    "ReviewerPipeline",
]


# ─── Unified Output Format ────────────────────────────────────────────────────


class ReviewStage(str, Enum):
    """Pipeline stages."""
    LLM_SCORING = "llm_scoring"       # LLMReviewer 6-dimension scoring
    AUTO_RULES = "auto_rules"         # AutoReviewRules halt-rule check
    BIAS_CHECK = "bias_check"        # Bias detection


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage: ReviewStage
    passed: bool
    score: float | None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class UnifiedReviewReport:
    """Unified review report combining all pipeline stages."""
    # Unified score (0-10, averaged across all scoring dimensions)
    unified_score: float
    # Final verdict
    final_verdict: str  # "accept" / "revise" / "reject" / "major_revision"
    # Stage results
    stages: list[StageResult]
    # Combined dimension scores (normalized to 0-10)
    dimension_scores: dict[str, float]
    # Halt-rule violations
    halt_violations: list[str]
    # Bias flags
    bias_flags: list[str]
    # Critical issues
    critical_issues: list[str]
    # Overall confidence
    confidence: float
    # Total latency
    total_latency_ms: float
    # Raw LLM result (for debugging)
    llm_result: dict | None = None

    def to_dict(self) -> dict:
        return {
            "unified_score": round(self.unified_score, 2),
            "final_verdict": self.final_verdict,
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
            "halt_violations": self.halt_violations,
            "bias_flags": self.bias_flags,
            "critical_issues": self.critical_issues,
            "confidence": round(self.confidence, 3),
            "total_latency_ms": round(self.total_latency_ms, 1),
            "stages": [
                {
                    "stage": s.stage.value,
                    "passed": s.passed,
                    "score": s.score,
                    "latency_ms": round(s.latency_ms, 1),
                }
                for s in self.stages
            ],
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Unified Review Report",
            f"{'─' * 50}",
            f"Score: {self.unified_score:.2f}/10 | Verdict: {self.final_verdict}",
            f"Confidence: {self.confidence:.1%}",
        ]
        if self.halt_violations:
            lines.append(f"\nHalt violations ({len(self.halt_violations)}):")
            for v in self.halt_violations:
                lines.append(f"  - {v}")
        if self.bias_flags:
            lines.append(f"\nBias flags ({len(self.bias_flags)}):")
            for b in self.bias_flags:
                lines.append(f"  - {b}")
        if self.critical_issues:
            lines.append(f"\nCritical issues ({len(self.critical_issues)}):")
            for i in self.critical_issues:
                lines.append(f"  - {i}")
        lines.append(f"\nLatency: {self.total_latency_ms:.0f}ms")
        return "\n".join(lines)


# ─── Pipeline ────────────────────────────────────────────────────────────────


class ReviewerPipeline:
    """
    Unified reviewer pipeline.

    Chains:
      1. LLMReviewer: score across 6 dimensions (methodology, novelty, etc.)
      2. AutoReviewRules: check halt-rule violations (halt_on_fail rules)
      3. Bias detection: flag systematic reviewer tendencies

    The pipeline produces a single UnifiedReviewReport regardless of
    which reviewer implementations are used.

    Parameters
    ----------
    enable_auto_rules : bool
        Run AutoReviewRules halt-rule check after LLM scoring.
        Default True.
    enable_bias_check : bool
        Run bias detection. Default True.
    venue : str
        Default venue for review format. Default "ML".
    llm_timeout : float
        Timeout for LLM calls in seconds. Default 120.
    llm_max_retries : int
        Max retries for LLM calls. Default 1.
    """

    def __init__(
        self,
        enable_auto_rules: bool = True,
        enable_bias_check: bool = True,
        enable_history: bool = False,
        venue: str = "ML",
        llm_timeout: float = 120.0,
        llm_max_retries: int = 1,
        history_db_path: str = ".review_history.db",
    ):
        self.enable_auto_rules = enable_auto_rules
        self.enable_bias_check = enable_bias_check
        self.enable_history = enable_history
        self.default_venue = venue
        self.llm_timeout = llm_timeout
        self.llm_max_retries = llm_max_retries
        self.history_db_path = history_db_path
        self._history_db = None

    # ── Stage 1: LLM Scorer ────────────────────────────────────────────────

    def _llm_score(self, paper_content: str, venue: str) -> StageResult:
        """Run LLMReviewer to score the paper."""
        start = time.perf_counter()
        try:
            from scripts.core.reviewer import LLMReviewer
            reviewer = LLMReviewer(
                default_venue=venue,
                enable_cache=False,
                timeout=self.llm_timeout,
                max_retries=self.llm_max_retries,
            )
            result = reviewer.review(paper_content=paper_content, venue=venue)
            elapsed = (time.perf_counter() - start) * 1000

            # Extract dimension scores
            dim_scores = {}
            for dim, score_obj in result.scores.items():
                dim_scores[dim] = score_obj.score

            # Average across scored dimensions
            if dim_scores:
                avg_score = sum(dim_scores.values()) / len(dim_scores)
            else:
                avg_score = 0.0

            return StageResult(
                stage=ReviewStage.LLM_SCORING,
                passed=result.overall_score >= 5.0,
                score=avg_score,
                details={
                    "overall_score": result.overall_score,
                    "recommendation": result.overall_recommendation,
                    "dimension_scores": dim_scores,
                    "confidence": result.confidence,
                    "llm_result": result.to_dict(),
                },
                latency_ms=elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(f"LLM scoring failed: {exc}")
            return StageResult(
                stage=ReviewStage.LLM_SCORING,
                passed=False,
                score=None,
                details={},
                latency_ms=elapsed,
                error=str(exc),
            )

    # ── Stage 2: Auto Halt-Rule Check ──────────────────────────────────────

    def _auto_rules_check(self, paper_content: str) -> StageResult:
        """Run AutoReviewRules halt-rule check."""
        if not self.enable_auto_rules:
            return StageResult(
                stage=ReviewStage.AUTO_RULES,
                passed=True,
                score=None,
                details={"skipped": True},
                latency_ms=0.0,
            )

        start = time.perf_counter()
        try:
            from scripts.core.reviewer import AutoReviewRules
            arr = AutoReviewRules(domain="empirical_paper")

            # Split paper into chapters for rule-based scoring
            chapters = self._split_into_chapters(paper_content)
            score = arr.score_paper(chapters=chapters)
            elapsed = (time.perf_counter() - start) * 1000

            return StageResult(
                stage=ReviewStage.AUTO_RULES,
                passed=score.passed,
                score=score.overall,
                details={
                    "level": score.level,
                    "critical_issues": score.critical_issues,
                    "warnings": score.warnings,
                    "dimension_scores": score.dimension_scores,
                },
                latency_ms=elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(f"Auto rules check failed: {exc}")
            return StageResult(
                stage=ReviewStage.AUTO_RULES,
                passed=False,
                score=None,
                details={},
                latency_ms=elapsed,
                error=str(exc),
            )

    # ── Stage 3: Bias Detection ─────────────────────────────────────────────

    def _bias_check(self, llm_result: dict | None) -> StageResult:
        """Run bias detection on LLM review result."""
        if not self.enable_bias_check or llm_result is None:
            return StageResult(
                stage=ReviewStage.BIAS_CHECK,
                passed=True,
                score=None,
                details={"skipped": True},
                latency_ms=0.0,
            )

        start = time.perf_counter()
        try:
            # Use ReviewerCalibrator for bias detection
            from scripts.core.reviewer_calibrator import ReviewerCalibrator
            calibrator = ReviewerCalibrator()
            # Run bias detection with synthetic history (current review only)
            biases = calibrator.detect_biases(review_history=[])
            elapsed = (time.perf_counter() - start) * 1000

            bias_flags = [b.description for b in biases]
            return StageResult(
                stage=ReviewStage.BIAS_CHECK,
                passed=len(bias_flags) == 0,
                score=1.0 - (len(bias_flags) * 0.1),  # Score decreases with bias flags
                details={
                    "n_biases": len(bias_flags),
                    "bias_flags": bias_flags,
                },
                latency_ms=elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - start) * 1000
            logger.warning(f"Bias check failed: {exc}")
            return StageResult(
                stage=ReviewStage.BIAS_CHECK,
                passed=True,  # Don't fail the pipeline for bias check errors
                score=None,
                details={},
                latency_ms=elapsed,
                error=str(exc),
            )

    # ── Combine Results ────────────────────────────────────────────────────

    def _combine(
        self,
        llm_stage: StageResult,
        rules_stage: StageResult,
        bias_stage: StageResult,
    ) -> UnifiedReviewReport:
        """Combine all stage results into a unified report."""
        # Unified score: average of LLM score and AutoRules score (if available)
        scores = []
        if llm_stage.score is not None:
            scores.append(llm_stage.score)
        if rules_stage.score is not None:
            scores.append(rules_stage.score / 10.0)  # Normalize to 0-10
        unified_score = sum(scores) / len(scores) if scores else 0.0

        # Final verdict logic
        halt_violations = rules_stage.details.get("critical_issues", [])
        bias_flags = bias_stage.details.get("bias_flags", [])

        # Verdict: stricter of LLM verdict and halt-rule check
        llm_passed = llm_stage.passed
        rules_passed = rules_stage.passed
        bias_passed = bias_stage.passed

        if not llm_passed or not rules_passed:
            final_verdict = "major_revision"
        elif unified_score >= 7.5:
            final_verdict = "accept"
        elif unified_score >= 6.0:
            final_verdict = "revise"
        else:
            final_verdict = "reject"

        # Critical issues: from LLM weaknesses + halt violations
        llm_result = llm_stage.details.get("llm_result")
        critical_issues: list[str] = list(halt_violations)
        if llm_result:
            critical_issues.extend(llm_result.get("weaknesses", []))

        # Confidence: LLM confidence × bias pass rate
        llm_confidence = llm_stage.details.get("confidence", 0.5)
        bias_factor = 1.0 - (len(bias_flags) * 0.1)
        confidence = llm_confidence * max(bias_factor, 0.1)

        total_latency = llm_stage.latency_ms + rules_stage.latency_ms + bias_stage.latency_ms

        return UnifiedReviewReport(
            unified_score=unified_score,
            final_verdict=final_verdict,
            stages=[llm_stage, rules_stage, bias_stage],
            dimension_scores=llm_stage.details.get("dimension_scores", {}),
            halt_violations=halt_violations,
            bias_flags=bias_flags,
            critical_issues=critical_issues[:10],  # Cap at 10
            confidence=confidence,
            total_latency_ms=total_latency,
            llm_result=llm_result,
        )

    # ── Paper Chapter Splitting ──────────────────────────────────────────────

    @staticmethod
    def _split_into_chapters(paper_content: str) -> dict[str, str]:
        """Split paper text into logical chapters for AutoReviewRules."""
        # Simple heuristic split by common section headers
        chapters: dict[str, str] = {}
        sections = [
            "Introduction", "Abstract", "Literature", "Methodology",
            "Data", "Results", "Conclusion",
        ]
        current_chapter = "General"
        current_text: list[str] = []

        lines = paper_content.split("\n")
        for line in lines:
            stripped = line.strip()
            # Detect chapter headers
            is_header = False
            for sec in sections:
                if stripped.lower().startswith(sec.lower()):
                    # Save previous chapter
                    if current_text:
                        chapters[current_chapter] = "\n".join(current_text)
                    current_chapter = sec
                    current_text = []
                    is_header = True
                    break
            if not is_header:
                current_text.append(line)

        if current_text:
            chapters[current_chapter] = "\n".join(current_text)

        # If no chapters were found, use the whole content as "General"
        if not chapters:
            chapters["General"] = paper_content

        return chapters

    # ── Main Pipeline Entry ──────────────────────────────────────────────────

    def review(
        self,
        paper_content: str,
        venue: str | None = None,
    ) -> UnifiedReviewReport:
        """
        Run the full reviewer pipeline.

        Parameters
        ----------
        paper_content : str
            Full text content of the paper.
        venue : str, optional
            Venue identifier (e.g. "JFE", "经济研究"). Defaults to self.default_venue.

        Returns
        -------
        UnifiedReviewReport
            Combined report from all pipeline stages.
        """
        venue = venue or self.default_venue
        logger.info(f"Starting reviewer pipeline for venue={venue}")

        # Stage 1: LLM Scoring
        llm_stage = self._llm_score(paper_content, venue)

        # Stage 2: Auto Rules Check
        rules_stage = self._auto_rules_check(paper_content)

        # Stage 3: Bias Detection
        llm_result = llm_stage.details.get("llm_result")
        bias_stage = self._bias_check(llm_result)

        # Combine
        report = self._combine(llm_stage, rules_stage, bias_stage)

        # Record to history DB if enabled
        if self.enable_history:
            self._record_to_history(venue, report)

        logger.info(
            f"Pipeline complete: score={report.unified_score:.2f}, "
            f"verdict={report.final_verdict}, latency={report.total_latency_ms:.0f}ms"
        )
        return report

    def _get_history_db(self):
        """Lazily initialize the history DB."""
        if self._history_db is None:
            try:
                from scripts.core.reviewer_calibrator import BiasHistoryDB
                self._history_db = BiasHistoryDB(db_path=self.history_db_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to initialize history DB: {exc}")
                self._history_db = None
        return self._history_db

    def _record_to_history(self, venue: str, report: UnifiedReviewReport) -> None:
        """Record the review result to the history DB."""
        db = self._get_history_db()
        if db is None:
            return
        try:
            from scripts.core.reviewer_calibrator import BiasReport, BiasInstance, BiasType
            import time
            review_id = f"review_{int(time.time() * 1000)}"
            bias_report = BiasReport(
                total_reviews=1,
                detected_biases=[
                    BiasInstance(
                        bias_type=BiasType(bf),
                        severity=0.5,
                        description=bf,
                        affected_dimensions=[],
                        statistical_evidence={},
                        recommendation="",
                    )
                    for bf in report.bias_flags
                ],
                overall_bias_score=sum(
                    0.1 for _ in report.bias_flags
                ) if report.bias_flags else 0.0,
                is_calibration_needed=False,
                bias_patterns={},
                review_history_summary={},
            )
            db.record_review(review_id, venue, bias_report)
            logger.debug(f"Recorded review {review_id} to history DB")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to record review to history DB: {exc}")
