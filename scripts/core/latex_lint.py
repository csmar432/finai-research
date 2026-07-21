"""LaTeX 即时验证 — 不编译检测常见错误.

功能：
  - 正则表达式即时验证（无需完整编译）
  - 交叉引用一致性检查（\\ref / \\label）
  - 参考文献完整性检查（\\cite）
  - 图表/表格/公式编号一致性
  - 常见语法错误检测

与 TexGuardian 的区别：
  - 本模块专注于**即时验证**（sub-second）
  - 不依赖 VLM，适合 CI/CD 集成
  - 适合在写作过程中实时反馈

Usage:
    checker = LatexLintChecker("papers/main.tex")
    issues = checker.check_all()
    for issue in issues:
        print(f"[{issue.severity}] Line {issue.line}: {issue.message}")

    # CI/CD 集成：零错误退出
    if checker.has_errors():
        sys.exit(1)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["LatexLintChecker", "LintIssue", "Severity"]

logger = logging.getLogger(__name__)


class Severity:
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class LintIssue:
    """
    单条 LaTeX lint 问题。

    Attributes
    ----------
    severity : str
        ERROR / WARNING / INFO。
    line : int
        行号（1-indexed）。
    message : str
        问题描述。
    rule : str
        触发此问题的规则名称。
    context : str
        出错行的上下文内容。
    """

    severity: str
    line: int
    message: str
    rule: str
    context: str = ""
    suggestion: str = ""


class LatexLintChecker:
    """
    LaTeX 即时验证器 — 基于正则表达式的快速检查。

    检查规则：

    | # | 规则 | 严重程度 | 说明 |
    |---|------|---------|------|
    | R1 | 孤立 \\ref | ERROR | \\ref{key} 但无对应 \\label{key} |
    | R2 | 孤立 \\label | ERROR | \\label{key} 但无对应 \\ref{key}（warning） |
    | R3 | 孤立 \\cite | ERROR | \\cite{key} 但无参考文献条目 |
    | R4 | 重复 \\label | WARNING | 同一文件内重复 label |
    | R5 | 未关闭环境 | ERROR | \\begin{xxx} 无对应 \\end{xxx} |
    | R6 | 未关闭数学模式 | WARNING | $ / $$ 不匹配 |
    | R7 | 缺失 \\caption | WARNING | figure/table 环境无 caption |
    | R8 | 缺失 \\label | WARNING | figure/table 环境无 label |
    | R9 | 缺失 \\bibliography | WARNING | 文档无参考文献 |
    | R10 | 表格列数不匹配 | ERROR | \\tabular 含 N 列但某行只有 M 项 |

    Usage
    -----
        checker = LatexLintChecker("papers/main.tex")
        issues = checker.check_all()
        print(f"Found {len(issues)} issues")
        checker.print_report()
    """

    def __init__(self, tex_path: str | Path):
        self.tex_path = Path(tex_path)
        self.content = ""
        self.lines: list[str] = []
        self.issues: list[LintIssue] = []
        self._load()

    def _load(self):
        if self.tex_path.exists():
            self.content = self.tex_path.read_text(encoding="utf-8")
            self.lines = self.content.split("\n")
        else:
            self.issues.append(LintIssue(
                severity=Severity.ERROR,
                line=0,
                message=f"File not found: {self.tex_path}",
                rule="file_exists",
            ))

    # ── Regex patterns ─────────────────────────────────────────────────

    # R1: \ref{...}
    REF_PATTERN = re.compile(r"\\ref\{([^}]+)\}")
    # R2: \label{...}
    LABEL_PATTERN = re.compile(r"\\label\{([^}]+)\}")
    # R3: \cite{...} or \citep{...} or \citet{...}
    CITE_PATTERN = re.compile(r"\\cite[pt]?\{([^}]+)\}")
    # R4: figure/table environments
    BEGIN_ENV = re.compile(r"\\begin\{([^}]+)\}")
    END_ENV = re.compile(r"\\end\{([^}]+)\}")
    # R5: caption
    CAPTION_PATTERN = re.compile(r"\\caption(\[[^\]]*\])?\{")
    # R6: math modes
    MATH_INLINE = re.compile(r"\$([^\$]+)\$")
    MATH_DISPLAY = re.compile(r"\$\$([^\$]+)\$\$")
    # R7: bibliography
    BIBLIOGRAPHY = re.compile(r"\\bibliography\{([^}]+)\}")
    # R8: tabular columns
    TABULAR_COLS = re.compile(r"\{([clr|p{.*?}]+(?:\s*[clr|p{.*?}]*)*)\}")
    # R9: include/input
    INPUT_PATTERN = re.compile(r"\\(?:input|include)\{([^}]+)\}")

    # ── Check methods ───────────────────────────────────────────────────

    def check_all(self) -> list[LintIssue]:
        """运行所有检查规则。"""
        self.issues = []
        if not self.tex_path.exists():
            return self.issues

        self._check_refs()
        self._check_labels()
        self._check_citations()
        self._check_env_balance()
        self._check_math_balance()
        self._check_figures_tables()
        self._check_bibliography()
        self._check_tabular_columns()
        return self.issues

    def _check_refs(self):
        """R1: 孤立 \\ref（无对应 \\label）。"""
        refs = set()
        for i, line in enumerate(self.lines, 1):
            for m in self.REF_PATTERN.finditer(line):
                refs.add((m.group(1), i, line.strip()))

        # 构建 label 集合（包含本文件和所有 input 文件）
        all_labels = self._get_all_labels()
        self._get_all_bib_entries()

        for key, line_no, context in refs:
            if key not in all_labels:
                self.issues.append(LintIssue(
                    severity=Severity.ERROR,
                    line=line_no,
                    message=f"\\ref{{{key}}} — no matching \\label{{{key}}}",
                    rule="orphan_ref",
                    context=context,
                    suggestion=f"Add \\label{{{key}}} in a figure, table, or equation environment",
                ))

    def _check_labels(self):
        """R2: 孤立 \\label（无对应 \\ref）或重复 label。"""
        labels: dict[str, list[tuple[int, str]]] = {}
        for i, line in enumerate(self.lines, 1):
            for m in self.LABEL_PATTERN.finditer(line):
                key = m.group(1)
                labels.setdefault(key, []).append((i, line.strip()))

        refs = set(m.group(1) for line in self.lines for m in self.REF_PATTERN.finditer(line))

        for key, occurrences in labels.items():
            # 重复 label
            if len(occurrences) > 1:
                for line_no, context in occurrences:
                    self.issues.append(LintIssue(
                        severity=Severity.WARNING,
                        line=line_no,
                        message=f"Duplicate \\label{{{key}}} (defined {len(occurrences)} times)",
                        rule="duplicate_label",
                        context=context,
                        suggestion="Use unique label names",
                    ))
            # 孤立 label（无 ref）
            if key not in refs:
                line_no, context = occurrences[0]
                self.issues.append(LintIssue(
                    severity=Severity.INFO,
                    line=line_no,
                    message=f"\\label{{{key}}} — no corresponding \\ref{{{key}}}",
                    rule="orphan_label",
                    context=context,
                    suggestion="Add \\ref{{{key}}} where this label is referenced",
                ))

    def _check_citations(self):
        """R3: 孤立 \\cite（无参考文献条目）。"""
        cites: dict[str, list[tuple[int, str]]] = {}
        for i, line in enumerate(self.lines, 1):
            for m in self.CITE_PATTERN.finditer(line):
                key = m.group(1)
                cites.setdefault(key, []).append((i, line.strip()))

        all_bibs = self._get_all_bib_entries()

        for key, occurrences in cites.items():
            if key not in all_bibs:
                line_no, context = occurrences[0]
                self.issues.append(LintIssue(
                    severity=Severity.ERROR,
                    line=line_no,
                    message=f"\\cite{{{key}}} — no matching BibTeX entry",
                    rule="orphan_cite",
                    context=context,
                    suggestion="Add @article/{key} (or similar) to your .bib file",
                ))

    def _check_env_balance(self):
        """R4: 环境未关闭（begin/end 不匹配）。"""
        stack: list[tuple[str, int]] = []
        for i, line in enumerate(self.lines, 1):
            for m in self.BEGIN_ENV.finditer(line):
                env = m.group(1)
                stack.append((env, i))
            for m in self.END_ENV.finditer(line):
                env = m.group(1)
                if stack and stack[-1][0] == env:
                    stack.pop()
                else:
                    self.issues.append(LintIssue(
                        severity=Severity.ERROR,
                        line=i,
                        message=f"\\end{{{env}}} — no matching \\begin{{{env}}}",
                        rule="unmatched_end",
                        context=line.strip(),
                    ))

        for env, line_no in stack:
            self.issues.append(LintIssue(
                severity=Severity.ERROR,
                line=line_no,
                message=f"\\begin{{{env}}} — no matching \\end{{{env}}}",
                rule="unclosed_env",
                context=self.lines[line_no - 1].strip() if line_no <= len(self.lines) else "",
            ))

    def _check_math_balance(self):
        """R5: 数学模式不匹配。"""
        inline_math = list(self.MATH_INLINE.finditer(self.content))
        display_math = list(self.MATH_DISPLAY.finditer(self.content))

        # 简单检查：计数是否偶数（不完美，但对大多数情况有效）
        if len(inline_math) % 2 != 0:
            self.issues.append(LintIssue(
                severity=Severity.WARNING,
                line=0,
                message=f"Unmatched inline math $...$ (count={len(inline_math)}, expected even)",
                rule="unmatched_math",
            ))
        if len(display_math) % 2 != 0:
            self.issues.append(LintIssue(
                severity=Severity.WARNING,
                line=0,
                message=f"Unmatched display math $$...$$ (count={len(display_math)}, expected even)",
                rule="unmatched_display_math",
            ))

    def _check_figures_tables(self):
        """R6+R7: figure/table 环境缺失 caption 或 label。"""
        for env_name in ["figure", "table"]:
            lines_with_env = []
            for i, line in enumerate(self.lines, 1):
                if f"\\begin{{{env_name}}}" in line:
                    lines_with_env.append(i)

            for start_line in lines_with_env:
                end_line = self._find_env_end(start_line, env_name)
                env_lines = self.lines[start_line - 1 : end_line]
                env_content = "\n".join(env_lines)

                if not self.CAPTION_PATTERN.search(env_content):
                    self.issues.append(LintIssue(
                        severity=Severity.WARNING,
                        line=start_line,
                        message=f"\\begin{{{env_name}}} missing \\caption",
                        rule="missing_caption",
                        context=env_lines[0].strip() if env_lines else "",
                        suggestion=f"Add \\caption{{...}} inside the {env_name} environment",
                    ))

                if not self.LABEL_PATTERN.search(env_content):
                    self.issues.append(LintIssue(
                        severity=Severity.WARNING,
                        line=start_line,
                        message=f"\\begin{{{env_name}}} missing \\label",
                        rule="missing_label",
                        context=env_lines[0].strip() if env_lines else "",
                        suggestion=f"Add \\label{{fig:xxx}} or \\label{{tab:xxx}} inside the {env_name} environment",
                    ))

    def _check_bibliography(self):
        """R8: 文档无参考文献。"""
        if not self.BIBLIOGRAPHY.search(self.content) and not self.content.startswith(r"%"):
            has_cites = bool(self.CITE_PATTERN.search(self.content))
            if has_cites:
                self.issues.append(LintIssue(
                    severity=Severity.WARNING,
                    line=0,
                    message="Document has \\cite but no \\bibliography",
                    rule="missing_bibliography",
                    suggestion="Add \\bibliography{refs} or \\bibliographystyle{...}",
                ))

    def _check_tabular_columns(self):
        """R9: tabular 列数不匹配。"""
        for i, line in enumerate(self.lines, 1):
            if "\\begin{tabular}" in line or "\\begin{tabular*}" in line:
                m = self.TABULAR_COLS.search(line)
                if not m:
                    continue
                # 计算声明列数
                col_str = m.group(1)
                declared = len([c for c in re.split(r"\s*", col_str) if c])

                # 找到 \\begin 和 \\end 之间的行
                end_line = self._find_env_end(i, "tabular")
                for j in range(i, min(end_line, len(self.lines))):
                    row_line = self.lines[j].strip()
                    if row_line.startswith("%") or not row_line:
                        continue
                    if row_line.startswith("\\hline") or row_line.startswith("\\cline"):
                        continue
                    if row_line.startswith("\\end"):
                        break
                    # 统计 & 分隔符数量（不含转义）
                    ampersands = row_line.count("&")
                    expected = declared - 1  # N 列 → N-1 个 &
                    if ampersands != expected and ampersands > 0:
                        self.issues.append(LintIssue(
                            severity=Severity.ERROR,
                            line=j + 1,
                            message=(
                                f"Tabular row has {ampersands} & separators "
                                f"but {declared} columns declared ({expected} expected)"
                            ),
                            rule="tabular_column_mismatch",
                            context=row_line,
                            suggestion="Check column alignment (& separators) in this row",
                        ))

    # ── Helpers ────────────────────────────────────────────────────────

    def _find_env_end(self, begin_line: int, env_name: str) -> int:
        """找到环境的 \\end 行号。"""
        for i in range(begin_line, len(self.lines)):
            if f"\\end{{{env_name}}}" in self.lines[i]:
                return i
        return len(self.lines)

    def _get_all_labels(self) -> set[str]:
        """收集本文件和所有 input 文件的 label。"""
        labels: set[str] = set()
        for m in self.LABEL_PATTERN.finditer(self.content):
            labels.add(m.group(1))

        # 递归处理 input 文件
        for m in self.INPUT_PATTERN.finditer(self.content):
            inc_path = self.tex_path.parent / m.group(1)
            if inc_path.suffix == "":
                inc_path = inc_path.with_suffix(".tex")
            if inc_path.exists():
                try:
                    inc_content = inc_path.read_text(encoding="utf-8")
                    for sub_m in self.LABEL_PATTERN.finditer(inc_content):
                        labels.add(sub_m.group(1))
                except Exception:
                    pass

        return labels

    def _get_all_bib_entries(self) -> set[str]:
        """收集所有 .bib 文件中的文献 key。"""
        bib_keys: set[str] = set()

        # 从 \bibliography{file} 获取 bib 文件
        for m in self.BIBLIOGRAPHY.finditer(self.content):
            bib_name = m.group(1)
            bib_path = self.tex_path.parent / f"{bib_name}.bib"
            if bib_path.exists():
                try:
                    bib_content = bib_path.read_text(encoding="utf-8")
                    # 匹配 @article{key 或 @book{key 等
                    for bib_m in re.finditer(r"@\w+\{([^,]+)", bib_content):
                        bib_keys.add(bib_m.group(1).strip())
                except Exception:
                    pass

        return bib_keys

    # ── Report ────────────────────────────────────────────────────────

    def has_errors(self) -> bool:
        """返回 True 表示有 ERROR 级别问题。"""
        return any(i.severity == Severity.ERROR for i in self.issues)

    def has_warnings(self) -> bool:
        """返回 True 表示有 WARNING 级别问题。"""
        return any(i.severity == Severity.WARNING for i in self.issues)

    def print_report(self, file=None):
        """打印格式化报告。"""
        if not self.issues:
            print("✅ LaTeX lint: No issues found", file=file)
            return

        error_count = sum(1 for i in self.issues if i.severity == Severity.ERROR)
        warn_count = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in self.issues if i.severity == Severity.INFO)

        print(f"LaTeX Lint Report: {len(self.issues)} issues", file=file)
        print(f"  {'🔴' if error_count else '  '} ERROR  : {error_count}", file=file)
        print(f"  {'🟡' if warn_count else '  '} WARNING: {warn_count}", file=file)
        print(f"  {'🔵' if info_count else '  '} INFO   : {info_count}", file=file)
        print(file=file)

        for issue in self.issues:
            icon = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(issue.severity, "  ")
            line_str = f"L{issue.line:>4d}" if issue.line > 0 else "    "
            print(
                f"  {icon} {line_str} [{issue.rule}] {issue.message}",
                file=file,
            )
            if issue.context:
                print(f"         Context: {issue.context[:80]}", file=file)
            if issue.suggestion:
                print(f"         → {issue.suggestion}", file=file)

    def get_grouped_report(self) -> dict[str, list[dict]]:
        """按规则分组的问题报告。"""
        grouped: dict[str, list[dict]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.rule, []).append({
                "severity": issue.severity,
                "line": issue.line,
                "message": issue.message,
                "context": issue.context,
                "suggestion": issue.suggestion,
            })
        return grouped
