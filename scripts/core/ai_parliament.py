"""AI Parliament - Multi-Model Debate for Academic Review.

Reference: FWMA's AI Parliament approach where three AI models debate
each paper with transparent, auditable justifications.

This module implements:
- Chair agent - Opens debate, summarizes, final score (default: Gemini)
- Member Engineering - Architecture, reproducibility, methodology (default: Claude)
- Member Finance/Theory - Financial intuition, modeling validity (default: GPT)

Model names are configurable via environment variables:
  PARLIAMENT_CHAIR_MODEL      (default: gemini-2.5-flash-preview-05-20)
  PARLIAMENT_ENGINEERING_MODEL (default: claude-3-opus-latest)
  PARLIAMENT_FINANCE_MODEL    (default: gpt-4o)
"""

from __future__ import annotations

__all__ = [
    "MemberType",
    "MemberConfig",
    "DebateRound",
    "RebuttalRound",
    "Verdict",
    "BaseMemberAgent",
    "ChairAgent",
    "EngineeringMemberAgent",
    "FinanceMemberAgent",
    "MemberMethodologyAgent",
    "MemberStatisticsAgent",
    "MemberWritingAgent",
    "AIParliament",
    "AIParliamentHITLIntegration",
    "MEMBER_CONFIGS",
    "main",
]

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_SPECIALIZED_AGENTS_AVAILABLE = False
try:
    from scripts.core.specialized_agents import run_all_agents, AgentReviewResult
    _SPECIALIZED_AGENTS_AVAILABLE = True
except ImportError:
    pass


# ─── Environment-based Model Resolution ─────────────────────────────────────────


def _resolve_model(env_var: str, default: str) -> str:
    """Resolve model name from environment variable, falling back to default."""
    value = os.environ.get(env_var, "").strip()
    if value:
        logger.info(f"[AIParliament] {env_var}={value}")
        return value
    return default


# ─── Member Types ────────────────────────────────────────────────────────────────


class MemberType(Enum):
    """Types of parliament members."""
    CHAIR = "chair"
    MEMBER_ENGINEERING = "member_engineering"
    MEMBER_FINANCE = "member_finance"
    MEMBER_METHODOLOGY = "methodology"  # NEW - econometric methodology
    MEMBER_STATISTICS = "statistics"    # NEW - statistical power and testing
    MEMBER_WRITING = "writing"          # NEW - writing quality and LaTeX


@dataclass
class MemberConfig:
    """Configuration for a parliament member."""
    member_type: MemberType
    name: str
    role: str
    model: str
    expertise: list[str]
    perspective: str


@dataclass
class DebateRound:
    """A single round of debate."""
    round_number: int
    speaker: MemberType
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RebuttalRound:
    """A single rebuttal round."""
    round_num: int
    member_type: MemberType
    response_to_summary: str
    strength: str  # "strong", "moderate", "weak"


@dataclass
class Verdict:
    """Final verdict from the parliament."""
    score: float  # 0-5
    recommendation: str  # "accept", "revision", "reject"
    summary: str
    key_strengths: list[str]
    key_weaknesses: list[str]
    debate_rounds: list[DebateRound] = field(default_factory=list)
    # New fields
    rebuttal_rounds: list[RebuttalRound] = field(default_factory=list)
    disputed: bool = False  # True if any two members differ by > 1.0
    all_arguments: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Compute disputed flag based on debate round scores
        # This is a simplified check; actual score tracking happens in debate()
        pass


# ─── Member Configurations ──────────────────────────────────────────────────────


MEMBER_CONFIGS: dict[MemberType, MemberConfig] = {
    MemberType.CHAIR: MemberConfig(
        member_type=MemberType.CHAIR,
        name="主持人",
        role="议会主持人，引导辩论，总结观点，判定最终分数",
        model=_resolve_model("PARLIAMENT_CHAIR_MODEL", "gemini-2.5-flash-preview-05-20"),
        expertise=["学术评审", "研究方法论", "跨领域综合"],
        perspective="综合评估研究贡献、方法和影响力",
    ),
    MemberType.MEMBER_ENGINEERING: MemberConfig(
        member_type=MemberType.MEMBER_ENGINEERING,
        name="工程视角委员",
        role="从工程和实践角度评审，关注架构设计、可复现性和实验质量",
        model=_resolve_model("PARLIAMENT_ENGINEERING_MODEL", "claude-3-opus-latest"),
        expertise=["机器学习系统", "实验设计", "代码质量", "可复现性"],
        perspective="工程视角：技术实现是否扎实，实验是否可复现，方法是否高效",
    ),
    MemberType.MEMBER_FINANCE: MemberConfig(
        member_type=MemberType.MEMBER_FINANCE,
        name="金融理论委员",
        role="从金融和经济理论角度评审，关注建模合理性和实际意义",
        model=_resolve_model("PARLIAMENT_FINANCE_MODEL", "gpt-4o"),
        expertise=["金融工程", "计量经济学", "资产定价", "风险管理"],
        perspective="理论视角：理论是否扎实，建模是否合理，应用价值如何",
    ),
    MemberType.MEMBER_METHODOLOGY: MemberConfig(
        member_type=MemberType.MEMBER_METHODOLOGY,
        name="方法论委员",
        role="专注于因果推断方法论评审：识别策略、平行趋势、SE聚类",
        model=_resolve_model("PARLIAMENT_METHODOLOGY_MODEL", "claude-3-opus-latest"),
        expertise=["计量经济学", "因果推断", "DID/IV/RDD", "合成控制"],
        perspective="方法论视角：识别策略是否可靠，平行趋势假设是否检验，SUTVA是否满足",
    ),
    MemberType.MEMBER_STATISTICS: MemberConfig(
        member_type=MemberType.MEMBER_STATISTICS,
        name="统计委员",
        role="专注于统计功效、置信区间、等价性检验和多重检验校正",
        model=_resolve_model("PARLIAMENT_STATISTICS_MODEL", "gpt-4o"),
        expertise=["假设检验", "统计功效", "置信区间", "FDR校正", "TOST"],
        perspective="统计视角：CI宽度与系数幅度关系，统计功效，等价性检验，多重比较校正",
    ),
    MemberType.MEMBER_WRITING: MemberConfig(
        member_type=MemberType.MEMBER_WRITING,
        name="写作质量委员",
        role="专注于写作质量、LaTeX结构、图表清晰度和学术规范",
        model=_resolve_model("PARLIAMENT_WRITING_MODEL", "gemini-2.5-flash-preview-05-20"),
        expertise=["学术写作", "LaTeX排版", "图表设计", "学术规范"],
        perspective="写作视角：代词明确性、时态一致性、图表引用格式、表格标题、章节过渡",
    ),
}


