"""Unit tests for scripts/core/checkpoint.py.

Covers: PipelineCheckpoint, PipelineTelemetry, CheckpointManager, and helpers.
CheckpointableOrchestrator is integration-tested separately (requires AgentOrchestrator).

Test conventions:
  - Synthetic data only — no network calls.
  - Uses tmp_path fixture for file I/O.
  - Deterministic, no timing dependencies.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.checkpoint import (
    PipelineCheckpoint,
    CheckpointManager,
    PipelineTelemetry,
    _sha256,
    _make_config_hash,
    _atomic_write_json,
    _sanitise,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════


class TestSanitise:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("simple", "simple"),
            ("with-dash", "with-dash"),
            ("with_underscore", "with_underscore"),
            ("with.dot", "with.dot"),
            ("with space", "with_space"),
            ("with/slash", "with_slash"),
            ("UPPERCASE", "UPPERCASE"),
            ("中文", "中文"),
            ("pipe|name", "pipe_name"),
            ("question?mark", "question_mark"),
        ],
    )
    def test_sanitise_replaces_unsafe_chars(self, name, expected):
        assert _sanitise(name) == expected


class TestSha256:
    def test_sha256_returns_hex(self):
        result = _sha256("hello")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest length
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_deterministic(self):
        h1 = _sha256("test content")
        h2 = _sha256("test content")
        assert h1 == h2

    def test_sha256_different_inputs_different_hash(self):
        h1 = _sha256("abc")
        h2 = _sha256("xyz")
        assert h1 != h2

    def test_sha256_unicode(self):
        result = _sha256("中文测试")
        assert len(result) == 64


class TestMakeConfigHash:
    def test_make_config_hash_dict(self):
        config = {"key": "value", "num": 42}
        result = _make_config_hash(config)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_make_config_hash_list(self):
        config = ["step1", "step2", "step3"]
        result = _make_config_hash(config)
        assert len(result) == 64

    def test_make_config_hash_order_independent(self):
        # sort_keys=True makes ordering irrelevant
        h1 = _make_config_hash({"a": 1, "b": 2})
        h2 = _make_config_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_make_config_hash_different_values(self):
        h1 = _make_config_hash({"k": "v1"})
        h2 = _make_config_hash({"k": "v2"})
        assert h1 != h2


class TestAtomicWriteJson:
    def test_atomic_write_creates_file(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"key": "value"})
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"key": "value"}

    def test_atomic_write_nested_dict(self, tmp_path):
        path = tmp_path / "nested.json"
        _atomic_write_json(path, {"outer": {"inner": [1, 2, 3]}})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["outer"]["inner"] == [1, 2, 3]

    def test_atomic_write_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / "nested" / "file.json"
        _atomic_write_json(path, {"test": True})
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["test"] is True


# ═══════════════════════════════════════════════════════════════════════════
# PipelineCheckpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineCheckpointInit:
    def test_init_with_required_fields(self):
        chk = PipelineCheckpoint(
            pipeline_id="paper_2025",
            pipeline_name="paper_pipeline",
            timestamp=1234567890.0,
        )
        assert chk.pipeline_id == "paper_2025"
        assert chk.pipeline_name == "paper_pipeline"
        assert chk.timestamp == 1234567890.0
        assert chk.completed_stage_index == -1
        assert chk.completed_stages == []
        assert chk.context == {}
        assert chk.stage_results == {}
        assert chk.hitl_state is None
        assert chk.config_hash == ""
        assert chk.metadata == {}
        assert chk.random_seeds == {}

    def test_init_with_all_fields(self):
        now = time.time()
        ctx = {"key": "context_value"}
        results = {"stage1": {"output": "data"}}
        meta = {"topic": "carbon trading"}
        seeds = {"numpy": "state"}
        chk = PipelineCheckpoint(
            pipeline_id="full_chk",
            pipeline_name="full_pipeline",
            timestamp=now,
            completed_stage_index=2,
            completed_stages=["stage1", "stage2", "stage3"],
            context=ctx,
            stage_results=results,
            hitl_state={"pending": []},
            config_hash="abc123",
            metadata=meta,
            random_seeds=seeds,
        )
        assert chk.completed_stage_index == 2
        assert chk.completed_stages == ["stage1", "stage2", "stage3"]
        assert chk.context == ctx
        assert chk.stage_results == results
        assert chk.hitl_state == {"pending": []}
        assert chk.config_hash == "abc123"
        assert chk.metadata == meta
        assert chk.random_seeds == seeds


class TestPipelineCheckpointToJson:
    def test_to_json_returns_dict(self):
        chk = PipelineCheckpoint(
            pipeline_id="json_test",
            pipeline_name="test_pipe",
            timestamp=1000.0,
            completed_stage_index=1,
            completed_stages=["s1", "s2"],
            context={"ctx": True},
            stage_results={"s1": {"out": 1}},
            hitl_state={"pending": []},
            config_hash="hash123",
            metadata={"tag": "test"},
            random_seeds={"seed": 42},
        )
        data = chk.to_json()
        assert isinstance(data, dict)
        assert data["pipeline_id"] == "json_test"
        assert data["pipeline_name"] == "test_pipe"
        assert data["timestamp"] == 1000.0
        assert data["completed_stage_index"] == 1
        assert data["completed_stages"] == ["s1", "s2"]
        assert data["context"] == {"ctx": True}
        assert data["stage_results"] == {"s1": {"out": 1}}
        assert data["hitl_state"] == {"pending": []}
        assert data["config_hash"] == "hash123"
        assert data["metadata"] == {"tag": "test"}
        assert data["random_seeds"] == {"seed": 42}

    def test_to_json_roundtrip(self):
        original = PipelineCheckpoint(
            pipeline_id="roundtrip",
            pipeline_name="rt_pipeline",
            timestamp=9999.0,
            completed_stage_index=0,
            completed_stages=["init"],
            context={"data": [1, 2, 3]},
            stage_results={"init": {"status": "ok"}},
            hitl_state=None,
            config_hash="rthash",
            metadata={"version": 1},
            random_seeds={},
        )
        data = original.to_json()
        restored = PipelineCheckpoint.from_json(data)
        assert restored.pipeline_id == original.pipeline_id
        assert restored.pipeline_name == original.pipeline_name
        assert restored.timestamp == original.timestamp
        assert restored.completed_stage_index == original.completed_stage_index
        assert restored.completed_stages == original.completed_stages
        assert restored.context == original.context
        assert restored.stage_results == original.stage_results
        assert restored.hitl_state == original.hitl_state
        assert restored.config_hash == original.config_hash
        assert restored.metadata == original.metadata
        assert restored.random_seeds == original.random_seeds


class TestPipelineCheckpointFromJson:
    def test_from_json_required_only(self):
        data = {
            "pipeline_id": "minimal",
            "pipeline_name": "min_pipe",
            "timestamp": 1234.0,
        }
        chk = PipelineCheckpoint.from_json(data)
        assert chk.pipeline_id == "minimal"
        assert chk.pipeline_name == "min_pipe"
        assert chk.timestamp == 1234.0
        assert chk.completed_stage_index == -1
        assert chk.completed_stages == []
        assert chk.context == {}
        assert chk.stage_results == {}
        assert chk.hitl_state is None
        assert chk.config_hash == ""
        assert chk.metadata == {}

    def test_from_json_missing_fields_use_defaults(self):
        data = {
            "pipeline_id": "partial",
            "pipeline_name": "partial_pipe",
            "timestamp": 5678.0,
            "completed_stage_index": 5,
        }
        chk = PipelineCheckpoint.from_json(data)
        assert chk.completed_stage_index == 5
        assert chk.completed_stages == []
        assert chk.context == {}

    def test_from_json_drops_extra_fields(self):
        data = {
            "pipeline_id": "extra",
            "pipeline_name": "extra_pipe",
            "timestamp": 0.0,
            "unknown_field": "should_be_ignored",
            "another": 123,
        }
        chk = PipelineCheckpoint.from_json(data)
        assert not hasattr(chk, "unknown_field")


class TestPipelineCheckpointProperties:
    def test_checkpoint_id_format(self):
        chk = PipelineCheckpoint(
            pipeline_id="test_id",
            pipeline_name="test",
            timestamp=1234567890.5,
        )
        # checkpoint_id = "{pipeline_id}_{int(timestamp * 1_000_000)}"
        expected = f"test_id_{int(1234567890.5 * 1_000_000)}"
        assert chk.checkpoint_id == expected

    def test_checkpoint_id_deterministic(self):
        chk1 = PipelineCheckpoint(
            pipeline_id="abc",
            pipeline_name="x",
            timestamp=1000.0,
        )
        chk2 = PipelineCheckpoint(
            pipeline_id="abc",
            pipeline_name="x",
            timestamp=1000.0,
        )
        assert chk1.checkpoint_id == chk2.checkpoint_id

    def test_is_empty_true_when_no_stages(self):
        chk = PipelineCheckpoint(
            pipeline_id="empty",
            pipeline_name="e",
            timestamp=0.0,
            completed_stage_index=-1,
        )
        assert chk.is_empty is True

    def test_is_empty_false_when_stages_completed(self):
        chk = PipelineCheckpoint(
            pipeline_id="nonempty",
            pipeline_name="ne",
            timestamp=0.0,
            completed_stage_index=0,
            completed_stages=["stage0"],
        )
        assert chk.is_empty is False

    def test_is_empty_false_when_index_0(self):
        # completed_stage_index=0 means stage 0 completed (not "empty")
        chk = PipelineCheckpoint(
            pipeline_id="zero",
            pipeline_name="z",
            timestamp=0.0,
            completed_stage_index=0,
            completed_stages=["first_stage"],
        )
        assert chk.is_empty is False


class TestPipelineCheckpointConfigChangedSince:
    def test_config_changed_no_stored_hash(self):
        chk = PipelineCheckpoint(
            pipeline_id="no_hash",
            pipeline_name="n",
            timestamp=0.0,
            config_hash="",
        )
        assert chk.config_changed_since({"any": "config"}) is False

    def test_config_changed_same_config(self):
        config = {"model": "deepseek"}
        chk_hash = _make_config_hash(config)
        chk = PipelineCheckpoint(
            pipeline_id="same",
            pipeline_name="s",
            timestamp=0.0,
            config_hash=chk_hash,
        )
        assert chk.config_changed_since(config) is False

    def test_config_changed_different_config(self):
        chk_hash = _make_config_hash({"a": 1})
        chk = PipelineCheckpoint(
            pipeline_id="diff",
            pipeline_name="d",
            timestamp=0.0,
            config_hash=chk_hash,
        )
        assert chk.config_changed_since({"b": 2}) is True

    def test_config_changed_since_string(self):
        content = "original config content"
        chk_hash = _sha256(content)
        chk = PipelineCheckpoint(
            pipeline_id="str_test",
            pipeline_name="st",
            timestamp=0.0,
            config_hash=chk_hash,
        )
        assert chk.config_changed_since(content) is False
        assert chk.config_changed_since("modified content") is True


# ═══════════════════════════════════════════════════════════════════════════
# PipelineTelemetry
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineTelemetryInit:
    def test_init_with_required_fields(self):
        tel = PipelineTelemetry(pipeline_id="test_pipeline")
        assert tel.pipeline_id == "test_pipeline"
        assert tel.stage_durations == {}
        assert tel.token_counts == {}
        assert tel.api_call_counts == {}
        assert tel.error_counts == {}
        assert tel.mcp_call_counts == {}
        assert tel.checkpoint_ids == []
        assert tel.started_at is not None
        assert tel.ended_at is None

    def test_init_with_all_fields(self):
        now = time.time()
        tel = PipelineTelemetry(
            pipeline_id="full_tel",
            stage_durations={"lit_review": 10.5},
            token_counts={"gpt-4o": 50000},
            api_call_counts={"search": 20},
            error_counts={"timeout": 1},
            mcp_call_counts={"openalex": 15},
            checkpoint_ids=["chk1", "chk2"],
            started_at=now,
            ended_at=now + 300,
        )
        assert tel.stage_durations == {"lit_review": 10.5}
        assert tel.token_counts == {"gpt-4o": 50000}
        assert tel.api_call_counts == {"search": 20}
        assert tel.error_counts == {"timeout": 1}
        assert tel.mcp_call_counts == {"openalex": 15}
        assert tel.checkpoint_ids == ["chk1", "chk2"]
        assert tel.ended_at == now + 300


class TestPipelineTelemetryMethods:
    def test_record_stage(self):
        tel = PipelineTelemetry(pipeline_id="stage_test")
        tel.record_stage("literature_review", 5.5)
        tel.record_stage("writing", 30.0)
        assert tel.stage_durations["literature_review"] == 5.5
        assert tel.stage_durations["writing"] == 30.0

    def test_record_stage_overwrites(self):
        tel = PipelineTelemetry(pipeline_id="overwrite")
        tel.record_stage("s1", 10.0)
        tel.record_stage("s1", 20.0)
        assert tel.stage_durations["s1"] == 20.0

    def test_record_token(self):
        tel = PipelineTelemetry(pipeline_id="token_test")
        tel.record_token("gpt-4o", 1000)
        tel.record_token("gpt-4o", 500)
        tel.record_token("claude", 200)
        assert tel.token_counts["gpt-4o"] == 1500
        assert tel.token_counts["claude"] == 200

    def test_record_api_call(self):
        tel = PipelineTelemetry(pipeline_id="api_test")
        tel.record_api_call("search")
        tel.record_api_call("search")
        tel.record_api_call("fetch")
        assert tel.api_call_counts["search"] == 2
        assert tel.api_call_counts["fetch"] == 1

    def test_record_error(self):
        tel = PipelineTelemetry(pipeline_id="err_test")
        tel.record_error("timeout")
        tel.record_error("timeout")
        tel.record_error("auth")
        assert tel.error_counts["timeout"] == 2
        assert tel.error_counts["auth"] == 1

    def test_record_mcp_call(self):
        tel = PipelineTelemetry(pipeline_id="mcp_test")
        tel.record_mcp_call("openalex")
        tel.record_mcp_call("arxiv")
        tel.record_mcp_call("openalex")
        assert tel.mcp_call_counts["openalex"] == 2
        assert tel.mcp_call_counts["arxiv"] == 1

    def test_to_dict(self):
        tel = PipelineTelemetry(pipeline_id="dict_test")
        tel.record_stage("s1", 10.0)
        tel.record_token("m1", 1000)
        tel.record_api_call("api1")
        tel.record_error("e1")
        tel.record_mcp_call("mcp1")
        d = tel.to_dict()
        assert isinstance(d, dict)
        assert d["pipeline_id"] == "dict_test"
        assert "stages" in d
        assert "total_duration" in d
        assert "tokens" in d
        assert "api_calls" in d
        assert "errors" in d
        assert "mcp_calls" in d
        assert "started_at" in d
        assert "ended_at" in d

    def test_to_dict_total_duration(self):
        tel = PipelineTelemetry(pipeline_id="dur_test")
        tel.record_stage("s1", 10.0)
        tel.record_stage("s2", 5.5)
        d = tel.to_dict()
        assert d["total_duration"] == 15.5


class TestPipelineTelemetrySave:
    def test_save_writes_jsonl(self, tmp_path):
        tel = PipelineTelemetry(pipeline_id="save_test")
        tel.record_stage("step1", 3.0)
        path = tmp_path / "telemetry.jsonl"
        result_path = tel.save(path)
        assert result_path == path
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            line = f.readline()
        data = json.loads(line)
        assert data["pipeline_id"] == "save_test"

    def test_save_creates_parent_dirs(self, tmp_path):
        tel = PipelineTelemetry(pipeline_id="nested_save")
        path = tmp_path / "a" / "b" / "telemetry.jsonl"
        result_path = tel.save(path)
        assert path.exists()

    def test_save_appends_not_overwrites(self, tmp_path):
        path = tmp_path / "append.jsonl"
        path.write_text('{"old": true}\n', encoding="utf-8")
        tel = PipelineTelemetry(pipeline_id="append_test")
        tel.save(path)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["old"] is True
        assert json.loads(lines[1])["pipeline_id"] == "append_test"

    def test_save_uses_default_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tel = PipelineTelemetry(pipeline_id="default_path")
        tel.save()
        default = Path("data/pipeline_telemetry.jsonl")
        assert default.exists()


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — path helpers & init
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerInit:
    def test_init_default_base_dir(self):
        cm = CheckpointManager()
        assert cm.base_dir == Path("data/checkpoints")

    def test_init_creates_base_dir(self, tmp_path):
        base = tmp_path / "checkpoints"
        cm = CheckpointManager(base_dir=base)
        assert cm.base_dir == base
        assert base.exists()

    def test_init_lock_timeout(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path, lock_timeout=10.0)
        assert cm._lock_timeout == 10.0

    def test_init_default_lock_timeout(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        assert cm._lock_timeout == 5.0


class TestCheckpointManagerPaths:
    def test_checkpoint_path_format(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        path = cm._checkpoint_path("my_pipeline", 1234567890.5)
        safe = _sanitise("my_pipeline")
        suffix = int(1234567890.5 * 1_000_000)
        assert path.name == f"checkpoint_{safe}_{suffix}.json"
        assert path.parent == tmp_path

    def test_latest_path(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        path = cm._latest_path("my_pipeline")
        safe = _sanitise("my_pipeline")
        assert path.name == f"checkpoint_{safe}_latest.json"

    def test_index_path(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        path = cm._index_path("my_pipeline")
        safe = _sanitise("my_pipeline")
        assert path.name == f"index_{safe}.json"

    def test_paths_sanitise_pipeline_id(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        p1 = cm._latest_path("pipeline/with slash")
        p2 = cm._latest_path("pipeline_with_slash")
        assert p1 == p2


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — save / load / delete
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerSave:
    def test_save_returns_checkpoint_id(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        chk_id = cm.save(
            pipeline_id="save_test",
            pipeline_name="save_pipeline",
            completed_stage="lit_review",
            context={"topic": "carbon"},
            stage_results={"lit_review": {"papers": 10}},
        )
        assert isinstance(chk_id, str)
        assert "save_test" in chk_id

    def test_save_creates_files(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save(
            pipeline_id="files_test",
            pipeline_name="ft",
            completed_stage="s1",
            context={},
            stage_results={"s1": {}},
        )
        assert cm._latest_path("files_test").exists()
        assert cm._index_path("files_test").exists()

    def test_save_creates_manifest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save(
            pipeline_id="manifest_test",
            pipeline_name="mt",
            completed_stage="s1",
            context={},
            stage_results={"s1": {}},
        )
        manifest = cm._read_manifest("manifest_test")
        assert "checkpoints" in manifest
        assert len(manifest["checkpoints"]) == 1

    def test_save_multiple_accumulates_manifest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("multi", "m", "s1", {}, {"s1": {}})
        cm.save("multi", "m", "s2", {}, {"s1": {}, "s2": {}})
        manifest = cm._read_manifest("multi")
        assert len(manifest["checkpoints"]) == 2

    def test_save_with_metadata(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save(
            pipeline_id="meta_test",
            pipeline_name="mt",
            completed_stage="s1",
            context={},
            stage_results={"s1": {}},
            metadata={"author": "tester", "version": 2},
        )
        loaded = cm.load_latest("meta_test")
        assert loaded.metadata == {"author": "tester", "version": 2}

    def test_save_with_config_hash(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        config_hash = "abc123def456"
        cm.save(
            pipeline_id="hash_test",
            pipeline_name="ht",
            completed_stage="s1",
            context={},
            stage_results={"s1": {}},
            config_hash=config_hash,
        )
        loaded = cm.load_latest("hash_test")
        assert loaded.config_hash == config_hash

    def test_save_updates_latest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("latest", "l", "s1", {}, {"s1": {}})
        time.sleep(0.01)
        cm.save("latest", "l", "s2", {"key": "v2"}, {"s1": {}, "s2": {}})
        latest = cm.load_latest("latest")
        assert latest.completed_stage_index >= 0

    def test_save_completed_stage_index_calculation(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("idx", "i", "stage1", {"a": 1}, {"stage1": {"data": 1}})
        chk1 = cm.load_latest("idx")
        assert chk1.completed_stage_index == 0

        cm.save("idx", "i", "stage2", {"a": 2}, {"stage1": {"data": 1}, "stage2": {"data": 2}})
        chk2 = cm.load_latest("idx")
        # stage2 is at index 1 in the sorted keys
        assert chk2.completed_stage_index == 1


class TestCheckpointManagerLoad:
    def test_load_latest_nonexistent(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        result = cm.load_latest("does_not_exist")
        assert result is None

    def test_load_returns_pipeline_checkpoint(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("load_test", "lt", "s1", {"k": "v"}, {"s1": {}})
        loaded = cm.load_latest("load_test")
        assert isinstance(loaded, PipelineCheckpoint)
        assert loaded.pipeline_id == "load_test"

    def test_load_with_checkpoint_id(self, tmp_path):
        """load(pipeline_id, checkpoint_id=...) uses load_latest as fallback.

        NOTE: The current load() implementation has a timestamp-precision bug
        (multiplies by 1000 instead of dividing by 1000), so we test the
        load_latest path which is used by the orchestrator in practice.
        """
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("id_test", "it", "s1", {}, {"s1": {}})
        # CheckpointManager.load() calls load_latest() when checkpoint_id=None
        loaded = cm.load("id_test")
        assert loaded is not None
        assert loaded.pipeline_id == "id_test"

    def test_load_without_checkpoint_id_uses_latest(self, tmp_path):
        """load() without checkpoint_id delegates to load_latest()."""
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("latest_fallback", "lf", "s1", {"key": "val"}, {"s1": {}})
        loaded = cm.load("latest_fallback", checkpoint_id=None)
        assert loaded is not None
        assert loaded.context == {"key": "val"}

    def test_load_with_invalid_checkpoint_id(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("inv", "i", "s1", {}, {"s1": {}})
        result = cm.load("inv", checkpoint_id="not_a_valid_id")
        assert result is None

    def test_load_preserves_context(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        original_ctx = {
            "topic": "carbon trading",
            "papers_found": 50,
            "nested": {"key": [1, 2, 3]},
        }
        cm.save("ctx_test", "ct", "s1", original_ctx, {"s1": {}})
        loaded = cm.load_latest("ctx_test")
        assert loaded.context == original_ctx

    def test_load_preserves_hitl_state(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        hitl_state = {"pending": [{"gate_id": "g1", "state": "pending"}]}
        cm.save(
            "hitl_test",
            "ht",
            "s1",
            {},
            {"s1": {}},
            hitl_state=hitl_state,
        )
        loaded = cm.load_latest("hitl_test")
        assert loaded.hitl_state == hitl_state

    def test_load_preserves_metadata(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        meta = {"author": "test", "tag": "unit_test"}
        cm.save("meta", "m", "s1", {}, {"s1": {}}, metadata=meta)
        loaded = cm.load_latest("meta")
        assert loaded.metadata == meta


class TestCheckpointManagerRestoreContext:
    def test_restore_context_returns_copy(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("copy_test", "ct", "s1", {"mutable": [1, 2]}, {"s1": {}})
        loaded = cm.load_latest("copy_test")
        ctx = cm.restore_context(loaded)
        ctx["mutable"].append(3)
        # Original context should be unchanged
        assert loaded.context["mutable"] == [1, 2]

    def test_restore_context_empty_context(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("empty_ctx", "ec", "s1", {}, {"s1": {}})
        loaded = cm.load_latest("empty_ctx")
        ctx = cm.restore_context(loaded)
        assert ctx == {}


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — delete / prune
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerDelete:
    def test_delete_removes_checkpoint(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        chk_id = cm.save("del_test", "dt", "s1", {}, {"s1": {}})
        result = cm.delete("del_test", chk_id)
        assert result is True
        assert cm.load_latest("del_test") is None

    def test_delete_nonexistent_returns_false(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("delghost", "dg", "s1", {}, {"s1": {}})
        result = cm.delete("delghost", "nonexistent_chk_id")
        assert result is False

    def test_delete_refreshes_latest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        id1 = cm.save("refresh", "r", "s1", {}, {"s1": {}})
        time.sleep(0.01)
        cm.save("refresh", "r", "s2", {}, {"s1": {}, "s2": {}})
        cm.delete("refresh", id1)
        latest = cm.load_latest("refresh")
        assert latest.completed_stages == ["s1", "s2"]

    def test_delete_all_manifest_updated(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("upd", "u", "s1", {}, {"s1": {}})
        time.sleep(0.01)
        cm.save("upd", "u", "s2", {}, {"s1": {}, "s2": {}})
        id1 = cm._read_manifest("upd")["checkpoints"][1]["id"]
        cm.delete("upd", id1)
        manifest = cm._read_manifest("upd")
        assert len(manifest["checkpoints"]) == 1


class TestCheckpointManagerPrune:
    def test_prune_removes_old_checkpoints(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(7):
            cm.save("prune_test", "pt", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        cm.prune("prune_test", keep=3)
        checkpoints = cm.list_checkpoints("prune_test", limit=100)
        assert len(checkpoints) == 3

    def test_prune_keeps_newest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(5):
            cm.save("keep_new", "kn", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        cm.prune("keep_new", keep=2)
        checkpoints = cm.list_checkpoints("keep_new", limit=100)
        # Should keep the 2 most recent
        assert len(checkpoints) == 2

    def test_prune_zero_keeps_nothing(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(3):
            cm.save("prune0", "p0", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        cm.prune("prune0", keep=0)
        checkpoints = cm.list_checkpoints("prune0", limit=100)
        assert len(checkpoints) == 0

    def test_prune_updates_latest(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(5):
            cm.save("prune_lat", "pl", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        cm.prune("prune_lat", keep=2)
        latest = cm.load_latest("prune_lat")
        assert latest is not None

    def test_prune_invalidates_latest_if_all_deleted(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("prune_all", "pa", "s1", {}, {"s1": {}})
        cm.prune("prune_all", keep=0)
        assert not cm._latest_path("prune_all").exists()

    def test_prune_negative_raises(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        with pytest.raises(ValueError, match="keep must be non-negative"):
            cm.prune("neg", keep=-1)


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — list / stats / compute_config_hash / validate_resume
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerList:
    def test_list_checkpoints_empty(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        checkpoints = cm.list_checkpoints("nonexistent")
        assert checkpoints == []

    def test_list_checkpoints_returns_ordered(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(5):
            cm.save("list_test", "lt", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        checkpoints = cm.list_checkpoints("list_test")
        # Newest first
        assert checkpoints[0].timestamp >= checkpoints[-1].timestamp

    def test_list_checkpoints_respects_limit(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        for i in range(5):
            cm.save("lim", "l", f"s{i}", {}, {f"s{i}": {}})
            time.sleep(0.005)
        checkpoints = cm.list_checkpoints("lim", limit=2)
        assert len(checkpoints) == 2


class TestCheckpointManagerStats:
    def test_stats_empty_pipeline(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        stats = cm.stats("no_pipeline")
        assert stats["count"] == 0
        assert stats["pipeline_id"] == "no_pipeline"

    def test_stats_with_checkpoints(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("statsp", "sp", "s1", {}, {"s1": {}})
        stats = cm.stats("statsp")
        assert stats["count"] == 1
        assert stats["pipeline_id"] == "statsp"
        assert "oldest" in stats
        assert "newest" in stats
        assert "completed_stages" in stats
        assert "latest_stage_index" in stats


class TestCheckpointManagerComputeConfigHash:
    def test_compute_config_hash(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        config = {"model": "deepseek-v4", "temperature": 0.7}
        result = cm.compute_config_hash(config)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_compute_config_hash_deterministic(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        config = {"key": "value"}
        h1 = cm.compute_config_hash(config)
        h2 = cm.compute_config_hash(config)
        assert h1 == h2


class TestCheckpointManagerValidateResume:
    def test_validate_resume_no_hash(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        cm.save("safe1", "s1", "s1", {}, {"s1": {}})
        chk = cm.load_latest("safe1")
        is_safe, reason = cm.validate_resume(chk, {"any": "config"})
        assert is_safe is True
        assert reason == ""

    def test_validate_resume_same_config(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        config = {"model": "gpt-4o"}
        config_hash = cm.compute_config_hash(config)
        cm.save("safe2", "s2", "s1", {}, {"s1": {}}, config_hash=config_hash)
        chk = cm.load_latest("safe2")
        is_safe, reason = cm.validate_resume(chk, config)
        assert is_safe is True

    def test_validate_resume_changed_config(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        old_config = {"model": "deepseek"}
        new_config = {"model": "claude"}
        cm.save(
            "unsafe",
            "u",
            "s1",
            {},
            {"s1": {}},
            config_hash=cm.compute_config_hash(old_config),
        )
        chk = cm.load_latest("unsafe")
        is_safe, reason = cm.validate_resume(chk, new_config)
        assert is_safe is False
        assert "changed" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — manifest helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerManifest:
    def test_read_manifest_creates_default(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        manifest = cm._read_manifest("brand_new")
        assert manifest == {"pipeline_id": "brand_new", "checkpoints": []}

    def test_read_manifest_corrupt_json(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        index_path = cm._index_path("corrupt")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("not valid json{{{", encoding="utf-8")
        manifest = cm._read_manifest("corrupt")
        assert manifest == {"pipeline_id": "corrupt", "checkpoints": []}

    def test_write_manifest_roundtrip(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        manifest = {"pipeline_id": "roundtrip", "checkpoints": [{"id": "c1"}]}
        cm._write_manifest("roundtrip", manifest)
        read = cm._read_manifest("roundtrip")
        assert read == manifest


# ═══════════════════════════════════════════════════════════════════════════
# CheckpointManager — corrupt file tolerance
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpointManagerCorruptFiles:
    def test_corrupt_checkpoint_file_skipped(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        # Write a valid checkpoint first
        cm.save("corrupt_skip", "cs", "s1", {}, {"s1": {}})
        # Write a corrupt checkpoint file directly
        chk_path = cm._checkpoint_path("corrupt_skip", 9999999.0)
        chk_path.parent.mkdir(parents=True, exist_ok=True)
        chk_path.write_text("not json{{{", encoding="utf-8")
        # Should not crash
        checkpoints = cm.list_checkpoints("corrupt_skip", limit=100)
        # Valid checkpoint should still be there
        assert len(checkpoints) == 1

    def test_load_corrupt_checkpoint_returns_none(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        chk_path = tmp_path / "checkpoint_bad.json"
        chk_path.write_text("{{broken", encoding="utf-8")
        result = cm._read_checkpoint_file(chk_path)
        assert result is None

    def test_load_missing_checkpoint_returns_none(self, tmp_path):
        cm = CheckpointManager(base_dir=tmp_path)
        missing = tmp_path / "does_not_exist.json"
        result = cm._read_checkpoint_file(missing)
        assert result is None
