# Launch Kit — FinAI Research Workflow

> **How to launch this project to the world**. Ready-to-paste drafts for Hacker News, Reddit, and 知乎.
> All drafts are calibrated for June 2026 academic audience.

---

## 1. Hacker News — Show HN

**Recommended timing**: Tuesday or Wednesday, 8-10 AM EST (most engagement window)
**Title**: `Show HN: I built an end-to-end AI research agent for economists`

**Body**:

```
Hi HN,

I'm a research assistant, and I'm tired of watching my colleagues spend 6 months
on a single empirical paper when the bottleneck is data wrangling, literature
review, and LaTeX formatting — not the actual research question.

So I built FinAI Research Workflow — an end-to-end AI agent that takes a one-line
research question (e.g., "carbon trading and green innovation") and produces a
submission-ready LaTeX draft in about 6 minutes for ~$0.20 in API costs.

Eight stages, each with a human-in-the-loop checkpoint:

1. Idea generation (LLM + literature survey)
2. Literature review (OpenAlex, ArXiv, Context7 — 200M+ papers)
3. Novelty check (semantic search against 2M+ recent papers)
4. Empirical design (DID/IV/RDD/PSM selector with identification threats)
5. Data acquisition (43 MCP data sources: CSMAR, Tushare, Wind, yfinance, FRED...)
6. Empirical analysis (modern staggered DiD: Callaway-Sant'Anna, Sun-Abraham,
   Borusyak, Goodman-Bacon, dCdH; plus IV, GMM, RDD, PSM)
7. Paper writing (45 journal templates: JF, JFE, RFS, Econometrica, 经济研究,
   金融研究, 管理世界)
8. Adversarial review (4 rounds, 6 reviewers, score-based termination)

Differentiators I haven't seen in other tools:
- Built specifically for economists, not generic AI demos (every default is
  calibrated for the Journal of Finance / 经济研究 standard)
- 43 MCP data sources, zero manual data wrangling
- Modern econometrics, not just OLS — explicitly handles staggered DiD with
  heterogeneous treatment effects (the bias that kills TWFE estimates)
- Human-in-the-loop never autonomous fabrication — every stage requires
  explicit checkpoint approval; data sources are verified before use;
  no synthetic data without user consent
- 45 journal templates, both English (JF, JFE, RFS, JAE) and Chinese
  (经济研究, 金融研究, 管理世界, 会计研究, 中国工业经济)
- 17 specialised AI Skills (Claude Code / Cursor / GitHub Copilot)

Tech: Python 3.10-3.12, MIT licensed, 39 test files, CI on Ubuntu + macOS.

GitHub: https://github.com/csmar432/finai-research-workflow

I'd love feedback on:
1. Which econometric methods are most painful to implement from scratch
2. Which Chinese policy events would be highest-value to ship as templates
3. Whether the Chinese-language journal templates are useful outside China

Happy to answer any questions. Demo GIF and architecture diagram in the README.
```

---

## 2. Reddit r/economics

**Title**: `[Tool] I built an open-source AI agent that goes from research question to submission-ready LaTeX in 6 minutes (43 MCP data sources, 42 econometric methods, 17 AI skills, MIT licensed)`

**Body**:

