"""ResearchPlanner: Task decomposition, topological execution, and fallback strategies."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Enums ───────────────────────────────────────────────────────────────────


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    RETRY = "retry"


class TaskType(Enum):
    DATA_FETCH = "data_fetch"
    LITERATURE = "literature"
    ANALYSIS = "analysis"
    WRITING = "writing"
    CODE = "code"
    VISUALIZATION = "visualization"
    REVIEW = "review"
    ORCHESTRATE = "orchestrate"


# ─── Task Dataclass ───────────────────────────────────────────────────────────


@dataclass
class Task:
    id: str
    description: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    subtasks: list["Task"] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


# ─── Keyword/Regex Classification ─────────────────────────────────────────────


KEYWORD_PATTERNS: dict[TaskType, list[str]] = {
    TaskType.DATA_FETCH: [
        "获取", "查询", "下载", "拉取", "fetch", "download", "获取数据",
        "日线", "行情", "财报", "数据",
    ],
    TaskType.LITERATURE: [
        "文献", "论文检索", "搜论文", "查找文献", "arXiv", "文献综述",
        "综述", "检索文献",
    ],
    TaskType.ANALYSIS: [
        "分析", "回归", "统计", "ROE", "毛利率", "估值", "分析数据",
        "财务", "营收", "利润", "回归分析", "回归",
    ],
    TaskType.WRITING: [
        "写论文", "写报告", "生成报告", "生成研报", "论文大纲", "润色",
        "写", "目标NeurIPS", "目标ICML", "论文",
    ],
    TaskType.CODE: [
        "代码", "写代码", "python", "script", "def ", "import ",
    ],
    TaskType.VISUALIZATION: [
        "画图", "可视化", "图表", "chart", "plot", "绘图",
    ],
    TaskType.REVIEW: [
        "审稿", "review", "润色",
    ],
}

REGEX_PATTERNS: list[tuple[str, TaskType]] = [
    (r"写.*(?:论文|paper)", TaskType.WRITING),
    (r"英.*(?:论文|paper)", TaskType.WRITING),
    (r"分析.*(?:财务|ROE|营收|利润|估值)", TaskType.ANALYSIS),
    (r"生成.*(?:研报|行研|行业.*报告)", TaskType.WRITING),
    (r"搜.*(?:文献|论文)|找.*(?:文献|论文)|检索.*(?:文献|论文)", TaskType.LITERATURE),
    (r"获取.*(?:日线|财务|行情|数据)", TaskType.DATA_FETCH),
]


# ─── ResearchPlanner ───────────────────────────────────────────────────────────


class ResearchPlanner:
    """
    Task planner that decomposes user requests into a task graph,
    executes in topological order, and implements fallback strategies.
    """

    def __init__(self, memory: "ResearchMemory"):
        self.memory = memory
        self.tasks: dict[str, Task] = {}
        self._task_counter = 0

    def _next_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter:03d}"

    def _estimate_task_type(self, text: str) -> list[TaskType]:
        """
        Classify task type based on keywords and regex patterns.
        Returns a list of matched TaskTypes (can be multiple).
        """
        matched: list[TaskType] = []

        # First, check regex patterns (higher priority)
        for pattern, task_type in REGEX_PATTERNS:
            if re.search(pattern, text):
                if task_type not in matched:
                    matched.append(task_type)

        # Then, check keyword patterns
        for task_type, keywords in KEYWORD_PATTERNS.items():
            if task_type in matched:
                continue
            for kw in keywords:
                if kw in text:
                    matched.append(task_type)
                    break

        # Default to ANALYSIS if nothing matched
        if not matched:
            matched.append(TaskType.ANALYSIS)

        return matched

    def _create_task(
        self,
        description: str,
        task_type: TaskType,
        dependencies: list[str] | None = None,
        subtasks: list[Task] | None = None,
    ) -> Task:
        """Factory method to create a Task with auto-generated ID."""
        return Task(
            id=self._next_id(),
            description=description,
            task_type=task_type,
            status=TaskStatus.PENDING,
            subtasks=subtasks or [],
            dependencies=dependencies or [],
        )

    def decompose(self, user_request: str) -> list[Task]:
        """
        Decompose a user request into a task graph.

        Returns a list of root tasks (which may contain subtasks).
        Task dependencies are set so that execution follows topological order.
        """
        task_types = self._estimate_task_type(user_request)
        root_tasks: list[Task] = []

        # Case 1: LITERATURE / literature + review (check before ANALYSIS)
        if TaskType.LITERATURE in task_types or "综述" in user_request or "文献" in user_request:
            root_tasks.extend(self._decompose_literature(user_request))

        # Case 2: WRITING task (paper/report generation)
        elif TaskType.WRITING in task_types:
            root_tasks.extend(self._decompose_writing(user_request))

        # Case 2: LITERATURE task (literature search + review)
        elif TaskType.LITERATURE in task_types:
            root_tasks.extend(self._decompose_literature(user_request))

        # Case 3: ANALYSIS + DATA_FETCH
        elif TaskType.ANALYSIS in task_types or TaskType.DATA_FETCH in task_types:
            root_tasks.extend(self._decompose_analysis_with_data(user_request))

        # Case 4: Standalone DATA_FETCH
        elif TaskType.DATA_FETCH in task_types:
            root_tasks.extend(self._decompose_data_fetch(user_request))

        # Case 5: Standalone CODE
        elif TaskType.CODE in task_types:
            root_tasks.extend(self._decompose_code(user_request))

        # Case 6: Standalone VISUALIZATION
        elif TaskType.VISUALIZATION in task_types:
            root_tasks.extend(self._decompose_visualization(user_request))

        # Case 7: Fallback — create a single ANALYSIS task
        else:
            task = self._create_task(
                description=user_request,
                task_type=TaskType.ANALYSIS,
            )
            root_tasks.append(task)

        # Store all tasks in the planner's task registry
        self._register_tasks(root_tasks)

        return root_tasks

    def _decompose_writing(self, request: str) -> list[Task]:
        """Decompose writing task: outline → chapters → assemble."""
        outline_task = self._create_task(
            description="设计论文大纲",
            task_type=TaskType.WRITING,
        )

        chapter_task = self._create_task(
            description=f"撰写论文章节内容: {request}",
            task_type=TaskType.WRITING,
            dependencies=[outline_task.id],
        )

        assemble_task = self._create_task(
            description="整合各章节生成完整论文",
            task_type=TaskType.WRITING,
            dependencies=[chapter_task.id],
        )

        return [outline_task, chapter_task, assemble_task]

    def _decompose_literature(self, request: str) -> list[Task]:
        """Decompose literature task: search → download → review."""
        search_task = self._create_task(
            description=f"检索文献: {request}",
            task_type=TaskType.LITERATURE,
        )

        download_task = self._create_task(
            description="下载文献PDF",
            task_type=TaskType.LITERATURE,
            dependencies=[search_task.id],
        )

        review_task = self._create_task(
            description="撰写文献综述",
            task_type=TaskType.REVIEW,
            dependencies=[download_task.id],
        )

        return [search_task, download_task, review_task]

    def _decompose_analysis_with_data(self, request: str) -> list[Task]:
        """Decompose analysis with data fetch: fetch → analysis."""
        fetch_task = self._create_task(
            description=f"获取分析所需数据: {request}",
            task_type=TaskType.DATA_FETCH,
        )

        analysis_task = self._create_task(
            description=f"数据分析: {request}",
            task_type=TaskType.ANALYSIS,
            dependencies=[fetch_task.id],
        )

        return [fetch_task, analysis_task]

    def _decompose_data_fetch(self, request: str) -> list[Task]:
        """Decompose data fetch task."""
        task = self._create_task(
            description=f"获取数据: {request}",
            task_type=TaskType.DATA_FETCH,
        )
        return [task]

    def _decompose_code(self, request: str) -> list[Task]:
        """Decompose code generation task: clarify → code → test."""
        clarify_task = self._create_task(
            description=f"澄清代码需求: {request}",
            task_type=TaskType.CODE,
        )

        code_task = self._create_task(
            description=f"编写代码: {request}",
            task_type=TaskType.CODE,
            dependencies=[clarify_task.id],
        )

        test_task = self._create_task(
            description="测试代码",
            task_type=TaskType.CODE,
            dependencies=[code_task.id],
        )

        return [clarify_task, code_task, test_task]

    def _decompose_visualization(self, request: str) -> list[Task]:
        """Decompose visualization task."""
        task = self._create_task(
            description=f"生成可视化图表: {request}",
            task_type=TaskType.VISUALIZATION,
        )
        return [task]

    def _register_tasks(self, tasks: list[Task]):
        """Register all tasks (including subtasks) in the planner's registry."""
        for task in tasks:
            self.tasks[task.id] = task
            self._register_tasks(task.subtasks)

    def execute(self, task_graph: list[Task]) -> dict[str, Any]:
        """
        Execute tasks in topological order (Kahn's algorithm).

        Returns a dict mapping task_id -> result.
        Skeleton implementation that returns placeholder results.
        """
        results: dict[str, Any] = {}

        # Collect all tasks including subtasks
        all_tasks = self._flatten_tasks(task_graph)

        # Kahn's topological sort
        sorted_tasks = self._topological_sort(all_tasks)

        for task in sorted_tasks:
            # Skip if dependencies not met
            unmet = [dep for dep in task.dependencies if results.get(dep) is None]
            if unmet:
                task.status = TaskStatus.BLOCKED
                continue

            task.status = TaskStatus.RUNNING

            # Simulate execution (placeholder — ToolSelector not yet implemented)
            try:
                task.result = {"status": "executed", "task_id": task.id}
                task.status = TaskStatus.DONE
                task.finished_at = time.time()
            except Exception as exc:
                task.error = str(exc)
                task.status = TaskStatus.FAILED
                fallback_task = self._fallback(task)
                if fallback_task:
                    results[fallback_task.id] = fallback_task.result

            results[task.id] = task.result

        return results

    def _flatten_tasks(self, tasks: list[Task]) -> list[Task]:
        """Flatten a task tree into a list (BFS)."""
        flat = []
        queue = list(tasks)
        while queue:
            t = queue.pop(0)
            flat.append(t)
            queue.extend(t.subtasks)
        return flat

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """
        Topological sort using Kahn's algorithm.
        Tasks with no unmet dependencies come first.
        """
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: len(t.dependencies) for t in tasks}
        ready = [t for t in tasks if in_degree[t.id] == 0]
        sorted_tasks = []

        while ready:
            task = ready.pop(0)
            sorted_tasks.append(task)
            # Decrease in-degree for dependent tasks
            for t in tasks:
                if task.id in t.dependencies:
                    in_degree[t.id] -= 1
                    if in_degree[t.id] == 0 and t not in sorted_tasks and t not in ready:
                        ready.append(t)

        # Append any remaining tasks (circular deps or orphaned)
        for t in tasks:
            if t not in sorted_tasks:
                sorted_tasks.append(t)

        return sorted_tasks

    def _fallback(self, failed_task: Task) -> Task | None:
        """
        4-level fallback strategy:

        1. Retry — retry_count < 3 (API temporary failure)
        2. Degrade — tool unavailable, use alternative
        3. Skip — non-critical task
        4. Abort — critical task failure
        """
        CRITICAL_TYPES = {TaskType.WRITING, TaskType.ANALYSIS}

        # Level 1: Retry
        if failed_task.retry_count < 3:
            failed_task.retry_count += 1
            failed_task.status = TaskStatus.RETRY
            failed_task.error = None
            return failed_task

        # Level 2: Degrade — try alternative tool/task type
        if failed_task.task_type in CRITICAL_TYPES:
            degraded = self._create_task(
                description=f"[降级] {failed_task.description}",
                task_type=TaskType.ANALYSIS,
            )
            degraded.retry_count = failed_task.retry_count
            return degraded

        # Level 3: Skip — non-critical task
        if failed_task.task_type not in CRITICAL_TYPES:
            skipped = self._create_task(
                description=f"[跳过] {failed_task.description}",
                task_type=failed_task.task_type,
            )
            skipped.status = TaskStatus.DONE
            skipped.result = {"skipped": True, "original_error": failed_task.error}
            return skipped

        # Level 4: Abort — critical task failure
        failed_task.status = TaskStatus.FAILED
        return None

    def get_status(self) -> dict[str, str]:
        """Return a summary dict {task_id: status.value}."""
        return {tid: task.status.value for tid, task in self.tasks.items()}
