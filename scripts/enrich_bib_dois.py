#!/usr/bin/env python3
"""enrich_bib_dois.py — Auto-enrich BibTeX files with missing DOIs via CrossRef API.

For each entry without a DOI, query CrossRef with title + first author + year,
fetch the most likely DOI, and update the .bib file in-place.

Usage:
    python scripts/enrich_bib_dois.py                   # dry-run (just report)
    python scripts/enrich_bib_dois.py --apply            # actually update .bib
    python scripts/enrich_bib_dois.py --limit 5          # only enrich first 5
    python scripts/enrich_bib_dois.py --bib papers/finai_methodology/references.bib

CrossRef API docs:
    https://api.crossref.org/swagger-ui/index.html

We rate-limit to 5 req/sec (CrossRef etiquette).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CROSSREF_BASE = "https://api.crossref.org/works"
USER_AGENT = "FinAI-Research-Workflow/0.2.0a0 (mailto:research@finai.dev)"


def query_crossref(title: str, author: str, year: str, timeout: int = 15) -> str | None:
    """Query CrossRef for DOI matching title/author/year.

    Returns DOI string or None.
    """
    # Build query: prefer bibliographic search with title + author + year
    params = {
        "query.bibliographic": title,
        "rows": 5,
    }
    if author:
        # Extract first author last name
        first_author = re.split(r"[,&]", author)[0].strip().split()[-1]
        params["query.author"] = first_author
    if year:
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"

    url = f"{CROSSREF_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        items = data.get("message", {}).get("items", [])
        # Prefer items from authoritative economics/finance journals
        PRIORITY_JOURNALS = (
            "American Economic Review",
            "Econometrica",
            "Quarterly Journal of Economics",
            "Review of Economic Studies",
            "Journal of Political Economy",
            "Journal of Finance",
            "Journal of Financial Economics",
            "Review of Financial Studies",
            "Journal of Econometrics",
            "Management Science",
            "Review of Economics and Statistics",
            "Journal of Economic Literature",
            "Journal of Economic Perspectives",
            "American Economic Journal",
            "AEJ",
            "RFS",
            "JF",
            "JFE",
        )
        best_doi = None
        best_score = 0.0
        for item in items:
            doi = item.get("DOI")
            if not doi:
                continue
            crossref_titles = item.get("title", [])
            if not crossref_titles:
                continue
            cr_title = crossref_titles[0].lower()
            our_title = title.lower()
            # Title overlap score
            our_words = {w for w in re.findall(r"\b\w{4,}\b", our_title)}
            cr_words = {w for w in re.findall(r"\b\w{4,}\b", cr_title)}
            if not our_words:
                continue
            overlap = len(our_words & cr_words) / len(our_words)
            # Bonus for matching a priority journal
            journal_priority = any(
                p.lower() in " ".join(item.get("container-title", [])).lower()
                for p in PRIORITY_JOURNALS
            )
            score = overlap + (0.3 if journal_priority else 0)
            if overlap >= 0.6 and score > best_score:
                best_score = score
                best_doi = doi
        return best_doi
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        sys.stderr.write(f"  ⚠️ CrossRef error: {e}\n")
        return None


def parse_bib_entries(text: str) -> list[dict]:
    """Parse BibTeX entries with field extraction."""
    ENTRY_RE = re.compile(
        r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)\n\s*\}",
        re.DOTALL,
    )
    FIELD_RE = re.compile(r"^\s*(?P<name>\w+)\s*=\s*[\{\"](?P<value>[^}\"]*)[\}\"]", re.MULTILINE)

    entries = []
    for m in ENTRY_RE.finditer(text):
        body = m.group("body")
        fields = {}
        for fm in FIELD_RE.finditer(body):
            fields[fm.group("name").lower()] = fm.group("value").strip()
        entries.append(
            {
                "key": m.group("key"),
                "type": m.group("type"),
                "start": m.start(),
                "end": m.end(),
                "fields": fields,
                "raw": m.group(0),
            }
        )
    return entries


def enrich_bib_file(bib_path: Path, apply: bool, limit: int | None) -> dict:
    """Enrich a single .bib file. Returns stats dict."""
    text = bib_path.read_text(encoding="utf-8")
    entries = parse_bib_entries(text)

    stats = {
        "file": str(bib_path.relative_to(ROOT)),
        "total": len(entries),
        "enriched": 0,
        "failed": 0,
        "skipped": 0,
    }

    if not entries:
        return stats

    new_text = text
    for entry in entries:
        if "doi" in entry["fields"]:
            stats["skipped"] += 1
            continue
        if limit and stats["enriched"] >= limit:
            break

        title = entry["fields"].get("title", "").replace("\n", " ").strip()
        author = entry["fields"].get("author", "")
        year = entry["fields"].get("year", "")
        if not title or not author:
            stats["skipped"] += 1
            continue

        # CrossRef rate-limit: 5 req/sec (be polite)
        time.sleep(0.25)

        print(f"  [{entry['key']}] {author.split(',')[0]}: {title[:60]}...")
        doi = query_crossref(title, author, year)
        if doi:
            print(f"     → Found DOI: {doi}")
            stats["enriched"] += 1

            if apply:
                # Inject doi = {DOI} field right after the key (e.g. after `key,`)
                # Strategy: replace `@type{key,\n` with `@type{key,\n  doi = {DOI},\n`
                old = entry["raw"]
                # Find the comma after the key
                key_comma_pattern = re.compile(
                    r"(@\w+\s*\{\s*" + re.escape(entry["key"]) + r"\s*,)"
                )
                m = key_comma_pattern.search(old)
                if m:
                    new_entry = (
                        m.group(1)
                        + "\n  doi = {"
                        + doi
                        + "},"
                        + old[m.end():]
                    )
                    new_text = new_text.replace(old, new_entry, 1)
        else:
            print(f"     → No DOI found")
            stats["failed"] += 1

    if apply and stats["enriched"] > 0:
        bib_path.write_text(new_text, encoding="utf-8")
        print(f"  💾 Updated {bib_path.name}")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write DOIs to .bib")
    parser.add_argument("--limit", type=int, help="Limit enrichments per file")
    parser.add_argument("--bib", type=str, help="Specific .bib file to enrich")
    args = parser.parse_args()

    print(f"CrossRef DOI Enrichment · {'APPLY' if args.apply else 'DRY-RUN'}\n")

    if args.bib:
        bib_files = [Path(args.bib)]
    else:
        bib_files = sorted(ROOT.glob("papers/**/*.bib"))

    total_enriched = 0
    total_failed = 0
    for bib in bib_files:
        if not bib.exists():
            continue
        print(f"\n📄 {bib.relative_to(ROOT)}")
        stats = enrich_bib_file(bib, apply=args.apply, limit=args.limit)
        print(
            f"   Total: {stats['total']}, "
            f"Enriched: {stats['enriched']}, "
            f"Failed: {stats['failed']}, "
            f"Skipped (already has DOI): {stats['skipped']}"
        )
        total_enriched += stats["enriched"]
        total_failed += stats["failed"]

    print(f"\n{'='*50}")
    print(f"Total: enriched {total_enriched}, failed {total_failed}")
    if not args.apply and total_enriched > 0:
        print(f"\n💡 Run with --apply to actually update .bib files")

    return 0


if __name__ == "__main__":
    sys.exit(main())
