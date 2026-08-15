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

Fault column (ADR-0077): a missing or unreadable audit log renders an
explicit ``unavailable (reason=…)`` line. An unavailable instrument that
rendered as "no approval record" would manufacture the exact false alarm
this finding set out to make impossible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import value_layer_approval_join as vlaj  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "value_layer_approval_join.py"

HOME = "/Users/someone/.config/moltbook"
START = "2026-08-01T23:00:00+09:00"
END = "2026-08-08T23:00:00+09:00"


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


def _reading(records, *, section="skills", changed=True, top=vlaj._DEFAULT_TOP, unparsable=0):
    return vlaj.build_reading(
        records,
        section=section,
        changed=changed,
        start=_ts(START),
        end=_ts(END),
        unparsable=unparsable,
        top=top,
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

    def test_timezone_naive_stamps_are_read_as_utc(self):
        parsed = vlaj.parse_ts("2026-08-03T03:00:00")
        assert parsed == datetime(2026, 8, 3, 3, 0, tzinfo=timezone.utc)
