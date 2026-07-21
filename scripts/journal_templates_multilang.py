"""多语言期刊模板扩展：日文 / 德文 / 欧洲经济期刊。

在 `journal_template.py` 的 JournalTemplate 数据模型基础上，
补充日文（JPE / RES / JSI）和德文（ZWiSt / AStA / JNS / Schmoll）期刊模板。

用法:
    from scripts.journal_templates_multilang import get_jpe, get_zwist, get_all_multilang

    t = get_jpe()
    t.generate_example("output/jpe_example.tex")
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── Re-use core JournalTemplate from journal_template.py ────────────────────────
from scripts.journal_template import JournalTemplate


# ═════════════════════════════════════════════════════════════════════════════════
# 日文期刊模板
# ╘════════════════════════════════════════════════════════════════════════════════

TEMPLATES: dict[str, JournalTemplate] = {}


# ─── JPE: Journal of Political Economy（日文版不代表日本期刊，此处补充日文经济学期刊）───

# JPE 已有于 journal_template.py，以下为日文经济学会期刊

# ─────────────────────────────────────────────────────────────────────────────
# 日文期刊 ①：JPE (Journal of Political Economy) — 芝加哥学派，不代表日本
#     注意：日文经济学期刊用罗马音首字母缩写，如下
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# 日文期刊 ②：RES (Review of Economic Studies) — 顶级理论期刊
#     已有于 journal_template.py (RFS)，此处仅作说明
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# 日文期刊 ③：日本経済学会機関誌（日本語経済学期刊）
#     Japanese Economic Review (JER) — Wiley 出版
#     Japanese Journal of Economics (JJIE) — 东京大学出版会
#     Asian Economic Journal (AEJ) — 亚洲经济学会
#     经济研究 (Kieru Kenkyu) — 一桥大学
#     经济学论丛 (Keizai Gaku) — 庆应义塾大学
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["Japanese Economic Review"] = JournalTemplate(
    name="Japanese Economic Review",
    short_name="JER",
    category="经济",
    description="日本经济学会主办，Wiley出版，亚洲经济学领域重要期刊",
    bibliography_style="econ",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "CJK", "uplatex"],
    page_limit="约30页",
    blind_review=True,
    url="https://onlinelibrary.wiley.com/journal/14680359",
    latex_code=r"""
% Japanese Economic Review (JER) LaTeX Template
% 日本経済学会機関誌 / Wiley Online Library
%
% 注意事项：
%   1. 使用 uplatex + jsarticle 编译（支持日文）
%   2. 参考文献格式：American Economic Review 风格
%   3. 双栏排版，单行长度较短
%
% 编译方式：
%   uplatex paper.tex && uplatex paper.tex && pbibtex paper && uplatex paper.tex && uplatex paper.tex
%

\documentclass[paper, a4j, twocolumn, 10pt]{jsarticle}
\usepackage{amsmath, amssymb, amsfonts}
\usepackage{graphicx}
\usepackage{cite}
\usepackage{url}
\usepackage{mathptmx}
\usepackage[T1]{fontenc}
\usepackage{textcomp}

% ── 页面设置 ──────────────────────────────────────────────────────────────
\pagestyle{plain}
\oddsidemargin 0.1in
\evensidemargin 0.1in
\textwidth 6.7in
\topmargin -0.3in
\textheight 9.2in

% ── 标题 ──────────────────────────────────────────────────────────────────
\title{タイトル：和政策が企業イノベーションに与える影響}
\author{
  著者名$^{1}$\footnote{ Corresponding author. E-mail: author@university.ac.jp } \\
  $^{1}$所属機関名 \\
  著者名$^{2}$ \\
  $^{2}$所属機関名
}
\date{\today}

\begin{document}
\maketitle

% ── 要旨 ──────────────────────────────────────────────────────────────────
\begin{abstract}
本稿では、排出権取引制度（ETS）が中国の工业企业のグリーンイノベーションに
与える影響を検証するため、二重差分法（DID）を適用した。
2010年から2022年までのA股上場企業2,847社のパネルデータを用いて分析した結果、
ETS参加企業は非参加企業と比較して、グリーンパテント件数が有意に増加することが判明した。
Parallel trend仮説も満たされている（F=1.23, p=0.287）。
 Robustness checks include IV estimation (historical SO2 as instrument, F=23.4),
 placebo tests, and alternative specifications.
