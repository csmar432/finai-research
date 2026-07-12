# Agent Orchestration Architecture

> Created: 2026-05-28
> Last Updated: 2026-07-12 (audit_fix_2026_07_12 — 新增 CLI 入口 + 类名核对)
> Status: Active

This document describes the two distinct orchestrator systems in the codebase and their architectural boundaries.

> **CLI 入口 (v1.0+ 推荐用户入口)**
>
> 上述两个编排器 (`AgentOrchestrator` / `MultiAgentOrchestrator`) 是**库级 API**, 用户应通过以下 CLI 入口调用:
>
> | CLI | 用途 | 模块 |
> |-----|------|------|
> | `python scripts/start_research.py --topic "..."` | 5 轮渐进式主题澄清入口 | `scripts/start_research.py` |
> | `python scripts/agent_pipeline.py --topic "..."` | 端到端研究流水线（主题→论文 PDF） | `scripts/agent_pipeline.py` |
> | `python scripts/agent.py --task "..."` | 单任务智能体入口（轻量级） | `scripts/agent.py` |
>
> README 主推 `start_research.py` 作为新用户入口.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User / Entry Point                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
           ┌────────────────┴─────────────────┐
           │                                  │
           ▼                                  ▼
┌──────────────────────────┐    ┌───────────────────────────────┐
│  AgentOrchestrator        │    │  MultiAgentOrchestrator        │
│  (orchestrator.py)        │    │  (multi_agent.py)              │
│                          │    │                               │
│  Tier 1 ─ Pipeline       │    │  Capability-based routing      │
│  Tier 2 ─ Parallel       │    │  Task-level assignment         │
│      Analysts            │    │  General-purpose               │
│  Tier 3 ─ Ext. MultiAgent│    │                               │
└──────────────────────────┘    └───────────────────────────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────────┐    ┌───────────────────────────────┐
│  BaseAgent (paper_agents)│    │  Agent (dataclass)            │
│  - OutlineAgent           │    │  - research_designer          │
│  - LiteratureReviewAgent  │    │  - literature_reviewer        │
│  - PlottingAgent          │    │  - data_analyst               │
│  - SectionWritingAgent    │    │  - paper_writer               │
│  - ContentRefinementAgent │    │  - reviewer                   │
└──────────────────────────┘    └───────────────────────────────┘
```

---

## 2. L1 — Pipeline Orchestrator (`AgentOrchestrator`)

**File:** `scripts/core/orchestrator.py`

### What it does
- Orchestrates **fixed multi-stage pipelines** for paper writing and research workflows.
- Manages the full lifecycle: `outline → literature → plotting → writing → refinement`.
- Supports **HITL (Human-In-The-Loop) gates** — pauses at configurable checkpoints for human approval before continuing.
- Provides a **message bus** for agent-to-agent communication.
- Integrates with **SelfEvolutionEngine** for iterative improvement.

### Data Models

```python
# orchestrator.py

class PipelineStage(Enum):
    OUTLINE = "outline"
    LITERATURE = "literature"
    PLOTTING = "plotting"
    WRITING = "writing"
    REFINEMENT = "refinement"
    EVALUATION = "evaluation"
    FINANCIAL_ANALYSIS = "financial_analysis"
    REPORT_WRITING = "report_writing"

@dataclass
class PipelineStep:
    stage: PipelineStage
    agent_name: str
    depends_on: list[PipelineStage] = field(default_factory=list)
    hitl_gate: bool = False      # Pause for human approval
    skip: bool = False           # Conditionally skip
    condition: Callable[[dict], bool] | None = None

@dataclass
class PipelineResult:
    pipeline_name: str
    success: bool
    stage_results: dict[PipelineStage, AgentResult]
    final_context: dict[str, Any]
    total_latency_ms: float
    hitl_paused_at: PipelineStage | None = None
    evolution_events: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    timestamp: float
