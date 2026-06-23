"""
Tests for DIDEventStudyConfig control group mean fields in interactive_explorer.py
"""

import pytest
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.interactive_explorer import (
    DIDEventStudyConfig,
    DIDEventStudyExplorer,
)


class TestDIDEventStudyConfigCtrlMeans:
    """Test that DIDEventStudyConfig accepts pre_ctrl_means and post_ctrl_means."""

    def test_config_accepts_ctrl_means_fields(self):
        """Config dataclass accepts pre_ctrl_means and post_ctrl_means."""
        cfg = DIDEventStudyConfig(
            pre_means={"-2": 1.0, "-1": 1.1},
            post_means={"1": 2.0, "2": 2.2},
            pre_ctrl_means={"-2": 0.9, "-1": 1.0},
            post_ctrl_means={"1": 1.8, "2": 1.9},
        )
        assert cfg.pre_ctrl_means == {"-2": 0.9, "-1": 1.0}
        assert cfg.post_ctrl_means == {"1": 1.8, "2": 1.9}

    def test_config_defaults_to_empty_dict(self):
        """New fields default to empty dict when not provided."""
        cfg = DIDEventStudyConfig(
            pre_means={"-1": 1.0},
            post_means={"1": 2.0},
        )
        assert cfg.pre_ctrl_means == {}
        assert cfg.post_ctrl_means == {}


class TestPreparePlotDataCtrlMeans:
    """Test that _prepare_plot_data uses control means when provided."""

    def test_uses_ctrl_means_when_provided(self, caplog):
        """When pre/post_ctrl_means are set, they are used instead of treatment means."""
        cfg = DIDEventStudyConfig(
            pre_means={"-2": 10.0, "-1": 11.0},
            post_means={"1": 20.0, "2": 22.0},
            pre_ctrl_means={"-2": 5.0, "-1": 5.5},
            post_ctrl_means={"1": 8.0, "2": 8.5},
        )
        explorer = DIDEventStudyExplorer(cfg)

        with caplog.at_level(logging.WARNING):
            periods, treat_vals, ctrl_vals, ctrl_ses = explorer._get_periods_and_values()

        # Control means should differ from treatment means
        assert ctrl_vals[0] == 5.0  # pre_ctrl_means["-2"]
        assert ctrl_vals[1] == 5.5  # pre_ctrl_means["-1"]
        assert ctrl_vals[2] == 8.0  # post_ctrl_means["1"]
        assert ctrl_vals[3] == 8.5  # post_ctrl_means["2"]
        # No warnings since ctrl means are provided
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("Control group mean missing" in m for m in warning_msgs)

    def test_falls_back_to_treat_and_warns_when_ctrl_means_missing(self, caplog):
        """When ctrl means are missing, falls back to treatment mean and logs a warning."""
        cfg = DIDEventStudyConfig(
            pre_means={"-1": 10.0},
            post_means={"1": 20.0},
            # No pre_ctrl_means / post_ctrl_means
        )
        explorer = DIDEventStudyExplorer(cfg)

        with caplog.at_level(logging.WARNING):
            periods, treat_vals, ctrl_vals, ctrl_ses = explorer._get_periods_and_values()

        # Falls back to treatment means
        assert ctrl_vals[0] == 10.0
        assert ctrl_vals[1] == 20.0
        # Should have logged warnings
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_msgs) >= 2  # one for pre, one for post
        assert all("Control group mean missing" in m for m in warning_msgs)

    def test_ctrl_means_used_for_integer_string_keys(self):
        """Integer-like period strings (e.g. '-1') are handled correctly."""
        cfg = DIDEventStudyConfig(
            pre_means={"-1": 10.0, "-2": 9.0},
            post_means={"1": 20.0, "2": 22.0},
            pre_ctrl_means={"-1": 4.0, "-2": 3.5},
            post_ctrl_means={"1": 8.0, "2": 8.5},
        )
        explorer = DIDEventStudyExplorer(cfg)
        periods, treat_vals, ctrl_vals, _ = explorer._get_periods_and_values()
        # Integer key "-1" should match pre_ctrl_means["-1"]
        assert ctrl_vals[0] == 3.5
        assert ctrl_vals[1] == 4.0


class TestToSummaryDataCtrlMeans:
    """Test that to_summary_data uses control group means from config."""

    def test_uses_ctrl_means_in_summary(self):
        """to_summary_data computes pre/post_diff using config ctrl means."""
        cfg = DIDEventStudyConfig(
            pre_means={"-2": 10.0, "-1": 12.0},  # mean = 11.0
            post_means={"1": 20.0},               # mean = 20.0
            pre_ctrl_means={"-2": 8.0, "-1": 10.0},  # mean = 9.0
            post_ctrl_means={"1": 15.0},              # mean = 15.0
        )
        explorer = DIDEventStudyExplorer(cfg)
        summary = explorer.to_summary_data()

        # pre_diff = treat(11.0) - ctrl(9.0) = 2.0
        assert summary["pre_diff"] == pytest.approx(2.0)
        # post_diff = treat(20.0) - ctrl(15.0) = 5.0
        assert summary["post_diff"] == pytest.approx(5.0)
        # did_estimate = post_diff - pre_diff = 5.0 - 2.0 = 3.0
        assert summary["did_estimate"] == pytest.approx(3.0)

    def test_falls_back_to_treat_mean_when_ctrl_means_missing(self, caplog):
        """to_summary_data falls back to treatment mean when ctrl means are absent."""
        cfg = DIDEventStudyConfig(
            pre_means={"-1": 10.0},  # mean = 10.0
            post_means={"1": 20.0},  # mean = 20.0
            # No ctrl_means
        )
        explorer = DIDEventStudyExplorer(cfg)

        with caplog.at_level(logging.WARNING):
            summary = explorer.to_summary_data()

        # pre_mean_ctrl = pre_mean_treat = 10.0 (fallback)
        assert summary["pre_diff"] == pytest.approx(0.0)
        # post_mean_ctrl = post_mean_treat = 20.0 (fallback)
        assert summary["post_diff"] == pytest.approx(0.0)
        # did_estimate = post_diff - pre_diff = 0.0
        assert summary["did_estimate"] == pytest.approx(0.0)
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Control group" in m and "not provided" in m for m in warning_msgs)
