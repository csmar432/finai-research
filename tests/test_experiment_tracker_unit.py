"""Unit tests for scripts/experiment_tracker.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def et():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import experiment_tracker as e
    yield e
    if _p in sys.path:
        sys.path.remove(_p)


class TestExperimentConfig:
    def test_default_init(self, et):
        cfg = et.ExperimentConfig()
        assert cfg.random_seed == 42
        assert cfg.model_params == {}

    def test_custom_init(self, et):
        cfg = et.ExperimentConfig(
            random_seed=42,
            dataset_version="v1",
            dataset_source="tushare",
            data_time_range="2020-2024",
            model_params={"layers": 3},
            hyperparams={"lr": 0.01},
            environment={"python": "3.11"},
            notes="baseline run",
        )
        assert cfg.random_seed == 42
        assert cfg.notes == "baseline run"


class TestExperimentResult:
    def test_init(self, et):
        r = et.ExperimentResult(
            metric_name="ATE",
            value=0.15,
            std=0.02,
            p_value=0.03,
            ci_lower=0.10,
            ci_upper=0.20,
            sample_size=1000,
            note="DID baseline",
        )
        assert r.metric_name == "ATE"
        assert abs(r.value - 0.15) < 1e-9


class TestExperimentArtifact:
    def test_init(self, et):
        a = et.ExperimentArtifact(
            artifact_type="table",
            path="/tmp/result.csv",
            description="Main regression table",
            format="csv",
        )
        assert a.artifact_type == "table"
        assert a.format == "csv"


class TestExperimentTracker:
    def test_init(self, et):
        tracker = et.ExperimentTracker()
        assert tracker is not None
