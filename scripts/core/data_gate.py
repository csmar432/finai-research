"""DataGate — 真实数据前移到写作阶段之前（PR2, Audit 2026-06-27).

解决问题 #8：真实数据应该在数据获取阶段完成，而不是写完再替换。

核心约束：
  1. 论文写作（阶段 6）必须验证数据完成
  2. 禁止在数据未完成时生成包含数字的正文
  3. 阶段 5 的数据必须包含 provenance_id（由 provenance.py 注入）

使用：
  from scripts.core.data_gate import DataGate, DataGateResult

  gate = DataGate(session_dir="output/.clarify_session")
  result = gate.check()          # 检查数据是否完成
  if not result.is_ready:
      print(result.block_message)  # 打印阻止原因
      gate.prompt_user()          # CLI: 询问用户如何处理
      return  # 不继续

  # 数据就绪 → 进入写作阶段
"""

from __future__ import annotations

__all__ = [
    "DataGate",
    "DataGateResult",
    "DataGateLevel",
    "RealDataError",
]

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Data Gate Level ────────────────────────────────────────────────────────────


class DataGateLevel(Enum):
    """数据验证的严格程度。"""
    NONE = "none"                # 不验证（跳过）
    CHECKPOINT_ONLY = "checkpoint"  # 仅检查 checkpoint 文件存在
    PROVENANCE = "provenance"   # 检查 provenance_id（推荐）
    FULL = "full"               # 全量验证（额外运行数据健康检查）


@dataclass
class DataGateResult:
    """DataGate 检查结果。"""
    is_ready: bool                    # 数据是否就绪
    level: DataGateLevel
    gate_file: Path | None           # 哪个 gate 文件存在
    missing: list[str] = field(default_factory=list)  # 缺失项
    warnings: list[str] = field(default_factory=list)  # 警告
    blocked_at: str = ""             # 阻止时间
    provenance_ids: list[str] = field(default_factory=list)
    data_files: list[Path] = field(default_factory=list)
    mock_ratio: float = 0.0          # 模拟数据比例（0.0 = 无 mock）

    @property
    def block_message(self) -> str:
        if self.is_ready:
            return ""
        lines = ["\n🔴 数据未完成 — 禁止进入写作阶段\n"]
        if self.missing:
            lines.append("  缺失项：")
            for m in self.missing:
                lines.append(f"    • {m}")
        if self.warnings:
            lines.append("\n  警告：")
            for w in self.warnings:
                lines.append(f"    ⚠️  {w}")
        if self.mock_ratio > 0:
            lines.append(f"\n  🚨 警告：{self.mock_ratio*100:.0f}% 为模拟数据！")
        lines.append("\n  解决方案：")
        lines.append("    ① 补充缺失数据：python scripts/research_framework/data_fetcher.py")
        lines.append("    ② 授权使用模拟数据（仅演示）：添加 --allow-synthetic")
        lines.append("    ③ 更换数据来源：修改 REFINED_DESIGN.md 中的数据源配置")
        return "\n".join(lines)


class RealDataError(Exception):
    """数据未就绪时尝试进入写作阶段抛出。"""
    pass


# ─── Data Gate ─────────────────────────────────────────────────────────────────


