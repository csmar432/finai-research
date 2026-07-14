"""Unit tests for scripts/retry_utils.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ru():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import retry_utils
    yield retry_utils
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestRetryApiCall:
    def test_no_retry_when_tenacity_missing(self, ru, monkeypatch):
        """When tenacity not available, decorator is a no-op pass-through."""
        monkeypatch.setattr(ru, "_TENACITY_AVAILABLE", False)
        decorator = ru.retry_api_call(max_attempts=3)
        # Should be a callable

        @decorator
        def myfunc(x):
            return x * 2

        assert myfunc(5) == 10

    def test_decorator_supports_direct_call(self, ru, monkeypatch):
        """@retry_api_call (no parens) — not actually supported by retry_api_call.

        `_no_retry_decorator()` does support it, but retry_api_call needs
        (max_attempts=..., backoff=...) arguments.
        """
        monkeypatch.setattr(ru, "_TENACITY_AVAILABLE", False)

        # With parens
        @ru.retry_api_call()
        def myfunc():
            return "ok"

        assert myfunc() == "ok"


class TestRetryWithBackoff:
    def test_succeeds_first_try(self, ru, monkeypatch):
        def good_func(*args, **kwargs):
            return "success"

        with mock.patch.object(ru.time, "sleep"):
            result = ru.retry_with_backoff(good_func, max_attempts=3)
            assert result == "success"

    def test_retries_then_succeeds(self, ru, monkeypatch):
        calls = {"count": 0}

        def flaky_func():
            calls["count"] += 1
            if calls["count"] < 2:
                raise ConnectionError("fail")
            return "ok"

        with mock.patch.object(ru.time, "sleep"):
            result = ru.retry_with_backoff(flaky_func, max_attempts=3)
        assert result == "ok"
        assert calls["count"] == 2

    def test_raises_after_max_attempts(self, ru, monkeypatch):
        calls = {"count": 0}

        def always_fail():
            calls["count"] += 1
            raise ConnectionError(f"fail #{calls['count']}")

        with mock.patch.object(ru.time, "sleep"):
            with pytest.raises(ConnectionError):
                ru.retry_with_backoff(always_fail, max_attempts=2)
        assert calls["count"] == 2

    def test_passes_args_and_kwargs(self, ru, monkeypatch):
        def myfunc(x, y, z=0):
            return x + y + z

        with mock.patch.object(ru.time, "sleep"):
            result = ru.retry_with_backoff(myfunc, 1, 2, z=3, max_attempts=1)
        assert result == 6

    def test_with_single_exception_type(self, ru, monkeypatch):
        calls = {"count": 0}

        def may_fail():
            calls["count"] += 1
            if calls["count"] < 2:
                raise ValueError("nope")
            return "done"

        with mock.patch.object(ru.time, "sleep"):
            result = ru.retry_with_backoff(may_fail, max_attempts=2, exceptions=ValueError)
        assert result == "done"


class TestExports:
    def test_all_exports_present(self, ru):
        for name in ["retry_api_call", "retry_with_backoff", "retry_tushare",
                     "retry_yfinance", "retry_macro", "DEFAULT_RETRY_EXCEPTIONS"]:
            assert name in ru.__all__
            assert hasattr(ru, name)

    def test_default_exceptions(self, ru):
        assert ConnectionError in ru.DEFAULT_RETRY_EXCEPTIONS
        assert TimeoutError in ru.DEFAULT_RETRY_EXCEPTIONS

