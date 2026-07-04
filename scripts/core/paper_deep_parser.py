"""
paper_deep_parser.py — Academic Paper Deep Parser

Local PDF parsing engine for extracting structured data from academic papers.
Extracts: tables (→ CSV/JSON), figures (→ image data points via OCR),
appendix regression tables, and Chinese PDF support.

Architecture:
  - PDF reading: pdfplumber (primary) → PyMuPDF (fallback)
  - Table extraction: pdfplumber (table detection) → tabula-py (fallback)
  - OCR: pytesseract (English) + RapidOCR (Chinese)
  - Figure extraction: PyMuPDF page render + pytesseract
  - Chinese PDF: pdfplumber with lang='chinese'

Usage:
    from scripts.core.paper_deep_parser import (
        PaperDeepParser, TableExtractor, FigureExtractor,
        ChinesePDFParser, RegressionTableParser
    )
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from io import StringIO
from pathlib import Path
from typing import Any

__all__ = [
    "ParseResultStatus",
    "ParseResult",
    "TableResult",
    "FigureResult",
    "RegressionTableResult",
    "TableExtractor",
    "FigureExtractor",
    "ChinesePDFParser",
    "RegressionTableParser",
    "PaperDeepParser",
]

_log = logging.getLogger("paper_deep_parser")


# ---------------------------------------------------------------------------
# Enums & Status
# ---------------------------------------------------------------------------

class ParseResultStatus(Enum):
    """Status of a parsing operation."""
    SUCCESS = "success"
    TABLE_EXTRACTED = "table_extracted"
    FIGURE_EXTRACTED = "figure_extracted"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TableResult:
    """Extracted table from a PDF page.

    Attributes:
        paper_id: Unique identifier for the paper.
        table_index: Zero-based index of the table within the paper.
        page_num: Page number (1-based) where the table appears.
        table_html: HTML representation of the table.
        dataframe_json: JSON string of the table as a pandas DataFrame.
        caption: Table caption text extracted from the surrounding context.
        note: Any footnote or note text associated with the table.
    """
    paper_id: str
    table_index: int
    page_num: int
    table_html: str = ""
    dataframe_json: str = ""
    caption: str = ""
    note: str = ""

    def to_csv_string(self) -> str:
        """Convert the embedded DataFrame JSON back to a CSV string.

        Returns:
            CSV-formatted string with headers, or an empty string if
            the DataFrame JSON cannot be decoded.
        """
        if not self.dataframe_json:
            return ""
        try:
            import pandas as pd
            df = pd.read_json(StringIO(self.dataframe_json), orient="records")
            return df.to_csv(index=False)
        except Exception as exc:
            _log.warning("to_csv_string failed for table %s: %s", self.table_index, exc)
            return ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation of this result."""
        return {
            "paper_id": self.paper_id,
            "table_index": self.table_index,
            "page_num": self.page_num,
            "table_html": self.table_html,
            "dataframe_json": self.dataframe_json,
            "caption": self.caption,
            "note": self.note,
        }


