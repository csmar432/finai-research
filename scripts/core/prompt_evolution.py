"""Prompt 自动演化 — 基于 Self-Questioning 的 prompt 改进引擎.

功能：
  1. 收集历史执行结果，识别低质量输出的模式
  2. 使用 LLM 分析 prompt 中的歧义/不完整/过度约束
  3. 自动生成改进的 prompt 变体
  4. 评估改进效果，迭代优化

参考 EvoAgentX Self-Questioning 设计。

Usage:
    evolver = PromptEvolver(gateway)
    evolver.record_result("literature_agent", "生成文献摘要", output="...", quality=0.6)
    evolver.record_result("literature_agent", "生成文献摘要", output="...", quality=0.9)
    improved = evolver.evolve_prompt("literature_agent", "生成文献摘要")
    print(improved)
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "PromptEvolutionRecord",
    "PromptEvolver",
]

logger = logging.getLogger(__name__)


@dataclass
class PromptEvolutionRecord:
    """单次 prompt 执行记录。"""

    timestamp: float
    agent_name: str
    task_type: str
    prompt: str
    output: str
    quality: float  # 0-1
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "output": self.output[:500],  # 截断
            "quality": self.quality,
            "context": self.context,
        }


class PromptEvolver:
    """
    Prompt 自动演化引擎。

    核心机制：
      1. 记录：收集每次 prompt 执行的质量
      2. 分析：识别低质量输出的 prompt 模式
      3. 演化：使用 LLM 生成改进的 prompt
      4. 验证：在下一轮执行中验证改进效果

    Usage
    -----
        evolver = PromptEvolver(gateway)

        # 记录执行
        evolver.record_result("literature_agent", "生成摘要", prompt, output, 0.7)

        # 演化
        improved = evolver.evolve_prompt("literature_agent", "生成摘要")
        print(f"改进后 prompt:\n{improved}")

        # 批量演化所有低质量 task
        evolver.evolve_all(min_quality=0.6)
    """

    def __init__(
        self,
        gateway=None,
        history_dir: str = ".cache/prompt_evolution",
        min_history: int = 3,
    ):
        self.gateway = gateway
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.min_history = min_history
        self._records: list[PromptEvolutionRecord] = []
        self._evolved_prompts: dict[str, str] = {}  # (agent, task) -> evolved_prompt
        self._load_history()

    # ── Record ────────────────────────────────────────────────────────────────

    def record_result(
        self,
        agent_name: str,
        task_type: str,
        prompt: str,
        output: str,
        quality: float,
        context: dict | None = None,
    ):
        """
        记录一次 prompt 执行结果。

        Parameters
        ----------
        agent_name : str
            Agent 名称。
        task_type : str
            任务类型（用于分组）。
        prompt : str
            使用的 prompt。
        output : str
            模型输出。
        quality : float
            质量评分 0-1。
        context : dict | None
            额外上下文。
        """
        record = PromptEvolutionRecord(
            timestamp=time.time(),
            agent_name=agent_name,
            task_type=task_type,
            prompt=prompt,
            output=output,
            quality=quality,
            context=context or {},
        )
        self._records.append(record)
        self._save_record(record)

    def _save_record(self, record: PromptEvolutionRecord):
        """持久化单条记录。"""
        path = self.history_dir / f"{record.agent_name}_{record.task_type}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def _load_history(self):
        """加载历史记录。"""
        for path in self.history_dir.glob("*.jsonl"):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        data = json.loads(line)
                        self._records.append(PromptEvolutionRecord(
                            timestamp=data["timestamp"],
                            agent_name=data["agent_name"],
                            task_type=data["task_type"],
                            prompt=data["prompt"],
                            output=data["output"],
                            quality=data["quality"],
                            context=data.get("context", {}),
                        ))
            except Exception as exc:
                logger.warning(f"[PromptEvolver] Failed to load {path}: {exc}")

    # ── Analyze ────────────────────────────────────────────────────────────────

    def get_task_records(
        self,
        agent_name: str,
        task_type: str,
    ) -> list[PromptEvolutionRecord]:
        """获取某 agent/task 的所有历史记录。"""
        return [
            r for r in self._records
            if r.agent_name == agent_name and r.task_type == task_type
        ]

    def get_avg_quality(
        self,
        agent_name: str,
        task_type: str,
    ) -> float:
        """计算某 agent/task 的平均质量。"""
        records = self.get_task_records(agent_name, task_type)
        if not records:
            return 0.5
        return sum(r.quality for r in records) / len(records)

    def analyze_failures(
        self,
        agent_name: str,
        task_type: str,
        threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        分析低质量输出的共同模式。

        Returns
        -------
        dict
            含问题模式和改进建议。
        """
        records = self.get_task_records(agent_name, task_type)
        low_quality = [r for r in records if r.quality < threshold]

        if len(low_quality) < self.min_history:
            return {
                "sufficient_data": False,
                "reason": f"仅 {len(low_quality)} 条低质量记录（需要 {self.min_history} 条）",
            }

        # 构建分析 prompt
        low_prompts = "\n---\n".join(r.prompt[:500] for r in low_quality[:5])
        low_outputs = "\n---\n".join(r.output[:300] for r in low_quality[:5])

        analysis_prompt = f"""你是 AI Agent Prompt 优化专家。请分析以下低质量输出对应的 prompt，识别问题模式。

## 低质量 Prompt 样例
{low_prompts}

## 对应输出
{low_outputs}

## 分析任务
请从以下维度识别问题：
1. **歧义性**：prompt 中存在多种解释的表述
2. **不完整性**：缺少关键约束或上下文
3. **过度约束**：限制条件过多导致无法满足
4. **格式不清晰**：输出格式要求不明确
5. **角色不明确**：未定义 Agent 应扮演的角色
6. **示例不足**：缺少 few-shot 示例

请以 JSON 格式输出：
{{
  "pattern": "主要问题模式（歧义/不完整/过度约束/格式不清晰/角色不明确/示例不足）",
  "frequency": "出现频率（high/medium/low）",
  "description": "问题具体描述",
  "examples": ["具体例子1", "具体例子2"],
  "improvement_suggestions": ["改进建议1", "改进建议2"],
  "confidence": 0.0-1.0
}}"""

        if self.gateway is None:
            return {
                "sufficient_data": True,
                "pattern": "unknown",
                "reason": "No LLM gateway available",
            }

        try:
            response = self.gateway.generate(analysis_prompt, format_json=True, task_hint="prompt_analysis")
            text = response.response if hasattr(response, "response") else str(response)
            data = json.loads(text)
            return {
                "sufficient_data": True,
                "records_analyzed": len(low_quality),
                **data,
            }
        except Exception as exc:
            logger.warning(f"[PromptEvolver] Analysis failed: {exc}")
            return {
                "sufficient_data": True,
                "records_analyzed": len(low_quality),
                "error": str(exc),
            }

    # ── Evolve ────────────────────────────────────────────────────────────────

    def evolve_prompt(
        self,
        agent_name: str,
        task_type: str,
        base_prompt: str | None = None,
    ) -> str | None:
        """
        演化某 agent/task 的 prompt。

        Parameters
        ----------
        agent_name : str
            Agent 名称。
        task_type : str
            任务类型。
        base_prompt : str | None
            基准 prompt（如果不提供，从最新记录获取）。

        Returns
        -------
        str | None
            演化后的 prompt。
        """
        if self.gateway is None:
            logger.warning("[PromptEvolver] No LLM gateway — skipping evolution")
            return None

        records = self.get_task_records(agent_name, task_type)

        # 获取基准 prompt
        if base_prompt is None:
            if records:
                base_prompt = records[-1].prompt
            else:
                logger.warning(
                    f"[PromptEvolver] No records for {agent_name}/{task_type}"
                )
                return None

        # 获取问题分析
        analysis = self.analyze_failures(agent_name, task_type)

        evolution_prompt = f"""你是 AI Agent Prompt 优化专家。请根据以下问题分析，生成改进的 prompt。

## 基准 Prompt
{base_prompt}

## 问题分析
{json.dumps(analysis, ensure_ascii=False, indent=2)}

## 任务
基于问题分析，生成改进的 prompt。
要求：
1. 修复分析中发现的问题模式
2. 保持原 prompt 的核心意图
3. 使用更清晰、无歧义的语言
4. 添加必要的格式约束和示例
5. 明确 Agent 角色和输出格式

请直接输出改进后的完整 prompt（不要 JSON，不要解释）："""

        try:
            response = self.gateway.generate(
                evolution_prompt,
                task_hint="prompt_evolution",
            )
            evolved = response.response if hasattr(response, "response") else str(response)

            # 缓存演化结果
            key = f"{agent_name}:{task_type}"
            self._evolved_prompts[key] = evolved

            # 持久化
            self._save_evolved_prompt(agent_name, task_type, evolved, analysis)

            logger.info(f"[PromptEvolver] Evolved {agent_name}/{task_type}")
            return evolved

        except Exception as exc:
            logger.warning(f"[PromptEvolver] Evolution failed: {exc}")
            return None

    def _save_evolved_prompt(
        self,
        agent_name: str,
        task_type: str,
        evolved: str,
        analysis: dict,
    ):
        """持久化演化后的 prompt。"""
        path = self.history_dir / f"evolved_{agent_name}_{task_type}.json"
        data = {
            "agent_name": agent_name,
            "task_type": task_type,
            "evolved_prompt": evolved,
            "analysis": analysis,
            "timestamp": time.time(),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_evolved_prompt(
        self,
        agent_name: str,
        task_type: str,
    ) -> str | None:
        """获取已演化的 prompt。"""
        key = f"{agent_name}:{task_type}"
        if key in self._evolved_prompts:
            return self._evolved_prompts[key]

        # 尝试从文件加载
        path = self.history_dir / f"evolved_{agent_name}_{task_type}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._evolved_prompts[key] = data["evolved_prompt"]
                return data["evolved_prompt"]
            except Exception:
                pass
        return None

    def evolve_all(
        self,
        min_quality: float = 0.6,
        min_records: int = 3,
    ) -> dict[str, str | None]:
        """
        批量演化所有低于质量阈值的 agent/task。

        Returns
        -------
        dict[str, str | None]
            agent:task → 演化后的 prompt。
        """
        # 按 agent/task 分组
        task_map: dict[str, list[PromptEvolutionRecord]] = defaultdict(list)
        for r in self._records:
            key = f"{r.agent_name}:{r.task_type}"
            task_map[key].append(r)

        results = {}

        for key, records in task_map.items():
            avg_q = sum(r.quality for r in records) / len(records)
            if avg_q < min_quality and len(records) >= min_records:
                agent, task = key.split(":", 1)
                evolved = self.evolve_prompt(agent, task)
                results[key] = evolved
                logger.info(f"[PromptEvolver] Batch evolved {key}: {evolved is not None}")

        return results

    # ── Report ────────────────────────────────────────────────────────────────

    def get_report(self) -> dict[str, Any]:
        """生成演化报告。"""
        task_map: dict[str, list[PromptEvolutionRecord]] = defaultdict(list)
        for r in self._records:
            key = f"{r.agent_name}:{r.task_type}"
            task_map[key].append(r)

        task_stats = []
        for key, records in task_map.items():
            agent, task = key.split(":", 1)
            avg_q = sum(r.quality for r in records) / len(records)
            evolved = self.get_evolved_prompt(agent, task)
            task_stats.append({
                "agent": agent,
                "task": task,
                "record_count": len(records),
                "avg_quality": avg_q,
                "has_evolved": evolved is not None,
            })

        return {
            "total_records": len(self._records),
            "unique_tasks": len(task_map),
            "evolved_prompts": len(self._evolved_prompts),
            "task_stats": task_stats,
        }

    def print_report(self, file=None):
        """打印演化报告。"""
        report = self.get_report()
        print("=" * 60, file=file)
        print("  Prompt Evolution Report", file=file)
        print("=" * 60, file=file)
        print(f"  总记录数：{report['total_records']}", file=file)
        print(f"  唯一任务：{report['unique_tasks']}", file=file)
        print(f"  已演化 prompt：{report['evolved_prompts']}", file=file)
        print(file=file)

        print("  各任务质量：", file=file)
        for stat in report["task_stats"]:
            icon = "🔄" if stat["has_evolved"] else "  "
            q = stat["avg_quality"]
            bar = "█" * int(q * 10) + "░" * (10 - int(q * 10))
            print(
                f"  {icon} {stat['agent']}/{stat['task'][:20]:20s} "
                f"{bar} {q:.2f} ({stat['record_count']}条)",
                file=file,
            )

        print("=" * 60, file=file)
