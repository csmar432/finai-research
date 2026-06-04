"""Citation Stance Classifier.

This module classifies academic citations by their stance:
- SUPPORT: Citation explicitly supports the paper's claims
- CONTRAST: Citation offers contrasting or competing views
- NEUTRAL: Citation is merely mentioned
- MENTION: Citation is a passing reference

Reference: JARVIS citation stance classification.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CitationStance(Enum):
    """Citation stance types."""
    SUPPORT = "support"           # Supports the paper's argument
    CONTRAST = "contrast"        # Offers contrasting view
    NEUTRAL = "neutral"          # Neutral reference
    MENTION = "mention"          # Just mentioned


@dataclass
class CitationContext:
    """Context around a citation."""
    citation_marker: str         # e.g., "Smith et al. (2020)"
    surrounding_text: str         # Text before and after citation
    section: str = ""             # Section where citation appears
    claim: str = ""              # Claim being supported/challenged


@dataclass
class CitationAnalysis:
    """Analysis of a single citation."""
    marker: str
    stance: CitationStance
    confidence: float             # 0.0 - 1.0
    reasoning: str
    related_claims: list[str] = field(default_factory=list)


# ─── Stance Detection Patterns ─────────────────────────────────────────────────


class StanceDetector:
    """Detects citation stance based on linguistic patterns."""

    SUPPORT_PATTERNS = [
        r"支持\s*(?:了|着|的)",
        r"证实?\s*(?:了|着|的|表明)",
        r"证明\s*(?:了|着|的)",
        r"符合\s*(?:了|着|的)",
        r"与\s*.+\s*一致",
        r"consistent\s+with",
        r"support(?:s|ed|ing)?\s+the",
        r"confirm(?:s|ed|ing)?\s+the",
        r"validat(?:e|es|ed|ing)\s+the",
        r"demonstrat(?:e|es|ed|ing)\s+that",
        r"show(?:s|ed)?\s+(?:that|the)",
        r"found\s+(?:that|the)",
        r"provide(?:s|d)?\s+evidence\s+for",
        r"同\s*(?:样|样地|样)*\s*表明",
        r"正如\s*.+?\s*所\s*(?:示|说|表明)",
    ]

    CONTRAST_PATTERNS = [
        r"然而?\s*.+",
        r"但是\s*.+",
        r"与\s*.+\s*不同",
        r"与\s*.+\s*相反",
        r"不同于\s*.+",
        r"contrast(?:s|ed|ing)?\s+with",
        r"differ(?:s|ed|ing)?\s+from",
        r"oppos(?:e|es|ed|ing)?\s+to",
        r"against\s+the\s+view",
        r"however\s+.+",
        r"although\s+.+",
        r"whereas\s+.+",
        r"while\s+.+",
        r"然而",
        r"但\s*(?:是\s*)?",
        r"相反",
        r"不同于",
        r"质疑",
        r"挑战\s*(?:了|着|的)",
        r"反驳\s*(?:了|着|的)",
    ]

    NEUTRAL_PATTERNS = [
        r"讨论\s*(?:了|着|的|过)",
        r"分析\s*(?:了|着|的|过)",
        r"研究\s*(?:了|着|的|过)",
        r"提出\s*(?:了|着|的|过)",
        r"认为\s*(?:了|着|的|过)",
        r"指出\s*(?:了|着|的|过)",
        r"discuss(?:es|ed|ing)?\s+the",
        r"analyz(?:e|es|ed|ing)?\s+the",
        r"study\s+(?:the|how)",
        r"propos(?:e|es|ed|ing)?\s+the",
        r"suggest(?:s|ed|ing)?\s+the",
        r"find(?:s|ing)?\s+the",
        r"investigate(?:s|d|ing)?\s+the",
    ]

    MENTION_PATTERNS = [
        r"见\s*.+",
        r"参见\s*.+",
        r"参考\s*.+",
        r"如\s*.+?\s*所示",
        r"see\s+also",
        r"cf\.",
        r"compare\s+with",
        r"see\s+Figure",
        r"see\s+Table",
        r"详细\s*(?:的|见)",
    ]

    def __init__(self):
        self.support_re = [re.compile(p, re.IGNORECASE) for p in self.SUPPORT_PATTERNS]
        self.contrast_re = [re.compile(p, re.IGNORECASE) for p in self.CONTRAST_PATTERNS]
        self.neutral_re = [re.compile(p, re.IGNORECASE) for p in self.NEUTRAL_PATTERNS]
        self.mention_re = [re.compile(p, re.IGNORECASE) for p in self.MENTION_PATTERNS]

    def detect(self, context: CitationContext) -> CitationAnalysis:
        """Detect the stance of a citation."""
        text = context.surrounding_text.lower()

        # Check patterns in order of specificity
        # First check for contrast (most specific)
        for pattern in self.contrast_re:
            if pattern.search(text):
                return CitationAnalysis(
                    marker=context.citation_marker,
                    stance=CitationStance.CONTRAST,
                    confidence=0.8,
                    reasoning=f"Found contrast pattern: {pattern.pattern[:30]}",
                )

        # Then check for support
        for pattern in self.support_re:
            if pattern.search(text):
                return CitationAnalysis(
                    marker=context.citation_marker,
                    stance=CitationStance.SUPPORT,
                    confidence=0.8,
                    reasoning=f"Found support pattern: {pattern.pattern[:30]}",
                )

        # Then check for neutral
        for pattern in self.neutral_re:
            if pattern.search(text):
                return CitationAnalysis(
                    marker=context.citation_marker,
                    stance=CitationStance.NEUTRAL,
                    confidence=0.6,
                    reasoning=f"Found neutral pattern: {pattern.pattern[:30]}",
                )

        # Finally check for mentions
        for pattern in self.mention_re:
            if pattern.search(text):
                return CitationAnalysis(
                    marker=context.citation_marker,
                    stance=CitationStance.MENTION,
                    confidence=0.7,
                    reasoning=f"Found mention pattern: {pattern.pattern[:30]}",
                )

        # Default: neutral
        return CitationAnalysis(
            marker=context.citation_marker,
            stance=CitationStance.NEUTRAL,
            confidence=0.5,
            reasoning="No specific pattern found, defaulting to neutral",
        )


# ─── Citation Extractor ────────────────────────────────────────────────────────


class CitationExtractor:
    """Extracts citations from text."""

    # Patterns for various citation formats
    CITATION_PATTERNS = [
        # (Author, Year) format
        r"([A-Z][a-z]+(?:\s+(?:et\s+al\.|and\s+[A-Z][a-z]+))?(?:\s+(?:et\s+al\.))?)\s*\(\d{4}[a-z]?\)",
        # [1], [2], etc.
        r"\[\d+(?:,\s*\d+)*\]",
        # Author (Year) format
        r"([A-Z][a-z]+(?:\s+(?:et\s+al\.))?)\s*\(\d{4}[a-z]?\)",
    ]

    def __init__(self):
        # Pattern to match various citation formats
        # Supports: Author (Year), [1], Chen et al. (2020), etc.
        self.citation_re = re.compile(
            r'\([A-Z][a-z]+.*?\d{4}[a-z]?\)|'  # Author (Year)
            r'\[\d+(?:,\s*\d+)*\]|'  # [1] or [1,2,3]
            r'\d+\(\d{4}[a-z]?\)|'  # 1(2020)
            r'[\u4e00-\u9fff]{2,}(?:\s+[\u4e00-\u9fff]+)*\s*\(\d{4}[a-z]?\)',  # Chinese names
            re.MULTILINE,
        )

    def extract_citations(self, text: str, context_window: int = 100) -> list[CitationContext]:
        """Extract all citations with surrounding context."""
        citations = []

        for match in self.citation_re.finditer(text):
            marker = match.group(0)
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            surrounding = text[start:end]

            citations.append(CitationContext(
                citation_marker=marker,
                surrounding_text=surrounding,
            ))

        return citations

    def extract_unique_markers(self, text: str) -> list[str]:
        """Extract unique citation markers."""
        markers = set()
        for match in self.citation_re.finditer(text):
            markers.add(match.group(0))
        return sorted(list(markers))


# ─── Citation Stance Classifier ────────────────────────────────────────────────


class CitationStanceClassifier:
    """
    Classifier for citation stance.

    Reference: JARVIS citation stance classification.

    Analyzes academic citations and classifies them as:
    - SUPPORT: Citation supports the paper's claims
    - CONTRAST: Citation offers contrasting view
    - NEUTRAL: Citation is neutral reference
    - MENTION: Citation is merely mentioned
    """

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.detector = StanceDetector()
        self.extractor = CitationExtractor()

    def classify_citations(
        self,
        text: str,
        use_llm_fallback: bool = True,
    ) -> list[CitationAnalysis]:
        """
        Classify all citations in a text.

        Parameters
        ----------
        text : str
            Text containing citations.
        use_llm_fallback : bool
            Use LLM for ambiguous cases.

        Returns
        -------
        list[CitationAnalysis]
            List of citation analyses.
        """
        contexts = self.extractor.extract_citations(text)
        analyses = []

        for context in contexts:
            # Pattern-based detection
            analysis = self.detector.detect(context)

            # If low confidence and LLM available, try LLM
            if analysis.confidence < 0.7 and use_llm_fallback and self.gateway:
                llm_analysis = self._llm_classify(context)
                if llm_analysis:
                    analyses.append(llm_analysis)
                else:
                    analyses.append(analysis)
            else:
                analyses.append(analysis)

        return analyses

    def _llm_classify(self, context: CitationContext) -> CitationAnalysis | None:
        """Use LLM to classify citation stance."""
        if not self.gateway:
            return None

        prompt = f"""分析以下学术引用句子的立场：

