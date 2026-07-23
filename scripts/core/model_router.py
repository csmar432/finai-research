"""
model_router.py — 智能模型路由器

根据任务类型自动选择最优模型，借鉴 MSc 的任务感知模型路由。

核心设计：
1. 任务分类器：将用户输入分类到金融研究任务类型
2. 模型选择器：根据任务类型选择最优模型（速度/质量/成本权衡）
3. 金融特化：对中文金融研究任务有特殊处理
4. 故障转移：主模型失败时自动切换到备选

模型层级：
  L1 (最快/最便宜): deepseek_flash, gemini_flash
  L2 (均衡): deepseek_pro, kimi, glm
  L3 (最强推理): claude_sonnet, gpt_pro, deepseek_r1
  L4 (顶级): claude_opus, gpt_o
"""

from __future__ import annotations

__all__ = [
    "TaskType",
    "ModelChoice",
    "TaskClassification",
    "ModelConfig",
    "TaskClassifier",
    "ModelSelector",
    "ModelRouter",
]

import logging
import os
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """金融研究任务类型。"""
    # 文献与探索
    LITERATURE_SEARCH = "literature_search"       # 文献检索（快速，广覆盖）
    LITERATURE_SYNTHESIS = "literature_synthesis"  # 文献综合（深度理解）
    PAPER_READING = "paper_reading"              # 论文精读（长文本）

    # 想法与设计
    IDEA_GENERATION = "idea_generation"           # 想法生成（创意驱动）
    NOVELTY_CHECK = "novelty_check"              # 新颖性验证（精确比对）
    EXPERIMENT_DESIGN = "experiment_design"      # 实证设计（结构化推理）

    # 写作
    DRAFT_WRITING_CN = "draft_writing_cn"         # 中文论文写作
    DRAFT_WRITING_EN = "draft_writing_en"         # 英文论文写作
    REFINEMENT = "refinement"                    # 润色优化（快速）
    TRANSLATION_CN_EN = "translation_cn_en"      # 中译英
    TRANSLATION_EN_CN = "translation_en_cn"      # 英译中

    # 分析与实证
    DATA_ANALYSIS = "data_analysis"             # 数据分析（计算密集）
    REGRESSION_RESULT = "regression_result"      # 回归结果解读
    FINANCIAL_ANALYSIS = "financial_analysis"   # 财务分析
    TEXT_SENTIMENT = "text_sentiment"           # 文本情感分析（中文）

    # 评审
    PEER_REVIEW = "peer_review"                 # 同行评审（严格推理）
    FACT_CHECK = "fact_check"                  # 事实核查
    CRITIQUE = "critique"                      # 批评性反馈

    # 规划与元
    PLANNING = "planning"                      # 研究规划
    SUMMARIZATION = "summarization"            # 摘要/总结
    CODE_GENERATION = "code_generation"         # 代码生成
    GENERAL = "general"                        # 通用对话


@dataclass
class ModelChoice:
    """模型选择结果。"""
    primary: str            # 主模型 ID
    primary_label: str      # 主模型名称
    fallback: str           # 备选模型 ID
    fallback_label: str     # 备选模型名称
    reasoning: str         # 选择理由
    cost_estimate: str     # 成本估算
    expected_latency: str   # 预期延迟
    task_type: TaskType
    confidence: float       # 分类置信度 0-1


@dataclass
class TaskClassification:
    """任务分类结果。"""
    task_type: TaskType
    confidence: float
    keywords: list[str]    # 触发的关键词
    domain: str            # "academic_paper" / "financial_report" / "general"
    language: str          # "cn" / "en" / "mixed"


# ─── 模型配置 ────────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """单个模型的配置。"""
    model_id: str
    provider: str          # "deepseek" / "relay" / "openai" / "anthropic" / "gemini"
    tier: int              # 1=最快, 4=最强
    strengths: list[str]   # 擅长领域
    weaknesses: list[str]
    chinese_quality: float  # 1-5，中文输出质量
    english_quality: float # 1-5，英文输出质量
    code_quality: float   # 1-5，代码质量
    speed: str            # "fast" / "medium" / "slow"
    cost_tier: str        # "low" / "medium" / "high"
    max_context: int      # 最大上下文 token
    api_key_env: str      # 环境变量名
    base_url: str | None  # API base URL（可选）

    def is_available(self) -> bool:
        return bool(os.getenv(self.api_key_env, ""))


