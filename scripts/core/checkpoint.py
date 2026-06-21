"""Pipeline checkpoint system — save and restore agent pipeline execution state.

断点续传：保存每个 stage 完成后的完整状态，崩溃后可从断点恢复继续执行。

Architecture
------------
    PipelineCheckpoint  — frozen snapshot of a single completed stage
    CheckpointManager    — CRUD operations on checkpoints (JSON files)
    CheckpointableOrchestrator  — drop-in wrapper for AgentOrchestrator

Storage layout
--------------
    data/checkpoints/
        checkpoint_{pipeline_id}_{unix_ts}.json   # individual checkpoints
        checkpoint_{pipeline_id}_latest.json      # symlink / pointer to newest
        index_{pipeline_id}.json                 # ordered list of all checkpoint IDs

Integration with HITLGate
--------------------------
    After each stage the HITL gate state is serialised and stored in the
    checkpoint.  On restore the caller re-constructs a HITLGate from that dict
    and injects it via AgentOrchestrator.set_hitl_gate().

Usage
-----
    # ── Standalone ──────────────────────────────────────────────────────────
    cm = CheckpointManager()

    chk = cm.load_latest("paper_20260529")
    if chk:
        ctx  = cm.restore_context(chk)
        next_stage_idx = chk.completed_stage_index + 1
        hitl_state = chk.hitl_state

    for i, step in enumerate(all_steps[next_stage_idx:], start=next_stage_idx):
        result = agent.run(ctx)
        ctx[f"{step.stage.value}_result"] = result.output
        cm.save(
            pipeline_id="paper_20260529",
            pipeline_name="paper_pipeline",
            completed_stage=step.stage.value,
            context=ctx,
            stage_results={s.value: ctx.get(f"{s.value}_result")
                          for s in all_steps[:i + 1]},
            hitl_state=hgl.get_state() if hgl else None,
        )

    # ── With CheckpointableOrchestrator ──────────────────────────────────────
    base    = AgentOrchestrator(gateway)
    wrapped = CheckpointableOrchestrator(base)

    chk = wrapped.checkpoint_manager.load_latest("my_pipeline")
    start_from = 0
    context    = {}
    if chk:
        context    = wrapped.checkpoint_manager.restore_context(chk)
        start_from = chk.completed_stage_index + 1
        print(f"Resuming from stage {start_from}")

    result = wrapped.run_pipeline_with_checkpoints(
        pipeline_name="my_pipeline",
        steps=all_steps[start_from:],
        input_data=context,
        checkpoint_every=1,
    )
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "PipelineCheckpoint",
    "CheckpointManager",
    "CheckpointableOrchestrator",
    "PipelineTelemetry",
]

logger = logging.getLogger(__name__)


# ─── Dataclass ─────────────────────────────────────────────────────────────────


@dataclass
class PipelineCheckpoint:
    """
    Frozen snapshot captured after one pipeline stage completes.

    Attributes
    ----------
    pipeline_id : str
        Unique identifier for this pipeline run (e.g. "paper_20260529").
    pipeline_name : str
        Human-readable name of the pipeline template (e.g. "paper_pipeline").
    timestamp : float
        Unix timestamp when the checkpoint was written.
    completed_stage_index : int
        0-based index of the last completed stage.
        -1 means no stage has completed yet (initial checkpoint before any run).
    completed_stages : list[str]
        Ordered list of completed stage names.
    context : dict
        Full context dict *after* the last completed stage.
        This is what gets passed into the next stage.
    stage_results : dict[str, Any]
        Output dict of each completed stage keyed by stage name.
    hitl_state : dict | None
        Serialised HITLGate state (pending gates, history, etc.) at the time
        of the checkpoint.  None if no HITLGate is attached.
    config_hash : str
        SHA-256 hex digest of a canonical JSON serialisation of the pipeline
        definition.  Used to detect when the pipeline definition has changed
        between a checkpoint and a resume attempt.
    metadata : dict
        Arbitrary extra information (topic, user, tags, …).
    """

    pipeline_id: str
    pipeline_name: str
    timestamp: float
    completed_stage_index: int = -1
    completed_stages: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    stage_results: dict[str, Any] = field(default_factory=dict)
    hitl_state: dict | None = None
    config_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    random_seeds: dict[str, Any] = field(default_factory=dict)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_json(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for json.dumps."""
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "timestamp": self.timestamp,
            "completed_stage_index": self.completed_stage_index,
            "completed_stages": self.completed_stages,
            "context": self.context,
            "stage_results": self.stage_results,
            "hitl_state": self.hitl_state,
            "config_hash": self.config_hash,
            "metadata": self.metadata,
            "random_seeds": self.random_seeds,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PipelineCheckpoint:
        """Reconstruct a PipelineCheckpoint from a plain dict."""
        return cls(
            pipeline_id=data["pipeline_id"],
            pipeline_name=data["pipeline_name"],
            timestamp=data["timestamp"],
            completed_stage_index=data.get("completed_stage_index", -1),
            completed_stages=data.get("completed_stages", []),
            context=data.get("context", {}),
            stage_results=data.get("stage_results", {}),
            hitl_state=data.get("hitl_state"),
            config_hash=data.get("config_hash", ""),
            metadata=data.get("metadata", {}),
            random_seeds=data.get("random_seeds", {}),
        )

    # ── Convenience ──────────────────────────────────────────────────────────

    @property
    def checkpoint_id(self) -> str:
        """Stable ID for this checkpoint (derived from pipeline_id + timestamp in microseconds)."""
        return f"{self.pipeline_id}_{int(self.timestamp * 1_000_000)}"

    @property
    def is_empty(self) -> bool:
        """True when no stage has completed yet."""
        return self.completed_stage_index < 0

    def config_changed_since(self, new_config: Any) -> bool:
        """Return True if the pipeline definition has changed.

        ``new_config`` can be a JSON string or any serialisable object.
        If the checkpoint has no stored hash, returns False (no-change assumption).
        """
        if not self.config_hash:
            return False
        if isinstance(new_config, str):
            return self.config_hash != _sha256(new_config)
        return self.config_hash != _make_config_hash(new_config)


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_config_hash(config: Any) -> str:
    """Return a stable SHA-256 hash of a serialisable config object."""
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return _sha256(canonical)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically: write to temp file then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)          # atomic on POSIX
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ─── CheckpointManager ─────────────────────────────────────────────────────────


