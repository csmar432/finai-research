#!/usr/bin/env python3
"""
交互式论文写作工作流
====================
核心原则：
1. 先出大纲，用户确认后再逐步生成
2. 所有数据必须真实，禁止编造
3. 每个章节完成后询问用户意见

使用方法：
  python scripts/interactive_paper_pipeline.py

工作流程：
  1. 确定研究主题 → 用户确认
  2. 生成论文大纲 → 用户确认
  3. 逐章节生成内容 → 用户确认
  4. 数据分析与实证 → 用户确认
  5. 整合与润色
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 路径设置
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# ═══════════════════════════════════════════════════════════════════════════
# 阶段状态
# ═══════════════════════════════════════════════════════════════════════════

class PaperWorkflow:
    """论文写作工作流状态管理"""

    def __init__(self):
        self.project_dir: Path | None = None
        self.topic: str | None = None
        self.title: str | None = None
        self.outline: dict | None = None
        self.draft: dict = {}
        self.status = "初始化"

    def new_project(self, topic: str) -> Path:
        """创建新项目目录"""
        # 生成项目目录名（拼音或英文）
        import re
        safe_name = re.sub(r'[^\w\-]', '_', topic[:20])
        self.project_dir = PROJECT_ROOT / "projects" / safe_name / "chapters"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.topic = topic
        self.status = "项目创建"
        return self.project_dir

    def save_outline(self, outline: dict):
        """保存大纲"""
        self.outline = outline
        self.status = "大纲已定"

        # 保存到文件
        from pathlib import Path

        # Always use absolute path for the config file
        project_root = Path(__file__).parent.parent.resolve()
        config_path = project_root / "config" / "project_config.json"

        try:
            import json as _json
            data = _json.loads(config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, _json.JSONDecodeError):
            data = {}

        data.update({
            "title": self.title,
            "topic": self.topic,
            "outline": outline,
            "status": "outline_confirmed"
        })
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_chapter(self, chapter_name: str, content: str):
        """保存章节"""
        self.draft[chapter_name] = content
        file_path = self.project_dir / f"{chapter_name}.md"
        file_path.write_text(content, encoding="utf-8")
        print(f"✅ 章节已保存: {file_path}")

    def generate_full_paper(self) -> str:
        """整合所有章节为完整论文"""
        sections = []
        for name, content in self.draft.items():
            sections.append(f"\n\n{'='*60}\n{name}\n{'='*60}\n\n")
            sections.append(content)

        full_paper = "".join(sections)
        output_path = self.project_dir / "全文草稿.md"
        output_path.write_text(full_paper, encoding="utf-8")
        return full_paper


# ═══════════════════════════════════════════════════════════════════════════
# 用户交互函数
# ═══════════════════════════════════════════════════════════════════════════

def ask_user(question: str, options: list[str] = None, default: str = "y") -> str:
    """询问用户并获取回答"""
    print(f"\n❓ {question}")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"  [{i}] {opt}")
        while True:
            try:
                choice = input(f"请选择 (默认{default}): ").strip()
                if not choice:
                    return default
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
                print("无效选择，请重试")
            except ValueError:
                print("请输入数字")
    else:
        response = input("(直接回车确认) ").strip()
        return response if response else default
    return default


def confirm_proceed(question: str = "确认继续？") -> bool:
    """确认是否继续"""
    response = ask_user(question, ["继续", "修改", "退出"])
    if response == "退出":
        print("已退出工作流")
        sys.exit(0)
    return response == "继续"


# ═══════════════════════════════════════════════════════════════════════════
# LLM 调用
# ═══════════════════════════════════════════════════════════════════════════

def get_llm_response(prompt: str, system: str = "", task: str = "general") -> str:
    """调用 LLM 获取响应"""
    # 优先使用 DeepSeek
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if api_key:
        return call_deepseek(prompt, system)

    # 降级方案：返回模拟响应（仅用于测试）
    print("⚠️ 未配置 LLM API，生成模拟响应")
    return _generate_mock_response(prompt, task)


def call_deepseek(prompt: str, system: str = "") -> str:
    """调用 DeepSeek API（model_id 从 llm_config.json 动态读取，不再硬编码）"""
    import openai

    from scripts.ai_router import build_model_pool

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")

    # 从配置动态读取 model_id（而非硬编码）
    from scripts.ai_router import ModelKey
    pool = build_model_pool()
    cfg = pool.get(ModelKey.DEEPSEEK_FLASH)
    model_id = cfg.model_id if cfg else "deepseek-v4-flash"

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        timeout=120,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    print(f"  ⏳ 等待 LLM 响应... (model={model_id})")
    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=0.7,
        max_tokens=4000,
    )

    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("LLM 返回空内容")

    return content


def _generate_mock_response(prompt: str, task: str) -> str:
    """生成模拟响应（仅用于测试）"""
    if task == "topics":
        return """
