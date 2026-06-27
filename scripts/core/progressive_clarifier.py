"""Progressive Theme Clarifier (audit-fix-2026-06-27, rename from NORA-style).

5 轮渐进式主题澄清器：把"输入主题 → 直接跑"改造为
"主题 → 5 轮逐步澄清 → 锁定研究画像 → 进入流水线"。

解决问题：
  #1 主题确认不够细致，没有逐步机制
  #2 出大纲后应该及时和用户同步
  #10 生成文章悄悄用合成数据，没征询意见（每轮产物落盘，必须 ack）

历史说明（2026-06-27 命名修正）：
  本模块最初参考 night_owl_research_agent (NORA) 的 5 轮交互式主题澄清
  模式，但所有代码均独立实现。为避免与 NORA 项目的命名混淆，已将原
  `NoraOrchestrator` / `NoraState` / `NoraStage` 等标识符重命名为功能性
  名称：`ProgressiveClarifier` / `ClarificationState` / `ClarificationStage`。

使用：
  CLI 模式（阻塞 input）：
    python scripts/core/progressive_clarifier.py --topic "碳排放权交易对绿色创新的影响"
  编程模式（AI agent 上下文）：
    from scripts.core.progressive_clarifier import ProgressiveClarifier
    clarifier = ProgressiveClarifier(auto_ack=False)
    state = clarifier.start(topic="...")
    while not state.is_complete:
        question, options = clarifier.next_question(state)
        # 把 question 展示给用户；收到回复后：
        clarifier.submit_answer(state, answer)
        state = clarifier.advance(state)
"""

from __future__ import annotations

__all__ = [
    "ClarificationState",
    "ClarificationStage",
    "ResearchProfile",
    "ProgressiveClarifier",
    "VariableCandidate",
]

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Stage Definitions ────────────────────────────────────────────────────────


class ClarificationStage(Enum):
    """5 轮澄清的固定阶段。"""
    INTAKE = "intake"                  # 接收原始主题
    QUESTION_TYPE = "question_type"    # 实证 / 综述 / 理论
    IDENTIFICATION = "identification"  # 识别策略（DID/IV/RDD/PSM/其他）
    SAMPLE = "sample"                  # 样本窗口、地理范围、行业
    VARIABLES = "variables"            # 因变量、自变量、控制变量（含冗余候选）
    VENUE = "venue"                    # 目标期刊


# 5 轮问题的固定 prompt 模板（每轮只问一件事）
_STAGE_QUESTIONS: dict[ClarificationStage, str] = {
    ClarificationStage.QUESTION_TYPE: "这份研究主要是哪一种？\n  1) 实证研究（用数据检验因果/相关）\n  2) 文献综述（系统性梳理文献）\n  3) 理论研究（理论模型/数学推导）",
    ClarificationStage.IDENTIFICATION: "你倾向用什么识别策略？\n  1) 双重差分 DID（含 PSM-DID / 现代 DID）\n  2) 工具变量 IV / 2SLS\n  3) 断点回归 RDD\n  4) 倾向得分匹配 PSM\n  5) 面板 GMM / 固定效应\n  6) 局部投影 LP / 事件研究\n  7) 综合运用多种方法（推荐：DID 为主 + 多种稳健性）",
    ClarificationStage.SAMPLE: "样本窗口和范围是什么？\n  例如：\n   - 2010-2022 中国 A 股上市公司\n   - 2015-2020 美国 S&P 500\n   - 2008-2019 中国省级面板\n  （请给出起止年份 + 国家/地区 + 数据粒度：公司/省级/国家级/家庭）",
    ClarificationStage.VARIABLES: "你已经定义好的变量是什么？（如未确定，可以只填因变量，其他留空，我会在文献检索后给候选）\n  - 因变量 Y：\n  - 核心解释变量 X：\n  - 政策/事件虚拟变量：\n  - 至少 3 个控制变量：\n  （说明：文献综述阶段会自动补充更多候选变量，确保稳健性检验时可替换）",
    ClarificationStage.VENUE: "目标期刊/投稿方向是？\n  1) 中文顶刊：经济研究 / 金融研究 / 管理世界 / 会计研究\n  2) 英文 SSCI：JF / JFE / RFS / JAE / JPE\n  3) 一般 SSCI： Emerging Markets Review / China Economic Review\n  4) 暂无偏好（我会按数据可行性推荐）",
}


