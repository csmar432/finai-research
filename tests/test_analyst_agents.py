"""Analyst Agents 单元测试（无需真实API）"""
import pytest
from scripts.core.analyst_agents import (
    AnalystType,
    AnalystConfig,
    EnhancedFinancialAnalyst,
    EnhancedValuationAnalyst,
    AnalystFactory,
)


@pytest.mark.asyncio
class TestEnhancedFinancialAnalyst:
    def setup_method(self):
        self.analyst = EnhancedFinancialAnalyst()

    async def test_dupont_analysis(self, sample_financial_data):
        result = await self.analyst.analyze_financial_health(
            ticker="000001.SZ",
            financial_data=sample_financial_data,
            industry="default",
        )
        assert "dupont" in result
        assert "profitability" in result
        assert "solvency" in result
        assert "cash_flow" in result
        assert 0 < result["dupont"]["roe"] < 100

    async def test_warnings_on_low_roe(self, sample_financial_data):
        sample_financial_data["income_statement"]["net_income"] = 10  # Very low
        result = await self.analyst.analyze_financial_health(
            ticker="000001.SZ",
            financial_data=sample_financial_data,
            industry="default",
        )
        warnings = result["warnings"]
        assert len(warnings) > 0

    async def test_industry_comparison(self, sample_financial_data):
        result = await self.analyst.analyze_financial_health(
            ticker="000001.SZ",
            financial_data=sample_financial_data,
            industry="tech",
        )
        assert "industry_comparison" in result


@pytest.mark.asyncio
class TestEnhancedValuationAnalyst:
    def setup_method(self):
        self.analyst = EnhancedValuationAnalyst()

    async def test_dcf_scenarios(self, sample_financial_data):
        result = await self.analyst.analyze_valuation(
            ticker="000001.SZ",
            financial_data=sample_financial_data,
            market_data={"current_price": 10.0},
            current_price=10.0,
        )
        assert "dcf_scenarios" in result
        assert "乐观情景" in result["dcf_scenarios"]
        assert "基准情景" in result["dcf_scenarios"]
        assert "悲观情景" in result["dcf_scenarios"]


class TestAnalystFactory:
    def test_register_and_create(self):
        config = AnalystConfig(
            analyst_type=AnalystType.VALUATION,
            name="test",
            role="test",
            focus_areas=[],
            tools=[],
        )
        agent = AnalystFactory.create(AnalystType.VALUATION, config)
        assert agent is not None

    def test_unknown_type_fallback(self):
        config = AnalystConfig(
            analyst_type=AnalystType.VALUATION,
            name="test",
            role="test",
            focus_areas=[],
            tools=[],
        )
        # Unknown type falls back to BaseAnalystAgent
        agent = AnalystFactory.create(AnalystType.RISK, config)
        assert agent is not None


class TestAnalystTypes:
    """Tests for AnalystType enum and AnalystConfig dataclass."""

    def test_analyst_type_values(self):
        for t in AnalystType:
            assert isinstance(t.value, str)
            assert len(t.value) > 0

    def test_analyst_type_count(self):
        assert len(AnalystType) >= 6

    def test_analyst_config_defaults(self):
        config = AnalystConfig(
            analyst_type=AnalystType.FUNDAMENTAL_FINANCIAL,
            name="test_analyst",
            role="Financial analyst",
            focus_areas=["profitability"],
            tools=["tushare"],
        )
        assert config.name == "test_analyst"
        assert config.analyst_type == AnalystType.FUNDAMENTAL_FINANCIAL


class TestAnalystFactoryExtended:
    """Additional AnalystFactory tests."""

    def test_create_all_registered_types(self):
        for analyst_type in AnalystType:
            config = AnalystConfig(
                analyst_type=analyst_type,
                name=f"test_{analyst_type.value}",
                role="Test",
                focus_areas=[],
                tools=[],
            )
            agent = AnalystFactory.create(analyst_type, config)
            assert agent is not None, f"Failed: {analyst_type}"


class TestCompositeAnalysis:
    """Tests for CompositeAnalysis dataclass."""

    def test_composite_analysis_creation(self):
        from scripts.core.analyst_agents import CompositeAnalysis
        import time
        analysis = CompositeAnalysis(
            ticker="000001.SZ",
            timestamp=time.time(),
            analyst_results={},
            consensus_view="Positive outlook",
            divergent_views=["Concern about leverage"],
            confidence=0.75,
            total_latency_ms=500.0,
        )
        assert analysis.ticker == "000001.SZ"
        assert analysis.confidence == 0.75

    def test_composite_analysis_to_dict(self):
        from scripts.core.analyst_agents import CompositeAnalysis, AnalystResult, AnalystType
        import time
        ca = CompositeAnalysis(
            ticker="600000.SH",
            timestamp=time.time(),
            analyst_results={
                AnalystType.FUNDAMENTAL_FINANCIAL: AnalystResult(
                    analyst_type=AnalystType.FUNDAMENTAL_FINANCIAL,
                    status="success",
                    findings={},
                    confidence=0.8,
                    key_points=["Strong ROE"],
                    warnings=[],
                )
            },
            consensus_view="Hold",
            divergent_views=[],
            confidence=0.60,
            total_latency_ms=300.0,
        )
        d = ca.to_dict()
        assert isinstance(d, dict)
        assert d["ticker"] == "600000.SH"
        assert "analyst_results" in d


class TestDupontDecomposition:
    """Tests for DupontDecomposition dataclass."""

    def test_dupont_decomposition_fields(self):
        from scripts.core.analyst_agents import DupontDecomposition
        dd = DupontDecomposition(
            company="TestCorp",
            year=2023,
            roe=0.12,
            net_margin=0.08,
            asset_turnover=1.2,
            equity_multiplier=1.5,
            roa=0.08,
            comparison={},
        )
        assert dd.company == "TestCorp"
        assert dd.roe == 0.12


class TestAccrualsAnalysis:
    """Tests for AccrualsAnalysis dataclass."""

    def test_accruals_analysis_creation(self):
        from scripts.core.analyst_agents import AccrualsAnalysis
        acc = AccrualsAnalysis(
            year=2023,
            total_accruals=0.05,
            abnormal_accruals=0.02,
            discretionary_accruals=0.01,
            is_suspicious=False,
        )
        assert acc.year == 2023
        assert acc.total_accruals == 0.05
        assert acc.is_suspicious is False
