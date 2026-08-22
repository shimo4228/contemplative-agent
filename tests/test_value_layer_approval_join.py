"""Tests for scripts/value_layer_approval_join.py (approval-provenance join).

The weekly state diff shows *what* changed in the value layer and said
nothing about *whether it passed the ADR-0012 gate*, so the 2026-08-15
report raised its loudest alarm on a question ``logs/audit.jsonl`` had
already answered. This join renders that answer next to each diff section.

What is pinned here is the three-state distinction the instrument exists
for — an approved row present, an approved row *absent while the section
shows a diff* (the alarm), and the log being unreadable (never the alarm) —
plus the render boundary: ``reason`` is operator free text and ``source_ids``
is an unbounded lineage list, and neither may ever reach the prompt.

The live-text reconciliation (2026-08-22 F1.2) is pinned beside it: the row
tally answers "was there an approval row", never "are these the approved
bytes", so a hand-repaired value layer reads identical to an untouched one.
The three named states — live text matching an approved row, live text
matching none, and an approved row with no live file carrying its hash —
are asserted separately, together with the fact that the tally stays clean
in the second case (which is why the hash comparison has to exist).

Calibration is pinned beside the states (review, 2026-08-22): the second
state is also where a shipped default permanently sits — ``init`` copies
the template value layer in with no audit row — so the rendering must name
that cause instead of asserting a bypass, and an empty section directory
must abstain rather than read as reconciled.

Fault column (ADR-0077): a missing or unreadable audit log renders an
explicit ``unavailable (reason=…)`` line, and so does an unhashable live
layer. An unavailable instrument that rendered as "no approval record" (or
as "matches NO approved row") would manufacture the exact false alarm this
finding set out to make impossible.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _audit  # noqa: E402  # pyright: ignore[reportMissingImports]
import value_layer_approval_join as vlaj  # noqa: E402  # pyright: ignore[reportMissingImports]
import value_layer_due_check as vldc  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "value_layer_approval_join.py"

HOME = "/Users/someone/.config/moltbook"
START = "2026-08-01T23:00:00+09:00"
END = "2026-08-08T23:00:00+09:00"
# More live files than one reconciliation line may name, so the overflow is
# exercised rather than assumed.
_CAP_OVERFLOW = 8


def _ts(raw: str) -> datetime:
    parsed = vlaj.parse_ts(raw)
    assert parsed is not None
    return parsed


# ``path`` is deliberately ``object``: one test feeds a non-string to pin that a
# malformed record is skipped rather than crashing the whole reading.
def _record(
    path: object, ts: str, *, command: str = "insight", decision: str = "approved", **extra
):
    return {
        "ts": ts,
        "command": command,
        "path": path,
        "decision": decision,
        "source": "direct",
        "content_hash": "abc123def4567890",
        **extra,
    }


def _reading(
    records, *, section="skills", changed=True, top=vlaj._DEFAULT_TOP, unparsable=0, live=None
):
    return vlaj.build_reading(
        records,
        section=section,
        changed=changed,
        start=_ts(START),
        end=_ts(END),
        unparsable=unparsable,
        top=top,
        live=live,
    )


class TestSectionMatching:
    def test_each_section_claims_only_its_own_paths(self):
        records = [
            _record(f"{HOME}/identity.md", "2026-08-03T01:00:00+00:00"),
            _record(f"{HOME}/constitution/contemplative-axioms.md", "2026-08-03T02:00:00+00:00"),
            _record(f"{HOME}/skills/a-skill.md", "2026-08-03T03:00:00+00:00"),
            _record(f"{HOME}/rules/a-rule.md", "2026-08-03T04:00:00+00:00"),
            _record(f"{HOME}/knowledge.json", "2026-08-03T05:00:00+00:00"),
        ]
        for section in ("identity", "constitution", "skills", "rules"):
            reading = _reading(records, section=section)
            assert len(reading.rows) == 1, section
            assert reading.approved == 1, section

    def test_knowledge_json_belongs_to_no_value_layer_section(self):
        records = [_record(f"{HOME}/knowledge.json", "2026-08-03T05:00:00+00:00")]
        for section in ("identity", "constitution", "skills", "rules"):
            assert _reading(records, section=section).rows == ()

    def test_a_file_named_like_a_section_is_not_that_section(self):
        """Only a *parent* component names a directory section.

        Matching the whole path would let ``.../notes/skills`` (a file) count
        as a skills approval and quietly satisfy the alarm.
        """
        records = [_record(f"{HOME}/notes/skills", "2026-08-03T03:00:00+00:00")]
        assert _reading(records, section="skills").rows == ()

    def test_a_relocated_home_still_matches(self):
        """Records carry whatever MOLTBOOK_HOME was live at write time."""
        records = [
            _record("/mnt/backup/moltbook-2025/skills/a-skill.md", "2026-08-03T03:00:00+00:00")
        ]
        assert len(_reading(records, section="skills").rows) == 1

    def test_a_non_string_path_is_skipped_not_crashed(self):
        assert _reading([_record(None, "2026-08-03T03:00:00+00:00")]).rows == ()

    def test_a_renamed_identity_leaf_still_belongs_to_the_identity_section(self):
        """The one defect class that matters here renames the target.

        Live on 2026-08-15: the H5 collision guard turned an approved
        ``distill-identity`` write into ``identity-2.md``
        (``cli/adopt.py::_replaces_canonical_target``). On a leaf-name match
        that approved row belonged to no section, leaving ``approved 0,
        staged 1, changed=True`` — this instrument's own maximum-severity
        output, raised on a question ``audit.jsonl`` had answered.
        """
        records = [
            _record(
                f"{HOME}/identity.md",
                "2026-08-03T04:03:59+00:00",
                command="distill-identity",
                decision="staged",
            ),
            _record(
                f"{HOME}/identity-2.md",
                "2026-08-03T04:20:00+00:00",
                command="distill-identity",
                content_hash="TWINHASH00000001",
            ),
        ]
        reading = _reading(records, section="identity", changed=True)
        assert reading.approved == 1
        assert reading.staged == 1
        assert reading.unmatched == 0, "a placed row is not also a residual"
        rendered = vlaj.format_reading(reading)
        assert "NO APPROVED RECORD" not in rendered
        assert "TWINHASH00000001" in rendered

    def test_the_identity_command_vocabulary_is_shared_with_the_cadence_reading(self):
        """One set, not two copies.

        The command arm above places a row the leaf name cannot. If a command
        rename reached only one of the two readings, that row would be counted
        by neither — invisible, which is the drop this join was repaired to
        stop. Pinned on identity (`is`) rather than equality so a re-introduced
        local copy fails here even while its contents still happen to agree.
        """
        assert vlaj.IDENTITY_COMMANDS is _audit.IDENTITY_COMMANDS
        assert vldc.IDENTITY_COMMANDS is _audit.IDENTITY_COMMANDS

    def test_the_command_arm_does_not_steal_a_directory_section_row(self):
        """A row inside ``skills/`` stays a skills row whatever its command.

        Counting it twice would let one approval clear two sections' alarms.
        """
        records = [
            _record(
                f"{HOME}/skills/a-skill.md",
                "2026-08-03T03:00:00+00:00",
                command="distill-identity",
            )
        ]
        identity = _reading(records, section="identity")
        assert identity.rows == ()
        assert identity.approved == 0
        assert len(_reading(records, section="skills").rows) == 1
        assert identity.unmatched == 0


class TestWindowing:
    def test_window_is_half_open_on_the_start_commit(self):
        """A record stamped at the start commit is already inside its tree.

        Counting it would credit the *previous* week's approval to this
        week's diff.
        """
        at_start = _reading([_record(f"{HOME}/skills/s.md", START)])
        assert at_start.rows == ()

        just_after = _reading([_record(f"{HOME}/skills/s.md", "2026-08-01T23:00:01+09:00")])
        assert len(just_after.rows) == 1

    def test_window_is_closed_on_the_end_commit(self):
        assert len(_reading([_record(f"{HOME}/skills/s.md", END)]).rows) == 1
        after = _reading([_record(f"{HOME}/skills/s.md", "2026-08-08T23:00:01+09:00")])
        assert after.rows == ()

    def test_mixed_offsets_compare_on_the_instant_not_the_string(self):
        """``2026-08-02T00:30:00+09:00`` is inside a window whose start is
        ``2026-08-01T23:00:00+09:00`` — a lexical compare would agree here,
        but the same instant written as UTC (``2026-08-01T15:30:00Z``) sorts
        before the start string while being after it in time."""
        reading = _reading([_record(f"{HOME}/skills/s.md", "2026-08-01T15:30:00Z")])
        assert len(reading.rows) == 1

    def test_pre_2026_04_timestamp_key_is_recognized(self):
        """The audit log carries schema drift the due-check already handles;
        the two readings must not disagree about which rows exist."""
        legacy = {
            "timestamp": "2026-08-03T01:00:00+00:00",
            "command": "distill-identity-ca",
            "path": f"{HOME}/identity.md",
            "decision": "approved",
            "content_hash": "0123456789abcdef",
        }
        reading = _reading([legacy], section="identity")
        assert len(reading.rows) == 1
        assert reading.rows[0].source == "—", "a missing source must render, not vanish"


class TestAlarmCondition:
    def test_changed_with_no_approved_row_is_the_alarm(self):
        rendered = vlaj.format_reading(_reading([], changed=True))
        assert "NO APPROVED RECORD" in rendered

    def test_a_staged_row_alone_does_not_satisfy_the_gate(self):
        """``staged`` is a deferred decision, not an approval (ADR-0074)."""
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", decision="staged")]
        reading = _reading(records, changed=True)
        assert reading.staged == 1
        assert reading.approved == 0
        assert "NO APPROVED RECORD" in vlaj.format_reading(reading)

    def test_a_rejected_row_alone_does_not_satisfy_the_gate(self):
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", decision="rejected")]
        reading = _reading(records, changed=True)
        assert reading.rejected == 1
        assert "NO APPROVED RECORD" in vlaj.format_reading(reading)

    def test_an_approved_row_clears_the_alarm_and_is_citable(self):
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00")]
        rendered = vlaj.format_reading(_reading(records, changed=True))
        assert "NO APPROVED RECORD" not in rendered
        assert "abc123def4567890" in rendered
        assert "2026-08-03T03:00:00+00:00" in rendered

    def test_no_diff_and_no_rows_is_not_an_alarm(self):
        rendered = vlaj.format_reading(_reading([], changed=False))
        assert "NO APPROVED RECORD" not in rendered
        assert "nothing to reconcile" in rendered

    def test_rows_without_a_diff_are_still_rendered(self):
        """Approved but absent from the diff is its own signal (sync lag)."""
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00")]
        rendered = vlaj.format_reading(_reading(records, changed=False))
        assert "abc123def4567890" in rendered
        assert "NO APPROVED RECORD" not in rendered


class TestUnmatchedRowsAreVisible:
    """A row this join cannot place must read as "cannot tell", not silence.

    The 08-15 misfire was an *approved* row falling outside every section
    predicate: the tally emptied and the alarm fired on the emptiness. Any
    future unanticipated path shape must be visible in the render instead.
    """

    def test_an_unplaceable_in_window_row_is_counted_and_rendered(self):
        records = [_record(f"{HOME}/knowledge.json", "2026-08-03T05:00:00+00:00")]
        for section in ("identity", "constitution", "skills", "rules"):
            reading = _reading(records, section=section)
            assert reading.rows == (), section
            assert reading.unmatched == 1, section
            assert "matched no section" in vlaj.format_reading(reading), section

    def test_a_malformed_path_is_a_residual_not_a_silent_drop(self):
        reading = _reading([_record(None, "2026-08-03T03:00:00+00:00")])
        assert reading.rows == ()
        assert reading.unmatched == 1

    def test_an_out_of_window_unplaceable_row_is_not_counted(self):
        """The residual describes this window, like every other tally here."""
        records = [_record(f"{HOME}/knowledge.json", "2026-08-09T05:00:00+00:00")]
        assert _reading(records).unmatched == 0

    def test_no_residual_line_when_every_row_is_placed(self):
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00")]
        reading = _reading(records)
        assert reading.unmatched == 0
        assert "matched no section" not in vlaj.format_reading(reading)


class TestRenderBoundary:
    def test_reason_and_source_ids_never_reach_the_render(self):
        records = [
            _record(
                f"{HOME}/skills/s.md",
                "2026-08-03T03:00:00+00:00",
                reason="FREE-TEXT-MARKER typed by the operator",
                source_ids=["LINEAGE-MARKER-1", "LINEAGE-MARKER-2"],
                epistemic_counts={"generated": 3},
            )
        ]
        rendered = vlaj.format_reading(_reading(records))
        assert "FREE-TEXT-MARKER" not in rendered
        assert "LINEAGE-MARKER-1" not in rendered

    def test_target_paths_never_reach_the_render(self):
        """Skill filenames are slugified from distilled pattern text."""
        records = [
            _record(f"{HOME}/skills/SLUG-MARKER-from-a-post.md", "2026-08-03T03:00:00+00:00")
        ]
        rendered = vlaj.format_reading(_reading(records))
        assert "SLUG-MARKER" not in rendered

    def test_a_newline_in_a_field_cannot_break_out_of_its_cell(self):
        records = [
            _record(
                f"{HOME}/skills/s.md",
                "2026-08-03T03:00:00+00:00",
                command="insight\n## Forged Heading",
            )
        ]
        rendered = vlaj.format_reading(_reading(records))
        assert "\n## Forged Heading" not in rendered
        assert "## Forged Heading" in rendered.replace("\\|", "|")

    def test_a_pipe_in_a_field_cannot_forge_a_table_column(self):
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", command="a|b")]
        row_line = [
            ln for ln in vlaj.format_reading(_reading(records)).splitlines() if "a\\|b" in ln
        ]
        assert row_line, "pipe was not escaped"
        assert row_line[0].count("|") - row_line[0].count("\\|") == 6

    def test_an_overlong_field_is_capped(self):
        records = [_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", command="x" * 500)]
        rendered = vlaj.format_reading(_reading(records))
        assert "x" * 500 not in rendered
        assert "…" in rendered


class TestCapsAndCountsAreDeclared:
    def test_truncation_is_stated_never_silent(self):
        records = [
            _record(f"{HOME}/skills/s{i}.md", f"2026-08-03T03:00:{i:02d}+00:00") for i in range(5)
        ]
        reading = _reading(records, top=2)
        assert len(reading.rows) == 2
        assert reading.approved == 5, "the tally counts every match, not just the shown ones"
        assert "3 further record(s) not shown" in vlaj.format_reading(reading)

    def test_the_cap_reserves_the_approved_rows(self):
        """The rows that answer the question survive truncation.

        Observed on the live log: a skills week is ~110 rows dominated by
        same-second ``staged`` batches, so a head-of-list slice showed 25
        staged rows and hid all 8 approved ones — while the prompt asks B to
        cite an approving row's ``ts`` and ``content_hash``.
        """
        records = [
            _record(f"{HOME}/skills/s{i}.md", f"2026-08-03T03:00:{i:02d}+00:00", decision="staged")
            for i in range(30)
        ]
        records.append(
            _record(
                f"{HOME}/skills/approved.md",
                "2026-08-03T03:59:00+00:00",
                content_hash="APPROVEDHASH0001",
            )
        )
        reading = _reading(records, top=5, changed=True)
        rendered = vlaj.format_reading(reading)
        assert "APPROVEDHASH0001" in rendered
        assert len(reading.rows) == 5
        assert "26 further record(s) not shown" in rendered
        # The shown set still reads as a timeline, not approved-first.
        assert [row.ts for row in reading.rows] == sorted(row.ts for row in reading.rows)

    def test_unparsable_lines_are_counted_in_the_render(self):
        reading = _reading([], changed=False, unparsable=2)
        assert "2 audit line(s) unparsable" in vlaj.format_reading(reading)

    def test_same_second_rows_sort_without_raising(self):
        records = [
            _record(f"{HOME}/skills/b.md", "2026-08-03T03:00:00+00:00", command="zzz"),
            _record(f"{HOME}/skills/a.md", "2026-08-03T03:00:00+00:00", command="aaa"),
        ]
        reading = _reading(records)
        assert [row.command for row in reading.rows] == ["aaa", "zzz"]


class TestUnavailableIsNotTheAlarm:
    def test_missing_audit_log_renders_a_reason_code(self, tmp_path):
        result = _run_cli(tmp_path / "absent.jsonl", "--diff", "changed")
        assert result.returncode == 0, result.stderr
        assert "unavailable (reason=audit-log-missing)" in result.stdout
        assert "NO APPROVED RECORD" not in result.stdout

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="chmod(0o000) does not block root, so the fault cannot be injected",
    )
    def test_unreadable_audit_log_renders_a_reason_code(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text("{}\n", encoding="utf-8")
        audit.chmod(0o000)
        try:
            result = _run_cli(audit, "--diff", "changed")
        finally:
            audit.chmod(0o600)
        assert result.returncode == 0, result.stderr
        assert "unavailable (reason=" in result.stdout
        assert "NO APPROVED RECORD" not in result.stdout

    def test_unparsable_window_renders_a_reason_code(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text("", encoding="utf-8")
        result = _run_cli(audit, "--diff", "changed", start="unknown")
        assert result.returncode == 0, result.stderr
        assert "unavailable (reason=window-unparsable)" in result.stdout
        assert "NO APPROVED RECORD" not in result.stdout

    def test_load_records_raises_rather_than_returning_empty(self, tmp_path):
        try:
            vlaj.load_records(tmp_path / "absent.jsonl")
        except vlaj.JoinUnavailable as exc:
            assert exc.reason == "audit-log-missing"
        else:  # pragma: no cover - the point of the test
            raise AssertionError("a missing log must not read as zero records")

    def test_malformed_lines_degrade_to_a_count(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text(
            "\n".join(
                [
                    json.dumps(_record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00")),
                    "{not json",
                    "[1, 2, 3]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        records, unparsable = vlaj.load_records(audit)
        assert len(records) == 1
        assert unparsable == 2


def _digest(text: str) -> str:
    """The hash ``cli/approval.py:161`` writes for `text`."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _live_home(tmp_path: Path, section: str, files: dict[str, str]) -> Path:
    home = tmp_path / "home"
    directory = home if section == "identity" else home / section
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (home / name).parent.mkdir(parents=True, exist_ok=True)
        (home / name).write_text(text, encoding="utf-8")
    return home


