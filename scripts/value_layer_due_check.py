#!/usr/bin/env python3
"""Value-layer cadence instrument — identity / constitution due readings.

Read-only over three stores the agent already writes: the ADR-0012 approval
audit log (``logs/audit.jsonl``), ``knowledge.json`` and the staging dir
(ADR-0074).  Emits one JSON reading on stdout for the weekly pipeline:

- ``identity``: days since the last ``distill-identity`` run and whether the
  monthly interval has elapsed.  The cadence gates *generation*, not
  adoption, so it counts rows whose ``source`` was stamped when the distill
  ran (``stage``/``direct``) and ignores every ``stage-adopted*`` row — a
  gate deciding on 08-08 an item generated on 07-01 must not restart the
  clock, whatever it decided (T-HELD-IDENTITY-CADENCE).  The pipeline stages
  a fresh candidate only when this is due AND staging is empty; adoption
  stays at the Saturday gate.
- ``constitution``: days since the last *adopted* amendment
  (``decision="approved"``) plus the pattern-count delta since then.
  Informational only — an amendment is a deliberate, benched event
  (ADR-0090 / docs/runbooks/constitution-amendment.md), never automated.
- ``staging_pending``: unreviewed ``*.meta.json`` sidecars in staging, so
  the caller can respect the one-unreviewed-batch invariant (ADR-0074).

Faults: a missing/unreadable audit log abstains with a reason code on
stderr and a nonzero exit — an unknown state must never read as "due" and
fire an unattended LLM run (ADR-0077).  Partial faults (malformed audit
lines, missing knowledge.json) degrade to counted reasons in the reading.

The audit log carries schema drift: pre-2026-04 records use ``timestamp``
instead of ``ts`` and ``distill-identity-ca`` as the command name; both are
recognized.  ``--as-of`` is passed in (no wall-clock read) so a reading is
reproducible offline from the same inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from _audit import parse_records, parse_ts

_IDENTITY_COMMANDS = frozenset({"distill-identity", "distill-identity-ca"})
_AMEND_COMMAND = "amend-constitution"

# Audit sources written AT generation time, as opposed to later at the gate.
# ``source`` records which path reached the gate (cli/approval.py): ``stage``
# is stamped when the distill run stages its output, ``direct`` when the run
# generates and approves in one interactive pass. Every ``stage-adopted*``
# source is written later, when a human decides an item generated earlier.
#
# The identity cadence measures "how long since the last identity distillation
# RAN" (T-HELD-IDENTITY-CADENCE, owner's call 2026-08-15), so it filters on
# this rather than on ``decision``. Filtering on decision cannot express it:
# ``approved`` is written at generation time on the direct path but at the
# gate on the staged path, and a decision allowlist of ``{"staged"}`` would
# silently stop counting direct runs — a generation that happened would not
# advance the clock and the weekly chain would stage another one.
#
# Selecting on source is also stable against the decision vocabulary growing:
# ``held`` (the 4th value, 2026-08-15) and any 5th value are gate decisions
# and fall outside this set by construction.
_GENERATION_SOURCES = frozenset({"stage", "direct"})
# Sources written at the gate, on content generated earlier. Enumerated rather
# than treated as "anything not a generation source" so that an audit source
# this script has never heard of reads as unknown history and abstains,
# instead of quietly reading as "no distill ever ran".
_GATE_SOURCES = frozenset({"stage-adopted", "stage-adopted-names", "stage-adopted-auto"})


class CheckError(Exception):
    """An instrument-level fault: the reading is unavailable, not zero."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _record_ts(record: dict) -> tuple[str, datetime] | None:
    raw = record.get("ts") or record.get("timestamp")
    if not isinstance(raw, str):
        return None
    parsed = parse_ts(raw)
    if parsed is None:
        return None
    return raw, parsed


def _latest(
    records: list[dict],
    *,
    commands: frozenset[str],
    decisions: frozenset[str] | None,
    sources: frozenset[str] | None = None,
) -> tuple[tuple[str, datetime] | None, int]:
    """Latest matching record's (raw_ts, parsed_ts) + count of unparsable matches.

    ``decisions`` selects on what the gate decided, ``sources`` on which path
    wrote the row; both are optional and AND-ed. A record with no ``source``
    key predates the field, when the only writer was the direct path — so it
    reads as ``"direct"`` rather than being dropped by a source allowlist.

    A matching row whose ``source`` is recognised by neither ``sources`` nor
    ``_GATE_SOURCES`` counts as unparsable rather than being skipped. Skipping
    it would be fail-OPEN: with no generation row found and nothing counted,
    the caller's bootstrap arm reads "no prior run" and fires an unattended
    generation every week, under a reason code that says the history is empty
    when it is not (code review 2026-08-15). ``AuditSource`` is a growing
    ``Literal``, so this is the vocabulary risk the source filter trades the
    decision-vocabulary risk for — named, not eliminated.
    """
    best: tuple[str, datetime] | None = None
    unparsable = 0
    for record in records:
        # build_reading is the pure, independently-callable entry point, so
        # it must not depend on the CLI loader having filtered non-dicts.
        if not isinstance(record, dict):
            unparsable += 1
            continue
        if record.get("command") not in commands:
            continue
        if decisions is not None and record.get("decision") not in decisions:
            continue
        if sources is not None:
            source = record.get("source") or "direct"
            if source not in sources:
                if source not in _GATE_SOURCES:
                    unparsable += 1
                continue
        stamped = _record_ts(record)
        if stamped is None:
            unparsable += 1
            continue
        if best is None or stamped[1] > best[1]:
            best = stamped
    return best, unparsable


