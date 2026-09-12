"""Tests for scripts/instrument_census.py — every self-written log gets a reader.

ADR-0107 built the census; ADR-0110 replaced its 30-row random sample with a
session ledger, a run-length trace, per-minute strips, id-field repeats,
within-week outliers and collapsed hunting windows. The fixtures here use
invented category names on purpose: the projection must not know the name of
any endpoint or caller that happens to be broken this month.
"""

from __future__ import annotations

import base64
import builtins
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import instrument_census as ic  # type: ignore[import-not-found]  # noqa: E402

START = date(2026, 9, 5)
END = date(2026, 9, 11)
IN = "2026-09-08T10:00:00+00:00"
OUT = "2026-08-01T10:00:00+00:00"
PAST = "2026-08-20T10:00:00+00:00"  # inside the previous-4-weeks vocabulary window

# Invented category names — the implementation must not special-case them.
CAT_A = "GET /alpha"
CAT_B = "GET /beta"
BURST = "GET /gamma"


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _append(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _llm(caller: str, digest: str, session: str, ts: str = IN, **extra) -> dict:
    row = {
        "ts": ts,
        "caller": caller,
        "prompt_norm_sha256": digest,
        "prompt_sha256": "raw" + digest,
        "outcome": "ok",
        "duration_ms": 100,
        "session_id": session,
    }
    row.update(extra)
    return row


def _api(endpoint: str, session: str, ts: str, **extra) -> dict:
    row = {
        "ts": ts,
        "method": endpoint.split(" ")[0],
        "endpoint": endpoint,
        "status": 200,
        "rate_remaining": 55,
        "session_id": session,
    }
    row.update(extra)
    return row


def _at(day: int, minute: int, second: int = 0) -> str:
    """A timestamp inside the window: 2026-09-0{day} 10:{minute}:{second}Z."""
    base = datetime(2026, 9, day, 10, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minute, seconds=second)).isoformat()


def _healthy_week(home: Path, n_sessions: int = 28, cats=(CAT_A, CAT_B)) -> list[str]:
    """``n_sessions`` identically shaped sessions, one per hour-long slot.

    Each session emits every category in ``cats`` six times, ten minutes apart,
    into api-audit, plus one llm-calls row. Returns the session ids in order.
    """
    sids = []
    api_rows: list[dict] = []
    llm_rows: list[dict] = []
    for i in range(n_sessions):
        sid = f"s{i:02d}0000"
        sids.append(sid)
        day = 5 + i % 7
        for step in range(6):
            for cat in cats:
                api_rows.append(_api(cat, sid, _at(day, step * 10)))
        llm_rows.append(_llm("mod.judge", f"d{i}", sid, ts=_at(day, 5)))
    _write(home / "logs" / "api-audit.jsonl", api_rows)
    _write(home / "logs" / "llm-calls-2026-09-08.jsonl", llm_rows)
    return sids


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "moltbook"
    (h / "logs").mkdir(parents=True)
    return h


def _by_name(readings, name):
    return next(r for r in readings if r.name == name)


def _section(md: str, heading: str) -> str:
    """The text under ``### {heading}...`` up to the next ``###``."""
    parts = md.split("\n### ")
    for p in parts[1:]:
        if p.startswith(heading):
            return p
    raise AssertionError(f"section {heading!r} not found in:\n{md}")