class DataGate:
    """数据验证门控。

    在论文写作阶段前强制验证真实数据已完成。

    工作流程：
      1. 检查 session_dir/.clarify_session/session_state.json 存在（澄清流程完成标志）
      2. 检查 session_dir/redundant_variables.json 存在（变量清单）
      3. 检查 session_dir/data_manifest.json 存在（数据获取清单）
      4. 检查 session_dir/data/ 目录有真实数据文件（非 mock）
      5. 可选：检查 provenance_id（由 provenance.py 注入）

    产物：
      - gate.json：记录检查结果
      - blocked.json：当 is_ready=False 时，写入阻止信息
    """

    # 数据就绪必须满足的最小文件
    REQUIRED_GATE_FILES = [
        "session_state.json",         # 澄清会话完成
        "redundant_variables.json",   # 变量冗余清单
    ]

    # 可选文件（缺失时发警告但不阻止）
    OPTIONAL_GATE_FILES = [
        "data_manifest.json",         # 数据获取清单
        "data/final_panel.csv",       # 最终面板数据
        "data_manifest.md",           # 数据说明文档
    ]

    def __init__(
        self,
        session_dir: Path | str | None = None,
        level: DataGateLevel = DataGateLevel.PROVENANCE,
    ):
        self.session_dir = Path(session_dir) if session_dir else Path("output/.clarify_session")
        self.level = level
        self.gate_file = self.session_dir / "gate.json"
        self.blocked_file = self.session_dir / "blocked.json"

    def check(self) -> DataGateResult:
        """执行检查，返回结果。"""
        missing: list[str] = []
        warnings: list[str] = []
        data_files: list[Path] = []
        provenance_ids: list[str] = []
        mock_ratio = 0.0

        # 1. 澄清会话完成
        if not (self.session_dir / "session_state.json").exists():
            missing.append("澄清会话未完成（session_state.json 不存在）")

        # 2. 变量冗余清单
        var_file = self.session_dir / "redundant_variables.json"
        if not var_file.exists():
            missing.append("变量冗余清单未生成（redundant_variables.json 不存在）")
        else:
            try:
                var_data = json.loads(var_file.read_text())
                if not var_data.get("has_minimum_redundancy"):
                    warnings.append("变量冗余不足（部分类别未达到最小阈值）")
            except Exception:
                warnings.append("redundant_variables.json 格式错误")

        # 3. 数据获取清单（可选）
        manifest_file = self.session_dir / "data_manifest.json"
        if not manifest_file.exists():
            warnings.append("数据获取清单不存在（data_manifest.json），建议先运行数据获取")
        else:
            try:
                manifest = json.loads(manifest_file.read_text())
                if manifest.get("requires_synthetic_data"):
                    warnings.append("数据清单要求使用模拟数据，请在获取真实数据后重新检查")
            except Exception:
                warnings.append("data_manifest.json 格式错误")

        # 4. 数据文件存在性检查
        data_dir = self.session_dir / "data"
        if data_dir.exists():
            csv_files = list(data_dir.glob("*.csv")) + list(data_dir.glob("*.parquet"))
            data_files.extend(csv_files)
            if not csv_files:
                warnings.append("数据目录存在但无 CSV/Parquet 文件")
            else:
                # 检查是否含 mock
                for f in csv_files:
                    if "_mock" in f.name.lower() or "_sim" in f.name.lower():
                        warnings.append(f"数据文件 {f.name} 包含 mock 标记")
                        mock_ratio = 0.5  # 保守估计
        else:
            warnings.append("数据目录不存在（请先运行数据获取）")

        # 5. Provenance 检查（严格模式）
        if self.level in (DataGateLevel.PROVENANCE, DataGateLevel.FULL):
            prov_file = self.session_dir / "provenance_ids.json"
            if prov_file.exists():
                try:
                    prov_data = json.loads(prov_file.read_text())
                    provenance_ids = prov_data.get("ids", [])
                except Exception:
                    warnings.append("provenance_ids.json 格式错误")
            else:
                if data_files:
                    warnings.append("缺少 provenance_ids.json（建议在数据获取后生成）")

        is_ready = len(missing) == 0
        # mock 数据比例 > 0 → 数据不安全，禁止进入写作
        if mock_ratio > 0:
            is_ready = False
            warnings.insert(0, f"检测到 {mock_ratio*100:.0f}% 模拟数据，数据未就绪")
        # FULL 模式下变量冗余不足 → 未就绪
        if self.level == DataGateLevel.FULL:
            var_file = self.session_dir / "redundant_variables.json"
            if var_file.exists():
                try:
                    var_data = json.loads(var_file.read_text())
                    if not var_data.get("has_minimum_redundancy"):
                        is_ready = False
                        warnings.insert(0, "变量冗余不足（FULL 模式要求所有类别达标）")
                except Exception:
                    pass

        result = DataGateResult(
            is_ready=is_ready,
            level=self.level,
            gate_file=self.gate_file,
            missing=missing,
            warnings=warnings,
            blocked_at=time.strftime("%Y-%m-%d %H:%M:%S") if not is_ready else "",
            provenance_ids=provenance_ids,
            data_files=data_files,
            mock_ratio=mock_ratio,
        )

        self._save_gate_result(result)
        return result

    def enforce(self) -> DataGateResult:
        """enforce = check + raise（若未就绪则抛异常）。"""
        result = self.check()
        if not result.is_ready:
            raise RealDataError(result.block_message)
        return result

    def prompt_user(self) -> DataGateResult:
        """CLI 模式：打印阻止信息，询问用户选择。"""
        result = self.check()
        if result.is_ready:
            print("\n✅ 数据验证通过，可以进入写作阶段。")
            return result

        print(result.block_message)
        print("\n" + "─" * 60)
        try:
            choice = input("选择处理方式 [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return result

        if choice == "1":
            print("\n  💡 请运行数据获取：")
            print(f"    python scripts/research_framework/data_fetcher.py")
            print(f"    python scripts/start_research.py --resume --session-dir {self.session_dir}")
        elif choice == "2":
            print("\n  ⚠️  你选择了使用模拟数据继续（仅用于演示）")
            print("  ⚠️  生成的论文将包含模拟数字，不能用于发表")
        elif choice == "3":
            print("\n  退出，当前会话保留在磁盘（可 resume）")
        return result

    def _save_gate_result(self, result: DataGateResult) -> None:
        """保存检查结果。"""
        self.gate_file.write_text(json.dumps({
            "is_ready": result.is_ready,
            "level": result.level.value,
            "missing": result.missing,
            "warnings": result.warnings,
            "blocked_at": result.blocked_at,
            "provenance_ids": result.provenance_ids,
            "data_files": [str(f) for f in result.data_files],
            "mock_ratio": result.mock_ratio,
            "checked_at": time.time(),
        }, ensure_ascii=False, indent=2))

        if not result.is_ready:
            self.blocked_file.write_text(json.dumps({
                "blocked": True,
                "message": result.block_message,
                "missing": result.missing,
                "warnings": result.warnings,
                "blocked_at": result.blocked_at,
            }, ensure_ascii=False, indent=2))

    # ─── Integration with agent_pipeline ─────────────────────────────────────

    @staticmethod
    def is_pipeline_blocked(session_dir: Path | str | None = None) -> bool:
        """检查流水线是否被数据门控阻止（用于 agent_pipeline.py）。"""
        gate = DataGate(session_dir=session_dir)
        blocked_file = gate.session_dir / "blocked.json"
        return blocked_file.exists()


# ─── CLI Entry ───────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="数据验证门控")
    parser.add_argument("--session-dir", default="output/.clarify_session", help="会话目录")
    parser.add_argument("--level", default="provenance",
                       choices=["none", "checkpoint", "provenance", "full"],
                       help="验证严格程度")
    parser.add_argument("--enforce", action="store_true", help="未就绪时抛出异常")
    args = parser.parse_args()

    level = DataGateLevel(args.level)
    gate = DataGate(session_dir=args.session_dir, level=level)

    print(f"\n🔍 数据验证门控 | level={level.value}")
    print(f"   会话目录: {gate.session_dir}")

    result = gate.check()
    print(f"\n   就绪状态: {'✅ ' + '就绪' if result.is_ready else '🔴 未就绪'}")
    if result.missing:
        print(f"   缺失项: {result.missing}")
    if result.warnings:
        print(f"   警告: {result.warnings}")
    if result.mock_ratio > 0:
        print(f"   ⚠️  模拟数据比例: {result.mock_ratio*100:.0f}%")

    if args.enforce and not result.is_ready:
        raise SystemExit(1)
    raise SystemExit(0 if result.is_ready else 1)


if __name__ == "__main__":
    main()