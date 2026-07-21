"""
dual_reviewer.py — 对偶评审器（Generator-Evaluator 严格分离）

借鉴 MSc 的 multi-model counsel debate 机制。

核心设计：
1. 双模型独立评审：主审（Claude/DeepSeek Pro）+ 影子审（不同模型）
2. 金融假设压力测试：对经济金融假设进行专项检验
3. 辩论收敛机制：两个评审意见分歧时，生成第三轮综合裁判
4. 评审报告：结构化输出，包含评分、问题列表、改进建议

评审维度（经济金融特化）：
  - 理论贡献 (Theory)
  - 识别策略 (Identification)
  - 数据质量 (Data)
  - 实证严谨性 (Rigor)
  - 经济解释 (Interpretation)
  - 稳健性 (Robustness)
  - 写作质量 (Writing)
  - 创新性 (Novelty)
"""

from __future__ import annotations

__all__ = [
    "ReviewDimension",
    "DimensionScore",
    "ReviewReport",
    "DualReviewer",
]

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ReviewDimension(str, Enum):
    """评审维度。"""
    THEORY = "theory"           # 理论贡献
    IDENTIFICATION = "identification"  # 识别策略
    DATA_QUALITY = "data"       # 数据质量
    EMPIRICAL_RIGOR = "rigor"   # 实证严谨性
    INTERPRETATION = "interpretation"  # 经济解释
    ROBUSTNESS = "robustness"   # 稳健性
    WRITING = "writing"         # 写作质量
    NOVELTY = "novelty"         # 创新性


@dataclass
class DimensionScore:
    """单个维度的评分。"""
    dimension: ReviewDimension
    score: float          # 1-10
    verdict: str          # "strong" / "acceptable" / "weak" / "critical"
    strengths: list[str]
    weaknesses: list[str]
    specific_issues: list[str]  # 具名问题
    suggestions: list[str]


@dataclass
class ReviewReport:
    """完整评审报告。"""
    # 基本信息
    document_type: str       # "paper" / "research_design" / "regression_result"
    target: str              # 论文标题/研究设计名称
    primary_reviewer: str    # 主审模型
    shadow_reviewer: str     # 影子审模型
    timestamp: str

    # 评分
    dimension_scores: list[DimensionScore]
    weighted_score: float    # 加权总分
    hard_floor_passed: bool  # 是否所有维度通过硬地板

    # 评审意见
    primary_review: str      # 主审意见（详细）
    shadow_review: str       # 影子审意见（详细）
    convergence_opinion: str  # 收敛裁判意见

    # 分歧分析
    disagreements: list[dict]  # 分歧点列表

    # 改进建议
    critical_issues: list[str]   # 必须修复
    important_issues: list[str]  # 建议修复
    minor_issues: list[str]      # 可选修复

    # 结论
    verdict: str              # "accept" / "revise" / "reject" / "major_revision"
    confidence: float         # 评审置信度 0-1


# ─── 评审 Prompt 模板 ──────────────────────────────────────────────────────────

FINANCIAL_REVIEW_PROMPT = """你是一名经济金融领域的资深学术评审员。请对以下{doc_type}进行严格评审。

{task_context}

{doc_type_description}

{doc_content}

评审要求：
1. 对每个维度给出 1-10 分（10为最高），并说明评分理由
2. 识别具体的strengths和weaknesses（不要泛泛而谈）
3. 指出具体的问题和修改建议
4. 特别关注：
   - 识别策略的有效性（内生性、因果识别）
   - 数据来源和样本选择
   - 稳健性检验是否充分
   - 经济解释是否符合理论预期
5. 对金融实证特有的问题保持高度敏感（如A股涨跌停T+1、散户占比高等）

请以JSON格式输出评审结果：
```json
{{
  "dimension_scores": [
    {{
      "dimension": "theory|identification|data|rigor|interpretation|robustness|writing|novelty",
      "score": 1-10,
      "verdict": "strong|acceptable|weak|critical",
      "strengths": ["具体优点"],
      "weaknesses": ["具体弱点"],
      "specific_issues": ["具体问题"],
      "suggestions": ["改进建议"]
    }}
  ],
  "overall_review": "详细的文字评审意见，200-500字",
  "critical_issues": ["必须修复的问题"],
  "important_issues": ["建议修复的问题"],
  "minor_issues": ["可选修复的问题"],
  "verdict": "accept|revise|reject|major_revision",
  "confidence": 0.0-1.0
}}
```"""

