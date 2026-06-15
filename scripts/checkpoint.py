"""Checkpoint 统一入口 Facade — 论文-研报工作流 v1.8.1

本项目历史上存在 3 个 checkpoint 相关文件，本模块作为统一对外入口：

  ┌─────────────────────────────────────────────────────────────┐
  │  面向用户（强交互、断点）                                     │
  │  scripts/pipeline_checkpoint.py                              │
  │    ├─ InteractivePipelineCheckpoint  (CLI 强制等待用户输入)  │
  │    ├─ Stage / StageResult / DecisionOption                  │
  │    └─ 主要用于 8 步流程的 阶段过渡 + 模拟数据授权            │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │  底层实现（自动断点）                                         │
  │  scripts/core/checkpoint.py                                  │
  │    ├─ PipelineCheckpoint       (frozen snapshot dataclass)  │
  │    ├─ CheckpointManager        (CRUD on JSON files)         │
  │    └─ CheckpointableOrchestrator (drop-in wrapper)          │
  │  scripts/core/checkpoint_pipeline_integration.py             │
  │    ├─ CheckpointedEnhancedPipeline                          │
  │    └─ CheckpointCLI / checkpoint_resume / checkpoint_list   │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │  scripts/checkpoint.py  ← 你在这里                          │
  │    本模块 — 统一 re-export + 选择性 facade                  │
  └─────────────────────────────────────────────────────────────┘

使用建议:
    # 大多数场景（用户级 CLI 强制 checkpoint）
    from scripts.checkpoint import InteractivePipelineCheckpoint, Stage

    # 自动断点（程序内部）
    from scripts.checkpoint import CheckpointManager, PipelineCheckpoint
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────
# 下层：自动断点续传
# ─────────────────────────────────────────────────────────────────────
from scripts.core.checkpoint import (
    CheckpointableOrchestrator,
    CheckpointManager,
    PipelineCheckpoint,
    PipelineTelemetry,
    get_telemetry,
)
from scripts.core.checkpoint_pipeline_integration import (
    CheckpointCLI,
    CheckpointedEnhancedPipeline,
    checkpoint_list,
    checkpoint_resume,
)

# ─────────────────────────────────────────────────────────────────────
# 上层：交互式 CLI 强制 checkpoint
# ─────────────────────────────────────────────────────────────────────
from scripts.pipeline_checkpoint import (
    DecisionOption,
    InteractivePipelineCheckpoint,
    Stage,
    StageResult,
)

__all__ = [
    # Upper layer (interactive)
    "Stage",
    "StageResult",
    "DecisionOption",
    "InteractivePipelineCheckpoint",
    # Lower layer (automatic)
    "PipelineCheckpoint",
    "CheckpointManager",
    "CheckpointableOrchestrator",
    "PipelineTelemetry",
    "get_telemetry",
    # Integration helpers
    "CheckpointedEnhancedPipeline",
    "CheckpointCLI",
    "checkpoint_resume",
    "checkpoint_list",
]


def quick_help() -> str:
    """Quick reference for which checkpoint to use when.

    Returns:
        A short guide string for developers.
    """
    return """
    Quick guide:
      • 用户研究流程的强制 checkpoint     →  InteractivePipelineCheckpoint.wait_at_checkpoint()
      • 后台任务自动保存 / 崩溃恢复        →  CheckpointManager.save() / load_latest()
      • 包装 agent pipeline 自动 checkpoint →  CheckpointedEnhancedPipeline
      • 列出/恢复历史 checkpoint           →  checkpoint_list() / checkpoint_resume()
    """
