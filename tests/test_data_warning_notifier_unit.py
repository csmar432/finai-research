"""Unit tests for scripts/core/data_warning_notifier.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.core import data_warning_notifier as dwn
from scripts.core.data_warning_notifier import DataWarning, DataWarningNotifier


class TestDataWarningDataclass:
    """DataWarning frozen dataclass."""

    def test_required_fields(self):
        w = DataWarning(category="c", source="s", reason="r")
        assert w.category == "c"
        assert w.source == "s"
        assert w.reason == "r"

    def test_default_ts(self):
        w = DataWarning(category="c", source="s", reason="r")
        assert isinstance(w.ts, float)

    def test_optional_site(self):
        w = DataWarning(category="c", source="s", reason="r", site="x.py:10")
        assert w.site == "x.py:10"

    def test_frozen(self):
        w = DataWarning(category="c", source="s", reason="r")
        with pytest.raises(Exception):  # FrozenInstanceError
            w.category = "new"  # type: ignore[misc]


class TestDataWarningNotifierInit:
    """Constructor + initial state."""

    def test_init_creates_seen_set(self):
        n = DataWarningNotifier()
        assert isinstance(n._seen, set)

    def test_init_creates_lock(self):
        n = DataWarningNotifier()
        import threading
        assert isinstance(n._lock, type(threading.Lock()))

    def test_init_disabled_false(self):
        n = DataWarningNotifier()
        assert n._disabled is False


class TestDataWarningNotifierConfigure:
    """configure(disabled=...) toggles processing."""

    def test_configure_disable(self):
        n = DataWarningNotifier()
        n.configure(disabled=True)
        assert n._disabled is True

    def test_configure_enable(self):
        n = DataWarningNotifier()
        n.configure(disabled=True)
        n.configure(disabled=False)
        assert n._disabled is False


class TestDataWarningNotifierWarn:
    """warn() emits, dedups, and respects disabled state."""

    def setup_method(self):
        self.notifier = DataWarningNotifier()
        self.tmp_log = Path("/tmp/test_data_warn_unit.jsonl")
        if self.tmp_log.exists():
            self.tmp_log.unlink()

    def teardown_method(self):
        if self.tmp_log.exists():
            self.tmp_log.unlink()

    def test_warn_first_call_fires(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        result = self.notifier.warn("research_direction", "behavioral_finance", "statsmodels failed")
        assert result is True

    def test_warn_dedup_second_call_returns_false(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.warn("research_direction", "behavioral_finance", "statsmodels failed")
        result = self.notifier.warn("research_direction", "behavioral_finance", "different reason")
        assert result is False

    def test_warn_different_source_fires(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.warn("research_direction", "behavioral_finance", "statsmodels failed")
        result = self.notifier.warn("research_direction", "macro_finance", "different source")
        assert result is True

    def test_warn_disabled_returns_false(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.configure(disabled=True)
        result = self.notifier.warn("c", "s", "r")
        assert result is False
        # Log file should not be created
        assert not self.tmp_log.exists()

    def test_warn_appends_to_log(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.warn("c", "s", "r")
        assert self.tmp_log.exists()
        content = self.tmp_log.read_text(encoding="utf-8").strip()
        record = json.loads(content)
        assert record["category"] == "c"
        assert record["source"] == "s"
        assert record["reason"] == "r"

    def test_warn_appends_site_when_provided(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.warn("c", "s", "r", site="x.py:42")
        record = json.loads(self.tmp_log.read_text(encoding="utf-8").strip())
        assert record["site"] == "x.py:42"

    def test_warn_site_is_none_by_default(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", self.tmp_log)
        self.notifier.warn("c", "s", "r")
        record = json.loads(self.tmp_log.read_text(encoding="utf-8").strip())
        assert record["site"] is None


class TestDataWarningNotifierStats:
    """stats() returns the dedup set."""

    def test_stats_initial_empty(self):
        n = DataWarningNotifier()
        stats = n.stats()
        assert isinstance(stats, dict)
        assert stats.get("unique_warnings") == 0

    def test_stats_after_warning(self, monkeypatch):
        monkeypatch.setattr(dwn, "_LOG_PATH", Path("/tmp/x.jsonl"))
        n = DataWarningNotifier()
        n.warn("c1", "s1", "r1")
        n.warn("c1", "s2", "r2")
        stats = n.stats()
        assert stats["unique_warnings"] == 2
        assert isinstance(stats["warnings"], list)
        assert len(stats["warnings"]) == 2


class TestSuppressEnvVar:
    """FINAI_SUPPRESS_DATA_WARNINGS=1 silences output."""

    def test_suppress_env_disables_warnings(self, monkeypatch):
        # First ensure clean state
        n = DataWarningNotifier()
        monkeypatch.setattr(dwn, "_SUPPRESSED", True)
        result = n.warn("c", "s", "r")
        assert result is False


class TestLoggingFailureSwallowed:
    """Logging failures must not break the caller."""

    def test_log_failure_swallowed(self, monkeypatch):
        n = DataWarningNotifier()
        # Force the log file write to fail
        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(dwn, "_LOG_PATH", Path("/nonexistent/x/y/z.jsonl"))
        # Even if mkdir fails, the warn() should not raise
        with patch("builtins.open", side_effect=_boom):
            # This will internally try to open and fail
            try:
                result = n.warn("c", "s", "r")
                # Result may be True if no exception escapes
                assert result in (True, False)
            except Exception as exc:
                pytest.fail(f"warn() raised: {exc}")
