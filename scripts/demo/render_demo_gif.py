#!/usr/bin/env python3
"""Generate a static-state terminal GIF using PIL ImageDraw.

This is a fallback when asciinema → agg → gif is unavailable.
We render the terminal screen (100x30, 800x600 output) as a static
animated GIF by drawing the captured stdout at timed intervals.

Usage:
    python scripts/demo/render_demo_gif.py /tmp/demo_full_raw.txt /tmp/demo_full.gif
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Find a monospace font installed on macOS
FONT_PATHS = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFMono-Regular.otf",
    "/Library/Fonts/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Courier.dfont",
]


def get_font(size: int = 14):
    for p in FONT_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_lines(raw: str, cols: int = 100) -> list[str]:
    out: list[str] = []
    for line in raw.split("\n"):
        if len(line) <= cols:
            out.append(line)
            continue
        # simple wrap by char count
        for i in range(0, len(line), cols):
            out.append(line[i:i + cols])
    return out


def render(lines: list[str], w: int = 800, h: int = 600, row_h: int = 18) -> Image.Image:
    cols = max(1, int(w // (row_h * 0.6)))
    full = "\n".join(lines)
    wrapped = wrap_lines(full, cols)

    img = Image.new("RGB", (w, h), "black")
    d = ImageDraw.Draw(img)
    font = get_font(14)

    max_rows = (h // row_h) - 1
    d.text((6, 6), "$ bash — FinAI Research Workflow v0.2.0-alpha", font=font, fill="white")

    y = row_h
    for idx, line in enumerate(wrapped[:max_rows]):
        # truncate manually using int cols
        truncated = line[: max(1, cols - 1)]
        d.text((6, y), truncated, font=font, fill="#9ee9ff")
        y += row_h
    return img


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    txt_path = Path(sys.argv[1])
    gif_path = Path(sys.argv[2])

    raw = txt_path.read_text()
    # Build 8 progressively-revealing frames to add motion
    # Each frame hides (paint black bar) lines not yet revealed, simulating
    # the CLI commands scrolling into view.
    all_lines = raw.split("\n")
    total_lines = len(all_lines)
    chunk = max(1, total_lines // 8)
    progress_lines: list[list[str]] = []
    for i in range(1, 9):
        slice_ = all_lines[: i * chunk]
        progress_lines.append(slice_)

    images = [render(li, w=800, h=600) for li in progress_lines]
    if not images:
        images = [render(all_lines)]

    gif_path.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(
        gif_path,
        save_all=True,
        append_images=images[:-1] if len(images) > 1 else [],
        duration=800,  # 0.8s per frame → ~6.4s total for 8 frames
        loop=0,
        optimize=True,
    )
    print(f"  ✓ wrote {gif_path} ({gif_path.stat().st_size} bytes, {len(images)} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
