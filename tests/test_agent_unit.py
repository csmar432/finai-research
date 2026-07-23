"""Unit tests for scripts/agent.py."""

from __future__ import annotations


from scripts.agent import _print_result


class TestPrintResult:
    """_print_result() formats result dicts."""

    def test_print_result_with_status_object(self, capsys):
        """Status with .state attribute should print formatted."""
        # Mock a status object with state, completed_tasks, failed_tasks, avg_score
        class MockState:
            value = "completed"

        class MockStatus:
            state = MockState()
            completed_tasks = 5
            failed_tasks = 1
            avg_score = 0.85

        result = {
            "session_id": "s1",
            "status": MockStatus(),
            "summary": "Test summary",
        }
        _print_result(result)
        captured = capsys.readouterr()
        assert "s1" in captured.out
        assert "Test summary" in captured.out
        assert "0.85" in captured.out

    def test_print_result_with_string_status(self, capsys):
        result = {
            "session_id": "s2",
            "status": "completed",
            "completed_tasks": 3,
            "failed_tasks": 0,
            "avg_score": 0.9,
            "summary": "another summary",
        }
        _print_result(result)
        captured = capsys.readouterr()
        assert "s2" in captured.out
        assert "another summary" in captured.out

    def test_print_result_none_status(self, capsys):
        result = {
            "session_id": "s3",
            "status": None,
            "summary": "summary here",
        }
        _print_result(result)
        captured = capsys.readouterr()
        assert "s3" in captured.out
        assert "summary here" in captured.out

    def test_print_result_empty_summary(self, capsys):
        result = {
            "session_id": "s4",
            "status": "running",
        }
        _print_result(result)
        captured = capsys.readouterr()
        assert "s4" in captured.out
        assert "无" in captured.out


class TestPrintResultAvgScoreNone:
    """_print_result handles avg_score=None."""

    def test_avg_none_with_object(self, capsys):
        class MockState:
            value = "completed"

        class MockStatus:
            state = MockState()
            completed_tasks = 0
            failed_tasks = 0
            avg_score = None

        result = {
            "session_id": "s5",
            "status": MockStatus(),
            "summary": "x",
        }
        _print_result(result)
        captured = capsys.readouterr()
        assert "s5" in captured.out
        assert "N/A" in captured.out
