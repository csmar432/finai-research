"""Tests for scripts/validate_econometrics.py"""
import pytest

class TestFDRCorrection:
    def test_bh_correction_basic(self):
        from scripts.research_framework.robustness_runner import apply_fdr_correction
        pvalues = [0.001, 0.01, 0.03, 0.05, 0.10]
        qvalues = apply_fdr_correction(pvalues, method="bh")
        assert len(qvalues) == len(pvalues)
        # All q-values should be >= corresponding p-values
        for p, q in zip(pvalues, qvalues):
            assert q >= p
        # q-values should be monotonically non-decreasing
        for i in range(len(qvalues) - 1):
            assert qvalues[i] <= qvalues[i + 1]
        # All should be capped at 1.0
        assert all(q <= 1.0 for q in qvalues)

    def test_bh_correction_empty(self):
        from scripts.research_framework.robustness_runner import apply_fdr_correction
        assert apply_fdr_correction([], method="bh") == []

    def test_bh_correction_single(self):
        from scripts.research_framework.robustness_runner import apply_fdr_correction
        result = apply_fdr_correction([0.05], method="bh")
        assert len(result) == 1

    def test_by_correction_more_conservative(self):
        from scripts.research_framework.robustness_runner import apply_fdr_correction
        pvalues = [0.001, 0.01, 0.03, 0.05, 0.10]
        q_bh = apply_fdr_correction(pvalues, method="bh")
        q_by = apply_fdr_correction(pvalues, method="by")
        # BY should be more conservative (higher q-values)
        for bh, by_ in zip(q_bh, q_by):
            assert by_ >= bh

    def test_invalid_method_raises(self):
        from scripts.research_framework.robustness_runner import apply_fdr_correction
        with pytest.raises(ValueError):
            apply_fdr_correction([0.05], method="invalid")


class TestSummarizeRobustnessWithFDR:
    def test_empty_results(self):
        from scripts.research_framework.robustness_runner import summarize_robustness_with_fdr
        result = summarize_robustness_with_fdr([])
        assert result["n_tests"] == 0

    def test_summarizes_with_fdr(self):
        from scripts.research_framework.robustness_runner import summarize_robustness_with_fdr
        results = [
            {"name": "test1", "pvalue": 0.001, "coefficient": 0.5},
            {"name": "test2", "pvalue": 0.05, "coefficient": 0.3},
            {"name": "test3", "pvalue": 0.50, "coefficient": 0.1},
        ]
        summary = summarize_robustness_with_fdr(results, fdr_threshold=0.05)
        assert summary["n_tests"] == 3
        assert "raw_significant" in summary
        assert "fdr_significant" in summary
        assert "results" in summary
        assert len(summary["results"]) == 3
        # Check each result has q-value
        for r in summary["results"]:
            assert "qvalue" in r
            assert "fdr_reject" in r
            assert "raw_reject" in r
        assert "summary" in summary


class TestValidationScript:
    def test_module_imports(self):
        from scripts import validate_econometrics
        assert hasattr(validate_econometrics, "ValidationResult")
        assert hasattr(validate_econometrics, "validate_did")
        assert hasattr(validate_econometrics, "validate_iv")

    def test_did_synthetic_true_att(self):
        from scripts.validate_econometrics import load_did_synthetic, estimate_did_python
        df = load_did_synthetic()
        assert len(df) == 400  # 200 pre + 200 post
        assert "outcome" in df.columns
        coef, se = estimate_did_python(df)
        assert isinstance(coef, float)
        assert isinstance(se, float)
        assert 0 <= coef <= 2  # Should be close to 1.0 (known true ATT)

    def test_iv_synthetic_import(self):
        from scripts.validate_econometrics import load_wooldridge_card_hehes
        df = load_wooldridge_card_hehes()
        assert "lwage" in df.columns
        assert "educ" in df.columns
        assert "nearc4" in df.columns
        assert len(df) == 3014

    def test_validation_result_pass(self):
        from scripts.validate_econometrics import ValidationResult
        result = ValidationResult(
            method="test_did",
            ref_value=1.0,
            python_value=1.02,
            ref_std_err=None,
            python_std_err=0.1,
            tolerance=0.05,
            reference_source="synthetic",
        )
        assert result.pass_all is True
        assert result.pass_coef is True
        assert "PASS" in str(result)

    def test_validation_result_fail(self):
        from scripts.validate_econometrics import ValidationResult
        result = ValidationResult(
            method="test_did",
            ref_value=1.0,
            python_value=5.0,  # Way off
            ref_std_err=None,
            python_std_err=0.1,
            tolerance=0.05,
            reference_source="synthetic",
        )
        assert result.pass_all is False
        assert result.pass_coef is False
        assert "FAIL" in str(result)

    def test_validation_result_with_se(self):
        from scripts.validate_econometrics import ValidationResult
        result = ValidationResult(
            method="test_iv",
            ref_value=0.107,
            python_value=0.108,
            ref_std_err=0.032,
            python_std_err=0.033,
            tolerance=0.02,
            reference_source="wooldridge",
        )
        assert result.pass_all is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
