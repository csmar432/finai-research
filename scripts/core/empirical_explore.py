"""Official empirical exploration helpers (reuse FinAI estimators; no parallel stack).

Motivation (test-user audit): agents freestyled ``run_real_*.py`` because the
official path was thin (demo panel + one DID + six hand-picked robustness
tests) while still telling them not to invent a second stack.

This module:
  1. Loads panels with redundancy: local empirical root → optional path → caller
  2. Explores multiple *existing* ModernDiDEngine estimators (fail soft per method)
  3. Does NOT invent coefficients, Mock panels, or proxy outcomes
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

__all__ = [
    "PanelLoadResult",
    "ExploreReport",
    "load_panel_redundant",
    "explore_did_suite",
    "topic_local_keywords",
]

_log = logging.getLogger("empirical_explore")

# Estimators that exist on ModernDiDEngine today (do not list advertised-but-missing sa/dCdH).
_SUITE_STANDARD: tuple[str, ...] = (
    "did_2x2",
    "parallel_trends_test",
    "bacon",
    "honest_did",
    "cs",
)
_SUITE_EXPLORE: tuple[str, ...] = _SUITE_STANDARD + (
    "bjs",
    "gardner",
    "event_study_data",
)


@dataclass
class PanelLoadResult:
    df: pd.DataFrame | None
    source: str  # local_empirical | path | empty
    path: str = ""
    tried: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.df is not None and not self.df.empty


@dataclass
class ExploreReport:
    results: dict[str, Any] = field(default_factory=dict)
    succeeded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    level: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "succeeded": list(self.succeeded),
            "skipped": list(self.skipped),
            "errors": dict(self.errors),
            "results": self.results,
        }


def topic_local_keywords(topic: str) -> list[str]:
    """Derive filesystem keywords from a research topic (CN/EN mix)."""
    text = (topic or "").strip()
    if not text:
        return []
    keys = [
        "绿色专利",
        "patent",
        "海关",
        "customs",
        "利差",
        "spread",
        "债券",
        "bond",
        "碳",
        "carbon",
        "esg",
        "panel",
        "面板",
        "did",
    ]
    hits = [k for k in keys if k.lower() in text.lower()]
    # Always include a few coarse tokens from the topic itself
    for tok in text.replace("，", " ").replace(",", " ").split():
        t = tok.strip()
        if len(t) >= 2:
            hits.append(t)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:24]


def load_panel_redundant(
    *,
    topic: str = "",
    panel_path: str | Path | None = None,
    keywords: list[str] | None = None,
    allow_empty: bool = True,
) -> PanelLoadResult:
    """Try local empirical root / explicit path. No Mock, no remote invent.

    Remote MCP/CLI remains the caller's job (enhanced_pipeline / UniversalDataFetcher).
    This function only hardens the *local redundancy* layer that agents skipped.
    """
    tried: list[str] = []
    keys = list(keywords or []) or topic_local_keywords(topic)

    if panel_path:
        p = Path(panel_path).expanduser()
        tried.append(f"path:{p}")
        if p.is_file():
            try:
                df = _read_table(p)
                if df is not None and not df.empty:
                    return PanelLoadResult(df=df, source="path", path=str(p), tried=tried)
            except Exception as exc:
                tried.append(f"path_err:{exc}")

    try:
        from scripts.core.empirical_data_root import (
            find_candidate_files,
            resolve_empirical_data_root,
        )
    except Exception as exc:
        return PanelLoadResult(
            df=None, source="empty", tried=tried, error=f"import failed: {exc}"
        )

    root = resolve_empirical_data_root()
    tried.append(f"root:{root.path}:{root.source}:available={root.available}")
    if root.available and keys:
        hits = find_candidate_files(keys, root)
        tried.append(f"hits:{len(hits)}")
        for hit in hits[:5]:
            try:
                df = _read_table(hit)
                if df is not None and not df.empty:
                    return PanelLoadResult(
                        df=df, source="local_empirical", path=str(hit), tried=tried
                    )
            except Exception as exc:
                tried.append(f"load_err:{hit.name}:{exc}")

    if allow_empty:
        return PanelLoadResult(df=None, source="empty", tried=tried, error="no local panel")
    raise FileNotFoundError(
        "No local panel under FINAI_EMPIRICAL_DATA_ROOT / --panel. "
        f"Tried: {tried}"
    )


def explore_did_suite(
    engine: Any,
    *,
    level: str = "standard",
    cluster_var: str | None = None,
) -> ExploreReport:
    """Run multiple ModernDiDEngine methods; each failure is recorded, not fatal.

    level:
      - standard: 2x2 + PT + Bacon + Honest + CS
      - explore:  standard + BJS + Gardner + event_study_data
    """
    names = list(_SUITE_EXPLORE if level == "explore" else _SUITE_STANDARD)
    report = ExploreReport(level=level)

    for name in names:
        fn = getattr(engine, name, None)
        if not callable(fn):
            report.skipped.append(name)
            report.errors[name] = "method missing on ModernDiDEngine"
            continue
        try:
            out = _call_estimator(fn, name, cluster_var=cluster_var)
            report.results[name] = out
            report.succeeded.append(name)
        except Exception as exc:
            report.skipped.append(name)
            report.errors[name] = str(exc)[:240]
            _log.info("[explore] %s skipped: %s", name, exc)

    return report


def _call_estimator(fn: Callable, name: str, *, cluster_var: str | None) -> Any:
    if name == "did_2x2":
        res = fn(cluster_var=cluster_var) if cluster_var else fn()
        return res.to_dict() if hasattr(res, "to_dict") else res
    if name == "parallel_trends_test":
        return fn()
    if name == "bacon":
        df = fn()
        if isinstance(df, pd.DataFrame):
            return df.to_dict("records") if not df.empty else {}
        return df
    if name == "honest_did":
        return fn(m=0.5)
    if name == "event_study_data":
        data = fn()
        if isinstance(data, pd.DataFrame):
            return data.to_dict("records") if not data.empty else {}
        return data
    # cs / bjs / gardner
    res = fn()
    return res.to_dict() if hasattr(res, "to_dict") else res


def _read_table(path: Path) -> pd.DataFrame | None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".dta":
        return pd.read_stata(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return None
