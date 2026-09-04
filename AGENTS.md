# AGENTS.md — Codex / Copilot / Claude Code entry point

> **Purpose**: This is the canonical agent entry point for tools that
> read `AGENTS.md` (OpenAI Codex, GitHub Copilot, Claude Code, Lovable, etc.).
> It is equivalent to `CLAUDE.md` (Claude Code legacy) and
> `.cursor/rules/system-init.mdc` (Cursor IDE).
>
> **Size budget**: keep under 32 KiB (Codex's `project_doc_max_bytes`).
> Defer deep reference to other files.

---

## Project: 论文-研报工作流 · FinResearch Agent

**One-liner:** Describe your research topic → receive submission-ready LaTeX draft.

A finance & economics AI research workflow that automates the 8-stage research
pipeline (idea → lit review → novelty → design → data → analysis → draft → review)
with 43 MCP data sources, 58 econometric method modules, 30 journal templates, and
18 AI skills.

**Repo:** https://github.com/csmar432/finai-research
**License:** MIT

---

## Quick Start (3 commands)

```bash
# 1. Install (one of:)
pip install -e ".[extras]"           # from source (recommended)
pip install 'finai-research-workflow[extras]'  # from PyPI

# 2. Configure LLM (DeepSeek is free for Chinese use)
cp .env.example .env.local
# Edit .env.local: set DEEPSEEK_API_KEY=sk-...

# 3. Run (pick one path)
# 3a. Clarify first (recommended for new topics; does not auto-run writing)
python scripts/start_research.py --topic "Carbon trading and green innovation"
# optional: python scripts/start_research.py --topic "..." --continue --use-hitl

# 3b. Direct writing pipeline
python scripts/agent_pipeline.py --topic "Carbon trading and green innovation" --use-hitl

# 3c. Agent-host / isolation slot (non-interactive, no Mock, fail-closed)
#    Writes output/SKIPPED_CONFIG.md + output/FINAL.md when blocked (e.g. no LLM).
#    Do NOT invent a parallel pipeline outside FinAI when this exits non-zero.
python scripts/agent_host_entry.py --topic "Carbon trading and green innovation"
# or: place TOPIC.md in cwd, then: python scripts/agent_host_entry.py
```

---

## Agent-host / isolation protocol

When a host agent is told **not to ask**, **not to wait**, and **not to use Mock**:

1. Prefer `python scripts/agent_host_entry.py` (reads `TOPIC.md` if `--topic` omitted).
2. If the run is blocked (no LLM, missing topic, preflight refuse), **stop** after
   `output/SKIPPED_CONFIG.md` + `output/FINAL.md` are written. Exit `4` = LLM/config block; `2` = bad/missing topic.
3. **Do not** freestyle a second research stack, fabricate citations/coefficients, or silently enable Mock.
4. Empirical work (DID/IV/data fetch) remains a **separate hand-off** from the writing pipeline; see dual-track notes in `docs/ARCHITECTURE.md`.
5. Batch HITL off: default for `agent_host_entry`; or `FINAI_NO_HITL=1` / `--no-use-hitl` on other CLIs.
6. **Local empirics first**: set `FINAI_EMPIRICAL_DATA_ROOT` (e.g. `/data/实证分析`).
   Universal + CachedDataFetcher Layer 0 read this root before MCP/CLI. Skipping local
   panels and substituting city patents / overseas revenue / interest coverage for
   firm green patents / customs HS / bond spreads is **proxy laundering** — forbidden.
7. **Deepen inside FinAI, don't fork outside**: if results are thin, use
   `python -m scripts.research_framework.enhanced_pipeline --topic "..." --explore
   [--panel path]` (multi-estimator + comprehensive robustness). Freestyle
   `run_real_*.py` that bypasses FinAI APIs / local root is the anti-pattern.
8. **TOPIC integrity**: `agent_host_entry` records hard-gaps in `SKIPPED_CONFIG.md`.
   Writing may continue as `status=partial` with non-claims; use `--block-on-topic-gaps`
   to refuse the whole run. Causal PDF delivery is not "completed" while gaps remain.
9. **Delivery contract**: required artifacts are `FINAL.md` + `SKIPPED_CONFIG.md`
   (`CODEX_FINAL.md` alone is insufficient). Optional: `--check-delivery` → `DELIVERY.md`.
10. Interactive Cursor chats still greet / HITL per `.cursor/rules/system-init.mdc`;
    isolation autopilot overrides that via `FINAI_AUTOPILOT=1` + `agent_host_entry` only.

---

## 8-Stage Pipeline

```
Stage 0: Health Check        → python scripts/health_check.py
Stage 1: Idea Generation     → IDE handles via prompt
Stage 2: Literature Review   → scripts/literature_download.py
Stage 3: Novelty Check       → scripts/agent_pipeline.py --novelty-check
                               (NoveltyGate: SS/OpenAlex search + Jaccard; LLM only if search down)
Stage 4: Empirical Design    → scaffold: pipeline.py --mode design
                               real design: fin-experiment-design / REFINED_DESIGN.md
Stage 5: Data Acquisition    → scripts/universal_data_fetcher.py
Stage 6: Analysis            → python -m scripts.research_framework.enhanced_pipeline
                               or import scripts.research_framework.modern_did
                               step2b runs the gold slots (structure facts / stepwise /
                               tighter / sample flow / T→M with --mechanism M ...),
                               writes GOLD_TABLES.md + empirical_package.json;
                               slots that did not run stay dropped with a reason
Stage 6.5 Write-gate         → python -m scripts.core.empirical_package audit <package.json>
Stage 7: Paper Draft         → scripts/agent_pipeline.py / report_generator.py  【写作轨】
Stage 8: Review              → scripts/core/llm_reviewer.py
```
Writing (7) and empirics (4–6) are separate hand-offs — see `docs/ARCHITECTURE.md` §0.

Each stage should pause for user confirmation when HITL is enabled.
Use `python scripts/agent_pipeline.py --topic "..." --use-hitl` (defaults to
outline/literature/draft gates). `run_research.py` also defaults to HITL;
set `FINAI_NO_HITL=1` or `--no-use-hitl` for batch. Do NOT auto-continue past a stage.

HITL protocol (`AgentOrchestrator` / `AgentPipeline`):
1. Stage agent runs first; gate holds **after** output exists (review real content).
2. `approve_step(stage)` then `resume_pipeline(paused)` → keep output, run next stage.
3. `reject_step(stage, feedback)` then `resume_pipeline(paused)` → re-run same stage
   with feedback injected; do not call resume while the gate is still PENDING.

---

## Key Entry Scripts

| I want to... | Run this |
|---|---|
| Check system health | `python scripts/health_check.py` |
| Clarify topic (5 rounds) | `python scripts/start_research.py --topic "..."` |
| Run full pipeline | `python scripts/agent_pipeline.py --topic "..." --use-hitl` |
| Agent-host batch (fail-closed) | `python scripts/agent_host_entry.py --topic "..."` |
| Generate paper draft | `python scripts/research_framework/report_generator.py --outline FILE.md` |
| Run empirics (modern DID) | `python -m scripts.research_framework.enhanced_pipeline --topic "..." [--mechanism M1 M2]` or `from scripts.research_framework import modern_did` |
| Audit empirical package / write-gate | `python -m scripts.core.empirical_package audit output/empirical_package.json` |
| List journal templates | `python scripts/journal_template.py --list` |
| List / register MCP servers | `python scripts/register_mcp_servers.py --list` / `--profile academic --prune` |
| Verify project integrity | `python scripts/audit_guard.py` (26/26 checks) |

---

## Mandatory Conventions

1. **Data provenance required** — every fetched dataset must call `DataFetcher.fetch()` not bypass it. The default `allow_synthetic=False`. Mock data needs explicit user authorization.
2. **Cite papers by DOI/ArXiv ID** — never invent citations. Use Semantic Scholar / OpenAlex MCP for searches.
3. **Statistical sanity** — cluster-robust SE at firm level; wild bootstrap for small-N; pre-trend tests for DID.
4. **Journals** — 30 templates available. Default venue: 经济研究 (Chinese) / JF (English). User can override via `--venue`.
5. **HITL** — pause at every stage transition. Never auto-skip a confirmation gate.
6. **No silent fallback to mock data** — fetch() raises if all layers fail unless user opts in.
7. **Empirical package before causal claims** — a policy DID is gold slots + live T→M table + a retellable story page, not one TWFE coefficient. Controls need jobs attached to *this* Y. Core needs ≥2 named channels from constructs other than Y, and two mechanism methods from *different inference families*. Do not drop mechanism on core mode. Do not write 「研究发现」 when `main_p>0.10` or the event-study figure is dirty. Do not write 「H1 被拒绝」— rewrite the question. Claim ≤ tables; do not ship a whole output folder as the submission.

---

## File Layout (skim-level)

```
scripts/
├── agent_pipeline.py       # Entry: writing pipeline
├── agent_host_entry.py     # Entry: non-interactive agent-host (SKIPPED/FINAL)
├── research_framework/     # 58 econometric method modules
├── core/                   # agent orchestration (LLM, checkpoint, telemetry)
├── health_check.py         # System diagnostics
├── audit_guard.py          # 25-check project integrity
├── journal_template.py     # 30 journal templates
├── register_mcp_servers.py # 43 MCP servers
└── universal_data_fetcher.py # 7-layer data fallback

mcp_servers/                # 43 MCP directories (28 free + 12 keyed + 3 opt-in)
docs/
├── tutorials/              # Step-by-step guides
├── adr/                    # Architecture Decision Records
└── api_reference.md        # API documentation
papers/                     # 2 demo papers (sample data)
```

---

## Skill Triggers (if your tool supports them)

- `Skill: fin-full-pipeline` — end-to-end topic → paper PDF
- `Skill: fin-lit-review` — systematic literature review
- `Skill: fin-novelty-check` — JF/JFE/RFS novelty verification
- `Skill: fin-experiment-design` — DID/IV/RDD design
- `Skill: fin-paper-draft` — body text generation
- `Skill: fin-paper-figure` — 20+ chart types, ≥300 DPI
- `Skill: fin-data-acquisition` — auto-fetch + regression scripts

---

## Cross-Platform Notes

- **macOS / Linux**: fully supported. CI matrix includes both.
- **Windows**: most features work. Known limitations:
 - `event_monitor.py --daemon` (uses `os.fork`) → **not supported on Windows**.
   Use `scripts/install_service.ps1 -Action Install` (Task Scheduler wrapper) instead.
   Polling mode (`--interval 300`) works on all platforms.
 - `keychain_setup.py` (mac-specific) → use `scripts/keychain_manager.py`
   instead.
- **Python**: 3.10, 3.11, 3.12, 3.13 all supported. Some `asyncio.get_event_loop()`
  calls emit DeprecationWarning on 3.10+ (harmless but adds noise).

---

## First-Touch Protocol (recommended)

When the user opens a session for the first time:

1. Greet them, list capabilities (5 max).
2. Run `python scripts/health_check.py` (no args) in background; show top 3 issues only.
3. Ask: "Describe your research direction."
4. Do NOT auto-start the pipeline. Wait for the topic.

---

## Reference (read if needed)

- `CLAUDE.md` — Claude Code detailed instructions
- `README.md` — project overview
- `使用指南.md` — Chinese full guide (993 lines, 13 chapters)
- `.cursor/rules/system-init.mdc` — Cursor IDE rules
- `.github/copilot-instructions.md` — Copilot detailed instructions

> **CAUTION**: AI-generated causal identification strategies, statistical results,
> and citations MUST be independently verified by the human researcher before
> submission. The agent accelerates work, not replaces authorship.
