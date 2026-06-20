# FinAI Research Workflow — 30/60/90 Day Star-Growth Roadmap

> **Mission**: take FinAI Research Workflow from 0 to **500+ GitHub stars** in 90 days by making it the *de facto* end-to-end AI research pipeline for economic and financial researchers in both English and Chinese academic communities.

---

## 0. Competitive Position (June 2026)

| Project | Stars | Focus | Gap We Fill |
|---|---:|---|---|
| **dowhy** | 8,120 | Generic causal inference (industrial) | Not academic-paper focused |
| **moderndid** | Growing | GPU-accelerated DiD (library) | Not end-to-end pipeline |
| **StatsPAI** | 50 | Agent-native econometrics toolkit | No literature review, no LaTeX |
| **PaperOrchestra** | 58 | Google's multi-agent paper writing | No econometrics, no data acquisition |
| **superRA** | 1 | Plan-implement-integrate workflow | Lacks data layer |
| **E2ER-project** | 1 | End-to-end empirical papers | Narrow scope (yfinance/FRED only) |
| **econ-paper-studio** | 0 | CLI orchestration layer | No actual data fetching |
| **AutoRegMonkey** | 0 | RAG on Hansen textbook | Knowledge-only, no real research |
| **claude-research-workflow** | 1 | Behavioral economics template | Sub-domain, niche |
| **ZeroPaper** | 0 | 30 agents, JFQA quality | Closed license, no real release |

**Our unique position**: the *only* open-source project that combines **(1) 43 MCP data sources** + **(2) modern econometrics (CS-DiD, dCdH, etc.)** + **(3) 45 journal templates including 6 Chinese top journals** + **(4) human-in-the-loop checkpoints with provenance** in a single, MIT-licensed, end-to-end pipeline.

---

## 1. 30-Day Sprint: "Demoable Polish" (target: 50-100 stars)

### Week 1 — Asset Creation

- [x] **Generate architecture banner** — `docs/assets/banner.svg` (done)
- [x] **Generate 60-second demo screenshot** — `docs/assets/quickstart.svg` (done)
- [x] **Generate 3 social-preview images** (1280×640, 1280×320, 800×800) with the project tagline — `docs/assets/social-preview-*.{png,svg}` (done)
- [ ] **Record real 6-minute terminal demo GIF** — use `asciinema` on a real run
  - Command: `asciinema rec -c "python scripts/agent_pipeline.py --topic '绿色金融与企业创新'" demo.cast`
  - Convert: `asciinema upload demo.cast` → embed GIF in README

### Week 2 — README Conversion Optimisation

- [x] **Top of README rewrite** — category claim + 60s demo + value prop (done)
- [x] **"Why FinAI" section** with 6 differentiators (done)
- [x] **"Star History" + "Cite" sections** at bottom (done)
- [x] **"Related Projects" section** — cross-link competitors (done)
- [x] **Add 3 code-architecture Mermaid diagrams**:
  - Pipeline DAG (8 stages + checkpoints)
  - MCP tool selection flow (43 sources with fallback)
  - Modern DID estimation comparison (CS / SunAb / Borusyak)
- [ ] **Add "Comparison with [competitor]" table** for StatsPAI, PaperOrchestra, E2ER

### Week 3 — Hacker News / Reddit Launch Kit

- [ ] **Write Show HN post** (650 words):
  - Title: `Show HN: I built an end-to-end AI research agent for economists`
  - Lead with the pain point (DID biases, CSMAR data wrangling, 6-month paper cycle)
  - Embed demo GIF and key architecture diagram
  - Mention: 43 MCP sources, 42 econometric methods, MIT license, active maintenance
- [ ] **Write r/economics + r/MachineLearning + r/AcademicPhilosophy + r/AskAcademia post** — same story, different angle
- [ ] **Write 中文知乎专栏文章** (2000 字):
  - 标题: "我用 AI Agent 写了一篇实证经济学论文的全过程"
  - 在 [经济金融学术圈] 话题下发布
  - 同步推送到"数量经济学"、"AI and Economics" 公众号

### Week 4 — Awesome List Seeding

- [ ] **Submit to `awesome-economics`** (PR)
- [ ] **Submit to `awesome-causal-inference`** (PR)
- [ ] **Submit to `awesome-mcp`** (PR)
- [ ] **Submit to `awesome-llm-agents`** (PR)
- [ ] **Submit to `awesome-academic-writing`** (PR)
- [ ] **Submit to `awesome-stata`** (mention Python equivalent)
- [ ] **Submit to `awesome-Python`** (under "Science" or "Academic")

### Week 4 — Issue & PR Hygiene