## 备选研究题目

### 题目1：碳排放权交易试点政策对企业绿色创新的影响
- **研究问题**：碳交易机制是否促进企业绿色专利产出？
- **数据需求**：上市公司绿色专利数据、碳交易试点名单
- **方法**：双重差分法(DID)

### 题目2：绿色信贷政策对企业环境绩效的影响
- **研究问题**：绿色信贷政策是否改善企业环境表现？
- **数据需求**：银行绿色信贷数据、企业污染排放数据
- **方法**：双重差分法+倾向得分匹配

### 题目3：环境规制对企业出口竞争力的影响
- **研究问题**：环境规制是否削弱出口竞争力？
- **数据需求**：海关出口数据、环境处罚数据
- **方法**：工具变量法
"""
    elif task == "outline":
        return """
## 论文大纲

### 第一部分：引言（约1500字）
1. 研究背景与问题提出
2. 研究意义（理论意义、实践意义）
3. 研究框架与结构安排

### 第二部分：文献综述与研究假设（约2000字）
1. 核心概念界定
2. 文献综述
3. 研究假设

### 第三部分：研究设计（约1500字）
1. 样本选择与数据来源
2. 变量定义
3. 模型设定

### 第四部分：实证结果与分析（约2000字）
1. 描述性统计
2. 基准回归结果
3. 异质性分析
4. 机制检验

### 第五部分：稳健性检验（约1000字）
1. 平行趋势检验
2. 安慰剂检验
3. PSM-DID检验

### 第六部分：结论与政策建议（约500字）
1. 研究结论
2. 政策建议
3. 研究局限与未来展望
"""
    elif task == "chapter":
        return """
# 章节标题

## 章节内容

本章节将根据大纲要求撰写具体内容...

**注意**：此为模拟内容，需要 LLM API 才能生成真实内容。
"""
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# 工作流步骤
# ═══════════════════════════════════════════════════════════════════════════

def step1_topic_selection(workflow: PaperWorkflow):
    """步骤1：确定研究主题"""
    print("\n" + "="*60)
    print("📝 步骤1：确定研究主题")
    print("="*60)

    print("""
请描述你的研究方向，例如：
- "我想研究碳交易政策对企业绿色创新的影响"
- "我想研究绿色金融对上市公司环境绩效的影响"
- "我想研究环境规制对企业出口竞争力的影响"
""")

    topic = input("请输入研究主题（输入 q 退出）: ").strip()

    if topic.lower() == 'q':
        print("已退出")
        sys.exit(0)

    if not topic:
        print("❌ 研究主题不能为空")
        return step1_topic_selection(workflow)

    workflow.new_project(topic)

    # 生成备选题目
    print("\n📊 根据您的研究方向，正在生成备选题目...")

    prompt = f"""用户研究方向：{topic}

请生成3-5个具体的研究题目建议，每个题目包含：
1. 题目名称
2. 核心研究问题（一句话）
3. 主要数据来源
4. 建议的实证方法

