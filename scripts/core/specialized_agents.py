"""Specialized Review Agents for Academic Paper Review.

Six specialized agents for comprehensive paper quality assurance:
    1. ProofreaderAgent      — Grammar, flow, LaTeX structure
    2. RReviewerAgent       — R/Stata code validation
    3. TikZCriticAgent      — Figure quality review
    4. AdversarialQAAgent   — Skeptical referee questions
    5. LiteratureGapAgent   — Contribution claim verification
    6. DataAuditAgent       — Result number verification
"""

from __future__ import annotations

__all__ = [
    "AgentTask",
    "ReviewFinding",
    "AgentReviewResult",
    "_get_llm_gateway",
]

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.core.llm_gateway import LLMGateway


def _get_llm_gateway():
    """Lazy import to avoid platform.py shadowing issue."""
    from scripts.core.llm_gateway import LLMGateway
    return LLMGateway


class AgentTask(str, Enum):
    """Task type for routing."""
    PROOFREAD = "proofread"
    R_CODE_REVIEW = "r_code_review"
    TIKZ_REVIEW = "tikz_review"
    ADVERSARIAL_QA = "adversarial_qa"
    LITERATURE_GAP = "literature_gap"
    DATA_AUDIT = "data_audit"


@dataclass
class ReviewFinding:
    """A single finding from a review agent."""
    severity: str  # "critical", "major", "minor", "suggestion"
    category: str
    location: str  # e.g., "Section 2.1", "Table 1", "Figure 2"
    description: str
    suggestion: str | None = None
    line_ref: int | None = None


@dataclass
class AgentReviewResult:
    """Result from a specialized review agent."""
    agent: AgentTask
    findings: list[ReviewFinding] = field(default_factory=list)
    summary: str = ""
    pass_flag: bool = True  # True = ready for submission
    review_time_seconds: float = 0.0
    raw_response: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def major_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "major")

    def to_dict(self) -> dict:
        return {
            "agent": self.agent.value,
            "findings": [
                {"severity": f.severity, "category": f.category,
                 "location": f.location, "description": f.description,
                 "suggestion": f.suggestion}
                for f in self.findings
            ],
            "summary": self.summary,
            "pass": self.pass_flag,
            "review_time": self.review_time_seconds,
        }


class ProofreaderAgent:
    r"""Reviews grammar, flow, LaTeX structure, and writing quality.

    Checks:
    - Ambiguous pronouns (it/this/that without clear antecedent)
    - Tense consistency (past vs present)
    - Section transitions and logical flow
    - Figure/table reference formatting (\ref{}, \cref{})
    - Novelty claim accuracy
    - Jargon overuse
    """

    def __init__(self, gateway: LLMGateway | None = None):
        self.gateway = gateway or _get_llm_gateway()
        self.prompt_template = """You are a professional academic paper proofreader specializing in {journal} journal style.

Review the following paper text. For each issue found, output a JSON object:
{{"findings": [{{"severity": "critical"|"major"|"minor"|"suggestion", "category": "...", "location": "...", "description": "...", "suggestion": "..."}}]}}

CHECKS TO PERFORM:
1. AMBIGUOUS PRONOUNS: Flag "it", "this", "that", "they", "these" without clear antecedent
2. TENSE: Flag inconsistent tense (e.g., "we find" in methodology but "we found" in results)
3. SECTION FLOW: Flag missing transitions between paragraphs/sections
4. FIGURE REFS: Flag missing \\ref{} or \\cref{} for any figure mentioned
5. TABLE REFS: Flag missing \\ref{} for any table mentioned
6. NUMBER CONSISTENCY: Flag when numbers in text differ from table values
7. JARGON: Flag overuse of technical jargon without explanation
8. NOVELTY CLAIMS: Flag phrases like "first to", "novel", "new" — verify they're justified

PAPER TEXT:
{paper_text}

JOURNAL: {journal}
LANGUAGE: {language}

Output JSON only:"""

    async def review(
        self,
        paper_text: str,
        journal: str = "JF",
        language: str = "en",
    ) -> AgentReviewResult:
        import time
        t0 = time.time()

        prompt = self.prompt_template.format(
            paper_text=paper_text[:8000],  # token limit
            journal=journal,
            language=language,
        )

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            # Parse JSON from response
            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # Try extracting from markdown code block
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                else:
                    data = {"findings": []}

            findings = [
                ReviewFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "unknown"),
                    location=f.get("location", "unknown"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion"),
                )
                for f in data.get("findings", [])
            ]

            return AgentReviewResult(
                agent=AgentTask.PROOFREAD,
                findings=findings,
                summary=f"Found {len(findings)} issues: {sum(1 for f in findings if f.severity in ('critical','major'))} major+",
                pass_flag=len([f for f in findings if f.severity == "critical"]) == 0,
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.PROOFREAD,
                findings=[],
                summary=f"Review failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
                raw_response=str(exc),
            )


