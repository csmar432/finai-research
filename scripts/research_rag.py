#!/usr/bin/env python3
"""
学术 RAG 模块
============
基于 FAISS + sentence-transformers 的检索增强生成（RAG）系统。
用于学术研究场景：论文片段检索、研究笔记问答、文献综述辅助写作。

核心组件：
  - Chunk: 文本片段（带元数据）
  - ResearchRAG: 管理 chunks、embeddings、FAISS 索引
  - 混合搜索：向量相似度 + BM25 融合
  - RAG 管道：检索 → 格式化 → LLM 生成

集成：
  - ai_router.AI 做 LLM 调用
  - 可选 cross-encoder 重排序
  - 可选连接 knowledge_graph 提供引文上下文

用法：
  rag = ResearchRAG()
  rag.chunk_paper(paper_text)
  rag.embed_chunks(rag.chunks)
  rag.build_index()
  result = rag.rag_query("LLM在金融领域有哪些应用？", llm_model="deepseek")

作者：Paper-Report Workflow
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

# ── 日志配置 ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── 延迟导入（可选依赖）────────────────────────────────────────────────────

def _try_import(name: str, package: str | None = None):
    """延迟导入可选依赖。"""
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError:
        logger.warning(f"  可选依赖 '{name}' 未安装，部分功能将不可用")
        return None


FAISS_AVAILABLE = _try_import("faiss") is not None
ST_AVAILABLE = _try_import("sentence_transformers") is not None
CJK_AVAILABLE = _try_import("jieba") is not None


# ── 数据模型 ────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """
    文本片段。
    """
    id: str                          # 唯一 ID（chunk_xxxx）
    content: str                     # 文本内容
    paper_id: str = ""               # 所属论文 ID
    section: str = ""                # 章节名（Introduction/Method 等）
    source: str = ""                 # 来源（pdf/txt/markdown）
    chunk_index: int = 0             # 在原文中的序号
    start_char: int = 0             # 在原文中的起始字符位置
    end_char: int = 0               # 在原文中的结束字符位置

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Chunk:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RetrievalResult:
    """检索结果。"""
    chunk: Chunk
    score: float                    # 相似度分数
    rank: int                       # 排名


# ── Embedding 生成器 ───────────────────────────────────────────────────────

class Embedder:
    """
    文本向量化。
    优先使用 sentence-transformers（支持中文），fallback 到 OpenAI ada-002。
    """

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self.model = None
        self.dimension = 0
        self._init_model()

    def _init_model(self):
        if ST_AVAILABLE:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                self.dimension = self.model.get_sentence_embedding_dimension()
                logger.info(f"  Embedder: {self.model_name} (dim={self.dimension})")
                return
            except Exception as e:
                logger.warning(f"  sentence-transformers 加载失败: {e}")

        if FAISS_AVAILABLE:
            logger.info("  Embedder: 使用 OpenAI ada-002（需配置 API Key）")
            self.dimension = 1536
        else:
            logger.warning("  Embedder: 无可用 embedding 模型，将使用随机向量（仅用于测试）")
            self.dimension = 384

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """
        将文本列表编码为向量。

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            numpy 数组，shape = (len(texts), dimension)
        """
        if not texts:
            return np.array([]).reshape(0, self.dimension)

        if self.model is not None:
            try:
                embeddings = self.model.encode(
                    texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
                return embeddings.astype("float32")
            except Exception as e:
                logger.warning(f"  sentence-transformers encode 失败: {e}")

        return self._encode_openai_fallback(texts)

    def _encode_openai_fallback(self, texts: list[str]) -> np.ndarray:
        """Fallback 到 OpenAI ada-002。"""
        try:
            from openai import OpenAI
            client = OpenAI()

            def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
                text = text.replace("\n", " ")[:8000]
                resp = client.embeddings.create(
                    input=text,
                    model=model,
                )
                return resp.data[0].embedding

            embeddings = []
            for i in range(0, len(texts), 100):
                batch = texts[i:i + 100]
                for text in batch:
                    emb = get_embedding(text)
                    embeddings.append(emb)
                    if i + len(embeddings) < len(texts):
                        import time
                        time.sleep(0.1)

            return np.array(embeddings, dtype="float32")
        except Exception as e:
            logger.warning(f"  OpenAI embedding 失败: {e}，使用随机向量")
            return np.random.randn(len(texts), self.dimension).astype("float32")


# ── BM25 搜索引擎 ──────────────────────────────────────────────────────────

class BM25Searcher:
    """
    BM25 全文检索（用于混合搜索）。
    使用 jieba 中文分词，fallback 到英文 tokenize。
    """

    def __init__(self):
        self.documents: dict[str, str] = {}
        self.doc_ids: list[str] = []
        self.corpus: list[str] = []
        self._index = None
        self._avgdl = 0
        self._k1 = 1.5
        self._b = 0.75

    def add_documents(self, docs: dict[str, str]) -> None:
        """
        添加文档。
        Args:
            docs: {chunk_id: text}
        """
        self.documents.update(docs)
        self.doc_ids = list(self.documents.keys())
        self.corpus = [self.documents[did] for did in self.doc_ids]
        self._build_index()

    def _tokenize(self, text: str) -> list[str]:
        """分词。"""
        text = text.lower()
        if CJK_AVAILABLE:
            import jieba
            tokens = list(jieba.cut(text))
        else:
            tokens = re.findall(r"[a-z0-9]+", text)
        return tokens

    def _build_index(self):
        """构建倒排索引。"""
        if not self.corpus:
            return
        self._index = {}
        N = len(self.corpus)
        doc_lens = [len(self._tokenize(doc)) for doc in self.corpus]
        self._avgdl = sum(doc_lens) / N if N > 0 else 1

        for i, doc in enumerate(self.corpus):
            tokens = self._tokenize(doc)
            for token in tokens:
                if token not in self._index:
                    self._index[token] = {"df": 0, "postings": []}
                self._index[token]["df"] += 1
                self._index[token]["postings"].append(i)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        BM25 搜索。

        Returns:
            [(chunk_id, score), ...]
        """
        if not self._index or not self.corpus:
            return []

        q_tokens = self._tokenize(query)
        scores: dict[int, float] = {}

        N = len(self.corpus)
        for token in q_tokens:
            if token not in self._index:
                continue
            df = self._index[token]["df"]
            idf = np.log((N - df + 0.5) / (df + 0.5) + 1)
            for doc_idx in self._index[token]["postings"]:
                doc_len = len(self._tokenize(self.corpus[doc_idx]))
                term_freq = self._tokenize(self.corpus[doc_idx]).count(token)
                score = idf * term_freq * (self._k1 + 1) / (
                    term_freq + self._k1 * (1 - self._b + self._b * doc_len / self._avgdl)
                )
                scores[doc_idx] = scores.get(doc_idx, 0) + score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(self.doc_ids[idx], score) for idx, score in ranked[:top_k]]


