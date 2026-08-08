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
