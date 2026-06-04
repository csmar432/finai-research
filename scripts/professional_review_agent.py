#!/usr/bin/env python3
"""
专业评审 Agent — AcademicPaperReviewer
=====================================
严格遵循 halt-rule-driven 审稿机制的专业学术论文评审 Agent。

核心机制：
  - 论文质量分级（优秀/良好/合格/不合格）
  - 多轮迭代修订（最多 5 轮）
  - 硬性 halt 规则（任何一项触发即拒绝）
  - 软性 halt 规则（累积触发则升级）
  - 统计显著性验证（回归结果必须有 p 值）

halt 规则清单：
  [硬性 - 任一触发即拒绝]
  H1. 引用缺失或不准确（引用DOI/标题不匹配）
  H2. 数据虚构（回归系数无法溯源）
  H3. 关键假设缺失（未说明稳健性检验）
  H4. 图表数据与正文数据不一致

  [软性 - 累积触发则降级]
  S1. 方法论描述不充分
  S2. 写作质量（语法/结构）
  S3. 逻辑连贯性
  S4. 格式规范

质量评分：
  90-100: 优秀 (Excellent) → 可投稿
  80-89:  良好 (Good)      → 小修后可投稿
  70-79:  合格 (Acceptable) → 大修后重审
  <70:    不合格 (Reject)  → 拒绝

用法：
  from scripts.professional_review_agent import AcademicPaperReviewer

  reviewer = AcademicPaperReviewer(config, gateway)
  result = reviewer.run({
      "paper_text": full_paper,
      "empirical_data": regression_results,
      "provenance": provenance_tracker,
  })
  print(result.output)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from scripts.core.agents.base import (
    AgentConfig,
    BaseAgent,
    HaltDecision,
)

# ════════════════════════════════════════════════════════════════════
# HALT RULE DEFINITIONS
# ════════════════════════════════════════════════════════════════════

@dataclass
class HaltRule:
    """
    审稿规则定义。
    """
    code: str            # 唯一标识
    description: str     # 规则描述
    severity: str        # "hard" | "soft"
    category: str        # "citation" | "data" | "methodology" | "writing" | "format"
    threshold: float = 1.0  # 触发阈值（>= 触发）
    weight: float = 1.0  # 软性规则的权重（累积得分用）

    def is_hard(self) -> bool:
        return self.severity == "hard"


# 硬性规则（任何一项触发即拒绝）
HARD_HALT_RULES = [
    HaltRule(
        code="H1_CITATION_INVALID",
        description="引用缺失或不准确。引用DOI或标题与实际论文不符；引用覆盖率低于70%。",
        severity="hard",
        category="citation",
    ),
    HaltRule(
        code="H2_DATA_FABRICATED",
        description="数据虚构。回归系数、标准误、样本量无法溯源；显著性标注与p值不匹配。",
        severity="hard",
        category="data",
    ),
    HaltRule(
        code="H3_KEY_ASSUMPTION_MISSING",
        description="关键假设缺失。未说明识别策略假设（如平行趋势、DID同质性）；稳健性检验缺失。",
        severity="hard",
        category="methodology",
    ),
    HaltRule(
        code="H4_TABLE_TEXT_MISMATCH",
        description="图表数据与正文描述不一致。表格数字与正文所述方向或显著性不符。",
        severity="hard",
        category="data",
    ),
    HaltRule(
        code="H5_ABSTRACT_MISSING",
        description="摘要缺失或过短（<150词）。摘要必须包含研究问题、方法、主要发现和结论。",
        severity="hard",
        category="format",
    ),
    HaltRule(
        code="H6_REGRESSION_STARS_INVALID",
        description="显著性星号标注错误。***/**/* 与 p 值不匹配（如 p=0.15 标 ***）。",
        severity="hard",
        category="data",
    ),
]

# 软性规则（累积触发则降级）
SOFT_HALT_RULES = [
    HaltRule(
        code="S1_METHODOLOGY_THIN",
        description="方法论描述不够充分。缺少识别策略、估计方法或识别假设的详细说明。",
        severity="soft",
        category="methodology",
        weight=0.10,
    ),
    HaltRule(
        code="S2_WRITING_QUALITY",
        description="写作质量欠佳。存在语法错误、表达不清晰或逻辑断层。",
        severity="soft",
        category="writing",
        weight=0.08,
    ),
    HaltRule(
        code="S3_COHERENCE",
        description="逻辑连贯性不足。引言→文献综述→方法→结果的逻辑链不清晰。",
        severity="soft",
        category="writing",
        weight=0.08,
    ),
    HaltRule(
        code="S4_FORMAT_INCOMPLETE",
        description="格式规范不完整。缺少图表标题、公式编号、参考文献格式不符合期刊要求。",
        severity="soft",
        category="format",
        weight=0.05,
    ),
    HaltRule(
        code="S5_LITERATURE_STALE",
        description="文献综述过时。缺少近3年重要文献；引用以次要文献为主。",
        severity="soft",
        category="citation",
        weight=0.07,
    ),
    HaltRule(
        code="S6_CONCLUSION_WEAK",
        description="结论过于薄弱。缺少对理论/实践的启示；未承认研究局限性。",
        severity="soft",
        category="writing",
        weight=0.06,
    ),
    HaltRule(
        code="S7_FIGURE_QUALITY",
        description="图表质量欠佳。轴标签不清晰、图例缺失、DPI不足（<300）。",
        severity="soft",
        category="format",
        weight=0.04,
    ),
]

ALL_RULES = HARD_HALT_RULES + SOFT_HALT_RULES


@dataclass
class ReviewReport:
    """结构化审稿报告。"""
    verdict: str              # "accept" | "minor_revise" | "major_revise" | "reject"
    score: float             # 0-100
    hard_violations: list[dict]
    soft_violations: list[dict]
    overall_comments: str
    detailed_feedback: list[dict]
    checklist: dict[str, bool]  # 格式检查清单
    provenance_check: dict[str, Any]  # 数据溯源检查结果
    regression_check: dict[str, Any]  # 回归质量检查
    iteration: int = 1


# ════════════════════════════════════════════════════════════════════
# ACADEMIC PAPER REVIEWER AGENT
# ════════════════════════════════════════════════════════════════════

class AcademicPaperReviewer(BaseAgent):
    """
    专业学术论文评审 Agent。

    严格遵循 halt-rule-driven 审稿机制：
      - 硬性规则：任何一项触发即拒绝
      - 软性规则：累积加权扣分
      - 实证数据验证：检查回归系数、标准误、显著性与表格一致性
      - 多轮迭代：最多 5 轮修订 → 重审

    使用方法：
      reviewer = AcademicPaperReviewer(config, gateway)
      result = reviewer.run({"paper_text": ..., "empirical_data": ...})
    """

    # 评分区间
    SCORE_GRADES = [
        (90, "优秀 (Excellent)", "accept"),
        (80, "良好 (Good)", "minor_revise"),
        (70, "合格 (Acceptable)", "major_revise"),
        (0, "不合格 (Reject)", "reject"),
    ]

    def __init__(self, config: AgentConfig, gateway, halt_rules: list[HaltRule] | None = None):
        super().__init__(config, gateway)
        self.hard_rules = halt_rules if halt_rules else HARD_HALT_RULES
        self.soft_rules = SOFT_HALT_RULES

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        执行论文审稿。

        Context keys:
            paper_text: 完整论文文本
            sections: dict 各章节文本
            empirical_data: dict 实证结果（如回归表格）
            provenance: ProvenanceTracker 数据溯源跟踪器
            tables: list[dict] 表格数据（用于一致性检查）
            figures: list[str] 图表路径列表
        """
        paper_text = context.get("paper_text", "")
        sections = context.get("sections", {})
        empirical_data = context.get("empirical_data", {})
        provenance = context.get("provenance")
        tables = context.get("tables", [])
        figures = context.get("figures", [])
        iteration = context.get("_iteration", 1)

        # 构建审稿 prompt
        rules_text = self._build_rules_prompt()
        data_check_prompt = self._build_data_check_prompt(empirical_data, provenance)
        structure_prompt = self._build_structure_prompt(sections)
        writing_prompt = self._build_writing_prompt(paper_text)

        # 分模块审稿
        prompt = f"""你是学术期刊的专业审稿人。请对以下论文进行全面审稿。

{rules_text}

{data_check_prompt}

{structure_prompt}

{writing_prompt}

请输出严格符合以下 JSON 格式的审稿报告，不要包含任何 Markdown 代码块：
{{
  "verdict": "accept" | "minor_revise" | "major_revise" | "reject",
  "score": 0-100,
  "hard_violations": [
    {{"rule_code": "H1_CITATION_INVALID", "location": "具体位置", "issue": "具体问题", "suggestion": "修改建议"}}
  ],
  "soft_violations": [
    {{"rule_code": "S1_METHODOLOGY_THIN", "severity": "soft", "location": "具体位置", "issue": "具体问题", "suggestion": "修改建议"}}
  ],
  "overall_comments": "总体评价（1-3句话）",
  "detailed_feedback": [
    {{"section": "章节名", "comments": "具体审稿意见"}}
  ],
  "checklist": {{
    "has_abstract": true/false,
    "has_introduction": true/false,
    "has_methodology": true/false,
    "has_results": true/false,
    "has_conclusion": true/false,
    "abstract_has_problem_method_result_conclusion": true/false,
    "has_robustness_check": true/false,
    "has_parallel_trends": true/false,
    "citation_coverage_above_70": true/false,
    "tables_have_sources": true/false,
    "figures_have_captions": true/false,
    "all_regression_results_contain_standard_errors": true/false,
    "all_regression_results_contain_observations": true/false
  }},
  "provenance_check": {{
    "all_coefficients_traced": true/false,
    "no_simulated_data_without_warning": true/false,
    "data_sources_documented": true/false
  }},
  "regression_check": {{
    "stars_match_pvalues": true/false,
    "standard_errors_reported": true/false,
    "clustering_strategy_justified": true/false,
    "effect_sizes_reasonable": true/false
  }}
}}"""

        response = self._generate(prompt, format_json=True)

        try:
            review = self._parse_json_response(response.response)
        except ValueError:
            review = {
                "verdict": "major_revise",
                "score": 60,
                "hard_violations": [{"rule_code": "FORMAT_ERROR", "issue": "无法解析审稿结果JSON"}],
                "soft_violations": [],
                "overall_comments": "审稿过程出错，格式错误",
                "detailed_feedback": [],
                "checklist": {},
                "provenance_check": {},
                "regression_check": {},
            }

        return {
            "review": review,
            "model": response.model_used,
            "latency_ms": response.latency_ms,
            "iteration": iteration,
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        """评估审稿结果，决定是否需要修订。"""
        review = act_result.get("review", {})
        verdict = review.get("verdict", "major_revise")
        score = review.get("score", 0)
        hard_violations = review.get("hard_violations", [])
        soft_violations = review.get("soft_violations", [])

        # 硬性规则：任何一项触发即拒绝
        if hard_violations:
            violation_codes = [v.get("rule_code", "UNKNOWN") for v in hard_violations]
            violation_summary = "\n".join(
                f"  • [{v.get('rule_code')}] {v.get('issue', '')}"
                for v in hard_violations[:5]
            )
            return {
                "halt": HaltDecision.REJECTED,
                "feedback": (
                    f"硬性规则触发，拒绝论文：\n{violation_summary}\n\n"
                    f"必须解决上述所有硬性问题后才能重新提交。"
                ),
                "score": score / 100,
                "flags": violation_codes,
            }

        # 评分判断
        if score >= 90:
            return {
                "halt": HaltDecision.APPROVED,
                "feedback": f"论文质量优秀（得分 {score}/100），推荐接受。{review.get('overall_comments', '')}",
                "score": score / 100,
                "flags": [],
            }
        elif score >= 80:
            return {
                "halt": HaltDecision.APPROVED,
                "feedback": f"论文质量良好（得分 {score}/100），小修后可接受。{review.get('overall_comments', '')}",
                "score": score / 100,
                "flags": [v.get("rule_code") for v in soft_violations[:3]],
            }
        elif score >= 70:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": (
                    f"论文合格（得分 {score}/100），需要大修。\n"
                    f"软性规则问题：\n" + "\n".join(
                        f"  • [{v.get('rule_code')}] {v.get('issue', '')}"
                        for v in soft_violations[:5]
                    )
                ),
                "score": score / 100,
                "flags": [v.get("rule_code") for v in soft_violations[:5]],
            }
        else:
            return {
                "halt": HaltDecision.REJECTED,
                "feedback": (
                    f"论文不合格（得分 {score}/100），拒绝。\n"
                    f"主要问题：\n" + "\n".join(
                        f"  • [{v.get('rule_code')}] {v.get('issue', '')}"
                        for v in hard_violations + soft_violations[:5]
                    )
                ),
                "score": score / 100,
                "flags": [v.get("rule_code") for v in (hard_violations + soft_violations)[:5]],
            }

    # ── Prompt 构建 ───────────────────────────────────────────────────────

    def _build_rules_prompt(self) -> str:
        """构建审稿规则 prompt。"""
        hard_lines = [
            f"- [{r.code}] {r.description}（硬性规则，触发即拒绝）"
            for r in self.hard_rules
        ]
        soft_lines = [
            f"- [{r.code}] {r.description}（软性规则，累积降级，权重={r.weight}）"
            for r in self.soft_rules
        ]
        return f"""## 审稿规则

### 硬性规则（触发即拒绝）
{chr(10).join(hard_lines)}

### 软性规则（累积触发则降级）
{chr(10).join(soft_lines)}

评分标准：
  90-100: 优秀 (Excellent) → 可投稿
  80-89:  良好 (Good)      → 小修后可投稿
  70-79:  合格 (Acceptable) → 大修后重审
  <70:    不合格 (Reject)  → 拒绝"""

    def _build_data_check_prompt(self, empirical_data: dict, provenance) -> str:
        """构建数据验证 prompt。"""
        if not empirical_data:
            return "### 数据检查\n（无实证数据）"

        provenance_note = ""
        if provenance:
            summary = provenance.summary() if hasattr(provenance, 'summary') else {}
            sim_fields = provenance.simulated_fields() if hasattr(provenance, 'simulated_fields') else []
            provenance_note = f"\n- 模拟字段: {sim_fields or '无'}"
            provenance_note += f"\n- 总字段: {summary.get('total_fields', 'N/A')}"

        tables_info = ""
        if empirical_data.get("tables"):
            for i, tbl in enumerate(empirical_data.get("tables", [])[:3]):
                rows = tbl.get("data", [])
                if rows:
                    provenance_note += f"\n表格{i+1} 行数: {len(rows)}"

        return f"""### 数据溯源检查
必须验证以下内容：
- 所有回归系数的来源（是否来自数据，不是编造）
- 显著性星号标注与 p 值是否匹配（p<0.01=***, p<0.05=**, p<0.10=*）
- 表格中的样本量、均值、标准误是否合理
- 是否存在模拟数据未标注的情况
{providence_note}{tables_info}"""

    def _build_structure_prompt(self, sections: dict) -> str:
        """构建论文结构检查 prompt。"""
        if not sections:
            return "### 论文结构\n（未提供章节文本）"

        required = ["abstract", "introduction", "methodology", "results", "conclusion"]
        found = [s for s in required if s.lower() in {k.lower() for k in sections.keys()}]
        missing = [s for s in required if s.lower() not in {k.lower() for k in sections.keys()}]

        return f"""### 论文结构检查
必需章节：{required}
已提供：{found}
缺失章节：{missing or '无'}"""

    def _build_writing_prompt(self, paper_text: str) -> str:
        """构建写作质量检查 prompt。"""
        if not paper_text:
            return "### 写作质量\n（无论文文本）"

        # 截断避免 token 超限
        truncated = paper_text[:8000]
        word_count = len(paper_text.split())
        abstract_match = re.search(r"abstract[:\s]*(.{100,500}?)(?:\n\n|\n\s*\n)", paper_text, re.IGNORECASE)
        abstract = abstract_match.group(1) if abstract_match else "未找到摘要"

        return f"""### 写作质量检查
全文词数：{word_count}
摘要（首200字符）：{abstract[:200]}

检查要点：
1. 摘要是否包含：研究问题、方法、主要发现、结论（4个要素）
2. 引言是否有研究动机和核心贡献声明
3. 方法论章节是否有识别策略、估计方法、假设说明
4. 结论章节是否有理论启示、实践启示和局限性承认
5. 是否存在明显的语法错误或表达不清之处"""

    # ── 辅助方法 ───────────────────────────────────────────────────────

    def generate_review_letter(self, review: dict, context: dict) -> str:
        """
        根据审稿报告生成正式审稿信。

        Args:
            review: 审稿报告 dict
            context: 原始上下文

        Returns:
            格式化的审稿信文本
        """
        verdict_map = {
            "accept": "接受",
            "minor_revise": "小修后接受",
            "major_revise": "大修后重审",
            "reject": "拒绝",
        }
        verdict_cn = verdict_map.get(review.get("verdict", ""), review.get("verdict", ""))
        score = review.get("score", 0)

        lines = [
            "=" * 60,
            "学术论文审稿意见书",
            "=" * 60,
            f"审稿结论：{verdict_cn}（得分：{score}/100）",
            "",
            "一、总体评价",
            "-" * 40,
            review.get("overall_comments", ""),
            "",
            "二、硬性规则问题（必须解决）",
            "-" * 40,
        ]

        hard = review.get("hard_violations", [])
        if hard:
            for i, v in enumerate(hard, 1):
                lines.append(f"  {i}. [{v.get('rule_code')}] {v.get('issue', '')}")
                if v.get("suggestion"):
                    lines.append(f"     修改建议：{v.get('suggestion')}")
        else:
            lines.append("  无硬性规则问题。")

        lines.extend([
            "",
            "三、软性规则建议（改进项）",
            "-" * 40,
        ])

        soft = review.get("soft_violations", [])
        if soft:
            for i, v in enumerate(soft, 1):
                lines.append(f"  {i}. [{v.get('rule_code')}] {v.get('issue', '')}")
                if v.get("suggestion"):
                    lines.append(f"     修改建议：{v.get('suggestion')}")
        else:
            lines.append("  无软性规则问题。")

        lines.extend([
            "",
            "四、详细审稿意见",
            "-" * 40,
        ])

        detailed = review.get("detailed_feedback", [])
        if detailed:
            for fb in detailed:
                lines.append(f"\n  [{fb.get('section', 'General')}]")
                lines.append(f"  {fb.get('comments', '')}")
        else:
            lines.append("  无详细章节意见。")

        lines.extend([
            "",
            "=" * 60,
            "格式检查清单",
            "-" * 40,
        ])

        checklist = review.get("checklist", {})
        for item, passed in checklist.items():
            status = "✅" if passed else "❌"
            lines.append(f"  {status} {item}")

        lines.append("=" * 60)

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ════════════════════════════════════════════════════════════════════

