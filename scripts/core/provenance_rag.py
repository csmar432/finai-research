"""Provenance 数字注入与向量检索增强。

在 `provenance.py` 的 ProvenanceChain 基础上，添加：

1. **NumberExtractor** — 从论文/文本中提取数值（系数、标准误、t值、p值、置信区间）
   并与 ProvenanceChain 中的节点关联。
2. **ProvenanceRAG** — ChromaDB 向量存储 + 混合检索，使研究者可通过自然语言
   查询任意数字的来源（如"图3中0.082的回归系数来自哪行代码"）。

用法：
    from scripts.core.provenance_rag import NumberExtractor, ProvenanceRAG

    rag = ProvenanceRAG(project_dir="output/papers/draft_v1")
    rag.index_paper("paper.tex")

    # 自然语言查询数字来源
    results = rag.query("碳排放交易对企业绿色创新的处理效应系数是多少？")
"""

from __future__ import annotations

__all__ = [
    "ExtractedNumber",
    "NumberExtractor",
    "RAGResult",
]

import logging
import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ─── Soft dependency check ───────────────────────────────────────────────────────

_chroma_available = False
_embedder: Any = None
_embed_model: Any = None

try:
    import chromadb

    _chroma_available = True
except ImportError:
    logger.warning(
        "[ProvenanceRAG] chromadb not installed. "
        "Run: pip install chromadb sentence-transformers jieba faiss-cpu"
    )

try:
    from sentence_transformers import SentenceTransformer

    _embedder = SentenceTransformer
except ImportError:
    logger.warning(
        "[ProvenanceRAG] sentence-transformers not installed. "
        "Vector embedding disabled. Run: pip install sentence-transformers"
    )


# ═════════════════════════════════════════════════════════════════════════════════
# NumberExtractor — 论文数字提取
# ╘════════════════════════════════════════════════════════════════════════════════


@dataclass
class ExtractedNumber:
    """从文本中提取的数值。"""
    value: float
    raw_text: str                    # 原始匹配文本（含单位）
    context: str                     # 前后各60字符
    position: int                    # 在原文中的字节偏移
    number_type: str = "unknown"    # coefficient / se / t_stat / p_value / ci / effect
    confidence: float = 1.0          # 置信度 0-1
    table_ref: str | None = None     # e.g. "Table 3"
    figure_ref: str | None = None    # e.g. "Figure 2"


# ─── Number patterns ────────────────────────────────────────────────────────────


# 数字 + 单位/指标的组合
_COEF_PATTERNS = [
    # 系数（科学计数法格式，如 1.23**-0.45）+ 标准误 + 可选 t值
    # 例: "1.23**-0.45 (0.12) t=2.15" → 系数=-0.045, se=0.12, t=2.15
    #    "3.2**0.5 (0.04)"            → 系数≈1.79, se=0.04
    re.compile(
        r"([+-]?\d+\.?\d*)\s*\*\*\s*([+-]?\d+\.?\d*)\s*"
        r"\(\s*([+-]?\d+\.?\d*)\s*\)\s*"
        r"(?:t\s*[=:]?\s*([+-]?\d+\.?\d*))?",
        re.IGNORECASE,
    ),
    # 系数 + 显著性星号 (1-3颗) + (标准误) 或 (t=值)
    # 例: "1.23*** (0.12)" → 系数=1.23, se=0.12; "0.45** (t=3.2)" → 系数=0.45, t=3.2
    re.compile(
        r"([+-]?\d+\.?\d*)\s*(\*{1,3})\s*"
        r"(?:\(\s*([+-]?\d+\.?\d*)\s*\)|\(\s*t\s*[=:]\s*([+-]?\d+\.?\d*)\s*\))",
        re.IGNORECASE,
    ),
    # 系数 (标准误) — 无星号，独立一行（regression table 最后一列风格）
    re.compile(
        r"(?<!\*)\(([+-]?\d+\.\d+)\)\s*$",
        re.MULTILINE,
    ),
    # 系数 （标准误）— 中英文混合括号
    re.compile(r"([+-]?\d+\.\d{3,})\s*(?:\(|（)([+-]?\d+\.\d+)(?:\)|）)"),
    # 带描述的系数
    re.compile(
        r"(?:treatment|effect|impact|coefficient|系数|效应|处理)\s*"
        r"[:=\s]*([+-]?\d+\.\d+)",
        re.IGNORECASE,
    ),
]

