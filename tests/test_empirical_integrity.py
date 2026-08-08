"""Tests for empirical data root, TOPIC integrity, delivery contract, host wiring."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_resolve_empirical_data_root_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.core.empirical_data_root import resolve_empirical_data_root

    monkeypatch.delenv("FINAI_EMPIRICAL_DATA_ROOT", raising=False)
    data = tmp_path / "panels"
    data.mkdir()
    (data / "green_patent_firm.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(data))
    root = resolve_empirical_data_root()
    assert root.available
    assert root.source == "env"
    assert root.path == data.resolve() or root.path == data


def test_find_candidate_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.core.empirical_data_root import find_candidate_files, resolve_empirical_data_root

    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "firm_green_patent_2019.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("nope", encoding="utf-8")
    root = resolve_empirical_data_root()
    hits = find_candidate_files(["green_patent", "专利"], root)
    assert any("green_patent" in str(h) for h in hits)


def test_topic_integrity_hard_gaps_without_panels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.core.topic_integrity import assess_topic_integrity
    from scripts.core.empirical_data_root import resolve_empirical_data_root

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(empty))
    topic = "使用企业级绿色专利与海关HS码、债券利差完成DID实证"
    report = assess_topic_integrity(topic, data_root=resolve_empirical_data_root())
    assert "firm_green_patents" in report.hard_gaps
    assert "customs_hs" in report.hard_gaps
    assert "bond_spreads" in report.hard_gaps
    assert not report.ok_for_causal_empirics
    skips = report.to_skipped_items()
    assert any("empirics:" in s["item"] for s in skips)


def test_topic_integrity_satisfied_when_files_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.core.topic_integrity import assess_topic_integrity
    from scripts.core.empirical_data_root import resolve_empirical_data_root

    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "企业绿色专利面板.csv").write_text("id,y\n1,0\n", encoding="utf-8")
    topic = "研究企业级绿色专利与数字金融"
    report = assess_topic_integrity(topic, data_root=resolve_empirical_data_root())
    assert "firm_green_patents" in report.satisfied
    assert "firm_green_patents" not in report.hard_gaps


def test_topic_integrity_proxy_warning():
    from scripts.core.topic_integrity import assess_topic_integrity

    topic = "需要海关HS码贸易明细"
    artifact = "本文用海外营收作为海关数据的代理变量完成回归"
    report = assess_topic_integrity(topic, artifact_text=artifact)
    assert any("customs_hs" in w for w in report.proxy_warnings)


def test_delivery_contract_requires_final_and_skipped(tmp_path: Path):
    from scripts.core.delivery_contract import validate_delivery

    (tmp_path / "CODEX_FINAL.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "main.pdf").write_bytes(b"%PDF-1.4")
    bad = validate_delivery(tmp_path, require_pdf=True, allow_alias_final=True)
    assert not bad.ok
    assert "FINAL.md" in bad.missing
    assert "SKIPPED_CONFIG.md" in bad.missing

    (tmp_path / "FINAL.md").write_text("# FINAL\n", encoding="utf-8")
    (tmp_path / "SKIPPED_CONFIG.md").write_text("# SKIP\n", encoding="utf-8")
    good = validate_delivery(tmp_path, require_pdf=True)
    assert good.ok


def test_datafetcher_layer0_local_empirical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.universal_data_fetcher import DataFetcher, DataSource

    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "a_stock_financial_demo.csv").write_text(
        "ts_code,rev\n000001.SZ,1\n", encoding="utf-8"
    )

    class Stub(DataFetcher):
        def try_mcp(self, *a, **k):
            raise NotImplementedError("should not need mcp")

    fetcher = Stub("a_stock_financial")
    result = fetcher.fetch(local_keywords=["a_stock_financial"])
    assert result.available
    assert result.source == DataSource.LOCAL_EMPIRICAL
    assert isinstance(result.data, pd.DataFrame)
    assert "local_empirical" in result.provenance


def test_dotenv_override_false_in_astock_fetcher():
    """Regression: .env.local must not wipe exported env with override=True."""
    import inspect
    from scripts.universal_data_fetcher import AStockFinancialFetcher

    src = inspect.getsource(AStockFinancialFetcher.try_mcp)
    assert "override=True" not in src
    assert "override=False" in src


def test_agent_host_entry_records_topic_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(tmp_path / "nope_missing"))
    (tmp_path / "TOPIC.md").write_text(
        "# T\n\n使用企业级绿色专利完成碳排放权交易DID\n",
        encoding="utf-8",
    )
    from scripts.agent_host_entry import main

    with patch("scripts.health_check.run_diagnostic") as diag:
        diag.return_value = MagicMock(llm_available=True, llm_status="ok")
        code = main(
            [
                "--output-dir",
                str(tmp_path / "output"),
                "--dry-run-preflight",
                "--check-delivery",
            ]
        )
    assert code == 0
    skipped = (tmp_path / "output" / "SKIPPED_CONFIG.md").read_text(encoding="utf-8")
    assert "empirics:" in skipped or "企业级绿色专利" in skipped or "firm_green"
    assert (tmp_path / "output" / "DELIVERY.md").is_file()
    final = (tmp_path / "output" / "FINAL.md").read_text(encoding="utf-8")
    assert "do **not** invent a parallel pipeline" in final or "parallel pipeline" in final


def test_agent_host_block_on_topic_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("FINAI_EMPIRICAL_DATA_ROOT", str(empty))
    from scripts.agent_host_entry import main

    with patch("scripts.health_check.run_diagnostic") as diag:
        diag.return_value = MagicMock(llm_available=True, llm_status="ok")
        code = main(
            [
                "--topic",
                "企业级绿色专利与海关HS码的因果识别",
                "--output-dir",
                str(tmp_path / "output"),
                "--block-on-topic-gaps",
            ]
        )
    assert code == 4
    text = (tmp_path / "output" / "SKIPPED_CONFIG.md").read_text(encoding="utf-8")
    assert "empirics:" in text
