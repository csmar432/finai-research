"""LLM-based Academic Paper Reviewer — calibrated against human judgments.

Inspired by AI Scientist's Automated Reviewer (69% balanced accuracy).

Evaluates papers along 6 dimensions:
    1. Methodology Rigor (1-10)
    2. Novelty / Contribution (1-10)
    3. Clarity & Presentation (1-10)
    4. Reproducibility (1-10)
    5. Significance / Impact (1-10)
    6. Overall Recommendation (1-10)

Calibration:
    - Reviewer prompt matches real conference review forms
    - Supports calibration dataset for measuring balanced accuracy
    - Outputs structured JSON for programmatic analysis

Usage:
    reviewer = LLMReviewer()
    review = reviewer.review(paper_content=paper_text, venue="CVPR", language="en")
    print(f"Recommendation: {review.overall_recommendation}")
    print(f"Methodology: {review.scores['methodology_rigor'].score}/10")
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "LLMReviewer",
    "ReviewResult",
    "ReviewScore",
    "CalibrationResult",
    "CalibrationDataset",
    "VENUE_CONFIGS",
]

# ─── Venue Configurations ────────────────────────────────────────────────────


VENUE_CONFIGS: dict[str, dict[str, Any]] = {
    # ── ML/AI ──────────────────────────────────────────────────────────────
    "CVPR": {
        "name": "CVPR",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "Computer Vision",
        "focus": "novel methods, empirical evaluation",
        "language": "en",
    },
    "NeurIPS": {
        "name": "NeurIPS",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "Machine Learning",
        "focus": "theoretical depth, empirical rigor",
        "language": "en",
    },
    "ICLR": {
        "name": "ICLR",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "ML/AI",
        "focus": "clarity, significance, reproducibility",
        "language": "en",
    },
    "ACL": {
        "name": "ACL",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "NLP",
        "focus": "linguistic insight, empirical evaluation",
        "language": "en",
    },
    "EMNLP": {
        "name": "EMNLP",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "NLP",
        "focus": "empirical evidence, scientific rigor",
        "language": "en",
    },
    # ── Finance ──────────────────────────────────────────────────────────────
    "JFE": {
        "name": "Journal of Financial Economics",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "Finance",
        "focus": "economic intuition, identification strategy, robustness",
        "language": "en",
    },
    "RFS": {
        "name": "Review of Financial Studies",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "Finance",
        "focus": "theoretical contribution, identification, sample quality",
        "language": "en",
    },
    # ── Chinese / Chinese Economics ──────────────────────────────────────────
    "经济研究": {
        "name": "经济研究",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "经济学",
        "focus": "理论创新、识别策略、稳健性",
        "language": "zh",
    },
    "管理世界": {
        "name": "管理世界",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "管理学",
        "focus": "理论贡献、实践意义、方法规范",
        "language": "zh",
    },
    "金融研究": {
        "name": "金融研究",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "金融学",
        "focus": "实证规范、金融学贡献、稳健性检验",
        "language": "zh",
    },
    # ── Generic fallback ─────────────────────────────────────────────────────
    "ML": {
        "name": "Machine Learning",
        "threshold_accept": 7.0,
        "threshold_borderline": 5.0,
        "domain": "ML/AI",
        "focus": "novelty, rigor, reproducibility",
        "language": "en",
    },
}

# ─── Review Prompts ─────────────────────────────────────────────────────────


_REVIEWER_PROMPT_EN = """You are a {venue_name} program committee member reviewing paper #{paper_number}.

TASK: Provide a rigorous, fair, and constructive review.

PAPER TO REVIEW:
---
{paper_content}
---

SCORING INSTRUCTIONS:
Rate each dimension from 1 (very poor) to 10 (exceptional). Be critical but constructive.

DIMENSIONS:
1. Methodology Rigor (1-10): Are the methods technically sound? Correct? Appropriate for the research question? Is the identification strategy valid?
2. Novelty / Contribution (1-10): What is the original contribution? How much does it advance the field? Is it a genuine advance over prior work?
3. Clarity & Presentation (1-10): Is the paper well-written, well-organized, and easy to follow? Are figures and tables informative?
4. Reproducibility (1-10): Are sufficient details provided (code, data, hyperparameters) to reproduce the results?
5. Significance / Impact (1-10): How impactful are the findings for the {domain} community? Will it influence future research or practice?
6. Overall (1-10): Taking all factors into account, your overall recommendation score.

RECOMMENDATION THRESHOLDS:
- 9-10: Strong Accept (top 10% of submissions — publish as-is or minor fixes)
- 7-8: Accept (solid contribution, clearly above acceptance bar)
- 5-6: Borderline (interesting but needs significant revisions)
- 3-4: Reject (serious flaws or limited contribution)
- 1-2: Strong Reject (fundamentally flawed)

IMPORTANT GUIDELINES:
- Focus on the research quality, not surface-level writing issues
- Consider the expected bar for {venue_name}: {focus}
- Look for: sound methodology, genuine novelty, adequate experiments, proper baselines
- Check: Are claims supported by evidence? Are comparisons to baselines fair?
- DEDUCTION CRITERIA: missing ablation studies, unfair comparisons, unclear experiments,
  lack of statistical significance, missing robustness checks