class RReviewerAgent:
    """Validates R/Stata code blocks in paper appendices.

    Checks:
    - Package version compatibility
    - Deprecated function usage
    - Syntax correctness
    - Required library imports
    - Seed setting for reproducibility
    - Output column names matching paper claims
    """

    def __init__(self, gateway: LLMGateway | None = None):
        self.gateway = gateway or _get_llm_gateway()

    async def review_code(self, code: str, language: str = "r") -> AgentReviewResult:
        """Review R or Stata code for correctness and reproducibility."""
        import time
        t0 = time.time()

        prompt = f"""You are an R/Stata code reviewer for academic economics papers.

Review the following {language} code. For each issue:
{{"findings": [{{"severity": "critical"|"major"|"minor", "category": "...", "location": "line X", "description": "...", "suggestion": "..."}}]}}

CHECKS:
1. SYNTAX: Missing parentheses, braces, commas
2. PACKAGE DEPENDENCIES: Missing library() or require() calls
3. DEPRECATED FUNCTIONS: Flag known deprecated functions
   - R: "map" from base R (deprecated), use purrr::map
   - R: "gather/spread" from tidyr (deprecated), use pivot_longer/pivot_wider
   - Stata: "xi:" prefix (deprecated), use i. prefix
4. REPRODUCIBILITY: Missing set.seed() before random operations
5. VARIABLE NAMES: Check if column names in output match paper claims
6. MISSING VALUES: Check na.rm=TRUE for summary statistics
7. CLUSTERING: Check if cluster() or vcovCL() used properly

CODE:
```{language}
{code}
```

Output JSON only:"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                data = json.loads(match.group(1)) if match else {"findings": []}

            findings = [
                ReviewFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "unknown"),
                    location=f.get("location", "unknown"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion"),
                )
                for f in data.get("findings", [])
            ]

            return AgentReviewResult(
                agent=AgentTask.R_CODE_REVIEW,
                findings=findings,
                summary=f"{language.upper()} code review: {len(findings)} issues found",
                pass_flag=len([f for f in findings if f.severity == "critical"]) == 0,
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.R_CODE_REVIEW,
                findings=[],
                summary=f"Code review failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
            )


class TikZCriticAgent:
    """Reviews TikZ/PGFPlots figures for publication quality.

    Checks:
    - Axis labels (units, font size)
    - Colorblind-safe palettes (viridis, colorblind-safe)
    - Font consistency (same family/size across all figures)
    - Legend placement and clarity
    - Appropriate figure width (not exceeding text width)
    - No rasterized elements in vector output
    """

    async def review_tikz(self, tikz_code: str) -> AgentReviewResult:
        """Review TikZ/PGFPlots figure code."""
        import time
        t0 = time.time()

        prompt = f"""You are a TikZ/PGFPlots figure reviewer for economics papers.

Review the following figure code for publication quality:
{{"findings": [{{"severity": "critical"|"major"|"minor", "category": "...", "location": "line X or component", "description": "...", "suggestion": "..."}}]}}

CHECKS:
1. AXIS LABELS: Must include units (e.g., "%", "$ USD millions")
2. COLORBLIND SAFETY: Flag Red-Green patterns; recommend viridis/plasma/cividis
3. FONT SIZES: Check all nodes use consistent sizing (\\footnotesize or \\small)
4. LINE WIDTHS: Standardize across subplots
5. LEGEND: Check for overlapping elements
6. FIGURE WIDTH: Warn if > 0.95\\\\textwidth
7. ASPECT RATIO: Flag if too tall or too wide
8. QUALITY: Flag raster images (\\includegraphics with jpg/png in LaTeX)