class CheckpointManager:
    """
    CRUD interface for pipeline checkpoints stored as JSON files.

    Directory layout
        {base_dir}/
            checkpoint_{pipeline_id}_{ts}.json     # individual snapshots
            checkpoint_{pipeline_id}_latest.json    # always points to newest
            index_{pipeline_id}.json               # ordered manifest

    Thread-safety
        All public methods acquire a shared file lock on the index file so
        that concurrent writers in the same process or from subprocesses do
        not corrupt the manifest.

    Partial-file tolerance
        If a checkpoint JSON is truncated or otherwise unreadable it is
        skipped silently (logged as a warning) rather than crashing the
        caller.
    """

    def __init__(
        self,
        base_dir: str | Path = "data/checkpoints",
        *,
        lock_timeout: float = 5.0,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock_timeout = lock_timeout

    # ── Path helpers ─────────────────────────────────────────────────────────

    def _checkpoint_path(self, pipeline_id: str, ts: float) -> Path:
        safe_id = _sanitise(pipeline_id)
        suffix = int(ts * 1_000_000)  # microseconds: avoids millisecond collision in fast loops
        return self.base_dir / f"checkpoint_{safe_id}_{suffix}.json"

    def _latest_path(self, pipeline_id: str) -> Path:
        safe_id = _sanitise(pipeline_id)
        return self.base_dir / f"checkpoint_{safe_id}_latest.json"

    def _index_path(self, pipeline_id: str) -> Path:
        safe_id = _sanitise(pipeline_id)
        return self.base_dir / f"index_{safe_id}.json"

    # ── Locking ─────────────────────────────────────────────────────────────

    def _lock_index(self, pipeline_id: str) -> tuple:
        """Acquire an exclusive lock on the index for this pipeline.

        Uses LOCK_NB (non-blocking) with a timeout loop so that a crashed process
        holding the lock does not deadlock other processes forever.
        """
        lock_path = self._index_path(pipeline_id).with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(lock_path, "w")   # create if absent
        deadline = time.time() + self._lock_timeout
        poll_interval = 0.1
        while time.time() < deadline:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_file
            except BlockingIOError:
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, 1.0)   # cap at 1s backoff
        lock_file.close()
        raise TimeoutError(
            f"Failed to acquire lock for pipeline '{pipeline_id}' "
            f"after {self._lock_timeout}s. "
            f"Another process may be holding the lock. "
            f"Remove stale lock: {lock_path}"
        )

    @staticmethod
    def _unlock_index(lock_file) -> None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    # ── Core CRUD ────────────────────────────────────────────────────────────

    def save(
        self,
        pipeline_id: str,
        pipeline_name: str,
        completed_stage: str,
        context: dict[str, Any],
        stage_results: dict[str, Any],
        hitl_state: dict | None = None,
        config_hash: str = "",
        metadata: dict[str, Any] | None = None,
        random_seeds: dict[str, Any] | None = None,
    ) -> str:
        """
        Persist a checkpoint after a stage completes.

        Parameters
        ----------
        pipeline_id : str
            Unique identifier for this run.
        pipeline_name : str
            Human-readable pipeline template name.
        completed_stage : str
            Name of the stage that just finished.
        context : dict
            Full execution context after this stage.
        stage_results : dict
            Accumulated outputs of all completed stages.
        hitl_state : dict | None
            Optional serialised HITLGate state.
        config_hash : str
            SHA-256 of the pipeline definition (empty to skip config check).
        metadata : dict | None
            Extra information to store alongside.
        random_seeds : dict | None
            Optional random seed state captured before the stage ran.
            If not provided, attempts to capture numpy.random.get_state().

        Returns
        -------
        str
            The written checkpoint's filename (without directory).
        """
        all_stages = list(stage_results.keys())
        stage_index = all_stages.index(completed_stage) if completed_stage in all_stages else len(all_stages) - 1

        # Capture random seeds if not provided
        seeds = dict(random_seeds) if random_seeds is not None else {}
        if not seeds:
            try:
                import numpy as _np
                seeds["numpy_random_state"] = str(_np.random.get_state())
            except Exception as exc:
                logger.debug("[CheckpointManager] NumPy seed not captured: %s", exc)

        checkpoint = PipelineCheckpoint(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            timestamp=time.time(),
            completed_stage_index=stage_index,
            completed_stages=all_stages,
            context=context,
            stage_results=stage_results,
            hitl_state=hitl_state,
            config_hash=config_hash,
            metadata=metadata or {},
            random_seeds=seeds,
        )

        lock_file = self._lock_index(pipeline_id)
        try:
            # ── Write checkpoint file ──────────────────────────────────────
            chk_path = self._checkpoint_path(pipeline_id, checkpoint.timestamp)
            _atomic_write_json(chk_path, checkpoint.to_json())

            # ── Update latest pointer ──────────────────────────────────────
            latest_path = self._latest_path(pipeline_id)
            _atomic_write_json(latest_path, checkpoint.to_json())

            # ── Update manifest ────────────────────────────────────────────
            manifest = self._read_manifest(pipeline_id)
            manifest["checkpoints"].insert(0, {
                "id": checkpoint.checkpoint_id,
                "path": str(chk_path),
                "timestamp": checkpoint.timestamp,
                "completed_stage": completed_stage,
                "completed_stage_index": stage_index,
            })
            self._write_manifest(pipeline_id, manifest)

            logger.info(
                "[CheckpointManager] Saved checkpoint %s  stage=%s  idx=%d",
                checkpoint.checkpoint_id,
                completed_stage,
                stage_index,
            )

            return checkpoint.checkpoint_id
        finally:
            self._unlock_index(lock_file)

    def load(
        self,
        pipeline_id: str,
        checkpoint_id: str | None = None,
    ) -> PipelineCheckpoint | None:
        """
        Load a checkpoint by ID, or the latest if ``checkpoint_id`` is None.

        Returns None when:
            - No checkpoint for this pipeline exists at all
            - The requested ``checkpoint_id`` is not found
            - The JSON file is corrupt / truncated (logged as warning)
        """
        if checkpoint_id:
            # Reconstruct path from checkpoint_id format: "{pipeline_id}_{ts_ms}"
            ts_str = checkpoint_id.rsplit("_", 1)[-1]
            try:
                ts = int(ts_str) / 1000.0
            except ValueError:
                logger.warning("[CheckpointManager] Malformed checkpoint_id %r", checkpoint_id)
                return None
            path = self._checkpoint_path(pipeline_id, ts)
            return self._read_checkpoint_file(path)

        return self.load_latest(pipeline_id)

    def load_latest(self, pipeline_id: str) -> PipelineCheckpoint | None:
        """
        Return the most recent checkpoint for ``pipeline_id``, or None.
        """
        latest_path = self._latest_path(pipeline_id)
        chk = self._read_checkpoint_file(latest_path)
        if chk is None:
            logger.debug("[CheckpointManager] No latest checkpoint for %s", pipeline_id)
        return chk

    def list_checkpoints(
        self,
        pipeline_id: str,
        limit: int = 20,
    ) -> list[PipelineCheckpoint]:
        """
        List all checkpoints for a pipeline, newest first.

        Parameters
        ----------
        pipeline_id : str
        limit : int
            Maximum number of checkpoints to return (default 20).

        Returns
        -------
        list[PipelineCheckpoint]
        """
        manifest = self._read_manifest(pipeline_id)
        checkpoints: list[PipelineCheckpoint] = []

        for entry in manifest.get("checkpoints", [])[:limit]:
            path = Path(entry["path"])
            chk = self._read_checkpoint_file(path)
            if chk is not None:
                checkpoints.append(chk)

        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints

    def restore_context(
        self,
        checkpoint: PipelineCheckpoint,
    ) -> dict[str, Any]:
        """
        Reconstruct the context dict ready to pass to the next stage.

        The returned dict is a deep copy — callers may mutate it freely.
        """
        import copy
        return copy.deepcopy(checkpoint.context)

    def delete(
        self,
        pipeline_id: str,
        checkpoint_id: str,
    ) -> bool:
        """
        Delete a specific checkpoint.

        Returns True if the file existed and was removed, False if it was
        already absent.
        """
        lock_file = self._lock_index(pipeline_id)
        try:
            # Find the path from the manifest
            manifest = self._read_manifest(pipeline_id)
            entry_to_remove = None
            for entry in manifest.get("checkpoints", []):
                if entry["id"] == checkpoint_id:
                    entry_to_remove = entry
                    break

            if entry_to_remove is None:
                return False

            path = Path(entry_to_remove["path"])
            if path.exists():
                path.unlink()
                logger.info("[CheckpointManager] Deleted checkpoint %s", checkpoint_id)

            # Rebuild manifest without this entry
            manifest["checkpoints"] = [
                e for e in manifest.get("checkpoints", [])
                if e["id"] != checkpoint_id
            ]
            self._write_manifest(pipeline_id, manifest)

            # Refresh latest if we deleted the newest
            remaining = self.list_checkpoints(pipeline_id, limit=1)
            latest_path = self._latest_path(pipeline_id)
            if remaining:
                _atomic_write_json(latest_path, remaining[0].to_json())
            elif latest_path.exists():
                latest_path.unlink()

            return True
        finally:
            self._unlock_index(lock_file)

    def prune(self, pipeline_id: str, keep: int = 5) -> int:
        """
        Delete all but the ``keep`` most recent checkpoints.

        Parameters
        ----------
        pipeline_id : str
        keep : int
            Number of newest checkpoints to retain (default 5).

        Returns
        -------
        int
            Number of checkpoints actually deleted.
        """
        if keep < 0:
            raise ValueError(f"keep must be non-negative, got {keep}")

        lock_file = self._lock_index(pipeline_id)
        deleted = 0
        try:
            manifest = self._read_manifest(pipeline_id)
            all_entries = manifest.get("checkpoints", [])

            to_delete = all_entries[keep:]
            for entry in to_delete:
                path = Path(entry["path"])
                try:
                    if path.exists():
                        path.unlink()
                        logger.debug("[CheckpointManager] Pruned %s", entry["id"])
                        deleted += 1
                except OSError as exc:
                    logger.warning("Failed to delete checkpoint %s: %s", entry["id"], exc)

            manifest["checkpoints"] = all_entries[:keep]
            self._write_manifest(pipeline_id, manifest)

            # Refresh latest pointer
            remaining = self.list_checkpoints(pipeline_id, limit=1)
            latest_path = self._latest_path(pipeline_id)
            if remaining:
                _atomic_write_json(latest_path, remaining[0].to_json())
            elif latest_path.exists():
                latest_path.unlink()

            logger.info("[CheckpointManager] Pruned %d checkpoints for %s (kept %d)",
                        deleted, pipeline_id, keep)
            return deleted
        finally:
            self._unlock_index(lock_file)

    # ── Internal manifest helpers ────────────────────────────────────────────

    def _read_manifest(self, pipeline_id: str) -> dict[str, Any]:
        path = self._index_path(pipeline_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"pipeline_id": pipeline_id, "checkpoints": []}

    def _write_manifest(self, pipeline_id: str, manifest: dict[str, Any]) -> None:
        index_path = self._index_path(pipeline_id)
        _atomic_write_json(index_path, manifest)

    def _read_checkpoint_file(self, path: Path) -> PipelineCheckpoint | None:
        """Read a checkpoint file, returning None on any error."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PipelineCheckpoint.from_json(data)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "[CheckpointManager] Corrupt checkpoint file %s: %s — skipping",
                path,
                exc,
            )
            return None

    # ── Convenience ──────────────────────────────────────────────────────────

    def compute_config_hash(self, config: Any) -> str:
        """Hash a pipeline config object. Use to generate config_hash for save()."""
        return _make_config_hash(config)

    def validate_resume(
        self,
        checkpoint: PipelineCheckpoint,
        current_config: Any,
    ) -> tuple[bool, str]:
        """
        Check whether it is safe to resume from a checkpoint.

        Returns
        -------
        (is_safe, reason)
            is_safe : bool
            reason  : str  — human-readable explanation (empty when safe)
        """
        if checkpoint.config_hash and checkpoint.config_changed_since(current_config):
            return False, (
                "Pipeline definition has changed since checkpoint was created. "
                "Resuming with a different config may produce inconsistent results."
            )
        return True, ""

    def stats(self, pipeline_id: str) -> dict[str, Any]:
        """Return basic statistics for a pipeline's checkpoints."""
        checkpoints = self.list_checkpoints(pipeline_id, limit=1000)
        if not checkpoints:
            return {"count": 0, "pipeline_id": pipeline_id}

        timestamps = [c.timestamp for c in checkpoints]
        return {
            "count": len(checkpoints),
            "pipeline_id": pipeline_id,
            "oldest": datetime.fromtimestamp(min(timestamps)).isoformat(),
            "newest": datetime.fromtimestamp(max(timestamps)).isoformat(),
            "completed_stages": checkpoints[0].completed_stages,
            "latest_stage_index": checkpoints[0].completed_stage_index,
        }


