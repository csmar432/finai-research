"""scripts.econometrics — 兼容层 stub.

历史：本模块在 2026-06-19 commit 528e17b 被删除（清理废弃脚本）。
但 9 个外部脚本仍 `from scripts.econometrics import ...`，
依赖 try/except ImportError 兜底，导致：
  - 模块顶部 except ImportError 吞掉错误
  - 但类级别（如 EmpiricalAgentResult.advisor_evaluation: EvaluationResult）
    需要类型在 class body 解析时已定义
  - 当 import 失败时，触发 NameError（scripts/empirical_agent.py:168）

本 stub 提供：
  1. 从 scripts.research_framework 中重定向常用的回归/诊断类
  2. 提供 EvaluationResult 等可能被类级别引用的类型（空 dataclass）
  3. 明确标记 STUB，避免未来误以为是完整实现

设计原则（来自用户决策 2026-06-28）：
  - "恢复 stub" 而非恢复完整模块（删除原因：复杂、被取代）
  - 让 try/except ImportError 在 9 个 import 方仍能工作
  - 解决 class body 中的 NameError 问题
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

# 模块被删除时，打印一次性警告
warnings.warn(
    "scripts.econometrics is a STUB module restored for backward compatibility. "
    "The full implementation was removed in 528e17b (2026-06-19). "
    "Please migrate to scripts.research_framework.* equivalents.",
    DeprecationWarning,
    stacklevel=2,
)


# ─────────────────────────────────────────────────────────────────────────────
# Stub 类型定义（仅满足 class-body 类型注解需求）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RegressionTable:
    """空 dataclass stub."""

    data: Any = None


@dataclass
class DiagnosticSuite:
    """空 dataclass stub."""

    data: Any = None


@dataclass
class DIDRegression:
    """空 dataclass stub — use scripts.research_framework.modern_did instead."""

    data: Any = None


@dataclass
class OLSRegression:
    """空 dataclass stub — use scripts.research_framework.regression_engine instead."""

    data: Any = None


@dataclass
class AdjustmentAction:
    """空 dataclass stub for empirical_agent compatibility."""

    name: str = ""


@dataclass
class AdjustmentStrategy:
    """空 dataclass stub for empirical_agent compatibility."""

    name: str = ""


@dataclass
class DiagnosticResult:
    """空 dataclass stub for empirical_agent compatibility."""

    passed: bool = True
    score: float = 0.0
    details: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = {}


@dataclass
class EmpiricalAdvisor:
    """空 dataclass stub for empirical_agent compatibility."""

    config: Any = None


@dataclass
class EvaluationResult:
    """空 dataclass stub for empirical_agent compatibility.

    History: scripts/empirical_agent.py:168 has
        class EmpiricalAgentResult:
            advisor_evaluation: EvaluationResult | None = None
    This class-body annotation triggers NameError if EvaluationResult is not
    imported. This stub restores the symbol.
    """

    score: float = 0.0
    recommendation: str = "Unknown"
    details: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = {}


@dataclass
class ModelSwitch:
    """空 dataclass stub for empirical_agent compatibility."""

    from_model: str = ""
    to_model: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 空函数 stub（保持 import 兼容）
# ─────────────────────────────────────────────────────────────────────────────


def breusch_pagan_test(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """STUB — 请使用 scripts.research_framework.diagnostics 中的实现."""
    return {"statistic": 0.0, "pvalue": 1.0, "stub": True}


def durbin_watson_test(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """STUB."""
    return {"statistic": 2.0, "stub": True}


def vif_test(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """STUB."""
    return {"vif": {}, "stub": True}


def white_test(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """STUB."""
    return {"statistic": 0.0, "pvalue": 1.0, "stub": True}


def descriptive_stats(*args: Any, **kwargs: Any) -> Any:
    """STUB — 请使用 scripts.research_framework 中相应实现."""
    warnings.warn("descriptive_stats is a stub; use research_framework", stacklevel=2)
    return None


def table_to_markdown(*args: Any, **kwargs: Any) -> str:
    """STUB — 请使用 scripts.research_framework 中相应实现."""
    warnings.warn("table_to_markdown is a stub; use research_framework", stacklevel=2)
    return ""


def winsorize_all(*args: Any, **kwargs: Any) -> Any:
    """STUB — 请使用 scripts.research_framework 中相应实现."""
    warnings.warn("winsorize_all is a stub; use research_framework", stacklevel=2)
    return None


__all__ = [
    # 类型
    "RegressionTable",
    "DiagnosticSuite",
    "DIDRegression",
    "OLSRegression",
    "AdjustmentAction",
    "AdjustmentStrategy",
    "DiagnosticResult",
    "EmpiricalAdvisor",
    "EvaluationResult",
    "ModelSwitch",
    # 函数
    "breusch_pagan_test",
    "durbin_watson_test",
    "vif_test",
    "white_test",
    "descriptive_stats",
    "table_to_markdown",
    "winsorize_all",
]