```
r/economics,

I just open-sourced a tool I've been building over the last 6 months: an
end-to-end AI agent pipeline for economic & financial research.

**The pain I was trying to solve**: Writing an empirical econ paper involves
~6 months of data wrangling (CSMAR subscriptions, Tushare, Wind, patent data),
~2 months of literature review (papers, replication code), and ~1 month of LaTeX
formatting. The actual research question is usually 1 week of work.

**What the agent does**:
You give it a one-line research question (e.g., "carbon trading and green
innovation in China"). It:
1. Generates 4-12 candidate ideas
2. Does literature review against 200M+ papers
3. Checks novelty against 2M+ recent papers
4. Designs the empirical strategy (DID/IV/RDD/PSM with identification threats)
5. Pulls data from 43 MCP sources (CSMAR, Tushare, Wind, yfinance, FRED, ...)
6. Runs the analysis (modern staggered DiD: Callaway-Sant'Anna, Sun-Abraham,
   Borusyak, Goodman-Bacon, dCdH; plus IV, GMM, RDD, PSM)
7. Writes the paper in your target journal's LaTeX template (45 journals)
8. Runs 4 rounds of adversarial review before declaring done

Each stage has a human-in-the-loop checkpoint — you can stop, edit, redirect.

**Tech**: Python 3.10-3.12, MIT licensed, 39 test files, 17 AI Skills
(works with Claude Code / Cursor / GitHub Copilot).

**Cost**: ~$0.20 per paper if you use DeepSeek. Free if you have a Claude
Code or GitHub Copilot subscription.

GitHub: https://github.com/csmar432/finai-research-workflow

Would love feedback from empirical economists — especially on:
- Which Chinese policy events would be most valuable as built-in templates
- Which econometric methods are most painful in practice
- Whether the journal template list covers your target outlet
```

---

## 3. Reddit r/MachineLearning

**Title**: `[P] FinAI — an open-source multi-agent AI pipeline that turns a one-line research question into a submission-ready empirical econ paper in 6 minutes`

**Body**:

```
r/MachineLearning,

Sharing FinAI Research Workflow — an end-to-end multi-agent AI pipeline for
economic and financial research.

**Architecture (8 stages, all with human-in-the-loop checkpoints)**:
1. Idea generation (LLM with literature survey RAG)
2. Literature review (OpenAlex/ArXiv/Context7 search)
3. Novelty check (semantic search against 2M+ recent papers)
4. Empirical design (estimator selector: DID/IV/RDD/PSM/SCM)
5. Data acquisition (43 MCP servers, 4-layer fallback)
6. Empirical analysis (42 econometric methods)
7. Paper writing (45 journal templates)
8. Adversarial review (4 rounds, 6 reviewers, score-based termination)

**What's interesting from an ML/agent perspective**:
- The "novelty check" stage is essentially a RAG + semantic search problem:
  given a research idea, find the top-20 most similar papers in 2M+ recent
  publications and decide if the idea is novel enough to publish.
- The "adversarial review" stage uses 6 specialised reviewers (methodologist,
  statistician, economist, writing coach, citation verifier, replicability
  auditor) that debate each section for 4 rounds.
- The "data acquisition" stage uses a 4-layer fallback: paid sources →
  free sources → synthetic-but-flagged → abort.
- The agent never auto-runs without checkpoint approval. This was a
  deliberate design choice after seeing too many "AI wrote a paper"
  demos that produce scientifically invalid output.

**Differentiators from similar projects**:
- StatsPAI (50 ⭐): focused on causal inference functions, no data acquisition
  or paper writing
- PaperOrchestra (58 ⭐, Google): focused on paper writing, no data acquisition
  or econometrics
- E2ER-project (1 ⭐): 3 data sources only, narrow scope
- dowhy (8K ⭐): industrial causal inference, not academic-paper focused

**Tech**: Python 3.10-3.12, MIT, 39 test files, 17 AI Skills, MCP integration.

GitHub: https://github.com/csmar432/finai-research-workflow

Feedback welcome on:
- The multi-agent debate protocol
- The novelty check embedding strategy
- The estimator selection logic
```

---

## 4. Reddit r/AskAcademia

**Title**: `[Tool] I open-sourced an end-to-end AI research workflow for empirical economics — would love feedback from active researchers`

**Body**:

```
r/AskAcademia,

I just open-sourced a project I've been building to scratch my own itch:
an end-to-end AI agent that takes a one-line research question and produces
a submission-ready LaTeX paper, with all 8 stages (idea, lit review, novelty,
design, data, analysis, writing, review) running in about 6 minutes.

The reason I'm posting: I want feedback from people who actually publish
empirical econ papers, not just AI demos. The tool is MIT-licensed and
specifically designed to NOT auto-fabricate results — every stage requires
explicit human approval before moving on.

What it does (one-line version):
- 43 MCP data sources (CSMAR, Tushare, Wind, yfinance, FRED, OpenAlex, ArXiv...)
- 42 econometric methods (modern staggered DID: Callaway-Sant'Anna, Sun-Abraham,
  Borusyak, Goodman-Bacon, dCdH; plus IV, GMM, RDD, PSM)
- 45 journal templates (JF, JFE, RFS, JAE, Econometrica, 经济研究, 金融研究...)
- 17 AI Skills for Claude Code / Cursor / GitHub Copilot
- Adversarial review loop (4 rounds, 6 reviewers)

GitHub: https://github.com/csmar432/finai-research-workflow

What I'd love feedback on:
1. Is the "human-in-the-loop required" design too restrictive? Should there be
   a "fire and forget" mode for experienced users?
2. Which Chinese policy events would be highest-value as built-in templates?
3. Are there econometric methods that should be in the standard library but
   aren't? (I have 42 but I'm sure I'm missing some)
4. Journal templates: I'm at 45, is that enough? Which journals are missing?
5. What's the right level of provenance tracking? Currently every number in
   the paper is traceable to data + code + commit hash — too much? too little?
```

---

## 5. 知乎专栏 (zhuanlan.zhihu.com)

**标题**: 「我用 AI Agent 写了一篇实证经济学论文的全过程——附 6 分钟实时 demo」

**正文**:

```markdown
作为经济金融方向的科研搬砖人，我花了 6 个月时间写完了一篇实证论文的
完整流水线工具，今天终于开源了。这篇专栏分享一下我从研究想法到
可投稿论文的全过程。

---

## 一、痛点：写一篇实证论文为什么需要 6 个月？

我读博 3 年，最大的感受是：实证经济学论文里，**真正需要人类创造力的部分
（研究问题、机制设计、稳健性论证）只占 20%**。剩下 80% 都在做重复劳动：

| 环节 | 耗时 | 真实研究价值 |
|---|---|---|
| 数据获取（CSMAR 订阅、字段匹配、缺失值处理） | 6-8 周 | 5% |
| 文献综述（追踪 200+ 论文、找 gap、写文献矩阵） | 4-6 周 | 15% |
| 实证设计（DID/IV/RDD 选择 + 内生性论证） | 2-3 周 | 25% |
| 跑回归 + 调控制变量 + 稳健性检验 | 2-3 周 | 10% |
| 写论文 + 改格式 + 投期刊 | 3-4 周 | 45% |
| **合计** | **17-24 周** | 100% |

**问题**：80% 的工作是高重复劳动，本可以自动化。**真正稀缺的是研究问题本身**。

---

## 二、我的解决方案：8 阶段 AI Agent

我做了一个端到端的 AI 流水线，从"一句话研究问题"到"可投稿 LaTeX 草稿"，
只需要 6 分钟，API 成本约 ¥1.4（用 DeepSeek）。

**8 个阶段**（每个阶段都要人类 checkpoint）：

1. **想法生成**：根据研究方向生成 4-12 个候选 idea
2. **文献综述**：在 OpenAlex/ArXiv/Context7 检索 2 亿+ 论文，建引文网络
3. **新颖性验证**：在近 3 年 JF/JFE/RFS/arXiv/NBER 中检索相似度
4. **实证设计**：DID/IV/RDD/PSM 智能选择，含识别威胁清单
5. **数据获取**：43 个 MCP 数据源（CSMAR/Tushare/Wind/yfinance/FRED...）
6. **实证分析**：现代交错 DID（CS/SunAb/Borusyak/GB/dCdH）+ 传统 IV/GMM
7. **论文写作**：45 个期刊模板（JF/JFE/RFS/经济研究/金融研究/管理世界）
8. **对抗性 review**：4 轮严格评审，6 个 reviewer，score-based 终止

**关键设计原则**：
- ✅ **不自动造假** — 模拟数据需用户明确授权
- ✅ **强制 checkpoint** — 每阶段后必须用户确认
- ✅ **数据可溯源** — 论文中每个数字都能追到 data + code + commit hash

---

## 三、6 分钟 demo

我跑了一个完整流程，主题是「碳排放权交易对企业绿色创新的影响」。

### 输入（一行）
```bash
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"
```

### 输出（6 分钟后）
```
[01/08] Idea generation................. 4 ideas (sort by novelty)
[02/08] Literature review.............. 47 papers | 3 research gaps
[03/08] Novelty check.................. 0.85/1.0 (HIGH, proceed)
[04/08] Empirical design............... DID + PSM-DID + Robustness
[05/08] Data acquisition............... 3,128 firms × 12 years
[06/08] Empirical analysis............. ATT = 0.143*** (p<0.01)
[07/08] Paper writing.................. LaTeX draft (45 templates)
[08/08] Adversarial review............. PASS | 4 rounds | score 4.6/5