def validate_regression_table(table: pd.DataFrame | dict) -> dict:
    """
    验证回归表格的质量。

    检查：
    - 显著性星号与 p 值是否匹配
    - 标准误是否合理（非负、有量纲）
    - 观测数是否合理
    - 系数是否有预期符号

    Returns:
        dict with keys: valid, errors, warnings
    """
    errors = []
    warnings = []

    if isinstance(table, dict):
        coefs = table.get("all_coefs", {})
        n_obs = table.get("n_obs", 0)
        r2 = table.get("r_squared", 0)
    elif isinstance(table, pd.DataFrame):
        coefs = {str(k): v for k, v in table.to_dict("index").items()}
        n_obs = 0
        r2 = 0
    else:
        return {"valid": False, "errors": ["Unknown table format"], "warnings": []}

    for var, vals in coefs.items():
        if not isinstance(vals, dict):
            continue

        coef = vals.get("coef", 0)
        se = vals.get("se", 0)
        pval = vals.get("pval", 1)
        sig = vals.get("sig", "")

        # 检查标准误非负
        if se < 0:
            errors.append(f"{var}: 标准误为负数 ({se:.4f})")

        # 检查显著性星号与 p 值匹配
        if pval < 0.001 and "***" not in sig:
            errors.append(f"{var}: p={pval:.4f} 但未标注 ***")
        elif 0.001 <= pval < 0.01 and "**" not in sig and "***" not in sig:
            warnings.append(f"{var}: p={pval:.4f} 可标注 ** 或 ***")
        elif 0.01 <= pval < 0.05 and "*" not in sig and "**" not in sig:
            warnings.append(f"{var}: p={pval:.4f} 可标注 * 或 **")
        elif 0.05 <= pval < 0.10 and "dagger" not in sig.lower() and "*" not in sig:
            warnings.append(f"{var}: p={pval:.4f} 可标注 \\dagger 或 *")

        # 检查标准误量级（不应比系数大10倍以上）
        if se > 0 and abs(coef) > 0 and se / abs(coef) > 10:
            warnings.append(f"{var}: 标准误远大于系数（比值={se/abs(coef):.1f}）")

    # 检查观测数
    if n_obs > 0 and n_obs < 30:
        warnings.append(f"样本量较小（N={n_obs}），稳健性存疑")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ════════════════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("AcademicPaperReviewer — 专业评审 Agent")
    print("=" * 50)
    print(f"硬性规则: {len(HARD_HALT_RULES)} 条")
    print(f"软性规则: {len(SOFT_HALT_RULES)} 条")
    print()
    print("硬性规则清单:")
    for r in HARD_HALT_RULES:
        print(f"  [{r.code}] {r.description[:60]}")
    print()
    print("软性规则清单:")
    for r in SOFT_HALT_RULES:
        print(f"  [{r.code}] {r.description[:60]} (权重={r.weight})")
