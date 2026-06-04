"""LaTeX 版本追踪 — latexdiff 对比 + diff PDF 生成.

功能：
  - 每次编译自动生成变更对比
  - 生成 diff.tex → 编译为 diff.pdf
  - 红色=删除内容  绿色=新增内容  黄色=位置变化
  - 版本历史管理（最多保留 N 个历史版本）

依赖：pip install latexdiff

Usage:
    tracker = LatexDiffTracker("papers/draft_v1/main.tex")
    tracker.save_version("v1.0")                    # 保存快照
    tracker.save_version("v1.1")                   # 再次保存
    tracker.generate_diff("v1.0", "v1.1")          # 生成 diff.tex
    tracker.compile_diff()                         # 编译 diff.pdf
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["LatexDiffTracker", "LatexVersionSnapshot"]

logger = logging.getLogger(__name__)


@dataclass
class LatexVersionSnapshot:
    """单次 LaTeX 版本快照。"""

    version: str
    path: str
    checksum: str          # SHA-256 of main.tex content
    timestamp: float
    stats: dict[str, int]  # word_count, line_count, section_count
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "path": self.path,
            "checksum": self.checksum,
            "timestamp": self.timestamp,
            "stats": self.stats,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LatexVersionSnapshot":
        return cls(**data)


class LatexDiffTracker:
    """
    LaTeX 版本追踪器 — 基于 latexdiff 的版本对比。

    工作流程：
      1. save_version("v1.0")   — 保存当前版本快照
      2. save_version("v1.1")   — 保存新版本
      3. generate_diff("v1.0", "v1.1")  — 生成 diff.tex
      4. compile_diff()        — 编译为 diff.pdf

    输出目录结构：
      {project_dir}/
        main_v1.0.tex        ← 快照副本
        main_v1.1.tex        ← 快照副本
        diff/
          diff_v1.0_v1.1.tex
          diff_v1.0_v1.1.pdf

    Usage
    -----
        tracker = LatexDiffTracker(
            project_dir="papers/draft_v1",
            main_file="main.tex",
        )
        tracker.save_version("v1.0")
        # ... 编辑 main.tex ...
        tracker.save_version("v1.1")
        tracker.generate_diff("v1.0", "v1.1")
        tracker.compile_diff("v1.0", "v1.1")
    """

    def __init__(
        self,
        project_dir: str | Path,
        main_file: str = "main.tex",
        max_versions: int = 10,
    ):
        self.project_dir = Path(project_dir)
        self.main_file = main_file
        self.max_versions = max_versions
        self._snapshots: list[LatexVersionSnapshot] = []
        self._index_path = self.project_dir / ".latex_version_index.json"
        self._diff_dir = self.project_dir / "diff"
        self._diff_dir.mkdir(exist_ok=True)
        self._load_index()

    # ── Main file path ───────────────────────────────────────────────────

    @property
    def main_tex_path(self) -> Path:
        return self.project_dir / self.main_file

    # ── Version Management ────────────────────────────────────────────────

    def _compute_checksum(self, path: Path) -> str:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]

    def _compute_stats(self, path: Path) -> dict[str, int]:
        """统计 LaTeX 文件基本信息。"""
        try:
            text = path.read_text(encoding="utf-8")
            return {
                "word_count": len(text.split()),
                "line_count": text.count("\n"),
                "char_count": len(text),
                "section_count": text.count(r"\section"),
                "subsection_count": text.count(r"\subsection"),
                "figure_count": text.count(r"\begin{figure}"),
                "table_count": text.count(r"\begin{table}"),
                "equation_count": text.count(r"\begin{equation}"),
                "ref_count": text.count(r"\ref{"),
                "cite_count": text.count(r"\cite"),
            }
        except Exception:
            return {}

    def save_version(self, version: str, metadata: dict | None = None) -> LatexVersionSnapshot:
        """
        保存当前 main.tex 的版本快照。

        Parameters
        ----------
        version : str
            版本标签，例如 "v1.0", "outline_final", "after_review1"。
        metadata : dict | None
            可选元数据（author / notes / stage 等）。

        Returns
        -------
        LatexVersionSnapshot
        """
        main = self.main_tex_path
        if not main.exists():
            raise FileNotFoundError(f"main.tex not found at {main}")

        checksum = self._compute_checksum(main)
        stats = self._compute_stats(main)
        ts = time.time()

        # 检查是否已有同名版本
        existing = [s for s in self._snapshots if s.version == version]
        if existing:
            # 更新
            snap = existing[0]
            snap.checksum = checksum
            snap.timestamp = ts
            snap.stats = stats
            snap.metadata = metadata or {}
            logger.info(f"[LatexDiffTracker] Updated version '{version}'")
        else:
            # 新建
            snap = LatexVersionSnapshot(
                version=version,
                path=str(main),
                checksum=checksum,
                timestamp=ts,
                stats=stats,
                metadata=metadata or {},
            )
            self._snapshots.append(snap)
            # 复制快照文件
            snapshot_path = self.project_dir / f"main_{version}.tex"
            shutil.copy2(main, snapshot_path)
            logger.info(f"[LatexDiffTracker] Saved version '{version}' → {snapshot_path}")

        # 裁剪旧版本
        self._prune_old_versions()
        self._save_index()
        return snap

    def list_versions(self) -> list[LatexVersionSnapshot]:
        """返回所有版本快照，按时间倒序。"""
        return sorted(self._snapshots, key=lambda s: s.timestamp, reverse=True)

    def get_version(self, version: str) -> LatexVersionSnapshot | None:
        for s in self._snapshots:
            if s.version == version:
                return s
        return None

    def get_latest_version(self) -> LatexVersionSnapshot | None:
        if not self._snapshots:
            return None
        return max(self._snapshots, key=lambda s: s.timestamp)

    def get_previous_version(self, version: str) -> LatexVersionSnapshot | None:
        """返回某版本的前一个版本。"""
        sorted_versions = sorted(self._snapshots, key=lambda s: s.timestamp)
        for i, s in enumerate(sorted_versions):
            if s.version == version and i > 0:
                return sorted_versions[i - 1]
        return None

    # ── Diff Generation ─────────────────────────────────────────────────

    def generate_diff(
        self,
        old_version: str,
        new_version: str,
        *,
        style: str = "changetrack",  # "context" | "word" | "changetrack" | "todo"
        output_name: str | None = None,
    ) -> Path | None:
        """
        使用 latexdiff 生成两个版本之间的差异。

        Parameters
        ----------
        old_version, new_version : str
            版本标签。
        style : str
            latexdiff 样式：
              - "changetrack": 追踪模式（红色删除/绿色新增）
              - "word": 词语级差异（更精细）
              - "context": 上下文差异
              - "todo": 待办注释模式
        output_name : str | None
            输出文件名，默认 "diff_{old}_{new}.tex"。

        Returns
        -------
        Path | None
            生成的 diff.tex 路径。
        """
        old_snap = self.get_version(old_version)
        new_snap = self.get_version(new_version)
        if not old_snap or not new_snap:
            logger.error(
                f"[LatexDiffTracker] Version not found: "
                f"'{old_version}' or '{new_version}'"
            )
            return None

        old_file = self.project_dir / f"main_{old_version}.tex"
        new_file = self.project_dir / f"main_{new_version}.tex"
        if not old_file.exists() or not new_file.exists():
            logger.error(f"[LatexDiffTracker] Snapshot files not found")
            return None

        output_name = output_name or f"diff_{old_version}_{new_version}.tex"
        diff_path = self._diff_dir / output_name

        cmd = [
            "latexdiff",
            str(old_file),
            str(new_file),
            "--type", style,
            "--preamble", " ACCEPTBLANKLINES=1",
            "-o", str(diff_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(
                    f"[LatexDiffTracker] latexdiff returned {result.returncode}: "
                    f"{result.stderr[:200]}"
                )
                return None

            logger.info(f"[LatexDiffTracker] Generated diff: {diff_path}")
            return diff_path

        except FileNotFoundError:
            logger.error(
                "[LatexDiffTracker] latexdiff not installed. "
                "Run: pip install latexdiff"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.error("[LatexDiffTracker] latexdiff timed out")
            return None

    def compile_diff(
        self,
        old_version: str,
        new_version: str,
        *,
        engine: str = "pdflatex",
        passes: int = 2,
    ) -> Path | None:
        """
        编译 diff.tex → diff.pdf。

        Parameters
        ----------
        old_version, new_version : str
            版本标签。
        engine : str
            LaTeX 引擎（pdflatex / xelatex / lualatex）。
        passes : int
            编译次数（2 = 标准编译，含目录/引用）。

        Returns
        -------
        Path | None
            生成的 diff.pdf 路径。
        """
        diff_tex = self._diff_dir / f"diff_{old_version}_{new_version}.tex"
        if not diff_tex.exists():
            # 尝试自动生成
            generated = self.generate_diff(old_version, new_version)
            if not generated:
                return None
            diff_tex = generated

        # 生成临时编译脚本
        log_path = self._diff_dir / f"diff_{old_version}_{new_version}.log"

        try:
            for pass_num in range(passes):
                compile_cmd = [
                    engine,
                    "-interaction=nonstopmode",
                    f"-output-directory={self._diff_dir}",
                    str(diff_tex),
                ]
                result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=self._diff_dir,
                )
                if result.returncode != 0:
                    logger.warning(
                        f"[LatexDiffTracker] {engine} pass {pass_num+1} failed: "
                        f"{result.stderr[-300:]}"
                    )
                    # 继续，不阻断

            pdf_path = diff_tex.with_suffix(".pdf")
            if pdf_path.exists():
                logger.info(f"[LatexDiffTracker] Compiled diff PDF: {pdf_path}")
                return pdf_path
            else:
                logger.error(f"[LatexDiffTracker] diff.pdf not generated")
                return None

        except FileNotFoundError:
            logger.error(
                f"[LatexDiffTracker] {engine} not found in PATH. "
                f"Install TeX Live or MacTeX."
            )
            return None
        except subprocess.TimeoutExpired:
            logger.error("[LatexDiffTracker] LaTeX compilation timed out")
            return None

    def diff_all_between(
        self,
        old_version: str,
        new_version: str,
    ) -> dict[str, Path | None]:
        """
        生成两个版本之间的完整 diff（tex + pdf）。

        Returns
        -------
        dict
            {"diff_tex": Path, "diff_pdf": Path}
        """
        tex_path = self.generate_diff(old_version, new_version)
        pdf_path = None
        if tex_path:
            pdf_path = self.compile_diff(old_version, new_version)
        return {"diff_tex": tex_path, "diff_pdf": pdf_path}

    def get_change_summary(
        self,
        old_version: str,
        new_version: str,
    ) -> dict[str, Any]:
        """
        返回两个版本之间的变更摘要。

        Returns
        -------
        dict
            含 stats 变化、checksum 差异、文件行数变化等。
        """
        old_snap = self.get_version(old_version)
        new_snap = self.get_version(new_version)
        if not old_snap or not new_snap:
            return {"error": "Version not found"}

        old_stats = old_snap.stats
        new_stats = new_snap.stats

        delta = {}
        for key in set(list(old_stats.keys()) + list(new_stats.keys())):
            old_val = old_stats.get(key, 0)
            new_val = new_stats.get(key, 0)
            delta[key] = new_val - old_val

        return {
            "old_version": old_version,
            "new_version": new_version,
            "checksum_changed": old_snap.checksum != new_snap.checksum,
            "time_elapsed_seconds": new_snap.timestamp - old_snap.timestamp,
            "stats_delta": delta,
            "old_stats": old_stats,
            "new_stats": new_stats,
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _prune_old_versions(self):
        """删除超过 max_versions 的旧版本。"""
        if len(self._snapshots) <= self.max_versions:
            return
        sorted_snaps = sorted(self._snapshots, key=lambda s: s.timestamp)
        to_remove = sorted_snaps[: len(self._snapshots) - self.max_versions]
        for snap in to_remove:
            snap_file = self.project_dir / f"main_{snap.version}.tex"
            if snap_file.exists():
                snap_file.unlink()
        self._snapshots = sorted_snaps[len(to_remove) :]

    def _save_index(self):
        data = {
            "snapshots": [s.to_dict() for s in self._snapshots],
            "max_versions": self.max_versions,
        }
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_index(self):
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._snapshots = [
                    LatexVersionSnapshot.from_dict(s) for s in data.get("snapshots", [])
                ]
            except Exception as exc:
                logger.warning(f"[LatexDiffTracker] Failed to load index: {exc}")
