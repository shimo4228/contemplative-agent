#!/usr/bin/env python3
"""Join value-layer state diffs to their ADR-0012 approval records (read-only).

The weekly state diff shows *what* changed in identity / constitution /
skills / rules, and nothing about *whether the change passed the approval
gate*. That gap produced the loudest — and unresolvable — claim in the
2026-08-15 report: "whether it passed through the ``amend-constitution``
approval path is not visible in the operator-facing data supplied here".
``logs/audit.jsonl`` had already answered it. This renders that answer next
to each diff section, so a value-layer change arrives either matched to an
approval row or explicitly flagged as having none.

The *absence* of an approved row for a section that shows a diff is the
alarm condition. It is therefore distinguished, in the rendering, from the
three states that must never read as that alarm:

- the audit log is missing or unreadable (``unavailable``, with a reason
  code) — an unavailable instrument reads zero, not clean (ADR-0077);
- the section shows no diff (``none (no diff either)``);
- an in-window row matched no section at all — counted and rendered as a
  residual, because a row this join cannot place is a "cannot tell" about
  that row, and an unplaced *approved* row is precisely what turns this
  instrument's own maximum-severity output into a false alarm (2026-08-15).
  The residual covers rows whose timestamp parses, since windowing is what
  makes "in-window" meaningful; a row that is *both* unplaceable and
  undatable is dropped uncounted — the ``unparsable`` tally is section-scoped
  and this join has no window to place such a row in. Known and left as a
  caveat rather than a counter: an undatable row cannot be attributed to
  *this* week's diff, so counting it here would spread one week's residual
  across every window the log is ever read through.

Live-text reconciliation (weekly 2026-08-22 F1.2): the tally above answers
"was there an approval row", never "do the bytes in place now match one".
``audit.jsonl`` records *approvals*, not *writes*, so a hand repair, a
restore from backup or an out-of-band edit changes the live layer while
leaving a clean tally. The audit row's ``content_hash`` is
``sha256(bytes written)[:16]`` (``cli/approval.py:161``, invariant stated at
``cli/adopt.py:323-326``), so the live file's provenance is decidable by
hashing it. Three named states are rendered, of which the last two are
today indistinguishable in the tally alone:

- a live file's hash matches an approved row (the normal case);
- a live file matches NO approved row — those bytes never passed the gate;
- an in-window approved row has no live file carrying its hash — approved
  and written, but not what the runtime reads now.

"Live" means the files the runtime actually loads: ``identity.md`` for
identity (``core/llm/prompting.py:213``), ``*.md`` under the section
directory for constitution / skills / rules (``core/domain.py:332``,
``core/llm/prompting.py:178``, ``core/skill_selection.py:141``,
``core/text_utils.py:190``). A sibling written beside the canonical name
(``identity-2.md``) is therefore not a live file and shows up as the third
state, which is exactly what it is.

Calibration of the second state (review, 2026-08-22): "matches no approved
row" is *not* a synonym for "bypassed the gate". ``contemplative-agent
init`` copies the template value layer into MOLTBOOK_HOME writing no audit
row at all (``cli/session_cmds.py:66`` for the three directories, ``:88``
for ``identity.md``), and an approval older than the retained log reads the
same way. A shipped default never amended in place therefore sits in this
state permanently and benignly, so the rendering names that cause beside
the three write-time ones instead of asserting a bypass. What carries
signal is a *rise* in the count, not the count.

Scope of the constitution scan: the runtime reads ``<home>/constitution``
only when started without ``--constitution-dir`` and without
``--no-axioms`` (``cli/runtime.py:104-105``). Under an override it loads a
different tree, and this reading — which has no way to know which flags the
scheduled run used — would describe files nobody read. That assumption is
rendered with the section rather than left implicit. An existing but empty
section directory reads ``unavailable (reason=live-dir-empty)``: zero files
hashed is the one shape an override and a genuinely empty layer share, and
neither is a clean bill of health.

Windowing: ``--start`` / ``--end`` are the *commit timestamps* of the two
data-repo snapshots the diff is taken between, not the report's calendar
bounds. The interval is half-open, ``start < ts <= end``: anything approved
at or before the start commit is already inside that commit's tree and so
is not part of the diff. Passing calendar dates instead would mis-window by
the sync lag.

Security / boundary (load-bearing):
- Reads ONLY ``audit.jsonl``, which the agent writes itself (never episode
  logs — injection boundary).
- Renders five dense fields per row: ``ts``, ``command``, ``decision``,
  ``source``, ``content_hash``. ``reason`` is operator free text and
  ``source_ids`` is an unbounded lineage list; neither is ever rendered.
  Target paths are not rendered either — skill filenames are slugified from
  distilled pattern text, so they are the one structural field in a record
  that carries content-derived bytes.
- The five rendered fields are written by this codebase from closed
  vocabularies, but are still squashed of non-printables, length-capped and
  pipe-escaped at render: a record is durable state, and a malformed row
  must not break out of its table cell into report prose.
- The reconciliation reads live value-layer files but renders only
  ``sha256(...)[:16]`` digests and counts — the same 16-hex shape already in
  the log, one-way, and never the file's content or its path.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from _audit import IDENTITY_COMMANDS, parse_records, parse_ts
from _md import md_safe, printable

# Which path shapes belong to which state-diff section. ``identity`` is a
# single canonical file; the other three are directories.
_DIR_SECTIONS = ("constitution", "skills", "rules")
_SECTIONS = ("identity", *_DIR_SECTIONS)

# ``IDENTITY_COMMANDS`` (the commands that own the identity section by
# construction, whatever leaf their write landed on) is imported from
# ``_audit`` rather than restated: ``value_layer_due_check`` selects on the same
# vocabulary and the two readings must not disagree about which rows exist.

_FIELD_CAP = 80
_DEFAULT_TOP = 25
# How many digests / timestamps one reconciliation line may name before it
# degrades to a count. Same reason as `--top`: the line answers "which state",
# and an unbounded list of them buries that answer.
_RECON_CAP = 5


class JoinUnavailable(Exception):
    """The reading cannot be produced. Carries a reason code, never zero."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ``order=True`` is load-bearing: Row is the tie-breaker in the (ts, row) sort
