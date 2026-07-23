"""Tests for scripts/idea_data_checker.py — idea-data cross-validation.

No external services or API calls required (all MCP/URL checks are mocked).
"""



from scripts.idea_data_checker import (
    DataSourceAvailability,
    Feasibility,
    GapReason,
    IdeaDataRequirement,
    IdeaDataValidator,
    IdeaValidationResult,
    ValidationReport,
)


# ── Feasibility & GapReason enums ─────────────────────────────────────────────


class TestFeasibility:
    def test_all_values(self):
        assert Feasibility.AVAILABLE.value == "available"
        assert Feasibility.PARTIALLY_AVAILABLE.value == "partial"
        assert Feasibility.DATA_GAP.value == "data_gap"
        assert Feasibility.REQUIRES_AUTH.value == "auth_needed"


class TestGapReason:
    def test_all_values(self):
        assert GapReason.REQUIRES_COMMERCIAL_DB.value == "requires_commercial_db"
        assert GapReason.REQUIRES_INSTITUTION.value == "requires_institution"
        assert GapReason.REQUIRES_API_KEY.value == "requires_api_key"
        assert GapReason.DATA_NOT_DIGITIZED.value == "not_digitized"
        assert GapReason.NO_PUBLIC_SOURCE.value == "no_public_source"
        assert GapReason.USER_AUTHORIZATION.value == "user_authorization"


# ── IdeaDataRequirement dataclass ─────────────────────────────────────────────


class TestIdeaDataRequirement:
    def test_required_fields(self):
        req = IdeaDataRequirement(
            data_type="financial_panel",
            description="A-share financial panel",
            required_variables=["roa", "lev", "size"],
            time_frequency="yearly",
            time_range="2015-2023",
            sample_scope="A-share non-financial",
            data_sources_candidates=["CSMAR", "Wind"],
        )
        assert req.data_type == "financial_panel"
        assert "roa" in req.required_variables
        assert req.priority == 1  # default

    def test_with_priority(self):
        req = IdeaDataRequirement(
            data_type="macro_indicator",
            description="GDP data",
            required_variables=["gdp"],
            time_frequency="yearly",
            time_range="2010-2023",
            sample_scope="China",
            data_sources_candidates=["NBS", "World Bank"],
            priority=2,
        )
        assert req.priority == 2


# ── DataSourceAvailability dataclass ─────────────────────────────────────────


class TestDataSourceAvailability:
    def test_available_source(self):
        avail = DataSourceAvailability(
            data_type="financial_panel",
            feasibility=Feasibility.AVAILABLE,
            gap_reason=None,
            available_sources=["CSMAR", "Wind"],
            unavailable_sources=[],
            what_is_missing="",
            how_to_get="Download from CSMAR",
            how_to_get_url="https://csmar.com",
            how_to_get_cost="Academic license",
            can_use_synthetic=False,
        )
        assert avail.feasibility == Feasibility.AVAILABLE
        assert avail.gap_reason is None
        assert len(avail.available_sources) == 2

    def test_data_gap(self):
        avail = DataSourceAvailability(
            data_type="customs_trade",
            feasibility=Feasibility.DATA_GAP,
            gap_reason=GapReason.REQUIRES_COMMERCIAL_DB,
            available_sources=[],
            unavailable_sources=["China Customs DB"],
            what_is_missing="Customs transaction-level data",
            how_to_get="Purchase from China Customs",
            how_to_get_url="",
            how_to_get_cost="Commercial license required",
            can_use_synthetic=True,
        )
        assert avail.feasibility == Feasibility.DATA_GAP
        assert avail.gap_reason == GapReason.REQUIRES_COMMERCIAL_DB
        assert avail.can_use_synthetic is True


# ── IdeaValidationResult dataclass ─────────────────────────────────────────────


class TestIdeaValidationResult:
    def test_create_result(self):
        idea = {
            "id": "idea_001",
            "title": "关税冲击与企业创新",
            "description": "Use DID to study tariff impact on innovation",
        }
        req = IdeaDataRequirement(
            data_type="patent_data",
            description="Patent applications",
            required_variables=["patent_count", "rd_expense"],
            time_frequency="yearly",
            time_range="2015-2023",
            sample_scope="A-share exporters",
            data_sources_candidates=["CNRDS", "CSMAR"],
        )
        avail = DataSourceAvailability(
            data_type="patent_data",
            feasibility=Feasibility.AVAILABLE,
            gap_reason=None,
            available_sources=["CNRDS"],
            unavailable_sources=[],
            what_is_missing="",
            how_to_get="Access via university library",
            how_to_get_url="",
            how_to_get_cost="Free via institution",
            can_use_synthetic=False,
        )
        result = IdeaValidationResult(
            idea=idea,
            data_requirements=[req],
            availability_results=[avail],
            feasibility=Feasibility.AVAILABLE,
            feasibility_score=0.95,
            gaps=[],
            actions=[],
            recommendation="Proceed with data acquisition.",
        )
        assert result.feasibility == Feasibility.AVAILABLE
        assert result.feasibility_score == 0.95
        assert len(result.data_requirements) == 1


# ── ValidationReport dataclass ─────────────────────────────────────────────────


class TestValidationReport:
    def test_counts(self):
        report = ValidationReport(
            total_ideas=10,
            available_count=4,
            partial_count=3,
            gap_count=2,
            auth_needed_count=1,
            idea_results=[],
            feasible_ideas=[],
            partial_ideas=[],
            gap_ideas=[],
            batch_actions=[],
            user_options=[],
        )
        assert report.total_ideas == 10
        assert report.available_count == 4
        assert report.partial_count == 3
        assert report.gap_count == 2
        assert report.auth_needed_count == 1


# ── IdeaDataValidator ─────────────────────────────────────────────────────────


class TestIdeaDataValidator:
    def test_validator_initialization(self):
        ideas = [
            {
                "id": "idea_1",
                "title": "DID with tariff data",
                "keywords": ["tariff", "DID", "A-share"],
            },
            {
                "id": "idea_2",
                "title": "ESG and cost of capital",
                "keywords": ["ESG", "cost of capital"],
            },
        ]
        validator = IdeaDataValidator(ideas)
        assert len(validator.ideas) == 2
        assert validator.ideas[0]["id"] == "idea_1"

    def test_match_pattern_tariff(self):
        """Tariff keywords should match trade-related pattern."""
        ideas = [
            {
                "id": "idea_1",
                "title": "Tariff shock on exports",
                "keywords": ["关税", "tariff", "export"],
            },
        ]
        validator = IdeaDataValidator(ideas)
        patterns = validator._match_pattern(validator.ideas[0])
        assert len(patterns) > 0
        # Should match trade-related pattern
        matched_types = patterns[0].get("data_types", [])
        assert any(
            t in ["customs_trade", "tariff_exposure", "financial_panel"] for t in matched_types
        )

    def test_match_pattern_carbon(self):
        """Carbon/green innovation keywords should match environmental pattern."""
        ideas = [
            {
                "id": "idea_2",
                "title": "Carbon trading and innovation",
                "keywords": ["carbon", "patent", "green innovation"],
            },
        ]
        validator = IdeaDataValidator(ideas)
        patterns = validator._match_pattern(ideas[0])
        assert len(patterns) > 0
