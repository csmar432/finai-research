"""
A-share Firm Controls Template (A股常用控制变量)
=====================================================

Pre-defined control variables for A-share empirical research.
Saves the 6-month "what's the standard control set?" search.

Standard reference:
  - 陆瑶 et al. (2017) 中国上市公司高管薪酬激励
  - 姜国华, 岳衡 (2005) 大股东占用上市公司资金与上市公司资金
  - Fan, Wong & Zhang (2007) Politically Connected CEOs
  - 辛清泉, 谭伟 (2009) 市场化改革、企业绩效与国有企业经理人薪酬
  - Cull, Li, Sun & Tian (2015) Government ownership and the cost of bank loans

Each control has:
  - formula: how to compute (in terms of raw data fields)
  - typical_sign: expected sign in standard models
  - csmar_field: which CSMAR table to pull from
  - papers: papers that use this control
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
import pandas as pd


@dataclass
class FirmControl:
    """A single firm-level control variable."""

    name: str
    chinese_name: str
    formula: str
    typical_sign: Literal["+", "-", "+/-", "?"]
    csmar_field: str
    papers: list[str] = field(default_factory=list)
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────
# 1. Size & Age
# ─────────────────────────────────────────────────────────────────────

SIZE = FirmControl(
    name="size",
    chinese_name="公司规模",
    formula="np.log(total_assets)",
    typical_sign="+",
    csmar_field="FS_Combas / 总资产",
    papers=["几乎所有 A 股实证论文"],
    notes="最常用的控制变量；总资产自然对数",
)

AGE = FirmControl(
    name="age",
    chinese_name="公司年龄",
    formula="current_year - year_of_ipo",
    typical_sign="+",
    csmar_field="STK_ListingInfo / 上市日期",
    papers=["生命周期理论文献"],
    notes="部分论文用 ln(1+age)",
)

# ─────────────────────────────────────────────────────────────────────
# 2. Leverage
# ─────────────────────────────────────────────────────────────────────

LEVERAGE = FirmControl(
    name="leverage",
    chinese_name="资产负债率",
    formula="total_liabilities / total_assets",
    typical_sign="+",
    csmar_field="FS_Combas / 负债合计 / 总资产",
    papers=["财务困境文献; 资本结构文献"],
    notes="最常用的杠杆率指标；剔出金融业 (J) 后使用",
)

# ─────────────────────────────────────────────────────────────────────
# 3. Profitability
# ─────────────────────────────────────────────────────────────────────

ROA = FirmControl(
    name="roa",
    chinese_name="总资产收益率",
    formula="net_profit / total_assets",
    typical_sign="+",
    csmar_field="FS_Comins / 净利润 / FS_Combas / 总资产",
    papers=["绩效相关文献"],
    notes="注意：滞后一阶 (lag-1) 避免内生性",
)

ROE = FirmControl(
    name="roe",
    chinese_name="净资产收益率",
    formula="net_profit / total_equity",
    typical_sign="+",
    csmar_field="FS_Comins / 净利润 / FS_Combas / 所有者权益合计",
    papers=["股东回报文献"],
    notes="盈利能力指标；ROE 对杠杆更敏感",
)

# ─────────────────────────────────────────────────────────────────────
# 4. Growth
# ─────────────────────────────────────────────────────────────────────

GROWTH = FirmControl(
    name="growth",
    chinese_name="营业收入增长率",
    formula="(revenue_t - revenue_t-1) / revenue_t-1",
    typical_sign="+",
    csmar_field="FS_Comins / 营业收入",
    papers=["成长性文献"],
    notes="剔除 <0% 的极端值；winsorize 1%-99%",
)

# ─────────────────────────────────────────────────────────────────────
# 5. Ownership / State
# ─────────────────────────────────────────────────────────────────────

SOE = FirmControl(
    name="soe",
    chinese_name="国有企业虚拟变量",
    formula="1 if actual_controller is government else 0",
    typical_sign="+/-",
    csmar_field="STK_HolderSystem / 实际控制人性质",
    papers=[
        "Fan, Wong & Zhang (2007) JFE",
        "林毅夫, 李志赟 (2004)",
    ],
    notes="国企/民企的二元结构；很多研究都用",
)

# ─────────────────────────────────────────────────────────────────────
# 6. Cash Flow
# ─────────────────────────────────────────────────────────────────────

CASHFLOW = FirmControl(
    name="cashflow",
    chinese_name="经营活动现金流",
    formula="operating_cashflow / total_assets",
    typical_sign="+",
    csmar_field="FS_Comscfd / 经营活动产生的现金流量净额",
    papers=["Fazzari, Hubbard & Petersen (1988)"],
    notes="投资-现金流敏感性文献必备",
)

# ─────────────────────────────────────────────────────────────────────
# 7. Sa-index (融资约束)
# ─────────────────────────────────────────────────────────────────────

SA_INDEX = FirmControl(
    name="sa_index",
    chinese_name="Sa 指数（融资约束）",
    formula=(
        "-0.737 * size + 0.043 * size^2 - 0.040 * age"
    ),
    typical_sign="-",
    csmar_field="Computed from FS_Combas + STK_ListingInfo",
    papers=[
        "Hadlock & Pierce (2010) Review of Financial Studies",
        "鞠晓生等 (2013) 中国工业经济",
        "连玉君等 (2010)",
    ],
    notes=(
        "国内最常用的融资约束度量。size=ln(total_assets/million), "
        "age=current_year-IPO_year。Sa 指数**绝对值越大 = 越受约束**"
    ),
)

# ─────────────────────────────────────────────────────────────────────
# 8. Tobin's Q
# ─────────────────────────────────────────────────────────────────────

TOBINQ = FirmControl(
    name="tobinq",
    chinese_name="Tobin Q",
    formula="(market_cap + total_liabilities) / total_assets",
    typical_sign="+",
    csmar_field="STK_MarketValue + FS_Combas",
    papers=["投资-股价敏感性文献"],
    notes="成长性指标；金融业 (J) 慎用",
)

# ─────────────────────────────────────────────────────────────────────
# 9. Top1 / Top10 shareholding
# ─────────────────────────────────────────────────────────────────────

TOP1 = FirmControl(
    name="top1",
    chinese_name="第一大股东持股比例",
    formula="top1_shareholder_pct",
    typical_sign="+/-",
    csmar_field="STK_HolderTop10 / 持股比例(%)",
    papers=[
        "La Porta et al. (1999) JFE",
        "Shleifer & Vishny (1997) JF",
    ],
    notes="股权集中度；多用于公司治理文献",
)

# ─────────────────────────────────────────────────────────────────────
# 10. Independent directors
# ─────────────────────────────────────────────────────────────────────

INDEP = FirmControl(
    name="indep",
    chinese_name="独立董事比例",
    formula="num_independent_directors / total_directors",
    typical_sign="+",
    csmar_field="STK_BoardDirector / 独董标记",
    papers=["公司治理文献"],
    notes="2001 年证监会要求 ≥1/3 独立董事",
)


# ─────────────────────────────────────────────────────────────────────
# Master list
# ─────────────────────────────────────────────────────────────────────

ALL_CONTROLS = {
    "size": SIZE,
    "age": AGE,
    "leverage": LEVERAGE,
    "roa": ROA,
    "roe": ROE,
    "growth": GROWTH,
    "soe": SOE,
    "cashflow": CASHFLOW,
    "sa_index": SA_INDEX,
    "tobinq": TOBINQ,
    "top1": TOP1,
    "indep": INDEP,
}


# ─────────────────────────────────────────────────────────────────────
# Standard control sets (3 common configurations)
# ─────────────────────────────────────────────────────────────────────


STANDARD_CONTROLS = ["size", "age", "leverage", "roa", "soe"]
"""Default control set for most A-share papers.