# ─── Base Member Agent ──────────────────────────────────────────────────────────


class BaseMemberAgent(ABC):
    """Base class for parliament member agents."""

    def __init__(self, config: MemberConfig, gateway=None):
        self.config = config
        self.gateway = gateway

    @abstractmethod
    async def opening_statement(self, paper: dict) -> str:
        """Generate opening statement for the debate."""
        raise NotImplementedError

    @abstractmethod
    async def respond(self, context: dict) -> str:
        """Respond to other members' arguments."""
        raise NotImplementedError

    @abstractmethod
    async def final_statement(self, context: dict) -> str:
        """Generate final statement and summary."""
        raise NotImplementedError


class ChairAgent(BaseMemberAgent):
    """Chair agent - orchestrates the debate and produces final verdict."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.CHAIR], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Chair opens the debate."""
        prompt = f"""作为议会主持人，请对以下研究论文进行初步评审。

论文标题: {paper.get('title', 'N/A')}
摘要: {paper.get('abstract', paper.get('content', 'N/A')[:500])}

请从以下维度给出初步评估：
1. 研究问题的清晰度
2. 方法论的适当性
3. 潜在贡献

请以主持人的身份发表开场陈述。"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def respond(self, context: dict) -> str:
        """Chair summarizes and keeps debate on track."""
        engineering_arg = context.get("engineering_arg", "")
        finance_arg = context.get("finance_arg", "")
        round_num = context.get("round", 1)

        prompt = f"""作为议会主持人，请对第{round_num}轮辩论进行总结。

工程视角委员观点:
{engineering_arg[:500]}

金融理论委员观点:
{finance_arg[:500]}

请总结双方核心论点，指出分歧点，并引导进入下一轮讨论。"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Chair produces final verdict."""
        all_arguments = context.get("all_arguments", [])
        scores = context.get("individual_scores", {})

        prompt = f"""作为议会主持人，请综合所有讨论，给出最终裁决。

各委员评分:
{json.dumps(scores, ensure_ascii=False, indent=2)}

综合论点摘要:
{json.dumps(all_arguments[:3], ensure_ascii=False, indent=2) if all_arguments else '无'}

请给出:
1. 最终评分 (0-5)
2. 建议 (accept/revision/reject)
3. 核心优势 (最多3点)
4. 核心不足 (最多3点)
5. 综合评价

请以JSON格式输出。"""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            # Gateway error during final_statement — propagate structured error
            return {
                "score": None,
                "recommendation": "error",
                "summary": f"{response.get('error_type', 'Unknown')}: {response.get('error', 'LLM调用失败')}",
                "key_strengths": [],
                "key_weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {
                "score": None,
                "recommendation": "error",
                "summary": "未配置LLM网关",
                "key_strengths": [],
                "key_weaknesses": [],
                "_error": True,
                "_error_message": "LLM gateway not configured",
            }
        return self._parse_verdict(response, all_arguments)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,  # Use member's configured model
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_verdict(self, response: str, arguments: list) -> dict:
        """Parse verdict from response."""
        # Detect LLM failure markers to avoid silent degradation to score=3.0
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM verdict generation failed: {response}")
            return {
                "score": None,
                "recommendation": "error",
                "summary": response,
                "key_strengths": [],
                "key_weaknesses": [],
                "_error": True,
                "_error_message": response,
            }

        # Try to extract JSON from response
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score", 3.0),
                    "recommendation": data.get("recommendation", "revision"),
                    "summary": data.get("summary", response[:500]),
                    "key_strengths": data.get("key_strengths", [])[:3],
                    "key_weaknesses": data.get("key_weaknesses", [])[:3],
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse verdict JSON, falling back: {response[:100]}")
        return {
            "score": None,
            "recommendation": "revision",
            "summary": response[:500],
            "key_strengths": [],
            "key_weaknesses": [],
            "_error": True,
            "_error_message": "JSON解析失败",
        }


class EngineeringMemberAgent(BaseMemberAgent):
    """Engineering perspective member - evaluates technical quality."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.MEMBER_ENGINEERING], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Engineering perspective on the paper."""
        prompt = f"""作为工程视角委员，请评估以下论文的技术质量。

论文标题: {paper.get('title', 'N/A')}
内容摘要: {paper.get('abstract', paper.get('content', 'N/A')[:800])}

请从工程视角评估：
1. **方法论**: 实验设计是否严谨？基线是否充分？
2. **可复现性**: 描述是否清晰？代码/数据是否可获取？
3. **技术贡献**: 创新性如何？实现是否高效？
4. **评估指标**: 是否适当？是否全面？

请给出具体的优缺点评价。"""
        return await self._generate_response(prompt)

    async def respond(self, context: dict) -> str:
        """Respond to other perspectives."""
        chair_summary = context.get("chair_summary", "")
        finance_arg = context.get("finance_arg", "")

        prompt = f"""作为工程视角委员，请对以下论点进行回应。

主持人的总结:
{chair_summary[:300]}

金融理论委员的观点:
{finance_arg[:300]}

请从工程角度：
1. 同意或反驳哪些观点
2. 补充工程实践中的重要考量
3. 对论文的最终评价"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Engineering member's final evaluation."""
        prompt = f"""作为工程视角委员，请给出最终评分和理由。

论文: {context.get('paper_title', 'N/A')}
之前论点: {context.get('previous_arguments', '')[:500]}

请给出:
1. 技术质量评分 (0-5)
2. 主要技术优势 (1-2点)
3. 主要技术不足 (1-2点)
4. 简短理由

JSON格式输出。"""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            # Gateway error — propagate structured error
            return {
                "score": None,
                "strengths": [],
                "weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "LLM gateway not configured"}
        return self._parse_score(response)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_score(self, response: str) -> dict:
        # Detect LLM failure markers
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM score generation failed: {response}")
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": response}

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score"),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse score JSON: {response[:100]}")
        return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "JSON解析失败"}


