#!/usr/bin/env python3
"""verify_bib_dois.py — Audit reference .bib files for missing DOIs.

Usage:
    python scripts/verify_bib_dois.py                    # List missing DOIs
    python scripts/verify_bib_dois.py --check-online     # Also try online lookup
    python scripts/verify_bib_dois.py --report            # Save report

Why this matters:
    BibTeX entries without DOIs are hard to verify and harder to publish
    (most journals require DOI for citations). This script catches the gap.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
BIB_PATTERNS = ["papers/**/*.bib"]

# Regex: match BibTeX entry start and its fields
ENTRY_RE = re.compile(
    r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)\n\s*\}",
    re.DOTALL,
)
FIELD_RE = re.compile(r"^\s*(?P<name>\w+)\s*=\s*[\{\"](?P<value>[^}\"]*)[\}\"]", re.MULTILINE)


def find_bib_entries(path: Path) -> list[dict]:
    """Extract all BibTeX entries from a file."""
    text = path.read_text(encoding="utf-8")
    entries = []
    for m in ENTRY_RE.finditer(text):
        body = m.group("body")
        fields = {}
        for fm in FIELD_RE.finditer(body):
            fields[fm.group("name").lower()] = fm.group("value").strip()
        entries.append(
            {
                "file": str(path.relative_to(REPO)),
                "key": m.group("key"),
                "type": m.group("type"),
                "title": fields.get("title", ""),
                "author": fields.get("author", ""),
                "year": fields.get("year", ""),
                "journal": fields.get("journal", ""),
                "has_doi": "doi" in fields,
                "doi": fields.get("doi", ""),
            }
        )
    return entries


def check_online(doi: str, timeout: int = 5) -> bool:
    """Check if DOI resolves via CrossRef API (more reliable than doi.org redirect)."""
    try:
        req = urllib.request.Request(f"https://api.crossref.org/works/{doi}")
        req.add_header("User-Agent", "FinAI-Research-Workflow/0.2.0-alpha (mailto:research@finai.dev)")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 200:
                return True
            return False
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-online", action="store_true", help="Validate DOIs online")
    parser.add_argument("--report", action="store_true", help="Save report to docs/audit/")
    args = parser.parse_args()

    # Gather all entries
    all_entries = []
    for pat in BIB_PATTERNS:
        for bib in REPO.glob(pat):
            all_entries.extend(find_bib_entries(bib))

    if not all_entries:
        print("No .bib files found.")
        return 0

    # Stats
    total = len(all_entries)
    with_doi = sum(1 for e in all_entries if e["has_doi"])
    missing_doi = [e for e in all_entries if not e["has_doi"]]

    print(f"BibTeX entries: {total}")
    print(f"  With DOI:    {with_doi} ({with_doi/total*100:.0f}%)")
    print(f"  Missing DOI: {len(missing_doi)} ({len(missing_doi)/total*100:.0f}%)")

    if missing_doi:
        print("\n--- Entries missing DOI ---")
        for e in missing_doi[:25]:
            print(f"  [{e['key']}] {e['author'][:40]}")
            print(f"      {e['title'][:90]}")

    # Online validation
    online_check = {}
    if args.check_online:
        print("\n--- Online DOI validation ---")
        for e in all_entries:
            if e["doi"]:
                ok = check_online(e["doi"])
                online_check[e["doi"]] = ok
                status = "✅" if ok else "❌"
                print(f"  {status} {e['doi']}")
        good = sum(1 for v in online_check.values() if v)
        bad = sum(1 for v in online_check.values() if not v)
        print(f"\nOnline: {good} valid, {bad} broken")

    # Save report
    if args.report:
        report_path = REPO / "docs" / "audit" / "BIB_DOI_AUDIT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write("# BibTeX DOI Audit Report\n\n")
            f.write(f"Generated: {Path(__file__).name}\n\n")
            f.write(f"## Summary\n\n")
            f.write(f"- Total entries: {total}\n")
            f.write(f"- With DOI: {with_doi} ({with_doi/total*100:.1f}%)\n")
            f.write(f"- Missing DOI: {len(missing_doi)} ({len(missing_doi)/total*100:.1f}%)\n\n")
            if online_check:
                f.write(f"## Online validation\n\n")
                for doi, ok in online_check.items():
                    f.write(f"- {'✅' if ok else '❌'} {doi}\n")
                f.write("\n")
            if missing_doi:
                f.write(f"## Missing DOI entries\n\n")
                for e in missing_doi:
                    f.write(f"- `[{e['key']}]` {e['author']}\n")
                    f.write(f"  - Title: {e['title']}\n")
                    f.write(f"  - Year: {e['year']}\n")
                    f.write(f"  - Journal: {e['journal']}\n\n")
        print(f"\nReport saved: {report_path.relative_to(REPO)}")

    # Exit code: 0 if all DOIs are present and valid; else 1
    if not missing_doi and (not args.check_online or all(online_check.values())):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
