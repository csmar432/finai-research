#!/usr/bin/env python3
"""
论文质量评分器 (Paper Quality Scorer)
====================================
对论文的学术质量进行多维度自动评估。

核心功能：
1. 六维度评分：清晰度、创新性、方法论、证据充分性、文献覆盖、可复现性
2. 自动生成改进建议
3. 与实验追踪系统集成
4. 输出标准化的评审报告

参考 ACL/NeurIPS 评审标准设计。

使用方法：
    from scripts.paper_quality_scorer import PaperQualityScorer, PaperReview

    scorer = PaperQualityScorer()
    review = scorer.score("path/to/paper.pdf")
    print(review.to_markdown())

    suggestions = scorer.suggest_improvements(review)
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ai_router import AI, Task

# ═════════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═════════════════════════════════════════════════════════════════════════════════


@dataclass
class DimensionScore:
    """单维度评分"""
    dimension: str               # 维度名
    score: float              # 分数 (0-10)
    weight: float             # 权重
    max_score: float = 10.0  # 最高分
    evidence: list[str] = field(default_factory=list)  # 支撑证据
    issues: list[str] = field(default_factory=list)   # 问题列表
    suggestions: list[str] = field(default_factory=list)  # 改进建议

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PaperReview:
    """
    完整的论文评审报告。
    """
    review_id: str
    paper_path: str
    paper_title: str
    overall_score: float          # 综合分数 (0-10)
    dimension_scores: list[DimensionScore]
    generated_at: str
    reviewer_notes: str = ""    # 评审笔记
    strength_summary: str = ""  # 优势总结
    weakness_summary: str = ""   # 劣势总结

    def to_dict(self) -> dict:
        return asdict(self)

    def get_dimension(self, dimension: str) -> DimensionScore | None:
        """获取指定维度"""
        for ds in self.dimension_scores:
            if ds.dimension == dimension:
                return ds
        return None

    def weighted_score(self) -> float:
        """计算加权总分"""
        total_weight = sum(ds.weight for ds in self.dimension_scores)
        weighted = sum(ds.score * ds.weight for ds in self.dimension_scores)
        return weighted / total_weight if total_weight > 0 else 0

    def to_markdown(self) -> str:
        """导出为 Markdown 格式"""
        dimension_names = {
            "clarity": "表达清晰度",
            "novelty": "创新性",
            "methodology": "方法论严谨性",
            "evidence": "实证证据充分性",
            "related_work": "文献覆盖完整性",
            "reproducibility": "可复现性",
        }

        lines = [
            "# 论文评审报告",
            "",
            f"**论文**: {self.paper_title}",
            f"**文件**: {self.paper_path}",
            f"**评审时间**: {self.generated_at}",
            f"**综合评分**: {self.overall_score:.1f}/10",
            "",
            "---",
            "",
            "## 各维度评分",
            "",
        ]

        # 雷达图数据（用于文本可视化）
        radar_data = []
        for ds in self.dimension_scores:
            dim_name = dimension_names.get(ds.dimension, ds.dimension)
            score_bar = "█" * int(ds.score) + "░" * (10 - int(ds.score))

            lines.append(f"### {dim_name} ({ds.score:.1f}/10)")
            lines.append(f"[{score_bar}]")
            lines.append("")

            if ds.evidence:
                lines.append("**支撑证据**:")
                for e in ds.evidence[:3]:
                    lines.append(f"- {e}")
                lines.append("")

            if ds.issues:
                lines.append("**主要问题**:")
                for issue in ds.issues[:3]:
                    lines.append(f"- {issue}")
                lines.append("")

            if ds.suggestions:
                lines.append("**改进建议**:")
                for s in ds.suggestions[:3]:
                    lines.append(f"- {s}")
                lines.append("")

            radar_data.append(f"{dim_name}:{ds.score:.1f}")

        lines.extend([
            "---",
            "",
            "## 总结",
            "",
        ])

        if self.strength_summary:
            lines.append(f"**优势**: {self.strength_summary}")
            lines.append("")

        if self.weakness_summary:
            lines.append(f"**劣势**: {self.weakness_summary}")
            lines.append("")

        lines.extend([
            "---",
            "",
            f"*由 Paper Quality Scorer 生成 | {datetime.now().isoformat()}*",
        ])

        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ═════════════════════════════════════════════════════════════════════════════════
# 论文质量评分器
# ═════════════════════════════════════════════════════════════════════════════════


class PaperQualityScorer:
    """
    论文质量评分器。

    对论文进行六维度自动评估：
    1. 表达清晰度 (clarity) - 权重 15%
    2. 创新性 (novelty) - 权重 20%
    3. 方法论严谨性 (methodology) - 权重 25%
    4. 实证证据充分性 (evidence) - 权重 20%
    5. 文献覆盖完整性 (related_work) - 权重 10%
    6. 可复现性 (reproducibility) - 权重 10%
    """

    DIMENSIONS = {
        "clarity": {
            "name": "表达清晰度",
            "weight": 0.15,
            "description": "语言表达是否清晰、逻辑是否连贯、格式是否规范",
            "checklist": [
                "摘要是否简洁完整地概括全文",
                "引言是否清晰阐述研究动机",
                "方法论描述是否足够详细可复现",
                "图表是否有清晰的标题和标注",
                "结论是否与实验结果一致",
                "语言是否流畅、无语法错误",
            ],
        },
        "novelty": {
            "name": "创新性",
            "weight": 0.20,
            "description": "研究是否有显著的理论或方法创新",
            "checklist": [
                "是否提出了新的方法/模型/理论",
                "是否解决了现有方法的关键局限",
                "创新点是否明确表述",
                "与现有工作的核心区别是否清晰",
                "是否具有领域影响力潜力",
            ],
        },
        "methodology": {
            "name": "方法论严谨性",
            "weight": 0.25,
            "description": "研究方法是否科学、严谨、适当",
            "checklist": [
                "问题定义是否清晰形式化",
                "方法选择是否有充分论证",
                "实验设计是否合理（对照、随机、重复）",
                "假设检验是否使用适当的统计方法",
                "是否考虑了潜在的内生性问题",
                "是否进行了充分的消融实验",
            ],
        },
        "evidence": {
            "name": "实证证据充分性",
            "weight": 0.20,
            "description": "实验结果是否充分支持论文结论",
            "checklist": [
                "是否在多个数据集上验证",
                "基线方法是否足够强和全面",
                "性能提升是否具有统计显著性",
                "是否报告了置信区间或标准误",
                "是否有负向结果的分析",
                "异常值和离群点是否妥善处理",
            ],
        },
        "related_work": {
            "name": "文献覆盖完整性",
            "weight": 0.10,
            "description": "文献综述是否全面、引用是否恰当",
            "checklist": [
                "是否覆盖了领域内的主要工作",
                "是否准确描述了现有方法的优缺点",
                "引用格式是否规范统一",
                "是否正确引用了原创工作",
                "是否遗漏了近期的重要进展",
            ],
        },
        "reproducibility": {
            "name": "可复现性",
            "weight": 0.10,
            "description": "论文是否提供足够的复现信息",
            "checklist": [
                "是否公开了代码或链接",
                "超参数设置是否完整报告",
                "数据集来源和版本是否明确",
                "随机种子是否固定",
                "运行环境是否说明",
                "计算资源需求是否报告",
            ],
        },
    }

    # ── 经济金融实证论文专项评分维度（2026-06-04 增强）─────────────────

    ECON_FIN_DIMENSIONS = {
        "identification": {
            "name": "识别策略严谨性",
            "weight": 0.25,
            "description": "实证识别策略的选择和论证是否科学",
            "checklist": [
                "是否明确说明了准自然实验的来源",
                "平行趋势假设是否经过检验",
                "是否考虑了潜在的内生性问题（反向因果/遗漏变量/测量误差）",
                "是否进行了工具变量、RD或匹配等内生性处理",
                "样本选择是否存在自选择偏误",
                "处理效应是否具有外部有效性",
            ],
        },
        "robustness": {
            "name": "稳健性检验充分性",
            "weight": 0.20,
            "description": "稳健性检验是否充分覆盖主要威胁",
            "checklist": [
                "是否进行了安慰剂检验",
                "是否进行了PSM或倾向得分截断",
                "是否进行了子样本检验",
                "是否更换了因变量或控制变量",
                "是否进行了DDD（三重差分）稳健性检验",
                "是否进行了IV子样本排除检验",
                "是否报告了聚类稳健标准误",
                "是否进行了预期效应排除检验",
                "是否进行了滞后因变量检验",
            ],
        },
        "data_quality": {
            "name": "数据质量与来源",
            "weight": 0.15,
            "description": "数据来源、处理和质量是否透明",
            "checklist": [
                "数据来源是否明确（CSMAR/Wind/RESSET等）",
                "样本选择标准是否清晰报告",
                "缺失值处理方法是否说明",
                "极端值处理方法（缩尾/剔除）是否报告",
                "变量定义是否有文献依据",
                "是否提供了描述性统计和相关性矩阵",
            ],
        },
        "hypothesis_testing": {
            "name": "假设检验规范性",
            "weight": 0.15,
            "description": "假设检验和统计推断是否规范",
            "checklist": [
                "是否报告了回归系数的标准误或t统计量",
                "是否明确说明了聚类层级",
                "是否进行了多重比较校正",
                "经济显著性与统计显著性是否均进行了讨论",
                "是否进行了效应量的报告和解释",
            ],
        },
        "chinese_journal_compliance": {
            "name": "中文顶刊格式规范",
            "weight": 0.10,
            "description": "是否符合目标期刊的格式要求",
            "checklist": [
                "参考文献格式是否符合GB/T 7714-2015",
                "图表标题是否规范（三线表格式）",
                "是否包含JEL分类号和关键词",
                "摘要长度是否符合期刊要求（约200-300字）",
                "作者信息是否按期刊要求格式",
                "页数是否在期刊限制范围内",
            ],
        },
    }

    def __init__(self, model: str = "deepseek", temperature: float = 0.3,
                 paper_type: str = "general"):
        """
        Initialize the paper quality scorer.

        Parameters
        ----------
        model : str
            LLM model to use for scoring.
        temperature : float
            Sampling temperature for LLM.
        paper_type : str
            Type of paper: "general" (ACL/NeurIPS style) or "econ_fin" (empirical economics/finance).
        """
        self.model = model
        self.temperature = temperature
        self.paper_type = paper_type
        # Use appropriate dimensions based on paper type
        self._active_dimensions = (
            self.ECON_FIN_DIMENSIONS if paper_type == "econ_fin" else self.DIMENSIONS
        )

    def _extract_text(self, paper_path: str) -> str:
        """从论文文件中提取文本"""
        path = Path(paper_path)

        if not path.exists():
            return ""

        if path.suffix == ".pdf":
            try:
                import subprocess
                result = subprocess.run(
                    ["pdftotext", "-layout", str(path), "-"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return result.stdout[:50000]  # 限制长度
            except FileNotFoundError:
                pass

            # Fallback: 使用 pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(path)
                text = ""
                for page in reader.pages[:30]:  # 前30页
                    text += page.extract_text() + "\n"
                return text[:50000]
            except ImportError:
                return f"[PDF文件: {paper_path}]"

        elif path.suffix in [".md", ".txt"]:
            return path.read_text(encoding="utf-8")[:50000]

        elif path.suffix == ".tex":
            # 提取 tex 文件中的文本内容
            content = path.read_text(encoding="utf-8")
            # 移除命令和宏
            content = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', content)
            content = re.sub(r'\\[a-zA-Z]+', '', content)
            return content[:50000]

        return ""

    def _generate_review_prompt(self, text: str, paper_title: str) -> str:
        """生成评审 prompt"""
        dim_checks = []
        for dim_id, dim_info in self.DIMENSIONS.items():
            checks = "\n".join(f"  - {c}" for c in dim_info["checklist"])
            dim_checks.append(f"""
