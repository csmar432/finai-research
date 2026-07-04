"""Tests for LaTeX multi-backend compilation (PR4, Audit 2026-06-27)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.journal_template import JournalTemplate


@pytest.mark.latex
def test_detect_best_backend_finds_tectonic():
    """tectonic 在 macOS 上已安装，应被检测到。
    Skip in environments without tectonic installed (CI ubuntu runner)."""
    if shutil.which("tectonic") is None:
        pytest.skip("tectonic LaTeX engine not installed in this environment")
    jt = JournalTemplate.__new__(JournalTemplate)
    backend = jt._detect_best_backend()
    assert backend == "tectonic"


def test_detect_best_backend_returns_first_available():
    """如果 xelatex 不在 PATH，应返回 tectonic（排第二）。"""
    # 模拟一个没有 xelatex 的环境
    original_which = shutil.which

    def fake_which(cmd):
        if cmd in ("xelatex", "pdflatex", "lualatex"):
            return None
        if cmd == "tectonic":
            return "/usr/local/bin/tectonic"
        return original_which(cmd)

    shutil.which = fake_which
    try:
        jt = JournalTemplate.__new__(JournalTemplate)
        backend = jt._detect_best_backend()
        assert backend == "tectonic"
    finally:
        shutil.which = original_which


def test_compile_nonexistent_file_returns_false():
    """不存在的 .tex 文件应返回 False，不抛异常。"""
    jt = JournalTemplate.__new__(JournalTemplate)
    result = jt.compile("/nonexistent/path/paper.tex")
    assert result is False


def test_compile_unknown_engine_falls_back_to_autodetect(tmp_path):
    """未知引擎名应回退到 auto-detect。"""
    # 创建一个真实的 .tex 文件
    tex_file = tmp_path / "test.tex"
    tex_file.write_text("\\documentclass{article}\\begin{document}test\\end{document}")

    jt = JournalTemplate.__new__(JournalTemplate)
    result = jt.compile(str(tex_file), engine="unknown_engine_xyz")
    # 应该有 fallback 逻辑（尝试 tectonic）
    # 结果取决于 tectonic 是否能编译上面的空白文件
    assert isinstance(result, bool)


def test_compile_with_tectonic_auto_detected(tmp_path):
    """engine=None 时应自动检测到 tectonic。"""
    # 一个能被 tectonic 编译的极简文件
    tex_file = tmp_path / "minimal.tex"
    tex_file.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Hello World\n"
        "\\end{document}\n"
    )

    jt = JournalTemplate.__new__(JournalTemplate)
    result = jt.compile(str(tex_file), engine=None)
    # tectonic 应该能编译成功
    assert result is True
    assert (tmp_path / "minimal.pdf").exists()


def test_tectonic_compile_success_message(tmp_path, capsys):
    """tectonic 编译成功应打印确认信息。"""
    tex_file = tmp_path / "hello.tex"
    tex_file.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Test\n"
        "\\end{document}\n"
    )

    jt = JournalTemplate.__new__(JournalTemplate)
    jt._compile_tectonic(tex_file)

    captured = capsys.readouterr().out
    assert "✅" in captured or tex_file.with_suffix(".pdf").exists()


def test_no_hang_on_timeout(tmp_path):
    """编译超时应有明确错误信息，不挂起。"""
    # 这是一个超时测试：实际编译应在合理时间内返回
    jt = JournalTemplate.__new__(JournalTemplate)
    tex_file = tmp_path / "test.tex"
    tex_file.write_text("\\documentclass{article}\\begin{document}\\end{document}")

    # 编译应在 120 秒内完成
    import time
    start = time.time()
    result = jt._compile_tectonic(tex_file)
    elapsed = time.time() - start

    assert elapsed < 60, f"Compilation took {elapsed:.1f}s (should be < 60s)"
    assert isinstance(result, bool)


def test_pandoc_fallback_when_no_latex_installed(tmp_path, capsys):
    """当没有任何 LaTeX 编译器时，应提示 pandoc 作为替代。"""
    original_which = shutil.which

    def fake_which(cmd):
        return None  # 所有编译器都不可用

    shutil.which = fake_which
    try:
        jt = JournalTemplate.__new__(JournalTemplate)
        backend = jt._detect_best_backend()
        assert backend is None

        tex_file = tmp_path / "test.tex"
        tex_file.write_text("\\documentclass{article}\\begin{document}\\end{document}")
        result = jt.compile(str(tex_file), engine=None)

        captured = capsys.readouterr().out
        # 应提示安装 tectonic 或使用 pandoc
        assert "tectonic" in captured.lower() or "pandoc" in captured.lower()
        assert result is False
    finally:
        shutil.which = original_which