class FinanceMemberAgent(BaseMemberAgent):
    """Finance/Theory perspective member - evaluates theoretical soundness."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.MEMBER_FINANCE], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Finance perspective on the paper."""
        prompt = f"""作为金融理论委员，请评估以下论文的理论深度和实际价值。

论文标题: {paper.get('title', 'N/A')}
内容摘要: {paper.get('abstract', paper.get('content', 'N/A')[:800])}

请从理论视角评估：
1. **理论基础**: 理论假设是否合理？文献综述是否充分？
2. **建模方法**: 模型设定是否正确？实证策略是否适当？
3. **经济直觉**: 结果是否符合经济学直觉？解释是否合理？
4. **实际意义**: 研究对实践有何启示？局限性如何？

请给出具体的优缺点评价。"""
        return await self._generate_response(prompt)

    async def respond(self, context: dict) -> str:
        """Respond to other perspectives."""
        chair_summary = context.get("chair_summary", "")
        engineering_arg = context.get("engineering_arg", "")

        prompt = f"""作为金融理论委员，请对以下论点进行回应。

主持人的总结:
{chair_summary[:300]}

工程视角委员的观点:
{engineering_arg[:300]}

请从理论角度：
1. 同意或反驳哪些观点
2. 补充理论层面的重要考量
3. 对论文的最终评价"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Finance member's final evaluation."""
        prompt = f"""作为金融理论委员，请给出最终评分和理由。

论文: {context.get('paper_title', 'N/A')}
之前论点: {context.get('previous_arguments', '')[:500]}

请给出:
1. 理论质量评分 (0-5)
2. 主要理论优势 (1-2点)
3. 主要理论不足 (1-2点)
4. 简短理由

JSON格式输出。"""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            return {
                "score": None,
                "strengths": [],
                "weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "LLM gateway not configured"}
        return self._parse_score(response)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_score(self, response: str) -> dict:
        # Detect LLM failure markers
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM score generation failed: {response}")
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": response}

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score"),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse score JSON: {response[:100]}")
        return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "JSON解析失败"}


class MemberMethodologyAgent(BaseMemberAgent):
    """Reviews econometric methodology: identification strategy, parallel trends, SE clustering."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.MEMBER_METHODOLOGY], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Methodology perspective on the paper."""
        prompt = f"""You are a methodology reviewer specializing in econometric causal inference.
Review this paper focusing ONLY on econometric methodology.

Paper Title: {paper.get('title', 'N/A')}
Abstract: {paper.get('abstract', paper.get('content', 'N/A')[:800])}

Please evaluate from the methodology perspective:
1. **Identification Strategy**: Is the causal identification strategy clearly stated and appropriate?
   - What is the key identifying assumption?
   - Is it plausible given the context?
2. **Parallel Trends**:
   - Are pre-treatment trends tested and visualized?
   - Is the event study specification correctly specified?
3. **SUTVA Compliance**:
   - No anticipation assumption - is it justified?
   - No spillover effects - is this plausible?
4. **Standard Error Clustering**:
   - Are SEs clustered appropriately (firm/time/industry)?
   - Are there arguments for alternative clustering?

Please provide specific strengths and weaknesses."""
        return await self._generate_response(prompt)

    async def respond(self, context: dict) -> str:
        """Respond to other perspectives on methodology."""
        chair_summary = context.get("chair_summary", "")
        engineering_arg = context.get("engineering_arg", "")
        finance_arg = context.get("finance_arg", "")

        prompt = f"""As the methodology reviewer, please respond to the following arguments.

Chair summary:
{chair_summary[:300]}

Engineering perspective:
{engineering_arg[:300]}

Finance/Theory perspective:
{finance_arg[:300]}

Please:
1. Agree or disagree with methodological claims
2. Address any econometric concerns raised
3. Provide your assessment of the identification strategy"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Methodology member's final evaluation."""
        prompt = f"""As the methodology reviewer, please provide your final score and reasoning.

Paper: {context.get('paper_title', 'N/A')}
Previous arguments: {context.get('previous_arguments', '')[:500]}

Please provide:
1. Methodology quality score (0-5)
2. Main methodological strengths (1-2 points)
3. Main methodological concerns (1-2 points)
4. Brief justification

JSON format output."""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            return {
                "score": None,
                "strengths": [],
                "weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "LLM gateway not configured"}
        return self._parse_score(response)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_score(self, response: str) -> dict:
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM score generation failed: {response}")
            return {"score": 0.0, "strengths": [], "weaknesses": [], "_error": True, "_error_message": response}

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score"),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse score JSON: {response[:100]}")
        return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "JSON解析失败"}


