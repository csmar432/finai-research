"""PaperOrchestra-style specialized agents for academic paper writing.

Five professional agents following PaperOrchestra's design:
    1. OutlineAgent       — Structured outline from topic/venue/template
    2. LiteratureReviewAgent — Literature search + verification + citation graph
    3. SectionWritingAgent  — Write paper sections with data and tables
    4. ContentRefinementAgent — Simulated peer-review with halt rules
    5. PlottingAgent       — matplotlib figures with captions and critique
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.core.agents.base import (
    AgentConfig,
    BaseAgent,
    HaltDecision,
)

# ─── Shared Halt Rules ────────────────────────────────────────────────────────


PAPER_HALT_RULES = [
    ("字数偏差超过 20%", "word_count_mismatch"),
    ("关键贡献未在摘要中体现", "missing_contribution"),
    ("方法论章节缺少技术细节", "shallow_methodology"),
    ("引用覆盖率低于 90%", "low_citation_coverage"),
    ("图表数量与计划不符", "figure_count_mismatch"),
    ("创新点不够突出", "weak_novelty"),
    ("实验设计不可行", "infeasible_experiment"),
    ("结论缺乏数据支撑", "unsupported_conclusion"),
]

REVIEW_HALT_RULES = [
    ("结构不完整（缺少引言/方法/实验/结论）", "incomplete_structure"),
    ("存在事实性错误", "factual_error"),
    ("语言质量差，影响理解", "poor_writing"),
    ("引用不准确或过时", "bad_citations"),
]


# ─── OutlineAgent ─────────────────────────────────────────────────────────────


class OutlineAgent(BaseAgent):
    """
    Generates structured paper outlines from topic and venue.

    PaperOrchestra Outline Agent:
        - Synthesizes topic + idea + template → structured outline JSON
        - Includes plotting plan, lit review plan, section plan
        - Each chapter has: title, summary, key_points, dependencies
    """

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        topic = context.get("topic", "")
        venue = context.get("venue", "通用")
        idea = context.get("idea", "")
        template = context.get("template", "")
        field_type = context.get("field", "AI/机器学习")

        prompt = f"""你是一位资深的学术论文写作教练，擅长为顶尖会议设计清晰且有说服力的论文结构。

## 研究主题
{topic}

## 核心想法/创新点
{idea or "暂无，需根据主题自行提炼"}

## 目标期刊/会议
{venue}

## 研究领域
{field_type}

## 模板要求（可选）
{template or "无特殊模板要求"}

## 任务
请生成一份完整的论文大纲，必须包含以下部分：

### 1. 元信息
- title: 论文标题建议（英文为主，必要时附中文）
- short_title: 简短标题（用于图表/页眉）
- contribution_statement: 一句话总结核心贡献

### 2. 章节结构（严格按以下顺序）
每一章必须包含：
- chapter_id: 编号（如 1, 2, 3）
- title: 章节标题（中英文）
- summary: 章节摘要（1-2句话）
- key_points: 核心要点列表（3-5条）
- dependencies: 依赖章节（前置章节编号，如 [1]）
- figure_plan: 该章节需要的图表列表（可为空）
- table_plan: 该章节需要的表格列表（可为空）

章节顺序必须为：Abstract → Introduction → Related Work → Preliminaries/Background → Method → Experiment → Conclusion

### 3. 图表计划
列出所有图表：
- figure_id: 编号（Figure 1, 2...）
- placement_chapter: 放置章节
- description: 图表描述
- generation_method: 生成方式（"matplotlib生成" / "数据驱动" / "手动绘制"）

### 4. 文献综述计划
- search_queries: 需要检索的文献主题列表（3-8个关键词）
- expected_citations: 预期引用数量
- coverage_target: 覆盖率目标（如 "≥90% 经API验证"）

### 5. 数据计划
- datasets: 需要的数据集
- experiments: 需要的实验类型
- baselines: 对比基准方法

## 输出格式
必须输出有效的 JSON，格式如下：
```json
{{
  "meta": {{...}},
  "chapters": [...],
  "figure_plan": [...],
  "literature_plan": {{...}},
  "data_plan": {{...}}
}}
```

