# Blog Post Outlines (5 篇文章大纲)

> **5 篇博客概要**，每篇 2500 字。具体内容留给后续发布。
> 这里只给出 outline / key points，节省 token。

---

## Blog 1: "How to Fix Staggered DiD with Negative Weights"

**Target audience**: Economists using DID in 2024+
**Goal**: Demystify Callaway-Sant'Anna in 100 lines of Python
**Format**: Code-heavy, with minimal math

### Outline

1. **Hook (200 words)**: The "DID problem" — your 2x2 standard errors are wrong
   - Recent papers (Goodman-Bacon 2021, de Chaisemartin & D'Haultfoeuille 2020)
   - Show: TWFE coefficient is 0.05, true ATT is 0.15

2. **The Problem in 5 min (400 words)**
   - TWFE: Y_it = α_i + λ_t + β·D_it + ε_it
   - With staggered treatment: β is a weighted average of all 2x2 DIDs
   - Weights can be negative → "forbidden comparisons"
   - Example: state A treated in 2010, state B in 2015; TWFE uses B as control for A's pre-treatment

3. **The Fix: Callaway-Sant'Anna (600 words)**
   - Estimate ATT(g, t) for each (group, time) cell
   - Group = first treatment year (e.g., 2010 cohort)
   - Then aggregate over g and t as you wish
   - 100 lines of Python code (live demo)

4. **Code (500 words)**
   ```python
   from scripts.research_framework.modern_did import CallawaySantAnnaDID
   result = CallawaySantAnnaDID(
       outcome="green_innovation",
       treatment="is_treated",
       time_var="year",
       unit_var="firm_id",
   ).fit(df)
   result.summary()
   ```

5. **Robustness (400 words)**: Try Sun-Abraham, Borusyak, de Chaisemartin
   - Show that all 3 give similar ATT(g, t) but TWFE is biased

6. **Conclusion (200 words)**: Modern DiD is now table-stakes for empirical econ

**Code repository**: GitHub gist or full notebook

---

## Blog 2: "Why Economists Need Their Own AI Agent (Not Just ChatGPT)"

**Target audience**: Applied economists curious about LLMs
**Goal**: Show why generic AI tools don't work for econ research
**Format**: Opinion + demo

### Outline

1. **Hook (300 words)**: I tried writing a paper with ChatGPT. It hallucinated citations, made up data, and ignored the standard control set.

2. **The 4 specific gaps (1000 words)**
   - **Gap 1: Data access** — ChatGPT can't pull CSMAR, Tushare, or FRED
   - **Gap 2: Identification** — doesn't know that "carbon trading" → national ETS 2021, not 2017
   - **Gap 3: Robustness** — no idea what "PSM-DID" means or how to run it
   - **Gap 4: Style** — writes in the wrong register (NeurIPS, not JF)

3. **The FinAI approach (500 words)**
   - 43 MCP data sources
   - Pre-built CSMAR schema, 12 standard controls
   - Modern DiD, IV, GMM, RDD all built in
   - 45 journal templates (incl. 经济研究 / 金融研究)

4. **Demo: 6 min from topic to draft (500 words)**
   - Topic: 碳排放权交易对企业绿色创新的影响
   - Show the 8-stage pipeline output
   - Compare to a 6-month manual workflow

5. **What FinAI is NOT (200 words)**: autonomous fabrication, replace econometrician, etc.

**Code repository**: FinAI repo + demo GIF

---

## Blog 3: "Replicating a Published A-share Paper in 30 Minutes"

**Target audience**: PhD students, junior researchers
**Goal**: Show FinAI as a learning tool, not just a productivity tool
**Format**: Step-by-step walkthrough

### Outline

1. **Hook (200 words)**: A 2024 经济研究 paper on 绿色金融 → I replicated in 30 min

2. **The target paper (200 words)**
   - Title, journal, year
   - Identification: PSM-DID
   - Data: CSMAR 2015-2022
   - Findings: ATT = 0.07 (p<0.05)

3. **Step 1: Get the paper (5 min)**
   - Use OpenAlex MCP to find the paper by title
   - Get full text via Context7
   - Extract: data, methods, controls

4. **Step 2: Reconstruct the dataset (10 min)**
   - Use Tushare/CSMAR MCP to pull data
   - Apply the same filters
   - Build the same control set

5. **Step 3: Replicate the analysis (10 min)**
   - PSM-DID module
   - Same standard errors (cluster-robust at firm level)
   - Same sample (2015-2022, listed firms, ex-financial)

6. **Step 4: Compare and audit (5 min)**
   - Result: ATT = 0.068 (vs original 0.07) — within 5%
   - Why the 5% difference? (likely different winsorize cutoff or industry code)
   - Document the audit

7. **Conclusion (200 words)**: Replication is now a 30-min task, not 30-day

**Code repository**: Full replication package

---

## Blog 4: "From CSMAR to LaTeX: A Data-to-Paper Pipeline That Doesn't Lie"

**Target audience**: Empirical researchers worried about reproducibility
**Goal**: Make provenance tracking central to the workflow
**Format**: Architecture + philosophy

### Outline

1. **Hook (300 words)**: "Why is this paper wrong?" → 80% of the time, it's data.

2. **The reproducibility crisis in empirical econ (400 words)**
   - Many papers don't release data
   - When they do, 60% don't run (Chang & Li 2017)
   - When they do run, numbers often differ slightly
   - The fix: provenance tracking

3. **What is provenance? (300 words)**
   - Every number in the paper traceable to: data + code + commit hash
   - Example: "Table 3, row 2: ATT = 0.143, source = scripts/run_regression.py:42, data = csmar_v2024.parquet, commit = abc123"

4. **The FinAI implementation (600 words)**
   - Every MCP fetch records: source URL, query params, response hash
   - Every transformation records: input + output + code
   - Every regression records: code, seed, sample
   - The paper manuscript includes a footer for every table/figure: source file + commit

5. **Demo: provenance-aware LaTeX (400 words)**
   - Generate LaTeX that includes \input{provenance_table3.tex}
   - This LaTeX file is generated FROM the data, not hand-typed
   - Result: if the data changes, the table changes

6. **The "doesn't lie" guarantee (200 words)**
   - No synthetic data without user consent
   - No hardcoded numbers
   - Every transformation is auditable

**Code repository**: Sample LaTeX + provenance JSON

---

## Blog 5: "How to Evaluate Whether Your AI-Generated Paper Is Actually Publishable"

**Target audience**: Researchers considering AI tools
**Goal**: A self-assessment checklist
**Format**: Checklist + scoring rubric

### Outline

1. **Hook (200 words)**: An AI-generated paper is easy. A publishable one is hard.

2. **The 12-point checklist (1500 words)**
   - **Scientific rigor (5 points)**
     1. Novel identification strategy
     2. Robust to 18 standard checks (parallel trends, placebo, alt samples, ...)
     3. Cluster-robust SEs at the right level
     4. Effect size is economically meaningful
     5. Mechanism / channel documented
   - **Data integrity (3 points)**
     6. All numbers traceable to data + code
     7. Sample is correctly defined
     8. No data leakage between pre/post
   - **Writing quality (3 points)**
     9. Introduction has 3 motivating facts + 1 specific contribution
     10. Empirical strategy is clear to a non-author
     11. Conclusion is honest about limitations
   - **Adversarial review survival (1 point)**
     12. Survives 4 rounds of referee-style review with score >4.0

3. **The scoring rubric (300 words)**
   - 12/12: Submit to JF/JFE
   - 10-11/12: Submit to RFS/JAE
   - 8-9/12: Submit to 经济研究/金融研究
   - 6-7/12: Major revisions needed
   - <6/12: Start over

4. **FinAI as a checklist automation (300 words)**
   - The 18 robustness checks → 1 command
   - The provenance audit → 1 command
   - The 4-round adversarial review → 1 command
   - The paper-quality score → 1 command
   - Putting them all together: a pre-submission gate

5. **The "would I bet my career on this?" test (200 words)**
   - If you're not willing to put your name on it, don't submit

**Code repository**: FinAI check command + sample outputs

---

## Publishing Plan

| Blog | When | Where | Length |
|------|------|-------|--------|
| Blog 1 | Week 1 | Hacker Noon + 知乎专栏 | 2500 words |
| Blog 2 | Week 2 | Medium + 公众号 | 2500 words |
| Blog 3 | Week 4 | Hacker Noon + 知乎 | 2500 words |
| Blog 4 | Week 6 | Medium + 公众号 | 2500 words |
| Blog 5 | Week 8 | Hacker Noon + 公众号 | 2500 words |

## Cross-Promotion

- Each blog links to the FinAI GitHub repo
- Each blog embeds the banner.svg and quickstart.svg
- Each blog ends with "If you want to try this: github.com/csmar432/finai-research"
- All blogs share a "FinAI Blog" tag
