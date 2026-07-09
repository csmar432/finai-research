"""Three staggered-DID case studies on real Chinese firm-level data.
All estimates: two-way FE (firm+year), SE clustered by firm.
Outputs JSON results + event-study coefficients for LaTeX table generation.
"""
import warnings; warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
from pathlib import Path
from linearmodels.panel import PanelOLS

P = Path("output/fin-experiments/case_studies/staged")
R = Path("output/fin-experiments/case_studies/results")
R.mkdir(parents=True, exist_ok=True)
CTRL = ["Size", "Lev", "ROA", "Growth", "Top1", "ListAge"]
results = {}

def winsor(s, p=0.01):
    lo, hi = s.quantile(p), s.quantile(1 - p)
    return s.clip(lo, hi)

def load_controls():
    c = pd.read_parquet(P / "controls_b13.parquet")
    for col in CTRL:
        if col in c.columns:
            c[col] = pd.to_numeric(c[col], errors="coerce")
    return c

def twfe(df, y, treat, controls, cl="stkcd"):
    d = df.dropna(subset=[y, treat] + controls).copy()
    d = d.set_index(["stkcd", "year"])
    exog = [treat] + controls
    mod = PanelOLS(d[y], d[exog], entity_effects=True, time_effects=True, drop_absorbed=True)
    res = mod.fit(cov_type="clustered", cluster_entity=True)
    return res, d

def summarize(res, treat):
    return {
        "coef": float(res.params[treat]),
        "se": float(res.std_errors[treat]),
        "t": float(res.tstats[treat]),
        "p": float(res.pvalues[treat]),
        "n": int(res.nobs),
        "r2_within": float(res.rsquared_within),
    }

