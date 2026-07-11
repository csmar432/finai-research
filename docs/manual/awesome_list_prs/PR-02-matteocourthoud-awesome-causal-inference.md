# PR 2: matteocourthoud/awesome-causal-inference

> **Status:** DRAFT — awaiting your review before submitting via web UI.
> **Submit URL:** https://github.com/matteocourthoud/awesome-causal-inference/pulls
> **Suggested branch name:** `add-finai-research-workflow`
> **Target file:** `src/libraries.md` (Python section)
> **Note:** This list has no CONTRIBUTING.md; we follow the existing format in `src/libraries.md`.

## PR Title

```
Add FinAI Research Workflow (Python library for empirical economic CI workflows)
```

## PR Body

Thanks for maintaining this comprehensive list — it's been a reference for
my own econometrics work for years.

I'd like to add **FinAI Research Workflow** to the **Python → Libraries**
section of `src/libraries.md`. It is **complementary** to the algorithm-layer
libraries already listed (DoWhy, EconML, CausalML, causal-learn, CausalPy):
FinAI wraps modern staggered DID (Callaway-Sant'Anna, Sun-Abraham, Borusyak),
synthetic control, IV/2SLS, panel GMM, triple-diff, panel quantile, spatial
regression, and 19-class robustness testing into a research-workflow layer that
also handles data acquisition and submission-ready LaTeX.

**Proposed insertion** at the bottom of `## 🐍 Python`:

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research)
  ![stars](https://img.shields.io/github/stars/csmar432/finai-research)
  - [didi](https://github.com/csmar432/finai-research) - Modern staggered DID (Callaway-Sant'Anna, Sun-Abraham, Borusyak)
  - [synth](https://github.com/csmar432/finai-research) - Synthetic control and synthetic DiD
  - [iv](https://github.com/csmar432/finai-research) - IV / 2SLS for panel and cross-section
  - [gmm](https://github.com/csmar432/finai-research) - Panel GMM (Arellano-Bond, Blundell-Bond)
  - [rdd](https://github.com/csmar432/finai-research) - Sharp / fuzzy regression discontinuity
  - [triple](https://github.com/csmar432/finai-research) - Triple-difference (DDD)
  - [panelquantile](https://github.com/csmar432/finai-research) - Panel fixed-effects quantile regression
  - [spatial](https://github.com/csmar432/finai-research) - Spatial regression (SAR/SEM/SDM)
  - [robustness](https://github.com/csmar432/finai-research) - 19-class automated robustness testing
```

The tool's distinguishing focus is **end-to-end workflow** (literature review
→ empirical design → data → paper) rather than new CI algorithms, so it is
positioned at the bottom of the Python list with the other workflow tools.

**Compliance:**

- [x] Python-first project.
- [x] Active (commits within last 30 days).
- [x] Documented (README + CLAUDE.md + 17 SKILL.md files).
- [x] MIT license.
- [x] Follows the existing badge + sub-entry format used in `libraries.md`.
- [x] Single project per PR.

**Caveat for users:** all AI-generated regression results and citations must
be verified by the human researcher before submission. The tool enforces
HITL gates but does not eliminate this responsibility.

Happy to move the placement or reformat if you prefer a different style.
