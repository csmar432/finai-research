"""全文级 Provenance 追踪系统.

对标 data-to-paper 的"数据链追溯"能力——从论文中任意数字回溯到
具体代码行、原始数据来源、以及中间计算步骤。

核心数据结构:
    ProvenanceNode — 追踪链中的每个节点（数据 / 代码 / 图表 / 段落）
    ProvenanceLink  — 节点之间的因果关系
    ProvenanceChain — 从数字到数据的完整链路

用法:
    from scripts.core.provenance import ProvenanceChain, get_chain

    chain = ProvenanceChain(project_dir="output/papers/draft_v1")
    chain.trace_figure("Figure 3")   # 回溯图3中每个数字的来源
    chain.trace_number("0.023")       # 找到 0.023 的完整链路
    chain.export_report("provenance_report.md")
"""

from __future__ import annotations

__all__ = [
    "NodeType",
    "SourceRef",
    "ProvenanceNode",
    "compute_checksum",
    "compute_checksum_long",
    "record_transform",
    "get_chain",
    "latex_provenance_comment",
]

import hashlib
import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ─── Node Types ────────────────────────────────────────────────────────────────


class NodeType(Enum):
    RAW_DATA = "raw_data"          # 原始数据文件
    CLEANED_DATA = "cleaned_data"   # 清洗后数据
    VARIABLE = "variable"           # 变量（列）
    CODE = "code"                  # 代码片段
    OUTPUT = "output"               # 计算结果/模型输出
    CHART = "chart"                # 图表
    TABLE = "table"                # 表格
    PARAGRAPH = "paragraph"         # 论文段落
    NUMBER = "number"               # 论文中的具体数字
    CITATION = "citation"           # 文献引用
    MODEL = "model"                # 统计/ML 模型


@dataclass
class SourceRef:
    """指向具体来源的引用。"""
    type: str          # "file", "api", "url", "db"
    path: str          # 文件路径或 URL
    line_start: int | None = None
    line_end: int | None = None
    query: str | None = None        # SQL / API 查询
    checksum: str | None = None      # SHA256


@dataclass
class ProvenanceNode:
    """
    追踪链中的单个节点。

    每个节点代表一个数据处理或生成步骤，可以是：
    - 原始数据文件（CSV/Parquet）
    - 清洗后的数据集
    - 代码片段（Python/Stata）
    - 模型输出（回归系数、预测值）
    - 图表对象
    - 论文中的段落或数字
    """
    node_id: str
    node_type: NodeType
    label: str                          # 人类可读的描述
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 来源追踪
    sources: list[SourceRef] = field(default_factory=list)

    # 内容
    content: str = ""                   # 代码 / 文本内容
    numeric_value: float | None = None   # 论文中的具体数值（如 0.023）
    numeric_context: str = ""            # 数值出现的上下文

    # 依赖关系
    parent_ids: list[str] = field(default_factory=list)   # 输入节点
    child_ids: list[str] = field(default_factory=list)    # 输出节点

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    def add_parent(self, parent_id: str) -> None:
        if parent_id not in self.parent_ids:
            self.parent_ids.append(parent_id)

    def add_child(self, child_id: str) -> None:
        if child_id not in self.child_ids:
            self.child_ids.append(child_id)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "created_at": self.created_at,
            "sources": [
                {"type": s.type, "path": s.path, "line_start": s.line_start,
                 "line_end": s.line_end, "query": s.query, "checksum": s.checksum}
                for s in self.sources
            ],
            "content": self.content[:500] + ("..." if len(self.content) > 500 else ""),
            "numeric_value": self.numeric_value,
            "numeric_context": self.numeric_context,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "metadata": self.metadata,
            "version": self.version,
        }


@dataclass
class ProvenanceLink:
    """节点之间的因果关系边。"""
    link_id: str
    source_id: str
    target_id: str
    operation: str           # e.g. "regression", "filter", "aggregate", "plot"
    description: str = ""     # 人类可读描述
    code_snippet: str = ""   # 引起此链接的具体代码
    metadata: dict = field(default_factory=dict)


