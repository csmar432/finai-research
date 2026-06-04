#!/usr/bin/env python3
"""
内容审查层
============
DeepSeek 审查 + GPT 修复双阶段流水线。

工作流程：
  1. DeepSeek 审查（Review）  → 发现问题，给出评分和建议
  2. GPT-5.5 修复（Fix）    → 根据审查意见重写内容

使用方式：
  from scripts.review_layer import ReviewLayer, ReviewType

  layer = ReviewLayer()
  result = layer.review_and_fix(
      content=my_text,
      content_type=ReviewType.PAPER_CHAPTER,
      context={"topic": "深度学习量化交易", "venue": "NeurIPS"},
  )
  print(result.fixed_content)
"""

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ─── 配置路径 ────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent
CACHE_DIR = SCRIPT_DIR / ".cache" / "review_layer"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── 审查类型 ────────────────────────────────────────────

class ReviewType(Enum):
    LITERATURE_REVIEW = "literature_review"    # 文献综述
    PAPER_SUMMARY    = "paper_summary"        # 论文摘要
    PAPER_CHAPTER    = "paper_chapter"        # 论文章节（引言/方法/实验/结论）
    FINANCIAL_REPORT = "financial_report"      # 财务研报
    COVER_LETTER     = "cover_letter"         # 投稿信
    RESPONSE_LETTER  = "response_letter"      # 回复信


# ─── 审查结果 ────────────────────────────────────────────

@dataclass
class ReviewResult:
    original_content: str
    review_content: str          # DeepSeek 的审查意见
    fixed_content: str            # GPT-5.5 根据审查修复后的内容
    issues: list[str]            # 发现的问题列表
    overall_score: float         # 1-10 分
    review_model: str
    fix_model: str
    review_latency_ms: float
    fix_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "issues": self.issues,
            "overall_score": self.overall_score,
            "review_model": self.review_model,
            "fix_model": self.fix_model,
            "review_latency_ms": round(self.review_latency_ms, 1),
            "fix_latency_ms": round(self.fix_latency_ms, 1),
        }


# ─── 审查层核心 ─────────────────────────────────────────

