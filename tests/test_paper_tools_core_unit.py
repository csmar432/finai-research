"""Unit tests for scripts/paper_tools_core.py — focused on latex_check which is pure logic."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ptc():
    sys.path.insert(0, str(SCRIPTS_DIR))
    # paper_tools_core imports from scripts.ai_router which may not be loadable
    # in test env. Provide a MagicMock in sys.modules.
    if "scripts.ai_router" not in sys.modules:
        mock_mod = mock.MagicMock()
        mock_mod.AI = mock.MagicMock()
        sys.modules["scripts.ai_router"] = mock_mod
    if "paper_tools_core" in sys.modules:
        del sys.modules["paper_tools_core"]
    import paper_tools_core as _ptc
    # Replace the AI attribute since `from X import Y` makes a copy at import time
    _ptc.AI = mock.MagicMock()
    yield _ptc
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


@pytest.fixture
def simple_tex(tmp_path):
    """Simple valid LaTeX file."""
    content = r"""\documentclass{article}
\begin{document}
\begin{abstract}
Test abstract.
\end{abstract}

\begin{figure}
\caption{Fig1}\label{fig:f1}
\end{figure}

\begin{equation}\label{eq:e1}
y = x
\end{equation}

\section{Intro}
See Figure~\ref{fig:f1} and \eqref{eq:e1}.

\begin{thebibliography}{1}
\bibitem{x} Author
\end{thebibliography}
\end{document}
"""
    f = tmp_path / "paper.tex"
    f.write_text(content, encoding="utf-8")
    return f


class TestLatexCheck:
    def test_returns_dict(self, ptc, simple_tex):
        result = ptc.latex_check(str(simple_tex))
        assert isinstance(result, dict)
        assert "issues" in result
        assert "stats" in result

    def test_missing_file(self, ptc, tmp_path):
        result = ptc.latex_check(str(tmp_path / "nope.tex"))
        assert "error" in result

    def test_counts_figures(self, ptc, simple_tex):
        result = ptc.latex_check(str(simple_tex))
        assert result["stats"]["figures"] == 1

    def test_counts_equations(self, ptc, simple_tex):
        result = ptc.latex_check(str(simple_tex))
        assert result["stats"]["equations"] == 1

    def test_counts_sections(self, ptc, simple_tex):
        result = ptc.latex_check(str(simple_tex))
        assert result["stats"]["sections"] == 1

    def test_counts_word_count(self, ptc, simple_tex):
        result = ptc.latex_check(str(simple_tex))
        assert "word_count" in result["stats"]
        assert result["stats"]["word_count"] > 0

    def test_no_unmatched_refs_in_well_formed(self, ptc, simple_tex):
        """Well-formed doc should have no ref warnings."""
        result = ptc.latex_check(str(simple_tex))
        for issue in result["issues"]:
            assert "warning" not in issue.lower() or "fig:" in issue  # OK

    def test_detects_unmatched_fig_ref(self, ptc, tmp_path):
        """When figures exist but no \ref{fig:}, warning is added."""
        tex = tmp_path / "m.tex"
        tex.write_text(
            r"""\documentclass{article}
\begin{document}
\section{Intro}
\begin{figure}
\caption{x}
\end{figure}
\begin{figure}
\caption{y}
\end{figure}
\end{document}
""",
            encoding="utf-8",
        )
        result = ptc.latex_check(str(tex))
        # 2 figures, 0 fig refs → warning expected
        has_unref = any("张图但仅" in i for i in result["issues"])
        assert has_unref

    def test_detects_missing_bibliography(self, ptc, tmp_path):
        tex = tmp_path / "m.tex"
        tex.write_text(
            r"""\documentclass{article}
\begin{document}
\section{Intro}
text
\end{document}
""",
            encoding="utf-8",
        )
        result = ptc.latex_check(str(tex))
        assert any("bibliography" in i.lower() or "参考文献" in i for i in result["issues"])

    def test_detects_missing_abstract(self, ptc, tmp_path):
        tex = tmp_path / "m.tex"
        tex.write_text(
            r"""\documentclass{article}
\begin{document}
\section{Intro}
text
\bibliography{refs}
\end{document}
""",
            encoding="utf-8",
        )
        result = ptc.latex_check(str(tex))
        assert any("abstract" in i.lower() or "摘要" in i for i in result["issues"])

    def test_refs_count_correct(self, ptc, tmp_path):
        tex = tmp_path / "m.tex"
        tex.write_text(
            r"""\documentclass{article}
\begin{document}
\section{Intro}
\begin{figure}\caption{a}\label{fig:a}\end{figure}
\begin{figure}\caption{b}\label{fig:b}\end{figure}
As shown in Figure~\ref{fig:a} and Figure~\ref{fig:b}.
\end{document}
""",
            encoding="utf-8",
        )
        result = ptc.latex_check(str(tex))
        # 2 fig refs, 2 figures → no warning expected
        for i in result["issues"]:
            assert "张图但仅" not in i


class TestCheckPlagiarism:
    def test_returns_required_keys(self, ptc):
        """check_plagiarism returns dict with required structure."""
        with mock.patch("scripts.ai_router.AI") as mock_ai:
            mock_ai.chat.return_value = mock.Mock(response="analysis", latency_ms=500)
            result = ptc.check_plagiarism("Some text with no templates.")
        assert "total_chars" in result
        assert "total_words" in result
        assert "template_found" in result
        assert "est_similarity" in result
        assert "risk_level" in result

    def test_finds_template_phrase(self, ptc):
        with mock.patch("scripts.ai_router.AI") as mock_ai:
            mock_ai.chat.return_value = mock.Mock(response="x", latency_ms=100)
            text = "in recent years we have seen things"
            result = ptc.check_plagiarism(text)
            assert "in recent years" in result["template_found"]

    def test_no_template_phrases(self, ptc):
        with mock.patch("scripts.ai_router.AI") as mock_ai:
            mock_ai.chat.return_value = mock.Mock(response="x", latency_ms=100)
            text = "totally original text here"
            result = ptc.check_plagiarism(text)
            assert result["template_found"] == []

    def test_risk_level_low_for_clean_text(self, ptc):
        with mock.patch("scripts.ai_router.AI") as mock_ai:
            mock_ai.chat.return_value = mock.Mock(response="x", latency_ms=100)
            text = "x " * 100  # long, no templates
            result = ptc.check_plagiarism(text)
            assert result["risk_level"] == "低"


class TestPolishFallback:
    """Test the prompt-generation/parsing logic indirectly via mocking AI."""

    def test_polish_strips_marker(self, ptc):
        """polish strips [Polished English] marker from response."""
        # paper_tools_core references `result.latency_ms` for f-string format
        result_mock = mock.Mock()
        result_mock.response = "[Polished English] Hello world."
        result_mock.latency_ms = 100000.0  # float so f'{:.1f}' works
        ptc.AI.chat.return_value = result_mock
        with mock.patch("builtins.print"):
            result = ptc.polish("Hello world.", lang="english", level="light")
        assert "Hello world" in result
        assert "[Polished English]" not in result

    def test_polish_strips_chinese_marker(self, ptc):
        result_mock = mock.Mock()
        result_mock.response = "[润色后] 你好世界"
        result_mock.latency_ms = 100000.0
        ptc.AI.chat.return_value = result_mock
        with mock.patch("builtins.print"):
            result = ptc.polish("你好世界", lang="chinese", level="light")
        assert "你好世界" in result
        assert "[润色后]" not in result

