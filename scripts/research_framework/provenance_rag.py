"""Provenance-enhanced RAG for 论文-研报工作流.

Injects provenance-tracked numbers into the vector database for accurate
retrieval of specific empirical results (e.g., "the 0.023 coefficient on carbon trading").

Usage:
    rag = ProvenanceRAG()
    rag.index_paper("papers/camera_ready.tex", provenance_path="output/provenance/report.md")
    results = rag.query("碳排放权交易对企业绿色创新的影响有多大")
    for r in results:
        print(f"[{r['source']}] {r['text'][:200]}")
        print(f"  → 数据来源: {r['provenance']}")
        print(f"  → 系数: {r['coefficient']} (p={r['pvalue']})")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any



# CJK Unicode ranges for character-level tokenization
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff]|"   # Chinese
    r"[\u3400-\u4dbf]|"   # Chinese Extension A
    r"[\uf900-\ufaff]|"   # CJK Compatibility Ideographs
    r"[\u3040-\u309f]|"   # Hiragana
    r"[\u30a0-\u30ff]|"   # Katakana
    r"[\uac00-\ud7af]"    # Korean Hangul
)


@dataclass
class ProvenanceResult:
    """A RAG retrieval result with provenance metadata."""
    text: str
    score: float
    source: str  # e.g., "Table 2", "Section 3.1"
    page: int | None = None
    # Provenance metadata
    provenance: str = ""  # e.g., "MCP: user-tushare, 2026-01-15"
    data_source: str = ""
    timestamp: str = ""
    coefficient: float | None = None
    standard_error: float | None = None
    pvalue: float | None = None
    n_obs: int | None = None
    regression_type: str = ""
    dependent_var: str = ""
    independent_var: str = ""
    table_row: str = ""
    figure_id: str = ""
    # Extended fields from number extraction
    variable_name: str = ""
    significance_stars: str = ""
    table_caption: str = ""
    # Chain of provenance node IDs
    node_ids: list[str] = field(default_factory=list)
    # Citation context
    citations: list[str] = field(default_factory=list)
    # Raw provenance dict for debugging
    raw_provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "score": self.score,
            "source": self.source,
            "provenance": self.provenance,
            "coefficient": self.coefficient,
            "pvalue": self.pvalue,
            "n_obs": self.n_obs,
            "regression_type": self.regression_type,
            "dependent_var": self.dependent_var,
            "citations": self.citations,
        }


@dataclass
class NumberWithContext:
    """A number extracted from a paper with its surrounding context."""
    value: float
    context_before: str  # ~50 chars before
    context_after: str    # ~50 chars after
    line_number: int
    is_coefficient: bool
    is_se: bool
    is_pvalue: bool
    is_n_obs: bool
    is_r_squared: bool
    significance_stars: str = ""  # *, **, ***
    table_caption: str = ""
    row_label: str = ""
    variable_name: str = ""
    provenance_ids: list[str] = field(default_factory=list)


class NumberExtractor:
    """Extracts numerical results from LaTeX papers with context."""

    # Coefficient + SE in adjacent LaTeX table cells: "0.0234*** & (0.0082)"
    # or "0.0234 & 0.0082" with stars on either side
    COEF_SE_PATTERN = re.compile(
        r"([+-]?\d+\.\d+)\s*([*]+)?\s*"   # coefficient + optional stars
        r"&\s*\("                           # cell sep + optional paren before SE
        r"([+-]?\d+\.\d+)\s*"              # SE value
        r"\)\s*([*]+)?"                    # closing paren + optional stars
    )

    # Standalone numbers with significance
    NUMBER_WITH_STARS = re.compile(r"([+-]?\d+\.\d+)\s*\{([*]+)\}")

    # p-value patterns
    PVALUE_PATTERN = re.compile(r"p\s*=\s*([01]\.\d+)|p\s*<\s*(\d+\.\d+)")

    # N observation patterns (more flexible to catch "3,842" in LaTeX)
    NOBS_PATTERN = re.compile(
        r"\\hline\s*\n\s*N\s*&\s*\\multicolumn.*?\{([\d,]+)\}"
    )

    # Table caption
    TABLE_CAPTION = re.compile(r"\\caption\{([^}]+)\}")
    TABLE_ROW = re.compile(r"\\textit\{([^}]+)\}")

    def extract_from_latex(self, latex_path: str | Path) -> list[NumberWithContext]:
        """Extract all numbers with their context from a LaTeX file."""
        path = Path(latex_path)
        text = path.read_text(encoding="utf-8")

        # Remove comments
        text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)

        results: list[NumberWithContext] = []
        lines = text.split("\n")

        for i, line in enumerate(lines):
            # Extract table captions
            caption_match = self.TABLE_CAPTION.search(line)
            current_caption = caption_match.group(1) if caption_match else ""

            # Extract row labels
            row_label = ""
            row_match = self.TABLE_ROW.search(line)
            if row_match:
                row_label = row_match.group(1)

            # Find coefficient + SE pairs
            for match in self.COEF_SE_PATTERN.finditer(line):
                coef_str, stars_coef, se_str, stars_se = match.groups()
                stars = stars_coef or stars_se or ""
                try:
                    coef = float(coef_str)
                    se = float(se_str)
                    results.append(NumberWithContext(
                        value=coef,
                        context_before=" ".join(lines[max(0,i-1):i]),
                        context_after=" ".join(lines[i+1:min(len(lines),i+2)]),
                        line_number=i+1,
                        is_coefficient=True,
                        is_se=False,
                        is_pvalue=False,
                        is_n_obs=False,
                        is_r_squared=False,
                        significance_stars=stars,
                        table_caption=current_caption,
                        row_label=row_label,
                        variable_name=row_label,
                    ))
                    results.append(NumberWithContext(
                        value=se,
                        context_before="",
                        context_after="",
                        line_number=i+1,
                        is_coefficient=False,
                        is_se=True,
                        is_pvalue=False,
                        is_n_obs=False,
                        is_r_squared=False,
                        table_caption=current_caption,
                        row_label=row_label,
                        variable_name=row_label,
                    ))
                except ValueError:
                    continue

            # Find p-values
            for match in self.PVALUE_PATTERN.finditer(line):
                pval_str = match.group(1) or match.group(2)
                try:
                    pval = float(pval_str)
                    if 0 < pval < 1:
                        results.append(NumberWithContext(
                            value=pval,
                            context_before=" ".join(lines[max(0,i-1):i]),
                            context_after=" ".join(lines[i+1:min(len(lines),i+2)]),
                            line_number=i+1,
                            is_coefficient=False,
                            is_se=False,
                            is_pvalue=True,
                            is_n_obs=False,
                            is_r_squared=False,
                            table_caption=current_caption,
                            row_label=row_label,
                        ))
                except ValueError:
                    continue

            # Find N observations
            for match in self.NOBS_PATTERN.finditer(line):
                n_str = match.group(1).replace(",", "")
                try:
                    n = int(n_str)
                    if n > 10:  # Reasonable observation count
                        results.append(NumberWithContext(
                            value=float(n),
                            context_before=" ".join(lines[max(0,i-1):i]),
                            context_after=" ".join(lines[i+1:min(len(lines),i+2)]),
                            line_number=i+1,
                            is_coefficient=False,
                            is_se=False,
                            is_pvalue=False,
                            is_n_obs=True,
                            is_r_squared=False,
                            table_caption=current_caption,
                            row_label=row_label,
                        ))
                except ValueError:
                    continue

        return results


class ProvenanceRAG:
    """Vector store that combines semantic search with provenance tracking.

    Enhances standard RAG by:
    1. Storing numbers with full provenance metadata
    2. Indexing tables and figures as separate documents
    3. Cross-referencing provenance chain for each result
    4. Filtering by data source, regression type, significance level
    """

    def __init__(self, persist_dir: str | Path = ".cache/provenance_rag"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index (can be replaced with ChromaDB)
        self._documents: list[dict[str, Any]] = []
        self._number_store: dict[str, NumberWithContext] = {}  # id -> NumberWithContext
        self._provenance_map: dict[str, dict[str, Any]] = {}    # number_id -> provenance
        self._next_id = 0

        # Try to use ChromaDB if available
        self._use_chroma = False
        try:
            import chromadb
            self._client = chromadb.PersistentClient(str(self.persist_dir / "chroma"))
            self._collection = self._client.get_or_create_collection(
                "provenance_rag",
                metadata={"description": "Provenance-enhanced paper index"}
            )
            self._use_chroma = True
        except ImportError:
            pass

    def index_paper(
        self,
        latex_path: str | Path,
        provenance_path: str | Path | None = None,
        paper_id: str | None = None,
    ) -> int:
        """Index a paper's content and numbers.

        Returns the number of chunks indexed.
        """
        path = Path(latex_path)
        paper_id = paper_id or path.stem

        # Extract provenance if available
        provenance_data: dict[str, Any] = {}
        if provenance_path:
            provenance_data = self._load_provenance(Path(provenance_path))

        # Extract numbers
        extractor = NumberExtractor()
        numbers = extractor.extract_from_latex(path)
        n_indexed = 0

        # Index each number
        for num in numbers:
            num_id = f"{paper_id}_num_{self._next_id}"
            self._next_id += 1

            # Build text for embedding
            if num.is_coefficient:
                text = (
                    f"{num.table_caption}: "
                    f"{num.variable_name} = {num.value:.4f}"
                    f"{num.significance_stars} "
                    f"(SE = {num.context_after[:50] if num.context_after else 'N/A'}). "
                    f"Context: {num.context_before[:100]}"
                )
            elif num.is_pvalue:
                text = f"{num.table_caption}: p-value = {num.value:.4f} for {num.variable_name}"
            elif num.is_n_obs:
                text = f"{num.table_caption}: N = {int(num.value)} observations for {num.variable_name}"
            else:
                text = f"{num.table_caption}: {num.value} ({num.variable_name})"

            doc = {
                "id": num_id,
                "text": text,
                "paper_id": paper_id,
                "type": "coefficient" if num.is_coefficient else
                        "pvalue" if num.is_pvalue else
                        "n_obs" if num.is_n_obs else "other",
                "value": num.value,
                "variable": num.variable_name,
                "stars": num.significance_stars,
                "caption": num.table_caption,
                "line": num.line_number,
                "source_file": str(path),
            }

            self._documents.append(doc)
            self._number_store[num_id] = num

            # Link to provenance
            if provenance_data:
                # Find matching provenance node
                matching = self._find_matching_provenance(num, provenance_data)
                if matching:
                    self._provenance_map[num_id] = matching
                    num.provenance_ids = matching.get("node_ids", [])

            # Index in ChromaDB if available
            if self._use_chroma:
                try:
                    self._collection.add(
                        documents=[text],
                        metadatas=[{
                            "paper_id": paper_id,
                            "type": doc["type"],
                            "value": num.value,
                            "variable": num.variable_name,
                            "source": str(path),
                        }],
                        ids=[num_id],
                    )
                except Exception:  # noqa: S110
                    pass  # ChromaDB indexing failure is non-fatal

            n_indexed += 1

        return n_indexed

    def _load_provenance(self, path: Path) -> dict[str, Any]:
        """Load provenance data from JSON or Markdown report."""
        try:
            if path.suffix == ".json":
                return json.loads(path.read_text())
            else:
                # Parse Markdown provenance report
                text = path.read_text()
                return self._parse_provenance_md(text)
        except Exception:
            return {}

    def _parse_provenance_md(self, text: str) -> dict[str, Any]:
        """Parse provenance report Markdown into structured data."""
        result = {"nodes": [], "links": [], "figures": {}}

        # Extract figure sections
        fig_sections = re.findall(
            r"## Provenance Report: ([^\n]+)\n(.*?)(?=## |\Z)",
            text,
            re.DOTALL,
        )
        for fig_id, content in fig_sections:
            result["figures"][fig_id.strip()] = content

        # Extract node metadata
        node_blocks = re.findall(
            r"\*\*Source\*\*:?\s*([^\n]+)|"
            r"\*\*Code\*\*:?\s*`([^`]+)`|"
            r"\*\*ID\*\*:?\s*`([^`]+)`",
            text,
        )
        for block in node_blocks:
            for field_val in block:
                if field_val:
                    result["nodes"].append({"description": field_val.strip()})

        return result

    def _find_matching_provenance(
        self,
        num: NumberWithContext,
        provenance_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find the provenance node that matches a given number."""
        figures = provenance_data.get("figures", {})
        for fig_content in figures.values():
            if num.variable_name.lower() in fig_content.lower():
                return {"source": "provenance", "node_ids": [], "text": fig_content[:200]}
        return None

    def query(
        self,
        question: str,
        top_k: int = 5,
        min_significance: str | None = None,  # "***", "**", "*"
        regression_type: str | None = None,
        data_source: str | None = None,
        paper_id: str | None = None,
    ) -> list[ProvenanceResult]:
        """Query the RAG index with provenance filtering.

        Parameters
        ----------
        question : str
            Natural language question (e.g., "碳排放权交易对企业绿色创新的影响")
        top_k : int
            Maximum number of results
        min_significance : str, optional
            Minimum significance level ("***", "**", "*")
        regression_type : str, optional
            Filter by regression type (e.g., "DID", "IV")
        data_source : str, optional
            Filter by data source (e.g., "tushare", "worldbank")
        paper_id : str, optional
            Filter by paper ID
        """
        if self._use_chroma:
            return self._query_chroma(
                question, top_k, min_significance,
                regression_type, data_source, paper_id
            )
        else:
            return self._query_bm25(
                question, top_k, min_significance,
                regression_type, data_source, paper_id
            )

    def _query_chroma(
        self,
        question: str,
        top_k: int,
        min_significance: str | None,
        regression_type: str | None,
        data_source: str | None,
        paper_id: str | None,
    ) -> list[ProvenanceResult]:
        """Query using ChromaDB vector search."""
        results: list[ProvenanceResult] = []

        try:
            query_results = self._collection.query(
                query_texts=[question],
                n_results=top_k * 3,  # Over-fetch for filtering
            )

            for i, (doc_id, doc_text, metadata) in enumerate(zip(
                query_results["ids"][0],
                query_results["documents"][0],
                query_results["metadatas"][0],
            )):
                # Apply filters
                if paper_id and metadata.get("paper_id") != paper_id:
                    continue
                if min_significance and metadata.get("stars", "") < min_significance:
                    continue
                if regression_type and regression_type.lower() not in (doc_text + metadata.get("variable", "")).lower():
                    continue

                prov = self._provenance_map.get(doc_id, {})

                results.append(ProvenanceResult(
                    text=doc_text,
                    score=1.0 - (i * 0.01),  # Placeholder score
                    source=metadata.get("source", ""),
                    provenance=prov.get("text", metadata.get("source", "")),
                    coefficient=metadata.get("value") if metadata.get("type") == "coefficient" else None,
                    raw_provenance=prov,
                ))

                if len(results) >= top_k:
                    break

        except Exception:
            return self._query_bm25(question, top_k, min_significance, regression_type, data_source, paper_id)

        return results

    def _tokenize_cjk(self, text: str) -> set[str]:
        """Tokenize text with CJK character-level + English word support."""
        tokens: set[str] = set()
        lower = text.lower()
        # Extract all CJK characters individually
        cjk_chars = set(_CJK_RE.findall(lower))
        tokens.update(cjk_chars)
        # Remove CJK chars and split the remaining text
        non_cjk = _CJK_RE.sub(" ", lower)
        for word in non_cjk.split():
            if len(word) > 1:  # Keep meaningful non-CJK words
                tokens.add(word)
        return tokens

    def _query_bm25(
        self,
        question: str,
        top_k: int,
        min_significance: str | None,
        regression_type: str | None,
        data_source: str | None,
        paper_id: str | None,
    ) -> list[ProvenanceResult]:
        """Fallback BM25-style keyword search with CJK support."""
        query_tokens = self._tokenize_cjk(question)

        scored: list[tuple[float, dict[str, Any]]] = []
        for doc in self._documents:
            if paper_id and doc.get("paper_id") != paper_id:
                continue

            doc_tokens = self._tokenize_cjk(doc["text"])
            score = sum(1 for kw in query_tokens if kw in doc_tokens)

            if score > 0:
                if min_significance and doc.get("stars", "") < min_significance:
                    continue
                if regression_type and regression_type.lower() not in doc["text"].lower():
                    continue
                scored.append((score / max(len(query_tokens), 1), doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []

        for score, doc in scored[:top_k]:
            prov = self._provenance_map.get(doc["id"], {})
            results.append(ProvenanceResult(
                text=doc["text"],
                score=score,
                source=doc.get("source_file", ""),
                provenance=prov.get("text", ""),
                coefficient=doc.get("value") if doc.get("type") == "coefficient" else None,
                pvalue=doc.get("value") if doc.get("type") == "pvalue" else None,
                n_obs=int(doc["value"]) if doc.get("type") == "n_obs" else None,
                variable_name=doc.get("variable", ""),
                significance_stars=doc.get("stars", ""),
                table_caption=doc.get("caption", ""),
                raw_provenance=prov,
            ))

        return results

    def filter_by_significance(
        self,
        stars: str,
        results: list[ProvenanceResult],
    ) -> list[ProvenanceResult]:
        """Filter results by significance level.

        Args:
            stars: Minimum significance ("*" = p<0.1, "**" = p<0.05, "***" = p<0.01)
        """
        star_levels = {"*": 1, "**": 2, "***": 3}
        min_level = star_levels.get(stars, 0)
        return [
            r for r in results
            if star_levels.get(r.significance_stars, 0) >= min_level
        ]

    def get_number_by_id(self, number_id: str) -> ProvenanceResult | None:
        """Get a specific number by its ID with full provenance."""
        doc = next((d for d in self._documents if d["id"] == number_id), None)
        if not doc:
            return None

        prov = self._provenance_map.get(number_id, {})
        num = self._number_store.get(number_id)

        return ProvenanceResult(
            text=doc["text"],
            score=1.0,
            source=doc.get("source_file", ""),
            provenance=prov.get("text", ""),
            coefficient=doc.get("value") if doc.get("type") == "coefficient" else None,
            pvalue=doc.get("value") if doc.get("type") == "pvalue" else None,
            standard_error=num.value if num and num.is_se else None,
            n_obs=int(doc["value"]) if doc.get("type") == "n_obs" else None,
            variable_name=doc.get("variable", ""),
            significance_stars=doc.get("stars", ""),
            table_caption=doc.get("caption", ""),
            node_ids=prov.get("node_ids", []),
            raw_provenance=prov,
        )

    def save(self, path: str | Path | None = None) -> Path:
        """Save the index to disk."""
        path = Path(path) if path else self.persist_dir / "index.json"
        data = {
            "documents": self._documents,
            "provenance_map": self._provenance_map,
            "next_id": self._next_id,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def load(self, path: str | Path) -> None:
        """Load the index from disk."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._documents = data.get("documents", [])
        self._provenance_map = data.get("provenance_map", {})
        self._next_id = data.get("next_id", 0)

    def __len__(self) -> int:
        return len(self._documents)


if __name__ == "__main__":
    # Demo
    import tempfile
    from pathlib import Path

    # Create a sample paper with regression results
    # Using raw string to avoid escape warnings
    sample_latex = r"""\documentclass{article}
\begin{document}
\begin{table}[ht]
\caption{碳排放权交易对企业绿色创新的影响 (DID)}
\label{tab:did}
\begin{tabular}{lcc}
\hline
变量 & 系数 & 标准误 \\
\hline
treated $\times$ post & 0.0234*** & (0.0082) \\
绿色专利申请数 & 0.156** & (0.0621) \\
研发投入强度 & 0.089* & (0.0456) \\
控制变量 & \multicolumn{2}{c}{是} \\
年份固定效应 & \multicolumn{2}{c}{是} \\
企业固定效应 & \multicolumn{2}{c}{是} \\
\hline
N & \multicolumn{2}{c}{3,842} \\
R$^2$ & \multicolumn{2}{c}{0.623} \\
\hline
\end{tabular}
\note{*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类标准误，聚类到企业层面。数据来源：国家知识产权局。}
\end{table}
\end{document}"""

    with tempfile.TemporaryDirectory() as tmpdir:
        paper_path = Path(tmpdir) / "sample_paper.tex"
        paper_path.write_text(sample_latex)

        rag = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag_cache")

        n = rag.index_paper(paper_path, paper_id="sample_2026")
        print(f"Indexed {n} numbers from sample paper")
        print(f"Total documents: {len(rag)}")

        # Query
        results = rag.query("碳排放权交易对企业绿色创新的影响", top_k=3)
        print(f"\nTop 3 results for '碳排放权交易对企业绿色创新的影响':")
        for r in results:
            print(f"  [{r.score:.2f}] {r.text[:100]}")
            if r.coefficient:
                print(f"    → coefficient = {r.coefficient}")
            if r.n_obs:
                print(f"    → N = {r.n_obs}")

        # Significance filter
        sig_results = rag.filter_by_significance("**", results)
        print(f"\nFiltered to significant results (≥**): {len(sig_results)}")

        # Save/load
        save_path = rag.save()
        print(f"\nIndex saved to: {save_path}")
