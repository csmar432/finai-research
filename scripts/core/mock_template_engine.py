"""MockTemplateEngine — last-resort fallback when all LLM backends fail.

PR3 (Audit 2026-06-27).

设计原则：
  1. 当 DeepSeek / Relay / Ollama 全部不可用时，MockTemplateEngine 产出
     结构化的、可读的模板内容（不是乱码）
  2. 内容来源于内置模板（基于顶刊论文结构），不是随机生成
  3. 明确标注 "[MOCK — 无 LLM 后端]" 前缀，防止混入正式产物
  4. 仅用于：outline / lit_review / design 阶段（论文正文仍要求 LLM）

使用：
  from scripts.core.mock_template_engine import MockTemplateEngine
  engine = MockTemplateEngine()
  result = engine.generate("outline", topic="碳排放权交易与绿色创新", venue="经济研究")
  print(result.content)   # 结构化大纲

  # 作为 AIRouter 的最终 fallback：
  result = ai_router.chat(...)
  if result.model_used == "mock_template":
      print("⚠️  无 LLM 后端，使用模板生成")
"""

from __future__ import annotations

__all__ = [
    "MockTemplateEngine",
    "MockTemplateEngineError",
    "TASK_TEMPLATES",
]

import time
from dataclasses import dataclass
from typing import Any

logger = __import__("logging").getLogger(__name__)


class MockTemplateEngineError(Exception):
    """MockTemplateEngine 内部错误（不应该发生）。"""


# ─── Task Types ────────────────────────────────────────────────────────────────


class MockTask:
    OUTLINE = "outline"
    LIT_REVIEW = "lit_review"
    DESIGN = "design"
    IDEA_REPORT = "idea_report"
    NOVELTY_CHECK = "novelty_check"
    PAPER_ABSTRACT = "abstract"
    GENERAL = "general"


# ─── Templates ────────────────────────────────────────────────────────────────


_TASK_TEMPLATE_MAP: dict[str, dict[str, str]] = {
    MockTask.OUTLINE: {
        "title": "{topic}研究",
        "sections": "1.引言\n2.文献综述\n3.研究设计\n4.实证分析\n5.结论与启示",
    },
    MockTask.LIT_REVIEW: {
        "structure": "### 研究主题：{topic}\n\n#### 1.核心文献（3篇）\n\n#### 2.理论机制\n\n#### 3.研究空白",
    },
    MockTask.DESIGN: {
        "identification": "DID（双重差分）",
        "variables": "因变量: {dep_var}\n自变量: DID × Post × Treat\n控制变量: Size, Lev, ROA, Age, Growth",
    },
    MockTask.IDEA_REPORT: {
        "format": "## 候选研究想法\n\n### 想法1\n- 研究问题\n- 识别策略\n- 数据需求\n- 可行性",
    },
    MockTask.NOVELTY_CHECK: {
        "approach": "1. 在 JF/JFE/RFS/arXiv 检索近3年相关文献\n2. 检查研究问题和识别策略的差异\n3. 评估边际贡献",
    },
    MockTask.PAPER_ABSTRACT: {
        "template": "**背景**：\n**研究问题**：\n**方法**：\n**数据**：\n**结论**：",
    },
    MockTask.GENERAL: {
        "response": "⚠️  [MOCK — 所有 LLM 后端不可用]\n\n主题：{topic}\n\n请配置以下任一 LLM 后端以继续：\n1. DeepSeek: 设置 DEEPSEEK_API_KEY\n2. Ollama: 运行 `ollama serve`（无需 API Key）\n3. Relay: 设置 RELAY_API_KEY",
    },
}


@dataclass
class MockResult:
    """MockTemplateEngine 的输出。

    v2.2 (2026-07-13) 增加 ``is_mock`` 字段，供下游 agent_pipeline.py
    检测并阻止写入有效输出目录（避免占位文本被误当作真结果使用）。
    """
    content: str
    latency_ms: float
    model: str = "mock_template"
    provider: str = "template"
    tokens_used: int = 0
    error: str | None = None
    is_mock: bool = True


# ─── Main Class ───────────────────────────────────────────────────────────────


