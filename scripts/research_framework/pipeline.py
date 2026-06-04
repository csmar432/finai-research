#!/usr/bin/env python3
"""
research_framework/pipeline.py
Main pipeline for generating academic papers from US equity data.

Usage:
    python scripts/research_framework/pipeline.py \
        --topic "ESG and Financing Constraints" \
        --language "zh" \
        --output papers/us_esg_financing/

The pipeline:
  1. Data acquisition (MCP probing with fallback)
  2. Panel construction
  3. DID regression with DOF checking
  4. Report generation (LaTeX + Word, both languages)

This is a GENERIC framework — works for any US equity empirical topic.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

# ─────────────────────────────────────────
# CORE MODULES (shared via base.py)
# ─────────────────────────────────────────
from scripts.research_framework.base import DataSource, ProvenanceTracker


# ── DOF Check ──
def check_dof(df, x_vars, firm_col, year_col, use_firm_fe, use_year_fe):
    n_obs = len(df); n_reg = len(x_vars); n_fe = 0
    if use_firm_fe and firm_col in df.columns: n_fe += df[firm_col].nunique()-1
    if use_year_fe and year_col in df.columns: n_fe += df[year_col].nunique()-1
    n_params = n_reg + n_fe; res_df = max(0, n_obs - n_params)
    is_valid = res_df >= 10
    if not is_valid:
        print(f"  ⚠ DOF WARNING: {n_obs} obs, {n_params} params, {res_df} residual df")
    return dict(n_obs=n_obs, n_params=n_params, residual_df=res_df, is_valid=is_valid,
                fallback_triggered=not is_valid)

# ── Result Extraction ──
def extract(model, xnames):
    def _to_np(arr):
        """Convert pandas Series or numpy array to numpy array safely."""
        if hasattr(arr, 'values'):
            return np.asarray(arr.values)
        return np.asarray(arr)

    if hasattr(model.params, "index"):
        names = list(model.params.index)
        params = np.asarray(model.params.values)
    else:
        names = xnames[:len(model.params)] if xnames else [f"x{i}" for i in range(len(model.params))]
        params = np.asarray(model.params)

    bses = _to_np(model.bse)
    pvals = _to_np(model.pvalues)
    tvals = _to_np(model.tvalues)

    out = {}
    for i,n in enumerate(names):
        p,s,pv,tv = float(params[i]),float(bses[i]),float(pvals[i]),float(tvals[i])
        sig = ""
        if pv < 0.001:
            sig = "***"
        elif pv < 0.01:
            sig = "**"
        elif pv < 0.05:
            sig = "*"
        elif pv < 0.10:
            sig = r"$\dagger$"
        out[n]=dict(coef=p,se=s,pval=pv,tstat=tv,sig=sig)
    return out

def fmt_coef(v): return f"${v['coef']:.4f}{v.get('sig','')}$ (${v['se']:.4f}$)"

# ── DID Regression ──
def run_did(df, y_var, treat_var, time_var, x_vars, did_name="did",
            firm_col="ticker", year_col="year",
            use_firm_fe=True, use_year_fe=True, robust_se=True):
    df_sub = df.dropna(subset=[y_var,treat_var,time_var]+x_vars)
    diag = check_dof(df_sub, [treat_var,time_var]+x_vars, firm_col, year_col, use_firm_fe, use_year_fe)
    if diag["fallback_triggered"]: use_firm_fe=False
    # Build DID term
    did_col = (df_sub[treat_var].astype(float)*df_sub[time_var].astype(float)).rename(did_name)
    # Build fixed-effect dummy variables (if any)
    fe_dummies = pd.DataFrame(index=df_sub.index)
    if use_firm_fe and firm_col in df_sub.columns:
        fe_dummies = pd.concat([fe_dummies,
            pd.get_dummies(df_sub[firm_col],prefix="firm",drop_first=True).astype(float)], axis=1)
    if use_year_fe and year_col in df_sub.columns:
        fe_dummies = pd.concat([fe_dummies,
            pd.get_dummies(df_sub[year_col],prefix="yr",drop_first=True).astype(float)], axis=1)
    # Add constant to x_vars FIRST, then append DID term and FE dummies.
    # This avoids sm.add_constant adding a duplicate column when firm/year
    # dummies are already present in the matrix (cf. regression_engine.py line 362).
    x_with_const = sm.add_constant(df_sub[x_vars].astype(float), has_constant="add")
    X = pd.concat([x_with_const, did_col, fe_dummies], axis=1).fillna(0)
    y = df_sub[y_var].astype(float).values
    model = sm.OLS(y,X.values).fit(cov_type="HC1" if robust_se else "nonrobust")
    results = extract(model, list(X.columns))
    did_coef = results.get(did_name,{}).get("coef",0)
    did_se   = results.get(did_name,{}).get("se",0)
    did_pval = results.get(did_name,{}).get("pval",1)
    return dict(did_coef=did_coef,did_se=did_se,did_pval=did_pval,
                did_sig=results.get(did_name,{}).get("sig",""),
                model=model,all_coefs=results,
                n_obs=len(df_sub),r_squared=float(model.rsquared),
                diagnostic=diag)

# ─────────────────────────────────────────
# WORD TABLE (real python-docx Table)
# ─────────────────────────────────────────
def add_docx_table(doc, caption, coefs, all_vars):
    """Add a REAL python-docx Table — not image, not text."""
    try:
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        print("  ⚠ python-docx not installed — skipping Word tables")
        return

    p = doc.add_paragraph()
    r = p.add_run(caption); r.bold=True

    # Build rows: [Variable, Coef, SE, p-value]
    rows = []
    for var in all_vars:
        if var in coefs:
            v = coefs[var]
            rows.append([var, f"{v['coef']:.4f}{v.get('sig','')}",
                       f"({v['se']:.4f})", f"{v['pval']:.4f}"])

    tbl = doc.add_table(rows=len(rows)+1, cols=4)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = tbl.rows[0].cells
    for j,h in enumerate(["Variable","Coefficient","Std Error","p-value"]):
        hdr[j].text = h
        for para in hdr[j].paragraphs:
            for run in para.runs: run.bold=True; run.font.size=Pt(9)
    for i,row_data in enumerate(rows):
        cells = tbl.rows[i+1].cells
        for j,val in enumerate(row_data):
            cells[j].text = val
            for para in cells[j].paragraphs:
                for run in para.runs: run.font.size=Pt(8)
    doc.add_paragraph()

def add_docx_figure(doc, img_path, caption):
    """Add a figure image to the Word document."""
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        return
    if not Path(img_path).exists(): return
    try:
        para = doc.add_paragraph()
        para.add_run().add_picture(str(img_path), width=Inches(5.5))
        p = doc.add_paragraph(); p.add_run(caption).italic=True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        doc.add_paragraph(f"[Figure: {caption}]")

# ─────────────────────────────────────────
# LATEX TABLE
# ─────────────────────────────────────────
def did_to_latex(results_list, y_labels, x_vars, title="", label=""):
    col_count = 1 + len(y_labels)
    col_spec = "l" + "c" * len(y_labels)
    lines = [
        "\\begin{table}[htbp]",
        "  \\centering",
        f"  \\caption{{{title}}}",
        f"  \\label{{{label}}}",
        "  \\begin{threeparttable}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        "    \\toprule",
        "    \\\\textbf{Variable} & " + " & ".join(f"\\textbf{{{y}}}" for y in y_labels) + " \\\\",
        "    \\midrule",
    ]
    for var in x_vars:
        cells = [f"\\textit{{{var}}}"]
        for res in results_list:
            c = res.get("all_coefs", {}).get(var, {})
            if c:
                cells.append(
                    f"${c.get('coef', 0):.4f}{c.get('sig', '')}$ \\quad (${c.get('se', 0):.4f}$)"
                )
            else:
                cells.append("—")
        lines.append("    " + " & ".join(cells) + " \\\\")
    lines.extend([
        "    \\bottomrule",
        "    \\textbf{N} & " + " & ".join(str(r.get("n_obs", "N")) for r in results_list) + " \\\\",
        "    \\textbf{R${}^2$} & " + " & ".join("{:.3f}".format(r.get("r_squared", 0)) for r in results_list) + " \\\\ ",
        "  \\end{tabular}",
        "  \\begin{tablenotes}",
        "    \\small",
        "    \\item Standard errors in parentheses. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
        "  \\end{tablenotes}",
        "  \\end{threeparttable}",
        "\\end{table}",
    ])
    return "\n".join(lines)

# ─────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Academic paper generation pipeline")
    ap.add_argument("--topic", default="ESG and Financing Constraints",
                    help="Research topic")
    ap.add_argument("--language", default="zh", choices=["zh","en","both"],
                    help="Output language: zh/en/both")
    ap.add_argument("--output", default="papers/us_esg_financing",
                    help="Output directory")
    ap.add_argument("--tickers", default="XOM,CVX,COP,DVN,SLB,OXY,HAL,BKR,MRO,FANG,EOG,PXD,EQT,KMI,PSX,VLO",
                    help="Comma-separated ticker list")
    ap.add_argument("--years", default="2018,2019,2020,2021,2022,2023,2024",
                    help="Comma-separated years")
    args = ap.parse_args()

    OUTPUT = Path(args.output)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/"latex").mkdir(exist_ok=True)
    (OUTPUT/"tables").mkdir(exist_ok=True)
    (OUTPUT/"figures").mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print("  Research Framework Pipeline")
    print(f"  Topic: {args.topic}")
    print(f"  Language: {args.language}")
    print(f"  Output: {OUTPUT}")
    print(f"{'='*60}\n")

    tracker = ProvenanceTracker()

    # ── Step 1: Load / build panel ──
    panel_path = OUTPUT/"panel_data.csv"
    if panel_path.exists():
        print("  [1/6] Loading cached panel...")
        df = pd.read_csv(panel_path)
    else:
        print("  [1/6] Panel data not found. Run data_fetcher.py first.")
        print("  Creating demo panel for framework validation...")
        # Build demo panel
        tickers = args.tickers.split(",")
        years = [int(y) for y in args.years.split(",")]
        np.random.seed(42)
        rows=[]
        sectors={"XOM":"integrated","CVX":"integrated","COP":"e&p","DVN":"e&p","SLB":"equipment",
                 "OXY":"e&p","HAL":"equipment","BKR":"equipment","MRO":"e&p","FANG":"e&p",
                 "EOG":"e&p","PXD":"e&p","EQT":"e&p","KMI":"midstream","PSX":"refining","VLO":"refining"}
        for t in tickers:
            sec=sectors.get(t,"e&p")
            is_high_esg=sec in ["integrated","refining"]
            for yr in years:
                ta=np.random.uniform(10e9,450e9)
                td=ta*np.random.uniform(0.08,0.45)
                ltd=td*np.random.uniform(0.5,0.9)
                ni=ta*np.random.uniform(-0.05,0.20)
                opcf=ta*np.random.uniform(0.02,0.15)
                ie=td*np.random.uniform(0.02,0.06)
                eq=ta-td
                rows.append(dict(ticker=t,year=yr,sector=sec,
                                 esg_high=int(is_high_esg),
                                 post=int(yr>=2022),
                                 did=int(is_high_esg)*(yr>=2022),
                                 ln_assets=np.log(ta),
                                 roa=ni/ta, tangibility=np.random.uniform(0.3,0.9),
                                 mb=np.random.uniform(1,4), cash_ratio=np.random.uniform(0.01,0.08),
                                 total_assets=ta,total_debt=td,long_term_debt=ltd,
                                 interest_exp=ie,net_income=ni,lev=td/ta,ltd_ratio=ltd/ta,
                                 cost_debt=ie/td*100))
                tracker.record(f"{t}:{yr}:lev",DataSource.SIMULATED,"demo panel")
        df=pd.DataFrame(rows)
        df.to_csv(panel_path,index=False)
        print(f"  ✅ Demo panel: {len(df)} obs, {df['ticker'].nunique()} firms")

    print("\n  [2/6] Panel summary:")
    print(f"      N={len(df)}, firms={df['ticker'].nunique()}, years={sorted(df['year'].unique())}")

    # ── Step 2: DID Regression ──
    print("\n  [3/6] Running DID regressions...")
    X_VARS=["ln_assets","roa","tangibility","mb","cash_ratio"]

    results_lev = run_did(df,"lev","esg_high","post",X_VARS,did_name="did",
                          firm_col="ticker",year_col="year",use_firm_fe=True,use_year_fe=True)
    results_ltd = run_did(df,"ltd_ratio","esg_high","post",X_VARS,did_name="did",
                          firm_col="ticker",year_col="year",use_firm_fe=True,use_year_fe=True)
    results_cod = run_did(df,"cost_debt","esg_high","post",X_VARS,did_name="did",
                          firm_col="ticker",year_col="year",use_firm_fe=True,use_year_fe=True)

    print(f"  DID (lev):       coef={results_lev['did_coef']:+.4f}, p={results_lev['did_pval']:.3f}")
    print(f"  DID (ltd):      coef={results_ltd['did_coef']:+.4f}, p={results_ltd['did_pval']:.3f}")
    print(f"  DID (cost_debt): coef={results_cod['did_coef']:+.4f}, p={results_cod['did_pval']:.3f}")

    # Heterogeneity
    print("\n  [4/6] Heterogeneity analysis...")
    het_results=[]
    for label,grp_df in [("E&P",df[df["sector"]=="e&p"]),
                          ("Integrated",df[df["sector"]=="integrated"]),
                          ("Equipment",df[df["sector"]=="equipment"]),
                          ("Refining",df[df["sector"]=="refining"])]:
        if len(grp_df)<10: continue
        r=run_did(grp_df,"lev","esg_high","post",X_VARS,did_name="did",
                  firm_col="ticker",year_col="year",use_firm_fe=False,use_year_fe=True)
        het_results.append((label,r))
        print(f"    {label:12s}: DID={r['did_coef']:+.4f} (p={r['did_pval']:.3f}, N={r['n_obs']})")

    # ── Step 3: Generate tables ──
    print("\n  [5/6] Generating tables...")
    all_res=[results_lev,results_ltd,results_cod]
    all_labs=["(1) lev","(2) ltd_ratio","(3) cost_debt"]
    x_vars_show=["did","esg_high","post"]+X_VARS

    # LaTeX Table 3
    latex3 = did_to_latex(all_res, all_labs, x_vars_show,
                          title="ESG and Financing Constraints — Baseline DID Results",
                          label="tab:did")
    (OUTPUT/"latex"/"table3_did.tex").write_text(latex3,encoding="utf-8")
    print("  ✅ table3_did.tex")

    # Markdown Table 3
    md_lines=["| Variable | " + " | ".join(all_labs) + " |",
              "|:---|" + "|".join(["---:"]*len(all_labs)) + "|"]
    for var in x_vars_show:
        cells=[var]
        for res in all_res:
            c=res["all_coefs"].get(var,{})
            cells.append(f"${c.get('coef',0):.4f}{c.get('sig','')}$")
        md_lines.append("| " + " | ".join(cells) + " |")
    (OUTPUT/"tables"/"table3_did.md").write_text("\n".join(md_lines),encoding="utf-8")
    print("  ✅ table3_did.md")

    # Heterogeneity table
    het_md=["| Sub-sample | N | DID Coef | SE | p-value |",
            "|:---|---:|:---|:---|:---|"]
    for label,r in het_results:
        c=r["all_coefs"].get("did",{})
        het_md.append(f"| {label} | {r['n_obs']} | ${c.get('coef',0):+.4f}{c.get('sig','')}$ | "
                     f"({c.get('se',0):.4f}) | {c.get('pval',1):.3f} |")
    (OUTPUT/"tables"/"table4_heterogeneity.md").write_text("\n".join(het_md),encoding="utf-8")
    print("  ✅ table4_heterogeneity.md")

    # Descriptive stats
    desc_cols=["lev","ltd_ratio","cost_debt","ln_assets","roa","tangibility"]
    desc=df[desc_cols].describe().T[["count","mean","std","min","50%","max"]]
    desc.columns=["N","Mean","Std","Min","Median","Max"]
    desc.index.name="Variable"
    desc.to_csv(OUTPUT/"tables"/"table2_descriptive_stats.csv")
    print("  ✅ table2_descriptive_stats.csv")

    # ── Step 4: Word document ──
    print("\n  [6/6] Generating Word document...")
    try:
        from docx import Document as DocxDocument
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor

        doc=DocxDocument()
        # Title
        t=doc.add_heading(args.topic,0)
        t.alignment=WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}")

        # Abstract
        # Prominent simulated data warning at document start
        sim_fields = tracker.simulated_fields()
        if sim_fields:
            p = doc.add_paragraph()
            run = p.add_run(
                "⚠ 警告 / WARNING: 本文使用模拟数据，结论不可外推。 "
                f"模拟字段: {', '.join(sim_fields)} "
                "| This paper uses simulated data. Findings should NOT be generalized."
            )
            run.bold = True
            run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)  # Dark red
            doc.add_paragraph()

        doc.add_heading("摘要 / Abstract",1)
        doc.add_paragraph(
            f"本文基于{len(df)}个{'公司-年度' if args.language=='zh' else 'firm-year'}观测值，"
            f"检验ESG表现对企业融资约束的影响。"
            f"基准DID估计显示，ESG_high × Post系数为{results_lev['did_coef']:+.4f}，"
            f"对应p值为{results_lev['did_pval']:.3f}。"
        )

        # Section 1
        doc.add_heading("一、研究设计" if args.language=="zh" else "1. Research Design",1)
        doc.add_paragraph(
            f"样本包括{args.tickers.count(',')+1}家{'美国能源行业上市公司' if args.language=='zh' else 'US energy sector firms'}，"
            f"时间跨度{args.years.split(',')[0]}–{args.years.split(',')[-1]}年。"
        )

        # Section 2: Results
        doc.add_heading("二、实证结果" if args.language=="zh" else "2. Empirical Results",1)
        doc.add_paragraph(
            f"表3报告了基准DID回归结果。"
            f"ESG_high × Post系数在账面杠杆方程中为{results_lev['did_coef']:+.4f}，"
            f"在长期负债率方程中为{results_ltd['did_coef']:+.4f}。"
        )

        # REAL embedded tables
        all_vars_show=["did","esg_high","post"]+X_VARS
        add_docx_table(doc, "表3: 基准DID回归结果 / Table 3: Baseline DID Results",
                      results_lev["all_coefs"], all_vars_show)

        # Heterogeneity table
        het_rows=[("E&P",r) for _,r in het_results]
        add_docx_table(doc, "表4: 异质性分析 / Table 4: Heterogeneity Analysis",
                      {k:v for k,v in het_results[0][1]["all_coefs"].items() if k=="did"},
                      ["did"])

        # Figures
        for fig in OUTPUT.glob("figures/*.png"):
            add_docx_figure(doc, str(fig), f"[{fig.stem}]")

        # Provenance appendix
        doc.add_page_break()
        doc.add_heading("附录: 数据溯源 / Appendix: Data Provenance",1)
        summary=tracker.summary()
        doc.add_paragraph(f"总字段数: {summary.get('total_fields',0)}")
        for src,cnt in summary.get("by_source",{}).items():
            doc.add_paragraph(f"• {src}: {cnt} fields")
        sim_fields=tracker.simulated_fields()
        if sim_fields:
            doc.add_paragraph(f"⚠ 模拟字段: {', '.join(sim_fields)}")

        doc_path=OUTPUT/"framework_paper.docx"
        doc.save(str(doc_path))
        print(f"  ✅ Word document: {doc_path}")
    except ImportError:
        print("  ⚠ python-docx not installed — Word document skipped")
        print("    Run: pip install python-docx")

    # ── Step 5: Save provenance ──
    tracker.save(OUTPUT/"provenance.json")
    manifest={
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": args.topic,
        "language": args.language,
        "n_obs": len(df),
        "n_firms": df["ticker"].nunique(),
        "years": sorted(df["year"].unique().tolist()),
        "did_results": {
            "lev": {"coef": results_lev["did_coef"], "se": results_lev["did_se"],
                     "pval": results_lev["did_pval"]},
            "ltd_ratio": {"coef": results_ltd["did_coef"], "se": results_ltd["did_se"],
                         "pval": results_ltd["did_pval"]},
            "cost_debt": {"coef": results_cod["did_coef"], "se": results_cod["did_se"],
                          "pval": results_cod["did_pval"]},
        },
        "heterogeneity": {label:{"coef":r["did_coef"],"pval":r["did_pval"],"n":r["n_obs"]}
                         for label,r in het_results},
        "provenance_summary": tracker.summary(),
    }
    (OUTPUT/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str))
    print("  ✅ manifest.json")

    print(f"\n{'='*60}")
    print("  Pipeline complete!")
    print(f"  Output: {OUTPUT}")
    print(f"  Simulated fields: {tracker.simulated_fields() or 'None'}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
