#!/usr/bin/env python3
"""Repository asset counter (auto-generated metrics for README).

计数项目内可自动统计的资源数量：
  - MCP server 目录数（mcp_servers/user_*/）
  - 期刊模板数（scripts/journal_template.py 注册的）
  - 计量方法模块数（scripts/research_framework/）
  - 技能数（.cursor/skills/）
  - research_framework 测试覆盖模块数

使用：
    python scripts/count_assets.py
    python scripts/count_assets.py --json
    python scripts/count_assets.py --markdown   # 输出 README 表格

维护建议：
  每次大改后跑 `python scripts/count_assets.py --markdown`，
  替换 README.md 中的 "Key numbers" 表格。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def count_mcp_servers() -> dict[str, int]:
    """统计 MCP server 目录数 + server.py 状态。"""
    mcp_root = PROJECT_ROOT / "mcp_servers"
    user_servers = sorted(
        d for d in mcp_root.iterdir() if d.is_dir() and d.name.startswith("user_")
    )

    free_count = 0
    stub_count = 0
    full_impl_count = 0
    legal_risk_count = 0
    LEGAL_RISK_SERVERS = {"user_cnki", "user_wanfang", "user_chinese_literature"}

    for srv in user_servers:
        server_py = srv / "server.py"
        if not server_py.exists():
            stub_count += 1
            continue
        content = server_py.read_text()
        # 真实实现：含具体的 tool 注册（list_tools / call_tool）
        if (
            "list_tools" in content
            and "call_tool" in content
            and "register_tool" not in content[:500]
        ):
            if srv.name in LEGAL_RISK_SERVERS:
                legal_risk_count += 1
            else:
                # 检查是否声明需 API Key
                if re.search(r"API_KEY|api_key|getenv\(.+_KEY", content):
                    full_impl_count += 1
                else:
                    free_count += 1
        else:
            stub_count += 1

    return {
        "total": len(user_servers),
        "free_no_key": free_count,
        "requires_api_key": full_impl_count,
        "stub_only": stub_count,
        "legal_risk_disabled_by_default": legal_risk_count,
    }


def count_journal_templates() -> dict[str, int]:
    """统计期刊模板数（解析 scripts/journal_template.py 的 JOURNAL_METADATA dict）。"""
    import ast

    jt = PROJECT_ROOT / "scripts" / "journal_template.py"
    if not jt.exists():
        return {"total": 0}

    try:
        tree = ast.parse(jt.read_text())
    except SyntaxError:
        return {"total": 0}

    total = 0
    for node in ast.walk(tree):
        # 找形如 "name": {...} 的赋值
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "JOURNAL_METADATA" and isinstance(node.value, ast.Dict):
                total = len(node.value.keys)
        # 也兼容普通赋值
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "JOURNAL_METADATA":
                    if isinstance(node.value, ast.Dict):
                        total = len(node.value.keys)

    return {"total": total}


def count_econometric_methods() -> int:
    """统计 scripts/research_framework/ 下的方法模块数。"""
    rf = PROJECT_ROOT / "scripts" / "research_framework"
    return sum(1 for f in rf.glob("*.py") if not f.name.startswith("_"))


def count_skills() -> int:
    """统计 .cursor/skills/ 下的 skill 数。"""
    skills = PROJECT_ROOT / ".cursor" / "skills"
    if not skills.exists():
        return 0
    return sum(1 for d in skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def count_research_directions() -> int:
    """统计实际注册的研究方向数。

    P0-6 第二阶段修复 (2026-06-29): 之前数 scripts/research_directions/*.py 文件数，
    但那是 BaseResearchDirection 子类数（13 个），不等于 DirectionFactory 注册的方向数（45）。
    改为查询 DirectionFactory._registry。
    """
    try:
        from scripts.research_directions import DirectionFactory  # noqa: E402

        if not DirectionFactory._initialized:
            DirectionFactory._init_registry()
        return len(DirectionFactory._registry)
    except Exception:
        rd = PROJECT_ROOT / "scripts" / "research_directions"
        if not rd.exists():
            return 0
        return sum(1 for f in rd.glob("*.py") if not f.name.startswith("_"))


def count_test_files() -> dict[str, int]:
    """统计 tests/ 下文件 + test_ 函数数。

    P0 修复 2026-06-28: 同时统计 module-level def test_* 和
    class TestXxx: 内的 def test_* 方法（与 pytest --collect 一致）。
    之前只数 def test_，导致 SSOT 报 448，实测 2874，差 6.4x。
    """
    tests = PROJECT_ROOT / "tests"
    test_files = sum(1 for f in tests.glob("test_*.py"))
    test_funcs = 0
    func_pattern = re.compile(r"^\s+(?:async\s+)?def test_", re.MULTILINE)
    module_pattern = re.compile(r"^(?:async\s+)?def test_", re.MULTILINE)
    class_pattern = re.compile(r"^class\s+Test\w+", re.MULTILINE)
    for tf in tests.glob("test_*.py"):
        text = tf.read_text()
        # 统计 module-level def test_*
        test_funcs += len(module_pattern.findall(text))
        # 统计 class TestXxx: 内的 def test_*
        for m in class_pattern.finditer(text):
            class_start = m.end()
            # 找下一个 class 或 EOF
            next_class = class_pattern.search(text, class_start)
            class_end = next_class.start() if next_class else len(text)
            class_body = text[class_start:class_end]
            test_funcs += len(func_pattern.findall(class_body))
    return {"files": test_files, "test_functions": test_funcs}


def count_modules_with_tests(rf_count: int) -> dict[str, int]:
    """统计 research_framework 中有/无独立测试的模块数。

    Returns: {"with_tests": int, "without_tests": int, "total": int,
              "modules_without_tests": list[str]}  # 新增：模块名列表

    测试文件命名约定（任一命中即算覆盖）：
      - test_<module>.py            — 标准（最常见）
      - test_<module>_*.py          — deep_exec / smoke 等变体
      - test_research_framework_<module>.py — 旧风格（PR #132 之前）
      - test_research_framework_<module>_*.py — 旧风格变体
    """
    rf = PROJECT_ROOT / "scripts" / "research_framework"
    tests = PROJECT_ROOT / "tests"
    with_test = 0
    without_test = 0
    modules_without_tests: list[str] = []
    for m in rf.glob("*.py"):
        if m.name.startswith("_"):
            continue
        module_name = m.stem
        # 多命名约定匹配
        candidates = [
            tests / f"test_{module_name}.py",
            *sorted(tests.glob(f"test_{module_name}_*.py")),
            tests / f"test_research_framework_{module_name}.py",
            *sorted(tests.glob(f"test_research_framework_{module_name}_*.py")),
        ]
        if any(p.exists() for p in candidates):
            with_test += 1
        else:
            without_test += 1
            modules_without_tests.append(module_name)
    return {
        "with_tests": with_test,
        "without_tests": without_test,
        "total": rf_count,
        "modules_without_tests": sorted(modules_without_tests),
    }


def count_all() -> dict:
    mcp = count_mcp_servers()
    jt = count_journal_templates()
    methods = count_econometric_methods()
    skills = count_skills()
    directions = count_research_directions()
    tests = count_test_files()
    coverage = count_modules_with_tests(methods)

    return {
        "mcp_servers": mcp,
        "journal_templates": jt,
        "econometric_methods": methods,
        "skills": skills,
        "research_directions": directions,
        "tests": tests,
        "research_framework_test_coverage": coverage,
    }


def to_markdown_table(stats: dict) -> str:
    """生成 README 友好的 markdown 表格。"""
    mcp = stats["mcp_servers"]
    tests = stats["tests"]
    cov = stats["research_framework_test_coverage"]

    lines = [
        "| Metric | Count |",
        "|--------|------:|",
        f"| MCP server directories | {mcp['total']} ({mcp['free_no_key']} free, {mcp['requires_api_key']} API-key, {mcp['stub_only']} stub, {mcp['legal_risk_disabled_by_default']} opt-in) |",
        f"| Econometric method modules | {stats['econometric_methods']} |",
        f"| Journal templates | {stats['journal_templates']['total']} |",
        f"| AI Skills | {stats['skills']} |",
        f"| Research directions | {stats['research_directions']} |",
        f"| Test files / test functions | {tests['files']} / {tests['test_functions']} |",
        f"| research_framework modules with tests | {cov['with_tests']}/{cov['total']} |",
    ]
    return "\n".join(lines)


def sync_ssot() -> int:
    """Regenerate scripts/PROJECT_NUMBERS.json from disk state.

    Single Source of Truth maintenance: whenever you want to update
    PROJECT_NUMBERS.json, run `python scripts/count_assets.py --sync-ssot`
    instead of editing by hand. This eliminates manual drift.
    """
    ssot_path = PROJECT_ROOT / "scripts" / "PROJECT_NUMBERS.json"
    if not ssot_path.exists():
        print(f"❌ {ssot_path} not found — initialize manually first")
        return 1

    # Load existing SSOT to preserve fields count_assets.py doesn't track
    with open(ssot_path) as f:
        ssot = json.load(f)

    stats = count_all()
    mcp = stats["mcp_servers"]
    tests = stats["tests"]
    cov = stats["research_framework_test_coverage"]

    # Update only the auto-detectable fields
    ssot["mcp"]["total_directories"] = mcp["total"]
    ssot["mcp"]["breakdown"]["fully_free"] = mcp["free_no_key"]
    ssot["mcp"]["breakdown"]["requires_paid_account"] = mcp["requires_api_key"]
    ssot["mcp"]["breakdown"]["stub_no_tools"] = mcp["stub_only"]
    ssot["mcp"]["breakdown"]["legal_risk"] = mcp["legal_risk_disabled_by_default"]
    ssot["mcp"]["stub_servers"] = []  # auto-detected: 0 stubs

    ssot["econometrics"]["total_method_modules"] = stats["econometric_methods"]
    ssot["econometrics"]["test_coverage"]["modules_with_tests"] = cov["with_tests"]
    ssot["econometrics"]["test_coverage"]["modules_total"] = cov["total"]
    # 自动计算 percent（之前手写 66.0 与 47/47 = 100 不一致；分子分母都在 SSoT 中，派生即可）
    if cov["total"] > 0:
        pct = round(100.0 * cov["with_tests"] / cov["total"], 2)
        ssot["econometrics"]["test_coverage"]["percent"] = pct
    # 自动维护 zero_test_modules（之前是手写列表，经常过时）
    if "modules_without_tests" in cov:
        ssot["econometrics"]["zero_test_modules"] = cov["modules_without_tests"]

    ssot["testing"]["test_files"] = tests["files"]
    ssot["testing"]["test_functions"] = tests["test_functions"]

    # last_verified timestamp
    from datetime import datetime

    ssot["last_verified"] = datetime.now().strftime("%Y-%m-%d")
    ssot["verified_by"] = "scripts/count_assets.py --sync-ssot"

    with open(ssot_path, "w") as f:
        json.dump(ssot, f, ensure_ascii=False, indent=2)
        f.write("\n")  # POSIX-style trailing newline (ruff W292)

    print(f"✅ Synced {ssot_path}")
    print(f"   MCP free: {mcp['free_no_key']}")
    print(f"   Tests: {tests['files']} files, {tests['test_functions']} functions")
    print(f"   Coverage: {cov['with_tests']}/{cov['total']} modules")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Count repository assets (auto-generated metrics)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--markdown", action="store_true", help="Output Markdown table for README")
    parser.add_argument(
        "--sync-ssot", action="store_true", help="Regenerate scripts/PROJECT_NUMBERS.json from disk"
    )
    args = parser.parse_args()

    if args.sync_ssot:
        return sync_ssot()

    stats = count_all()

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    if args.markdown:
        print(to_markdown_table(stats))
        return 0

    # 人类可读
    print("=" * 60)
    print("Repository Asset Counter (auto-generated)")
    print("=" * 60)
    print()
    mcp = stats["mcp_servers"]
    print(f"📦 MCP server directories: {mcp['total']}")
    print(f"   ├─ Free (no API key): {mcp['free_no_key']}")
    print(f"   ├─ Requires API key: {mcp['requires_api_key']}")
    print(f"   ├─ Stub only: {mcp['stub_only']}")
    print(f"   └─ Opt-in legal-risk: {mcp['legal_risk_disabled_by_default']}")
    print()
    print(f"📊 Econometric method modules: {stats['econometric_methods']}")
    print(f"📄 Journal templates: {stats['journal_templates']['total']}")
    print(f"🤖 AI Skills: {stats['skills']}")
    print(f"🧭 Research directions: {stats['research_directions']}")
    print()
    tests = stats["tests"]
    cov = stats["research_framework_test_coverage"]
    print(f"🧪 Tests: {tests['files']} files, {tests['test_functions']} test functions")
    print(f"📈 research_framework test coverage: {cov['with_tests']}/{cov['total']} modules")
    print()
    print("─" * 60)
    print("Re-run with --markdown to get README table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