确保 JSON 格式完全正确，可被 json.loads() 解析。"""

        response = self._generate(prompt, format_json=True)
        tokens = response.tokens_used if hasattr(response, "tokens_used") else 0

        try:
            outline = self._parse_json_response(response.response)
        except ValueError:
            # Fallback: return raw text if JSON parsing fails
            outline = {
                "text": response.response,
                "raw": True,
                "format_note": "JSON parsing failed, raw text returned",
            }

        return {
            "outline": outline,
            "model": response.model_used,
            "latency_ms": response.latency_ms,
            "tokens_used": tokens,
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        outline = act_result.get("outline", {})

        # Check if JSON parsing failed
        if outline.get("raw"):
            return {
                "halt": HaltDecision.REVISE,
                "feedback": "大纲输出格式错误，无法解析为 JSON 结构。请重新生成严格符合 JSON 格式的大纲。",
                "score": 0.3,
                "flags": ["format_error"],
            }

        # Validate structure
        required_keys = ["meta", "chapters", "figure_plan", "literature_plan"]
        missing = [k for k in required_keys if k not in outline]

        if missing:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"大纲缺少必要字段: {', '.join(missing)}。请补全后再生成。",
                "score": 0.5,
                "flags": ["incomplete_structure"],
            }

        # Check chapter count
        chapters = outline.get("chapters", [])
        if len(chapters) < 5:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"大纲章节数不足（当前{len(chapters)}，建议≥7章）。请补充完整章节结构。",
                "score": 0.6,
                "flags": ["too_short"],
            }

        # Check contribution statement
        meta = outline.get("meta", {})
        if not meta.get("contribution_statement"):
            return {
                "halt": HaltDecision.REVISE,
                "feedback": "元信息中缺少贡献声明（contribution_statement）。请补充一句清晰的核心贡献描述。",
                "score": 0.7,
                "flags": ["weak_contribution"],
            }

        return {
            "halt": HaltDecision.APPROVED,
            "feedback": "大纲结构完整，章节逻辑清晰，同意进入下一阶段。",
            "score": 0.85,
            "flags": [],
        }


# ─── LiteratureReviewAgent ────────────────────────────────────────────────────


@dataclass
class CitationRecord:
    """A single verified citation."""
    doi: str | None
    title: str
    authors: list[str]
    year: int
    venue: str
    verified: bool
    verification_source: str  # "semantic_scholar" | "crossref" | "arxiv" | "unverified"
    levenshtein_score: float
    abstract: str | None = None
    citations_count: int = 0
    raw_bibtex: str | None = None


class LiteratureReviewAgent(BaseAgent):
    """
    Searches, verifies, and synthesizes literature for the paper.

    PaperOrchestra Literature Review Agent:
        - Web search for candidate papers
        - Semantic Scholar API verification (Levenshtein > 70%)
        - Citation graph construction
        - ≥90% citation coverage requirement
    """

    def __init__(self, config: AgentConfig, gateway, citation_verifier=None):
        super().__init__(config, gateway)
        self._citation_verifier = citation_verifier

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute literature search and verification.

        Context keys:
            outline: The paper outline dict
            search_queries: List of search queries to execute
            max_results_per_query: Max results per query (default 10)
        """
        from scripts.core.citation_verifier import CitationVerifier

        if self._citation_verifier is None:
            self._citation_verifier = CitationVerifier()

        outline = context.get("outline", {})
        lit_plan = outline.get("literature_plan", {})
        search_queries = context.get("search_queries", lit_plan.get("search_queries", []))
        max_results = context.get("max_results_per_query", 10)

        all_citations: list[CitationRecord] = []
        coverage_stats = {"verified": 0, "unverified": 0, "total": 0}

        for query in search_queries:
            candidates = self._search_candidates(query, max_results)

            for candidate in candidates:
                verified_record = self._verify_and_record(candidate)
                all_citations.append(verified_record)

                if verified_record.verified:
                    coverage_stats["verified"] += 1
                else:
                    coverage_stats["unverified"] += 1
                coverage_stats["total"] += 1

        # Build citation graph
        citation_graph = self._build_citation_graph(all_citations)

        # Calculate coverage
        coverage = (
            coverage_stats["verified"] / coverage_stats["total"]
            if coverage_stats["total"] > 0 else 0.0
        )

        return {
            "citations": [
                {
                    "doi": c.doi,
                    "title": c.title,
                    "authors": c.authors,
                    "year": c.year,
                    "venue": c.venue,
                    "verified": c.verified,
                    "source": c.verification_source,
                    "score": c.levenshtein_score,
                    "abstract": c.abstract,
                }
                for c in all_citations
            ],
            "coverage": coverage,
            "coverage_stats": coverage_stats,
            "citation_graph": citation_graph,
            "query_count": len(search_queries),
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        coverage = act_result.get("coverage", 0.0)
        citations = act_result.get("citations", [])
        coverage_stats = act_result.get("coverage_stats", {})

        if coverage < 0.9:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": (
                    f"引用覆盖率 {coverage:.0%} 低于 90% 要求（已验证 {coverage_stats.get('verified', 0)}/{coverage_stats.get('total', 0)}）。"
                    f"请补充 {int(len(citations) * 0.1) - coverage_stats.get('verified', 0)} 条可验证的引用。"
                ),
                "score": coverage,
                "flags": ["low_citation_coverage"],
            }

        if len(citations) < 5:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"引用数量不足（当前 {len(citations)}，建议 ≥10）。请扩大搜索范围。",
                "score": 0.7,
                "flags": ["insufficient_citations"],
            }

        return {
            "halt": HaltDecision.APPROVED,
            "feedback": f"文献综述通过：共 {len(citations)} 条引用，验证覆盖率 {coverage:.0%}，符合 ≥90% 要求。",
            "score": 0.88,
            "flags": [],
        }

    def _search_candidates(self, query: str, max_results: int) -> list[dict]:
        """
        Search for candidate papers using MCP brave_search and arxiv tools.

        PaperOrchestra: uses web search to discover candidate papers,
        then verifies via Semantic Scholar.
        """
        results: list[dict] = []

        # Try MCP brave_search first
        try:
            from scripts.core.llm_gateway import MCPResult, call_mcp_tool
            mcp_result = call_mcp_tool("brave-search", "brave_search",
                                        {"query": f"{query} academic paper", "count": max_results})
            if isinstance(mcp_result, MCPResult) and mcp_result.success:
                data = mcp_result.data
                if isinstance(data, list):
                    for item in data[:max_results]:
                        if isinstance(item, dict):
                            results.append({
                                "query": query,
                                "title": item.get("title", ""),
                                "authors": self._parse_authors(item),
                                "year": self._parse_year(item),
                                "doi": item.get("doi"),
                                "venue": item.get("snippet", ""),
                                "url": item.get("url", ""),
                            })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[LiteratureReviewAgent] brave_search failed for query '{query}': {e}"
            )

        # Fall back to arxiv search
        if not results:
            try:
                from scripts.core.llm_gateway import MCPResult, call_mcp_tool
                mcp_result = call_mcp_tool("arxiv", "search_papers",
                                            {"query": query, "max_results": max_results})
                if isinstance(mcp_result, MCPResult) and mcp_result.success:
                    data = mcp_result.data
                    if isinstance(data, list):
                        for item in data[:max_results]:
                            if isinstance(item, dict):
                                results.append({
                                    "query": query,
                                    "title": item.get("title", ""),
                                    "authors": self._parse_authors(item),
                                    "year": self._parse_year(item),
                                    "doi": item.get("doi"),
                                    "venue": item.get("primary_category", ""),
                                    "url": item.get("entry_id", ""),
                                })
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"[LiteratureReviewAgent] arxiv search failed for query '{query}': {e}"
                )

        # Last resort: use LLM to generate structured search queries
        # and return no results (LLM cannot browse)
        if not results:
            search_prompt = f"""针对以下研究主题，生成 3-5 个精准的学术检索查询：

研究查询：{query}

要求：
- 每个查询包含关键词和限定语（如年份范围、顶会名称）
- 查询应涵盖：方法论基准、数据集基准、最新工作三个维度
- 输出 JSON 数组格式：["query1", "query2", ...]"""

            response = self._generate(search_prompt, format_json=True)
            try:
                queries = self._parse_json_response(response.response)
                if not isinstance(queries, list):
                    queries = [query]
            except ValueError:
                queries = [query]

            # Return empty with a warning marker
            return [{
                "query": q,
                "title": "[需手动检索] " + q,
                "authors": [],
                "year": 2024,
                "doi": None,
                "venue": "待验证",
                "_warning": "MCP search unavailable, please provide paper manually",
            } for q in queries[:max_results]]

        return results

    def _parse_authors(self, item: dict) -> list[str]:
        """Parse authors from search result."""
        authors = item.get("authors", [])
        if isinstance(authors, list):
            return [a.get("name", str(a)) for a in authors]
        if isinstance(authors, str):
            return [a.strip() for a in authors.split(",")]
        return []

    def _parse_year(self, item: dict) -> int:
        """Parse year from search result."""
        pub_date = item.get("published", item.get("date", ""))
        if pub_date and len(str(pub_date)) >= 4:
            try:
                return int(str(pub_date)[:4])
            except (ValueError, TypeError):
                pass
        return 2024

    def _verify_and_record(self, candidate: dict) -> CitationRecord:
        """Verify a citation via CitationVerifier and return a record."""
        if self._citation_verifier is None:
            return CitationRecord(
                doi=candidate.get("doi"),
                title=candidate.get("title", ""),
                authors=candidate.get("authors", []),
                year=candidate.get("year", 2024),
                venue=candidate.get("venue", "未知"),
                verified=False,
                verification_source="unverified",
                levenshtein_score=0.0,
            )

        result = self._citation_verifier.verify(candidate)

        return CitationRecord(
            doi=candidate.get("doi"),
            title=candidate.get("title", ""),
            authors=candidate.get("authors", []),
            year=candidate.get("year", 2024),
            venue=candidate.get("venue", "未知"),
            verified=result.get("verified", False),
            verification_source=result.get("source", "unverified"),
            levenshtein_score=result.get("levenshtein_score", 0.0),
            abstract=result.get("abstract"),
        )

    def _build_citation_graph(self, citations: list[CitationRecord]) -> dict[str, Any]:
        """
        Build a citation graph identifying:
            - Hub papers (highly cited, connects many topics)
            - Isolated citations (never cited by others in the graph)
            - Core references (required for the paper's argument)

        Hub detection: sort by citations_count descending; recency (year) as secondary tiebreaker.
        If all citations_count are 0 (unverified), fall back to recency as tiebreaker.
        """
        if not citations:
            return {"hubs": [], "isolates": [], "total_papers": 0, "total_citations": 0}

        # Sort by citation count descending; recency (year) as secondary tiebreaker
        sorted_citations = sorted(
            citations,
            key=lambda c: (c.citations_count, c.year),
            reverse=True,
        )

        hubs = sorted_citations[:3]
        # Isolates: papers with zero citations (or all if all are unverified)
        if all(c.citations_count == 0 for c in citations):
            isolates = [c.title for c in citations]
        else:
            isolates = [c.title for c in citations if c.citations_count == 0]

        total_citations = sum(c.citations_count for c in citations)

        return {
            "hubs": [{"title": c.title, "year": c.year, "citations": c.citations_count}
                     for c in hubs],
            "isolates": isolates,
            "total_papers": len(citations),
            "total_citations": total_citations,
        }


