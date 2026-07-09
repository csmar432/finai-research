"""Generate LaTeX tables (300 DPI figures) from case_results.json."""
import json, warnings, numpy as np, matplotlib, matplotlib.pyplot as plt
warnings.filterwarnings("ignore")
matplotlib.use("Agg")

OUT = "output/fin-experiments/case_studies/results"
R   = json.load(open(f"{OUT}/case_results.json"))

def S(p):
    if p < 0.001: return "$^{***}$"
    if p < 0.01:  return "$^{**}$"
    if p < 0.05:  return "$^{*}$"
    return ""

def row(coef, se, p, n, stars=True):
    s = S(p) if stars else ""
    return f"  DID & {coef:.4f}{s} & ({se:.3f}) & {n:,} \\\\"

def tab(header, body_rows, notes, label):
    ncols = 4
    t = (f"\\begin{{table}}[htbp]\n"
         f"\\caption{{{header}}}\n"
         f"\\label{{{label}}}\n"
         f"\\centering\n"
         f"\\resizebox{{0.85\\textwidth}}{{!}}{{%\n"
         f"\\begin{{threeparttable}}\n"
         f"\\begin{{tabular}}{{lccc}}\n\\toprule\n"
         f"                               & \\mc{{1}}{{c}}{{(1)}} & \\mc{{1}}{{c}}{{(2)}} & \\mc{{1}}{{c}}{{(3)}} \\\\\n"
         f"                               & \\mc{{1}}{{c}}{{Baseline}} & \\mc{{1}}{{c}}{{Controls}} & \\mc{{1}}{{c}}{{Heterogeneity}} \\\\\n"
         f"\\midrule\n")
    for r in body_rows:
        t += r + "\n"
    t += ("\\midrule\n"
          "\\bottomrule\n\\end{tabular}\n"
          f"\\begin{{tablenotes}}\n"
          f"\\item \\textit{{Notes}}: {notes}\n"
          "\\end{tablenotes}\n"
          "\\end{threeparttable}}\n"
          "}\n\\end{table}\n")
    return t

# ── TABLE 5.1: CS1 低碳城市 → 专利 ──────────────────────────────────────────
c = R["cs1"]
r1 = c["main"]; r2 = c["nocontrol"]; r3 = c.get("het_SOE", {"coef":np.nan,"se":np.nan,"p":np.nan,"n":0})
rows = [
    row(r2["coef"],r2["se"],r2["p"],r2["n"]),
    row(r1["coef"],r1["se"],r1["p"],r1["n"]),
    row(r3.get("coef",np.nan),r3.get("se",np.nan),r3.get("p",np.nan),r3.get("n",0)),
]
t1 = tab(
    "TABLE 5.1: Effect of Low-Carbon City Pilot on Firm Innovation (Patent Applications)",
    rows,
    "TWFE DID estimates. Column (1): no controls. Column (2): with Size, Lev, ROA, Growth, Top1, ListAge. Column (3): SOE sub-sample. All specifications include firm and year fixed effects. Standard errors clustered by firm. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.1$.",
    "tab:cs1-lcc"
)
open(f"{OUT}/table_cs1_lcc.tex","w",encoding="utf-8").write(t1)

# ── TABLE 5.2: CS2 绿色信贷 → 融资约束 ──────────────────────────────────────
c = R["cs2"]
r1 = c["main"]; r2 = c["nocontrol"]
r_soe = c.get("het_SOE", {"coef":np.nan,"se":np.nan,"p":np.nan,"n":0})
rows = [
    row(r2["coef"],r2["se"],r2["p"],r2["n"]),
    row(r1["coef"],r1["se"],r1["p"],r1["n"]),
    row(r_soe.get("coef",np.nan),r_soe.get("se",np.nan),r_soe.get("p",np.nan),r_soe.get("n",0)),
]
t2 = tab(
    "TABLE 5.2: Effect of Green Credit Policy on Firm Financing Constraints (SA Index)",
    rows,
    "TWFE DID estimates. Dependent variable: SA index (higher = more constrained). Column (1): no controls. Column (2): full controls. Column (3): SOE sub-sample. All specifications include firm and year fixed effects. Standard errors clustered by firm. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.1$.",
    "tab:cs2-gc"
)
open(f"{OUT}/table_cs2_gc.tex","w",encoding="utf-8").write(t2)

# ── TABLE 5.3: CS3 大数据综试区 → AI专利 ────────────────────────────────────
c = R["cs3"]
r1 = c["main"]; r2 = c["nocontrol"]
rows = [
    row(r2["coef"],r2["se"],r2["p"],r2["n"]),
    row(r1["coef"],r1["se"],r1["p"],r1["n"]),
    "  DID &  &  &  \\\\",
]
t3 = tab(
    "TABLE 5.3: Effect of National Big-Data Pilot Zones on Firm AI Innovation",
    rows,
    "TWFE DID estimates. Dependent variable: ln(1+AI patents). Column (1): no controls. Column (2): with Size, Lev, ROA, Growth, Top1, ListAge. All specifications include firm and year fixed effects. Standard errors clustered by firm. $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.1$.",
    "tab:cs3-bd"
)
open(f"{OUT}/table_cs3_bd.tex","w",encoding="utf-8").write(t3)

