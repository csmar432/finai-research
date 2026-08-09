"""Generate FinAI's deterministic SVG visual system.

The architecture views are deliberately complementary. Supporting README assets
share the same design tokens so screenshots, counts, and safety claims do not
drift independently.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / ".github" / "demo"
ASSET_DIR = PROJECT_ROOT / "docs" / "assets"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from count_assets import count_all  # noqa: E402

STATS = count_all()
MCP_COUNT = STATS["mcp_servers"]["total"]
METHOD_COUNT = STATS["econometric_methods"]
SKILL_COUNT = STATS["skills"]
JOURNAL_COUNT = STATS["journal_templates"]["total"]
TEST_COUNT = STATS["tests"]["test_functions"]

WIDTH, HEIGHT = 1600, 900
BG = "#f7f5ef"
BG2 = "#efede5"
PANEL = "#ffffff"
PANEL2 = "#f2f0e9"
INK = "#10231c"
INK2 = "#4f6259"
INK3 = "#607168"
BORDER = "#d8d6cd"
BLUE = "#3659a2"
GREEN = "#0b7a53"
AMBER = "#a35b20"
PURPLE = "#71558b"
RED = "#a63f3f"
FLOW = "#829087"

COL_INTERFACE = (PANEL, BLUE)
COL_DATA = (PANEL, GREEN)
COL_PROCESS = (PANEL, AMBER)
COL_CONTROL = (PANEL, PURPLE)
COL_USER = (PANEL, RED)

FONT = "'Inter', 'SF Pro Text', 'Segoe UI', system-ui, -apple-system, sans-serif"
MONO = "'SF Mono', 'JetBrains Mono', 'Cascadia Code', monospace"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _version() -> str:
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
            return "v" + tomllib.load(handle).get("project", {}).get("version", "?")
    except Exception:
        return "v?"


def header(title: str, subtitle: str, version: str | None = None) -> str:
    version = version or _version()
    return f'''  <title id="title">{_esc(title)}</title>
  <desc id="desc">{_esc(subtitle)}</desc>
  <defs>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BG}"/>
      <stop offset="100%" stop-color="{BG2}"/>
    </linearGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#d8d6cd" stroke-width="1" opacity="0.30"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bgGrad)"/>
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <path d="M56 48h28v28H56z M63 55v14h14V55z" fill="{GREEN}" fill-rule="evenodd"/>
  <text x="104" y="68" fill="{INK}" font-size="31" font-weight="720" font-family="{FONT}">{_esc(title)}</text>
  <text x="104" y="98" fill="{INK2}" font-size="15" font-family="{FONT}">{_esc(subtitle)}</text>
  <text x="1544" y="65" fill="{INK2}" font-size="13" text-anchor="end" font-family="{MONO}">FinAI Research Workflow · {version}</text>
  <text x="1544" y="91" fill="{INK3}" font-size="11" text-anchor="end" font-family="{MONO}">evidence first · fail closed · human review</text>
  <line x1="56" y1="126" x2="1544" y2="126" stroke="{BORDER}"/>'''


def footer(index: int, total: int = 5) -> str:
    return f'''  <line x1="56" y1="850" x2="1544" y2="850" stroke="{BORDER}"/>
  <text x="56" y="878" fill="{INK3}" font-size="12" font-family="{MONO}">FIGURE {index:02d} / {total:02d} · github.com/csmar432/finai-research</text>
  <text x="1544" y="878" fill="{INK3}" font-size="12" text-anchor="end" font-family="{FONT}">MIT · 2026</text>'''


def node(
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    desc: str = "",
    col=COL_PROCESS,
    radius: int = 12,
    fontsize: int = 16,
) -> str:
    fill, accent = col
    title_y = y + h / 2 - (9 if desc else -5)
    desc_text = (
        f'<text x="{x + 22}" y="{title_y + 29}" fill="{INK2}" font-size="12.5" '
        f'font-family="{FONT}">{_esc(desc)}</text>'
        if desc
        else ""
    )
    return f'''  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{BORDER}" stroke-width="1.2"/>
    <rect x="{x}" y="{y}" width="5" height="{h}" rx="2.5" fill="{accent}"/>
    <text x="{x + 22}" y="{title_y}" fill="{INK}" font-size="{fontsize}" font-weight="680" font-family="{FONT}">{_esc(title)}</text>
    {desc_text}
  </g>'''


def arrow(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    label: str = "",
    color: str = FLOW,
    dashed: bool = False,
) -> str:
    marker = f"arrow-{x1}-{y1}-{x2}-{y2}".replace("-", "m", 1)
    dash = ' stroke-dasharray="6 6"' if dashed else ""
    label_svg = ""
    if label:
        label_svg = (
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 9}" fill="{INK3}" '
            f'font-size="11" text-anchor="middle" font-family="{MONO}">{_esc(label)}</text>'
        )
    return f'''  <g>
    <defs><marker id="{marker}" markerWidth="9" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0,0 L0,8 L8,4 z" fill="{color}"/></marker></defs>
    <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.6"{dash} marker-end="url(#{marker})"/>
    {label_svg}
  </g>'''


def section(x: int, y: int, w: int, h: int, label: str, color: str = BLUE) -> str:
    label_w = max(120, len(label) * 10 + 24)
    return f'''  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{PANEL}" stroke="{BORDER}" stroke-width="1.2"/>
    <rect x="{x + 16}" y="{y - 13}" width="{label_w}" height="26" rx="13" fill="{BG}" stroke="{color}"/>
    <text x="{x + 16 + label_w / 2}" y="{y + 5}" fill="{color}" font-size="12" font-weight="700" text-anchor="middle" font-family="{FONT}">{_esc(label)}</text>
  </g>'''


def pill(x: int, y: int, w: int, text: str, color: str) -> str:
    return f'''  <g>
    <rect x="{x}" y="{y}" width="{w}" height="34" rx="17" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-opacity="0.72"/>
    <text x="{x + w / 2}" y="{y + 22}" fill="{INK}" font-size="12" text-anchor="middle" font-family="{MONO}">{_esc(text)}</text>
  </g>'''


def wrap(text: str) -> str:
    return text


def _start() -> list[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">']


def _finish(parts: list[str], index: int) -> str:
    parts.append(footer(index, 9))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def gen_01_architecture_overview() -> str:
    parts = _start()
    parts.append(header("System architecture", "One research brief, two governed tracks, one auditable delivery contract"))

    parts.append(section(56, 176, 244, 584, "INPUTS", RED))
    parts.append(node(80, 214, 196, 86, "Research brief", "topic · venue · claims", COL_USER))
    parts.append(node(80, 326, 196, 86, "Host agent", "Codex · Claude Code · Cursor", COL_INTERFACE))
    parts.append(node(80, 438, 196, 86, "Local data root", "Layer 0 · panels first", COL_DATA))
    parts.append(node(80, 550, 196, 86, f"{MCP_COUNT} data sources", "provenance recorded", COL_DATA))
    parts.append(node(80, 662, 196, 64, "Human decisions", "HITL checkpoints", COL_CONTROL))

    parts.append(section(348, 176, 834, 260, "WRITING TRACK", BLUE))
    writing = (
        (380, "Clarify", "brief + hard gaps"),
        (634, "Evidence", "literature + novelty"),
        (888, "Draft", "outline + manuscript + review"),
    )
    for x, title, desc in writing:
        parts.append(node(x, 244, 216, 112, title, desc, COL_INTERFACE))
    parts.append(arrow(596, 300, 626, 300))
    parts.append(arrow(850, 300, 880, 300))

    parts.append(section(348, 500, 834, 260, "EMPIRICAL TRACK", GREEN))
    empirics = (
        (380, "Identification", "DID · IV · RD · GMM"),
        (634, "Data acquisition", "validated variables + lineage"),
        (888, "Estimation", "robustness + diagnostics"),
    )
    for x, title, desc in empirics:
        parts.append(node(x, 568, 216, 112, title, desc, COL_DATA))
    parts.append(arrow(596, 624, 626, 624))
    parts.append(arrow(850, 624, 880, 624))

    parts.append(section(1230, 176, 314, 584, "DELIVERY", AMBER))
    parts.append(node(1258, 228, 258, 88, "Research package", "LaTeX · PDF · figures", COL_PROCESS))
    parts.append(node(1258, 344, 258, 88, "FINAL.md", "user-facing completion", COL_PROCESS))
    parts.append(node(1258, 460, 258, 88, "SKIPPED_CONFIG.md", "hard gaps, never hidden", COL_CONTROL))
    parts.append(node(1258, 576, 258, 88, "Provenance ledger", "source · timestamp · transform", COL_DATA))
    parts.append(node(1258, 692, 258, 42, "No silent Mock", "", COL_CONTROL, fontsize=14))
    parts.append(arrow(1104, 300, 1250, 278, "writing"))
    parts.append(arrow(1104, 624, 1250, 620, "empirics"))
    parts.append(arrow(300, 470, 340, 470, "route"))
    return _finish(parts, 1)


def gen_02_skill_system_map() -> str:
    parts = _start()
    parts.append(header(f"{SKILL_COUNT} research skills", "A small set of composable capabilities organized by research phase"))
    groups = (
        ("DISCOVER", BLUE, ("fin-idea-discovery", "fin-generate-idea", "fin-lit-review", "fin-novelty-check")),
        ("DESIGN & DATA", GREEN, ("fin-brief-generator", "fin-experiment-design", "fin-data-acquisition", "fin-arch-diagram")),
        ("WRITE", AMBER, ("fin-paper-plan", "fin-paper-draft", "fin-paper-writing", "fin-paper-figure", "fin-viz-launch")),
        ("REVIEW & DELIVER", PURPLE, ("fin-review-loop", "fin-ref-paper", "fin-paper-convert", "fin-submit-check", "fin-full-pipeline")),
    )
    for index, (label, color, skills) in enumerate(groups):
        x = 56 + index * 382
        parts.append(section(x, 190, 354, 566, label, color))
        for row, skill in enumerate(skills):
            parts.append(node(x + 24, 230 + row * 92, 306, 68, skill, "", (PANEL2, color), fontsize=14))
        if index < 3:
            parts.append(arrow(x + 354, 472, x + 374, 472, color=color))
    parts.append(pill(488, 782, 624, "independent skills · one fin-full-pipeline orchestrator", BLUE))
    return _finish(parts, 2)


def gen_03_mcp_ecosystem_map() -> str:
    parts = _start()
    parts.append(header(f"Evidence acquisition · {MCP_COUNT} source directories", "Priority is explicit: local panels first, provenance always, failure visible"))
    layers = (
        (180, "LAYER 0", "Local empirical panels", "FINAI_EMPIRICAL_DATA_ROOT · exact variables", COL_USER),
        (312, "LAYER 1", "Validated cache", "schema · freshness · content hash", COL_INTERFACE),
        (444, "LAYER 2", f"{MCP_COUNT} MCP directories", "academic · China markets · global macro · filings", COL_DATA),
        (576, "LAYER 3+", "Official libraries and APIs", "only compatible, documented substitutions", COL_PROCESS),
        (708, "STOP", "Fail closed", "no proxy laundering · no silent synthetic data", COL_CONTROL),
    )
    for index, (y, tag, title, desc, color) in enumerate(layers):
        parts.append(pill(70, y + 26, 150, tag, color[1]))
        parts.append(node(250, y, 1020, 86, title, desc, color, fontsize=17))
        if index < len(layers) - 1:
            parts.append(arrow(760, y + 86, 760, layers[index + 1][0] - 10))

    parts.append(section(1310, 190, 234, 522, "SOURCE DOMAINS", GREEN))
    for row, (label, sub) in enumerate((
        ("Academic", "OpenAlex · ArXiv · NBER"),
        ("China", "Tushare · CSMAR · Wind"),
        ("Global", "SEC · yfinance · EODHD"),
        ("Macro", "FRED · WB · IMF · OECD"),
    )):
        parts.append(node(1332, 230 + row * 108, 190, 78, label, sub, COL_DATA, fontsize=14))
    parts.append(pill(1318, 738, 218, "Mock = explicit opt-in", RED))
    return _finish(parts, 3)


def gen_04_research_pipeline() -> str:
    parts = _start()
    parts.append(header("Research pipeline", "Eight research stages after preflight; HITL gates review real outputs"))
    stages = (
        ("0", "Health", "preflight", COL_CONTROL),
        ("1", "Idea", "question", COL_PROCESS),
        ("2", "Literature", "evidence map", COL_INTERFACE),
        ("3", "Novelty", "search gate", COL_INTERFACE),
        ("4", "Design", "identification", COL_DATA),
        ("5", "Data", "provenance", COL_DATA),
        ("6", "Analysis", "robustness", COL_DATA),
        ("7", "Draft", "LaTeX", COL_PROCESS),
        ("8", "Review", "adversarial", COL_CONTROL),
    )
    for index, (num, title, desc, color) in enumerate(stages):
        row, col = divmod(index, 5)
        x = 56 + col * 306
        y = 192 + row * 238
        parts.append(node(x, y, 266, 112, f"{num}  {title}", desc, color, fontsize=17))
        if col < 4 and index < len(stages) - 1:
            parts.append(arrow(x + 266, y + 56, x + 296, y + 56))
    parts.append(f'''  <g>
    <defs><marker id="pipeline-turn" markerWidth="9" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0,0 L0,8 L8,4 z" fill="{FLOW}"/></marker></defs>
    <path d="M1530 248 V382 Q1530 430 1482 430 H322" fill="none" stroke="{FLOW}" stroke-width="1.6" stroke-dasharray="6 6" marker-end="url(#pipeline-turn)"/>
    <text x="1498" y="338" fill="{INK3}" font-size="11" text-anchor="end" font-family="{MONO}">continue</text>
  </g>''')

    parts.append(section(56, 680, 1488, 118, "GOVERNANCE AT EVERY TRANSITION", PURPLE))
    controls = (
        (80, "Checkpoint", "approve or reject output"),
        (448, "Provenance", "source and transform recorded"),
        (816, "No silent fallback", "Mock requires explicit authorization"),
        (1184, "Dual-track hand-off", "writing ≠ empirical estimation"),
    )
    for x, title, desc in controls:
        parts.append(node(x, 710, 328, 62, title, desc, COL_CONTROL, fontsize=13))
    return _finish(parts, 4)


def gen_05_deployment_data_flow() -> str:
    parts = _start()
    parts.append(header("Execution and delivery", "Interactive research and isolated agent-host runs share the same governed core"))
    parts.append(section(56, 188, 312, 548, "ENTRY", BLUE))
    parts.append(node(82, 230, 260, 92, "Interactive", "start_research · HITL on", COL_INTERFACE))
    parts.append(node(82, 354, 260, 92, "Direct writing", "agent_pipeline · explicit gates", COL_INTERFACE))
    parts.append(node(82, 478, 260, 92, "Agent host", "non-interactive · fail closed", COL_CONTROL))
    parts.append(node(82, 602, 260, 92, "Topic integrity", "hard gaps recorded", COL_CONTROL))

    parts.append(section(418, 188, 402, 548, "GOVERNED CORE", AMBER))
    parts.append(node(446, 230, 346, 92, "Agent orchestrator", "routing · checkpoints · resume", COL_PROCESS))
    parts.append(node(446, 354, 346, 92, "LLM gateway", "host model · API · Ollama", COL_PROCESS))
    parts.append(node(446, 478, 346, 92, "DataFetcher", "local → cache → source", COL_DATA))
    parts.append(node(446, 602, 346, 92, "Validation", "schema · statistics · provenance", COL_CONTROL))

    parts.append(section(870, 188, 312, 548, "BOUNDARIES", GREEN))
    parts.append(node(896, 230, 260, 92, "Local data", "never uploaded implicitly", COL_DATA))
    parts.append(node(896, 354, 260, 92, "External sources", "keys stay in keychain", COL_DATA))
    parts.append(node(896, 478, 260, 92, "Sandbox", "subprocess · limits", COL_CONTROL))
    parts.append(node(896, 602, 260, 92, "CI", f"{TEST_COUNT:,} tests · 3 OS", COL_INTERFACE))

    parts.append(section(1232, 188, 312, 548, "OUTPUT", PURPLE))
    parts.append(node(1258, 230, 260, 92, "FINAL.md", "required delivery summary", COL_PROCESS))
    parts.append(node(1258, 354, 260, 92, "SKIPPED_CONFIG.md", "required gap ledger", COL_CONTROL))
    parts.append(node(1258, 478, 260, 92, "Research artifacts", "data · code · figures · paper", COL_DATA))
    parts.append(node(1258, 602, 260, 92, "DELIVERY.md", "optional contract check", COL_INTERFACE))
    for x1, x2 in ((368, 410), (820, 862), (1182, 1224)):
        parts.append(arrow(x1, 462, x2, 462))
    return _finish(parts, 5)


def gen_banner() -> str:
    width, height = 1600, 520
    stages = ("Idea", "Literature", "Novelty", "Design", "Data", "Analysis", "Draft", "Review")
    colors = (AMBER, BLUE, BLUE, GREEN, GREEN, GREEN, AMBER, PURPLE)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">']
    parts.append(header("FinAI Research Workflow", "Evidence-first infrastructure for economic and financial research"))
    for index, stage in enumerate(stages):
        x = 48 + index * 188
        parts.append(node(x, 190, 164, 92, stage, "", (PANEL, colors[index]), fontsize=14))
        if index < len(stages) - 1:
            parts.append(arrow(x + 164, 236, x + 180, 236))
    parts.append(pill(166, 340, 286, f"{MCP_COUNT} data sources", GREEN))
    parts.append(pill(492, 340, 286, f"{METHOD_COUNT} method modules", BLUE))
    parts.append(pill(818, 340, 286, f"{SKILL_COUNT} research skills", AMBER))
    parts.append(pill(1144, 340, 286, f"{JOURNAL_COUNT} journal templates", PURPLE))
    parts.append(f'<text x="800" y="460" fill="{INK3}" font-size="12" text-anchor="middle" font-family="{MONO}">human checkpoints · provenance · no silent Mock</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def gen_quickstart() -> str:
    width, height = 1400, 900
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">']
    parts.append('<title id="title">Start FinAI with your preferred agent</title><desc id="desc">Codex is recommended; Cursor, Claude Code, API providers, and Ollama are supported. Mock is explicit opt-in only.</desc>')
    parts.append(f'''<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0L0 0 0 40" fill="none" stroke="{BORDER}" opacity=".32"/></pattern></defs>''')
    parts.append(f'<rect width="100%" height="100%" fill="{BG}"/>')
    parts.append(f'<rect width="100%" height="100%" fill="url(#grid)"/>')
    parts.append(f'<text x="64" y="68" fill="{INK}" font-size="34" font-weight="720" font-family="{FONT}">Start with the agent you already use</text>')
    parts.append(f'<text x="64" y="102" fill="{INK2}" font-size="16" font-family="{FONT}">Codex is recommended; Cursor, Claude Code, API providers, and Ollama use the same project protocol.</text>')
    hosts = ((64, 250, "RECOMMENDED", "Codex", GREEN), (334, 250, "SUPPORTED", "Cursor", BLUE), (604, 250, "SUPPORTED", "Claude Code", PURPLE), (874, 462, "OPTIONAL", "API / Ollama", AMBER))
    for x, w, tag, title, color in hosts:
        parts.append(f'<rect x="{x}" y="132" width="{w}" height="92" rx="14" fill="{PANEL}" stroke="{color}"/>')
        parts.append(f'<text x="{x + 22}" y="162" fill="{color}" font-size="10" font-weight="700" font-family="{MONO}">{tag}</text>')
        parts.append(f'<text x="{x + 22}" y="198" fill="{INK}" font-size="20" font-weight="700" font-family="{FONT}">{title}</text>')
    cards = (
        (64, "01 · RECOMMENDED", "Clarify first", "start_research.py", "Refine the question before running|the writing track.", GREEN),
        (478, "02 · DIRECT", "Writing pipeline", "agent_pipeline.py --use-hitl", "Use when the research brief|is already specific.", BLUE),
        (892, "03 · BATCH", "Agent host", "agent_host_entry.py", "Fail closed; writes explicit gap files;|never enables Mock.", PURPLE),
    )
    for x, tag, title, command, desc, color in cards:
        parts.append(section(x, 284, 360, 388, tag, color))
        parts.append(f'<text x="{x + 28}" y="358" fill="{INK}" font-size="25" font-weight="700" font-family="{FONT}">{_esc(title)}</text>')
        for line_index, line in enumerate(desc.split("|")):
            parts.append(f'<text x="{x + 28}" y="{397 + line_index * 21}" fill="{INK2}" font-size="13" font-family="{FONT}">{_esc(line)}</text>')
        parts.append(f'<rect x="{x + 28}" y="454" width="304" height="88" rx="12" fill="{PANEL2}" stroke="{BORDER}"/>')
        parts.append(f'<text x="{x + 48}" y="490" fill="{color}" font-size="12" font-family="{MONO}">python scripts/</text>')
        parts.append(f'<text x="{x + 48}" y="518" fill="{INK}" font-size="13" font-family="{MONO}">{_esc(command)}</text>')
        parts.append(pill(x + 28, 586, 304, "Mock is explicit opt-in only", PURPLE))
    parts.append(section(64, 746, 1188, 92, "SEPARATE EMPIRICAL HAND-OFF", GREEN))
    parts.append(f'<text x="94" y="800" fill="{INK}" font-size="15" font-family="{MONO}">python -m scripts.research_framework.enhanced_pipeline --topic "..." --explore [--panel FILE]</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def gen_06_writing_track() -> str:
    parts = _start()
    parts.append(header("Writing track", "Five generated artifacts, four reviewable transitions, no empirical estimation hidden inside"))
    stages = (
        ("01", "Outline", "research question · venue"),
        ("02", "Literature", "verified identifiers · evidence map"),
        ("03", "Figures", "claims matched to visual evidence"),
        ("04", "Manuscript", "structured LaTeX draft"),
        ("05", "Refinement", "adversarial review loop"),
    )
    for i, (num, title, desc) in enumerate(stages):
        x = 70 + i * 300
        parts.append(node(x, 270, 252, 118, f"{num}  {title}", desc, COL_INTERFACE if i < 2 else COL_PROCESS, fontsize=17))
        if i < 4:
            parts.append(arrow(x + 252, 329, x + 290, 329, "HITL"))
    parts.append(section(174, 520, 1252, 164, "RESEARCHER RESPONSIBILITY", PURPLE))
    for i, (title, desc) in enumerate((("Approve", "accept the actual artifact"), ("Reject", "rerun the same stage with feedback"), ("Verify", "citations, claims, and authorship"))):
        parts.append(node(210 + i * 406, 564, 352, 78, title, desc, COL_CONTROL, fontsize=15))
    return _finish(parts, 6)


def gen_07_data_routing() -> str:
    parts = _start()
    parts.append(header("Data routing", "Exact-variable matching and provenance outrank convenience"))
    parts.append(node(60, 350, 230, 110, "Variable request", "construct · unit · period", COL_USER))
    parts.append(arrow(290, 405, 352, 405))
    routes = (
        (352, "0", "Local panel", "FINAI_EMPIRICAL_DATA_ROOT", COL_DATA),
        (602, "1", "Validated cache", "schema + freshness + hash", COL_INTERFACE),
        (852, "2", "MCP / official API", "compatible source only", COL_DATA),
        (1102, "3", "Stop visibly", "missing ≠ synthetic", COL_CONTROL),
    )
    for i, (x, num, title, desc, color) in enumerate(routes):
        parts.append(node(x, 326, 214, 158, f"{num}  {title}", desc, color, fontsize=16))
        if i < len(routes) - 1:
            parts.append(arrow(x + 214, 405, x + 244, 405, "miss"))
    parts.append(section(352, 590, 964, 118, "ACCEPTANCE CONTRACT", GREEN))
    for x, label in ((388, "exact construct"), (622, "source recorded"), (856, "transform logged"), (1090, "validation passed")):
        parts.append(pill(x, 632, 190, label, GREEN))
    return _finish(parts, 7)


def gen_08_did_selection() -> str:
    parts = _start()
    parts.append(header("Modern DID selection", "Estimator choice follows treatment timing and assumptions—not a default TWFE button"))
    parts.append(node(60, 350, 250, 104, "Treatment structure", "timing · cohort · dose", COL_USER))
    parts.append(node(390, 246, 272, 104, "Staggered binary", "adoption timing differs", COL_CONTROL))
    parts.append(node(390, 500, 272, 104, "Continuous dose", "intensity varies", COL_CONTROL))
    parts.append(arrow(310, 402, 390, 298, "binary"))
    parts.append(arrow(310, 402, 390, 552, "dose"))
    parts.append(arrow(662, 298, 760, 246, "group-time ATT"))
    parts.append(arrow(662, 298, 760, 392, "dynamic effects"))
    parts.append(arrow(662, 552, 760, 554, "dose response"))
    parts.append(node(760, 194, 332, 104, "Callaway–Sant’Anna", "never / not-yet controls", COL_DATA))
    parts.append(node(760, 340, 332, 104, "Sun–Abraham / BJS", "event study / imputation", COL_INTERFACE))
    parts.append(node(760, 502, 332, 104, "Continuous DID", "state the dose estimand", COL_DATA))
    parts.append(section(1160, 204, 360, 412, "REQUIRED DIAGNOSTICS", AMBER))
    for i, (title, desc) in enumerate((("Pre-trends", "joint tests + plot"), ("Inference", "cluster / wild bootstrap"), ("Sensitivity", "alternative windows"))):
        parts.append(node(1188, 246 + i * 112, 304, 82, title, desc, COL_PROCESS, fontsize=14))
    parts.append(pill(458, 700, 684, "TWFE is a diagnostic baseline, not proof of identification", RED))
    return _finish(parts, 8)


def gen_09_provenance_chain() -> str:
    parts = _start()
    parts.append(header("Provenance chain", "Every reported number remains traceable to source, transform, validation, and artifact"))
    steps = (
        (70, "SOURCE", "provider · query · timestamp", COL_DATA),
        (370, "RAW", "immutable snapshot · checksum", COL_INTERFACE),
        (670, "TRANSFORM", "code version · parameters", COL_PROCESS),
        (970, "VALIDATE", "schema · ranges · missingness", COL_CONTROL),
        (1270, "ARTIFACT", "table · figure · manuscript", COL_USER),
    )
    for i, (x, title, desc, color) in enumerate(steps):
        parts.append(node(x, 330, 240, 124, title, desc, color, fontsize=16))
        if i < 4:
            parts.append(arrow(x + 240, 392, x + 290, 392))
    parts.append(section(220, 564, 1160, 132, "REPRODUCIBILITY RECORD", BLUE))
    for x, label in ((256, "provenance.json"), (526, "manifest + hashes"), (796, "environment lock"), (1066, "gap ledger")):
        parts.append(pill(x, 610, 220, label, BLUE))
    return _finish(parts, 9)


def gen_hero(dark: bool = False) -> str:
    bg, ink, sub, rule = (("#10231c", "#f7f4eb", "#b9c7bf", "#29473c") if dark else ("#f7f5ef", "#10231c", "#53645c", "#d8d6cd"))
    green = "#49c08d" if dark else GREEN
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 560" role="img" aria-labelledby="title desc">
  <title id="title">FinAI Research Workflow</title><desc id="desc">Evidence-first infrastructure from research question to defensible manuscript.</desc>
  <rect width="1600" height="560" fill="{bg}"/>
  <path d="M0 448H1600M1000 0V560M1200 0V560M1400 0V560" stroke="{rule}"/>
  <g transform="translate(84 72)" fill="none" stroke="{ink}" stroke-width="12" stroke-linejoin="round"><rect width="80" height="96" rx="8"/><path d="M20 32h40M20 54h34"/><path d="M20 76h40" stroke="{green}"/></g>
  <text x="196" y="118" fill="{ink}" font-size="28" font-weight="750" font-family="{FONT}">FinAI</text>
  <text x="84" y="242" fill="{ink}" font-size="66" font-weight="760" font-family="{FONT}">Research that can</text>
  <text x="84" y="316" fill="{ink}" font-size="66" font-weight="760" font-family="{FONT}">show its work.</text>
  <text x="88" y="380" fill="{sub}" font-size="22" font-family="{FONT}">Evidence-first infrastructure for empirical economics and finance.</text>
  <text x="88" y="438" fill="{green}" font-size="14" font-weight="700" font-family="{MONO}">LOCAL DATA FIRST  ·  HUMAN CHECKPOINTS  ·  NO SILENT MOCK</text>
  <g font-family="{MONO}" font-size="13"><text x="1040" y="92" fill="{sub}">01  DISCOVER</text><text x="1240" y="92" fill="{sub}">02  DESIGN</text><text x="1440" y="92" fill="{sub}">03  EVIDENCE</text><text x="1040" y="292" fill="{sub}">04  ESTIMATE</text><text x="1240" y="292" fill="{sub}">05  WRITE</text><text x="1440" y="292" fill="{sub}">06  REVIEW</text></g>
  <g fill="{ink}" font-family="{FONT}" font-weight="740" font-size="31"><text x="1040" y="178">{MCP_COUNT}</text><text x="1240" y="178">{METHOD_COUNT}</text><text x="1440" y="178">{SKILL_COUNT}</text><text x="1040" y="378">{JOURNAL_COUNT}</text></g>
  <g fill="{sub}" font-family="{MONO}" font-size="11"><text x="1040" y="204">DATA SOURCES</text><text x="1240" y="204">METHOD MODULES</text><text x="1440" y="204">AI SKILLS</text><text x="1040" y="404">JOURNAL TEMPLATES</text></g>
</svg>\n'''


def _write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def _render_png(svg_path: Path, width: int, height: int) -> bool:
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        return False
    subprocess.run(
        [renderer, "-w", str(width), "-h", str(height), str(svg_path), "-o", str(svg_path.with_suffix(".png"))],
        check=True,
    )
    return True


def main() -> None:
    diagrams = (
        ("01-architecture-overview.svg", gen_01_architecture_overview),
        ("02-skill-system-map.svg", gen_02_skill_system_map),
        ("03-mcp-ecosystem-map.svg", gen_03_mcp_ecosystem_map),
        ("04-research-pipeline.svg", gen_04_research_pipeline),
        ("05-deployment-data-flow.svg", gen_05_deployment_data_flow),
        ("06-writing-track.svg", gen_06_writing_track),
        ("07-data-routing.svg", gen_07_data_routing),
        ("08-did-selection.svg", gen_08_did_selection),
        ("09-provenance-chain.svg", gen_09_provenance_chain),
    )
    overview_rendered = False
    for name, generator in diagrams:
        path = OUT_DIR / name
        _write_svg(path, generator())
        rendered = _render_png(path, WIDTH, HEIGHT)
        if name == "01-architecture-overview.svg":
            overview_rendered = rendered
        print(f"generated {path.relative_to(PROJECT_ROOT)}" + (" + PNG" if rendered else ""))

    support = (
        (ASSET_DIR / "banner.svg", gen_banner(), 1600, 520, True),
        (ASSET_DIR / "quickstart.svg", gen_quickstart(), 1400, 900, True),
        (ASSET_DIR / "hero-light.svg", gen_hero(False), 1600, 560, False),
        (ASSET_DIR / "hero-dark.svg", gen_hero(True), 1600, 560, False),
    )
    for path, content, width, height, render_png in support:
        _write_svg(path, content)
        rendered = render_png and _render_png(path, width, height)
        print(f"generated {path.relative_to(PROJECT_ROOT)}" + (" + PNG" if rendered else ""))
    shutil.copyfile(ASSET_DIR / "banner.svg", OUT_DIR / "banner.svg")
    shutil.copyfile(OUT_DIR / "01-architecture-overview.svg", OUT_DIR / "architecture-diagram.svg")
    if overview_rendered:
        shutil.copyfile(OUT_DIR / "01-architecture-overview.png", OUT_DIR / "architecture-diagram.png")


if __name__ == "__main__":
    main()
