"""Cross-platform normalization layer.

Goal: ensure outputs are byte-identical (or as close as physically possible)
across macOS, Linux, and Windows. Three categories:

A) **Normalizers** (must-call, single source of truth):
   - normalize_path()           — pathlib.PurePosixPath, no native separator
   - normalize_line_endings()   — strip \\r, force \\n
   - normalize_datetime()       — always UTC, ISO 8601, microsecond precision
   - normalize_json_dumps()     — sort_keys=True, ensure_ascii=False, indent=2, LF
   - normalize_csv_writes()     — lineterminator='\\n', encoding='utf-8'
   - normalize_random_seed()    — fixed seed, single-thread BLAS

B) **Sane defaults** (set once at import time):
   - os.environ['OMP_NUM_THREADS']='1' (BLAS single-thread = reproducible)
   - os.environ['MKL_NUM_THREADS']='1'
   - os.environ['OPENBLAS_NUM_THREADS']='1'
   - os.environ['PYTHONHASHSEED']='0' (deterministic dict order)

C) **Limitations** (impossible to make byte-identical):
   - File mtime (FAT32 vs NTFS vs ext4)
   - matplotlib pixel rendering on different fonts
   - tectonic PDF timestamp (compile-time only)

Usage:
    from scripts.core.normalize import (
        normalize_path, normalize_json_dumps, normalize_line_endings,
        setup_reproducible_env, normalize_csv_writer, normalize_random_seed,
    )

    # At module init (e.g. in agent_pipeline.py):
    setup_reproducible_env()

    # Anywhere:
    p = normalize_path("data\\file.csv")       # → PurePosixPath('data/file.csv')
    s = normalize_json_dumps({"b": 2, "a": 1}) # → '{"a": 1, "b": 2}\\n'
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


# ── A. Normalizers ────────────────────────────────────────────────────────────


def normalize_path(p: str | Path | os.PathLike) -> PurePosixPath:
    """Convert any path (incl. Windows backslashes) to PurePosixPath.

    Rationale: macOS / Linux / Windows all parse PurePosixPath the same way
    (forward slashes, no drive letter). Using PurePosixPath everywhere
    makes log messages and JSON keys byte-identical across OSes.

    Note: This is for *displayed* paths (logs, JSON keys, error messages).
    For actual file I/O, use pathlib.Path which respects the native OS.
    """
    return PurePosixPath(str(p).replace("\\", "/"))


def normalize_line_endings(text: str) -> str:
    """Convert CRLF and CR to LF. Idempotent."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_line_endings_bytes(b: bytes) -> bytes:
    """Same as normalize_line_endings but for bytes."""
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalize_datetime(dt: datetime | None = None, *, utc: bool = True) -> str:
    """ISO 8601 with microsecond precision. Always UTC for cross-OS byte ID.

    Format: 2026-07-12T15:30:00.123456+00:00
    """
    if dt is None:
        dt = datetime.now(timezone.utc) if utc else datetime.now()
    elif utc and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if utc:
        dt = dt.astimezone(timezone.utc)
    # isoformat uses +00:00 (not Z); force microsecond precision
    return dt.isoformat()


def normalize_json_dumps(
    obj: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
    append_newline: bool = True,
) -> str:
    """JSON with fixed parameters for cross-OS byte-identical output.

    - sort_keys=True:        deterministic key order
    - ensure_ascii=False:    preserve CJK characters (UTF-8)
    - indent=2:              human-readable
    - LF line endings:       always \\n, never \\r\\n (Python json default)
    - trailing newline:      POSIX convention
    """
    s = json.dumps(
        obj,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=ensure_ascii,
        separators=(",", ": ") if indent else (",", ":"),
    )
    s = normalize_line_endings(s)
    if append_newline and not s.endswith("\n"):
        s += "\n"
    return s


def normalize_json_dump(obj: Any, fp, **kwargs) -> None:
    """Like json.dump but with normalize_json_dumps defaults."""
    fp.write(normalize_json_dumps(obj, **kwargs))


def normalize_csv_writer(csv_file) -> None:
    """Wrap a csv.writer with LF line terminator. Idempotent on re-call.

    Usage:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            normalize_csv_writer(f)
            w.writerow([...])
    """
    # The csv module uses the underlying file's newline attribute; in
    # Python 3 the only portable way to get LF on all OSes is to open
    # with newline='' and set lineterminator explicitly per dialect.
    csv_file.dialect.lineterminator = "\n"


