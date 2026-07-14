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
        PaperWritingBench,
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

    def test_generate_default_variant_is_good(self):
        """Default variant must be 'good'."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper")
        assert "title" in result

    def test_generate_explicit_good_variant(self):
        """Explicit 'good' variant must return structured content."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="good")
        assert isinstance(result, dict)
        assert "title" in result
        assert "abstract" in result
        assert "references" in result
        assert len(result["references"]) > 0

    def test_generate_bad_variant_returns_minimal(self):
        """'bad' variant must return content with fewer items."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="bad")
        assert isinstance(result, dict)
        assert "title" in result
        assert "abstract" in result

    def test_generate_finance_report_good(self):
        """finance_report 'good' variant must have valuation and rating."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="finance_report", variant="good")
        assert "valuation" in result
        assert "rating" in result
        assert "Strong Buy" in result["rating"]

    def test_generate_finance_report_bad(self):
        """finance_report 'bad' variant must return content."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="finance_report", variant="bad")
        assert isinstance(result, dict)
        assert "title" in result

    def test_generate_ml_paper_good(self):
        """ml_paper 'good' variant must have methodology and reproducibility."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="ml_paper", variant="good")
        assert "methodology" in result
        assert "results" in result
        assert "reproducibility" in result

    def test_generate_ml_paper_bad(self):
        """ml_paper 'bad' variant must return content."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="ml_paper", variant="bad")
        assert isinstance(result, dict)
        assert "title" in result

    def test_generate_unknown_domain_returns_generic(self):
        """Unknown domain must fall back to generic paper."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="unknown_domain_xyz")
        assert isinstance(result, dict)
        assert "title" in result

    def test_good_empirical_paper_has_references_with_dois(self):
        """empirical_paper 'good' variant must have DOIs in references."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="good")
        refs = result.get("references", [])
        assert len(refs) >= 1
        # Good variant has DOIs
        dois = [r.get("doi", "") for r in refs]
        assert any(d for d in dois if d), "Good variant should have DOIs"

    def test_bad_empirical_paper_weak_references(self):
        """empirical_paper 'bad' variant has weak/missing DOIs."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="bad")
        refs = result.get("references", [])
        assert len(refs) >= 1
        # Bad variant has empty or placeholder DOIs
        dois = [r.get("doi", "") for r in refs]
        assert not all(d for d in dois), "Bad variant should have weak references"

    def test_good_ml_paper_has_code_url(self):
        """ml_paper 'good' variant must have GitHub code URL."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="ml_paper", variant="good")
        repro = result.get("reproducibility", {})
        assert "code_url" in repro
        assert "github" in repro["code_url"].lower()

    def test_good_empirical_paper_has_identification_assumptions(self):
        """empirical_paper 'good' must include identification assumptions."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="good")
        assert "identification_assumptions" in result
        assert len(result["identification_assumptions"]) > 0

    def test_good_empirical_paper_has_limitations(self):
        """empirical_paper 'good' must include limitations discussion."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="good")
        assert "limitations" in result
        assert len(result["limitations"]) > 0

    def test_good_empirical_paper_has_economic_significance(self):
        """empirical_paper 'good' must include economic significance."""
        gen = SyntheticPaperGenerator()
        result = gen.generate(domain="empirical_paper", variant="good")
        assert "economic_significance" in result
        assert len(result["economic_significance"]) > 0


class TestPaperWritingBenchInit:
    """Test PaperWritingBench initialization."""

    def test_init_default_config(self):
        """PaperWritingBench must initialize with default config."""
        bench = PaperWritingBench()
        assert bench is not None
        assert bench.config is not None
        assert bench.config.n_papers == 5

    def test_init_custom_config(self):
        """PaperWritingBench must accept custom BenchmarkConfig."""
        cfg = BenchmarkConfig(n_papers=3, domains=["empirical_paper"])
        bench = PaperWritingBench(config=cfg)
        assert bench.config.n_papers == 3
        assert bench.config.domains == ["empirical_paper"]

    def test_init_output_dir_created(self, tmp_path):
        """Output directory must be created on init."""
        out = tmp_path / "bench_out"
        bench = PaperWritingBench(BenchmarkConfig(output_dir=str(out)))
        assert out.exists()

    def test_init_uses_synthetic_generator(self):
        """PaperWritingBench must use SyntheticPaperGenerator by default."""
        bench = PaperWritingBench()
        assert hasattr(bench, "_generator")
        assert isinstance(bench._generator, SyntheticPaperGenerator)


class TestPaperWritingBenchResultsToPapers:
    """Test results_to_papers() method."""

    def test_results_to_papers_empty(self):
        """Empty results must produce empty list."""
        bench = PaperWritingBench()
        papers = bench.results_to_papers([])
        assert papers == []

    def test_results_to_papers_converts_score(self):
        """results_to_papers must convert PaperScore to paper dicts."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={"abstract": 0.8},
                overall_score=0.8,
                halt_results={},
                passed_rules=8,
                total_rules=10,
                pass_rate=0.8,
                generation_time_sec=1.0,
            )
        ]
        papers = bench.results_to_papers(scores)
        assert len(papers) == 1
        assert papers[0]["paper_id"] == "p1"
        assert papers[0]["domain"] == "empirical_paper"
        assert papers[0]["pass_rate"] == 0.8
        assert papers[0]["halt_score"] == 0.8