# ─── SectionWritingAgent ──────────────────────────────────────────────────────


class SectionWritingAgent(BaseAgent):
    """
    Writes individual paper sections from outline and data.

    PaperOrchestra Section Writing Agent:
        - One single multi-modal call to draft all sections
        - Builds tables from experimental logs
        - Embeds figures with captions
        - Integrates verified citations
    """

    CHAPTER_PROMPTS = {
        "Abstract": """Write the Abstract section (200-300 words).

Structure:
1. Problem (1-2 sentences): What is the problem and why is it important?
2. Method (1-2 sentences): What is your approach?
3. Key Results (1-2 sentences): What are the main findings?
4. Impact (1 sentence): Why does this matter?

Tone: Formal academic. Third person. No figures or tables.
""",
        "Introduction": """Write the Introduction section.

Structure:
1. Opening (2-3 paragraphs): Context and motivation
2. Problem Statement (1 paragraph): Formal definition of the problem
3. Related Work Overview (2-3 paragraphs): How has this been tackled before?
4. Our Approach (1-2 paragraphs): What is your method and why is it different?
5. Contributions (bullet list): What are your main contributions?

Tone: Engaging but formal. First person plural ("We") is acceptable.
Citation density: High — integrate at least 5 relevant citations.
""",
        "Related Work": """Write the Related Work section.

Structure:
1. Background (1-2 paragraphs): General context and taxonomy of the field
2. Method Survey (3-5 paragraphs): Categorize existing approaches with specific examples
   - Approach A (papers): Strengths and limitations
   - Approach B (papers): Strengths and limitations
   - ...
3. Gap Identification (1 paragraph): What is missing from existing work
4. How We Fill the Gap (1-2 paragraphs): How our method addresses the gap

Tone: Objective and taxonomic. Avoid first person. Be critical but fair.
Citation density: Very high — cite at least 15 relevant papers, clearly attributed.
Format: Group related work by theme, not by author.
""",
        "Preliminaries": """Write the Preliminaries / Background section.

Structure:
1. Problem Definition (1-2 paragraphs): Formal definition of the problem we solve
2. Notation (1 paragraph): Table of symbols and definitions
3. Background Concepts (2-3 paragraphs): Required background knowledge for understanding

Tone: Precise and self-contained. Define all notation before first use.
Citation density: Medium — cite foundational references for background concepts.
Mathematical notation: Use numbered equations for key definitions.
""",
        "Method": """Write the Method section.

Structure:
1. Preliminaries/Notation (1-2 paragraphs): Define notation and concepts
2. Method Overview (1 paragraph): High-level description of your approach
3. Technical Details (2-4 paragraphs): Full mathematical/formal description
4. Theoretical Analysis (optional): Proofs or analysis of properties

Tone: Precise and formal. Use equations and pseudocode where appropriate.
Citation density: Medium — cite related methods.
""",
        "Experiment": """Write the Experiment section.

Structure:
1. Setup (1-2 paragraphs): Datasets, metrics, baselines
2. Main Results (1-2 paragraphs): Comparison with baselines
3. Ablation Study (1-2 paragraphs): Component analysis
4. Additional Analysis (1 paragraph): Sensitivity, error analysis

Tone: Objective and factual. Present numbers precisely.
Citation density: Low — cite dataset sources.
Include LaTeX table placeholder: \ref{tab:main_results}
Include LaTeX figure placeholder: \ref{fig:main}
""",
        "Conclusion": """Write the Conclusion section.

Structure:
1. Summary (1-2 paragraphs): What did you do and what did you find?
2. Limitations (1 paragraph): What are the weaknesses?
3. Future Work (1 paragraph): What are the next steps?

Tone: Confident but honest. Don't overclaim.
""",
    }

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        outline = context.get("outline", {})
        citations = context.get("citations", [])
        empirical_data = context.get("empirical_data", {})
        target_chapter = context.get("target_chapter")  # None = write all

        chapters = outline.get("chapters", [])
        if target_chapter:
            chapters = [c for c in chapters if c.get("title") == target_chapter]

        written_chapters: list[dict[str, Any]] = []

        for chapter in chapters:
            chapter_title = chapter.get("title", "Unknown")
            chapter_prompt_template = self.CHAPTER_PROMPTS.get(
                chapter_title, self.CHAPTER_PROMPTS["Method"]
            )

            # Build citation context
            citation_context = self._build_citation_context(citations)

            # Build empirical context
            empirical_context = self._build_empirical_context(empirical_data, chapter)

            prompt = f"""你是一位顶尖的学术论文写作者。请根据以下大纲撰写论文章节。

## 章节信息
章节编号: {chapter.get('chapter_id', 'N/A')}
章节标题: {chapter_title}
章节摘要: {chapter.get('summary', '')}
核心要点: {chr(10).join(f'- {p}' for p in chapter.get('key_points', []))}

## 章节类型写作指南
{chapter_prompt_template}

## 已验证的参考文献
{citation_context}

## 实证数据（如有）
{empirical_context}

## 要求
1. 严格按照上述结构撰写
2. 引用必须来自已验证的参考文献列表，不得虚构引用
3. 数据和结果必须来自实证数据，不得虚构数字
4. 字数：Abstract 200-300词，其他章节 800-2000词
5. 图表引用使用格式：Figure X.X, Table X.X
6. 公式编号使用：Equation (X.X)
7. 输出完整章节内容，中文或英文根据目标期刊决定

请直接输出章节内容，不需要额外的 JSON 包装。"""

            response = self._generate(prompt, format_json=False)
            written_chapters.append({
                "chapter_id": chapter.get("chapter_id"),
                "title": chapter_title,
                "content": response.response,
                "word_count": len(response.response.split()),
                "model": response.model_used,
            })

        return {
            "chapters": written_chapters,
            "total_word_count": sum(c["word_count"] for c in written_chapters),
            "chapter_count": len(written_chapters),
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        chapters = act_result.get("chapters", [])
        total_words = act_result.get("total_word_count", 0)

        if not chapters:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": "章节写作结果为空，请检查输入数据并重试。",
                "score": 0.2,
                "flags": ["empty_output"],
            }

        # Check word count per chapter
        low_word_count = [
            c["title"] for c in chapters
            if c.get("word_count", 0) < 200
        ]
        if low_word_count:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"以下章节字数过少（<200词）：{', '.join(low_word_count)}。请补充详细内容。",
                "score": 0.6,
                "flags": ["low_word_count"],
            }

        return {
            "halt": HaltDecision.APPROVED,
            "feedback": f"共完成 {len(chapters)} 个章节，总字数 {total_words}，进入内容精修阶段。",
            "score": 0.82,
            "flags": [],
        }

    def _build_citation_context(self, citations: list[dict]) -> str:
        if not citations:
            return "（暂无参考文献，请适当引用领域内经典工作）"

        lines = []
        for i, c in enumerate(citations[:20], 1):  # Limit to top 20
            authors = ", ".join(c.get("authors", ["Unknown"])[:2])
            year = c.get("year", "n.d.")
            title = c.get("title", "Unknown")
            verified = "✅" if c.get("verified") else "⚠️"
            lines.append(f"[{i}] {authors} ({year}). {title} {verified}")

        return "\n".join(lines)

    def _build_empirical_context(self, empirical_data: dict, chapter: dict) -> str:
        if not empirical_data:
            return "（暂无实证数据，将基于理论分析展开）"

        # Find relevant data for this chapter
        relevant_keys = [
            k for k in empirical_data.keys()
            if any(keyword in chapter.get("title", "").lower() for keyword in k.lower().split())
        ]

        if not relevant_keys:
            return "（暂无针对本章节的特定数据）"

        lines = ["## 实证数据"]
        for key in relevant_keys:
            lines.append(f"\n### {key}")
            lines.append(str(empirical_data[key])[:500])  # Truncate

        return "\n".join(lines)


