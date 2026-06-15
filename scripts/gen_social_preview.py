"""Generate the GitHub social preview image (1280x640 PNG)."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# GitHub dark background colors
BG = "#0d1117"
FG = "#ffffff"
SUB = "#8b949e"
ACCENT1 = "#58a6ff"  # blue
ACCENT2 = "#7ee787"  # green
ACCENT3 = "#ffa657"  # orange
CARD = "#161b22"

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

# Three highlight cards
cards = [
    (2.3, "43 MCP\nData Sources", ACCENT1),
    (6.4, "49 Econometric\nMethods (DID/IV/RDD)", ACCENT2),
    (10.5, "70 Journal\nTemplates", ACCENT3),
]
for x, label, color in cards:
    box = mpatches.FancyBboxPatch(
        (x - 1.4, 1.4), 2.8, 1.5,
        boxstyle="round,pad=0.05,rounding_size=0.1",
        facecolor=CARD, edgecolor=color, linewidth=2.5,
    )
    ax.add_patch(box)
    ax.text(
        x, 2.15, label,
        ha="center", va="center",
        fontsize=13, color=color, weight="bold",
    )

# Bottom URL
ax.text(
    6.4, 0.55,
    "github.com/csmar432/FinAI-Research-Workflow",
    ha="center", va="center",
    fontsize=15, color=SUB, family="monospace",
)

plt.savefig(
    ".github/social-preview.png",
    dpi=100, facecolor=BG, bbox_inches=None,
)
print("saved .github/social-preview.png")
