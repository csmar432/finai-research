"""LangGraph Bridge for Agent Pipeline (optional orchestration backend).

P0 修复 2026-06-28: 此模块之前在 agent_pipeline.py 中被 try-import，
但实际不存在，导致 _LG_BRIDGE_AVAILABLE 永远为 False（软失败掩盖）。

本模块提供:
- 模块级 is_langgraph_available / is_pipeline_available bool 标志
  （与 tests/test_orchestrator_lg_bridge.py 期望一致）
- PipelineRunner 类：支持 topic/venue/language 构造，暴露 .run()/.stream()/.checkpoint()
- run_research_pipeline 函数：入口 API
- 未安装 langgraph 时优雅降级（run/stream 返回 error dict，checkpoint 写入错误标记 JSON）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)


def _probe_langgraph() -> bool:
    """探测 langgraph Python 包是否安装。"""
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_pipeline() -> bool:
    """探测 research_framework.pipeline 是否可导入。"""
    try:
        from scripts.research_framework import pipeline  # noqa: F401
        return True
    except Exception:
        return False


# ── 模块级 bool 标志（满足 tests/test_orchestrator_lg_bridge.py 期望）──────────
is_langgraph_available: bool = _probe_langgraph()
is_pipeline_available: bool = _probe_pipeline()


class PipelineRunner:
    """LangGraph 流水线运行器（占位 stub，兼容测试接口）。

    当 langgraph 未安装时，所有方法安全降级（返回 error/None，写入 error JSON）。
    当 langgraph 已安装但完整实现未到位时，方法会抛出 NotImplementedError
    提示用户升级到 v0.2 或使用默认 AgentPipeline(use_langgraph=False)。
    """

    def __init__(self, topic: str = "", venue: str = "", language: str = "en") -> None:
        self.topic = topic
        self.venue = venue
        self.language = language
        self._checkpoint_data: dict[str, Any] = {
            "topic": topic,
            "venue": venue,
            "language": language,
        }

    def run(self) -> dict:
        """同步运行流水线（占位）。

        Returns:
            dict 包含 is_complete / stage_outputs / error 字段
        """
        if not is_langgraph_available:
            logger.warning("LangGraph not installed, returning error result")
            return {
                "is_complete": False,
                "stage_outputs": {},
                "error": "LangGraph backend not installed (pip install langgraph)",
            }
        raise NotImplementedError(
            "LangGraph PipelineRunner.run is a stub (v0.1). "
            "Full implementation scheduled for v0.2. "
            "Use AgentPipeline(use_langgraph=False) for default flow."
        )

    def stream(self) -> Iterator[dict]:
        """流式运行流水线（占位）。

        Yields:
            dict 包含 stage / status / payload 字段
        """
        if not is_langgraph_available:
            yield {
                "stage": "init",
                "status": "error",
                "payload": {"error": "LangGraph backend not installed"},
            }
            return
        raise NotImplementedError(
            "LangGraph PipelineRunner.stream is a stub (v0.1)."
        )

    def checkpoint(self, path: "str | Path") -> None:
        """写入 checkpoint JSON 文件（始终可用，让测试可通过）。

        当 LangGraph 不可用时，写入错误标记 JSON 而非抛出异常。
        """
        path = Path(path)
        data = dict(self._checkpoint_data)
        if not is_langgraph_available:
            data["status"] = "stub_no_langgraph"
            data["warning"] = "LangGraph backend not installed"
        else:
            data["status"] = "stub_langgraph_available"
            data["warning"] = "Full PipelineRunner implementation pending v0.2"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def run_research_pipeline(
    topic: str,
    venue: str = "working_paper",
    language: str = "en",
    use_langgraph: bool = False,
) -> dict:
    """运行研究流水线（占位 stub）。

    Args:
        topic: 研究主题
        venue: 目标期刊/会议
        language: "zh" / "en"
        use_langgraph: 是否启用 LangGraph 后端

    Returns:
        dict 包含 is_complete / stage_outputs / error 字段
    """
    if not use_langgraph:
        # 委托给 research_framework.pipeline
        if is_pipeline_available:
            try:
                from scripts.research_framework.pipeline import pipeline as _pf
                return _pf.run(topic=topic, venue=venue, language=language)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("research_framework.pipeline fallback failed: %s", exc)
        return {
            "is_complete": False,
            "stage_outputs": {},
            "error": "research_framework.pipeline not available",
        }

    if not is_langgraph_available:
        return {
            "is_complete": False,
            "stage_outputs": {},
            "error": "use_langgraph=True but langgraph not installed",
        }

    raise NotImplementedError(
        "LangGraph backend (use_langgraph=True) is a stub (v0.1). "
        "Use use_langgraph=False for default flow."
    )


__all__ = [
    "PipelineRunner",
    "is_langgraph_available",
    "is_pipeline_available",
    "run_research_pipeline",
]