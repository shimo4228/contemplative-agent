"""Tests for scripts/instrument_census.py — every self-written log gets a reader (ADR-0107)."""

from __future__ import annotations

import base64
import builtins
import json
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import instrument_census as ic  # type: ignore[import-not-found]  # noqa: E402

START = date(2026, 9, 5)
END = date(2026, 9, 11)
IN = "2026-09-08T10:00:00+00:00"
OUT = "2026-08-01T10:00:00+00:00"


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


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


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "moltbook"
    (h / "logs").mkdir(parents=True)
    return h


def _by_name(readings, name):
    return next(r for r in readings if r.name == name)


class TestStatus:
    def test_registered_file_with_rows_is_ok(self, home):
        _write(home / "logs" / "llm-calls-2026-09-08.jsonl", [_llm("a", "d1", "s1")])
        r = _by_name(
            ic.census(home / "logs", START, END, sample_n=5, seed="x"), "llm-calls-*.jsonl"
        )
        assert r.status == ic.OK
        assert r.rows == 1 and r.sessions == 1 and r.files == 1

    def test_live_entry_with_no_rows_in_window_is_no_rows(self, home):
        _write(home / "logs" / "verification-audit.jsonl", [{"ts": OUT, "solve_success": True}])
        r = _by_name(
            ic.census(home / "logs", START, END, sample_n=5, seed="x"), "verification-audit.jsonl"
        )
        assert r.status == ic.NO_ROWS
        assert r.rows_out_of_window == 1

    def test_missing_heartbeat_event_is_named(self, home):
        _write(
            home / "logs" / "injection-detect-2026-09-08.jsonl",
            [{"ts": IN, "event": "injection_tokens_removed", "total_removed": 1}],
        )
        r = _by_name(
            ic.census(home / "logs", START, END, sample_n=0, seed="x"), "injection-detect-*.jsonl"
        )
        assert r.status == ic.MISSING_EVENT

    def test_retired_writer_with_file_on_disk_is_orphan(self, home):
        (home / "logs" / "insight-worth.jsonl").write_text("", encoding="utf-8")
        readings = ic.census(home / "logs", START, END, sample_n=0, seed="x")
        assert _by_name(readings, "insight-worth.jsonl").status == ic.ORPHAN
        assert _by_name(readings, "noise-*.jsonl").status == ic.ABSENT

    def test_unregistered_file_is_unknown(self, home):
        _write(home / "logs" / "brand-new-thing.jsonl", [{"ts": IN}])
        readings = ic.census(home / "logs", START, END, sample_n=0, seed="x")
        r = _by_name(readings, "brand-new-thing.jsonl")
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
        r = _by_name(
            ic.census(home / "logs", START, END, sample_n=0, seed="x"), "llm-calls-*.jsonl"
        )
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
        r = _by_name(
            ic.census(home / "logs", START, END, sample_n=0, seed="x"), "llm-calls-*.jsonl"
        )
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

        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        monkeypatch.setattr(builtins, "open", spy)
        readings = ic.census(home / "logs", START, END, sample_n=5, seed="x")
        assert all(
            "episodes" not in p and ".log" not in p and "2026-09-07" not in p for p in opened
        ), opened
        assert all(r.parse_failures == 0 for r in readings)
        # And the stray episode copy is not reported as UNKNOWN either — it is
        # the other guard's business, not a registry gap.
        assert not any(r.name == "2026-09-07.jsonl" for r in readings)

    def test_projection_strips_bodies_by_name_and_by_shape(self):
        rec = {
            "ts": IN,
            "caller": "moltbook.comment",
            "prompt_b64": base64.b64encode(b"secret").decode(),
            "prompt_sha256": "abc",
            "prompt_norm_sha256": "def",
            "prompt_chars": 4000,
            "output_b64": "zzz",
            "reason": "some explanatory text",
            "content_bytes": 12,
            "long": "x" * (ic.MAX_STR + 1),
            "nested": {"message": "hi", "count": 2},
            "tags": ["a", "b"],  # model-produced names — dropped (ADR-0083)
            "flags": [1, 0],
            "ok": True,
        }
        out = ic.strip_body(rec)
        assert set(out) == {
            "ts",
            "caller",
            "prompt_sha256",
            "prompt_norm_sha256",
            "prompt_chars",
            "content_bytes",
            "nested",
            "flags",
            "ok",
        }
        assert out["nested"] == {"count": 2}

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
        md = ic.run(home, START, END, sample_n=10)
        assert "_b64" not in md
        assert "QUJD" not in md and "REVG" not in md
        assert body[:50] not in md
        assert "## Instrument Census" in md
        assert "moltbook.comment" in md  # the enum reading survived


class TestRender:
    def test_non_ok_rows_are_summarized_up_front(self, home):
        _write(home / "logs" / "mystery.jsonl", [{"ts": IN}])
        md = ic.run(home, START, END, sample_n=0)
        first_para = md.split("| Status |")[0]
        assert "UNKNOWN `mystery.jsonl`" in first_para
        assert "NO_ROWS" not in first_para.split("UNKNOWN")[0] or "ABSENT" in first_para

    def test_sample_is_deterministic_for_a_seed(self, home):
        rows = [_llm("c", f"d{i}", "s1", ts=f"2026-09-08T10:{i:02d}:00+00:00") for i in range(40)]
        _write(home / "logs" / "llm-calls-2026-09-08.jsonl", rows)
        a = ic.run(home, START, END, sample_n=5)
        b = ic.run(home, START, END, sample_n=5)
        assert a == b

    def test_main_never_fails_the_caller(self, tmp_path, capsys):
        rc = ic.main(
            ["--home", str(tmp_path / "nowhere"), "--start", "2026-09-05", "--end", "2026-09-11"]
        )
        assert rc == 0
        assert "## Instrument Census" in capsys.readouterr().out
