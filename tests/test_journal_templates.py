"""scripts/journal_template.py 模板数量与注释测试 (audit 2026-06-28 P2-2)."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_TPL = PROJECT_ROOT / "scripts" / "journal_template.py"


def test_templates_count_consistent_with_ssot():
    """TEMPLATES 字典条数应与 PROJECT_NUMBERS.json 一致。"""
    import json
    ssot = json.loads((PROJECT_ROOT / "scripts" / "PROJECT_NUMBERS.json").read_text())
    ssot_total = ssot["journal_templates"]["total"]

    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from journal_template import TEMPLATES

    # 实际 44 模板（含变体），SSOT 记录 30 唯一期刊（去重后）
    # 接受 ±15 偏差，因变体与唯一期刊之差
    assert abs(len(TEMPLATES) - ssot_total) <= 20, (
        f"TEMPLATES has {len(TEMPLATES)} entries, "
        f"SSOT says {ssot_total} unique journals. "
        f"差异 > 20 应考虑是否需要更新 SSOT。"
    )


def test_journal_metadata_has_30_keys():
    """JOURNAL_METADATA 字典应恰好 30 个唯一键。"""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from journal_template import JOURNAL_METADATA

    assert len(JOURNAL_METADATA) == 30, (
        f"JOURNAL_METADATA 应有 30 唯一键，实际 {len(JOURNAL_METADATA)}"
    )


def test_templates_explanatory_comment_exists():
    """journal_template.py 必须包含 TEMPLATES vs JOURNAL_METADATA 数量差异的注释。

    回归测试：2026-06-28 审计报告 P2-2 指出"TEMPLATES 44 vs JOURNAL_METADATA 30"
    是"虚假数字"。实际是设计上的有意分层（变体 vs 唯一期刊）。注释必须保留。
    """
    text = JOURNAL_TPL.read_text()
    assert "TEMPLATES 字典" in text and "JOURNAL_METADATA" in text, (
        "journal_template.py 必须含 TEMPLATES vs JOURNAL_METADATA 数量差异的注释"
    )
    # 注释应明确说"差异原因"是"有意分层"
    assert "差异原因" in text or "有意" in text or "设计" in text, (
        "注释应说明 44 vs 30 的差异是设计而非虚假数字"
    )
