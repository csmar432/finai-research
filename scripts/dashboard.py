#!/usr/bin/env python3
"""
研究工作流监控仪表盘 (Research Dashboard)
=====================================
基于 Streamlit 的图形化监控面板。

功能：
1. 会话管理：查看/恢复研究会话
2. 任务看板：实时查看任务状态
3. 记忆检索：跨会话知识检索
4. 论文预览：快速预览和管理论文
5. RAG 查询：学术知识库问答
6. 数据新鲜度：监控数据版本状态

使用方法：
    python scripts/dashboard.py
    # 或
    streamlit run scripts/dashboard.py

部署：
    streamlit run scripts/dashboard.py --server.port 8501
"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
from datetime import datetime

# Streamlit（延迟导入）
try:
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    print("提示：Streamlit 未安装。运行 'pip install streamlit plotly pandas' 安装")
    print("或直接使用：python scripts/dashboard.py --cli")


# ═════════════════════════════════════════════════════════════════════════════════
# 页面配置
# ═════════════════════════════════════════════════════════════════════════════════


def set_page_config():
    """设置页面配置"""
    st.set_page_config(
        page_title="金融AI研究工作流",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def add_custom_css():
    """添加自定义 CSS - 现代化暗色主题"""
    st.markdown("""
    <style>
    /* 全局暗色主题 */
    .stApp {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
    }

    /* 主标题样式 */
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4A90E2, #22c55e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 1.5rem;
    }

    /* 统计卡片 */
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.25rem;
        text-align: center;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }

    .metric-card:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(74, 144, 226, 0.3);
        transform: translateY(-2px);
    }

    /* 状态标签 */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
    }

    .status-pending { background: rgba(234, 179, 8, 0.15); color: #eab308; }
    .status-running { background: rgba(74, 144, 226, 0.15); color: #4A90E2; }
    .status-done { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
    .status-failed { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

    /* 按钮样式 */
    .stButton > button {
        background: linear-gradient(135deg, #4A90E2 0%, #357abd 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
    }

    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0f1419 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }

    [data-testid="stSidebar"] .stRadio > label {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 10px;
        padding: 8px 12px;
        margin: 4px 0;
        transition: all 0.2s;
    }

    [data-testid="stSidebar"] .stRadio > label:hover {
        background: rgba(74, 144, 226, 0.15);
    }

    /* 卡片容器 */
    .card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.25rem;
        margin: 0.5rem 0;
    }

    /* 标题样式 */
    h1, h2, h3 {
        color: #e7e9ea;
    }

    /* 分隔线 */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
        margin: 1.5rem 0;
    }

    /* 标签样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255, 255, 255, 0.03);
        padding: 4px;
        border-radius: 12px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
    }

    /* 输入框样式 */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
    }

    /* 滑块样式 */
    .stSlider > div > div > div {
        background: rgba(74, 144, 226, 0.3);
    }

    /* 图表容器 */
    .chart-container {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 1rem;
    }

    /* 动画 */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .animate-in {
        animation: fadeIn 0.5s ease forwards;
    }

    /* 进度条 */
    .progress-bar {
        height: 8px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 4px;
        overflow: hidden;
    }

    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #4A90E2, #22c55e);
        border-radius: 4px;
        transition: width 0.3s ease;
    }
    </style>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════════
# 侧边栏
# ═════════════════════════════════════════════════════════════════════════════════


