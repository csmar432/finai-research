# Demo Assets

This directory contains the README demo and complementary architecture views.

## Canonical Quick Demo

`demo.gif` is a 1200×675, 15-frame guided product preview. It explains the
workflow contract without pretending that a staged animation is a live research
run. In particular, it contains no generated citations, coefficients, p-values,
or claims of real-time data acquisition.

The five scenes cover:

1. Codex (recommended), Cursor, Claude Code, and API/Ollama hosts.
2. Research-brief clarification and human review.
3. Separate writing and empirical tracks.
4. Local-first, fail-closed routing; Mock remains explicit opt-in only.
5. A verifiable delivery package and dynamically counted capabilities.

Regenerate with the repository's existing Pillow dependency:

```bash
python scripts/demo/gen_quick_demo.py
```

The storyboard and content are deterministic. Platform-appropriate fonts may
produce small pixel differences across operating systems. The generator validates
output dimensions and frame count before returning.

## Architecture diagrams (9 complementary views)

| # | File | One-line description | View |
|---|------|----------------------|------|
| 1 | `01-architecture-overview.svg/png` | 5-layer end-to-end architecture | High-level bird's-eye |
| 2 | `02-skill-system-map.svg/png` | 18 skills organised into 4 phases | Skill layer |
| 3 | `03-mcp-ecosystem-map.svg/png` | 43 source directories with fail-closed routing | Data layer |
| 4 | `04-research-pipeline.svg/png` | 8-stage research pipeline (idea → paper) | Flow layer |
| 5 | `05-deployment-data-flow.svg/png` | Deployment / data flow + 3 security boundaries | Ops layer |
| 6 | `06-writing-track.svg/png` | Five writing artifacts + HITL transitions | Writing layer |
| 7 | `07-data-routing.svg/png` | Exact-variable routing and visible stop | Data contract |
| 8 | `08-did-selection.svg/png` | Modern DID estimator decision path | Methods layer |
| 9 | `09-provenance-chain.svg/png` | Source-to-artifact lineage | Reproducibility |

Generate:

```bash
python scripts/gen_architecture_diagrams.py
# Output → .github/demo/0[1-9]-*.{svg,png}
```

Convert to PNG (requires `librsvg`):

```bash
brew install librsvg
for f in .github/demo/0[1-9]-*.svg; do
  rsvg-convert -w 1600 -h 1000 "$f" -o "${f%.svg}.png"
done
```