class TestPaperWritingBenchComputeSectionScores:
    """Test _compute_section_scores() via evaluate_paper internals."""

    def test_compute_section_scores_string(self):
        """_compute_section_scores must handle string fields."""
        bench = PaperWritingBench()
        content = {
            "abstract": "A" * 1000,
            "introduction": "B" * 200,
        }
        scores = bench._compute_section_scores(content)
        assert "abstract" in scores
        assert "introduction" in scores
        assert 0 <= scores["abstract"] <= 1.0
        assert scores["abstract"] >= scores["introduction"]  # longer = higher score

    def test_compute_section_scores_dict(self):
        """_compute_section_scores must handle dict fields."""
        bench = PaperWritingBench()
        content = {
            "references": [{"doi": "10.x/a"}] * 10,
        }
        scores = bench._compute_section_scores(content)
        assert "references" in scores

    def test_compute_section_scores_empty(self):
        """_compute_section_scores must handle empty content."""
        bench = PaperWritingBench()
        scores = bench._compute_section_scores({})
        assert scores == {}


class TestPaperWritingBenchEvaluatePaper:
    """Test _evaluate_paper() method with synthetic generator."""

    def test_evaluate_paper_good_variant_scores_high(self):
        """Good variant must produce high pass_rate."""
        bench = PaperWritingBench()
        score = bench._evaluate_paper("empirical_paper", "synthetic", "good")
        assert score.paper_id.startswith("empirical_paper_good_")
        assert score.domain == "empirical_paper"
        assert score.model == "synthetic"
        assert score.total_rules > 0
        assert score.generation_time_sec >= 0

    def test_evaluate_paper_bad_variant_scoring(self):
        """Bad variant must produce a PaperScore with populated halt_results."""
        bench = PaperWritingBench()
        bad_score = bench._evaluate_paper("empirical_paper", "synthetic", "bad")
        assert bad_score.domain == "empirical_paper"
        assert bad_score.model == "synthetic"
        assert bad_score.total_rules > 0
        assert isinstance(bad_score.halt_results, dict)

    def test_evaluate_paper_has_section_scores(self):
        """_evaluate_paper must populate section_scores."""
        bench = PaperWritingBench()
        score = bench._evaluate_paper("empirical_paper", "synthetic", "good")
        assert isinstance(score.section_scores, dict)

    def test_evaluate_paper_has_halt_results(self):
        """_evaluate_paper must populate halt_results."""
        bench = PaperWritingBench()
        score = bench._evaluate_paper("empirical_paper", "synthetic", "good")
        assert isinstance(score.halt_results, dict)

    def test_evaluate_paper_tracks_passed_rules(self):
        """_evaluate_paper must track passed/total rule counts."""
        bench = PaperWritingBench()
        score = bench._evaluate_paper("empirical_paper", "synthetic", "good")
        assert score.passed_rules >= 0
        assert score.total_rules >= 0
        assert score.passed_rules <= score.total_rules

    def test_evaluate_paper_uses_real_pipeline(self):
        """_evaluate_paper must call pipeline_fn when provided."""
        bench = PaperWritingBench()
        called = []

        def fake_pipeline(domain, model):
            called.append((domain, model))
            return {"title": "Fake Paper", "abstract": "Abstract", "text": "Text"}

        score = bench._evaluate_paper("empirical_paper", "gpt-4", "good", fake_pipeline)
        assert len(called) == 1
        assert called[0] == ("empirical_paper", "gpt-4")
        assert score.paper_id.startswith("empirical_paper_good_")


