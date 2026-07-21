"""
campaign_orchestrator.py — Campaign 编排器

借鉴 MSc 的 Campaign 系统，支持多阶段顺序研究链。

核心设计：
1. Campaign: 一个完整的研究项目，包含多个相关的研究阶段
2. Stage: 独立的研究阶段，有输入/输出/状态
3. 上下文传递：各阶段之间自动传递文献库、背景知识、已生成的数据
4. 依赖管理：自动解析阶段间的依赖关系
5. 进度持久化：每个阶段完成后保存状态，支持断点恢复
"""

from __future__ import annotations

__all__ = [
    "StageStatus",
    "Stage",
    "SharedContext",
    "Campaign",
    "CampaignTemplate",
    "CampaignOrchestrator",
]

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """阶段状态。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PAUSED = "paused"


@dataclass
class Stage:
    """研究阶段。"""
    name: str
    description: str
    skill_name: str           # 对应的 Skill 名称
    input_artifacts: list[str]  # 需要的输入产物
    output_artifacts: list[str]  # 生成的输出产物
    depends_on: list[str]     # 依赖的其他阶段名
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result: dict = field(default_factory=dict)  # 阶段输出结果
    metadata: dict = field(default_factory=dict)


@dataclass
class SharedContext:
    """跨阶段共享的上下文。"""
    # 文献
    literature_cache: dict = field(default_factory=dict)  # paper_id -> paper_meta
    citation_network: dict = field(default_factory=dict)
    # 数据
    acquired_data: dict = field(default_factory=dict)  # data_id -> path
    # 背景
    research_background: str = ""       # 研究背景（由初始阶段填充）
    topic: str = ""                   # 研究主题
    target_journal: str = ""          # 目标期刊
    # 配置
    flags: dict = field(default_factory=dict)
    # 预算
    token_budget: float = 100.0       # 剩余 token 预算（美元）
    time_budget_hours: float = 48.0  # 剩余时间预算

    def save(self, path: Path) -> None:
        """保存上下文到文件。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "literature_cache": self.literature_cache,
                "citation_network": self.citation_network,
                "acquired_data": self.acquired_data,
                "research_background": self.research_background,
                "topic": self.topic,
                "target_journal": self.target_journal,
                "flags": self.flags,
                "token_budget": self.token_budget,
                "time_budget_hours": self.time_budget_hours,
            }, f, ensure_ascii=False, indent=2)

    def load(self, path: Path) -> bool:
        """从文件加载上下文。"""
        if not path.exists():
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.literature_cache = data.get("literature_cache", {})
            self.citation_network = data.get("citation_network", {})
            self.acquired_data = data.get("acquired_data", {})
            self.research_background = data.get("research_background", "")
            self.topic = data.get("topic", "")
            self.target_journal = data.get("target_journal", "")
            self.flags = data.get("flags", {})
            self.token_budget = data.get("token_budget", 100.0)
            self.time_budget_hours = data.get("time_budget_hours", 48.0)
            return True
        except Exception as e:
            logger.warning(f"Failed to load shared context: {e}")
            return False


@dataclass
class Campaign:
    """研究 Campaign。"""
    campaign_id: str
    name: str
    description: str
    topic: str
    stages: list[Stage]
    shared_context: SharedContext = field(default_factory=SharedContext)
    output_dir: Path = field(default_factory=Path)
    status: str = "created"  # created / running / paused / completed / failed
    created_at: str = ""
    current_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "name": self.name,
            "topic": self.topic,
            "status": self.status,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
            "stages": [
                {"name": s.name, "status": s.status.value, "description": s.description}
                for s in self.stages
            ],
            "token_budget_remaining": self.shared_context.token_budget,
            "time_budget_remaining_hours": self.shared_context.time_budget_hours,
        }


# ─── Campaign 模板 ─────────────────────────────────────────────────────────

