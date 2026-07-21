#!/usr/bin/env python3
"""Render a Chinese-font-capable multi-frame animated GIF from raw
terminal session output.

Usage:
    python scripts/demo/render_demo_gif_v3.py INPUT.txt OUTPUT.gif \\
        [width=900] [fps=0.8] [frames=24]

Features:
- Splits INPUT into N chunks; each chunk becomes one frame.
- Uses STHeiti Medium or Hiragino Sans GB for proper Chinese rendering.
- Auto-paginates long lines (wraps at column boundary).
- Configurable frame width (default 900 px = 100 columns × ~9 px).
- Outputs GIF89a with loop=0 (infinite loop).
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Font preferences (CJK-capable)
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Songti.ttc",
    "/System/Library/Fonts/CJKSymbolsFallback.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]


def pick_font(size: int = 14) -> ImageFont.FreeTypeFont:
    """Pick the first available CJK-capable font."""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_lines(raw: str, cols: int) -> list[str]:
    """Wrap lines exceeding cols (UTF-8-aware by character count)."""
    out: list[str] = []
    for line in raw.split("\n"):
        # Replace tabs with 4 spaces for consistent width
        line = line.replace("\t", "    ")
        if len(line) <= cols:
            out.append(line)
            continue
        # Wrap by char count (no sub-word since terminal output is already
        # formatted). Each CJK char is one column; ASCII also one column
        # in monospace.
        for i in range(0, len(line), cols):
            out.append(line[i : i + cols])
    return out


def render(
    lines: list[str],
    width: int = 900,
    row_h: int = 16,
    font_size: int = 13,
    title: str | None = None,
) -> Image.Image:
    """Render one frame at `width` × `auto_height`.

    The auto_height ensures ALL lines are visible — we don't truncate
    when more lines than rows would be needed.
    """
    font = pick_font(font_size)
    # Determine cols from width (each char ~ 7 px at size 13)
    char_w = max(6, int(font_size * 0.55))
    cols = max(40, width // char_w)

    wrapped = wrap_lines("\n".join(lines), cols)

    # Add title bar
    if title:
        wrapped = [title] + [""] + wrapped

    # Calculate height based on actual rows needed (NO truncation)
    max_rows = len(wrapped)
    h = (max_rows + 2) * row_h
    img = Image.new("RGB", (width, h), "#0d1117")  # GitHub dark bg
    d = ImageDraw.Draw(img)

    y = 6
    for i, line in enumerate(wrapped):
        color = "#c9d1d9"  # default text
        if line.startswith("$ "):
            color = "#7ee787"  # command prompt green
        elif line.startswith("✓") or "PASS" in line or "✅" in line:
            color = "#7ee787"  # green for success
        elif line.startswith("✗") or "FAIL" in line:
            color = "#ff7b72"
        elif line.startswith(("━", "Stage", "━━━━")):
            color = "#79c0ff"  # blue header
        elif "→" in line or "📊" in line or "🎯" in line or "📐" in line:
            color = "#d2a8ff"  # purple for annotations
        elif "Variable" in line or "==" in line or "---" in line:
            color = "#f0883e"  # orange for table headers
        elif "firm" in line.lower() and ("leverage" in line.lower() or "esg" in line.lower()):
            color = "#a5d6ff"  # light blue for data rows
        d.text((6, y), line[:cols], font=font, fill=color)
        y += row_h

    return img


def chunk_text(raw: str, n_chunks: int = 24) -> list[str]:
    """Split raw text into n_chunks parts preserving line boundaries.
    Each chunk is roughly the same height; we use overlapping windows so
    the GIF scrolls through content smoothly (last lines stay visible
    across consecutive frames)."""
    lines = raw.split("\n")
    if len(lines) <= n_chunks:
        # If fewer than n_chunks lines, repeat last to pad
        return lines + [lines[-1] if lines else ""] * max(0, n_chunks - len(lines))

    chunk_size = max(1, len(lines) // n_chunks)
    chunks: list[str] = []
    for i in range(n_chunks):
        # Each chunk = lines from i*chunk_size to i*chunk_size + (chunk_size + 2)
        start = i * chunk_size
        end = min(start + chunk_size + 2, len(lines))
        chunks.append("\n".join(lines[start:end]))
    return chunks


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    txt_path = Path(sys.argv[1])
    gif_path = Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    fps_str = sys.argv[4] if len(sys.argv) > 4 else "0.8"
    n_frames = int(sys.argv[5]) if len(sys.argv) > 5 else 24

    raw = txt_path.read_text(encoding="utf-8")
    chunks = chunk_text(raw, n_chunks=n_frames)
    images = [render(chunk.split("\n"), width=width, font_size=13) for chunk in chunks]

    if not images:
        return 1

    duration_ms = int(1000 / float(fps_str))
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,  # optimize can corrupt CJK fonts
    )
    size = gif_path.stat().st_size
    print(f"  ✓ wrote {gif_path}")
    print(f"    size:   {size} bytes ({size/1024:.1f} KB)")
    print(f"    frames: {len(images)}")
    print(f"    each:   {images[0].size[0]}×{images[0].size[1]}")
    print(f"    loop:   {duration_ms} ms × {len(images)} = "
          f"{duration_ms * len(images) / 1000:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
