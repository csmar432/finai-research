#!/usr/bin/env python3
"""
LangSmith Trace 集成
====================
提供 LangSmith 原生集成以及本地追踪替代方案

功能：
1. LangSmith 原生集成（需要 API Key）
2. 本地追踪替代方案（SQLite 存储）
3. Trace 可视化

使用方法：
  from scripts.core.langsmith_integration import LangSmithTracer, get_tracer

  tracer = get_tracer()
  with tracer.trace("我的操作"):
      # 执行操作
      pass
"""

from __future__ import annotations

__all__ = [
    "LocalSpan",
    "LocalTracer",
    "LangSmithTracer",
    "get_tracer",
    "traceable",
    "render_trace_viewer",
    "LANGSMITH_AVAILABLE",
]

import json
import os
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# 尝试导入 LangSmith
LANGSMITH_AVAILABLE = False
try:
    from langsmith import Client, trace, traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# 本地追踪器（LangSmith 不可用时的替代）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LocalSpan:
    """本地追踪跨度"""
    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: float | None = None
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    error: str | None = None


class LocalTracer:
    """
    本地追踪器

    提供与 LangSmith 类似的追踪功能，但数据存储在本地 SQLite 数据库中。
    当 LangSmith 不可用或未配置时使用此追踪器。
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = ".cache/traces.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._current_trace_id: str | None = None
        self._spans: dict[str, LocalSpan] = {}

    def _init_db(self):
        """初始化数据库"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                name TEXT,
                start_time REAL,
                end_time REAL,
                metadata TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT,
                name TEXT,
                start_time REAL,
                end_time REAL,
                metadata TEXT,
                tags TEXT,
                events TEXT,
                error TEXT,
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id)")

        conn.commit()
        conn.close()

    def start_trace(self, name: str, metadata: dict = None) -> str:
        """开始追踪"""
        trace_id = str(uuid.uuid4())
        self._current_trace_id = trace_id

        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO traces (trace_id, name, start_time, metadata)
            VALUES (?, ?, ?, ?)
        """, (trace_id, name, time.time(), json.dumps(metadata or {})))

        conn.commit()
        conn.close()

        return trace_id

    def end_trace(self, trace_id: str = None, metadata: dict = None):
        """结束追踪"""
        trace_id = trace_id or self._current_trace_id
        if not trace_id:
            return

        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE traces
            SET end_time = ?
            WHERE trace_id = ?
        """, (time.time(), trace_id))

        conn.commit()
        conn.close()

        self._current_trace_id = None

    @contextmanager
    def trace(self, name: str, tags: list[str] = None, metadata: dict = None):
        """
        追踪上下文管理器

        使用方式：
            with tracer.trace("我的操作"):
                # 执行操作
                pass
        """
        span = LocalSpan(
            span_id=str(uuid.uuid4()),
            trace_id=self._current_trace_id or str(uuid.uuid4()),
            name=name,
            start_time=time.time(),
            tags=tags or [],
            metadata=metadata or {}
        )

        self._spans[span.span_id] = span

        try:
            yield span
        except Exception as e:
            span.error = str(e)
            raise
        finally:
            span.end_time = time.time()
            self._save_span(span)

    def _save_span(self, span: LocalSpan):
        """保存跨度到数据库"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO spans
            (span_id, trace_id, name, start_time, end_time, metadata, tags, events, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            span.span_id,
            span.trace_id,
            span.name,
            span.start_time,
            span.end_time,
            json.dumps(span.metadata),
            json.dumps(span.tags),
            json.dumps(span.events),
            span.error
        ))

        conn.commit()
        conn.close()

    def add_event(self, span_id: str, name: str, metadata: dict = None):
        """添加事件"""
        span = self._spans.get(span_id)
        if span:
            span.events.append({
                "name": name,
                "timestamp": time.time(),
                "metadata": metadata or {}
            })

    def get_traces(self, limit: int = 50) -> list[dict]:
        """获取追踪列表"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT trace_id, name, start_time, end_time, metadata
            FROM traces
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,))

        traces = []
        for row in cursor.fetchall():
            traces.append({
                "trace_id": row[0],
                "name": row[1],
                "start_time": row[2],
                "end_time": row[3],
                "duration": row[3] - row[2] if row[3] else None,
                "metadata": json.loads(row[4]) if row[4] else {}
            })

        conn.close()
        return traces

    def get_trace_spans(self, trace_id: str) -> list[dict]:
        """获取追踪的跨度"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT span_id, name, start_time, end_time, metadata, tags, events, error
            FROM spans
            WHERE trace_id = ?
            ORDER BY start_time
        """, (trace_id,))

        spans = []
        for row in cursor.fetchall():
            spans.append({
                "span_id": row[0],
                "name": row[1],
                "start_time": row[2],
                "end_time": row[3],
                "duration": row[3] - row[2] if row[3] else None,
                "metadata": json.loads(row[4]) if row[4] else {},
                "tags": json.loads(row[5]) if row[5] else [],
                "events": json.loads(row[6]) if row[6] else [],
                "error": row[7]
            })

        conn.close()
        return spans


