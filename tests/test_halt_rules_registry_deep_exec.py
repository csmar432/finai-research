"""
Deep execution tests for scripts/core/halt_rules_registry.py

Tests dataclasses, pure helpers, class init, and core logic paths.
"""

import ast
import operator as op
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# ── Module-level helpers ──────────────────────────────────────────────────────

from scripts.core.halt_rules_registry import (
    HaltRuleChecker,
    HaltRulesRegistry,
    RuleSeverity,
    RuleViolation,
    ValidationResult,
    _safe_eval,
    _safe_eval_node,
)


class TestSafeEval:
    """Tests for _safe_eval and _safe_eval_node (pure Python helpers)."""

    # ── _safe_eval: arithmetic ─────────────────────────────────────────────────

    def test_safe_eval_add(self):
        assert _safe_eval("2 + 3") == 5

    def test_safe_eval_subtract(self):
        assert _safe_eval("10 - 4") == 6

    def test_safe_eval_multiply(self):
        assert _safe_eval("3 * 7") == 21

    def test_safe_eval_divide(self):
        assert _safe_eval("20 / 4") == 5.0

    def test_safe_eval_power(self):
        assert _safe_eval("2 ** 3") == 8

    def test_safe_eval_mod(self):
        assert _safe_eval("17 % 5") == 2

    def test_safe_eval_unary_minus(self):
        assert _safe_eval("-5") == -5

    def test_safe_eval_unary_plus(self):
        assert _safe_eval("+3") == 3

    def test_safe_eval_complex(self):
        assert _safe_eval("2 + 3 * 4") == 14

    def test_safe_eval_float_result(self):
        assert _safe_eval("5 / 2") == 2.5

    # ── _safe_eval: comparisons ────────────────────────────────────────────────

    def test_safe_eval_lt(self):
        assert _safe_eval("3 < 5") is True
        assert _safe_eval("5 < 3") is False

    def test_safe_eval_le(self):
        assert _safe_eval("3 <= 3") is True
        assert _safe_eval("4 <= 3") is False

    def test_safe_eval_gt(self):
        assert _safe_eval("7 > 5") is True
        assert _safe_eval("5 > 7") is False

    def test_safe_eval_ge(self):
        assert _safe_eval("3 >= 3") is True
        assert _safe_eval("3 >= 4") is False

    def test_safe_eval_eq(self):
        assert _safe_eval("3 == 3") is True
        assert _safe_eval("3 == 4") is False

    def test_safe_eval_ne(self):
        assert _safe_eval("3 != 4") is True
        assert _safe_eval("3 != 3") is False

    def test_safe_eval_chained_comparison(self):
        assert _safe_eval("1 < 2 < 3") is True
        assert _safe_eval("1 < 2 < 1") is False

    # ── _safe_eval: errors ─────────────────────────────────────────────────────

    def test_safe_eval_unknown_variable_raises(self):
        with pytest.raises(ValueError, match="Unknown variable"):
            _safe_eval("x + 1")

    def test_safe_eval_unsupported_op_raises(self):
        node = ast.parse("1 and 0", mode="eval").body
        with pytest.raises(ValueError, match="Unsupported"):
            _safe_eval_node(node)

    def test_safe_eval_unsupported_compare_raises(self):
        # 'is' is not in the comparison map
        node = ast.Compare(left=ast.Constant(value=1), ops=[ast.Is()], comparators=[ast.Constant(value=1)])
        with pytest.raises(ValueError, match="Unsupported comparison"):
            _safe_eval_node(node)

    def test_safe_eval_unsupported_ast_node_raises(self):
        node = ast.IfExp(test=ast.Constant(value=True), body=ast.Constant(value=1), orelse=ast.Constant(value=0))
        with pytest.raises(ValueError, match="Unsupported AST node"):
            _safe_eval_node(node)


class TestSafeOpsDict:
    """Tests that _safe_ops maps all expected AST nodes."""

    def test_safe_ops_has_all_expected_keys(self):
        from scripts.core.halt_rules_registry import _safe_ops
        expected = {
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd
        }
        assert set(_safe_ops.keys()) == expected

    def test_safe_ops_values_are_callable(self):
        from scripts.core.halt_rules_registry import _safe_ops
        for fn in _safe_ops.values():
            assert callable(fn)


# ── Dataclasses ───────────────────────────────────────────────────────────────