class MemberStatisticsAgent(BaseMemberAgent):
    """Reviews statistical power, CI width, equivalence testing."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.MEMBER_STATISTICS], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Statistics perspective on the paper."""
        prompt = f"""You are a statistics reviewer.
Review this paper focusing ONLY on statistical rigor.

Paper Title: {paper.get('title', 'N/A')}
Abstract: {paper.get('abstract', paper.get('content', 'N/A')[:800])}

Please evaluate from the statistics perspective:
1. **Confidence Interval Width**:
   - Is the CI width reasonable relative to coefficient magnitude?
   - Are the results economically meaningful or just statistically significant?
2. **Statistical Power**:
   - Was power analysis conducted?
   - Are the sample sizes adequate?
3. **TOST Equivalence Testing**:
   - Were equivalence margins pre-specified?
   - Is TOST/equivalence testing used for demonstrating "no effect"?
4. **Multiple Testing Corrections**:
   - FDR/Bonferroni corrections for multiple outcomes?
   - Family-wise error rate control?
5. **Effect Size Interpretation**:
   - Cohen's d / partial R² reported?
   - Practical vs statistical significance discussed?

Please provide specific strengths and weaknesses."""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def respond(self, context: dict) -> str:
        """Respond to other perspectives on statistics."""
        chair_summary = context.get("chair_summary", "")
        engineering_arg = context.get("engineering_arg", "")
        finance_arg = context.get("finance_arg", "")

        prompt = f"""As the statistics reviewer, please respond to the following arguments.

Chair summary:
{chair_summary[:300]}

Engineering perspective:
{engineering_arg[:300]}

Finance/Theory perspective:
{finance_arg[:300]}

Please:
1. Address any statistical concerns raised
2. Comment on effect size and practical significance
3. Provide your assessment of statistical rigor"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Statistics member's final evaluation."""
        prompt = f"""As the statistics reviewer, please provide your final score and reasoning.

Paper: {context.get('paper_title', 'N/A')}
Previous arguments: {context.get('previous_arguments', '')[:500]}

Please provide:
1. Statistical quality score (0-5)
2. Main statistical strengths (1-2 points)
3. Main statistical concerns (1-2 points)
4. Brief justification

JSON format output."""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            return {
                "score": None,
                "strengths": [],
                "weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "LLM gateway not configured"}
        return self._parse_score(response)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_score(self, response: str) -> dict:
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM score generation failed: {response}")
            return {"score": 0.0, "strengths": [], "weaknesses": [], "_error": True, "_error_message": response}

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score"),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse score JSON: {response[:100]}")
        return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "JSON解析失败"}


class MemberWritingAgent(BaseMemberAgent):
    """Reviews writing quality, LaTeX structure, figure clarity."""

    def __init__(self, gateway=None):
        super().__init__(MEMBER_CONFIGS[MemberType.MEMBER_WRITING], gateway)

    async def opening_statement(self, paper: dict) -> str:
        """Writing quality perspective on the paper."""
        prompt = f"""You are a writing quality reviewer.
Review this paper focusing ONLY on writing quality and presentation.

Paper Title: {paper.get('title', 'N/A')}
Abstract: {paper.get('abstract', paper.get('content', 'N/A')[:800])}

Please evaluate from the writing quality perspective:
1. **Ambiguous Pronouns**:
   - Are subject references clear?
   - Can readers always identify what "this", "that", "it" refer to?
2. **Tense Consistency**:
   - Present tense for results vs past tense for methods?
   - Consistent throughout?
3. **Figure Reference Formatting**:
   - Are figures referenced as "Figure 1" or "figure 1"?
   - Consistent LaTeX-style references (\ref{{fig:xxx}})?
4. **Table Captions**:
   - Do tables have clear, self-explanatory captions?
   - Are all columns/variables defined?
5. **Section Transitions**:
   - Do paragraphs flow logically?
   - Are there clear signposting sentences?
6. **Novelty Claims**:
   - Are novelty claims supported and specific?
   - No overclaiming contributions?

Please provide specific strengths and weaknesses."""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def respond(self, context: dict) -> str:
        """Respond to other perspectives on writing quality."""
        chair_summary = context.get("chair_summary", "")
        engineering_arg = context.get("engineering_arg", "")
        finance_arg = context.get("finance_arg", "")

        prompt = f"""As the writing quality reviewer, please respond to the following arguments.

Chair summary:
{chair_summary[:300]}

Engineering perspective:
{engineering_arg[:300]}

Finance/Theory perspective:
{finance_arg[:300]}

Please:
1. Address any writing quality concerns raised
2. Comment on presentation clarity
3. Provide your assessment of overall readability"""
        result = await self._generate_response(prompt)
        if isinstance(result, dict):
            return f"[ERROR: {result.get('error_type', 'Unknown')} — {result.get('error', 'LLM调用失败')[:80]}]"
        if result is None:
            return "[WARNING: 未配置LLM网关]"
        return result

    async def final_statement(self, context: dict) -> dict:
        """Writing member's final evaluation."""
        prompt = f"""As the writing quality reviewer, please provide your final score and reasoning.

Paper: {context.get('paper_title', 'N/A')}
Previous arguments: {context.get('previous_arguments', '')[:500]}

Please provide:
1. Writing quality score (0-5)
2. Main writing strengths (1-2 points)
3. Main writing concerns (1-2 points)
4. Brief justification

JSON format output."""
        response = await self._generate_response(prompt)
        if isinstance(response, dict):
            return {
                "score": None,
                "strengths": [],
                "weaknesses": [],
                "_error": True,
                "_error_message": response.get("error", str(response)),
                "_error_type": response.get("error_type"),
            }
        if response is None:
            return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "LLM gateway not configured"}
        return self._parse_score(response)

    async def _generate_response(self, prompt: str) -> str | dict | None:
        """Generate response using gateway or fallback.

        Returns
        -------
        str | dict | None
            On success: string content.
            On gateway error: dict with None scores and error info.
            On no gateway: None (caller handles gracefully).
        """
        if self.gateway:
            try:
                result = self.gateway.generate(
                    prompt,
                    task_hint="academic_review",
                    model=self.config.model,
                )
                return result.response
            except Exception as exc:
                logger.warning(f"[{self.config.member_type.value}] Generation failed: {exc}")
                return {
                    "content": "",
                    "overall": None,
                    "methodology": None,
                    "novelty": None,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
        return None

    def _parse_score(self, response: str) -> dict:
        if response.startswith("[ERROR:") or response.startswith("[WARNING:"):
            logger.error(f"LLM score generation failed: {response}")
            return {"score": 0.0, "strengths": [], "weaknesses": [], "_error": True, "_error_message": response}

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("score"),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "_error": False,
                }
        except Exception:
            pass

        logger.warning(f"Could not parse score JSON: {response[:100]}")
        return {"score": None, "strengths": [], "weaknesses": [], "_error": True, "_error_message": "JSON解析失败"}