### {dim_info['name']}（权重 {dim_info['weight']:.0%}）
{dim_info['description']}
检查要点：
{checks}
""")

        return self._build_review_prompt(text, paper_title)

    def _build_review_prompt(self, text: str, paper_title: str) -> str:
        """构建评审 prompt（支持 general 和 econ_fin 两种类型）。"""
        dim_checks = []
        json_schema_keys = []

        for dim_id, dim_info in self._active_dimensions.items():
            checks = "\n".join(f"  - {c}" for c in dim_info["checklist"])
            dim_checks.append(f"""
### {dim_info['name']}（权重 {dim_info['weight']:.0%}）
{dim_info['description']}
检查要点：
{checks}
""")
            json_schema_keys.append(dim_id)

        dim_list_str = "\n".join(dim_checks)

        # Build JSON schema dynamically based on paper type
        if self.paper_type == "econ_fin":
            paper_type_intro = (
                "你是一位经济金融实证论文的专业评审人。请对以下中国A股/宏观/金融实证论文进行严格评审。"
            )
            output_schema = self._build_econ_fin_json_schema(json_schema_keys)
        else:
            paper_type_intro = "你是一位专业的学术论文评审人。请对以下论文进行质量评审。"
            output_schema = self._build_general_json_schema()

        return f"""{paper_type_intro}

