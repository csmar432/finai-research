#!/usr/bin/env python3
"""
release.py — 一键发布脚本

执行流程：
  1. ✅ 检查 git status (干净)
  2. ✅ 跑测试
  3. ✅ bump version
  4. ✅ 更新 CHANGELOG
  5. ✅ commit + 打 tag
  6. ✅ build wheel + sdist
  7. ✅ 用 twine 上传到 PyPI (或 testpypi)
  8. ✅ 创建 GitHub Release

使用：
  python scripts/release.py 1.0.0 --test   # 上传 test.pypi.org
  python scripts/release.py 1.0.0           # 上传正式 pypi.org
  python scripts/release.py 1.0.0 --skip-tests
  python scripts/release.py 1.0.0 --dry-run
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, check=True, capture=False, **kwargs):
    """执行 shell 命令。"""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=capture,
        text=True,
        **kwargs,
    )
    if check and result.returncode != 0:
        if capture:
            print(result.stdout)
            print(result.stderr)
        sys.exit(result.returncode)
    return result


def check_git_clean():
    """检查 git 工作区干净。"""
    print("\n[1/7] 检查 git 状态...")
    result = run(["git", "status", "--porcelain"], check=False, capture=True)
    if result.stdout.strip():
        print("❌ git 工作区不干净：")
        print(result.stdout)
        print("\n请先 commit 或 stash 所有改动。")
        sys.exit(1)
    print("✅ 工作区干净")


def run_tests(skip_tests):
    """跑测试。"""
    if skip_tests:
        print("\n[2/7] 跳过测试 (--skip-tests)")
        return
    print("\n[2/7] 跑测试...")
    result = run(["pytest", "tests/", "-x", "-q", "--tb=short"], check=False)
    if result.returncode != 0:
        print("❌ 测试失败！")
        sys.exit(1)
    print("✅ 测试通过")


def bump_version(new_version):
    """bump pyproject.toml 版本号。"""
    print(f"\n[3/7] 更新版本号到 {new_version}...")
    pyproject = Path("pyproject.toml")
    content = pyproject.read_text(encoding="utf-8")
    pattern = r'^version = "[^"]+"'
    new_content, count = re.subn(
        pattern, f'version = "{new_version}"', content, count=1, flags=re.MULTILINE
    )
    if count != 1:
        print(f"❌ 无法更新版本号 (匹配 {count} 次)")
        sys.exit(1)
    pyproject.write_text(new_content, encoding="utf-8")
    print(f"✅ pyproject.toml 版本 → {new_version}")


def update_changelog(version):
    """更新 CHANGELOG.md。"""
    print("\n[4/7] 更新 CHANGELOG.md...")
    cl = Path("CHANGELOG.md")
    if not cl.exists():
        print("⚠️  CHANGELOG.md 不存在，跳过")
        return
    content = cl.read_text(encoding="utf-8")
    today = subprocess.run(
        ["date", "+%Y-%m-%d"], capture_output=True, text=True
    ).stdout.strip()
    # 把 [Unreleased] 替换为 [version] - date
    if "## [Unreleased]" in content:
        new_content = content.replace(
            "## [Unreleased]",
            f"## [Unreleased]\n\n## [{version}] - {today}",
            1,
        )
        cl.write_text(new_content, encoding="utf-8")
        print("✅ CHANGELOG 更新")


def commit_and_tag(version, dry_run):
    """commit + 打 tag。"""
    if dry_run:
        print("\n[5/7] 跳过 commit+tag (--dry-run)")
        return
    print(f"\n[5/7] Commit + 打 tag v{version}...")
    run(["git", "add", "pyproject.toml", "CHANGELOG.md"])
    run(["git", "commit", "-m", f"chore(release): bump version to v{version}"])
    run(["git", "tag", f"v{version}"])
    print(f"✅ Tag v{version} 创建成功")
    print("💡 下一步: git push origin main && git push origin v{version}")


def build_artifacts(dry_run):
    """构建 wheel + sdist。"""
    if dry_run:
        print("\n[6/7] 跳过 build (--dry-run)")
        return
    print("\n[6/7] 构建 wheel + sdist...")
    if Path("dist").exists():
        shutil.rmtree("dist")
    if Path("build").exists():
        shutil.rmtree("build")
    run(["python", "-m", "pip", "install", "--upgrade", "build", "twine"], check=False)
    run(["python", "-m", "build"])
    print("✅ 构建完成")
    run(["ls", "-la", "dist/"])


def upload_pypi(test, dry_run):
    """上传到 PyPI。"""
    if dry_run:
        print("\n[7/7] 跳过 upload (--dry-run)")
        return
    print(f"\n[7/7] 上传到 {'TestPyPI' if test else 'PyPI'}...")
    repo = "testpypi" if test else "pypi"
    if not shutil.which("twine"):
        print("❌ twine 未安装。pip install twine")
        sys.exit(1)
    run(["twine", "check", "dist/*"])
    run(["twine", "upload", "--repository", repo, "dist/*"])
    print("✅ 上传成功")


def main():
    parser = argparse.ArgumentParser(
        description="FinAI Research Workflow · 一键发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("version", help="新版本号（语义化版本）")
    parser.add_argument("--test", action="store_true", help="上传到 TestPyPI")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试")
    parser.add_argument(
        "--dry-run", action="store_true", help="演练模式，不实际改任何东西"
    )
    args = parser.parse_args()

    # 验证版本号格式
    if not re.match(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$", args.version):
        print(f"❌ 无效版本号: {args.version}")
        print("  应为: MAJOR.MINOR.PATCH (如 1.0.0)")
        sys.exit(1)

    print("=" * 60)
    print(f"🚀 发布 v{args.version} 到 {'TestPyPI' if args.test else 'PyPI'}")
    print("=" * 60)

    check_git_clean()
    run_tests(args.skip_tests)
    bump_version(args.version)
    update_changelog(args.version)
    commit_and_tag(args.version, args.dry_run)
    build_artifacts(args.dry_run)
    upload_pypi(args.test, args.dry_run)

    print()
    print("=" * 60)
    print("✅ 发布完成！")
    print("=" * 60)
    print()
    print("下一步：")
    print(f"  1. 推 tag:    git push origin v{args.version}")
    print("  2. 在 GitHub 创建 Release (会触发 release-sign.yml)")
    print(f"  3. 验证: pip install finai-research-workflow=={args.version}")


if __name__ == "__main__":
    main()