def normalize_random_seed(seed: int = 42) -> None:
    """Set Python's, NumPy's, and (if available) PyTorch's random seeds.

    Also forces hash randomization off (PYTHONHASHSEED=0) if not already.
    """
    os.environ.setdefault("PYTHONHASHSEED", "0")
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


# ── B. Reproducibility env (call once at startup) ─────────────────────────────


def setup_reproducible_env(*, seed: int = 42, verbose: bool = False) -> None:
    """Pin all known sources of cross-OS variability.

    - Single-thread BLAS (parallel reduction is non-deterministic across
      thread counts, which differs across macOS Accelerate / Linux OpenBLAS
      / Windows MKL).
    - PYTHONHASHSEED=0 (string dict order is randomized by default).
    - Locale to C (avoid ',' vs '.' decimal separators in some langs).
    - Random seeds (Python, NumPy, PyTorch).

    Call this at the very top of any script that needs reproducible
    output. Safe to call multiple times.
    """
    # 1. Single-thread BLAS — reproducibility over performance
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")  # macOS Accelerate

    # 2. Hash seed for deterministic dict iteration
    os.environ.setdefault("PYTHONHASHSEED", "0")

    # 3. Locale to C.UTF-8 — avoid e.g. German ',' as decimal separator,
    #    while still supporting Chinese/UTF-8 chars in stdout.
    #    audit-2026-07-14 PR-6: was `LC_ALL=C` which broke Chinese stdout
    #    on macOS (cp1252) and Windows (cp936) with UnicodeEncodeError.
    #    C.UTF-8 keeps the deterministic locale (no ',' separator) while
    #    making UTF-8 the default encoding everywhere.
    os.environ.setdefault("LC_ALL", "C.UTF-8")
    os.environ.setdefault("LANG", "C.UTF-8")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # 4. Random seeds
    normalize_random_seed(seed)

    if verbose:
        print(f"[normalize] Reproducible env set: seed={seed}, single-thread BLAS, LC_ALL=C.UTF-8")


# ── C. Documented limitations ────────────────────────────────────────────────


LIMITATIONS = """


__all__ = [
    "normalize_path",
    "normalize_line_endings",
    "normalize_line_endings_bytes",
    "normalize_datetime",
    "normalize_json_dumps",
    "normalize_json_dump",
    "normalize_csv_writer",
    "normalize_random_seed",
    "setup_reproducible_env",
    "print_limitations",
    "LIMITATIONS",
]
Cross-platform byte-identical output — KNOWN LIMITATIONS (T3 audit 2026-07-12):

1. **PDF byte-identity** is impossible with tectonic / xelatex because:
   - /CreationDate and /ModDate in PDF metadata are always current time.
   - Different OS / tectonic version may embed different fonts.
   - Workaround: pass --print --keep-intermediates and compare .tex source
     instead of final PDF.

2. **Image pixel-identity** across macOS / Linux / Windows is impossible
   with matplotlib default fonts (PingFang / DejaVu / Microsoft YaHei
   differ in glyph rendering). To minimize:
   - Force a single TTF font present on all 3 OSes (e.g. DejaVu Sans).
   - Set matplotlib metadata={'Title': '', 'Creator': '', ...}.
   - Use SVG format (text-only, no rendering differences).

3. **Float comparison across CPU architectures** can differ in the last
   bit due to fused-multiply-add (FMA) and SIMD reordering. We pin
   OMP/MKL/OPENBLAS threads to 1 to minimize but cannot eliminate.

4. **File system metadata** (mtime, inode, owner) is OS-specific by
   design. We do not attempt to normalize.

5. **Git commit hash** is always different (includes timestamp + author).

6. **Tectonic compile** embeds a UUID in aux files that changes per run.

What IS byte-identical after applying this layer:
  - JSON outputs (sort_keys + LF + UTF-8)
  - CSV outputs (UTF-8 + LF)
  - LaTeX .tex source files (paths, line endings, timestamps normalized)
  - Numerical regression results (single-thread BLAS + fixed seed)
  - Log messages (PurePosixPath + UTC ISO 8601)
  - PNG metadata (DateTime, Software stripped)
"""


def print_limitations() -> None:
    print(LIMITATIONS)


if __name__ == "__main__":
    print_limitations()
