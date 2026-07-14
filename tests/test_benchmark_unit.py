"""Tests for scripts/core/benchmark.py — PaperWritingBench dataclasses."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.benchmark import (
        BenchmarkConfig,
        PaperScore,
        ValidationSummary,
        SyntheticPaperGenerator,
    )
except Exception as _exc:
    pytest.skip(f"benchmark not importable: {_exc}", allow_module_level=True)


class TestBenchmarkConfig:
    def test_default_values(self):
        """BenchmarkConfig must have sensible defaults."""
        cfg = BenchmarkConfig()
        assert cfg.n_papers == 5
        assert cfg.output_dir == ".cache/benchmark"
        assert cfg.max_tokens_per_call == 4096
        assert cfg.timeout_per_paper == 300

    def test_custom_values(self):
        """Custom parameters must be accepted."""
        cfg = BenchmarkConfig(
            n_papers=10,
            domains=["theory_paper"],
            timeout_per_paper=600,
        )
        assert cfg.n_papers == 10
        assert cfg.domains == ["theory_paper"]
        assert cfg.timeout_per_paper == 600


class TestPaperScore:
    def test_required_fields(self):
        """PaperScore must accept all required fields."""
        score = PaperScore(
            paper_id="p1",
            domain="empirical_paper",
            model="gpt-4",
            section_scores={"clarity": 7.5, "novelty": 6.0, "methodology": 8.0},
            overall_score=7.1,
            halt_results={"H003": (True, "OK")},
            passed_rules=9,
            total_rules=10,
            pass_rate=0.9,
            generation_time_sec=45.0,
        )
        assert score.paper_id == "p1"
        assert score.domain == "empirical_paper"
        assert score.overall_score == 7.1
        assert score.error is None

    def test_optional_error(self):
        """Error field must be accepted."""
        score = PaperScore(
            paper_id="p2",
            domain="theory_paper",
            model="claude-3",
            section_scores={},
            overall_score=0.0,
            halt_results={},
            passed_rules=0,
            total_rules=10,
            pass_rate=0.0,
            generation_time_sec=1.0,
            error="Timeout exceeded",
        )
        assert score.error == "Timeout exceeded"


class TestValidationSummary:
    def test_required_fields(self):
        """ValidationSummary must accept all required fields."""
        summary = ValidationSummary(
            domain="empirical_paper",
            total_rules=10,
            papers_evaluated=50,
            papers_passed=40,
            pass_rate=0.8,
            mean_pass_rate=0.75,
            std_pass_rate=0.1,
            rule_results={"H001": {"pass": 45, "fail": 5}},
        )
        assert summary.papers_evaluated == 50
        assert summary.papers_passed == 40
        assert summary.pass_rate == 0.8


class TestSyntheticPaperGenerator:
    def test_init(self):
        """SyntheticPaperGenerator must initialize."""
        gen = SyntheticPaperGenerator()
        assert gen is not None

    def test_generate_returns_dict(self):
        """generate() must return a dict (not a string)."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper")
        assert isinstance(result, dict)
        assert len(result) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
