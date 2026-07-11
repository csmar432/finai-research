#!/usr/bin/env python3
"""Render a multi-frame animated GIF from a raw terminal session dump.

Designed for academic research workflow demos:
- Academic color palette (cream paper-like background for tables,
  GitHub-dark for terminal lines)
- Color-coded lines by category (commands, headers, tables, MCP labels)
- CJK-capable fonts (macOS STHeiti / Hiragino / Windows MS YaHei / Linux Noto)
- Auto-sized frames so nothing is truncated
- Generous width (1100 px) for legibility

Usage:
    python scripts/demo/render_demo_gif_v4.py INPUT.txt OUTPUT.gif \\
        [width=1100] [fps=0.6] [frames=30]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# CJK-capable font preferences
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]


def pick_font(size: int = 14) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# Academic palette
BG_DARK = "#0d1117"     # terminal background
BG_PANEL = "#161b22"    # subtle panel
FG_TEXT = "#c9d1d9"     # default text
FG_DIM = "#8b949e"      # secondary text
FG_CMD = "#7ee787"      # command prompt green
FG_PASS = "#7ee787"     # success
FG_FAIL = "#ff7b72"     # fail
FG_HEAD = "#79c0ff"     # section headers (blue)
FG_ACCENT = "#d2a8ff"   # accent / annotation (purple)
FG_TABLE = "#f0883e"    # table headers (orange)
FG_DATA = "#a5d6ff"     # data rows (light blue)
FG_MCP = "#ffa657"      # MCP labels (warm orange)
FG_LINK = "#58a6ff"     # URL / link (blue)
BG_HIGHLIGHT = "#1f2937"  # highlight band

PADDING_X = 16
PADDING_Y = 12
LINE_HEIGHT = 17  # slightly tighter for academic density


def wrap_lines(raw: str, cols: int) -> list[str]:
    """Wrap lines at cols (UTF-8-aware)."""
    out: list[str] = []
    for line in raw.split("\n"):
        line = line.replace("\t", "    ")
        if len(line) <= cols:
            out.append(line)
            continue
        for i in range(0, len(line), cols):
            out.append(line[i : i + cols])
    return out


def classify(line: str) -> tuple[str, str]:
    """Return (color, optional_bg_color) for a line.

    color scheme:
      FG_CMD    - $ prompt / commands
      FG_PASS   - PASS, OK, checkmarks
      FG_FAIL   - FAIL, errors
      FG_HEAD   - section headers (╔, ║, ┌───, Stage)
      FG_ACCENT - annotations (›, →, 📊, 🎯)
      FG_TABLE  - table headers (===, ---, Variable, =)
      FG_DATA   - data rows
      FG_MCP    - MCP labels (› (a), (b), (c), etc.)
      FG_LINK   - URL links
      FG_DIM    - other secondary
      FG_TEXT   - default
    """
    # MCP label lines
    if line.startswith("› ") or "(a)" in line[:8] or "(b)" in line[:8] or "(c)" in line[:8]:
        return FG_MCP, ""
    # Section headers
    if line.startswith(("╔", "║", "╚", "┌", "│", "└", "┘", "┐")):
        return FG_HEAD, ""
    if line.startswith(("==", "--", "===")):
        return FG_TABLE, ""
    if line.startswith("Table ") or "Specification" in line or "Hypotheses" in line:
        return FG_ACCENT, ""
    if line.startswith("Notes:") or line.startswith("Title "):
        return FG_DIM, ""
    if line.startswith("$ "):
        return FG_CMD, ""
    if "PASS" in line or line.startswith("✓") or line.startswith("✅"):
        return FG_PASS, ""
    if "FAIL" in line or line.startswith("✗"):
        return FG_FAIL, ""
    if line.startswith("Stage "):
        return FG_HEAD, BG_HIGHLIGHT
    if line.startswith("›"):
        return FG_MCP, ""
    if line.startswith("→") or line.startswith("📊") or line.startswith("🎯"):
        return FG_ACCENT, ""
    if line.startswith("Variable") or line.startswith("Treat ") or "Post " in line[:6]:
        return FG_DATA, ""
    if "DGS" in line[:6] or "DGS1MO" in line or "DGS10" in line or "DGS30" in line:
        return FG_DATA, ""
    if "XOM " in line[:5] or "CVX " in line[:5] or "COP " in line[:5] or "SLB " in line[:5]:
        return FG_DATA, ""
    if "GDP growth" in line or "China" in line[:5] or "USA" in line[:5] or "Germany" in line[:7]:
        return FG_DATA, ""
    if "CIK=" in line or "10-K" in line or "10-Q" in line or "8-K" in line:
        return FG_DATA, ""
    if "cites)" in line or "matches=" in line:
        return FG_DATA, ""
    if "elapsed" in line:
        return FG_DIM, ""
    if "TODO" in line or "FIXME" in line:
        return FG_FAIL, ""
    return FG_TEXT, ""


def render(lines: list[str], width: int = 1100, font_size: int = 13) -> Image.Image:
    """Render one frame; auto-sizes height to fit ALL content."""
    font = pick_font(font_size)
    char_w = max(6, int(font_size * 0.6))
    cols = max(60, (width - 2 * PADDING_X) // char_w)
    wrapped = wrap_lines("\n".join(lines), cols)

    total_h = PADDING_Y * 2 + len(wrapped) * LINE_HEIGHT
    img = Image.new("RGB", (width, total_h), BG_DARK)
    d = ImageDraw.Draw(img)

    # Top border bar
    d.rectangle([0, 0, width, 3], fill=FG_HEAD)

    y = PADDING_Y
    for i, line in enumerate(wrapped):
        color, bg = classify(line)
        if bg:
            d.rectangle([0, y - 2, width, y + LINE_HEIGHT - 2], fill=bg)
        # Truncate at cols
        text = line[:cols]
        d.text((PADDING_X, y), text, font=font, fill=color)
        y += LINE_HEIGHT

    return img


def chunk_text(raw: str, n_chunks: int = 30, overlap: int = 3) -> list[str]:
    """Split raw text into ~n_chunks windows of lines, with overlap so
    consecutive frames share a few lines (smooth scroll)."""
    lines = raw.split("\n")
    if len(lines) <= n_chunks:
        # Pad with last line
        return lines + [lines[-1] if lines else ""] * max(0, n_chunks - len(lines))

    chunk_size = max(1, (len(lines) - overlap) // n_chunks)
    chunks: list[str] = []
    for i in range(n_chunks):
        start = i * chunk_size
        end = min(start + chunk_size + overlap, len(lines))
        chunks.append("\n".join(lines[start:end]))
    # Append final chunk that reaches the end
    if chunks and chunks[-1].split("\n")[-1] != lines[-1]:
        chunks.append("\n".join(lines[-(chunk_size + overlap):]))
    return chunks


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    txt_path = Path(sys.argv[1])
    gif_path = Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1100
    fps_str = sys.argv[4] if len(sys.argv) > 4 else "0.7"
    n_frames = int(sys.argv[5]) if len(sys.argv) > 5 else 30

    raw = txt_path.read_text(encoding="utf-8")
    chunks = chunk_text(raw, n_chunks=n_frames, overlap=3)
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
        optimize=False,
    )
    size = gif_path.stat().st_size
    h = images[0].size[1]
    print(f"  ✓ {gif_path}")
    print(f"    frames: {len(images)}")
    print(f"    each:   {width}x{h}")
    print(f"    duration: {duration_ms}ms × {len(images)} = "
          f"{duration_ms * len(images) / 1000:.1f}s")
    print(f"    size:   {size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
