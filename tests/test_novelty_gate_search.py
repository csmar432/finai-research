"""NoveltyGate must use real literature search (not LLM-only)."""

from __future__ import annotations

from unittest.mock import patch

from scripts.core.evolution_gate import NoveltyGate


def _paper(title: str, year: int = 2024, venue: str = "Journal of Finance", abstract: str = ""):
    return {
        "title": title,
        "year": year,
        "venue": venue,
        "abstract": abstract,
        "externalIds": {"DOI": "10.0/test"},
    }


def test_token_jaccard_overlap():
    g = NoveltyGate()
    assert g._token_jaccard("carbon trading green innovation", "carbon trading policy") > 0.2
    assert g._token_jaccard("aaa bbb", "zzz yyy") == 0.0


def test_search_hit_raises_similarity_and_records_overlap():
    g = NoveltyGate(similarity_threshold=0.3, lookback_years=5)
    close = _paper(
        "Carbon Emissions Trading and Green Innovation",
        abstract="We study carbon trading effects on green innovation using DID.",
    )
    with patch(
        "scripts.literature_download.search_semantic",
        return_value=[close],
    ), patch(
        "scripts.literature_download.search_openalex",
        return_value=[],
    ), patch.object(NoveltyGate, "_llm_heuristic_similarity", return_value=0.99):
        assessment = g._assess_idea(
            "Carbon emissions trading and corporate green innovation DID"
        )

    assert assessment["search_status"] == "ok"
    assert assessment["similarity"] > 0.2
    assert assessment["overlaps"]
    assert "Carbon" in assessment["overlaps"][0]["title"]


def test_lookback_filters_old_papers():
    g = NoveltyGate(lookback_years=3)
    old = _paper("Ancient carbon paper", year=1999)
    new = _paper("Recent carbon trading innovation", year=2024)
    filtered = g._filter_papers([old, new])
    years = {p["year"] for p in filtered}
    assert 2024 in years
    assert 1999 not in years


def test_search_unavailable_falls_back_to_llm_heuristic():
    g = NoveltyGate()
    with patch(
        "scripts.literature_download.search_semantic",
        return_value=[],
    ), patch(
        "scripts.literature_download.search_openalex",
        return_value=[],
    ), patch.object(NoveltyGate, "_llm_heuristic_similarity", return_value=0.42) as llm:
        assessment = g._assess_idea("obscure niche topic xyz")

    assert assessment["search_status"] == "unavailable"
    assert assessment["similarity"] == 0.42
    llm.assert_called_once()


def test_evaluate_includes_search_backend_and_overlaps():
    g = NoveltyGate()
    with patch.object(
        NoveltyGate,
        "_assess_idea",
        return_value={
            "similarity": 0.1,
            "search_status": "ok",
            "overlaps": [{"title": "T", "year": 2024, "venue": "JF", "doi": "", "similarity": 0.1}],
        },
    ):
        result = g.evaluate({"ideas": ["some idea"]})

    assert result.passed is True
    assert result.details["search_backend"] == "literature_download"
    assert result.details["results"][0]["overlaps"][0]["title"] == "T"


def test_check_novelty_back_compat_delegates():
    g = NoveltyGate()
    with patch.object(
        NoveltyGate,
        "_assess_idea",
        return_value={"similarity": 0.55, "search_status": "ok", "overlaps": []},
    ):
        assert g._check_novelty("idea") == 0.55


def test_normalize_paper_strips_doi_prefix():
    g = NoveltyGate()
    p = g._normalize_paper(
        {
            "title": "X",
            "year": 2023,
            "venue": "Journal of Finance",
            "doi": "https://doi.org/10.1/abc",
            "abstract": "hello",
        },
        source="openalex",
    )
    assert p["doi"] == "10.1/abc"
    assert g._is_top_journal(p["venue"]) is True


def test_top_journal_soft_boost():
    g = NoveltyGate(lookback_years=5)
    paper = _paper(
        "Trading policy study",
        year=2024,
        venue="Journal of Finance",
        abstract="trading policy firm outcomes",
    )
    with patch(
        "scripts.literature_download.search_semantic",
        return_value=[paper],
    ), patch(
        "scripts.literature_download.search_openalex",
        return_value=[],
    ):
        boosted = g._assess_idea("trading policy firm outcomes")
        paper2 = dict(paper)
        paper2["venue"] = "Obscure Local Review"
        with patch(
            "scripts.literature_download.search_semantic",
            return_value=[paper2],
        ):
            plain = g._assess_idea("trading policy firm outcomes")
    assert boosted["similarity"] >= plain["similarity"]


def test_evaluate_notes_when_all_search_unavailable():
    g = NoveltyGate()
    with patch.object(
        NoveltyGate,
        "_assess_idea",
        return_value={
            "similarity": 0.2,
            "search_status": "unavailable",
            "overlaps": [],
        },
    ):
        result = g.evaluate({"ideas": ["a", "b"]})
    assert any("文献检索不可用" in i for i in result.issues)
