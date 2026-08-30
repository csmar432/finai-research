"""Generate FinAI's canonical 1280×640 social preview with native SVG."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from count_assets import count_all  # noqa: E402

BG = "#10231c"
FG = "#f7f4eb"
SUB = "#b9c7bf"
ACCENT1 = "#49c08d"
ACCENT2 = "#8ea7ff"
ACCENT3 = "#e7b875"
FONT = "'Inter','SF Pro Display','Segoe UI',system-ui,sans-serif"
MONO = "'SF Mono','JetBrains Mono','Cascadia Code',monospace"

SVG_OUTPUTS = (
    PROJECT_ROOT / "docs/assets/social-preview.svg",
    PROJECT_ROOT / "docs/assets/social-preview-1280x640.svg",
)
SQUARE_SVG_OUTPUT = PROJECT_ROOT / "docs/assets/social-preview-800x800.svg"
OUTPUTS = (
    PROJECT_ROOT / ".github/social-preview.png",
    PROJECT_ROOT / "docs/assets/social-preview.png",
    PROJECT_ROOT / "docs/assets/social-preview-1280x640.png",
)
SQUARE_OUTPUT = PROJECT_ROOT / "docs/assets/social-preview-800x800.png"

stats = count_all()
mcp_total = stats["mcp_servers"]["total"]
methods_total = stats["econometric_methods"]
skills_total = stats["skills"]
jt_total = stats["journal_templates"]["total"]


def build_svg() -> str:
    stage_labels = ("DISCOVER", "DESIGN", "EVIDENCE", "ESTIMATE", "WRITE", "REVIEW")
    stages = []
    for index, label in enumerate(stage_labels):
        row, col = divmod(index, 2)
        x, y = 706 + col * 278, 188 + row * 76
        color = ACCENT1 if col == 0 else ACCENT2
        stages.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="12" font-weight="700" font-family="{MONO}">{index + 1:02d}</text>')
        stages.append(f'<text x="{x + 44}" y="{y}" fill="{FG}" font-size="16" font-weight="700" font-family="{FONT}">{label}</text>')

    stat_items = ((mcp_total, "DATA SOURCES"), (methods_total, "METHOD MODULES"),
                  (skills_total, "AI SKILLS"), (jt_total, "JOURNAL TEMPLATES"))
    stat_svg = []
    for index, (value, label) in enumerate(stat_items):
        row, col = divmod(index, 2)
        x, y = 706 + col * 278, 486 + row * 64
        stat_svg.append(f'<text x="{x}" y="{y}" fill="{FG}" font-size="26" font-weight="750" font-family="{FONT}">{value}</text>')
        stat_svg.append(f'<text x="{x + 52}" y="{y}" fill="#8ba095" font-size="10" font-weight="700" font-family="{MONO}">{label}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" role="img" aria-labelledby="title desc">
  <title id="title">FinAI Research Workflow</title><desc id="desc">Research that can show its work.</desc>
  <rect width="1280" height="640" fill="{BG}"/>
  <path d="M660 0V640M0 536H1280M660 112H1280M968 0V640" stroke="#29473c"/>
  <g transform="translate(72 60)" fill="none" stroke="{FG}" stroke-width="8" stroke-linejoin="round"><rect width="58" height="72" rx="6"/><path d="M15 24h29M15 41h25"/><path d="M15 57h29" stroke="{ACCENT1}"/></g>
  <text x="151" y="92" fill="{FG}" font-size="22" font-weight="750" font-family="{FONT}">FinAI</text>
  <text x="218" y="92" fill="{ACCENT1}" font-size="11" font-weight="700" font-family="{MONO}">RESEARCH WORKFLOW</text>
  <text x="72" y="230" fill="{FG}" font-size="52" font-weight="760" font-family="{FONT}">Research that</text>
  <text x="72" y="290" fill="{FG}" font-size="52" font-weight="760" font-family="{FONT}">can show its work.</text>
  <text x="74" y="356" fill="{SUB}" font-size="17" font-family="{FONT}">Evidence-first infrastructure for empirical economics</text>
  <text x="74" y="382" fill="{SUB}" font-size="17" font-family="{FONT}">and finance — from question to defensible manuscript.</text>
  <text x="74" y="466" fill="{ACCENT1}" font-size="11" font-weight="700" font-family="{MONO}">LOCAL DATA FIRST</text>
  <text x="232" y="466" fill="{ACCENT2}" font-size="11" font-weight="700" font-family="{MONO}">HUMAN CHECKPOINTS</text>
  <text x="436" y="466" fill="{ACCENT3}" font-size="11" font-weight="700" font-family="{MONO}">NO SILENT MOCK</text>
  <text x="72" y="584" fill="#82988b" font-size="12" font-family="{MONO}">github.com/csmar432/finai-research</text>
  <text x="706" y="76" fill="#8ba095" font-size="11" font-weight="700" font-family="{MONO}">ONE GOVERNED RESEARCH SYSTEM</text>
  {''.join(stages)}
  <path d="M706 414H1216" stroke="#29473c"/>
  {''.join(stat_svg)}
</svg>\n'''


def build_square_svg() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" role="img" aria-labelledby="title desc">
  <title id="title">FinAI Research Workflow</title><desc id="desc">Research that can show its work.</desc>
  <rect width="800" height="800" fill="{BG}"/>
  <path d="M64 584H736M64 672H736" stroke="#29473c"/>
  <g transform="translate(64 62)" fill="none" stroke="{FG}" stroke-width="8" stroke-linejoin="round"><rect width="58" height="72" rx="6"/><path d="M15 24h29M15 41h25"/><path d="M15 57h29" stroke="{ACCENT1}"/></g>
  <text x="143" y="94" fill="{FG}" font-size="22" font-weight="750" font-family="{FONT}">FinAI</text>
  <text x="210" y="94" fill="{ACCENT1}" font-size="11" font-weight="700" font-family="{MONO}">RESEARCH WORKFLOW</text>
  <text x="64" y="238" fill="{FG}" font-size="55" font-weight="760" font-family="{FONT}">Research that</text>
  <text x="64" y="302" fill="{FG}" font-size="55" font-weight="760" font-family="{FONT}">can show its work.</text>
  <text x="66" y="370" fill="{SUB}" font-size="18" font-family="{FONT}">Evidence-first infrastructure for empirical</text>
  <text x="66" y="398" fill="{SUB}" font-size="18" font-family="{FONT}">economics and finance.</text>
  <text x="66" y="482" fill="{ACCENT1}" font-size="12" font-weight="700" font-family="{MONO}">LOCAL DATA FIRST</text>
  <text x="252" y="482" fill="{ACCENT2}" font-size="12" font-weight="700" font-family="{MONO}">HUMAN CHECKPOINTS</text>
  <text x="490" y="482" fill="{ACCENT3}" font-size="12" font-weight="700" font-family="{MONO}">NO SILENT MOCK</text>
  <g fill="{FG}" font-size="28" font-weight="750" font-family="{FONT}"><text x="66" y="638">{mcp_total}</text><text x="238" y="638">{methods_total}</text><text x="430" y="638">{skills_total}</text><text x="596" y="638">{jt_total}</text></g>
  <g fill="#8ba095" font-size="10" font-weight="700" font-family="{MONO}"><text x="66" y="706">DATA SOURCES</text><text x="238" y="706">METHOD MODULES</text><text x="430" y="706">AI SKILLS</text><text x="596" y="706">JOURNALS</text></g>
  <text x="66" y="760" fill="#82988b" font-size="12" font-family="{MONO}">github.com/csmar432/finai-research</text>
</svg>\n'''


def generate() -> tuple[Path, ...]:
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        raise RuntimeError("rsvg-convert is required (brew install librsvg)")
    svg = build_svg()
    for svg_output in SVG_OUTPUTS:
        svg_output.parent.mkdir(parents=True, exist_ok=True)
        svg_output.write_text(svg, encoding="utf-8")
    SQUARE_SVG_OUTPUT.write_text(build_square_svg(), encoding="utf-8")
    primary = OUTPUTS[0]
    primary.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([renderer, "-w", "1280", "-h", "640", str(SVG_OUTPUTS[0]), "-o", str(primary)], check=True)
    for target in OUTPUTS[1:]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(primary, target)
    subprocess.run([renderer, "-w", "800", "-h", "800", str(SQUARE_SVG_OUTPUT), "-o", str(SQUARE_OUTPUT)], check=True)
    return (*OUTPUTS, SQUARE_OUTPUT)


def main() -> None:
    outputs = generate()
    print("saved " + " + ".join(str(path.relative_to(PROJECT_ROOT)) for path in outputs))
    print(f"counts: MCP={mcp_total}, methods={methods_total}, skills={skills_total}, journals={jt_total}")


if __name__ == "__main__":
    main()
