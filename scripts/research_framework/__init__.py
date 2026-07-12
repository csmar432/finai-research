"""
research_framework - Generic academic paper generation framework.

Module structure:
  __init__.py             — Re-exports the public API
  base.py                 — Shared DataSource enum and ProvenanceTracker
  data_fetcher.py         — MCP data acquisition with fallback chains
  a_share_variables.py     — A-share specialized variables (margin/north-flow/ESG/...)
  policy_database.py       — Chinese policy experiment database (2008-2024, 23 policies)
  fin_charts.py           — Professional financial chart factory (20+ chart types)
  data_validator.py        — ProvinceDataValidator for provincial data validation
  regression_engine.py     — DID/OLS regressions with automatic DOF checking
  report_generator.py     — LaTeX + Word (.docx) output with embedded tables
  pipeline.py             — Main CLI entry point (check_dof / run_did / main)
  enhanced_pipeline.py    — Extended pipeline with modern_did / latex_diff / self_evolution
  diagnostic_reporter.py  — Automatic diagnostic decision engine (PASS/WARN/FAIL)
  iv_panel.py             — Panel IV/GMM via linearmodels (IV/2SLS/Arellano-Bond/Fama-MacBeth)
  journal_templates_multilang.py — Multi-language journal templates (EN/JP/DE)
  kob_decomposition.py    — Kitagawa-Oaxaca-Blinder wage decomposition
  leamer_sensitivity.py   — Leamer sensitivity + Eberstein-Magnac + OP/LP + contagion/spillover
  prisma_compliance.py   — PRISMA 2020 systematic review compliance engine
  provenance_rag.py       — Provenance-enhanced RAG for empirical paper retrieval
  robustness_runner.py    — Automated robustness test runner (15+ test types + Oster Bounds)
  vuong_kob.py           — Vuong non-nested test + Kitagawa-Oaxaca-Blinder decomposition
  vuong_test.py          — English wrappers for vuong_kob (VuongTest / ClarkeTest)
  finance_sensitivity.py  — Advanced sensitivity: OLS-PLS / OP-LP / contagion / spillover
  synthetic_control.py    — Synthetic Control Method (Abadie et al. 2010/2015/2021)
  modern_did.py           — 13+ modern DiD estimators (CS/S&A/BJS/Gardner/dCdH) + HTE extension
  rdd.py                 — Sharp/Fuzzy RDD with IK/CCT/MSED bandwidth selection
  spatial_regression.py   — SAR/SEM/SDM + spatial panel (RE/FE)
  local_projections_did.py — Local Projections DiD (Jordà 2005, LP-based IRF)
  triple_diff_did.py      — Triple DiD + Synthetic DiD (Arkhangelsky et al. 2021)
  panel_quantile_regression.py — Panel Quantile Regression (Canay 2011, Koenker 2004)
  interactive_fixed_effects.py — IFE (Bai 2009) + CCE (Bai & Ng 2013)
  synthetic_did.py        — Synthetic DiD with placebo/conformal inference
  panel_threshold_regression.py — Panel Threshold Regression (Hansen 2000) + bootstrap
  mediation_test.py       — Causal mediation analysis (Baron-Kenny/Sobel/Bootstrap/JointSig)
  a_share_firm_controls.py — A-share firm-level control variables catalog (FirmControl + helpers)
  china_carbon_events.py   — China carbon ETS pilot panel builder + baseline/robustness templates
  china_policy_events.py   — China policy event database (ChinaPolicyEvent catalog for staggered DID)

  # v1.8.1 new modules
  panel_var.py            — Panel VAR (Abrigo & Love 2016) + IRF/FEVD/Granger causality
  discrete_choice.py       — Logit/Probit/Ordered Logit/Negative Binomial
  volatility_models.py     — GARCH/GJR-GARCH/EGARCH + Realized Volatility + HAR
  time_varying_models.py   — TVP-VAR (Nakajima 2010) + DCC-GARCH (Engle 2002)
  survival_analysis.py     — Cox PH / Kaplan-Meier / Nelson-Aalen / Fine-Gray
  causal_ml.py            — Causal Forest / Double ML (DML) / X-Learner / T-Learner
  panel_cointegration.py  — Pedroni/Kao/Westerlund cointegration + Panel ECM
  green_bond_model.py     — Green bond premium (greenium) / ESG factor decomposition / CAR event study
  options_iv_surface.py  — Implied volatility surface from options chains + BS IV solver + Greeks

Usage:
    from scripts.research_framework import (
        ProvenanceTracker, DataSource,
        RegressionEngine, ReportGenerator,
        DataFetcher, ProvinceDataValidator,
        AShareVariableFetcher, AShareVariable,
        PolicyDatabase, FinancialChartFactory,
    )
    # Advanced econometrics
    from scripts.research_framework.spatial_regression import SpatialRegressionEngine
    from scripts.research_framework.local_projections_did import LocalProjectionsDIDEngine
    from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
    from scripts.research_framework.panel_quantile_regression import PanelQuantileRegression
    from scripts.research_framework.interactive_fixed_effects import InteractiveFixedEffects
    from scripts.research_framework.synthetic_did import SyntheticDiDEngine
    from scripts.research_framework.synthetic_control import SyntheticControlEngine
    from scripts.research_framework.rdd import RDDEngine
    from scripts.research_framework.modern_did import ModernDiDEngine, CSDIDHTE
    from scripts.research_framework.panel_threshold_regression import PanelThresholdRegression
    # v1.8.1 new
    from scripts.research_framework.panel_var import PanelVAR
    from scripts.research_framework.discrete_choice import DiscreteChoiceModel
    from scripts.research_framework.volatility_models import GARCHModel
    from scripts.research_framework.time_varying_models import TVPVAR, DCCGARCH
    from scripts.research_framework.survival_analysis import CoxPHModel
    from scripts.research_framework.causal_ml import CausalForest, DoubleML
    from scripts.research_framework.panel_cointegration import PanelCointegrationTest

Note:
    DataSource and ProvenanceTracker are defined in base.py to ensure a single
    source of truth across all framework modules.
"""

