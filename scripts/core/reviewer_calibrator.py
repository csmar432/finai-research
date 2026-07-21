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

import logging
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "ReviewerCalibrator",
    "CalibratorFeedbackLoop",
    "BiasHistoryDB",
    "PersistentCalibratorFeedbackLoop",
    "BiasType",
    "BiasInstance",
    "BiasReport",
    "CalibrationResult",
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
        review_report.get("review_id", f"review_{int(time.time())}")

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


# ═══════════════════════════════════════════════════════════════════════════════
# 自动反馈环：偏见 → Prompt 调整
# ═══════════════════════════════════════════════════════════════════════════════


class CalibratorFeedbackLoop:
    """
    Reviewer 偏见反馈闭环。

    将偏见探测结果自动转化为 LLM prompt 调整指令，
    形成「探测偏见 → 调整评分 → 验证效果」的闭环。

    解决的问题（PROJECT_EVALUATION.md 指出）：
    - Review 评分标准（REVIEWER_DIFFICULTY）为人工设置，无自动校准反馈

    Usage:
        loop = CalibratorFeedbackLoop(calibrator=ReviewerCalibrator())
        feedback = loop.generate_prompt_adjustments(bias_report)
        adjusted_reviewer = loop.apply_feedback(reviewer, feedback)
        result = loop.verify_adjustment(adjusted_reviewer, bias_report)
    """

    def __init__(self, calibrator: ReviewerCalibrator):
        self.calibrator = calibrator

    # ── 偏见 → Prompt 调整映射 ──────────────────────────────────────────────

    BIAS_PROMPT_RULES: dict[BiasType, dict] = {
        BiasType.ORDER_EFFECT: {
            "severity_tag": "order_effect",
            "prompt_adjustment": (
                "评分时请从最后一个维度开始，逐步向前评分。"
                "避免先入为主的印象影响后续评分。"
                "每个维度独立评分，不要参考其他维度的分数。"
            ),
            "score_correction": "reorder",  # 重排维度顺序
        },
        BiasType.FATIGUE: {
            "severity_tag": "fatigue",
            "prompt_adjustment": (
                "评分时请保持注意力集中。"
                "对论文后半部分的评价标准应与前半部分相同。 "
                "如果感到疲劳，建议分段休息后继续评分。"
            ),
            "score_correction": "uplift_late",
        },
        BiasType.CENTRAL_TENDENCY: {
            "severity_tag": "central_tendency",
            "prompt_adjustment": (
                "请使用更宽的评分范围：高质量论文给 8-10 分，"
                "一般论文给 4-6 分，低质量论文给 1-3 分。"
                "避免给所有论文都打 6-7 分的中等分数。"
            ),
            "score_correction": "spread_out",
        },
        BiasType.LENIENCY: {
            "severity_tag": "leniency",
            "prompt_adjustment": (
                "请严格评分。高质量论文才能获得 8 分以上。"
                "平庸或存在方法论问题的论文不应超过 6 分。"
                "接受标准应与 JF/JFE 等顶刊的实际标准对齐。"
            ),
            "score_correction": "downscale",
        },
        BiasType.STRINGENCY: {
            "severity_tag": "stringency",
            "prompt_adjustment": (
                "请适度宽松评分。如果论文方法正确、主要结论可靠，"
                "就给 7-8 分。只有存在严重问题才给 3 分以下。"
                "避免对所有论文都过于苛刻。"
            ),
            "score_correction": "upscale",
        },
        BiasType.METHODOLOGY_BIAS: {
            "severity_tag": "methodology_bias",
            "prompt_adjustment": (
                "评分时对不同方法论保持中立。"
                "无论论文使用 DID/IV/RCT/实验/理论/机器学习，"
                "只要方法合理、结论可靠，就应获得公平评分。"
            ),
            "score_correction": "neutralize",
        },
    }

    def generate_prompt_adjustments(
        self,
        bias_report: BiasReport,
    ) -> list[dict]:
        """
        根据偏见报告生成 LLM prompt 调整指令。

        Returns:
            list of adjustment dicts with keys:
              - bias_type: BiasType
              - severity: float (0-1)
              - adjustment: str (prompt text)
              - correction_method: str
        """
        adjustments = []
        for bias in bias_report.detected_biases:
            rule = self.BIAS_PROMPT_RULES.get(bias.bias_type)
            if not rule:
                continue
            # 只对中等及以上严重程度的偏见生成调整
            if bias.severity >= 0.3:
                adjustments.append({
                    "bias_type": bias.bias_type.value,
                    "severity": bias.severity,
                    "severity_tag": rule["severity_tag"],
                    "prompt_adjustment": rule["prompt_adjustment"],
                    "correction_method": rule["score_correction"],
                    "description": bias.description,
                })
        return adjustments

    def build_adjusted_system_prompt(
        self,
        adjustments: list[dict],
        base_prompt: str = "",
    ) -> str:
        """将偏见调整合并为一个增强的 system prompt。"""
        if not adjustments:
            return base_prompt

        sections = [
            "# 评分注意事项（基于偏见探测的自动调整）",
            "",
        ]
        for adj in adjustments:
            sections.append(
                f"## {adj['severity_tag'].upper()}（严重度 {adj['severity']:.0%}）"
            )
            sections.append(adj["prompt_adjustment"])
            sections.append("")

        return (
            (base_prompt + "\n\n" if base_prompt else "")
            + "\n".join(sections)
        )

    def apply_score_corrections(
        self,
        original_scores: dict[str, float],
        correction_method: str,
        severity: float,
    ) -> dict[str, float]:
        """对原始评分应用偏见修正（severity 控制修正强度）。"""
        corrected = dict(original_scores)
        strength = min(severity, 1.0)  # 上限1.0

        if correction_method == "downscale":
            # 宽松偏见：分数偏高，向下调整
            factor = 1.0 - strength * 0.15
            for k in corrected:
                corrected[k] = round(corrected[k] * factor, 2)

        elif correction_method == "upscale":
            # 严格偏见：分数偏低，向上调整
            factor = 1.0 + strength * 0.15
            for k in corrected:
                corrected[k] = min(10.0, round(corrected[k] * factor, 2))

        elif correction_method == "spread_out":
            # 趋中偏见：扩大分数分布
            mean = sum(corrected.values()) / len(corrected) if corrected else 7.0
            for k in corrected:
                delta = corrected[k] - mean
                corrected[k] = round(mean + delta * (1 + strength * 0.5), 2)

        elif correction_method == "reorder":
            # 顺序偏见：不再重排分数，只是标记（分数不变）
            pass

        elif correction_method == "neutralize":
            # 方法论偏见：中性化（不对分数本身调整，由 prompt 提示）
            pass

        # 确保所有分数在 [1, 10] 范围内
        for k in corrected:
            corrected[k] = max(1.0, min(10.0, corrected[k]))

        return corrected

    def verify_adjustment(
        self,
        adjusted_bias_report: BiasReport,
        original_bias_report: BiasReport,
    ) -> dict:
        """验证偏见修正效果：对比修正前后的偏见严重度。"""
        orig_map = {b.bias_type: b.severity for b in original_bias_report.detected_biases}
        adj_map = {b.bias_type: b.severity for b in adjusted_bias_report.detected_biases}

        improvements = {}
        for bt, orig_sev in orig_map.items():
            adj_sev = adj_map.get(bt, 0.0)
            delta = orig_sev - adj_sev
            improvements[bt.value] = {
                "original_severity": orig_sev,
                "adjusted_severity": adj_sev,
                "improvement": delta,
                "status": (
                    "✅ FIXED" if adj_sev < 0.2
                    else "⚠️ PARTIAL" if delta > 0.1
                    else "❌ NO CHANGE"
                ),
            }
        return improvements

    def run_full_loop(
        self,
        reviewer_scores: dict[str, float],
        bias_report: BiasReport,
        original_prompt: str = "",
    ) -> dict:
        """
        运行完整的反馈闭环。

        Returns:
            {
                "adjustments": [偏见的调整列表],
                "adjusted_prompt": 增强后的 system prompt,
                "corrected_scores": 修正后的评分,
                "verification": 修正效果验证结果,
            }
        """
        adjustments = self.generate_prompt_adjustments(bias_report)
        adjusted_prompt = self.build_adjusted_system_prompt(adjustments, original_prompt)

        # 应用分数修正
        corrected_scores = {}
        for adj in adjustments:
            correction = adj.get("correction_method", "none")
            if correction not in ("reorder", "neutralize"):
                corrected_scores = self.apply_score_corrections(
                    reviewer_scores, correction, adj["severity"]
                )
                reviewer_scores = corrected_scores

        return {
            "adjustments": adjustments,
            "adjusted_prompt": adjusted_prompt,
            "corrected_scores": corrected_scores,
            "verification": None,  # 需要重新运行偏见探测才能验证
        }