TIKZ/PGFPLOTS CODE:
```
{tikz_code}
```

Output JSON only:"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                data = json.loads(match.group(1)) if match else {"findings": []}

            findings = [
                ReviewFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "unknown"),
                    location=f.get("location", "unknown"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion"),
                )
                for f in data.get("findings", [])
            ]

            return AgentReviewResult(
                agent=AgentTask.TIKZ_REVIEW,
                findings=findings,
                summary=f"TikZ review: {len(findings)} issues",
                pass_flag=len([f for f in findings if f.severity == "critical"]) == 0,
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.TIKZ_REVIEW,
                findings=[],
                summary=f"TikZ review failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
            )


def _evaluate_qa_pass(
    questions: list[dict],
    strict_mode: bool,
    min_questions_loose: int = 1,
    min_questions_strict: int = 5,
    min_hard_strict: int = 3,
) -> bool:
    """评估 AdversarialQA 生成的 questions 是否通过 gate。

    P1 修复 2026-06-28: 加入 strict mode 让用户控制通过严格度。

    Args:
        questions: 从 LLM 解析出的问题列表（每项含 dimension/question/difficulty）
        strict_mode: True=严格模式（>= min_questions_strict + >= min_hard_strict hard）
                     False=loose（>= min_questions_loose 即可）
        min_questions_loose: loose 模式最少问题数（默认 1）
        min_questions_strict: strict 模式最少问题数（默认 5）
        min_hard_strict: strict 模式最少 hard 难度问题（默认 3）

    Returns:
        True if pass, False otherwise
    """
    if not questions:
        return False

    if not strict_mode:
        # Loose: 任何问题都算通过（与原始行为兼容）
        return len(questions) >= min_questions_loose

    # Strict: 必须有足够多问题 + 足够多 hard 难度问题
    if len(questions) < min_questions_strict:
        return False

    hard_count = sum(
        1 for q in questions if str(q.get("difficulty", "")).lower() == "hard"
    )
    return hard_count >= min_hard_strict