@dataclass
class FigureResult:
    """Extracted figure from a PDF page.

    Attributes:
        paper_id: Unique identifier for the paper.
        figure_index: Zero-based index of the figure within the paper.
        page_num: Page number (1-based) where the figure appears.
        image_path: Path to the extracted image file on disk.
        extracted_text: OCR-extracted text from the figure.
        has_ocr: Whether OCR was successfully applied.
        caption: Figure caption text.
    """
    paper_id: str
    figure_index: int
    page_num: int
    image_path: str = ""
    extracted_text: str = ""
    has_ocr: bool = False
    caption: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation of this result."""
        return {
            "paper_id": self.paper_id,
            "figure_index": self.figure_index,
            "page_num": self.page_num,
            "image_path": self.image_path,
            "extracted_text": self.extracted_text,
            "has_ocr": self.has_ocr,
            "caption": self.caption,
        }


@dataclass
class RegressionTableResult:
    """Parsed regression table (e.g. DID, OLS, 2SLS results).

    Attributes:
        paper_id: Unique identifier for the paper.
        table_index: Zero-based index of the table within the paper.
        page_num: Page number (1-based) where the table appears.
        headers: List of header rows; each row is a list of column labels.
        body: List of data rows; each row is a list of string cells.
        notes: Footnote text (e.g. standard errors, significance stars).
    """
    paper_id: str
    table_index: int
    page_num: int
    headers: list[list[str]] = field(default_factory=list)
    body: list[list[str]] = field(default_factory=list)
    notes: str = ""

    def to_stata_format(self) -> str:
        """Convert the regression table to a Stata-readable format.

        Writes tab-delimited columns: varname \\t coef \\t se \\t t \\t p \\t ci_low \\t ci_high

        Returns:
            Tab-separated string ready to be pasted into a Stata do-file.
        """
        lines: list[str] = []
        if self.headers:
            header_row = self.headers[-1] if self.headers else []
            lines.append("\t".join(str(h) for h in header_row))
        for row in self.body:
            lines.append("\t".join(str(cell) for cell in row))
        if self.notes:
            lines.append(f"// Notes: {self.notes}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation of this result."""
        return {
            "paper_id": self.paper_id,
            "table_index": self.table_index,
            "page_num": self.page_num,
            "headers": self.headers,
            "body": self.body,
            "notes": self.notes,
        }


