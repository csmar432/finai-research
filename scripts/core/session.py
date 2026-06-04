"""ResearchSession: Session orchestrator tying together all four core modules.

Architecture:
    ResearchSession
        ├── memory: ResearchMemory       — three-layer memory (context / short-term / long-term)
        ├── llm: LLMGateway              — unified LLM routing with caching and cost tracking
        ├── planner: ResearchPlanner     — task decomposition + topological execution + fallback
        ├── tool_selector: ToolSelector  — MCP + script tool routing
        └── reflector: ResearchReflector — four-dimensional result evaluation

Execution modes:
    - Sequential (default): tasks execute one-by-one in topological order
    - Parallel: dependency-free tasks execute concurrently (max_workers configurable)

User-facing entry point for the economic research agent.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.core.llm_gateway import LLMGateway
from scripts.core.memory import ResearchMemory
from scripts.core.planner import ResearchPlanner, Task, TaskStatus
from scripts.core.reflector import Evaluation, ResearchReflector
from scripts.core.tool_selector import ToolSelection, ToolSelector

# ─── Session State & Status ────────────────────────────────────────────────────


class SessionState(Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SessionStatus:
    """Snapshot of the current session's progress."""
    state: SessionState
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    avg_score: float | None = None


# ─── Session Config ────────────────────────────────────────────────────────────


@dataclass
class SessionConfig:
    """Configuration for a ResearchSession."""
    session_id: str
    user_goal: str
    workspace_root: Path = Path(".")
    auto_save: bool = True
    max_context_items: int = 20
    max_retries: int = 3
    verbose: bool = False
    db_path: str | None = None
    # ── Execution mode ────────────────────────────────────────────
    parallel: bool = False            # Enable parallel execution
    max_workers: int = 4              # Max concurrent tasks in parallel mode
    # ── Progress callback ────────────────────────────────────────
    progress_callback: Callable[[str, Task, float], None] | None = None
    # ── LLM settings ─────────────────────────────────────────────
    llm_use_cache: bool = True       # Enable LLM response caching


# ─── ResearchSession ───────────────────────────────────────────────────────────