class TestStatus:
    def test_registered_file_with_rows_is_ok(self, home):
        _write(home / "logs" / "llm-calls-2026-09-08.jsonl", [_llm("a", "d1", "s1")])
        r = _by_name(ic.census(home / "logs", START, END), "llm-calls-*.jsonl")
        assert r.status == ic.OK
        assert r.rows == 1 and r.sessions == 1 and r.files == 1

    def test_live_entry_with_no_rows_in_window_is_no_rows(self, home):
        _write(home / "logs" / "verification-audit.jsonl", [{"ts": OUT, "solve_success": True}])
        r = _by_name(ic.census(home / "logs", START, END), "verification-audit.jsonl")
        assert r.status == ic.NO_ROWS
        assert r.rows_out_of_window == 1

    def test_missing_heartbeat_event_is_named(self, home):
        _write(
            home / "logs" / "injection-detect-2026-09-08.jsonl",
            [{"ts": IN, "event": "injection_tokens_removed", "total_removed": 1}],
        )
        r = _by_name(ic.census(home / "logs", START, END), "injection-detect-*.jsonl")
        assert r.status == ic.MISSING_EVENT

    def test_retired_writer_with_file_on_disk_is_orphan(self, home):
        (home / "logs" / "insight-worth.jsonl").write_text("", encoding="utf-8")
        readings = ic.census(home / "logs", START, END)
        assert _by_name(readings, "insight-worth.jsonl").status == ic.ORPHAN
        assert _by_name(readings, "noise-*.jsonl").status == ic.ABSENT

    def test_unregistered_file_is_unknown(self, home):
        _write(home / "logs" / "brand-new-thing.jsonl", [{"ts": IN}])
        r = _by_name(ic.census(home / "logs", START, END), "brand-new-thing.jsonl")
        assert r.status == ic.UNKNOWN and r.entry is None

    def test_registry_globs_cover_the_known_writers(self):
        known = [
            "llm-calls-2026-09-08.jsonl",
            "constitution-shadow.jsonl",
            "injection-detect-2026-09-08.jsonl",
            "verification-audit.jsonl",
            "weekly-pipeline-audit.jsonl",
            "pipeline-metrics.jsonl",
            "insight-novelty.jsonl",
            "insight-staged.jsonl",
            "submolt-scope-2026-09-08.jsonl",
            "api-audit.jsonl",
            "audit.jsonl",
            "skill-selection-2026-09-08.jsonl",
            "comment-outcomes.jsonl",
        ]
        for name in known:
            assert any(e.matches(name) and e.status == ic.LIVE for e in ic.REGISTRY), name

    def test_registry_category_and_error_are_data(self):
        """No callable in a registry row — the row is data a human edits."""
        for e in ic.REGISTRY:
            assert e.category is None or isinstance(e.category, str)
            assert e.saturation is None or isinstance(e.saturation, str)
            for field, op, value in e.error:
                assert isinstance(field, str) and isinstance(op, str)
                assert isinstance(value, (tuple, int, float)) and not callable(value)
            assert not hasattr(e, "note")


class TestRedundancy:
    def test_counts_repeats_within_a_session_only(self, home):
        rows = [
            _llm("moltbook.score_relevance", "d1", "s1"),
            _llm("moltbook.score_relevance", "d1", "s1", outcome="ok"),
            _llm("moltbook.score_relevance", "d1", "s1", outcome="truncated_dropped"),
            _llm("moltbook.score_relevance", "d1", "s2"),  # another session — legitimate
            _llm("moltbook.internal_note", "d1", "s1"),  # different caller — different key
        ]
        _write(home / "logs" / "llm-calls-2026-09-08.jsonl", rows)
        r = _by_name(ic.census(home / "logs", START, END), "llm-calls-*.jsonl")
        assert r.redundant_keys == 1
        assert r.redundant_calls == 2
        ((sid, key), n, outcomes) = r.redundancy[0]
        assert sid == "s1" and key == ("moltbook.score_relevance", "d1") and n == 3
        assert outcomes["ok"] == 2 and outcomes["truncated_dropped"] == 1

    def test_rows_without_the_normalized_digest_are_not_counted(self, home):
        rows = [
            {"ts": IN, "caller": "x", "prompt_sha256": "raw1", "session_id": "s1"},
            {"ts": IN, "caller": "x", "prompt_sha256": "raw1", "session_id": "s1"},
        ]
        _write(home / "logs" / "llm-calls-2026-09-08.jsonl", rows)
        r = _by_name(ic.census(home / "logs", START, END), "llm-calls-*.jsonl")
        assert r.redundant_keys == 0

    def test_caller_sequence_keeps_order_as_runs(self):
        seq = ic._compress_sequence(["a", "a", "b", "a"])
        assert seq == "a ×2, b ×1, a ×1"


