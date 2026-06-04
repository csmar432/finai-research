"""MCP Tool Call Middleware — request logging, rate limiting, and result caching.

Provides a pluggable middleware layer for MCP tool calls that:

1. **Request Logging** — Writes every tool call to `data/tool_calls/tool_calls_YYYY-MM-DD.jsonl`
   using a hash of the arguments (no plain-text secrets).

2. **Rate Limiting** — Token-bucket rate limiter (per-server or global) with
   configurable calls-per-window. Thread-safe.

3. **Result Caching** — TTL-based cache keyed by `(server, tool, args_hash)`.
   Stored as JSON files in `data/tool_cache/`. Cache hits are flagged in logs.

4. **Integration** — `wrap_tool_selector()` returns a ToolSelector that intercepts
   `execute()` calls through the middleware. Can also be used standalone via
   `MiddlewareToolCaller`.

Usage
-----
    # Standalone
    from scripts.core.tool_middleware import ToolCallMiddleware

    mw = ToolCallMiddleware(
        enable_logging=True,
        enable_rate_limit=True,
        rate_limit=30,
        rate_window=60,
        cache_dir=Path("data/tool_cache"),
    )
    result = await mw.acall("user-yfinance", "get_stock_info", {"symbol": "AAPL"})

    # With ToolSelector
    from scripts.core.tool_middleware import wrap_tool_selector
    from scripts.core.tool_selector import ToolSelector

    selector = ToolSelector(memory)
    wrapped = wrap_tool_selector(selector, middleware=mw)
    result = wrapped.execute(selection, inputs)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Data Classes ────────────────────────────────────────────────────────────
# Re-export ToolResult so callers don't need an extra import
from scripts.core.tool_selector import ToolResult

# ─── Hashing ──────────────────────────────────────────────────────────────────


def _args_hash(arguments: dict) -> str:
    """
    Compute a deterministic SHA-256 hash of a dict's JSON representation.

    Uses sorted JSON serialization so argument order does not affect the hash.
    """
    canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ─── Rate Limiter ─────────────────────────────────────────────────────────────


@dataclass
class RateLimitResult:
    """Result of a rate-limit check."""
    allowed: bool
    wait_seconds: float
    remaining: int
    reset_at: float  # Unix timestamp when the bucket refills to full


class TokenBucketRateLimiter:
    """
    Thread-safe token-bucket rate limiter.

    Each call consumes one token. Tokens refill at `rate / window` per second.
    If the bucket is empty, requests are rejected until enough tokens accumulate.

    Supports both per-server buckets and a global bucket.

    Parameters
    ----------
    rate : int
        Maximum number of calls allowed per window. Default 30.
    window : float
        Time window in seconds. Default 60.
    num_buckets : int
        Number of individual server buckets + 1 global bucket.
        bucket[0] = global; bucket[i] = server i-1. Default 32.
    """

    def __init__(
        self,
        rate: int = 30,
        window: float = 60.0,
        num_buckets: int = 32,
    ):
        self.rate = rate
        self.window = window
        self._num_buckets = num_buckets
        # tokens[bucket_idx] = (available_tokens, last_refill_ts)
        self._tokens: list[tuple[float, float]] = [
            (float(rate), time.time()) for _ in range(num_buckets)
        ]
        self._lock = threading.RLock()

    def _bucket_idx(self, key: str | None) -> int:
        """Map a key (server name) to a bucket index. None = global bucket 0."""
        if key is None:
            return 0
        # Simple hash to distribute server names across bucket slots
        return (hash(key) % (self._num_buckets - 1)) + 1

    def _refill(self, idx: int) -> tuple[float, float]:
        """Refill tokens for a bucket based on elapsed time. Returns (tokens, now)."""
        tokens, last_refill = self._tokens[idx]
        now = time.time()
        elapsed = now - last_refill
        refill_per_sec = self.rate / self.window
        new_tokens = min(self.rate, tokens + elapsed * refill_per_sec)
        return new_tokens, now

    def check(self, key: str | None = None) -> RateLimitResult:
        """
        Check whether a call is allowed under the rate limit.

        Parameters
        ----------
        key : str | None
            Server/tool key for per-server limiting. None uses the global bucket.

        Returns
        -------
        RateLimitResult
            Whether the call is allowed, how long to wait if not, and remaining tokens.
        """
        with self._lock:
            idx = self._bucket_idx(key)
            tokens, last_refill = self._tokens[idx]
            now = time.time()
            elapsed = now - last_refill

            # Refill
            refill_per_sec = self.rate / self.window
            tokens = min(self.rate, tokens + elapsed * refill_per_sec)

            if tokens >= 1.0:
                tokens -= 1.0
                self._tokens[idx] = (tokens, now)
                # Estimate when bucket is refilled to full
                deficit = self.rate - tokens
                reset_at = now + (deficit / refill_per_sec) if deficit > 0 else now
                return RateLimitResult(
                    allowed=True,
                    wait_seconds=0.0,
                    remaining=int(tokens),
                    reset_at=reset_at,
                )
            else:
                # How long until next token?
                wait = (1.0 - tokens) / refill_per_sec
                self._tokens[idx] = (tokens, now)
                reset_at = now + wait * self.rate
                return RateLimitResult(
                    allowed=False,
                    wait_seconds=wait,
                    remaining=0,
                    reset_at=reset_at,
                )

    def wait_and_check(self, key: str | None = None, max_wait: float = 30.0) -> RateLimitResult:
        """
        Block until a call is allowed, or return RateLimitResult(allowed=False) if
        max_wait is exceeded.

        Parameters
        ----------
        key : str | None
            Server/tool key for per-server limiting.
        max_wait : float
            Maximum seconds to wait. Default 30.

        Returns
        -------
        RateLimitResult
            Whether the call was allowed and how long was actually waited.
        """
        start = time.time()
        while True:
            result = self.check(key)
            if result.allowed:
                return result
            elapsed = time.time() - start
            if elapsed >= max_wait:
                return RateLimitResult(
                    allowed=False,
                    wait_seconds=max_wait,
                    remaining=0,
                    reset_at=start + result.reset_at - time.time() + max_wait,
                )
            # Sleep until the next token would be available
            sleep_time = min(result.wait_seconds, max_wait - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)


# ─── Tool Call Logger ─────────────────────────────────────────────────────────


class ToolCallLogger:
    """
    Structured JSONL logger for MCP tool calls.

    Writes one JSON object per line to `data/tool_calls/tool_calls_YYYY-MM-DD.jsonl`.
    Each entry contains sanitized metadata (args_hash instead of raw args) to
    avoid logging sensitive data in plain text.

    Thread-safe.
    """

    def __init__(self, log_dir: Path | str | None = None):
        if log_dir is None:
            log_dir = Path("data/tool_calls")
        else:
            log_dir = Path(log_dir)
        self._log_dir = log_dir
        self._lock = threading.Lock()
        self._day: str | None = None
        self._fh: object | None = None  # file handle

    def _get_handle(self):
        """Get or create the daily log file handle."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._fh is None or self._day != today:
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
            self._log_dir.mkdir(parents=True, exist_ok=True)
            path = self._log_dir / f"tool_calls_{today}.jsonl"
            self._fh = open(path, "a", encoding="utf-8")
            self._day = today
        return self._fh

    def log(
        self,
        call_id: str,
        server: str,
        tool: str,
        args_hash: str,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        cache_hit: bool = False,
        rate_limited: bool = False,
        wait_ms: float = 0.0,
    ):
        """
        Append a tool-call record to the daily log file.

        Parameters
        ----------
        call_id : str
            Unique identifier for this call.
        server : str
            MCP server name.
        tool : str
            Tool name on that server.
        args_hash : str
            SHA-256 prefix of the serialized arguments.
        latency_ms : float
            Time spent executing the tool (excluding queue/wait time).
        success : bool
            Whether the tool call succeeded.
        error : str | None
            Error message if the call failed.
        cache_hit : bool
            Whether the result came from cache.
        rate_limited : bool
            Whether the call was rejected due to rate limiting.
        wait_ms : float
            Time spent waiting for rate-limit clearance (ms).
        """
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "call_id": call_id,
            "server": server,
            "tool": tool,
            "args_hash": args_hash,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "error": error,
            "cache_hit": cache_hit,
            "rate_limited": rate_limited,
            "wait_ms": round(wait_ms, 2),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)

        with self._lock:
            try:
                fh = self._get_handle()
                fh.write(line + "\n")
                fh.flush()
            except Exception:
                # Swallow file I/O errors — don't let logging crash tool calls
                pass

    def close(self):
        """Close the log file handle."""
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
                self._day = None


