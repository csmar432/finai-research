#!/usr/bin/env python3
"""
Keychain 管理脚本
=================
使用 macOS Keychain 安全存储 API 密钥，替代明文 .env 文件。

首次使用：
  python scripts/keychain_setup.py --register

查看已存储：
  python scripts/keychain_setup.py --list

删除密钥：
  python scripts/keychain_setup.py --delete

使用方法（代码中无需修改）：
  from scripts.keychain_manager import get_secret
  api_key = get_secret("论文工作流", "DEEPSEEK_API_KEY")
"""

import argparse
import subprocess
from pathlib import Path

SERVICE = "论文工作流"

KEYS = {
    "RELAY_API_KEY":    "中转 API Key（兼容 OpenAI 格式的代理服务，如 B.AI/Groq/Nexr/OpenRouter）",
    "DEEPSEEK_API_KEY": "DeepSeek 直连 API Key",
    "ZHIPU_API_KEY":    "智谱 AI API Key",
    # MCP Server 专用
    "TUSHARE_TOKEN":       "Tushare Pro Token（A 股数据：行情/财务/融资融券）",
    "EODHD_API_KEY":       "EODHD API Key（全球宏观数据：GDP/CPI/国债收益率）",
    "FRED_API_KEY":        "FRED API Key（美联储经济数据）",
    "ALPHA_VANTAGE_API_KEY": "Alpha Vantage（股价/外汇数据）",
    "TIINGO_API_KEY":        "Tiingo（美股基本面+新闻）",
    "POLYGON_API_KEY":       "Polygon.io（美股实时行情）",
    "COINGECKO_API_KEY":     "CoinGecko（加密货币数据）",
}


def _run_security(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["security"] + args, capture_output=True, text=True)


def get_secret(account: str) -> str | None:
    """从 Keychain 读取密钥，找不到返回 None"""
    result = _run_security(["find-generic-password", "-s", SERVICE, "-a", account, "-w"])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def set_secret(account: str, password: str) -> bool:
    """写入 Keychain。已存在则更新"""
    # 先尝试删除旧的（避免 macOS 报错）
    _run_security(["delete-generic-password", "-s", SERVICE, "-a", account])
    result = _run_security(["add-generic-password", "-s", SERVICE, "-a", account, "-w", password])
    if result.returncode == 0:
        print(f"  ✅ 已存入 Keychain: {account}")
        return True
    print(f"  ❌ 写入失败 [{account}]: {result.stderr}")
    return False


def delete_secret(account: str) -> bool:
    """从 Keychain 删除密钥"""
    result = _run_security(["delete-generic-password", "-s", SERVICE, "-a", account])
    if result.returncode == 0:
        print(f"  🗑️  已删除: {account}")
        return True
    print(f"  ⚠️  未找到: {account}")
    return False


def register_from_env():
    """从当前 .env.local 批量注册到 Keychain"""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env.local"
    if not env_file.exists():
        print(f"❌ 未找到 {env_file}，跳过 .env.local 导入")
        return

    print(f"\n从 {env_file} 导入现有密钥到 Keychain...\n")
    success = 0
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if key in KEYS and value and not value.startswith("YOUR_"):
            if set_secret(key, value):
                success += 1
    print(f"\n✅ 完成，共导入 {success} 个密钥到 Keychain")
    print("\n💡 建议后续删除 .env.local 文件，彻底告别明文存储")
    print("   删除前请确认所有密钥已在 Keychain 中！")


def register_interactive():
    """交互式注册新密钥"""
    print("\n=== 交互式注册密钥 ===\n")
    for key, desc in KEYS.items():
        existing = get_secret(key)
        if existing:
            print(f"  ⏭️  {key} 已存在，跳过")
            continue
        print(f"\n  [{key}] {desc}")
        value = input("    输入密钥值（输入空行跳过）: ").strip()
        if value:
            set_secret(key, value)


def list_secrets():
    """查看已存储的密钥（不显示实际值，仅确认存在）"""
    print(f"\nKeychain 服务: {SERVICE}\n")
    found = 0
    for key, desc in KEYS.items():
        if get_secret(key):
            print(f"  ✅ {key} — {desc}")
            found += 1
        else:
            print(f"  ❌ {key} — {desc}")
    print(f"\n共 {found}/{len(KEYS)} 个密钥已注册")


def delete_all():
    """删除所有密钥"""
    print("\n⚠️  确认删除所有密钥？此操作不可恢复！")
    confirm = input("输入 'YES' 确认: ").strip()
    if confirm != "YES":
        print("取消。")
        return
    for key in KEYS:
        delete_secret(key)
    print("\n✅ 已清空所有密钥")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keychain 密钥管理")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", action="store_true", help="从 .env.local 注册密钥到 Keychain")
    group.add_argument("--interactive", action="store_true", help="交互式注册新密钥")
    group.add_argument("--list", action="store_true", help="查看已存储的密钥")
    group.add_argument("--delete", action="store_true", help="删除所有密钥")
    args = parser.parse_args()

    if args.register:
        register_from_env()
    elif args.interactive:
        register_interactive()
    elif args.list:
        list_secrets()
    elif args.delete:
        delete_all()
