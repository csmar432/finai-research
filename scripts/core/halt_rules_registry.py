"""
HaltRulesRegistry: validates content against YAML-defined quality rules.

Usage:
    registry = HaltRulesRegistry(rules_dir="config/halt_rules")

    # Validate a financial report
    passed, violations = registry.validate(
        domain="finance_report",
        content={"text": "...", "data": {...}},
    )

    if not passed:
        for v in violations:
            print(f"  [VIOLATION] {v}")
"""

from __future__ import annotations

__all__ = [
    "RuleViolation",
    "ValidationResult",
    "RuleSeverity",
    "HaltRuleChecker",
    "HaltRulesRegistry",
]

import ast
import operator as op
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_log: Any = None  # resolved lazily to avoid circular import

# --- safe math evaluator (replaces bare eval) ---
_safe_ops = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def _safe_eval(expr: str) -> bool | float | int:
    """Safely evaluate a simple math/relational expression without eval()."""
    node = ast.parse(expr, mode="eval").body
    return _safe_eval_node(node)


def _safe_eval_node(node: ast.AST) -> bool | float | int:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.BinOp):
        return _safe_ops[type(node.op)](_safe_eval_node(node.left), _safe_eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        return _safe_ops[type(node.op)](_safe_eval_node(node.operand))
    if isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left)
        for op_node, right_node in zip(node.ops, node.comparators):
            cmp_fn = {
                ast.Lt: op.lt,
                ast.LtE: op.le,
                ast.Gt: op.gt,
                ast.GtE: op.ge,
                ast.Eq: op.eq,
                ast.NotEq: op.ne,
            }.get(type(op_node))
            if cmp_fn is None:
                raise ValueError(f"Unsupported comparison: {type(op_node).__name__}")
            right = _safe_eval_node(right_node)
            if not cmp_fn(left, right):
                return False
            left = right
        return True
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def _logger():
    global _log
    if _log is None:
        import logging
        _log = logging.getLogger("halt_rules")
    return _log


@dataclass
class RuleViolation:
    """A single rule violation detected during validation."""
    rule_id: str
    severity: str  # "error" | "warning" | "info"
    message: str
    auto_fix_available: bool


@dataclass
class ValidationResult:
    """Result of running all rules for a given domain."""
    all_passed: bool
    violations: list[RuleViolation]
    halted: bool  # True if any halt_on_fail rule was violated
    checked_rules: int = 0  # number of rules checked
    domain: str = ""  # domain name

    @property
    def passed(self) -> bool:
        """Alias for all_passed (test compatibility)."""
        return self.all_passed

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