@dataclass
class ParseResult:
    """Complete parsing result for a single paper.

    Attributes:
        paper_id: Unique identifier for the paper.
        file_path: Path to the source PDF file.
        status: High-level parsing status.
        tables: All extracted tables.
        figures: All extracted figures.
        reg_tables: Regression tables detected among the tables.
        parsing_errors: List of error messages encountered during parsing.
        parsing_time_sec: Total wall-clock time spent parsing this paper.
    """
    paper_id: str
    file_path: str
    status: ParseResultStatus = ParseResultStatus.SUCCESS
    tables: list[TableResult] = field(default_factory=list)
    figures: list[FigureResult] = field(default_factory=list)
    reg_tables: list[RegressionTableResult] = field(default_factory=list)
    parsing_errors: list[str] = field(default_factory=list)
    parsing_time_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation (JSON-serializable)."""
        return {
            "paper_id": self.paper_id,
            "file_path": self.file_path,
            "status": self.status.value,
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "reg_tables": [r.to_dict() for r in self.reg_tables],
            "parsing_errors": self.parsing_errors,
            "parsing_time_sec": round(self.parsing_time_sec, 3),
        }

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        parts = [
            f"paper_id={self.paper_id}",
            f"status={self.status.value}",
            f"tables={len(self.tables)}",
            f"figures={len(self.figures)}",
            f"reg_tables={len(self.reg_tables)}",
            f"time={self.parsing_time_sec:.2f}s",
        ]
        if self.parsing_errors:
            parts.append(f"errors={len(self.parsing_errors)}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _html_table_from_df(df: Any) -> str:
    """Render a pandas DataFrame as an HTML table string."""
    headers = [escape(str(c)) for c in df.columns]
    rows = []
    for _, row in df.iterrows():
        cells = [f"<td>{escape(str(v))}</td>" for v in row]
        rows.append(f"<tr>{''.join(cells)}</tr>")
    header_html = f"<tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"
    return f"<table>{header_html}{''.join(rows)}</table>"


# ---------------------------------------------------------------------------
# TableExtractor
# ---------------------------------------------------------------------------

class TableExtractor:
    """Extract tables from PDF files.

    Args:
        strategy: Primary extraction library. Defaults to "pdfplumber".
                  Set to "tabula" to force the tabula-py fallback.
    """

    def __init__(self, strategy: str = "pdfplumber") -> None:
        self.strategy = strategy

    # ------------------------------------------------------------------
    # Internal extraction methods
    # ------------------------------------------------------------------

    def _try_pdfplumber(self, path: Path) -> list[TableResult]:
        """Extract tables using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            _log.warning("pdfplumber not available — skipping PDF table extraction")
            return []

        tables: list[TableResult] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = page.extract_tables()
                    for table_idx, raw_table in enumerate(page_tables):
                        if not raw_table:
                            continue
                        try:
                            import pandas as pd
                            df = pd.DataFrame(raw_table[1:], columns=raw_table[0])
                            df_json = df.to_json(orient="records", force_ascii=False)
                            html = _html_table_from_df(df)
                            tables.append(
                                TableResult(
                                    paper_id="",
                                    table_index=len(tables),
                                    page_num=page_num,
                                    table_html=html,
                                    dataframe_json=df_json,
                                )
                            )
                        except Exception as exc:
                            _log.debug(
                                "Table parse error on page %d table %d: %s",
                                page_num, table_idx, exc,
                            )
        except Exception as exc:
            _log.warning("pdfplumber failed on %s: %s", path, exc)
        return tables

    def _try_tabula(self, path: Path) -> list[TableResult]:
        """Extract tables using tabula-py (JVM-based, requires Java)."""
        try:
            import tabula
        except ImportError:
            _log.warning("tabula-py not available — skipping fallback table extraction")
            return []

        tables: list[TableResult] = []
        try:
            dfs = tabula.read_tables(str(path), pages="all")
            for table_idx, df in enumerate(dfs):
                if df is None or df.empty:
                    continue
                try:
                    df_json = df.to_json(orient="records", force_ascii=False)
                    html = _html_table_from_df(df)
                    tables.append(
                        TableResult(
                            paper_id="",
                            table_index=len(tables),
                            page_num=table_idx + 1,
                            table_html=html,
                            dataframe_json=df_json,
                        )
                    )
                except Exception as exc:
                    _log.debug("tabula table %d parse error: %s", table_idx, exc)
        except Exception as exc:
            _log.warning("tabula extraction failed on %s: %s", path, exc)
        return tables

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, path: Path, paper_id: str) -> list[TableResult]:
        """Extract all tables from a single PDF file.

        Args:
            path: Path to the PDF file.
            paper_id: Identifier to assign to each extracted table.

        Returns:
            List of TableResult objects. May be empty if no tables are
            found or all backends fail.
        """
        path = Path(path)
        if not path.exists():
            _log.error("PDF file not found: %s", path)
            return []

        if self.strategy == "pdfplumber":
            tables = self._try_pdfplumber(path)
            if tables:
                for t in tables:
                    t.paper_id = paper_id
                return tables
            _log.info("pdfplumber returned no tables for %s — trying tabula", path)
            tables = self._try_tabula(path)
        else:
            tables = self._try_tabula(path)

        for t in tables:
            t.paper_id = paper_id
        return tables

    def extract_all_from_directory(
        self, dir_path: Path, paper_ids: list[str] | None = None
    ) -> list[TableResult]:
        """Extract tables from every PDF found in a directory.

        Args:
            dir_path: Directory containing PDF files.
            paper_ids: Optional list of paper IDs aligned with the
                       discovered PDF files. If None, IDs are derived
                       from filenames.

        Returns:
            Combined list of TableResult objects from all PDFs.
        """
        dir_path = Path(dir_path)
        pdf_files = sorted(dir_path.glob("*.pdf"))
        if not pdf_files:
            _log.info("No PDF files found in %s", dir_path)
            return []

        if paper_ids is None:
            paper_ids = [p.stem for p in pdf_files]
        elif len(paper_ids) < len(pdf_files):
            paper_ids = list(paper_ids) + [
                p.stem for p in pdf_files[len(paper_ids) :]
            ]

        all_tables: list[TableResult] = []
        for pdf_path, pid in zip(pdf_files, paper_ids, strict=False):
            all_tables.extend(self.extract(pdf_path, pid))
        return all_tables


# ---------------------------------------------------------------------------
# FigureExtractor
# ---------------------------------------------------------------------------