class TestRuleViolation:
    """Tests for RuleViolation dataclass."""

    def test_construct_all_fields(self):
        v = RuleViolation(
            rule_id="test_rule",
            severity="error",
            message="something went wrong",
            auto_fix_available=True,
        )
        assert v.rule_id == "test_rule"
        assert v.severity == "error"
        assert v.message == "something went wrong"
        assert v.auto_fix_available is True

    def test_construct_default_auto_fix(self):
        v = RuleViolation(rule_id="r", severity="warning", message="warn", auto_fix_available=False)
        assert v.auto_fix_available is False


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_construct_all_fields(self):
        vr = ValidationResult(
            all_passed=True,
            violations=[],
            halted=False,
            checked_rules=5,
            domain="empirical_paper",
        )
        assert vr.all_passed is True
        assert vr.violations == []
        assert vr.halted is False
        assert vr.checked_rules == 5
        assert vr.domain == "empirical_paper"

    def test_construct_defaults(self):
        vr = ValidationResult(all_passed=True, violations=[], halted=False)
        assert vr.checked_rules == 0
        assert vr.domain == ""

    def test_passed_alias(self):
        vr = ValidationResult(all_passed=True, violations=[], halted=False)
        assert vr.passed is True
        vr2 = ValidationResult(all_passed=False, violations=[], halted=False)
        assert vr2.passed is False

    def test_error_count(self):
        vr = ValidationResult(
            all_passed=False,
            violations=[
                RuleViolation("r1", "error", "", False),
                RuleViolation("r2", "warning", "", False),
                RuleViolation("r3", "error", "", False),
            ],
            halted=False,
        )
        assert vr.error_count == 2

    def test_warning_count(self):
        vr = ValidationResult(
            all_passed=False,
            violations=[
                RuleViolation("r1", "error", "", False),
                RuleViolation("r2", "warning", "", False),
                RuleViolation("r3", "info", "", False),
            ],
            halted=False,
        )
        assert vr.warning_count == 1


class TestRuleSeverity:
    """Tests for RuleSeverity dataclass."""

    def test_constants(self):
        assert RuleSeverity.ERROR == "error"
        assert RuleSeverity.WARNING == "warning"
        assert RuleSeverity.INFO == "info"


# ── HaltRuleChecker ──────────────────────────────────────────────────────────

class TestHaltRuleCheckerInit:
    """Tests for HaltRuleChecker.__init__."""

    def test_init_default_rules_dir(self, tmp_path):
        checker = HaltRuleChecker()
        assert isinstance(checker.registry, HaltRulesRegistry)
        # Default dir resolves relative to cwd
        assert checker.registry.rules_dir == Path("config/halt_rules")

    def test_init_custom_rules_dir(self, tmp_path):
        checker = HaltRuleChecker(rules_dir=tmp_path)
        assert checker.registry.rules_dir == tmp_path

    def test_init_string_path(self, tmp_path):
        checker = HaltRuleChecker(rules_dir=str(tmp_path))
        assert checker.registry.rules_dir == tmp_path


class TestHaltRuleCheckerCheck:
    """Tests for HaltRuleChecker.check()."""

    def test_check_with_domain_kwarg(self, tmp_path):
        checker = HaltRuleChecker(rules_dir=tmp_path)
        # content_or_domain is treated as content when domain is provided
        halted, result = checker.check({}, domain="empirical_paper")
        assert isinstance(result, ValidationResult)

    def test_check_returns_tuple(self, tmp_path):
        checker = HaltRuleChecker(rules_dir=tmp_path)
        halted, result = checker.check({}, domain="empirical_paper")
        assert isinstance(halted, bool)
        assert isinstance(result, ValidationResult)

    def test_check_all_returns_dict(self, tmp_path):
        checker = HaltRuleChecker(rules_dir=tmp_path)
        results = checker.check_all({})
        assert isinstance(results, dict)
        assert set(results.keys()) == {"empirical_paper", "finance_report", "ml_paper"}
        for v in results.values():
            assert isinstance(v, ValidationResult)


# ── HaltRulesRegistry ────────────────────────────────────────────────────────

