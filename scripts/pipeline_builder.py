"""
scripts/pipeline_builder.py — Low-Code Pipeline Builder (Streamlit App)

A visual, low-code interface for building and running research pipelines.
Users can drag-and-drop agents, configure parameters, preview the generated
YAML, save it to config/agents.yaml, and run the pipeline.

Run:
    pip install streamlit pyyaml
    streamlit run scripts/pipeline_builder.py --server.port 8502

Dependencies:
    - streamlit  (pip install streamlit)
    - pyyaml     (pip install pyyaml)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import streamlit as st
import yaml

# ─── Path setup ────────────────────────────────────────────────────────────────
# Resolve workspace root (parent of scripts/)
WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_YAML = WORKSPACE_ROOT / "config" / "agents.yaml"
DRAFT_DIR = WORKSPACE_ROOT / "data" / "pipeline_drafts"
DRAFT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Stage constants (mirror PipelineStage enum) ─────────────────────────────
PAPER_STAGES = [
    "OUTLINE",
    "LITERATURE",
    "PLOTTING",
    "WRITING",
    "REFINEMENT",
]
ANALYST_STAGES = [
    "FINANCIAL_ANALYSIS",
]

# ─── Agent categories ─────────────────────────────────────────────────────────
PAPER_AGENTS = {"outline", "literature_review", "plotting", "section_writing", "content_refinement"}
ANALYST_AGENTS = {
    "fundamental_market",
    "fundamental_financial",
    "competitive",
    "risk",
    "valuation",
    "earnings_quality",
    "market",
}
ALL_AGENT_NAMES = PAPER_AGENTS | ANALYST_AGENTS

# ─── Color map ────────────────────────────────────────────────────────────────
CATEGORY_COLORS = {
    "paper": "blue",
    "analyst": "green",
    "utility": "gray",
}


def _agent_category(name: str) -> str:
    if name in PAPER_AGENTS:
        return "paper"
    if name in ANALYST_AGENTS:
        return "analyst"
    return "utility"


def _stage_color(idx: int) -> str:
    """Return a distinct color for each stage index."""
    colors = [
        "#9B59B6",  # OUTLINE
        "#3498DB",  # LITERATURE
        "#E67E22",  # PLOTTING
        "#27AE60",  # WRITING
        "#E74C3C",  # REFINEMENT
        "#1ABC9C",  # FINANCIAL_ANALYSIS
        "#34495E",  # REPORT_WRITING
    ]
    return colors[idx % len(colors)]


# ─── Session state helpers ────────────────────────────────────────────────────

def _init_state():
    """Initialize session state variables."""
    defaults = {
        "pb_tab": "New Pipeline",
        "pb_pipeline_name": "my_pipeline",
        "pb_pipeline_desc": "自定义流水线",
        "pb_steps": [],          # list[dict] — each step: {id, agent, stage, hitl_gate, max_iterations}
        "pb_selected_step": None,  # step id
        "pb_agent_data": {},     # name -> raw YAML dict
        "pb_pipelines": {},     # name -> raw YAML dict
        "pb_loaded": False,
        "pb_validation_errors": [],
        "pb_run_output": "",
        "pb_run_status": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _reload_yaml():
    """Reload agent definitions from config/agents.yaml."""
    if not CONFIG_YAML.exists():
        st.error(f"Config file not found: {CONFIG_YAML}")
        return

    with open(CONFIG_YAML, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    st.session_state.pb_agent_data = {
        **{k: {**v, "category": "paper"} for k, v in data.get("agents", {}).items()},
        **{k: {**v, "category": "analyst"} for k, v in data.get("analysts", {}).items()},
    }
    st.session_state.pb_pipelines = data.get("pipelines", {})
    st.session_state.pb_loaded = True


def _step_id() -> str:
    return str(int(time.time() * 1000))


def _build_pipeline_yaml() -> dict:
    """Build the YAML dict for the current pipeline."""
    st.session_state.pb_pipeline_name.strip() or "my_pipeline"
    desc = st.session_state.pb_pipeline_desc.strip() or "自定义流水线"

    steps_yaml = []
    for s in st.session_state.pb_steps:
        entry: dict[str, object] = {
            "agent": s["agent"],
            "stage": s["stage"],
            "hitl_gate": s.get("hitl_gate", False),
        }
        if s.get("max_iterations"):
            entry["max_iterations"] = s["max_iterations"]
        depends = s.get("depends_on", [])
        if depends:
            entry["depends_on"] = depends
        steps_yaml.append(entry)

    return {
        "name": desc,
        "description": desc,
        "mode": "sequential",
        "steps": steps_yaml,
    }


def _validate_pipeline() -> list[str]:
    """Validate the current pipeline and return a list of error messages."""
    errors: list[str] = []
    if not st.session_state.pb_pipeline_name.strip():
        errors.append("Pipeline name is required.")
    if not st.session_state.pb_steps:
        errors.append("Add at least one step to the pipeline.")
    step_agents = [s["agent"] for s in st.session_state.pb_steps]
    if len(step_agents) != len(set(step_agents)):
        errors.append("Duplicate agents in pipeline (same agent used multiple times).")
    for s in st.session_state.pb_steps:
        if s["agent"] not in st.session_state.pb_agent_data:
            errors.append(f"Unknown agent: '{s['agent']}'.")
    return errors


def _save_draft():
    """Auto-save current pipeline draft to data/pipeline_drafts/."""
    name = st.session_state.pb_pipeline_name.strip() or "draft"
    safe_name = name.replace("/", "_").replace("\\", "_")
    draft_file = DRAFT_DIR / f"{safe_name}_{int(time.time())}.yaml"
    pipeline_yaml = _build_pipeline_yaml()
    content = {
        "pipeline_name": st.session_state.pb_pipeline_name,
        "pipeline_desc": st.session_state.pb_pipeline_desc,
        "pipeline": pipeline_yaml,
        "steps": st.session_state.pb_steps,
    }
    with open(draft_file, "w", encoding="utf-8") as fh:
        yaml.dump(content, fh, allow_unicode=True, default_flow_style=False)
    return draft_file


def _generate_yaml_output() -> str:
    """Generate full agents.yaml-compatible YAML string."""
    if not CONFIG_YAML.exists():
        return "# Error: config/agents.yaml not found"

    with open(CONFIG_YAML, encoding="utf-8") as fh:
        base_data = yaml.safe_load(fh) or {}

    pipeline_name = st.session_state.pb_pipeline_name.strip() or "my_pipeline"
    pipeline_def = _build_pipeline_yaml()

    # Merge into pipelines section
    base_data.setdefault("pipelines", {})
    base_data["pipelines"][pipeline_name] = pipeline_def

    return yaml.dump(
        base_data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _load_pipeline(name: str):
    """Load an existing pipeline into the editor."""
    raw = st.session_state.pb_pipelines.get(name, {})
    steps_raw = raw.get("steps", [])

    st.session_state.pb_pipeline_name = name
    st.session_state.pb_pipeline_desc = raw.get("description", "")

    new_steps = []
    for s in steps_raw:
        new_steps.append({
            "id": _step_id(),
            "agent": s.get("agent", ""),
            "stage": s.get("stage", "OUTLINE"),
            "hitl_gate": s.get("hitl_gate", False),
            "max_iterations": s.get("max_iterations", None),
            "depends_on": s.get("depends_on", []),
        })

    st.session_state.pb_steps = new_steps
    st.session_state.pb_selected_step = None


# ─── UI Components ─────────────────────────────────────────────────────────────

def _render_agent_card(name: str, data: dict):
    """Render a single agent card in the palette."""
    category = data.get("category", "utility")
    CATEGORY_COLORS.get(category, "gray")
    role = data.get("role", "")
    goal = data.get("goal", "")
    color_map = {"paper": "🟦", "analyst": "🟩", "utility": "⬜"}

    with st.expander(f"{color_map.get(category, '⬜')} `{name}`", expanded=False):
        st.markdown(f"**角色:** {role}")
        st.markdown(f"**目标:** {goal}")
        tools = data.get("allowed_tools", [])
        if tools:
            st.markdown(f"**工具:** `{'`, `'.join(tools)}`")


def _render_step_card(step: dict, idx: int):
    """Render a single pipeline step card."""
    agent = step["agent"]
    data = st.session_state.pb_agent_data.get(agent, {})
    role = data.get("role", agent)
    stage = step.get("stage", "OUTLINE")
    hitl = step.get("hitl_gate", False)
    max_iters = step.get("max_iterations")

    icon = "🛑" if hitl else "▶"
    badge = f"`<hitl>`" if hitl else ""
    iters_badge = f"`iters={max_iters}`" if max_iters else ""

    is_selected = st.session_state.pb_selected_step == step["id"]

    col1, col2 = st.columns([0.05, 1])
    with col1:
        st.markdown(f"**{idx+1}.**")
    with col2:
        label = f"{icon} `{agent}` {badge} {iters_badge}"
        if is_selected:
            st.markdown(f":blue[{label}]")
        else:
            st.markdown(label)
        st.caption(f"{stage} · {role[:60]}")

    # Click to select
    if st.button("✏️", key=f"sel_{step['id']}"):
        st.session_state.pb_selected_step = step["id"]
        st.rerun()

    # Up / Down reorder
    c1, c2 = st.columns(2)
    with c1:
        if idx > 0 and st.button("⬆️ 上移", key=f"up_{step['id']}"):
            steps = st.session_state.pb_steps
            steps[idx], steps[idx - 1] = steps[idx - 1], steps[idx]
            st.session_state.pb_steps = steps
            st.rerun()
    with c2:
        if idx < len(st.session_state.pb_steps) - 1 and st.button("⬇️ 下移", key=f"down_{step['id']}"):
            steps = st.session_state.pb_steps
            steps[idx], steps[idx + 1] = steps[idx + 1], steps[idx]
            st.session_state.pb_steps = steps
            st.rerun()


def _render_step_config_panel():
    """Render the right-side step configuration panel."""
    step_id = st.session_state.pb_selected_step
    if not step_id:
        st.info("👈 从下方选择一个步骤进行配置")
        return

    step = next((s for s in st.session_state.pb_steps if s["id"] == step_id), None)
    if not step:
        st.session_state.pb_selected_step = None
        st.rerun()
        return

    agent = step["agent"]
    data = st.session_state.pb_agent_data.get(agent, {})

    st.subheader(f"⚙️ 配置步骤: `{agent}`")
    st.caption(f"角色: {data.get('role', '')}")

    # Stage
    all_stages = PAPER_STAGES + ANALYST_STAGES
    current_stage = step.get("stage", "OUTLINE")
    new_stage = st.selectbox(
        "Stage（阶段）",
        all_stages,
        index=all_stages.index(current_stage) if current_stage in all_stages else 0,
        key=f"stage_{step_id}",
    )
    step["stage"] = new_stage

    # HITL gate
    hitl = st.checkbox("🛑 启用人工审核点 (HITL Gate)", value=step.get("hitl_gate", False), key=f"hitl_{step_id}")
    step["hitl_gate"] = hitl

    # Max iterations override
    default_iters = data.get("max_iterations", 3)
    use_override = st.checkbox("覆盖 max_iterations", value=step.get("max_iterations") is not None, key=f"override_{step_id}")
    if use_override:
        max_iters = st.number_input(
            f"max_iterations (默认: {default_iters})",
            min_value=1,
            max_value=50,
            value=step.get("max_iterations") or default_iters,
            key=f"iters_{step_id}",
        )
        step["max_iterations"] = max_iters
    else:
        step["max_iterations"] = None

    # Allowed tools (read-only)
    tools = data.get("allowed_tools", [])
    if tools:
        st.markdown(f"**可用工具:** `{'`, `'.join(tools)}`")

    # Remove step button
    st.divider()
    if st.button("🗑️ 移除此步骤", type="primary", key=f"rm_{step_id}"):
        st.session_state.pb_steps = [s for s in st.session_state.pb_steps if s["id"] != step_id]
        st.session_state.pb_selected_step = None
        st.rerun()


# ─── Main app ─────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Pipeline Builder — FinResearch Agent",
        page_icon="🔧",
        layout="wide",
    )

    st.title("🔧 研究流水线构建器")
    st.caption("可视化编排 Agent 流水线 → 生成 YAML 配置 → 一键运行")

    _init_state()

    # ── Load data once ──────────────────────────────────────────────────────
    if not st.session_state.pb_loaded:
        _reload_yaml()

    # ── Sidebar ─────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("📋 导航")
        tab = st.radio(
            "选择功能",
            ["新建流水线", "编辑现有", "运行流水线"],
            index=["新建流水线", "编辑现有", "运行流水线"].index(st.session_state.pb_tab)
            if st.session_state.pb_tab in ["新建流水线", "编辑现有", "运行流水线"]
            else 0,
            key="pb_nav_radio",
        )
        st.session_state.pb_tab = tab

        st.divider()

        # ── Agent Palette ───────────────────────────────────────────────────
        st.subheader("🧩 Agent 组件库")
        st.caption("点击展开查看详情")

        # Grouped by category
        paper_agents = {k: v for k, v in st.session_state.pb_agent_data.items() if v.get("category") == "paper"}
        analyst_agents = {k: v for k, v in st.session_state.pb_agent_data.items() if v.get("category") == "analyst"}

        with st.expander("🟦 论文组件 (Paper)", expanded=True):
            for name, data in sorted(paper_agents.items()):
                _render_agent_card(name, data)

        with st.expander("🟩 分析师 (Analyst)", expanded=False):
            for name, data in sorted(analyst_agents.items()):
                _render_agent_card(name, data)

        st.divider()

        # ── Pipeline Templates ──────────────────────────────────────────────
        st.subheader("📦 模板流水线")
        for pl_name in st.session_state.pb_pipelines:
            if st.button(f"📥 加载: `{pl_name}`", key=f"load_pl_{pl_name}"):
                _load_pipeline(pl_name)
                st.session_state.pb_tab = "新建流水线"
                st.rerun()

        # Recent drafts
        drafts = sorted(DRAFT_DIR.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        if drafts:
            st.divider()
            st.subheader("📁 最近草稿")
            for draft in drafts:
                if st.button(f"📄 {draft.stem[:30]}", key=f"draft_{draft}"):
                    try:
                        with open(draft, encoding="utf-8") as fh:
                            content = yaml.safe_load(fh)
                        st.session_state.pb_pipeline_name = content.get("pipeline_name", draft.stem)
                        st.session_state.pb_pipeline_desc = content.get("pipeline_desc", "")
                        saved_steps = content.get("steps", [])
                        if not any(s["id"] for s in saved_steps):
                            for s in saved_steps:
                                s["id"] = _step_id()
                        st.session_state.pb_steps = saved_steps
                        st.session_state.pb_selected_step = None
                        st.session_state.pb_tab = "新建流水线"
                        st.rerun()
                    except Exception as e:
                        st.error(f"加载失败: {e}")

    # ── Tab: New Pipeline ────────────────────────────────────────────────────
    if st.session_state.pb_tab == "新建流水线":
        col_left, col_center, col_right = st.columns([1, 2, 1])

        # ── Left: Add agents ─────────────────────────────────────────────
        with col_left:
            st.subheader("➕ 添加步骤")

            all_agent_names = sorted(st.session_state.pb_agent_data.keys())
            selected_agent = st.selectbox("选择 Agent", all_agent_names, key="pb_add_agent_select")

            if selected_agent:
                data = st.session_state.pb_agent_data.get(selected_agent, {})
                role = data.get("role", "")
                st.caption(f"**{role}**" if role else "")

            default_stage = PAPER_STAGES[0]
            if selected_agent in ANALYST_AGENTS:
                default_stage = ANALYST_STAGES[0]

            selected_stage = st.selectbox("Stage", PAPER_STAGES + ANALYST_STAGES,
                                          index=(PAPER_STAGES + ANALYST_STAGES).index(default_stage),
                                          key="pb_add_stage_select")

            if st.button("✅ 添加到流水线", type="primary", key="pb_add_step_btn"):
                new_step = {
                    "id": _step_id(),
                    "agent": selected_agent,
                    "stage": selected_stage,
                    "hitl_gate": False,
                    "max_iterations": None,
                    "depends_on": [],
                }
                st.session_state.pb_steps.append(new_step)
                st.rerun()

            st.divider()

            # Pipeline metadata
            st.subheader("📝 流水线元信息")
            st.text_input("流水线名称", value=st.session_state.pb_pipeline_name,
                           key="pb_name_input", placeholder="my_pipeline")
            st.session_state.pb_pipeline_name = st.session_state.pb_name_input

            st.text_area("描述", value=st.session_state.pb_pipeline_desc,
                         key="pb_desc_input", placeholder="流水线描述（选填）")
            st.session_state.pb_pipeline_desc = st.session_state.pb_desc_input

        # ── Center: Pipeline sequence ──────────────────────────────────────
        with col_center:
            st.subheader("🔗 流水线序列")
            if not st.session_state.pb_steps:
                st.info("⬅️ 从左侧选择 Agent 并添加到流水线")
            else:
                for idx, step in enumerate(st.session_state.pb_steps):
                    _render_step_card(step, idx)

                st.divider()

                # Add from existing steps
                if len(st.session_state.pb_steps) >= 2:
                    st.caption("💡 可以拖动上下按钮调整顺序")

                # Add step shortcut
                with st.expander("➕ 继续添加"):
                    agent_options = sorted(st.session_state.pb_agent_data.keys())
                    quick_agent = st.selectbox("Agent", agent_options, key="pb_quick_agent")
                    quick_stage = st.selectbox("Stage", PAPER_STAGES + ANALYST_STAGES, key="pb_quick_stage")
                    if st.button("添加", key="pb_quick_add"):
                        st.session_state.pb_steps.append({
                            "id": _step_id(),
                            "agent": quick_agent,
                            "stage": quick_stage,
                            "hitl_gate": False,
                            "max_iterations": None,
                            "depends_on": [],
                        })
                        st.rerun()

        # ── Right: Step config ────────────────────────────────────────────
        with col_right:
            _render_step_config_panel()

    # ── Tab: Edit Existing ──────────────────────────────────────────────────
    elif st.session_state.pb_tab == "编辑现有":
        st.subheader("📂 选择要编辑的流水线")

        pipelines = st.session_state.pb_pipelines
        if not pipelines:
            st.warning("暂无保存的流水线。")
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                pl_names = list(pipelines.keys())
                pl_to_edit = st.selectbox("流水线", pl_names, key="pb_edit_select")
            with col2:
                st.write("")  # spacer

            raw = pipelines.get(pl_to_edit, {})
            st.markdown(f"**描述:** {raw.get('description', '—')}")
            st.markdown(f"**模式:** {raw.get('mode', 'sequential')}")

            steps_raw = raw.get("steps", [])
            st.markdown(f"**步骤数:** {len(steps_raw)}")

            # List steps
            for i, s in enumerate(steps_raw):
                st.markdown(f"  {i+1}. `{s.get('agent', '')}` — {s.get('stage', '')} "
                            f"{'🛑' if s.get('hitl_gate') else ''}")

            if st.button("✏️ 在编辑器中打开", type="primary", key="pb_edit_open"):
                _load_pipeline(pl_to_edit)
                st.session_state.pb_tab = "新建流水线"
                st.rerun()

            st.divider()
            st.subheader("🗑️ 删除流水线")
            st.warning("此操作会从 config/agents.yaml 中移除流水线定义！")
            if st.button("确认删除", type="secondary", key="pb_delete_confirm"):
                # Remove from YAML file
                if CONFIG_YAML.exists():
                    with open(CONFIG_YAML, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    data.get("pipelines", {}).pop(pl_to_edit, None)
                    with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
                        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False)
                    _reload_yaml()
                    st.success(f"已删除: {pl_to_edit}")
                    st.rerun()

    # ── Tab: Run Pipeline ───────────────────────────────────────────────────
    elif st.session_state.pb_tab == "运行流水线":
        st.subheader("🚀 运行流水线")

        # Validation
        errors = _validate_pipeline()
        if errors:
            for err in errors:
                st.error(f"⚠️ {err}")
            st.stop()

        col1, col2 = st.columns(2)

        with col1:
            st.text_input("研究主题", value="", key="pb_topic_input", placeholder="输入研究主题...")

        with col2:
            venue_options = ["通用", "经济研究", "金融研究", "管理世界", "NeurIPS", "ICML", "CVPR", "ACL", "IEEE"]
            st.selectbox("目标期刊/会议", venue_options, key="pb_venue_select")

        st.divider()

        # Action buttons
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            save_clicked = st.button("💾 保存 YAML", type="primary")

        with c2:
            copy_clicked = st.button("📋 复制 YAML")

        with c3:
            draft_clicked = st.button("📝 保存草稿")

        with c4:
            run_clicked = st.button("▶️ 运行流水线")

        # Generate YAML
        yaml_output = _generate_yaml_output()

        if save_clicked:
            try:
                with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
                    fh.write(yaml_output)
                st.success(f"✅ 已保存到 {CONFIG_YAML}")
                _reload_yaml()
            except Exception as e:
                st.error(f"保存失败: {e}")

        if copy_clicked:
            st.code(yaml_output, language="yaml")
            st.info("⬆️ 上方是 YAML 内容，手动复制")

        if draft_clicked:
            draft_path = _save_draft()
            st.success(f"📝 草稿已保存: {draft_path.name}")

        if run_clicked:
            topic = st.session_state.pb_topic_input.strip()
            if not topic:
                st.error("请输入研究主题")
                st.stop()

            # Save YAML first
            try:
                with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
                    fh.write(yaml_output)
                _reload_yaml()
            except Exception as e:
                st.error(f"保存YAML失败: {e}")
                st.stop()

            st.info(f"⏳ 正在运行流水线: **{topic}** (Ctrl+C 停止)")
            st.session_state.pb_run_output = ""
            st.session_state.pb_run_status = "running"

            output_placeholder = st.empty()
            status_placeholder = st.empty()

            try:
                import base64

                # Secure: encode topic as base64 to prevent command injection
                topic_b64 = base64.b64encode(topic.encode("utf-8")).decode("ascii")

                proc = subprocess.Popen(
                    [
                        sys.executable, "-c",
                        f"""
