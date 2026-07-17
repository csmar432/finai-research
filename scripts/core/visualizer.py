"""WorkflowVisualizer: Graph-based workflow visualization.

LangGraph Studio / PaperOrchestra-style visualization:
    - Graphviz DOT language export
    - Mermaid diagram generation
    - Interactive HTML visualization
    - Pipeline execution trace overlay

Reference: LangGraph, https://github.com/langchain-ai/langgraph
"""

from __future__ import annotations

__all__ = [
    "OutputFormat",
    "VizNode",
    "VizEdge",
    "create_tracked_chart",
]

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.core.orchestrator import PipelineResult

# ─── Output Format ─────────────────────────────────────────────────────────────


class OutputFormat(Enum):
    DOT = "dot"           # Graphviz DOT
    MERMAID = "mermaid"   # Mermaid markdown
    HTML = "html"         # Interactive HTML (D3.js)
    JSON = "json"         # Raw node-link data


# ─── Node & Edge ────────────────────────────────────────────────────────────────


@dataclass
class VizNode:
    """A node in the workflow visualization."""
    id: str
    label: str
    type: str = "agent"   # "agent" | "gate" | "data" | "output" | "input" | "tool"
    color: str = "#4A90E2"
    shape: str = "box"      # "box" | "diamond" | "circle" | "hexagon" | "stadium"
    metadata: dict = field(default_factory=dict)
    # Enhanced trace data
    status: str = ""        # "pending" | "running" | "approved" | "error" | "max_iterations"
    duration_ms: float = 0
    tokens_used: int = 0
    model: str = ""
    input_preview: str = ""
    output_preview: str = ""
    error: str = ""
    iterations: int = 0
    tools_called: list = field(default_factory=list)
    citations: list = field(default_factory=list)

    def to_dot(self) -> str:
        shape_map = {
            "box": "box",
            "diamond": "diamond",
            "circle": "circle",
            "hexagon": "hexagon",
            "stadium": "stadium",
        }
        shape = shape_map.get(self.shape, "box")
        meta_parts = []
        if self.duration_ms:
            meta_parts.append(f"耗时: {self.duration_ms/1000:.1f}s")
        if self.tokens_used:
            meta_parts.append(f"Token: {self.tokens_used:,}")
        if self.iterations:
            meta_parts.append(f"迭代: {self.iterations}")
        meta_str = " | ".join(meta_parts)
        label = self.label if not meta_str else f"{self.label} | {meta_str}"
        return f'    "{self.id}" [label="{label}", shape={shape}, color="{self.color}", style=filled, fillcolor=lightyellow];'

    def to_mermaid(self) -> str:
        shape_map = {
            "box": "{ }",
            "diamond": "{ { } }",
            "circle": "(())",
            "hexagon": "六边形",
            "stadium": "()",
        }
        shape_str = shape_map.get(self.shape, "{ }")
        return f'    {self.id}{shape_str}["{self.label}"]'

    def _status_to_color(self) -> str:
        """Map status to badge color."""
        mapping = {
            "approved": "#22c55e",
            "error": "#ef4444",
            "max_iterations": "#eab308",
            "running": "#3b82f6",
            "pending": "#6b7280",
        }
        return mapping.get(self.status, "#6b7280")

    def _type_icon_svg(self) -> str:
        """Return SVG path for node type icon."""
        icons = {
            "input": '<path d="M12 4v16m8-8H4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
            "agent": '<path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
            "gate": '<path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
            "output": '<path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
            "tool": '<path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
            "data": '<path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
        }
        return icons.get(self.type, icons["agent"])

    def _type_label_cn(self) -> str:
        labels = {
            "input": "输入节点",
            "agent": "Agent 节点",
            "gate": "审批门控",
            "output": "输出节点",
            "tool": "工具节点",
            "data": "数据节点",
        }
        return labels.get(self.type, self.type)

    def _duration_str(self) -> str:
        if not self.duration_ms:
            return "—"
        if self.duration_ms < 1000:
            return f"{self.duration_ms:.0f}ms"
        if self.duration_ms < 60000:
            return f"{self.duration_ms/1000:.1f}s"
        return f"{self.duration_ms/60000:.1f}min"

    def _tokens_str(self) -> str:
        if not self.tokens_used:
            return "—"
        if self.tokens_used < 1000:
            return f"{self.tokens_used}"
        return f"{self.tokens_used/1000:.1f}k"


@dataclass
class VizEdge:
    """A directed edge in the workflow visualization."""
    source: str
    target: str
    label: str = ""
    style: str = "solid"  # "solid" | "dashed" | "dotted"
    color: str = "#666666"
    metadata: dict = field(default_factory=dict)


# ─── Color Palette ────────────────────────────────────────────────────────────


AGENT_COLORS = {
    "outline": "#9B59B6",      # Purple
    "literature": "#3498DB",   # Blue
    "plotting": "#E67E22",     # Orange
    "writing": "#27AE60",      # Green
    "refinement": "#E74C3C",  # Red
    "evaluation": "#1ABC9C",   # Teal
    "gate": "#F39C12",        # Gold
    "data": "#95A5A6",        # Gray
    "input": "#3498DB",        # Blue
    "output": "#27AE60",      # Green
}


# ─── WorkflowVisualizer ────────────────────────────────────────────────────────


