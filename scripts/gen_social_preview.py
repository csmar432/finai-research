"""Generate the GitHub social preview image (1280x640 PNG).

Numbers are sourced from `scripts/count_assets.py::count_all()` — the
single source of truth for repo statistics — so the PNG never drifts from
README/audit. If you need to update counts, run:

    python scripts/count_assets.py --markdown  # to see current numbers
    python scripts/gen_social_preview.py        # to regenerate PNG
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Robust import: works from any cwd as long as PROJECT_ROOT is discoverable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
from count_assets import count_all  # noqa: E402

# GitHub dark background colors
BG = "#0d1117"
FG = "#ffffff"
SUB = "#8b949e"
ACCENT1 = "#58a6ff"  # blue
ACCENT2 = "#7ee787"  # green
ACCENT3 = "#ffa657"  # orange
CARD = "#161b22"

# Pull canonical counts — never hard-code
stats = count_all()
mcp_total = stats["mcp_servers"]["total"]
methods_total = stats["econometric_methods"]
skills_total = stats["skills"]
jt_total = stats["journal_templates"]["total"]

fig, ax = plt.subplots(figsize=(12.8, 6.4), dpi=100)
ax.set_xlim(0, 12.8)
ax.set_ylim(0, 6.4)
ax.axis("off")
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# Title
ax.text(
    6.4, 5.3, "FinAI Research Workflow",
    ha="center", va="center",
    fontsize=46, color=FG, weight="bold",
)
# Subtitle
ax.text(
    6.4, 4.35,
    "AI-powered research workflow for finance & economics",
    ha="center", va="center",
    fontsize=20, color=SUB,
)
ax.text(
    6.4, 3.85,
    "lit review → idea generation → empirical design → paper writing",
    ha="center", va="center",
    fontsize=14, color=SUB, style="italic",
)

# Four highlight cards — values pulled from count_all() (SSOT)
cards = [
    (1.9, f"{mcp_total}\nMCP Data\nSources", ACCENT1),
    (5.1, f"{methods_total}\nEconometric\nMethods", ACCENT2),
    (8.2, f"{skills_total}\nAI Skills", ACCENT3),
    (11.3, f"{jt_total}\nJournal\nTemplates", ACCENT1),
]
for x, label, color in cards:
    box = mpatches.FancyBboxPatch(
        (x - 1.25, 1.3), 2.5, 1.55,
        boxstyle="round,pad=0.05,rounding_size=0.1",
        facecolor=CARD, edgecolor=color, linewidth=2.5,
    )
    ax.add_patch(box)
    ax.text(
        x, 2.07, label,
        ha="center", va="center",
        fontsize=13, color=color, weight="bold",
    )

# Bottom URL
ax.text(
    6.4, 0.55,
    "github.com/csmar432/finai-research",
    ha="center", va="center",
    fontsize=15, color=SUB, family="monospace",
)

plt.savefig(
    ".github/social-preview.png",
    dpi=100, facecolor=BG, bbox_inches=None,
)
print(f"saved .github/social-preview.png  (MCP={mcp_total}, methods={methods_total}, "
      f"skills={skills_total}, journals={jt_total})")