# below, so same-second records would raise on comparison without it.
@dataclass(frozen=True, order=True)
class Row:
    ts: str
    command: str
    decision: str
    source: str
    content_hash: str


@dataclass(frozen=True)
class LiveFile:
    """One live value-layer file reduced to digests. No path, no content.

    Two digests, not one: ``_log_approval`` hashes the text it was handed
    (``cli/approval.py:161``) while ``adopt`` writes that text plus a
    trailing newline when it lacks one (``cli/adopt.py:335``). Hashing only
    the bytes on disk would therefore report every newline-terminated adopt
    as unapproved. ``digests[0]`` is the on-disk bytes and is the one shown.
    """

    digests: tuple[str, ...]


@dataclass(frozen=True)
class LiveScan:
    """Result of hashing a section's live files.

    ``reason`` non-None means the scan could not be performed: an
    unavailable instrument reads *unavailable*, never "matches no approved
    row" (ADR-0077) — that string is an accusation.
    """

    files: tuple[LiveFile, ...] = ()
    unreadable: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class Reconciliation:
    """Live bytes vs approved hashes, in the three states of the docstring."""

    scanned: int
    matched: int
    latest_match_ts: str
    unmatched_live: tuple[str, ...]
    unmatched_live_total: int
    orphan_rows: tuple[str, ...]
    orphan_rows_total: int
    unreadable: int
    reason: str | None = None


@dataclass(frozen=True)
class Reading:
    section: str
    changed: bool
    rows: tuple[Row, ...]
    approved: int
    staged: int
    rejected: int
    other: int
    unparsable: int
    unmatched: int
    truncated: int
    window_start: str
    window_end: str
    reconciliation: Reconciliation | None = None


