"""us_esg docx 与 tex 一致性测试。"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


DOCX_PATH = Path("papers/us_esg_financing/esg_financing_paper.docx")


@pytest.fixture(scope="module")
def docx_xml():
    """读取 docx 内部 XML（如果文件不存在则 skip）。"""
    if not DOCX_PATH.exists():
        pytest.skip(f"{DOCX_PATH} 不存在 — 先跑 scripts/us_esg_formatter.py")
    with zipfile.ZipFile(DOCX_PATH) as z:
        return z.read("word/document.xml").decode("utf-8")


@pytest.fixture(scope="module")
def docx_text(docx_xml):
    """提取纯文本。"""
    text = re.sub(r"<[^>]+>", " ", docx_xml)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def test_docx_has_substantial_content(docx_text):
    """docx 文本长度应 > 8000 字（之前只 4779）。"""
    assert len(docx_text) > 8000, f"docx 文本仅 {len(docx_text)} 字，内容不足"


def test_docx_has_subscript_runs(docx_xml):
    """docx 必须有下标（之前 0 个）。"""
    n_sub = docx_xml.count('w:val="subscript"')
    assert n_sub > 5, f"subscript 元素仅 {n_sub} 个，应 >= 5"


def test_docx_has_superscript_runs(docx_xml):
    """docx 必须有上标（之前 0 个）。"""
    n_sup = docx_xml.count('w:val="superscript"')
    assert n_sup > 0, f"superscript 元素 0 个，数学符号标注缺失"


def test_docx_has_greek_letters(docx_text):
    """docx 必须有希腊字母（β α γ ε μ λ 等）。"""
    greek_chars = sum(
        docx_text.count(c) for c in ["α", "β", "γ", "δ", "σ", "ε", "μ", "λ", "Σ"]
    )
    assert greek_chars > 5, f"希腊字母仅 {greek_chars} 个"


def test_docx_has_embedded_images():
    """docx 必须嵌入图片（之前 0 张）。"""
    with zipfile.ZipFile(DOCX_PATH) as z:
        media = [n for n in z.namelist() if "media" in n]
    assert len(media) >= 3, f"docx 仅嵌入 {len(media)} 张图"


def test_docx_has_tables():
    """docx 必须有表格（之前 0 个）。"""
    with zipfile.ZipFile(DOCX_PATH) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    n_tables = xml.count("<w:tbl>")
    assert n_tables >= 4, f"docx 仅 {n_tables} 个表格，应 >= 4"


def test_docx_chinese_font_configured():
    """docx 应配置中文字体（eastAsia）。"""
    with zipfile.ZipFile(DOCX_PATH) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        styles_xml = z.read("word/styles.xml").decode("utf-8")
    # w:rFonts 元素 + eastAsia 属性
    assert 'eastAsia' in xml or 'eastAsia' in styles_xml, (
        "docx 未配置中文字体（缺 w:rFonts eastAsia）"
    )


def test_docx_full_paper_sections(docx_text):
    """docx 应包含完整 5 节 + Abstract + References。"""
    required_phrases = [
        "Abstract", "Introduction", "Literature Review",
        "Research Design", "Empirical Results", "Conclusion", "References",
        "Parallel Trends", "Heterogeneity", "Mechanism",
    ]
    for phrase in required_phrases:
        assert phrase in docx_text, f"docx 缺 '{phrase}' 章节"


def test_docx_did_coefficient_reported(docx_text):
    """docx 应报告 DID 系数（不是占位）。"""
    # 表 3 中系数至少有一个出现
    assert any(s in docx_text for s in ["0.0107", "0.0130", "0.0879", "0.0358"]), (
        "docx 缺 DID 系数报告"
    )


def test_docx_equation_rendered(docx_text):
    """docx 应包含主回归方程（β_1 等）。"""
    # β 字符
    assert "β" in docx_text, "docx 缺回归方程中的 β 系数"