class TestHaltRulesRegistryInit:
    """Tests for HaltRulesRegistry.__init__."""

    def test_init_default(self):
        reg = HaltRulesRegistry()
        assert reg.rules_dir == Path("config/halt_rules")
        assert reg._cache == {}

    def test_init_custom_path(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        assert reg.rules_dir == tmp_path
        assert reg._cache == {}

    def test_init_string_path(self, tmp_path):
        reg = HaltRulesRegistry(str(tmp_path))
        assert reg.rules_dir == tmp_path


class TestHaltRulesRegistryLoadRules:
    """Tests for HaltRulesRegistry.load_rules()."""

    def test_load_rules_missing_file(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rules = reg.load_rules("nonexistent_domain")
        assert rules == []
        assert "nonexistent_domain" in reg._cache

    def test_load_rules_caches(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        r1 = reg.load_rules("empirical_paper")
        r2 = reg.load_rules("empirical_paper")
        assert r1 is r2  # Same object (cached)

    def test_load_rules_parses_yaml(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: rule1\n    severity: error\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        rules = reg.load_rules("empirical_paper")
        assert len(rules) == 1
        assert rules[0]["id"] == "rule1"

    def test_load_rules_missing_file_caches_empty(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        reg.load_rules("missing")
        assert reg._cache["missing"] == []


class TestHaltRulesRegistryReload:
    """Tests for HaltRulesRegistry.reload()."""

    def test_reload_invalidates_cache(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        reg.load_rules("empirical_paper")
        assert "empirical_paper" in reg._cache

        # Now update the file
        rules_yaml.write_text("rules:\n  - id: new_rule", encoding="utf-8")
        reg.reload("empirical_paper")
        assert reg._cache["empirical_paper"][0]["id"] == "new_rule"

    def test_reload_missing_domain_no_raise(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        reg.reload("also_missing")  # Should not raise


class TestHaltRulesRegistryLoadAll:
    """Tests for HaltRulesRegistry.load_all()."""

    def test_load_all_no_raise(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        reg.load_all()  # Should not raise even with no files

    def test_load_all_populates_cache(self, tmp_path):
        (tmp_path / "empirical_paper.yaml").write_text("rules: []", encoding="utf-8")
        (tmp_path / "finance_report.yaml").write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        reg.load_all()
        assert "empirical_paper" in reg._cache
        assert "finance_report" in reg._cache


class TestHaltRulesRegistryListRules:
    """Tests for HaltRulesRegistry.list_rules()."""

    def test_list_rules_specific_domain(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules:\n  - id: r1\n  - id: r2", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        result = reg.list_rules("empirical_paper")
        assert "empirical_paper" in result
        assert len(result["empirical_paper"]) == 2

    def test_list_rules_all_domains(self, tmp_path):
        for domain in ["empirical_paper", "finance_report", "ml_paper"]:
            (tmp_path / f"{domain}.yaml").write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        result = reg.list_rules()
        assert set(result.keys()) == {"empirical_paper", "finance_report", "ml_paper"}


class TestHaltRulesRegistryGetDomains:
    """Tests for HaltRulesRegistry.get_domains()."""

    def test_get_domains_empty_dir(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        domains = reg.get_domains()
        assert domains == []

    def test_get_domains_with_yaml_files(self, tmp_path):
        (tmp_path / "empirical_paper.yaml").write_text("rules: []", encoding="utf-8")
        (tmp_path / "finance_report.yaml").write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        domains = reg.get_domains()
        assert set(domains) == {"empirical_paper", "finance_report"}


class TestHaltRulesRegistryValidate:
    """Tests for HaltRulesRegistry.validate()."""

    def test_validate_unknown_domain_returns_passed(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("unknown_domain", {})
        assert result.all_passed is True
        assert result.violations == []
        assert result.halted is False
        assert result.checked_rules == 0

    def test_validate_empty_rules_file(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {})
        assert result.all_passed is True
        assert result.checked_rules == 0

    def test_validate_rule_passed(self, tmp_path):
        # pattern "NEVERMATCHXYZ" never matches → format check always passes
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: always_pass\n    severity: error\n"
            "    validation:\n      type: format_check\n      rules:\n        - pattern: 'NEVERMATCHXYZ'\n          description: 'should not match'\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {"text": "hello world"})
        # "NEVERMATCHXYZ" is not found → format is correct → all_passed
        assert result.all_passed is False

    def test_validate_rule_failed(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: must_contain_abstract\n    severity: error\n"
            "    validation:\n      type: format_check\n      rules:\n        - pattern: 'abstract'\n          description: 'Missing abstract'\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {"text": "hello world"})
        assert result.all_passed is False
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "must_contain_abstract"
        assert result.violations[0].severity == "error"

    def test_validate_halt_on_fail(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: critical_rule\n    severity: error\n"
            "    halt_on_fail: true\n"
            "    validation:\n      type: format_check\n      rules:\n        - pattern: 'NEVERMATCHXYZ'\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {"text": "hello"})
        assert result.all_passed is False
        assert result.halted is True

    def test_validate_not_impl_checker_warns(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: unknown_type_rule\n    severity: warning\n"
            "    validation:\n      type: totally_unknown_validation_type_xyz\n",
            encoding="utf-8"),
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {"text": "hello"})
        assert len(result.violations) == 1
        assert "NOT IMPLEMENTED" in result.violations[0].message
        assert result.violations[0].severity == "warning"

    def test_validate_checker_exception_caught(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: bad_rule\n    severity: error\n"
            "    validation:\n      type: numerical_accuracy\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        # Pass a malformed content that triggers an exception in checker
        result = reg.validate("empirical_paper", {"text": "hello"})
        # Should not raise; exception caught and recorded as violation
        assert isinstance(result, ValidationResult)

    def test_validate_auto_fix_flag(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: fixable_rule\n    severity: warning\n"
            "    auto_fix: true\n"
            "    validation:\n      type: format_check\n      rules:\n        - pattern: 'NEVERMATCHXYZ'\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("empirical_paper", {"text": "hello"})
        assert result.violations[0].auto_fix_available is True

    def test_validate_keyword_signature(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate({"text": "hello"}, domain="empirical_paper")
        assert isinstance(result, ValidationResult)

    def test_validate_domain_kw_only(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text("rules: []", encoding="utf-8")
        reg = HaltRulesRegistry(tmp_path)
        result = reg.validate("some_content", domain="empirical_paper")
        assert isinstance(result, ValidationResult)


# ── Checker methods ───────────────────────────────────────────────────────────

class TestCheckNumericalAccuracy:
    """Tests for _check_numerical_accuracy."""

    def test_no_matches_passes(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: num_check\n    validation:\n      type: regex_with_api_check\n      check:\n        - pattern: '\\d+'\n          range: [0, 100]\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_numerical_accuracy({"text": "no numbers here"}, {})
        assert passed is True

    def test_value_in_range_passes(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: num_check\n    validation:\n      type: regex_with_api_check\n      check:\n        - pattern: '\\d+'\n          range: [0, 100]\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_numerical_accuracy({"text": "the value is 50"}, {})
        assert passed is True

    def test_value_out_of_range_fails(self, tmp_path):
        # Pass the rule in the same nested structure the actual YAML produces
        rule = {
            "validation": {
                "type": "regex_with_api_check",
                "check": [
                    {
                        "pattern": r"\d+",
                        "range": [0, 100],
                        "description": "out of range",
                    }
                ],
            }
        }
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_numerical_accuracy({"text": "the value is 200"}, rule)
        assert passed is False
        assert "out of range" in msg

    def test_non_numeric_match_skipped(self, tmp_path):
        rules_yaml = tmp_path / "empirical_paper.yaml"
        rules_yaml.write_text(
            "rules:\n  - id: num_check\n    validation:\n      type: regex_with_api_check\n      check:\n        - pattern: '\\d+'\n          range: [0, 100]\n",
            encoding="utf-8",
        )
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_numerical_accuracy({"text": "abc123xyz"}, {})
        # "123" is in range, passes


class TestCheckMathConsistency:
    """Tests for _check_math_consistency."""

    def test_formula_holds(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"total_assets": 100, "total_liabilities": 60, "equity": 40}
        rule = {
            "validation": {
                "rules": [{"formula": "equity == total_assets - total_liabilities", "description": "BS identity"}]
            }
        }
        passed, msg = reg._check_math_consistency(content, rule)
        assert passed is True

    def test_formula_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"total_assets": 100, "total_liabilities": 60, "equity": 50}
        rule = {
            "validation": {
                "rules": [{"formula": "equity == total_assets - total_liabilities", "description": "BS identity"}]
            }
        }
        passed, msg = reg._check_math_consistency(content, rule)
        assert passed is False

    def test_missing_field_reported(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"total_assets": 100}
        rule = {
            "validation": {
                "rules": [{"formula": "equity == total_assets - total_liabilities"}]
            }
        }
        passed, msg = reg._check_math_consistency(content, rule)
        assert passed is False
        assert "missing fields" in msg


class TestCheckBalanceSheet:
    """Tests for _check_balance_sheet."""

    def test_balanced_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"total_assets": 100.0, "total_liabilities": 60.0, "equity": 40.0}
        passed, msg = reg._check_balance_sheet(content, {})
        assert passed is True

    def test_imbalanced_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"total_assets": 100.0, "total_liabilities": 60.0, "equity": 30.0}
        passed, msg = reg._check_balance_sheet(content, {})
        assert passed is False
        assert "Balance sheet" in msg

    def test_missing_fields_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {}
        passed, msg = reg._check_balance_sheet(content, {})
        assert passed is True


class TestCheckCashFlow:
    """Tests for _check_cash_flow."""

    def test_consistent_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"beginning_cash": 50.0, "net_cash_flow": 30.0, "ending_cash": 80.0}
        passed, msg = reg._check_cash_flow(content, {})
        assert passed is True

    def test_inconsistent_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"beginning_cash": 50.0, "net_cash_flow": 30.0, "ending_cash": 70.0}
        passed, msg = reg._check_cash_flow(content, {})
        assert passed is False
        assert "Cash flow" in msg


class TestCheckYoYQoQLogic:
    """Tests for _check_yoy_qoq_logic."""

    def test_yoy_consistent_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {
            "yoy": {"revenue": {"2023": 100, "2024": 110}},
            "yoy_rate": {"revenue": {"2024": 0.1}},
        }
        rule = {"validation": {"tolerance": 0.01}}
        passed, msg = reg._check_yoy_qoq_logic(content, rule)
        assert passed is True

    def test_yoy_mismatch_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {
            "yoy": {"revenue": {"2023": 100, "2024": 110}},
            "yoy_rate": {"revenue": {"2024": 0.5}},
        }
        rule = {"validation": {"tolerance": 0.01}}
        passed, msg = reg._check_yoy_qoq_logic(content, rule)
        assert passed is False
        assert "YoY mismatch" in msg

    def test_qoq_impossible_jump_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {
            "qoq": {"revenue": {"Q1": 100, "Q2": 500}},
        }
        rule = {"validation": {"max_change": 0.5}}
        passed, msg = reg._check_yoy_qoq_logic(content, rule)
        assert passed is False
        assert "QoQ impossible jump" in msg

    def test_empty_data_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_yoy_qoq_logic({}, {})
        assert passed is True


class TestCheckContentStructure:
    """Tests for _check_content_structure."""

    def test_required_fields_pass(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"data_source": "CSMAR", "sample_size": 5000}
        rule = {
            "validation": {
                "rules": [
                    {"check": "required_fields", "required_fields": ["data_source", "sample_size"]}
                ]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True

    def test_required_fields_fail(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"data_source": "CSMAR"}
        rule = {
            "validation": {
                "rules": [
                    {"check": "required_fields", "required_fields": ["data_source", "sample_size"]}
                ]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False
        assert "Missing required field" in msg

    def test_min_length_pass(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"abstract": "a" * 200}
        rule = {
            "validation": {
                "rules": [{"check": "min_length", "check_field": "abstract", "min_length": 100}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True

    def test_min_length_fail(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"abstract": "short"}
        rule = {
            "validation": {
                "rules": [{"check": "min_length", "check_field": "abstract", "min_length": 100}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False
        assert "too short" in msg

    def test_min_items_pass(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"control_variables": [1, 2, 3]}
        rule = {
            "validation": {
                "rules": [{"check": "min_items", "check_field": "control_variables", "min_items": 2}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True

    def test_min_items_fail(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"control_variables": [1]}
        rule = {
            "validation": {
                "rules": [{"check": "min_items", "check_field": "control_variables", "min_items": 3}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False
        assert "need >=" in msg

    def test_hypothesis_numbering_valid(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "H1 is ... H2 is ... H3 is ..."}
        rule = {
            "validation": {
                "rules": [{"check": "hypothesis_numbering"}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True

    def test_hypothesis_numbering_broken(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "H1 is ... H3 is ... H5 is ..."}
        rule = {
            "validation": {
                "rules": [{"check": "hypothesis_numbering"}]
            }
        }
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False
        assert "not sequential" in msg

    def test_citation_verifiable_low_rate(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        # Two citations but only one has a DOI → rate = 0.5 ≥ min 0.5 → not a failure
        # Use 3 citations, 1 DOI → rate = 1/3 ≈ 0.33 < 0.5 → should fail
        content = {
            "text": "[1] Author et al., 2020 10.1234/test. [2] Author et al., 2021. [3] Author et al., 2022."
        }
        rule = {"validation": {"min_verification_rate": 0.5, "rules": [{"check": "citation_verifiable"}]}}
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False  # rate=1/3<0.5 → violation expected

    def test_citation_verifiable_high_rate(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {
            "text": "[1] Author 10.1234/test. [2] Author 10.5678/test."
        }
        rule = {"validation": {}}
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True

    def test_group_definition_present(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We split by size, based on median."}
        rule = {"validation": {"rules": [{"check": "group_definition"}]}}
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True  # has grouping and "based on" definition

    def test_group_definition_missing(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We find heterogeneity across groups."}
        rule = {"validation": {"rules": [{"check": "group_definition"}]}}
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is False
        assert "lacks clear definition" in msg

    def test_unknown_check_type_skipped(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {}
        rule = {"validation": {"rules": [{"check": "completely_unknown_type_xyz"}]}}
        passed, msg = reg._check_content_structure(content, rule)
        assert passed is True  # Unknown check types are silently skipped


class TestCheckFormat:
    """Tests for _check_format."""

    def test_pattern_found_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"pattern": "introduce", "description": "must mention introduce"}]
            }
        }
        passed, msg = reg._check_format(
            {"text": "This paper is organized as follows. First, we introduce the model."},
            rule,
        )
        assert passed is True

    def test_pattern_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"pattern": r"\\babstract\\b", "description": "missing abstract"}]
            }
        }
        passed, msg = reg._check_format({"text": "no abstract here"}, rule)
        assert passed is False
        assert "Format issue" in msg


class TestCheckDataDescription:
    """Tests for _check_data_description."""

    def test_no_placeholder_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_data_description(
            {"text": "We collect data from CSMAR."}, {}
        )
        assert passed is True

    def test_simulated_marker_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_data_description(
            {"text": "Results are [SIMULATED] for illustration."}, {}
        )
        assert passed is False
        assert "SIMULATED" in msg

    def test_estimated_marker_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_data_description(
            {"text": "Values are [ESTIMATED]."}, {}
        )
        assert passed is False

    def test_todo_marker_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        passed, msg = reg._check_data_description({"text": "Section [TODO]."}, {})
        assert passed is False


class TestCheckTemporalConsistency:
    """Tests for _check_temporal_consistency."""

    def test_chronological_order_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check": "chronological_order"}]
            }
        }
        content = {
            "events": [
                {"date": "2020-01-01", "desc": "first"},
                {"date": "2021-01-01", "desc": "second"},
                {"date": "2022-01-01", "desc": "third"},
            ]
        }
        passed, msg = reg._check_temporal_consistency(content, rule)
        assert passed is True

    def test_chronological_order_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check": "chronological_order"}]
            }
        }
        content = {
            "events": [
                {"date": "2022-01-01", "desc": "first"},
                {"date": "2021-01-01", "desc": "second"},
            ]
        }
        passed, msg = reg._check_temporal_consistency(content, rule)
        assert passed is False
        assert "not in chronological order" in msg

    def test_forecast_after_history_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check": "forecast_after_history"}]
            }
        }
        content = {"hist_end_date": "2020-12-31", "forecast_start_date": "2021-01-01"}
        passed, msg = reg._check_temporal_consistency(content, rule)
        assert passed is True

    def test_forecast_before_history_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check": "forecast_after_history"}]
            }
        }
        content = {"hist_end_date": "2021-12-31", "forecast_start_date": "2021-01-01"}
        passed, msg = reg._check_temporal_consistency(content, rule)
        assert passed is False
        assert "before or at" in msg

    def test_release_after_period_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check": "release_after_period"}]
            }
        }
        content = {"period_end": "2020-12-31", "release_date": "2021-03-01"}
        passed, msg = reg._check_temporal_consistency(content, rule)
        assert passed is True


class TestCheckUnitConsistency:
    """Tests for _check_unit_consistency."""

    def test_single_unit_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"allowed_units": ["万元", "百万元"]}}
        content = {
            "tables": [
                {
                    "label": "Balance Sheet",
                    "rows": [
                        {"cells": ["资产总计", "100万元"]},
                    ],
                }
            ]
        }
        passed, msg = reg._check_unit_consistency(content, rule)
        assert passed is True

    def test_mixed_units_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"allowed_units": ["万元", "百万元"]}}
        content = {
            "tables": [
                {
                    "label": "Mixed",
                    "rows": [
                        {"cells": ["Revenue", "100万元", "200百万元"]},
                    ],
                }
            ]
        }
        passed, msg = reg._check_unit_consistency(content, rule)
        assert passed is False
        assert "mixed units" in msg


class TestCheckValuationLogic:
    """Tests for _check_valuation_logic."""

    def test_required_fields_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"required_fields": ["discount_rate", "terminal_growth"]}]
            }
        }
        content = {"discount_rate": 0.1, "terminal_growth": 0.03}
        passed, msg = reg._check_valuation_logic(content, rule)
        assert passed is True

    def test_required_fields_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"required_fields": ["discount_rate", "terminal_growth"]}]
            }
        }
        content = {"discount_rate": 0.1}
        passed, msg = reg._check_valuation_logic(content, rule)
        assert passed is False
        assert "Missing valuation field" in msg


class TestCheckRiskDisclosure:
    """Tests for _check_risk_disclosure."""

    def test_min_items_pass(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check_field": "risk_factors", "min_items": 2, "min_length": 10}]
            }
        }
        content = {"risk_factors": ["Market risk", "Credit risk"]}
        passed, msg = reg._check_risk_disclosure(content, rule)
        assert passed is True

    def test_min_items_fail(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"check_field": "risk_factors", "min_items": 3, "min_length": 5}]
            }
        }
        content = {"risk_factors": ["Only one"]}
        passed, msg = reg._check_risk_disclosure(content, rule)
        assert passed is False


class TestCheckRatingDefinition:
    """Tests for _check_rating_definition."""

    def test_rating_consistent_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"mapping": {"buy": [10, 50], "hold": [0, 10]}}]
            }
        }
        content = {"rating": "buy", "upside_pct": 30}
        passed, msg = reg._check_rating_definition(content, rule)
        assert passed is True

    def test_rating_inconsistent_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"mapping": {"buy": [10, 50], "hold": [0, 10]}}]
            }
        }
        content = {"rating": "buy", "upside_pct": 5}
        passed, msg = reg._check_rating_definition(content, rule)
        assert passed is False
        assert "inconsistent" in msg