class MockTemplateEngine:
    """模板驱动的 LLM 替代引擎。

    使用内置模板生成结构化内容，所有输出均含 [MOCK] 前缀。
    """

    def __init__(self):
        self._templates = _TASK_TEMPLATE_MAP

    def generate(
        self,
        task: str,
        topic: str = "",
        venue: str = "经济研究",
        identification: str = "DID",
        dep_var: str = "Y（待定义）",
        indep_var: str = "X（待定义）",
        extra: dict[str, Any] | None = None,
    ) -> MockResult:
        """生成模板内容。

        Args:
            task: 任务类型（outline/lit_review/design/...）
            topic: 研究主题
            venue: 目标期刊
            identification: 识别策略
            dep_var: 因变量名
            indep_var: 自变量名
            extra: 额外参数

        Returns:
            MockResult: 含结构化内容的响应对象
        """
        start = time.time()

        if task not in self._templates:
            task = MockTask.GENERAL

        tmpl = self._templates[task]

        # 用模板变量替换
        if task == MockTask.OUTLINE:
            content = self._render_outline(tmpl, topic, venue)
        elif task == MockTask.LIT_REVIEW:
            content = self._render_lit_review(tmpl, topic)
        elif task == MockTask.DESIGN:
            content = self._render_design(tmpl, topic, identification, dep_var, indep_var)
        elif task == MockTask.IDEA_REPORT:
            content = self._render_idea_report(tmpl, topic)
        elif task == MockTask.NOVELTY_CHECK:
            content = self._render_novelty(tmpl, topic)
        elif task == MockTask.PAPER_ABSTRACT:
            content = self._render_abstract(tmpl, topic)
        else:
            content = tmpl["response"].format(topic=topic)

        return MockResult(
            content=content,
            model="mock_template",
            provider="template",
            latency_ms=(time.time() - start) * 1000,
            tokens_used=len(content),
        )

    def _render_outline(self, tmpl: dict, topic: str, venue: str) -> str:
        sections = tmpl["sections"]
        return f"""# {topic or '[待定研究主题]'}

**⚠️  [MOCK — 所有 LLM 后端不可用，以下为模板大纲，请配置 DeepSeek/Ollama 后填入具体内容]**

**目标期刊**: {venue}
**生成时间**: {time.strftime('%Y-%m-%d %H:%M')}

## 论文结构大纲

{sections}

## 各章摘要指引

### 第1章 引言
- 研究背景与意义
- 研究问题
- 研究贡献（3点）

### 第2章 文献综述
- 理论框架
- 核心文献梳理
- 研究缺口

### 第3章 研究设计
- 数据来源与样本
- 变量定义
- 实证模型

### 第4章 实证分析
- 描述性统计
- 基准回归
- 稳健性检验
- 异质性分析

### 第5章 结论与启示
- 主要结论
- 政策建议
- 研究局限
"""

    def _render_lit_review(self, tmpl: dict, topic: str) -> str:
        return f"""# 文献综述：{topic or '[待定主题]'}

**⚠️  [MOCK — 请配置 LLM 后端后自动生成完整文献综述]**

## 文献综述结构指引

{tmpl['structure'].format(topic=topic or '[待定主题]')}

## 推荐检索路径

1. **中文数据库**: CNKI / CSSCI → 核心期刊
2. **英文数据库**: OpenAlex / Semantic Scholar → JF / JFE / RFS
3. **预印本**: arXiv / NBER Working Papers

## 理论机制

- 机制1: 融资约束渠道
- 机制2: 创新激励渠道
- 机制3: 资源配置渠道
"""

    def _render_design(
        self,
        tmpl: dict,
        topic: str,
        identification: str,
        dep_var: str,
        indep_var: str,
    ) -> str:
        return f"""# 实证研究设计

**⚠️  [MOCK — 请配置 LLM 后端后生成完整研究设计]**

## 识别策略

**推荐**: {tmpl['identification']}
**选择理由**: 基于准自然实验设计，处理组/对照组可清晰划分

## 变量体系

| 变量类型 | 名称 | 测度方法 | 数据来源 |
|---------|------|---------|---------|
| 因变量 | {dep_var} | 见下方 | - |
| 自变量 | {indep_var} | DID交互项 | 政策文件 |
| 控制变量 | Size | ln(总资产) | akshare/Wind |
| 控制变量 | Lev | 资产负债率 | akshare/Wind |
| 控制变量 | ROA | 净利润/总资产 | akshare/Wind |
| 控制变量 | Age | ln(企业年龄) | CSMAR |

## 模型设定

```
Y_it = α + β(DID_it) + γX_it + δ_i + λ_t + ε_it
```

其中 δ_i 为企业固定效应，λ_t 为年份固定效应。

## 稳健性检验清单

- [ ] 替换因变量测度
- [ ] 变更样本窗口
- [ ] 工具变量法
- [ ] 安慰剂检验
- [ ] PSM-DID
"""

    def _render_idea_report(self, tmpl: dict, topic: str) -> str:
        return f"""# 候选研究想法

**⚠️  [MOCK — 请配置 LLM 后端后生成排序研究想法]**

{tmpl['format']}

## 说明

本模板基于以下方向生成候选想法：
- 实证研究（因果识别为核心）
- 数据可行性优先
- 边际贡献可论证

请运行以下命令获取真实想法生成：
```bash
python scripts/agent_pipeline.py --topic "{topic or '[TOPIC]'}"
```
"""

    def _render_novelty(self, tmpl: dict, topic: str) -> str:
        return f"""# 新颖性验证框架

**⚠️  [MOCK — 请配置 LLM 后端后进行完整新颖性检索]**

## 检索策略

{tmpl['approach']}

## 顶刊检索清单

| 期刊 | 优先级 | 检索词 |
|------|--------|--------|
| JF / JFE / RFS | 高 | {topic} |
| JAE / JPE | 高 | 政策 + 创新 |
| 经济研究 | 高 | 环境规制 + 生产率 |
| 金融研究 | 中 | 绿色金融 + 融资 |

## 评估标准

1. **研究问题新**: 现有文献未系统研究
2. **数据新**: 使用新数据集或新代理变量
3. **方法新**: 采用更严格的识别策略
4. **结论新**: 发现与现有文献不同的结论
"""

    def _render_abstract(self, tmpl: dict, topic: str) -> str:
        return f"""# 论文摘要

**⚠️  [MOCK — 请配置 LLM 后端后生成完整摘要]**

{tmpl['template']}

## 摘要要素（按经济研究标准）

1. **背景** (1句): 现实背景 + 文献空白
2. **问题** (1句): 本文研究...
3. **方法** (2句): 基于X数据，采用Y方法
4. **结论** (2-3句): 研究发现...

## 字数要求

- 经济研究: 约300字
- 金融研究: 约300字
- JF/RFS: 约150 words
"""


