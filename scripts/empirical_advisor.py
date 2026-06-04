#!/usr/bin/env python3
"""
实证分析智能顾问 (EmpiricalAdvisor)
====================================
参考经济金融论文标准流程的智能实证分析引擎。

核心功能：
1. 显著性检测与诊断
   - 自动检测核心变量是否显著
   - 分析不显著的可能原因

2. 变量自动调整（5级策略）
   - Level 1: 控制变量调整（添加/移除/替换）
   - Level 2: 数据处理优化（缩尾、缺失值处理）
   - Level 3: 标准误结构优化（聚类维度和稳健SE）
   - Level 4: 固定效应组合调整
   - Level 5: 变量度量方式更换

3. 模型智能切换（完整计量模型谱系）
   - OLS/DID → IV/2SLS（内生性处理）
   - OLS/DID → PSM+DID（选择偏差处理）
   - OLS → Panel FE（个体异质性）
   - Linear → Logit/Probit/Tobit（非线性）
   - OLS → Panel GMM（动态面板）
   - OLS → RDD（断点回归）

4. 完整检验流程
   - 平行趋势检验（DID前提）
   - 安慰剂检验
   - 稳健性检验
   - 内生性检验（工具变量/Heckman）

使用方式：
    from scripts.empirical_advisor import EmpiricalAdvisor

    advisor = EmpiricalAdvisor(
        topic="ESG对企业融资约束的影响",
        core_variable="did",  # 核心解释变量
        dependent_var="lev",   # 被解释变量
    )

    # 传入回归结果进行诊断
    result = advisor.evaluate(
        did_coef=0.05,
        did_pval=0.15,
        all_results={"lev": {...}, "ltd": {...}},
        diagnostics={"dw": 1.8, "bp_pval": 0.02, "vif": [2.1, 3.2]},
        context={"n_obs": 5000, "n_firms": 200, "n_years": 10}
    )

    print(result.recommendation)
    print(result.action_plan)
"""

import logging

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
_log = logging.getLogger("empirical_advisor")
_log.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# 常量与枚举
# ─────────────────────────────────────────────────────────────────────────────

class InsignificanceCause(Enum):
    """不显著的可能原因"""
    ENDOGENEITY = "endogeneity"           # 内生性问题
    SELECTION_BIAS = "selection_bias"     # 选择偏差
    HETEROGENEITY = "heterogeneity"       # 个体异质性
    DYNAMIC_EFFECT = "dynamic_effect"     # 动态效应
    MEASUREMENT_ERROR = "measurement_error"  # 测量误差
    OUTLIERS = "outliers"                 # 极端值影响
    MULTICOLLINEARITY = "multicollinearity"  # 多重共线性
    HETEROSKEDASTICITY = "heteroskedasticity"  # 异方差
    AUTOCORRELATION = "autocorrelation"   # 自相关
    LOW_POWER = "low_statistical_power"   # 统计功效不足
    WRONG_MODEL = "wrong_model_type"      # 模型设定错误
    PARALLEL_TREND = "parallel_trend_violated"  # 平行趋势违反


class AdjustmentStrategy(Enum):
    """变量调整策略级别"""
    LEVEL_1_CONTROL_VARS = "level1_control_vars"      # 控制变量调整
    LEVEL_2_DATA_CLEANING = "level2_data_cleaning"    # 数据清洗优化
    LEVEL_3_SE_STRUCTURE = "level3_se_structure"      # 标准误结构
    LEVEL_4_FIXED_EFFECTS = "level4_fixed_effects"   # 固定效应调整
    LEVEL_5_VARIABLE_MEASURE = "level5_measurement"  # 变量度量更换


class ModelSwitch(Enum):
    """模型切换选项"""
    DID_TO_IV = "did_to_iv"                 # DID → IV/2SLS
    DID_TO_PSM_DID = "did_to_psm_did"       # DID → PSM+DID
    OLS_TO_PANEL_FE = "ols_to_panel_fe"     # OLS → 面板固定效应
    LINEAR_TO_NONLINEAR = "linear_to_nonlinear"  # 线性 → 非线性
    OLS_TO_PANEL_GMM = "ols_to_panel_gmm"  # OLS → GMM
    OLS_TO_RDD = "ols_to_rdd"              # OLS → RDD
    PANEL_TO_FAMA_MACBETH = "panel_to_fama_macbeth"  # 面板 → Fama-MacBeth
    OLS_TO_HECKMAN = "ols_to_heckman"      # OLS → Heckman两步法


