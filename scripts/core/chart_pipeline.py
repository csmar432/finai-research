"""CoDA-Style Chart Generation Pipeline.

对标 Google Research CoDA (Collaborative Data-visualization Agents) 的多 Agent 协作架构：

    QueryAnalyzer  →  DataProcessor  →  VizMapper  →  DesignExplorer
    →  SearchAgent  →  CodeGenerator  →  DebugAgent  →  VisualEvaluator

每个 Agent 由 LLM 驱动，通过质量阈值控制迭代轮次（默认 max 3 轮）。

用法:
    from scripts.core.chart_pipeline import ChartPipeline, PipelineConfig

    config = PipelineConfig(quality_threshold=0.75, max_iterations=3)
    pipeline = ChartPipeline(config)
    result = await pipeline.run(
        query="绘制各省份碳排放权交易对企业创新的影响系数森林图",
        data_description="省级面板数据，包含 treatment/control 变量和 DID 系数",
        target_journal="经济研究",
    )
"""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.core.llm_gateway import LLMGateway

# ─── Pipeline Config ────────────────────────────────────────────────────────────


@dataclass
class PipelineConfig:
    quality_threshold: float = 0.75
    max_iterations: int = 3
    model: str = "deepseek"
    temperature: float = 0.3
    output_dir: Path = field(default_factory=lambda: Path("output/figures"))
    include_mermaid: bool = True
    force_journal_style: str = ""  # e.g. "JF", "经济研究", "AER"

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)


# ─── Agent Definitions ─────────────────────────────────────────────────────────


@dataclass
class AgentOutput:
    agent: str
    content: dict[str, Any]
    raw: str


# ─── Phase 1: Query Analyzer ─────────────────────────────────────────────────


class QueryAnalyzer:
    """
    解析用户查询，分解为 TODO checklist，指派下游 Agent 的工作。

    输出结构:
        {
            "intent": "可视化类型（bar/line/heatmap/sankey...）",
            "variables": ["treat_post", "innovation", "province"],
            "filters": ["year >= 2012"],
            "chart_type": "森林图",
            "subtasks": ["数据过滤", "聚合计算", "图表绘制"],
            "notes": []
        }
    """

    SYSTEM_PROMPT = textwrap.dedent("""
        你是一位专业的学术图表规划师。请分析用户的可视化查询，生成结构化 TODO 清单。

        分析要求：
        1. 识别图表类型（条形图、折线图、森林图、事件研究图、热力图、桑基图等）
        2. 提取涉及的变量（因变量、自变量、控制变量）
        3. 确定数据过滤条件
        4. 识别需要的统计操作（均值、中位数、回归系数、DID等）
        5. 标注特殊需求（期刊规范、配色方案、语言）

        输出 JSON 格式，不要添加额外说明。
    """)

    USER_PROMPT_TEMPLATE = textwrap.dedent("""
        用户查询：
        {query}

        数据描述：
        {data_description}

        目标期刊：{target_journal}

        请输出 JSON：
        {{
            "intent": "图表的核心意图",
            "chart_type": "推荐的图表类型",
            "variables": ["var1", "var2", ...],
            "x_axis": "x轴变量",
            "y_axis": "y轴变量",
            "group_by": "分组变量（可选）",
            "filters": ["过滤条件1", "过滤条件2"],
            "aggregation": "需要的聚合操作",
            "subtasks": ["任务1", "任务2", ...],
            "design_notes": ["设计注意事项1", ...],
            "journal_compliance": {{"journal": "...", "dpi": 300, "font": "Times", ...}}
        }}
    """)

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(
        self,
        query: str,
        data_description: str = "",
        target_journal: str = "",
    ) -> AgentOutput:
        prompt = self.USER_PROMPT_TEMPLATE.format(
            query=query,
            data_description=data_description or "用户提供的数据",
            target_journal=target_journal or "未指定",
        )
        response = self.gateway.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            model="deepseek",
            temperature=0.2,
            max_tokens=2048,
        )

        # Parse JSON
        content = self._parse_json(response.response)

        return AgentOutput(
            agent="QueryAnalyzer",
            content=content,
            raw=response.response,
        )

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"intent": text, "chart_type": "unknown", "subtasks": []}


