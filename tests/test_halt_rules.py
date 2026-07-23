"""HaltRulesRegistry 单元测试"""
from scripts.core.halt_rules_registry import HaltRulesRegistry


class TestHaltRulesRegistry:
    def setup_method(self):
        self.registry = HaltRulesRegistry()

    def test_load_empirical_paper_rules(self):
        rules = self.registry.load_rules("empirical_paper")
        assert len(rules) > 0
        rule_ids = [r["id"] for r in rules]
        assert "hypothesis_derivation" in rule_ids

    def test_load_finance_report_rules(self):
        rules = self.registry.load_rules("finance_report")
        assert len(rules) > 0
        rule_ids = [r["id"] for r in rules]
        assert "numerical_accuracy" in rule_ids

    def test_content_structure_hypothesis_with_theory(self):
        text = "H1: Policy affects outcomes. 基于波特竞争理论。"
        result, msg = self.registry._check_content_structure(
            text,
            {"validation": {"rules": [{"check": "hypothesis_has_theory_reference"}]}}
        )
        assert result is True

    def test_content_structure_hypothesis_without_theory(self):
        text = "H1: Policy affects outcomes."
        result, msg = self.registry._check_content_structure(
            text,
            {"validation": {"rules": [{"check": "hypothesis_has_theory_reference"}]}}
        )
        assert result is False

    def test_content_structure_group_definition(self):
        # Both grouping word AND definition word present → pass
        text = "按企业规模分组（标准：营业收入≥50亿为大型）：分析大型企业、中型企业、小型企业的差异。"
        result, msg = self.registry._check_content_structure(
            text,
            {"validation": {"rules": [{"check": "group_definition"}]}}
        )
        assert result is True

    def test_content_structure_group_without_definition(self):
        text = "按企业规模分组分析。"  # Has grouping word, no definition word
        result, msg = self.registry._check_content_structure(
            text,
            {"validation": {"rules": [{"check": "group_definition"}]}}
        )
        # Missing definition/criteria for grouping → violation → False
        assert result is False
        assert "lacks" in msg.lower()

    def test_temporal_consistency_chronological(self):
        data = {"events": [{"date": "2020"}, {"date": "2021"}, {"date": "2022"}]}
        result, msg = self.registry._check_temporal_consistency(
            data,
            {"validation": {"rules": [{"check": "chronological_order"}]}}
        )
        assert result is True

    def test_temporal_consistency_not_chronological(self):
        data = {"events": [{"date": "2022"}, {"date": "2020"}, {"date": "2021"}]}
        result, msg = self.registry._check_temporal_consistency(
            data,
            {"validation": {"rules": [{"check": "chronological_order"}]}}
        )
        assert result is False

    def test_forecast_after_history_pass(self):
        data = {"hist_end_date": "2024-12-31", "forecast_start_date": "2025-01-01"}
        result, msg = self.registry._check_temporal_consistency(
            data,
            {"validation": {"rules": [{"check": "forecast_after_history"}]}}
        )
        assert result is True

    def test_forecast_after_history_fail(self):
        data = {"hist_end_date": "2025-12-31", "forecast_start_date": "2024-01-01"}
        result, msg = self.registry._check_temporal_consistency(
            data,
            {"validation": {"rules": [{"check": "forecast_after_history"}]}}
        )
        assert result is False

    def test_math_consistency_margin(self):
        data = {"net_margin": 0.30, "gross_margin": 0.20}
        result, msg = self.registry._check_math_consistency(
            data,
            {"validation": {"rules": [{"formula": "net_margin <= gross_margin"}]}}
        )
        assert result is False

    def test_math_consistency_margin_pass(self):
        data = {"net_margin": 0.15, "gross_margin": 0.30}
        result, msg = self.registry._check_math_consistency(
            data,
            {"validation": {"rules": [{"formula": "net_margin <= gross_margin"}]}}
        )
        assert result is True

    def test_balance_sheet_identity_pass(self):
        data = {"total_assets": 1000, "total_liabilities": 400, "equity": 600}
        result, msg = self.registry._check_balance_sheet(
            data,
            {"validation": {"rules": [{"formula": "total_assets == total_liabilities + equity"}]}}
        )
        assert result is True

    def test_balance_sheet_identity_fail(self):
        data = {"total_assets": 1000, "total_liabilities": 400, "equity": 500}
        result, msg = self.registry._check_balance_sheet(
            data,
            {"validation": {"rules": [{"formula": "total_assets == total_liabilities + equity"}]}}
        )
        assert result is False