本研究は、環境政策がイノベーションを促進する可能性を示唆するものである。
\textbf{キーワード}: 排出権取引、グリーンイノベーション、DID、中国
\end{abstract}

% ── JEL分类号 ─────────────────────────────────────────────────────────────
\textbf{JEL Classification}: Q58, O31, C23, R38

% ── 本文 ──────────────────────────────────────────────────────────────────
\section{はじめに}
\label{sec:intro}

% ── 参考文献 ──────────────────────────────────────────────────────────────
\bibliographystyle{econometrica}
\bibliography{references}

\end{document}
""",
)


TEMPLATES["JER"] = TEMPLATES["Japanese Economic Review"]


TEMPLATES["Japanese Journal of Income Distribution"] = JournalTemplate(
    name="Japanese Journal of Income Distribution",
    short_name="JJID",
    category="经济",
    description="日本 소득분포학회机关志，收入分配研究领域",
    bibliography_style="econ",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "CJK", "uplatex"],
    page_limit="约20页",
    blind_review=False,
    url="https://www.jstage.jst.go.jp/browse/jjid",
    latex_code=r"""
% Japanese Journal of Income Distribution (JJID) LaTeX Template
% 日本소득분포학회机关志
%
% 编译方式：uplatex + pbibtex

\documentclass[paper, a4j, twocolumn, 10pt]{jsarticle}
\usepackage{amsmath, amssymb, graphicx, cite}
\usepackage[T1]{fontenc}

\pagestyle{plain}
\textwidth 6.7in
\textheight 9.2in

\title{タイトル}
\author{
  氏名$^{1}$ \quad 氏名$^{2}$ \\
  $^{1}$所属 \quad $^{2}$所属
}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
本研究では\ldots
\end{abstract}

\textbf{キーワード}: キーワード1、キーワード2

\section{序論}
\label{sec:intro}

\section{データと方法}
\label{sec:data}

\section{分析結果}
\label{sec:results}

\section{結論}
\label{sec:conclusion}

\bibliographystyle{econ}
\bibliography{references}
\end{document}
""",
)


# ═════════════════════════════════════════════════════════════════════════════════
# 德文期刊模板
# ╘════════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 德文期刊 ①：Zeitschrift für Wirtschaftsstudien (ZWiSt)
#     经济研究杂志，德语区最重要的经济学刊物之一
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["Zeitschrift für Wirtschaftsstudien"] = JournalTemplate(
    name="Zeitschrift für Wirtschaftsstudien",
    short_name="ZWiSt",
    category="经济",
    description="德语区顶级经济学综合期刊，偏重实证经济研究，Springer出版",
    bibliography_style="authoryear",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "babel"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://www.springer.com/journal/101",
    latex_code=r"""
% ZWiSt (Zeitschrift für Wirtschaftsstudien) LaTeX Template
% Springer ECONSAMT style
%
% 注意事项：
%   1. 使用 pdflatex 编译
%   2. babel[ngerman] 设置德语
%   3. 参考文献：authoryear 风格（HauptsQuelle 2000）
%   4. 双栏排版，参考文献混排于正文底部
%
% 编译方式：
%   pdflatex paper.tex && bibtex paper && pdflatex paper.tex && pdflatex paper.tex

\documentclass[envcountsame, envcountchap, econdiv]{svmono3}

\usepackage[ngerman, english]{babel}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{url}
\usepackage[T1]{fontenc}
\usepackage{mathptmx}
\usepackage[a4paper, margin=2.5cm]{geometry}

% ── 标题页 ────────────────────────────────────────────────────────────────
\subtitle{Forschungsartikel}

\title{题目：政策が企業イノベーションに与える影響}
%\subtitle{副标题（可选）}
\author{
  Maximilian Müller$^{1}$ \quad Anna Schmidt$^{2}$ \\
  $^{1}$Ludwig-Maximilians-Universität München \\
  $^{2}$Universität Mannheim
}
\date{Dezember 2024}