class TestBoundary:
    def test_episodes_and_dot_log_files_are_never_opened(self, home, monkeypatch):
        (home / "logs" / "episodes").mkdir()
        (home / "logs" / "episodes" / "2026-09-08.jsonl").write_text("not json\n", encoding="utf-8")
        (home / "logs" / "2026-09-07.jsonl").write_text(
            "not json\n", encoding="utf-8"
        )  # stray copy
        (home / "logs" / "agent-launchd.log").write_text("not json\n", encoding="utf-8")
        _write(home / "logs" / "audit.jsonl", [{"ts": IN, "decision": "approved"}])
        opened: list[str] = []
        real_open = builtins.open
        real_read_text = Path.read_text

        # Both doors, because they are different doors: Path.read_text reaches
        # io.open through the module attribute and does not pass through
        # builtins.open, so a spy on builtins alone records nothing and the
        # assertion below passes over an empty list. Verified by mutation: a
        # read of logs/episodes/ inserted into census() fails this test.
        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        def spy_read_text(self, *a, **k):
            opened.append(str(self))
            return real_read_text(self, *a, **k)

        monkeypatch.setattr(builtins, "open", spy)
        monkeypatch.setattr(Path, "read_text", spy_read_text)
        readings = ic.census(home / "logs", START, END)
        assert opened, "the spy recorded nothing — it is watching the wrong door"
        # Match on the path *below* logs/ — pytest's own tmpdir is named after
        # this test, so "episodes" and ".log" appear in every absolute path.
        logs = str(home / "logs") + "/"
        under_logs = [p.split(logs, 1)[1] for p in opened if logs in p]
        assert all(
            "episodes" not in p and ".log" not in p and "2026-09-07" not in p for p in under_logs
        ), under_logs
        assert "audit.jsonl" in under_logs  # the registered file WAS read
        assert all(r.parse_failures == 0 for r in readings)
        # And the stray episode copy is not reported as UNKNOWN either — it is
        # the other guard's business, not a registry gap.
        assert not any(r.name == "2026-09-07.jsonl" for r in readings)

    def test_body_fields_never_enter_the_frame(self, home):
        """The allowlist is the load boundary: bodies are not columns at all."""
        _write(
            home / "logs" / "llm-calls-2026-09-08.jsonl",
            [
                _llm(
                    "moltbook.comment",
                    "d1",
                    "s1",
                    prompt_b64=base64.b64encode(b"secret").decode(),
                    content="a body",
                    tags=["a", "b"],
                    reason="explanatory text",
                )
            ],
        )
        r = _by_name(ic.census(home / "logs", START, END), "llm-calls-*.jsonl")
        cols = set(r.frame.columns)
        assert {"ts", "session_id", "caller", "outcome", "duration_ms"} <= cols
        assert not any(c in cols for c in ("prompt_b64", "content", "tags", "reason"))
        assert "prompt_norm_sha256" in cols  # digests survive — they are the redundancy key

    def test_rendered_output_carries_no_bodies(self, home):
        body = "B" * 500
        _write(
            home / "logs" / "llm-calls-2026-09-08.jsonl",
            [
                _llm(
                    "moltbook.comment",
                    "d1",
                    "s1",
                    prompt_b64=base64.b64encode(body.encode()).decode(),
                )
            ],
        )
        _write(
            home / "logs" / "skill-selection-2026-09-08.jsonl",
            [
                {
                    "ts": IN,
                    "kind": "selection",
                    "verdict": "judged",
                    "prompt_b64": "QUJD",
                    "output_b64": "REVG",
                }
            ],
        )
        md = ic.run(home, START, END)
        assert "_b64" not in md
        assert "QUJD" not in md and "REVG" not in md
        assert body[:50] not in md
        assert "## Instrument Census" in md
        assert "moltbook.comment" in md  # the enum reading survived


class TestLedger:
    def test_ledger_has_one_row_per_session_and_a_median_row(self, home):
        sids = _healthy_week(home, n_sessions=5)
        md = ic.run(home, START, END)
        ledger = _section(md, "Session ledger")
        for sid in sids:
            assert sid[:8] in ledger
        assert "median" in ledger

    def test_new_category_gets_axes_without_registry_change(self, home):
        """A caller nobody registered still gets its own column."""
        _healthy_week(home, n_sessions=5)
        _append(
            home / "logs" / "llm-calls-2026-09-08.jsonl",
            [_llm("mod.brand_new_caller", "z1", "s000000", ts=_at(5, 7))],
        )
        matrix, _ = ic.session_matrix(ic.census(home / "logs", START, END))
        assert any("brand_new_caller" in c for c in matrix.columns)

    def test_session_with_no_rows_in_one_log_gets_a_zero_row(self, home):
        _healthy_week(home, n_sessions=5)
        _append(
            home / "logs" / "api-audit.jsonl",
            [_api(CAT_A, "api-only-session", _at(6, 3))],
        )
        matrix, _ = ic.session_matrix(ic.census(home / "logs", START, END))
        assert "api-only-session" in matrix.index
        llm_cols = [
            c for c in matrix.columns if c.startswith("llm-calls:") and not c.endswith("gap s")
        ]
        assert llm_cols
        assert all(matrix.loc["api-only-session", c] == 0 for c in llm_cols)
        # A gap is absent, not zero: a session with no second event has no interval.
        gap = next(c for c in matrix.columns if c.startswith("llm-calls:") and c.endswith("gap s"))
        assert pd.isna(matrix.loc["api-only-session", gap])