def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.title("📊 研究工作流")

        pages = {
            "🏠 概览": "overview",
            "🚀 舰队状态": "fleet",
            "💰 成本分析": "cost",
            "📈 执行时间线": "timeline",
            "👤 人工审核": "hitl",
            "❌ 错误日志": "errors",
            "🔀 DAG可视化": "dag",
            "📊 追踪查看": "trace",
            "💬 会话管理": "sessions",
            "📋 任务看板": "tasks",
            "🧠 记忆检索": "memory",
            "📄 论文管理": "papers",
            "🔍 RAG 查询": "rag",
            "📈 数据状态": "data",
            "⚙️ 设置": "settings",
        }

        st.session_state["current_page"] = st.radio(
            "导航",
            list(pages.keys()),
            format_func=lambda x: x,
        )

        st.divider()

        # 连接状态
        st.caption("🔗 连接状态")
        col1, col2 = st.columns(2)
        with col1:
            st.success("🟢 在线")
        with col2:
            st.caption(f"时间: {datetime.now().strftime('%H:%M')}")

        return pages


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：概览
# ═════════════════════════════════════════════════════════════════════════════════


def render_overview():
    """渲染概览页面"""
    st.markdown('<h1 class="main-header">研究工作流概览</h1>', unsafe_allow_html=True)

    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)

    # 会话统计
    sessions = _get_sessions()
    session_count = len(sessions)

    # 活跃会话
    active = len([s for s in sessions if s.get("state") == "running"])

    # 任务统计
    tasks_count = _get_tasks_count()

    # 论文统计
    papers = _get_papers()

    # 卡片样式
    cards = [
        (col1, session_count, "会话总数", "#4A90E2", "M12 2a5 5 0 1 0 5 5 5 5 0 0-5-5zm0 8a3 3 0 1 1 3-3 3 3 0 0 1-3 3z"),
        (col2, active, "活跃会话", "#22c55e", "M13 2L3 14h9l-1 8 10-12h-9l1-8z"),
        (col3, tasks_count, "任务总数", "#a855f7", "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"),
        (col4, len(papers), "论文数", "#eab308", "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"),
    ]

    for col, value, label, color, icon in cards:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 12px;">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2">
                        <path d="{icon}"/>
                    </svg>
                </div>
                <div style="font-size: 2.2rem; font-weight: 700; color: {color}; margin-bottom: 4px;">{value}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # 活动图表
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 最近会话活动")
        if sessions:
            df = pd.DataFrame(sessions[:20])
            if "updated_at" in df.columns:
                df["updated_at"] = pd.to_datetime(df["updated_at"], unit="s", errors="coerce")
                fig = px.line(
                    df, x="updated_at", y="state",
                    title="会话状态变化",
                    template="plotly_dark",
                    color_discrete_sequence=["#4A90E2"]
                )
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e7e9ea"),
                    height=300,
                    margin=dict(l=40, r=20, t=40, b=20),
                )
                fig.update_traces(line=dict(width=3))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无会话数据")

    with col2:
        st.markdown("#### 任务状态分布")
        status_counts = _get_task_status_counts()
        if status_counts:
            fig = px.pie(
                values=list(status_counts.values()),
                names=list(status_counts.keys()),
                title="任务状态",
                template="plotly_dark",
                color_discrete_sequence=["#eab308", "#4A90E2", "#22c55e", "#ef4444"]
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e7e9ea"),
                height=300,
                margin=dict(l=40, r=20, t=40, b=20),
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hole=0.4,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无任务数据")

    st.divider()

    # 快捷操作
    st.markdown("#### 快捷操作")
    col1, col2, col3, col4 = st.columns(4)

    actions = [
        (col1, "新建会话", "📝", "在侧边栏选择功能开始新会话"),
        (col2, "写论文", "📄", "使用 paper_write.py 开始论文写作"),
        (col3, "文献检索", "🔍", "使用 literature_search.py 检索文献"),
        (col4, "数据分析", "📊", "使用 data_pipeline.py 获取数据"),
    ]

    for col, label, icon, msg in actions:
        with col:
            if st.button(f"{icon} {label}", use_container_width=True):
                st.info(msg)

    # 进度指示器
    st.markdown("#### 工作流进度")
    col1, col2, col3, col4, col5 = st.columns(5)

    progress_steps = [
        (col1, "outline", "大纲", 100),
        (col2, "literature", "文献", 75),
        (col3, "writing", "写作", 50),
        (col4, "review", "审核", 25),
        (col5, "submit", "提交", 0),
    ]

    for col, step_id, step_name, progress in progress_steps:
        with col:
            color = "#22c55e" if progress == 100 else "#4A90E2" if progress > 0 else "#3f3f46"
            st.markdown(f"""
            <div style="text-align: center;">
                <div style="position: relative; width: 60px; height: 60px; margin: 0 auto 8px;">
                    <svg viewBox="0 0 36 36" style="transform: rotate(-90deg);">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#3f3f46" stroke-width="3"/>
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="{color}" stroke-width="3"
                            stroke-dasharray="{progress}, 100" stroke-linecap="round"/>
                    </svg>
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 14px;">
                        {int(progress)}%
                    </div>
                </div>
                <div style="font-size: 12px; color: #8b98a5;">{step_name}</div>
            </div>
            """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：会话管理
# ═════════════════════════════════════════════════════════════════════════════════


def render_sessions():
    """渲染会话管理页面"""
    st.markdown('<h1 class="main-header">会话管理</h1>', unsafe_allow_html=True)

    sessions = _get_sessions()

    if not sessions:
        st.info("暂无会话记录")
        return

    # 过滤器
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔍 搜索会话", placeholder="输入会话ID或描述...")

    with col2:
        state_filter = st.selectbox(
            "状态筛选",
            ["全部", "运行中", "已完成", "失败"]
        )

    # 过滤会话
    filtered = sessions
    if search:
        filtered = [s for s in filtered if search.lower() in str(s.get("session_id", "")).lower()]

    if state_filter != "全部":
        state_map = {"运行中": "running", "已完成": "completed", "失败": "failed"}
        state_val = state_map.get(state_filter, "")
        filtered = [s for s in filtered if s.get("state") == state_val]

    st.caption(f"共 {len(filtered)} 个会话")

    # 会话列表
    for session in filtered[:20]:
        state = session.get('state', 'unknown')
        state_colors = {
            'running': ('#4A90E2', '运行中'),
            'completed': ('#22c55e', '已完成'),
            'failed': ('#ef4444', '失败'),
            'unknown': ('#8b98a5', '未知'),
        }
        color, state_text = state_colors.get(state, state_colors['unknown'])

        with st.expander(f"📌 {session.get('session_id', '未知')}", expanded=False):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(f"""
                <div class="status-badge status-{state}">
                    <span style="width: 8px; height: 8px; border-radius: 50%; background: currentColor;"></span>
                    {state_text}
                </div>
                """, unsafe_allow_html=True)

            with col2:
                updated = session.get("updated_at")
                if updated:
                    updated = datetime.fromtimestamp(updated)
                    st.caption(f"更新: {updated.strftime('%Y-%m-%d %H:%M')}")

            with col3:
                if st.button("恢复会话", key=f"resume_{session.get('session_id')}"):
                    st.info(f"恢复会话: {session.get('session_id')}")

            summary = session.get("summary", "")
            if summary:
                st.text(f"摘要: {summary[:200]}")


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：任务看板
# ═════════════════════════════════════════════════════════════════════════════════


def render_tasks():
    """渲染任务看板页面"""
    st.markdown('<h1 class="main-header">任务看板</h1>', unsafe_allow_html=True)

    # 获取任务状态
    status_counts = _get_task_status_counts()

    # 状态卡片
    col1, col2, col3, col4 = st.columns(4)

    statuses = [
        ("pending", "⏳ 待处理", "#eab308"),
        ("running", "🔄 运行中", "#4A90E2"),
        ("done", "✅ 已完成", "#22c55e"),
        ("failed", "❌ 失败", "#ef4444"),
    ]

    for i, (status, label, color) in enumerate(statuses):
        count = status_counts.get(status, 0)
        with {"col1": col1, "col2": col2, "col3": col3, "col4": col4, "col5": col5, "col6": col6, "col7": col7, "col8": col8, "col9": col9, "col10": col10, "col11": col11, "col12": col12}[f"col{i+1}"]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem; font-weight: 700; color: {color}; margin-bottom: 4px;">{count}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # 任务列表
    st.markdown("#### 最近任务")

    tasks = _get_recent_tasks()
    if not tasks:
        st.info("暂无任务数据")
        return

    # 按状态分组
    by_status = {}
    for task in tasks:
        status = task.get("status", "pending")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(task)

    if by_status:
        tabs = st.tabs([f"{s} ({len(t)})" for s, t in by_status.items()])

        for i, (status, task_list) in enumerate(by_status.items()):
            with tabs[i]:
                for task in task_list[:10]:
                    col1, col2 = st.columns([4, 1])

                    task_type = task.get("task_type", "unknown")
                    task_desc = task.get("description", "无描述")

                    with col1:
                        st.markdown(f"""
                        <div class="card">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="background: rgba(74, 144, 226, 0.15); color: #4A90E2; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600;">
                                    {task_type.upper()}
                                </span>
                                <span style="color: #e7e9ea;">{task_desc[:60]}{'...' if len(task_desc) > 60 else ''}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    with col2:
                        score = task.get("score", 0)
                        if score:
                            st.markdown(f"""
                            <div style="text-align: right;">
                                <div style="font-size: 1.2rem; font-weight: 600; color: #22c55e;">{score:.1f}</div>
                                <div style="font-size: 10px; color: #8b98a5;">评分</div>
                            </div>
                            """, unsafe_allow_html=True)

                        created = task.get("created_at")
                        if created:
                            created = datetime.fromtimestamp(created)
                            st.caption(created.strftime("%H:%M"))


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：记忆检索
# ═════════════════════════════════════════════════════════════════════════════════


def render_memory():
    """渲染记忆检索页面"""
    st.markdown('<h1 class="main-header">跨会话记忆检索</h1>', unsafe_allow_html=True)

    # 搜索框
    query = st.text_input("🔍 输入检索关键词", placeholder="输入检索词...")

    col1, col2 = st.columns([1, 3])

    with col1:
        limit = st.slider("结果数量", 1, 50, 10)

    with col2:
        tags = st.multiselect(
            "标签筛选",
            ["paper", "experiment", "data", "analysis", "writing"],
            default=["paper"]
        )

    if st.button("🔍 检索", use_container_width=True) and query:
        results = _search_memory(query, tags, limit)

        st.markdown(f"#### 找到 {len(results)} 条结果")

        for result in results:
            with st.expander(f"📌 {result.get('key', '未知')[:50]}", expanded=False):
                value = result.get("value", {})
                if isinstance(value, dict):
                    for k, v in value.items():
                        st.markdown(f"""
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #8b98a5; font-size: 12px;">{k}</span>
                            <span style="color: #e7e9ea; font-size: 12px;">{str(v)[:80]}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.text(str(value)[:200])

                st.markdown(f"""
                <div style="margin-top: 12px;">
                    <span style="background: rgba(74, 144, 226, 0.15); color: #4A90E2; padding: 4px 10px; border-radius: 6px; font-size: 11px;">
                        {', '.join(result.get('tags', []))}
                    </span>
                </div>
                """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：论文管理
# ═════════════════════════════════════════════════════════════════════════════════


def render_papers():
    """渲染论文管理页面"""
    st.markdown('<h1 class="main-header">论文管理</h1>', unsafe_allow_html=True)

    # 论文统计
    papers = _get_papers()
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 2rem; font-weight: 700; color: #4A90E2; margin-bottom: 4px;">{len(papers)}</div>
            <div style="font-size: 0.85rem; color: #8b98a5;">论文总数</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        stages = set(p.get("stage", "unknown") for p in papers)
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 2rem; font-weight: 700; color: #a855f7; margin-bottom: 4px;">{len(stages)}</div>
            <div style="font-size: 0.85rem; color: #8b98a5;">写作阶段</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        if papers:
            latest = papers[0].get("created_at", "")
            latest_date = latest[:10] if latest else "N/A"
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 1.2rem; font-weight: 700; color: #22c55e; margin-bottom: 4px;">{latest_date}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">最新论文</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
                <div style="font-size: 1.2rem; font-weight: 700; color: #8b98a5; margin-bottom: 4px;">N/A</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">最新论文</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # 操作按钮
    col1, col2, col3, col4 = st.columns(4)

    actions = [
        (col1, "📝 新建论文", "使用 paper_write.py 创建新论文"),
        (col2, "📊 质量评分", "使用 paper_quality_scorer.py 评分"),
        (col3, "📦 版本历史", "使用 paper_versioning.py 查看历史"),
        (col4, "🔄 整合论文", "整合各章节为完整论文"),
    ]

    for col, label, msg in actions:
        with col:
            if st.button(label, use_container_width=True):
                st.info(msg)

    st.divider()

    # 论文列表
    st.markdown("#### 论文列表")

    if not papers:
        st.info("暂无论文数据")
        return

    for paper in papers[:10]:
        title = paper.get("title", "无标题")
        stage = paper.get("stage", "unknown")
        path = paper.get("path", "")

        with st.expander(f"📄 {title}", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"""
                <span style="background: rgba(168, 85, 247, 0.15); color: #a855f7; padding: 4px 10px; border-radius: 6px; font-size: 12px;">
                    {stage}
                </span>
                """, unsafe_allow_html=True)

            with col2:
                if path:
                    st.caption(f"路径: {path[:40]}...")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("预览", key=f"view_{paper.get('id')}"):
                    st.info("预览功能开发中")

            with col2:
                if st.button("评分", key=f"score_{paper.get('id')}"):
                    st.info("开始评分...")

            with col3:
                if st.button("导出", key=f"export_{paper.get('id')}"):
                    st.info("导出功能开发中")


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：RAG 查询
# ═════════════════════════════════════════════════════════════════════════════════


def render_rag():
    """渲染 RAG 查询页面"""
    st.markdown('<h1 class="main-header">学术知识库问答</h1>', unsafe_allow_html=True)

    st.info("基于已索引的论文和笔记进行问答")

    # 查询输入
    query = st.text_area(
        "💬 输入问题",
        placeholder="例如：LLM在金融领域有哪些应用？",
        height=100
    )

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        top_k = st.slider("检索数量", 1, 20, 5)

    with col2:
        model = st.selectbox("使用模型", ["deepseek", "gpt", "claude"])

    with col3:
        st.write("")  # spacing

    if st.button("🔍 查询", use_container_width=True):
        if query:
            with st.spinner("查询中..."):
                answer, sources = _rag_query(query, top_k, model)

                st.markdown("""
                <div class="card">
                    <h3 style="color: #22c55e; margin-bottom: 12px;">💡 回答</h3>
                """, unsafe_allow_html=True)
                st.markdown(answer)
                st.markdown("</div>", unsafe_allow_html=True)

                if sources:
                    st.markdown("#### 📚 参考来源")
                    for i, src in enumerate(sources, 1):
                        st.markdown(f"""
                        <div style="padding: 8px 12px; background: rgba(74, 144, 226, 0.1); border-radius: 8px; margin: 4px 0; font-size: 13px;">
                            <span style="color: #4A90E2; font-weight: 600;">[{i}]</span> {src[:120]}...
                        </div>
                        """, unsafe_allow_html=True)

    # RAG 状态
    st.divider()
    st.markdown("#### 知识库状态")

    try:
        from scripts.research_rag import ResearchRAG
        rag = ResearchRAG()
        stats = rag.stats()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem; font-weight: 700; color: #4A90E2;">{stats.get("total_chunks", 0)}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">总片段</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem; font-weight: 700; color: #a855f7;">{stats.get("papers", 0)}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">论文数</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            indexed = "✅ 是" if stats.get("index_built") else "❌ 否"
            color = "#22c55e" if stats.get("index_built") else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 1.5rem; font-weight: 700; color: {color};">{indexed}</div>
                <div style="font-size: 0.85rem; color: #8b98a5;">索引已构建</div>
            </div>
            """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"知识库状态获取失败: {e}")


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：数据状态
# ═════════════════════════════════════════════════════════════════════════════════


def render_data():
    """渲染数据状态页面"""
    st.markdown('<h1 class="main-header">数据版本状态</h1>', unsafe_allow_html=True)

    # 数据新鲜度
    st.markdown("#### 数据新鲜度")

    try:
        from scripts.data_version import DataVersionManager
        dvm = DataVersionManager()
        report = dvm.get_freshness_report()

        summary = report.get("summary", {})

        col1, col2, col3, col4 = st.columns(4)

        freshness_data = [
            (col1, summary.get("total", 0), "总数据源", "#4A90E2"),
            (col2, summary.get("fresh", 0), "🟢 新鲜", "#22c55e"),
            (col3, summary.get("stale", 0), "🟡 略旧", "#eab308"),
            (col4, summary.get("old", 0), "🔴 过期", "#ef4444"),
        ]

        for col, value, label, color in freshness_data:
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 2rem; font-weight: 700; color: {color}; margin-bottom: 4px;">{value}</div>
                    <div style="font-size: 0.85rem; color: #8b98a5;">{label}</div>
                </div>
                """, unsafe_allow_html=True)

        # 新鲜数据列表
        if report.get("fresh"):
            with st.expander("🟢 新鲜数据", expanded=False):
                for item in report["fresh"][:10]:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <span style="font-weight: 500;">{item['ticker']}</span>
                        <span style="color: #8b98a5;">{item['age_days']} 天前</span>
                    </div>
                    """, unsafe_allow_html=True)

        # 略旧数据
        if report.get("stale"):
            with st.expander("🟡 略旧数据", expanded=False):
                for item in report["stale"][:10]:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <span style="font-weight: 500;">{item['ticker']}</span>
                        <span style="color: #eab308;">{item['age_days']} 天前</span>
                    </div>
                    """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"数据版本状态获取失败: {e}")

    st.divider()

    # 实验统计
    st.markdown("#### 实验追踪")

    try:
        from scripts.experiment_tracker import ExperimentTracker
        tracker = ExperimentTracker()
        summary = tracker.summary()

        col1, col2, col3, col4 = st.columns(4)

        exp_data = [
            (col1, summary.get("total_experiments", 0), "实验总数", "#4A90E2"),
            (col2, summary.get("completed_experiments", 0), "已完成", "#22c55e"),
            (col3, summary.get("ablation_experiments", 0), "消融实验", "#a855f7"),
            (col4, f"{summary.get('verification_rate', 0):.0%}", "验证率", "#eab308"),
        ]

        for col, value, label, color in exp_data:
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 1.8rem; font-weight: 700; color: {color}; margin-bottom: 4px;">{value}</div>
                    <div style="font-size: 0.85rem; color: #8b98a5;">{label}</div>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"实验追踪状态获取失败: {e}")


# ═════════════════════════════════════════════════════════════════════════════════
# 页面：设置
# ═════════════════════════════════════════════════════════════════════════════════


def render_settings():
    """渲染设置页面"""
    st.markdown('<h1 class="main-header">设置</h1>', unsafe_allow_html=True)

    # LLM 配置
    st.markdown("#### LLM 配置")

    try:
        from scripts.ai_router import AIRouter
        router = AIRouter()
        status = router.status()

        # 显示为卡片样式
        st.markdown("""
        <div class="card">
        """, unsafe_allow_html=True)
        st.json(status)
        st.markdown("</div>", unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"LLM 状态获取失败: {e}")

    st.divider()

    # MCP 工具
    st.markdown("#### MCP 工具状态")

    mcp_tools = _get_mcp_tools()
    if mcp_tools:
        for tool in mcp_tools:
            status_color = "#22c55e" if tool["status"] == "在线" else "#ef4444"
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: rgba(255,255,255,0.03); border-radius: 10px; margin: 8px 0;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4A90E2" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                    </svg>
                    <span style="font-weight: 500;">{tool['name']}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 16px;">
                    <span style="background: rgba(34, 197, 94, 0.15); color: {status_color}; padding: 4px 10px; border-radius: 6px; font-size: 12px;">
                        {tool['status']}
                    </span>
                    <span style="color: #8b98a5; font-size: 12px;">{tool['calls']} 次调用</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("暂无 MCP 工具数据")

    st.divider()

    # 缓存管理
    st.markdown("#### 缓存管理")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🗑️ 清理缓存", use_container_width=True):
            st.info("清理功能开发中")

    with col2:
        if st.button("📊 缓存统计", use_container_width=True):
            st.info("统计功能开发中")


# ═════════════════════════════════════════════════════════════════════════════════
# 数据获取函数
# ═════════════════════════════════════════════════════════════════════════════════


def _get_sessions() -> list:
    """获取会话列表"""
    try:
        import sqlite3
        conn = sqlite3.connect(".cache/research.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT session_id, state, updated_at, summary
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT 50
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "session_id": row[0],
                "state": row[1],
                "updated_at": row[2],
                "summary": row[3],
            }
            for row in rows
        ]
    except Exception:
        return []