# ─── CheckpointableOrchestrator ─────────────────────────────────────────────────


class CheckpointableOrchestrator:
    """
    Drop-in wrapper that adds automatic checkpointing to an AgentOrchestrator.

    Usage
    -----
        from scripts.core.orchestrator import AgentOrchestrator, PipelineStep, PipelineStage
        from scripts.core.checkpoint import CheckpointableOrchestrator

        base    = AgentOrchestrator(gateway)
        wrapped = CheckpointableOrchestrator(base)

        # ── Fresh start ────────────────────────────────────────────────────
        result = wrapped.run_pipeline_with_checkpoints(
            pipeline_name="my_paper",
            steps=all_steps,
            input_data={"topic": "..."},
            checkpoint_every=1,        # after every stage
        )

        # ── Resume after crash ───────────────────────────────────────────
        chk = wrapped.checkpoint_manager.load_latest("my_paper")
        if chk:
            ctx  = wrapped.checkpoint_manager.restore_context(chk)
            next_idx = chk.completed_stage_index + 1
            result = wrapped.run_pipeline_with_checkpoints(
                pipeline_name="my_paper",
                steps=all_steps[next_idx:],
                input_data=ctx,
                checkpoint_every=1,
            )

    Parameters
    ----------
    base : AgentOrchestrator
        The underlying orchestrator to wrap.
    base_dir : str | Path
        Directory for checkpoint files (default "data/checkpoints").
    checkpoint_every : int
        Default checkpoint interval (number of completed stages between
        saves).  1 = every stage.  0 = only at the very end.
    auto_load_hitl : bool
        If True (default), automatically re-inject the HITL state from the
        checkpoint into the base orchestrator on resume.
    """

    def __init__(
        self,
        base: AgentOrchestrator,
        base_dir: str | Path = "data/checkpoints",
        checkpoint_every: int = 1,
        auto_load_hitl: bool = True,
    ):
        self.base = base
        self.checkpoint_manager = CheckpointManager(base_dir=base_dir)
        self.checkpoint_every = checkpoint_every
        self.auto_load_hitl = auto_load_hitl

    # ── Public API ───────────────────────────────────────────────────────────

    def run_pipeline_with_checkpoints(
        self,
        pipeline_name: str,
        steps: list[PipelineStep],
        input_data: dict[str, Any],
        config: Any = None,
        hitl_gate=None,
        parallel: bool = False,
        max_workers: int = 4,
        checkpoint_every: int | None = None,
    ) -> PipelineResult:
        """
        Run a pipeline with automatic checkpointing.

        After each stage that should be checkpointed the manager is called
        automatically.  If the process crashes the caller can call this same
        method again with the remaining steps and the context restored from
        the latest checkpoint.

        Parameters
        ----------
        pipeline_name : str
            Unique identifier for this run (used as pipeline_id).
        steps : list[PipelineStep]
            Remaining steps to execute (can be a slice of the full list).
        input_data : dict
            Context dict to pass to the first step (already restored).
        config : Any
            Pipeline definition used to compute config_hash for validation.
            Can be a dict, a list of steps, or any JSON-serialisable object.
        hitl_gate : HITLGate | None
            Optional HITL gate to pass to the base orchestrator.
        checkpoint_every : int | None
            Override the default interval (default None → use self.checkpoint_every).
        parallel, max_workers
            Passed through to ``base.run_pipeline``.

        Returns
        -------
        PipelineResult
        """
        interval = checkpoint_every if checkpoint_every is not None else self.checkpoint_every
        pipeline_id = _sanitise(pipeline_name)
        config_hash = self.checkpoint_manager.compute_config_hash(config) if config else ""

        # Inject HITL state from latest checkpoint if auto_load_hitl is enabled
        if self.auto_load_hitl and hitl_gate is None:
            latest = self.checkpoint_manager.load_latest(pipeline_id)
            if latest and latest.hitl_state:
                hitl_gate = self._reconstruct_hitl_gate(latest.hitl_state)
                self.base.set_hitl_gate(hitl_gate)

        # Keep a running accumulation of stage results for the next checkpoint
        stage_results: dict[str, Any] = {}
        context = dict(input_data)

        # Detect how many stages we are about to skip (used for index offset)
        latest = self.checkpoint_manager.load_latest(pipeline_id)
        offset = (latest.completed_stage_index + 1) if latest else 0

        for i, step in enumerate(steps):
            # Set up HITL gate if provided
            if hitl_gate is not None:
                self.base.set_hitl_gate(hitl_gate)

            result = self.base.run_pipeline(
                pipeline_name=pipeline_name,
                steps=[step],
                input_data=context,
                parallel=False,
                max_workers=max_workers,
            )

            # Update accumulated state
            context[f"{step.stage.value}_result"] = result.final_context.get(
                f"{step.stage.value}_result", {}
            )
            stage_results[step.stage.value] = result.final_context.get(
                f"{step.stage.value}_result", {}
            )

            current_idx = offset + i

            # Decide whether to save a checkpoint
            if interval > 0 and (current_idx + 1) % interval == 0:
                hitl_state = self._capture_hitl_state(hitl_gate)
                checkpoint_id = self.checkpoint_manager.save(
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_name,
                    completed_stage=step.stage.value,
                    context=context,
                    stage_results=dict(stage_results),
                    hitl_state=hitl_state,
                    config_hash=config_hash,
                    metadata={
                        "total_steps": len(steps),
                        "current_step": i + 1,
                        "offset": offset,
                    },
                )

                # Auto-export provenance report after each checkpoint
                try:
                    from scripts.core.provenance import get_chain
                    chain = get_chain()
                    if chain:
                        report_path = Path(f"output/provenance/checkpoint_{checkpoint_id[:8]}.md")
                        chain.export_report(report_path)
                        logger.info(f"Provenance report saved: {report_path}")
                except Exception as exc:
                    logger.warning(f"Failed to export provenance report: {exc}")

            # If pipeline was paused at a HITL gate, stop checkpointing
            if result.hitl_paused_at is not None:
                hitl_state = self._capture_hitl_state(hitl_gate)
                checkpoint_id = self.checkpoint_manager.save(
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_name,
                    completed_stage=step.stage.value,
                    context=context,
                    stage_results=dict(stage_results),
                    hitl_state=hitl_state,
                    config_hash=config_hash,
                    metadata={
                        "total_steps": len(steps),
                        "current_step": i + 1,
                        "offset": offset,
                        "hitl_paused": True,
                    },
                )

                # Auto-export provenance report after HITL pause checkpoint
                try:
                    from scripts.core.provenance import get_chain
                    chain = get_chain()
                    if chain:
                        report_path = Path(f"output/provenance/checkpoint_{checkpoint_id[:8]}.md")
                        chain.export_report(report_path)
                        logger.info(f"Provenance report saved: {report_path}")
                except Exception as exc:
                    logger.warning(f"Failed to export provenance report: {exc}")
                return result

        return result

    # ── HITL helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _capture_hitl_state(gate) -> dict | None:
        """Serialise a HITLGate into a plain dict."""
        if gate is None:
            return None
        try:
            pending = [
                {"gate_id": r.gate_id, "stage": r.stage, "state": r.state.value,
                 "content": r.content, "question": r.question}
                for r in gate.get_pending()
            ]
            history = [
                {"gate_id": r.gate_id, "stage": r.stage, "state": r.state.value,
                 "feedback": r.feedback, "held_at": r.held_at, "decided_at": r.decided_at}
                for r in gate.get_history(limit=100)
            ]
            return {
                "pending": pending,
                "history": history,
                "stats": gate.stats(),
            }
        except Exception as exc:
            logger.warning("[CheckpointableOrchestrator] Failed to capture HITL state: %s", exc)
            return None

    @staticmethod
    def _reconstruct_hitl_gate(state: dict):
        """
        Reconstruct a HITLGate from a serialised state dict.

        Creates a fresh HITLGate and injects any pending approval records
        back into it so that a resumed pipeline can query its pending gates.
        """
        from scripts.core.hitl_gate import ApprovalRecord, GateState, HITLGate

        gate = HITLGate()

        for pending_entry in state.get("pending", []):
            gate._pending[pending_entry["gate_id"]] = ApprovalRecord(
                gate_id=pending_entry["gate_id"],
                stage=pending_entry["stage"],
                state=GateState[pending_entry["state"]],
                content=pending_entry.get("content", {}),
                question=pending_entry.get("question", ""),
                held_at=time.time(),
            )

        for hist_entry in state.get("history", []):
            record = ApprovalRecord(
                gate_id=hist_entry["gate_id"],
                stage=hist_entry["stage"],
                state=GateState[hist_entry["state"]],
                feedback=hist_entry.get("feedback", ""),
                held_at=hist_entry.get("held_at", time.time()),
                decided_at=hist_entry.get("decided_at"),
            )
            gate._history.append(record)

        return gate

    # ── Convenience ──────────────────────────────────────────────────────────

    def resume(
        self,
        pipeline_name: str,
        steps: list[PipelineStep],
        config: Any = None,
        hitl_gate=None,
    ) -> PipelineResult:
        """
        Shortcut: load latest checkpoint and resume pipeline from there.

        Returns PipelineResult from the wrapped run.
        """
        pipeline_id = _sanitise(pipeline_name)
        chk = self.checkpoint_manager.load_latest(pipeline_id)
        if chk is None:
            raise ValueError(f"No checkpoint found for pipeline {pipeline_name}")

        is_safe, reason = self.checkpoint_manager.validate_resume(chk, config)
        if not is_safe:
            logger.warning(
                "[CheckpointableOrchestrator] Unsafe resume: %s  "
                "Use force=True to override.",
                reason,
            )
            raise ValueError(f"Unsafe resume: {reason}")

        context = self.checkpoint_manager.restore_context(chk)

        return self.run_pipeline_with_checkpoints(
            pipeline_name=pipeline_name,
            steps=steps[chk.completed_stage_index + 1:],
            input_data=context,
            config=config,
            hitl_gate=hitl_gate,
        )

    def get_stats(self, pipeline_name: str) -> dict[str, Any]:
        """Return checkpoint statistics for a pipeline."""
        pipeline_id = _sanitise(pipeline_name)
        return self.checkpoint_manager.stats(pipeline_id)