OUTPUT FORMAT: Return ONLY a valid JSON object (no markdown, no explanation outside JSON):
{{
  "scores": {{
    "methodology_rigor": {{"score": 7.0, "confidence": 0.85, "reasoning": "1-2 sentences"}},
    "novelty": {{"score": 6.5, "confidence": 0.80, "reasoning": "1-2 sentences"}},
    "clarity": {{"score": 7.5, "confidence": 0.90, "reasoning": "1-2 sentences"}},
    "reproducibility": {{"score": 6.0, "confidence": 0.75, "reasoning": "1-2 sentences"}},
    "significance": {{"score": 7.0, "confidence": 0.82, "reasoning": "1-2 sentences"}},
    "overall": {{"score": 7.0, "confidence": 0.88, "reasoning": "1-2 sentences"}}
  }},
  "overall_recommendation": "Accept",
  "summary": "3-5 sentence summary of the paper's strengths and weaknesses",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
  "detailed_feedback": "Full review text, 2-3 paragraphs",
  "confidence": 0.85,
  "metadata": {{"venue": "{venue_name}", "paper_number": {paper_number}}}
}}
"""

_REVIEWER_PROMPT_ZH = """你是{venue_name}的程序委员会审稿人，审阅第 {paper_number} 篇论文。

任务：对论文进行严格、公正、建设性的评审。

待审评论文:
---
{paper_content}
---

评分标准（1-10分）:
1. 方法论严谨性 (1-10): 方法是否技术严谨？识别策略是否有效？
2. 创新性与贡献 (1-10): 原创贡献是什么？对领域有多大推进？
3. 表达清晰度 (1-10): 论文写作是否清晰、组织是否合理？
4. 可复现性 (1-10): 是否提供了足够细节（代码、数据、超参数）？
5. 学术意义与影响 (1-10): 研究发现对{domain}领域的意义？
6. 综合评分 (1-10): 综合所有因素的整体评分

推荐等级:
- 9-10: 强烈接收（top 10%）
- 7-8: 接收（明显超过接收标准）
- 5-6: 边缘（有趣但需要重大修改）
- 3-4: 拒绝（有严重缺陷或贡献有限）
- 1-2: 强烈拒绝（根本性缺陷）

输出格式（仅返回JSON，无其他内容）:
{{
  "scores": {{
    "methodology_rigor": {{"score": 7.0, "confidence": 0.85, "reasoning": "1-2句话说明"}},
    "novelty": {{"score": 6.5, "confidence": 0.80, "reasoning": "1-2句话说明"}},
    "clarity": {{"score": 7.5, "confidence": 0.90, "reasoning": "1-2句话说明"}},
    "reproducibility": {{"score": 6.0, "confidence": 0.75, "reasoning": "1-2句话说明"}},
    "significance": {{"score": 7.0, "confidence": 0.82, "reasoning": "1-2句话说明"}},
    "overall": {{"score": 7.0, "confidence": 0.88, "reasoning": "1-2句话说明"}}
  }},
  "overall_recommendation": "接收",
  "summary": "3-5句话总结论文的优缺点",
  "strengths": ["优点1", "优点2", "优点3"],
  "weaknesses": ["缺点1", "缺点2", "缺点3"],
  "detailed_feedback": "详细评审意见，2-3段",
  "confidence": 0.85,
  "metadata": {{"venue": "{venue_name}", "paper_number": {paper_number}, "language": "zh"}}
}}
"""

# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ReviewScore:
    score: float
    confidence: float
    reasoning: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewResult:
    scores: dict[str, ReviewScore]
    overall_score: float
    overall_recommendation: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    detailed_feedback: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scores": {k: v.to_dict() for k, v in self.scores.items()},
            "overall_score": self.overall_score,
            "overall_recommendation": self.overall_recommendation,
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "detailed_feedback": self.detailed_feedback,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_llm_response(cls, raw_text: str) -> ReviewResult:
        """Parse LLM's text output into structured ReviewResult."""
        # Try to extract JSON from the response
        raw_text = raw_text.strip()

        # Handle markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL)
        if json_match:
            raw_text = json_match.group(1)

        # Try to find JSON object (may have leading/trailing text)
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            raw_text = raw_text[json_start:json_end]

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to parse LLM review JSON: {exc}")
            # Return a fallback result
            return cls(
                scores={
                    k: ReviewScore(score=0.0, confidence=0.0, reasoning="Parse failed")
                    for k in ["methodology_rigor", "novelty", "clarity",
                              "reproducibility", "significance", "overall"]
                },
                overall_score=0.0,
                overall_recommendation="Unknown (parse failed)",
                summary=raw_text[:500],
                strengths=[],
                weaknesses=["Failed to parse LLM response as JSON"],
                detailed_feedback=raw_text,
                confidence=0.0,
                metadata={"parse_error": str(exc)},
            )

        # Parse scores
        parsed_scores = {}
        raw_scores = data.get("scores", {})
        for dim in ["methodology_rigor", "novelty", "clarity",
                    "reproducibility", "significance", "overall"]:
            s = raw_scores.get(dim, {})
            if isinstance(s, dict):
                parsed_scores[dim] = ReviewScore(
                    score=float(s.get("score", 0.0)),
                    confidence=float(s.get("confidence", 0.0)),
                    reasoning=str(s.get("reasoning", "")),
                )
            elif isinstance(s, (int, float)):
                parsed_scores[dim] = ReviewScore(
                    score=float(s), confidence=0.5, reasoning=""
                )
            else:
                parsed_scores[dim] = ReviewScore(
                    score=0.0, confidence=0.0, reasoning="Missing"
                )

        return cls(
            scores=parsed_scores,
            overall_score=float(data.get("overall_score", data.get("overall", {}).get("score", 0.0))),
            overall_recommendation=str(data.get("overall_recommendation", "Unknown")),
            summary=str(data.get("summary", "")),
            strengths=list(data.get("strengths", [])),
            weaknesses=list(data.get("weaknesses", [])),
            detailed_feedback=str(data.get("detailed_feedback", "")),
            confidence=float(data.get("confidence", 0.5)),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CalibrationResult:
    balanced_accuracy: float
    precision_per_class: dict[str, float]
    recall_per_class: dict[str, float]
    f1_per_class: dict[str, float]
    confusion_matrix: list[list[int]]
    dimension_correlation: dict[str, float]
    dataset_size: int
    dataset_source: str
    total_predictions: int = 0
    correct_predictions: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Balanced Accuracy: {self.balanced_accuracy:.1%} | "
            f"Predictions: {self.correct_predictions}/{self.total_predictions} | "
            f"Dataset: {self.dataset_source} ({self.dataset_size} papers)"
        )


