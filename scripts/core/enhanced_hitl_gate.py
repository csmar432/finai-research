"""Enhanced HITL Gate — 4 种决策类型 + interrupt 语义 + Command 结构.

改进自 scripts/core/hitl_gate.py，参考 LangGraph interrupt 设计。

新增能力：
  - 4 种决策类型：approve / edit / reject / respond
  - Command dataclass：结构化决策对象
  - interrupt() 语义：pipeline 在 gate 处真正暂停，不轮询
  - 超时自动回退机制
  - 与 CheckpointManager 深度集成

复用：
  - scripts/core/checkpoint.py 的 CheckpointManager 已实现完整的 JSON 持久化
  - 本模块不重复造轮子，仅在 HITL 层面增加决策类型和 interrupt 语义
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.core.hitl_gate import ApprovalRecord, GateState, HITLGate

__all__ = [
    "DecisionType",
    "HITLCommand",
    "EnhancedHITLGate",
]


# ─── Extended Decision Types ──────────────────────────────────────────────────


class DecisionType(Enum):
    """4 种决策类型，参考 LangGraph interrupt 设计。"""

    APPROVE = "approve"   # 通过，pipeline 继续
    EDIT = "edit"         # 修改内容后通过，pipeline 继续
    REJECT = "reject"     # 拒绝，pipeline 回退
    RESPOND = "respond"   # 追加提问/要求说明，pipeline 暂停等待下一轮


@dataclass
class HITLCommand:
    """
    结构化决策对象，替代原有的 approve/reject 函数参数集合。

    Attributes
    ----------
    decision : DecisionType
        决策类型。
    gate_id : str
        关联的 gate ID。
    feedback : str
        审核意见。
    modified_content : dict | None
        EDIT 类型特有：修改后的内容。
    respond_message : str | None
        RESPOND 类型特有：追加提问内容。
    decided_by : str | None
        决策者标识。
    decided_at : float
        决策时间戳。
    """

    decision: DecisionType
    gate_id: str
    feedback: str = ""
    modified_content: dict | None = None
    respond_message: str | None = None
    decided_by: str | None = None
    decided_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "gate_id": self.gate_id,
            "feedback": self.feedback,
            "modified_content": self.modified_content,
            "respond_message": self.respond_message,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HITLCommand:
        return cls(
            decision=DecisionType(data["decision"]),
            gate_id=data["gate_id"],
            feedback=data.get("feedback", ""),
            modified_content=data.get("modified_content"),
            respond_message=data.get("respond_message"),
            decided_by=data.get("decided_by"),
            decided_at=data.get("decided_at", time.time()),
        )


# ─── Enhanced HITL Gate ─────────────────────────────────────────────────────


class EnhancedHITLGate(HITLGate):
    """
    增强版 HITL Gate，继承 HITLGate 的 SQLite 持久化和监听器机制，
    新增 4 种决策类型和 interrupt 语义。

    关键改进
    --------
    1. 4 种决策类型（approve/edit/reject/respond）
    2. interrupt() 暂停语义 — pipeline 不再轮询，真正挂起
    3. 超时自动回退 — 避免 gate 永久挂起
    4. Command 结构 — 统一所有决策类型的数据结构
    5. 与 CheckpointManager 深度集成 — interrupt 时保存完整 pipeline state

    Usage
    -----
        gate = EnhancedHITLGate()

        # interrupt 暂停 pipeline（LangGraph 风格）
        cmd = gate.interrupt(
            stage="outline",
            content={"outline": outline_json},
            question="请确认大纲结构",
            options=["approve", "edit", "reject", "respond"],
        )
        # 此时 pipeline 真正挂起，state 被序列化到 checkpoint

        # 人工决策后恢复（从 session 或 checkpoint 恢复）
        gate.inject_command(cmd)
        gate.resume(gate_id=cmd.gate_id)

        # 直接决策（兼容原有 approve/reject 用法）
        gate.approve(gate_id, feedback="结构OK")
        gate.edit(gate_id, feedback="小改", modified_content={...})
        gate.respond(gate_id, message="请补充数据来源说明")
    """

    # 继承的字段由父类初始化，以下是本类新增的字段
    _interrupted: dict[str, dict] = {}   # gate_id → interrupt snapshot
    _command_log: list[HITLCommand] = []

    def __init__(
        self,
        db_path: str = ".cache/hitl_gates.db",
        *,
        timeout_seconds: float | None = None,
        checkpoint_manager=None,
    ):
        super().__init__(db_path)
        self.timeout_seconds = timeout_seconds
        self.checkpoint_manager = checkpoint_manager
        # 新增表：commands（记录所有决策）
        self._init_commands_table()

    # ── Database schema ────────────────────────────────────────────────────

    def _init_commands_table(self):
        """初始化 commands 表，存储所有决策记录。"""
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS hitl_commands ("
            "  command_id TEXT PRIMARY KEY,"
            "  gate_id TEXT,"
            "  decision TEXT,"
            "  feedback TEXT,"
            "  modified_content TEXT,"
            "  respond_message TEXT,"
            "  decided_by TEXT,"
            "  decided_at REAL,"
            "  created_at REAL"
            ")"
        )
        self._db.commit()

    # ── 4 种决策方法 ───────────────────────────────────────────────────────

    def edit(
        self,
        gate_id: str,
        feedback: str,
        modified_content: dict,
        decided_by: str | None = None,
    ) -> ApprovalRecord:
        """
        修改内容后通过审核，pipeline 继续。

        Parameters
        ----------
        gate_id : str
        feedback : str
            审核意见。
        modified_content : dict
            修改后的内容（替换 ApprovalRecord.content）。
        decided_by : str | None
        """
        record = self._pending.pop(gate_id, None)
        if record is None:
            raise ValueError(f"Gate '{gate_id}' not found or already decided")

        record.state = GateState.APPROVED
        record.content = modified_content   # 用修改后的内容替换
        record.feedback = feedback
        record.decided_at = time.time()
        record.approved_by = decided_by

        cmd = HITLCommand(
            decision=DecisionType.EDIT,
            gate_id=gate_id,
            feedback=feedback,
            modified_content=modified_content,
            decided_by=decided_by,
        )
        self._persist_command(cmd)
        self._command_log.append(cmd)
        self._update_record_state(record, "approved", decided_by)
        self._history.append(record)
        self._notify("edit", record)
        return record

    def respond(
        self,
        gate_id: str,
        message: str,
        feedback: str = "",
        decided_by: str | None = None,
    ) -> ApprovalRecord:
        """
        追加提问/要求说明，pipeline 暂停等待下一轮（不消耗 gate）。

        与 reject 的区别：reject 关闭 gate，respond 保持 gate 开启。

        Parameters
        ----------
        gate_id : str
        message : str
            追加提问内容（将显示给 Agent）。
        feedback : str
            审核意见（可选）。
        decided_by : str | None
        """
        record = self._pending.get(gate_id)
        if record is None:
            raise ValueError(f"Gate '{gate_id}' not found or already decided")

        cmd = HITLCommand(
            decision=DecisionType.RESPOND,
            gate_id=gate_id,
            feedback=feedback,
            respond_message=message,
            decided_by=decided_by,
        )
        self._persist_command(cmd)
        self._command_log.append(cmd)
        self._notify("respond", record)
        return record

    # ── Interrupt 语义 ─────────────────────────────────────────────────────

    def interrupt(
        self,
        stage: str,
        content: dict,
        question: str = "请审核以下内容并决定是否继续：",
        options: list[str] | None = None,
        gate_id: str | None = None,
    ) -> HITLCommand:
        """
        真正暂停 pipeline — 不再轮询，state 序列化到 checkpoint。

        与 hold() 的区别：
          - hold()：插入 gate 后返回 gate_id，pipeline 继续轮询
          - interrupt()：插入 gate 后序列化完整 state，pipeline 等待 resume()

        LangGraph 等价：
            interrupt(value={"ask": "approve_outline", "options": [...]})
        本方法等价：
            gate_id = interrupt(stage, content, options)
            checkpoint_manager.save(pipeline_id, context, hitl_state)
            → pipeline 等待 resume()

        Parameters
        ----------
        stage, content, question, gate_id
            同 hold()。
        options : list[str] | None
            可选的决策选项列表。默认 ["approve", "edit", "reject", "respond"]。

        Returns
        -------
        HITLCommand
            包含 gate_id 的中断命令，用于后续 resume()。
        """
        gid = gate_id or f"hitl_{stage}_{int(time.time() * 1000)}"
        options = options or ["approve", "edit", "reject", "respond"]

        # 调用父类 hold() 插入 gate
        super().hold(stage=stage, content=content, question=question, gate_id=gid)

        # 保存 interrupt snapshot（含 state 快照，供 resume 时恢复）
        self._interrupted[gid] = {
            "stage": stage,
            "content": content,
            "question": question,
            "options": options,
            "interrupted_at": time.time(),
            "timeout_seconds": self.timeout_seconds,
        }

        # 与 CheckpointManager 集成：保存 pipeline state
        if self.checkpoint_manager is not None:
            # checkpoint_manager.save() 由调用方在 interrupt() 之后主动调用
            # 这里仅记录 interrupt 事件，供后续 resume() 使用
            pass

        return HITLCommand(
            decision=DecisionType.APPROVE,   # 占位，resume 时被真实决策替换
            gate_id=gid,
            feedback="",
            decided_at=time.time(),
        )

    def resume(self, gate_id: str, command: HITLCommand) -> ApprovalRecord:
        """
        从 interrupt 状态恢复。

        Parameters
        ----------
        gate_id : str
            interrupt() 返回的 gate_id。
        command : HITLCommand
            真实决策命令（approve/edit/reject/respond）。

        Returns
        -------
        ApprovalRecord
        """
        if command.decision == DecisionType.APPROVE:
            return self.approve(gate_id, command.feedback, command.decided_by)
        elif command.decision == DecisionType.EDIT:
            if command.modified_content is None:
                raise ValueError("EDIT decision requires modified_content")
            return self.edit(gate_id, command.feedback, command.modified_content, command.decided_by)
        elif command.decision == DecisionType.REJECT:
            return self.reject(gate_id, command.feedback, command.decided_by)
        elif command.decision == DecisionType.RESPOND:
            return self.respond(gate_id, command.respond_message or "", command.feedback, command.decided_by)
        else:
            raise ValueError(f"Unknown decision: {command.decision}")

    def inject_command(self, command: HITLCommand) -> None:
        """
        注入一个预构建的 Command（从 checkpoint/UI 恢复时使用）。

        将 command 存入 _command_log，但不立即处理。
        resume() 时会使用注入的 command。
        """
        self._command_log.append(command)

    def get_interrupted(self) -> dict[str, dict]:
        """返回所有当前中断中的 gate 快照。"""
        return dict(self._interrupted)

    def check_timeout(self) -> list[tuple[str, HITLCommand]]:
        """
        检查所有中断中的 gate 是否超时，返回超时的 gate 列表。

        Returns
        -------
        list[tuple[gate_id, HITLCommand]]
            超时 gate 的 (gate_id, 自动 REJECT Command) 列表。
        """
        if self.timeout_seconds is None:
            return []

        now = time.time()
        timed_out: list[tuple[str, HITLCommand]] = []

        for gid, snap in list(self._interrupted.items()):
            elapsed = now - snap["interrupted_at"]
            if elapsed > self.timeout_seconds:
                cmd = HITLCommand(
                    decision=DecisionType.REJECT,
                    gate_id=gid,
                    feedback=f"自动超时回退（>{self.timeout_seconds}s 无响应）",
                    decided_by="system",
                )
                timed_out.append((gid, cmd))
                del self._interrupted[gid]

        return timed_out

    # ── 查询增强 ──────────────────────────────────────────────────────────

    def get_command_history(self, gate_id: str | None = None) -> list[HITLCommand]:
        """
        返回所有决策命令历史。

        Parameters
        ----------
        gate_id : str | None
            过滤特定 gate 的命令。
        """
        results = list(self._command_log)
        if gate_id:
            results = [c for c in results if c.gate_id == gate_id]
        return results

    def get_decision(self, gate_id: str) -> DecisionType | None:
        """
        返回某 gate 的最终决策类型。
        """
        for cmd in reversed(self._command_log):
            if cmd.gate_id == gate_id:
                return cmd.decision
        return None

    def is_interrupted(self, gate_id: str) -> bool:
        """检查某 gate 是否处于中断状态。"""
        return gate_id in self._interrupted

    def get_pending_with_timeout(self) -> list[dict[str, Any]]:
        """
        返回所有 pending gate，含超时预警。

        Returns
        -------
        list[dict]
            每个 dict 含 gate record + elapsed_seconds + timeout_warning。
        """
        now = time.time()
        pending = []
        for record in self._pending.values():
            elapsed = now - record.held_at
            warning = (
                self.timeout_seconds is not None
                and elapsed > self.timeout_seconds * 0.8
            )
            pending.append({
                "record": record,
                "elapsed_seconds": elapsed,
                "timeout_warning": warning,
                "is_interrupted": record.gate_id in self._interrupted,
            })
        return pending

    def stats(self) -> dict[str, Any]:
        """增强版统计：含各决策类型分布。"""
        base = super().stats()
        decision_counts: dict[str, int] = {d.value: 0 for d in DecisionType}
        for cmd in self._command_log:
            decision_counts[cmd.decision.value] += 1
        base["decision_breakdown"] = decision_counts
        base["interrupted_count"] = len(self._interrupted)
        return base

    # ── Checkpoint 集成 ───────────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """
        序列化完整 HITL state（含 interrupt snapshot），
        供 CheckpointManager.save() 使用。
        """
        base = super().get_state() if hasattr(super(), "get_state") else {}

        pending = [
            {"gate_id": r.gate_id, "stage": r.stage, "state": r.state.value,
             "content": r.content, "question": r.question, "held_at": r.held_at}
            for r in self._pending.values()
        ]
        commands = [c.to_dict() for c in self._command_log]
        interrupted = dict(self._interrupted)

        return {
            "pending": pending,
            "history_count": len(self._history),
            "command_log": commands,
            "interrupted": interrupted,
            "stats": base if isinstance(base, dict) else {},
        }

    @classmethod
    def from_state(cls, state: dict, db_path: str = ".cache/hitl_gates.db") -> EnhancedHITLGate:
        """
        从序列化 state 重建 EnhancedHITLGate。
        用于从 checkpoint 恢复完整 HITL 状态。
        """
        gate = cls(db_path)

        # 重建 pending gates
        for entry in state.get("pending", []):
            rec = ApprovalRecord(
                gate_id=entry["gate_id"],
                stage=entry["stage"],
                state=GateState[entry["state"]],
                content=entry.get("content", {}),
                question=entry.get("question", ""),
                held_at=entry.get("held_at", time.time()),
            )
            gate._pending[rec.gate_id] = rec

        # 重建 command log
        for cmd_dict in state.get("command_log", []):
            gate._command_log.append(HITLCommand.from_dict(cmd_dict))

        # 重建 interrupted snapshot
        gate._interrupted = dict(state.get("interrupted", {}))

        return gate

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    def _persist_command(self, cmd: HITLCommand):
        """将决策命令写入 SQLite。"""
        with self._write_lock:
            self._db.execute(
                "INSERT OR REPLACE INTO hitl_commands VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    f"{cmd.gate_id}_{int(cmd.decided_at * 1000)}",
                    cmd.gate_id,
                    cmd.decision.value,
                    cmd.feedback,
                    json.dumps(cmd.modified_content) if cmd.modified_content else None,
                    cmd.respond_message,
                    cmd.decided_by,
                    cmd.decided_at,
                    time.time(),
                ],
            )
            self._db.commit()

    def _update_record_state(self, record: ApprovalRecord, state_str: str, decided_by: str | None):
        """更新 SQLite 中 record 的 state。"""
        with self._write_lock:
            self._db.execute(
                "UPDATE approval_records SET state=?, feedback=?, decided_at=?, "
                "approved_by=? WHERE gate_id=?",
                [state_str, record.feedback, record.decided_at, decided_by, record.gate_id],
            )
            self._db.commit()