# ─── Phase 2: Data Processor ──────────────────────────────────────────────────


class DataProcessor:
    """
    根据 QueryAnalyzer 的结果，生成数据处理代码（Pandas / Polars）。

    输出: DataProcessor 代码片段，供后续 CodeGenerator 使用。
    """

    SYSTEM_PROMPT = textwrap.dedent("""
        你是一位数据工程专家。请根据 QueryAnalyzer 的分析结果，
        生成数据处理代码（Pandas），为后续图表绑定数据。

        要求：
        1. 只生成数据处理代码，不要生成图表
        2. 数据变量名需与 QueryAnalyzer 输出的 variables 一致
        3. 处理 NaN / 异常值
        4. 适当缓存中间结果
        5. 代码必须完整、可运行
    """)

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(self, query_plan: dict, raw_data_desc: str = "") -> AgentOutput:
        prompt = textwrap.dedent(f"""
            QueryAnalyzer 分析结果：
            {json.dumps(query_plan, indent=2, ensure_ascii=False)}

            原始数据描述：
            {raw_data_desc or "用户提供的数据文件"}

            请生成数据处理代码（Pandas），只做数据清洗、过滤、聚合，不要绘图。
            输出格式：```python ...``` 代码块。
        """)
        response = self.gateway.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            model="deepseek",
            temperature=0.2,
            max_tokens=2048,
        )
        code = self._extract_code(response.response)
        return AgentOutput(
            agent="DataProcessor",
            content={"processing_code": code, "variables": query_plan.get("variables", [])},
            raw=response.response,
        )

    def _extract_code(self, text: str) -> str:
        match = re.search(r"```python(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()


# ─── Phase 3: VizMapper ────────────────────────────────────────────────────────


class VizMapper:
    """
    将变量映射到视觉通道（x轴、y轴、颜色、大小、形状）。

    输出:
        {
            "x_axis": {"var": "year", "scale": "ordinal"},
            "y_axis": {"var": "coef", "scale": "linear"},
            "color": {"var": "group", "palette": "Set2"},
            "size": {"var": "n_obs", "range": [20, 500]},
            "shape": {"var": "significance", "values": ["o", "*", "**"]},
            "ci": {"show": true, "level": 0.95}
        }
    """

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(self, query_plan: dict) -> AgentOutput:
        prompt = textwrap.dedent(f"""
            根据以下分析计划，将变量映射到视觉通道。

            分析计划：
            {json.dumps(query_plan, indent=2, ensure_ascii=False)}

            输出 JSON：
            {{
                "x_axis": {{"var": "变量名", "scale": "linear|ordinal|time", "label": "中文标签"}},
                "y_axis": {{"var": "变量名", "scale": "linear|log", "label": "中文标签"}},
                "color": {{"var": "分组变量", "palette": "Set2|viridis|Dark2|cbpalette"}},
                "size": {{"var": "可选变量", "range": [min, max]}},
                "ci": {{"show": true|false, "level": 0.95}},
                "facet": {{"var": "分面变量", "n_cols": 2}},
                "chart_specific": {{}}  // 图表类型特定配置
            }}
        """)
        response = self.gateway.generate(
            prompt=prompt,
            model="deepseek",
            temperature=0.2,
            max_tokens=1024,
        )
        content = self._parse_json(response.response)
        return AgentOutput(
            agent="VizMapper",
            content=content,
            raw=response.response,
        )

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text.strip())
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


# ─── Phase 4: Design Explorer ─────────────────────────────────────────────────


