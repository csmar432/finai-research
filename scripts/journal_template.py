#!/usr/bin/env python3
"""
LaTeX 期刊模板管理器
=====================
提供金融顶刊的 LaTeX 模板，支持快速生成符合期刊格式的论文。

支持的期刊：
- JFE: Journal of Financial Economics（金融经济学杂志）
- JF: Journal of Finance（金融杂志）
- RFS: Review of Financial Studies（金融研究综述）
- 经济研究
- 管理世界
- 金融研究

使用方法：
    from scripts.journal_template import JournalTemplate, get_template

    # 获取模板
    template = get_template("JFE")
    print(template.latex_code)

    # 生成示例文件
    template.generate_example("my_paper.tex")

    # 编译测试
    template.compile("my_paper.tex")
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═════════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═════════════════════════════════════════════════════════════════════════════════


@dataclass
class JournalTemplate:
    """期刊模板"""
    name: str                      # 显示名称
    short_name: str               # 简称（如 JFE）
    category: str                 # 类别（金融/会计/经济）
    description: str              # 描述
    latex_code: str              # 主模板代码
    bibliography_style: str       # 参考文献格式
    required_packages: list[str]  # 必需宏包
    page_limit: str | None     # 页数限制
    author_notes: bool = False    # 是否有作者注
    blind_review: bool = True     # 是否支持盲审
    url: str = ""                # 期刊官网

    def generate_example(self, output_path: str | Path) -> Path:
        """生成示例文件"""
        output_path = Path(output_path)
        output_path.write_text(self.latex_code, encoding="utf-8")
        return output_path

    def compile(
        self,
        tex_path: str | Path,
        engine: str = "pdflatex",
        passes: int = 2,
    ) -> bool:
        """编译 LaTeX 文件"""
        tex_path = Path(tex_path)

        if not tex_path.exists():
            raise FileNotFoundError(f"文件不存在: {tex_path}")

        try:
            for i in range(passes):
                result = subprocess.run(
                    [engine, "-interaction=nonstopmode", str(tex_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    # 检查是否有致命错误
                    if "Fatal" in result.stderr:
                        print(f"编译错误: {result.stderr[:500]}")
                        return False

            # 检查 PDF 是否生成
            pdf_path = tex_path.with_suffix(".pdf")
            return pdf_path.exists()

        except FileNotFoundError:
            print(f"未找到 {engine}，请安装 TeX Live")
            return False
        except subprocess.TimeoutExpired:
            print("编译超时")
            return False


# ═════════════════════════════════════════════════════════════════════════════════
# 期刊模板定义
# ═════════════════════════════════════════════════════════════════════════════════


TEMPLATES: dict[str, JournalTemplate] = {}


# ─── JFE: Journal of Financial Economics ────────────────────────────────────────

TEMPLATES["JFE"] = JournalTemplate(
    name="Journal of Financial Economics",
    short_name="JFE",
    category="金融",
    description="金融经济学领域顶级期刊，偏重实证金融研究",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx"],
    page_limit="约50页（双栏）",
    blind_review=True,
    url="https://www.journals.elsevier.com/journal-of-financial-economics",
    latex_code=r"""
% JFE LaTeX Template
% 金融经济学杂志 (Journal of Financial Economics)
% 基于官方模板修改

\documentclass[jfe]{../../templates/journals/jfe}
% jfe.cls 需要从期刊官网下载

\title{论文标题}
%\subtitle{副标题（可选）}

% 作者信息（盲审模式下会自动隐藏）
\author{
    Author One\thanks{作者一注释} \\
    Institution 1 \\
    \texttt{email1@example.com}
    \AND
    Author Two\thanks{作者二注释} \\
    Institution 2 \\
    \texttt{email2@example.com}
}

\date{\today}

% 摘要
\Abstract{
    本文研究了...使用面板数据分析方法，我们发现...
    研究结果表明...这一发现对...具有重要的理论和实践意义。
}

% 关键词
\Keywords{关键词1；关键词2；关键词3}

% JEL 分类
\JEL{G10, G14, G20}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

引言部分应包含：
\begin{itemize}
    \item 研究动机和研究问题
    \item 主要贡献和创新点
    \item 论文结构概述
\end{itemize}

\section{Literature Review}
\label{sec:lit}

文献综述应系统梳理相关领域的研究进展...

\section{Data and Methodology}
\label{sec:data}

\subsection{数据来源}
数据来自...

\subsection{研究设计}
本研究采用以下模型...

\subsection{变量定义}
\begin{table}[htbp]
    \centering
    \caption{变量定义表}
    \begin{tabular}{lcc}
        \hline
        变量 & 符号 & 定义 \\
        \hline
        因变量 & $Y$ & ... \\
        自变量 & $X$ & ... \\
        控制变量 & $Z$ & ... \\
        \hline
    \end{tabular}
\end{table}

\section{Empirical Results}
\label{sec:results}

\subsection{描述性统计}
见 Table \ref{tab:summary}。

\begin{table}[htbp]
    \centering
    \caption{描述性统计}
    \label{tab:summary}
    \begin{tabular}{lccccc}
        \hline
        变量 & 均值 & 标准差 & 最小值 & 最大值 \\
        \hline
        $Y$ & 0.05 & 0.20 & -0.50 & 0.60 \\
        $X$ & 10.5 & 3.2 & 5.0 & 20.0 \\
        \hline
    \end{tabular}
\end{table}

\subsection{主回归结果}
见 Table \ref{tab:reg}。

\begin{table}[htbp]
    \centering
    \caption{主回归结果}
    \label{tab:reg}
    \begin{tabular}{lccc}
        \hline
        & (1) & (2) & (3) \\
        \hline
        $X$ & 0.05** & 0.06*** & 0.04** \\
            & (0.02) & (0.02) & (0.02) \\
        Constant & 0.01 & 0.02 & 0.03 \\
            & (0.02) & (0.02) & (0.02) \\
        \hline
        观测数 & 1,000 & 1,000 & 1,000 \\
        $R^2$ & 0.15 & 0.18 & 0.22 \\
        \hline
        \multicolumn{4}{l}{注：*** p<0.01, ** p<0.05, * p<0.1。括号内为标准误。}
    \end{tabular}
\end{table}

\section{Robustness Checks}
\label{sec:robust}

\subsection{内生性处理}

\subsection{替代解释}

\section{Conclusion}
\label{sec:concl}

本研究...

\clearpage

% 参考文献
\bibliographystyle{jfe}
\bibliography{references}

% 附录
\appendix
\section{附录A：补充表格}
\label{app:supptables}

\end{document}
""",
)


# ─── JF: Journal of Finance ──────────────────────────────────────────────────────

TEMPLATES["JF"] = JournalTemplate(
    name="Journal of Finance",
    short_name="JF",
    category="金融",
    description="金融学领域最顶级期刊之一，强调理论和实证贡献",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "graphicx"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://onlinelibrary.wiley.com/journal/15406261",
    latex_code=r"""
% Journal of Finance LaTeX Template
% 金融杂志 (Journal of Finance)

\documentclass[jf]{../../templates/journals/jf}

\title{论文标题}

\author{%
    Author One\thanks{ affiliations... } \\
    \AND
    Author Two%
}

\Abstract{
    本文的摘要内容...
}

\Keywords{关键词}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

本文研究了...

\section{Hypothesis Development}
\label{sec:hypothesis}

基于现有理论和文献，提出以下假设：

\begin{hypothesis}
\label{h1}
H1: ...
\end{hypothesis}

\section{Data and Methodology}
\label{sec:data}

\subsection{样本与数据}

\subsection{回归模型}
本研究使用以下双向固定效应模型：

\begin{equation}
\label{eq:1}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

\section{Results}
\label{sec:results}

\subsection{主结果}
Table \ref{tab:main} 报告了主回归结果。

\begin{table}[htbp]
    \centering
    \caption{主回归结果}
    \label{tab:main}
    \begin{tabular}{lcc}
        \hline
        & 基准 & 固定效应 \\
        \hline
        $X$ & 0.05** & 0.06*** \\
            & (0.02) & (0.02) \\
        控制变量 & 否 & 是 \\
        企业固定效应 & 否 & 是 \\
        年份固定效应 & 否 & 是 \\
        \hline
        观测数 & 1,000 & 1,000 \\
        $R^2$ & 0.15 & 0.22 \\
        \hline
    \end{tabular}
\end{table}

\section{Conclusion}
\label{sec:concl}

\clearpage

\bibliographystyle{jf}
\bibliography{references}

\end{document}
""",
)


# ─── RFS: Review of Financial Studies ────────────────────────────────────────────

TEMPLATES["RFS"] = JournalTemplate(
    name="Review of Financial Studies",
    short_name="RFS",
    category="金融",
    description="金融研究领域顶级期刊，偏重理论建模和实证分析",
    bibliography_style="apa",
    required_packages=["natbib", "amsmath", "graphicx", "booktabs"],
    page_limit="约50页（单栏）",
    blind_review=True,
    url="https://academic.oup.com/rfs",
    latex_code=r"""
% Review of Financial Studies LaTeX Template
% 金融研究综述 (Review of Financial Studies)

\documentclass[article]{../../templates/journals/rfs}