class ReviewLayer:
    """
    DeepSeek 审查 + GPT 修复双阶段流水线。

    支持的内容类型：文献综述、论文摘要、论文章节、研报、投稿信、回复信。
    每个类型有专属的审查 prompt 和评分维度。

    使用类级单例 router，避免每次实例化都重新构建 AIRouter（耗时 + 重复初始化开销）。
    首次调用时自动初始化，后续调用共享同一 router 实例。
    """

    _router: "LLMGateway | None" = None

    def __init__(self, use_cache: bool = True):
        if ReviewLayer._router is None:
            import sys as _sys
            _sys.path.insert(0, str(SCRIPT_DIR))
            from scripts.core.llm_gateway import LLMGateway
            ReviewLayer._router = LLMGateway(memory=None, use_cache=use_cache)
        self.router = ReviewLayer._router
        self._use_cache = use_cache

    def set_cache(self, enabled: bool):
        """运行时切换缓存开关（不影响已缓存的结果）。"""
        self._use_cache = enabled

    # ── 公开接口 ────────────────────────────────────────

    def review_and_fix(
        self,
        content: str,
        content_type: ReviewType,
        context: dict | None = None,
        skip_review: bool = False,
        skip_fix: bool = False,
    ) -> ReviewResult:
        """
        完整流程：DeepSeek 审查 → GPT-5.5 修复。

        Args:
            content: 待审查的内容
            content_type: 内容类型（决定使用哪个审查模板）
            context: 额外上下文，如 {"topic": "深度学习", "venue": "NeurIPS"}
            skip_review: True = 直接修复（不审查）
            skip_fix: True = 只审查不修复

        Returns:
            ReviewResult：包含原始内容、审查意见、修复后内容、评分、耗时
        """
        context = context or {}
        t0 = time.time()
        review_content = ""
        issues: list[str] = []
        score = 0.0
        review_latency = 0.0
        review_model_used = "(skipped)"

        # Step 1：DeepSeek 审查
        if not skip_review:
            review_prompt = self._build_review_prompt(content, content_type, context)
            review_result = self.router.chat(
                user_input=review_prompt,
                task=None,
                model="deepseek",
                temperature=0.3,
                max_tokens=2048,
            )
            review_content = review_result.response.strip()
            review_latency = time.time() - t0
            issues, score = self._parse_review(review_content, content_type)
            review_model_used = review_result.model_used

        # Step 2：GPT-5.5 修复
        fixed_content = content
        fix_latency = 0.0
        fix_model_used = ""
        if not skip_fix and issues:
            t_fix = time.time()
            fix_prompt = self._build_fix_prompt(content, review_content, content_type, context)
            fix_result = self.router.chat(
                user_input=fix_prompt,
                task=None,
                model="gpt5",
                temperature=0.5,
                max_tokens=8192,
            )
            fixed_content = fix_result.response.strip()
            fix_latency = time.time() - t_fix
            fix_model_used = fix_result.model_used

        return ReviewResult(
            original_content=content,
            review_content=review_content,
            fixed_content=fixed_content,
            issues=issues,
            overall_score=score,
            review_model=review_model_used,
            fix_model=fix_model_used or "gpt-5.5",
            review_latency_ms=review_latency * 1000,
            fix_latency_ms=fix_latency * 1000,
        )

    def review_only(
        self,
        content: str,
        content_type: ReviewType,
        context: dict | None = None,
    ) -> tuple[str, list[str], float]:
        """仅审查，不修复。返回 (审查意见, 问题列表, 评分)。"""
        result = self.review_and_fix(content, content_type, context, skip_fix=True)
        return result.review_content, result.issues, result.overall_score

    def fix_only(
        self,
        content: str,
        content_type: ReviewType,
        context: dict | None = None,
    ) -> str:
        """直接修复，不审查（跳过已知无问题）。"""
        result = self.review_and_fix(content, content_type, context, skip_review=True)
        return result.fixed_content

    # ── 内部方法 ─────────────────────────────────────────

    def _build_review_prompt(
        self, content: str, content_type: ReviewType, context: dict
    ) -> str:
        """根据内容类型构建审查 prompt。"""
        topic = context.get("topic", "未知主题")
        venue = context.get("venue", "未知期刊")

        base = {
            ReviewType.LITERATURE_REVIEW: self._review_literature_review(content, topic),
            ReviewType.PAPER_SUMMARY:    self._review_paper_summary(content, topic),
            ReviewType.PAPER_CHAPTER:    self._review_paper_chapter(content, topic, venue),
            ReviewType.FINANCIAL_REPORT: self._review_financial_report(content, topic),
            ReviewType.COVER_LETTER:     self._review_cover_letter(content, venue),
            ReviewType.RESPONSE_LETTER:  self._review_response_letter(content),
        }
        return base.get(content_type, self._review_paper_chapter(content, topic, venue))

    def _build_fix_prompt(
        self, content: str, review: str, content_type: ReviewType, context: dict
    ) -> str:
        """根据审查意见构建修复 prompt。"""
        topic = context.get("topic", "未知主题")
        venue = context.get("venue", "未知期刊")

        base = {
            ReviewType.LITERATURE_REVIEW: self._fix_literature_review(content, review, topic),
            ReviewType.PAPER_SUMMARY:    self._fix_paper_summary(content, review, topic),
            ReviewType.PAPER_CHAPTER:    self._fix_paper_chapter(content, review, topic, venue),
            ReviewType.FINANCIAL_REPORT: self._fix_financial_report(content, review, topic),
            ReviewType.COVER_LETTER:     self._fix_cover_letter(content, review, venue),
            ReviewType.RESPONSE_LETTER:  self._fix_response_letter(content, review),
        }
        return base.get(content_type, self._fix_paper_chapter(content, review, topic, venue))

    def _parse_review(self, review_text: str, content_type: ReviewType) -> tuple[list[str], float]:
        """从审查文本中提取问题列表和评分。"""
        issues = []

        # 提取评分
        score = 5.0
        for line in review_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("综合评分:") or stripped.startswith("评分:"):
                try:
                    num = float(stripped.split(":")[-1].strip().split("/")[0].replace("分", ""))
                    score = min(max(num, 1.0), 10.0)
                except (ValueError, IndexError):
                    pass

        # 提取问题（以 - 或 * 开头的行）
        for line in review_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                issue_text = stripped[2:].strip()
                if 10 < len(issue_text) < 200:
                    issues.append(issue_text)

        return issues[:10], score

    # ════════════════════════════════════════════════════
    #  审查 Prompt 模板
    # ════════════════════════════════════════════════════

    def _review_literature_review(self, content: str, topic: str) -> str:
        return f"""你是一位资深学术审稿人。请对以下文献综述进行严格审查。

## 研究主题
{topic}

## 待审查内容
---
{content[:8000]}
---

## 审查维度（请逐项检查）

### 1. 结构完整性（1-10分）
- 是否包含：研究概述、方法对比、核心发现、变量梳理、局限分析、未来方向、对你研究的启发？
- 各部分比例是否合理？

### 2. 学术规范性（1-10分）
- 语言是否专业、准确、无口语化？
- 是否正确引用论文序号（如 [1]、[2]）？
- 是否有夸大、绝对化表述？

### 3. 内容准确性（1-10分）
- 对各论文方法的描述是否准确？
- 主要发现和结论是否忠实原文？

### 4. 逻辑连贯性（1-10分）
- 各段落之间是否有清晰的逻辑衔接？
- 是否存在重复或跑题？

### 5. 研究启发价值（1-10分）
- 对你研究的指导意义是否具体可行？

## 输出格式
请严格按照以下格式输出，不要输出其他内容：

综合评分: X.X/10

主要问题：
- [问题1，简洁描述]
- [问题2，简洁描述]
- ...

具体建议：
[分点列出改进建议，每点不超过2句话]"""

    def _review_paper_summary(self, content: str, topic: str) -> str:
        return f"""你是一位资深学术审稿人。请对以下论文摘要进行严格审查。

## 论文主题
{topic}

## 待审查内容
---
{content[:4000]}
---

## 审查维度

### 1. 内容完整性（1-10分）
- 是否包含：背景问题、研究动机、核心方法、主要结果、关键贡献？

### 2. 学术规范性（1-10分）
- 语言是否精炼、准确、无歧义？
- 是否避免了非学术化表达？

### 3. 创新性表达（1-10分）
- 核心贡献是否被清晰突出？
- 是否避免了空洞的修饰词？

### 4. 可读性（1-10分）
- 结构是否清晰（背景→方法→结果→贡献）？
- 长度是否适中（中文摘要 300-500 字）？

## 输出格式
请严格按照以下格式输出：

综合评分: X.X/10

主要问题：
- [问题简述]
- ...

具体建议：
[分点列出]"""

    def _review_paper_chapter(self, content: str, topic: str, venue: str) -> str:
        return f"""你是一位资深学术审稿人，专注于 {venue} 级别论文。请对以下论文章节进行严格审查。

## 论文主题
{topic}

## 目标期刊
{venue}

## 待审查内容
---
{content[:8000]}
---

## 审查维度

### 1. 学术写作规范（1-10分）
- 语言是否专业、精确、避免口语化？
- 公式和术语使用是否正确？
- 图表引用是否规范？

### 2. 逻辑严密性（1-10分）
- 论点是否有充分证据支撑？
- 因果关系是否清晰？
- 是否存在逻辑跳跃或未论证的假设？

### 3. 完整性（1-10分）
- 关键细节是否充分展开？
- 相关工作是否被充分讨论？
- 局限性是否被诚实讨论？

### 4. 可复现性（1-10分）
- 方法描述是否足够详细？
- 超参数、数据集、评估指标是否明确？

### 5. 与顶会标准的差距（1-10分）
- 距离 {venue} 录稿标准还差哪些？

## 输出格式
请严格按照以下格式输出：

综合评分: X.X/10

主要问题：
- [问题简述，附具体位置]
- ...

具体建议：
[分点列出，每点说明具体修改方向]"""

    def _review_financial_report(self, content: str, topic: str) -> str:
        return f"""你是一位资深金融分析师。请对以下财务研报进行严格审查。

## 研究对象
{topic}

## 待审查内容
---
{content[:8000]}
---

## 审查维度

### 1. 数据准确性（1-10分）
- 财务数据是否与公开披露一致？
- 数据来源是否标注清楚？

### 2. 逻辑严密性（1-10分）
- 估值方法是否合理（DCF 参数假设是否合理）？
- 投资逻辑是否有充分支撑？

### 3. 风险揭示（1-10分）
- 主要风险是否被充分识别和讨论？
- 风险提示是否醒目？

### 4. 表达规范性（1-10分）
- 格式是否符合头部券商研报标准？
- 图表是否清晰、标注完整？

## 输出格式
请严格按照以下格式输出：

综合评分: X.X/10

主要问题：
- [问题简述]
- ...

具体建议：
[分点列出]"""

    def _review_cover_letter(self, content: str, venue: str) -> str:
        return f"""你是一位资深学术期刊编辑。请对以下 Cover Letter 进行审查。

## 目标期刊
{venue}

## 待审查内容
---
{content[:2000]}
---

## 审查维度

### 1. 结构完整性（1-10分）
- 是否包含：投稿声明、论文概述、主要贡献、适合性说明、通讯作者信息？

### 2. 语言规范性（1-10分）
- 语气是否专业、礼貌、自信但不傲慢？
- 是否避免了过于绝对或夸大的表述？

### 3. 贡献突出性（1-10分）
- 主要贡献是否被清晰、有力地呈现？
- 是否针对 {venue} 的读者群做了定制化说明？

## 输出格式
综合评分: X.X/10

主要问题：
- [问题简述]
- ...

具体建议：
[分点列出]"""

    def _review_response_letter(self, content: str) -> str:
        return f"""你是一位资深期刊编辑。请对以下审稿回复信进行审查。

## 待审查内容
---
{content[:5000]}
---

## 审查维度

### 1. 回应完整性（1-10分）
- 是否逐条回应了所有审稿意见？
- 有无遗漏的审稿意见？

### 2. 态度适当性（1-10分）
- 语气是否礼貌、诚恳？
- 是否避免了防御性或对抗性表达？

### 3. 修改说明质量（1-10分）
- 对审稿意见的回应是否具体、有据可查？
- 是否引用了修改位置（如 "见 Section 3.2"）？

### 4. 表格完整性（1-10分）
- 修改摘要表是否完整记录了所有修改？

## 输出格式
综合评分: X.X/10

主要问题：
- [问题简述]
- ...

具体建议：
[分点列出]"""

    # ════════════════════════════════════════════════════
    #  修复 Prompt 模板
    # ════════════════════════════════════════════════════

    def _fix_literature_review(self, content: str, review: str, topic: str) -> str:
        return f"""你是一位专业学术写作专家。请根据以下审查意见对文献综述进行精修。

## 研究主题
{topic}

## 原始文献综述
---
{content[:8000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. **逐条解决**审查意见中的每个问题
2. **保持原文长度**基本不变（允许 ±20% 调整）
3. **不要删除**原文已有的正确内容，只修改有问题的部分
4. **保持学术语言**的专业性和准确性
5. **引用格式**保持 [序号] 风格

请直接输出修复后的完整文献综述，不要添加说明文字："""

    def _fix_paper_summary(self, content: str, review: str, topic: str) -> str:
        return f"""你是一位专业学术写作专家。请根据以下审查意见对论文摘要进行精修。

## 论文主题
{topic}

## 原始摘要
---
{content[:4000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. 保持标准结构：背景 → 方法 → 结果 → 贡献
2. 中文摘要控制在 300-500 字
3. 精炼语言，删除冗余修饰词
4. 确保核心贡献被清晰突出

请直接输出修复后的完整摘要，不要添加说明文字："""

    def _fix_paper_chapter(self, content: str, review: str, topic: str, venue: str) -> str:
        return f"""你是一位专业学术写作专家，精通 {venue} 级别论文写作规范。请根据以下审查意见对论文章节进行精修。

## 论文主题
{topic}

## 目标期刊
{venue}

## 原始章节内容
---
{content[:8000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. **严格遵循** {venue} 的写作规范
2. **逐条解决**审查意见中的每个问题
3. **保持原有结构**，不要打乱章节框架
4. **学术语言**：精确、专业、避免主观夸大
5. **引用规范**：公式编号、图表引用、文献引用必须准确
6. **保持长度**，不允许删减核心内容，扩展不充分的说明

请直接输出修复后的完整章节内容，不要添加说明文字或注释："""

    def _fix_financial_report(self, content: str, review: str, topic: str) -> str:
        return f"""你是一位专业金融分析师。请根据以下审查意见对财务研报进行精修。

## 研究对象
{topic}

## 原始研报
---
{content[:8000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. 逐条解决审查意见中的问题
2. 保持头部券商研报的标准格式
3. 数据必须准确，假设必须明确
4. 风险提示必须醒目且全面

请直接输出修复后的完整研报，不要添加说明文字："""

    def _fix_cover_letter(self, content: str, review: str, venue: str) -> str:
        return f"""你是一位专业学术写作专家。请根据以下审查意见对 Cover Letter 进行精修。

## 目标期刊
{venue}

## 原始内容
---
{content[:2000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. 语气专业、礼貌、自信
2. 主要贡献必须清晰、有力
3. 适合性说明要针对 {venue} 定制
4. 长度控制在 300-500 词

请直接输出修复后的完整 Cover Letter，不要添加说明文字："""

    def _fix_response_letter(self, content: str, review: str) -> str:
        return f"""你是一位资深审稿回复写作专家。请根据以下审查意见对 Response Letter 进行精修。

## 原始回复信
---
{content[:5000]}
---

## 审查意见
---
{review}
---

## 修复要求

1. 确保逐条回应所有审稿意见
2. 语气礼貌、诚恳，有据可查
3. 修改说明必须引用具体修改位置（如 "见 Section 3.2, Figure 2"）
4. 修改摘要表必须完整

请直接输出修复后的完整回复信，不要添加说明文字："""


# ─── 便捷入口 ─────────────────────────────────────────────

def quick_review(
    content: str,
    content_type: ReviewType = ReviewType.PAPER_CHAPTER,
    **context,
) -> ReviewResult:
    """
    快速审查：自动加载路由，一行调用。

    示例：
        result = quick_review(论文章节文本, ReviewType.PAPER_CHAPTER, topic="量化交易", venue="NeurIPS")
        print(result.fixed_content)
        print(result.issues)
    """
    layer = ReviewLayer()
    return layer.review_and_fix(content, content_type, context)
