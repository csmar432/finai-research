"""
collaboration_layer.py — 多用户协作层 + 子步 Checkpoint

Part 1: 多用户协作层（Shared Knowledge + RBAC）
- 共享研究知识库（跨用户的知识条目）
- 基于角色的访问控制（RBAC）
- 协作文档标注和评论

Part 2: 子步 Checkpoint（Intermediate Save）
- 长阶段内的中间保存（每 N 个子步骤保存一次）
- 支持 Autonomy Loop 中的迭代执行 checkpoint
- 支持 LangGraph 图执行中的节点内 checkpoint

Usage:
    # 多用户协作
    layer = CollaborationLayer(knowledge_base=ck)
    layer.share_entry("user_B", entry_id="paper:003")
    layer.grant_role("user_B", Role.CONTRIBUTOR)

    # 子步 checkpoint
    subchk = SubStepCheckpoint(interval=5)
    for i, step in enumerate(large_steps):
        result = execute(step)
        subchk.save_if_needed(i, result, {"step": i, "total": len(large_steps)})
        if subchk.should_stop():
            break
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "Role",
    "CollaborationLayer",
    "SubStepCheckpoint",
    "CheckpointStrategy",
]


# ─── 角色类型 ─────────────────────────────────────────────────────────

class Role(str, Enum):
    """用户角色。"""
    ADMIN = "admin"
    RESEARCHER = "researcher"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"
    GUEST = "guest"


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"read", "write", "delete", "share", "admin"},
    Role.RESEARCHER: {"read", "write", "share"},
    Role.CONTRIBUTOR: {"read", "write"},
    Role.VIEWER: {"read"},
    Role.GUEST: set(),
}


# ─── 多用户协作层 ─────────────────────────────────────────────────────

@dataclass
class User:
    """用户。"""
    user_id: str
    name: str
    role: Role
    created_at: float
    last_active: float
    shared_entries: list[str] = field(default_factory=list)  # shared entry IDs
    metadata: dict = field(default_factory=dict)


@dataclass
class SharedEntry:
    """共享条目。"""
    entry_id: str
    owner_id: str
    content: Any
    shared_with: dict[str, Role]  # user_id -> Role
    created_at: float
    updated_at: float
    version: int
    annotations: list[dict] = field(default_factory=list)  # 协作注释


@dataclass
class CollaborationResult:
    """协作结果。"""
    success: bool
    message: str
    shared_entry: SharedEntry | None = None


class CollaborationLayer:
    """
    多用户协作层。

    功能：
    1. 共享知识库：跨用户共享研究知识条目
    2. RBAC：基于角色的访问控制
    3. 协作文档标注：用户可以在共享条目上添加注释
    4. 版本控制：共享条目的版本追踪

    Usage:
        layer = CollaborationLayer(cross_session_knowledge=ck)

        # 管理员添加用户
        layer.add_user("user_A", "Alice", Role.ADMIN)
        layer.add_user("user_B", "Bob", Role.RESEARCHER)

        # 共享知识条目
        result = layer.share_entry("user_A", entry_id="paper:001", shared_with=["user_B"], role=Role.CONTRIBUTOR)

        # Bob 读取（通过协作层）
        entry = layer.get_shared_entry("user_B", entry_id="paper:001")

        # Bob 添加注释
        layer.add_annotation("user_B", entry_id="paper:001", comment="Important!")
    """

    def __init__(self, cross_session_knowledge=None):
        self.ck = cross_session_knowledge

        # 用户存储
        self._users: dict[str, User] = {}
        self._shared_entries: dict[str, SharedEntry] = {}

        # 默认管理员
        self.add_user("system_admin", "System Admin", Role.ADMIN)

    # ── 用户管理 ──────────────────────────────────────────────────────

    def add_user(
        self,
        user_id: str,
        name: str,
        role: Role = Role.VIEWER,
    ) -> User:
        """添加用户。"""
        user = User(
            user_id=user_id,
            name=name,
            role=role,
            created_at=time.time(),
            last_active=time.time(),
        )
        self._users[user_id] = user
        logger.info(f"[Collab] User added: {name} ({role.value})")
        return user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def update_user_role(self, admin_id: str, target_user_id: str, new_role: Role) -> bool:
        """管理员更新用户角色。"""
        admin = self._users.get(admin_id)
        if not admin or Role.ADMIN not in ROLE_PERMISSIONS.get(admin.role, set()):
            return False
        target = self._users.get(target_user_id)
        if not target:
            return False
        target.role = new_role
        logger.info(f"[Collab] {admin.name} changed {target.name}'s role to {new_role.value}")
        return True

    def list_users(self, role_filter: Role | None = None) -> list[User]:
        users = list(self._users.values())
        if role_filter:
            users = [u for u in users if u.role == role_filter]
        return users

    def _check_permission(self, user_id: str, permission: str) -> bool:
        """检查用户是否有指定权限。"""
        user = self._users.get(user_id)
        if not user:
            return False
        return permission in ROLE_PERMISSIONS.get(user.role, set())

    # ── 知识共享 ──────────────────────────────────────────────────────

    def share_entry(
        self,
        owner_id: str,
        entry_id: str,
        shared_with: list[str] | None = None,
        role: Role = Role.VIEWER,
        content: Any = None,
    ) -> CollaborationResult:
        """
        共享知识条目。

        Args:
            owner_id: 所有者用户 ID
            entry_id: 知识条目 ID
            shared_with: 要共享的用户 ID 列表
            role: 授予的默认角色
            content: 条目内容（如果不在 cross_session_knowledge 中）

        Returns:
            CollaborationResult
        """
        owner = self._users.get(owner_id)
        if not owner:
            return CollaborationResult(False, f"User '{owner_id}' not found")

        if not self._check_permission(owner_id, "share"):
            return CollaborationResult(False, f"User '{owner_id}' lacks share permission")

        # 获取或创建共享条目
        if entry_id in self._shared_entries:
            shared = self._shared_entries[entry_id]
            if shared.owner_id != owner_id:
                return CollaborationResult(False, "Not the owner of this entry")
        else:
            shared = SharedEntry(
                entry_id=entry_id,
                owner_id=owner_id,
                content=content or {},
                shared_with={},
                created_at=time.time(),
                updated_at=time.time(),
                version=1,
            )
            self._shared_entries[entry_id] = shared

        # 添加共享用户
        shared_with = shared_with or []
        for uid in shared_with:
            if uid in self._users:
                shared.shared_with[uid] = role
                if uid not in owner.shared_entries:
                    owner.shared_entries.append(entry_id)
                logger.info(f"[Collab] {owner.name} shared '{entry_id}' with {self._users[uid].name}")

        shared.updated_at = time.time()
        return CollaborationResult(True, f"Shared with {len(shared_with)} users", shared)

    def get_shared_entry(self, user_id: str, entry_id: str) -> SharedEntry | None:
        """获取共享条目（检查权限）。"""
        user = self._users.get(user_id)
        if not user:
            return None

        # 管理员和所有者可以访问所有
        if user.role == Role.ADMIN or Role.ADMIN in ROLE_PERMISSIONS.get(user.role, set()):
            return self._shared_entries.get(entry_id)

        # 检查是否被共享
        shared = self._shared_entries.get(entry_id)
        if not shared:
            # 尝试从 cross_session_knowledge 获取
            return None

        if user_id in shared.shared_with or shared.owner_id == user_id:
            return shared

        return None

    def revoke_access(self, owner_id: str, entry_id: str, target_user_id: str) -> bool:
        """撤销共享访问权限。"""
        shared = self._shared_entries.get(entry_id)
        owner = self._users.get(owner_id)
        if not shared or not owner:
            return False
        if shared.owner_id != owner_id:
            return False

        if target_user_id in shared.shared_with:
            del shared.shared_with[target_user_id]
            shared.updated_at = time.time()
            logger.info(f"[Collab] {owner.name} revoked {target_user_id}'s access to '{entry_id}'")
            return True
        return False

    def add_annotation(
        self,
        user_id: str,
        entry_id: str,
        comment: str,
        position: str | None = None,
    ) -> bool:
        """添加协作注释。"""
        entry = self.get_shared_entry(user_id, entry_id)
        if not entry:
            return False

        annotation = {
            "annotation_id": hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:12],
            "user_id": user_id,
            "user_name": self._users.get(user_id, User("", "", Role.VIEWER, 0, 0)).name,
            "comment": comment,
            "position": position,
            "created_at": time.time(),
        }
        entry.annotations.append(annotation)
        entry.version += 1
        entry.updated_at = time.time()
        logger.info(f"[Collab] {self._users[user_id].name} added annotation to '{entry_id}'")
        return True

    def list_shared_for_user(self, user_id: str) -> list[SharedEntry]:
        """列出用户可访问的所有共享条目。"""
        user = self._users.get(user_id)
        if not user:
            return []

        results = []
        for entry in self._shared_entries.values():
            if entry.owner_id == user_id or user_id in entry.shared_with:
                results.append(entry)
        return sorted(results, key=lambda e: e.updated_at, reverse=True)

    def get_shared_stats(self) -> dict:
        """获取协作统计。"""
        return {
            "total_users": len(self._users),
            "total_shared_entries": len(self._shared_entries),
            "total_annotations": sum(len(e.annotations) for e in self._shared_entries.values()),
            "role_distribution": {
                role.value: sum(1 for u in self._users.values() if u.role == role)
                for role in Role
            },
        }


# ─── 子步 Checkpoint ─────────────────────────────────────────────────

class CheckpointStrategy(str, Enum):
    """子步 checkpoint 策略。"""
    EVERY_N_STEPS = "every_n_steps"     # 每 N 步保存一次
    ON_SIGNIFICANT_RESULT = "on_significant"  # 有重要结果时保存
    ON_ERROR = "on_error"               # 出错时保存（用于恢复）
    ON_USER_REQUEST = "on_user_request"  # 用户请求时保存
    ADAPTIVE = "adaptive"               # 自适应（根据步骤时长）


@dataclass
class SubStepCheckpoint:
    """
    长阶段内的中间 checkpoint。

    用于：
    1. Autonomy Loop 中每 N 次迭代保存一次
    2. LangGraph 节点内每 N 个子步骤保存一次
    3. 大规模数据处理的中途保存

    Usage:
        subchk = SubStepCheckpoint(interval=5, strategy=CheckpointStrategy.EVERY_N_STEPS)

        for i, step in enumerate(long_running_steps):
            result = execute(step)
            should_save, reason = subchk.should_save(i, result, state)

            if should_save:
                subchk.save(i, result, state)
                print(f"Checkpoint saved at step {i}: {reason}")

            if subchk.should_stop(i, len(steps)):
                print(f"Stopping at step {i} (max reached)")
                break
    """

    interval: int = 5
    strategy: CheckpointStrategy = CheckpointStrategy.EVERY_N_STEPS
    max_checkpoints: int = 20
    significant_threshold: float = 0.1  # 结果变化超过此阈值 → 重要
    _checkpoints: list[dict] = field(default_factory=list)
    _last_significant_step: int = 0

    def should_save(
        self,
        step_idx: int,
        result: Any,
        state: dict | None = None,
    ) -> tuple[bool, str]:
        """
        判断是否应该保存 checkpoint。

        Returns:
            (should_save, reason)
        """
        if self.strategy == CheckpointStrategy.EVERY_N_STEPS:
            if step_idx % self.interval == 0 and step_idx > 0:
                return True, f"every_{self.interval}_steps"
            return False, ""

        elif self.strategy == CheckpointStrategy.ON_SIGNIFICANT_RESULT:
            if step_idx == 0:
                return False, ""
            if self._is_significant_change(result, state):
                self._last_significant_step = step_idx
                return True, f"significant_change_at_step_{step_idx}"
            return False, ""

        elif self.strategy == CheckpointStrategy.ON_ERROR:
            if isinstance(result, dict) and result.get("error"):
                return True, f"error_at_step_{step_idx}"
            return False, ""

        return False, ""

    def should_stop(
        self,
        step_idx: int,
        total_steps: int,
        max_steps: int | None = None,
    ) -> bool:
        """判断是否应该停止执行。"""
        if max_steps and step_idx >= max_steps:
            return True
        if self.max_checkpoints and len(self._checkpoints) >= self.max_checkpoints:
            return True
        if step_idx >= total_steps:
            return True
        return False

    def save(
        self,
        step_idx: int,
        result: Any,
        state: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """保存 checkpoint。"""
        checkpoint = {
            "step_idx": step_idx,
            "timestamp": time.time(),
            "datetime": datetime.fromtimestamp(time.time()).isoformat(),
            "result": self._serialize_result(result),
            "state": (self._serialize_result(state) if state else {}),
            "metadata": metadata or {},
            "checkpoint_idx": len(self._checkpoints),
        }
        self._checkpoints.append(checkpoint)

        # 限制数量
        if len(self._checkpoints) > self.max_checkpoints:
            self._checkpoints = self._checkpoints[-self.max_checkpoints:]

        logger.info(f"[SubStepCheckpoint] Saved at step {step_idx} (#{len(self._checkpoints)})")
        return checkpoint

    def get_latest(self) -> dict | None:
        """获取最新的 checkpoint。"""
        return self._checkpoints[-1] if self._checkpoints else None

    def get_all(self) -> list[dict]:
        """获取所有 checkpoint。"""
        return list(self._checkpoints)

    def restore(self, checkpoint_idx: int | None = None) -> dict | None:
        """
        从 checkpoint 恢复。

        Args:
            checkpoint_idx: 要恢复的 checkpoint 索引（None = 最新）

        Returns:
            恢复的状态字典
        """
        if checkpoint_idx is None:
            chk = self.get_latest()
        else:
            chk = self._checkpoints[checkpoint_idx] if checkpoint_idx < len(self._checkpoints) else None
        return chk["state"] if chk else None

    def restore_result(self, checkpoint_idx: int | None = None) -> Any:
        """从 checkpoint 恢复结果。"""
        chk = self._checkpoints[checkpoint_idx] if checkpoint_idx is not None else self.get_latest()
        return chk["result"] if chk else None

    def get_recovery_plan(self, total_steps: int) -> list[dict]:
        """
        生成恢复计划：告诉调用者从哪个 step 继续。

        Returns:
            list of {"resume_from": step_idx, "checkpoint_idx": int}
        """
        plan = []
        for i, chk in enumerate(self._checkpoints):
            resume_from = chk["step_idx"] + 1
            if resume_from < total_steps:
                plan.append({
                    "resume_from": resume_from,
                    "checkpoint_idx": i,
                    "saved_at_step": chk["step_idx"],
                    "datetime": chk["datetime"],
                })
        return plan

    def _is_significant_change(self, result: Any, state: dict | None) -> bool:
        """判断结果是否有显著变化。"""
        if not self._checkpoints:
            return False

        prev = self._checkpoints[-1].get("result")
        if prev is None or result is None:
            return False

        if isinstance(result, (int, float)) and isinstance(prev, (int, float)):
            if prev != 0:
                rel_change = abs(result - prev) / abs(prev)
                return rel_change > self.significant_threshold
            return abs(result - prev) > self.significant_threshold

        if isinstance(result, dict) and isinstance(prev, dict):
            # 比较关键数值字段
            for key in ["score", "loss", "accuracy", "coefficient", "signal"]:
                if key in result and key in prev:
                    r_val = result[key]
                    p_val = prev[key]
                    if isinstance(r_val, (int, float)) and isinstance(p_val, (int, float)):
                        if p_val != 0:
                            return abs(r_val - p_val) / abs(p_val) > self.significant_threshold
                        return abs(r_val - p_val) > self.significant_threshold

        return False

    def _serialize_result(self, result: Any) -> Any:
        """序列化结果（去除不可 JSON 序列化的对象）。"""
        if result is None:
            return None
        try:
            json.dumps(result)
            return result
        except (TypeError, ValueError):
            return {"__repr__": str(result)[:500]}

    def clear(self):
        """清空所有 checkpoint。"""
        self._checkpoints.clear()
        self._last_significant_step = 0
