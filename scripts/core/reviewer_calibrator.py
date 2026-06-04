"""
reviewer_calibrator.py — Reviewer 校准器

对 DualReviewer 的评分进行量化校准和偏见探测：

1. 量化校准（Quantitative Calibration）
   - Ground Truth 校准：使用已发表论文/黄金标准评估 reviewer 评分准确性
   - 评分分布校准：将 reviewer 评分映射到统计上一致的分布
   - 跨期刊标准化：不同期刊标准不同，校准到统一尺度

2. 偏见探测（Bias Detection）
   - 系统性偏见：作者/机构/期刊/方法论偏好
   - 顺序效应：先评分的维度分数偏高
   - 疲劳效应：长篇论文后期评分趋于宽松
   - 锚定效应：受初始分数影响

3. 校准报告
   - 评分偏差报告
   - 偏见模式识别
   - 改进建议

Usage:
    calibrator = ReviewerCalibrator(reviewer=DualReviewer(...))

    # Ground truth 校准
    calibrated = calibrator.calibrate_with_ground_truth(
        review_report=report,
        ground_truth=known_evaluation,
    )

    # 偏见探测
    biases = calibrator.detect_biases(review_history=history)

    # 生成校准报告
    report = calibrator.generate_calibration_report(...)
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ReviewerCalibrator",
    "BiasType",
    "CalibrationResult",
    "BiasReport",
    "CalibrationReport",
]


# ─── 数据类型 ───────────────────────────────────────────────────────────────

class BiasType(str, Enum):
    """偏见类型。"""
    AUTHOR_BIAS = "author_bias"           # 作者偏好
    INSTITUTION_BIAS = "institution_bias"  # 机构偏好
    JOURNAL_BIAS = "journal_bias"         # 期刊偏好
    METHODOLOGY_BIAS = "methodology_bias" # 方法论偏好
    ORDER_EFFECT = "order_effect"         # 顺序效应
    FATIGUE = "fatigue"                   # 疲劳效应
    ANCHORING = "anchoring"              # 锚定效应
    LENIENCY = "leniency"                # 宽松偏见
    STRINGENCY = "stringency"            # 严格偏见
    CENTRAL_TENDENCY = "central_tendency" # 趋中偏见


@dataclass
class CalibrationResult:
    """校准结果。"""
    original_score: float
    calibrated_score: float
    bias_correction: float
    calibration_method: str           # "ground_truth" / "distribution" / "standardization"
    confidence: float                 # 0-1
    details: dict = field(default_factory=dict)


@dataclass
class BiasInstance:
    """偏见实例。"""
    bias_type: BiasType
    severity: float                  # 0-1
    description: str
    affected_dimensions: list[str]
    statistical_evidence: dict
    recommendation: str


@dataclass
class BiasReport:
    """偏见检测报告。"""
    total_reviews: int
    detected_biases: list[BiasInstance]
    overall_bias_score: float         # 0-1 (越高偏见越严重)
    is_calibration_needed: bool
    bias_patterns: dict              # 偏见模式统计
    review_history_summary: dict


@dataclass
class CalibrationReport:
    """完整校准报告。"""
    review_id: str
    timestamp: float
    calibration_method: str
    ground_truth_score: float | None
    original_overall_score: float
    calibrated_overall_score: float
    dimension_calibrations: dict[str, CalibrationResult]
    bias_report: BiasReport | None
    is_reliable: bool
    confidence: float
    recommendations: list[str]


# ─── Ground Truth 数据 ─────────────────────────────────────────────────────

# 已发表论文的黄金标准评分（用于校准）
# 格式：{paper_id: {"dimensions": {dim: score}, "overall": score, "verdict": "accept/reject"}}
GROUND_TRUTH_DATASET: dict[str, dict] = {
    # 示例：JF 顶刊论文（已知评分）
    "jf_example_001": {
        "dimensions": {
            "theory": 9.0, "methodology": 9.5, "novelty": 8.5,
            "writing": 8.0, "relevance": 9.0, "reproducibility": 7.5,
        },
        "overall": 8.6,
        "verdict": "accept",
        "journal": "JF",
        "year": 2023,
    },
    "jfe_example_001": {
        "dimensions": {
            "theory": 8.5, "methodology": 9.0, "novelty": 8.0,
            "writing": 7.5, "relevance": 8.5, "reproducibility": 8.0,
        },
        "overall": 8.3,
        "verdict": "accept",
        "journal": "JFE",
        "year": 2023,
    },
}


# ─── Reviewer 校准器 ─────────────────────────────────────────────────────────

class ReviewerCalibrator:
    """
    Reviewer 评分校准器。

    功能：
    1. Ground Truth 校准：与已知标准评分对比
    2. 评分分布校准：使评分符合统计标准分布
    3. 跨期刊标准化：不同期刊标准 → 统一尺度
    4. 偏见探测：识别系统性评分偏见

    Usage:
        calibrator = ReviewerCalibrator(reviewer=DualReviewer(...))

        # 校准一份报告
        result = calibrator.calibrate_review(report, method="ground_truth")

        # 探测偏见
        bias_report = calibrator.detect_biases(review_history)
    """

    # 偏见探测的统计阈值
    FATIGUE_THRESHOLD = 0.3       # 评分下降超过30% → 疲劳效应
    ORDER_EFFECT_THRESHOLD = 0.5  # 首尾维度差异超过0.5 → 顺序效应
    CENTRAL_TENDENCY_SD = 0.5     # 评分标准差小于0.5 → 趋中偏见

    def __init__(
        self,
        reviewer=None,
        ground_truth_dataset: dict[str, dict] | None = None,
        journal_baselines: dict[str, dict] | None = None,
    ):
        self.reviewer = reviewer
        self.ground_truth_dataset = ground_truth_dataset or GROUND_TRUTH_DATASET

        # 期刊基准评分（各维度平均值）
        self.journal_baselines = journal_baselines or {
            "JF": {
                "theory": 7.5, "methodology": 7.5, "novelty": 7.5,
                "writing": 7.5, "relevance": 7.5, "reproducibility": 7.0,
                "overall": 7.5,
            },
            "JFE": {
                "theory": 7.8, "methodology": 8.0, "novelty": 7.5,
                "writing": 7.5, "relevance": 7.8, "reproducibility": 7.5,
                "overall": 7.7,
            },
            "RFS": {
                "theory": 8.0, "methodology": 8.0, "novelty": 8.0,
                "writing": 7.8, "relevance": 8.0, "reproducibility": 8.0,
                "overall": 8.0,
            },
            "JME": {
                "theory": 7.8, "methodology": 7.5, "novelty": 7.5,
                "writing": 7.5, "relevance": 7.8, "reproducibility": 7.0,
                "overall": 7.6,
            },
            # 中文顶刊
            "经济研究": {
                "theory": 8.0, "methodology": 7.5, "novelty": 7.5,
                "writing": 7.5, "relevance": 8.5, "reproducibility": 6.5,
                "overall": 7.6,
            },
            "金融研究": {
                "theory": 7.8, "methodology": 7.8, "novelty": 7.5,
                "writing": 7.5, "relevance": 8.0, "reproducibility": 7.0,
                "overall": 7.6,
            },
            "管理世界": {
                "theory": 7.5, "methodology": 7.0, "novelty": 7.0,
                "writing": 7.5, "relevance": 8.0, "reproducibility": 6.5,
                "overall": 7.3,
            },
        }

        # 校准历史（用于偏见探测）
        self._review_history: list[dict] = []
        self._calibration_cache: dict[str, CalibrationResult] = {}

    def add_to_history(self, review_data: dict):
        """将 review 数据加入历史，用于偏见分析。"""
        self._review_history.append({
            "timestamp": time.time(),
            "review": review_data,
        })

    # ── 量化校准 ──────────────────────────────────────────────────────────

    def calibrate_review(
        self,
        review_report: dict,
        method: str = "distribution",
        ground_truth_id: str | None = None,
        target_journal: str | None = None,
    ) -> CalibrationReport:
        """
        对一份 review 报告进行校准。

        Args:
            review_report: DualReviewer 输出的 report dict
            method: 校准方法
                - "ground_truth": 使用已知标准评分校准
                - "distribution": 使用统计分布校准
                - "standardization": 跨期刊标准化
            ground_truth_id: 已知标准的论文ID
            target_journal: 目标期刊（用于跨期刊标准化）

        Returns:
            CalibrationReport
        """
        review_id = review_report.get("review_id", f"review_{int(time.time())}")

        if method == "ground_truth" and ground_truth_id:
            return self._calibrate_ground_truth(review_report, ground_truth_id)
        elif method == "standardization" and target_journal:
            return self._calibrate_standardization(review_report, target_journal)
        else:
            return self._calibrate_distribution(review_report)

    def _calibrate_ground_truth(
        self, review_report: dict, gt_id: str,
    ) -> CalibrationReport:
        """使用 ground truth 校准。"""
        gt = self.ground_truth_dataset.get(gt_id)
        if not gt:
            return self._calibrate_distribution(review_report)

        dim_scores = review_report.get("dimension_scores", {})
        gt_dims = gt.get("dimensions", {})

        dim_calibrations = {}
        calibrated_scores = []
        total_correction = 0.0

        for dim, score in dim_scores.items():
            if dim in gt_dims:
                correction = gt_dims[dim] - score
                calibrated = score + correction * 0.5  # 软校准（不全纠）
                dim_calibrations[dim] = CalibrationResult(
                    original_score=score,
                    calibrated_score=calibrated,
                    bias_correction=correction,
                    calibration_method="ground_truth",
                    confidence=0.8,
                    details={"ground_truth": gt_dims[dim], "gt_paper": gt_id},
                )
                calibrated_scores.append(calibrated)
                total_correction += abs(correction)

        # 整体校准
        original_overall = review_report.get("overall_score", 0)
        gt_overall = gt.get("overall", original_overall)
        overall_correction = gt_overall - original_overall
        calibrated_overall = original_overall + overall_correction * 0.5

        return CalibrationReport(
            review_id=review_report.get("review_id", "unknown"),
            timestamp=time.time(),
            calibration_method="ground_truth",
            ground_truth_score=gt_overall,
            original_overall_score=original_overall,
            calibrated_overall_score=calibrated_overall,
            dimension_calibrations=dim_calibrations,
            bias_report=None,
            is_reliable=total_correction < 2.0,
            confidence=0.8 if gt else 0.3,
            recommendations=self._generate_calibration_recommendations(
                dim_calibrations, total_correction,
            ),
        )

    def _calibrate_distribution(self, review_report: dict) -> CalibrationReport:
        """使用评分分布统计校准（中心化 + 标准化）。"""
        dim_scores = review_report.get("dimension_scores", {})
        if not dim_scores:
            return self._empty_calibration_report(review_report, "distribution")

        scores = list(dim_scores.values())
        mean_score = statistics.mean(scores)
        sd_score = statistics.stdev(scores) if len(scores) > 1 else 1.0

        # 检测趋中偏见
        if sd_score < self.CENTRAL_TENDENCY_SD:
            logger.info("[Calibrator] Central tendency bias detected (sd=%.2f)", sd_score)

        dim_calibrations = {}
        calibrated_scores = []

        target_mean = 7.0
        target_sd = 1.2

        for dim, score in dim_scores.items():
            # Z-score → 新分布
            if sd_score > 0.01:
                z = (score - mean_score) / sd_score
                calibrated = target_mean + z * target_sd
                calibrated = max(1.0, min(10.0, calibrated))
            else:
                calibrated = score

            correction = calibrated - score
            dim_calibrations[dim] = CalibrationResult(
                original_score=score,
                calibrated_score=calibrated,
                bias_correction=correction,
                calibration_method="distribution",
                confidence=0.6,
                details={"z_score": (score - mean_score) / sd_score if sd_score > 0.01 else 0},
            )
            calibrated_scores.append(calibrated)

        original_overall = review_report.get("overall_score", mean_score)
        calibrated_overall = statistics.mean(calibrated_scores)

        return CalibrationReport(
            review_id=review_report.get("review_id", "unknown"),
            timestamp=time.time(),
            calibration_method="distribution",
            ground_truth_score=None,
            original_overall_score=original_overall,
            calibrated_overall_score=calibrated_overall,
            dimension_calibrations=dim_calibrations,
            bias_report=None,
            is_reliable=True,
            confidence=0.6,
            recommendations=self._generate_distribution_recommendations(sd_score, mean_score),
        )

    def _calibrate_standardization(
        self, review_report: dict, target_journal: str,
    ) -> CalibrationReport:
        """跨期刊标准化。"""
        baseline = self.journal_baselines.get(target_journal, self.journal_baselines["JF"])
        dim_scores = review_report.get("dimension_scores", {})

        dim_calibrations = {}
        calibrated_scores = []

        for dim, score in dim_scores.items():
            if dim in baseline:
                bl_score = baseline[dim]
                correction = bl_score - 7.5  # 基准线为7.5
                calibrated = score + correction * 0.3
                calibrated = max(1.0, min(10.0, calibrated))
            else:
                calibrated = score

            dim_calibrations[dim] = CalibrationResult(
                original_score=score,
                calibrated_score=calibrated,
                bias_correction=calibrated - score,
                calibration_method=f"standardization_{target_journal}",
                confidence=0.7,
                details={"target_journal": target_journal, "baseline": baseline.get(dim)},
            )
            calibrated_scores.append(calibrated)

        original_overall = review_report.get("overall_score", 7.5)
        calibrated_overall = statistics.mean(calibrated_scores)

        return CalibrationReport(
            review_id=review_report.get("review_id", "unknown"),
            timestamp=time.time(),
            calibration_method=f"standardization_{target_journal}",
            ground_truth_score=None,
            original_overall_score=original_overall,
            calibrated_overall_score=calibrated_overall,
            dimension_calibrations=dim_calibrations,
            bias_report=None,
            is_reliable=True,
            confidence=0.7,
            recommendations=[f"Scores standardized to {target_journal} baseline"],
        )

    def _empty_calibration_report(self, review_report: dict, method: str) -> CalibrationReport:
        return CalibrationReport(
            review_id=review_report.get("review_id", "unknown"),
            timestamp=time.time(),
            calibration_method=method,
            ground_truth_score=None,
            original_overall_score=review_report.get("overall_score", 0),
            calibrated_overall_score=review_report.get("overall_score", 0),
            dimension_calibrations={},
            bias_report=None,
            is_reliable=False,
            confidence=0.0,
            recommendations=["No dimension scores available for calibration"],
        )

    # ── 偏见探测 ─────────────────────────────────────────────────────────

    def detect_biases(
        self,
        review_history: list[dict] | None = None,
    ) -> BiasReport:
        """
        从历史评分中探测系统性偏见。

        Args:
            review_history: 评分历史（默认使用内部累积的历史）

        Returns:
            BiasReport
        """
        history = review_history or self._review_history
        if not history:
            return BiasReport(
                total_reviews=0,
                detected_biases=[],
                overall_bias_score=0.0,
                is_calibration_needed=False,
                bias_patterns={},
                review_history_summary={},
            )

        detected: list[BiasInstance] = []
        bias_scores: dict[BiasType, float] = {}

        # 1. 顺序效应检测
        order_bias = self._detect_order_effect(history)
        if order_bias:
            detected.append(order_bias)
            bias_scores[BiasType.ORDER_EFFECT] = order_bias.severity

        # 2. 疲劳效应检测
        fatigue_bias = self._detect_fatigue_effect(history)
        if fatigue_bias:
            detected.append(fatigue_bias)
            bias_scores[BiasType.FATIGUE] = fatigue_bias.severity

        # 3. 趋中偏见检测
        central_bias = self._detect_central_tendency(history)
        if central_bias:
            detected.append(central_bias)
            bias_scores[BiasType.CENTRAL_TENDENCY] = central_bias.severity

        # 4. 宽松/严格偏见检测
        severity_bias = self._detect_severity_bias(history)
        if severity_bias:
            detected.append(severity_bias)
            bias_scores[severity_bias.bias_type] = severity_bias.severity

        # 5. 方法论偏见检测
        method_bias = self._detect_methodology_bias(history)
        if method_bias:
            detected.append(method_bias)
            bias_scores[BiasType.METHODOLOGY_BIAS] = method_bias.severity

        # 总体偏见分数
        overall_score = statistics.mean(bias_scores.values()) if bias_scores else 0.0

        # 偏见模式统计
        patterns = {
            "total_reviews": len(history),
            "bias_types_detected": [b.value for b in bias_scores],
            "avg_severity": overall_score,
        }

        return BiasReport(
            total_reviews=len(history),
            detected_biases=detected,
            overall_bias_score=overall_score,
            is_calibration_needed=overall_score > 0.3,
            bias_patterns=patterns,
            review_history_summary=self._summarize_history(history),
        )

    def _detect_order_effect(self, history: list[dict]) -> BiasInstance | None:
        """检测顺序效应：先评分的维度分数偏高。"""
        first_dim_scores: list[float] = []
        last_dim_scores: list[float] = []

        for entry in history:
            dims = entry.get("review", {}).get("dimension_scores", {})
            if not dims:
                continue
            sorted_dims = list(dims.items())
            if len(sorted_dims) >= 2:
                first_dim_scores.append(sorted_dims[0][1])
                last_dim_scores.append(sorted_dims[-1][1])

        if len(first_dim_scores) < 3:
            return None

        avg_first = statistics.mean(first_dim_scores)
        avg_last = statistics.mean(last_dim_scores)
        diff = avg_first - avg_last

        if abs(diff) > self.ORDER_EFFECT_THRESHOLD:
            return BiasInstance(
                bias_type=BiasType.ORDER_EFFECT,
                severity=min(abs(diff) / 1.0, 1.0),
                description=f"First dimension scores avg={avg_first:.2f}, "
                            f"last dimension avg={avg_last:.2f}, diff={diff:.2f}",
                affected_dimensions=["first_dimension", "last_dimension"],
                statistical_evidence={"avg_first": avg_first, "avg_last": avg_last, "diff": diff},
                recommendation="Randomize the order of dimension evaluations",
            )
        return None

    def _detect_fatigue_effect(self, history: list[dict]) -> BiasInstance | None:
        """检测疲劳效应：随评分数量增加分数趋于下降。"""
        if len(history) < 5:
            return None

        early_scores = []
        late_scores = []

        for i, entry in enumerate(history):
            dims = entry.get("review", {}).get("dimension_scores", {})
            if dims:
                avg = statistics.mean(dims.values())
                if i < len(history) // 2:
                    early_scores.append(avg)
                else:
                    late_scores.append(avg)

        if len(early_scores) < 2 or len(late_scores) < 2:
            return None

        early_mean = statistics.mean(early_scores)
        late_mean = statistics.mean(late_scores)
        drop_ratio = (early_mean - late_mean) / early_mean if early_mean > 0 else 0

        if drop_ratio > self.FATIGUE_THRESHOLD:
            return BiasInstance(
                bias_type=BiasType.FATIGUE,
                severity=min(drop_ratio, 1.0),
                description=f"Scores drop by {drop_ratio:.1%} over review session. "
                            f"Early avg={early_mean:.2f}, late avg={late_mean:.2f}",
                affected_dimensions=["all_late_dimensions"],
                statistical_evidence={"early_mean": early_mean, "late_mean": late_mean, "drop_ratio": drop_ratio},
                recommendation="Take breaks during long review sessions; limit reviews per session",
            )
        return None

    def _detect_central_tendency(self, history: list[dict]) -> BiasInstance | None:
        """检测趋中偏见：评分标准差过小。"""
        all_sds = []
        for entry in history:
            dims = entry.get("review", {}).get("dimension_scores", {})
            if dims and len(dims) > 1:
                sd = statistics.stdev(dims.values())
                all_sds.append(sd)

        if not all_sds:
            return None

        avg_sd = statistics.mean(all_sds)
        if avg_sd < self.CENTRAL_TENDENCY_SD:
            return BiasInstance(
                bias_type=BiasType.CENTRAL_TENDENCY,
                severity=1.0 - (avg_sd / self.CENTRAL_TENDENCY_SD),
                description=f"Reviewer shows central tendency bias. Average SD={avg_sd:.2f} "
                            f"(threshold={self.CENTRAL_TENDENCY_SD})",
                affected_dimensions=["all_dimensions"],
                statistical_evidence={"avg_sd": avg_sd, "threshold": self.CENTRAL_TENDENCY_SD},
                recommendation="Use more extreme scores when warranted; force differentiation",
            )
        return None

    def _detect_severity_bias(self, history: list[dict]) -> BiasInstance | None:
        """检测宽松/严格偏见：评分系统性偏高或偏低。"""
        all_means = []
        for entry in history:
            dims = entry.get("review", {}).get("dimension_scores", {})
            if dims:
                all_means.append(statistics.mean(dims.values()))

        if len(all_means) < 3:
            return None

        overall_mean = statistics.mean(all_means)

        if overall_mean > 8.5:
            return BiasInstance(
                bias_type=BiasType.LENIENCY,
                severity=min((overall_mean - 7.5) / 2.5, 1.0),
                description=f"Reviewer is lenient: average score={overall_mean:.2f} (expected ~7.5)",
                affected_dimensions=["all_dimensions"],
                statistical_evidence={"overall_mean": overall_mean, "expected": 7.5},
                recommendation="Apply stricter standards; not all papers are excellent",
            )
        elif overall_mean < 5.5:
            return BiasInstance(
                bias_type=BiasType.STRINGENCY,
                severity=min((7.5 - overall_mean) / 2.0, 1.0),
                description=f"Reviewer is overly stringent: average score={overall_mean:.2f}",
                affected_dimensions=["all_dimensions"],
                statistical_evidence={"overall_mean": overall_mean, "expected": 7.5},
                recommendation="Be more open to incremental contributions; not all weaknesses are fatal",
            )
        return None

    def _detect_methodology_bias(self, history: list[dict]) -> BiasInstance | None:
        """检测方法论偏好偏见。"""
        method_scores: dict[str, list[float]] = {}

        for entry in history:
            review = entry.get("review", {})
            method = review.get("metadata", {}).get("methodology", "unknown")
            dims = review.get("dimension_scores", {})
            if dims and method != "unknown":
                if method not in method_scores:
                    method_scores[method] = []
                method_scores[method].append(statistics.mean(dims.values()))

        if len(method_scores) < 2:
            return None

        method_means = {m: statistics.mean(scores) for m, scores in method_scores.items()}
        max_diff = max(method_means.values()) - min(method_means.values())

        if max_diff > 1.5:
            fav = max(method_means, key=method_means.get)
            unfav = min(method_means, key=method_means.get)
            return BiasInstance(
                bias_type=BiasType.METHODOLOGY_BIAS,
                severity=min(max_diff / 3.0, 1.0),
                description=f"Methodology preference bias: '{fav}' avg={method_means[fav]:.2f} "
                            f"vs '{unfav}' avg={method_means[unfav]:.2f}",
                affected_dimensions=["methodology", "overall"],
                statistical_evidence=method_means,
                recommendation="Evaluate methodologies on their appropriateness for the research question, not personal preference",
            )
        return None

    # ── 辅助 ─────────────────────────────────────────────────────────────

    def _generate_calibration_recommendations(
        self, dim_calibrations: dict, total_correction: float,
    ) -> list[str]:
        recs = []
        if total_correction > 3.0:
            recs.append("Significant deviation from ground truth; reviewer's scores may be unreliable")
        if total_correction > 1.5:
            recs.append("Moderate calibration recommended; check for systematic biases")
        for dim, cal in dim_calibrations.items():
            if abs(cal.bias_correction) > 1.5:
                recs.append(f"Dimension '{dim}' shows large deviation ({cal.bias_correction:.1f}); "
                             "reviewer may have systematic bias here")
        if not recs:
            recs.append("Reviewer scores are well-calibrated")
        return recs

    def _generate_distribution_recommendations(self, sd: float, mean: float) -> list[str]:
        recs = []
        if sd < 0.5:
            recs.append("Detected central tendency: use more varied scores")
        if abs(mean - 7.0) > 1.5:
            recs.append(f"Score mean ({mean:.1f}) is far from expected (7.0); calibrate scores")
        if not recs:
            recs.append("Score distribution is reasonable")
        return recs

    def _summarize_history(self, history: list[dict]) -> dict:
        all_dims: list[float] = []
        all_overalls: list[float] = []
        journals: set[str] = set()

        for entry in history:
            dims = entry.get("review", {}).get("dimension_scores", {})
            all_dims.extend(dims.values())
            overall = entry.get("review", {}).get("overall_score")
            if overall:
                all_overalls.append(overall)
            journal = entry.get("review", {}).get("metadata", {}).get("journal")
            if journal:
                journals.add(journal)

        return {
            "total_reviews": len(history),
            "avg_dimension_score": statistics.mean(all_dims) if all_dims else 0,
            "avg_overall_score": statistics.mean(all_overalls) if all_overalls else 0,
            "score_range": (min(all_dims) if all_dims else 0, max(all_dims) if all_dims else 0),
            "journals_reviewed": list(journals),
        }

    def calibrate_with_ground_truth(
        self,
        review_report: dict,
        ground_truth_id: str,
    ) -> CalibrationReport:
        """便捷方法：使用 ground truth 校准。"""
        return self.calibrate_review(
            review_report,
            method="ground_truth",
            ground_truth_id=ground_truth_id,
        )
