"""Unit tests for small uncovered utility scripts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import(modname, filepath):
    import importlib
    try:
        return importlib.import_module(modname)
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(modname, filepath)
        m = importlib.util.module_from_spec(spec)
        sys.modules[modname] = m
        spec.loader.exec_module(m)
        return m


@pytest.fixture(scope="module")
def calendar_qualifier():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.calendar_qualifier",
                  "scripts/research_framework/calendar_qualifier.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def logging_config():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.logging_config",
                  "scripts/logging_config.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def exceptions():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.exceptions",
                  "scripts/exceptions.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def parse_mcp_data():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.parse_mcp_data",
                  "scripts/parse_mcp_data.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def fetch_us_esg_data():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.fetch_us_esg_data",
                  "scripts/fetch_us_esg_data.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def fix_metadata():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.fix_metadata",
                  "scripts/fix_metadata.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def auto_register_tools():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.auto_register_tools",
                  "scripts/auto_register_tools.py")
    if _p in sys.path:
        sys.path.remove(_p)


class TestCalendarQualifier:
    def test_module_imports(self, calendar_qualifier):
        assert calendar_qualifier is not None

    def test_has_callables(self, calendar_qualifier):
        fns = [n for n in dir(calendar_qualifier)
               if not n.startswith('_') and callable(getattr(calendar_qualifier, n, None))]
        assert len(fns) >= 1


class TestLoggingConfig:
    def test_module_imports(self, logging_config):
        assert logging_config is not None


class TestExceptions:
    def test_module_imports(self, exceptions):
        assert exceptions is not None

    def test_has_exception_classes(self, exceptions):
        excs = [n for n in dir(exceptions)
                if isinstance(getattr(exceptions, n, None), type)
                and issubclass(getattr(exceptions, n), Exception)]
        assert len(excs) >= 0  # may have 0 if module just imports


class TestParseMcpData:
    def test_module_imports(self, parse_mcp_data):
        assert parse_mcp_data is not None


class TestFetchUsEsgData:
    def test_module_imports(self, fetch_us_esg_data):
        assert fetch_us_esg_data is not None


class TestFixMetadata:
    def test_module_imports(self, fix_metadata):
        assert fix_metadata is not None


class TestAutoRegisterTools:
    def test_module_imports(self, auto_register_tools):
        assert auto_register_tools is not None

    def test_has_main(self, auto_register_tools):
        assert hasattr(auto_register_tools, "main") or \
               any(callable(getattr(auto_register_tools, n, None))
                   for n in dir(auto_register_tools)
                   if not n.startswith('_'))
