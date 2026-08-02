"""Tests for fin-arch-diagram Skill integration.

A5: 验证 4 个 SKILL.md 文件都存在 + 关键字段齐全
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


# 4 个 skill 副本位置
SKILL_FILES = [
    REPO_ROOT / ".cursor" / "skills" / "fin-arch-diagram" / "SKILL.md",
    REPO_ROOT / ".claude" / "skills" / "fin-arch-diagram.md",
    REPO_ROOT / ".github" / "skills" / "fin-arch-diagram.md",
    REPO_ROOT / "knowledge" / "skills" / "fin-arch-diagram.md",
]


# 4 个 SKILL.md 都应存在
@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_skill_md_exists(skill_path: Path):
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"
    assert skill_path.stat().st_size > 0, f"SKILL.md 是空的: {skill_path}"


# Cursor 版要有完整 YAML frontmatter
def test_cursor_skill_has_frontmatter():
    p = SKILL_FILES[0]
    content = p.read_text(encoding="utf-8")
    assert content.startswith("---\n"), "缺少 YAML frontmatter"
    assert "name:" in content, "缺少 name 字段"
    assert "description:" in content, "缺少 description 字段"
    assert "trigger:" in content, "缺少 trigger 字段"


# Cursor 版要有触发关键词
def test_cursor_skill_has_keywords():
    p = SKILL_FILES[0]
    content = p.read_text(encoding="utf-8")
    for kw in ["架构图", "流程图", "层次图"]:
        assert kw in content, f"缺少触发关键词: {kw}"


# Claude / GitHub / Knowledge 三副本内容一致
def test_claude_github_knowledge_in_sync():
    contents = [
        SKILL_FILES[1].read_text(encoding="utf-8"),
        SKILL_FILES[2].read_text(encoding="utf-8"),
        SKILL_FILES[3].read_text(encoding="utf-8"),
    ]
    # 三份应一致（除了可能的末尾换行）
    base = contents[0].strip()
    for c in contents[1:]:
        assert c.strip() == base, "三个 SKILL.md 副本内容不一致"


# 4 个 SKILL.md 都要引用核心 Python 模块
@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_skill_md_references_core_modules(skill_path: Path):
    content = skill_path.read_text(encoding="utf-8")
    # Cursor 版一定要包含；其他副本可选
    if "cursor" in str(skill_path):
        assert "arch_diagram_gv" in content, "Cursor SKILL.md 缺少 arch_diagram_gv 引用"
        assert "draw_diagram" in content, "Cursor SKILL.md 缺少 draw_diagram 引用"


# 验证 arch_diagram_demos.py 存在
def test_demo_runner_exists():
    p = REPO_ROOT / "scripts" / "research_framework" / "arch_diagram_demos.py"
    assert p.exists(), f"demo runner 不存在: {p}"


# 验证 SCRIPTS_INDEX.md 包含 fin-arch-diagram 索引
def test_scripts_index_updated():
    p = REPO_ROOT / "scripts" / "SCRIPTS_INDEX.md"
    content = p.read_text(encoding="utf-8")
    assert "arch_diagram_demos" in content, "SCRIPTS_INDEX.md 未加 arch_diagram_demos 索引"


# 验证 CLAUDE.md 加了技能行
def test_claude_md_updated():
    p = REPO_ROOT / "CLAUDE.md"
    content = p.read_text(encoding="utf-8")
    assert "fin-arch-diagram" in content, "CLAUDE.md 未加 fin-arch-diagram"