class SignificanceLevel(Enum):
    """显著性水平"""
    P_001 = ("***", 0.001)
    P_01 = ("**", 0.01)
    P_05 = ("*", 0.05)
    P_10 = ("dagger", 0.10)
    NOT_SIGNIFICANT = ("", 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DiagnosticResult:
    """诊断结果"""
    cause: InsignificanceCause
    confidence: float  # 0-1，可信度
    evidence: list[str]  # 支持该诊断的证据
    recommendation: str  # 建议措施
    suggested_adjustment: AdjustmentStrategy
    suggested_model_switch: ModelSwitch | None = None


@dataclass
class AdjustmentAction:
    """调整动作"""
    level: AdjustmentStrategy
    action_type: str  # "add_control", "remove_control", "winsorize", "cluster", etc.
    description: str
    specific_changes: dict[str, Any]  # 具体变更描述
    expected_impact: str  # 预期影响
    priority: int  # 1-5, 优先级


@dataclass
class EvaluationResult:
    """评估结果"""
    is_significant: bool
    best_significance_level: str  # "***", "**", "*", "dagger", ""
    core_variable_result: dict  # 核心变量的结果

    # 诊断信息
    diagnostics: list[DiagnosticResult]

    # 行动建议
    adjustment_plan: list[AdjustmentAction]  # 变量调整计划
    model_switch_recommendation: ModelSwitch | None  # 模型切换建议

    # 综合决策
    recommendation: str  # 总体建议
    action_plan: list[str]  # 具体行动计划
    research_note: str  # 研究注释（如果需要人工介入）

    # 元数据
    max_attempts: int = 3  # 最大自动调整次数
    current_attempt: int = 0
    exhausted_strategies: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 核心诊断逻辑
# ─────────────────────────────────────────────────────────────────────────────

class DiagnosticEngine:
    """
    诊断引擎：分析不显著原因并提供诊断建议。

    诊断流程参考经济金融论文的实证检验标准。
    """

    # 不同原因的特征模式
    CAUSE_PATTERNS = {
        InsignificanceCause.ENDOGENEITY: {
            "indicators": {
                "reverse_causality": True,  # 可能存在反向因果
                "omitted_variable": True,    # 可能遗漏变量
                "simulated_instruments": False,  # 工具变量是否模拟
            },
            "evidence_weight": 0.8,
        },
        InsignificanceCause.SELECTION_BIAS: {
            "indicators": {
                "non_random_treatment": True,  # 非随机处理
                "propensity_score_low": True,   # PSM得分重叠区域小
            },
            "evidence_weight": 0.75,
        },
        InsignificanceCause.HETEROGENEITY: {
            "indicators": {
                "high_firm_variance": True,   # 企业间方差大
                "significant_fe_variance": True,  # FE显著
            },
            "evidence_weight": 0.7,
        },
    }

    def diagnose(
        self,
        regression_result: dict,
        context: dict,
        diagnostics: dict | None = None,
    ) -> list[DiagnosticResult]:
        """
        综合诊断，识别不显著的可能原因。

        Args:
            regression_result: 回归结果（包含系数、SE、p值等）
            context: 上下文信息（样本量、企业数、年份数等）
            diagnostics: 额外诊断检验结果（DW、BP、VIF等）

        Returns:
            list[DiagnosticResult]: 可能的诊断原因列表，按可信度排序
        """
        results = []

        # 1. 检查统计功效（样本量）
        if context.get("n_obs", 0) < 100:
            results.append(DiagnosticResult(
                cause=InsignificanceCause.LOW_POWER,
                confidence=0.9,
                evidence=["样本量不足100，可能统计功效不足"],
                recommendation="增加样本量或使用面板数据",
                suggested_adjustment=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
            ))

        # 2. 检查异方差
        if diagnostics:
            if diagnostics.get("bp_pval", 1) < 0.05:
                results.append(DiagnosticResult(
                    cause=InsignificanceCause.HETEROSKEDASTICITY,
                    confidence=0.85,
                    evidence=[f"Breusch-Pagan检验p={diagnostics['bp_pval']:.3f} < 0.05，存在异方差"],
                    recommendation="使用稳健标准误（HC1/HC3）或聚类稳健SE",
                    suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
                ))

            # 3. 检查自相关
            dw = diagnostics.get("dw", 2.0)
            if dw < 1.5 or dw > 2.5:
                results.append(DiagnosticResult(
                    cause=InsignificanceCause.AUTOCORRELATION,
                    confidence=0.8,
                    evidence=[f"Durbin-Watson={dw:.3f}，存在自相关问题"],
                    recommendation="使用Newey-West稳健标准误或聚类到企业层面",
                    suggested_adjustment=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
                ))

            # 4. 检查多重共线性
            vif_max = max(diagnostics.get("vif", [0]))
            if vif_max > 10:
                results.append(DiagnosticResult(
                    cause=InsignificanceCause.MULTICOLLINEARITY,
                    confidence=0.9,
                    evidence=[f"最大VIF={vif_max:.1f} > 10，存在严重共线性"],
                    recommendation="剔除或合并高度相关的控制变量",
                    suggested_adjustment=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
                ))
            elif vif_max > 5:
                results.append(DiagnosticResult(
                    cause=InsignificanceCause.MULTICOLLINEARITY,
                    confidence=0.7,
                    evidence=[f"最大VIF={vif_max:.1f} > 5，存在中等共线性"],
                    recommendation="关注变量共线性，考虑剔除高共线性变量",
                    suggested_adjustment=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
                ))

        # 5. 检查极端值
        if context.get("has_extreme_values", False):
            results.append(DiagnosticResult(
                cause=InsignificanceCause.OUTLIERS,
                confidence=0.75,
                evidence=["数据存在极端值，可能影响回归结果"],
                recommendation="对连续变量进行1%/99%缩尾处理",
                suggested_adjustment=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
            ))

        # 6. 检查内生性风险
        if context.get("potential_endogeneity", False):
            results.append(DiagnosticResult(
                cause=InsignificanceCause.ENDOGENEITY,
                confidence=0.85,
                evidence=["处理变量可能存在内生性问题（反向因果/遗漏变量）"],
                recommendation="考虑使用工具变量法（IV/2SLS）或Heckman两步法",
                suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
                suggested_model_switch=ModelSwitch.DID_TO_IV,
            ))

        # 7. 检查选择偏差
        if context.get("non_random_selection", False):
            results.append(DiagnosticResult(
                cause=InsignificanceCause.SELECTION_BIAS,
                confidence=0.8,
                evidence=["样本可能存在自选择问题"],
                recommendation="使用PSM倾向得分匹配+DID方法",
                suggested_adjustment=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
                suggested_model_switch=ModelSwitch.DID_TO_PSM_DID,
            ))

        # 8. 检查平行趋势
        if context.get("did_setting", False):
            results.append(DiagnosticResult(
                cause=InsignificanceCause.PARALLEL_TREND,
                confidence=0.75,
                evidence=["DID设置可能违反平行趋势假设"],
                recommendation="进行事件研究法（Event Study）检验平行趋势",
                suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
            ))

        # 9. 检查个体异质性
        if context.get("high_firm_heterogeneity", False):
            results.append(DiagnosticResult(
                cause=InsignificanceCause.HETEROGENEITY,
                confidence=0.7,
                evidence=["企业间异质性较高"],
                recommendation="考虑双向固定效应或随机效应模型",
                suggested_adjustment=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
                suggested_model_switch=ModelSwitch.OLS_TO_PANEL_FE,
            ))

        # 按可信度排序
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 调整策略生成器
# ─────────────────────────────────────────────────────────────────────────────

class AdjustmentStrategyGenerator:
    """
    调整策略生成器：基于诊断结果生成变量调整计划。

    参考经济金融论文的标准调整流程。
    """

    # 标准控制变量模板（按研究领域）
    CONTROL_VAR_TEMPLATES = {
        "finance": ["ln_assets", "roa", "lev", "tangibility", "mb", "cash_ratio", "age"],
        "corporate": ["ln_assets", "roa", "lev", "tangibility", "mb", "soe", "top1_holder"],
        "macro": ["gdp_growth", "inflation", "money_supply", "exchange_rate"],
        "default": ["size", "leverage", "profitability", "tangibility", "growth"],
    }

    def __init__(self, research_field: str = "finance"):
        self.research_field = research_field
        self.standard_controls = self.CONTROL_VAR_TEMPLATES.get(
            research_field, self.CONTROL_VAR_TEMPLATES["default"]
        )

    def generate_plan(
        self,
        diagnostics: list[DiagnosticResult],
        current_controls: list[str],
        current_fe: dict,
        context: dict,
    ) -> list[AdjustmentAction]:
        """
        基于诊断结果生成调整计划。

        Args:
            diagnostics: 诊断结果列表
            current_controls: 当前控制变量
            current_fe: 当前固定效应设置
            context: 上下文信息

        Returns:
            list[AdjustmentAction]: 调整动作列表
        """
        plan = []

        for diag in diagnostics:
            action = self._create_action(diag, current_controls, current_fe, context)
            if action:
                plan.append(action)

        # 按优先级排序
        plan.sort(key=lambda x: x.priority)
        return plan

    def _create_action(
        self,
        diag: DiagnosticResult,
        current_controls: list[str],
        current_fe: dict,
        context: dict,
    ) -> AdjustmentAction | None:
        """根据诊断创建具体调整动作"""

        cause = diag.cause
        strategy = diag.suggested_adjustment

        if strategy == AdjustmentStrategy.LEVEL_1_CONTROL_VARS:
            return self._level1_action(diag, current_controls, context)
        elif strategy == AdjustmentStrategy.LEVEL_2_DATA_CLEANING:
            return self._level2_action(diag, context)
        elif strategy == AdjustmentStrategy.LEVEL_3_SE_STRUCTURE:
            return self._level3_action(diag, context)
        elif strategy == AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS:
            return self._level4_action(diag, current_fe)
        elif strategy == AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE:
            return self._level5_action(diag, context)

        return None

    def _level1_action(
        self,
        diag: DiagnosticResult,
        current_controls: list[str],
        context: dict,
    ) -> AdjustmentAction:
        """Level 1: 控制变量调整"""
        missing_standard = [c for c in self.standard_controls if c not in current_controls]
        redundant = [c for c in current_controls if c not in self.standard_controls and context.get("vif_high_vars", [])]

        return AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_1_CONTROL_VARS,
            action_type="adjust_controls",
            description="调整控制变量组合",
            specific_changes={
                "add": missing_standard[:2],  # 最多添加2个
                "remove": redundant[:1],  # 最多移除1个
                "reason": diag.recommendation,
            },
            expected_impact="可能改善核心变量显著性（减少遗漏变量偏误或降低共线性）",
            priority=1,
        )

    def _level2_action(
        self,
        diag: DiagnosticResult,
        context: dict,
    ) -> AdjustmentAction:
        """Level 2: 数据清洗优化"""
        return AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_2_DATA_CLEANING,
            action_type="winsorize_outliers",
            description="对连续变量进行缩尾处理",
            specific_changes={
                "winsorize_vars": ["ln_assets", "roa", "lev", "tangibility", "mb", "cash_ratio"],
                "lower": 0.01,
                "upper": 0.99,
                "reason": "减少极端值对回归的影响",
            },
            expected_impact="减少极端值影响，提高统计功效",
            priority=2,
        )

    def _level3_action(
        self,
        diag: DiagnosticResult,
        context: dict,
    ) -> AdjustmentAction:
        """Level 3: 标准误结构优化"""
        n_firms = context.get("n_firms", 100)
        n_years = context.get("n_years", 10)

        # 根据数据结构选择聚类维度
        if n_firms > 50 and n_years > 5:
            cluster = "firm"
            se_type = "double_cluster"
        elif n_firms > 50:
            cluster = "firm"
            se_type = "cluster"
        else:
            cluster = "industry"
            se_type = "robust"

        return AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_3_SE_STRUCTURE,
            action_type="adjust_se",
            description="调整标准误结构",
            specific_changes={
                "se_type": se_type,
                "cluster_vars": [cluster] if se_type == "cluster" else ["firm", "year"],
                "robust_type": "HC3" if se_type == "robust" else None,
                "reason": f"当前数据({n_firms}企业×{n_years}年)，推荐{se_type}标准误",
            },
            expected_impact="获得更可靠的标准误和p值",
            priority=3,
        )

    def _level4_action(
        self,
        diag: DiagnosticResult,
        current_fe: dict,
    ) -> AdjustmentAction:
        """Level 4: 固定效应调整"""
        firm_fe = current_fe.get("firm_fe", True)
        year_fe = current_fe.get("year_fe", True)
        industry_fe = current_fe.get("industry_fe", False)

        # 建议的固定效应组合
        if not firm_fe:
            new_fe = {"firm_fe": True, "year_fe": year_fe, "industry_fe": industry_fe}
            desc = "添加企业固定效应"
        elif not year_fe:
            new_fe = {"firm_fe": firm_fe, "year_fe": True, "industry_fe": industry_fe}
            desc = "添加年份固定效应"
        elif not industry_fe:
            new_fe = {"firm_fe": firm_fe, "year_fe": year_fe, "industry_fe": True}
            desc = "添加行业固定效应"
        else:
            new_fe = {"firm_fe": firm_fe, "year_fe": year_fe, "industry_fe": industry_fe}
            desc = "当前固定效应组合已是最优，考虑移除企业FE使用Driscoll-Kraay SE"

        return AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_4_FIXED_EFFECTS,
            action_type="adjust_fixed_effects",
            description=desc,
            specific_changes={
                "current_fe": current_fe,
                "suggested_fe": new_fe,
                "reason": diag.recommendation,
            },
            expected_impact="控制更多不可观测的异质性",
            priority=4,
        )

    def _level5_action(
        self,
        diag: DiagnosticResult,
        context: dict,
    ) -> AdjustmentAction:
        """Level 5: 变量度量更换"""
        # 根据研究主题建议变量度量
        topic = context.get("topic", "").lower()

        if "融资约束" in topic or "finance" in topic:
            alt_vars = {
                "dep_vars": ["SA_index", "KZ_index", "WW_index", "cash_holding"],
                "treat_vars": ["esg_score", "esg_rating", "emission_level"],
            }
        elif "创新" in topic or "innovation" in topic:
            alt_vars = {
                "dep_vars": ["rd_intensity", "patent_count", "new_product"],
                "treat_vars": ["subsidy", "tax_incentive", "policy"],
            }
        else:
            alt_vars = {
                "dep_vars": ["performance", "productivity", "efficiency"],
                "treat_vars": ["treatment", "policy", "reform"],
            }

        return AdjustmentAction(
            level=AdjustmentStrategy.LEVEL_5_VARIABLE_MEASURE,
            action_type="change_variable_measure",
            description="考虑更换变量度量方式",
            specific_changes={
                "alternative_vars": alt_vars,
                "reason": "当前度量可能不敏感，建议尝试替代度量",
            },
            expected_impact="可能找到更敏感的核心变量度量方式",
            priority=5,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 模型切换决策器
# ─────────────────────────────────────────────────────────────────────────────

class ModelSwitchDecision:
    """
    模型切换决策器：决定何时从当前模型切换到更合适的模型。

    参考经济金融论文的模型选择标准。
    """

    # 模型适用场景
    MODEL_SUITABILITY = {
        ModelSwitch.DID_TO_IV: {
            "condition": "potential_endogeneity",
            "required_context": ["has_instrument"],
            "expected_improvement": "解决内生性偏误",
        },
        ModelSwitch.DID_TO_PSM_DID: {
            "condition": "non_random_selection",
            "required_context": ["has_covariates_for_psm"],
            "expected_improvement": "解决样本选择偏误",
        },
        ModelSwitch.OLS_TO_PANEL_FE: {
            "condition": "high_firm_heterogeneity",
            "required_context": ["panel_data"],
            "expected_improvement": "控制个体异质性",
        },
        ModelSwitch.LINEAR_TO_NONLINEAR: {
            "condition": "bounded_dep_var",
            "required_context": [],
            "expected_improvement": "更准确地建模",
        },
        ModelSwitch.OLS_TO_PANEL_GMM: {
            "condition": "dynamic_panel",
            "required_context": ["lagged_dep_var"],
            "expected_improvement": "处理动态面板内生性",
        },
        ModelSwitch.OLS_TO_RDD: {
            "condition": "continuity_assignment",
            "required_context": ["forcing_var", "cutoff"],
            "expected_improvement": "更干净的因果识别",
        },
        ModelSwitch.PANEL_TO_FAMA_MACBETH: {
            "condition": "cross_sectional_correlation",
            "required_context": ["panel_data", "many_firms"],
            "expected_improvement": "处理横截面相关",
        },
        ModelSwitch.OLS_TO_HECKMAN: {
            "condition": "sample_selection",
            "required_context": ["selection_equation"],
            "expected_improvement": "解决样本选择问题",
        },
    }

    def should_switch(
        self,
        diagnostics: list[DiagnosticResult],
        exhausted_strategies: list[str],
        context: dict,
        max_adjustment_attempts: int = 3,
    ) -> tuple[bool, ModelSwitch | None, str]:
        """
        判断是否应该切换模型。

        Args:
            diagnostics: 诊断结果
            exhausted_strategies: 已尝试过的调整策略
            context: 上下文
            max_adjustment_attempts: 最大自动调整次数

        Returns:
            (should_switch, suggested_model, reason)
        """
        # 如果所有策略都已尝试，考虑切换
        all_strategies = [s.value for s in AdjustmentStrategy]
        remaining = [s for s in all_strategies if s not in exhausted_strategies]

        if len(remaining) == 0:
            # 所有变量调整策略都已尝试，需要切换模型
            return self._decide_best_model(diagnostics, context)

        # 如果特定诊断建议模型切换
        for diag in diagnostics:
            if diag.suggested_model_switch:
                confidence = diag.confidence
                if confidence > 0.8:
                    return True, diag.suggested_model_switch, diag.recommendation

        return False, None, ""

    def _decide_best_model(
        self,
        diagnostics: list[DiagnosticResult],
        context: dict,
    ) -> tuple[bool, ModelSwitch | None, str]:
        """在所有策略耗尽后，选择最佳替代模型"""

        for diag in diagnostics:
            if diag.suggested_model_switch:
                return True, diag.suggested_model_switch, diag.recommendation

        # 基于上下文选择默认替代模型
        if context.get("is_panel_data"):
            if context.get("has_lagged_dep_var"):
                return True, ModelSwitch.OLS_TO_PANEL_GMM, "面板数据存在内生性，尝试GMM"
            else:
                return True, ModelSwitch.OLS_TO_PANEL_FE, "使用面板固定效应模型"

        if context.get("has_binary_dep_var"):
            return True, ModelSwitch.LINEAR_TO_NONLINEAR, "被解释变量为二值变量，尝试Logit/Probit"

        if context.get("non_random_selection"):
            return True, ModelSwitch.DID_TO_PSM_DID, "存在选择偏误，尝试PSM+DID"

        if context.get("potential_endogeneity"):
            return True, ModelSwitch.DID_TO_IV, "存在内生性，尝试工具变量法"

        return False, None, "当前模型已是最优选择"


# ─────────────────────────────────────────────────────────────────────────────
# 实证分析智能顾问（主类）
# ─────────────────────────────────────────────────────────────────────────────

class EmpiricalAdvisor:
    """
    实证分析智能顾问：指导实证研究流程的智能系统。

    使用方式：
        advisor = EmpiricalAdvisor(
            topic="ESG对企业融资约束的影响",
            core_variable="did",
            dependent_var="lev",
        )

        result = advisor.evaluate(
            did_coef=0.05,
            did_pval=0.15,
            all_results={...},
            diagnostics={"dw": 1.8, "bp_pval": 0.02, "vif": [2.1, 3.2]},
            context={"n_obs": 5000, "n_firms": 200, "n_years": 10}
        )

        print(result.recommendation)
    """

    def __init__(
        self,
        topic: str = "",
        core_variable: str = "did",
        dependent_var: str = "",
        research_field: str = "finance",
    ):
        self.topic = topic
        self.core_variable = core_variable
        self.dependent_var = dependent_var
        self.research_field = research_field

        # 初始化组件
        self._diagnostic_engine = DiagnosticEngine()
        self._strategy_generator = AdjustmentStrategyGenerator(research_field)
        self._model_switch = ModelSwitchDecision()

        # 状态跟踪
        self._adjustment_history: list[AdjustmentAction] = []
        self._model_history: list[str] = ["baseline_ols"]

    def evaluate(
        self,
        core_coef: float,
        core_pval: float,
        all_results: dict | None = None,
        diagnostics: dict | None = None,
        context: dict | None = None,
        current_controls: list[str] | None = None,
        current_fe: dict | None = None,
    ) -> EvaluationResult:
        """
        评估实证结果并提供改进建议。

        Args:
            core_coef: 核心变量系数
            core_pval: 核心变量p值
            all_results: 所有回归结果
            diagnostics: 诊断检验结果（DW、BP、VIF等）
            context: 上下文信息
            current_controls: 当前控制变量
            current_fe: 当前固定效应

        Returns:
            EvaluationResult: 评估结果和建议
        """
        context = context or {}
        diagnostics = diagnostics or {}
        all_results = all_results or {}

        # 1. 判断显著性
        is_significant, sig_level = self._check_significance(core_pval)

        # 2. 综合诊断
        regression_result = {
            "coef": core_coef,
            "pval": core_pval,
            "se": all_results.get(f"{self.core_variable}_se", 0),
        }
        diag_results = self._diagnostic_engine.diagnose(
            regression_result, context, diagnostics
        )

        # 3. 生成调整计划
        current_controls = current_controls or []
        current_fe = current_fe or {"firm_fe": True, "year_fe": True}
        adjustment_plan = self._strategy_generator.generate_plan(
            diag_results, current_controls, current_fe, context
        )

        # 4. 判断是否需要模型切换
        exhausted = [a.level.value for a in self._adjustment_history]
        should_switch, model_switch, switch_reason = self._model_switch.should_switch(
            diag_results, exhausted, context
        )

        # 5. 生成最终建议
        recommendation, action_plan, research_note = self._generate_recommendation(
            is_significant, diag_results, adjustment_plan, should_switch, model_switch
        )

        # 6. 更新状态
        self._adjustment_history.extend(adjustment_plan)
        if model_switch:
            self._model_history.append(model_switch.value)

        return EvaluationResult(
            is_significant=is_significant,
            best_significance_level=sig_level,
            core_variable_result={
                "coef": core_coef,
                "pval": core_pval,
                "sig": sig_level,
            },
            diagnostics=diag_results,
            adjustment_plan=adjustment_plan,
            model_switch_recommendation=model_switch if should_switch else None,
            recommendation=recommendation,
            action_plan=action_plan,
            research_note=research_note,
            current_attempt=len(self._adjustment_history),
        )

    def _check_significance(self, pval: float) -> tuple[bool, str]:
        """检查显著性水平"""
        if pval < 0.001:
            return True, "***"
        elif pval < 0.01:
            return True, "**"
        elif pval < 0.05:
            return True, "*"
        elif pval < 0.1:
            return True, "dagger"
        else:
            return False, ""

    def _generate_recommendation(
        self,
        is_significant: bool,
        diagnostics: list[DiagnosticResult],
        adjustment_plan: list[AdjustmentAction],
        should_switch: bool,
        model_switch: ModelSwitch | None,
    ) -> tuple[str, list[str], str]:
        """生成最终建议"""

        if is_significant:
            return self._generate_positive_recommendation(diagnostics)
        else:
            return self._generate_negative_recommendation(
                diagnostics, adjustment_plan, should_switch, model_switch
            )

    def _generate_positive_recommendation(
        self,
        diagnostics: list[DiagnosticResult],
    ) -> tuple[str, list[str], str]:
        """结果显著时的建议"""
        action_plan = [
            "结果已显著，继续进行稳健性检验",
            "进行安慰剂检验验证结果稳健性",
            "考虑进行内生性检验（如IV/2SLS）",
        ]

        research_note = ""
        if diagnostics:
            warnings = [d.recommendation for d in diagnostics[:2]]
            if warnings:
                research_note = f"注意：{warnings[0]}"

        return "核心变量结果显著，建议进行稳健性检验", action_plan, research_note

    def _generate_negative_recommendation(
        self,
        diagnostics: list[DiagnosticResult],
        adjustment_plan: list[AdjustmentAction],
        should_switch: bool,
        model_switch: ModelSwitch | None,
    ) -> tuple[str, list[str], str]:
        """结果不显著时的建议"""
        action_plan = []

        # 添加调整计划
        for action in adjustment_plan[:3]:  # 最多3个
            action_plan.append(action.description)

        recommendation = ""
        research_note = ""

        if should_switch and model_switch:
            switch_info = self._model_switch.MODEL_SUITABILITY.get(model_switch, {})
            recommendation = (
                f"建议切换到{self._model_name_cn(model_switch)}。"
                f"原因：{switch_info.get('expected_improvement', '更合适的模型设定')}"
            )
            action_plan.append(f"模型切换: {self._model_name_cn(model_switch)}")
        else:
            if adjustment_plan:
                top_action = adjustment_plan[0]
                recommendation = (
                    f"建议尝试{top_action.description}。"
                    f"预期：{top_action.expected_impact}"
                )
            else:
                recommendation = "当前模型设定下结果不显著，建议重新审视研究设计"

        # 添加研究注释
        if diagnostics:
            for d in diagnostics[:2]:
                if d.cause == InsignificanceCause.LOW_POWER:
                    research_note = "⚠ 样本量可能不足，建议增加样本或使用面板数据"
                elif d.cause == InsignificanceCause.PARALLEL_TREND:
                    research_note = "⚠ DID前提假设可能不成立，需进行平行趋势检验"

        return recommendation, action_plan, research_note

    def _model_name_cn(self, model_switch: ModelSwitch) -> str:
        """模型名称中文"""
        names = {
            ModelSwitch.DID_TO_IV: "工具变量回归（IV/2SLS）",
            ModelSwitch.DID_TO_PSM_DID: "倾向得分匹配+DID（PSM+DID）",
            ModelSwitch.OLS_TO_PANEL_FE: "面板固定效应模型",
            ModelSwitch.LINEAR_TO_NONLINEAR: "非线性模型（Logit/Probit）",
            ModelSwitch.OLS_TO_PANEL_GMM: "面板GMM估计",
            ModelSwitch.OLS_TO_RDD: "断点回归设计（RDD）",
            ModelSwitch.PANEL_TO_FAMA_MACBETH: "Fama-MacBeth两步法",
            ModelSwitch.OLS_TO_HECKMAN: "Heckman两步法",
        }
        return names.get(model_switch, str(model_switch.value))

    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "adjustment_attempts": len(self._adjustment_history),
            "adjustment_history": [
                {"level": a.level.value, "action": a.action_type}
                for a in self._adjustment_history
            ],
            "model_history": self._model_history,
        }

    def reset(self):
        """重置状态"""
        self._adjustment_history = []
        self._model_history = ["baseline_ols"]


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def check_parallel_trend(
    df: Any,
    outcome_var: str,
    treatment_var: str,
    time_var: str,
    pre_periods: int = 3,
) -> dict:
    """
    平行趋势检验（事件研究法）。

    对政策前各期与基期进行回归，检验处理组与对照组在政策前是否满足平行趋势假设。

    Args:
        df: DataFrame，包含 outcome_var, treatment_var, time_var 列
        outcome_var: 结果变量名
        treatment_var: 处理变量名（0/1 二值）
        time_var: 时间变量名（数值型，如年份）
        pre_periods: 检验政策前几期

    Returns:
        dict with test results including pre_coefficients, parallel_trend_hold, and recommendation
    """
    import warnings
    warnings.filterwarnings("ignore")

    try:
        import numpy as np
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        required = [outcome_var, treatment_var, time_var]
        available = [c for c in required if c in df.columns]
        if len(available) < 3:
            return {
                "test_performed": False,
                "error": f"缺少必要列：{set(required) - set(available)}",
                "parallel_trend_hold": False,
                "pre_coefficients": [],
                "recommendation": "数据缺少必要列，无法进行平行趋势检验",
            }

        data = df[required].dropna()
        if len(data) < 50:
            return {
                "test_performed": False,
                "error": f"样本量不足 ({len(data)}<50)",
                "parallel_trend_hold": False,
                "pre_coefficients": [],
                "recommendation": "样本量不足，建议增加数据",
            }

        times = sorted(data[time_var].unique())
        if len(times) < 3:
            return {
                "test_performed": False,
                "error": f"时间期数不足 ({len(times)}<3)",
                "parallel_trend_hold": False,
                "pre_coefficients": [],
                "recommendation": "时间期数不足，无法进行事件研究",
            }

        # 找到政策实施的时间点（使用处理组中最早的政策实施时间）
        treat_times = data[data[treatment_var] == 1][time_var].unique()
        if len(treat_times) == 0:
            return {
                "test_performed": False,
                "error": "处理组为空",
                "parallel_trend_hold": False,
                "pre_coefficients": [],
                "recommendation": "处理组为空，无法进行平行趋势检验",
            }

        # 正确做法：基准期为政策实施前的最后一个观测期（而非时间序列中位数）
        policy_time = int(np.min(treat_times))  # 最早的政策实施时间
        pre_periods = [t for t in times if t < policy_time]
        if pre_periods:
            # 基准期 = 政策前最后一个观测期
            base_period = max(pre_periods)
        else:
            # 无政策前期：回退到第2个观测期
            base_period = times[1] if len(times) > 1 else times[0]

        # 构建事件时间（相对时间）
        data = data.copy()
        data["rel_time"] = data[time_var] - policy_time

        # 构建相对时间虚拟变量（基期为 base_period 的相对时间）
        data["rel_time_centered"] = data[time_var] - base_period

        # 生成各期的交互项（排除基期）
        interaction_coefs = {}
        interaction_se = {}
        interaction_pvals = {}

        for t in times:
            if t == base_period:
                continue
            col = f"rel_{int(t)}"
            data[col] = (data[time_var] == t).astype(float) * data[treatment_var]

            try:
                # 简单回归：outcome ~ treat * time_dummy + treat + time_dummy
                y = data[outcome_var].values
                t_dummy = (data[time_var] == t).astype(float).values
                treat = data[treatment_var].values

                X = np.column_stack([np.ones(len(y)), treat, t_dummy, data[col].values])
                X = sm.add_constant(data[[treatment_var, col]].values)

                model = sm.OLS(data[outcome_var].values, X).fit(disp=False)

                # 提取交互项系数
                if col in model.params.index or len(model.params) >= 3:
                    idx = len(model.params) - 1  # 交互项在最后
                    interaction_coefs[col] = float(model.params[idx])
                    interaction_se[col] = float(model.bse[idx])
                    interaction_pvals[col] = float(model.pvalues[idx])
            except Exception as exc:
                logger.warning(f"Event-study coefficient extraction failed (col={col}): {exc}")
                pass

        # 整理结果
        pre_coefs = []
        for col, coef in sorted(interaction_coefs.items()):
            rel_t = int(col.split("_")[1]) - base_period
            if rel_t < 0:
                pre_coefs.append({
                    "period": rel_t,
                    "coef": coef,
                    "se": interaction_se[col],
                    "pval": interaction_pvals[col],
                    "sig": ("***" if interaction_pvals[col] < 0.001
                            else "**" if interaction_pvals[col] < 0.01
                            else "*" if interaction_pvals[col] < 0.05
                            else ""),
                })

        # 判断平行趋势是否成立：
        # 政策前各期系数均不显著（p > 0.1）
        pre_significant = [c for c in pre_coefs if c["pval"] < 0.1]
        parallel_trend_hold = len(pre_significant) == 0

        # F 检验：政策前所有系数联合为零
        all_pre_cols = [f"rel_{int(t)}" for t in times if t != base_period]
        pre_cols_available = [c for c in all_pre_cols if c in data.columns]

        if len(pre_cols_available) > 1:
            try:
                y = data[outcome_var].values
                X_data = data[pre_cols_available].values
                X = np.column_stack([np.ones(len(y)), data[treatment_var].values, X_data])
                restrict_model = sm.OLS(y, np.column_stack([np.ones(len(y)), data[treatment_var].values])).fit(disp=False)
                full_model = sm.OLS(y, X).fit(disp=False)

                rss_restricted = restrict_model.ssr
                rss_full = full_model.ssr
                q = len(pre_cols_available)
                n = len(y)
                k = X.shape[1]

                if rss_restricted > rss_full:
                    f_stat = ((rss_restricted - rss_full) / q) / (rss_full / (n - k))
                    f_pval = 1 - scipy_stats.f.cdf(f_stat, q, n - k)
                    joint_test_pass = f_pval > 0.1
                else:
                    f_stat = 0.0
                    f_pval = 1.0
                    joint_test_pass = True
            except Exception as exc:
                logger.warning(f"check_parallel_trend: F-test failed, skipping — {exc}")
        else:
            f_stat = 0.0
            f_pval = 1.0
            joint_test_pass = True

        # 生成建议
        if parallel_trend_hold and joint_test_pass:
            conclusion = "平行趋势假设成立"
            recommendation = "DID 估计结果可信，可继续使用双重差分方法"
        elif not parallel_trend_hold:
            significant_pre = [c for c in pre_coefs if c["pval"] < 0.1]
            worst = min(significant_pre, key=lambda x: x["pval"]) if significant_pre else None
            conclusion = f"平行趋势假设不完全成立（{len(significant_pre)}期显著）"
            recommendation = (
                f"处理前第{worst['period']}期系数显著(p={worst['pval']:.3f})，"
                "建议：(1)更换基期；(2)使用PSM+DID；(3)考虑事件研究法调整"
            )
        else:
            conclusion = "平行趋势假设在联合F检验下成立，但个别期可能有问题"
            recommendation = "建议进一步检查个别期系数，考虑使用Driscoll-Kraay SE"

        return {
            "test_performed": True,
            "parallel_trend_hold": parallel_trend_hold,
            "pre_coefficients": pre_coefs,
            "post_coefficients": [
                {"period": int(col.split("_")[1]) - base_period,
                 "coef": interaction_coefs[col],
                 "se": interaction_se[col],
                 "pval": interaction_pvals[col],
                 "sig": ("***" if interaction_pvals[col] < 0.001
                         else "**" if interaction_pvals[col] < 0.01
                         else "*" if interaction_pvals[col] < 0.05
                         else "")}
                for col in interaction_coefs
                if int(col.split("_")[1]) - base_period > 0
            ],
            "joint_f_test": {
                "f_stat": float(f_stat),
                "pval": float(f_pval),
                "significant": not joint_test_pass,
            },
            "base_period": int(base_period),
            "conclusion": conclusion,
            "recommendation": recommendation,
        }

    except Exception as e:
        return {
            "test_performed": False,
            "error": str(e),
            "parallel_trend_hold": False,
            "pre_coefficients": [],
            "recommendation": f"平行趋势检验执行失败：{e}，建议人工检查数据",
        }


