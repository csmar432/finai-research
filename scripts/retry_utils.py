"""
Retry utilities — 可选 tenacity wrapper

提供：
  - retry_api_call: 装饰器，包装 API 调用，失败后自动重试
  - retry_with_backoff: 自定义重试

用法：
    from scripts.retry_utils import retry_api_call
    @retry_api_call(max_attempts=3, backoff=2.0)
    def fetch_tushare_data(...):
        ...

设计原则：
  - tenacity 不在 core deps（在 requirements-optional.txt）
  - 如未安装，回退为 no-op（保持向后兼容）
  - 默认 3 次尝试，指数退避 1.0s, 2.0s, 4.0s
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入 tenacity（可选）
try:
    from tenacity import (
        before_sleep_log,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )
    from tenacity import (
        retry as _tenacity_retry,
    )
    _TENACITY_AVAILABLE = True
except ImportError:
    _TENACITY_AVAILABLE = False


def _no_retry_decorator(*args, **kwargs):
    """tenacity 不可用时的占位装饰器。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*fargs, **fkwargs):
            return func(*fargs, **fkwargs)
        return wrapper
    # 支持 @retry_api_call 和 @retry_api_call() 两种调用
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

# 默认重试异常: 网络/超时/连接错误
DEFAULT_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
    IOError,
)


def retry_api_call(
    max_attempts: int = 3,
    backoff: float = 2.0,
    max_wait: float = 30.0,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = DEFAULT_RETRY_EXCEPTIONS,
):
    """
    装饰器：API 调用失败后自动重试（指数退避）。

    Args:
        max_attempts: 最大尝试次数（含首次）。
        backoff: 指数退避基数（秒），第 N 次等待 backoff^(N-1) 秒。
        max_wait: 每次最大等待秒数。
        exceptions: 触发重试的异常类型。

    Returns:
        装饰后的函数。

    Note:
        如果 tenacity 未安装（requirements-optional.txt），降级为 no-op
        （不重试，但保证 import 不报错）。可通过 `pip install tenacity` 启用。
    """
    if not _TENACITY_AVAILABLE:
        logger.debug(
            "tenacity not installed; retry disabled. "
            "Install via: pip install tenacity"
        )
        return _no_retry_decorator()

    if isinstance(exceptions, type):
        exceptions = (exceptions,)

    def decorator(func: Callable) -> Callable:
        @_tenacity_retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=backoff, max=max_wait),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        return wrapper
    return decorator


def retry_with_backoff(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: type[BaseException] | tuple[type[BaseException], ...] = DEFAULT_RETRY_EXCEPTIONS,
    **kwargs: Any,
) -> Any:
    """
    函数式重试：不用装饰器，直接调用。

    Args:
        func: 要重试的函数。
        *args: 透传位置参数。
        max_attempts: 最大尝试次数。
        backoff: 指数退避基数。
        exceptions: 触发重试的异常类型。
        **kwargs: 透传关键字参数。

    Returns:
        func 的返回值。

    Raises:
        最后一次失败的异常。
    """
    if isinstance(exceptions, type):
        exceptions = (exceptions,)

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            if attempt >= max_attempts:
                logger.error(
                    "%s failed after %d attempts: %s",
                    getattr(func, "__name__", "function"),
                    attempt,
                    e,
                )
                raise
            wait = min(backoff ** attempt, 30.0)
            logger.warning(
                "%s attempt %d failed (%s); retrying in %.1fs",
                getattr(func, "__name__", "function"),
                attempt,
                e,
                wait,
            )
            time.sleep(wait)
    # 不可达，保持类型检查
    if last_exc:
        raise last_exc
    raise RuntimeError("retry_with_backoff: unexpected end of loop")


# ---------------------------------------------------------------------------
# 便捷预设
# ---------------------------------------------------------------------------

retry_tushare = retry_api_call(
    max_attempts=3,
    backoff=2.0,
    exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
        ValueError,  # Tushare 偶发 token 错误
    ),
)
"""Tushare API 重试预设（3 次，2s 指数退避）"""


retry_yfinance = retry_api_call(
    max_attempts=3,
    backoff=1.5,
    exceptions=(ConnectionError, TimeoutError, OSError),
)
"""yfinance API 重试预设（3 次，1.5s 指数退避）"""


retry_macro = retry_api_call(
    max_attempts=4,
    backoff=2.0,
    exceptions=(ConnectionError, TimeoutError, OSError),
)
"""宏观数据 API 重试预设（4 次，2s 指数退避，更激进）"""


__all__ = [
    "retry_api_call",
    "retry_with_backoff",
    "retry_tushare",
    "retry_yfinance",
    "retry_macro",
    "DEFAULT_RETRY_EXCEPTIONS",
]