% ── 摘要 ─────────────────────────────────────────────────────────────────
\begin{abstract}
In dieser Studie untersuchen wir die kausalen Auswirkungen des
Emissionshandelssystems (EHS) auf die grüne Innovation von Unternehmen
mittels eines Difference-in-Differences-Ansatzes.
Unter Verwendung eines Paneldatensatzes von 2.847 börsennotierten
Unternehmen im Zeitraum 2010--2022 zeigen wir, dass die durch das
EHS behandelten Unternehmen eine signifikant höhere Anzahl an
grünen Patenten aufweisen (coef=0.082***, t=3.21).
Die Paralleltrendannahme wird bestätigt (F=1.23, p=0.287).
Robuste Ergebnisse zeigen sich in IV-Schätzungen, Placebo-Tests und
alternativen Spezifikationen.
\\
\textbf{Schlüsselwörter}: Emissionshandel, Grüne Innovation, DiD, China
\\
\textbf{JEL-Klassifikation}: Q58, O31, C23, R38
\end{abstract}

\keywords{Emissionshandel \sep Grüne Innovation \sep Difference-in-Differences \sep China}

% ── 正文 ─────────────────────────────────────────────────────────────────
\begin{document}
\maketitle

\section{Einleitung}
\label{sec:einleitung}

\section{Literaturübersicht und Hypothesen}
\label{sec:literatur}

\section{Daten und Methodik}
\label{sec:daten}

\subsection{Datensatz}
\label{sec:dataset}

\subsection{Empirische Strategie}
\label{sec:strategie}

\section{Ergebnisse}
\label{sec:ergebnisse}

\subsection{Hauptergebnisse}
\label{sec:haupt}

\subsection{Robustheitsprüfungen}
\label{sec:robust}

\section{Schlussfolgerung}
\label{sec:schluss}

% ── 参考文献 ──────────────────────────────────────────────────────────────
\bibliographystyle{aea}
\bibliography{references}

\end{document}
""",
)


TEMPLATES["ZWiSt"] = TEMPLATES["Zeitschrift für Wirtschaftsstudien"]


# ─────────────────────────────────────────────────────────────────────────────
# 德文期刊 ②：AStA Wirtschafts- und Sozialstatistisches Archiv
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["AStA Wirtschafts- und Sozialstatistisches Archiv"] = JournalTemplate(
    name="AStA Wirtschafts- und Sozialstatistisches Archiv",
    short_name="AStA",
    category="统计",
    description="德国经济与社会统计档案，统计学方法论文优先",
    bibliography_style="authoryear",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "babel[ngerman]"],
    page_limit="约25页",
    blind_review=True,
    url="https://www.springer.com/journal/10143",
    latex_code=r"""
% AStA Wirtschafts- und Sozialstatistisches Archiv LaTeX Template
% Springer style — statistische und ökonometrische Methoden

\documentclass[envcountsame]{svmono3}
\usepackage[ngerman, english]{babel}
\usepackage{natbib}
\usepackage{amsmath, amssymb, graphicx}
\usepackage[T1]{fontenc}
\usepackage[a4paper, margin=2.5cm]{geometry}

\title{Titel}
\subtitle{Untertitel}
\author{Vorname Nachname$^{1$}$ \quad Vorname Nachname$^{2}$}
\institute{
  $^{1}$Institution, E-Mail: email@university.de \\
  $^{2}$Institution, E-Mail: email2@university.de
}
\date{\today}

\begin{abstract}
\begin{otherlanguage}{ngerman}
Zusammenfassung des Artikels\ldots
\end{otherlanguage}
\end{abstract}

\keywords{Schlüsselwörter: Wort1 \sep Wort2 \sep Wort3}
\JELClass{O21, C23, L25}

\begin{document}
\maketitle

\section{Einleitung}
\section{Daten}
\section{Methoden}
\section{Ergebnisse}
\section{Schlussfolgerung}