# Provenance & data sources (shared via base.py)
from .base import DataSource, ProvenanceTracker, DataProvenance

# Data fetching
from .data_fetcher import DataFetcher, MCPCallError, ProxyVariableBuilder

# A-share specialized variables
from .a_share_variables import (
    AShareVariableFetcher,
    AShareVariable,
    VariableAvailability,
    VariableResult,
    VariableSpec,
    VARIABLE_REGISTRY,
)

# Policy experiment database
from .policy_database import PolicyDatabase, load_policy_database

# Financial charts
from .fin_charts import FinancialChartFactory, ChartConfig, CHART_PRESETS

# Regression
from .regression_engine import RegressionEngine, _extract, _fmt

# Report generation
from .report_generator import (
    ReportGenerator,
    TableFormatter,
)

# Data validation
from .data_validator import ProvinceDataValidator

# Pipeline
from .pipeline import (
    main,
    run_did,
    check_dof,
    extract,
    fmt_coef,
    did_to_latex,
)

# Enhanced pipeline
from .enhanced_pipeline import EnhancedPipeline, PipelineContext

# Diagnostic reporter
from .diagnostic_reporter import (
    DiagnosticReporter,
    DiagnosticDecision,
    DiagnosticCheck,
    DiagnosticReport,
)

# Panel IV / GMM
from .iv_panel import (
    IVPanel,
    DynamicGMM,
    FamaMacBeth,
    PanelDiagnostic,
    DynamicPanelDiagnostics,
)

# Multi-language journal templates
from .journal_templates_multilang import (
    TemplateStyle,
    JournalTemplate,
    get_multilang_templates,
    get_template,
    list_multilang_templates,
    format_latex_preamble,
)

