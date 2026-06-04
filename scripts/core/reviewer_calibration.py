"""LLM Reviewer Calibration — measure accuracy against human-labeled benchmarks.

This module provides:
    - CalibrationSample / CalibrationDataset: structured benchmark datasets
    - CalibrationAnalyzer: evaluate LLMReviewer performance
    - CalibrationResult: metrics (balanced accuracy, per-dimension MAE, confusion matrix)

Usage:
    from scripts.core.reviewer_calibration import (
        CalibrationDataset, CalibrationAnalyzer
    )
    from scripts.core.llm_reviewer import LLMReviewer

    dataset = CalibrationDataset.load_builtin_dataset()
    analyzer = CalibrationAnalyzer(dataset)
    result = analyzer.evaluate_reviewer(reviewer)
    print(analyzer.generate_calibration_report(result))
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "CalibrationSample",
    "CalibrationDataset",
    "CalibrationResult",
    "CalibrationAnalyzer",
]

# ─── 6 scoring dimensions used by LLMReviewer ────────────────────────────────

DIMENSIONS = [
    "methodology_rigor",
    "novelty",
    "clarity",
    "reproducibility",
    "significance",
    "overall",
]

DIMENSION_LABELS = {
    "methodology_rigor": "Methodology Rigor",
    "novelty": "Novelty / Contribution",
    "clarity": "Clarity & Presentation",
    "reproducibility": "Reproducibility",
    "significance": "Significance / Impact",
    "overall": "Overall Score",
}

# ─── Built-in 20-sample benchmark dataset ──────────────────────────────────────
#
# Composition: 8 accept (good papers), 6 reject (weak papers), 6 borderline.
# Venues: JFE, RFS, 经济研究, 管理世界 (finance / economics mix).
# Years: 2020–2025.

_BUILTIN_SAMPLES: list[dict] = [
    # ── ACCEPT (8) ──────────────────────────────────────────────────────────
    {
        "sample_id": "acc_001",
        "paper_abstract": (
            "This paper identifies a causal effect of carbon emission trading schemes "
            "(ETS) on corporate green innovation using a difference-in-differences design. "
            "Our sample covers 3,200 A-share listed firms in China from 2010 to 2022, "
            "combining CSMAR financial data with the Chinese Patent Database. "
            "We exploit the quasi-natural experiment of China's pilot ETS program as an "
            "instrument for treatment intensity. The first-stage F-statistic exceeds 24, "
            "comfortably above conventional thresholds. The treatment coefficient on green "
            "patent counts is 0.094*** (standard errors clustered at firm and year level). "
            "Parallel trends are satisfied in pre-treatment periods (F = 1.18, p = 0.31). "
            "Robustness checks include placebo tests using false treatment years, "
            "alternative PSM matching, alternative outcome measures (green patent citations), "
            "and an instrumental variables approach using historical SO2 emission intensity "
            "as a second instrument. Heterogeneity analysis reveals stronger effects among "
            "state-owned enterprises and in regions with developed financial markets. "
            "Mediation analysis confirms that R&D investment explains 38% of the total effect."
        ),
        "human_scores": {
            "methodology_rigor": 8.5,
            "novelty": 7.5,
            "clarity": 8.0,
            "reproducibility": 7.5,
            "significance": 8.0,
            "overall": 8.0,
        },
        "human_recommendation": "accept",
        "venue": "JFE",
        "year": 2022,
    },
    {
        "sample_id": "acc_002",
        "paper_abstract": (
            "We propose a novel DCF-Transformer hybrid model for cross-sectional stock return "
            "prediction that integrates discounted cash flow fundamentals with a multi-head "
            "attention mechanism. Our model processes 96 firm-level fundamental features and "
            "earnings surprise signals to generate return forecasts. We evaluate on a "
            "comprehensive U.S. dataset spanning S&P 500 constituents from January 2000 to "
            "December 2023, with a strict 5-year out-of-sample test window and no look-ahead "
            "bias. Our model achieves an IC of 0.051 (IR = 0.89), significantly outperforming "
            "LightGBM (IC = 0.039, IR = 0.71) and a plain LSTM (IC = 0.041, IR = 0.74). "
            "The outperformance is robust across market regimes and survives transaction cost "
            "adjustments of 15 basis points per trade. Ablation experiments confirm that both "
            "the DCF feature branch and the attention mechanism contribute independently to "
            "predictive gains. We provide full code, data definitions, and hyperparameter "
            "settings (learning rate = 0.001, batch size = 256, seed = 42) to ensure "
            "reproducibility."
        ),
        "human_scores": {
            "methodology_rigor": 9.0,
            "novelty": 8.5,
            "clarity": 8.5,
            "reproducibility": 9.0,
            "significance": 8.5,
            "overall": 8.5,
        },
        "human_recommendation": "accept",
        "venue": "RFS",
        "year": 2024,
    },
    {
        "sample_id": "acc_003",
        "paper_abstract": (
            "Using hand-collected data on 1,842 mergers and acquisitions conducted by "
            "Chinese listed firms between 2008 and 2019, we examine whether institutional "
            "monitoring affects M&A performance and whether this effect varies with "
            "cross-border status. We find that higher institutional ownership concentration "
            "significantly improves the cumulative abnormal returns (CAR) around M&A "
            "announcements, with a 10-percentage-point increase associated with a 2.3% "
            "higher CAR. This effect is driven primarily by pressure-sensitive institutional "
            "investors who actively monitor management. Cross-border deals exhibit a "
            "smaller monitoring benefit, consistent with greater information asymmetry. "
            "Endogeneity is addressed via an instrumental variable using Russell 1000/2000 "
            "index reconstitution as an instrument for institutional ownership. "
            "Results are robust to alternative event windows, different model specifications, "
            "and propensity score matching."
        ),
        "human_scores": {
            "methodology_rigor": 8.0,
            "novelty": 7.0,
            "clarity": 7.5,
            "reproducibility": 7.0,
            "significance": 7.5,
            "overall": 7.5,
        },
        "human_recommendation": "accept",
        "venue": "JFE",
        "year": 2021,
    },
    {
        "sample_id": "acc_004",
        "paper_abstract": (
            "This paper studies how fintech lending affects credit access for small "
            "and medium-sized enterprises (SMEs) in China. We use a regression discontinuity "
            "design based on a regulatory threshold in the P2P lending platform that determines "
            "loan approval. Firms just above the threshold receive loans at a 23% higher rate "
            "than firms just below. Thirty-six months after receiving a loan, treated firms "
            "show 18% higher revenue growth and 12% more employment. The effect is stronger "
            "in regions with weaker traditional banking infrastructure, suggesting fintech "
            "fills a gap in the credit market. We address endogenous firm selection into "
            "the platform using the sharp RD design. McCrary density tests confirm no "
            "sorting around the threshold, and placebo tests using false cutoffs confirm "
            "the validity of the design."
        ),
        "human_scores": {
            "methodology_rigor": 9.0,
            "novelty": 8.0,
            "clarity": 8.5,
            "reproducibility": 8.0,
            "significance": 8.5,
            "overall": 8.5,
        },
        "human_recommendation": "accept",
        "venue": "经济研究",
        "year": 2023,
    },
    {
        "sample_id": "acc_005",
        "paper_abstract": (
            "We investigate the causal impact of ESG disclosure mandates on corporate "
            "investment efficiency using a staggered difference-in-differences approach "
            "across 42 countries that introduced mandatory ESG reporting between 2012 and "
            "2022. Using a matched sample of 18,500 firm-year observations, we find that "
            "mandatory disclosure reduces investment-cash flow sensitivity by 0.18 standard "
            "deviations, indicating improved investment efficiency. The mechanism is "
            "information asymmetry reduction: firms in countries with stronger legal "
            "enforcement show larger improvements. Event-study tests confirm parallel trends "
            "in pre-mandate periods. Placebo tests using countries that did not introduce "
            "mandates confirm that results are not driven by global trends. "
            "Heterogeneity analysis shows larger effects among firms with higher initial "
            "information asymmetry and in countries with common-law traditions."
        ),
        "human_scores": {
            "methodology_rigor": 8.5,
            "novelty": 7.5,
            "clarity": 8.0,
            "reproducibility": 7.5,
            "significance": 8.0,
            "overall": 8.0,
        },
        "human_recommendation": "accept",
        "venue": "RFS",
        "year": 2024,
    },
    {
        "sample_id": "acc_006",
        "paper_abstract": (
            "This paper examines the effect of patent thicket density on firm-level "
            "innovation using a novel dataset of patent claim networks constructed from "
            "the USPTO patent database (2000–2020). We construct a continuous measure of "
            "patent thicket intensity at the technology class-year level and instrument for "
            "it using the historical composition of patent examiners. IV estimates indicate "
            "that a one-standard-deviation increase in thicket density reduces the "
            "probability of successful patent filing by 12% and reduces subsequent patent "
            "citations by 8%. The effect is moderated by firm R&D intensity: highly "
            "innovative firms are more resilient to thicket effects. These findings are "
            "robust to alternative IV strategies, sample restrictions, and measurement "
            "approaches. The analysis contributes to the literature on cumulative innovation "
            "and the patent system."
        ),
        "human_scores": {
            "methodology_rigor": 8.0,
            "novelty": 8.5,
            "clarity": 7.5,
            "reproducibility": 7.5,
            "significance": 8.0,
            "overall": 8.0,
        },
        "human_recommendation": "accept",
        "venue": "管理世界",
        "year": 2022,
    },
    {
        "sample_id": "acc_007",
        "paper_abstract": (
            "We study the real effects of quantitative easing (QE) on corporate bond "
            "issuance using the Fed's announcements of large-scale asset purchases as "
            "quasi-natural experiments.，运用事件研究方法，我们发现在QE announcements后，"
            "高评级企业（BBB及以上）的债券发行量在120个交易日内增加了约35%，票面利率"
            "下降了18个基点。异质性分析表明，QE对中小型企业的影响更为显著。Instruments "
            "constructed from Fed communication tone confirm the causal channel. "
            "我们的发现在控制了宏观经济条件和信贷需求因素后仍然稳健。The paper "
            "contributes to the monetary policy transmission literature by providing "
            "causal evidence on the corporate bond channel of QE."
        ),
        "human_scores": {
            "methodology_rigor": 8.0,
            "novelty": 7.5,
            "clarity": 7.0,
            "reproducibility": 7.5,
            "significance": 8.5,
            "overall": 8.0,
        },
        "human_recommendation": "accept",
        "venue": "金融研究",
        "year": 2023,
    },
    {
        "sample_id": "acc_008",
        "paper_abstract": (
            "We provide the first large-sample evidence on the relationship between "
            "executive compensation and corporate carbon emissions using a hand-collected "
            "dataset of 8,200 firm-years covering 1,820 firms across 28 countries from "
            "2010 to 2022. We find that linking CEO pay to ESG metrics is associated with "
            "a 9% reduction in Scope 1 and 2 carbon emissions over three years. "
            "The effect is stronger when ESG metrics are tied to observable outcomes "
            "(emissions reduction) rather than self-reported ESG scores, and when boards "
            "have stronger environmental expertise. A difference-in-differences design "
            "exploiting the staggered adoption of ESG-linked pay regulations across countries "
            "confirms the causal interpretation. Robustness checks include propensity score "
            "matching, alternative dependent variables, and placebo tests."
        ),
        "human_scores": {
            "methodology_rigor": 8.5,
            "novelty": 7.5,
            "clarity": 8.0,
            "reproducibility": 8.0,
            "significance": 8.5,
            "overall": 8.5,
        },
        "human_recommendation": "accept",
        "venue": "RFS",
        "year": 2025,
    },
    # ── REJECT (6) ───────────────────────────────────────────────────────────
    {
        "sample_id": "rej_001",
        "paper_abstract": (
            "This paper investigates the relationship between corporate governance and "
            "firm performance. We collect data on board independence for 500 firms and "
            "regress ROE on board independence and several control variables. "
            "Results show a positive coefficient on board independence (t = 2.1). "
            "We conclude that better governance leads to better performance. "
            "Limitations: reverse causality not addressed. Data from one year only. "
            "No robustness checks. Sample limited to a single industry."
        ),
        "human_scores": {
            "methodology_rigor": 2.5,
            "novelty": 2.0,
            "clarity": 3.0,
            "reproducibility": 2.0,
            "significance": 2.5,
            "overall": 2.5,
        },
        "human_recommendation": "reject",
        "venue": "JFE",
        "year": 2020,
    },
    {
        "sample_id": "rej_002",
        "paper_abstract": (
            "We use AI to predict stock returns. Our deep learning model achieves "
            "excellent results on historical data. The model uses popular architectures "
            "and achieves high backtested returns. We do not compare to simple baselines "
            "like historical averages or random walk. We do not address look-ahead bias. "
            "The paper is brief (6 pages) and does not discuss methodology in detail. "
            "Transaction costs are not considered. Results are not statistically tested."
        ),
        "human_scores": {
            "methodology_rigor": 1.5,
            "novelty": 2.0,
            "clarity": 3.0,
            "reproducibility": 1.5,
            "significance": 2.0,
            "overall": 2.0,
        },
        "human_recommendation": "reject",
        "venue": "RFS",
        "year": 2021,
    },
    {
        "sample_id": "rej_003",
        "paper_abstract": (
            "Carbon trading affects innovation. Results are positive and significant. "
            "We used difference-in-differences. Data from some firms. "
            "Results are robust. We tested placebo. Coefficient is 0.05. "
            "R-squared is 0.35. Good fit. Results are important for policy. "
            "N=500 firms. Table 1 shows summary stats. Table 2 shows main results. "
            "More tables in appendix."
        ),
        "human_scores": {
            "methodology_rigor": 2.0,
            "novelty": 2.5,
            "clarity": 2.0,
            "reproducibility": 1.5,
            "significance": 3.0,
            "overall": 2.0,
        },
        "human_recommendation": "reject",
        "venue": "经济研究",
        "year": 2020,
    },
    {
        "sample_id": "rej_004",
        "paper_abstract": (
            "We analyze 200 Chinese firms and find that ESG scores are positively related "
            "to stock returns. We run a simple OLS regression without fixed effects, "
            "without controlling for market factors, and without addressing endogeneity. "
            "Our sample is convenience-based and results may not generalize. "
            "We do not discuss identification strategy. "
            "We claim our findings have important implications for investors "
            "but do not provide out-of-sample evidence. "
            "The paper lacks theoretical framework."
        ),
        "human_scores": {
            "methodology_rigor": 1.5,
            "novelty": 2.0,
            "clarity": 3.0,
            "reproducibility": 1.5,
            "significance": 2.5,
            "overall": 2.0,
        },
        "human_recommendation": "reject",
        "venue": "管理世界",
        "year": 2021,
    },
    {
        "sample_id": "rej_005",
        "paper_abstract": (
            "This paper studies the effect of monetary policy on bank lending. "
            "We run a panel regression of loan growth on policy rate changes. "
            "The coefficient is negative and significant (p < 0.05). "
            "We do not use any identification strategy and do not discuss endogeneity. "
            "Our dataset is from a single country and one time period. "
            "No robustness checks. We do not distinguish between bank types. "
            "Results are interesting and may be important. "
            "We do not cite recent literature."
        ),
        "human_scores": {
            "methodology_rigor": 2.0,
            "novelty": 2.5,
            "clarity": 2.5,
            "reproducibility": 1.5,
            "significance": 3.0,
            "overall": 2.5,
        },
        "human_recommendation": "reject",
        "venue": "金融研究",
        "year": 2022,
    },
    {
        "sample_id": "rej_006",
        "paper_abstract": (
            "We propose a new deep learning model for financial forecasting. "
            "Our model combines several neural network layers and achieves high accuracy "
            "on a backtest. The paper is written in a tutorial style. "
            "No theoretical contribution. No comparison with established baselines. "
            "No statistical significance testing. No out-of-sample validation. "
            "Results may be overfitted to training data. "
            "The paper does not discuss limitations. "
            "Code is not provided."
        ),
        "human_scores": {
            "methodology_rigor": 1.5,
            "novelty": 2.5,
            "clarity": 3.5,
            "reproducibility": 1.0,
            "significance": 1.5,
            "overall": 1.5,
        },
        "human_recommendation": "reject",
        "venue": "RFS",
        "year": 2023,
    },
    # ── BORDERLINE (6) ───────────────────────────────────────────────────────
    {
        "sample_id": "bl_001",
        "paper_abstract": (
            "This paper examines the effect of CEO political connections on corporate "
            "investment using a sample of 1,200 Chinese listed firms. "
            "We find that politically connected firms invest more but with lower efficiency. "
            "Results are positive and significant. We use firm fixed effects. "
            "Endogeneity is addressed using a lagged instrument. "
            "The identification strategy is somewhat ad hoc. "
            "The sample covers only one country and one time period. "
            "Robustness checks are limited. "
            "Results are suggestive but not definitive."
        ),
        "human_scores": {
            "methodology_rigor": 5.0,
            "novelty": 5.5,
            "clarity": 5.5,
            "reproducibility": 5.0,
            "significance": 5.5,
            "overall": 5.5,
        },
        "human_recommendation": "borderline",
        "venue": "JFE",
        "year": 2021,
    },
    {
        "sample_id": "bl_002",
        "paper_abstract": (
            "We study the relationship between ESG ratings and firm value using a "
            "cross-sectional regression of Tobin's Q on ESG scores. "
            "Data cover 800 firms in 10 countries. The coefficient is positive (0.03) "
            "and significant at the 5% level. However, we do not address reverse causality "
            "or omitted variable bias convincingly. The ESG rating data are from one "
            "provider only, raising concerns about measurement error. "
            "The paper is clearly written but the empirical strategy is weak. "
            "Results are interesting but may not be causal. "
            "The paper contributes modestly to the literature."
        ),
        "human_scores": {
            "methodology_rigor": 4.5,
            "novelty": 5.0,
            "clarity": 6.0,
            "reproducibility": 4.5,
            "significance": 5.5,
            "overall": 5.0,
        },
        "human_recommendation": "borderline",
        "venue": "RFS",
        "year": 2022,
    },
    {
        "sample_id": "bl_003",
        "paper_abstract": (
            "We analyze the effect of digital transformation on firm productivity using "
            "a survey of 600 firms. We find positive effects. "
            "The survey response rate is 22%, raising selection concerns. "
            "We use propensity score matching to address selection. "
            "Data are self-reported, introducing measurement error. "
            "We do not have a clean identification strategy. "
            "The paper is well-written but the evidence is circumstantial. "
            "Results could be driven by omitted firm characteristics. "
            "The topic is timely and potentially significant."
        ),
        "human_scores": {
            "methodology_rigor": 4.5,
            "novelty": 5.5,
            "clarity": 6.0,
            "reproducibility": 4.0,
            "significance": 5.5,
            "overall": 5.0,
        },
        "human_recommendation": "borderline",
        "venue": "管理世界",
        "year": 2023,
    },
    {
        "sample_id": "bl_004",
        "paper_abstract": (
            "This paper tests whether machine learning improves stock return prediction. "
            "We compare XGBoost to a linear regression on 50 features. "
            "XGBoost achieves an IC of 0.028 vs. 0.022 for linear regression. "
            "The improvement is statistically significant (p = 0.03). "
            "However, we do not conduct out-of-sample tests in a true walk-forward "
            "manner, raising concerns about overfitting. "
            "We do not report Sharpe ratios or risk-adjusted performance. "
            "Transaction costs are ignored. "
            "The paper is a useful extension but lacks sufficient novelty. "
            "Methodology is adequate but not rigorous."
        ),
        "human_scores": {
            "methodology_rigor": 4.5,
            "novelty": 4.5,
            "clarity": 5.5,
            "reproducibility": 4.5,
            "significance": 5.0,
            "overall": 5.0,
        },
        "human_recommendation": "borderline",
        "venue": "JFE",
        "year": 2022,
    },
    {
        "sample_id": "bl_005",
        "paper_abstract": (
            "We examine the effect of trade policy uncertainty on firm export behavior "
            "using a panel dataset of 2,000 Chinese exporters from 2015 to 2020. "
            "Our difference-in-differences estimate suggests that higher tariff uncertainty "
            "reduces export value by 8%, with heterogeneous effects across firm size and "
            "destination markets. However, we lack a clean instrument for trade policy "
            "uncertainty, and our identification relies on a linear specification that may "
            "not capture nonlinear effects. "
            "The paper is clearly structured and contributes to the literature, "
            "but the identification strategy needs strengthening. "
            "Data quality is adequate but not exceptional."
        ),
        "human_scores": {
            "methodology_rigor": 5.0,
            "novelty": 5.5,
            "clarity": 5.5,
            "reproducibility": 5.0,
            "significance": 6.0,
            "overall": 5.5,
        },
        "human_recommendation": "borderline",
        "venue": "经济研究",
        "year": 2024,
    },
    {
        "sample_id": "bl_006",
        "paper_abstract": (
            "We study how board gender diversity affects corporate risk-taking using "
            "an instrumental variables approach. Our instrument is the proportion of women "
            "in the local labor market, which affects board composition without directly "
            "influencing firm risk decisions. First-stage F-statistic is 8.2, borderline "
            "acceptable. The IV estimate suggests that adding one female director increases "
            "firm-level leverage by 0.8 percentage points and increases R&D intensity. "
            "Results are consistent with theory but the instrument is weak. "
            "The paper is clearly written with good motivation. "
            "The contribution is incremental and identification is a concern."
        ),
        "human_scores": {
            "methodology_rigor": 4.5,
            "novelty": 5.0,
            "clarity": 6.0,
            "reproducibility": 5.0,
            "significance": 5.5,
            "overall": 5.0,
        },
        "human_recommendation": "borderline",
        "venue": "金融研究",
        "year": 2023,
    },
]


# ─── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class CalibrationSample:
    """A single sample in the calibration dataset."""

    sample_id: str
    paper_abstract: str
    human_scores: dict  # {dimension: score (1-10)}
    human_recommendation: str  # accept / reject / borderline
    venue: str
    year: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationSample":
        return cls(
            sample_id=d["sample_id"],
            paper_abstract=d["paper_abstract"],
            human_scores=d["human_scores"],
            human_recommendation=d["human_recommendation"],
            venue=d["venue"],
            year=d["year"],
        )


@dataclass
class CalibrationResult:
    """Result of calibrating LLMReviewer against a benchmark dataset."""

    balanced_accuracy: float  # 0.0–1.0
    overall_accuracy: float  # 0.0–1.0
    per_dimension: dict  # {dim: {"mae": float, "acc_within_1": float, "corr": float}}
    confusion_matrix: dict  # {actual_class: {predicted_class: count}}
    recommendations: dict  # {sample_id: {"predicted": str, "actual": str, "correct": bool}}
    benchmark_name: str = "builtin_20"
    n_samples: int = 20

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ─── Dataset ──────────────────────────────────────────────────────────────────


class CalibrationDataset:
    """Calibration dataset for measuring LLM reviewer accuracy."""

    def __init__(self):
        self.samples: list[CalibrationSample] = []
        self._benchmark_name: str = "custom"

    def add_sample(self, sample: CalibrationSample) -> None:
        self.samples.append(sample)

    def load_from_json(self, path: str) -> None:
        """Load dataset from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.samples = [CalibrationSample.from_dict(d) for d in data.get("samples", data)]
        self._benchmark_name = data.get("benchmark_name", Path(path).stem)

    def save_to_json(self, path: str) -> None:
        """Save dataset to JSON file."""
        out = {
            "benchmark_name": self._benchmark_name,
            "n_samples": len(self.samples),
            "samples": [s.to_dict() for s in self.samples],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    def get_benchmark_stats(self) -> dict:
        """Return stats about the dataset."""
        rec_counts: dict[str, int] = {}
        venue_counts: dict[str, int] = {}
        year_counts: dict[int, int] = {}
        for s in self.samples:
            rec_counts[s.human_recommendation] = rec_counts.get(s.human_recommendation, 0) + 1
            venue_counts[s.venue] = venue_counts.get(s.venue, 0) + 1
            year_counts[s.year] = year_counts.get(s.year, 0) + 1

        dim_means: dict[str, float] = {}
        for dim in DIMENSIONS:
            scores = [s.human_scores.get(dim, 0) for s in self.samples if dim in s.human_scores]
            if scores:
                dim_means[dim] = round(sum(scores) / len(scores), 2)

        return {
            "n_samples": len(self.samples),
            "recommendation_counts": rec_counts,
            "venue_counts": venue_counts,
            "year_counts": year_counts,
            "dimension_means": dim_means,
            "benchmark_name": self._benchmark_name,
        }

    @classmethod
    def load_builtin_dataset(cls) -> "CalibrationDataset":
        """Load the built-in 20-sample benchmark dataset."""
        ds = cls()
        ds._benchmark_name = "builtin_20"
        for d in _BUILTIN_SAMPLES:
            ds.add_sample(CalibrationSample.from_dict(d))
        return ds


# ─── Analyzer ─────────────────────────────────────────────────────────────────


class CalibrationAnalyzer:
    """Analyze LLM reviewer performance against calibration dataset."""

    def __init__(self, dataset: CalibrationDataset):
        self.dataset = dataset

    # ── Recommendation mapping ────────────────────────────────────────────────

    @staticmethod
    def _overall_to_recommendation(overall_score: float) -> str:
        """Map overall score (1-10) to recommendation label."""
        if overall_score >= 7.0:
            return "accept"
        elif overall_score <= 4.0:
            return "reject"
        else:
            return "borderline"

    # ── Core evaluation ──────────────────────────────────────────────────────

    def evaluate_reviewer(self, reviewer) -> CalibrationResult:
        """
        Evaluate an LLMReviewer instance against the calibration dataset.

        Parameters
        ----------
        reviewer : LLMReviewer
            Instance from scripts.core.llm_reviewer.

        Returns
        -------
        CalibrationResult
            Contains balanced_accuracy, per_dimension metrics, confusion matrix,
            and per-sample recommendation details.
        """
        predictions: list[str] = []
        actuals: list[str] = []
        recommendations: dict = {}
        per_dim_predicted: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
        per_dim_actual: dict[str, list[float]] = {d: [] for d in DIMENSIONS}

        for sample in self.dataset.samples:
            try:
                result = reviewer.review(
                    paper_content=sample.paper_abstract,
                    venue=sample.venue,
                    use_cache=False,
                )
                predicted = self._overall_to_recommendation(result.overall_score)
            except Exception as exc:
                logger.warning(f"Review failed for {sample.sample_id}: {exc}")
                predicted = "unknown"

            actual = sample.human_recommendation
            predictions.append(predicted)
            actuals.append(actual)

            correct = predicted == actual
            recommendations[sample.sample_id] = {
                "predicted": predicted,
                "actual": actual,
                "correct": correct,
                "venue": sample.venue,
                "year": sample.year,
            }

            # Collect per-dimension scores
            for dim in DIMENSIONS:
                if hasattr(result.scores.get(dim), "score"):
                    per_dim_predicted[dim].append(result.scores[dim].score)
                else:
                    per_dim_predicted[dim].append(0.0)
                per_dim_actual[dim].append(sample.human_scores.get(dim, 0.0))

        # Compute metrics
        balanced_acc = self.compute_balanced_accuracy(predictions, actuals)
        overall_acc = sum(p == a for p, a in zip(predictions, actuals)) / max(len(predictions), 1)

        # Per-dimension metrics
        per_dimension = {}
        for dim in DIMENSIONS:
            per_dimension[dim] = self.compute_dimension_accuracy(
                dim,
                per_dim_predicted[dim],
                per_dim_actual[dim],
                tolerance=1.0,
            )

        # Confusion matrix
        classes = ["accept", "reject", "borderline"]
        confusion_matrix: dict[str, dict[str, int]] = {c: {c2: 0 for c2 in classes} for c in classes}
        for pred, act in zip(predictions, actuals):
            if act in confusion_matrix and pred in confusion_matrix[act]:
                confusion_matrix[act][pred] += 1

        return CalibrationResult(
            balanced_accuracy=balanced_acc,
            overall_accuracy=overall_acc,
            per_dimension=per_dimension,
            confusion_matrix=confusion_matrix,
            recommendations=recommendations,
            benchmark_name=self.dataset._benchmark_name,
            n_samples=len(self.dataset.samples),
        )

    # ── Metric computations ─────────────────────────────────────────────────

    def compute_balanced_accuracy(self, predicted: list[str], actual: list[str]) -> float:
        """
        Compute balanced accuracy for accept/reject/borderline.

        Balanced accuracy = average of per-class recall.
        """
        classes = ["accept", "reject", "borderline"]
        recalls: list[float] = []

        for cls in classes:
            tp = sum(1 for p, a in zip(predicted, actual) if p == cls and a == cls)
            fn = sum(1 for p, a in zip(predicted, actual) if p != cls and a == cls)
            total_actual = sum(1 for a in actual if a == cls)
            recall = tp / max(total_actual, 1)
            recalls.append(recall)

        return sum(recalls) / len(recalls) if recalls else 0.0

    def compute_dimension_accuracy(
        self,
        dim: str,
        predicted: list[float],
        actual: list[float],
        tolerance: float = 1.0,
    ) -> dict:
        """
        Compute accuracy and MAE for a single scoring dimension.

        Parameters
        ----------
        dim : str
            Dimension name.
        predicted : list[float]
            LLM-predicted scores.
        actual : list[float]
            Human ground-truth scores.
        tolerance : float
            Tolerance for accuracy (e.g., 1.0 means predicted within 1 point is "accurate").

        Returns
        -------
        dict
            {"mae": float, "acc_within_1": float, "acc_within_2": float, "corr": float}
        """
        import math

        n = len(predicted)
        if n == 0:
            return {"mae": float("nan"), "acc_within_1": float("nan"), "acc_within_2": float("nan"), "corr": float("nan")}

        # MAE
        mae = sum(abs(p - a) for p, a in zip(predicted, actual)) / n

        # Accuracy within tolerance
        acc_within_1 = sum(1 for p, a in zip(predicted, actual) if abs(p - a) <= tolerance) / n
        acc_within_2 = sum(1 for p, a in zip(predicted, actual) if abs(p - a) <= 2.0) / n

        # Pearson correlation
        mean_p = sum(predicted) / n
        mean_a = sum(actual) / n
        cov = sum((p - mean_p) * (a - mean_a) for p, a in zip(predicted, actual)) / n
        std_p = math.sqrt(sum((p - mean_p) ** 2 for p in predicted) / n)
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in actual) / n)
        corr = cov / (std_p * std_a) if (std_p * std_a) > 0 else 0.0

        return {
            "mae": round(mae, 3),
            "acc_within_1": round(acc_within_1, 3),
            "acc_within_2": round(acc_within_2, 3),
            "corr": round(corr, 3),
        }

    # ── Reporting ───────────────────────────────────────────────────────────

    def generate_calibration_report(self, result: CalibrationResult) -> str:
        """Generate a human-readable calibration report."""
        lines = [
            "=" * 60,
            "LLM Reviewer Calibration Report",
            "=" * 60,
            f"Benchmark : {result.benchmark_name}",
            f"Samples   : {result.n_samples}",
            "",
            "Overall Metrics",
            "-" * 40,
            f"  Balanced Accuracy : {result.balanced_accuracy:.1%}",
            f"  Overall Accuracy  : {result.overall_accuracy:.1%}",
            "",
            "Confusion Matrix",
            "-" * 40,
            f"  {'Actual':<12} {'Accept':>8} {'Reject':>8} {'Borderline':>10}",
        ]

        for actual_cls in ["accept", "reject", "borderline"]:
            row = result.confusion_matrix.get(actual_cls, {})
            lines.append(
                f"  {actual_cls:<12} "
                f"{row.get('accept', 0):>8} "
                f"{row.get('reject', 0):>8} "
                f"{row.get('borderline', 0):>10}"
            )

        lines.append("")
        lines.append("Per-Dimension Metrics")
        lines.append("-" * 40)
        lines.append(
            f"  {'Dimension':<22} {'MAE':>6} {'±1':>6} {'±2':>6} {'Corr':>6}"
        )
        for dim in DIMENSIONS:
            m = result.per_dimension.get(dim, {})
            label = DIMENSION_LABELS.get(dim, dim)
            lines.append(
                f"  {label:<22} "
                f"{m.get('mae', 0):>6.2f} "
                f"{m.get('acc_within_1', 0):>6.1%} "
                f"{m.get('acc_within_2', 0):>6.1%} "
                f"{m.get('corr', 0):>6.2f}"
            )

        lines.append("")
        lines.append("Per-Sample Predictions")
        lines.append("-" * 40)
        correct_count = 0
        for sample_id, rec in result.recommendations.items():
            status = "✓" if rec["correct"] else "✗"
            if rec["correct"]:
                correct_count += 1
            lines.append(
                f"  [{status}] {sample_id:<12} "
                f"pred={rec['predicted']:<10} "
                f"actual={rec['actual']:<10} "
                f"({rec['venue']}, {rec['year']})"
            )

        lines.append("")
        lines.append(f"Correct: {correct_count}/{result.n_samples} "
                      f"({correct_count / max(result.n_samples, 1):.1%})")
        lines.append("=" * 60)
        return "\n".join(lines)
