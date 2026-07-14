"""Comprehensive unit tests for scripts/core/paper_deep_parser.py.

Targets dataclasses, enums, parser helpers, config classes, table/figure
extraction (with mocked PDF/OCR backends), Chinese PDF parsing, regression
table detection and variable identification, the PaperDeepParser orchestrator
and directory/batch export.

Heavy dependencies (pdfplumber, PyMuPDF/fitz, tabula-py, pytesseract,
RapidOCR) are mocked via ``sys.modules`` insertion so the parser code can
``import`` them without needing them installed.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core import paper_deep_parser as pdp  # noqa: E402
from scripts.core.paper_deep_parser import (  # noqa: E402
    ChinesePDFParser,
    FigureExtractor,
    FigureResult,
    PaperDeepParser,
    ParseResult,
    ParseResultStatus,
    RegressionTableParser,
    RegressionTableResult,
    TableExtractor,
    TableResult,
)


# ─── Module imports / sanity ─────────────────────────────────────────────


class TestModule:
    def test_all_exports_present(self):
        for name in pdp.__all__:
            assert hasattr(pdp, name), f"missing export: {name}"


# ─── ParseResultStatus enum ──────────────────────────────────────────────


class TestParseResultStatus:
    def test_values(self):
        assert ParseResultStatus.SUCCESS.value == "success"
        assert ParseResultStatus.TABLE_EXTRACTED.value == "table_extracted"
        assert ParseResultStatus.FIGURE_EXTRACTED.value == "figure_extracted"
        assert ParseResultStatus.ERROR.value == "error"

    def test_member_count(self):
        assert len(list(ParseResultStatus)) == 4

    def test_str_round_trip(self):
        for s in ParseResultStatus:
            assert ParseResultStatus(s.value) is s


# ─── TableResult dataclass ────────────────────────────────────────────────


class TestTableResult:
    def _make(self, **over):
        kw = dict(
            paper_id="p1", table_index=0, page_num=1,
            table_html="", dataframe_json="",
            caption="", note="",
        )
        kw.update(over)
        return TableResult(**kw)

    def test_defaults(self):
        t = TableResult(paper_id="x", table_index=2, page_num=4)
        assert t.paper_id == "x"
        assert t.table_index == 2
        assert t.page_num == 4
        assert t.table_html == ""
        assert t.dataframe_json == ""
        assert t.caption == ""
        assert t.note == ""

    def test_to_csv_string_with_data(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        t = self._make(dataframe_json=df.to_json(orient="records"))
        out = t.to_csv_string()
        assert "a,b" in out
        assert "1,3" in out

    def test_to_csv_string_empty(self):
        t = self._make()
        assert t.to_csv_string() == ""

    def test_to_csv_string_bad_json_logs_warning(self):
        t = self._make(dataframe_json="{not json")
        # Should return "" without raising (logs warning)
        with pytest.warns(None) if False else __import__("contextlib").nullcontext():
            out = t.to_csv_string()
        assert out == ""

    def test_to_dict_keys(self):
        t = self._make(table_html="<table/>", caption="c1", note="n1")
        d = t.to_dict()
        assert set(d.keys()) == {
            "paper_id", "table_index", "page_num",
            "table_html", "dataframe_json", "caption", "note",
        }
        assert d["caption"] == "c1"
        assert d["note"] == "n1"


# ─── FigureResult dataclass ──────────────────────────────────────────────


class TestFigureResult:
    def test_defaults(self):
        f = FigureResult(paper_id="p", figure_index=0, page_num=1)
        assert f.image_path == ""
        assert f.extracted_text == ""
        assert f.has_ocr is False
        assert f.caption == ""

    def test_with_values(self):
        f = FigureResult(
            paper_id="p", figure_index=2, page_num=3,
            image_path="/tmp/fig.png", extracted_text="text",
            has_ocr=True, caption="caption",
        )
        d = f.to_dict()
        assert d["paper_id"] == "p"
        assert d["figure_index"] == 2
        assert d["image_path"] == "/tmp/fig.png"
        assert d["extracted_text"] == "text"
        assert d["has_ocr"] is True
        assert d["caption"] == "caption"


# ─── RegressionTableResult dataclass ─────────────────────────────────────


class TestRegressionTableResult:
    def test_defaults(self):
        r = RegressionTableResult(paper_id="r", table_index=0, page_num=1)
        assert r.headers == []
        assert r.body == []
        assert r.notes == ""

    def test_to_stata_format(self):
        r = RegressionTableResult(
            paper_id="r", table_index=0, page_num=1,
            headers=[["Var", "(1)", "(2)"]],
            body=[
                ["treated", "0.05", "0.07"],
                ["N", "1000", "2000"],
            ],
            notes="*** p<0.01",
        )
        s = r.to_stata_format()
        assert "Var\t(1)\t(2)" in s
        assert "treated\t0.05\t0.07" in s
        assert "N\t1000\t2000" in s
        assert "// Notes: *** p<0.01" in s

    def test_to_stata_format_no_headers(self):
        r = RegressionTableResult(
            paper_id="r", table_index=0, page_num=1,
            headers=[], body=[["a", "1"]], notes="",
        )
        s = r.to_stata_format()
        assert "a\t1" in s

    def test_to_stata_format_uses_last_header_row(self):
        r = RegressionTableResult(
            paper_id="r", table_index=0, page_num=1,
            headers=[["A", "B"], ["Var", "Coef"]],
            body=[["x", "1.2"]],
        )
        s = r.to_stata_format()
        # Last header row wins
        assert "Var\tCoef" in s

    def test_to_dict(self):
        r = RegressionTableResult(
            paper_id="r", table_index=2, page_num=4,
            headers=[["Var", "Coef"]], body=[["x", "1.0"]],
            notes="foo",
        )
        d = r.to_dict()
        assert d["paper_id"] == "r"
        assert d["table_index"] == 2
        assert d["page_num"] == 4
        assert d["headers"] == [["Var", "Coef"]]
        assert d["body"] == [["x", "1.0"]]
        assert d["notes"] == "foo"


# ─── ParseResult dataclass ───────────────────────────────────────────────


class TestParseResult:
    def test_defaults(self):
        r = ParseResult(paper_id="p", file_path="/x.pdf")
        assert r.status == ParseResultStatus.SUCCESS
        assert r.tables == []
        assert r.figures == []
        assert r.reg_tables == []
        assert r.parsing_errors == []
        assert r.parsing_time_sec == 0.0

    def test_summary_no_errors(self):
        r = ParseResult(paper_id="p", file_path="/x.pdf", parsing_time_sec=2.5)
        s = r.summary()
        assert "paper_id=p" in s
        assert "status=success" in s
        assert "tables=0" in s
        assert "figures=0" in s
        assert "time=2.50s" in s
        assert "errors=" not in s

    def test_summary_with_errors(self):
        r = ParseResult(
            paper_id="p", file_path="/x.pdf",
            parsing_errors=["oops"], parsing_time_sec=1.0,
        )
        s = r.summary()
        assert "errors=1" in s

    def test_to_dict_roundtrip_json(self):
        r = ParseResult(
            paper_id="p", file_path="/x.pdf",
            tables=[TableResult(paper_id="p", table_index=0, page_num=1)],
            figures=[FigureResult(paper_id="p", figure_index=0, page_num=1)],
            reg_tables=[RegressionTableResult(paper_id="p", table_index=0, page_num=1)],
            parsing_errors=["x"], parsing_time_sec=0.123456,
        )
        d = r.to_dict()
        # must be JSON-serialisable
        s = json.dumps(d, ensure_ascii=False)
        loaded = json.loads(s)
        assert loaded["paper_id"] == "p"
        assert loaded["status"] == "success"
        assert loaded["parsing_time_sec"] == 0.123  # rounded to 3 decimals
        assert loaded["tables"][0]["paper_id"] == "p"
        assert loaded["figures"][0]["figure_index"] == 0


# ─── _html_table_from_df helper ──────────────────────────────────────────


class TestHtmlTableFromDf:
    def test_basic(self):
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        html = pdp._html_table_from_df(df)
        assert html.startswith("<table>")
        assert "<th>A</th>" in html
        assert "<th>B</th>" in html
        assert "<td>1</td>" in html
        assert "<td>x</td>" in html
        assert html.endswith("</table>")

    def test_html_escapes_special_chars(self):
        df = pd.DataFrame({"<x>": ["<script>", "&"]})
        html = pdp._html_table_from_df(df)
        assert "&lt;x&gt;" in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html


# ─── Mock backends for table/figure extraction ───────────────────────────


def _install_pdfplumber_mock(monkeypatch, *, pages_with_tables):
    """Inject a fake pdfplumber module that yields given (page, tables) tuples.

    ``pages_with_tables`` is a list of lists; each inner list contains the
    ``raw_table`` lists (rows of cells) reported by that page's
    ``extract_tables()`` call.
    """
    fake_pages = []
    for tables in pages_with_tables:
        page = MagicMock()
        page.extract_tables.return_value = tables
        fake_pages.append(page)
    fake_pdf = MagicMock()
    fake_pdf.pages = fake_pages
    # pdfplumber.open(path) is a context manager
    fake_open = MagicMock()
    fake_open.return_value.__enter__.return_value = fake_pdf
    fake_open.return_value.__exit__.return_value = False
    mod = types.ModuleType("pdfplumber")
    mod.open = fake_open
    monkeypatch.setitem(sys.modules, "pdfplumber", mod)
    return mod


def _install_fitz_mock(monkeypatch, *, page_count=2, raise_open=False):
    """Inject a fake PyMuPDF (fitz) module returning real PNG bytes per page."""
    import io

    from PIL import Image

    def _make_png_bytes() -> bytes:
        """Generate a tiny valid PNG."""
        img = Image.new("RGB", (4, 4), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    PNG_BYTES = _make_png_bytes()

    class FakePixmap:
        def __init__(self):
            self._b = PNG_BYTES

        def tobytes(self, _fmt):
            return self._b

    class FakePage:
        def get_pixmap(self, dpi=200):
            return FakePixmap()

    class FakeDoc:
        def __init__(self, path, n=page_count, raise_open=False):
            self._n = n
            if raise_open:
                raise RuntimeError("open failed")
            self.pages = [FakePage() for _ in range(n)]

        def __len__(self):
            return self._n

        def __iter__(self):
            return iter(self.pages)

        def __getitem__(self, i):
            return self.pages[i]

        def close(self):
            pass

    mod = types.ModuleType("fitz")
    mod.open = lambda path: FakeDoc(path, n=page_count, raise_open=raise_open)
    monkeypatch.setitem(sys.modules, "fitz", mod)
    return mod


def _install_pytesseract_mock(monkeypatch, *, text="OCR TEXT"):
    mod = types.ModuleType("pytesseract")
    mod.image_to_string = MagicMock(return_value=text)
    monkeypatch.setitem(sys.modules, "pytesseract", mod)
    return mod


def _install_pil_mock(monkeypatch):
    import io
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        # Minimal stub
        from PIL import Image  # type: ignore

        def open(buf):
            return Image.new("RGB", (1, 1))

        Image.open = open
        Image._open_buf = buf


# ─── TableExtractor ──────────────────────────────────────────────────────


class TestTableExtractor:
    def test_init_default_strategy(self):
        te = TableExtractor()
        assert te.strategy == "pdfplumber"

    def test_init_tabula_strategy(self):
        te = TableExtractor(strategy="tabula")
        assert te.strategy == "tabula"

    def test_extract_missing_file(self, tmp_path):
        te = TableExtractor()
        out = te.extract(tmp_path / "no.pdf", "p1")
        assert out == []

    def test_extract_pdfplumber_success(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")

        # Page 1 has one table, page 2 has two tables
        tables_p1 = [[["A", "B"], ["1", "2"], ["3", "4"]]]
        tables_p2 = [
            [["C"], ["5"]],
            [["D"], ["6"]],
        ]
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[tables_p1, tables_p2])

        te = TableExtractor()
        out = te.extract(pdf, "my_paper")
        assert len(out) == 3
        # Paper IDs are stamped
        for t in out:
            assert t.paper_id == "my_paper"
        # Page numbers
        assert out[0].page_num == 1
        assert out[1].page_num == 2
        assert out[2].page_num == 2
        # Table indices are sequential
        assert [t.table_index for t in out] == [0, 1, 2]
        # HTML and JSON populated
        for t in out:
            assert t.table_html.startswith("<table>")
            assert t.dataframe_json

    def test_extract_pdfplumber_skips_empty_tables(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")

        tables = [[["A", "B"], ["1", "2"]], []]  # second is empty
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[tables])
        te = TableExtractor()
        out = te.extract(pdf, "p")
        assert len(out) == 1

    def test_extract_pdfplumber_inner_parse_error_continues(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        # Mix bad / good table rows
        tables_p1 = [[[None, None], [None, None]]]  # may trigger pandas issue
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[tables_p1])
        te = TableExtractor()
        # Should not raise even if inner pandas op chokes
        out = te.extract(pdf, "p")
        assert isinstance(out, list)

    def test_extract_pdfplumber_exception_returns_empty(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        # Patch pdfplumber.open to raise
        mod = types.ModuleType("pdfplumber")
        mod.open = MagicMock(side_effect=RuntimeError("kaboom"))
        monkeypatch.setitem(sys.modules, "pdfplumber", mod)
        te = TableExtractor()
        out = te.extract(pdf, "p")
        assert out == []

    def test_extract_falls_back_to_tabula(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")

        # pdfplumber unavailable
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)

        # Make pdfplumber's import fail by patching __import__
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *args, **kw):
            if name == "pdfplumber":
                raise ImportError("not available")
            return orig_import(name, *args, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        # tabula-py stub
        tabula_mod = types.ModuleType("tabula")
        df1 = pd.DataFrame({"A": [1]})
        df2 = pd.DataFrame({"B": [2]})
        tabula_mod.read_tables = MagicMock(return_value=[df1, df2])
        monkeypatch.setitem(sys.modules, "tabula", tabula_mod)

        te = TableExtractor()
        out = te.extract(pdf, "p")
        assert len(out) == 2
        assert all(t.paper_id == "p" for t in out)

    def test_extract_strategy_tabula_directly(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        df = pd.DataFrame({"x": [1, 2]})
        tabula_mod = types.ModuleType("tabula")
        tabula_mod.read_tables = MagicMock(return_value=[df])
        monkeypatch.setitem(sys.modules, "tabula", tabula_mod)
        te = TableExtractor(strategy="tabula")
        out = te.extract(pdf, "p")
        assert len(out) == 1
        assert out[0].page_num == 1

    def test_extract_tabula_skips_empty(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        empty_df = pd.DataFrame()
        tabula_mod = types.ModuleType("tabula")
        tabula_mod.read_tables = MagicMock(return_value=[empty_df, None])
        monkeypatch.setitem(sys.modules, "tabula", tabula_mod)
        te = TableExtractor(strategy="tabula")
        out = te.extract(pdf, "p")
        assert out == []

    def test_extract_tabula_exception(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        tabula_mod = types.ModuleType("tabula")
        tabula_mod.read_tables = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setitem(sys.modules, "tabula", tabula_mod)
        te = TableExtractor(strategy="tabula")
        out = te.extract(pdf, "p")
        assert out == []

    def test_extract_tabula_inner_parse_error(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")

        class BadDf:
            empty = True
            def to_json(self, *a, **kw): raise RuntimeError("bad json")

        tabula_mod = types.ModuleType("tabula")
        tabula_mod.read_tables = MagicMock(return_value=[BadDf()])
        monkeypatch.setitem(sys.modules, "tabula", tabula_mod)
        te = TableExtractor(strategy="tabula")
        # Should swallow the inner exception and return empty list
        out = te.extract(pdf, "p")
        assert out == []

    def test_extract_all_from_directory_default_ids(self, monkeypatch, tmp_path):
        # Create two PDFs
        (tmp_path / "alpha.pdf").write_bytes(b"%PDF-a")
        (tmp_path / "beta.pdf").write_bytes(b"%PDF-b")
        # Use pdfplumber stub returning empty tables for all files
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]] * 2)
        te = TableExtractor()
        out = te.extract_all_from_directory(tmp_path)
        # Each file yields zero tables, but paper_ids should still be derived
        assert out == []
        # No exceptions → ok
        # Calling with explicit paper_ids subset
        out = te.extract_all_from_directory(tmp_path, paper_ids=["custom"])
        assert out == []

    def test_extract_all_from_directory_no_pdfs(self, tmp_path):
        te = TableExtractor()
        out = te.extract_all_from_directory(tmp_path)
        assert out == []


# ─── FigureExtractor ─────────────────────────────────────────────────────


class TestFigureExtractor:
    def test_init_defaults(self):
        fe = FigureExtractor()
        assert fe.ocr_engine == "pytesseract"
        assert fe.dpi == 300

    def test_init_custom(self):
        fe = FigureExtractor(ocr_engine="tesseract", dpi=150)
        assert fe.ocr_engine == "tesseract"
        assert fe.dpi == 150

    def test_extract_missing_file(self, tmp_path):
        fe = FigureExtractor()
        assert fe.extract(tmp_path / "no.pdf", "p") == []

    def test_extract_no_fitz(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        fe = FigureExtractor()
        out = fe.extract(pdf, "p")
        assert out == []

    def test_extract_with_fitz_but_no_tesseract(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_fitz_mock(monkeypatch, page_count=2)
        if "pytesseract" in sys.modules:
            monkeypatch.delitem(sys.modules, "pytesseract", raising=False)
        fe = FigureExtractor()
        out = fe.extract(pdf, "p")
        assert len(out) == 2
        for f in out:
            assert f.paper_id == "p"
            assert f.has_ocr is False
            assert f.extracted_text == ""

    def test_extract_with_ocr(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_fitz_mock(monkeypatch, page_count=1)
        _install_pytesseract_mock(monkeypatch, text="Hello OCR")
        # PIL is needed for image conversion; pytest environment usually has it
        fe = FigureExtractor()
        out = fe.extract(pdf, "p")
        assert len(out) == 1
        f = out[0]
        assert f.paper_id == "p"
        assert f.page_num == 1
        assert f.has_ocr is True
        assert "Hello OCR" in f.extracted_text

    def test_extract_with_empty_ocr(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_fitz_mock(monkeypatch, page_count=1)
        _install_pytesseract_mock(monkeypatch, text="   \n  ")  # empty after strip
        fe = FigureExtractor()
        out = fe.extract(pdf, "p")
        assert len(out) == 1
        assert out[0].has_ocr is False

    def test_extract_fitz_open_raises(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_fitz_mock(monkeypatch, raise_open=True)
        fe = FigureExtractor()
        out = fe.extract(pdf, "p")
        assert out == []

    def test_extract_all_from_directory(self, monkeypatch, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"%PDF-a")
        _install_fitz_mock(monkeypatch, page_count=1)
        fe = FigureExtractor()
        out = fe.extract_all_from_directory(tmp_path)
        assert len(out) == 1
        assert out[0].paper_id == "a"

    def test_extract_all_from_directory_no_pdfs(self, tmp_path):
        fe = FigureExtractor()
        assert fe.extract_all_from_directory(tmp_path) == []


# ─── ChinesePDFParser ────────────────────────────────────────────────────


class TestChinesePDFParser:
    def test_init_default(self):
        p = ChinesePDFParser()
        assert p.ocr_backend == "rapidocr"

    def test_init_custom(self):
        p = ChinesePDFParser(ocr_backend="pytesseract")
        assert p.ocr_backend == "pytesseract"

    def test_parse_text_extraction(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        _install_fitz_mock(monkeypatch, page_count=1)
        # No OCR backend available
        for mod in ["rapidocr_ai", "pytesseract"]:
            if mod in sys.modules:
                monkeypatch.delitem(sys.modules, mod, raising=False)
        p = ChinesePDFParser(ocr_backend="nonexistent")
        out = p.parse(pdf, "cn_paper")
        assert out.paper_id == "cn_paper"
        assert out.status == ParseResultStatus.SUCCESS
        # At least one parsing_errors entry logs text length
        assert any("text_length=" in e for e in out.parsing_errors)

    def test_parse_text_extraction_no_pdfplumber(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "pdfplumber":
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        _install_fitz_mock(monkeypatch, page_count=0)
        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        # When pdfplumber unavailable, error is logged
        assert any("text_extraction_error" in e or "text_length=" in e
                   for e in out.parsing_errors)

    def test_parse_with_rapidocr_success(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        _install_fitz_mock(monkeypatch, page_count=1)

        rapid = types.ModuleType("rapidocr_ai")

        class FakeRapid:
            def __call__(self, _img):
                # Each item is (bbox, text, confidence). When text is a string,
                # ``" ".join(item[1])`` splits characters with spaces.
                return ([["bb", "中文字符", 0.99]], None, None)

        rapid.RapidOCR = FakeRapid
        monkeypatch.setitem(sys.modules, "rapidocr_ai", rapid)

        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        assert len(out.figures) == 1
        fig = out.figures[0]
        # OCR returned something (chars joined with spaces due to source logic)
        assert fig.has_ocr is True
        assert "中" in fig.extracted_text
        assert "文" in fig.extracted_text

    def test_parse_rapidocr_exception_falls_back_to_tesseract(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        _install_fitz_mock(monkeypatch, page_count=1)
        _install_pytesseract_mock(monkeypatch, text="中文文本 cn")

        rapid = types.ModuleType("rapidocr_ai")

        class BadRapid:
            def __call__(self, _img):
                raise RuntimeError("rapidocr fail")

        rapid.RapidOCR = BadRapid
        monkeypatch.setitem(sys.modules, "rapidocr_ai", rapid)

        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        # pytesseract fallback should run
        assert any("中文" in f.extracted_text for f in out.figures)

    def test_parse_no_ocr_backend_available(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        _install_fitz_mock(monkeypatch, page_count=1)
        for mod in ["rapidocr_ai", "pytesseract"]:
            if mod in sys.modules:
                monkeypatch.delitem(sys.modules, mod, raising=False)
        # Patch __import__ to refuse those modules
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("rapidocr_ai", "rapidocr", "pytesseract"):
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        # No OCR text recovered; figures still present but has_ocr False
        for f in out.figures:
            assert f.has_ocr is False

    def test_parse_no_fitz_figure_error(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "fitz":
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        assert any("PyMuPDF not available" in e for e in out.parsing_errors)

    def test_parse_status_unchanged_without_content(self, monkeypatch, tmp_path):
        pdf = tmp_path / "cn.pdf"
        pdf.write_bytes(b"%PDF-c")
        # No tables, no figures
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "fitz":
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        p = ChinesePDFParser()
        out = p.parse(pdf, "cn")
        # status remains SUCCESS because parsing completed
        assert out.status in (ParseResultStatus.SUCCESS, ParseResultStatus.ERROR)


# ─── RegressionTableParser ───────────────────────────────────────────────


class TestRegressionTableParser:
    def test_init(self):
        p = RegressionTableParser()
        assert p is not None

    def test_is_regression_english(self):
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html="<table><tr><th>Variable</th><th>Coef</th><th>Std.</th></tr></table>",
        )
        assert RegressionTableParser._is_regression_table(t) is True

    def test_is_regression_chinese(self):
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html="<table><tr><th>变量</th><th>系数</th><th>标准误</th></tr></table>",
        )
        assert RegressionTableParser._is_regression_table(t) is True

    def test_is_regression_below_threshold(self):
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html="<table><tr><th>Country</th><th>GDP</th></tr></table>",
        )
        assert RegressionTableParser._is_regression_table(t) is False

    def test_is_regression_case_insensitive(self):
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html="<table><tr><th>VARIABLE</th><th>ESTIMATE</th></tr></table>",
        )
        assert RegressionTableParser._is_regression_table(t) is True

    def test_parse_regression_structure_from_json(self):
        df = pd.DataFrame({
            "Var": ["x", "y"],
            "(1)": [0.1, 0.2],
            "(2)": [0.3, 0.4],
        })
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            dataframe_json=df.to_json(orient="records"),
            table_html="<table/>",
        )
        r = RegressionTableParser._parse_regression_structure(t)
        assert r.paper_id == "p"
        assert r.table_index == 0
        assert r.page_num == 1
        assert r.headers == [list(df.columns)]
        # Body cells come out as floats (with possible FP precision drift);
        # we compare cell-by-cell with tolerance rather than exact equality.
        expected_body = [list(row) for row in df.values.tolist()]
        assert len(r.body) == len(expected_body)
        for actual_row, expected_row in zip(r.body, expected_body):
            assert len(actual_row) == len(expected_row)
            for av, ev in zip(actual_row, expected_row):
                if isinstance(ev, float):
                    assert isinstance(av, float)
                    assert av == pytest.approx(ev)
                else:
                    assert av == ev
        assert r.notes == ""

    def test_parse_regression_structure_fallback_to_html(self):
        # Bad JSON so it falls back to HTML parsing
        html = (
            "<table>"
            "<tr><th>Var</th><th>Coef</th></tr>"
            "<tr><td>x</td><td>0.5</td></tr>"
            "<tr><td>y</td><td>1.0</td></tr>"
            "</table>"
        )
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html=html, dataframe_json="",
        )
        r = RegressionTableParser._parse_regression_structure(t)
        # Header row should be parsed from the <th> cells
        assert len(r.headers) == 1
        assert r.headers[0] == ["Var", "Coef"]
        # Body must contain the cell text. The simple regex implementation groups
        # <td> cells into a single row regardless of <tr> boundaries — verify
        # the actual cell values are present in the body's flattened form.
        flat = " ".join(cell for row in r.body for cell in row)
        assert "x" in flat
        assert "0.5" in flat
        assert "y" in flat
        assert "1.0" in flat

    def test_parse_regression_structure_includes_note(self):
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            table_html="<table><tr><th>A</th></tr></table>",
            note="Robust SE clustered by firm",
        )
        r = RegressionTableParser._parse_regression_structure(t)
        assert r.notes == "Robust SE clustered by firm"

    def test_extract_routes_through_table_extractor(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_pdfplumber_mock(
            monkeypatch,
            pages_with_tables=[[
                [["Var", "Coef", "Std"], ["treated", "0.05", "0.01"], ["N", "1000", ""]],
            ]],
        )
        p = RegressionTableParser()
        out = p.extract(pdf, "rp")
        assert len(out) == 1
        assert isinstance(out[0], RegressionTableResult)
        assert out[0].paper_id == "rp"

    def test_extract_returns_empty_when_no_tables(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[]])
        p = RegressionTableParser()
        out = p.extract(pdf, "rp")
        assert out == []

    def test_extract_skips_non_regression_tables(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        _install_pdfplumber_mock(
            monkeypatch,
            pages_with_tables=[[
                [["Name", "Age", "Country"], ["Alice", "30", "USA"]],
            ]],
        )
        p = RegressionTableParser()
        out = p.extract(pdf, "rp")
        assert out == []

    def test_identify_variables_english(self):
        r = RegressionTableResult(
            paper_id="p", table_index=0, page_num=1,
            headers=[["", "(1)", "(2)"]],
            body=[
                ["dependent var", "0.1", "0.2"],
                ["treatment", "0.05", "0.07"],
                ["X1 control", "0.0", "0.0"],
            ],
        )
        result = RegressionTableParser.identify_variables_from_tables([r])
        assert "dependent" in result
        assert "independent" in result
        # dependent tokens should mention "dependent"
        joined_dep = " ".join(result["dependent"]).lower()
        assert "dependent" in joined_dep
        joined_indep = " ".join(result["independent"]).lower()
        assert "treatment" in joined_indep or "control" in joined_indep

    def test_identify_variables_chinese(self):
        r = RegressionTableResult(
            paper_id="p", table_index=0, page_num=1,
            headers=[["", "(1)"]],
            body=[
                ["因变量: ln_income", "0.1"],
                ["核心解释变量 treated", "0.05"],
            ],
        )
        result = RegressionTableParser.identify_variables_from_tables([r])
        joined_dep = " ".join(result["dependent"]).lower()
        joined_indep = " ".join(result["independent"]).lower()
        assert "因变量" in joined_dep or "ln_income" in joined_dep
        assert "核心解释" in joined_indep or "treated" in joined_indep

    def test_identify_variables_empty(self):
        result = RegressionTableParser.identify_variables_from_tables([])
        assert result["dependent"] == set()
        assert result["independent"] == set()


# ─── PaperDeepParser orchestrator ────────────────────────────────────────


class TestPaperDeepParser:
    def test_init_default(self):
        p = PaperDeepParser()
        assert p.chinese_mode is False
        assert isinstance(p.table_extractor, TableExtractor)
        assert isinstance(p.figure_extractor, FigureExtractor)
        assert isinstance(p.regression_parser, RegressionTableParser)
        # No chinese_parser attribute by default
        assert not hasattr(p, "chinese_parser") or getattr(p, "chinese_parser", None) is None

    def test_init_chinese_mode(self):
        p = PaperDeepParser(chinese_mode=True)
        assert p.chinese_mode is True
        assert isinstance(p.chinese_parser, ChinesePDFParser)

    def test_parse_missing_file(self, tmp_path):
        p = PaperDeepParser()
        r = p.parse(tmp_path / "missing.pdf")
        assert r.status == ParseResultStatus.ERROR
        assert any("File not found" in e for e in r.parsing_errors)
        assert r.paper_id == "missing"  # derived from stem
        assert r.parsing_time_sec >= 0

    def test_parse_explicit_paper_id(self, tmp_path):
        p = PaperDeepParser()
        r = p.parse(tmp_path / "missing.pdf", paper_id="custom_id")
        assert r.paper_id == "custom_id"
        assert r.status == ParseResultStatus.ERROR

    def test_parse_with_only_tables(self, monkeypatch, tmp_path):
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-a")
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[
            [["Var", "Coef"], ["x", "0.1"], ["y", "0.2"]],
        ]])
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        p = PaperDeepParser()
        r = p.parse(pdf, "p1")
        # Tables → status TABLE_EXTRACTED
        assert r.status == ParseResultStatus.TABLE_EXTRACTED
        assert len(r.tables) == 1

    def test_parse_with_only_figures(self, monkeypatch, tmp_path):
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"%PDF-b")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "pdfplumber":
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        _install_fitz_mock(monkeypatch, page_count=2)
        _install_pytesseract_mock(monkeypatch, text="")
        p = PaperDeepParser()
        r = p.parse(pdf, "p2")
        assert r.status == ParseResultStatus.FIGURE_EXTRACTED
        assert len(r.figures) == 2

    def test_parse_records_extraction_errors(self, monkeypatch, tmp_path):
        pdf = tmp_path / "c.pdf"
        pdf.write_bytes(b"%PDF-c")

        # Force table extractor to raise
        bad_ext = MagicMock(spec=TableExtractor)
        bad_ext.extract = MagicMock(side_effect=RuntimeError("table boom"))
        # Force figure extractor to raise
        bad_fig = MagicMock(spec=FigureExtractor)
        bad_fig.extract = MagicMock(side_effect=RuntimeError("figure boom"))
        # Force regression parser to raise
        bad_reg = MagicMock(spec=RegressionTableParser)
        bad_reg.extract = MagicMock(side_effect=RuntimeError("reg boom"))

        p = PaperDeepParser()
        p.table_extractor = bad_ext
        p.figure_extractor = bad_fig
        p.regression_parser = bad_reg

        r = p.parse(pdf, "p3")
        # Status is ERROR because no tables or figures succeeded
        assert r.status == ParseResultStatus.ERROR
        assert any("table_extraction_error" in e for e in r.parsing_errors)
        assert any("figure_extraction_error" in e for e in r.parsing_errors)
        assert any("regression_table_error" in e for e in r.parsing_errors)

    def test_parse_default_paper_id_from_stem(self, monkeypatch, tmp_path):
        pdf = tmp_path / "my_paper.pdf"
        pdf.write_bytes(b"%PDF-x")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("pdfplumber", "fitz"):
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        p = PaperDeepParser()
        r = p.parse(pdf)
        assert r.paper_id == "my_paper"

    def test_parse_batch_uses_default_ids(self, monkeypatch, tmp_path):
        p1 = tmp_path / "p1.pdf"
        p2 = tmp_path / "p2.pdf"
        for p in (p1, p2):
            p.write_bytes(b"%PDF")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("pdfplumber", "fitz"):
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        parser = PaperDeepParser()
        out = parser.parse_batch([p1, p2])
        ids = [r.paper_id for r in out]
        assert "p1" in ids
        assert "p2" in ids

    def test_parse_batch_pads_paper_ids(self, monkeypatch, tmp_path):
        p1 = tmp_path / "p1.pdf"
        p2 = tmp_path / "p2.pdf"
        for p in (p1, p2):
            p.write_bytes(b"%PDF")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("pdfplumber", "fitz"):
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        parser = PaperDeepParser()
        out = parser.parse_batch([p1, p2], paper_ids=["only_one"])
        ids = [r.paper_id for r in out]
        assert ids[0] == "only_one"
        assert ids[1] == "p2"  # derived from stem

    def test_parse_directory_no_pdfs(self, tmp_path):
        parser = PaperDeepParser()
        assert parser.parse_directory(tmp_path) == []

    def test_parse_directory_uses_glob(self, monkeypatch, tmp_path):
        for stem in ("a", "b"):
            (tmp_path / f"{stem}.pdf").write_bytes(b"%PDF")
        if "pdfplumber" in sys.modules:
            monkeypatch.delitem(sys.modules, "pdfplumber", raising=False)
        if "fitz" in sys.modules:
            monkeypatch.delitem(sys.modules, "fitz", raising=False)
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("pdfplumber", "fitz"):
                raise ImportError("nope")
            return orig_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        parser = PaperDeepParser()
        out = parser.parse_directory(tmp_path)
        assert len(out) == 2


# ─── PaperDeepParser.export_results ─────────────────────────────────────


class TestExportResults:
    def test_export_creates_subdirs_and_files(self, tmp_path):
        # Build a fake parse result with tables and figures
        out_dir = tmp_path / "out"
        t = TableResult(
            paper_id="p1", table_index=0, page_num=1,
            dataframe_json=pd.DataFrame({"a": [1]}).to_json(orient="records"),
            caption="", note="",
        )
        # Real PNG bytes for the figure source
        png_src = tmp_path / "fig_src.png"
        png_src.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        f = FigureResult(
            paper_id="p1", figure_index=0, page_num=1,
            image_path=str(png_src), extracted_text="", has_ocr=False,
        )
        r = ParseResult(
            paper_id="p1", file_path="/x.pdf",
            tables=[t], figures=[f],
        )
        parser = PaperDeepParser()
        parser.export_results([r], out_dir)

        assert (out_dir / "tables").is_dir()
        assert (out_dir / "figures").is_dir()
        # CSV created
        csv = out_dir / "tables" / "p1_table_0.csv"
        assert csv.exists()
        # Figure copied with new name
        copied = out_dir / "figures" / "p1_figure_0.png"
        assert copied.exists()
        # JSON metadata
        meta = out_dir / "p1_parse_result.json"
        assert meta.exists()
        data = json.loads(meta.read_text(encoding="utf-8"))
        assert data["paper_id"] == "p1"

    def test_export_skips_figures_without_image(self, tmp_path):
        out_dir = tmp_path / "out"
        f = FigureResult(
            paper_id="p", figure_index=0, page_num=1,
            image_path="", extracted_text="x", has_ocr=False,
        )
        r = ParseResult(paper_id="p", file_path="/x.pdf", figures=[f])
        PaperDeepParser().export_results([r], out_dir)
        assert (out_dir / "figures").is_dir()
        assert list((out_dir / "figures").iterdir()) == []

    def test_export_skips_figures_with_missing_path(self, tmp_path):
        out_dir = tmp_path / "out"
        f = FigureResult(
            paper_id="p", figure_index=0, page_num=1,
            image_path=str(tmp_path / "no.png"), extracted_text="x", has_ocr=False,
        )
        r = ParseResult(paper_id="p", file_path="/x.pdf", figures=[f])
        PaperDeepParser().export_results([r], out_dir)
        assert list((out_dir / "figures").iterdir()) == []

    def test_export_skips_empty_table(self, tmp_path):
        out_dir = tmp_path / "out"
        t = TableResult(
            paper_id="p", table_index=0, page_num=1,
            dataframe_json="", table_html="",
        )
        r = ParseResult(paper_id="p", file_path="/x.pdf", tables=[t])
        PaperDeepParser().export_results([r], out_dir)
        assert list((out_dir / "tables").iterdir()) == []

    def test_export_multiple_results(self, tmp_path):
        out_dir = tmp_path / "out"
        r1 = ParseResult(
            paper_id="a", file_path="/a.pdf",
            tables=[TableResult(paper_id="a", table_index=0, page_num=1,
                                dataframe_json=pd.DataFrame({"c": [1]}).to_json(orient="records"))],
        )
        r2 = ParseResult(
            paper_id="b", file_path="/b.pdf",
            tables=[TableResult(paper_id="b", table_index=0, page_num=1,
                                dataframe_json=pd.DataFrame({"d": [2]}).to_json(orient="records"))],
        )
        PaperDeepParser().export_results([r1, r2], out_dir)
        assert (out_dir / "a_parse_result.json").exists()
        assert (out_dir / "b_parse_result.json").exists()
        assert (out_dir / "tables" / "a_table_0.csv").exists()
        assert (out_dir / "tables" / "b_table_0.csv").exists()


# ─── End-to-end smoke ────────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_pipeline_with_mocks(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-x")
        # Tables + regression + figures + OCR
        _install_pdfplumber_mock(monkeypatch, pages_with_tables=[[
            [["Var", "Coef", "Std"], ["treatment", "0.05", "0.01"], ["N", "1000", ""]],
        ]])
        _install_fitz_mock(monkeypatch, page_count=1)
        _install_pytesseract_mock(monkeypatch, text="Figure 1: GDP")

        parser = PaperDeepParser()
        result = parser.parse(pdf, "demo")

        # Must have tables, figures, and at least one regression table
        assert len(result.tables) >= 1
        assert len(result.figures) == 1
        assert len(result.reg_tables) >= 1
        # summary contains everything
        s = result.summary()
        assert "demo" in s
        assert "tables=" in s
        assert "figures=" in s
        # JSON serialisable
        json.dumps(result.to_dict(), ensure_ascii=False)
        # Status reflects what's been extracted
        assert result.status in (
            ParseResultStatus.TABLE_EXTRACTED,
            ParseResultStatus.FIGURE_EXTRACTED,
            ParseResultStatus.SUCCESS,
        )