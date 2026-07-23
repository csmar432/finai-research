"""Tests for the pipeline checkpoint system (scripts/core/checkpoint.py).

These tests verify the save/load/restore cycle and the atomic-write guarantee
using a temporary directory — no external services required.
"""


import pytest

from scripts.core.checkpoint import (
    CheckpointManager,
    PipelineCheckpoint,
)


# ── PipelineCheckpoint dataclass ───────────────────────────────────────────────


class TestPipelineCheckpoint:
    """Tests for PipelineCheckpoint serialization and properties."""

    def test_to_json_roundtrip(self):
        """to_json() → from_json() should preserve all fields."""
        chk = PipelineCheckpoint(
            pipeline_id="test_run_001",
            pipeline_name="paper_pipeline",
            timestamp=1700000000.0,
            completed_stage_index=2,
            completed_stages=["outline", "literature", "plotting"],
            context={"outline": {"sections": 5}, "lit_count": 12},
            stage_results={"outline": {"ok": True}},
            hitl_state={"pending": [], "history": []},
            config_hash="abc123",
            metadata={"topic": "Carbon trading"},
        )

        d = chk.to_json()
        restored = PipelineCheckpoint.from_json(d)

        assert restored.pipeline_id == "test_run_001"
        assert restored.pipeline_name == "paper_pipeline"
        assert restored.completed_stage_index == 2
        assert restored.completed_stages == ["outline", "literature", "plotting"]
        assert restored.context["outline"]["sections"] == 5
        assert restored.stage_results["outline"]["ok"] is True
        assert restored.config_hash == "abc123"
        assert restored.metadata["topic"] == "Carbon trading"

    def test_is_empty_true_when_no_stages(self):
        """is_empty should be True when completed_stage_index < 0."""
        chk = PipelineCheckpoint(
            pipeline_id="fresh",
            pipeline_name="test",
            timestamp=0.0,
            completed_stage_index=-1,
            completed_stages=[],
        )
        assert chk.is_empty is True

    def test_is_empty_false_when_stages_completed(self):
        """is_empty should be False after at least one stage completes."""
        chk = PipelineCheckpoint(
            pipeline_id="resumed",
            pipeline_name="test",
            timestamp=0.0,
            completed_stage_index=0,
            completed_stages=["outline"],
        )
        assert chk.is_empty is False

    def test_config_changed_since_detects_change(self):
        """config_changed_since should return True when hash differs."""
        chk = PipelineCheckpoint(
            pipeline_id="test",
            pipeline_name="test",
            timestamp=0.0,
            config_hash="old_hash_abc",
        )
        assert chk.config_changed_since('{"stages": ["a", "b"]}') is True

    def test_config_changed_since_allows_unchanged(self):
        """config_changed_since should return False when hash matches."""
        config_str = '{"stages": ["a", "b"]}'
        # Replicate the hashing logic used by CheckpointManager
        import hashlib
        import json as _json
        canonical = _json.dumps(_json.loads(config_str), sort_keys=True)
        h = hashlib.sha256(canonical.encode()).hexdigest()

        chk = PipelineCheckpoint(
            pipeline_id="test",
            pipeline_name="test",
            timestamp=0.0,
            config_hash=h,
        )
        assert chk.config_changed_since(config_str) is False

    def test_checkpoint_id_derivation(self):
        """checkpoint_id should be derived from pipeline_id and timestamp."""
        chk = PipelineCheckpoint(
            pipeline_id="my_pipeline",
            pipeline_name="test",
            timestamp=1700000000.0,
        )
        assert "my_pipeline" in chk.checkpoint_id
        assert str(int(1700000000.0 * 1000)) in chk.checkpoint_id


# ── CheckpointManager ──────────────────────────────────────────────────────────