\bibliographystyle{aea}
\bibliography{references}
\end{document}
""",
)


# ─────────────────────────────────────────────────────────────────────────────
# 德文期刊 ③：Jahrbücher für Nationalökonomie und Statistik (JNS)
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["Jahrbücher für Nationalökonomie und Statistik"] = JournalTemplate(
    name="Jahrbücher für Nationalökonomie und Statistik",
    short_name="JNS",
    category="经济",
    description="德语区历史最悠久的经济学统计期刊，De Gruyter出版",
    bibliography_style="econ",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "babel[ngerman]"],
    page_limit="约35页",
    blind_review=True,
    url="https://www.degruyter.com/journal/key/jns",
    latex_code=r"""
% JNS (Jahrbücher für Nationalökonomie und Statistik) LaTeX Template
% De Gruyter style

\documentclass[envcountsame]{svmono3}
\usepackage[ngerman, english]{babel}
\usepackage{natbib}
\usepackage{amsmath, amssymb, graphicx}
\usepackage{url}
\usepackage[T1]{fontenc}
\usepackage{mathptmx}
\usepackage[a4paper, margin=2.5cm]{geometry}

\title{Titel des Artikels}
\subtitle{Untertitel}
\author{
  Maximilian Müller$^{1}$ \and Anna Schmidt$^{2}$ \\
  $^{1}$LMU München, München, Deutschland \\
  $^{2}$Universität Mannheim, Mannheim, Deutschland
}
\date{\today}

\abstract{
In dieser Arbeit analysieren wir die Auswirkungen der Umweltpolitik auf
Unternehmensinnovationen mittels eines Difference-in-Differences-Designs.
Der Datensatz umfasst 2.847 chinesische börsennotierte Unternehmen
von 2010 bis 2022. Die Ergebnisse zeigen einen signifikanten positiven
Effekt der Behandlung auf grüne Innovationen (coef=0.082***, t=3.21).
\\
\textbf{Keywords}: Emissionshandel, Grüne Innovation, DiD, China
\\
\textbf{JEL}: Q58, O31, C23
}

\begin{document}
\maketitle

\section{Einleitung}
\section{Literatur}
\section{Daten und Methoden}
\section{Ergebnisse}
\section{Fazit}

\bibliographystyle{aea}
\bibliography{references}
\end{document}
""",
)


# ─────────────────────────────────────────────────────────────────────────────
# 补充：Schmollers Jahrbuch（德国应用经济学）
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["Schmollers Jahrbuch"] = JournalTemplate(
    name="Schmollers Jahrbuch",
    short_name="Schmollers",
    category="经济",
    description="德国应用经济学杂志，关注政策导向的实证研究",
    bibliography_style="authoryear",
    required_packages=["natbib", "amsmath", "graphicx", "babel[ngerman]"],
    page_limit="约30页",
    blind_review=True,
    url="https://www.duncker-humblot.de/zeitschrift/schmollers-jahrbuch",
    latex_code=r"""
% Schmollers Jahrbuch LaTeX Template
% Duncker \& Humblot publisher

\documentclass[envcountsame]{svmono3}
\usepackage[ngerman]{babel}
\usepackage{natbib}
\usepackage{amsmath, amssymb, graphicx}
\usepackage[T1]{fontenc}
\usepackage[a4paper, margin=2.5cm]{geometry}

\title{Titel}
\subtitle{Untertitel}
\author{Autor Name, Institution}
\date{\today}

\abstract{
Zusammenfassung: \ldots
\\
\textbf{JEL-Klassifikation}: O30, Q58, C23
\\
\textbf{Keywords}: Politik, Innovation, DiD
}

\begin{document}
\maketitle

\section{Einleitung}
\section{Theorie und Hypothesen}
\section{Daten}
\section{Empirische Ergebnisse}
\section{Schlussfolgerungen}

\bibliographystyle{aea}
\bibliography{references}
\end{document}
""",
)


# ─────────────────────────────────────────────────────────────────────────────
# 补充：Applied Economics Quarterly (德文经济学期刊补充)
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES["Applied Economics Quarterly"] = JournalTemplate(
    name="Applied Economics Quarterly",
    short_name="AEQ",
    category="经济",
    description="应用经济学季刊，理论与实证并重",
    bibliography_style="econ",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx"],
    page_limit="约25页",
    blind_review=True,
    url="https://www.moutoncontentco.com/journals/applied-economics-quarterly",
    latex_code=r"""