class TestOutliers:
    def test_burst_in_any_category_is_a_within_week_outlier(self, home):
        """One session hammers an arbitrary category — it must surface by shape.

        ``BURST`` is a fixture constant: nothing in the implementation may know
        which endpoint or caller is currently misbehaving.
        """
        sids = _healthy_week(home, n_sessions=28)
        burst_sid = sids[9]
        burst_day = 5 + 9 % 7
        # every session calls BURST twice; one session also calls it 12 times in 11s
        rows = [_api(BURST, sid, _at(5 + i % 7, 20)) for i, sid in enumerate(sids)]
        rows += [_api(BURST, sid, _at(5 + i % 7, 40)) for i, sid in enumerate(sids)]
        rows += [_api(BURST, burst_sid, _at(burst_day, 59, s)) for s in range(0, 12)]
        _append(home / "logs" / "api-audit.jsonl", rows)
        md = ic.run(home, START, END)
        out = _section(md, "Within-week outliers")
        top = [ln for ln in out.splitlines() if ln.startswith("|")][2:4]
        assert any(BURST in ln and burst_sid[:8] in ln for ln in top), out
        hunt = _section(md, "Hunting windows")
        assert f"{BURST} ×12" in hunt, hunt

    def test_absent_category_in_one_session_is_an_outlier(self, home):
        sids = _healthy_week(home, n_sessions=28)
        # Every session but one calls a further category six times; the one
        # that never calls it is a zero in a column of sixes. Six, not two:
        # on a column with no spread the scale floor is one unit, so the
        # smallest flagged departure is 3.5 × 1.4826 ≈ 5.2 units.
        rows = [
            _api("GET /everywhere", sid, _at(5 + i % 7, 30 + k))
            for i, sid in enumerate(sids)
            if i != 3
            for k in range(6)
        ]
        _append(home / "logs" / "api-audit.jsonl", rows)
        out = _section(ic.run(home, START, END), "Within-week outliers")
        assert sids[3][:8] in out
        line = next(ln for ln in out.splitlines() if sids[3][:8] in ln)
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert cells[1] == "api-audit:GET /everywhere"
        assert cells[3] == "0" and cells[4] == "6"  # value 0 against a median of 6

    def test_category_seen_last_weeks_but_absent_this_week_is_a_zero_column(self, home):
        _healthy_week(home, n_sessions=5)
        _append(
            home / "logs" / "api-audit.jsonl",
            [_api("GET /retired", "old-session", PAST)],
        )
        matrix, absent = ic.session_matrix(ic.census(home / "logs", START, END))
        col = next(c for c in matrix.columns if "GET /retired" in c)
        assert (matrix[col] == 0).all()
        assert any("GET /retired" in c for c in absent)
        out = _section(ic.run(home, START, END), "Within-week outliers")
        assert "GET /retired" in out

    def test_healthy_week_lists_no_outliers(self, home):
        _healthy_week(home, n_sessions=28)
        out = _section(ic.run(home, START, END), "Within-week outliers")
        assert "No session departed from the others" in out

    def test_mad_zero_departure_is_listed_without_infinity(self, home):
        sids = _healthy_week(home, n_sessions=28)
        _append(
            home / "logs" / "api-audit.jsonl",
            [_api(CAT_A, sids[7], _at(5 + 7 % 7, 50 + k)) for k in range(9)],
        )
        out = _section(ic.run(home, START, END), "Within-week outliers")
        assert sids[7][:8] in out
        assert "inf" not in out.lower() and "nan" not in out.lower()


