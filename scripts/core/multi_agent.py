#!/usr/bin/env python3
"""
多Agent协同编排器
=================
提供多Agent任务分配、协同执行、结果聚合等功能

功能：
1. Agent注册 - 动态注册Agent
2. 任务分发 - 智能任务分配
3. 协同执行 - 并行/串行执行
4. 结果聚合 - 多Agent结果合并
"""

from __future__ import annotations

__all__ = [
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
]

import asyncio
import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from scripts.core.agents.base import AgentCancelledError, CancellationToken

# ═══════════════════════════════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════════════════════════════

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ExecutionMode(Enum):
    """执行模式"""
    SEQUENTIAL = "sequential"    # 串行执行
    PARALLEL = "parallel"        # 并行执行
    PIPELINE = "pipeline"        # 流水线执行

@dataclass
class Agent:
    """Agent定义"""
    agent_id: str
    name: str
    role: str                    # 角色描述
    capabilities: list[str]      # 能力列表
    system_prompt: str           # 系统提示词
    max_concurrent: int = 1     # 最大并发任务数

@dataclass
class Task:
    """任务定义"""
    task_id: str
    name: str
    description: str
    required_capabilities: list[str]
    input_data: dict
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: str | None = None
    result: Any | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

@dataclass
class Workflow:
    """工作流定义"""
    workflow_id: str
    name: str
    description: str
    agents: list[Agent]
    tasks: list[Task]
    execution_mode: ExecutionMode
    dependencies: dict[str, list[str]]  # task_id -> [dependent_task_ids]


# ═══════════════════════════════════════════════════════════════════════════
# Agent执行器接口
# ═══════════════════════════════════════════════════════════════════════════

class AgentExecutor(Protocol):
    """Agent执行器协议"""

    def execute(self, agent: Agent, task: Task) -> Any:
        """执行任务"""
        ...

    async def async_execute(self, agent: Agent, task: Task) -> Any:
        """异步执行任务"""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# 默认Agent执行器
# ═══════════════════════════════════════════════════════════════════════════

class DefaultAgentExecutor:
    """默认Agent执行器"""

    def __init__(self, llm_provider: Callable = None):
        self.llm_provider = llm_provider

    def execute(self, agent: Agent, task: Task) -> Any:
        """执行任务"""
        # 构造prompt
        prompt = f"""
# {agent.name}
{agent.system_prompt}

# 任务
{task.description}

# 输入数据
{json.dumps(task.input_data, ensure_ascii=False, indent=2)}

# 输出要求
请根据上述信息和输入数据完成任务，并返回结果。
"""

        # 如果有LLM提供者，调用它
        if self.llm_provider:
            result = self.llm_provider(prompt, system=agent.system_prompt)
            return result

        # 否则返回模拟结果
        return {
            "agent_id": agent.agent_id,
            "task_id": task.task_id,
            "result": f"任务 '{task.name}' 已完成",
            "timestamp": time.time()
        }

    async def async_execute(self, agent: Agent, task: Task) -> Any:
        """异步执行任务"""
        # T2 audit 2026-07-12: use get_running_loop (avoids DeprecationWarning on 3.10+)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.execute, agent, task)


# ═══════════════════════════════════════════════════════════════════════════
# 多Agent编排器
# ═══════════════════════════════════════════════════════════════════════════

class MultiAgentOrchestrator:
    """
    多Agent协同编排器

    支持的工作流模式：
    1. 串行执行 - 任务按顺序执行
    2. 并行执行 - 任务同时执行
    3. 流水线执行 - 任务按依赖关系执行
    """

    def __init__(self, executor: AgentExecutor = None):
        self.executor = executor or DefaultAgentExecutor()

        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, Task] = {}
        self._workflows: dict[str, Workflow] = {}
        self._results: dict[str, Any] = {}
        self._lock = threading.Lock()

        # Cancellation token registry: task_id -> CancellationToken
        self._active_tokens: dict[str, CancellationToken] = {}

        # 注册默认Agent
        self._register_default_agents()

    def _register_default_agents(self):
        """注册默认Agent"""
        # 研究设计Agent
        self.register_agent(Agent(
            agent_id="research_designer",
            name="研究设计专家",
            role="负责研究问题设计、假设提出、方法选择",
            capabilities=["research_design", "hypothesis", "methodology"],
            system_prompt="""你是一位资深研究设计专家，擅长：
1. 根据研究领域设计有价值的研究问题
2. 提出可检验的研究假设
3. 选择适当的实证研究方法
4. 确保研究设计的科学性和可行性"""
        ))

        # 文献综述Agent
        self.register_agent(Agent(
            agent_id="literature_reviewer",
            name="文献综述专家",
            role="负责文献检索、分析和综述撰写",
            capabilities=["literature_search", "analysis", "writing"],
            system_prompt="""你是一位专业文献综述专家，擅长：
1. 系统检索相关文献
2. 批判性分析文献
3. 撰写结构清晰的文献综述
4. 识别研究空白和创新点"""
        ))

        # 数据分析Agent
        self.register_agent(Agent(
            agent_id="data_analyst",
            name="数据分析专家",
            role="负责数据处理、统计分析、结果解读",
            capabilities=["data_processing", "statistics", "visualization"],
            system_prompt="""你是一位专业数据分析专家，擅长：
1. 数据清洗和预处理
2. 描述性统计和推断统计
3. 回归分析和假设检验
4. 数据可视化和结果解读"""
        ))

        # 论文写作Agent
        self.register_agent(Agent(
            agent_id="paper_writer",
            name="论文写作专家",
            role="负责论文撰写、修改和润色",
            capabilities=["academic_writing", "editing", "polishing"],
            system_prompt="""你是一位专业学术论文写作专家，擅长：
1. 撰写规范的学术论文
2. 逻辑清晰、论证严密
3. 语言精炼、表达准确
4. 格式规范、引用正确"""
        ))

        # 审核Agent
        self.register_agent(Agent(
            agent_id="reviewer",
            name="论文审核专家",
            role="负责论文质量审核、问题发现和修改建议",
            capabilities=["review", "quality_check", "feedback"],
            system_prompt="""你是一位资深论文审核专家，擅长：
1. 评估论文整体质量
2. 发现逻辑和论证问题
3. 提出建设性修改建议
4. 确保学术规范"""
        ))

    def register_agent(self, agent: Agent) -> bool:
        """注册Agent"""
        with self._lock:
            if agent.agent_id in self._agents:
                return False
            self._agents[agent.agent_id] = agent
            return True

    def unregister_agent(self, agent_id: str) -> bool:
        """注销Agent"""
        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
            return False

    def get_agent(self, agent_id: str) -> Agent | None:
        """获取Agent"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[Agent]:
        """列出所有Agent"""
        return list(self._agents.values())

    def find_best_agent(self, required_capabilities: list[str]) -> Agent | None:
        """找到最合适的Agent"""
        best_agent = None
        max_match = 0

        for agent in self._agents.values():
            match_count = sum(1 for cap in required_capabilities if cap in agent.capabilities)
            if match_count > max_match:
                max_match = match_count
                best_agent = agent

        return best_agent

    def create_task(
        self,
        name: str,
        description: str,
        required_capabilities: list[str],
        input_data: dict = None
    ) -> Task:
        """创建任务"""
        task = Task(
            task_id=str(uuid.uuid4()),
            name=name,
            description=description,
            required_capabilities=required_capabilities,
            input_data=input_data or {}
        )

        with self._lock:
            self._tasks[task.task_id] = task

        return task

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """分配任务给Agent"""
        with self._lock:
            if task_id not in self._tasks or agent_id not in self._agents:
                return False

            task = self._tasks[task_id]
            task.assigned_agent_id = agent_id
            return True

    def execute_task(self, task_id: str) -> Any:
        """执行单个任务"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 找到合适的Agent
        if not task.assigned_agent_id:
            agent = self.find_best_agent(task.required_capabilities)
            if not agent:
                raise ValueError(f"没有找到合适的Agent: {task.required_capabilities}")
            task.assigned_agent_id = agent.agent_id
        else:
            agent = self._agents.get(task.assigned_agent_id)
            if not agent:
                raise ValueError(f"Agent不存在: {task.assigned_agent_id}")

        # 更新任务状态
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # Create and track cancellation token
        token = CancellationToken()
        self._active_tokens[task.task_id] = token

        try:
            # Execute task
            result = self.executor.execute(agent, task)
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()

            # 保存结果
            self._results[task_id] = result

            return result

        except AgentCancelledError:
            task.status = TaskStatus.CANCELLED
            task.error = "Task cancelled via CancellationToken"
            task.completed_at = time.time()
            raise
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            raise
        finally:
            self._active_tokens.pop(task.task_id, None)

    async def async_execute_task(self, task_id: str) -> Any:
        """异步执行单个任务"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 找到合适的Agent
        if not task.assigned_agent_id:
            agent = self.find_best_agent(task.required_capabilities)
            if not agent:
                raise ValueError("没有找到合适的Agent")
            task.assigned_agent_id = agent.agent_id
        else:
            agent = self._agents.get(task.assigned_agent_id)
            if not agent:
                raise ValueError("Agent不存在")

        # 更新任务状态
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # Create and track cancellation token
        token = CancellationToken()
        self._active_tokens[task.task_id] = token

        try:
            # 异步执行任务
            result = await self.executor.async_execute(agent, task)
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()

            self._results[task_id] = result
            return result

        except AgentCancelledError:
            task.status = TaskStatus.CANCELLED
            task.error = "Task cancelled via CancellationToken"
            task.completed_at = time.time()
            raise
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            raise
        finally:
            self._active_tokens.pop(task.task_id, None)

    def execute_parallel(self, task_ids: list[str]) -> dict[str, Any]:
        """并行执行多个任务"""
        results = {}
        errors = {}

        # 创建异步任务
        async def run_all():
            tasks = [self.async_execute_task(tid) for tid in task_ids]
            return await asyncio.gather(*tasks, return_exceptions=True)

        # 运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            raw_results = loop.run_until_complete(run_all())
        finally:
            loop.close()

        # 整理结果
        for tid, result in zip(task_ids, raw_results):
            if isinstance(result, Exception):
                errors[tid] = str(result)
            else:
                results[tid] = result

        return {"results": results, "errors": errors}

    def execute_sequential(self, task_ids: list[str]) -> dict[str, Any]:
        """串行执行多个任务"""
        results = {}
        errors = {}

        for task_id in task_ids:
            try:
                result = self.execute_task(task_id)
                results[task_id] = result
            except Exception as e:
                errors[task_id] = str(e)

        return {"results": results, "errors": errors}

    def execute_pipeline(self, task_ids: list[str], dependencies: dict[str, list[str]]) -> dict[str, Any]:
        """流水线执行（按依赖关系）"""
        results = {}
        errors = {}
        completed = set()

        remaining = list(task_ids)

        while remaining:
            # 找出可以执行的任务（依赖都已完成）
            ready = []
            for task_id in remaining:
                deps = dependencies.get(task_id, [])
                if all(d in completed for d in deps):
                    ready.append(task_id)

            if not ready:
                # 没有可执行的任务，可能是依赖循环
                for task_id in remaining:
                    errors[task_id] = "依赖循环或无法满足的依赖"
                break

            # 并行执行就绪的任务
            exec_results = self.execute_parallel(ready)
            results.update(exec_results["results"])
            errors.update(exec_results["errors"])

            # 更新状态
            for task_id in ready:
                if task_id not in errors:
                    completed.add(task_id)
                remaining.remove(task_id)

        return {"results": results, "errors": errors}

    def get_task(self, task_id: str) -> Task | None:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态"""
        task = self._tasks.get(task_id)
        return task.status if task else None

    def get_results(self) -> dict[str, Any]:
        """获取所有结果"""
        return dict(self._results)

    def get_result(self, task_id: str) -> Any | None:
        """获取单个任务结果"""
        return self._results.get(task_id)

    def cancel_task(self, task_id: str, reason: str = "") -> bool:
        """
        Cancel a running task.

        Uses CancellationToken for cooperative cancellation. The task must be
        currently executing inside execute_task() or async_execute_task().

        Parameters
        ----------
        task_id : str
            ID of the task to cancel.
        reason : str
            Human-readable cancellation reason.

        Returns
        -------
        bool
            True if cancellation was requested, False if the task is not active.
        """
        if task_id in self._active_tokens:
            self._active_tokens[task_id].cancel(reason)
            return True
        return False

    def is_task_active(self, task_id: str) -> bool:
        """Return True if the task is currently running."""
        return task_id in self._active_tokens


