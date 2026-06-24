"""
scripts/core/analyst.py
======================
Consolidated analyst module — single import entry point.

The following analyst modules have been consolidated into this file:
  - analyst_agents.py      → AnalystType, ParallelAnalystOrchestrator, AnalystFactory, etc.
  - ai_parliament.py        → AIParliament, AIParliamentHITLIntegration, MemberType, etc.
  - multi_agent.py           → MultiAgentOrchestrator, Workflow, Agent, etc.
  - collaboration.py          → CollaborationServer, CollaborationClient, etc.
  - specialized_agents.py    → AdversarialQAAgent, LiteratureGapAgent, DataAuditAgent, etc.

The original files are kept as-is for backward compatibility.
Do not add new code here — add it to the canonical files above.

Usage:
    from scripts.core.analyst import (
        AnalystType,
        ParallelAnalystOrchestrator,
        AIParliament,
        MultiAgentOrchestrator,
        CollaborationServer,
    )

Canonical files (in order of precedence):
    1. scripts/core/analyst_agents.py   — primary analyst implementation (100KB, most complete)
    2. scripts/core/ai_parliament.py     — AI parliament multi-agent debate
    3. scripts/core/multi_agent.py         — general multi-agent orchestrator
    4. scripts/core/collaboration.py       — real-time collaboration
    5. scripts/core/specialized_agents.py — adversarial/specialized agents
"""

# ── Analyst Agents ──────────────────────────────────────────────────────────────
from scripts.core.analyst_agents import (
    AnalystType,
    AnalystConfig,
    AnalystResult,
    CompositeAnalysis,
    DupontDecomposition,
    EnhancedFinancialAnalyst,
    DCFScenario,
    EnhancedValuationAnalyst,
    AccrualsAnalysis,
    EnhancedEarningsQualityAnalyst,
    BaseAnalystAgent,
    EnhancedFundamentalFinancialAgent,
    EnhancedValuationAgent,
    EnhancedEarningsQualityAgent,
    EnhancedMarketAnalyst,
    EnhancedCompetitiveAnalyst,
    EnhancedRiskAnalyst,
    AnalystFactory,
    ParallelAnalystOrchestrator,
    TushareDataAgent,
)

# ── AI Parliament ──────────────────────────────────────────────────────────────
from scripts.core.ai_parliament import (
    MemberType,
    MemberConfig,
    DebateRound,
    RebuttalRound,
    Verdict,
    BaseMemberAgent,
    ChairAgent,
    EngineeringMemberAgent,
    FinanceMemberAgent,
    MemberMethodologyAgent,
    MemberStatisticsAgent,
    MemberWritingAgent,
    AIParliament,
    AIParliamentHITLIntegration,
)

# ── Multi-Agent Orchestrator ────────────────────────────────────────────────────
from scripts.core.multi_agent import (
    TaskStatus,
    ExecutionMode,
    Agent,
    Task,
    Workflow,
    AgentExecutor,
    DefaultAgentExecutor,
    MultiAgentOrchestrator,
    WorkflowTemplates,
    create_default,
)

# ── Collaboration ──────────────────────────────────────────────────────────────
from scripts.core.collaboration import (
    OperationType,
    Operation,
    UserPresence,
    PaperSnapshot,
    ConflictResolution,
    OperationalTransform,
    CollaborationServer,
    CollaborationClient,
)

# ── Specialized Agents ──────────────────────────────────────────────────────────
from scripts.core.specialized_agents import (
    AgentTask,
    ReviewFinding,
    AgentReviewResult,
    ProofreaderAgent,
    RReviewerAgent,
    TikZCriticAgent,
    AdversarialQAAgent,
    LiteratureGapAgent,
    DataAuditAgent,
    run_all_agents,
)

__all__ = [
    # analyst_agents
    "AnalystType",
    "AnalystConfig",
    "AnalystResult",
    "CompositeAnalysis",
    "DupontDecomposition",
    "EnhancedFinancialAnalyst",
    "DCFScenario",
    "EnhancedValuationAnalyst",
    "AccrualsAnalysis",
    "EnhancedEarningsQualityAnalyst",
    "BaseAnalystAgent",
    "EnhancedFundamentalFinancialAgent",
    "EnhancedValuationAgent",
    "EnhancedEarningsQualityAgent",
    "EnhancedMarketAnalyst",
    "EnhancedCompetitiveAnalyst",
    "EnhancedRiskAnalyst",
    "AnalystFactory",
    "ParallelAnalystOrchestrator",
    "TushareDataAgent",
    "get_analyst",
    "list_analysts",
    "run_parallel_analysis",
    # ai_parliament
    "MemberType",
    "MemberConfig",
    "DebateRound",
    "RebuttalRound",
    "Verdict",
    "BaseMemberAgent",
    "ChairAgent",
    "EngineeringMemberAgent",
    "FinanceMemberAgent",
    "MemberMethodologyAgent",
    "MemberStatisticsAgent",
    "MemberWritingAgent",
    "AIParliament",
    "AIParliamentHITLIntegration",
    "MEMBER_CONFIGS",
    "parliament_main",
    # multi_agent
    "TaskStatus",
    "ExecutionMode",
    "Agent",
    "Task",
    "Workflow",
    "AgentExecutor",
    "DefaultAgentExecutor",
    "MultiAgentOrchestrator",
    "WorkflowTemplates",
    "create_default",
    # collaboration
    "OperationType",
    "Operation",
    "UserPresence",
    "PaperSnapshot",
    "ConflictResolution",
    "OperationalTransform",
    "CollaborationServer",
    "CollaborationClient",
    # specialized_agents
    "AgentTask",
    "ReviewFinding",
    "AgentReviewResult",
    "ProofreaderAgent",
    "RReviewerAgent",
    "TikZCriticAgent",
    "AdversarialQAAgent",
    "LiteratureGapAgent",
    "DataAuditAgent",
    "run_all_agents",
]
