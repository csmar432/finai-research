#!/usr/bin/env python3
"""
论文版本控制系统 (Paper Versioning System)
========================================
基于 Git 的论文版本控制，支持自动 commit 和 diff 对比。

核心功能：
1. 自动 Git commit：每次保存自动创建版本快照
2. 版本历史：查看论文的完整修改历史
3. Diff 对比：对比任意两个版本的差异
4. 标签管理：为重要版本添加标签（初稿、审稿、终稿等）
5. 分支支持：支持多分支管理（中文版/英文版等）

使用方法：
    from scripts.paper_versioning import PaperVersionControl, VersionInfo

    pvc = PaperVersionControl()
    version_id = pvc.save_version("paper.tex", message="修改引言部分")
    history = pvc.history("paper.tex")
    diff = pvc.diff("v1", "v2")
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═════════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═════════════════════════════════════════════════════════════════════════════════


@dataclass
class VersionInfo:
    """版本信息"""
    commit_hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str
    files_changed: list[str]
    insertions: int = 0
    deletions: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiffInfo:
    """Diff 信息"""
    old_version: str
    new_version: str
    files_changed: list[str]
    hunks: list[dict]  # [{file, old_lines, new_lines, diff_text}]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PaperProject:
    """论文项目（包含多个文件）"""
    project_id: str
    name: str
    root_dir: Path
    main_file: str  # 主文件（如 paper.tex）
    git_repo: Path
    created_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════════
# 论文版本控制系统
# ═════════════════════════════════════════════════════════════════════════════════


class PaperVersionControl:
    """
    论文版本控制系统。

    基于 Git 提供论文的版本管理功能。
    支持自动 commit、版本历史、diff 对比、标签管理。
    """

    # 预定义标签
    PREDEFINED_TAGS = {
        "draft": "初稿",
        "revision": "修改版",
        "review": "审稿版",
        "final": "终稿",
        "submitted": "已投稿",
        "accepted": "已接收",
    }

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self.git_dir = self.project_root / ".papers_git"
        self._ensure_git_repo()

    def _run_git(self, args: list, cwd: Path | None = None, capture_output: bool = True) -> subprocess.CompletedProcess:
        """运行 Git 命令"""
        working_dir = cwd or self.git_dir
        result = subprocess.run(
            ["git"] + args,
            cwd=working_dir,
            capture_output=capture_output,
            text=True,
            timeout=30,
        )
        return result

    def _ensure_git_repo(self):
        """确保 Git 仓库存在"""
        if not self.git_dir.exists():
            self.git_dir.mkdir(parents=True, exist_ok=True)
            self._run_git(["init"])
            self._run_git(["config", "user.email", "paper-workflow@local"])
            self._run_git(["config", "user.name", "Paper Workflow"])

    def _get_file_hash(self, filepath: Path) -> str:
        """计算文件内容的 MD5 哈希"""
        if filepath.exists():
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()[:8]
        return ""

    def _copy_to_git(self, source_path: Path, relative_path: str) -> bool:
        """复制文件到 Git 仓库"""
        dest_path = self.git_dir / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if source_path.is_file():
                shutil.copy2(source_path, dest_path)
                return True
            elif source_path.is_dir():
                shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                return True
        except Exception:
            return False
        return False

    def save_version(
        self,
        paper_path: str | Path,
        message: str,
        author: str = "Paper Workflow",
        auto_stage: bool = True,
    ) -> str:
        """
        保存论文版本（Git commit）。

        Args:
            paper_path: 论文文件路径
            message: 提交信息
            author: 作者名
            auto_stage: 是否自动暂存所有变更

        Returns:
            commit hash
        """
        paper_path = Path(paper_path)

        if not paper_path.exists():
            raise FileNotFoundError(f"论文文件不存在: {paper_path}")

        # 确定文件相对路径
        if paper_path.is_absolute():
            try:
                relative_path = paper_path.relative_to(self.project_root)
            except ValueError:
                relative_path = paper_path.name
        else:
            relative_path = paper_path

        # 复制文件到 Git 仓库
        self._copy_to_git(paper_path, relative_path)

        # Git 操作
        if auto_stage:
            self._run_git(["add", "."])

        # Commit
        timestamp = datetime.now().isoformat()
        full_message = f"{message}\n\nPaper Workflow Auto-commit | {timestamp}"

        self._run_git(["config", "user.name", author])
        result = self._run_git(["commit", "-m", full_message])

        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                return self._get_latest_commit()

        commit_hash = self._get_latest_commit()
        return commit_hash

    def _get_latest_commit(self) -> str:
        """获取最新的 commit hash"""
        result = self._run_git(["rev-parse", "HEAD"])
        return result.stdout.strip() if result.returncode == 0 else ""

    def get_version(self, commit_hash: str) -> VersionInfo | None:
        """获取指定版本的信息"""
        # 获取 commit 信息
        result = self._run_git(["show", "--quiet", "--format=%H%n%an%n%s%n%ai", commit_hash])

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if len(lines) < 4:
            return None

        commit_hash = lines[0]
        author = lines[1]
        message = lines[2]
        timestamp = lines[3]

        # 获取变更统计
        stat_result = self._run_git(["show", "--stat", "--format=", commit_hash])
        insertions = stat_result.stdout.count("+")
        deletions = stat_result.stdout.count("-")

        # 获取变更文件列表
        files_result = self._run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
        files = [f for f in files_result.stdout.strip().split("\n") if f]

        # 获取标签
        tags_result = self._run_git(["tag", "--points-at", commit_hash])
        tags = [t for t in tags_result.stdout.strip().split("\n") if t]

        return VersionInfo(
            commit_hash=commit_hash,
            short_hash=commit_hash[:8],
            message=message,
            author=author,
            timestamp=timestamp,
            files_changed=files,
            insertions=insertions,
            deletions=deletions,
            tags=tags,
        )

    def history(
        self,
        paper_path: str | None = None,
        limit: int = 50,
    ) -> list[VersionInfo]:
        """
        获取版本历史。

        Args:
            paper_path: 可选，限定特定文件的变更历史
            limit: 最大返回数量

        Returns:
            版本信息列表
        """
        if paper_path:
            # 获取特定文件的变更历史
            result = self._run_git([
                "log", "--format=%H|%an|%s|%ai",
                f"--{paper_path}",
                f"-{limit}"
            ])
        else:
            # 获取所有变更历史
            result = self._run_git([
                "log", "--format=%H|%an|%s|%ai",
                f"-{limit}"
            ])

        if result.returncode != 0:
            return []

        versions = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) >= 4:
                commit_hash = parts[0]
                author = parts[1]
                message = parts[2]
                timestamp = parts[3]

                # 获取该版本的文件列表
                files_result = self._run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
                files = [f for f in files_result.stdout.strip().split("\n") if f]

                # 获取标签
                tags_result = self._run_git(["tag", "--points-at", commit_hash])
                tags = [t for t in tags_result.stdout.strip().split("\n") if t]

                versions.append(VersionInfo(
                    commit_hash=commit_hash,
                    short_hash=commit_hash[:8],
                    message=message,
                    author=author,
                    timestamp=timestamp,
                    files_changed=files,
                    tags=tags,
                ))

        return versions

    def diff(
        self,
        old_version: str,
        new_version: str | None = None,
        file_path: str | None = None,
    ) -> DiffInfo:
        """
        对比两个版本的差异。

        Args:
            old_version: 旧版本（commit hash 或标签）
            new_version: 新版本，默认为最新版本
            file_path: 可选，只对比特定文件

        Returns:
            DiffInfo 对象
        """
        if new_version is None:
            new_version = "HEAD"

        # 解析版本（标签转换为 commit hash）
        old_commit = self._resolve_version(old_version)
        new_commit = self._resolve_version(new_version)

        if not old_commit or not new_commit:
            return DiffInfo(
                old_version=old_version,
                new_version=new_version,
                files_changed=[],
                hunks=[],
            )

        # 获取变更的文件列表
        if file_path:
            files = [file_path]
        else:
            result = self._run_git([
                "diff", "--name-only",
                f"{old_commit}..{new_commit}"
            ])
            files = [f for f in result.stdout.strip().split("\n") if f]

        # 获取每个文件的 diff
        hunks = []
        for file in files:
            diff_result = self._run_git([
                "diff", old_commit, new_commit, "--", file
            ])

            if diff_result.stdout.strip():
                hunks.append({
                    "file": file,
                    "diff_text": diff_result.stdout,
                    "old_hash": self._get_file_hash(self.git_dir / file),
                    "new_hash": self._get_file_hash(self.git_dir / file),
                })

        return DiffInfo(
            old_version=old_version,
            new_version=new_version,
            files_changed=files,
            hunks=hunks,
        )

    def _resolve_version(self, version: str) -> str:
        """将标签或短 hash 解析为完整的 commit hash"""
        # 尝试直接作为 commit hash
        result = self._run_git(["rev-parse", version])
        if result.returncode == 0:
            return result.stdout.strip()

        return ""

    def add_tag(
        self,
        version: str,
        tag: str,
        message: str | None = None,
    ) -> bool:
        """
        为指定版本添加标签。

        Args:
            version: 版本（commit hash 或标签名）
            tag: 标签名
            message: 可选，标签描述

        Returns:
            是否成功
        """
        commit = self._resolve_version(version)
        if not commit:
            return False

        tag_name = tag if tag in self.PREDEFINED_TAGS else tag

        result = self._run_git([
            "tag", "-a", tag_name,
            "-m", message or f"{tag_name}: {self.PREDEFINED_TAGS.get(tag, tag)}",
            commit
        ])

        return result.returncode == 0

    def remove_tag(self, tag: str) -> bool:
        """删除标签"""
        result = self._run_git(["tag", "-d", tag])
        return result.returncode == 0

    def list_tags(self) -> list[dict]:
        """列出所有标签"""
        result = self._run_git(["tag", "-l", "-format=%(refname:short)|%(subject)|%(creatordate)"])

        if result.returncode != 0:
            return []

        tags = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            tag_name = parts[0] if parts else line
            message = parts[1] if len(parts) > 1 else ""
            date = parts[2] if len(parts) > 2 else ""

            tags.append({
                "name": tag_name,
                "description": message,
                "date": date,
                "is_predefined": tag_name in self.PREDEFINED_TAGS,
            })

        return tags

    def get_file_at_version(
        self,
        file_path: str,
        version: str | None = None,
    ) -> str | None:
        """
        获取指定版本的文件内容。

        Args:
            file_path: 文件相对路径
            version: 版本，默认为最新

        Returns:
            文件内容
        """
        if version is None:
            version = "HEAD"

        commit = self._resolve_version(version)
        if not commit:
            return None

        result = self._run_git(["show", f"{commit}:{file_path}"])

        if result.returncode == 0:
            return result.stdout

        return None

    def restore_version(
        self,
        file_path: str,
        version: str,
        restore_path: Path | None = None,
    ) -> bool:
        """
        恢复指定版本的文件。

        Args:
            file_path: 文件相对路径
            version: 版本
            restore_path: 恢复到的目标路径，默认为原位置

        Returns:
            是否成功
        """
        content = self.get_file_at_version(file_path, version)
        if content is None:
            return False

        restore_path = restore_path or (self.project_root / file_path)
        restore_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            restore_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def generate_changelog(self, from_version: str | None = None) -> str:
        """
        生成变更日志。

        Args:
            from_version: 起始版本，默认为第一个 commit

        Returns:
            变更日志文本
        """
        if from_version:
            from_commit = self._resolve_version(from_version)
            if not from_commit:
                from_version = None

        result = self._run_git([
            "log", "--format=%h|%s|%ai|%an",
            f"{from_version}..HEAD" if from_version else "-20"
        ])

        if result.returncode != 0:
            return "无法生成变更日志"

        lines = ["# 变更日志\n"]
        current_date = ""

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) >= 4:
                short_hash = parts[0]
                message = parts[1]
                timestamp = parts[2][:10]  # 只取日期
                author = parts[3]

                if timestamp != current_date:
                    current_date = timestamp
                    lines.append(f"\n## {timestamp}\n")

                lines.append(f"- `{short_hash}` {message} ({author})\n")

        return "".join(lines)

    def stats(self) -> dict:
        """获取版本统计信息"""
        # 总 commit 数
        result = self._run_git(["rev-list", "--count", "HEAD"])
        total_commits = int(result.stdout.strip()) if result.returncode == 0 else 0

        # 标签数
        tags_result = self._run_git(["tag", "-l"])
        tags_count = len([t for t in tags_result.stdout.strip().split("\n") if t])

        # 最后更新时间
        log_result = self._run_git(["log", "-1", "--format=%ai"])
        last_update = log_result.stdout.strip() if log_result.returncode == 0 else ""

        return {
            "total_commits": total_commits,
            "total_tags": tags_count,
            "last_update": last_update,
            "repository_path": str(self.git_dir),
        }

    def to_markdown_diff(self, diff_info: DiffInfo) -> str:
        """将 DiffInfo 转换为 Markdown 格式"""
        lines = [
            "# 版本对比",
            "",
            f"**{diff_info.old_version}** → **{diff_info.new_version}**",
            "",
            f"变更文件 ({len(diff_info.files_changed)}):",
        ]

        for hunk in diff_info.hunks:
            lines.append(f"\n## {hunk['file']}")
            lines.append("\n```diff")
            lines.append(hunk["diff_text"])
            lines.append("```")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="论文版本控制系统")
    parser.add_argument("--save", "-s", help="保存版本", metavar="FILE")
    parser.add_argument("--message", "-m", default="", help="提交信息")
    parser.add_argument("--history", "-l", nargs="?", const="", help="查看历史")
    parser.add_argument("--diff", "-d", nargs=2, metavar=("V1", "V2"), help="对比差异")
    parser.add_argument("--tag", "-t", nargs=2, metavar=("VERSION", "TAG"), help="添加标签")
    parser.add_argument("--tags", action="store_true", help="列出所有标签")
    parser.add_argument("--restore", "-r", nargs=2, metavar=("VERSION", "FILE"), help="恢复版本")
    parser.add_argument("--changelog", "-c", help="生成变更日志")
    parser.add_argument("--stats", action="store_true", help="统计信息")

    args = parser.parse_args()

    pvc = PaperVersionControl()

    if args.save:
        commit = pvc.save_version(args.save, args.message or "Auto-save")
        print(f"\n✅ 版本已保存: {commit[:8]}")
        print(f"   路径: {args.save}")

    elif args.history is not None:
        paper_path = args.history if args.history else None
        history = pvc.history(paper_path)

        print(f"\n{'='*70}")
        print(f"  版本历史 ({len(history)} 个版本)")
        print(f"{'='*70}")

        for v in history[:20]:
            tags_str = f" [{', '.join(v.tags)}]" if v.tags else ""
            print(f"\n  `{v.short_hash}` {v.timestamp[:10]}")
            print(f"  {v.message[:60]}")
            print(f"  变更: {len(v.files_changed)} 个文件{tags_str}")

    elif args.diff:
        v1, v2 = args.diff
        diff_info = pvc.diff(v1, v2)

        print(f"\n{'='*70}")
        print(f"  版本对比: {v1} → {v2}")
        print(f"{'='*70}")
        print(f"\n变更文件 ({len(diff_info.files_changed)}):")

        for hunk in diff_info.hunks:
            print(f"\n### {hunk['file']}")
            # 只显示前20行
            diff_lines = hunk["diff_text"].split("\n")[:20]
            for line in diff_lines:
                print(f"  {line}")
            if len(hunk["diff_text"].split("\n")) > 20:
                print("  ... (省略)")

    elif args.tag:
        version, tag = args.tag
        success = pvc.add_tag(version, tag)
        print(f"\n{'✅ 标签添加成功' if success else '❌ 添加失败'}: {tag} → {version}")

    elif args.tags:
        tags = pvc.list_tags()
        print(f"\n{'='*70}")
        print(f"  标签列表 ({len(tags)} 个)")
        print(f"{'='*70}")

        predefined = [t for t in tags if t["is_predefined"]]
        custom = [t for t in tags if not t["is_predefined"]]

        if predefined:
            print("\n预定义标签:")
            for t in predefined:
                print(f"  {t['name']}: {t['description']}")

        if custom:
            print("\n自定义标签:")
            for t in custom:
                print(f"  {t['name']}: {t['description']}")

    elif args.restore:
        version, file_path = args.restore
        success = pvc.restore_version(file_path, version)
        print(f"\n{'✅ 版本已恢复' if success else '❌ 恢复失败'}: {file_path} ← {version}")

    elif args.changelog:
        changelog = pvc.generate_changelog(args.changelog if args.changelog else None)
        print(changelog)

    elif args.stats:
        stats = pvc.stats()
        print(f"\n{'='*70}")
        print("  版本统计")
        print(f"{'='*70}")
        print(f"  总提交数: {stats['total_commits']}")
        print(f"  标签数: {stats['total_tags']}")
        print(f"  最后更新: {stats['last_update']}")
        print(f"  仓库路径: {stats['repository_path']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
