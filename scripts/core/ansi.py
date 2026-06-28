"""ANSI color helpers for CLI output.

P3-8 修复 2026-06-29: 提取自 scripts/mcp_diagnostic.py，让 agent_pipeline.py 等
其他需要 ANSI 颜色的脚本可复用。原来的 mcp_diagnostic.py 内部保留作为 fallback，
但统一入口是这个模块。

用法：
    from scripts.core.ansi import bold, cyan, dim, yellow, red
    print(bold(cyan("Hello")))
"""

from __future__ import annotations

__all__ = [
    "bold",
    "cyan",
    "dim",
    "yellow",
    "red",
    "green",
    "blue",
    "magenta",
]


def _ansi(code: str, text: str) -> str:
    """Wrap text in ANSI escape codes if stdout is a TTY."""
    import sys

    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    """Bold text."""
    return _ansi("1", text)


def dim(text: str) -> str:
    """Dim text (lower intensity)."""
    return _ansi("2", text)


def cyan(text: str) -> str:
    """Cyan text."""
    return _ansi("36", text)


def yellow(text: str) -> str:
    """Yellow text."""
    return _ansi("33", text)


def red(text: str) -> str:
    """Red text."""
    return _ansi("31", text)


def green(text: str) -> str:
    """Green text."""
    return _ansi("32", text)


def blue(text: str) -> str:
    """Blue text."""
    return _ansi("34", text)


def magenta(text: str) -> str:
    """Magenta text."""
    return _ansi("35", text)
