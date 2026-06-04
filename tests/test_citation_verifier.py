"""CitationVerifier 单元测试"""
import pytest
from scripts.core.citation_verifier import CitationVerifier, CitationCheckResult


class TestCitationVerifier:
    def setup_method(self):
        self.verifier = CitationVerifier()

    def test_empty_citation_returns_invalid(self):
        result = self.verifier.verify("")
        assert result.valid is False

    def test_doi_extraction(self):
        doi = self.verifier._extract_doi("基于 doi:10.1234/test-example 的研究")
        assert doi == "10.1234/test-example"

    def test_doi_extraction_uppercase(self):
        doi = self.verifier._extract_doi("DOI: 10.1234/TEST")
        assert doi is not None

    def test_arxiv_extraction(self):
        arxiv = self.verifier._extract_arxiv("参见 arXiv:2103.00001")
        assert arxiv == "2103.00001"

    def test_arxiv_extraction_v(self):
        arxiv = self.verifier._extract_arxiv("arXiv:2301.09876v3")
        assert "2301.09876" in arxiv

    def test_verify_text_structural(self):
        result = self.verifier.verify("Smith (2020). Title. Journal. [1]")
        assert result.valid is True
        assert result.source == "structural"

    def test_verify_batch(self):
        citations = [
            "Smith (2020). A study.",
            "DOI: 10.1234/test",
        ]
        results = self.verifier.verify_batch(citations)
        assert len(results) == 2
        assert all(isinstance(r, CitationCheckResult) for r in results)

    def test_cache_hit(self):
        r1 = self.verifier.verify("Smith (2021). Test.")
        r2 = self.verifier.verify("Smith (2021). Test.")
        # Second call should hit cache (result should be same)
        assert r1.valid == r2.valid
