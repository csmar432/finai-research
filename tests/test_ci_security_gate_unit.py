"""Unit tests for scripts/ci_security_gate.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.ci_security_gate import check_bandit, check_pip_audit, run_cmd


class TestRunCmd:
    """run_cmd() subprocess wrapper."""

    def test_returns_tuple(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_cmd(["echo", "hello"])
            assert isinstance(result, tuple)
            assert len(result) == 3

    def test_returns_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            rc, _, _ = run_cmd(["echo"])
            assert rc == 0

    def test_returns_stdout_stderr(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="hello", stderr="world")
            _, stdout, stderr = run_cmd(["echo"])
            assert stdout == "hello"
            assert stderr == "world"

    def test_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            rc, _, stderr = run_cmd(["nonexistent_tool"])
            assert rc == -1
            assert "not found" in stderr

    def test_generic_exception(self):
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            rc, _, stderr = run_cmd(["tool"])
            assert rc == -1
            assert "boom" in stderr


class TestCheckPipAudit:
    """check_pip_audit() — pip-audit wrapper."""

    def test_returns_bool(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = check_pip_audit()
        assert isinstance(result, bool)

    def test_pip_audit_not_installed_returns_false(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = check_pip_audit()
        assert result is False

    def test_no_vulns(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/pip-audit")
        clean_output = json.dumps({"dependencies": []})
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, clean_output, "")
            result = check_pip_audit()
            assert result is False

    def test_low_severity_vuln_ignored(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/pip-audit")
        vuln_data = {
            "dependencies": [
                {
                    "name": "pkg",
                    "version": "1.0",
                    "vulns": [
                        {"id": "CVE-1", "cvss_severity": "LOW", "cvss_score": 3.0}
                    ],
                }
            ]
        }
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, json.dumps(vuln_data), "")
            result = check_pip_audit()
            assert result is False

    def test_high_severity_vuln_blocks(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/pip-audit")
        vuln_data = {
            "dependencies": [
                {
                    "name": "pkg",
                    "version": "1.0",
                    "vulns": [
                        {"id": "CVE-1", "cvss_severity": "HIGH", "cvss_score": 8.0}
                    ],
                }
            ]
        }
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, json.dumps(vuln_data), "")
            result = check_pip_audit()
            assert result is True

    def test_invalid_json_returns_false(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/pip-audit")
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, "not json", "")
            result = check_pip_audit()
            assert result is False

    def test_empty_output_returns_false(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/pip-audit")
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, "", "")
            result = check_pip_audit()
            assert result is False


class TestCheckBandit:
    """check_bandit() — bandit wrapper."""

    def test_returns_bool(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = check_bandit()
        assert isinstance(result, bool)

    def test_bandit_not_installed_returns_false(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = check_bandit()
        assert result is False

    def test_no_issues(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/bandit")
        output = json.dumps({"results": []})
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, output, "")
            result = check_bandit()
            assert result is False

    def test_low_issue_ignored(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/bandit")
        output = json.dumps({
            "results": [
                {
                    "filename": "x.py",
                    "line_number": 10,
                    "test_name": "B001",
                    "issue_severity": "LOW",
                }
            ]
        })
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, output, "")
            result = check_bandit()
            assert result is False

    def test_high_issue_blocks(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/bandit")
        output = json.dumps({
            "results": [
                {
                    "filename": "x.py",
                    "line_number": 10,
                    "test_name": "B001",
                    "issue_severity": "HIGH",
                }
            ]
        })
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, output, "")
            result = check_bandit()
            assert result is True

    def test_invalid_json_returns_false(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/bandit")
        with patch("scripts.ci_security_gate.run_cmd") as mock_run:
            mock_run.return_value = (0, "not json", "")
            result = check_bandit()
            assert result is False