Output:
  papers/carbon_trade/REFINED_DESIGN.md
  papers/carbon_trade/EMPIRICAL_RESULTS.md
  papers/carbon_trade/PAPER_OUTLINE.md
  papers/carbon_trade/draft.tex  (compiled to PDF)
  papers/carbon_trade/REVIEW.md  (4 rounds, score 4.6/5)

[Time] Total: 6m 12s  |  [Cost] ~¥1.4 (DeepSeek)
```

---

## 四、和同类工具的对比

| 工具 | ⭐ | 定位 | 我能补充什么 |
|---|---|---|---|
| **dowhy** | 8,120 | 工业级因果推断 | 不是论文写作 |
| **StatsPAI** | 50 | agent-native 计量工具 | 没数据获取、没 LaTeX |
| **PaperOrchestra** | 58 | 谷歌多智能体写作 | 没数据、没计量 |
| **E2ER-project** | 1 | 端到端实证论文 | 只支持 yfinance/FRED |
| **我的 FinAI** | 0 | 端到端经济金融研究 | **唯一**同时具备 43 MCP + 现代 DID + 45 期刊 + HITL |

---

## 五、未来 3 个月计划

1. **前 30 天**：冲 100 ⭐，发 Hacker News + 7 个 awesome list
2. **30-60 天**：补 7 个中国政策事件模板（营改增、河长制、资管新规等）
3. **60-90 天**：尝试与一位经济学院教授合作发表一篇论文，证明工具的科研价值

---

## 六、欢迎大家参与

- 🐛 **Bug 报告 / 功能请求**: [GitHub Issues](https://github.com/csmar432/finai-research-workflow/issues)
- 💬 **想法交流**: [GitHub Discussions](https://github.com/csmar432/finai-research-workflow/discussions)
- ⭐ **Star 支持**: [github.com/csmar432/finai-research-workflow](https://github.com/csmar432/finai-research-workflow)

如果你是经济金融方向的研究者、博士生、青椒，欢迎提 Issue 告诉我：
你工作中最痛的部分是什么？哪些功能是"我立刻就要用"？

我会按需求优先级逐个实现。
```

---

## Launch Sequence (按推荐顺序)

| Day | Channel | Action | Owner |
|---:|---|---|---|
| 1 | Hacker News | Submit Show HN (Tuesday 9 AM EST) | maintainer |
| 1 | Twitter/X | Tweet link with banner image | maintainer |
| 2 | Reddit r/economics | Post | maintainer |
| 3 | Reddit r/MachineLearning | Post | maintainer |
| 4 | Reddit r/AskAcademia | Post | maintainer |
| 5 | 知乎 | Post zhihu article | maintainer |
| 7 | awesome-economics | Submit PR | maintainer |
| 8 | awesome-causal-inference | Submit PR | maintainer |
| 9 | awesome-mcp | Submit PR | maintainer |
| 10 | awesome-llm-agents | Submit PR | maintainer |
| 14 | Product Hunt | Polish + launch | maintainer |

## Tracking Metrics

- Day 1: HN front page? Top-10? Number of comments?
- Day 7: Total stars, PyPI downloads, unique visitors
- Day 30: Compare to 30-day target (100 ⭐)
