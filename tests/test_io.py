"""Tests for core/_io shared I/O helpers (process lock, audit M5)."""

import json
import os
import re
import stat

import pytest

from contemplative_agent.core._io import (
    SUMMARY_MAX_LENGTH,
    acquire_run_lock,
    append_jsonl_restricted,
    now_iso,
    strip_code_fence,
    truncate,
    write_restricted,
)


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


class TestTruncate:
    @pytest.mark.parametrize(
        "text,max_length,expected",
        [
            ("short", 10, "short"),
            ("exactly-10", 10, "exactly-10"),
            ("", 10, ""),
        ],
        ids=["under-max", "at-boundary", "empty"],
    )
    def test_no_change_when_within_limit(self, text, max_length, expected):
        assert truncate(text, max_length) == expected

    def test_truncates_to_exact_max_length(self):
        result = truncate("a" * 20, 10)
        assert result == "a" * 7 + "..."
        assert len(result) == 10

    def test_default_cap_is_summary_max_length(self):
        result = truncate("x" * 500)
        assert len(result) == SUMMARY_MAX_LENGTH
        assert result.endswith("...")

    def test_japanese_truncated_by_chars(self):
        result = truncate("あ" * 20, 10)
        assert result == "あ" * 7 + "..."
        assert len(result) == 10


class TestStripCodeFence:
    def test_text_without_fence_unchanged(self):
        assert strip_code_fence("plain text") == "plain text"

    def test_surrounding_whitespace_stripped(self):
        assert strip_code_fence("  plain  \n") == "plain"

    def test_json_fence_removed(self):
        assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fence_without_language_tag_removed(self):
        assert strip_code_fence("```\nbody\n```") == "body"

    def test_inner_fence_lines_also_removed_when_leading_fence(self):
        # Implementation behaviour: once the text starts with a fence,
        # every fence line is filtered out, including inner ones.
        text = "```\nkeep\n```python\ninner\n```\n```"
        assert strip_code_fence(text) == "keep\ninner"

    def test_inner_fence_kept_when_no_leading_fence(self):
        text = "intro\n```\ncode\n```"
        assert strip_code_fence(text) == text

    def test_empty_string(self):
        assert strip_code_fence("") == ""


class TestWriteRestricted:
    def test_content_round_trip_unicode(self, tmp_path):
        path = tmp_path / "out.md"
        write_restricted(path, "日本語 content ✓")
        assert path.read_text(encoding="utf-8") == "日本語 content ✓"

    def test_new_file_has_0600_permissions(self, tmp_path):
        path = tmp_path / "secret.md"
        write_restricted(path, "x")
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "out.md"
        write_restricted(path, "first")
        write_restricted(path, "second")
        assert path.read_text(encoding="utf-8") == "second"

    def test_umask_restored_after_call(self, tmp_path):
        original = os.umask(0o022)
        try:
            write_restricted(tmp_path / "f.md", "x")
            assert os.umask(0o022) == 0o022
        finally:
            os.umask(original)


class TestAppendJsonlRestricted:
    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "log.jsonl"
        append_jsonl_restricted(path, {"a": 1})
        assert path.exists()

    def test_n_appends_yield_n_parseable_lines(self, tmp_path):
        path = tmp_path / "log.jsonl"
        for i in range(3):
            append_jsonl_restricted(path, {"i": i})
        lines = path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["i"] for line in lines] == [0, 1, 2]

    def test_new_file_has_0600_permissions(self, tmp_path):
        path = tmp_path / "log.jsonl"
        append_jsonl_restricted(path, {"a": 1})
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_existing_file_permissions_preserved(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text("")
        path.chmod(0o644)
        append_jsonl_restricted(path, {"a": 1})
        assert stat.S_IMODE(path.stat().st_mode) == 0o644

    def test_unicode_written_raw_not_escaped(self, tmp_path):
        path = tmp_path / "log.jsonl"
        append_jsonl_restricted(path, {"msg": "日本語"})
        raw = path.read_text(encoding="utf-8")
        assert "日本語" in raw
        assert "\\u" not in raw


class TestNowIso:
    def test_default_minutes_precision(self):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00", now_iso())

    def test_seconds_precision(self):
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", now_iso(timespec="seconds")
        )

    def test_utc_offset(self):
        assert now_iso().endswith("+00:00")
