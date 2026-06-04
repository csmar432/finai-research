"""Financial Report Structure Templates.

Reference: FinResearchAgent's 21-section equity memo and 8-section macro report.

This module provides standardized templates for institutional-quality financial research reports,
covering equity analysis (21 sections) and macro research (8 sections).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ReportType(Enum):
    """Types of financial reports."""
    EQUITY = "equity"
    MACRO = "macro"
    INDUSTRY = "industry"
    COMPANY = "company"
    THESIS = "thesis"


class SectionType(Enum):
    """Section types for different content."""
    EXECUTIVE_SUMMARY = "executive_summary"
    FINANCIAL_ANALYSIS = "financial_analysis"
    VALUATION = "valuation"
    RISK = "risk"
    LITERATURE_REVIEW = "literature_review"
    ECONOMETRIC = "econometric"
    QUALITATIVE = "qualitative"
    RECOMMENDATION = "recommendation"


@dataclass
class ReportSection:
    """A single section in a report."""
    id: str
    title: str
    title_en: str
    section_type: SectionType
    order: int
    required: bool = True
    subsections: list[str] = field(default_factory=list)
    prompt_template: str = ""
    min_words: int = 200
    max_words: int = 2000

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "title_en": self.title_en,
            "type": self.section_type.value,
            "order": self.order,
            "required": self.required,
            "subsections": self.subsections,
            "word_range": f"{self.min_words}-{self.max_words}",
        }


@dataclass
class ReportTemplate:
    """Complete report template."""
    name: str
    report_type: ReportType
    sections: list[ReportSection]
    description: str = ""
    target_audience: str = "Institutional investors"
    typical_length_words: int = 15000

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.report_type.value,
            "description": self.description,
            "target_audience": self.target_audience,
            "estimated_length": f"{self.typical_length_words // 1000}k words",
            "sections": [s.to_dict() for s in self.sections],
        }

    def get_section(self, section_id: str) -> ReportSection | None:
        """Get section by ID."""
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def get_sections_by_type(self, section_type: SectionType) -> list[ReportSection]:
        """Get all sections of a specific type."""
        return [s for s in self.sections if s.section_type == section_type]

    def generate_outline(self) -> str:
        """Generate markdown outline."""
        lines = [f"# {self.name}\n"]
        for s in sorted(self.sections, key=lambda x: x.order):
            prefix = "##" if self.report_type == ReportType.EQUITY else "##"
            lines.append(f"{prefix} {s.order}. {s.title} ({s.title_en})")
            for sub in s.subsections:
                lines.append(f"   - {sub}")
            lines.append("")
        return "\n".join(lines)


# ─── 21-Section Equity Report Template ────────────────────────────────────────

EQUITY_21_SECTIONS = [
    ReportSection(
        id="es",
        title="投资摘要",
        title_en="Executive Summary",
        section_type=SectionType.EXECUTIVE_SUMMARY,
        order=1,
        subsections=["核心观点", "关键指标", "投资评级"],
        prompt_template="""提供股票{ ticker }的简明投资摘要。
涵盖：1) 核心投资观点（一句话）；2) 关键财务指标；3) 投资评级和目标价。
""",
        min_words=300,
        max_words=500,
    ),
    ReportSection(
        id="thesis",
        title="投资亮点",
        title_en="Investment Thesis",
        section_type=SectionType.EXECUTIVE_SUMMARY,
        order=2,
        subsections=["核心逻辑", "增长驱动", "竞争优势"],
        prompt_template="""阐述股票{ ticker }的核心投资逻辑。
分析：1) 为什么现在看好；2) 主要增长驱动因素；3) 公司的竞争优势和护城河。
""",
        min_words=500,
        max_words=1000,
    ),
    ReportSection(
        id="company",
        title="公司概况",
        title_en="Company Overview",
        section_type=SectionType.QUALITATIVE,
        order=3,
        subsections=["业务模式", "发展历程", "股权结构", "管理层"],
        prompt_template="""介绍{ticker}的公司概况。
