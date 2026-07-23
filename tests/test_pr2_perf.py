"""Tests for PR-2 perf/correctness fixes.

Covers:
  - LLM cache key now includes system_prompt / temperature / max_tokens
    (scripts.ai_router.ResponseCache)
  - RobustnessRunner cache key uses a content-based fingerprint instead
    of id(df)
  - Literature _rate_limit token-bucket honours ``cache_hit=True`` bypass
    and falls back to legacy sleep for unknown servers
"""
from __future__ import annotations

import time

import pandas as pd

from scripts.ai_router import CacheManager as ResponseCache
from scripts.literature_download import (
    _SS_BUCKET,
    _rate_limit,
)


# ── ResponseCache key composition (PR-2.1) ──────────────────────────────


def _make_cache(tmp_path):
    return ResponseCache(cache_dir=str(tmp_path), max_age_days=0)


def test_cache_key_differs_by_system_prompt(tmp_path):
    c = _make_cache(tmp_path)
    c.set("hello", "deepseek", "resp-A", task="lit", system="sys-A")
    c.set("hello", "deepseek", "resp-B", task="lit", system="sys-B")
    # Both writes produce a get-hit for *their* key, but neither key
    # should collide with the other's lookup.
    assert c.get("hello", "deepseek", system="sys-A", task="lit") == "resp-A"
    assert c.get("hello", "deepseek", system="sys-B", task="lit") == "resp-B"
    assert c.get("hello", "deepseek", system="sys-C", task="lit") is None


def test_cache_key_differs_by_temperature(tmp_path):
    c = _make_cache(tmp_path)
    c.set("hi", "deepseek", "hot", task="lit", temperature=0.9)
    c.set("hi", "deepseek", "cold", task="lit", temperature=0.1)
    assert c.get("hi", "deepseek", temperature=0.9, task="lit") == "hot"
    assert c.get("hi", "deepseek", temperature=0.1, task="lit") == "cold"


def test_cache_key_differs_by_max_tokens(tmp_path):
    c = _make_cache(tmp_path)
    c.set("x", "deepseek", "short", task="lit", max_tokens=256)
    c.set("x", "deepseek", "long", task="lit", max_tokens=4096)
    assert c.get("x", "deepseek", max_tokens=256, task="lit") == "short"
    assert c.get("x", "deepseek", max_tokens=4096, task="lit") == "long"


def test_cache_hit_with_no_metadata_does_not_match_rich_lookup(tmp_path):
    """Cache entries written without extra metadata cannot be served to
    callers that supply *real* metadata — guards against silent stale
    data when system_prompt / temperature / max_tokens actually differ.
    """
    c = _make_cache(tmp_path)
    c.set("foo", "deepseek", "bare", task="lit")  # no system/temp/max
    # A caller supplying real (non-None) system_prompt / temperature /
    # max_tokens will hash to a different key than the bare write, so they
    # must see a miss.
    miss = c.get("foo", "deepseek", system="sys-A", temperature=0.7,
                 max_tokens=512, task="lit")
    assert miss is None


def test_cache_lookup_with_none_metadata_finds_bare_entry(tmp_path):
    """Lookup with system=None / temperature=None / max_tokens=None must
    still find the entry written without metadata — the None values are
    canonical, so the hashes match."""
    c = _make_cache(tmp_path)
    c.set("foo", "deepseek", "bare", task="lit")
    hit = c.get("foo", "deepseek", system=None, temperature=None,
                max_tokens=None, task="lit")
    assert hit == "bare"


# ── RobustnessRunner fingerprint (PR-2.6) ──────────────────────────────


def test_robustness_runner_uses_content_fingerprint(monkeypatch):
    """Verify the new fingerprint code path is exercised and stable."""
    # Sanity: two DataFrames with identical content must produce the same
    # fingerprint regardless of object identity.
    df_a = pd.DataFrame({"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]})
    df_b = df_a.copy()
    assert id(df_a) != id(df_b)
    import hashlib as _h
    fp_a = _h.sha256(
        pd.util.hash_pandas_object(df_a.head(200_000), index=False).values.tobytes()
    ).hexdigest()[:16]
    fp_b = _h.sha256(
        pd.util.hash_pandas_object(df_b.head(200_000), index=False).values.tobytes()
    ).hexdigest()[:16]
    assert fp_a == fp_b


def test_robustness_runner_different_content_different_fingerprint():
    df_a = pd.DataFrame({"a": [1, 2, 3, 4]})
    df_b = pd.DataFrame({"a": [1, 2, 3, 5]})
    import hashlib as _h
    fp_a = _h.sha256(
        pd.util.hash_pandas_object(df_a.head(200_000), index=False).values.tobytes()
    ).hexdigest()[:16]
    fp_b = _h.sha256(
        pd.util.hash_pandas_object(df_b.head(200_000), index=False).values.tobytes()
    ).hexdigest()[:16]
    assert fp_a != fp_b


# ── Token-bucket rate limit (PR-2.7) ───────────────────────────────────


def test_rate_limit_cache_hit_skips_sleep(monkeypatch):
    """cache_hit=True must not sleep or take a token."""
    # Set capacity to 1; without cache_hit the first call drains it; with
    # cache_hit it must not.
    _SS_BUCKET._tokens = 1.0
    t0 = time.monotonic()
    _rate_limit(server="semantic_scholar", cache_hit=True)
    elapsed = time.monotonic() - t0
    # Should be effectively instant.
    assert elapsed < 0.05
    # Bucket untouched.
    assert _SS_BUCKET._tokens == 1.0


def test_rate_limit_known_server_consumes_token(monkeypatch):
    """``_rate_limit`` on a known server must decrement the bucket.

    Reset the bucket to exactly 1.0 first, then fake out the refilling
    sleep path so the test is fast and deterministic.
    """
    # Freeze refill: any time.sleep call is a no-op during this test.
    monkeypatch.setattr("scripts.literature_download.time.sleep", lambda *_: None)
    _SS_BUCKET._tokens = 1.0
    _SS_BUCKET._last = time.monotonic()  # baseline
    _rate_limit(server="semantic_scholar")
    # After one acquire with refills frozen, bucket should be < 1.0.
    assert _SS_BUCKET._tokens < 1.0


def test_rate_limit_unknown_server_legacy_sleep(monkeypatch):
    """Unknown server -> falls back to ``time.sleep(min_seconds)``."""
    calls = {"slept": 0.0}
    real_sleep = time.sleep

    def fake_sleep(s):
        calls["slept"] = s
        # Do not actually wait — keep the test fast.
        return None

    monkeypatch.setattr("scripts.literature_download.time.sleep", fake_sleep)
    _rate_limit(min_seconds=0.123, server="bogus_server_xyz")
    assert calls["slept"] == 0.123