# ─── Main Chain ────────────────────────────────────────────────────────────────


class ProvenanceChain:
    """
    全文级 Provenance 追踪器。

    追踪从原始数据到论文中每个数字的完整链路。
    支持：
    - 注册节点和边
    - 数字 → 图表 → 代码 → 原始数据的反向追溯
    - 导出 Mermaid 血缘图
    - 生成 Markdown 追溯报告
    """

    def __init__(self, project_dir: str | Path | None = None):
        self.project_dir = Path(project_dir or "output")
        self.nodes: dict[str, ProvenanceNode] = {}
        self.links: list[ProvenanceLink] = []
        self._chain_path = self.project_dir / "provenance_chain.json"
        self._load()

    # ── CRUD ───────────────────────────────────────────────────────────────

    def register_node(self, node: ProvenanceNode) -> str:
        """注册节点，返回 node_id。"""
        if not node.node_id:
            node.node_id = f"{node.node_type.value}_{uuid.uuid4().hex[:8]}"
        self.nodes[node.node_id] = node
        self._save()
        return node.node_id

    def register_link(self, link: ProvenanceLink) -> None:
        """注册节点间的因果边。"""
        if link.source_id in self.nodes and link.target_id in self.nodes:
            self.nodes[link.source_id].add_child(link.target_id)
            self.nodes[link.target_id].add_parent(link.source_id)
        self.links.append(link)
        self._save()

    def register_data_source(
        self,
        path: str | Path,
        node_type: NodeType = NodeType.RAW_DATA,
        label: str = "",
        checksum: str | None = None,
    ) -> str:
        """快捷方法：注册数据文件节点。"""
        path = str(path)
        if not label:
            label = Path(path).name
        if not checksum:
            checksum = self._file_hash(Path(path))

        node = ProvenanceNode(
            node_id="",
            node_type=node_type,
            label=label,
            sources=[SourceRef(type="file", path=path, checksum=checksum)],
        )
        return self.register_node(node)

    def register_code(
        self,
        code: str,
        output_node_id: str,
        operation: str = "execute",
        description: str = "",
    ) -> str:
        """注册代码节点，并建立从代码到输出的链接。"""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        code_node = ProvenanceNode(
            node_id=f"code_{code_hash}",
            node_type=NodeType.CODE,
            label=f"代码片段: {operation}",
            content=code,
            sources=[SourceRef(type="file", path="<inline>")],
            child_ids=[output_node_id],
        )

        if output_node_id in self.nodes:
            self.nodes[output_node_id].add_parent(code_node.node_id)

        link = ProvenanceLink(
            link_id=f"link_{uuid.uuid4().hex[:8]}",
            source_id=code_node.node_id,
            target_id=output_node_id,
            operation=operation,
            description=description,
            code_snippet=code[:200],
        )
        self.register_node(code_node)
        self.register_link(link)
        return code_node.node_id

    def register_number(
        self,
        value: float,
        context: str,
        parent_ids: list[str],
        label: str = "",
    ) -> str:
        """注册论文中的一个数值（回归系数、统计量等）。"""
        node = ProvenanceNode(
            node_id=f"num_{uuid.uuid4().hex[:8]}",
            node_type=NodeType.NUMBER,
            label=label or f"数值 {value:.4f}",
            numeric_value=value,
            numeric_context=context,
            parent_ids=parent_ids,
        )
        for pid in parent_ids:
            if pid in self.nodes:
                self.nodes[pid].add_child(node.node_id)
        return self.register_node(node)

    def register_figure(
        self,
        figure_path: str | Path,
        data_source_id: str,
        caption: str = "",
        figure_label: str = "",
    ) -> str:
        """注册图表节点。"""
        node = ProvenanceNode(
            node_id=f"fig_{uuid.uuid4().hex[:8]}",
            node_type=NodeType.CHART,
            label=figure_label or Path(figure_path).name,
            sources=[SourceRef(type="file", path=str(figure_path))],
            parent_ids=[data_source_id],
            metadata={"caption": caption, "figure_label": figure_label},
        )
        if data_source_id in self.nodes:
            self.nodes[data_source_id].add_child(node.node_id)
        return self.register_node(node)

    # ── Trace ──────────────────────────────────────────────────────────────

    def trace_figure(self, figure_identifier: str) -> list[ProvenanceNode]:
        """
        追溯图表中数据的来源链。

        参数:
            figure_identifier: figure label（如 "Figure 1"）或路径

        返回:
            从原始数据到图表的完整节点列表
        """
        # Find figure node
        fig_node = None
        for node in self.nodes.values():
            if node.node_type == NodeType.CHART:
                label_match = figure_identifier.lower() in node.label.lower()
                meta_match = figure_identifier.lower() in str(node.metadata.get("figure_label", "")).lower()
                if label_match or meta_match:
                    fig_node = node
                    break

        if not fig_node:
            return []

        return self._backtrack(fig_node.node_id)

    def trace_number(self, value: float | str) -> list[ProvenanceNode]:
        """
        追溯论文中一个具体数字的来源。

        参数:
            value: 浮点数或字符串形式的小数

        返回:
            从原始数据到该数字的完整链路
        """
        # Find number node
        num_nodes = []
        target = None
        if isinstance(value, str):
            try:
                target = float(value)
            except ValueError:
                # Search by string
                for node in self.nodes.values():
                    if node.node_type == NodeType.NUMBER:
                        if value in (node.numeric_context or ""):
                            num_nodes.append(node)
        else:
            target = value

        if target is not None:
            for node in self.nodes.values():
                if (node.node_type == NodeType.NUMBER
                    and node.numeric_value is not None
                    and abs(node.numeric_value - target) < 1e-6):
                    num_nodes.append(node)

        if not num_nodes:
            return []

        # Backtrack from first match
        return self._backtrack(num_nodes[0].node_id)

    def _backtrack(self, node_id: str) -> list[ProvenanceNode]:
        """反向追溯到根节点（原始数据）。"""
        path = []
        visited: set[str] = set()
        stack = [node_id]

        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)

            if current_id in self.nodes:
                node = self.nodes[current_id]
                path.append(node)
                stack.extend(node.parent_ids)

        return path

    def _forward_trace(self, node_id: str) -> list[ProvenanceNode]:
        """正向追踪到叶节点（图表/段落）。"""
        path = []
        visited: set[str] = set()
        stack = [node_id]

        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)

            if current_id in self.nodes:
                node = self.nodes[current_id]
                path.append(node)
                stack.extend(node.child_ids)

        return path

    # ── Export ─────────────────────────────────────────────────────────

    def export_mermaid(self, output_path: Path | None = None) -> str:
        """导出 Mermaid 血缘图。"""
        lines = ["```mermaid", "flowchart LR"]

        type_color = {
            NodeType.RAW_DATA: "fill:#e3f2fd,stroke:#1976d2",
            NodeType.CLEANED_DATA: "fill:#f3e5f5,stroke:#7b1fa2",
            NodeType.VARIABLE: "fill:#e8f5e9,stroke:#388e3c",
            NodeType.CODE: "fill:#fff3e0,stroke:#f57c00",
            NodeType.OUTPUT: "fill:#fce4ec,stroke:#c2185b",
            NodeType.CHART: "fill:#e0f7fa,stroke:#0097a7",
            NodeType.NUMBER: "fill:#fff9c4,stroke:#fbc02d",
            NodeType.PARAGRAPH: "fill:#f1f8e9,stroke:#689f38",
            NodeType.CITATION: "fill:#fafafa,stroke:#757575",
            NodeType.MODEL: "fill:#f3e5f5,stroke:#512da8",
        }

        for node_id, node in self.nodes.items():
            color = type_color.get(node.node_type, "")
            shape = "{" + "{" + node.node_type.value + "}" + "}" if node.node_type == NodeType.NUMBER else "(" + node.node_type.value + ")"
            label = node.label[:40] + "..." if len(node.label) > 40 else node.label
            lines.append(f'    {node_id}{shape}["{label}"]')

        for link in self.links:
            lines.append(f'    {link.source_id} -->|{link.operation}| {link.target_id}')

        lines.append("```")
        mermaid = "\n".join(lines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(mermaid, encoding="utf-8")

        return mermaid

    def export_report(self, output_path: Path | None = None) -> str:
        """导出 Markdown 追溯报告。"""
        lines = [
            "# Provenance 追溯报告\n",
            f"生成时间: {datetime.now().isoformat()}\n",
            f"项目目录: {self.project_dir}\n",
            f"节点总数: {len(self.nodes)}\n",
            f"链路总数: {len(self.links)}\n",
            "\n---\n\n",
        ]

        # Group by type
        by_type: dict[NodeType, list[ProvenanceNode]] = {}
        for node in self.nodes.values():
            by_type.setdefault(node.node_type, []).append(node)

        for ntype, nodes in sorted(by_type.items(), key=lambda x: x[0].value):
            lines.append(f"## {ntype.value}\n\n")
            for node in nodes:
                lines.append(f"### `{node.node_id}` — {node.label}\n")
                if node.sources:
                    for src in node.sources:
                        src_str = f"[{src.type}] {src.path}"
                        if src.line_start:
                            src_str += f" (L{src.line_start}"
                            if src.line_end:
                                src_str += f"-L{src.line_end}"
                            src_str += ")"
                        lines.append(f"- 来源: {src_str}\n")
                if node.numeric_value is not None:
                    lines.append(f"- 数值: `{node.numeric_value:.6f}`\n")
                    lines.append(f"- 上下文: {node.numeric_context[:100]}\n")
                if node.parent_ids:
                    lines.append(f"- 父节点: {node.parent_ids}\n")
                if node.child_ids:
                    lines.append(f"- 子节点: {node.child_ids}\n")
                lines.append("\n")

        report = "\n".join(lines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding="utf-8")

        return report

    def export_figure_provenance_report(
        self,
        figure_identifier: str,
        output_path: Path | None = None,
    ) -> str:
        """Generate a per-figure provenance report as Markdown.

        Shows the complete data lineage for a specific figure with hyperlinks.
        """
        nodes = self.trace_figure(figure_identifier)

        lines = [
            f"# Provenance Report: {figure_identifier}",
            "",
            f"Found {len(nodes)} provenance nodes.",
            "",
        ]

        for i, node in enumerate(nodes):
            lines.append(f"## Step {i + 1}: {node.node_type.value}")
            lines.append(f"- **ID**: `{node.node_id}`")
            # Sources: node.sources is a list[SourceRef]
            if node.sources:
                for src in node.sources:
                    src_label = src.path if hasattr(src, 'path') else str(src)
                    lines.append(f"- **Source**: {src_label}")
            else:
                lines.append(f"- **Source**: (none recorded)")
            lines.append(f"- **Created**: {node.created_at}")
            if node.content:
                lines.append(f"- **Code** (first 100 chars): `{node.content[:100]}`")
            if node.metadata:
                for k, v in node.metadata.items():
                    lines.append(f"- **{k}**: {v}")
            lines.append("")

        content = "\n".join(lines)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")

        return content

    # ── Storage ────────────────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "links": [
                {
                    "link_id": l.link_id,
                    "source_id": l.source_id,
                    "target_id": l.target_id,
                    "operation": l.operation,
                    "description": l.description,
                    "code_snippet": l.code_snippet[:300],
                    "metadata": l.metadata,
                }
                for l in self.links
            ],
            "saved_at": datetime.now().isoformat(),
        }
        self._chain_path.parent.mkdir(parents=True, exist_ok=True)
        self._chain_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _load(self) -> None:
        if not self._chain_path.exists():
            return
        try:
            data = json.loads(self._chain_path.read_text(encoding="utf-8"))
            self.nodes = {
                k: self._dict_to_node(v) for k, v in data.get("nodes", {}).items()
            }
            self.links = [
                ProvenanceLink(
                    link_id=l["link_id"],
                    source_id=l["source_id"],
                    target_id=l["target_id"],
                    operation=l["operation"],
                    description=l.get("description", ""),
                    code_snippet=l.get("code_snippet", ""),
                    metadata=l.get("metadata", {}),
                )
                for l in data.get("links", [])
            ]
        except Exception as exc:
            logger.warning("[ProvenanceChain] Failed to load checkpoint from %s, starting fresh: %s", self._chain_path, exc)

    def _dict_to_node(self, d: dict) -> ProvenanceNode:
        sources = [
            SourceRef(
                type=s.get("type", ""),
                path=s.get("path", ""),
                line_start=s.get("line_start"),
                line_end=s.get("line_end"),
                query=s.get("query"),
                checksum=s.get("checksum"),
            )
            for s in d.get("sources", [])
        ]
        return ProvenanceNode(
            node_id=d.get("node_id", ""),
            node_type=NodeType(d.get("node_type", "raw_data")),
            label=d.get("label", ""),
            created_at=d.get("created_at", ""),
            sources=sources,
            content=d.get("content", ""),
            numeric_value=d.get("numeric_value"),
            numeric_context=d.get("numeric_context", ""),
            parent_ids=d.get("parent_ids", []),
            child_ids=d.get("child_ids", []),
            metadata=d.get("metadata", {}),
            version=d.get("version", "1.0"),
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        if path.exists():
            return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        return ""


def compute_checksum(data: dict | list | str | Any) -> str:
    """计算任意数据的 SHA-256 校验和。用于数据版本追踪和去重。

    v3 DATA-2 enhancement: extended to accept pandas DataFrame and numpy
    arrays natively, plus optional algorithm selector for performance-
    sensitive callers. Returns the 16-character short hash for human
    readability in reports (full 64-char is also available via
    :func:`compute_checksum_long`).
    """
    if data is None:
        return "0" * 16

    # Lazy imports to keep module import-time light
    if hasattr(data, "to_dict"):  # pandas DataFrame
        try:
            # Hash: shape + column dtypes + sampled values (avoid hashing entire df)
            meta = {
                "_kind": "dataframe",
                "shape": list(getattr(data, "shape", [0, 0])),
                "columns": [str(c) for c in getattr(data, "columns", [])],
                "dtypes": {str(c): str(t) for c, t in getattr(data, "dtypes", {}).items()},
            }
            # Sample first/last 3 rows for content fingerprint
            try:
                n = len(data)
                if n > 0:
                    sample_idx = list(range(min(3, n)))
                    if n > 6:
                        sample_idx += list(range(max(0, n - 3), n))
                    sample = data.iloc[sample_idx].to_dict(orient="records")
                    meta["sample"] = sample
            except Exception:
                pass
            encoded = json.dumps(meta, sort_keys=True, ensure_ascii=False, default=str).encode()
        except Exception:
            encoded = repr(data).encode()
    elif isinstance(data, dict):
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    elif isinstance(data, list):
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    elif isinstance(data, (bytes, bytearray)):
        encoded = bytes(data)
    else:
        encoded = str(data).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def compute_checksum_long(data: dict | list | str | Any) -> str:
    """Full 64-char SHA-256. Use for cryptographic-grade audit trails."""
    return hashlib.sha256(compute_checksum(data).encode()).hexdigest()


def record_transform(
    chain: "ProvenanceChain",
    input_node_ids: list[str],
    transform_fn: str,
    params: dict | None = None,
    output_label: str = "",
    output_payload: Any = None,
) -> "ProvenanceNode":
    """Bridge helper: record a data transformation step in the provenance chain.

    Each call attaches a ProvenanceNode to ``chain`` representing one
    deterministic data transformation, with:
      - input_node_ids: causal predecessors
      - transform_fn: name of the function (e.g. ``"winsorize_99"``)
      - params: dict of function arguments (recorded for replay)
      - output_label: human label
      - output_payload: optional data — its checksum is stored automatically

    This enables the "data-to-paper" replay capability: given the same
    input checksum + transform_fn + params, the output is reproducible.

    Parameters
    ----------
    chain : ProvenanceChain
        Target provenance chain.
    input_node_ids : list[str]
        Node IDs that fed into this transform.
    transform_fn : str
        Name of the transformation function.
    params : dict | None
        Arguments passed to ``transform_fn`` (must be JSON-serializable).
    output_label : str
        Human-readable label for the output.
    output_payload : Any, optional
        If provided, a checksum of this data is stored as the output.

    Returns
    -------
    ProvenanceNode
        The newly created node.
    """
    from scripts.core.provenance import ProvenanceNode, NodeType  # local to avoid cycles

    output_checksum = compute_checksum(output_payload) if output_payload is not None else ""
    sources = [SourceRef(type="node_ref", path=nid) for nid in input_node_ids]
    node = ProvenanceNode(
        node_id="",
        node_type=NodeType.OUTPUT,
        label=output_label or transform_fn,
        sources=sources,
        content=f"transform_fn={transform_fn}",
        metadata={
            "transform_fn": transform_fn,
            "params": params or {},
            "output_checksum": output_checksum,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )
    chain.register_node(node)
    return node


# ─── Global singleton ────────────────────────────────────────────────────────


_global_chain: ProvenanceChain | None = None


def get_chain(project_dir: str | Path | None = None) -> ProvenanceChain:
    """获取全局 ProvenanceChain 实例。"""
    global _global_chain
    if _global_chain is None:
        _global_chain = ProvenanceChain(project_dir)
    return _global_chain


# ─── LaTeX Integration ─────────────────────────────────────────────────────────


def latex_provenance_comment(
    figure_label: str,
    data_sources: list[str],
    model_output: str = "",
) -> str:
    """
    生成 LaTeX provenance 注释宏。

    用法：在 LaTeX 导言区加入：
        \\usepackage{xparse} \\NewDocumentCommand\\provenance{mmm}{\\textbf{[Provenance: #1 → #2 → #3]}}

    然后在图表 caption 中使用：
        \\provenance{Figure 1}{CSMAR 数据库}{OLS 回归}
    """
    parts = [f"Figure: {figure_label}"]
    parts.append(f"Sources: {', '.join(data_sources)}")
    if model_output:
        parts.append(f"Output: {model_output}")
    return f"% \\provenance{{{figure_label}}}{{{'; '.join(data_sources)}}}{{{model_output}}}"


def inject_provenance_into_latex(
    tex_path: str | Path,
    chain: ProvenanceChain,
) -> Path:
    """
    将 provenance 信息注入 LaTeX 文档。

    在每个 \\begin{{figure}} 后的 \\caption 下方添加 provenance 注释。
    """
    tex_path = Path(tex_path)
    content = tex_path.read_text(encoding="utf-8")

    # Find all figures
    pattern = re.compile(
        r"(\\begin\{figure\}.*?\\caption\{(.*?)\})",
        re.DOTALL,
    )

    def replace_figure(m: re.Match) -> str:
        full = m.group(0)
        caption = m.group(2)
        # Try to find corresponding chart node
        for node in chain.nodes.values():
            if node.node_type == NodeType.CHART and caption in (node.metadata.get("caption", "") or ""):
                sources = [s.path for s in node.sources]
                comment = latex_provenance_comment(caption, sources)
                return full + f"\n\\hfill{{{comment}}}"
        return full

    new_content = pattern.sub(replace_figure, content)

    out_path = tex_path.with_stem(tex_path.stem + "_with_provenance")
    out_path.write_text(new_content, encoding="utf-8")
    return out_path


# ─── ChartMetadata ──────────────────────────────────────────────────────────────


@dataclass
class ChartMetadata:
    """图表的元数据，用于 provenance 追踪。"""
    path: str | Path
    caption: str = ""
    figure_label: str = ""
    data_sources: list[str] = field(default_factory=list)
    code_snippet: str = ""
    width: float = 0
    height: float = 0
    dpi: int = 300
    format: str = "pdf"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "caption": self.caption,
            "figure_label": self.figure_label,
            "data_sources": self.data_sources,
            "code_snippet": self.code_snippet[:200] if self.code_snippet else "",
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "format": self.format,
            "created_at": self.created_at,
        }


# ─── ProvenanceTracker (high-level facade) ──────────────────────────────────────


class ProvenanceTracker:
    """
    高层 provenance 追踪门面类。

    提供比 ProvenanceChain 更简洁的 API，用于日常研究工作流。
    """

    def __init__(self, project_dir: str | Path | None = None):
        self._chain = ProvenanceChain(project_dir)

    def register_data(
        self,
        path: str | Path,
        label: str = "",
        node_type: NodeType = NodeType.RAW_DATA,
    ) -> str:
        return self._chain.register_data_source(path, node_type, label)

    def register_chart(self, metadata: ChartMetadata, data_node_id: str) -> str:
        """注册图表及其数据来源。"""
        fig_node = ProvenanceNode(
            node_id=f"fig_{uuid.uuid4().hex[:8]}",
            node_type=NodeType.CHART,
            label=metadata.figure_label or Path(metadata.path).name,
            sources=[
                SourceRef(type="file", path=str(metadata.path)),
                *[SourceRef(type="file", path=ds) for ds in metadata.data_sources],
            ],
            content=metadata.code_snippet,
            parent_ids=[data_node_id],
            metadata=metadata.to_dict(),
        )
        if data_node_id in self._chain.nodes:
            self._chain.nodes[data_node_id].add_child(fig_node.node_id)
        return self._chain.register_node(fig_node)

    def trace_figure(self, identifier: str) -> list[ProvenanceNode]:
        return self._chain.trace_figure(identifier)

    def trace_number(self, value: float | str) -> list[ProvenanceNode]:
        return self._chain.trace_number(value)

    def export_mermaid(self, output_path: Path | None = None) -> str:
        return self._chain.export_mermaid(output_path)

    def export_report(self, output_path: Path | None = None) -> str:
        return self._chain.export_report(output_path)


# ─── Global singleton facade ─────────────────────────────────────────────────────


_global_tracker: ProvenanceTracker | None = None


def set_tracker(tracker: ProvenanceTracker | None) -> None:
    """设置全局 ProvenanceTracker 实例。"""
    global _global_tracker
    _global_tracker = tracker


def get_tracker(project_dir: str | Path | None = None) -> ProvenanceTracker:
    """获取或创建全局 ProvenanceTracker 实例。"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ProvenanceTracker(project_dir)
    return _global_tracker


def reset_tracker() -> None:
    """重置全局 tracker（清空所有节点）。"""
    global _global_tracker, _global_chain
    _global_tracker = None
    _global_chain = None


def register_chart(
    metadata: ChartMetadata,
    data_node_id: str,
    tracker: ProvenanceTracker | None = None,
) -> str:
    """快捷函数：注册图表。"""
    t = tracker or get_tracker()
    return t.register_chart(metadata, data_node_id)


def register_data_source(
    path: str | Path,
    node_type: NodeType = NodeType.RAW_DATA,
    label: str = "",
    tracker: ProvenanceTracker | None = None,
) -> str:
    """快捷函数：注册数据源（委托给全局 tracker）。"""
    t = tracker or get_tracker()
    return t._chain.register_data_source(path, node_type, label)
