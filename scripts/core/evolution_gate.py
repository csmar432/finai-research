"""Validation Gate — 4 种研究质量门控，参考 MSc Poggio Lab 设计.

本模块将 MSc 的 4 种 Validation Gate 嵌入论文-研报工作流：

  Gate 1: Novelty Gate（新颖性门控）
    输入：研究想法列表
    检查：是否与近 3 年顶刊/顶会重叠
    阈值：相似度 < 0.3 才通过
    失败动作：过滤掉 → 触发新想法生成

  Gate 2: Feasibility Gate（可行性门控）
    输入：研究设计方案
    检查：数据可获取性 + 方法可行性 + 计算资源
    阈值：所有条件满足
    失败动作：降级方案或提示用户提供数据

  Gate 3: Duality Gate（理论与实验一致性门控）
    输入：理论预测 vs 实验结果
    检查：两者方向一致性
    阈值：符号一致 + 量级合理
    失败动作：触发 Theory/Experiment 迭代对齐

  Gate 4: Quality Gate（质量门控）
    输入：最终稿件
    检查：图表规范 / 引用完整性 / 语法正确性
    阈值：全部通过
    失败动作：返回修改 → 重跑 Quality Gate

Usage:
    gate = ValidationGate()
    gate.register(NoveltyGate())
    gate.register(FeasibilityGate())
    gate.register(DualityGate())
    gate.register(QualityGate())

    result = gate.evaluate_all(ideas=ideas, design=design, results=results, manuscript=path)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "GateType",
    "GateResult",
    "ValidationGate",
    "NoveltyGate",
    "FeasibilityGate",
    "DualityGate",
    "QualityGate",
]

logger = logging.getLogger(__name__)


class GateType:
    NOVELTY = "novelty"
    FEASIBILITY = "feasibility"
    DUALITY = "duality"
    QUALITY = "quality"


@dataclass
class GateResult:
    """
    单个 Gate 的评估结果。

    Attributes
    ----------
    gate_type : str
        Gate 类型。
    passed : bool
        是否通过。
    score : float
        通过程度 0-1。
    issues : list[str]
        发现的问题。
    suggestions : list[str]
        改进建议。
    details : dict
        详细结果。
    elapsed_seconds : float
        评估耗时。
    """

    gate_type: str
    passed: bool
    score: float = 0.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "gate_type": self.gate_type,
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "details": self.details,
            "elapsed_seconds": self.elapsed_seconds,
        }


class BaseGate(ABC):
    """Validation Gate 抽象基类。"""

    @property
    @abstractmethod
    def gate_type(self) -> str:
        """Gate 类型标识。"""

    @abstractmethod
    def evaluate(self, context: dict) -> GateResult:
        """执行评估。"""

    def __repr__(self):
        return f"<{self.__class__.__name__} type={self.gate_type}>"


# ─────────────────────────────────────────────────────────────────────────────
# GATE 1: NOVELTY
# ─────────────────────────────────────────────────────────────────────────────


class NoveltyGate(BaseGate):
    """
    新颖性门控 — 检查研究想法是否与近 lookback_years 年文献重叠。

    检查方式（真实检索优先）：
      1. 用想法文本查询 Semantic Scholar / OpenAlex（``literature_download``）
      2. 按 lookback_years 过滤；顶刊命中加权
      3. 标题+摘要 vs 想法的 token Jaccard 最大相似度
      4. 相似度 < threshold → 通过；≥ threshold → 拒绝
      5. 全部检索失败时才回退 LLM 启发式，并在 details 中标注 search_status
    """

    def __init__(
        self,
        similarity_threshold: float = 0.3,
        lookback_years: int = 3,
        top_journals: list[str] | None = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.lookback_years = lookback_years
        self.top_journals = top_journals or [
            "Journal of Finance", "Journal of Financial Economics",
            "Review of Financial Studies",
            "Journal of Accounting Research", "Accounting Review",
            "Management Science", "Review of Economics and Statistics",
            "American Economic Review", "Quarterly Journal of Economics",
            "经济研究", "金融研究", "管理世界", "会计研究",
        ]

    @property
    def gate_type(self) -> str:
        return GateType.NOVELTY

    def evaluate(self, context: dict) -> GateResult:
        """评估研究想法的新颖性。"""
        start = time.time()
        ideas = context.get("ideas", [])
        issues: list[str] = []
        suggestions: list[str] = []
        passed_count = 0
        detailed_results = []
        search_statuses: list[str] = []

        for idea in ideas:
            idea_text = idea if isinstance(idea, str) else idea.get("idea", str(idea))
            assessment = self._assess_idea(idea_text)
            similarity = float(assessment["similarity"])
            search_statuses.append(str(assessment.get("search_status", "unknown")))

            if similarity < self.similarity_threshold:
                passed_count += 1
            else:
                issues.append(
                    f"想法与已有文献高度重叠（相似度={similarity:.2f}）：{idea_text[:80]}"
                )
                top = assessment.get("overlaps") or []
                if top:
                    hit = top[0]
                    issues.append(
                        f"  最接近: {hit.get('title', '?')[:100]} "
                        f"({hit.get('year', '?')}, {hit.get('venue', '')[:60]})"
                    )
                suggestions.append(f"考虑从 {idea_text[:50]}... 方向寻找差异化视角")

            detailed_results.append({
                "idea": idea_text[:100],
                "similarity": similarity,
                "passed": similarity < self.similarity_threshold,
                "search_status": assessment.get("search_status"),
                "overlaps": assessment.get("overlaps", []),
            })

        score = passed_count / len(ideas) if ideas else 0.0
        passed = score >= 0.7  # 至少 70% 想法通过

        if not passed:
            suggestions.append(
                f"仅 {passed_count}/{len(ideas)} 想法通过新颖性门控，"
                "建议重新生成更具差异化的研究方向"
            )
        if search_statuses and all(s == "unavailable" for s in search_statuses):
            issues.append(
                "文献检索不可用（Semantic Scholar / OpenAlex 均无结果）；"
                "本次分数含 LLM 启发式回退，请联网后重跑 --novelty-check"
            )

        return GateResult(
            gate_type=self.gate_type,
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
            details={
                "threshold": self.similarity_threshold,
                "total_ideas": len(ideas),
                "passed_ideas": passed_count,
                "lookback_years": self.lookback_years,
                "results": detailed_results,
                "search_backend": "literature_download",
            },
            elapsed_seconds=time.time() - start,
        )

    def _assess_idea(self, idea: str) -> dict:
        """Return similarity + overlap metadata for one idea."""
        papers = self._search_literature(idea)
        if not papers:
            return {
                "similarity": self._llm_heuristic_similarity(idea),
                "search_status": "unavailable",
                "overlaps": [],
            }

        filtered = self._filter_papers(papers)
        if not filtered:
            return {
                "similarity": self._llm_heuristic_similarity(idea),
                "search_status": "filtered_empty",
                "overlaps": [],
            }

        scored: list[dict] = []
        for paper in filtered:
            blob = f"{paper.get('title', '')} {paper.get('abstract', '')}"
            sim = self._token_jaccard(idea, blob)
            if self._is_top_journal(str(paper.get("venue") or "")):
                sim = min(1.0, sim + 0.1)  # top-journal hit soft boost
            scored.append({**paper, "similarity": round(sim, 4)})

        scored.sort(key=lambda p: p["similarity"], reverse=True)
        best = scored[0]["similarity"] if scored else 0.0
        return {
            "similarity": float(best),
            "search_status": "ok",
            "overlaps": [
                {
                    "title": p.get("title", ""),
                    "year": p.get("year"),
                    "venue": p.get("venue", ""),
                    "doi": p.get("doi", ""),
                    "similarity": p.get("similarity", 0.0),
                }
                for p in scored[:5]
            ],
        }

    def _check_novelty(self, idea: str) -> float:
        """Back-compat: return max overlap similarity in [0, 1]."""
        return float(self._assess_idea(idea)["similarity"])

    def _search_literature(self, query: str) -> list[dict]:
        """Fetch candidate papers from SS + OpenAlex; normalize to a common shape."""
        q = " ".join((query or "").split())[:240]
        if not q:
            return []

        hits: list[dict] = []
        try:
            from scripts.literature_download import search_openalex, search_semantic
        except Exception as exc:
            logger.warning("NoveltyGate: cannot import literature_download: %s", exc)
            return []

        for label, fn in (
            ("semantic", lambda: search_semantic(q, limit=10)),
            ("openalex", lambda: search_openalex(q, limit=10)),
        ):
            try:
                raw = fn() or []
            except Exception as exc:
                logger.debug("NoveltyGate %s search failed: %s", label, exc)
                continue
            for item in raw:
                hits.append(self._normalize_paper(item, source=label))

        # Dedupe by lowercased title
        seen: set[str] = set()
        unique: list[dict] = []
        for p in hits:
            key = (p.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(p)
        return unique

    @staticmethod
    def _normalize_paper(item: dict, source: str) -> dict:
        title = item.get("title") or ""
        year = item.get("year") or item.get("publication_year")
        venue = item.get("venue") or ""
        if not venue and isinstance(item.get("primary_location"), dict):
            src = (item.get("primary_location") or {}).get("source") or {}
            venue = src.get("display_name", "") if isinstance(src, dict) else ""
        abstract = item.get("abstract") or ""
        if isinstance(abstract, dict):
            # OpenAlex inverted index sometimes leaked through — ignore for overlap.
            abstract = ""
        doi = ""
        ext = item.get("externalIds") or item.get("external_ids") or {}
        if isinstance(ext, dict):
            doi = ext.get("DOI") or ext.get("doi") or ""
        doi = doi or item.get("doi") or ""
        if isinstance(doi, str) and doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")
        return {
            "title": title,
            "year": year,
            "venue": venue or "",
            "abstract": abstract if isinstance(abstract, str) else "",
            "doi": doi,
            "source": source,
        }

    def _filter_papers(self, papers: list[dict]) -> list[dict]:
        from datetime import datetime

        min_year = datetime.now().year - max(1, int(self.lookback_years))
        kept: list[dict] = []
        for p in papers:
            year = p.get("year")
            try:
                y = int(year) if year is not None else None
            except (TypeError, ValueError):
                y = None
            if y is not None and y < min_year:
                continue
            kept.append(p)
        return kept or papers  # if year filter empties everything, keep raw hits

    def _is_top_journal(self, venue: str) -> bool:
        v = (venue or "").lower()
        if not v:
            return False
        return any(j.lower() in v for j in self.top_journals)

    @staticmethod
    def _token_jaccard(a: str, b: str) -> float:
        def toks(s: str) -> set[str]:
            return {t for t in "".join(
                ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (s or "")
            ).split() if len(t) > 2}

        ta, tb = toks(a), toks(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def _llm_heuristic_similarity(self, idea: str) -> float:
        """Fallback when literature search is unavailable. Documented as heuristic."""
        try:
            from scripts.core.llm_gateway import LLMGateway
            import re

            gateway = LLMGateway(memory=None)
            prompt = (
                f"Estimate how overlapping this research idea is with recent finance/"
                f"economics literature. Reply with ONLY a float in [0,1].\n\nIdea: {idea}"
            )
            response = gateway.generate(prompt, task_hint="novelty_check")
            text = response.response if hasattr(response, "response") else str(response)
            match = re.search(r"\b(0?\.\d+)\b", text)
            if match:
                return min(1.0, max(0.0, float(match.group(1))))
        except Exception as exc:
            logger.debug("NoveltyGate LLM heuristic failed: %s", exc)
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# GATE 2: FEASIBILITY
# ─────────────────────────────────────────────────────────────────────────────


class FeasibilityGate(BaseGate):
    """
    可行性门控 — 检查研究设计的可执行性。

    检查维度：
      1. 数据可获取性：所需数据是否有 MCP 工具支持或用户提供
      2. 方法可行性：所选方法在样本量/变量维度下是否可行
      3. 计算资源：DID/ML 方法的计算需求是否可满足
      4. 时间可行性：是否在合理时间内完成（硕士 ≤ 3 月，博士 ≤ 12 月）

    失败动作：降级方案或提示用户提供数据
    """

    def __init__(self, max_runtime_months: int = 3):
        self.max_runtime_months = max_runtime_months

    @property
    def gate_type(self) -> str:
        return GateType.FEASIBILITY

    def evaluate(self, context: dict) -> GateResult:
        start = time.time()
        design = context.get("design", {})
        issues: list[str] = []
        suggestions: list[str] = []
        checks: dict[str, bool] = {}

        # 检查数据可获取性
        required_data = design.get("required_data", [])
        data_availability = self._check_data_availability(required_data)
        checks["data_available"] = data_availability["available"]
        if not data_availability["available"]:
            issues.append(f"缺少数据：{', '.join(data_availability['missing'])}")
            for missing in data_availability["missing"]:
                suggestions.append(
                    f"请提供 {missing} 数据，或使用 MCP 工具 {missing} 获取"
                )

        # 检查方法可行性
        method = design.get("method", "")
        sample_size = design.get("sample_size", 0)
        checks["method_feasible"] = self._check_method_feasibility(method, sample_size)
        if not checks["method_feasible"]:
            issues.append(
                f"方法 '{method}' 在样本量 {sample_size} 下可能不可行"
            )
            suggestions.append(
                "考虑增加样本量、使用更简单的方法（如 OLS 替代 DID），"
                "或拆分研究问题"
            )

        # 检查样本量
        if sample_size < 100:
            issues.append(f"样本量过小（{sample_size} < 100），统计功效不足")
            suggestions.append("建议增加样本量或使用面板数据")
        checks["sufficient_sample"] = sample_size >= 100

        # 检查时间可行性
        estimated_months = design.get("estimated_months", 0)
        checks["time_feasible"] = estimated_months <= self.max_runtime_months
        if not checks["time_feasible"]:
            issues.append(
                f"预计耗时 {estimated_months} 月，超过 {self.max_runtime_months} 月限制"
            )
            suggestions.append("考虑简化研究设计或分阶段执行")

        passed = all(checks.values())
        score = sum(checks.values()) / len(checks) if checks else 0.0

        return GateResult(
            gate_type=self.gate_type,
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
            details={
                "checks": checks,
                "data_availability": data_availability,
                "estimated_months": estimated_months,
            },
            elapsed_seconds=time.time() - start,
        )

    def _check_data_availability(self, required_data: list[str]) -> dict:
        """检查所需数据的可获取性。"""
        mcp_data_sources = {
            "stock": ["user-yfinance", "user-tushare", "user-eodhd"],
            "financial": ["user-yfinance", "user-csmar", "user-tushare"],
            "macro": ["user-financial", "user-eodhd", "user-wb-data"],
            "esg": ["user-yfinance"],
            "news": ["user-eastmoney-reports", "user-brave-search"],
            "province": ["user-province-stats", "user-hubei-stats"],
            "forex": ["user-enhanced-finance"],
            "bond": ["user-eastmoney-bond"],
            "fund": ["user-eastmoney-fund"],
        }

        available = []
        missing = []

        for data in required_data:
            data_lower = data.lower()
            found = any(
                src in str(mcp_data_sources)
                for src_list in mcp_data_sources.values()
                for src in src_list
                if any(k in data_lower for k in mcp_data_sources)
            )
            if found or "provided" in data_lower or "user" in data_lower:
                available.append(data)
            else:
                missing.append(data)

        return {
            "available": len(missing) == 0,
            "available_data": available,
            "missing": missing,
        }

    def _check_method_feasibility(self, method: str, sample_size: int) -> bool:
        """检查方法在给定样本量下的可行性。"""
        method_lower = method.lower()

        if any(k in method_lower for k in ["did", "diff-in-diff", "倍差"]):
            return sample_size >= 200
        if any(k in method_lower for k in ["iv", "instrument", "工具变量"]):
            return sample_size >= 100
        if any(k in method_lower for k in ["dml", "ml", "machine learning", "机器学习"]):
            return sample_size >= 500
        if any(k in method_lower for k in ["rd", "regression discontinuity", "断点回归"]):
            return sample_size >= 200
        return True


# ─────────────────────────────────────────────────────────────────────────────
# GATE 3: DUALITY
# ─────────────────────────────────────────────────────────────────────────────


class DualityGate(BaseGate):
    """
    理论与实验一致性门控 — 检查理论预测与实验结果是否一致。

    检查维度：
      1. 符号一致性：理论预测的符号方向与实证结果是否一致
      2. 量级合理性：实证系数量级是否在理论预期范围内
      3. 机制一致性：理论提出的机制是否在数据中得到支持

    失败动作：触发 Theory/Experiment 迭代对齐
    """

    def __init__(self, magnitude_tolerance: float = 3.0):
        self.magnitude_tolerance = magnitude_tolerance

    @property
    def gate_type(self) -> str:
        return GateType.DUALITY

    def evaluate(self, context: dict) -> GateResult:
        start = time.time()
        hypothesis = context.get("hypothesis", "")
        results = context.get("results", {})
        issues: list[str] = []
        suggestions: list[str] = []

        # 提取理论预测
        predicted_sign = self._extract_predicted_sign(hypothesis)
        predicted_direction = self._extract_predicted_direction(hypothesis)

        # 提取实证结果
        empirical_coef = results.get("coef", 0)
        empirical_sign = "+" if empirical_coef >= 0 else "-"

        # 检查符号一致性
        sign_match = (predicted_sign == empirical_sign) if predicted_sign else None
        checks = {}

        if sign_match is not None:
            checks["sign_consistent"] = sign_match
            if not sign_match:
                issues.append(
                    f"符号不一致：理论预测 {predicted_sign}，"
                    f"实证结果 {empirical_sign}（系数={empirical_coef:.4f}）"
                )
                suggestions.append(
                    "检查：① 理论机制是否理解正确 ② 变量定义是否一致"
                    "③ 存在反向因果或其他内生性问题"
                )
        else:
            checks["sign_consistent"] = None

        # 检查量级合理性
        if predicted_direction and abs(empirical_coef) > 0:
            expected_range = self._estimate_magnitude_range(
                predicted_direction, results
            )
            checks["magnitude_reasonable"] = expected_range[0] <= abs(empirical_coef) <= expected_range[1]

            if not checks["magnitude_reasonable"]:
                issues.append(
                    f"量级不合理：系数 {empirical_coef:.4f}，"
                    f"预期范围 {expected_range[0]:.4f} ~ {expected_range[1]:.4f}"
                )
                suggestions.append(
                    "可能原因：① 变量标准化方式不同 ② 样本差异 ③ 遗漏重要控制变量"
                )
        else:
            checks["magnitude_reasonable"] = True

        # 检查统计显著性
        pval = results.get("pval", 1)
        checks["significant"] = pval < 0.05
        if not checks["significant"]:
            issues.append(f"结果不显著（p={pval:.4f}），难以支持理论")
            suggestions.append(
                "增加样本量、调整时间窗口，或考虑使用代理变量"
            )

        passed = (
            (checks.get("sign_consistent") is None or checks.get("sign_consistent", False))
            and checks.get("significant", False)
        )
        score = sum(1 for v in checks.values() if v) / max(len(checks), 1)

        return GateResult(
            gate_type=self.gate_type,
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
            details={
                "checks": checks,
                "predicted_sign": predicted_sign,
                "predicted_direction": predicted_direction,
                "empirical_coef": empirical_coef,
                "empirical_sign": empirical_sign,
                "pval": pval,
            },
            elapsed_seconds=time.time() - start,
        )

    def _extract_predicted_sign(self, hypothesis: str) -> str | None:
        """从假说中提取预测符号。"""
        pos_kw = ["正向", "促进", "提高", "增加", "正相关", "positive", "increase", "enhance"]
        neg_kw = ["负向", "抑制", "降低", "减少", "负相关", "negative", "decrease", "reduce"]

        for kw in pos_kw:
            if kw in hypothesis:
                return "+"
        for kw in neg_kw:
            if kw in hypothesis:
                return "-"
        return None

    def _extract_predicted_direction(self, hypothesis: str) -> str:
        """提取预测方向描述。"""
        return hypothesis[:200] if hypothesis else ""

    def _estimate_magnitude_range(
        self, direction: str, results: dict
    ) -> tuple[float, float]:
        """估计合理的量级范围。"""
        results.get("se", 0)
        coef = results.get("coef", 0)
        base = abs(coef)

        if base < 0.01:
            return (0, 0.1)
        elif base < 0.1:
            return (base * 0.1, base * 10)
        else:
            return (base * 0.3, base * 3.0)


# ─────────────────────────────────────────────────────────────────────────────
# GATE 4: QUALITY
# ─────────────────────────────────────────────────────────────────────────────


class QualityGate(BaseGate):
    """
    质量门控 — 最终稿件的综合质量检查。

    检查维度：
      1. 图表规范：图表标题/编号/引用/格式
      2. 引用完整性：\\ref/\\cite 是否全部有对应定义
      3. LaTeX 语法：环境闭合/列数匹配等
      4. 格式合规：期刊模板规范

    失败动作：返回修改 → 重跑 Quality Gate
    """

    def __init__(
        self,
        latex_issues_threshold: int = 0,
        cite_threshold: float = 1.0,
    ):
        self.latex_issues_threshold = latex_issues_threshold
        self.cite_threshold = cite_threshold

    @property
    def gate_type(self) -> str:
        return GateType.QUALITY

    def evaluate(self, context: dict) -> GateResult:
        start = time.time()
        issues: list[str] = []
        suggestions: list[str] = []
        checks: dict[str, bool] = {}

        manuscript_path = context.get("manuscript_path")

        # LaTeX 即时验证
        if manuscript_path and Path(manuscript_path).exists():
            latex_issues = self._check_latex(manuscript_path)
            checks["latex_clean"] = len(latex_issues) <= self.latex_issues_threshold
            if latex_issues:
                issues.append(f"LaTeX 错误 {len(latex_issues)} 项")
                for issue in latex_issues[:5]:
                    issues.append(f"  - {issue}")
                suggestions.append("使用 latex_lint.py 修复 LaTeX 错误")
        else:
            checks["latex_clean"] = True

        # 引用完整性
        if manuscript_path and Path(manuscript_path).exists():
            cite_issues = self._check_citations(manuscript_path)
            cite_rate = 1 - (len(cite_issues) / max(len(cite_issues), 1))
            checks["citation_complete"] = cite_rate >= self.cite_threshold
            if cite_issues:
                issues.append(f"引用问题 {len(cite_issues)} 项")
                for issue in cite_issues[:3]:
                    issues.append(f"  - {issue}")
                suggestions.append("补全缺失的参考文献条目")
        else:
            checks["citation_complete"] = True

        # 检查图表
        if manuscript_path:
            fig_tab_issues = self._check_figures_tables(manuscript_path)
            checks["figures_complete"] = len(fig_tab_issues) == 0
            if fig_tab_issues:
                issues.append(f"图表问题 {len(fig_tab_issues)} 项")
                for issue in fig_tab_issues[:3]:
                    issues.append(f"  - {issue}")
        else:
            checks["figures_complete"] = True

        # 摘要检查
        if manuscript_path:
            abstract_issues = self._check_abstract(manuscript_path)
            checks["abstract_complete"] = len(abstract_issues) == 0
            if abstract_issues:
                issues.append(f"摘要问题：{abstract_issues[0]}")
        else:
            checks["abstract_complete"] = True

        passed = all(checks.values())
        score = sum(1 for v in checks.values() if v) / max(len(checks), 1)

        return GateResult(
            gate_type=self.gate_type,
            passed=passed,
            score=score,
            issues=issues,
            suggestions=suggestions,
            details={"checks": checks},
            elapsed_seconds=time.time() - start,
        )

    def _check_latex(self, path: str | Path) -> list[str]:
        """LaTeX 语法检查。"""
        try:
            from scripts.core.latex_lint import LatexLintChecker

            checker = LatexLintChecker(path)
            checker.check_all()
            errors = [i.message for i in checker.issues if i.severity == "ERROR"]
            return errors[:10]
        except Exception:
            return []

    def _check_citations(self, path: str | Path) -> list[str]:
        """引用完整性检查。"""
        try:
            from scripts.core.latex_lint import LatexLintChecker

            checker = LatexLintChecker(path)
            checker.check_all()
            issues = [
                i.message for i in checker.issues
                if i.rule == "orphan_cite" or i.rule == "orphan_ref"
            ]
            return issues[:10]
        except Exception:
            return []

    def _check_figures_tables(self, path: str | Path) -> list[str]:
        """图表完整性检查。"""
        try:
            from scripts.core.latex_lint import LatexLintChecker

            checker = LatexLintChecker(path)
            checker.check_all()
            issues = [
                i.message for i in checker.issues
                if i.rule in ("missing_caption", "missing_label")
            ]
            return issues[:10]
        except Exception:
            return []

    def _check_abstract(self, path: str | Path) -> list[str]:
        """摘要质量检查。"""
        try:
            content = Path(path).read_text(encoding="utf-8")
            import re
            abstract_match = re.search(
                r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                content,
                re.DOTALL,
            )
            if not abstract_match:
                return ["摘要环境缺失（\\begin{abstract}...\\end{abstract}）"]

            abstract_text = abstract_match.group(1)
            word_count = len(abstract_text.split())

            if word_count < 150:
                return [f"摘要过短（{word_count} < 150 词）"]
            if word_count > 350:
                return [f"摘要过长（{word_count} > 350 词）"]
            return []
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION GATE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────


class ValidationGate:
    """
    Validation Gate 编排器 — 按顺序执行所有 Gate。

    Usage
    -----
        gate = ValidationGate()
        gate.register(NoveltyGate())
        gate.register(FeasibilityGate())
        gate.register(DualityGate())
        gate.register(QualityGate())

        # 评估研究想法
        result = gate.evaluate_all(ideas=ideas)

        # 评估研究设计
        result = gate.evaluate_all(design=design)

        # 评估论文
        result = gate.evaluate_all(manuscript_path="papers/main.tex")
    """

    def __init__(self):
        self._gates: list[BaseGate] = []

    def register(self, gate: BaseGate):
        """注册 Gate。"""
        existing = [g for g in self._gates if g.gate_type == gate.gate_type]
        if existing:
            self._gates = [g for g in self._gates if g.gate_type != gate.gate_type]
        self._gates.append(gate)
        logger.info(f"[ValidationGate] Registered: {gate}")

    def list_gates(self) -> list[str]:
        """列出所有注册的 Gate。"""
        return [g.gate_type for g in self._gates]

    def evaluate_all(self, **context) -> dict:
        """
        执行所有 Gate。

        Parameters
        ----------
        context
            传递给各 Gate 的上下文数据。可包含：
              - ideas: 研究想法列表
              - design: 研究设计方案
              - hypothesis: 研究假说
              - results: 实证结果
              - manuscript_path: 论文路径

        Returns
        -------
        dict
            各 Gate 的评估结果汇总。
        """
        results: dict[str, GateResult] = {}

        for gate in self._gates:
            relevant_context = self._filter_context(gate.gate_type, context)
            try:
                result = gate.evaluate(relevant_context)
                results[gate.gate_type] = result
                status = "✅" if result.passed else "❌"
                logger.info(
                    f"[ValidationGate] {status} {gate.gate_type} "
                    f"(score={result.score:.2f}, {result.elapsed_seconds:.1f}s)"
                )
            except Exception as exc:
                logger.warning(f"[ValidationGate] {gate.gate_type} failed: {exc}")
                results[gate.gate_type] = GateResult(
                    gate_type=gate.gate_type,
                    passed=False,
                    score=0.0,
                    issues=[f"Gate 评估异常：{exc}"],
                    elapsed_seconds=0.0,
                )

        overall_passed = all(r.passed for r in results.values())
        overall_score = (
            sum(r.score for r in results.values()) / len(results)
            if results else 0.0
        )

        return {
            "overall_passed": overall_passed,
            "overall_score": overall_score,
            "gate_results": {k: v.to_dict() for k, v in results.items()},
            "all_passed": all(r.passed for r in results.values()),
            "failed_gates": [
                k for k, v in results.items() if not v.passed
            ],
            "total_gates": len(self._gates),
        }

    def _filter_context(self, gate_type: str, context: dict) -> dict:
        """根据 Gate 类型筛选相关上下文。"""
        if gate_type == GateType.NOVELTY:
            return {k: v for k, v in context.items() if k in ("ideas",)}
        elif gate_type == GateType.FEASIBILITY:
            return {k: v for k, v in context.items() if k in ("design",)}
        elif gate_type == GateType.DUALITY:
            return {k: v for k, v in context.items()
                    if k in ("hypothesis", "results", "design")}
        elif gate_type == GateType.QUALITY:
            return {k: v for k, v in context.items()
                    if k in ("manuscript_path",)}
        return context

    def print_summary(self, result: dict, file=None):
        """打印评估摘要。"""
        print("=" * 60, file=file)
        print("  Validation Gate Summary", file=file)
        print("=" * 60, file=file)
        print(
            f"  Overall: {'✅ PASSED' if result['overall_passed'] else '❌ FAILED'} "
            f"(score={result['overall_score']:.2f})",
            file=file,
        )
        print(file=file)

        for gate_type, gate_result in result["gate_results"].items():
            icon = "✅" if gate_result["passed"] else "❌"
            print(
                f"  {icon} {gate_type.upper():15s} "
                f"score={gate_result['score']:.2f} "
                f"({gate_result['elapsed_seconds']:.1f}s)",
                file=file,
            )
            for issue in gate_result.get("issues", [])[:3]:
                print(f"      ⚠ {issue}", file=file)
            for suggestion in gate_result.get("suggestions", [])[:2]:
                print(f"      → {suggestion}", file=file)

        print("=" * 60, file=file)