class TestTraceAndStrips:
    def test_trace_keeps_within_cycle_order(self, home):
        """``H A B A B`` and ``H A A B B`` are different traces."""
        rows_ab = [
            _api("H", "s_ab", _at(5, 0)),
            _api("A", "s_ab", _at(5, 1)),
            _api("B", "s_ab", _at(5, 2)),
            _api("A", "s_ab", _at(5, 3)),
            _api("B", "s_ab", _at(5, 4)),
        ]
        rows_aabb = [
            _api("H", "s_aabb", _at(6, 0)),
            _api("A", "s_aabb", _at(6, 1)),
            _api("A", "s_aabb", _at(6, 2)),
            _api("B", "s_aabb", _at(6, 3)),
            _api("B", "s_aabb", _at(6, 4)),
        ]
        _write(home / "logs" / "api-audit.jsonl", rows_ab + rows_aabb)
        trace = _section(ic.run(home, START, END), "Session trace")
        line_ab = next(ln for ln in trace.splitlines() if "s_ab " in ln or ln.startswith("s_ab"))
        line_aabb = next(ln for ln in trace.splitlines() if "s_aabb" in ln)
        assert line_ab.split(None, 1)[1] != line_aabb.split(None, 1)[1]

    def test_trace_is_run_length_over_all_logs(self, home):
        _write(
            home / "logs" / "api-audit.jsonl",
            [_api(CAT_A, "s_mix", _at(5, 0)), _api(CAT_A, "s_mix", _at(5, 2))],
        )
        _write(
            home / "logs" / "llm-calls-2026-09-08.jsonl",
            [_llm("mod.judge", "d1", "s_mix", ts=_at(5, 1))],
        )
        trace = _section(ic.run(home, START, END), "Session trace")
        legend = trace.splitlines()
        assert any(CAT_A in ln and "mod.judge" in ln for ln in legend), trace
        line = next(ln for ln in legend if ln.startswith("s_mix"))
        # a, b, a — the llm call sits between the two api calls, so the api run
        # is broken in two: three runs, not one.
        assert line.count("×") == 3, line

    def test_strip_is_60_chars_and_peaks_at_the_burst_minute(self, home):
        rows = []
        for i in range(3):
            sid = f"strip{i}"
            rows += [_api(CAT_A, sid, _at(5 + i, m)) for m in range(0, 60, 10)]
        rows += [_api(CAT_A, "strip0", _at(5, 30, s)) for s in range(0, 20)]
        _write(home / "logs" / "api-audit.jsonl", rows)
        strips = _section(ic.run(home, START, END), "Session strips")
        lines = {
            ln.split()[0]: ln.split()[-1] for ln in strips.splitlines() if ln.startswith("strip")
        }
        assert all(len(v) == 60 for v in lines.values()), lines
        assert lines["strip0"][30] == ic._STRIP_RAMP[-1]
        assert lines["strip0"][1] == ic._STRIP_RAMP[0]
        # the scale is the week's maximum, shared by every session: the same
        # per-minute count renders as the same character everywhere.
        assert lines["strip1"][0] == lines["strip2"][0]

    def test_strip_keeps_quiet_minutes_visible_beside_a_burst(self, home):
        """A minute with rows is never the glyph the legend calls zero."""
        rows = [_api(CAT_A, "quiet", _at(5, m)) for m in range(0, 50)]
        rows += [_api(CAT_A, "loud", _at(6, 30, s)) for s in range(100)]
        rows += [_api(CAT_A, "loud", _at(6, 0))]
        _write(home / "logs" / "api-audit.jsonl", rows)
        strips = _section(ic.run(home, START, END), "Session strips")
        band = {
            ln.split()[0]: ln.split()[-1]
            for ln in strips.splitlines()
            if ln[:5] in ("quiet", "loud ")
        }
        # the loud session's own one-row minute survives the 100-row scale
        assert band["loud"][0] != ic._STRIP_RAMP[0]
        assert band["loud"][30] == ic._STRIP_RAMP[-1]
        assert band["quiet"][10] != ic._STRIP_RAMP[0]

    def test_a_log_whose_category_is_always_null_does_not_break_the_run(self, home):
        """Rows with no caller must not take the whole census down."""
        _write(
            home / "logs" / "llm-calls-2026-09-08.jsonl",
            [{"ts": _at(5, m), "session_id": "s1", "outcome": "ok"} for m in range(5)],
        )
        _write(home / "logs" / "api-audit.jsonl", [_api(CAT_A, "s1", _at(5, 1))])
        md = ic.run(home, START, END)
        assert "unavailable (reason=" not in md
        assert "### Session strips" in md

    def test_hunting_window_orders_across_midnight(self):
        """Lines carry HH:MM:SS, so the merge must sort on the real timestamps."""
        base = datetime(2026, 9, 8, 23, 59, 0, tzinfo=timezone.utc)
        late = ic.collapse_runs_dated([(base, "x")])
        early = ic.collapse_runs_dated([(base + timedelta(minutes=2), "y")])
        merged = [line for _, line in sorted(late + early, key=lambda i: i[0])]
        assert merged[0].startswith("23:59") and merged[1].startswith("00:01")

    def test_a_category_containing_a_pipe_does_not_break_the_tables(self, home):
        _healthy_week(home, n_sessions=5)
        _append(
            home / "logs" / "api-audit.jsonl",
            [_api("GET /a|b", "s000000", _at(5, 40 + k)) for k in range(3)],
        )
        md = ic.run(home, START, END)
        ledger = _section(md, "Session ledger")
        header = next(ln for ln in ledger.splitlines() if ln.startswith("| session"))
        separator = next(ln for ln in ledger.splitlines() if ln.startswith("|:---"))
        cells = lambda ln: len(re.split(r"(?<!\\)\|", ln))  # noqa: E731 — escaped pipes are data
        assert "GET /a\\|b" in header  # the value survives, escaped
        assert cells(header) == cells(separator)


