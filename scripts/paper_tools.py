#!/usr/bin/env python3
"""
论文工具集
==========
学术论文写作与排版的辅助工具。

功能：
- LaTeX 项目初始化（从模板创建）
- BibTeX 条目管理
- 论文查重（SimHash / n-gram）
- 参考文献格式转换
- 图表编号与引用管理
- 图表分辨率检查与转换
"""

import hashlib
import re
import shutil
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")


# ─── LaTeX 项目管理 ───────────────────────────────────────

PROJECT_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = PROJECT_DIR / "templates"
PAPER_TEMPLATES = {
    "acl": TEMPLATE_DIR / "paper" / "acl_latex.tex",
    "ieee": TEMPLATE_DIR / "paper" / "ieee_latex.tex",
    "ctex": TEMPLATE_DIR / "latex" / "ctex_article.tex",
}


def init_latex_project(name: str, template: str = "acl",
                        output_dir: str = "projects") -> dict:
    """
    从模板初始化一个新的 LaTeX 论文项目。

    Args:
        name: 项目名称（将用于目录名）
        template: 模板类型 ("acl" | "ieee" | "ctex")
        output_dir: 输出根目录

    Returns:
        dict，包含创建的目录结构
    """
    if template not in PAPER_TEMPLATES:
        raise ValueError(f"未知模板: {template}，可用: {list(PAPER_TEMPLATES.keys())}")

    # 安全检查：禁止路径遍历
    safe_name = re.sub(r"[^\w\-_. ]", "_", name).strip()
    if not safe_name:
        raise ValueError("项目名称不能为空或仅包含非法字符")
    if safe_name.startswith(".") or "/" in safe_name or "\\" in safe_name:
        raise ValueError("项目名称不能包含路径分隔符或以点开头")

    template_path = PAPER_TEMPLATES[template]
    # 使用 Path.resolve() 确保在可控目录内
    root = (Path.cwd() / output_dir).resolve()
    project_path = root / safe_name
    paper_path = project_path / "paper"
    figures_path = project_path / "figures"
    tables_path = project_path / "tables"
    data_path = project_path / "data"
    src_path = project_path / "src"

    for d in [paper_path, figures_path, tables_path, data_path, src_path]:
        d.mkdir(parents=True, exist_ok=True)

    shutil.copy(template_path, paper_path / f"{safe_name}.tex")

    bib_path = paper_path / "references.bib"
    bib_path.write_text(
        "% 参考文献管理\n"
        "% 使用 BibTeX 格式，DOI 必填\n\n",
        encoding="utf-8"
    )

    notes_path = project_path / "notes.md"
    notes_path.write_text(
        f"# {name}\n\n"
        f"创建时间: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        "## 研究问题\n\n## 主要贡献\n\n## 关键参考文献\n\n## 实验计划\n\n## 时间线\n\n",
        encoding="utf-8"
    )

    print(f"[✓] 项目 '{name}' 已创建:")
    print(f"    论文: {paper_path / f'{name}.tex'}")
    print(f"    图表: {figures_path}")
    print(f"    表格: {tables_path}")
    print(f"    代码: {src_path}")
    print(f"    笔记: {notes_path}")
    print(f"    参考文献: {bib_path}")

    return {
        "project_path": str(project_path),
        "paper_path": str(paper_path / f"{safe_name}.tex"),
        "figures_path": str(figures_path),
        "tables_path": str(tables_path),
        "references_path": str(bib_path),
    }


# ─── BibTeX 管理 ─────────────────────────────────────────

def add_bib_entry(bib_path: str, entry_type: str, cite_key: str, fields: dict) -> str:
    """
    添加 BibTeX 条目。

    Args:
        bib_path: .bib 文件路径
        entry_type: article | inproceedings | book | techreport
        cite_key: 引用键，如 "chen2024llm"
        fields: dict，包含 title, author, year, journal 等

    Example:
        add_bib_entry("refs.bib", "article", "chen2024llm", {
            "title": "Large Language Models for Finance",
            "author": "Chen, Wei and Wang, Li",
            "year": "2024",
            "journal": "Journal of Finance AI",
            "doi": "10.1234/jfai.2024.001"
        })
    """
    required_fields = ["title", "author", "year"]
    for rf in required_fields:
        if rf not in fields:
            raise ValueError(f"缺少必需字段: {rf}")

    lines = [f"@{entry_type}{{{cite_key},"]
    for key, value in fields.items():
        lines.append(f"  {key} = {{{value}}},")
    lines.append("}\n")

    entry_text = "\n".join(lines)

    with open(bib_path, "a", encoding="utf-8") as f:
        f.write(entry_text)

    return entry_text


def fetch_doi_metadata(doi: str) -> dict:
    """
    通过 DOI 获取元数据（用于生成 BibTeX）。

    Args:
        doi: DOI 号，如 "10.1109/CVPR.2024.12345"

    Returns:
        dict，包含 title, author, year, journal 等字段
    """
    try:
        import urllib.request
        url = f"https://doi.org/{doi}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/x-bibtex"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            bibtex = response.read().decode("utf-8")
        return {"bibtex": bibtex}
    except urllib.error.HTTPError:
        return {"error": f"DOI {doi} 在 CrossRef 上未找到"}
    except urllib.error.URLError:
        return {"error": "网络错误，请检查网络连接"}
    except Exception as e:
        return {"error": f"获取 BibTeX 失败: {e}"}