包括：1) 主营业务和业务模式；2) 公司发展历程；3) 股权结构；4) 核心管理层背景。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="industry",
        title="行业分析",
        title_en="Industry Analysis",
        section_type=SectionType.QUALITATIVE,
        order=4,
        subsections=["行业规模", "增长趋势", "政策环境", "波特五力"],
        prompt_template="""分析{ticker}所处行业。
使用波特五力框架：1) 行业内竞争；2) 新进入者威胁；3) 替代品威胁；4) 供应商议价能力；5) 客户议价能力。
""",
        min_words=600,
        max_words=1200,
    ),
    ReportSection(
        id="competitive",
        title="竞争格局",
        title_en="Competitive Position",
        section_type=SectionType.QUALITATIVE,
        order=5,
        subsections=["市场份额", "竞争对手", "SWOT分析"],
        prompt_template="""分析{ticker}的竞争格局。
重点：1) 市场份额及变化趋势；2) 主要竞争对手对比；3) SWOT分析。
""",
        min_words=500,
        max_words=1000,
    ),
    ReportSection(
        id="business",
        title="商业模式",
        title_en="Business Model",
        section_type=SectionType.QUALITATIVE,
        order=6,
        subsections=["收入模式", "成本结构", "盈利模式"],
        prompt_template="""深入分析{ticker}的商业模式。
分析：1) 收入来源和模式；2) 成本结构；3) 盈利模式可持续性。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="financial_hist",
        title="财务分析_历史",
        title_en="Historical Financials",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=7,
        subsections=["收入", "利润", "资产负债表", "现金流量表"],
        prompt_template="""分析{ticker}历史财务数据。
重点：1) 收入增长趋势；2) 盈利能力（毛利率、净利率）；3) 资产质量；4) 现金流状况。
""",
        min_words=600,
        max_words=1200,
    ),
    ReportSection(
        id="financial_proj",
        title="财务分析_预测",
        title_en="Financial Projections",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=8,
        subsections=["收入预测", "盈利预测", "关键假设"],
        prompt_template="""提供{ticker}未来3-5年财务预测。
基于历史数据和市场判断：1) 收入预测及CAGR；2) 利润率预测；3) 关键假设说明。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="profitability",
        title="盈利能力",
        title_en="Profitability Analysis",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=9,
        subsections=["ROE分析", "杜邦分解", "同业对比"],
        prompt_template="""深度分析{ticker}的盈利能力。
进行杜邦分析：ROE = 净利率 × 资产周转率 × 权益乘数，并与同业对比。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="cashflow",
        title="现金流分析",
        title_en="Cash Flow Analysis",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=10,
        subsections=["经营现金流", "投资现金流", "筹资现金流"],
        prompt_template="""分析{ticker}的现金流状况。
重点：1) 经营现金流与净利润匹配度；2) 自由现金流；3) 现金分红能力。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="balancesheet",
        title="资产负债表",
        title_en="Balance Sheet Health",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=11,
        subsections=["资产结构", "负债结构", "偿债能力"],
        prompt_template="""评估{ticker}的资产负债状况。
分析：1) 资产结构；2) 负债水平和结构；3) 短期和长期偿债能力。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="dcf",
        title="估值分析_DCF",
        title_en="DCF Valuation",
        section_type=SectionType.VALUATION,
        order=12,
        subsections=["假设", "WACC", "敏感性分析"],
        prompt_template="""对{ticker}进行DCF估值。
步骤：1) 设定WACC；2) 预测未来10年FCF；3) 计算终值；4) 敏感性分析。
""",
        min_words=500,
        max_words=1000,
    ),
    ReportSection(
        id="comparable",
        title="估值分析_可比",
        title_en="Comparable Company Analysis",
        section_type=SectionType.VALUATION,
        order=13,
        subsections=["可比公司", "倍数选择", "估值区间"],
        prompt_template="""对{ticker}进行可比公司法估值。
选择可比公司，计算P/E、P/B、EV/EBITDA等倍数，确定估值区间。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="scenario",
        title="估值分析_情景",
        title_en="Scenario Valuation",
        section_type=SectionType.VALUATION,
        order=14,
        subsections=["乐观情景", "基准情景", "悲观情景"],
        prompt_template="""对{ticker}进行情景分析估值。
设定乐观/基准/悲观三种情景，测算各情景下的目标价和概率加权价值。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="technical",
        title="技术面分析",
        title_en="Technical Analysis",
        section_type=SectionType.QUALITATIVE,
        order=15,
        subsections=["趋势分析", "支撑阻力", "技术指标"],
        prompt_template="""对{ticker}进行技术面分析。
分析：1) 价格趋势；2) 关键支撑/阻力位；3) 主要技术指标信号。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="earnings_quality",
        title="盈利质量",
        title_en="Earnings Quality",
        section_type=SectionType.FINANCIAL_ANALYSIS,
        order=16,
        subsections=["应计项目", "现金流匹配", "盈余管理"],
        prompt_template="""评估{ticker}的盈利质量。
分析：1) 应计项目占比；2) 现金流与净利润匹配；3) 可能的盈余管理迹象。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="risk",
        title="风险因素",
        title_en="Risk Factors",
        section_type=SectionType.RISK,
        order=17,
        subsections=["经营风险", "财务风险", "行业风险", "宏观风险"],
        prompt_template="""识别{ticker}面临的主要风险。
