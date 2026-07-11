# X.com (Twitter) 推文

> **目标 URL**: https://x.com/compose/post
> **最佳时间**: 美东周二-周四 9 AM ET 或 3 PM ET

---

## A. 主推文（thread 形式，5 条推）

### 推 1 / 5 (Hook)

```
We just open-sourced FinAI Research Workflow — a single-CLI pipeline
that turns an empirical research topic into a submission-ready LaTeX
draft.

43 MCP data sources · 47 econometric methods · 30 journal templates
(JF/JFE/RFS, 经济研究/金融研究/管理世界)

github.com/csmar432/finai-research
```

### 推 2 / 5 (Problem)

```
The current empirical research workflow requires 5-7 tools:

Tushare/yfinance → Stata/R → BibTeX → Overleaf → AI assistants

Every handoff has a cost. Every step has a human-in-the-loop friction.

We tried to compress it into one CLI command:
`python scripts/cli.py pipeline --topic X`
```

### 推 3 / 5 (Solution)

```
8-stage pipeline:

1. Idea generation (8-12 candidates, novelty-checked against
   JF/JFE/RFS/arXiv)
2. Literature review (OpenAlex 400M+ papers + ArXiv + SS)
3. Empirical design (DID/IV/RDD/PSM with 19-class automated
   robustness)
4. Data acquisition (43 MCP servers, 28 free, no API key)
5. Paper drafting (30 journal templates)
6. Adversarial review (GPT-4o + Claude + Gemini)
```

### 推 4 / 5 (Differentiator)

```
What makes this different from generic "AI paper writer":

→ HITL gates at every stage. The next stage refuses to run until a
  human signs off the previous one.
→ Provenance tracking. Every chart and table has a JSON sidecar
  pointing to the raw API call that produced the number.
→ MIT licensed. No telemetry. No SaaS.

Empirical economics is small enough that an in-house tool is more
cost-effective than SaaS. The workflow IS the value.
```

### 推 5 / 5 (Call to action + disclaimer)

```
4 upstream awesome-list PRs already submitted (3 auto-accepted by
bot, awaiting maintainer review):

→ matteocourthoud/awesome-causal-inference#14
→ wilsonfreitas/awesome-quant#468
→ academic/awesome-datascience#654
→ emptymalei/awesome-research#111

⚠️ Every AI-generated regression result and citation MUST be verified
by the human researcher before submission. The tool enforces HITL
gates but does not eliminate the responsibility.

github.com/csmar432/finai-research

Feedback welcome!
```

---

## B. 单推（短版本）

如果你只想发一条：

```
Open-sourced FinAI Research Workflow today.

Single CLI to turn an empirical research topic into a submission-ready
LaTeX draft.

→ 43 MCP data sources (28 free, no API key)
→ 47 econometric methods (modern staggered DID included)
→ 30 journal templates (JF/JFE/RFS, 经济研究/金融研究/管理世界)
→ HITL gates at every stage (no LLM fabrication reaches the draft)

github.com/csmar432/finai-research
```

---

## 配图建议

X.com 每条推最多 4 张图。建议：

1. **architecture-diagram.svg** (项目 .github/demo/ 下)
2. **demo.gif** (项目 .github/demo/ 下) — 终端实际录制
3. **PR screenshot** — GitHub PR 列表截图

---

## 提交步骤

1. 打开 https://x.com/compose/post
2. 登录账号
3. 输入推文 1/5
4. 点击 "+" 添加下一条推（thread 模式）
5. 继续输入推文 2/5, 3/5, 4/5, 5/5
6. **可选**: 添加 1-4 张图
7. 点击 "Post all" (一次性发布整个 thread)

---

## 标签建议

每条推文末尾添加 2-3 个 hashtag：
```
#OpenSource #Econometrics #Python #MCP
#ResearchTools #AcademicTwitter #EconTwitter
#FinanceResearch
```

---

## 转推策略

发布后：
1. 自己立刻 quote tweet（"为什么我们做这个"）— 增加 visibility
2. @几位计量经济学 KOL：
   - @matteocourthoud (causal inference 列表维护者)
   - @WilsonFreitas (awesome-quant 维护者)
   - @academic_awesome (datascience 列表)
3. **避免 spam** — 不要每小时发一次，**一天 ≤ 2 条 thread**

---

## 提交后监测

推文 URL 格式：
```
https://x.com/<user_handle>/status/<tweet_id>
```

提交后填 README.md "提交状态" 段。

---

## 自动监测工具（可选）

如果你想追踪 hashtag 反馈：
- Tweetdeck (X.com 自带)
- 第三方: Buffer / Hootsuite (免费 tier 足够)

我们的项目 README 提到了：
- `scripts/update_related_stars.py` — 自动更新 GitHub stars
- 不需要 X.com 监控脚本 (除非特别需要)