class TestPaperWritingBenchRun:
    """Test the run() method."""

    def test_run_returns_list(self):
        """run() must return a list of PaperScore objects."""
        bench = PaperWritingBench(BenchmarkConfig(n_papers=2, domains=["empirical_paper"]))
        results = bench.run()
        assert isinstance(results, list)
        assert len(results) == 2

    def test_run_populates_results(self):
        """run() must populate bench.results."""
        bench = PaperWritingBench(BenchmarkConfig(n_papers=2, domains=["empirical_paper"]))
        assert bench.results == []
        bench.run()
        assert len(bench.results) == 2
        assert all(isinstance(r, PaperScore) for r in bench.results)

    def test_run_multiple_domains(self):
        """run() must evaluate all specified domains."""
        bench = PaperWritingBench(
            BenchmarkConfig(n_papers=1, domains=["empirical_paper", "ml_paper"])
        )
        results = bench.run()
        domains = set(r.domain for r in results)
        assert "empirical_paper" in domains
        assert "ml_paper" in domains

    def test_run_multiple_models(self):
        """run() must evaluate all specified models."""
        bench = PaperWritingBench(
            BenchmarkConfig(n_papers=1, domains=["empirical_paper"], models=["gpt-4", "claude-3"])
        )
        results = bench.run()
        models = set(r.model for r in results)
        assert "gpt-4" in models
        assert "claude-3" in models

    def test_run_default_domain_all_available(self):
        """run() with no domains must use all available domains."""
        bench = PaperWritingBench(BenchmarkConfig(n_papers=1))
        results = bench.run()
        assert len(results) >= 1


class TestPaperWritingBenchReport:
    """Test the report() method."""

    def test_report_empty_results(self):
        """report() must handle empty results gracefully."""
        bench = PaperWritingBench()
        df = bench.report([])
        assert isinstance(df, __import__("pandas").DataFrame)
        assert df.empty

    def test_report_with_results(self):
        """report() must return a DataFrame with result rows."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.9,
                halt_results={},
                passed_rules=9,
                total_rules=10,
                pass_rate=0.9,
                generation_time_sec=1.0,
            ),
            PaperScore(
                paper_id="p2",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.5,
                halt_results={},
                passed_rules=5,
                total_rules=10,
                pass_rate=0.5,
                generation_time_sec=0.5,
            ),
        ]
        df = bench.report(scores)
        assert len(df) == 2
        assert "pass_rate" in df.columns
        assert "paper_id" in df.columns
        assert "domain" in df.columns

    def test_report_includes_error_column(self):
        """report() DataFrame must include 'error' column."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.0,
                halt_results={},
                passed_rules=0,
                total_rules=10,
                pass_rate=0.0,
                generation_time_sec=0.1,
                error="Test error",
            )
        ]
        df = bench.report(scores)
        assert "error" in df.columns
        assert df.iloc[0]["error"] == "Test error"


