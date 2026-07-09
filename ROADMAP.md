# FinAI Research Workflow — Roadmap

> Last updated: 2026-07-09
> Status: v0.2.0-alpha

This document outlines the development roadmap for FinAI Research Workflow.
星标（Star）和社区反馈会优先影响 roadmap 优先级。

---

## Vision

**FinAI** — an AI-powered research workflow for economics and finance — reduces the time from research idea to submission-ready manuscript by 15-20x while maintaining journal-standard rigor.

**Target users**: Academic researchers, graduate students, and quantitative analysts in economics, finance, and related fields.

---

## Release Horizons

### 🚀 v0.3.0 — "First Release" (Target: 2026-Q3)
*Focus: visibility and first-time user experience*

- [ ] **First GitHub Release** (v0.3.0-alpha) with CHANGELOG
- [ ] GitHub Discussions enabled and community categories configured
- [ ] README restructured: ≤300 lines, quick-start demo GIF
- [ ] MCP server tiering (Core / Recommended / Optional)
- [ ] arXiv preprint submission (finai.pdf, English)
- [ ] Discord community server created and linked in README
- [ ] Codecov token added to CI, coverage target raised to 60%

### 📦 v0.4.0 — "Benchmark & Trust" (Target: 2026-Q4)
*Focus: credibility, reproducibility, academic adoption*

- [ ] arXiv paper revised with reviewer feedback (if any)
- [ ] Zenodo DOI updated with each release
- [ ] All econometric methods benchmarked against published results (DID/IV/RDD/SDID/IFE)
- [ ] `pytest --m smoke` integrated in CI (0-second pre-merge gate)
- [ ] Docker Compose single-command setup (`docker compose up`)
- [ ] CONTRIBUTING.md with PR template and code style guide

### 🎯 v1.0.0 — "Production Ready" (Target: 2027-H1)
*Focus: reliability, breadth, community*

- [ ] Test coverage ≥ 75% across all research framework modules
- [ ] Stata integration for IV/Panel GMM alongside Python
- [ ] Multi-language paper support (English + Chinese + Japanese)
- [ ] Automated journal template checker (latexcheck workflow)
- [ ] 5 community-contributed research direction templates
- [ ] Documentation site (MkDocs / GitHub Pages) with full API reference

### 🌟 v2.0.0 — "Ecosystem" (Target: 2027-H2)
*Focus: scale, integrations, platform lock-in removal*

- [ ] Plugin architecture: custom MCP servers as pip-installable packages
- [ ] Web dashboard: Streamlit UI for non-CLI users
- [ ] Collaborative review: multi-user review sessions
- [ ] Real-time data pipelines: webhook integration with Tushare/FRED
- [ ] R integration (tidyverse + causalinfer)
- [ ] Institutional case studies published (with permission)

---

## Ongoing / Backlog

### High Priority
| Item | Description | Ticket |
|------|-------------|--------|
| MCP tiering | Restructure 50 MCP dirs into Core/Recommended/Optional tiers | #TBD |
| Demo GIF | Replace SVG/PNG with ≤15s GIF for README | #TBD |
| Coverage +10% | Add tests for fin_charts, report_generator, robustness_runner | #TBD |
| arXiv submission | Submit finai.pdf with revised abstract and case studies | #TBD |

### Medium Priority
| Item | Description |
|------|-------------|
| Stata bridge | Auto-generate Stata .do files from REFINED_DESIGN.md |
| Jupyter notebooks | Tutorial notebooks for each research direction |
| Dataset registry | Central manifest of all supported data sources |
| Method comparison table | DID vs IV vs RDD decision tree |

### Lower Priority (Community Request)
| Item | Description |
|------|-------------|
| R plugin | R integration via `reticulate` |
| Multi-user auth | Web dashboard user management |
| Mobile companion | Query pipeline status via Telegram bot |

---

## Transparency Notes

- **MCP servers requiring institutional accounts** (CSMAR, Wind) return mock data by default. Users must explicitly enable with `MCP_MOCK_MODE=allow`.
- **Mock data policy**: All mock outputs include explicit "MOCK DATA" warnings. Do not use mock data for publication.
- **GitHub Stars** drive priority: items that attract stars get accelerated.

---

*Maintained by [csmar432](https://github.com/csmar432).  Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).*
