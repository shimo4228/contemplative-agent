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


# --- Identity cadence counts generation, not gate decisions
# (T-HELD-IDENTITY-CADENCE, owner's call 2026-08-15) ---


def _identity_reading(records: list[dict]) -> dict:
    return vldc.build_reading(
        audit_records=records,
        patterns=[],
        staging_pending=0,
        as_of="2026-08-09",
        identity_interval_days=27,
        amendment_interval_days=84,
    )["identity"]


def test_held_identity_row_does_not_advance_cadence() -> None:
    """A hold says the human did not decide — it is not a generation event.

    Before the fix the identity branch passed ``decisions=None``, so the
    ``held`` row (written at the gate, weeks after the distill ran) moved
    ``last_run_ts`` forward and deferred the next generation by exactly the
    length of the deferral.
    """
    identity = _identity_reading(
        [
            {
                "ts": "2026-07-01T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "staged",
                "source": "stage",
            },
            {
                "ts": "2026-08-08T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "held",
                "source": "stage-adopted-names",
            },
        ]
    )
    assert identity["last_run_ts"] == "2026-07-01T00:00:00+00:00"
    assert identity["due"] is True


def test_gate_adoption_row_does_not_advance_cadence() -> None:
    """Same for ``approved``/``rejected`` reached via the staging gate.

    The generation ran on 07-01; the human deciding it on 08-08 must not
    restart the 27-day clock, or a slow gate silently stretches the cadence.
    """
    for decision in ("approved", "rejected"):
        identity = _identity_reading(
            [
                {
                    "ts": "2026-07-01T00:00:00+00:00",
                    "command": "distill-identity",
                    "decision": "staged",
                    "source": "stage",
                },
                {
                    "ts": "2026-08-08T00:00:00+00:00",
                    "command": "distill-identity",
                    "decision": decision,
                    "source": "stage-adopted",
                },
            ]
        )
        assert identity["last_run_ts"] == "2026-07-01T00:00:00+00:00", decision
        assert identity["due"] is True, decision


def test_direct_run_advances_cadence_without_a_staged_row() -> None:
    """``distill-identity`` without ``--stage`` writes no ``staged`` row.

    Generation and approval happen in one interactive run, so the ``approved``
    row IS the generation timestamp. A decision allowlist of ``{"staged"}``
    would drop it and leave the reading claiming no run ever happened —
    the weekly chain would then stage another identity next week.
    """
    identity = _identity_reading(
        [
            {
                "ts": "2026-08-05T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "approved",
                "source": "direct",
            }
        ]
    )
    assert identity["last_run_ts"] == "2026-08-05T00:00:00+00:00"
    assert identity["due"] is False


def test_only_gate_decisions_reads_as_no_prior_generation() -> None:
    """Gate rows alone are not evidence a distill ran inside this log.

    Fail-safe direction: unknown-but-nonempty history falls into the
    bootstrap branch (due), it does not silently pin the clock to a gate.
    """
    identity = _identity_reading(
        [
            {
                "ts": "2026-08-08T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "held",
                "source": "stage-adopted-names",
            },
            {
                "ts": "2026-08-08T00:00:00+00:00",
                "command": "insight",
                "decision": "approved",
                "source": "stage-adopted",
            },
        ]
    )
    assert identity["last_run_ts"] is None
    assert identity["due"] is True


def test_a_row_predating_the_source_field_counts_as_a_generation() -> None:
    """Pre-2026 records have no `source`; the only writer then was direct.

    Pinned explicitly rather than left to older fixtures that happen to omit
    the key — a routine fixture cleanup would otherwise drop the coverage
    silently (code review 2026-08-15).
    """
    identity = _identity_reading(
        [{"ts": "2026-08-05T00:00:00+00:00", "command": "distill-identity", "decision": "approved"}]
    )
    assert identity["last_run_ts"] == "2026-08-05T00:00:00+00:00"