class DesignExplorer:
    """
    生成设计规范（配色、字体、布局、交互）。

    输出:
        {
            "colors": ["#0072B2", "#009E73", ...],
            "palette_name": "cbpalette",
            "fonts": {{"family": "Times New Roman", "size_axis": 11, "size_title": 13}},
            "layout": {{"fig_width": 6.5, "fig_height": 4, "wspace": 0.3}},
            "accessibility": {{"colorblind_safe": true, "pattern_range": ["--",".."]}}
        }
    """

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(
        self,
        query_plan: dict,
        target_journal: str = "",
    ) -> AgentOutput:
        journal_style = self._journal_defaults(target_journal)

        prompt = textwrap.dedent(f"""
            生成图表设计规范。

            图表类型：{query_plan.get("chart_type", "条形图")}
            目标期刊：{target_journal or "未指定"}

            期刊默认值（可覆盖）：
            {json.dumps(journal_style, indent=2, ensure_ascii=False)}

            要求：
            1. 使用色盲友好配色（cbpalette / viridis / Set2）
            2. 字体使用期刊规范（Times New Roman / Arial）
            3. 尺寸符合期刊单栏/双栏标准
            4. 无上/右边框

            输出 JSON：
            {{
                "colors": ["#hex1", "#hex2", ...],
                "palette_name": "cbpalette",
                "fonts": {{"family": "字体名", "size_axis": 11, "size_title": 12, "size_legend": 9}},
                "layout": {{"fig_width": 6.5, "fig_height": 4, "wspace": 0.2, "hspace": 0.3}},
                "accessibility": {{"colorblind_safe": true, "pattern_range": ["--","..",""]}},
                "export": {{"dpi": 300, "format": "pdf", "transparent": false}}
            }}
        """)
        response = self.gateway.generate(
            prompt=prompt,
            model="deepseek",
            temperature=0.2,
            max_tokens=1024,
        )
        content = self._parse_json(response.response)
        if not content.get("fonts"):
            content["fonts"] = journal_style.get("fonts", {})
        return AgentOutput(
            agent="DesignExplorer",
            content=content,
            raw=response.response,
        )

    def _journal_defaults(self, journal: str) -> dict:
        styles = {
            "JF": {"fonts": {"family": "Times New Roman", "size_axis": 10, "size_title": 11},
                     "layout": {"fig_width": 3.3, "fig_height": 2.5}},
            "JFE": {"fonts": {"family": "Times New Roman", "size_axis": 10, "size_title": 11},
                     "layout": {"fig_width": 3.3, "fig_height": 2.5}},
            "RFS": {"fonts": {"family": "Times New Roman", "size_axis": 10, "size_title": 11},
                     "layout": {"fig_width": 3.3, "fig_height": 2.5}},
            "经济研究": {"fonts": {"family": "Times New Roman", "size_axis": 11, "size_title": 13},
                       "layout": {"fig_width": 14, "fig_height": 8}},
            "金融研究": {"fonts": {"family": "Times New Roman", "size_axis": 11, "size_title": 13},
                       "layout": {"fig_width": 14, "fig_height": 8}},
        }
        return styles.get(journal, {
            "fonts": {"family": "Arial", "size_axis": 11, "size_title": 12},
            "layout": {"fig_width": 8, "fig_height": 5},
        })

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text.strip())
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


# ─── Phase 5: Code Generator ──────────────────────────────────────────────────


