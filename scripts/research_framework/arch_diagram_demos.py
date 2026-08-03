"""
arch_diagram_demos.py — 同时使用 matplotlib + graphviz 双后端生成 5 张 demo 图

用法:
  python scripts/research_framework/arch_diagram_demos.py

输出:
  output/figures/demo_arch_finresearch_gv.png     (graphviz 后端 · 浅色风格)
  output/figures/demo_hierarchy_pipeline_gv.png   (graphviz 后端)
  output/figures/demo_process_flow_gv.png         (graphviz 后端)
  output/figures/demo_consort_gv.png              (graphviz 后端)
  output/figures/demo_org_chart_gv.png            (graphviz 后端)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.research_framework.arch_diagram import (
    DiagramSpec,
    Edge,
    Layer,
    Node,
    NODE_DECISION,
    NODE_END,
    NODE_START,
)
from scripts.research_framework.arch_diagram_gv import (
    graphviz_available,
    hierarchy_tree_gv,
    process_flow_gv,
    swim_lane_gv,
)


OUT_DIR = Path(__file__).resolve().parents[2] / "output" / "figures"


def demo_arch_finresearch_gv() -> str:
    """Demo 1: FinResearch Agent 系统架构（graphviz 浅色风格）"""
    out = f"{OUT_DIR}/demo_arch_finresearch_gv.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = DiagramSpec(
        title="",
        width=120, height=70,
        layers=[
            Layer("USER LAYER", y_top=70, y_bottom=55, color="#FDEBD0", text_color="#D68910"),
            Layer("SKILLS LAYER", y_top=53, y_bottom=38, color="#D6EAF8", text_color="#21618C"),
            Layer("PERSISTENCE", y_top=36, y_bottom=21, color="#EBDEF0", text_color="#6C3483"),
            Layer("INFRASTRUCTURE", y_top=19, y_bottom=4, color="#D5F5E3", text_color="#1E8449"),
        ],
        nodes=[
            # USER LAYER
            Node("u1", "Researchers", layer="USER LAYER", column="Main",
                 color="#F39C12", icon="U"),
            Node("u2", "HitL Reviewer", layer="USER LAYER", column="Main",
                 color="#F39C12", icon="U"),
            # SKILLS - Sub-agents
            Node("a1", "Orchestrator", layer="SKILLS LAYER", column="Sub-agents",
                 color="#1ABC9C", icon="1"),
            Node("a2", "Ideator", layer="SKILLS LAYER", column="Sub-agents",
                 color="#1ABC9C", icon="2"),
            Node("a3", "Reviewer", layer="SKILLS LAYER", column="Sub-agents",
                 color="#1ABC9C", icon="3"),
            # SKILLS - Pipelines
            Node("p1", "fin-full-pipeline", layer="SKILLS LAYER", column="Pipelines",
                 color="#3498DB", icon="1"),
            Node("p2", "fin-lit-review", layer="SKILLS LAYER", column="Pipelines",
                 color="#3498DB", icon="2"),
            Node("p3", "fin-novelty-check", layer="SKILLS LAYER", column="Pipelines",
                 color="#3498DB", icon="3"),
            # SKILLS - Knowledge
            Node("d1", "SKILL.md x17", layer="SKILLS LAYER", column="Knowledge",
                 color="#8E44AD", icon="K"),
            # PERSISTENCE
            Node("s1", "Checkpoint", layer="PERSISTENCE", column="Main",
                 color="#8E44AD", icon="D"),
            Node("s2", "Provenance", layer="PERSISTENCE", column="Main",
                 color="#8E44AD", icon="P"),
            # INFRASTRUCTURE
            Node("i1", "MCP x43", layer="INFRASTRUCTURE", column="Main",
                 color="#27AE60", icon="M"),
            Node("i2", "LLM (DeepSeek)", layer="INFRASTRUCTURE", column="Main",
                 color="#27AE60", icon="L"),
        ],
        edges=[
            # 主流程：用户 → pipeline → 反馈
            Edge("u1", "p1", style="solid"),
            Edge("p1", "p2", style="solid"),
            Edge("p2", "p3", style="solid"),
            Edge("p3", "u2", label="HITL", style="invoke"),
            # pipeline → sub-agents
            Edge("p1", "a1", label="dispatch", style="invoke"),
            Edge("a1", "a2", style="dashed"),
            Edge("a2", "a3", style="dashed"),
            # sub-agents → knowledge
            Edge("a1", "d1", label="read", style="data"),
            # pipeline → persistence
            Edge("p1", "s1", style="solid"),
            Edge("p3", "s2", style="solid"),
            # persistence → infrastructure
            Edge("s1", "i1", style="solid"),
            Edge("s2", "i2", style="loop"),
        ],
    )
    return swim_lane_gv(spec, out)


def demo_hierarchy_pipeline_gv() -> str:
    """Demo 2: 8 步研究流水线（graphviz 后端）"""
    out = f"{OUT_DIR}/demo_hierarchy_pipeline_gv.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = DiagramSpec(
        title="",
        nodes=[
            Node("root", "Research Pipeline", color="#F5B700"),
            Node("p1", "1. Lit Review", color="#3498DB"),
            Node("p2", "2. Idea Gen", color="#9B59B6"),
            Node("p3", "3. Novelty Check", color="#E91E63"),
            Node("p4", "4. Design", color="#1ABC9C"),
            Node("p5", "5. Data Acq", color="#27AE60"),
            Node("p6", "6. Empirical", color="#F39C12"),
            Node("p7", "7. Paper Write", color="#E67E22"),
            Node("p8", "8. Review", color="#E74C3C"),
            Node("c1", "Idea Feasibility", color="#95A5A6"),
            Node("c2", "DID/IV/RDD", color="#95A5A6"),
            Node("c3", "MCP x43", color="#95A5A6"),
            Node("c4", "300 DPI Charts", color="#95A5A6"),
        ],
        edges=[
            Edge("root", f"p{i}") for i in range(1, 9)
        ] + [
            Edge("p2", "c1"), Edge("p4", "c2"),
            Edge("p5", "c3"), Edge("p6", "c4"),
        ],
    )
    return hierarchy_tree_gv(spec, out, style="tree")


def demo_process_flow_gv() -> str:
    """Demo 3: 文献检索流程（graphviz 后端）"""
    out = f"{OUT_DIR}/demo_process_flow_gv.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = DiagramSpec(
        title="",
        nodes=[
            Node("start", "Start Search", node_type=NODE_START, color="#34D399", icon="S"),
            Node("q", "Input Topic", color="#3498DB", icon="1"),
            Node("fetch", "MCP Multi-Source", color="#8E44AD", icon="2"),
            Node("enough", "Papers >= 30?", node_type=NODE_DECISION,
                 color="#F39C12", icon="?"),
            Node("aug", "Augment Query", color="#E67E22", icon="3"),
            Node("dedup", "Dedup + Sort", color="#9B59B6", icon="4"),
            Node("cite", "Citation Network", color="#16A085", icon="5"),
            Node("save", "Save LIT_REVIEW.md", color="#27AE60", icon="6"),
            Node("end", "Done", node_type=NODE_END, color="#E74C3C", icon="E"),
        ],
        edges=[
            Edge("start", "q"),
            Edge("q", "fetch"),
            Edge("fetch", "enough"),
            Edge("enough", "dedup", label="yes", color="#27AE60"),
            Edge("enough", "aug", label="no", color="#E74C3C"),
            Edge("aug", "fetch", style="loop"),
            Edge("dedup", "cite"),
            Edge("cite", "save"),
            Edge("save", "end"),
        ],
    )
    return process_flow_gv(spec, out)


def demo_consort_gv() -> str:
    """Demo 4: CONSORT 流程图（graphviz 后端）"""
    out = f"{OUT_DIR}/demo_consort_gv.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = DiagramSpec(
        title="",
        nodes=[
            Node("enroll", "Enrolled N=5820", layer=0, color="#1ABC9C"),
            Node("rand", "Randomized", layer=1, color="#3498DB"),
            Node("trt", "Treatment n=2910", layer=1, column="left", color="#27AE60"),
            Node("ctl", "Control n=2910", layer=1, column="right", color="#E67E22"),
            Node("trt_ex", "Excluded n=170", layer=2, column="left", color="#E74C3C"),
            Node("trt_an", "Analyzed n=2740", layer=2, column="left", color="#27AE60"),
            Node("ctl_ex", "Excluded n=170", layer=2, column="right", color="#E74C3C"),
            Node("ctl_an", "Analyzed n=2740", layer=2, column="right", color="#27AE60"),
        ],
        edges=[
            Edge("enroll", "rand"),
            Edge("rand", "trt"), Edge("rand", "ctl"),
            Edge("trt", "trt_ex"), Edge("trt", "trt_an"),
            Edge("ctl", "ctl_ex"), Edge("ctl", "ctl_an"),
        ],
    )
    return hierarchy_tree_gv(spec, out, style="consort")


def demo_org_chart_gv() -> str:
    """Demo 5: FinResearch Agent 组织架构（graphviz 后端）"""
    out = f"{OUT_DIR}/demo_org_chart_gv.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = DiagramSpec(
        title="",
        nodes=[
            Node("root", "FinResearch Agent", color="#F5B700"),
            Node("core", "Core Layer\n87 modules", color="#1ABC9C"),
            Node("rf", "Research Framework\n47 methods", color="#27AE60"),
            Node("mcp", "MCP x43", color="#9B59B6"),
            Node("lit", "Literature\nPipeline", color="#3498DB"),
            Node("data", "Data Fetcher", color="#E67E22"),
            Node("paper", "Paper\nGenerator", color="#E91E63"),
            Node("skill", "Skill Registry\n17 skills", color="#9B59B6"),
            Node("hl", "HitL\nCheckpoint", color="#F39C12"),
        ],
        edges=[
            Edge("root", "core"), Edge("root", "rf"), Edge("root", "mcp"),
            Edge("core", "skill"), Edge("core", "hl"),
            Edge("rf", "lit"), Edge("rf", "data"), Edge("rf", "paper"),
        ],
    )
    return hierarchy_tree_gv(spec, out, style="org")


def main():
    if not graphviz_available():
        print("⚠️  graphviz 不可用，请先安装：brew install graphviz && pip install graphviz")
        return

    print("=" * 60)
    print("Arch Diagram Demos · Graphviz 后端（浅色风格）")
    print("=" * 60)
    demos = [
        ("arch_finresearch", demo_arch_finresearch_gv),
        ("hierarchy_pipeline", demo_hierarchy_pipeline_gv),
        ("process_flow", demo_process_flow_gv),
        ("consort", demo_consort_gv),
        ("org_chart", demo_org_chart_gv),
    ]
    for name, func in demos:
        try:
            out = func()
            size = os.path.getsize(out)
            print(f"[OK] {name:25s} -> {out}  ({size:,} bytes)")
        except Exception as ex:
            print(f"[FAIL] {name:25s} -> {ex}")
    print()
    print("5 张 graphviz 后端 demo 已生成（接近参考图风格）")


if __name__ == "__main__":
    main()
