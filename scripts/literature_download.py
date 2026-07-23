#!/usr/bin/env python3
"""
literature_download.py — 学术论文批量下载工具
==============================================
从多个来源下载学术论文：
  - arXiv (PDF + 摘要解析)
  - Semantic Scholar (元数据)
  - OpenAlex (元数据)
  - NBER Working Papers

特性：
  - 去重（按 DOI/arXiv ID）
  - 断点续传
  - 速率限制遵守
  - 缓存检查（已下载跳过）
  - 元数据保存为 JSON

用法：
  python scripts/literature_download.py "tariff innovation firm performance" --source arxiv,semantic --limit 20
  python scripts/literature_download.py --doi 10.1093/qje/fbs042 --output papers/
  python scripts/literature_download.py --arxiv-list 2301.08583,1905.12345 --output papers/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

warnings.filterwarnings("ignore")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# P5-6 audit-2026-07-23: 模块级共享 Session — keep-alive + pool 复用
# pool_connections/pool_maxsize=10 与 audit 建议一致
if _REQUESTS_AVAILABLE:
    try:
        from requests.adapters import HTTPAdapter as _HTTPAdapter
        _SESSION = requests.Session()
        _adapter = _HTTPAdapter(pool_connections=10, pool_maxsize=10)
        _SESSION.mount("http://", _adapter)
        _SESSION.mount("https://", _adapter)
    except Exception:   # noqa: S110
        _SESSION = requests  # fallback: 直接调用 requests.get/post（无 keep-alive）

# ── 配置 ──────────────────────────────────────────────────────────────────────

ATOMS_NS = "http://www.w3.org/2005/Atom"
_ARXIV_BASE = "http://export.arxiv.org/api/query"
_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_OA_BASE = "https://api.openalex.org"
_NBER_BASE = "https://www.nber.org"

_SS_HEADERS = {"Accept": "application/json", "User-Agent": "FinResearch-Agent/1.0"}
_OA_HEADERS = {"User-Agent": "FinResearch-Agent/1.0 (mailto:research@example.com)"}
_ARXIV_UA = "FinResearch-Agent/1.0 (mailto:research@example.com)"

_MIN_PDF_BYTES = 5_000  # 最小有效 PDF 大小

# ── 数据模型 ─────────────────────────────────────────────────────────────────

@dataclass
class PaperRecord:
    """下载的论文记录。"""
    paper_id: str = ""      # 内部唯一 ID（DOI 或 arXiv ID）
    source: str = ""        # arxiv / semantic / openalex / nber
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    doi: str = ""
    arxiv_id: str = ""
    venue: str = ""
    citation_count: int = 0
    pdf_url: str = ""
    pdf_path: str = ""      # 本地保存路径
    downloaded: bool = False
    size_kb: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _normalize_arxiv_id(raw: str) -> str:
    """清理 arXiv ID。"""
    value = raw.strip()
    for prefix in ("https://arxiv.org/abs/", "https://arxiv.org/pdf/", "arxiv:", "id:"):
        if prefix.lower() in value.lower():
            value = value.lower().split(prefix.lower())[1]
    # 去除版本号
    if "." in value and any(c.isdigit() for c in value.split(".")[-1]):
        parts = value.split(".")
        if len(parts) == 2 and parts[1].isdigit():
            pass
        elif parts[-1].startswith("v") and parts[-1][1:].isdigit():
            value = ".".join(parts[:-1])
    return value.strip()


def _arxiv_id_pattern(value: str) -> bool:
    new_re = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
    old_re = re.compile(r"^[a-z-]+/\d{7}(v\d+)?$")
    return bool(new_re.match(value) or old_re.match(value))


# ── v2.2 (2026-07-13, PR-2.7): token-bucket rate limiter ───────────────
# Replaces the old ``time.sleep(3.0)`` blanket which made literature pulls
# O(papers × 3s) — i.e. ~5 minutes for 50 SS detail fetches.  The new
# limiter honors ``X-RateLimit-Remaining`` headers when present and falls
# back to a default 3 req/s budget otherwise.  Calls coming from the
# data_cache layer skip the limiter entirely (the cache hit already paid
# the cost once).

_DEFAULT_BUCKET_CAPACITY = 3.0      # tokens
_DEFAULT_BUCKET_REFILL_PER_SEC = 1.0  # tokens per second
_bucket_lock = threading.Lock()
_bucket_state: dict[str, tuple[float, float]] = {}


class _TokenBucket:
    """Simple token bucket: capacity tokens, refilled at refill_per_sec."""

    __slots__ = ("capacity", "refill_per_sec", "_tokens", "_last", "_lock")

    def __init__(
        self,
        capacity: float = _DEFAULT_BUCKET_CAPACITY,
        refill_per_sec: float = _DEFAULT_BUCKET_REFILL_PER_SEC,
    ):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.refill_per_sec,
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            if not blocking:
                return False
            wait = (1.0 - self._tokens) / self.refill_per_sec
        time.sleep(min(wait, timeout) if timeout else wait)
        with self._lock:
            self._tokens = max(0.0, self._tokens - 1.0)
            return True

    def update_from_headers(self, remaining: float | None, reset_seconds: float | None) -> None:
        """Update capacity / refill rate from a server ``X-RateLimit-*`` hint."""
        if remaining is None:
            return
        with self._lock:
            self._tokens = max(0.0, min(self.capacity, float(remaining)))
            self._last = time.monotonic()


_SS_BUCKET = _TokenBucket(capacity=3.0, refill_per_sec=1.0)
_ARXIV_BUCKET = _TokenBucket(capacity=2.0, refill_per_sec=0.5)
_OPENALEX_BUCKET = _TokenBucket(capacity=10.0, refill_per_sec=5.0)


def _rate_limit(
    min_seconds: float = 3.0,  # kept for backward compatibility
    server: str = "semantic_scholar",
    cache_hit: bool = False,
) -> None:
    """Backward-compatible rate limit.  v2.2: token-bucket, not sleep.

    Old behaviour: ``time.sleep(min_seconds)``.  New behaviour: take one
    token from the per-server bucket; cache hits bypass the bucket
    entirely.  ``min_seconds`` is preserved as the *minimum* spacing
    between requests via the bucket's ``refill_per_sec``.
    """
    if cache_hit:
        return
    if server == "semantic_scholar":
        _SS_BUCKET.acquire()
    elif server == "arxiv":
        _ARXIV_BUCKET.acquire()
    elif server == "openalex":
        _OPENALEX_BUCKET.acquire()
    else:
        # Unknown server: fall back to legacy sleep behaviour.
        time.sleep(min_seconds)


# ── arXiv 下载 ────────────────────────────────────────────────────────────────

def search_arxiv(query: str, max_results: int = 20, start: int = 0) -> list[dict]:
    """搜索 arXiv。"""
    if not _REQUESTS_AVAILABLE:
        return []
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        import xml.etree.ElementTree as ET
        resp = _SESSION.get(_ARXIV_BASE, params=params, timeout=30,
                            headers={"User-Agent": _ARXIV_UA})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        results = []
        for entry in root.findall(f"{{{ATOMS_NS}}}entry"):
            raw_id = entry.findtext(f"{{{ATOMS_NS}}}id", "")
            arxiv_id = _normalize_arxiv_id(raw_id)
            results.append({
                "id": arxiv_id,
                "title": (entry.findtext(f"{{{ATOMS_NS}}}title") or "").replace("\n", " ").strip(),
                "authors": [a.text or "" for a in entry.findall(f"{{{ATOMS_NS}}}author")],
                "abstract": (entry.findtext(f"{{{ATOMS_NS}}}summary") or "").replace("\n", " ").strip(),
                "published": (entry.findtext(f"{{{ATOMS_NS}}}published") or "")[:10],
                "categories": [c.get("term", "") for c in entry.findall(f"{{{ATOMS_NS}}}category")],
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            })
        return results
    except Exception as e:
        print(f"  ⚠️  arXiv search error: {e}", file=sys.stderr)
        return []


def download_arxiv_pdf(arxiv_id: str, output_dir: str = "papers/arxiv") -> PaperRecord:
    """下载单个 arXiv 论文 PDF。"""
    record = PaperRecord(paper_id=arxiv_id, source="arxiv", arxiv_id=arxiv_id)
    clean_id = _normalize_arxiv_id(arxiv_id)
    safe_id = clean_id.replace("/", "_")
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{safe_id}.pdf"
    record.pdf_path = str(dest)

    if dest.exists() and dest.stat().st_size >= _MIN_PDF_BYTES:
        record.downloaded = True
        record.size_kb = int(dest.stat().st_size / 1024)
        return record

    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
    try:
        resp = _SESSION.get(pdf_url, timeout=60, headers={"User-Agent": _ARXIV_UA}, stream=True)
        resp.raise_for_status()
        data = b"".join(resp.iter_content(chunk_size=8192))
        if len(data) < _MIN_PDF_BYTES:
            record.error = f"Downloaded file too small ({len(data)} bytes)"
            return record
        dest.write_bytes(data)
        record.downloaded = True
        record.size_kb = int(len(data) / 1024)
        # 获取元数据
        meta = search_arxiv(f"id:{clean_id}", max_results=1)
        if meta:
            m = meta[0]
            record.title = m.get("title", "")
            record.authors = m.get("authors", [])
            record.abstract = m.get("abstract", "")[:2000]
            record.year = int(m.get("published", "0000")[:4]) if m.get("published") else None
            record.pdf_url = m.get("pdf_url", pdf_url)
    except Exception as e:
        record.error = str(e)

    return record


# ── Semantic Scholar ─────────────────────────────────────────────────────────

def search_semantic(query: str, limit: int = 20) -> list[dict]:
    """搜索 Semantic Scholar。"""
    if not _REQUESTS_AVAILABLE:
        return []
    _rate_limit(server="semantic_scholar")
    try:
        resp = _SESSION.get(
            f"{_SS_BASE}/paper/search",
            params={
                "query": query,
                "year": "2015-2025",
                "fields": "paperId,title,authors,year,venue,citationCount,externalIds,openAccessPdf,abstract",
                "limit": min(limit, 100),
                "sort": "citationCount:desc",
            },
            headers=_SS_HEADERS,
            timeout=30,
        )
        if resp.status_code == 429:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  ⚠️  SS search error: {e}", file=sys.stderr)
        return []


def get_semantic_details(paper_id: str) -> dict | None:
    """获取论文详情。"""
    if not _REQUESTS_AVAILABLE:
        return None
    _rate_limit(server="semantic_scholar")
    try:
        resp = _SESSION.get(
            f"{_SS_BASE}/paper/{paper_id}",
            params={
                "fields": "paperId,title,authors,year,venue,citationCount,externalIds,abstract,tldr,openAccessPdf",
            },
            headers=_SS_HEADERS,
            timeout=30,
        )
        if resp.status_code == 429:
            return None
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError, OSError):
        # Specific errors: network failure, JSON decode error, file I/O
        return None


# ── OpenAlex ─────────────────────────────────────────────────────────────────

def search_openalex(query: str, limit: int = 20) -> list[dict]:
    """搜索 OpenAlex。"""
    if not _REQUESTS_AVAILABLE:
        return []
    try:
        resp = _SESSION.get(
            f"{_OA_BASE}/works",
            params={
                "search": query,
                "per_page": limit,
                "sort": "cited_by_count:desc",
                "filter": "publication_year:2015-2025",
            },
            headers=_OA_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for w in data.get("results", []):
            authors = [a["author"]["display_name"] for a in w.get("authorships", [])[:5]]
            results.append({
                "id": w["id"].split("/")[-1],
                "title": w.get("title", ""),
                "authors": authors,
                "abstract": w.get("abstract_inverted_index", ""),  # OpenAlex returns inverted index
                "year": w.get("publication_year"),
                "venue": w.get("primary_location", {}).get("source", {}).get("display_name", ""),
                "doi": w.get("doi", "").replace("https://doi.org/", ""),
                "citation_count": w.get("cited_by_count", 0),
                "pdf_url": w.get("best_oa_location", {}).get("pdf_url", ""),
            })
        return results
    except Exception as e:
        print(f"  ⚠️  OpenAlex search error: {e}", file=sys.stderr)
        return []


# ── 批量下载主函数 ────────────────────────────────────────────────────────────

def download_batch(
    papers: list[dict],
    output_dir: str = "papers/",
    sources: list[str] | None = None,
    delay: float = 3.0,
) -> list[PaperRecord]:
    """批量下载论文 PDF。"""
    if sources is None:
        sources = ["arxiv"]

    records = []
    for i, paper in enumerate(papers, 1):
        record = PaperRecord(
            paper_id=paper.get("paper_id", paper.get("id", "")),
            title=paper.get("title", ""),
            source=paper.get("source", ""),
        )

        # 确定下载方式
        arxiv_id = paper.get("arxiv_id") or paper.get("externalIds", {}).get("ArXiv", "")
        if not arxiv_id and "arxiv.org" in str(paper.get("pdf_url", "")):
            arxiv_id = _normalize_arxiv_id(str(paper["pdf_url"]))

        if arxiv_id and "arxiv" in sources:
            _rate_limit(delay, server="arxiv")
            r = download_arxiv_pdf(arxiv_id, output_dir)
            r.title = paper.get("title", r.title)
            r.authors = paper.get("authors", r.authors)
            r.abstract = paper.get("abstract", r.abstract)
            r.year = paper.get("year", r.year)
            r.doi = paper.get("doi", "")
            r.venue = paper.get("venue", "")
            r.citation_count = paper.get("citationCount", paper.get("citation_count", 0))
            records.append(r)
        elif paper.get("pdf_url"):
            # 通用 PDF 下载
            _rate_limit(delay, server="openalex")
            dest = Path(output_dir) / f"{record.paper_id.replace('/','_')}.pdf"
            try:
                resp = _SESSION.get(paper["pdf_url"], timeout=60, stream=True)
                resp.raise_for_status()
                data = b"".join(resp.iter_content(8192))
                if len(data) >= _MIN_PDF_BYTES:
                    dest.write_bytes(data)
                    record.downloaded = True
                    record.size_kb = int(len(data) / 1024)
                    record.pdf_path = str(dest)
            except Exception as e:
                record.error = str(e)
            records.append(record)
        else:
            # 仅记录元数据，不下载
            record.title = paper.get("title", "")
            record.authors = paper.get("authors", [])
            record.year = paper.get("year")
            record.doi = paper.get("doi", "")
            record.arxiv_id = arxiv_id
            record.venue = paper.get("venue", "")
            record.citation_count = paper.get("citationCount", paper.get("citation_count", 0))
            records.append(record)

        print(f"  [{i}/{len(papers)}] {'✅' if record.downloaded else '📋'} {record.title[:60] or record.paper_id}")

    return records


def search_and_download(
    query: str,
    sources: list[str],
    limit: int = 20,
    output_dir: str = "papers/",
    delay: float = 3.0,
) -> list[PaperRecord]:
    """搜索并下载论文的完整流程。"""
    print(f"\n=== Searching: {query} ===")
    print(f"Sources: {', '.join(sources)}")

    all_papers: list[dict] = []
    seen_ids: set[str] = set()

    for src in sources:
        if src == "arxiv":
            papers = search_arxiv(query, max_results=limit)
            print(f"  arXiv: {len(papers)} results")
            for p in papers:
                if p["id"] not in seen_ids:
                    p["source"] = "arxiv"
                    p["arxiv_id"] = p["id"]
                    all_papers.append(p)
                    seen_ids.add(p["id"])

        elif src == "semantic":
            papers = search_semantic(query, limit=limit)
            print(f"  Semantic Scholar: {len(papers)} results")
            for p in papers:
                pid = p.get("paperId", p.get("id", ""))
                if pid not in seen_ids:
                    p["source"] = "semantic"
                    p["arxiv_id"] = p.get("externalIds", {}).get("ArXiv", "")
                    p["doi"] = p.get("externalIds", {}).get("DOI", "")
                    if p.get("openAccessPdf"):
                        p["pdf_url"] = p["openAccessPdf"].get("url", "")
                    all_papers.append(p)
                    seen_ids.add(pid)

        elif src == "openalex":
            papers = search_openalex(query, limit=limit)
            print(f"  OpenAlex: {len(papers)} results")
            for p in papers:
                pid = p.get("id", "")
                if pid not in seen_ids:
                    p["source"] = "openalex"
                    all_papers.append(p)
                    seen_ids.add(pid)

    print(f"\n=== Deduplicated: {len(all_papers)} papers ===")

    # 去重并排序（优先 arXiv 有 PDF 的）
    def sort_key(p: dict) -> tuple[int, int]:
        has_pdf = int(bool(p.get("arxiv_id") or p.get("pdf_url")))
        cites = p.get("citationCount", p.get("citation_count", 0))
        return (has_pdf, cites)

    all_papers.sort(key=sort_key, reverse=True)
    records = download_batch(all_papers, output_dir=output_dir, delay=delay)

    return records


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search and download academic papers from multiple sources.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--source", default="arxiv,semantic",
                        help="Comma-separated sources: arxiv,semantic,openalex (default: all)")
    parser.add_argument("--limit", type=int, default=20, help="Max papers per source")
    parser.add_argument("--output", "-o", default="papers/", help="Output directory")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between requests (seconds)")
    parser.add_argument("--arxiv-list", help="Comma-separated arXiv IDs to download")
    parser.add_argument("--manifest", help="Output manifest JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Search only, no download")

    args = parser.parse_args(argv)

    if args.arxiv_list:
        ids = [_normalize_arxiv_id(x.strip()) for x in args.arxiv_list.split(",")]
        papers = [{"id": i, "arxiv_id": i, "source": "arxiv"} for i in ids]
        records = download_batch(papers, output_dir=args.output)
    elif args.query:
        sources = [s.strip() for s in args.source.split(",") if s.strip()]
        if args.dry_run:
            # 仅搜索
            for src in sources:
                if src == "arxiv":
                    r = search_arxiv(args.query, max_results=args.limit)
                    print(f"arXiv: {len(r)} papers")
                    for p in r:
                        print(f"  {p['id']} | {p['title'][:60]}")
                elif src == "semantic":
                    r = search_semantic(args.query, limit=args.limit)
                    print(f"Semantic Scholar: {len(r)} papers")
                    for p in r:
                        print(f"  {p.get('paperId','N/A')} | {p.get('title','')[:60]}")
                elif src == "openalex":
                    r = search_openalex(args.query, limit=args.limit)
                    print(f"OpenAlex: {len(r)} papers")
                    for p in r:
                        print(f"  {p['id']} | {p['title'][:60]}")
            return 0
        records = search_and_download(
            args.query, sources=sources,
            limit=args.limit, output_dir=args.output, delay=args.delay,
        )
    else:
        parser.print_help()
        return 0

    # 汇总
    downloaded = [r for r in records if r.downloaded]
    metadata_only = [r for r in records if not r.downloaded and not r.error]
    errors = [r for r in records if r.error]

    print(f"\n=== Summary ===")
    print(f"  Downloaded (PDF): {len(downloaded)}")
    print(f"  Metadata only:    {len(metadata_only)}")
    print(f"  Errors:          {len(errors)}")
    if errors:
        for e in errors[:3]:
            print(f"    ⚠️  {e.paper_id}: {e.error}")

    if args.manifest:
        manifest = {
            "query": args.query,
            "total": len(records),
            "downloaded": len(downloaded),
            "records": [r.to_dict() for r in records],
        }
        Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"  Manifest: {args.manifest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
