# FinAI Research Workflow

> End-to-end AI agent pipeline for economic and financial academic research — from research idea to submission-ready paper. Integrates MCP data acquisition, causal inference (DID/IV/PSM/GMM), LaTeX typesetting, and adversarial review loops.

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://pypi.org/project/finai-research-workflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/finai-research-workflow?color=blue)](https://pypi.org/project/finai-research-workflow/)
[![PyPI downloads](https://img.shields.io/pypi/dm/finai-research-workflow?color=blue)](https://pypi.org/project/finai-research-workflow/)
[![arXiv](https://img.shields.io/badge/arXiv-cs.AI-b31b1b.svg)](https://arxiv.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/csmar432/finai-research-workflow/ci.yml?branch=main&label=CI)](https://github.com/csmar432/finai-research-workflow/actions)
[![docs](https://img.shields.io/github/actions/workflow/status/csmar432/finai-research-workflow/docs.yml?branch=main&label=docs)](https://github.com/csmar432/finai-research-workflow/actions)
[![codecov](https://codecov.io/gh/csmar432/finai-research-workflow/branch/main/graph/badge.svg)](https://codecov.io/gh/csmar432/finai-research-workflow)
<!-- Zenodo DOI badge: 真实发布到 Zenodo 后替换占位符。 -->
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.PENDING.svg)](https://doi.org/10.5281/zenodo.PENDING)
[![GitHub stars](https://img.shields.io/github/stars/csmar432/finai-research-workflow?style=social)](https://github.com/csmar432/finai-research-workflow/stargazers)

[🇨🇳 **中文文档**](README.md) · [🇬🇧 **English Documentation**](#)

---

## 🚀 One-Liner Pitch

> **"Tell me your research topic, I'll help you: from literature review → idea generation → empirical design → paper draft → LaTeX compilation — fully automated."**

## 📌 Quick Navigation

| I'm looking for... | Go here |
|---|---|
| **One-line publish script** | `python scripts/release.py` |
| **API reference** | [scripts/](scripts/) modules with type hints and docstrings |
| **Architecture overview** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **18 AI skills** | [knowledge/skills/](knowledge/skills/) |
| **Architecture overview** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **Troubleshooting FAQ** | [FAQ.md](FAQ.md) |
| **Chinese comprehensive guide** | [使用指南.md](使用指南.md) (1049 lines, 13 chapters) |

---

## 👥 Who Is This For?

| Audience | Use Case |
|----------|----------|
| **PhD students / researchers** | Design empirical studies, run econometric analysis, generate LaTeX manuscripts for JF/JFE/RFS/经济研究/金融研究 |
| **Finance professors** | Automate literature reviews, track policy experiments, benchmark against published papers |
| **Graduate students** | Learn econometric methods (DID/IV/RDD) with automated validation and robustness checks |
| **Quantitative analysts** | Access A-share data, run factor analysis, generate institutional-grade research reports |
| **AI/ML researchers** | Explore LLM applications in financial research automation, provenance tracking, HITL design |

> **Not sure?** If you've ever spent days downloading data, running regressions, formatting LaTeX tables, or searching for related work — this tool is for you.

---

## ✨ Core Capabilities

### 📊 Data Acquisition (43 MCP Servers, mostly no API key required)

| What you need | MCP server |
|---|---|
| A-share quote/financial/margin | `user-tushare` (need TUSHARE_TOKEN) |
| China macro (GDP/CPI/M2) | `user-financial` (free) |
| Federal Reserve / FOMC | `user-fed-data` (free) |
| World Bank macro | `user-wb-data` (free) |
| IMF data | `user-imf-data` (free) |
| OECD data | `user-oecd-data` (free) |
| US Treasury yield / economic calendar | `user-eodhd` (need key) |
| US stocks / ESG | `user-yfinance` (free) |
| Research reports / news | `user-eastmoney-reports` (free) |
| Forex / shipping / commodities | `user-enhanced-finance` (free) |
| Academic papers | `user-arxiv`, `user-nber-wp`, `user-semantic-scholar` |
| Chinese literature | `user-brave-search` |

> **4-layer fallback** for every data request: `MCP → Python lib → HTTP → synthetic (explicitly marked)`

### 🧮 Econometric Methods (~30 independent algorithms, JF/JFE/RFS standard)

> **Note**: Numbers below count independent estimators. Some methods depend on `linearmodels` or `diff-in-diff2` (marked 🔗); ⭐ denotes self-contained Python implementations.

- **⭐ Standard DID + Event Study** (2): 2x2 OLS, cluster-robust SE (HC0/HC1/CR0/CR1/CGM)
- **⭐ Bacon Decomposition** (1): Goodman-Bacon (2021) weight diagnostic
- **🔗 Staggered DID** (4): Callaway-Sant'Anna (QJE 2021), Sun-Abraham (REStud 2021), Borusyak (REStud 2024), dCdH — requires `pip install diff-in-diff2`
- **🔗 Synthetic Control** (2): Abadie (JASA 2016), Arkhangelsky (Science 2021)
- **🔗 IV / 2SLS** (2): panel IV, Jackknife IV — requires `linearmodels`
- **🔗 Panel GMM** (2): Arellano-Bond, Blundell-Bord — requires `linearmodels`
- **⭐ Other** (~20): RDD, triple-diff, panel quantile, interactive fixed effects, local projections, spatial regression, Causal Forest, TVP-VAR, sensitivity analysis (Wild Bootstrap, Leamer bounds)


### 📄 Paper Writing (52 journal templates, English/Chinese/Japanese/German)

- **English top**: JF · JFE · RFS · JAE · JFQA · JPE · Econometrica
- **Chinese top**: 经济研究 · 金融研究 · 管理世界 · 会计研究 · 中国工业经济
- LaTeX compilation · Figures ≥300 DPI · BibTeX · PRISMA compliance

### 🤖 18 AI Skills (Claude Code / Cursor / Copilot)

- **Discovery**: `fin-idea-discovery` · `fin-generate-idea` · `fin-novelty-check` · `fin-lit-review`
- **Design**: `fin-experiment-design` · `fin-data-acquisition`
- **Writing**: `fin-paper-plan` · `fin-paper-draft` · `fin-paper-figure` · `fin-paper-writing` · `fin-paper-convert`
- **Review**: `fin-review-loop` · `fin-submit-check` · `fin-ref-paper` · `fin-brief-generator` · `fin-viz-launch`

### 🏗 Engineering Quality

- ✅ 86 test files, 7 CI jobs, 2-OS matrix (Ubuntu + macOS)
- ✅ Coverage report, codecov badge
- ✅ Pre-commit hooks (ruff + mypy + codespell + commitlint)
- ✅ Dependabot (pip + GitHub Actions)
- ✅ Sigstore-signed releases
- ✅ Security: SECURITY.md, bandit, 48h ack SLA
- ✅ Sandbox: AST validation, halt rules
- ✅ Full data provenance tracking

---

## 🚀 Quick Start

```bash
# 1. Install
git clone https://github.com/csmar432/finai-research-workflow.git
cd finai-research-workflow
pip install -e ".[dev]"

# 2. Configure API keys
cp .env.example .env
# At minimum, fill DEEPSEEK_API_KEY

# 3. Health check
python scripts/health_check.py

# 4. Run a research pipeline
python scripts/agent_pipeline.py --topic "Carbon trading policy and corporate green innovation"

# 5. Browse examples
ls examples/
python examples/01-quickstart-pipeline.py
```

---

## 🏛 Research Pipeline (8 steps)

```
Step 0  Health check        → scripts/health_check.py
Step 1  Research ideas      → 8-12 candidate ideas, ranked
Step 2  Idea ↔ Data verify  → scripts/idea_data_checker.py (HITL checkpoint)
Step 3  Literature review   → MCP multi-source, citation network, gap analysis
Step 4  Novelty check       → JF/JFE/RFS/arXiv search
Step 5  Empirical design    → DID/IV/RD/PSM/18 robustness checks
Step 6  Data acquisition    → 43 MCP servers, 4-layer fallback
Step 7  Paper writing       → outline → draft → figures → LaTeX
Step 8  Adversarial review  → multi-round, until publishable
```

Each step is **independently callable** and **has its own output file** as a state carrier.

---

## 🏆 Highlights

| Metric | Value | Note |
|---|-------|------|
| MCP data servers | **43** | 43 real servers; see MCP docs for coverage |
| Econometric methods | **~30** | ⭐ self-contained, 🔗 requires linearmodels/diff-in-diff2 |
| Journal templates | **52** | 49 EN/ZH + 3 JP/DE |
| AI skills | **17** | .cursor/skills/ (operational source) |
| Test files | **86** | pytest collect: 2,136 tests |
| Python lines | **~200K** | |
| CI jobs | **7** | 3 batches + lint + 2 smoke + docs + coverage |
| Coverage | **~7%** | gate commented pending improvement |

> ⚠️ Coverage gate (60%) is commented out in pyproject.toml — current total coverage is ~7%.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions must:
1. Pass `ruff check scripts/`
2. Pass `pytest tests/`
3. Use [Conventional Commits](https://www.conventionalcommits.org/) format: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
4. Link an issue

We use PR labeler (`.github/labeler.yml`) for automatic labels.

---

## 📜 License

[MIT License](LICENSE) — Copyright (c) 2026 FinAI Research Workflow Contributors

---

## 🔗 Links

- **PyPI**: https://pypi.org/project/finai-research-workflow/
- **Issues**: https://github.com/csmar432/finai-research-workflow/issues
- **Discussions**: https://github.com/csmar432/finai-research-workflow/discussions
- **Security**: See [SECURITY.md](SECURITY.md)
- **Cite this work**: See [CITATION.cff](CITATION.cff)
- **Full Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **Releases**: [releases/](releases/)

---

## 👤 Maintainer

This project is maintained by **[@csmar432](https://github.com/csmar432)**.

- 🐛 **Bug reports & feature requests**: [GitHub Issues](https://github.com/csmar432/finai-research-workflow/issues)
- 💬 **Questions & ideas**: [GitHub Discussions](https://github.com/csmar432/finai-research-workflow/discussions)
- 🔒 **Security disclosures**: [GitHub Security Advisories](https://github.com/csmar432/finai-research-workflow/security/advisories/new)
- 💖 **Sponsor / support**: [GitHub Sponsors](https://github.com/sponsors/csmar432) · [爱发电](https://afdian.net/a/finresearch)

> Contributions of all sizes are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

---

## 🙏 Acknowledgments

- **JF / JFE / RFS** for econometric methodology standards
- **OpenAlex / ArXiv / Semantic Scholar** for academic data
- **MCP (Model Context Protocol)** for the tool integration standard
- **Cursor / Claude Code / GitHub Copilot** for the AI coding platform

---

<p align="center">
  <sub>Built with ❤️ by the open-source financial AI community · MIT License · 2026</sub>
</p>
