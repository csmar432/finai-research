#!/usr/bin/env python3
"""
fix_git_authorship.py — 修复仓库 commit 作者信息

用途: 把所有 commit 的 author/committer 邮箱从一个地址改写为另一个地址
      (例如把 .local 域名改为 GitHub noreply 邮箱, 让绿点 contribution graph 正常显示)

使用场景:
  • 本地 .local 邮箱被推到 GitHub, 想改成 noreply
  • 多个不同邮箱的 commit 统一为一个
  • 切换 GitHub 账户 (新旧邮箱都保留)

工作原理: 用 git filter-branch 重写所有 commit 的 author + committer 信息

⚠️  警告: 这是破坏性操作,会重写 commit hash,所有人需要重新 clone
   建议: 在 push 到 GitHub 之前运行 (如果已 push, 先 git push -f)

使用:
  # 演练 (推荐先看, 不改任何东西)
  python scripts/fix_git_authorship.py \\
    --old-email "old@example.com" \\
    --new-email "12345+your_github_user@users.noreply.github.com" \\
    --new-name "Your Name" \\
    --dry-run

  # 实际执行
  python scripts/fix_git_authorship.py \\
    --old-email "old@example.com" \\
    --new-email "12345+your_github_user@users.noreply.github.com" \\
    --new-name "Your Name"
"""
import argparse
import os
import subprocess
import sys


def get_old_identity():
    """从最新 commit 读取旧 author 信息。"""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("❌ git log 失败")
        sys.exit(1)
    return result.stdout.strip()


def count_commits():
    """总 commit 数。"""
    result = subprocess.run(
        ["git", "rev-list", "--count", "--all"],
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def list_old_authors():
    """列出所有不同的 author 邮箱。"""
    result = subprocess.run(
        ["git", "log", "--all", "--format=%ae | %an"],
        capture_output=True,
        text=True,
    )
    seen = set()
    for line in result.stdout.strip().split("\n"):
        if line and line not in seen:
            seen.add(line)
            print(f"  • {line}")


def dry_run(old_email, new_email, new_name):
    """演练模式, 显示会重写什么。"""
    print("=" * 60)
    print("🔍 演练模式 (不改任何东西)")
    print("=" * 60)
    print()
    print(f"当前 author 邮箱: {get_old_identity()}")
    print(f"  Commit 总数: {count_commits()}")
    print()
    print("所有不同的 author:")
    list_old_authors()
    print()
    print("  → 将改写为:")
    print(f"  {new_name} <{new_email}>")
    print()
    print("⚠️  影响:")
    print("  • 所有 commit hash 会改变")
    print("  • 如果已 push 到 GitHub, 需要 git push -f")
    print("  • 其他人需要重新 clone 仓库")
    print()
    print("✅ 验证命令 (执行后):")
    print("  git log --all --format='%an <%ae>' | sort -u")
    print()


def run_filter_branch(old_email, new_email, new_name):
    """实际重写历史。"""
    print("=" * 60)
    print("🔧 重写 commit 历史...")
    print("=" * 60)
    print()

    # 检查 git filter-branch 可用
    if subprocess.run(["git", "filter-branch", "--help"],
                      capture_output=True).returncode != 0:
        print("❌ git filter-branch 不可用 (非常老旧 git?)")
        sys.exit(1)

    # 用环境变量方式重写
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": new_name,
        "GIT_AUTHOR_EMAIL": new_email,
        "GIT_COMMITTER_NAME": new_name,
        "GIT_COMMITTER_EMAIL": new_email,
    }

    cmd = [
        "git", "filter-branch", "-f",
        "--env-filter", (
            f'if [ "$GIT_AUTHOR_EMAIL" = "{old_email}" ]; then'
            f' export GIT_AUTHOR_NAME="{new_name}";'
            f' export GIT_AUTHOR_EMAIL="{new_email}";'
            f' fi;'
            f' if [ "$GIT_COMMITTER_EMAIL" = "{old_email}" ]; then'
            f' export GIT_COMMITTER_NAME="{new_name}";'
            f' export GIT_COMMITTER_EMAIL="{new_email}";'
            f' fi;'
        ),
        "--tag-name-filter", "cat",
        "--", "--branches", "--tags",
    ]
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print("❌ filter-branch 失败")
        sys.exit(1)

    print()
    print("✅ 历史重写完成")
    print()
    print("🔍 验证:")
    subprocess.run(["git", "log", "-5", "--format=%an <%ae>"])
    print()
    print("下一步:")
    print("  1. git log --all --format='%an <%ae>' | sort -u  # 确认无残留")
    print("  2. git remote -v                                   # 检查 remote")
    print("  3. git push -f origin main                         # 推送到 GitHub (警告!)")
    print("  4. 或撤销: git reset --hard <旧 commit hash>")


def main():
    parser = argparse.ArgumentParser(
        description="修复仓库 commit 作者信息 (改写 author/committer 邮箱)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--old-email",
        required=True,
        help="要替换的旧邮箱 (例如 user@machine.local)",
    )
    parser.add_argument(
        "--new-email",
        required=True,
        help="新邮箱地址 (例如 12345+user@users.noreply.github.com)",
    )
    parser.add_argument(
        "--new-name",
        required=True,
        help='新作者名 (例如 "Your Name")',
    )
    parser.add_argument("--dry-run", action="store_true", help="演练模式")
    args = parser.parse_args()

    if args.dry_run:
        dry_run(args.old_email, args.new_email, args.new_name)
    else:
        print("⚠️  警告: 这会重写所有 commit hash")
        print()
        print(f"  旧邮箱: {args.old_email}")
        print("       →")
        print(f"  新邮箱: {args.new_email}")
        print()
        print(f"  新姓名: {args.new_name}")
        print()
        print(f"  影响的 commit: {count_commits()} 个")
        print()
        response = input("确认执行? (yes/no): ")
        if response.strip().lower() != "yes":
            print("已取消")
            sys.exit(0)
        run_filter_branch(args.old_email, args.new_email, args.new_name)


if __name__ == "__main__":
    main()
