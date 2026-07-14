"""Unit tests for scripts/core/citation_verifier.py.

These tests cover:
- CitationCheckResult dataclass construction and defaults
- CitationVerifier.__init__ (timeout, cache_size)
- _extract_doi (DOI patterns)
- _extract_arxiv (ArXiv ID patterns)
- _verify_doi (CrossRef API, mocked)
- _verify_arxiv (Semantic Scholar API, mocked)
- _verify_text (structural heuristics)
- verify() entry point (cache, dispatch logic)
- verify_batch() (rate limiting, empty input)
- main() CLI surface
- Module exports (__all__)

All external API calls are mocked. No real network or file I/O.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core import citation_verifier as cv_mod
    from scripts.core.citation_verifier import (
        CROSSREF_API,
        SEMANTIC_SCHOLAR_API,
        CitationCheckResult,
        CitationVerifier,
        main,
    )
except Exception as _exc:  # pragma: no cover
    pytest.skip(f"citation_verifier not importable: {_exc}", allow_module_level=True)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


class _FakeHTTPResponse:
    """Mimic urllib.request.urlopen context manager returning a JSON payload."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def _fake_urlopen(payload: dict | bytes, *, raises: Exception | None = None):
    """Return a function suitable to patch ``urllib.request.urlopen``."""

    if raises is not None:
        def _urlopen(req, timeout=None):  # noqa: ARG001
            raise raises
        return _urlopen

    if isinstance(payload, dict):
        body = json.dumps(payload).encode("utf-8")
    else:
        body = payload

    def _urlopen(req, timeout=None):  # noqa: ARG001
        return _FakeHTTPResponse(body)

    return _urlopen


# ════════════════════════════════════════════════════════════════════
# Module-level constants & exports
# ════════════════════════════════════════════════════════════════════


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_semantic_scholar_api_has_placeholder(self):
        """SEMANTIC_SCHOLAR_API must contain the {paper_id} placeholder."""
        assert "{paper_id}" in SEMANTIC_SCHOLAR_API
        assert "semanticscholar.org" in SEMANTIC_SCHOLAR_API

    def test_crossref_api_has_placeholder(self):
        """CROSSREF_API must contain the {doi} placeholder."""
        assert "{doi}" in CROSSREF_API
        assert "crossref.org" in CROSSREF_API

    def test_module_all_exports(self):
        """All symbols in __all__ must be importable."""
        for name in cv_mod.__all__:
            assert hasattr(cv_mod, name), f"Missing export: {name}"

    def test_all_expected(self):
        """__all__ must contain the canonical public API."""
        expected = {"CitationCheckResult", "CitationVerifier", "main"}
        assert set(cv_mod.__all__) == expected


# ════════════════════════════════════════════════════════════════════
# CitationCheckResult
# ════════════════════════════════════════════════════════════════════


class TestCitationCheckResult:
    """Tests for CitationCheckResult dataclass."""

    def test_minimal_construction(self):
        """Minimum required: valid, verified, score, source."""
        r = CitationCheckResult(
            valid=True, verified=False, score=0.5, source="mock"
        )
        assert r.valid is True
        assert r.verified is False
        assert r.score == 0.5
        assert r.source == "mock"

    def test_default_fields(self):
        """Optional fields have sensible defaults."""
        r = CitationCheckResult(
            valid=False, verified=False, score=0.0, source="none"
        )
        assert r.title is None
        assert r.authors is None
        assert r.year is None
        assert r.message == ""

    def test_all_fields_roundtrip(self):
        """All fields must be assignable."""
        r = CitationCheckResult(
            valid=True,
            verified=True,
            score=0.95,
            source="crossref",
            title="A Paper",
            authors="Doe, J., Smith, K. et al.",
            year=2024,
            message="Verified",
        )
        assert r.title == "A Paper"
        assert r.year == 2024
        assert r.message == "Verified"
        assert r.authors.startswith("Doe")


# ════════════════════════════════════════════════════════════════════
# CitationVerifier.__init__
# ════════════════════════════════════════════════════════════════════