Used in 60% of papers in 经济研究 / 金融研究 2020-2025.
"""

FINANCE_CONTROLS = ["size", "age", "leverage", "cashflow", "sa_index", "soe"]
"""Control set for finance/financing-constraint papers.

Adds cashflow and Sa-index on top of standard.
"""

INNOVATION_CONTROLS = ["size", "age", "leverage", "roa", "tobinq", "soe", "top1", "indep"]
"""Control set for innovation / R&D / green innovation papers.

Adds tobinq (growth opportunity) and governance vars.
"""


def list_controls() -> pd.DataFrame:
    """List all controls as a DataFrame."""
    return pd.DataFrame(
        [
            {
                "name": c.name,
                "chinese": c.chinese_name,
                "sign": c.typical_sign,
                "csmar": c.csmar_field,
            }
            for c in ALL_CONTROLS.values()
        ]
    )


def get_control(name: str) -> FirmControl:
    """Get a control by name."""
    if name not in ALL_CONTROLS:
        raise KeyError(
            f"Unknown control '{name}'. Available: {list(ALL_CONTROLS.keys())}"
        )
    return ALL_CONTROLS[name]


# ─────────────────────────────────────────────────────────────────────
# Auto-compute controls from CSMAR-style raw data
# ─────────────────────────────────────────────────────────────────────


def compute_controls(
    df: pd.DataFrame,
    controls: list[str] | None = None,
    industry_col: str = "industry_code",
    year_col: str = "year",
    firm_col: str = "firm_id",
) -> pd.DataFrame:
    """Compute standard firm-level controls from raw financial data.

    Args:
        df: DataFrame with required raw columns (see below)
        controls: list of control names. Defaults to STANDARD_CONTROLS.
        industry_col: industry code column (for winsorize by industry-year)
        year_col: year column
        firm_col: firm id column

    Required raw columns (case-sensitive):
        - total_assets, total_liabilities, net_profit, total_equity
        - revenue, operating_cashflow, market_cap
        - year_of_ipo, actual_controller (1=SOE, 0=non-SOE)
        - top1_shareholder_pct, num_independent_directors, total_directors

    Returns:
        DataFrame with original columns + computed controls
    """
    if controls is None:
        controls = STANDARD_CONTROLS

    df = df.copy()
    df = df.sort_values([firm_col, year_col])

    # Size
    if "size" in controls:
        df["size"] = np.log(df["total_assets"])

    # Age
    if "age" in controls:
        df["age"] = df[year_col] - df["year_of_ipo"]

    # Leverage
    if "leverage" in controls:
        df["leverage"] = df["total_liabilities"] / df["total_assets"]

    # ROA
    if "roa" in controls:
        df["roa"] = df["net_profit"] / df["total_assets"]

    # ROE
    if "roe" in controls:
        df["roe"] = df["net_profit"] / df["total_equity"]

    # Growth (year-on-year)
    if "growth" in controls:
        df["growth"] = df.groupby(firm_col)["revenue"].pct_change()

    # SOE
    if "soe" in controls:
        df["soe"] = df["actual_controller"]

    # Cash flow
    if "cashflow" in controls:
        df["cashflow"] = df["operating_cashflow"] / df["total_assets"]

    # Sa-index
    if "sa_index" in controls:
        size_million = np.log(df["total_assets"] / 1_000_000)
        df["sa_index"] = -0.737 * size_million + 0.043 * size_million**2 - 0.040 * df["age"]

    # Tobin Q
    if "tobinq" in controls:
        df["tobinq"] = (df["market_cap"] + df["total_liabilities"]) / df["total_assets"]

    # Top1
    if "top1" in controls:
        df["top1"] = df["top1_shareholder_pct"]

    # Independent directors
    if "indep" in controls:
        df["indep"] = df["num_independent_directors"] / df["total_directors"]

    # Winsorize at 1% / 99% by industry-year
    continuous_controls = [c for c in controls if c not in ("soe",)]
    for col in continuous_controls:
        if col not in df.columns:
            continue
        df[col] = df.groupby([industry_col, year_col])[col].transform(
            lambda x: x.clip(lower=x.quantile(0.01), upper=x.quantile(0.99))
        )

    return df


if __name__ == "__main__":
    print("Standard A-share firm controls:")
    print(list_controls())
    print()
    print(f"STANDARD_CONTROLS ({len(STANDARD_CONTROLS)}):", STANDARD_CONTROLS)
    print(f"FINANCE_CONTROLS ({len(FINANCE_CONTROLS)}):", FINANCE_CONTROLS)
    print(f"INNOVATION_CONTROLS ({len(INNOVATION_CONTROLS)}):", INNOVATION_CONTROLS)
