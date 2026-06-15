"""Keychain 统一读取器 — 跨平台密钥获取

读取优先级（向后兼容）：
  1. macOS Keychain（最安全）
  2. 环境变量 os.environ（最常见）
  3. .env 文件（开发 fallback）

用法：
    from scripts.keychain_manager import get_secret
    api_key = get_secret("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY not configured")

环境：
    macOS   — 使用 security CLI (需要 scripts.keychain_setup 先注册)
    Linux   — 自动跳过 Keychain，从 env/.env 读取
    Windows — 自动跳过 Keychain，从 env/.env 读取
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 加载 .env 文件到 os.environ（若已加载则跳过）
try:
    from dotenv import load_dotenv

    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    for _env_name in (".env", ".env.local"):
        _env_path = _PROJECT_ROOT / _env_name
        if _env_path.exists():
            load_dotenv(_env_path, override=False)
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────
# Keychain 支持检测
# ─────────────────────────────────────────────────────────────────────

def _is_macos() -> bool:
    return sys.platform == "darwin"


def _keychain_available() -> bool:
    """检测 macOS Keychain 是否可用"""
    if not _is_macos():
        return False
    import subprocess
    try:
        r = subprocess.run(
            ["security", "show-keychain-info"],
            capture_output=True, timeout=2,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_KEYCHAIN_OK = _keychain_available()
_KEYCHAIN_SERVICE = "论文工作流"


# ─────────────────────────────────────────────────────────────────────
# 核心：get_secret 完整回退链
# ─────────────────────────────────────────────────────────────────────

def _from_keychain(account: str) -> str | None:
    """从 macOS Keychain 读取（仅 macOS）"""
    if not _KEYCHAIN_OK:
        return None
    import subprocess
    try:
        r = subprocess.run(
            ["security", "find-generic-password",
             "-s", _KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_secret(name: str, *, prefer: str = "auto") -> str | None:
    """按优先级读取密钥。

    Args:
        name: 密钥名（e.g. "DEEPSEEK_API_KEY"）
        prefer: 优先级模式
            - "auto" (默认): keychain → env → .env
            - "env": 仅 env/.env
            - "keychain": 仅 keychain

    Returns:
        密钥值，未找到返回 None
    """
    if prefer in ("auto", "keychain"):
        v = _from_keychain(name)
        if v:
            return v

    if prefer in ("auto", "env"):
        v = os.environ.get(name)
        if v:
            return v

    return None


def get_secret_or_warn(name: str) -> str | None:
    """get_secret + 缺失时打 warning（便于迁移期使用）"""
    v = get_secret(name)
    if not v:
        import warnings
        warnings.warn(
            f"[keychain_manager] {name} 未配置。检查："
            f"  1. .env 文件中有 {name}=..."
            f"  2. 或运行: python scripts/keychain_setup.py --register",
            stacklevel=2,
        )
    return v


# ─────────────────────────────────────────────────────────────────────
# 健康检查
# ─────────────────────────────────────────────────────────────────────

def health_check() -> dict:
    """报告 keychain_manager 的状态"""
    return {
        "platform": sys.platform,
        "keychain_available": _KEYCHAIN_OK,
        "keychain_service": _KEYCHAIN_SERVICE if _KEYCHAIN_OK else None,
        "env_loaded": any(
            (Path(__file__).resolve().parent.parent / n).exists()
            for n in (".env", ".env.local")
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(health_check(), indent=2, ensure_ascii=False))