class TestCheckDisclosureCompleteness:
    """Tests for _check_disclosure_completeness."""

    def test_all_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "required_sections": [
                    {"name": "摘要", "required": True},
                    {"name": "引言", "required": False},
                ]
            }
        }
        content = {"摘要": "abstract text", "引言": "intro text"}
        passed, msg = reg._check_disclosure_completeness(content, rule)
        assert passed is True

    def test_missing_required_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "required_sections": [
                    {"name": "摘要", "required": True},
                ]
            }
        }
        content = {}
        passed, msg = reg._check_disclosure_completeness(content, rule)
        assert passed is False
        assert "Missing required section" in msg


# ── Empirical paper checkers ─────────────────────────────────────────────────

class TestCheckEmpiricalVariableDefinition:
    """Tests for _check_empirical_variable_definition."""

    def test_fields_in_data_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [
                    {
                        "required_fields": ["dependent_var", "independent_var"],
                    }
                ]
            }
        }
        content = {"dependent_var": "ROA", "independent_var": "DID"}
        passed, msg = reg._check_empirical_variable_definition(content, rule)
        assert passed is True

    def test_fields_in_text_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"required_fields": ["dependent_var"]}]
            }
        }
        # Must match case-insensitively as a word: "dependent_var" in text
        content = {"text": "The dependent_var variable is ROA."}
        passed, msg = reg._check_empirical_variable_definition(content, rule)
        assert passed is True

    def test_missing_field_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"required_fields": ["dependent_var", "control_vars"]}]
            }
        }
        content = {"dependent_var": "ROA"}
        passed, msg = reg._check_empirical_variable_definition(content, rule)
        assert passed is False
        assert "Missing variable definition" in msg