class TestCheckpointManager:
    """Tests for CheckpointManager file operations."""

    @pytest.fixture
    def mgr(self, tmp_path):
        return CheckpointManager(base_dir=tmp_path / "checkpoints")

    def test_save_and_load_latest(self, mgr):
        """save() → load_latest() should restore a checkpoint."""
        import uuid
        pid = f"paper_{uuid.uuid4().hex[:8]}"
        mgr.save(
            pipeline_id=pid,
            pipeline_name="paper_pipeline",
            completed_stage="literature",
            context={"lit_count": 15},
            stage_results={"literature": {"papers": 15}},
        )

        chk = mgr.load_latest(pid)
        assert chk is not None
        assert chk.pipeline_name == "paper_pipeline"
        assert chk.context["lit_count"] == 15
        assert chk.completed_stage_index >= 0

    def test_context_restoration(self, mgr):
        """restore_context() should return a deep copy of the saved context."""
        import uuid
        pid = f"restore_{uuid.uuid4().hex[:8]}"
        mgr.save(
            pipeline_id=pid,
            pipeline_name="test",
            completed_stage="outline",
            context={"key1": "value1", "key2": [1, 2, 3]},
            stage_results={},
        )

        restored = mgr.load_latest(pid)
        ctx = mgr.restore_context(restored)

        assert ctx["key1"] == "value1"
        assert ctx["key2"] == [1, 2, 3]
        ctx["key2"].append(4)
        # Original should be unaffected (deep copy)
        assert mgr.restore_context(restored)["key2"] == [1, 2, 3]

    def test_atomic_write_no_tmp_files(self, mgr):
        """After multiple saves, no *.tmp files should remain."""
        for i in range(5):
            mgr.save(
                pipeline_id=f"pipeline_{i}",
                pipeline_name=f"Pipeline {i}",
                completed_stage="outline",
                context={"i": i},
                stage_results={},
            )

        tmp_files = list(mgr.base_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Found leftover tmp files: {tmp_files}"

    def test_load_nonexistent_returns_none(self, mgr):
        """load_latest() for a never-seen pipeline should return None."""
        result = mgr.load_latest("this_pipeline_never_existed_xyz")
        assert result is None

    def test_multiple_checkpoints_newest_first(self, mgr):
        """list_checkpoints() should return checkpoints newest-first by timestamp."""
        import uuid
        pipeline_id = f"multi_test_{uuid.uuid4().hex[:8]}"
        for stage in ["outline", "literature", "plotting"]:
            mgr.save(
                pipeline_id=pipeline_id,
                pipeline_name="test",
                completed_stage=stage,
                context={"stage": stage},
                stage_results={stage: {}},
            )

        checkpoints = mgr.list_checkpoints(pipeline_id, limit=10)
        assert len(checkpoints) == 3
        # Newest first — plotting (last save) has latest timestamp
        assert checkpoints[0].completed_stages == ["plotting"]
        assert checkpoints[1].completed_stages == ["literature"]
        assert checkpoints[2].completed_stages == ["outline"]

    def test_prune_keeps_recent(self, mgr):
        """prune(keep=2) should delete older checkpoints."""
        import time
        for i in range(5):
            mgr.save(
                pipeline_id="prune_test",
                pipeline_name="test",
                completed_stage=f"stage_{i}",
                context={"i": i},
                stage_results={f"stage_{i}": {}},
            )
            time.sleep(0.01)  # ensure unique timestamps

        deleted = mgr.prune("prune_test", keep=2)
        assert deleted == 3

        remaining = mgr.list_checkpoints("prune_test")
        assert len(remaining) == 2

    def test_validate_resume_safe(self, mgr):
        """validate_resume() should return (True, '') for matching config."""
        import hashlib
        import json

        config = {"stages": ["a", "b"]}
        canonical = json.dumps(config, sort_keys=True)
        h = hashlib.sha256(canonical.encode()).hexdigest()

        chk = PipelineCheckpoint(
            pipeline_id="validate_test",
            pipeline_name="test",
            timestamp=0.0,
            config_hash=h,
        )

        safe, reason = mgr.validate_resume(chk, config)
        assert safe is True
        assert reason == ""

    def test_validate_resume_unsafe(self, mgr):
        """validate_resume() should warn when config has changed."""
        chk = PipelineCheckpoint(
            pipeline_id="validate_changed",
            pipeline_name="test",
            timestamp=0.0,
            config_hash="old_hash_xyz",
        )

        safe, reason = mgr.validate_resume(chk, {"stages": ["x", "y", "z"]})
        assert safe is False
        assert "changed" in reason.lower()

    def test_stats_returns_count(self, mgr):
        """stats() should return the number of checkpoints."""
        for stage in ["a", "b"]:
            mgr.save(
                pipeline_id="stats_test",
                pipeline_name="test",
                completed_stage=stage,
                context={},
                stage_results={stage: {}},
            )

        stats = mgr.stats("stats_test")
        assert stats["count"] == 2
        assert stats["pipeline_id"] == "stats_test"
        assert stats["latest_stage_index"] == 0  # single stage per save