import sys, base64, json
sys.path.insert(0, '{WORKSPACE_ROOT}')
topic = base64.b64decode('{topic_b64}').decode('utf-8')
from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig
config = AgentPipelineConfig(topic=topic, auto_dashboard=False, visualize=False)
pipeline = AgentPipeline(config=config)
result = pipeline.run(topic=topic)
print('DONE:', result.success)
print('OUTLINE:', bool(result.outline))
print('WRITING:', bool(result.writing))
""",
                    ],
                    cwd=str(WORKSPACE_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                for line in proc.stdout:
                    st.session_state.pb_run_output += line
                    output_placeholder.code(st.session_state.pb_run_output, language="bash")

                proc.wait()
                st.session_state.pb_run_status = "done"

                if "DONE: True" in st.session_state.pb_run_output:
                    status_placeholder.success("✅ 流水线运行成功！")
                else:
                    status_placeholder.warning("⚠️ 流水线结束，请检查输出")

            except Exception as e:
                st.session_state.pb_run_status = "error"
                st.error(f"运行出错: {e}")

    # ── YAML Preview (always visible below main content) ───────────────────
    st.divider()
    st.subheader("📄 YAML 预览")

    errors = _validate_pipeline()
    if errors:
        with st.expander("⚠️ 验证警告", expanded=True):
            for err in errors:
                st.warning(err)

    yaml_out = _build_pipeline_yaml()
    preview_str = yaml.dump(yaml_out, allow_unicode=True, default_flow_style=False, sort_keys=False)
    st.code(preview_str, language="yaml")

    if st.button("💾 立即保存到 config/agents.yaml", type="primary"):
        full_yaml = _generate_yaml_output()
        try:
            with open(CONFIG_YAML, "w", encoding="utf-8") as fh:
                fh.write(full_yaml)
            _reload_yaml()
            st.success("✅ 已保存")
        except Exception as e:
            st.error(f"保存失败: {e}")

    # ── Agent Details Panel ─────────────────────────────────────────────────
    with st.expander("📖 Agent 详情参考"):
        tab_detail = st.tabs(["论文组件", "分析师组件"])
        with tab_detail[0]:
            for name, data in sorted(paper_agents := {
                k: v for k, v in st.session_state.pb_agent_data.items()
                if v.get("category") == "paper"
            }.items()):
                st.markdown(f"### `{name}`")
                st.markdown(f"**角色:** {data.get('role', '')}")
                st.markdown(f"**目标:** {data.get('goal', '')}")
                backstory = data.get("backstory", "")
                if backstory:
                    st.markdown(f"**背景:** {backstory[:200]}...")
                st.markdown(f"**LLM:** `{data.get('llm_model', '—')}` | "
                            f"**温度:** `{data.get('temperature', '—')}` | "
                            f"**最大迭代:** `{data.get('max_iterations', '—')}`")
                st.divider()

        with tab_detail[1]:
            for name, data in sorted({
                k: v for k, v in st.session_state.pb_agent_data.items()
                if v.get("category") == "analyst"
            }.items()):
                st.markdown(f"### `{name}`")
                st.markdown(f"**角色:** {data.get('role', '')}")
                st.markdown(f"**目标:** {data.get('goal', '')}")
                st.markdown(f"**LLM:** `{data.get('llm_model', '—')}` | "
                            f"**最大迭代:** `{data.get('max_iterations', '—')}`")
                st.divider()

    # ── Footer ─────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "Pipeline Builder · FinResearch Agent · "
        f"已加载 {len(st.session_state.pb_agent_data)} 个 Agent, "
        f"{len(st.session_state.pb_pipelines)} 个流水线 · "
        f"配置文件: `{CONFIG_YAML}`"
    )


if __name__ == "__main__":
    main()