class TestLiveTextReconciliation:
    """audit.jsonl records *approvals*, not *writes* (2026-08-22 F1.2)."""

    def test_live_text_matching_an_approved_row_is_the_normal_case(self, tmp_path):
        text = "approved body\n"
        home = _live_home(tmp_path, "skills", {"skills/s.md": text})
        records = [
            _record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", content_hash=_digest(text))
        ]
        rendered = vlaj.format_reading(
            _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "1 live file(s) hashed, 1 match an approved row" in rendered
        assert "match NO approved row" not in rendered
        assert "no live file carrying that hash" not in rendered

    def test_a_hand_repaired_file_matches_no_approved_row(self, tmp_path):
        """The state the tally cannot see.

        An approval row exists for the section (so the row-count alarm stays
        silent), but the bytes the runtime reads are not the approved ones —
        a hand edit, a restore, or an out-of-band write.
        """
        home = _live_home(tmp_path, "identity", {"identity.md": "hand-typed replacement\n"})
        records = [
            _record(
                f"{HOME}/identity.md",
                "2026-08-03T03:00:00+00:00",
                content_hash=_digest("the text that was actually approved"),
            )
        ]
        reading = _reading(
            records, section="identity", live=vlaj.scan_live(home, "identity"), changed=True
        )
        rendered = vlaj.format_reading(reading)
        assert reading.approved == 1, "the tally reads clean — that is the whole point"
        assert "NO APPROVED RECORD" not in rendered
        assert "1 live file(s) match NO approved row" in rendered
        assert _digest("hand-typed replacement\n") in rendered

    def test_an_approved_row_with_no_live_file_is_its_own_state(self, tmp_path):
        """Approved and written, but not what the runtime reads now."""
        live_text = "the older, still-live body\n"
        home = _live_home(tmp_path, "skills", {"skills/s.md": live_text})
        records = [
            _record(
                f"{HOME}/skills/s.md",
                "2026-07-01T03:00:00+00:00",
                content_hash=_digest(live_text),
            ),
            _record(
                f"{HOME}/skills/s.md",
                "2026-08-03T03:00:00+00:00",
                content_hash=_digest("adopted somewhere the runtime does not read"),
            ),
        ]
        rendered = vlaj.format_reading(
            _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "1 approved row(s) in this window have no live file carrying that hash" in rendered
        assert "@2026-08-03T03:00:00+00:00" in rendered
        assert "match NO approved row" not in rendered, "the live bytes were approved in July"

    def test_a_pre_window_approval_still_counts_as_approved_bytes(self, tmp_path):
        """Window-scoping the live side would call every untouched file forged."""
        text = "approved long before the start commit\n"
        home = _live_home(tmp_path, "rules", {"rules/r.md": text})
        records = [
            _record(f"{HOME}/rules/r.md", "2026-05-01T03:00:00+00:00", content_hash=_digest(text))
        ]
        rendered = vlaj.format_reading(
            _reading(records, section="rules", live=vlaj.scan_live(home, "rules"), changed=False)
        )
        assert "1 match an approved row" in rendered
        assert "match NO approved row" not in rendered

    def test_the_adopt_newline_terminator_is_not_a_mismatch(self, tmp_path):
        """``adopt`` hashes the text and writes it plus a newline.

        Hashing only the bytes on disk would report every newline-terminated
        adoption as an unapproved hand edit.
        """
        text = "body without a trailing newline"
        home = _live_home(tmp_path, "skills", {"skills/s.md": text + "\n"})
        records = [
            _record(f"{HOME}/skills/s.md", "2026-08-03T03:00:00+00:00", content_hash=_digest(text))
        ]
        rendered = vlaj.format_reading(
            _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "1 match an approved row" in rendered
        assert "match NO approved row" not in rendered

    def test_a_sibling_beside_the_canonical_identity_is_not_live(self, tmp_path):
        """``identity-2.md`` is written, approved, and never read by the runtime."""
        home = _live_home(
            tmp_path,
            "identity",
            {"identity.md": "live body\n", "identity-2.md": "the adopted body\n"},
        )
        scan = vlaj.scan_live(home, "identity")
        assert len(scan.files) == 1
        assert scan.files[0].digests[0] == _digest("live body\n")

    def test_only_hashes_and_counts_are_rendered_never_content_or_names(self, tmp_path):
        home = _live_home(
            tmp_path, "skills", {"skills/SLUG-MARKER-from-a-post.md": "BODY-MARKER text\n"}
        )
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "BODY-MARKER" not in rendered
        assert "SLUG-MARKER" not in rendered
        assert "match NO approved row" in rendered

    def test_the_list_of_unmatched_digests_is_capped_not_silent(self, tmp_path):
        home = _live_home(
            tmp_path, "skills", {f"skills/s{i}.md": f"body {i}\n" for i in range(_CAP_OVERFLOW)}
        )
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert f"{_CAP_OVERFLOW} live file(s) match NO approved row" in rendered
        assert f"+{_CAP_OVERFLOW - vlaj._RECON_CAP} more" in rendered

    def test_a_never_approved_default_is_named_as_a_cause_not_a_bypass(self, tmp_path):
        """``init`` copies the template value layer in with no audit row.

        ``cli/session_cmds.py:66`` (constitution / skills / rules) and ``:88``
        (identity) write no approval record at all, so a shipped default sits
        in "matches NO approved row" permanently and benignly. Naming only
        hand repair / restore / out-of-band edit would render that steady
        state as an accusation every week.
        """
        home = _live_home(tmp_path, "constitution", {"constitution/axioms.md": "template body\n"})
        rendered = vlaj.format_reading(
            _reading(
                [],
                section="constitution",
                live=vlaj.scan_live(home, "constitution"),
                changed=False,
            )
        )
        assert "1 live file(s) match NO approved row" in rendered
        assert "contemplative-agent init" in rendered
        assert "never had a row" in rendered
        assert "RISE in it is the signal" in rendered

    def test_the_constitution_scan_declares_the_override_it_cannot_see(self, tmp_path):
        """``--constitution-dir`` redirects the runtime's read (`cli/runtime.py:105`).

        The scan hashes ``<home>/constitution`` regardless, so the assumption
        is rendered rather than left implicit. The other sections have no
        such override and must not carry the caveat.
        """
        text = "approved body\n"
        home = _live_home(tmp_path, "constitution", {"constitution/axioms.md": text})
        records = [
            _record(
                f"{HOME}/constitution/axioms.md",
                "2026-08-03T03:00:00+00:00",
                content_hash=_digest(text),
            )
        ]
        rendered = vlaj.format_reading(
            _reading(
                records,
                section="constitution",
                live=vlaj.scan_live(home, "constitution"),
                changed=True,
            )
        )
        assert "`--constitution-dir`" in rendered

        skills_home = _live_home(tmp_path / "s", "skills", {"skills/s.md": text})
        skills_rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(skills_home, "skills"), changed=True)
        )
        assert "--constitution-dir" not in skills_rendered

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="chmod(0o000) does not block root, so the fault cannot be injected",
    )
    def test_an_unreadable_live_file_degrades_to_a_count(self, tmp_path):
        text = "readable\n"
        home = _live_home(tmp_path, "skills", {"skills/a.md": text, "skills/b.md": "secret\n"})
        blocked = home / "skills" / "b.md"
        blocked.chmod(0o000)
        try:
            scan = vlaj.scan_live(home, "skills")
        finally:
            blocked.chmod(0o600)
        records = [
            _record(f"{HOME}/skills/a.md", "2026-08-03T03:00:00+00:00", content_hash=_digest(text))
        ]
        rendered = vlaj.format_reading(_reading(records, live=scan, changed=True))
        assert scan.unreadable == 1
        assert "1 live file(s) could not be hashed" in rendered