class CampaignTemplate:
    """预定义的 Campaign 模板。"""

    TEMPLATES: dict[str, list[dict]] = {
        "empirical_finance": [
            {
                "name": "background",
                "skill": "fin-lit-review",
                "description": "文献综述与研究背景",
                "input": [],
                "output": ["LIT_REVIEW.md", "research_background.md"],
                "depends": [],
            },
            {
                "name": "ideas",
                "skill": "fin-generate-idea",
                "description": "研究想法生成",
                "input": ["LIT_REVIEW.md"],
                "output": ["IDEA_REPORT.md", "IDEA_CANDIDATES.md"],
                "depends": ["background"],
            },
            {
                "name": "novelty",
                "skill": "fin-novelty-check",
                "description": "新颖性验证",
                "input": ["IDEA_CANDIDATES.md"],
                "output": ["NOVELTY_REPORT.md"],
                "depends": ["ideas"],
            },
            {
                "name": "design",
                "skill": "fin-experiment-design",
                "description": "实证方法设计",
                "input": ["NOVELTY_REPORT.md"],
                "output": ["REFINED_DESIGN.md", "VARIABLE_DEFINITIONS.md"],
                "depends": ["novelty"],
            },
            {
                "name": "data",
                "skill": "fin-data-acquisition",
                "description": "数据获取与实证",
                "input": ["REFINED_DESIGN.md"],
                "output": ["DATA_MANIFEST.md", "regression_results/"],
                "depends": ["design"],
            },
            {
                "name": "outline",
                "skill": "fin-paper-plan",
                "description": "论文大纲与图表计划",
                "input": ["DATA_MANIFEST.md"],
                "output": ["PAPER_OUTLINE.md", "FIGURE_PLAN.md", "TABLE_PLAN.md"],
                "depends": ["data"],
            },
            {
                "name": "writing",
                "skill": "fin-paper-draft",
                "description": "论文正文写作",
                "input": ["PAPER_OUTLINE.md", "DATA_MANIFEST.md"],
                "output": ["draft_v1/"],
                "depends": ["outline"],
            },
            {
                "name": "figures",
                "skill": "fin-paper-figure",
                "description": "图表生成",
                "input": ["FIGURE_PLAN.md"],
                "output": ["draft_v1/figures/"],
                "depends": ["writing"],
            },
            {
                "name": "review",
                "skill": "fin-review-loop",
                "description": "对抗性评审",
                "input": ["draft_v1/"],
                "output": ["REVIEW_REPORT.md"],
                "depends": ["writing", "figures"],
            },
            {
                "name": "compile",
                "skill": "fin-paper-convert",
                "description": "LaTeX编译",
                "input": ["draft_v1/"],
                "output": ["draft_v1/main.pdf"],
                "depends": ["review"],
            },
            {
                "name": "submit",
                "skill": "fin-submit-check",
                "description": "投稿前检查",
                "input": ["draft_v1/"],
                "output": ["SUBMIT_CHECK_REPORT.md"],
                "depends": ["compile"],
            },
        ],
        "idea_exploration": [
            {
                "name": "lit",
                "skill": "fin-lit-review",
                "description": "快速文献扫描",
                "input": [],
                "output": ["LIT_REVIEW.md"],
                "depends": [],
            },
            {
                "name": "ideas",
                "skill": "fin-generate-idea",
                "description": "多方向想法生成",
                "input": ["LIT_REVIEW.md"],
                "output": ["IDEA_REPORT.md"],
                "depends": ["lit"],
            },
            {
                "name": "novelty",
                "skill": "fin-novelty-check",
                "description": "新颖性快速验证",
                "input": ["IDEA_REPORT.md"],
                "output": ["NOVELTY_REPORT.md"],
                "depends": ["ideas"],
            },
            {
                "name": "design",
                "skill": "fin-experiment-design",
                "description": "最佳想法的实证设计",
                "input": ["NOVELTY_REPORT.md"],
                "output": ["REFINED_DESIGN.md"],
                "depends": ["novelty"],
            },
        ],
        "heterogeneity_deep_dive": [
            {
                "name": "base_analysis",
                "skill": "fin-data-acquisition",
                "description": "基准分析",
                "input": ["REFINED_DESIGN.md"],
                "output": ["base_results.md"],
                "depends": [],
            },
            {
                "name": "industry_het",
                "skill": "fin-data-acquisition",
                "description": "行业异质性",
                "input": ["REFINED_DESIGN.md"],
                "output": ["industry_het_results.md"],
                "depends": ["base_analysis"],
            },
            {
                "name": "size_het",
                "skill": "fin-data-acquisition",
                "description": "规模异质性",
                "input": ["REFINED_DESIGN.md"],
                "output": ["size_het_results.md"],
                "depends": ["base_analysis"],
            },
            {
                "name": "region_het",
                "skill": "fin-data-acquisition",
                "description": "地区异质性",
                "input": ["REFINED_DESIGN.md"],
                "output": ["region_het_results.md"],
                "depends": ["base_analysis"],
            },
            {
                "name": "synthesis",
                "skill": "fin-paper-draft",
                "description": "异质性分析综合写作",
                "input": ["base_results.md", "industry_het_results.md", "size_het_results.md", "region_het_results.md"],
                "output": ["heterogeneity_section.md"],
                "depends": ["industry_het", "size_het", "region_het"],
            },
        ],
    }

    @classmethod
    def get_template(cls, name: str) -> list[dict] | None:
        return cls.TEMPLATES.get(name)