# ── Cross-Encoder 重排序 ────────────────────────────────────────────────────

class Reranker:
    """
    Cross-Encoder 重排序。
    使用 ms-marco-MiniLM-L-6-v2 对检索结果重排序。
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = None
        self.model_name = model_name
        self._init_model()

    def _init_model(self):
        if ST_AVAILABLE:
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name)
                logger.info(f"  Reranker: {self.model_name}")
                return
            except Exception as e:
                logger.warning(f"  Cross-Encoder 加载失败: {e}")

    def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        scores: list[float],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """
        对检索结果重排序。

        Args:
            query: 查询文本
            chunks: 检索到的 chunks
            scores: 原始相似度分数
            top_k: 返回 top_k 结果

        Returns:
            重排序后的 RetrievalResult 列表
        """
        if self.model is None or not chunks:
            return [
                RetrievalResult(chunk=c, score=s, rank=i + 1)
                for i, (c, s) in enumerate(zip(chunks, scores))
            ]

        try:
            pairs = [(query, chunk.content) for chunk in chunks]
            cross_scores = self.model.predict(pairs)

            reranked = sorted(
                zip(chunks, cross_scores),
                key=lambda x: x[1],
                reverse=True,
            )
            return [
                RetrievalResult(chunk=c, score=float(s), rank=i + 1)
                for i, (c, s) in enumerate(reranked[:top_k])
            ]
        except Exception as e:
            logger.warning(f"  Cross-Encoder 重排序失败: {e}")
            return [
                RetrievalResult(chunk=c, score=s, rank=i + 1)
                for i, (c, s) in enumerate(zip(chunks, scores))
            ]


# ── FAISS 索引管理 ─────────────────────────────────────────────────────────

class FAISSIndex:
    """
    FAISS 向量索引封装。
    支持 IndexFlatIP（内积，cosine similarity）和 IndexIVFFlat。
    """

    def __init__(self, dimension: int = 384, metric: str = "cosine"):
        self.dimension = dimension
        self.metric = metric
        self.index = None
        self._chunk_ids: list[str] = []
        self._chunks_map: dict[str, Chunk] = {}
        self._embeddings: np.ndarray | None = None

    def add(self, chunk_ids: list[str], embeddings: np.ndarray, chunks: list[Chunk]) -> None:
        """
        添加向量到索引。

        Args:
            chunk_ids: chunk ID 列表
            embeddings: 向量数组 (N, dimension)
            chunks: Chunk 对象列表
        """
        if embeddings.shape[0] == 0:
            return

        if not FAISS_AVAILABLE:
            logger.warning("  FAISS 未安装，使用内存向量搜索")
            self._chunk_ids.extend(chunk_ids)
            self._chunks_map.update({c.id: c for c in chunks})
            self._embeddings = (
                np.vstack([self._embeddings, embeddings])
                if self._embeddings is not None
                else embeddings
            )
            return

        embeddings = np.asarray(embeddings, dtype="float32")

        if self.metric == "cosine":
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            embeddings = embeddings / norms

        if self.index is None:
            self.index = faiss.IndexFlatIP(self.dimension)

        self.index.add(embeddings)
        self._chunk_ids.extend(chunk_ids)
        self._chunks_map.update({c.id: c for c in chunks})

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
        """
        向量检索。

        Returns:
            [(chunk_id, score), ...]
        """
        if not FAISS_AVAILABLE:
            return self._memory_search(query_embedding, top_k)

        if self.index is None or self.index.ntotal == 0:
            return []

        q = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
        if self.metric == "cosine":
            norm = np.linalg.norm(q)
            if norm > 0:
                q = q / norm

        k = min(top_k, self.index.ntotal)
        distances, indices = self.index.search(q, k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self._chunk_ids):
                results.append((self._chunk_ids[idx], float(dist)))
        return results

    def _memory_search(self, query: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """内存版向量搜索（无 FAISS 时 fallback）。"""
        if self._embeddings is None or len(self._embeddings) == 0:
            return []
        q = query.reshape(1, -1)
        sims = np.dot(self._embeddings, q.T).flatten()
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [(self._chunk_ids[i], float(sims[i])) for i in top_idx]

    def save(self, path: str | Path) -> None:
        """保存索引到磁盘。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if FAISS_AVAILABLE and self.index is not None:
            faiss.write_index(self.index, str(path))
            logger.info(f"  FAISS 索引已保存: {path}")

        chunks_path = path.with_suffix(".chunks.json")
        chunks_data = {
            "chunk_ids": self._chunk_ids,
            "chunks": [c.to_dict() for c in self._chunks_map.values()],
            "dimension": self.dimension,
            "metric": self.metric,
            "saved_at": datetime.now().isoformat(),
        }
        chunks_path.write_text(json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"  Chunks 元数据已保存: {chunks_path}")

    def load(self, path: str | Path) -> bool:
        """从磁盘加载索引。"""
        path = Path(path)
        chunks_path = path.with_suffix(".chunks.json")

        if not path.exists():
            logger.error(f"  索引文件不存在: {path}")
            return False

        if not chunks_path.exists():
            logger.error(f"  Chunks 元数据不存在: {chunks_path}")
            return False

        try:
            if FAISS_AVAILABLE:
                self.index = faiss.read_index(str(path))
                self.dimension = self.index.d

            chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
            self._chunk_ids = chunks_data.get("chunk_ids", [])
            self._chunks_map = {
                c["id"]: Chunk.from_dict(c)
                for c in chunks_data.get("chunks", [])
            }
            self.metric = chunks_data.get("metric", "cosine")
            logger.info(f"  FAISS 索引已加载: {len(self._chunk_ids)} 条记录")
            return True
        except Exception as e:
            logger.error(f"  索引加载失败: {e}")
            return False


