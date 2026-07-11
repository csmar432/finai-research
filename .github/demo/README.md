# Demo Assets

This directory contains visual assets for the project README and
documentation.

## Demo GIFs

| File | Dimensions | Frames | Loop | Purpose |
|------|-----------|--------|------|---------|
| `demo_full_pipeline.gif` | 1100×211 | 33 | ~47 s | Full 8-stage research workflow with real MCP data |
| `demo.gif` | 860×608 | 30 | ~6 s | Tool-inventory only (legacy) |
| `demo.cast` | – | – | – | asciinema source for `demo.gif` |
| `demo_v1_health.*` | – | – | – | Backups of v1 |

### `demo_full_pipeline.gif` (active demo)

Records an end-to-end academic research session for the topic
*Carbon Emissions Trading and Enterprise Green Innovation*. Each
frame is a real command invocation whose output is captured at
demo-generation time (no simulated data).

| Stage | Real data source |
|-------|------------------|
| 0  Tool inventory  | `scripts/cli.py version/health` |
| 1  Literature      | OpenAlex MCP — title-search, top 4 by citations |
| 2  Novelty check   | `scripts/cli.py lit-review` |
| 3  Identification  | DID specification: Treat × Post on 14 firms × 3 yrs |
| 4  Data (5 MCPs)   | (a) yfinance, (b) SEC EDGAR, (c) World Bank, (d) OpenAlex, (e) FRED |
| 5  Estimation      | DID coefficient table (Table 3 of the paper) |
| 6  Paper draft     | `papers/us_esg_financing/latex/esg_financing_paper.tex` |
| 7  Audit           | `scripts/audit_guard.py` (16/16 checks) |

Regenerate:

```bash
bash scripts/demo/record_full_pipeline_v4.sh > /tmp/demo.txt 2>&1
python scripts/demo/render_demo_gif_v4.py \
    /tmp/demo.txt .github/demo/demo_full_pipeline.gif \
    1100 0.7 32
```

## Architecture diagrams (5 complementary views)

| # | File | One-line description | View |
|---|------|----------------------|------|
| 1 | `01-architecture-overview.svg/png` | 5-layer end-to-end architecture | High-level bird's-eye |
| 2 | `02-skill-system-map.svg/png` | 17 skills organised into 4 phases | Skill layer |
| 3 | `03-mcp-ecosystem-map.svg/png` | 44 MCP server ecosystem (8 categories) | Data layer |
| 4 | `04-research-pipeline.svg/png` | 8-stage research pipeline (idea → paper) | Flow layer |
| 5 | `05-deployment-data-flow.svg/png` | Deployment / data flow + 3 security boundaries | Ops layer |

Generate:

```bash
python scripts/gen_architecture_diagrams.py
# Output → .github/demo/0[1-5]-*.{svg,png}
```

Convert to PNG (requires `librsvg`):

```bash
brew install librsvg
for f in .github/demo/0[1-5]-*.svg; do
  rsvg-convert -w 1600 -h 1000 "$f" -o "${f%.svg}.png"
done
```