- [ ] **Triage all open issues** — respond within 24h, label `bug` / `enhancement` / `question` / `duplicate`
- [ ] **Add `good first issue` label** to 3-5 beginner-friendly tasks
- [ ] **Add `help wanted` label** to 3-5 medium tasks
- [ ] **Create `CONTRIBUTING.md` improvements** (current is good, but add "How to add a new MCP server" guide)
- [ ] **Enable GitHub Discussions** if not already on

### 30-Day Targets

- ⭐ 50-100 stars
- 🐛 < 3 open issues older than 7 days
- 📝 3-5 new contributors (any size)
- 🚀 1 successful Show HN post (top-10 in HN if possible)

---

## 2. 60-Day Sprint: "Differentiation & Depth" (target: 200-350 stars)

### Economic-Finance-Specific Features (the moat)

- [x] **Carbon trading policy data pack** — pre-built CSV of China ETS rollout (2013, 2017, 2021) + EU ETS phase boundaries; pre-registered event-study template — `scripts/research_framework/china_carbon_events.py` (done)
- [x] **Common Chinese policy shocks** (7 events, ready to DID) — `scripts/research_framework/china_policy_events.py`:
  - 营改增 (2012, 2016)
  - 大气十条 (2013)
  - 河长制 (2016)
  - 资管新规 (2018)
  - 科创板设立 (2019)
  - 碳达峰碳中和 (2020)
  - 数据二十条 (2022)
- [x] **A股常用控制变量模板** (FirmControls class) — pre-defined Sa-index, leverage, ROA, growth, size, age, SOE, with sane defaults — `scripts/research_framework/a_share_firm_controls.py` (done)
- [x] **PSM-DID 一键脚手架** — `scripts/research_framework/psm_did.py` (done)
- [x] **Mediation analysis** (Baron-Kenny + bootstrap + modern Sobel) — `scripts/research_framework/mediation.py` (done)
- [x] **调节效应模板** (Heckman两步法、交互项、门槛回归) — `scripts/research_framework/moderation.py` + `panel_threshold_regression.py` (done)
- [x] **空间计量 (SDM/SAR/SEM)** — `scripts/research_framework/spatial_regression.py` (done; 7 估计器, 2033 lines)

### Content Marketing (2nd wave)

- [ ] **Write 5 blog posts** (2500 字 each, in `docs/blog/`):
  1. "How to fix staggered DiD with negative weights (Callaway-Sant'Anna in 100 lines of Python)"
  2. "Why economists need their own AI agent (not just ChatGPT)"
  3. "Replicating a published A-share paper in 30 minutes with FinAI"
  4. "From CSMAR to LaTeX: a data-to-paper pipeline that doesn't lie"
  5. "How to evaluate whether your AI-generated paper is actually publishable"
- [ ] **Cross-post to**: HackerNoon, Medium, 知乎专栏, 微信公众号 (with permission)
- [ ] **Make 2 YouTube/Bilibili videos** (10 min each):
  1. "FinAI 完整 demo: 6 分钟生成可投稿论文"
  2. "如何在你的 Mac 上 5 分钟跑通 FinAI"

### Community & Integrations

- [ ] **Add `claude-code` plugin** — publish as `claude-code-finai` npm-like plugin
- [ ] **Add `cursor` extension** — publish on Cursor marketplace
- [ ] **Add GitHub Action** — `csmar432/finai-research-action` for CI paper-quality check
- [ ] **PyPI publish** — already 1.0.0, but verify install + smoke test
- [ ] **Docker image** — `docker pull csmar432/finai-research-workflow`

### 60-Day Targets

- ⭐ 200-350 stars
- 📈 500+ PyPI downloads/month
- 🇨🇳 1000+ 知乎关注 / 公众号订阅
- 🎓 3-5 replication packages in `papers/` (real published papers re-implemented)

---

## 3. 90-Day Sprint: "Authority & Moat" (target: 500+ stars)

### Academic Authority

- [ ] **Co-author with a real economist** — find a Chinese assistant professor who uses the tool to write a working paper, list them as co-author
- [ ] **Get cited in a working paper** — preprint on SSRN/RePEc with FinAI as tooling
- [ ] **Submit to JF/Econometrica software section** if applicable
- [ ] **Workshop at a Chinese university** — 上海财大、对外经贸、央财 经济学院
- [ ] **Speak at `数量经济学` or `AI and Economics` 公众号** — 30min talk
- [ ] **Publish a benchmarking paper** — "AI-Generated Empirical Papers: A Replication Study" — 20 published A-share papers replicated + assessed

### Feature Moat (Differentiators Hard to Copy)

