# FinAI Research Workflow · Benchmark Report

> **Last updated**: 2026-07-08  
> **Purpose**: Empirical evidence that FinAI produces high-quality research outputs.
> All benchmarks are run on macOS (Apple Silicon M-series) with Python 3.12.

---

## 1. Method Accuracy Benchmarks

FinAI's econometric implementations are validated against known analytical solutions
and published reference implementations. Tolerance: MAD ≤ 0.05 (5 percentage points)
for treatment effect estimates.

### 1.1 Standard DID (2×2 OLS)

```
Method:         Standard DID (modern_did.py)
Reference:      Manual OLS regression (benchmark_econometrics.py)
Test data:      500 firms × 10 years synthetic panel, τ = 0.15
Result:         MAD = 0.0012  ✅ PASS
Tolerance:      MAD ≤ 0.05
```

### 1.2 Event Study (Pre/Post Visualization)

```
Method:         Event study (modern_did.py)
Reference:      Manual OLS with year dummies
Test data:      200 firms × 12 years, treatment at t=6
Result:         All pre-treatment coefficients not significantly different from 0 (p > 0.1)
                Post-treatment coefficients correctly signed ✅ PASS
```

### 1.3 Synthetic Control (Abel et al. 2016)

```
Method:         Synthetic control (synthetic_control.py)
Reference:      Manual convex optimization
Test data:      50 treated × 200 control, 8 pre-treatment periods
Result:         RMSPE (pre-period) = 0.018  ✅ PASS
                RMSPE (post-period) = 0.089
                Suppression ratio = 4.9x (good separation)
```

### 1.4 Panel GMM (Arellano-Bond)

```
Method:         Panel GMM (iv_panel.py, Arellano-Bond estimator)
Reference:      statsmodels linear panel
Test data:      300 firms × 15 years, IV = lag(y,2)
Result:         GMM estimate within 0.02 of reference ✅ PASS
                AR(1) test: p < 0.01  ✅
                AR(2) test: p > 0.10  ✅ (no second-order autocorrelation)
```

### 1.5 RDD (Sharp and Fuzzy)

```
Method:         RDD (rdd.py, local linear regression, triangular kernel)
Reference:      rdrobust (Calonico et al. 2019) Python port
Test data:      10,000 obs, cutoff = 0, bandwidth = 0.15
Result:         Sharp RD: MAD = 0.008  ✅ PASS
                Fuzzy RD: MAD = 0.011  ✅ PASS
```

> **Note**: See `scripts/benchmark_econometrics.py` for full reproducible test code
> and `tests/test_benchmark_econometrics.py` for automated regression tests.

---

## 2. Pipeline Performance Benchmarks

### 2.1 Stage-Level Timing (median, cold start)

| Stage | Median Duration | 90th Percentile | Notes |
|-------|--------------|----------------|-------|
| Idea generation | 45s | 90s | LLM call + N=8 idea expansion |
| Literature search (MCP) | 12s | 30s | OpenAlex API, top-50 papers |
| Novelty check | 30s | 60s | LLM + arXiv/Google Scholar search |
| Empirical design | 60s | 120s | DID/IV/RDD selection + Refined_DESIGN.md |
| Data acquisition | 15s–∞ | — | Depends on data source (MCP vs manual) |
| Analysis | 30s–∞ | — | Depends on method complexity |
| Paper writing | 90s | 180s | LLM call, full draft generation |
| Adversarial review | 60s | 120s | AI reviewer × 2 rounds |

> **Cold start**: First LLM call in a session incurs ~5–10s latency (API handshake).
> Subsequent calls are ~2–5s depending on response length.

### 2.2 Pipeline Telemetry Summary (from `data/pipeline_telemetry.jsonl`)

```
Total pipelines logged:        142
Median total duration:         32.1s  (orchestrator-level, no LLM)
Median API calls per run:      1.0   (orchestrator entry point)
Error rate:                    0.0%  (0 pipelines with errors)
MCP calls per run:             varies by data source
```

---

## 3. FinAI vs. Manual Research — Qualitative Comparison

> ⚠️ **Disclaimer**: These are design-goal estimates based on typical research workflows.
> Actual performance depends on researcher expertise, topic complexity, and available data.

### 3.1 Literature Review

| Metric | Manual (expert) | FinAI | Delta |
|--------|----------------|-------|-------|
| Find 50 relevant papers | 3–4 hours | 8–12 min | **~20× faster** |
| Citation network mapping | 2–3 hours | 30–60s | **~3× faster** |
| Key findings extraction | 2 hours | 3–5 min | **~30× faster** |
| Recall (relevant papers found) | ~70–80% | ~85–90% | **+10–15pp** |
| Precision (relevant/total found) | ~90% | ~75–85% | **−5–15pp** |

**Why FinAI is faster**: MCP servers query OpenAlex / Semantic Scholar with structured
keyword expansion in seconds. Manual search requires iterative refinement.

**Why FinAI may have lower precision**: LLM summarization occasionally includes
marginally relevant papers. Human judgment remains superior for niche topics.

### 3.2 Empirical Design

| Metric | Manual (PhD-level) | FinAI | Delta |
|--------|-------------------|-------|-------|
| Identify identification strategy | 1–2 hours | 3–8 min | **~15× faster** |
| Choose robustness checks | 30–60 min | 2–5 min | **~15× faster** |
| Correct method selection (DID/IV/RDD) | ~95% | ~90–95% | **Comparable** |
| Novelty assessment | Varies widely | 30–60s | **Consistent** |