要求：
- 题目要有学术价值和现实意义
- 方法要规范可行
- 数据要可得

请用中文回复。
"""

    try:
        response = get_llm_response(prompt, task="topics")
        print("\n📋 备选题目：")
        print(response)

        # 让用户选择或自定义
        choice = ask_user("请选择题目编号，或输入自定义题目",
                         ["使用题目1", "使用题目2", "使用题目3", "自定义题目"])

        if choice == "自定义题目":
            custom_title = input("请输入自定义题目: ").strip()
            workflow.title = custom_title
        else:
            # 提取选择的题目
            idx = int(choice[-1]) - 1
            workflow.title = f"备选题目{idx+1}"  # 简化处理

    except Exception as e:
        print(f"⚠️ LLM调用失败: {e}，使用默认题目")
        workflow.title = topic

    print(f"\n✅ 确定研究题目: {workflow.title}")
    return workflow.title


def step2_outline_generation(workflow: PaperWorkflow):
    """步骤2：生成论文大纲"""
    print("\n" + "="*60)
    print("📝 步骤2：生成论文大纲")
    print("="*60)

    print(f"\n📌 研究题目: {workflow.title}")
    print("\n⏳ 正在生成论文大纲...")

    prompt = f"""请为以下研究题目生成完整的论文大纲：

题目：{workflow.title}

要求：
1. 包含6-8个主要章节
2. 每个章节要有关键内容点
3. 总字数预估：10000-15000字
4. 方法规范：包含实证研究设计
5. 结构完整：引言→文献综述→研究设计→实证分析→结论

请用Markdown格式回复，结构要清晰。
"""

    try:
        outline_text = get_llm_response(prompt, task="outline")
        print("\n📋 论文大纲：")
        print(outline_text)

        # 保存大纲
        workflow.outline = {"title": workflow.title, "outline": outline_text}
        workflow.save_outline(workflow.outline)

        # 让用户确认
        choice = ask_user("大纲是否满意？",
                         ["满意，开始写第一章", "需要修改", "重新生成"])

        if choice == "需要修改":
            modifications = input("请描述需要修改的内容: ").strip()
            print("📝 已记录修改意见，将根据反馈调整")
            workflow.outline["user_modifications"] = modifications

        elif choice == "重新生成":
            return step2_outline_generation(workflow)

    except Exception as e:
        print(f"⚠️ LLM调用失败: {e}")
        # 使用默认大纲
        workflow.outline = {
            "title": workflow.title,
            "outline": _generate_mock_response("", "outline")
        }
        workflow.save_outline(workflow.outline)

    return workflow.outline


def step3_chapter_writing(workflow: PaperWorkflow):
    """步骤3：逐章节写作"""
    print("\n" + "="*60)
    print("📝 步骤3：逐章节写作")
    print("="*60)

    print("\n📌 大纲已确认，开始逐章节写作")
    print("="*60)

    # 定义各章节
    chapters = [
        ("引言", "研究背景、问题提出、研究意义、框架结构"),
        ("文献综述与假设", "概念界定、文献评述、研究假设"),
        ("研究设计", "样本选择、变量定义、模型设定"),
        ("实证结果", "描述性统计、基准回归、异质性分析"),
        ("稳健性检验", "平行趋势、安慰剂、PSM-DID"),
        ("结论与建议", "研究结论、政策建议、研究局限"),
    ]

    for i, (chapter_name, content_desc) in enumerate(chapters, 1):
        print(f"\n{'─'*60}")
        print(f"📖 第{i}章：{chapter_name}")
        print(f"{'─'*60}")
        print(f"内容要点：{content_desc}")

        # 检查是否有缓存
        cached_file = workflow.project_dir / f"{chapter_name}.md"
        if cached_file.exists():
            choice = ask_user("发现已有草稿，是否使用？",
                            ["使用现有草稿", "重新生成"])
            if choice == "使用现有草稿":
                print(f"✅ 使用缓存: {chapter_name}")
                workflow.draft[chapter_name] = cached_file.read_text(encoding="utf-8")
                continue

        # 生成章节内容
        prompt = f"""请撰写论文的第{i}章：{chapter_name}

