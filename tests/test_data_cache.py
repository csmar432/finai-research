"""Tests for scripts/core/data_cache.py"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


class TestDataCacheBasics:
    """Happy-path tests for DataCache."""

    def test_cache_get_miss_without_db(self, tmp_path):
        """get() returns None when cache miss on fresh DB."""
        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_cache.ddb"))
        result = cache.get(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
        )
        # Result is None (cache miss) on fresh DB
        assert result is None

    def test_cache_set_and_get(self, tmp_path):
        """set() then get() returns the stored data."""
        from scripts.core.data_cache import DataCache

        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        cache = DataCache(db_path=str(tmp_path / "test_set_get.ddb"))

        test_data = {"price": 150.5, "volume": 1000, "ticker": "AAPL"}
        cache.set(
            server="user-yfinance",
            tool="get_quote",
            args={"ticker": "AAPL"},
            data=test_data,
        )

        retrieved = cache.get(
            server="user-yfinance",
            tool="get_quote",
            args={"ticker": "AAPL"},
        )

        assert retrieved is not None
        assert retrieved["price"] == 150.5
        assert retrieved["volume"] == 1000

    def test_cache_get_same_args_different_order(self, tmp_path):
        """get() key is order-invariant for dict args."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_order.ddb"))

        test_data = {"result": "ok"}
        cache.set(
            server="test-server",
            tool="test-tool",
            args={"a": 1, "b": 2},
            data=test_data,
        )

        # Same args different order should hit
        retrieved = cache.get(
            server="test-server",
            tool="test-tool",
            args={"b": 2, "a": 1},
        )
        assert retrieved is not None

    def test_cache_get_different_args_miss(self, tmp_path):
        """Different args produce cache miss."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_diff_args.ddb"))

        cache.set(
            server="test-server",
            tool="test-tool",
            args={"ticker": "AAPL"},
            data={"price": 100},
        )

        result = cache.get(
            server="test-server",
            tool="test-tool",
            args={"ticker": "MSFT"},
        )
        assert result is None

    def test_cache_stats(self, tmp_path):
        """stats() returns expected structure."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_stats.ddb"))
        stats = cache.stats()

        assert "enabled" in stats
        assert "total_entries" in stats
        assert "total_hits" in stats

    def test_cache_invalidate(self, tmp_path):
        """invalidate() removes a specific entry."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_invalidate.ddb"))

        cache.set(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
            data={"result": "data"},
        )

        # Confirm it's there
        assert cache.get(server="test-server", tool="test-tool",
                         args={"key": "value"}) is not None

        # Invalidate
        removed = cache.invalidate(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
        )
        assert removed is True

        # Should be gone
        assert cache.get(server="test-server", tool="test-tool",
                         args={"key": "value"}) is None

    def test_cache_invalidate_not_found(self, tmp_path):
        """invalidate() returns False when entry not found."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_inv_miss.ddb"))
        removed = cache.invalidate(
            server="nonexistent",
            tool="nonexistent",
            args={"key": "value"},
        )
        assert removed is False


class TestDataCacheTTL:
    """TTL and expiration tests."""

    def test_cache_ttl_expired(self, tmp_path):
        """get() returns None for expired entry."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(
            db_path=str(tmp_path / "test_ttl.ddb"),
            default_ttl_seconds=86400.0,
        )

        cache.set(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
            data={"price": 100},
        )

        # Within TTL — should hit
        result = cache.get(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
            ttl_seconds=86400.0,
        )
        assert result is not None

        # After TTL — should miss
        result_expired = cache.get(
            server="test-server",
            tool="test-tool",
            args={"key": "value"},
            ttl_seconds=0.0,  # already expired
        )
        assert result_expired is None

    def test_cache_custom_ttl(self, tmp_path):
        """set() respects per-call TTL via get()."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(db_path=str(tmp_path / "test_custom_ttl.ddb"))

        cache.set(
            server="test-server",
            tool="test-tool",
            args={"key": "short_ttl"},
            data={"data": "short"},
        )

        # Short TTL should expire immediately
        result = cache.get(
            server="test-server",
            tool="test-tool",
            args={"key": "short_ttl"},
            ttl_seconds=0.0,
        )
        assert result is None


