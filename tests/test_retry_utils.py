"""Test retry_utils — 覆盖 4 个核心场景"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from scripts.retry_utils import (
    retry_api_call,
    retry_with_backoff,
    DEFAULT_RETRY_EXCEPTIONS,
    _TENACITY_AVAILABLE,
)


# ---------------------------------------------------------------------------
# 1) retry_with_backoff 函数式（不需要 tenacity）
# ---------------------------------------------------------------------------

class FlakyCounter:
    def __init__(self, fail_n: int, exc: Exception | None = None):
        self.calls = 0
        self.fail_n = fail_n
        self.exc = exc or ConnectionError("flaky")

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_n:
            raise self.exc
        return "ok"


def test_retry_with_backoff_success_first_try():
    counter = FlakyCounter(fail_n=0)
    result = retry_with_backoff(counter, max_attempts=3, backoff=0.01)
    assert result == "ok"
    assert counter.calls == 1


def test_retry_with_backoff_success_after_failures():
    counter = FlakyCounter(fail_n=2)
    result = retry_with_backoff(counter, max_attempts=5, backoff=0.01)
    assert result == "ok"
    assert counter.calls == 3  # 2 failures + 1 success


def test_retry_with_backoff_gives_up():
    counter = FlakyCounter(fail_n=10)
    with pytest.raises(ConnectionError):
        retry_with_backoff(counter, max_attempts=3, backoff=0.01)
    assert counter.calls == 3


def test_retry_with_backoff_passes_args():
    def add(a, b, *, mul=1):
        return (a + b) * mul

    result = retry_with_backoff(add, 2, 3, max_attempts=2, backoff=0.01, mul=4)
    assert result == 20


# ---------------------------------------------------------------------------
# 2) retry_api_call 装饰器（需要 tenacity）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _TENACITY_AVAILABLE, reason="tenacity not installed")
def test_retry_api_call_decorator():
    counter = FlakyCounter(fail_n=2)

    @retry_api_call(max_attempts=3, backoff=0.01)
    def flaky_func():
        return counter()

    result = flaky_func()
    assert result == "ok"
    assert counter.calls == 3


@pytest.mark.skipif(not _TENACITY_AVAILABLE, reason="tenacity not installed")
def test_retry_api_call_preserves_metadata():
    @retry_api_call(max_attempts=2, backoff=0.01)
    def my_func(x: int) -> int:
        """My docstring."""
        return x * 2

    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "My docstring."
    assert my_func(5) == 10


@pytest.mark.skipif(not _TENACITY_AVAILABLE, reason="tenacity not installed")
def test_retry_api_call_does_not_retry_other_exceptions():
    counter = FlakyCounter(fail_n=5, exc=ValueError("not retried"))

    @retry_api_call(max_attempts=3, backoff=0.01, exceptions=ConnectionError)
    def picky_func():
        return counter()

    with pytest.raises(ValueError):
        picky_func()
    # 只调用了 1 次（ValueError 不在 exceptions 中）
    assert counter.calls == 1


# ---------------------------------------------------------------------------
# 3) 降级 (tenacity 不可用) — 装饰器仍然能调用
# ---------------------------------------------------------------------------

def test_no_op_decorator_works():
    """即使 tenacity 不可用，装饰器也不抛错"""

    @retry_api_call(max_attempts=3, backoff=0.01)
    def simple_func(x):
        return x + 1

    assert simple_func(10) == 11


def test_no_op_decorator_no_retry():
    """降级模式下不重试"""

    @retry_api_call(max_attempts=3, backoff=0.01)
    def always_fails():
        raise ConnectionError("nope")

    with pytest.raises(ConnectionError):
        always_fails()


# ---------------------------------------------------------------------------
# 4) 边界条件
# ---------------------------------------------------------------------------

def test_retry_with_backoff_max_attempts_1():
    counter = FlakyCounter(fail_n=0)
    result = retry_with_backoff(counter, max_attempts=1, backoff=0.01)
    assert result == "ok"
    assert counter.calls == 1


def test_retry_with_backoff_single_exception_type():
    counter = FlakyCounter(fail_n=2, exc=TimeoutError("slow"))
    result = retry_with_backoff(
        counter, max_attempts=5, backoff=0.01, exceptions=TimeoutError
    )
    assert result == "ok"
    assert counter.calls == 3


def test_retry_with_backoff_exception_tuple():
    counter = FlakyCounter(fail_n=2, exc=TimeoutError("slow"))
    result = retry_with_backoff(
        counter, max_attempts=5, backoff=0.01,
        exceptions=(ConnectionError, TimeoutError)
    )
    assert result == "ok"


# ---------------------------------------------------------------------------
# 5) 性能 smoke test (确保重试不会导致指数爆炸)
# ---------------------------------------------------------------------------

def test_retry_with_backoff_actually_waits():
    counter = FlakyCounter(fail_n=2)
    t0 = time.time()
    result = retry_with_backoff(counter, max_attempts=3, backoff=0.05)
    elapsed = time.time() - t0
    assert result == "ok"
    # 等待 backoff^1 + backoff^2 = 0.05 + 0.0025 ≈ 0.0525s
    assert elapsed >= 0.05  # 至少 0.05s
    assert elapsed < 1.0    # 不会过长