# ─── Utility ───────────────────────────────────────────────────────────────────


def _sanitise(name: str) -> str:
    """Replace characters that are unsafe in filenames."""
    import re
    return re.sub(r"[^\w\-_.]", "_", name)


# ─── Pipeline Telemetry ─────────────────────────────────────────────────────────


@dataclass
class PipelineTelemetry:
    """Tracks execution metrics for a pipeline run."""
    pipeline_id: str
    stage_durations: dict[str, float] = field(default_factory=dict)
    token_counts: dict[str, int] = field(default_factory=dict)
    api_call_counts: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)
    mcp_call_counts: dict[str, int] = field(default_factory=dict)
    checkpoint_ids: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    def record_stage(self, stage: str, duration: float) -> None:
        self.stage_durations[stage] = duration

    def record_token(self, model: str, tokens: int) -> None:
        self.token_counts[model] = self.token_counts.get(model, 0) + tokens

    def record_api_call(self, tool_name: str) -> None:
        self.api_call_counts[tool_name] = self.api_call_counts.get(tool_name, 0) + 1

    def record_error(self, error_type: str) -> None:
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    def record_mcp_call(self, mcp_server: str) -> None:
        self.mcp_call_counts[mcp_server] = self.mcp_call_counts.get(mcp_server, 0) + 1

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "stages": self.stage_durations,
            "total_duration": sum(self.stage_durations.values()),
            "tokens": self.token_counts,
            "api_calls": self.api_call_counts,
            "errors": self.error_counts,
            "mcp_calls": self.mcp_call_counts,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else Path("data/pipeline_telemetry.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(self.to_dict()) + "\n")
        return path


# Global telemetry instance
_pipeline_telemetry: dict[str, PipelineTelemetry] = {}


def get_telemetry(pipeline_id: str) -> PipelineTelemetry:
    """Get or create telemetry for a pipeline run."""
    if pipeline_id not in _pipeline_telemetry:
        _pipeline_telemetry[pipeline_id] = PipelineTelemetry(pipeline_id=pipeline_id)
    return _pipeline_telemetry[pipeline_id]