# KOB decomposition
from .kob_decomposition import (
    KOBDecomposition,
    KOBResult,
    OaxacaBlinderDecomposition,
    OaxacaResult,
    wage_decomposition,
    credit_gap_decomposition,
    investment_decomposition,
    plot_decomposition,
    to_latex,
)

# Leamer sensitivity
from .leamer_sensitivity import (
    LeamerSensitivity,
    LeamerResult,
    EbersteinMagnacSensitivity,
    BoundingResult,
    OlleyPakesEstimator,
    LevinsohnPetrinEstimator,
    ContagionTest,
    SpilloverIndex,
    CreditRiskSensitivity,
    test_ar2,
    DynamicPanelDiagnostics as LeamerDynamicPanelDiagnostics,
)

# Finance sensitivity (OLS-PLS sensitivity)
from .finance_sensitivity import OLSPLSSensitivity

# PRISMA compliance
from .prisma_compliance import (
    PRISMAStage,
    PRISMAStageStatus,
    GRADEQuality,
    SearchStrategy,
    ScreeningRecord,
    PICOExtract,
    ROBAssessment,
    PRISMAFlowchart,
    PRISMAReport,
)

# Provenance RAG
from .provenance_rag import (
    ProvenanceRAG,
    ProvenanceResult,
    NumberWithContext,
    NumberExtractor,
)

# ─────────────────────────────────────────────────────────────────────────────
# v1.8.1 NEW MODULES — 7 new modules + 2 existing modules with new extensions
# ─────────────────────────────────────────────────────────────────────────────

# Panel VAR (Abrigo & Love 2016)
try:
    from .panel_var import PanelVAR, PanelVARResult
except ImportError:
    PanelVAR = None
    PanelVARResult = None

# Discrete choice models (Logit/Probit/Ordered)
try:
    from .discrete_choice import (
        DiscreteChoiceModel, DiscreteChoiceSuite,
        DiscreteChoiceResult, MarginalEffectsResult,
    )
except ImportError:
    DiscreteChoiceModel = None
    DiscreteChoiceSuite = None
    DiscreteChoiceResult = None
    MarginalEffectsResult = None

# GARCH & volatility models
try:
    from .volatility_models import (
        GARCHModel, RealizedVolatility, VolatilitySuite,
        VolatilityResult, HARModel,
    )
except ImportError:
    GARCHModel = None
    RealizedVolatility = None
    VolatilitySuite = None
    VolatilityResult = None
    HARModel = None

# TVP-VAR & DCC-GARCH
try:
    from .time_varying_models import (
        TVPVAR, DCCGARCH, TVPVARResult, DCCGARCHResult,
    )
except ImportError:
    TVPVAR = None
    DCCGARCH = None
    TVPVARResult = None
    DCCGARCHResult = None

# Survival analysis (Cox/KM)
try:
    from .survival_analysis import (
        CoxPHModel, KaplanMeier, SurvivalSuite, SurvivalResult,
    )
except ImportError:
    CoxPHModel = None
    KaplanMeier = None
    SurvivalSuite = None
    SurvivalResult = None

# Causal ML (Causal Forest / DML)
try:
    from .causal_ml import (
        CausalForest, DoubleML, CausalMLSuite,
        CausalMLResult, HeterogeneityReport,
    )
except ImportError:
    CausalForest = None
    DoubleML = None
    CausalMLSuite = None
    CausalMLResult = None
    HeterogeneityReport = None

# Panel cointegration (Pedroni/Kao/Westerlund)
try:
    from .panel_cointegration import (
        PanelCointegrationTest, PanelECM,
        CointegrationResult, ECMResult,
    )
except ImportError:
    PanelCointegrationTest = None
    PanelECM = None
    CointegrationResult = None
    ECMResult = None

# ── v1.8.4 NEW: Green bond premium + ESG factor models ──
try:
    from .green_bond_model import GreenBondFactorModel, GreenBondResult, GreenBondESGModel