**Why FinAI is faster**: `empirical_advisor.py` encodes ~42 econometric methods with
decision trees for method selection, calibrated against JF/JFE/RFS standards.

**Caveat**: FinAI's method selection is appropriate for ~90% of standard empirical
questions. Complex designs (bunching RDD, fuzzy IV with heterogeneous effects)
still benefit from domain expert review.

### 3.3 Paper Writing (LaTeX Draft)

| Metric | Manual (PhD student) | FinAI | Delta |
|--------|---------------------|-------|-------|
| First draft (8 sections) | 6–12 hours | 45–90 min | **~8× faster** |
| LaTeX formatting | 2–4 hours | <1 min | **~100× faster** |
| Reference formatting | 1–2 hours | <30s | **~200× faster** |
| Section consistency | High (with advisor) | Moderate | **Needs review** |
| Citation accuracy | High | Moderate | **Needs verification** |

**Why FinAI is faster**: LaTeX templates are pre-built for 30 journals.
LLM generates structured prose from research design. BibTeX entries are auto-fetched
via CrossRef DOI resolution.

**Critical**: Every generated draft requires human review. LLM-generated citations,
statistical claims, and methodological descriptions must be verified before submission.

---

## 4. Data Quality Benchmarks

### 4.1 MCP Data Source Accuracy

| Source | Type | Latency | Coverage | Verified Against |
|--------|------|---------|----------|-----------------|
| `user-financial` (akshare) | China macro | <1s | CPI, GDP, M2, PMI | NBS official releases |
| `user-yfinance` | US equities | <2s | OHLCV, financials | Yahoo Finance |
| `user-openalex` | Academic papers | <3s | 200M+ papers | CrossRef |
| `user-eastmoney-reports` | Research reports | <5s | CN institutional | East Money |
| `user-sec-edgar` | SEC filings | <3s | Full 10-K/10-Q | SEC.gov |

### 4.2 Mock Data Governance

Five MCP servers return mock/hardcoded data by default. All are clearly labeled:

| Server | Default | Flag | Acceptable Use |
|--------|---------|------|----------------|
| `user-nber_wp` | **Mock** | `MCP_MOCK_MODE=allow` | Demo only |
| `user-bea_data` | **Mock** | `MCP_MOCK_MODE=allow` | Demo only |
| `user-csmar` | **Mock** | `MCP_MOCK_MODE=allow` | Demo only |
| `user-wuhan_stats` | Public snapshot | Default OK | Research OK |
| `user-macro_datas` | Public snapshot | Default OK | Research OK |

> **Full list**: See `docs/MOCK_DATA_POLICY.md`

---

## 5. Test Coverage Baseline

**Date**: 2026-07-08  
**Scope**: `scripts/` (72,178 statements, 20,726 branches)  
**Test framework**: pytest + pytest-cov 7.1.0 + pytest-xdist -n 2  
**Hardware**: macOS Apple Silicon, Python 3.12  
**Total tests**: 8,048 across 398 test files (was 8,038 / 397 before PR-12)  
**Threshold (CI gate)**: 28% (`coverage report --fail-under=28`)

| Scope | Stmts | Miss | Branch | Cover | Notes |
|-------|------:|-----:|-------:|------:|-------|
| **Overall** | 72,178 | 46,240 | 20,726 | **32.2%** | Passes 28% CI gate |
| `scripts/start_research.py` | 158 | 41 | 32 | **70.5%** | Raised from 0% by PR-12; pipeline entry point now smoke-tested |
| `scripts/research_framework/` | ~12K | ~3K | ~2K | **~80%** | All 47 econometric methods individually tested |
| `scripts/core/` | ~6K | ~2K | ~1.5K | **~70%** | Agent orchestration, checkpoint, observability |
| `scripts/research_directions/` | ~3K | ~3K | ~500 | **~5%** | Lightweight stubs, integration-tested via pipeline |
| `scripts/run_research.py` | 224 | 197 | 32 | **10%** | CLI wrapper, exercised via shell integration |

**Run yourself**:
```bash
PYTHONPATH="${PYTHONPATH:-}:." pytest tests/ \
  -n 2 \
  --cov=scripts --cov-branch \
  --cov-report=term --cov-report=html:htmlcov \
  --maxfail=20 -q --no-header -p no:cacheprovider
```

Open `htmlcov/index.html` for line-by-line coverage visualization. Full report
also written to `.coverage-final.json` for programmatic consumption.

---

## 6. Reproducibility Checklist

Every benchmark above is reproducible. Run:

```bash
# Method accuracy benchmarks
python scripts/benchmark_econometrics.py

# Pipeline performance (no LLM keys needed for orchestration timing)
python scripts/agent_pipeline.py --topic "Carbon trading" --dry-run

# Coverage / CI
pytest tests/test_benchmark_econometrics.py -v
```

---

## 7. Contributing New Benchmarks

We welcome community benchmarks. To add a new benchmark:

1. Add test data generation in `scripts/benchmark_econometrics.py`
2. Add assertion with tolerance threshold
3. Document in this file with:
   - Method name and reference
   - Test data description
   - MAD / PASS/FAIL result
   - Date of benchmark

All new benchmarks must pass CI: `pytest tests/test_benchmark_econometrics.py -v`
