"""
tests/test_demo_research_report.py
=================================
Tests for the end-to-end A-share research report demo.

Covers:
- Mock data has correct _mock flag
- Mock data contains all required fields
- Financial analysis returns expected structure
- Valuation returns all required fields
- DCF value is positive
- Recommendation logic is correct
- Output directory is created
- Event-driven pipeline trigger integration
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

# Import the module under test
from scripts.demo_research_report import (
    _get_mock_stock_data,
    DEMO_CONFIG,
    analyze_financials,
    run_valuation,
    assess_risk,
    generate_report,
    run_demo_pipeline,
)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_data():
    """Standard mock data fixture."""
    return _get_mock_stock_data("000001.SZ")


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory for report tests."""
    output = tmp_path / "reports"
    output.mkdir()
    return output


# ══════════════════════════════════════════════════════════════════════════════
# MOCK DATA TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestMockData:
    """Tests for the mock data generator."""

    def test_mock_data_has_mock_flag(self):
        """Verify _get_mock_stock_data returns _mock=True."""
        data = _get_mock_stock_data("000001.SZ")
        assert data.get("_mock") is True, (
            f"Expected _mock=True, got {data.get('_mock')}"
        )

    def test_mock_data_has_mock_reason(self):
        """Verify _get_mock_stock_data includes a mock reason."""
        data = _get_mock_stock_data("000001.SZ")
        assert "_mock_reason" in data, "Missing _mock_reason field"
        assert len(data["_mock_reason"]) > 0, "_mock_reason should not be empty"

    def test_mock_data_contains_required_fields(self, mock_data):
        """Verify financial_summary has all expected keys."""
        required_keys = [
            "revenue_2025",
            "revenue_growth_yoy",
            "net_profit_2025",
            "profit_growth_yoy",
            "roe",
            "eps",
            "bps",
            "pe_ttm",
            "pb",
        ]
        financial_summary = mock_data.get("financial_summary", {})
        missing = [k for k in required_keys if k not in financial_summary]
        assert not missing, f"Missing financial_summary keys: {missing}"

    def test_mock_data_key_ratios_fields(self, mock_data):
        """Verify key_ratios has all required banking-specific fields."""
        required_keys = ["npl_ratio", "capital_adequacy", "tier1_ratio", "liquidity_coverage"]
        key_ratios = mock_data.get("key_ratios", {})
        missing = [k for k in required_keys if k not in key_ratios]
        assert not missing, f"Missing key_ratios keys: {missing}"

    def test_mock_data_ts_code_preserved(self):
        """Verify the ts_code is preserved in mock data."""
        ts_code = "600519.SH"
        data = _get_mock_stock_data(ts_code)
        assert data["ts_code"] == ts_code, f"Expected {ts_code}, got {data['ts_code']}"

    def test_mock_data_price_data_structure(self, mock_data):
        """Verify price_data has correct structure."""
        price_data = mock_data.get("price_data", {})
        assert len(price_data) >= 1, "price_data should have at least 1 entry"
        for date, values in price_data.items():
            assert "close" in values, f"Missing 'close' for date {date}"
            assert "volume" in values, f"Missing 'volume' for date {date}"
            assert isinstance(values["close"], (int, float)), "close should be numeric"
            assert isinstance(values["volume"], int), "volume should be int"

    def test_mock_data_npl_ratio_realistic(self, mock_data):
        """Verify NPL ratio is in realistic range for Chinese banks."""
        npl = mock_data.get("key_ratios", {}).get("npl_ratio", 0)
        assert 0.5 <= npl <= 3.0, f"NPL ratio {npl}% outside realistic range [0.5, 3.0]"

    def test_mock_data_capital_adequacy_realistic(self, mock_data):
        """Verify capital adequacy ratio meets Chinese regulatory requirements."""
        ca = mock_data.get("key_ratios", {}).get("capital_adequacy", 0)
        assert ca >= 10.5, f"Capital adequacy {ca}% below Chinese regulatory minimum 10.5%"


# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL ANALYSIS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestFinancialAnalysis:
    """Tests for the financial analysis function."""

    def test_analyze_financials_returns_dict(self):
        """Verify analyze_financials returns a dictionary."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    def test_analyze_financials_contains_expected_keys(self):
        """Verify analysis output has all expected top-level keys."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        required = [
            "revenue_analysis",
            "profitability",
            "dupont_analysis",
            "asset_quality",
            "capital",
            "key_findings",
        ]
        missing = [k for k in required if k not in result]
        assert not missing, f"Missing analysis keys: {missing}"

    def test_analyze_financials_revenue_trend_positive(self):
        """Verify revenue trend label for positive growth."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        assert result["revenue_analysis"]["trend"] == "稳定增长"

    def test_analyze_financials_roe_above_industry_avg(self):
        """Verify ROE is above industry average in mock data."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        roe = result["profitability"]["roe"]
        industry_avg = result["profitability"]["industry_avg_roe"]
        assert roe > industry_avg, f"ROE {roe} should exceed industry avg {industry_avg}"

    def test_analyze_financials_key_findings_not_empty(self):
        """Verify key_findings list is non-empty."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        findings = result.get("key_findings", [])
        assert len(findings) > 0, "key_findings should not be empty"

    def test_analyze_financials_dupont_decomposition_contains_roe(self):
        """Verify Dupont decomposition text mentions ROE."""
        data = _get_mock_stock_data("000001.SZ")
        result = analyze_financials(data)
        dupont_text = result["dupont_analysis"].get("roe_decomposition", "")
        assert "ROE" in dupont_text or "roe" in dupont_text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# VALUATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestValuation:
    """Tests for the DCF + PB valuation function."""

    def test_run_valuation_returns_dict(self):
        """Verify run_valuation returns a dictionary."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    def test_run_valuation_returns_all_fields(self):
        """Verify valuation output has all required fields."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        required = [
            "dcf_value",
            "dcf_wacc",
            "dcf_terminal_growth",
            "comp_low",
            "comp_high",
            "comp_mid",
            "current_price",
            "upside_dcf",
            "upside_comp",
            "recommendation",
        ]
        missing = [k for k in required if k not in result]
        assert not missing, f"Missing valuation fields: {missing}"

    def test_dcf_value_positive(self):
        """Verify DCF value is positive."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        assert result["dcf_value"] > 0, f"DCF value must be positive, got {result['dcf_value']}"

    def test_dcf_value_reasonable_range(self):
        """Verify DCF value is within a reasonable range (5–50 CNY for a bank)."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        dcf = result["dcf_value"]
        assert 5 <= dcf <= 50, f"DCF value {dcf} outside reasonable range [5, 50]"

    def test_comp_low_less_than_high(self):
        """Verify PB comparable low < high."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        assert result["comp_low"] < result["comp_high"], (
            f"comp_low ({result['comp_low']}) should be < comp_high ({result['comp_high']})"
        )

    def test_comp_mid_is_average(self):
        """Verify comp_mid is the midpoint of comp_low and comp_high."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        expected_mid = (result["comp_low"] + result["comp_high"]) / 2
        assert abs(result["comp_mid"] - expected_mid) < 0.01, (
            f"comp_mid {result['comp_mid']} should equal "
            f"(comp_low + comp_high)/2 = {expected_mid}"
        )

    def test_upside_dcf_calculation(self):
        """Verify upside_dcf is calculated correctly."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        expected = (result["dcf_value"] - result["current_price"]) / result["current_price"] * 100
        assert abs(result["upside_dcf"] - expected) < 0.1, (
            f"upside_dcf {result['upside_dcf']} != expected {expected:.1f}"
        )

    def test_recommendation_logic(self):
        """Verify recommendation matches valuation thresholds."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        price = result["current_price"]
        dcf = result["dcf_value"]
        rec = result["recommendation"]

        if dcf > price * 1.15:
            assert rec == "买入", f"Expected '买入' when DCF/price={dcf/price:.2f}, got '{rec}'"
        elif dcf > price * 0.9:
            assert rec == "持有", f"Expected '持有' when DCF/price={dcf/price:.2f}, got '{rec}'"
        else:
            assert rec == "减持", f"Expected '减持' when DCF/price={dcf/price:.2f}, got '{rec}'"

    def test_recommendation_valid_values(self):
        """Verify recommendation is one of the valid values."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        valid = {"买入", "持有", "减持"}
        assert result["recommendation"] in valid, (
            f"Invalid recommendation '{result['recommendation']}'. Must be one of {valid}"
        )

    def test_dcf_wacc_in_realistic_range(self):
        """Verify WACC assumption is in realistic range for Chinese banks."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        wacc = result["dcf_wacc"]
        assert 0.07 <= wacc <= 0.15, f"WACC {wacc:.2%} outside realistic range [7%, 15%]"

    def test_dcf_terminal_growth_less_than_wacc(self):
        """Verify terminal growth rate < WACC (standard DCF assumption)."""
        data = _get_mock_stock_data("000001.SZ")
        result = run_valuation(data)
        assert result["dcf_terminal_growth"] < result["dcf_wacc"], (
            f"Terminal growth ({result['dcf_terminal_growth']}) must be < "
            f"WACC ({result['dcf_wacc']})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# RISK ASSESSMENT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskAssessment:
    """Tests for the risk assessment function."""

    def test_assess_risk_returns_dict(self):
        """Verify assess_risk returns a dictionary."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        result = assess_risk(data, analysis)
        assert isinstance(result, dict)

    def test_assess_risk_has_risk_categories(self):
        """Verify risk categories are present."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        result = assess_risk(data, analysis)
        for key in ["macro_risks", "company_risks", "market_risks"]:
            assert key in result, f"Missing risk category: {key}"

    def test_overall_risk_rating_present(self):
        """Verify overall risk rating is present."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        result = assess_risk(data, analysis)
        assert "overall_risk_rating" in result
        assert len(result["overall_risk_rating"]) > 0

    def test_risk_summary_not_empty(self):
        """Verify risk summary text is not empty."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        result = assess_risk(data, analysis)
        assert len(result.get("risk_summary", "")) > 20, "risk_summary should be descriptive"


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestReportGeneration:
    """Tests for the report generation function."""

    def test_generate_report_creates_tex_file(self, temp_output_dir):
        """Verify generate_report creates a .tex file."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        valuation = run_valuation(data)
        risk = assess_risk(data, analysis)

        result = generate_report(
            ts_code="000001.SZ",
            company_name="平安银行",
            data=data,
            analysis=analysis,
            valuation=valuation,
            risk=risk,
            output_dir=str(temp_output_dir),
        )

        assert "tex" in result, "Result should contain 'tex' key"
        tex_path = Path(result["tex"])
        assert tex_path.exists(), f"TeX file not created: {tex_path}"

    def test_generate_report_output_contains_metadata(self, temp_output_dir):
        """Verify report output dict contains expected metadata."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        valuation = run_valuation(data)
        risk = assess_risk(data, analysis)

        result = generate_report(
            ts_code="000001.SZ",
            company_name="平安银行",
            data=data,
            analysis=analysis,
            valuation=valuation,
            risk=risk,
            output_dir=str(temp_output_dir),
        )

        for key in ["is_mock", "ts_code", "company_name", "recommendation"]:
            assert key in result, f"Missing expected output key: {key}"

    def test_generate_report_marks_mock_data(self, temp_output_dir):
        """Verify is_mock flag is set correctly in report output."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        valuation = run_valuation(data)
        risk = assess_risk(data, analysis)

        result = generate_report(
            ts_code="000001.SZ",
            company_name="平安银行",
            data=data,
            analysis=analysis,
            valuation=valuation,
            risk=risk,
            output_dir=str(temp_output_dir),
        )

        assert result["is_mock"] is True, "is_mock should be True for mock data"

    def test_tex_file_contains_company_name(self, temp_output_dir):
        """Verify the generated TeX file contains the company name."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        valuation = run_valuation(data)
        risk = assess_risk(data, analysis)

        result = generate_report(
            ts_code="000001.SZ",
            company_name="平安银行",
            data=data,
            analysis=analysis,
            valuation=valuation,
            risk=risk,
            output_dir=str(temp_output_dir),
        )

        tex_content = Path(result["tex"]).read_text(encoding="utf-8")
        assert "平安银行" in tex_content, "TeX should contain company name"

    def test_tex_file_contains_valuation_numbers(self, temp_output_dir):
        """Verify the generated TeX file contains valuation figures."""
        data = _get_mock_stock_data("000001.SZ")
        analysis = analyze_financials(data)
        valuation = run_valuation(data)
        risk = assess_risk(data, analysis)

        result = generate_report(
            ts_code="000001.SZ",
            company_name="平安银行",
            data=data,
            analysis=analysis,
            valuation=valuation,
            risk=risk,
            output_dir=str(temp_output_dir),
        )

        tex_content = Path(result["tex"]).read_text(encoding="utf-8")
        # Check for key financial figures
        assert str(valuation["dcf_value"])[:4] in tex_content or \
               f"{valuation['dcf_value']:.2f}" in tex_content, \
               "TeX should contain DCF value"


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """End-to-end pipeline integration tests."""

    def test_run_demo_pipeline_returns_completed_status(self, temp_output_dir):
        """Verify run_demo_pipeline completes with status='completed'."""
        result = run_demo_pipeline(
            ts_code="000001.SZ",
            output_dir=str(temp_output_dir),
        )
        assert result["status"] == "completed", f"Pipeline should complete, got {result['status']}"

    def test_run_demo_pipeline_has_all_sections(self, temp_output_dir):
        """Verify pipeline output has all required sections."""
        result = run_demo_pipeline(
            ts_code="000001.SZ",
            output_dir=str(temp_output_dir),
        )
        for key in ["analysis", "valuation", "risk", "summary", "outputs"]:
            assert key in result, f"Pipeline result missing key: {key}"

    def test_run_demo_pipeline_creates_tex(self, temp_output_dir):
        """Verify pipeline creates a .tex file in output directory."""
        result = run_demo_pipeline(
            ts_code="000001.SZ",
            output_dir=str(temp_output_dir),
        )
        assert "tex" in result["outputs"], "Pipeline should produce .tex file"
        assert Path(result["outputs"]["tex"]).exists(), "TeX file should exist"

    def test_output_dir_creation(self, tmp_path):
        """Verify output directory is created even if it doesn't exist."""
        non_existent = tmp_path / "new_output_dir"
        assert not non_existent.exists(), "Precondition: dir should not exist"

        result = run_demo_pipeline(
            ts_code="000001.SZ",
            output_dir=str(non_existent),
        )
        assert non_existent.exists(), "Output directory should be created"
        assert result["status"] == "completed"

    def test_trigger_research_pipeline_from_event(self, temp_output_dir):
        """Test event-driven pipeline trigger with custom stock code."""
        # Simulate an event trigger (e.g., from a dashboard or webhook)
        event_payload = {
            "event": "stock_research_request",
            "ts_code": "600519.SH",
            "company_name": "贵州茅台",
            "requested_by": "test_user",
        }

        result = run_demo_pipeline(
            ts_code=event_payload["ts_code"],
            output_dir=str(temp_output_dir),
        )

        assert result["status"] == "completed"
        assert result["stock"] == "600519.SH"
        assert "tex" in result["outputs"]

    def test_pipeline_handles_mock_data_flag_propagation(self, temp_output_dir):
        """Verify _mock flag is propagated through the pipeline to outputs."""
        result = run_demo_pipeline(
            ts_code="000001.SZ",
            output_dir=str(temp_output_dir),
        )
        # The data flag should flow through to the report output
        assert result["outputs"].get("is_mock") is True, (
            "is_mock flag should propagate from data to report output"
        )


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestDemoConfig:
    """Tests for DEMO_CONFIG constant."""

    def test_demo_config_is_dict(self):
        """Verify DEMO_CONFIG is a dictionary."""
        assert isinstance(DEMO_CONFIG, dict)

    def test_demo_config_has_required_keys(self):
        """Verify DEMO_CONFIG has all required configuration keys."""
        required = ["stock", "company_name", "industry", "report_date", "analyst", "methodology"]
        missing = [k for k in required if k not in DEMO_CONFIG]
        assert not missing, f"Missing DEMO_CONFIG keys: {missing}"

    def test_demo_config_stock_format(self):
        """Verify default stock code is in valid Tushare format."""
        stock = DEMO_CONFIG["stock"]
        assert "." in stock, "Stock code should contain '.' (e.g., 000001.SZ)"
        assert stock.count(".") == 1, "Stock code should have exactly one '.'"
        parts = stock.split(".")
        assert len(parts[0]) == 6, "Stock code prefix should be 6 digits"
        assert parts[1] in {"SZ", "SH"}, "Exchange suffix should be SZ or SH"
