"""
cross_session_knowledge.py — 跨会话知识积累层

扩展 ResearchMemory，增加跨会话知识共享和文献库集成：

1. 跨会话检索（cross_session_search）
   - 搜索所有历史会话的知识，而非仅当前会话
   - 按时间衰减 + 相关性排序

2. 洞察发现（insight_mining）
   - 从历史会话中提取重复出现的研究模式
   - 跨论文的知识关联

3. 文献库同步（sync_to_literature_store）
   - 将 ResearchMemory 中的重要发现同步到 LiteratureVectorStore
   - 构建研究知识图谱

4. 会话历史（session_history）
   - 列出/摘要历史会话
   - 支持会话重建

5. 与 LiteratureVectorStore 双向集成
   - LiteratureVectorStore 查询结果写入 ResearchMemory
   - ResearchMemory 知识自动进入文献索引
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 可选依赖 ────────────────────────────────────────────────────────────────

try:
    from scripts.core.literature_vector_store import LiteratureVectorStore, LiteratureQueryResult
    LITERATURE_STORE_AVAILABLE = True
except ImportError:
    LITERATURE_STORE_AVAILABLE = False
    LiteratureVectorStore = None
    LiteratureQueryResult = None


# ─── 数据类型 ───────────────────────────────────────────────────────────────

@dataclass
class CrossSessionInsight:
    """跨会话洞察。"""
    insight_type: str          # "recurring_pattern" / "knowledge_gap" / "methodology_pattern" / "finding"
    title: str
    description: str
    session_ids: list[str]
    first_appeared: float
    last_appeared: float
    occurrence_count: int
    confidence: float          # 0-1
    related_topics: list[str] = field(default_factory=list)
    linked_papers: list[str] = field(default_factory=list)


@dataclass
class SessionSummary:
    """会话摘要。"""
    session_id: str
    created_at: float
    updated_at: float
    task_count: int
    topics: list[str]
    key_findings: list[str]
    tools_used: list[str]
    research_directions: list[str]


# ─── 跨会话知识管理器 ────────────────────────────────────────────────────

class CrossSessionKnowledge:
    """
    跨会话知识积累管理器。

    特点：
    1. 全会话向量检索（不限当前 session_id）
    2. 洞察挖掘（重复模式、知识缺口）
    3. 知识同步（↔ LiteratureVectorStore）
    4. 会话历史查询

    Usage:
        # 基本用法（自动使用默认数据库路径）
        ck = CrossSessionKnowledge()

        # 跨会话检索
        results = ck.cross_session_search("关税政策 创新 DID", top_k=10)

        # 挖掘洞察
        insights = ck.mine_insights(min_occurrences=2)

        # 同步到文献库
        ck.sync_to_literature_store(literature_store)

        # 查询会话历史
        sessions = ck.list_sessions(limit=10)
    """

    _write_lock = threading.Lock()

    def __init__(
        self,
        db_path: str | None = None,
        literature_store_path: str | None = None,
        embed_fn: callable | None = None,
    ):
        self.db_path = db_path or ".cache/research.db"
        self._ensure_db_dir()
        self._conn = self._connect_db()
        self._init_tables()

        # Literature store 集成
        self._lit_store: LiteratureVectorStore | None = None
        if LITERATURE_STORE_AVAILABLE:
            store_path = literature_store_path or "data/literature_store"
            self._lit_store = LiteratureVectorStore(persist_dir=store_path)
            if embed_fn:
                self._lit_store.set_embed_function(embed_fn)

        # 洞察缓存
        self._insight_cache: list[CrossSessionInsight] = []
        self._insight_cache_time: float = 0
        self._insight_cache_ttl: float = 300  # 5分钟缓存

        logger.info(f"CrossSessionKnowledge initialized: db={self.db_path}")

    def _ensure_db_dir(self):
        d = os.path.dirname(self.db_path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

    def _connect_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """初始化跨会话专用表。"""
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cross_session_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                session_ids TEXT,
                first_appeared REAL,
                last_appeared REAL,
                occurrence_count INTEGER DEFAULT 1,
                confidence REAL DEFAULT 0.5,
                related_topics TEXT,
                linked_papers TEXT,
                created_at REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_session_id TEXT,
                source_type TEXT,
                key TEXT,
                synced_to TEXT,
                synced_at REAL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_insights_type ON cross_session_insights(insight_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_insights_last ON cross_session_insights(last_appeared)
        """)
        with self._write_lock:
            self._conn.commit()

    # ── 跨会话检索 ────────────────────────────────────────────────────────

    def cross_session_search(
        self,
        query: str,
        top_k: int = 10,
        session_filter: list[str] | None = None,
        time_decay: bool = True,
    ) -> list[dict]:
        """
        跨所有历史会话检索知识。

        检索策略：
        1. 精确关键词匹配（SQL LIKE）
        2. 时间衰减排序（近期优先）
        3. session_id 聚合去重

        Args:
            query: 检索查询
            top_k: 返回条数
            session_filter: 仅检索特定 session_ids（None = 全部）
            time_decay: 是否启用时间衰减

        Returns:
            检索结果列表，每项包含知识内容和元数据
        """
        cursor = self._conn.cursor()

        base_sql = """
            SELECT k.key, k.value, k.tags, k.timestamp, k.session_id,
                   s.summary as session_summary
            FROM knowledge k
            LEFT JOIN sessions s ON k.session_id = s.session_id
            WHERE (k.key LIKE ? OR k.value LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if session_filter:
            placeholders = ",".join(["?"] * len(session_filter))
            base_sql += f" AND k.session_id IN ({placeholders})"
            params.extend(session_filter)

        base_sql += " ORDER BY k.timestamp DESC LIMIT ?"
        params.append(top_k * 3)

        try:
            cursor.execute(base_sql, params)
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Cross-session search failed: {e}")
            return []

        # 按 session_id 去重，取每 session 最佳结果
        seen_session: dict[str, dict] = {}
        for row in rows:
            sid = row["session_id"]
            if sid not in seen_session:
                seen_session[sid] = {
                    "key": row["key"],
                    "value": json.loads(row["value"]) if row["value"] else {},
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "timestamp": row["timestamp"],
                    "session_id": sid,
                    "session_summary": row["session_summary"] or "",
                }

        results = list(seen_session.values())

        # 时间衰减
        if time_decay:
            now = time.time()
            decay = 0.95
            for r in results:
                age_days = (now - r["timestamp"]) / 86400
                r["time_weight"] = pow(decay, min(age_days / 30, 12))
                # 综合分数 = 相关性 * 时间权重
                q_lower = query.lower()
                content = (str(r["value"]) + r["key"]).lower()
                r["relevance"] = 1.0 if q_lower in content else 0.3
                r["combined_score"] = r["relevance"] * r["time_weight"]
            results.sort(key=lambda x: x["combined_score"], reverse=True)

        return results[:top_k]

    def search_cross_session_semantic(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """
        语义跨会话检索（需要 ChromaDB + embed_fn）。

        使用 LiteratureVectorStore 的混合检索能力，
        在所有会话的文献知识上做向量搜索。
        """
        if not self._lit_store:
            logger.warning("LiteratureVectorStore not available, falling back to keyword search")
            return self.cross_session_search(query, top_k)

        try:
            results = self._lit_store.hybrid_search(query, top_k=top_k, return_sections=False)
            output = []
            for r in results:
                paper = r.paper_metadata
                output.append({
                    "paper_id": paper.get("paper_id", ""),
                    "title": paper.get("title", ""),
                    "journal": paper.get("journal", ""),
                    "year": paper.get("year", 0),
                    "methods": paper.get("methods", []),
                    "topics": paper.get("topics", []),
                    "combined_score": r.combined_score,
                    "matched_keywords": r.matched_keywords,
                })
            return output
        except Exception as e:
            logger.error(f"Semantic cross-session search failed: {e}")
            return self.cross_session_search(query, top_k)

    # ── 洞察挖掘 ─────────────────────────────────────────────────────────

    def mine_insights(
        self,
        min_occurrences: int = 2,
        force_refresh: bool = False,
    ) -> list[CrossSessionInsight]:
        """
        从历史会话中挖掘跨会话洞察。

        发现的洞察类型：
        - recurring_pattern: 重复出现的研究模式
        - methodology_pattern: 反复使用的方法论
        - finding: 跨多个研究一致的结论
        - knowledge_gap: 被多次提及但未解决的知识缺口

        Args:
            min_occurrences: 最少出现次数
            force_refresh: 强制重新计算（忽略缓存）

        Returns:
            洞察列表
        """
        # 缓存检查
        if not force_refresh and (time.time() - self._insight_cache_time) < self._insight_cache_ttl:
            return [i for i in self._insight_cache if i.occurrence_count >= min_occurrences]

        cursor = self._conn.cursor()

        # 从 contexts 表提取关键词共现
        cursor.execute("""
            SELECT session_id, task, result, timestamp
            FROM contexts
            WHERE is_compressed = 0
            ORDER BY timestamp DESC
            LIMIT 1000
        """)
        rows = cursor.fetchall()

        # 提取高频关键词
        keyword_freq: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"sessions": set(), "timestamps": [], "count": 0}
        )

        for row in rows:
            sid = row["session_id"]
            text = f"{row['task']} {str(row['result'])}"
            ts = row["timestamp"]

            # 简单关键词提取（中文词 + 英文词）
            import re
            en_words = re.findall(r"[A-Z]{2,}[a-z]*[A-Z]*|[a-z]{4,}", text)
            cn_chars = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")

            for kw in en_words + [cn_chars[i:i+2] for i in range(len(cn_chars)-1)]:
                kw = kw.lower().strip()
                if len(kw) < 2:
                    continue
                keyword_freq[kw]["sessions"].add(sid)
                keyword_freq[kw]["timestamps"].append(ts)
                keyword_freq[kw]["count"] += 1

        # 构建洞察
        insights: list[CrossSessionInsight] = []
        for kw, info in keyword_freq.items():
            if len(info["sessions"]) < min_occurrences:
                continue

            # 判断类型
            method_kws = {"did", "iv", "panel", "rd", "ols", "ml", "regression", "synthetic", "event", "difference", "causal", "双重差分", "工具变量", "面板数据"}
            topic_kws = {"tariff", "innovation", "esg", "carbon", "macro", "asset", "risk", "green", "关税", "创新", "宏观", "碳"}
            finding_kws = {"发现", "结论", "findings", "result", "significant", "positive", "negative"}

            kw_lower = kw.lower()
            if kw_lower in method_kws:
                ins_type = "methodology_pattern"
                title = f"反复使用的方法: {kw}"
                desc = f"在 {len(info['sessions'])} 个会话中被使用"
            elif kw_lower in topic_kws:
                ins_type = "recurring_pattern"
                title = f"反复研究的主题: {kw}"
                desc = f"在 {len(info['sessions'])} 个会话中出现"
            elif any(f in kw_lower for f in finding_kws):
                ins_type = "finding"
                title = f"重复发现: {kw}"
                desc = f"在 {len(info['sessions'])} 个会话中一致的结论"
            else:
                ins_type = "recurring_pattern"
                title = f"反复出现的概念: {kw}"
                desc = f"在 {len(info['sessions'])} 个会话中被讨论"

            ts_list = sorted(info["timestamps"])
            confidence = min(len(info["sessions"]) / 5.0, 1.0)

            insight = CrossSessionInsight(
                insight_type=ins_type,
                title=title,
                description=desc,
                session_ids=list(info["sessions"]),
                first_appeared=ts_list[0],
                last_appeared=ts_list[-1],
                occurrence_count=info["count"],
                confidence=confidence,
                related_topics=[kw],
            )
            insights.append(insight)

        # 按置信度排序
        insights.sort(key=lambda x: (x.confidence, x.occurrence_count), reverse=True)

        # 缓存
        self._insight_cache = insights
        self._insight_cache_time = time.time()

        # 持久化到数据库
        self._persist_insights(insights)

        return [i for i in insights if i.occurrence_count >= min_occurrences]

    def _persist_insights(self, insights: list[CrossSessionInsight]):
        """将洞察持久化到数据库。"""
        cursor = self._conn.cursor()
        with self._write_lock:
            for ins in insights:
                cursor.execute("""
                    INSERT OR REPLACE INTO cross_session_insights
                    (insight_type, title, description, session_ids, first_appeared,
                     last_appeared, occurrence_count, confidence, related_topics, linked_papers, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ins.insight_type,
                    ins.title,
                    ins.description,
                    json.dumps(ins.session_ids, ensure_ascii=False),
                    ins.first_appeared,
                    ins.last_appeared,
                    ins.occurrence_count,
                    ins.confidence,
                    json.dumps(ins.related_topics, ensure_ascii=False),
                    json.dumps(ins.linked_papers, ensure_ascii=False),
                    time.time(),
                ))
            self._conn.commit()

    def get_cached_insights(self) -> list[CrossSessionInsight]:
        """获取已缓存的洞察（无需重新计算）。"""
        return list(self._insight_cache)

    # ── 文献库同步 ───────────────────────────────────────────────────────

    def sync_to_literature_store(
        self,
        topic: str | None = None,
        session_id: str | None = None,
    ) -> int:
        """
        将 ResearchMemory 中的重要知识同步到 LiteratureVectorStore。

        同步内容：
        - 从 contexts 中提取关键发现（evaluation 为正面的）
        - 从 knowledge 表中提取高价值知识条目
        - 从 insights 中提取高置信度洞察

        Args:
            topic: 仅同步特定主题（None = 全部）
            session_id: 仅同步特定会话（None = 全部）

        Returns:
            同步的条目数量
        """
        if not self._lit_store:
            logger.warning("LiteratureVectorStore not available, skipping sync")
            return 0

        cursor = self._conn.cursor()
        synced = 0

        # 1. 同步有正面评价的 context 结果
        sql = """
            SELECT session_id, task, result, timestamp
            FROM contexts
            WHERE is_compressed = 0
        """
        params: list[Any] = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        for row in rows:
            result_str = str(row["result"])
            if len(result_str) < 50:
                continue

            try:
                self._lit_store.add_paper(
                    paper_text=result_str,
                    metadata={
                        "paper_id": f"memory_{row['session_id']}_{int(row['timestamp'])}",
                        "title": row["task"][:200],
                        "journal": "ResearchMemory",
                        "year": datetime.fromtimestamp(row["timestamp"]).year,
                        "methods": [],
                        "topics": [topic] if topic else [],
                        "abstract": result_str[:500],
                        "added_at": datetime.now().isoformat(),
                    },
                )
                synced += 1

                # 记录同步日志
                self._log_sync(row["session_id"], "context", row["task"])
            except Exception as e:
                logger.debug(f"Sync skip (likely duplicate): {e}")

        # 2. 同步高置信度洞察
        cursor.execute("""
            SELECT title, description, insight_type, confidence, session_ids
            FROM cross_session_insights
            WHERE confidence >= 0.5
        """)
        insight_rows = cursor.fetchall()
        for row in insight_rows:
            try:
                self._lit_store.add_paper(
                    paper_text=f"{row['title']}\n\n{row['description']}",
                    metadata={
                        "paper_id": f"insight_{row['title'][:50]}",
                        "title": row["title"],
                        "journal": "CrossSessionInsight",
                        "year": datetime.now().year,
                        "methods": [row["insight_type"]],
                        "topics": [],
                        "abstract": row["description"],
                        "added_at": datetime.now().isoformat(),
                    },
                )
                synced += 1
            except Exception:
                pass

        logger.info(f"Synced {synced} items to LiteratureVectorStore")
        return synced

    def _log_sync(self, session_id: str, source_type: str, key: str):
        """记录同步日志。"""
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "INSERT INTO knowledge_sync_log (source_session_id, source_type, key, synced_to, synced_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, source_type, key[:100], "LiteratureVectorStore", time.time()),
            )
            self._conn.commit()

    # ── 会话历史 ─────────────────────────────────────────────────────────

    def list_sessions(
        self,
        limit: int = 20,
        since: float | None = None,
    ) -> list[SessionSummary]:
        """
        列出历史会话。

        Args:
            limit: 返回条数
            since: 仅返回 since 之后的会话（Unix 时间戳）

        Returns:
            会话摘要列表
        """
        cursor = self._conn.cursor()
        sql = "SELECT * FROM sessions"
        params: list[Any] = []

        if since:
            sql += " WHERE updated_at >= ?"
            params.append(since)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        summaries = []
        for row in rows:
            sid = row["session_id"]

            # 获取任务数
            cursor.execute(
                "SELECT COUNT(*) FROM contexts WHERE session_id = ? AND is_compressed = 0",
                (sid,),
            )
            task_count = cursor.fetchone()[0]

            # 获取工具使用情况
            cursor.execute(
                "SELECT tools_used FROM contexts WHERE session_id = ? AND is_compressed = 0 LIMIT 50",
                (sid,),
            )
            tool_rows = cursor.fetchall()
            all_tools: set[str] = set()
            for tr in tool_rows:
                if tr["tools_used"]:
                    all_tools.update(json.loads(tr["tools_used"]))

            # 获取主题（从 task 字段提取）
            cursor.execute(
                "SELECT task FROM contexts WHERE session_id = ? AND is_compressed = 0 LIMIT 20",
                (sid,),
            )
            topic_rows = cursor.fetchall()
            topics = list({r["task"].split(":")[0].strip() for r in topic_rows if r["task"]})[:5]

            summaries.append(SessionSummary(
                session_id=sid,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                task_count=task_count,
                topics=topics,
                key_findings=[],
                tools_used=list(all_tools),
                research_directions=topics,
            ))

        return summaries

    def get_session_context(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """获取特定会话的上下文记录。"""
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT timestamp, task, result, evaluation, tools_used
            FROM contexts
            WHERE session_id = ? AND is_compressed = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """, (session_id, limit))
        rows = cursor.fetchall()
        return [
            {
                "timestamp": r["timestamp"],
                "task": r["task"],
                "result": json.loads(r["result"]) if r["result"] else {},
                "evaluation": r["evaluation"],
                "tools_used": json.loads(r["tools_used"]) if r["tools_used"] else [],
            }
            for r in rows
        ]

    def get_knowledge_summary(self) -> dict:
        """获取知识库总体摘要。"""
        cursor = self._conn.cursor()

        n_sessions = cursor.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        n_contexts = cursor.execute("SELECT COUNT(*) FROM contexts WHERE is_compressed = 0").fetchone()[0]
        n_knowledge = cursor.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        n_insights = cursor.execute("SELECT COUNT(*) FROM cross_session_insights").fetchone()[0]

        # 最新会话
        cursor.execute("SELECT session_id, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 1")
        last_row = cursor.fetchone()

        # 高频方法
        cursor.execute("""
            SELECT insight_type, COUNT(*) as cnt
            FROM cross_session_insights
            GROUP BY insight_type
            ORDER BY cnt DESC
            LIMIT 5
        """)
        method_rows = cursor.fetchall()

        return {
            "total_sessions": n_sessions,
            "total_contexts": n_contexts,
            "total_knowledge_entries": n_knowledge,
            "total_insights": n_insights,
            "last_session": last_row["session_id"] if last_row else None,
            "last_updated": last_row["updated_at"] if last_row else None,
            "insight_types": [{"type": r["insight_type"], "count": r["cnt"]} for r in method_rows],
            "db_path": self.db_path,
        }

    def __del__(self):
        try:
            if hasattr(self, "_conn") and self._conn:
                self._conn.close()
        except Exception:
            pass