\title{论文标题}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\abstract{%
    本研究...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{ Literature Review}
\label{sec:lit}

\section{ Hypothesis Development}
\label{sec:hypothesis}

\section{ Data and Methodology}
\label{sec:data}

\section{ Empirical Results}
\label{sec:results}

\subsection{Main Results}

\subsection{Robustness Tests}

\section{ Conclusion}
\label{sec:concl}

\appendix
\section*{Internet Appendix}

\bibliographystyle{rfs}
\bibliography{references}

\end{document}
""",
)


# ─── 经济研究 ────────────────────────────────────────────────────────────────────

TEMPLATES["经济研究"] = JournalTemplate(
    name="《经济研究》",
    short_name="经济研究",
    category="经济",
    description="中国经济学顶级期刊，偏重理论研究和政策分析",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "geometry", "fancyhdr", "setspace", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="https://ces.uibe.edu.cn/",
    latex_code=r"""% 《经济研究》(Economic Research Journal) LaTeX 模板
% 适配 GB/T 7714-2015 参考文献格式
% 格式：16开，双栏，中文，支持JEL分类号
%
% 编译方式：xelatex -> bibtex -> xelatex -> xelatex
%
% 依赖宏包（自动加载）：
%   ctex, xeCJK, natbib, amsmath, geometry, fancyhdr, setspace, graphicx, booktabs

% ─── 文档类 ────────────────────────────────────────────────────────────────
\documentclass[10.5pt, UTF8, twocolumn, landscape]{ctexart}
% 10.5pt: 经济研究正文字号
% twocolumn, landscape + geometry: 实现16开双栏排版

% ─── 页面布局 ─────────────────────────────────────────────────────────────
\usepackage[
    paperwidth=235mm,
    paperheight=165mm,
    top=20mm,
    bottom=20mm,
    left=15mm,
    right=15mm,
    headheight=10mm,
    footskip=8mm,
]{geometry}

% ─── 语言与字体 ───────────────────────────────────────────────────────────
\usepackage{xeCJK}
% 设置中文主体字体（系统须安装相应字体，fallback 由 ctex 自动处理）
%\setCJKmainfont{FandolSong-Regular.otf}[BoldFont={FandolSong-Bold.otf}]

% ─── 数学与符号 ────────────────────────────────────────────────────────────
\usepackage{amsmath, amssymb}
\usepackage{mathtools}   % enhanced amsmath
\usepackage{booktabs}    % professional tables
\usepackage{longtable}   % 长表格
\usepackage{graphicx}    % 插图
\graphicspath{{./figures/}}

% ─── 间距控制 ─────────────────────────────────────────────────────────────
\usepackage{setspace}
%\setstretch{1.5}          % 正文1.5倍行距（经济研究要求）
\setlength{\parindent}{2em}  % 首行缩进2字符
\setlength{\parskip}{0pt}    % 段间距

% ─── 页面样式 ─────────────────────────────────────────────────────────────
\usepackage{fancyhdr}
\fancypagestyle{JJYX}{
    \fancyhf{}
    \fancyhead[C]{\thepage}
    \fancyfoot[C]{\thepage}
    \renewcommand{\headrulewidth}{0pt}
    \renewcommand{\footrulewidth}{0pt}
}
\pagestyle{JJYX}

% ─── 超链接 ───────────────────────────────────────────────────────────────
\usepackage[colorlinks=true, linkcolor=black, citecolor=black, urlcolor=black]{hyperref}

% ─── 参考文献（GB/T 7714-2015 numeric）──────────────────────────────────────
\usepackage[numbers,sort&compress]{natbib}
% 样式说明：
%   gbt7714-2005.bst 或 gbt7714-plain.bst 配合 natbib 使用
%   如模板目录有 gbt7714-2005.bst，改用：
%   \bibliographystyle{gbt7714-2005}
\bibliographystyle{gbt7714-plain}

% ─── 标题宏定义 ──────────────────────────────────────────────────────────
% 经济研究要求：标题/作者/单位/摘要/关键词/中图分类号/JEL分类号
\makeatletter
% 作者、标题、关键词、摘要、分类号、JEL分类号存储
\def\@JJYXtitle#1{\gdef\@JJYX@title{#1}}\def\@JJYX@title{}
\def\@JJYXauthor#1{\gdef\@JJYX@author{#1}}\def\@JJYX@author{}
\def\@JJYXaffiliation#1{\gdef\@JJYX@affiliation{#1}}\def\@JJYX@affiliation{}
\def\@JJYXabstract#1{\gdef\@JJYX@abstract{#1}}\def\@JJYX@abstract{}
\def\@JJYXkeywords#1{\gdef\@JJYX@keywords{#1}}\def\@JJYX@keywords{}
\def\@JJYXclscode#1{\gdef\@JJYX@clscode{#1}}\def\@JJYX@clscode{}
\def\@JJYXjel#1{\gdef\@JJYX@jel{#1}}\def\@JJYX@jel{}

% 环境：摘要
\newenvironment{jjyxabstract}{
    \wuhao\sffamily\global\let\@JJYXabstract\@empty
    \par\noindent\textbf{摘要\quad}\wuhao
}{\par\vspace{\baselineskip}}

% 环境：关键词
\newenvironment{jjyxkeywords}{
    \par\noindent\textbf{关键词\quad}\wuhao
}{\par\vspace{\baselineskip}}

% 环境：分类号
\newenvironment{jjyxclscode}{
    \par\noindent\textbf{中图分类号\quad}\wuhao
}{\par\vspace{0.5\baselineskip}}

% 环境：JEL分类号
\newenvironment{jjyxjel}{
    \par\noindent\textbf{JEL分类号\quad}\wuhao
}{\par\vspace{\baselineskip}}

\makeatother

% 小五号字体命令
\newcommand{\wuhao}{\fontsize{9pt}{13pt}\selectfont}
% 标题区字号
\newcommand{\JJYXtitlefont}{\fontsize{16pt}{22pt}\bfseries\selectfont}
% 作者区字号
\newcommand{\JJYXauthorfont}{\fontsize{10.5pt}{16pt}\selectfont}

% ─── 标题页环境 ──────────────────────────────────────────────────────────
% 使用方法：
%   \begin{jjYXtitle}{标题}{作者}{单位}
%   \begin{jjYXabstract} 摘要内容 \end{jjYXabstract}
%   \begin{jjYXkeywords} 关键词1；关键词2；关键词3 \end{jjYXkeywords}
%   \begin{jjYXclscode} F0；F03 \end{jjYXclscode}
%   \begin{jjYXjel} JEL: G00; O40 \end{jjYXjel}
%   \end{jjYXtitle}

\NewDocumentEnvironment{jjYXtitle}{mmm}{
    % 参数：{标题}{作者信息}{单位信息}
    \twocolumn[%
        \centering
        % 标题
        \JJYXtitlefont\@JJYX@title\par
        \vspace{6pt}
        % 作者
        {\JJYXauthorfont #2}\par
        \vspace{3pt}
        % 单位
        {\JJYXauthorfont #3}\par
        \vspace{6pt}
        % 摘要栏（单栏排版）
        \hspace{2em}\begin{minipage}{0.9\linewidth}
            % 摘要
            \wuhao\textbf{摘要}\quad\@JJYX@abstract\par
            \vspace{3pt}
            % 关键词
            \wuhao\textbf{关键词}\quad\@JJYX@keywords\par
            % 中图分类号
            \ifx\@JJYX@clscode\@empty\else
                \wuhao\textbf{中图分类号}\quad\@JJYX@clscode\par
            \fi
            % JEL分类号
            \ifx\@JJYX@jel\@empty\else
                \wuhao\textbf{JEL分类号}\quad\@JJYX@jel\par
            \fi
        \end{minipage}
        \vspace{8pt}
    ]%
}{}

% ─── 标题快捷命令（单命令方式）────────────────────────────────────────────
% 使用方法：
%   \JJYXsettitle{标题}
%   \JJYXsetauthor{作者}   % 盲审时注释掉
%   \JJYXsetaffiliation{单位}
%   \begin{jjYXabstract} 摘要 \end{jjYXabstract}
%   \begin{jjYXkeywords} 关键词1；关键词2 \end{jjYXkeywords}

\NewDocumentCommand{\JJYXsettitle}{m}{\@JJYXtitle{#1}}
\NewDocumentCommand{\JJYXsetauthor}{m}{\@JJYXauthor{#1}}
\NewDocumentCommand{\JJYXsetaffiliation}{m}{\@JJYXaffiliation{#1}}
\NewDocumentCommand{\JJYXsetabstract}{m}{\@JJYXabstract{#1}}
\NewDocumentCommand{\JJYXsetkeywords}{m}{\@JJYXkeywords{#1}}
\NewDocumentCommand{\JJYXsetclscode}{m}{\@JJYXclscode{#1}}
\NewDocumentCommand{\JJYXsetjel}{m}{\@JJYXjel{#1}}

% ─── 正文环境 ─────────────────────────────────────────────────────────────
% 一级标题：宋体加粗
\ctexset{section/format={\centering\zihao{-3}\CJKfamily{zhsong}\bfseries}}
% 二级标题：宋体
\ctexset{subsection/format={\zihao{4}\CJKfamily{zhsong}}}
% 三级标题：宋体
\ctexset{subsubsection/format={\zihao{-4}\CJKfamily{zhsong}}}

% ─── 图表浮动体 ────────────────────────────────────────────────────────────
\usepackage{flafter}    % 图表放在引用之后
\usepackage{booktabs}   % 三线表
\usepackage{sidecap}    % 图注在侧
% 表格字号
\DeclareFontFamily{OT1}{fakesc}{}
\usepackage{caption}
\captionsetup{font=small, skip=6pt}

% ─── 定理/证明环境 ─────────────────────────────────────────────────────────
\newtheorem{hypothesis}{假设}
\newtheorem{assumption}{假定}
\newtheorem{definition}{定义}
\newtheorem{prop}{性质}
\newtheorem*{proof}{证明}

% ─── 附录格式 ─────────────────────────────────────────────────────────────
\ctexset{section/aftertitle={\par}}{}

% ─────────────────────────────────────────────────────────────────────────
\begin{document}

% ══════════════════════════════════════════════════════════════════════════════
% 请填写以下信息（盲审时请删除作者和单位信息）
% ══════════════════════════════════════════════════════════════════════════════

\JJYXsettitle{论文标题（中文，不超过20字）}

% 盲审时注释掉以下两行
\JJYXsetauthor{作者一$^{1}$  ~~作者二$^{2}$ ~~作者三$^{1}$}
\JJYXsetaffiliation{$^{1}$北京大学光华管理学院  $^{2}$清华大学五道口金融学院}

% 摘要（不超过300字）
\begin{jjYXabstract}
本文基于XX数据，采用XX方法，实证研究了XX问题。研究发现：（1）……；（2）……；（3）……。这一发现对理解……具有重要意义，并对我……政策的制定提供了经验证据。
\end{jjYXabstract}

% 关键词（3-5个）
\begin{jjYXkeywords}
关键词一；关键词二；关键词三；关键词四；关键词五
\end{jjYXkeywords}

% 中图分类号（http://ztflh.xhma.com/）
\begin{jjYXclscode}
F0；F03
\end{jjYXclscode}

% JEL分类号（https://www.aeaweb.org/jel/jel-class-series）
\begin{jjYXjel}
JEL: G00; O40; C50
\end{jjYXjel}

% ══════════════════════════════════════════════════════════════════════════════
% 正文
% ══════════════════════════════════════════════════════════════════════════════

\section{引言}
\label{sec:intro}

\section{文献综述与研究假设}
\label{sec:lit}

\subsection{文献综述}

\subsection{研究假设}
基于以上分析，本文提出如下待检验的研究假设：

\begin{hypothesis}
\label{hyp:h1}
\textbf{假设1：}……（说明假设内容）。
\end{hypothesis}

\begin{hypothesis}
\label{hyp:h2}
\textbf{假设2：}……（说明假设内容）。
\end{hypothesis}

\section{研究设计}
\label{sec:design}

\subsection{样本与数据}
本文以……为研究样本，时间跨度为……至……。数据来源于……。

\subsection{变量定义}

\subsubsection{被解释变量}
$Y_{it}$ 表示……，数据来源于……。

\subsubsection{解释变量}
核心解释变量$X_{it}$ 为……。

\subsubsection{控制变量}
参考已有文献（\cite{xxx}），本文还控制了以下变量……。

\begin{table}[htbp]
\centering
\caption{变量定义表}
\label{tab:var}
\wuhao
\begin{tabular}{p{2.2cm}p{2.5cm}p{5.5cm}}
\toprule
变量类型 & 变量名称 & 变量定义 \\
\midrule
因变量 & $Y$ & ……（数据来源：XX数据库）\\
\midrule
自变量 & $X$ & ……（指标构造方法）\\
\midrule
控制变量 & $Z_1$ & ……\\
& $Z_2$ & ……\\
& $Year$ & 年份虚拟变量\\
\midrule
工具变量 & $IV$ & ……（工具变量选择依据）\\
\bottomrule
\end{tabular}
\end{table}

\subsection{模型设定}
为检验假设1，本文构建如下双向固定效应回归模型：

\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

其中，$\mu_i$ 和 $\lambda_t$ 分别为企业和年份固定效应，$\varepsilon_{it}$ 为误差项。

\section{实证结果}
\label{sec:results}

\subsection{描述性统计}

\begin{longtable}{ccccccc}
\caption{描述性统计}
\label{tab:desc}
\\\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endfirsthead
\multicolumn{7}{c}{\textbf{续表\thetable\ 描述性统计}}\\
\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endhead
\bottomrule
\endfoot
$Y$ & 1000 & 0.05 & 0.20 & -0.50 & 0.03 & 0.60 \\
$X$ & 1000 & 0.30 & 0.15 & 0.10 & 0.28 & 0.70 \\
$Z_1$ & 1000 & 5.20 & 1.50 & 1.00 & 5.00 & 9.00 \\
\bottomrule
\end{longtable}

\subsection{基准回归分析}
表~\ref{tab:reg} 报告了基准回归结果。

\begin{table}[htbp]
\centering
\caption{基准回归结果}
\label{tab:reg}
\wuhao
\begin{tabular}{lccc}
\toprule
 & (1) & (2) & (3) \\
\midrule
$X$ & 0.05** & 0.06*** & 0.04** \\
    & (0.02) & (0.02) & (0.02) \\
$Z_1$ & & 0.10*** & 0.08** \\
      &      & (0.03)  & (0.03) \\
\midrule
常数项 & 0.01 & 0.02 & 0.03 \\
       & (0.02) & (0.02) & (0.02) \\
\midrule
控制变量 & 否 & 是 & 是 \\
企业固定效应 & 否 & 否 & 是 \\
年份固定效应 & 否 & 否 & 是 \\
\midrule
观测数 & 1000 & 1000 & 1000 \\
$R^2$ & 0.15 & 0.18 & 0.22 \\
\bottomrule
\multicolumn{4}{l}{\small 注：*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类稳健标准误（聚类到企业）。}
\end{tabular}
\end{table}

\subsection{内生性处理}
为缓解遗漏变量偏误和反向因果导致的内生性问题，本文采用……方法进行检验。

\subsection{稳健性检验}

\subsubsection{替换核心变量}
为保证结果的稳健性，本文采用……替换核心解释变量。

\subsubsection{改变样本范围}
剔除……样本后，主要结论依然成立。

\section{进一步分析}
\label{sec:进一步}

\section{结论与启示}
\label{sec:concl}

本文基于……数据，实证研究了……问题。研究发现：（1）……；（2）……；（3）……。

本文的研究启示在于：第一，……；第二，……；第三，……。未来研究可以从……角度进一步深化。

\section*{参考文献}
\addcontentsline{toc}{section}{参考文献}
\bibliography{references}

% ══════════════════════════════════════════════════════════════════════════════
% 附录（如有）
% ══════════════════════════════════════════════════════════════════════════════
\clearpage
\appendix
\section*{附录}
\addcontentsline{toc}{section}{附录}

\end{document}
""",
)


# ─── 管理世界 ────────────────────────────────────────────────────────────────────

TEMPLATES["管理世界"] = JournalTemplate(
    name="《管理世界》",
    short_name="管理世界",
    category="管理",
    description="中国管理学顶级期刊，偏重管理实践和案例研究",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "geometry", "fancyhdr", "setspace", "graphicx", "booktabs"],
    page_limit="约15000字",
    blind_review=True,
    url="https://www.mgmt.org.cn/",
    latex_code=r"""% 《管理世界》(Management World) LaTeX 模板
% 适配 GB/T 7714-2015 参考文献格式
% 格式：A4，双栏，中文，摘要+关键词+作者信息
%
% 编译方式：xelatex -> bibtex -> xelatex -> xelatex

% ─── 文档类 ────────────────────────────────────────────────────────────────
\documentclass[10pt, UTF8, twocolumn]{ctexart}
% 10pt: 管理世界正文字号
% twocolumn: 双栏排版

% ─── 页面布局 ─────────────────────────────────────────────────────────────
\usepackage[
    a4paper,
    top=20mm,
    bottom=22mm,
    left=18mm,
    right=18mm,
    headheight=10mm,
    footskip=8mm,
    columnsep=8mm,
]{geometry}

% ─── 语言与字体 ────────────────────────────────────────────────────────────
\usepackage{xeCJK}
%\setCJKmainfont{...}[...]  % 系统字体配置（可选，ctex 自动 fallback）

% ─── 数学与符号 ────────────────────────────────────────────────────────────
\usepackage{amsmath, amssymb}
\usepackage{mathtools}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\graphicspath{{./figures/}}

% ─── 间距控制 ─────────────────────────────────────────────────────────────
\usepackage{setspace}
%\setstretch{1.5}
\setlength{\parindent}{2em}
\setlength{\parskip}{0pt}

% ─── 页面样式 ─────────────────────────────────────────────────────────────
\usepackage{fancyhdr}
\fancypagestyle{GLSJ}{
    \fancyhf{}
    \fancyhead[C]{\thepage}
    \fancyfoot[C]{\thepage}
    \fancyhead[LO,RE]{}
    \fancyhead[CO,CE]{}
    \renewcommand{\headrulewidth}{0pt}
    \renewcommand{\footrulewidth}{0pt}
}
\pagestyle{GLSJ}

% ─── 超链接 ───────────────────────────────────────────────────────────────
\usepackage[colorlinks=true, linkcolor=black, citecolor=black, urlcolor=black]{hyperref}

% ─── 参考文献（GB/T 7714-2015 numeric）─────────────────────────────────────
\usepackage[numbers,sort&compress]{natbib}
\bibliographystyle{gbt7714-plain}
% 如有 gbt7714-2005.bst 可改用: \bibliographystyle{gbt7714-2005}

% ─── 标题宏 ────────────────────────────────────────────────────────────────
\makeatletter
\def\@GLSJtitle#1{\gdef\@GLSJ@title{#1}}\def\@GLSJ@title{}
\def\@GLSJauthor#1{\gdef\@GLSJ@author{#1}}\def\@GLSJ@author{}
\def\@GLSJaffiliation#1{\gdef\@GLSJ@affiliation{#1}}\def\@GLSJ@affiliation{}
\def\@GLSJabstract#1{\gdef\@GLSJ@abstract{#1}}\def\@GLSJ@abstract{}
\def\@GLSJkeywords#1{\gdef\@GLSJ@keywords{#1}}\def\@GLSJ@keywords{}
\makeatother

% 摘要环境
\NewDocumentEnvironment{glsjabstract}{}{
    \par\noindent\textbf{摘\quad 要}\xiaosi
    \wuhao
}{
    \par\vspace{\baselineskip}
}

% 关键词环境
\NewDocumentEnvironment{glsjkeywords}{}{
    \par\noindent\textbf{关键词}\xiaosi\ \wuhao
}{
    \par\vspace{0.5\baselineskip}
}

% 设置命令
\NewDocumentCommand{\GLSJsettitle}{m}{\@GLSJtitle{#1}}
\NewDocumentCommand{\GLSJsetauthor}{m}{\@GLSJauthor{#1}}
\NewDocumentCommand{\GLSJsetaffiliation}{m}{\@GLSJaffiliation{#1}}
\NewDocumentCommand{\GLSJsetabstract}{m}{\@GLSJabstract{#1}}
\NewDocumentCommand{\GLSJsetkeywords}{m}{\@GLSJkeywords{#1}}

% 字号命令
\newcommand{\xiaosi}{\fontsize{12pt}{18pt}\selectfont}
\newcommand{\wuhao}{\fontsize{9pt}{13pt}\selectfont}
% 标题字号
\newcommand{\GLSJtitlefont}{\fontsize{18pt}{26pt}\bfseries\selectfont}
% 作者字号
\newcommand{\GLSJauthorfont}{\fontsize{10.5pt}{16pt}\selectfont}

% ─── 正文格式 ─────────────────────────────────────────────────────────────
% 一级标题：黑体加粗，居中
\ctexset{section/format={\centering\zihao{-3}\CJKfamily{zhhei}\bfseries}}
% 二级标题：黑体
\ctexset{subsection/format={\zihao{4}\CJKfamily{zhhei}}}
% 三级标题：黑体
\ctexset{subsubsection/format={\zihao{-4}\CJKfamily{zhhei}}}

% ─── 图表浮动 ─────────────────────────────────────────────────────────────
\usepackage{caption}
\captionsetup{font=small, skip=6pt}

% ─── 定理环境 ─────────────────────────────────────────────────────────────
\newtheorem{hypothesis}{假设}
\newtheorem{assumption}{假定}
\newtheorem{management}{命题}
\newtheorem*{proof}{证明}

% ─────────────────────────────────────────────────────────────────────────
\begin{document}

% ══════════════════════════════════════════════════════════════════════════════
% 封面信息（盲审时删除作者和单位信息）
% ══════════════════════════════════════════════════════════════════════════════

\GLSJsettitle{论文标题（中文，不超过20字）}

% 盲审时注释掉以下两行
\GLSJsetauthor{作者一$^{1}$~~作者二$^{2}$~~作者三$^{1}$}
\GLSJsetaffiliation{$^{1}$北京大学光华管理学院~~$^{2}$清华大学经济管理学院}

\GLSJsetabstract{%
本文基于XX数据，采用XX方法，研究了XX问题。研究发现：（1）……；（2）……；（3）……。本文的研究对理解……具有理论意义，对企业/政府/管理者……具有实践启示。
}

\begin{glsjabstract}
本文基于XX数据，采用XX方法，研究了XX问题。研究发现：（1）……；（2）……；（3）……。本文的研究对理解……具有理论意义，对企业/政府/管理者……具有实践启示。
\end{glsjabstract}

\begin{glsjkeywords}
关键词一；关键词二；关键词三；关键词四
\end{glsjkeywords}

% ══════════════════════════════════════════════════════════════════════════════
% 正文
% ══════════════════════════════════════════════════════════════════════════════

\section{引言}
\label{sec:intro}

本文的研究背景、意义和主要贡献如下。

第一，……

第二，……

第三，……

\section{理论分析与研究假设}
\label{sec:theory}

\subsection{理论分析}

\subsection{研究假设}
基于以上理论分析，本文提出如下研究假设：

\begin{hypothesis}
\label{hyp:h1}
\textbf{假设1：}……（说明假设内容及理论依据）。
\end{hypothesis}

\begin{hypothesis}
\label{hyp:h2}
\textbf{假设2：}……（说明假设内容及理论依据）。
\end{hypothesis}

\section{研究设计}
\label{sec:design}

\subsection{样本选择与数据来源}
本文以……为研究样本，时间跨度为……至……。数据来源包括……数据库和……。

剔除标准：（1）……；（2）……；（3）……。

\subsection{变量定义}

\begin{enumerate}
\itemsep0pt
\item \textbf{被解释变量} $Y_{it}$：……，数据来源于……。

\item \textbf{解释变量}：核心解释变量$X_{it}$ 为……。工具变量$IV_{it}$ 为……。选择依据：……。

\item \textbf{控制变量} $Z_{it}$：参考已有研究（\cite{xxx}），本文控制了以下变量……。

\begin{table}[htbp]
\centering
\caption{变量定义表}
\label{tab:var}
\xiaosi
\begin{tabular}{p{2cm}p{2.5cm}p{5.5cm}}
\toprule
变量类型 & 变量名称 & 变量定义 \\
\midrule
因变量 & $Y$ & ……（数据来源）\\
\midrule
自变量 & $X$ & ……（指标构造方法）\\
\midrule
控制变量 & $Z_1$ & ……（定义）\\
& $Z_2$ & ……（定义）\\
& $Year$ & 年份虚拟变量\\
\midrule
工具变量 & $IV$ & ……（选择依据）\\
\bottomrule
\end{tabular}
\end{table}
\end{enumerate}

\subsection{模型构建}
为检验假设1和假设2，本文构建如下基准回归模型：

\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

其中，$X_{it}$ 为核心解释变量，$Z_{it}$ 为控制变量，$\mu_i$ 和 $\lambda_t$ 分别为企业和年份固定效应，$\varepsilon_{it}$ 为随机误差项。

\section{实证分析}
\label{sec:results}

\subsection{描述性统计与相关性分析}

\begin{longtable}{ccccccc}
\caption{描述性统计}
\label{tab:desc}
\\\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endfirsthead
\multicolumn{7}{c}{\textbf{续表\thetable\ 描述性统计}}\\
\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endhead
\bottomrule
\endfoot
$Y$ & 1000 & 0.05 & 0.20 & -0.50 & 0.03 & 0.60 \\
$X$ & 1000 & 0.30 & 0.15 & 0.10 & 0.28 & 0.70 \\
$Z_1$ & 1000 & 5.20 & 1.50 & 1.00 & 5.00 & 9.00 \\
\bottomrule
\end{longtable}

\subsection{基准回归结果}
表~\ref{tab:reg} 报告了基准回归结果。

\begin{table}[htbp]
\centering
\caption{基准回归结果}
\label{tab:reg}
\xiaosi
\begin{tabular}{lccc}
\toprule
 & (1) & (2) & (3) \\
\midrule
$X$ & 0.05** & 0.06*** & 0.04** \\
    & (0.02) & (0.02) & (0.02) \\
$Z_1$ & & 0.10*** & 0.08** \\
      &      & (0.03)  & (0.03) \\
\midrule
常数项 & 0.01 & 0.02 & 0.03 \\
       & (0.02) & (0.02) & (0.02) \\
\midrule
控制变量 & 否 & 是 & 是 \\
企业固定效应 & 否 & 否 & 是 \\
年份固定效应 & 否 & 否 & 是 \\
\midrule
观测数 & 1000 & 1000 & 1000 \\
$R^2$ & 0.15 & 0.18 & 0.22 \\
\bottomrule
\multicolumn{4}{l}{\small 注：*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类稳健标准误（聚类到企业层面）。}
\end{tabular}
\end{table}

\subsection{内生性处理}
为缓解潜在的内生性问题，本文采用以下策略：

（1）工具变量法。选择……作为$X$的工具变量。

（2）滞后解释变量。将核心解释变量滞后一期进行回归。

（3）PSM倾向得分匹配。

（4）Heckman两阶段模型。

\section{进一步讨论}
\label{sec:further}

\section{结论与启示}
\label{sec:concl}

本文以……为研究对象，基于……数据，采用……方法，实证研究了……问题。研究发现：（1）……；（2）……；（3）……。

本文的理论贡献在于：第一，……；第二，……。

实践启示：对于企业管理者，……；对于政府部门，……；对于投资者，……。

本文的局限性及未来研究方向：……。

\section*{参考文献}
\addcontentsline{toc}{section}{参考文献}
\bibliography{references}

% ══════════════════════════════════════════════════════════════════════════════
% 附录
% ══════════════════════════════════════════════════════════════════════════════
\clearpage
\appendix
\section*{附录}
\addcontentsline{toc}{section}{附录}

\end{document}
""",
)


# ─── 金融研究 ────────────────────────────────────────────────────────────────────

TEMPLATES["金融研究"] = JournalTemplate(
    name="《金融研究》",
    short_name="金融研究",
    category="金融",
    description="中国金融学核心期刊，偏重金融市场和金融机构研究",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "geometry", "fancyhdr", "setspace", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="http://jrs.ccer.edu.cn/",
    latex_code=r"""% 《金融研究》(Journal of Financial Research) LaTeX 模板
% 适配 GB/T 7714-2015 参考文献格式
% 格式：A4，双栏，中文，摘要+关键词
%
% 编译方式：xelatex -> bibtex -> xelatex -> xelatex

% ─── 文档类 ────────────────────────────────────────────────────────────────
\documentclass[10pt, UTF8, twocolumn]{ctexart}
% 10pt: 金融研究正文字号
% twocolumn: 双栏排版

% ─── 页面布局 ─────────────────────────────────────────────────────────────
\usepackage[
    a4paper,
    top=22mm,
    bottom=22mm,
    left=20mm,
    right=20mm,
    headheight=10mm,
    footskip=8mm,
    columnsep=8mm,
]{geometry}

% ─── 语言与字体 ────────────────────────────────────────────────────────────
\usepackage{xeCJK}
%\setCJKmainfont{...}[...]  % 系统字体配置（可选，ctex 自动 fallback）

% ─── 数学与符号 ────────────────────────────────────────────────────────────
\usepackage{amsmath, amssymb}
\usepackage{mathtools}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\graphicspath{{./figures/}}

% ─── 间距控制 ─────────────────────────────────────────────────────────────
\usepackage{setspace}
%\setstretch{1.5}
\setlength{\parindent}{2em}
\setlength{\parskip}{0pt}

% ─── 页面样式 ─────────────────────────────────────────────────────────────
\usepackage{fancyhdr}
\fancypagestyle{JRYJ}{
    \fancyhf{}
    \fancyhead[C]{\thepage}
    \fancyfoot[C]{\thepage}
    \fancyhead[LO,RE]{}
    \fancyhead[CO,CE]{}
    \renewcommand{\headrulewidth}{0pt}
    \renewcommand{\footrulewidth}{0pt}
}
\pagestyle{JRYJ}

% ─── 超链接 ───────────────────────────────────────────────────────────────
\usepackage[colorlinks=true, linkcolor=black, citecolor=black, urlcolor=black]{hyperref}

% ─── 参考文献（GB/T 7714-2015 numeric）─────────────────────────────────────
\usepackage[numbers,sort&compress]{natbib}
\bibliographystyle{gbt7714-plain}
% 如有 gbt7714-2005.bst 可改用: \bibliographystyle{gbt7714-2005}

% ─── 标题宏 ───────────────────────────────────────────────────────────────
\makeatletter
\def\@JRYJtitle#1{\gdef\@JRYJ@title{#1}}\def\@JRYJ@title{}
\def\@JRYJauthor#1{\gdef\@JRYJ@author{#1}}\def\@JRYJ@author{}
\def\@JRYJaffiliation#1{\gdef\@JRYJ@affiliation{#1}}\def\@JRYJ@affiliation{}
\def\@JRYJabstract#1{\gdef\@JRYJ@abstract{#1}}\def\@JRYJ@abstract{}
\def\@JRYJkeywords#1{\gdef\@JRYJ@keywords{#1}}\def\@JRYJ@keywords{}
\makeatother

% 摘要环境
\NewDocumentEnvironment{jryjabstract}{}{
    \par\noindent\textbf{摘\quad 要}\xiaosi
    \wuhao
}{
    \par\vspace{\baselineskip}
}

% 关键词环境
\NewDocumentEnvironment{jryjkeywords}{}{
    \par\noindent\textbf{关键词}\xiaosi\ \wuhao
}{
    \par\vspace{0.5\baselineskip}
}

% 设置命令
\NewDocumentCommand{\JRYJsettitle}{m}{\@JRYJtitle{#1}}
\NewDocumentCommand{\JRYJsetauthor}{m}{\@JRYJauthor{#1}}
\NewDocumentCommand{\JRYJsetaffiliation}{m}{\@JRYJaffiliation{#1}}
\NewDocumentCommand{\JRYJsetabstract}{m}{\@JRYJabstract{#1}}
\NewDocumentCommand{\JRYJsetkeywords}{m}{\@JRYJkeywords{#1}}

% 字号命令
\newcommand{\xiaosi}{\fontsize{12pt}{18pt}\selectfont}
\newcommand{\wuhao}{\fontsize{9pt}{13pt}\selectfont}
% 标题字号
\newcommand{\JRYJtitlefont}{\fontsize{18pt}{26pt}\bfseries\selectfont}
% 作者字号
\newcommand{\JRYJauthorfont}{\fontsize{10.5pt}{16pt}\selectfont}

% ─── 正文格式 ─────────────────────────────────────────────────────────────
% 一级标题：黑体加粗，居中
\ctexset{section/format={\centering\zihao{-3}\CJKfamily{zhhei}\bfseries}}
% 二级标题：黑体
\ctexset{subsection/format={\zihao{4}\CJKfamily{zhhei}}}
% 三级标题：黑体
\ctexset{subsubsection/format={\zihao{-4}\CJKfamily{zhhei}}}

% ─── 图表浮动 ─────────────────────────────────────────────────────────────
\usepackage{caption}
\captionsetup{font=small, skip=6pt}

% ─── 定理环境 ─────────────────────────────────────────────────────────────
\newtheorem{hypothesis}{假设}
\newtheorem{assumption}{假定}
\newtheorem{finance}{命题}
\newtheorem*{proof}{证明}

% ─────────────────────────────────────────────────────────────────────────
\begin{document}

% ══════════════════════════════════════════════════════════════════════════════
% 封面信息（盲审时删除作者和单位信息）
% ══════════════════════════════════════════════════════════════════════════════

\JRYJsettitle{论文标题（中文，不超过20字）}

% 盲审时注释掉以下两行
\JRYJsetauthor{作者一$^{1}$~~作者二$^{2}$~~作者三$^{1}$}
\JRYJsetaffiliation{$^{1}$北京大学光华管理学院~~$^{2}$清华大学五道口金融学院}

\begin{jryjabstract}
本文基于XX数据，采用XX方法，实证研究了XX问题。研究发现：（1）……；（2）……；（3）……。本文的研究对理解……具有理论意义，对金融监管和金融市场参与者……具有实践价值。
\end{jryjabstract}

\begin{jryjkeywords}
关键词一；关键词二；关键词三；关键词四
\end{jryjkeywords}

% ══════════════════════════════════════════════════════════════════════════════
% 正文
% ══════════════════════════════════════════════════════════════════════════════

\section{引言}
\label{sec:intro}

本文的研究背景与问题、意义和主要贡献如下。

第一，……

第二，……

第三，……

\section{文献综述}
\label{sec:lit}

\subsection{理论文献回顾}

\subsection{实证文献回顾}
已有文献在……方面做出了重要贡献，但仍存在以下不足：（1）……；（2）……；（3）……。

本文与已有研究的关键区别在于：……。

\section{研究设计}
\label{sec:design}

\subsection{样本与数据}
本文以……为研究样本，时间跨度为……至……。数据来源包括……数据库、……数据库和……。

样本筛选过程：（1）剔除……；（2）剔除……；（3）剔除……。

\subsection{变量定义}

\subsubsection{被解释变量}
$Y_{it}$ 表示……，数据来源于……。

\subsubsection{解释变量}
核心解释变量$X_{it}$ 为……。该指标由……构造得到。

工具变量$IV_{it}$ 为……。选择依据：……。

\subsubsection{控制变量}
参考已有研究（\cite{xxx}），本文还控制了以下变量：$Z_1$（……）、$Z_2$（……）、年份固定效应等。

\begin{table}[htbp]
\centering
\caption{变量定义表}
\label{tab:var}
\xiaosi
\begin{tabular}{p{2cm}p{2.5cm}p{5.5cm}}
\toprule
变量类型 & 变量名称 & 变量定义 \\
\midrule
因变量 & $Y$ & ……（数据来源：XX数据库）\\
\midrule
自变量 & $X$ & ……（指标构造方法）\\
\midrule
控制变量 & $Z_1$ & ……（定义）\\
& $Z_2$ & ……（定义）\\
& $Year$ & 年份虚拟变量\\
\midrule
工具变量 & $IV$ & ……（选择依据）\\
\bottomrule
\end{tabular}
\end{table}

\subsection{模型构建}
为检验假设1，本文构建如下双向固定效应回归模型：

\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

其中，$X_{it}$ 为核心解释变量，$Z_{it}$ 为控制变量向量，$\mu_i$ 和 $\lambda_t$ 分别为企业和年份固定效应，$\varepsilon_{it}$ 为随机误差项。

\section{实证结果}
\label{sec:results}

\subsection{描述性统计}
表~\ref{tab:desc} 报告了主要变量的描述性统计。

\begin{longtable}{ccccccc}
\caption{描述性统计}
\label{tab:desc}
\\\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endfirsthead
\multicolumn{7}{c}{\textbf{续表\thetable\ 描述性统计}}\\
\toprule
变量 & 观测数 & 均值 & 标准差 & 最小值 & 中位数 & 最大值 \\
\midrule
\endhead
\bottomrule
\endfoot
$Y$ & 1000 & 0.05 & 0.20 & -0.50 & 0.03 & 0.60 \\
$X$ & 1000 & 0.30 & 0.15 & 0.10 & 0.28 & 0.70 \\
$Z_1$ & 1000 & 5.20 & 1.50 & 1.00 & 5.00 & 9.00 \\
\bottomrule
\end{longtable}

\subsection{基准回归分析}
表~\ref{tab:reg} 报告了基准回归结果。

\begin{table}[htbp]
\centering
\caption{基准回归结果}
\label{tab:reg}
\xiaosi
\begin{tabular}{lccc}
\toprule
 & (1) & (2) & (3) \\
\midrule
$X$ & 0.05** & 0.06*** & 0.04** \\
    & (0.02) & (0.02) & (0.02) \\
$Z_1$ & & 0.10*** & 0.08** \\
      &      & (0.03)  & (0.03) \\
\midrule
常数项 & 0.01 & 0.02 & 0.03 \\
       & (0.02) & (0.02) & (0.02) \\
\midrule
控制变量 & 否 & 是 & 是 \\
企业固定效应 & 否 & 否 & 是 \\
年份固定效应 & 否 & 否 & 是 \\
\midrule
观测数 & 1000 & 1000 & 1000 \\
$R^2$ & 0.15 & 0.18 & 0.22 \\
\bottomrule
\multicolumn{4}{l}{\small 注：*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类稳健标准误（聚类到企业层面）。}
\end{tabular}
\end{table}

\section{内生性处理}
\label{sec:endo}

\subsection{工具变量法}
为缓解反向因果导致的内生性问题，本文采用工具变量方法。

第一阶段：$X_{it} = \pi_0 + \pi_1 IV_{it} + \cdots + \varepsilon_{it}$

第二阶段：$Y_{it} = \alpha + \beta \hat{X}_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}$

工具变量有效性检验：弱工具变量检验F统计量为……，Stock-Yogo临界值为……，拒绝弱工具变量假设。

\subsection{其他内生性处理策略}
（1）滞后解释变量；（2）PSM倾向得分匹配；（3）Heckman两阶段模型。

\section{稳健性检验}
\label{sec:robust}

（1）替换核心变量：采用……替换$X$，结果依然显著。

（2）改变样本范围：剔除……样本后，主要结论不变。

（3）改变控制变量：加入/剔除……变量，结论稳健。

（4）改变固定效应结构：加入……交互固定效应。

\section{进一步分析}
\label{sec:further}

\section{结论}
\label{sec:concl}

本文基于……数据，实证研究了……问题。研究发现：（1）……；（2）……；（3）……。

理论贡献：第一，……；第二，……。

实践启示：对于金融监管机构，……；对于金融机构，……；对于投资者，……。

本文的局限性及未来研究方向：……。

\section*{参考文献}
\addcontentsline{toc}{section}{参考文献}
\bibliography{references}

% ══════════════════════════════════════════════════════════════════════════════
% 附录
% ══════════════════════════════════════════════════════════════════════════════
\clearpage
\appendix
\section*{附录}
\addcontentsline{toc}{section}{附录}

\end{document}
""",
)


# ─── ACL (已存在，补充完整模板) ─────────────────────────────────────────────────

TEMPLATES["ACL"] = JournalTemplate(
    name="ACL / NAACL / EMNLP",
    short_name="ACL",
    category="AI/计算语言学",
    description="自然语言处理领域顶级会议/期刊",
    bibliography_style="acl_natbib",
    required_packages=["acl", "natbib", "amsmath"],
    page_limit="8页（不含参考文献）",
    blind_review=True,
    url="https://www.aclweb.org/",
    latex_code=r"""
% ACL LaTeX Template
% 用于 ACL / NAACL / EMNLP

\documentclass[11pt, a4paper]{article}
\usepackage{acl}
\usepackage{natbib}
\usepackage{amsmath}
\usepackage{graphicx}

% 设置标题
\title{论文标题}

% 作者（盲审时删除）
\author{
    Author One \\
    Institution 1 \\
    \texttt{email1@example.com}
    \AND
    Author Two \\
    Institution 2 \\
    \texttt{email2@example.com}
}

\date{}

\begin{document}

\maketitle

\begin{abstract}
本文提出了一种新方法，用于解决...
实验结果表明，本文方法在...上取得了显著改进。
\end{abstract}

\section{Introduction}

\section{Related Work}

\section{Methodology}
\label{sec:method}

\section{Experiments}
\label{sec:exp}

\section{Conclusion}
\label{sec:concl}

\bibliographystyle{acl_natbib}
\bibliography{references}

\end{document}
""",
)


# ─── NeurIPS ────────────────────────────────────────────────────────────────────

TEMPLATES["NeurIPS"] = JournalTemplate(
    name="NeurIPS",
    short_name="NeurIPS",
    category="AI/机器学习",
    description="神经信息处理系统会议，机器学习顶级会议",
    bibliography_style="neurips",
    required_packages=["neurips", "natbib", "amsmath"],
    page_limit="9页（不含参考文献和附录）",
    blind_review=True,
    url="https://nips.cc/",
    latex_code=r"""
% NeurIPS LaTeX Template

\documentclass[11pt, letterpaper]{article}
\usepackage[hypertex]{hyperref}
\usepackage{nips10submit_e}
\usepackage{epsfig}
\usepackage{amsmath}
\usepackage{amsthm}

\title{论文标题}

\author{%
    Author One \\
    Institution 1 \\
    \texttt{email1@example.com}
    \AND
    Author Two \\
    Institution 2 \\
    \texttt{email2@example.com}
}

\begin{document}

\maketitle

\begin{abstract}
本文研究了...我们提出了...
实验结果表明...
\end{abstract}

\section{Introduction}
\label{sec:intro}

\section{Related Work}
\label{sec:related}

\section{Method}
\label{sec:method}

\section{Experiments}
\label{sec:exp}

\section{Conclusion}
\label{sec:concl}

\bibliography{references}

\end{document}
""",
)


# ═════════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═════════════════════════════════════════════════════════════════════════════════


def get_template(name: str) -> JournalTemplate | None:
    """根据名称获取模板"""
    return TEMPLATES.get(name.upper()) or TEMPLATES.get(name)


def list_templates(category: str | None = None) -> list[JournalTemplate]:
    """列出所有模板"""
    templates = list(TEMPLATES.values())
    if category:
        templates = [t for t in templates if t.category == category]
    return templates


# ═════════════════════════════════════════════════════════════════════════════════
# 新增模板：金融学 Q1/Q2 SCI
# ═════════════════════════════════════════════════════════════════════════════════

# ─── JFQA: Journal of Financial and Quantitative Analysis ─────────────────────

TEMPLATES["JFQA"] = JournalTemplate(
    name="Journal of Financial and Quantitative Analysis",
    short_name="JFQA",
    category="金融",
    description="金融定量分析领域重要期刊，偏重量化方法和实证金融",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约50页（双栏）",
    blind_review=True,
    url="https://www.jfqa.org/",
    latex_code=r"""
% JFQA LaTeX Template
% Journal of Financial and Quantitative Analysis

\documentclass[jfqa]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{dcolumn}
\newcolumntype{d}[1]{D{.}{.}{#1}}

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Literature Review}
\label{sec:lit}

\section{Hypothesis Development}
\label{sec:hypothesis}

\section{Data and Methodology}
\label{sec:data}

\subsection{Sample and Data}
\subsection{Variables}
\subsection{Methodology}
\subsection{Summary Statistics}

\section{Empirical Results}
\label{sec:results}

\subsection{Main Results}
\subsection{Robustness Checks}
\subsection{Additional Tests}

\section{Conclusion}
\label{sec:concl}

\appendix
\section*{Internet Appendix}

\bibliographystyle{jfqa}
\bibliography{references}

\end{document}
""",
)


# ─── JCF: Journal of Corporate Finance ───────────────────────────────────────

TEMPLATES["JCF"] = JournalTemplate(
    name="Journal of Corporate Finance",
    short_name="JCF",
    category="金融",
    description="公司金融领域重要期刊，偏重资本结构、并购、公司治理",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://www.journals.elsevier.com/journal-of-corporate-finance",
    latex_code=r"""
% JCF LaTeX Template
% Journal of Corporate Finance

\documentclass[jcf]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{threeparttable}

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Literature Review and Hypotheses}
\label{sec:lit}

\subsection{Literature Review}
\subsection{Hypotheses}

\section{Data and Methodology}
\label{sec:data}

\subsection{Sample Selection}
\subsection{Variable Definitions}
\subsection{Model Specification}

\section{Results}
\label{sec:results}

\subsection{Summary Statistics}
\subsection{Main Regression Results}
\subsection{Robustness Tests}

\section{Conclusion}
\label{sec:concl}

\bibliographystyle{jf}
\bibliography{references}

\appendix
\section*{Appendix}

\end{document}
""",
)


# ─── JFM: Journal of Financial Markets ───────────────────────────────────────

TEMPLATES["JFM"] = JournalTemplate(
    name="Journal of Financial Markets",
    short_name="JFM",
    category="金融",
    description="金融市场领域重要期刊，偏重市场微观结构、衍生品、交易",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约30页（单栏）",
    blind_review=True,
    url="https://www.journals.elsevier.com/journal-of-financial-markets",
    latex_code=r"""
% JFM LaTeX Template
% Journal of Financial Markets

\documentclass[jfm]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Related Literature}
\label{sec:lit}

\section{Hypotheses}
\label{sec:hypothesis}

\section{Data and Methodology}
\label{sec:data}

\section{Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\bibliographystyle{jfe}
\bibliography{references}

\end{document}
""",
)


# ─── JFI: Journal of Financial Intermediation ─────────────────────────────────

TEMPLATES["JFI"] = JournalTemplate(
    name="Journal of Financial Intermediation",
    short_name="JFI",
    category="金融",
    description="金融中介领域权威期刊，偏重银行、保险、信用市场",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://www.journals.elsevier.com/journal-of-financial-intermediation",
    latex_code=r"""
% JFI LaTeX Template
% Journal of Financial Intermediation

\documentclass[article]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Literature Review}
\label{sec:lit}

\section{Hypotheses}
\label{sec:hypothesis}

\section{Data and Methodology}
\label{sec:data}

\section{Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\bibliographystyle{aer}
\bibliography{references}

\end{document}
""",
)


# ═════════════════════════════════════════════════════════════════════════════════
# 新增模板：经济学 Q1 SCI
# ═════════════════════════════════════════════════════════════════════════════════

# ─── QJE: Quarterly Journal of Economics ──────────────────────────────────────

TEMPLATES["QJE"] = JournalTemplate(
    name="Quarterly Journal of Economics",
    short_name="QJE",
    category="经济",
    description="经济学四大顶刊之一，历史最悠久，偏重理论与实证",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约60页（单栏）",
    blind_review=True,
    url="https://academic.oup.com/qje",
    latex_code=r"""
% QJE LaTeX Template
% Quarterly Journal of Economics
% 基于 Oxford University Press 官方模板

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{setspace}
\doublespacing

\title{论文标题}
%\subtitle{副标题（可选）}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\date{\today}

\Abstract{%
    本文摘要内容... 研究发现... 政策启示...
}

\keywords{关键词1；关键词2；关键词3}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Background and Literature}
\label{sec:lit}

\section{Conceptual Framework}
\label{sec:framework}

\section{Data}
\label{sec:data}

\section{Empirical Strategy}
\label{sec:strategy}

\section{Results}
\label{sec:results}

\subsection{Baseline Results}
\subsection{Heterogeneity Analysis}
\subsection{Robustness Checks}

\section{Conclusion}
\label{sec:concl}

\appendix
\section*{Appendix A: Additional Results}
\label{app:a}

\bibliographystyle{aer}
\bibliography{references}

\end{document}
""",
)


# ─── JPE: Journal of Political Economy ──────────────────────────────────────

TEMPLATES["JPE"] = JournalTemplate(
    name="Journal of Political Economy",
    short_name="JPE",
    category="经济",
    description="经济学四大顶刊之一，芝加哥学派阵地，偏重理论与政策",
    bibliography_style="chicago",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约50页（双栏）",
    blind_review=True,
    url="https://www.journals.uchicago.edu/journals/jpe",
    latex_code=r"""
% JPE LaTeX Template
% Journal of Political Economy
% 基于 University of Chicago Press 官方模板

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{cases}

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Theoretical Framework}
\label{sec:theory}

\section{Related Literature}
\label{sec:lit}

\section{Data and Empirical Strategy}
\label{sec:data}

\section{Results}
\label{sec:results}

\subsection{Main Findings}
\subsection{Robustness and Sensitivity}
\subsection{Extensions}

\section{Conclusion}
\label{sec:concl}

\appendix
\section*{Proofs}
\label{app:proofs}

\bibliographystyle{jpe}
\bibliography{references}

\end{document}
""",
)


# ─── Econometrica ─────────────────────────────────────────────────────────────

TEMPLATES["ECONOMETRICA"] = JournalTemplate(
    name="Econometrica",
    short_name="Econometrica",
    category="经济",
    description="经济学四大顶刊之一，计量经济学协会官方期刊",
    bibliography_style="econometrica",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约50页（单栏）",
    blind_review=True,
    url="https://www.econometricsociety.org/publications/econometrica",
    latex_code=r"""
% Econometrica LaTeX Template
% Econometrica — Journal of the Econometric Society
% 基于官方模板

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{longtable}

\title{论文标题}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\Abstract{%
    本文摘要内容... 使用...方法，研究了...问题。发现...
}

\keywords{关键词1；关键词2；关键词3}

\JEL{JEL: C01; C22; G32}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Model}
\label{sec:model}

\section{Estimation and Inference}
\label{sec:estimation}

\section{Related Literature}
\label{sec:lit}

\section{Data}
\label{sec:data}

\section{Empirical Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\appendix
\section*{Appendix: Technical Details}
\label{app:tech}

\bibliographystyle{econometrica}
\bibliography{references}

\end{document}
""",
)


# ─── REStud: Review of Economic Studies ─────────────────────────────────────

TEMPLATES["RESTUD"] = JournalTemplate(
    name="Review of Economic Studies",
    short_name="REStud",
    category="经济",
    description="经济学四大顶刊之一，偏重理论与数量方法",
    bibliography_style="econometrica",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约50页（单栏）",
    blind_review=True,
    url="https://academic.oup.com/restud",
    latex_code=r"""
% REStud LaTeX Template
% Review of Economic Studies

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}

\title{论文标题}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\Abstract{%
    本文摘要内容...
}

\keywords{关键词1；关键词2}

\JEL{JEL: C01; D01; G02}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Model}
\label{sec:model}

\section{Estimation}
\label{sec:estimation}

\section{Data and Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\appendix
\section*{Appendix}

\bibliographystyle{econometrica}
\bibliography{references}

\end{document}
""",
)


# ═════════════════════════════════════════════════════════════════════════════════
# 新增模板：中国C刊
# ═════════════════════════════════════════════════════════════════════════════════

# ─── 中国工业经济 ─────────────────────────────────────────────────────────────

TEMPLATES["中国工业经济"] = JournalTemplate(
    name="《中国工业经济》",
    short_name="中国工业经济",
    category="经济/产业",
    description="中国经济学C刊顶级，偏重产业组织、企业行为、规制政策",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "graphicx", "booktabs", "hyperref"],
    page_limit="约25000字",
    blind_review=True,
    url="http://cie journal.ajcass.com/",
    latex_code=r"""
% 《中国工业经济》LaTeX 模板
% 基于官方格式要求

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}
\usepackage{cleveref}

\title{论文标题}

\author{%
    作者一$^{1}$\quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文利用...数据，研究了...问题。
    研究发现：...这一发现对于理解...具有重要意义。
    政策启示：...
}

\keywords{关键词1；关键词2；关键词3；关键词4}

\CJKclassified{F0; G3}% 中图分类号

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述与理论分析}
\label{sec:lit}

\subsection{文献综述}
\subsection{理论分析与研究假设}

\section{研究设计}
\label{sec:design}

\subsection{样本与数据}
\subsection{变量定义}
\begin{table}[htbp]
    \centering
    \caption{变量定义表}
    \begin{tabular}{cll}
        \toprule
        变量类型 & 变量名称 & 定义 \\
        \midrule
        因变量 & $Y$ & ... \\
        自变量 & $X$ & ... \\
        控制变量 & $Z_1$ & ... \\
            & $Z_2$ & ... \\
        \bottomrule
    \end{tabular}
\end{table}

\subsection{回归模型设定}
\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

\section{实证结果}
\label{sec:results}

\subsection{描述性统计}
\subsection{基准回归结果}
表~\ref{tab:reg}报告了基准回归结果。

\begin{table}[htbp]
    \centering
    \caption{基准回归结果}
    \label{tab:reg}
    \begin{tabular}{lccc}
        \toprule
        & (1) & (2) & (3) \\
        \midrule
        $X$ & 0.05** & 0.06*** & 0.04** \\
            & (0.02) & (0.02) & (0.02) \\
        Constant & 0.01 & 0.02 & 0.03 \\
            & (0.02) & (0.02) & (0.02) \\
        \midrule
        控制变量 & 否 & 是 & 是 \\
        固定效应 & 否 & 否 & 是 \\
        \midrule
        观测数 & 1,000 & 1,000 & 1,000 \\
        $R^2$ & 0.15 & 0.18 & 0.22 \\
        \bottomrule
        \multicolumn{4}{l}{注：*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类稳健标准误。}
    \end{tabular}
\end{table}

\subsection{稳健性检验}
\subsection{进一步分析}

\section{结论与政策建议}
\label{sec:concl}

本文利用...数据，研究了...问题。研究发现：...

政策建议：...

\clearpage

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\appendix
\section*{附录A：补充检验}

\end{document}
""",
)


# ─── 数量经济技术经济研究 ────────────────────────────────────────────────────

TEMPLATES["数量经济技术经济研究"] = JournalTemplate(
    name="《数量经济技术经济研究》",
    short_name="数量经济技术经济研究",
    category="经济/方法",
    description="中国C刊，偏重数量方法在经济研究中的应用",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="http://sljjjs.org.cn/",
    latex_code=r"""
% 《数量经济技术经济研究》LaTeX 模板

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文利用...方法，研究了...问题...
}

\keywords{关键词1；关键词2；关键词3}

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述}
\label{sec:lit}

\section{模型构建}
\label{sec:model}

\section{数据与变量}
\label{sec:data}

\section{实证分析}
\label{sec:results}

\section{结论}
\label{sec:concl}

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\end{document}
""",
)


# ─── 统计研究 ────────────────────────────────────────────────────────────────

TEMPLATES["统计研究"] = JournalTemplate(
    name="《统计研究》",
    short_name="统计研究",
    category="统计",
    description="中国C刊，偏重统计方法、抽样调查、数据科学",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="http://tjyj.ajcass.com/",
    latex_code=r"""
% 《统计研究》LaTeX 模板

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文...研究了...问题...
}

\keywords{关键词1；关键词2；关键词3}

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{研究方法}
\label{sec:method}

\section{数据说明}
\label{sec:data}

\section{实证结果}
\label{sec:results}

\section{结论}
\label{sec:concl}

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\end{document}
""",
)


# ─── 世界经济 ────────────────────────────────────────────────────────────────

TEMPLATES["世界经济"] = JournalTemplate(
    name="《世界经济》",
    short_name="世界经济",
    category="经济/国际",
    description="中国C刊顶级，偏重国际贸易、国际金融、跨国投资",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约25000字",
    blind_review=True,
    url="http://sjjj.ajcass.com/",
    latex_code=r"""
% 《世界经济》LaTeX 模板

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文利用...数据，研究了...国际经济问题...
}

\keywords{关键词1；关键词2；关键词3；关键词4}

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述与理论分析}
\label{sec:lit}

\section{研究设计}
\label{sec:design}

\section{实证结果}
\label{sec:results}

\section{结论与政策启示}
\label{sec:concl}

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\appendix

\end{document}
""",
)


# ─── 会计研究 ────────────────────────────────────────────────────────────────

TEMPLATES["会计研究"] = JournalTemplate(
    name="《会计研究》",
    short_name="会计研究",
    category="会计",
    description="中国C刊顶级，偏重会计理论、审计、财务报告",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="http://kjyj.ajcass.com/",
    latex_code=r"""
% 《会计研究》LaTeX 模板

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文利用...数据，研究了...会计问题...
}

\keywords{关键词1；关键词2；关键词3}

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述}
\label{sec:lit}

\section{理论分析与研究假设}
\label{sec:hypothesis}

\section{研究设计}
\label{sec:design}

\section{实证结果}
\label{sec:results}

\section{研究结论}
\label{sec:concl}

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\end{document}
""",
)


# ─── 财政研究 ────────────────────────────────────────────────────────────────

TEMPLATES["财政研究"] = JournalTemplate(
    name="《财政研究》",
    short_name="财政研究",
    category="财政",
    description="中国C刊，偏重财政税收、公共经济学、政府预算",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约20000字",
    blind_review=True,
    url="http://czyj.ajcass.com/",
    latex_code=r"""
% 《财政研究》LaTeX 模板

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二%
}

\Abstract{%
    本文利用...数据，研究了...财政问题...
}

\keywords{关键词1；关键词2；关键词3}

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述}
\label{sec:lit}

\section{理论分析与研究假设}
\label{sec:hypothesis}

\section{研究设计}
\label{sec:design}

\section{实证结果}
\label{sec:results}

\section{结论与建议}
\label{sec:concl}

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\end{document}
""",
)


# ─── 经济学(季刊) ───────────────────────────────────────────────────────────

TEMPLATES["经济学季刊"] = JournalTemplate(
    name="《经济学》(季刊)",
    short_name="经济学季刊",
    category="经济",
    description="中国C刊顶级，北京大学主办，偏重理论与实证经济学",
    bibliography_style="gb7714-2015",
    required_packages=["ctex", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约30000字",
    blind_review=True,
    url="http://jxjl.ajcass.com/",
    latex_code=r"""
% 《经济学》(季刊) LaTeX 模板
% 北京大学主办

\documentclass[UTF8, a4paper, 12pt]{article}
\usepackage{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{hyperref}
\usepackage{cases}

\title{论文标题}

\author{%
    作者一$^{1}$ \quad 作者二$^{2}$ \quad 作者三$^{3}$%
}

\affiliation{%
    $^{1}$单位一 \\
    $^{2}$单位二 \\
    $^{3}$单位三%
}

\Abstract{%
    本文利用...数据，实证研究了...问题。
    研究发现：...这一发现对于理解...具有重要意义。
}

\keywords{关键词1；关键词2；关键词3；关键词4}

\CJKclassified{F0; G3}% 中图分类号

\begin{document}

\maketitle

\section{引言}
\label{sec:intro}

\section{文献综述与理论分析}
\label{sec:lit}

\subsection{经典文献回顾}
\subsection{理论分析与研究假设}

\section{研究设计}
\label{sec:design}

\subsection{数据来源}
\subsection{样本选择}
\subsection{变量定义}
\begin{table}[htbp]
    \centering
    \caption{变量定义表}
    \begin{tabular}{cll}
        \toprule
        变量类型 & 变量名称 & 定义 \\
        \midrule
        因变量 & $Y$ & ... \\
        自变量 & $X$ & ... \\
        控制变量 & $Z_1$ & ... \\
            & $Z_2$ & ... \\
        \bottomrule
    \end{tabular}
\end{table}

\subsection{模型设定}
\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta X_{it} + \gamma Z_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

\section{实证结果}
\label{sec:results}

\subsection{描述性统计}
\subsection{基准回归}
表~\ref{tab:reg}报告了基准回归结果。

\begin{table}[htbp]
    \centering
    \caption{基准回归结果}
    \label{tab:reg}
    \begin{tabular}{lccc}
        \toprule
        & (1) & (2) & (3) \\
        \midrule
        $X$ & 0.05** & 0.06*** & 0.04** \\
            & (0.02) & (0.02) & (0.02) \\
        Constant & 0.01 & 0.02 & 0.03 \\
            & (0.02) & (0.02) & (0.02) \\
        \midrule
        控制变量 & 否 & 是 & 是 \\
        企业固定效应 & 否 & 否 & 是 \\
        年份固定效应 & 否 & 否 & 是 \\
        \midrule
        观测数 & 1,000 & 1,000 & 1,000 \\
        $R^2$ & 0.15 & 0.18 & 0.22 \\
        \bottomrule
        \multicolumn{4}{l}{注：*** p<0.01, ** p<0.05, * p<0.1。括号内为聚类稳健标准误。}
    \end{tabular}
\end{table}

\subsection{稳健性检验}
\subsection{异质性分析}

\section{结论与政策启示}
\label{sec:concl}

本文利用...数据，研究了...问题。研究发现：...政策启示：...

\clearpage

\begin{thebibliography}{99}
    \bibitem{ref1} 作者. 标题[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\appendix
\section*{附录A：稳健性检验}

\end{document}
""",
)


# ─── JEEA: Journal of the European Economic Association ─────────────────────

TEMPLATES["JEEA"] = JournalTemplate(
    name="Journal of the European Economic Association",
    short_name="JEEA",
    category="经济",
    description="欧洲经济学协会会刊，经济学Q1期刊",
    bibliography_style="econometrica",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约50页（单栏）",
    blind_review=True,
    url="https://academic.oup.com/jeea",
    latex_code=r"""
% JEEA LaTeX Template
% Journal of the European Economic Association

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}

\title{论文标题}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\Abstract{%
    This paper... using... data, we study...
}

\keywords{keyword1; keyword2; keyword3}

\JEL{JEL: C01; D01; G02}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Model}
\label{sec:model}

\section{Related Literature}
\label{sec:lit}

\section{Data}
\label{sec:data}

\section{Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\appendix

\bibliographystyle{econometrica}
\bibliography{references}

\end{document}
""",
)


# ─── AEJ:AEI: American Economic Journal: Applied Economics ──────────────────

TEMPLATES["AEJAE"] = JournalTemplate(
    name="American Economic Journal: Applied Economics",
    short_name="AEJ:AEI",
    category="经济",
    description="AEA旗下应用经济学期刊，经济学Q1",
    bibliography_style="aer",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://www.aeaweb.org/journals/aej/aej-applied",
    latex_code=r"""
% AEJ: Applied Economics LaTeX Template
% American Economic Journal: Applied Economics

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}
\usepackage{setspace}
\doublespacing

\title{论文标题}

\author{%
    Author One\thanks{Affiliation} \\
    \AND
    Author Two\thanks{Affiliation}%
}

\Abstract{%
    This paper... using... data, we study... We find...
}

\keywords{keyword1; keyword2; keyword3}

\JEL{JEL: C01; G32; O16}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Background and Hypotheses}
\label{sec:lit}

\section{Data and Empirical Strategy}
\label{sec:data}

\section{Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\appendix

\bibliographystyle{aer}
\bibliography{references}

\end{document}
""",
)


# ─── Review of Economics and Statistics ─────────────────────────────────────

TEMPLATES["RESTAT"] = JournalTemplate(
    name="Review of Economics and Statistics",
    short_name="REStat",
    category="经济",
    description="MIT Press出版，偏重计量经济学方法与应用，经济学Q1",
    bibliography_style="econometrica",
    required_packages=["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
    page_limit="约40页（双栏）",
    blind_review=True,
    url="https://www.mitpressjournals.org/loi/rest",
    latex_code=r"""
% REStat LaTeX Template
% Review of Economics and Statistics

\documentclass[12pt]{article}
\usepackage{natbib}
\usepackage{amsmath, amssymb}
\usepackage{graphicx, booktabs}

\title{论文标题}

\author{%
    Author One$^{1}$ \quad Author Two$^{2}$%
}

\affiliation{%
    $^{1}$Institution 1 \\
    $^{2}$Institution 2%
}

\Abstract{%
    This paper...
}

\keywords{keyword1; keyword2; keyword3}

\JEL{JEL: C01; C22; G32}

\begin{document}

\maketitle

\section{Introduction}
\label{sec:intro}

\section{Literature Review}
\label{sec:lit}

\section{Model and Hypotheses}
\label{sec:model}

\section{Data and Methods}
\label{sec:data}

\section{Results}
\label{sec:results}

\section{Conclusion}
\label{sec:concl}

\appendix

\bibliographystyle{econometrica}
\bibliography{references}

\end{document}
""",
)

# ═════════════════════════════════════════════════════════════════════════════════
# 中文期刊模板扩展（2026-06-04，新增8个模板）
# 覆盖：科研管理、南开管理评论、系统工程理论与实践、中国软科学、
#       管理科学学报、系统工程学报、中国管理科学、管理科学
# ═════════════════════════════════════════════════════════════════════════════════

TEMPLATES["科研管理"] = JournalTemplate(
    name="《科研管理》",
    short_name="科研管理",
    category="管理",
    description="中国科学院主办，管理学C刊偏重科技政策、R&D管理、创新管理，CSSCI来源期刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约15000字",
    blind_review=True,
    url="http://kjgl.bjdsteam.cn/",
    latex_code=r"""
% 《科研管理》LaTeX 模板
% 参考: http://kjgl.bjdsteam.cn/

\documentclass[10pt, UTF8, a4paper, twocolumn]{ctexart}
\usepackage[top=2.5cm, bottom=2.5cm, left=2cm, right=2cm]{geometry}
\usepackage{xeCJK}
\xeCJKsetup{ChineseHeading=true, space=auto}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace, fancyhdr}
\usepackage{makecell}
\usepackage[font=small, skip=6pt]{caption}
\bibliographystyle{gbt7714-plain}

\ctexset{section/format={\centering\songti\zihao{-4}\bfseries},
          subsection/format={\raggedright\kaishu\zihao{5}\bfseries},
          subsubsection/format={\raggedright\kaishu\zihao{5}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}
\setlength{\parskip}{6pt}

% 页面样式
\fancyhead[L]{\songti\zihao{-5}\kaishu 科研管理}
\fancyfoot[C]{\thepage}

\begin{document}

% 标题区
\begin{center}
  {\songti\zihao{3} 论文标题\citep{作者年份}}

  \vspace{6pt}
  {\kaishu\zihao{-4} 作者姓名$^{1}$，作者姓名$^{2}$}

  \vspace{4pt}
  {\kaishu\zihao{-5}
    $^{1}$第一作者单位，邮编 \\
    $^{2}$第二作者单位，邮编
  }
\end{center}

\vspace{12pt}

% 中文摘要
\noindent\textbf{摘要：}
\CJKunderline{在此输入中文摘要内容。摘要应简明扼要地反映论文的主要研究问题、方法、主要结论和贡献，一般不超过300字。}
\\[4pt]
\noindent\textbf{关键词：}关键词1；关键词2；关键词3；关键词4

\vspace{10pt}
\hrule height 0.5pt
\vspace{10pt}

% 英文摘要
\begin{center}
  {\bfseries\zihao{-4} Title of Paper (English)}
\end{center}
\noindent\textbf{Abstract: } \CJKunderline{Write English abstract here. It should be consistent with the Chinese abstract, usually within 200 words.}
\\[4pt]
\noindent\textbf{Keywords: } keyword1; keyword2; keyword3; keyword4

\vspace{10pt}

\section{引言}
\label{sec:intro}
请在此输入引言部分。引言应简要介绍研究背景、问题的提出、研究意义，以及本文的主要贡献。

\section{文献综述与研究假设}
\label{sec:lit}
\subsection{文献综述}
对相关文献进行系统梳理，评述现有研究的主要贡献和不足。
\subsection{研究假设}
基于文献综述，提出本文的研究假设 $H_1$, $H_2$, $H_3$。

\section{研究设计}
\label{sec:design}
\subsection{样本与数据}
说明样本选择依据、数据来源。
\subsection{变量定义}
说明因变量、自变量、控制变量的定义，参见表~\ref{tab:var}。
\subsection{模型设定}
设定回归模型：
\begin{equation}
\label{eq:1}
Y_{it} = \alpha + \beta \cdot Treat_{it} + \gamma X_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

\section{实证结果}
\label{sec:results}
\subsection{描述性统计}
参见表~\ref{tab:desc}。
\subsection{基准回归}
参见表~\ref{tab:main}。
\subsection{稳健性检验}
参见表~\ref{tab:robust}。

\section{结论与启示}
\label{sec:concl}
本文基于XXX数据，利用双重差分方法研究了XXX对XXX的影响。研究发现：\circled{1}...；\circled{2}...；\circled{3}...。

\section*{参考文献}
\bibliographystyle{gbt7714-plain}
\bibliography{references}

\begin{thebibliography}{99}
  \bibitem{作者年份} 作者. 论文题目[J]. 期刊名, 年份, 卷(期): 起始页-终止页.
\end{thebibliography}

\appendix

\section{附录A：变量描述性统计详情}
% 补充材料

\end{document}
""",
)

TEMPLATES["南开管理评论"] = JournalTemplate(
    name="《南开管理评论》",
    short_name="南开管理评论",
    category="管理",
    description="南开大学主办，管理学C刊偏重公司治理、战略管理、组织行为，CSSCI来源期刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约20000字",
    blind_review=True,
    url="http://nkpl.bankPSS.com/",
    latex_code=r"""
% 《南开管理评论》LaTeX 模板
% 参考: http://nkpl.bankPSS.com/

\documentclass[10pt, UTF8, a4paper]{ctexart}
\usepackage[top=2.54cm, bottom=2.54cm, left=3.17cm, right=3.17cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\usepackage[font=small, skip=4pt]{caption}
\bibliographystyle{gbt7714-plain}

\ctexset{section/format={\centering\heiti\zihao{4}\bfseries},
          subsection/format={\raggedright\fangsong\zihao{5}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}
\setlength{\parskip}{3pt}

\begin{document}

% 首页
\thispagestyle{empty}
\begin{center}
  \vspace*{1cm}
  {\heiti\zihao{2} 论文标题}

  \vspace{1.5cm}
  {\fangsong\zihao{-4}
    作者一$^{1}$ \quad 作者二$^{1}$ \quad 作者三$^{2}$
  }

  \vspace{0.5cm}
  {\fangsong\zihao{-5}
    $^{1}$南开大学商学院，300071 \\
    $^{2}$某某大学某某学院，100000
  }
\end{center}

\vspace{1.5cm}

% 中文摘要
\noindent{\heiti 摘要：}
摘要内容。摘要应包括研究目的、方法、主要发现和结论，不超过300字。
\\[4pt]
\noindent{\heiti 关键词：}关键词；关键词；关键词；关键词
\\[6pt]
\noindent{\fangsong Abstract: } English abstract here.
\\[2pt]
\noindent{\fangsong Keywords: } keyword; keyword; keyword; keyword

\newpage
\thispagestyle{plain}

\section{引言}
\label{sec:intro}
引言部分应介绍研究背景、问题的提出、本文的主要贡献。

\section{理论分析与研究假设}
\label{sec:theory}
\subsection{理论基础}
介绍相关理论。
\subsection{研究假设}
提出研究假设 $H_1$ 和 $H_2$。

\section{研究设计}
\label{sec:design}
\subsection{样本与数据}
说明研究样本的选取过程和数据来源。

\subsection{变量定义}
\begin{table}[htbp]
  \centering
  \caption{变量定义表}
  \label{tab:var}
  \begin{tabular}{p{3cm}p{4cm}p{4cm}p{2cm}}
    \toprule
    变量类型 & 变量名称 & 变量定义 & 预期符号 \\
    \midrule
    因变量 & $Y$ & XXX &  \\
    自变量 & $X$ & XXX & + \\
    \bottomrule
  \end{tabular}
\end{table}

\section{实证分析}
\label{sec:empirical}
\subsection{描述性统计与相关性分析}
表~\ref{tab:desc} 报告了主要变量的描述性统计。

\subsection{基准回归分析}
表~\ref{tab:main} 报告了基准回归结果。

\section{稳健性检验}
\label{sec:robust}
为保证研究结论的可靠性，本文进行了如下稳健性检验：\circled{1}替换因变量；\circled{2}倾向得分匹配；\circled{3}子样本检验。

\section{研究结论与启示}
\label{sec:concl}
本文基于XXX理论，研究了XXX对XXX的影响。主要结论如下：...

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

TEMPLATES["系统工程理论与实践"] = JournalTemplate(
    name="《系统工程理论与实践》",
    short_name="系统工程理论与实践",
    category="管理",
    description="中国系统工程学会主办，系统科学/运筹学C刊，偏重方法论、决策科学，CSSCI来源期刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "amssymb", "booktabs",
                       "geometry", "graphicx"],
    page_limit="约15000字",
    blind_review=True,
    url="https://www.sysengi.com/",
    latex_code=r"""
% 《系统工程理论与实践》LaTeX 模板
% 参考: https://www.sysengi.com/

\documentclass[10pt, UTF8, a4paper]{article}
\usepackage[top=2.5cm, bottom=2.5cm, left=3cm, right=3cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\bibliographystyle{gbt7714-plain}

\CTEXsetup[titleformat={\fangsong\zihao{-3}\bfseries}]{section}
\CTEXsetup[name={,．}, number=Chinese]{section}

\usepackage{lineno}
\linenumbers

\begin{document}

\begin{center}
  {\fangsong\zihao{3} \textbf{论文题目}}\citep{作者年份}

  \vspace{8pt}
  {\kaishu\zihao{-4}
    作者一\quad 作者二\quad 作者三
  }

  \vspace{4pt}
  {\kaishu\zihao{-5}
    （单位名称，邮政编码）
  }
\end{center}

\vspace{10pt}

\noindent\textbf{摘要：} 摘要内容（200-300字）。
\\[4pt]
\noindent\textbf{关键词：} 关键词1；关键词2；关键词3

\vspace{6pt}
\noindent\textbf{AMS(2020)主题分类：} 90Cxx \quad\textbf{中图分类号：} N945

\section{引言}
引言内容。说明研究背景、问题的提出、主要贡献。

\section{问题描述与模型构建}
\subsection{问题描述}
对研究问题进行清晰描述。
\subsection{模型构建}
构建数学模型：
\begin{maximize}
\label{eq:obj}
\max_{x} \quad f(x) = \sum_{i=1}^{n} c_i x_i
\end{maximize}
\begin{s.t.}
\begin{aligned}
\sum_{j=1}^{n} a_{ij} x_j &\leqslant b_i, \quad i = 1, \ldots, m \\
x_j &\geqslant 0, \quad j = 1, \ldots, n
\end{aligned}
\end{s.t.}

\section{算法设计}
描述求解算法。
\subsection{算法步骤}
算法~\ref{algo:1} 给出了求解步骤。

\section{数值实验}
报告数值实验结果，与现有算法进行对比。

\section{结论}
总结全文，提出未来研究方向。

\begin{thebibliography}{99}
  \bibitem{作者年份} 作者. 题目[J]. 期刊名, 年份, 卷(期): 页码.
\end{thebibliography}

\end{document}
""",
)

TEMPLATES["中国软科学"] = JournalTemplate(
    name="《中国软科学》",
    short_name="中国软科学",
    category="管理",
    description="科技部主管，软科学领域权威期刊，偏重科技政策、创新政策、公共政策评估，C刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约18000字",
    blind_review=True,
    url="http://cssm.cssn.cn/",
    latex_code=r"""
% 《中国软科学》LaTeX 模板
% 参考: http://cssm.cssn.cn/

\documentclass[10pt, UTF8, a4paper, twocolumn]{ctexart}
\usepackage[top=2.5cm, bottom=2.5cm, left=2cm, right=2cm, columnsep=0.6cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace, iftex}
\bibliographystyle{gbt7714-plain}

\ctexset{section/format={\centering\heiti\zihao{4}\bfseries},
          subsection/format={\raggedright\fangsong\zihao{5}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}

\begin{document}

% 首页格式（单栏）
\begin{onecolumnpage}
\begin{center}
  \vspace*{2cm}
  {\heiti\zihao{-2} 论文标题}

  \vspace{1cm}
  {\kaishu\zihao{-4} 作者一$^{1}$ \quad 作者二$^{2}$}

  \vspace{0.5cm}
  {\fangsong\zihao{-5}
    $^{1}$单位，邮编 \\
    $^{2}$单位，邮编
  }
\end{center}

\vspace{1cm}

\noindent\textbf{摘要：}摘要内容，不超过300字。
\\[4pt]
\noindent\textbf{关键词：}关键词1；关键词2；关键词3；关键词4

\newpage
\end{onecolumnpage}

% 恢复双栏
\begin{strip}
  \vspace{-\stripsep}
\end{strip}

% 双栏正文
\section{引言}
\label{sec:intro}
引言应阐明研究背景，问题的提出，研究意义，主要贡献。

\section{文献综述与研究假设}
\label{sec:lit}
系统梳理国内外相关文献，评述现有研究的不足，提出研究假设。

\section{研究设计}
\label{sec:design}
\subsection{数据来源}
说明数据来源和样本选取。
\subsection{模型设定}
构建实证模型：
\begin{equation}
\label{eq:did}
Y_{it} = \alpha + \beta \cdot DID_{it} + \gamma X_{it} + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

\section{实证结果}
\label{sec:results}
报告基准回归结果、稳健性检验、内生性处理。

\section{结论与政策建议}
\label{sec:concl}
本研究的主要发现：\circled{1}...；\circled{2}...。
基于研究发现，提出如下政策建议：...

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

TEMPLATES["管理科学学报"] = JournalTemplate(
    name="《管理科学学报》",
    short_name="管理科学学报",
    category="管理",
    description="国家自然科学基金委员会管理科学部主办，管理科学方法论权威期刊，偏重运筹学、信息管理、供应链，C刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约15000字",
    blind_review=True,
    url="http://jmsc.buaa.edu.cn/",
    latex_code=r"""
% 《管理科学学报》LaTeX 模板
% 参考: http://jmsc.buaa.edu.cn/

\documentclass[10pt, UTF8, a4paper, twocolumn]{article}
\usepackage[top=2.54cm, bottom=2.54cm, left=2.5cm, right=2.5cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\bibliographystyle{gbt7714-plain}

\usepackage[compact]{titlesec}
\titlespacing*{\section}{0pt}{6pt}{6pt}
\titlespacing*{\subsection}{0pt}{4pt}{4pt}

\onehalfspacing
\setlength{\parindent}{2em}
\usepackage{lineno}
\linenumbers

\begin{document}

\begin{center}
  {\songti\zihao{-2} \textbf{论文标题}}

  \vspace{8pt}
  {\kaishu\zihao{-4}
    作者一$^{1}$ \quad 作者二$^{2}$
  }

  \vspace{4pt}
  {\fangsong\zihao{-5}
    $^{1,2}$北京航空航天大学经济管理学院，北京 100083
  }
\end{center}

\vspace{6pt}

\noindent\textbf{摘要：} 摘要内容（200-300字）。
\\[4pt]
\noindent\textbf{关键词：} 关键词1；关键词2；关键词3

\section{引言}
介绍研究背景与问题，研究意义与创新点。

\section{模型与算法}
\subsection{模型构建}
构建管理科学模型。
\subsection{算法设计}
设计求解算法，给出算法复杂度分析。

\section{算例分析}
通过数值算例验证模型和算法的有效性。

\section{结论}
总结全文。

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

TEMPLATES["系统工程学报"] = JournalTemplate(
    name="《系统工程学报》",
    short_name="系统工程学报",
    category="管理",
    description="中国系统工程学会主办，系统工程方法论权威期刊，偏重系统工程方法论，CSSCI扩展版",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约12000字",
    blind_review=True,
    url="http://jse.buaa.edu.cn/",
    latex_code=r"""
% 《系统工程学报》LaTeX 模板
% 参考: http://jse.buaa.edu.cn/

\documentclass[10pt, UTF8, a4paper]{ctexart}
\usepackage[top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\bibliographystyle{gbt7714-plain}

\ctexset{section/format={\centering\heiti\zihao{4}\bfseries},
          subsection/format={\raggedright\fangsong\zihao{-4}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}

\begin{document}

\begin{center}
  {\heiti\zihao{-2} 论文题目}

  \vspace{10pt}
  {\kaishu\zihao{-4}
    作者一$^{1}$，作者二$^{1,2}$
  }

  \vspace{4pt}
  {\fangsong\zihao{-5}
    $^{1}$北京航空航天大学系统工程系，北京 100083 \\
    $^{2}$某某大学某某学院，某某市 100000
  }
\end{center}

\vspace{8pt}

\noindent\textbf{摘要：} 摘要内容（约300字）。
\\[4pt]
\noindent\textbf{关键词：} 关键词1；关键词2；关键词3

\section{引言}
阐明系统工程问题的实际背景和理论意义。

\section{问题分析}
对系统工程问题进行系统分析，建立问题的数学描述。

\section{模型建立}
给出数学模型：
\begin{equation}
\label{eq:system}
\min_{x\in X} \quad F(x) = \left[f_1(x), f_2(x), \ldots, f_m(x)\right]^{\top}
\end{equation}

\section{求解方法}
设计求解方法，报告计算结果。

\section{结论}
总结全文，说明方法的有效性和适用范围。

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

TEMPLATES["中国管理科学"] = JournalTemplate(
    name="《中国管理科学》",
    short_name="中国管理科学",
    category="管理",
    description="中国优选法统筹法与经济数学研究会等主办，管理科学方法与应用，CSSCI来源期刊",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约15000字",
    blind_review=True,
    url="http://zgglkx.whu.edu.cn/",
    latex_code=r"""
% 《中国管理科学》LaTeX 模板
% 参考: http://zgglkx.whu.edu.cn/

\documentclass[10pt, UTF8, a4paper]{article}
\usepackage[top=2.5cm, bottom=2.5cm, left=3cm, right=3cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\bibliographystyle{gbt7714-plain}

\ctexsetup{section/format={\centering\heiti\zihao{4}\bfseries},
            subsection/format={\raggedright\fangsong\zihao{-4}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}

\begin{document}

\begin{center}
  {\heiti\zihao{-2} 论文题目}

  \vspace{1cm}
  {\kaishu\zihao{-4}
    作者一$^{1,2}$ \quad 作者二$^{1,2}$
  }

  \vspace{0.5cm}
  {\fangsong\zihao{-5}
    $^{1,2}$武汉大学经济与管理学院，武汉 430072
  }
\end{center}

\vspace{0.8cm}

\noindent\textbf{摘要：} 摘要内容。
\\[4pt]
\noindent\textbf{关键词：} 关键词1；关键词2；关键词3；关键词4

\section{引言}
研究背景、问题的提出与研究意义。

\section{模型构建}
构建管理科学模型，说明模型假设和适用范围。

\section{求解算法}
设计算法，给出算法步骤和复杂度分析。

\section{数值实验}
通过数值实验验证方法的有效性。

\section{结论}
总结全文，提出管理建议。

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

TEMPLATES["管理科学"] = JournalTemplate(
    name="《管理科学》",
    short_name="管理科学",
    category="管理",
    description="哈尔滨工业大学主办，管理科学与工程领域核心期刊，偏重理论与方法，CSSCI扩展版",
    bibliography_style="gbt7714-2015",
    required_packages=["ctex", "xeCJK", "natbib", "amsmath", "booktabs", "geometry",
                       "fancyhdr", "setspace", "graphicx"],
    page_limit="约12000字",
    blind_review=True,
    url="https://glkx.hit.edu.cn/",
    latex_code=r"""
% 《管理科学》LaTeX 模板
% 参考: https://glkx.hit.edu.cn/

\documentclass[10pt, UTF8, a4paper]{article}
\usepackage[top=2.5cm, bottom=2.5cm, left=3cm, right=3cm]{geometry}
\usepackage{xeCJK}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{amsmath, amssymb, booktabs, graphicx, setspace}
\bibliographystyle{gbt7714-plain}

\ctexsetup{section/format={\centering\heiti\zihao{4}\bfseries},
            subsection/format={\raggedright\fangsong\zihao{5}\bfseries}}

\onehalfspacing
\setlength{\parindent}{2em}

\begin{document}

\begin{center}
  {\songti\zihao{-2} \textbf{论文标题}}

  \vspace{8pt}
  {\kaishu\zihao{-4}
    作者一$^{1}$ \quad 作者二$^{1,2}$
  }

  \vspace{4pt}
  {\fangsong\zihao{-5}
    $^{1}$哈尔滨工业大学经济与管理学院，哈尔滨 150001 \\
    $^{2}$通信作者单位，邮编
  }
\end{center}

\vspace{8pt}

\noindent\textbf{摘要：} 摘要内容（不超过300字）。
\\[4pt]
\noindent\textbf{关键词：} 关键词1；关键词2；关键词3

\section{引言}
阐明研究背景、问题的提出、主要贡献。

\section{理论模型}
建立理论模型，给出命题和证明（或推导）。

\section{实证分析}
使用实证数据验证理论模型的主要结论。

\section{结论}
总结全文，说明研究局限和未来方向。

\bibliographystyle{gbt7714-plain}
\bibliography{references}

\end{document}
""",
)

# ═════════════════════════════════════════════════════════════════════════════════
# 通用模板快捷别名（兼容旧版本）
# ═════════════════════════════════════════════════════════════════════════════════

# 方便通过别名快速访问
_TEMPLATES_ALIASES = {
    "JFQA": TEMPLATES.get("JFQA"),
    "JCF": TEMPLATES.get("JCF"),
    "QJE": TEMPLATES.get("QJE"),
    "JPE": TEMPLATES.get("JPE"),
    "中国工业经济": TEMPLATES.get("中国工业经济"),
    "世界经济": TEMPLATES.get("世界经济"),
    "会计研究": TEMPLATES.get("会计研究"),
    "财政研究": TEMPLATES.get("财政研究"),
    "经济学季刊": TEMPLATES.get("经济学季刊"),
    "科研管理": TEMPLATES.get("科研管理"),
    "南开管理评论": TEMPLATES.get("南开管理评论"),
    "系统工程理论与实践": TEMPLATES.get("系统工程理论与实践"),
    "中国软科学": TEMPLATES.get("中国软科学"),
    "管理科学学报": TEMPLATES.get("管理科学学报"),
    "系统工程学报": TEMPLATES.get("系统工程学报"),
    "中国管理科学": TEMPLATES.get("中国管理科学"),
    "管理科学": TEMPLATES.get("管理科学"),
}
# Merge aliases into main dict (only add if key doesn't already exist)
for k, v in _TEMPLATES_ALIASES.items():
    if v is not None and k not in TEMPLATES:
        TEMPLATES[k] = v


# ═════════════════════════════════════════════════════════════════════════════════
# 期刊自动选择器 (JournalTemplateSelector)
# ═════════════════════════════════════════════════════════════════════════════════


JOURNAL_METADATA: dict[str, dict] = {
    # Academic CS
    "cvpr": {
        "full_name": "Conference on Computer Vision and Pattern Recognition",
        "publisher": "IEEE",
        "style": "cvpr",
        "packages": ["amsmath", "amssymb", "graphicx"],
        "page_limit": 8,
        "reference_format": "numerical",
        "anonymous": True,
        "latex_template": "cvpr_2026",
        "submission_style": True,
    },
    "neurips": {
        "full_name": "Conference on Neural Information Processing Systems",
        "publisher": "Curran Associates",
        "style": "neurips",
        "packages": ["amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 9,
        "reference_format": "natbib",
        "anonymous": True,
        "latex_template": "neurips_2026",
        "submission_style": True,
    },
    "iclr": {
        "full_name": "International Conference on Learning Representations",
        "publisher": "OpenReview",
        "style": "iclr",
        "packages": ["amsmath", "amssymb", "graphicx"],
        "page_limit": 10,
        "reference_format": "iclr",
        "anonymous": True,
        "latex_template": "iclr",
        "submission_style": True,
    },
    "acl": {
        "full_name": "Association for Computational Linguistics",
        "publisher": "ACL",
        "style": "acl",
        "packages": ["amsmath", "graphicx", "url"],
        "page_limit": 8,
        "reference_format": "acl",
        "anonymous": True,
        "latex_template": "acl",
        "submission_style": True,
    },
    # Finance / Economics
    "jfe": {
        "full_name": "Journal of Financial Economics",
        "publisher": "Elsevier",
        "style": "jfe",
        "packages": ["amsmath", "amssymb", "graphicx", "booktabs", "threeparttable"],
        "page_limit": 50,
        "reference_format": "jfe",
        "anonymous": False,
        "latex_template": "jfe",
        "submission_style": False,
    },
    "rfs": {
        "full_name": "Review of Financial Studies",
        "publisher": "Oxford",
        "style": "rfs",
        "packages": ["amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "rfs",
        "anonymous": False,
        "latex_template": "rfs",
        "submission_style": False,
    },
    "aer": {
        "full_name": "American Economic Review",
        "publisher": "AEA",
        "style": "aer",
        "packages": ["amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "aea",
        "anonymous": False,
        "latex_template": "aer",
        "submission_style": False,
    },
    "经济研究": {
        "full_name": "经济研究",
        "publisher": "中国社科院",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 30,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "管理世界": {
        "full_name": "管理世界",
        "publisher": "管理世界杂志社",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 30,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "金融研究": {
        "full_name": "金融研究",
        "publisher": "金融研究编辑部",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 25,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    # 新增金融Q1/Q2
    "jfqa": {
        "full_name": "Journal of Financial and Quantitative Analysis",
        "publisher": "Cambridge",
        "style": "aer",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "aer",
        "anonymous": True,
        "latex_template": "jfqa",
        "submission_style": False,
    },
    "jcf": {
        "full_name": "Journal of Corporate Finance",
        "publisher": "Elsevier",
        "style": "aer",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 40,
        "reference_format": "aer",
        "anonymous": True,
        "latex_template": "jcf",
        "submission_style": False,
    },
    "qje": {
        "full_name": "Quarterly Journal of Economics",
        "publisher": "Oxford",
        "style": "aer",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 60,
        "reference_format": "aer",
        "anonymous": True,
        "latex_template": "qje",
        "submission_style": False,
    },
    "jpe": {
        "full_name": "Journal of Political Economy",
        "publisher": "Chicago",
        "style": "chicago",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "chicago",
        "anonymous": True,
        "latex_template": "jpe",
        "submission_style": False,
    },
    "econometrica": {
        "full_name": "Econometrica",
        "publisher": "Econometric Society",
        "style": "econometrica",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "econometrica",
        "anonymous": True,
        "latex_template": "econometrica",
        "submission_style": False,
    },
    "restud": {
        "full_name": "Review of Economic Studies",
        "publisher": "Oxford",
        "style": "econometrica",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "econometrica",
        "anonymous": True,
        "latex_template": "restud",
        "submission_style": False,
    },
    "restat": {
        "full_name": "Review of Economics and Statistics",
        "publisher": "MIT Press",
        "style": "econometrica",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 40,
        "reference_format": "econometrica",
        "anonymous": True,
        "latex_template": "restat",
        "submission_style": False,
    },
    "jeea": {
        "full_name": "Journal of the European Economic Association",
        "publisher": "Oxford",
        "style": "econometrica",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 50,
        "reference_format": "econometrica",
        "anonymous": True,
        "latex_template": "jeea",
        "submission_style": False,
    },
    "aejae": {
        "full_name": "American Economic Journal: Applied Economics",
        "publisher": "AEA",
        "style": "aer",
        "packages": ["natbib", "amsmath", "amssymb", "graphicx", "booktabs"],
        "page_limit": 40,
        "reference_format": "aer",
        "anonymous": True,
        "latex_template": "aejae",
        "submission_style": False,
    },
    # 新增中国C刊
    "中国工业经济": {
        "full_name": "中国工业经济",
        "publisher": "中国社会科学院工业经济研究所",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs", "hyperref"],
        "page_limit": 30,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "世界经济": {
        "full_name": "世界经济",
        "publisher": "中国社会科学院世界经济与政治研究所",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 30,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "会计研究": {
        "full_name": "会计研究",
        "publisher": "中国会计学会",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 25,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "财政研究": {
        "full_name": "财政研究",
        "publisher": "中国财政学会",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 25,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "数量经济技术经济研究": {
        "full_name": "数量经济技术经济研究",
        "publisher": "中国社会科学院数量经济与技术经济研究所",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 25,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "统计研究": {
        "full_name": "统计研究",
        "publisher": "中国统计学会",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 25,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
    "经济学季刊": {
        "full_name": "经济学(季刊)",
        "publisher": "北京大学",
        "style": "ctex",
        "packages": ["ctex", "amsmath", "graphicx", "booktabs"],
        "page_limit": 35,
        "reference_format": "gbt7714",
        "anonymous": False,
        "latex_template": "ctex_article",
        "submission_style": False,
    },
}


class JournalTemplateSelector:
    """Automatically select and apply journal LaTeX template.

    Given a paper topic/abstract, or a journal name, this class:
    1. Detects the most appropriate journal
    2. Applies the correct LaTeX template
    3. Sets reference format
    4. Configures documentclass options

    Usage:
        selector = JournalTemplateSelector()

        # Auto-detect journal from topic
        journal = selector.detect_journal(
            topic="LLM在金融时间序列预测中的应用",
            keywords=["deep learning", "finance"]
        )
        print(journal["full_name"])  # "Conference on Neural Information Processing Systems"

        # Generate LaTeX for a specific venue
        latex = selector.generate_latex(
            content={"abstract": "...", "introduction": "..."},
            venue="neurips"
        )

        # Get reference format
        ref_fmt = selector.get_reference_format("jfe")
    """

    def __init__(self):
        self.journals = JOURNAL_METADATA

    def detect_journal(
        self,
        topic: str | None = None,
        abstract: str | None = None,
        keywords: list[str] | None = None,
    ) -> dict:
        """Detect most appropriate journal from topic/abstract/keywords.

        Uses keyword matching to score journals.

        Args:
            topic: Paper topic/title
            abstract: Paper abstract
            keywords: List of keywords

        Returns:
            Journal metadata dict from JOURNAL_METADATA.

        Raises:
            ValueError: If no text input provided.

        Example:
            >>> selector = JournalTemplateSelector()
            >>> journal = selector.detect_journal(
            ...     topic="碳排放权交易对企业绿色创新的影响",
            ...     keywords=["DID", "波特假说"]
            ... )
            >>> print(journal["short_name"])
            经济研究
        """
        if not topic and not abstract and not keywords:
            raise ValueError(
                "Must provide at least one of topic, abstract, or keywords"
            )

        text = " ".join(
            filter(None, [topic, abstract] + (keywords or []))
        ).lower()

        scores: dict[str, int] = {}
        scoring_rules: dict[str, list[str]] = {
            "cvpr": [
                "computer vision", "image", "video", "object detection",
                "segmentation", "recognition", "visual", "vision"
            ],
            "neurips": [
                "neural network", "deep learning", "reinforcement learning",
                "transformer", "gpt", "llm", "large language model",
                "optimization", "generative", "diffusion"
            ],
            "iclr": [
                "representation learning", "self-supervised", "generative model",
                "diffusion", "contrastive"
            ],
            "acl": [
                "natural language", "nlp", "language model", "text",
                "parsing", "translation", "summarization", "sentiment"
            ],
            # Finance journals
            "jfe": [
                "finance", "financial", "stock", "asset pricing",
                "corporate finance", "investment", "equity", "bond", "jfe"
            ],
            "jf": [
                "finance", "financial markets", "portfolio", "equity premium",
                "capital market", "jf", "journal of finance"
            ],
            "rfs": [
                "financial", "risk", "bank", "capital structure",
                "merger", "governance", "portfolio", "rfs"
            ],
            "jfqa": [
                "quantitative", "derivative", "option", "futures", "market microstructure",
                "jfqa", "financial analysis"
            ],
            "jcf": [
                "corporate", "merger", "acquisition", "governance", "m&a",
                "capital structure", "jcf", "leverage", "dividend"
            ],
            # Economics journals
            "aer": [
                "economics", "economic", "labor", "trade", "macro",
                "micro", "policy", "growth", "aer", "american economic"
            ],
            "qje": [
                "quarterly", "political economy", "labor economics", "public economics",
                "qje", "income", "wage", "employment"
            ],
            "jpe": [
                "political economy", "chicago", "jpe", "growth theory",
                "development", "economic history"
            ],
            "econometrica": [
                "econometrica", "econometric", "identification", "causal inference",
                "structural estimation", "game theory"
            ],
            "restud": [
                "restud", "economic theory", "mathematical economics",
                "dynamic programming", "mechanism design"
            ],
            "jeea": [
                "european", "euro area", "monetary union", "eea", "ecb",
                "european central bank", "sovereign debt"
            ],
            "aejae": [
                "applied", "experiment", "field experiment", "quasi-experiment",
                "natural experiment", "policy evaluation"
            ],
            "restat": [
                "restat", "econometrics", "time series", "panel data",
                "causal", "identification strategy"
            ],
            # Chinese journals
            "经济研究": [
                "经济", "宏观经济", "微观经济", "政策", "增长",
                "产业", "贸易", "DID", "双重差分", "经济研究"
            ],
            "管理世界": [
                "管理", "企业", "组织", "战略", "人力资源", "营销",
                "管理世界", "公司治理", "商业模式"
            ],
            "金融研究": [
                "金融", "货币", "银行", "资本市场", "证券", "保险",
                "金融研究", "利率", "汇率"
            ],
            "中国工业经济": [
                "产业", "工业", "企业", "规制", "垄断", "竞争",
                "中国工业经济", "产业政策", "僵尸企业"
            ],
            "世界经济": [
                "国际", "贸易", "汇率", "fdi", "外资", "跨国公司",
                "世界经济", "出口", "进口", "关税"
            ],
            "会计研究": [
                "会计", "审计", "财务报告", "盈余管理", "会计研究",
                "内部控制", "信息披露"
            ],
            "财政研究": [
                "财政", "税收", "公共支出", "财政研究", "预算",
                "国债", "转移支付"
            ],
            "数量经济技术经济研究": [
                "数量经济", "计量", "技术效率", "全要素生产率", "TFP",
                "数量经济技术经济研究", "随机前沿", "DEA"
            ],
            "统计研究": [
                "统计", "抽样", "参数估计", "假设检验", "统计研究",
                "非参数", "贝叶斯"
            ],
            "经济学季刊": [
                "经济学季刊", "北京大学", "理论经济", "实证经济",
                "制度经济", "新制度经济学"
            ],
        }

        for journal, keywords_list in scoring_rules.items():
            score = sum(1 for kw in keywords_list if kw in text)
            if score > 0:
                scores[journal] = score

        if not scores:
            return self.journals["neurips"]  # default

        best = max(scores, key=scores.get)
        return self.journals[best]

    def generate_latex(
        self,
        content: dict[str, str],
        venue: str,
        output_path: str | Path | None = None,
    ) -> str:
        """Generate complete LaTeX document for venue.

        Args:
            content: dict with keys like 'abstract', 'introduction', etc.
            venue: journal/conference name (e.g. "jfe", "cvpr", "neurips", "经济研究")
            output_path: optional path to save .tex file

        Returns:
            Generated LaTeX source code as string.
        """
        journal = self.journals.get(venue.lower(), self.journals["neurips"])
        template_code = self._get_template(journal, content)

        if output_path:
            Path(output_path).write_text(template_code, encoding="utf-8")

        return template_code

    def _get_template(self, journal: dict, content: dict) -> str:
        """Generate LaTeX template for journal."""
        style = journal.get("style", "neurips")
        packages = journal.get("packages", [])
        pkg_str = ", ".join(packages) if packages else ""
        journal_name = journal.get("full_name", journal.get("style", ""))

        abstract = content.get("abstract", "请在此输入摘要...")
        intro = content.get("introduction", "请在此输入引言...")
        title = content.get("title", "论文标题")

        parts = [
            f"% Auto-generated LaTeX for {journal_name}",
            f"% Style: {style}",
            f"% Packages: {pkg_str}",
            "",
            "\\documentclass[11pt]{article}",
            f"\\usepackage{{{pkg_str}}}",
        ]

        if "ctex" in packages:
            parts.append("\\usepackage{ctex}")
        if "natbib" in packages:
            parts.append("\\usepackage{natbib}")
        if "booktabs" in packages:
            parts.append("\\usepackage{booktabs}")
        if "hyperref" in packages:
            parts.append("\\usepackage[colorlinks=true]{hyperref}")

        parts.extend([
            f"\\title{{{title}}}",
            "",
            "\\author{",
            "    作者一$^{1}$ \\quad 作者二$^{2}$ \\quad 作者三$^{3}$",
            "}",
            "",
            "\\affiliation{",
            "    $^{1}$单位一 \\\\",
            "    $^{2}$单位二 \\\\",
            "    $^{3}$单位三",
            "}",
            "",
            "\\begin{document}",
            "",
            "\\maketitle",
            "",
            "\\begin{abstract}",
            abstract,
            "\\end{abstract}",
            "",
            "\\keywords{关键词1；关键词2；关键词3}",
            "",
            "\\section{Introduction}",
            "\\label{sec:intro}",
            intro,
            "",
            "\\section{Related Work}",
            "\\label{sec:related}",
            "",
            "\\section{Method}",
            "\\label{sec:method}",
            "",
            "\\section{Experiments}",
            "\\label{sec:exp}",
            "",
            "\\section{Conclusion}",
            "\\label{sec:concl}",
            "",
            f"\\bibliographystyle{{{style}}}",
            "\\bibliography{references}",
            "",
            "\\end{document}",
        ])

        return "\n".join(parts)

    def get_reference_format(self, venue: str) -> dict:
        """Get citation/reference format for venue.

        Args:
            venue: Journal/conference name

        Returns:
            Dict with 'style', 'bibliography' key, etc.
        """
        formats: dict[str, dict] = {
            "cvpr": {
                "style": "numerical",
                "bibliography": "thebibliography",
                "packages": ["amsmath", "amssymb", "graphicx"],
            },
            "neurips": {
                "style": "natbib",
                "bibliography": "References",
                "packages": ["natbib", "amsmath"],
            },
            "iclr": {
                "style": "natbib",
                "bibliography": "References",
                "packages": ["natbib"],
            },
            "acl": {
                "style": "acl",
                "bibliography": "References",
                "packages": ["acl_natbib"],
            },
            "jfe": {
                "style": "jfe",
                "bibliography": "thebibliography",
                "packages": ["natbib"],
            },
            "rfs": {
                "style": "rfs",
                "bibliography": "thebibliography",
                "packages": ["natbib"],
            },
            "aer": {
                "style": "aea",
                "bibliography": "thebibliography",
                "packages": ["natbib"],
            },
            "经济研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "管理世界": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "金融研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            # Finance Q1/Q2
            "jfqa": {
                "style": "aer",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            "jcf": {
                "style": "aer",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            # Economics Q1
            "qje": {
                "style": "aer",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath"],
            },
            "jpe": {
                "style": "chicago",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath"],
            },
            "econometrica": {
                "style": "econometrica",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            "restud": {
                "style": "econometrica",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            "restat": {
                "style": "econometrica",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            "jeea": {
                "style": "econometrica",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            "aejae": {
                "style": "aer",
                "bibliography": "thebibliography",
                "packages": ["natbib", "amsmath", "booktabs"],
            },
            # Chinese C-journals
            "中国工业经济": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex", "booktabs"],
            },
            "世界经济": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex", "booktabs"],
            },
            "会计研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "财政研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "数量经济技术经济研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "统计研究": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex"],
            },
            "经济学季刊": {
                "style": "gbt7714",
                "bibliography": "参考文献",
                "packages": ["ctex", "booktabs"],
            },
        }
        return formats.get(venue.lower(), formats["neurips"])

    def list_journals(self) -> list[dict]:
        """List all available journals with metadata."""
        return [
            {"key": k, **v}
            for k, v in self.journals.items()
        ]


def generate_paper(
    template_name: str,
    output_path: str | Path,
    **kwargs,
) -> Path:
    """
    生成论文模板文件。

    Args:
        template_name: 模板名称
        output_path: 输出路径
        **kwargs: 自定义内容（标题、作者等）

    Returns:
        输出文件路径
    """
    template = get_template(template_name)
    if not template:
        raise ValueError(f"未找到模板: {template_name}")

    return template.generate_example(output_path)


# ═════════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="期刊模板管理器")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有模板")
    parser.add_argument("--category", "-c", help="按类别筛选")
    parser.add_argument("--generate", "-g", nargs=2, metavar=("TEMPLATE", "OUTPUT"),
                       help="生成示例文件")
    parser.add_argument("--info", "-i", help="查看模板信息")

    args = parser.parse_args()

    if args.list:
        templates = list_templates(args.category)
        print(f"\n{'='*70}")
        print(f"  可用期刊模板 ({len(templates)} 个)")
        print(f"{'='*70}")

        # 按类别分组
        by_category = {}
        for t in templates:
            if t.category not in by_category:
                by_category[t.category] = []
            by_category[t.category].append(t)

        for cat, tmpls in by_category.items():
            print(f"\n### {cat}")
            for t in tmpls:
                print(f"  [{t.short_name:15}] {t.name}")
                print(f"       页数: {t.page_limit or '无限制'} | 盲审: {'是' if t.blind_review else '否'}")

    elif args.generate:
        template_name, output_path = args.generate
        template = get_template(template_name)

        if not template:
            print(f"未找到模板: {template_name}")
            return

        path = template.generate_example(output_path)
        print(f"✅ 已生成: {path}")

    elif args.info:
        template = get_template(args.info)
        if not template:
            print(f"未找到模板: {args.info}")
            return

        print(f"\n{'='*70}")
        print(f"  {template.name}")
        print(f"{'='*70}")
        print(f"  简称: {template.short_name}")
        print(f"  类别: {template.category}")
        print(f"  描述: {template.description}")
        print(f"  页数限制: {template.page_limit or '无'}")
        print(f"  盲审: {'是' if template.blind_review else '否'}")
        print(f"  参考文献格式: {template.bibliography_style}")
        print(f"  必需宏包: {', '.join(template.required_packages)}")
        print(f"  官网: {template.url}")

    else:
        parser.print_help()
        print("\n可用模板:")
        for name in TEMPLATES:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