def test_an_unrecognised_audit_source_abstains_instead_of_reading_as_never_run() -> None:
    """Fail-safe against `AuditSource` growing a value this script never saw.

    Skipping the row would leave no generation found and nothing counted, so
    the bootstrap arm would report `due=True` with `NO_PRIOR_RUN` — firing an
    unattended distill every week while claiming a history that exists is
    absent. Unknown must abstain, as it already does for unparsable rows.
    """
    identity = _identity_reading(
        [
            {
                "ts": "2026-08-05T00:00:00+00:00",
                "command": "distill-identity",
                "decision": "staged",
                "source": "stage-via-some-future-path",
            }
        ]
    )
    assert identity["last_run_ts"] is None
    assert identity["due"] is False
    assert identity["reason"] == "UNPARSABLE_HISTORY"


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


# --- Rules layer (ADR-0097 D2) ---
#
# `rules-distill` / `rules-stocktake` were retired as LLM generators; this
# deterministic reading is the only maintenance owner the layer has left. The
# structural check is a MIRROR of core.stocktake._check_rule_quality — the
# script runs under the system python3, which has no contemplative_agent on
# its path — so the first test below pins the two together.

GOOD_RULE = (
    "# Verify Before Work\n\n"
    "**Practice:** Confirm the premise in code before starting a ledger task.\n\n"
    "**Rationale:** Three of the last ten tasks were already done when they "
    "were picked up, and the ledger entry was the only thing that still said "
    "otherwise. Reading the code first costs a minute and closes the entry.\n"
)


def _rules_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    rules = tmp_path / "rules"
    rules.mkdir()
    for name, body in files.items():
        (rules / name).write_text(body, encoding="utf-8")
    return rules


def test_local_rule_check_agrees_with_the_canonical_one() -> None:
    """The duplication is deliberate (system python3 cannot import the
    package) — so it is pinned, not left to vigilance. A change to one and
    not the other fails here."""
    from contemplative_agent.core.stocktake import _check_rule_quality as canonical

    bodies = {
        "good.md": GOOD_RULE,
        "short.md": "Brief.",
        "no-practice.md": "x" * 250 + "\n\n**Rationale:** because.\n",
        "no-rationale.md": "x" * 250 + "\n\n**Practice:** do it.\n",
        "exactly-200.md": "y" * 200,
        "199.md": "y" * 199,
    }
    for name, body in bodies.items():
        mine = vldc._check_rule_quality(body)
        theirs = canonical(name, body)
        assert mine == (theirs.reason if theirs is not None else None), name


def test_rules_reading_counts_mtime_and_issues(tmp_path: Path) -> None:
    rules = _rules_dir(tmp_path, {"good.md": GOOD_RULE, "bad.md": "too short"})
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-01T00:00:00+00:00", source="stage")],
    )
    reading = _reading(_run(paths, "--rules-dir", str(rules)))
    assert reading["rules"]["files"] == 2
    assert reading["rules"]["reason"] == "OK"
    assert reading["rules"]["issues"] == [{"file": "bad.md", "reason": "body < 200 chars"}]
    assert reading["rules"]["newest_mtime"] is not None
    # Measured against --as-of, not the wall clock: the reading replays.
    assert reading["rules"]["days_since_newest"] is not None
    # A content problem is NOT a chain fault — it must not reach the header
    # reason list, where the packet's recurrence trigger would spend an
    # unattended improve session on it.
    assert reading["reasons"] == []


def test_rules_key_absent_when_not_asked_for(tmp_path: Path) -> None:
    """No --rules-dir = not scanned. The packet keeps that apart from
    scanned-and-clean, so the key must be missing rather than null."""
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-01T00:00:00+00:00", source="stage")],
    )
    assert "rules" not in _reading(_run(paths))


def test_missing_rules_dir_reaches_the_header(tmp_path: Path) -> None:
    """A dir the caller pointed at and that is not there is a wiring typo or
    a wrong MOLTBOOK_HOME — it must not stand for months as one cell inside
    §8. The recurrence-noise objection is answered in the packet's
    DESIGNED_OUTCOME_CODES, not by staying quiet here."""
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-01T00:00:00+00:00", source="stage")],
    )
    reading = _reading(_run(paths, "--rules-dir", str(tmp_path / "absent")))
    assert reading["rules"]["reason"] == "RULES_DIR_MISSING"
    assert reading["rules"]["files"] == 0
    assert reading["reasons"] == ["RULES_DIR_MISSING"]


