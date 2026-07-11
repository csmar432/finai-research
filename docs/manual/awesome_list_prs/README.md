# Awesome-list PR Campaign — Summary

> **Status:** 5 PR drafts ready for review + 2 documented non-submissions.
> **Methodology:** every entry verified against the target list's actual
> CONTRIBUTING.md (downloaded and parsed before drafting).

## Background

The original `MANUAL_TASKS.md` (任务 6) listed 7 awesome-list PR targets,
but **5 of the 7 URLs were 404 Not Found** at the time of writing.
Real-world replacements were searched via GitHub API + WebSearch.

| # | Original (MANUAL_TASKS.md) | Status | Real replacement |
|---|----------------------------|--------|------------------|
| 1 | OpenSourceEcon/awesome-economics | ❌ 404 | antontarasenko/awesome-economics (655⭐) |
| 2 | ijustcb/awesome-causal-inference | ❌ 404 | matteocourthoud/awesome-causal-inference (1178⭐) |
| 3 | wgamboa/awesome-finance | ❌ 404 | wilsonfreitas/awesome-quant (3k⭐) |
| 4 | kevinmcguinness/awesome-mcp-servers | ❌ 404 | **wong2** (4193⭐) does NOT accept PRs |
| 5 | MacJerome/awesome-data-science | ❌ 404 | academic/awesome-datascience (29.5k⭐) |
| 6 | vinta/awesome-python | ✅ real | But project not on PyPI → auto-rejected |
| 7 | emptymalei/awesome-research | ✅ real | OK to submit |

## PR Campaign — Final Plan

| # | Draft file | Submit URL | Status |
|---|------------|------------|--------|
| 1 | [PR-01](./PR-01-antontarasenko-awesome-economics.md) | https://github.com/antontarasenko/awesome-economics/pulls | ✅ READY |
| 2 | [PR-02](./PR-02-matteocourthoud-awesome-causal-inference.md) | https://github.com/matteocourthoud/awesome-causal-inference/pulls | ✅ READY |
| 3 | [PR-03](./PR-03-wilsonfreitas-awesome-quant.md) | https://github.com/wilsonfreitas/awesome-quant/pulls | ✅ READY |
| 4 | [PR-04](./PR-04-academic-awesome-datascience.md) | https://github.com/academic/awesome-datascience/pulls | ✅ READY |
| 5 | [PR-05](./PR-05-emptymalei-awesome-research.md) | https://github.com/emptymalei/awesome-research/pulls | ✅ READY |
| 6 | [PR-06](./PR-06-WITHDRAWN-wong2-awesome-mcp-servers.md) | (none — wong2 README explicitly says no PRs) | ⚠️ WITHDRAWN |
| 7 | [PR-07](./PR-07-DEFERRED-vinta-awesome-python.md) | (deferred — needs PyPI + 100 stars) | ⏸️ DEFERRED |

## Sending Order (1 per day)

Per `MANUAL_TASKS.md` ordering priority and acceptance likelihood:

1. **PR-02 matteocourthoud** — highest acceptance likelihood (DID/IV/RDD users most relevant, multi-sub-file list with active maintainer).
2. **PR-03 wilsonfreitas** — strict format compliance, exact spec-following entry.
3. **PR-01 antontarasenko** — standard format, low bar.
4. **PR-05 emptymalei** — minimal format, low effort to accept.
5. **PR-04 academic** — large list, 29.5k stars, may take longer to review.

## Submitting the PRs

These drafts need **manual web UI submission** by the maintainer
(@csmar432) because:

1. Each PR requires GitHub OAuth authentication from your account.
2. AI agents cannot bypass GitHub's CAPTCHA / 2FA.
3. Each maintainer may request follow-up edits — you should be the one
   responding.

**To submit a PR:**

1. Read the corresponding `PR-XX-*.md` file.
2. Open the Submit URL in your browser.
3. Click "New pull request" → "compare across forks" → select the
   suggested branch name.
4. Copy the PR title and body from the draft into GitHub's web form.
5. Submit.

**Expected time per PR:** 5-10 minutes (after drafting).

## Quality Bar Applied

For every PR:

- ✅ Description is one sentence, ends with a period (per most lists' format).
- ✅ Title-cased link text (per antontarasenko's guideline).
- ✅ Language tag in backticks (per wilsonfreitas's guideline).
- ✅ Entry format follows the specific list's existing entries.
- ✅ License disclosed (MIT).
- ✅ Activity confirmed (commits within last 30 days).
- ✅ AI disclaimer included (per the project's HITL policy).
- ✅ No marketing language ("amazing", "revolutionary", etc.).
- ✅ No comparison against other projects in the list (avoids looking
  like self-promotion).
- ✅ One project per PR (per most lists' strict rule).

## Verification

- `ruff`: not applicable (markdown only).
- `pytest`: not applicable.
- Manual review by maintainer: ⏳ **required**.