# ── FIGURE 5.1: CS1 Event Study ──────────────────────────────────────────────
ev = R["cs1"]["event"]
ev_keys = sorted([k for k in ev.keys() if k not in ("error","_meta")], key=lambda x: int(x))
xs = [int(k) for k in ev_keys]
ys = [ev[k]["coef"] for k in ev_keys]
ses = [ev[k]["se"] for k in ev_keys]
hi = [y+1.96*s for y,s in zip(ys,ses)]
lo = [y-1.96*s for y,s in zip(ys,ses)]

fig, ax = plt.subplots(figsize=(7.5, 4))
ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
ax.fill_between(xs, lo, hi, alpha=0.2, color="steelblue", label="95% CI")
ax.plot(xs, ys, "o-", color="steelblue", ms=6, lw=2, label="DID coefficient")
ax.axvline(-0.5, color="red", lw=1.2, ls=":", alpha=0.7, label="Policy implementation")
# annotate significant points
for k,v in ev.items():
    try:
        k=int(k)
        if v["p"] < 0.1:
            ax.annotate("*" if v["p"]<0.05 else "+", (k, v["coef"]),
                       fontsize=12, ha="center", color="red")
    except: pass
ax.set_xlabel("Years relative to low-carbon city pilot", fontsize=10)
ax.set_ylabel("DID coefficient on ln(patents)", fontsize=10)
ax.set_title("Figure 5.1: Event Study — Low-Carbon City Pilot and Firm Innovation", fontsize=11)
ax.set_xticks(xs)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.2)
plt.tight_layout()
for fmt in ["pdf","png"]:
    fig.savefig(f"{OUT}/fig_event_cs1.{fmt}", dpi=300, bbox_inches="tight")
plt.close()

# ── FIGURE 5.2: CS3 Event Study ──────────────────────────────────────────────
ev = R["cs3"]["event"]
ev_keys = sorted([k for k in ev.keys() if k not in ("error","_meta")], key=lambda x: int(x))
xs = [int(k) for k in ev_keys]
ys = [ev[k]["coef"] for k in ev_keys]
ses = [ev[k]["se"] for k in ev_keys]
hi = [y+1.96*s for y,s in zip(ys,ses)]
lo = [y-1.96*s for y,s in zip(ys,ses)]

fig, ax = plt.subplots(figsize=(7.5, 4))
ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
ax.fill_between(xs, lo, hi, alpha=0.2, color="darkorange", label="95% CI")
ax.plot(xs, ys, "s-", color="darkorange", ms=6, lw=2, label="DID coefficient")
ax.axvline(-0.5, color="red", lw=1.2, ls=":", alpha=0.7, label="Policy implementation")
for k,v in ev.items():
    try:
        k=int(k)
        if v["p"] < 0.1:
            ax.annotate("*" if v["p"]<0.05 else "+", (k, v["coef"]),
                       fontsize=12, ha="center", color="red")
    except: pass
ax.set_xlabel("Years relative to big-data pilot zone", fontsize=10)
ax.set_ylabel("DID coefficient on ln(AI patents)", fontsize=10)
ax.set_title("Figure 5.2: Event Study — Big-Data Pilot Zones and Firm AI Innovation", fontsize=11)
ax.set_xticks(xs)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.2)
plt.tight_layout()
for fmt in ["pdf","png"]:
    fig.savefig(f"{OUT}/fig_event_cs3.{fmt}", dpi=300, bbox_inches="tight")
plt.close()

print("Tables + figures written:")
for f in ["table_cs1_lcc.tex","table_cs2_gc.tex","table_cs3_bd.tex",
           "fig_event_cs1.pdf","fig_event_cs1.png","fig_event_cs3.pdf","fig_event_cs3.png"]:
    import os.path as p; fp=f"{OUT}/{f}"
    sz=os.path.getsize(fp) if os.path.exists(fp) else 0
    print(f"  {f}  ({sz//1024} KB)")

# Summary for finai.tex
print("\n=== Results for finai.tex §5 ===")
for cs, desc in [("cs1","Low-carbon city → innovation"),
                  ("cs2","Green credit → SA constraint"),
                  ("cs3","Big-data zone → AI patents")]:
    r = R[cs]["main"]
    sig = "***" if r["p"]<0.01 else "**" if r["p"]<0.05 else "*" if r["p"]<0.1 else "n.s."
    print(f"  {cs} ({desc}): coef={r['coef']:.4f} ({sig}), se={r['se']:.4f}, p={r['p']:.4f}, N={r['n']:,}")