# ─── Campaign 编排器 ────────────────────────────────────────────────────────

class CampaignOrchestrator:
    """Campaign 编排器。

    Usage:
        orch = CampaignOrchestrator(
            output_dir="output/campaigns/my_tariff_study",
            topic="关税政策对A股出口型企业创新的影响",
        )
        campaign = orch.create_campaign("empirical_finance")
        orch.run(campaign, auto_proceed=False)
    """

    def __init__(
        self,
        output_dir: str | Path = "output/campaigns",
        topic: str = "",
        target_journal: str = "",
    ):
        self.output_dir = Path(output_dir)
        self.topic = topic
        self.target_journal = target_journal

    def create_campaign(
        self,
        template_name: str,
        name: str | None = None,
        custom_stages: list[dict] | None = None,
    ) -> Campaign:
        """从模板创建 Campaign。"""
        import uuid

        stages_data = custom_stages or CampaignTemplate.get_template(template_name) or []
        stages = [
            Stage(
                name=s["name"],
                description=s["description"],
                skill_name=s["skill"],
                input_artifacts=s.get("input", []),
                output_artifacts=s.get("output", []),
                depends_on=s.get("depends", []),
            )
            for s in stages_data
        ]

        campaign_id = f"campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        campaign_dir = self.output_dir / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)

        context = SharedContext(
            topic=self.topic,
            target_journal=self.target_journal,
            flags={"auto_proceed": False, "human_checkpoint": True},
        )

        return Campaign(
            campaign_id=campaign_id,
            name=name or template_name,
            description=f"基于 {template_name} 模板的 Campaign",
            topic=self.topic,
            stages=stages,
            shared_context=context,
            output_dir=campaign_dir,
            created_at=datetime.now().isoformat(),
        )

    def save_campaign(self, campaign: Campaign) -> None:
        """保存 Campaign 状态。"""
        state_file = campaign.output_dir / "campaign_state.json"
        campaign.output_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "topic": campaign.topic,
            "status": campaign.status,
            "current_stage": campaign.current_stage,
            "completed_stages": campaign.completed_stages,
            "failed_stages": campaign.failed_stages,
            "stages": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "error": s.error,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                }
                for s in campaign.stages
            ],
            "created_at": campaign.created_at,
            "timestamp": datetime.now().isoformat(),
        }

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 保存共享上下文
        ctx_file = campaign.output_dir / "shared_context.json"
        campaign.shared_context.save(ctx_file)

    def load_campaign(self, campaign_id: str) -> Campaign | None:
        """加载 Campaign 状态。"""
        for cp_dir in self.output_dir.glob("campaign_*"):
            if cp_dir.name == campaign_id or campaign_id in cp_dir.name:
                state_file = cp_dir / "campaign_state.json"
                if not state_file.exists():
                    return None
                try:
                    with open(state_file, encoding="utf-8") as f:
                        data = json.load(f)
                    # 重建 Campaign（简化版）
                    return Campaign(
                        campaign_id=data["campaign_id"],
                        name=data["name"],
                        description="",
                        topic=data.get("topic", ""),
                        stages=[],
                        shared_context=SharedContext(),
                        output_dir=cp_dir,
                        status=data.get("status", "created"),
                        created_at=data.get("created_at", ""),
                        current_stage=data.get("current_stage"),
                        completed_stages=data.get("completed_stages", []),
                        failed_stages=data.get("failed_stages", []),
                    )
                except Exception as e:
                    logger.warning(f"Failed to load campaign {campaign_id}: {e}")
        return None

    def run(
        self,
        campaign: Campaign,
        *,
        auto_proceed: bool = False,
        max_parallel: int = 1,
        stage_filter: str | None = None,
    ) -> Campaign:
        """运行 Campaign。"""
        campaign.status = "running"
        self.save_campaign(campaign)

        # 按依赖顺序拓扑排序
        sorted_stages = self._topological_sort(campaign.stages)

        for stage in sorted_stages:
            # 过滤
            if stage_filter and stage.name != stage_filter:
                stage.status = StageStatus.SKIPPED
                continue

            # 检查依赖
            if not self._deps_satisfied(stage, campaign):
                stage.status = StageStatus.SKIPPED
                continue

            # 预算检查
            if campaign.shared_context.token_budget <= 0:
                logger.warning(f"Token budget exhausted, stopping at {stage.name}")
                campaign.status = "paused"
                break

            # 执行阶段
            campaign.current_stage = stage.name
            stage.status = StageStatus.RUNNING
            stage.started_at = datetime.now().isoformat()
            self.save_campaign(campaign)

            try:
                result = self._execute_stage(stage, campaign)
                stage.result = result
                stage.status = StageStatus.COMPLETED
                stage.completed_at = datetime.now().isoformat()
                campaign.completed_stages.append(stage.name)
            except Exception as e:
                stage.status = StageStatus.FAILED
                stage.error = str(e)
                stage.completed_at = datetime.now().isoformat()
                campaign.failed_stages.append(stage.name)
                logger.error(f"Stage {stage.name} failed: {e}")
                if not auto_proceed:
                    campaign.status = "paused"
                    break

            self.save_campaign(campaign)

        # 检查是否全部完成
        if not campaign.failed_stages:
            pending = [s for s in campaign.stages if s.status == StageStatus.PENDING]
            if not pending:
                campaign.status = "completed"

        return campaign

    def _execute_stage(self, stage: Stage, campaign: Campaign) -> dict:
        """执行单个阶段。"""
        logger.info(f"Executing stage: {stage.name} (skill: {stage.skill_name})")

        # 生成输出目录
        stage_dir = campaign.output_dir / stage.name
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 构建上下文字典（传递给 Skill）
        context = {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.name,
            "topic": campaign.topic,
            "target_journal": campaign.target_journal,
            "stage_name": stage.name,
            "stage_dir": str(stage_dir),
            "literature_cache": campaign.shared_context.literature_cache,
            "acquired_data": campaign.shared_context.acquired_data,
            "research_background": campaign.shared_context.research_background,
            "flags": campaign.shared_context.flags,
        }

        # 模拟 Skill 调用
        # 真实实现应该调用 Skill.execute() 或通过 Skill tool
        result = {
            "stage": stage.name,
            "skill": stage.skill_name,
            "output_dir": str(stage_dir),
            "artifacts": stage.output_artifacts,
            "context_passed": context,
            "status": "completed",
        }

        # 更新共享上下文
        if stage.name == "background" and "literature_cache" in result:
            campaign.shared_context.literature_cache.update(result.get("literature_cache", {}))

        return result

    def _topological_sort(self, stages: list[Stage]) -> list[Stage]:
        """拓扑排序（Kahn算法）。"""
        {s.name: s for s in stages}
        in_degree = {s.name: len(s.depends_on) for s in stages}
        queue = [s for s in stages if in_degree[s.name] == 0]
        sorted_list = []

        while queue:
            stage = queue.pop(0)
            sorted_list.append(stage)
            for s in stages:
                if stage.name in s.depends_on:
                    in_degree[s.name] -= 1
                    if in_degree[s.name] == 0:
                        queue.append(s)

        return sorted_list

    def _deps_satisfied(self, stage: Stage, campaign: Campaign) -> bool:
        """检查依赖阶段是否已满足。"""
        for dep in stage.depends_on:
            dep_stage = next((s for s in campaign.stages if s.name == dep), None)
            if not dep_stage or dep_stage.status != StageStatus.COMPLETED:
                return False
        return True

    def generate_campaign_report(self, campaign: Campaign) -> str:
        """生成 Campaign 报告。"""
        lines = [
            f"# Campaign 报告",
            f"",
            f"**Campaign ID**: {campaign.campaign_id}",
            f"**名称**: {campaign.name}",
            f"**主题**: {campaign.topic}",
            f"**状态**: {campaign.status}",
            f"**创建时间**: {campaign.created_at}",
            f"",
            f"## 阶段进度",
            f"",
            f"| 阶段 | 状态 | 依赖 |",
            f"|------|------|------|",
        ]

        for s in campaign.stages:
            status_icon = {
                StageStatus.COMPLETED: "✅",
                StageStatus.RUNNING: "🔄",
                StageStatus.PENDING: "⏳",
                StageStatus.FAILED: "❌",
                StageStatus.SKIPPED: "⏭️",
                StageStatus.PAUSED: "⏸️",
            }.get(s.status, "❓")
            lines.append(f"| {s.name} | {status_icon} {s.status.value} | {', '.join(s.depends_on) or '-'} |")

        lines.extend([
            f"",
            f"## 预算",
            f"",
            f"- Token 预算剩余: ${campaign.shared_context.token_budget:.2f}",
            f"- 时间预算剩余: {campaign.shared_context.time_budget_hours:.1f} 小时",
            f"",
            f"## 共享上下文",
            f"",
            f"- 文献缓存: {len(campaign.shared_context.literature_cache)} 篇",
            f"- 已获取数据: {len(campaign.shared_context.acquired_data)} 项",
            f"- 研究背景: {len(campaign.shared_context.research_background)} 字",
        ])

        return "\n".join(lines)
