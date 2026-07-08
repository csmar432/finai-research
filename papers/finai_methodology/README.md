# FinAI Methodology Paper · arXiv Submission

> **Status**: Draft (2026-07-08)  
> **Compile**: `tectonic finai.tex` (or `latex finai.tex && bibtex finai && latex finai.tex && dvips finai.dvi && ps2pdf finai.ps`)  
> **Output**: `finai.pdf` (43 KB)

## Files

| File | Description |
|------|-------------|
| `finai.tex` | Main LaTeX manuscript (arXiv-compatible AEA format) |
| `references.bib` | BibTeX bibliography (15 references) |
| `finai.pdf` | Compiled PDF |

## arXiv Submission Checklist

- [ ] Add arXiv categories: `cs.AI`, `econ.GN`, `q-fin.GN`
- [ ] Verify all references are accessible
- [ ] Run `arxiv-latex` checker: `arXivcheck finai.tex`
- [ ] Remove author information (arXiv uses separate metadata form)
- [ ] Add keywords in arXiv submission form
- [ ] Check PDF renders correctly on arXiv (font embedding)
- [ ] Upload figures separately if needed (> 10MB total)

## How to Update

```bash
# Edit finai.tex, then recompile
cd papers/finai_methodology
tectonic finai.tex

# Add new references to references.bib
# References must include DOI or URL for arXiv
```

## Next Steps

1. **Add co-author information** to the LaTeX `\author{}` field
2. **Add acknowledgments** before `\bibliography{}`
3. **Submit to arXiv** at https://arxiv.org/submit
4. **Post to Twitter/X** with link to paper + repo
