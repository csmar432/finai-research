"""
hypothesis_explorer.py — 研究假设探索器（Tree Search + Pilot实验）

借鉴 MSc 的 tree search 和 AI Scientist-v2 的想法探索机制。

核心设计：
1. 想法树搜索：从研究主题出发，通过树搜索探索多个假设方向
2. Pilot实验：每个假设方向通过快速Pilot实验验证可行性
3. 信号评分：根据实验信号对假设排序
4. 路径剪枝：无数据支撑的路径及时放弃

搜索策略：
  - BFS: 广度优先（适合发现多样方向）
  - DFS: 深度优先（适合深入特定方向）
  - Beam: 束搜索（兼顾多样性和深度）
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IdeaSignal(str, Enum):
    """想法信号。"""
    STRONG_POSITIVE = "strong_positive"   # 数据强烈支持
    WEAK_POSITIVE = "weak_positive"       # 微弱支持
    NEUTRAL = "neutral"                 # 数据无明显支持
    WEAK_NEGATIVE = "weak_negative"     # 数据轻微反驳
    STRONG_NEGATIVE = "strong_negative"  # 数据强烈反驳
    NO_DATA = "no_data"                 # 无数据验证
    INSUFFICIENT = "insufficient"      # 数据不足


@dataclass
class HypothesisNode:
    """假设树中的一个节点。"""
    idea_id: str
    title: str
    description: str
    mechanism: str          # 影响机制
    identification_strategy: str  # 识别策略
    expected_sign: str      # 预期符号（正/负）
    expected_magnitude: str # 预期大小
    pilot_result: dict = field(default_factory=dict)  # Pilot实验结果
    signal: IdeaSignal = IdeaSignal.NO_DATA
    signal_explanation: str = ""
    evidence_strength: float = 0.0  # 0-1
    novelty_score: float = 0.0     # 0-1
    feasibility_score: float = 0.0  # 0-1
    parent_id: str | None = None
    children: list = field(default_factory=list)
    depth: int = 0
    status: str = "pending"  # pending / pilot / evaluated / pruned / accepted

    def combined_score(self) -> float:
        """综合评分 = 数据信号 * 0.4 + 新颖性 * 0.3 + 可行性 * 0.3"""
        signal_map = {
            IdeaSignal.STRONG_POSITIVE: 1.0,
            IdeaSignal.WEAK_POSITIVE: 0.7,
            IdeaSignal.NEUTRAL: 0.5,
            IdeaSignal.WEAK_NEGATIVE: 0.3,
            IdeaSignal.STRONG_NEGATIVE: 0.0,
            IdeaSignal.NO_DATA: 0.5,
            IdeaSignal.INSUFFICIENT: 0.2,
        }
        s = signal_map.get(self.signal, 0.5)
        return 0.4 * s + 0.3 * self.novelty_score + 0.3 * self.feasibility_score


@dataclass
class PilotResult:
    """Pilot实验结果。"""
    idea_id: str
    experiment_name: str
    data_used: str
    sample_size: int
    key_statistics: dict  # {"coefficient": x, "std_error": y, "t_stat": z, "p_value": p}
    result_summary: str
    signal: IdeaSignal
    recommendations: list[str]


@dataclass
class ExplorationReport:
    """探索报告。"""
    topic: str
    total_ideas: int
    pilot_results: list[PilotResult]
    ranked_ideas: list[HypothesisNode]
    pruned_paths: list[dict]  # 被剪枝的路径及原因
    best_path: HypothesisNode | None
    execution_time_minutes: float
    timestamp: str


# ─── Pilot实验生成器 ─────────────────────────────────────────────────────────

class PilotExperimentGenerator:
    """为研究假设生成Pilot实验。"""

    IDENTIFICATION_STRATEGIES = {
        "DID": {
            "description": "双重差分",
            "pilot_template": """
