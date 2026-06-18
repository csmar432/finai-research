# Awesome List Submission Templates

> **How to submit FinAI Research Workflow to 7 awesome lists**.
> Each section contains:
> - 仓库地址 (where to PR)
> - 文件路径 (which file to edit)
> - 草稿条目 (ready-to-paste)
> - PR 标题/正文 模板

---

## 1. awesome-economics

- **Repo**: https://github.com/antonalley/awesome-economics
- **File**: `README.md` (look for "Software" or "Tools" section)
- **Add to**: Software → Empirical Methods / Data Analysis

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent pipeline for economic & financial research (lit review → empirical design → DID/IV/RDD → paper writing). 43 MCP data sources, 42 econometric methods, 17 AI skills. MIT.
```

**PR Title**:
```
Add FinAI Research Workflow to Software section
```

**PR Body**:
```
Adds FinAI Research Workflow, an end-to-end AI agent pipeline for
empirical economic research. It uniquely combines literature review,
modern econometrics (Callaway-Sant'Anna, Borusyak, Sun-Abraham, etc.),
data acquisition from 43 sources, and paper writing for 45 journal
templates (English + Chinese) in a single MIT-licensed package.

This adds value to the awesome-economics list because it lowers the
barrier for empirical research automation, especially for Chinese
economists who use CSMAR/Tushare/Wind and target Chinese top journals
(经济研究, 金融研究, 管理世界).
```

---

## 2. awesome-causal-inference

- **Repo**: https://github.com/mauricio-zuber/awesome-causal-inference
- **File**: `README.md` (Software section)
- **Add to**: Software → Python → Research

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent for empirical research with modern causal inference (Callaway-Sant'Anna, Sun-Abraham, Borusyak, Goodman-Bacon, dCdH, Synthetic DiD, IV, GMM, RDD, PSM).
```

**PR Title**:
```
Add FinAI Research Workflow
```

**PR Body**:
```
Adds FinAI Research Workflow to the Python software section.

This project is specifically focused on modern causal inference for
applied economics — the modern staggered DiD estimators (Callaway-Sant'Anna,
Sun-Abraham, Borusyak, Goodman-Bacon, de Chaisemartin-d'Haultfoeuille) are
all first-class citizens. It also includes the full econometric pipeline
(data acquisition → analysis → paper writing) that few other tools cover.

Differentiation from existing entries:
- dowhy (already listed): industrial causal inference, not academic
- EconML (already listed): ML-based heterogeneous treatment effects
- moderndid (could be listed): GPU-accelerated modern DiD
- FinAI: end-to-end research pipeline, not just a library
```

---

## 3. awesome-mcp

- **Repo**: https://github.com/kevinwu06/awesome-mcp
- **File**: `README.md` (Servers section, or "By Use Case" → Research)
- **Add to**: "Servers for Research" or "Servers for Data"

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - 43 MCP servers for economic/financial research: Tushare (A-share), CSMAR, Wind, yfinance, FRED, OpenAlex (200M papers), ArXiv, Context7 (paper fulltext), and 35+ more.
```

**PR Title**:
```
Add FinAI Research Workflow (43 MCP servers for economic research)
```

**PR Body**:
```
Adds FinAI Research Workflow, which ships 43 MCP servers for
economic/financial research data:

- Tushare, CSMAR, Wind, CNRDS (Chinese A-share data)
- yfinance, SEC EDGAR, FRED, BEA, World Bank, IMF, OECD (US/global)
- OpenAlex, ArXiv, Semantic Scholar, Context7, NBER (200M+ academic papers)
- Brave Search, News API (research discovery)
- And 25+ more...

Each server is a standalone MCP server you can use independently,
or compose via the FinAI pipeline.
```

---

## 4. awesome-llm-agents

- **Repo**: https://github.com/kaushik-bhat/awesome-llm-agents
- **File**: `README.md` (Frameworks or Research Applications section)

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - Multi-agent pipeline for economic research: 8 specialised agents (idea, lit review, novelty, design, data, analysis, writing, adversarial review) with human-in-the-loop checkpoints. 17 Skills, 43 MCP data sources.
```

**PR Title**:
```
Add FinAI Research Workflow (multi-agent economic research pipeline)
```

**PR Body**:
```
Adds FinAI Research Workflow to research-applications section.

It's a multi-agent pipeline for empirical economic research with:
- 8 specialised agents (one per pipeline stage)
- 4 human-in-the-loop checkpoints (mandatory, no auto-fabrication)
- Adversarial review loop (4 rounds, 6 reviewers, score-based termination)
- 17 AI Skills for Claude Code / Cursor / GitHub Copilot
- Provenance tracking (every number → data + code + commit hash)

A good example of "constrained, principled" multi-agent design where
agents are specialists with explicit handoffs, not general-purpose
autonomous loops.
```

---

## 5. awesome-academic-writing

- **Repo**: https://github.com/snwau/awesome-academic-writing
- **File**: `README.md` (Tools / Software section)

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - AI-assisted academic paper writing for economists. 45 journal templates (English: JF/JFE/RFS/JAE/Econometrica; Chinese: 经济研究/金融研究/管理世界/会计研究/中国工业经济). LaTeX compilation, BibTeX management, citation verification, multi-round adversarial review.
```

**PR Title**:
```
Add FinAI Research Workflow (45 journal templates, EN+CN)
```

**PR Body**:
```
Adds FinAI Research Workflow to the tools section.

Unique value: it ships 45 journal templates covering both English
top journals (JF, JFE, RFS, JAE, Econometrica) and Chinese top
journals (经济研究, 金融研究, 管理世界, 会计研究, 中国工业经济).
This is a gap I noticed — most academic-writing tools focus on
English-only or specific conference formats (NeurIPS, ACL, IEEE).

The Chinese journal templates are particularly rare in open source
and would benefit Chinese economics/finance PhD students significantly.
```

---

## 6. awesome-stata

- **Repo**: https://github.com/wfg/awesome-stata
- **File**: `README.md` (Programming → Python section, or "Related Tools" section)

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - Python equivalent of a complete Stata workflow for empirical economics. Modern DiD (CS/SunAb/Borusyak/GB/dCdH), IV, GMM, RDD, PSM. Outputs publication-ready LaTeX. Use when you want a Python-based end-to-end pipeline.
```

**PR Title**:
```
Add FinAI Research Workflow (Python equivalent of complete Stata workflow)
```

**PR Body**:
```
Adds FinAI Research Workflow to the "related / Python equivalents" section.

For Stata users who want to migrate to Python or want a unified pipeline
that goes beyond Stata, this project provides:
- Modern staggered DiD (Callaway-Sant'Anna, Sun-Abraham, Borusyak, etc.)
  — the same estimators as `csdid`, `eventstudyinteract`, did_imputation
- IV/GMM (Arellano-Bond, Blundell-Bond)
- RDD (local polynomial, fuzzy)
- PSM-DID (full pipeline)
- Plus 35+ more methods

Plus the surrounding workflow (data acquisition, paper writing, review)
that Stata doesn't provide.
```

---

## 7. awesome-python (Science / Academic subsection)

- **Repo**: https://github.com/vinta/awesome-python
- **File**: `README.md` (Science section)

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent for economic & financial research. 43 MCP data sources, 42 econometric methods, 17 AI skills, 45 journal templates (EN+CN). MIT.
```

**PR Title**:
```
Add FinAI Research Workflow to Science section
```

**PR Body**:
```
Adds FinAI Research Workflow to the Science subsection.

This is a Python-native end-to-end research pipeline that:
- Integrates 43 MCP data sources (CSMAR, Tushare, Wind, yfinance, FRED...)
- Implements 42 econometric methods (modern DiD, IV, GMM, RDD, PSM)
- Outputs to 45 journal LaTeX templates
- Has 17 AI Skills for Claude Code / Cursor / GitHub Copilot

It fits well in the Science section alongside:
- [statsmodels](https://github.com/statsmodels/statsmodels) — already listed
- [linearmodels](https://github.com/bashtage/linearmodels) — already listed
- [causaldata](https://github.com/NickCH-K/causaldata) — already listed

But uniquely combines all four capabilities (data + econometrics +
LaTeX + Skills) in a single project.
```

---

## General PR Strategy

### Tone
- Be **respectful** and **brief**. Maintainers are busy.
- Show you actually use awesome lists and read the contribution guide.
- Make a single-line addition unless the maintainer asks for more.

### Pre-PR Checklist
- [ ] Read the awesome list's `CONTRIBUTING.md` (most have one)
- [ ] Search the existing list to confirm you're not duplicating
- [ ] Check alphabetical ordering (if required)
- [ ] Use the EXACT format pattern from existing entries
- [ ] Keep description to 1-2 sentences
- [ ] Don't include emojis unless the list uses them

### PR Title Convention
- `Add [Tool Name]` (most common)
- `Add [Tool Name] to [Section] section`
- `Adding [Tool Name] to [section]`

### Common Pitfalls
- ❌ Marketing copy / excessive enthusiasm
- ❌ Multiple tools in one PR
- ❌ Editing other entries
- ❌ Not checking the contribution guide
- ✅ Brief, professional, follows house style
