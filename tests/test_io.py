"""Tests for core/_io shared I/O helpers (process lock, audit M5)."""

import base64
import hashlib
import json
import logging
import os
import re
import stat

import pytest

from contemplative_agent.core._io import (
    SUMMARY_MAX_LENGTH,
    acquire_run_lock,
    append_jsonl_restricted,
    b64_audit_fields,
    log_safe_identifier,
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
        assert list(tmp_path.glob("*.tmp")) == []

    def test_no_tmp_file_left_on_success(self, tmp_path):
        target = tmp_path / "rule.md"
        write_restricted(target, "body")
        assert target.read_text(encoding="utf-8") == "body"
        assert list(tmp_path.glob("*.tmp")) == []


class TestWriteRestrictedTmpNoFollow:
    """T-WRITE-TMP-NOFOLLOW: the temp file must never be a path an attacker
    can occupy in advance.

    ``os.replace`` is symlink-safe (it replaces the link itself), so the
    *target* was never the exposure — the predictable ``<target>.tmp``
    sibling was. A pre-placed symlink there converted "may write inside
    MOLTBOOK_HOME" into "may write any path on the filesystem", the one
    write path in the staging -> adopt chain that crossed the boundary.
    """

    def test_a_symlink_at_the_old_predictable_name_is_inert(self, tmp_path):
        """The exploit, replayed: pre-place the link the old code followed."""
        home = tmp_path / "home"
        home.mkdir()
        outside = tmp_path / "outside" / "victim.txt"
        outside.parent.mkdir()
        outside.write_text("untouched", encoding="utf-8")

        target = home / "identity.md"
        (home / "identity.md.tmp").symlink_to(outside)

        write_restricted(target, "new identity")

        assert outside.read_text(encoding="utf-8") == "untouched"
        assert target.read_text(encoding="utf-8") == "new identity"

    def test_a_dangling_link_at_the_old_name_creates_nothing(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        planted = outside / "created-by-attacker.md"

        target = home / "identity.md"
        (home / "identity.md.tmp").symlink_to(planted)

        write_restricted(target, "new identity")

        assert not planted.exists()
        assert target.read_text(encoding="utf-8") == "new identity"

    def test_a_hardlink_at_the_old_name_is_inert(self, tmp_path):
        """``O_NOFOLLOW`` does not see hardlinks — only the unpredictable
        name does (code review 2026-08-15: the old code wrote straight
        through one of these too)."""
        home = tmp_path / "home"
        home.mkdir()
        outside = tmp_path / "victim.txt"
        outside.write_text("untouched", encoding="utf-8")
        os.link(outside, home / "rule.md.tmp")

        write_restricted(home / "rule.md", "body")

        assert outside.read_text(encoding="utf-8") == "untouched"
        assert (home / "rule.md").read_text(encoding="utf-8") == "body"

    def test_the_temp_file_is_opened_exclusively_and_without_following(self, tmp_path):
        """Defence in depth pinned by inspection, deliberately.

        With an unpredictable name no behavioural test can distinguish these
        flags — that is the point of the name. They are what keeps the write
        safe if a future change reintroduces a guessable path, so assert
        their presence rather than pretend a black-box test covers them.
        """
        seen: dict[str, int] = {}
        real_open = os.open

        def _record(path, flags, mode=0o777, **kwargs):
            if str(path).endswith(".tmp"):
                seen["mode"] = mode
                seen["flags"] = flags
            return real_open(path, flags, mode, **kwargs)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(os, "open", _record)
        try:
            write_restricted(tmp_path / "rule.md", "body")
        finally:
            monkeypatch.undo()

        assert "mode" in seen, "the temp file was not opened through os.open"
        assert seen["mode"] == 0o600
        assert seen["flags"] & os.O_EXCL
        assert seen["flags"] & os.O_NOFOLLOW

    def test_a_leftover_temp_file_does_not_block_the_write(self, tmp_path):
        """A hard kill leaves an orphan behind; it must not be load-bearing."""
        target = tmp_path / "skill.md"
        stale = tmp_path / "skill.md.abc123.tmp"
        stale.write_text("truncated leftover", encoding="utf-8")

        write_restricted(target, "body")

        assert target.read_text(encoding="utf-8") == "body"
        assert stale.exists(), "an unrelated orphan is not this function's to delete"

    def test_symlinked_target_itself_is_replaced_not_followed(self, tmp_path):
        """Unchanged contract, pinned: ``os.replace`` swaps the link, and
        ``_replaces_canonical_target`` (cli/adopt.py) relies on exactly that."""
        outside = tmp_path / "victim.txt"
        outside.write_text("untouched", encoding="utf-8")
        target = tmp_path / "identity.md"
        target.symlink_to(outside)

        write_restricted(target, "new identity")

        assert outside.read_text(encoding="utf-8") == "untouched"
        assert not target.is_symlink()
        assert target.read_text(encoding="utf-8") == "new identity"

    def test_an_interleaved_writer_cannot_publish_half_a_file(self, tmp_path):
        """The M11 contract under concurrency (code review 2026-08-15).

        What this pins is **temp-name isolation**: a nested write runs to
        completion inside the outer one's ``os.replace``, and the outer
        replace must still find its own inode. Under the old shared name the
        inner writer's replace consumed it and the outer raised
        ``FileNotFoundError``, so this catches the regression — but through
        the exception, not through the asserted splice. The splice itself
        (publishing the other writer's half-written bytes) needs real
        interleaving at the *write* step and is not reproduced here.
        """
        target = tmp_path / "identity.md"
        target.write_text("previous identity\n", encoding="utf-8")
        inner = "B" * 4096

        real_replace = os.replace
        calls: list[str] = []

        def _replace_with_an_interleaved_writer(src, dst):
            if not calls:
                calls.append("outer")
                write_restricted(target, inner)
            return real_replace(src, dst)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(os, "replace", _replace_with_an_interleaved_writer)
        try:
            write_restricted(target, "A" * 4096)
        finally:
            monkeypatch.undo()

        published = target.read_text(encoding="utf-8")
        assert published in ("A" * 4096, inner), "published a spliced file"
        assert list(tmp_path.glob("*.tmp")) == []

    def test_mode_is_pinned_to_0600_under_a_hostile_umask(self, tmp_path):
        """Not "at most 0600" — exactly 0600.

        A umask can only clear bits, so world-readability was never the risk
        once the mode moved onto the create call. The residual is the other
        direction: an ambient umask carrying 0o200 would leave the agent
        unable to rewrite its own identity file.
        """
        original = os.umask(0o377)
        try:
            target = tmp_path / "rule.md"
            write_restricted(target, "body")
        finally:
            os.umask(original)

        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_a_permissive_leftover_cannot_publish_its_own_mode(self, tmp_path):
        """The old fixed name reused whatever inode was sitting there, so a
        0666 leftover published a 0666 value-layer file."""
        target = tmp_path / "rule.md"
        (tmp_path / "rule.md.tmp").write_text("leftover", encoding="utf-8")
        (tmp_path / "rule.md.tmp").chmod(0o666)

        write_restricted(target, "body")

        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_an_unencodable_payload_leaves_no_orphan(self, tmp_path):
        """Fault catalog (ADR-0077): the failure is a ValueError, not an OSError.

        ``handle.write`` raises ``UnicodeEncodeError`` on a lone surrogate,
        which an ``except OSError`` cleanup does not see. With a unique temp
        name the orphan it left was permanent, and the path is reachable from
        attacker-controlled data — ``cli/adopt.py::_mark_sidecar_held``
        re-serialises a user-writable sidecar, so one orphan per attempt.
        """
        target = tmp_path / "identity.md"

        with pytest.raises(UnicodeEncodeError):
            write_restricted(target, "\ud800")

        assert list(tmp_path.glob("*.tmp")) == []
        assert not target.exists()

    def test_a_failure_taking_the_descriptor_leaves_neither_fd_nor_orphan(
        self, tmp_path, monkeypatch
    ):
        """The other new failure path: ``mkstemp`` handed us an fd and a file,
        and ``os.fdopen`` did not take ownership of either."""
        import contemplative_agent.core._io as io_mod

        def _boom(*_args, **_kwargs):
            raise MemoryError("simulated")

        monkeypatch.setattr(io_mod.os, "fdopen", _boom)
        with pytest.raises(MemoryError):
            write_restricted(tmp_path / "rule.md", "body")
        monkeypatch.undo()

        assert list(tmp_path.glob("*.tmp")) == []
        # A leaked fd would still pin the unlinked inode; the cheap
        # observable is that the writer keeps working afterwards.
        write_restricted(tmp_path / "rule.md", "body")
        assert (tmp_path / "rule.md").read_text(encoding="utf-8") == "body"

    def test_an_ordinary_write_is_silent(self, tmp_path, caplog):
        """No log line for the normal path. Pinned because the previous
        design emitted a WARNING on a guard whose negative half nothing
        asserted — mutating it to ``if True`` kept the suite green (code
        review 2026-08-15), so every write would have reported an attack."""
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core._io"):
            write_restricted(tmp_path / "rule.md", "body")
        assert not caplog.records


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


class TestLogSafeIdentifier:
    """Externally-authored display names must not be able to forge log lines.

    The published-body leak (T-LOG-DEBUG-CONTENT) was closed first; the
    2026-08-01 security review then found the same attack available through the
    counterparty's display name, which reaches the launchd log at INFO — so it
    survives a non-verbose run, unlike the body path.
    """

    def test_newline_cannot_start_a_forged_line(self):
        out = log_safe_identifier("alice\nWARNING backoff triggered")
        assert "\n" not in out
        assert "\r" not in out

    def test_ansi_escape_removed(self):
        assert "\x1b" not in log_safe_identifier("bob\x1b[31mred")

    def test_bounded(self):
        assert len(log_safe_identifier("x" * 500)) <= 64

    def test_ordinary_name_untouched(self):
        assert log_safe_identifier("alice_42") == "alice_42"

    def test_all_non_ascii_name_becomes_placeholder(self):
        """Stripping to ASCII empties it, and a hole in the sentence reads as
        a bug — say what happened instead."""
        assert log_safe_identifier("日本語だけの名前") == "<unprintable>"

    def test_whitespace_only_name_becomes_placeholder(self):
        assert log_safe_identifier("   ") == "<unprintable>"

    def test_custom_placeholder(self):
        assert log_safe_identifier("", placeholder="<anon>") == "<anon>"
