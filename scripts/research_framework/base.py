"""
research_framework/base.py
Shared data types for the research framework.

This module provides shared enums and utility functions used across
research_framework components, preventing duplicate class definitions.

Contents:
- DataSource: Enum of all possible data source identifiers
- _stars(): Significance star annotation (p < 0.001 → ***, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import pandas as pd

# ─── Data Source Identifiers ──────────────────────────────────────────────────

class DataSource(str, Enum):
    """All possible data source identifiers (Enum + string mixin).

    Inherits from both str and Enum so that:
      - DataSource.MCP_YFINANCE == "mcp:yfinance"  (str comparison works)
      - DataSource.MCP_YFINANCE.value  (Enum access works)
      - Any module can use string literals without importing DataSource

    Canonical source strings:
      "mcp:yfinance"    — US stock data via MCP
      "mcp:finviz"     — US stock screening via MCP
      "mcp:eodhd"      — Macro/economic data via MCP
      "mcp:brave"      — Web search / literature via MCP
      "mcp:arxiv"      — Academic papers via MCP
      "mcp:user"       — User-provided file
      "mcp:tushare"    — A-share data via MCP
      "mcp:eastmoney"  — Chinese market data via MCP
      "fallback:proxy"  — Filled via proxy variable
      "simulated"       — Explicitly simulated data
      "manual"          — Manually entered data
    """
    MCP_YFINANCE    = "mcp:yfinance"
    MCP_FINVIZ      = "mcp:finviz"
    MCP_EODHD       = "mcp:eodhd"
    MCP_BRAVE       = "mcp:brave"
    MCP_ARXIV       = "mcp:arxiv"
    MCP_USER        = "mcp:user"
    MCP_TUSHARE     = "mcp:tushare"
    MCP_EASTMONEY   = "mcp:eastmoney"
    FALLBACK_PROXY  = "fallback:proxy"
    SIMULATED       = "simulated"
    MANUAL          = "manual"

    def __str__(self) -> str:
        return self.value


# ─── Provenance Tracker ──────────────────────────────────────────────────────

@dataclass
class DataProvenance:
    """Structured provenance record for a single data field."""
    field_name: str
    source: Any  # DataSource enum or string literal
    source_detail: str = ""
    is_simulated: bool = False
    is_fallback: bool = False
    timestamp: str = ""
    note: str = ""

    def __post_init__(self):
        if not self.timestamp:
            from datetime import datetime, timezone
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def flag_simulated(self, reason: str = "") -> "DataProvenance":
        return DataProvenance(
            field_name=self.field_name,
            source=DataSource.SIMULATED,
            source_detail=self.source_detail,
            is_simulated=True,
            is_fallback=self.is_fallback,
            timestamp=self.timestamp,
            note=reason or self.note,
        )

    def flag_fallback(self, method: str) -> "DataProvenance":
        return DataProvenance(
            field_name=self.field_name,
            source=DataSource.FALLBACK_PROXY,
            source_detail=self.source_detail,
            is_simulated=self.is_simulated,
            is_fallback=True,
            timestamp=self.timestamp,
            note=f"method={method}",
        )


class ProvenanceTracker:
    """Tracks the origin of every data field in the analysis.

    All three frameworks (pipeline.py, report_generator.py, data_fetcher.py)
    use this same class. Internal storage uses a dict of dataclass-like dicts
    for maximum compatibility.

    Usage:
        tracker = ProvenanceTracker()
        tracker.record("roa", DataSource.MCP_YFINANCE, "API response")
        tracker.flag_simulated("roa", "yfinance returned empty")
        tracker.record("leverage", DataSource.SIMULATED, "No data available")
        print(tracker.summary())
        tracker.save("output/provenance.json")
    """

    def __init__(self) -> None:
        self._r: dict = {}

    def record(self, field: str, source, detail: str = "",
               returned_fields: list[str] | None = None,
               **kwargs) -> None:
        """Record the source of a data field.

        Args:
            field: Field/variable name
            source: DataSource value or string literal (e.g., DataSource.MCP_YFINANCE)
            detail: Additional detail about the source
            returned_fields: Actual field/column names from the API response
            **kwargs: Extra metadata (e.g., method, url, date)
        """
        # Serialize source: Enum → string value for JSON compatibility
        src_val = source.value if hasattr(source, "value") else str(source)
        self._r[field] = dict(
            field_name=field,
            source=src_val,
            source_detail=detail,
            is_simulated=False,
            is_fallback=False,
            returned_fields=returned_fields or [],
            **kwargs,
        )

    def flag_simulated(self, field: str, reason: str = "") -> None:
        """Mark a field as simulated/fake data.

        v3 QUAL-2 enhancement: also write the simulated flag to df.attrs
        (when df is bound) so downstream RegressionEngine / RobustnessRunner
        can detect synthetic data via the standard pandas metadata channel.
        """
        if field in self._r:
            record = self._r[field]
            record["is_simulated"] = True
            record["note"] = reason
            # Ensure source is a string (not Enum) for JSON serialization
            src = record.get("source")
            record["source"] = src.value if hasattr(src, "value") else str(src)
        else:
            self._r[field] = dict(
                field_name=field,
                source=DataSource.SIMULATED.value,
                source_detail="",
                is_simulated=True,
                is_fallback=False,
                note=reason,
            )
        # Mirror to bound DataFrame's attrs (best-effort)
        df_bound = getattr(self, "_df", None)
        if df_bound is not None and hasattr(df_bound, "attrs"):
            existing = list(df_bound.attrs.get("simulated_vars", []))
            if field not in existing:
                existing.append(field)
            df_bound.attrs["simulated_vars"] = existing
            df_bound.attrs["is_simulated"] = True

    def flag_fallback(self, field: str, method: str = "") -> None:
        """Mark a field as filled via a fallback/proxy method."""
        if field in self._r:
            record = self._r[field]
            record["is_fallback"] = True
            record["note"] = f"method={method}"
            src = record.get("source")
            record["source"] = src.value if hasattr(src, "value") else str(src)
        else:
            self._r[field] = dict(
                field_name=field,
                source=DataSource.FALLBACK_PROXY.value,
                source_detail="",
                is_simulated=False,
                is_fallback=True,
                note=f"method={method}",
            )

    def summary(self) -> dict:
        """Return a summary dict of recorded sources."""
        counts: dict = {}
        for v in self._r.values():
            src = v.get("source", "unknown")
            # Handle both Enum (has .value) and plain string
            k = src.value if hasattr(src, "value") else str(src)
            counts[k] = counts.get(k, 0) + 1
        return dict(
            total_fields=len(self._r),
            by_source=counts,
            simulated=len(self.simulated_fields()),
            fallback=sum(1 for v in self._r.values() if v.get("is_fallback")),
        )

    def simulated_fields(self) -> list:
        """Return list of field names that are simulated."""
        return [k for k, v in self._r.items() if v.get("is_simulated")]

    def save(self, path: str | Path) -> None:
        """Save provenance records to JSON."""
        import json
        from pathlib import Path

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._r, f, ensure_ascii=False, indent=2)

    def get(self, key: str):
        """Get provenance record for a field."""
        return self._r.get(key)

    def __len__(self) -> int:
        return len(self._r)

    def __repr__(self) -> str:
        return f"ProvenanceTracker(fields={len(self._r)})"


# ─── Table Formatting Utilities ────────────────────────────────────────────────

def _stars(pval: float) -> str:
    """Return significance star markers for a p-value.

    Uses the standard academic convention:
      *** : p < 0.001
      **  : p < 0.01
      *   : p < 0.05
      †   : p < 0.10

    Args:
        pval: The p-value from a statistical test.

    Returns:
        LaTeX-formatted string of star markers.
    """
    if pval <= 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    if pval < 0.1:
        return r"$\dagger$"
    return ""


def fmt_coef(value: float, se: float, pval: float, stars: bool = True,
             prec: int = 3) -> str:
    """Format a regression coefficient with SE in parentheses and significance stars.

    Args:
        value: Coefficient estimate.
        se: Standard error.
        pval: Two-tailed p-value.
        stars: Whether to append significance stars.
        prec: Decimal precision for the coefficient.

    Returns:
        LaTeX-formatted string, e.g. "0.052\\*{(0.021)}"
    """
    marker = _stars(pval) if stars else ""
    return f"{value:.{prec}f}{marker} ({se:.{prec}f})"


def stars_for_stars(pval: float) -> str:
    """Alias for _stars() to avoid name collision when imported."""
    return _stars(pval)


def to_markdown_table(
    df: pd.DataFrame,
    headers: list[str] | None = None,
    float_fmt: str = "{:.3f}",
    stars_col: int | None = None,
) -> str:
    """Convert a DataFrame to a Markdown table string.

    Args:
        df: DataFrame to convert.
        headers: Optional column headers (defaults to df.columns).
        float_fmt: Format string for float columns.
        stars_col: Column index for significance stars (appends as bold text).

    Returns:
        Markdown table string.
    """
    if df.empty:
        return "_No data_"

    cols = headers if headers is not None else list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]

    for _, row in df.iterrows():
        cells = []
        for i, col in enumerate(cols):
            val = row[col] if col in df.columns else row.iloc[i if i < len(df.columns) else 0]
            if pd.isna(val):
                cells.append("—")
            elif isinstance(val, float):
                cells.append(float_fmt.format(val))
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def to_latex_table(
    df: pd.DataFrame,
    caption: str = "",
    label: str = "",
    notes: str = "",
    col_format: str | None = None,
    position: str = "htbp",
) -> str:
    """Convert a DataFrame to a LaTeX booktabs table string.

    Args:
        df: DataFrame to convert.
        caption: Table caption.
        label: LaTeX label (e.g., "tab:did").
        notes: Table notes (appended as tablenotes).
        col_format: Column format string (default: "l" + "c" * (n-1)).
        position: Table position float.

    Returns:
        LaTeX table string.
    """
    n = len(df.columns)
    fmt = col_format if col_format else "l" + "c" * (n - 1)

    parts = [
        "\\begin{table}[" + position + "]",
        "  \\centering",
        f"  \\caption{{{caption}}}" if caption else "",
        f"  \\label{{{label}}}" if label else "",
        "  \\begin{threeparttable}",
        f"  \\begin{{tabular}}{{{fmt}}}",
        "    \\toprule",
    ]

    header_cols = [f"\\textbf{{{c}}}" for c in df.columns]
    parts.append("    " + " & ".join(header_cols) + " \\\\")
    parts.append("    \\midrule")

    for _, row in df.iterrows():
        cells = []
        for val in row:
            if pd.isna(val):
                cells.append("—")
            elif isinstance(val, float):
                cells.append(f"{val:.3f}")
            else:
                cells.append(str(val))
        parts.append("    " + " & ".join(cells) + " \\\\")

    parts.extend([
        "    \\bottomrule",
        "  \\end{tabular}",
    ])

    if notes:
        parts.extend([
            "  \\begin{tablenotes}",
            "    \\small",
            f"    \\item {notes}",
            "  \\end{tablenotes}",
        ])

    parts.extend([
        "  \\end{threeparttable}",
        "\\end{table}",
    ])

    return "\n".join(parts)
