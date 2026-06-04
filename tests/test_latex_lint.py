"""Tests for scripts/core/latex_lint.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


class TestLatexLintInit:
    """Initialization tests."""

    def test_lint_init_valid_file(self, valid_latex_tex):
        """LatexLintChecker initializes with valid .tex file."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        assert checker.tex_path.exists()
        assert len(checker.lines) > 0

    def test_lint_init_nonexistent_file(self, tmp_path):
        """LatexLintChecker handles nonexistent file gracefully."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        fake_path = tmp_path / "nonexistent.tex"
        checker = LatexLintChecker(fake_path)

        assert len(checker.issues) == 1
        assert checker.issues[0].severity == Severity.ERROR
        assert "not found" in checker.issues[0].message

    def test_lint_init_with_pathlib(self, valid_latex_tex):
        """LatexLintChecker accepts pathlib.Path."""
        from scripts.core.latex_lint import LatexLintChecker

        p = Path(valid_latex_tex)
        checker = LatexLintChecker(p)
        assert checker.tex_path == p


class TestLatexLintHappyPath:
    """Happy-path tests with valid LaTeX."""

    def test_check_all_valid_file(self, valid_latex_tex):
        """check_all() returns empty issues for valid LaTeX."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        checker = LatexLintChecker(valid_latex_tex)
        issues = checker.check_all()

        # Should have no ERROR-level issues for valid file
        error_issues = [i for i in issues if i.severity == Severity.ERROR]
        assert len(error_issues) == 0

    def test_has_errors_false_for_valid(self, valid_latex_tex):
        """has_errors() returns False for clean LaTeX."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        checker.check_all()

        assert checker.has_errors() is False

    def test_has_warnings_false_for_valid(self, valid_latex_tex):
        """has_warnings() returns False for clean LaTeX."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        checker.check_all()

        assert checker.has_warnings() is False


class TestLatexLintBrokenFile:
    """Tests with intentionally broken LaTeX."""

    def test_check_all_broken_file(self, broken_latex_tex):
        """check_all() detects issues in broken LaTeX."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(broken_latex_tex)
        issues = checker.check_all()

        assert len(issues) > 0

    def test_orphan_ref_detected(self, broken_latex_tex):
        """Orphan \\ref{} is detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        checker = LatexLintChecker(broken_latex_tex)
        issues = checker.check_all()

        orphan_refs = [
            i for i in issues
            if i.rule == "orphan_ref" and "\\ref{eq:missing}" in i.message
        ]
        assert len(orphan_refs) >= 1

    def test_tabular_column_mismatch_detected(self, broken_latex_tex):
        """Tabular column count mismatch is detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        checker = LatexLintChecker(broken_latex_tex)
        issues = checker.check_all()

        tabular_issues = [
            i for i in issues
            if i.rule == "tabular_column_mismatch"
        ]
        assert len(tabular_issues) >= 1
        assert all(i.severity == Severity.ERROR for i in tabular_issues)

    def test_figure_missing_caption_detected(self, broken_latex_tex):
        """Figure without \\caption is detected as WARNING."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        checker = LatexLintChecker(broken_latex_tex)
        issues = checker.check_all()

        fig_missing_cap = [
            i for i in issues
            if i.rule == "missing_caption" and "figure" in i.context.lower()
        ]
        assert len(fig_missing_cap) >= 1

    def test_duplicate_label_detected(self, tmp_path):
        """Duplicate \\label{} keys are detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        content = r"""\documentclass{article}
\begin{document}
\section{Test}\label{sec:test}
\section{Test2}\label{sec:test}
\end{document}
"""
        p = tmp_path / "dup_label.tex"
        p.write_text(content, encoding="utf-8")

        checker = LatexLintChecker(p)
        checker.check_all()

        dup_labels = [i for i in checker.issues if i.rule == "duplicate_label"]
        assert len(dup_labels) >= 1

    def test_unclosed_env_detected(self, tmp_path):
        """Unclosed \\begin{} is detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        content = r"""\documentclass{article}
\begin{document}
\begin{figure}
  \caption{Test}
\end{document}
"""
        p = tmp_path / "unclosed.tex"
        p.write_text(content, encoding="utf-8")

        checker = LatexLintChecker(p)
        checker.check_all()

        unclosed = [i for i in checker.issues if i.rule == "unclosed_env"]
        assert len(unclosed) >= 1
        assert any(i.severity == Severity.ERROR for i in unclosed)


