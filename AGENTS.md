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
with 43 MCP data sources, 47 econometric methods, 30 journal templates, and
17 AI skills.

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

# 3. Run
python scripts/agent_pipeline.py --topic "Carbon trading and green innovation"
```

---

## 8-Stage Pipeline

```
Stage 0: Health Check        → python scripts/health_check.py
Stage 1: Idea Generation     → IDE handles via prompt
Stage 2: Literature Review   → scripts/literature_download.py
Stage 3: Novelty Check       → scripts/agent_pipeline.py --novelty-check
Stage 4: Empirical Design    → scripts/research_framework/pipeline.py --mode design
Stage 5: Data Acquisition    → scripts/universal_data_fetcher.py
Stage 6: Analysis            → scripts/research_framework/modern_did.py
Stage 7: Paper Draft         → scripts/research_framework/report_generator.py
Stage 8: Review              → scripts/core/llm_reviewer.py
```

Each stage requires user confirmation (HITL). Do NOT auto-continue past a stage.

---

## Key Entry Scripts

| I want to... | Run this |
|---|---|
| Check system health | `python scripts/health_check.py` |
| Run full pipeline | `python scripts/agent_pipeline.py --topic "..."` |
| Generate paper draft | `python scripts/research_framework/report_generator.py --outline FILE.md` |
| Run a specific method (DID/IV/RDD/PSM) | `python scripts/research_framework/modern_did.py --help` |
| List journal templates | `python scripts/journal_template.py --list` |
| List MCP servers | `python scripts/register_mcp_servers.py --list` |
| Verify project integrity | `python scripts/audit_guard.py` (17/17 checks) |

---

## Mandatory Conventions

1. **Data provenance required** — every fetched dataset must call `DataFetcher.fetch()` not bypass it. The default `allow_synthetic=False`. Mock data needs explicit user authorization.
2. **Cite papers by DOI/ArXiv ID** — never invent citations. Use Semantic Scholar / OpenAlex MCP for searches.
3. **Statistical sanity** — cluster-robust SE at firm level; wild bootstrap for small-N; pre-trend tests for DID.
4. **Journals** — 30 templates available. Default venue: 经济研究 (Chinese) / JF (English). User can override via `--venue`.
5. **HITL** — pause at every stage transition. Never auto-skip a confirmation gate.
6. **No silent fallback to mock data** — fetch() raises if all layers fail unless user opts in.

---

## File Layout (skim-level)

```
scripts/
├── agent_pipeline.py       # Entry: full pipeline
├── research_framework/     # 47 econometric methods
├── core/                   # 87 modules (LLM, checkpoint, telemetry)
├── health_check.py         # System diagnostics
├── audit_guard.py          # 17-check project integrity
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
  - `event_monitor.py --daemon` (uses `os.fork`) → not supported; use polling
    mode (`--interval 300`) instead.
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