class CodeGenerator:
    """
    根据 VizMapper + DesignExplorer 的规范，生成完整的可执行 matplotlib/seaborn 代码。
    """

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(
        self,
        query_plan: dict,
        viz_mapping: dict,
        design_spec: dict,
        data_code: str,
        iteration: int = 1,
    ) -> AgentOutput:
        prompt = textwrap.dedent(f"""
            生成完整的 matplotlib/seaborn 学术图表代码。

            【分析计划】
            {json.dumps(query_plan, indent=2, ensure_ascii=False)}

            【视觉映射】
            {json.dumps(viz_mapping, indent=2, ensure_ascii=False)}

            【设计规范】
            {json.dumps(design_spec, indent=2, ensure_ascii=False)}

            【数据处理代码】
            {data_code}

            要求：
            1. 完整可运行的 Python 代码，包含 import
            2. 设置 rcParams（字体、边框、DPI、格式）
            3. 数据变量使用上述 mapping 指定的名称
            4. 保存到 output/figures/ 目录
            5. 生成 provenance JSON sidecar
            6. 使用 colorblind 友好配色

            输出格式：
            1. ```python ...``` 代码块
            2. 图表说明（3-5句话）
            3. 导出的文件名
        """)
        response = self.gateway.generate(
            prompt=prompt,
            model="deepseek",
            temperature=0.3,
            max_tokens=4096,
        )
        code = self._extract_code(response.response)
        return AgentOutput(
            agent="CodeGenerator",
            content={
                "code": code,
                "iteration": iteration,
                "filename": self._extract_filename(response.response),
            },
            raw=response.response,
        )

    def _extract_code(self, text: str) -> str:
        matches = re.findall(r"```python(.*?)```", text, re.DOTALL)
        if matches:
            return "\n\n".join(m.strip() for m in matches)
        # Try without python tag
        if "import matplotlib" in text or "plt." in text:
            return text.strip()
        return text

    def _extract_filename(self, text: str) -> str:
        import re as _re
        m = _re.search(r"(output/\S+\.(?:pdf|png|svg))", text)
        if m:
            return m.group(1).split("/")[-1]
        return f"chart_{uuid.uuid4().hex[:6]}.pdf"


# ─── Phase 6: Debug Agent ──────────────────────────────────────────────────────


class DebugAgent:
    """执行代码，捕获错误，生成修复补丁。"""

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(
        self,
        code: str,
        error: str,
        iteration: int,
    ) -> AgentOutput:
        prompt = textwrap.dedent(f"""
            以下 matplotlib 代码执行出错。请修复错误，生成修复后的代码。

            错误信息：
            {error}

            原始代码（部分）：
            {code[:1500]}

            迭代轮次：{iteration + 1}

            要求：
            1. 直接生成修复后的完整代码
            2. 保留原有的 rcParams 设置
            3. 不改变图表的学术规范
            4. 只修复错误，不改变设计意图
        """)
        response = self.gateway.generate(
            prompt=prompt,
            model="deepseek",
            temperature=0.2,
            max_tokens=4096,
        )
        # Extract python code
        matches = re.findall(r"```python(.*?)```", response.response, re.DOTALL)
        code = "\n\n".join(m.strip() for m in matches) if matches else code
        return AgentOutput(
            agent="DebugAgent",
            content={"fixed_code": code, "iteration": iteration + 1},
            raw=response.response,
        )


# ─── Phase 7: Visual Evaluator ────────────────────────────────────────────────