# ─── Result Cache ─────────────────────────────────────────────────────────────


@dataclass
class CachedResult:
    """A cached tool-call result."""
    data: Any
    stored_at: float
    ttl_seconds: float

    def is_fresh(self) -> bool:
        return (time.time() - self.stored_at) < self.ttl_seconds


class ToolResultCache:
    """
    TTL-based file cache for tool call results.

    Cache key: `{server}/{tool}/{args_hash}.json`
    Each entry stores the serialized result and a timestamp.
    Idempotent by design — callers should only cache GET-like queries.

    Thread-safe.
    """

    def __init__(self, cache_dir: Path | str | None = None, ttl_seconds: float = 300.0):
        """
        Parameters
        ----------
        cache_dir : Path | str | None
            Directory for cache files. Default `data/tool_cache`.
        ttl_seconds : float
            Default time-to-live for cached entries. Default 300s (5 min).
        """
        if cache_dir is None:
            cache_dir = Path("data/tool_cache")
        self._cache_dir = Path(cache_dir)
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        # In-memory index: key → (stored_at, file_path) for fast freshness checks
        self._index: dict[str, tuple[float, Path]] = {}
        self._index_loaded = False

    def _key_to_path(self, server: str, tool: str, args_hash: str) -> Path:
        """Convert a cache key to a file path."""
        server_dir = self._cache_dir / server
        return server_dir / f"{tool}_{args_hash}.json"

    def _load_index(self):
        """Build an in-memory index of existing cache entries."""
        if self._index_loaded:
            return
        with self._lock:
            if self._index_loaded:
                return
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                for server_dir in self._cache_dir.iterdir():
                    if not server_dir.is_dir():
                        continue
                    for f in server_dir.iterdir():
                        if f.suffix != ".json":
                            continue
                        # Parse server/tool from path
                        try:
                            name = f.stem  # "toolname_hash"
                            parts = name.rsplit("_", 1)
                            if len(parts) == 2:
                                tool, args_hash = parts
                                stored_at = f.stat().st_mtime
                                key = f"{server_dir.name}/{tool}/{args_hash}"
                                self._index[key] = (stored_at, f)
                        except Exception:
                            continue
            except Exception:
                pass
            self._index_loaded = True

    def get(self, server: str, tool: str, arguments: dict) -> CachedResult | None:
        """
        Retrieve a cached result if it exists and is fresh.

        Parameters
        ----------
        server : str
            MCP server name.
        tool : str
            Tool name.
        arguments : dict
            Tool arguments (used to compute the cache key).

        Returns
        -------
        CachedResult | None
            The cached result if fresh, else None.
        """
        args_hash = _args_hash(arguments)
        key = f"{server}/{tool}/{args_hash}"

        self._load_index()
        with self._lock:
            entry = self._index.get(key)
            if entry is None:
                return None
            stored_at, path = entry

            # Check freshness
            if (time.time() - stored_at) >= self._ttl:
                # Expired — remove from index
                self._index.pop(key, None)
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None

            # Load and return
            try:
                with open(path, encoding="utf-8") as f:
                    payload = json.load(f)
                return CachedResult(
                    data=payload.get("data"),
                    stored_at=stored_at,
                    ttl_seconds=self._ttl,
                )
            except Exception:
                self._index.pop(key, None)
                return None

    def set(
        self,
        server: str,
        tool: str,
        arguments: dict,
        data: Any,
        ttl_seconds: float | None = None,
    ):
        """
        Store a result in the cache.

        Parameters
        ----------
        server : str
            MCP server name.
        tool : str
            Tool name.
        arguments : dict
            Tool arguments (used to compute the cache key).
        data : Any
            Result data to cache.
        ttl_seconds : float | None
            Override the default TTL for this entry.
        """
        args_hash = _args_hash(arguments)
        path = self._key_to_path(server, tool, args_hash)
        key = f"{server}/{tool}/{args_hash}"
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl

        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            server_dir = path.parent
            server_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "server": server,
                "tool": tool,
                "args_hash": args_hash,
                "data": data,
                "stored_at": time.time(),
                "ttl_seconds": ttl,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, default=str)
        except Exception:
            # Cache write failures are non-fatal
            pass

        with self._lock:
            self._index[key] = (time.time(), path)

    def invalidate(self, server: str | None = None, tool: str | None = None):
        """
        Invalidate cache entries matching the given pattern.

        Parameters
        ----------
        server : str | None
            If provided, only invalidate entries for this server.
        tool : str | None
            If provided, only invalidate entries for this tool.
        """
        self._load_index()
        with self._lock:
            to_remove = []
            for key, (_, path) in self._index.items():
                parts = key.split("/")
                if len(parts) != 3:
                    continue
                s, t, _ = parts
                if server is not None and s != server:
                    continue
                if tool is not None and t != tool:
                    continue
                to_remove.append(key)
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            for k in to_remove:
                self._index.pop(k, None)

    def clear(self):
        """Clear all cache entries."""
        self._load_index()
        with self._lock:
            for _, path in list(self._index.values()):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            self._index.clear()

    @property
    def hit_count(self) -> int:
        """Approximate number of entries in the cache index."""
        self._load_index()
        with self._lock:
            return len(self._index)


