"""
Deep execution tests for scripts/empirical_advisor.py

Tests dataclasses, pure helpers, class init, DiagnosticEngine,
AdjustmentStrategyGenerator, ModelSwitchDecision, and EmpiricalAdvisor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.empirical_advisor import (
    AdjustmentAction,
    AdjustmentStrategy,
    AdjustmentStrategyGenerator,
    DiagnosticEngine,
    DiagnosticResult,
    EmpiricalAdvisor,
    EvaluationResult,
    InsignificanceCause,
    ModelSwitch,
    ModelSwitchDecision,
    check_placebo,
    check_parallel_trend,
)


# ── Enums ─────────────────────────────────────────────────────────────────────

class TestInsignificanceCauseEnum:
    """Tests for InsignificanceCause enum."""

    def test_all_values_present(self):
        expected = {
            "endogeneity", "selection_bias", "heterogeneity",
            "dynamic_effect", "measurement_error", "outliers",
            "multicollinearity", "heteroskedasticity", "autocorrelation",
            "low_statistical_power", "wrong_model_type", "parallel_trend_violated",
        }
        actual = {e.value for e in InsignificanceCause}
        assert actual == expected

    def test_member_lookup(self):
        assert InsignificanceCause.ENDOGENEITY.value == "endogeneity"


class TestAdjustmentStrategyEnum:
    """Tests for AdjustmentStrategy enum."""

    def test_all_values_present(self):
        expected = {
            "level1_control_vars", "level2_data_cleaning",
            "level3_se_structure", "level4_fixed_effects", "level5_measurement",
        }
        actual = {e.value for e in AdjustmentStrategy}
        assert actual == expected


class TestModelSwitchEnum:
    """Tests for ModelSwitch enum."""

    def test_all_values_present(self):
        expected = {
            "did_to_iv", "did_to_psm_did", "ols_to_panel_fe",
            "linear_to_nonlinear", "ols_to_panel_gmm", "ols_to_rdd",
            "panel_to_fama_macbeth", "ols_to_heckman",
        }
        actual = {e.value for e in ModelSwitch}
        assert actual == expected


# ── Dataclasses ────────────────────────────────────────────────────────────────

class TestDiagnosticResult:
    """Tests for DiagnosticResult dataclass."""

    def test_construct_all_fields(self):
        dr = DiagnosticResult(
            cause=InsignificanceCause.ENDOGENEITY,
            confidence=0.85,
            evidence=["Evidence A", "Evidence B"],
            recommendation="Use IV",
            suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
            suggested_model_switch=ModelSwitch.DID_TO_IV,
        )
        assert dr.cause == InsignificanceCause.ENDOGENEITY
        assert dr.confidence == 0.85
        assert len(dr.evidence) == 2
        assert dr.suggested_model_switch == ModelSwitch.DID_TO_IV

    def test_construct_no_switch(self):
        dr = DiagnosticResult(
            cause=InsignificanceCause.MULTICOLLINEARITY,
            confidence=0.7,
            evidence=["High VIF"],
            recommendation="Drop variable",
            suggested_adjustment=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
            suggested_model_switch=None,
        )
        assert dr.suggested_model_switch is None


class TestAdjustmentAction:
    """Tests for AdjustmentAction dataclass."""

    def test_construct_all_fields(self):
        aa = AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
            action_type="adjust_controls",
            description="Add missing controls",
            specific_changes={"add": ["roa"], "remove": []},
            expected_impact="Better control",
            priority=1,
        )
        assert aa.level == AdjustmentStrategy.LEVEL_1_CONTROL_VARS
        assert aa.priority == 1
        assert aa.specific_changes["add"] == ["roa"]


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_construct_all_fields(self):
        er = EvaluationResult(
            is_significant=True,
            best_significance_level="***",
            core_variable_result={"coef": 0.05, "pval": 0.001},
            diagnostics=[],
            adjustment_plan=[],
            model_switch_recommendation=None,
            recommendation="Result significant",
            action_plan=["Run robustness checks"],
            research_note="",
            max_attempts=3,
            current_attempt=0,
            exhausted_strategies=[],
        )
        assert er.is_significant is True
        assert er.best_significance_level == "***"
        assert er.current_attempt == 0

    def test_construct_defaults(self):
        er = EvaluationResult(
            is_significant=False,
            best_significance_level="",
            core_variable_result={},
            diagnostics=[],
            adjustment_plan=[],
            model_switch_recommendation=None,
            recommendation="Not significant",
            action_plan=[],
            research_note="",
        )
        assert er.max_attempts == 3
        assert er.current_attempt == 0
        assert er.exhausted_strategies == []


# ── DiagnosticEngine ──────────────────────────────────────────────────────────

class TestDiagnosticEngine:
    """Tests for DiagnosticEngine."""

    def setup_method(self):
        self.engine = DiagnosticEngine()

    def test_causes_patterns_present(self):
        assert InsignificanceCause.ENDOGENEITY in DiagnosticEngine.CAUSE_PATTERNS
        assert InsignificanceCause.SELECTION_BIAS in DiagnosticEngine.CAUSE_PATTERNS
        assert InsignificanceCause.HETEROGENEITY in DiagnosticEngine.CAUSE_PATTERNS

    def test_diagnose_low_sample_size(self):
        results = self.engine.diagnose({}, {"n_obs": 50}, {})
        assert any(
            d.cause == InsignificanceCause.LOW_POWER and d.confidence == 0.9
            for d in results
        )

    def test_diagnose_heteroskedasticity(self):
        results = self.engine.diagnose({}, {}, {"bp_pval": 0.01})
        assert any(
            d.cause == InsignificanceCause.HETEROSKEDASTICITY and d.confidence == 0.85
            for d in results
        )

    def test_diagnose_autocorrelation_low_dw(self):
        results = self.engine.diagnose({}, {}, {"dw": 1.2})
        assert any(
            d.cause == InsignificanceCause.AUTOCORRELATION and d.confidence == 0.8
            for d in results
        )

    def test_diagnose_autocorrelation_high_dw(self):
        results = self.engine.diagnose({}, {}, {"dw": 2.8})
        assert any(
            d.cause == InsignificanceCause.AUTOCORRELATION
            for d in results
        )

    def test_diagnose_multicollinearity_vif_high(self):
        results = self.engine.diagnose({}, {}, {"vif": [1, 2, 15]})
        assert any(
            d.cause == InsignificanceCause.MULTICOLLINEARITY and d.confidence == 0.9
            for d in results
        )

    def test_diagnose_multicollinearity_vif_moderate(self):
        results = self.engine.diagnose({}, {}, {"vif": [1, 6]})
        assert any(
            d.cause == InsignificanceCause.MULTICOLLINEARITY and d.confidence == 0.7
            for d in results
        )

    def test_diagnose_extreme_values(self):
        results = self.engine.diagnose({}, {"has_extreme_values": True}, {})
        assert any(d.cause == InsignificanceCause.OUTLIERS for d in results)

    def test_diagnose_endogeneity_risk(self):
        results = self.engine.diagnose({}, {"potential_endogeneity": True}, {})
        assert any(
            d.cause == InsignificanceCause.ENDOGENEITY
            and d.suggested_model_switch == ModelSwitch.DID_TO_IV
            for d in results
        )

    def test_diagnose_selection_bias(self):
        results = self.engine.diagnose({}, {"non_random_selection": True}, {})
        assert any(
            d.cause == InsignificanceCause.SELECTION_BIAS
            and d.suggested_model_switch == ModelSwitch.DID_TO_PSM_DID
            for d in results
        )

    def test_diagnose_parallel_trend(self):
        results = self.engine.diagnose({}, {"did_setting": True}, {})
        assert any(d.cause == InsignificanceCause.PARALLEL_TREND for d in results)

    def test_diagnose_firm_heterogeneity(self):
        results = self.engine.diagnose({}, {"high_firm_heterogeneity": True}, {})
        assert any(
            d.cause == InsignificanceCause.HETEROGENEITY
            and d.suggested_model_switch == ModelSwitch.OLS_TO_PANEL_FE
            for d in results
        )

    def test_diagnose_results_sorted_by_confidence(self):
        results = self.engine.diagnose(
            {},
            {"n_obs": 50, "potential_endogeneity": True},
            {"bp_pval": 0.01, "vif": [15]},
        )
        confidences = [d.confidence for d in results]
        assert confidences == sorted(confidences, reverse=True)

    def test_diagnose_empty_context(self):
        results = self.engine.diagnose({}, {}, {})
        assert isinstance(results, list)


# ── AdjustmentStrategyGenerator ───────────────────────────────────────────────

class TestAdjustmentStrategyGenerator:
    """Tests for AdjustmentStrategyGenerator."""

    def setup_method(self):
        self.gen = AdjustmentStrategyGenerator("finance")

    def test_init_default_field(self):
        # AdjustmentStrategyGenerator() defaults to research_field="finance"
        gen = AdjustmentStrategyGenerator()
        assert gen.research_field == "finance"
        assert gen.standard_controls == AdjustmentStrategyGenerator.CONTROL_VAR_TEMPLATES["finance"]

    def test_init_finance_field(self):
        assert self.gen.standard_controls == AdjustmentStrategyGenerator.CONTROL_VAR_TEMPLATES["finance"]

    def test_control_var_templates_has_all_fields(self):
        templates = AdjustmentStrategyGenerator.CONTROL_VAR_TEMPLATES
        assert "finance" in templates
        assert "corporate" in templates
        assert "macro" in templates
        assert "default" in templates

    def test_generate_plan_empty_diagnostics(self):
        plan = self.gen.generate_plan([], [], {}, {})
        assert plan == []

    def test_generate_plan_returns_sorted_by_priority(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.LOW_POWER,
            confidence=0.9,
            evidence=[],
            recommendation="Add data",
            suggested_adjustment=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
        )
        plan = self.gen.generate_plan([diag], ["roa"], {}, {})
        assert len(plan) == 1
        assert plan[0].priority == 2

    def test_generate_plan_level1_action(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.MULTICOLLINEARITY,
            confidence=0.9,
            evidence=["High VIF"],
            recommendation="Adjust controls",
            suggested_adjustment=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
        )
        plan = self.gen.generate_plan([diag], ["roa"], {}, {})
        assert len(plan) == 1
        assert plan[0].level == AdjustmentStrategy.LEVEL_1_CONTROL_VARS

    def test_generate_plan_level2_action(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.OUTLIERS,
            confidence=0.75,
            evidence=[],
            recommendation="Winsorize",
            suggested_adjustment=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
        )
        plan = self.gen.generate_plan([diag], [], {}, {})
        assert plan[0].action_type == "winsorize_outliers"

    def test_generate_plan_level3_double_cluster(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROSKEDASTICITY,
            confidence=0.85,
            evidence=[],
            recommendation="Use cluster SE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
        )
        plan = self.gen.generate_plan(
            [diag], [], {},
            {"n_firms": 100, "n_years": 10},
        )
        assert plan[0].specific_changes["se_type"] == "double_cluster"

    def test_generate_plan_level3_firm_cluster(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROSKEDASTICITY,
            confidence=0.85,
            evidence=[],
            recommendation="Cluster",
            suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
        )
        plan = self.gen.generate_plan(
            [diag], [], {},
            {"n_firms": 60, "n_years": 5},
        )
        assert plan[0].specific_changes["se_type"] == "cluster"

    def test_generate_plan_level3_robust(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROSKEDASTICITY,
            confidence=0.85,
            evidence=[],
            recommendation="Robust",
            suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
        )
        plan = self.gen.generate_plan(
            [diag], [], {},
            {"n_firms": 20, "n_years": 3},
        )
        assert plan[0].specific_changes["se_type"] == "robust"

    def test_generate_plan_level4_add_firm_fe(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROGENEITY,
            confidence=0.7,
            evidence=[],
            recommendation="Add FE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
        )
        plan = self.gen.generate_plan(
            [diag], [], {"firm_fe": False, "year_fe": True, "industry_fe": False}, {}
        )
        assert plan[0].specific_changes["suggested_fe"]["firm_fe"] is True

    def test_generate_plan_level4_add_year_fe(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROGENEITY,
            confidence=0.7,
            evidence=[],
            recommendation="Add year FE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
        )
        plan = self.gen.generate_plan(
            [diag], [], {"firm_fe": True, "year_fe": False, "industry_fe": False}, {}
        )
        assert plan[0].specific_changes["suggested_fe"]["year_fe"] is True

    def test_generate_plan_level4_add_industry_fe(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROGENEITY,
            confidence=0.7,
            evidence=[],
            recommendation="Add industry FE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
        )
        plan = self.gen.generate_plan(
            [diag], [], {"firm_fe": True, "year_fe": True, "industry_fe": False}, {}
        )
        assert plan[0].specific_changes["suggested_fe"]["industry_fe"] is True

    def test_generate_plan_level5_finance_topic(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.MEASUREMENT_ERROR,
            confidence=0.6,
            evidence=[],
            recommendation="Change measure",
            suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
        )
        plan = self.gen.generate_plan(
            [diag], [], {}, {"topic": "融资约束"}
        )
        assert "SA_index" in plan[0].specific_changes["alternative_vars"]["dep_vars"]

    def test_generate_plan_level5_innovation_topic(self):
        gen = AdjustmentStrategyGenerator()
        diag = DiagnosticResult(
            cause=InsignificanceCause.MEASUREMENT_ERROR,
            confidence=0.6,
            evidence=[],
            recommendation="Change measure",
            suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
        )
        plan = gen.generate_plan(
            [diag], [], {}, {"topic": "创新"}
        )
        assert "rd_intensity" in plan[0].specific_changes["alternative_vars"]["dep_vars"]


# ── ModelSwitchDecision ────────────────────────────────────────────────────────

class TestModelSwitchDecision:
    """Tests for ModelSwitchDecision."""

    def setup_method(self):
        self.decision = ModelSwitchDecision()

    def test_model_suitability_has_all_models(self):
        keys = set(ModelSwitchDecision.MODEL_SUITABILITY.keys())
        assert keys == {e for e in ModelSwitch}

    def test_should_switch_all_strategies_exhausted(self):
        should, model, reason = self.decision.should_switch(
            diagnostics=[],
            exhausted_strategies=[
                s.value for s in AdjustmentStrategy
            ],
            context={},
        )
        # All exhausted → should decide best model based on context
        assert isinstance(should, bool)
        assert model is None or isinstance(model, ModelSwitch)

    def test_should_switch_high_confidence_diag(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.ENDOGENEITY,
            confidence=0.9,
            evidence=[],
            recommendation="Use IV",
            suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
            suggested_model_switch=ModelSwitch.DID_TO_IV,
        )
        should, model, reason = self.decision.should_switch(
            [diag], [], {},
        )
        assert should is True
        assert model == ModelSwitch.DID_TO_IV

    def test_should_switch_low_confidence_no_switch(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROGENEITY,
            confidence=0.5,
            evidence=[],
            recommendation="Try FE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
            suggested_model_switch=None,
        )
        should, model, reason = self.decision.should_switch([diag], [], {})
        assert should is False
        assert model is None

    def test_decide_best_panel_gmm(self):
        should, model, reason = self.decision._decide_best_model(
            [], {"is_panel_data": True, "has_lagged_dep_var": True}
        )
        assert should is True
        assert model == ModelSwitch.OLS_TO_PANEL_GMM

    def test_decide_best_panel_fe(self):
        should, model, reason = self.decision._decide_best_model(
            [], {"is_panel_data": True, "has_lagged_dep_var": False}
        )
        assert should is True
        assert model == ModelSwitch.OLS_TO_PANEL_FE

    def test_decide_best_nonlinear(self):
        should, model, reason = self.decision._decide_best_model(
            [], {"has_binary_dep_var": True}
        )
        assert should is True
        assert model == ModelSwitch.LINEAR_TO_NONLINEAR

    def test_decide_best_psm_did(self):
        should, model, reason = self.decision._decide_best_model(
            [], {"non_random_selection": True}
        )
        assert should is True
        assert model == ModelSwitch.DID_TO_PSM_DID

    def test_decide_best_iv(self):
        should, model, reason = self.decision._decide_best_model(
            [], {"potential_endogeneity": True}
        )
        assert should is True
        assert model == ModelSwitch.DID_TO_IV

    def test_decide_best_no_switch(self):
        should, model, reason = self.decision._decide_best_model([], {})
        assert should is False
        assert model is None
        assert "最优" in reason


# ── EmpiricalAdvisor ───────────────────────────────────────────────────────────

class TestEmpiricalAdvisorInit:
    """Tests for EmpiricalAdvisor.__init__."""

    def test_init_default(self):
        advisor = EmpiricalAdvisor()
        assert advisor.topic == ""
        assert advisor.core_variable == "did"
        assert advisor.dependent_var == ""
        assert advisor.research_field == "finance"
        assert isinstance(advisor._diagnostic_engine, DiagnosticEngine)
        assert isinstance(advisor._strategy_generator, AdjustmentStrategyGenerator)
        assert isinstance(advisor._model_switch, ModelSwitchDecision)

    def test_init_custom(self):
        advisor = EmpiricalAdvisor(
            topic="Carbon trading innovation",
            core_variable="did",
            dependent_var="patent",
            research_field="corporate",
        )
        assert advisor.topic == "Carbon trading innovation"
        assert advisor.core_variable == "did"
        assert advisor.dependent_var == "patent"
        assert advisor.research_field == "corporate"

    def test_initial_state(self):
        advisor = EmpiricalAdvisor()
        assert advisor._adjustment_history == []
        assert advisor._model_history == ["baseline_ols"]


class TestEmpiricalAdvisorCheckSignificance:
    """Tests for EmpiricalAdvisor._check_significance."""

    def setup_method(self):
        self.advisor = EmpiricalAdvisor()

    def test_pval_0001(self):
        sig, level = self.advisor._check_significance(0.0001)
        assert sig is True
        assert level == "***"

    def test_pval_005(self):
        sig, level = self.advisor._check_significance(0.005)
        assert sig is True
        assert level == "**"

    def test_pval_03(self):
        sig, level = self.advisor._check_significance(0.03)
        assert sig is True
        assert level == "*"

    def test_pval_08(self):
        sig, level = self.advisor._check_significance(0.08)
        assert sig is True
        assert level == "dagger"

    def test_pval_15_not_sig(self):
        sig, level = self.advisor._check_significance(0.15)
        assert sig is False
        assert level == ""


class TestEmpiricalAdvisorEvaluate:
    """Tests for EmpiricalAdvisor.evaluate()."""

    def setup_method(self):
        self.advisor = EmpiricalAdvisor()

    def test_evaluate_insignificant_returns_diagnostics(self):
        result = self.advisor.evaluate(
            core_coef=0.02,
            core_pval=0.15,
            all_results={"did": {"coef": 0.02, "se": 0.015, "pval": 0.15}},
            diagnostics={"dw": 1.8, "bp_pval": 0.02, "vif": [2, 3]},
            context={"n_obs": 5000, "n_firms": 200, "n_years": 10},
        )
        assert isinstance(result, EvaluationResult)
        assert result.is_significant is False
        assert len(result.diagnostics) > 0

    def test_evaluate_significant(self):
        result = self.advisor.evaluate(
            core_coef=0.05,
            core_pval=0.003,
            all_results={"did": {"coef": 0.05, "se": 0.015, "pval": 0.003}},
            context={"n_obs": 5000, "n_firms": 200, "n_years": 10},  # sufficient sample
            diagnostics={},  # no issues
        )
        assert result.is_significant is True
        assert result.best_significance_level == "**"
        assert len(result.adjustment_plan) == 0

    def test_evaluate_updates_adjustment_history(self):
        result = self.advisor.evaluate(
            core_coef=0.02,
            core_pval=0.15,
            diagnostics={"bp_pval": 0.01, "vif": [15]},
            context={"n_obs": 5000},
        )
        assert len(self.advisor._adjustment_history) > 0

    def test_evaluate_increments_attempt(self):
        result = self.advisor.evaluate(
            core_coef=0.02,
            core_pval=0.15,
            diagnostics={"bp_pval": 0.01, "vif": [15]},  # triggers diagnostics
            context={"n_obs": 5000},
        )
        assert result.current_attempt > 0

    def test_evaluate_with_endogeneity_suggests_model_switch(self):
        advisor = EmpiricalAdvisor(core_variable="did")
        result = advisor.evaluate(
            core_coef=0.01,
            core_pval=0.3,
            diagnostics={},
            context={"n_obs": 5000, "potential_endogeneity": True},
        )
        # Should either suggest switch or have adjustment plan
        assert isinstance(result, EvaluationResult)
        assert len(result.action_plan) > 0

    def test_evaluate_defaults(self):
        result = self.advisor.evaluate(core_coef=0.05, core_pval=0.5)
        assert isinstance(result, EvaluationResult)
        assert result.recommendation != ""


class TestEmpiricalAdvisorRecommendation:
    """Tests for EmpiricalAdvisor recommendation generation."""

    def setup_method(self):
        self.advisor = EmpiricalAdvisor()

    def test_positive_recommendation(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROSKEDASTICITY,
            confidence=0.5,
            evidence=["Minor issue"],
            recommendation="Minor note",
            suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
        )
        rec, actions, note = self.advisor._generate_positive_recommendation([diag])
        assert "稳健性" in rec or "significant" in rec.lower()
        assert len(actions) > 0

    def test_negative_recommendation_with_plan(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.HETEROSKEDASTICITY,
            confidence=0.85,
            evidence=["Breusch-Pagan p=0.01"],
            recommendation="Use robust SE",
            suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
        )
        action = AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
            action_type="adjust_se",
            description="调整标准误结构",
            specific_changes={},
            expected_impact="More reliable SE",
            priority=3,
        )
        rec, actions, note = self.advisor._generate_negative_recommendation(
            [diag], [action], False, None
        )
        assert len(actions) > 0
        assert rec != ""

    def test_negative_recommendation_with_model_switch(self):
        diag = DiagnosticResult(
            cause=InsignificanceCause.ENDOGENEITY,
            confidence=0.9,
            evidence=["Potential endogeneity"],
            recommendation="Use IV",
            suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
            suggested_model_switch=ModelSwitch.DID_TO_IV,
        )
        rec, actions, note = self.advisor._generate_negative_recommendation(
            [diag], [], True, ModelSwitch.DID_TO_IV
        )
        assert "IV" in rec or "工具变量" in rec

    def test_research_note_low_power(self):
        advisor = EmpiricalAdvisor()
        diag = DiagnosticResult(
            cause=InsignificanceCause.LOW_POWER,
            confidence=0.9,
            evidence=["Sample < 100"],
            recommendation="Add data",
            suggested_adjustment=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
        )
        rec, actions, note = advisor._generate_negative_recommendation(
            [diag], [], False, None
        )
        assert "⚠" in note or "样本量" in note

    def test_research_note_parallel_trend(self):
        advisor = EmpiricalAdvisor()
        diag = DiagnosticResult(
            cause=InsignificanceCause.PARALLEL_TREND,
            confidence=0.75,
            evidence=["Parallel trend may be violated"],
            recommendation="Test parallel trend",
            suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
        )
        rec, actions, note = advisor._generate_negative_recommendation(
            [diag], [], False, None
        )
        assert "⚠" in note or "平行趋势" in note

    def test_model_name_cn(self):
        assert "IV" in self.advisor._model_name_cn(ModelSwitch.DID_TO_IV)
        assert "PSM" in self.advisor._model_name_cn(ModelSwitch.DID_TO_PSM_DID)
        assert "GMM" in self.advisor._model_name_cn(ModelSwitch.OLS_TO_PANEL_GMM)


class TestEmpiricalAdvisorGetStatus:
    """Tests for EmpiricalAdvisor.get_status()."""

    def test_get_status_initial(self):
        advisor = EmpiricalAdvisor()
        status = advisor.get_status()
        assert status["adjustment_attempts"] == 0
        assert status["model_history"] == ["baseline_ols"]

    def test_get_status_after_evaluate(self):
        advisor = EmpiricalAdvisor()
        advisor.evaluate(
            core_coef=0.01, core_pval=0.5,
            diagnostics={"bp_pval": 0.01, "vif": [15]},
            context={"n_obs": 5000},
        )
        status = advisor.get_status()
        assert status["adjustment_attempts"] > 0


class TestEmpiricalAdvisorReset:
    """Tests for EmpiricalAdvisor.reset()."""

    def test_reset_clears_history(self):
        advisor = EmpiricalAdvisor()
        advisor.evaluate(core_coef=0.01, core_pval=0.5, context={"n_obs": 5000})
        advisor.reset()
        assert advisor._adjustment_history == []
        assert advisor._model_history == ["baseline_ols"]


# ── Module-level helpers ───────────────────────────────────────────────────────

class TestCheckParallelTrend:
    """Tests for check_parallel_trend() helper."""

    def test_missing_columns_returns_error(self):
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = check_parallel_trend(df, "outcome", "treatment", "time")
        assert result["test_performed"] is False
        assert "缺少必要列" in result["error"]

    def test_insufficient_sample_returns_error(self):
        import pandas as pd
        df = pd.DataFrame({
            "outcome": [1.0, 2.0],
            "treatment": [0, 1],
            "time": [2020, 2021],
            "unit": [1, 2],
        })
        result = check_parallel_trend(df, "outcome", "treatment", "time")
        assert result["test_performed"] is False

    def test_insufficient_time_periods_returns_error(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "outcome": np.random.randn(n),
            "treatment": np.random.randint(0, 2, n),
            "time": [2020] * n,
            "unit": list(range(n)),
        })
        result = check_parallel_trend(df, "outcome", "treatment", "time")
        assert result["test_performed"] is False

    def test_empty_treatment_group_returns_error(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        periods = list(range(2018, 2023))  # 5 periods
        # Build fully balanced panel: n=100, 5 periods, 500 rows
        outcome = np.random.randn(n * len(periods))
        data = {
            "outcome": outcome,
            "treatment": [0] * (n * len(periods)),  # No treated units
            "time": [t for t in periods for _ in range(n)],
            "unit": [u for _ in periods for u in range(n)],
        }
        df = pd.DataFrame(data)
        result = check_parallel_trend(df, "outcome", "treatment", "time")
        assert result["test_performed"] is False

    def test_exception_handling(self):
        # Pass non-DataFrame should be handled
        result = check_parallel_trend("not a dataframe", "x", "y", "z")
        assert result["test_performed"] is False

    def test_returns_required_keys(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        periods = list(range(2018, 2023))
        outcome = np.random.randn(n * len(periods))
        data = {
            "outcome": outcome,
            "treatment": np.random.randint(0, 2, n * len(periods)),
            "time": [t for t in periods for _ in range(n)],
            "unit": [u for _ in periods for u in range(n)],
        }
        df = pd.DataFrame(data)
        result = check_parallel_trend(df, "outcome", "treatment", "time")
        assert "test_performed" in result
        assert "parallel_trend_hold" in result
        assert "pre_coefficients" in result


class TestCheckPlacebo:
    """Tests for check_placebo() helper."""

    def test_missing_columns_returns_error(self):
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = check_placebo(df, "outcome", "treatment", "time", "unit")
        assert result["test_performed"] is False
        assert "缺少必要列" in result["error"]

    def test_insufficient_sample_returns_error(self):
        import pandas as pd
        df = pd.DataFrame({
            "outcome": [1.0, 2.0, 3.0],
            "treatment": [0, 1, 0],
            "time": [2020, 2021, 2022],
            "unit": [1, 2, 3],
        })
        result = check_placebo(df, "outcome", "treatment", "time", "unit")
        assert result["test_performed"] is False

    def test_non_binary_treatment_returns_error(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        periods = list(range(2018, 2023))
        outcome = np.random.randn(n * len(periods))
        data = {
            "outcome": outcome,
            "treatment": np.random.randint(0, 5, n * len(periods)),  # Not 0/1
            "time": [t for t in periods for _ in range(n)],
            "unit": [u for _ in periods for u in range(n)],
        }
        df = pd.DataFrame(data)
        result = check_placebo(df, "outcome", "treatment", "time", "unit")
        assert result["test_performed"] is False

    def test_insufficient_time_periods_returns_error(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "outcome": np.random.randn(n),
            "treatment": np.random.randint(0, 2, n),
            "time": [2020] * n,
            "unit": list(range(n)),
        })
        result = check_placebo(df, "outcome", "treatment", "time", "unit")
        assert result["test_performed"] is False

    def test_returns_required_keys(self):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        n = 100
        periods = list(range(2018, 2023))
        outcome = np.random.randn(n * len(periods))
        data = {
            "outcome": outcome,
            "treatment": np.random.randint(0, 2, n * len(periods)),
            "time": [t for t in periods for _ in range(n)],
            "unit": [u for _ in periods for u in range(n)],
        }
        df = pd.DataFrame(data)
        result = check_placebo(df, "outcome", "treatment", "time", "unit")
        assert "test_performed" in result
        assert "significant_placebo_ratio" in result
        assert "conclusion" in result

    def test_exception_handling(self):
        result = check_placebo("not a df", "x", "y", "z", "w")
        assert result["test_performed"] is False
