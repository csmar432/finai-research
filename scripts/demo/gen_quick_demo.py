#!/usr/bin/env python3
"""Generate the canonical, deterministic FinAI Quick Demo GIF.

This is a guided product preview, not a recorded research run. It deliberately
contains no citations, coefficients, or claims that could be mistaken for live
empirical output.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from count_assets import count_all  # noqa: E402

OUTPUT = PROJECT_ROOT / ".github" / "demo" / "demo.gif"
WIDTH, HEIGHT = 1200, 675
DISCLOSURE = "INTERFACE WALKTHROUGH · NO LIVE CLAIMS OR STATISTICAL RESULTS"
BG = "#10231c"
PANEL = "#173027"
PANEL_2 = "#1d3a30"
FG = "#f7f4eb"
SUB = "#b9c7bf"
DIM = "#82988b"
GREEN = "#49c08d"
BLUE = "#8ea7ff"
AMBER = "#e7b875"
RED = "#ef8f8f"
RULE = "#315044"

FONT_REGULAR = (
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)
FONT_BOLD = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
)
FONT_MONO = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
)


def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.ImageFont:
    candidates = FONT_MONO if mono else FONT_BOLD if bold else FONT_REGULAR
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, color: str = FG,
         *, bold: bool = False, mono: bool = False, anchor: str | None = None) -> None:
    draw.text(xy, value, fill=color, font=font(size, bold=bold, mono=mono), anchor=anchor)


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, outline: str = RULE,
         fill: str = PANEL, radius: int = 18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def pill(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: str = GREEN) -> int:
    label_font = font(13, bold=True, mono=True)
    width = int(draw.textlength(label, font=label_font)) + 30
    draw.rounded_rectangle((x, y, x + width, y + 32), radius=16, fill=PANEL_2, outline=color, width=1)
    draw.text((x + 15, y + 9), label, fill=color, font=label_font)
    return width


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = DIM) -> None:
    draw.line((*start, *end), fill=color, width=3)
    x, y = end
    draw.polygon(((x, y), (x - 10, y - 6), (x - 10, y + 6)), fill=color)


def base_frame(step: int, title: str, kicker: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.line((0, 104, WIDTH, 104), fill=RULE, width=2)
    draw.line((0, 624, WIDTH, 624), fill=RULE, width=2)

    draw.rounded_rectangle((48, 34, 82, 76), radius=5, outline=FG, width=4)
    draw.line((58, 48, 72, 48), fill=FG, width=3)
    draw.line((58, 58, 72, 58), fill=GREEN, width=3)
    text(draw, (98, 40), "FinAI", 23, bold=True)
    text(draw, (164, 46), "GUIDED PREVIEW", 11, GREEN, bold=True, mono=True)

    for index in range(5):
        x = 924 + index * 44
        active = index <= step
        draw.ellipse((x, 46, x + 12, 58), fill=GREEN if active else RULE)
        if index < 4:
            draw.line((x + 14, 52, x + 40, 52), fill=GREEN if index < step else RULE, width=2)

    text(draw, (52, 136), kicker.upper(), 12, GREEN, bold=True, mono=True)
    text(draw, (52, 164), title, 36, bold=True)
    text(draw, (52, 646), DISCLOSURE, 11, DIM, bold=True, mono=True)
    text(draw, (1148, 646), f"0{step + 1} / 05", 11, DIM, mono=True, anchor="ra")
    return image, draw


def scene_agent(reveal: int) -> Image.Image:
    image, draw = base_frame(
        0,
        "Start with the agent you already use",
        "compatible entry points · several hosts",
    )
    agents = (("Codex", "RECOMMENDED", GREEN), ("Cursor", "SUPPORTED", BLUE),
              ("Claude Code", "SUPPORTED", BLUE), ("API / Ollama", "OPTIONAL", AMBER))
    for index, (name, status, color) in enumerate(agents):
        x = 52 + index * 282
        card(draw, (x, 236, x + 250, 344), outline=color if index <= reveal else RULE)
        text(draw, (x + 20, 258), status, 10, color if index <= reveal else DIM, bold=True, mono=True)
        text(draw, (x + 20, 294), name, 22, FG if index <= reveal else DIM, bold=True)
    if reveal >= 1:
        card(draw, (52, 392, 1148, 538), fill="#0b211a")
        text(draw, (78, 418), "$", 16, GREEN, bold=True, mono=True)
        text(draw, (106, 418), "python scripts/start_research.py --topic", 16, SUB, mono=True)
        text(draw, (106, 451), '"Carbon trading and green innovation"', 17, FG, mono=True)
        text(draw, (78, 499), "Recommended: clarify the brief before execution", 14, GREEN, bold=True)
    return image


def scene_brief(reveal: int) -> Image.Image:
    image, draw = base_frame(1, "Clarify the research brief before execution", "human checkpoint")
    card(draw, (52, 228, 606, 546))
    text(draw, (80, 254), "RESEARCH BRIEF", 11, BLUE, bold=True, mono=True)
    fields = (("Question", "Does carbon trading affect green innovation?"),
              ("Unit", "Firm-year panel"), ("Identification", "Staggered policy adoption"),
              ("Evidence gap", "Exact firm-level outcomes still required"))
    for index, (label, value) in enumerate(fields[: reveal + 2]):
        y = 302 + index * 58
        text(draw, (80, y), label.upper(), 10, DIM, bold=True, mono=True)
        text(draw, (206, y - 4), value, 15, FG if index < 3 else AMBER)
    if reveal >= 1:
        card(draw, (642, 228, 1148, 390), outline=GREEN, fill=PANEL_2)
        text(draw, (672, 254), "CHECKPOINT", 11, GREEN, bold=True, mono=True)
        text(draw, (672, 294), "Review the actual brief", 24, bold=True)
        text(draw, (672, 332), "Approve · reject · revise with feedback", 14, SUB)
    if reveal >= 2:
        x = 642
        for label, color in (("research_profile.json", BLUE), ("HITL checkpoint", GREEN),
                             ("hard gaps recorded", AMBER)):
            x += pill(draw, x, 438, label, color) + 12
    return image


def scene_tracks(reveal: int) -> Image.Image:
    image, draw = base_frame(2, "One brief, two governed research tracks", "writing is not estimation")
    tracks = (
        ("WRITING TRACK", 228, BLUE, ("Evidence", "Draft", "Review")),
        ("EMPIRICAL TRACK", 406, GREEN, ("Design", "Data", "Estimate")),
    )
    for label, y, color, stages in tracks:
        text(draw, (52, y), label, 11, color, bold=True, mono=True)
        for index, stage in enumerate(stages):
            x = 210 + index * 220
            card(draw, (x, y - 20, x + 174, y + 76), outline=color if index <= reveal else RULE)
            text(draw, (x + 18, y + 14), stage, 17, FG if index <= reveal else DIM, bold=True)
            if index < 2:
                arrow(draw, (x + 178, y + 28), (x + 210, y + 28))
    if reveal >= 2:
        arrow(draw, (828, 256), (914, 340), BLUE)
        arrow(draw, (828, 434), (914, 350), GREEN)
        card(draw, (914, 282, 1148, 414), outline=AMBER, fill=PANEL_2)
        text(draw, (940, 308), "RESEARCH PACKAGE", 10, AMBER, bold=True, mono=True)
        text(draw, (940, 346), "LaTeX · figures", 17, bold=True)
        text(draw, (940, 376), "code · provenance", 15, SUB)
    return image


def scene_fail_closed(reveal: int) -> Image.Image:
    image, draw = base_frame(3, "Missing inputs stop visibly", "local data first · no silent mock")
    routes = (("0", "Local panel", GREEN), ("1", "Validated cache", BLUE),
              ("2", "MCP / official source", GREEN), ("STOP", "Gap ledger", RED))
    for index, (tag, label, color) in enumerate(routes):
        x = 52 + index * 282
        card(draw, (x, 246, x + 242, 350), outline=color if index <= reveal else RULE)
        text(draw, (x + 18, 267), tag, 10, color, bold=True, mono=True)
        text(draw, (x + 18, 304), label, 18, FG if index <= reveal else DIM, bold=True)
        if index < 3:
            arrow(draw, (x + 246, 298), (x + 272, 298))
    if reveal >= 1:
        card(draw, (52, 408, 1148, 534), fill=PANEL_2)
        outputs = (("FINAL.md", "what completed", GREEN),
                   ("SKIPPED_CONFIG.md", "what is missing", AMBER),
                   ("Mock", "explicit opt-in only", RED))
        for index, (name, desc, color) in enumerate(outputs):
            x = 84 + index * 352
            text(draw, (x, 438), name, 15, color, bold=True, mono=True)
            text(draw, (x, 474), desc, 14, SUB)
    return image


def scene_delivery(reveal: int) -> Image.Image:
    stats = count_all()
    image, draw = base_frame(4, "Deliver work that can show its work", "verifiable research package")
    artifacts = (("Manuscript", "LaTeX draft", BLUE), ("Evidence", "verified identifiers", GREEN),
                 ("Empirics", "code + diagnostics", GREEN), ("Ledger", "source → artifact", AMBER))
    for index, (name, desc, color) in enumerate(artifacts):
        x = 52 + (index % 2) * 300
        y = 232 + (index // 2) * 136
        card(draw, (x, y, x + 268, y + 108), outline=color if index <= reveal + 1 else RULE)
        text(draw, (x + 20, y + 24), name, 18, bold=True)
        text(draw, (x + 20, y + 62), desc, 13, color, mono=True)
    if reveal >= 1:
        card(draw, (686, 232, 1148, 476), fill=PANEL_2, outline=GREEN)
        text(draw, (716, 258), "CURRENT CAPABILITIES", 11, GREEN, bold=True, mono=True)
        values = ((stats["mcp_servers"]["total"], "DATA SOURCES"),
                  (stats["econometric_methods"], "METHOD MODULES"),
                  (stats["skills"], "AI SKILLS"),
                  (stats["journal_templates"]["total"], "JOURNALS"))
        for index, (value, label) in enumerate(values):
            x = 716 + (index % 2) * 214
            y = 316 + (index // 2) * 92
            text(draw, (x, y), str(value), 30, bold=True)
            text(draw, (x + 58, y + 10), label, 10, DIM, bold=True, mono=True)
    if reveal >= 2:
        text(draw, (52, 558), "Human review remains required before submission.", 16, AMBER, bold=True)
    return image


def build_frames() -> tuple[list[Image.Image], list[int]]:
    scenes = (scene_agent, scene_brief, scene_tracks, scene_fail_closed, scene_delivery)
    frames = [scene(reveal) for scene in scenes for reveal in range(3)]
    durations = [300, 300, 1000] * 4 + [300, 300, 1600]
    return frames, durations


def generate(output: Path = OUTPUT) -> Path:
    frames, durations = build_frames()
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    with Image.open(output) as rendered:
        assert rendered.size == (WIDTH, HEIGHT)
        assert rendered.n_frames == len(frames)
    return output


def main() -> int:
    output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUTPUT
    generated = generate(output)
    print(f"generated {generated.relative_to(PROJECT_ROOT) if generated.is_relative_to(PROJECT_ROOT) else generated}")
    print(f"{WIDTH}x{HEIGHT} · 15 frames · {generated.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