# ── 偏见报告 CLI ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ReviewerCalibrator 偏见探测工具")
    parser.add_argument("--bias-demo", action="store_true", help="演示偏见探测")
    parser.add_argument("--loop-demo", action="store_true", help="演示反馈环")
    args = parser.parse_args()

    if args.bias_demo:
        from scripts.core.reviewer import DualReviewer

        reviewer = DualReviewer()
        calibrator = ReviewerCalibrator(reviewer=reviewer)
        history = [
            {
                "review": {
                    "dimension_scores": {
                        "methodology": 7.0, "novelty": 8.0, "writing": 6.5,
                        "theory": 7.5, "reproducibility": 7.0,
                    },
                    "overall_score": 7.2,
                    "metadata": {"journal": "JF"},
                }
            },
        ]
        report = calibrator.detect_biases(history)
        print(f"\n偏见探测报告:")
        print(f"  检测到偏见数: {len(report.detected_biases)}")
        for b in report.detected_biases:
            print(f"  [{b.severity:.0%}] {b.bias_type.value}: {b.description}")

    if args.loop_demo:
        loop = CalibratorFeedbackLoop(calibrator=ReviewerCalibrator())
        # 构建模拟偏见报告
        bias = BiasInstance(
            bias_type=BiasType.CENTRAL_TENDENCY,
            severity=0.7,
            description="所有评分集中在 6-7 分",
            affected_dimensions=["all"],
            statistical_evidence={"score_range": 0.5, "std": 0.3},
            recommendation="建议使用更宽的评分范围",
        )
        report = BiasReport(
            total_reviews=1,
            detected_biases=[bias],
            overall_bias_score=0.7,
            is_calibration_needed=True,
            bias_patterns={},
            review_history_summary={},
        )
        adj = loop.generate_prompt_adjustments(report)
        print(f"\n反馈环生成 {len(adj)} 条调整:")
        for a in adj:
            print(f"  [{a['severity_tag']}] {a['prompt_adjustment'][:60]}...")