_STAGE_TO_ACK_FILE = {
    ClarificationStage.QUESTION_TYPE: "01_question_type.json",
    ClarificationStage.IDENTIFICATION: "02_identification.json",
    ClarificationStage.SAMPLE: "03_sample.json",
    ClarificationStage.VARIABLES: "04_variables.json",
    ClarificationStage.VENUE: "05_venue.json",
}


# ─── Variable Candidate (for redundancy resolution) ──────────────────────────


@dataclass
class VariableCandidate:
    """单个变量的多个备选测度，用于解决数据冗余问题。"""
    name: str                       # 人类可读名，如 "TFP_OP"
    formula: str                    # 公式描述，如 "OP method (Olley-Pakes 1996)"
    data_source_hint: str           # 数据源提示，如 "Tushare income/asset/employee"
    priority: int = 1               # 1=首选，2=备选1，3=备选2


@dataclass
class VariableSet:
    """一组变量定义，每个变量含多个测度候选。"""
    dependent: list[VariableCandidate] = field(default_factory=list)
    independent: list[VariableCandidate] = field(default_factory=list)
    control: list[VariableCandidate] = field(default_factory=list)
    policy_event: list[VariableCandidate] = field(default_factory=list)


# ─── Research Profile (final output) ─────────────────────────────────────────


@dataclass
class ResearchProfile:
    """5 轮澄清完成后产出的研究画像。"""
    topic: str
    question_type: str = ""             # "empirical" | "review" | "theoretical"
    identification: str = ""            # "DID" | "IV" | "RDD" | "PSM" | "FE" | "LP" | "multi"
    sample_window: str = ""             # "2010-2022"
    geography: str = ""                 # "China A-share"
    unit: str = ""                      # "firm" | "province" | "country" | "household"
    venue: str = ""                     # "经济研究"
    variables: VariableSet = field(default_factory=VariableSet)
    raw_answers: dict[str, str] = field(default_factory=dict)
    locked_at: float = 0.0


# ─── State Machine ────────────────────────────────────────────────────────────


@dataclass
class ClarificationState:
    """澄清流程的当前状态。"""
    topic: str
    current_stage: ClarificationStage = ClarificationStage.QUESTION_TYPE
    answers: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    profile: ResearchProfile | None = None
    started_at: float = field(default_factory=time.time)
    output_dir: Path | None = None
    needs_user_input: bool = True

    @property
    def is_complete(self) -> bool:
        return self.profile is not None

    @property
    def progress_pct(self) -> float:
        stages = list(ClarificationStage)
        # INTAKE 不是问题阶段，所以从 QUESTION_TYPE 开始计数
        question_stages = [s for s in stages if s != ClarificationStage.INTAKE]
        answered = sum(1 for s in question_stages if s.value in self.answers)
        return round(100.0 * answered / len(question_stages), 1)


# ─── Clarifier ────────────────────────────────────────────────────────────────


