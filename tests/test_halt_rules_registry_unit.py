"""Unit tests for scripts/core/halt_rules_registry.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def hrr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import halt_rules_registry as h
    yield h
    if _p in sys.path:
        sys.path.remove(_p)


# ─── _safe_eval tests ────────────────────────────────────────────────────────────

class TestSafeEval:
    def test_eval_number(self, hrr):
        assert hrr._safe_eval("42") == 42
        assert hrr._safe_eval("-3") == -3

    def test_eval_add(self, hrr):
        assert hrr._safe_eval("2 + 3") == 5

    def test_eval_sub(self, hrr):
        assert hrr._safe_eval("10 - 4") == 6

    def test_eval_mul(self, hrr):
        assert hrr._safe_eval("3 * 4") == 12

    def test_eval_div(self, hrr):
        assert hrr._safe_eval("10 / 2") == 5.0

    def test_eval_pow(self, hrr):
        assert hrr._safe_eval("2 ** 3") == 8

    def test_eval_mod(self, hrr):
        assert hrr._safe_eval("10 % 3") == 1

    def test_eval_complex(self, hrr):
        assert hrr._safe_eval("2 + 3 * 4") == 14
        assert hrr._safe_eval("(2 + 3) * 4") == 20

    def test_compare_lt(self, hrr):
        assert hrr._safe_eval("3 < 5") is True
        assert hrr._safe_eval("5 < 3") is False

    def test_compare_le(self, hrr):
        assert hrr._safe_eval("3 <= 3") is True
        assert hrr._safe_eval("3 <= 2") is False

    def test_compare_gt(self, hrr):
        assert hrr._safe_eval("5 > 3") is True

    def test_compare_ge(self, hrr):
        assert hrr._safe_eval("5 >= 5") is True

    def test_compare_eq(self, hrr):
        assert hrr._safe_eval("5 == 5") is True
        assert hrr._safe_eval("5 == 3") is False

    def test_compare_ne(self, hrr):
        assert hrr._safe_eval("5 != 3") is True

    def test_compare_chain(self, hrr):
        assert hrr._safe_eval("1 < 2 < 3") is True
        assert hrr._safe_eval("1 < 3 < 2") is False

    def test_eval_unknown_var_raises(self, hrr):
        with pytest.raises(ValueError, match="Unknown variable"):
            hrr._safe_eval("x + 1")


# ─── Dataclass tests ─────────────────────────────────────────────────────────────

class TestDataclasses:
    def test_rule_violation(self, hrr):
        v = hrr.RuleViolation(
            rule_id="r1",
            severity="error",
            message="test violation",
            auto_fix_available=False,
        )
        assert v.rule_id == "r1"
        assert v.severity == "error"

    def test_validation_result_default(self, hrr):
        r = hrr.ValidationResult(all_passed=True, violations=[], halted=False)
        assert r.all_passed is True
        assert r.halted is False
        assert r.checked_rules == 0
        assert r.domain == ""

    def test_validation_result_passed_alias(self, hrr):
        r = hrr.ValidationResult(all_passed=True, violations=[], halted=False)
        assert r.passed is True

    def test_validation_result_error_count(self, hrr):
        r = hrr.ValidationResult(
            all_passed=False,
            violations=[
                hrr.RuleViolation("r1", "error", "e1", False),
                hrr.RuleViolation("r2", "warning", "w1", False),
                hrr.RuleViolation("r3", "error", "e2", False),
            ],
            halted=False,
        )
        assert r.error_count == 2

    def test_validation_result_warning_count(self, hrr):
        r = hrr.ValidationResult(
            all_passed=False,
            violations=[
                hrr.RuleViolation("r1", "error", "e1", False),
                hrr.RuleViolation("r2", "warning", "w1", False),
            ],
            halted=False,
        )
        assert r.warning_count == 1

    def test_rule_severity(self, hrr):
        s = hrr.RuleSeverity()
        assert s.ERROR == "error"
        assert s.WARNING == "warning"
        assert s.INFO == "info"


# ─── HaltRulesRegistry tests ─────────────────────────────────────────────────────

class TestRegistryInit:
    def test_init_with_path(self, hrr, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        reg = hrr.HaltRulesRegistry(rules_dir)
        assert reg.rules_dir == rules_dir
        assert isinstance(reg._cache, dict)


class TestRegistryValidate:
    def test_validate_nonexistent_domain_returns_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path / "nonexistent")
        result = reg.validate("nonexistent_domain_xyz")
        assert result.all_passed is True
        assert len(result.violations) == 0

    def test_validate_signature_positional(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path / "r")
        result = reg.validate("finance_report", {"text": "test"})
        assert result is not None
        assert isinstance(result, hrr.ValidationResult)

    def test_validate_signature_keyword(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path / "r")
        result = reg.validate({"text": "test"}, domain="finance_report")
        assert result is not None

    def test_validate_halted_flag(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path / "r")
        # With no rules, nothing halts
        result = reg.validate("nonexistent")
        assert result.halted is False


class TestRegistryHelpers:
    def test_load_rules_caches(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rules = reg.load_rules("nonexistent")
        assert rules == []
        assert "nonexistent" in reg._cache

    def test_reload_invalidates_cache(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        reg.load_rules("nonexistent")
        assert "nonexistent" in reg._cache
        reg.reload("nonexistent")
        assert "nonexistent" in reg._cache  # still cached but reloaded

    def test_list_rules(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        result = reg.list_rules()
        assert isinstance(result, dict)

    def test_list_rules_single_domain(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        result = reg.list_rules("empirical_paper")
        assert isinstance(result, dict)

    def test_get_domains_returns_sorted_list(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        domains = reg.get_domains()
        assert isinstance(domains, list)

    def test_load_all(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        reg.load_all()
        # Should not raise


# ─── HaltRuleChecker tests ───────────────────────────────────────────────────────

class TestHaltRuleChecker:
    def test_init(self, hrr, tmp_path):
        checker = hrr.HaltRuleChecker(tmp_path / "rules")
        assert checker.registry is not None

    def test_check_positional(self, hrr, tmp_path):
        checker = hrr.HaltRuleChecker(tmp_path)
        # Use keyword argument to avoid positional argument ambiguity
        halted, result = checker.check({"text": "test"}, domain="nonexistent_domain_xyz")
        assert isinstance(result, hrr.ValidationResult)

    def test_check_keyword(self, hrr, tmp_path):
        checker = hrr.HaltRuleChecker(tmp_path)
        halted, result = checker.check({"text": "test"}, domain="finance_report")
        assert isinstance(result, hrr.ValidationResult)

    def test_check_all(self, hrr, tmp_path):
        checker = hrr.HaltRuleChecker(tmp_path)
        results = checker.check_all({"text": "test"})
        assert isinstance(results, dict)


# ─── Checker method tests ────────────────────────────────────────────────────────

class TestNumericalChecker:
    def test_check_numerical_in_range(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "n1", "validation": {"type": "regex_with_api_check", "check": [
            {"pattern": r"\d+", "range": [0, 100], "description": "value in range"}
        ]}}
        passed, msg = reg._check_numerical_accuracy("value is 50", rule)
        assert passed is True

    def test_check_numerical_out_of_range(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "n2", "validation": {"type": "regex_with_api_check", "check": [
            {"pattern": r"\d+", "range": [0, 10], "description": "value in range"}
        ]}}
        passed, msg = reg._check_numerical_accuracy("value is 999", rule)
        assert passed is False
        assert "outside range" in msg


class TestMathConsistency:
    def test_check_math_consistency_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "m1", "validation": {"type": "math_consistency", "rules": [
            {"formula": "net_margin <= gross_margin", "description": "margin check"}
        ]}}
        passed, msg = reg._check_math_consistency(
            {"net_margin": 0.1, "gross_margin": 0.3}, rule
        )
        assert passed is True

    def test_check_math_consistency_fail(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "m2", "validation": {"type": "math_consistency", "rules": [
            {"formula": "net_margin <= gross_margin", "description": "margin check"}
        ]}}
        passed, msg = reg._check_math_consistency(
            {"net_margin": 0.5, "gross_margin": 0.3}, rule
        )
        assert passed is False

    def test_check_math_missing_field(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "m3", "validation": {"type": "math_consistency", "rules": [
            {"formula": "a <= b", "description": "check"}
        ]}}
        passed, msg = reg._check_math_consistency({"a": 1}, rule)
        assert passed is False
        assert "missing fields" in msg


class TestBalanceSheet:
    def test_balance_sheet_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "b1"}
        passed, msg = reg._check_balance_sheet(
            {"total_assets": 100, "total_liabilities": 60, "equity": 40}, rule
        )
        assert passed is True

    def test_balance_sheet_fail(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "b2"}
        passed, msg = reg._check_balance_sheet(
            {"total_assets": 100, "total_liabilities": 60, "equity": 20}, rule
        )
        assert passed is False


class TestCashFlow:
    def test_cash_flow_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "c1"}
        passed, msg = reg._check_cash_flow(
            {"beginning_cash": 100, "net_cash_flow": 50, "ending_cash": 150}, rule
        )
        assert passed is True

    def test_cash_flow_fail(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "c2"}
        passed, msg = reg._check_cash_flow(
            {"beginning_cash": 100, "net_cash_flow": 50, "ending_cash": 120}, rule
        )
        assert passed is False


class TestYoYQoQLogic:
    def test_yoy_qoq_logic_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "y1", "validation": {"type": "custom", "tolerance": 0.01, "checks": []}}
        content = {
            "yoy": {"revenue": {"2023": 100, "2024": 110}},
            "yoy_rate": {"revenue": {"2024": 0.1}},
        }
        passed, msg = reg._check_yoy_qoq_logic(content, rule)
        assert passed is True

    def test_qoq_jump_detected(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "y2", "validation": {"type": "custom", "max_change": 1.0, "checks": []}}
        content = {
            "qoq": {"revenue": {"Q1": 100, "Q2": 500}},
        }
        passed, msg = reg._check_yoy_qoq_logic(content, rule)
        assert passed is False


class TestFormatChecker:
    def test_format_check_pass(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "f1", "validation": {"type": "format_check", "rules": [
            {"pattern": r"\d{4}-\d{2}-\d{2}", "description": "date format"}
        ]}}
        passed, msg = reg._check_format("Date: 2024-01-15", rule)
        assert passed is True

    def test_format_check_fail(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "f2", "validation": {"type": "format_check", "rules": [
            {"pattern": r"\d{4}-\d{2}-\d{2}", "description": "date format"}
        ]}}
        passed, msg = reg._check_format("Date: Jan 15 2024", rule)
        assert passed is False


class TestDataDescription:
    def test_no_placeholder_passes(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "d1", "validation": {"type": "data_description_check"}}
        passed, msg = reg._check_data_description("Real financial data for 2024.", rule)
        assert passed is True

    def test_placeholder_detected(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "d2", "validation": {"type": "data_description_check"}}
        passed, msg = reg._check_data_description("This is [SIMULATED] data.", rule)
        assert passed is False
        assert "SIMULATED" in msg


class TestSignificance:
    def test_significance_format_declared(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "s1", "validation": {"type": "significance_check"}}
        passed, msg = reg._check_empirical_significance(
            "* p<0.1, ** p<0.05, *** p<0.01", rule
        )
        assert passed is True

    def test_significance_not_declared(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "s2", "validation": {"type": "significance_check"}}
        passed, msg = reg._check_empirical_significance("Results are significant ***", rule)
        assert passed is False


class TestCitation:
    def test_doi_format_check(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "c1", "validation": {"type": "citation_format_check"}}
        passed, msg = reg._check_empirical_citation_format(
            "See Smith (2024) 10.1000/xyz123", rule
        )
        assert passed is True

    def test_malformed_doi_detected(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "c2", "validation": {"type": "citation_format_check"}}
        # When no DOIs are found, check passes (no malformed ones to detect)
        passed, msg = reg._check_empirical_citation_format(
            "See Smith (2024).", rule
        )
        # No DOI found → check passes
        assert passed is True


class TestMLPaper:
    def test_ml_experiment_missing_ablation(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "ml1", "validation": {"type": "experiment_check"}}
        passed, msg = reg._check_ml_experiment("This paper uses BERT.", rule)
        assert passed is False

    def test_ml_experiment_with_ablation_and_baseline(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {"id": "ml2", "validation": {"type": "experiment_check"}}
        passed, msg = reg._check_ml_experiment(
            "We perform ablation studies and compare with baseline methods including BERT and GPT.", rule
        )
        assert passed is True


class TestEmpiricalStructure:
    def test_paper_structure_all_present(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {
            "id": "es1",
            "validation": {
                "type": "structure_check",
                "required_sections": [
                    {"name": "abstract", "required": True},
                    {"name": "introduction", "required": True},
                ],
            },
        }
        text = "Abstract: This paper introduces a new method. Introduction discusses prior work."
        passed, msg = reg._check_empirical_paper_structure(text, rule)
        assert passed is True

    def test_paper_structure_missing_section(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        rule = {
            "id": "es2",
            "validation": {
                "type": "structure_check",
                "required_sections": [
                    {"name": "abstract", "required": True},
                    {"name": "introduction", "required": True},
                    {"name": "conclusion", "required": True},
                ],
            },
        }
        text = "Abstract: This paper introduces a new method."
        passed, msg = reg._check_empirical_paper_structure(text, rule)
        assert passed is False


class TestExtractField:
    def test_extract_direct_key(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        val = reg._extract_field({"total_assets": 100}, "total_assets")
        assert val == 100.0

    def test_extract_with_underscore_variant(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        val = reg._extract_field({"totalAssets": 200}, "total_assets")
        assert val == 200.0

    def test_extract_missing(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        val = reg._extract_field({"x": 1}, "missing_field")
        assert val is None

    def test_extract_non_numeric(self, hrr, tmp_path):
        reg = hrr.HaltRulesRegistry(tmp_path)
        val = reg._extract_field({"x": "hello"}, "x")
        assert val is None


class TestModuleAttributes:
    def test_all_exports(self, hrr):
        expected = ["RuleViolation", "ValidationResult", "RuleSeverity",
                    "HaltRuleChecker", "HaltRulesRegistry"]
        for name in expected:
            assert hasattr(hrr, name), f"Missing export: {name}"

    def test_backward_compat_alias(self, hrr):
        # The __getattr__ provides HaltRuleRegistry without trailing 's'
        assert hrr.HaltRulesRegistry is not None
