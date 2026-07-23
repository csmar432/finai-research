"""llm_reviewer.py 占位 DOI 回归测试 (P0-E, audit 2026-06-27).

确保未来不会引入新的虚构 DOI 模式（如 XXXXX、201XXXXX、jofi.XXXXX）。
"""

from __future__ import annotations

import re
from pathlib import Path


LLM_REVIEWER = Path(__file__).resolve().parent.parent / "scripts" / "core" / "llm_reviewer.py"


def test_no_placeholder_doi_in_llm_reviewer():
    """禁止出现虚构 DOI（XXXXX / 201XXXXX / jofi.XXXXX 等模式）。"""
    content = LLM_REVIEWER.read_text()
    # 常见占位模式
    forbidden_patterns = [
        r"DOI[:\s]+10\.\d+/\w+\.XXXXX",
        r"10\.1257/aer\.201X",       # AER placeholder
        r"10\.1111/jofi\.XXXXX",     # JofI placeholder
        r"10\.1016/j\.\w+\.XXXXX",   # Elsevier placeholder
        r"\bXXXXX\b",                 # 任何 XXXXX 残留
    ]
    violations = []
    for pattern in forbidden_patterns:
        for m in re.finditer(pattern, content):
            # 允许 docstring 注释中讨论占位 DOI（"removed 2026-06-27"）
            line_no = content[:m.start()].count("\n") + 1
            line = content.splitlines()[line_no - 1]
            if "placeholder removed" in line or "removed 2026" in line:
                continue
            violations.append(f"L{line_no}: {m.group()}")
    assert len(violations) == 0, (
        f"占位 DOI 残留（应在 2026-06-27 audit 中删除）:\n" + "\n".join(violations[:5])
    )


def test_no_placeholder_journal_suffix():
    """禁止出现 .XXXXX 期刊后缀（j.jfinec.2021.12.345 是真实格式，但 .XXXXX 不是）。"""
    content = LLM_REVIEWER.read_text()
    # 找 j.<journal>.XXXXX 模式
    pattern = r"j\.\w+\.XXXXX"
    matches = re.findall(pattern, content)
    assert len(matches) == 0, f"Found journal placeholder suffix: {matches}"