系统性分析：1) 经营风险；2) 财务风险；3) 行业周期性风险；4) 宏观政策风险。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="esg",
        title="ESG分析",
        title_en="ESG Considerations",
        section_type=SectionType.QUALITATIVE,
        order=18,
        subsections=["环境", "社会责任", "公司治理"],
        prompt_template="""评估{ticker}的ESG表现。
分析：1) 环境责任；2) 社会责任；3) 公司治理水平。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="ownership",
        title="机构持仓",
        title_en="Ownership Analysis",
        section_type=SectionType.QUALITATIVE,
        order=19,
        subsections=["股东结构", "机构持仓", "大股东行为"],
        prompt_template="""分析{ticker}的股东结构和机构持仓。
重点：1) 主要股东构成；2) 机构持仓变化；3) 大股东增减持情况。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="catalyst",
        title="催化剂",
        title_en="Catalysts",
        section_type=SectionType.EXECUTIVE_SUMMARY,
        order=20,
        subsections=["近期催化", "中长期催化", "时间表"],
        prompt_template="""识别{ticker}的股价催化剂。
分析：1) 近期可能的催化因素；2) 中长期增长催化剂；3) 关键事件时间表。
""",
        min_words=300,
        max_words=600,
    ),
    ReportSection(
        id="recommendation",
        title="投资建议",
        title_en="Investment Recommendation",
        section_type=SectionType.RECOMMENDATION,
        order=21,
        subsections=["评级", "目标价", "风险收益比", "更新时间"],
        prompt_template="""给出{ticker}的投资建议。
结论：1) 投资评级；2) 目标价及上涨空间；3) 风险收益比；4) 建议操作。
""",
        min_words=300,
        max_words=500,
    ),
]

EQUITY_REPORT_TEMPLATE = ReportTemplate(
    name="21-Section 机构级股票研报",
    report_type=ReportType.EQUITY,
    sections=EQUITY_21_SECTIONS,
    description="完整的机构级股票研究推荐报告模板，覆盖从投资摘要到投资建议的21个标准化章节",
    target_audience="机构投资者、基金经理、分析师",
    typical_length_words=15000,
)


# ─── 8-Section Macro Report Template ─────────────────────────────────────────

MACRO_8_SECTIONS = [
    ReportSection(
        id="macro_es",
        title="宏观摘要",
        title_en="Executive Summary",
        section_type=SectionType.EXECUTIVE_SUMMARY,
        order=1,
        subsections=["核心判断", "关键数据", "政策建议"],
        prompt_template="""提供{topic}的宏观研究摘要。
简明扼要：1) 核心宏观判断；2) 关键数据变化；3) 政策建议摘要。
""",
        min_words=300,
        max_words=500,
    ),
    ReportSection(
        id="indicators",
        title="经济指标分析",
        title_en="Economic Indicators",
        section_type=SectionType.ECONOMETRIC,
        order=2,
        subsections=["增长", "通胀", "就业", "领先指标"],
        prompt_template="""分析{topic}相关的主要经济指标。
覆盖：1) 增长指标(GDP等)；2) 通胀指标(CPI/PPI)；3) 就业市场；4) 领先指标。
""",
        min_words=600,
        max_words=1200,
    ),
    ReportSection(
        id="monetary",
        title="货币政策",
        title_en="Monetary Policy",
        section_type=SectionType.QUALITATIVE,
        order=3,
        subsections=["政策立场", "利率", "流动性", "前瞻指引"],
        prompt_template="""分析{topic}的货币政策环境。
重点：1) 货币政策立场；2) 利率走势；3) 流动性状况；4) 央行前瞻指引。
""",
        min_words=500,
        max_words=1000,
    ),
    ReportSection(
        id="fiscal",
        title="财政政策",
        title_en="Fiscal Policy",
        section_type=SectionType.QUALITATIVE,
        order=4,
        subsections=["财政立场", "赤字", "债务", "结构改革"],
        prompt_template="""分析{topic}的财政政策。
覆盖：1) 财政立场；2) 赤字率；3) 债务水平；4) 结构改革进展。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="lit_review",
        title="实证文献综述",
        title_en="Empirical Literature Review",
        section_type=SectionType.LITERATURE_REVIEW,
        order=5,
        subsections=["经典文献", "最新研究", "政策启示"],
        prompt_template="""综述{topic}相关的实证经济学文献。
覆盖：1) 经典理论和实证；2) 最新研究进展；3) 对政策制定的启示。
""",
        min_words=800,
        max_words=1500,
    ),
    ReportSection(
        id="econometric",
        title="计量模型分析",
        title_en="Econometric Analysis",
        section_type=SectionType.ECONOMETRIC,
        order=6,
        subsections=["模型设定", "数据说明", "实证结果", "稳健性"],
        prompt_template="""展示{topic}的计量经济学分析。
