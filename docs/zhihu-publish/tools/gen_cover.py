#!/usr/bin/env python3
"""
知乎封面图生成器（中文版）
- 尺寸: 1200x630 (2:1 知乎推荐)
- 风格: 深色科技感，左文右图
- 字体: Hiragino Sans GB / STHeiti（macOS 内置）
- 输出: docs/zhihu-publish/assets/cover.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Hiragino Sans GB', 'STHeiti', 'PingFang SC', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

COLORS = {
    "dark": "#0A2540",
    "accent": "#00BFA6",
    "blue": "#0EA5E9",
    "gold": "#F5B700",
    "card": "#FFFFFF",
    "bg": "#F7F9FC",
    "text": "#1A202C",
    "muted": "#718096",
    "green": "#10B981",
}


def create_cover():
    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 63)
    ax.axis("off")

    # === 左侧深色面板 ===
    left = patches.Rectangle((0, 0), 50, 63, facecolor=COLORS["dark"], zorder=1)
    ax.add_patch(left)

    # 装饰圆形
    for y, a in [(56, 0.12), (49, 0.08), (42, 0.06)]:
        for x_off in [3, 10, 17, 24, 31]:
            c = patches.Circle((x_off, y), 0.7, facecolor=COLORS["accent"], alpha=a, zorder=2)
            ax.add_patch(c)

    # === 顶部项目名 ===
    ax.text(3.5, 57, "FinResearch Agent", fontsize=10, color=COLORS["accent"],
            fontweight="bold", zorder=3)
    ax.text(3.5, 54.5, "AI 驱动的经济金融研究工作流", fontsize=8, color="#8899AA",
            style="italic", zorder=3)

    # === 主标题（中文） ===
    ax.text(3.5, 46, "用 6 个月做了个", fontsize=13, color="#FFFFFF", zorder=3)
    ax.text(3.5, 40.5, "开源项目", fontsize=13, color="#FFFFFF", zorder=3)
    ax.text(3.5, 35, "让 AI 帮你跑完", fontsize=20, color="#FFFFFF",
            fontweight="bold", zorder=3)
    ax.text(3.5, 29, "43 类实证模型", fontsize=20, color=COLORS["accent"],
            fontweight="bold", zorder=3)
    ax.text(3.5, 23.5, "生成可投稿的", fontsize=13, color="#FFFFFF", zorder=3)
    ax.text(3.5, 18, "LaTeX 论文草稿", fontsize=20, color=COLORS["gold"],
            fontweight="bold", zorder=3)

    # === 8 步流水线标签 ===
    steps_cn = ["想法", "文献", "新颖性", "设计", "数据", "实证", "写作", "Review"]
    step_colors = ["#00BFA6","#0EA5E9","#8B5CF6","#EC4899",
                   "#F59E0B","#10B981","#3B82F6","#EF4444"]

    for i, (step, color) in enumerate(zip(steps_cn, step_colors)):
        x = 3.5 + i * 5.8
        # 节点
        circle = patches.Circle((x, 10.5), 1.4, facecolor=color,
                               edgecolor="white", linewidth=1.5, zorder=4)
        ax.add_patch(circle)
        ax.text(x, 10.5, str(i+1), fontsize=9, color="white",
                ha="center", va="center", fontweight="bold", zorder=5)
        # 连接线
        if i < 7:
            ax.plot([x+1.4, x+4.4], [10.5, 10.5], color="#4A5568",
                    linewidth=1.5, zorder=3, linestyle="--")
        # 文字
        ax.text(x, 7.5, step, fontsize=7.5, color="#A0AEC0",
                ha="center", va="center", zorder=4)

    # === 右侧数据统计卡 ===
    stats = [
        ("43", "数据源", "#0EA5E9"),
        ("47", "因果方法", "#8B5CF6"),
        ("88", "期刊模板", "#EC4899"),
    ]
    for i, (num, label, color) in enumerate(stats):
        x = 57 + i * 21
        card = FancyBboxPatch((x, 38), 18, 15,
                              boxstyle="round,pad=0.3,rounding_size=0.8",
                              facecolor="white", edgecolor=color, linewidth=2, zorder=3)
        ax.add_patch(card)
        ax.text(x+9, 48, num, fontsize=30, color=color,
                ha="center", va="center", fontweight="bold", zorder=4)
        ax.text(x+9, 41, label, fontsize=10, color="#4A5568",
                ha="center", va="center", zorder=4)

    # === 右侧项目快照文字 ===
    ax.text(57, 32, "项目快照", fontsize=14, color=COLORS["dark"],
            fontweight="bold", zorder=3)
    ax.text(57, 28.5, "OpenSSF Gold 21/21 · MIT 协议", fontsize=9,
            color=COLORS["accent"], zorder=3)
    ax.text(57, 25, "12,520 个测试函数 · CI 全绿", fontsize=9,
            color=COLORS["muted"], zorder=3)

    # === 能力列表 ===
    abilities = [
        "✅ A股/美股/宏观 · 全自动数据获取",
        "✅ DID/IV/RDD/PSM · 47 种因果方法",
        "✅ JF/JFE/RFS · 经济研究 · 金融研究",
        "✅ 8 步流水线 · 每步人工确认",
    ]
    for j, ab in enumerate(abilities):
        ax.text(57, 21 - j*4.2, ab, fontsize=9, color="#4A5568", zorder=3)

    # === GitHub 链接 ===
    ax.text(117, 3.5, "github.com/csmar432/finai-research",
            fontsize=10, color=COLORS["accent"], ha="right",
            family="monospace", fontweight="bold", zorder=3)

    # === 版本号 ===
    ax.text(3.5, 3.5, "v1.0 · 开源 MIT", fontsize=8.5, color="#5A6A7A", zorder=3)

    plt.tight_layout(pad=0)
    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/cover.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ 封面图生成: {out}")
    return out


if __name__ == "__main__":
    create_cover()