class TestReconciliationUnavailableIsNotTheAlarm:
    def test_a_missing_home_renders_a_reason_code(self, tmp_path):
        scan = vlaj.scan_live(tmp_path / "absent", "skills")
        assert scan.reason == "live-home-missing"
        rendered = vlaj.format_reading(_reading([], live=scan, changed=True))
        assert "reason=live-home-missing" in rendered
        assert "match NO approved row" not in rendered

    def test_a_missing_section_directory_renders_a_reason_code(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        scan = vlaj.scan_live(home, "skills")
        assert scan.reason == "live-dir-missing"
        assert "match NO approved row" not in vlaj.format_reading(_reading([], live=scan))

    def test_an_empty_section_directory_renders_a_reason_code(self, tmp_path):
        """Zero files hashed must not read as reconciled.

        It is also the shape a run redirected by ``--constitution-dir``
        leaves in the default tree, which this scan cannot detect.
        """
        home = _live_home(tmp_path, "constitution", {})
        scan = vlaj.scan_live(home, "constitution")
        assert scan.reason == "live-dir-empty"
        rendered = vlaj.format_reading(
            _reading([], section="constitution", live=scan, changed=True)
        )
        assert "reason=live-dir-empty" in rendered
        assert "match NO approved row" not in rendered
        assert "Every live file traces" not in rendered

    def test_a_missing_identity_file_renders_a_reason_code(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        scan = vlaj.scan_live(home, "identity")
        assert scan.reason == "live-identity-missing"
        assert "match NO approved row" not in vlaj.format_reading(
            _reading([], section="identity", live=scan)
        )

    def test_omitting_home_on_the_cli_is_declared_not_skipped(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text("", encoding="utf-8")
        result = _run_cli(audit, "--diff", "changed")
        assert result.returncode == 0, result.stderr
        assert "reason=live-home-not-given" in result.stdout
        assert "match NO approved row" not in result.stdout


def _run_cli(audit: Path, *extra: str, start: str = START) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--audit",
            str(audit),
            "--section",
            "skills",
            "--start",
            start,
            "--end",
            END,
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestCli:
    def test_end_to_end_render_over_a_real_file(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text(
            json.dumps(
                _record(
                    f"{HOME}/skills/s.md",
                    "2026-08-03T03:00:00+00:00",
                    reason="FREE-TEXT-MARKER",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        result = _run_cli(audit, "--diff", "changed")
        assert result.returncode == 0, result.stderr
        assert "**Approval provenance**" in result.stdout
        assert "abc123def4567890" in result.stdout
        assert "FREE-TEXT-MARKER" not in result.stdout

    def test_end_to_end_reconciliation_over_a_real_home(self, tmp_path):
        home = _live_home(tmp_path, "skills", {"skills/s.md": "hand-typed body\n"})
        audit = tmp_path / "audit.jsonl"
        audit.write_text(
            json.dumps(
                _record(
                    f"{HOME}/skills/s.md",
                    "2026-08-03T03:00:00+00:00",
                    content_hash=_digest("the approved body\n"),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        result = _run_cli(audit, "--diff", "changed", "--home", str(home))
        assert result.returncode == 0, result.stderr
        assert "**Live-text reconciliation**" in result.stdout
        assert "1 live file(s) match NO approved row" in result.stdout
        assert _digest("hand-typed body\n") in result.stdout
        assert "hand-typed body" not in result.stdout

    def test_timezone_naive_stamps_are_read_as_utc(self):
        parsed = vlaj.parse_ts("2026-08-03T03:00:00")
        assert parsed == datetime(2026, 8, 3, 3, 0, tzinfo=timezone.utc)


class TestReconciliationTrend:
    """The unmatched set is compared to the prior reading (2026-08-22 gate).

    The rendering said "a RISE in it is the signal" while holding no prior
    reading — the rise was left for the operator to compute by eye across
    two reports. A shipped default that never had a row also re-rendered the
    full four-causes paragraph every week, which is how a steady line stops
    being read.
    """

    def _state(self, tmp_path: Path, **sections) -> Path:
        path = tmp_path / "state.json"
        path.write_text(json.dumps(sections), encoding="utf-8")
        return path

    def test_first_reading_declares_no_prior_and_records_the_set(self, tmp_path):
        home = _live_home(tmp_path, "skills", {"skills/s.md": "template body\n"})
        state = tmp_path / "state.json"
        emit = tmp_path / "pending.json"
        trend = vlaj.read_trend(state, "skills", END, {_digest("template body\n")})
        assert trend.prior_end is None
        assert trend.reason is None
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=False), trend=trend
        )
        assert "no prior reading" in rendered
        assert "RISE in it is the signal" in rendered
        vlaj.emit_state(emit, "skills", END, {_digest("template body\n")}, trend)
        stored = json.loads(emit.read_text(encoding="utf-8"))
        assert stored["skills"]["end"] == END
        assert stored["skills"]["digests"] == [_digest("template body\n")]
        assert stored["skills"]["unchanged_since"] == END

    def test_an_unchanged_set_folds_to_one_steady_line(self, tmp_path):
        digest = _digest("template body\n")
        home = _live_home(tmp_path, "skills", {"skills/s.md": "template body\n"})
        state = self._state(
            tmp_path,
            skills={
                "end": START,
                "digests": [digest],
                "unchanged_since": "2026-07-01T00:00:00+00:00",
            },
        )
        trend = vlaj.read_trend(state, "skills", END, {digest})
        assert trend.added == 0 and trend.removed == 0
        assert trend.unchanged_since == "2026-07-01T00:00:00+00:00"
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=False), trend=trend
        )
        assert "steady" in rendered
        assert "unchanged since @2026-07-01T00:00:00+00:00" in rendered
        # The four-causes paragraph is the first reading's; a steady week does
        # not re-render it, nor does it re-list the digests.
        assert "FOUR causes" not in rendered
        assert digest not in rendered
        assert "⚠️" not in rendered.split("**Live-text reconciliation**")[1]

    def test_a_rise_names_the_delta_and_keeps_the_full_paragraph(self, tmp_path):
        old = _digest("template body\n")
        new = _digest("hand-typed body\n")
        home = _live_home(
            tmp_path,
            "skills",
            {"skills/a.md": "template body\n", "skills/b.md": "hand-typed body\n"},
        )
        state = self._state(
            tmp_path, skills={"end": START, "digests": [old], "unchanged_since": START}
        )
        trend = vlaj.read_trend(state, "skills", END, {old, new})
        assert trend.added == 1 and trend.removed == 0
        assert trend.unchanged_since is None
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=True), trend=trend
        )
        assert f"prior reading @{START}: 1" in rendered
        assert "+1 new, -0 gone" in rendered
        assert "FOUR causes" in rendered

    def test_a_rerun_of_the_same_window_compares_against_the_reading_before_it(self, tmp_path):
        digest = _digest("template body\n")
        state = self._state(
            tmp_path,
            skills={
                "end": END,
                "digests": [digest],
                "unchanged_since": END,
                "previous": {"end": START, "digests": [], "unchanged_since": None},
            },
        )
        trend = vlaj.read_trend(state, "skills", END, {digest})
        assert trend.prior_end == START
        assert trend.added == 1

    def test_an_unreadable_state_renders_a_reason_not_a_first_run(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{not json", encoding="utf-8")
        trend = vlaj.read_trend(state, "skills", END, set())
        assert trend.reason == "state-unparsable"
        home = _live_home(tmp_path, "skills", {"skills/s.md": "x\n"})
        rendered = vlaj.format_reading(
            _reading([], live=vlaj.scan_live(home, "skills"), changed=False), trend=trend
        )
        assert "trend unavailable (reason=state-unparsable)" in rendered
        assert "no prior reading" not in rendered

    def test_emit_merges_sections_into_one_pending_file(self, tmp_path):
        emit = tmp_path / "pending.json"
        vlaj.emit_state(emit, "skills", END, {"a" * 16}, vlaj.Trend())
        vlaj.emit_state(emit, "rules", END, set(), vlaj.Trend())
        stored = json.loads(emit.read_text(encoding="utf-8"))
        assert set(stored) == {"skills", "rules"}

    def test_emit_keeps_the_prior_reading_as_previous_for_reruns(self, tmp_path):
        state = self._state(tmp_path, skills={"end": START, "digests": [], "unchanged_since": None})
        emit = tmp_path / "pending.json"
        trend = vlaj.read_trend(state, "skills", END, {"a" * 16})
        vlaj.emit_state(emit, "skills", END, {"a" * 16}, trend)
        stored = json.loads(emit.read_text(encoding="utf-8"))
        assert stored["skills"]["previous"]["end"] == START

    def test_cli_wires_state_and_emit(self, tmp_path):
        home = _live_home(tmp_path, "skills", {"skills/s.md": "template body\n"})
        audit = tmp_path / "audit.jsonl"
        audit.write_text("", encoding="utf-8")
        state = tmp_path / "state.json"
        emit = tmp_path / "pending.json"
        result = _run_cli(
            audit,
            "--diff",
            "unchanged",
            "--home",
            str(home),
            "--state",
            str(state),
            "--emit-state",
            str(emit),
        )
        assert result.returncode == 0, result.stderr
        assert "no prior reading" in result.stdout
        assert emit.is_file() and not state.exists()
        # Promote as last week's baseline, re-run: steady.
        stored = json.loads(emit.read_text(encoding="utf-8"))
        stored["skills"]["end"] = START
        state.write_text(json.dumps(stored), encoding="utf-8")
        result = _run_cli(
            audit,
            "--diff",
            "unchanged",
            "--home",
            str(home),
            "--state",
            str(state),
            "--emit-state",
            str(emit),
        )
        assert result.returncode == 0, result.stderr
        assert "steady" in result.stdout
        assert "FOUR causes" not in result.stdout


class TestTrendBaselineIsNotReset:
    """Review 2026-08-22: promotion replaces the whole baseline file."""

    def test_an_abstaining_section_carries_its_prior_entry_forward(self, tmp_path):
        """A section that writes nothing this week (live-dir-empty) must not
        read as a first reading next week."""
        state = tmp_path / "state.json"
        state.write_text(
            json.dumps(
                {
                    "rules": {"end": START, "digests": ["a" * 16], "unchanged_since": START},
                    "skills": {"end": START, "digests": [], "unchanged_since": START},
                }
            ),
            encoding="utf-8",
        )
        emit = tmp_path / "pending.json"
        trend = vlaj.read_trend(state, "skills", END, set())
        vlaj.emit_state(emit, "skills", END, set(), trend, state_path=state)
        stored = json.loads(emit.read_text(encoding="utf-8"))
        assert stored["rules"] == {"end": START, "digests": ["a" * 16], "unchanged_since": START}
        assert stored["skills"]["end"] == END

    def test_a_corrupt_pending_file_is_refused_not_replaced(self, tmp_path):
        emit = tmp_path / "pending.json"
        emit.write_text("{not json", encoding="utf-8")
        with pytest.raises(vlaj.JoinUnavailable) as exc:
            vlaj.emit_state(emit, "skills", END, set(), vlaj.Trend())
        assert exc.value.reason == "pending-unparsable"
        assert emit.read_text(encoding="utf-8") == "{not json"

    def test_cli_reports_a_refused_write_after_the_reading(self, tmp_path):
        home = _live_home(tmp_path, "skills", {"skills/s.md": "x\n"})
        audit = tmp_path / "audit.jsonl"
        audit.write_text("", encoding="utf-8")
        emit = tmp_path / "pending.json"
        emit.write_text("[]", encoding="utf-8")
        result = _run_cli(
            audit, "--diff", "unchanged", "--home", str(home), "--emit-state", str(emit)
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.rstrip().endswith(
            "(trend state not written: reason=pending-unparsable)"
        )
        assert emit.read_text(encoding="utf-8") == "[]"

    def test_previous_keeps_the_prior_entrys_own_unchanged_since(self, tmp_path):
        state = tmp_path / "state.json"
        old_since = "2026-07-01T00:00:00+00:00"
        state.write_text(
            json.dumps(
                {"skills": {"end": START, "digests": ["a" * 16], "unchanged_since": old_since}}
            ),
            encoding="utf-8",
        )
        emit = tmp_path / "pending.json"
        # The set changed this week, so this reading's unchanged_since resets…
        trend = vlaj.read_trend(state, "skills", END, {"b" * 16})
        assert trend.unchanged_since is None
        vlaj.emit_state(emit, "skills", END, {"b" * 16}, trend, state_path=state)
        stored = json.loads(emit.read_text(encoding="utf-8"))
        # …but the prior entry's own history is carried, so a re-run of this
        # window that lands back on the old set reports the true date.
        assert stored["skills"]["previous"]["unchanged_since"] == old_since
        emit.rename(state)
        rerun = vlaj.read_trend(state, "skills", END, {"a" * 16})
        assert rerun.unchanged_since == old_since


class TestArchiveExitIsNotAnOrphan:
    """A retirement into ``skills/.archive/`` is a gated write, not a defect.

    ADR-0097 Decision 5 turns retirement into a *move*, so from the window's
    audit log a retired skill looks exactly like the third state this join
    was built to raise: an approved row whose bytes are not live. Left
    unhandled, the exit would fire that alarm at every gate — and the alarm's
    own cause list offers three explanations, none of which is "retired".
    """

    def test_a_retirement_is_counted_apart_and_kept_out_of_the_orphan_set(self, tmp_path):
        retired = "retired body\n"
        live = "live body\n"
        home = _live_home(tmp_path, "skills", {"skills/kept.md": live})
        records = [
            _record(
                f"{HOME}/skills/kept.md",
                "2026-08-03T03:00:00+00:00",
                content_hash=_digest(live),
            ),
            _record(
                f"{HOME}/skills/.archive/gone.md",
                "2026-08-03T04:00:00+00:00",
                command="remove-skill",
                content_hash=_digest(retired),
            ),
        ]
        reading = _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        # Still a skills-section approval — the gate approved it.
        assert reading.approved == 2
        assert reading.archived == 1
        rendered = vlaj.format_reading(reading)
        assert "1 of the approved row(s) wrote under `skills/.archive/`" in rendered
        assert "1 retirement(s)" in rendered
        assert "purge" not in rendered.split("Retirement and purge")[0]
        # The alarm this exit would otherwise manufacture every week.
        assert "no live file carrying that hash" not in rendered

    def test_without_the_carve_out_the_row_would_read_as_an_orphan(self, tmp_path):
        """Pins the mechanism, not just the outcome.

        The same bytes under ``skills/`` — a real approved-but-not-live row —
        must still raise the warning, so the test cannot pass by the
        reconciliation having been disabled.
        """
        gone = "vanished body\n"
        home = _live_home(tmp_path, "skills", {"skills/kept.md": "live body\n"})
        records = [
            _record(
                f"{HOME}/skills/gone.md",
                "2026-08-03T04:00:00+00:00",
                content_hash=_digest(gone),
            )
        ]
        rendered = vlaj.format_reading(
            _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "no live file carrying that hash" in rendered
        assert "wrote under `skills/.archive/`" not in rendered

    def test_a_retirement_still_answers_the_no_approved_record_alarm(self, tmp_path):
        """An archive-only week shows a diff (the deletion) and must not alarm."""
        home = _live_home(tmp_path, "skills", {"skills/kept.md": "live body\n"})
        records = [
            _record(
                f"{HOME}/skills/.archive/gone.md",
                "2026-08-03T04:00:00+00:00",
                command="remove-skill",
                content_hash=_digest("retired body\n"),
            )
        ]
        rendered = vlaj.format_reading(
            _reading(records, live=vlaj.scan_live(home, "skills"), changed=True)
        )
        assert "NO APPROVED RECORD" not in rendered

    def test_the_top_cap_reserves_retirements_after_the_other_approvals(self):
        """The diff above the table no longer shows archives; the header counts them."""
        records = [
            _record(
                f"{HOME}/skills/.archive/gone-{i}.md",
                f"2026-08-03T0{i}:00:00+00:00",
                command="remove-skill",
            )
            for i in range(1, 4)
        ]
        records.append(_record(f"{HOME}/skills/adopted.md", "2026-08-03T09:00:00+00:00"))
        reading = _reading(records, top=1)
        assert [row.command for row in reading.rows] == ["insight"]
        assert reading.truncated == 3

    def test_a_purge_is_separated_from_a_retirement_by_source_not_by_path(self):
        """Both write under `.archive/`; only `source` says which happened."""
        records = [
            _record(
                f"{HOME}/skills/.archive/gone.md",
                "2026-08-03T04:00:00+00:00",
                command="remove-skill",
                source="direct-archive",
            ),
            _record(
                f"{HOME}/skills/.archive/old.md",
                "2026-08-03T05:00:00+00:00",
                command="remove-skill",
                source="direct-purge-auto",
            ),
        ]
        reading = _reading(records)
        assert (reading.archived, reading.purged) == (2, 1)
        rendered = vlaj.format_reading(reading)
        assert "1 retirement(s) and 1 purge(s) of an already-retired file" in rendered

    def test_an_archive_row_outside_a_known_section_is_still_unplaced(self):
        """The predicate must not rescue a path no section claims."""
        reading = _reading(
            [_record(f"{HOME}/notes/.archive/x.md", "2026-08-03T03:00:00+00:00")],
            changed=False,
        )
        assert reading.archived == 0
        assert reading.unmatched == 1