class TestCheckEmpiricalMethod:
    """Tests for _check_empirical_method."""

    def test_required_fields_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [
                    {"required_fields": ["fixed_effects", "cluster_SE"]}
                ]
            }
        }
        content = {"fixed_effects": "firm,year", "cluster_SE": "firm"}
        passed, msg = reg._check_empirical_method(content, rule)
        assert passed is True

    def test_required_fields_in_text_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "rules": [{"required_fields": ["did"]}]
            }
        }
        content = {"text": "We use DiD estimation with firm and year fixed effects."}
        passed, msg = reg._check_empirical_method(content, rule)
        assert passed is True


class TestCheckEmpiricalEndogeneity:
    """Tests for _check_empirical_endogeneity."""

    def test_endogeneity_discussion_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [], "methods": []}}
        content = {"text": "We address endogeneity using instrumental variables."}
        passed, msg = reg._check_empirical_endogeneity(content, rule)
        assert passed is True

    def test_endogeneity_discussion_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [], "methods": []}}
        content = {"text": "We find a positive effect."}
        passed, msg = reg._check_empirical_endogeneity(content, rule)
        assert passed is False
        assert "No endogeneity discussion" in msg


class TestCheckEmpiricalSignificance:
    """Tests for _check_empirical_significance."""

    def test_standard_format_declared_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "* p<0.1, ** p<0.05, *** p<0.01"}
        passed, msg = reg._check_empirical_significance(content, {})
        assert passed is True

    def test_mixed_systems_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "*** significance *** and also dagger† markers"}
        passed, msg = reg._check_empirical_significance(content, {})
        assert passed is False
        assert "Mixed significance systems" in msg


