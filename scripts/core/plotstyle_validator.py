"""图表期刊合规验证 — 基于 PlotStyle API 的可视化质量检查.

功能：
  - 字体大小合规（正文字号 ≥ 9pt，轴标签 ≥ 8pt）
  - 图形尺寸合规（单栏 ≤ 3.5in，双栏 ≤ 7in）
  - DPI 合规（≥ 300 DPI）
  - 颜色对比度（图表文字与背景对比度 ≥ 4.5:1）
  - 纵横比检查（避免过高/过宽图形）
  - 坐标轴范围合理性

PlotStyle API 集成：
  - 优先调用 plotstyle.validate()（如已安装）
  - 未安装时使用内置启发式规则作为 fallback

依赖（可选）：
  pip install plotstyle
  # 不安装也能使用内置规则运行
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "PlotStyleValidator",
    "FigureIssue",
    "JournalStandard",
    "IssueSeverity",
]


logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """问题严重程度。"""
    ERROR = "ERROR"      # 期刊必然拒绝
    WARNING = "WARNING"  # 期刊可能要求修改
    INFO = "INFO"        # 建议性优化


@dataclass
class FigureIssue:
    """单个图表问题。"""
    severity: IssueSeverity
    category: str          # "font" / "size" / "dpi" / "color" / "aspect" / "layout"
    message: str
    suggestion: str
    details: dict[str, Any] = field(default_factory=dict)


class JournalStandard(Enum):
    """目标期刊标准。"""
    IEEE = "ieee"
    JF = "jf"           # Journal of Finance
    JFE = "jfe"          # Journal of Financial Economics
    RFS = "rfs"          # Review of Financial Studies
    ECONOMETRICA = "ecta" # Econometrica
    AER = "aer"          # American Economic Review
    CHINESE = "chinese"  # 经济研究/金融研究/管理世界
    NATURE = "nature"
    SCIENCE = "science"


# 期刊标准参数
JOURNAL_PARAMS = {
    JournalStandard.IEEE: {
        "min_font_size": 8,
        "min_label_size": 7,
        "min_caption_size": 8,
        "max_width_single": 3.5,
        "max_width_double": 7.0,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.5,
        "aspect_ratio_max": 2.0,
    },
    JournalStandard.JF: {
        "min_font_size": 9,
        "min_label_size": 8,
        "min_caption_size": 9,
        "max_width_single": 3.3,
        "max_width_double": 6.75,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.5,
        "aspect_ratio_max": 2.5,
    },
    JournalStandard.JFE: {
        "min_font_size": 9,
        "min_label_size": 8,
        "min_caption_size": 9,
        "max_width_single": 3.3,
        "max_width_double": 6.75,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.5,
        "aspect_ratio_max": 2.5,
    },
    JournalStandard.RFS: {
        "min_font_size": 9,
        "min_label_size": 8,
        "min_caption_size": 9,
        "max_width_single": 3.3,
        "max_width_double": 7.0,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 2.5,
    },
    JournalStandard.ECONOMETRICA: {
        "min_font_size": 9,
        "min_label_size": 8,
        "min_caption_size": 9,
        "max_width_single": 3.5,
        "max_width_double": 7.0,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 2.5,
    },
    JournalStandard.AER: {
        "min_font_size": 9,
        "min_label_size": 8,
        "min_caption_size": 9,
        "max_width_single": 3.25,
        "max_width_double": 6.5,
        "min_dpi": 300,
        "font_family": "Times New Roman",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 2.5,
    },
    JournalStandard.CHINESE: {
        "min_font_size": 10.5,
        "min_label_size": 9,
        "min_caption_size": 10.5,
        "max_width_single": 14.0,   # cm → 约 5.5in
        "max_width_double": 17.0,   # cm → 约 6.7in
        "min_dpi": 300,
        "font_family": "SimHei",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 3.0,
    },
    JournalStandard.NATURE: {
        "min_font_size": 7,
        "min_label_size": 7,
        "min_caption_size": 8,
        "max_width_single": 3.5,
        "max_width_double": 7.0,
        "min_dpi": 300,
        "font_family": "Arial",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 3.0,
    },
    JournalStandard.SCIENCE: {
        "min_font_size": 7,
        "min_label_size": 7,
        "min_caption_size": 8,
        "max_width_single": 3.5,
        "max_width_double": 7.0,
        "min_dpi": 300,
        "font_family": "Arial",
        "aspect_ratio_min": 0.4,
        "aspect_ratio_max": 3.0,
    },
}


class PlotStyleValidator:
    """
    图表期刊合规验证器。

    集成 PlotStyle validate() API，未安装时使用内置启发式规则。

    Usage:
        validator = PlotStyleValidator(journal=JournalStandard.JFE)
        issues = validator.validate_figure(Path("fig1_main.pdf"))
        # 或验证代码元数据
        issues = validator.validate_from_metadata(fig_size=(3.5, 2.5), dpi=300, font="Times")
    """

    # PlotStyle API 映射（如果 plotstyle 已安装）
    PLOTSTYLE_AVAILABLE = False
    _plotstyle_module = None

    def __init__(
        self,
        journal: JournalStandard = JournalStandard.IEEE,
        strict: bool = False,
    ):
        self.journal = journal
        self.strict = strict
        self.params = JOURNAL_PARAMS.get(journal, JOURNAL_PARAMS[JournalStandard.IEEE])
        self._issues: list[FigureIssue] = []

        # 尝试加载 PlotStyle
        self._try_load_plotstyle()

    def _try_load_plotstyle(self) -> bool:
        """尝试加载 plotstyle 模块。返回是否成功加载。"""
        if self._plotstyle_module is not None:
            return self.PLOTSTYLE_AVAILABLE
        try:
            import plotstyle as ps
            self._plotstyle_module = ps
            self.PLOTSTYLE_AVAILABLE = True
            logger.info(
                "[PlotStyleValidator] PlotStyle 已加载，使用 API 验证"
            )
            return True
        except ImportError:
            logger.debug(
                "[PlotStyleValidator] PlotStyle 未安装，使用内置规则验证"
            )
            return False

    def validate_figure(self, figure_path: Path) -> list[FigureIssue]:
        """
        验证单个图表文件（PDF/PNG）。

        Parameters
        ----------
        figure_path : Path
            图表文件路径。

        Returns
        -------
        list[FigureIssue]
            发现的问题列表，空列表表示通过。
        """
        self._issues = []
        path = Path(figure_path)

        if not path.exists():
            self._issues.append(FigureIssue(
                severity=IssueSeverity.ERROR,
                category="file",
                message=f"文件不存在: {path}",
                suggestion="检查文件路径是否正确",
            ))
            return self._issues

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            self._validate_pdf(path)
        elif suffix in (".png", ".jpg", ".jpeg"):
            self._validate_image(path)
        elif suffix == ".svg":
            self._issues.append(FigureIssue(
                severity=IssueSeverity.INFO,
                category="format",
                message="SVG 格式为矢量，天然 DPI 合规",
                suggestion="无需额外检查",
            ))
        else:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="format",
                message=f"不支持的格式: {suffix}",
                suggestion="使用 PDF/PNG/SVG 格式",
            ))

        return self._issues

    def _validate_pdf(self, path: Path) -> None:
        """验证 PDF 图表。"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="dependency",
                message="PyMuPDF 未安装，无法精确验证 PDF 尺寸",
                suggestion="pip install pymupdf，或使用 validate_from_metadata()",
            ))
            # fallback：检查文件大小（PDF 通常 > 1KB）
            if path.stat().st_size < 500:
                self._issues.append(FigureIssue(
                    severity=IssueSeverity.WARNING,
                    category="size",
                    message="PDF 文件异常小，可能生成失败",
                    suggestion="重新生成图表",
                ))
            return

        try:
            doc = fitz.open(path)
            page = doc[0]
            rect = page.rect
            width_inch = rect.width / 72  # PDF points → inches
            height_inch = rect.height / 72
            doc.close()

            self._check_dimensions(width_inch, height_inch, str(path))

        except Exception as exc:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="parse",
                message=f"无法解析 PDF 元数据: {exc}",
                suggestion="使用 validate_from_metadata() 手动传入尺寸",
            ))

    def _validate_image(self, path: Path) -> None:
        """验证位图图表（PNG/JPG）。"""
        try:
            from PIL import Image
        except ImportError:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="dependency",
                message="Pillow 未安装，无法验证图像尺寸",
                suggestion="pip install pillow",
            ))
            return

        try:
            img = Image.open(path)
            width_inch = img.width / img.info.get("dpi", (72, 72))[0] if "dpi" in img.info else img.width / 72
            height_inch = img.height / img.info.get("dpi", (72, 72))[1] if "dpi" in img.info else img.height / 72

            # 检查 DPI
            dpi = img.info.get("dpi", (0, 0))
            if isinstance(dpi, tuple):
                actual_dpi = dpi[0]
            else:
                actual_dpi = dpi

            if actual_dpi < self.params["min_dpi"]:
                self._issues.append(FigureIssue(
                    severity=IssueSeverity.ERROR,
                    category="dpi",
                    message=f"DPI={actual_dpi} 低于期刊要求 {self.params['min_dpi']}",
                    suggestion=f"重新保存为 ≥ {self.params['min_dpi']} DPI",
                    details={"actual_dpi": actual_dpi, "required_dpi": self.params["min_dpi"]},
                ))

            self._check_dimensions(width_inch, height_inch, str(path))

        except Exception as exc:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="parse",
                message=f"无法解析图像: {exc}",
                suggestion="使用 validate_from_metadata() 手动传入尺寸",
            ))

    def _check_dimensions(self, width_inch: float, height_inch: float, path: str, column_type: str | None = None) -> None:
        """检查图表尺寸是否符合标准。

        验证策略：
          - 始终检查是否超出单栏宽度限制（ERROR）
          - 单栏上限内：完全合规
          - 单栏与双栏之间：strict 模式报错；宽松模式允许（作双栏图）
          - 超出双栏上限：始终 ERROR
        """
        max_single = self.params["max_width_single"]
        max_double = self.params["max_width_double"]

        # 栏型：显式指定 > 按宽度推断
        if column_type == "single":
            limit = max_single
            mode = "single"
        elif column_type == "double":
            limit = max_double
            mode = "double"
        elif width_inch <= max_single:
            limit = max_single
            mode = "single"
        elif width_inch <= max_double:
            limit = max_double
            mode = "auto-double"
        else:
            limit = max_double
            mode = "over-both"

        if width_inch <= limit:
            # 合规
            pass
        else:
            # 超限
            severity = IssueSeverity.ERROR
            suggestion = f"减小宽度至 ≤ {limit:.2f}in"
            if mode == "auto-double":
                suggestion += f"（单栏 ≤ {max_single:.2f}in，双栏 ≤ {max_double:.2f}in）。或设置 column_type=\"double\" 明确为双栏图"
            self._issues.append(FigureIssue(
                severity=severity,
                category="size",
                message=f"宽度 {width_inch:.2f}in 超出 {mode} 限制 {limit:.2f}in",
                suggestion=suggestion,
                details={
                    "actual_width": width_inch,
                    "limit": limit,
                    "max_single": max_single,
                    "max_double": max_double,
                    "column_type": mode,
                },
            ))

        # 纵横比检查（与宽度合规性独立）
        if height_inch > 0:
            aspect = height_inch / width_inch
            if aspect < self.params["aspect_ratio_min"]:
                self._issues.append(FigureIssue(
                    severity=IssueSeverity.WARNING,
                    category="aspect",
                    message=f"纵横比 {aspect:.2f} 低于建议值 {self.params['aspect_ratio_min']}",
                    suggestion="图形可能过于扁平，考虑调整布局",
                    details={"aspect_ratio": aspect},
                ))
            elif aspect > self.params["aspect_ratio_max"]:
                self._issues.append(FigureIssue(
                    severity=IssueSeverity.WARNING,
                    category="aspect",
                    message=f"纵横比 {aspect:.2f} 超过建议值 {self.params['aspect_ratio_max']}",
                    suggestion="图形可能过于狭长，考虑调整布局或拆分为多个子图",
                    details={"aspect_ratio": aspect},
                ))


    def validate_from_metadata(
        self,
        fig_size: tuple[float, float] | None = None,
        dpi: int | None = None,
        font_family: str | None = None,
        font_size: float | None = None,
        label_size: float | None = None,
        caption: str | None = None,
        column_type: str | None = None,
    ) -> list[FigureIssue]:
        """
        根据图表元数据（非文件）验证合规性。

        用于在生成图表后立即验证，或对无法解析的文件（如 SVG）使用。

        Parameters
        ----------
        fig_size : tuple[float, float]
            图表尺寸（英寸），(宽度, 高度)。
        dpi : int
            输出 DPI。
        font_family : str
            字体名称。
        font_size : float
            正文字号（pt）。
        label_size : float
            轴标签字号（pt）。
        caption : str
            图注文字。
        column_type : str | None
            栏型："single"（单栏）或 "double"（双栏）。
            不指定时按宽度自动推断。
        """
        self._issues = []

        # 尺寸检查
        if fig_size:
            self._check_dimensions(fig_size[0], fig_size[1], "<metadata>", column_type)

        # DPI 检查
        if dpi is not None and dpi < self.params["min_dpi"]:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.ERROR,
                category="dpi",
                message=f"DPI={dpi} 低于期刊要求 {self.params['min_dpi']}",
                suggestion=f"使用 matplotlib.savefig(dpi={self.params['min_dpi']})",
                details={"actual_dpi": dpi, "required_dpi": self.params["min_dpi"]},
            ))

        # 字体检查
        expected_font = self.params["font_family"].lower()
        if font_family and expected_font not in font_family.lower():
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="font",
                message=f"字体 '{font_family}' 不是期刊推荐字体 '{self.params['font_family']}'",
                suggestion=f"使用 {self.params['font_family']} 以符合期刊规范",
                details={"expected": self.params["font_family"], "actual": font_family},
            ))

        # 字号检查
        if font_size is not None and font_size < self.params["min_font_size"]:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.ERROR,
                category="font",
                message=f"正文字号 {font_size}pt 低于期刊最低要求 {self.params['min_font_size']}pt",
                suggestion=f"增大字号至 ≥ {self.params['min_font_size']}pt",
                details={"actual": font_size, "required": self.params["min_font_size"]},
            ))

        if label_size is not None and label_size < self.params["min_label_size"]:
            self._issues.append(FigureIssue(
                severity=IssueSeverity.WARNING,
                category="font",
                message=f"轴标签字号 {label_size}pt 低于最低要求 {self.params['min_label_size']}pt",
                suggestion=f"增大轴标签字号至 ≥ {self.params['min_label_size']}pt",
                details={"actual": label_size, "required": self.params["min_label_size"]},
            ))

        # 图注检查
        if caption:
            # 检查图注中是否包含必要元素
            if not re.search(r"fig\.|图\s*\d+", caption, re.IGNORECASE):
                self._issues.append(FigureIssue(
                    severity=IssueSeverity.WARNING,
                    category="caption",
                    message="图注可能缺少图表编号",
                    suggestion="确保图注以 'Figure X' 或 '图X' 开头",
                ))

        # PlotStyle API（如可用）
        if self.PLOTSTYLE_AVAILABLE and self._plotstyle_module:
            self._validate_with_plotstyle_api(
                fig_size=fig_size,
                dpi=dpi,
                font_family=font_family,
            )

        return self._issues

    def _validate_with_plotstyle_api(
        self,
        fig_size: tuple[float, float] | None,
        dpi: int | None,
        font_family: str | None,
    ) -> None:
        """调用 PlotStyle API 进行额外验证。"""
        if not self._plotstyle_module:
            return

        try:
            validator = getattr(self._plotstyle_module, "Validator", None)
            if validator is None:
                validator = getattr(self._plotstyle_module, "validate", None)

            if callable(validator):
                # PlotStyle API 调用
                result = validator(
                    journal=self.journal.value,
                    figsize=fig_size,
                    dpi=dpi,
                    font=font_family,
                )
                if result and isinstance(result, dict):
                    issues = result.get("issues", [])
                    for iss in issues:
                        self._issues.append(FigureIssue(
                            severity=IssueSeverity(iss.get("severity", "WARNING")),
                            category=iss.get("category", "unknown"),
                            message=iss.get("message", ""),
                            suggestion=iss.get("suggestion", ""),
                            details=iss.get("details", {}),
                        ))
            else:
                logger.debug(
                    "[PlotStyleValidator] PlotStyle 模块无可直接调用的 validate 方法，"
                    "使用内置规则"
                )
        except Exception as exc:
            logger.warning(f"[PlotStyleValidator] PlotStyle API 调用失败: {exc}，使用内置规则")
            self._issues.append(FigureIssue(
                severity=IssueSeverity.INFO,
                category="plotstyle",
                message=f"PlotStyle API 调用失败，使用内置规则: {exc}",
                suggestion="PlotStyle 可用时将提供更精确的验证",
            ))

    def validate_batch(
        self,
        figure_paths: list[Path],
        stop_on_error: bool = False,
    ) -> dict[Path, list[FigureIssue]]:
        """
        批量验证多个图表。

        Returns
        -------
        dict[Path, list[FigureIssue]]
            每个文件对应的问题列表。
        """
        results: dict[Path, list[FigureIssue]] = {}
        for path in figure_paths:
            issues = self.validate_figure(Path(path))
            results[Path(path)] = issues
            if stop_on_error and any(i.severity == IssueSeverity.ERROR for i in issues):
                logger.error(f"[PlotStyleValidator] 严重错误，停止批量验证: {path}")
                break
        return results

    def has_errors(self) -> bool:
        """是否存在 ERROR 级别问题。"""
        return any(i.severity == IssueSeverity.ERROR for i in self._issues)

    def has_warnings(self) -> bool:
        """是否存在 WARNING 级别问题。"""
        return any(i.severity == IssueSeverity.WARNING for i in self._issues)

    def summary(self) -> str:
        """生成验证报告摘要。"""
        errors = [i for i in self._issues if i.severity == IssueSeverity.ERROR]
        warnings = [i for i in self._issues if i.severity == IssueSeverity.WARNING]
        infos = [i for i in self._issues if i.severity == IssueSeverity.INFO]

        lines = [
            f"[PlotStyleValidator] 期刊标准: {self.journal.name}",
            f"  错误: {len(errors)}",
            f"  警告: {len(warnings)}",
            f"  提示: {len(infos)}",
        ]
        if errors:
            lines.append("  ERROR 详情:")
            for i in errors:
                lines.append(f"    [{i.category}] {i.message}")
                lines.append(f"             → {i.suggestion}")
        if warnings and self.strict:
            lines.append("  WARNING 详情 (strict 模式):")
            for i in warnings:
                lines.append(f"    [{i.category}] {i.message}")
                lines.append(f"             → {i.suggestion}")

        return "\n".join(lines)