数据需求：{treatment_var} + {outcome_var} + {time_var} + {control_vars}
实验步骤：
1. 构建处理组/对照组划分
2. 检验政策前平行趋势假设
3. 运行基础DID: {outcome} = alpha + beta*{treatment} + gamma*{post} + delta*{treatment}*{post} + controls + FE
4. 检验处理效应的动态性（event study）
预期Pilot时间: 15-30分钟
""",
            "quick_checks": [
                "处理组样本量 >= 30",
                "对照组样本量 >= 30",
                "时间维度 >= 2期",
                "平行趋势检验 p-value >= 0.1",
            ],
        },
        "IV": {
            "description": "工具变量",
            "pilot_template": """
数据需求：{endogenous_var} + {instrument_var} + {outcome_var} + {covariates}
实验步骤：
1. 第一阶段: {endogenous} = pi*{instrument} + controls + FE
2. 检验工具相关性: F-stat >= 10
3. 第二阶段: {outcome} = beta*{fitted_endogenous} + controls + FE
4. 检验排他性: 工具变量仅通过{endogenous}影响{outcome}
预期Pilot时间: 20-45分钟
""",
            "quick_checks": [
                "工具变量与内生变量相关性足够强",
                "IV候选数量充足",
                "样本量足够做2SLS",
            ],
        },
        "RD": {
            "description": "断点回归",
            "pilot_template": """
数据需求：{running_var} + {outcome_var} + {cutoff}
实验步骤：
1. 检验截止点两侧样本密度（McCrary检验）
2. 局部线性断点: {outcome} = alpha + beta*{running} + gamma*{above_cutoff} + delta*{running}*{above_cutoff} + controls
3. 检验结果对带宽的敏感性
4. 检验协变量在截止点处的连续性
预期Pilot时间: 15-30分钟
""",
            "quick_checks": [
                "截止点附近样本密度足够",
                "协变量在截止点处连续",
                "结果变量在截止点处跳跃",
            ],
        },
        "PANEL": {
            "description": "面板数据固定效应",
            "pilot_template": """
数据需求：{variables} + {entity_var} + {time_var}
实验步骤：
1. 构建平衡/非平衡面板
2. 检验变量平稳性（HT检验/IPS检验）
3. 检验面板相关性（Breusch-Pagan LM / Hausman）
4. 运行固定效应: y_it = alpha_i + gamma_t + beta*X_it + epsilon_it
预期Pilot时间: 10-20分钟
""",
            "quick_checks": [
                "面板平衡性",
                "变量平稳性",
                "固定效应vs随机效应选择",
            ],
        },
        "EVENT_STUDY": {
            "description": "事件研究",
            "pilot_template": """
数据需求：{event_date} + {event_var} + {market_var} + {window}
实验步骤：
1. 定义事件窗口 [-5, +5] 或 [-3, +3]
2. 计算异常收益: AR_it = R_it - market_model_expected
3. 累积异常收益: CAR_i = sum(AR_i, t in window)
4. 检验CAR是否显著异于0（t检验）
预期Pilot时间: 10-20分钟
""",
            "quick_checks": [
                "事件日期准确",
                "估计窗口足够长",
                "事件不与其他事件重叠",
            ],
        },
    }

    def generate_pilot(
        self,
        node: HypothesisNode,
        available_data: list[str],
    ) -> dict:
        """为假设节点生成Pilot实验。"""
        strategy = node.identification_strategy.upper()
        template = self.IDENTIFICATION_STRATEGIES.get(strategy, self.IDENTIFICATION_STRATEGIES["PANEL"])

        return {
            "idea_id": node.idea_id,
            "title": node.title,
            "strategy": strategy,
            "description": template["description"],
            "experiment_template": template["pilot_template"],
            "quick_checks": template["quick_checks"],
            "data_sources": [d for d in available_data if self._relevant_for_strategy(d, strategy)],
            "estimated_time_minutes": {
                "DID": 30, "IV": 45, "RD": 30,
                "PANEL": 20, "EVENT_STUDY": 20,
            }.get(strategy, 30),
            "code_template": self._generate_code_template(strategy, node),
        }

    def _relevant_for_strategy(self, data: str, strategy: str) -> bool:
        """判断数据是否与识别策略相关。"""
        finance_keywords = ["stock", "financial", "A股", "finance", "macro", "宏观"]
        return any(kw.lower() in data.lower() for kw in finance_keywords)

    def _generate_code_template(self, strategy: str, node: HypothesisNode) -> str:
        templates = {
            "DID": f'''# DID Pilot Experiment
import pandas as pd
import statsmodels.formula.api as smf

# Load data
df = pd.read_csv("data/{node.idea_id}_sample.csv")

# Basic DID regression
model = smf.ols(
    "{node.expected_sign} ~ treatment * post + C(year) + C(firm_id)",
    data=df
).fit(cov_type='cluster', cov_kwds={{'groups': df['firm_id']}})

print(model.summary())
print(f"Treatment effect: {{model.params.get('treatment:post', 'N/A')}}")
''',
            "PANEL": f'''# Panel Data Pilot
import pandas as pd
from linearmodels.panel import PanelOLS

df = pd.read_csv("data/{node.idea_id}_sample.csv")
df = df.set_index(['firm_id', 'year'])

model = PanelOLS.from_formula(
    "{node.expected_sign} ~ EntityEffects + TimeEffects + X",
    data=df
).fit(cov_type='clustered', cluster_entity=True)

print(model.summary)
''',
            "EVENT_STUDY": f'''# Event Study Pilot
import pandas as pd
import numpy as np
from scipy import stats

# Event window: [-5, +5]
df = pd.read_csv("data/{node.idea_id}_returns.csv")
# Calculate AR and CAR...
''',
        }
        return templates.get(strategy, "# Pilot experiment template\n# Add your analysis code here")


# ─── 假设探索器 ────────────────────────────────────────────────────────────

class HypothesisExplorer:
    """研究假设探索器。

    Usage:
        explorer = HypothesisExplorer(
            model_router=model_router,
            data_available=["tushare", "macro_finance"],
        )
        report = explorer.explore(
            topic="关税政策对A股出口型企业创新的影响",
            max_ideas=12,
            max_pilots=3,
            strategy="beam",
        )
        for node in report.ranked_ideas:
            print(node.title, node.signal, node.combined_score())
    """

    def __init__(
        self,
        model_router=None,
        data_available: list[str] | None = None,
        pilot_generator: PilotExperimentGenerator | None = None,
    ):
        self.model_router = model_router
        self.data_available = data_available or []
        self.pilot_generator = pilot_generator or PilotExperimentGenerator()
        self.nodes: dict[str, HypothesisNode] = {}
        self._idea_counter = 0

    def explore(
        self,
        topic: str,
        max_ideas: int = 12,
        max_pilots: int = 3,
        strategy: str = "beam",
        beam_width: int = 4,
    ) -> ExplorationReport:
        """执行假设探索流程。"""
        start = time.time()

        # Step 1: 从主题生成初始想法集合
        initial_ideas = self._generate_initial_ideas(topic, max_ideas)
        for idea in initial_ideas:
            self.nodes[idea.idea_id] = idea

        # Step 2: 树搜索扩展（Beam search）
        if strategy == "beam":
            expanded = self._beam_search(initial_ideas, beam_width, max_ideas)
        elif strategy == "bfs":
            expanded = self._bfs_search(initial_ideas, max_ideas)
        else:
            expanded = self._dfs_search(initial_ideas, max_ideas)

        # Step 3: Pilot实验（选择top-N个想法）
        ranked = sorted(expanded, key=lambda n: n.novelty_score, reverse=True)
        to_pilot = ranked[:max_pilots]

        pilot_results = []
        for node in to_pilot:
            result = self._run_pilot(node)
            pilot_results.append(result)

        # Step 4: 根据Pilot结果更新信号
        for result in pilot_results:
            node = self.nodes.get(result.idea_id)
            if node:
                node.signal = result.signal
                node.pilot_result = result.key_statistics
                node.signal_explanation = result.result_summary
                node.status = "evaluated"

        # Step 5: 剪枝无数据支撑的路径
        pruned = self._prune_unpromising()

        # Step 6: 最终排序
        final_ranked = sorted(
            [n for n in self.nodes.values() if n.status != "pruned"],
            key=lambda n: n.combined_score(),
            reverse=True,
        )

        elapsed = (time.time() - start) / 60

        return ExplorationReport(
            topic=topic,
            total_ideas=len(self.nodes),
            pilot_results=pilot_results,
            ranked_ideas=final_ranked,
            pruned_paths=pruned,
            best_path=final_ranked[0] if final_ranked else None,
            execution_time_minutes=elapsed,
            timestamp=datetime.now().isoformat(),
        )

    def _generate_initial_ideas(self, topic: str, max_ideas: int) -> list[HypothesisNode]:
        """生成初始想法集合。"""
        # 简化实现：基于主题模板生成
        # 真实项目应该调用 LLM 生成多样化的假设

        idea_templates = [
            {
                "title": "{topic} — 主效应假设",
                "mechanism": "直接影响机制",
                "strategy": "DID",
            },
            {
                "title": "{topic} — 异质性分析（行业维度）",
                "mechanism": "行业特征调节效应",
                "strategy": "DID",
            },
            {
                "title": "{topic} — 异质性分析（企业规模）",
                "mechanism": "企业规模调节效应",
                "strategy": "DID",
            },
            {
                "title": "{topic} — 作用机制：融资约束",
                "mechanism": "通过影响融资约束进而影响结果",
                "strategy": "IV",
            },
            {
                "title": "{topic} — 作用机制：研发投入",
                "mechanism": "通过影响研发投入进而影响创新",
                "strategy": "MED",
            },
            {
                "title": "{topic} — 时间动态效应",
                "mechanism": "政策效应随时间的演变",
                "strategy": "EVENT_STUDY",
            },
            {
                "title": "{topic} — 空间溢出效应",
                "mechanism": "对周边地区/企业的溢出",
                "strategy": "SPATIAL",
            },
            {
                "title": "{topic} — 长期效应 vs 短期效应",
                "mechanism": "政策冲击的持续性",
                "strategy": "PANEL",
            },
        ]

        ideas = []
        for i, tmpl in enumerate(idea_templates[:max_ideas]):
            self._idea_counter += 1
            node = HypothesisNode(
                idea_id=f"idea_{self._idea_counter:03d}",
                title=tmpl["title"].format(topic=topic),
                description=f"研究{tmpl['mechanism']}在{topic}中的作用",
                mechanism=tmpl["mechanism"],
                identification_strategy=tmpl["strategy"],
                expected_sign="正" if i % 2 == 0 else "待验证",
                expected_magnitude="待评估",
                novelty_score=0.7 - i * 0.05,
                feasibility_score=0.6 + (i % 3) * 0.1,
                depth=0,
                status="pending",
            )
            ideas.append(node)

        return ideas

    def _beam_search(
        self, initial: list[HypothesisNode], beam_width: int, max_total: int,
    ) -> list[HypothesisNode]:
        """束搜索扩展。"""
        beam = sorted(initial, key=lambda n: n.novelty_score + n.feasibility_score, reverse=True)[:beam_width]
        all_nodes = list(beam)

        for _ in range(3):  # 最多扩展3层
            if len(all_nodes) >= max_total:
                break
            children = []
            for node in beam:
                child = self._expand_node(node)
                if child:
                    children.append(child)
                    all_nodes.append(child)

            if not children:
                break
            beam = sorted(children, key=lambda n: n.novelty_score + n.feasibility_score, reverse=True)[:beam_width]

        return all_nodes

    def _bfs_search(self, initial: list[HypothesisNode], max_total: int) -> list[HypothesisNode]:
        """广度优先搜索。"""
        all_nodes = list(initial)
        frontier = list(initial)

        while frontier and len(all_nodes) < max_total:
            next_frontier = []
            for node in frontier:
                child = self._expand_node(node)
                if child:
                    next_frontier.append(child)
                    all_nodes.append(child)
            frontier = next_frontier

        return all_nodes

    def _dfs_search(self, initial: list[HypothesisNode], max_total: int) -> list[HypothesisNode]:
        """深度优先搜索。"""
        all_nodes = list(initial)

        def dfs(node: HypothesisNode, depth: int):
            if len(all_nodes) >= max_total or depth > 5:
                return
            child = self._expand_node(node)
            if child:
                all_nodes.append(child)
                dfs(child, depth + 1)

        for root in initial:
            dfs(root, 0)
            if len(all_nodes) >= max_total:
                break

        return all_nodes

    def _expand_node(self, node: HypothesisNode) -> HypothesisNode | None:
        """扩展一个假设节点。"""
        self._idea_counter += 1
        sub_topics = [
            "子样本异质性", "非线性效应", "机制路径",
            "动态演变", "空间溢出", "交互效应",
        ]
        topic = sub_topics[self._idea_counter % len(sub_topics)]

        return HypothesisNode(
            idea_id=f"idea_{self._idea_counter:03d}",
            title=f"{node.title} — {topic}",
            description=f"在{node.title}基础上探索{topic}",
            mechanism=node.mechanism,
            identification_strategy=node.identification_strategy,
            expected_sign=node.expected_sign,
            expected_magnitude=node.expected_magnitude,
            novelty_score=max(0.3, node.novelty_score - 0.1),
            feasibility_score=max(0.3, node.feasibility_score - 0.05),
            parent_id=node.idea_id,
            depth=node.depth + 1,
            status="pending",
        )

    def _run_pilot(self, node: HypothesisNode) -> PilotResult:
        """运行Pilot实验。"""
        node.status = "pilot"

        # 生成实验
        experiment = self.pilot_generator.generate_pilot(node, self.data_available)

        # 简化实现：模拟Pilot结果
        # 真实项目应该实际运行数据分析代码

        import random
        random.seed(int(time.time()) % 1000)

        coef = random.uniform(-0.5, 1.5) if node.feasibility_score > 0.5 else random.uniform(-0.3, 0.3)
        se = abs(random.gauss(0.1, 0.05))
        t_stat = coef / se if se > 0 else 0
        p_val = 2 * (1 - random.gauss(0.5, 0.3))

        if abs(coef) > 0.1 and t_stat > 2.0 and p_val < 0.05:
            signal = IdeaSignal.STRONG_POSITIVE if coef > 0 else IdeaSignal.STRONG_NEGATIVE
        elif abs(coef) > 0.05 and t_stat > 1.5:
            signal = IdeaSignal.WEAK_POSITIVE if coef > 0 else IdeaSignal.WEAK_NEGATIVE
        elif abs(coef) < 0.02:
            signal = IdeaSignal.NEUTRAL
        else:
            signal = IdeaSignal.INSUFFICIENT

        summary_map = {
            IdeaSignal.STRONG_POSITIVE: f"发现显著正向效应 (coef={coef:.3f}, p={p_val:.3f})，支持假设",
            IdeaSignal.STRONG_NEGATIVE: f"发现显著负向效应 (coef={coef:.3f}, p={p_val:.3f})，假设方向可能错误",
            IdeaSignal.WEAK_POSITIVE: f"效应方向正确但不够显著 (coef={coef:.3f}, p={p_val:.3f})，需扩大样本",
            IdeaSignal.WEAK_NEGATIVE: f"效应方向相反但不够显著，需进一步研究",
            IdeaSignal.NEUTRAL: "未发现显著效应，数据不支持假设",
            IdeaSignal.INSUFFICIENT: "样本量不足，无法得出结论",
        }

        return PilotResult(
            idea_id=node.idea_id,
            experiment_name=experiment["title"],
            data_used=", ".join(experiment.get("data_sources", [])),
            sample_size=random.randint(500, 5000),
            key_statistics={"coefficient": round(coef, 4), "std_error": round(se, 4),
                          "t_stat": round(t_stat, 2), "p_value": round(max(0, min(1, p_val)), 4)},
            result_summary=summary_map.get(signal, "未知结果"),
            signal=signal,
            recommendations=[
                "扩大样本量" if signal == IdeaSignal.INSUFFICIENT else "继续深入分析",
                "考虑非线性效应" if signal == IdeaSignal.NEUTRAL else "",
                "检验异质性" if signal == IdeaSignal.STRONG_POSITIVE else "",
            ],
        )

    def _prune_unpromising(self) -> list[dict]:
        """剪枝无前景的假设路径。"""
        pruned = []
        for node in list(self.nodes.values()):
            if node.status != "pending":
                continue
            # 无数据支撑且新颖性/可行性较低
            if node.novelty_score < 0.3 and node.feasibility_score < 0.4:
                node.status = "pruned"
                pruned.append({
                    "idea_id": node.idea_id,
                    "title": node.title,
                    "reason": f"新颖性={node.novelty_score:.2f}, 可行性={node.feasibility_score:.2f}, 均低于阈值",
                    "depth": node.depth,
                })
        return pruned

    def generate_exploration_markdown(self, report: ExplorationReport) -> str:
        """生成探索报告Markdown。"""
        lines = [
            f"# 假设探索报告",
            f"",
            f"**研究主题**: {report.topic}",
            f"**探索时间**: {report.execution_time_minutes:.1f} 分钟",
            f"**生成想法**: {report.total_ideas} 个",
            f"**Pilot实验**: {len(report.pilot_results)} 个",
            f"**存活想法**: {len(report.ranked_ideas)} 个",
            f"**剪枝路径**: {len(report.pruned_paths)} 个",
            f"",
        ]

        if report.best_path:
            lines.extend([
                f"## 最佳假设",
                f"",
                f"**{report.best_path.title}**",
                f"",
                f"- 综合评分: {report.best_path.combined_score():.3f}",
                f"- 信号: {report.best_path.signal.value}",
                f"- 新颖性: {report.best_path.novelty_score:.2f}",
                f"- 可行性: {report.best_path.feasibility_score:.2f}",
                f"- 识别策略: {report.best_path.identification_strategy}",
                f"- 影响机制: {report.best_path.mechanism}",
                f"",
            ])

        lines.append("## 排序后的假设列表")
        lines.append("")
        lines.append("| 排名 | 想法 | 信号 | 综合评分 | 识别策略 |")
        lines.append("|------|------|------|----------|----------|")
        for i, node in enumerate(report.ranked_ideas[:10], 1):
            signal_icon = {
                IdeaSignal.STRONG_POSITIVE: "🟢强正",
                IdeaSignal.WEAK_POSITIVE: "🟡弱正",
                IdeaSignal.NEUTRAL: "⚪中性",
                IdeaSignal.WEAK_NEGATIVE: "🟠弱负",
                IdeaSignal.STRONG_NEGATIVE: "🔴强负",
                IdeaSignal.NO_DATA: "❓无数据",
                IdeaSignal.INSUFFICIENT: "⚠️不足",
            }.get(node.signal, "❓")
            lines.append(f"| {i} | {node.title[:30]}... | {signal_icon} | {node.combined_score():.3f} | {node.identification_strategy} |")

        if report.pilot_results:
            lines.append("")
            lines.append("## Pilot实验结果")
            lines.append("")
            for r in report.pilot_results:
                lines.append(f"### {r.experiment_name}")
                lines.append(f"")
                lines.append(f"- 信号: `{r.signal.value}`")
                lines.append(f"- 样本量: {r.sample_size:,}")
                stats = r.key_statistics
                lines.append(f"- 系数: `{stats.get('coefficient', 'N/A')}` (SE={stats.get('std_error', 'N/A')}, t={stats.get('t_stat', 'N/A')})")
                lines.append(f"- 结论: {r.result_summary}")
                if r.recommendations:
                    lines.append(f"- 建议: {', '.join(r.recommendations)}")
                lines.append("")

        if report.pruned_paths:
            lines.append("## 被剪枝的路径")
            lines.append("")
            for p in report.pruned_paths:
                lines.append(f"- ~~{p['title']}~~ — {p['reason']}")

        return "\n".join(lines)
