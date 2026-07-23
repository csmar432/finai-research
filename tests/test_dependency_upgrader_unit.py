"""Unit tests for scripts/dependency_upgrader.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def du():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import dependency_upgrader
    yield dependency_upgrader
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestParseVersion:
    def test_basic_version(self, du):
        assert du.parse_version("1.2.3") == (1, 2, 3)

    def test_two_part(self, du):
        assert du.parse_version("1.2") == (1, 2)

    def test_single_int(self, du):
        assert du.parse_version("5") == (5,)

    def test_with_suffix(self, du):
        assert du.parse_version("1.2.3a1") == (1, 2, 3)

    def test_empty_returns_zero_tuple(self, du):
        assert du.parse_version("") == (0,)


class TestIsOutdated:
    def test_older_is_outdated(self, du):
        assert du.is_outdated("1.0.0", "2.0.0") is True

    def test_same_is_not_outdated(self, du):
        assert du.is_outdated("2.0.0", "2.0.0") is False

    def test_newer_is_not_outdated(self, du):
        assert du.is_outdated("2.1.0", "2.0.0") is False

    def test_minor_outdated(self, du):
        assert du.is_outdated("2.0.0", "2.0.1") is True


class TestParseRequirements:
    def test_parses_simple_eq(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("requests==1.2.3\n")
        deps = du.parse_requirements(str(f))
        assert len(deps) == 1
        assert deps[0].name == "requests"
        assert deps[0].current == "1.2.3"
        assert deps[0].operator == "=="

    def test_parses_gte(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("pandas>=2.0.0\n")
        deps = du.parse_requirements(str(f))
        assert deps[0].operator == ">="

    def test_skips_comments(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("# comment\nrequests==1.2.3\n")
        deps = du.parse_requirements(str(f))
        assert len(deps) == 1

    def test_skips_empty_lines(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("\n\nrequests==1.2.3\n\n")
        deps = du.parse_requirements(str(f))
        assert len(deps) == 1

    def test_skips_options(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("-r other.txt\nrequests[extra]==1.2.3\nrequests==1.0.0\n")
        deps = du.parse_requirements(str(f))
        # -r and extras are skipped
        names = [d.name for d in deps]
        assert "requests" in names

    def test_missing_file_warns(self, du, tmp_path, capsys):
        f = tmp_path / "nope.txt"
        deps = du.parse_requirements(str(f))
        assert deps == []

    def test_multiple_packages(self, du, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("a==1.0.0\nb==2.0.0\nc>=3.0.0\n")
        deps = du.parse_requirements(str(f))
        assert len(deps) == 3
        assert [d.name for d in deps] == ["a", "b", "c"]


class TestGetLatestVersion:
    def test_returns_version_on_200(self, du, monkeypatch):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "2.0.0"}}
        with mock.patch.object(du._SESSION, "get", return_value=mock_response):
            assert du.get_latest_version("foo") == "2.0.0"

    def test_returns_none_on_non_200(self, du, monkeypatch):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        with mock.patch.object(du._SESSION, "get", return_value=mock_response):
            assert du.get_latest_version("foo") is None

    def test_returns_none_on_exception(self, du, monkeypatch):
        def raise_exc(*a, **kw):
            raise Exception("nope")
        with mock.patch.object(du._SESSION, "get", side_effect=raise_exc):
            assert du.get_latest_version("foo") is None


class TestCheckSecurity:
    def test_returns_vulns_on_200(self, du, monkeypatch):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vulns": [{"id": "CVE-2023-001"}]}
        with mock.patch.object(du._SESSION, "post", return_value=mock_response):
            vulns = du.check_security("foo", "1.0.0")
            assert vulns == [{"id": "CVE-2023-001"}]

    def test_returns_empty_on_no_vulns(self, du, monkeypatch):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vulns": []}
        with mock.patch.object(du._SESSION, "post", return_value=mock_response):
            assert du.check_security("foo", "1.0.0") == []

    def test_returns_empty_on_exception(self, du, monkeypatch):
        with mock.patch.object(du._SESSION, "post", side_effect=Exception):
            assert du.check_security("foo", "1.0.0") == []

    def test_returns_empty_on_non_200(self, du, monkeypatch):
        mock_response = mock.Mock()
        mock_response.status_code = 500
        with mock.patch.object(du._SESSION, "post", return_value=mock_response):
            assert du.check_security("foo", "1.0.0") == []


class TestDependencyDataclass:
    def test_dependency_construction(self, du):
        d = du.Dependency(name="foo", current="1.0", operator="==", constraint="foo==1.0")
        assert d.name == "foo"
        assert d.current == "1.0"
        assert d.operator == "=="
        assert d.constraint == "foo==1.0"

    def test_dependency_is_namedtuple(self, du):
        d = du.Dependency(name="foo", current="1.0", operator="==", constraint="x")
        # Should be unpackable
        name, current, op, constraint = d
        assert name == "foo"
        assert current == "1.0"

