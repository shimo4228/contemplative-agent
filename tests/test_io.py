"""Tests for core/_io shared I/O helpers (process lock, audit M5)."""

import base64
import hashlib
import json
import os
import re
import stat

import pytest

from contemplative_agent.core._io import (
    SUMMARY_MAX_LENGTH,
    acquire_run_lock,
    append_jsonl_restricted,
    b64_audit_fields,
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


class TestWriteRestrictedAtomicM11:
    """Bug-audit 2026-07-06 M11: value-layer writes (skills / rules /
    constitution) must be atomic — an interruption mid-write previously left
    a truncated .md that the next curation run silently consumed."""

    def test_failure_leaves_original_intact(self, tmp_path, monkeypatch):
        import contemplative_agent.core._io as io_mod

        target = tmp_path / "skill.md"
        write_restricted(target, "original body")

        def _boom(src, dst):
            raise OSError("simulated interruption")

        monkeypatch.setattr(io_mod.os, "replace", _boom)
        with pytest.raises(OSError):
            write_restricted(target, "new body")

        assert target.read_text(encoding="utf-8") == "original body"
        assert not (tmp_path / "skill.md.tmp").exists()

    def test_no_tmp_file_left_on_success(self, tmp_path):
        target = tmp_path / "rule.md"
        write_restricted(target, "body")
        assert target.read_text(encoding="utf-8") == "body"
        assert list(tmp_path.glob("*.tmp")) == []


class TestB64AuditFields:
    """Shared replay-safe encoder for untrusted audit text (ADR-0075).

    Single owner for the format used by insight-novelty, skill-selection and
    verification audit logs — these tests are what stops the three from
    drifting apart again.
    """

    def test_untruncated_roundtrips(self):
        text = "hello world"
        fields = b64_audit_fields("prompt", text, max_bytes=1024)
        assert fields["prompt_encoding"] == "base64:utf-8"
        assert fields["prompt_truncated"] is False
        assert fields["prompt_bytes"] == len(text.encode("utf-8"))
        assert base64.b64decode(fields["prompt_b64"]).decode("utf-8") == text
        assert fields["prompt_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_none_emits_only_b64_key(self):
        # "never produced" must stay distinguishable from "produced and empty":
        # no digest, no length, no truncation flag.
        assert b64_audit_fields("output", None, max_bytes=1024) == {"output_b64": None}

    def test_empty_string_is_not_none(self):
        fields = b64_audit_fields("output", "", max_bytes=1024)
        assert fields["output_b64"] == ""
        assert fields["output_bytes"] == 0
        assert fields["output_truncated"] is False

    def test_sha256_covers_full_text_not_kept_prefix(self):
        text = "x" * 100
        fields = b64_audit_fields("prompt", text, max_bytes=10)
        assert fields["prompt_truncated"] is True
        assert fields["prompt_bytes"] == 100
        assert len(base64.b64decode(fields["prompt_b64"])) == 10
        # Digest is over the whole text, so replay can detect a bounded row.
        assert fields["prompt_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_truncated_multibyte_prefix_still_decodes(self):
        # Regression: a raw ``raw[:cap]`` slice cut mid-sequence, so a consumer
        # doing b64decode(...).decode("utf-8") raised UnicodeDecodeError on
        # Japanese payloads. The prefix must land on a codepoint boundary.
        text = "あいうえお" * 10  # 3 bytes per char
        for cap in range(1, 32):
            fields = b64_audit_fields("prompt", text, max_bytes=cap)
            kept = base64.b64decode(fields["prompt_b64"])
            kept.decode("utf-8")  # must not raise
            assert len(kept) <= cap
            assert text.startswith(kept.decode("utf-8"))

    def test_boundary_trim_still_flags_truncation(self):
        # cap=2 on a 3-byte char keeps zero bytes — still a truncation, and the
        # flag must say so rather than reading as a complete empty payload.
        fields = b64_audit_fields("prompt", "あ", max_bytes=2)
        assert base64.b64decode(fields["prompt_b64"]) == b""
        assert fields["prompt_truncated"] is True
        assert fields["prompt_bytes"] == 3

    def test_sha256_override_wins(self):
        # verification passes the solver's precomputed digest so the audit row
        # and the rejected-answer index key stay literally identical.
        fields = b64_audit_fields("challenge", "abc", max_bytes=1024, sha256="deadbeef")
        assert fields["challenge_sha256"] == "deadbeef"

    def test_name_prefixes_every_field(self):
        fields = b64_audit_fields("challenge", "abc", max_bytes=1024)
        assert set(fields) == {
            "challenge_sha256",
            "challenge_encoding",
            "challenge_b64",
            "challenge_bytes",
            "challenge_truncated",
        }