# ─── Calibration Dataset ─────────────────────────────────────────────────────


class CalibrationDataset:
    """
    Predefined and custom calibration datasets, plus synthetic generation.

    Quality levels (mapped to expected scores):
        - strong_accept: overall ~9, methodology ~9, novelty ~8, clarity ~8
        - accept:        overall ~7, methodology ~7, novelty ~6, clarity ~7
        - weak_accept:   overall ~6, methodology ~6, novelty ~5, clarity ~6
        - borderline:    overall ~5, methodology ~5, novelty ~5, clarity ~5
        - reject:       overall ~3, methodology ~3, novelty ~3, clarity ~3

    The generate_* methods create paper text that clearly exhibits the
    characteristics of each quality level, allowing us to test whether
    the LLM reviewer correctly assigns scores/recommendations.
    """

    QUALITY_LEVELS = ["strong_accept", "accept", "weak_accept", "borderline", "reject"]
    DOMAINS = ["empirical", "finance", "ml"]

    # Minimal synthetic dataset for development/testing
    # In production, replace with real labeled data from OpenReview, journal archives
    SYNTHETIC_SAMPLES = [
        {
            "paper_content": (
                "We propose DeepTrade, a novel transformer architecture for stock prediction. "
                "We evaluate on 5 years of S&P 500 data. DeepTrade achieves 62% accuracy vs. "
                "the best prior method at 58%. We provide code and data. Limitations: only US markets."
            ),
            "human_verdict": "Accept",
            "expected_scores": {"methodology_rigor": 7, "novelty": 6, "overall": 7},
            "notes": "Solid empirical paper, decent baselines",
        },
        {
            "paper_content": (
                "We use GPT-4 to generate trading signals. Results are good. "
                "The paper is short. We don't compare to any baselines."
            ),
            "human_verdict": "Reject",
            "expected_scores": {"methodology_rigor": 2, "novelty": 3, "overall": 2},
            "notes": "No methodology, no baselines, no experiments",
        },
        {
            "paper_content": (
                "This paper proves that stock returns follow a power law distribution. "
                "We provide theoretical proofs and validate on 10 markets over 30 years. "
                "Code is provided. Related work is thoroughly discussed."
            ),
            "human_verdict": "Strong Accept",
            "expected_scores": {"methodology_rigor": 9, "novelty": 8, "overall": 9},
            "notes": "Strong theory + empirical validation",
        },
    ]

    KNOWN_DATASETS: dict[str, dict] = {
        "synthetic": {
            "description": "Synthetic papers with known quality variations (for development only)",
            "samples": SYNTHETIC_SAMPLES,
            "source": "Generated for calibration testing",
        },
    }

    def __init__(self, seed: int = 42):
        """Initialize with a random seed for reproducibility."""
        self.rng = np.random.default_rng(seed)

    # ── Synthetic paper generation ──────────────────────────────────────────

    def generate_paper(self, quality_level: str, domain: str = "empirical") -> dict:
        """
        Generate a synthetic paper with specific quality level and domain.

        Parameters
        ----------
        quality_level : str
            One of: strong_accept, accept, weak_accept, borderline, reject.
        domain : str
            One of: empirical, finance, ml.

        Returns
        -------
        dict
            Paper dict with keys: paper_id, quality_level, domain, text,
            expected_score, expected_recommendation.
        """
        quality_level = quality_level.lower()
        domain = domain.lower()

        if quality_level not in self.QUALITY_LEVELS:
            raise ValueError(f"Unknown quality_level: {quality_level}. "
                             f"Available: {self.QUALITY_LEVELS}")
        if domain not in self.DOMAINS:
            raise ValueError(f"Unknown domain: {domain}. Available: {self.DOMAINS}")

        if domain == "empirical":
            text = self._generate_empirical_paper(quality_level)
        elif domain == "finance":
            text = self._generate_finance_paper(quality_level)
        else:
            text = self._generate_ml_paper(quality_level)

        expected_score = self._quality_to_score(quality_level)
        expected_recommendation = self._quality_to_recommendation(quality_level)

        return {
            "paper_id": f"syn_{domain}_{quality_level}_{self.rng.integers(10000):04d}",
            "quality_level": quality_level,
            "domain": domain,
            "text": text,
            "expected_score": expected_score,
            "expected_recommendation": expected_recommendation,
        }

    def _generate_empirical_paper(self, quality_level: str) -> str:
        """Generate empirical paper text at given quality level."""
        base = "[SYNTHETIC PAPER — Empirical Economics] "

        if quality_level == "strong_accept":
            return base + """
We study the causal effect of environmental regulation on corporate innovation using China's
Emissions Trading Scheme (ETS). We hypothesize: H1: ETS positively affects green patents.
H2: Effects are heterogeneous by financial development. Identification relies on DID with
PSM matching. N=2,847 A-share listed firms (CSMAR + Chinese Patent Database, 2010-2022).
The treatment coefficient is 0.082*** (t=3.21), economically significant: a 1 SD increase
in ETS intensity increases green patents by 6.4%. Parallel trends are confirmed (F=1.23, p=0.287).
Robustness checks include IV estimation (historical SO2 as instrument, F=23.4), placebo tests
using pre-treatment years, alternative sample windows, and alternative outcome measures.
Heterogeneity: stronger effects in high financial development regions (z=2.15, p=0.032).
Mediation analysis confirms innovation investment as key channel (Sobel z=2.34, p=0.019).
We address endogeneity using instrumental variables. Limitations are clearly discussed:
causal interpretation depends on the parallel trends assumption. References include recent
top-journal papers (doi: 10.1257/jel.20191110, 10.1016/j.jfinec.2021.12.345).
Code and data appendix provided. Tables: Summary Statistics, Main Results, Robustness.
"""
        elif quality_level == "accept":
            return base + """
This paper examines how carbon trading affects firm green innovation using DID.
Data covers 2,500 Chinese listed firms 2010-2020. Treatment coefficient is 0.07** (t=2.8).
Parallel trends are satisfied. We use firm and year fixed effects with clustered standard errors.
Robustness checks include alternative specifications and placebo tests.
Results show positive effects especially in regions with better financial development.
Limitations are acknowledged. References cite major environmental economics journals.
"""
        elif quality_level == "weak_accept":
            return base + """
This paper examines carbon trading and innovation. Results show positive effects.
We use DID with firm fixed effects. N=2,000 firms. Coefficient is positive and significant.
Some robustness checks are included. Limitations are mentioned.
"""
        elif quality_level == "borderline":
            return base + """
This paper studies environmental policy and innovation. Results are positive.
We used DID. Data from some years. Some firms. Results are good.
"""
        else:  # reject
            return base + """
ETS drives innovation. The positive coefficient proves ETS causes innovation.
Results are important. We used DID. N=firms. R²=0.23. Good results.
"""

    def _generate_finance_paper(self, quality_level: str) -> str:
        """Generate finance paper text at given quality level."""
        base = "[SYNTHETIC PAPER — Finance] "

        if quality_level == "strong_accept":
            return base + """
We propose a novel DCF-LSTM hybrid model for stock return prediction combining discounted
cash flow fundamentals with LSTM deep learning. We evaluate on S&P 500 constituents
(2000-2024) with proper train/validation/test splits preventing look-ahead bias.
Our model achieves IC=0.048 (IR=0.85) vs. LightGBM (IC=0.039, IR=0.71) and LSTM (IC=0.041, IR=0.74).
Statistical significance confirmed via Newey-West standard errors (t=3.2, p<0.01).
Ablation study: removing DCF features reduces IC by 18% (0.048 -> 0.039).
Backtest: long-short portfolio earns 16.2% annualized return (Sharpe=1.4, max drawdown=12%).
Turnover analysis: 25% monthly average. Transaction costs of 10bp reduce Sharpe to 1.1.
Risk-adjusted outperformance is robust across market regimes (expansion vs. recession).
Code available at github.com/author/dcf-lstm with seed=42 for reproducibility.
Random seed set to 42. Results reported as mean +/- std across 10 independent runs.
References include recent JFQA and RFS papers with DOI.
"""
        elif quality_level == "accept":
            return base + """
We propose a hybrid model for stock prediction combining fundamental analysis and ML.
Tested on S&P 500 data 2010-2023. Model outperforms LightGBM baseline by 12%.
Backtest shows positive risk-adjusted returns. Some robustness checks included.
"""
        elif quality_level == "weak_accept":
            return base + """
We use deep learning for stock prediction. Results are positive.
Compared to a few baselines. Some experiments included.
"""
        elif quality_level == "borderline":
            return base + """
We predict stock returns with ML. Results are good. Compared to one baseline.
"""
        else:  # reject
            return base + """
We predict stocks with AI. Our method works well. Results are good.
"""

    def _generate_ml_paper(self, quality_level: str) -> str:
        """Generate ML paper text at given quality level."""
        base = "[SYNTHETIC PAPER — Machine Learning] "

        if quality_level == "strong_accept":
            return base + """
We propose HATT, a Hierarchical Attention Transformer for cross-sectional stock returns.
Attention is All You Need (Vaswani et al., 2017) provides the transformer foundation.
We compare against LightGBM, LSTM, MLP, and Ridge baselines. Our method achieves
IC=0.045 +/- 0.012 and IR=0.82, outperforming LightGBM (IC=0.040 +/- 0.015, IR=0.71) by 12%.
Ablation study: removing cross-sectional attention reduces IC by 15% (0.045 -> 0.038).
Code: https://github.com/author/hatt. Random seed=42. GPU: 48h on 4x NVIDIA A100.
Hyperparameters: lr=0.001, batch_size=256, epochs=100, hidden_dim=128.
Data: CRSP daily returns + Compustat fundamentals, 2000-2023.
Theorem 1: Attention mechanism has O(n^2) complexity. Proof provided.
Figures include legends, axis labels, and captions.
Related work discusses differences from Smith et al. (2024) and Jones et al. (2025).
"""
        elif quality_level == "accept":
            return base + """
We propose a transformer model for stock prediction. We compare to LightGBM and LSTM.
Results show IC=0.043, outperforming baselines by 8%. Ablation study included.
Code provided on GitHub.
"""
        elif quality_level == "weak_accept":
            return base + """
We use deep learning for stock prediction. Results are positive.
Compared to a couple baselines.
"""
        elif quality_level == "borderline":
            return base + """
We use deep learning for stocks. Results are good. One baseline compared.
"""
        else:  # reject
            return base + """
We use deep learning for stocks. Our method works well.
"""

    def _quality_to_score(self, quality_level: str) -> float:
        """Map quality level to expected overall score (1-10 scale)."""
        mapping = {
            "strong_accept": 9.0,
            "accept": 7.0,
            "weak_accept": 6.0,
            "borderline": 5.0,
            "reject": 3.0,
        }
        return mapping.get(quality_level, 5.0)

    def _quality_to_recommendation(self, quality_level: str) -> str:
        """Map quality level to expected recommendation string."""
        mapping = {
            "strong_accept": "Strong Accept",
            "accept": "Accept",
            "weak_accept": "Weak Accept",
            "borderline": "Borderline",
            "reject": "Reject",
        }
        return mapping.get(quality_level, "Unknown")

    def generate_dataset(
        self,
        n_per_level: int = 20,
        domain: str = "empirical",
    ) -> pd.DataFrame:
        """
        Generate full calibration dataset.

        Parameters
        ----------
        n_per_level : int
            Number of papers per quality level. Default 20.
        domain : str
            Domain: empirical, finance, or ml.

        Returns
        -------
        pd.DataFrame
            Columns: paper_id, quality_level, domain, text,
            expected_score, expected_recommendation.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for generate_dataset")

        rows = []
        for quality_level in self.QUALITY_LEVELS:
            for i in range(n_per_level):
                paper = self.generate_paper(quality_level, domain)
                rows.append(paper)

        return pd.DataFrame(rows)

    def generate_mixed_domain_dataset(
        self,
        n_per_level: int = 20,
        domains: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Generate dataset across multiple domains.

        Parameters
        ----------
        n_per_level : int
            Number of papers per quality level per domain.
        domains : list[str], optional
            List of domains. Defaults to all three.

        Returns
        -------
        pd.DataFrame
            Same columns as generate_dataset, with domain column.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for generate_mixed_domain_dataset")

        domains = domains or self.DOMAINS
        all_rows = []

        for domain in domains:
            df = self.generate_dataset(n_per_level=n_per_level, domain=domain)
            all_rows.append(df)

        return pd.concat(all_rows, ignore_index=True)

    @classmethod
    def get(cls, name: str) -> list[dict]:
        """Get a calibration dataset by name."""
        if name not in cls.KNOWN_DATASETS:
            raise ValueError(
                f"Unknown dataset: {name}. Available: {list(cls.KNOWN_DATASETS.keys())}"
            )
        return cls.KNOWN_DATASETS[name]["samples"]

    @classmethod
    def add_custom(cls, name: str, samples: list[dict], source: str = "custom"):
        """Add a custom calibration dataset."""
        cls.KNOWN_DATASETS[name] = {"description": f"Custom dataset: {source}",
                                     "samples": samples, "source": source}


# ─── LLM Reviewer ──────────────────────────────────────────────────────────────


class LLMReviewer:
    """
    LLM-based academic paper reviewer — calibrated against human judgments.

    Supports:
    - Single paper review with structured scoring
    - Batch review (parallel)
    - Calibration against human-labeled datasets
    - Chinese and English venue templates
    - Integration with existing AIRouter for model calls
    """

    def __init__(
        self,
        judge_model: str = "gpt5",
        default_venue: str = "ML",
        enable_cache: bool = True,
        cache_dir: str = "data/review_cache",
    ):
        """
        Initialize the LLM reviewer.

        Parameters
        ----------
        judge_model : str
            Model alias to use for judging. Default "gpt5" routes to GPT-5.4-Mini via B.AI.
        default_venue : str
            Default venue for review format. Can be overridden per-review.
        enable_cache : bool
            Cache review results to avoid re-judging the same paper.
        cache_dir : str
            Directory for review cache files.
        """
        self.judge_model = judge_model
        self.default_venue = default_venue
        self.enable_cache = enable_cache
        self.cache_dir = Path(cache_dir)
        self._review_count = 0

        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Core review ───────────────────────────────────────────────────────────

    def review(
        self,
        paper_content: str,
        venue: str | None = None,
        language: str | None = None,
        paper_number: int = 1,
        use_cache: bool = True,
    ) -> ReviewResult:
        """
        Generate a structured review for a single paper.

        Parameters
        ----------
        paper_content : str
            Full text content of the paper.
        venue : str, optional
            Venue identifier (e.g. "CVPR", "JFE", "经济研究"). Defaults to default_venue.
        language : str, optional
            "en" or "zh". Auto-detected from venue if None.
        paper_number : int
            Paper number for the review (used in prompt).
        use_cache : bool
            Use cached result if available.

        Returns
        -------
        ReviewResult
            Structured review with per-dimension scores and recommendation.
        """
        venue = venue or self.default_venue
        venue_cfg = VENUE_CONFIGS.get(venue, VENUE_CONFIGS["ML"])
        language = language or venue_cfg.get("language", "en")

        # Check cache
        if use_cache and self.enable_cache:
            cached = self._load_cache(paper_content, venue)
            if cached:
                logger.debug(f"Review cache hit for venue={venue}")
                return cached

        # Build prompt
        if language == "zh":
            prompt = _REVIEWER_PROMPT_ZH.format(
                venue_name=venue_cfg["name"],
                domain=venue_cfg["domain"],
                paper_number=paper_number,
                paper_content=paper_content[:12000],  # Truncate to avoid token limits
            )
        else:
            prompt = _REVIEWER_PROMPT_EN.format(
                venue_name=venue_cfg["name"],
                domain=venue_cfg["domain"],
                focus=venue_cfg["focus"],
                paper_number=paper_number,
                paper_content=paper_content[:12000],
            )

        # Call LLM
        raw_response = self._call_llm(prompt, model=self.judge_model, language=language)

        # Parse result
        result = ReviewResult.from_llm_response(raw_response)
        result.metadata["venue"] = venue
        result.metadata["judge_model"] = self.judge_model
        result.metadata["paper_number"] = paper_number

        # Save cache
        if self.enable_cache:
            self._save_cache(paper_content, venue, result)

        self._review_count += 1
        return result

    def batch_review(
        self,
        papers: list[dict],
        venue: str | None = None,
        parallel: bool = True,
        max_workers: int = 4,
        paper_numbers: list[int] | None = None,
    ) -> list[ReviewResult]:
        """
        Review multiple papers in sequence or parallel.

        Parameters
        ----------
        papers : list[dict]
            List of {"content": str, "metadata": dict} dicts.
        venue : str, optional
            Venue for all papers.
        parallel : bool
            Use ThreadPoolExecutor for parallel review.
        max_workers : int
            Max parallel workers.
        paper_numbers : list[int], optional
            Paper numbers. Auto-assigned if None.

        Returns
        -------
        list[ReviewResult]
        """
        if paper_numbers is None:
            paper_numbers = list(range(1, len(papers) + 1))

        results: list[ReviewResult] = []
        for i, paper in enumerate(papers):
            try:
                result = self.review(
                    paper_content=paper.get("content", ""),
                    venue=venue,
                    paper_number=paper_numbers[i],
                )
                results.append(result)
            except Exception as exc:
                logger.error(f"Review failed for paper {paper_numbers[i]}: {exc}")
                # Return a placeholder error result
                results.append(
                    ReviewResult(
                        scores={},
                        overall_score=0.0,
                        overall_recommendation=f"Review Error: {exc}",
                        summary="",
                        strengths=[],
                        weaknesses=[f"Review failed: {exc}"],
                        detailed_feedback="",
                        confidence=0.0,
                        metadata={"paper_number": paper_numbers[i], "error": str(exc)},
                    )
                )
        return results

    # ── Calibration ───────────────────────────────────────────────────────────

    def calibrate(
        self,
        dataset: list[tuple[str, str]],
        target_accuracy: float = 0.65,
        max_samples: int | None = None,
    ) -> CalibrationResult:
        """
        Calibrate the reviewer against human judgments.

        Compares the LLM reviewer's recommendations against human-labeled
        ground truth, computing balanced accuracy and per-class metrics.

        Parameters
        ----------
        dataset : list of (paper_content, human_verdict) tuples
            Labeled papers with ground-truth human verdicts.
        target_accuracy : float
            Stop when balanced accuracy >= this threshold.
        max_samples : int, optional
            Limit dataset size for faster calibration.

        Returns
        -------
        CalibrationResult
            Balanced accuracy, precision/recall per class, confusion matrix.
        """
        if max_samples:
            dataset = dataset[:max_samples]

        classes = sorted(set(human for _, human in dataset))
        n_classes = len(classes)

        # Initialize confusion matrix
        cm = [[0] * n_classes for _ in range(n_classes)]
        correct = 0
        total = 0

        predictions: list[tuple[str, str]] = []

        for paper_content, human_verdict in dataset:
            try:
                result = self.review(paper_content, use_cache=False)
                llm_verdict = result.overall_recommendation

                predictions.append((llm_verdict, human_verdict))

                # Update confusion matrix
                if llm_verdict in classes and human_verdict in classes:
                    pred_idx = classes.index(llm_verdict)
                    true_idx = classes.index(human_verdict)
                    cm[true_idx][pred_idx] += 1

                    if llm_verdict == human_verdict:
                        correct += 1
                    total += 1

            except Exception as exc:
                logger.warning(f"Calibration failed for sample: {exc}")
                continue

        total = max(total, 1)

        # Compute per-class precision/recall/F1
        precision_per_class, recall_per_class, f1_per_class = {}, {}, {}
        for i, cls in enumerate(classes):
            tp = cm[i][i]
            fp = sum(cm[r][i] for r in range(n_classes)) - tp
            fn = sum(cm[i][c] for c in range(n_classes)) - tp

            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            f1 = 2 * prec * rec / max(prec + rec, 1e-9)

            precision_per_class[cls] = prec
            recall_per_class[cls] = rec
            f1_per_class[cls] = f1

        # Balanced accuracy
        balanced_acc = sum(recall_per_class.values()) / n_classes

        # Per-dimension correlation (only available for synthetic datasets)
        dimension_correlation: dict[str, float] = {}

        return CalibrationResult(
            balanced_accuracy=balanced_acc,
            precision_per_class=precision_per_class,
            recall_per_class=recall_per_class,
            f1_per_class=f1_per_class,
            confusion_matrix=cm,
            dimension_correlation=dimension_correlation,
            dataset_size=len(dataset),
            dataset_source="user_provided",
            total_predictions=total,
            correct_predictions=correct,
        )

    def calibrate_on_synthetic(
        self,
        dataset: CalibrationDataset | None = None,
        n_per_level: int = 20,
        domain: str = "empirical",
    ) -> CalibrationResult:
        """
        Run calibration on a synthetic dataset generated from CalibrationDataset.

        Steps:
        1. Generate n_per_level papers at each quality level
        2. Run self.review() on each paper
        3. Compare LLM recommendations vs expected
        4. Compute: balanced accuracy, confusion matrix, per-class metrics

        Parameters
        ----------
        dataset : CalibrationDataset, optional
            Dataset generator. If None, creates a new one with default seed.
        n_per_level : int
            Number of papers per quality level. Default 20.
        domain : str
            Domain for synthetic papers. Default "empirical".

        Returns
        -------
        CalibrationResult
            Balanced accuracy, precision/recall/F1 per class, confusion matrix.
        """
        if dataset is None:
            dataset = CalibrationDataset(seed=42)

        print(f"\n  Generating synthetic calibration dataset: "
              f"{n_per_level} papers x {len(CalibrationDataset.QUALITY_LEVELS)} levels "
              f"= {n_per_level * len(CalibrationDataset.QUALITY_LEVELS)} total papers")
        cal_df = dataset.generate_dataset(n_per_level=n_per_level, domain=domain)
        print(f"  Dataset shape: {cal_df.shape}")
        print(f"  Columns: {list(cal_df.columns)}")

        # Build (content, expected_verdict) tuples
        dataset_tuples: list[tuple[str, str]] = []
        for _, row in cal_df.iterrows():
            dataset_tuples.append((row["text"], row["expected_recommendation"]))

        print(f"  Running LLM reviews on {len(dataset_tuples)} papers...")
        result = self.calibrate(dataset_tuples)
        result.dataset_source = f"synthetic:{domain}"
        result.dataset_size = len(dataset_tuples)

        # Print summary
        print("\n  Calibration Result:")
        print(f"    Balanced Accuracy : {result.balanced_accuracy:.1%}")
        print(f"    Agreement Rate    : {result.correct_predictions}/{result.total_predictions} "
              f"({result.correct_predictions / max(result.total_predictions, 1):.1%})")
        print("  Per-class F1:")
        for cls, f1 in result.f1_per_class.items():
            print(f"    {cls:20s}: {f1:.1%}")

        return result

    def reliability_diagram_data(
        self,
        dataset: CalibrationDataset | None = None,
        n_per_level: int = 20,
        bins: int = 10,
        domain: str = "empirical",
    ) -> dict:
        """
        Generate data for a reliability diagram.

        Compares predicted probability of acceptance vs actual acceptance rate
        across bins of predicted confidence. Useful for detecting over/under-
        confident LLM reviewer scores.

        Parameters
        ----------
        dataset : CalibrationDataset, optional
            Dataset generator. Default creates one with seed=42.
        n_per_level : int
            Papers per quality level. Default 20.
        bins : int
            Number of bins for the reliability diagram. Default 10.
        domain : str
            Domain for synthetic papers.

        Returns
        -------
        dict
            Keys: bin_edges, bin_centers, predicted_probs, actual_fractions,
            counts, ideal (diagonal), ece (Expected Calibration Error).
        """
        if dataset is None:
            dataset = CalibrationDataset(seed=42)

        cal_df = dataset.generate_dataset(n_per_level=n_per_level, domain=domain)
        threshold = 6.0  # Score >= 6 means "accept"

        predicted_probs: list[float] = []
        actuals: list[int] = []

        for _, row in cal_df.iterrows():
            try:
                review_result = self.review(row["text"], use_cache=False)
                # Map overall score 1-10 to probability of acceptance
                # P(accept) = (score - 1) / 9 maps linearly from [1,10] to [0,1]
                prob = (review_result.overall_score - 1) / 9
                prob = max(0.0, min(1.0, prob))

                actual = 1 if review_result.overall_score >= threshold else 0
                predicted_probs.append(prob)
                actuals.append(actual)
            except Exception:
                continue

        if not predicted_probs:
            return {"error": "No predictions generated"}

        # Bin the data
        bin_edges = np.linspace(0, 1, bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        predicted_bin_means = []
        actual_bin_means = []
        bin_counts = []

        for i in range(bins):
            low, high = bin_edges[i], bin_edges[i + 1]
            in_bin = [
                (p, a) for p, a in zip(predicted_probs, actuals)
                if low <= p < high or (i == bins - 1 and p == high)
            ]
            if in_bin:
                preds = [x[0] for x in in_bin]
                acts = [x[1] for x in in_bin]
                predicted_bin_means.append(np.mean(preds))
                actual_bin_means.append(np.mean(acts))
                bin_counts.append(len(in_bin))
            else:
                predicted_bin_means.append(bin_centers[i])
                actual_bin_means.append(bin_centers[i])
                bin_counts.append(0)

        # Expected Calibration Error
        ece = sum(
            c / len(predicted_probs) * abs(p - a)
            for c, p, a in zip(bin_counts, predicted_bin_means, actual_bin_means)
        )

        # Ideal diagonal
        ideal = list(bin_centers)

        return {
            "bin_edges": bin_edges.tolist(),
            "bin_centers": bin_centers.tolist(),
            "predicted_probs": predicted_bin_means,
            "actual_fractions": actual_bin_means,
            "counts": bin_counts,
            "ideal": ideal,
            "ece": float(ece),
            "total_samples": len(predicted_probs),
        }

    # ── Helper methods ───────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, model: str, language: str) -> str:
        """Call the LLM via AIRouter."""
        try:
            from scripts.ai_router import AIRouter
            router = AIRouter()
            result = router.chat(
                user_input=prompt,
                model=model,
                temperature=0.3,  # Low temperature for structured output
                max_tokens=4096,
            )
            return result.response
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            raise RuntimeError(f"LLM review call failed: {exc}") from exc

    def _cache_key(self, content: str, venue: str) -> str:
        """Generate a cache key for a paper review."""
        import hashlib
        key_str = f"{venue}:{content[:200]}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _cache_path(self, content: str, venue: str) -> Path:
        return self.cache_dir / f"{venue}_{self._cache_key(content, venue)}.json"

    def _load_cache(self, content: str, venue: str) -> ReviewResult | None:
        """Load cached review if exists and not expired (7 days)."""
        cache_path = self._cache_path(content, venue)
        if not cache_path.exists():
            return None
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days > 7:
            return None
        try:
            with open(cache_path) as f:
                data = json.load(f)
            return ReviewResult(
                scores={
                    k: ReviewScore(**v) for k, v in data.get("scores", {}).items()
                },
                **{k: v for k, v in data.items()
                   if k not in ("scores",)},
            )
        except Exception:
            return None

    def _save_cache(self, content: str, venue: str, result: ReviewResult):
        """Save review result to cache."""
        try:
            with open(self._cache_path(content, venue), "w") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"Failed to save review cache: {exc}")

    # ── Comparison with rule-based checks ───────────────────────────────────

    def compare_with_rules(
        self,
        paper_content: str,
        rules_result: dict,
        venue: str | None = None,
    ) -> dict:
        """
        Compare LLM review with rule-based halt-rule check results.

        Useful for understanding where LLM and rules agree/disagree,
        which can guide calibration efforts.

        Parameters
        ----------
        paper_content : str
            The paper text.
        rules_result : dict
            Result from HaltRulesRegistry.validate(), e.g.
            {"passed": True, "violations": ["missing baseline comparison"]}
        venue : str, optional
            Venue for review format.

        Returns
        -------
        dict with comparison metrics:
            - llm_overall_score
            - rules_passed
            - agreement: whether LLM and rules agree on accept/reject
            - conflict_notes: where they disagree
        """
        review = self.review(paper_content, venue=venue, use_cache=False)

        threshold = VENUE_CONFIGS.get(venue or self.default_venue, VENUE_CONFIGS["ML"])
        llm_accept = review.overall_score >= threshold["threshold_accept"]
        rules_pass = rules_result.get("passed", True)

        return {
            "llm_overall_score": review.overall_score,
            "llm_recommendation": review.overall_recommendation,
            "llm_accept": llm_accept,
            "rules_passed": rules_pass,
            "rules_violations": rules_result.get("violations", []),
            "agreement": llm_accept == rules_pass,
            "conflict_notes": (
                "LLM and rules disagree: "
                f"LLM={'Accept' if llm_accept else 'Reject'}, "
                f"Rules={'Pass' if rules_pass else 'Fail'}"
                if llm_accept != rules_pass else
                "LLM and rules agree"
            ),
            "llm_scores": {k: v.score for k, v in review.scores.items()},
        }