class AdversarialQAAgent:
    """Generates hard skeptical questions simulating a tough referee.

    Generates questions across dimensions:
    - Identification: "What if parallel trends is violated?"
    - External validity: "Does this generalize to..."
    - Mechanism: "How do you rule out the alternative mechanism?"
    - Data: "What if measurement error in X is classical?"
    - Robustness: "What if you use alternative definitions?"

    P1 修复 2026-06-28：加入 ``strict_mode`` config flag 让用户选择严格度。

    Modes:
      - ``loose`` (默认): pass_flag=True 仅当生成 0 个问题（向后兼容，原始行为）
      - ``strict``: pass_flag 基于质量评估（question 覆盖维度、难度分布）
    """

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        strict_mode: bool | None = None,
    ):
        """初始化。

        Args:
            gateway: LLM 网关
            strict_mode: 严格模式。None=读环境变量 ADVERSARIAL_QA_STRICT；
                默认 ``"0"`` (loose)。设为 ``"1"`` 或 True 开启 strict 模式。
        """
        self.gateway = gateway or _get_llm_gateway()
        if strict_mode is None:
            env_val = os.environ.get("ADVERSARIAL_QA_STRICT", "0").lower()
            strict_mode = env_val in ("1", "true", "yes", "on")
        self.strict_mode = strict_mode

    async def generate_questions(
        self,
        paper_text: str,
        num_questions: int = 10,
    ) -> AgentReviewResult:
        """Generate adversarial questions a skeptical referee might ask."""
        import time
        t0 = time.time()

        prompt = f"""You are a skeptical, adversarial referee for an economics paper.

Generate {num_questions} hard questions that challenge the paper's claims.
Format as JSON:
{{"questions": [{{"dimension": "...", "question": "...", "difficulty": "easy"|"medium"|"hard", "response_guidance": "..."}}]}}

DIMENSIONS TO CHALLENGE:
1. IDENTIFICATION: Parallel trends assumption, SUTVA violation, no anticipation
2. EXTERNAL VALIDITY: Would results hold in different samples/contexts?
3. MECHANISM: Alternative mechanisms that could explain the result
4. MEASUREMENT: Classical vs non-classical measurement error
5. SELECTION: Selection on observables vs unobservables
6. SPILLOVERS: General equilibrium effects, SUTVA violations
7. HETEROGENEITY: Heterogeneous effects that could bias aggregate estimate
8. ROBUSTNESS: Alternative specifications, placebo tests
9. CAUSALITY vs CORRELATION: Are results truly causal?
10. REPLICATION: Is the sample size sufficient for the reported effects?

PAPER:
{paper_text[:6000]}

Output JSON only:"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                data = json.loads(match.group(1)) if match else {"questions": []}

            questions = data.get("questions", [])

            findings = [
                ReviewFinding(
                    severity="major",  # Adversarial questions are always important
                    category=q.get("dimension", "unknown"),
                    location="Referee question",
                    description=q.get("question", ""),
                    suggestion=q.get("response_guidance"),
                )
                for q in questions
            ]

            return AgentReviewResult(
                agent=AgentTask.ADVERSARIAL_QA,
                findings=findings,
                summary=f"Generated {len(questions)} adversarial questions (strict={self.strict_mode})",
                # P1 修复 2026-06-28：pass_flag 基于 strict_mode + 问题质量
                # loose 模式: 与原行为一致（生成问题即通过）
                # strict 模式: 必须生成 >= 3 个 hard 难度问题才算通过
                pass_flag=_evaluate_qa_pass(
                    questions=questions,
                    strict_mode=self.strict_mode,
                ),
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.ADVERSARIAL_QA,
                findings=[],
                summary=f"Question generation failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
            )


class LiteratureGapAgent:
    """Verifies contribution claims against the literature review.

    Checks:
    - "First to study X" claims are accurate
    - Novelty claims are verifiable
    - Related literature is properly cited
    - No known prior studies are omitted
    """

    def __init__(self, gateway: LLMGateway | None = None):
        self.gateway = gateway or _get_llm_gateway()

    async def verify_claims(
        self,
        contribution_statement: str,
        lit_review_summary: str,
    ) -> AgentReviewResult:
        """Verify novelty and contribution claims against literature."""
        import time
        t0 = time.time()

        prompt = f"""You are a literature review expert verifying contribution claims.

CONTRIBUTION STATEMENT TO VERIFY:
"{contribution_statement}"

LITERATURE REVIEW SUMMARY:
{lit_review_summary[:4000]}

Generate findings:
{{"findings": [{{"severity": "critical"|"major"|"minor", "category": "claim_verification", "location": "...", "description": "...", "suggestion": "..."}}]}}

CHECKS:
1. "FIRST TO": Search mentally for counterexamples, flag if uncertain
2. NOVELTY CLAIMS: Compare against literature summary, flag overclaims
3. MISSING CITATIONS: Flag key related studies not mentioned
4. METHODOLOGY UNIQUENESS: Is the specific empirical strategy novel?
5. SAMPLE UNIQUENESS: Is the sample/data source truly unique?
6. OVERCLAIMING: Flag language like "completely", "entirely", "universally"

Output JSON only:"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                data = json.loads(match.group(1)) if match else {"findings": []}

            findings = [
                ReviewFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "unknown"),
                    location=f.get("location", "unknown"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion"),
                )
                for f in data.get("findings", [])
            ]

            return AgentReviewResult(
                agent=AgentTask.LITERATURE_GAP,
                findings=findings,
                summary=f"Contribution claim verification: {len(findings)} concerns",
                pass_flag=len([f for f in findings if f.severity == "critical"]) == 0,
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.LITERATURE_GAP,
                findings=[],
                summary=f"Claim verification failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
            )