MODELS: dict[str, ModelConfig] = {
    # L1: 快速/便宜
    "deepseek_flash": ModelConfig(
        model_id="deepseek_flash",
        provider="deepseek",
        tier=1,
        strengths=["中文写作", "快速总结", "数据格式化", "表格生成"],
        weaknesses=["复杂推理", "长篇创作"],
        chinese_quality=4.5, english_quality=4.0, code_quality=4.0,
        speed="fast", cost_tier="low", max_context=1_000_000,
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "gemini_flash": ModelConfig(
        model_id="gemini_flash",
        provider="gemini",
        tier=1,
        strengths=["快速搜索", "多模态", "网络搜索"],
        weaknesses=["中文金融写作", "学术格式"],
        chinese_quality=3.5, english_quality=4.0, code_quality=3.5,
        speed="fast", cost_tier="low", max_context=1_000_000,
        api_key_env="GEMINI_API_KEY",
        base_url=None,
    ),

    # L2: 均衡
    "deepseek_pro": ModelConfig(
        model_id="deepseek_pro",
        provider="deepseek",
        tier=2,
        strengths=["中文论文写作", "复杂推理", "文献综述", "实证分析"],
        weaknesses=["顶级英文写作"],
        chinese_quality=5.0, english_quality=4.5, code_quality=4.5,
        speed="medium", cost_tier="medium", max_context=1_000_000,
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "kimi": ModelConfig(
        model_id="kimi",
        provider="relay",
        tier=2,
        strengths=["长文档理解", "中文分析", "学术写作"],
        weaknesses=["复杂推理"],
        chinese_quality=4.5, english_quality=4.0, code_quality=3.5,
        speed="medium", cost_tier="medium", max_context=128_000,
        api_key_env="RELAY_API_KEY",
        base_url="https://api.b.ai/v1",
    ),
    "glm": ModelConfig(
        model_id="glm",
        provider="relay",
        tier=2,
        strengths=["结构化输出", "中文分析", "JSON格式"],
        weaknesses=["长篇写作"],
        chinese_quality=4.5, english_quality=4.0, code_quality=4.0,
        speed="medium", cost_tier="medium", max_context=128_000,
        api_key_env="RELAY_API_KEY",
        base_url="https://api.b.ai/v1",
    ),

    # L3: 深度推理
    "claude_sonnet": ModelConfig(
        model_id="claude_sonnet",
        provider="anthropic",
        tier=3,
        strengths=["深度分析", "学术写作(EN)", "复杂推理", "评审批评"],
        weaknesses=["中文理解稍弱", "成本较高"],
        chinese_quality=4.0, english_quality=5.0, code_quality=4.5,
        speed="slow", cost_tier="high", max_context=200_000,
        api_key_env="RELAY_API_KEY",
        base_url="https://api.b.ai/v1",
    ),
    "gpt_pro": ModelConfig(
        model_id="gpt_pro",
        provider="openai",
        tier=3,
        strengths=["英文写作", "代码生成", "多语言", "通用推理"],
        weaknesses=["中文金融写作"],
        chinese_quality=3.5, english_quality=5.0, code_quality=5.0,
        speed="slow", cost_tier="high", max_context=128_000,
        api_key_env="RELAY_API_KEY",
        base_url="https://api.b.ai/v1",
    ),
    "deepseek_r1": ModelConfig(
        model_id="deepseek_r1",
        provider="deepseek",
        tier=3,
        strengths=["复杂推理", "数学证明", "金融计量", "实证设计"],
        weaknesses=["非推理任务速度慢"],
        chinese_quality=5.0, english_quality=4.5, code_quality=4.5,
        speed="slow", cost_tier="medium", max_context=1_000_000,
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),

    # L4: 顶级
    "claude_opus": ModelConfig(
        model_id="claude_opus",
        provider="anthropic",
        tier=4,
        strengths=["顶级推理", "学术写作(EN)", "评审", "长文档"],
        weaknesses=["成本最高", "速度慢"],
        chinese_quality=4.5, english_quality=5.0, code_quality=5.0,
        speed="slow", cost_tier="highest", max_context=200_000,
        api_key_env="RELAY_API_KEY",
        base_url="https://api.b.ai/v1",
    ),
}


# ─── 任务分类器 ─────────────────────────────────────────────────────────────

class TaskClassifier:
    """基于关键词规则的任务分类器。"""

    KEYWORD_MAP: dict[str, TaskType] = {
        # 文献
        "literature_search": [
            "搜索", "找文献", "查论文", "文献检索", "文献查找",
            "search for", "find papers", "literature search",
            "有什么研究", "近三年", "最新进展", "最新文献",
        ],
        "literature_synthesis": [
            "综述", "综合", "文献回顾", "研究现状",
            "literature review", "synthesize", "研究脉络",
            "系统梳理", "研究缺口", "研究空白",
        ],
        "paper_reading": [
            "这篇论文", "这篇文献", "读一下", "精读", "理解这篇",
            "read this paper", "summarize", "abstract",
            "主要贡献", "核心发现",
        ],

        # 想法与设计
        "idea_generation": [
            "有什么想法", "研究点", "新方向", "创新点",
            "ideas for", "research ideas", "novel topic",
            "能做", "可以做", "值得研究", "潜在贡献",
        ],
        "novelty_check": [
            "新颖性", "是否有人做过", "重复了吗", "有没有类似",
            "novelty", "already done", "existing work", "prior study",
            "创新性", "原创性",
        ],
        "experiment_design": [
            "实验设计", "实证方法", "DID", "IV", "RDD", "合成控制",
            "design experiment", "identification strategy",
            "控制组", "处理组", "工具变量", "断点回归",
            "面板数据", "双向固定效应", "event study",
        ],

        # 写作
        "draft_writing_cn": [
            "写", "撰写", "起草", "中文",
            "write introduction", "write methodology", "中文论文",
            "中文报告", "经济研究", "金融研究", "管理世界",
            "实证结果", "稳健性检验", "研究假说",
        ],
        "draft_writing_en": [
            "write in English", "英文", "write the abstract",
            "JF", "JFE", "RFS", "JME", "英文论文",
        ],
        "refinement": [
            "润色", "修改", "优化", "改写", "精炼",
            "polish", "improve", "revise", "refine",
            "表达更准确", "更流畅", "更学术",
        ],
        "translation_cn_en": [
            "翻译成英文", "翻译成英文", "中译英",
            "translate to English", "translate into English",
        ],
        "translation_en_cn": [
            "翻译成中文", "英译中", "翻译",
            "translate to Chinese", "translate into Chinese",
        ],

        # 分析
        "data_analysis": [
            "分析", "回归", "统计", "数据处理",
            "analyze", "regression", "statistical",
            "相关性", "显著性", "p值", "稳健性",
        ],
        "regression_result": [
            "回归结果", "实证结果", "系数解读",
            "regression results", "coefficient",
            "t统计量", "R方", "F统计量",
        ],
        "financial_analysis": [
            "财务分析", "ROE", "ROA", "估值", "DCF",
            "financial analysis", "valuation",
            "盈利能力", "偿债能力", "现金流",
        ],
        "text_sentiment": [
            "情感分析", "文本分析", "语调", "年报文本",
            "sentiment analysis", "text analysis",
            "正面词", "负面词", "管理层讨论",
        ],

        # 评审
        "peer_review": [
            "review", "评审", "审稿", "审查",
            "critique", "evaluate", "assess quality",
            "学术质量", "实证严谨性",
        ],
        "fact_check": [
            "核查", "验证", "事实",
            "fact check", "verify", "validate",
            "数据是否准确", "引用是否正确",
        ],
        "critique": [
            "批评", "问题", "不足", "weakness",
            "criticism", "limitation", "gap",
            "有什么问题", "主要缺陷",
        ],

        # 规划与元
        "planning": [
            "研究计划", "规划", "步骤", "如何开展",
            "research plan", "roadmap", "steps to",
            "工作流", "流程",
        ],
        "summarization": [
            "总结", "摘要", "概括",
            "summary", "abstract", "outline",
            "主要结论", "核心观点",
        ],
        "code_generation": [
            "代码", "脚本", "Python", "Stata", "写代码",
            "code", "script", "program", "generate code",
            "回归分析", "数据清洗",
        ],
    }

    def classify(self, text: str) -> TaskClassification:
        """对输入文本进行任务分类。"""
        text_lower = text.lower()
        scores: dict[TaskType, float] = {}

        for task, keywords in self.KEYWORD_MAP.items():
            hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hits > 0:
                scores[TaskType(task)] = hits

        if not scores:
            return TaskClassification(
                task_type=TaskType.GENERAL,
                confidence=0.5,
                keywords=[],
                domain="general",
                language="mixed",
            )

        best_task = max(scores, key=scores.get)
        confidence = min(scores[best_task] / 3.0, 1.0)

        # 判断语言
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en_words = len([w for w in text.split() if w.isascii()])
        if cn_chars > en_words * 2:
            language = "cn"
        elif en_words > cn_chars * 2:
            language = "en"
        else:
            language = "mixed"

        # 判断领域
        financial_keywords = ["A股", "股票", "债券", "基金", "金融", "经济",
                            "宏观", "微观", "实证", "回归", "面板", "期权",
                            "stock", "bond", "finance", "economic", "macro",
                            "market", "portfolio", "risk"]
        academic_keywords = ["论文", "期刊", "发表", "顶刊", "学术",
                           "paper", "journal", "publication", "research",
                           "cite", "hypothesis", "literature"]

        domain = "general"
        if any(kw in text_lower for kw in financial_keywords):
            domain = "financial_report"
        if any(kw in text_lower for kw in academic_keywords):
            domain = "academic_paper"

        # 触发的关键词
        keywords = [kw for kw in self.KEYWORD_MAP.get(best_task.value, [])
                   if kw.lower() in text_lower]

        return TaskClassification(
            task_type=best_task,
            confidence=confidence,
            keywords=keywords,
            domain=domain,
            language=language,
        )


# ─── 模型选择器 ────────────────────────────────────────────────────────────

class ModelSelector:
    """根据任务类型选择最优模型。"""

    # 任务类型 → 模型选择策略
    TASK_ROUTING: dict[TaskType, tuple[tuple[str, str], tuple[str, str]]] = {
        # (primary, fallback)
        TaskType.LITERATURE_SEARCH: (
            ("deepseek_flash", "gemini_flash"),
            ("deepseek_pro", "kimi"),
        ),
        TaskType.LITERATURE_SYNTHESIS: (
            ("deepseek_pro", "kimi"),
            ("claude_sonnet", "deepseek_flash"),
        ),
        TaskType.PAPER_READING: (
            ("kimi", "deepseek_pro"),
            ("claude_sonnet", "gemini_flash"),
        ),
        TaskType.IDEA_GENERATION: (
            ("deepseek_pro", "deepseek_r1"),
            ("claude_opus", "deepseek_flash"),
        ),
        TaskType.NOVELTY_CHECK: (
            ("claude_sonnet", "deepseek_pro"),
            ("deepseek_flash", "gemini_flash"),
        ),
        TaskType.EXPERIMENT_DESIGN: (
            ("deepseek_r1", "deepseek_pro"),
            ("claude_opus", "claude_sonnet"),
        ),
        TaskType.DRAFT_WRITING_CN: (
            ("deepseek_pro", "kimi"),
            ("glm", "deepseek_flash"),
        ),
        TaskType.DRAFT_WRITING_EN: (
            ("claude_sonnet", "gpt_pro"),
            ("deepseek_pro", "deepseek_flash"),
        ),
        TaskType.REFINEMENT: (
            ("deepseek_flash", "gemini_flash"),
            ("claude_sonnet", "kimi"),
        ),
        TaskType.TRANSLATION_CN_EN: (
            ("deepseek_pro", "gpt_pro"),
            ("claude_sonnet", "gemini_flash"),
        ),
        TaskType.TRANSLATION_EN_CN: (
            ("deepseek_pro", "kimi"),
            ("deepseek_flash", "glm"),
        ),
        TaskType.DATA_ANALYSIS: (
            ("deepseek_r1", "deepseek_pro"),
            ("claude_sonnet", "deepseek_flash"),
        ),
        TaskType.REGRESSION_RESULT: (
            ("deepseek_pro", "claude_sonnet"),
            ("deepseek_r1", "kimi"),
        ),
        TaskType.FINANCIAL_ANALYSIS: (
            ("deepseek_pro", "deepseek_r1"),
            ("claude_sonnet", "kimi"),
        ),
        TaskType.TEXT_SENTIMENT: (
            ("deepseek_pro", "kimi"),
            ("glm", "claude_sonnet"),
        ),
        TaskType.PEER_REVIEW: (
            ("claude_opus", "claude_sonnet"),
            ("deepseek_r1", "deepseek_pro"),
        ),
        TaskType.FACT_CHECK: (
            ("claude_sonnet", "deepseek_pro"),
            ("gemini_flash", "deepseek_flash"),
        ),
        TaskType.CRITIQUE: (
            ("claude_opus", "claude_sonnet"),
            ("deepseek_r1", "gpt_pro"),
        ),
        TaskType.PLANNING: (
            ("deepseek_pro", "deepseek_flash"),
            ("kimi", "claude_sonnet"),
        ),
        TaskType.SUMMARIZATION: (
            ("deepseek_flash", "gemini_flash"),
            ("kimi", "deepseek_pro"),
        ),
        TaskType.CODE_GENERATION: (
            ("deepseek_pro", "gpt_pro"),
            ("claude_sonnet", "deepseek_r1"),
        ),
        TaskType.GENERAL: (
            ("deepseek_flash", "gemini_flash"),
            ("deepseek_pro", "kimi"),
        ),
    }

    def select(self, classification: TaskClassification) -> ModelChoice:
        """根据分类结果选择最优模型。"""
        task = classification.task_type
        routing = self.TASK_ROUTING.get(task, self.TASK_ROUTING[TaskType.GENERAL])

        primary_id, fallback_id = routing
        primary_cfg = MODELS.get(primary_id[0], MODELS["deepseek_flash"])
        fallback_cfg = MODELS.get(fallback_id[0], MODELS["deepseek_pro"])

        # 如果首选不可用，降级
        if not primary_cfg.is_available():
            primary_id, fallback_id = fallback_id, primary_id
            primary_cfg, fallback_cfg = fallback_cfg, primary_cfg

        # 金融领域特殊调整
        reasoning = self._build_reasoning(task, classification, primary_cfg, fallback_cfg)

        return ModelChoice(
            primary=primary_id[0],
            primary_label=f"{primary_cfg.provider}/{primary_cfg.model_id} ({primary_cfg.speed})",
            fallback=fallback_id[0],
            fallback_label=f"{fallback_cfg.provider}/{fallback_cfg.model_id} ({fallback_cfg.speed})",
            reasoning=reasoning,
            cost_estimate=self._estimate_cost(primary_cfg),
            expected_latency=self._estimate_latency(primary_cfg, classification),
            task_type=task,
            confidence=classification.confidence,
        )

    def _build_reasoning(
        self, task: TaskType, cls: TaskClassification,
        primary: ModelConfig, fallback: ModelConfig,
    ) -> str:
        lang_note = {"cn": "中文", "en": "英文", "mixed": "中英混合"}[cls.language]
        domain_note = {"academic_paper": "学术论文", "financial_report": "金融报告", "general": "通用"}[cls.domain]
        return (
            f"任务={task.value} | 语言={lang_note} | 领域={domain_note} | "
            f"置信度={cls.confidence:.0%} | "
            f"首选={primary.provider}/{primary.model_id} "
            f"(CN={primary.chinese_quality:.1f}/EN={primary.english_quality:.1f}/代码={primary.code_quality:.1f}) | "
            f"备选={fallback.provider}/{fallback.model_id} | "
            f"关键词={cls.keywords[:3]}"
        )

    def _estimate_cost(self, cfg: ModelConfig) -> str:
        return {"low": "~$0.1/M", "medium": "~$0.5/M", "high": "~$2/M", "highest": "~$15/M"}[cfg.cost_tier]

    def _estimate_latency(self, cfg: ModelConfig, cls: TaskClassification) -> str:
        base = {"fast": "5-15s", "medium": "15-60s", "slow": "60-180s"}[cfg.speed]
        # 论文写作类任务需要更长时间
        if cls.task_type in (TaskType.DRAFT_WRITING_CN, TaskType.DRAFT_WRITING_EN,
                             TaskType.LITERATURE_SYNTHESIS):
            return base + " (长输出可能翻倍)"
        return base


# ─── 主路由器 ──────────────────────────────────────────────────────────────

class ModelRouter:
    """智能模型路由器——统一入口。

    Usage:
        router = ModelRouter()
        choice = router.route("帮我综述一下关税政策对A股的影响")
        print(f"使用模型: {choice.primary}")
        print(f"原因: {choice.reasoning}")
    """

    def __init__(self):
        self.classifier = TaskClassifier()
        self.selector = ModelSelector()

    def route(self, user_input: str) -> ModelChoice:
        """对用户输入进行分类并选择最优模型。"""
        classification = self.classifier.classify(user_input)
        choice = self.selector.select(classification)

        logger.info(f"ModelRouter: {classification.task_type.value} → {choice.primary}")
        return choice

    def route_by_task(self, task: TaskType) -> ModelChoice:
        """直接按任务类型路由（绕过分类器）。"""
        cls = TaskClassification(
            task_type=task, confidence=1.0, keywords=[], domain="general", language="mixed"
        )
        return self.selector.select(cls)

    def generate_prompt_with_context(
        self,
        user_input: str,
        *,
        include_routing: bool = True,
        include_examples: bool = False,
    ) -> tuple[str, ModelChoice]:
        """生成带路由上下文的提示词。

        Returns
        -------
        (modified_prompt, model_choice)
            modified_prompt: 加入路由上下文的提示词
            model_choice: 模型选择结果
        """
        choice = self.route(user_input)

        if not include_routing:
            return user_input, choice

        context = f"""[系统指令 - 路由上下文]
任务类型: {choice.task_type.value}
语言: 中文 | 领域: 经济金融学术研究
选用模型: {choice.primary} (primary) / {choice.fallback} (fallback)
成本: {choice.cost_estimate} | 预期延迟: {choice.expected_latency}

请根据上述任务类型生成高质量输出。
"""

        # 对话类输入直接追加
        return context + "\n\n" + user_input, choice

    def batch_route(self, inputs: list[str]) -> list[ModelChoice]:
        """批量路由。"""
        return [self.route(inp) for inp in inputs]

    def get_available_models(self) -> dict[str, bool]:
        """返回可用模型列表。"""
        return {mid: cfg.is_available() for mid, cfg in MODELS.items()}


# ─── 使用示例 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    router = ModelRouter()

    test_inputs = [
        "帮我综述一下关税政策对A股出口型企业创新的影响",
        "帮我设计一个DID实证策略",
        "写一个Python脚本进行面板数据回归",
        "这篇论文的主要贡献是什么？",
        "有什么研究想法关于数字金融",
        "润色一下这段英文摘要",
        "review一下我的研究设计",
        "帮我查一下最近3年的文献",
    ]

    print("Model Router Demo")
    print("=" * 80)
    for inp in test_inputs:
        choice = router.route(inp)
        print(f"\n输入: {inp[:40]}...")
        print(f"  任务: {choice.task_type.value} | 置信: {choice.confidence:.0%}")
        print(f"  模型: {choice.primary} | 成本: {choice.cost_estimate}")
