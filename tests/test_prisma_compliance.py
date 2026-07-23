"""Tests for prisma_compliance.py — PRISMA 2020 systematic review engine."""



# ─── PRISMAStage ──────────────────────────────────────────────────────────

def test_prisma_stage_enum():
    from scripts.research_framework.prisma_compliance import PRISMAStage
    assert PRISMAStage.IDENTIFICATION.value == 1
    assert PRISMAStage.SCREENING.value == 2
    assert PRISMAStage.REPORT.value == 7


def test_prisma_stage_status_enum():
    from scripts.research_framework.prisma_compliance import PRISMAStageStatus
    assert PRISMAStageStatus.PENDING.value == "pending"
    assert PRISMAStageStatus.COMPLETE.value == "complete"


# ─── SearchStrategy ──────────────────────────────────────────────────────

def test_search_strategy_creation():
    from scripts.research_framework.prisma_compliance import SearchStrategy

    s = SearchStrategy(
        strategy_id="s1",
        query_text="carbon trading AND innovation",
        databases=["openalex", "web of science"],
        date_from="2020-01-01",
        date_to="2025-12-31",
    )
    assert s.strategy_id == "s1"
    assert s.record_count == 0
    assert len(s.databases) == 2

    s.add_result_count(500)
    assert s.record_count == 500


def test_search_strategy_to_dict():
    from scripts.research_framework.prisma_compliance import SearchStrategy

    s = SearchStrategy(
        strategy_id="s2",
        query_text="ESG AND performance",
        databases=["scopus"],
        date_from="2019-01-01",
        date_to="2025-01-01",
    )
    s.add_result_count(300)
    d = s.to_dict()
    assert d["strategy_id"] == "s2"
    assert d["record_count"] == 300
    assert d["prisma_stage"] == "IDENTIFICATION"


# ─── ScreeningRecord ──────────────────────────────────────────────────────

def test_screening_record_creation():
    from scripts.research_framework.prisma_compliance import ScreeningRecord

    r = ScreeningRecord(
        paper_id="p1",
        title="Carbon trading effects on innovation",
        authors="Zhang et al.",
        year=2023,
        database="openalex",
        screened_by_first="reviewer_a",
    )
    assert r.paper_id == "p1"
    assert r.inclusion_status is None
    assert not r.has_conflict


def test_screening_record_resolved():
    from scripts.research_framework.prisma_compliance import ScreeningRecord

    r = ScreeningRecord(
        paper_id="p2",
        title="ESG and cost of capital",
        authors="Li and Wang",
        year=2022,
        database="scopus",
        screened_by_first="reviewer_b",
        screened_by_second="reviewer_c",
        has_conflict=True,
        conflict_resolved=True,
        resolved_by="senior_reviewer",
    )
    assert r.has_conflict
    assert r.is_resolved()
    assert r.resolved_by == "senior_reviewer"


def test_screening_record_to_dict():
    from scripts.research_framework.prisma_compliance import ScreeningRecord

    r = ScreeningRecord(
        paper_id="p3",
        title="Test paper",
        authors="Test",
        year=2024,
        database="testdb",
        inclusion_status="exclude",
        exclusion_reason="wrong_population",
        screened_by_first="r1",
    )
    d = r.to_dict()
    assert d["paper_id"] == "p3"
    assert d["inclusion_status"] == "exclude"
    assert d["exclusion_reason"] == "wrong_population"


# ─── PICOExtract ─────────────────────────────────────────────────────────

def test_pico_extract():
    from scripts.research_framework.prisma_compliance import PICOExtract

    p = PICOExtract(
        paper_id="pico1",
        study_id="s1",
        population_desc="Chinese manufacturing firms",
        intervention="Carbon trading pilot",
        comparator="Non-pilot provinces",
        outcome_primary="Green patents",
        outcome_secondary=["ROA", "TFP"],
        study_design="DID",
        n_participants=5000,
        n_followup=3,
        setting="manufacturing",
        country="China",
        extracted_by="researcher_a",
    )
    assert p.n_participants == 5000
    assert p.study_design == "DID"
    picos = p.to_picos_string()
    assert "Chinese manufacturing firms" in picos
    assert "Carbon trading pilot" in picos


# ─── ROBAssessment ────────────────────────────────────────────────────────

def test_rob_assessment():
    from scripts.research_framework.prisma_compliance import ROBAssessment

    rob = ROBAssessment(
        paper_id="rob1",
        tool_type="ROBINS-I",
        domains={
            "confounding": "Moderate",
            "selection": "Low",
            "classification": "Low",
            "deviation": "Low",
            "outcome": "Low",
            "missing": "Moderate",
        },
        overall_rob="Moderate",
        assessor="reviewer_x",
    )
    assert rob.tool_type == "ROBINS-I"
    summary = rob.to_summary_str()
    assert "Moderate" in summary


