"""
Common China Policy Shocks (中国常见政策事件)
================================================

7 pre-built policy event datasets ready for staggered DID analysis.
All events are real policies with verifiable launch dates.

Each event provides:
  - launch_date: official start date
  - scope_dict: which provinces/industries are treated
  - covariates: recommended controls
  - example_papers: DOIs of published papers using this event
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class ChinaPolicyEvent:
    """A single China policy event ready for DID analysis."""

    name: str
    english_name: str
    launch_date: date
    scope: str
    treated_provinces: list[int]  # 6-digit province codes, or [] for national
    treated_industries: list[str]  # SW industry codes (2-digit), or [] for all
    expected_effect: str
    example_papers: list[str]
    data_sources: list[str]
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────
# Event 1: 营改增 (Replace Business Tax with VAT) — 2012-01-01 Shanghai pilot
# ─────────────────────────────────────────────────────────────────────
# Major tax reform: replaced business tax (营业税) with VAT (增值税)
# for transportation and some modern services. Rolled out to all provinces
# by 2013-08-01. Extended to construction/finance/real estate in 2016-05-01.

YING_GAI_ZENG = ChinaPolicyEvent(
    name="营改增",
    english_name="Replace Business Tax with VAT",
    launch_date=date(2012, 1, 1),
    scope=(
        "Shanghai pilot (2012-01-01), national rollout (2013-08-01), "
        "extended to construction/finance/real estate (2016-05-01)"
    ),
    treated_provinces=[310000],  # Shanghai (2012-01-01 only)
    treated_industries=[
        "G54",  # 道路运输业
        "G55",  # 水上运输业
        "G56",  # 航空运输业
        "G57",  # 管道运输业
        "G58",  # 装卸搬运和仓储业
        "G59",  # 邮政业
        "L72",  # 商务服务业
        "L73",  # 研究和试验发展
        "L74",  # 专业技术服务业
        "L75",  # 科技推广和应用服务业
    ],
    expected_effect=(
        "Reduce tax burden for service firms, increase specialisation, "
        "raise firm value (especially in transportation)"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.chieco.2018.04.008",  # 范子英, 2017
        # Add your own
    ],
    data_sources=["CSMAR", "Wind", "CNRDS"],
    notes=(
        "Three-stage rollout: 2012 (Shanghai), 2013 (national), 2016 (extended). "
        "Recommend three separate events for clean identification."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 2: 大气十条 (Air Pollution Action Plan) — 2013-09-10
# ─────────────────────────────────────────────────────────────────────
# China's first comprehensive air pollution control plan.
# Most affected: Beijing-Tianjin-Hebei (京津冀), Yangtze River Delta, Pearl River Delta

DAQI_SHI_TIAO = ChinaPolicyEvent(
    name="大气十条",
    english_name="Air Pollution Prevention and Control Action Plan",
    launch_date=date(2013, 9, 10),
    scope=(
        "National, but strict targets for Beijing-Tianjin-Hebei, "
        "Yangtze River Delta, Pearl River Delta"
    ),
    treated_provinces=[
        110000,  # 北京
        120000,  # 天津
        130000,  # 河北
        310000,  # 上海
        320000,  # 江苏
        330000,  # 浙江
        440000,  # 广东
    ],
    treated_industries=[
        "B06",  # 煤炭开采
        "C17",  # 纺织业
        "C22",  # 造纸及纸制品业
        "C25",  # 石油加工、炼焦及核燃料加工业
        "C26",  # 化学原料及化学制品制造业
        "C27",  # 医药制造业
        "C28",  # 化学纤维制造业
        "C30",  # 非金属矿物制品业 (cement, glass)
        "C31",  # 黑色金属冶炼及压延加工业 (steel)
        "C32",  # 有色金属冶炼及压延加工业
        "C44",  # 电力、热力生产和供应业
    ],
    expected_effect=(
        "Force heavy polluters to upgrade equipment; reduce PM2.5 by 25%; "
        "may improve green innovation among listed firms"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.jeem.2018.06.002",  # Chen et al.
    ],
    data_sources=["CSMAR", "CNRDS (environmental patents)"],
    notes=(
        "Strong policy with measurable outcomes. "
        "Recommend constructing PM2.5 county-level data as continuous treatment."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 3: 河长制 (River Chief System) — 2016-12-11 (中央办公厅发文)
# ─────────────────────────────────────────────────────────────────────
# Assigns personal responsibility to officials for river water quality.

HE_ZHANG_ZHI = ChinaPolicyEvent(
    name="河长制",
    english_name="River Chief System",
    launch_date=date(2016, 12, 11),
    scope="National rollout starting with Wuxi (2007), Jiangxi (2014), then national (2016)",
    treated_provinces=[
        320000,  # 江苏 (Wuxi 2007)
        360000,  # 江西 (2014)
        # National: 2016-12-11 onwards, all 31 provinces
    ],
    treated_industries=[
        "C17",  # 纺织业
        "C22",  # 造纸
        "C26",  # 化学原料
        "C30",  # 非金属矿物 (cement)
        "C44",  # 电力
        "D46",  # 水的生产和供应业
    ],
    expected_effect=(
        "Reduce water pollution; force upstream firms to upgrade water treatment; "
        "may harm small chemical firms disproportionately"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.jeem.2020.102408",
    ],
    data_sources=["CSMAR", "CNRDS (water pollution)"],
    notes=(
        "Staggered rollout: Wuxi 2007, Jiangxi 2014, national 2016-12-11. "
        "Use Callaway-Sant'Anna for clean identification."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 4: 资管新规 (Asset Management New Rules) — 2018-04-27
# ─────────────────────────────────────────────────────────────────────
# Unified regulation for asset management products.
# Major impact on banks' shadow banking, channel business.

ZI_GUAN_XIN_GUI = ChinaPolicyEvent(
    name="资管新规",
    english_name="Asset Management New Rules",
    launch_date=date(2018, 4, 27),
    scope="National (all financial institutions)",
    treated_provinces=[],
    treated_industries=[
        "J66",  # 货币金融服务 (banks)
        "J67",  # 资本市场服务 (securities)
        "J68",  # 保险业
        "J69",  # 其他金融业
    ],
    expected_effect=(
        "Reduce shadow banking, channel business; "
        "decrease bank off-balance-sheet activities; "
        "may increase bank risk-taking initially"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.jfs.2020.100789",
    ],
    data_sources=["CSMAR", "Wind", "BankFocus"],
    notes=(
        "Sharp shock to financial sector. "
        "Recommend narrow sample to financial firms only."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 5: 科创板设立 (STAR Market establishment) — 2019-07-22
# ─────────────────────────────────────────────────────────────────────
# Shanghai Stock Exchange Science and Technology Innovation Board.
# Registration-based IPO system for tech firms.

KE_CHUANG_BAN = ChinaPolicyEvent(
    name="科创板设立",
    english_name="STAR Market Establishment",
    launch_date=date(2019, 7, 22),
    scope="National (firms can list from any province)",
    treated_provinces=[],
    treated_industries=[
        "C39",  # 计算机、通信和其他电子设备制造业
        "I63",  # 电信、广播电视和卫星传输服务
        "I64",  # 互联网和相关服务
        "I65",  # 软件和信息技术服务业
        "M73",  # 研究和试验发展
        "M74",  # 专业技术服务业
        "M75",  # 科技推广和应用服务业
    ],
    expected_effect=(
        "Boost tech firm IPOs; increase R&D investment industry-wide; "
        "may reduce financing constraints for tech firms"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.jfs.2021.100987",
    ],
    data_sources=["CSMAR", "Wind", "CNRDS"],
    notes=(
        "Better to compare STAR-eligible firms vs non-tech firms. "
        "Use tech firm indicator (CN industry codes) as treatment."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 6: 碳达峰碳中和 (Dual Carbon Goals) — 2020-09-22 (announced at UN)
# ─────────────────────────────────────────────────────────────────────
# China's commitment: peak CO2 emissions before 2030, neutrality before 2060.
# Major implications for high-carbon industries.

TAN_DA_FENG = ChinaPolicyEvent(
    name="碳达峰碳中和",
    english_name="Dual Carbon Goals (Peak by 2030, Neutrality by 2060)",
    launch_date=date(2020, 9, 22),
    scope="National, but high-carbon industries most affected",
    treated_provinces=[],
    treated_industries=[
        "B06",  # 煤炭
        "C25",  # 石油加工
        "C26",  # 化学原料
        "C30",  # 非金属矿物 (cement)
        "C31",  # 黑色金属 (steel)
        "C32",  # 有色金属
        "C44",  # 电力热力
    ],
    expected_effect=(
        "Force high-carbon industries to green-transition; "
        "decrease fossil fuel use; increase green innovation; "
        "may cause stranded assets in coal/steel"
    ),
    example_papers=[
        "https://doi.org/10.1016/j.jeem.2023.102967",
    ],
    data_sources=["CSMAR", "CNRDS", "Wind"],
    notes=(
        "Diffuse but strong. Use 2020-09-22 as treatment date. "
        "High-carbon indicator (per CN industry codes) as treatment."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Event 7: 数据二十条 (Data Twenty Articles) — 2022-12-02
# ─────────────────────────────────────────────────────────────────────
# "Opinions on Building the Data Basic System to Better Play the Role of
# Data Elements" — establishes data as a factor of production.

SHU_JU_ER_SHI_TIAO = ChinaPolicyEvent(
    name="数据二十条",
    english_name="Data Twenty Articles",
    launch_date=date(2022, 12, 2),
    scope="National",
    treated_provinces=[],
    treated_industries=[
        "I63",  # 电信
        "I64",  # 互联网
        "I65",  # 软件和信息技术服务业
        "C39",  # 计算机、通信和其他电子设备制造业
        "L72",  # 商务服务业 (incl. data services)
    ],
    expected_effect=(
        "Boost data-driven firms; increase digital economy investment; "
        "may ease data sharing constraints"
    ),
    example_papers=[
        # Emerging, no major papers yet (cutoff 2026-06)
    ],
    data_sources=["CSMAR", "Wind"],
    notes=(
        "Very recent (2022-12-02). Limited time-series for outcome analysis. "
        "Recommend event-study with long pre-period."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Aggregate dictionary for easy access
# ─────────────────────────────────────────────────────────────────────

ALL_EVENTS = {
    "ying_gai_zeng": YING_GAI_ZENG,
    "daqi_shi_tiao": DAQI_SHI_TIAO,
    "he_zhang_zhi": HE_ZHANG_ZHI,
    "zi_guan_xin_gui": ZI_GUAN_XIN_GUI,
    "ke_chuang_ban": KE_CHUANG_BAN,
    "tan_da_feng": TAN_DA_FENG,
    "shu_ju_er_shi_tiao": SHU_JU_ER_SHI_TIAO,
}


def get_event(name: str) -> ChinaPolicyEvent:
    """Get a policy event by short name.

    Args:
        name: One of: ying_gai_zeng, daqi_shi_tiao, he_zhang_zhi, zi_guan_xin_gui,
            ke_chuang_ban, tan_da_feng, shu_ju_er_shi_tiao

    Returns:
        ChinaPolicyEvent instance
    """
    if name not in ALL_EVENTS:
        raise KeyError(
            f"Unknown event '{name}'. Available: {list(ALL_EVENTS.keys())}"
        )
    return ALL_EVENTS[name]


def list_events() -> pd.DataFrame:
    """List all events as a DataFrame for easy inspection."""
    return pd.DataFrame(
        [
            {
                "name": e.name,
                "english": e.english_name,
                "launch": e.launch_date,
                "scope": e.scope[:80] + "...",
            }
            for e in ALL_EVENTS.values()
        ]
    )


if __name__ == "__main__":
    print(list_events())
    print()
    print("Example: 河长制 treatment provinces:")
    print(HE_ZHANG_ZHI.treated_provinces)