# ═══════════════════════════════════════════════════════════════════════════
# 预定义工作流模板
# ═══════════════════════════════════════════════════════════════════════════

class WorkflowTemplates:
    """工作流模板"""

    @staticmethod
    def paper_writing_workflow(orchestrator: MultiAgentOrchestrator) -> list[Task]:
        """论文写作工作流"""
        tasks = []

        # 1. 研究设计
        task1 = orchestrator.create_task(
            name="研究设计",
            description="设计研究问题、假设和方法",
            required_capabilities=["research_design", "hypothesis", "methodology"],
            input_data={"topic": "待定"}
        )
        tasks.append(task1)

        # 2. 文献综述
        task2 = orchestrator.create_task(
            name="文献综述",
            description="检索和分析相关文献",
            required_capabilities=["literature_search", "analysis"],
            input_data={"topic": "待定"}
        )
        tasks.append(task2)

        # 3. 数据分析
        task3 = orchestrator.create_task(
            name="数据分析",
            description="处理数据并进行统计分析",
            required_capabilities=["data_processing", "statistics"],
            input_data={"data": "待定"}
        )
        tasks.append(task3)

        # 4. 论文写作
        task4 = orchestrator.create_task(
            name="论文写作",
            description="撰写完整论文",
            required_capabilities=["academic_writing"],
            input_data={}
        )
        tasks.append(task4)

        # 5. 论文审核
        task5 = orchestrator.create_task(
            name="论文审核",
            description="审核论文质量",
            required_capabilities=["review", "quality_check"],
            input_data={}
        )
        tasks.append(task5)

        return tasks


# ═══════════════════════════════════════════════════════════════════════════
# Factory — call create_default() to get a pre-configured instance.
# Do NOT import the module-level orchestrator variable directly; it is
# kept only for backward compatibility and will be removed in a future version.
# ═══════════════════════════════════════════════════════════════════════════

def create_default() -> MultiAgentOrchestrator:
    """Create and return a new pre-configured MultiAgentOrchestrator instance."""
    instance = MultiAgentOrchestrator()
    return instance