def test_empty_rules_dir_named_apart_from_missing(tmp_path: Path) -> None:
    """A dir that exists and holds no rules is a legitimate state of a young
    store — the one rules state that does NOT reach the header."""
    rules = _rules_dir(tmp_path, {})
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-01T00:00:00+00:00", source="stage")],
    )
    reading = _reading(_run(paths, "--rules-dir", str(rules)))
    assert reading["rules"]["reason"] == "RULES_EMPTY"
    assert reading["rules"]["files"] == 0
    assert reading["rules"]["newest_mtime"] is None
    assert reading["rules"]["days_since_newest"] is None
    assert reading["reasons"] == []


def test_truncated_rule_files_are_not_an_empty_layer(tmp_path: Path) -> None:
    """Ten rules truncated to zero bytes is an incident; a store with no
    rules is a state. Without `empty_files` both render as RULES_EMPTY."""
    rules = _rules_dir(tmp_path, {"a.md": "", "b.md": "---\nname: b\n---\n"})
    reading = vldc.read_rules_layer(rules)
    assert reading is not None
    assert reading["files"] == 0
    assert reading["empty_files"] == 2
    assert reading["reason"] == "RULES_EMPTY"


def test_unreadable_rule_file_is_a_header_fault(tmp_path: Path) -> None:
    """ "I could not read what is there" IS a fault — unlike an empty layer,
    it means the reading is incomplete."""
    rules = _rules_dir(tmp_path, {"good.md": GOOD_RULE})
    (rules / "binary.md").write_bytes(b"\xff\xfe not utf-8")
    paths = _write_inputs(
        tmp_path,
        audit_lines=[_audit_line("distill-identity", "2026-08-01T00:00:00+00:00", source="stage")],
    )
    reading = _reading(_run(paths, "--rules-dir", str(rules)))
    assert reading["rules"]["reason"] == "RULES_UNREADABLE"
    assert reading["rules"]["unreadable_files"] == 1
    assert reading["rules"]["files"] == 1
    assert "RULES_UNREADABLE" in reading["reasons"]


def test_local_traversal_matches_read_markdown_documents(tmp_path: Path) -> None:
    """The parity test above pins the rule VERDICTS. The `files:` count is the
    other half of the reading, and it comes from a second mirrored contract —
    `core.text_utils.read_markdown_documents`: sorted `*.md`, dotfiles
    skipped, frontmatter stripped, empty bodies dropped. A traversal change
    would drift the count with nothing failing."""
    from contemplative_agent.core.text_utils import read_markdown_documents

    rules = _rules_dir(
        tmp_path,
        {
            "b.md": GOOD_RULE,
            "a.md": "---\nname: a\n---\n\n" + GOOD_RULE,
            ".hidden.md": GOOD_RULE,
            "empty.md": "---\nname: e\n---\n",
            "not-markdown.txt": GOOD_RULE,
        },
    )
    canonical = read_markdown_documents(rules)
    mine = vldc.read_rules_layer(rules)
    assert mine is not None
    assert mine["files"] == len(canonical) == 2
    # Same bodies, in the same order, after the same frontmatter strip.
    assert [vldc._strip_frontmatter((rules / n).read_text()).strip() for n, _, _ in canonical] == [
        body for _, _, body in canonical
    ]


def test_rules_reading_skips_dotfiles_and_frontmatter(tmp_path: Path) -> None:
    """Same file rules as read_markdown_documents: dotfiles out, the check
    runs on the frontmatter-stripped body."""
    rules = _rules_dir(
        tmp_path,
        {
            ".hidden.md": "short",
            "front.md": "---\nname: front\n---\n\n" + GOOD_RULE,
            "empty-body.md": "---\nname: e\n---\n",
        },
    )
    reading = vldc.read_rules_layer(rules)
    assert reading is not None
    assert reading["files"] == 1
    assert reading["issues"] == []


def test_rules_days_since_newest_uses_as_of(tmp_path: Path) -> None:
    reading = vldc.build_reading(
        audit_records=[{"ts": "2026-08-01T00:00:00+00:00", "command": "distill-identity"}],
        patterns=[],
        staging_pending=0,
        as_of="2026-08-22",
        identity_interval_days=27,
        amendment_interval_days=83,
        rules={
            "files": 2,
            "newest_mtime": "2026-04-11T00:00:00+00:00",
            "issues": [],
            "reason": "OK",
        },
    )
    assert reading["rules"]["days_since_newest"] == 133
