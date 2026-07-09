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
    """papers/event_runs/ 和 papers/demo_*.tex 应在 .gitignore 中。

    背景: papers/ 目录现已包含有价值的学术输出（finai_methodology/ 论文、
    us_esg_financing/ ESG 融资研究），不应整体忽略。仅需忽略:
    1. event_runs/ — 自动生成的临时跑图文件
    2. demo_*.tex — 演示文件（已有 test_no_demo_tex_files 二次防护）
    """
    gitignore = (PROJECT_ROOT / ".gitignore").read_text()
    lines = [l.strip() for l in gitignore.splitlines() if l.strip() and not l.strip().startswith("#")]
    # 检查 event_runs/ 是否被忽略（最关键）
    has_event_runs_ignore = any(
        "event_runs" in line or line == "papers/event_runs/"
        for line in lines
    )
    # 检查 papers/ 整体是否被忽略（如果有，说明 finai_methodology/us_esg_financing
    # 被有意排除——但它们现在是有价值的学术输出）
    has_papers_ignore = any(
        line.strip() == "papers/" or line.strip() == "papers"
        for line in lines
    )
    assert has_event_runs_ignore, (
        "papers/event_runs/ 应在 .gitignore 中（自动生成文件）"
    )