研究题目：{workflow.title}

章节内容要点：{content_desc}

完整大纲：
{workflow.outline.get('outline', '')}

要求：
1. 约1000-2000字
2. 学术论文写作规范
3. 使用Markdown格式
4. 如需数据表格，先留空或使用占位符"[数据表格]"
5. 不要编造任何数据

请开始撰写。
"""

        try:
            print("⏳ 正在生成内容...")
            chapter_content = get_llm_response(prompt, task="chapter")
            print("\n📄 生成内容预览（前500字）：")
            print(chapter_content[:500] + "...")

            # 保存章节
            workflow.save_chapter(chapter_name, chapter_content)

            # 让用户确认
            choice = ask_user("章节内容是否满意？",
                            ["满意，继续下一章", "需要修改", "重新生成"])

            if choice == "需要修改":
                modifications = input("请描述需要修改的内容: ").strip()
                # 重新生成
                prompt += f"\n\n用户修改意见：{modifications}"
                chapter_content = get_llm_response(prompt, task="chapter")
                workflow.save_chapter(chapter_name, chapter_content)

            elif choice == "重新生成":
                chapter_content = get_llm_response(prompt, task="chapter")
                workflow.save_chapter(chapter_name, chapter_content)

        except Exception as e:
            print(f"⚠️ LLM调用失败: {e}")
            workflow.save_chapter(chapter_name, f"# {chapter_name}\n\n[待生成]")

    print("\n" + "="*60)
    print("✅ 所有章节写作完成！")
    print("="*60)

    return workflow.draft


def step4_data_analysis(workflow: PaperWorkflow):
    """步骤4：数据分析与实证（如果需要真实数据）"""
    print("\n" + "="*60)
    print("📝 步骤4：数据分析与实证")
    print("="*60)

    print("""
⚠️ 重要提示：
本步骤需要调用真实数据分析模块，生成真实的数据结果。
这将替换论文中的模拟数据为真实回归结果。

可用的数据模块：
1. econometrics.py - 计量经济学回归分析
2. data_pipeline.py - 数据清洗与预处理
3. empirical_agent.py - 实证研究智能体
""")

    choice = ask_user("是否生成真实实证结果？",
                     ["是，生成真实数据", "否，使用现有草稿继续"])

    if choice == "是，生成真实数据":
        print("""
📊 数据分析模块说明：
1. 需要提供原始数据文件（CSV/Excel）
2. 定义被解释变量、核心解释变量、控制变量
3. 自动进行描述性统计、相关性分析、回归分析
4. 生成可直接引用的回归表格
""")

        # 提示用户数据文件位置
        data_path = input("请输入数据文件路径（直接回车跳过）: ").strip()

        if data_path and Path(data_path).exists():
            print(f"📁 数据文件已找到: {data_path}")
            _run_empirical_analysis(workflow, data_path)
        else:
            # 询问是否需要变量配置来生成模拟数据表格
            choice2 = ask_user("未找到数据文件，如何处理？",
                             ["配置变量后生成模拟结果", "跳过数据分析"])

            if choice2 == "配置变量后生成模拟结果":
                _run_empirical_analysis_with_config(workflow)
            else:
                print("⚠️ 跳过数据生成，将保留论文中的占位符")
                print("""
📋 后续操作指南：
1. 准备数据文件后，运行：
   python scripts/empirical_agent.py --data <您的数据文件>
   
2. 或使用 econometrics 模块直接分析：
   python scripts/econometrics.py --input <数据文件> --dep <被解释变量> --ind <解释变量>
   
3. 推荐数据来源：
   - 东方财富 Choice金融终端
   - CSMAR 国泰安数据库
   - Wind 万得数据库