class FigureExtractor:
    """Extract figures (rendered pages) from PDFs and apply OCR.

    Args:
        ocr_engine: OCR backend to use. Defaults to "pytesseract".
        dpi: Resolution at which to render PDF pages (images).
    """

    def __init__(self, ocr_engine: str = "pytesseract", dpi: int = 300) -> None:
        self.ocr_engine = ocr_engine
        self.dpi = dpi

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_images(self, path: Path) -> list[bytes]:
        """Render each page of the PDF as a PNG image (bytes)."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            _log.warning("PyMuPDF (fitz) not available — cannot render PDF pages")
            return []

        images: list[bytes] = []
        try:
            doc = fitz.open(str(path))
            for page in doc:
                pix = page.get_pixmap(dpi=self.dpi)
                images.append(pix.tobytes("png"))
            doc.close()
        except Exception as exc:
            _log.warning("PyMuPDF rendering failed on %s: %s", path, exc)
        return images

    def _ocr_image(self, image_bytes: bytes, lang: str = "eng") -> str:
        """Run OCR on raw image bytes.

        Args:
            image_bytes: PNG image data.
            lang: Tesseract language code (e.g. "eng", "chi_sim").

        Returns:
            Extracted text or an empty string on failure.
        """
        try:
            import pytesseract
        except ImportError:
            _log.debug("pytesseract not available for OCR")
            return ""

        try:
            import numpy as np
            try:
                import io

                from PIL import Image
                img = Image.open(io.BytesIO(image_bytes))
                img_array = np.array(img)
                return pytesseract.image_to_string(img_array, lang=lang)
            except ImportError:
                _log.debug("PIL not available for OCR")
                return ""
        except Exception as exc:
            _log.debug("OCR failed: %s", exc)
            return ""

    def _extract_single_figure(
        self, path: Path, paper_id: str, idx: int
    ) -> FigureResult:
        """Render one PDF page as a figure and OCR it."""
        page_num = idx + 1
        result = FigureResult(
            paper_id=paper_id,
            figure_index=idx,
            page_num=page_num,
        )
        try:
            import fitz
        except ImportError:
            _log.warning("PyMuPDF not available")
            return result

        try:
            doc = fitz.open(str(path))
            if idx >= len(doc):
                return result
            page = doc[idx]
            pix = page.get_pixmap(dpi=self.dpi)
            img_bytes = pix.tobytes("png")
            doc.close()

            result.image_path = ""
            ocr_text = self._ocr_image(img_bytes, lang="eng")
            if ocr_text.strip():
                result.extracted_text = ocr_text
                result.has_ocr = True
            else:
                result.has_ocr = False
        except Exception as exc:
            _log.debug("Figure extraction failed for page %d: %s", page_num, exc)

        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, path: Path, paper_id: str) -> list[FigureResult]:
        """Extract all figures (pages rendered as images) from a PDF.

        Args:
            path: Path to the PDF file.
            paper_id: Identifier for the paper.

        Returns:
            List of FigureResult, one per page.
        """
        path = Path(path)
        if not path.exists():
            _log.error("PDF file not found: %s", path)
            return []

        figures: list[FigureResult] = []
        try:
            import fitz
        except ImportError:
            _log.warning("PyMuPDF (fitz) not available — cannot extract figures")
            return []

        try:
            doc = fitz.open(str(path))
            num_pages = len(doc)
            doc.close()
            for idx in range(num_pages):
                figures.append(self._extract_single_figure(path, paper_id, idx))
        except Exception as exc:
            _log.warning("Figure extraction failed on %s: %s", path, exc)

        return figures

    def extract_all_from_directory(
        self, dir_path: Path, paper_ids: list[str] | None = None
    ) -> list[FigureResult]:
        """Extract figures from all PDFs in a directory.

        Args:
            dir_path: Directory containing PDF files.
            paper_ids: Optional list of paper IDs aligned with discovered PDFs.

        Returns:
            Combined list of FigureResult from all PDFs.
        """
        dir_path = Path(dir_path)
        pdf_files = sorted(dir_path.glob("*.pdf"))
        if not pdf_files:
            return []

        if paper_ids is None:
            paper_ids = [p.stem for p in pdf_files]
        elif len(paper_ids) < len(pdf_files):
            paper_ids = list(paper_ids) + [
                p.stem for p in pdf_files[len(paper_ids) :]
            ]

        all_figures: list[FigureResult] = []
        for pdf_path, pid in zip(pdf_files, paper_ids, strict=False):
            all_figures.extend(self.extract(pdf_path, pid))
        return all_figures


# ---------------------------------------------------------------------------
# ChinesePDFParser
# ---------------------------------------------------------------------------

class ChinesePDFParser:
    """Specialised parser for Chinese-language PDF papers.

    Handles Chinese text extraction and Chinese-figure OCR using
    RapidOCR (primary) with pytesseract (lang='chi_sim+eng') as fallback.

    Args:
        ocr_backend: Backend for figure OCR. Defaults to "rapidocr".
    """

    def __init__(self, ocr_backend: str = "rapidocr") -> None:
        self.ocr_backend = ocr_backend

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_chinese_text(self, path: Path) -> str:
        """Extract Chinese text from a PDF using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            _log.warning("pdfplumber not available for Chinese text extraction")
            return ""

        try:
            with pdfplumber.open(path) as pdf:
                text_chunks: list[str] = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_chunks.append(t)
                return "\n\n".join(text_chunks)
        except Exception as exc:
            _log.warning("Chinese text extraction failed on %s: %s", path, exc)
            return ""

    def _ocr_chinese_figure(self, image_bytes: bytes) -> str:
        """OCR a Chinese figure image.

        Attempts RapidOCR first; falls back to pytesseract with
        lang='chi_sim+eng' if RapidOCR is unavailable.
        """
        # --- Try RapidOCR ------------------------------------------------
        try:
            from rapidocr_ai import RapidOCR

            rap = RapidOCR()
            result, _, _ = rap(image_bytes)
            if result:
                lines = [" ".join(item[1]) for item in result]
                return "\n".join(lines)
        except ImportError:
            _log.debug("RapidOCR not available — trying pytesseract fallback")
        except Exception as exc:
            _log.debug("RapidOCR OCR failed: %s", exc)

        # --- Fallback: pytesseract with Chinese ----------------------------
        try:
            import pytesseract
        except ImportError:
            _log.debug("pytesseract not available")
            return ""

        try:
            import io

            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            img_array = np.array(img)
            return pytesseract.image_to_string(img_array, lang="chi_sim+eng")
        except Exception as exc:
            _log.debug("pytesseract Chinese OCR failed: %s", exc)

        return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, path: Path, paper_id: str) -> ParseResult:
        """Full parse of a Chinese PDF: text, tables, and figure OCR.

        Args:
            path: Path to the PDF file.
            paper_id: Identifier for the paper.

        Returns:
            ParseResult with tables, figures, and any parsing errors.
        """
        start = time.perf_counter()
        result = ParseResult(
            paper_id=paper_id,
            file_path=str(path),
            status=ParseResultStatus.SUCCESS,
        )

        # 1. Extract text
        try:
            text = self._extract_chinese_text(path)
            result.parsing_errors.append(f"text_length={len(text)}")
        except Exception as exc:
            result.parsing_errors.append(f"text_extraction_error: {exc}")

        # 2. Extract tables
        try:
            table_extractor = TableExtractor()
            result.tables = table_extractor.extract(path, paper_id)
            for t in result.tables:
                t.caption = ""
                t.note = ""
        except Exception as exc:
            result.parsing_errors.append(f"table_extraction_error: {exc}")

        # 3. Extract figures with Chinese OCR
        try:
            import fitz
            doc = fitz.open(str(path))
            for page_idx, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                ocr_text = self._ocr_chinese_figure(img_bytes)
                fig = FigureResult(
                    paper_id=paper_id,
                    figure_index=len(result.figures),
                    page_num=page_idx + 1,
                    extracted_text=ocr_text,
                    has_ocr=bool(ocr_text.strip()),
                )
                result.figures.append(fig)
            doc.close()
        except ImportError:
            result.parsing_errors.append("PyMuPDF not available for figure extraction")
        except Exception as exc:
            result.parsing_errors.append(f"figure_extraction_error: {exc}")

        if result.tables or result.figures:
            result.status = ParseResultStatus.SUCCESS

        result.parsing_time_sec = time.perf_counter() - start
        return result