# ── Research RAG 主类 ──────────────────────────────────────────────────────

class ResearchRAG:
    """
    学术 RAG 系统。
    整合 chunking、embedding、FAISS 索引、混合搜索、RAG 查询。
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        self.chunks: list[Chunk] = []
        self.chunk_map: dict[str, Chunk] = {}
        self._chunk_ids: list[str] = []  # Parallel list to chunks for index alignment
        self.embedder = embedder or Embedder()
        self.faiss_index = FAISSIndex(dimension=self.embedder.dimension)
        self.bm25 = BM25Searcher()
        self.reranker = Reranker()
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._embedding_cache: dict[str, np.ndarray] = {}
        self._initialized = False

    # ── Chunking ───────────────────────────────────────────────────────────

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """添加预分好的 chunks。"""
        added = 0
        for chunk in chunks:
            if chunk.id not in self.chunk_map:
                self.chunks.append(chunk)
                self.chunk_map[chunk.id] = chunk
                added += 1
        return added

    def chunk_paper(
        self,
        paper_text: str,
        paper_id: str = "",
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[Chunk]:
        """
        将论文文本拆分为 chunks。

        Args:
            paper_text: 论文纯文本
            paper_id: 论文 ID（用于元数据）
            chunk_size: 每段字数（默认 500）
            overlap: 相邻段重叠字数（默认 50）

        Returns:
            生成的 Chunk 列表
        """
        cs = chunk_size or self.chunk_size
        ov = overlap or self.overlap

        if cs <= ov:
            raise ValueError("chunk_size 必须大于 overlap")

        text = paper_text.strip()
        if not text:
            return []

        chunks: list[Chunk] = []
        start = 0
        idx = 0

        while start < len(text):
            end = start + cs
            if end >= len(text):
                end = len(text)
            else:
                line_break = text.rfind("\n", start + cs - 100, end)
                if line_break > start + cs // 2:
                    end = line_break + 1

            content = text[start:end].strip()
            if content:
                chunk_id = self._gen_chunk_id(content, idx)
                chunk = Chunk(
                    id=chunk_id,
                    content=content,
                    paper_id=paper_id,
                    section=self._detect_section(content),
                    source="paper",
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                )
                chunks.append(chunk)
                idx += 1

            start = end - ov
            if start < 0:
                start = 0

        self.add_chunks(chunks)
        logger.info(f"  论文分块完成: {len(chunks)} 个 chunks")
        return chunks

    def chunk_research_notes(self, notes_dir: str | Path) -> list[Chunk]:
        """
        将 knowledge/ 目录下的所有 markdown 文件分块。

        Args:
            notes_dir: 笔记目录路径

        Returns:
            生成的 Chunk 列表
        """
        notes_dir = Path(notes_dir)
        if not notes_dir.exists():
            logger.warning(f"  笔记目录不存在: {notes_dir}")
            return []

        all_chunks: list[Chunk] = []
        md_files = list(notes_dir.glob("**/*.md"))

        logger.info(f"  扫描笔记目录: {len(md_files)} 个 .md 文件")
        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8")
                rel_path = str(md_file.relative_to(notes_dir))
                chunks = self.chunk_paper(text, paper_id=rel_path)
                for c in chunks:
                    c.source = "notes"
                all_chunks.extend(chunks)
            except Exception as e:
                logger.warning(f"  读取失败 {md_file}: {e}")

        logger.info(f"  笔记分块完成: {len(all_chunks)} 个 chunks")
        return all_chunks

    def _detect_section(self, text: str) -> str:
        """根据文本内容推断章节。"""
        text_lower = text.lower()[:200]
        section_keywords = {
            "abstract": ["abstract", "摘要"],
            "introduction": ["introduction", "1.", "一、引", "二、引", "背景"],
            "related work": ["related work", "literature review", "文献综述"],
            "method": ["method", "methodology", "model", "approach", "方法"],
            "experiment": ["experiment", "evaluation", "results", "实验", "结果"],
            "conclusion": ["conclusion", "summary", "conclude", "总结", "结论"],
            "reference": ["reference", "bibliography", "参考文献"],
        }
        for sec, keywords in section_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return sec
        return "body"

    def _gen_chunk_id(self, content: str, idx: int) -> str:
        """生成稳定的 chunk ID。"""
        prefix = hashlib.md5(content.encode()).hexdigest()[:6]
        return f"chunk_{prefix}_{idx:04d}"

    # ── Embedding ───────────────────────────────────────────────────────────

    def embed_chunks(self, chunks: list[Chunk] | None = None) -> None:
        """
        为 chunks 生成 embedding 向量。

        Args:
            chunks: 要嵌入的 chunks（默认用 self.chunks）
        """
        target = chunks or self.chunks
        if not target:
            return

        texts = [c.content for c in target]
        logger.info(f"  生成 embedding: {len(texts)} 个")

        embeddings = self.embedder.encode(texts)

        for chunk, emb in zip(target, embeddings):
            self._embedding_cache[chunk.id] = emb

        logger.info(f"  Embedding 生成完成: {embeddings.shape}")

    def _ensure_embeddings(self) -> None:
        """确保所有 chunks 都有 embedding。"""
        unembedded = [c for c in self.chunks if c.id not in self._embedding_cache]
        if unembedded:
            self.embed_chunks(unembedded)

    # ── 索引构建 ────────────────────────────────────────────────────────────

    def build_index(self) -> None:
        """构建 FAISS 索引和 BM25 索引。"""
        self._ensure_embeddings()

        if not self.chunks:
            logger.warning("  没有 chunks，跳过索引构建")
            return

        chunk_ids = [c.id for c in self.chunks]
        embeddings = np.stack([self._embedding_cache[c.id] for c in self.chunks])

        self.faiss_index = FAISSIndex(dimension=self.embedder.dimension)
        self.faiss_index.add(chunk_ids, embeddings, self.chunks)

        doc_dict = {c.id: c.content for c in self.chunks}
        self.bm25.add_documents(doc_dict)

        self._initialized = True
        logger.info(f"  索引构建完成: {len(self.chunks)} 个 chunks")

    # ── 检索 ────────────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        纯向量检索。

        Args:
            query: 查询文本
            top_k: 返回 top_k 结果

        Returns:
            RetrievalResult 列表
        """
        if not self._initialized:
            self.build_index()

        q_emb = self.embedder.encode([query])[0]
        results = self.faiss_index.search(q_emb, top_k=top_k)

        retrieval_results = []
        for chunk_id, score in results:
            chunk = self.chunk_map.get(chunk_id)
            if chunk:
                retrieval_results.append(RetrievalResult(chunk=chunk, score=score, rank=0))

        return retrieval_results

    def hybrid_search(self, query: str, top_k: int = 5, alpha: float = 0.5) -> list[RetrievalResult]:
        """
        混合搜索：向量相似度 + BM25。

        Args:
            query: 查询文本
            top_k: 返回 top_k 结果
            alpha: 向量权重（0=纯 BM25，1=纯向量）

        Returns:
            融合后的 RetrievalResult 列表
        """
        if not self._initialized:
            self.build_index()

        top_k_extended = top_k * 3

        q_emb = self.embedder.encode([query])[0]
        vector_results = dict(self.faiss_index.search(q_emb, top_k=top_k_extended))

        bm25_results = dict(self.bm25.search(query, top_k=top_k_extended))

        all_ids = set(vector_results) | set(bm25_results)
        if not all_ids:
            return []

        max_vector = max(vector_results.values()) if vector_results else 1.0
        max_bm25 = max(bm25_results.values()) if bm25_results else 1.0

        combined: dict[str, float] = {}
        for chunk_id in all_ids:
            vs = (vector_results.get(chunk_id, 0) / max_vector) if max_vector > 0 else 0
            bs = (bm25_results.get(chunk_id, 0) / max_bm25) if max_bm25 > 0 else 0
            combined[chunk_id] = alpha * vs + (1 - alpha) * bs

        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RetrievalResult(
                chunk=self.chunk_map[cid],
                score=score,
                rank=i + 1,
            )
            for i, (cid, score) in enumerate(ranked)
            if cid in self.chunk_map
        ]

    def query_with_context(
        self,
        query: str,
        top_k: int = 5,
        max_context_tokens: int = 4000,
        use_rerank: bool = True,
    ) -> str:
        """
        检索相关 chunks 并格式化为上下文。

        Args:
            query: 查询文本
            top_k: 候选 chunks 数
            max_context_tokens: 最大上下文 token 数（粗略估算：1 token ≈ 1.5 字符）
            use_rerank: 是否使用 cross-encoder 重排序

        Returns:
            格式化的上下文字符串
        """
        if not self._initialized:
            self.build_index()

        top_k_extended = top_k * 2
        candidates = self.hybrid_search(query, top_k=top_k_extended, alpha=0.6)

        if use_rerank and len(candidates) > top_k:
            reranked = self.reranker.rerank(
                query,
                [r.chunk for r in candidates],
                [r.score for r in candidates],
                top_k=top_k,
            )
            candidates = reranked
        else:
            candidates = candidates[:top_k]

        context_parts: list[str] = []
        total_chars = 0
        max_chars = int(max_context_tokens * 1.5)

        for result in candidates:
            chunk = result.chunk
            part = self._format_chunk_context(chunk, result.score, result.rank)
            if total_chars + len(part) > max_chars and context_parts:
                break
            context_parts.append(part)
            total_chars += len(part)

        if not context_parts:
            return "未找到相关上下文。"

        header = f"以下是与你问题相关的 {len(context_parts)} 个文档片段：\n\n"
        return header + "\n\n---\n\n".join(context_parts)

    def _format_chunk_context(self, chunk: Chunk, score: float, rank: int) -> str:
        """格式化单个 chunk 为上下文片段。"""
        meta = []
        if chunk.paper_id:
            meta.append(f"论文: {chunk.paper_id}")
        if chunk.section:
            meta.append(f"章节: {chunk.section}")
        if chunk.source:
            meta.append(f"来源: {chunk.source}")
        meta.append(f"相关度: {score:.3f}")

        meta_str = " | ".join(meta)
        content = chunk.content[:2000]

        return f"[片段 {rank}] ({meta_str})\n{content}"

    # ── RAG 查询 ────────────────────────────────────────────────────────────

    def rag_query(
        self,
        query: str,
        llm_model: str = "deepseek",
        top_k: int = 5,
        max_context_tokens: int = 4000,
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> dict:
        """
        完整的 RAG 管道：检索 → 格式化 → LLM 生成。

        Args:
            query: 用户问题
            llm_model: LLM 模型标识（deepseek / gpt5 / gemini / kimi）
            top_k: 检索的 chunks 数量
            max_context_tokens: 最大上下文 token 数
            temperature: LLM 温度参数
            system_prompt: 自定义系统提示词

        Returns:
            {
                "answer": str,          # LLM 回答
                "sources": list[dict],  # 引用的 sources
                "context": str,         # 原始上下文
                "model_used": str,      # 使用的模型
            }
        """
        context = self.query_with_context(query, top_k=top_k, max_context_tokens=max_context_tokens)

        if system_prompt is None:
            system_prompt = (
                "你是一位专业学术研究助手，擅长根据提供的文档片段回答用户问题。\n"
                "要求：\n"
                "1. 仅基于提供的上下文回答，不要编造信息\n"
                "2. 如果上下文没有足够信息，明确指出\n"
                "3. 引用片段时请注明来源\n"
                "4. 回答用中文，语言专业、简洁\n"
            )

        default_system = system_prompt
        user_prompt = f"## 用户问题\n{query}\n\n## 参考上下文\n{context}"

        try:
            from scripts.core.llm_gateway import LLMGateway
            from scripts.ai_router import Task

            gateway = LLMGateway(memory=None, use_cache=True)
            result = gateway.generate(
                user_prompt,
                task_hint=Task.RESEARCH,
                model=llm_model,
                system=default_system,
                temperature=temperature,
                max_tokens=4096,
            )
            answer = result.response
            model_used = result.model_used
        except ImportError:
            logger.warning("  ai_router 不可用，使用 mock 回答")
            answer = f"[Mock] 基于以下 {top_k} 个片段回答：{context[:200]}..."
            model_used = "mock"

        sources = []
        for r in self.hybrid_search(query, top_k=top_k)[:top_k]:
            sources.append({
                "id": r.chunk.id,
                "content_preview": r.chunk.content[:100],
                "score": r.score,
                "paper_id": r.chunk.paper_id,
                "section": r.chunk.section,
            })

        return {
            "answer": answer,
            "sources": sources,
            "context": context,
            "model_used": model_used,
        }

    # ── 持久化 ──────────────────────────────────────────────────────────────

    def save_index(self, path: str | Path) -> None:
        """保存 FAISS 索引和 chunks。"""
        path = Path(path)
        self.faiss_index.save(path)
        logger.info(f"  RAG 索引已保存: {path}")

    def load_index(self, path: str | Path) -> bool:
        """加载 FAISS 索引。"""
        success = self.faiss_index.load(path)
        if success:
            # Copy from FAISSIndex internal state (loaded from disk)
            self._chunk_ids = list(self.faiss_index._chunk_ids)
            self.chunk_map = dict(self.faiss_index._chunks_map)
            self.chunks = list(self.chunk_map.values())
            self._initialized = True
        return success

    # ── 统计信息 ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回 RAG 系统统计信息。"""
        return {
            "total_chunks": len(self.chunks),
            "papers": len(set(c.paper_id for c in self.chunks if c.paper_id)),
            "sections": len(set(c.section for c in self.chunks)),
            "embedding_dimension": self.embedder.dimension,
            "index_built": self._initialized,
            "reranker_available": self.reranker.model is not None,
        }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="学术 RAG 检索工具")
    parser.add_argument("--query", "-q", help="查询文本")
    parser.add_argument("--notes-dir", "-n", help="笔记目录（自动 chunk）")
    parser.add_argument("--index", "-i", help="加载已有索引")
    parser.add_argument("--output", "-o", help="保存索引路径")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="返回结果数")
    parser.add_argument("--model", "-m", default="deepseek", help="LLM 模型")

    args = parser.parse_args()

    rag = ResearchRAG()

    if args.index:
        rag.load_index(args.index)

    if args.notes_dir:
        rag.chunk_research_notes(args.notes_dir)
        rag.embed_chunks()
        rag.build_index()

    if args.query:
        result = rag.rag_query(args.query, llm_model=args.model, top_k=args.top_k)
        print(f"\n{'='*60}")
        print(f"  问题: {args.query}")
        print(f"  模型: {result['model_used']}")
        print(f"{'='*60}")
        print(f"\n回答:\n{result['answer']}")
        print(f"\n来源 ({len(result['sources'])} 个):")
        for i, src in enumerate(result["sources"], 1):
            print(f"  [{i}] {src['paper_id']} / {src['section']} (score={src['score']:.3f})")

    if args.output:
        rag.save_index(args.output)

    if not args.query and not args.notes_dir:
        parser.print_help()


if __name__ == "__main__":
    main()
