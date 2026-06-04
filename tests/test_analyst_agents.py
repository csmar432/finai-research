"""Analyst Agents 单元测试（无需真实API）"""
import pytest
from scripts.core.analyst_agents import (
    AnalystType,
    AnalystConfig,
    EnhancedFinancialAnalyst,
    EnhancedValuationAnalyst,
    EnhancedEarningsQualityAnalyst,
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