# ═══════════════════════════════════════════════════════════════════════════
# LangSmith 集成
# ═══════════════════════════════════════════════════════════════════════════

class LangSmithTracer:
    """
    LangSmith 追踪器

    当 LANGSMITH_API_KEY 环境变量设置时使用原生 LangSmith，
    否则使用本地追踪器。
    """

    def __init__(self):
        self.use_langsmith = LANGSMITH_AVAILABLE and bool(os.environ.get("LANGSMITH_API_KEY"))

        if self.use_langsmith:
            self.client = Client()
            print("✅ 使用 LangSmith 追踪")
        else:
            self.local_tracer = LocalTracer()
            print("📦 使用本地追踪器")

    def start_trace(self, name: str, metadata: dict = None) -> str:
        """开始追踪"""
        if self.use_langsmith:
            run = self.client.create_run(
                name=name,
                run_type="chain",
                metadata=metadata or {}
            )
            return str(run.id)
        else:
            return self.local_tracer.start_trace(name, metadata)

    def end_trace(self, trace_id: str = None, metadata: dict = None):
        """结束追踪"""
        if self.use_langsmith:
            self.client.update_run(trace_id, end_time=datetime.now(), metadata=metadata or {})
        else:
            self.local_tracer.end_trace(trace_id, metadata)

    @contextmanager
    def trace(self, name: str, tags: list[str] = None, metadata: dict = None):
        """追踪上下文管理器"""
        if self.use_langsmith:
            # 使用 LangSmith 的 traceable 装饰器
            with trace(name, tags=tags, metadata=metadata):
                yield None
        else:
            # 使用本地追踪器
            with self.local_tracer.trace(name, tags, metadata) as span:
                yield span

    def get_traces(self, limit: int = 50) -> list[dict]:
        """获取追踪列表"""
        if self.use_langsmith:
            runs = self.client.list_runs(last_n=limit)
            return [
                {
                    "trace_id": str(run.id),
                    "name": run.name,
                    "start_time": run.start_time.timestamp() if run.start_time else None,
                    "end_time": run.end_time.timestamp() if run.end_time else None,
                    "duration": (run.end_time - run.start_time).total_seconds() if run.end_time and run.start_time else None,
                    "metadata": run.metadata or {}
                }
                for run in runs
            ]
        else:
            return self.local_tracer.get_traces(limit)

    def get_trace_spans(self, trace_id: str) -> list[dict]:
        """获取追踪的跨度"""
        if self.use_langsmith:
            run = self.client.read_run(trace_id)
            return [
                {
                    "span_id": str(run.id),
                    "name": run.name,
                    "start_time": run.start_time.timestamp() if run.start_time else None,
                    "end_time": run.end_time.timestamp() if run.end_time else None,
                    "duration": (run.end_time - run.start_time).total_seconds() if run.end_time and run.start_time else None,
                    "metadata": run.metadata or {},
                    "error": str(run.error) if run.error else None
                }
            ]
        else:
            return self.local_tracer.get_trace_spans(trace_id)


