# HN Show HN 提交

> **目标 URL**: https://news.ycombinator.com/submit
> **最佳时间**: 美东周二-周四 8-10 AM (北京时间 20-22 点)

## 标题

```
Show HN: FinAI Research Workflow – An open-source AI pipeline for empirical econ
```

## URL (Submit 字段)

```
https://github.com/csmar432/finai-research
```

## 内容（提交时填入文本框）

```
Hi HN,

I'm an economist who got tired of juggling 7 tools per paper (Tushare for
data, Stata for regressions, BibTeX for citations, Overleaf for LaTeX, plus
3 AI assistants for lit review), so I built a single CLI that takes a
research topic and produces a submission-ready LaTeX draft.

The pipeline (one command: `python scripts/agent_pipeline.py --topic X`)
runs:

1. Idea generation – 8-12 ranked candidates, novelty-checked against
   JF/JFE/RFS/arXiv.
2. Literature review – OpenAlex/ArXiv/Semantic Scholar MCP integration
   with citation graphs.
3. Empirical design – DID/IV/RDD/PSM with 19-class automated robustness
   (cluster-robust SE, Bacon decomposition, event study, parallel trends).
4. Data acquisition – 43 MCP data sources (28 work with no API key;
   yfinance for US, akshare for China macro, OpenAlex for papers).
5. Paper drafting – 30 journal templates (JF/JFE/RFS/JPE/Econometrica in
   English; 经济研究/金融研究/管理世界 in Chinese).
6. Adversarial review – 3-layer LLM review loop (GPT-4o + Claude + Gemini).

Tech stack (for the HN crowd):
- 58 econometric methods, not just OLS. Modern staggered DID
  (Callaway-Sant'Anna, Sun-Abraham, Borusyak, Goodman-Bacon) all
  included. Full list: python scripts/count_assets.py.
- All MCP servers are stdlib HTTP + local SQLite — no proprietary vendor
  SDK lock-in.
- Provenance tracking on every data fetch (see scripts/core/provenance.py).
- 18 Skills for Codex / Cursor / Claude Code / GitHub Copilot.

Important caveat (also in the README):
⚠️ Every AI-generated regression result and citation MUST be verified by
the human researcher before submission. The tool enforces HITL gates
between stages but does not eliminate academic responsibility. Empirical
economics publications have desk-reject standards; "AI wrote it" is not a
valid defense.

Stack: Python 3.10+, FastAPI for the orchestrator, optional maintained
econometrics backends, and matplotlib for charts (300 DPI PDF). No SaaS,
no telemetry, no phone-home. MIT licensed.

Happy to answer technical questions about MCP integration, causal
inference implementations, or LaTeX template customization.

GitHub: https://github.com/csmar432/finai-research
PyPI: https://pypi.org/project/finai-research-workflow/
DOI: 10.5281/zenodo.21262689
```

## 提交步骤

1. 打开 https://news.ycombinator.com/submit
2. 登录你的 HN 账号 (注册: https://news.ycombinator.com/login)
3. Title: 复制上面的标题
4. URL: 复制 GitHub 链接
5. Text: 复制上面的内容
6. 点击 Submit
7. **等待审核** — HN 编辑 (dang) 会决定是否上首页。通常 5-15 分钟。

## 提交后监控

- 投票排行: https://news.ycombinator.com/item?id=XXXXX (提交后获得)
- **如果前 2 小时 > 50 upvotes**: 可能会被推上首页 front page
- **如果 24 小时 < 10 upvotes**: 帖子会沉下去，不需要补充评论

## 注意事项

- **不要**在其他时间发"补充信息" — HN 编辑讨厌 "bumping"
- **如果被批评**，礼貌回答，不对抗 (HN 文化)
- **避免链接到 landing page** — 直接链接到 GitHub repo
- **不要**用 marketing 词汇 ("revolutionary", "amazing")

## 自动检测已发链接

提交后，把 HN item ID 填到 `docs/manual/social_media/README.md` 顶部 "提交状态" 段，方便追踪。