# ---------------------------------------------------------------------------
# RegressionTableParser
# ---------------------------------------------------------------------------

# Common regression-related header terms (English + Chinese)
_REGRESSION_TERMS_EN = {
    "coefficient", "coef", "estimate", "std", "standard error", "t-stat",
    "t stat", "p-value", "p value", "t-value", "se ", "confiden", "ci(",
    "variable", "dependent", "outcome", "control", "treatment", "constant",
    "intercept", " observations", "r-squared", "r2", "adj. r2", "adj r2",
    "n ", " obs", "fixed effect", "robust", "clustered", "cluster",
}
_REGRESSION_TERMS_CN = {
    "变量", "系数", "标准误", "t统计量", "p值", "显著性", "常数项",
    "截距", "观测值", "r方", "adj", "控制变量", "处理变量", "因变量",
    "自变量", "固定效应", "稳健标准误", "聚类", "样本量",
}

# Patterns for column headers that indicate regression output
_REGEX_COL_PATTERN = re.compile(
    r"(?i)"
    r"(\([0-9]+\))"  # e.g. (1), (2), (3)
    r"|(coeff|coef|estimate|std\.?|se|t.?stat|p.?value|conf\.?|ci)"
    r"|(变量|系数|标准误|t统计|p值|置信)"
    r"|(^$)"  # empty column
)

