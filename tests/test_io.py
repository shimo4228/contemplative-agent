"""Tests for core/_io shared I/O helpers (process lock, audit M5)."""

from contemplative_agent.core._io import acquire_run_lock


class TestAcquireRunLock:
    """flock-based process lock: run takes it non-blocking (fail fast on a
    concurrent session), distill takes it blocking (wait, never skip a
    distill window). Kernel releases the lock on process death — no stale
    lock cleanup needed."""

    def test_acquire_yields_true(self, tmp_path):
        lock = tmp_path / ".run.lock"
        with acquire_run_lock(lock, blocking=False) as acquired:
            assert acquired is True
        assert lock.exists()

    def test_reacquire_after_release(self, tmp_path):
        lock = tmp_path / ".run.lock"
        with acquire_run_lock(lock, blocking=False) as first:
            assert first is True
        with acquire_run_lock(lock, blocking=False) as second:
            assert second is True

    def test_nonblocking_contended_yields_false(self, tmp_path):
        # flock locks belong to the open file description: two separate
        # opens conflict even within one process, so this models a second
        # concurrent process.
        lock = tmp_path / ".run.lock"
        with acquire_run_lock(lock, blocking=False) as outer:
            assert outer is True
            with acquire_run_lock(lock, blocking=False) as inner:
                assert inner is False

    def test_creates_parent_directory(self, tmp_path):
        lock = tmp_path / "nested" / "dir" / ".run.lock"
        with acquire_run_lock(lock, blocking=False) as acquired:
            assert acquired is True
