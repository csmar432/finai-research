"""ResearchReflector: Four-dimensional result evaluation and feedback module.

Evaluation dimensions (weighted):
1. Completeness (30%): result fields齐全
2. Accuracy (40%): 数值范围检查、逻辑一致性
3. Consistency (20%): 与历史结果对比
4. Confidence (10%): LLM置信度、API状态码

Feedback loop:
    Task execution complete
        ↓
    Reflection.evaluate(task, result, context)
        ↓
    Evaluation(score, quality_flags)
        ↓
    ┌─ score >= 0.7 → 写入 Memory.context (evaluation=feedback)
    ├─ score < 0.7 且可修复 → 回退 Planner 重试（max 3次）
    ├─ score < 0.3 → 放弃，标记 BLOCKED，通知用户
    └─ quality_flags 包含 inconsistency → 追加验证步骤
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# ─── Quality Flags ────────────────────────────────────────────────────────────


QUALITY_FLAGS: dict[str, str] = {
    "missing_data": "关键数据缺失",
    "outdated_data": "数据超过30天未更新",
    "low_confidence": "LLM置信度低于0.7",
    "inconsistent": "与历史结果矛盾",
    "incomplete_output": "输出不完整",
    "api_error": "API调用失败",
    "needs_verification": "建议人工核查",
}

# Weights for the four evaluation dimensions
WEIGHT_COMPLETENESS = 0.3
WEIGHT_ACCURACY = 0.4
WEIGHT_CONSISTENCY = 0.2
WEIGHT_CONFIDENCE = 0.1

SUCCESS_THRESHOLD = 0.7


# ─── Evaluation Dataclass ─────────────────────────────────────────────────────


@dataclass
class Evaluation:
    task_id: str
    success: bool
    score: float  # 0.0–1.0
    feedback: str  # 自然语言反馈
    suggestions: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ─── Required Fields per TaskType ─────────────────────────────────────────────


# Required output fields per task type for completeness check
REQUIRED_FIELDS: dict[str, list[str]] = {
    "data_fetch": ["df", "data", "price", "content"],
    "literature": ["papers", "results", "review"],
    "analysis": ["result", "df", "table", "metrics"],
    "writing": ["content", "text", "outline"],
    "code": ["code", "script"],
    "visualization": ["figure", "chart", "path"],
}


# ─── Financial Domain Accuracy Rules ─────────────────────────────────────────


@dataclass
class AccuracyRule:
    """A single accuracy validation rule for a financial metric."""
    field: str  # key name in result dict
    min_val: float | None
    max_val: float | None
    message: str


ACCURACY_RULES: list[AccuracyRule] = [
    AccuracyRule("roe", -100.0, 500.0, "ROE must be in range [-100%, 500%]"),
    AccuracyRule("pe", 0.0, 1000.0, "PE ratio must be > 0 and < 1000"),
    AccuracyRule("pe_ratio", 0.0, 1000.0, "PE ratio must be > 0 and < 1000"),
    AccuracyRule("revenue_growth", -100.0, 1000.0, "Revenue growth must be in range [-100%, 1000%]"),
    AccuracyRule("growth", -100.0, 1000.0, "Growth must be in range [-100%, 1000%]"),
    AccuracyRule("price", 0.0, None, "Stock price must be > 0"),
    AccuracyRule("sentiment", -1.0, 1.0, "Sentiment score must be in range [-1, 1]"),
]


# ─── ResearchReflector ───────────────────────────────────────────────────────


class ResearchReflector:
    """
    Evaluates task execution results across four dimensions and writes feedback
    to memory, enabling the feedback loop.

    Dimensions (weights):
        - Completeness (30%): result fields are present
        - Accuracy (40%): numeric values within domain-valid ranges
        - Consistency (20%): compared against historical results in memory
        - Confidence (10%): LLM confidence / API status

    Final score = weighted average; success = score >= 0.7.
    """

    def __init__(self, memory: "ResearchMemory"):
        self.memory = memory
        self._llm = None  # lazy initialization — reserved for future LLM summarization

    # ── Public API ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        task: "Task",
        result: Any,
        context: list["ContextUnit"],
    ) -> Evaluation:
        """
        Evaluate a task execution result across four dimensions.

        Args:
            task: The Task that was executed.
            result: The result returned by the tool/executor.
            context: List of historical ContextUnits from memory.

        Returns:
            Evaluation dataclass with score, feedback, suggestions, quality_flags.
        """
        quality_flags: list[str] = []

        # 1. Completeness check (30%)
        completeness_score, completeness_flags = self._check_completeness(task, result)
        quality_flags.extend(completeness_flags)

        # 2. Accuracy check (40%)
        accuracy_score, accuracy_flags = self._check_accuracy(task, result)
        quality_flags.extend(accuracy_flags)

        # 3. Consistency check (20%)
        consistency_score, consistency_flags = self._check_consistency(task, result, context)
        quality_flags.extend(consistency_flags)

        # 4. Confidence check (10%)
        confidence_score, confidence_flags = self._infer_quality_flags(task, result)
        quality_flags.extend(confidence_flags)

        # Deduplicate flags
        quality_flags = list(dict.fromkeys(quality_flags))

        # Final weighted score
        score = (
            WEIGHT_COMPLETENESS * completeness_score
            + WEIGHT_ACCURACY * accuracy_score
            + WEIGHT_CONSISTENCY * consistency_score
            + WEIGHT_CONFIDENCE * confidence_score
        )
        score = round(min(1.0, max(0.0, score)), 4)
        success = score >= SUCCESS_THRESHOLD

        # If completeness is 0 (all required fields missing), flag as incomplete output
        # and lower confidence so the final score clearly falls below threshold
        if completeness_score == 0.0 and "incomplete_output" not in quality_flags:
            quality_flags.append("incomplete_output")
            confidence_score = min(confidence_score, 0.5)
            score = (
                WEIGHT_COMPLETENESS * completeness_score
                + WEIGHT_ACCURACY * accuracy_score
                + WEIGHT_CONSISTENCY * consistency_score
                + WEIGHT_CONFIDENCE * confidence_score
            )
            score = round(min(1.0, max(0.0, score)), 4)
            success = score >= SUCCESS_THRESHOLD

        # Build natural language feedback
        feedback = self._build_feedback(
            task=task,
            result=result,
            completeness_score=completeness_score,
            accuracy_score=accuracy_score,
            consistency_score=consistency_score,
            confidence_score=confidence_score,
            quality_flags=quality_flags,
        )

        # Generate improvement suggestions
        suggestions = self._generate_suggestions(
            quality_flags=quality_flags,
            completeness_score=completeness_score,
            accuracy_score=accuracy_score,
            consistency_score=consistency_score,
        )

        return Evaluation(
            task_id=task.id,
            success=success,
            score=score,
            feedback=feedback,
            suggestions=suggestions,
            quality_flags=quality_flags,
            timestamp=time.time(),
        )

    def reflect(self, session: Any) -> str:
        """
        Session-level reflection — summarizes all evaluations in memory
        and returns improvement suggestions.

        The `session` parameter is accepted for future use (ResearchSession
        not yet fully implemented). Currently reflects based on memory state.

        Returns:
            A string summarizing findings and recommended improvements.
        """
        context = self.memory.get_context(limit=20)

        if not context:
            return "会话暂无记录，建议开始一个研究任务以生成评估数据。"

        # Analyze quality flags across all context units
        flag_counts: dict[str, int] = {}
        total_evaluations = 0

        for unit in context:
            eval_text = unit.evaluation
            if eval_text:
                total_evaluations += 1
                for flag_key in QUALITY_FLAGS:
                    if flag_key in eval_text.lower():
                        flag_counts[flag_key] = flag_counts.get(flag_key, 0) + 1

        if total_evaluations == 0:
            return (
                "本次会话已完成但尚未生成评估数据。"
                "建议在后续任务中启用自动评估以获取质量反馈。"
            )

        # Build summary
        lines = [
            f"会话反思报告（基于 {total_evaluations} 项评估）",
            "",
        ]

        if flag_counts:
            lines.append("发现的质量问题：")
            for flag, count in sorted(flag_counts.items(), key=lambda x: -x[1]):
                flag_desc = QUALITY_FLAGS.get(flag, flag)
                lines.append(f"  - {flag_desc}: {count} 次")
            lines.append("")

        # Compute average score proxy from evaluation text
        avg_score_estimate = self._estimate_avg_score_from_context(context)

        lines.append(f"整体质量评估（估算）: {avg_score_estimate:.1%}")
        lines.append("")

        # Top improvement suggestions
        suggestions = self._session_improvement_suggestions(flag_counts)
        if suggestions:
            lines.append("改进建议：")
            for s in suggestions:
                lines.append(f"  - {s}")
        else:
            lines.append("整体表现良好，建议继续保持当前工作流程。")

        return "\n".join(lines)

    # ── Dimension Checks ────────────────────────────────────────────────────

    def _check_completeness(
        self,
        task: "Task",
        result: Any,
    ) -> tuple[float, list[str]]:
        """
        Check result completeness based on task type.

        Score = min(1.0, filled_count / required_count).
        If result has numeric values but none of the required fields, grant
        partial credit (0.5) for ANALYSIS tasks to avoid false negatives
        when tools return data under non-canonical field names.
        Flags: "missing_data" if score < 0.5.
        """
        task_type_key = task.task_type.value

        if result is None:
            return 0.0, ["missing_data"]

        result_dict: dict
        if isinstance(result, dict):
            result_dict = result
        else:
            return 0.5, []

        required = REQUIRED_FIELDS.get(task_type_key, [])
        if not required:
            return 1.0, []

        # Check how many required fields are present and non-None
        filled_count = 0
        for field_name in required:
            if field_name in result_dict and result_dict[field_name] is not None:
                filled_count += 1

        score = min(1.0, filled_count / len(required))

        # If no required fields found but result has meaningful numeric data,
        # grant partial credit for ANALYSIS tasks (tools may return data
        # under custom field names like "roe" instead of "result")
        if score == 0.0:
            # Local import to avoid circular dependency
            from scripts.core.planner import TaskType
            if task.task_type == TaskType.ANALYSIS:
                has_numeric = any(
                    isinstance(v, (int, float)) and v is not None
                    for v in result_dict.values()
                )
                if has_numeric:
                    score = 0.5

        flags: list[str] = []
        if score < 0.5:
            flags.append("missing_data")

        return round(score, 4), flags

    def _check_accuracy(
        self,
        task: "Task",
        result: Any,
    ) -> tuple[float, list[str]]:
        """
        Check result accuracy against financial domain rules.

        Score = passed_rules / total_applicable_rules.
        Flags: "needs_verification" if score < 0.5.
        """
        if not isinstance(result, dict):
            return 1.0, []

        applicable_rules = [
            rule for rule in ACCURACY_RULES if rule.field in result
        ]

        if not applicable_rules:
            return 1.0, []

        passed_count = 0
        flags: list[str] = []

        for rule in applicable_rules:
            value = result.get(rule.field)
            if value is None:
                continue

            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                flags.append("needs_verification")
                continue

            # Validate range
            if rule.min_val is not None and numeric_value < rule.min_val:
                flags.append("needs_verification")
                continue
            if rule.max_val is not None and numeric_value > rule.max_val:
                flags.append("needs_verification")
                continue

            passed_count += 1

        score = passed_count / len(applicable_rules)

        if score < 0.5 and not flags:
            flags.append("needs_verification")

        return round(score, 4), list(dict.fromkeys(flags))

    def _check_consistency(
        self,
        task: "Task",
        result: Any,
        context: list["ContextUnit"],
    ) -> tuple[float, list[str]]:
        """
        Check consistency with historical results in context.

        Looks for entity names in task description, then compares overlapping
        numeric values. If same entity, same metric, difference > 50%,
        flag "inconsistent".

        Score: 1.0 if no contradiction, 0.0 if contradiction found.
        """
        if not isinstance(result, dict) or not context:
            return 1.0, []

        # Extract entity name from task description
        entity_name = self._extract_entity_name(task.description)
        if not entity_name:
            return 1.0, []

        # Find historical results for the same entity
        historical: dict[str, float] = {}
        for unit in context:
            if self._entity_mentioned(entity_name, unit.task):
                if isinstance(unit.result, dict):
                    for key, value in unit.result.items():
                        if isinstance(value, (int, float)) and value is not None:
                            historical[key] = float(value)

        if not historical:
            return 1.0, []

        # Compare overlapping keys
        flags: list[str] = []
        for key, current_value in result.items():
            if not isinstance(current_value, (int, float)) or current_value is None:
                continue
            if key in historical:
                historical_value = historical[key]
                if historical_value == 0:
                    if current_value != 0:
                        flags.append("inconsistent")
                        break
                else:
                    relative_diff = abs(current_value - historical_value) / abs(historical_value)
                    if relative_diff > 0.5:
                        flags.append("inconsistent")
                        break

        if "inconsistent" in flags:
            return 0.0, flags
        return 1.0, []

    def _infer_quality_flags(
        self,
        task: "Task",
        result: Any,
    ) -> tuple[float, list[str]]:
        """
        Rule-based quality flag inference from result structure.

        Score: 1.0 if no problem signals, lower otherwise.
        Flags inferred:
            - "api_error": result.get("error") or status_code != 200
            - "incomplete_output": result is None / empty string / empty dict/list
            - "low_confidence": result.get("confidence", 1.0) < 0.7
        """
        flags: list[str] = []

        # api_error check
        if isinstance(result, dict):
            if result.get("error"):
                flags.append("api_error")
            status_code = result.get("status_code")
            if status_code is not None and status_code != 200:
                flags.append("api_error")

        # incomplete_output check
        if result is None:
            flags.append("incomplete_output")
        elif isinstance(result, str) and result.strip() == "":
            flags.append("incomplete_output")
        elif isinstance(result, (list, dict)) and len(result) == 0:
            flags.append("incomplete_output")

        # low_confidence check
        confidence: float | None = None
        if isinstance(result, dict):
            confidence = result.get("confidence")
        elif isinstance(result, float):
            confidence = result

        if confidence is not None and confidence < 0.7:
            flags.append("low_confidence")
            confidence_score = confidence
        else:
            confidence_score = 1.0

        return round(confidence_score, 4), list(dict.fromkeys(flags))

    # ── Helper Methods ─────────────────────────────────────────────────────

    # ── Task verbs that should not be returned as entity names ────────────────

    _TASK_VERBS: frozenset[str] = frozenset({
        "再次", "分析", "获取", "检索", "查询", "搜索",
        "下载", "生成", "追踪", "对比", "任务",
        "完成", "执行", "开始", "结束", "处理",
        "写入", "读取", "存储", "提取", "计算",
    })

    def _extract_entity_name(self, description: str) -> str | None:
        """
        Extract a company/entity name from task description.

        Strategy:
        1. Find the full 2-6 character Chinese sequence (re.search, not findall)
           to avoid splitting valid entity names like "苹果PE" → "苹果"
        2. Strip known verb prefixes to get the entity core
        3. If that yields a 2+ char Chinese word, return it
        4. Fall back to English capitalized names
        """
        # Step 1: find the full Chinese sequence (greedy, so "苹果" in "再次分析苹果PE")
        cn_match = re.search(r'[\u4e00-\u9fa5]{2,6}', description)
        if cn_match:
            text = cn_match.group(0)
            # Step 2: strip all known verb prefixes (longest first) to get entity core
            # Keep stripping until we get a pure-Chinese 2+ char result or run out of verbs
            remaining = text
            for verb in sorted(self._TASK_VERBS, key=len, reverse=True):
                if remaining.startswith(verb):
                    remaining = remaining[len(verb):]
            # Step 3: remaining is the entity core
            if len(remaining) >= 2:
                return remaining

        # Step 4: English company name (capitalized words)
        en_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', description)
        if en_match:
            return en_match.group(1)

        return None

    def _entity_mentioned(self, entity: str, text: str) -> bool:
        """Check if entity name is mentioned in text (case-insensitive)."""
        return entity.lower() in text.lower()

    def _build_feedback(
        self,
        task: "Task",
        result: Any,
        completeness_score: float,
        accuracy_score: float,
        consistency_score: float,
        confidence_score: float,
        quality_flags: list[str],
    ) -> str:
        """Build natural language feedback string from evaluation results."""
        parts: list[str] = []

        # Overall score
        overall = (
            WEIGHT_COMPLETENESS * completeness_score
            + WEIGHT_ACCURACY * accuracy_score
            + WEIGHT_CONSISTENCY * consistency_score
            + WEIGHT_CONFIDENCE * confidence_score
        )
        overall = round(min(1.0, max(0.0, overall)), 4)

        if overall >= 0.9:
            parts.append(f"任务「{task.description}」执行质量优秀（综合得分 {overall:.0%}）。")
        elif overall >= 0.7:
            parts.append(f"任务「{task.description}」执行质量良好（综合得分 {overall:.0%}）。")
        elif overall >= 0.5:
            parts.append(f"任务「{task.description}」执行质量一般（综合得分 {overall:.0%}），建议关注以下问题。")
        else:
            parts.append(f"任务「{task.description}」执行质量不达标（综合得分 {overall:.0%}），需要重点改进。")

        # Dimension breakdown
        dim_map = [
            ("完整性", completeness_score, WEIGHT_COMPLETENESS),
            ("准确性", accuracy_score, WEIGHT_ACCURACY),
            ("一致性", consistency_score, WEIGHT_CONSISTENCY),
            ("置信度", confidence_score, WEIGHT_CONFIDENCE),
        ]
        dim_lines = []
        for name, score, weight in dim_map:
            weighted = score * weight
            dim_lines.append(f"{name} {score:.0%}（权重 {weight:.0%}）")
        parts.append(" | ".join(dim_lines))

        # Flag descriptions
        if quality_flags:
            flag_descriptions = [
                QUALITY_FLAGS.get(f, f) for f in quality_flags
            ]
            parts.append(f"发现问题：{'、'.join(flag_descriptions)}。")

        return " ".join(parts)

    def _generate_suggestions(
        self,
        quality_flags: list[str],
        completeness_score: float,
        accuracy_score: float,
        consistency_score: float,
    ) -> list[str]:
        """Generate improvement suggestions based on quality flags and scores."""
        suggestions: list[str] = []

        if completeness_score < 0.5:
            suggestions.append("补充缺失的关键字段，确保结果结构完整。")

        if accuracy_score < 0.5:
            suggestions.append("检查数值范围是否符合金融领域规则，建议重新验证数据来源。")

        if consistency_score < 0.5:
            suggestions.append("当前结果与历史记录存在较大差异，建议人工核查或更新历史数据。")

        if "low_confidence" in quality_flags:
            suggestions.append("LLM置信度较低，建议使用更强大的模型重新执行，或提供更清晰的输入。")

        if "api_error" in quality_flags:
            suggestions.append("API调用失败，建议检查网络连接或接口可用性，稍后重试。")

        if "outdated_data" in quality_flags:
            suggestions.append("数据过于陈旧，建议更新数据源或明确标注数据截止日期。")

        if not suggestions:
            suggestions.append("当前结果质量良好，建议保持现有工作流程。")

        return suggestions

    def _session_improvement_suggestions(
        self,
        flag_counts: dict[str, int],
    ) -> list[str]:
        """Generate session-level improvement suggestions from flag distribution."""
        suggestions: list[str] = []

        if flag_counts.get("missing_data", 0) >= 2:
            suggestions.append("多次出现数据缺失问题，建议完善工具的返回值定义。")

        if flag_counts.get("inconsistent", 0) >= 2:
            suggestions.append("多次出现数据不一致，建议建立数据版本管理机制。")

        if flag_counts.get("low_confidence", 0) >= 2:
            suggestions.append("LLM置信度持续偏低，建议优化Prompt或切换更强模型。")

        if flag_counts.get("api_error", 0) >= 2:
            suggestions.append("API错误频繁，建议增加重试机制和熔断策略。")

        if flag_counts.get("needs_verification", 0) >= 3:
            suggestions.append("大量结果需要人工核查，建议改进数据验证规则。")

        return suggestions

    def _estimate_avg_score_from_context(
        self,
        context: list["ContextUnit"],
    ) -> float:
        """
        Estimate average quality score from context evaluation strings.
        Parses percentage values from evaluation text.
        """
        scores: list[float] = []

        for unit in context:
            eval_text = unit.evaluation or ""
            # Look for patterns like "87%" or "0.87" in the text
            matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', eval_text)
            for m in matches:
                val = float(m)
                if val > 1:
                    val = val / 100.0
                if 0 <= val <= 1:
                    scores.append(val)

        if not scores:
            return 0.7  # default

        return sum(scores) / len(scores)
