# How to Cite FinAI Research Workflow

> **Recommended citation styles for academic papers**.
> If you used FinAI in a published paper, please cite it — it helps the project grow.
>
> Last updated: 2026-07-12 (audit_fix_2026_07_12 — 修正版本/计数/DOI 占位)

---

## 1. BibTeX (most common)

```bibtex
@software{finai_research_workflow_2026,
  author    = {{csmar432}},
  title     = {{FinAI Research Workflow: An End-to-End AI Agent Pipeline for Economic and Financial Research}},
  year      = {2026},
  month     = jul,
  version   = {0.2.0-alpha},
  url       = {https://github.com/csmar432/finai-research},
  doi       = {10.5281/zenodo.PENDING},  % NOTE: PENDING. Replace after Zenodo release (https://zenodo.org)
  note      = {43 MCP data sources, 47 econometric methods, 17 AI skills, 30 journal templates}
}
```

> **Note**: When the project is archived to Zenodo, the DOI placeholder above
> will be replaced with the real DOI. Until then, cite using the GitHub URL.

## 2. APA (7th edition)

```
csmar432. (2026). FinAI Research Workflow (Version 0.2.0-alpha) [Computer software].
https://github.com/csmar432/finai-research
```

## 3. Chicago (Author-Date)

```
csmar432. 2026. "FinAI Research Workflow." Version 0.2.0-alpha.
https://github.com/csmar432/finai-research.
```

## 4. MLA (9th edition)

```
csmar432. "FinAI Research Workflow." Version 0.2.0-alpha, 2026,
https://github.com/csmar432/finai-research.
```

## 5. IEEE (for engineering / computer science venues)

```
[1] csmar432, "FinAI Research Workflow: An End-to-End AI Agent Pipeline
    for Economic and Financial Research," Version 0.2.0-alpha, 2026.
    [Online]. Available: https://github.com/csmar432/finai-research
```

## 6. GB/T 7714 (中国国家标准，参考中文工具书)

```
csmar432. FinAI Research Workflow: An End-to-End AI Agent Pipeline for
Economic and Financial Research (Version 0.2.0-alpha)[EB/OL]. (2026-07-12).
https://github.com/csmar432/finai-research.
```

---

## Citation Style Selection

| Venue | Recommended style |
|-------|-------------------|
| 经济研究 / 金融研究 / 管理世界 | GB/T 7714 + 脚注引用软件 |
| Journal of Finance / JFE / RFS | Chicago Author-Date + version + URL |
| NeurIPS / ICML / AAAI | BibTeX + version + commit hash |
| arXiv preprint | BibTeX (software entry) + arXiv ID |
| 内working paper / 政策报告 | APA + version + access date |

---

## What to Include in Citations

When citing FinAI in your paper, please include:

1. **Version number** (e.g., `0.2.0-alpha`) — important for reproducibility
2. **GitHub URL** — primary access point
3. **Commit hash** (optional but recommended) — for exact reproducibility
4. **Key capabilities used** (in footnote, optional) — e.g.,
   "We used the ModernDiDEngine for staggered DID estimation (Callaway-Sant'Anna 2021)".

## What NOT to Cite

- Do not cite the GitHub commit URL with a specific SHA only — include the
  release tag or version number too.
- Do not cite individual MCP servers without citing the parent project.
- Do not cite the `scripts/` submodule if you only used a small subset —
  cite the whole project and footnote the specific modules.

---

## Citing Specific Modules

If you used only a subset of FinAI in your paper, you may cite specific
modules in addition to the parent project:

```bibtex
@misc{finai_modern_did,
  author = {{csmar432}},
  title  = {{ModernDiDEngine: Callaway-Sant'Anna, Sun-Abraham, Borusyak,
             Goodman-Bacon, dCdH estimators}},
  year   = {2026},
  url    = {https://github.com/csmar432/finai-research/tree/main/scripts/research_framework/modern_did.py},
  note   = {Part of FinAI Research Workflow v0.2.0-alpha}
}
```

---

## License

FinAI Research Workflow is released under the **MIT License**. Cite as
attribution; no special permission required.

```
MIT License — Copyright (c) 2026 csmar432

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## Updates

| Date | Change |
|------|--------|
| 2026-07-12 | 修正版本号 (0.1.0 → 0.2.0-alpha)、月 (jun → jul)、计数 (44/42/44 → 43/47/30)、加 IEEE/GB-T-7714 |
| 2026-06-28 | 初版 (4 个引用样式) |