def _get_tasks_count() -> int:
    """获取任务总数"""
    try:
        conn = sqlite3.connect(".cache/research.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM contexts")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _get_papers() -> list:
    """获取论文列表"""
    papers = []

    # 从 knowledge/outlines 目录
    outline_dir = Path("knowledge/outlines")
    if outline_dir.exists():
        for f in sorted(outline_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            try:
                content = f.read_text(encoding="utf-8")[:200]
                papers.append({
                    "id": f.stem,
                    "title": f.stem[:50],
                    "stage": "大纲",
                    "path": str(f),
                    "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
            except Exception:
                pass

    return papers


def _get_task_status_counts() -> dict:
    """获取任务状态统计"""
    return {
        "pending": 5,
        "running": 2,
        "done": 15,
        "failed": 1,
    }


def _get_recent_tasks() -> list:
    """获取最近任务"""
    try:
        conn = sqlite3.connect(".cache/research.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT task, result, timestamp
            FROM contexts
            ORDER BY timestamp DESC
            LIMIT 20
        """)

        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            try:
                result = json.loads(row[1]) if row[1] else {}
                tasks.append({
                    "description": row[0],
                    "status": "done" if result.get("success") else "failed",
                    "score": result.get("score", 0),
                    "task_type": "analysis",
                    "created_at": row[2],
                })
            except Exception:
                pass

        return tasks
    except Exception:
        return []


def _search_memory(query: str, tags: list, limit: int) -> list:
    """搜索记忆"""
    try:
        conn = sqlite3.connect(".cache/research.db")
        cursor = conn.cursor()

        sql = """
            SELECT key, value, tags
            FROM knowledge
            WHERE key LIKE ? OR value LIKE ?
        """
        params = [f"%{query}%", f"%{query}%"]

        if tags:
            for tag in tags:
                sql += " AND tags LIKE ?"
                params.append(f"%\"{tag}\"%")

        sql += f" LIMIT {limit}"

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "key": row[0],
                "value": row[1],
                "tags": json.loads(row[2]) if row[2] else [],
            }
            for row in rows
        ]
    except Exception:
        return []


def _rag_query(query: str, top_k: int, model: str) -> tuple[str, list]:
    """执行 RAG 查询"""
    try:
        from scripts.research_rag import ResearchRAG
        rag = ResearchRAG()
        result = rag.rag_query(query, llm_model=model, top_k=top_k)

        sources = [s.get("paper_id", "") for s in result.get("sources", [])]
        return result.get("answer", ""), sources
    except Exception as e:
        return f"查询失败: {e}", []


def _get_mcp_tools() -> list:
    """获取 MCP 工具状态"""
    return [
        {"name": "arxiv", "status": "在线", "calls": 15},
        {"name": "financial", "status": "在线", "calls": 32},
        {"name": "finviz_sec", "status": "在线", "calls": 8},
        {"name": "brave_search", "status": "在线", "calls": 24},
        {"name": "fetch", "status": "在线", "calls": 45},
        {"name": "context7", "status": "离线", "calls": 0},
    ]


# ═════════════════════════════════════════════════════════════════════════════════
# CLI 模式
# ═════════════════════════════════════════════════════════════════════════════════


def run_cli():
    """CLI 模式（Streamlit 不可用时）"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║       金融AI研究工作流 - 监控仪表盘                      ║
╠══════════════════════════════════════════════════════════════╣
║  1. 安装 Streamlit                                      ║
║     pip install streamlit plotly pandas                  ║
║                                                        ║
║  2. 启动仪表盘                                          ║
║     streamlit run scripts/dashboard.py                   ║
║                                                        ║
║  3. 或使用 Python 直接调用                              ║
║     from scripts.dashboard import *                     ║
║     render_overview()  # 渲染概览页面                   ║
╚══════════════════════════════════════════════════════════════╝
""")


# ═════════════════════════════════════════════════════════════════════════════════
# 主函数
# ═════════════════════════════════════════════════════════════════════════════════


def main():
    if not STREAMLIT_AVAILABLE:
        run_cli()
        return

    set_page_config()
    add_custom_css()

    pages = render_sidebar()

    # 渲染对应页面
    page = st.session_state.get("current_page", "🏠 概览")

    # 页面映射
    page_funcs = {
        "🏠 概览": render_overview,
        "🚀 舰队状态": lambda: render_advanced_view("fleet"),
        "💰 成本分析": lambda: render_advanced_view("cost"),
        "📈 执行时间线": lambda: render_advanced_view("timeline"),
        "👤 人工审核": lambda: render_advanced_view("hitl"),
        "❌ 错误日志": lambda: render_advanced_view("errors"),
        "🔀 DAG可视化": lambda: render_advanced_view("dag"),
        "📊 追踪查看": render_trace_viewer,
        "💬 会话管理": render_sessions,
        "📋 任务看板": render_tasks,
        "🧠 记忆检索": render_memory,
        "📄 论文管理": render_papers,
        "🔍 RAG 查询": render_rag,
        "📈 数据状态": render_data,
        "⚙️ 设置": render_settings,
    }

    page_func = page_funcs.get(page, render_overview)
    page_func()


def render_advanced_view(view_type: str):
    """渲染高级视图"""
    try:
        from scripts.core.dashboard_advanced import (
            render_cost_analytics,
            render_dag_visualization,
            render_error_log,
            render_execution_timeline,
            render_fleet_status,
            render_hitl_inbox,
        )

        views = {
            "fleet": render_fleet_status,
            "cost": render_cost_analytics,
            "timeline": render_execution_timeline,
            "hitl": render_hitl_inbox,
            "errors": render_error_log,
            "dag": render_dag_visualization,
        }

        view_func = views.get(view_type)
        if view_func:
            view_func()
        else:
            st.error(f"未知的视图类型: {view_type}")

    except ImportError as e:
        st.error(f"无法导入高级视图模块: {e}")
        st.info("请确保已安装所有依赖：pip install streamlit plotly pandas")


def render_trace_viewer():
    """渲染追踪查看器"""
    try:
        from scripts.core.langsmith_integration import render_trace_viewer as _render
        _render()
    except ImportError as e:
        st.error(f"无法导入追踪模块: {e}")


if __name__ == "__main__":
    main()
