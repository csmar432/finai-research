# Reddit r/MachineLearning 提交

> **目标 URL**: https://reddit.com/r/MachineLearning/submit
> **最佳时间**: 美东周二-周四 8-10 AM (北京时间 20-22 点)
> **注意**: r/MachineLearning 有严格的 self-promotion 政策，请仔细阅读

## 标题

```
[P] FinAI Research Workflow — End-to-end empirical research pipeline
(43 MCP data sources, 47 econometric methods, 30 journal templates)
```

## Flair (必选)

```
Project
```

## 内容

```
Hi r/MachineLearning,

I'd like to share an MIT-licensed project I've been building:
**FinAI Research Workflow** — an end-to-end pipeline that turns an
empirical research topic (e.g. "carbon trading and green innovation")
into a submission-ready LaTeX draft.

GitHub: https://github.com/csmar432/finai-research

## What it does

`python scripts/cli.py pipeline --topic "your topic"` runs:

1. **Idea generation** (8-12 candidates, novelty-checked against JF/
   JFE/RFS/arXiv/NBER).
2. **Literature review** via OpenAlex (400M+ papers) + ArXiv +
   Semantic Scholar MCP servers.
3. **Empirical design** (DID/IV/RDD/PSM) with 19-class automated
   robustness testing.
4. **Data acquisition** via 43 MCP servers (28 free, no API key):
   A-share via Tushare/akshare, US via yfinance, global macro via
   FRED/IMF/World Bank, papers via OpenAlex/ArXiv.
5. **Paper drafting** in 30 journal templates (JF/JFE/RFS, 经济研究,
   金融研究, 管理世界).
6. **Adversarial review** loop (GPT-4o + Claude + Gemini).

## What's relevant to ML researchers

- Modern staggered DID (Callaway-Sant'Anna, Sun-Abraham, Borusyak)
  — proper handling of heterogeneous treatment effects in
  observational panel data.
- Causal ML: Doubly-Robust Learners, Causal Forests, Meta-Learners
  integrated alongside traditional econometrics.
- All MCP servers are stdlib HTTP + local DB — no proprietary SDK
  lock-in. You can audit every byte.

## What it is NOT

- Not a "do my research" tool. Every regression result and citation
  must be verified by the human researcher before submission.
  HITL gates enforce checkpoints but don't eliminate responsibility.
- Not a chat interface. It's a deterministic pipeline with explicit
  provenance tracking.

## Why I'm posting here

This is a project I built because I couldn't find anything that
combined econometric rigor with LaTeX templating and modern MCP
data plumbing. I'd value feedback from anyone working on causal
inference, time-series, or applied ML. PRs welcome.

Tech: Python 3.10+, FastAPI, linearmodels, diff-in-diff2, matplotlib.
License: MIT. No telemetry. No SaaS.

4 upstream awesome-list PRs submitted as of posting:
- https://github.com/matteocourthoud/awesome-causal-inference/pull/14
- https://github.com/wilsonfreitas/awesome-quant/pull/468
- https://github.com/academic/awesome-datascience/pull/654
- https://github.com/emptymalei/awesome-research/pull/111

Happy to answer technical questions.
```

## 提交步骤

1. 打开 https://reddit.com/r/MachineLearning/submit
2. 登录 (用你常用账号即可)
3. Title: 复制上面的标题
4. 选择 Flair: **Project**
5. URL or Text: 选择 "Text" 模式 (不是 link)
6. Body: 复制上面的内容
7. 点击 Submit

## r/MachineLearning 自宣传规则

- ⚠️ 标题前缀 `[P]` 必加 (Project)
- ⚠️ 必须是 Project (不是 Link)
- ⚠️ 必须包含自述 (不是只丢链接)
- ⚠️ 至少 10 个 subreddit karma 推荐先发 (避免被 auto-spam filter 拦)
- ✅ 严禁短时间连发 (30 天内只能发 1 个项目贴)

## 提交后预期

- 前 2-4 小时: 0-50 upvotes, 排名 r/MachineLearning/new
- 8-12 小时: 如果 > 100 upvotes, 升至 hot 段
- 24 小时: 如果 > 500 upvotes, 升至 /r/all (首页)

## 自动监测

r/MachineLearning 帖子的 URL 格式:
```
https://reddit.com/r/MachineLearning/comments/XXXXXX/...
```

提交后填到 README.md 顶部 "提交状态" 段。