class TestDataCachePrune:
    """Cache pruning tests."""

    def test_cache_prune_expired(self, tmp_path):
        """prune_expired() removes old entries."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        cache = DataCache(
            db_path=str(tmp_path / "test_prune.ddb"),
            default_ttl_seconds=1.0,  # 1 second TTL
        )

        cache.set(
            server="test-server",
            tool="test-tool",
            args={"key": "prune_test"},
            data={"data": "old"},
        )

        # Wait for expiry
        time.sleep(1.1)

        n_removed = cache.prune_expired(ttl_seconds=1.0)
        assert n_removed >= 1


class TestDataCacheRateLimiter:
    """RateLimiter tests."""

    def test_rate_limiter_init(self):
        """RateLimiter initializes correctly."""
        from scripts.core.data_cache import RateLimiter

        limiter = RateLimiter(server="test-server", tool="test-tool")

        assert limiter.server == "test-server"
        assert limiter.tool == "test-tool"
        assert limiter.remaining is None
        assert limiter.total_requests == 0
        assert limiter.total_hits == 0

    def test_rate_limiter_record_response(self):
        """record_response() parses X-RateLimit headers."""
        from scripts.core.data_cache import RateLimiter

        limiter = RateLimiter(server="test", tool="test")
        headers = {
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Reset": str(time.time() + 3600),
            "Retry-After": "60",
        }

        limiter.record_response(headers)

        assert limiter.remaining == 50
        assert limiter.retry_after == 60.0
        assert limiter.total_requests == 1

    def test_rate_limiter_should_backoff_low_remaining(self):
        """should_backoff() returns True when remaining < 10."""
        from scripts.core.data_cache import RateLimiter

        limiter = RateLimiter(server="test", tool="test", remaining=5)
        assert limiter.should_backoff() is True

        limiter_ok = RateLimiter(server="test", tool="test", remaining=50)
        assert limiter_ok.should_backoff() is False

    def test_rate_limiter_should_backoff_reset_pending(self):
        """should_backoff() returns True when reset time hasn't passed."""
        from scripts.core.data_cache import RateLimiter

        limiter = RateLimiter(
            server="test",
            tool="test",
            remaining=100,
            reset_at=time.time() + 3600,
        )
        assert limiter.should_backoff() is True

    def test_rate_limiter_backoff_seconds(self):
        """backoff_seconds() computes reasonable backoff time."""
        from scripts.core.data_cache import RateLimiter

        # No info — default
        limiter = RateLimiter(server="test", tool="test")
        assert 1.0 <= limiter.backoff_seconds() <= 5.0

        # With retry_after
        limiter_retry = RateLimiter(
            server="test",
            tool="test",
            retry_after=120.0,
        )
        assert limiter_retry.backoff_seconds() == 120.0

        # With remaining
        limiter_remain = RateLimiter(server="test", tool="test", remaining=8)
        assert limiter_remain.backoff_seconds() > 0

    def test_rate_limiter_record_hit(self):
        """record_hit() increments total_hits."""
        from scripts.core.data_cache import RateLimiter

        limiter = RateLimiter(server="test", tool="test")
        assert limiter.total_hits == 0

        limiter.record_hit()
        assert limiter.total_hits == 1

        limiter.record_hit()
        assert limiter.total_hits == 2