class DataAuditAgent:
    """Verifies every number in results matches regression output files.

    Compares:
    - Table values in LaTeX against output JSON files
    - Numbers in text against table values
    - Coefficients with reported standard errors
    - Sample sizes across tables
    """

    def __init__(self, gateway: LLMGateway | None = None):
        self.gateway = gateway or _get_llm_gateway()

    async def audit_numbers(
        self,
        latex_tables: dict[str, str],
        regression_outputs: dict[str, Any],
    ) -> AgentReviewResult:
        """Audit every number in LaTeX tables against regression outputs."""
        import time
        t0 = time.time()

        prompt = f"""You are a data auditor for an economics paper.

Verify that every number in LaTeX tables matches the regression output files.
Format:
{{"findings": [{{"severity": "critical"|"major"|"minor", "category": "data_mismatch", "location": "...", "description": "...", "suggestion": "..."}}]}}

CHECKS:
1. COEFFICIENT MATCH: Table values vs JSON output values
2. STANDARD ERRORS: Reported SE matches JSON output
3. SAMPLE SIZES: N across tables is consistent
4. R-SQUARED: Reported R² matches JSON output
5. SIGNIFICANCE STARS: * p<0.1, ** p<0.05, *** p<0.01 matches actual p-values
6. NUMBER PRECISION: Check for rounding errors (e.g., 0.001 vs 0.0009)
7. TABLE CONSISTENCY: Same dependent variable across tables uses consistent precision

LATEX TABLES:
{str(latex_tables)[:3000]}

REGRESSION OUTPUTS:
{str(regression_outputs)[:3000]}

Output JSON only:"""

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.gateway.generate(prompt, format_json=True),
            )
            text = response.response if hasattr(response, "response") else str(response)

            import json
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                data = json.loads(match.group(1)) if match else {"findings": []}

            findings = [
                ReviewFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "unknown"),
                    location=f.get("location", "unknown"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion"),
                )
                for f in data.get("findings", [])
            ]

            return AgentReviewResult(
                agent=AgentTask.DATA_AUDIT,
                findings=findings,
                summary=f"Data audit: {len(findings)} discrepancies found",
                pass_flag=len([f for f in findings if f.severity in ("critical", "major")]) == 0,
                review_time_seconds=time.time() - t0,
                raw_response=text,
            )
        except Exception as exc:
            return AgentReviewResult(
                agent=AgentTask.DATA_AUDIT,
                findings=[],
                summary=f"Data audit failed: {exc}",
                pass_flag=False,
                review_time_seconds=time.time() - t0,
            )


# Convenience function to run all agents
async def run_all_agents(
    paper_text: str,
    latex_tables: dict[str, str] | None = None,
    code_blocks: dict[str, str] | None = None,
    contribution: str | None = None,
    lit_review: str | None = None,
    regression_outputs: dict[str, Any] | None = None,
    journal: str = "JF",
    gateway: LLMGateway | None = None,
) -> dict[str, AgentReviewResult]:
    """Run all 6 specialized review agents in parallel."""
    import asyncio

    latex_tables = latex_tables or {}
    code_blocks = code_blocks or {}
    regression_outputs = regression_outputs or {}

    tasks = []

    # Proofreader
    tasks.append(ProofreaderAgent(gateway).review(paper_text, journal=journal))

    # R/Stata code review
    for lang, code in code_blocks.items():
        tasks.append(RReviewerAgent(gateway).review_code(code, language=lang))

    # Adversarial QA
    tasks.append(AdversarialQAAgent(gateway).generate_questions(paper_text, num_questions=10))

    # Literature gap
    if contribution and lit_review:
        tasks.append(LiteratureGapAgent(gateway).verify_claims(contribution, lit_review))

    # Data audit
    if latex_tables and regression_outputs:
        tasks.append(DataAuditAgent(gateway).audit_numbers(latex_tables, regression_outputs))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build result dict
    output: dict[str, AgentReviewResult] = {}
    idx = 0
    output["proofreader"] = results[idx] if idx < len(results) else None
    idx += 1

    for lang in code_blocks:
        output[f"r_review_{lang}"] = results[idx] if idx < len(results) else None
        idx += 1

    output["adversarial_qa"] = results[idx] if idx < len(results) else None
    idx += 1

    if contribution and lit_review:
        output["literature_gap"] = results[idx] if idx < len(results) else None
        idx += 1

    if latex_tables and regression_outputs:
        output["data_audit"] = results[idx] if idx < len(results) else None

    return output


