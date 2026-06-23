"""Tests for scripts/research_framework/provenance_rag.py"""
import pytest
import tempfile
from pathlib import Path


class TestNumberExtractor:
    def test_extracts_coefficients_from_latex(self):
        from scripts.research_framework.provenance_rag import NumberExtractor
        extractor = NumberExtractor()
        latex = r"""\documentclass{article}
\begin{document}
\begin{tabular}{lcc}
treated \times post & 0.0234*** & (0.0082) \\
Green patents & 0.156** & (0.0621) \\
R&D intensity & 0.089* & (0.0456) \\
N & \multicolumn{2}{c}{3842} \\
R$^2$ & \multicolumn{2}{c}{0.623} \\
\end{tabular}
\end{document}"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as f:
            f.write(latex)
            f.flush()
            results = extractor.extract_from_latex(f.name)

        assert len(results) > 0
        coefs = [r for r in results if r.is_coefficient]
        assert len(coefs) >= 2
        assert any(r.value > 0 for r in coefs)

    def test_extracts_pvalues(self):
        from scripts.research_framework.provenance_rag import NumberExtractor
        extractor = NumberExtractor()
        latex = r"""\documentclass{article}
\begin{document}
\textit{test} p-value = 0.0234 p < 0.05
\end{document}"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as f:
            f.write(latex)
            f.flush()
            results = extractor.extract_from_latex(f.name)
        pvals = [r for r in results if r.is_pvalue]
        assert len(pvals) >= 1

    def test_empty_latex(self):
        from scripts.research_framework.provenance_rag import NumberExtractor
        extractor = NumberExtractor()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as f:
            f.write(r"\documentclass{article}\begin{document}\end{document}")
            f.flush()
            results = extractor.extract_from_latex(f.name)
        assert isinstance(results, list)


class TestProvenanceRAG:
    def test_initializes(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG
        with tempfile.TemporaryDirectory() as tmpdir:
            rag = ProvenanceRAG(persist_dir=tmpdir)
            assert rag is not None
            assert len(rag) == 0

    def test_indexes_latex_paper(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG
        latex = r"""\documentclass{article}
\begin{document}
\begin{tabular}{lcc}
treated \times post & 0.0234*** & (0.0082) \\
N & \multicolumn{2}{c}{3842} \\
\end{tabular}
\end{document}"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paper_path = Path(tmpdir) / "test.tex"
            paper_path.write_text(latex)
            rag = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag")
            n = rag.index_paper(paper_path, paper_id="test_paper")
            assert n > 0
            assert len(rag) > 0

    def test_query_bm25_returns_results(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG
        latex = r"""\documentclass{article}
\begin{document}
carbon trading innovation effect = 0.0234***
\end{document}"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paper_path = Path(tmpdir) / "test.tex"
            paper_path.write_text(latex)
            rag = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag")
            rag.index_paper(paper_path, paper_id="test")
            results = rag.query("carbon trading innovation", top_k=3)
            assert isinstance(results, list)

    def test_save_and_load(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG
        with tempfile.TemporaryDirectory() as tmpdir:
            rag = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag")
            rag._documents = [{"id": "d1", "text": "test", "type": "coefficient", "value": 1.23}]
            rag._next_id = 1
            save_path = rag.save()
            rag2 = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag")
            rag2.load(save_path)
            assert len(rag2) == 1

    def test_filter_by_significance(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG, ProvenanceResult
        results = [
            ProvenanceResult(text="a", score=0.9, source="Table 1", significance_stars="***"),
            ProvenanceResult(text="b", score=0.8, source="Table 1", significance_stars="**"),
            ProvenanceResult(text="c", score=0.7, source="Table 1", significance_stars="*"),
        ]
        rag = ProvenanceRAG()
        filtered = rag.filter_by_significance("**", results)
        assert len(filtered) == 2  # *** and **

    def test_get_number_by_id(self):
        from scripts.research_framework.provenance_rag import ProvenanceRAG
        with tempfile.TemporaryDirectory() as tmpdir:
            rag = ProvenanceRAG(persist_dir=Path(tmpdir) / "rag")
            rag._documents = [{"id": "num_1", "text": "test coef", "type": "coefficient", "value": 0.5}]
            rag._next_id = 1
            result = rag.get_number_by_id("num_1")
            assert result is not None
            assert result.coefficient == 0.5


class TestProvenanceResult:
    def test_to_dict(self):
        from scripts.research_framework.provenance_rag import ProvenanceResult
        r = ProvenanceResult(
            text="test text",
            score=0.95,
            source="Table 1",
            coefficient=0.0234,
            pvalue=0.001,
        )
        d = r.to_dict()
        assert d["text"] == "test text"
        assert d["score"] == 0.95
        assert d["coefficient"] == 0.0234

    def test_defaults(self):
        from scripts.research_framework.provenance_rag import ProvenanceResult
        r = ProvenanceResult(text="test", score=0.5, source="Table 1")
        assert r.provenance == ""
        assert r.node_ids == []
        assert r.citations == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
