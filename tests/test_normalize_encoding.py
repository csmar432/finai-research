"""Tests for scripts/core/normalize.py cross-platform environment setup.

audit-2026-07-14 PR-6: validate that ``setup_reproducible_env`` pins
``LC_ALL`` / ``LANG`` / ``PYTHONIOENCODING`` to UTF-8-friendly values so
Chinese (or any non-ASCII) stdout never trips ``UnicodeEncodeError`` on
macOS (cp1252) or Windows (cp936) runners.

These tests are pure stdlib and ``scripts.core.normalize``; they have no
dependency on third-party packages.
"""
from __future__ import annotations

import os
import subprocess
import sys


def test_setup_reproducible_env_sets_utf8_locale():
    """setup_reproducible_env() must override LC_ALL/LANG to C.UTF-8.

    audit-2026-07-14 PR-6 (P1-1): the previous default ``C`` crashed any
    pipeline emitting Chinese/UTF-8 characters on macOS/Windows because
    stdout was cp1252/cp936.  C.UTF-8 keeps the deterministic locale
    (no ``,`` decimal separator surprises) while supporting UTF-8.
    """
    # Strip any inherited env so setdefault takes effect.
    for k in ("LC_ALL", "LANG", "PYTHONIOENCODING"):
        os.environ.pop(k, None)

    from scripts.core.normalize import setup_reproducible_env

    setup_reproducible_env()

    assert os.environ.get("LC_ALL") == "C.UTF-8", (
        f"LC_ALL must be C.UTF-8, got {os.environ.get('LC_ALL')!r}"
    )
    assert os.environ.get("LANG") == "C.UTF-8", (
        f"LANG must be C.UTF-8, got {os.environ.get('LANG')!r}"
    )
    assert os.environ.get("PYTHONIOENCODING") == "utf-8", (
        f"PYTHONIOENCODING must be utf-8, got "
        f"{os.environ.get('PYTHONIOENCODING')!r}"
    )


def test_setup_reproducible_env_does_not_overwrite_explicit_locale():
    """If the user already set LC_ALL, setdefault must respect it.

    The user-facing escape hatch: someone debugging a locale issue can
    pre-set ``LC_ALL=en_US.UTF-8`` and ``setup_reproducible_env`` should
    not silently clobber it.
    """
    os.environ["LC_ALL"] = "en_US.UTF-8"
    os.environ.pop("LANG", None)
    os.environ.pop("PYTHONIOENCODING", None)

    from scripts.core.normalize import setup_reproducible_env

    setup_reproducible_env()

    assert os.environ.get("LC_ALL") == "en_US.UTF-8", (
        "Explicit user LC_ALL must not be overwritten by setdefault"
    )


def test_chinese_stdout_works_under_setup_reproducible_env():
    """End-to-end: Chinese chars in stdout print without crashing.

    Reproduces the audit-reported failure mode: ``LC_ALL=C`` on macOS
    cp1252 stdout → ``UnicodeEncodeError: 'ascii' codec can't encode
    character '\\u4e2d'`` when emitting Chinese.
    """
    # Reset and apply the env.
    for k in ("LC_ALL", "LANG", "PYTHONIOENCODING"):
        os.environ.pop(k, None)
    from scripts.core.normalize import setup_reproducible_env
    setup_reproducible_env()

    # Subprocess prints Chinese to stdout; under broken locale this raises.
    code = (
        "import sys, os; "
        "sys.stdout.write('中文测试 — LC_ALL=' + os.environ.get('LC_ALL', '') + '\\n'); "
        "sys.stdout.flush()"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"Chinese stdout raised under normalize env: "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert "中文测试" in proc.stdout, (
        f"Chinese chars missing from output: {proc.stdout!r}"
    )


def test_ci_verify_recognizes_utf8_locale():
    """ci_verify.py must accept C.UTF-8 as the canonical LC_ALL.

    Audit-2026-07-14 PR-6: ci_verify.py was checking ``LC_ALL == "C"``,
    which would silently fail once normalize.py started setting
    C.UTF-8.  Run run_checks() with C.UTF-8 set and confirm the locale
    check passes.
    """
    # Force LC_ALL=C.UTF-8 (we can't easily mock; run_checks reads env
    # at call time, so it's fine to mutate os.environ here).
    os.environ["LC_ALL"] = "C.UTF-8"
    os.environ["LANG"] = "C.UTF-8"

    from scripts.ci_verify import run_checks  # type: ignore[attr-defined]

    results = run_checks()

    # The locale check is a CheckResult with name containing 'LC_ALL'.
    locale_results = [
        r for r in results if "LC_ALL" in getattr(r, "name", "")
    ]
    assert locale_results, (
        "ci_verify must include an LC_ALL check (sanity that PR-6 edit landed)"
    )
    assert all(getattr(r, "passed", False) for r in locale_results), (
        "ci_verify locale check must pass under C.UTF-8; got: "
        f"{[(r.name, r.passed, r.detail) for r in locale_results]}"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))