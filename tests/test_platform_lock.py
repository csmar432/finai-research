"""P3 2026-06-29: Unit tests for platform-conditional file locking helpers.

Verifies the cross-platform abstraction introduced in scripts/core/checkpoint.py:
- Unix: fcntl.flock path (LOCK_EX | LOCK_NB)
- Windows: msvcrt.locking path (LK_NBLCK)

These helpers must:
1. Be importable regardless of platform.
2. Acquire an exclusive lock on a writable fd.
3. Raise BlockingIOError when another process holds the lock.
4. Release cleanly without raising.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_lock_file(tmp_path: Path):
    """Provide a writable file fd for lock acquisition tests."""
    lock_path = tmp_path / "test.lock"
    lock_path.write_text("")
    fd = os.open(str(lock_path), os.O_RDWR)
    try:
        yield fd, lock_path
    finally:
        os.close(fd)


@pytest.fixture
def tmp_lock_file_second_fd(tmp_path: Path):
    """Provide a SECOND writable fd to the same file (for contention tests).

    On POSIX (Linux/macOS), flock() locks the OPEN FILE DESCRIPTION, not the
    file descriptor itself — so two fds to the same file in the same process
    share the lock state and second-lock on a different fd succeeds. To
    simulate cross-process contention we use os.open with O_RDWR twice and
    rely on the fact that flock IS reentrant on a single OFD but rejects
    LOCK_NB contention from a different process.

    For our purposes: opening the same file twice in the same process gives
    us two OFDs; locking fd1, then locking fd2 with LOCK_NB should BLOCK on
    most systems. macOS uses the OPEN-FILE-DESCRIPTION lock semantics which
    allows same-process re-locking; Linux treats flock as advisory per-OFD.
    """
    lock_path = tmp_path / "test.lock"
    lock_path.write_text("")
    fd1 = os.open(str(lock_path), os.O_RDWR)
    fd2 = os.open(str(lock_path), os.O_RDWR)
    try:
        yield fd1, fd2, lock_path
    finally:
        os.close(fd1)
        os.close(fd2)


def _import_lock_helpers():
    """Re-import scripts.core.checkpoint module to inspect lock helpers.

    The module-level `if sys.platform == "win32"` branch selects between
    fcntl and msvcrt at import time, so we just import once per test run.
    """
    from scripts.core import checkpoint

    return checkpoint


def test_lock_helpers_are_exposed():
    """Both helpers must exist as module-level callables."""
    cp = _import_lock_helpers()
    assert callable(cp._file_lock_acquire)
    assert callable(cp._file_lock_release)


def test_lock_helpers_are_appropriate_for_platform():
    """Helpers must resolve to the platform-correct implementation.

    - On win32: msvcrt must be importable (and fcntl must NOT be imported
      by this module under the win32 branch).
    - On unix: fcntl must be importable.
    """
    cp = _import_lock_helpers()
    if sys.platform == "win32":
        # On win32 branch, the module imports msvcrt.
        assert hasattr(cp, "msvcrt"), "msvcrt must be importable on win32 branch"
    else:
        # On unix branch, the module imports fcntl.
        assert hasattr(cp, "fcntl"), "fcntl must be importable on unix branch"


def test_acquire_release_roundtrip(tmp_lock_file):
    """Acquire then release must complete without raising."""
    fd, _path = tmp_lock_file
    cp = _import_lock_helpers()

    # Should not raise.
    cp._file_lock_acquire(fd)
    cp._file_lock_release(fd)


def test_acquire_is_exclusive_blocks_second_attempt(tmp_lock_file):
    """A second acquire on the SAME fd is reentrant (POSIX flock semantics).

    Per POSIX, flock() locks the OPEN FILE DESCRIPTION, not the fd itself.
    A single process re-locking the same OFD is allowed (lock count is
    tracked per-OFD, not per-fd). So acquire→acquire on one fd succeeds;
    true contention must come from a DIFFERENT process or DIFFERENT OFD.

    This test documents the reentrant behavior so future refactors don't
    assume fd-level exclusivity (which would break under multi-fd patterns).
    """
    fd, _path = tmp_lock_file
    cp = _import_lock_helpers()

    cp._file_lock_acquire(fd)
    try:
        # Same fd, same OFD: reentrant — must NOT raise.
        cp._file_lock_acquire(fd)
        # But release count must match acquire count for proper cleanup.
        cp._file_lock_release(fd)
    finally:
        cp._file_lock_release(fd)


def test_acquire_on_different_ofd_raises_blocking(tmp_lock_file_second_fd):
    """Two different OFDs to the same file must contend.

    Opening the file twice yields two distinct open file descriptions.
    Locking one and trying to lock the other with LOCK_NB must raise
    BlockingIOError — this guards cross-process semantics.
    """
    fd1, fd2, _path = tmp_lock_file_second_fd
    cp = _import_lock_helpers()

    cp._file_lock_acquire(fd1)
    try:
        with pytest.raises(BlockingIOError):
            cp._file_lock_acquire(fd2)
    finally:
        cp._file_lock_release(fd1)


def test_release_then_reacquire_works(tmp_lock_file):
    """After release, the same fd can be re-acquired."""
    fd, _path = tmp_lock_file
    cp = _import_lock_helpers()

    for _ in range(3):
        cp._file_lock_acquire(fd)
        cp._file_lock_release(fd)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix-only fcntl semantics test",
)
def test_fcntl_path_uses_lock_nb_semantics(tmp_lock_file_second_fd):
    """On unix, verify the helper raises BlockingIOError (not some other error).

    The fcntl path uses LOCK_NB so the call returns EAGAIN immediately if
    contended, surfaced as BlockingIOError. We use two distinct OFDs to
    actually trigger contention (same-OFD is reentrant).

    This test guards against accidental removal of LOCK_NB — without it,
    the second acquire would block indefinitely.
    """
    fd1, fd2, _path = tmp_lock_file_second_fd
    cp = _import_lock_helpers()

    cp._file_lock_acquire(fd1)
    try:
        # Second acquire on a different OFD must fail fast (not block forever).
        import time

        start = time.monotonic()
        with pytest.raises(BlockingIOError):
            cp._file_lock_acquire(fd2)
        elapsed = time.monotonic() - start
        # Should fail in <100ms (LOCK_NB), definitely not the timeout value.
        assert elapsed < 0.1, f"Lock acquire should be non-blocking, took {elapsed:.3f}s"
    finally:
        cp._file_lock_release(fd1)


def test_release_on_unlocked_fd_does_not_raise(tmp_lock_file):
    """Releasing a non-locked fd must not raise.

    On Unix, fcntl.flock is idempotent on unlock; on Windows, msvcrt
    raises OSError if byte region not locked — but our Windows wrapper
    swallows that (safe in cleanup paths).
    """
    fd, _path = tmp_lock_file
    cp = _import_lock_helpers()

    # Should NOT raise even though nothing was locked.
    cp._file_lock_release(fd)


def test_checkpoint_manager_imports_with_helpers():
    """Sanity: CheckpointManager class is importable alongside helpers.

    Guards against refactors that break the cross-platform abstraction
    by ensuring both the lock helpers AND the CheckpointManager class
    can be imported together (checkpoint.py loads both at module init).
    """
    from scripts.core.checkpoint import CheckpointManager

    assert CheckpointManager.__name__ == "CheckpointManager"