# ─── Middleware ───────────────────────────────────────────────────────────────


class ToolCallMiddleware:
    """
    Middleware layer for MCP tool calls — logging, rate limiting, and caching.

    All three features are independently optional.

    Parameters
    ----------
    enable_logging : bool
        Whether to log tool calls to `data/tool_calls/`. Default True.
    enable_rate_limit : bool
        Whether to enforce rate limiting. Default True.
    rate_limit : int
        Maximum calls per rate window. Default 30.
    rate_window : float
        Rate-limit window in seconds. Default 60.
    cache_dir : Path | str | None
        Directory for result cache. Default `data/tool_cache`.
        Set to None to disable caching.
    cache_ttl : float
        Default TTL for cached results in seconds. Default 300 (5 min).
    rate_limit_per_server : bool
        If True, rate limiting is per-server. If False, a single global bucket
        is used. Default True.
    max_rate_wait : float
        Maximum seconds to wait for rate-limit clearance. Default 30.
    """

    def __init__(
        self,
        enable_logging: bool = True,
        enable_rate_limit: bool = True,
        rate_limit: int = 30,
        rate_window: float = 60.0,
        cache_dir: Path | str | None = "data/tool_cache",
        cache_ttl: float = 300.0,
        rate_limit_per_server: bool = True,
        max_rate_wait: float = 30.0,
    ):
        self._enable_logging = enable_logging
        self._enable_rate_limit = enable_rate_limit
        self._rate_limit_per_server = rate_limit_per_server
        self._max_rate_wait = max_rate_wait

        # Logger
        self._logger = ToolCallLogger() if enable_logging else None

        # Rate limiter
        if enable_rate_limit:
            self._rate_limiter = TokenBucketRateLimiter(
                rate=rate_limit,
                window=rate_window,
            )
        else:
            self._rate_limiter = None

        # Cache
        if cache_dir is not None:
            self._cache = ToolResultCache(cache_dir=cache_dir, ttl_seconds=cache_ttl)
        else:
            self._cache = None

    # ── Sync call ───────────────────────────────────────────────────────────

    def call(
        self,
        server: str,
        tool: str,
        arguments: dict,
        timeout: float = 30.0,
    ) -> ToolResult:
        """
        Execute a tool call through the middleware pipeline (synchronous).

        Pipeline:
        1. Check cache → return if fresh
        2. Check / wait for rate limit
        3. Log pre-call
        4. Execute via `llm_gateway.call_mcp_tool`
        5. Log post-call + cache result

        Parameters
        ----------
        server : str
            MCP server name (e.g. "user-yfinance").
        tool : str
            Tool name on that server.
        arguments : dict
            Keyword arguments for the tool.
        timeout : float
            Tool call timeout in seconds. Default 30.

        Returns
        -------
        ToolResult
            Structured result matching `tool_selector.ToolResult`.
        """
        call_id = f"tc_{uuid.uuid4().hex[:8]}"
        args_hash = _args_hash(arguments)
        rate_key = server if self._rate_limit_per_server else None

        # ── 1. Cache check ────────────────────────────────────────────────────
        if self._cache is not None:
            cached = self._cache.get(server, tool, arguments)
            if cached is not None:
                if self._logger is not None:
                    self._logger.log(
                        call_id=call_id,
                        server=server,
                        tool=tool,
                        args_hash=args_hash,
                        latency_ms=0.0,
                        success=True,
                        cache_hit=True,
                    )
                return ToolResult(
                    success=True,
                    output=cached.data,
                    tool_name=f"{server}.{tool}",
                    error=None,
                    latency_ms=0.0,
                    cached=True,
                )

        # ── 2. Rate limit check ───────────────────────────────────────────────
        wait_ms = 0.0
        if self._rate_limiter is not None:
            if self._enable_rate_limit:
                limit_result = self._rate_limiter.wait_and_check(
                    key=rate_key,
                    max_wait=self._max_rate_wait,
                )
                if not limit_result.allowed:
                    if self._logger is not None:
                        self._logger.log(
                            call_id=call_id,
                            server=server,
                            tool=tool,
                            args_hash=args_hash,
                            latency_ms=0.0,
                            success=False,
                            error=f"Rate limit exceeded. Retry after {limit_result.wait_seconds:.1f}s",
                            rate_limited=True,
                        )
                    return ToolResult(
                        success=False,
                        output=None,
                        tool_name=f"{server}.{tool}",
                        error=f"Rate limit exceeded. Retry after {limit_result.wait_seconds:.1f}s",
                        latency_ms=0.0,
                        cached=False,
                    )
                wait_ms = limit_result.wait_seconds * 1000

        # ── 3 & 4. Execute ────────────────────────────────────────────────────
        start = time.perf_counter()
        error_msg: str | None = None
        output: Any = None

        try:
            from scripts.core.llm_gateway import call_mcp_tool
            mcp_result = call_mcp_tool(server, tool, arguments, timeout=timeout)
            if mcp_result.success:
                output = mcp_result.data
                error_msg = None
            else:
                output = None
                error_msg = mcp_result.error
        except Exception as exc:
            output = None
            error_msg = str(exc)

        latency_ms = (time.perf_counter() - start) * 1000

        # ── 5. Cache + log ────────────────────────────────────────────────────
        if self._cache is not None and output is not None and error_msg is None:
            # Only cache successful results
            self._cache.set(server, tool, arguments, output)

        if self._logger is not None:
            self._logger.log(
                call_id=call_id,
                server=server,
                tool=tool,
                args_hash=args_hash,
                latency_ms=latency_ms,
                success=(error_msg is None),
                error=error_msg,
                cache_hit=False,
                wait_ms=wait_ms,
            )

        return ToolResult(
            success=(error_msg is None),
            output=output,
            tool_name=f"{server}.{tool}",
            error=error_msg,
            latency_ms=latency_ms,
            cached=False,
        )

    # ── Async call ──────────────────────────────────────────────────────────

    async def acall(
        self,
        server: str,
        tool: str,
        arguments: dict,
        timeout: float = 30.0,
    ) -> ToolResult:
        """
        Async version of `call()`. Runs the synchronous pipeline in a thread pool.

        Parameters
        ----------
        server : str
            MCP server name.
        tool : str
            Tool name.
        arguments : dict
            Tool arguments.
        timeout : float
            Timeout in seconds.

        Returns
        -------
        ToolResult
            Structured result.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.call,
            server,
            tool,
            arguments,
            timeout,
        )

    # ── Utilities ───────────────────────────────────────────────────────────

    def invalidate_cache(self, server: str | None = None, tool: str | None = None):
        """Invalidate cache entries. Pass server/tool to invalidate selectively."""
        if self._cache is not None:
            self._cache.invalidate(server=server, tool=tool)

    def clear_cache(self):
        """Clear all cached tool results."""
        if self._cache is not None:
            self._cache.clear()

    def close(self):
        """Flush and close all handles."""
        if self._logger is not None:
            self._logger.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── ToolSelector Integration ──────────────────────────────────────────────────


def wrap_tool_selector(
    original: ToolSelector,
    middleware: ToolCallMiddleware,
) -> ToolSelector:
    """
    Wrap a ToolSelector so that its `execute()` method routes through the middleware.

    The returned selector is the same object, mutated in-place.

    The middleware intercepts MCP tool calls (identified by `tool_name in MCP_TOOLS`)
    and passes them through its call pipeline. Script tools are passed through
    directly.

    Parameters
    ----------
    original : ToolSelector
        The ToolSelector instance to wrap.
    middleware : ToolCallMiddleware
        The middleware instance to use.

    Returns
    -------
    ToolSelector
        The same object, with `execute()` intercepted.

    Example
    -------
        from scripts.core.tool_middleware import ToolCallMiddleware, wrap_tool_selector
        from scripts.core.tool_selector import ToolSelector

        mw = ToolCallMiddleware(enable_logging=True, enable_rate_limit=True)
        selector = ToolSelector(memory)
        wrapped = wrap_tool_selector(selector, mw)

        # All execute() calls now go through the middleware
        result = wrapped.execute(selection, inputs)
    """
    # Import here to avoid circular imports

    _original_execute = original.execute  # type: ignore[attr-defined]

    def _wrapped_execute(selection, inputs):
        tool_name = selection.tool_name

        # Only intercept MCP tools — script tools go direct
        from scripts.core.tool_selector import ToolSelector as TS
        if tool_name not in TS.MCP_TOOLS:  # type: ignore[attr-defined]
            return _original_execute(selection, inputs)

        # Map tool_name to server + tool via the selector's map
        actual_tool_name, server_name = TS.MCP_TOOL_SERVER_MAP.get(  # type: ignore[attr-defined]
            tool_name, (tool_name, tool_name)
        )

        # Normalize server name (replace underscores with hyphens for MCP config)
        server = server_name.replace("_", "-")

        # Build arguments from inputs
        arguments = dict(inputs)

        # Delegate to middleware
        mw_result = middleware.call(server, actual_tool_name, arguments)

        # Convert MiddlewareResult → ToolResult
        return ToolResult(
            success=mw_result.success,
            output=mw_result.output,
            tool_name=tool_name,
            error=mw_result.error,
            latency_ms=mw_result.latency_ms,
            cached=mw_result.cached,
        )

    original.execute = _wrapped_execute  # type: ignore[assignment]
    return original


# ─── Exports ──────────────────────────────────────────────────────────────────

__all__ = [
    # Classes
    "ToolCallMiddleware",
    "TokenBucketRateLimiter",
    "ToolCallLogger",
    "ToolResultCache",
    "CachedResult",
    "RateLimitResult",
    # Utility
    "wrap_tool_selector",
    "_args_hash",
    # Re-export
    "ToolResult",
]
