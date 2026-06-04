"""Core modules for the economic research agent."""

from scripts.core.langsmith_integration import (
    LangSmithTracer,
    LocalTracer,
    get_tracer,
    traceable,
)
from scripts.core.memory import ContextUnit, ResearchMemory
from scripts.core.observability import (
    AgentObserver,
    EvaluationReport,
    EvaluationResult,
    LLMasJudge,
    MetricsCollector,
    OTelTracer,
    Span,
    StructuredLogger,
    get_observer,
    reset_observer,
    wrap_llm_gateway,
    wrap_tool_selector,
)
from scripts.core.planner import ResearchPlanner, Task, TaskStatus, TaskType
from scripts.core.provenance import (
    ChartMetadata,
    ProvenanceNode,
    ProvenanceTracker,
    get_tracker,
    register_chart,
    register_data_source,
    reset_tracker,
    set_tracker,
)
from scripts.core.reflector import QUALITY_FLAGS, Evaluation, ResearchReflector
from scripts.core.session import (
    ResearchSession,
    SessionConfig,
    SessionState,
    SessionStatus,
)
from scripts.core.tool_selector import (
    CostTier,
    ToolCapability,
    ToolResult,
    ToolSelection,
    ToolSelector,
)

__all__ = [
    # Memory
    "ResearchMemory",
    "ContextUnit",
    # Provenance
    "ProvenanceNode",
    "ProvenanceTracker",
    "ChartMetadata",
    "register_chart",
    "register_data_source",
    "get_tracker",
    "set_tracker",
    "reset_tracker",
    # Planner
    "ResearchPlanner",
    "Task",
    "TaskStatus",
    "TaskType",
    # Reflector
    "Evaluation",
    "QUALITY_FLAGS",
    "ResearchReflector",
    # Session
    "ResearchSession",
    "SessionConfig",
    "SessionState",
    "SessionStatus",
    # Tool selector
    "CostTier",
    "ToolCapability",
    "ToolSelection",
    "ToolResult",
    "ToolSelector",
    # Observability
    "AgentObserver",
    "Span",
    "MetricsCollector",
    "LLMasJudge",
    "StructuredLogger",
    "OTelTracer",
    "EvaluationResult",
    "EvaluationReport",
    "wrap_llm_gateway",
    "wrap_tool_selector",
    "get_observer",
    "reset_observer",
    # LangSmith / Tracing
    "LangSmithTracer",
    "LocalTracer",
    "get_tracer",
    "traceable",
]
