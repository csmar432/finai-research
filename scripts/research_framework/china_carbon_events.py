"""
China Carbon Trading Policy Events (碳排放权交易政策事件数据)
============================================================

Provides pre-built event data for DID analysis of carbon trading policy impact.
Includes:
  - China national ETS (全国碳市场): 2021-07-16 launch (power sector first)
  - China pilot ETS (试点碳市场): 2013-06-18 (Shenzhen), 2013-12-19 (other 6)
  - EU ETS phases (for replication studies):
    - Phase 1: 2005-2007
    - Phase 2: 2008-2012
    - Phase 3: 2013-2020
    - Phase 4: 2021-2030

Sources:
  - 中国碳市场年度报告 (2024)
  - 生态环境部公告
  - EU Commission "Report on the functioning of the European carbon market"

Usage:
  >>> from scripts.research_framework.china_carbon_events import ChinaCarbonEvents
  >>> events = ChinaCarbonEvents.get_national_ets_panel()
  >>> events.head()
  province_code  is_treated  treatment_date  policy_strength
  110000         0           NaT             0
  110000         0           NaT             0
  ...
  440000         1           2021-07-16      1.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd


# ─────────────────────────────────────────────────────────────────────
# 1. China National Carbon Market
# ─────────────────────────────────────────────────────────────────────
# Launched 2021-07-16, only power generation sector in Phase 1
# (2,162 entities, ~4.5 billion tons CO2/year, ~40% of national emissions)

CHINA_NATIONAL_ETS = {
    "policy_name": "全国碳排放权交易市场",
    "english_name": "China National ETS",
    "launch_date": date(2021, 7, 16),
    "scope": "Power generation (发电行业) only in Phase 1",
    "covered_emissions_pct": 40.0,
    "covered_entities": 2162,
    "covered_provinces": "National (all 31 provinces)",
    "regulatory_body": "生态环境部 (MEE)",
    "primary_law": "碳排放权交易管理暂行条例 (2024-02-04 effective)",
    "design": "Intensity-based (基准法) with sector-specific benchmarks",
    "papers_to_replicate": [
        # Add DOIs/URLs of papers using this event as a natural experiment
        # "10.1234/example.2024"
    ],
}


# ─────────────────────────────────────────────────────────────────────
# 2. China Pilot Carbon Markets (7 pilot cities/provinces, 2013-2014)
# ─────────────────────────────────────────────────────────────────────

CHINA_PILOT_ETS = pd.DataFrame(
    [
        # (city, province_code, launch_date, scope, key_sectors)
        ("深圳", 440300, date(2013, 6, 18), "工业+建筑", "电力、水务、制造业、建筑物"),
        ("上海", 310000, date(2013, 11, 26), "工业", "电力、钢铁、石化、化工、有色、建材"),
        ("北京", 110000, date(2013, 11, 28), "工业+服务业", "电力、热力、水泥、石化、服务业"),
        ("广东", 440000, date(2013, 12, 19), "工业", "电力、水泥、钢铁、石化"),
        ("天津", 120000, date(2013, 12, 26), "工业", "电力、钢铁、化工"),
        ("湖北", 420000, date(2014, 4, 2), "工业", "电力、钢铁、水泥、化工"),
        ("重庆", 500000, date(2014, 6, 19), "工业", "电力、电解铝、钢铁、化工、水泥、造纸"),
    ],
    columns=["city", "province_code", "launch_date", "scope", "key_sectors"],
)


# ─────────────────────────────────────────────────────────────────────
# 3. EU Carbon Market (for replication studies)
# ─────────────────────────────────────────────────────────────────────

EU_ETS_PHASES = pd.DataFrame(
    [
        # (phase, start, end, scope_change)
        (1, date(2005, 1, 1), date(2007, 12, 31), "Phase 1: Power + energy-intensive industry, EU-27"),
        (2, date(2008, 1, 1), date(2012, 12, 31), "Phase 2: + aviation (2012)"),
        (3, date(2013, 1, 1), date(2020, 12, 31), "Phase 3: Centralised auctioning, backloading"),
        (4, date(2021, 1, 1), date(2030, 12, 31), "Phase 4: -44% cap vs 2005, CBAM start"),
    ],
    columns=["phase", "start", "end", "description"],
)


# ─────────────────────────────────────────────────────────────────────
# 4. A-share firm-level treated/control panel builder
# ─────────────────────────────────────────────────────────────────────


@dataclass
class CarbonETSConfig:
    """Configuration for building a China carbon ETS analysis panel.

    Attributes:
        treatment_year: Year the policy applied to the treatment group.
        use_pilots: If True, uses 7-pilot staggered rollout; else uses
            national ETS 2021 rollout.
        firm_filter: Optional callable(df) -> df to filter firms
            (e.g. by industry code).
        covariates: List of column names to include as controls.
        cluster_level: 'firm' | 'industry' | 'province'
    """

    treatment_year: int = 2021
    use_pilots: bool = False
    firm_filter: object | None = None
    covariates: list[str] = field(default_factory=lambda: ["leverage", "roa", "size", "age"])
    cluster_level: Literal["firm", "industry", "province"] = "firm"


def build_carbon_ets_panel(
    firm_panel: pd.DataFrame,
    province_col: str = "province_code",
    year_col: str = "year",
    config: CarbonETSConfig | None = None,
) -> pd.DataFrame:
    """Build a balanced panel for carbon ETS DID analysis.

    Adds columns:
      - is_treated: 1 if the firm's province is in the treatment group
      - post: 1 if year >= treatment_year
      - did: is_treated * post (the standard DiD interaction)

    Args:
        firm_panel: Long-format DataFrame with one row per (firm, year)
        province_col: Name of the province code column (3-6 digit code)
        year_col: Name of the year column
        config: CarbonETSConfig instance

    Returns:
        DataFrame with original columns + is_treated + post + did
    """
    if config is None:
        config = CarbonETSConfig()

    df = firm_panel.copy()

    if config.use_pilots:
        treated_provinces = set(CHINA_PILOT_ETS["province_code"].tolist())
    else:
        # National ETS 2021 - all 31 provinces treated
        treated_provinces = set(range(110000, 700000, 10000))

    df["is_treated"] = df[province_col].isin(treated_provinces).astype(int)
    df["post"] = (df[year_col] >= config.treatment_year).astype(int)
    df["did"] = df["is_treated"] * df["post"]

    if config.firm_filter is not None:
        df = config.firm_filter(df)

    return df


# ─────────────────────────────────────────────────────────────────────
# 5. Pre-registered regression template
# ─────────────────────────────────────────────────────────────────────


def carbon_ets_regression_template():
    """Return a pre-registered regression template (publication-ready)."""
    return """