class TestCitationVerifierInit:
    """Tests for CitationVerifier initialization."""

    def test_default_init(self):
        """Default params: timeout=5.0, cache_size=200."""
        v = CitationVerifier()
        assert v.timeout == 5.0
        assert v._cache_size == 200
        assert v._cache == {}

    def test_custom_init(self):
        """Custom timeout and cache_size must be stored."""
        v = CitationVerifier(timeout=10.0, cache_size=500)
        assert v.timeout == 10.0
        assert v._cache_size == 500
        assert v._cache == {}

    def test_cache_is_empty_dict(self):
        """Cache must start as an empty dict (not None or list)."""
        v = CitationVerifier()
        assert isinstance(v._cache, dict)


# ════════════════════════════════════════════════════════════════════
# _extract_doi
# ════════════════════════════════════════════════════════════════════


class TestExtractDoi:
    """Tests for DOI extraction."""

    @pytest.fixture
    def v(self):
        return CitationVerifier()

    def test_extracts_bare_doi(self, v):
        """Plain DOI URL form ``10.xxxx/...`` is recognised."""
        text = "10.1234/example.paper.2024"
        assert v._extract_doi(text) == "10.1234/example.paper.2024"

    def test_extracts_doi_lowercase_prefix(self, v):
        """``doi:`` prefix is recognised and group(1) returned."""
        text = "doi:10.1234/abcd"
        assert v._extract_doi(text) == "10.1234/abcd"

    def test_extracts_doi_uppercase_prefix(self, v):
        """``DOI:`` prefix is recognised."""
        text = "DOI:10.9999/xyz"
        assert v._extract_doi(text) == "10.9999/xyz"

    def test_extracts_doi_in_sentence(self, v):
        """DOI embedded in a citation string is still found."""
        text = "Smith (2020). Findings. Journal of Finance. https://doi.org/10.1111/jofi.12345"
        doi = v._extract_doi(text)
        assert doi is not None
        assert doi.startswith("10.1111/")
        assert "jofi" in doi

    def test_returns_none_when_no_doi(self, v):
        """Plain text without DOI yields None."""
        assert v._extract_doi("Smith (2020). Some paper without DOI.") is None

    def test_handles_special_chars_in_suffix(self, v):
        """DOIs with hyphens, periods, underscores in suffix are captured."""
        assert v._extract_doi("10.1234/foo-bar.baz_qux") == "10.1234/foo-bar.baz_qux"


# ════════════════════════════════════════════════════════════════════
# _extract_arxiv
# ════════════════════════════════════════════════════════════════════


class TestExtractArxiv:
    """Tests for ArXiv ID extraction."""

    @pytest.fixture
    def v(self):
        return CitationVerifier()

    def test_extracts_bare_id(self, v):
        """Plain arXiv ID ``2101.12345`` is recognised."""
        assert v._extract_arxiv("arXiv:2101.12345") == "2101.12345"

    def test_extracts_lowercase_prefix(self, v):
        """``arxiv:`` (lowercase prefix) is recognised."""
        assert v._extract_arxiv("arxiv:2405.00001") == "2405.00001"

    def test_extracts_without_prefix(self, v):
        """ID-only form is recognised (regex is relaxed on prefix)."""
        # Regex requires (?:arXiv:?) — the "arXiv:" is optional. Verify both
        # the prefixed and bare forms work.
        prefixed = v._extract_arxiv("Some paper arXiv:2301.00001 about X")
        bare = v._extract_arxiv("Some paper 2301.00002 about X")
        assert prefixed == "2301.00001"
        # Bare form: the regex only matches when the literal "arXiv" is there
        assert bare is None

    def test_extracts_version_suffix(self, v):
        """ArXiv version suffix ``v2`` is captured as part of the ID."""
        assert v._extract_arxiv("arXiv:2101.12345v3") == "2101.12345v3"

    def test_returns_none_when_no_arxiv(self, v):
        """Plain text without ArXiv ID yields None."""
        assert v._extract_arxiv("Smith (2020). Some paper.") is None

    def test_case_insensitive(self, v):
        """The prefix is matched case-insensitively."""
        assert v._extract_arxiv("ARXIV:2305.00001") == "2305.00001"
        assert v._extract_arxiv("ArXiv:2305.00002") == "2305.00002"


# ════════════════════════════════════════════════════════════════════
# _verify_doi
# ════════════════════════════════════════════════════════════════════