HYPOTHESIS_PRESSURE_TEST = """你是一名经济金融计量经济学家。请对以下研究假设进行压力测试。

研究假设：
{hypothesis}

研究背景：
{background}

压力测试维度：
1. **平行趋势假设**：DID中处理组和对照组在政策前是否满足平行趋势？
2. **SUTVA假设**：政策冲击是否只通过单一渠道影响结果变量？
3. **预期效应**：个体是否在政策实施前就调整了行为？
4. **溢出效应**：处理组是否影响了对照组？
5. **异质性检验**：处理效应是否在不同子样本中一致？
6. **遗漏变量**：是否存在与政策相关的遗漏变量？
7. **测量误差**：核心变量的测量是否存在系统性偏误？

请输出：
1. 每个维度的通过/不通过/存疑判断
2. 具体的数据检验建议
3. 如果不通过，替代识别策略建议
"""

SHADOW_REVIEW_PROMPT = """你是一名批评性学术审稿人，风格接近RFS/JF的严格评审标准。
请对以下{doc_type}进行"魔鬼辩护"式的批评。

{doc_content}

要求：
1. 找出3-5个最严重的方法论问题
2. 指出文献综述中的遗漏
3. 质疑实证结果的稳健性
4. 评估理论贡献是否充分

输出JSON格式：
```json
{{
  "verdict": "revise|reject|major_revision",
  "critical_arguments": ["具体批评论点"],
  "missing_literature": ["遗漏的重要文献"],
  "robustness_concerns": ["稳健性问题"],
  "contribution_assessment": "理论贡献评估",
  "alternative_explanations": ["替代解释"]
}}
```"""


# ─── 评审执行器 ─────────────────────────────────────────────────────────────

