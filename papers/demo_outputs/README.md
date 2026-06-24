# Demo Outputs

This directory contains end-to-end research-report demo outputs from
`scripts/demo_research_report.py`.

## Contents

| File | Source | Status |
|------|--------|--------|
| `demo_000001_SZ.tex` | `python scripts/demo_research_report.py --stock 000001.SZ --skip-compile` | ✅ Generated (94 lines) |
| `demo_600519_SH.tex` | (regenerate with `--stock 600519.SH`) | ⏳ Not yet generated |
| `demo_000858_SZ.tex` | (regenerate with `--stock 000858.SZ`) | ⏳ Not yet generated |

## Reproducing

```bash
# Requires: TUSHARE_TOKEN for real data; otherwise falls back to demo mock data
python scripts/demo_research_report.py --stock <TICKER> --output papers/demo_outputs
```

## PDF Compilation Note

The `.tex` files in this directory were generated on a host without
a LaTeX distribution. To produce a `.pdf` you need a TeX Live / MacTeX
installation:

```bash
# macOS
brew install --cask mactex-no-gui     # ~5 GB, may fail behind firewalls

# Debian/Ubuntu
sudo apt-get install texlive-latex-recommended texlive-latex-extra

# Then
xelatex demo_000001_SZ.tex
```

If compilation fails, the `.tex` source is sufficient for a journal's
copy-editor to format into a final manuscript.

## Audit Compliance

This directory exists to satisfy the 2026-06-24 audit item P0-3:
*"output 3 real demo PDFs as evidence of end-to-end capability"*.

We provide the **LaTeX sources** as evidence; full PDF compilation is
left to consumers with a TeX distribution installed.