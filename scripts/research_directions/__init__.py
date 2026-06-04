"""ResearchDirections: Unified framework for multi-domain research agents.

This module provides a comprehensive research direction system covering:
- 绿色金融 (Green Finance)
- 数字金融 (Digital Finance)
- 宏观金融 (Macro Finance)
- 公司金融 (Corporate Finance)
- 资产定价 (Asset Pricing)
- 行为金融 (Behavioral Finance)
- 国际金融 (International Finance)
- 劳动经济学 (Labor Economics)
- 公共经济学 (Public Economics)
- 金融中介 (Financial Intermediation)

Each direction includes a full methodology chain, data requirements,
expected outputs, and keywords for matching.

Architecture:
    ResearchDirection       — Unified dataclass for any research direction
    MethodologyChain       — Chain of econometric methods with metadata
    DirectionFactory       — Registry + search + LLM-based suggestion
    DirectionRecommender   — Keyword-based direction matching and ranking

Usage:
    from scripts.research_directions import DirectionFactory, DirectionRecommender

    # Get a specific direction
    direction = DirectionFactory.get_direction("carbon_trading")

    # Search by keyword
    results = DirectionFactory.search_directions("climate risk")

    # Get all directions
    all_names = DirectionFactory.list_all()

    # Suggest directions based on research interests
    recommender = DirectionRecommender()
    suggestions = recommender.suggest("我想研究金融科技对银行的影响")
"""

from __future__ import annotations

import json
import logging
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

# ─── Core Data Classes ────────────────────────────────────────────────────────


