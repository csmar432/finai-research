#!/usr/bin/env python3
"""
GitHub 项目头像生成器（方形）
- 尺寸: 400x400（GitHub 推荐）
- 风格: 深色科技感，项目 Logo 风格
- 字体: Hiragino Sans GB / STHeiti（macOS 内置）
- 输出: docs/zhihu-publish/assets/avatar.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import matplotlib
matplotlib.rcParams['font.sans-serif'] = [
    'Hiragino Sans GB', 'STHeiti', 'PingFang SC', 'Arial Unicode MS'
]
matplotlib.rcParams['axes.unicode_minus'] = False

COLORS = {
    "dark": "#0A2540",
    "accent": "#00BFA6",
    "blue": "#0EA5E9",
    "gold": "#F5B700",
    "green": "#10B981",
    "purple": "#8B5CF6",
    "pink": "#EC4899",
}


def create_avatar():
    fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
    fig.patch.set_facecolor(COLORS["dark"])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # 背景渐变圆
    bg = patches.Circle((50, 50), 48, facecolor=COLORS["dark"],
                        edgecolor=COLORS["accent"], linewidth=3, zorder=1)
    ax.add_patch(bg)

    # 装饰圆点（科研感）
    for y, a in [(85, 0.15), (15, 0.12), (8, 0.08)]:
        for x in [15, 30, 50, 70, 85]:
            dot = patches.Circle((x, y), 1.2, facecolor=COLORS["accent"], alpha=a, zorder=2)
            ax.add_patch(dot)

    # 外圈细线
    for r in [44, 41]:
        ring = patches.Circle((50, 50), r,
                              facecolor='none', edgecolor=COLORS["accent"],
                              linewidth=0.5, alpha=0.3, zorder=2)
        ax.add_patch(ring)

    # === 顶部 F ===
    ax.text(50, 80, "F", fontsize=36, color="white",
            ha="center", va="center", fontweight="bold", zorder=3)

    # === 中部 FinResearch ===
    ax.text(50, 65, "FinResearch", fontsize=11, color=COLORS["accent"],
            ha="center", va="center", fontweight="bold", zorder=3)
    ax.text(50, 57, "Agent", fontsize=9, color="white",
            ha="center", va="center", fontweight="bold", zorder=3)

    # === 分隔线 ===
    ax.plot([25, 75], [51, 51], color=COLORS["accent"], linewidth=1.5, alpha=0.6, zorder=3)

    # === 8 步流水线（小圆点）===
    steps = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"]
    colors = ["#00BFA6", "#0EA5E9", "#8B5CF6", "#EC4899",
              "#F59E0B", "#10B981", "#3B82F6", "#EF4444"]
    for i, (s, c) in enumerate(zip(steps, colors)):
        x = 22 + i * 8
        circle = patches.Circle((x, 42), 2.5, facecolor=c, zorder=4)
        ax.add_patch(circle)

    # === 底部关键数字 ===
    stats = [("43", "数据源"), ("47", "方法"), ("30", "模板")]
    for i, (num, label) in enumerate(stats):
        x = 22 + i * 28
        ax.text(x, 24, num, fontsize=13, color=COLORS["accent"],
                ha="center", va="center", fontweight="bold", zorder=4)
        ax.text(x, 18, label, fontsize=7, color="#8899AA",
                ha="center", va="center", zorder=4)

    plt.tight_layout(pad=0)
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/avatar.png"
    plt.savefig(out, dpi=100, bbox_inches="tight",
                facecolor=COLORS["dark"])
    plt.close()
    print(f"✅ 项目头像生成: {out}")
    return out


if __name__ == "__main__":
    create_avatar()
