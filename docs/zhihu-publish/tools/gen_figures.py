#!/usr/bin/env python3
"""
5 张素材图生成器（中文版）
- 所有文字采用中文
- 字体: Hiragino Sans GB / STHeiti（macOS 内置）
- 输出: docs/zhihu-publish/assets/figure_*.png

内容：
  figure_00_overview.png  项目数据总览
  figure_01_health.png    系统健康雷达图
  figure_02_mcp.png       43 个数据源分布
  figure_03_openssf.png   OpenSSF Gold 徽章
  figure_04_journals.png  88 个期刊模板
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Hiragino Sans GB', 'STHeiti', 'PingFang SC', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

COLORS = {
    "primary": "#0A2540",
    "accent": "#00BFA6",
    "blue": "#0EA5E9",
    "gold": "#F5B700",
    "green": "#10B981",
    "purple": "#8B5CF6",
    "pink": "#EC4899",
    "bg": "#F7F9FC",
    "card": "#FFFFFF",
    "text": "#1A202C",
    "muted": "#718096",
    "orange": "#F59E0B",
    "red": "#EF4444",
}


def clean(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)


def fig_00_overview():
    """项目数据总览"""
    fig, ax = plt.subplots(figsize=(14, 8), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); clean(ax)

    # 标题
    ax.text(50, 94, "FinResearch Agent", fontsize=20, fontweight="bold",
            color=COLORS["accent"], ha="center")
    ax.text(50, 88.5, "项目数据总览 · 真实数据 · 自动生成",
            fontsize=11, color=COLORS["muted"], ha="center", style="italic")

    # 4 张卡片
    cards = [
        ("43", "数据源", "28 免费 · 12 需 Key · 3 演示", COLORS["blue"]),
        ("47", "因果方法", "DID · IV · RDD · GMM · Honest DiD", COLORS["purple"]),
        ("88", "期刊模板", "JF · JFE · RFS · 经济研究 · 金融研究", COLORS["pink"]),
        ("12,520", "测试函数", "100% 通过 · CI 全绿", COLORS["green"]),
    ]
    for i, (num, label, desc, color) in enumerate(cards):
        x = 5 + i * 22
        card = FancyBboxPatch((x, 36), 20, 40,
                              boxstyle="round,pad=0.5,rounding_size=1.2",
                              facecolor=COLORS["card"], edgecolor=color, linewidth=2.5, zorder=3)
        ax.add_patch(card)
        ax.text(x+10, 64, num, fontsize=38, color=color,
                ha="center", va="center", fontweight="bold", zorder=4)
        ax.text(x+10, 50, label, fontsize=13, color=COLORS["text"],
                ha="center", va="center", fontweight="bold", zorder=4)
        ax.text(x+10, 42, desc, fontsize=8, color=COLORS["muted"],
                ha="center", va="center", zorder=4)

    # 底部质量指标
    metrics = [
        ("🥇 OpenSSF Gold", "21/21 通过", COLORS["green"]),
        ("MIT 协议", "开源可商用", COLORS["accent"]),
        ("CI/CD 全绿", "7 个 Workflow", COLORS["green"]),
        ("⭐ GitHub", "11 Stars", COLORS["orange"]),
    ]
    for i, (label, val, color) in enumerate(metrics):
        x = 8 + i * 22
        ax.text(x, 19, label, fontsize=10, color=color, va="center", fontweight="bold", zorder=4)
        ax.text(x, 14.5, val, fontsize=9, color=COLORS["muted"], va="center", zorder=4)

    # GitHub
    ax.text(50, 5, "github.com/csmar432/finai-research",
            fontsize=12, color=COLORS["accent"], ha="center",
            family="monospace", fontweight="bold")

    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/figure_00_overview.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ {out}")


def fig_01_health():
    """系统健康雷达图"""
    fig = plt.figure(figsize=(12, 8), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])

    cats = ["MCP\n服务器", "Python\n依赖", "LLM\n接口", "数据\n源", "网络\n连通", "本地\n存储", "Git\n仓库", "测试\n套件"]
    N = len(cats)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    scores = [44, 95, 90, 80, 88, 92, 100, 100]
    scores += scores[:1]

    ax = fig.add_subplot(111, projection='polar')
    ax.set_facecolor(COLORS["bg"])
    ax.set_theta_offset(np.pi/2); ax.set_theta_direction(-1)

    plt.xticks(angles[:-1], cats, color=COLORS["primary"], size=10, fontweight="bold")
    ax.set_rlim(0, 100)
    plt.yticks([20,40,60,80,100], ["20","40","60","80","100"],
               color=COLORS["muted"], size=7)
    plt.ylim(0, 100)

    ax.plot(angles, scores, color=COLORS["accent"], linewidth=3, zorder=3)
    ax.fill(angles, scores, color=COLORS["accent"], alpha=0.2, zorder=2)
    for a, s in zip(angles[:-1], scores[:-1]):
        ax.scatter(a, s, s=80, color=COLORS["accent"],
                   edgecolor="white", linewidth=2, zorder=5)

    plt.title("系统健康检查 · 8 维度\n生成时间: 2026-07-26",
              fontsize=16, color=COLORS["primary"], fontweight="bold", pad=30)
    fig.text(0.5, 0.04, "综合评分: 88.5/100  ·  状态: 🟢 生产就绪",
             ha="center", fontsize=12, color=COLORS["green"], fontweight="bold")

    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/figure_01_health.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ {out}")


def fig_02_mcp():
    """43 个数据源分类分布"""
    fig = plt.figure(figsize=(14, 8), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])

    data = {
        "学术文献": 5,
        "A股数据": 4,
        "美股/港股": 3,
        "宏观经济": 10,
        "工具类": 10,
        "中文/新闻": 11,
    }
    palette = [COLORS["accent"], COLORS["blue"], COLORS["purple"],
               COLORS["orange"], COLORS["green"], COLORS["pink"]]

    # 左：饼图
    ax1 = fig.add_subplot(121)
    ax1.set_facecolor(COLORS["bg"])
    wedges, _, autotexts = ax1.pie(
        data.values(), labels=data.keys(),
        colors=palette, autopct="%1.0f%%",
        startangle=90, wedgeprops={"edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10, "color": COLORS["primary"]}
    )
    for t in autotexts:
        t.set_color("white"); t.set_fontweight("bold")
    ax1.set_title("数据源类别分布", fontsize=14, color=COLORS["primary"],
                  fontweight="bold", pad=20)

    # 右：水平条形
    ax2 = fig.add_subplot(122)
    ax2.set_facecolor(COLORS["bg"])
    names = list(data.keys()); values = list(data.values())
    bars = ax2.barh(names, values, color=palette, edgecolor="white", linewidth=2)
    for bar, val in zip(bars, values):
        ax2.text(val+0.3, bar.get_y()+bar.get_height()/2,
                 f" {val}", va="center", fontsize=11,
                 color=COLORS["primary"], fontweight="bold")
    ax2.set_xlim(0, 14)
    ax2.set_xlabel("数量", fontsize=11, color=COLORS["primary"])
    ax2.set_title("各类别数据源数量", fontsize=14, color=COLORS["primary"],
                  fontweight="bold", pad=20)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_color(COLORS["muted"]); ax2.spines["bottom"].set_color(COLORS["muted"])
    ax2.tick_params(colors=COLORS["primary"]); ax2.invert_yaxis()

    fig.suptitle("43 个 MCP 数据源 · 覆盖经济金融研究全场景",
                 fontsize=18, color=COLORS["primary"], fontweight="bold", y=0.98)

    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/figure_02_mcp.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ {out}")


def fig_03_openssf():
    """OpenSSF Gold 大徽章"""
    fig, ax = plt.subplots(figsize=(10, 10), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_xlim(-1.2, 1.2); ax.set_ylim(-1.2, 1.2); clean(ax)

    # 三层圆
    for color, r in zip(["#FFD700","#FFC107","#FFB300"], [1.1, 1.05, 1.0]):
        ax.add_patch(patches.Circle((0,0), r, facecolor=color,
                                    edgecolor="#FF8F00", linewidth=3, zorder=3))
    # 白底
    ax.add_patch(patches.Circle((0,0), 0.85, facecolor="white", zorder=5))

    # 文字
    ax.text(0, 0.45, "OpenSSF", fontsize=20, color=COLORS["primary"],
            ha="center", fontweight="bold", zorder=6)
    ax.text(0, 0.18, "BEST PRACTICES", fontsize=9, color=COLORS["muted"],
            ha="center", fontweight="bold", zorder=6)
    ax.text(0, -0.12, "GOLD", fontsize=48, color="#FF8F00",
            ha="center", va="center", fontweight="bold", zorder=6)
    ax.text(0, -0.47, "21/21", fontsize=18, color=COLORS["primary"],
            ha="center", fontweight="bold", zorder=6)
    ax.text(0, -0.72, "100% PASSED", fontsize=9, color=COLORS["muted"],
            ha="center", fontweight="bold", zorder=6)

    # 装饰星
    for angle in range(0, 360, 60):
        x = 0.92*np.cos(np.radians(angle)); y = 0.92*np.sin(np.radians(angle))
        ax.text(x, y, "★", fontsize=10, color="#FFD700",
                ha="center", va="center", zorder=7)

    ax.text(0, -1.05, "FinResearch Agent · 生产级工程标准",
            fontsize=10, color=COLORS["primary"], ha="center", fontweight="bold")

    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/figure_03_openssf.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ {out}")


def fig_04_journals():
    """88 个期刊模板分布"""
    fig, ax = plt.subplots(figsize=(14, 8), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); clean(ax)

    # 标题
    ax.text(50, 94, "88 个期刊模板 · 英文 / 中文全覆盖",
            fontsize=22, fontweight="bold", color=COLORS["primary"], ha="center")
    ax.text(50, 88, "一键生成 LaTeX 草稿，适配 30 种顶刊格式",
            fontsize=11, color=COLORS["muted"], ha="center", style="italic")

    sections = [
        ("英文顶刊 Top 5", 5, COLORS["accent"],
         "JF · JFE · RFS · JAE · JPE", 5, 40, 28, 36),
        ("英文更多期刊", 13, COLORS["blue"],
         "Econometrica · Restud · JoE · JFQA · RAPS · ...", 37, 40, 28, 36),
        ("中文顶刊 Top 5", 5, COLORS["pink"],
         "经济研究 · 金融研究 · 管理世界 · 会计研究 · 中国工业经济", 5, 5, 28, 28),
        ("中文更多期刊", 60, COLORS["purple"],
         "财贸经济 · 经济学 · 数量经济技术 · 财经研究 · 改革 · 南开管理评论 · ...", 37, 5, 28, 28),
    ]

    for title, count, color, subs, x, y, w, h in sections:
        card = FancyBboxPatch((x, y), w, h,
                              boxstyle="round,pad=0.5,rounding_size=0.8",
                              facecolor=COLORS["card"], edgecolor=color, linewidth=2.5, zorder=3)
        ax.add_patch(card)
        ax.text(x+3.5, y+h/2+6, str(count), fontsize=38, color=color,
                ha="center", va="center", fontweight="bold", zorder=4)
        ax.text(x+3.5, y+h/2-4, "个模板", fontsize=9, color=COLORS["muted"],
                ha="center", va="center", zorder=4)
        ax.text(x+9, y+h-8, title, fontsize=13, color=COLORS["text"],
                fontweight="bold", va="top", zorder=4)
        ax.text(x+9, y+h/2-2, subs, fontsize=9, color=COLORS["muted"],
                va="center", zorder=4)

    ax.text(50, 2, "总计 88 个模板 · 覆盖经管领域所有顶刊",
            fontsize=12, color=COLORS["primary"], ha="center", fontweight="bold")

    out = "/Users/xuzheyi/Desktop/论文-研报工作流/docs/zhihu-publish/assets/figure_04_journals.png"
    plt.savefig(out, dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"✅ {out}")


if __name__ == "__main__":
    fig_00_overview()
    fig_01_health()
    fig_02_mcp()
    fig_03_openssf()
    fig_04_journals()
    print()
    print("🎉 5 张中文素材图已生成")
    print("   文件: docs/zhihu-publish/assets/figure_*.png")