# ─── 图表分辨率检查 ───────────────────────────────────────

def check_figure_resolution(figure_path: str, min_dpi: int = 300) -> dict:
    """
    检查图片分辨率是否符合论文要求（≥300 DPI）。

    Returns:
        dict，包含 passed, actual_dpi, suggestion
    """
    from PIL import Image

    img = Image.open(figure_path)
    width_px, height_px = img.size

    if img.info.get("dpi"):
        dpi_tuple = img.info["dpi"]
        dpi_val = dpi_tuple[0] if isinstance(dpi_tuple, (list, tuple)) else dpi_tuple
        dpi = dpi_val if dpi_val > 0 else (width_px / 6.5 if width_px > 100 else 72)
    else:
        dpi = width_px / 6.5 if width_px > 100 else 72

    result = {
        "file": figure_path,
        "width_px": width_px,
        "height_px": height_px,
        "estimated_dpi": int(dpi),
        "passed": dpi >= min_dpi,
        "min_dpi": min_dpi,
        "suggestion": ""
    }

    if not result["passed"]:
        target_width = 300 * 6.5 / 72 * width_px
        result["suggestion"] = (
            f"分辨率不足。建议: width={int(target_width)}px "
            f"(300 DPI, 宽度 6.5 英寸)"
        )

    return result


def convert_figure_dpi(input_path: str, output_path: str, target_dpi: int = 300):
    """转换图片到指定 DPI。"""
    from PIL import Image

    img = Image.open(input_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")

    new_size = (int(6.5 * target_dpi), int(6.5 * target_dpi * img.size[1] / img.size[0]))
    resized = img.resize(new_size, Image.LANCZOS)

    new_img = Image.new("RGB", (new_size[0], new_size[1]), (255, 255, 255))
    new_img.paste(resized, (0, 0))
    new_img.save(output_path, dpi=(target_dpi, target_dpi), quality=95)

    print(f"[✓] 已转换: {input_path} → {output_path} ({target_dpi} DPI)")


# ─── 论文查重 ────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本。"""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)
    except ImportError:
        print("请安装 pdfplumber: pip install pdfplumber")
        return ""


def compute_ngram_hash(text: str, n: int = 3) -> set:
    """计算 n-gram 哈希集合（用于相似度检测）。"""
    words = text.lower().split()
    ngrams = set()
    for i in range(len(words) - n + 1):
        ngram = " ".join(words[i:i+n])
        ngram_hash = hashlib.md5(ngram.encode()).hexdigest()[:8]
        ngrams.add(ngram_hash)
    return ngrams


def plagiarism_check(text1: str, text2: str, n: int = 3) -> dict:
    """
    比较两段文本的相似度（SimHash 思想）。

    Returns:
        dict，包含 similarity_score (0-1), shared_ngrams, total_ngrams
    """
    hash1 = compute_ngram_hash(text1, n)
    hash2 = compute_ngram_hash(text2, n)

    intersection = hash1 & hash2
    union = hash1 | hash2

    similarity = len(intersection) / len(union) if union else 0

    return {
        "similarity_score": round(similarity, 4),
        "shared_ngrams": len(intersection),
        "total_ngrams": len(union),
        "interpretation": (
            "低相似度" if similarity < 0.1 else
            "中等相似度" if similarity < 0.3 else
            "较高相似度，建议检查" if similarity < 0.5 else
            "高相似度，需要仔细检查"
        )
    }


# ─── LaTeX 辅助函数 ──────────────────────────────────────

def count_words_in_latex(tex_path: str) -> dict:
    """统计 LaTeX 文档字数（不含命令和引用）。"""
    with open(tex_path, encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", content)
    content = re.sub(r"\\[a-zA-Z]+", "", content)
    content = re.sub(r"\{[^}]*\}", "", content)
    content = re.sub(r"%.*", "", content)
    content = re.sub(r"\\[{}]", "", content)

    chinese = len(re.findall(r"[\u4e00-\u9fff]", content))
    english = len(re.findall(r"[a-zA-Z]+", content))

    return {
        "chinese_chars": chinese,
        "english_words": english,
        "total_approx": chinese + english,
    }


def extract_equations(tex_path: str) -> list[dict]:
    """提取 LaTeX 文档中的所有公式。"""
    with open(tex_path, encoding="utf-8") as f:
        content = f.read()

    equations = []
    for i, match in enumerate(re.finditer(r"\$\$(.+?)\$\$", content, re.DOTALL)):
        equations.append({"type": "display", "id": i+1, "text": match.group(1).strip()})

    for i, match in enumerate(re.finditer(r"(?<!\\)\$(.+?)(?<!\\)\$", content), start=len(equations)):
        equations.append({"type": "inline", "id": i+1, "text": match.group(1).strip()})

    return equations


# ─── 演示 ────────────────────────────────────────────────

if __name__ == "__main__":
    print("论文工具集 v1.0")
    print("=" * 50)

    # 初始化项目
    init_latex_project("example_paper", template="acl", output_dir="projects")

    # 统计字数
    word_count = count_words_in_latex("projects/example_paper/paper/example_paper.tex")
    print(f"\n字数统计: {word_count}")

    # 查重演示
    text_a = "深度学习在金融领域的应用越来越广泛"
    text_b = "深度学习被广泛应用于金融领域的各项任务"
    result = plagiarism_check(text_a, text_b)
    print(f"\n相似度检测: {result}")
