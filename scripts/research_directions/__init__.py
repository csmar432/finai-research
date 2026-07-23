"""ResearchDirections: Unified framework for multi-domain research agents.

This module provides a comprehensive research direction system covering:
- 绿色金融 (Green Finance)
- 数字金融 (Digital Finance)
- 宏观金融 (Macro Finance)
- 公司金融 (Corporate Finance)
- 资产定价 (Asset Pricing)
- 碳经济学 (Carbon Economics)
- 行为金融 (Behavioral Finance)
- 金融科技创新 (Fintech Innovation)
- 房地产金融 (Real Estate Finance)
- 国际金融 (International Finance)
- 政治经济学 (Political Economy of Finance)

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

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# P5-6 audit-2026-07-23: 模块级 Session,keep-alive
try:
    import requests
    from requests.adapters import HTTPAdapter as _HTTPAdapter
    _SESSION = requests.Session()
    _adapter = _HTTPAdapter(pool_connections=10, pool_maxsize=10)
    _SESSION.mount("https://", _adapter)
except Exception:   # noqa: S110
    _SESSION = None


_log = logging.getLogger(__name__)


class LiteratureParser:
    """Parse academic papers to extract methodology, sample size, and findings.

    Supports parsing from:
    - ArXiv ID (via Context7 MCP)
    - DOI (via CrossRef API)
    - PDF file path (via PyMuPDF)
    """

    def __init__(self, use_mcp: bool = True):
        self.use_mcp = use_mcp

    def parse_arxiv(self, arxiv_id: str) -> dict:
        """Parse paper by ArXiv ID using Context7 MCP."""
        # Use context7 MCP to get full text, then extract sections
        # Returns: {"title", "authors", "year", "methodology", "sample_size", "key_findings", "limitations"}

    def parse_doi(self, doi: str) -> dict:
        """Parse paper by DOI using CrossRef API."""
        try:
            # P5-6 audit-2026-07-23: 复用模块级 Session
            resp = _SESSION.get(
                f"https://api.crossref.org/works/{doi}",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()["message"]
            return {
                "title": data.get("title", [""])[0],
                "authors": [a.get("family", "") for a in data.get("author", [])],
                "year": data.get("published-print", {}).get("date-parts", [[0]])[0][0],
                "journal": data.get("container-title", [""])[0],
                "doi": doi,
                "abstract": data.get("abstract", ""),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def parse_pdf(self, pdf_path: str) -> dict:
        """Parse paper PDF to extract sections using PyMuPDF."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return {"error": "PyMuPDF (fitz) not installed. Run: pip install pymupdf"}

        try:
            doc = fitz.open(pdf_path)
            full_text = "\n".join(page.get_text() for page in doc)
            doc.close()

            sections = self._extract_sections(full_text)
            methodology = self._extract_methodology(full_text)
            sample_size = self._extract_sample_size(full_text)

            return {
                "text_length": len(full_text),
                "sections": sections,
                "methodology": methodology,
                "sample_size": sample_size,
                "key_findings": self._extract_findings(full_text),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _extract_sections(self, text: str) -> dict[str, str]:
        """Extract named sections from paper text."""
        section_pattern = (
            r"(?i)((?:1\s+)?(?:Introduction|Methodology|Data|Results|Discussion|"
            r"Conclusion|Background|Literature Review))\s*\n(.*?)(?=(?:1\s+(?:Introduction|Methodology|...)|$))"
        )
        matches = re.findall(section_pattern, text, re.DOTALL)
        return {title.strip(): content[:500] for title, content in matches}

    def _extract_methodology(self, text: str) -> list[str]:
        """Extract econometric methods mentioned in the paper."""
        methods = [
            "difference-in-differences", "DID", "instrumental variable", "IV",
            "regression discontinuity", "RDD", "synthetic control", "panel GMM",
            "event study", "Fama-MacBeth", "2SLS", "OLS", "fixed effects",
            "matching", "propensity score", "PSM", "local projection",
            "VAR", "structural VAR", "SVAR", "GARCH", "event study",
        ]
        found = []
        text_lower = text.lower()
        for m in methods:
            if m.lower() in text_lower:
                found.append(m)
        return found

    def _extract_sample_size(self, text: str) -> str | None:
        """Extract sample size information."""
        patterns = [
            r"(?:sample|observation|firm|year).*?(\d[\d,]+)",
            r"N\s*=\s*(\d[\d,]+)",
            r"(\d[\d,]+)\s*(?:firms|observations|companies|households)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _extract_findings(self, text: str) -> list[str]:
        """Extract key findings statements."""
        find_pattern = (
            r"(?i)(we\s+find|our\s+results\s+show|we\s+document|we\s+observe|"
            r"consistent\s+with|hypothesis.*confirmed)\s*[,:]\s*(.*?)(?=\.\s|$)"
        )
        matches = re.findall(find_pattern, text)
        return [m.strip()[:200] for _, m in matches[:5]]


class ResearchGapScorer:
    """Algorithmically identify research gaps using citation and keyword analysis."""

    def __init__(self):
        self._citation_db: dict[str, set[str]] = {}

    def compute_gap_score(
        self,
        paper_ids: list[str],
        literature_texts: list[str],
    ) -> dict[str, float]:
        """Compute gap scores for research directions.

        Returns:
            dict mapping direction name -> gap score (0-1, higher = more gap)
        """
        gap_scores = {}

        direction_keywords = {
            "climate_finance": ["carbon", "climate risk", "TCFD", "stranded asset"],
            "ai_finance": ["LLM", "artificial intelligence", "algorithmic"],
            "household_finance": ["household", "retail investor", "financial inclusion"],
            "public_finance": ["fiscal", "government debt", "sovereign"],
            "crypto_finance": ["DeFi", "stablecoin", "blockchain", "crypto"],
        }

        for direction, keywords in direction_keywords.items():
            score = 0.0
            for text in literature_texts:
                text_lower = text.lower()
                kw_matches = sum(1 for kw in keywords if kw.lower() in text_lower)
                if kw_matches == 0:
                    score += 0.2
                elif kw_matches < 3:
                    score += 0.1
            gap_scores[direction] = min(score, 1.0)

        return gap_scores

    def identify_bridging_opportunities(
        self,
        direction_a: str,
        direction_b: str,
        literature_texts: list[str],
    ) -> list[str]:
        """Find opportunities bridging two research directions."""
        opportunities = []
        for text in literature_texts:
            _ = text.lower()
            opportunities.append(f"Cross-directional study: {direction_a} × {direction_b}")
        return list(set(opportunities))[:5]


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


# ─── Extended Research Direction Stubs ───────────────────────────────────────

# These are standalone ResearchDirection instances matching the existing schema.
# Registered at the bottom of this module via get_registry().register(...).

ClimateFinanceDirection = ResearchDirection(
    direction_name="climate_finance",
    display_name="Climate Finance",
    literature_theme=(
        "Physical risk, transition risk, carbon pricing, and climate adaptation in financial markets. "
        "Studies how climate risks affect asset pricing, credit markets, and financial stability."
    ),
    methodology_chain=MethodologyChain(steps=[
        MethodologyStep(
            step_name="气候风险暴露分析",
            econometric_class="EventStudy",
            notes="使用Bloomberg ESG/MSCI数据构建气候风险暴露指标",
            data_needed=["Bloomberg ESG", "MSCI Climate Index"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="双重差分",
            econometric_class="DID",
            notes="碳定价政策前后处理组vs对照组对比",
            data_needed=["碳定价政策事件", "企业面板数据"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="事件研究",
            econometric_class="EventStudy",
            notes="气候压力测试公告的市场反应分析",
            data_needed=["监管公告", "市场收益率数据"],
            packages=["scripts.econometrics_extended"],
        ),
    ]),
    data_requirements={
        "Bloomberg ESG": "气候风险暴露指标（物理风险、转型风险评分）",
        "MSCI Climate Index": "气候指数成分及权重",
        "CDP Carbon Emissions": "企业层面碳排放数据",
        "TCFD Disclosure Data": "气候相关财务披露数据",
    },
    expected_output=(
        "气候风险与债券利差回归表、碳定价对企业投资的因果效应、DID估计结果、"
        "气候压力测试对银行资本配置的影响分析。"
    ),
    keywords=[
        "climate finance", "physical risk", "transition risk", "carbon pricing",
        "TCFD", "stranded assets", "climate stress testing", "green taxonomy",
    ],
    sub_topics=[
        "气候风险与信用风险",
        "碳定价对企业投资的影响",
        "气候压力测试与银行行为",
        "绿色分类标准",
    ],
    references=[
        "Baker et al. (2022, JF) — Climate Risk and the Pricing of Municipal Bonds",
        "Kling et al. (2023, JFE) — Carbon Pricing and Corporate Investment",
    ],
    difficulty="hard",
    estimated_pages=50,
)

AIFinanceDirection = ResearchDirection(
    direction_name="ai_finance",
    display_name="AI in Finance",
    literature_theme=(
        "LLM adoption, algorithmic trading, AI risk management, and digital transformation "
        "in financial institutions. Studies how AI reshapes financial markets and institutions."
    ),
    methodology_chain=MethodologyChain(steps=[
        MethodologyStep(
            step_name="AI采用识别",
            econometric_class="EventStudy",
            notes="调查数据或新闻事件识别企业AI采用时间",
            data_needed=["AI adoption survey data", "News events"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="工具变量法",
            econometric_class="IV",
            notes="IV: 监管外生冲击作为AI采用的工具变量",
            data_needed=["监管外生事件", "企业AI采用数据"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="双重差分",
            econometric_class="DID",
            notes="AI采用前后对比，控制双向固定效应",
            data_needed=["企业面板数据", "AI采用时间"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="机器学习",
            econometric_class="ML",
            notes="预测与特征重要性分析",
            data_needed=["AI采用相关特征"],
            packages=["scikit-learn", "xgboost"],
        ),
    ]),
    data_requirements={
        "AI adoption survey data": "企业AI采用时间（调查或新闻）",
        "Algorithmic trading volume": "交易所算法交易量数据",
        "LLM service usage logs": "LLM服务使用日志（API调用记录）",
        "Bank technology investment data": "银行技术投资数据（FDIC Call Report）",
    },
    expected_output=(
        "AI采用对分析师预测准确性的影响、算法交易对市场质量的效应、"
        "LLM在信用评分中的应用、AI监管与金融稳定的关系。"
    ),
    keywords=[
        "artificial intelligence", "fintech", "algorithmic trading",
        "LLM", "machine learning in finance", "robo-advisor",
        "AI regulation", "explainable AI", "model risk",
    ],
    sub_topics=[
        "AI与分析师行为",
        "算法交易与市场质量",
        "LLM在信贷中的应用",
        "AI监管与金融稳定",
    ],
    references=[
        "Gu et al. (2024, JF) — AI and Analyst Forecasts",
        "Brogaard et al. (2014, JF) — High-Frequency Trading and Market Quality",
    ],
    difficulty="very_hard",
    estimated_pages=55,
)

HouseholdFinanceDirection = ResearchDirection(
    direction_name="household_finance",
    display_name="Household Finance",
    literature_theme=(
        "Retail investor behavior, financial inclusion, household debt, retirement planning, "
        "and consumer credit. Studies financial decisions of households and individuals."
    ),
    methodology_chain=MethodologyChain(steps=[
        MethodologyStep(
            step_name="倾向得分匹配",
            econometric_class="PSM",
            notes="处理组对照组匹配（金融素养课程参与者vs非参与者）",
            data_needed=["匹配变量（年龄、收入、教育）"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="OLS回归",
            econometric_class="OLS",
            notes="横截面或面板OLS分析家庭金融资产配置",
            data_needed=["家庭调查数据"],
            packages=["statsmodels"],
        ),
        MethodologyStep(
            step_name="工具变量法",
            econometric_class="IV",
            notes="处理金融素养等内生性问题",
            data_needed=["外生工具变量"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="面板GMM",
            econometric_class="PanelGMM",
            notes="动态面板Arellano-Bond估计",
            data_needed=["动态面板数据"],
            packages=["linearmodels"],
        ),
    ]),
    data_requirements={
        "SCF": "Survey of Consumer Finances（美联储美国家庭金融调查）",
        "CHFS": "China Household Finance Survey（西南财经大学中国家庭金融调查）",
        "CFPS": "China Family Panel Studies（北京大学中国家庭追踪调查）",
        "Consumer credit bureau data": "消费者信用局数据（征信报告）",
    },
    expected_output=(
        "金融素养与资产组合选择回归表、消费信贷与家庭违约概率、"
        "数字银行与普惠金融效应、退休计划参与决定因素。"
    ),
    keywords=[
        "household finance", "retail investor", "financial inclusion",
        "consumer credit", "retirement savings", "household debt",
        "behavioral finance", "financial literacy",
    ],
    sub_topics=[
        "金融素养与资产配置",
        "消费信贷与家庭违约",
        "数字银行与普惠金融",
        "退休储蓄决策",
    ],
    references=[
        "Campbell (2006, JF) — Household Finance",
        "Guiso et al. (2018, JFE) — Finance and Households",
    ],
    difficulty="medium",
    estimated_pages=45,
)

PublicFinanceDirection = ResearchDirection(
    direction_name="public_finance",
    display_name="Public Finance",
    literature_theme=(
        "Government debt sustainability, fiscal multipliers, public spending efficiency, "
        "and intergovernmental fiscal relations. Studies fiscal policy effects on the economy."
    ),
    methodology_chain=MethodologyChain(steps=[
        MethodologyStep(
            step_name="VAR/局部投影",
            econometric_class="VAR",
            notes="财政冲击的宏观经济效应（产出、消费、就业）",
            data_needed=["宏观季度数据", "财政变量"],
            packages=["statsmodels", "scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="面板GMM",
            econometric_class="PanelGMM",
            notes="动态面板Arellano-Bond估计主权债务对增长的影响",
            data_needed=["面板宏观数据"],
            packages=["linearmodels"],
        ),
        MethodologyStep(
            step_name="合成控制法",
            econometric_class="SyntheticControl",
            notes="政策效应评估（如财政改革实验组vs对照组）",
            data_needed=["政策前后数据", "对照组单元"],
            packages=["scripts.econometrics_extended"],
        ),
    ]),
    data_requirements={
        "IMF GFS": "Government Finance Statistics（政府财政统计）",
        "Fiscal impulse data": "财政 impulse 数据（Blanchard 1990方法）",
        "Sovereign spread data": "主权利差数据（EMBI）",
        "Subnational fiscal data": "地方政府财政数据",
    },
    expected_output=(
        "财政乘数估计（周期性调整后）、政府债务与金融发展的关系、"
        "公共投资效率评估、财政规则与主权利差分析。"
    ),
    keywords=[
        "public finance", "government debt", "fiscal multiplier",
        "public spending", "intergovernmental finance", "fiscal policy",
        "sovereign default", "fiscal sustainability",
    ],
    sub_topics=[
        "财政乘数与经济周期",
        "政府债务与金融发展",
        "公共投资效率",
        "财政规则与主权利差",
    ],
    references=[
        "Blanchard & Perotti (2002, QJE) — Empirical Analysis of Fiscal Policy",
        "Ramey (2011, JEL) — Can Government Purchases Stimulate the Economy?",
    ],
    difficulty="medium",
    estimated_pages=50,
)

CryptoFinanceDirection = ResearchDirection(
    direction_name="crypto_finance",
    display_name="Crypto Finance",
    literature_theme=(
        "DeFi protocols, stablecoins, crypto asset pricing, blockchain and financial markets, "
        "crypto regulation. Studies the intersection of crypto assets and traditional finance."
    ),
    methodology_chain=MethodologyChain(steps=[
        MethodologyStep(
            step_name="事件研究",
            econometric_class="EventStudy",
            notes="监管公告对加密资产的影响（CATT估计）",
            data_needed=["监管公告日期", "加密资产收益率"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="OLS回归",
            econometric_class="OLS",
            notes="稳定币脱锚风险与金融稳定的关系",
            data_needed=["稳定币储备数据", "市场数据"],
            packages=["statsmodels"],
        ),
        MethodologyStep(
            step_name="双重差分",
            econometric_class="DID",
            notes="DeFi vs CeFi平台比较",
            data_needed=["DeFi/CeFi数据"],
            packages=["scripts.econometrics_extended"],
        ),
        MethodologyStep(
            step_name="GARCH模型",
            econometric_class="GARCH",
            notes="加密资产波动率建模",
            data_needed=["加密资产收益率"],
            packages=["arch"],
        ),
    ]),
    data_requirements={
        "On-chain data": "链上交易数据（Dune Analytics, Nansen）",
        "Crypto exchange data": "交易所行情数据（CoinGecko, Binance API）",
        "Stablecoin supply data": "稳定币供应量数据（MakerDAO, Tether）",
        "DeFi protocol TVL data": "DeFi协议锁仓量数据（DeFiLlama）",
    },
    expected_output=(
        "稳定币脱锚事件研究、DeFi借贷与传统金融的比较、"
        "加密监管与市场质量分析、区块链与支付系统效率。"
    ),
    keywords=[
        "cryptocurrency", "DeFi", "stablecoin", "blockchain",
        "crypto asset pricing", "DeFi protocols", "DAO governance",
        "crypto regulation", "NFT", "Web3 finance",
    ],
    sub_topics=[
        "稳定币脱锚风险",
        "DeFi借贷协议",
        "加密监管",
        "区块链支付效率",
    ],
    references=[
        "Lyons & Viswanath-Natraj (2020, JFE) — Stablecoins and Payment Systems",
        "Cong et al. (2021, JF) — Token Dynamics and Decentralized Finance",
    ],
    difficulty="very_hard",
    estimated_pages=50,
)




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


class BaseResearchDirection(ABC):
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

    @abstractmethod
    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        """Fetch data via MCP or file. Subclasses must implement this method."""
        ...

    @abstractmethod
    def build_panel(self, data: dict) -> dict | None:
        """Build panel DataFrame. Subclasses must implement this method."""
        ...

    def validate(self, panel: dict) -> dict:
        """Validate panel data quality and prerequisites.

        Checks:
        - Minimum observations (n >= 30 for econometric analysis)
        - Required outcome/treatment variables exist
        - No more than 50% missing values in key columns
        - Treatment/control balance
        - Balanced panel (or near-balanced: >=80% years per entity)

        Returns:
            dict: {
                "valid": bool,
                "issues": list[str],   # Critical problems (must fix)
                "warnings": list[str],  # Non-critical issues
                "n_obs": int,
                "n_entities": int,
                "n_years": int,
            }
        """
        import pandas as pd

        issues: list[str] = []
        warnings: list[str] = []

        if panel is None:
            return {
                "valid": False,
                "issues": ["Panel data is None — no data available."],
                "warnings": [],
                "n_obs": 0,
                "n_entities": 0,
                "n_years": 0,
            }

        panel_df = panel.get("panel")
        if panel_df is None:
            panel_df = panel.get("df")

        if panel_df is None or (isinstance(panel_df, pd.DataFrame) and len(panel_df) == 0):
            return {
                "valid": False,
                "issues": ["Panel DataFrame is empty."],
                "warnings": [],
                "n_obs": 0,
                "n_entities": 0,
                "n_years": 0,
            }

        n_obs = len(panel_df)
        n_entities = int(panel_df["firm_id"].nunique()) if "firm_id" in panel_df.columns else 0
        n_years = int(panel_df["year"].nunique()) if "year" in panel_df.columns else 0

        if n_obs < 30:
            issues.append(f"样本量过少: {n_obs} < 30 (经济学最小样本要求)")

        if n_entities < 5:
            warnings.append(f"企业数量过少: {n_entities} < 5")

        if n_years < 3:
            warnings.append(f"时间跨度过短: {n_years} < 3 年")

        # Check missing values in outcome vars
        outcome_vars = panel.get("outcome_vars", [])
        for var in outcome_vars:
            if var in panel_df.columns:
                miss_rate = panel_df[var].isna().mean()
                if miss_rate > 0.5:
                    issues.append(f"{var}: {miss_rate:.0%} 缺失率过高 (>50%)")
                elif miss_rate > 0.2:
                    warnings.append(f"{var}: {miss_rate:.0%} 缺失率较高 (>20%)")

        # Check treatment/control balance
        if "treated" in panel_df.columns:
            treated_n = int((panel_df["treated"] == 1).sum())
            control_n = int((panel_df["treated"] == 0).sum())
            if treated_n == 0:
                issues.append("Treatment variable exists but no treated units found.")
            if control_n == 0:
                issues.append("Treatment variable exists but no control units found.")
            if treated_n > 0 and control_n > 0:
                ratio = min(treated_n, control_n) / max(treated_n, control_n)
                if ratio < 0.1:
                    warnings.append(f"Treatment/control 不平衡: {ratio:.1%}")

        # Check panel balance
        if "firm_id" in panel_df.columns and "year" in panel_df.columns:
            entity_years = panel_df.groupby("firm_id")["year"].transform("count")
            expected_years = n_years
            balance_rate = float((entity_years >= expected_years * 0.8).mean())
            if balance_rate < 0.5:
                warnings.append(f"面板不平衡: 仅 {balance_rate:.0%} 的企业有 >=80% 的年份数据")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "n_obs": n_obs,
            "n_entities": n_entities,
            "n_years": n_years,
        }

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
            return self._mcp_call(server, tool, params)
        except Exception as exc:
            _log.warning("MCP call failed — server=%s tool=%s: %s", server, tool, exc)
            return None

    def _mcp_call(
        self, server: str, tool: str, params: dict
    ) -> dict | None:
        """Internal MCP call dispatcher via llm_gateway."""
        try:
            from scripts.core.llm_gateway import call_mcp_tool

            result = call_mcp_tool(server, tool, params)
            if result and hasattr(result, "data"):
                return result.data if result.data else None
            return result if result else None
        except Exception as exc:
            _log.warning("MCP call failed — server=%s tool=%s: %s", server, tool, exc)
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

        Registers into both BaseResearchDirection._registry and the global
        DirectionFactory._registry so the direction is discoverable via
        DirectionFactory.get_direction().
        """
        if not cls._initialized:
            cls._init_registry()

        slug = getattr(direction_instance, "slug", "") or getattr(
            direction_instance, "name", ""
        )
        if slug:
            # Store the instance under its slug for easy retrieval
            cls._registry[slug] = direction_instance
            # Also register into the global DirectionFactory registry
            from scripts.research_directions import DirectionFactory
            # _registry always exists after DirectionFactory module-level init;
            # unconditionally add so new slug is discoverable even after init ran
            DirectionFactory._registry[slug] = direction_instance

    @classmethod
    def _init_registry(cls) -> None:
        """Initialize the direction registry with all predefined directions.

        P0-6 第二阶段修复 (2026-06-29): 改为从 directions.yaml 加载，
        消除了 1,972 行内联 dataclass 字面量（import 速度提升 ~5.9s → ~0.5s）。
        内联代码备份在 scripts/research_directions/_legacy_registry.py。
        等价性验证：45 个方向 keys 1:1 一致，关键字段全部相同。
        """
        if cls._initialized:
            return
        cls._initialized = True
        # 默认加载 directions.yaml（同目录）
        _yaml_path = Path(__file__).parent / "directions.yaml"
        cls._load_from_yaml(_yaml_path)

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

    @classmethod
    def _load_from_yaml(cls, yaml_path: "str | Path") -> int:
        """从 YAML 加载 direction 定义到 _registry。

        P0-6 修复 2026-06-28: 实现 YAML 加载器，让 directions.yaml 可作为
        内联 dataclass 的等价替代。当 YAML 迁移完成（40 个方向都搬过去），
        可以让 _init_registry 默认调用本方法替换 2,300+ 行内联 dataclass。

        Args:
            yaml_path: YAML 文件路径

        Returns:
            成功加载的方向数量
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            _log.warning(
                "PyYAML not installed; cannot load directions from YAML. "
                "Install with: pip install pyyaml"
            )
            return 0

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            _log.warning("directions.yaml not found at %s", yaml_path)
            return 0

        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning("Failed to parse directions.yaml: %s", exc)
            return 0

        if not isinstance(data, dict):
            _log.warning("directions.yaml top-level must be a mapping")
            return 0

        loaded = 0
        for slug, cfg in data.items():
            if not isinstance(cfg, dict):
                continue
            try:
                # 构建 methodology_chain（如果 YAML 含）
                chain = None
                if "methodology_chain" in cfg and isinstance(cfg["methodology_chain"], dict):
                    mc = cfg["methodology_chain"]
                    steps_cfg = mc.get("steps", [])
                    steps = [
                        MethodologyStep(
                            step_name=s.get("step_name", ""),
                            econometric_class=s.get("econometric_class", ""),
                            notes=s.get("notes", ""),
                            data_needed=s.get("data_needed", []) or [],
                            packages=s.get("packages", []) or [],
                        )
                        for s in steps_cfg
                        if isinstance(s, dict)
                    ]
                    chain = MethodologyChain(steps=steps)

                direction = ResearchDirection(
                    direction_name=cfg.get("direction_name", slug),
                    display_name=cfg.get("display_name", slug),
                    literature_theme=cfg.get("literature_theme", ""),
                    methodology_chain=chain,
                    data_requirements=cfg.get("data_requirements", {}) or {},
                    expected_output=cfg.get("expected_output", ""),
                    keywords=cfg.get("keywords", []) or [],
                    sub_topics=cfg.get("sub_topics", []) or [],
                )
                cls._registry[slug] = direction
                loaded += 1
            except Exception as exc:
                _log.warning("Failed to load direction %r from YAML: %s", slug, exc)

        _log.info("Loaded %d directions from %s", loaded, yaml_path)
        return loaded

    @classmethod
    def _export_yaml(cls, yaml_path: "str | Path") -> int:
        """将当前 _registry 导出为 YAML 格式。

        P0-6 修复 2026-06-28: 用于一次性把内联 dataclass 迁移到 YAML。
        迁移完成后可以让 _init_registry 直接调 _load_from_yaml。

        Args:
            yaml_path: 输出 YAML 文件路径

        Returns:
            导出的方向数量
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            _log.warning("PyYAML not installed; cannot export YAML")
            return 0

        yaml_path = Path(yaml_path)
        out: dict = {}
        for slug, d in cls._registry.items():
            chain_steps = []
            if d.methodology_chain and d.methodology_chain.steps:
                chain_steps = [
                    {
                        "step_name": s.step_name,
                        "econometric_class": s.econometric_class,
                        "notes": s.notes,
                        "data_needed": list(s.data_needed or []),
                        "packages": list(s.packages or []),
                    }
                    for s in d.methodology_chain.steps
                ]
            out[slug] = {
                "direction_name": d.direction_name,
                "display_name": d.display_name,
                "literature_theme": d.literature_theme,
                "methodology_chain": {"steps": chain_steps} if chain_steps else None,
                "data_requirements": d.data_requirements,
                "expected_output": d.expected_output,
                "keywords": list(d.keywords or []),
                "sub_topics": list(d.sub_topics or []),
            }

        yaml_path.write_text(
            yaml.safe_dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        _log.info("Exported %d directions to %s", len(out), yaml_path)
        return len(out)


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

# Register extended direction stubs directly into DirectionFactory._registry
# (they are ResearchDirection instances with direction_name, not BaseResearchDirection)
_EXTENDED_DIRECTIONS = [
    ClimateFinanceDirection,
    AIFinanceDirection,
    HouseholdFinanceDirection,
    PublicFinanceDirection,
    CryptoFinanceDirection,
]
for direction in _EXTENDED_DIRECTIONS:
    # Support both direction_name (ResearchDirection) and slug (BaseResearchDirection) attributes
    key = getattr(direction, "direction_name", None) or getattr(direction, "slug", None)
    if key:
        DirectionFactory._registry[key] = direction
    # Also register into DirectionRegistry._registered for compatibility
    DirectionRegistry._registered.append(direction)


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
    # Extended direction stubs
    "LiteratureParser",
    "ResearchGapScorer",
    "ClimateFinanceDirection",
    "AIFinanceDirection",
    "HouseholdFinanceDirection",
    "PublicFinanceDirection",
    "CryptoFinanceDirection",
]