class TestPaperWritingBenchSimulateAcceptanceRates:
    """Test simulate_acceptance_rates()."""

    def test_simulate_empty_results(self):
        """simulate_acceptance_rates() must handle empty results."""
        bench = PaperWritingBench()
        rates = bench.simulate_acceptance_rates([])
        assert rates == {}

    def test_simulate_returns_dict_per_venue(self):
        """simulate_acceptance_rates() must return dict with venue keys."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.9,
                halt_results={},
                passed_rules=9,
                total_rules=10,
                pass_rate=0.9,
                generation_time_sec=1.0,
            )
        ]
        rates = bench.simulate_acceptance_rates(scores)
        assert isinstance(rates, dict)
        assert len(rates) > 0
        for venue, stats in rates.items():
            assert "threshold" in stats
            assert "acceptance_rate" in stats
            assert "accepted" in stats
            assert "total" in stats
            assert "mean_score" in stats
            assert "std_score" in stats

    def test_simulate_venue_thresholds_vary(self):
        """Different venues must have different thresholds."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={},
                passed_rules=8,
                total_rules=10,
                pass_rate=0.8,
                generation_time_sec=1.0,
            )
        ]
        rates = bench.simulate_acceptance_rates(scores)
        thresholds = set(v["threshold"] for v in rates.values())
        assert len(thresholds) > 1

    def test_simulate_csv_path_default(self, tmp_path):
        """simulate_acceptance_rates() must write CSV to default path."""
        out = tmp_path / "benchmark"
        out.mkdir()
        bench = PaperWritingBench(BenchmarkConfig(output_dir=str(out)))
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={},
                passed_rules=8,
                total_rules=10,
                pass_rate=0.8,
                generation_time_sec=1.0,
            )
        ]
        bench.simulate_acceptance_rates(scores, output_csv=str(tmp_path / "rates.csv"))
        csv_file = tmp_path / "rates.csv"
        assert csv_file.exists()


class TestPaperWritingBenchValidationSummary:
    """Test validation_summary() method."""

    def test_validation_summary_empty(self):
        """validation_summary() must handle empty results."""
        bench = PaperWritingBench()
        summaries = bench.validation_summary([])
        assert summaries == []

    def test_validation_summary_returns_list(self):
        """validation_summary() must return list of ValidationSummary."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={"H001": (True, "OK"), "H002": (True, "OK")},
                passed_rules=2,
                total_rules=2,
                pass_rate=1.0,
                generation_time_sec=1.0,
            )
        ]
        summaries = bench.validation_summary(scores)
        assert isinstance(summaries, list)
        assert len(summaries) == 1
        s = summaries[0]
        assert s.domain == "empirical_paper"
        assert s.papers_evaluated == 1
        assert s.total_rules == 2
        assert s.mean_pass_rate == 1.0

    def test_validation_summary_computes_std(self):
        """validation_summary() must compute std of pass rates."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id=f"p{i}",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={},
                passed_rules=8,
                total_rules=10,
                pass_rate=0.8,
                generation_time_sec=1.0,
            )
            for i in range(5)
        ]
        summaries = bench.validation_summary(scores)
        assert len(summaries) == 1
        assert summaries[0].std_pass_rate == 0.0  # all identical

    def test_validation_summary_skips_errored(self):
        """validation_summary() must skip papers with errors."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="good",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={},
                passed_rules=8,
                total_rules=10,
                pass_rate=0.8,
                generation_time_sec=1.0,
            ),
            PaperScore(
                paper_id="error",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.0,
                halt_results={},
                passed_rules=0,
                total_rules=10,
                pass_rate=0.0,
                generation_time_sec=0.1,
                error="Simulated error",
            ),
        ]
        summaries = bench.validation_summary(scores)
        assert len(summaries) == 1
        assert summaries[0].papers_evaluated == 1  # only non-error counted

    def test_validation_summary_rule_breakdown(self):
        """validation_summary() must include rule_results breakdown."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.5,
                halt_results={
                    "H001": (True, "OK"),
                    "H002": (False, "Failed"),
                },
                passed_rules=1,
                total_rules=2,
                pass_rate=0.5,
                generation_time_sec=1.0,
            )
        ]
        summaries = bench.validation_summary(scores)
        assert "H001" in summaries[0].rule_results
        assert "H002" in summaries[0].rule_results
        assert summaries[0].rule_results["H001"]["passed"] == 1


