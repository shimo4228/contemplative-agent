"""Tests for scripts/value_layer_due_check.py (value-layer cadence instrument).

The instrument is a read-only reading over the ADR-0012 approval audit log
(``logs/audit.jsonl``), ``knowledge.json`` and the staging dir: how long since
the last identity distillation ran, how long since the last constitution
amendment was adopted, and whether staging currently holds an unreviewed
batch (ADR-0074).  The weekly pipeline uses the reading to trigger the
monthly identity staging and to surface "amendment due" in the Saturday
packet; it must never guess when its inputs are absent.

Fault column (ADR-0077): a missing or unreadable audit log abstains nonzero
with a reason code — an unknown state must never read as "identity due" and
fire an LLM run.  Partial faults (malformed lines, missing knowledge.json)
degrade to counted reasons while the rest of the reading stays live.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import value_layer_due_check as vldc  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "value_layer_due_check.py"

AS_OF = "2026-08-09"


def _audit_line(command: str, ts: str, decision: str = "approved", **extra) -> str:
    return json.dumps({"ts": ts, "command": command, "decision": decision, **extra})


def _write_inputs(
    tmp_path: Path,
    *,
    audit_lines: list[str] | None,
    patterns: list[dict] | None = None,
    staged_metas: int = 0,
) -> dict[str, Path]:
    paths = {
        "audit": tmp_path / "audit.jsonl",
        "knowledge": tmp_path / "knowledge.json",
        "staged": tmp_path / ".staged",
    }
    if audit_lines is not None:
        paths["audit"].write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    if patterns is not None:
        paths["knowledge"].write_text(json.dumps(patterns), encoding="utf-8")
    paths["staged"].mkdir()
    for i in range(staged_metas):
        (paths["staged"] / f"item-{i}.md").write_text("body\n", encoding="utf-8")
        (paths["staged"] / f"item-{i}.md.meta.json").write_text("{}\n", encoding="utf-8")
    return paths


def _run(paths: dict[str, Path], *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--audit",
            str(paths["audit"]),
            "--knowledge",
            str(paths["knowledge"]),
            "--staged-dir",
            str(paths["staged"]),
            "--as-of",
            AS_OF,
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _reading(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- Identity cadence ---


def test_identity_due_after_interval() -> None:
    """51 days since the last distill-identity run (any decision) → due."""
    reading = vldc.build_reading(
        audit_records=[
            {"ts": "2026-06-19T02:08:23+00:00", "command": "distill-identity", "decision": "staged"}
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is True
    assert reading["identity"]["reason"] == "INTERVAL_ELAPSED"
    assert reading["identity"]["days_since"] == 51
    assert reading["identity"]["last_run_ts"] == "2026-06-19T02:08:23+00:00"


def test_identity_not_due_within_interval() -> None:
    reading = vldc.build_reading(
        audit_records=[
            {
                "ts": "2026-08-01T02:08:23+00:00",
                "command": "distill-identity",
                "decision": "rejected",
            }
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is False
    assert reading["identity"]["reason"] == "NOT_DUE"
    assert reading["identity"]["days_since"] == 8


def test_identity_no_prior_run_is_due() -> None:
    """Bootstrap: a live audit log (other records exist) with no identity
    run is immediately due."""
    reading = vldc.build_reading(
        audit_records=[
            {"ts": "2026-08-01T00:00:00+00:00", "command": "insight", "decision": "staged"}
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is True
    assert reading["identity"]["reason"] == "NO_PRIOR_RUN"
    assert reading["identity"]["last_run_ts"] is None
    assert reading["identity"]["days_since"] is None


def test_empty_audit_is_truncation_not_bootstrap() -> None:
    """Zero readable records = truncation/corruption (a fresh home has no
    audit.jsonl at all and abstains upstream) — never fires a run."""
    reading = vldc.build_reading(
        audit_records=[],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is False
    assert reading["identity"]["reason"] == "NO_AUDIT_RECORDS"
    assert "NO_AUDIT_RECORDS" in reading["reasons"]


def test_future_timestamp_is_named_not_not_due() -> None:
    """A record dated after as-of is clock skew or a doctored log — fails
    safe and is loud (propagated via reasons for the packet header)."""
    reading = vldc.build_reading(
        audit_records=[
            {"ts": "9999-12-31T00:00:00+00:00", "command": "distill-identity", "decision": "staged"}
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is False
    assert reading["identity"]["reason"] == "FUTURE_TIMESTAMP"
    assert "FUTURE_TIMESTAMP" in reading["reasons"]


def test_non_utc_offset_normalized_before_day_arithmetic() -> None:
    """+09:00 and its UTC equivalent must yield the same days_since — the
    .date() boundary is taken in UTC, not the record's own offset."""
    for ts in ("2026-07-13T02:00:00+09:00", "2026-07-12T17:00:00+00:00"):
        reading = vldc.build_reading(
            audit_records=[{"ts": ts, "command": "distill-identity", "decision": "staged"}],
            patterns=[],
            staging_pending=0,
            as_of="2026-08-09",
            identity_interval_days=28,
            amendment_interval_days=84,
        )
        assert reading["identity"]["days_since"] == 28, ts
        assert reading["identity"]["due"] is True, ts