if __name__ == "__main__":
    import asyncio
    import sys
    import importlib.util
    from pathlib import Path

    # Add project root to sys.path so 'scripts' package is found
    _project_root = Path(__file__).resolve().parents[2]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

    async def test():
        # Load the module directly WITHOUT triggering scripts/__init__.py
        # This avoids the platform.py shadowing issue
        _module_path = _project_root / "scripts" / "core" / "specialized_agents.py"
        _spec = importlib.util.spec_from_file_location(
            "specialized_agents", _module_path
        )
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["specialized_agents"] = _module
        _spec.loader.exec_module(_module)

        # Now we can access all classes
        ProofreaderAgent = _module.ProofreaderAgent
        RReviewerAgent = _module.RReviewerAgent
        TikZCriticAgent = _module.TikZCriticAgent
        AdversarialQAAgent = _module.AdversarialQAAgent
        LiteratureGapAgent = _module.LiteratureGapAgent
        DataAuditAgent = _module.DataAuditAgent
        ReviewFinding = _module.ReviewFinding
        AgentReviewResult = _module.AgentReviewResult
        AgentTask = _module.AgentTask
        run_all_agents = _module.run_all_agents

        # Verify dataclass fields
        rf_fields = [f.name for f in ReviewFinding.__dataclass_fields__.values()]
        arr_fields = [f.name for f in AgentReviewResult.__dataclass_fields__.values()]
        task_values = [e.value for e in AgentTask]

        # Verify all agent types are present
        assert AgentTask.PROOFREAD.value == "proofread"
        assert AgentTask.R_CODE_REVIEW.value == "r_code_review"
        assert AgentTask.TIKZ_REVIEW.value == "tikz_review"
        assert AgentTask.ADVERSARIAL_QA.value == "adversarial_qa"
        assert AgentTask.LITERATURE_GAP.value == "literature_gap"
        assert AgentTask.DATA_AUDIT.value == "data_audit"

        # Verify ReviewFinding fields
        assert "severity" in rf_fields
        assert "category" in rf_fields
        assert "location" in rf_fields
        assert "description" in rf_fields
        assert "suggestion" in rf_fields

        # Verify AgentReviewResult fields
        assert "agent" in arr_fields
        assert "findings" in arr_fields
        assert "summary" in arr_fields
        assert "pass_flag" in arr_fields
        assert "review_time_seconds" in arr_fields

        # Verify AgentReviewResult properties
        arr = AgentReviewResult(agent=AgentTask.PROOFREAD)
        assert hasattr(arr, "critical_count")
        assert hasattr(arr, "major_count")
        assert hasattr(arr, "to_dict")

        # Verify run_all_agents is async
        import inspect
        assert inspect.iscoroutinefunction(run_all_agents)

        # Verify each agent has the expected methods
        assert hasattr(ProofreaderAgent, "review")
        assert hasattr(RReviewerAgent, "review_code")
        assert hasattr(TikZCriticAgent, "review_tikz")
        assert hasattr(AdversarialQAAgent, "generate_questions")
        assert hasattr(LiteratureGapAgent, "verify_claims")
        assert hasattr(DataAuditAgent, "audit_numbers")

        print("=" * 60)
        print("SPECIALIZED REVIEW AGENTS - TEST RESULTS")
        print("=" * 60)
        print(f"ReviewFinding fields: {rf_fields}")
        print(f"AgentReviewResult fields: {arr_fields}")
        print(f"AgentTask values: {task_values}")
        print("-" * 60)
        print("All 6 agents defined:")
        print("  1. ProofreaderAgent      - Grammar, flow, LaTeX structure")
        print("  2. RReviewerAgent       - R/Stata code validation")
        print("  3. TikZCriticAgent      - Figure quality review")
        print("  4. AdversarialQAAgent   - Skeptical referee questions")
        print("  5. LiteratureGapAgent   - Contribution claim verification")
        print("  6. DataAuditAgent       - Result number verification")
        print("-" * 60)
        print("All tests passed!")

    asyncio.run(test())