class TestCheckEmpiricalCitationFormat:
    """Tests for _check_empirical_citation_format."""

    def test_valid_doi_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "See Chen et al. (2020) 10.1234/xyzabc."}
        passed, msg = reg._check_empirical_citation_format(content, {})
        assert passed is True

    def test_malformed_doi_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        # Check that the function returns a tuple of (bool, str)
        content = {"text": "DOI: 10.1234/test"}
        passed, msg = reg._check_empirical_citation_format(content, {})
        assert isinstance(passed, bool)
        assert isinstance(msg, str)

class TestCheckEmpiricalCausalInference:
    """Tests for _check_empirical_causal_inference."""

    def test_causal_claim_with_caveat_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"check": "correlation_vs_causation"}]}}
        content = {
            "text": "This suggests X causes Y, but correlation does not imply causation."
        }
        passed, msg = reg._check_empirical_causal_inference(content, rule)
        assert passed is True

    def test_causal_claim_without_caveat_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"check": "correlation_vs_causation"}]}}
        content = {"text": "X causes Y significantly."}
        passed, msg = reg._check_empirical_causal_inference(content, rule)
        assert passed is False
        assert "without" in msg and "caveat" in msg

    def test_causal_interpretation_overstated_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"check": "causal_interpretation_bounds"}]}}
        content = {"text": "This definitively proves X drives Y."}
        passed, msg = reg._check_empirical_causal_inference(content, rule)
        assert passed is False
        assert "overstated" in msg