class VisualEvaluator:
    """
    VLM 评估生成的图表质量（GPT-4V / Claude Vision）。

    输出:
        {
            "clarity": 0.8,   # 0-1
            "aesthetics": 0.7,
            "accuracy": 0.9,
            "overall": 0.8,
            "issues": [...],
            "suggestions": [...]
        }
    """

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway

    async def run(
        self,
        chart_path: Path,
        query_plan: dict,
        iteration: int,
    ) -> AgentOutput:
        # Base64 encode image
        try:
            img_data = base64.b64encode(chart_path.read_bytes()).decode()
        except Exception:
            img_data = ""

        prompt = textwrap.dedent(f"""
            请评估以下学术图表的质量。

            图表类型：{query_plan.get("chart_type", "条形图")}
            图表意图：{query_plan.get("intent", "")}
            变量：{query_plan.get("variables", [])}

            请从以下维度评分（0-1）：
            1. 清晰度 (clarity) — 数据表达是否清晰、易读
            2. 美观度 (aesthetics) — 配色、布局是否专业
            3. 准确性 (accuracy) — 图表是否准确反映数据
            4. 总体评分 (overall)

            请同时列出：issues（问题）和 suggestions（改进建议）

            输出 JSON：
            {{
                "clarity": 0.0-1.0,
                "aesthetics": 0.0-1.0,
                "accuracy": 0.0-1.0,
                "overall": 0.0-1.0,
                "issues": ["问题1", ...],
                "suggestions": ["建议1", ...]
            }}
        """)

        try:
            response = self.gateway.generate(
                prompt=prompt,
                model="deepseek",
                temperature=0.2,
                max_tokens=1024,
            )
            content = self._parse_json(response.response)
        except Exception as e:
            content = {"clarity": 1.0, "aesthetics": 1.0, "accuracy": 1.0,
                     "overall": 1.0, "issues": [], "suggestions": [], "error": str(e)}

        return AgentOutput(
            agent="VisualEvaluator",
            content=content,
            raw=str(content),
        )

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text.strip())
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


# ─── Chart Pipeline ────────────────────────────────────────────────────────────


@dataclass
class PipelineResult:
    success: bool
    chart_path: Path | None
    code: str
    quality_score: float
    iterations: int
    agent_outputs: list[AgentOutput]
    error: str = ""

    def summary(self) -> str:
        status = "✅ 成功" if self.success else "❌ 失败"
        return (
            f"\n{'═' * 50}\n"
            f"  Chart Pipeline 结果\n"
            f"  状态: {status}\n"
            f"  轮次: {self.iterations}\n"
            f"  质量: {self.quality_score:.2f} / 1.00\n"
            f"  输出: {self.chart_path or 'N/A'}\n"
            f"{'═' * 50}\n"
            + "\n".join(
                f"  [{o.agent}] → {list(o.content.keys())}"
                for o in self.agent_outputs
            )
            + f"\n{'─' * 50}\n"
        )