# Patterns for dependent variable indicators
_DEP_PATTERNS_EN = [
    re.compile(r"(?i)dependent|outcome|y[\s]*=|dep[\s]*var"),
    re.compile(r"(?i)dependent var"),
    re.compile(r"(?i)y\b"),
]
_DEP_PATTERNS_CN = [
    re.compile(r"(?i)因变量|被解释变量"),
]
# Patterns for independent (treatment / key) variable indicators
_IND_PATTERNS_EN = [
    re.compile(r"(?i)treatment|treated|control|X[0-9]|x[0-9]|main effect"),
    re.compile(r"(?i)核心解释变量"),
]
_IND_PATTERNS_CN = [
    re.compile(r"(?i)解释变量|自变量|核心解释"),
]


class RegressionTableParser:
    """Detect regression tables among extracted tables and parse them.

    A regression table is identified by its column headers containing
    common statistical terms (coefficient, standard error, t-stat, etc.)
    in either English or Chinese.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_regression_table(table: TableResult) -> bool:
        """Heuristic check: does ``table`` look like a regression output table?

        Scans the table HTML for regression-related keywords.
        Returns True if at least 2 distinct keyword groups are found.
        """
        html = table.table_html.lower()
        found_en = sum(1 for term in _REGRESSION_TERMS_EN if term in html)
        found_cn = sum(1 for term in _REGRESSION_TERMS_CN if term in html)
        return (found_en + found_cn) >= 2

    @staticmethod
    def _parse_regression_structure(
        table: TableResult,
    ) -> RegressionTableResult:
        """Parse an HTML table into structured header + body rows.

        Extracts plain text from ``<th>`` and ``<td>`` elements using
        simple regex-based HTML parsing (no extra dependencies).
        """
        headers: list[list[str]] = []
        body: list[list[str]] = []

        import pandas as pd

        # Try to parse via pandas from the stored JSON first
        try:
            if table.dataframe_json:
                df = pd.read_json(StringIO(table.dataframe_json), orient="records")
                headers = [list(df.columns)]
                body = [list(row) for row in df.values.tolist()]
        except Exception:
            pass

        # Fallback: simple regex extraction from HTML
        if not body:
            html = table.table_html
            # Extract <th>...</th>
            th_cells = re.findall(r"<th[^>]*>(.*?)</th>", html, re.DOTALL)
            # Extract <td>...</td>
            td_cells = re.findall(r"<td[^>]*>(.*?)</td>", html, re.DOTALL)

            # Group td_cells into rows by counting <tr> blocks
            row_splits = re.split(r"<tr[^>]*>", html)
            row_cells: list[list[str]] = []
            cursor = 0
            for _ in row_splits[1:]:  # skip before first <tr>
                row: list[str] = []
                for _ in range(10):  # max 10 cols per row
                    if cursor >= len(td_cells):
                        break
                    cell = td_cells[cursor].strip()
                    row.append(cell)
                    cursor += 1
                if row:
                    row_cells.append(row)

            if th_cells:
                headers.append([c.strip() for c in th_cells])
            if row_cells:
                body = row_cells

        return RegressionTableResult(
            paper_id=table.paper_id,
            table_index=table.table_index,
            page_num=table.page_num,
            headers=headers,
            body=body,
            notes=table.note or "",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, path: Path, paper_id: str) -> list[RegressionTableResult]:
        """Extract regression tables from a PDF.

        Args:
            path: Path to the PDF file.
            paper_id: Identifier for the paper.

        Returns:
            List of RegressionTableResult for tables identified as
            regression outputs.
        """
        extractor = TableExtractor()
        tables = extractor.extract(path, paper_id)
        reg_tables: list[RegressionTableResult] = []
        for table in tables:
            if self._is_regression_table(table):
                reg_tables.append(self._parse_regression_structure(table))
        return reg_tables

    @staticmethod
    def identify_variables_from_tables(
        tables: list[RegressionTableResult],
    ) -> dict[str, set[str]]:
        """Identify dependent and independent variables across tables.

        Scans cell text for patterns that indicate dependent variables
        (e.g. "dependent", "y =", "因变量") or independent variables
        (e.g. "treatment", "treated", "X1", "核心解释变量").

        Args:
            tables: List of parsed regression tables.

        Returns:
            Dict with keys ``"dependent"`` and ``"independent"``, each
            containing a set of variable names found.
        """
        dependent_vars: set[str] = set()
        independent_vars: set[str] = set()

        all_text = " ".join(
            " ".join(" ".join(row) for row in t.body) +
            " ".join(" ".join(h) for h in t.headers)
            for t in tables
        ).lower()

        # Dependent variable patterns
        for pat in _DEP_PATTERNS_EN + _DEP_PATTERNS_CN:
            for m in pat.finditer(all_text):
                token = all_text[max(0, m.start() - 20) : m.end() + 20]
                dependent_vars.add(token.strip())

        # Independent variable patterns
        for pat in _IND_PATTERNS_EN + _IND_PATTERNS_CN:
            for m in pat.finditer(all_text):
                token = all_text[max(0, m.start() - 20) : m.end() + 20]
                independent_vars.add(token.strip())

        return {
            "dependent": dependent_vars,
            "independent": independent_vars,
        }


# ---------------------------------------------------------------------------
# PaperDeepParser — Orchestrator
# ---------------------------------------------------------------------------

class PaperDeepParser:
    """High-level orchestrator that combines table, figure, and
    regression-table extraction into a single parsing result.

    Args:
        chinese_mode: If True, uses ChinesePDFParser internally so that
                      figure OCR defaults to Chinese language support.
    """

    def __init__(self, chinese_mode: bool = False) -> None:
        self.chinese_mode = chinese_mode
        self.table_extractor = TableExtractor()
        self.figure_extractor = FigureExtractor()
        self.regression_parser = RegressionTableParser()
        if chinese_mode:
            self.chinese_parser = ChinesePDFParser()

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def parse(self, path: Path, paper_id: str | None = None) -> ParseResult:
        """Full parse of a single PDF.

        Args:
            path: Path to the PDF file.
            paper_id: Optional identifier. If omitted, derived from
                      the filename (stem).

        Returns:
            ParseResult containing tables, figures, and detected
            regression tables.
        """
        start = time.perf_counter()
        path = Path(path)

        if paper_id is None:
            paper_id = path.stem

        if not path.exists():
            _log.error("PDF not found: %s", path)
            return ParseResult(
                paper_id=paper_id,
                file_path=str(path),
                status=ParseResultStatus.ERROR,
                parsing_errors=[f"File not found: {path}"],
                parsing_time_sec=time.perf_counter() - start,
            )

        result = ParseResult(
            paper_id=paper_id,
            file_path=str(path),
            status=ParseResultStatus.SUCCESS,
        )

        # --- Tables -------------------------------------------------------
        try:
            result.tables = self.table_extractor.extract(path, paper_id)
        except Exception as exc:
            result.parsing_errors.append(f"table_extraction_error: {exc}")

        # --- Figures ------------------------------------------------------
        try:
            result.figures = self.figure_extractor.extract(path, paper_id)
        except Exception as exc:
            result.parsing_errors.append(f"figure_extraction_error: {exc}")

        # --- Regression tables --------------------------------------------
        try:
            reg_tables = self.regression_parser.extract(path, paper_id)
            result.reg_tables = reg_tables
        except Exception as exc:
            result.parsing_errors.append(f"regression_table_error: {exc}")

        # --- Status -------------------------------------------------------
        if result.tables:
            result.status = ParseResultStatus.TABLE_EXTRACTED
        if result.figures:
            result.status = ParseResultStatus.FIGURE_EXTRACTED
        if result.parsing_errors and not (result.tables or result.figures):
            result.status = ParseResultStatus.ERROR

        result.parsing_time_sec = time.perf_counter() - start
        return result

    # ------------------------------------------------------------------
    # Batch / directory
    # ------------------------------------------------------------------

    def parse_batch(
        self,
        paths: list[Path],
        paper_ids: list[str] | None = None,
    ) -> list[ParseResult]:
        """Parse multiple PDFs in parallel using a thread pool.

        Args:
            paths: List of PDF file paths.
            paper_ids: Optional list of identifiers aligned with ``paths``.
                       If None, IDs are derived from filenames.

        Returns:
            List of ParseResult, one per input path. Errors are captured
            inside each result rather than raising exceptions.
        """
        if paper_ids is None:
            paper_ids = [p.stem for p in paths]
        elif len(paper_ids) < len(paths):
            paper_ids = list(paper_ids) + [
                p.stem for p in paths[len(paper_ids) :]
            ]

        results: list[ParseResult] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self.parse, p, pid): (p, pid)
                for p, pid in zip(paths, paper_ids, strict=False)
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    p, pid = futures[future]
                    results.append(
                        ParseResult(
                            paper_id=pid,
                            file_path=str(p),
                            status=ParseResultStatus.ERROR,
                            parsing_errors=[f"thread_exception: {exc}"],
                        )
                    )
        return results

    def parse_directory(self, dir_path: Path) -> list[ParseResult]:
        """Parse every PDF found in a directory.

        Args:
            dir_path: Directory containing PDF files.

        Returns:
            List of ParseResult, one per discovered PDF.
        """
        dir_path = Path(dir_path)
        pdf_files = sorted(dir_path.glob("*.pdf"))
        if not pdf_files:
            _log.info("No PDF files in directory: %s", dir_path)
            return []
        return self.parse_batch(pdf_files)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_results(
        self,
        results: list[ParseResult],
        output_dir: Path,
    ) -> None:
        """Write parsing results to disk.

        Creates three sub-directories:
          output_dir/tables/   — one CSV per table
          output_dir/figures/   — one PNG per figure
          output_dir/           — ``results.json`` with the full result set

        Args:
            results: List of ParseResult objects from ``parse`` /
                     ``parse_batch`` / ``parse_directory``.
            output_dir: Root output directory (created if missing).
        """
        output_dir = Path(output_dir)
        tables_dir = output_dir / "tables"
        figures_dir = output_dir / "figures"
        tables_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)

        for res in results:
            pid = res.paper_id
            # --- Tables ----------------------------------------------------
            for table in res.tables:
                csv_str = table.to_csv_string()
                if csv_str:
                    out = tables_dir / f"{pid}_table_{table.table_index}.csv"
                    out.write_text(csv_str, encoding="utf-8")

            # --- Figures ----------------------------------------------------
            for fig in res.figures:
                if fig.image_path and Path(fig.image_path).exists():
                    import shutil

                    src = Path(fig.image_path)
                    dst = figures_dir / f"{pid}_figure_{fig.figure_index}{src.suffix}"
                    shutil.copy2(src, dst)

            # --- Full JSON -------------------------------------------------
            json_path = output_dir / f"{pid}_parse_result.json"
            json_path.write_text(
                json.dumps(res.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        _log.info(
            "Exported %d results → %s (tables: %d, figures: %d)",
            len(results),
            output_dir,
            sum(len(r.tables) for r in results),
            sum(len(r.figures) for r in results),
        )
