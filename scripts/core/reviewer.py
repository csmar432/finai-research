"""
scripts/core/reviewer.py
=======================
Consolidated reviewer module — single import entry point.

The following reviewer modules have been consolidated into this file:
  - llm_reviewer.py       → LLMReviewer, ReviewResult, ReviewScore, CalibrationResult
  - reviewer_pipeline.py   → ReviewerPipeline, ReviewStage, UnifiedReviewReport
  - dual_reviewer.py      → DualReviewer, ReviewDimension, DimensionScore, ReviewReport
  - auto_review_rules.py  → AutoReviewRules, AutoReviewRule, AutoReviewScore

The original files are kept as aliases for backward compatibility.
Do not add new code here — add it to the canonical files above.

Usage:
    from scripts.core.reviewer import (
        LLMReviewer,
        ReviewerPipeline,
        DualReviewer,
        AutoReviewRules,
    )

Canonical files (in order of precedence):
    1. scripts/core/llm_reviewer.py       — primary LLM reviewer (most complete)
    2. scripts/core/reviewer_pipeline.py   — pipeline orchestration
    3. scripts/core/dual_reviewer.py       — dual-reviewer pattern
    4. scripts/core/auto_review_rules.py   — rule-based auto review
"""

from scripts.core.llm_reviewer import (
    LLMReviewer,
    ReviewResult,
    ReviewScore,
    CalibrationResult,
    CalibrationDataset,
    VENUE_CONFIGS as REVIEWER_VENUE_CONFIGS,
    _build_calibration_samples,
)
from scripts.core.reviewer_pipeline import (
    ReviewerPipeline,
    ReviewStage,
    StageResult,
    UnifiedReviewReport,
)
from scripts.core.dual_reviewer import (
    DualReviewer,
    ReviewDimension,
    DimensionScore,
    ReviewReport,
)
from scripts.core.auto_review_rules import (
    AutoReviewRules,
    AutoReviewRule,
    AutoReviewScore,
)

__all__ = [
    # llm_reviewer
    "LLMReviewer",
    "ReviewResult",
    "ReviewScore",
    "CalibrationResult",
    "CalibrationDataset",
    "VENUE_CONFIGS",
    "REVIEWER_VENUE_CONFIGS",
    "_build_calibration_samples",
    # reviewer_pipeline
    "ReviewerPipeline",
    "ReviewStage",
    "StageResult",
    "UnifiedReviewReport",
    # dual_reviewer
    "DualReviewer",
    "ReviewDimension",
    "DimensionScore",
    "ReviewReport",
    # auto_review_rules
    "AutoReviewRules",
    "AutoReviewRule",
    "AutoReviewScore",
]