""")
    else:
        print("""
📋 数据分析可稍后单独运行：
1. python scripts/empirical_agent.py
2. python scripts/econometrics.py
""")

    return workflow


def _run_empirical_analysis(workflow: PaperWorkflow, data_path: str):
    """运行实证分析（基于真实数据文件）"""
    print("\n" + "─"*40)
    print("🔬 启动实证分析模块")
    print("─"*40)

    try:
        # 动态导入数据分析模块
        from scripts.data_pipeline import load_data, preprocess_data
        from scripts.econometrics import run_regression

        # 加载数据
        print(f"📂 加载数据: {data_path}")
        df = load_data(data_path)
        print(f"✅ 数据加载成功，共 {len(df)} 行，{len(df.columns)} 列")

        # 数据预处理
        print("⚙️  数据预处理中...")
        df_clean = preprocess_data(df)
        print(f"✅ 预处理完成，有效样本 {len(df_clean)} 行")

        # 变量配置
        print("""
📊 变量配置：
请配置您的回归模型（直接回车使用默认值）
""")

        dep_var = input("被解释变量 (默认: y): ").strip() or "y"
        indep_vars = input("核心解释变量（逗号分隔，默认: x1,x2）: ").strip() or "x1,x2"
        control_vars = input("控制变量（逗号分隔，可跳过）: ").strip()

        print("\n📐 模型设定:")
        print(f"   被解释变量: {dep_var}")
        print(f"   核心解释变量: {indep_vars}")
        print(f"   控制变量: {control_vars or '无'}")

        # 运行回归
        confirm = ask_user("确认运行回归分析？", ["确认", "取消"])
        if confirm == "确认":
            print("\n⏳ 正在运行回归分析...")

            # 构建变量列表
            all_vars = [dep_var] + indep_vars.split(",") + (control_vars.split(",") if control_vars else [])

            # 调用回归模块
            result = run_regression(df_clean, dep_var, indep_vars.split(","),
                                  control_vars.split(",") if control_vars else [])

            if result:
                print("✅ 回归分析完成！")
                print("\n📊 回归结果预览:")
                print(result.get("summary", ""))

                # 保存结果
                result_file = workflow.project_dir / "回归结果.md"
                result_file.write_text(result.get("full_output", ""), encoding="utf-8")
                print(f"📁 结果已保存: {result_file}")
            else:
                print("⚠️ 回归分析未返回结果，请检查变量配置")

    except ImportError as e:
        print(f"⚠️ 数据分析模块导入失败: {e}")
        print("   请确保已安装所需依赖: pandas, statsmodels, scipy")
        print("   运行: pip install pandas statsmodels scipy")
    except Exception as e:
        print(f"⚠️ 数据分析执行出错: {e}")
        import traceback
        traceback.print_exc()


def _run_empirical_analysis_with_config(workflow: PaperWorkflow):
    """使用变量配置生成模拟实证结果（用于演示）"""
    print("\n" + "─"*40)
    print("🔬 配置实证模型（模拟数据）")
    print("─"*40)

    print("""
📋 请配置您的实证模型（用于生成符合学术规范的模拟结果）
此功能可帮助您预览论文中实证部分的格式和结构
""")

    dep_var = input("被解释变量 (如: roa, tobinq): ").strip()
    indep_vars = input("核心解释变量（逗号分隔，如: did, size）: ").strip()
    control_vars = input("控制变量（逗号分隔，可跳过）: ").strip()

    if not dep_var or not indep_vars:
        print("⚠️ 被解释变量和核心解释变量不能为空")
        return

    print(f"""
📐 模型配置完成：
   被解释变量: {dep_var}
   核心解释变量: {indep_vars}
   控制变量: {control_vars or '无'}
   