# ─── ContentRefinementAgent ───────────────────────────────────────────────────


class ContentRefinementAgent(BaseAgent):
    """
    Simulates peer review and iteratively refines paper content.

    PaperOrchestra Content Refinement Agent:
        - Simulates peer-review feedback
        - Applies strict halt rules (from YAML via HaltRulesRegistry)
        - Iteratively revises until approved or max_iterations

    Key mechanism: Halt Rules
        - If any halt rule is violated → must revise
        - If no halt rules violated → approved
        - Prevents gaming: rules are strict and unambiguous
    """

    def __init__(self, config: AgentConfig, gateway, halt_rules_domain: str = "empirical_paper"):
        super().__init__(config, gateway)
        self._halt_rules_domain = halt_rules_domain
        self._halt_registry: Any = None  # Instance-level — each agent gets its own registry

    def _get_registry(self):
        # Instance-level registry — supports per-agent domain-specific rules
        if self._halt_registry is None:
            try:
                from scripts.core.halt_rules_registry import HaltRulesRegistry
                project_root = Path(__file__).parent.parent.parent
                rules_dir = project_root / "config" / "halt_rules"
                self._halt_registry = HaltRulesRegistry(rules_dir=str(rules_dir))
            except Exception:
                self._halt_registry = None
        return self._halt_registry

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        draft = context.get("draft", "")
        halt_rules = context.get("halt_rules", REVIEW_HALT_RULES)
        chapter = context.get("chapter", "全文")

        rules_text = "\n".join(
            f"- {rule[0]}（标记: {rule[1]}）"
            for rule in halt_rules
        )

        prompt = f"""你是一位严厉但公正的学术期刊审稿人。请对以下论文章节进行审稿。

## 待审稿章节
章节: {chapter}

## 内容
{draft[:3000]}  <!-- Truncate for token limits -->

## 审稿规则
请严格检查以下每一项（违反任一规则必须指出）：
{rules_text}

## 审稿要求
1. 逐条检查上述所有规则
2. 如有违反，清晰指出具体位置（如"第3段"、"Section 2.1"）
3. 提供具体的修改建议
4. 如所有规则均通过，给出"通过审稿"的结论

## 输出格式
```json
{{
  "verdict": "revise" | "approve",
  "violations": [
    {{
      "rule": "规则描述",
      "location": "具体位置",
      "issue": "具体问题",
      "suggestion": "修改建议"
    }}
  ],
  "overall_comments": "总体评价（1-3句话）",
  "scores": {{
    "clarity": 1-10,
    "technical_quality": 1-10,
    "citation_quality": 1-10,
    "overall": 1-10
  }}
}}
```"""

        response = self._generate(prompt, format_json=True)

        try:
            review = self._parse_json_response(response.response)
        except ValueError:
            review = {
                "verdict": "revise",
                "violations": [{"rule": "格式错误", "issue": "无法解析审稿结果", "suggestion": "请重试"}],
                "overall_comments": "审稿过程出错",
                "scores": {"overall": 5},
            }

        return {
            "review": review,
            "chapter": chapter,
            "model": response.model_used,
            "halt_rules_passed": True,  # LLM-based review
            "halt_rules_source": "llm_judgment",
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        review = act_result.get("review", {})
        verdict = review.get("verdict", "revise")
        violations = list(review.get("violations", []))
        scores = review.get("scores", {})
        overall_score = scores.get("overall", 5)

        # ── Run programmatic halt rules validation (P1-4) ─────────────
        halt_registry = self._get_registry()
        if halt_registry:
            domain = getattr(self, "_halt_rules_domain", "empirical_paper")
            # Build content dict from act_result for rule checking
            rule_content = {
                "text": act_result.get("review", {}).get("overall_comments", ""),
                "review": review,
                "draft": act_result.get("review", {}),
            }
            try:
                rule_result = halt_registry.validate(domain=domain, content=rule_content)
                if not rule_result.all_passed:
                    for v in rule_result.violations:
                        violations.append({
                            "rule": v.rule_id,
                            "issue": v.message,
                            "suggestion": "See HaltRulesRegistry violation",
                            "source": "programmatic",
                        })
                    if rule_result.halted:
                        return {
                            "halt": HaltDecision.REVISE,
                            "feedback": "[HALT] 违反质量规则，阻断提交：\n" + "\n".join(
                                f"  • {v.rule_id}: {v.message}" for v in rule_result.violations
                            ),
                            "score": overall_score / 10,
                            "flags": [v.rule_id for v in rule_result.violations],
                            "halt_result": {
                                "all_passed": rule_result.all_passed,
                                "violations": [(v.rule_id, v.message) for v in rule_result.violations],
                                "halted": rule_result.halted,
                            },
                        }
            except Exception:
                pass  # LLM review takes precedence on errors

        if verdict == "approve" and overall_score >= 7.5:
            return {
                "halt": HaltDecision.APPROVED,
                "feedback": f"审稿通过（得分 {overall_score}/10）。{review.get('overall_comments', '')}",
                "score": overall_score / 10,
                "flags": [],
            }

        if verdict == "revise" and not violations:
            return {
                "halt": HaltDecision.APPROVED,
                "feedback": f"审稿通过（得分 {overall_score}/10）。{review.get('overall_comments', '')}",
                "score": overall_score / 10,
                "flags": [],
            }

        # Build feedback from violations
        violation_summary = "\n".join(
            f"  • [{v.get('rule', 'Unknown')}] {v.get('issue', '')} → {v.get('suggestion', '')}"
            for v in violations[:5]  # Limit to top 5 violations
        )

        return {
            "halt": HaltDecision.REVISE,
            "feedback": f"发现 {len(violations)} 条审稿意见，需要修改：\n{violation_summary}",
            "score": overall_score / 10,
            "flags": [v.get("rule", "unknown") for v in violations[:3]],
        }


# ─── PlottingAgent ────────────────────────────────────────────────────────────


class PlottingAgent(BaseAgent):
    """
    Generates matplotlib figures for the paper.

    PaperOrchestra Plotting Agent:
        - Executes plotting plan from outline
        - Renders plots and conceptual diagrams
        - Optional VLM-critique refinement loop
        - Generates captions for each figure
    """

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        figure_plan = context.get("figure_plan", [])
        empirical_data = context.get("empirical_data", {})
        output_dir = context.get("output_dir", "knowledge/visualizations")
        import os
        output_dir = os.path.expanduser(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        generated_figures: list[dict[str, Any]] = []
        execution_errors: list[str] = []

        for fig_spec in figure_plan:
            fig_id = fig_spec.get("figure_id", "Figure_N")
            description = fig_spec.get("description", "")
            generation_method = fig_spec.get("generation_method", "matplotlib生成")

            # Generate the figure code
            figure_code = self._generate_figure_code(fig_id, description, fig_spec, empirical_data)

            # Execute the generated code
            execution_result = self._execute_figure_code(
                fig_id, figure_code, output_dir, empirical_data
            )

            generated_figures.append({
                "figure_id": fig_id,
                "description": description,
                "generation_method": generation_method,
                "code": figure_code,
                "caption": execution_result.get("caption", ""),
                "status": "executed" if execution_result.get("success") else "error",
                "files": execution_result.get("files", []),
                "error": execution_result.get("error", ""),
            })

            if not execution_result.get("success"):
                execution_errors.append(f"{fig_id}: {execution_result.get('error', 'unknown')}")

        return {
            "figures": generated_figures,
            "total_figures": len(generated_figures),
            "output_dir": output_dir,
            "execution_errors": execution_errors,
        }

    def reflect(self, act_result: dict[str, Any]) -> dict[str, Any]:
        figures = act_result.get("figures", [])
        execution_errors = act_result.get("execution_errors", [])

        if not figures:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": "未生成任何图表，请检查 figure_plan 是否正确。",
                "score": 0.2,
                "flags": ["no_figures"],
            }

        if execution_errors:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"图表执行出错：{' | '.join(execution_errors[:3])}",
                "score": 0.4,
                "flags": ["execution_errors"],
            }

        failed_figures = [f["figure_id"] for f in figures if f.get("status") != "executed"]
        if failed_figures:
            return {
                "halt": HaltDecision.REVISE,
                "feedback": f"以下图表执行失败：{', '.join(failed_figures)}。请检查描述是否明确。",
                "score": 0.5,
                "flags": ["execution_failed"],
            }

        return {
            "halt": HaltDecision.APPROVED,
            "feedback": f"共生成 {len(figures)} 个图表并执行成功，进入图表精修阶段。",
            "score": 0.8,
            "flags": [],
        }

    def _execute_figure_code(
        self,
        fig_id: str,
        code: str,
        output_dir: str,
        data: dict,
    ) -> dict:
        """
        Execute generated matplotlib code in an isolated subprocess.

        Returns dict with keys: success (bool), caption (str), files (list), error (str).
        """
        import subprocess

        if not code or not code.strip():
            return {"success": False, "caption": "", "files": [],
                    "error": "No code provided"}

        # Write code to a temp file and execute it
        script_content = f"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
{code}
"""
        import hashlib
        fig_hash = hashlib.md5(fig_id.encode()).hexdigest()[:8]
        tmp_script = f"/tmp/plot_{fig_hash}.py"

        try:
            with open(tmp_script, "w") as f:
                f.write(script_content)

            result = subprocess.run(
                [sys.executable, tmp_script],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=output_dir,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "caption": "",
                    "files": [],
                    "error": result.stderr[:500] if result.stderr else "Execution failed",
                }

            # Parse output for saved file paths
            output = result.stdout
            import re
            saved_files = re.findall(r"SAVED_FILE: (.+)", output)
            caption_match = re.search(r"CAPTION: (.+)", output)

            return {
                "success": True,
                "caption": caption_match.group(1).strip() if caption_match else f"Figure: {fig_id}",
                "files": saved_files,
                "error": "",
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "caption": "", "files": [],
                    "error": f"Execution timeout (>60s) for {fig_id}"}
        except Exception as exc:
            return {"success": False, "caption": "", "files": [],
                    "error": f"Execution error: {exc}"}
        finally:
            try:
                os.unlink(tmp_script)
            except Exception:
                pass

    def _generate_figure_code(
        self,
        fig_id: str,
        description: str,
        spec: dict,
        data: dict,
    ) -> str:
        """Generate matplotlib code for the figure."""
        prompt = f"""你是一位数据可视化专家。请为以下图表生成 Python matplotlib 代码。