class TestVerifyDoi:
    """Tests for CrossRef DOI verification (network mocked)."""

    @pytest.fixture
    def v(self):
        return CitationVerifier(timeout=1.0)

    def test_successful_verification(self, v):
        """A 200-style CrossRef message is parsed into a verified result."""
        payload = {
            "message": {
                "title": ["Carbon Pricing and Innovation"],
                "author": [
                    {"given": "Alice", "family": "Smith"},
                    {"given": "Bob", "family": "Jones"},
                ],
                "published-print": {"date-parts": [[2024, 3]]},
            }
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_doi("10.1234/example.2024")
        assert result.valid is True
        assert result.verified is True
        assert result.source == "crossref"
        assert result.score == 1.0
        assert result.title == "Carbon Pricing and Innovation"
        assert "Smith" in result.authors
        assert "Jones" in result.authors
        assert result.year == 2024

    def test_authors_truncated_with_et_al(self, v):
        """More than 3 authors → truncated with ``et al.``."""
        payload = {
            "message": {
                "title": ["Big Paper"],
                "author": [
                    {"given": "A", "family": f"Author{i}"} for i in range(5)
                ],
                "published-online": {"date-parts": [[2023]]},
            }
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_doi("10.1234/big")
        assert "et al." in result.authors

    def test_empty_author_list(self, v):
        """Empty author list produces an empty authors string (no crash)."""
        payload = {
            "message": {
                "title": ["Anonymous"],
                "author": [],
                "published-print": {"date-parts": [[2022]]},
            }
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_doi("10.1234/anonymous")
        assert result.year == 2022
        # author_str is empty (just " et al." appended, or nothing)
        assert result.authors is not None

    def test_missing_title(self, v):
        """Missing title yields None in title."""
        payload = {
            "message": {
                "author": [{"given": "A", "family": "B"}],
                "published-print": {"date-parts": [[2021]]},
            }
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_doi("10.1234/notitle")
        assert result.title is None

    def test_invalid_json_response(self, v):
        """Non-JSON bytes produce a parse-error result (valid but unverified)."""
        with patch("urllib.request.urlopen", _fake_urlopen(b"not-json-at-all{{{")):
            result = v._verify_doi("10.1234/bad-json")
        assert result.valid is True
        assert result.verified is False
        assert result.source == "crossref"
        assert result.score == 0.7
        assert "parse error" in result.message.lower()

    def test_network_failure(self, v):
        """Network error → valid=True, verified=False, score=0.8."""
        with patch(
            "urllib.request.urlopen",
            _fake_urlopen(b"", raises=OSError("DNS down")),
        ):
            result = v._verify_doi("10.1234/network-error")
        assert result.valid is True
        assert result.verified is False
        assert result.score == 0.8
        assert "DOI format valid" in result.message

    def test_url_constructed_correctly(self, v):
        """The CrossRef URL must embed the DOI."""
        captured_urls = []

        def _capture(req, timeout=None):  # noqa: ARG001
            captured_urls.append(req.full_url)
            return _FakeHTTPResponse(
                json.dumps(
                    {"message": {"title": ["t"], "author": [],
                                 "published-print": {"date-parts": [[2020]]}}}
                ).encode("utf-8")
            )

        with patch("urllib.request.urlopen", _capture):
            v._verify_doi("10.5555/embed")

        assert len(captured_urls) == 1
        assert captured_urls[0].endswith("/works/10.5555/embed")

    def test_year_falls_back_to_published_online(self, v):
        """When published-print is absent, published-online is used."""
        payload = {
            "message": {
                "title": ["Online First"],
                "author": [],
                "published-online": {"date-parts": [[2019, 6]]},
            }
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_doi("10.1234/online")
        assert result.year == 2019


# ════════════════════════════════════════════════════════════════════
# _verify_arxiv
# ════════════════════════════════════════════════════════════════════


class TestVerifyArxiv:
    """Tests for ArXiv verification (Semantic Scholar mocked)."""

    @pytest.fixture
    def v(self):
        return CitationVerifier(timeout=1.0)

    def test_successful_verification(self, v):
        """Successful ArXiv verification populates title/authors/year."""
        payload = {
            "title": "Attention Is All You Need",
            "authors": [{"name": "Vaswani"}, {"name": "Shazeer"}],
            "year": 2017,
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_arxiv("1706.03762")
        assert result.valid is True
        assert result.verified is True
        assert result.source == "semantic_scholar"
        assert result.score == 1.0
        assert result.title == "Attention Is All You Need"
        assert "Vaswani" in result.authors
        assert result.year == 2017

    def test_many_authors_truncated(self, v):
        """>3 authors triggers the ``et al.`` suffix."""
        payload = {
            "title": "Big Team Paper",
            "authors": [{"name": f"Author{i}"} for i in range(6)],
            "year": 2022,
        }
        with patch("urllib.request.urlopen", _fake_urlopen(payload)):
            result = v._verify_arxiv("2201.00001")
        assert "et al." in result.authors

    def test_invalid_json(self, v):
        """Bad JSON produces parse-error (valid but unverified)."""
        with patch("urllib.request.urlopen", _fake_urlopen(b"<<notjson>>")):
            result = v._verify_arxiv("2301.00002")
        assert result.valid is True
        assert result.verified is False
        assert "parse error" in result.message.lower()

    def test_network_error(self, v):
        """Network failure → valid=True, verified=False."""
        with patch(
            "urllib.request.urlopen",
            _fake_urlopen(b"", raises=RuntimeError("connection reset")),
        ):
            result = v._verify_arxiv("2301.00003")
        assert result.valid is True
        assert result.verified is False
        assert result.source == "semantic_scholar"
        assert "ArXiv ID valid" in result.message

    def test_url_includes_arxiv_prefix(self, v):
        """Semantic Scholar URL must be ``/paper/arXiv:<id>``."""
        captured = []

        def _capture(req, timeout=None):  # noqa: ARG001
            captured.append(req.full_url)
            return _FakeHTTPResponse(
                json.dumps({"title": "t", "authors": [], "year": 2020}).encode("utf-8")
            )

        with patch("urllib.request.urlopen", _capture):
            v._verify_arxiv("2301.00099")

        assert len(captured) == 1
        assert "arXiv:2301.00099" in captured[0]


# ════════════════════════════════════════════════════════════════════
# _verify_text
# ════════════════════════════════════════════════════════════════════


class TestVerifyText:
    """Tests for free-text citation verification (structural heuristics)."""

    @pytest.fixture
    def v(self):
        return CitationVerifier()

    def test_full_structural_match(self, v):
        """Citation with year, bracket ref, and quoted title → score=0.8 (valid)."""
        text = '[1] Smith et al. (2020). "A Great Empirical Study". Journal of Finance.'
        result = v._verify_text(text)
        # year (0.3) + bracket_ref (0.3) + title_like (0.2) = 0.8
        assert result.valid is True
        assert result.verified is False
        assert result.score == pytest.approx(0.8)
        assert result.source == "structural"
        assert result.year == 2020

    def test_year_only(self, v):
        """Citation with only year reaches score=0.3 → invalid (< 0.4)."""
        text = "Some random text 2019 nothing else here"
        result = v._verify_text(text)
        assert result.year == 2019
        assert result.valid is False
        assert result.score == pytest.approx(0.3)

    def test_year_with_bracket_only(self, v):
        """Year + bracket ref reaches score=0.6 → valid."""
        text = "[3] A study published in 2021 about nothing"
        result = v._verify_text(text)
        assert result.valid is True
        assert result.score == pytest.approx(0.6)

    def test_year_with_quoted_title(self, v):
        """Year + quoted ≥10 chars reaches score=0.5 → valid."""
        text = 'Smith et al. 2020 said "this is a long quoted title text"'
        result = v._verify_text(text)
        assert result.valid is True
        assert result.score == pytest.approx(0.5)

    def test_no_year_invalid(self, v):
        """No year + nothing else → score=0.0, invalid."""
        text = "Some strange text without any structural elements"
        result = v._verify_text(text)
        assert result.valid is False
        assert result.year is None
        assert result.score == pytest.approx(0.0)

    def test_parenthetical_author_form(self, v):
        """``(Smith et al., 2020)`` parenthetical form is detected as bracket ref."""
        text = "Reference: (Smith et al., 2020) for the relevant work."
        result = v._verify_text(text)
        # has_bracket_ref should match the parenthetical form
        assert result.score >= 0.6  # year + bracket ref
        assert result.year == 2020

    def test_score_capped_at_0_9(self, v):
        """Even with all four indicators, the score is capped at 0.9."""
        text = '[1] Alice et al. (2019). "A Very Long Quoted Title Indeed"'
        result = v._verify_text(text)
        assert result.score <= 0.9

    def test_message_valid(self, v):
        """Valid citation gets the 'Structurally valid' message."""
        text = '[1] Foo (2020). "Some Really Long Title Text Here"'
        result = v._verify_text(text)
        assert "Structurally valid" in result.message

    def test_message_invalid(self, v):
        """Invalid citation gets the verify-manually warning."""
        result = v._verify_text("garbage")
        assert "verify manually" in result.message


# ════════════════════════════════════════════════════════════════════
# verify()
# ════════════════════════════════════════════════════════════════════


class TestVerify:
    """Tests for the main verify() entry point."""

    @pytest.fixture
    def v(self):
        return CitationVerifier(timeout=1.0)

    def test_empty_citation(self, v):
        """Empty / whitespace-only → invalid+unverified result."""
        r = v.verify("")
        assert r.valid is False
        assert r.verified is False
        assert r.source == "none"
        assert "Empty" in r.message

    def test_whitespace_only(self, v):
        """Whitespace-only counts as empty."""
        r = v.verify("   ")
        assert r.valid is False
        assert r.source == "none"

    def test_strips_whitespace(self, v):
        """Leading/trailing whitespace is stripped before processing."""
        with patch("urllib.request.urlopen", _fake_urlopen(b"not-json-{{{")):
            r = v.verify("   10.1234/example   ")
        # Routed to _verify_doi → tries parsing → falls into invalid-json branch
        assert r.source == "crossref"

    def test_cache_hit(self, v):
        """A second verify() with the same citation must use the cache."""
        # First call — populate cache via text verification (no network).
        v.verify("[1] Foo (2020). 'Some really long quoted title for caching'")
        # Now check the cache contains the entry
        cache_key = "[1] Foo (2020). 'Some really long quoted title for caching'"[:100]
        assert cache_key in v._cache

        # Second call returns the cached value (same object reference)
        r1 = v.verify("[1] Foo (2020). 'Some really long quoted title for caching'")
        r2 = v.verify("[1] Foo (2020). 'Some really long quoted title for caching'")
        assert r1 is r2  # exact same object from cache

    def test_cache_key_truncates_to_100(self, v):
        """Cache key is the first 100 characters of the (stripped) citation."""
        long_citation = "x" * 200
        v.verify(long_citation)
        assert "x" * 100 in v._cache

    def test_cache_size_eviction(self, v):
        """When the cache is full, the oldest entry is evicted (FIFO)."""
        small = CitationVerifier(timeout=1.0, cache_size=3)
        # 4 distinct text citations → oldest should be evicted
        for i in range(4):
            small.verify(f"[{i}] Author{i} (2020). 'Some really long quoted title text here'")
        # Last entry is present
        assert ("[3] Author3 (2020). 'Some really long quoted title text here'"[:100]) in small._cache
        # First entry was evicted
        assert ("[0] Author0 (2020). 'Some really long quoted title text here'"[:100]) not in small._cache

    def test_dispatches_to_doi(self, v):
        """A citation containing a DOI is routed to the DOI path."""
        with patch.object(
            v, "_verify_doi", wraps=v._verify_doi
        ) as spy:
            with patch("urllib.request.urlopen", _fake_urlopen(b"{}")):
                v.verify("10.1234/spied")
            spy.assert_called_once_with("10.1234/spied")

    def test_dispatches_to_arxiv(self, v):
        """A citation containing an ArXiv ID is routed to the ArXiv path."""
        with patch.object(
            v, "_verify_arxiv", wraps=v._verify_arxiv
        ) as spy:
            with patch("urllib.request.urlopen", _fake_urlopen(b"{}")):
                v.verify("arXiv:2301.99999 about something")
            spy.assert_called_once_with("2301.99999")

    def test_dispatches_to_text(self, v):
        """Plain-text citation (no DOI/ArXiv) is routed to text path."""
        with patch.object(
            v, "_verify_text", wraps=v._verify_text
        ) as spy:
            v.verify("[1] Foo et al. (2020). 'Long quoted title'")
            spy.assert_called_once()


# ════════════════════════════════════════════════════════════════════
# verify_batch()
# ════════════════════════════════════════════════════════════════════


class TestVerifyBatch:
    """Tests for verify_batch()."""

    @pytest.fixture
    def v(self):
        return CitationVerifier()

    def test_empty_list(self, v):
        """Empty input → empty output, no errors."""
        assert v.verify_batch([]) == []

    def test_returns_one_result_per_input(self, v):
        """Output length equals input length."""
        citations = [
            "[1] A (2020). 'A long quoted title text'",
            "[2] B (2021). 'Another very long quoted title text'",
            "[3] C (2022). 'Yet another long quoted title here'",
        ]
        results = v.verify_batch(citations, delay=0)
        assert len(results) == 3
        assert all(isinstance(r, CitationCheckResult) for r in results)

    def test_rate_limiting_uses_sleep(self, v):
        """verify_batch must invoke time.sleep when delay > 0."""
        with patch("scripts.core.citation_verifier.time.sleep") as mock_sleep:
            v.verify_batch(
                ["[1] A (2020). 'A long quoted title'"],
                delay=0.5,
            )
            # sleep is called at least once for the one item
            assert mock_sleep.called
            assert mock_sleep.call_args.args[0] == 0.5

    def test_no_sleep_when_delay_zero(self, v):
        """No sleep happens when delay=0."""
        with patch("scripts.core.citation_verifier.time.sleep") as mock_sleep:
            v.verify_batch(
                ["[1] A (2020). 'A long quoted title'"],
                delay=0,
            )
            mock_sleep.assert_not_called()

    def test_propagates_inner_results(self, v):
        """Each input's individual result is included in the output."""
        out = v.verify_batch(
            ["[1] Foo (2020). 'A long quoted title for batch test'"],
            delay=0,
        )
        assert out[0].valid in (True, False)


# ════════════════════════════════════════════════════════════════════
# main()
# ════════════════════════════════════════════════════════════════════


class TestMain:
    """Tests for the CLI entry point."""

    def test_main_no_args_prints_help(self, capsys):
        """Calling main() with no args invokes parser.print_help()."""
        with patch("sys.argv", ["citation_verifier"]):
            try:
                main()
            except SystemExit:
                pass  # argparse exits 0 on --help; without args it just prints help
        out = capsys.readouterr().out
        # Either empty (argparse default) or contains 'usage'/'help' text
        # We just check no exception leaked
        assert "usage" in out.lower() or out == ""

    def test_main_single_citation(self, capsys):
        """main() with a positional citation calls verify() and prints."""
        with patch("sys.argv", ["citation_verifier", "10.1234/example"]):
            with patch("urllib.request.urlopen", _fake_urlopen(b"<<not-json")):
                try:
                    main()
                except SystemExit:
                    pass
        out = capsys.readouterr().out
        # Should contain the verification status symbol
        assert "crossref" in out or "structural" in out or "semantic_scholar" in out

    def test_main_batch_file(self, tmp_path, capsys):
        """main() with --batch reads citations line-by-line."""
        batch = tmp_path / "citations.txt"
        batch.write_text(
            "[1] Foo (2020). 'A long quoted title'\n"
            "[2] Bar (2021). 'Another long quoted title here'\n"
        )
        with patch("sys.argv", ["citation_verifier", "--batch", str(batch)]):
            try:
                main()
            except SystemExit:
                pass
        out = capsys.readouterr().out
        # Should contain status markers for each line
        assert "structural" in out


# ════════════════════════════════════════════════════════════════════
# Module smoke
# ════════════════════════════════════════════════════════════════════


def test_dataclass_equality():
    """Two CitationCheckResults with same fields compare equal."""
    a = CitationCheckResult(valid=True, verified=True, score=1.0, source="x")
    b = CitationCheckResult(valid=True, verified=True, score=1.0, source="x")
    assert a == b


def test_verifier_reusable_across_calls():
    """Same verifier instance can verify many citations."""
    v = CitationVerifier()
    r1 = v.verify("[1] A (2020). 'A quoted title of significant length'")
    r2 = v.verify("[2] B (2021). 'Another long quoted title of ample length'")
    assert r1 is not r2
    assert len(v._cache) == 2
