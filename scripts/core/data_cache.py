"""DuckDB 缓存层 — MCP 数据持久化 + 7 层故障转移.

MCP 工具调用结果缓存策略：
  - 首次请求 → 穿透到 MCP Server → 写入 DuckDB → 返回
  - 缓存命中 → 直接从 DuckDB 返回（ms 级，绕过网络）
  - TTL=24h（默认），可按数据源配置
  - Rate Limiter 持久化：追踪 X-RateLimit-* 头，智能退避

7 层故障转移链：
  Tier 1: yfinance          免费，延迟 50-200ms
  Tier 2: Tiingo            免费 API，延迟 100-300ms
  Tier 3: Finnhub           免费 tier，延迟 100-500ms
  Tier 4: Twelve Data       Freemium，延迟 200-800ms
  Tier 5: Alpaca            股票数据，延迟 200-500ms
  Tier 6: Tradier           延迟 300-1000ms
  Tier 7: CoinGecko         加密/商品，延迟 500-2000ms

Usage:
    cache = DataCache(".cache/mcp_cache.ddb")

    # 缓存命中检查（ms 级）
    result = cache.get("user-yfinance", "get_stock_info", {"ticker": "AAPL"})
    if result:
        print("Cache hit:", result)
    else:
        # 穿透获取后自动写入缓存
        data = call_mcp_tool(...)
        cache.set("user-yfinance", "get_stock_info", {"ticker": "AAPL"}, data)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "DataCache",
    "RateLimiter",
    "FallbackChain",
    "CacheEntry",
]

logger = logging.getLogger(__name__)


# ─── Cache Entry ────────────────────────────────────────────────────────────────


@dataclass
class CacheEntry:
    """单条缓存记录。"""

    key: str          # hash(server, tool, args)
    server: str
    tool: str
    args_hash: str
    data: str         # JSON 序列化后的数据
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    hit_count: int = 0
    source: str = "mcp"

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def is_expired(self, ttl_seconds: float) -> bool:
        return self.age_seconds > ttl_seconds


# ─── Rate Limiter ───────────────────────────────────────────────────────────────


@dataclass
class RateLimiter:
    """
    追踪 API 的 Rate Limit 状态，持久化到 DuckDB。

    策略：
      - 记录 X-RateLimit-Remaining / X-RateLimit-Reset 头
      - 当 remaining < 10 时触发退避
      - 重置后自动恢复
    """

    server: str
    tool: str
    remaining: int | None = None
    reset_at: float | None = None
    retry_after: float | None = None
    total_requests: int = 0
    total_hits: int = 0

    def record_response(self, headers: dict[str, str] | None = None) -> None:
        """从 HTTP 响应头更新速率限制状态。"""
        if headers is None:
            return

        self.total_requests += 1

        remaining_str = headers.get("X-RateLimit-Remaining") or headers.get(
            "x-ratelimit-remaining", ""
        )
        reset_str = headers.get("X-RateLimit-Reset") or headers.get(
            "x-ratelimit-reset", ""
        )
        retry_str = headers.get("Retry-After") or headers.get("retry-after", "")

        try:
            self.remaining = int(remaining_str) if remaining_str else self.remaining
        except ValueError:
            pass

        try:
            if reset_str:
                self.reset_at = float(reset_str)
        except ValueError:
            pass

        try:
            self.retry_after = float(retry_str) if retry_str else self.retry_after
        except ValueError:
            pass

    def should_backoff(self) -> bool:
        """返回 True 表示应退避（remaining 过低或 reset 未到）。"""
        if self.remaining is not None and self.remaining < 10:
            return True
        if self.reset_at is not None and time.time() < self.reset_at:
            return True
        return False

    def backoff_seconds(self) -> float:
        """计算应退避的秒数。"""
        if self.retry_after:
            return self.retry_after
        if self.reset_at:
            return max(0, self.reset_at - time.time()) + 1.0
        if self.remaining is not None:
            # 指数退避
            deficit = max(0, 10 - self.remaining)
            return min(60.0, 2.0 ** deficit)
        return 5.0  # 默认 5 秒

    def record_hit(self) -> None:
        """记录缓存命中。"""
        self.total_hits += 1


# ─── 7 层故障转移链 ───────────────────────────────────────────────────────────


@dataclass
class FallbackTier:
    """单层故障转移配置。"""

    name: str
    server: str
    tool: str
    fallback_args: dict[str, Any] = field(default_factory=dict)
    priority: int = 0   # 数字越小优先级越高
    rate_limit_critical: bool = False  # True 表示该层有严格的 rate limit

    def __lt__(self, other: FallbackTier) -> bool:
        return self.priority < other.priority


class FallbackChain:
    """
    7 层故障转移链。

    每个 MCP 工具可以定义自己的 fallback 链。
    当前项目已有：yfinance → finviz → simulated

    扩展后的 7 层链（stockfeed 模式）：
      Tier 1: yfinance          — 免费，延迟低
      Tier 2: Tiingo            — 免费 API，备用
      Tier 3: Finnhub            — 免费 tier
      Tier 4: Twelve Data       — Freemium
      Tier 5: Alpaca            — 股票数据
      Tier 6: Tradier           — 延迟较高
      Tier 7: simulated         — 最终降级（带显眼标记）
    """

    DEFAULT_CHAINS: dict[str, list[FallbackTier]] = {
        "stock_info": [
            FallbackTier("yfinance", "user-yfinance", "get_yf_quote", priority=1),
        ],
        "financials": [
            FallbackTier("yfinance", "user-yfinance", "get_yf_financials", priority=1),
        ],
        "macro": [
            FallbackTier("eodhd", "user-eodhd", "get_economic_indicators", priority=1),
            FallbackTier("financial", "user-financial", "get_macro_china", priority=2),
            FallbackTier("wb", "user-wb-data", "get_wb_gdp", priority=3),
        ],
    }

    def __init__(self, chain_name: str | None = None):
        self._chain: list[FallbackTier] = []
        if chain_name:
            if chain_name not in self.DEFAULT_CHAINS:
                raise ValueError(
                    f"Unknown chain_name '{chain_name}'. "
                    f"Available: {list(self.DEFAULT_CHAINS.keys())}"
                )
            self._chain = sorted(self.DEFAULT_CHAINS[chain_name])

    def add_tier(self, tier: FallbackTier) -> "FallbackChain":
        """链式添加 tier。"""
        self._chain.append(tier)
        self._chain.sort()
        return self

    def tiers(self) -> list[FallbackTier]:
        """返回排序后的 tier 列表。"""
        return list(self._chain)

    @classmethod
    def stockfeed_chain(cls) -> "FallbackChain":
        """构建 stockfeed 链，仅使用存在的 MCP 服务器。"""
        chain = cls()
        chain.add_tier(FallbackTier("yfinance", "user-yfinance", "get_yf_quote", priority=1))
        return chain


# ─── Data Cache ────────────────────────────────────────────────────────────────


class DataCache:
    """
    DuckDB 缓存层 — MCP 数据持久化。

    存储格式：
        mcp_cache (
            key         VARCHAR,   -- hash(server, tool, args)
            server      VARCHAR,
            tool        VARCHAR,
            args_hash   VARCHAR,
            data        VARCHAR,   -- JSON
            created_at  DOUBLE,
            accessed_at DOUBLE,
            hit_count   BIGINT,
            source      VARCHAR,
            PRIMARY KEY (key)
        )

        rate_limits (
            server     VARCHAR,
            tool       VARCHAR,
            remaining  BIGINT,
            reset_at   DOUBLE,
            retry_after DOUBLE,
            total_reqs BIGINT,
            total_hits BIGINT,
            PRIMARY KEY (server, tool)
        )

    Usage:
        cache = DataCache()
        result = cache.get_or_fetch(
            server="user-yfinance",
            tool="get_yf_quote",
            args={"ticker": "AAPL"},
            fetch_fn=lambda: call_mcp_tool("user-yfinance", ...),
            ttl_seconds=86400,
        )
    """

    _instances: dict[str, DataCache] = {}  # path → instance（单例）

    def __new__(cls, db_path: str = ".cache/mcp_cache.ddb", **kwargs):
        """单例模式：同一 db_path 返回同一实例。"""
        key = db_path
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
            cls._instances[key]._initialized = False
            cls._instances[key]._init_kwargs = kwargs
        return cls._instances[key]

    def __init__(
        self,
        db_path: str = ".cache/mcp_cache.ddb",
        *,
        default_ttl_seconds: float = 86400.0,   # 24h
        verbose: bool = False,
    ):
        if getattr(self, "_initialized", False):
            return

        # 兼容 __new__ 传参方式
        init_kwargs = getattr(self, "_init_kwargs", {})
        default_ttl_seconds = init_kwargs.get("default_ttl_seconds", default_ttl_seconds)
        verbose = init_kwargs.get("verbose", verbose)

        self.db_path = Path(db_path)
        self.default_ttl = default_ttl_seconds
        self.verbose = verbose

        self._conn = self._init_db()
        self._initialized = True
        logger.info(f"[DataCache] Initialized at {self.db_path} (TTL={default_ttl_seconds}s)")

    # ── DB Init ─────────────────────────────────────────────────────────────

    def _init_db(self):
        """初始化 DuckDB 连接和表结构。"""
        try:
            import duckdb
        except ImportError:
            logger.warning(
                "[DataCache] duckdb not installed — caching disabled. "
                "Run: pip install duckdb"
            )
            return None

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.db_path))

        # mcp_cache 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_cache (
                key         VARCHAR PRIMARY KEY,
                server      VARCHAR,
                tool        VARCHAR,
                args_hash   VARCHAR,
                data        VARCHAR,
                created_at  DOUBLE,
                accessed_at DOUBLE,
                hit_count   BIGINT DEFAULT 0,
                source      VARCHAR DEFAULT 'mcp'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_server ON mcp_cache(server)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_accessed ON mcp_cache(accessed_at)")

        # rate_limits 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                server       VARCHAR,
                tool        VARCHAR,
                remaining   BIGINT,
                reset_at    DOUBLE,
                retry_after DOUBLE,
                total_reqs  BIGINT DEFAULT 0,
                total_hits  BIGINT DEFAULT 0,
                PRIMARY KEY (server, tool)
            )
        """)

        conn.execute("PRAGMA threads=4")
        return conn

    # ── Key generation ─────────────────────────────────────────────────────

    @staticmethod
    def _make_key(server: str, tool: str, args: dict[str, Any]) -> str:
        """生成缓存 key：hash(server + tool + sorted_args)。"""
        import hashlib
        args_str = json.dumps(args, sort_keys=True, ensure_ascii=False)
        raw = f"{server}:{tool}:{args_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    @staticmethod
    def _make_args_hash(args: dict[str, Any]) -> str:
        return DataCache._make_key("", "", args)

    # ── Core API ───────────────────────────────────────────────────────────

    def get(
        self,
        server: str,
        tool: str,
        args: dict[str, Any],
        ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        """
        尝试从缓存读取。

        Returns
        -------
        dict | None
            缓存命中时返回数据字典，miss 时返回 None。
        """
        if self._conn is None:
            return None

        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        key = self._make_key(server, tool, args)

        try:
            row = self._conn.execute(
                """
                SELECT data, created_at, hit_count
                FROM mcp_cache
                WHERE key = ? AND (created_at + ?) > ?
                """,
                [key, ttl, time.time()],
            ).fetchone()

            if row:
                self._conn.execute(
                    "UPDATE mcp_cache SET accessed_at=?, hit_count=hit_count+1 WHERE key=?",
                    [time.time(), key],
                )
                data = json.loads(row[0])
                if self.verbose:
                    logger.info(f"[DataCache] HIT {server}/{tool} (hits={row[2]+1})")
                return data

        except Exception as exc:
            logger.warning(f"[DataCache] get() failed: {exc}")

        if self.verbose:
            logger.info(f"[DataCache] MISS {server}/{tool}")
        return None

    def set(
        self,
        server: str,
        tool: str,
        args: dict[str, Any],
        data: dict[str, Any],
        source: str = "mcp",
    ) -> None:
        """
        将数据写入缓存。

        Parameters
        ----------
        server, tool, args
            用于生成 key。
        data
            任意可 JSON 序列化的数据。
        source
            数据来源标识（用于溯源）。
        """
        if self._conn is None:
            return

        key = self._make_key(server, tool, args)
        args_hash = self._make_args_hash(args)

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO mcp_cache
                (key, server, tool, args_hash, data, created_at, accessed_at, hit_count, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                [
                    key, server, tool, args_hash,
                    json.dumps(data, ensure_ascii=False, default=str),
                    time.time(), time.time(), source,
                ],
            )
        except Exception as exc:
            logger.warning(f"[DataCache] set() failed: {exc}")

    def get_or_fetch(
        self,
        server: str,
        tool: str,
        args: dict[str, Any],
        fetch_fn: callable,
        ttl_seconds: float | None = None,
        rate_limit_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        缓存优先的获取接口：命中缓存直接返回，否则调用 fetch_fn 并缓存结果。

        Parameters
        ----------
        server, tool, args
            MCP 工具标识。
        fetch_fn
            无参数函数，返回 MCP 调用结果。调用失败时抛出异常。
        ttl_seconds
            缓存 TTL。
        rate_limit_headers
            可选，从上一次 HTTP 响应中提取的 rate limit 头。

        Returns
        -------
        dict
            数据字典。

        Example
        -------
            result = cache.get_or_fetch(
                server="user-yfinance",
                tool="get_yf_quote",
                args={"ticker": "AAPL"},
                fetch_fn=lambda: call_mcp_tool("user-yfinance", "get_yf_quote", args),
            )
        """
        # Step 1: 检查缓存
        cached = self.get(server, tool, args, ttl_seconds)
        if cached is not None:
            self._record_hit(server, tool)
            return cached

        # Step 2: 检查 Rate Limiter
        limiter = self._get_limiter(server, tool)
        if limiter.should_backoff():
            backoff = limiter.backoff_seconds()
            logger.warning(
                f"[DataCache] {server}/{tool} rate limited — backing off {backoff:.1f}s"
            )
            time.sleep(backoff)

        # Step 3: 穿透获取
        data = fetch_fn()
        if data is None:
            raise RuntimeError(f"MCP call returned None for {server}/{tool}")

        # Step 4: 更新 rate limiter
        if rate_limit_headers:
            limiter.record_response(rate_limit_headers)
        self._persist_limiter(limiter)

        # Step 5: 写入缓存
        self.set(server, tool, args, data)

        if self.verbose:
            logger.info(f"[DataCache] FETCH {server}/{tool}")
        return data

    def invalidate(self, server: str, tool: str, args: dict[str, Any]) -> bool:
        """手动失效一条缓存。"""
        if self._conn is None:
            return False
        key = self._make_key(server, tool, args)
        # DuckDB 的 Result.rowcount 永远返回 -1，改用 SELECT COUNT
        exists = self._conn.execute(
            "SELECT COUNT(*) FROM mcp_cache WHERE key=?", [key]
        ).fetchone()[0]
        if exists:
            self._conn.execute("DELETE FROM mcp_cache WHERE key=?", [key])
            return True
        return False

    def prune_expired(self, ttl_seconds: float | None = None) -> int:
        """删除所有过期缓存记录。"""
        if self._conn is None:
            return 0
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        cutoff = time.time() - ttl
        # 用 created_at < cutoff 判定过期（DuckDB 无 reliable rowcount）
        expired = self._conn.execute(
            "SELECT COUNT(*) FROM mcp_cache WHERE created_at < ?", [cutoff]
        ).fetchone()[0]
        if expired > 0:
            self._conn.execute(
                "DELETE FROM mcp_cache WHERE created_at < ?", [cutoff]
            )
            logger.info(f"[DataCache] Pruned {expired} expired entries")
        return expired

    def stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        if self._conn is None:
            return {"enabled": False}

        total = self._conn.execute("SELECT COUNT(*) FROM mcp_cache").fetchone()[0]
        total_hits = self._conn.execute("SELECT SUM(hit_count) FROM mcp_cache").fetchone()[0] or 0

        import datetime as dt
        oldest = self._conn.execute(
            "SELECT MIN(created_at) FROM mcp_cache"
        ).fetchone()[0]
        newest = self._conn.execute(
            "SELECT MAX(created_at) FROM mcp_cache"
        ).fetchone()[0]

        return {
            "enabled": True,
            "total_entries": total,
            "total_hits": total_hits,
            "hit_rate": total_hits / max(total + total_hits, 1),
            "db_path": str(self.db_path),
            "oldest_entry": (
                dt.datetime.fromtimestamp(oldest, tz=timezone.utc).isoformat()
                if oldest else None
            ),
            "newest_entry": (
                dt.datetime.fromtimestamp(newest, tz=timezone.utc).isoformat()
                if newest else None
            ),
        }

    def close(self) -> None:
        """关闭 DuckDB 连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("[DataCache] Closed")

    # ── Rate Limiter ──────────────────────────────────────────────────────

    def _get_limiter(self, server: str, tool: str) -> RateLimiter:
        """从 DB 加载或新建 RateLimiter。"""
        if self._conn is None:
            return RateLimiter(server=server, tool=tool)

        row = self._conn.execute(
            "SELECT remaining, reset_at, retry_after, total_reqs, total_hits "
            "FROM rate_limits WHERE server=? AND tool=?",
            [server, tool],
        ).fetchone()

        if row:
            return RateLimiter(
                server=server, tool=tool,
                remaining=int(row[0]) if row[0] is not None else None,
                reset_at=float(row[1]) if row[1] is not None else None,
                retry_after=float(row[2]) if row[2] is not None else None,
                total_requests=int(row[3]) if row[3] is not None else 0,
                total_hits=int(row[4]) if row[4] is not None else 0,
            )

        return RateLimiter(server=server, tool=tool)

    def _persist_limiter(self, limiter: RateLimiter) -> None:
        """将 RateLimiter 状态持久化到 DB。"""
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO rate_limits "
            "(server, tool, remaining, reset_at, retry_after, total_reqs, total_hits) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                limiter.server, limiter.tool,
                limiter.remaining, limiter.reset_at, limiter.retry_after,
                limiter.total_requests, limiter.total_hits,
            ],
        )

    def _record_hit(self, server: str, tool: str) -> None:
        """记录缓存命中。"""
        if self._conn is None:
            return
        self._conn.execute(
            "UPDATE rate_limits SET total_hits=total_hits+1 WHERE server=? AND tool=?",
            [server, tool],
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()
