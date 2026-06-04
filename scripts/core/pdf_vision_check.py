"""PDF 视觉检查 — 使用 VLM 检测 LaTeX 编译后的布局问题.

功能：
  - 提取 PDF 页面截图（PNG）
  - 使用 VLM 分析布局问题（溢出/字体过小/图表重叠）
  - 检测页面边距和排版规范
  - 与 TexGuardian 7 步审查流水线对齐

依赖：
  - pymupdf（fitz）：PDF 截图提取
  - openai 或 anthropic：VLM 视觉分析

Usage:
    checker = PDFVisionChecker()
    issues = checker.check("papers/draft_v1/main.pdf")
    checker.print_report()
"""

from __future__ import annotations

import io
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "PDFVisionIssue",
    "PDFVisionChecker",
]

logger = logging.getLogger(__name__)


@dataclass
class PDFVisionIssue:
    """
    单条 PDF 视觉问题。

    Attributes
    ----------
    severity : str
        CRITICAL / WARNING / INFO。
    page : int
        页码（1-indexed）。
    location : str
        问题位置描述。
    description : str
        问题描述。
    suggestion : str
        修复建议。
    """

    severity: str
    page: int
    location: str
    description: str
    suggestion: str = ""


class PDFVisionChecker:
    """
    PDF 视觉检查器 — 基于 VLM 的 LaTeX 编译质量保障。

    检查维度：

    | # | 维度 | 严重程度 | 说明 |
    |---|------|---------|------|
    | V1 | 页面溢出 | CRITICAL | 图表/文字超出页面边界 |
    | V2 | 字体过小 | WARNING | 正文字体 < 9pt |
    | V3 | 图表重叠 | WARNING | 两个浮点数环境重叠 |
    | V4 | 空白过多 | INFO | 页面大量空白（> 40%）|
    | V5 | 标题截断 | CRITICAL | 节标题被截断 |
    | V6 | 参考文献溢出 | WARNING | 参考文献溢出页面 |
    | V7 | 公式溢出 | CRITICAL | 长公式超出文本宽度 |
    | V8 | 表格过宽 | WARNING | 表格超出文本宽度 |

    Usage
    -----
        checker = PDFVisionChecker()
        checker.check("papers/draft_v1/main.pdf")
        checker.print_report()

        # 仅提取截图（不调用 VLM）
        pages = checker.extract_pages("papers/draft_v1/main.pdf")
        for page_num, img_bytes in pages:
            with open(f"page_{page_num}.png", "wb") as f:
                f.write(img_bytes)
    """

    def __init__(
        self,
        vlm_provider: str = "claude",
        vlm_model: str | None = None,
        api_key: str | None = None,
        *,
        dpi: int = 150,
        min_font_size: float = 9.0,
        max_whitespace_ratio: float = 0.4,
    ):
        self.dpi = dpi
        self.min_font_size = min_font_size
        self.max_whitespace_ratio = max_whitespace_ratio
        self.vlm_provider = vlm_provider
        self.vlm_model = vlm_model
        self.api_key = api_key
        self.issues: list[PDFVisionIssue] = []
        self._vlm_client = None
        self._init_vlm()

    def _init_vlm(self):
        """初始化 VLM 客户端。"""
        if self.vlm_provider == "openai":
            try:
                from openai import OpenAI
                self._vlm_client = OpenAI(api_key=self.api_key)
            except ImportError:
                logger.warning("[PDFVisionChecker] openai not installed")
        elif self.vlm_provider == "anthropic":
            try:
                import anthropic
                self._vlm_client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                logger.warning("[PDFVisionChecker] anthropic not installed")

    def _extract_page_image(self, pdf_path: Path, page_num: int) -> bytes | None:
        """
        提取单页 PNG 截图。

        Parameters
        ----------
        pdf_path : Path
            PDF 文件路径。
        page_num : int
            页码（0-indexed）。

        Returns
        -------
        bytes | None
            PNG 图像字节。
        """
        try:
            import fitz  # pymupdf
        except ImportError:
            try:
                import PyMuPDF as fitz
            except ImportError:
                logger.warning(
                    "[PDFVisionChecker] pymupdf not installed. "
                    "Run: pip install pymupdf"
                )
                return None

        try:
            doc = fitz.open(str(pdf_path))
            if page_num >= len(doc):
                return None
            page = doc[page_num]
            mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            doc.close()
            return img_bytes
        except Exception as exc:
            logger.warning(f"[PDFVisionChecker] Failed to extract page {page_num}: {exc}")
            return None

    def extract_pages(
        self,
        pdf_path: str | Path,
        max_pages: int = 5,
    ) -> list[tuple[int, bytes]]:
        """
        提取 PDF 前 N 页的 PNG 截图。

        Returns
        -------
        list[tuple[page_num (1-indexed), png_bytes]]
        """
        pdf_path = Path(pdf_path)
        pages: list[tuple[int, bytes]] = []

        for i in range(max_pages):
            img = self._extract_page_image(pdf_path, i)
            if img is None:
                break
            pages.append((i + 1, img))

        return pages

    def _analyze_with_vlm(
        self,
        page_num: int,
        image_bytes: bytes,
    ) -> list[PDFVisionIssue]:
        """使用 VLM 分析单页图像。"""
        if self._vlm_client is None:
            return []

        issues: list[PDFVisionIssue] = []
        prompt = """你是一位学术论文排版质量审核员。请分析以下 PDF 页面截图，检测以下问题：

1. **CRITICAL - 页面溢出**：图表、文字或公式超出页面边界
2. **CRITICAL - 标题截断**：节标题（section/subsection）被截断
3. **CRITICAL - 公式溢出**：长数学公式超出文本宽度
4. **WARNING - 字体过小**：正文字体明显小于正常大小（< 9pt）
5. **WARNING - 图表重叠**：两个浮动体（figure/table）重叠
6. **WARNING - 表格过宽**：表格超出文本宽度
7. **INFO - 空白过多**：页面超过 40% 为空白

请以 JSON 格式输出（仅 JSON，不要其他内容）：
{
  "issues": [
    {
      "severity": "CRITICAL|WARNING|INFO",
      "location": "如：顶部/底部/左侧/右侧/中间区域",
      "description": "问题描述",
      "suggestion": "修复建议"
    }
  ]
}

如果页面没有问题，返回空的 issues 数组：{"issues": []}"""

        try:
            if self.vlm_provider == "openai":
                import base64
                b64 = base64.b64encode(image_bytes).decode()
                response = self._vlm_client.chat.completions.create(
                    model=self.vlm_model or "gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64}",
                                        "detail": "low",
                                    },
                                },
                            ],
                        }
                    ],
                    max_tokens=512,
                )
                import json
                text = response.choices[0].message.content
                data = json.loads(text)
                for item in data.get("issues", []):
                    issues.append(PDFVisionIssue(
                        severity=item["severity"],
                        page=page_num,
                        location=item.get("location", ""),
                        description=item["description"],
                        suggestion=item.get("suggestion", ""),
                    ))

            elif self.vlm_provider == "anthropic":
                import base64
                b64 = base64.b64encode(image_bytes).decode()
                response = self._vlm_client.messages.create(
                    model=self.vlm_model or "claude-3-5-sonnet-20241022",
                    max_tokens=512,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": b64,
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                )
                import json
                text = response.content[0].text
                data = json.loads(text)
                for item in data.get("issues", []):
                    issues.append(PDFVisionIssue(
                        severity=item["severity"],
                        page=page_num,
                        location=item.get("location", ""),
                        description=item["description"],
                        suggestion=item.get("suggestion", ""),
                    ))

        except Exception as exc:
            logger.warning(f"[PDFVisionChecker] VLM analysis failed for page {page_num}: {exc}")

        return issues

    def check(
        self,
        pdf_path: str | Path,
        max_pages: int = 10,
        use_vlm: bool = True,
    ) -> list[PDFVisionIssue]:
        """
        全面检查 PDF 视觉问题。

        Parameters
        ----------
        pdf_path : str | Path
            PDF 文件路径。
        max_pages : int
            最多检查的页数（默认前 10 页）。
        use_vlm : bool
            是否使用 VLM 分析（True = 更准确但更慢）。

        Returns
        -------
        list[PDFVisionIssue]
        """
        self.issues = []
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            logger.error(f"[PDFVisionChecker] PDF not found: {pdf_path}")
            return self.issues

        logger.info(f"[PDFVisionChecker] Checking {pdf_path} ({max_pages} pages)")

        # 提取页面截图
        pages = self.extract_pages(pdf_path, max_pages=max_pages)
        logger.info(f"[PDFVisionChecker] Extracted {len(pages)} pages")

        # VLM 分析
        if use_vlm and self._vlm_client:
            for page_num, img_bytes in pages:
                page_issues = self._analyze_with_vlm(page_num, img_bytes)
                self.issues.extend(page_issues)
                logger.info(f"[PDFVisionChecker] Page {page_num}: {len(page_issues)} issues")
        else:
            # 无 VLM 时的基本检查
            self._basic_check(pdf_path, pages)

        return self.issues

    def _basic_check(
        self,
        pdf_path: Path,
        pages: list[tuple[int, bytes]],
    ):
        """无 VLM 时的基本启发式检查。"""
        try:
            import fitz
            doc = fitz.open(str(pdf_path))

            for page_idx, (page_num, _) in enumerate(pages):
                if page_idx >= len(doc):
                    break
                page = doc[page_idx]

                # 检查字体大小（基本近似）
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:  # 仅文本块
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span["size"] < self.min_font_size:
                                self.issues.append(PDFVisionIssue(
                                    severity="WARNING",
                                    page=page_num,
                                    location=f"Block at y={span['bbox'][1]:.0f}",
                                    description=f"Small font size: {span['size']:.1f}pt",
                                    suggestion=f"Increase font size above {self.min_font_size}pt",
                                ))

                # 检查页面使用率
                page_rect = page.rect
                used_area = sum(
                    abs(b["bbox"][2] - b["bbox"][0]) * abs(b["bbox"][3] - b["bbox"][1])
                    for b in blocks
                    if b.get("bbox")
                )
                total_area = abs(page_rect.width) * abs(page_rect.height)
                if total_area > 0:
                    whitespace_ratio = 1 - (used_area / total_area)
                    if whitespace_ratio > self.max_whitespace_ratio:
                        self.issues.append(PDFVisionIssue(
                            severity="INFO",
                            page=page_num,
                            location="整个页面",
                            description=f"High whitespace: {whitespace_ratio:.1%} empty",
                            suggestion="Consider adding more content or adjusting layout",
                        ))

            doc.close()
        except Exception as exc:
            logger.warning(f"[PDFVisionChecker] Basic check failed: {exc}")

    def has_critical(self) -> bool:
        """返回是否有 CRITICAL 问题。"""
        return any(i.severity == "CRITICAL" for i in self.issues)

    def print_report(self, file=None):
        """打印格式化报告。"""
        if not self.issues:
            print("✅ PDF Vision Check: No issues found", file=file)
            return

        critical = [i for i in self.issues if i.severity == "CRITICAL"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        infos = [i for i in self.issues if i.severity == "INFO"]

        print(f"PDF Vision Report: {len(self.issues)} issues", file=file)
        print(f"  {'🔴' if critical else '  '} CRITICAL: {len(critical)}", file=file)
        print(f"  {'🟡' if warnings else '  '} WARNING : {len(warnings)}", file=file)
        print(f"  {'🔵' if infos else '  '} INFO    : {len(infos)}", file=file)
        print(file=file)

        for issue in self.issues:
            icon = {
                "CRITICAL": "🔴",
                "WARNING": "🟡",
                "INFO": "🔵",
            }.get(issue.severity, "  ")
            print(
                f"  {icon} [Page {issue.page}] {issue.description}",
                file=file,
            )
            if issue.location:
                print(f"      位置: {issue.location}", file=file)
            if issue.suggestion:
                print(f"      → {issue.suggestion}", file=file)

    def to_dict(self) -> dict:
        """导出为字典。"""
        return {
            "total_issues": len(self.issues),
            "critical_count": sum(1 for i in self.issues if i.severity == "CRITICAL"),
            "warning_count": sum(1 for i in self.issues if i.severity == "WARNING"),
            "info_count": sum(1 for i in self.issues if i.severity == "INFO"),
            "issues": [
                {
                    "severity": i.severity,
                    "page": i.page,
                    "location": i.location,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }
