"""Stage raw empirical data into the project with key normalization + provenance.
Only the columns actually used in the three case studies are extracted.
Source: /Users/xuzheyi/Desktop/实证数据 (user-provided real datasets)
"""
import pandas as pd
import numpy as np
from pathlib import Path

RAW = Path("/Users/xuzheyi/Desktop/实证数据")
OUT = Path("output/fin-experiments/case_studies/staged")
OUT.mkdir(parents=True, exist_ok=True)

def norm_code(s):
    """Normalize stock code to 6-digit zero-padded string."""
    s = pd.to_numeric(s, errors="coerce")
    return s.dropna().astype(int).astype(str).str.zfill(6)

def norm(df, code_col, year_col):
    df = df.copy()
    df["stkcd"] = pd.to_numeric(df[code_col], errors="coerce")
    df["year"] = pd.to_numeric(
        df[year_col].astype(str).str.extract(r"(\d{4})")[0], errors="coerce"
    )
    df = df.dropna(subset=["stkcd", "year"])
    df["stkcd"] = df["stkcd"].astype(int).astype(str).str.zfill(6)
    df["year"] = df["year"].astype(int)
    return df

# ---- CS1: 低碳城市试点 ----
lc = pd.read_stata(RAW / "1367 DID数据大合集2(1).0/上市公司是否属于“低碳城市”试点城市匹配数据（2010-2022）/上市公司是否属于“低碳城市”试点城市匹配数据（2010-2022）.dta")
print("低碳城市 cols:", list(lc.columns))
lc = norm(lc, "股票代码", "年份")
treat_col = [c for c in lc.columns if "低碳" in c][0]
lc = lc[["stkcd", "year", "省份", "城市", treat_col]].rename(columns={treat_col: "lowcarbon"})
lc["lowcarbon"] = pd.to_numeric(lc["lowcarbon"], errors="coerce")
lc.to_parquet(OUT / "cs1_lowcarbon.parquet")
print("CS1 staged:", lc.shape, "| treated firm-years:", int(lc['lowcarbon'].sum()))

# ---- CS3: 大数据综合试验区 ----
bd = pd.read_stata(RAW / "1367 DID数据大合集2(1).0/上市公司是否属于“国家级大数据综合试验区”匹配数据（2010-2022）/上市公司是否属于“国家级大数据综合试验区”匹配数据（2010-2022）.dta")
bd = norm(bd, "股票代码", "年份")
tcol = [c for c in bd.columns if "大数据" in c][0]
bd = bd[["stkcd", "year", "省份", "城市", tcol]].rename(columns={tcol: "bigdata"})
bd["bigdata"] = pd.to_numeric(bd["bigdata"], errors="coerce")
bd.to_parquet(OUT / "cs3_bigdata.parquet")
print("CS3 staged:", bd.shape, "| treated firm-years:", int(bd['bigdata'].sum()))

# ---- CS2: 绿色信贷 ----
gc = pd.read_stata(RAW / "1367 DID数据大合集2(1).0/绿色信贷与上市公司匹配数据（2000-2022）/绿色信贷与上市公司匹配数据（2000-2022）.dta")
print("绿色信贷 cols:", list(gc.columns))
gc = norm(gc, "股票代码", "年份")
keep = ["stkcd", "year"] + [c for c in ["policy", "gcres", "did", "行业名称", "省份", "城市"] if c in gc.columns]
gc = gc[keep]
gc.to_parquet(OUT / "cs2_greencredit.parquet")
print("CS2 staged:", gc.shape)

# ---- Outcome: AI专利 ----
ai = pd.read_excel(RAW / "1464【科技创新】上市公司人工智能专利数据（ 2001-2022年）/上市公司年度人工智能专利统计数据（2001-2022年）_ppman.xlsx")
ai = norm(ai, "股票代码", "统计年度")
pcol = [c for c in ai.columns if "专利" in c][0]
ai = ai[["stkcd", "year", pcol]].rename(columns={pcol: "ai_patents"})
ai["ai_patents"] = pd.to_numeric(ai["ai_patents"], errors="coerce")
ai.to_parquet(OUT / "outcome_ai_patents.parquet")
print("AI patents staged:", ai.shape)

# ---- Outcome: 企业创新能力 ----
inno = pd.read_excel(RAW / "上市公司企业创新能力、质量、效率-原始数据+dofile+结果（2006-2023年）(1)(1)/上市公司企业创新能力、质量、效率_未缩尾未剔除金融企业.xlsx")
inno = norm(inno, "stkcd", "year")
keep = ["stkcd", "year"] + [c for c in ["LnRD","RD","Patent1","Patent2","专利1","专利2","InnoEff1","企业性质"] if c in inno.columns]
inno = inno[keep]
inno.to_parquet(OUT / "outcome_innovation.parquet")
print("Innovation staged:", inno.shape, "| cols:", keep)

# ---- Controls: B13 ----
ctrl = pd.read_stata(RAW / "B13 上市公司常用控制变量大全2.0 [2006-2024]/常用控制变量-已剔除已缩尾.dta")
ctrl = norm(ctrl, "Stkcd", "year")
keep = ["stkcd", "year"] + [c for c in ["Size","Lev","ROA","Growth","Top1","Board","Indep","SOE","ListAge","TobinQ","SA指数","Cashflow","FC指数","KZ指数","WW指数"] if c in ctrl.columns]
ctrl = ctrl[keep]
ctrl.to_parquet(OUT / "controls_b13.parquet")
print("Controls staged:", ctrl.shape, "| cols:", keep)

print("\nAll staged to", OUT)