def _cadence(
    last: tuple[str, datetime] | None,
    *,
    as_of: date,
    interval_days: int,
    no_prior_reason: str,
    no_prior_due: bool,
) -> dict[str, Any]:
    if last is None:
        return {
            "last_ts": None,
            "days_since": None,
            "interval_days": interval_days,
            "due": no_prior_due,
            "reason": no_prior_reason,
        }
    raw, parsed = last
    days_since = (as_of - parsed.date()).days
    if days_since < 0:
        # A record dated after as-of is clock skew or corruption, not a fresh
        # run — fail safe (no fire) but name it instead of claiming NOT_DUE.
        return {
            "last_ts": raw,
            "days_since": days_since,
            "interval_days": interval_days,
            "due": False,
            "reason": "FUTURE_TIMESTAMP",
        }
    due = days_since >= interval_days
    return {
        "last_ts": raw,
        "days_since": days_since,
        "interval_days": interval_days,
        "due": due,
        "reason": "INTERVAL_ELAPSED" if due else "NOT_DUE",
    }


def build_reading(
    *,
    audit_records: list[dict],
    patterns: list[dict] | None = None,
    staging_pending: int,
    as_of: str,
    identity_interval_days: int,
    amendment_interval_days: int,
    patterns_loader: Callable[[], list[dict] | None] | None = None,
) -> dict[str, Any]:
    """Assemble the reading from already-loaded inputs (pure; unit-testable).

    ``patterns=None`` means knowledge.json was unavailable — the constitution
    pattern delta degrades to null with a reason, the rest stays live.
    ``patterns_loader`` (used by the CLI) defers that load until an adoption
    baseline actually exists: knowledge.json is >100 MB in production and
    deserializing it costs ~1.5 GB peak RSS on a 16 GB box that also hosts
    Ollama (security review 2026-08-10 M3) — a weekly reading must not pay
    that for a field only rendered on amendment-due weeks.
    """
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError as exc:
        raise CheckError("BAD_AS_OF", as_of) from exc
    if identity_interval_days < 1 or amendment_interval_days < 1:
        # A zero/negative interval would make the layer permanently due —
        # an unattended LLM run every single week. Abstain instead.
        raise CheckError("BAD_INTERVAL", f"{identity_interval_days}/{amendment_interval_days}")

    reasons: list[str] = []

    identity_last, identity_unparsable = _latest(
        audit_records,
        commands=_IDENTITY_COMMANDS,
        decisions=None,
        sources=_GENERATION_SOURCES,
    )
    # Matching records existed but none carried a parseable timestamp: the
    # history is unknown, not absent. Unknown must never read as "due" and
    # fire an unattended LLM run (codex review 2026-08-10 P2) — so this
    # abstains from the due claim instead of falling into the bootstrap
    # branch below.
    identity_history_unknown = identity_last is None and identity_unparsable > 0
    # An audit log with zero readable records is truncation or corruption,
    # not a fresh install — a fresh MOLTBOOK_HOME has no audit.jsonl at all
    # and abstains upstream as AUDIT_MISSING. So the genuine bootstrap
    # (due=true with no prior run) requires at least one OTHER readable
    # record as evidence the log is alive (security review 2026-08-10 L1).
    empty_audit = not audit_records
    if identity_history_unknown:
        identity_no_prior_reason = "UNPARSABLE_HISTORY"
    elif empty_audit:
        identity_no_prior_reason = "NO_AUDIT_RECORDS"
    else:
        identity_no_prior_reason = "NO_PRIOR_RUN"
    identity = _cadence(
        identity_last,
        as_of=as_of_date,
        interval_days=identity_interval_days,
        # Bootstrap exception to "unknown never reads as due": generation is
        # cheap and adoption stays human-gated, so a store that never ran
        # (but whose audit log is demonstrably alive) is immediately due.
        no_prior_reason=identity_no_prior_reason,
        no_prior_due=not (identity_history_unknown or empty_audit),
    )
    identity["last_run_ts"] = identity.pop("last_ts")

    amend_last, amend_unparsable = _latest(
        audit_records, commands=frozenset({_AMEND_COMMAND}), decisions=frozenset({"approved"})
    )
    amend_history_unknown = amend_last is None and amend_unparsable > 0
    constitution = _cadence(
        amend_last,
        as_of=as_of_date,
        interval_days=amendment_interval_days,
        # No baseline → no cadence claim; a first amendment is a deliberate
        # human decision the instrument must not nudge. Same due=False for
        # unknown history, but named differently so the reader can tell
        # "never adopted" from "records exist but are unreadable".
        no_prior_reason="UNPARSABLE_HISTORY" if amend_history_unknown else "NO_PRIOR_ADOPTION",
        no_prior_due=False,
    )
    constitution["last_adopted_ts"] = constitution.pop("last_ts")

    patterns_since: int | None = None
    if amend_last is not None:
        loaded = patterns_loader() if patterns_loader is not None else patterns
        if loaded is not None:
            adopted_at = amend_last[1]
            patterns_since = 0
            for pattern in loaded:
                distilled = (
                    parse_ts(pattern.get("distilled")) if isinstance(pattern, dict) else None
                )
                if distilled is not None and distilled > adopted_at:
                    patterns_since += 1
        else:
            reasons.append("KNOWLEDGE_UNAVAILABLE")
    constitution["patterns_since"] = patterns_since

    # Anomalous cadence states must be loud, not just embedded in the layer
    # dicts — the packet builder propagates this list into its header reason
    # codes, so a suppressed or corrupted clock never reads as a quiet week
    # (security review 2026-08-10 M1 second door).
    for layer in (identity, constitution):
        if layer["reason"] in ("FUTURE_TIMESTAMP", "UNPARSABLE_HISTORY", "NO_AUDIT_RECORDS"):
            code = str(layer["reason"])
            if code not in reasons:
                reasons.append(code)

    malformed = identity_unparsable + amend_unparsable
    return {
        "as_of": as_of,
        "identity": identity,
        "constitution": constitution,
        "staging_pending": staging_pending,
        "malformed_audit_lines": malformed,
        "reasons": reasons,
    }


