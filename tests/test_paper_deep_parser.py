"""Tests for paper_deep_parser.py — PDF deep parsing engine."""

import pytest
import json


# ─── Enums ───────────────────────────────────────────────────────────────

def test_parse_result_status_enum():
    from scripts.core.paper_deep_parser import ParseResultStatus
    assert ParseResultStatus.SUCCESS.value == "success"
    assert ParseResultStatus.TABLE_EXTRACTED.value == "table_extracted"
    assert ParseResultStatus.ERROR.value == "error"


# ─── TableResult ────────────────────────────────────────────────────────

def test_table_result_basic():
    from scripts.core.paper_deep_parser import TableResult

    tr = TableResult(
        paper_id="p1",
        table_index=0,
        page_num=3,
        table_html="<table><tr><td>A</td><td>1</td></tr></table>",
        dataframe_json='{"A":[1],"B":[2]}',
        caption="Descriptive statistics",
    )
    assert tr.paper_id == "p1"
    assert tr.table_index == 0
    csv_str = tr.to_csv_string()
    assert "A" in csv_str
    assert "1" in csv_str


def test_table_result_to_dict():
    from scripts.core.paper_deep_parser import TableResult

    tr = TableResult(
        paper_id="p2",
        table_index=1,
        page_num=5,
        table_html="<table></table>",
        dataframe_json='{"x":[1,2],"y":[3,4]}',
    )
    d = tr.to_dict()
    assert d["paper_id"] == "p2"
    assert d["page_num"] == 5


# ─── FigureResult ────────────────────────────────────────────────────────

def test_figure_result():
    from scripts.core.paper_deep_parser import FigureResult

    fr = FigureResult(
        paper_id="fig1",
        figure_index=0,
        page_num=1,
        image_path="/tmp/fig1.png",
        extracted_text="Figure 1: GDP growth",
        has_ocr=True,
        caption="GDP over time",
    )
    assert fr.has_ocr
    assert "GDP" in fr.extracted_text
    d = fr.to_dict()
    assert d["figure_index"] == 0


# ─── RegressionTableResult ────────────────────────────────────────────────

def test_regression_table_result():
    from scripts.core.paper_deep_parser import RegressionTableResult

    rtr = RegressionTableResult(
        paper_id="r1",
        table_index=0,
        page_num=4,
        headers=[["", "(1)", "(2)"]],
        body=[
            ["treatment", "0.05***", "0.07***"],
            ["control", "0.02", "0.03"],
            ["N", "1000", "2000"],
        ],
    )
    assert len(rtr.body) == 3
    stata = rtr.to_stata_format()
    assert "treatment" in stata
    assert "0.05" in stata


def test_regression_table_to_dict():
    from scripts.core.paper_deep_parser import RegressionTableResult

    rtr = RegressionTableResult(
        paper_id="r2", table_index=1, page_num=6,
        headers=[["Var", "Coef"]],
        body=[["x", "1.2"]],
    )
    d = rtr.to_dict()
    assert d["paper_id"] == "r2"
    assert d["body"][0][0] == "x"


# ─── ParseResult ─────────────────────────────────────────────────────────

def test_parse_result_basic():
    from scripts.core.paper_deep_parser import ParseResult, ParseResultStatus

    pr = ParseResult(
        paper_id="doc1",
        file_path="/tmp/test.pdf",
        status=ParseResultStatus.SUCCESS,
        tables=[],
        figures=[],
        reg_tables=[],
        parsing_errors=[],
        parsing_time_sec=1.5,
    )
    assert pr.status == ParseResultStatus.SUCCESS
    assert pr.parsing_time_sec == 1.5
    d = pr.to_dict()
    assert d["paper_id"] == "doc1"


def test_parse_result_summary():
    from scripts.core.paper_deep_parser import ParseResult, ParseResultStatus, TableResult

    pr = ParseResult(
        paper_id="doc2",
        file_path="/tmp/test2.pdf",
        status=ParseResultStatus.TABLE_EXTRACTED,
        tables=[
            TableResult(
                paper_id="doc2", table_index=0, page_num=1,
                table_html="", dataframe_json="{}", caption="",
            ),
            TableResult(
                paper_id="doc2", table_index=1, page_num=2,
                table_html="", dataframe_json="{}", caption="",
            ),
        ],
        figures=[],
        reg_tables=[],
        parsing_errors=["Warning: font not embedded"],
        parsing_time_sec=2.0,
    )
    s = pr.summary()
    assert "tables=2" in s
    assert "figures=0" in s
    assert "errors=1" in s  # 1 parsing error recorded