class ProgressiveClarifier:
    """5 轮渐进式主题澄清器。

    设计要点：
      1. 5 轮逐步澄清（不一次性接收所有信息）
      2. 每轮产物落盘到 output_dir/.clarify_session/XX_*.json
      3. 强制 ack：不调用 submit_answer()，禁止 advance()
      4. 同步：每轮问完，CLI 调用 input()；AI agent 模式下返回 InteractionResult
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        auto_ack: bool = False,
        cli_mode: bool = True,
    ):
        """初始化。

        Args:
            output_dir: 产物落盘目录，默认 output/.clarify_session/
            auto_ack: 仅用于测试；生产必须 False（强制用户确认）
            cli_mode: True 阻塞 input；False 返回 InteractionResult
        """
        self.output_dir = Path(output_dir) if output_dir else Path("output/.clarify_session")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.auto_ack = auto_ack
        self.cli_mode = cli_mode
        logger.info("ProgressiveClarifier initialized: output_dir=%s cli_mode=%s",
                    self.output_dir, cli_mode)

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def start(self, topic: str) -> ClarificationState:
        """接收主题，启动澄清流程。"""
        if not topic or not topic.strip():
            raise ValueError("Topic must be a non-empty string")

        state = ClarificationState(
            topic=topic.strip(),
            output_dir=self.output_dir,
            current_stage=ClarificationStage.QUESTION_TYPE,
        )
        self._save_state(state)
        logger.info("Clarification session started: topic=%r, session_dir=%s", topic, self.output_dir)
        return state

    def next_question(self, state: ClarificationState) -> tuple[str, list[str]]:
        """返回当前阶段的问题（CLI/AI agent 共用）。"""
        if state.is_complete:
            return ("研究画像已锁定，进入下一阶段（文献综述）。", [])

        question = _STAGE_QUESTIONS[state.current_stage]
        options = self._extract_options(question)
        return (question, options)

    def submit_answer(self, state: ClarificationState, answer: str) -> None:
        """提交当前阶段的答案。

        Args:
            state: 当前状态
            answer: 用户答案（CLI 模式为 input() 返回；AI agent 模式为对话文本）

        Raises:
            RuntimeError: 当 auto_ack=False 且 answer 为空（防止悄悄 fallback）
        """
        if state.is_complete:
            raise RuntimeError("Session is already complete")

        if not self.auto_ack and not answer.strip():
            raise RuntimeError(
                f"Stage {state.current_stage.value}: empty answer not allowed. "
                "User must explicitly provide input (no silent fallback)."
            )

        # 记录答案
        state.answers[state.current_stage.value] = answer.strip()
        state.history.append({
            "stage": state.current_stage.value,
            "question": _STAGE_QUESTIONS[state.current_stage],
            "answer": answer.strip(),
            "ts": time.time(),
        })
        self._save_state(state)
        logger.info("Stage %s answered", state.current_stage.value)

    def advance(self, state: ClarificationState) -> ClarificationState:
        """推进到下一阶段；若已到最后阶段，锁定研究画像。"""
        if state.is_complete:
            return state

        # 顺序：QUESTION_TYPE → IDENTIFICATION → SAMPLE → VARIABLES → VENUE → 锁定
        order = [
            ClarificationStage.QUESTION_TYPE,
            ClarificationStage.IDENTIFICATION,
            ClarificationStage.SAMPLE,
            ClarificationStage.VARIABLES,
            ClarificationStage.VENUE,
        ]
        try:
            idx = order.index(state.current_stage)
            if idx + 1 < len(order):
                state.current_stage = order[idx + 1]
            else:
                state.profile = self._build_profile(state)
                state.needs_user_input = False
        except ValueError:
            pass

        self._save_state(state)
        return state

    def rollback(self, state: ClarificationState, target_stage: ClarificationStage) -> ClarificationState:
        """回退到指定阶段（用户要求修改答案时使用）。"""
        if state.is_complete:
            state.profile = None
            state.needs_user_input = True

        state.current_stage = target_stage
        # 清除之后阶段的答案
        order = [
            ClarificationStage.QUESTION_TYPE,
            ClarificationStage.IDENTIFICATION,
            ClarificationStage.SAMPLE,
            ClarificationStage.VARIABLES,
            ClarificationStage.VENUE,
        ]
        try:
            idx = order.index(target_stage)
            for later_stage in order[idx + 1:]:
                state.answers.pop(later_stage.value, None)
        except ValueError:
            pass

        self._save_state(state)
        logger.info("Rolled back to stage %s", target_stage.value)
        return state

    # ─── Interactive Run ───────────────────────────────────────────────────

    def run_interactive(self, topic: str) -> ResearchProfile:
        """CLI 阻塞模式：自动 5 轮 input() 直到画像锁定。

        Returns:
            ResearchProfile: 锁定后的研究画像

        Raises:
            KeyboardInterrupt: 用户 Ctrl+C 中断（不会悄悄生成 mock）
        """
        if not self.cli_mode:
            raise RuntimeError("run_interactive requires cli_mode=True")

        state = self.start(topic)

        print("\n" + "═" * 70)
        print("  主题澄清（5 轮逐步引导）")
        print("═" * 70)
        print(f"\n  📌 研究主题: {topic}")
        print(f"  📂 会话目录: {self.output_dir}")
        print(f"  ⏱️  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n  说明：每轮问一个问题，必须回答后才能进入下一轮。")
        print("        随时可输入 'quit' 退出（不会生成任何 mock 数据）。\n")

        while not state.is_complete:
            question, _ = self.next_question(state)
            print("\n" + "─" * 70)
            print(f"  [{state.progress_pct}%] 第 {state.current_stage.value} 阶段")
            print("─" * 70)
            print(question)
            print()
            try:
                answer = input("  你的回答 › ")
            except (EOFError, KeyboardInterrupt):
                print("\n\n  ⚠️  会话中止（已保留部分答案到磁盘，可后续 resume）")
                self._save_state(state)
                raise

            if answer.strip().lower() in {"quit", "exit", "q"}:
                print("\n  ⚠️  会话中止（不会生成任何模拟数据）")
                self._save_state(state)
                raise KeyboardInterrupt("User quit")

            try:
                self.submit_answer(state, answer)
            except RuntimeError as e:
                print(f"  ❌ {e}")
                continue

            state = self.advance(state)

        # 画像锁定
        print("\n" + "═" * 70)
        print("  ✅ 研究画像已锁定")
        print("═" * 70)
        self._print_profile_summary(state.profile)

        return state.profile

    # ─── Persistence ───────────────────────────────────────────────────────

    def _save_state(self, state: ClarificationState) -> None:
        """落盘当前状态（含每阶段答案）。"""
        state_file = self.output_dir / "session_state.json"
        state_dict = {
            "topic": state.topic,
            "current_stage": state.current_stage.value,
            "answers": state.answers,
            "history": state.history,
            "progress_pct": state.progress_pct,
            "is_complete": state.is_complete,
            "started_at": state.started_at,
        }
        if state.profile:
            state_dict["profile"] = asdict(state.profile)
        state_file.write_text(json.dumps(state_dict, ensure_ascii=False, indent=2))

        # 每阶段单独落盘，方便外部审计
        for stage, fname in _STAGE_TO_ACK_FILE.items():
            if stage.value in state.answers:
                ack_file = self.output_dir / fname
                ack_file.write_text(json.dumps({
                    "stage": stage.value,
                    "question": _STAGE_QUESTIONS[stage],
                    "answer": state.answers[stage.value],
                    "ts": time.time(),
                }, ensure_ascii=False, indent=2))

    def resume(self, session_dir: Path) -> ClarificationState:
        """恢复已落盘的会话（支持断点续传）。"""
        state_file = Path(session_dir) / "session_state.json"
        if not state_file.exists():
            raise FileNotFoundError(f"No session at {state_file}")

        data = json.loads(state_file.read_text())
        state = ClarificationState(
            topic=data["topic"],
            output_dir=Path(session_dir),
            current_stage=ClarificationStage(data["current_stage"]),
            answers=data.get("answers", {}),
            history=data.get("history", []),
            started_at=data.get("started_at", time.time()),
        )
        if data.get("profile"):
            # 反序列化 VariableCandidate 列表
            prof_data = data["profile"]
            variables = prof_data.pop("variables", {})
            prof_data["variables"] = VariableSet(
                dependent=[VariableCandidate(**v) for v in variables.get("dependent", [])],
                independent=[VariableCandidate(**v) for v in variables.get("independent", [])],
                control=[VariableCandidate(**v) for v in variables.get("control", [])],
                policy_event=[VariableCandidate(**v) for v in variables.get("policy_event", [])],
            )
            state.profile = ResearchProfile(**prof_data)

        logger.info("Resumed session: topic=%r, progress=%s%%",
                    state.topic, state.progress_pct)
        return state

    # ─── Profile Building ──────────────────────────────────────────────────

    def _build_profile(self, state: ClarificationState) -> ResearchProfile:
        """从 5 轮答案构建研究画像。"""
        answers = state.answers

        # 解析样本窗口和地理范围
        sample_text = answers.get(ClarificationStage.SAMPLE.value, "")
        sample_window = self._extract_year_range(sample_text)
        geography = self._extract_geography(sample_text)
        unit = self._extract_unit(sample_text)

        profile = ResearchProfile(
            topic=state.topic,
            question_type=self._normalize_choice(answers.get(ClarificationStage.QUESTION_TYPE.value, ""), {
                "1": "empirical", "2": "review", "3": "theoretical",
                "实证": "empirical", "综述": "review", "理论": "theoretical",
            }, default="empirical"),
            identification=self._normalize_choice(answers.get(ClarificationStage.IDENTIFICATION.value, ""), {
                "1": "DID", "2": "IV", "3": "RDD", "4": "PSM", "5": "FE", "6": "LP", "7": "multi",
            }, default="multi"),
            sample_window=sample_window,
            geography=geography,
            unit=unit,
            venue=self._normalize_choice(answers.get(ClarificationStage.VENUE.value, ""), {
                "1": "经济研究", "2": "JF", "3": "SSCI", "4": "auto",
            }, default="auto"),
            variables=self._parse_variables(answers.get(ClarificationStage.VARIABLES.value, "")),
            raw_answers=answers,
            locked_at=time.time(),
        )
        return profile

    def _parse_variables(self, text: str) -> VariableSet:
        """从用户文本解析变量定义。

        简单启发式：按行匹配 "因变量 Y:" / "核心解释变量 X:" 等关键字。
        若用户没明确给出，会生成空集（VariableRedundancyResolver 会从
        文献综述自动补充候选）。
        """
        import re
        variables = VariableSet()
        if not text:
            return variables

        section_map = {
            "因变量": "dependent",
            "Y": "dependent",
            "核心解释变量": "independent",
            "X": "independent",
            "政策": "policy_event",
            "事件": "policy_event",
            "控制变量": "control",
        }
        current_field = None
        for line in text.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # 匹配 "因变量 Y：" 这样的标题
            matched = False
            for keyword, field_name in section_map.items():
                if keyword in line_stripped and ("：" in line_stripped or ":" in line_stripped):
                    current_field = field_name
                    # 同行的变量名（"因变量 Y：TFP" 或 "控制变量：Size, Lev, ROA"）
                    parts = line_stripped.split("：", 1) if "：" in line_stripped else line_stripped.split(":", 1)
                    if len(parts) > 1 and parts[1].strip():
                        # 同行内可能含逗号/顿号分隔
                        inline_vars = re.split(r"[,，、;；\s]+", parts[1].strip())
                        for var_name in inline_vars:
                            var_name = var_name.strip()
                            if not var_name:
                                continue
                            candidate = VariableCandidate(
                                name=var_name,
                                formula="user-defined",
                                data_source_hint="unknown",
                                priority=1,
                            )
                            getattr(variables, current_field).append(candidate)
                    matched = True
                    break
            if not matched and current_field:
                # 可能是控制变量列表的某一行（可能含逗号/顿号分隔）
                line_clean = line_stripped.lstrip("-•* ").strip()
                # 拆分 "Size, Lev, ROA" → ["Size", "Lev", "ROA"]
                # 同时拆分 "Size、Lev、ROA"（中文顿号）
                parts = re.split(r"[,，、;；\s]+", line_clean)
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    candidate = VariableCandidate(
                        name=part,
                        formula="user-defined",
                        data_source_hint="unknown",
                        priority=1,
                    )
                    getattr(variables, current_field).append(candidate)

        return variables

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _extract_options(self, question: str) -> list[str]:
        """从问题文本中提取选项（1), 2), ...）。"""
        options = []
        for line in question.splitlines():
            line = line.strip()
            if len(line) > 2 and line[0].isdigit() and line[1] in ").）":
                options.append(line)
        return options

    def _normalize_choice(self, text: str, mapping: dict[str, str], default: str) -> str:
        """从用户答案中提取归一化选项。"""
        text = text.strip()
        if not text:
            return default
        # 优先匹配数字前缀
        first_char = text[0]
        if first_char in mapping:
            return mapping[first_char]
        # 关键词匹配
        for key, val in mapping.items():
            if key in text:
                return val
        return default

    def _extract_year_range(self, text: str) -> str:
        """从样本描述提取年份范围。"""
        import re
        match = re.search(r"(\d{4})\s*[-—–]\s*(\d{4})", text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return ""

    def _extract_geography(self, text: str) -> str:
        """从样本描述提取地理范围。"""
        keywords = [
            ("S&P", "USA-S&P"),
            ("A 股", "China A-share"),
            ("A股", "China A-share"),
            ("上市公司", "China A-share"),
            ("省级", "China-province"),
            ("家庭", "China-household"),
            ("中国", "China"),
            ("美国", "USA"),
            ("日本", "Japan"),
        ]
        for kw, geo in keywords:
            if kw in text:
                return geo
        return ""

    def _extract_unit(self, text: str) -> str:
        """从样本描述提取数据粒度。"""
        if any(kw in text for kw in ["公司", "上市", "A 股", "S&P", "firm"]):
            return "firm"
        if any(kw in text for kw in ["省", "province"]):
            return "province"
        if any(kw in text for kw in ["国家", "country"]):
            return "country"
        if any(kw in text for kw in ["家庭", "household"]):
            return "household"
        return ""

    def _print_profile_summary(self, profile: ResearchProfile) -> None:
        """打印锁定后的画像摘要。"""
        print(f"\n  📌 主题: {profile.topic}")
        print(f"  🔬 研究类型: {profile.question_type}")
        print(f"  🧪 识别策略: {profile.identification}")
        print(f"  📅 样本窗口: {profile.sample_window or '(待定)'}")
        print(f"  🌏 地理范围: {profile.geography or '(待定)'}")
        print(f"  📊 数据粒度: {profile.unit or '(待定)'}")
        print(f"  🎯 目标期刊: {profile.venue}")
        print(f"  📈 因变量数: {len(profile.variables.dependent)}")
        print(f"  📊 自变量数: {len(profile.variables.independent)}")
        print(f"  🔧 控制变量数: {len(profile.variables.control)}")
        print(f"\n  ⏱️  锁定时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  📂 会话目录: {self.output_dir}")


# ─── CLI Entry ───────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="5 轮渐进式主题澄清器")
    parser.add_argument("--topic", required=True, help="研究主题")
    parser.add_argument("--output-dir", default=None, help="会话产物目录")
    parser.add_argument("--auto-ack", action="store_true", help="仅测试用，跳过用户确认")
    args = parser.parse_args()

    clarifier = ProgressiveClarifier(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        auto_ack=args.auto_ack,
        cli_mode=True,
    )
    profile = clarifier.run_interactive(args.topic)

    # 输出最终画像 JSON
    output = {
        "topic": profile.topic,
        "question_type": profile.question_type,
        "identification": profile.identification,
        "sample_window": profile.sample_window,
        "geography": profile.geography,
        "unit": profile.unit,
        "venue": profile.venue,
        "locked_at": profile.locked_at,
    }
    print("\n" + json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
