"""可视化唤起入口 — fin-viz-launcher.

用户可以通过自然语言选择图表类型，系统自动生成最佳可视化方案。

唤起方式:
    1. 命令行: python scripts/fin-viz-launcher.py
    2. Agent Skill: fin-viz-launch
    3. Dashboard: 侧边栏 "图表生成" 按钮

交互流程:
    用户输入查询 → 自然语言解析 → 推荐图表类型 → 用户确认 →
    调用 ChartPipeline 或 AdvancedChartFactory → 预览 → 导出
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ─── Chart Type Registry ───────────────────────────────────────────────────────


@dataclass
class ChartTypeRecommendation:
    name: str
    name_cn: str
    score: float          # 0-1 match score
    description: str
    examples: list[str]
    best_for: list[str]
    factory_method: str    # which AdvancedChartFactory method to use
    pipeline_query: str   # natural language query for ChartPipeline


CHART_REGISTRY: list[ChartTypeRecommendation] = [
    ChartTypeRecommendation(
        name="event_study",
        name_cn="事件研究图",
        score=0.0,
        description="展示政策/事件前后时间维度的效应变化，用于平行趋势检验",
        examples=["DID事件研究", "政策效应时序", "干预前后对比"],
        best_for=["DID", "事件分析", "时间序列"],
        factory_method="custom",
        pipeline_query="绘制事件研究图，展示政策实施前后各期的回归系数及95%置信区间",
    ),
    ChartTypeRecommendation(
        name="forest",
        name_cn="森林图",
        score=0.0,
        description="展示多个回归模型的系数估计值与置信区间",
        examples=["DID系数对比", "稳健性检验", "异质性分析"],
        best_for=["回归分析", "系数对比", "meta分析"],
        factory_method="custom",
        pipeline_query="绘制森林图，展示多个回归模型的DID系数及95%置信区间",
    ),
    ChartTypeRecommendation(
        name="sankey",
        name_cn="桑基图",
        score=0.0,
        description="展示流量从一个状态到另一个状态的流向与比例",
        examples=["资金流向", "碳配额流动", "能源流向"],
        best_for=["流量分析", "经济结构", "产业转移"],
        factory_method="sankey",
        pipeline_query="绘制桑基图，展示资金/资源/要素在各部门间的流动",
    ),
    ChartTypeRecommendation(
        name="funnel",
        name_cn="漏斗图",
        score=0.0,
        description="展示多阶段转化率",
        examples=["企业筛选漏斗", "IPO审核", "项目审批"],
        best_for=["转化分析", "漏斗", "筛选"],
        factory_method="funnel",
        pipeline_query="绘制漏斗图，展示企业/项目在各阶段的转化率",
    ),
    ChartTypeRecommendation(
        name="alluvial",
        name_cn="冲积图",
        score=0.0,
        description="展示分类在多个维度间的变化与流动",
        examples=["行业-地区流动", "企业所有制变化", "职业流动"],
        best_for=["分类变化", "动态分类", "多维度流动"],
        factory_method="alluvial",
        pipeline_query="绘制冲积图，展示分类变量在不同维度间的变化流向",
    ),
    ChartTypeRecommendation(
        name="ridgeline",
        name_cn="山脊图",
        score=0.0,
        description="展示多个时间段的分布变化（Joy Plot）",
        examples=["收入分布演变", "股价波动分布", "气温分布变化"],
        best_for=["分布时序", "密度估计", "比较分析"],
        factory_method="ridgeline",
        pipeline_query="绘制山脊图，展示多个时间段的分布密度变化",
    ),
    ChartTypeRecommendation(
        name="heterogeneity_bar",
        name_cn="异质性条形图",
        score=0.0,
        description="分组回归系数的对比柱状图",
        examples=["所有制异质性", "行业异质性", "地区异质性"],
        best_for=["异质性分析", "分组回归", "系数对比"],
        factory_method="custom",
        pipeline_query="绘制异质性条形图，展示不同分组的回归系数对比",
    ),
    ChartTypeRecommendation(
        name="heatmap",
        name_cn="热力图",
        score=0.0,
        description="矩阵数据的颜色编码可视化",
        examples=["相关性矩阵", "超参数敏感性", "行业关联"],
        best_for=["相关性", "矩阵", "双维度"],
        factory_method="custom",
        pipeline_query="绘制热力图，展示相关性矩阵或敏感性分析结果",
    ),
    ChartTypeRecommendation(
        name="ensemble_ribbon",
        name_cn="集成预测区间图",
        score=0.0,
        description="展示多个模型的预测不确定性范围",
        examples=["预测区间", "模型集成", "不确定性量化"],
        best_for=["预测", "集成学习", "置信区间"],
        factory_method="ensemble_ribbon",
        pipeline_query="绘制集成预测区间图，展示预测值的中位数和95%置信区间",
    ),
    ChartTypeRecommendation(
        name="waffle",
        name_cn="华夫图",
        score=0.0,
        description="用方块表示类别比例",
        examples=["市场份额", "投票比例", "资产配置"],
        best_for=["比例", "构成", "份额"],
        factory_method="waffle",
        pipeline_query="绘制华夫图，展示类别构成的占比",
    ),
    ChartTypeRecommendation(
        name="scatter_regression",
        name_cn="回归散点图",
        score=0.0,
        description="带回归线、置信区间的散点图",
        examples=["Y-X关系", "OLS拟合", "残差分析"],
        best_for=["相关分析", "拟合", "回归"],
        factory_method="custom",
        pipeline_query="绘制带回归线的散点图，展示变量间的关系",
    ),
    ChartTypeRecommendation(
        name="consort",
        name_cn="CONSORT流程图",
        score=0.0,
        description="临床试验受试者筛选与分组流程（CONSORT 2010 标准）",
        examples=["RCT流程", "样本筛选", "分组随机"],
        best_for=["临床试验", "随机对照", "样本流程"],
        factory_method="consort",
        pipeline_query="绘制CONSORT流程图，展示临床试验受试者筛选与分组流程",
    ),
]


# ─── Query Intent Classifier ────────────────────────────────────────────────


class IntentClassifier:
    """
    将用户的自然语言查询映射到最佳图表类型。

    使用关键词匹配 + LLM 辅助解析。
    """

    KEYWORD_MAP: dict[str, list[str]] = {
        "event_study": ["事件研究", "event study", "平行趋势", "动态效应", "did", "双重差分", "政策效应时序", "relative time"],
        "forest": ["森林图", "forest plot", "系数对比", "coefficient", "回归系数", "稳健性", "异质性"],
        "sankey": ["桑基", "sankey", "流量", "流向", "流动", "资金流", "碳配额", "能源流", "flow"],
        "funnel": ["漏斗", "funnel", "转化", "转化率", "筛选", "漏斗图", "conversion"],
        "alluvial": ["冲积", "alluvial", "变化", "流向变化", "分类变化", "transition", "动态分类"],
        "ridgeline": ["山脊", "ridgeline", "分布演变", "密度时序", "joy plot", "分布变化", "分布时序"],
        "heterogeneity_bar": ["异质性", "heterogeneity", "分组对比", "分组回归", "所有制", "行业异质", "地区异质"],
        "heatmap": ["热力", "heatmap", "相关矩阵", "相关性", "敏感", "sensitivity", "correlation matrix"],
        "ensemble_ribbon": ["预测区间", "ensemble", "不确定性", "置信区间", "prediction interval", "forecast"],
        "waffle": ["华夫", "waffle", "比例", "份额", "构成", "composition"],
        "scatter_regression": ["散点", "scatter", "回归线", "拟合", "regression line"],
        "consort": ["consort", "临床试验", "RCT", "随机对照", "样本筛选"],
    }

    def __init__(self):
        self._score_cache: dict[str, list[ChartTypeRecommendation]] = {}

    def classify(self, query: str) -> list[ChartTypeRecommendation]:
        """将查询分类，返回排序后的图表推荐列表。"""
        q_lower = query.lower()

        for rec in CHART_REGISTRY:
            score = 0.0

            # Keyword matching
            keywords = self.KEYWORD_MAP.get(rec.name, [])
            for kw in keywords:
                if kw.lower() in q_lower:
                    score += 0.3
                    # Exact match bonus
                    if kw.lower() == q_lower.strip():
                        score += 0.2

            # Example matching
            for ex in rec.examples:
                if ex.lower() in q_lower:
                    score += 0.2

            # best_for matching
            for bf in rec.best_for:
                if bf.lower() in q_lower:
                    score += 0.15

            rec.score = min(score, 1.0)

        # Sort descending by score
        return sorted(CHART_REGISTRY, key=lambda r: r.score, reverse=True)

    def top_k(self, query: str, k: int = 3) -> list[ChartTypeRecommendation]:
        """返回 Top-K 推荐。"""
        return self.classify(query)[:k]


# ─── Interactive Launcher ───────────────────────────────────────────────────────


@dataclass
class VizSession:
    query: str
    recommended: list[ChartTypeRecommendation]
    selected: ChartTypeRecommendation | None = None
    data_description: str = ""
    target_journal: str = ""
    output_path: Path | None = None
    status: str = "pending"  # pending | generating | done | error


class VizLauncher:
    """
    可视化唤起器 — 交互式图表生成入口。

    流程：
    1. 解析用户查询 → 推荐图表类型（Top-3）
    2. 用户选择确认（或输入自定义需求）
    3. 调用 AdvancedChartFactory（快速）或 ChartPipeline（LLM 驱动）
    4. 预览并导出
    """

    def __init__(self):
        self.classifier = IntentClassifier()
        self.sessions: dict[str, VizSession] = {}

    def parse(self, query: str) -> VizSession:
        """解析查询，返回推荐会话。"""
        top = self.classifier.top_k(query, k=3)
        session = VizSession(query=query, recommended=top)
        self.sessions[session_id(query)] = session
        return session

    def select(self, session_id: str, choice: int | str) -> None:
        """用户选择图表类型。"""
        session = self.sessions.get(session_id)
        if not session:
            return

        if isinstance(choice, int) and 0 < choice <= len(session.recommended):
            session.selected = session.recommended[choice - 1]
        else:
            # Custom — find by name
            for rec in session.recommended:
                if rec.name == choice or rec.name_cn == choice:
                    session.selected = rec
                    break

        if session.selected:
            session.status = "ready"

    def generate_quick(
        self,
        session: VizSession,
        data: dict | None = None,
    ) -> Path | None:
        """
        使用 AdvancedChartFactory 快速生成（无需 LLM）。
        """
        from scripts.core.chart_factory import AdvancedChartFactory

        if not session.selected:
            return None

        factory = AdvancedChartFactory()
        method = session.selected.factory_method
        output_name = f"{session.selected.name}_{session.query[:20].replace(' ', '_')}"

        if method == "sankey":
            return factory.sankey(
                nodes=["A", "B", "C", "D"],
                links=[(0, 1, 100), (1, 2, 80), (1, 3, 40), (2, 3, 60)],
                title=session.query,
                output_name=output_name,
            )
        elif method == "funnel":
            return factory.funnel(
                stages=["浏览", "注册", "付费", "复购"],
                values=[1000, 200, 50, 15],
                title=session.query,
                output_name=output_name,
            )
        elif method == "ridgeline":
            import numpy as np
            times = ["2020", "2021", "2022", "2023", "2024"]
            dists = [np.random.normal(0.5 + i * 0.05, 0.15, 100).tolist() for i in range(5)]
            return factory.ridgeline(
                time_labels=times,
                distributions=dists,
                title=session.query,
                output_name=output_name,
            )
        elif method == "waffle":
            cats = [("处理组", 35), ("对照组", 65)]
            return factory.waffle(
                categories=cats,
                title=session.query,
                output_name=output_name,
            )
        elif method == "ensemble_ribbon":
            import numpy as np
            x = list(range(50))
            median = [0.5 + 0.02 * i + np.random.normal(0, 0.05) for i in x]
            lower = [m - 0.15 for m in median]
            upper = [m + 0.15 for m in median]
            return factory.ensemble_ribbon(
                x=x, y_median=median, y_lower=lower, y_upper=upper,
                title=session.query,
                output_name=output_name,
            )
        elif method == "consort":
            return factory.consort(
                groups={},
                title=session.query,
                output_name=output_name,
            )

        return None

    def generate_llm(
        self,
        session: VizSession,
    ) -> "asyncio.Task":
        """
        使用 ChartPipeline（CoDA 风格）生成。
        返回 asyncio Task。
        """
        from scripts.core.chart_pipeline import ChartPipeline, PipelineConfig

        if not session.selected:
            raise ValueError("No chart type selected")

        config = PipelineConfig(
            quality_threshold=0.75,
            max_iterations=3,
            output_dir=Path("output/figures"),
            force_journal_style=session.target_journal,
        )
        pipeline = ChartPipeline(config)

        return asyncio.create_task(
            pipeline.run(
                query=session.selected.pipeline_query,
                data_description=session.data_description,
                target_journal=session.target_journal,
            )
        )

    def format_recommendations(self, session: VizSession) -> str:
        """格式化推荐结果为 Markdown 显示。"""
        lines = [f"\n{'='*50}", f"  图表推荐 — \"{session.query}\"", f"{'='*50}\n"]

        for i, rec in enumerate(session.recommended, 1):
            score_bar = "█" * int(rec.score * 10) + "░" * (10 - int(rec.score * 10))
            lines.append(f"  {i}. **{rec.name_cn}** ({rec.name})")
            lines.append(f"     匹配度: {score_bar} {rec.score:.0%}")
            lines.append(f"     {rec.description}")
            lines.append(f"     适用: {', '.join(rec.best_for[:3])}")
            lines.append("")

        lines.append("  请选择图表类型编号（1-3），或输入具体描述：")
        return "\n".join(lines)


def session_id(query: str) -> str:
    import hashlib
    return hashlib.md5(query.encode()).hexdigest()[:8]


# ─── Skill Integration ────────────────────────────────────────────────────────


async def run_viz_launcher(
    query: str,
    mode: str = "quick",     # "quick" | "llm" | "interactive"
    data: dict | None = None,
    target_journal: str = "",
) -> dict[str, Any]:
    """
    Skill 入口函数。

    用法（Agent Skill）:
        Skill: fin-viz-launch "[研究描述]"

    或命令行:
        python scripts/fin-viz-launcher.py --query "绘制碳排放权交易对企业创新的影响系数森林图"
    """
    launcher = VizLauncher()
    session = launcher.parse(query)

    # Print recommendations
    print(launcher.format_recommendations(session))

    if mode == "quick":
        # Auto-select top recommendation
        if session.recommended:
            session.selected = session.recommended[0]
            path = launcher.generate_quick(session, data)
            return {
                "status": "done",
                "chart_type": session.selected.name,
                "chart_type_cn": session.selected.name_cn,
                "output_path": str(path) if path else None,
                "query": query,
            }

    elif mode == "llm":
        if session.recommended:
            session.selected = session.recommended[0]
        task = launcher.generate_llm(session)
        return {
            "status": "generating",
            "task": task,
            "chart_type": session.selected.name if session.selected else None,
            "query": query,
        }

    return {"status": "pending", "recommendations": [
        {"name": r.name, "name_cn": r.name_cn, "score": r.score, "description": r.description}
        for r in session.recommended
    ]}


# ─── CLI Entry Point ───────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="可视化唤起器 — fin-viz-launcher")
    parser.add_argument("--query", "-q", required=True, help="图表描述")
    parser.add_argument("--mode", "-m", choices=["quick", "llm"],
                       default="quick", help="生成模式")
    parser.add_argument("--journal", "-j", default="", help="目标期刊")
    parser.add_argument("--list", "-l", action="store_true",
                       help="列出所有支持的图表类型")
    args = parser.parse_args()

    if args.list:
        print("\n支持的图表类型：\n")
        for rec in CHART_REGISTRY:
            print(f"  {rec.name_cn:12s} ({rec.name:20s}) — {rec.description}")
        print()
        return

    launcher = VizLauncher()
    session = launcher.parse(args.query)
    print(launcher.format_recommendations(session))

    # Auto-run quick mode
    if args.mode == "quick":
        session.target_journal = args.journal
        path = launcher.generate_quick(session)
        if path:
            print(f"\n✅ 图表已生成: {path}")
        else:
            print("\n⚠️  快速生成模式未覆盖此类型，请使用 --mode llm")


if __name__ == "__main__":
    main()
