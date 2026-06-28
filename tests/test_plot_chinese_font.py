"""matplotlib 中文字体配置测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_setup_chinese_font_returns_font_or_none():
    """setup_chinese_font 应该返回找到的字体名或 None。"""
    import matplotlib

    from scripts.plot_utils import setup_chinese_font

    result = setup_chinese_font(verbose=False)
    # result 可能是字体名字符串或 None（系统无中文）
    assert result is None or isinstance(result, str)

    # 应已配置 matplotlib rcParams
    sans_serif = matplotlib.rcParams["font.sans-serif"]
    assert isinstance(sans_serif, list)


def test_get_cjk_font_returns_str_or_none():
    """get_cjk_font 应返回字体名或 None。"""
    from scripts.plot_utils import get_cjk_font

    result = get_cjk_font()
    assert result is None or isinstance(result, str)


def test_setup_chinese_font_sets_unicode_minus():
    """setup_chinese_font 应设置 axes.unicode_minus=False（解决负号方块）。"""
    import matplotlib

    from scripts.plot_utils import setup_chinese_font

    setup_chinese_font(verbose=False)
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_font_keywords_has_macos_linux_windows():
    """应覆盖三大平台字体。"""
    from scripts.plot_utils import CJK_FONT_KEYWORDS

    keywords_lower = " ".join(CJK_FONT_KEYWORDS).lower()
    # macOS
    assert any(k in keywords_lower for k in ["heiti", "songti", "pingfang", "hiragino"])
    # Linux
    assert any(k in keywords_lower for k in ["noto sans cjk", "wqy"])
    # Windows
    assert any(k in keywords_lower for k in ["simhei", "simsun", "yahei"])


def test_font_added_to_sans_serif_list():
    """找到中文字体时，应被添加到 matplotlib font.sans-serif 第一位。"""
    from scripts.plot_utils import setup_chinese_font, get_cjk_font

    import matplotlib

    # 重置
    matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]

    setup_chinese_font(verbose=False)
    found = get_cjk_font()
    if found:
        sans_serif = matplotlib.rcParams["font.sans-serif"]
        assert found in sans_serif
        assert sans_serif[0] == found, f"中文字体应放第一位，实际 {sans_serif[:3]}"