def test_patterns_loader_is_lazy() -> None:
    """knowledge.json is >100 MB in production — the loader must not fire
    when no adoption baseline exists (security review 2026-08-10 M3)."""
    calls: list[int] = []

    def loader() -> list[dict]:
        calls.append(1)
        return []

    vldc.build_reading(
        audit_records=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
        patterns_loader=loader,
    )
    assert calls == []

    reading = vldc.build_reading(
        audit_records=[
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "command": "amend-constitution",
                "decision": "approved",
            }
        ],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
        patterns_loader=loader,
    )
    assert calls == [1]
    assert reading["constitution"]["patterns_since"] == 0


def test_identity_legacy_command_name_and_timestamp_key() -> None:
    """Pre-2026-04 records use command="distill-identity-ca" and key "timestamp"."""
    reading = vldc.build_reading(
        audit_records=[
            {
                "timestamp": "2026-07-29T10:53:36+00:00",
                "command": "distill-identity-ca",
                "decision": "approved",
            }
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["last_run_ts"] == "2026-07-29T10:53:36+00:00"
    assert reading["identity"]["due"] is False


def test_identity_takes_latest_of_multiple_records() -> None:
    reading = vldc.build_reading(
        audit_records=[
            {
                "ts": "2026-03-01T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "staged",
            },
            {
                "ts": "2026-08-05T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "approved",
            },
            {
                "ts": "2026-05-01T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "staged",
            },
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["last_run_ts"] == "2026-08-05T00:00:00+00:00"
    assert reading["identity"]["due"] is False


# --- Constitution cadence ---


def test_constitution_due_after_interval_counts_patterns_since() -> None:
    reading = vldc.build_reading(
        audit_records=[
            {
                "ts": "2026-05-05T01:34:23+00:00",
                "command": "amend-constitution",
                "decision": "approved",
            },
            # staged-only records are proposals, not adoptions — must not move the clock
            {
                "ts": "2026-08-01T05:31:51+00:00",
                "command": "amend-constitution",
                "decision": "staged",
            },
        ],
        patterns=[
            {"pattern": "old", "distilled": "2026-04-01T00:00+00:00"},
            {"pattern": "new-1", "distilled": "2026-06-01T00:00+00:00"},
            {"pattern": "new-2", "distilled": "2026-07-15T00:00+00:00"},
        ],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["constitution"]["due"] is True
    assert reading["constitution"]["reason"] == "INTERVAL_ELAPSED"
    assert reading["constitution"]["days_since"] == 96
    assert reading["constitution"]["last_adopted_ts"] == "2026-05-05T01:34:23+00:00"
    assert reading["constitution"]["patterns_since"] == 2


def test_constitution_not_due_within_interval() -> None:
    reading = vldc.build_reading(
        audit_records=[
            {
                "ts": "2026-08-09T12:10:35+00:00",
                "command": "amend-constitution",
                "decision": "approved",
            }
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["constitution"]["due"] is False
    assert reading["constitution"]["reason"] == "NOT_DUE"


def test_constitution_no_prior_adoption_is_not_due() -> None:
    """No baseline → no cadence claim. A first amendment is a deliberate
    human decision, not something the instrument should nudge."""
    reading = vldc.build_reading(
        audit_records=[],
        patterns=[{"pattern": "p", "distilled": "2026-06-01T00:00+00:00"}],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["constitution"]["due"] is False
    assert reading["constitution"]["reason"] == "NO_PRIOR_ADOPTION"
    assert reading["constitution"]["patterns_since"] is None


# --- Staging / partial faults ---


def test_staging_pending_counts_meta_sidecars(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-05T00:00:00+00:00")],
        patterns=[],
        staged_metas=2,
    )
    reading = _reading(_run(paths))
    assert reading["staging_pending"] == 2


def test_staging_dir_missing_reads_as_zero(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path, audit_lines=[], patterns=[])
    paths["staged"] = tmp_path / "no-such-dir"
    reading = _reading(_run(paths))
    assert reading["staging_pending"] == 0


def test_malformed_audit_lines_counted_not_fatal(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        audit_lines=[
            "{not json",
            '"a bare string"',
            _audit_line("distill-identity", "2026-08-05T00:00:00+00:00"),
            json.dumps({"ts": "not-a-timestamp", "command": "distill-identity"}),
        ],
        patterns=[],
    )
    reading = _reading(_run(paths))
    assert reading["identity"]["last_run_ts"] == "2026-08-05T00:00:00+00:00"
    assert reading["malformed_audit_lines"] == 3
    assert "AUDIT_PARTIAL_PARSE" in reading["reasons"]


def test_knowledge_missing_degrades_patterns_since_only(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("amend-constitution", "2026-01-01T00:00:00+00:00")],
        patterns=None,
    )
    reading = _reading(_run(paths))
    assert reading["constitution"]["due"] is True
    assert reading["constitution"]["patterns_since"] is None
    assert "KNOWLEDGE_UNAVAILABLE" in reading["reasons"]


# --- Abstain (nonzero) faults ---


def test_audit_missing_abstains_nonzero(tmp_path: Path) -> None:
    """No audit log → no reading. Must never default to "due" and fire a run."""
    paths = _write_inputs(tmp_path, audit_lines=None, patterns=[])
    proc = _run(paths)
    # Exit 2 is the abstain contract; exit 1 would be an uncaught traceback
    # (the failure mode the fault column exists to pin).
    assert proc.returncode == 2
    assert "AUDIT_MISSING" in proc.stderr


def test_bad_as_of_abstains_nonzero(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path, audit_lines=[], patterns=[])
    proc = _run(paths, "--as-of", "not-a-date")
    assert proc.returncode == 2
    assert "BAD_AS_OF" in proc.stderr


def test_bad_interval_abstains_nonzero(tmp_path: Path) -> None:
    """A zero interval = permanently due = an unattended run every week."""
    paths = _write_inputs(tmp_path, audit_lines=[], patterns=[])
    proc = _run(paths, "--identity-interval-days", "0")
    assert proc.returncode == 2
    assert "BAD_INTERVAL" in proc.stderr


def test_non_utf8_audit_abstains_not_traceback(tmp_path: Path) -> None:
    """UnicodeDecodeError is a ValueError, not an OSError — the historical
    packet-builder gap (2026-07-29) must not recur here."""
    paths = _write_inputs(tmp_path, audit_lines=[], patterns=[])
    paths["audit"].write_bytes(b'{"ts": "\xff\xfe"}\n')
    proc = _run(paths)
    assert proc.returncode == 2
    assert "AUDIT_UNREADABLE" in proc.stderr


def test_non_utf8_knowledge_degrades_not_crashes(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("amend-constitution", "2026-01-01T00:00:00+00:00")],
        patterns=[],
    )
    paths["knowledge"].write_bytes(b"\xff\xfe not json")
    reading = _reading(_run(paths))
    assert reading["constitution"]["patterns_since"] is None
    assert "KNOWLEDGE_UNAVAILABLE" in reading["reasons"]


# --- CLI end-to-end happy path (real files, matches pipeline call shape) ---


def test_cli_end_to_end(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        audit_lines=[
            _audit_line("distill-identity", "2026-06-20T02:08:23+00:00", decision="staged"),
            _audit_line("amend-constitution", "2026-05-05T01:34:23+00:00"),
        ],
        patterns=[{"pattern": "p", "distilled": "2026-06-01T00:00+00:00"}],
        staged_metas=1,
    )
    reading = _reading(_run(paths))
    assert reading["as_of"] == AS_OF
    assert reading["identity"]["due"] is True
    assert reading["constitution"]["due"] is True
    assert reading["staging_pending"] == 1
    # Defaults are 27/83, not 28/84: --as-of lags the run day by one, so
    # these anchor the cadence at exactly 4 / 12 weeks of Saturday runs.
    assert reading["identity"]["interval_days"] == 27
    assert reading["constitution"]["interval_days"] == 83


def test_unparsable_identity_history_abstains_from_due() -> None:
    """Matching records with no parseable timestamp = unknown history, not
    absent history — must never read as due (codex review 2026-08-10 P2)."""
    reading = vldc.build_reading(
        audit_records=[
            {"ts": "not-a-timestamp", "command": "distill-identity", "decision": "staged"},
            {"command": "distill-identity", "decision": "approved"},  # no ts at all
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["identity"]["due"] is False
    assert reading["identity"]["reason"] == "UNPARSABLE_HISTORY"
    assert reading["identity"]["last_run_ts"] is None
    assert reading["malformed_audit_lines"] == 2


def test_unparsable_amendment_history_named_distinctly() -> None:
    reading = vldc.build_reading(
        audit_records=[
            {"ts": "garbage", "command": "amend-constitution", "decision": "approved"},
        ],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=28,
        amendment_interval_days=84,
    )
    assert reading["constitution"]["due"] is False
    assert reading["constitution"]["reason"] == "UNPARSABLE_HISTORY"