def _matches_section(record: dict[str, Any], section: str) -> bool:
    """Does this audit record belong to `section`?

    Matched on path components rather than a prefix: the audit log records
    absolute paths from whatever MOLTBOOK_HOME was live at write time, which is
    not necessarily the home this scan runs against (backfill runs, relocated
    data dirs).

    The identity section is additionally selected by the *command's canonical
    target*, not by leaf name alone. The one defect class that matters here
    renames the target: the H5 collision guard turned an approved
    ``distill-identity`` write into ``identity-2.md``
    (``cli/adopt.py::_replaces_canonical_target``, live on 2026-08-15). On a
    leaf-name match that approved row belongs to no section at all and is
    dropped, leaving ``approved 0, staged 1, changed=True`` — the exact
    predicate for ``NO APPROVED RECORD``. Reading and writing must not
    disagree about which command owns which section. The producer defect is
    closed, but this log is append-only: those rows are in every future
    backfill or replay window.

    The command-based arm yields to the directory-shaped sections, so a
    mislabelled row lands in exactly one section rather than being counted
    twice.
    """
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return False
    parts = PurePosixPath(raw_path).parts
    if not parts:
        return False
    if section == "identity":
        if parts[-1] == "identity.md":
            return True
        command = record.get("command")
        if not isinstance(command, str) or command not in IDENTITY_COMMANDS:
            return False
        return not any(other in parts[:-1] for other in _DIR_SECTIONS)
    # A directory-shaped section: some *parent* component carries the name.
    # Checking parents only keeps a file literally named ``skills`` out.
    return section in parts[:-1]


def _clean(value: object) -> str:
    """Render one audit field: non-printables squashed, capped, Markdown-safed.

    Both neutralisers, because this lands in a table an LLM reads: `printable`
    for what could act on a terminal or reorder the line, `md_safe` for what
    breaks the table cell or the code span around it.
    """
    if value is None:
        return "—"
    text = printable(str(value)).strip()
    if not text:
        return "—"
    if len(text) > _FIELD_CAP:
        text = text[: _FIELD_CAP - 1] + "…"
    return md_safe(text)


