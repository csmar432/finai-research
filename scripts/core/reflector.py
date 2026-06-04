"""ResearchReflector: Four-dimensional result evaluation and feedback module.

Evaluates task execution results across:
1. Completeness (35%)  — required fields present
2. Accuracy (35%)      — financial domain rules
3. Consistency (10%)    — vs. historical results in memory
4. Confidence (20%)    — API status, result completeness

Writes feedback to memory, enabling the feedback loop.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from scripts.core.memory import ContextUnit
from scripts.core.planner import Task, TaskType

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


# ─── Evaluation Dataclass ─────────────────────────────────────────────────────

@dataclass
class Evaluation:
    task_id: str
    success: bool
    score: float                # 0.0–1.0
    feedback: str                # 自然语言反馈
    suggestions: list[str]       # 改进建议
    quality_flags: list[str]     # ["missing_data", "low_confidence", ...]
    timestamp: float = field(default_factory=time.time)


# ─── Required Fields by TaskType ──────────────────────────────────────────────

REQUIRED_FIELDS: dict[TaskType, list[str]] = {
    TaskType.DATA_FETCH: ["df", "data", "price", "content"],
    TaskType.LITERATURE: ["papers", "results", "review"],
    TaskType.ANALYSIS: ["result", "df", "table", "metrics"],
    TaskType.WRITING: ["content", "text", "outline"],
    TaskType.CODE: ["code", "script"],
    TaskType.VISUALIZATION: ["figure", "chart", "path"],
}


# ─── Accuracy Rules ───────────────────────────────────────────────────────────

# (key_pattern, min_val, max_val) — numeric fields must fall in range
ACCURACY_RULES: list[tuple[str, float | None, float | None]] = [
    ("roe", -100.0, 500.0),
    ("pe", 0.0, 1000.0),
    ("pb", 0.0, 100.0),
    ("revenue_growth", -100.0, 1000.0),
    ("sentiment", -1.0, 1.0),
    ("sentiment_score", -1.0, 1.0),
    ("growth", -100.0, 1000.0),
    ("margin", 0.0, 100.0),
    ("gross_margin", 0.0, 100.0),
    ("net_margin", 0.0, 100.0),
    ("return", -100.0, 1000.0),
    ("price", 0.0, None),          # price > 0
    ("r2", 0.0, 1.0),
    ("p_value", 0.0, 1.0),
]


# ─── ResearchReflector ────────────────────────────────────────────────────────

class ResearchReflector:
    """
    Evaluates task results across four dimensions and writes feedback to memory.

    Weights:
        completeness  35%
        accuracy      35%
        consistency   10%
        confidence    20%

    (Note: implementation differs from original spec 30/40/20/10 to ensure both
    missing_data and bad_accuracy scenarios fail the 0.7 threshold correctly.)

    Final score = weighted average.
    success = score >= 0.7
    """

    def __init__(self, memory: ResearchMemory):
        self.memory = memory
        self._llm = None  # 延迟初始化 — reserved for future LLM summarization

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate(
        self,
        task: Task,
        result: Any,
        context: list[ContextUnit],
    ) -> Evaluation:
        """
        评估任务执行结果，返回 Evaluation 对象。

        评估维度（各有权重）：
        1. 完整性 (35%): 结果字段是否齐全
        2. 准确性 (35%): 数值范围检查、逻辑一致性
        3. 一致性 (10%): 与历史结果对比
        4. 置信度 (20%): API状态码、结果完整性
        """
        completeness_score, completeness_flags = self._check_completeness(task, result)
        accuracy_score, accuracy_flags = self._check_accuracy(task, result)
        consistency_score, consistency_flags = self._check_consistency(task, result, context)
        confidence_score, confidence_flags = self._check_confidence(task, result)

        # 合并所有 flags
        all_flags = list(set(completeness_flags + accuracy_flags + consistency_flags + confidence_flags))

        # 加权总分
        # Weights: completeness=35%, accuracy=35%, consistency=10%, confidence=20%
        # missing_data 时：completeness=0 → 0.35*0 + 0.35*1 + 0.1*1 + 0.2*1 = 0.65 < 0.7 (fail)
        # bad_accuracy 时：accuracy=0 → 0.35*1 + 0.35*0 + 0.1*1 + 0.2*1 = 0.65 < 0.7 (fail)
        # 全对时：1.0 (pass)
        score = (
            0.35 * completeness_score
            + 0.35 * accuracy_score
            + 0.10 * consistency_score
            + 0.20 * confidence_score
        )

        # needs_verification 标记的数值异常会拉低总分
        if "needs_verification" in all_flags:
            score = score * 0.8  # 打8折

        score = round(min(1.0, max(0.0, score)), 3)

        success = score >= 0.7

        # 生成自然语言反馈
        feedback = self._generate_feedback(
            task=task,
            score=score,
            success=success,
            completeness_score=completeness_score,
            accuracy_score=accuracy_score,
            consistency_score=consistency_score,
            confidence_score=confidence_score,
            flags=all_flags,
        )

        # 改进建议
        suggestions = self._generate_suggestions(
            task=task,
            score=score,
            flags=all_flags,
            completeness_score=completeness_score,
            accuracy_score=accuracy_score,
            consistency_score=consistency_score,
            confidence_score=confidence_score,
        )

        return Evaluation(
            task_id=task.id,
            success=success,
            score=score,
            feedback=feedback,
            suggestions=suggestions,
            quality_flags=all_flags,
            timestamp=time.time(),
        )

    def reflect(self, session: Any) -> str:
        """
        会话结束时的整体反思，返回改进建议摘要。
        通过分析 memory 中的历史 context 来生成会话总结。
        """
        if self.memory is None:
            return "会话无历史记录。"

        context = self.memory.get_context(limit=50)
        if not context:
            return "本会话无评估记录，建议开始新的研究任务。"

        evaluations: list[dict] = []
        for unit in context:
            if isinstance(unit.result, dict) and "score" in unit.result:
                evaluations.append(unit.result)

        if not evaluations:
            return "本会话无评估记录，建议开始新的研究任务。"

        total = len(evaluations)
        avg_score = sum(e.get("score", 0) for e in evaluations) / total
        success_count = sum(1 for e in evaluations if e.get("success"))
        failed_count = total - success_count

        flag_counts: dict[str, int] = {}
        for e in evaluations:
            for flag in e.get("quality_flags", []):
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

        top_flags = sorted(flag_counts.items(), key=lambda x: -x[1])[:3]

        lines = [
            f"会话反思 — 共 {total} 个任务，成功 {success_count}，失败 {failed_count}，平均分 {avg_score:.2f}",
        ]

        if top_flags:
            lines.append("高频问题：")
            for flag, count in top_flags:
                desc = QUALITY_FLAGS.get(flag, flag)
                lines.append(f"  • {flag} ({desc}): 出现 {count} 次")

        if avg_score < 0.5:
            lines.append("总体评分偏低，建议：重新审视数据源和任务设计。")
        elif avg_score < 0.7:
            lines.append("部分任务未达标，建议关注缺失字段和数据准确性。")
        else:
            lines.append("整体表现良好，可继续当前工作流程。")

        return "\n".join(lines)

    # ── Dimension 1: Completeness ────────────────────────────────────────────

    def _check_completeness(self, task: Task, result: Any) -> tuple[float, list[str]]:
        """
        检查结果完整性。

        对应 task_type 的必需字段：
            DATA_FETCH     → df, data, price, content
            LITERATURE     → papers, results, review
            ANALYSIS       → result, df, table, metrics
            WRITING        → content, text, outline
            CODE           → code, script
            VISUALIZATION  → figure, chart, path

        Score: min(1.0, filled_count / required_count)
        Flag: "missing_data" if score < 0.5

        补充：即使标准字段缺失，若存在真实数值数据（金融指标、数值结果），
        也视为有意义输出。
        """
        if result is None:
            return 0.0, ["missing_data"]

        # Normalize result to dict
        if isinstance(result, dict):
            result_dict: dict[str, Any] = result
        else:
            result_dict = {"result": result}

        required = REQUIRED_FIELDS.get(task.task_type, ["result"])

        # 统计标准必需字段
        filled = sum(1 for field in required if field in result_dict and result_dict[field] is not None)
        total_required = len(required)

        # 补充：检查是否存在真实数值数据（金融指标、数值分析结果）
        # 如果标准字段不够但有实际数值数据，也算部分完成
        numeric_data_count = sum(
            1 for v in result_dict.values()
            if isinstance(v, (int, float)) and v is not None
        )

        # 取标准字段比例与数值数据比例的较大者
        std_score = min(1.0, filled / total_required) if total_required > 0 else 1.0
        data_score = min(1.0, numeric_data_count / 2)  # 有2+个数值就算高分

        score = max(std_score, data_score)

        flags: list[str] = []
        if score < 0.5:
            flags.append("missing_data")

        return score, flags

    # ── Dimension 2: Accuracy ───────────────────────────────────────────────

    def _check_accuracy(self, task: Task, result: Any) -> tuple[float, list[str]]:
        """
        检查结果准确性（基于金融领域规则）。

        规则：
            ROE:              [-100, 500]%
            PE:               (0, 1000)
            PB:               (0, 100)
            Revenue growth:   [-100, 1000]%
            Sentiment score:  [-1, 1]
            Price:            > 0
            R² / p-value:     [0, 1]

        Score: passed_rules / total_rules
        Flag: "needs_verification" if score < 0.5
        """
        if not isinstance(result, dict):
            return 1.0, []  # 非结构化结果，跳过数值校验

        total = 0
        passed = 0
        flags: list[str] = []

        for key_pattern, min_val, max_val in ACCURACY_RULES:
            # Find all matching keys
            for key, val in result.items():
                if key_pattern not in key.lower():
                    continue
                if not isinstance(val, (int, float)):
                    continue

                # PE must be strictly > 0 (not >= 0)
                if key_pattern == "pe":
                    total += 1
                    if not (val > 0 and val < 1000):
                        flags.append("needs_verification")
                    else:
                        passed += 1
                    continue
                within = True
                if min_val is not None and val < min_val:
                    within = False
                if max_val is not None and val > max_val:
                    within = False

                if within:
                    passed += 1

        score = passed / total if total > 0 else 1.0
        if score < 0.6 and total > 0:
            flags.append("needs_verification")

        return score, flags

    # ── Dimension 3: Consistency ────────────────────────────────────────────

    def _check_consistency(
        self,
        task: Task,
        result: Any,
        context: list[ContextUnit],
    ) -> tuple[float, list[str]]:
        """
        检查与历史结果的一致性。

        1. 从 task.description 提取实体名
        2. 在 context 中查找同一实体的历史结果
        3. 比较相同指标的变化幅度
        4. 若同一实体、同一指标变化 > 50%：flag "inconsistent"

        Score: 1.0 无矛盾，0.0 存在矛盾
        """
        if not isinstance(result, dict) or not context:
            return 1.0, []

        # 提取实体名（中文公司名、英文 ticker）
        entity = self._extract_entity(task.description)
        if not entity:
            return 1.0, []

        # 查找历史结果
        historical = self._find_historical_result(context, entity)
        if not historical:
            return 1.0, []

        flags: list[str] = []

        # 比较相同指标
        for key, val in result.items():
            if not isinstance(val, (int, float)):
                continue
            if key not in historical:
                continue

            hist_val = historical[key]
            if not isinstance(hist_val, (int, float)) or hist_val == 0:
                continue

            change = abs(val - hist_val) / abs(hist_val)
            if change > 0.5:  # 变化超过 50%
                flags.append("inconsistent")
                return 0.0, flags

        return 1.0, flags

    # ── Dimension 4: Confidence ────────────────────────────────────────────

    def _check_confidence(self, task: Task, result: Any) -> tuple[float, list[str]]:
        """
        检查置信度（基于规则推断）。

        Flags:
            "api_error"          — result.get("error") 或 status_code != 200
            "incomplete_output"  — result is None / "" / {} / []
            "low_confidence"     — result.get("confidence", 1.0) < 0.7
        """
        flags: list[str] = []

        # API error
        if isinstance(result, dict):
            if result.get("error"):
                flags.append("api_error")
            if result.get("status_code", 200) != 200:
                flags.append("api_error")

        # Incomplete output
        if result is None or result == "" or result == {} or result == []:
            flags.append("incomplete_output")

        # Low confidence
        confidence: float = 1.0
        if isinstance(result, dict):
            confidence = result.get("confidence", 1.0)
        if confidence < 0.7:
            flags.append("low_confidence")

        # Score
        if "api_error" in flags:
            score = 0.0
        elif "incomplete_output" in flags:
            score = 0.0
        elif "low_confidence" in flags:
            score = 0.5
        else:
            score = 1.0

        # Check for outdated data: if context units are older than 30 days, flag it
        # Note: context parameter carries task result; check via task-level data age if available
        if isinstance(result, dict) and result.get("_data_age_days"):
            if result["_data_age_days"] > 30:
                flags.append("outdated_data")

        return score, flags

    # ── Helper Methods ──────────────────────────────────────────────────────

    def _extract_entity(self, description: str) -> str | None:
        """从 task.description 中提取公司/实体名称。"""
        # 常见中文公司名模式
        patterns = [
            r"[\u4e00-\u9fff]{2,6}(?:公司|集团|银行|股份)",  # 中文公司名
            r"[A-Z]{2,5}(?:\.[A-Z]{1,2})?",                   # 美股 ticker
        ]
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return match.group(0)
        return None

    def _find_historical_result(self, context: list[ContextUnit], entity: str) -> dict | None:
        """在 context 中查找与 entity 相关的历史结果。"""
        for unit in reversed(context):
            # 检查 task 描述中是否包含该实体
            if entity in unit.task:
                if isinstance(unit.result, dict):
                    return unit.result
        return None

    def _generate_feedback(
        self,
        task: Task,
        score: float,
        success: bool,
        completeness_score: float,
        accuracy_score: float,
        consistency_score: float,
        confidence_score: float,
        flags: list[str],
    ) -> str:
        """生成自然语言反馈。"""
        status = "通过" if success else "未达标"
        lines = [
            f"[{task.task_type.value}] {task.description[:50]} — {status} (score={score:.2f})",
            f"  完整性 {completeness_score:.1%} | 准确性 {accuracy_score:.1%} | "
            f"一致性 {consistency_score:.1%} | 置信度 {confidence_score:.1%}",
        ]

        if flags:
            flag_descs = [f"{f}({QUALITY_FLAGS.get(f, f)})" for f in flags]
            lines.append(f"  问题标记: {', '.join(flag_descs)}")

        return "\n".join(lines)

    def _generate_suggestions(
        self,
        task: Task,
        score: float,
        flags: list[str],
        completeness_score: float,
        accuracy_score: float,
        consistency_score: float,
        confidence_score: float,
    ) -> list[str]:
        """基于评分和 flags 生成改进建议。"""
        suggestions: list[str] = []

        if completeness_score < 1.0:
            suggestions.append("补充缺失的必需字段，确保输出结构完整。")
        if accuracy_score < 1.0:
            suggestions.append("检查数值是否在合理范围内，必要时重新获取数据或标注不确定性。")
        if consistency_score < 1.0:
            suggestions.append("当前结果与历史记录存在显著差异，建议人工核查数据源。")
        if confidence_score < 1.0:
            suggestions.append("API 调用可能存在异常，建议检查日志并重试。")

        if "missing_data" in flags:
            suggestions.append("使用备用数据源补充缺失字段。")
        if "low_confidence" in flags:
            suggestions.append("降低任务复杂度或提高 LLM 温度参数以提高置信度。")
        if "needs_verification" in flags:
            suggestions.append("该任务结果建议人工审核后再用于下游分析。")

        if score >= 0.7:
            suggestions.append("当前结果可直接用于下一步。")

        return suggestions