# t统计量
_T_PATTERNS = [
    re.compile(r"t\s*[=:]\s*([+-]?\d+\.?\d*)", re.IGNORECASE),
    re.compile(r"t\s+statistic\s*[=:]\s*([+-]?\d+\.?\d*)", re.IGNORECASE),
    re.compile(r"t值\s*[=:]\s*([+-]?\d+\.?\d*)", re.IGNORECASE),
]

# p值
_P_PATTERNS = [
    re.compile(r"p\s*[<≤=:]\s*([01]\.\d+)", re.IGNORECASE),
    re.compile(r"p值\s*[<≤=:]\s*([01]\.\d+)", re.IGNORECASE),
    re.compile(r"\(p\s*=\s*0?\.\d+\)", re.IGNORECASE),
]

# R² / 调整R²
_R2_PATTERNS = [
    re.compile(r"R\s*²\s*[=:]\s*([01]\.\d+)", re.IGNORECASE),
    re.compile(r"Adj\.\s*R\s*²\s*[=:]\s*([01]\.\d+)", re.IGNORECASE),
    re.compile(r"R-squared\s*[=:]\s*([01]\.\d+)", re.IGNORECASE),
]

# 置信区间
_CI_PATTERNS = [
    re.compile(r"\[(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\]"),
]

# 百分比变化
_PCT_PATTERNS = [
    re.compile(r"([+-]?\d+\.?\d*)\s*%(?:\s+(?:increase|decrease|increase|增长|减少|增加))", re.IGNORECASE),
    re.compile(r"(?:increase|decrease|增长|减少)\s+by\s+([+-]?\d+\.?\d*)\s*%", re.IGNORECASE),
]

# F统计量
_F_PATTERNS = [
    re.compile(r"(?<![a-zA-Z])F\s*[=:]\s*(\d+\.?\d*)", re.IGNORECASE),
    re.compile(r"F\s*statistic\s*[=:]\s*([+-]?\d+\.?\d*)", re.IGNORECASE),
]

# 样本量
_N_PATTERNS = [
    re.compile(r"N\s*[=:]\s*([\d,]+)", re.IGNORECASE),
    re.compile(r"样本[量数]\s*[=:：]\s*([\d,]+)", re.IGNORECASE),
    re.compile(r"observations?\s*[=:]\s*([\d,]+)", re.IGNORECASE),
]

# 表格/图的引用上下文
_TABLE_FIG_PATTERNS = [
    re.compile(r"(?:Table|表)\s*(\d+[A-Z]?)"),
    re.compile(r"(?:Figure|图)\s*(\d+[A-Z]?)"),
]


