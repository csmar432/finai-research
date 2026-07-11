# PR 7 (deferred): vinta/awesome-python

> **Status:** DEFERRED — project does not yet satisfy acceptance criteria.
> **Reason documented:** the project must clear one of three strict bars before
> vinta's automated checks will accept a PR.

## Why we can't PR right now

`vinta/awesome-python`'s `CONTRIBUTING.md` requires the project to satisfy
**ALL** of these AND clear **one** of three acceptance bars:

### Universal quality requirements

1. Python-first (>50% of codebase): ✅ Yes (project is 100% Python).
2. Active (commits within last 12 months): ✅ Yes (commits within last 30 days).
3. Stable (production-ready): ⚠️ Currently `0.2.0-alpha`. The version string
   suggests alpha, which the maintainers' automated check likely flags.
4. Documented (README + examples): ✅ Yes (README + 17 SKILL.md + CLAUDE.md).
5. Unique (distinct value, not "yet another X"): ✅ Yes (workflow layer is
   distinct from algorithm-layer libraries).
6. Established (repo ≥ 1 month old): ✅ Yes.

### Acceptance bars (must clear ONE)

| Bar | Threshold | Status |
|-----|-----------|--------|
| **Industry Standard** | Go-to tool almost everyone uses (e.g. requests, flask, pandas) | ❌ Too new |
| **Rising Star** | 5,000+ stars in < 1 year | ❌ We have ~few stars |
| **Hidden Gem** | 100-500 stars preferred; strong justification + 3 months old with consistent activity + real-world usage | ⚠️ Borderline. Repo is < 3 months old with mostly documentation commits, not yet enough real-world usage citations. |

### Additional hard requirements

- **PyPI publication** — vinta explicitly requires PyPI package names for
  display. We currently install via `pip install -e ".[dev]"` from GitHub.
  Verified at https://pypi.org/project/finai-research-workflow/ → **404 Not Found**.
- **No archived / abandoned** — ✅ Yes.
- **No empty description** — ✅ Yes.
- **>100 stars** — ❌ Not yet (PR description must justify if < 100).

## What we would need to do before submitting

1. Publish a stable (non-alpha) version to PyPI:
   `python -m build && twine upload dist/*`.
2. Reach either 100+ GitHub stars or gather 3+ real-world usage citations
   (papers, blog posts, or third-party tutorials using FinAI).
3. Wait for the repo to age to ≥ 3 months.
4. Then submit with a strong "Hidden Gem" justification in the PR template.

## Action items for the maintainer (you)

1. Decide if we should:
   - (a) Push `0.2.0` to PyPI now and accelerate community adoption.
   - (b) Wait 1-2 months for organic growth, then PR.
2. Once PyPI is published, run
   `python scripts/update_related_stars.py --apply` to update README links.

## Workaround in the meantime

We did not submit any PR to vinta/awesome-python. Listed it in our README's
"Related Projects" section as a curated reference (this is fair use for
attribution).

---

**References:**

- `vinta/awesome-python/CONTRIBUTING.md` (master, 111 lines).
- `vinta/awesome-python/.github/PULL_REQUEST_TEMPLATE.md` (master, 25 lines).
- GitHub repo: https://github.com/vinta/awesome-python (307k stars).
- Our project PyPI status: https://pypi.org/project/finai-research-workflow/ → 404.