⏳ 正在生成模拟回归结果...
""")

    try:
        # 尝试生成模拟回归表格
        # FIX (2026-05-29): generate_mock_regression_table 不存在于任何模块，
        # 直接生成格式参考用的 Markdown 回归表格（模拟数据，仅供格式参考）
        dep_list = [dep_var] + [v.strip() for v in indep_vars.split(",")]
        ctrl_list = [v.strip() for v in (control_vars.split(",") if control_vars else [])]
        all_vars = dep_list + ctrl_list

        table_md = "| 变量 | (1) 系数 | (2) 标准误 | (3) 系数 | (4) 标准误 |\n"
        table_md += "|:------|:------:|:------:|:------:|:------:|\n"
        for v in all_vars:
            table_md += f"| {v} | 0.000 | (0.000) | 0.000 | (0.000) |\n"
        table_md += "| N | 1,500 | | 1,500 | |\n"
        table_md += "| R² | 0.000 | | 0.000 | |\n"
        table_md += "| 控制变量 | 否 | | 是 | |\n"
        table_md += "\n*注：以上为格式参考占位数据，实际结果请准备真实数据后运行 `python scripts/empirical_agent.py`*\n"
        result = table_md

        if result:
            print("✅ 模拟回归表格生成成功！")
            print(result)

            # 保存结果
            result_file = workflow.project_dir / f"回归结果_{dep_var}.md"
            result_file.write_text(result, encoding="utf-8")
            print(f"📁 结果已保存: {result_file}")

            print("""
⚠️ 注意：以上为模拟数据结果，仅供格式参考。
请准备真实数据后，运行 python scripts/empirical_agent.py 获取实际结果。
""")
        else:
            print("⚠️ 无法生成模拟结果，请检查 econometrics_extended 模块")

    except Exception as e:
        print(f"⚠️ 生成模拟结果时出错: {e}")
        import traceback
        traceback.print_exc()


def step5_finalize(workflow: PaperWorkflow):
    """步骤5：整合与输出"""
    print("\n" + "="*60)
    print("📝 步骤5：整合论文")
    print("="*60)

    # 整合论文
    full_paper = workflow.generate_full_paper()

    print("\n✅ 论文已整合完成！")
    print(f"📁 输出位置: {workflow.project_dir / '全文草稿.md'}")

    # 统计字数
    chinese_chars = sum(1 for c in full_paper if '\u4e00' <= c <= '\u9fff')
    print(f"📊 中文字数: {chinese_chars}")

    return full_paper


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """主函数：运行完整工作流"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║           📝 交互式论文写作工作流 v2.0                               ║
║                                                                      ║
║           核心原则：                                                  ║
║           1. 先出大纲，用户确认后再逐步生成                          ║
║           2. 所有数据必须真实，禁止编造                               ║
║           3. 每个章节完成后询问用户意见                               ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    # 创建工作流实例
    workflow = PaperWorkflow()

    try:
        # 步骤1：确定主题
        step1_topic_selection(workflow)

        if not confirm_proceed("确认进入下一步？"):
            return

        # 步骤2：生成大纲
        step2_outline_generation(workflow)

        if not confirm_proceed("大纲确认后进入写作？"):
            return

        # 步骤3：逐章节写作
        step3_chapter_writing(workflow)

        # 步骤4：数据分析（可选）
        step4_data_analysis(workflow)

        # 步骤5：整合输出
        full_paper = step5_finalize(workflow)

        print("\n" + "="*60)
        print("🎉 论文写作工作流完成！")
        print("="*60)
        print(f"""
下一步建议：
1. 查看完整论文: {workflow.project_dir / '全文草稿.md'}
2. 如需数据分析，请运行: python scripts/econometrics.py
3. 如需导出Word，请运行: python scripts/generate_docx_tables.py
        """)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，工作流已保存当前进度")
        if workflow.project_dir:
            print(f"📁 草稿位置: {workflow.project_dir}")
    except Exception as e:
        print(f"\n❌ 工作流出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env.local", override=False)

    main()