class ResearchSession:
    """
    Session orchestrator that ties together all four core modules.

    This is the main user-facing entry point for the economic research agent.
    It manages the lifecycle of a research session: decomposition, execution,
    evaluation, and persistence.

    Execution modes:
        - parallel=False (default): sequential topological execution
        - parallel=True: concurrent execution of dependency-free tasks

    Example usage:
        session = ResearchSession(SessionConfig(
            session_id="茅台财务分析_20260523",
            user_goal="分析贵州茅台2024年财务数据和投资价值",
        ))

        # Sequential execution
        result = session.run("帮我分析茅台的ROE和毛利率")

        # Parallel execution
        result = session.run("同时分析茅台和五粮液的财务数据", parallel=True)

        # Follow-up
        followup = session.ask("再对比一下五粮液")

        # Pause & resume
        session.pause()
        restored = session.resume()

        # Progress tracking
        def on_progress(phase: str, task: Task, progress: float):
            print(f"[{phase}] {task.description}: {progress:.0%}")

        session = ResearchSession(SessionConfig(
            session_id="test",
            user_goal="分析",
            progress_callback=on_progress,
        ))
    """

    def __init__(self, config: SessionConfig):
        self.config = config
        self.memory = ResearchMemory(
            session_id=config.session_id,
            db_path=config.db_path,
        )
        self.llm = LLMGateway(self.memory, use_cache=config.llm_use_cache)
        self.planner = ResearchPlanner(self.memory)
        self.tool_selector = ToolSelector(self.memory)
        self.reflector = ResearchReflector(self.memory)
        self._task_results: dict[str, Any] = {}
        self._state = SessionState.CREATED
        self._created_at = time.time()
        # ── Parallel execution state ──────────────────────────────
        self._running_task_count = 0
        self._running_task_count_lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Initially not paused

        # ── Self-Evolution Integration ─────────────────────────────
        self._evolution_engine: Any | None = None
        self._evolution_activated: bool = False

    def enable_self_evolution(
        self,
        engine: Any | None = None,
        log_path: str | None = None,
        quality_baseline: float = 0.7,
    ) -> dict[str, Any]:
        """
        启用自进化引擎，将 ResearchSession 与 SEPL 协议集成。

        Parameters
        ----------
        engine : Any | None
            外部提供的 SelfEvolutionEngine 实例。
            如果为 None，则创建新实例。
        log_path : str | None
            进化历史日志路径。
        quality_baseline : float
            质量基准线，低于此值触发进化。

        Returns
        -------
        dict[str, Any]
            激活状态摘要。
        """
        if self._evolution_activated:
            return {"status": "already_enabled", "engine_id": id(self._evolution_engine)}

        # 注册各组件到进化引擎
        if engine is None:
            from scripts.core.self_evolution import SelfEvolutionEngine
            engine = SelfEvolutionEngine(memory=self.memory, gateway=self.llm)

        engine.register_agent("planner", self.planner)
        engine.register_agent("tool_selector", self.tool_selector)
        engine.register_agent("reflector", self.reflector)

        # 激活引擎
        result = engine.activate(
            evolution_log_path=log_path,
            quality_baseline=quality_baseline,
        )

        self._evolution_engine = engine
        self._evolution_activated = True

        return {
            "status": "enabled",
            "engine": engine,
            "activation": result,
        }

    def disable_self_evolution(self) -> dict[str, Any]:
        """停用自进化引擎。"""
        if not self._evolution_activated or self._evolution_engine is None:
            return {"status": "not_enabled"}

        result = self._evolution_engine.deactivate()
        self._evolution_activated = False
        return result

    def _on_task_complete(
        self,
        task_id: str,
        result: Any,
    ) -> None:
        """
        任务完成回调：触发进化引擎评估。

        在每个任务执行完成后由 _execute_sequential / _execute_parallel 调用。
        """
        if not self._evolution_activated or self._evolution_engine is None:
            return

        try:
            self._evolution_engine.record_and_assess(
                agent_name=task_id,
                result=result,
                context={"session_id": self.config.session_id},
            )
        except Exception:
            pass  # 进化评估失败不影响主流程

    def get_evolution_status(self) -> dict[str, Any]:
        """返回自进化引擎状态。"""
        if not self._evolution_activated:
            return {"status": "not_enabled"}
        engine = self._evolution_engine
        return {
            "status": "enabled",
            "is_active": engine.is_active(),
            "events": len(engine._history),
            "proposals": len(engine._proposals),
        }

    def run(self, user_request: str) -> dict[str, Any]:
        """
        Execute a complete research session.

        Main flow:
        1. Planner.decompose(user_request) → task graph
        2. Topological execution:
           - Sequential: Kahn's algorithm, one-by-one
           - Parallel: layer-by-layer, max_workers concurrent
        3. Per-task: select → execute → evaluate → memory → save
        4. Return {session_id, tasks, summary, status}

        Parameters
        ----------
        user_request : str
            The user's research request or instruction.

        Returns
        -------
        dict[str, Any]
            {
                "session_id": str,
                "tasks": dict[str, dict],   # task_id → {result, evaluation}
                "summary": str,               # reflector.reflect() output
                "status": SessionStatus,
                "total_latency_ms": float,
            }
        """
        start_time = time.time()
        self._state = SessionState.RUNNING
        self._pause_event.set()  # Ensure not paused

        # Decompose user request into task graph
        tasks = self.planner.decompose(user_request)
        if self.config.verbose:
            print(f"[ResearchSession] Decomposed into {len(tasks)} root tasks")

        all_tasks = self._flatten_tasks(tasks)

        if self.config.parallel:
            self._execute_parallel(all_tasks)
        else:
            self._execute_sequential(all_tasks)

        # Session complete
        if any(
            r.get("evaluation", Evaluation("", False, 0, "", [], [], time.time())).success
            for r in self._task_results.values()
        ):
            self._state = SessionState.COMPLETED
        else:
            self._state = SessionState.FAILED

        summary = self.reflector.reflect(self)
        total_latency_ms = (time.time() - start_time) * 1000

        if self.config.auto_save:
            self.save()

        return {
            "session_id": self.config.session_id,
            "tasks": self._task_results,
            "summary": summary,
            "status": self.status(),
            "total_latency_ms": total_latency_ms,
        }

    def ask(self, followup: str) -> dict[str, Any]:
        """
        Handle a follow-up / supplementary instruction on the current session.

        Follows the same execution mode (parallel/sequential) as the original run.
        """
        if self._state != SessionState.RUNNING:
            self._state = SessionState.RUNNING

        if self.config.verbose:
            print(f"[ResearchSession.ask] Follow-up: {followup}")

        tasks = self.planner.decompose(f"{self.config.user_goal}。{followup}")
        all_tasks = self._flatten_tasks(tasks)

        if self.config.parallel:
            self._execute_parallel(all_tasks)
        else:
            self._execute_sequential(all_tasks)

        if self.config.auto_save:
            self.save()

        summary = self.reflector.reflect(self)

        return {
            "session_id": self.config.session_id,
            "tasks": self._task_results,
            "summary": summary,
            "status": self.status(),
            "followup": followup,
        }

    def pause(self):
        """
        Pause the session. Currently sets a flag; for full pause support,
        call this between task boundaries.
        """
        self._pause_event.clear()
        self._state = SessionState.PAUSED

    def resume(self) -> dict[str, Any]:
        """
        Resume a paused session. Re-executes remaining pending tasks.
        """
        if self._state != SessionState.PAUSED:
            return {"error": "Session is not paused"}

        self._pause_event.set()
        self._state = SessionState.RUNNING

        # Find pending tasks
        pending = [
            t for t in self.planner.tasks.values()
            if t.status == TaskStatus.PENDING
        ]

        if not pending:
            return {"message": "No pending tasks to resume"}

        if self.config.parallel:
            self._execute_parallel(pending)
        else:
            self._execute_sequential(pending)

        summary = self.reflector.reflect(self)

        if self.config.auto_save:
            self.save()

        return {
            "session_id": self.config.session_id,
            "tasks": self._task_results,
            "summary": summary,
            "status": self.status(),
            "resumed_tasks": len(pending),
        }

    def status(self) -> SessionStatus:
        """Return the current session status snapshot."""
        completed = 0
        failed = 0
        pending = 0
        running = 0
        scores: list[float] = []

        for task_result in self._task_results.values():
            evaluation: Evaluation | None = task_result.get("evaluation")
            if evaluation is None:
                continue
            if evaluation.success:
                completed += 1
            else:
                failed += 1
            scores.append(evaluation.score)

        with self._running_task_count_lock:
            running = self._running_task_count

        for task in self.planner.tasks.values():
            if task.status == TaskStatus.PENDING:
                pending += 1

        avg_score = sum(scores) / len(scores) if scores else None

        return SessionStatus(
            state=self._state,
            completed_tasks=completed,
            failed_tasks=failed,
            pending_tasks=pending,
            running_tasks=running,
            avg_score=avg_score,
        )

    def save(self):
        """Manually persist the session to disk."""
        self.memory.save_session()

    @staticmethod
    def resume_session(session_id: str, db_path: str | None = None) -> ResearchSession:
        """Alias for ResearchSession.load()."""
        return ResearchSession.load(session_id, db_path)

    @staticmethod
    def load(session_id: str, db_path: str | None = None) -> ResearchSession:
        """Load a saved session and reconstruct its state."""
        path = db_path or ".cache/research.db"

        memory = ResearchMemory.load_session(session_id, db_path=path)

        context = memory.get_context(limit=1)
        user_goal = "Restored session"
        if context:
            user_goal = context[0].task if context else "Restored session"

        config = SessionConfig(
            session_id=session_id,
            user_goal=user_goal,
            workspace_root=Path("."),
            db_path=path,
        )

        session = ResearchSession(config)
        session.memory = memory
        session.planner = ResearchPlanner(session.memory)
        session.tool_selector = ToolSelector(session.memory)
        session.reflector = ResearchReflector(session.memory)

        for unit in session.memory.get_context(limit=100):
            if isinstance(unit.result, dict) and "task_id" in unit.result:
                task_id = unit.result["task_id"]
                session._task_results[task_id] = {
                    "result": unit.result.get("result"),
                    "evaluation": None,
                }

        # Restore planner tasks from stored task results
        if hasattr(session.planner, "tasks"):
            for task_id, task_result in session._task_results.items():
                result_data = task_result.get("result", {})
                if isinstance(result_data, dict):
                    task = session.planner.tasks.get(task_id)
                    if task is not None:
                        from scripts.core.planner import TaskStatus
                        task.status = (
                            TaskStatus.DONE
                            if result_data.get("success")
                            else TaskStatus.FAILED
                        )

        if session._task_results:
            session._state = SessionState.COMPLETED
        else:
            session._state = SessionState.CREATED

        return session

    # ── Sequential Execution ───────────────────────────────────────────────────

    def _execute_sequential(self, tasks: list[Task]):
        """Execute tasks sequentially in topological order."""
        sorted_tasks = self._topological_order(tasks)
        total = len(sorted_tasks)

        for i, task in enumerate(sorted_tasks):
            # Check pause
            self._pause_event.wait()

            if not self._dependencies_ready(task, sorted_tasks):
                task.status = TaskStatus.BLOCKED
                continue

            task.status = TaskStatus.RUNNING
            self._report_progress("running", task, (i + 1) / total)

            context = self.memory.get_context(limit=self.config.max_context_items)
            result, evaluation = self._execute_single_task(task, context)

            self._task_results[task.id] = {
                "result": result,
                "evaluation": evaluation,
            }

            # Self-evolution: trigger evolution assessment after task
            self._on_task_complete(task.id, result)

            if evaluation.success:
                task.status = TaskStatus.DONE
                task.finished_at = time.time()
            else:
                task.status = TaskStatus.FAILED
                task.error = evaluation.feedback

            self._report_progress("done", task, (i + 1) / total)

            if self.config.auto_save:
                self.save()

    # ── Parallel Execution ──────────────────────────────────────────────────────

    def _execute_parallel(self, tasks: list[Task]):
        """
        Execute tasks in parallel, layer by layer.

        Strategy:
        1. Kahn topological sort produces a layer-by-layer order
        2. All tasks in the same "layer" (no unmet dependencies) run concurrently
        3. Max concurrent workers = self.config.max_workers
        4. Results are stored as each task completes
        5. Dependency counts are updated after each layer finishes
        """
        task_map = {t.id: t for t in tasks}
        remaining = {t.id for t in tasks}
        in_degree = {t.id: len(t.dependencies) for t in tasks}
        total = len(tasks)
        completed_count = [0]  # Mutable counter for progress

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.max_workers
        ) as executor:
            while remaining:
                # Find all tasks ready to run (in_degree == 0)
                ready_ids = [tid for tid in remaining if in_degree.get(tid, 0) == 0]

                if not ready_ids:
                    # Deadlock — remaining tasks have unmet circular dependencies
                    for tid in remaining:
                        task_map[tid].status = TaskStatus.BLOCKED
                        task_map[tid].error = "Circular dependency detected"
                    break

                ready_tasks = [task_map[tid] for tid in ready_ids]

                # Mark as running
                for task in ready_tasks:
                    task.status = TaskStatus.RUNNING
                    self._report_progress("running", task, completed_count[0] / total)

                # Submit all ready tasks concurrently
                futures = {
                    executor.submit(self._execute_single_task_isolated, task): task
                    for task in ready_tasks
                }

                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    remaining.discard(task.id)

                    try:
                        result, evaluation = future.result()
                    except Exception as exc:
                        evaluation = self._create_empty_evaluation(task)
                        evaluation.feedback = f"Parallel execution error: {exc}"
                        result = {"task_id": task.id, "status": "error", "error": str(exc)}

                    self._task_results[task.id] = {
                        "result": result,
                        "evaluation": evaluation,
                    }

                    # Self-evolution: trigger evolution assessment after task
                    self._on_task_complete(task.id, result)

                    if evaluation.success:
                        task.status = TaskStatus.DONE
                        task.finished_at = time.time()
                    else:
                        task.status = TaskStatus.FAILED
                        task.error = evaluation.feedback

                    completed_count[0] += 1
                    self._report_progress("done", task, completed_count[0] / total)

                    # Update in-degrees of dependent tasks
                    for other_id, other_task in task_map.items():
                        if other_id in remaining and task.id in other_task.dependencies:
                            in_degree[other_id] -= 1

                if self.config.auto_save:
                    self.save()

    def _execute_single_task_isolated(self, task: Task) -> tuple[Any, Evaluation]:
        """
        Isolated task execution for parallel mode.

        Creates a fresh context snapshot to avoid race conditions
        when reading shared memory concurrently.
        """
        context = self.memory.get_context(limit=self.config.max_context_items)
        return self._execute_single_task(task, context)

    # ── Single Task Execution ─────────────────────────────────────────────────

    def _execute_single_task(
        self,
        task: Task,
        context: list,
    ) -> tuple[Any, Evaluation]:
        """Execute one task: select → execute → evaluate."""
        selections = self.tool_selector.select(task, context)

        if not selections:
            evaluation = self._create_empty_evaluation(task)
            self._write_context(task, None, evaluation)
            return None, evaluation

        result = self._execute_with_fallback(task, selections)
        evaluation = self.reflector.evaluate(task, result, context)
        self._write_context(task, result, evaluation)

        return result, evaluation

    # ── Internal Helpers ───────────────────────────────────────────────────────

    def _execute_with_fallback(
        self,
        task: Task,
        selections: list[ToolSelection],
    ) -> Any:
        """Execute a task using tool selections with fallback on failure."""
        attempt = 0
        last_error: str | None = None

        while attempt < self.config.max_retries:
            for selection in selections:
                try:
                    result = self.tool_selector.execute(selection, {"task": task})
                    if result.success:
                        return result.output
                    last_error = result.error
                except NotImplementedError:
                    return {
                        "task_id": task.id,
                        "task_type": task.task_type.value,
                        "status": "mocked",
                        "note": f"Tool '{selection.tool_name}' not implemented",
                        "attempt": attempt,
                    }
                except Exception as exc:
                    last_error = str(exc)

            attempt += 1

        return {
            "task_id": task.id,
            "task_type": task.task_type.value,
            "status": "failed",
            "error": last_error or "All tool executions failed",
            "attempts": attempt,
        }

    def _create_empty_evaluation(self, task: Task) -> Evaluation:
        """Create a minimal Evaluation for tasks with no tool available."""
        return Evaluation(
            task_id=task.id,
            success=False,
            score=0.0,
            feedback=f"No tool available for task [{task.task_type.value}] {task.description}",
            suggestions=["Install the required tool or MCP server for this task type."],
            quality_flags=["incomplete_output"],
            timestamp=time.time(),
        )

    def _write_context(
        self,
        task: Task,
        result: Any,
        evaluation: Evaluation,
    ):
        """Push task result and evaluation into memory."""
        tools_used: list[str] = []
        if result and isinstance(result, dict):
            tool_name = result.get("tool_name", "")
            if tool_name:
                tools_used = [tool_name]

        self.memory.push(
            task=task.description,
            result={
                "task_id": task.id,
                "result": result,
                "score": evaluation.score,
                "success": evaluation.success,
            },
            metadata={
                "tools": tools_used,
                "type": "task_complete",
                "evaluation": evaluation.feedback,
                "quality_flags": evaluation.quality_flags,
            },
        )

        context = self.memory.get_context(limit=1)
        if context:
            latest = context[-1]
            self.memory.update_evaluation(latest.timestamp, evaluation.feedback)

    def _report_progress(self, phase: str, task: Task, progress: float):
        """Report progress via callback if configured."""
        if self.config.progress_callback:
            try:
                self.config.progress_callback(phase, task, progress)
            except Exception:
                pass  # Don't let callback errors break execution

    def _flatten_tasks(self, tasks: list[Task]) -> list[Task]:
        """Flatten a task tree into a flat list (BFS)."""
        flat = []
        queue = list(tasks)
        while queue:
            t = queue.pop(0)
            flat.append(t)
            queue.extend(t.subtasks)
        return flat

    def _topological_order(self, tasks: list[Task]) -> list[Task]:
        """
        Kahn's topological sort — tasks with no unmet dependencies come first.
        """
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: 0 for t in tasks}

        for t in tasks:
            for dep_id in t.dependencies:
                if dep_id in in_degree:
                    in_degree[t.id] += 1

        ready = [t for t in tasks if in_degree[t.id] == 0]
        sorted_tasks: list[Task] = []

        dependents: dict[str, list[Task]] = {t.id: [] for t in tasks}
        for t in tasks:
            for dep_id in t.dependencies:
                if dep_id in dependents:
                    dependents[dep_id].append(t)

        while ready:
            task = ready.pop(0)
            sorted_tasks.append(task)
            if task.id in dependents:
                for dep in dependents[task.id]:
                    in_degree[dep.id] -= 1
                    if in_degree[dep.id] == 0 and dep not in sorted_tasks and dep not in ready:
                        ready.append(dep)

        for t in tasks:
            if t not in sorted_tasks:
                sorted_tasks.append(t)

        return sorted_tasks

    def _dependencies_ready(self, task: Task, all_tasks: list[Task]) -> bool:
        """Check whether all dependencies of a task have been executed."""
        if not task.dependencies:
            return True

        completed_ids = {
            t.id for t in all_tasks
            if t.status in (TaskStatus.DONE, TaskStatus.BLOCKED)
            # NOTE: FAILED does NOT satisfy dependencies — a failed dep means the task cannot run
        }

        return all(dep_id in completed_ids for dep_id in task.dependencies)

    def __repr__(self) -> str:
        return (
            f"ResearchSession(id={self.config.session_id!r}, "
            f"state={self._state.value}, "
            f"tasks={len(self._task_results)}, "
            f"parallel={self.config.parallel})"
        )
