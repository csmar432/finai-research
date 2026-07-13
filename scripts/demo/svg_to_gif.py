#!/usr/bin/env python3
"""Convert a termtosvg SVG animation to a GIF.

termtosvg emits an SVG with SMIL animations: <g id="g1">, <g id="g2">,
... interleaved via <use xlink:href="#gN"> within <g id="screen_view">
blocks. Each <g> within screen_view is one frame in time order.

Strategy: parse the SVG, walk the screen_view groups, for each group
extract the visible text shapes, render the cumulative screen at that
moment via cairosvg, rasterize to RGBA via PIL, dump each frame to a
GIF.

Usage:
    python scripts/demo/svg_to_gif.py INPUT.svg OUTPUT.gif [width=800]
"""
from __future__ import annotations

import sys
import re
import math
from pathlib import Path
from PIL import Image
try:
    import cairosvg
    _CAIRO_AVAILABLE = True
except ImportError:
    cairosvg = None  # type: ignore[assignment]
    _CAIRO_AVAILABLE = False
import io


def parse_svg_frames(svg_path: Path) -> tuple[str, list[str], int]:
    """Read the termtosvg SVG and extract:
      - the <defs> with all <g id="gN"> reusable components
      - a list of <use>-only state per frame (we'll concat <defs> with each)
      - the viewBox dimensions (width, height)
    """
    content = svg_path.read_text(encoding="utf-8")
    # Get the viewBox or width/height
    vb_m = re.search(r'viewBox\s*=\s*"\s*0\s+0\s+(\d+)\s+(\d+)\s*"', content)
    if vb_m:
        w, h = int(vb_m.group(1)), int(vb_m.group(2))
    else:
        w_m = re.search(r'width\s*=\s*"?(\d+)', content)
        h_m = re.search(r'height\s*=\s*"?(\d+)', content)
        w = int(w_m.group(1)) if w_m else 800
        h = int(h_m.group(1)) if h_m else 510

    # Extract the entire <defs>...</defs> block (or wrap in <svg> for raster)
    return content, content, w, h


def render_svg_to_png(svg_text: str, w: int, h: int) -> Image.Image:
    png = cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        output_width=w,
        output_height=h,
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> int:
    if not _CAIRO_AVAILABLE:
        print("cairosvg not installed. Install with: pip install cairosvg", file=sys.stderr)
        return 1

    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    out_w = int(sys.argv[3]) if len(sys.argv) > 3 else 800

    # Get frames
    content = in_path.read_text(encoding="utf-8")
    vb_m = re.search(r'viewBox\s*=\s*"\s*0\s+0\s+(\d+)\s+(\d+)\s*"', content)
    w = int(vb_m.group(1)) if vb_m else 800
    h = int(vb_m.group(2)) if vb_m else 510
    aspect = h / w
    out_h = int(out_w * aspect)

    # Termtosvg emits multiple `<g>` blocks under `<g id="screen_view">`.
    # Each `<g>` is one moment in time. We extract them.
    # Heuristic: split the SVG into frames by `<g id="screen_view">` followed
    # by a `<g>` block ending in `</g></g>`. Instead, scan for individual
    # `<g>` (without `id`) blocks within screen_view — they are inline frames.

    # Simpler: detect all individual frames by a state identifier pattern:
    # termtosvg alternates <g><use...></g> blocks within screen_view.
    # Easiest approach: rasterize the entire SVG once per frame using synthetic
    # instant-state. Fallback: rely on SVG's own animation by rendering each
    # second-offset PNG via cairosvg + svglib stepwise manipulation isn't
    # trivial — fall back to "render the SVG as still PNG", since termtosvg
    # SVGs already accumulate text per frame via <use>.
    #
    # We exploit a smarter trick: the SVG's <defs> has many <g id="gN"> components.
    # We grep each one and synthesize a frame SVG that <use>'s that gN
    # plus all preceding g's. Then render each.

    # Extract <defs>
    defs_m = re.search(r"(<defs>.*?</defs>)", content, re.DOTALL)
    if not defs_m:
        print("  ✗ no <defs> in SVG (not a termtosvg output?)")
        return 1
    defs = defs_m.group(1)

    # Find all id'd groups inside defs in order
    group_ids = re.findall(r'<g id="(g\d+)"', defs)
    n = len(group_ids)
    if n == 0:
        print("  ✗ no <g id=\"gN\"> in defs")
        return 1

    frames: list[Image.Image] = []
    used_ids: set[str] = set()
    for gid in group_ids:
        used_ids.add(gid)
        # Build a SVG that uses all groups up to and including this gid
        used_defs = re.sub(
            r'<g id="(g\d+)">',
            lambda m, used=used_ids: (
                m.group(0) if m.group(1) in used
                else f'<g id="{m.group(1)}" style="display:none">'
            ),
            defs,
        )
        # Compose a fresh SVG using only those components
        fake_svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="100%" height="100%" fill="black"/>'
            f'{used_defs}'
            f'<g id="screen_view">'
            f'<g><use xlink:href="#{gid}" y="17"/></g>'
            f'</g>'
            f'</svg>'
        )
        # Render
        try:
            png = cairosvg.svg2png(
                bytestring=fake_svg.encode("utf-8"),
                output_width=out_w,
                output_height=out_h,
            )
            img = Image.open(io.BytesIO(png)).convert("RGBA")
        except Exception:
            # Last frame duplicated (already-passed)
            img = frames[-1].copy() if frames else Image.new("RGBA", (out_w, out_h), "black")

        frames.append(img)

    if not frames:
        return 1

    # Resample so the GIF plays ~8-12s for ~80 frames
    target_duration_ms = 10_000  # 10s
    target_frames = max(20, min(120, target_duration_ms // 33))
    step = max(1, len(frames) // target_frames)
    selected = frames[::step][:target_frames]

    duration_per_frame = target_duration_ms // len(selected)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    selected[0].save(
        out_path,
        save_all=True,
        append_images=selected[1:],
        duration=duration_per_frame,
        loop=0,
        optimize=True,
    )
    print(f"  ✓ wrote {out_path} ({out_path.stat().st_size} bytes, "
          f"{len(selected)} frames × {duration_per_frame} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