# ─── AIRouter Integration ──────────────────────────────────────────────────────


def _register_mock_template_fallback(router) -> None:
    """将 MockTemplateEngine 注册为 AIRouter 的最终 fallback。

    在 ai_router.py 的 AIRouter 实例化后调用此函数。
    修改 router._mock_fallback_engine 引用。
    """
    router._mock_fallback = MockTemplateEngine()
    logger.warning(
        "[LLM Fallback] MockTemplateEngine registered as final fallback. "
        "Set DEEPSEEK_API_KEY or run ollama serve for full functionality."
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MockTemplateEngine — 无 LLM 后端时的结构化降级")
    parser.add_argument("--task", default="outline",
                       choices=["outline", "lit_review", "design",
                               "idea_report", "novelty_check", "abstract", "general"],
                       help="生成的任务类型")
    parser.add_argument("--topic", default="碳排放权交易与绿色创新", help="研究主题")
    parser.add_argument("--venue", default="经济研究", help="目标期刊")
    parser.add_argument("--identification", default="DID", help="识别策略")
    args = parser.parse_args()

    engine = MockTemplateEngine()
    result = engine.generate(
        task=args.task,
        topic=args.topic,
        venue=args.venue,
        identification=args.identification,
    )

    print(f"\n⚠️  [MOCK — 无 LLM 后端]")
    print(f"   模型: {result.model}")
    print(f"   耗时: {result.latency_ms:.1f}ms")
    print(f"   token数: {result.tokens_used}")
    print("\n" + "─" * 60)
    print(result.content)


if __name__ == "__main__":
    main()