包括：1) 模型设定和假设；2) 数据来源和处理；3) 核心实证结果；4) 稳健性检验。
""",
        min_words=800,
        max_words=1500,
    ),
    ReportSection(
        id="scenario",
        title="情景预测",
        title_en="Scenario Analysis",
        section_type=SectionType.ECONOMETRIC,
        order=7,
        subsections=["基准预测", "乐观情景", "悲观情景", "尾部风险"],
        prompt_template="""对{topic}进行情景分析和预测。
设定不同假设下的情景，评估：1) 基准预测；2) 上下行风险。
""",
        min_words=400,
        max_words=800,
    ),
    ReportSection(
        id="policy_rec",
        title="政策建议",
        title_en="Policy Recommendations",
        section_type=SectionType.RECOMMENDATION,
        order=8,
        subsections=["货币政策建议", "财政政策建议", "结构性改革建议"],
        prompt_template="""基于分析给出{topic}的政策建议。
区分短期和中长期，分别提出货币、财政和结构性改革建议。
""",
        min_words=400,
        max_words=800,
    ),
]

MACRO_REPORT_TEMPLATE = ReportTemplate(
    name="8-Section 宏观研究报告",
    report_type=ReportType.MACRO,
    sections=MACRO_8_SECTIONS,
    description="完整的宏观研究报告模板，适合经济研究、政策分析",
    target_audience="政策制定者、研究机构、宏观经济分析师",
    typical_length_words=10000,
)


# ─── Helper Functions ────────────────────────────────────────────────────────────


def get_template(report_type: ReportType) -> ReportTemplate:
    """Get report template by type."""
    templates = {
        ReportType.EQUITY: EQUITY_REPORT_TEMPLATE,
        ReportType.MACRO: MACRO_REPORT_TEMPLATE,
    }
    return templates.get(report_type, EQUITY_REPORT_TEMPLATE)


def list_templates() -> list[dict]:
    """List all available templates."""
    return [
        EQUITY_REPORT_TEMPLATE.to_dict(),
        MACRO_REPORT_TEMPLATE.to_dict(),
    ]


def generate_section_prompt(
    template: ReportTemplate,
    section_id: str,
    context: dict[str, Any],
) -> str:
    """Generate prompt for a specific section."""
    section = template.get_section(section_id)
    if not section:
        return ""

    prompt = section.prompt_template
    for key, value in context.items():
        placeholder = f"{{ {key} }}"
        prompt = prompt.replace(placeholder, str(value))

    return prompt


def validate_report_completeness(
    template: ReportTemplate,
    completed_sections: set[str],
) -> dict:
    """Validate report completeness against template."""
    required_ids = {s.id for s in template.sections if s.required}
    completed_required = required_ids.intersection(completed_sections)

    missing_required = required_ids - completed_required
    optional_completed = completed_sections - required_ids

    coverage = len(completed_required) / len(required_ids) if required_ids else 0

    return {
        "complete": len(missing_required) == 0,
        "coverage": f"{coverage:.0%}",
        "required_completed": len(completed_required),
        "required_total": len(required_ids),
        "missing_required": list(missing_required),
        "optional_completed": list(optional_completed),
    }


def export_template_json(template: ReportTemplate, path: str | Path) -> None:
    """Export template to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)


# ─── CLI Interface ──────────────────────────────────────────────────────────────


def main():
    """CLI interface for report templates."""
    import argparse

    parser = argparse.ArgumentParser(description="Financial Report Templates")
    parser.add_argument("--list", action="store_true", help="List all templates")
    parser.add_argument("--outline", choices=["equity", "macro"], help="Generate outline")
    parser.add_argument("--validate", type=str, help="Validate completeness (comma-separated section IDs)")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_templates(), ensure_ascii=False, indent=2))

    elif args.outline:
        template = get_template(ReportType.EQUITY if args.outline == "equity" else ReportType.MACRO)
        print(template.generate_outline())

    elif args.validate:
        sections = set(args.validate.split(","))
        result = validate_report_completeness(EQUITY_REPORT_TEMPLATE, sections)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