class DualReviewer:
    """对偶评审器。

    Usage:
        reviewer = DualReviewer(
            primary_model="deepseek_pro",
            shadow_model="claude_sonnet",
        )
        report = reviewer.review_paper(paper_text, paper_type="实证论文")
        print(report.weighted_score, report.verdict)
    """

    DIMENSION_WEIGHTS = {
        ReviewDimension.THEORY: 0.10,
        ReviewDimension.IDENTIFICATION: 0.20,   # 识别策略权重最高
        ReviewDimension.DATA_QUALITY: 0.10,
        ReviewDimension.EMPIRICAL_RIGOR: 0.20,
        ReviewDimension.INTERPRETATION: 0.10,
        ReviewDimension.ROBUSTNESS: 0.15,        # 稳健性权重次高
        ReviewDimension.WRITING: 0.05,
        ReviewDimension.NOVELTY: 0.10,
    }

    # 硬地板（任何维度低于此值则必须修改）
    HARD_FLOORS = {
        ReviewDimension.IDENTIFICATION: 6.0,
        ReviewDimension.EMPIRICAL_RIGOR: 6.5,
        ReviewDimension.ROBUSTNESS: 6.0,
        ReviewDimension.DATA_QUALITY: 5.5,
    }

    def __init__(
        self,
        primary_model: str = "deepseek_pro",
        shadow_model: str = "claude_sonnet",
        llm_call_fn: callable = None,
    ):
        self.primary_model = primary_model
        self.shadow_model = shadow_model
        self._llm = llm_call_fn  # 注入LLM调用函数

    def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        """调用LLM（需注入实现）。"""
        if self._llm:
            return self._llm(model=model, system=system_prompt, user=user_prompt, temperature=temperature)
        # Fallback: 返回格式提示
        return json.dumps({
            "dimension_scores": [],
            "overall_review": f"[Mock review from {model}]",
            "critical_issues": [],
            "important_issues": [],
            "minor_issues": [],
            "verdict": "revise",
            "confidence": 0.5,
        })

    def review_paper(
        self,
        paper_content: str,
        *,
        paper_title: str = "Untitled",
        paper_type: str = "实证论文",
        include_hypothesis_test: bool = True,
    ) -> ReviewReport:
        """评审一篇学术论文。"""
        now = datetime.now().isoformat()

        # 类型描述
        type_descriptions = {
            "实证论文": "这是一篇金融/经济实证研究论文，应包含：引言（研究贡献）、文献综述与假说推导、研究设计（数据、变量、识别策略）、实证结果、稳健性检验、结论与启示。",
            "研究设计": "这是一份研究设计方案，应包含：研究问题、文献基础、识别策略、数据来源、变量定义、预期结果。",
            "回归结果": "这是一份实证回归结果，应包含：回归表格、系数解读、控制变量、稳健性检验。",
        }
        type_desc = type_descriptions.get(paper_type, type_descriptions["实证论文"])

        # 并行执行主审和影子审
        primary_prompt = FINANCIAL_REVIEW_PROMPT.format(
            doc_type="学术论文",
            doc_type_description=type_desc,
            doc_content=paper_content,
            task_context=f"论文标题：{paper_title}",
        )

        shadow_prompt = SHADOW_REVIEW_PROMPT.format(
            doc_type="论文",
            doc_content=paper_content,
        )

        # 调用两个模型（并行）
        try:
            primary_raw = self._call_llm(self.primary_model, "", primary_prompt, temperature=0.3)
            shadow_raw = self._call_llm(self.shadow_model, "", shadow_prompt, temperature=0.4)
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            primary_raw = json.dumps({"dimension_scores": [], "overall_review": str(e), "verdict": "revise"})
            shadow_raw = json.dumps({"critical_arguments": [], "verdict": "revise"})

        # 解析
        primary_data = self._parse_json(primary_raw)
        shadow_data = self._parse_json(shadow_raw)

        # 构建维度评分
        dim_scores = self._build_dimension_scores(primary_data)

        # 计算加权总分
        weighted = self._compute_weighted_score(dim_scores)

        # 检查硬地板
        hard_floor_passed = all(
            ds.score >= self.HARD_FLOORS.get(ds.dimension, 1.0)
            for ds in dim_scores
        )

        # 分歧分析
        disagreements = self._analyze_disagreements(primary_data, shadow_data)

        # 收敛裁判
        convergence = self._generate_convergence(primary_data, shadow_data, disagreements)

        # 归类问题
        critical, important, minor = self._classify_issues(primary_data, shadow_data)

        # 最终判定
        verdict = self._compute_verdict(
            weighted, hard_floor_passed, dim_scores,
            len(critical), len(disagreements)
        )

        return ReviewReport(
            document_type=paper_type,
            target=paper_title,
            primary_reviewer=self.primary_model,
            shadow_reviewer=self.shadow_model,
            timestamp=now,
            dimension_scores=dim_scores,
            weighted_score=weighted,
            hard_floor_passed=hard_floor_passed,
            primary_review=primary_data.get("overall_review", ""),
            shadow_review=shadow_data.get("overall_review", shadow_data.get("critical_arguments", [])),
            convergence_opinion=convergence,
            disagreements=disagreements,
            critical_issues=critical,
            important_issues=important,
            minor_issues=minor,
            verdict=verdict,
            confidence=primary_data.get("confidence", 0.5),
        )

    def pressure_test_hypothesis(
        self,
        hypothesis: str,
        background: str = "",
    ) -> dict:
        """对研究假设进行压力测试。"""
        prompt = HYPOTHESIS_PRESSURE_TEST.format(
            hypothesis=hypothesis,
            background=background or "无背景信息",
        )
        try:
            raw = self._call_llm(self.primary_model, "", prompt, temperature=0.3)
            data = self._parse_json(raw)
            return data
        except Exception as e:
            logger.warning(f"Hypothesis pressure test failed: {e}")
            return {"error": str(e)}

    def _build_dimension_scores(self, data: dict) -> list[DimensionScore]:
        """从原始JSON构建维度评分对象。"""
        scores = []
        raw_scores = data.get("dimension_scores", [])

        for raw in raw_scores:
            try:
                dim = ReviewDimension(raw.get("dimension", "writing"))
                score = float(raw.get("score", 5))
                verdict_map = {
                    "strong": "strong", "acceptable": "acceptable",
                    "weak": "weak", "critical": "critical",
                }
                scores.append(DimensionScore(
                    dimension=dim,
                    score=score,
                    verdict=verdict_map.get(raw.get("verdict", ""), "acceptable"),
                    strengths=raw.get("strengths", []),
                    weaknesses=raw.get("weaknesses", []),
                    specific_issues=raw.get("specific_issues", []),
                    suggestions=raw.get("suggestions", []),
                ))
            except (ValueError, KeyError):
                continue

        # 补全缺失维度（默认5分）
        for dim in ReviewDimension:
            if not any(s.dimension == dim for s in scores):
                scores.append(DimensionScore(
                    dimension=dim, score=5.0, verdict="acceptable",
                    strengths=[], weaknesses=[], specific_issues=[], suggestions=[],
                ))
        return scores

    def _compute_weighted_score(self, dim_scores: list[DimensionScore]) -> float:
        """计算加权总分。"""
        total = 0.0
        for ds in dim_scores:
            w = self.DIMENSION_WEIGHTS.get(ds.dimension, 0.05)
            total += w * ds.score
        return round(total, 2)

    def _analyze_disagreements(self, primary: dict, shadow: dict) -> list[dict]:
        """分析两个评审之间的分歧。"""
        disagreements = []

        # 检查关键问题是否一致
        set(primary.get("critical_issues", []))
        set(shadow.get("critical_arguments", []))

        # 评分分歧
        for raw in primary.get("dimension_scores", []):
            dim = raw.get("dimension", "")
            if raw.get("verdict") == "weak" and dim not in ["writing", "novelty"]:
                disagreements.append({
                    "type": "low_dimension",
                    "dimension": dim,
                    "issue": raw.get("weaknesses", ["未知问题"]),
                    "severity": "high",
                })

        # 总体判定分歧
        p_verdict = primary.get("verdict", "revise")
        s_verdict = shadow.get("verdict", "revise")
        if p_verdict != s_verdict:
            disagreements.append({
                "type": "verdict_mismatch",
                "primary": p_verdict,
                "shadow": s_verdict,
                "severity": "medium",
            })

        return disagreements

    def _generate_convergence(
        self, primary: dict, shadow: dict, disagreements: list[dict],
    ) -> str:
        """生成收敛裁判意见。"""
        if not disagreements:
            return "主审和影子审意见基本一致，无明显分歧。"

        lines = ["## 收敛裁判意见", ""]
        lines.append(f"发现 {len(disagreements)} 个分歧点。")

        for i, d in enumerate(disagreements, 1):
            if d["type"] == "verdict_mismatch":
                lines.append(f"\n分歧{i}（总体判定）: 主审={d['primary']}, 影子审={d['shadow']}")
                lines.append("→ 裁判：倾向于更严格的评审标准，建议按较低版本判定。")
            else:
                lines.append(f"\n分歧{i}（{d.get('dimension', 'unknown')}）: {d.get('issue', '')}")
                lines.append(f"  严重程度: {d.get('severity', 'unknown')}")

        return "\n".join(lines)

    def _classify_issues(
        self, primary: dict, shadow: dict,
    ) -> tuple[list[str], list[str], list[str]]:
        """将问题分为 critical / important / minor。"""
        critical = list(primary.get("critical_issues", []))
        shadow_critical = shadow.get("critical_arguments", [])
        critical.extend(shadow_critical[:2])  # 影子审的前两个critical

        important = list(primary.get("important_issues", []))
        important.extend(shadow.get("robustness_concerns", [])[:2])

        minor = list(primary.get("minor_issues", []))

        # 去重
        critical = list(dict.fromkeys(critical))
        important = list(dict.fromkeys(important))
        minor = list(dict.fromkeys(minor))

        return critical, important, minor

    def _compute_verdict(
        self,
        weighted: float,
        hard_floor_passed: bool,
        dim_scores: list[DimensionScore],
        n_critical: int,
        n_disagreements: int,
    ) -> str:
        """计算最终判定。"""
        if not hard_floor_passed:
            return "major_revision"
        if n_critical > 3:
            return "major_revision"
        if weighted < 6.0:
            return "revise"
        if n_disagreements > 5:
            return "revise"
        if weighted >= 7.5:
            return "accept"
        return "revise"

    def _parse_json(self, raw: str) -> dict:
        """从LLM输出中解析JSON。"""
        try:
            # 尝试提取代码块中的JSON
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
            if match:
                return json.loads(match.group(1))
            # 直接解析
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def generate_review_markdown(self, report: ReviewReport) -> str:
        """生成 Markdown 格式的评审报告。"""
        lines = [
            f"# 学术评审报告",
            f"",
            f"**文档**: {report.target}",
            f"**类型**: {report.document_type}",
            f"**时间**: {report.timestamp}",
            f"**评审者**: 主审={report.primary_reviewer} / 影子审={report.shadow_reviewer}",
            f"",
            f"## 综合评分",
            f"",
            f"| 维度 | 分数 | 判定 |",
            f"|------|------|------|",
        ]

        for ds in report.dimension_scores:
            verdict_icon = {"strong": "🟢", "acceptable": "🟡", "weak": "🟠", "critical": "🔴"}[ds.verdict]
            lines.append(f"| {ds.dimension.value} | {ds.score:.1f}/10 | {verdict_icon} {ds.verdict} |")

        lines.extend([
            f"",
            f"**加权总分**: {report.weighted_score:.2f}/10",
            f"**硬地板**: {'✅ 通过' if report.hard_floor_passed else '❌ 未通过'}",
            f"**最终判定**: {'✅ 接收' if report.verdict == 'accept' else '🔄 修改后接收' if report.verdict == 'major_revision' else '⚠️ 需要修改'}",
            f"",
            f"## 主审意见",
            f"",
            f"{report.primary_review}",
        ])

        if report.shadow_review and isinstance(report.shadow_review, str):
            lines.extend([
                f"",
                f"## 影子审意见（魔鬼辩护）",
                f"",
                f"{report.shadow_review}",
            ])

        if report.convergence_opinion:
            lines.extend([
                f"",
                f"## 收敛裁判",
                f"",
                f"{report.convergence_opinion}",
            ])

        if report.critical_issues:
            lines.extend([
                f"",
                f"## 必须修复的问题",
                f"",
            ])
            for issue in report.critical_issues:
                lines.append(f"- ❌ {issue}")

        if report.important_issues:
            lines.extend([
                f"",
                f"## 建议修复的问题",
                f"",
            ])
            for issue in report.important_issues:
                lines.append(f"- ⚠️ {issue}")

        if report.minor_issues:
            lines.extend([
                f"",
                f"## 可选优化",
                f"",
            ])
            for issue in report.minor_issues:
                lines.append(f"- 💡 {issue}")

        return "\n".join(lines)


if __name__ == "__main__":
    reviewer = DualReviewer(primary_model="deepseek_pro", shadow_model="claude_sonnet")
    print("DualReviewer initialized")
    print(f"Weights: {reviewer.DIMENSION_WEIGHTS}")
    print(f"Hard floors: {reviewer.HARD_FLOORS}")