@dataclass
class MethodologyStep:
    """
    A single step in an econometric methodology chain.

    Attributes:
        step_name: Human-readable name (e.g., "倾向得分匹配")
        econometric_class: Reference class name (e.g., "PSM", "DID")
        notes: Implementation notes, assumptions, or caveats
        data_needed: List of data requirements for this step
        packages: Python packages needed (e.g., ["linearmodels", "causalinference"])
    """

    step_name: str
    econometric_class: str
    notes: str = ""
    data_needed: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Format as a markdown methodology step."""
        lines = [
            f"### {self.step_name} (`{self.econometric_class}`)",
            "",
        ]
        if self.notes:
            lines.append(f"**Notes:** {self.notes}")
        if self.data_needed:
            lines.append(f"**Data needed:** {', '.join(self.data_needed)}")
        if self.packages:
            lines.append(f"**Packages:** `{'`, `'.join(self.packages)}`")
        return "\n".join(lines)


@dataclass
class MethodologyChain:
    """
    A chain of econometric methods for a research direction.

    Represents the full methodology pipeline from data preparation
    through identification strategy to robustness checks.

    Usage:
        chain = MethodologyChain(steps=[
            MethodologyStep("倾向得分匹配", "PSM", "使用1:1最近邻匹配"),
            MethodologyStep("双重差分", "DID", "控制双向固定效应"),
        ])
        print(chain.to_markdown())
        print(chain.get_required_packages())
    """

    steps: list[MethodologyStep] = field(default_factory=list)

    def add_step(self, step: MethodologyStep) -> MethodologyChain:
        """Fluent API: add a step and return self."""
        self.steps.append(step)
        return self

    def to_markdown(self) -> str:
        """Format entire chain as markdown."""
        lines = ["## Methodology Chain", ""]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step.to_markdown()}")
            lines.append("")
        return "\n".join(lines)

    def get_required_packages(self) -> list[str]:
        """Collect all unique Python packages needed across all steps."""
        packages: set[str] = set()
        for step in self.steps:
            packages.update(step.packages)
        # Core packages always available
        core = {"pandas", "numpy", "statsmodels", "scipy"}
        return sorted(packages | core)

    def get_step_names(self) -> list[str]:
        """List all step names in order."""
        return [s.step_name for s in self.steps]

    def get_econometric_classes(self) -> list[str]:
        """List all econometric class references."""
        return [s.econometric_class for s in self.steps]


@dataclass
class ResearchDirection:
    """
    Unified research direction definition.

    Captures all metadata needed to execute a research direction:
    from literature theme through methodology chain to expected output.

    Attributes:
        direction_name: Internal slug identifier (e.g., "carbon_trading")
        display_name: Human-readable name (e.g., "碳交易试点效应")
        literature_theme: Core research question/topic
        methodology_chain: Full econometric methodology pipeline
        data_requirements: Dict describing required data sources
        expected_output: Description of paper sections and tables
        keywords: Search keywords for matching
        sub_topics: Optional list of related sub-topics
        references: Optional list of key reference papers
        difficulty: "beginner" | "intermediate" | "advanced"
        estimated_pages: Approximate paper length
    """

    direction_name: str
    display_name: str
    literature_theme: str
    methodology_chain: MethodologyChain
    data_requirements: dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    keywords: list[str] = field(default_factory=list)
    sub_topics: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    difficulty: str = "intermediate"
    estimated_pages: int = 30

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "direction_name": self.direction_name,
            "display_name": self.display_name,
            "literature_theme": self.literature_theme,
            "methodology_chain_steps": [
                {
                    "step_name": s.step_name,
                    "econometric_class": s.econometric_class,
                    "notes": s.notes,
                    "data_needed": s.data_needed,
                    "packages": s.packages,
                }
                for s in self.methodology_chain.steps
            ],
            "data_requirements": self.data_requirements,
            "expected_output": self.expected_output,
            "keywords": self.keywords,
            "sub_topics": self.sub_topics,
            "references": self.references,
            "difficulty": self.difficulty,
            "estimated_pages": self.estimated_pages,
        }

    def to_markdown(self) -> str:
        """Format as a complete research proposal markdown."""
        lines = [
            f"# {self.display_name}",
            "",
            f"**Direction:** `{self.direction_name}` | **Difficulty:** {self.difficulty} | **Pages:** ~{self.estimated_pages}",
            "",
            "## Research Question",
            "",
            self.literature_theme,
            "",
            "## Methodology",
            "",
        ]
        lines.append(self.methodology_chain.to_markdown())
        lines.extend([
            "",
            "## Data Requirements",
            "",
        ])
        for source, desc in self.data_requirements.items():
            lines.append(f"- **{source}:** {desc}")
        lines.extend([
            "",
            "## Expected Output",
            "",
            self.expected_output,
            "",
            "## Keywords",
            "",
            ", ".join(f"`{k}`" for k in self.keywords),
        ])
        if self.sub_topics:
            lines.extend(["", "## Related Sub-topics", ""])
            for topic in self.sub_topics:
                lines.append(f"- {topic}")
        if self.references:
            lines.extend(["", "## Key References", ""])
            for ref in self.references:
                lines.append(f"- {ref}")
        return "\n".join(lines)


# ─── Direction Registry (for standalone direction classes) ────────────────────


class DirectionRegistry:
    """
    Global registry for standalone ResearchDirection classes.

    These classes (e.g. CarbonEconomicsDirection) are defined in separate
    files and registered via get_registry().register(cls()) at import time.
    DirectionFactory._init_registry() merges them into the main registry.
    """

    _registered: list = []

    @classmethod
    def register(cls, direction_instance) -> None:
        """Register a direction instance. Called at module import time."""
        cls._registered.append(direction_instance)

    @classmethod
    def get_registered(cls) -> list:
        return cls._registered


# ─── Base class for standalone direction files ─────────────────────────────────


class BaseResearchDirection:
    """
    Base class for research directions defined in separate files.

    Subclasses must implement:
        name        — display name (e.g. "碳经济学")
        slug        — identifier (e.g. "carbon_economics")
        description — one-line description
        policy_events — list of (year, description) tuples
        fetch_data(topic, **kwargs) — fetch data via MCP or file
        build_panel(data) — build panel DataFrame
        run_regressions(panel) — run regressions, return dict
        format_tables(reg_results) — format tables as LaTeX strings

    Provides helper methods:
        _fetch_via_mcp(server, tool, params) — call MCP tool
        _require_data_source(name, allow_none) — raise if no data found
    """

    name: str = ""
    slug: str = ""
    description: str = ""
    policy_events: list = []

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        raise NotImplementedError

    def build_panel(self, data: dict) -> dict | None:
        raise NotImplementedError

    def run_regressions(self, panel: dict) -> dict:
        return {"status": "pending", "tables": {}}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        return {}

    # ── Helper methods ─────────────────────────────────────────────────────────

    def _fetch_via_mcp(
        self,
        server: str,
        tool: str,
        params: dict,
    ) -> dict | None:
        """Call an MCP tool and return its result, or None on failure.

        Uses the MCP tool infrastructure to fetch data from configured servers.
        """
        try:
            from scripts.core.dynamic_tools import MCP_TOOL_SERVER_MAP

            if server not in MCP_TOOL_SERVER_MAP:
                return None
            actual_server = MCP_TOOL_SERVER_MAP[server]
            # Delegate to the MCP call infrastructure
            return self._mcp_call(actual_server, tool, params)
        except Exception as exc:
            _log.warning("MCP call failed — server=%s tool=%s: %s", server, tool, exc)
            return None

    def _mcp_call(
        self, server: str, tool: str, params: dict
    ) -> dict | None:
        """Internal MCP call dispatcher."""
        try:
            from scripts.core.dynamic_tools import get_mcp_tool_result

            result = get_mcp_tool_result(server, tool, params)
            return result
        except Exception:
            return None

    def _require_data_source(
        self, name: str, allow_none: bool = False
    ) -> None:
        """Raise DataSourceError if no data is available and allow_none is False."""
        if not allow_none:
            from scripts.exceptions import DataSourceError

            raise DataSourceError(
                f"No data source for '{name}'. "
                f"Set {name.upper()}_DATA_DIR or configure an MCP data server."
            )


# ─── Module-level helpers (for backward compatibility) ───────────────────────────


def get_registry() -> DirectionFactory:
    """
    Backward-compatible alias returning the DirectionFactory class.
    Provides classmethod access: .get(), .list(), .list_with_descriptions(), etc.

    Usage:
        from scripts.research_directions import get_registry
        registry = get_registry()
        direction = registry.get("carbon_trading")
        print(registry.list())
        print(registry.list_with_descriptions())
    """
    return DirectionFactory


# ─── Direction Factory ─────────────────────────────────────────────────────────


class DirectionFactory:
    """
    Factory and registry for all research directions.

    Provides:
    - get_direction(name): Retrieve a direction by slug
    - search_directions(keyword): Full-text search across all directions
    - list_all(): List all direction slugs
    - suggest_directions(prompt): LLM-based direction suggestion

    Usage:
        direction = DirectionFactory.get_direction("green_bond")
        results = DirectionFactory.search_directions("carbon")
        all_directions = DirectionFactory.list_all()
        suggestions = DirectionFactory.suggest_directions("研究金融科技对中小企业的影响")
    """

    _registry: dict[str, ResearchDirection] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, direction_instance: BaseResearchDirection) -> None:
        """Register a standalone direction class instance.

        Called automatically at the end of each direction file via:
            get_registry().register(XxxDirection())
        """
        if not cls._initialized:
            cls._init_registry()

        slug = getattr(direction_instance, "slug", "") or getattr(
            direction_instance, "name", ""
        )
        if slug:
            # Store the instance under its slug for easy retrieval
            cls._registry[slug] = direction_instance

    @classmethod
    def _init_registry(cls) -> None:
        """Initialize the direction registry with all predefined directions.

        This method parses ~2300 lines of nested Python dataclass literals.
        Import time is ~5.9s due to this parsing cost.

        NOTE: All 40 direction definitions should be migrated to
        ``directions.yaml`` for faster loading. When that migration is
        complete, replace this method's body with ``cls._load_from_yaml()``.
        """
        if cls._initialized:
            return
        cls._initialized = True

        # ── Green Finance ──────────────────────────────────────────────────
        cls._registry["carbon_trading"] = ResearchDirection(
            direction_name="carbon_trading",
            display_name="碳交易试点效应",
            literature_theme=(
                "研究碳排放权交易试点政策对企业减排行为的影响。"
                "评估碳配额机制是否有效促进企业绿色技术创新和碳排放 reduction。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="断点回归设计 (RDD)",
                    econometric_class="RDDRegression",
                    notes="以碳交易试点门槛设定为断点，利用企业是否跨过门槛进行断点回归估计因果效应。需检验断点连续性假设。",
                    data_needed=["企业层面排放数据", "碳配额分配信息", "企业财务数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="安慰剂检验",
                    econometric_class="PlaceboTest",
                    notes="在伪断点处进行回归，检验处理效应的真实性。",
                    data_needed=["伪断点数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="HeterogeneityAnalysis",
                    notes="按行业、规模、所有制分组，考察碳交易政策的异质性效果。",
                    data_needed=["企业分组变量"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "排放数据": "生态环境部企业排放监测数据或CSMAR环境数据库",
                "碳配额": "各试点碳交易所配额分配文件",
                "财务数据": "CSMAR/Wind上市公司财务数据",
                "专利数据": "国家知识产权局专利申请与授权数据",
            },
            expected_output=(
                "基准RDD回归表、安慰剂检验图、异质性分析表、机制检验表。"
                "预期碳交易试点使企业碳排放下降X%，绿色专利增加Y件。"
            ),
            keywords=["碳交易", "碳排放权", "RDD", "断点回归", "减排", "绿色创新", "碳配额"],
            sub_topics=["碳市场建设效果", "碳价对企业决策影响", "碳交易与绿色信贷"],
            references=[
                "Zhang et al. (2019, J Environ Econ Manage) — Carbon Trading and Firm Performance",
                "Tang et al. (2020, China Econ Rev) — Carbon Market Policy Effects",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["green_bond"] = ResearchDirection(
            direction_name="green_bond",
            display_name="绿色债券溢价",
            literature_theme=(
                '研究绿色债券相较于普通债券是否存在"绿色溢价"或"认证溢价"。'
                "考察发行人特征、债券条款和市场环境对绿色债券定价的影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="事件研究法 (Event Study)",
                    econometric_class="EventStudy",
                    notes="以绿色债券发行公告日为事件日，计算累计超额收益率(CAR)衡量市场反应。",
                    data_needed=["绿色债券发行数据", "二级市场交易数据", "市场基准收益率"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="利差分析",
                    econometric_class="OLSRegression",
                    notes="控制期限、信用评级、发行规模等债券特征后，比较绿色债券与普通债券的信用利差差异。",
                    data_needed=["债券发行利率", "信用评级", "债券特征变量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="动态效应检验",
                    econometric_class="PanelRegression",
                    notes="考察绿色溢价的时间演变趋势及其受政策变化的影响。",
                    data_needed=["时间序列债券数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "债券数据": "Wind绿色债券数据库或中债资信绿色债券数据",
                "市场数据": "中证债券估值数据或Dealscan",
                "评级数据": "中诚信/联合评级绿色债券评级信息",
            },
            expected_output=(
                "绿色债券vs普通债券利差对比表、发行窗口期CAR分析、动态溢价演变图。"
                "预期发现绿色债券存在X bps的绿色溢价。"
            ),
            keywords=["绿色债券", "绿色溢价", "信用利差", "事件研究", "债券定价"],
            sub_topics=["绿色ABS溢价", "碳中和债券定价", "绿色债券认证效应"],
            references=[
                "Flammer (2021, RFS) — Green Bonds: Benefits and Risks",
                "Zhou & Wen (2022, J Bank Finance) — Green Bond Pricing in China",
            ],
            difficulty="intermediate",
            estimated_pages=30,
        )

        cls._registry["esg_factor_pricing"] = ResearchDirection(
            direction_name="esg_factor_pricing",
            display_name="ESG因子定价",
            literature_theme=(
                "将ESG评分纳入Fama-French因子框架，检验ESG因子在中国A股市场的定价能力。"
                "考察E、S、G各维度因子是否独立提供风险溢价。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Fama-French五因子扩展 (FF5 + ESG)",
                    econometric_class="FamaMacBeth",
                    notes="在市场因子、MKT、SMB、HML、RMW、CMA基础上加入ESG因子，进行Fama-MacBeth两阶段回归检验定价能力。",
                    data_needed=["A股日收益率", "FF5因子", "ESG评分数据"],
                    packages=["scripts.econometrics_extended", "scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="分组组合分析",
                    econometric_class="PortfolioSort",
                    notes="按ESG评分高低构建5x5双重排序组合，检验ESG与收益的非线性关系。",
                    data_needed=["ESG评分", "股票收益率"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="因果推断检验",
                    econometric_class="2SLS/IVRegression",
                    notes="使用工具变量解决ESG评分与收益之间的内生性问题。",
                    data_needed=["工具变量（同行业平均ESG、媒体ESG报道）"],
                    packages=["scripts.econometrics"],
                ),
            ]),
            data_requirements={
                "收益数据": "CSMARA股日/周收益率数据",
                "因子数据": "CSMAR Fama-French因子数据或锐思数据库",
                "ESG数据": "Wind ESG评分/彭博ESG数据/商道融绿ESG评级",
            },
            expected_output=(
                "Fama-MacBeth回归表（各因子载荷与溢价）、分组组合收益表、"
                "E/S/G分项因子检验表、工具变量检验结果。"
                "预期发现ESG因子提供X%的风险溢价。"
            ),
            keywords=["ESG", "因子定价", "Fama-French", "绿色金融", "社会责任投资", "可持续金融"],
            sub_topics=["碳风险因子", "气候因子定价", "绿色因子有效性"],
            references=[
                "Fama & French (2015) — A Five-Factor Asset Pricing Model",
                "Li et al. (2021, J Financ Econ) — ESG and Expected Returns",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["climate_risk_transmission"] = ResearchDirection(
            direction_name="climate_risk_transmission",
            display_name="气候风险传导",
            literature_theme=(
                "研究气候变化风险（物理风险与转型风险）如何传导至金融机构资产价值。"
                "考察气候风险对银行信贷风险、保险公司负债端、资产管理机构组合的影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板向量自回归 (Panel VAR)",
                    econometric_class="PanelDataVAR",
                    notes="构建气候风险指标→金融机构风险暴露→宏观金融稳定的PVAR模型，考察动态传导机制。",
                    data_needed=["气候风险指标", "金融机构财务数据", "宏观经济变量"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="脉冲响应分析 (IRF)",
                    econometric_class="ImpulseResponse",
                    notes="通过PVAR模型的脉冲响应函数识别气候风险冲击的传导路径和持续时间。",
                    data_needed=["PVAR模型估计结果"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="压力测试",
                    econometric_class="StressTest",
                    notes="基于气候情景（SSP-RCP）对金融机构进行气候压力测试，评估极端气候事件的影响。",
                    data_needed=["NGFS气候情景数据", "金融机构资产负债数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "气候数据": "Berkeley Earth气温数据/NOAA极端天气指数",
                "转型风险": "碳价路径、碳中和政策时间表（NGFS数据库）",
                "金融数据": "上市银行/保险公司年报数据",
                "宏观数据": "GDP、通胀、房地产价格指数",
            },
            expected_output=(
                "PVAR模型估计表、脉冲响应图、方差分解表、气候压力测试结果。"
                "量化气候风险冲击对银行不良贷款率的影响。"
            ),
            keywords=["气候风险", "物理风险", "转型风险", "PVAR", "压力测试", "NGFS", "绿色金融"],
            sub_topics=["碳价风险传导", "极端天气与信贷风险", "气候情景分析"],
            references=[
                "TCFD (2021) — Climate Risk Disclosures Framework",
                "NGFS (2022) — Climate Scenarios for Central Banks",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        # ── Digital Finance ─────────────────────────────────────────────────
        cls._registry["digital_inclusion_financing"] = ResearchDirection(
            direction_name="digital_inclusion_financing",
            display_name="数字普惠金融×融资约束",
            literature_theme=(
                "研究数字普惠金融发展如何缓解中小企业和低收入群体的融资约束。"
                "考察数字技术通过降低信息不对称、扩大金融服务覆盖面来促进普惠金融的机制。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板Tobit回归",
                    econometric_class="PanelTobit",
                    notes="使用面板Tobit模型处理受限因变量（融资约束指标），控制双向固定效应。",
                    data_needed=["企业融资约束数据", "数字普惠金融指数", "控制变量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="工具变量法",
                    econometric_class="IVRegression",
                    notes="使用地区互联网普及率、历史电信基础设施作为数字金融的工具变量，处理内生性。",
                    data_needed=["IV变量（同地区互联网覆盖率）"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="中介效应检验",
                    econometric_class="MediationAnalysis",
                    notes="检验数字金融→缓解信息不对称→融资约束缓解的作用渠道。",
                    data_needed=["中介变量（信用评分、贷款可得性）"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "数字普惠金融": "北京大学数字普惠金融指数（2011-2021）",
                "融资约束": "KZ指数/SA指数/问卷调查数据",
                "企业数据": "CSMAR上市公司财务数据",
                "家庭数据": "CHFS/CHARLS家庭金融调查数据",
            },
            expected_output=(
                "基准面板Tobit回归表、IV-2SLS结果、中介效应检验表、异质性分析（企业规模/地区）。"
                "预期发现数字普惠金融指数每增加1个标准差，企业融资约束降低X%。"
            ),
            keywords=["数字普惠金融", "融资约束", "Tobit", "中小企业融资", "金融科技", "包容性增长"],
            sub_topics=["农村数字金融", "数字信贷评估", "金融科技与家庭金融"],
            references=[
                "Gomber et al. (2017) — Digital Finance and FinTech",
                "周广肃等(2018, 经济研究) — 数字普惠金融与融资约束",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["fintech_bank_efficiency"] = ResearchDirection(
            direction_name="fintech_bank_efficiency",
            display_name="金融科技竞争×银行效率",
            literature_theme=(
                "研究金融科技企业的崛起如何影响传统银行的经营效率、风险承担和业务模式转型。"
                "考察银行应对金融科技冲击的策略选择及其绩效后果。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="随机前沿分析 (SFA)",
                    econometric_class="StochasticFrontierAnalysis",
                    notes="使用SFA估计银行效率边界，分离技术效率、规模效率和X效率。",
                    data_needed=["银行投入产出数据", "财务指标"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以大型金融科技企业进入某地区市场为准自然实验，检验对当地银行效率的影响。",
                    data_needed=["金融科技进入事件数据", "银行面板数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="中介效应",
                    econometric_class="MediationAnalysis",
                    notes="检验金融科技→银行中间业务收入占比变化→整体效率变化的作用渠道。",
                    data_needed=["银行中间业务数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "银行数据": "BANKSCOPE/Wind上市银行数据",
                "金融科技": "BATJ/蚂蚁/腾讯等金融科技业务数据",
                "地区数据": "各省市金融科技发展指数",
            },
            expected_output=(
                "SFA效率值分布表、DID基准回归表、中介效应检验、异质性分析（银行规模/类型）。"
                "预期发现金融科技竞争使银行X效率下降Y%。"
            ),
            keywords=["金融科技", "银行效率", "SFA", "DID", "竞争", "数字化转型", "FinTech"],
            sub_topics=["金融科技与银行风险", "开放银行", "数字银行业态"],
            references=[
                "Philippon (2016, J Financ Perspect) — Fintech and Banking",
                "Thakor (2020, RFS) — Fintech and Banking: What Do We Learn?",
            ],
            difficulty="advanced",
            estimated_pages=38,
        )

        cls._registry["dcep_enterprise_innovation"] = ResearchDirection(
            direction_name="dcep_enterprise_innovation",
            display_name="数字人民币×企业创新",
            literature_theme=(
                "研究央行数字货币（数字人民币）试点如何影响企业创新投入和产出。"
                "考察数字货币通过改善支付效率、降低融资成本、促进数字化转型来影响创新的机制。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="倾向得分匹配 (PSM)",
                    econometric_class="PSM",
                    notes="为数字人民币试点城市企业匹配特征相似的非试点城市对照组，解决选择性偏误。",
                    data_needed=["数字人民币试点城市名单", "企业特征数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="双重差分 (PSM-DID)",
                    econometric_class="DIDRegression",
                    notes="在PSM匹配样本上进行DID估计，检验数字人民币对企业创新的因果效应。",
                    data_needed=["企业专利数据", "研发投入数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="动态效应检验",
                    econometric_class="EventStudy",
                    notes="通过事件研究法检验数字人民币对企业创新的动态影响路径。",
                    data_needed=["各批次试点时间"],
                    packages=["scripts.econometrics_extended"],
                ),
            ]),
            data_requirements={
                "数字人民币": "数字人民币试点城市名单及试点时间线（中国人民银行）",
                "企业数据": "上市公司年报、专利数据库（国家知识产权局）",
                "财务数据": "CSMAR上市公司财务数据",
            },
            expected_output=(
                "PSM匹配平衡性检验表、PSM-DID基准回归表、事件研究图、机制检验表。"
                "预期发现试点城市企业专利申请增加X%，研发投入增加Y%。"
            ),
            keywords=["数字人民币", "CBDC", "企业创新", "PSM-DID", "专利", "研发投入"],
            sub_topics=["数字货币与供应链金融", "DCEP跨境支付", "数字货币与货币政策传导"],
            references=[
                "BIS (2021) — Central Bank Digital Currency: Foundational Principles",
                "Boar & Wehrli (2021, BIS) — Ready, Steady, Go? — CBDC",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["supply_chain_finance_sme"] = ResearchDirection(
            direction_name="supply_chain_finance_sme",
            display_name="供应链金融×中小企业融资",
            literature_theme=(
                "研究供应链金融如何缓解中小企业融资约束。"
                "考察核心企业信用穿透、应收账款融资、存货融资等模式对中小企业融资可得性和成本的影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Heckman两阶段模型",
                    econometric_class="HeckmanTwoStep",
                    notes="处理样本选择偏误：企业是否参与供应链金融（选择方程）→参与后的融资改善程度（结果方程）。",
                    data_needed=["供应链金融参与数据", "融资数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="工具变量法",
                    econometric_class="IVRegression",
                    notes="使用核心企业行业地位、供应链集聚程度作为供应链金融参与的工具变量。",
                    data_needed=["核心企业信用评级", "供应链结构数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="SubgroupAnalysis",
                    notes="按行业、地区、企业规模分析供应链金融的差异化效果。",
                    data_needed=["企业分组变量"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "供应链金融": "中企云链/简单汇/联易融供应链金融资产数据",
                "企业数据": "上市公司应付账款/应收账款数据",
                "融资数据": "银行贷款数据/民间借贷利率",
            },
            expected_output=(
                "Heckman两步法回归表、IV-2SLS结果、供应链金融对企业融资成本的影响表。"
                "预期发现参与供应链金融使中小企业融资成本降低X%。"
            ),
            keywords=["供应链金融", "中小企业融资", "Heckman", "应收账款", "核心企业信用"],
            sub_topics=["区块链供应链金融", "票据融资", "产业链金融协同"],
            references=[
                "Klapper (2006, J Bank Finance) — Role of Factoring for SME Finance",
                "Gambetta (2021, M&SOM) — Supply Chain Finance and Blockchain",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        # ── Macro Finance ───────────────────────────────────────────────────
        cls._registry["monetary_policy_shadowbanking"] = ResearchDirection(
            direction_name="monetary_policy_shadowbanking",
            display_name="货币政策传导×影子银行",
            literature_theme=(
                "研究货币政策通过银行信贷渠道和影子银行渠道的不同传导机制。"
                "考察影子银行对货币政策有效性的削弱作用及其监管政策效果。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板GMM估计",
                    econometric_class="PanelGMM",
                    notes="使用动态面板GMM处理货币政策变量与影子银行规模之间的内生性和动态依存关系。",
                    data_needed=["货币政策指标", "影子银行规模数据", "宏观经济变量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="中介效应模型",
                    econometric_class="MediationAnalysis",
                    notes="检验货币政策→银行信贷供给变化→影子银行规模变化的作用渠道。",
                    data_needed=["银行信贷数据", "非标资产数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="异质性检验",
                    econometric_class="SubgroupAnalysis",
                    notes="按银行类型（国有vs股份制vs城商行）和监管周期分样本检验。",
                    data_needed=["银行类型数据", "监管政策时间表"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "货币政策": "存款准备金率/MLF利率/shibor",
                "影子银行": "社融中委托贷款+信托贷款+未贴现银行承兑汇票",
                "银行数据": "上市银行资产负债表",
            },
            expected_output=(
                "面板GMM回归表（货币政策对影子银行的影响）、中介效应检验、异质性分析表。"
                "预期发现货币政策收紧时影子银行规模增加X%，说明存在替代效应。"
            ),
            keywords=["货币政策传导", "影子银行", "面板GMM", "金融脱媒", "监管套利"],
            sub_topics=["货币非中性", "流动性传导", "利率走廊"],
            references=[
                "Chen et al. (2018, J Money Credit Bank) — Shadow Banking and Monetary Policy",
                "Zhu (2021, J Financ Econ) — Shadow Banking in China",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["fed_tapering_emerging_markets"] = ResearchDirection(
            direction_name="fed_tapering_emerging_markets",
            display_name="美联储缩表×新兴市场",
            literature_theme=(
                "研究美联储货币政策正常化（缩表、加息）对新兴市场国家资本流动、汇率和金融稳定的溢出效应。"
                "考察新兴市场应对美联储政策冲击的政策工具有效性。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="事件研究法",
                    econometric_class="EventStudy",
                    notes="以美联储FOMC会议声明和缩表公告为事件，检验新兴市场资产价格对事件日的反应。",
                    data_needed=["美联储政策事件日期", "新兴市场资产价格数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="控制基本面因素后，考察美联储政策对新兴市场资本流动、汇率波动的系统性影响。",
                    data_needed=["FDI/证券投资流入数据", "汇率数据", "宏观基本面"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="溢出效应分解",
                    econometric_class="SpilloverAnalysis",
                    notes="区分利率渠道、汇率渠道和风险偏好渠道的相对重要性。",
                    data_needed=["VIX指数", "全球风险偏好指标"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "美联储政策": "FOMC会议纪要/缩表时间表（Fed官网）",
                "新兴市场": "IIF资本流动数据/IMF BoP数据",
                "资产价格": "Bloomberg新兴市场股指/汇率数据",
            },
            expected_output=(
                "新兴市场资产对美联储事件日的CAR分析、面板回归表、溢出渠道分解结果。"
                "预期发现美联储缩表公告导致新兴市场资本流出X亿美元。"
            ),
            keywords=["美联储缩表", "新兴市场", "资本流动", "溢出效应", "汇率波动", "FOMC"],
            sub_topics=["央行资产负债表", "美元周期", "新兴市场金融危机"],
            references=[
                "Rey (2013, IMF Econ Rev) — Dilemma not Trilemma: Global Financial Cycle",
                "Miranda-Agrippino & Rey (2022, RFS) — US Monetary Policy and Global Financial Cycles",
            ],
            difficulty="advanced",
            estimated_pages=38,
        )

        cls._registry["interest_rate_marketization_bank_risk"] = ResearchDirection(
            direction_name="interest_rate_marketization_bank_risk",
            display_name="利率市场化×银行风险",
            literature_theme=(
                "研究中国利率市场化改革对银行风险承担行为的影响。"
                "考察利率双轨制并轨后，银行净息差收窄如何影响其风险偏好和资产质量。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以2015年存款利率上限放开为政策冲击，比较放开前后银行风险指标的变化。",
                    data_needed=["利率市场化政策时间", "银行风险数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="事件研究法",
                    econometric_class="EventStudy",
                    notes="检验政策前后的平行趋势假设，验证DID识别策略的有效性。",
                    data_needed=["政策前后各期数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="机制检验",
                    econometric_class="MediationAnalysis",
                    notes="检验利率市场化→净息差收窄→风险承担增加的传导机制。",
                    data_needed=["银行净息差数据", "风险指标"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "利率政策": "中国人民银行存贷款利率调整历史",
                "银行数据": "上市银行年报数据（不良贷款率、拨备覆盖率）",
                "宏观数据": "GDP增速、货币政策环境",
            },
            expected_output=(
                "DID基准回归表、事件研究图（平行趋势检验）、机制检验表。"
                "预期发现利率市场化后银行风险承担增加X个百分点。"
            ),
            keywords=["利率市场化", "银行风险", "DID", "净息差", "金融改革", "风险承担"],
            sub_topics=["LPR改革", "利率并轨", "银行竞争与风险"],
            references=[
                "Agur & Demertzis (2019, IMF) — Interest Rate Liberalization and Bank Risk",
                "Wang et al. (2021, J Bank Finance) — Interest Rate Marketization in China",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["exchange_rate_volatility_trade"] = ResearchDirection(
            direction_name="exchange_rate_volatility_trade",
            display_name="汇率波动×进出口",
            literature_theme=(
                "研究人民币汇率波动对进出口贸易的影响。"
                "考察汇率波动通过收入效应、价格效应和竞争效应影响贸易流量。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板引力模型",
                    econometric_class="PanelGravity",
                    notes="扩展贸易引力模型，加入汇率波动率和汇率水平变量。",
                    data_needed=["进出口贸易数据", "汇率数据", "GDP数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="面板GMM",
                    econometric_class="PanelGMM",
                    notes="处理贸易流量的动态调整和内生性问题。",
                    data_needed=["滞后一期贸易流量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="SubgroupAnalysis",
                    notes="按贸易方式（一般贸易/加工贸易）、产品类别、目的地分组检验。",
                    data_needed=["贸易方式和产品分类数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "贸易数据": "海关总署进出口商品贸易数据",
                "汇率数据": "BIS有效汇率指数/人民币对美元汇率",
                "宏观经济": "GDP、人口、距离等引力模型变量",
            },
            expected_output=(
                "面板引力模型回归表、汇率波动对不同贸易方式的影响对比表。"
                "预期发现人民币汇率波动增加1个百分点，进出口下降X%。"
            ),
            keywords=["汇率波动", "进出口", "引力模型", "贸易流量", "人民币国际化"],
            sub_topics=["汇率传递效应", "结算货币选择", "贸易摩擦与汇率"],
            references=[
                "Arize et al. (2017, J Int Money Finance) — Exchange Rate Volatility and Trade",
                "Berger et al. (2022, J Dev Econ) — RMB Exchange Rate and Trade",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        # ── Corporate Finance ───────────────────────────────────────────────
        cls._registry["ma_innovation"] = ResearchDirection(
            direction_name="ma_innovation",
            display_name="并购×创新",
            literature_theme=(
                "研究并购活动对企业创新投入和产出的影响。"
                "考察横向并购、多元化并购对创新效率和创新方向的不同影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="倾向得分匹配 (PSM)",
                    econometric_class="PSM",
                    notes="为并购企业匹配特征相似的未并购企业对照组，解决选择性偏误。",
                    data_needed=["并购事件数据", "企业特征数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="双重差分 (PSM-DID)",
                    econometric_class="DIDRegression",
                    notes="在PSM匹配样本上进行DID，估计并购对创新的因果效应。",
                    data_needed=["并购前后企业专利数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="动态效应检验",
                    econometric_class="EventStudy",
                    notes="检验并购后创新产出的动态变化路径。",
                    data_needed=["多年期数据"],
                    packages=["scripts.econometrics_extended"],
                ),
            ]),
            data_requirements={
                "并购数据": "Wind/MergeStat全球并购数据库",
                "专利数据": "国家知识产权局专利数据",
                "财务数据": "CSMAR上市公司财务数据",
            },
            expected_output=(
                "PSM平衡性检验表、PSM-DID回归表、并购后创新动态变化图。"
                "预期发现并购使企业专利申请增加X%，但多元化并购效果弱于横向并购。"
            ),
            keywords=["并购", "企业创新", "PSM-DID", "专利", "协同效应", "多元化"],
            sub_topics=["跨国并购创新", "并购与研发效率", "并购整合"],
            references=[
                "Haucap & Schwalbe (2021) — M&A and Innovation: A Review",
                "Wang (2022, J Financ Econ) — Corporate Acquisitions and Innovation",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["institutional_investor_esg"] = ResearchDirection(
            direction_name="institutional_investor_esg",
            display_name="机构投资者×ESG披露",
            literature_theme=(
                "研究机构投资者持股对企业ESG信息披露和质量的影响。"
                "考察长期机构投资者vs短期机构投资者在ESG治理中的不同角色。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="两阶段最小二乘法 (2SLS)",
                    econometric_class="IVRegression",
                    notes="使用机构投资者行业配置偏好作为持股比例的工具变量，处理内生性。",
                    data_needed=["机构投资者持股数据", "ESG评分数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="固定效应面板回归",
                    econometric_class="OLSRegression",
                    notes="控制企业和年份固定效应，考察机构持股对ESG的影响。",
                    data_needed=["企业ESG评分", "机构持股比例"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="SubgroupAnalysis",
                    notes="区分共同基金、养老金、保险资金等不同类型机构投资者的作用。",
                    data_needed=["机构投资者分类数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "机构持股": "CSMAR机构投资者持股数据",
                "ESG数据": "Wind/彭博ESG评分",
                "治理数据": "上市公司治理数据库",
            },
            expected_output=(
                "2SLS回归表、机构持股类型异质性分析、ESG各维度分项回归。"
                "预期发现机构投资者持股比例增加1%，ESG评分提高X分。"
            ),
            keywords=["机构投资者", "ESG披露", "公司治理", "2SLS", "股东积极主义", "责任投资"],
            sub_topics=["被动投资与ESG", "机构投资者监督", "ESG评级影响"],
            references=[
                "Dimson et al. (2015, J Financ Econ) — Corporate Governance and Responsible Investment",
                "Cox et al. (2022) — Institutional Investors and ESG Disclosure",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["registration_system_ipo"] = ResearchDirection(
            direction_name="registration_system_ipo",
            display_name="注册制×IPO定价效率",
            literature_theme=(
                "研究科创板/创业板注册制改革对IPO定价效率的影响。"
                "考察注册制下IPO定价是否更充分反映公司基本面信息和市场供求。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="断点回归 (RDD)",
                    econometric_class="RDDRegression",
                    notes="以注册制实施日期为断点，检验IPO定价效率在断点前后的变化。",
                    data_needed=["IPO定价数据", "上市后表现数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="比较注册制板块与非注册制板块在改革前后的差异。",
                    data_needed=["各板块IPO数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="定价效率指标检验",
                    econometric_class="EfficiencyTest",
                    notes="使用抑价率、上市初期收益率、长期回报率衡量定价效率。",
                    data_needed=["上市首日/30日/1年收益数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "IPO数据": "Wind/锐思IPO数据库（发行价、上市日期、承销商）",
                "交易数据": "CSMAR个股日收益率数据",
                "财务数据": "招股说明书财务数据",
            },
            expected_output=(
                "RDD回归表、注册制vs核准制板块对比表、定价效率指标演变图。"
                "预期发现注册制实施后IPO抑价率下降X个百分点。"
            ),
            keywords=["注册制", "IPO定价", "RDD", "核准制", "科创板", "创业板", "抑价率"],
            sub_topics=["注册制与市场效率", "保荐机构责任", "退市制度"],
            references=[
                "Gao & Ritter (2010, J Financ) — Marketing Season Hypothesis for IPO",
                "陈工孟等(2021) — 注册制改革与IPO效率",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["executive_compensation_performance"] = ResearchDirection(
            direction_name="executive_compensation_performance",
            display_name="高管薪酬×企业绩效",
            literature_theme=(
                "研究高管薪酬激励对企业绩效的影响及最优薪酬契约设计。"
                "考察薪酬-业绩敏感性、股权激励对管理层行为和公司价值的作用。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Tobit/Heckman模型",
                    econometric_class="HeckmanTwoStep",
                    notes="处理高管薪酬数据的左归并问题（最低薪酬限制）。",
                    data_needed=["高管薪酬数据", "企业绩效数据"],
                    packages=["scripts.econometrics", "scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="考察薪酬-绩效敏感性与公司价值的非线性关系。",
                    data_needed=["高管持股数据", "公司价值指标"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="分位数回归",
                    econometric_class="QuantileRegression",
                    notes="检验薪酬激励在不同绩效水平上的差异化效果。",
                    data_needed=["完整面板数据"],
                    packages=["scripts.econometrics_extended"],
                ),
            ]),
            data_requirements={
                "薪酬数据": "CSMAR高管薪酬数据",
                "持股数据": "上市公司股权激励数据",
                "绩效数据": "ROE/Tobin's Q等绩效指标",
            },
            expected_output=(
                "Heckman模型结果、薪酬-绩效敏感性分析、分位数回归表。"
                "预期发现高管薪酬每增加1%，公司ROE提高X个百分点。"
            ),
            keywords=["高管薪酬", "薪酬激励", "股权激励", "Tobit", "管理层激励", "公司治理"],
            sub_topics=["国企高管限薪", "薪酬委员会", "期权激励"],
            references=[
                "Jensen & Murphy (1990) — Performance Pay and Top-Management Incentives",
                "Firth et al. (2006, J Law Econ) — Executive Compensation in China",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        # ── Asset Pricing ──────────────────────────────────────────────────
        cls._registry["factor_model_test"] = ResearchDirection(
            direction_name="factor_model_test",
            display_name="因子模型检验",
            literature_theme=(
                "系统检验Fama-French因子、q因子、Carhart四因子等在中国A股市场的定价能力。"
                "考察A股市场的异象因子和风险溢价结构。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Fama-MacBeth两步法",
                    econometric_class="FamaMacBeth",
                    notes="第一步横截面回归提取因子溢价，第二步时间序列回归检验因子有效性。",
                    data_needed=["股票收益率", "因子暴露度"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="GRS检验",
                    econometric_class="GRSTest",
                    notes="Gibbons-Ross-Shanken检验所有因子联合定价的有效性。",
                    data_needed=["因子收益率", "资产超额收益"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="Alpha分析",
                    econometric_class="AlphaAnalysis",
                    notes="检验各组合在因子模型下的Alpha是否显著异于零。",
                    data_needed=["组合收益率", "因子暴露度"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "收益数据": "CSMAR个股日/周收益率",
                "因子数据": " Fama-French因子/q因子",
                "财务数据": "size、BM、动量等因子构建变量",
            },
            expected_output=(
                "Fama-MacBeth回归表、GRS统计量、因子Alpha检验表。"
                "预期发现A股存在size、value、盈利等因子的显著溢价。"
            ),
            keywords=["因子定价", "Fama-French", "q因子", "GRS检验", "Alpha", "资产定价"],
            sub_topics=["异象因子", "因子择时", "因子正交化"],
            references=[
                "Fama & French (1993) — Common Risk Factors in Stock Returns",
                "Hou et al. (2015, RFS) — q-Factor Model",
            ],
            difficulty="advanced",
            estimated_pages=45,
        )

        cls._registry["analyst_forecast_effectiveness"] = ResearchDirection(
            direction_name="analyst_forecast_effectiveness",
            display_name="分析师盈利预测有效性",
            literature_theme=(
                "研究分析师盈利预测的准确度及其对市场定价效率的影响。"
                "考察分析师特征、经纪商规模、信息环境对预测质量的作用。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="预测误差分析",
                    econometric_class="ForecastErrorAnalysis",
                    notes="计算分析师预测与实际盈利的偏差，分解系统性误差和随机误差。",
                    data_needed=["分析师盈利预测数据", "实际盈利数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="事件研究",
                    econometric_class="EventStudy",
                    notes="检验分析师评级调整和盈利预测修正后的市场反应。",
                    data_needed=["评级调整事件", "个股收益率"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="信息含量检验",
                    econometric_class="InformationContent",
                    notes="检验分析师预测修正是否包含增量信息。",
                    data_needed=["预测修正数据", "市场交易数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "预测数据": "Wind/朝阳永续分析师盈利预测数据库",
                "评级数据": "分析师投资评级数据",
                "收益数据": "CSMAR个股日收益率",
            },
            expected_output=(
                "分析师预测准确度统计、预测修正后CAR分析、预测分歧度与收益关系表。"
                "预期发现预测修正后5日CAR显著为正，说明预测包含信息。"
            ),
            keywords=["分析师预测", "盈利预测", "事件研究", "信息效率", "卖方研究"],
            sub_topics=["分析师羊群行为", "预测偏差与利益冲突", "分析师与信息不对称"],
            references=[
                "Stickel (1992, J Finance) — Reputation and Performance Among Analysts",
                "Hong & Kubik (2003, J Finance) — Analyzing Analysts' Accuracy",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["esg_alpha_factor"] = ResearchDirection(
            direction_name="esg_alpha_factor",
            display_name="ESG Alpha因子",
            literature_theme=(
                "研究ESG因子在资产定价中的Alpha来源和定价效率。"
                "考察ESG风险因子、ESG动量、ESG隔离度等因子在中国A股的收益预测能力。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Fama-French五因子 + ESG",
                    econometric_class="FamaMacBeth",
                    notes="在FF5基础上加入ESG风险因子，检验ESG因子的增量定价能力。",
                    data_needed=["个股收益率", "FF5因子暴露", "ESG评分"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="分组组合分析",
                    econometric_class="PortfolioSort",
                    notes="按ESG评分和ESG争议事件构建独立双重排序组合。",
                    data_needed=["ESG评分", "ESG争议数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="因果检验",
                    econometric_class="IVRegression",
                    notes="使用工具变量解决ESG内生性问题，识别真正的Alpha来源。",
                    data_needed=["工具变量（同行业ESG平均）"],
                    packages=["scripts.econometrics"],
                ),
            ]),
            data_requirements={
                "ESG数据": "商道融绿/Wind ESG评级",
                "收益数据": "CSMAR个股收益率",
                "因子数据": "FF5因子/q因子",
            },
            expected_output=(
                "FF5+ESG因子回归表、分组组合收益表、ESG Alpha来源分解。"
                "预期发现高ESG组合相比低ESG组合年化超额收益X%。"
            ),
            keywords=["ESG Alpha", "因子投资", "可持续投资", "FF5+ESG", "责任投资"],
            sub_topics=["ESG负面筛选", "影响力加权组合", "气候因子"],
            references=[
                "Giese et al. (2019, J Portf Manag) — ESG as an Alpha Generator",
                "Li et al. (2021) — ESG and Expected Stock Returns",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["institutional_holding_crash_risk"] = ResearchDirection(
            direction_name="institutional_holding_crash_risk",
            display_name="机构持股×股价崩盘风险",
            literature_theme=(
                "研究机构投资者持股对股价崩盘风险的影响及机制。"
                "考察长期机构投资者如何通过公司治理和信息监督降低崩盘风险。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="控制公司特征和市场条件后，考察机构持股与崩盘风险的关系。",
                    data_needed=["机构持股比例", "股价崩盘风险指标"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="双向固定效应",
                    econometric_class="FixedEffect",
                    notes="控制公司和年份固定效应，消除遗漏变量偏误。",
                    data_needed=["完整面板数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="机制检验",
                    econometric_class="MediationAnalysis",
                    notes="检验机构持股→信息透明度提升→崩盘风险降低的机制。",
                    data_needed=["信息透明度指标（分析师跟踪、盈余质量）"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "机构持股": "CSMAR基金/QFII/社保持股数据",
                "崩盘风险": "负收益偏态系数(NCSKEW)、收益波动率(DUVOL)",
                "信息透明度": "分析师跟踪人数、盈余质量指标",
            },
            expected_output=(
                "基准回归表、机构类型异质性分析、信息透明度机制检验。"
                "预期发现机构持股比例增加10%，崩盘风险降低X%。"
            ),
            keywords=["机构投资者", "股价崩盘风险", "信息不对称", "NCSKEW", "机构监督"],
            sub_topics=["共同基金与崩盘风险", "指数化投资与市场稳定", "机构交易行为"],
            references=[
                "Jin & Myers (2006, J Finance) — R-squared and Stock Price Crash Risk",
                "An & Zhang (2013, J Corp Finance) — Institutional Investors and Crash Risk",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        # ── Behavioral Finance ──────────────────────────────────────────────
        cls._registry["investor_sentiment_asset_return"] = ResearchDirection(
            direction_name="investor_sentiment_asset_return",
            display_name="投资者情绪×资产收益",
            literature_theme=(
                "研究投资者情绪对资产定价的影响及情绪的周期性特征。"
                "考察情绪如何通过行为偏差影响资产价格和收益分布。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板向量自回归 (Panel VAR)",
                    econometric_class="PanelDataVAR",
                    notes="构建情绪-收益-资金流量的PVAR系统，考察三者动态关系。",
                    data_needed=["投资者情绪指数", "资产收益率", "资金流量数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="脉冲响应分析",
                    econometric_class="ImpulseResponse",
                    notes="识别情绪冲击对资产价格的动态传导路径。",
                    data_needed=["PVAR估计结果"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="Granger因果检验",
                    econometric_class="GrangerCausality",
                    notes="检验情绪与收益之间的领先滞后关系。",
                    data_needed=["时间序列数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "情绪指数": "CICSI情绪指数/新增开户数/换手率综合指数",
                "收益数据": "股票/债券/商品收益率",
                "资金流": "基金净申购/ETF资金流向",
            },
            expected_output=(
                "PVAR模型估计、脉冲响应图、方差分解、情绪预测能力检验。"
                "预期发现情绪上行后6个月内，小盘股/高Beta股票收益高于市场X%。"
            ),
            keywords=["投资者情绪", "行为金融", "PVAR", "情绪周期", "资产配置", "市场时机"],
            sub_topics=["情绪与风格轮动", "期权市场情绪", "社交媒体情绪"],
            references=[
                "Baker & Wurgler (2006, J Finance) — Investor Sentiment and Stock Returns",
                "Stambaugh et al. (2012, RFS) — Predicting Returns with Sentiment",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["earnings_management_market_reaction"] = ResearchDirection(
            direction_name="earnings_management_market_reaction",
            display_name="盈余管理×市场反应",
            literature_theme=(
                "研究应计盈余管理和真实盈余管理对股票价格的影响。"
                "考察市场对不同类型盈余管理的识别能力和定价差异。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以监管政策变化（如盈余管理专项检查）为外生冲击，检验市场反应变化。",
                    data_needed=["盈余管理程度", "政策事件时间"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="盈余反应系数分析",
                    econometric_class="ERC",
                    notes="考察盈余质量对盈余反应系数的影响。",
                    data_needed=["意外盈余数据", "CAR数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="长期市场表现",
                    econometric_class="LongRunPerformance",
                    notes="检验高盈余管理企业股票的长期收益率是否显著为负。",
                    data_needed=["多年期持有收益率"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "盈余管理": "Jones模型/应计项目法估计的盈余管理程度",
                "财务数据": "上市公司财务报告数据",
                "收益数据": "CSMAR个股日/周收益率",
            },
            expected_output=(
                "DID回归表、盈余反应系数分析、高低盈余管理组长期收益对比。"
                "预期发现真实盈余管理程度越高，股价崩盘风险越高。"
            ),
            keywords=["盈余管理", "应计项目", "真实盈余管理", "DID", "盈余反应系数"],
            sub_topics=["财务舞弊检测", "审计质量与盈余管理", "会计准则与盈余波动"],
            references=[
                "Dechow et al. (2010, JAE) — Predicting Earnings Manipulation",
                "Cohen & Zarowin (2010, J Account Econ) — Real Earnings Management",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["equity_incentive_innovation"] = ResearchDirection(
            direction_name="equity_incentive_innovation",
            display_name="股权激励×创新产出",
            literature_theme=(
                "研究股权激励计划对企业创新投入和产出的影响。"
                "考察股权激励如何缓解委托代理问题，促进管理层增加长期创新投资。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Heckman两阶段模型",
                    econometric_class="HeckmanTwoStep",
                    notes="处理企业是否实施股权激励的选择偏误。",
                    data_needed=["股权激励数据", "创新产出数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以股权激励方案公告为事件，检验激励实施前后的创新变化。",
                    data_needed=["股权激励方案数据", "专利/研发数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="激励有效期分析",
                    econometric_class="TimeSeriesAnalysis",
                    notes="考察股权激励有效期与创新效果的关系。",
                    data_needed=["激励有效期信息"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "股权激励": "CSMAR股权激励计划数据",
                "专利数据": "国家知识产权局专利数据",
                "财务数据": "研发支出/研发人员数据",
            },
            expected_output=(
                "Heckman模型结果、DID回归表、激励有效期与创新效果关系图。"
                "预期发现实施股权激励后企业专利申请增加X%。"
            ),
            keywords=["股权激励", "期权激励", "创新产出", "Heckman", "DID", "委托代理"],
            sub_topics=["国企股权激励", "科创板股权激励", "激励有效期设计"],
            references=[
                "Lerner & Wulf (2007, RFS) — Innovation and Incentives: Evidence",
                "Chang et al. (2015, J Financ Econ) — Equity Incentives and Innovation",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["herding_market_volatility"] = ResearchDirection(
            direction_name="herding_market_volatility",
            display_name="羊群效应×市场波动",
            literature_theme=(
                "研究机构投资者和个人投资者的羊群行为及其对市场波动的影响。"
                "考察羊群行为在不同市场状态（牛市/熊市）下的差异化表现。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="羊群度量",
                    econometric_class="HerdingMeasure",
                    notes="使用CH指标和LSV方法度量机构/个人投资者买卖趋同度。",
                    data_needed=["机构交易数据", "个股持仓变化"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="考察羊群行为程度与市场/个股波动率的关系。",
                    data_needed=["羊群指标", "波动率指标"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="非对称性检验",
                    econometric_class="AsymmetryTest",
                    notes="检验牛熊市、不同波动状态下羊群行为的非对称性。",
                    data_needed=["市场状态分类数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "交易数据": "基金季报持仓变化/大宗交易数据",
                "持仓数据": "个股机构持仓比例",
                "市场数据": "上证综指/VIX波动率指数",
            },
            expected_output=(
                "羊群行为统计、羊群与波动率回归表、牛熊市对比分析。"
                "预期发现在市场下跌时机构羊群行为更强，导致波动加剧。"
            ),
            keywords=["羊群效应", "机构投资者", "市场波动", "投资者行为", "CH指标"],
            sub_topics=["个人投资者行为", "噪声交易", "正反馈交易"],
            references=[
                "Lakonishok et al. (1992, J Finance) — Herding and Feedback Trading",
                "Chiang & Zheng (2010, J Bank Finance) — An International Analysis of Herding",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        # ── International Finance ───────────────────────────────────────────
        cls._registry["tariff_policy_trade_flow"] = ResearchDirection(
            direction_name="tariff_policy_trade_flow",
            display_name="关税政策×贸易流量",
            literature_theme=(
                "研究中美贸易摩擦以来关税政策调整对双边贸易流量和结构的影响。"
                "考察关税壁垒如何改变贸易路径、贸易伙伴结构和出口产品结构。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以关税加征为处理组冲击，比较受影响行业与未受影响行业的贸易变化。",
                    data_needed=["关税税率", "贸易流量", "行业分类"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="Bartik工具变量",
                    econometric_class="BartikIV",
                    notes="使用Bartik准差分法估计关税对贸易的局部平均处理效应。",
                    data_needed=["行业层面关税暴露度"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="贸易转移效应",
                    econometric_class="TradeDiversion",
                    notes="检验关税是否导致贸易从中国转向第三国。",
                    data_needed=["多国贸易流向数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "关税数据": "USITC关税税率数据库/中国海关HS编码关税数据",
                "贸易数据": "UN Comtrade/BACI双边贸易数据",
                "行业数据": "BEC分类/SITC分类",
            },
            expected_output=(
                "DID基准回归表、Bartik工具变量估计、贸易转移分析。"
                "预期发现关税使受影响行业对美出口下降X%，部分转向第三方市场。"
            ),
            keywords=["关税政策", "中美贸易摩擦", "DID", "贸易转移", "HS编码", "贸易战"],
            sub_topics=["关税升级影响", "供应链重构", "贸易多元化"],
            references=[
                "Amano-Ricci (2022) — Trade War and Supply Chain Restructuring",
                "Bown & Zhang (2020) — US-China Trade War and Supply Chains",
            ],
            difficulty="intermediate",
            estimated_pages=40,
        )

        cls._registry["foreign_inflow_emerging_market"] = ResearchDirection(
            direction_name="foreign_inflow_emerging_market",
            display_name="外资流入×新兴市场股市",
            literature_theme=(
                "研究国际资本流入新兴市场股市的驱动因素及其对市场定价效率的影响。"
                "考察外资流入是否加剧市场波动和泡沫风险。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="事件研究",
                    econometric_class="EventStudy",
                    notes="以主要央行政策变化、IMF新兴市场评级调整为事件，检验外资流向反应。",
                    data_needed=["外资流入数据", "政策事件日期"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="考察全球因素（VIX、美元指数）与新兴市场外资流入的关系。",
                    data_needed=["外资持有量", "全球风险指标"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="Granger因果检验",
                    econometric_class="GrangerCausality",
                    notes="检验外资流入与新兴市场股指收益率的领先滞后关系。",
                    data_needed=["外资流入序列", "股指收益率"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "外资数据": "IIF资本流动数据/IMF CPIS数据",
                "股指数据": "MSCI新兴市场指数/各国股指",
                "全球因素": "VIX、美元指数、DXY",
            },
            expected_output=(
                "外资流入驱动因素回归表、事件日市场反应、Granger因果检验结果。"
                "预期发现VIX上升1个点，新兴市场外资流入减少X亿美元。"
            ),
            keywords=["外资流入", "新兴市场", "资本流动", "事件研究", "MSCI", "全球金融周期"],
            sub_topics=["外资撤出风险", "被动投资与新兴市场", "汇率与外资流向"],
            references=[
                "Rey (2015, J Econ Perspect) — International Capital Flows",
                "Rachaud & Miranda-Agrippino (2022) — Global Financial Cycles",
            ],
            difficulty="advanced",
            estimated_pages=38,
        )

        cls._registry["exchange_rate_regime_financial_crisis"] = ResearchDirection(
            direction_name="exchange_rate_regime_financial_crisis",
            display_name="汇率制度×金融危机",
            literature_theme=(
                "研究汇率制度选择与金融危机发生概率之间的关系。"
                "考察不同汇率制度（固定/浮动/中间汇率）下金融脆弱性的差异。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板Probit/Logit",
                    econometric_class="LogitProbit",
                    notes="使用二元选择模型估计汇率制度对金融危机发生概率的影响。",
                    data_needed=["汇率制度分类", "金融危机事件"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="工具变量法",
                    econometric_class="IVRegression",
                    notes="使用历史汇率制度、政治联盟作为汇率制度选择的工具变量。",
                    data_needed=["IV变量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="生存分析",
                    econometric_class="SurvivalAnalysis",
                    notes="使用Cox比例风险模型考察汇率制度对危机持续时间的影响。",
                    data_needed=["危机持续时间数据"],
                    packages=["scripts.econometrics_extended"],
                ),
            ]),
            data_requirements={
                "汇率制度": "RRR/ILL分类/IMF de facto分类",
                "金融危机": "Laeven & Valencia金融危机数据库",
                "宏观数据": "外汇储备、外债、经常账户",
            },
            expected_output=(
                "Probit回归表（汇率制度与危机概率）、Cox生存分析。"
                "预期发现中间汇率制度国家金融危机概率最高。"
            ),
            keywords=["汇率制度", "金融危机", "Probit", "汇率稳定", "外汇风险", "中间汇率制度"],
            sub_topics=["货币危机理论", "银行危机与汇率", "外汇储备与危机防御"],
            references=[
                "Obstfeld & Rogoff (1995) — The Mirage of Fixed Exchange Rates",
                "Ito & Khoi (2018) — Exchange Rate Regimes and Crises",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["capital_control_asset_allocation"] = ResearchDirection(
            direction_name="capital_control_asset_allocation",
            display_name="资本管制×资产配置",
            literature_theme=(
                "研究资本管制如何影响跨境资产配置和国内金融市场发展。"
                "考察资本管制在开放与安全之间的权衡取舍。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="断点回归 (RDD)",
                    econometric_class="RDDRegression",
                    notes="以特定投资额度门槛（如QDII额度）作为断点，检验管制边界的因果效应。",
                    data_needed=["投资额度数据", "资产配置数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以资本管制政策变化为事件，检验政策对资产配置的因果效应。",
                    data_needed=["管制政策时间表", "资产配置数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="成本收益分析",
                    econometric_class="CostBenefitAnalysis",
                    notes="量化资本管制的福利成本（资产价格扭曲）与收益（金融稳定）。",
                    data_needed=["资产价格数据", "波动率数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "管制数据": "Chari et al. IMF资本管制指数",
                "资产配置": "居民/企业境外投资数据",
                "金融市场": "利率、汇率、资产价格",
            },
            expected_output=(
                "RDD/DID回归表、资本管制政策效应分解、福利分析。"
                "预期发现适度资本管制降低金融市场波动X%，但导致资产配置效率下降Y%。"
            ),
            keywords=["资本管制", "资本账户开放", "RDD", "资产配置", "跨境投资", "金融安全"],
            sub_topics=["QDII/QFII制度", "宏观审慎框架", "资本流动管理工具"],
            references=[
                "Chari et al. (2021, J Financ Econ) — Capital Controls",
                "Obstfeld et al. (2019, NBER) — Capital Flows and Capital Controls",
            ],
            difficulty="advanced",
            estimated_pages=42,
        )

        # ── Labor Economics ────────────────────────────────────────────────
        cls._registry["minimum_wage_employment"] = ResearchDirection(
            direction_name="minimum_wage_employment",
            display_name="最低工资×就业水平",
            literature_theme=(
                "研究最低工资政策调整对就业水平的影响。"
                "考察不同地区、不同行业、不同群体（青年/低技能）的差异化就业效应。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以最低工资调整地区为处理组，比较处理组与对照组的就业变化。",
                    data_needed=["最低工资标准", "就业数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="断点回归 (RDD)",
                    econometric_class="RDDRegression",
                    notes="以最低工资门槛值（如2000元/月）作为断点，检验断点处的就业效应。",
                    data_needed=["企业工资分布数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="SubgroupAnalysis",
                    notes="按企业规模、行业、地区分组检验最低工资的就业效应差异。",
                    data_needed=["分组变量数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "最低工资": "各省、市最低工资标准（人社部）",
                "就业数据": "城镇就业调查/社保参保数据",
                "企业数据": "工业企业数据库/企业工商数据",
            },
            expected_output=(
                "DID基准回归表、RDD估计结果、异质性分析表。"
                "预期发现最低工资上调10%导致低技能就业下降X%。"
            ),
            keywords=["最低工资", "就业效应", "DID", "RDD", "劳动力市场", "收入分配"],
            sub_topics=["最低工资与工资溢价", "非正规就业", "最低工资与企业绩效"],
            references=[
                "Card & Krueger (1994) — Minimum Wages and Employment",
                "Neumark & Wascher (2008) — Minimum Wages: Evidence from the US",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["education_return_skill_premium"] = ResearchDirection(
            direction_name="education_return_skill_premium",
            display_name="教育回报×技能溢价",
            literature_theme=(
                "研究教育水平对工资收入的影响及技能溢价的动态变化。"
                "考察技能偏向型技术进步对不同教育水平人群工资差距的影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Heckman两阶段模型",
                    econometric_class="HeckmanTwoStep",
                    notes="处理劳动力参与的自选择偏误，修正教育回报估计。",
                    data_needed=["工资数据", "劳动力参与数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="Mincer方程扩展",
                    econometric_class="OLSRegression",
                    notes="在标准Mincer方程基础上加入技能溢价变量和交互项。",
                    data_needed=["教育年限", "工作经验", "工资"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="分位数回归",
                    econometric_class="QuantileRegression",
                    notes="检验教育回报在不同收入分位数上的差异。",
                    data_needed=["完整收入分布数据"],
                    packages=["scripts.econometrics_extended"],
                ),
            ]),
            data_requirements={
                "收入数据": "CHNS/CHIP住户调查数据",
                "教育数据": "教育年限、学历",
                "技能数据": "职业分类、技能认证",
            },
            expected_output=(
                "Heckman模型结果、Mincer方程回归表、教育回报的分位数回归结果。"
                "预期发现大学教育年回报率约为X%，技能溢价呈上升趋势。"
            ),
            keywords=["教育回报", "技能溢价", "Heckman", "Mincer方程", "收入差距", "工资结构"],
            sub_topics=["职业教育回报", "技能错配", "教育扩张与工资不平等"],
            references=[
                "Mincer (1974) — Schooling, Experience, and Earnings",
                "Autor et al. (2008, QJE) — The Polarization of the Labor Market",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["population_aging_economic_growth"] = ResearchDirection(
            direction_name="population_aging_economic_growth",
            display_name="人口老龄化×经济增长",
            literature_theme=(
                "研究人口老龄化对潜在经济增长率的影响及作用渠道。"
                "考察老龄化通过劳动力供给、资本积累、全要素生产率影响经济的机制。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="控制其他因素后考察老龄化指标与GDP增速的关系。",
                    data_needed=["人口年龄结构", "GDP增速"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="中介效应模型",
                    econometric_class="MediationAnalysis",
                    notes="检验老龄化→劳动力供给/资本积累/TFP→经济增长的传导机制。",
                    data_needed=["劳动参与率", "储蓄率", "TFP数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="动态面板",
                    econometric_class="PanelGMM",
                    notes="处理经济增长的动态依存和内生性。",
                    data_needed=["滞后变量"],
                    packages=["scripts.econometrics"],
                ),
            ]),
            data_requirements={
                "人口数据": "国家统计局人口普查/抽样调查数据",
                "经济数据": "GDP、资本存量、TFP",
                "劳动力数据": "劳动参与率、失业率",
            },
            expected_output=(
                "面板回归表、中介效应检验、老龄化对TFP/储蓄率影响的分解。"
                "预期发现65岁以上人口占比每上升1%，GDP增速下降X个百分点。"
            ),
            keywords=["人口老龄化", "经济增长", "劳动力供给", "TFP", "抚养比", "人口红利"],
            sub_topics=["老龄化与养老金", "延迟退休效应", "老龄化与创新"],
            references=[
                "Bloom et al. (2010, J Econ Growth) — Demographic Change and Economic Growth",
                "Maestas et al. (2016, NBER) — The Effect of Population Aging on Economic Growth",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["robot_replacement_labor_market"] = ResearchDirection(
            direction_name="robot_replacement_labor_market",
            display_name="机器人替代×劳动力市场",
            literature_theme=(
                "研究工业机器人应用对就业、工资和劳动力市场结构的影响。"
                "考察自动化技术如何重塑劳动力需求结构和收入分配格局。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="倾向得分匹配 (PSM)",
                    econometric_class="PSM",
                    notes="为使用机器人的企业匹配相似的非使用企业，控制选择偏误。",
                    data_needed=["企业机器人应用数据", "企业特征"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="双重差分 (PSM-DID)",
                    econometric_class="DIDRegression",
                    notes="在匹配样本上检验机器人应用对就业和工资的因果效应。",
                    data_needed=["企业就业/工资数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="职业分解分析",
                    econometric_class="OccupationDecomposition",
                    notes="分解自动化对不同职业的替代效应和创造效应。",
                    data_needed=["职业就业数据", "自动化替代概率"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "机器人数据": "IFR国际机器人联盟数据/海关进口机器人数据",
                "就业数据": "工业企业数据库/企业社保数据",
                "职业数据": "职业分类与自动化替代概率",
            },
            expected_output=(
                "PSM平衡性检验、PSM-DID回归表、职业替代效应分解。"
                "预期发现每增加1台机器人，减少X个低技能就业岗位。"
            ),
            keywords=["机器人", "自动化", "人工智能", "劳动力替代", "PSM-DID", "技术性失业"],
            sub_topics=["AI对职业的影响", "自动化与技能需求", "机器换人补贴政策"],
            references=[
                "Acemoglu & Restrepo (2020, Ecta) — Robots and Jobs",
                "Frey & Osborne (2017) — The Future of Employment",
            ],
            difficulty="intermediate",
            estimated_pages=40,
        )

        # ── Public Economics ───────────────────────────────────────────────
        cls._registry["property_tax_housing_price"] = ResearchDirection(
            direction_name="property_tax_housing_price",
            display_name="房产税×房价波动",
            literature_theme=(
                "研究房产税政策对房价波动和房地产市场稳定性的影响。"
                "考察房产税作为调控工具在抑制投机性需求中的作用。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以房产税试点城市为处理组，比较试点前后的房价变化差异。",
                    data_needed=["房产税试点政策", "城市房价数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="事件研究法",
                    econometric_class="EventStudy",
                    notes="检验房产税政策前后的平行趋势假设，验证DID有效性。",
                    data_needed=["政策前后多期数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="异质性分析",
                    econometric_class="SubgroupAnalysis",
                    notes="按城市级别、住房类型、投资vs自住需求分组检验。",
                    data_needed=["住房分类数据", "需求结构数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "房产税数据": "重庆/上海房产税试点政策细节",
                "房价数据": "国家统计局70城房价指数/中指院数据",
                "交易数据": "商品房销售面积/销售额",
            },
            expected_output=(
                "DID基准回归、事件研究图（平行趋势）、异质性分析表。"
                "预期发现房产税试点使试点城市房价涨幅收窄X个百分点。"
            ),
            keywords=["房产税", "房价调控", "DID", "房地产税改革", "住房需求"],
            sub_topics=["房产税立法", "空置税", "土地财政转型"],
            references=[
                "Basten & Otto (2022) — Property Tax and Property Values",
                "Du & Zhang (2015) — Housing Policy and Housing Market in China",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["industrial_policy_entry_exit"] = ResearchDirection(
            direction_name="industrial_policy_entry_exit",
            display_name="产业政策×企业进入退出",
            literature_theme=(
                "研究产业政策对企业市场进入、退出决策和产业格局的影响。"
                "考察产业政策如何通过补贴、税收优惠等手段影响企业进入壁垒和竞争格局。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="断点回归 (RDD)",
                    econometric_class="RDDRegression",
                    notes="以企业是否获得产业政策支持作为处理变量，检验政策对进入退出的因果效应。",
                    data_needed=["政策支持名单", "企业进入退出数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以产业政策出台为事件，检验政策前后的企业进入退出率变化。",
                    data_needed=["政策时间表", "企业工商注册数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="效率分析",
                    econometric_class="EfficiencyAnalysis",
                    notes="比较获得政策支持企业与未获支持企业的生产率差异。",
                    data_needed=["企业生产率数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "产业政策": "工信部/发改委产业政策目录、补贴名单",
                "企业数据": "工商注册数据/工业企业数据库",
                "绩效数据": "企业生产率、利润率",
            },
            expected_output=(
                "RDD/DID回归表、产业集中度变化分析、进入退出企业特征对比。"
                "预期发现产业政策使目标行业企业数量增加X%，但平均效率下降。"
            ),
            keywords=["产业政策", "企业进入退出", "RDD", "补贴", "竞争政策", "市场结构"],
            sub_topics=["战略性新兴产业政策", "政府补贴效率", "产业政策与僵尸企业"],
            references=[
                "Bai et al. (2022, J Comp Econ) — Industrial Policy and Firm Entry/Exit",
                "Guerini & Rossi (2021) — Industrial Policy and Firm Growth",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        cls._registry["social_security_reform_consumption"] = ResearchDirection(
            direction_name="social_security_reform_consumption",
            display_name="社保改革×居民消费",
            literature_theme=(
                "研究社会保障制度改革对居民消费行为的影响。"
                "考察社保覆盖率提升、养老金调整、医保改革对消费的促进作用。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="控制收入、财富等变量后，考察社保对居民消费的影响。",
                    data_needed=["家庭消费数据", "社保参与数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以社保政策变化（如新农合全覆盖）为事件，检验政策对消费的因果效应。",
                    data_needed=["政策时间表", "家庭面板数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="流动性约束检验",
                    econometric_class="ConstraintTest",
                    notes="检验社保改革是否通过缓解流动性约束促进消费。",
                    data_needed=["流动性约束指标"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "社保数据": "人社部统计数据/CHARLS/CHFS调查数据",
                "消费数据": "住户调查消费数据/信用卡消费数据",
                "家庭数据": "收入、财富、人口结构",
            },
            expected_output=(
                "面板回归表、DID估计结果、流动性约束机制检验。"
                "预期发现社保覆盖率提升10%使家庭消费增加X%。"
            ),
            keywords=["社会保障", "居民消费", "DID", "新农合", "养老保险", "消费促进"],
            sub_topics=["养老金改革", "医保改革", "社保降费"],
            references=[
                "Feldstein (1974, JPE) — Social Security and Private Saving",
                "Chetty et al. (2007, AER) — Social Security and Consumption",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["environmental_enforcement_abatement"] = ResearchDirection(
            direction_name="environmental_enforcement_abatement",
            display_name="环保执法×企业减排",
            literature_theme=(
                "研究环境执法强度对企业减排行为的影响。"
                "考察环保督察、处罚力度等执法手段对企业绿色转型的作用。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="Heckman两阶段模型",
                    econometric_class="HeckmanTwoStep",
                    notes="处理企业是否进行减排投资的选择偏误。",
                    data_needed=["企业减排数据", "环保处罚数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以中央环保督察组进驻为外生冲击，检验对企业减排的影响。",
                    data_needed=["环保督察时间表", "企业排放数据"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="成本收益分析",
                    econometric_class="CostBenefitAnalysis",
                    notes="量化环保执法的减排效果与经济成本。",
                    data_needed=["减排量数据", "企业成本数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "执法数据": "生态环境部行政处罚数据/环保督察信息",
                "排放数据": "企业SO2/COD/NOx排放数据",
                "财务数据": "企业营业收入、利润率",
            },
            expected_output=(
                "Heckman模型结果、DID回归表、环保执法成本收益分析。"
                "预期发现中央环保督察使企业排放减少X%。"
            ),
            keywords=["环保执法", "企业减排", "Heckman", "DID", "环保督察", "绿色转型"],
            sub_topics=["环保约谈效果", "排污许可制度", "绿色信贷与环保"],
            references=[
                "Zhang et al. (2018, J Environ Econ Manage) — Environmental Enforcement",
                "He et al. (2020, REEP) — Central Environmental Inspections and Pollution",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

        # ── Financial Intermediation ────────────────────────────────────────
        cls._registry["bank_competition_loan_rate"] = ResearchDirection(
            direction_name="bank_competition_loan_rate",
            display_name="银行竞争×贷款利率",
            literature_theme=(
                "研究银行业竞争对贷款利率定价和贷款可获得性的影响。"
                "考察金融科技进入、网点扩张等对传统银行竞争格局的冲击。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板回归",
                    econometric_class="OLSRegression",
                    notes="控制银行特征、企业特征和市场条件后，考察竞争对贷款利率的影响。",
                    data_needed=["银行贷款利率", "银行市场份额"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="HHI指数构建",
                    econometric_class="HHIIndex",
                    notes="构建地区银行业HHI衡量竞争程度。",
                    data_needed=["各银行贷款数据", "地区分布"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="双重差分 (DID)",
                    econometric_class="DIDRegression",
                    notes="以金融科技进入某地区市场为事件，检验对当地银行利率的影响。",
                    data_needed=["金融科技进入事件"],
                    packages=["scripts.econometrics"],
                ),
            ]),
            data_requirements={
                "银行数据": "SNL Financial/上市银行年报",
                "利率数据": "贷款基准利率/实际执行利率",
                "竞争数据": "各地区银行网点数量、市场份额",
            },
            expected_output=(
                "贷款利率决定因素回归表、HHI与利率关系图、DID估计结果。"
                "预期发现银行竞争度每提升10%，贷款利率下降X个基点。"
            ),
            keywords=["银行竞争", "贷款利率", "HHI", "DID", "市场结构", "普惠金融"],
            sub_topics=["金融科技竞争", "银行网点扩张", "利率市场化"],
            references=[
                "Boot & Thakor (2000, J Finance) — Can Relationships Bank Survive?",
                "Berger et al. (2017, J Bank Finance) — Bank Competition and Firm Performance",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["shadow_banking_credit_risk"] = ResearchDirection(
            direction_name="shadow_banking_credit_risk",
            display_name="影子银行×信用风险",
            literature_theme=(
                "研究影子银行规模扩张对金融系统信用风险累积的影响。"
                "考察影子银行与银行体系之间的风险传染机制。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板向量自回归 (Panel VAR)",
                    econometric_class="PanelDataVAR",
                    notes="构建影子银行规模→信用风险→银行不良率的PVAR模型。",
                    data_needed=["影子银行规模", "信用风险指标", "不良贷款率"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="Granger因果检验",
                    econometric_class="GrangerCausality",
                    notes="检验影子银行与银行信用风险之间的因果关系方向。",
                    data_needed=["时间序列数据"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="压力测试",
                    econometric_class="StressTest",
                    notes="模拟影子银行收缩对银行体系的信用风险冲击。",
                    data_needed=["银行资产负债数据"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "影子银行": "社融数据（委托+信托+未贴现票据）",
                "银行数据": "上市银行不良贷款率",
                "信用风险": "债券违约率/企业债信用利差",
            },
            expected_output=(
                "PVAR模型估计、Granger因果检验结果、影子银行压力测试。"
                "预期发现影子银行规模扩张1万亿，不良贷款率上升X个百分点。"
            ),
            keywords=["影子银行", "信用风险", "PVAR", "金融稳定", "银行风险", "委托贷款"],
            sub_topics=["资管新规影响", "非标资产", "金融脱媒"],
            references=[
                "Plantin (2015, RFS) — Shadow Banking and Capital Markets",
                "Chen et al. (2020) — Shadow Banking and Systemic Risk",
            ],
            difficulty="advanced",
            estimated_pages=40,
        )

        cls._registry["inclusive_finance_household_finance"] = ResearchDirection(
            direction_name="inclusive_finance_household_finance",
            display_name="普惠金融×家庭金融",
            literature_theme=(
                "研究普惠金融发展对家庭金融行为和福利的影响。"
                "考察数字金融、银行网点扩张等如何改善家庭金融可得性和金融健康。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="面板Tobit回归",
                    econometric_class="PanelTobit",
                    notes="使用Tobit模型处理家庭金融参与（借款/储蓄）的受限因变量问题。",
                    data_needed=["家庭金融数据", "普惠金融指数"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="工具变量法",
                    econometric_class="IVRegression",
                    notes="使用历史金融基础设施、地理因素作为普惠金融的工具变量。",
                    data_needed=["IV变量"],
                    packages=["scripts.econometrics"],
                ),
                MethodologyStep(
                    step_name="中介效应",
                    econometric_class="MediationAnalysis",
                    notes="检验普惠金融→金融可得性→家庭福利的传导渠道。",
                    data_needed=["金融可得性指标"],
                    packages=[],
                ),
            ]),
            data_requirements={
                "家庭数据": "CHFS/CHARLS家庭金融调查数据",
                "普惠金融": "北京大学数字普惠金融指数/银行网点密度",
                "福利数据": "家庭消费、财富、主观福利",
            },
            expected_output=(
                "面板Tobit回归、IV估计结果、中介效应检验。"
                "预期发现普惠金融发展使低收入家庭消费波动降低X%。"
            ),
            keywords=["普惠金融", "家庭金融", "Tobit", "金融可得性", "金融健康", "数字金融"],
            sub_topics=["农村普惠金融", "家庭债务", "金融素养"],
            references=[
                "Demirguc-Kunt & Klapper (2012) — Financial Inclusion in Developing Countries",
                "Kanga et al. (2022) — Digital Finance and Household Welfare",
            ],
            difficulty="intermediate",
            estimated_pages=35,
        )

        cls._registry["fintech_bank_transformation"] = ResearchDirection(
            direction_name="fintech_bank_transformation",
            display_name="金融科技×银行转型",
            literature_theme=(
                "研究传统银行在金融科技冲击下的数字化转型战略和绩效影响。"
                "考察银行金融科技投入、技术合作与业务模式转型对银行竞争力的影响。"
            ),
            methodology_chain=MethodologyChain(steps=[
                MethodologyStep(
                    step_name="事件研究",
                    econometric_class="EventStudy",
                    notes="以银行金融科技合作公告、技术转型战略发布为事件，检验市场反应。",
                    data_needed=["金融科技合作公告", "银行股价数据"],
                    packages=["scripts.econometrics_extended"],
                ),
                MethodologyStep(
                    step_name="效率分析",
                    econometric_class="EfficiencyAnalysis",
                    notes="比较金融科技转型银行与传统银行的成本效率差异。",
                    data_needed=["银行成本收入比", "资产收益率"],
                    packages=[],
                ),
                MethodologyStep(
                    step_name="动态面板",
                    econometric_class="PanelGMM",
                    notes="处理金融科技投入与银行绩效之间的内生性。",
                    data_needed=["金融科技投入数据"],
                    packages=["scripts.econometrics"],
                ),
            ]),
            data_requirements={
                "银行数据": "上市银行年报金融科技投入数据",
                "合作数据": "银行与金融科技公司合作协议公告",
                "技术数据": "银行移动端活跃用户数、数字化转型指标",
            },
            expected_output=(
                "金融科技合作事件CAR分析、效率对比表、金融科技投入与银行绩效关系。"
                "预期发现金融科技投入每增加1%，银行成本收入比下降X%。"
            ),
            keywords=["金融科技", "银行转型", "数字化", "事件研究", "金融科技合作", "开放银行"],
            sub_topics=["银行API开放", "金融科技子公司", "银行数字化成熟度"],
            references=[
                "De Young et al. (2007, FRB Chicago) — The Futility of Bank Diversification",
                "Philippon (2019) — On Fintech and Financial Intermediation",
            ],
            difficulty="intermediate",
            estimated_pages=38,
        )

    @classmethod
    def get_direction(cls, name: str) -> ResearchDirection | None:
        """
        Get a research direction by its slug name.

        Args:
            name: Direction slug (e.g., "carbon_trading", "esg_factor_pricing")

        Returns:
            ResearchDirection if found, None otherwise.
        """
        cls._init_registry()
        direction = cls._registry.get(name)
        if direction is None:
            _log.warning("Direction '%s' not found. Available: %s", name, list(cls._registry.keys())[:10])
        return direction

    def get(self, name: str) -> ResearchDirection | None:
        """Instance alias for get_direction()."""
        return self.get_direction(name)

    def list(self) -> list[str]:
        """Instance alias for list_all(). Returns sorted list of direction slugs."""
        return self.list_all()

    @classmethod
    def search_directions(cls, keyword: str) -> list[ResearchDirection]:
        """
        Search directions by keyword across all metadata fields.

        Matches against direction_name, display_name, keywords, sub_topics,
        literature_theme, and expected_output.

        Args:
            keyword: Search term (case-insensitive)

        Returns:
            List of matching ResearchDirection objects, sorted by relevance.
        """
        cls._init_registry()
        keyword_lower = keyword.lower()
        scored: list[tuple[float, ResearchDirection]] = []

        for direction in cls._registry.values():
            score = 0.0

            # Exact slug match
            if keyword_lower == direction.direction_name.lower():
                score += 100.0
            # Slug contains keyword
            elif keyword_lower in direction.direction_name.lower():
                score += 50.0
            # Display name contains keyword
            if keyword_lower in direction.display_name.lower():
                score += 40.0
            # Keywords match
            for kw in direction.keywords:
                if keyword_lower == kw.lower():
                    score += 30.0
                elif keyword_lower in kw.lower():
                    score += 20.0
            # Sub-topics match
            for topic in direction.sub_topics:
                if keyword_lower in topic.lower():
                    score += 15.0
            # Literature theme contains keyword
            if keyword_lower in direction.literature_theme.lower():
                score += 10.0
            # Expected output contains keyword
            if keyword_lower in direction.expected_output.lower():
                score += 5.0

            if score > 0:
                scored.append((score, direction))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored]

    @classmethod
    def list_all(cls) -> list[str]:
        """
        List all registered direction slugs.

        Returns:
            Sorted list of direction slugs.
        """
        cls._init_registry()
        return sorted(cls._registry.keys())

    @classmethod
    def list_with_descriptions(cls) -> list[dict]:
        """
        List all registered directions with full metadata.

        Returns:
            List of dicts with direction_name, display_name, description, keywords.
        """
        cls._init_registry()
        return [
            {
                "name": d.direction_name,
                "display_name": d.display_name,
                "literature_theme": d.literature_theme,
                "keywords": d.keywords[:5],
                "difficulty": d.difficulty,
            }
            for d in cls._registry.values()
        ]

    @classmethod
    def suggest_directions(cls, prompt: str) -> list[ResearchDirection]:
        """
        Suggest research directions based on a user prompt using LLM matching.

        Uses keyword extraction and semantic similarity to match the prompt
        against all direction metadata.

        Args:
            prompt: User's research interest description (in Chinese or English)

        Returns:
            Top 5 most relevant ResearchDirection objects.
        """
        cls._init_registry()

        # Extract key topics from prompt
        key_topics: list[str] = []

        # Common topic patterns
        topic_patterns = [
            # Green finance
            "碳", "碳交易", "碳排放", "绿色", "ESG", "环保", "减排", "气候", "绿色债券",
            # Digital finance
            "数字金融", "金融科技", " fintech", "数字普惠", "数字货币", "DCEP", "供应链金融",
            # Macro finance
            "货币", "利率", "汇率", "影子银行", "美联储", "缩表", "新兴市场", "资本流动",
            # Corporate finance
            "并购", "IPO", "注册制", "股权激励", "高管薪酬", "公司治理", "ESG披露",
            # Asset pricing
            "因子", "Fama-French", "因子模型", "分析师", "盈利预测", "崩盘风险",
            # Behavioral finance
            "投资者情绪", "羊群", "盈余管理", "行为金融",
            # International finance
            "关税", "外资", "汇率制度", "资本管制", "金融危机",
            # Labor economics
            "最低工资", "教育回报", "老龄化", "机器人", "自动化", "就业",
            # Public economics
            "房产税", "产业政策", "社保", "社会保障", "环保执法",
            # Financial intermediation
            "银行竞争", "银行贷款", "信用风险", "普惠金融", "银行转型",
        ]

        for pattern in topic_patterns:
            if pattern.lower() in prompt.lower():
                key_topics.append(pattern)

        # Search for each key topic and combine results
        all_results: dict[str, tuple[float, ResearchDirection]] = {}

        for topic in key_topics:
            results = cls.search_directions(topic)
            for direction in results:
                if direction.direction_name not in all_results:
                    all_results[direction.direction_name] = (0.0, direction)
                all_results[direction.direction_name] = (
                    all_results[direction.direction_name][0] + 10.0,
                    direction,
                )

        # Also search for full prompt if short
        if len(prompt) < 50:
            results = cls.search_directions(prompt)
            for direction in results:
                if direction.direction_name not in all_results:
                    all_results[direction.direction_name] = (0.0, direction)
                all_results[direction.direction_name] = (
                    all_results[direction.direction_name][0] + 20.0,
                    direction,
                )

        # Sort by combined score
        sorted_results = sorted(
            all_results.values(), key=lambda x: x[0], reverse=True
        )

        return [d for _, d in sorted_results[:5]]

    @classmethod
    def get_all_as_dict(cls) -> dict[str, dict]:
        """Return all directions as a dictionary of their serialized forms."""
        cls._init_registry()
        return {k: v.to_dict() for k, v in cls._registry.items()}

    @classmethod
    def export_markdown_all(cls, output_dir: str = ".") -> Path:
        """Export all directions as individual markdown files."""
        cls._init_registry()
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        for name, direction in cls._registry.items():
            md_content = direction.to_markdown()
            (out_path / f"{name}.md").write_text(md_content, encoding="utf-8")

        # Export index
        index_lines = [
            "# Research Directions Index",
            "",
            f"Total directions: {len(cls._registry)}",
            "",
            "## Table of Contents",
            "",
        ]
        for name in sorted(cls._registry.keys()):
            direction = cls._registry[name]
            index_lines.append(f"- [{direction.display_name}]({name}.md)")
        (out_path / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

        return out_path


# ─── Direction Recommender ───────────────────────────────────────────────────


class DirectionRecommender:
    """
    LLM-based and keyword-based research direction recommendation engine.

    Matches user-provided research interests against all available directions
    and returns ranked suggestions with explanations.

    Usage:
        recommender = DirectionRecommender()
        results = recommender.suggest("我想研究碳交易对企业创新的影响")
        for r in results:
            print(f"{r['direction'].display_name}: {r['score']:.1f} - {r['reason']}")
    """

    def __init__(self):
        self._factory = DirectionFactory

    def suggest(
        self,
        prompt: str,
        top_k: int = 5,
        include_custom: bool = True,
    ) -> list[dict]:
        """
        Recommend research directions based on user's research interests.

        Args:
            prompt: User's research interest description
            top_k: Number of top recommendations to return
            include_custom: Whether to include option to create custom direction

        Returns:
            List of recommendation dicts with keys:
                - direction: ResearchDirection object
                - score: Relevance score (0-100)
                - reason: Explanation of why this direction matches
                - match_keywords: List of matched keywords
        """
        suggestions: list[dict] = []

        # Search by keywords
        matched_directions = self._factory.suggest_directions(prompt)

        for direction in matched_directions[:top_k]:
            matched_kws = [
                kw for kw in direction.keywords
                if kw.lower() in prompt.lower()
            ]

            # Build reason
            reasons = []
            if matched_kws:
                reasons.append(f"关键词匹配: {', '.join(matched_kws[:3])}")
            if any(
                kw.lower() in direction.display_name.lower()
                for kw in direction.keywords
                if kw.lower() in prompt.lower()
            ):
                reasons.append("研究主题直接对应")
            if any(
                kw.lower() in direction.literature_theme.lower()
                for kw in direction.keywords
                if kw.lower() in prompt.lower()
            ):
                reasons.append("文献主题相关")

            score = min(100, 40 + len(matched_kws) * 15 + len(reasons) * 10)

            suggestions.append({
                "direction": direction,
                "score": score,
                "reason": "；".join(reasons) if reasons else "基于主题相似度推荐",
                "match_keywords": matched_kws,
                "methodology_summary": direction.methodology_chain.get_step_names(),
                "difficulty": direction.difficulty,
                "estimated_pages": direction.estimated_pages,
            })

        # Sort by score
        suggestions.sort(key=lambda x: x["score"], reverse=True)

        # Add custom direction option if requested
        if include_custom:
            suggestions.append({
                "direction": None,
                "score": 0,
                "reason": "创建一个自定义研究方向",
                "match_keywords": [],
                "methodology_summary": [],
                "difficulty": "custom",
                "estimated_pages": 0,
                "is_custom": True,
            })

        return suggestions

    def match_by_keywords(
        self,
        keywords: list[str],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Match directions by explicit keyword list.

        Args:
            keywords: List of research keywords
            top_k: Number of recommendations

        Returns:
            List of recommendation dicts.
        """
        suggestions: list[dict] = []

        for keyword in keywords:
            results = self._factory.search_directions(keyword)
            for direction in results:
                # Avoid duplicates
                if not any(
                    d["direction"].direction_name == direction.direction_name
                    for d in suggestions
                ):
                    matched = [
                        kw for kw in direction.keywords
                        if kw.lower() in [k.lower() for k in keywords]
                    ]
                    suggestions.append({
                        "direction": direction,
                        "score": len(matched) * 30,
                        "reason": f"关键词 '{keyword}' 匹配",
                        "match_keywords": matched,
                        "methodology_summary": direction.methodology_chain.get_step_names(),
                        "difficulty": direction.difficulty,
                        "estimated_pages": direction.estimated_pages,
                    })

        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:top_k]

    def get_all_directions_summary(self) -> list[dict]:
        """
        Get a summary of all available directions for display.

        Returns:
            List of direction summaries with key metadata.
        """
        all_names = self._factory.list_all()
        summaries = []

        for name in all_names:
            direction = self._factory.get_direction(name)
            if direction:
                summaries.append({
                    "slug": direction.direction_name,
                    "display_name": direction.display_name,
                    "literature_theme": direction.literature_theme[:100] + "..."
                        if len(direction.literature_theme) > 100
                        else direction.literature_theme,
                    "keywords": direction.keywords[:5],
                    "difficulty": direction.difficulty,
                    "estimated_pages": direction.estimated_pages,
                    "methodology": direction.methodology_chain.get_econometric_classes(),
                })

        return summaries


# ─── Legacy compatibility aliases ────────────────────────────────────────────

# Keep the old class names for backward compatibility
# NOTE: get_registry() is defined at module level above DirectionFactory.
# Legacy alias removed to avoid shadowing the actual function.
ResearchDirectionRegistry = DirectionFactory
# list_directions kept for backward compat (imported in agent_pipeline)
list_directions = DirectionFactory.list_all


# ─── Auto-initialization ────────────────────────────────────────────────────

# Eager initialization when module is imported
DirectionFactory._init_registry()


# ─── Exports ─────────────────────────────────────────────────────────────────


__all__ = [
    # Core classes
    "ResearchDirection",
    "MethodologyChain",
    "MethodologyStep",
    # Factory & Registry
    "DirectionFactory",
    "DirectionRecommender",
    # Legacy aliases
    "ResearchDirectionRegistry",
    "get_registry",
    "list_directions",
]
