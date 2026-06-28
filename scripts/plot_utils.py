"""matplotlib 中文字体配置 helper。

P0 修复 2026-06-28：之前 plt.rcParams 只设 font.family="sans-serif"，
而 sans-serif 默认是 DejaVu Sans 等无中文支持的字体，
导致中文字符显示为方块。

本模块提供 setup_chinese_font()，自动探测系统可用中文字体并配置 matplotlib。

用法：
    from scripts.plot_utils import setup_chinese_font
    setup_chinese_font()  # 在 import pyplot 之前调用
    import matplotlib.pyplot as plt
"""

from __future__ import annotations

import matplotlib
import matplotlib.font_manager as fm

# 中文字体关键词（macOS / Linux / Windows 覆盖）
CJK_FONT_KEYWORDS = [
    "noto sans cjk",  # Linux (apt install fonts-noto-cjk)
    "wqy",            # Linux (WenQuanYi)
    "ar pl",          # Linux (AR PL)
    "simhei",         # Windows
    "microsoft yahei",  # Windows
    "simsun",         # Windows
    "heiti tc",       # macOS
    "songti tc",      # macOS
    "songti sc",      # macOS
    "heiti sc",       # macOS
    "stheit",         # macOS
    "pingfang",       # macOS
    "hiragino",       # macOS
    "arial unicode",  # 全平台 fallback
]


def _find_cjk_font() -> str | None:
    """在系统字体中找到第一个可用的中文字体名称。"""
    available = {f.name.lower(): f.name for f in fm.fontManager.ttflist}
    for kw in CJK_FONT_KEYWORDS:
        for name_lower, name_original in available.items():
            if kw in name_lower:
                return name_original
    return None


def setup_chinese_font(verbose: bool = False) -> str | None:
    """配置 matplotlib 使用中文字体。

    应在 `import matplotlib.pyplot` 之前调用。

    Args:
        verbose: True 时打印找到的字体名称

    Returns:
        找到的字体名称，未找到返回 None
    """
    # 强制重建字体缓存（防止 fontManager 未扫描新装字体）
    try:
        fm._load_fontmanager(try_read_cache=False)
    except Exception:
        pass

    cjk_font = _find_cjk_font()
    if cjk_font is None:
        if verbose:
            print(
                "[plot_utils] ⚠️ 未找到系统中文字体。"
                " 中文字符可能显示为方块。"
                " macOS 安装 PingFang/Microsoft YaHei；"
                " Linux: apt install fonts-noto-cjk；"
                " Windows: 安装 SimHei 或 Microsoft YaHei。"
            )
        # 至少把 font.sans-serif 设为空，让 matplotlib 走 unicode fallback
        matplotlib.rcParams["font.sans-serif"] = []
        matplotlib.rcParams["axes.unicode_minus"] = False
        return None

    # 把中文字体放到 sans-serif 第一位
    current = list(matplotlib.rcParams.get("font.sans-serif", []))
    if cjk_font not in current:
        current = [cjk_font] + current
    matplotlib.rcParams["font.sans-serif"] = current
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["axes.unicode_minus"] = False  # 解决负号方块

    if verbose:
        print(f"[plot_utils] ✅ matplotlib 中文字体: {cjk_font}")
    return cjk_font


def get_cjk_font() -> str | None:
    """不修改配置，仅查询系统中文字体。"""
    return _find_cjk_font()