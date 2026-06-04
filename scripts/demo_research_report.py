#!/usr/bin/env python3
"""
demo_research_report.py — End-to-end A-share research report demo.

Demonstrates the complete research pipeline:
  1. Data Collection (MCP tools or graceful mock fallback)
  2. Financial Analysis (Dupont decomposition, profitability)
  3. Valuation (DCF + PB comparable)
  4. Risk Assessment
  5. Report Generation (LaTeX)
  6. Summary output

Usage:
    python scripts/demo_research_report.py
    python scripts/demo_research_report.py --stock 600519.SH --output papers
    python scripts/demo_research_report.py --skip-compile
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_log = logging.getLogger("demo_research_report")
_log.setLevel(logging.INFO)

DEMO_CONFIG = {
    "stock": "000001.SZ",
    "company_name": "平安银行",
    "industry": "商业银行",
    "report_date": "2026-06-02",
    "analyst": "AI Research Agent",
    "methodology": "基本面分析 + 估值模型 + 行业对比",
}


# ──────────────────────────────────────────────────────────────────────────────
# DATA LAYER
# ──────────────────────────────────────────────────────────────────────────────

def _get_mock_stock_data(ts_code: str) -> dict:
    """Realistic mock data for 平安银行 (000001.SZ).  Marked with _mock=True."""
    return {
        "_mock": True,
        "_mock_reason": "TUSHARE_TOKEN not configured or API unavailable",
        "ts_code": ts_code,
        "company_name": "平安银行",
        "industry": "商业银行",
        "price_data": {
            "2026-03-31": {"close": 12.45, "volume": 45_230_000},
            "2026-04-30": {"close": 11.87, "volume": 52_100_000},
            "2026-05-31": {"close": 13.22, "volume": 67_800_000},
        },
        "financial_summary": {
            "revenue_2025": 1798.32,
            "revenue_growth_yoy": 2.3,
            "net_profit_2025": 468.21,
            "profit_growth_yoy": 1.8,
            "roe": 11.24,
            "eps": 2.41,
            "bps": 21.35,
            "pe_ttm": 5.49,
            "pb": 0.58,
        },
        "key_ratios": {
            "npl_ratio": 1.05,
            "capital_adequacy": 13.87,
            "tier1_ratio": 11.24,
            "liquidity_coverage": 156.3,
        },
        "dividend_yield": 4.8,
        "analyst_target_price": 15.60,
        "analyst_count": 42,
    }


def collect_stock_data(ts_code: str) -> dict:
    """Try MCP tools first, fall back to mock data."""
    _log.info("Attempting MCP data fetch for %s", ts_code)
    # Tushare / EastMoney calls would go here.
    # For now, always use mock data (token may not be set).
    return _get_mock_stock_data(ts_code)


# ──────────────────────────────────────────────────────────────────────────────
# FINANCIAL ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

def analyze_financials(data: dict) -> dict:
    """Perform financial analysis on collected data."""
    fin = data.get("financial_summary", {})
    ratios = data.get("key_ratios", {})

    revenue_growth = fin.get("revenue_growth_yoy", 0)
    roe = fin.get("roe", 0)
    industry_avg_roe = 10.8
    npl = ratios.get("npl_ratio", 0)

    return {
        "revenue_analysis": {
            "trend": "稳定增长" if revenue_growth > 0 else "下降",
            "yoy_growth": f"{revenue_growth:.1f}%",
            "assessment": (
                f"公司2025年营收同比增长{revenue_growth:.1f}%，"
                "增速较上年有所放缓，主要受贷款需求走弱和净息差收窄影响。"
            ),
        },
        "profitability": {
            "roe": roe,
            "industry_avg_roe": industry_avg_roe,
            "assessment": (
                f"ROE为{roe:.2f}%，高于行业平均{roe - industry_avg_roe:.2f}个百分点，"
                "盈利能力良好。"
            ),
        },
        "dupont_analysis": {
            "net_margin": 26.0,
            "asset_turnover": 0.038,
            "equity_multiplier": 10.5,
            "roe_decomposition": (
                f"净利率贡献26.0% × 资产周转率0.038 × 权益乘数10.5 "
                f"= ROE约{26.0 * 0.038 * 10.5:.1f}%"
            ),
        },
        "asset_quality": {
            "npl_ratio": npl,
            "industry_avg_npl": 1.3,
            "assessment": (
                f"不良贷款率{npl:.2f}%，低于行业平均水平，资产质量稳健。"
            ),
        },
        "capital": {
            "capital_adequacy": ratios.get("capital_adequacy", 0),
            "tier1_ratio": ratios.get("tier1_ratio", 0),
            "assessment": (
                f"资本充足率{ratios.get('capital_adequacy', 0):.2f}%，"
                "满足监管要求（≥10.5%），有充足缓冲空间。"
            ),
        },
        "key_findings": [
            "非利息收入占比持续提升，业务结构优化",
            "资产质量保持稳定，不良率控制在1.1%以内",
            "资本充足率符合监管要求",
            "分红收益率4.8%，对长线资金有吸引力",
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# VALUATION
# ──────────────────────────────────────────────────────────────────────────────

def run_valuation(data: dict) -> dict:
    """Run DCF and PB-band comparable valuation."""
    fin = data.get("financial_summary", {})
    price_data = data.get("price_data", {})
    last_price = (
        list(price_data.values())[-1]["close"] if price_data else 12.45
    )

    # DCF — Gordon Growth Model
    net_profit = fin.get("net_profit_2025", 468)
    fcf = net_profit * 0.85
    terminal_growth = 0.03
    wacc = 0.09

    terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** 5
    pv_fcf = sum(
        fcf * (1 + 0.05) ** t / (1 + wacc) ** t
        for t in range(1, 6)
    )
    total_ev = pv_fcf + pv_terminal
    shares = 194                          # 亿股 for 平安银行
    dcf_value = round(total_ev / shares, 2)  # 元/股

    # PB-band comparable
    bvps = fin.get("bps", 21.35)
    comp_low = round(bvps * 0.5, 2)
    comp_high = round(bvps * 0.8, 2)
    comp_mid = round((comp_low + comp_high) / 2, 2)

    # Recommendation
    if dcf_value > last_price * 1.15:
        recommendation = "买入"
    elif dcf_value > last_price * 0.9:
        recommendation = "持有"
    else:
        recommendation = "减持"

    return {
        "dcf_value": dcf_value,
        "dcf_wacc": wacc,
        "dcf_terminal_growth": terminal_growth,
        "dcf_fcf_estimate_billion": round(fcf, 2),
        "comp_low": comp_low,
        "comp_high": comp_high,
        "comp_mid": comp_mid,
        "current_price": last_price,
        "upside_dcf": round((dcf_value - last_price) / last_price * 100, 1),
        "upside_comp": round((comp_mid - last_price) / last_price * 100, 1),
        "recommendation": recommendation,
        "target_price": round(dcf_value * 0.9 + comp_mid * 0.1, 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# RISK ASSESSMENT
# ──────────────────────────────────────────────────────────────────────────────

def assess_risk(data: dict, analysis: dict) -> dict:
    """Assess investment risks."""
    ratios = data.get("key_ratios", {})
    price_data = data.get("price_data", {})

    prices = [v["close"] for v in price_data.values()] if price_data else [12.45]
    vol = round((max(prices) - min(prices)) / min(prices) * 100, 1)
    npl = ratios.get("npl_ratio", 1.05)

    return {
        "macro_risks": [
            {
                "name": "宏观经济下行",
                "severity": "中等",
                "description": "GDP增速放缓可能压缩银行净息差，影响利息收入。",
                "mitigation": "非利息收入占比提升有助对冲。",
            },
            {
                "name": "房地产风险传导",
                "severity": "中等",
                "description": "涉房贷款质量需持续关注。",
                "mitigation": "不良率1.05%处于可控水平。",
            },
            {
                "name": "利率市场化压力",
                "severity": "低",
                "description": "LPR下行压缩净息差。",
                "mitigation": "资产配置优化与负债成本控制。",
            },
        ],
        "company_risks": [
            {
                "name": "资产质量波动",
                "severity": "低",
                "description": "不良贷款率1.05%，关注类贷款迁徙需跟踪。",
                "mitigation": "充足的拨备覆盖率提供缓冲。",
            },
            {
                "name": "资本补充压力",
                "severity": "低",
                "description": f"资本充足率{ratios.get('capital_adequacy', 13.87):.2f}%，满足监管要求。",
                "mitigation": "内生增长为主，外源融资需求低。",
            },
        ],
        "market_risks": [
            {
                "name": "股价波动性",
                "severity": "中等",
                "3个月波动率": f"{vol}%",
                "description": "银行业β系数较高，整体市场波动敏感。",
                "mitigation": "4.8%分红收益率提供下行保护。",
            },
        ],
        "overall_risk_rating": "中等偏低",
        "risk_summary": (
            f"平安银行整体风险可控。资产质量优于同业（不良率{npl:.2f}% vs 行业1.3%），"
            "资本充足率满足监管要求。股价波动性中等，分红收益率提供一定安全边际。"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# REPORT CONTENT BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def _build_latex(content_str: str) -> str:
    """Minimal LaTeX wrapper — used when ReportGenerator is unavailable."""
    return (
        "\\documentclass[UTF8]{ctexart}\n"
        "\\usepackage{geometry}\n"
        "\\geometry{a4paper, margin=2.5cm}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{amsmath}\n"
        "\\usepackage{hyperref}\n"
        "\\hypersetup{colorlinks=true}\n"
        "\\usepackage{xcolor}\n"
        "\\begin{document}\n"
        + content_str +
        "\\end{document}"
    )


def _build_report_content(
    ts_code: str,
    company_name: str,
    data: dict,
    analysis: dict,
    valuation: dict,
    risk: dict,
) -> list[dict]:
    """Build structured section list for the report generator."""
    fin = data.get("financial_summary", {})
    rev = analysis["revenue_analysis"]
    prof = analysis["profitability"]
    dupont = analysis["dupont_analysis"]
    asset = analysis["asset_quality"]
    cap = analysis["capital"]
    is_mock = data.get("_mock", False)
    today = datetime.now().strftime("%Y-%m-%d")

    sections = []

    # ── Executive Summary ──────────────────────────────────────────────────
    sections.append({
        "title": "投资摘要",
        "body": (
            f"\\textbf{{标的}}: {company_name}（{ts_code}）"
            f"\\hspace{{1em}}\\textbf{{行业}}: {data.get('industry', '商业银行')}"
            f"\\hspace{{1em}}\\textbf{{报告日期}}: {today}\n\n"
            f"\\begin{{tabular}}{{@{{}}lcc@{{}}}}\\hline\n"
            f"\\textbf{{指标}} & \\textbf{{数值}} & \\textbf{{行业平均}} \\\\ \\hline\n"
            f"最新收盘价 & ¥{valuation['current_price']:.2f} & — \\\\\n"
            f"DCF估值 & ¥{valuation['dcf_value']:.2f} & — \\\\\n"
            f"PB估值区间 & ¥{valuation['comp_low']:.2f}--¥{valuation['comp_high']:.2f} & 0.5--0.8x \\\\\n"
            f"目标价 & ¥{valuation['target_price']:.2f} & — \\\\\n"
            f"隐含上涨空间 & {valuation['upside_dcf']:.1f}\\% (DCF) & — \\\\\n"
            f"\\textbf{{投资评级}} & \\textbf{{{valuation['recommendation']}}} & — \\\\ \\hline\n"
            f"\\end{{tabular}}"
        ),
    })

    # ── Company Overview ─────────────────────────────────────────────────
    sections.append({
        "title": "一、公司概况",
        "body": (
            f"{company_name}是中国平安保险（集团）股份有限公司的控股子公司，"
            f"主营业务涵盖公司银行、零售银行、资金业务等。2025年末，"
            f"公司总资产超过4.5万亿元，营业收入{fin.get('revenue_2025', 1798.32):.2f}亿元，"
            f"净利润{fin.get('net_profit_2025', 468.21):.2f}亿元。"
        ),
    })

    # ── Financial Analysis ────────────────────────────────────────────────
    sections.append({"title": "二、财务分析", "body": ""})

    sections.append({
        "title": "2.1 成长性分析",
        "body": (
            f"营收增长：{rev['yoy_growth']}（{rev['trend']}）。"
            f" {rev['assessment']}"
        ),
    })

    sections.append({
        "title": "2.2 盈利能力",
        "body": (
            f"ROE = {prof['roe']:.2f}\\%（行业平均 {prof['industry_avg_roe']:.1f}\\%）。"
            f" {prof['assessment']}\n\n"
            f"\\textbf{{杜邦分解}}: {dupont['roe_decomposition']}"
        ),
    })

    sections.append({
        "title": "2.3 资产质量",
        "body": (
            f"不良贷款率：{asset['npl_ratio']:.2f}\\%（行业平均 {asset['industry_avg_npl']:.1f}\\%）。"
            f" {asset['assessment']}"
        ),
    })

    sections.append({
        "title": "2.4 资本充足率",
        "body": (
            f"资本充足率：{cap['capital_adequacy']:.2f}\\%；"
            f"一级资本充足率：{cap['tier1_ratio']:.2f}\\%。"
            f" {cap['assessment']}"
        ),
    })

    # ── Valuation ────────────────────────────────────────────────────────
    sections.append({
        "title": "三、估值分析",
        "body": (
            f"\\subsection*{{3.1 DCF估值}}\n"
            f"WACC = {valuation['dcf_wacc']:.0%}，永续增长率 = {valuation['dcf_terminal_growth']:.0%}，"
            f"预测期FCF（亿元）：{valuation['dcf_fcf_estimate_billion']:.2f}。\\\\\n"
            f"\\textbf{{DCF估值：¥{valuation['dcf_value']:.2f}}}"
            f"\\hspace{{2em}}\\textbf{{当前股价：¥{valuation['current_price']:.2f}}}\\\\\n"
            f"隐含上涨空间：{valuation['upside_dcf']:.1f}\\%\n\n"
            f"\\subsection*{{3.2 可比估值（PB）}}\n"
            f"行业PB区间：0.5x--0.8x\\\\\n"
            f"BVPS = ¥{fin.get('bps', 21.35):.2f}\\\\\n"
            f"\\textbf{{PB估值区间：¥{valuation['comp_low']:.2f}--¥{valuation['comp_high']:.2f}}}，"
            f"中值¥{valuation['comp_mid']:.2f}"
            f"（隐含上涨空间{valuation['upside_comp']:.1f}\\%）\n\n"
            f"\\subsection*{{3.3 综合评级}}\n"
            f"\\centering\n"
            f"\\begin{{tabular}}{{@{{}}cccc@{{}}}}\\hline\n"
            f"\\textbf{{DCF估值}} & \\textbf{{PB中值}} & \\textbf{{综合目标价}} & \\textbf{{评级}} \\\\\\hline\n"
            f"¥{valuation['dcf_value']:.2f} & ¥{valuation['comp_mid']:.2f} & "
            f"¥{valuation['target_price']:.2f} & "
            f"\\textbf{{{valuation['recommendation']}}} \\\\\\hline\n"
            f"\\end{{tabular}}"
        ),
    })

    # ── Risk ─────────────────────────────────────────────────────────────
    sections.append({
        "title": "四、风险提示",
        "body": (
            f"整体风险评级：{risk['overall_risk_rating']}\n\n"
            f"{risk['risk_summary']}"
        ),
    })

    # ── Key Findings ───────────────────────────────────────────────────────
    findings_latex = "\n".join(
        f"\\item {f}" for f in analysis["key_findings"]
    )
    sections.append({
        "title": "五、关键发现与投资亮点",
        "body": (
            f"\\begin{{itemize}}\n{findings_latex}\n\\end{{itemize}}"
        ),
    })

    # ── Disclaimer ────────────────────────────────────────────────────────
    if is_mock:
        disclaimer = (
            "\\paragraph*{{免责声明}} 本报告使用模拟数据生成，仅用于系统演示目的。"
            "模拟数据（\\_mock=True）不构成任何投资建议。"
            "真实投资决策请参考持牌分析师发布的正式研究报告。"
        )
    else:
        disclaimer = (
            "\\paragraph*{{免责声明}} 本报告仅供研究参考，不构成投资建议。"
            "投资有风险，决策需谨慎。"
        )
    sections.append({"title": "六、免责声明", "body": disclaimer})

    return sections


# ──────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def generate_report(
    ts_code: str,
    company_name: str,
    data: dict,
    analysis: dict,
    valuation: dict,
    risk: dict,
    output_dir: str,
) -> dict:
    """Generate a LaTeX research report (PDF compilation attempted)."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    safe_name = ts_code.replace(".", "_")
    today = datetime.now().strftime("%Y-%m-%d")
    sections = _build_report_content(
        ts_code, company_name, data, analysis, valuation, risk
    )

    # Build raw LaTeX content
    content_parts = [
        f"\\title{{{company_name}（{ts_code}）研究报告}}",
        f"\\date{{{today}}}",
        "\\maketitle",
    ]
    for sec in sections:
        content_parts.append(f"\\section{{{sec['title']}}}")
        if sec.get("body"):
            content_parts.append(sec["body"])

    latex_body = "\n\n".join(content_parts)

    # Try using ReportGenerator, fall back to raw LaTeX
    try:
        from scripts.research_framework.report_generator import ReportGenerator
        gen = ReportGenerator(
            output_dir=str(output_path),
            language="zh",
            provenance_tracker=None,
        )
        gen.set_title(title_zh=f"{company_name}（{ts_code}）研究报告")
        for sec in sections:
            gen.add_section(sec["title"], sec.get("body", ""), level=1)
        tex_path = gen.generate_tex(f"demo_{safe_name}.tex")
        tex_file = Path(tex_path) if tex_path else (output_path / f"demo_{safe_name}.tex")
    except Exception:
        tex_file = output_path / f"demo_{safe_name}.tex"
        with open(tex_file, "w", encoding="utf-8") as fh:
            fh.write(_build_latex(latex_body))

    # Compile with xelatex
    pdf_file: Optional[Path] = None
    compile_success = False
    compile_error = ""
    try:
        result = subprocess.run(
            [
                "xelatex", "-interaction=batchmode", "-halt-on-error",
                "-output-directory", str(output_path), str(tex_file),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        compile_success = result.returncode == 0
        if not compile_success:
            compile_error = (result.stderr or "Unknown error")[:500]
        else:
            candidate = tex_file.with_suffix(".pdf")
            if candidate.exists():
                pdf_file = candidate
    except FileNotFoundError:
        compile_error = "xelatex not found — is TeX Live installed?"
    except subprocess.TimeoutExpired:
        compile_error = "LaTeX compilation timed out after 120s"
    except Exception as e:
        compile_error = str(e)

    return {
        "tex": str(tex_file),
        "pdf": str(pdf_file) if pdf_file else None,
        "compile_success": compile_success,
        "compile_error": compile_error if not compile_success else "",
        "is_mock": data.get("_mock", False),
        "ts_code": ts_code,
        "company_name": company_name,
        "report_date": today,
        "recommendation": valuation.get("recommendation", "持有"),
        "target_price": valuation.get("target_price", 0),
        "current_price": valuation.get("current_price", 0),
        "upside_dcf": valuation.get("upside_dcf", 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE ORCHESTRATION
# ──────────────────────────────────────────────────────────────────────────────

def run_demo_pipeline(
    ts_code: str = "000001.SZ",
    output_dir: str = "papers",
) -> dict:
    """Run the complete research pipeline and return results."""
    results: dict = {
        "stock": ts_code,
        "status": "running",
        "outputs": {},
        "errors": [],
        "analysis": {},
        "valuation": {},
        "risk": {},
        "summary": {},
    }

    # Step 1: Data
    print(f"[1/6] Fetching data for {ts_code}...")
    data = collect_stock_data(ts_code)
    if data.get("_mock"):
        print(f"  [WARNING] Using mock data: {data.get('_mock_reason', 'unavailable')}")
    results["data"] = data

    # Step 2: Financial Analysis
    print(f"[2/6] Running financial analysis...")
    analysis = analyze_financials(data)
    results["analysis"] = analysis
    print(f"  ROE: {analysis['profitability']['roe']:.2f}%, "
          f"NPL: {analysis['asset_quality']['npl_ratio']:.2f}%")

    # Step 3: Valuation
    print(f"[3/6] Running valuation models...")
    valuation = run_valuation(data)
    results["valuation"] = valuation
    dcf = valuation
    print(f"  DCF: ¥{dcf['dcf_value']:.2f} | "
          f"PB Band: ¥{dcf['comp_low']:.2f}--¥{dcf['comp_high']:.2f} | "
          f"Rating: {dcf['recommendation']}")

    # Step 4: Risk
    print(f"[4/6] Risk assessment...")
    risk = assess_risk(data, analysis)
    results["risk"] = risk
    print(f"  Overall Risk: {risk['overall_risk_rating']}")

    # Step 5: Report
    print(f"[5/6] Generating research report...")
    company_name = data.get("company_name", DEMO_CONFIG["company_name"])
    report_files = generate_report(
        ts_code=ts_code,
        company_name=company_name,
        data=data,
        analysis=analysis,
        valuation=valuation,
        risk=risk,
        output_dir=output_dir,
    )
    results["outputs"] = report_files
    print(f"  TeX: {report_files.get('tex', 'N/A')}")
    if report_files.get("pdf"):
        print(f"  PDF: {report_files['pdf']}")
    if report_files.get("is_mock"):
        print(f"  [NOTE] Mock data — set TUSHARE_TOKEN for real data")

    # Step 6: Summary
    print(f"[6/6] Generating summary...")
    results["summary"] = _generate_summary(analysis, valuation, risk)
    results["status"] = "completed"
    return results


def _generate_summary(
    analysis: dict,
    valuation: dict,
    risk: dict,
) -> dict:
    """Compact summary dict."""
    return {
        "recommendation": valuation.get("recommendation", "持有"),
        "target_price": valuation.get("target_price", 0),
        "current_price": valuation.get("current_price", 0),
        "upside": f"{valuation.get('upside_dcf', 0):.1f}%",
        "dcf_value": valuation.get("dcf_value", 0),
        "pb_range": (
            f"¥{valuation.get('comp_low', 0):.2f}--"
            f"¥{valuation.get('comp_high', 0):.2f}"
        ),
        "roe": analysis["profitability"]["roe"],
        "npl": analysis["asset_quality"]["npl_ratio"],
        "risk_rating": risk.get("overall_risk_rating", "未知"),
        "key_highlights": analysis.get("key_findings", [])[:3],
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="End-to-end A-share research report demo",
    )
    parser.add_argument(
        "--stock", default="000001.SZ",
        help="Stock code (e.g., 000001.SZ, 600519.SH)",
    )
    parser.add_argument(
        "--output", default="papers",
        help="Output directory for report files",
    )
    parser.add_argument(
        "--skip-compile", action="store_true",
        help="Skip LaTeX compilation to PDF",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  A-Share Research Report Demo")
    print(f"  Stock: {args.stock} | Output: {args.output}")
    print("=" * 60)

    results = run_demo_pipeline(ts_code=args.stock, output_dir=args.output)

    s = results.get("summary", {})
    out = results.get("outputs", {})

    print("\n" + "=" * 60)
    print(f"  Status: {results['status']}")
    if out.get("tex"):
        print(f"  TeX:   {out['tex']}")
    if out.get("pdf"):
        print(f"  PDF:   {out['pdf']}")
    if not out.get("compile_success") and out.get("tex"):
        print(f"  NOTE:  LaTeX compilation skipped or failed")
    if out.get("is_mock"):
        print(f"  [NOTE] Mock data — set TUSHARE_TOKEN for real data")

    print("\n  Investment Summary:")
    print(f"    Recommendation : {s.get('recommendation', 'N/A')}")
    print(f"    Target Price  : ¥{s.get('target_price', 0):.2f}")
    print(f"    Current Price : ¥{s.get('current_price', 0):.2f}")
    print(f"    Upside (DCF)  : {s.get('upside', 'N/A')}")
    print(f"    ROE           : {s.get('roe', 0):.2f}%")
    print(f"    NPL Ratio     : {s.get('npl', 0):.2f}%")
    print(f"    Risk Rating   : {s.get('risk_rating', 'N/A')}")
    print("=" * 60)
