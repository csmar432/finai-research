"""
gen_architecture_diagrams.py
============================
生成 5 个**非冗余**架构图，覆盖项目的不同视角：

  01_architecture_overview.svg   端到端体系架构（高层鸟瞰）
  02_skill_system_map.svg       17 个 skill 体系
  03_mcp_ecosystem_map.svg      {{MCP_COUNT}} 个 MCP server 生态
  04_research_pipeline.svg      8 步研究流水线
  05_deployment_data_flow.svg   部署/数据流

设计原则：
  - 每图只讲一个故事
  - 统一暗色背景（与现有架构图一致）
  - 16:9 比例
  - 文字层级清晰（标题 > 节标题 > 节点标题 > 节点描述）
  - 颜色编码：蓝色 (interface) / 绿色 (data) / 橙色 (process) / 紫色 (control)
"""
from __future__ import annotations

import os

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", ".github", "demo")
os.makedirs(OUT_DIR, exist_ok=True)

# ─── MCP 数量（真相源: scripts/count_mcp.py）─────────────────────────
# v2.1 (2026-07-12): 此前硬编码 44 (drift)，改为运行时同步 count_mcp.py 的结果。
try:
    from scripts.count_mcp import count_mcp_directories as _cad
    MCP_COUNT = _cad()
except Exception:
    # 兜底：43 个（当前 ground truth）
    MCP_COUNT = 43

# ─── 主题与样式 ──────────────────────────────────────────────────────
BG = "#0a0e1a"
BG2 = "#0d1220"
INK = "#e8edf5"
INK2 = "#aab4c5"
INK3 = "#7a8499"

# 4 类节点配色 (4 个视角统一)
COL_INTERFACE = ("#1a3a6e", "#3b82f6")  # 蓝 - 接口
COL_DATA      = ("#0f4d2e", "#10b981")  # 绿 - 数据
COL_PROCESS   = ("#7a3b0e", "#f59e0b")  # 橙 - 处理
COL_CONTROL   = ("#3b1a6e", "#a855f7")  # 紫 - 控制
COL_USER      = ("#5e1a3b", "#ec4899")  # 粉 - 用户/角色

FONT = "'SF Pro Text', 'Segoe UI', system-ui, -apple-system, sans-serif"
MONO = "'SF Mono', 'JetBrains Mono', 'Cascadia Code', monospace"

WIDTH, HEIGHT = 1600, 1000  # 16:10 宽屏