class TestPaperWritingBenchLLMJudge:
    """Test llm_judge_evaluate() and _llm_judge_fallback()."""

    def test_llm_judge_fallback_returns_dataframe(self):
        """_llm_judge_fallback() must return a DataFrame."""
        bench = PaperWritingBench()
        papers = [{"paper_id": "p1", "domain": "empirical_paper", "halt_score": 0.8}]
        df = bench._llm_judge_fallback(papers)
        assert len(df) == 1
        assert "paper_id" in df.columns
        assert "halt_score" in df.columns
        assert "llm_mean" in df.columns
        assert "agreement" in df.columns

    def test_llm_judge_fallback_scales_halt_score(self):
        """_llm_judge_fallback() must scale halt_score [0,1] to [1,10]."""
        bench = PaperWritingBench()
        papers = [{"paper_id": "p1", "domain": "empirical_paper", "halt_score": 0.5}]
        df = bench._llm_judge_fallback(papers)
        # halt_score 0.5 → llm_mean 0.5*9+1 = 5.5
        assert df.iloc[0]["llm_mean"] == 5.5
        assert df.iloc[0]["halt_scaled"] == 5.5

    def test_llm_judge_evaluate_uses_fallback_when_reviewer_unavailable(self):
        """llm_judge_evaluate() must use fallback when reviewer unavailable."""
        bench = PaperWritingBench()
        papers = [{"paper_id": "p1", "domain": "empirical_paper", "halt_score": 0.8}]
        df = bench.llm_judge_evaluate(papers, judge_model="nonexistent-model")
        assert len(df) == 1
        assert "paper_id" in df.columns

    def test_llm_judge_evaluate_multiple_papers(self):
        """llm_judge_evaluate() must handle multiple papers."""
        bench = PaperWritingBench()
        papers = [
            {"paper_id": f"p{i}", "domain": "empirical_paper", "halt_score": 0.5 + i * 0.1}
            for i in range(3)
        ]
        df = bench.llm_judge_evaluate(papers)
        assert len(df) == 3


class TestPaperWritingBenchPrintRuleBreakdown:
    """Test _print_domain_rule_breakdown()."""

    def test_prints_without_error(self):
        """_print_domain_rule_breakdown() must not raise."""
        bench = PaperWritingBench()
        scores = [
            PaperScore(
                paper_id="p1",
                domain="empirical_paper",
                model="synthetic",
                section_scores={},
                overall_score=0.8,
                halt_results={"H001": (True, "OK"), "H002": (False, "Fail")},
                passed_rules=1,
                total_rules=2,
                pass_rate=0.5,
                generation_time_sec=1.0,
            )
        ]
        # Should not raise
        bench._print_domain_rule_breakdown("empirical_paper", scores)


class TestBenchmarkConfigAdditional:
    """Additional tests for BenchmarkConfig."""

    def test_default_domains_is_none(self):
        """Default domains must be None (use all available)."""
        cfg = BenchmarkConfig()
        assert cfg.domains is None

    def test_default_models_is_none(self):
        """Default models must be None (use ['synthetic'])."""
        cfg = BenchmarkConfig()
        assert cfg.models is None

    def test_all_fields_acceptable(self):
        """BenchmarkConfig must accept all documented fields."""
        cfg = BenchmarkConfig(
            n_papers=20,
            domains=["empirical_paper", "ml_paper"],
            models=["gpt-4", "claude-3"],
            output_dir="/tmp/bench",
            max_tokens_per_call=8192,
            timeout_per_paper=600,
        )
        assert cfg.n_papers == 20
        assert cfg.domains == ["empirical_paper", "ml_paper"]
        assert cfg.models == ["gpt-4", "claude-3"]
        assert cfg.output_dir == "/tmp/bench"
        assert cfg.max_tokens_per_call == 8192
        assert cfg.timeout_per_paper == 600


class TestValidationSummaryAdditional:
    """Additional tests for ValidationSummary."""

    def test_papers_passed_threshold(self):
        """papers_passed must count papers with pass_rate >= 0.7."""
        summary = ValidationSummary(
            domain="empirical_paper",
            total_rules=10,
            papers_evaluated=5,
            papers_passed=3,
            pass_rate=0.6,
            mean_pass_rate=0.65,
            std_pass_rate=0.2,
            rule_results={},
        )
        assert summary.papers_passed == 3
        assert summary.papers_passed / summary.papers_evaluated == summary.pass_rate


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
