"""Unit tests for scripts/core/data_cache.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def dc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import data_cache as d
    yield d
    if _p in sys.path:
        sys.path.remove(_p)


class TestDataclasses:
    def test_cache_entry(self, dc):
        entry = dc.CacheEntry(
            key="k1",
            server="tushare",
            tool="get_daily_quote",
            args_hash="abc123",
            data={"prices": [100, 101]},
        )
        assert entry.key == "k1"
        assert entry.data["prices"] == [100, 101]

    def test_fallback_tier(self, dc):
        tier = dc.FallbackTier(
            name="primary",
            server="tushare",
            tool="get_daily_quote",
            fallback_args={},
        )
        assert tier.name == "primary"

    def test_rate_limiter(self, dc):
        rl = dc.RateLimiter(
            server="tushare",
            tool="get_data",
            remaining=10,
            reset_at=1000.0,
        )
        assert rl.remaining == 10


class TestFallbackChain:
    def test_init(self, dc):
        chain = dc.FallbackChain(chain_name="stock_info")
        assert chain is not None

    def test_init_invalid_raises(self, dc):
        import pytest
        with pytest.raises(ValueError, match="Unknown chain"):
            dc.FallbackChain(chain_name="data_fetch")  # invalid chain name


class TestDataCache:
    def test_init(self, dc):
        cache = dc.DataCache()
        assert cache is not None

    def test_init_with_path(self, dc):
        cache = dc.DataCache(db_path=".cache/test.ddb")
        assert cache is not None
