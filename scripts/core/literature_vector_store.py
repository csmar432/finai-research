"""
literature_vector_store.py — 学术论文向量文献库

基于 ChromaDB 的持久化文献向量存储，专为经济金融学术研究设计。

核心特点：
1. Section级分块：Abstract / Introduction / Literature / Methodology / Results / Conclusion
   （而非固定token窗口，保持语义完整性）
2. Hybrid检索：向量相似度 + BM25关键词 + RRF重排
3. 增量索引：新论文追加，无需全量重建
4. 多模态元数据：年份/期刊/作者/关键词/方法论
5. 与ResearchMemory集成：跨会话知识积累

继承自 ResearchRAG 的设计理念，但专注论文文献这一垂直场景。
"""

from __future__ import annotations

__all__ = [
    "PaperMetadata",
    "PaperSection",
    "LiteratureQueryResult",
    "AcademicPaperChunker",
    "LiteratureVectorStore",
    "CHROMA_AVAILABLE",
    "NP_AVAILABLE",
]

import hashlib
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── 可选依赖 ──────────────────────────────────────────────────────────────

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False
    np = None


# ─── 数据类型 ──────────────────────────────────────────────────────────────

class PaperMetadata:
    """论文元数据。"""
    paper_id: str = ""
    title: str = ""
    authors: list[str] = None
    year: int = 0
    journal: str = ""
    arxiv_id: str | None = None
    doi: str | None = None
    keywords: list[str] = None
    methods: list[str] = None
    topics: list[str] = None
    abstract: str | None = None
    url: str | None = None
    local_path: str | None = None
    citations: int | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    added_at: str = ""
    updated_at: str = ""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        if self.authors is None:
            self.authors = []
        if self.keywords is None:
            self.keywords = []
        if self.methods is None:
            self.methods = []
        if self.topics is None:
            self.topics = []

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != []}


@dataclass
class PaperSection:
    """论文的一个章节。"""
    section_id: str
    paper_id: str
    section_name: str        # "abstract" / "introduction" / "literature" / "methodology" / "results" / "conclusion" / "appendix"
    content: str
    word_count: int
    start_char: int
    end_char: int
    metadata: "dict" = field(default_factory=dict)


@dataclass
class LiteratureQueryResult:
    """文献检索结果。"""
    section: PaperSection
    paper_metadata: dict
    vector_score: float
    bm25_score: float | None
    combined_score: float
    rank: int
    matched_keywords: list[str]


# ─── Section 分块器 ───────────────────────────────────────────────────────

