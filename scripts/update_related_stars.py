#!/usr/bin/env python3
"""update_related_stars.py — Auto-update star counts in README.md Related Projects.

Reads repo URLs from the "## Related Projects" section, queries GitHub API
for current star counts, and updates README.md in place.

Usage:
    python scripts/update_related_stars.py           # dry-run (show changes)
    python scripts/update_related_stars.py --apply   # write to README.md
    python scripts/update_related_stars.py --report  # save report to docs/audit/

Why this matters:
    Star counts in README grow stale fast (dowhy already 8.1K → 8.2K in a
    month). Manual updates are error-prone; this script makes it reproducible.

Rate limiting:
    GitHub API allows 60 req/hr unauthenticated, 5000/hr authenticated.
    We throttle to 1 req/sec to stay well below limits either way.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# Match GitHub repo URL patterns in markdown links: [name](https://github.com/owner/repo)
REPO_LINK_RE = re.compile(
    r"\[(?P<name>[^\]]+)\]\(https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^)/]+)\)"
)
# Match existing star counts: (8.1K ⭐), (274 ⭐), (8208 ⭐), etc.
STARS_RE = re.compile(
    r"\((?P<stars>[\d.]+[Kk]?)\s*⭐\)"
)


def fetch_stars(owner: str, repo: str, timeout: int = 10) -> int | None:
    """Fetch current star count from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "FinAI-Research-Workflow/0.2.0-alpha")
    req.add_header("Accept", "application/vnd.github+json")
    # Use gh CLI token if available (raises rate limit to 5000/hr)
    gh_token = _get_gh_token()
    if gh_token:
        req.add_header("Authorization", f"Bearer {gh_token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            stars = data.get("stargazers_count")
            if isinstance(stars, int):
                return stars
            return None
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.stderr.write(f"  ⚠️ rate limited on {owner}/{repo}\n")
        elif e.code == 404:
            sys.stderr.write(f"  ⚠️ repo not found: {owner}/{repo}\n")
        else:
            sys.stderr.write(f"  ⚠️ HTTP {e.code} on {owner}/{repo}\n")
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        sys.stderr.write(f"  ⚠️ network error on {owner}/{repo}: {type(e).__name__}\n")
        return None


def _get_gh_token() -> str | None:
    """Try to get a GitHub token from gh CLI for higher rate limits."""
    try:
        import subprocess

        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):  # noqa: S110
        pass
    return None


def format_stars(n: int) -> str:
    """Format star count with K suffix for >= 1000."""
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def find_related_section(text: str) -> tuple[int, int] | None:
    """Find byte offsets of '## Related Projects' section."""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## Related Projects"):
            start = i
            break
    if start is None:
        return None
    # End at next ## heading
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("## "):
            end = i
            break
    # Convert line offsets to byte offsets (approximate but fine for ASCII)
    offset_start = sum(len(lines[i]) + 1 for i in range(start))
    offset_end = sum(len(lines[i]) + 1 for i in range(end))
    return offset_start, offset_end


def update_readme(text: str, apply: bool, rate_limit_sec: float = 1.0) -> dict:
    """Find all repo links in Related Projects section and update star counts."""
    section = find_related_section(text)
    if section is None:
        return {"error": "## Related Projects section not found"}

    offset_start, offset_end = section
    section_text = text[offset_start:offset_end]

    changes = []
    updated_lines = []

    for line in section_text.split("\n"):
        # Find repo link and existing stars
        link_match = REPO_LINK_RE.search(line)
        if not link_match:
            updated_lines.append(line)
            continue
        owner = link_match.group("owner")
        repo = link_match.group("repo")
        name = link_match.group("name")

        # Find existing stars
        stars_match = STARS_RE.search(line)
        old_stars = stars_match.group("stars") if stars_match else None

        # Fetch current
        print(f"  → {owner}/{repo} (was: {old_stars or 'none'})")
        time.sleep(rate_limit_sec)  # rate limit
        new_stars_int = fetch_stars(owner, repo)
        if new_stars_int is None:
            updated_lines.append(line)
            continue
        new_stars_str = format_stars(new_stars_int)

        # Build replacement: always put stars at the end of the line, after description
        # Remove any existing stars from this line first
        cleaned = STARS_RE.sub("", line).rstrip()
        # Insert fresh stars at end
        new_line = cleaned + f" ({new_stars_str} ⭐)"

        changes.append(
            {
                "repo": f"{owner}/{repo}",
                "old": old_stars,
                "new": new_stars_str,
                "name": name,
            }
        )
        updated_lines.append(new_line)

    new_section = "\n".join(updated_lines)
    new_text = text[:offset_start] + new_section + text[offset_end:]

    return {
        "changes": changes,
        "old_text": section_text,
        "new_text": new_section,
        "new_full": new_text,
        "applied": apply,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write to README.md")
    parser.add_argument("--report", action="store_true", help="Save audit report")
    args = parser.parse_args()

    if not README.exists():
        print(f"❌ README.md not found at {README}")
        return 1

    text = README.read_text(encoding="utf-8")
    print(f"Updating star counts in {README.name} ({'APPLY' if args.apply else 'DRY-RUN'})\n")

    result = update_readme(text, apply=args.apply)
    if "error" in result:
        print(f"❌ {result['error']}")
        return 1

    changes = result.get("changes", [])
    if not changes:
        print("\nNo repo links found in Related Projects section.")
        return 0

    print(f"\nFound {len(changes)} repos. Changes:")
    for c in changes:
        old = c["old"] or "(missing)"
        print(f"  {c['repo']}: {old} → {c['new']}")

    if args.apply:
        README.write_text(result["new_full"], encoding="utf-8")
        print(f"\n✅ README.md updated")
    else:
        print(f"\n💡 Run with --apply to write changes")

    if args.report:
        report_path = ROOT / "docs" / "audit" / "RELATED_STARS_AUDIT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write("# Related Projects Star Count Audit\n\n")
            f.write(f"Generated: {Path(__file__).name}\n")
            f.write(f"Mode: {'APPLIED' if args.apply else 'DRY-RUN'}\n\n")
            f.write("| Repository | Old (in README) | New (GitHub API) |\n")
            f.write("|------------|-----------------|------------------|\n")
            for c in changes:
                f.write(f"| [{c['repo']}](https://github.com/{c['repo']}) | {c['old'] or '—'} | {c['new']} |\n")
            f.write("\n## Note\n\n")
            f.write(
                "Run `python scripts/update_related_stars.py --apply` to update README.md\n"
                "with these counts. Consider setting up a monthly GitHub Action.\n"
            )
        print(f"\n📄 Report: {report_path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

