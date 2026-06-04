#!/usr/bin/env python3
"""
Dashboard 高级组件
=================
提供成本分析、执行时间线、错误分类等高级视图

组件：
1. FleetStatusView - 舰队状态概览
2. CostAnalyticsView - 成本分析
3. ExecutionTimelineView - 执行时间线
4. HITLInboxView - 人工审核收件箱
5. ErrorLogView - 错误日志
6. DAGVisualizationView - DAG可视化
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from scripts.core.agent_state import (
    ErrorClassifier,
    ErrorType,
    agent_state_manager,
    cost_tracker,
    hitl_manager,
)
from scripts.core.visualizer import VizEdge, VizNode, WorkflowVisualizer

# ═══════════════════════════════════════════════════════════════════════════
# 颜色主题
# ═══════════════════════════════════════════════════════════════════════════

COLORS = {
    "running": "#22c55e",   # 绿色 - 运行中
    "succeeded": "#3b82f6", # 蓝色 - 成功
    "failed": "#ef4444",     # 红色 - 失败
    "idle": "#6b7280",      # 灰色 - 空闲
    "waiting": "#f59e0b",   # 黄色 - 等待
    "retrying": "#8b5cf6",  # 紫色 - 重试
}

STATUS_LABELS = {
    "running": "运行中",
    "succeeded": "成功",
    "failed": "失败",
    "idle": "空闲",
    "waiting": "等待审核",
    "retrying": "重试中",
}


# ═══════════════════════════════════════════════════════════════════════════
# View 1: Fleet Status（舰队状态）
# ═══════════════════════════════════════════════════════════════════════════

def render_fleet_status():
    """渲染舰队状态视图"""
    st.markdown("## 🚀 舰队状态")

    # 获取状态
    status = agent_state_manager.get_fleet_status()
    agents = agent_state_manager.get_all_agents()

    # 统计卡片
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric("Agent总数", status["total_agents"])
    with col2:
        st.metric("运行中", status["running_count"],
                  delta_color="normal" if status["running_count"] > 0 else "off")
    with col3:
        st.metric("空闲", status["idle_count"])
    with col4:
        st.metric("失败", status["failed_count"],
                  delta_color="inverse" if status["failed_count"] > 0 else "off")
    with col5:
        st.metric("等待审核", status["waiting_count"],
                  delta_color="normal" if status["waiting_count"] > 0 else "off")
    with col6:
        st.metric("重试中", status.get("retrying_count", 0))

    st.divider()

    # Agent列表
    st.markdown("### 📋 Agent 详情")

    if agents:
        # 构建DataFrame
        data = []
        for agent in agents:
            duration = None
            if agent.start_time:
                end = agent.end_time or datetime.now().timestamp()
                duration = end - agent.start_time

            data.append({
                "Agent ID": agent.agent_id,
                "名称": agent.name,
                "状态": STATUS_LABELS.get(agent.status.value, agent.status.value),
                "当前任务": agent.current_task or "-",
                "错误次数": agent.error_count,
                "持续时间": f"{duration:.1f}s" if duration else "-",
                "最后错误": agent.last_error[:50] + "..." if agent.last_error and len(agent.last_error) > 50 else agent.last_error or "-"
            })

        df = pd.DataFrame(data)

        # 状态筛选
        col1, col2 = st.columns([3, 1])
        with col1:
            status_filter = st.multiselect(
                "筛选状态",
                options=list(STATUS_LABELS.keys()),
                default=list(STATUS_LABELS.keys()),
                format_func=lambda x: STATUS_LABELS[x]
            )
        with col2:
            refresh = st.button("🔄 刷新")

        # 过滤数据
        filtered_df = df[df["状态"].isin([STATUS_LABELS[s] for s in status_filter])]

        # 显示表格
        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True
        )

        # 状态分布图
        st.markdown("### 📊 状态分布")
        col1, col2 = st.columns(2)

        with col1:
            status_counts = df["状态"].value_counts()
            fig_pie = px.pie(
                values=status_counts.values,
                names=status_counts.index,
                title="状态占比",
                color=status_counts.index,
                color_discrete_map={v: COLORS.get(k.lower(), "#6b7280") for k, v in STATUS_LABELS.items()}
            )
            fig_pie.update_layout(
                template="plotly_dark",
                height=300
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            fig_bar = px.bar(
                x=status_counts.index,
                y=status_counts.values,
                title="状态数量",
                color=status_counts.index,
                color_discrete_map={v: COLORS.get(k.lower(), "#6b7280") for k, v in STATUS_LABELS.items()}
            )
            fig_bar.update_layout(
                template="plotly_dark",
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("暂无Agent数据")


# ═══════════════════════════════════════════════════════════════════════════
# View 2: Cost Analytics（成本分析）
# ═══════════════════════════════════════════════════════════════════════════

def render_cost_analytics():
    """渲染成本分析视图"""
    st.markdown("## 💰 成本分析")

    # 获取成本数据
    total_cost = cost_tracker.get_total_cost()
    by_agent = cost_tracker.get_cost_by_agent()
    timeline = cost_tracker.get_cost_timeline(24)
    recent_records = cost_tracker.get_recent_records(50)

    # 成本概览卡片
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "总成本 (USD)",
            f"${total_cost['total_cost_usd']:.4f}",
            delta=None
        )
    with col2:
        st.metric(
            "总Token数",
            f"{total_cost['total_input_tokens'] + total_cost['total_output_tokens']:,}",
            delta=None
        )
    with col3:
        st.metric(
            "API调用次数",
            total_cost["total_calls"],
            delta=None
        )
    with col4:
        st.metric(
            "平均成本/次",
            f"${total_cost.get('cost_per_call', 0):.6f}",
            delta=None
        )

    st.divider()

    # Token分解
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 Token消耗")

        input_tokens = total_cost["total_input_tokens"]
        output_tokens = total_cost["total_output_tokens"]

        fig_tokens = px.pie(
            values=[input_tokens, output_tokens],
            names=["输入Token", "输出Token"],
            title="Input vs Output Token",
            color=["输入Token", "输出Token"],
            color_discrete_map={"输入Token": "#3b82f6", "输出Token": "#22c55e"}
        )
        fig_tokens.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig_tokens, use_container_width=True)

    with col2:
        st.markdown("### 📈 成本趋势（24小时）")

        if timeline:
            df_timeline = pd.DataFrame(timeline)
            df_timeline["time"] = pd.to_datetime(df_timeline["timestamp"], unit="s")

            fig_trend = px.line(
                df_timeline,
                x="time",
                y="cost_usd",
                title="每小时成本",
                color_discrete_sequence=["#4A90E2"]
            )
            fig_trend.update_layout(
                template="plotly_dark",
                height=300,
                xaxis_title="时间",
                yaxis_title="成本 (USD)"
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("暂无成本数据")

    # 按Agent分解
    st.markdown("### 🏷️ 按Agent成本分解")

    if by_agent:
        agent_data = []
        for agent_id, stats in by_agent.items():
            agent_data.append({
                "Agent": agent_id,
                "调用次数": stats["call_count"],
                "输入Token": stats["total_input_tokens"],
                "输出Token": stats["total_output_tokens"],
                "成本 (USD)": f"${stats['total_cost']:.4f}"
            })

        df_agents = pd.DataFrame(agent_data)
        df_agents = df_agents.sort_values("成本 (USD)", ascending=False)

        st.dataframe(df_agents, use_container_width=True, hide_index=True)

        # 成本柱状图
        fig_bar = px.bar(
            df_agents.head(10),
            x="Agent",
            y="成本 (USD)",
            title="Top 10 Agent成本",
            color="成本 (USD)",
            color_continuous_scale="Viridis"
        )
        fig_bar.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("暂无Agent成本数据")

    # 最近调用记录
    st.markdown("### 📝 最近API调用记录")

    if recent_records:
        records_data = []
        for r in recent_records:
            records_data.append({
                "时间": datetime.fromtimestamp(r.timestamp).strftime("%H:%M:%S"),
                "Agent": r.agent_id,
                "模型": r.model,
                "输入Token": r.input_tokens,
                "输出Token": r.output_tokens,
                "成本 (USD)": f"${r.cost_usd:.6f}"
            })

        df_records = pd.DataFrame(records_data)
        st.dataframe(df_records, use_container_width=True, hide_index=True)
    else:
        st.info("暂无调用记录")


# ═══════════════════════════════════════════════════════════════════════════
# View 3: Execution Timeline（执行时间线）
# ═══════════════════════════════════════════════════════════════════════════

def render_execution_timeline():
    """渲染执行时间线视图"""
    st.markdown("## 📈 执行时间线")

    # 时间范围选择
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        hours = st.selectbox("时间范围", [1, 6, 12, 24, 72, 168], index=3)
    with col2:
        refresh = st.button("🔄 刷新")
    with col3:
        st.caption(f"显示最近 {hours} 小时的数据")

    # 获取历史事件
    history = agent_state_manager.get_history(limit=500)

    if history:
        # 转换数据
        events_data = []
        for event in history:
            events_data.append({
                "时间": datetime.fromtimestamp(event.timestamp),
                "类型": event.event_type.value,
                "Agent": event.agent_id or "-",
                "持续时间": f"{event.duration_ms:.0f}ms" if event.duration_ms else "-",
                "详情": str(event.data)[:100]
            })

        df = pd.DataFrame(events_data)
        df = df[df["时间"] > datetime.now() - timedelta(hours=hours)]

        # 时间线图表
        st.markdown("### 📊 事件时间线")

        if not df.empty:
            # 事件计数按时间聚合
            df["分钟"] = df["时间"].dt.floor("T")
            events_per_minute = df.groupby(["分钟", "类型"]).size().reset_index(name="count")

            fig_timeline = px.line(
                events_per_minute,
                x="分钟",
                y="count",
                color="类型",
                title="事件频率",
                markers=True
            )
            fig_timeline.update_layout(
                template="plotly_dark",
                height=400,
                xaxis_title="时间",
                yaxis_title="事件数"
            )
            st.plotly_chart(fig_timeline, use_container_width=True)

        # 事件列表
        st.markdown("### 📋 事件详情")
        st.dataframe(df.sort_values("时间", ascending=False), use_container_width=True, hide_index=True)

        # 状态变化甘特图
        st.markdown("### 📊 Agent执行状态")

        agents = agent_state_manager.get_all_agents()
        if agents:
            gantt_data = []
            for agent in agents:
                if agent.start_time:
                    gantt_data.append({
                        "Agent": agent.name or agent.agent_id,
                        "状态": agent.status.value,
                        "开始": datetime.fromtimestamp(agent.start_time),
                        "结束": datetime.fromtimestamp(agent.end_time) if agent.end_time else datetime.now(),
                        "持续时间(s)": (agent.end_time or datetime.now().timestamp()) - agent.start_time
                    })

            if gantt_data:
                df_gantt = pd.DataFrame(gantt_data)

                # 使用plotly创建甘特图
                fig_gantt = px.timeline(
                    df_gantt,
                    x_start="开始",
                    x_end="结束",
                    y="Agent",
                    color="状态",
                    color_discrete_map=COLORS,
                    title="Agent执行时间线"
                )
                fig_gantt.update_layout(template="plotly_dark", height=max(300, len(df_gantt) * 40))
                st.plotly_chart(fig_gantt, use_container_width=True)
    else:
        st.info("暂无执行数据")


# ═══════════════════════════════════════════════════════════════════════════
# View 4: Human-in-the-Loop Inbox（人工审核收件箱）
# ═══════════════════════════════════════════════════════════════════════════

def render_hitl_inbox():
    """渲染人工审核收件箱"""
    st.markdown("## 👤 人工审核收件箱")

    # 获取待审核请求
    pending = hitl_manager.get_pending()
    all_requests = hitl_manager.get_all()

    # 统计
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("待审核", len(pending))
    with col2:
        approved = len([r for r in all_requests if r.status == "approved"])
        st.metric("已批准", approved)
    with col3:
        rejected = len([r for r in all_requests if r.status == "rejected"])
        st.metric("已拒绝", rejected)

    st.divider()

    if pending:
        st.markdown("### ⏳ 待审核请求")

        for req in pending:
            with st.container():
                st.markdown("---")

                col1, col2 = st.columns([4, 1])

                with col1:
                    st.markdown(f"**Agent**: {req.agent_id}")
                    st.markdown(f"**决策点**: {req.decision_point}")
                    st.markdown(f"**任务ID**: {req.task_id}")
                    st.markdown(f"**创建时间**: {datetime.fromtimestamp(req.created_at).strftime('%Y-%m-%d %H:%M:%S')}")

                    # 显示上下文
                    if req.context:
                        st.markdown("**上下文信息**:")
                        st.json(req.context)

                with col2:
                    # 审核按钮
                    comment = st.text_area("审核意见", key=f"comment_{req.request_id}", height=100)

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("✅ 批准", key=f"approve_{req.request_id}", type="primary"):
                            hitl_manager.approve(req.request_id, comment)
                            st.rerun()
                    with col_b:
                        if st.button("❌ 拒绝", key=f"reject_{req.request_id}", type="secondary"):
                            hitl_manager.reject(req.request_id, comment)
                            st.rerun()
    else:
        st.success("🎉 没有待审核的请求")

    # 历史审核记录
    st.divider()
    st.markdown("### 📝 审核历史")

    if all_requests:
        history = [r for r in all_requests if r.status != "pending"]
        if history:
            data = []
            for r in history[:50]:
                data.append({
                    "Agent": r.agent_id,
                    "决策点": r.decision_point,
                    "状态": "✅ 批准" if r.status == "approved" else "❌ 拒绝",
                    "审核时间": datetime.fromtimestamp(r.reviewed_at).strftime("%Y-%m-%d %H:%M:%S") if r.reviewed_at else "-",
                    "审核意见": r.reviewer_comment or "-"
                })

            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无审核历史")
    else:
        st.info("暂无审核记录")


# ═══════════════════════════════════════════════════════════════════════════
# View 5: Error Log（错误日志）
# ═══════════════════════════════════════════════════════════════════════════

def render_error_log():
    """渲染错误日志视图"""
    st.markdown("## ❌ 错误日志")

    # 获取历史事件
    history = agent_state_manager.get_history(limit=500)

    # 筛选错误事件
    error_events = [
        e for e in history
        if e.event_type.value in ["agent_error", "agent_retry"]
        or (e.data and e.data.get("error"))
    ]

    if error_events:
        # 错误分类统计
        error_types = {}
        for event in error_events:
            error_msg = event.data.get("error", "Unknown")
            error_type = ErrorClassifier.classify(error_msg).value
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # 统计卡片
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("错误总数", len(error_events))
        with col2:
            unique_errors = len(set(e.data.get("error", "") for e in error_events))
            st.metric("错误类型数", unique_errors)
        with col3:
            retry_count = len([e for e in error_events if e.event_type.value == "agent_retry"])
            st.metric("重试次数", retry_count)

        st.divider()

        # 错误类型分布
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 📊 错误类型分布")

            if error_types:
                df_errors = pd.DataFrame([
                    {"错误类型": k, "数量": v}
                    for k, v in error_types.items()
                ]).sort_values("数量", ascending=False)

                fig_pie = px.pie(
                    df_errors,
                    values="数量",
                    names="错误类型",
                    title="错误类型占比"
                )
                fig_pie.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.markdown("### 📈 错误趋势")

            df_timeline = pd.DataFrame([
                {"时间": datetime.fromtimestamp(e.timestamp), "错误": 1}
                for e in error_events
            ])

            if not df_timeline.empty:
                df_timeline = df_timeline.set_index("时间").resample("H").sum().reset_index()

                fig_line = px.line(
                    df_timeline,
                    x="时间",
                    y="错误",
                    title="每小时错误数"
                )
                fig_line.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig_line, use_container_width=True)

        # 错误列表
        st.markdown("### 📋 错误详情")

        data = []
        for event in error_events:
            error_msg = event.data.get("error", "Unknown")
            data.append({
                "时间": datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S"),
                "Agent": event.agent_id or "-",
                "错误类型": ErrorClassifier.classify(error_msg).value,
                "错误信息": error_msg[:100] + "..." if len(error_msg) > 100 else error_msg,
                "持续时间": f"{event.duration_ms:.0f}ms" if event.duration_ms else "-"
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 重试建议
        st.markdown("### 💡 重试策略建议")

        for error_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
            strategy = ErrorClassifier.get_retry_strategy(ErrorType(error_type))
            st.markdown(f"""
            **{error_type}** ({count}次)
            - 最大重试次数: {strategy['max_retries']}
            - 退避策略: {strategy.get('backoff', '无')}
            """)
    else:
        st.success("🎉 没有错误记录")


# ═══════════════════════════════════════════════════════════════════════════
# View 6: DAG Visualization（DAG可视化）
# ═══════════════════════════════════════════════════════════════════════════

def render_dag_visualization():
    """交互式 DAG 可视化视图 — 集成 WorkflowVisualizer，支持实时状态"""
    st.markdown("## 🔀 论文写作流程 DAG")

    # ── 1. 实时状态栏 ─────────────────────────────────────────
    try:
        agents = agent_state_manager.get_all_agents()
    except Exception:
        agents = []

    running = [a for a in agents if a.status.value == "running"]
    waiting = [a for a in agents if a.status.value in ("idle", "waiting")]
    failed = [a for a in agents if a.status.value == "failed"]
    done = [a for a in agents if a.status.value == "succeeded"]

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("🚀 运行中", len(running),
                  delta=" | ".join(a.agent_id for a in running) if running else None)
    with m2:
        st.metric("✅ 已完成", len(done))
    with m3:
        st.metric("⏳ 等待中", len(waiting))
    with m4:
        st.metric("❌ 失败", len(failed),
                  delta=" | ".join(a.agent_id for a in failed) if failed else None)
    with m5:
        st.metric("📊 总计", len(agents))

    if running:
        st.info("**正在执行：** " + " → ".join(f"`{a.agent_id}`" for a in running))
    if failed:
        st.error("**执行失败：** " + " | ".join(f"⚠️ `{a.agent_id}`" for a in failed))

    st.divider()

    # ── 2. 控制栏 ──────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 1, 1, 1])
    with ctrl1:
        search_q = st.text_input("🔍 搜索节点", placeholder="输入节点名称过滤…", label_visibility="collapsed")

    with ctrl2:
        layout_mode = st.selectbox("布局", ["水平", "垂直"], index=0)

    with ctrl3:
        theme_choice = st.selectbox("主题", ["深色", "浅色"], index=0)

    with ctrl4:
        st.write("")  # spacer
        st.button("🔄 刷新", type="secondary", use_container_width=True)

    # ── 3. 构建可视化 ─────────────────────────────────────────
    dag_nodes_def = [
        ("topic", "确定研究主题", "design"),
        ("outline", "生成论文大纲", "design"),
        ("outline_review", "大纲审核", "review"),
        ("chapter1", "第1章: 引言", "exec"),
        ("chapter2", "第2章: 文献综述", "exec"),
        ("chapter3", "第3章: 研究设计", "exec"),
        ("chapter4", "第4章: 实证分析", "exec"),
        ("chapter5", "第5章: 稳健性检验", "exec"),
        ("chapter6", "第6章: 结论建议", "exec"),
        ("chapter_review", "章节审核", "review"),
        ("revision", "修改润色", "decision"),
        ("finalize", "整合输出", "exec"),
        ("export", "导出文档", "exec"),
    ]

    type_colors = {"design": "#3b82f6", "exec": "#22c55e", "review": "#f59e0b", "decision": "#8b5cf6"}
    status_display = {"running": "运行中", "succeeded": "已完成", "failed": "执行失败", "idle": "待执行", "waiting": "等待中"}
    agent_status_map = {a.agent_id: a.status.value for a in agents}

    viz = WorkflowVisualizer()
    viz._nodes.append(VizNode(id="input", label="用户请求", type="input", color="#3b82f6", status="已完成"))

    prev = "input"
    for node_id, label, ntype in dag_nodes_def:
        sv = agent_status_map.get(node_id, "idle")
        ds = status_display.get(sv, "待执行")
        color = type_colors[ntype]
        if sv == "running": color = "#3b82f6"
        elif sv == "succeeded": color = "#22c55e"
        elif sv == "failed": color = "#ef4444"

        # 按搜索过滤：隐藏不匹配的节点
        if search_q and search_q.lower() not in label.lower() and search_q.lower() not in node_id.lower():
            pass  # 不加入 viz，但仍保持边连接
        else:
            viz._nodes.append(VizNode(id=node_id, label=label, type="agent", color=color, status=ds))

        viz._edges.append(VizEdge(source=prev, target=node_id, color="#6366f1"))
        prev = node_id

    viz._nodes.append(VizNode(id="output", label="最终结果", type="output", color="#22c55e", status="待执行"))
    viz._edges.append(VizEdge(source=prev, target="output", color="#22c55e"))

    # 生成 HTML
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        tmp_path = f.name
    try:
        viz.to_modern_html(tmp_path,
                           title="论文写作工作流",
                           theme="dark" if theme_choice == "深色" else "light",
                           layout="horizontal" if layout_mode == "水平" else "vertical")
        with open(tmp_path, encoding="utf-8") as f:
            html_content = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # ── 4. 嵌入可视化 ─────────────────────────────────────────
    st.components.v1.html(html_content, height=680, scrolling=False)

    # ── 5. 图例 + 说明 ────────────────────────────────────────
    lc1, lc2, lc3, lc4 = st.columns(4)
    with lc1: st.markdown("🔵 **设计** — 确定主题与大纲")
    with lc2: st.markdown("🟢 **执行** — 各章节撰写与检验")
    with lc3: st.markdown("🟡 **审核** — 大纲/章节审核")
    with lc4: st.markdown("🟣 **决策** — 修改润色判断")
    st.caption("💡 点击节点查看详情（耗时、Token、输入输出、工具调用、引用文献）| 运行中节点有脉冲动画")


# ═══════════════════════════════════════════════════════════════════════════
# 主函数：渲染所有高级视图
# ═══════════════════════════════════════════════════════════════════════════

def render_advanced_views():
    """渲染所有高级视图"""

    # 创建Tab
    tabs = st.tabs([
        "🚀 舰队状态",
        "💰 成本分析",
        "📈 执行时间线",
        "👤 人工审核",
        "❌ 错误日志",
        "🔀 DAG可视化"
    ])

    with tabs[0]:
        render_fleet_status()

    with tabs[1]:
        render_cost_analytics()

    with tabs[2]:
        render_execution_timeline()

    with tabs[3]:
        render_hitl_inbox()

    with tabs[4]:
        render_error_log()

    with tabs[5]:
        render_dag_visualization()
