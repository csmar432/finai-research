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
  report_generator.py      — LaTeX + Word (.docx) output with embedded tables
  pipeline.py             — Main CLI entry point
  modern_did.py          — 13+ modern DiD estimators (CS/S&A/BJS/Gardner/dCdH)
  synthetic_control.py    — Synthetic Control (Abadie et al. 2010/2015, augmented SC)
  rdd.py                 — Sharp/Fuzzy RDD with IK/CCT/MSED bandwidth selection
  spatial_regression.py   — SAR/SEM/SDM + spatial panel (RE/FE)
  local_projections_did.py — Local Projections DiD (Jorda 2005, LP-based IRF)
  triple_diff_did.py     — Triple DiD + Synthetic DiD (Arkhangelsky et al. 2021)
  panel_quantile_regression.py — Panel Quantile Regression (Canay 2011, Koenker 2004)
  interactive_fixed_effects.py — IFE (Bai 2009) + CCE (Bai & Ng 2013)
  synthetic_did.py        — Synthetic DiD with placebo/conformal inference
  vuong_kob.py          — Vuong non-nested test + KOB decomposition
  leamer_sensitivity.py   — Leamer sensitivity + Eberstein-Magnac + OP/LP + contagion/spillover
  diagnostic_reporter.py  — Automatic diagnostic decision engine (PASS/WARN/FAIL)

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
    from scripts.research_framework.modern_did import ModernDiDEngine

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

__all__ = [
    # Provenance
    "DataSource", "ProvenanceTracker",
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
]