# ─── AI Parliament ──────────────────────────────────────────────────────────────


class AIParliament:
    """
    AI Parliament for academic paper review.

    Reference: FWMA's AI Parliament approach with transparent,
    auditable multi-model debate scoring.

    Six models debate each paper:
    - Chair (Gemini) - Opens debate, summarizes, final verdict
    - Member Engineering (Claude) - Technical quality
    - Member Finance (GPT) - Theoretical soundness
    - Member Methodology (Claude) - Econometric methodology
    - Member Statistics (GPT) - Statistical power and testing
    - Member Writing (Gemini) - Writing quality and LaTeX
    """

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.max_rounds = int(os.environ.get("PARLIAMENT_MAX_ROUNDS", "3"))

        # Initialize all 6 members
        self.members = {
            MemberType.CHAIR: ChairAgent(gateway),
            MemberType.MEMBER_ENGINEERING: EngineeringMemberAgent(gateway),
            MemberType.MEMBER_FINANCE: FinanceMemberAgent(gateway),
            MemberType.MEMBER_METHODOLOGY: MemberMethodologyAgent(gateway),
            MemberType.MEMBER_STATISTICS: MemberStatisticsAgent(gateway),
            MemberType.MEMBER_WRITING: MemberWritingAgent(gateway),
        }

    async def debate(
        self,
        paper: dict,
        rounds: int | None = None,
    ) -> Verdict:
        """
        Run the complete debate process.

        Parameters
        ----------
        paper : dict
            Paper information with title, abstract/content.
        rounds : int | None
            Number of debate rounds. Defaults to self.max_rounds (from PARLIAMENT_MAX_ROUNDS env var).

        Returns
        -------
        Verdict
            Final verdict with score and debate transcript.
        """
        if rounds is None:
            rounds = self.max_rounds

        debate_rounds: list[DebateRound] = []
        all_arguments: list[str] = []
        individual_scores: dict[str, float] = {}

        # Round 0: Opening statements (PARALLEL execution)
        logger.info("Starting opening statements (parallel)...")
        opening_tasks = {
            member_type: member.opening_statement(paper)
            for member_type, member in self.members.items()
        }

        # Execute all opening statements in parallel
        import asyncio
        try:
            opening_results = await asyncio.wait_for(
                asyncio.gather(
                    *opening_tasks.values(),
                    return_exceptions=True,
                ),
                timeout=self.max_rounds * 5.0  # 5 seconds per round max
            )
            for (member_type, _), result in zip(opening_tasks.items(), opening_results):
                if isinstance(result, Exception):
                    logger.error(f"Opening statement failed for {member_type}: {result}")
                    opening = f"[ERROR: {member_type.value} failed]"
                else:
                    opening = result
                all_arguments.append(opening)
                debate_rounds.append(DebateRound(
                    round_number=0,
                    speaker=member_type,
                    content=opening,
                ))
        except asyncio.TimeoutError:
            logger.error("Opening statements timed out")
            # Fallback: use timeout responses
            for member_type in self.members:
                all_arguments.append("[超时：响应超时]")
                debate_rounds.append(DebateRound(
                    round_number=0,
                    speaker=member_type,
                    content="[超时：响应超时]",
                ))

        # Rounds 1 to N: Debate
        for round_num in range(1, rounds + 1):
            logger.info(f"Debate round {round_num}...")

            # For round 1, use opening statements as prior arguments.
            # For round 2+, use the most recent member responses.
            base_opening_count = 3  # CHAIR + ENGINEERING + FINANCE openings
            prior_member_args = all_arguments[base_opening_count:]  # all member args so far
            # Use opening statements as context for round 1; prior rounds for rounds 2+
            if round_num == 1:
                # Pull engineering and finance openings as the debate context
                engineering_arg = all_arguments[1] if len(all_arguments) > 1 else ""
                finance_arg = all_arguments[2] if len(all_arguments) > 2 else ""
            else:
                engineering_arg = prior_member_args[-2] if len(prior_member_args) >= 2 else ""
                finance_arg = prior_member_args[-1] if len(prior_member_args) >= 1 else ""
            # Most recent chair summary (if any)
            chair_summary = next(
                (a for a in reversed(all_arguments) if str(a).startswith("[CHAIR]")),
                ""
            )
            context = {
                "chair_summary": chair_summary,
                "engineering_arg": engineering_arg,
                "finance_arg": finance_arg,
                "round": round_num,
            }

            # Run all 6 member responses in parallel
            engineering_resp, finance_resp, methodology_resp, statistics_resp, writing_resp = await asyncio.gather(
                self.members[MemberType.MEMBER_ENGINEERING].respond(context),
                self.members[MemberType.MEMBER_FINANCE].respond(context),
                self.members[MemberType.MEMBER_METHODOLOGY].respond(context),
                self.members[MemberType.MEMBER_STATISTICS].respond(context),
                self.members[MemberType.MEMBER_WRITING].respond(context),
            )

            all_arguments.extend([engineering_resp, finance_resp, methodology_resp, statistics_resp, writing_resp])
            debate_rounds.append(DebateRound(round_num, MemberType.MEMBER_ENGINEERING, engineering_resp))
            debate_rounds.append(DebateRound(round_num, MemberType.MEMBER_FINANCE, finance_resp))
            debate_rounds.append(DebateRound(round_num, MemberType.MEMBER_METHODOLOGY, methodology_resp))
            debate_rounds.append(DebateRound(round_num, MemberType.MEMBER_STATISTICS, statistics_resp))
            debate_rounds.append(DebateRound(round_num, MemberType.MEMBER_WRITING, writing_resp))

            # Chair summarizes (not on last round — final verdict handles it)
            if round_num < rounds:
                context["engineering_arg"] = engineering_resp
                context["finance_arg"] = finance_resp
                chair_summary = await self.members[MemberType.CHAIR].respond(context)
                all_arguments.append(chair_summary)
                debate_rounds.append(DebateRound(round_num, MemberType.CHAIR, chair_summary))

        # Final statements and scoring (all 6 members)
        logger.info("Collecting final statements from all 6 members...")

        engineering_final = await self.members[MemberType.MEMBER_ENGINEERING].final_statement({
            "paper_title": paper.get("title", ""),
            "previous_arguments": "\n".join(str(a) for a in all_arguments[-6:]),
        })
        eng_score = None if engineering_final.get("_error") else engineering_final.get("score")
        if engineering_final.get("_error"):
            logger.error(f"Engineering final statement failed: {engineering_final.get('_error_message', 'unknown')}")
        individual_scores["engineering"] = eng_score

        finance_final = await self.members[MemberType.MEMBER_FINANCE].final_statement({
            "paper_title": paper.get("title", ""),
            "previous_arguments": "\n".join(str(a) for a in all_arguments[-6:]),
        })
        fin_score = None if finance_final.get("_error") else finance_final.get("score")
        if finance_final.get("_error"):
            logger.error(f"Finance final statement failed: {finance_final.get('_error_message', 'unknown')}")
        individual_scores["finance"] = fin_score

        methodology_final = await self.members[MemberType.MEMBER_METHODOLOGY].final_statement({
            "paper_title": paper.get("title", ""),
            "previous_arguments": "\n".join(str(a) for a in all_arguments[-6:]),
        })
        method_score = None if methodology_final.get("_error") else methodology_final.get("score")
        if methodology_final.get("_error"):
            logger.error(f"Methodology final statement failed: {methodology_final.get('_error_message', 'unknown')}")
        individual_scores["methodology"] = method_score

        statistics_final = await self.members[MemberType.MEMBER_STATISTICS].final_statement({
            "paper_title": paper.get("title", ""),
            "previous_arguments": "\n".join(str(a) for a in all_arguments[-6:]),
        })
        stat_score = None if statistics_final.get("_error") else statistics_final.get("score")
        if statistics_final.get("_error"):
            logger.error(f"Statistics final statement failed: {statistics_final.get('_error_message', 'unknown')}")
        individual_scores["statistics"] = stat_score

        writing_final = await self.members[MemberType.MEMBER_WRITING].final_statement({
            "paper_title": paper.get("title", ""),
            "previous_arguments": "\n".join(str(a) for a in all_arguments[-6:]),
        })
        writing_score = None if writing_final.get("_error") else writing_final.get("score")
        if writing_final.get("_error"):
            logger.error(f"Writing final statement failed: {writing_final.get('_error_message', 'unknown')}")
        individual_scores["writing"] = writing_score

        # Chair produces final verdict
        chair_verdict = await self.members[MemberType.CHAIR].final_statement({
            "all_arguments": all_arguments,
            "individual_scores": individual_scores,
        })

        # Use None for errors to avoid polluting avg with fallback 3.0
        eng_score = None if engineering_final.get("_error") else engineering_final.get("score")
        fin_score = None if finance_final.get("_error") else finance_final.get("score")
        method_score = None if methodology_final.get("_error") else methodology_final.get("score")
        stat_score = None if statistics_final.get("_error") else statistics_final.get("score")
        writing_score = None if writing_final.get("_error") else writing_final.get("score")
        chair_score = None if chair_verdict.get("_error") else chair_verdict.get("score")
        if engineering_final.get("_error"):
            logger.error(f"Engineering final statement failed: {engineering_final.get('_error_message', 'unknown')}")
        individual_scores["engineering"] = eng_score
        if finance_final.get("_error"):
            logger.error(f"Finance final statement failed: {finance_final.get('_error_message', 'unknown')}")
        individual_scores["finance"] = fin_score
        if methodology_final.get("_error"):
            logger.error(f"Methodology final statement failed: {methodology_final.get('_error_message', 'unknown')}")
        individual_scores["methodology"] = method_score
        if statistics_final.get("_error"):
            logger.error(f"Statistics final statement failed: {statistics_final.get('_error_message', 'unknown')}")
        individual_scores["statistics"] = stat_score
        if writing_final.get("_error"):
            logger.error(f"Writing final statement failed: {writing_final.get('_error_message', 'unknown')}")
        individual_scores["writing"] = writing_score

        # Chair produces final verdict
        chair_verdict = await self.members[MemberType.CHAIR].final_statement({
            "all_arguments": all_arguments,
            "individual_scores": individual_scores,
        })
        if chair_verdict.get("_error"):
            logger.error(f"Chair final statement failed: {chair_verdict.get('_error_message', 'unknown')}")
        individual_scores["chair"] = chair_score

        # Determine recommendation — equal-weight average of all valid member scores (skip None)
        all_scores = [eng_score, fin_score, method_score, stat_score, writing_score, chair_score]
        valid_scores = [s for s in all_scores if isinstance(s, (int, float)) and s is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else None

        has_errors = any([
            engineering_final.get("_error"),
            finance_final.get("_error"),
            methodology_final.get("_error"),
            statistics_final.get("_error"),
            writing_final.get("_error"),
            chair_verdict.get("_error"),
        ])

        if has_errors and not valid_scores:
            recommendation = "error"
        elif avg_score is None:
            recommendation = "error"
        elif avg_score >= 4.0:
            recommendation = "accept"
        elif avg_score >= 2.5:
            recommendation = "revision"
        else:
            recommendation = "reject"

        # Check for disagreement (disputed verdict)
        if valid_scores:
            max_diff = max(valid_scores) - min(valid_scores)
            disputed = max_diff > 1.0
        else:
            disputed = False

        # Rebuttal rounds - all 5 member agents respond to the chair's summary
        rebuttal_rounds: list[RebuttalRound] = []
        chair_summary = chair_verdict.get("summary", "")

        for member_type in [
            MemberType.MEMBER_ENGINEERING,
            MemberType.MEMBER_FINANCE,
            MemberType.MEMBER_METHODOLOGY,
            MemberType.MEMBER_STATISTICS,
            MemberType.MEMBER_WRITING,
        ]:
            rebuttal = await self.members[member_type].respond({
                "chair_summary": chair_summary,
                "round": -1,  # Signals rebuttal round
            })
            rebuttal_rounds.append(RebuttalRound(
                round_num=-1,
                member_type=member_type,
                response_to_summary=rebuttal,
                strength="moderate",
            ))

        return Verdict(
            score=round(avg_score, 2) if avg_score is not None else None,
            recommendation=recommendation,
            summary=chair_verdict.get("summary", ""),
            key_strengths=chair_verdict.get("key_strengths", []),
            key_weaknesses=chair_verdict.get("key_weaknesses", []),
            debate_rounds=debate_rounds,
            rebuttal_rounds=rebuttal_rounds,
            disputed=disputed,
            all_arguments=all_arguments,
        )

    def format_verdict(self, verdict: Verdict) -> str:
        """Format verdict for display."""
        lines = []

        # Header
        score_icon = "🟢" if verdict.score >= 4 else ("🟡" if verdict.score >= 2.5 else "🔴")
        rec_icon = {"accept": "✅", "revision": "🔄", "reject": "❌"}.get(verdict.recommendation, "")
        disputed_icon = "⚠️" if verdict.disputed else ""

        lines.append(f"# AI Parliament 评审结果 {score_icon} {disputed_icon}")
        lines.append("")
        lines.append(f"**评分**: {verdict.score}/5")
        lines.append(f"**建议**: {rec_icon} {verdict.recommendation.upper()}")
        if verdict.disputed:
            lines.append("**状态**: ⚠️ 存在显著分歧（评分差异 > 1.0）")
        lines.append("")

        # Error info — collect errors from debate rounds
        error_info: list[str] = []
        for round_obj in verdict.debate_rounds:
            content = str(round_obj.content)
            if content.startswith("[ERROR:") and content not in [a for a in all_arguments[:all_arguments.index(content)] if str(a).startswith("[ERROR:")]:
                # Show unique error content snippets
                error_info.append(f"{round_obj.speaker.value}: {content[7:60]}")
        if error_info:
            lines.append("**Member Errors**: " + ", ".join(error_info[:3]))
            lines.append("")

        # Key points
        if verdict.key_strengths:
            lines.append("## 核心优势")
            for s in verdict.key_strengths:
                lines.append(f"- ✅ {s}")
            lines.append("")

        if verdict.key_weaknesses:
            lines.append("## 核心不足")
            for w in verdict.key_weaknesses:
                lines.append(f"- ⚠️ {w}")
            lines.append("")

        # Summary
        if verdict.summary:
            lines.append("## 综合评价")
            lines.append(verdict.summary[:500])
            lines.append("")

        # Member type name mapping
        member_names = {
            MemberType.CHAIR: "主持人",
            MemberType.MEMBER_ENGINEERING: "工程委员",
            MemberType.MEMBER_FINANCE: "理论委员",
            MemberType.MEMBER_METHODOLOGY: "方法论委员",
            MemberType.MEMBER_STATISTICS: "统计委员",
            MemberType.MEMBER_WRITING: "写作委员",
        }

        # Debate transcript (condensed)
        lines.append("## 辩论摘要")
        for i, round_obj in enumerate(verdict.debate_rounds[:9]):  # First 9 rounds
            speaker_name = member_names.get(round_obj.speaker, "Unknown")

            lines.append(f"**Round {round_obj.round_number} - {speaker_name}**:")
            lines.append(f"{round_obj.content[:200]}...")
            lines.append("")

        # Rebuttal rounds
        if verdict.rebuttal_rounds:
            lines.append("## 反驳轮次")
            for rebuttal in verdict.rebuttal_rounds:
                speaker_name = member_names.get(rebuttal.member_type, "Unknown")
                lines.append(f"**{speaker_name} 对主席总结的回应**:")
                lines.append(f"{rebuttal.response_to_summary[:200]}...")
                lines.append(f"[论证强度: {rebuttal.strength}]")
                lines.append("")

        return "\n".join(lines)


# ─── HITL Integration ────────────────────────────────────────────────────────────


class AIParliamentHITLIntegration:
    """
    AI Parliament 与 HITLGate 联动模块

    功能：
    1. 将 AIParliament 的裁决结果自动驱动 HITLGate 审批
    2. 支持人工覆写裁决结果
    3. 记录 AI vs Human 决策差异
    4. 支持多轮 AI-Human 迭代评审
    """

    def __init__(self, parliament: AIParliament = None, hitl_gate=None):
        self.parliament = parliament or AIParliament()
        self.hitl_gate = hitl_gate
        self._decision_history: list[dict] = []

    async def debate_and_approve(
        self,
        paper: dict,
        rounds: int = 3,
        auto_threshold: float = 4.0,
    ) -> tuple[dict, bool]:
        """
        运行 AI 辩论并根据结果决定是否自动审批

        Parameters
        ----------
        paper : dict
            论文信息
        rounds : int
            辩论轮数
        auto_threshold : float
            自动审批阈值（评分 >= 此值则自动通过）

        Returns
        -------
        tuple[dict, bool]
            (裁决结果, 是否需要人工确认)
        """
        # 运行辩论
        verdict = await self.parliament.debate(paper, rounds=rounds)

        # 格式化裁决结果
        verdict_dict = {
            "score": verdict.score,
            "recommendation": verdict.recommendation,
            "summary": verdict.summary,
            "key_strengths": verdict.key_strengths,
            "key_weaknesses": verdict.key_weaknesses,
            "confidence": self._calculate_confidence(verdict),
            "disputed": getattr(verdict, 'disputed', False),
            "rebuttal_count": len(getattr(verdict, 'rebuttal_rounds', [])),
        }

        # 记录历史
        self._decision_history.append({
            "timestamp": time.time(),
            "verdict": verdict_dict,
            "auto_decision": verdict.score >= auto_threshold,
        })

        # 决定是否需要人工确认
        # Force human review if verdict is disputed (significant disagreement between members)
        need_human_review = verdict.score < auto_threshold or getattr(verdict, 'disputed', False)

        # Run specialized agents if available
        if _SPECIALIZED_AGENTS_AVAILABLE:
            try:
                agent_results = await run_all_agents(
                    paper_text=paper.get("text", ""),
                    latex_tables=paper.get("latex_tables", {}),
                    code_blocks=paper.get("code_blocks", {}),
                    contribution=paper.get("contribution", ""),
                    lit_review=paper.get("lit_review", ""),
                    regression_outputs=paper.get("regression_outputs", {}),
                    journal=paper.get("journal", "JF"),
                )
                verdict_dict = verdict.__dict__ if hasattr(verdict, "__dict__") else dict(verdict)
                verdict_dict["specialized_reviews"] = {
                    name: r.to_dict() for name, r in agent_results.items() if isinstance(r, AgentReviewResult)
                }
                logger.info(f"Specialized agent reviews: {[name for name in agent_results]}")
            except Exception as exc:
                logger.warning(f"Specialized agent review failed: {exc}")

        return verdict_dict, need_human_review

    def create_hitl_approval(
        self,
        verdict: dict,
        stage: str = "review",
        question: str = "",
    ) -> str:
        """
        根据裁决结果创建 HITL 审批请求

        Parameters
        ----------
        verdict : dict
            AI Parliament 裁决结果
        stage : str
            审批阶段标识
        question : str
            审批问题

        Returns
        -------
        str
            HITL gate_id
        """
        if self.hitl_gate is None:
            logger.warning("HITLGate 未配置，跳过人工审批")
            return ""

        # 构建审批内容
        content = {
            "ai_verdict": verdict,
            "recommendation": verdict.get("recommendation"),
            "score": verdict.get("score"),
            "confidence": verdict.get("confidence"),
        }

        # 构建审批问题
        if not question:
            if verdict.get("recommendation") == "accept":
                question = f"AI 评审建议接受（评分 {verdict.get('score')}/5）。是否确认通过？"
            elif verdict.get("recommendation") == "revision":
                question = f"AI 评审建议修改（评分 {verdict.get('score')}/5）。请查看主要问题后确认：\n" + "\n".join(
                    f"- {w}" for w in verdict.get("key_weaknesses", [])[:3]
                )
            else:
                question = f"AI 评审建议拒绝（评分 {verdict.get('score')}/5）。请确认：\n" + "\n".join(
                    f"- {w}" for w in verdict.get("key_weaknesses", [])[:3]
                )

        # 创建 HITL 审批
        gate_id = self.hitl_gate.hold(
            stage=stage,
            content=content,
            question=question,
        )

        return gate_id

    def _calculate_confidence(self, verdict) -> float:
        """
        计算裁决置信度

        基于：
        - 评分方差（多方一致→高置信）
        - 有效辩论轮数（轮数越多→置信越高，但TIMEOUT/ERROR轮不计入）
        - 建议类型（accept/reject→高置信，revision→中等置信）
        - 观点分歧（disputed→轻微降权）
        """
        base_confidence = 0.7

        # Only count valid member rounds (skip CHAIR-only or ERROR/TIMEOUT entries)
        valid_member_rounds = [
            r for r in verdict.debate_rounds
            if r.round_number > 0
            and r.speaker != MemberType.CHAIR
            and "[TIMEOUT" not in r.content
            and "[ERROR" not in r.content
        ]
        round_bonus = min(len(valid_member_rounds) * 0.02, 0.15)

        # 建议类型加成
        rec_bonus = {
            "accept": 0.1,
            "revision": 0.0,
            "reject": 0.1,
        }.get(verdict.recommendation, 0)

        # Perspective disagreement penalty
        disagreement_penalty = 0.1 if getattr(verdict, 'disputed', False) else 0.0

        return min(base_confidence + round_bonus + rec_bonus - disagreement_penalty, 0.99)

    def get_decision_stats(self) -> dict:
        """获取决策统计"""
        if not self._decision_history:
            return {"total_decisions": 0}

        auto_approved = sum(1 for d in self._decision_history if d["auto_decision"])
        human_reviewed = len(self._decision_history) - auto_approved

        avg_score = sum(d["verdict"]["score"] for d in self._decision_history) / len(self._decision_history)

        return {
            "total_decisions": len(self._decision_history),
            "auto_approved": auto_approved,
            "human_reviewed": human_reviewed,
            "auto_rate": round(auto_approved / len(self._decision_history), 2),
            "avg_score": round(avg_score, 2),
        }


# ─── CLI Interface ──────────────────────────────────────────────────────────────


async def main():
    """CLI interface for AI Parliament."""
    import argparse

    parser = argparse.ArgumentParser(description="AI Parliament")
    parser.add_argument("--title", type=str, required=True, help="Paper title")
    parser.add_argument("--abstract", type=str, help="Paper abstract")
    parser.add_argument("--content", type=str, help="Paper content (if no abstract)")
    parser.add_argument("--rounds", type=int, default=2, help="Number of debate rounds")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    paper = {
        "title": args.title,
        "abstract": args.abstract or args.content or "",
    }

    parliament = AIParliament()
    verdict = await parliament.debate(paper, rounds=args.rounds)

    if args.format == "json":
        print(json.dumps({
            "score": verdict.score,
            "recommendation": verdict.recommendation,
            "summary": verdict.summary,
            "key_strengths": verdict.key_strengths,
            "key_weaknesses": verdict.key_weaknesses,
            "debate_rounds": [
                {
                    "round": r.round_number,
                    "speaker": r.speaker.value,
                    "content": r.content[:200],
                }
                for r in verdict.debate_rounds
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(parliament.format_verdict(verdict))


if __name__ == "__main__":
    asyncio.run(main())
