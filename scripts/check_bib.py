#!/usr/bin/env python
"""
scripts/check_bib.py
检查 .tex 中 r"\\cite{}" 引用的 key 是否都在 .bib 中存在

用法:
  python scripts/check_bib.py                  # 检查整个项目
  python scripts/check_bib.py --strict         # 警告也当错误
  python scripts/check_bib.py output/          # 只检查指定目录

退出码: 0=全部引用找到, 1=有未定义引用
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set


# \cite{key1, key2, key3}  -- 各种 LaTeX cite 命令都匹配
# 注意: 不用 r-string 的"\\\\", 因为 (?:) 在 regex 里用单 \ 即可
CITE_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|citet\*|citep\*|citeauthor|citeyear|"
    r"parencite|textcite|footcite|autocite|fullcite|shortcite)"
    r"(?:\[[^\]]*\])?"
    r"\{([^{}]*)\}",
    re.DOTALL,
)

# \input{bibfile}  or  \bibliography{bibfile}  (无扩展名)
BIB_INPUT_PATTERN = re.compile(
    r"\\(?:bibliography|addbibresource|input|include)\{([^}]+)\}",
    re.DOTALL,
)

# .bib 文件中 @article{key, @book{key, 等
BIB_ENTRY_PATTERN = re.compile(
    r"@\w+\s*\{\s*([^,\s]+)\s*,",
    re.IGNORECASE,
)

# % 注释 (行内)
COMMENT_LINE = re.compile(r"^\s*%")


def strip_comments(text: str) -> str:
    """移除 % 开头的注释行 (粗略处理, 不处理行内 %)"""
    return "\n".join(
        line for line in text.split("\n")
        if not COMMENT_LINE.match(line)
    )


def extract_cite_keys(tex_content: str) -> Set[str]:
    r"""从 .tex 内容中提取所有 r"\cite{...}" 里的 key"""
    keys: Set[str] = set()
    stripped = strip_comments(tex_content)
    for match in CITE_PATTERN.finditer(stripped):
        body = match.group(1)
        # 拆分 key1, key2, [prefix]key3
        for raw_key in body.split(","):
            # 移除 [prefix] (如 \cite[p.~5]{key})
            key = re.sub(r"^\[.*?\]\s*", "", raw_key.strip())
            # 移除空格
            key = key.strip()
            if key and re.match(r"^[\w:.-]+$", key):
                keys.add(key)
    return keys


def extract_bib_keys(bib_content: str) -> Set[str]:
    """从 .bib 内容中提取所有 entry 的 key"""
    keys: Set[str] = set()
    for match in BIB_ENTRY_PATTERN.finditer(bib_content):
        keys.add(match.group(1).strip())
    return keys


def find_bib_files(tex_path: Path) -> list[Path]:
    """根据 .tex 的 \bibliography{...} 找到对应的 .bib 文件"""
    candidates: list[Path] = []
    if not tex_path.exists():
        return candidates

    try:
        content = tex_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return candidates

    project_root = Path(__file__).parent.parent
    search_dirs = [tex_path.parent, project_root]

    for match in BIB_INPUT_PATTERN.finditer(strip_comments(content)):
        body = match.group(1)
        for name in body.split(","):
            name = name.strip()
            if not name:
                continue
            # \bibliography{file} -> file.bib
            # \addbibresource{file.bib} -> file.bib
            bib_name = name if name.endswith(".bib") else name + ".bib"
            for sd in search_dirs:
                bib_path = sd / bib_name
                if bib_path.exists():
                    candidates.append(bib_path)
                    break

    # Fallback: 找同目录/上级/项目根的所有 .bib
    if not candidates:
        for sd in search_dirs:
            found = list(sd.rglob("*.bib"))
            if found:
                candidates.extend(found[:10])  # 限制数量
                break

    return list({c.resolve() for c in candidates})


def collect_all_bib_keys(search_root: Path) -> Dict[Path, Set[str]]:
    """扫描项目所有 .bib 文件, 返回 {bib_path: keys}"""
    bib_keys: Dict[Path, Set[str]] = {}
    for bib in search_root.rglob("*.bib"):
        if any(part.startswith(".") for part in bib.parts):
            continue
        try:
            content = bib.read_text(encoding="utf-8", errors="ignore")
            bib_keys[bib] = extract_bib_keys(content)
        except Exception as e:
            print(f"⚠️  Failed to read {bib}: {e}", file=sys.stderr)
    return bib_keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description=r"Check LaTeX \cite{} references against .bib entries"
    )
    parser.add_argument("path", nargs="?", default=".", help="Search root (default: cwd)")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    search_root = Path(args.path).resolve()
    if not search_root.exists():
        print(f"❌ Path not found: {search_root}", file=sys.stderr)
        return 1

    print(f"🔍 Scanning {search_root} for .tex and .bib files...")
    print()

    # 1. 收集所有 .bib keys
    all_bib_keys: Dict[Path, Set[str]] = collect_all_bib_keys(search_root)
    if not all_bib_keys:
        print("⚠️  No .bib files found - skipping check")
        return 0
    total_bib_keys: Set[str] = set()
    for keys in all_bib_keys.values():
        total_bib_keys |= keys
    print(f"📚 Found {len(all_bib_keys)} .bib file(s) with {len(total_bib_keys)} total entries")
    for bib, keys in all_bib_keys.items():
        print(f"   - {bib.relative_to(search_root)}: {len(keys)} entries")
    print()

    # 2. 扫描所有 .tex 收集 \cite
    tex_files = [t for t in search_root.rglob("*.tex")
                 if not any(p.startswith(".") for p in t.parts)]
    if not tex_files:
        print("⚠️  No .tex files found - skipping check")
        return 0
    print(f"📄 Found {len(tex_files)} .tex file(s) to check")
    print()

    # 3. 逐个 .tex 检查
    missing_report: Dict[str, list[str]] = defaultdict(list)  # key -> [tex_files]
    total_cites = 0
    total_unique = 0

    for tex in tex_files:
        try:
            content = tex.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"⚠️  Failed to read {tex}: {e}", file=sys.stderr)
            continue

        cite_keys = extract_cite_keys(content)
        if not cite_keys:
            continue

        total_cites += sum(len(line.split(",")) for line in [
            m.group(1) for m in CITE_PATTERN.finditer(strip_comments(content))
        ])
        total_unique += len(cite_keys)

        # 找到该 tex 引用的 .bib
        local_bibs = find_bib_files(tex)
        local_keys: Set[str] = set()
        for bib in local_bibs:
            if bib in all_bib_keys:
                local_keys |= all_bib_keys[bib]

        # 优先在 local 检查, fallback 到 global
        check_against = local_keys if local_keys else total_bib_keys

        for key in cite_keys:
            if key not in check_against:
                missing_report[key].append(str(tex.relative_to(search_root)))

    # 4. 输出报告
    report_lines = []
    report_lines.append("# BibTeX Reference Check Report")
    report_lines.append("")
    report_lines.append(f"- .bib files: **{len(all_bib_keys)}**")
    report_lines.append(f"- .tex files: **{len(tex_files)}**")
    report_lines.append(f"- Total \\cite commands: **{total_cites}**")
    report_lines.append(f"- Unique keys cited: **{total_unique}**")
    report_lines.append("")

    if not missing_report:
        report_lines.append("✅ **All \\cite{} references resolved successfully.**")
        print("\n".join(report_lines))
        try:
            Path("bib_check_report.md").write_text("\n".join(report_lines), encoding="utf-8")
        except Exception:  # noqa: S110
            pass
        print()
        print("✅ All \\cite{} references resolved successfully!")
        return 0

    report_lines.append(f"❌ **{len(missing_report)} undefined reference(s) found:**")
    report_lines.append("")
    report_lines.append("| Missing Key | Used In |")
    report_lines.append("|-------------|---------|")
    for key in sorted(missing_report.keys()):
        files = missing_report[key]
        files_short = ", ".join(f"`{f}`" for f in files[:5])
        if len(files) > 5:
            files_short += f" ... (+{len(files)-5} more)"
        report_lines.append(f"| `{key}` | {files_short} |")
    report_lines.append("")

    report_md = "\n".join(report_lines)
    try:
        Path("bib_check_report.md").write_text(report_md, encoding="utf-8")
    except Exception:  # noqa: S110
        pass

    print(report_md)
    return 1


if __name__ == "__main__":
    sys.exit(main())