class TestIdRepeats:
    def test_id_field_repeats_are_auto_discovered(self, home):
        rows = [
            _api(CAT_A, "s1", _at(5, m), foo_id="post-7") for m in range(3)
        ]  # same id three times
        rows += [_api(CAT_A, "s1", _at(5, 9), foo_id="post-8")]
        _write(home / "logs" / "api-audit.jsonl", rows)
        section = _section(ic.run(home, START, END), "Id-field repeats")
        line = next(ln for ln in section.splitlines() if "foo_id" in ln)
        assert "3" in line


class TestCollapse:
    def test_collapse_runs_same_category_within_two_seconds(self):
        base = datetime(2026, 9, 8, 15, 59, 0, tzinfo=timezone.utc)
        burst = [(base + timedelta(seconds=s), "X") for s in range(0, 12)]
        lines = ic.collapse_runs(burst)
        assert len(lines) == 1 and "X ×12 in 11s" in lines[0]
        # a gap over two seconds is not one run
        spread = [(base + timedelta(seconds=s * 5), "X") for s in range(3)]
        assert len(ic.collapse_runs(spread)) == 3
        # mixed categories are not collapsed together
        mixed = [(base + timedelta(seconds=s), "X" if s % 2 else "Y") for s in range(6)]
        assert len(ic.collapse_runs(mixed)) == 6

    def test_aggregation_matches_hand_count(self, home):
        """Five hand-counted rows: matrix cell, per-minute max, minimum gap."""
        rows = [
            _api(CAT_A, "s1", "2026-09-08T10:00:00+00:00"),
            _api(CAT_A, "s1", "2026-09-08T10:00:03+00:00"),
            _api(CAT_A, "s1", "2026-09-08T10:00:04+00:00"),
            _api(CAT_A, "s1", "2026-09-08T10:05:00+00:00"),
            _api(CAT_B, "s1", "2026-09-08T10:07:00+00:00"),
        ]
        _write(home / "logs" / "api-audit.jsonl", rows)
        matrix, _ = ic.session_matrix(ic.census(home / "logs", START, END))
        assert matrix.loc["s1", f"api-audit:{CAT_A}"] == 4
        assert matrix.loc["s1", f"api-audit:{CAT_A} /1m"] == 3
        assert matrix.loc["s1", f"api-audit:{CAT_A} gap s"] == 1.0
        assert matrix.loc["s1", f"api-audit:{CAT_B}"] == 1


class TestRender:
    def test_non_ok_rows_are_summarized_up_front(self, home):
        _write(home / "logs" / "mystery.jsonl", [{"ts": IN}])
        md = ic.run(home, START, END)
        first_para = md.split("| Status |")[0]
        assert "UNKNOWN `mystery.jsonl`" in first_para

    def test_sections_appear_in_reading_order(self, home):
        _healthy_week(home, n_sessions=4)
        md = ic.run(home, START, END)
        order = [
            "## Instrument Census",
            "### Distributions",
            "### Redundancy",
            "### Session ledger",
            "### Session trace",
            "### Session strips",
            "### Id-field repeats",
            "### Within-week outliers",
            "### Hunting windows",
        ]
        positions = [md.find(h) for h in order]
        assert all(p >= 0 for p in positions), list(zip(order, positions, strict=True))
        assert positions == sorted(positions)

    def test_output_is_deterministic(self, home):
        _healthy_week(home, n_sessions=6)
        assert ic.run(home, START, END) == ic.run(home, START, END)

    def test_main_never_fails_the_caller(self, tmp_path, capsys):
        rc = ic.main(
            ["--home", str(tmp_path / "nowhere"), "--start", "2026-09-05", "--end", "2026-09-11"]
        )
        assert rc == 0
        assert "## Instrument Census" in capsys.readouterr().out
