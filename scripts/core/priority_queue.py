"""优先级队列 — 支持 P0/P1/P2 任务排序的 HITL Gate 调度器.

功能：
  - 按优先级（P0 > P1 > P2）自动排序待审核任务
  - 支持紧急任务插队（bump）
  - 与 EnhancedHITLGate 无缝集成
  - 任务超时自动降级
  - 批量任务优先级推断

Usage:
    queue = PriorityGateQueue()
    queue.enqueue(gate_id="task_001", priority=Priority.P1, metadata={...})
    queue.enqueue(gate_id="task_002", priority=Priority.P0, metadata={...})

    # 按优先级顺序处理
    while not queue.is_empty():
        next_task = queue.dequeue()
        print(f"处理: {next_task.gate_id} (优先级: {next_task.priority.name})")
"""

from __future__ import annotations

import heapq
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

__all__ = [
    "Priority",
    "GateTask",
    "PriorityGateQueue",
]


logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """
    任务优先级，数值越小优先级越高。

    P0: 紧急 — 阻断主流程（如致命数据错误、实证结果矛盾）
    P1: 高优先级 — 影响后续分析（如关键假设未被验证）
    P2: 普通 — 可延后处理（如语言润色、格式调整）
    """
    P0_CRITICAL = 0
    P1_HIGH = 1
    P2_NORMAL = 2

    @property
    def label(self) -> str:
        labels = {0: "🔴 P0-CRITICAL", 1: "🟡 P1-HIGH", 2: "⚪ P2-NORMAL"}
        return labels[self.value]

    @property
    def urgency(self) -> str:
        """超出多长时间触发升级。"""
        thresholds = {0: "1分钟", 1: "5分钟", 2: "30分钟"}
        return thresholds[self.value]


@dataclass(order=False, slots=True)
class GateTask:
    """
    优先级队列中的单个任务。

    Attributes
    ----------
    gate_id : str
        唯一标识。
    priority : Priority
        优先级。
    enqueued_at : float
        入队时间戳（用于 FIFO 打破同优先级平局）。
    metadata : dict
        任务元数据（agent_name, task_type, context 等）。
    attempts : int
        处理次数（超过阈值自动降级）。
    deadline : float | None
        截止时间（可选）。
    """
    gate_id: str
    priority: Priority
    enqueued_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    deadline: float | None = None

    def __lt__(self, other: "GateTask") -> bool:
        """
        优先级队列排序：先按 priority（升序），同优先级按 enqueued_at（升序，FIFO）。
        """
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.enqueued_at < other.enqueued_at

    @property
    def age_seconds(self) -> float:
        """任务在队列中的等待时间（秒）。"""
        return time.time() - self.enqueued_at

    @property
    def age_minutes(self) -> float:
        """任务在队列中的等待时间（分钟）。"""
        return self.age_seconds / 60

    @property
    def is_overdue(self) -> bool:
        """是否已超过截止时间。"""
        if self.deadline is None:
            return False
        return time.time() > self.deadline

    def bump_to(self, new_priority: Priority) -> None:
        """
        将任务插队到新优先级。

        注意：仅更新 priority，不改变 enqueued_at（保持原始 FIFO 顺序）。
        """
        if new_priority.value < self.priority.value:
            logger.info(
                f"[PriorityGateQueue] 任务 {self.gate_id} "
                f"从 {self.priority.label} 升级到 {new_priority.label}"
            )
            self.metadata["bumped"] = True
            self.metadata["bumped_from"] = self.priority.name
        self.priority = new_priority

    def increment_attempts(self) -> None:
        """增加处理次数。"""
        self.attempts += 1
        if self.attempts >= 3:
            logger.warning(
                f"[PriorityGateQueue] 任务 {self.gate_id} "
                f"处理次数已达 {self.attempts} 次，强制降级"
            )
            self.metadata["force_degraded"] = True