def event_study(df, y, tcol, controls, span=(-5, 5), bucket=None):
    d = df.copy()
    fty = d[d[tcol] == 1].groupby("stkcd")["year"].min().rename("fty")
    d = d.merge(fty, on="stkcd", how="left")
    d["evt"] = d["year"] - d["fty"]
    d.loc[d["fty"].isna(), "evt"] = np.nan
    if bucket:
        d["evt"] = (d["evt"] // bucket) * bucket
    lo, hi = span
    dd = d.dropna(subset=[y] + controls).copy()
    # relative-time dummies, omit -1 as base
    for k in range(lo, hi + 1):
        if k == -1:
            continue
        lab = f"evt_m{abs(k)}" if k < 0 else f"evt_p{k}"
        if k <= lo:
            dd[lab] = (dd["evt"] <= lo).astype(int)
        elif k >= hi:
            dd[lab] = (dd["evt"] >= hi).astype(int)
        else:
            dd[lab] = (dd["evt"] == k).astype(int)
    # never-treated stay 0 on all dummies
    evt_cols = [c for c in dd.columns if c.startswith("evt_")]
    dd = dd.set_index(["stkcd", "year"])
    mod = PanelOLS(dd[y], dd[evt_cols + controls], entity_effects=True, time_effects=True)
    res = mod.fit(cov_type="clustered", cluster_entity=True)
    out = {}
    for k in range(lo, hi + 1):
        if k == -1:
            out[k] = {"coef": 0.0, "se": 0.0}
            continue
        lab = f"evt_m{abs(k)}" if k < 0 else f"evt_p{k}"
        out[k] = {"coef": float(res.params[lab]), "se": float(res.std_errors[lab])}
    return out

ctrl = load_controls()

# ============ CS1: 低碳城市试点 -> 企业创新 (LnRD) ============
print("=== CS1: Low-carbon city pilot -> firm innovation ===")
lc = pd.read_parquet(P / "cs1_lowcarbon.parquet")
inno = pd.read_parquet(P / "outcome_innovation.parquet")
inno["LnRD"] = pd.to_numeric(inno["LnRD"], errors="coerce")
d1 = lc.merge(inno[["stkcd", "year", "LnRD", "Patent1"]], on=["stkcd", "year"], how="inner")
d1 = d1.merge(ctrl[["stkcd", "year"] + CTRL], on=["stkcd", "year"], how="left")
d1["Patent1"] = pd.to_numeric(d1["Patent1"], errors="coerce"); d1["ln_pat"] = np.log1p(d1["Patent1"].clip(lower=0)); d1["ln_pat"] = winsor(d1["ln_pat"])
res1, _ = twfe(d1, "ln_pat", "lowcarbon", CTRL)
results["cs1"] = {"main": summarize(res1, "lowcarbon")}
print("  main:", results["cs1"]["main"])
# no-controls spec
res1b, _ = twfe(d1, "ln_pat", "lowcarbon", [])

results["cs1"]["nocontrol"] = summarize(res1b, "lowcarbon")
# event study
results["cs1"]["event"] = event_study(d1, "ln_pat", "lowcarbon", CTRL)
# heterogeneity: SOE
d1s = d1.merge(ctrl[["stkcd", "year", "SOE"]], on=["stkcd", "year"], how="left")
for grp, gv in [("SOE", 1), ("nonSOE", 0)]:
    sub = d1s[d1s["SOE"] == gv]
    try:
        rr, _ = twfe(sub, "ln_pat", "lowcarbon", CTRL)
        results["cs1"][f"het_{grp}"] = summarize(rr, "lowcarbon")
    except Exception as e:
        results["cs1"][f"het_{grp}"] = {"error": str(e)}

# ============ CS2: 绿色信贷 -> 融资约束 (SA index) ============
print("=== CS2: Green credit -> financing constraint (SA) ===")
gc = pd.read_parquet(P / "cs2_greencredit.parquet")
sa = ctrl[["stkcd", "year", "SA指数"]].rename(columns={"SA指数": "SA"})
sa["SA"] = pd.to_numeric(sa["SA"], errors="coerce")
d2 = gc.merge(sa, on=["stkcd", "year"], how="inner")
d2 = d2.merge(ctrl[["stkcd", "year"] + CTRL], on=["stkcd", "year"], how="left")
d2["SA"] = winsor(d2["SA"])
treat2 = "did"
res2, _ = twfe(d2, "SA", treat2, CTRL)
results["cs2"] = {"main": summarize(res2, treat2)}
print("  main:", results["cs2"]["main"])
res2b, _ = twfe(d2, "SA", treat2, [])
results["cs2"]["nocontrol"] = summarize(res2b, treat2)
results["cs2"]["event"] = event_study(d2, "SA", treat2, CTRL)

# ============ CS3: 大数据综试区 -> 企业AI创新 ============
print("=== CS3: Big-data pilot zone -> firm AI patents ===")
bd = pd.read_parquet(P / "cs3_bigdata.parquet")
ai = pd.read_parquet(P / "outcome_ai_patents.parquet")
ai["ai_patents"] = pd.to_numeric(ai["ai_patents"], errors="coerce")
d3 = bd.merge(ai, on=["stkcd", "year"], how="inner")
d3 = d3.merge(ctrl[["stkcd", "year"] + CTRL], on=["stkcd", "year"], how="left")
d3["ln_ai"] = np.log1p(d3["ai_patents"].clip(lower=0))
res3, _ = twfe(d3, "ln_ai", "bigdata", CTRL)
results["cs3"] = {"main": summarize(res3, "bigdata")}
print("  main:", results["cs3"]["main"])
res3b, _ = twfe(d3, "ln_ai", "bigdata", [])
results["cs3"]["nocontrol"] = summarize(res3b, "bigdata")
results["cs3"]["event"] = event_study(d3, "ln_ai", "bigdata", CTRL)

# sample sizes / summary
results["_meta"] = {
    "cs1_desc": "Low-carbon city pilot (staggered 2010/2012/2017) -> Ln(R&D). TWFE, SE clustered by firm.",
    "cs2_desc": "Green Credit Guidelines (2012) -> SA financing-constraint index. TWFE.",
    "cs3_desc": "National big-data pilot zone (2016+) -> Ln(1+AI patents). TWFE.",
    "controls": CTRL,
}
json.dump(results, open(R / "case_results.json", "w"), indent=2, ensure_ascii=False)
print("\nSaved", R / "case_results.json")
