#!/usr/bin/env python3
"""CrossRef DOI API - 参考文献元数据补全

基于 DOI 补全参考文献的标题、作者、期刊、年份、卷期页码。
API文档: https://www.crossref.org/documentation/retrieve-metadata/rest-api/

使用方法:
    from scripts.crossref_doi import CrossRefClient
    client = CrossRefClient()
    meta = client.get_metadata_by_doi("10.1016/j.jfinec.2023.104896")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import requests

# P5-6 audit-2026-07-23: 模块级 Session
from requests.adapters import HTTPAdapter as _HTTPAdapter
_SESSION = requests.Session()
_SESSION.mount("https://", _HTTPAdapter(pool_connections=10, pool_maxsize=10))

_log = logging.getLogger(__name__)

API_BASE = "https://api.crossref.org/works"


@dataclass
class DOIMetadata:
    """Standardized DOI metadata."""
    doi: str
    title: str
    authors: list[str]
    journal: str
    year: int
    volume: str | None
    issue: str | None
    pages: str | None
    publisher: str | None
    issn: str | None
    url: str | None

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "publisher": self.publisher,
            "issn": self.issn,
            "url": self.url,
        }


class CrossRefClient:
    """CrossRef DOI API client with rate limiting."""

    def __init__(self, mailto: str = "research@example.com", rate_limit: float = 0.2):
        """
        Args:
            mailto: Your email for CrossRef polite pool (faster response)
            rate_limit: Seconds between requests (CrossRef requires >=0.2s)
        """
        self.mailto = mailto
        self.rate_limit = rate_limit
        self._last_request = 0.0

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def get_metadata_by_doi(self, doi: str) -> DOIMetadata | None:
        """Fetch metadata for a single DOI.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            DOIMetadata or None if not found / error.
        """
        # Normalize DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        if doi.startswith("http://doi.org/"):
            doi = doi[len("http://doi.org/"):]

        url = f"{API_BASE}/{doi}"
        headers = {
            "User-Agent": f"Mailto:{self.mailto}",
            "Accept": "application/json",
        }

        self._rate_limit()

        try:
            resp = _SESSION.get(url, headers=headers, timeout=15)
            if resp.status_code == 404:
                _log.warning("[CrossRef] DOI not found: %s", doi)
                return None
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message", {})

            # Extract authors
            authors_raw = message.get("author", [])
            authors = []
            for a in authors_raw:
                given = a.get("given", "")
                family = a.get("family", "")
                name = f"{given} {family}".strip()
                if not name:
                    name = a.get("name", "Unknown")
                authors.append(name)

            # Extract publication info
            title_list = message.get("title", [])
            title = title_list[0] if title_list else "Unknown"

            container = message.get("container-title", [])
            journal = container[0] if container else ""

            issued = message.get("issued", {})
            year = None
            if "date-parts" in issued:
                date_parts = issued["date-parts"]
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]

            volume = message.get("volume", "")
            issue = message.get("issue", "")
            page = message.get("page", "")
            publisher = message.get("publisher", "")

            # ISSN
            issn_list = message.get("ISSN", [])
            issn = issn_list[0] if issn_list else None

            # URL
            url_ref = message.get("URL", f"https://doi.org/{doi}")

            return DOIMetadata(
                doi=doi,
                title=title,
                authors=authors,
                journal=journal,
                year=year or 0,
                volume=str(volume) if volume else None,
                issue=str(issue) if issue else None,
                pages=str(page) if page else None,
                publisher=publisher,
                issn=issn,
                url=url_ref,
            )

        except requests.exceptions.RequestException as exc:
            _log.warning("[CrossRef] Request failed for %s: %s", doi, exc)
            return None
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            _log.warning("[CrossRef] Parse failed for %s: %s", doi, exc)
            return None

    def batch_get(self, dois: list[str]) -> list[DOIMetadata | None]:
        """Batch fetch metadata for multiple DOIs."""
        results = []
        for doi in dois:
            meta = self.get_metadata_by_doi(doi)
            results.append(meta)
        return results


def enrich_bibtex_entry(doi: str) -> dict | None:
    """Fetch DOI metadata and return as a minimal BibTeX-compatible dict."""
    client = CrossRefClient()
    meta = client.get_metadata_by_doi(doi)
    if meta is None:
        return None

    import re
    author_str = " and ".join(meta.authors[:3])
    if len(meta.authors) > 3:
        author_str += " et al."

    year_str = str(meta.year) if meta.year else "n.d."
    key = re.sub(r"[^a-z]", "", meta.authors[0].lower()[:8]) if meta.authors else "unknown"
    key += year_str if meta.year else ""

    return {
        "doi": meta.doi,
        "title": meta.title,
        "author": author_str,
        "journal": meta.journal,
        "year": year_str,
        "volume": meta.volume or "",
        "number": meta.issue or "",
        "pages": meta.pages or "",
        "publisher": meta.publisher or "",
    }


if __name__ == "__main__":
    # Quick test
    client = CrossRefClient()
    result = client.get_metadata_by_doi("10.1016/j.jfinec.2023.104896")
    if result:
        print(f"Title: {result.title}")
        print(f"Authors: {', '.join(result.authors[:3])}")
        print(f"Journal: {result.journal}")
        print(f"Year: {result.year}")
    else:
        print("DOI not found or API error")