% Applied Economics Quarterly (AEQ) LaTeX Template

\documentclass[envcountsame]{svmono3}
\usepackage{natbib}
\usepackage{amsmath, amssymb, graphicx}
\usepackage[T1]{fontenc}
\usepackage[a4paper, margin=2.5cm]{geometry}

\title{Title}
\subtitle{Subtitle}
\author{
  First Author$^{1}$ \and Second Author$^{2}$ \\
  $^{1}$Affiliation \\
  $^{2}$Affiliation
}
\date{\today}

\abstract{
This paper investigates \ldots
Using a difference-in-differences design with 2,847 Chinese listed firms,
we find a positive and significant effect (coef=0.082***, t=3.21).
\\
\textbf{JEL Classification}: Q58, O31, C23
\\
\textbf{Keywords}: keyword1, keyword2, keyword3
}

\begin{document}
\maketitle

\section{Introduction}
\section{Literature}
\section{Data and Methods}
\section{Results}
\section{Conclusion}

\bibliographystyle{aea}
\bibliography{references}
\end{document}
""",
)


# ═════════════════════════════════════════════════════════════════════════════════
# API 函数（兼容 journal_template.py 的 get_template / get_all_templates）
# ═════════════════════════════════════════════════════════════════════════════════


def get_template(name: str) -> JournalTemplate | None:
    """按名称或简称获取模板，支持别名匹配。"""
    aliases = {
        "jer": "JER",
        "zwist": "ZWiSt",
        "asta": "AStA",
        "jns": "JNS",
        "schmollers": "Schmollers Jahrbuch",
        "aeq": "AEQ",
        "jjid": "Japanese Journal of Income Distribution",
        "japanese economic review": "Japanese Economic Review",
        "wirtschaftsstudien": "Zeitschrift für Wirtschaftsstudien",
        "nationalökonomie": "Jahrbücher für Nationalökonomie und Statistik",
    }
    key = aliases.get(name.lower(), name)
    return TEMPLATES.get(key)


def get_all_templates() -> dict[str, JournalTemplate]:
    """返回所有多语言期刊模板（按简称索引）。"""
    return dict(TEMPLATES)


def get_by_language(lang: str) -> dict[str, JournalTemplate]:
    """按语言筛选：`japanese` 或 `german`。"""
    japanese_short = {"JER", "JJID"}
    german_short = {"ZWiSt", "AStA", "JNS", "Schmollers Jahrbuch", "AEQ"}
    if lang.lower() == "japanese":
        return {k: v for k, v in TEMPLATES.items() if k in japanese_short}
    if lang.lower() == "german":
        return {k: v for k, v in TEMPLATES.items() if k in german_short}
    return dict(TEMPLATES)


def list_templates() -> list[str]:
    """返回所有模板简称（用于命令行选择）。"""
    return list(TEMPLATES.keys())


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="多语言期刊模板工具")
    parser.add_argument("--list", action="store_true", help="列出所有模板")
    parser.add_argument("--show", type=str, help="显示指定模板的LaTeX代码")
    parser.add_argument(
        "--lang", type=str, choices=["japanese", "german", "all"], default="all",
        help="按语言筛选"
    )
    args = parser.parse_args()

    if args.list:
        print(f"\n{'模板名':<30} {'简称':<8} {'语言':<10} {'描述'}")
        print("-" * 90)
        for t in TEMPLATES.values():
            lang = "日文" if t.short_name in {"JER", "JJID"} else "德文"
            print(f"{t.name:<30} {t.short_name:<8} {lang:<10} {t.description}")
        print(f"\n共 {len(TEMPLATES)} 个模板")
    elif args.show:
        t = get_template(args.show)
        if t:
            print(f"# {t.name} ({t.short_name})\n")
            print(t.latex_code)
        else:
            print(f"未找到模板: {args.show}")
    else:
        print("多语言期刊模板工具")
        print("用法: python journal_templates_multilang.py [--list] [--show NAME] [--lang japanese|german]")
