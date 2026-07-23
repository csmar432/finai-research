"""AutoReviewRules — 论文自动评分引擎。

基于 HaltRules YAML 配置，对论文各章节执行自动化评分。
无需人工反馈，直接输出量化质量报告。

集成方式：
    from scripts.core.auto_review_rules import AutoReviewRules

    arr = AutoReviewRules(domain="empirical_paper")
    score = arr.score_paper(chapters={
        "Introduction": intro_text,
        "Data": data_text,
        "Methodology": method_text,
    })
    print(f"Score: {score.overall}/100, Level: {score.level}")
    if not score.passed:
        print("Issues:", score.critical_issues)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "AutoReviewScore",
    "AutoReviewRule",
    "AutoReviewRules",
]


# ─── Score Dataclasses ────────────────────────────────────────────────────────


@dataclass
class AutoReviewScore:
    """自动评分结果。"""
    domain: str
    overall: float           # 0-100 总分
    level: str             # A/B/C/D/F
    passed: bool
    dimension_scores: dict[str, float]   # 各维度得分
    dimension_issues: dict[str, list[str]] # 各维度问题
    critical_issues: list[str]          # 严重问题（halt_on_fail=True 且失败）
    warnings: list[str]
    suggestions: list[str]
    rule_results: list[dict]  # 每条规则的详细结果
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "overall": round(self.overall, 1),
            "level": self.level,
            "passed": self.passed,
            "dimension_scores": {k: round(v, 1) for k, v in self.dimension_scores.items()},
            "critical_issues": self.critical_issues,
            "suggestions": self.suggestions[:5],
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


# ─── Rule Parser ─────────────────────────────────────────────────────────────


class AutoReviewRule:
    """单条自动评分规则。"""

    def __init__(self, rule_id: str, config: dict[str, Any]):
        self.id = rule_id
        self.description = config.get("description", "")
        self.category = config.get("category", "general")
        self.severity = config.get("severity", "warning")
        self.halt_on_fail = config.get("halt_on_fail", False)
        self.validation = config.get("validation", {})
        self.validation_type = self.validation.get("type", "unknown")
        self.rules = self.validation.get("rules", [])

    def score(self, content: str, context: dict | None = None) -> dict:
        """
        对内容执行规则评分。返回 dict：
            passed: bool
            score: float (0-1)
            issues: list[str]
            suggestion: str | None
        """
        context = context or {}
        len(self.rules) if self.rules else 1

        if self.validation_type == "content_structure_check":
            result = self._check_content_structure(content)
        elif self.validation_type == "format_check":
            result = self._check_format(content)
        elif self.validation_type == "data_description_check":
            result = self._check_data_description(content)
        elif self.validation_type == "variable_check":
            result = self._check_variables(content)
        elif self.validation_type == "method_check":
            result = self._check_method(content)
        elif self.validation_type == "econometric_quality_check":
            result = self._check_econometric(content)
        elif self.validation_type == "robustness_check":
            result = self._check_robustness(content)
        elif self.validation_type == "table_format_check":
            result = self._check_table_format(content)
        elif self.validation_type == "significance_check":
            result = self._check_significance(content)
        elif self.validation_type == "citation_format_check":
            result = self._check_citation_format(content)
        elif self.validation_type == "causal_inference_check":
            result = self._check_causal_inference(content)
        elif self.validation_type == "structure_check":
            result = self._check_structure(content)
        else:
            # Fallback: basic checks
            result = self._check_generic(content)

        return result

    # ─── Individual check methods ────────────────────────────────────────────

    def _check_content_structure(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        total = len(self.rules) if self.rules else 0

        for rule in self.rules or []:
            desc = rule.get("description", "")
            check_fn = rule.get("check", "")

            if check_fn == "hypothesis_has_theory_reference":
                if self._has_theory_reference(content):
                    checks_passed += 1
                else:
                    issues.append(f"缺少理论引用：{desc}")
            elif check_fn == "hypothesis_is_testable":
                if self._is_testable(content):
                    checks_passed += 1
                else:
                    issues.append(f"假设不可检验：{desc}")
            elif check_fn == "hypothesis_related_to_research_question":
                if self._is_related(content):
                    checks_passed += 1
                else:
                    issues.append(f"假设与研究问题不相关：{desc}")

        score = checks_passed / max(total, 1)
        return {
            "passed": checks_passed == total or (total == 0 and checks_passed == 0),
            "score": score,
            "issues": issues,
            "suggestion": issues[0] if issues else None,
        }

    def _check_format(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        for rule in self.rules or []:
            pattern = rule.get("pattern", "")
            if pattern:
                matches = re.findall(pattern, content)
                if matches:
                    checks_passed += 1
                else:
                    issues.append(f"格式不符：{rule.get('description', '')}")
        total = len(self.rules) or 1
        return {
            "passed": checks_passed == total,
            "score": checks_passed / total,
            "issues": issues,
            "suggestion": issues[0] if issues else None,
        }

    def _check_data_description(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        required_keywords = ["数据来源", "样本", "时间", "数据库", "data source", "sample", "period"]
        found = sum(1 for kw in required_keywords if kw.lower() in content.lower())
        if found >= 3:
            checks_passed = 1
        else:
            issues.append(f"数据描述不完整（找到 {found}/{len(required_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(required_keywords),
            "issues": issues,
            "suggestion": "补充数据来源、样本筛选标准、时间范围等描述",
        }

    def _check_variables(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        required_keywords = ["被解释变量", "解释变量", "控制变量", "dependent", "independent", "control"]
        found = sum(1 for kw in required_keywords if kw.lower() in content.lower())
        if found >= 3:
            checks_passed = 1
        else:
            issues.append(f"变量定义不完整（找到 {found}/{len(required_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(required_keywords),
            "issues": issues,
            "suggestion": "补充被解释变量、核心解释变量、控制变量的完整定义",
        }

    def _check_method(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        method_keywords = ["固定效应", "标准误", "聚类", "parallel trend", "fixed effects", "standard errors", "cluster"]
        found = sum(1 for kw in method_keywords if kw.lower() in content.lower())
        if found >= 3:
            checks_passed = 1
        else:
            issues.append(f"方法描述不完整（找到 {found}/{len(method_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(method_keywords),
            "issues": issues,
            "suggestion": "补充识别策略、固定效应设置、聚类标准误等方法描述",
        }

    def _check_econometric(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        econ_keywords = ["parallel trend", "平行趋势", "placebo", "稳健性", "robustness", "endogeneity", "内生性"]
        found = sum(1 for kw in econ_keywords if kw.lower() in content.lower())
        if found >= 2:
            checks_passed = 1
        else:
            issues.append(f"计量检验不完整（找到 {found}/{len(econ_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(econ_keywords),
            "issues": issues,
            "suggestion": "补充平行趋势检验、内生性处理等计量经济学检验",
        }

    def _check_robustness(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        robust_keywords = ["替换", "替换被解释变量", "替换核心解释变量", "调整样本", "bootstrap", "聚类"]
        found = sum(1 for kw in robust_keywords if kw.lower() in content.lower())
        min_tests = self.validation.get("min_tests", 2)
        if found >= min_tests:
            checks_passed = 1
        else:
            issues.append(f"稳健性检验不足（找到 {found} 种，需要 ≥{min_tests} 种）")
        return {
            "passed": checks_passed == 1,
            "score": min(found / min_tests, 1.0),
            "issues": issues,
            "suggestion": f"增加稳健性检验，当前 {found} 种，需要 ≥{min_tests} 种",
        }

    def _check_table_format(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        table_keywords = ["样本量", "N=", "R方", "R²", "标准误", "显著性", "N", "R-squared", "standard errors"]
        found = sum(1 for kw in table_keywords if kw in content)
        if found >= 4:
            checks_passed = 1
        else:
            issues.append(f"回归表格格式不完整（找到 {found}/{len(table_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(table_keywords),
            "issues": issues,
            "suggestion": "补充样本量(N)、R方、标准误、显著性标注等",
        }

    def _check_significance(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        sig_patterns = [r"\*\*\*.*p<0\.01", r"\*.*p<0\.1", r"†.*p<0\.1"]
        found = sum(1 for p in sig_patterns if re.search(p, content))
        if found >= 2:
            checks_passed = 1
        else:
            issues.append("显著性标注体系不完整")
        return {
            "passed": checks_passed == 1,
            "score": found / len(sig_patterns),
            "issues": issues,
            "suggestion": "使用统一显著性标注：*** p<0.01, ** p<0.05, * p<0.1",
        }

    def _check_citation_format(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        doi_pattern = r"10\.\d{4,}/[\w\.\-/%]+"
        dois = re.findall(doi_pattern, content)
        if dois:
            checks_passed = 1
        else:
            issues.append("缺少 DOI 引用（DOI 可验证性是顶刊标准）")
        return {
            "passed": checks_passed == 1,
            "score": min(len(dois) / 10, 1.0),  # 10个DOI = 满分
            "issues": issues,
            "suggestion": "补充可验证的 DOI 引用",
        }

    def _check_causal_inference(self, content: str) -> dict:
        issues = []
        checks_passed = 0
        causal_keywords = ["因果", "causal", "识别假设", "identification", "局限性", "limitation", "correlation", "相关"]
        found = sum(1 for kw in causal_keywords if kw.lower() in content.lower())
        if found >= 3:
            checks_passed = 1
        else:
            issues.append(f"因果推断讨论不完整（找到 {found}/{len(causal_keywords)} 个关键词）")
        return {
            "passed": checks_passed == 1,
            "score": found / len(causal_keywords),
            "issues": issues,
            "suggestion": "补充因果识别假设、局限性和相关vs因果的讨论",
        }

    def _check_structure(self, content: str) -> dict:
        required = self.validation.get("required_sections", [])
        issues = []
        checks_passed = 0
        for sec in required:
            name = sec.get("name", "")
            if name and (name in content or name.lower() in content.lower()):
                checks_passed += 1
            elif sec.get("required"):
                issues.append(f"缺少必需章节：{name}")
        total = len(required) or 1
        return {
            "passed": checks_passed == total,
            "score": checks_passed / total,
            "issues": issues,
            "suggestion": issues[0] if issues else None,
        }

    def _check_generic(self, content: str) -> dict:
        word_count = len(re.sub(r"\s+", "", content))
        score = min(word_count / 500, 1.0)  # 500字 = 满分
        return {
            "passed": word_count >= 500,
            "score": score,
            "issues": [],
            "suggestion": None,
        }

    # ─── Helper check methods ───────────────────────────────────────────────

    @staticmethod
    def _has_theory_reference(content: str) -> bool:
        theory_keywords = ["theory", "理论", "假设", "hypothesis", "文献", "literature"]
        return any(kw.lower() in content.lower() for kw in theory_keywords)

    @staticmethod
    def _is_testable(content: str) -> bool:
        testable_keywords = ["检验", "test", "验证", "实证", "empirical"]
        return any(kw.lower() in content.lower() for kw in testable_keywords)

    @staticmethod
    def _is_related(content: str) -> bool:
        related_keywords = ["研究问题", "研究主题", "研究对象", "research question"]
        return any(kw.lower() in content.lower() for kw in related_keywords)


# ─── AutoReviewRules ──────────────────────────────────────────────────────────


class AutoReviewRules:
    """
    论文自动评分引擎。

    从 YAML 配置文件加载质量规则，对论文内容执行自动化评分，
    生成维度得分、问题列表和修复建议。

    Parameters
    ----------
    domain : str
        领域类型："empirical_paper" | "finance_report" | "ml_paper"
    rules_dir : str | Path
        halt_rules 配置目录，默认为 config/halt_rules/
    """

    def __init__(
        self,
        domain: str = "empirical_paper",
        rules_dir: str | Path = "config/halt_rules",
    ):
        self.domain = domain
        self.rules_dir = Path(rules_dir)
        self.rules: list[AutoReviewRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        yaml_path = self.rules_dir / f"{self.domain}.yaml"
        if not yaml_path.exists():
            yaml_path = self.rules_dir / "empirical_paper.yaml"

        try:
            with open(yaml_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception:
            config = {"rules": []}

        for rule_cfg in config.get("rules", []):
            rule_id = rule_cfg.get("id", f"rule_{len(self.rules)}")
            self.rules.append(AutoReviewRule(rule_id, rule_cfg))

    def score_paper(
        self,
        chapters: dict[str, str],
        context: dict | None = None,
    ) -> AutoReviewScore:
        """
        对论文所有章节执行评分。

        Parameters
        ----------
        chapters : dict[str, str]
            章节名 → 章节正文内容的映射
        context : dict, optional
            全局上下文（如期刊名称、目标字数等）

        Returns
        -------
        AutoReviewScore
            包含总分、各维度得分、问题列表和修复建议
        """
        t0 = time.perf_counter()
        context = context or {}
        combined = "\n\n".join(f"## {k}\n{v}" for k, v in chapters.items())

        dim_scores: dict[str, float] = {}
        dim_issues: dict[str, list[str]] = {}
        critical: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []
        rule_results: list[dict] = []

        # Group rules by category
        category_rules: dict[str, list[AutoReviewRule]] = {}
        for rule in self.rules:
            category_rules.setdefault(rule.category, []).append(rule)

        for category, cat_rules in category_rules.items():
            cat_scores: list[float] = []
            cat_issues: list[str] = []

            for rule in cat_rules:
                result = rule.score(combined, context)
                cat_scores.append(result["score"])

                if result["issues"]:
                    cat_issues.extend(result["issues"])
                    if rule.severity == "error" and rule.halt_on_fail and not result["passed"]:
                        critical.extend(result["issues"])
                    elif rule.severity == "warning":
                        warnings.extend(result["issues"])

                if result.get("suggestion"):
                    suggestions.append(f"[{category}] {result['suggestion']}")

                rule_results.append({
                    "rule_id": rule.id,
                    "category": category,
                    "severity": rule.severity,
                    "passed": result["passed"],
                    "score": round(result["score"], 3),
                    "issues": result["issues"],
                })

            dim_scores[category] = sum(cat_scores) / max(len(cat_scores), 1) * 100
            if cat_issues:
                dim_issues[category] = cat_issues

        # Calculate overall score
        overall = sum(dim_scores.values()) / max(len(dim_scores), 1)
        passed = len(critical) == 0

        # Determine level
        if overall >= 90:
            level = "A"
        elif overall >= 80:
            level = "B"
        elif overall >= 70:
            level = "C"
        elif overall >= 60:
            level = "D"
        else:
            level = "F"

        return AutoReviewScore(
            domain=self.domain,
            overall=overall,
            level=level,
            passed=passed,
            dimension_scores=dim_scores,
            dimension_issues=dim_issues,
            critical_issues=critical,
            warnings=warnings,
            suggestions=list(dict.fromkeys(suggestions))[:10],  # Deduplicate
            rule_results=rule_results,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def score_chapter(self, chapter_name: str, text: str) -> dict:
        """对单个章节执行评分，返回简化结果。"""
        score = self.score_paper({chapter_name: text})
        return score.to_dict()

    def get_critical_rules(self) -> list[str]:
        """返回所有 halt_on_fail=True 的规则 ID。"""
        return [r.id for r in self.rules if r.halt_on_fail]


# ─── CLI Demo ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=== AutoReviewRules Demo ===\n")

    sample_paper = {
        "Introduction": """
        This paper studies the effect of carbon trading on corporate green innovation.
        We develop three hypotheses based on the Porter hypothesis and innovation theory.
        H1: Carbon trading promotes green innovation.
        We use a difference-in-differences approach.
        Data source: CSMAR database, sample period 2010-2023.
        """,
        "Methodology": """
        We use a two-way fixed effects model with firm and year dummies.
        Standard errors are clustered at the firm level.
        Parallel trend assumption is verified in Figure 2.
        We address endogeneity using instrumental variables.
        """,
        "Results": """
        Table 3 reports the main results.
        N = 5000, R² = 0.45
        Coefficient on carbon trading: 0.23*** (p<0.01)
        Standard errors in parentheses.
        *** p<0.01, ** p<0.05, * p<0.1
        """,
    }

    arr = AutoReviewRules(domain="empirical_paper")
    score = arr.score_paper(sample_paper)

    print(f"Overall: {score.overall:.1f}/100  Level: {score.level}")
    print(f"Passed: {score.passed}")
    print(f"\nDimension scores:")
    for dim, s in sorted(score.dimension_scores.items()):
        print(f"  {dim:20s}: {s:.1f}")
    if score.critical_issues:
        print(f"\nCritical issues ({len(score.critical_issues)}):")
        for iss in score.critical_issues[:5]:
            print(f"  ❌ {iss}")
    if score.suggestions:
        print(f"\nSuggestions:")
        for suggestion in score.suggestions[:5]:
            print(f"  💡 {suggestion}")
    print(f"\nElapsed: {score.elapsed_ms:.1f}ms")