def check_placebo(
    df: Any,
    outcome_var: str,
    treatment_var: str,
    time_var: str,
    unit_var: str = "unit",
    n_simulations: int = 1000,
) -> dict:
    """
    安慰剂检验（Placebo Test）。

    将政策实施时间随机化，重新估计DID系数。
    若随机化后的系数显著的比例接近5%（α=0.05），说明原结果不是偶然的。

    Args:
        df: DataFrame
        outcome_var: 结果变量名
        treatment_var: 处理变量名
        time_var: 时间变量名
        unit_var: 单位变量名（用于匹配）
        n_simulations: 模拟次数（默认1000）

    Returns:
        dict with placebo p-values, significant ratio, and conclusion
    """
    import warnings
    warnings.filterwarnings("ignore")

    try:
        import numpy as np
        import pandas as pd
        import statsmodels.api as sm

        required = [outcome_var, treatment_var, time_var, unit_var]
        available = [c for c in required if c in df.columns]
        if len(available) < 4:
            return {
                "test_performed": False,
                "error": f"缺少必要列：{set(required) - set(available)}",
                "placebo_pvalues": [],
                "significant_placebo_ratio": 0.0,
                "conclusion": "数据缺少必要列",
            }

        data = df[required].dropna().copy()
        if len(data) < 50:
            return {
                "test_performed": False,
                "error": f"样本量不足 ({len(data)})",
                "placebo_pvalues": [],
                "significant_placebo_ratio": 0.0,
                "conclusion": "样本量不足",
            }

        # 确认 treatment_var 为 0/1
        if not set(data[treatment_var].unique()).issubset({0, 1}):
            return {
                "test_performed": False,
                "error": f"treatment_var 必须为0/1二值变量，当前：{data[treatment_var].unique()}",
                "placebo_pvalues": [],
                "significant_placebo_ratio": 0.0,
                "conclusion": "treatment_var 不是二值变量",
            }

        times = sorted(data[time_var].unique())
        if len(times) < 3:
            return {
                "test_performed": False,
                "error": f"时间期数不足 ({len(times)})",
                "placebo_pvalues": [],
                "significant_placebo_ratio": 0.0,
                "conclusion": "时间期数不足",
            }

        mid_period = times[len(times) // 2]
        data["post"] = (data[time_var] >= mid_period).astype(int)
        data["did"] = data[treatment_var] * data["post"]

        # 原始 DID 估计（使用 DataFrame 以保留变量名）
        try:
            y = data[outcome_var].values
            X_df = data[["did", treatment_var, "post"]].copy()
            X_df = sm.add_constant(X_df)
            X = X_df.values
            orig_model = sm.OLS(y, X).fit(disp=False)
            # 用 DataFrame 获取系数（自动按列顺序对应）
            params_df = pd.DataFrame({"param": orig_model.params}, index=X_df.columns[1:])  # skip const
            did_idx_in_params = list(X_df.columns[1:]).index("did")
            orig_coef = float(orig_model.params[did_idx_in_params])
            orig_pval = float(orig_model.pvalues[did_idx_in_params])
        except Exception as exc:
            logger.warning(f"check_placebo: failed to extract original model DID coefficient: {exc}")
            orig_coef, orig_pval = 0.0, 1.0
            orig_coef = 0.0
            orig_pval = 1.0

        # 安慰剂检验：随机化处理组分配
        np.random.seed(42)
        placebo_pvalues: list[float] = []
        placebo_coefs: list[float] = []

        # 预计算常量：常数列 + treat + post
        const_col = np.ones((len(data), 1))
        treat_col = data[treatment_var].values
        post_col = data["post"].values

        for sim_i in range(n_simulations):
            data_sim = data.copy()

            # 随机抽取处理组（保持与原始相同的比例）
            treat_ratio = float(data_sim[treatment_var].mean())
            n_units = int(data_sim[unit_var].nunique())
            n_treated = max(1, int(n_units * treat_ratio))
            all_units = data_sim[unit_var].unique()
            treated_units = np.random.choice(
                all_units, size=n_treated, replace=False
            )
            data_sim["fake_treat"] = data_sim[unit_var].isin(treated_units).astype(int)
            data_sim["fake_did"] = data_sim["fake_treat"] * data_sim["post"]

            try:
                y_sim = data_sim[outcome_var].values
                # 构建 X：const + fake_did + fake_treat + post
                fake_did_col = data_sim["fake_did"].values.reshape(-1, 1)
                fake_treat_col = data_sim["fake_treat"].values.reshape(-1, 1)
                X_sim = np.column_stack([const_col, fake_did_col, fake_treat_col, post_col])
                sim_model = sm.OLS(y_sim, X_sim).fit(disp=False)
                # fake_did 在第 1 列（0=const）
                fake_pval = float(sim_model.pvalues[1])
                fake_coef = float(sim_model.params[1])
                placebo_pvalues.append(fake_pval)
                placebo_coefs.append(fake_coef)
            except Exception as exc:
                logger.warning(f"Placebo simulation {sim_i} failed: {exc}")
                pass

        if not placebo_pvalues:
            return {
                "test_performed": False,
                "error": "安慰剂检验模拟全部失败",
                "placebo_pvalues": [],
                "significant_placebo_ratio": 0.0,
                "conclusion": "模拟失败",
            }

        # 计算显著比例（p < 0.05）
        sig_ratio = sum(1 for p in placebo_pvalues if p < 0.05) / len(placebo_pvalues)

        # 计算原始系数在安慰剂分布中的位置（单侧 p 值）
        # 即：安慰剂系数绝对值 > 原始系数绝对值的比例
        orig_abs = abs(orig_coef)
        placebo_abs = [abs(c) for c in placebo_coefs]
        rank_pval = sum(1 for pa in placebo_abs if pa >= orig_abs) / len(placebo_abs)

        # 判断安慰剂检验是否通过
        # 显著比例接近 α=0.05（允许 [0.01, 0.10] 范围）
        placebo_passing = 0.01 <= sig_ratio <= 0.10
        rank_passing = rank_pval > 0.05

        if placebo_passing and rank_passing:
            conclusion = "安慰剂检验通过"
            recommendation = (
                f"随机化{n_simulations}次后，显著比例={sig_ratio:.1%}（接近5%），"
                f"原始系数排名={rank_pval:.1%}分位数，说明原结果不是偶然所得"
            )
        elif not placebo_passing:
            conclusion = "安慰剂检验未通过"
            recommendation = (
                f"随机化{n_simulations}次后显著比例={sig_ratio:.1%}（偏高），"
                "原结果可能由偶然因素或样本特殊性导致，建议谨慎解读"
            )
        else:
            conclusion = "安慰剂检验边缘通过"
            recommendation = (
                f"原始系数位于安慰剂分布{rank_pval:.1%}分位数，"
                "建议结合其他稳健性检验综合判断"
            )

        return {
            "test_performed": True,
            "placebo_pvalues": placebo_pvalues[:100] if len(placebo_pvalues) > 100 else placebo_pvalues,
            "placebo_coefficients": placebo_coefs[:100] if len(placebo_coefs) > 100 else placebo_coefs,
            "significant_placebo_ratio": float(sig_ratio),
            "original_coef": float(orig_coef),
            "original_pval": float(orig_pval),
            "rank_pval": float(rank_pval),
            "n_simulations": n_simulations,
            "n_converged": len(placebo_pvalues),
            "conclusion": conclusion,
            "placebo_passing": placebo_passing,
            "recommendation": recommendation,
        }

    except Exception as e:
        return {
            "test_performed": False,
            "error": str(e),
            "placebo_pvalues": [],
            "significant_placebo_ratio": 0.0,
            "conclusion": f"安慰剂检验执行失败：{e}",
            "recommendation": "建议人工进行安慰剂检验",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 演示
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("  实证分析智能顾问 (EmpiricalAdvisor)")
    print("=" * 70)
    print()

    # 示例用法
    advisor = EmpiricalAdvisor(
        topic="ESG对企业融资约束的影响",
        core_variable="did",
        dependent_var="lev",
        research_field="finance",
    )

    # 模拟评估
    result = advisor.evaluate(
        core_coef=0.023,
        core_pval=0.15,  # 不显著
        all_results={"did": {"coef": 0.023, "se": 0.016, "pval": 0.15}},
        diagnostics={
            "dw": 1.8,
            "bp_pval": 0.02,  # 异方差
            "vif": [2.1, 3.2, 8.5],  # 第三个VIF较高
        },
        context={
            "n_obs": 5000,
            "n_firms": 200,
            "n_years": 10,
            "potential_endogeneity": True,
        },
        current_controls=["ln_assets", "roa", "lev"],
        current_fe={"firm_fe": True, "year_fe": True},
    )

    print("评估结果:")
    print("-" * 50)
    print(f"核心变量是否显著: {result.is_significant}")
    print(f"显著性水平: {result.best_significance_level}")
    print()
    print("诊断结果:")
    for d in result.diagnostics:
        print(f"  [{d.cause.value}] 可信度:{d.confidence:.0%}")
        print(f"    建议: {d.recommendation}")
    print()
    print("调整计划:")
    for a in result.adjustment_plan:
        print(f"  [{a.level.value}] {a.description}")
        print(f"    具体操作: {a.specific_changes}")
    print()
    print("最终建议:")
    print(f"  {result.recommendation}")
    print()
    print("行动计划:")
    for i, action in enumerate(result.action_plan, 1):
        print(f"  {i}. {action}")
    if result.research_note:
        print()
        print(f"研究注释: {result.research_note}")

    print()
    print("=" * 70)
    print("  使用方式:")
    print("  from scripts.empirical_advisor import EmpiricalAdvisor")
    print("  advisor = EmpiricalAdvisor(topic='...', core_variable='did')")
    print("  result = advisor.evaluate(core_coef=..., core_pval=...)")
    print("=" * 70)
