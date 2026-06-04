"""
Visual Graph Editor for Agent Pipeline Construction.

Provides a programmatic interface for building, visualizing, and editing
agent pipelines as directed acyclic graphs (DAGs).

Features:
- Build pipeline from Python DSL
- Visualize pipeline as graph (matplotlib + NetworkX)
- Export pipeline as YAML (for agents.yaml)
- Validate pipeline DAG (no cycles, all dependencies satisfied)
- Generate Canvas-compatible output for Cursor canvases

This is a CODE-BASED visual builder — it provides the programmatic foundation
for constructing and visualizing pipeline graphs without requiring a full web UI.

Usage:
    # Build a pipeline programmatically
    builder = PipelineBuilder("paper_pipeline")
    builder.add_agent("outline", "OutlineAgent").then("literature", "LiteratureReviewAgent")
    builder.with_hitl("literature").then("plotting", "PlottingAgent")
    builder.add_agent("writing", "SectionWritingAgent").add_agent("refinement", "RefinementAgent")
    graph = builder.build()
    graph.visualize()              # Show in matplotlib window
    graph.visualize("pipeline.png") # Save to file

    # Export to agents.yaml format
    yaml_dict = graph.to_yaml_dict()
    with open("config/agents.yaml", "w") as f:
        yaml.dump(yaml_dict, f)

    # Load from existing agents.yaml
    graph = PipelineGraph.from_agents_yaml("config/agents.yaml")
    graph.validate()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "NodeType",
    "PipelineNode",
    "PipelineEdge",
    "PipelineGraph",
    "PipelineBuilder",
]

# ── Optional visualization dependencies ────────────────────────────────────────
try:
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import networkx as nx

    _HAS_VISUAL = True
except ImportError:
    _HAS_VISUAL = False
    nx = None  # type: ignore


# ════════════════════════════════════════════════════════════════════════════════
# Data Models
# ════════════════════════════════════════════════════════════════════════════════


class NodeType(Enum):
    """Node types in a pipeline graph."""
    AGENT = "agent"       # A professional agent (e.g., OutlineAgent)
    GATE = "gate"         # HITL approval gate
    MERGE = "merge"       # Parallel branch merge point
    SPLIT = "split"       # Parallel branch split point
    INPUT = "input"       # Pipeline input
    OUTPUT = "output"     # Pipeline output


@dataclass
class PipelineNode:
    """
    A node in the pipeline graph.

    Attributes
    ----------
    id : str
        Unique identifier within the graph.
    node_type : NodeType
        Semantic role of the node.
    label : str
        Human-readable label for display.
    config : dict
        Arbitrary configuration (agent_name, hitl, etc.).
    position : tuple[float, float] | None
        Optional (x, y) position for fixed-layout visualization.
    """
    id: str
    node_type: NodeType
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    position: tuple[float, float] | None = None


@dataclass
class PipelineEdge:
    """
    A directed edge in the pipeline graph.

    Attributes
    ----------
    source : str
        ID of the source node.
    target : str
        ID of the target node.
    condition : str | None
        Optional condition for conditional edges (e.g., "if score > 7").
    """
    source: str
    target: str
    condition: str | None = None


# ════════════════════════════════════════════════════════════════════════════════
# PipelineGraph
# ════════════════════════════════════════════════════════════════════════════════


class PipelineGraph:
    """
    Directed acyclic graph (DAG) representing an agent pipeline.

    Supports validation, serialization, and visualization.

    Example
    -------
        graph = PipelineGraph(name="paper_pipeline")
        graph.add_node(PipelineNode("outline", NodeType.AGENT, "OutlineAgent"))
        graph.add_node(PipelineNode("literature", NodeType.AGENT, "LiteratureReviewAgent"))
        graph.add_edge("outline", "literature")
        graph.validate()
    """

    def __init__(self, name: str):
        self.name = name
        self.nodes: list[PipelineNode] = []
        self.edges: list[PipelineEdge] = []

    # ── Node/edge CRUD ────────────────────────────────────────────────────────

    def add_node(self, node: PipelineNode) -> None:
        """Add a node to the graph. Raises ValueError if id already exists."""
        if any(n.id == node.id for n in self.nodes):
            raise ValueError(f"Node with id '{node.id}' already exists in graph")
        self.nodes.append(node)

    def add_edge(self, source: str, target: str,
                 condition: str | None = None) -> None:
        """Add a directed edge. Validates that both nodes exist."""
        if not any(n.id == source for n in self.nodes):
            raise ValueError(f"Source node '{source}' does not exist")
        if not any(n.id == target for n in self.nodes):
            raise ValueError(f"Target node '{target}' does not exist")
        self.edges.append(PipelineEdge(source, target, condition))

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all connected edges."""
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [
            e for e in self.edges
            if e.source != node_id and e.target != node_id
        ]

    def get_node(self, node_id: str) -> PipelineNode | None:
        """Return node by id, or None if not found."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def successors(self, node_id: str) -> list[PipelineNode]:
        """Return all nodes directly downstream of node_id."""
        targets = {e.target for e in self.edges if e.source == node_id}
        return [n for n in self.nodes if n.id in targets]

    def predecessors(self, node_id: str) -> list[PipelineNode]:
        """Return all nodes directly upstream of node_id."""
        sources = {e.source for e in self.edges if e.target == node_id}
        return [n for n in self.nodes if n.id in sources]

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """
        Validate the graph for correctness.

        Checks:
        - No cycles (DAG requirement)
        - No unreachable nodes (except INPUT sources)
        - Nodes with no successors (except OUTPUT)
        - Multiple OUTPUT nodes

        Returns
        -------
        list[str]
            List of warning/error messages (empty if all checks pass).
        """
        warnings: list[str] = []

        if self._has_cycle():
            warnings.append("ERROR: Pipeline contains a cycle — not a valid DAG")

        # Check for unreachable nodes
        input_nodes = [n.id for n in self.nodes if n.node_type == NodeType.INPUT]
        if input_nodes:
            reachable = self._reachable_nodes(input_nodes[0])
            unreachable = [
                n.id for n in self.nodes
                if n.node_type != NodeType.INPUT and n.id not in reachable
            ]
            if unreachable:
                warnings.append(f"WARNING: Unreachable nodes: {unreachable}")

        # Check for dangling non-OUTPUT nodes
        output_ids = {n.id for n in self.nodes if n.node_type == NodeType.OUTPUT}
        dangling = [
            n.id for n in self.nodes
            if n.node_type not in {NodeType.OUTPUT, NodeType.GATE}
            and not any(e.source == n.id for e in self.edges)
        ]
        if dangling:
            warnings.append(f"WARNING: Nodes with no successors (dead ends): {dangling}")

        # Warn about multiple OUTPUT nodes
        output_nodes = [n for n in self.nodes if n.node_type == NodeType.OUTPUT]
        if len(output_nodes) > 1:
            warnings.append(
                f"WARNING: Multiple OUTPUT nodes found: "
                f"{[n.id for n in output_nodes]}"
            )

        if warnings:
            logger.warning("Pipeline validation issues: %s", warnings)
        else:
            logger.info("Pipeline '%s' passed validation", self.name)

        return warnings

    def _has_cycle(self) -> bool:
        """Detect cycles using depth-first search with recursion stack."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for edge in self.edges:
                if edge.source == node_id:
                    if edge.target in rec_stack:
                        return True
                    if edge.target not in visited:
                        if dfs(edge.target):
                            return True
            rec_stack.remove(node_id)
            return False

        for node in self.nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True
        return False

    def _reachable_nodes(self, start: str) -> set[str]:
        """Find all nodes reachable from start via DFS."""
        reachable: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            for edge in self.edges:
                if edge.source == node:
                    stack.append(edge.target)
        return reachable

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to a plain dict for JSON serialization."""
        return {
            "name": self.name,
            "nodes": [
                {
                    "id": n.id,
                    "type": n.node_type.value,
                    "label": n.label,
                    "config": n.config,
                    "position": n.position,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "condition": e.condition,
                }
                for e in self.edges
            ],
        }

    def to_json(self, path: str | Path | None = None) -> str:
        """Serialize graph as JSON, optionally saving to file."""
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        if path:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def to_yaml_dict(self) -> dict[str, Any]:
        """
        Convert to agents.yaml format.

        Generates a minimal YAML-compatible dict matching the agents.yaml schema:
            pipelines:
                <name>:
                    name: <name>
                    steps:
                        - agent: <agent_name>
                          stage: <stage_name>
                          hitl_gate: <bool>
        """
        steps = []
        for node in self.nodes:
            if node.node_type == NodeType.AGENT:
                steps.append({
                    "agent": node.config.get("agent_name", node.id),
                    "stage": node.id.upper(),
                    "hitl_gate": node.config.get("hitl", False),
                })
        return {
            "pipelines": {
                self.name: {
                    "name": self.name,
                    "steps": steps,
                }
            }
        }

    def to_markdown(self) -> str:
        """Generate a human-readable markdown table of the pipeline."""
        lines = [
            f"# Pipeline: {self.name}",
            "",
            "## Nodes",
            "",
            "| ID | Type | Label | Config |",
            "|---|---|---|---|",
        ]
        for n in self.nodes:
            config_str = ", ".join(f"{k}={v}" for k, v in n.config.items())
            lines.append(f"| `{n.id}` | {n.node_type.value} | {n.label} | {config_str} |")

        lines.extend(["", "## Edges", ""])
        for e in self.edges:
            cond = f" [{e.condition}]" if e.condition else ""
            lines.append(f"`{e.source}` ──{cond}──► `{e.target}`")

        return "\n".join(lines)

    # ── Visualization ────────────────────────────────────────────────────────

    def visualize(
        self,
        output_path: str | Path | None = None,
        figsize: tuple[int, int] = (14, 10),
        title: str | None = None,
    ) -> None:
        """
        Visualize the pipeline as a directed graph.

        Requires matplotlib and networkx.

        Parameters
        ----------
        output_path : str | Path | None
            If provided, save figure to this path. Otherwise display interactively.
        figsize : tuple[int, int]
            Figure size in inches (width, height).
        title : str | None
            Override the figure title. Defaults to the pipeline name.

        Example
        -------
            graph.visualize()                # Show in window
            graph.visualize("graph.png")    # Save to PNG
            graph.visualize("graph.pdf")    # Save to PDF
        """
        if not _HAS_VISUAL:
            logger.warning(
                "matplotlib or networkx not available. "
                "Install with: pip install matplotlib networkx"
            )
            return

        G = nx.DiGraph()
        for node in self.nodes:
            G.add_node(node.id, **node.config)
        for edge in self.edges:
            G.add_edge(edge.source, edge.target)

        fig, ax = plt.subplots(figsize=figsize)

        # Layout: use dot if available (requires pygraphviz), fall back to spring
        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except Exception:
            pos = nx.spring_layout(G, k=3, iterations=50, seed=42)

        # Color map by node type
        color_map: dict[NodeType, str] = {
            NodeType.AGENT:   "#4CAF50",  # Green
            NodeType.GATE:    "#FF9800",  # Orange
            NodeType.MERGE:   "#9C27B0",  # Purple
            NodeType.SPLIT:   "#E91E63",  # Pink
            NodeType.INPUT:   "#2196F3",  # Blue
            NodeType.OUTPUT:  "#607D8B",  # Grey
        }
        node_colors = [
            color_map.get(n.node_type, "#9E9E9E")
            for n in self.nodes
        ]

        nx.draw(
            G, pos, ax=ax,
            with_labels=True,
            node_color=node_colors,
            node_size=2200,
            font_size=8,
            font_weight="bold",
            arrows=True,
            arrowsize=18,
            edge_color="#666666",
            width=1.5,
            connectionstyle="arc3,rad=0.05",
        )

        # Legend
        legend_patches = [
            mpatches.Patch(color=c, label=t.value)
            for t, c in color_map.items()
        ]
        ax.legend(handles=legend_patches, loc="upper left", fontsize=8)

        ax.set_title(title or f"Pipeline: {self.name}", fontsize=14, fontweight="bold")
        ax.axis("off")

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()
            logger.info("Pipeline graph saved to %s", output_path)
        else:
            plt.tight_layout()
            plt.show()

    # ── Class Methods ────────────────────────────────────────────────────────

    @classmethod
    def from_agents_yaml(cls, yaml_path: str | Path) -> PipelineGraph:
        """
        Load a pipeline graph from an agents.yaml file.

        Parameters
        ----------
        yaml_path : str | Path
            Path to the YAML file.

        Returns
        -------
        PipelineGraph
            Reconstructed graph with nodes and edges.

        Example
        -------
            graph = PipelineGraph.from_agents_yaml("config/agents.yaml")
        """
        import yaml

        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        pipelines = data.get("pipelines", {})
        if not pipelines:
            raise ValueError(f"No 'pipelines' key found in {yaml_path}")

        name = list(pipelines.keys())[0]
        graph = cls(name=name)

        # Always add INPUT
        graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))

        prev_id = "input"
        for step in pipelines[name].get("steps", []):
            node_id = step.get("stage", step.get("agent", "unknown")).lower()
            graph.add_node(PipelineNode(
                node_id,
                NodeType.AGENT,
                step.get("agent", node_id),
                config={
                    "agent_name": step.get("agent"),
                    "hitl": step.get("hitl_gate", False),
                },
            ))
            graph.add_edge(prev_id, node_id)
            prev_id = node_id

        # Always add OUTPUT
        graph.add_node(PipelineNode("output", NodeType.OUTPUT, "Output"))
        graph.add_edge(prev_id, "output")

        return graph

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PipelineGraph:
        """Reconstruct a graph from a plain dict (from to_dict())."""
        graph = cls(name=d.get("name", "unknown"))

        for nd in d.get("nodes", []):
            graph.add_node(PipelineNode(
                id=nd["id"],
                node_type=NodeType(nd.get("type", "agent")),
                label=nd.get("label", nd["id"]),
                config=nd.get("config", {}),
                position=nd.get("position"),
            ))

        for ed in d.get("edges", []):
            graph.add_edge(ed["source"], ed["target"], condition=ed.get("condition"))

        return graph


# ════════════════════════════════════════════════════════════════════════════════
# PipelineBuilder (Python DSL)
# ════════════════════════════════════════════════════════════════════════════════


class PipelineBuilder:
    """
    Fluent builder for constructing PipelineGraphs using a Python DSL.

    Allows pipeline definition using method chaining:

        graph = (PipelineBuilder("paper_pipeline")
                 .add_agent("outline", "OutlineAgent")
                 .then("literature", "LiteratureReviewAgent")
                 .with_hitl("literature")
                 .then("plotting", "PlottingAgent")
                 .then("writing", "SectionWritingAgent")
                 .then("refinement", "RefinementAgent")
                 .build())

    The resulting graph is automatically wired with INPUT/OUTPUT nodes and
    sequential edges between agents unless explicitly configured otherwise.
    """

    def __init__(self, name: str):
        self.graph = PipelineGraph(name=name)
        self._last_agent: str | None = None

    def add_agent(
        self,
        node_id: str,
        agent_type: str,
        *,
        hitl: bool = False,
        **config: Any,
    ) -> PipelineBuilder:
        """
        Add an agent node.

        Parameters
        ----------
        node_id : str
            Unique identifier for this agent (e.g., "outline", "literature").
        agent_type : str
            Agent class name (e.g., "OutlineAgent", "LiteratureReviewAgent").
        hitl : bool
            Whether this agent has an associated HITL gate.
        **config : Any
            Additional configuration stored on the node.

        Returns
        -------
        PipelineBuilder (self) for chaining.
        """
        self.graph.add_node(PipelineNode(
            id=node_id,
            node_type=NodeType.AGENT,
            label=agent_type,
            config={"agent_name": agent_type, "hitl": hitl, **config},
        ))
        self._last_agent = node_id
        return self

    def then(self, next_id: str, agent_type: str, **config: Any) -> PipelineBuilder:
        """
        Add the next agent, automatically wired from the previous agent.

        Parameters
        ----------
        next_id : str
            Identifier for the next agent.
        agent_type : str
            Agent class name.
        **config : Any
            Additional configuration.

        Returns
        -------
        PipelineBuilder (self) for chaining.
        """
        if self._last_agent is None:
            raise ValueError("then() called but no previous agent — use add_agent() first")

        self.graph.add_node(PipelineNode(
            id=next_id,
            node_type=NodeType.AGENT,
            label=agent_type,
            config={"agent_name": agent_type, **config},
        ))
        self.graph.add_edge(self._last_agent, next_id)
        self._last_agent = next_id
        return self

    def with_hitl(self, agent_name: str) -> PipelineBuilder:
        """
        Add a HITL gate node after an existing agent.

        Inserts a GATE node between the agent and its next successor.

        Parameters
        ----------
        agent_name : str
            ID of the agent after which to insert the gate.

        Returns
        -------
        PipelineBuilder (self) for chaining.
        """
        gate_id = f"{agent_name}_hitl_gate"
        self.graph.add_node(PipelineNode(
            id=gate_id,
            node_type=NodeType.GATE,
            label="HITL Gate",
            config={"after_agent": agent_name},
        ))

        # Find existing outgoing edges from agent and rewire through gate
        edges_to_rewire = [
            e for e in self.graph.edges
            if e.source == agent_name
        ]
        for edge in edges_to_rewire:
            # Remove old edge
            self.graph.edges.remove(edge)
            # Add gate in the middle
            self.graph.add_edge(edge.source, gate_id)
            self.graph.add_edge(gate_id, edge.target)

        # If no successors exist yet, just wire the gate after the agent
        if not edges_to_rewire:
            self.graph.add_edge(agent_name, gate_id)

        return self

    def parallel(
        self,
        agents: list[str],
        *,
        after: str | None = None,
    ) -> PipelineBuilder:
        """
        Add a parallel branch (SPLIT → [agents] → MERGE).

        Creates a split node, runs the given agents in parallel,
        then merges back into the main flow.

        Parameters
        ----------
        agents : list[str]
            List of agent IDs that form the parallel branch.
        after : str | None
            Agent ID after which to insert the parallel split.
            Defaults to the last added agent.

        Returns
        -------
        PipelineBuilder (self) for chaining.
        """
        split_id = f"split_{self._last_agent or 'start'}"
        merge_id = f"merge_{self._last_agent or 'end'}"

        from_id = after or self._last_agent or "input"

        self.graph.add_node(PipelineNode(split_id, NodeType.SPLIT, "Parallel Split"))
        self.graph.add_node(PipelineNode(merge_id, NodeType.MERGE, "Parallel Merge"))

        self.graph.add_edge(from_id, split_id)
        for agent in agents:
            self.graph.add_edge(split_id, agent)
            self.graph.add_edge(agent, merge_id)

        self._last_agent = merge_id
        return self

    def on_failure(self, fallback_agent: str) -> PipelineBuilder:
        """
        Add an error/fallback path from the last agent.

        Currently adds a conditional edge — actual error handling
        is implemented at the orchestrator level.

        Parameters
        ----------
        fallback_agent : str
            ID of the fallback agent to route to on failure.

        Returns
        -------
        PipelineBuilder (self) for chaining.
        """
        if self._last_agent:
            self.graph.add_edge(
                self._last_agent,
                fallback_agent,
                condition="on_failure",
            )
        return self

    def build(self) -> PipelineGraph:
        """
        Finalize and validate the pipeline graph.

        Automatically:
        - Adds INPUT and OUTPUT nodes if missing
        - Wires remaining sequential agents

        Returns
        -------
        PipelineGraph
            Validated pipeline graph.

        Warns
        -----
        Logs all validation warnings (cycles, unreachable nodes, etc.).
        """
        node_ids = {n.id for n in self.graph.nodes}

        # Add INPUT if no INPUT node exists
        if "input" not in node_ids:
            self.graph.add_node(PipelineNode("input", NodeType.INPUT, "Input"))

        # Add OUTPUT if no OUTPUT node exists
        if "output" not in node_ids:
            self.graph.add_node(PipelineNode("output", NodeType.OUTPUT, "Output"))

        # Auto-wire INPUT to first agent if not already connected
        first_agent = self._first_agent()
        if first_agent:
            input_has_edge = any(e.source == "input" for e in self.graph.edges)
            if not input_has_edge:
                self.graph.add_edge("input", first_agent)

        # Auto-wire last agent to OUTPUT if not already connected
        if self._last_agent:
            output_has_edge = any(e.target == "output" for e in self.graph.edges)
            if not output_has_edge:
                self.graph.add_edge(self._last_agent, "output")

        # Validate
        warnings = self.graph.validate()
        if warnings:
            print("\nPipeline validation warnings:")
            for w in warnings:
                print(f"  {w}")

        return self.graph

    def _first_agent(self) -> str | None:
        """Return the first AGENT node in the graph by insertion order."""
        for node in self.graph.nodes:
            if node.node_type == NodeType.AGENT:
                return node.id
        return None


# ════════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ════════════════════════════════════════════════════════════════════════════════


def load_pipeline(yaml_path: str | Path) -> PipelineGraph:
    """
    Load a pipeline from an agents.yaml file and validate it.

    Parameters
    ----------
    yaml_path : str | Path
        Path to the YAML configuration file.

    Returns
    -------
    PipelineGraph
        Loaded and validated graph.
    """
    graph = PipelineGraph.from_agents_yaml(yaml_path)
    warnings = graph.validate()
    if warnings:
        print(f"Loaded pipeline '{graph.name}' with {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  {w}")
    return graph


def quick_build(name: str, *agent_names: str) -> PipelineGraph:
    """
    Build a simple sequential pipeline from a list of agent names.

    Parameters
    ----------
    name : str
        Pipeline name.
    *agent_names : str
        Sequential agent identifiers (e.g., "outline", "literature", "writing").

    Returns
    -------
    PipelineGraph
        A validated pipeline graph.

    Example
    -------
        graph = quick_build("simple", "outline", "writing")
    """
    builder = PipelineBuilder(name)
    for agent_id in agent_names:
        if builder._last_agent is None:
            builder.add_agent(agent_id, agent_id.title() + "Agent")
        else:
            builder.then(agent_id, agent_id.title() + "Agent")
    return builder.build()