class AcademicPaperChunker:
    """学术论文 SECTION 级分块器。

    策略：按论文的标准结构划分，而非固定token窗口。
    优势：每个 chunk 有清晰的语义角色（方法/结果/讨论），
    检索结果更可解释。

    支持的论文格式：
    - 英文顶刊（JF/JFE/RFS/JME 等）
    - 中文顶刊（经济研究/金融研究/管理世界/会计研究 等）
    - ArXiv 预印本
    - NBER Working Papers
    """

    # 英文学术论文的章节标题模式（非捕获组，支持#标题和编号章节）
    ENGLISH_SECTION_PATTERNS = [
        (r"(?:Abstract|ABSTRACT)", "abstract"),
        (r"(?:^|\n)(?:1\.?\s*)?(?:Introduction|INTRODUCTION)", "introduction"),
        (r"(?:^|\n)(?:2\.?\s*)?(?:Literature\s*(?:Review)?|RELATED\s*(?:WORK|LITERATURE)|BACKGROUND)", "literature"),
        (r"(?:^|\n)(?:3\.?\s*)?(?:Methodology|Method|Model|Data\s+and\s+Method|Design|Approach)", "methodology"),
        (r"(?:^|\n)(?:4\.?\s*)?(?:Results?|Empirical|Analysis|Findings)", "results"),
        (r"(?:^|\n)(?:5\.?\s*)?(?:Conclusion|Discussion|Summary)", "conclusion"),
        (r"(?:^|\n)(?:Robustness|Sensitivity|Checks?|(?:Additional|Further)\s*Analysis)", "robustness"),
        (r"(?:^|\n)(?:Appendix|Supplementary|SI\s+Materials?)", "appendix"),
    ]

    # 中文学术论文的章节标题模式（支持多种分隔符）
    CHINESE_SECTION_PATTERNS = [
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:摘\s*要)", "abstract"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:引\s*言|研究背景)", "introduction"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:文献综述|研究评述|理论背景)", "literature"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:研究假设|假\s*说|理论分析|机制分析)", "hypothesis"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:研究设计|实证设计|样本与数据|变量定义|模型设定|研究方法)", "methodology"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:实证结果|实证分析|回归结果|检验结果)", "results"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:稳健性检验|进一步分析|内生性|异质性)", "robustness"),
        (r"(?:^|\n)(?:[一二三四五六七八九十]+)[、，,]\s*(?:研究结论|结论与启示|主要结论)", "conclusion"),
        (r"附\s*(?:录|表|图)|参考文献", "appendix"),
    ]

    def chunk_paper(
        self,
        paper_text: str,
        paper_id: str,
        metadata: PaperMetadata | None = None,
    ) -> list[PaperSection]:
        """将论文文本分块为语义章节。"""
        sections: list[PaperSection] = []
        meta = metadata or {}

        # 尝试多种分块策略
        sections = self._chunk_by_structure(paper_text, paper_id, meta)
        if not sections:
            # Fallback: 固定窗口分块
            sections = self._chunk_fixed(paper_text, paper_id, meta)

        # 去重
        seen = set()
        unique = []
        for s in sections:
            if s.content.strip() and s.section_id not in seen:
                seen.add(s.section_id)
                unique.append(s)

        return unique

    def _chunk_by_structure(
        self, text: str, paper_id: str, meta: PaperMetadata,
    ) -> list[PaperSection]:
        """按论文结构分块。"""
        # 检测语言
        patterns = self.CHINESE_SECTION_PATTERNS if self._is_chinese(text) else self.ENGLISH_SECTION_PATTERNS

        # 找所有章节标题位置
        section_boundaries: list[tuple[int, str]] = []  # (position, section_name)

        for line_pattern, section_name in patterns:
            for m in re.finditer(line_pattern, text, re.MULTILINE):
                section_boundaries.append((m.start(), section_name))

        # 按位置排序
        section_boundaries.sort(key=lambda x: x[0])

        if len(section_boundaries) < 2:
            return []

        # 提取每个章节
        sections = []
        for i, (start_pos, section_name) in enumerate(section_boundaries):
            end_pos = section_boundaries[i + 1][0] if i + 1 < len(section_boundaries) else len(text)
            content = text[start_pos:end_pos].strip()

            if len(content) < 100:  # 太短的跳过
                continue

            section_id = f"{paper_id}__{section_name}__{hashlib.md5(content[:50].encode(), usedforsecurity=False).hexdigest()[:8]}"
            sections.append(PaperSection(
                section_id=section_id,
                paper_id=paper_id,
                section_name=section_name,
                content=content[:8000],  # 截断避免超长
                word_count=self._count_words(content),
                start_char=start_pos,
                end_char=end_pos,
                metadata=meta,
            ))

        return sections

    def _chunk_fixed(
        self, text: str, paper_id: str, meta: PaperMetadata,
        chunk_size: int = 2000, overlap: int = 200,
    ) -> list[PaperSection]:
        """固定窗口分块（fallback）。"""
        sections = []
        start = 0
        idx = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            content = text[start:end].strip()
            if content:
                section_id = f"{paper_id}__chunk__{idx:04d}__{hashlib.md5(content[:50].encode(), usedforsecurity=False).hexdigest()[:8]}"
                sections.append(PaperSection(
                    section_id=section_id,
                    paper_id=paper_id,
                    section_name="body",
                    content=content,
                    word_count=self._count_words(content),
                    start_char=start,
                    end_char=end,
                    metadata=meta,
                ))
            start = end - overlap
            idx += 1

        return sections

    def _is_chinese(self, text: str) -> bool:
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en_words = len([w for w in text.split() if w.isascii()])
        return cn_chars > en_words

    def _count_words(self, text: str) -> int:
        cn_words = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en_words = len([w for w in text.split() if w.strip()])
        return cn_words + en_words


# ─── ChromaDB 文献向量库 ──────────────────────────────────────────────────