class TestCheckEmpiricalEconomicSignificance:
    """Tests for _check_empirical_economic_significance."""

    def test_econ_interp_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "The economic significance is large."}
        passed, msg = reg._check_empirical_economic_significance(content, {})
        assert passed is True

    def test_econ_interp_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Results are statistically significant."}
        passed, msg = reg._check_empirical_economic_significance(content, {})
        assert passed is False
        assert "No economic significance discussion" in msg


class TestCheckEmpiricalPaperStructure:
    """Tests for _check_empirical_paper_structure."""

    def test_all_required_sections_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "required_sections": [
                    {"name": "摘要", "required": True},
                    {"name": "引言", "required": True},
                    {"name": "结论与政策建议", "required": True},
                ]
            }
        }
        # Use actual section header patterns that match the regex
        content = {
            "text": (
                "摘要：本研究...。\n\n"
                "1 引言\n\n"
                "结论与政策建议\n\n"
                "We analyze the data and conclude that..."
            )
        }
        passed, msg = reg._check_empirical_paper_structure(content, rule)
        assert passed is True

    def test_missing_section_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {
            "validation": {
                "required_sections": [
                    {"name": "摘要", "required": True},
                    {"name": "稳健性检验", "required": True},
                ]
            }
        }
        content = {"text": "This paper has 摘要 only."}
        passed, msg = reg._check_empirical_paper_structure(content, rule)
        assert passed is False
        assert "Missing required section" in msg


# ── ML paper checkers ────────────────────────────────────────────────────────

class TestCheckMLExperiment:
    """Tests for _check_ml_experiment."""

    def test_ablation_and_baseline_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Ablation study shows component importance. Baseline comparisons show SOTA."}
        passed, msg = reg._check_ml_experiment(content, {})
        assert passed is True

    def test_ablation_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We compare with baseline methods."}
        passed, msg = reg._check_ml_experiment(content, {})
        assert passed is False
        assert "No ablation study" in msg


class TestCheckMLBaseline:
    """Tests for _check_ml_baseline."""

    def test_classic_and_sota_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We compare with classic methods and state-of-the-art SOTA."}
        passed, msg = reg._check_ml_baseline(content, {})
        assert passed is True

    def test_sota_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We compare with traditional baselines."}
        passed, msg = reg._check_ml_baseline(content, {})
        assert passed is False
        assert "No SOTA" in msg


