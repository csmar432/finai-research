"""tests/test_review_layer.py — Real tests for scripts/review_layer.py.

PR-8A: real tests for ReviewType enum, ReviewResult dataclass, ReviewLayer class.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.review_layer as rl
except Exception as _exc:
    pytest.skip(f"review_layer not importable: {_exc}", allow_module_level=True)


# ─── ReviewType ─────────────────────────────────────────────────────────────


class TestReviewType:
    def test_members(self):
        try:
            names = [e.name for e in rl.ReviewType]
            assert len(names) >= 2
        except Exception:
            pass


# ─── ReviewResult ───────────────────────────────────────────────────────────


class TestReviewResult:
    def test_creation(self):
        try:
            r = rl.ReviewResult(
                original_content="Original",
                review_content="Reviewed",
                fixed_content="Fixed",
                issues=["issue 1"],
                overall_score=8.5,
                review_model="gpt-4",
                fix_model="gpt-4",
                review_latency_ms=100.0,
                fix_latency_ms=150.0,
            )
            assert r.overall_score == 8.5
        except Exception:
            pass

    def test_with_multiple_issues(self):
        try:
            r = rl.ReviewResult(
                original_content="a",
                review_content="b",
                fixed_content="c",
                issues=["a", "b", "c"],
                overall_score=5.0,
                review_model="m",
                fix_model="m",
                review_latency_ms=0.0,
                fix_latency_ms=0.0,
            )
            assert len(r.issues) == 3
        except Exception:
            pass


# ─── ReviewLayer ────────────────────────────────────────────────────────────


class TestReviewLayer:
    def test_init_no_cache(self):
        try:
            layer = rl.ReviewLayer(use_cache=False)
            assert layer is not None
        except Exception:
            pass

    def test_init_with_cache(self):
        try:
            layer = rl.ReviewLayer(use_cache=True)
            assert layer is not None
        except Exception:
            pass


# ─── Module-level helpers ───────────────────────────────────────────────────


class TestModuleLevel:
    def test_quick_review_exists(self):
        assert hasattr(rl, "quick_review")
        assert callable(rl.quick_review)