- [ ] **Real-time novelty check against 2M+ papers** — vector search via Context7 + OpenAlex, not just keyword
- [ ] **Provenance RAG** — every number in the paper traceable to data + code + commit hash
- [ ] **Multi-agent debate reviewer** — 3 LLM agents debate (method, novelty, writing), then human arbitrates
- [ ] **Citation verifier** — every cited paper checked for factual existence, abstract match, and DOI resolution
- [ ] **Auto IRB / pre-registration** for experimental economics
- [ ] **Built-in replication package generator** — produce `replication.zip` ready for journals
- [ ] **Co-author multi-paper workflows** — write a thesis (4 papers) instead of 1 paper

### Partnerships

- [ ] **CSMAR official integration** — request academic partnership (free API tier for academic users)
- [ ] **Wind official integration** — same
- [ ] **CNKI/Wanfang official integration** — same
- [ ] **Anaconda / conda-forge** — get into `conda install -c conda-forge finai-research-workflow`
- [ ] **JetBrains marketplace** — PyCharm plugin for paper writing

### 90-Day Targets

- ⭐ 500+ stars (stretch: 1000)
- 📈 2000+ PyPI downloads/month
- 🎓 1 published paper crediting FinAI
- 🤝 1-2 official data-provider partnerships
- 🇨🇳 Recognised brand in Chinese econ research circles

---

## 4. Ongoing Tactics (apply daily/weekly)

### Daily
- Triage issues (24h response SLA)
- Review PRs
- Update CHANGELOG.md

### Weekly
- 1 short blog post OR social media post
- 1 community engagement (HN comment, 知乎回答, Reddit reply)
- 1 dependency update via Dependabot

### Monthly
- Release a minor version (1.1, 1.2, ...)
- Write 1 long-form blog post (2500+ words)
- Host 1 community call / Office Hours (Chinese timezone + US timezone)
- Update ROADMAP.md

### Quarterly
- 1 "v2.0" release with major feature
- 1 conference talk / workshop
- 1 academic paper / preprint

---

## 5. Content Calendar (first 90 days)

| Day | Channel | Content |
|---:|---|---|
| 1 | HN Show | "End-to-end AI agent for economists" |
| 3 | Reddit r/economics | "Replicating A-share paper in 30 min" |
| 5 | 知乎专栏 | "我用 AI Agent 写论文全过程" |
| 8 | 公众号 数量经济学 | Guest post on 数量经济学 |
| 10 | HN | "How we fix staggered DiD biases" |
| 15 | YouTube/Bilibili | "6-min FinAI demo" |
| 20 | HN Comment | Reply to 2-3 AI-for-research threads |
| 25 | Reddit r/MachineLearning | "Comparison: FinAI vs StatsPAI vs E2ER" |
| 30 | Medium | "Building a 43-MCP ecosystem" |
| 45 | 知乎 | "CSMAR 数据到 LaTeX 完整流水线" |
| 60 | Conference | Submit talk to PyCon China / R Conference |
| 75 | Preprint | "FinAI: An Open-Source AI Pipeline" on SSRN |
| 90 | Hacker News | "Lessons learned scaling to 500 stars" |

---

## 6. Success Metrics Dashboard

| Metric | Day 30 | Day 60 | Day 90 |
|---|---:|---:|---:|
| GitHub stars | 100 | 350 | 500 |
| PyPI downloads/month | 200 | 800 | 2000 |
| GitHub forks | 15 | 50 | 100 |
| Unique contributors | 5 | 15 | 30 |
| Open issues < 7 days | < 3 | < 5 | < 10 |
| 知乎关注 | 300 | 1000 | 3000 |
| Published papers crediting FinAI | 0 | 0 | 1-2 |
| Unique MCP data fetches/day | 50 | 200 | 500 |

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Competitor launches similar tool | Med | High | Move fast on Chinese-specific features; build community moat |
| GitHub account suspension (personal vs org) | Low | Critical | Migrate to GitHub Organization; add 2-3 maintainers |
| API cost for users (DeepSeek, OpenAI) | Med | Med | Default to DeepSeek (cheapest); document free alternatives |
| Chinese data license issues (CSMAR/Wind) | Med | High | Document legal use cases; partner officially |
| Bad-faith star attacks (suspected) | Med | Med | Don't buy stars; organic growth only |
| "AI-generated paper" backlash | Med | Med | Position as "AI-assisted" not "AI-generated"; require human verification |

---

## 8. Anti-Patterns to Avoid

- ❌ Don't buy stars / fake engagement
- ❌ Don't add `awesome-` or `star-this-` features
- ❌ Don't spam every HN thread with FinAI mentions
- ❌ Don't claim false citations / replication
- ❌ Don't ship features without tests / docs
- ❌ Don't use corporate / paid social to promote (looks fake)
- ❌ Don't break public APIs (deprecation → 2 minor versions notice)

---

*Last updated: 2026-06-20 · Maintained by [@csmar432](https://github.com/csmar432)*
*Recent maintenance: v8-v16 (PRs #40-#49). CI green. All Issues #42/#22 closed.*