# ═══════════════════════════════════════════════════════════════════════════
# 全局追踪器实例
# ═══════════════════════════════════════════════════════════════════════════

_tracer_instance: LangSmithTracer | None = None


def get_tracer() -> LangSmithTracer:
    """获取全局追踪器实例"""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = LangSmithTracer()
    return _tracer_instance


# ═══════════════════════════════════════════════════════════════════════════
# 便捷装饰器
# ═══════════════════════════════════════════════════════════════════════════

def traceable(name: str = None, tags: list[str] = None):
    """
    追踪装饰器

    使用方式：
        @traceable("我的函数")
        def my_function(x):
            return x * 2
    """
    def decorator(func: Callable) -> Callable:
        _name = name or func.__name__

        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.trace(_name, tags=tags):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# ═══════════════════════════════════════════════════════════════════════════
# Streamlit 组件
# ═══════════════════════════════════════════════════════════════════════════

def render_trace_viewer():
    """渲染追踪查看器组件"""

    import pandas as pd
    import streamlit as st

    st.markdown("## 📊 追踪查看器")

    tracer = get_tracer()
    traces = tracer.get_traces(limit=50)

    if not traces:
        st.info("暂无追踪数据")
        return

    # 追踪列表
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown("### 追踪历史")

    with col2:
        if st.button("🔄 刷新"):
            st.rerun()

    # 转换为DataFrame
    df = pd.DataFrame(traces)
    df["start_time"] = pd.to_datetime(df["start_time"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")
    df["duration"] = df["duration"].apply(lambda x: f"{x:.2f}s" if x else "-")

    st.dataframe(
        df[["trace_id", "name", "start_time", "duration"]],
        use_container_width=True,
        hide_index=True
    )

    # 追踪详情
    st.markdown("### 追踪详情")

    selected_trace = st.selectbox(
        "选择追踪",
        options=[t["trace_id"] for t in traces],
        format_func=lambda x: next((t["name"] for t in traces if t["trace_id"] == x), x)
    )

    if selected_trace:
        spans = tracer.get_trace_spans(selected_trace)

        if spans:
            df_spans = pd.DataFrame(spans)
            df_spans["start_time"] = pd.to_datetime(df_spans["start_time"], unit="s").dt.strftime("%H:%M:%S.%f")[:-3]
            df_spans["duration"] = df_spans["duration"].apply(lambda x: f"{x*1000:.0f}ms" if x else "-")

            st.dataframe(
                df_spans[["name", "start_time", "duration", "error"]],
                use_container_width=True,
                hide_index=True
            )

            # 显示错误信息
            errors = [s for s in spans if s.get("error")]
            if errors:
                st.markdown("#### ❌ 错误信息")
                for span in errors:
                    st.error(f"**{span['name']}**: {span['error']}")


# ═══════════════════════════════════════════════════════════════════════════
# 配置说明
# ═══════════════════════════════════════════════════════════════════════════

LANGSMITH_CONFIG = """
# LangSmith 配置

LangSmith 是 LangChain 官方提供的追踪和监控平台，可提供更强大的追踪功能。

## 安装

```bash
pip install langsmith
```

## 配置 API Key

在 `.env.local` 中添加：

```bash
LANGSMITH_API_KEY=your_api_key_here
LANGSMITH_TRACING=true
```

## 获取 API Key

1. 访问 https://smith.langchain.com/
2. 注册/登录账号
3. 在 Settings 中获取 API Key

## 功能

- 实时追踪可视化
- Token 使用统计
- 成本分析
- 错误追踪
- 团队协作

## 本地替代

当 LANGSMITH_API_KEY 未设置时，系统将使用本地追踪器，
数据存储在 `.cache/traces.db` 中。
"""