class LiteratureVectorStore:
    """学术论文向量文献库。

    基于 ChromaDB，支持持久化存储、增量索引、混合检索。

    Usage:
        store = LiteratureVectorStore(persist_dir="data/literature_store")
        store.add_paper(paper_text, metadata={"title": "...", "journal": "JF", ...})
        results = store.hybrid_search("关税政策 创新 DID", top_k=10, section_filter=["methodology", "results"])
    """

    COLLECTION_NAME = "academic_papers"
    RRF_K = 60  # Reciprocal Rank Fusion parameter

    def __init__(
        self,
        persist_dir: str | Path = "data/literature_store",
        embed_model: str = "bge-m3",
        collection_name: str | None = None,
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or self.COLLECTION_NAME

        # ChromaDB 客户端
        self._chroma = None
        self._collection = None
        self._chroma_available = CHROMA_AVAILABLE

        if self._chroma_available:
            self._init_chroma()
        else:
            logger.warning("ChromaDB not installed, using in-memory fallback")

        # 增量索引追踪
        self._sqlite_db = self.persist_dir / "papers_metadata.db"
        self._init_sqlite()

        # Section分块器
        self.chunker = AcademicPaperChunker()

        # Embedding函数（注入）
        self._embed_fn: callable | None = None
        self._embed_model = embed_model

        logger.info(f"LiteratureVectorStore initialized at {self.persist_dir}")

    def _init_chroma(self) -> None:
        """初始化 ChromaDB。"""
        try:
            self._chroma = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._chroma.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "description": "Academic papers literature store"},
            )
            logger.info(f"ChromaDB collection '{self.collection_name}': {self._collection.count()} papers")
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e}, using fallback")
            self._chroma_available = False

    def _init_sqlite(self) -> None:
        """初始化 SQLite 元数据库。"""
        conn = sqlite3.connect(str(self._sqlite_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                journal TEXT,
                year INTEGER,
                authors TEXT,
                keywords TEXT,
                methods TEXT,
                topics TEXT,
                added_at TEXT,
                updated_at TEXT,
                section_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                arxiv_id TEXT,
                doi TEXT,
                url TEXT,
                local_path TEXT,
                citations INTEGER,
                abstract TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_sections (
                section_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                section_name TEXT,
                word_count INTEGER,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_journal ON papers(journal)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)
        """)
        conn.commit()
        conn.close()

    def set_embed_function(self, fn: callable) -> None:
        """注入 embedding 函数。

        fn(texts: list[str]) -> list[list[float]]
        返回的向量必须是 cosine-normalized 的。
        """
        self._embed_fn = fn

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """获取文本的embedding向量。"""
        if self._embed_fn:
            return self._embed_fn(texts)

        # Fallback: 使用 OpenAI API
        try:
            import os, requests
            api_key = os.getenv("OPENAI_API_KEY", "")
            if api_key:
                return self._openai_embed(texts, api_key)
        except Exception:  # noqa: S110
            pass

        # 随机向量 fallback（仅测试用）
        logger.warning("No embedding function set, using random vectors (NOT for production)")
        dim = 1536
        return np.random.randn(len(texts), dim).astype(float).tolist() if NP_AVAILABLE else [[0.0] * 1536] * len(texts)

    def _openai_embed(self, texts: list[str], api_key: str) -> list[list[float]]:
        """通过 OpenAI API 获取 embedding。"""
        import requests
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        embeddings = []
        for i in range(0, len(texts), 100):
            batch = texts[i:i + 100]
            payload = {"model": "text-embedding-3-small", "input": [t[:8000] for t in batch]}
            r = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers, json=payload, timeout=30,
            )
            r.raise_for_status()
            for item in r.json()["data"]:
                embeddings.append(item["embedding"])
        return embeddings

    def add_paper(
        self,
        paper_text: str,
        metadata: PaperMetadata,
    ) -> int:
        """添加论文到向量库。返回添加的 section 数量。"""
        paper_id = metadata.get("paper_id", f"paper_{uuid.uuid4().hex[:8]}")

        # 检查是否已存在
        if self._paper_exists(paper_id):
            logger.info(f"Paper {paper_id} already exists, skipping")
            return 0

        # Section级分块
        sections = self.chunker.chunk_paper(paper_text, paper_id, metadata)
        if not sections:
            logger.warning(f"No sections extracted for paper {paper_id}")
            return 0

        # 存储到 ChromaDB
        ids = []
        documents = []
        metadatas = []
        embeddings = []

        for sec in sections:
            ids.append(sec.section_id)
            documents.append(sec.content)
            metadatas.append({
                "paper_id": sec.paper_id,
                "section_name": sec.section_name,
                "word_count": sec.word_count,
                "journal": metadata.get("journal", ""),
                "year": metadata.get("year", 0),
                "title": metadata.get("title", ""),
                "authors": ",".join(metadata.get("authors", [])),
                "methods": ",".join(metadata.get("methods", [])),
                "topics": ",".join(metadata.get("topics", [])),
            })

        # 批量embedding
        try:
            embeddings = self._embed_texts(documents)
        except Exception as e:
            logger.error(f"Embedding failed for {paper_id}: {e}")
            return 0

        # 写入 ChromaDB
        if self._chroma_available and self._collection is not None:
            try:
                self._collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
            except Exception as e:
                logger.error(f"ChromaDB add failed: {e}")

        # 更新 SQLite
        self._upsert_paper_metadata(paper_id, metadata, sections)

        logger.info(f"Added paper {paper_id}: {len(sections)} sections")
        return len(sections)

    def add_pdf(
        self,
        pdf_path: str | Path,
        metadata: PaperMetadata,
        parse_fn: callable | None = None,
    ) -> int:
        """从 PDF 文件添加论文。

        Parameters
        ----------
        pdf_path : str | Path
            PDF 文件路径
        metadata : PaperMetadata
            论文元数据
        parse_fn : callable, optional
            PDF 解析函数，签名为 parse_fn(path) -> str（返回纯文本）
            默认使用 PyMuPDF (fitz)
        """
        if parse_fn:
            paper_text = parse_fn(str(pdf_path))
        else:
            paper_text = self._parse_pdf(str(pdf_path))

        if not paper_text:
            logger.warning(f"Failed to parse PDF: {pdf_path}")
            return 0

        if "paper_id" not in metadata:
            metadata["paper_id"] = Path(pdf_path).stem
        metadata["local_path"] = str(pdf_path)

        return self.add_paper(paper_text, metadata)

    def _parse_pdf(self, pdf_path: str) -> str:
        """解析 PDF 为纯文本。"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts)
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    return "\n".join(page.extract_text() or "" for page in pdf.pages)
            except ImportError:
                logger.warning("No PDF parser available (PyMuPDF or pdfplumber)")
                return ""

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        section_filter: list[str] | None = None,
        journal_filter: str | None = None,
        year_range: tuple[int, int] | None = None,
        method_filter: list[str] | None = None,
        return_sections: bool = True,
    ) -> list[LiteratureQueryResult]:
        """混合检索：向量 + BM25 + RRF重排。

        Parameters
        ----------
        query : str
            检索查询
        top_k : int
            返回前 K 条结果
        section_filter : list[str], optional
            仅检索特定章节，如 ["methodology", "results"]
        journal_filter : str, optional
            仅检索特定期刊，如 "JF"
        year_range : tuple, optional
            年份范围，如 (2020, 2024)
        method_filter : list[str], optional
            特定方法，如 ["DID", "IV", "RCT"]
        return_sections : bool
            是否返回 PaperSection 对象（False则只返回metadata）

        Returns
        -------
        list[LiteratureQueryResult]
            排序后的检索结果
        """
        if not self._chroma_available:
            return self._memory_fallback_search(query, top_k)

        # 扩展 top_k（重排后取前top_k）
        search_k = min(top_k * 3, 100)

        # 向量检索
        query_emb = self._embed_texts([query])[0]
        where_filter: dict = {}
        if section_filter:
            where_filter["section_name"] = {"$in": section_filter}
        if journal_filter:
            where_filter["journal"] = journal_filter
        if year_range:
            where_filter["year"] = {"$gte": year_range[0], "$lte": year_range[1]}
        if method_filter:
            ",".join(method_filter)
            where_filter["methods"] = {"$contains": method_filter[0]}

        try:
            if where_filter:
                results = self._collection.query(
                    query_embeddings=[query_emb],
                    n_results=search_k,
                    where=where_filter if where_filter else None,
                    include=["metadatas", "distances", "documents"],
                )
            else:
                results = self._collection.query(
                    query_embeddings=[query_emb],
                    n_results=search_k,
                    include=["metadatas", "distances", "documents"],
                )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

        if not results or not results.get("ids"):
            return []

        ids = results["ids"][0]
        distances = results["distances"][0]
        metadatas = results["metadatas"][0]
        documents = results.get("documents", [[]])[0]

        # 计算 cosine similarity (distances 在 cosine 下是 0-2, 0=完全相同)
        vector_scores = [1 - d / 2 for d in distances]

        # BM25 分数
        bm25_scores = self._bm25_score_documents(query, documents)

        # RRF 融合
        combined = self._rrf_fusion(
            vector_scores, bm25_scores, ids, k=self.RRF_K,
        )

        # 排序
        combined.sort(key=lambda x: x["combined_score"], reverse=True)

        # 构建结果
        output = []
        for rank, item in enumerate(combined[:top_k], 1):
            idx = item["idx"]
            meta = metadatas[idx]
            paper_meta = self._get_paper_metadata(meta["paper_id"]) or {}

            if return_sections:
                section = PaperSection(
                    section_id=ids[idx],
                    paper_id=meta["paper_id"],
                    section_name=meta.get("section_name", "body"),
                    content=documents[idx] if idx < len(documents) else "",
                    word_count=meta.get("word_count", 0),
                    start_char=0,
                    end_char=0,
                    metadata=paper_meta,
                )
            else:
                section = None

            output.append(LiteratureQueryResult(
                section=section,
                paper_metadata=paper_meta,
                vector_score=vector_scores[idx],
                bm25_score=bm25_scores[idx],
                combined_score=item["combined_score"],
                rank=rank,
                matched_keywords=self._extract_keywords(query),
            ))

        return output

    def _rrf_fusion(
        self,
        vector_scores: list[float],
        bm25_scores: list[float],
        ids: list[str],
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion 合并多路检索结果。"""
        # 按向量分数排序
        vec_ranked = sorted(enumerate(vector_scores), key=lambda x: x[1], reverse=True)
        bm25_ranked = sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)

        rrf_scores: dict[int, float] = {}

        for rank, (idx, _) in enumerate(vec_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1 / (k + rank + 1)

        for rank, (idx, _) in enumerate(bm25_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1 / (k + rank + 1)

        return [
            {"idx": idx, "combined_score": score}
            for idx, score in rrf_scores.items()
        ]

    def _bm25_score_documents(self, query: str, documents: list[str]) -> list[float]:
        """计算 BM25 分数（简化实现）。"""
        import math
        query_terms = self._tokenize(query)
        if not query_terms:
            return [0.0] * len(documents)

        avgdl = sum(len(self._tokenize(d)) for d in documents) / max(len(documents), 1)
        k1, b = 1.5, 0.75
        scores = []

        for doc in documents:
            doc_terms = self._tokenize(doc)
            dl = len(doc_terms)
            score = 0.0
            for term in query_terms:
                tf = doc_terms.count(term)
                if tf > 0:
                    idf = math.log((len(documents) + 0.5) / (max(tf, 1) + 0.5))
                    score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            scores.append(score)

        if not scores:
            return [0.0]
        max_s = max(scores)
        return [s / max_s if max_s > 0 else 0 for s in scores]

    def _tokenize(self, text: str) -> list[str]:
        """分词（英文按空格，中文用jieba或字符级）。"""
        en_tokens = text.lower().split()
        cn_chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
        try:
            import jieba
            cn_tokens = list(jieba.cut(text))
        except ImportError:
            cn_tokens = cn_chars
        return en_tokens + cn_tokens

    def _extract_keywords(self, query: str) -> list[str]:
        """从查询中提取关键词。"""
        stopwords = {"的", "是", "在", "和", "了", "对", "有", "研究", "分析", "the", "a", "an", "of", "in", "for", "and"}
        tokens = self._tokenize(query)
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def _memory_fallback_search(
        self, query: str, top_k: int,
    ) -> list[LiteratureQueryResult]:
        """无 ChromaDB 时的内存检索。"""
        logger.warning("Using in-memory fallback search (no ChromaDB)")
        conn = sqlite3.connect(str(self._sqlite_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM papers ORDER BY year DESC LIMIT ?", (top_k,)
        ).fetchall()
        conn.close()

        results = []
        for i, row in enumerate(rows, 1):
            bm25 = self._bm25_score_documents(query, [row["abstract"] or ""])[0]
            results.append(LiteratureQueryResult(
                section=None,
                paper_metadata={"paper_id": row["paper_id"], "title": row["title"],
                               "journal": row["journal"], "year": row["year"]},
                vector_score=0.0,
                bm25_score=bm25,
                combined_score=bm25,
                rank=i,
                matched_keywords=self._extract_keywords(query),
            ))
        return results[:top_k]

    def _paper_exists(self, paper_id: str) -> bool:
        conn = sqlite3.connect(str(self._sqlite_db))
        exists = conn.execute(
            "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone() is not None
        conn.close()
        return exists

    def _upsert_paper_metadata(
        self, paper_id: str, meta: PaperMetadata, sections: list[PaperSection],
    ) -> None:
        conn = sqlite3.connect(str(self._sqlite_db))
        conn.execute("""
            INSERT OR REPLACE INTO papers
            (paper_id, title, journal, year, authors, keywords, methods, topics,
             added_at, updated_at, section_count, chunk_count, arxiv_id, doi, url,
             local_path, citations, abstract)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            meta.get("title", ""),
            meta.get("journal", ""),
            meta.get("year", 0),
            ",".join(meta.get("authors", [])),
            ",".join(meta.get("keywords", [])),
            ",".join(meta.get("methods", [])),
            ",".join(meta.get("topics", [])),
            meta.get("added_at", datetime.now().isoformat()),
            datetime.now().isoformat(),
            len(sections),
            sum(s.word_count for s in sections),
            meta.get("arxiv_id"),
            meta.get("doi"),
            meta.get("url"),
            meta.get("local_path"),
            meta.get("citations"),
            meta.get("abstract"),
        ))
        for sec in sections:
            conn.execute(
                "INSERT OR REPLACE INTO paper_sections (section_id, paper_id, section_name, word_count) VALUES (?, ?, ?, ?)",
                (sec.section_id, sec.paper_id, sec.section_name, sec.word_count),
            )
        conn.commit()
        conn.close()

    def _get_paper_metadata(self, paper_id: str) -> PaperMetadata | None:
        conn = sqlite3.connect(str(self._sqlite_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return PaperMetadata(
            paper_id=row["paper_id"],
            title=row["title"],
            journal=row["journal"],
            year=row["year"],
            authors=row["authors"].split(",") if row["authors"] else [],
            keywords=row["keywords"].split(",") if row["keywords"] else [],
            methods=row["methods"].split(",") if row["methods"] else [],
            topics=row["topics"].split(",") if row["topics"] else [],
            added_at=row["added_at"],
            updated_at=row["updated_at"],
            abstract=row["abstract"],
            local_path=row["local_path"],
            arxiv_id=row["arxiv_id"],
            doi=row["doi"],
            url=row["url"],
            citations=row["citations"],
        )

    def get_stats(self) -> dict:
        """获取文献库统计。"""
        conn = sqlite3.connect(str(self._sqlite_db))
        conn.row_factory = sqlite3.Row
        n_papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        n_sections = conn.execute("SELECT COUNT(*) FROM paper_sections").fetchone()[0]
        journals = conn.execute(
            "SELECT journal, COUNT(*) as cnt FROM papers WHERE journal != '' GROUP BY journal ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        years = conn.execute(
            "SELECT MIN(year), MAX(year) FROM papers WHERE year > 1900"
        ).fetchone()
        conn.close()

        chroma_count = 0
        if self._chroma_available and self._collection is not None:
            chroma_count = self._collection.count()

        return {
            "total_papers": n_papers,
            "total_sections": n_sections,
            "chroma_documents": chroma_count,
            "journals": [{"journal": r["journal"], "count": r["cnt"]} for r in journals],
            "year_range": years if years and years[0] else None,
            "persist_dir": str(self.persist_dir),
        }

    def delete_paper(self, paper_id: str) -> bool:
        """删除论文。"""
        if self._chroma_available and self._collection is not None:
            try:
                self._collection.delete(where={"paper_id": paper_id})
            except Exception as e:
                logger.warning(f"ChromaDB delete failed: {e}")

        conn = sqlite3.connect(str(self._sqlite_db))
        conn.execute("DELETE FROM paper_sections WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
        conn.commit()
        conn.close()
        return True