class NumberExtractor:
    """
    从论文 LaTeX 源或 Markdown 中提取关键数值。

    支持提取：
    - 回归系数（带显著性标记 *** / ** / *）
    - 标准误（括号内）
    - t 统计量
    - p 值
    - 置信区间
    - R² / 调整R²
    - 百分比变化
    - F 统计量
    - 样本量

    配合 ProvenanceChain 使用时，可将每个提取的数值注册为 ProvenanceNode，
    建立数字 → 代码 → 原始数据的追溯链路。
    """

    def __init__(self, min_value: float = -1000, max_value: float = 1000):
        self.min_value = min_value
        self.max_value = max_value

    def extract(self, text: str) -> list[ExtractedNumber]:
        """从文本中提取所有关键数值。"""
        results: list[ExtractedNumber] = []
        seen: list[tuple[float, str]] = []  # (value, type) pairs for dedup

        # 提取表格/图的上下文引用
        table_fig_map: dict[int, str] = {}
        for m in re.finditer(r"(?:Table|表|Figure|图)\s*(\d+[A-Z]?)", text):
            table_fig_map[m.start()] = m.group(0)

        # 逐行/逐段扫描
        lines = text.split("\n")
        byte_offset = 0
        for line in lines:
            # 跳过注释行
            if line.strip().startswith("%"):
                byte_offset += len(line) + 1
                continue

            # 表格/图的上下文
            tbl_ref = None
            fig_ref = None
            for pos, ref in table_fig_map.items():
                if abs(pos - byte_offset) < 200:
                    if "Table" in ref or "表" in ref:
                        tbl_ref = ref
                    else:
                        fig_ref = ref

            # 系数 Pattern 0: val (se) (t=)
            for m in _COEF_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if self._is_valid(val):
                    se = float(m.group(3)) if m.group(3) else None
                    t_val = float(m.group(4)) if m.group(4) else None
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="coefficient",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "coefficient")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # 系数 Pattern 1: val*** (se) 或 val*** (t=)
            for m in _COEF_PATTERNS[1].finditer(line):
                val = float(m.group(1))
                if self._is_valid(val):
                    se = float(m.group(3)) if m.group(3) else float(m.group(4)) if m.group(4) else None
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="coefficient",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "coefficient")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # t统计量（独立行）
            for m in _T_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if 0 < abs(val) < 100:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="t_stat",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "t_stat")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # p值
            for m in _P_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if 0 <= val <= 1:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="p_value",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "p_value")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # 置信区间 [下限, 上限]
            for m in _CI_PATTERNS[0].finditer(line):
                lo = float(m.group(1))
                hi = float(m.group(2))
                midpoint = (lo + hi) / 2
                if self._is_valid(lo) and self._is_valid(hi):
                    num = ExtractedNumber(
                        value=midpoint,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="ci",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (midpoint, "ci")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # 百分比变化
            for m in _PCT_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if abs(val) <= 1000:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="effect",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "effect")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # F统计量
            for m in _F_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if 0 < val < 1e6:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="f_stat",
                        table_ref=tbl_ref,
                        figure_ref=fig_ref,
                    )
                    key = (val, "f_stat")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # R²
            for m in _R2_PATTERNS[0].finditer(line):
                val = float(m.group(1))
                if 0 <= val <= 1:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="r_squared",
                    )
                    key = (val, "r_squared")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            # 样本量
            for m in _N_PATTERNS[0].finditer(line):
                val_str = m.group(1).replace(",", "")
                val = float(val_str)
                if 10 <= val <= 1e9:
                    num = ExtractedNumber(
                        value=val,
                        raw_text=m.group(0),
                        context=text[max(0, byte_offset - 60):byte_offset + len(line) + 60],
                        position=byte_offset + m.start(),
                        number_type="sample_size",
                    )
                    key = (val, "sample_size")
                    if key not in {(v, t) for v, t in seen}:
                        results.append(num)
                        seen.append(key)

            byte_offset += len(line) + 1

        # 按 position 排序
        results.sort(key=lambda x: x.position)
        return results

    def _is_valid(self, val: float) -> bool:
        """过滤异常值。"""
        if math.isnan(val) or math.isinf(val):
            return False
        return self.min_value <= val <= self.max_value

    def extract_from_file(self, path: str | Path) -> list[ExtractedNumber]:
        """从 .tex / .md 文件提取数值。"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        return self.extract(text)

    def summarize(self, numbers: list[ExtractedNumber]) -> str:
        """生成人类可读的数值摘要。"""
        if not numbers:
            return "未提取到任何数值"

        by_type: dict[str, list[ExtractedNumber]] = {}
        for n in numbers:
            by_type.setdefault(n.number_type, []).append(n)

        lines = ["## 提取的数值摘要\n"]
        lines.append(f"总计提取 {len(numbers)} 个数值\n")

        for ntype, items in sorted(by_type.items()):
            type_label = {
                "coefficient": "回归系数",
                "t_stat": "t统计量",
                "p_value": "p值",
                "r_squared": "R²",
                "sample_size": "样本量",
                "effect": "效应量",
                "ci": "置信区间",
            }.get(ntype, ntype)
            lines.append(f"\n### {type_label} ({len(items)}个)\n")
            for item in items[:10]:  # 最多显示10个
                ref = ""
                if item.table_ref:
                    ref = f" [{item.table_ref}]"
                if item.figure_ref:
                    ref += f" [{item.figure_ref}]"
                lines.append(
                    f"- `{item.value:.4f}` {ref}\n"
                    f"  原文: *{item.raw_text.strip()}*\n"
                )

        return "".join(lines)


# ═════════════════════════════════════════════════════════════════════════════════
# ProvenanceRAG — 向量 + 关键词混合检索
# ╘════════════════════════════════════════════════════════════════════════════════


@dataclass
class RAGResult:
    """检索结果。"""
    content: str
    source: str                      # 文件路径或节点ID
    score: float                     # 相似度分 (0-1, 越高越好)
    provenance_chain: list[str] | None = None  # 追溯链路（如果可用）
    metadata: dict[str, Any] = field(default_factory=dict)


class ProvenanceRAG:
    """
    Provenance 向量检索增强。

    结合 ChromaDB 向量存储和 ProvenanceChain 的结构化血缘数据，
    支持自然语言查询论文中任意数字的来源。

    主要功能：
    - 将 ProvenanceChain 节点和论文文本嵌入到 ChromaDB
    - 数字提取 → 节点关联 → 溯源链路构建
    - 关键词 + 向量混合检索
    - SQLite 持久化（chroma 不可用时的降级方案）

    安装依赖：
        pip install chromadb sentence-transformers jieba faiss-cpu
    """

    def __init__(
        self,
        project_dir: str | Path | None = None,
        persist_dir: str | Path | None = None,
        embed_model: str = "all-MiniLM-L6-v2",
        use_sqlite_fallback: bool = True,
    ):
        self.project_dir = Path(project_dir or "output")
        self.persist_dir = Path(persist_dir or self.project_dir / ".rag_index")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._chroma_client: Any = None
        self._collection: Any = None
        self._embed_model_name = embed_model
        self._embedder_model: Any = None
        self._use_sqlite_fallback = use_sqlite_fallback
        self._sqlite_db: Path = self.persist_dir / "provenance_rag.sqlite"

        # 尝试初始化 ChromaDB
        if _chroma_available and _embedder is not None:
            self._init_chroma(embed_model)
        else:
            if use_sqlite_fallback:
                logger.info(
                    "[ProvenanceRAG] ChromaDB/sentence-transformers 未安装，"
                    " 使用 SQLite 全文检索降级模式"
                )
                self._init_sqlite()

    # ── Initialization ────────────────────────────────────────────────────────

    def _init_chroma(self, model_name: str) -> None:
        """初始化 ChromaDB + SentenceTransformer。"""
        try:
            import chromadb
            from chromadb.config import Settings

            self._chroma_client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name="provenance_numbers",
                metadata={"description": "Provenance number index for paper figures/tables"},
            )

            self._embedder_model = _embedder(model_name)
            logger.info(f"[ProvenanceRAG] ChromaDB initialized with model {model_name}")
        except Exception as e:
            logger.warning(f"[ProvenanceRAG] ChromaDB init failed: {e}, falling back to SQLite")
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """SQLite 全文检索降级。"""
        self._sql_conn = sqlite3.connect(str(self._sqlite_db))
        self._sql_conn.execute("""
            CREATE TABLE IF NOT EXISTS provenance_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT,
                node_type TEXT,
                numeric_value REAL,
                provenance_chain TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 全文索引
        self._sql_conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON provenance_index(content)")
        self._sql_conn.execute("CREATE INDEX IF NOT EXISTS idx_value ON provenance_index(numeric_value)")
        self._sql_conn.commit()

    # ── Indexing ─────────────────────────────────────────────────────────────

    def index_paper(
        self,
        paper_path: str | Path,
        extractor: NumberExtractor | None = None,
    ) -> list[ExtractedNumber]:
        """
        索引一篇论文（LaTeX / Markdown），提取数字并构建向量索引。

        步骤：
        1. NumberExtractor 提取论文中的数值
        2. 将每个数值节点及其上下文存入 ChromaDB / SQLite
        3. 返回提取的数值列表
        """
        path = Path(paper_path)
        if not path.exists():
            raise FileNotFoundError(f"论文文件不存在: {path}")

        text = path.read_text(encoding="utf-8", errors="replace")

        extractor = extractor or NumberExtractor()
        numbers = extractor.extract(text)

        if not numbers:
            logger.info(f"[ProvenanceRAG] No numbers extracted from {path.name}")
            return []

        # 存储到 ChromaDB 或 SQLite
        if self._collection is not None:
            self._index_numbers_chroma(numbers, path.name)
        else:
            self._index_numbers_sqlite(numbers, path.name)

        logger.info(f"[ProvenanceRAG] Indexed {len(numbers)} numbers from {path.name}")
        return numbers

    def index_provenance_chain(self, chain: Any) -> None:
        """
        将 ProvenanceChain 中的节点批量索引到向量数据库。

        chain : ProvenanceChain
            已构建的 ProvenanceChain 实例
        """
        if self._collection is not None:
            self._index_chain_chroma(chain)
        else:
            self._index_chain_sqlite(chain)

    def index_text(
        self,
        content: str,
        source: str = "inline",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """索引任意文本片段（代码、表格、图表说明）。"""
        if self._collection is not None:
            self._index_text_chroma(content, source, metadata or {})
        else:
            self._index_text_sqlite(content, source, metadata or {})

    def _index_numbers_chroma(self, numbers: list[ExtractedNumber], source: str) -> None:
        docs = []
        metas = []
        ids = []

        for i, num in enumerate(numbers):
            doc = (
                f"[{num.number_type}] {num.raw_text}\n"
                f"Context: {num.context}\n"
                f"Value: {num.value}"
            )
            docs.append(doc)
            metas.append({
                "number_type": num.number_type,
                "value": num.value,
                "raw_text": num.raw_text,
                "table_ref": num.table_ref or "",
                "figure_ref": num.figure_ref or "",
                "source": source,
            })
            ids.append(f"num_{source}_{i}_{num.position}")

        if docs:
            embeddings = self._embedder_model.encode(docs, show_progress_bar=False)
            self._collection.add(
                documents=docs,
                embeddings=embeddings.tolist(),
                metadatas=metas,
                ids=ids,
            )

    def _index_numbers_sqlite(self, numbers: list[ExtractedNumber], source: str) -> None:
        rows = []
        for num in numbers:
            rows.append((
                f"[{num.number_type}] {num.raw_text}\nContext: {num.context}\nValue: {num.value}",
                source,
                num.number_type,
                num.value,
                "",
            ))
        self._sql_conn.executemany(
            "INSERT INTO provenance_index (content, source, node_type, numeric_value, provenance_chain) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._sql_conn.commit()

    def _index_chain_chroma(self, chain: Any) -> None:
        """将 ProvenanceChain 节点批量嵌入。"""
        if not hasattr(chain, "nodes"):
            return

        docs, metas, ids = [], [], []
        for node_id, node in chain.nodes.items():
            doc = f"[{node.node_type.value}] {node.label}"
            if node.content:
                doc += f"\n{node.content[:500]}"
            if node.numeric_value is not None:
                doc += f"\nNumeric: {node.numeric_value}"

            docs.append(doc)
            metas.append({
                "node_id": node_id,
                "type": node.node_type.value,
                "value": node.numeric_value,
                "label": node.label,
            })
            ids.append(f"chain_{node_id}")

        if docs:
            embeddings = self._embedder_model.encode(docs, show_progress_bar=False)
            self._collection.add(
                documents=docs,
                embeddings=embeddings.tolist(),
                metadatas=metas,
                ids=ids,
            )

    def _index_chain_sqlite(self, chain: Any) -> None:
        if not hasattr(chain, "nodes"):
            return
        rows = []
        for node_id, node in chain.nodes.items():
            content = f"[{node.node_type.value}] {node.label}"
            if node.content:
                content += f"\n{node.content[:500]}"
            rows.append((content, node_id, node.node_type.value, node.numeric_value, ""))
        self._sql_conn.executemany(
            "INSERT INTO provenance_index (content, source, node_type, numeric_value, provenance_chain) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._sql_conn.commit()

    def _index_text_chroma(self, content: str, source: str, metadata: dict) -> None:
        emb = self._embedder_model.encode([content], show_progress_bar=False)
        self._collection.add(
            documents=[content],
            embeddings=emb.tolist(),
            metadatas=[metadata],
            ids=[f"text_{hash(content) % 100000}_{datetime.now().timestamp()}"],
        )

    def _index_text_sqlite(self, content: str, source: str, metadata: dict) -> None:
        self._sql_conn.execute(
            "INSERT INTO provenance_index (content, source, node_type, numeric_value, provenance_chain) VALUES (?, ?, ?, ?, ?)",
            (content, source, metadata.get("type", "text"), metadata.get("value"), ""),
        )
        self._sql_conn.commit()

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        question: str,
        top_k: int = 5,
        number_type: str | None = None,
    ) -> list[RAGResult]:
        """
        自然语言查询数字来源。

        example:
            results = rag.query("碳排放交易对企业绿色创新的处理效应是多少？")
            for r in results:
                print(f"  {r.content[:100]} (score={r.score:.3f})")

        Args:
            question: 自然语言问题
            top_k: 返回结果数量
            number_type: 仅返回指定类型的数值
        """
        if self._collection is not None:
            return self._query_chroma(question, top_k, number_type)
        else:
            return self._query_sqlite(question, top_k, number_type)

    def _query_chroma(
        self,
        question: str,
        top_k: int,
        number_type: str | None,
    ) -> list[RAGResult]:
        where = {"number_type": number_type} if number_type else None
        results = self._collection.query(
            query_texts=[question],
            n_results=top_k,
            where=where,
        )

        rag_results = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                score = 1 - (results["distances"][i][0] / 2) if results.get("distances") else 0.5
                rag_results.append(RAGResult(
                    content=doc,
                    source=meta.get("source", ""),
                    score=score,
                    provenance_chain=None,
                    metadata=meta,
                ))
        return rag_results

    def _query_sqlite(
        self,
        question: str,
        top_k: int,
        number_type: str | None,
    ) -> list[RAGResult]:
        """SQLite 降级：关键词 + 数值范围检索。"""
        sql = "SELECT content, source, node_type, numeric_value FROM provenance_index WHERE 1=1"
        params: list[Any] = []

        # 提取问句中的数值
        num_match = re.search(r"[+-]?\d+\.?\d*", question)
        if num_match:
            val = float(num_match.group())
            sql += " AND ABS(numeric_value - ?) < 0.01"
            params.append(val)

        # 类型过滤
        if number_type:
            sql += " AND node_type = ?"
            params.append(number_type)

        # 关键词匹配（从问句中提取有意义的词）
        stopwords = {"的", "是", "了", "和", "在", "与", "对", "有", "这", "为", "with", "the", "is", "and", "of", "in", "a", "to", "for", "what", "how", "which", "where"}
        keywords = [w for w in re.findall(r"[\u4e00-\u9fff_a-zA-Z]{2,}", question) if w not in stopwords]
        if keywords:
            kw_clauses = " OR ".join(["content LIKE ?" for _ in keywords])
            sql += f" AND ({kw_clauses})"
            params.extend([f"%{w}%" for w in keywords])

        sql += f" ORDER BY ABS(numeric_value - ?) LIMIT ?" if num_match else f" ORDER BY RANDOM() LIMIT ?"
        if num_match:
            params.insert(0, val)
        params.append(top_k)

        rows = self._sql_conn.execute(sql, params).fetchall()
        return [
            RAGResult(content=row[0], source=row[1], score=0.7, metadata={"type": row[2], "value": row[3]})
            for row in rows
        ]

    # ── Trace number ─────────────────────────────────────────────────────────

    def trace_number(self, value: float, tolerance: float = 0.001) -> list[RAGResult]:
        """
        根据数值精确定位其在论文中的来源。

        使用场景：审稿人质疑某个数字时，快速定位其代码/数据来源。
        """
        if self._collection is not None:
            return self._trace_chroma(value, tolerance)
        else:
            return self._trace_sqlite(value, tolerance)

    def _trace_chroma(self, value: float, tolerance: float) -> list[RAGResult]:
        results = self._collection.query(
            query_texts=[f"number {value}"],
            n_results=3,
            where={"value": {"$gte": value - tolerance, "$lte": value + tolerance}},
        )
        rag_results = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                rag_results.append(RAGResult(
                    content=doc,
                    source=results["metadatas"][i].get("source", "") if results["metadatas"] else "",
                    score=1 - (results["distances"][i][0] / 2) if results.get("distances") else 0.5,
                    metadata=results["metadatas"][i] if results["metadatas"] else {},
                ))
        return rag_results

    def _trace_sqlite(self, value: float, tolerance: float) -> list[RAGResult]:
        rows = self._sql_conn.execute(
            "SELECT content, source, node_type, numeric_value FROM provenance_index "
            "WHERE numeric_value BETWEEN ? AND ? ORDER BY ABS(numeric_value - ?) LIMIT 3",
            (value - tolerance, value + tolerance, value),
        ).fetchall()
        return [
            RAGResult(content=row[0], source=row[1], score=0.8, metadata={"type": row[2], "value": row[3]})
            for row in rows
        ]

    # ── Statistics ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """返回索引统计。"""
        stats = {
            "chroma_available": _chroma_available,
            "embed_model": self._embed_model_name if _embedder else None,
            "persist_dir": str(self.persist_dir),
        }
        if self._collection is not None:
            stats["chroma_count"] = self._collection.count()
        if hasattr(self, "_sql_conn"):
            cur = self._sql_conn.execute("SELECT COUNT(*) FROM provenance_index").fetchone()
            stats["sqlite_count"] = cur[0] if cur else 0
        return stats


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ProvenanceRAG 工具")
    parser.add_argument("--paper", type=str, help="论文 .tex 文件路径")
    parser.add_argument("--query", type=str, help="自然语言查询")
    parser.add_argument("--trace", type=float, help="根据数值溯源（如 0.082）")
    parser.add_argument("--stats", action="store_true", help="显示索引统计")
    parser.add_argument("--project-dir", type=str, default="output")
    args = parser.parse_args()

    rag = ProvenanceRAG(project_dir=args.project_dir)

    if args.paper:
        ext = NumberExtractor()
        numbers = rag.index_paper(args.paper, extractor=ext)
        print(f"\n✅ 从 {Path(args.paper).name} 提取了 {len(numbers)} 个数值\n")
        print(ext.summarize(numbers))

    if args.query:
        results = rag.query(args.query)
        print(f"\n查询: {args.query}\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] score={r.score:.3f} | {r.source}\n  {r.content[:200]}\n")

    if args.trace:
        results = rag.trace_number(args.trace)
        print(f"\n溯源数值: {args.trace}\n")
        for r in results:
            print(f"  {r.content[:300]}\n")

    if args.stats:
        import json
        print(json.dumps(rag.stats(), indent=2, ensure_ascii=False))