def _load_audit(path: Path) -> tuple[list[dict], int]:
    """Load audit records; malformed lines are counted, not fatal.

    Strict decode, unlike `value_layer_approval_join`: this reading drives a
    due/not-due verdict, so a log it cannot read in full must abstain rather
    than answer from the part that decoded. The line grammar is shared
    (`_audit.parse_records`) because both readings land in the same packet.
    """
    if not path.is_file():
        raise CheckError("AUDIT_MISSING", str(path))
    try:
        text = path.read_text(encoding="utf-8")
    # UnicodeDecodeError is a ValueError, not an OSError — the same gap that
    # took build_decision_packet.py down once (2026-07-29 review). A single
    # invalid byte must abstain, not traceback.
    except (OSError, UnicodeDecodeError) as exc:
        raise CheckError("AUDIT_UNREADABLE", str(exc)) from exc
    return parse_records(text)


def _load_patterns(path: Path) -> list[dict] | None:
    """Load knowledge.json; unavailability degrades to None (partial fault)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    # UnicodeDecodeError included for the same reason as _load_audit: this
    # path is documented as a partial fault and must degrade, not crash.
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) else None


def _count_staged(path: Path) -> int:
    if not path.is_dir():
        return 0
    return len(list(path.glob("*.meta.json")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True, help="ADR-0012 logs/audit.jsonl")
    parser.add_argument("--knowledge", type=Path, required=True, help="knowledge.json")
    parser.add_argument("--staged-dir", type=Path, required=True, help="staging dir (ADR-0074)")
    parser.add_argument("--as-of", required=True, help="reading date, YYYY-MM-DD")
    # Anchor offset: the weekly chain passes --as-of END_DATE = the day
    # BEFORE the run day, so on the k-th Saturday after a record was written
    # days_since = 7k - 1. The defaults are chosen against that anchor:
    # 27 → first eligible run at exactly 4 weeks, 83 → exactly 12 weeks.
    # A round 28/84 would silently mean 5 weeks / 13 weeks (code review
    # 2026-08-10 M4).
    parser.add_argument("--identity-interval-days", type=int, default=27)
    parser.add_argument("--amendment-interval-days", type=int, default=83)
    args = parser.parse_args(argv)

    try:
        audit_records, malformed_lines = _load_audit(args.audit)
        reading = build_reading(
            audit_records=audit_records,
            staging_pending=_count_staged(args.staged_dir),
            as_of=args.as_of,
            identity_interval_days=args.identity_interval_days,
            amendment_interval_days=args.amendment_interval_days,
            patterns_loader=lambda: _load_patterns(args.knowledge),
        )
    except CheckError as exc:
        print(f"value_layer_due_check: {exc.reason}: {exc}", file=sys.stderr)
        return 2

    reading["malformed_audit_lines"] += malformed_lines
    if reading["malformed_audit_lines"]:
        reading["reasons"].append("AUDIT_PARTIAL_PARSE")
    print(json.dumps(reading, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