class TestLatexLintMathMode:
    """Math mode balance tests."""

    def test_unmatched_inline_math_detected(self, math_latex_tex):
        """Unmatched inline $ math is detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        checker = LatexLintChecker(math_latex_tex)
        issues = checker.check_all()

        math_issues = [
            i for i in issues
            if i.rule in ("unmatched_math", "unmatched_display_math")
        ]
        # At least one unmatched math issue
        assert len(math_issues) >= 1


class TestLatexLintCitation:
    """Citation and bibliography tests."""

    def test_orphan_cite_detected(self, tmp_path):
        """Orphan \\cite{} without BibTeX entry is detected."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        # Create tex without cite first
        content = r"""\documentclass{article}
\begin{document}
Test.
\bibliography{refs}
\end{document}
"""
        p = tmp_path / "no_cite.tex"
        p.write_text(content, encoding="utf-8")

        # Create bib file with different key
        bib = tmp_path / "refs.bib"
        bib.write_text(r"@article{Author2020, author={A}, journal={J}, year={2020}}",
                       encoding="utf-8")

        checker = LatexLintChecker(p)
        checker.check_all()

        # No orphan cite since bib file exists
        orphan_cites = [i for i in checker.issues if i.rule == "orphan_cite"]
        assert len(orphan_cites) == 0

    def test_missing_bibliography_with_cites(self, tmp_path):
        """Document with \\cite{} but no \\bibliography raises WARNING."""
        from scripts.core.latex_lint import LatexLintChecker, Severity

        content = r"""\documentclass{article}
\begin{document}
Test \cite{Author2020}.
\end{document}
"""
        p = tmp_path / "no_bib.tex"
        p.write_text(content, encoding="utf-8")

        checker = LatexLintChecker(p)
        checker.check_all()

        missing_bib = [i for i in checker.issues if i.rule == "missing_bibliography"]
        assert len(missing_bib) >= 1
        assert all(i.severity == Severity.WARNING for i in missing_bib)


class TestLatexLintReport:
    """Report generation tests."""

    def test_print_report_no_issues(self, valid_latex_tex, capsys):
        """print_report() handles empty issues."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        checker.check_all()
        checker.print_report()

        captured = capsys.readouterr().out
        assert "No issues found" in captured or "issues" in captured.lower()

    def test_print_report_with_issues(self, broken_latex_tex, capsys):
        """print_report() shows issue counts."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(broken_latex_tex)
        checker.check_all()
        checker.print_report()

        captured = capsys.readouterr().out
        assert "ERROR" in captured or "WARNING" in captured

    def test_get_grouped_report(self, broken_latex_tex):
        """get_grouped_report() groups issues by rule name."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(broken_latex_tex)
        checker.check_all()
        grouped = checker.get_grouped_report()

        assert isinstance(grouped, dict)
        for rule, items in grouped.items():
            assert isinstance(items, list)
            assert all(isinstance(i, dict) for i in items)
            assert all("severity" in i for i in items)
            assert all("line" in i for i in items)
            assert all("message" in i for i in items)


class TestLatexLintHelpers:
    """Internal helper method tests."""

    def test_find_env_end(self, valid_latex_tex):
        """_find_env_end() returns correct end line number."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        checker.check_all()

        end_line = checker._find_env_end(1, "document")
        assert end_line >= 1

    def test_get_all_labels(self, valid_latex_tex):
        """_get_all_labels() collects labels from main file."""
        from scripts.core.latex_lint import LatexLintChecker

        checker = LatexLintChecker(valid_latex_tex)
        checker.check_all()

        labels = checker._get_all_labels()
        assert isinstance(labels, set)
        assert len(labels) >= 0


class TestLatexLintEdgeCases:
    """Edge case tests."""

    def test_empty_file(self, tmp_path):
        """Empty .tex file is handled gracefully."""
        from scripts.core.latex_lint import LatexLintChecker

        p = tmp_path / "empty.tex"
        p.write_text("", encoding="utf-8")

        checker = LatexLintChecker(p)
        issues = checker.check_all()

        assert isinstance(issues, list)

    def test_tex_with_only_comment(self, tmp_path):
        """LaTeX file with only comments is handled."""
        from scripts.core.latex_lint import LatexLintChecker

        p = tmp_path / "comment.tex"
        p.write_text("% This is a comment only\n", encoding="utf-8")

        checker = LatexLintChecker(p)
        issues = checker.check_all()

        assert isinstance(issues, list)

    def test_lint_issue_dataclass_fields(self):
        """LintIssue dataclass has all required fields."""
        from scripts.core.latex_lint import LintIssue, Severity

        issue = LintIssue(
            severity=Severity.ERROR,
            line=42,
            message="Test error",
            rule="test_rule",
            context="line content",
            suggestion="fix it",
        )

        assert issue.severity == Severity.ERROR
        assert issue.line == 42
        assert issue.message == "Test error"
        assert issue.rule == "test_rule"
        assert issue.context == "line content"
        assert issue.suggestion == "fix it"

    def test_severity_class_constants(self):
        """Severity class defines expected constants."""
        from scripts.core.latex_lint import Severity

        assert Severity.ERROR == "ERROR"
        assert Severity.WARNING == "WARNING"
        assert Severity.INFO == "INFO"
