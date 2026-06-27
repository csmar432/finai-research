"""scripts/papers/ 目录治理测试.

P0-G (audit 2026-06-28): papers/demo_*.tex 含空 abstract，用户观点
"案例留存只有负面影响"应用于 papers/ 演示文件。真实设计稿保留。
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPERS = PROJECT_ROOT / "papers"


def test_papers_dir_exists():
    """papers/ 目录必须存在。"""
    assert PAPERS.exists()


def test_no_demo_tex_files():
    """papers/ 不应再有 demo_*.tex 演示文件。

    Bug 历史：demo_000001_SZ.tex 含 94 行（含空 abstract），demo_outputs/
    重复。审计报告 2026-06-28 + 用户观点"案例留存只有负面影响"已删除。
    """
    for tex in PAPERS.rglob("*.tex"):
        if "demo" in tex.name.lower():
            pytest.fail(
                f"{tex.relative_to(PROJECT_ROOT)} 是 demo 文件，应已删除。"
                "如果是有意保留的，rename 为 'research_*' 或加 README 说明。"
            )


def test_refined_design_preserved():
    """REFINED_DESIGN.md（真实设计稿）应保留。"""
    refined = PAPERS / "us_esg_financing" / "REFINED_DESIGN.md"
    assert refined.exists(), "us_esg_financing/REFINED_DESIGN.md 是真实设计稿，不应删"


def test_papers_gitignored():
    """papers/ 应在 .gitignore 中（防止未来 demo 被 commit）。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text()
    # 应有 papers/ 这一行
    has_papers_ignore = any(
        line.strip() == "papers/" or line.strip().startswith("papers/")
        for line in gitignore.splitlines()
    )
    assert has_papers_ignore, "papers/ 应在 .gitignore 中"