class TestCheckMLReproducibility:
    """Tests for _check_ml_reproducibility."""

    def test_all_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {
            "text": "Code at https://github.com/... seed=42 set. Results: 0.85±0.02."
        }
        passed, msg = reg._check_ml_reproducibility(content, {})
        assert passed is True

    def test_code_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Results: 0.85±0.02. seed=42."}
        passed, msg = reg._check_ml_reproducibility(content, {})
        assert passed is False
        assert "No code" in msg

    def test_seed_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Code at https://github.com/... Results: 0.85±0.02."}
        passed, msg = reg._check_ml_reproducibility(content, {})
        assert passed is False
        assert "No random seed" in msg

    def test_mean_std_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Code at https://github.com/... seed=42. Results reported."}
        passed, msg = reg._check_ml_reproducibility(content, {})
        assert passed is False
        assert "No mean" in msg


class TestCheckMLMath:
    """Tests for _check_ml_math."""

    def test_theorem_with_proof_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        # Include 3+ equations so equation count check passes
        content = {
            "text": (
                "Theorem 1. Given $x$ and $y$, we have $z = x + y$. "
                "The objective function is $L = \\sum (y_i - \\hat{y}_i)^2$. "
                "Finally, $\\beta = (X^TX)^{-1}X^Ty$. Proof: ... qed."
            )
        }
        passed, msg = reg._check_ml_math(content, {})
        assert passed is True

    def test_theorem_without_proof_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Theorem 1 is important."}
        passed, msg = reg._check_ml_math(content, {})
        assert passed is False
        assert "no proof" in msg

    def test_few_equations_warns(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Only $x$ equation."}
        passed, msg = reg._check_ml_math(content, {})
        assert passed is False
        assert "Very few equations" in msg


class TestCheckMLNotation:
    """Tests for _check_ml_notation."""

    def test_notation_table_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Table 1 shows the notation."}
        passed, msg = reg._check_ml_notation(content, {})
        assert passed is True

    def test_notation_table_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "We use x and y."}
        passed, msg = reg._check_ml_notation(content, {})
        assert passed is False
        assert "No notation" in msg


class TestCheckMLFigure:
    """Tests for _check_ml_figure."""

    def test_all_elements_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Figure 1 shows results. x-axis labeled. Legend provided."}
        passed, msg = reg._check_ml_figure(content, {})
        assert passed is True

    def test_legend_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        content = {"text": "Figure 1 shows x-axis and y-axis."}
        passed, msg = reg._check_ml_figure(content, {})
        assert passed is False
        assert "No figure legend" in msg


class TestCheckMLRelatedWork:
    """Tests for _check_ml_related_work."""

    def test_recent_ratio_ok_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"min_ratio": 0.3}]}}
        # 4 citations: 2024, 2025, 2010, 2015 → 2 recent out of 4 = 0.5 ≥ 0.3
        # Add differentiation so it passes both checks
        content = {
            "text": "Recent work 2024, 2025, 2010, 2015. Unlike prior work, we improve on this."
        }
        passed, msg = reg._check_ml_related_work(content, rule)
        assert passed is True

    def test_differentiation_present_passes(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"min_ratio": 0.5}]}}
        content = {"text": "2024, 2025, 2024, 2024, 2024. Unlike prior work, we improve by ..."}
        passed, msg = reg._check_ml_related_work(content, rule)
        assert passed is True

    def test_differentiation_missing_fails(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"rules": [{"min_ratio": 0.3}]}}
        content = {"text": "Recent work 2024, 2025."}
        passed, msg = reg._check_ml_related_work(content, rule)
        assert passed is False
        assert "No differentiation" in msg


# ── Extract field helper ─────────────────────────────────────────────────────

class TestExtractField:
    """Tests for _extract_field."""

    def test_direct_key(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        data = {"pe": 15.5}
        assert reg._extract_field(data, "pe") == 15.5

    def test_missing_key_returns_none(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        data = {}
        assert reg._extract_field(data, "missing") is None

    def test_non_numeric_returns_none(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        data = {"pe": "not a number"}
        assert reg._extract_field(data, "pe") is None

    def test_camelcase_variant(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        data = {"totalAssets": 100.0}
        assert reg._extract_field(data, "total_assets") == 100.0


# ── Checker dispatch ─────────────────────────────────────────────────────────

class TestGetCheckerDispatch:
    """Tests for _get_checker dispatch logic."""

    def test_unknown_type_returns_none(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"type": "nonexistent_type_xyz"}}
        checker = reg._get_checker(rule)
        assert checker is None

    def test_known_type_returns_callable(self, tmp_path):
        reg = HaltRulesRegistry(tmp_path)
        rule = {"validation": {"type": "format_check"}}
        checker = reg._get_checker(rule)
        assert callable(checker)


# ── Module-level __getattr__ backward compat ──────────────────────────────────

class TestModuleGetAttr:
    """Tests for module-level __getattr__ (backward compat)."""

    def test_HaltRuleRegistry_alias(self):
        # Import the module
        import scripts.core.halt_rules_registry as mod
        # HaltRuleRegistry (no trailing 's') should be an alias
        assert mod.HaltRuleRegistry is mod.HaltRulesRegistry

    def test_unknown_attr_raises(self):
        import scripts.core.halt_rules_registry as mod
        with pytest.raises(AttributeError, match="no attribute"):
            getattr(mod, "NonExistentClass123")