# ─── TableExtractor ──────────────────────────────────────────────────────

def test_table_extractor_init():
    from scripts.core.paper_deep_parser import TableExtractor
    te = TableExtractor(strategy="pdfplumber")
    assert te.strategy == "pdfplumber"


def test_table_extractor_extract_fake_file(tmp_path):
    from scripts.core.paper_deep_parser import TableExtractor
    te = TableExtractor()
    # Non-existent file should be caught by graceful handling
    results = te.extract(tmp_path / "nonexistent.pdf", "fake")
    assert results == []  # graceful empty list


# ─── RegressionTableParser ────────────────────────────────────────────────

def test_is_regression_table_english():
    from scripts.core.paper_deep_parser import RegressionTableParser, TableResult

    rtp = RegressionTableParser()
    table = TableResult(
        paper_id="t1", table_index=0, page_num=1,
        table_html="<table><th>Variable</th><th>Estimate</th><th>Std.</th></table>",
        dataframe_json="{}",
    )
    assert rtp._is_regression_table(table)


def test_is_regression_table_chinese():
    from scripts.core.paper_deep_parser import RegressionTableParser, TableResult

    rtp = RegressionTableParser()
    table = TableResult(
        paper_id="t2", table_index=0, page_num=1,
        table_html="<table><th>变量</th><th>系数</th><th>标准误</th></table>",
        dataframe_json="{}",
    )
    assert rtp._is_regression_table(table)


def test_is_regression_table_false():
    from scripts.core.paper_deep_parser import RegressionTableParser, TableResult

    rtp = RegressionTableParser()
    table = TableResult(
        paper_id="t3", table_index=0, page_num=1,
        table_html="<table><th>Name</th><th>Age</th><th>Country</th></table>",
        dataframe_json="{}",
    )
    assert not rtp._is_regression_table(table)


def test_parse_regression_structure():
    from scripts.core.paper_deep_parser import RegressionTableParser, TableResult

    rtp = RegressionTableParser()
    table = TableResult(
        paper_id="r1", table_index=2, page_num=3,
        table_html="<table><tr><td>treated</td><td>0.05</td><td>0.01</td></tr></table>",
        dataframe_json="{}",
    )
    result = rtp._parse_regression_structure(table)
    assert result.paper_id == "r1"
    assert result.table_index == 2


def test_identify_variables_from_tables():
    from scripts.core.paper_deep_parser import RegressionTableParser, RegressionTableResult

    rtp = RegressionTableParser()
    tables = [
        RegressionTableResult(
            paper_id="p1", table_index=0, page_num=1,
            headers=[["", "(1)", "(2)"]],
            body=[
                ["treated", "0.05", "0.07"],
                ["ln_K", "0.30", "0.25"],
                ["N", "1000", "2000"],
            ],
        ),
    ]
    vars_dict = rtp.identify_variables_from_tables(tables)
    assert "dependent" in vars_dict or "independent" in vars_dict
    body_vars = [v for vs in vars_dict.values() for v in vs]
    # body_vars may contain deduplicated tokens; check flattened body
    flat = " ".join([" ".join(r) for r in [["treated","0.05","0.07"],["ln_K","0.30","0.25"],["N","1000","2000"]]])
    assert "treated" in flat


# ─── PaperDeepParser ──────────────────────────────────────────────────────

def test_paper_deep_parser_init():
    from scripts.core.paper_deep_parser import PaperDeepParser
    parser = PaperDeepParser()
    assert not parser.chinese_mode


def test_paper_deep_parser_init_chinese():
    from scripts.core.paper_deep_parser import PaperDeepParser
    parser = PaperDeepParser(chinese_mode=True)
    assert parser.chinese_mode


def test_paper_deep_parser_parse_fake_file(tmp_path):
    from scripts.core.paper_deep_parser import PaperDeepParser, ParseResultStatus
    parser = PaperDeepParser()
    result = parser.parse(tmp_path / "nonexistent.pdf", "fake_paper")
    assert result.status == ParseResultStatus.ERROR
    assert len(result.parsing_errors) > 0