def load_records(audit_path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read audit.jsonl -> (records, unparsable line count).

    A missing or unreadable log raises rather than returning empty: "no
    records" and "cannot tell" are the two states this instrument exists to
    keep apart. That decision stays here; `_audit.parse_records` owns only the
    line grammar, which must match `value_layer_due_check` because both feed
    the same packet. `errors="replace"` rather than an abstain on a decode
    fault: this reading is an annotation beside a diff, so a single mangled
    byte should cost that record's legibility, not the whole section.
    """
    if not audit_path.is_file():
        raise JoinUnavailable("audit-log-missing")
    try:
        text = audit_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise JoinUnavailable("audit-log-unreadable") from None
    return parse_records(text)


def _digests(data: bytes) -> tuple[str, ...]:
    """The hashes an approval row could carry for these bytes on disk."""
    hashes = [hashlib.sha256(data).hexdigest()[:16]]
    if data.endswith(b"\n"):
        # The adopt path logs the text *before* its newline terminator.
        hashes.append(hashlib.sha256(data[:-1]).hexdigest()[:16])
    return tuple(hashes)


def scan_live(home: Path, section: str) -> LiveScan:
    """Hash the files the runtime actually loads for `section`.

    Identity is one canonical file; the other three sections are a ``*.md``
    glob over the section directory — matching the loaders cited in the
    module docstring. A sibling like ``identity-2.md`` is deliberately NOT
    scanned: the runtime never reads it, so an approval that landed there is
    the third state, not the first.

    Per-file OSErrors degrade to a count rather than abstaining: one
    unreadable skill should cost that file's legibility, not the reading.

    A section directory that exists but holds no ``*.md`` abstains with
    ``live-dir-empty`` instead of reading "0 hashed, 0 unmatched": that
    shape is also what a run redirected by ``--constitution-dir`` leaves
    behind, and an empty scan must not read as reconciled.
    """
    if not home.is_dir():
        return LiveScan(reason="live-home-missing")
    if section == "identity":
        paths = [home / "identity.md"]
        if not paths[0].is_file():
            return LiveScan(reason="live-identity-missing")
    else:
        directory = home / section
        if not directory.is_dir():
            return LiveScan(reason="live-dir-missing")
        paths = sorted(p for p in directory.glob("*.md") if p.is_file())
        if not paths:
            return LiveScan(reason="live-dir-empty")
    files: list[LiveFile] = []
    unreadable = 0
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError:
            unreadable += 1
            continue
        files.append(LiveFile(digests=_digests(data)))
    return LiveScan(files=tuple(files), unreadable=unreadable)


def _reconcile(
    live: LiveScan,
    approved_by_hash: dict[str, tuple[datetime, str]],
    window_approved: list[tuple[datetime, str, str]],
) -> Reconciliation:
    """Compare live digests to approved hashes. Pure.

    ``approved_by_hash`` spans the *whole* log, not the window: bytes
    approved a month ago are still approved bytes, and window-scoping this
    side would report every untouched file as unapproved. ``window_approved``
    is window-scoped, because "approved this week and yet not live" is the
    claim worth making — the same row a year ago is just superseded history.
    """
    if live.reason is not None:
        return Reconciliation(
            scanned=0,
            matched=0,
            latest_match_ts="—",
            unmatched_live=(),
            unmatched_live_total=0,
            orphan_rows=(),
            orphan_rows_total=0,
            unreadable=live.unreadable,
            reason=live.reason,
        )
    matched = 0
    latest: tuple[datetime, str] | None = None
    unmatched_live: list[str] = []
    for file in live.files:
        hit = next((approved_by_hash[d] for d in file.digests if d in approved_by_hash), None)
        if hit is None:
            unmatched_live.append(file.digests[0])
            continue
        matched += 1
        if latest is None or hit[0] > latest[0]:
            latest = hit
    live_digests = {digest for file in live.files for digest in file.digests}
    orphans = [raw_ts for _, raw_ts, digest in window_approved if digest not in live_digests]
    return Reconciliation(
        scanned=len(live.files),
        matched=matched,
        latest_match_ts=_clean(latest[1]) if latest is not None else "—",
        unmatched_live=tuple(unmatched_live[:_RECON_CAP]),
        unmatched_live_total=len(unmatched_live),
        orphan_rows=tuple(_clean(ts) for ts in orphans[:_RECON_CAP]),
        orphan_rows_total=len(orphans),
        unreadable=live.unreadable,
    )


def build_reading(
    records: list[dict[str, Any]],
    *,
    section: str,
    changed: bool,
    start: datetime,
    end: datetime,
    unparsable: int = 0,
    top: int = _DEFAULT_TOP,
    live: LiveScan | None = None,
) -> Reading:
    """Select the section's in-window rows and tally decisions.

    Pure: takes already-loaded records — and already-hashed live files — so
    the join is reproducible offline from the same inputs (ADR-0075). All
    file I/O lives in `load_records` / `scan_live`.
    """
    selected: list[tuple[datetime, Row]] = []
    counts = {"approved": 0, "staged": 0, "rejected": 0, "other": 0}
    unmatched = 0
    # Every approved hash in the log, newest wins; and the in-window subset.
    approved_by_hash: dict[str, tuple[datetime, str]] = {}
    window_approved: list[tuple[datetime, str, str]] = []
    for record in records:
        mine = _matches_section(record, section)
        # A row this join cannot place must not read as silence: an unplaced
        # in-window row is counted and rendered, so a path shape the predicate
        # has not anticipated degrades to a visible "cannot tell" instead of
        # quietly emptying the tally that drives the alarm.
        placed = mine or any(_matches_section(record, other) for other in _SECTIONS)
        # Pre-2026-04 records use ``timestamp``; value_layer_due_check.py
        # recognizes both, so this must too or the two readings disagree.
        raw_ts = record.get("ts") or record.get("timestamp")
        parsed = parse_ts(raw_ts)
        if parsed is None:
            if mine:
                unparsable += 1
            continue
        in_window = start < parsed <= end
        if in_window and not placed:
            unmatched += 1
            continue
        if not mine:
            continue
        decision = record.get("decision")
        digest = record.get("content_hash")
        if decision == "approved" and isinstance(digest, str) and digest.strip():
            # Collected before the window filter: bytes approved before the
            # start commit are still approved bytes, and the live file
            # carrying them must not read as unapproved.
            digest = digest.strip().lower()
            previous = approved_by_hash.get(digest)
            if previous is None or parsed > previous[0]:
                approved_by_hash[digest] = (parsed, str(raw_ts))
            if in_window:
                window_approved.append((parsed, str(raw_ts), digest))
        if not in_window:
            continue
        counts[decision if decision in counts else "other"] += 1
        selected.append(
            (
                parsed,
                Row(
                    ts=_clean(raw_ts),
                    command=_clean(record.get("command")),
                    decision=_clean(decision),
                    source=_clean(record.get("source")),
                    content_hash=_clean(record.get("content_hash")),
                ),
            )
        )
    # Sort on the parsed timestamp, with the rendered tuple as tie-breaker so
    # same-second rows keep a stable order across runs.
    selected.sort(key=lambda item: (item[0], item[1]))
    if top <= 0 or len(selected) <= top:
        shown = selected
    else:
        # The cap must never spend itself on rows that do not answer the
        # question. A busy skills week is ~110 rows dominated by same-second
        # `staged` batches, so a plain head-of-list slice hid all 8 approved
        # rows behind 25 staged ones — while the prompt asks the report to
        # cite an approving row's ts and content_hash. Approved rows are
        # reserved first, the remaining slots go to the earliest others, and
        # the shown set is re-sorted chronologically so the table still reads
        # as a timeline.
        approved_rows = [item for item in selected if item[1].decision == "approved"]
        others = [item for item in selected if item[1].decision != "approved"]
        shown = approved_rows[:top]
        shown.extend(others[: top - len(shown)])
        shown.sort(key=lambda item: (item[0], item[1]))
    return Reading(
        section=section,
        changed=changed,
        rows=tuple(row for _, row in shown),
        approved=counts["approved"],
        staged=counts["staged"],
        rejected=counts["rejected"],
        other=counts["other"],
        unparsable=unparsable,
        unmatched=unmatched,
        truncated=len(selected) - len(shown),
        window_start=_clean(start.isoformat()),
        window_end=_clean(end.isoformat()),
        reconciliation=(
            None if live is None else _reconcile(live, approved_by_hash, window_approved)
        ),
    )


def format_unavailable(reason: str) -> str:
    return (
        f"**Approval provenance**: unavailable (reason={reason}). "
        "This is NOT evidence that the change above lacks an approval record — "
        "the instrument could not read `logs/audit.jsonl`."
    )


def format_reconciliation(recon: Reconciliation, section: str) -> list[str]:
    """Render the three named states. Digests and counts only."""
    if recon.reason is not None:
        return [
            "",
            f"**Live-text reconciliation**: unavailable (reason={recon.reason}). "
            "This is NOT evidence that the live text lacks an approval record — "
            "the instrument could not hash the live value-layer files.",
        ]
    lines = [
        "",
        "**Live-text reconciliation** (`sha256(live file)[:16]` vs the "
        "`content_hash` of every approved row, whole log): "
        f"{recon.scanned} live file(s) hashed, {recon.matched} match an approved "
        f"row (latest @{recon.latest_match_ts}).",
    ]
    if section == "constitution":
        lines.append(
            "(Scope: the `constitution/*.md` of the home given to this scan, which "
            "the runtime loads only when started without `--constitution-dir` and "
            "without `--no-axioms` (`cli/runtime.py:104-105`). This reading cannot "
            "see which flags a run used; under an override it describes files the "
            "runtime did not read.)"
        )
    if recon.unmatched_live_total:
        shown = ", ".join(recon.unmatched_live)
        more = recon.unmatched_live_total - len(recon.unmatched_live)
        suffix = f", +{more} more" if more else ""
        lines.append(
            f"⚠️ {recon.unmatched_live_total} live file(s) match NO approved row "
            f"(sha256[:16] {shown}{suffix}). The bytes the runtime reads did not come "
            "from a logged approval. FOUR causes produce this and the hash cannot "
            "tell them apart: a hand repair, a restore from backup, an out-of-band "
            "edit — and a file that never had a row to begin with, which is the "
            "expected, permanent state of a shipped default (`contemplative-agent "
            "init` copies the template value layer in without writing any audit row, "
            "`cli/session_cmds.py:66,88`) and of an approval older than the retained "
            "log. Do not report a steady count as a gate bypass; a RISE in it is the "
            "signal. All four leave the tally above clean — this line is about the "
            "bytes, not about the window."
        )
    if recon.orphan_rows_total:
        shown = ", ".join(f"@{ts}" for ts in recon.orphan_rows)
        more = recon.orphan_rows_total - len(recon.orphan_rows)
        suffix = f", +{more} more" if more else ""
        lines.append(
            f"⚠️ {recon.orphan_rows_total} approved row(s) in this window have no "
            f"live file carrying that hash ({shown}{suffix}). Approved and "
            "written, but not what the runtime reads now — superseded by a later "
            "approval, written beside the canonical name (`identity-2.md`), or "
            "reverted."
        )
    if not recon.unmatched_live_total and not recon.orphan_rows_total and recon.scanned:
        lines.append(
            "Every live file traces to an approved row, and every approved row in "
            "this window is live."
        )
    if recon.unreadable:
        lines.append(f"({recon.unreadable} live file(s) could not be hashed and are excluded.)")
    return lines


def format_reading(reading: Reading) -> str:
    total = reading.approved + reading.staged + reading.rejected + reading.other
    lines = [
        f"**Approval provenance** (`logs/audit.jsonl`, ADR-0012 gate; window "
        f"{reading.window_start} → {reading.window_end}, exclusive of the start "
        f"commit): {total} record(s) — approved {reading.approved}, staged "
        f"{reading.staged}, rejected {reading.rejected}, other {reading.other}."
    ]
    if reading.changed and reading.approved == 0:
        lines.append(
            "⚠️ NO APPROVED RECORD for a section that shows a diff. The state above "
            "changed with no matching approval row in this window — report it as the "
            "observation it is, not as a confirmed gate bypass (a sync lag or a "
            "pre-window approval also produces this shape)."
        )
    elif not reading.changed and total == 0:
        lines.append("No diff and no approval records — nothing to reconcile.")
    if reading.reconciliation is not None:
        lines.extend(format_reconciliation(reading.reconciliation, reading.section))
    if reading.rows:
        lines.append("")
        lines.append("| ts | command | decision | source | content_hash |")
        lines.append("|---|---|---|---|---|")
        lines.extend(
            f"| {row.ts} | {row.command} | {row.decision} | {row.source} | {row.content_hash} |"
            for row in reading.rows
        )
    if reading.truncated:
        lines.append("")
        lines.append(f"({reading.truncated} further record(s) not shown — `--top` cap.)")
    if reading.unparsable:
        lines.append("")
        lines.append(f"({reading.unparsable} audit line(s) unparsable and excluded.)")
    if reading.unmatched:
        lines.append("")
        lines.append(
            f"({reading.unmatched} in-window audit row(s) matched no section — path shapes "
            "this join does not recognize. Their approvals, if any, are not in any tally "
            "above.)"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path, help="path to audit.jsonl")
    parser.add_argument("--section", required=True, choices=_SECTIONS)
    parser.add_argument(
        "--diff",
        required=True,
        choices=("changed", "unchanged"),
        help="whether the state-diff section this annotates shows a change",
    )
    parser.add_argument("--start", required=True, help="ISO-8601 start-commit timestamp")
    parser.add_argument("--end", required=True, help="ISO-8601 end-commit timestamp")
    parser.add_argument("--top", type=int, default=_DEFAULT_TOP, help="max rows rendered")
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="MOLTBOOK_HOME whose live value-layer files are hashed and reconciled "
        "against the approved rows; omitted renders the reconciliation as "
        "unavailable rather than silently skipping it",
    )
    args = parser.parse_args(argv)

    try:
        start = parse_ts(args.start)
        end = parse_ts(args.end)
        if start is None or end is None:
            raise JoinUnavailable("window-unparsable")
        records, unparsable = load_records(args.audit)
    except JoinUnavailable as exc:
        print(format_unavailable(exc.reason))
        return 0

    live = (
        LiveScan(reason="live-home-not-given")
        if args.home is None
        else scan_live(args.home, args.section)
    )
    reading = build_reading(
        records,
        section=args.section,
        changed=args.diff == "changed",
        start=start,
        end=end,
        unparsable=unparsable,
        top=args.top,
        live=live,
    )
    print(format_reading(reading))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
