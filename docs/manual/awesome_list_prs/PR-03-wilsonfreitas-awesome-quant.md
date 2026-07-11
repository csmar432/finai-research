# PR 3: wilsonfreitas/awesome-quant

> **Status:** DRAFT — awaiting your review before submitting via web UI.
> **Submit URL:** https://github.com/wilsonfreitas/awesome-quant/pulls
> **Suggested branch name:** `add-finai-research-workflow`
> **Target section:** `## Quant Research Environments` (most fitting category)
> **Source `CONTRIBUTING.md`:** https://github.com/wilsonfreitas/awesome-quant/blob/main/CONTRIBUTING.md

## PR Title

```
Add FinAI Research Workflow
```

## PR Body

I'd like to add **FinAI Research Workflow** under the **Quant Research
Environments** section (the closest fit per the category list in CONTRIBUTING.md).

## Project

[FinAI Research Workflow](https://github.com/csmar432/finai-research) - `Python` -
End-to-end empirical-research workflow for economists: 43 data sources
(A-share, US, global macro, 400M+ papers), 47 econometric methods
(DID + modern staggered variants, IV, panel GMM, synthetic control,
triple-diff, spatial), 30 journal templates, and HITL gates preventing
LLM fabrication in submission-ready LaTeX drafts.

## Proposed Entry

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research) - `Python` - End-to-end empirical-research workflow (43 data sources, 47 econometric methods, 30 journal templates) with HITL gates.
```

## Why This Fits "Quant Research Environments"

While dowhy and causalml focus on individual CI algorithms, FinAI is positioned
at the **workflow** layer: idea → literature → novelty check → design → data →
analysis → paper → review. It bundles econometrics, data acquisition, and LaTeX
templating into a single CLI. This complements (rather than competes with)
the libraries already in the Quant Research Environments section.

## Compliance Checklist (per CONTRIBUTING.md)

- [x] Entry uses GitHub repo URL (`https://github.com/csmar432/finai-research`).
- [x] Language tag in backticks (`` `Python` ``).
- [x] Description ends with a period.
- [x] One sentence, concise.
- [x] One project per PR.
- [x] Project active (commits within last 30 days — see
      https://github.com/csmar432/finai-research/commits/main).
- [x] Documented (README + CLAUDE.md + per-skill SKILL.md).
- [x] MIT license (https://github.com/csmar432/finai-research/blob/main/LICENSE).
- [x] No archived status.

## Quality Note

FinAI is not on PyPI yet (alpha-stage MIT project), but per CONTRIBUTING.md
the "GitHub repository URLs are strongly preferred" rule applies and we use
the canonical GitHub URL. If you require PyPI publication as a precondition,
I'm happy to push a beta release after we discuss — for now the source install
(`pip install -e ".[dev]"`) is the supported path.

## Disclaimer (also in our README)

All AI-generated regression results and citations must be verified by the
human researcher before submission. The tool enforces HITL gates but does
not eliminate this responsibility.

Thanks for curating — `awesome-quant` is one of the most-cited lists in the
field and I'm glad to have a chance to contribute.