except ImportError:
    GreenBondFactorModel = None
    GreenBondResult = None
    GreenBondESGModel = None

# ── v1.8.4 NEW: Options implied volatility surface ──
try:
    from .options_iv_surface import (
        IVSurfaceBuilder, IVSurfaceResult,
        IVSurfaceModel, ImpliedVolatilityEngine,
    )
except ImportError:
    IVSurfaceBuilder = None
    IVSurfaceResult = None
    IVSurfaceModel = None
    ImpliedVolatilityEngine = None

# Robustness runner (v1.8.1+: includes Oster Bounds)
from .robustness_runner import (
    RobustnessRunner,
    RobustnessTest,
    RobustnessReport,
    oster_bounds,
)

# Modern DID (v1.8.1+: includes HTE extension)
try:
    from .modern_did import ModernDiDEngine, CSDIDHTE, cs_did_hte
except ImportError:
    ModernDiDEngine = None
    CSDIDHTE = None
    cs_did_hte = None

# Synthetic control
from .synthetic_control import SyntheticControlEngine, SCEstimationResult

# Panel threshold regression (Hansen 2000)
from .panel_threshold_regression import (
    PanelThresholdRegression,
    ThresholdResult,
    ThresholdModel,
)

# Mediation analysis
from .mediation_test import MediationTest, MediationResult

# ── v1.8.6 NEW: Data/control catalogs (lightweight wrappers) ──
try:
    from .a_share_firm_controls import (
        FirmControl, list_controls, get_control, compute_controls,
    )
except ImportError:
    FirmControl = None
    list_controls = None
    get_control = None
    compute_controls = None

try:
    from .china_carbon_events import (
        CarbonETSConfig, build_carbon_ets_panel,
        carbon_ets_regression_template,
    )
except ImportError:
    CarbonETSConfig = None
    build_carbon_ets_panel = None
    carbon_ets_regression_template = None

try:
    from .china_policy_events import (
        ChinaPolicyEvent, get_event as get_china_policy_event,
        list_events as list_china_policy_events,
    )
except ImportError:
    ChinaPolicyEvent = None
    get_china_policy_event = None
    list_china_policy_events = None

# Vuong non-nested hypothesis test + Clarke test
from .vuong_test import (
    VuongTest,
    VuongResult,
    vuong_did_vs_rdd,
    ClarkeTest,
    ClarkeTestEN,  # backward-compat alias
    vuong_different_controls,
    vuong_different_samples,
    vuong_linear_vs_logit,
)