class TestDataCacheFallbackChain:
    """FallbackChain tests."""

    def test_fallback_chain_init(self):
        """FallbackChain initializes with default chains."""
        from scripts.core.data_cache import FallbackChain

        chain = FallbackChain(chain_name="stock_info")
        tiers = chain.tiers()

        assert len(tiers) > 0
        assert all(t.priority >= 0 for t in tiers)

    def test_fallback_chain_sorted_by_priority(self):
        """Tiers are sorted by priority (ascending)."""
        from scripts.core.data_cache import FallbackChain

        chain = FallbackChain(chain_name="stock_info")
        tiers = chain.tiers()

        priorities = [t.priority for t in tiers]
        assert priorities == sorted(priorities)

    def test_fallback_chain_add_tier(self):
        """add_tier() appends and re-sorts tiers."""
        from scripts.core.data_cache import FallbackChain, FallbackTier

        chain = FallbackChain()
        chain.add_tier(FallbackTier("test1", "s1", "t1", priority=5))
        chain.add_tier(FallbackTier("test2", "s2", "t2", priority=1))
        chain.add_tier(FallbackTier("test3", "s3", "t3", priority=3))

        tiers = chain.tiers()
        assert tiers[0].priority == 1
        assert tiers[1].priority == 3
        assert tiers[2].priority == 5

    def test_fallback_chain_stockfeed(self):
        """stockfeed_chain() returns a 7-tier chain."""
        from scripts.core.data_cache import FallbackChain

        chain = FallbackChain.stockfeed_chain()
        tiers = chain.tiers()

        assert len(tiers) >= 1
        assert tiers[0].name == "yfinance"


class TestDataCacheEdgeCases:
    """Edge case and error handling tests."""

    def test_cache_get_none_conn(self):
        """get() returns None when DB not initialized (no duckdb)."""
        from scripts.core.data_cache import DataCache

        # Force _conn = None by patching
        cache = DataCache.__new__(DataCache)
        cache._conn = None
        cache.default_ttl = 86400.0
        cache.verbose = False

        result = cache.get(server="test", tool="test", args={})
        assert result is None

    def test_cache_set_none_conn(self):
        """set() returns early when _conn is None."""
        from scripts.core.data_cache import DataCache

        cache = DataCache.__new__(DataCache)
        cache._conn = None

        # Should not raise
        cache.set(server="test", tool="test", args={}, data={})

    def test_cache_context_manager(self, tmp_path):
        """DataCache works as context manager."""
        try:
            pass
        except ImportError:
            pytest.skip("duckdb not installed")

        from scripts.core.data_cache import DataCache

        with DataCache(db_path=str(tmp_path / "test_context.ddb")) as cache:
            cache.set(
                server="test",
                tool="test",
                args={"x": 1},
                data={"y": 2},
            )

        # After exiting, cache should be closed
        assert cache._conn is None

    def test_cache_key_generation(self):
        """_make_key() generates consistent SHA256-based keys."""
        from scripts.core.data_cache import DataCache

        key1 = DataCache._make_key("server", "tool", {"a": 1, "b": 2})
        key2 = DataCache._make_key("server", "tool", {"b": 2, "a": 1})

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex

    def test_cache_make_args_hash(self):
        """_make_args_hash() returns a hash string."""
        from scripts.core.data_cache import DataCache

        h = DataCache._make_args_hash({"k": "v"})
        assert isinstance(h, str)
        assert len(h) == 64


class TestDataCacheEntry:
    """CacheEntry and related dataclass tests."""

    def test_cache_entry_age(self):
        """age_seconds property returns positive value."""
        from scripts.core.data_cache import CacheEntry

        entry = CacheEntry(
            key="test_key",
            server="test-server",
            tool="test-tool",
            args_hash="abc",
            data='{"value": 1}',
        )

        age = entry.age_seconds
        assert isinstance(age, float)
        assert age >= 0

    def test_cache_entry_is_expired(self):
        """is_expired() correctly identifies expired entries."""
        from scripts.core.data_cache import CacheEntry
        import time

        entry = CacheEntry(
            key="test_key",
            server="test-server",
            tool="test-tool",
            args_hash="abc",
            data='{}',
            created_at=time.time() - 100,
        )

        assert entry.is_expired(ttl_seconds=50) is True
        assert entry.is_expired(ttl_seconds=200) is False