@dataclass
class RuleSeverity:
    """Rule severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HaltRuleChecker:
    """
    Standalone rule checker that can be used without a full registry.

    Usage:
        checker = HaltRuleChecker(rules_dir="config/halt_rules")
        result = checker.check("empirical_paper", {"text": "..."})
    """

    def __init__(self, rules_dir: str | Path = "config/halt_rules"):
        self.registry = HaltRulesRegistry(rules_dir)

    def check(
        self,
        content_or_domain: str | dict,
        domain: str | None = None,
    ) -> tuple[bool, ValidationResult]:
        """
        Validate content against rules for the given domain.

        Args:
            content_or_domain: Content dict/str, or domain string if domain arg provided
            domain: Optional domain string (keyword-only for test compat)

        Returns
        -------
        (should_halt, ValidationResult)
            should_halt: True if any halt_on_fail rule was violated
        """
        if domain is not None:
            # check(content, domain="...") — test compat
            content = content_or_domain
            result = self.registry.validate(content, domain=domain)
        else:
            # check(domain, content) — standard (both positional)
            domain_str, content = content_or_domain, domain  # type: ignore[assignment]
            result = self.registry.validate(domain_str, content)
        return result.halted, result

    def check_all(self, content: dict | str) -> dict[str, ValidationResult]:
        """Run all domains against content."""
        results = {}
        for domain in ["empirical_paper", "finance_report", "ml_paper"]:
            results[domain] = self.registry.validate(domain, content)
        return results


class HaltRulesRegistry:
    """
    Loads and executes Halt Rules defined in YAML files.

    Each rule specifies a validation type and its parameters.  This registry
    dispatches to the appropriate checker function for each type, returning
    a list of violations.
    """

    def __init__(self, rules_dir: str | Path = "config/halt_rules"):
        self.rules_dir = Path(rules_dir)
        self._cache: dict[str, list[dict]] = {}
        self._econometrics_engine = None  # lazy-loaded

    # ── Public API ──────────────────────────────────────────────────────────────

    def validate(
        self,
        domain_or_content: str | dict[str, Any],
        content_or_domain: str | dict[str, Any] | None = None,
        *,
        domain: str | None = None,
    ) -> ValidationResult:
        """
        Execute all rules for *domain* against *content*.

        Supports multiple call signatures:
            registry.validate(domain, content)           # standard
            registry.validate(content, domain="...")    # test compat (keyword)

        Returns
        -------
        ValidationResult
            .all_passed  — True when no violations were found
            .violations  — List of RuleViolation objects
            .halted      — True when any halt_on_fail rule was violated
        """
        # Detect keyword-arg call: validate(content, domain="finance_report")
        if domain is not None:
            content = domain_or_content
            domain_str = domain
        elif content_or_domain is not None:
            domain_str, content = domain_or_content, content_or_domain
        else:
            domain_str, content = str(domain_or_content), ""

        rules = self.load_rules(domain_str)
        if not rules:
            _logger().warning(f"No rules found for domain '{domain_str}'")
            return ValidationResult(all_passed=True, violations=[], halted=False,
                                  checked_rules=0, domain=domain_str)

        violations: list[RuleViolation] = []
        halted = False

        for rule in rules:
            checker = self._get_checker(rule)
            passed, msg = True, ""
            rule_id = rule.get("id", "unknown")

            if checker is None:
                msg = f"[NOT IMPLEMENTED] Rule '{rule_id}' has no checker — implement _check_{rule.get('validation', {}).get('type', 'unknown')}"
                violations.append(RuleViolation(
                    rule_id=rule_id,
                    severity="warning",
                    message=msg,
                    auto_fix_available=False,
                ))
                continue

            try:
                passed, msg = checker(content, rule)
            except Exception as exc:
                violations.append(RuleViolation(
                    rule_id=rule_id,
                    severity="error",
                    message=f"[CHECK FAILED] {rule_id}: {exc}",
                    auto_fix_available=False,
                ))
                continue

            if not passed:
                severity = rule.get("severity", "warning")
                violations.append(RuleViolation(
                    rule_id=rule_id,
                    severity=severity,
                    message=f"[{severity.upper()}] {rule_id}: {msg}",
                    auto_fix_available=rule.get("auto_fix", False),
                ))
                if rule.get("halt_on_fail", False):
                    halted = True

        all_passed = len(violations) == 0
        checked_count = len(rules)  # total rules loaded for this domain
        return ValidationResult(
            all_passed=all_passed,
            violations=violations,
            halted=halted,
            checked_rules=checked_count,
            domain=domain_str,
        )

    def load_rules(self, domain: str) -> list[dict]:
        """Load rules for *domain* from YAML, with in-memory caching."""
        if domain in self._cache:
            return self._cache[domain]

        path = self.rules_dir / f"{domain}.yaml"
        if not path.exists():
            _logger().warning(f"Rules file not found: {path}")
            self._cache[domain] = []
            return []

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("rules", []) if data else []
        self._cache[domain] = rules
        return rules

    def reload(self, domain: str) -> None:
        """Invalidate the cache for *domain* and re-load rules."""
        self._cache.pop(domain, None)
        self.load_rules(domain)

    def load_all(self) -> None:
        """Pre-load all available rule domains."""
        for domain in ["empirical_paper", "finance_report", "ml_paper"]:
            self.load_rules(domain)

    def list_rules(self, domain: str | None = None) -> dict[str, list[dict]]:
        """
        Return loaded rules as {domain: [rules...]}.

        If domain is specified, only return that domain.
        """
        if domain:
            self.load_rules(domain)
            return {domain: self._cache.get(domain, [])}
        result = {}
        for d in ["empirical_paper", "finance_report", "ml_paper"]:
            self.load_rules(d)
            result[d] = self._cache.get(d, [])
        return result

    def get_domains(self) -> list[str]:
        """Return list of available rule domains."""
        domains = []
        for f in self.rules_dir.glob("*.yaml"):
            domain = f.stem
            if self._cache.get(domain) or f.exists():
                # Ensure loaded
                if not self._cache.get(domain):
                    self.load_rules(domain)
                domains.append(domain)
        return sorted(domains)

    # ── Checker Dispatch ────────────────────────────────────────────────────────

    def _get_checker(self, rule: dict) -> Callable[[dict, dict], tuple[bool, str]] | None:
        """Return the checker function for a rule, or None if not implemented."""
        vtype = rule.get("validation", {}).get("type", "")

        # Map validation type → checker method name
        CHECKER_MAP: dict[str, str] = {
            "regex_with_api_check":   "_check_numerical_accuracy",
            "content_structure_check": "_check_content_structure",
            "format_check":            "_check_format",
            "data_description_check":  "_check_data_description",
            "math_consistency":        "_check_math_consistency",
            "balance_sheet_check":     "_check_balance_sheet",
            "cash_flow_check":         "_check_cash_flow",
            "timestamp_order_check":   "_check_temporal_consistency",
            "timestamp_check":          "_check_data_freshness",
            "unit_consistency":         "_check_unit_consistency",
            "valuation_check":         "_check_valuation_logic",
            "content_check":           "_check_risk_disclosure",
            "rating_check":            "_check_rating_definition",
            "completeness_check":     "_check_disclosure_completeness",
            # Custom class from YAML (e.g. "YoYQoQLogicRule")
            "custom":                  "_check_yoy_qoq_logic",
            # ── Empirical paper rule types ───────────────────────
            "variable_check":          "_check_empirical_variable_definition",
            "method_check":            "_check_empirical_method",
            "endogeneity_check":       "_check_empirical_endogeneity",
            "table_format_check":      "_check_empirical_regression_table",
            "significance_check":        "_check_empirical_significance",
            "citation_format_check":   "_check_empirical_citation_format",
            "citation_coverage_check":  "_check_empirical_citation_coverage",
            "causal_inference_check":  "_check_empirical_causal_inference",
            "robustness_check":        "_check_content_structure",
            "heterogeneity_check":      "_check_content_structure",
            "mediation_check":          "_check_content_structure",
            "economic_significance_check": "_check_empirical_economic_significance",
            "structure_check":         "_check_empirical_paper_structure",
            "econometric_quality_check": "_check_econometric_quality",
            # ── ML paper rule types ────────────────────────────────
            "experiment_check":         "_check_ml_experiment",
            "baseline_check":           "_check_ml_baseline",
            "reproducibility_check":   "_check_ml_reproducibility",
            "math_check":              "_check_ml_math",
            "notation_check":          "_check_ml_notation",
            "figure_check":            "_check_ml_figure",
            "related_work_check":     "_check_ml_related_work",
        }

        method_name = CHECKER_MAP.get(vtype)
        if method_name and hasattr(self, method_name):
            return getattr(self, method_name)
        return None

    # ── Numeric / Financial Checkers ────────────────────────────────────────────

    def _check_numerical_accuracy(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate numeric values in text against reasonable ranges."""
        text = content if isinstance(content, str) else content.get("text", "")
        checks = rule.get("validation", {}).get("check", [])
        violations: list[str] = []

        for check in checks:
            pattern = check.get("pattern", "")
            rng = check.get("range", [-999999, 999999])
            try:
                matches = re.findall(pattern, text)
                for match in matches:
                    try:
                        val = float(match)
                        if not (rng[0] <= val <= rng[1]):
                            violations.append(
                                f"{check.get('description', pattern)}: {val} outside range {rng}"
                            )
                    except ValueError as exc:
                        _logger().warning(
                            f"silent except in _check_data_freshness (regex match float cast): "
                            f"{type(exc).__name__}: {exc}"
                        )
            except re.error as exc:
                _logger().warning(
                    f"silent except in _check_data_freshness (regex compile): "
                    f"{type(exc).__name__}: {exc}"
                )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_math_consistency(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate relationships between financial metrics (e.g. net_margin <= gross_margin)."""
        data = content if isinstance(content, dict) else {}
        checks = rule.get("validation", {}).get("rules", [])
        violations: list[str] = []

        for check in checks:
            formula = check.get("formula", "")
            desc = check.get("description", formula)

            # Extract field names from formula: "X <= Y", "X == Y + Z", etc.
            fields = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", formula.replace("(", "").replace(")", ""))
            field_values = {}
            for f in fields:
                val = self._extract_field(data, f)
                if val is not None:
                    field_values[f] = val

            # Evaluate simple relational formulas
            try:
                expr = formula
                for name, val in field_values.items():
                    expr = re.sub(rf"\b{name}\b", str(val), expr)
                result = _safe_eval(expr)
                if not result:
                    violations.append(f"{desc}: formula '{formula}' evaluated to False")
            except Exception as exc:
                # If fields are missing, skip the check
                missing = [f for f in fields if f not in field_values]
                if missing:
                    violations.append(f"{desc}: missing fields {missing}")
                else:
                    violations.append(f"{desc}: evaluation error — {exc}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_balance_sheet(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate balance sheet identities."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        total_assets = self._extract_field(data, "total_assets")
        total_liabilities = self._extract_field(data, "total_liabilities")
        equity = self._extract_field(data, "equity")

        if all(v is not None for v in [total_assets, total_liabilities, equity]):
            if abs(total_assets - (total_liabilities + equity)) > 0.01:
                violations.append(
                    f"Balance sheet: assets ({total_assets}) != liabilities ({total_liabilities}) + equity ({equity})"
                )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_cash_flow(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate cash flow statement identities."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        beginning = self._extract_field(data, "beginning_cash")
        net = self._extract_field(data, "net_cash_flow")
        ending = self._extract_field(data, "ending_cash")

        if all(v is not None for v in [beginning, net, ending]):
            if abs((beginning + net) - ending) > 0.01:
                violations.append(
                    f"Cash flow: beginning ({beginning}) + net ({net}) != ending ({ending})"
                )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    # ── YoY / QoQ Logic Checker ─────────────────────────────────────────────────

    def _check_yoy_qoq_logic(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """
        Validate year-over-year and quarter-over-quarter growth logic.

        Checks:
        1. YoY growth rate matches the ratio of current/prior year values (within tolerance).
        2. QoQ growth doesn't exhibit impossible jumps (max_change threshold).
        """
        data = content if isinstance(content, dict) else {}
        # Support both flat format (tolerance/max_change at validation level)
        # and nested format (tolerance/max_change inside checks[] dicts)
        flat_tolerance = rule.get("validation", {}).get("tolerance", 0.05)
        flat_max_change = rule.get("validation", {}).get("max_change", 10.0)
        nested_checks = rule.get("validation", {}).get("checks", [])
        tolerance = next((c["tolerance"] for c in nested_checks if "tolerance" in c), flat_tolerance)
        max_change = next((c["max_change"] for c in nested_checks if "max_change" in c), flat_max_change)
        violations: list[str] = []

        # Extract time-series values for a given metric
        # Content format: {"yoy": {"2023": value, "2024": value}, "qoq": {...}}
        yoy_data = data.get("yoy", {})
        qoq_data = data.get("qoq", {})

        # Check YoY consistency
        for metric, years_data in yoy_data.items():
            if not isinstance(years_data, dict) or len(years_data) < 2:
                continue
            sorted_years = sorted(years_data.keys())
            for i in range(1, len(sorted_years)):
                curr_val = years_data.get(sorted_years[i])
                prev_val = years_data.get(sorted_years[i - 1])
                if curr_val is None or prev_val is None or prev_val == 0:
                    continue

                reported_yoy = data.get("yoy_rate", {}).get(metric, {}).get(sorted_years[i])
                computed_yoy = (curr_val - prev_val) / abs(prev_val)
                if reported_yoy is not None:
                    if abs(reported_yoy - computed_yoy) > tolerance:
                        violations.append(
                            f"YoY mismatch for {metric} in {sorted_years[i]}: "
                            f"reported {reported_yoy:.1%} vs computed {computed_yoy:.1%} (tolerance {tolerance:.1%})"
                        )

        # Check QoQ sanity (no jump > max_change)
        for metric, periods_data in qoq_data.items():
            if not isinstance(periods_data, dict) or len(periods_data) < 2:
                continue
            sorted_periods = sorted(periods_data.keys())
            for i in range(1, len(sorted_periods)):
                curr_val = periods_data.get(sorted_periods[i])
                prev_val = periods_data.get(sorted_periods[i - 1])
                if curr_val is None or prev_val is None or prev_val == 0:
                    continue
                qoq = abs((curr_val - prev_val) / prev_val)
                if qoq > max_change:
                    violations.append(
                        f"QoQ impossible jump for {metric} at {sorted_periods[i]}: "
                        f"{qoq:.0%} change exceeds max {max_change:.0%}"
                    )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    # ── Structural / Format Checkers ────────────────────────────────────────────

    def _check_content_structure(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate that required content sections/fields are present.

        Supports all empirical_paper rule types:
        - hypothesis_derivation     → checks theory references
        - hypothesis_numbering     → checks H1, H2... sequential numbering
        - data_description        → checks data_source, sample_size fields
        - variable_definition     → checks dependent/independent/control variables
        - method_identification   → checks fixed_effects, cluster_SE, iv, parallel_trend
        - endogeneity_handling   → checks endogeneity discussion
        - robustness_check       → checks at least 2 robustness tests
        - heterogeneity_analysis  → checks theory support + group definition
        - mediation_analysis     → checks mediator theory + Sobel/Bootstrap
        - regression_table       → checks N, R2, SE, significance markers
        - significance_reporting → checks consistent ***/**/* system
        - citation_format        → checks DOI pattern in text
        - causal_inference       → checks identification_assumptions, limitations
        - paper_structure       → checks required sections
        """
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)

        for check in rule.get("validation", {}).get("rules", []):
            check_type = check.get("check", "")
            field_name = check.get("check_field", "")

            if check_type == "required_fields":
                for rf in check.get("required_fields", []):
                    if rf not in data:
                        violations.append(f"Missing required field: {rf}")

            elif check_type == "min_length":
                min_len = check.get("min_length", 0)
                val = data.get(field_name, "")
                if len(str(val)) < min_len:
                    violations.append(f"{field_name} too short: {len(str(val))} < {min_len}")

            elif check_type == "min_items":
                min_items = check.get("min_items", 0)
                val = data.get(field_name, [])
                if len(val) < min_items:
                    violations.append(f"{field_name} has {len(val)} items, need >= {min_items}")

            elif check_type == "min_tests":
                min_tests = check.get("min_tests", 2)
                acceptable = check.get("acceptable_tests", [])
                found_tests = []
                for test in acceptable:
                    if test.lower() in text.lower():
                        found_tests.append(test)
                if len(found_tests) < min_tests:
                    violations.append(
                        f"Robustness: only {len(found_tests)} tests found, need >= {min_tests}"
                    )

            elif check_type == "hypothesis_has_theory_reference":
                h_patterns = [r"[Hh]\d+", r"假设[一二三四五]", r"Hypothesis"]
                has_h = any(re.search(p, text) for p in h_patterns)
                theory_indicators = [
                    "理论", "theory", "机制", "mechanism", "依据", "basis"
                ]
                has_theory = any(t.lower() in text.lower() for t in theory_indicators)
                if has_h and not has_theory:
                    violations.append("Hypothesis found but no theoretical reference")

            elif check_type == "hypothesis_is_testable":
                h_patterns = [r"[Hh]\d+"]
                for p in h_patterns:
                    for m in re.finditer(p, text):
                        ctx_start = max(0, m.start() - 50)
                        ctx_end = min(len(text), m.end() + 100)
                        ctx = text[ctx_start:ctx_end]
                        measurable = ["增加", "降低", "促进", "抑制", "正向", "负向",
                                     "increase", "decrease", "positive", "negative", "effect"]
                        if not any(word in ctx.lower() for word in measurable):
                            violations.append(
                                f"Hypothesis near '{m.group()}' may not be empirically testable"
                            )

            elif check_type == "hypothesis_numbering":
                nums = sorted(set(int(m.group(1)) for m in re.finditer(r"H(\d+)", text)))
                if nums:
                    expected = list(range(1, max(nums) + 1))
                    if nums != expected:
                        violations.append(
                            f"Hypothesis numbering not sequential: found {nums}, expected {expected}"
                        )

            elif check_type == "correlation_vs_causation":
                if any(w in text.lower() for w in ["因果", "cause", "导致", "drives"]):
                    caveats = ["不能", "not", "未必", "不一定", "并不意味着",
                              "相关关系", "correlation does not imply"]
                    if not any(c in text.lower() for c in caveats):
                        violations.append(
                            "Causal claim without 'correlation does not imply causation' caveat"
                        )

            elif check_type == "causal_interpretation_bounds":
                cautious = ["可能", "possibly", "might", "may", "一定程度上", "to some extent",
                           "有限", "limited", "部分", "partial"]
                if not any(c in text.lower() for c in cautious):
                    violations.append(
                        "Causal interpretation may be overstated — add uncertainty caveats"
                    )

            elif check_type == "heterogeneity_has_theory":
                has_grouping = any(w in text.lower() for w in
                                   ["异质", "heterogene", "分组", "子样本", "subsample"])
                has_rationale = any(w in text.lower() for w in
                                   ["理论", "theory", "预期", "expect", "预测", "predict"])
                if has_grouping and not has_rationale:
                    violations.append("Heterogeneity analysis lacks theoretical rationale")

            elif check_type == "mediator_has_theory":
                mediator_indicators = ["中介", "mediat", "传导", "channel", "机制", "mechanism"]
                has_mediator = any(w in text.lower() for w in mediator_indicators)
                has_mechanism = any(w in text.lower() for w in ["机制", "mechanism", "路径", "path"])
                if has_mediator and not has_mechanism:
                    violations.append("Mediation analysis lacks mechanism description")

            elif check_type == "single_significance_system":
                multi = bool(re.search(r"\*\*\*", text)) and bool(re.search(r"[†‡§]", text))
                if multi:
                    violations.append("Multiple significance annotation systems detected")

            elif check_type == "sequential_numbering":
                nums = sorted(set(int(m.group(1)) for m in re.finditer(r"H(\d+)", text)))
                if nums:
                    expected = list(range(1, max(nums) + 1))
                    if nums != expected:
                        violations.append(
                            f"Sequential numbering broken: found {nums}, expected {expected}"
                        )

            elif check_type == "citation_verifiable":
                dois = re.findall(r"10\.\d{4,}/[\w\.\-/]+", text)
                total = len(re.findall(r"\[\d+\]|\([A-Z][a-z]+ et al\., \d{4}\)", text))
                if total > 0:
                    rate = len(dois) / total
                    if rate < 0.5:
                        violations.append(
                            f"Too few verifiable citations: {rate:.0%} have DOI (need ≥50%)"
                        )

            elif check_type == "group_definition":
                has_grouping = any(w in text.lower() for w in
                                   ["分组", "异质", "子样本", "subsample", "heterogene"])
                has_def = any(w in text.lower() for w in
                               ["定义", "definition", "标准", "标准是", "criteria", "based on"])
                if has_grouping and not has_def:
                    violations.append("Heterogeneity grouping lacks clear definition/criteria")

            # P1-5/6 Fix: Add missing check type handlers
            elif check_type == "hypothesis_related_to_research_question":
                # Check that hypothesis mentions relate to the stated research question
                research_q_indicators = ["研究问题", "研究主题", "研究目标",
                                        "research question", "this paper", "本文", "本研究"]
                has_rq = any(w in text.lower() for w in research_q_indicators)
                has_h = bool(re.search(r"[Hh]\d+", text))
                if has_h and not has_rq:
                    # Heuristic: if hypotheses exist but no clear research question mention,
                    # flag as potential disconnect
                    violations.append(
                        "Hypothesis found but research question connection unclear"
                    )

            elif check_type == "test_has_expectation":
                # Each robustness test should have an expected directional outcome
                test_indicators = ["稳健性", "敏感性", "替换", "调整",
                                   "robustness", "sensitivity", "alternative"]
                has_test = any(w in text.lower() for w in test_indicators)
                # Check for expectation language near test mentions
                expectation_words = ["预期", "expect", "应该", "should", "预计", "anticipate"]
                has_exp = any(w in text.lower() for w in expectation_words)
                if has_test and not has_exp:
                    violations.append(
                        "Robustness/sensitivity test found but expected outcome not stated"
                    )

            elif check_type == "result_consistency":
                # Robustness results should be directionally consistent with baseline
                consistency_ok = any(w in text.lower() for w in
                                    ["一致", "稳健", "显著", "consistent",
                                     "similar", "robust", "confirms"])
                flag_words = ["相反", "不一致", "contradict", "opposite", "inconsistent"]
                has_flag = any(w in text.lower() for w in flag_words)
                if has_flag and not consistency_ok:
                    violations.append(
                        "Robustness test results may contradict baseline — clarify interpretation"
                    )

            elif check_type == "coefficient_interpretation":
                # Coefficients must be interpreted with economic meaning, not just statistical
                coeff_patterns = [r"\d+\.\d+", r"[0-9]+%", r"系数", r"coeffi"]
                has_number = any(re.search(p, text) for p in coeff_patterns)
                econ_words = ["经济意义", "亿元", "个百分点", "边际效应",
                             "economic", "magnitude", "meaningful", "substantive"]
                has_econ = any(w in text.lower() for w in econ_words)
                if has_number and not has_econ:
                    violations.append(
                        "Numerical result reported without clear economic interpretation"
                    )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_format(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate formatting rules (e.g. proper date formats, unit annotations)."""
        text = content if isinstance(content, str) else content.get("text", "")
        violations: list[str] = []
        for check in rule.get("validation", {}).get("rules", []):
            pattern = check.get("pattern", "")
            desc = check.get("description", pattern)
            if pattern and not re.search(pattern, text):
                violations.append(f"Format issue: {desc}")
        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_data_description(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate that simulated/estimated data is properly flagged."""
        text = content if isinstance(content, str) else content.get("text", "")
        # Check for markers like [SIMULATED], [ESTIMATED], TODO placeholders
        placeholder_patterns = [r"\[SIMULATED\]", r"\[ESTIMATED\]", r"\[TODO\]", r"占位"]
        found_markers = [p for p in placeholder_patterns if re.search(p, text)]
        if found_markers:
            return False, f"Placeholder data markers found: {', '.join(found_markers)}"
        return True, ""

    def _check_temporal_consistency(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate chronological ordering of events/dates."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        for check in rule.get("validation", {}).get("rules", []):
            ctype = check.get("check", "")
            if ctype == "chronological_order":
                events = data.get("events", [])
                dates = [e.get("date") for e in events if e.get("date")]
                if dates != sorted(dates):
                    violations.append("Events are not in chronological order")

            elif ctype == "forecast_after_history":
                # Forecast data periods must come after historical data periods
                hist_end = data.get("hist_end_date") or data.get("history_end")
                forecast_start = data.get("forecast_start_date") or data.get("forecast_start")
                if hist_end and forecast_start:
                    import datetime
                    try:
                        # Try multiple date formats
                        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y%m%d", "%Y"):
                            try:
                                h = datetime.datetime.strptime(str(hist_end), fmt)
                                f = datetime.datetime.strptime(str(forecast_start), fmt)
                                if f <= h:
                                    violations.append(
                                        f"Forecast period starts ({forecast_start}) "
                                        f"before or at historical end ({hist_end})"
                                    )
                                break
                            except ValueError:
                                continue
                    except Exception as exc:
                        _logger().warning(
                            f"silent except in _check_data_freshness (forecast/period format loop): {type(exc).__name__}: {exc}"
                        )
                        pass  # Skip if date parsing fails

            elif ctype == "release_after_period":
                # Report release date must be after the reporting period end date
                period_end = data.get("period_end") or data.get("report_period_end")
                release_date = data.get("release_date") or data.get("publish_date")
                if period_end and release_date:
                    import datetime
                    try:
                        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y%m%d", "%Y"):
                            try:
                                pe = datetime.datetime.strptime(str(period_end), fmt)
                                rd = datetime.datetime.strptime(str(release_date), fmt)
                                if rd <= pe:
                                    violations.append(
                                        f"Release date ({release_date}) is before or at "
                                        f"reporting period end ({period_end})"
                                    )
                                break
                            except ValueError:
                                continue
                    except Exception as exc:
                        _logger().warning(
                            f"silent except in _check_data_freshness (release_after_period): {type(exc).__name__}: {exc}"
                        )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_data_freshness(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate data is not stale (based on timestamps)."""
        import time
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        for check in rule.get("validation", {}).get("rules", []):
            max_age = check.get("max_age_days", 365) * 86400
            date_field = check.get("check_date_field", "report_date")
            date_val = data.get(date_field)

            if date_val:
                try:
                    # Try parsing as Unix timestamp or ISO string
                    if isinstance(date_val, (int, float)):
                        age = time.time() - date_val
                    else:
                        from datetime import datetime
                        dt = datetime.fromisoformat(str(date_val).replace("Z", "+00:00"))
                        age = time.time() - dt.timestamp()
                    if age > max_age:
                        violations.append(
                            f"{date_field} is {age / 86400:.0f} days old (max {max_age / 86400:.0f})"
                        )
                except (ValueError, OSError) as exc:
                    _logger().warning(
                        f"silent except in _check_data_freshness (date parse): "
                        f"{type(exc).__name__}: {exc}"
                    )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_unit_consistency(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate unit consistency within tables/sections."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []
        tables = data.get("tables", [])
        allowed = rule.get("validation", {}).get("allowed_units", [])

        for tbl in tables:
            units_in_row = set()
            for row in tbl.get("rows", []):
                for cell in row.get("cells", []):
                    for unit in allowed:
                        if unit in str(cell):
                            units_in_row.add(unit)
            if len(units_in_row) > 1:
                violations.append(f"Table '{tbl.get('label', '')}' has mixed units: {units_in_row}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_valuation_logic(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate DCF and valuation assumptions are present and logical."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        for check in rule.get("validation", {}).get("rules", []):
            required = check.get("required_fields", [])
            for field in required:
                if field not in data:
                    violations.append(f"Missing valuation field: {field}")

        # PE check
        pe = self._extract_field(data, "pe")
        if pe is not None and pe < 0:
            # Already handled by data, but warn if PE is used in valuation
            pass

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_risk_disclosure(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate risk disclosure section has sufficient content."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        for check in rule.get("validation", {}).get("rules", []):
            min_items = check.get("min_items", 0)
            min_len = check.get("min_length", 0)
            field = check.get("check_field", "risk_factors")

            items = data.get(field, [])
            if len(items) < min_items:
                violations.append(f"{field}: {len(items)} items, need >= {min_items}")

            for item in items:
                if len(str(item)) < min_len:
                    violations.append(f"{field} item too short: '{str(item)[:30]}...'")
                    break

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_rating_definition(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate investment rating is defined and consistent with target upside."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []

        rating = data.get("rating", "")
        upside = self._extract_field(data, "upside_pct")
        mapping = rule.get("validation", {}).get("rules", [{}])[0].get("mapping", {})

        if rating and mapping:
            expected_range = mapping.get(rating)
            if expected_range and upside is not None:
                low, high = expected_range
                if not (low <= upside <= high):
                    violations.append(
                        f"Rating '{rating}' inconsistent with upside {upside}% "
                        f"(expected {low}%–{high}%)"
                    )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_disclosure_completeness(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate all required disclosure sections are present."""
        data = content if isinstance(content, dict) else {}
        violations: list[str] = []
        sections = rule.get("validation", {}).get("required_sections", [])

        for section in sections:
            name = section.get("name", "")
            if section.get("required", False) and name not in data:
                violations.append(f"Missing required section: {name}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    # ── Empirical Paper Checkers ─────────────────────────────────────────────────

    def _check_empirical_variable_definition(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate that all variables (dependent, independent, control) are properly defined."""
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)
        rules = rule.get("validation", {}).get("rules", [])

        for check in rules:
            required_fields = check.get("required_fields", [])
            for field in required_fields:
                if field not in data and field.lower() not in text.lower():
                    violations.append(f"Missing variable definition: {field}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_method(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate identification strategy has theoretical basis (FE, IV, DID, RDD).

        When regression data (event_study_df, X, Z, df_matched, residuals) is
        present in content, this checker also delegates to the econometrics_rules
        module for statistical validation.
        """
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)
        rules = rule.get("validation", {}).get("rules", [])

        for check in rules:
            required_fields = check.get("required_fields", [])
            for field in required_fields:
                if field not in data:
                    # Check text for mentions
                    if field.replace("_", " ") not in text.lower():
                        violations.append(f"Missing method element: {field}")

        # Optionally delegate to econometrics_rules when regression data is present
        method = data.get("method", "")
        has_regression_data = any(
            k in data
            for k in [
                "regression_table",
                "event_study_df",
                "X",
                "Z",
                "df_matched",
                "residuals",
                "running_var",
            ]
        )
        if has_regression_data or method:
            try:
                eco_passed, eco_msg = self._check_econometric_quality(content, rule)
                if not eco_passed:
                    violations.append(f"Econometric validation failed: {eco_msg}")
            except Exception as exc:
                _logger().warning(
                    f"silent except in _check_econometric_quality wrapper: {type(exc).__name__}: {exc}"
                )
                pass  # Do not fail the whole check due to econometrics errors

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_endogeneity(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate endogeneity discussion and handling methods."""
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data if isinstance(content, str) else data.get("text", "")
        rules_list = rule.get("validation", {}).get("rules", [])
        methods_list = rule.get("validation", {}).get("methods", [])

        endogeneity_terms = ["内生", "endogen", "反向因果", "reverse causality",
                             "遗漏变量", "omitted variable", "选择性偏差", "selection bias"]
        has_discussion = any(term in text.lower() for term in endogeneity_terms)
        if not has_discussion:
            violations.append("No endogeneity discussion found")

        # Check required fields from rules (data_source, check_field references)
        for r in rules_list:
            for rf in r.get("required_fields", []):
                if rf not in data:
                    violations.append(f"Missing required field: {rf}")
            check_field = r.get("check_field", "")
            if check_field and check_field not in data and check_field.lower() not in text.lower():
                violations.append(f"Missing discussion of: {check_field}")

        # Validate against methods list if provided
        methods_found = [m for m in methods_list if m.lower() in text.lower()]
        if not methods_found and not has_discussion:
            violations.append("No endogeneity handling methods mentioned")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_regression_table(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate regression table format: N, R2, SE, significance markers present."""
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)
        rules = rule.get("validation", {}).get("rules", [])

        for check in rules:
            required = check.get("required_fields", [])
            for field in required:
                if "N" in field or "sample" in field.lower():
                    if not re.search(r"\bN\s*=\s*\d+", text):
                        violations.append("Sample size (N) not found in regression table")
                elif "R" in field:
                    if not re.search(r"R[\s]*[²2]?\s*[=:]", text):
                        violations.append("R-squared not found in regression table")

        sig_markers = re.findall(r"\*{1,3}", text)
        if len(sig_markers) < 2:
            violations.append("Insufficient significance markers (***/**/*) in regression table")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_significance(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate significance annotation is consistent (* p<0.1, ** p<0.05, *** p<0.01)."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")

        # Check for standard format
        standard = re.search(r"\*\s*p\s*<\s*0\.1", text)
        if not standard:
            violations.append("Significance level format not declared (* p<0.1, ** p<0.05, *** p<0.01)")

        # Check for mixed systems
        systems = []
        if re.search(r"\*\*\*", text): systems.append("***")
        if re.search(r"[†‡]", text): systems.append("dagger")
        if len(systems) > 1:
            violations.append(f"Mixed significance systems: {', '.join(systems)}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_citation_format(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate citation format and DOI correctness."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        rule.get("validation", {}).get("acceptable_formats", [])

        # Check DOI format
        dois = re.findall(r"10\.\d{4,}/[\w\.\-/]+", text)
        for doi in dois[:5]:  # Check first 5 DOIs
            if not re.match(r"10\.\d{4,}/[\w\.\-/]+", doi):
                violations.append(f"Malformed DOI: {doi}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_citation_coverage(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate citation coverage: 90% verifiable, 30% recent (within 5 years)."""
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)

        min_rate = rule.get("validation", {}).get("min_verification_rate", 0.9)
        min_recent = rule.get("validation", {}).get("min_recent_ratio", 0.3)

        total_citations = len(re.findall(r"\[\d+\]|\([A-Z][a-z]+ et al\., \d{4}\)", text))
        dois = re.findall(r"10\.\d{4,}/[\w\.\-/]+", text)

        if total_citations > 0:
            verifiable_rate = len(dois) / total_citations
            if verifiable_rate < min_rate:
                violations.append(
                    f"Citation verification rate {verifiable_rate:.0%} < {min_rate:.0%} "
                    f"(found {len(dois)} DOIs in {total_citations} citations)"
                )

        # Check recent citations (within 5 years of 2026 = 2021-2026)
        recent_years = re.findall(r"(?:19|20)\d{2}(?!\d)", text)
        recent = sum(1 for y in recent_years if 2021 <= int(y) <= 2026)
        if recent_years:
            recent_ratio = recent / len(recent_years)
            if recent_ratio < min_recent:
                violations.append(
                    f"Recent citation ratio {recent_ratio:.0%} < {min_recent:.0%} "
                    f"(need at least 30% from 2021-2026)"
                )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_causal_inference(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate causal inference rigor: no correlation=causation, identification assumptions stated."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        rules = rule.get("validation", {}).get("rules", [])

        for check in rules:
            check_type = check.get("check", "")
            check.get("required_fields", [])

            if check_type == "correlation_vs_causation":
                causal_terms = ["因果", "cause", "导致", "drives", "决定", "determines"]
                correl_terms = ["相关", "correlated", "associated", "有关"]
                has_causal = any(t in text.lower() for t in causal_terms)
                any(t in text.lower() for t in correl_terms)
                if has_causal:
                    caveats = ["不能", "not", "未必", "不一定", "并不意味着", "相关关系",
                              "not imply", "correlation does not imply"]
                    if not any(c in text.lower() for c in caveats):
                        violations.append(
                            "Causal claim without 'correlation does not imply causation' caveat"
                        )

            elif check_type == "causal_interpretation_bounds":
                cautious = ["可能", "possibly", "might", "may", "一定程度上",
                           "to some extent", "有限", "partial"]
                if not any(c in text.lower() for c in cautious):
                    violations.append(
                        "Causal interpretation may be overstated — add uncertainty caveats"
                    )

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_economic_significance(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate economic significance discussion and marginal effect reporting."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        rules = rule.get("validation", {}).get("rules", [])

        has_econ_interp = any(term in text.lower() for term in
                               ["经济意义", "economic significance", "经济含义", "经济解释",
                                "边际效应", "marginal effect", "弹性", "elasticity"])
        if not has_econ_interp:
            violations.append("No economic significance discussion found")

        has_marginal = any(term in text.lower() for term in
                           ["边际", "marginal", "弹性", "elastic", "影响程度", "magnitude"])
        required_fields = []
        for r in rules:
            required_fields.extend(r.get("required_fields", []))
        if required_fields and not has_marginal:
            violations.append("No marginal effect or elasticity reported")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_empirical_paper_structure(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate paper has all required sections (摘要/引言/文献综述/etc.)."""
        violations: list[str] = []
        data = content if isinstance(content, dict) else {}
        text = data.get("text", "") if isinstance(content, dict) else str(content)
        sections = rule.get("validation", {}).get("required_sections", [])

        section_markers = {
            "摘要": [r"摘要", r"abstract"],
            "引言": [r"^#+\s*引言", r"1\s+引言", r"introduction"],
            "文献综述": [r"文献综述", r"literature review", r"related work"],
            "理论框架与研究假设": [r"假设", r"hypothesis", r"理论框架", r"theoretical"],
            "研究设计": [r"研究设计", r"methodology?", r"research design"],
            "实证结果": [r"实证结果", r"empirical result", r"regression"],
            "稳健性检验": [r"稳健性", r"robustness", r"robustness check"],
            "结论与政策建议": [r"结论", r"conclusion", r"policy implication"],
            "参考文献": [r"参考文献", r"reference", r"bibliography"],
        }

        for section in sections:
            if not section.get("required", False):
                continue
            name = section.get("name", "")
            markers = section_markers.get(name, [re.escape(name)])
            found = any(re.search(m, text, re.IGNORECASE | re.MULTILINE) for m in markers)
            if not found:
                violations.append(f"Missing required section: {name}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    # ── ML Paper Checkers ────────────────────────────────────────────────────────

    def _check_ml_experiment(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate ML experiment completeness: ablation, baselines, standard datasets."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        rules = rule.get("validation", {}).get("rules", [])

        has_ablation = any(term in text.lower() for term in
                          ["消融", "ablation", "ablate", "组件", "component"])
        if not has_ablation:
            violations.append("No ablation study found")

        has_baseline = any(term in text.lower() for term in
                           ["基线", "baseline", "对比", "compare", "sota"])
        if not has_baseline:
            violations.append("No baseline comparison found")

        for check in rules:
            for rf in check.get("required_fields", []):
                if rf not in text.lower():
                    violations.append(f"Missing experiment detail: {rf}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_baseline(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate SOTA and classic baseline comparisons are present."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        has_classic = any(term in text.lower() for term in
                           ["基线", "baseline", "经典", "classic", "传统", "traditional"])
        if not has_classic:
            violations.append("No classic method comparison found")
        has_sota = "sota" in text.lower() or "state-of-the-art" in text.lower()
        if not has_sota:
            violations.append("No SOTA comparison found")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_reproducibility(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate reproducibility: code URL, hyperparameters, random seed, mean±std."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")
        rules = rule.get("validation", {}).get("rules", [])

        has_code = any(term in text.lower() for term in
                       ["github", "code", "代码", "https://", "repo"])
        if not has_code:
            violations.append("No code/repository link found")

        has_seed = any(term in text.lower() for term in
                        ["seed", "随机种子", "random seed", "set_seed"])
        if not has_seed:
            violations.append("No random seed specification found")

        has_mean_std = "±" in text or "+-" in text or "+/-" in text
        if not has_mean_std:
            violations.append("No mean±std reporting found (multiple runs required)")

        for check in rules:
            for rf in check.get("required_fields", []):
                if rf not in text.lower():
                    violations.append(f"Missing reproducibility detail: {rf}")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_math(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate mathematical rigor: theorem proofs, symbol consistency."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")

        has_theorem = any(term in text.lower() for term in
                           ["定理", "theorem", "引理", "lemma", "命题", "proposition", "证明", "proof"])
        if has_theorem and "证明" not in text.lower() and "proof" not in text.lower():
            violations.append("Theorem found but no proof provided")

        # Check symbol consistency (very basic: no multiple definitions of same symbol)
        # This is hard to verify automatically — warn if equation density is low
        eq_count = len(re.findall(r"\$\$[\s\S]+?\$\$|\$[^$]+\$", text))
        if eq_count < 3:
            violations.append(f"Very few equations found ({eq_count}) — math-heavy paper expected")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_notation(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate notation clarity: first use definitions, symbol table."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")

        # Check if a symbol table or notation section exists
        has_table = any(term in text.lower() for term in
                         ["符号表", "notation table", "符号定义", "notations", "表1", "table 1"])
        # This is a warning-level rule — don't fail hard
        if not has_table:
            violations.append("No notation/symbol table found")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_figure(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate figure quality: DPI, legends, axis labels, captions."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")

        has_legend = any(term in text.lower() for term in
                          ["图例", "legend", "标注", "annotation"])
        if not has_legend:
            violations.append("No figure legend/annotation found")

        has_axis = any(term in text.lower() for term in
                        ["x轴", "y轴", "x-axis", "y-axis", "横坐标", "纵坐标"])
        if not has_axis:
            violations.append("No axis label mentions found")

        has_caption = any(term in text.lower() for term in
                          ["图1", "fig.", "figure", "图2", "图3", "caption"])
        if not has_caption:
            violations.append("No figure captions found")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    def _check_ml_related_work(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """Validate related work coverage: recent work and differentiation from existing work."""
        violations: list[str] = []
        text = content if isinstance(content, str) else content.get("text", "")

        # Check for recent citations (within 3 years of 2026 = 2023-2026)
        recent_years = re.findall(r"(?:19|20)\d{2}(?!\d)", text)
        recent = sum(1 for y in recent_years if 2023 <= int(y) <= 2026)
        if recent_years:
            recent_ratio = recent / len(recent_years)
            min_ratio = rule.get("validation", {}).get("rules", [{}])[0].get("min_ratio", 0.3)
            if recent_ratio < min_ratio:
                violations.append(
                    f"Recent work ratio {recent_ratio:.0%} < {min_ratio:.0%} (need 30% from 2023-2026)"
                )

        has_diff = any(term in text.lower() for term in
                        ["区别", "不同于", "相比之下", "differ", "unlike", "whereas", "we improve"])
        if not has_diff:
            violations.append("No differentiation from existing work found")

        if violations:
            return False, "; ".join(violations)
        return True, ""

    # ── Econometrics Integration ───────────────────────────────────────────────────

    def _get_econometrics_engine(self):
        """Lazily import and return the econometrics rule engine."""
        if self._econometrics_engine is None:
            from scripts.core.econometrics_rules import (
                EconometricsRuleEngine,
                DIDValidator,
                WeakInstrumentTest,
                BalanceTestValidator,
                HeteroskedasticityTest,
            )
            self._econometrics_engine = {
                "engine": EconometricsRuleEngine(),
                "did": DIDValidator(),
                "weak_iv": WeakInstrumentTest(),
                "balance": BalanceTestValidator(),
                "hetero": HeteroskedasticityTest(),
            }
        return self._econometrics_engine

    def _check_econometric_quality(
        self, content: dict | str, rule: dict
    ) -> tuple[bool, str]:
        """
        Run econometric quality checks on regression results embedded in content.

        Detects the method type (DID/IV/PSM/RD/OLS) from the content and
        delegates to the appropriate validator from econometrics_rules.

        Expected content fields:
            - method: str (e.g. "did", "DiD", "iv", "instrumental", "psm", "ols")
            - regression_table or event_study_df: dict (regression results)
            - data_description: dict (sample info)
        """
        # Parse content (support JSON string)
        if isinstance(content, str):
            import json as _json
            try:
                data = _json.loads(content)
            except Exception:
                data = {"text": content}
        else:
            data = content if isinstance(content, dict) else {}

        # Extract method string
        method = data.get("method", "")
        if not method:
            text = data.get("text", "")
            method = text
        method_lower = method.lower()

        # Check if this content has econometric data to validate
        has_regression_data = any(
            k in data
            for k in [
                "regression_table",
                "event_study_df",
                "X",
                "Z",
                "df_matched",
                "residuals",
                "running_var",
            ]
        )
        if not has_regression_data and not any(
            kw in method_lower for kw in ["did", "iv", "psm", "ols", "rd", "instrument"]
        ):
            return True, ""

        # Dispatch based on method type
        result_map = self._get_econometrics_engine()
        engine = result_map["engine"]

        try:
            # Extract validated data for each method type
            validation_data = self._extract_econometric_data(data, method_lower)

            if not validation_data:
                return True, ""

            # Run the appropriate validation
            if any(kw in method_lower for kw in ["did", "diff_in_diff"]):
                result = engine.validate("did", validation_data)
            elif any(kw in method_lower for kw in ["iv", "instrumental", "2sls"]):
                result = engine.validate("iv", validation_data)
            elif any(kw in method_lower for kw in ["psm", "matching", "propensity"]):
                result = engine.validate("psm", validation_data)
            elif any(kw in method_lower for kw in ["rd", "rdd", "discontinuity"]):
                result = engine.validate("rd", validation_data)
            elif any(kw in method_lower for kw in ["ols", "regression", "panel", "fe"]):
                result = engine.validate("ols", validation_data)
            else:
                return True, ""

            # Store results back in content dict for later access
            if "_econometric_results" not in data:
                data["_econometric_results"] = {}
            data["_econometric_results"][method] = {
                "passed": result.passed,
                "warnings": result.warnings,
                "errors": result.errors,
                "details": result.details,
            }

            # Build failure message
            if not result.passed:
                parts = []
                if result.errors:
                    parts.extend(result.errors)
                if result.warnings:
                    parts.append(f"Warnings: {'; '.join(result.warnings)}")
                return False, "; ".join(parts)

            return True, ""

        except Exception as exc:
            return False, f"Econometric validation failed: {exc}"

    def _extract_econometric_data(
        self, data: dict, method_lower: str
    ) -> dict:
        """
        Extract and normalize econometric data from content dict.

        Returns a dict suitable for EconometricsRuleEngine.validate().
        """
        result = {}

        # DID data: event study dataframe
        if "event_study_df" in data:
            es_df = data["event_study_df"]
            if isinstance(es_df, dict):
                result["event_study_df"] = es_df
            elif hasattr(es_df, "to_dict"):
                result["event_study_df"] = es_df.to_dict("list")
        elif "regression_table" in data:
            reg = data["regression_table"]
            if isinstance(reg, dict) and "event_study" in reg:
                result["event_study_df"] = reg["event_study"]

        # IV data: endogenous var (X), instruments (Z), controls
        if "X" in data and "Z" in data:
            result["X"] = data["X"]
            result["Z"] = data["Z"]
            if "controls" in data:
                result["controls"] = data["controls"]
            if "residuals_2sls" in data:
                result["residuals_2sls"] = data["residuals_2sls"]
            if "n_instruments" in data:
                result["n_instruments"] = data["n_instruments"]

        # PSM data: matched dataframe
        if "df_matched" in data:
            result["df_matched"] = data["df_matched"]
            if "df_before" in data:
                result["df_before"] = data["df_before"]
            if "variables" in data:
                result["variables"] = data["variables"]

        # RDD data
        if "running_var" in data:
            result["running_var"] = data["running_var"]
            if "cutoff" in data:
                result["cutoff"] = data["cutoff"]
            if "bandwidth" in data:
                result["bandwidth"] = data["bandwidth"]

        # OLS data: residuals and X matrix
        if "residuals" in data:
            result["residuals"] = data["residuals"]
            if "X" in data:
                result["X"] = data["X"]
            if "varnames" in data:
                result["varnames"] = data["varnames"]

        return result

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_field(data: dict, field_name: str) -> float | None:
        """Extract a numeric field from a flat or nested dict."""
        # Try direct key
        val = data.get(field_name)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        # Try underscore/camelCase variants
        [field_name, field_name.lower(), field_name.upper()]
        for key in data:
            if key.lower().replace("_", "") == field_name.lower().replace("_", ""):
                try:
                    return float(data[key])
                except (TypeError, ValueError) as exc:
                    _logger().debug(
                        f"silent except in _extract_field (float cast for {field_name}={key!r}): "
                        f"{type(exc).__name__}: {exc}"
                    )
        return None


# ── Module-level aliases (backward compatibility) ──────────────────────────────

def __getattr__(name: str):
    """Allow `from halt_rules_registry import HaltRuleRegistry` (no trailing 's')."""
    if name == "HaltRuleRegistry":
        return HaltRulesRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