引用: {context.citation_marker}
上下文: {context.surrounding_text}

判断立场：
- support: 引用支持了论文的观点
- contrast: 引用提供了对比或质疑
- neutral: 引用是中性讨论
- mention: 引用只是附带提及

请以JSON格式输出：
{{"stance": "support|contrast|neutral|mention", "confidence": 0.0-1.0, "reasoning": "理由"}}"""

        try:
            result = self.gateway.generate(prompt, task_hint="academic_review")
            import re
            json_match = re.search(r'\{.*\}', result.response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return CitationAnalysis(
                    marker=context.citation_marker,
                    stance=CitationStance(data.get("stance", "neutral")),
                    confidence=data.get("confidence", 0.5),
                    reasoning=data.get("reasoning", ""),
                )
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")

        return None

    def generate_report(self, analyses: list[CitationAnalysis]) -> str:
        """Generate a human-readable report."""
        lines = ["# 引用立场分析报告\n"]

        # Count by stance
        counts = {
            CitationStance.SUPPORT: 0,
            CitationStance.CONTRAST: 0,
            CitationStance.NEUTRAL: 0,
            CitationStance.MENTION: 0,
        }

        for a in analyses:
            counts[a.stance] += 1

        lines.append(f"**总引用数**: {len(analyses)}")
        lines.append(f"- 支持性引用: {counts[CitationStance.SUPPORT]} ({counts[CitationStance.SUPPORT]/len(analyses)*100:.0f}%)")
        lines.append(f"- 对比性引用: {counts[CitationStance.CONTRAST]} ({counts[CitationStance.CONTRAST]/len(analyses)*100:.0f}%)")
        lines.append(f"- 中性引用: {counts[CitationStance.NEUTRAL]} ({counts[CitationStance.NEUTRAL]/len(analyses)*100:.0f}%)")
        lines.append(f"- 提及性引用: {counts[CitationStance.MENTION]} ({counts[CitationStance.MENTION]/len(analyses)*100:.0f}%)")
        lines.append("")

        # Detailed analysis
        lines.append("## 详细分析\n")

        stance_names = {
            CitationStance.SUPPORT: "支持性引用",
            CitationStance.CONTRAST: "对比性引用",
            CitationStance.NEUTRAL: "中性引用",
            CitationStance.MENTION: "提及性引用",
        }

        for stance in [CitationStance.SUPPORT, CitationStance.CONTRAST, CitationStance.NEUTRAL, CitationStance.MENTION]:
            relevant = [a for a in analyses if a.stance == stance]
            if relevant:
                lines.append(f"### {stance_names[stance]}\n")
                for a in relevant[:5]:  # Show first 5
                    lines.append(f"- **{a.marker}**: {a.reasoning}")
                lines.append("")

        return "\n".join(lines)


# ─── CLI Interface ──────────────────────────────────────────────────────────────


def main():
    """CLI interface for citation stance classifier."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Citation Stance Classifier")
    parser.add_argument("--text", type=str, help="Text to analyze")
    parser.add_argument("--file", type=str, help="File to analyze")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    # Get text
    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("Please provide --text or --file")
        return

    # Classify
    classifier = CitationStanceClassifier()
    analyses = classifier.classify_citations(text)

    if args.format == "json":
        print(json.dumps([
            {
                "marker": a.marker,
                "stance": a.stance.value,
                "confidence": a.confidence,
                "reasoning": a.reasoning,
            }
            for a in analyses
        ], ensure_ascii=False, indent=2))
    else:
        print(classifier.generate_report(analyses))


if __name__ == "__main__":
    main()