class WorkflowVisualizer:
    """
    Generate visual representations of agent workflows.

    Supported output formats:
        - DOT (Graphviz): Best for PDF/PNG export
        - Mermaid: Best for markdown documentation
        - HTML: Best for interactive exploration
        - JSON: Best for programmatic processing

    Usage:
        viz = WorkflowVisualizer()

        # Add nodes and edges
        viz.add_node("outline", "OutlineAgent")
        viz.add_edge("outline", "literature")

        # Generate DOT representation (no args needed)
        dot = viz.to_dot()

        # Generate Mermaid diagram
        mermaid = viz.to_mermaid()

        # Save as interactive HTML
        html_path = viz.to_html(output_path="workflow.html")

        # Save as modern HTML with D3.js
        modern_html = viz.to_modern_html(output_path="workflow_modern.html")

        # Overlay execution trace from PipelineResult
        viz.overlay_trace(pipeline_result)
    """

    def __init__(self):
        self._nodes: list[VizNode] = []
        self._edges: list[VizEdge] = []
        self._trace: dict[str, Any] = {}

    # ── Helpers ────────────────────────────────────────────────────

    def _ms_to_str(self, ms: float) -> str:
        """Format milliseconds to human-readable string."""
        if not ms:
            return "–"
        if ms < 1000:
            return f"{ms:.0f}ms"
        if ms < 60000:
            return f"{ms/1000:.1f}s"
        return f"{ms/60000:.1f}min"

    def _tokens_fmt(self, tokens: int) -> str:
        """Format token count."""
        if not tokens:
            return "–"
        if tokens < 1000:
            return str(tokens)
        return f"{tokens/1000:.1f}k"

    # ── Build from Pipeline Steps ─────────────────────────────────────

    def build_from_steps(self, steps: list[Any]) -> WorkflowVisualizer:
        """
        Build a visualization from pipeline steps.

        Parameters
        ----------
        steps : list
            List of PipelineStep objects from AgentOrchestrator.

        Returns
        -------
        WorkflowVisualizer
            Self (for chaining).
        """
        self._nodes = []
        self._edges = []

        # Input node
        self._nodes.append(VizNode(
            id="input",
            label="用户请求",
            type="input",
            color=AGENT_COLORS["input"],
            shape="box",
        ))

        prev_node = "input"

        for i, step in enumerate(steps):
            stage_name = getattr(step, "stage", None)
            stage_str = stage_name.value if stage_name else f"step_{i}"
            agent_name = getattr(step, "agent_name", stage_str)
            hitl_gate = getattr(step, "hitl_gate", False)

            # Main agent node
            node_color = AGENT_COLORS.get(agent_name, "#4A90E2")
            self._nodes.append(VizNode(
                id=stage_str,
                label=agent_name,
                type="agent",
                color=node_color,
                shape="box",
                metadata={"stage": stage_str, "agent": agent_name},
            ))

            self._edges.append(VizEdge(
                source=prev_node,
                target=stage_str,
                label="",
                style="solid",
            ))

            # HITL gate node
            if hitl_gate:
                gate_id = f"{stage_str}_gate"
                self._nodes.append(VizNode(
                    id=gate_id,
                    label="人工审批",
                    type="gate",
                    color=AGENT_COLORS["gate"],
                    shape="diamond",
                ))
                self._edges.append(VizEdge(
                    source=stage_str,
                    target=gate_id,
                    label="需审批",
                    style="dashed",
                    color="#F39C12",
                ))
                prev_node = gate_id
            else:
                prev_node = stage_str

        # Output node
        self._nodes.append(VizNode(
            id="output",
            label="最终结果",
            type="output",
            color=AGENT_COLORS["output"],
            shape="box",
        ))
        self._edges.append(VizEdge(
            source=prev_node,
            target="output",
            label="",
            style="solid",
        ))

        return self

    def overlay_trace(self, result: PipelineResult) -> WorkflowVisualizer:
        """
        Overlay execution trace data onto the visualization.

        Extracts detailed metrics: duration, tokens, model, inputs, outputs,
        tools called, and any error messages.
        """
        import time as _time
        self._trace = {}

        for event in result.trace:
            event_type = event.get("type", "")
            stage = event.get("stage", "")

            if event_type == "agent_start":
                self._trace[stage] = {"status": "running", "start_time": event.get("timestamp", _time.time())}
            elif event_type == "agent_end":
                status = event.get("status", "unknown")
                end_time = event.get("timestamp", _time.time())
                start_info = self._trace.get(stage, {})
                start_time = start_info.get("start_time", end_time)
                self._trace[stage] = {
                    "status": status,
                    "iterations": event.get("iterations", 0),
                    "duration_ms": event.get("latency_ms", (end_time - start_time) * 1000),
                    "tokens_used": event.get("tokens_used", 0),
                    "model": event.get("model", ""),
                    "input_preview": event.get("input_preview", ""),
                    "output_preview": event.get("output_preview", ""),
                    "error": event.get("error", ""),
                    "tools_called": event.get("tools_called", []),
                    "citations": event.get("citations", []),
                }

        for node in self._nodes:
            trace_info = self._trace.get(node.id, {})
            status = trace_info.get("status", "pending")

            # Map status to display
            status_map = {
                "approved": "已完成",
                "error": "执行失败",
                "max_iterations": "迭代超限",
                "running": "运行中",
                "pending": "待执行",
            }
            node.status = status_map.get(status, status)

            if status == "approved":
                node.color = "#22c55e"
            elif status == "error":
                node.color = "#ef4444"
            elif status == "max_iterations":
                node.color = "#eab308"
            elif status == "running":
                node.color = "#3b82f6"
            else:
                node.color = AGENT_COLORS.get(node.type, "#6b7280")

            node.duration_ms = trace_info.get("duration_ms", 0)
            node.tokens_used = trace_info.get("tokens_used", 0)
            node.model = trace_info.get("model", "")
            node.input_preview = trace_info.get("input_preview", "")
            node.output_preview = trace_info.get("output_preview", "")
            node.error = trace_info.get("error", "")
            node.iterations = trace_info.get("iterations", 0)
            node.tools_called = trace_info.get("tools_called", [])
            node.citations = trace_info.get("citations", [])

        return self

    # ── Output Formats ─────────────────────────────────────────────

    def to_dot(self) -> str:
        """
        Generate Graphviz DOT representation.

        Usage: dot -Tpdf workflow.dot > workflow.pdf
        """
        lines = [
            "digraph workflow {",
            "    rankdir=TB;",
            '    node [fontname="Helvetica"];',
            '    edge [fontname="Helvetica"];',
        ]

        for node in self._nodes:
            lines.append(node.to_dot())

        lines.append("")

        for edge in self._edges:
            style_str = f', style={edge.style}' if edge.style != "solid" else ""
            color_str = f', color="{edge.color}"' if edge.color != "#666666" else ""
            label_str = f', xlabel="{edge.label}"' if edge.label else ""
            lines.append(
                f'    "{edge.source}" -> "{edge.target}" [{style_str}{color_str}{label_str}];'
            )

        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """
        Generate Mermaid flowchart markdown.

        Usage: Paste into GitHub Issues, Notion, Mermaid Live Editor.
        """
        lines = [
            "```mermaid",
            "flowchart TD",
        ]

        # Nodes
        for node in self._nodes:
            status = node.metadata.get("status", "")
            label = str(node.label)
            if status:
                label = label + "\\n" + status

            if node.shape == "diamond":
                lines.append(f'    {node.id}{{{"{"} {"}"}}}["{label}"]')
            elif node.shape == "circle":
                lines.append(f'    {node.id}(({label}))')
            else:
                lines.append(f'    {node.id}["{label}"]')

        lines.append("")

        # Edges
        for edge in self._edges:
            label_str = f'|{edge.label}|' if edge.label else ""
            style_str = "" if edge.style == "solid" else ' -.- '

            lines.append(f'    {edge.source} -->{style_str}{label_str} {edge.target}')

        lines.append("```")
        return "\n".join(lines)


    def to_html(
        self,
        output_path: str | Path,
        title: str = "Agent Workflow",
        show_controls: bool = True,
        animation_enabled: bool = True,
    ) -> Path:
        """
        Generate an interactive HTML visualization with modern design.

        Features:
        - Animated execution flow
        - Node detail tooltips
        - Zoom/pan controls
        - Progress indicators
        - Status badges
        - Node search

        Parameters
        ----------
        output_path : str | Path
            Path to save the HTML file.
        title : str
            Page title.
        show_controls : bool
            Show zoom/search controls.
        animation_enabled : bool
            Enable node animations.

        Returns
        -------
        Path
            Path to the saved HTML file.
        """
        return self.to_modern_html(output_path, title, animation_enabled)

    def to_json(self) -> dict[str, Any]:
        """Export as raw node-link JSON with full trace data."""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.type,
                    "color": n.color,
                    "shape": n.shape,
                    "metadata": n.metadata,
                    "status": n.status,
                    "duration_ms": n.duration_ms,
                    "tokens_used": n.tokens_used,
                    "model": n.model,
                    "input_preview": n.input_preview,
                    "output_preview": n.output_preview,
                    "error": n.error,
                    "iterations": n.iterations,
                    "tools_called": n.tools_called,
                    "citations": n.citations,
                }
                for n in self._nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "label": e.label,
                    "style": e.style,
                    "color": e.color,
                }
                for e in self._edges
            ],
            "trace": self._trace,
        }

    def to_modern_html(
        self,
        output_path: str | Path,
        title: str = "Agent Workflow",
        animation_enabled: bool = True,
        theme: str = "light",
        layout: str = "horizontal",
    ) -> Path:
        """
        Generate a modern interactive HTML visualization.

        Features:
        - Two-panel layout (graph + detail panel)
        - Horizontal tree layout with SVG nodes
        - Full trace info: duration, tokens, model, I/O preview, tools, citations
        - Execution timeline bar
        - Node-type color legend
        - Light/dark theme toggle
        - Zoom, pan, fit-to-view, fullscreen controls
        - Resizable detail panel
        - Auto-refresh via window.updateNodeStatus()

        Parameters
        ----------
        output_path : Path
            Path to save HTML file.
        title : str
            Page title.
        animation_enabled : bool
            Enable animations.
        theme : str
            "light" or "dark".

        Returns
        -------
        Path to saved HTML.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # ── Serialize node data ──────────────────────────────────────
        nodes_data = [
            {
                "id": n.id,
                "label": n.label,
                "type": n.type,
                "color": n.color,
                "shape": n.shape,
                "status": n.status,
                "duration_ms": n.duration_ms,
                "tokens_used": n.tokens_used,
                "model": n.model,
                "input_preview": n.input_preview[:200] if n.input_preview else "",
                "output_preview": n.output_preview[:300] if n.output_preview else "",
                "error": n.error[:200] if n.error else "",
                "iterations": n.iterations,
                "tools_called": n.tools_called,
                "citations": n.citations,
                "duration_str": n._duration_str(),
                "tokens_str": n._tokens_str(),
            }
            for n in self._nodes
        ]

        links_data = [
            {
                "source": e.source,
                "target": e.target,
                "label": e.label,
                "style": e.style,
                "color": e.color,
            }
            for e in self._edges
        ]

        nodes_json = json.dumps(nodes_data, ensure_ascii=False)
        links_json = json.dumps(links_data, ensure_ascii=False)

        def _html(s):
            return (s.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))

        nodes_json_esc = _html(nodes_json)
        links_json_esc = _html(links_json)
        theme_esc = _html(theme)
        node_count = len(nodes_data)
        link_count = len(links_data)

        # Light vs dark theme tokens
        if theme == "dark":
            bg = "#0f172a"; surface = "#1e293b"; surface2 = "#334155"
            border = "#475569"; text = "#f1f5f9"; text_muted = "#94a3b8"
            accent = "#6366f1"; accent2 = "#818cf8"
            header_bg = "rgba(15,23,42,0.9)"; panel_bg = "rgba(30,41,59,0.98)"
            glow_c = "rgba(99,102,241,0.3)"
        else:
            bg = "#f8fafc"; surface = "#ffffff"; surface2 = "#f1f5f9"
            border = "#e2e8f0"; text = "#0f172a"; text_muted = "#64748b"
            accent = "#4f46e5"; accent2 = "#6366f1"
            header_bg = "rgba(255,255,255,0.92)"; panel_bg = "rgba(255,255,255,0.98)"
            glow_c = "rgba(79,70,229,0.15)"

        total_ms = sum(n.duration_ms for n in self._nodes)
        total_tokens = sum(n.tokens_used for n in self._nodes)
        sum(1 for n in self._nodes if n.status in ("已完成", "执行失败"))
        sum(1 for n in self._nodes if n.status == "执行失败")
        total_ms_display = self._ms_to_str(total_ms)
        total_tokens_display = self._tokens_fmt(total_tokens)

        # ── Layout orientation ────────────────────────────────────
        is_vertical = layout == "垂直"
        list({n.type for n in self._nodes})
        type_color_map = {}
        for n in self._nodes:
            if n.type not in type_color_map:
                type_color_map[n.type] = n.color

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
    :root {{
        --bg:{bg};--surface:{surface};--surface2:{surface2};
        --border:{border};--text:{text};--muted:{text_muted};
        --accent:{accent};--accent2:{accent2};
        --hbg:{header_bg};--pbg:{panel_bg};--glow:{glow_c};
    }}
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden;user-select:none;}}
    ::-webkit-scrollbar{{width:5px;height:5px;}}
    ::-webkit-scrollbar-track{{background:transparent;}}
    ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px;}}
    ::-webkit-scrollbar-thumb:hover{{background:var(--muted);}}

    @keyframes shimmer{{0%{{background-position:200% 0;}}100%{{background-position:-200% 0;}}}}
    @keyframes pulse-ring{{0%{{transform:scale(1);opacity:0.8;}}100%{{transform:scale(1.9);opacity:0;}}}}
    @keyframes spin{{to{{transform:rotate(360deg);}}}}
    @keyframes fadeUp{{from{{opacity:0;transform:translateY(6px);}}to{{opacity:1;transform:translateY(0);}}}}
    @keyframes ripple{{0%{{transform:scale(1);opacity:0.4;}}100%{{transform:scale(2.2);opacity:0;}}}}
    @keyframes nodeAppear{{from{{opacity:0;transform:scale(0.85) translateY(8px);}}to{{opacity:1;transform:scale(1) translateY(0);}}}}

    .shimmer{{animation:shimmer 1.8s linear infinite;background:linear-gradient(90deg,var(--accent) 0%,var(--accent2) 50%,var(--accent) 100%);background-size:200% 100%;}}
    .fade-up{{animation:fadeUp 0.25s ease-out forwards;}}
    .node-grp{{cursor:pointer;opacity:0;animation:nodeAppear 0.35s ease-out forwards;}}
    .node-grp:hover{{filter:brightness(1.1);}}
    .node-grp.selected .node-card{{stroke:var(--accent);stroke-width:2.5;}}
    .node-grp.dimmed{{opacity:0.25;}}

    .link-edge{{fill:none;transition:stroke-opacity 0.2s,stroke-width 0.2s;stroke-opacity:0.4;}}
    .link-edge:hover{{stroke-opacity:0.85;stroke-width:2.5;}}
    .link-edge.active{{stroke-opacity:1;stroke:var(--accent);stroke-width:2.5;}}

    .pulse-ring{{animation:pulse-ring 1.6s cubic-bezier(0.215,0.61,0.355,1) infinite;}}
    .spin{{animation:spin 2s linear infinite;}}
    .ripple{{animation:ripple 1.4s ease-out infinite;}}

    .mini-map{{border:1px solid var(--border);border-radius:10px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.15);}}
    .mini-node{{fill-opacity:0.9;stroke:none;}}

    .resizer{{width:4px;cursor:col-resize;background:var(--border);transition:background 0.15s;flex-shrink:0;}}
    .resizer:hover,.resizer.active{{background:var(--accent);}}

    .detail-section{{border-radius:10px;padding:12px 14px;background:var(--surface);border:1px solid var(--border);transition:all 0.2s;}}
    .detail-section:hover{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,70,229,0.08);}}
    .detail-section-header{{display:flex;align-items:center;gap:8px;padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid var(--border);}}
    .collapsible{{cursor:pointer;user-select:none;}}
    .collapsible::before{{content:"\25b8 ";transition:transform 0.2s;display:inline-block;}}
    .collapsible.open::before{{transform:rotate(90deg);}}
    .trace-item{{display:flex;align-items:flex-start;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);}}
    .trace-item:last-child{{border-bottom:none;}}
    .error-box{{background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:10px 12px;margin-top:8px;}}
    .error-box pre{{font-size:10px;color:#dc2626;white-space:pre-wrap;word-break:break-all;margin:0;}}
    .code-block{{font-family:'JetBrains Mono',monospace;font-size:11px;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 12px;white-space:pre-wrap;word-break:break-all;max-height:160px;overflow-y:auto;color:var(--text);line-height:1.55;}}

    .badge{{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap;}}
    .badge-success{{background:#dcfce7;color:#166534;}}
    .badge-error{{background:#fee2e2;color:#991b1b;}}
    .badge-running{{background:#dbeafe;color:#1e40af;}}
    .badge-warn{{background:#fef9c3;color:#854d0e;}}
    .badge-pending{{background:var(--surface2);color:var(--muted);}}

    .sidebar-item{{display:flex;align-items:center;gap:8px;padding:7px 12px;border-radius:8px;cursor:pointer;transition:all 0.15s;font-size:13px;color:var(--text);}}
    .sidebar-item:hover{{background:var(--surface2);}}
    .sidebar-item.active{{background:var(--accent);color:white;}}
    .sidebar-item .count{{margin-left:auto;background:var(--surface2);color:var(--muted);border-radius:999px;padding:1px 7px;font-size:11px;font-weight:600;}}
    .sidebar-item.active .count{{background:rgba(255,255,255,0.2);color:white;}}

    .tl-segment{{height:6px;border-radius:3px;transition:width 0.5s ease;cursor:pointer;}}
    .tl-segment:hover{{filter:brightness(1.15);}}

    .search-input{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 10px 7px 32px;font-size:13px;color:var(--text);outline:none;transition:border-color 0.15s;width:100%;}}
    .search-input:focus{{border-color:var(--accent);}}
    .search-input::placeholder{{color:var(--muted);}}

    .type-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;}}
    .type-dot-sm{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}

    .stat-pill{{border-radius:8px;padding:6px 12px;background:var(--surface);border:1px solid var(--border);text-align:center;min-width:64px;}}
    .stat-pill .v{{font-size:18px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--text);}}
    .stat-pill .l{{font-size:10px;color:var(--muted);margin-top:1px;}}
    .stat-pill.accent .v{{color:var(--accent);}}

    .fullscreen-panel{{position:fixed;inset:0;z-index:9999;background:var(--bg);padding:0;}}
    .fullscreen-panel .fp-header{{position:sticky;top:0;z-index:10;}}

    .node-tooltip{{position:absolute;background:var(--pbg);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:12px;pointer-events:none;opacity:0;transition:opacity 0.15s;white-space:nowrap;z-index:100;box-shadow:0 8px 24px rgba(0,0,0,0.12);}}
    .node-tooltip.visible{{opacity:1;}}

    .llm-badge{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;font-size:10px;font-family:'JetBrains Mono',monospace;background:var(--surface2);border:1px solid var(--border);color:var(--accent);}}
    </style>
</head>
<body>

<!-- ═══════════════════════════════ TOP HEADER ═══════════════════════════════ -->
<header class="fixed inset-x-0 top-0 z-50 flex items-center px-5 py-2.5 gap-6"
        style="background:var(--hbg);backdrop-filter:blur(24px);border-bottom:1px solid var(--border);height:58px;">
    <!-- Brand -->
    <div class="flex items-center gap-3 flex-shrink-0">
        <div class="w-9 h-9 rounded-xl flex items-center justify-center" style="background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 2px 10px var(--glow);">
            <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
        </div>
        <div>
            <h1 class="text-sm font-bold leading-tight" style="color:var(--text);">{title}</h1>
            <p class="text-xs leading-tight" style="color:var(--muted);">实时追踪 · 交互可视化</p>
        </div>
    </div>

    <!-- Global status pill -->
    <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium flex-shrink-0" style="background:var(--surface2);">
        <div class="w-2 h-2 rounded-full" id="h-dot" style="background:var(--muted);"></div>
        <span id="h-status" style="color:var(--muted);">就绪</span>
    </div>

    <!-- Stats row -->
    <div class="flex items-center gap-2 flex-1 justify-center">
        <div class="stat-pill">
            <div class="v" id="s-nodes">{node_count}</div>
            <div class="l">节点</div>
        </div>
        <div class="stat-pill">
            <div class="v" id="s-edges">{link_count}</div>
            <div class="l">连接</div>
        </div>
        <div class="stat-pill accent">
            <div class="v" id="s-dur">{total_ms_display}</div>
            <div class="l">总耗时</div>
        </div>
        <div class="stat-pill accent">
            <div class="v" id="s-tok">{total_tokens_display}</div>
            <div class="l">Token</div>
        </div>
        <div class="stat-pill">
            <div class="v" id="s-done">0/{node_count}</div>
            <div class="l">完成</div>
        </div>
        <div class="stat-pill">
            <div class="v text-red-500" id="s-err">0</div>
            <div class="l">错误</div>
        </div>
    </div>

    <!-- Controls -->
    <div class="flex items-center gap-2 flex-shrink-0">
        <button onclick="toggleLayout()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-80" style="background:var(--surface2);color:var(--text);" title="切换布局方向" id="layout-btn">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7"/>
            </svg>
            <span id="layout-label">{"水平" if is_vertical else "垂直"}</span>
        </button>
        <button onclick="toggleTheme()" class="p-2 rounded-lg transition-all hover:opacity-80" style="background:var(--surface2);" title="切换主题">
            <svg class="w-4 h-4" style="color:var(--text);" id="theme-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
            </svg>
        </button>
        <button onclick="exportSVG()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-80" style="background:var(--surface2);color:var(--text);" title="导出SVG">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            SVG
        </button>
        <button onclick="toggleFullscreen()" class="p-2 rounded-lg transition-all hover:opacity-80" style="background:var(--surface2);" title="全屏">
            <svg class="w-4 h-4" style="color:var(--text);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
            </svg>
        </button>
    </div>
</header>

<!-- ═══════════════════════════════ MAIN LAYOUT ════════════════════════════════ -->
<div class="flex" style="height:100vh;padding-top:58px;padding-bottom:54px;">

    <!-- ── LEFT SIDEBAR: Node Navigator ─────────────────────────────── -->
    <div class="flex flex-col overflow-y-auto flex-shrink-0"
         style="width:220px;background:var(--surface);border-right:1px solid var(--border);padding-top:12px;"
         id="sidebar">
        <!-- Search -->
        <div class="px-3 mb-3" style="position:relative;">
            <svg class="w-3.5 h-3.5" style="position:absolute;left:18px;top:50%;transform:translateY(-50%);color:var(--muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <input class="search-input" id="node-search" placeholder="搜索节点…" oninput="filterNodes(this.value)">
        </div>

        <!-- All nodes -->
        <div class="px-3 mb-2">
            <div class="sidebar-item active" onclick="setFilter('all')" id="filter-all">
                <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"/>
                </svg>
                全部节点
                <span class="count" id="cnt-all">{node_count}</span>
            </div>
        </div>

        <!-- Category sections (dynamically populated) -->
        <div class="px-3 mb-2">
            <div class="text-xs font-semibold uppercase tracking-wider mb-1.5 px-1" style="color:var(--muted);">按类型</div>
            <div id="type-filters"></div>
        </div>

        <!-- Status sections -->
        <div class="px-3 mb-2">
            <div class="text-xs font-semibold uppercase tracking-wider mb-1.5 px-1" style="color:var(--muted);">按状态</div>
            <div id="status-filters"></div>
        </div>

        <!-- Legend -->
        <div class="px-3 mt-auto p-3" style="border-top:1px solid var(--border);">
            <div class="text-xs font-semibold mb-2" style="color:var(--muted);">状态图例</div>
            <div class="flex flex-col gap-1.5">
                <div class="flex items-center gap-2"><div class="type-dot" style="background:#3b82f6;"></div><span class="text-xs" style="color:var(--text);">运行中</span></div>
                <div class="flex items-center gap-2"><div class="type-dot" style="background:#22c55e;"></div><span class="text-xs" style="color:var(--text);">已完成</span></div>
                <div class="flex items-center gap-2"><div class="type-dot" style="background:#ef4444;"></div><span class="text-xs" style="color:var(--text);">执行失败</span></div>
                <div class="flex items-center gap-2"><div class="type-dot" style="background:#94a3b8;"></div><span class="text-xs" style="color:var(--text);">待执行</span></div>
            </div>
        </div>
    </div>

    <!-- ── GRAPH CANVAS ────────────────────────────────────────────── -->
    <div class="flex-1 relative overflow-hidden" id="graph-area">
        <svg id="wf-svg" style="width:100%;height:100%;display:block;"></svg>

        <!-- Node tooltip -->
        <div class="node-tooltip" id="node-tooltip"></div>

        <!-- Zoom controls (bottom-left) -->
        <div class="absolute bottom-4 left-4 flex flex-col gap-1 p-1.5 rounded-xl z-20"
             style="background:var(--pbg);border:1px solid var(--border);backdrop-filter:blur(20px);">
            <button onclick="zoomIn()" class="p-2 rounded-lg hover:bg-black/5 transition-colors" title="放大">
                <svg class="w-4 h-4" style="color:var(--text);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                </svg>
            </button>
            <button onclick="zoomOut()" class="p-2 rounded-lg hover:bg-black/5 transition-colors" title="缩小">
                <svg class="w-4 h-4" style="color:var(--text);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
                </svg>
            </button>
            <div style="height:1px;background:var(--border);margin:2px 0;"></div>
            <button onclick="fitView()" class="p-2 rounded-lg hover:bg-black/5 transition-colors" title="适应屏幕">
                <svg class="w-4 h-4" style="color:var(--text);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"/>
                </svg>
            </button>
            <button onclick="resetView()" class="p-2 rounded-lg hover:bg-black/5 transition-colors" title="重置视图">
                <svg class="w-4 h-4" style="color:var(--text);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
            </button>
        </div>

        <!-- Minimap (bottom-right) -->
        <div class="mini-map absolute bottom-4 right-16 z-20" id="minimap-wrap" style="width:160px;height:100px;">
            <svg id="minimap-svg" width="160" height="100" style="display:block;"></svg>
        </div>

        <!-- Layout direction indicator (top-right of canvas) -->
        <div class="absolute top-4 right-4 z-20 flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium"
             style="background:var(--pbg);border:1px solid var(--border);backdrop-filter:blur(16px);color:var(--muted);" id="dir-indicator">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" id="dir-icon">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"/>
            </svg>
            <span id="dir-label">{"垂直流向" if is_vertical else "水平流向"}</span>
        </div>
    </div>

    <!-- ── RESIZER ─────────────────────────────────────────────────── -->
    <div class="resizer" id="resizer"></div>

    <!-- ── RIGHT DETAIL PANEL ─────────────────────────────────────── -->
    <div id="detail-panel" style="width:380px;min-width:280px;max-width:580px;background:var(--pbg);border-left:1px solid var(--border);overflow-y:auto;">
        <!-- Panel header -->
        <div class="sticky top-0 z-10 flex items-center justify-between px-4 py-3"
             style="background:var(--pbg);border-bottom:1px solid var(--border);backdrop-filter:blur(20px);">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" style="color:var(--accent);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <h2 class="text-sm font-semibold" style="color:var(--text);">节点详情</h2>
            </div>
            <button onclick="closePanel()" class="p-1.5 rounded-lg transition-colors hover:bg-black/5">
                <svg class="w-4 h-4" style="color:var(--muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>

        <!-- Panel content (empty state) -->
        <div id="panel-content" class="p-4">
            <div class="flex flex-col items-center justify-center py-16 gap-3">
                <div class="w-14 h-14 rounded-2xl flex items-center justify-center" style="background:var(--surface2);">
                    <svg class="w-7 h-7" style="color:var(--muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5"/>
                    </svg>
                </div>
                <p class="text-sm" style="color:var(--muted);">点击节点查看详情</p>
                <p class="text-xs text-center" style="color:var(--muted);">耗时 · Token · 模型 · 输入输出<br>工具调用 · 引用文献</p>
            </div>
        </div>
    </div>
</div>

<!-- ═══════════════════════════════ BOTTOM TIMELINE ════════════════════════════ -->
<div class="fixed bottom-0 inset-x-0 z-50 px-5 py-3 flex items-center gap-5"
     style="background:var(--hbg);backdrop-filter:blur(20px);border-top:1px solid var(--border);height:54px;">
    <span class="text-xs font-semibold shrink-0" style="color:var(--muted);">执行进度</span>
    <!-- Timeline bar -->
    <div class="flex-1 relative h-2.5 rounded-full overflow-hidden flex gap-0.5" style="background:var(--surface2);" id="tl-container">
        <!-- Segments injected by JS -->
    </div>
    <span class="text-xs font-mono font-bold shrink-0" id="tl-pct" style="color:var(--accent);">0%</span>
    <span class="text-xs font-mono shrink-0" id="tl-time" style="color:var(--muted);">{total_ms_display}</span>
    <!-- Node dots on timeline -->
    <div class="flex items-center gap-3 shrink-0" id="tl-dots-wrap" style="max-width:300px;overflow:hidden;"></div>
</div>

<!-- ═══════════════════════════════ JAVASCRIPT ══════════════════════════════════ -->
<script>
const NODES = {nodes_json_esc};
const LINKS = {links_json_esc};
let currentTheme = "{theme_esc}";
let isVert = {str(is_vertical).lower()};
let currentFilter = {{type:"all", status:"all", search:""}};
let selId = null;
let fullscreenActive = false;

// ── Dimensions ────────────────────────────────────────────────────────────────
const NW = 158, NH = 70, PAD = 60;

// ── SVG Setup ─────────────────────────────────────────────────────────────────
const svg = d3.select("#wf-svg");
const mmSvg = d3.select("#minimap-svg");
const gW = () => document.getElementById("graph-area").clientWidth;
const gH = () => document.getElementById("graph-area").clientHeight;

const defs = svg.append("defs");
defs.append("filter").attr("id","drop-shadow")
    .append("feDropShadow").attr("dx",0).attr("dy",3).attr("stdDeviation",5).attr("flood-opacity",0.12);
defs.append("filter").attr("id","glow-filter")
    .append("feGaussianBlur").attr("stdDeviation","3").attr("result","coloredBlur");
const glowMerge = defs.select("#glow-filter").append("feMerge");
glowMerge.append("feMergeNode").attr("in","coloredBlur");
glowMerge.append("feMergeNode").attr("in","SourceGraphic");

// Glass gradient (top-to-bottom white fade)
const glassGrad = defs.append("linearGradient").attr("id","glass-grad")
    .attr("x1","0%").attr("y1","0%").attr("x2","0%").attr("y2","100%");
glassGrad.append("stop").attr("offset","0%").attr("stop-color","rgba(255,255,255,0.18)").attr("stop-opacity","1");
glassGrad.append("stop").attr("offset","55%").attr("stop-color","rgba(255,255,255,0.04)").attr("stop-opacity","1");
glassGrad.append("stop").attr("offset","100%").attr("stop-color","rgba(255,255,255,0.00)").attr("stop-opacity","1");

// Arrow marker
defs.append("marker").attr("id","arr")
    .attr("viewBox","0 -5 10 10").attr("refX",7).attr("refY",0)
    .attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto")
    .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","var(--border)");

// Animated flow marker
defs.append("marker").attr("id","arr-active")
    .attr("viewBox","0 -5 10 10").attr("refX",7).attr("refY",0)
    .attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto")
    .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","var(--accent)");

const zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", e => {{ g.attr("transform", e.transform); updateMinimap(); }});
svg.call(zoom);
const g = svg.append("g");

// ── Helpers ───────────────────────────────────────────────────────────────────
function progressArc(d) {{
    const r = 14, cx = 24, cy = 56;
    const frac = Math.min((d.duration_ms || 0) / Math.max(d.duration_ms || 1, 1), 1);
    if (frac <= 0) return `M ${cx},${cy} m 0,0`;
    const a = frac * 2 * Math.PI;
    return `M ${cx},${cy} L ${cx + r * Math.sin(a)},${cy - r * Math.cos(a)}`;
}}

function statusLabel(s) {{
    const map = {{"":"待执行","pending":"待执行","running":"运行中","approved":"已批准","completed":"已完成","error":"失败","max_iterations":"达到上限"}};
    return map[s] || s || "待执行";
}}

// ── Layout Computation ────────────────────────────────────────────────────────
function computeLayout() {{
    const agents = NODES.filter(n => n.type !== "input" && n.type !== "output");
    const agentCount = agents.length;
    if (agentCount === 0) return;

    if (!isVert) {{
        // Horizontal: single row
        agents.forEach((n, i) => {{
            n.x = PAD + (i + 1) * (gW() - 2 * PAD) / (agentCount + 1);
            n.y = gH() / 2;
        }});
    }} else {{
        // Vertical: single column
        const totalH = agentCount * (NH + 30);
        const startY = (gH() - totalH) / 2 + NH / 2;
        agents.forEach((n, i) => {{
            n.x = gW() / 2;
            n.y = startY + i * (NH + 30);
        }});
    }}

    // Input/output fixed
    const inp = NODES.find(n => n.type === "input");
    const out = NODES.find(n => n.type === "output");
    if (inp) {{ inp.x = PAD; inp.y = gH() / 2; }}
    if (out) {{
        out.x = isVert ? gW() / 2 : gW() - PAD;
        out.y = isVert ? gH() - PAD : gH() / 2;
    }}
}}
computeLayout();

// ── Draw Edges ────────────────────────────────────────────────────────────────
const edgeG = g.append("g").attr("class", "edges");
LINKS.forEach(l => {{
    const s = NODES.find(n => n.id === l.source), t = NODES.find(n => n.id === l.target);
    if (!s || !t) return;

    let d;
    if (!isVert) {{
        const mx = (s.x + t.x) / 2;
        d = `M${{s.x}},${{s.y}} C${{mx}},${{s.y}} ${{mx}},${{t.y}} ${{t.x}},${{t.y}}`;
    }} else {{
        const my = (s.y + t.y) / 2;
        d = `M${{s.x}},${{s.y}} C${{s.x}},${{my}} ${{t.x}},${{my}} ${{t.x}},${{t.y}}`;
    }}

    const ep = edgeG.append("path").attr("class", "link-edge")
        .attr("d", d).attr("stroke", l.color || "var(--border)")
        .attr("stroke-width", l.style === "dashed" ? 1.5 : 2)
        .attr("stroke-dasharray", l.style === "dashed" ? "6,4" : "8,5")
        .attr("marker-end", "url(#arr)")
        .attr("data-from", l.source).attr("data-to", l.target);
    // Animated flowing dots along edge
    ep.append("animate")
        .attr("attributeName", "stroke-dashoffset")
        .attr("from", "0").attr("to", "-26")
        .attr("dur", "1.2s").attr("repeatCount", "indefinite")
        .attr("fill", "freeze");
}});

// ── Draw Nodes ────────────────────────────────────────────────────────────────
const nodeG = g.append("g").attr("class", "nodes");
const els = nodeG.selectAll(".node-grp").data(NODES).enter()
    .append("g").attr("class", "node-grp")
    .attr("transform", d => `translate(${{d.x - NW/2}},${{d.y - NH/2}})`)
    .attr("data-id", d => d.id)
    .style("animation-delay", (d, i) => `${{i * 40}}ms`)
    .on("click", (e, d) => selectNode(d))
    .on("mouseenter", (e, d) => showTooltip(e, d))
    .on("mouseleave", hideTooltip);

// Glassmorphism: outer status glow ring
els.append("rect").attr("width", NW + 10).attr("height", NH + 10)
    .attr("x", -5).attr("y", -5).attr("rx", 19).attr("fill", "none")
    .attr("stroke", d => statusColor(d.status)).attr("stroke-width", 2.5)
    .attr("opacity", d => d.status === "pending" ? 0.25 : 0.9)
    .attr("filter", "url(#drop-shadow)");

// Card shadow
els.append("rect").attr("class", "node-card").attr("width", NW).attr("height", NH)
    .attr("rx", 14).attr("fill", d => d.color).attr("filter", "url(#drop-shadow)");

// Glass overlay (top-half gradient for depth)
els.append("rect").attr("width", NW).attr("height", NH)
    .attr("rx", 14).attr("fill", "url(#glass-grad)").attr("pointer-events", "none");

// Icon
els.append("text").attr("x", 14).attr("y", 26).attr("font-size", "18px").text(d => typeIcon(d.type));

// Label
els.append("text").attr("x", 42).attr("y", 19).attr("text-anchor", "start")
    .attr("font-size", "12px").attr("font-weight", "700").attr("fill", "white")
    .text(d => d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label);

// Node ID subtitle
els.append("text").attr("x", 42).attr("y", 34).attr("text-anchor", "start")
    .attr("font-size", "8.5px").attr("fill", "rgba(255,255,255,0.55)")
    .text(d => d.id.length > 16 ? d.id.slice(0, 15) + "…" : d.id);

// Status badge (top-right pill)
els.append("rect").attr("x", NW - 56).attr("y", 3).attr("width", 48).attr("height", 16).attr("rx", 8)
    .attr("fill", d => statusColor(d.status)).attr("opacity", 0.9);
els.append("text").attr("x", NW - 32).attr("y", 14).attr("text-anchor", "middle")
    .attr("font-size", "8px").attr("font-weight", "600").attr("fill", "white")
    .text(d => statusLabel(d.status));

// Running: animated pulse ring
els.filter(d => d.status === "\u8fd0\u884c\u4e2d")
    .append("circle").attr("cx", NW/2).attr("cy", NH/2).attr("r", NH/2 + 6)
    .attr("fill", "none").attr("stroke", "rgba(255,255,255,0.45)").attr("stroke-width", 2)
    .attr("class", "pulse-ring");

// Duration (bottom center)
els.append("text").attr("x", NW/2).attr("y", NH - 12).attr("text-anchor", "middle")
    .attr("font-size", "9.5px").attr("font-family", "'JetBrains Mono',monospace")
    .attr("fill", "rgba(255,255,255,0.92)").text(d => d.duration_str || "\u2013");

// Token badge (bottom-left)
els.filter(d => d.tokens_used > 0)
    .append("rect").attr("x", 5).attr("y", NH - 23).attr("width", 48).attr("height", 15).attr("rx", 8)
        .attr("fill", "rgba(0,0,0,0.28)");
els.filter(d => d.tokens_used > 0)
    .append("text").attr("x", 29).attr("y", NH - 12).attr("text-anchor", "middle")
        .attr("font-size", "8.5px").attr("font-family", "'JetBrains Mono',monospace")
        .attr("fill", "rgba(255,255,255,0.82)").text(d => d.tokens_str);

// LLM model badge (top-left)
els.filter(d => d.model)
    .append("rect").attr("x", 4).attr("y", 3).attr("width", 62).attr("height", 16).attr("rx", 8)
        .attr("fill", "rgba(0,0,0,0.28)");
els.filter(d => d.model)
    .append("text").attr("x", 35).attr("y", 14).attr("text-anchor", "middle")
        .attr("font-size", "7.5px").attr("font-family", "'JetBrains Mono',monospace")
        .attr("fill", "rgba(255,255,255,0.7)").text(d => (d.model || "").slice(0, 7));attr("fill", "rgba(255,255,255,0.75)").text(d => (d.model || "").slice(0, 8));

// ── Minimap ───────────────────────────────────────────────────────────────────
function updateMinimap() {{
    const vx = parseFloat(g.attr("transform").match(/translate\\\\(([^,]+)/)?.[1] || 0);
    const vy = parseFloat(g.attr("transform").match(/,\\\\s*([^)]+)/)?.[1] || 0);
    const scale = parseFloat(g.attr("transform").match(/scale\\\\(([^)]+)\\\\)/)?.[1] || 1);

    mmSvg.selectAll("*").remove();
    mmSvg.append("rect").attr("width", 160).attr("height", 100).attr("fill", "var(--surface2)");

    const mmScale = 0.18;
    const mmG = mmSvg.append("g").attr("transform", `scale(${{mmScale}})`);

    // Mini edges
    LINKS.forEach(l => {{
        const s = NODES.find(n => n.id === l.source), t = NODES.find(n => n.id === l.target);
        if (!s || !t) return;
        mmG.append("line")
            .attr("x1", s.x).attr("y1", s.y).attr("x2", t.x).attr("y2", t.y)
            .attr("stroke", l.color || "var(--border)").attr("stroke-width", 3).attr("class", "mini-node");
    }});

    // Mini nodes
    mmG.selectAll(".mini-node").data(NODES).enter().append("rect")
        .attr("x", d => d.x - 10).attr("y", d => d.y - 5)
        .attr("width", 20).attr("height", 10).attr("rx", 4)
        .attr("fill", d => d.color).attr("class", "mini-node");

    // Viewport indicator
    const vpX = -vx / scale * mmScale;
    const vpY = -vy / scale * mmScale;
    const vpW = gW() / scale * mmScale;
    const vpH = gH() / scale * mmScale;
    mmSvg.append("rect")
        .attr("x", vpX).attr("y", vpY).attr("width", vpW).attr("height", vpH)
        .attr("fill", "none").attr("stroke", "var(--accent)").attr("stroke-width", 2 / mmScale)
        .attr("stroke-dasharray", `${4/mmScale},${2/mmScale}`)
        .attr("rx", 2 / mmScale);
}}
updateMinimap();

// ── Sidebar Population ────────────────────────────────────────────────────────
const typeCounts = {{}};
const statusCounts = {{}};
NODES.forEach(n => {{
    typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    statusCounts[n.status] = (statusCounts[n.status] || 0) + 1;
}});

const typeColorMap = {{}};
NODES.forEach(n => {{ if (!typeColorMap[n.type]) typeColorMap[n.type] = n.color; }});

const typeLabels = {{input:"输入",agent:"Agent",gate:"门控",output:"输出",tool:"工具",data:"数据"}};
const statusLabels = {{已完成:"已完成",执行失败:"执行失败",运行中:"运行中",待执行:"待执行","迭代超限":"迭代超限",等待中:"等待中"}};

Object.entries(typeCounts).forEach(([t, c]) => {{
    const el = document.createElement("div");
    el.className = "sidebar-item";
    el.dataset.filter = "type:" + t;
    el.innerHTML = `<div class="type-dot" style="background:${{typeColorMap[t]}};"></div>${{typeLabels[t]||t}}<span class="count">${{c}}</span>`;
    el.onclick = () => setFilter("type", t);
    document.getElementById("type-filters").appendChild(el);
}});

Object.entries(statusCounts).forEach(([s, c]) => {{
    const el = document.createElement("div");
    el.className = "sidebar-item";
    el.dataset.filter = "status:" + s;
    el.innerHTML = `<div class="type-dot" style="background:${{statusColor(s)}};"></div>${{statusLabels[s]||s}}<span class="count">${{c}}</span>`;
    el.onclick = () => setFilter("status", s);
    document.getElementById("status-filters").appendChild(el);
}});

// ── Filter Logic ─────────────────────────────────────────────────────────────
function setFilter(kind, value) {{
    currentFilter.type = kind === "type" ? value : "all";
    currentFilter.status = kind === "status" ? value : "all";
    document.querySelectorAll(".sidebar-item").forEach(el => el.classList.remove("active"));
    if (kind === "type") document.querySelector(`[data-filter="type:${{value}}"]`)?.classList.add("active");
    else if (kind === "status") document.querySelector(`[data-filter="status:${{value}}"]`)?.classList.add("active");
    else document.getElementById("filter-all")?.classList.add("active");
    applyFilter();
}}

function filterNodes(q) {{
    currentFilter.search = q.toLowerCase();
    applyFilter();
}}

function applyFilter() {{
    const q = currentFilter.search;
    NODES.forEach(n => {{
        const el = nodeG.select(`[data-id="${{n.id}}"]`);
        const matchType = currentFilter.type === "all" || n.type === currentFilter.type;
        const matchStatus = currentFilter.status === "all" || n.status === currentFilter.status;
        const matchSearch = !q || n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q);
        el.classed("dimmed", !(matchType && matchStatus && matchSearch));
    }});
}}

// ── Node Selection ───────────────────────────────────────────────────────────
function selectNode(d) {{
    selId = d.id;
    els.classed("selected", n => n.id === d.id);
    // Highlight connected edges
    d3.selectAll(".link-edge")
        .classed("active", l => l.source === d.id || l.target === d.id)
        .attr("marker-end", l => (l.source === d.id || l.target === d.id) ? "url(#arr-active)" : "url(#arr)");
    document.getElementById("panel-content").innerHTML = buildDetail(d);
    updateGlobalStatus();
}}

function showTooltip(e, d) {{
    const tip = document.getElementById("node-tooltip");
    const labels = {{已完成:"✓ 已完成",执行失败:"✗ 执行失败",运行中:"◌ 运行中",待执行:"○ 待执行","迭代超限":"⚠ 迭代超限"}};
    tip.innerHTML = `<b style="color:var(--text);">${{d.label}}</b> · ${{labels[d.status]||d.status}}${{d.duration_str ? " · " + d.duration_str : ""}}`;
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top = (e.clientY - 36) + "px";
    tip.classList.add("visible");
}}
function hideTooltip() {{
    document.getElementById("node-tooltip").classList.remove("visible");
}}

// ── Detail Panel Builder ─────────────────────────────────────────────────────
function buildDetail(d) {{
    let h = `<div class="fade-up space-y-3">`;

    // Header card
    h += `<div class="detail-section" style="background:linear-gradient(135deg, ${{d.color}}18, ${{d.color}}05);border-color:${{d.color}}40;">
        <div class="flex items-start gap-3 mb-3">
            <div class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0" style="background:${{d.color}};box-shadow:0 4px 12px ${{d.color}}40;">
                ${{typeIcon(d.type)}}
            </div>
            <div class="flex-1 min-w-0">
                <h3 class="text-sm font-bold truncate" style="color:var(--text);">${{d.label}}</h3>
                <p class="text-xs mt-0.5" style="color:var(--muted);">${{typeLabels[d.type]||d.type}} · ${{d.id}}</p>
            </div>
            <span class="badge ${{badgeCls(d.status)}}">${{statusLabels[d.status]||d.status}}</span>
        </div>
    </div>`;

    // Metrics
    h += `<div class="grid grid-cols-2 gap-2">`;
    h += `<div class="detail-section"><div class="text-xs mb-1" style="color:var(--muted);">耗时</div><div class="text-lg font-bold font-mono" style="color:var(--text);">${{d.duration_str||"–"}}</div></div>`;
    h += `<div class="detail-section"><div class="text-xs mb-1" style="color:var(--muted);">Token</div><div class="text-lg font-bold font-mono" style="color:var(--text);">${{d.tokens_str||"–"}}</div></div>`;
    if (d.iterations > 0) h += `<div class="detail-section"><div class="text-xs mb-1" style="color:var(--muted);">迭代次数</div><div class="text-lg font-bold" style="color:var(--text);">${{d.iterations}}</div></div>`;
    if (d.model) h += `<div class="detail-section col-span-2"><div class="text-xs mb-1" style="color:var(--muted);">语言模型</div><div class="llm-badge">${{esc(d.model)}}</div></div>`;
    h += `</div>`;

    // Error
    if (d.error) h += `<div class="detail-section" style="background:#fee2e2;border-color:#fecaca;"><div class="text-xs font-semibold mb-1" style="color:#991b1b;">错误信息</div><div class="code-block text-red-800">${{esc(d.error)}}</div></div>`;

    // Input
    if (d.input_preview) h += `<div>
        <div class="flex items-center gap-1.5 mb-1.5"><svg class="w-3.5 h-3.5" style="color:var(--accent);" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg><span class="text-xs font-semibold" style="color:var(--muted);">输入内容预览</span></div>
        <div class="code-block">${{esc(d.input_preview)}}</div></div>`;

    // Output
    if (d.output_preview) h += `<div>
        <div class="flex items-center gap-1.5 mb-1.5"><svg class="w-3.5 h-3.5" style="color:var(--accent);" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg><span class="text-xs font-semibold" style="color:var(--muted);">输出内容预览</span></div>
        <div class="code-block">${{esc(d.output_preview)}}</div></div>`;

    // Tools
    if (d.tools_called && d.tools_called.length) {{
        h += `<div>
            <div class="flex items-center gap-1.5 mb-1.5"><svg class="w-3.5 h-3.5" style="color:var(--accent);" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg><span class="text-xs font-semibold" style="color:var(--muted);">工具调用 (${{d.tools_called.length}})</span></div>
            <div class="flex flex-wrap gap-1.5">`;
        d.tools_called.forEach(t => {{
            const name = typeof t === "string" ? t : (t.name || t.tool || JSON.stringify(t));
            h += `<span class="inline-flex items-center px-2 py-1 rounded text-xs font-mono" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);">${{esc(name)}}</span>`;
        }});
        h += `</div></div>`;
    }}

    // Citations
    if (d.citations && d.citations.length) {{
        h += `<div>
            <div class="flex items-center gap-1.5 mb-1.5"><svg class="w-3.5 h-3.5" style="color:var(--accent);" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg><span class="text-xs font-semibold" style="color:var(--muted);">引用文献 (${{d.citations.length}})</span></div>
            <div class="space-y-1.5">`;
        d.citations.forEach(c => {{
            const text = typeof c === "string" ? c : (c.title || c.id || c.author || JSON.stringify(c).slice(0, 80));
            h += `<div class="text-xs rounded p-2.5" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);line-height:1.5;">${{esc(text)}}</div>`;
        }});
        h += `</div></div>`;
    }}

    h += `</div>`;
    return h;
}}

// ── Status Helpers ───────────────────────────────────────────────────────────
function typeIcon(t) {{return {{input:"📥",agent:"🤖",gate:"🚦",output:"📤",tool:"🔧",data:"📊"}}[t]||"⚙️";}}
function statusColor(s) {{return {{已完成:"#22c55e",执行失败:"#ef4444",运行中:"#3b82f6","迭代超限":"#eab308",待执行:"#94a3b8",等待中:"#f59e0b"}}[s]||"#94a3b8";}}
function badgeCls(s) {{return {{已完成:"badge-success",执行失败:"badge-error",运行中:"badge-running","迭代超限":"badge-warn",待执行:"badge-pending",等待中:"badge-pending"}}[s]||"badge-pending";}}
function esc(s) {{return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}}

// ── Global Status Update ─────────────────────────────────────────────────────
function updateGlobalStatus() {{
    const done = NODES.filter(n => n.status === "已完成").length;
    const err = NODES.filter(n => n.status === "执行失败").length;
    const run = NODES.filter(n => n.status === "运行中").length;
    const total = NODES.length;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;

    document.getElementById("s-done").textContent = `${{done}}/${{total}}`;
    document.getElementById("s-err").textContent = err;

    const dot = document.getElementById("h-dot");
    const txt = document.getElementById("h-status");
    const pb = document.getElementById("tl-container");

    if (err > 0) {{ dot.style.background = "#ef4444"; txt.textContent = `${{err}}个错误`; }}
    else if (run > 0) {{ dot.style.background = "#3b82f6"; txt.textContent = `运行中 ${{run}}个`; }}
    else if (done === total && total > 0) {{ dot.style.background = "#22c55e"; txt.textContent = "全部完成 ✓"; }}
    else {{ dot.style.background = "#94a3b8"; txt.textContent = "就绪"; }}

    updateTimeline();
}}

// ── Timeline Bar ──────────────────────────────────────────────────────────────
function updateTimeline() {{
    const totalMs = NODES.reduce((s, n) => s + (n.duration_ms || 0), 0) || 1;
    const doneMs = NODES.filter(n => n.status !== "待执行").reduce((s, n) => s + (n.duration_ms || 0), 0);
    const pct = Math.round(doneMs / totalMs * 100);

    document.getElementById("tl-pct").textContent = pct + "%";

    const container = document.getElementById("tl-container");
    container.innerHTML = "";
    NODES.forEach(n => {{
        const w = ((n.duration_ms || 0) / totalMs * 100).toFixed(2) + "%";
        const div = document.createElement("div");
        div.className = "tl-segment";
        div.style.width = w;
        div.style.background = n.status === "已完成" ? "#22c55e" : n.status === "执行失败" ? "#ef4444" : n.status === "运行中" ? "var(--accent)" : "#334155";
        div.style.flexShrink = "0";
        div.title = `${{n.label}}: ${{n.duration_str || "–"}}`;
        container.appendChild(div);
    }});

    // Dots row
    const dotsWrap = document.getElementById("tl-dots-wrap");
    dotsWrap.innerHTML = "";
    NODES.filter(n => n.duration_ms > 0).slice(-8).forEach(n => {{
        const dot = document.createElement("div");
        dot.className = "w-2 h-2 rounded-full border border-white flex-shrink-0";
        dot.style.background = statusColor(n.status);
        dot.title = `${{n.label}}`;
        dotsWrap.appendChild(dot);
    }});
}}

// ── Controls ─────────────────────────────────────────────────────────────────
function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.3); }}
function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.7); }}
function resetView() {{
    const cx = gW() / 2, cy = gH() / 2;
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(cx, cy).scale(0.9));
}}

function fitView() {{
    const pad = 60;
    const x0 = d3.min(NODES, d => d.x - NW/2) - pad, x1 = d3.max(NODES, d => d.x + NW/2) + pad;
    const y0 = d3.min(NODES, d => d.y - NH/2) - pad, y1 = d3.max(NODES, d => d.y + NH/2) + pad;
    const bw = x1 - x0, bh = y1 - y0;
    const s = Math.min(gW() / bw, gH() / bh, 1.1);
    const tx = (gW() - bw * s) / 2 - x0 * s, ty = (gH() - bh * s) / 2 - y0 * s;
    svg.transition().duration(700).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(s));
}}

function toggleFullscreen() {{
    if (!document.fullscreenElement) {{
        document.documentElement.requestFullscreen();
        fullscreenActive = true;
    }} else {{
        document.exitFullscreen();
        fullscreenActive = false;
    }}
}}

function toggleLayout() {{
    isVert = !isVert;
    document.getElementById("layout-label").textContent = isVert ? "垂直" : "水平";
    document.getElementById("dir-label").textContent = isVert ? "垂直流向" : "水平流向";
    document.getElementById("dir-icon").setAttribute("d", isVert
        ? "M5 12h14M12 5l7 7-7 7"
        : "M12 5v14M5 12l7 7 7-7");
    computeLayout();
    // Redraw edges
    edgeG.selectAll("*").remove();
    LINKS.forEach(l => {{
        const s = NODES.find(n => n.id === l.source), t = NODES.find(n => n.id === l.target);
        if (!s || !t) return;
        let d;
        if (!isVert) {{
            const mx = (s.x + t.x) / 2;
            d = `M${{s.x}},${{s.y}} C${{mx}},${{s.y}} ${{mx}},${{t.y}} ${{t.x}},${{t.y}}`;
        }} else {{
            const my = (s.y + t.y) / 2;
            d = `M${{s.x}},${{s.y}} C${{s.x}},${{my}} ${{t.x}},${{my}} ${{t.x}},${{t.y}}`;
        }}
        edgeG.append("path").attr("class", "link-edge")
            .attr("d", d).attr("stroke", l.color || "var(--border)")
            .attr("stroke-width", 2)
            .attr("marker-end", "url(#arr)");
    }});
    // Redraw nodes
    els.transition().duration(400).attr("transform", d => `translate(${{d.x - NW/2}},${{d.y - NH/2}})`);
    updateMinimap();
}}

function toggleTheme() {{
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    const t = currentTheme === "dark";
    const r = document.documentElement;
    r.style.setProperty("--bg", t ? "#0f172a" : "#f8fafc");
    r.style.setProperty("--surface", t ? "#1e293b" : "#ffffff");
    r.style.setProperty("--surface2", t ? "#334155" : "#f1f5f9");
    r.style.setProperty("--border", t ? "#475569" : "#e2e8f0");
    r.style.setProperty("--text", t ? "#f1f5f9" : "#0f172a");
    r.style.setProperty("--muted", t ? "#94a3b8" : "#64748b");
    r.style.setProperty("--accent", t ? "#6366f1" : "#4f46e5");
    r.style.setProperty("--accent2", t ? "#818cf8" : "#6366f1");
    r.style.setProperty("--hbg", t ? "rgba(15,23,42,0.92)" : "rgba(255,255,255,0.92)");
    r.style.setProperty("--pbg", t ? "rgba(30,41,59,0.98)" : "rgba(255,255,255,0.98)");
    r.style.setProperty("--glow", t ? "rgba(99,102,241,0.3)" : "rgba(79,70,229,0.15)");
    document.getElementById("theme-icon").innerHTML = t
        ? `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>`
        : `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>`;
}}

function exportSVG() {{
    const ser = new XMLSerializer();
    const src = ser.serializeToString(document.getElementById("wf-svg"));
    const blob = new Blob([src], {{type:"image/svg+xml;charset=utf-8"}});
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "workflow.svg"; a.click();
    URL.revokeObjectURL(a.href);
}}

function closePanel() {{
    selId = null;
    els.classed("selected", false);
    d3.selectAll(".link-edge").classed("active", false).attr("marker-end", "url(#arr)");
    document.getElementById("panel-content").innerHTML = `
        <div class="flex flex-col items-center justify-center py-16 gap-3">
            <div class="w-14 h-14 rounded-2xl flex items-center justify-center" style="background:var(--surface2);">
                <svg class="w-7 h-7" style="color:var(--muted);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5"/>
                </svg>
            </div>
            <p class="text-sm" style="color:var(--muted);">点击节点查看详情</p>
            <p class="text-xs text-center" style="color:var(--muted);">耗时 · Token · 模型 · 输入输出<br>工具调用 · 引用文献</p>
        </div>`;
}}

// ── Panel Resizer ────────────────────────────────────────────────────────────
(function() {{
    const resizer = document.getElementById("resizer");
    const panel = document.getElementById("detail-panel");
    let rz = false;
    resizer.addEventListener("mousedown", e => {{
        rz = true; resizer.classList.add("active");
        document.addEventListener("mousemove", onRz);
        document.addEventListener("mouseup", () => {{
            rz = false; resizer.classList.remove("active");
            document.removeEventListener("mousemove", onRz);
        }}, {{ once: true }});
    }});
    function onRz(e) {{
        if (!rz) return;
        panel.style.width = Math.max(260, Math.min(560, document.body.clientWidth - e.clientX)) + "px";
    }}
}})();

// ── Public API for external updates ──────────────────────────────────────────
window.updateNodeStatus = function(nodeId, status, extra) {{
    const node = NODES.find(n => n.id === nodeId);
    if (!node) return;
    node.status = status;
    if (extra) Object.assign(node, extra);
    els.filter(d => d.id === nodeId)
        .select("circle").attr("fill", statusColor(status));
    if (nodeId === selId)
        document.getElementById("panel-content").innerHTML = buildDetail(node);
    updateGlobalStatus();
    updateTimeline();
}};

// ── External poll: read status from localStorage ──────────────────────────────
let pollCount = 0;
setInterval(() => {{
    pollCount++;
    try {{
        const raw = localStorage.getItem("wf_status_updates");
        if (raw) {{
            const updates = JSON.parse(raw);
            Object.entries(updates).forEach(([id, data]) => updateNodeStatus(id, data.status, data));
            if (pollCount % 5 === 0) localStorage.removeItem("wf_status_updates");
        }}
    }} catch(e) {{}}
}}, 2500);

// ── Init ──────────────────────────────────────────────────────────────────────
setTimeout(() => {{
    fitView();
    updateGlobalStatus();
    updateTimeline();
    // Apply default filter
    document.getElementById("filter-all")?.classList.add("active");
}}, 400);
</script>
</body>
</html>'''

        path.write_text(html, encoding="utf-8")
        return path


# ─── EnhancedChart: Provenance-aware matplotlib wrapper ─────────────────────────


class EnhancedChart:
    """A matplotlib chart wrapper that integrates with ProvenanceTracker.

    Wraps a matplotlib Figure/Axes pair with data provenance tracking,
    LaTeX provenance comments, and Mermaid lineage generation.
    """

    def __init__(
        self,
        fig,
        ax,
        title: str,
        data_provenance: list[str] | None = None,
        chart_type: str = "generic",
        figure_number: str | None = None,
        source_notes: str | None = None,
    ):
        self.fig = fig
        self.ax = ax
        self.title = title
        self.chart_type = chart_type
        self.figure_number = figure_number
        self.source_notes = source_notes or ""
        self.data_provenance = data_provenance or []

    def get_latex_provenance_comment(self) -> str:
        """Generate LaTeX ``\\provenance{}`` comment for embedding in figure caption."""
        parts = []
        fig_label = f"Figure {self.figure_number or '?'}: {self.title}"
        parts.append(f"% \\provenance{{chart}}{{{fig_label}}}{{{self.chart_type}}}")

        if self.data_provenance:
            parts.append(f"% Data sources:")
            for src in self.data_provenance:
                parts.append(f"%   - {src}")

        if self.source_notes:
            parts.append(f"% Notes: {self.source_notes}")

        return "\n".join(parts)

    def get_mermaid_lineage(self) -> str:
        """Generate Mermaid flowchart for embedding in LaTeX."""
        lines = ["```mermaid", "flowchart LR"]

        node_id_map = {}
        for i, src in enumerate(self.data_provenance):
            node_id = f"D{i}"
            node_id_map[src] = node_id
            label = src if len(src) <= 30 else src[:27] + "..."
            lines.append(f'    {node_id}["📊 {label}"]')

        fig_id = "CHART"
        fig_label = self.title if len(self.title) <= 30 else self.title[:27] + "..."
        lines.append(f'    {fig_id}["📈 {fig_label}"]')

        for src, node_id in node_id_map.items():
            lines.append(f"    {node_id} --> {fig_id}")

        lines.append("```")
        return "\n".join(lines)

    def save_with_provenance(
        self,
        path: Path | str,
        dpi: int = 300,
        metadata: dict | None = None,
    ) -> None:
        """Save figure with provenance metadata embedded.

        Saves the figure and a sidecar ``.provenance.json`` file.
        """
        import json as _json

        path = Path(path)
        self.fig.savefig(path, dpi=dpi, bbox_inches="tight")

        prov_data = {
            "title": self.title,
            "chart_type": self.chart_type,
            "figure_number": self.figure_number,
            "source_notes": self.source_notes,
            "data_provenance": self.data_provenance,
            "latex_comment": self.get_latex_provenance_comment(),
            "mermaid": self.get_mermaid_lineage(),
        }
        if metadata:
            prov_data["metadata"] = metadata

        sidecar = path.with_suffix(path.suffix + ".provenance.json")
        sidecar.write_text(_json.dumps(prov_data, indent=2, ensure_ascii=False), encoding="utf-8")

    def to_dict(self) -> dict:
        """Serialize to dict for JSON export."""
        return {
            "title": self.title,
            "chart_type": self.chart_type,
            "figure_number": self.figure_number,
            "source_notes": self.source_notes,
            "data_provenance": self.data_provenance,
            "latex_comment": self.get_latex_provenance_comment(),
            "mermaid": self.get_mermaid_lineage(),
        }


def create_tracked_chart(
    fig,
    ax,
    title: str,
    data_sources: list[str],
    tracker=None,
    chart_type: str = "generic",
    figure_number: str | None = None,
) -> EnhancedChart:
    """Create an EnhancedChart and optionally register it with ProvenanceTracker.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The matplotlib Figure object.
    ax : matplotlib.axes.Axes
        The matplotlib Axes object.
    title : str
        Chart title.
    data_sources : list[str]
        List of data source identifiers (e.g. ["tushare_daily", "macro_gdp"]).
    tracker : ProvenanceTracker | None
        Tracker instance to register with. If None, tries to get the global tracker.
    chart_type : str
        Chart type (e.g. "line", "bar", "scatter").
    figure_number : str | None
        Figure number label (e.g. "1", "2a").

    Returns
    -------
    EnhancedChart
    """
    import uuid

    from scripts.core.provenance import ProvenanceTracker, get_tracker

    chart_id = f"chart_{uuid.uuid4().hex[:8]}"

    if tracker is None:
        try:
            tracker = get_tracker()
        except RuntimeError:
            tracker = None

    if tracker is not None:
        # Only register if at least one referenced data source exists
        # Guard against trackers where nodes attribute was not initialized
        node_ids = getattr(tracker, "nodes", {}) or {}
        refs = [s for s in data_sources if s in node_ids]
        if refs:
            tracker.register_chart(
                metadata=chart_id,  # register_chart signature: (metadata, data_node_id, tracker=None)
                data_node_id=refs[0],
            )

    return EnhancedChart(
        fig=fig,
        ax=ax,
        title=title,
        data_provenance=data_sources,
        chart_type=chart_type,
        figure_number=figure_number,
    )
