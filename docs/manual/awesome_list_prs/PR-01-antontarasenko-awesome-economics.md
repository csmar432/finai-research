# PR 1: antontarasenko/awesome-economics

> **Status:** DRAFT — awaiting your review before submitting via web UI.
> **Submit URL:** https://github.com/antontarasenko/awesome-economics/pulls
> **Suggested branch name:** `add-finai-research-workflow`

## Repository

[FinAI Research Workflow](https://github.com/csmar432/finai-research) - End-to-end
empirical research pipeline (43 data sources, 47 econometric methods, 30 journal
templates). Wraps idea generation, literature review, novelty check, empirical
design, data acquisition, paper drafting, and adversarial review into a single CLI.

## PR Title

```
Add FinAI Research Workflow
```

## PR Body

Hello! I'd like to add **FinAI Research Workflow** under the research-tools section.

It is an MIT-licensed pipeline that turns an empirical economics topic into a
submission-ready LaTeX draft. Key features that may be useful for economists:

- 43 data-source directories (A-share via Tushare/akshare, US via yfinance,
  global macro via FRED/IMF/World Bank, 400M+ papers via OpenAlex/ArXiv;
  28 free, no API key required).
- 47 econometric method modules including modern staggered DID
  (Callaway-Sant'Anna, Sun-Abraham, Borusyak), synthetic control, IV/2SLS,
  panel GMM, RDD, triple-diff, spatial regression.
- 30 journal templates (JF, JFE, RFS, Econometrica, 经济研究, 金融研究,
  管理世界, 会计研究, 中国工业经济).
- Human-in-the-loop gates at every pipeline stage to prevent LLM hallucination
  in the final submission draft.

**Entry placement** (per `contributing.md` — title-cased, period-terminated):

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research) - End-to-end empirical research pipeline (43 data sources, 47 econometric methods, 30 journal templates) for economists.
```

I will add it to the bottom of the most relevant existing category
(research tools / libraries).

**Compliance with contributing guidelines:**

- [x] Project is active (commits within last 30 days).
- [x] Repository is more than 1 month old.
- [x] MIT license.
- [x] Title-cased link text.
- [x] Single project per PR.
- [x] Description ends with period.
- [x] One-line entry format.

**Note on AI use:** Every regression result and citation produced by the tool
must be verified by the human researcher before submission. The tool enforces
this via HITL gates, but does not eliminate the responsibility.

Thanks for curating this list!
