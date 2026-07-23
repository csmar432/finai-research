"""
Tests for HaltRulesRegistry — scripts/core/halt_rules_registry.py
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.halt_rules_registry import (
    HaltRulesRegistry,
    RuleViolation,
    ValidationResult,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_rules_dir(tmp_path):
    import yaml
    rules = tmp_path / "halt_rules"
    rules.mkdir()
    data = {
        "domain": "test_domain",
        "version": "1.0",
        "rules": [
            {
                "id": "test_numerical",
                "description": "Test numeric range",
                "severity": "error",
                "validation": {
                    "type": "regex_with_api_check",
                    "check": [
                        {
                            "pattern": r"ROE=(-?\d+\.?\d*)%",
                            "range": [-50, 100],
                            "description": "ROE",
                        },
                    ],
                },
                "halt_on_fail": True,
            },
            {
                "id": "test_margin",
                "description": "Margins must be consistent",
                "severity": "error",
                "validation": {
                    "type": "math_consistency",
                    "rules": [
                        {
                            "description": "net_margin <= gross_margin",
                            "formula": "net_margin <= gross_margin",
                        },
                    ],
                },
                "halt_on_fail": True,
            },
            {
                "id": "test_freshness",
                "description": "Data must be recent",
                "severity": "warning",
                "validation": {
                    "type": "timestamp_check",
                    "rules": [
                        {
                            "description": "Report date within 365 days",
                            "max_age_days": 365,
                            "check_date_field": "report_date",
                        },
                    ],
                },
                "halt_on_fail": False,
            },
            {
                "id": "test_not_implemented",
                "description": "This rule type does not exist",
                "severity": "warning",
                "validation": {
                    "type": "nonexistent_validation_type",
                },
                "halt_on_fail": False,
            },
        ],
    }
    (rules / "test_domain.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return rules


@pytest.fixture
def registry(temp_rules_dir):
    return HaltRulesRegistry(rules_dir=str(temp_rules_dir))


# ── Registry Loading ───────────────────────────────────────────────────────────

class TestRegistryLoading:
    def test_load_rules_returns_list(self, registry):
        rules = registry.load_rules("test_domain")
        assert isinstance(rules, list)
        assert len(rules) == 4

    def test_load_rules_caches(self, registry):
        r1 = registry.load_rules("test_domain")
        r2 = registry.load_rules("test_domain")
        assert r1 is r2  # Same object (cached)

    def test_load_rules_nonexistent_domain(self, registry):
        rules = registry.load_rules("does_not_exist")
        assert rules == []

    def test_reload_invalidates_cache(self, registry):
        r1 = registry.load_rules("test_domain")
        registry.reload("test_domain")
        r2 = registry.load_rules("test_domain")
        assert r1 is not r2


# ── Validation Result ─────────────────────────────────────────────────────────

class TestValidationResult:
    def test_all_passed_true(self):
        result = ValidationResult(all_passed=True, violations=[], halted=False)
        assert result.all_passed is True
        assert result.halted is False
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_error_and_warning_counts(self):
        violations = [
            RuleViolation("r1", "error", "msg1", False),
            RuleViolation("r2", "warning", "msg2", False),
            RuleViolation("r3", "error", "msg3", False),
            RuleViolation("r4", "info", "msg4", False),
        ]
        result = ValidationResult(all_passed=False, violations=violations, halted=True)
        assert result.error_count == 2
        assert result.warning_count == 1


# ── Numeric Accuracy Check ────────────────────────────────────────────────────

class TestNumericalAccuracy:
    def test_valid_roe_in_range(self, registry):
        passed, msg = registry._check_numerical_accuracy(
            {"text": "ROE=15.5%"},
            {"validation": {"type": "regex_with_api_check", "check": [
                {"pattern": "ROE=(-?\\d+\\.?\\d*)%", "range": [-50, 100], "description": "ROE"}
            ]}},
        )
        assert passed is True
        assert msg == ""

    def test_roe_out_of_range(self, registry):
        passed, msg = registry._check_numerical_accuracy(
            {"text": "ROE=150.5%"},
            {"validation": {"type": "regex_with_api_check", "check": [
                {"pattern": "ROE=(-?\\d+\\.?\\d*)%", "range": [-50, 100], "description": "ROE"}
            ]}},
        )
        assert passed is False
        assert "outside range" in msg

    def test_no_matches_passes(self, registry):
        passed, msg = registry._check_numerical_accuracy(
            {"text": "Company has healthy financials."},
            {"validation": {"type": "regex_with_api_check", "check": [
                {"pattern": "ROE=(-?\\d+\\.?\\d*)%", "range": [-50, 100], "description": "ROE"}
            ]}},
        )
        assert passed is True


# ── Math Consistency Check ────────────────────────────────────────────────────

class TestMathConsistency:
    def test_net_margin_less_than_gross_margin_passes(self, registry):
        passed, msg = registry._check_math_consistency(
            {"net_margin": 10.0, "gross_margin": 30.0},
            {"validation": {"type": "math_consistency", "rules": [
                {"description": "net_margin <= gross_margin", "formula": "net_margin <= gross_margin"}
            ]}},
        )
        assert passed is True

    def test_net_margin_greater_than_gross_margin_fails(self, registry):
        passed, msg = registry._check_math_consistency(
            {"net_margin": 40.0, "gross_margin": 30.0},
            {"validation": {"type": "math_consistency", "rules": [
                {"description": "net_margin <= gross_margin", "formula": "net_margin <= gross_margin"}
            ]}},
        )
        assert passed is False
        assert "False" in msg

    def test_missing_fields_fails(self, registry):
        passed, msg = registry._check_math_consistency(
            {"other_field": 10.0},
            {"validation": {"type": "math_consistency", "rules": [
                {"description": "net_margin <= gross_margin", "formula": "net_margin <= gross_margin"}
            ]}},
        )
        # Missing fields → evaluation fails with a message listing them
        assert passed is False
        assert "missing fields" in msg


# ── YoY / QoQ Logic Check ────────────────────────────────────────────────────

class TestYoYQoQLogic:
    def test_yoy_within_tolerance_passes(self, registry):
        content = {
            "yoy_rate": {"revenue": {"2024": 0.12}},
            "yoy": {"revenue": {"2024": 112.0, "2023": 100.0}},
        }
        passed, msg = registry._check_yoy_qoq_logic(
            content,
            {"validation": {"type": "custom", "checks": [{"tolerance": 0.05, "max_change": 10.0}]}},
        )
        assert passed is True

    def test_qoq_impossible_jump_fails(self, registry):
        content = {
            "qoq": {"revenue": {"Q4": 1000.0, "Q3": 1.0}},
        }
        passed, msg = registry._check_yoy_qoq_logic(
            content,
            {"validation": {"type": "custom", "checks": [{"tolerance": 0.05, "max_change": 1.0}]}},
        )
        assert passed is False
        assert "QoQ impossible jump" in msg


# ── Data Freshness Check ──────────────────────────────────────────────────────

class TestDataFreshness:
    def test_fresh_data_passes(self, registry):
        import time
        content = {
            "report_date": time.time() - 30 * 86400,  # 30 days ago
        }
        passed, msg = registry._check_data_freshness(
            content,
            {"validation": {"type": "timestamp_check", "rules": [
                {"max_age_days": 365, "check_date_field": "report_date"}
            ]}},
        )
        assert passed is True

    def test_stale_data_fails(self, registry):
        import time
        content = {
            "report_date": time.time() - 400 * 86400,  # 400 days ago
        }
        passed, msg = registry._check_data_freshness(
            content,
            {"validation": {"type": "timestamp_check", "rules": [
                {"max_age_days": 365, "check_date_field": "report_date"}
            ]}},
        )
        assert passed is False
        assert "days old" in msg


# ── Full Validation Flow ─────────────────────────────────────────────────────

class TestFullValidation:
    def test_validate_all_pass(self, registry):
        result = registry.validate("test_domain", {"text": "ROE=15.5%", "net_margin": 10.0, "gross_margin": 30.0})
        # Only errors halt; warnings don't
        assert result.halted is False

    def test_validate_halts_on_critical_rule(self, registry):
        result = registry.validate("test_domain", {"text": "ROE=999%", "net_margin": 40.0, "gross_margin": 30.0})
        assert result.halted is True
        assert result.error_count >= 1

    def test_validate_not_implemented_warning(self, registry):
        result = registry.validate("test_domain", {"text": "anything"})
        not_impl = [v for v in result.violations if "NOT IMPLEMENTED" in v.message]
        assert len(not_impl) >= 1


# ── Empirical Paper Checker Tests ───────────────────────────────────────────────

class TestEmpiricalEndogeneity:
    """Tests for _check_empirical_endogeneity."""

    def test_endogeneity_discussion_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "We address potential endogeneity concerns using instrumental variables (IV). "
        text += "Selection bias is mitigated through propensity score matching."
        passed, msg = registry._check_empirical_endogeneity(
            {"text": text},
            {"validation": {"rules": [], "methods": ["IV", "instrumental"]}},
        )
        assert passed is True
        assert msg == ""

    def test_endogeneity_missing_discussion_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Our results show a positive effect on innovation."
        passed, msg = registry._check_empirical_endogeneity(
            {"text": text},
            {"validation": {"rules": [], "methods": ["IV"]}},
        )
        assert passed is False
        assert "No endogeneity discussion found" in msg


class TestEmpiricalSignificance:
    """Tests for _check_empirical_significance."""

    def test_standard_significance_format_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "* p<0.1, ** p<0.05, *** p<0.01. The coefficient is significantly positive."
        passed, msg = registry._check_empirical_significance(
            {"text": text},
            {"validation": {}},
        )
        assert passed is True
        assert msg == ""

    def test_missing_significance_format_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "The coefficient is significant at conventional levels."
        passed, msg = registry._check_empirical_significance(
            {"text": text},
            {"validation": {}},
        )
        assert passed is False
        assert "not declared" in msg

    def test_mixed_significance_systems_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Coefficient *** p<0.01, and another result marked with \u2020 p<0.05."
        passed, msg = registry._check_empirical_significance(
            {"text": text},
            {"validation": {}},
        )
        assert passed is False
        assert "Mixed significance systems" in msg


class TestEmpiricalCausalInference:
    """Tests for _check_empirical_causal_inference."""

    def test_causal_claim_with_caveat_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Our results show the policy caused an increase in innovation. "
        text += "However, correlation does not imply causation."
        passed, msg = registry._check_empirical_causal_inference(
            {"text": text},
            {"validation": {"rules": [{"check": "correlation_vs_causation"}]}},
        )
        assert passed is True
        assert msg == ""

    def test_causal_claim_without_caveat_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "The policy causes an increase in innovation."
        passed, msg = registry._check_empirical_causal_inference(
            {"text": text},
            {"validation": {"rules": [{"check": "correlation_vs_causation"}]}},
        )
        assert passed is False
        assert "caveat" in msg.lower()

    def test_causal_interpretation_without_bounds_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "The policy drives economic growth."
        passed, msg = registry._check_empirical_causal_inference(
            {"text": text},
            {"validation": {"rules": [{"check": "causal_interpretation_bounds"}]}},
        )
        assert passed is False
        assert "overstated" in msg.lower()


class TestEmpiricalEconomicSignificance:
    """Tests for _check_empirical_economic_significance."""

    def test_economic_significance_discussion_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "The marginal effect implies a 2 percentage point increase in investment. "
        text += "The economic significance is substantial relative to mean investment."
        passed, msg = registry._check_empirical_economic_significance(
            {"text": text},
            {"validation": {"rules": []}},
        )
        assert passed is True
        assert msg == ""

    def test_missing_economic_significance_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "The coefficient is positive and significant at the 1% level."
        passed, msg = registry._check_empirical_economic_significance(
            {"text": text},
            {"validation": {"rules": []}},
        )
        assert passed is False
        assert "No economic significance discussion found" in msg


# ── ML Paper Checker Tests ─────────────────────────────────────────────────────

class TestMLBaseline:
    """Tests for _check_ml_baseline."""

    def test_sota_and_classic_baselines_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "We compare against SOTA methods and classic baselines including "
        text += "logistic regression and random forest."
        passed, msg = registry._check_ml_baseline(
            {"text": text},
            {"validation": {}},
        )
        assert passed is True
        assert msg == ""

    def test_missing_baseline_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Our proposed model achieves 95% accuracy on the test set."
        passed, msg = registry._check_ml_baseline(
            {"text": text},
            {"validation": {}},
        )
        assert passed is False
        assert "No SOTA comparison found" in msg or "No classic method comparison found" in msg


class TestMLReproducibility:
    """Tests for _check_ml_reproducibility."""

    def test_reproducibility_statement_passes(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Code available at https://github.com/author/project. "
        text += "Experiments use random seed 42. "
        text += "Results reported as mean ± std across 10 runs."
        passed, msg = registry._check_ml_reproducibility(
            {"text": text},
            {"validation": {}},
        )
        assert passed is True
        assert msg == ""

    def test_missing_code_repo_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Experiments use random seed 42. Results: 0.85 ± 0.02."
        passed, msg = registry._check_ml_reproducibility(
            {"text": text},
            {"validation": {}},
        )
        assert passed is False
        assert "No code/repository link found" in msg

    def test_missing_random_seed_fails(self):
        registry = HaltRulesRegistry("config/halt_rules")
        text = "Code at https://github.com/author/project. Results: 0.85 ± 0.02."
        passed, msg = registry._check_ml_reproducibility(
            {"text": text},
            {"validation": {}},
        )
        assert passed is False
        assert "No random seed" in msg


class TestAllCheckersReturnTuples:
    """Sanity test: all checker methods return (bool, str) tuples."""

    def test_all_targeted_checkers_return_tuples(self):
        registry = HaltRulesRegistry("config/halt_rules")
        # All targeted checkers from CHECKER_MAP that exist
        targeted = [
            "_check_empirical_endogeneity",
            "_check_empirical_significance",
            "_check_empirical_causal_inference",
            "_check_empirical_economic_significance",
            "_check_ml_baseline",
            "_check_ml_reproducibility",
        ]
        for method_name in targeted:
            method = getattr(registry, method_name)
            result = method({"text": "test content"}, {"validation": {}})
            assert isinstance(result, tuple), f"{method_name} did not return a tuple"
            assert len(result) == 2, f"{method_name} did not return a 2-tuple"
            assert isinstance(result[0], bool), f"{method_name} first element not bool"
            assert isinstance(result[1], str), f"{method_name} second element not str"
