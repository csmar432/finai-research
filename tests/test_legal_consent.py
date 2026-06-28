"""LEGAL_CONSENT.md + 3 个 opt-in 服务器法律声明测试 (audit 2026-06-28 P2-3)."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGAL_CONSENT = PROJECT_ROOT / "LEGAL_CONSENT.md"
OPTIN_SERVERS = [
    "user_cnki",
    "user_wanfang",
    "user_chinese_literature",
]


def test_legal_consent_md_exists():
    """LEGAL_CONSENT.md 必须存在（README 引用）。"""
    assert LEGAL_CONSENT.exists(), (
        "README.md 引用 LEGAL_CONSENT.md 但文件不存在。\n"
        "已在 2026-06-28 审计中创建。如果不需要，删除 README 引用。"
    )


def test_legal_consent_covers_all_three_servers():
    """LEGAL_CONSENT.md 必须覆盖 3 个 opt-in 服务器。"""
    content = LEGAL_CONSENT.read_text()
    for srv in ["cnki", "wanfang", "chinese-literature", "user-cnki", "user-wanfang", "user-chinese-literature"]:
        assert srv in content, f"LEGAL_CONSENT.md 应提到 {srv}"


def test_legal_consent_has_optin_instructions():
    """LEGAL_CONSENT.md 必须说明 opt-in 方式。"""
    content = LEGAL_CONSENT.read_text()
    assert "CLI_ACCEPT_RISK" in content, "必须说明 opt-in 环境变量"
    assert "export" in content or "env" in content.lower(), "必须说明启用方法"


def test_legal_consent_has_disclaimer():
    """LEGAL_CONSENT.md 必须含免责声明。"""
    content = LEGAL_CONSENT.read_text()
    assert "免责" in content or "不承担任何责任" in content, (
        "必须明确免责声明"
    )


@pytest.mark.parametrize("server", OPTIN_SERVERS)
def test_optin_server_has_legal_disclaimer_in_header(server):
    """3 个 opt-in 服务器的 server.py 头部必须含法律声明。"""
    from pathlib import Path
    path = PROJECT_ROOT / "mcp_servers" / server / "server.py"
    assert path.exists(), f"{server}/server.py 不存在"
    content = path.read_text()
    # 检查前 30 行
    head = "\n".join(content.splitlines()[:30])
    has_legal = "免责" in head or "法律" in head or "⚠️" in head or "disclaim" in head.lower()
    assert has_legal, f"{server}/server.py 头部必须含法律声明（'免责'/'法律'/'⚠️'）"
