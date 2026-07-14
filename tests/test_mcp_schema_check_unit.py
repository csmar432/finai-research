"""Unit tests for scripts/mcp_schema_check.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def msc():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import mcp_schema_check
    yield mcp_schema_check
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestGetHandlerParams:
    def test_extracts_typed_params(self, msc):
        src = '''
arg1: str = args.get("alpha")
arg2: int = args.get("beta")
'''
        params = msc._get_handler_params(src)
        assert "alpha" in params
        # Note: the first regex stores the type name (str/int) as value
        # because group(2) is the type. Don't depend on specific value.
        assert "beta" in params

    def test_extracts_untyped_params(self, msc):
        src = 'x = args.get("key1", "")\ny = args.get("key2")\n'
        params = msc._get_handler_params(src)
        assert "key1" in params
        assert "key2" in params

    def test_empty_source(self, msc):
        assert msc._get_handler_params("") == {}


class TestExtractSignatureParams:
    def test_extracts_simple(self, msc):
        src = "def foo(x, y, z): pass"
        params = msc._extract_handler_params_from_signature(src)
        assert params == {"x", "y", "z"}

    def test_excludes_self(self, msc):
        src = "def foo(self, x): pass"
        params = msc._extract_handler_params_from_signature(src)
        assert params == {"x"}

    def test_excludes_args(self, msc):
        src = "def foo(self, args, x): pass"
        params = msc._extract_handler_params_from_signature(src)
        assert params == {"x"}

    def test_excludes_kwargs(self, msc):
        src = "def foo(self, kwargs, x): pass"
        params = msc._extract_handler_params_from_signature(src)
        assert params == {"x"}

    def test_default_value_handled(self, msc):
        src = "def foo(x, y=10, z=None): pass"
        params = msc._extract_handler_params_from_signature(src)
        assert params == {"x", "y", "z"}

    def test_no_def_returns_empty(self, msc):
        assert msc._extract_handler_params_from_signature("not a def") == set()


class TestNormalizeToolName:
    def test_strip_get(self, msc):
        assert msc._normalize_tool_name("get_quote") == "quote"

    def test_strip_fetch(self, msc):
        assert msc._normalize_tool_name("fetch_data") == "data"

    def test_strip_search(self, msc):
        assert msc._normalize_tool_name("search_papers") == "papers"

    def test_strip_list(self, msc):
        assert msc._normalize_tool_name("list_items") == "items"

    def test_lowercase(self, msc):
        assert msc._normalize_tool_name("GetData") == "getdata"

    def test_no_prefix(self, msc):
        assert msc._normalize_tool_name("hello") == "hello"

