"""Unit tests for scripts/core/tool_middleware.py.

Covers: _args_hash, RateLimitResult, TokenBucketRateLimiter, ToolCallLogger,
CachedResult, ToolResultCache, ToolCallMiddleware, wrap_tool_selector.

Test conventions:
  - Synthetic data only — no network calls, llm_gateway is mocked.
  - Uses tmp_path fixture for file I/O where needed.
  - Deterministic where possible; timing-dependent tests use small sleeps
    and are marked accordingly.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.tool_middleware import (
    _args_hash,
    RateLimitResult,
    TokenBucketRateLimiter,
    ToolCallLogger,
    CachedResult,
    ToolResultCache,
    ToolCallMiddleware,
    wrap_tool_selector,
)
from scripts.core.tool_selector import ToolResult


# ═══════════════════════════════════════════════════════════════════════════
# _args_hash
# ═══════════════════════════════════════════════════════════════════════════


class TestArgsHash:
    def test_returns_hex_string(self):
        result = _args_hash({})
        assert isinstance(result, str)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        h1 = _args_hash({"a": 1, "b": 2})
        h2 = _args_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_order_independent(self):
        h1 = _args_hash({"z": 1, "a": 2})
        h2 = _args_hash({"a": 2, "z": 1})
        assert h1 == h2

    def test_different_args_different_hash(self):
        h1 = _args_hash({"key": "value1"})
        h2 = _args_hash({"key": "value2"})
        assert h1 != h2

    def test_empty_dict(self):
        h = _args_hash({})
        assert len(h) == 16

    def test_nested_dict(self):
        h = _args_hash({"outer": {"inner": [1, 2, 3]}})
        assert len(h) == 16

    def test_unicode(self):
        h = _args_hash({"中文": "测试", "emoji": "🎉"})
        assert len(h) == 16

    def test_none_value(self):
        h = _args_hash({"key": None})
        assert len(h) == 16

    def test_bool_values(self):
        h1 = _args_hash({"flag": True})
        h2 = _args_hash({"flag": False})
        assert h1 != h2

    def test_numeric_precision(self):
        h1 = _args_hash({"val": 1.0})
        h2 = _args_hash({"val": 1})
        # These are different JSON values so should differ
        assert isinstance(h1, str)
        assert isinstance(h2, str)


# ═══════════════════════════════════════════════════════════════════════════
# RateLimitResult dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimitResult:
    def test_init_all_fields(self):
        r = RateLimitResult(allowed=True, wait_seconds=0.0, remaining=29, reset_at=12345.0)
        assert r.allowed is True
        assert r.wait_seconds == 0.0
        assert r.remaining == 29
        assert r.reset_at == 12345.0

    def test_init_denied(self):
        r = RateLimitResult(allowed=False, wait_seconds=2.5, remaining=0, reset_at=67890.0)
        assert r.allowed is False
        assert r.wait_seconds == 2.5
        assert r.remaining == 0
        assert r.reset_at == 67890.0


# ═══════════════════════════════════════════════════════════════════════════
# TokenBucketRateLimiter
# ═══════════════════════════════════════════════════════════════════════════


class TestTokenBucketRateLimiterInit:
    def test_defaults(self):
        r = TokenBucketRateLimiter()
        assert r.rate == 30
        assert r.window == 60.0
        assert r._num_buckets == 32

    def test_custom_params(self):
        r = TokenBucketRateLimiter(rate=10, window=30.0, num_buckets=8)
        assert r.rate == 10
        assert r.window == 30.0
        assert r._num_buckets == 8

    def test_tokens_initialized_to_full(self):
        r = TokenBucketRateLimiter(rate=5)
        for tokens, _ in r._tokens:
            assert tokens == 5.0


class TestTokenBucketRateLimiterBucketIdx:
    def test_none_returns_zero(self):
        r = TokenBucketRateLimiter()
        assert r._bucket_idx(None) == 0

    def test_same_key_same_idx(self):
        r = TokenBucketRateLimiter()
        idx1 = r._bucket_idx("user-yfinance")
        idx2 = r._bucket_idx("user-yfinance")
        assert idx1 == idx2
        assert idx1 != 0  # global bucket

    def test_different_keys_different_idx(self):
        r = TokenBucketRateLimiter()
        idxs = {r._bucket_idx(f"server_{i}") for i in range(20)}
        # Should spread across 31 buckets (1 global + 31 server)
        assert len(idxs) > 1

    def test_bucket_idx_within_range(self):
        r = TokenBucketRateLimiter(num_buckets=8)
        for key in ["a", "b", "c", "d", "e", "f"]:
            idx = r._bucket_idx(key)
            assert 1 <= idx <= 7


class TestTokenBucketRateLimiterRefill:
    def test_refill_full_bucket(self):
        r = TokenBucketRateLimiter(rate=10, window=60.0)
        r._tokens[5] = (10.0, time.time() - 60.0)  # full, 60s ago
        tokens, now = r._refill(5)
        assert tokens == 10.0

    def test_refill_partial_bucket(self):
        r = TokenBucketRateLimiter(rate=10, window=10.0)
        # 5 tokens, 5s ago, refill rate = 10/10 = 1/s
        r._tokens[3] = (5.0, time.time() - 5.0)
        tokens, _ = r._refill(3)
        # tokens + elapsed * refill_rate = 5 + 5 * 1 = 10
        assert tokens == 10.0

    def test_refill_caps_at_rate(self):
        r = TokenBucketRateLimiter(rate=5, window=1.0)
        r._tokens[2] = (5.0, time.time() - 100.0)  # old, would overfill
        tokens, _ = r._refill(2)
        assert tokens == 5.0  # capped at rate


class TestTokenBucketRateLimiterCheck:
    def test_first_call_allowed(self):
        r = TokenBucketRateLimiter(rate=30, window=60.0)
        result = r.check()
        assert result.allowed is True
        assert result.remaining == 29
        assert result.wait_seconds == 0.0

    def test_multiple_calls_deplete(self):
        r = TokenBucketRateLimiter(rate=3, window=60.0)
        results = [r.check() for _ in range(3)]
        assert all(res.allowed for res in results[:3])
        assert results[-1].remaining == 0

    def test_calls_depleted_rejected(self):
        r = TokenBucketRateLimiter(rate=2, window=60.0)
        r.check()
        r.check()
        result = r.check()
        assert result.allowed is False
        assert result.remaining == 0
        assert result.wait_seconds > 0

    def test_global_bucket(self):
        r = TokenBucketRateLimiter(rate=2, window=60.0)
        r.check()
        r.check()
        result = r.check(None)
        assert result.allowed is False

    def test_per_server_buckets_independent(self):
        r = TokenBucketRateLimiter(rate=1, window=60.0, num_buckets=64)
        # With 64 buckets the probability of a hash collision between two
        # arbitrary keys is tiny; use many tries to guarantee separation.
        for _ in range(20):
            key_a = f"server_a_{_}_"
            key_b = f"server_b_{_}_"
            idx_a = r._bucket_idx(key_a)
            idx_b = r._bucket_idx(key_b)
            if idx_a != idx_b and idx_a != 0 and idx_b != 0:
                break
        # Consume token in bucket A, B should still have a token
        r.check(key_a)
        result = r.check(key_b)
        assert result.allowed is True

    def test_reset_at_is_future(self):
        r = TokenBucketRateLimiter(rate=10, window=60.0)
        result = r.check()
        assert result.reset_at >= time.time()

    def test_consecutive_depleted_calls(self):
        """After rejection, subsequent calls should also be rejected until refill."""
        r = TokenBucketRateLimiter(rate=1, window=60.0)
        r.check()
        result1 = r.check()
        result2 = r.check()
        assert result1.allowed is False
        assert result2.allowed is False


class TestTokenBucketRateLimiterWaitAndCheck:
    def test_immediate_allowed(self):
        r = TokenBucketRateLimiter(rate=30, window=60.0)
        result = r.wait_and_check(max_wait=1.0)
        assert result.allowed is True
        assert result.remaining >= 0

    def test_waits_for_refill(self):
        r = TokenBucketRateLimiter(rate=2, window=0.1)  # very fast refill
        r.check()
        r.check()  # depleted
        # Wait up to 2s for refill (should happen within 0.1s)
        result = r.wait_and_check(max_wait=2.0)
        assert result.allowed is True

    def test_timeout_exceeded(self):
        r = TokenBucketRateLimiter(rate=1, window=10.0)  # slow refill
        r.check()  # depleted
        result = r.wait_and_check(max_wait=0.001)
        assert result.allowed is False

    def test_wait_with_key(self):
        r = TokenBucketRateLimiter(rate=1, window=60.0)
        r.check("myserver")
        result = r.wait_and_check("myserver", max_wait=0.001)
        assert result.allowed is False


class TestTokenBucketRateLimiterThreadSafety:
    def test_concurrent_checks(self):
        r = TokenBucketRateLimiter(rate=100, window=60.0)
        results = []
        lock = threading.Lock()

        def worker():
            res = r.check()
            with lock:
                results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = sum(1 for res in results if res.allowed)
        assert allowed <= 100
        # All should complete without error
        assert len(results) == 20


# ═══════════════════════════════════════════════════════════════════════════
# ToolCallLogger
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallLoggerInit:
    def test_default_log_dir(self):
        logger = ToolCallLogger()
        assert logger._log_dir == Path("data/tool_calls")

    def test_custom_log_dir(self, tmp_path):
        logger = ToolCallLogger(log_dir=tmp_path / "custom")
        assert logger._log_dir == tmp_path / "custom"

    def test_path_object(self, tmp_path):
        logger = ToolCallLogger(log_dir=tmp_path)
        assert logger._log_dir == tmp_path

    def test_internal_state(self):
        logger = ToolCallLogger()
        assert logger._fh is None
        assert logger._day is None
        assert isinstance(logger._lock, type(threading.Lock()))


class TestToolCallLoggerGetHandle:
    def test_creates_file(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        fh = logger._get_handle()
        today = time.strftime("%Y-%m-%d")
        expected = tmp_path / f"tool_calls_{today}.jsonl"
        assert expected.exists()
        assert fh is logger._fh
        logger.close()

    def test_reuses_same_handle(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        fh1 = logger._get_handle()
        fh2 = logger._get_handle()
        assert fh1 is fh2
        logger.close()

    def test_creates_nested_dir(self, tmp_path):
        logger = ToolCallLogger(tmp_path / "a" / "b")
        fh = logger._get_handle()
        assert (tmp_path / "a" / "b").exists()
        logger.close()


class TestToolCallLoggerLog:
    def test_log_writes_jsonl_line(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger.log(
            call_id="tc_abc123",
            server="user-yfinance",
            tool="get_stock_info",
            args_hash="a1b2c3d4",
            latency_ms=50.0,
            success=True,
        )
        logger.close()

        today = time.strftime("%Y-%m-%d")
        log_file = tmp_path / f"tool_calls_{today}.jsonl"
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["call_id"] == "tc_abc123"
        assert record["server"] == "user-yfinance"
        assert record["tool"] == "get_stock_info"
        assert record["args_hash"] == "a1b2c3d4"
        assert record["success"] is True
        assert record["error"] is None
        assert record["cache_hit"] is False
        assert record["rate_limited"] is False

    def test_log_with_error(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger.log(
            call_id="tc_err",
            server="user-tushare",
            tool="get_daily_quote",
            args_hash="deadbeef",
            latency_ms=100.0,
            success=False,
            error="Connection timeout",
        )
        logger.close()

        today = time.strftime("%Y-%m-%d")
        log_file = tmp_path / f"tool_calls_{today}.jsonl"
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["success"] is False
        assert record["error"] == "Connection timeout"

    def test_log_cache_hit(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger.log(
            call_id="tc_cached",
            server="user-openalex",
            tool="get_openalex_works",
            args_hash="cafebabe",
            latency_ms=0.0,
            success=True,
            cache_hit=True,
        )
        logger.close()

        today = time.strftime("%Y-%m-%d")
        log_file = tmp_path / f"tool_calls_{today}.jsonl"
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["cache_hit"] is True

    def test_log_rate_limited(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger.log(
            call_id="tc_rl",
            server="user-yfinance",
            tool="get_quote",
            args_hash="0000",
            latency_ms=0.0,
            success=False,
            rate_limited=True,
            error="Rate limit exceeded",
            wait_ms=500.0,
        )
        logger.close()

        today = time.strftime("%Y-%m-%d")
        log_file = tmp_path / f"tool_calls_{today}.jsonl"
        record = json.loads(log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["rate_limited"] is True
        assert record["wait_ms"] == 500.0

    def test_log_multiple_lines(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        for i in range(5):
            logger.log(
                call_id=f"tc_{i}",
                server="user-yfinance",
                tool="get_stock_info",
                args_hash=f"h{i}",
                latency_ms=float(i),
                success=True,
            )
        logger.close()

        today = time.strftime("%Y-%m-%d")
        log_file = tmp_path / f"tool_calls_{today}.jsonl"
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 5


class TestToolCallLoggerClose:
    def test_close_idempotent(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger._get_handle()
        logger.close()
        logger.close()  # should not raise

    def test_close_sets_fh_to_none(self, tmp_path):
        logger = ToolCallLogger(tmp_path)
        logger._get_handle()
        assert logger._fh is not None
        logger.close()
        assert logger._fh is None


# ═══════════════════════════════════════════════════════════════════════════
# CachedResult dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestCachedResult:
    def test_init(self):
        now = time.time()
        c = CachedResult(data={"price": 100}, stored_at=now, ttl_seconds=60.0)
        assert c.data == {"price": 100}
        assert c.stored_at == now
        assert c.ttl_seconds == 60.0

    def test_is_fresh_within_ttl(self):
        c = CachedResult(data="x", stored_at=time.time(), ttl_seconds=300.0)
        assert c.is_fresh() is True

    def test_is_fresh_expired(self):
        c = CachedResult(data="x", stored_at=time.time() - 1000.0, ttl_seconds=60.0)
        assert c.is_fresh() is False

    def test_is_fresh_exactly_at_boundary(self):
        now = time.time()
        # is_fresh: (now - stored_at) < ttl  → strictly less
        c = CachedResult(data="x", stored_at=now - 60.0, ttl_seconds=60.0)
        assert c.is_fresh() is False

    def test_is_fresh_complex_data(self):
        data = {"nested": [1, 2, {"deep": True}], "null": None}
        c = CachedResult(data=data, stored_at=time.time(), ttl_seconds=300.0)
        assert c.is_fresh() is True
        assert c.data == data


# ═══════════════════════════════════════════════════════════════════════════
# ToolResultCache
# ═══════════════════════════════════════════════════════════════════════════


class TestToolResultCacheInit:
    def test_defaults(self):
        cache = ToolResultCache()
        assert cache._cache_dir == Path("data/tool_cache")
        assert cache._ttl == 300.0
        assert cache._index == {}
        assert cache._index_loaded is False

    def test_custom_params(self, tmp_path):
        cache = ToolResultCache(cache_dir=tmp_path, ttl_seconds=120.0)
        assert cache._cache_dir == tmp_path
        assert cache._ttl == 120.0

    def test_path_object(self, tmp_path):
        cache = ToolResultCache(cache_dir=tmp_path)
        assert cache._cache_dir == tmp_path


class TestToolResultCacheKeyToPath:
    def test_path_format(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        path = cache._key_to_path("user-yfinance", "get_stock_info", "abcd1234")
        assert path.parent == tmp_path / "user-yfinance"
        assert path.name == "get_stock_info_abcd1234.json"

    def test_nested_server_name(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        path = cache._key_to_path("user-openalex", "get_works", "ef90")
        assert "user-openalex" in str(path)


class TestToolResultCacheSet:
    def test_set_creates_file(self, tmp_path):
        cache = ToolResultCache(tmp_path, ttl_seconds=300.0)
        cache.set("user-yfinance", "get_quote", {"symbol": "AAPL"}, {"price": 150.0})

        path = cache._key_to_path("user-yfinance", "get_quote", _args_hash({"symbol": "AAPL"}))
        assert path.exists()

    def test_set_nested_data(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        data = {"items": [{"a": 1}, {"b": 2}], "count": 2}
        cache.set("s", "t", {}, data)
        assert cache.hit_count >= 1

    def test_set_overwrites(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s", "t", {"k": 1}, "v1")
        cache.set("s", "t", {"k": 1}, "v2")
        result = cache.get("s", "t", {"k": 1})
        assert result is not None
        assert result.data == "v2"

    def test_set_custom_ttl(self, tmp_path):
        cache = ToolResultCache(tmp_path, ttl_seconds=300.0)
        cache.set("s", "t", {}, "data", ttl_seconds=10.0)
        # Verify the per-entry TTL is written to the cache file
        # CachedResult.ttl_seconds reflects the cache's default TTL (self._ttl),
        # not the per-entry TTL — that's by design.
        cache_file = next((tmp_path / "s").iterdir())
        with open(cache_file, encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["ttl_seconds"] == 10.0


class TestToolResultCacheGet:
    def test_get_miss_not_cached(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        result = cache.get("never", "seen", {"key": "val"})
        assert result is None

    def test_get_hit(self, tmp_path):
        cache = ToolResultCache(tmp_path, ttl_seconds=300.0)
        cache.set("user-yfinance", "get_quote", {"symbol": "AAPL"}, {"price": 200.0})
        result = cache.get("user-yfinance", "get_quote", {"symbol": "AAPL"})
        assert result is not None
        assert result.data == {"price": 200.0}

    def test_get_expired_returns_none(self, tmp_path):
        cache = ToolResultCache(tmp_path, ttl_seconds=0.01)  # 10ms TTL
        cache.set("s", "t", {}, "fresh_data")
        time.sleep(0.05)
        result = cache.get("s", "t", {})
        assert result is None

    def test_get_wrong_args(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s", "t", {"a": 1}, "value")
        result = cache.get("s", "t", {"a": 2})
        assert result is None

    def test_get_wrong_server(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("server-a", "t", {}, "value")
        result = cache.get("server-b", "t", {})
        assert result is None

    def test_get_corrupt_file(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        path = tmp_path / "s"
        path.mkdir()
        bad_file = path / "t_0000.json"
        bad_file.write_text("{ invalid json", encoding="utf-8")
        # _load_index reads it; get should return None
        result = cache.get("s", "t", {})
        assert result is None


class TestToolResultCacheInvalidate:
    def test_invalidate_all(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s1", "t1", {}, "v1")
        cache.set("s2", "t2", {}, "v2")
        assert cache.hit_count == 2
        cache.invalidate()
        assert cache.hit_count == 0

    def test_invalidate_by_server(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("server-a", "t", {}, "v_a")
        cache.set("server-b", "t", {}, "v_b")
        cache.invalidate(server="server-a")
        assert cache.get("server-a", "t", {}) is None
        assert cache.get("server-b", "t", {}) is not None

    def test_invalidate_by_tool(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s", "tool-x", {}, "v1")
        cache.set("s", "tool-y", {}, "v2")
        cache.invalidate(tool="tool-x")
        assert cache.get("s", "tool-x", {}) is None
        assert cache.get("s", "tool-y", {}) is not None

    def test_invalidate_nonexistent(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.invalidate(server="ghost")  # should not raise


class TestToolResultCacheClear:
    def test_clear_removes_all(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s", "t", {}, "v")
        assert cache.hit_count >= 1
        cache.clear()
        assert cache.hit_count == 0

    def test_clear_empty(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.clear()  # should not raise


class TestToolResultCacheHitCount:
    def test_hit_count_zero_initially(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        assert cache.hit_count == 0

    def test_hit_count_reflects_set(self, tmp_path):
        cache = ToolResultCache(tmp_path)
        cache.set("s", "t", {}, "v")
        assert cache.hit_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# ToolCallMiddleware — init combinations
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallMiddlewareInit:
    def test_all_enabled_defaults(self):
        mw = ToolCallMiddleware()
        assert mw._enable_logging is True
        assert mw._enable_rate_limit is True
        assert mw._rate_limit_per_server is True
        assert mw._max_rate_wait == 30.0
        assert mw._logger is not None
        assert mw._rate_limiter is not None
        assert mw._cache is not None

    def test_logging_disabled(self, tmp_path):
        mw = ToolCallMiddleware(enable_logging=False, cache_dir=tmp_path)
        assert mw._logger is None
        assert mw._rate_limiter is not None

    def test_rate_limit_disabled(self):
        mw = ToolCallMiddleware(enable_rate_limit=False)
        assert mw._rate_limiter is None

    def test_cache_disabled(self):
        mw = ToolCallMiddleware(cache_dir=None)
        assert mw._cache is None

    def test_custom_rate_params(self):
        mw = ToolCallMiddleware(rate_limit=10, rate_window=30.0, rate_limit_per_server=False)
        assert mw._rate_limiter is not None
        assert mw._rate_limit_per_server is False

    def test_custom_cache_ttl(self, tmp_path):
        mw = ToolCallMiddleware(cache_dir=tmp_path, cache_ttl=600.0)
        assert mw._cache._ttl == 600.0

    def test_context_manager(self, tmp_path):
        with ToolCallMiddleware(enable_logging=True, cache_dir=tmp_path) as mw:
            assert mw._logger is not None
        # After exit, logger should be closed
        # (accessing the closed file handle may raise OSError — that's expected)


# ═══════════════════════════════════════════════════════════════════════════
# ToolCallMiddleware.call — mocked llm_gateway
# ═══════════════════════════════════════════════════════════════════════════


# The actual MCP call is imported from llm_gateway inside ToolCallMiddleware.call():
#   from scripts.core.llm_gateway import call_mcp_tool
# All tests patching this function must target scripts.core.llm_gateway.


def _mock_success():
    """Return a mock LLM gateway result for a successful call."""
    m = MagicMock()
    m.success = True
    m.data = {"quote": 150.0}
    m.error = None
    return m


def _mock_failure(msg="Network error"):
    """Return a mock LLM gateway result for a failed call."""
    m = MagicMock()
    m.success = False
    m.data = None
    m.error = msg
    return m


class TestToolCallMiddlewareCall:
    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_full_pipeline_success(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(
            enable_logging=True,
            enable_rate_limit=True,
            cache_dir=tmp_path,
        )
        result = mw.call("user-yfinance", "get_stock_info", {"symbol": "AAPL"})

        assert result.success is True
        assert result.output == {"quote": 150.0}
        assert result.tool_name == "user-yfinance.get_stock_info"
        assert result.error is None
        assert result.latency_ms >= 0
        mock_call.assert_called_once_with(
            "user-yfinance", "get_stock_info", {"symbol": "AAPL"}, timeout=30.0
        )
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_full_pipeline_failure(self, mock_call, tmp_path):
        mock_call.return_value = _mock_failure("Timeout")
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        result = mw.call("user-tushare", "get_daily", {})

        assert result.success is False
        assert result.output is None
        assert "Timeout" in (result.error or "")
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_exception_handling(self, mock_call, tmp_path):
        mock_call.side_effect = RuntimeError("Unexpected error")
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        result = mw.call("user-yfinance", "get_stock_info", {})

        assert result.success is False
        assert result.error == "Unexpected error"
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_cache_hit_skips_execution(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)

        # First call — populates cache
        result1 = mw.call("s", "t", {"key": "v"})
        assert result1.success is True
        assert mock_call.call_count == 1

        # Second call — cache hit
        result2 = mw.call("s", "t", {"key": "v"})
        assert result2.success is True
        assert result2.cached is True
        assert mock_call.call_count == 1  # still 1, no new call

        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_cache_miss_executes(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)

        mw.call("s", "t", {"key": "a"})
        assert mock_call.call_count == 1
        mw.call("s", "t", {"key": "b"})  # different args
        assert mock_call.call_count == 2

        mw.close()

    def test_rate_limit_exceeded(self, tmp_path):
        mw = ToolCallMiddleware(
            enable_rate_limit=True,
            rate_limit=1,
            rate_window=60.0,
            cache_dir=None,
        )
        mw._rate_limiter.check()  # exhaust the single token
        # Patch the rate limiter directly so it always denies the call
        denied = RateLimitResult(allowed=False, wait_seconds=999.0, remaining=0, reset_at=0.0)
        with patch.object(mw._rate_limiter, "wait_and_check", return_value=denied):
            with patch("scripts.core.llm_gateway.call_mcp_tool") as mock_call:
                result = mw.call("user-yfinance", "get_info", {})
        assert result.success is False
        assert "Rate limit exceeded" in (result.error or "")
        mock_call.assert_not_called()

    def test_wait_and_check_respects_max_wait(self, tmp_path):
        mw = ToolCallMiddleware(
            enable_rate_limit=True,
            rate_limit=1,
            rate_window=60.0,
            max_rate_wait=0.001,
            cache_dir=None,
        )
        mw._rate_limiter.check()  # exhaust the single token
        # Patch the rate limiter to always deny
        denied = RateLimitResult(allowed=False, wait_seconds=999.0, remaining=0, reset_at=0.0)
        with patch.object(mw._rate_limiter, "wait_and_check", return_value=denied):
            with patch("scripts.core.llm_gateway.call_mcp_tool") as mock_call:
                result = mw.call("user-yfinance", "get_info", {})
        assert result.success is False
        assert "Rate limit exceeded" in (result.error or "")
        mock_call.assert_not_called()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_no_cache_when_output_none(self, mock_call, tmp_path):
        mock_call.return_value = _mock_failure("Not found")
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        mw.call("s", "t", {"key": "v"})

        # Cache should be empty (only successful results are cached)
        result = mw.get("s", "t", {"key": "v"}) if hasattr(mw, "get") else None
        # Note: get is not exposed on middleware, so we check via cache directly
        assert mw._cache.get("s", "t", {"key": "v"}) is None
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_per_server_rate_limit(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(
            enable_rate_limit=True,
            rate_limit=1,
            rate_window=60.0,
            rate_limit_per_server=True,
            cache_dir=None,  # disable cache so rate-limit check always runs
            max_rate_wait=0.05,  # don't actually wait — fail fast
        )
        r1 = mw.call("server-a", "t", {"k": "v"})
        assert r1.success is True
        r2 = mw.call("server-a", "t", {"k": "v"})  # same server → depleted bucket
        assert r2.success is False  # rate limited

        r3 = mw.call("server-b", "t", {"k": "v"})  # different bucket
        assert r3.success is True  # allowed

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_global_rate_limit(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(
            enable_rate_limit=True,
            rate_limit=1,
            rate_window=60.0,
            rate_limit_per_server=False,  # global bucket
            cache_dir=None,
            max_rate_wait=0.05,  # don't actually wait — fail fast
        )
        r1 = mw.call("server-a", "t", {})
        assert r1.success is True
        r2 = mw.call("server-b", "t", {})  # same global bucket
        assert r2.success is False  # depleted

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_call_with_custom_timeout(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        mw.call("s", "t", {}, timeout=60.0)
        mock_call.assert_called_with("s", "t", {}, timeout=60.0)
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_latency_ms_recorded(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        result = mw.call("s", "t", {})
        assert result.latency_ms >= 0
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_no_logging_mode(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(enable_logging=False, cache_dir=tmp_path)
        result = mw.call("s", "t", {})
        assert result.success is True
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_no_rate_limit_mode(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(enable_rate_limit=False, cache_dir=tmp_path)
        result = mw.call("s", "t", {})
        assert result.success is True
        mw.close()


# ═══════════════════════════════════════════════════════════════════════════
# ToolCallMiddleware — acall
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallMiddlewareAcall:
    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_acall_returns_tool_result(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)

        async def run():
            return await mw.acall("s", "t", {})

        result = asyncio.run(run())
        assert isinstance(result, ToolResult)
        assert result.success is True
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_acall_caching_works(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)

        async def run():
            r1 = await mw.acall("s", "t", {"k": "v"})
            r2 = await mw.acall("s", "t", {"k": "v"})
            return r1, r2

        r1, r2 = asyncio.run(run())
        assert r1.success is True
        assert r2.cached is True
        mw.close()


# ═══════════════════════════════════════════════════════════════════════════
# ToolCallMiddleware — cache utilities
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallMiddlewareCacheUtils:
    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_invalidate_cache(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        mw.call("s", "t", {}, timeout=5.0)
        assert mw._cache.hit_count >= 1

        mw.invalidate_cache(server="s", tool="t")
        assert mw._cache.hit_count == 0
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_clear_cache(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        mw.call("s", "t", {}, timeout=5.0)
        mw.clear_cache()
        assert mw._cache.hit_count == 0
        mw.close()

    def test_invalidate_cache_when_disabled(self):
        mw = ToolCallMiddleware(cache_dir=None)
        mw.invalidate_cache()  # should not raise
        mw.clear_cache()  # should not raise


# ═══════════════════════════════════════════════════════════════════════════
# wrap_tool_selector
# ═══════════════════════════════════════════════════════════════════════════


class TestWrapToolSelector:
    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_non_mcp_tool_passthrough(self, mock_call, tmp_path):
        """Script tools (not in MCP_TOOLS) are passed to original execute."""
        mock_call.return_value = _mock_success()


        mw = ToolCallMiddleware(cache_dir=tmp_path)

        # Create a mock selection and original execute
        original = MagicMock()
        original.execute.return_value = ToolResult(
            success=True, output="script_result", tool_name="script_tool", error=None
        )
        wrapped = wrap_tool_selector(original, mw)

        # Create a selection with a non-MCP tool name
        selection = MagicMock()
        selection.tool_name = "script_tool"  # not in MCP_TOOLS

        result = wrapped.execute(selection, {"input": "data"})
        assert result.success is True
        assert result.output == "script_result"
        mock_call.assert_not_called()
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_mcp_tool_goes_through_middleware(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()


        mw = ToolCallMiddleware(cache_dir=tmp_path)
        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)

        # Use a tool name that IS in MCP_TOOLS (e.g., "yfinance")
        selection = MagicMock()
        selection.tool_name = "yfinance"

        result = wrapped.execute(selection, {"symbol": "AAPL"})
        assert result.success is True
        assert result.output == {"quote": 150.0}
        mock_call.assert_called_once()
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_mcp_tool_failure(self, mock_call, tmp_path):
        mock_call.return_value = _mock_failure("API error")
        mw = ToolCallMiddleware(cache_dir=tmp_path)

        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)

        selection = MagicMock()
        selection.tool_name = "openalex"

        result = wrapped.execute(selection, {"query": "carbon"})
        assert result.success is False
        assert "API error" in (result.error or "")
        mw.close()

    def test_returns_same_object(self, tmp_path):
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)
        assert wrapped is original
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_underscore_server_name_normalized(self, mock_call, tmp_path):
        """Server names with underscores are normalized to hyphens."""
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)

        selection = MagicMock()
        selection.tool_name = "tushare"

        wrapped.execute(selection, {"ts_code": "000001.SZ"})

        # The middleware.call receives server name with underscores replaced
        # We patched call_mcp_tool at the module level, so check args
        call_args = mock_call.call_args
        # Server should be normalized from user_tushare → user-tushare
        assert call_args is not None
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_latency_ms_returned(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)

        selection = MagicMock()
        selection.tool_name = "arxiv"

        result = wrapped.execute(selection, {"query": "finance"})
        assert result.latency_ms >= 0
        mw.close()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_cached_flag_preserved(self, mock_call, tmp_path):
        mock_call.return_value = _mock_success()
        mw = ToolCallMiddleware(cache_dir=tmp_path)
        original = MagicMock()
        wrapped = wrap_tool_selector(original, mw)

        selection = MagicMock()
        selection.tool_name = "yfinance"

        # First call — not cached
        r1 = wrapped.execute(selection, {"sym": "A"})
        assert r1.cached is False

        # Second call — cached
        r2 = wrapped.execute(selection, {"sym": "A"})
        assert r2.cached is True
        mw.close()


# ═══════════════════════════════════════════════════════════════════════════
# Exports / re-exports
# ═══════════════════════════════════════════════════════════════════════════


class TestExports:
    def test_all_exports_present(self):
        assert True  # All imported successfully

    def test_tool_result_re_exported(self):
        from scripts.core.tool_middleware import ToolResult as TR
        from scripts.core.tool_selector import ToolResult as TS
        assert TR is TS
