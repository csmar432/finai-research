#!/usr/bin/env python3
"""
时间旅行调试器
==============
提供Agent决策回溯、状态快照、重放等功能

功能：
1. 状态快照 - 保存任意时间点的状态
2. 时间旅行 - 回溯到任意历史状态
3. 决策回溯 - 查看Agent的决策历史
4. 重放执行 - 从某个状态重新执行
"""

from __future__ import annotations

__all__ = [
    "StateSnapshot",
    "DecisionRecord",
    "ExecutionTrace",
]

import copy
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# 数据类定义
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StateSnapshot:
    """状态快照"""
    snapshot_id: str
    agent_id: str
    timestamp: float
    state_type: str  # "running", "decision", "tool_call", "result"
    state_data: dict
    parent_snapshot_id: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class DecisionRecord:
    """决策记录"""
    decision_id: str
    agent_id: str
    timestamp: float
    decision_point: str  # 决策点描述
    options: list[dict]  # 可选方案
    chosen: int  # 选择的索引
    reasoning: str  # 选择原因
    context: dict  # 上下文信息

@dataclass
class ExecutionTrace:
    """执行追踪"""
    trace_id: str
    agent_id: str
    start_time: float
    end_time: float | None
    snapshots: list[StateSnapshot]
    decisions: list[DecisionRecord]
    final_state: dict | None


# ═══════════════════════════════════════════════════════════════════════════
# 时间旅行调试器
# ═══════════════════════════════════════════════════════════════════════════