```

### Key Methods

| Method | Description |
|--------|-------------|
| `register(agent: BaseAgent)` | Register a named `BaseAgent` into the registry |
| `register_default_agents()` | Register the 5-agent paper pipeline |
| `register_financial_agents()` | Bootstrap `ParallelAnalystOrchestrator` for financial reports |
| `run_pipeline(steps, input_data, parallel, max_workers)` | Execute sequential or parallel pipeline stages |
| `resume_pipeline(paused_result, steps)` | Resume a HITL-paused pipeline after approval/rejection |
| `run_parallel(agent_names, input_data)` | Run independent agents concurrently |
| `broadcast(message)` | Post a message to the agent message bus |
| `get_messages(agent_name)` | Retrieve messages for a specific agent |

### When to use
- **Paper writing workflows** (outline → literature → plotting → writing → refinement).
- **Research report generation** with financial analyst agents.
- Any workflow that needs **human approval gates** between stages.
- Scenarios requiring **full execution traces** for debugging.

### Agents registered by default

| Agent Name | Role |
|------------|------|
| `outline` | OutlinesAgent — converts research idea to structured outline |
| `literature` | LiteratureReviewAgent — retrieves and verifies ≥90% of citations |
| `plotting` | PlottingAgent — generates matplotlib charts (DPI≥300) |
| `writing` | SectionWritingAgent — writes paper sections |
| `refinement` | ContentRefinementAgent — iteratively improves content |

### HITL Integration
All approval state is managed exclusively by `HITLGate` (`scripts/core/hitl_gate.py`). The legacy `_pending_approvals` dict has been removed — use `approve_step()` and `reject_step()` on the orchestrator, which delegate to `HITLGate`.

---

## 3. L2 — Parallel Analysts (`ParallelAnalystOrchestrator`)

**File:** `scripts/core/analyst_agents.py`

### What it does
- Runs **6 simultaneous financial analyst agents** in parallel:
  - Fundamental Analyst
  - Competitive Analyst
  - Risk Analyst
  - Valuation Analyst
  - Earnings Quality Analyst
  - Macro/Industry Analyst
- Results are aggregated into a structured analyst report.
- Instantiated via `AgentOrchestrator.register_financial_agents()`.

### When to use
- **Financial research report generation** requiring multi-dimensional analysis (fundamental, competitive, risk, valuation).
- Scenarios where **independent analyses** should run concurrently to save time.

### Relationship to `AgentOrchestrator`
`ParallelAnalystOrchestrator` is **owned** by `AgentOrchestrator` (stored at `self._analyst_orchestrator`) when `register_financial_agents()` is called. It is not independently instantiated by the user.

---

## 4. L3 — Multi-Agent Orchestrator (`MultiAgentOrchestrator`)

**File:** `scripts/core/multi_agent.py`

### What it does
- **Capability-based task routing** — finds the best-fit agent for a task by matching required capabilities.
- Supports three execution modes: **sequential**, **parallel**, and **pipeline** (dependency-aware).
- General-purpose task assignment — not tied to any specific workflow.
- **Async execution** via `async_execute_task` / `async_execute_workflow`.

### Data Models

```python
# multi_agent.py

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ExecutionMode(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"

@dataclass
class Agent:
    agent_id: str
    name: str
    role: str
    capabilities: list[str]         # e.g. ["research_design", "hypothesis"]
    system_prompt: str
    max_concurrent: int = 1

@dataclass
class Task:
    task_id: str
    name: str
    description: str
    required_capabilities: list[str]  # e.g. ["literature_search", "writing"]
    input_data: dict
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

@dataclass
class Workflow:
    workflow_id: str
    name: str
    description: str
    agents: list[Agent]
    tasks: list[Task]
    execution_mode: ExecutionMode
    dependencies: dict[str, list[str]]  # task_id -> [dependent_task_ids]
```

### Key Methods

| Method | Description |
|--------|-------------|
| `register_agent(agent: Agent)` | Register an agent with capabilities |
| `find_best_agent(required_capabilities)` | Score all agents by capability overlap, return best match |
| `create_task(name, description, required_capabilities, input_data)` | Create and store a task |
| `assign_task(task_id, agent_id)` | Manually assign a task to a specific agent |
| `execute_task(task_id)` | Execute a single task synchronously |
| `async_execute_task(task_id)` | Execute a single task asynchronously |
| `execute_workflow(workflow_id)` | Execute a full workflow respecting dependencies and execution mode |
| `list_agents()` | Return all registered agents |

### Default Agents

| Agent ID | Name | Capabilities |
|----------|------|--------------|
| `research_designer` | 研究设计专家 | `research_design`, `hypothesis`, `methodology` |
| `literature_reviewer` | 文献综述专家 | `literature_search`, `analysis`, `writing` |
| `data_analyst` | 数据分析专家 | `data_processing`, `statistics`, `visualization` |
| `paper_writer` | 论文写作专家 | `academic_writing`, `editing`, `polishing` |
| `reviewer` | 论文审核专家 | `review`, `quality_check`, `feedback` |

### When to use
- **General task distribution** where tasks need to be routed to specialized agents based on capability requirements.
- Workflows with **dynamic task creation** and capability-based routing.
- Scenarios requiring **async execution** of multiple tasks.
- Research tasks that don't follow the fixed paper pipeline.

---

## 5. Call Graph — Who Calls Whom

```
User / Entry Point
│
├──► AgentOrchestrator
│    │
│    ├──► register_default_agents()
│    │        └──► BaseAgent instances (outline, literature, plotting, writing, refinement)
│    │
│    ├──► register_financial_agents()
│    │        └──► ParallelAnalystOrchestrator
│    │             └──► 6 analyst agents (fundamental, competitive, risk, valuation, etc.)
│    │
│    ├──► run_pipeline(steps, input_data)
│    │        └──► BaseAgent.run() for each step
│    │
│    └──► run_parallel(agent_names, input_data)
│             └──► concurrent.futures → BaseAgent.run() concurrently
│
└──► MultiAgentOrchestrator (independent — not called by AgentOrchestrator)
     │
     ├──► register_agent() / find_best_agent()
     │        └──► Routes Task → Agent by capability matching
     │
     ├──► execute_task(task_id)
     │        └──► DefaultAgentExecutor.execute()
     │             └──► LLM provider (if configured)
     │
     └──► execute_workflow(workflow_id)
              └──► Respects dependencies + ExecutionMode (sequential/parallel/pipeline)
```

**Note:** `MultiAgentOrchestrator` is accessed **independently** of `AgentOrchestrator`. It is not wired into `AgentOrchestrator` — the 3-tier docstring in `orchestrator.py` is aspirational documentation, not a runtime dependency.

---

## 6. Data Model Comparison

| Dimension | `AgentOrchestrator` | `MultiAgentOrchestrator` |
|-----------|---------------------|-------------------------|
| **File** | `scripts/core/orchestrator.py` | `scripts/core/multi_agent.py` |
| **Agent type** | `BaseAgent` (Protocol-based) | `Agent` (dataclass) |
| **Task/Step model** | `PipelineStep` + `PipelineStage` | `Task` (dataclass) |
| **Routing** | Named lookup in `_agents` dict | Capability scoring via `find_best_agent()` |
| **Dependencies** | `depends_on: list[PipelineStage]` | `dependencies: dict[str, list[str]]` |
| **HITL support** | Yes — `hitl_gate` on `PipelineStep` | No |
| **Message bus** | Yes — `broadcast()` / `get_messages()` | No |
| **Tracing** | Full execution trace in `PipelineResult` | No structured trace |
| **Async** | No (uses `concurrent.futures`) | Yes — `async_execute_task`, `async_execute_workflow` |
| **Execution modes** | Sequential + Parallel (via `concurrent.futures`) | Sequential + Parallel + Pipeline |
| **Default domain** | Paper writing, financial reports | General-purpose task distribution |
| **Configurable stop** | `condition: Callable[[dict], bool]` on `PipelineStep` | No |

---

## 7. Migration / Selection Guide

### Use `AgentOrchestrator` when:
- Writing papers or research reports with a **fixed pipeline structure**.
- You need **HITL gates** for human review at specific stages.
- You want **execution tracing** and structured `PipelineResult` output.
- Your workflow maps to: outline → literature → plotting → writing → refinement.
- You need a **message bus** for inter-agent communication.

### Use `MultiAgentOrchestrator` when:
- You have **dynamic tasks** that don't follow a fixed pipeline.
- You want **capability-based routing** (tasks declare requirements, orchestrator finds the best agent).
- You need **async execution** of multiple tasks.
- You're building a **general-purpose multi-agent system** for arbitrary workflows.
- You need **pipeline execution mode** with explicit task dependencies.

### Use `ParallelAnalystOrchestrator` when:
- Generating **financial research reports** requiring simultaneous fundamental, competitive, risk, valuation, and earnings quality analysis.
- Called via `AgentOrchestrator.register_financial_agents()`.

### Anti-patterns to avoid
- **Do not** instantiate both orchestrators for the same workflow — choose one based on the criteria above.
- **Do not** try to add HITL gates to `MultiAgentOrchestrator` — use `AgentOrchestrator` instead.
- **Do not** use `MultiAgentOrchestrator` for fixed pipeline workflows — use `AgentOrchestrator`'s `run_pipeline()` which provides better tracing and stage-level control.

---

## 8. Extending the Architecture

### Adding a new stage to `AgentOrchestrator`
1. Add the stage to `PipelineStage` enum in `orchestrator.py`.
2. Register a `BaseAgent` for the new stage via `orchestrator.register(agent)`.
3. Add a `PipelineStep(stage=PipelineStage.YOUR_STAGE, agent_name="your_agent")` to your pipeline.

### Adding a new agent to `MultiAgentOrchestrator`
1. Define a new `Agent` dataclass instance with appropriate `capabilities`.
2. Call `orchestrator.register_agent(agent)`.
3. Create tasks that declare `required_capabilities` matching the agent's capabilities.

### Bridging both systems (advanced)
If you need `MultiAgentOrchestrator`'s capability routing inside an `AgentOrchestrator` pipeline, call `MultiAgentOrchestrator.execute_task()` from within a custom `BaseAgent.run()` implementation. This is an intentional escape hatch — no automatic wiring exists.
