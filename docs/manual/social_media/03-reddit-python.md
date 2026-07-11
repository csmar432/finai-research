# Reddit r/Python 提交

> **目标 URL**: https://reddit.com/r/Python/submit
> **最佳时间**: 美东周二-周四 8-10 AM (北京时间 20-22 点)

## 标题

```
FinAI Research Workflow — End-to-end empirical research pipeline
(43 MCP data sources, 47 econometric methods, 30 journal templates)
```

## Flair

```
Show & Tell
```

## 内容

```
Hi r/Python,

I'd like to share a Python project that might be useful for anyone
doing empirical research: **FinAI Research Workflow** — a single-CLI
pipeline from research topic to submission-ready LaTeX draft.

GitHub: https://github.com/csmar432/finai-research
PyPI: coming soon (PR-07 pending)

## The Python ecosystem this project touches

- **MCP (Model Context Protocol) servers** in stdlib HTTP — 43 of
  them, 28 work without an API key.
- **Causal inference**: statsmodels, linearmodels, diff-in-diff2,
  PyWhy (DoWhy/EconML).
- **Data acquisition**: yfinance (US equities), akshare (A-share),
  wbdata, imfp, fredapi, sec-edgar-downloader.
- **Literature**: openalex, arxiv, semanticscholar.
- **Visualization**: matplotlib, seaborn, plotly.
- **LaTeX**: 30 journal templates via custom Jinja-like templating.

## What I find useful about the architecture

1. **HITL gates**: every pipeline stage writes a checkpoint file;
   the next stage refuses to run until a human signs off. No
   autonomous LLM fabrication reaches the final draft.

2. **Provenance tracking**: every chart and table in the generated
   paper has a JSON sidecar pointing to the raw API call that
   produced the underlying number. If a reviewer asks "where does
   this coefficient come from?", you can answer in one command.

3. **Deterministic + reproducible**: `python scripts/cli.py
   pipeline --topic X --seed 42` produces the same draft (modulo
   LLM temperature). This is rare in AI-assisted research tools.

## What I'd love feedback on

- Whether the MCP integration makes sense to anyone else
  (this is the project's first major release).
- Whether the LaTeX template approach (custom .tex.j2-ish templating)
  is reasonable or if I should use Quarto instead.
- Whether the 19-class robustness runner is overkill or just right
  (Chinese top journals want at least 14; I'm aiming for 19).

## Caveat

⚠️ Every AI-generated regression result and citation MUST be
verified by the human researcher before submission. The tool
enforces HITL gates but does not eliminate the responsibility.

## Tech

Python 3.10+, FastAPI for orchestrator, pytest (399 test files,
7824 test functions), ruff for linting, GitHub Actions for CI.
OpenSSF Scorecard gold tier. MIT licensed.

4 upstream PRs:
- matteocourthoud/awesome-causal-inference#14
- wilsonfreitas/awesome-quant#468
- academic/awesome-datascience#654
- emptymalei/awesome-research#111

Happy to take questions or PRs.
```

## 提交步骤

1. 打开 https://reddit.com/r/Python/submit
2. 登录
3. Title: 复制上面的标题
4. 选择 Flair: **Show & Tell**
5. 选 "Text" 模式
6. Body: 复制上面的内容
7. 点击 Submit

## r/Python 规则

- ✅ 标题加 "Show & Tell" 或类似的 flair
- ✅ 重点放在 Python 技术细节上 (不是功能介绍)
- ❌ 严禁 self-promotion 嫌疑 (避免 "I made this" 开头过强)
- ❌ 30 天内只允许 1 个项目贴
- ✅ 高质量代码 + README + 测试是基本要求 (我们都有)

## r/Python 自宣传规则详细

> 来自 r/Python FAQ：
> "If a large percentage of your posts are linking to your own
> content, you may be considered a spammer."

如果你的账号历史中大部分 post 都是项目，建议先在 r/Python
评论其他人的帖子 1-2 周建立 karma，再发自己的项目。

提交后填 README.md "提交状态" 段。