class TimeTravelDebugger:
    """
    时间旅行调试器

    核心功能：
    1. 快照管理 - 保存和恢复状态
    2. 历史回溯 - 回溯到任意历史点
    3. 差异分析 - 比较两个状态的差异
    4. 重放执行 - 从快照重新执行
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = ".cache/debugger.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._write_lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

        self._current_trace_id: str | None = None
        self._snapshots: dict[str, StateSnapshot] = {}
        self._decisions: list[DecisionRecord] = []

    def _init_db(self):
        """初始化数据库"""
        cursor = self._conn.cursor()

        # 快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                state_type TEXT NOT NULL,
                state_data TEXT NOT NULL,
                parent_snapshot_id TEXT,
                metadata TEXT,
                trace_id TEXT
            )
        """)

        # 决策表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                decision_point TEXT NOT NULL,
                options TEXT NOT NULL,
                chosen INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                context TEXT NOT NULL,
                trace_id TEXT
            )
        """)

        # 追踪表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                final_state TEXT
            )
        """)

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_agent ON snapshots(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_trace ON snapshots(trace_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_agent ON decisions(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_time ON decisions(timestamp)")

        with self._write_lock:
            self._conn.commit()

    # ═══════════════════════════════════════════════════════════════════════
    # 追踪管理
    # ═══════════════════════════════════════════════════════════════════════

    def start_trace(self, agent_id: str) -> str:
        """开始新的追踪"""
        trace_id = str(uuid.uuid4())

        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO traces (trace_id, agent_id, start_time)
                VALUES (?, ?, ?)
            """, (trace_id, agent_id, time.time()))
            self._conn.commit()

            self._current_trace_id = trace_id
            self._snapshots = {}
            self._decisions = []

        return trace_id

    def end_trace(self, final_state: dict = None):
        """结束当前追踪"""
        if not self._current_trace_id:
            return

        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE traces
                SET end_time = ?, final_state = ?
                WHERE trace_id = ?
            """, (time.time(), json.dumps(final_state or {}), self._current_trace_id))
            self._conn.commit()

            self._current_trace_id = None

    def get_trace(self, trace_id: str) -> ExecutionTrace | None:
        """获取追踪详情"""
        cursor = self._conn.cursor()

        # 获取追踪信息
        cursor.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
        trace_row = cursor.fetchone()

        if not trace_row:
            return None

        # 获取快照
        cursor.execute("""
            SELECT * FROM snapshots
            WHERE trace_id = ?
            ORDER BY timestamp
        """, (trace_id,))

        snapshots = []
        for row in cursor.fetchall():
            snapshots.append(StateSnapshot(
                snapshot_id=row[0],
                agent_id=row[1],
                timestamp=row[2],
                state_type=row[3],
                state_data=json.loads(row[4]),
                parent_snapshot_id=row[5],
                metadata=json.loads(row[6]) if row[6] else {}
            ))

        # 获取决策
        cursor.execute("""
            SELECT * FROM decisions
            WHERE trace_id = ?
            ORDER BY timestamp
        """, (trace_id,))

        decisions = []
        for row in cursor.fetchall():
            decisions.append(DecisionRecord(
                decision_id=row[0],
                agent_id=row[1],
                timestamp=row[2],
                decision_point=row[3],
                options=json.loads(row[4]),
                chosen=row[5],
                reasoning=row[6],
                context=json.loads(row[7])
            ))

        return ExecutionTrace(
            trace_id=trace_id,
            agent_id=trace_row[1],
            start_time=trace_row[2],
            end_time=trace_row[3],
            snapshots=snapshots,
            decisions=decisions,
            final_state=json.loads(trace_row[4]) if trace_row[4] else None
        )

    def list_traces(self, agent_id: str = None, limit: int = 20) -> list[dict]:
        """列出追踪记录"""
        cursor = self._conn.cursor()

        if agent_id:
            cursor.execute("""
                SELECT trace_id, agent_id, start_time, end_time
                FROM traces
                WHERE agent_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            """, (agent_id, limit))
        else:
            cursor.execute("""
                SELECT trace_id, agent_id, start_time, end_time
                FROM traces
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))

        traces = []
        for row in cursor.fetchall():
            traces.append({
                "trace_id": row[0],
                "agent_id": row[1],
                "start_time": row[2],
                "end_time": row[3],
                "duration": row[3] - row[2] if row[3] else None
            })

        return traces

    # ═══════════════════════════════════════════════════════════════════════
    # 快照管理
    # ═══════════════════════════════════════════════════════════════════════

    def take_snapshot(
        self,
        agent_id: str,
        state_type: str,
        state_data: dict,
        metadata: dict = None,
        parent_id: str = None
    ) -> StateSnapshot:
        """创建状态快照"""
        snapshot = StateSnapshot(
            snapshot_id=str(uuid.uuid4()),
            agent_id=agent_id,
            timestamp=time.time(),
            state_type=state_type,
            state_data=copy.deepcopy(state_data),
            parent_snapshot_id=parent_id,
            metadata=metadata or {}
        )

        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO snapshots
                (snapshot_id, agent_id, timestamp, state_type, state_data, parent_snapshot_id, metadata, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.snapshot_id,
                snapshot.agent_id,
                snapshot.timestamp,
                snapshot.state_type,
                json.dumps(snapshot.state_data),
                snapshot.parent_snapshot_id,
                json.dumps(snapshot.metadata),
                self._current_trace_id
            ))
            self._conn.commit()

            self._snapshots[snapshot.snapshot_id] = snapshot

        return snapshot

    def get_snapshot(self, snapshot_id: str) -> StateSnapshot | None:
        """获取快照"""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return StateSnapshot(
            snapshot_id=row[0],
            agent_id=row[1],
            timestamp=row[2],
            state_type=row[3],
            state_data=json.loads(row[4]),
            parent_snapshot_id=row[5],
            metadata=json.loads(row[6]) if row[6] else {}
        )

    def restore_snapshot(self, snapshot_id: str) -> dict | None:
        """恢复到指定快照"""
        snapshot = self.get_snapshot(snapshot_id)

        if not snapshot:
            return None

        # 返回快照状态数据
        return copy.deepcopy(snapshot.state_data)

    def compare_snapshots(self, snapshot_id1: str, snapshot_id2: str) -> dict:
        """比较两个快照的差异"""
        snapshot1 = self.get_snapshot(snapshot_id1)
        snapshot2 = self.get_snapshot(snapshot_id2)

        if not snapshot1 or not snapshot2:
            return {"error": "快照不存在"}

        return {
            "snapshot1": snapshot_id1,
            "snapshot2": snapshot_id2,
            "time_diff": snapshot2.timestamp - snapshot1.timestamp,
            "state1": snapshot1.state_data,
            "state2": snapshot2.state_data,
            "diff": self._compute_diff(snapshot1.state_data, snapshot2.state_data)
        }

    def _compute_diff(self, state1: dict, state2: dict) -> dict:
        """计算状态差异"""
        diff = {
            "added": {},
            "removed": {},
            "changed": {},
            "unchanged": {}
        }

        all_keys = set(state1.keys()) | set(state2.keys())

        for key in all_keys:
            if key not in state1:
                diff["added"][key] = state2[key]
            elif key not in state2:
                diff["removed"][key] = state1[key]
            elif state1[key] != state2[key]:
                diff["changed"][key] = {"from": state1[key], "to": state2[key]}
            else:
                diff["unchanged"][key] = state1[key]

        return diff

    # ═══════════════════════════════════════════════════════════════════════
    # 决策记录
    # ═══════════════════════════════════════════════════════════════════════

    def record_decision(
        self,
        agent_id: str,
        decision_point: str,
        options: list[dict],
        chosen: int,
        reasoning: str,
        context: dict = None
    ) -> DecisionRecord:
        """记录决策"""
        decision = DecisionRecord(
            decision_id=str(uuid.uuid4()),
            agent_id=agent_id,
            timestamp=time.time(),
            decision_point=decision_point,
            options=copy.deepcopy(options),
            chosen=chosen,
            reasoning=reasoning,
            context=copy.deepcopy(context or {})
        )

        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO decisions
                (decision_id, agent_id, timestamp, decision_point, options, chosen, reasoning, context, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.decision_id,
                decision.agent_id,
                decision.timestamp,
                decision.decision_point,
                json.dumps(decision.options),
                decision.chosen,
                decision.reasoning,
                json.dumps(decision.context),
                self._current_trace_id
            ))
            self._conn.commit()

            self._decisions.append(decision)

        return decision

    def get_decisions(self, agent_id: str = None, trace_id: str = None) -> list[DecisionRecord]:
        """获取决策记录"""
        cursor = self._conn.cursor()

        if trace_id:
            cursor.execute("""
                SELECT * FROM decisions
                WHERE trace_id = ?
                ORDER BY timestamp
            """, (trace_id,))
        elif agent_id:
            cursor.execute("""
                SELECT * FROM decisions
                WHERE agent_id = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """, (agent_id,))
        else:
            cursor.execute("""
                SELECT * FROM decisions
                ORDER BY timestamp DESC
                LIMIT 100
            """)

        decisions = []
        for row in cursor.fetchall():
            decisions.append(DecisionRecord(
                decision_id=row[0],
                agent_id=row[1],
                timestamp=row[2],
                decision_point=row[3],
                options=json.loads(row[4]),
                chosen=row[5],
                reasoning=row[6],
                context=json.loads(row[7])
            ))

        return decisions

    # ═══════════════════════════════════════════════════════════════════════
    # 重放执行
    # ═══════════════════════════════════════════════════════════════════════

    def replay_from_snapshot(
        self,
        snapshot_id: str,
        executor: Callable[[dict], dict],
        max_steps: int = 100
    ) -> dict:
        """
        从快照重放执行

        Args:
            snapshot_id: 起始快照ID
            executor: 执行函数，接收当前状态返回新状态
            max_steps: 最大重放步数

        Returns:
            最终状态
        """
        # 获取起始状态
        state = self.restore_snapshot(snapshot_id)

        if state is None:
            raise ValueError(f"快照不存在: {snapshot_id}")

        current_state = state
        step = 0

        while step < max_steps:
            # 保存当前状态作为快照
            self.take_snapshot(
                agent_id=current_state.get("agent_id", "replay"),
                state_type="replay",
                state_data=current_state,
                metadata={"replay_step": step}
            )

            # 执行一步
            try:
                current_state = executor(current_state)
            except Exception as e:
                # 记录错误
                self.take_snapshot(
                    agent_id=current_state.get("agent_id", "replay"),
                    state_type="error",
                    state_data={"error": str(e), "step": step}
                )
                raise

            step += 1

            # 检查是否完成
            if current_state.get("_completed"):
                break

        return current_state

    # ═══════════════════════════════════════════════════════════════════════
    # 分析功能
    # ═══════════════════════════════════════════════════════════════════════

    def analyze_trace(self, trace_id: str) -> dict:
        """分析追踪"""
        trace = self.get_trace(trace_id)

        if not trace:
            return {"error": "追踪不存在"}

        # 计算统计
        duration = trace.end_time - trace.start_time if trace.end_time else time.time() - trace.start_time

        # 决策分析
        decision_choices = [d.chosen for d in trace.decisions]

        # 状态类型分布
        state_types = {}
        for s in trace.snapshots:
            state_types[s.state_type] = state_types.get(s.state_type, 0) + 1

        return {
            "trace_id": trace_id,
            "agent_id": trace.agent_id,
            "duration_seconds": duration,
            "total_snapshots": len(trace.snapshots),
            "total_decisions": len(trace.decisions),
            "state_type_distribution": state_types,
            "decision_choices": decision_choices,
            "time_per_snapshot": duration / len(trace.snapshots) if trace.snapshots else 0
        }

    def close(self):
        """关闭连接"""
        self._conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 全局实例
# ═══════════════════════════════════════════════════════════════════════════

time_travel_debugger = TimeTravelDebugger()