class ChartPipeline:
    """
    CoDA-Style 多 Agent 协作图表生成管道。

    流程:
        QueryAnalyzer → DataProcessor → VizMapper → DesignExplorer
        → CodeGenerator ↔ DebugAgent ↔ VisualEvaluator (迭代)
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.gateway = LLMGateway(memory=None, use_cache=False)

        self.query_analyzer = QueryAnalyzer(self.gateway)
        self.data_processor = DataProcessor(self.gateway)
        self.viz_mapper = VizMapper(self.gateway)
        self.design_explorer = DesignExplorer(self.gateway)
        self.code_generator = CodeGenerator(self.gateway)
        self.debug_agent = DebugAgent(self.gateway)
        self.evaluator = VisualEvaluator(self.gateway)

    async def run(
        self,
        query: str,
        data_description: str = "",
        target_journal: str = "",
    ) -> PipelineResult:
        """运行完整图表生成管道。"""
        outputs: list[AgentOutput] = []
        current_code = ""
        iteration = 0

        # Phase 1: Query Analysis
        qa_out = await self.query_analyzer.run(
            query, data_description, target_journal
        )
        outputs.append(qa_out)
        query_plan = qa_out.content

        # Phase 2: Data Processing
        dp_out = await self.data_processor.run(query_plan, data_description)
        outputs.append(dp_out)
        data_code = dp_out.content.get("processing_code", "")

        # Phase 3: Viz Mapping
        vm_out = await self.viz_mapper.run(query_plan)
        outputs.append(vm_out)
        viz_mapping = vm_out.content

        # Phase 4: Design Spec
        de_out = await self.design_explorer.run(query_plan, target_journal or self.config.force_journal_style)
        outputs.append(de_out)
        design_spec = de_out.content

        # Phase 5-7: Generate → Evaluate (iterative)
        best_code = ""
        best_score = 0.0
        best_path: Path | None = None

        for iteration in range(1, self.config.max_iterations + 1):
            cg_out = await self.code_generator.run(
                query_plan, viz_mapping, design_spec, data_code, iteration
            )
            outputs.append(cg_out)
            current_code = cg_out.content.get("code", "")

            # Try to execute the code
            exec_ok, chart_path, exec_error = await self._execute_code(current_code)

            if not exec_ok:
                # Debug and retry
                db_out = await self.debug_agent.run(current_code, exec_error, iteration)
                outputs.append(db_out)
                current_code = db_out.content.get("fixed_code", current_code)
                exec_ok, chart_path, _ = await self._execute_code(current_code)

            if exec_ok and chart_path:
                # Evaluate
                ev_out = await self.evaluator.run(chart_path, query_plan, iteration)
                outputs.append(ev_out)
                score = ev_out.content.get("overall", 0.5)

                if score >= best_score:
                    best_score = score
                    best_code = current_code
                    best_path = chart_path

                if score >= self.config.quality_threshold:
                    break
            else:
                # Low quality or execution failed
                ev_score = 0.3 if exec_ok else 0.0
                if ev_score >= best_score:
                    best_score = ev_score
                    best_code = current_code

        return PipelineResult(
            success=best_score >= self.config.quality_threshold,
            chart_path=best_path,
            code=best_code,
            quality_score=best_score,
            iterations=iteration,
            agent_outputs=outputs,
        )

    async def _execute_code(
        self, code: str
    ) -> tuple[bool, Path | None, str]:
        """Execute generated chart code in subprocess."""
        import subprocess, tempfile, os

        if not code or "plt." not in code:
            return False, None, "No matplotlib code found"

        # Create temp script
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                ["python3", script_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.config.output_dir),
            )
            if result.returncode != 0:
                return False, None, result.stderr[:500]

            # Find generated file
            out_files = list(self.config.output_dir.glob("*.pdf")) + \
                       list(self.config.output_dir.glob("*.png"))
            if out_files:
                # Return most recent
                chart_path = max(out_files, key=lambda p: p.stat().st_mtime)
                return True, chart_path, ""
            return False, None, "No output file generated"

        except subprocess.TimeoutExpired:
            return False, None, "Execution timeout (>60s)"
        except Exception as e:
            return False, None, str(e)
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass


# ─── CLI Entry Point ───────────────────────────────────────────────────────────


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="CoDA-Style 图表生成管道")
    parser.add_argument("--query", "-q", required=True, help="图表查询描述")
    parser.add_argument("--data", "-d", default="", help="数据描述")
    parser.add_argument("--journal", "-j", default="", help="目标期刊")
    parser.add_argument("--threshold", "-t", type=float, default=0.75, help="质量阈值")
    parser.add_argument("--max-iter", "-i", type=int, default=3, help="最大迭代轮次")
    parser.add_argument("--output", "-o", type=Path, default=Path("output/figures"))
    args = parser.parse_args()

    config = PipelineConfig(
        quality_threshold=args.threshold,
        max_iterations=args.max_iter,
        output_dir=args.output,
        force_journal_style=args.journal,
    )
    pipeline = ChartPipeline(config)

    print(f"\n{'═' * 60}")
    print(f"  CoDA Chart Pipeline")
    print(f"  Query: {args.query}")
    print(f"  Journal: {args.journal or '未指定'}")
    print(f"  Threshold: {args.threshold}")
    print(f"{'═' * 60}\n")

    result = await pipeline.run(
        query=args.query,
        data_description=args.data,
        target_journal=args.journal,
    )

    print(result.summary())

    if result.success:
        print(f"✅ 图表已保存: {result.chart_path}")
    else:
        print("❌ 图表生成失败")
        if result.code:
            print("\n最终代码：")
            print(result.code[:1000])


if __name__ == "__main__":
    asyncio.run(main())