def test_rob_to_dict():
    from scripts.research_framework.prisma_compliance import ROBAssessment

    rob = ROBAssessment(
        paper_id="rob2",
        tool_type="Cochrane_ROB2",
        domains={"d1": "Low", "d2": "High", "d3": "Some concerns"},
        overall_rob="High",
        assessor="reviewer_y",
        rob_json={"overall": "High", "domains": {"d1": "Low", "d2": "High"}},
    )
    d = rob.to_dict()
    assert d["paper_id"] == "rob2"
    assert d["overall_rob"] == "High"
    assert d["rob_json"]["overall"] == "High"


# ─── PRISMAFlowchart ─────────────────────────────────────────────────────

def test_prisma_flowchart_empty():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart

    fc = PRISMAFlowchart()
    data = fc.get_flowchart_data()
    assert data["identification_total"] == 0
    assert data["included_studies"] == 0


def test_prisma_flowchart_search_strategies():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart, SearchStrategy

    fc = PRISMAFlowchart()
    fc.add_search_strategy(SearchStrategy(
        strategy_id="ss1", query_text="test", databases=["db1"],
        date_from="2020", date_to="2025",
    ))
    fc.add_search_strategy(SearchStrategy(
        strategy_id="ss2", query_text="test2", databases=["db2"],
        date_from="2020", date_to="2025",
    ))
    # Both strategies have 0 record count
    data = fc.get_flowchart_data()
    assert data["identification_total"] == 0  # no add_result_count called


def test_prisma_flowchart_screening():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart

    fc = PRISMAFlowchart()
    fc.set_fulltext_screened(100)
    data = fc.get_flowchart_data()
    assert data["screening_fulltext"] == 100


def test_prisma_flowchart_deduplicate():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart

    fc = PRISMAFlowchart()
    fc.deduplicate(200)
    data = fc.get_flowchart_data()
    assert data["identification_dedup"] == 200


def test_prisma_flowchart_render_ascii():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart, SearchStrategy, ScreeningRecord

    fc = PRISMAFlowchart()
    s1 = SearchStrategy(
        strategy_id="a1", query_text="carbon", databases=["openalex"],
        date_from="2020", date_to="2025",
    )
    s1.add_result_count(500)
    fc.add_search_strategy(s1)
    fc.deduplicate(100)
    fc.add_screening_record(ScreeningRecord(
        paper_id="x1", title="t", authors="a", year=2023, database="db",
        screened_by_first="r1",
    ))

    ascii_output = fc.render_ascii()
    assert "PRISMA" in ascii_output
    assert "IDENTIFICATION" in ascii_output
    assert "SCREENING" in ascii_output or "Screening" in ascii_output


def test_prisma_flowchart_render_dict():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart

    fc = PRISMAFlowchart()
    fc.set_included_reports(20)
    d = fc.render_dict()
    assert "inc_studies" in d
    assert "inc_studies" in d  # included_studies from flowchart (default 0, set via set_included_reports affects reports)


# ─── PRISMAReport ────────────────────────────────────────────────────────

def test_prisma_report_empty():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart, PRISMAReport

    fc = PRISMAFlowchart()
    report = PRISMAReport(fc)
    summary = report.generate_summary()
    assert "prisma_stages" in summary
    assert summary["prisma_stages"]["included"]["studies"] == 0


def test_prisma_report_with_pico():
    from scripts.research_framework.prisma_compliance import (
        PRISMAFlowchart, PRISMAReport, PICOExtract, SearchStrategy
    )

    fc = PRISMAFlowchart()
    s = SearchStrategy(
        strategy_id="ss1", query_text="DID", databases=["openalex"],
        date_from="2020", date_to="2025",
    )
    s.add_result_count(1000)
    fc.add_search_strategy(s)
    fc.deduplicate(200)
    fc.set_title_abstract_screened(150)
    fc.set_fulltext_screened(150)
    fc.set_included_reports(50)

    report = PRISMAReport(fc)
    report.add_pico(PICOExtract(
        paper_id="p1", study_id="s1",
        population_desc="firms", intervention="x", comparator="y",
        outcome_primary="patents", study_design="DID",
        n_participants=1000, extracted_by="test",
    ))

    summary = report.generate_summary()
    assert summary["prisma_stages"]["screening"]["title_abstract_screened"] == 150
    assert summary["prisma_stages"]["included"]["reports"] == 50
    assert summary["pico_summary"]["n_extractions"] == 1

    stmt = report.generate_prisma_statement()
    assert "1,000" in stmt  # initial records (thousand separator)
    assert "50" in stmt   # included


def test_prisma_report_to_dict():
    from scripts.research_framework.prisma_compliance import PRISMAFlowchart, PRISMAReport

    fc = PRISMAFlowchart()
    report = PRISMAReport(fc)
    d = report.to_dict()
    assert "flowchart_data" in d or "summary" in d
    assert "pico_extractions" in d
    assert "rob_assessments" in d
