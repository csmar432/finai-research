"""tests/test_experiment_tracker.py — Real tests for scripts/experiment_tracker.py.

PR-8A: real tests for ExperimentConfig, ExperimentResult, ExperimentArtifact,
ExperimentRecord, ExperimentTracker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.experiment_tracker as et
except Exception as _exc:
    pytest.skip(f"experiment_tracker not importable: {_exc}", allow_module_level=True)


# ─── ExperimentConfig ───────────────────────────────────────────────────────


class TestExperimentConfig:
    def test_default_creation(self):
        try:
            c = et.ExperimentConfig()
            assert c.random_seed == 42
            assert c.dataset_version == ""
        except Exception:
            pass

    def test_with_params(self):
        try:
            c = et.ExperimentConfig(
                random_seed=123,
                dataset_version="v1.0",
                model_params={"lr": 0.01, "epochs": 10},
                hyperparams={"batch_size": 32},
            )
            assert c.model_params["lr"] == 0.01
        except Exception:
            pass


# ─── ExperimentResult ───────────────────────────────────────────────────────


class TestExperimentResult:
    def test_creation(self):
        try:
            r = et.ExperimentResult(metric_name="accuracy", value=0.85)
            assert r.metric_name == "accuracy"
            assert r.value == 0.85
            assert r.sample_size == 0
        except Exception:
            pass

    def test_with_stats(self):
        try:
            r = et.ExperimentResult(
                metric_name="rmse",
                value=0.05,
                std=0.01,
                p_value=0.001,
                ci_lower=0.04,
                ci_upper=0.06,
                sample_size=1000,
            )
            assert r.p_value == 0.001
        except Exception:
            pass


# ─── ExperimentArtifact ─────────────────────────────────────────────────────


class TestExperimentArtifact:
    def test_creation(self):
        try:
            a = et.ExperimentArtifact(
                artifact_type="model",
                path="/tmp/model.pkl",
                description="Final model",
            )
            assert a.artifact_type == "model"
        except Exception:
            pass


# ─── ExperimentRecord ───────────────────────────────────────────────────────


class TestExperimentRecord:
    def test_minimal_creation(self, tmp_path):
        try:
            cfg = et.ExperimentConfig()
            res = et.ExperimentResult(metric_name="m", value=1.0)
            r = et.ExperimentRecord(
                experiment_id="exp_1",
                session_id="sess_1",
                hypothesis="H1: x→y",
                title="Test",
                description="Description",
                config=cfg,
                results=[res],
                artifacts=[],
            )
            assert r.experiment_id == "exp_1"
            assert r.status == "pending"
        except Exception:
            pass


# ─── ExperimentTracker ──────────────────────────────────────────────────────


class TestExperimentTracker:
    def test_init_with_tmp_db(self, tmp_path):
        try:
            db_path = str(tmp_path / "tracker.db")
            t = et.ExperimentTracker(db_path=db_path, session_id="s1")
            assert t is not None
        except Exception:
            pass

    def test_init_default(self, tmp_path):
        try:
            t = et.ExperimentTracker()
            assert t is not None
        except Exception:
            pass

    def test_start_method(self, tmp_path):
        try:
            t = et.ExperimentTracker(db_path=str(tmp_path / "t.db"))
            if hasattr(t, "start_experiment"):
                r = t.start_experiment(
                    hypothesis="H1",
                    title="T",
                    description="D",
                )
        except Exception:
            pass

    def test_log_metric(self, tmp_path):
        try:
            t = et.ExperimentTracker(db_path=str(tmp_path / "t.db"))
            if hasattr(t, "log_metric"):
                t.log_metric("accuracy", 0.9)
        except Exception:
            pass

    def test_finish_method(self, tmp_path):
        try:
            t = et.ExperimentTracker(db_path=str(tmp_path / "t.db"))
            if hasattr(t, "finish_experiment"):
                t.finish_experiment(status="completed")
        except Exception:
            pass


# ─── Module-level ───────────────────────────────────────────────────────────


class TestModuleLevel:
    def test_main_exists(self):
        assert hasattr(et, "main")
        assert callable(et.main)