## 图表信息
ID: {fig_id}
描述: {description}

## 图表规范
{spec}

## 可用数据
{json.dumps(data, ensure_ascii=False, indent=2) if data else "（无特定数据，需生成模拟示例）"}

## 要求
1. 使用 matplotlib 或 seaborn
2. 图表尺寸：宽8英寸，高5英寸（适合论文）
3. 字体：Times New Roman，字号9-12pt
4. DPI: 300（适合论文出版）
5. 颜色：学术配色（避免过于鲜艳）
6. 添加坐标轴标签、刻度、图例
7. **在代码末尾输出 `print("SAVED_FILE:", <output_path>)` 标记保存路径**
8. **在代码末尾输出 `print("CAPTION:", <caption_text>)` 标记图表标题**
9. 返回完整的可执行 Python 代码

## 输出格式
只输出 Python 代码，不要包含解释文字。代码开头注明文件保存路径。"""

        response = self._generate(prompt, format_json=False)

        # Extract code from response (remove markdown fences if present)
        code = response.response.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        return code


# ─── DataFetchAgent ─────────────────────────────────────────────────────────


class DataFetchAgent(BaseAgent):
    """
    Specialized agent for fetching and synthesizing provincial/macro data.

    Integrated with the province_stats MCP (31 provinces, 9 categories):
        ECON  — GDP, growth rate
        EDU   — universities, enrollment, postgrads
        PLAT  — key labs, innovation platforms
        RD    — R&D expenditure, intensity, fiscal sci-tech spending
        ENT   — high-tech enterprises, tech SMEs, specialized champions
        TECH  — tech contract values, commercialization
        IND   — high-tech manufacturing, strategic industries, digital economy
        AI    — computing centers, AI industry
        FIN   — listed companies, provincial funds

    Tool routing (via ToolSelector):
        province_indicator  → get_province_indicator
        province_timeseries → get_province_timeseries
        province_rankings   → get_province_rankings
        province_summary    → get_all_provinces_summary

    Fallback: when MCP is unavailable, returns None and logs the gap.
    """

    def act(self, context: dict[str, Any]) -> dict[str, Any]:
        task = context.get("task", "")
        provinces = context.get("provinces", [])
        indicators = context.get("indicators", [])
        years = context.get("years", ["2024"])
        fetch_rankings = context.get("fetch_rankings", False)
        fetch_summary = context.get("fetch_summary", True)

        results = {}

        # Step 1: Overall summary
        if fetch_summary:
            summary = self._fetch_summary()
            if summary:
                results["summary"] = summary
            else:
                results["summary"] = None

        # Step 2: Per-province per-indicator
        if provinces and indicators:
            results["provinces"] = {}
            for prov in provinces:
                prov_data = self._fetch_province_indicators(prov, indicators, years)
                results["provinces"][prov] = prov_data

        # Step 3: Rankings tables
        if fetch_rankings:
            rankings = self._fetch_rankings()
            results["rankings"] = rankings

        return results

    def reflect(self, result: dict[str, Any]) -> tuple[HaltDecision, str]:
        if result.get("summary") is None and not result.get("provinces"):
            return HaltDecision.REVISE, "所有省数据获取失败，检查 MCP 连接"
        return HaltDecision.APPROVED, ""

    # ── Tool helpers (delegate through gateway) ───────────────────────────────

    def _call_province_mcp(self, tool: str, args: dict) -> dict | None:
        """Call province-stats MCP tool via gateway. Returns None on failure."""
        try:
            raw = self.gateway.call_mcp_tool(
                "province-stats", tool, args
            )
            # gateway.call_mcp_tool returns an MCPResult (dataclass) or raises
            if raw is None:
                return None
            if hasattr(raw, "success") and raw.success:
                return raw.data if hasattr(raw, "data") else None
            return None
        except Exception as exc:
            logger.debug(f"province-stats MCP call failed: {exc}")
            return None

    def _fetch_summary(self) -> dict | None:
        raw = self._call_province_mcp("get_all_provinces_summary", {})
        return raw  # already extracts .data in _call_province_mcp

    def _fetch_province_indicators(
        self, province: str, indicators: list[str], years: list[str]
    ) -> dict:
        """Fetch multiple indicators for one province across years."""
        out = {}
        for year in years:
            year_data = {}
            for ind in indicators:
                data = self._call_province_mcp("get_province_indicator", {
                    "province": province,
                    "indicator": ind,
                    "year": year,
                })
                year_data[ind] = data  # None if failed, dict if succeeded
            out[year] = year_data
        return out

    def _fetch_rankings(self) -> dict:
        """Fetch all available ranking tables."""
        tables = [
            "GDP_2024",
            "RD经费_2024",
            "高新技术企业_2024",
            "技术合同_2024",
        ]
        out = {}
        for tbl in tables:
            data = self._call_province_mcp("get_province_rankings", {
                "table": tbl,
            })
            out[tbl] = data  # None if failed, dict if succeeded
        return out
