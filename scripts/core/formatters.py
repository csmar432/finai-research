"""共享格式化工具函数。

为经济金融研究框架各模块提供统一的格式化辅助函数，
避免在多个模块中重复实现相同逻辑（参见 v1.8.1 重构）。

典型用法:
    from scripts.core.formatters import significance_mark
    sig = significance_mark(0.023)  # -> "*"
"""

from __future__ import annotations


def significance_mark(pval: float) -> str:
    """将 p 值转换为 LaTeX/RegTable 风格的显著性星号标记。

    标准经济学顶刊（JFE/JF/RFS）显著性水平约定:
        - p < 0.001: ***
        - p < 0.01:  **
        - p < 0.05:  *
        - p < 0.10:  .

    Args:
        pval: p 值（可为 NaN，表示缺失）。

    Returns:
        "***" / "**" / "*" / "." / "" 五种结果之一。
    """
    if pval != pval:  # NaN check (works for float('nan'))
        return ""
    if pval < 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    if pval < 0.10:
        return "."
    return ""


__all__ = ["significance_mark"]