# ═══════════════════════════════════════════════════════════════════════════════
# 持久化与历史追踪：偏见历史数据库
# ═══════════════════════════════════════════════════════════════════════════════


class BiasHistoryDB:
    """
    偏见历史持久化存储。

    将每次偏见探测结果记录到 SQLite 数据库，支持：
    - 偏见趋势分析（随时间的严重度变化）
    - 期刊维度偏见对比
    - 跨评审者偏见模式对比
    - 自动导出 CSV/JSON

    Usage:
        db = BiasHistoryDB(db_path=".bias_history.db")
        db.record_review(review_id, journal, bias_report)
        trends = db.get_bias_trends(bias_type=BiasType.CENTRAL_TENDENCY)
        db.export_csv("bias_history.csv")
    """

    def __init__(self, db_path: str = ".bias_history.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bias_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                journal TEXT,
                bias_type TEXT NOT NULL,
                severity REAL NOT NULL,
                description TEXT,
                affected_dimensions TEXT,
                statistical_evidence TEXT,
                recommendation TEXT,
                overall_bias_score REAL,
                adjustment_applied INTEGER DEFAULT 0,
                adjustment_severity REAL,
                adjustment_method TEXT,
                UNIQUE(review_id, bias_type)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_metadata (
                review_id TEXT PRIMARY KEY,
                journal TEXT,
                reviewer_name TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paper_title TEXT,
                notes TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bias_type
            ON bias_records(bias_type, recorded_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_id
            ON bias_records(review_id)
        """)
        conn.commit()
        conn.close()

    def record_review(self, review_id: str, journal: str, bias_report: BiasReport,
                      metadata: dict | None = None) -> None:
        """记录一次偏见探测结果。"""
        import sqlite3, json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Record metadata
        meta = metadata or {}
        cursor.execute("""
            INSERT OR REPLACE INTO review_metadata
            (review_id, journal, reviewer_name, paper_title, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (
            review_id,
            journal,
            meta.get("reviewer_name", "unknown"),
            meta.get("paper_title", ""),
            meta.get("notes", ""),
        ))

        # Record each bias
        for bias in bias_report.detected_biases:
            cursor.execute("""
                INSERT OR REPLACE INTO bias_records
                (review_id, journal, bias_type, severity, description,
                 affected_dimensions, statistical_evidence, recommendation,
                 overall_bias_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review_id,
                journal,
                bias.bias_type.value,
                bias.severity,
                bias.description,
                json.dumps(bias.affected_dimensions),
                json.dumps(bias.statistical_evidence),
                bias.recommendation,
                bias_report.overall_bias_score,
            ))

        conn.commit()
        conn.close()

    def record_adjustment(self, review_id: str, bias_type: BiasType,
                          adjustment_severity: float, adjustment_method: str) -> None:
        """记录一次偏见调整的应用结果。"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE bias_records
            SET adjustment_applied = 1,
                adjustment_severity = ?,
                adjustment_method = ?
            WHERE review_id = ? AND bias_type = ?
        """, (adjustment_severity, adjustment_method, review_id, bias_type.value))
        conn.commit()
        conn.close()

    def get_bias_trends(self, bias_type: BiasType | None = None,
                        journal: str | None = None,
                        limit: int = 100) -> list[dict]:
        """获取偏见趋势数据。"""
        import sqlite3, json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT recorded_at, severity, journal, adjustment_applied FROM bias_records WHERE 1=1"
        params: list = []
        if bias_type:
            query += " AND bias_type = ?"
            params.append(bias_type.value)
        if journal:
            query += " AND journal = ?"
            params.append(journal)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [
            {"recorded_at": r[0], "severity": r[1], "journal": r[2], "adjusted": bool(r[3])}
            for r in rows
        ]

    def get_bias_summary(self) -> dict:
        """获取偏见汇总统计。"""
        import sqlite3, statistics
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT bias_type, COUNT(*), AVG(severity), MAX(severity), MIN(severity),
                   SUM(CASE WHEN adjustment_applied = 1 THEN 1 ELSE 0 END) as adjusted_count
            FROM bias_records
            GROUP BY bias_type
        """)
        rows = cursor.fetchall()
        conn.close()

        summary = {}
        for r in rows:
            bias_type_str, count, avg_sev, max_sev, min_sev, adj_count = r
            summary[bias_type_str] = {
                "count": count,
                "avg_severity": round(avg_sev, 3) if avg_sev else 0,
                "max_severity": max_sev or 0,
                "min_severity": min_sev or 0,
                "adjusted_count": adj_count or 0,
                "adjustment_rate": round((adj_count or 0) / count, 3) if count else 0,
            }
        return summary

    def export_csv(self, path: str) -> None:
        """导出偏见历史为 CSV。"""
        import sqlite3, csv
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.review_id, b.recorded_at, b.journal, b.bias_type, b.severity,
                   b.description, b.overall_bias_score, b.adjustment_applied,
                   b.adjustment_severity, b.adjustment_method, m.paper_title
            FROM bias_records b
            LEFT JOIN review_metadata m ON b.review_id = m.review_id
            ORDER BY b.recorded_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "review_id", "recorded_at", "journal", "bias_type", "severity",
                "description", "overall_bias_score", "adjustment_applied",
                "adjustment_severity", "adjustment_method", "paper_title"
            ])
            writer.writerows(rows)

    def export_json(self, path: str) -> None:
        """导出偏见历史为 JSON。"""
        import sqlite3, json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT review_id, journal, recorded_at, severity, bias_type, description, adjustment_applied FROM bias_records ORDER BY recorded_at DESC")
        rows = cursor.fetchall()
        conn.close()
        records = [
            {"review_id": r[0], "journal": r[1], "recorded_at": r[2],
             "severity": r[3], "bias_type": r[4], "description": r[5],
             "adjustment_applied": bool(r[6])}
            for r in rows
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"records": records, "summary": self.get_bias_summary()}, f, indent=2, ensure_ascii=False)