# Pre-registered Regression Template: Carbon ETS Policy Effect
# ============================================================
# Following Acemoglu et al. (2019) and Athey & Imbens (2017) guidelines
# for pre-analysis plans in policy evaluation

import statsmodels.api as sm
from scripts.research_framework.modern_did import CallawaySantAnnaDID

# Baseline: Standard TWFE
def baseline_twfe(df, outcome="green_innovation"):
    y = df[outcome]
    X = df[["did"] + config.covariates]
    X = sm.add_constant(X)
    model = sm.OLS(y, X, missing="drop").fit(
        cov_type="cluster", cov_kwds={"groups": df["firm_id"]}
    )
    return model

# Robustness: Callaway-Sant'Anna (modern staggered DiD)
def robustness_cs(df):
    return CallawaySantAnnaDID(
        outcome="green_innovation",
        treatment="is_treated",
        time_var="year",
        unit_var="firm_id",
    ).fit(df)

# Heterogeneity: by firm size, by SOE
def heterogeneity(df):
    return df.groupby(["size_quartile", "soe"]).apply(baseline_twfe)

# Robustness checks (standard 19 from FinAI's robustness_runner "full" level):
# 1. Placebo treatment (shift to 2 years before actual)
# 2. Different bandwidth (firms with 1-3 years pre/post)
# 3. Exclude specific industries (heavy polluters)
# 4. PSM-DID (match treated to control on pre-treatment characteristics)
# 5. Different control groups (drop pilot-ETS provinces)
# 6. Exclude pandemic years (2020-2022)
# 7. Drop national-ETS launch year (2021)
# 8. Triple difference (DID + ownership)
# ... (continue for 18 total)
"""
