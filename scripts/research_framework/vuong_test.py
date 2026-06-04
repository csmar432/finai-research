"""Vuong Non-Nested Hypothesis Tests for Model Comparison.

This module re-exports the canonical implementation from `vuong_kob.py`
and provides English-only convenience wrappers for the research framework.

Usage:
    from scripts.research_framework.vuong_test import VuongTest, VuongResult

    # Use the canonical implementation (Chinese+English, from vuong_kob.py)
    vt = VuongTest(name1="DID", name2="RDD")
    result = vt.fit(model_1, model_2)

    # Convenience wrappers
    result = vuong_did_vs_rdd(did_fit, rdd_fit)
    result = vuong_linear_vs_logit(ols_fit, logit_fit)

Note: The canonical VuongTest implementation lives in `vuong_kob.py`.
This module provides an English-language interface and re-exports the same class.
"""

from __future__ import annotations

from scripts.research_framework.vuong_kob import (
    VuongResult,
    VuongTest,
    vuong_did_vs_rdd,
    vuong_linear_vs_logit,
)

__all__ = [
    "VuongTest",
    "VuongResult",
    "ClarkeTest",
    "vuong_did_vs_rdd",
    "vuong_linear_vs_logit",
    "vuong_different_controls",
    "vuong_different_samples",
]


def vuong_different_controls(model_a, model_b, name_a: str = "Model_A", name_b: str = "Model_B"):
    """Compare two models with different control variable sets."""
    return VuongTest(name_a, name_b).fit(model_a, model_b)


def vuong_different_samples(model_1, model_2, name_1: str = "Sample_1", name_2: str = "Sample_2"):
    """Compare the same model estimated on different samples."""
    return VuongTest(name_1, name_2).fit(model_1, model_2)


# Re-export ClarkeTest from vuong_kob (private helper, available for advanced use)
from scripts.research_framework.vuong_kob import _clarke_test as ClarkeTest  # noqa: F401, E402