# ─────────────────────────────────────────────────────────────────────────────
__all__ = [
    # Provenance
    "DataSource", "ProvenanceTracker", "DataProvenance",
    # Data
    "DataFetcher", "ProxyVariableBuilder", "MCPCallError",
    # A-share variables
    "AShareVariableFetcher", "AShareVariable", "VariableAvailability",
    "VariableResult", "VariableSpec", "VARIABLE_REGISTRY",
    # Policy database
    "PolicyDatabase", "load_policy_database",
    # Charts
    "FinancialChartFactory", "ChartConfig", "CHART_PRESETS",
    # Regression
    "RegressionEngine", "_extract", "_fmt",
    # Report
    "ReportGenerator", "TableFormatter",
    # Validation
    "ProvinceDataValidator",
    # Pipeline
    "main", "run_did", "check_dof", "extract", "fmt_coef", "did_to_latex",
    # Enhanced pipeline
    "EnhancedPipeline", "PipelineContext",
    # Diagnostic reporter
    "DiagnosticReporter", "DiagnosticDecision", "DiagnosticCheck", "DiagnosticReport",
    # Panel IV / GMM
    "IVPanel", "DynamicGMM", "FamaMacBeth", "PanelDiagnostic", "DynamicPanelDiagnostics",
    # Multi-language journal templates
    "TemplateStyle", "JournalTemplate", "get_multilang_templates",
    "get_template", "list_multilang_templates", "format_latex_preamble",
    # KOB decomposition
    "KOBDecomposition", "KOBResult",
    "OaxacaBlinderDecomposition", "OaxacaResult",
    "wage_decomposition", "credit_gap_decomposition", "investment_decomposition",
    "plot_decomposition", "to_latex",
    # Leamer sensitivity
    "LeamerSensitivity", "LeamerResult",
    "EbersteinMagnacSensitivity", "BoundingResult",
    "OlleyPakesEstimator", "LevinsohnPetrinEstimator",
    "ContagionTest", "SpilloverIndex", "CreditRiskSensitivity",
    "test_ar2", "LeamerDynamicPanelDiagnostics",
    # PRISMA compliance
    "PRISMAStage", "PRISMAStageStatus", "GRADEQuality",
    "SearchStrategy", "ScreeningRecord", "PICOExtract",
    "ROBAssessment", "PRISMAFlowchart", "PRISMAReport",
    # Provenance RAG
    "ProvenanceRAG", "ProvenanceResult", "NumberWithContext", "NumberExtractor",
    # Robustness runner (v1.8.1+: includes Oster Bounds)
    "RobustnessRunner", "RobustnessTest", "RobustnessReport",
    "oster_bounds",
    # Modern DID HTE extension (v1.8.1+)
    "ModernDiDEngine", "CSDIDHTE", "cs_did_hte",
    # Synthetic control
    "SyntheticControlEngine", "SCEstimationResult",
    # Panel threshold regression
    "PanelThresholdRegression", "ThresholdResult", "ThresholdModel",
    # Mediation analysis
    "MediationTest", "MediationResult",
    # ── v1.8.1 NEW: Panel VAR ──
    "PanelVAR", "PanelVARResult",
    # ── v1.8.1 NEW: Discrete choice ──
    "DiscreteChoiceModel", "DiscreteChoiceSuite",
    "DiscreteChoiceResult", "MarginalEffectsResult",
    # ── v1.8.1 NEW: Volatility models ──
    "GARCHModel", "RealizedVolatility", "VolatilitySuite",
    "VolatilityResult", "HARModel",
    # ── v1.8.1 NEW: Time-varying models ──
    "TVPVAR", "DCCGARCH", "TVPVARResult", "DCCGARCHResult",
    # ── v1.8.1 NEW: Survival analysis ──
    "CoxPHModel", "KaplanMeier", "SurvivalSuite", "SurvivalResult",
    # ── v1.8.1 NEW: Causal ML ──
    "CausalForest", "DoubleML", "CausalMLSuite", "CausalMLResult", "HeterogeneityReport",
    # ── v1.8.1 NEW: Panel cointegration ──
    "PanelCointegrationTest", "PanelECM", "CointegrationResult", "ECMResult",
    # ── v1.8.4 NEW: Green bond premium ──
    "GreenBondFactorModel", "GreenBondResult", "GreenBondESGModel",
    # ── v1.8.4 NEW: Options IV surface ──
    "IVSurfaceBuilder", "IVSurfaceResult", "IVSurfaceModel", "ImpliedVolatilityEngine",
    # ── Vuong non-nested hypothesis test + Clarke test ──
    "VuongTest", "VuongResult", "vuong_did_vs_rdd",
    "ClarkeTest", "ClarkeTestEN",
    "vuong_different_controls", "vuong_different_samples", "vuong_linear_vs_logit",
    # ── Finance sensitivity ──
    "OLSPLSSensitivity",
    # ── v1.8.6 NEW: Data/control catalogs ──
    "FirmControl", "list_controls", "get_control", "compute_controls",
    "CarbonETSConfig", "build_carbon_ets_panel",
    "carbon_ets_regression_template",
    "ChinaPolicyEvent", "get_china_policy_event", "list_china_policy_events",
]