@dataclass
class PriorityQueueStats:
    """队列统计信息。"""
    total_enqueued: int = 0
    total_processed: int = 0
    total_expired: int = 0
    current_p0: int = 0
    current_p1: int = 0
    current_p2: int = 0
    avg_wait_seconds: float = 0.0
    max_wait_seconds: float = 0.0


class PriorityGateQueue:
    """
    HITL Gate 优先级队列。

    特性：
      - 最小堆实现，O(log n) 入队/出队
      - 支持按优先级自动排序
      - 任务超时自动降级（P2 → P1 → P0 → 自动通过）
      - 紧急插队（bump）
      - 批量优先级推断（基于任务类型）

    Usage:
        queue = PriorityGateQueue()
        queue.enqueue("task_1", Priority.P1, {"type": "data_validation"})
        queue.enqueue("task_2", Priority.P0, {"type": "fatal_error"})
        queue.enqueue("task_3", Priority.P2, {"type": "language_review"})

        # 处理最高优先级
        task = queue.dequeue()
        queue.mark_done(task.gate_id)
    """

    def __init__(self, auto_degrade_seconds: float | None = None):
        """
        Parameters
        ----------
        auto_degrade_seconds : float | None
            超过该时间自动降级（秒）。None 表示不自动降级。
            默认：P2 任务 30 分钟无响应则降为 P1，P1 5 分钟降为 P0，P0 1 分钟降为自动通过。
        """
        self._heap: list[GateTask] = []
        self._seen: set[str] = set()       # 已入队 ID（防止重复）
        self._processed: set[str] = set()  # 已处理 ID
        self._stats = PriorityQueueStats()
        self._auto_degrade_seconds = auto_degrade_seconds

        # 默认超时阈值（秒）
        self._timeout_thresholds: dict[Priority, float] = {
            Priority.P2_NORMAL: 30 * 60,   # 30 分钟
            Priority.P1_HIGH: 5 * 60,     # 5 分钟
            Priority.P0_CRITICAL: 1 * 60,  # 1 分钟
        }

    # ── 入队/出队 ─────────────────────────────────────────

    def enqueue(
        self,
        gate_id: str,
        priority: Priority | None = None,
        metadata: dict[str, Any] | None = None,
        deadline: float | None = None,
    ) -> GateTask | None:
        """
        将任务加入优先级队列。

        Parameters
        ----------
        gate_id : str
            任务唯一标识（与 EnhancedHITLGate 的 gate_id 对应）。
        priority : Priority | None
            优先级，None 则自动推断。
        metadata : dict | None
            任务元数据。
        deadline : float | None
            Unix 时间戳截止时间。

        Returns
        -------
        GateTask | None
            新建的任务对象。如果 gate_id 已存在则返回 None。
        """
        if gate_id in self._seen:
            logger.warning(
                f"[PriorityGateQueue] 任务 {gate_id} 已存在于队列，忽略重复入队"
            )
            return None

        # 自动推断优先级
        if priority is None:
            priority = self._infer_priority(metadata or {})

        task = GateTask(
            gate_id=gate_id,
            priority=priority,
            enqueued_at=time.time(),
            metadata=metadata or {},
            deadline=deadline,
        )
        heapq.heappush(self._heap, task)
        self._seen.add(gate_id)
        self._stats.total_enqueued += 1
        self._update_stats()

        logger.info(
            f"[PriorityGateQueue] 入队: {gate_id} "
            f"({priority.label})，队列长度: {len(self._heap)}"
        )
        return task

    def dequeue(self) -> GateTask | None:
        """
        取出最高优先级任务。

        Returns
        -------
        GateTask | None
            最高优先级任务（Priority 最小的最老任务）。
            队列为空返回 None。
        """
        if not self._heap:
            return None

        task = heapq.heappop(self._heap)
        self._seen.discard(task.gate_id)

        logger.info(
            f"[PriorityGateQueue] 出队: {task.gate_id} "
            f"({task.priority.label})，等待 {task.age_minutes:.1f} 分钟"
        )
        return task

    def peek(self) -> GateTask | None:
        """查看最高优先级任务（不移除）。"""
        if not self._heap:
            return None
        return self._heap[0]

    # ── 优先级操作 ─────────────────────────────────────────

    def bump(self, gate_id: str, new_priority: Priority) -> bool:
        """
        将指定任务插队到新优先级。

        注意：由于是最小堆结构，重新排序需要重建堆。
        对于紧急插队，建议使用 remove + enqueue。

        Returns
        -------
        bool
            是否成功。
        """
        for task in self._heap:
            if task.gate_id == gate_id:
                old_priority = task.priority
                task.bump_to(new_priority)
                # 重建堆以反映新优先级
                heapq.heapify(self._heap)
                logger.info(
                    f"[PriorityGateQueue] 插队: {gate_id} "
                    f"{old_priority.label} → {new_priority.label}"
                )
                return True
        return False

    def reprioritize(
        self,
        gate_id: str,
        new_priority: Priority,
    ) -> bool:
        """
        重新设置任务优先级（移除并重新入队）。

        推荐用于改变优先级，比 bump() 更可靠。
        """
        for i, task in enumerate(self._heap):
            if task.gate_id == gate_id:
                self._heap.pop(i)
                task.priority = new_priority
                heapq.heapify(self._heap)
                logger.info(
                    f"[PriorityGateQueue] 重排优先级: {gate_id} → {new_priority.label}"
                )
                return True
        return False

    def promote_overdue(self) -> list[GateTask]:
        """
        检查所有任务，对超时任务进行自动降级处理。

        P2 → P1 → P0 → 自动通过（标记为 auto_approved）
        """
        promoted: list[GateTask] = []
        new_heap: list[GateTask] = []

        while self._heap:
            task = heapq.heappop(self._heap)
            should_promote = False

            # 检查是否超时
            if task.age_seconds > self._timeout_thresholds[task.priority]:
                should_promote = True

            # 检查截止时间
            if task.is_overdue:
                should_promote = True

            if should_promote:
                old = task.priority
                if task.priority == Priority.P2_NORMAL:
                    task.priority = Priority.P1_HIGH
                elif task.priority == Priority.P1_HIGH:
                    task.priority = Priority.P0_CRITICAL
                else:
                    # P0 超时 → 标记自动通过
                    task.metadata["auto_approved"] = True
                    task.metadata["auto_approve_reason"] = f"超时 {task.age_minutes:.0f} 分钟无响应"
                    self._processed.add(task.gate_id)
                    self._seen.discard(task.gate_id)
                    self._stats.total_expired += 1
                    logger.warning(
                        f"[PriorityGateQueue] P0 超时，自动批准: {task.gate_id}"
                    )
                    promoted.append(task)
                    continue

                task.metadata["promoted"] = True
                task.metadata["promoted_from"] = old.name
                logger.info(
                    f"[PriorityGateQueue] 自动降级: {task.gate_id} "
                    f"{old.label} → {task.priority.label}"
                )

                promoted.append(task)
                new_heap.append(task)
            else:
                new_heap.append(task)

        self._heap = new_heap
        heapq.heapify(self._heap)
        return promoted

    # ── 辅助 ─────────────────────────────────────────────

    def mark_done(self, gate_id: str) -> bool:
        """标记任务已处理完成。"""
        if gate_id in self._processed:
            return False
        self._processed.add(gate_id)
        self._stats.total_processed += 1
        self._update_stats()
        return True

    def cancel(self, gate_id: str) -> bool:
        """从队列中移除任务（取消）。"""
        for i, task in enumerate(self._heap):
            if task.gate_id == gate_id:
                self._heap.pop(i)
                self._seen.discard(gate_id)
                heapq.heapify(self._heap)
                logger.info(f"[PriorityGateQueue] 取消: {gate_id}")
                return True
        return False

    def get_position(self, gate_id: str) -> int | None:
        """获取任务在队列中的位置（1-indexed）。"""
        for i, task in enumerate(sorted(self._heap)):
            if task.gate_id == gate_id:
                return i + 1
        return None

    def size(self) -> int:
        """当前队列长度。"""
        return len(self._heap)

    def is_empty(self) -> bool:
        """队列是否为空。"""
        return len(self._heap) == 0

    def contains(self, gate_id: str) -> bool:
        """任务是否在队列中（未处理）。"""
        return gate_id in self._seen

    # ── 优先级推断 ────────────────────────────────────────

    TASK_TYPE_PRIORITY: dict[str, Priority] = {
        # P0: 阻断流程
        "data_error": Priority.P0_CRITICAL,
        "fatal_error": Priority.P0_CRITICAL,
        "contradiction": Priority.P0_CRITICAL,     # 实证结果矛盾
        "security_issue": Priority.P0_CRITICAL,
        "methodology_error": Priority.P0_CRITICAL,
        # P1: 影响分析
        "data_validation": Priority.P1_HIGH,
        "assumption_check": Priority.P1_HIGH,
        "hypothesis_review": Priority.P1_HIGH,
        "model_selection": Priority.P1_HIGH,
        "variable_definition": Priority.P1_HIGH,
        # P2: 可延后
        "language_review": Priority.P2_NORMAL,
        "format_review": Priority.P2_NORMAL,
        "citation_check": Priority.P2_NORMAL,
        "figure_review": Priority.P2_NORMAL,
        "table_review": Priority.P2_NORMAL,
    }

    def _infer_priority(self, metadata: dict[str, Any]) -> Priority:
        """
        根据任务元数据自动推断优先级。

        推断依据：
          1. 显式 priority 字段
          2. task_type 关键字匹配
          3. agent_name 高风险标识（literature_review → P1）
        """
        # 显式优先级
        if "priority" in metadata:
            try:
                return Priority(metadata["priority"])
            except (ValueError, TypeError):
                pass

        # task_type 匹配
        task_type = metadata.get("task_type", "").lower()
        for keyword, priority in self.TASK_TYPE_PRIORITY.items():
            if keyword in task_type:
                return priority

        # agent 推断
        agent = metadata.get("agent_name", "").lower()
        high_risk_agents = {"literature", "empirical", "methodology", "review"}
        for keyword in high_risk_agents:
            if keyword in agent:
                return Priority.P1_HIGH

        return Priority.P2_NORMAL

    def infer_batch_priority(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[Priority]:
        """
        批量推断多个任务的优先级。

        Returns
        -------
        list[Priority]
            与输入顺序对应的优先级列表。
        """
        return [self._infer_priority(t) for t in tasks]

    # ── 统计 ─────────────────────────────────────────────

    def _update_stats(self) -> None:
        """更新队列统计信息。"""
        self._stats.current_p0 = sum(
            1 for t in self._heap if t.priority == Priority.P0_CRITICAL
        )
        self._stats.current_p1 = sum(
            1 for t in self._heap if t.priority == Priority.P1_HIGH
        )
        self._stats.current_p2 = sum(
            1 for t in self._heap if t.priority == Priority.P2_NORMAL
        )

        if self._processed:
            self._stats.avg_wait_seconds = sum(
                t.age_seconds for t in self._heap
            ) / max(len(self._heap), 1)

    def get_stats(self) -> PriorityQueueStats:
        """获取队列统计信息。"""
        self._update_stats()
        return self._stats

    def __len__(self) -> int:
        return len(self._heap)

    def __repr__(self) -> str:
        return (
            f"PriorityGateQueue(pending={len(self._heap)}, "
            f"processed={self._stats.total_processed}, "
            f"P0={self._stats.current_p0}, "
            f"P1={self._stats.current_p1}, "
            f"P2={self._stats.current_p2})"
        )