## 论文信息
标题：{paper_title}
长度：{len(text)} 字符

## 论文内容
{text[:30000]}

## 评审要求

请对论文进行以下维度的评估：

{dim_list_str}

## 输出格式

请严格按以下JSON格式输出（不要有额外文本）：

{output_schema}

请确保输出的JSON格式正确，可以被python的json.loads解析。
"""

    def _build_econ_fin_json_schema(self, dim_keys: list[str]) -> str:
        """为经济金融论文构建 JSON schema。"""
        dim_blocks = []
        for dim_id in dim_keys:
            dim_info = self.ECON_FIN_DIMENSIONS.get(dim_id, {})
            dim_blocks.append(f"""  "{dim_id}": {{
    "score": 0-10的分数,
    "evidence": ["支撑证据1", "支撑证据2"],
    "issues": ["主要问题1", "主要问题2"],
    "suggestions": ["改进建议1", "改进建议2"]
  }}""")
        return f"""{{
{chr(10).join(dim_blocks)}
  "strength_summary": "优势总结（100字以内）",
  "weakness_summary": "劣势总结（100字以内）"
}}"""

    def _build_general_json_schema(self) -> str:
        """为通用论文构建 JSON schema。"""
        return """{
  "clarity": {
    "score": 0-10的分数,
    "evidence": ["支撑证据1", "支撑证据2"],
    "issues": ["主要问题1", "主要问题2"],
    "suggestions": ["改进建议1", "改进建议2"]
  },
  "novelty": {
    "score": 0-10的分数,
    "evidence": [],
    "issues": [],
    "suggestions": []
  },
  "methodology": {
    "score": 0-10的分数,
    "evidence": [],
    "issues": [],
    "suggestions": []
  },
  "evidence": {
    "score": 0-10的分数,
    "evidence": [],
    "issues": [],
    "suggestions": []
  },
  "related_work": {
    "score": 0-10的分数,
    "evidence": [],
    "issues": [],
    "suggestions": []
  },
  "reproducibility": {
    "score": 0-10的分数,
    "evidence": [],
    "issues": [],
    "suggestions": []
  },
  "strength_summary": "优势总结（50字以内）",
  "weakness_summary": "劣势总结（50字以内）"
}}"""

    def score(self, paper_path: str) -> PaperReview:
        """
        对论文进行质量评分。

        Args:
            paper_path: 论文文件路径

        Returns:
            PaperReview: 完整的评审报告
        """
        print(f"\n{'='*70}")
        print("  [PaperQualityScorer] 评审论文")
        print(f"  文件: {paper_path}")
        print(f"{'='*70}")

        # 提取文本
        text = self._extract_text(paper_path)
        if not text:
            print("  ⚠️ 无法提取论文文本")
            return self._empty_review(paper_path, "无法提取文本")

        # 提取标题
        title_match = re.search(r"\\title\{([^}]+)\}", text)
        if title_match:
            paper_title = title_match.group(1)
        else:
            title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            paper_title = title_match.group(1) if title_match else Path(paper_path).stem

        print(f"  标题: {paper_title}")
        print(f"  文本长度: {len(text)} 字符")

        # 调用 LLM 进行评审
        prompt = self._build_review_prompt(text, paper_title)

        result = AI.chat(
            prompt,
            task=Task.RESEARCH,
            model=self.model,
            temperature=self.temperature,
            max_tokens=8192,
        )

        print(f"  耗时: {result.latency_ms/1000:.1f}s | 模型: {result.model_used}")

        # 解析结果
        try:
            review_data = json.loads(result.response)
        except json.JSONDecodeError:
            # 尝试提取 JSON
            json_match = re.search(r"\{[\s\S]*\}", result.response)
            if json_match:
                review_data = json.loads(json_match.group(0))
            else:
                print("  ⚠️ 无法解析评审结果")
                return self._empty_review(paper_path, paper_title)

        # 构建 DimensionScore 列表（使用当前激活的维度）
        dimension_scores = []
        total_weighted = 0.0
        total_weight = 0.0

        for dim_id, dim_info in self._active_dimensions.items():
            if dim_id in review_data:
                data = review_data[dim_id]
                ds = DimensionScore(
                    dimension=dim_id,
                    score=float(data.get("score", 5)),
                    weight=dim_info["weight"],
                    evidence=data.get("evidence", []),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                )
            else:
                ds = DimensionScore(
                    dimension=dim_id,
                    score=5.0,
                    weight=dim_info["weight"],
                    evidence=[],
                    issues=["未提供该维度评估"],
                    suggestions=[],
                )

            dimension_scores.append(ds)
            total_weighted += ds.score * ds.weight
            total_weight += ds.weight

        overall_score = total_weighted / total_weight if total_weight > 0 else 0

        review = PaperReview(
            review_id=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            paper_path=paper_path,
            paper_title=paper_title,
            overall_score=round(overall_score, 2),
            dimension_scores=dimension_scores,
            generated_at=datetime.now().isoformat(),
            strength_summary=review_data.get("strength_summary", ""),
            weakness_summary=review_data.get("weakness_summary", ""),
        )

        print(f"  ✅ 评审完成 | 综合评分: {overall_score:.1f}/10")

        return review

    def _empty_review(self, paper_path: str, title: str) -> PaperReview:
        """返回空评审"""
        dimension_scores = []
        for dim_id, dim_info in self._active_dimensions.items():
            dimension_scores.append(DimensionScore(
                dimension=dim_id,
                score=0,
                weight=dim_info["weight"],
                evidence=[],
                issues=["无法评审"],
                suggestions=["请检查文件是否存在或格式是否支持"],
            ))

        return PaperReview(
            review_id=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            paper_path=paper_path,
            paper_title=title,
            overall_score=0,
            dimension_scores=dimension_scores,
            generated_at=datetime.now().isoformat(),
            strength_summary="",
            weakness_summary="无法评审该论文",
        )

    def suggest_improvements(self, review: PaperReview) -> list[str]:
        """
        基于评审生成改进建议。

        Args:
            review: 评审报告

        Returns:
            改进建议列表
        """
        suggestions = []

        # 按权重排序，找出最需要改进的维度
        sorted_dims = sorted(
            review.dimension_scores,
            key=lambda x: x.score * x.weight,
        )

        dimension_names = {
            "clarity": "表达清晰度",
            "novelty": "创新性",
            "methodology": "方法论严谨性",
            "evidence": "实证证据充分性",
            "related_work": "文献覆盖完整性",
            "reproducibility": "可复现性",
        }

        for dim in sorted_dims[:3]:  # 改进最多的3个维度
            if dim.score < 7:
                dim_name = dimension_names.get(dim.dimension, dim.dimension)
                suggestions.append(f"**[{dim_name}]**")

                for issue in dim.issues[:2]:
                    suggestions.append(f"  - 问题: {issue}")

                for suggestion in dim.suggestions[:2]:
                    suggestions.append(f"  - 建议: {suggestion}")

        return suggestions

    def compare_reviews(
        self,
        review1: PaperReview,
        review2: PaperReview,
    ) -> dict:
        """
        对比两份评审报告。

        Returns:
            对比结果
        """
        comparison = {
            "overall_diff": review2.overall_score - review1.overall_score,
            "dimension_diffs": {},
        }

        for ds1 in review1.dimension_scores:
            ds2 = review2.get_dimension(ds1.dimension)
            if ds2:
                comparison["dimension_diffs"][ds1.dimension] = {
                    "before": ds1.score,
                    "after": ds2.score,
                    "diff": ds2.score - ds1.score,
                }

        return comparison

    def batch_score(self, paper_paths: list[str]) -> list[PaperReview]:
        """
        批量评分。

        Args:
            paper_paths: 论文文件路径列表

        Returns:
            评审报告列表
        """
        reviews = []
        for i, path in enumerate(paper_paths, 1):
            print(f"\n[{i}/{len(paper_paths)}] 评审: {path}")
            try:
                review = self.score(path)
                reviews.append(review)
            except Exception as e:
                print(f"  ⚠️ 评审失败: {e}")

        return reviews

    def save_review(self, review: PaperReview, filepath: Path | None = None):
        """保存评审报告"""
        if filepath is None:
            safe_name = Path(review.paper_path).stem
            review_dir = Path(__file__).parent.parent / "knowledge" / "reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            filepath = review_dir / f"{safe_name}_review.json"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(review.to_json())

        print(f"  💾 评审已保存: {filepath}")

    def save_review_markdown(self, review: PaperReview, filepath: Path | None = None):
        """保存评审报告为 Markdown"""
        if filepath is None:
            safe_name = Path(review.paper_path).stem
            review_dir = Path(__file__).parent.parent / "knowledge" / "reviews"
            review_dir.mkdir(parents=True, exist_ok=True)
            filepath = review_dir / f"{safe_name}_review.md"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(review.to_markdown())

        print(f"  💾 评审已保存: {filepath}")


# ═════════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="论文质量评分器")
    parser.add_argument("--paper", "-p", required=True, help="论文文件路径")
    parser.add_argument("--output", "-o", help="输出路径")
    parser.add_argument("--format", "-f", choices=["markdown", "json", "both"], default="markdown", help="输出格式")
    parser.add_argument("--save", "-s", action="store_true", help="保存到知识库")
    parser.add_argument("--batch", "-b", help="批量评分（文件夹路径）")

    args = parser.parse_args()

    scorer = PaperQualityScorer()

    if args.batch:
        folder = Path(args.batch)
        if folder.is_dir():
            paper_files = list(folder.glob("*.pdf")) + list(folder.glob("*.md"))
            reviews = scorer.batch_score([str(p) for p in paper_files])

            print(f"\n{'='*70}")
            print("  批量评审完成")
            print(f"{'='*70}")
            for review in reviews:
                print(f"  {review.paper_title}: {review.overall_score:.1f}/10")
        else:
            print(f"文件夹不存在: {folder}")
        return

    # 单篇评审
    review = scorer.score(args.paper)

    if args.format == "markdown" or args.format == "both":
        md = review.to_markdown()
        if args.output:
            Path(args.output if args.output.endswith(".md") else args.output + ".md").write_text(md, encoding="utf-8")
        else:
            print(f"\n{'='*70}")
            print(md)

    if args.format == "json" or args.format == "both":
        json_str = review.to_json()
        if args.output:
            json_path = args.output if args.output.endswith(".json") else args.output + ".json"
            Path(json_path).write_text(json_str, encoding="utf-8")

    if args.save:
        scorer.save_review(review)
        scorer.save_review_markdown(review)

    print(f"\n{'='*70}")
    print(f"  ✅ 评审完成 | 综合评分: {review.overall_score:.1f}/10")
    print(f"{'='*70}")

    # 打印改进建议
    suggestions = scorer.suggest_improvements(review)
    if suggestions:
        print("\n改进建议:")
        for s in suggestions:
            print(f"  {s}")


if __name__ == "__main__":
    main()
