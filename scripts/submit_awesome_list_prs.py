#!/usr/bin/env python3
"""Auto-submit awesome-list PRs via GitHub API.

For each target repo:
  1. Fork csmar432/<repo> (if not already forked)
  2. Create branch add-finai-research-workflow in fork
  3. Apply README modification from docs/manual/awesome_list_prs/<slug>.md
  4. Commit the change
  5. Open PR from fork:<branch> → upstream:<default-branch>

Prereq: `gh auth login` (PAT with admin:repo, repo scopes).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 5 PR targets: slug → (default_branch, readme_path, entry_text, pr_title, pr_body_file)
TARGETS = [
    {
        "slug": "antontarasenko/awesome-economics",
        "readme_path": "readme.md",
        "section": "## Software",
        "entry_text": "- [FinAI Research Workflow](https://github.com/csmar432/finai-research) - End-to-end empirical research pipeline (43 data sources, 47 econometric methods, 30 journal templates) for economists.",
        "pr_title": "Add FinAI Research Workflow",
        "pr_body_path": "docs/manual/awesome_list_prs/PR-01-antontarasenko-awesome-economics.md",
        "DISABLED": True,   # has_pull_requests=false on this repo (verified 2026-07-11)
        "DISABLED_REASON": "Repository has has_pull_requests=false per GitHub API",
    },
    {
        "slug": "matteocourthoud/awesome-causal-inference",
        "readme_path": "src/libraries.md",
        "section": "## 🐍 Python",
        "entry_text": "\n- [FinAI Research Workflow](https://github.com/csmar432/finai-research)\n  ![stars](https://img.shields.io/github/stars/csmar432/finai-research)\n  - [didi](https://github.com/csmar432/finai-research) - Modern staggered DID (Callaway-Sant'Anna, Sun-Abraham, Borusyak)\n  - [synth](https://github.com/csmar432/finai-research) - Synthetic control and synthetic DiD\n  - [iv](https://github.com/csmar432/finai-research) - IV / 2SLS for panel and cross-section\n  - [gmm](https://github.com/csmar432/finai-research) - Panel GMM (Arellano-Bond, Blundell-Bond)\n  - [rdd](https://github.com/csmar432/finai-research) - Sharp / fuzzy regression discontinuity\n  - [triple](https://github.com/csmar432/finai-research) - Triple-difference (DDD)\n  - [panelquantile](https://github.com/csmar432/finai-research) - Panel fixed-effects quantile regression\n  - [spatial](https://github.com/csmar432/finai-research) - Spatial regression (SAR/SEM/SDM)\n  - [robustness](https://github.com/csmar432/finai-research) - 19-class automated robustness testing\n",
        "pr_title": "Add FinAI Research Workflow (Python library for empirical economic CI workflows)",
        "pr_body_path": "docs/manual/awesome_list_prs/PR-02-matteocourthoud-awesome-causal-inference.md",
    },
    {
        "slug": "wilsonfreitas/awesome-quant",
        "readme_path": "README.md",
        "section": "## Quant Research Environments",
        "entry_text": "\n- [FinAI Research Workflow](https://github.com/csmar432/finai-research) - `Python` - End-to-end empirical-research workflow (43 data sources, 47 econometric methods, 30 journal templates) with HITL gates.\n",
        "pr_title": "Add FinAI Research Workflow",
        "pr_body_path": "docs/manual/awesome_list_prs/PR-03-wilsonfreitas-awesome-quant.md",
    },
    {
        "slug": "academic/awesome-datascience",
        "readme_path": "README.md",
        "section": "## Data Science Research",   # placeholder; will adjust
        "entry_text": "\n- [FinAI Research Workflow](https://github.com/csmar432/finai-research) - End-to-end empirical-research pipeline (43 data sources, 47 econometric methods, 30 journal templates) for economics and finance.\n",
        "pr_title": "Add FinAI Research Workflow",
        "pr_body_path": "docs/manual/awesome_list_prs/PR-04-academic-awesome-datascience.md",
    },
    {
        "slug": "emptymalei/awesome-research",
        "readme_path": "README.md",
        "section": "## Economics & Finance",
        "entry_text": "\n* [FinAI Research Workflow](https://github.com/csmar432/finai-research)\n",
        "pr_title": "Add FinAI Research Workflow to Economics & Finance section",
        "pr_body_path": "docs/manual/awesome_list_prs/PR-05-emptymalei-awesome-research.md",
    },
]


def run(cmd: list[str], check: bool = True, capture: bool = True) -> tuple[int, str, str]:
    """Run a subprocess; return (exit_code, stdout, stderr)."""
    proc = subprocess.run(cmd, capture_output=capture, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write(f"❌ {' '.join(cmd)}\n   stdout: {proc.stdout[:500]}\n   stderr: {proc.stderr[:500]}\n")
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return proc.returncode, proc.stdout, proc.stderr


def gh_api(method: str, endpoint: str, data: Optional[dict] = None) -> dict:
    """Call GitHub API via gh CLI. Returns parsed JSON."""
    args = ["gh", "api", "--method", method, endpoint]
    if data is not None:
        args.extend(["--input", "-"])
    if data is not None:
        proc = subprocess.run(args, input=json.dumps(data), capture_output=True, text=True)
    else:
        proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"⚠️ gh api {method} {endpoint}: {proc.stderr[:300]}\n")
        try:
            return json.loads(proc.stdout) if proc.stdout else {}
        except Exception:
            return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def ensure_fork(upstream_slug: str, fork_owner: str = "csmar432") -> str:
    """Ensure fork exists for upstream_slug; return fork slug."""
    fork_slug = f"{fork_owner}/{upstream_slug.split('/', 1)[1]}"

    # Check if fork already exists
    repo_data = gh_api("GET", f"/repos/{fork_slug}")
    if repo_data.get("id"):
        print(f"   ✓ Fork already exists: {fork_slug}")
        return fork_slug

    print(f"   ⚙️  Forking {upstream_slug} → {fork_slug}...")
    fork_data = gh_api("POST", f"/repos/{upstream_slug}/forks", {"name": upstream_slug.split("/", 1)[1]})
    if fork_data.get("id"):
        print(f"   ✓ Forked: {fork_slug} (id={fork_data['id']})")
        return fork_slug
    print(f"   ⚠️  Fork creation may have failed; check https://github.com/{fork_slug}")
    return fork_slug


def get_default_branch(slug: str) -> str:
    """Get the default branch of a repo via API."""
    data = gh_api("GET", f"/repos/{slug}")
    return data.get("default_branch", "main")


def get_readme_sha(slug: str, branch: str, path: str) -> Optional[str]:
    """Get the SHA of a file at a branch."""
    data = gh_api("GET", f"/repos/{slug}/contents/{path}?ref={branch}")
    return data.get("sha")


def get_readme_content(slug: str, branch: str, path: str) -> str:
    """Get decoded file content from GitHub API."""
    import base64
    data = gh_api("GET", f"/repos/{slug}/contents/{path}?ref={branch}")
    content_b64 = data.get("content", "")
    return base64.b64decode(content_b64).decode("utf-8", errors="replace")


def apply_entry_to_readme(readme: str, section: str, entry_text: str) -> str:
    """Insert entry_text at the end of the section, or append to bottom if section not found."""
    lines = readme.split("\n")
    section_idx = None
    next_section_idx = None
    for i, line in enumerate(lines):
        if line.startswith("#") and section.lower() in line.lower():
            section_idx = i
            break
    if section_idx is None:
        # fallback: append at end
        print(f"   ⚠️  Section '{section}' not found; appending to end of file")
        return readme.rstrip("\n") + "\n" + entry_text + "\n"

    # Find the next section header (any `#`) after this one
    for j in range(section_idx + 1, len(lines)):
        if lines[j].startswith("#"):
            next_section_idx = j
            break
    if next_section_idx is None:
        next_section_idx = len(lines)

    # Insert entry just before next section (preserves table of contents if any)
    insert_idx = next_section_idx
    # Walk backwards over blank lines to insert immediately after the last content line
    while insert_idx > 0 and lines[insert_idx - 1].strip() == "":
        insert_idx -= 1
    new_lines = lines[:insert_idx] + [entry_text] + [""] + lines[insert_idx:]
    return "\n".join(new_lines)


def commit_to_fork(fork_slug: str, branch: str, readme_path: str, new_content: str, commit_msg: str) -> bool:
    """Commit new content to fork at branch. Creates branch if needed."""
    # 1. Get the file's current SHA on the default branch (to use as base)
    default_branch = get_default_branch(fork_slug)
    base_sha = get_readme_sha(fork_slug, default_branch, readme_path)
    if not base_sha:
        print(f"   ❌ Could not get SHA for {readme_path} on {fork_slug}")
        return False

    # 2. Get the current branch's SHA (if it exists)
    branch_data = gh_api("GET", f"/repos/{fork_slug}/git/ref/heads/{branch}")
    branch_sha = branch_data.get("object", {}).get("sha")

    if not branch_sha:
        # Create branch from default_branch HEAD
        head_sha = gh_api("GET", f"/repos/{fork_slug}/git/ref/heads/{default_branch}").get("object", {}).get("sha")
        if not head_sha:
            print(f"   ❌ Could not get head SHA for {fork_slug}/{default_branch}")
            return False
        ref_data = gh_api("POST", f"/repos/{fork_slug}/git/refs", {
            "ref": f"refs/heads/{branch}",
            "sha": head_sha,
        })
        if not ref_data.get("object"):
            print(f"   ❌ Could not create branch {branch}: {ref_data}")
            return False
        print(f"   ✓ Created branch {branch}")

    # 3. Update file content via contents API
    import base64
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("ascii")
    update_data = {
        "message": commit_msg,
        "content": encoded,
        "branch": branch,
    }
    # If the file already exists on this branch, include its sha
    existing_sha = get_readme_sha(fork_slug, branch, readme_path)
    if existing_sha:
        update_data["sha"] = existing_sha

    result = gh_api("PUT", f"/repos/{fork_slug}/contents/{readme_path}", update_data)
    if result.get("commit", {}).get("sha"):
        print(f"   ✓ Committed: {result['commit']['sha'][:10]}")
        return True
    print(f"   ❌ Commit failed: {result.get('message', result)}")
    return False


def open_pr(fork_slug: str, upstream_slug: str, branch: str, default_branch: str,
            title: str, body: str) -> Optional[str]:
    """Open PR from fork:branch → upstream:default_branch. Return PR URL."""
    head = f"{fork_slug.split('/', 1)[0]}:{branch}"
    pr_data = {
        "title": title,
        "head": head,
        "base": default_branch,
        "body": body,
        "maintainer_can_modify": True,
        "draft": False,
    }
    result = gh_api("POST", f"/repos/{upstream_slug}/pulls", pr_data)
    url = result.get("html_url")
    if url:
        print(f"   ✅ PR opened: {url}")
        return url
    print(f"   ❌ PR failed: {result.get('message', result)}")
    if "pull request already exists" in str(result):
        # Find existing PR
        existing = gh_api("GET", f"/repos/{upstream_slug}/pulls?head={head}&state=open")
        if existing and isinstance(existing, list) and existing:
            url = existing[0].get("html_url")
            print(f"   ↪️  Existing PR: {url}")
            return url
    return None


def submit_one(target: dict) -> Optional[str]:
    """Submit one PR target. Return PR URL on success."""
    print(f"\n{'='*70}")
    print(f"▶ {target['slug']}")
    print(f"{'='*70}")
    slug = target["slug"]
    upstream_slug = slug
    fork_slug = ensure_fork(slug)

    branch = "add-finai-research-workflow"
    readme_path = target["readme_path"]
    default_branch = get_default_branch(upstream_slug)
    print(f"   ✓ Detected default branch: {default_branch}")

    # 0. Idempotency: if a PR already exists, return its URL
    head_ref = f"{fork_slug.split('/', 1)[0]}:{branch}"
    existing_prs = gh_api("GET", f"/repos/{upstream_slug}/pulls?head={head_ref}&state=open")
    if isinstance(existing_prs, list) and existing_prs:
        url = existing_prs[0].get("html_url")
        print(f"   ↪️  PR already open: {url}")
        return url
    closed_prs = gh_api("GET", f"/repos/{upstream_slug}/pulls?head={head_ref}&state=closed")
    if isinstance(closed_prs, list) and closed_prs:
        # A closed PR exists — don't reopen; let user handle
        url = closed_prs[0].get("html_url")
        print(f"   ↪️  PR already closed: {url}")
        return url

    # 1. Get current README from fork (it should match upstream after fork sync)
    print(f"   📥 Reading {readme_path} from fork {fork_slug}@{default_branch}...")
    current = get_readme_content(fork_slug, default_branch, readme_path)
    if not current:
        print(f"   ❌ Empty README content; aborting")
        return None
    print(f"   ✓ Got {len(current)} chars")

    # 2. Idempotency: check if entry already added (regardless of which branch)
    if "csmar432/finai-research" in current:
        print(f"   ⚠️  finai-research already present in fork {default_branch} {readme_path}; committing anyway (will be deduped upstream if previously merged)")

    # 3. Apply entry
    new_content = apply_entry_to_readme(current, target["section"], target["entry_text"])
    if new_content == current:
        print(f"   ⚠️  No change applied; aborting")
        return None
    print(f"   ✓ Entry inserted at section: {target['section']}")

    # 4. Commit to fork
    commit_msg = f"Add FinAI Research Workflow ({slug.split('/', 1)[1]})"
    if not commit_to_fork(fork_slug, branch, readme_path, new_content, commit_msg):
        return None

    # 5. Read PR body
    body_path = REPO_ROOT / target["pr_body_path"]
    if body_path.exists():
        body = body_path.read_text()
    else:
        body = target.get("pr_body_path", "")

    # 6. Open PR
    url = open_pr(fork_slug, upstream_slug, branch, default_branch,
                  target["pr_title"], body)
    return url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", help="submit only this slug (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="don't commit or open PRs")
    args = parser.parse_args()

    targets = TARGETS
    if args.target:
        targets = [t for t in TARGETS if t["slug"] == args.target]
        if not targets:
            print(f"❌ Unknown target: {args.target}")
            return 1

    results = {}
    for t in targets:
        if args.dry_run:
            print(f"[DRY-RUN] would process {t['slug']}")
            continue
        if t.get("DISABLED"):
            print(f"\n⚠️  Skipping {t['slug']} — {t.get('DISABLED_REASON', 'disabled')}")
            results[t["slug"]] = "SKIPPED (repo disabled)"
            continue
        try:
            url = submit_one(t)
            results[t["slug"]] = url or "FAILED"
        except Exception as e:
            print(f"❌ {t['slug']}: {type(e).__name__}: {e}")
            results[t["slug"]] = f"ERROR: {e}"

    print(f"\n{'='*70}")
    print("Summary")
    print(f"{'='*70}")
    for slug, status in results.items():
        print(f"  {slug}: {status}")
    return 0


if __name__ == "__main__":
    main()