def _esc(s: str) -> str:
    """Escape XML special chars."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def header(title: str, subtitle: str, version: str | None = None) -> str:
    """所有图共享的页眉。version 默认为动态读取 pyproject。"""
    if version is None:
        try:
            from pathlib import Path as _P

            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            pyproject = _P(__file__).resolve().parent.parent / "pyproject.toml"
            if pyproject.exists():
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                version = "v" + data.get("project", {}).get("version", "0.0.0")
            else:
                version = "v?"
        except Exception:
            version = "v?"
    return f'''  <defs>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BG}"/>
      <stop offset="100%" stop-color="{BG2}"/>
    </linearGradient>
    <linearGradient id="hdrGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bgGrad)"/>

  <!-- 页眉 -->
  <rect x="0" y="0" width="{WIDTH}" height="80" fill="url(#hdrGrad)" opacity="0.15"/>
  <text x="60" y="48" fill="{INK}" font-size="32" font-weight="700" font-family="{FONT}">{_esc(title)}</text>
  <text x="60" y="72" fill="{INK2}" font-size="16" font-family="{FONT}">{_esc(subtitle)}</text>
  <text x="{WIDTH-60}" y="48" fill="{INK2}" font-size="14" text-anchor="end" font-family="{MONO}">FinAI Research Workflow · {version}</text>
  <text x="{WIDTH-60}" y="72" fill="{INK3}" font-size="12" text-anchor="end" font-family="{MONO}">5-architecture series</text>
  <line x1="60" y1="100" x2="{WIDTH-60}" y2="100" stroke="#1e2738" stroke-width="1"/>'''


def footer(idx: int, total: int = 5) -> str:
    """所有图共享的页脚 (不含 </svg>)。"""
    return f'''
  <!-- 页脚 -->
  <line x1="60" y1="{HEIGHT-50}" x2="{WIDTH-60}" y2="{HEIGHT-50}" stroke="#1e2738" stroke-width="1"/>
  <text x="60" y="{HEIGHT-25}" fill="{INK3}" font-size="12" font-family="{MONO}">图 {idx} / {total} · finai-research-workflow</text>
  <text x="{WIDTH-60}" y="{HEIGHT-25}" fill="{INK3}" font-size="12" text-anchor="end" font-family="{FONT}">开源 · MIT · 2026</text>'''


def node(x: int, y: int, w: int, h: int, title: str, desc: str = "",
         col=COL_PROCESS, radius: int = 12, fontsize: int = 16) -> str:
    """一个节点（圆角矩形 + 标题 + 描述）。"""
    c1, c2 = col
    text_x = x + w / 2
    return f'''
  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{c1}" stroke="{c2}" stroke-width="1.5"/>
    <rect x="{x}" y="{y}" width="{w}" height="3" rx="2" fill="{c2}"/>
    <text x="{text_x}" y="{y + h/2 - (8 if desc else 0)}" fill="{INK}" font-size="{fontsize}" font-weight="600" text-anchor="middle" font-family="{FONT}">{_esc(title)}</text>
    {f'<text x="{text_x}" y="{y + h/2 + 18}" fill="{INK2}" font-size="13" text-anchor="middle" font-family="{FONT}">{_esc(desc)}</text>' if desc else ''}
  </g>'''


def arrow(x1: int, y1: int, x2: int, y2: int, label: str = "",
          color: str = "#5a6478", dashed: bool = False) -> str:
    """一条带箭头的连接线（可选标签）。"""
    dash_attr = ' stroke-dasharray="4 4"' if dashed else ''
    label_html = ""
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 8
        label_html = f'<text x="{mx}" y="{my}" fill="{INK3}" font-size="11" text-anchor="middle" font-family="{MONO}">{label}</text>'
    return f'''
  <g>
    <defs><marker id="ah_{x1}_{y1}" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="{color}"/>
    </marker></defs>
    <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"{dash_attr} marker-end="url(#ah_{x1}_{y1})"/>
    {label_html}
  </g>'''


def section(x: int, y: int, w: int, h: int, label: str, color: str = "#3b82f6") -> str:
    """一个分组（虚线矩形 + 标签）。"""
    return f'''
  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.6"/>
    <rect x="{x+12}" y="{y-10}" width="{len(label)*10+24}" height="22" rx="6" fill="{BG}" stroke="{color}" stroke-width="1"/>
    <text x="{x+12+len(label)*5+12}" y="{y+5}" fill="{color}" font-size="13" font-weight="600" text-anchor="middle" font-family="{FONT}">{_esc(label)}</text>
  </g>'''


def wrap(text: str) -> str:
    return text


# ═══════════════════════════════════════════════════════════════════
# 图 1: 体系架构 (端到端)
# ═══════════════════════════════════════════════════════════════════
def gen_01_architecture_overview() -> str:
    """高层鸟瞰：5 层架构 (User → Interface → Core → Skill → Data)。"""
    title = "图 1: 体系架构 (System Architecture Overview)"
    subtitle = "5 层端到端：用户 → 接口层 → 编排核心 → 技能系统 → 数据与基础设施"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">']
    parts.append(header(title, subtitle))

    # 5 个 section 横向排列
    y_top = 150
    layer_h = 700
    layer_w = 280
    gap = 30
    x_start = 60

    # Layer 1: User / Roles
    x = x_start
    parts.append(section(x, y_top, layer_w, layer_h, "① 用户 / 角色层", "#ec4899"))
    parts.append(node(x+30, y_top+40, layer_w-60, 80, "4 类用户", "学生 / 研究员 / 老师 / 机构", COL_USER))
    parts.append(node(x+30, y_top+150, layer_w-60, 70, "Setup Wizard", "交互式配置", COL_INTERFACE))
    parts.append(node(x+30, y_top+240, layer_w-60, 70, "Profile 切换", "4 profile / 智能 fallback", COL_INTERFACE))
    parts.append(node(x+30, y_top+330, layer_w-60, 70, "CLI 入口", "12+ 入口脚本", COL_INTERFACE))
    parts.append(node(x+30, y_top+420, layer_w-60, 70, "Checkpoint", "强制交互 (HITL)", COL_CONTROL))
    parts.append(node(x+30, y_top+510, layer_w-60, 70, "Event Monitor", "NFP/CPI/FOMC 监控", COL_CONTROL))
    parts.append(node(x+30, y_top+600, layer_w-60, 70, "Keychain", "API key 加密存储", COL_CONTROL))

    # Layer 2: Interface / I/O
    x += layer_w + gap
    parts.append(section(x, y_top, layer_w, layer_h, "② 接口层", "#3b82f6"))
    parts.append(node(x+30, y_top+40, layer_w-60, 70, "Claude Code / Cursor", "原生 IDE 集成", COL_INTERFACE))
    parts.append(node(x+30, y_top+130, layer_w-60, 70, "GitHub Copilot", "VS Code 集成", COL_INTERFACE))
    parts.append(node(x+30, y_top+220, layer_w-60, 70, "自然语言", "中文主题 → 论文", COL_INTERFACE))
    parts.append(node(x+30, y_top+310, layer_w-60, 70, "MCP Protocol", "Model Context Protocol", COL_INTERFACE))
    parts.append(node(x+30, y_top+400, layer_w-60, 70, "Stdin/stdout", "subprocess 沙箱", COL_INTERFACE))
    parts.append(node(x+30, y_top+490, layer_w-60, 70, "LaTeX 编译", "PDF 输出", COL_INTERFACE))
    parts.append(node(x+30, y_top+580, layer_w-60, 70, "JSON/CSV/YAML", "结构化输出", COL_INTERFACE))

    # Layer 3: Orchestration Core
    x += layer_w + gap
    parts.append(section(x, y_top, layer_w, layer_h, "③ 编排核心", "#f59e0b"))
    parts.append(node(x+30, y_top+40, layer_w-60, 80, "Agent Pipeline", "8 步端到端编排", COL_PROCESS))
    parts.append(node(x+30, y_top+140, layer_w-60, 70, "AI Router", "DeepSeek / Claude / GPT 路由", COL_PROCESS))
    parts.append(node(x+30, y_top+230, layer_w-60, 70, "LLM Reviewer", "对抗性评审", COL_PROCESS))
    parts.append(node(x+30, y_top+320, layer_w-60, 70, "Checkpoint", "断点续传", COL_PROCESS))
    parts.append(node(x+30, y_top+410, layer_w-60, 70, "Provenance", "数据溯源追踪", COL_PROCESS))
    parts.append(node(x+30, y_top+500, layer_w-60, 70, "Autonomy Loop", "自主循环 + HITL", COL_PROCESS))
    parts.append(node(x+30, y_top+590, layer_w-60, 70, "MCP Tool Market", "工具市场", COL_PROCESS))

    # Layer 4: Skill System
    x += layer_w + gap
    parts.append(section(x, y_top, layer_w, layer_h, "④ 技能系统", "#a855f7"))
    parts.append(node(x+30, y_top+40, layer_w-60, 80, "17 技能", "完整研究生命周期", COL_CONTROL))
    parts.append(node(x+30, y_top+140, layer_w-60, 70, "lit-review", "文献综述", COL_CONTROL))
    parts.append(node(x+30, y_top+230, layer_w-60, 70, "idea-discovery", "想法生成", COL_CONTROL))
    parts.append(node(x+30, y_top+320, layer_w-60, 70, "experiment-design", "实证设计", COL_CONTROL))
    parts.append(node(x+30, y_top+410, layer_w-60, 70, "paper-writing", "论文写作", COL_CONTROL))
    parts.append(node(x+30, y_top+500, layer_w-60, 70, "review-loop", "对抗性 review", COL_CONTROL))
    parts.append(node(x+30, y_top+590, layer_w-60, 70, "submit-check", "投稿前检查", COL_CONTROL))

    # Layer 5: Data & Infra
    x += layer_w + gap
    parts.append(section(x, y_top, layer_w, layer_h, "⑤ 数据与基础设施", "#10b981"))
    parts.append(node(x+30, y_top+40, layer_w-60, 80, f"{MCP_COUNT} MCP Servers", "完整金融数据", COL_DATA))
    parts.append(node(x+30, y_top+140, layer_w-60, 70, "4 层 Fallback", "MCP → lib → HTTP → synthetic", COL_DATA))
    parts.append(node(x+30, y_top+230, layer_w-60, 70, "27 计量方法", "DID/IV/RD/GMM", COL_DATA))
    parts.append(node(x+30, y_top+320, layer_w-60, 70, "20+ 图表预设", "≥300 DPI", COL_DATA))
    parts.append(node(x+30, y_top+410, layer_w-60, 70, "34 期刊模板", "JF/JFE/CTeX 等", COL_DATA))
    parts.append(node(x+30, y_top+500, layer_w-60, 70, "180 测试", "pytest 100% 通过", COL_DATA))
    parts.append(node(x+30, y_top+590, layer_w-60, 70, "3 平台 CI", "macOS/Linux/Windows", COL_DATA))

    # 横向连接箭头
    for i in range(4):
        x_from = x_start + (i+1)*layer_w + i*gap - gap + 5
        x_to = x_from + gap - 10
        ay = y_top + layer_h / 2
        parts.append(arrow(x_from, int(ay), x_to, int(ay), color="#5a6478"))

    parts.append(footer(1))
    return "\n".join(parts) + "\n</svg>\n"


# ═══════════════════════════════════════════════════════════════════
# 图 2: Skill System Map
# ═══════════════════════════════════════════════════════════════════
def gen_02_skill_system_map() -> str:
    """17 个 skill 体系 + 4 阶段 + 触发关系。"""
    title = "图 2: 17 技能体系 (Skill System Map)"
    subtitle = "4 阶段：发现 → 设计 → 写作 → 发布"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">']
    parts.append(header(title, subtitle))

    # 4 个 phase 大块
    y_top = 150
    phase_w = 360
    phase_h = 720
    gap = 30
    x_start = 60
    phases = [
        ("① 想法发现阶段", "#3b82f6", [
            ("fin-idea-discovery", "想法发现 + 数据验证", "完整流程"),
            ("fin-generate-idea", "8-12 排序想法", "批量生成"),
            ("fin-novelty-check", "顶刊查重", "JF/JFE/RFS"),
            ("fin-lit-review", "系统性综述", "MCP 检索"),
        ]),
        ("② 研究设计阶段", "#10b981", [
            ("fin-experiment-design", "实证方案设计", "DID/IV/RD/PSM"),
            ("fin-data-acquisition", "数据获取 + 脚本", f"{MCP_COUNT} MCP 数据源"),
        ]),
        ("③ 论文写作阶段", "#f59e0b", [
            ("fin-paper-plan", "大纲生成", "34 期刊模板"),
            ("fin-paper-draft", "正文写作", "中英双语"),
            ("fin-paper-figure", "图表生成", "≥300 DPI"),
            ("fin-paper-writing", "写作编排", "全流程调度"),
            ("fin-paper-convert", "LaTeX 编译", "PDF 输出"),
        ]),
        ("④ 评审发布阶段", "#a855f7", [
            ("fin-review-loop", "对抗性 review", "多轮严格"),
            ("fin-submit-check", "投稿前检查", "格式/数据"),
            ("fin-ref-paper", "BibTeX 管理", "参考文献"),
            ("fin-brief-generator", "FIN_BRIEF.md", "研究简报"),
            ("fin-viz-launch", "自然语言 → 图表", "快速可视化"),
        ]),
    ]

    for i, (label, color, skills) in enumerate(phases):
        x = x_start + i * (phase_w + gap)
        parts.append(section(x, y_top, phase_w, phase_h, label, color))

        # 节点
        n = len(skills)
        h_node = (phase_h - 60) // n - 12
        for j, (name, desc, _) in enumerate(skills):
            ny = y_top + 40 + j * (h_node + 12)
            parts.append(node(x+15, ny, phase_w-30, h_node, name, desc, col=(color, color)))

    # 阶段箭头
    for i in range(3):
        x_from = x_start + (i+1)*phase_w + i*gap - gap + 5
        x_to = x_from + gap - 10
        ay = y_top + phase_h / 2
        parts.append(arrow(x_from, int(ay), x_to, int(ay), color="#5a6478"))

    # 底部说明
    y_btm = 900
    parts.append(f'<text x="{WIDTH/2}" y="{y_btm}" fill="{INK2}" font-size="14" text-anchor="middle" font-family="{FONT}">每阶段独立可调用；可串联为 fin-full-pipeline（端到端 1 条命令）</text>')

    parts.append(footer(2))
    return "\n".join(parts) + "\n</svg>\n"


# ═══════════════════════════════════════════════════════════════════
# 图 3: MCP Ecosystem Map
# ═══════════════════════════════════════════════════════════════════
def gen_03_mcp_ecosystem_map() -> str:
    f"""{MCP_COUNT} 个 MCP server 分类。"""
    title = f"图 3: {MCP_COUNT} MCP 数据生态 (MCP Ecosystem Map)"
    subtitle = "8 类别：学术 / A股 / 美股 / 宏观 / 新闻 / 工具 / 加密 / 区块链"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">']
    parts.append(header(title, subtitle))

    # 中心节点：MCP 协议
    cx, cy = WIDTH//2, 480
    parts.append(f'''
  <g>
    <circle cx="{cx}" cy="{cy}" r="100" fill="url(#hdrGrad)" opacity="0.2"/>
    <circle cx="{cx}" cy="{cy}" r="80" fill="{BG2}" stroke="#3b82f6" stroke-width="2"/>
    <text x="{cx}" y="{cy-15}" fill="{INK}" font-size="20" font-weight="700" text-anchor="middle" font-family="{FONT}">MCP 协议</text>
    <text x="{cx}" y="{cy+10}" fill="{INK2}" font-size="14" text-anchor="middle" font-family="{MONO}">Model Context Protocol</text>
    <text x="{cx}" y="{cy+35}" fill="{INK3}" font-size="11" text-anchor="middle" font-family="{MONO}">222 tools</text>
    <text x="{cx}" y="{cy+52}" fill="{INK3}" font-size="11" text-anchor="middle" font-family="{MONO}">100% schema 完整</text>
  </g>''')

    # 8 个分类环状分布
    import math
    categories = [
        ("学术文献", "5 servers", "openalex / arxiv / context7 / semantic_scholar / nber", "#3b82f6"),
        ("A股数据", "4 servers", "tushare / eastmoney / wind / csmar", "#10b981"),
        ("美股/全球", "3 servers", "yfinance / sec-edgar / enhanced-finance", "#f59e0b"),
        ("宏观经济", "10 servers", "financial / eodhd / fed / wb / imf / oecd / bea / ceic / datas / stats", "#a855f7"),
        ("研报/新闻", "2 servers", "eastmoney-reports / newsapi", "#ec4899"),
        ("工具类", "10 servers", "latex / pandas / playwright / e2b / filesystem / province / hubei / wuhan / crypto / newsapi", "#06b6d4"),
        ("加密货币", "1 server", "cryptocompare", "#84cc16"),
        ("中文文献", "1 server", "chinese-literature / cnki / wanfang", "#ef4444"),
    ]
    n = len(categories)
    r = 320
    for i, (name, count, members, color) in enumerate(categories):
        angle = i * (2 * math.pi / n) - math.pi / 2
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        # 节点
        parts.append(f'''
  <g>
    <rect x="{px-130}" y="{py-45}" width="260" height="90" rx="10" fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="1.5"/>
    <rect x="{px-130}" y="{py-45}" width="3" height="90" fill="{color}"/>
    <text x="{px-110}" y="{py-22}" fill="{INK}" font-size="15" font-weight="700" font-family="{FONT}">{name}</text>
    <text x="{px-110}" y="{py-3}" fill="{color}" font-size="12" font-family="{MONO}">{count}</text>
    <text x="{px-110}" y="{py+18}" fill="{INK2}" font-size="10" font-family="{MONO}">{members[:35]}</text>
  </g>''')
        # 连接线
        # 计算线段起点（从中心圆边缘到目标节点边缘）
        dx = px - cx
        dy = py - cy
        dist = math.sqrt(dx*dx + dy*dy)
        # 中心圆边缘
        x1 = int(cx + 80 * dx / dist)
        y1 = int(cy + 80 * dy / dist)
        # 目标节点边缘 (近似)
        x2 = int(px - 130 * dx / dist)
        y2 = int(py - 45 * dy / dist)
        parts.append(arrow(x1, y1, x2, y2, color=color))

    # 底部说明：4 层 fallback
    y_btm = 900
    parts.append(f'<text x="{WIDTH/2}" y="{y_btm}" fill="{INK2}" font-size="14" text-anchor="middle" font-family="{FONT}">每个数据需求 4 层 fallback：MCP → Python lib → HTTP → synthetic（标记）</text>')

    parts.append(footer(3))
    return "\n".join(parts) + "\n</svg>\n"


# ═══════════════════════════════════════════════════════════════════
# 图 4: Research Pipeline (8 步)
# ═══════════════════════════════════════════════════════════════════
def gen_04_research_pipeline() -> str:
    """8 步研究流水线。"""
    title = "图 4: 研究流水线 (8-Step Research Pipeline)"
    subtitle = "想法 → 文献 → 验证 → 设计 → 数据 → 写作 → 评审 → 发布"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">']
    parts.append(header(title, subtitle))

    # 8 步水平流程 + 中间有 checkpoint 标志
    steps = [
        ("0", "系统自检", "health_check.py", COL_CONTROL),
        ("1", "研究想法", "8-12 候选", COL_PROCESS),
        ("1.5", "想法-数据", "交叉验证", COL_PROCESS),
        ("2", "文献综述", "MCP 检索", COL_DATA),
        ("3", "新颖性验证", "顶刊查重", COL_DATA),
        ("4", "实证设计", "DID/IV/RD", COL_PROCESS),
        ("5", "数据获取", f"{MCP_COUNT} MCP", COL_DATA),
        ("6", "论文写作", "LaTeX", COL_PROCESS),
        ("7", "对抗 Review", "多轮严格", COL_CONTROL),
    ]
    n = len(steps)
    box_w = 150
    box_h = 100
    gap = (WIDTH - 120 - n * box_w) // (n - 1)
    y_row = 200
    for i, (num, name, sub, col) in enumerate(steps):
        x = 60 + i * (box_w + gap)
        c1, c2 = col
        parts.append(f'''
  <g>
    <rect x="{x}" y="{y_row}" width="{box_w}" height="{box_h}" rx="10" fill="{c1}" stroke="{c2}" stroke-width="2"/>
    <circle cx="{x+25}" cy="{y_row+25}" r="18" fill="{c2}"/>
    <text x="{x+25}" y="{y_row+30}" fill="{BG}" font-size="14" font-weight="700" text-anchor="middle" font-family="{MONO}">{num}</text>
    <text x="{x+box_w/2+10}" y="{y_row+30}" fill="{INK}" font-size="16" font-weight="700" text-anchor="middle" font-family="{FONT}">{name}</text>
    <text x="{x+box_w/2}" y="{y_row+65}" fill="{INK2}" font-size="11" text-anchor="middle" font-family="{MONO}">{sub}</text>
    <text x="{x+box_w/2}" y="{y_row+85}" fill="{INK3}" font-size="10" text-anchor="middle" font-family="{MONO}">↳ checkpoint</text>
  </g>''')
        # 箭头
        if i < n - 1:
            ax1 = x + box_w
            ax2 = x + box_w + gap
            ay = y_row + box_h // 2
            parts.append(arrow(ax1, ay, ax2, ay, color="#5a6478"))

    # 下方：核心约束
    y_constraints = 400
    parts.append(section(60, y_constraints, WIDTH-120, 280, "6 大核心约束", "#ec4899"))
    constraints = [
        ("数据优先", "想法生成前先验证数据可行性"),
        ("禁止静默 Fallback", "模拟数据必须经用户授权"),
        ("强制 Checkpoint", "每阶段暂停等用户确认"),
        ("数据溯源", "每次数据获取记录来源+时间戳"),
        ("中文顶刊标准", "经济研究/金融研究/管理世界"),
        ("生成-评审分离", "写作和 review 由不同模块处理"),
    ]
    cw = (WIDTH - 180) // 3
    ch = 90
    for i, (title, desc) in enumerate(constraints):
        col = i % 3
        row = i // 3
        x = 90 + col * (cw + 15)
        y = y_constraints + 40 + row * (ch + 15)
        parts.append(node(x, y, cw, ch, title, desc, COL_CONTROL, fontsize=15))

    # 底部：闭环
    y_btm = 750
    parts.append(section(60, y_btm, WIDTH-120, 130, "流水线闭环 (Feedback Loop)", "#3b82f6"))
    parts.append(f'<text x="{WIDTH/2}" y="{y_btm+50}" fill="{INK}" font-size="16" text-anchor="middle" font-family="{FONT}">每个 step 失败时，可回退到上一步或更换方向；每步产出 checkpoint 文件</text>')
    parts.append(f'<text x="{WIDTH/2}" y="{y_btm+80}" fill="{INK2}" font-size="14" text-anchor="middle" font-family="{MONO}">FIN_BRIEF.md → LIT_REVIEW.md → IDEA_REPORT.md → NOVELTY_REPORT.md → REFINED_DESIGN.md → DATA_READY.md → PAPER_OUTLINE.md → MANUSCRIPT.md → REVIEW_REPORT.md</text>')
    parts.append(f'<text x="{WIDTH/2}" y="{y_btm+105}" fill="{INK3}" font-size="12" text-anchor="middle" font-family="{MONO}">10 个文档作为流水线状态载体</text>')

    parts.append(footer(4))
    return "\n".join(parts) + "\n</svg>\n"


# ═══════════════════════════════════════════════════════════════════
# 图 5: Deployment & Data Flow
# ═══════════════════════════════════════════════════════════════════
def gen_05_deployment_data_flow() -> str:
    """部署 / 数据流 / 安全边界。"""
    title = "图 5: 部署与数据流 (Deployment &amp; Data Flow)"
    subtitle = "用户 → Profile → CI → MCP → 输出 + 3 层安全边界"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">']
    parts.append(header(title, subtitle))

    # 横向流：4 个区域
    # 区域 A: 用户端
    ax, ay, aw, ah = 60, 180, 280, 600
    parts.append(section(ax, ay, aw, ah, "A. 用户端 (Client)", "#ec4899"))
    parts.append(node(ax+20, ay+40, aw-40, 70, "Cursor / Claude Code", "IDE 集成", COL_USER))
    parts.append(node(ax+20, ay+130, aw-40, 70, "4 Profile", "学生/老师/...", COL_USER))
    parts.append(node(ax+20, ay+220, aw-40, 70, ".env + Keychain", "API Key 安全", COL_CONTROL))
    parts.append(node(ax+20, ay+310, aw-40, 70, "Setup Wizard", "首次配置", COL_INTERFACE))
    parts.append(node(ax+20, ay+400, aw-40, 70, "Interactive Checkpoint", "HITL 强制确认", COL_CONTROL))
    parts.append(node(ax+20, ay+490, aw-40, 70, "Health Check", "启动前自检", COL_CONTROL))

    # 区域 B: 编排层
    bx = ax + aw + 30
    bw = 320
    parts.append(section(bx, ay, bw, ah, "B. 编排层 (Orchestration)", "#3b82f6"))
    parts.append(node(bx+20, ay+40, bw-40, 70, "Agent Pipeline", "8 步编排", COL_PROCESS))
    parts.append(node(bx+20, ay+130, bw-40, 70, "AI Router", "DeepSeek/Claude/GPT", COL_PROCESS))
    parts.append(node(bx+20, ay+220, bw-40, 70, "Checkpoint / Autonomy", "状态持久化", COL_PROCESS))
    parts.append(node(bx+20, ay+310, bw-40, 70, "LLM Reviewer", "对抗性评审", COL_PROCESS))
    parts.append(node(bx+20, ay+400, bw-40, 70, "17 Skills", "完整研究能力", COL_CONTROL))
    parts.append(node(bx+20, ay+490, bw-40, 70, "Provenance Tracker", "数据溯源", COL_CONTROL))

    # 区域 C: 沙箱
    cx = bx + bw + 30
    cw = 280
    parts.append(section(cx, ay, cw, ah, "C. 沙箱 (Sandbox)", "#f59e0b"))
    parts.append(node(cx+20, ay+40, cw-40, 70, "Subprocess 隔离", "subprocess.run", COL_CONTROL))
    parts.append(node(cx+20, ay+130, cw-40, 70, "AST 静态分析", "禁止危险调用", COL_CONTROL))
    parts.append(node(cx+20, ay+220, cw-40, 70, "Restricted exec()", "受限命名空间", COL_PROCESS))
    parts.append(node(cx+20, ay+310, cw-40, 70, "Halt Rules", "动态停止", COL_CONTROL))
    parts.append(node(cx+20, ay+400, cw-40, 70, "Resource Limits", "内存/CPU/时间", COL_CONTROL))
    parts.append(node(cx+20, ay+490, cw-40, 70, "Pre-commit Hooks", "私钥/AWS 检测", COL_CONTROL))

    # 区域 D: 数据 + 输出
    dx = cx + cw + 30
    dw = WIDTH - dx - 60
    parts.append(section(dx, ay, dw, ah, "D. 数据与输出 (Data &amp; Output)", "#10b981"))
    parts.append(node(dx+20, ay+40, dw-40, 70, f"{MCP_COUNT} MCP Servers", "金融数据", COL_DATA))
    parts.append(node(dx+20, ay+130, dw-40, 70, "4 层 Fallback", "MCP→lib→HTTP→synth", COL_DATA))
    parts.append(node(dx+20, ay+220, dw-40, 70, "data/ 目录", "用户上传/缓存", COL_DATA))
    parts.append(node(dx+20, ay+310, dw-40, 70, "output/", "LaTeX/PDF/图表", COL_DATA))
    parts.append(node(dx+20, ay+400, dw-40, 70, "knowledge/", "skills/rules", COL_DATA))
    # 版本号动态读取（pyproject.toml → 避免硬编码漂移）
    _version_tag = "v?"
    try:
        from pathlib import Path as _P
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        _pyproject = _P(__file__).resolve().parent.parent / "pyproject.toml"
        if _pyproject.exists():
            with open(_pyproject, "rb") as _f:
                _data = tomllib.load(_f)
            _version_tag = "v" + _data.get("project", {}).get("version", "0.0.0")
    except Exception:  # noqa: S110
        pass
    parts.append(node(dx+20, ay+490, dw-40, 70, "GitHub Releases", f"{_version_tag} 标签", COL_DATA))

    # 横向箭头
    for x1_end, x2_start in [(ax+aw, bx), (bx+bw, cx), (cx+cw, dx)]:
        ay_arrow = ay + ah // 2
        parts.append(arrow(x1_end+5, ay_arrow, x2_start-5, ay_arrow, color="#5a6478"))

    # 底部：3 层安全
    y_sec = 800
    parts.append(section(60, y_sec, WIDTH-120, 110, "3 层安全边界 (3-Layer Security)", "#ef4444"))
    parts.append(f'<text x="200" y="{y_sec+45}" fill="{INK}" font-size="14" font-family="{FONT}">① Pre-commit: 检测私钥/AWS 凭据 + ruff + mypy</text>')
    parts.append(f'<text x="200" y="{y_sec+70}" fill="{INK}" font-size="14" font-family="{FONT}">② CI/CD: 3 OS matrix + pip-audit + secret scanning + dependabot</text>')
    parts.append(f'<text x="200" y="{y_sec+95}" fill="{INK}" font-size="14" font-family="{FONT}">③ Runtime: Keychain + .env 隔离 + 沙箱 AST 验证 + Halt rules</text>')

    parts.append(footer(5))
    return "\n".join(parts) + "\n</svg>\n"


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════
def main():
    generators = [
        ("01-architecture-overview.svg", gen_01_architecture_overview),
        ("02-skill-system-map.svg", gen_02_skill_system_map),
        ("03-mcp-ecosystem-map.svg", gen_03_mcp_ecosystem_map),
        ("04-research-pipeline.svg", gen_04_research_pipeline),
        ("05-deployment-data-flow.svg", gen_05_deployment_data_flow),
    ]
    print(f"生成 5 个架构图 → {OUT_DIR}")
    for name, gen in generators:
        svg = gen()
        fpath = os.path.join(OUT_DIR, name)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(svg)
        size = os.path.getsize(fpath)
        print(f"  ✅ {name} ({size} bytes)")


if __name__ == "__main__":
    main()