# ── 增强的反馈环：集成持久化 ───────────────────────────────────────────────────


class PersistentCalibratorFeedbackLoop(CalibratorFeedbackLoop):
    """
    带持久化功能的增强版 CalibratorFeedbackLoop。

    在 CalibratorFeedbackLoop 基础上添加：
    1. 偏见历史 SQLite 存储
    2. 自动调整建议生成（基于历史偏见模式）
    3. 期刊标准化偏见基准
    4. 趋势预警（偏见严重度上升趋势）
    5. 调整效果追踪

    Usage:
        loop = PersistentCalibratorFeedbackLoop(
            calibrator=ReviewerCalibrator(),
            db_path=".bias_history.db"
        )
        loop.run_full_loop_with_persistence(review_id, journal, bias_report)
    """

    def __init__(self, calibrator: ReviewerCalibrator,
                 db_path: str = ".bias_history.db"):
        super().__init__(calibrator)
        self.db = BiasHistoryDB(db_path)

    def auto_calibration_advice(self) -> list[str]:
        """
        基于历史偏见模式，生成自动校准建议。

        分析历史偏见数据，识别：
        - 最频繁出现的偏见类型
        - 调整后仍然存在的偏见
        - 需要改变评分标准的期刊
        """
        import statistics
        advice = []
        summary = self.db.get_bias_summary()

        if not summary:
            advice.append("偏见历史为空，建议先积累 5-10 条评审记录后再分析趋势。")
            return advice

        # 最严重的偏见类型
        sorted_by_severity = sorted(
            summary.items(), key=lambda x: x[1]["avg_severity"], reverse=True
        )
        if sorted_by_severity:
            top_type, top_stats = sorted_by_severity[0]
            if top_stats["avg_severity"] > 0.6:
                advice.append(
                    f"最严重的偏见类型：{top_type}（平均严重度 {top_stats['avg_severity']:.0%}），"
                    f"共出现 {top_stats['count']} 次，建议在 prompt 中加强该偏见类型的纠正指令。"
                )

        # 调整率低的偏见
        low_adjust_rate = [
            (bt, s) for bt, s in summary.items()
            if s["adjustment_rate"] < 0.5 and s["count"] >= 3
        ]
        if low_adjust_rate:
            advice.append(
                f"有 {len(low_adjust_rate)} 种偏见类型的调整率低于 50%，"
                "当前 prompt 调整策略可能不够有效，建议更换调整方法或加强 prompt 强度。"
            )

        # 总体偏见趋势
        trends = self.db.get_bias_trends(limit=20)
        if len(trends) >= 5:
            severities = [t["severity"] for t in trends[:5]]
            if len(severities) >= 3:
                first_half = statistics.mean(severities[:len(severities)//2])
                second_half = statistics.mean(severities[len(severities)//2:])
                if second_half > first_half * 1.2:
                    advice.append(
                        f"⚠️ 偏见严重度呈上升趋势（近期均值 {second_half:.0%} > 早期均值 {first_half:.0%}），"
                        "建议检查评审者是否出现疲劳或标准漂移。"
                    )

        if not advice:
            advice.append("偏见状态良好，当前校准策略运行正常。")
        return advice

    def run_full_loop_with_persistence(
        self,
        review_id: str,
        journal: str,
        bias_report: BiasReport,
        reviewer_scores: dict[str, float] | None = None,
        original_prompt: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """
        运行完整的反馈闭环并持久化结果。

        Returns:
            {
                "adjustments": [偏见的调整列表],
                "adjusted_prompt": 增强后的 system prompt,
                "corrected_scores": 修正后的评分,
                "auto_advice": [自动校准建议],
                "persistence": {"recorded": True, "adjustment_ids": [...]}
            }
        """
        # 记录原始偏见
        self.db.record_review(review_id, journal, bias_report, metadata)

        # 执行反馈环
        result = self.run_full_loop(
            reviewer_scores=reviewer_scores or {},
            bias_report=bias_report,
            original_prompt=original_prompt,
        )

        # 记录调整应用
        for adj in result.get("adjustments", []):
            bt = BiasType(adj["bias_type"])
            self.db.record_adjustment(
                review_id, bt,
                adj["severity"],
                adj["correction_method"],
            )

        # 生成自动校准建议
        result["auto_advice"] = self.auto_calibration_advice()
        result["persistence"] = {"recorded": True, "db_path": self.db.db_path}
        return result

    def journal_bias_profile(self, journal: str) -> dict:
        """生成特定期刊的偏见画像。"""
        import statistics
        trends = self.db.get_bias_trends(journal=journal, limit=100)
        if not trends:
            return {"journal": journal, "samples": 0, "message": "无数据"}

        severities = [t["severity"] for t in trends]
        [t.get("bias_type", "unknown") for t in trends
                      if "bias_type" in t]
        return {
            "journal": journal,
            "samples": len(trends),
            "avg_severity": round(statistics.mean(severities), 3),
            "max_severity": max(severities),
            "min_severity": min(severities),
            "adjusted_rate": round(sum(1 for t in trends if t.get("adjusted")) / len(trends), 3),
        }
