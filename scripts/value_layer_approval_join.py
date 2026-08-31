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

Trend of the second state (gate, 2026-08-22): "a rise is the signal" is
only a usable instruction if the instrument holds the prior reading, and a
shipped default that never had a row must not re-render the full
four-causes paragraph every week — a steady line that is repeated is a line
that stops being read. ``--state`` / ``--emit-state`` carry the per-section
set of unmatched digests across runs in the same emit-aside / promote-after-
report discipline as the anomaly sweep (the baseline is spent only once a
report exists). A reading whose unmatched set equals the prior one folds to
a single "steady since" line; a changed set renders the delta next to the
full paragraph; a first run says so rather than pretending to a baseline.
A re-run of the same window (same ``--end``) compares against the reading
before the stored one, so a retried week does not read its own first
attempt as "steady".

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
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from _audit import IDENTITY_COMMANDS, parse_records, parse_ts
from _md import md_safe, printable

# Which path shapes belong to which state-diff section. ``identity`` is a
# single canonical file; the other three are directories.
_DIR_SECTIONS = ("constitution", "skills", "rules")
_SECTIONS = ("identity", *_DIR_SECTIONS)

# Retired skills are MOVED under ``skills/.archive/`` rather than unlinked
# (ADR-0097 Decision 5). Restated here rather than imported from
# ``adapters/moltbook/config.py::SKILLS_ARCHIVE_DIRNAME``: the weekly chain
# invokes this script with bare ``python3``, where ``contemplative_agent`` is
# not on the path. A test pins the two spellings together.
_ARCHIVE_DIRNAME = ".archive"

# ``source`` is the row's categorical execution path, and ADR-0097 gave it
# values that separate the two writes that share an ``.archive/`` path: a
# retirement MOVES a live skill in, a purge DELETES one already there. The
# path alone cannot tell them apart (unit A silent-failure review, 2026-08-22)
# — which is why the tally below reads ``source`` and the *exclusion* below
# reads the path: a source this join has not heard of must still be kept out
# of the live set, and being under ``.archive/`` is sufficient for that.
_PURGE_SOURCES = frozenset({"direct-purge", "direct-purge-auto"})

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
    # The whole unmatched set (``unmatched_live`` is the rendered, capped
    # prefix). Feeds the trend state; never rendered in full.
    unmatched_live_all: tuple[str, ...] = ()


@dataclass(frozen=True)
class Trend:
    """The unmatched-live set of this reading against the prior one.

    ``prior_end`` None with ``reason`` None is a first reading. ``reason``
    non-None means the state could not be read: rendered as unavailable,
    never as a first run (a corrupt baseline must not reset the trend).
    ``unchanged_since`` is the ``--end`` of the earliest consecutive reading
    that held this exact set; None when the set changed this week.
    """

    prior_end: str | None = None
    prior_total: int | None = None
    added: int = 0
    removed: int = 0
    unchanged_since: str | None = None
    reason: str | None = None
    # The prior set itself, carried so a re-run of this window can still be
    # compared against it once this reading has been stored (``previous``).
    prior_digests: tuple[str, ...] | None = None
    # The prior entry's own ``unchanged_since``, carried verbatim into
    # ``previous`` so a re-run of a changed week still knows how long the
    # week-before-last had held its set.
    prior_since: str | None = None


def _load_state(path: Path) -> dict[str, Any]:
    """Read the per-section trend state. Raises JoinUnavailable on failure."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise JoinUnavailable("state-unreadable") from None
    except ValueError:
        raise JoinUnavailable("state-unparsable") from None
    if not isinstance(loaded, dict):
        raise JoinUnavailable("state-unparsable")
    return loaded


def _entry_digests(entry: object) -> set[str] | None:
    if not isinstance(entry, dict):
        return None
    digests = entry.get("digests")
    if not isinstance(digests, list):
        return None
    return {d for d in digests if isinstance(d, str)}


def read_trend(state_path: Path | None, section: str, end: str, unmatched: set[str]) -> Trend:
    """Compare `unmatched` to the stored prior reading for `section`. Pure I/O-in.

    A stored entry whose ``end`` equals this run's ``end`` is this same
    window's earlier attempt; its ``previous`` is then the real prior.
    """
    if state_path is None:
        return Trend(reason="state-not-given")
    try:
        state = _load_state(state_path)
    except JoinUnavailable as exc:
        return Trend(reason=exc.reason)
    entry = state.get(section)
    if isinstance(entry, dict) and entry.get("end") == end:
        entry = entry.get("previous")
    prior = _entry_digests(entry)
    if prior is None:
        return Trend()
    assert isinstance(entry, dict)
    prior_end = entry.get("end")
    prior_end = _clean(prior_end) if isinstance(prior_end, str) else "—"
    added = len(unmatched - prior)
    removed = len(prior - unmatched)
    stored_since = entry.get("unchanged_since")
    prior_since = _clean(stored_since) if isinstance(stored_since, str) else None
    since: str | None = None
    if added == 0 and removed == 0:
        since = prior_since if prior_since is not None else prior_end
    return Trend(
        prior_end=prior_end,
        prior_total=len(prior),
        added=added,
        removed=removed,
        unchanged_since=since,
        prior_digests=tuple(sorted(prior)),
        prior_since=prior_since,
    )


def emit_state(
    emit_path: Path,
    section: str,
    end: str,
    unmatched: set[str],
    trend: Trend,
    state_path: Path | None = None,
) -> None:
    """Merge this section's reading into the pending state file.

    Each section's join is a separate process, so the pending file is read,
    updated and rewritten per call; the caller promotes it to ``--state``
    after the report lands. The prior reading (when one existed) is kept as
    ``previous`` so a re-run of the same window compares against it.

    The pending file is seeded from the committed ``state_path`` on first
    touch: promotion replaces the whole baseline, so a section that abstains
    this week (``live-dir-empty`` and friends write nothing) must carry its
    prior entry forward verbatim, or next week it would read as a first
    reading — the reset the module docstring forbids.

    A pending file that exists but does not parse is NOT replaced: four
    processes share it, and rewriting it from one section's view would drop
    the other three's entries silently. Raises ``JoinUnavailable`` so the
    caller can say so.
    """
    pending: dict[str, Any] = {}
    if emit_path.is_file():
        try:
            loaded = json.loads(emit_path.read_text(encoding="utf-8"))
        except OSError:
            raise JoinUnavailable("pending-unreadable") from None
        except ValueError:
            raise JoinUnavailable("pending-unparsable") from None
        if not isinstance(loaded, dict):
            raise JoinUnavailable("pending-unparsable")
        pending = loaded
    elif state_path is not None:
        try:
            pending = _load_state(state_path)
        except JoinUnavailable:
            # A baseline that cannot be read was already rendered as such by
            # read_trend; seeding from nothing here is the honest remainder.
            pending = {}
    entry: dict[str, Any] = {
        "end": end,
        "digests": sorted(unmatched),
        "unchanged_since": trend.unchanged_since if trend.unchanged_since else end,
    }
    if trend.prior_end is not None:
        entry["previous"] = {
            "end": trend.prior_end,
            "digests": list(trend.prior_digests or ()),
            "unchanged_since": trend.prior_since,
        }
    pending[section] = entry
    emit_path.write_text(json.dumps(pending, indent=1, sort_keys=True) + "\n", encoding="utf-8")


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
    # Approved rows that wrote under ``.archive/``. A subset of ``approved``,
    # not a fifth decision — kept apart because it is the one approved shape
    # that is not expected to be live. ``purged`` is in turn a subset of
    # ``archived``: a delete of a file already retired, not a new retirement.
    archived: int = 0
    purged: int = 0


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


def _is_retired(record: dict[str, Any]) -> bool:
    """Does this row name a file inside a section's ``.archive/``?

    A retirement is a gated mutation of the section, so the row stays in the
    section's tally — but the bytes are *deliberately* not live, which is the
    one thing the reconciliation below cannot infer. Left in
    ``window_approved`` every archive would render as "approved and written,
    but not what the runtime reads now", under a cause list that does not
    contain "retired": the exit would manufacture, at every gate, the exact
    alarm this join exists to raise for real defects.

    Path-shaped, like ``_matches_section`` and for the same reason — the log
    records absolute paths from whatever home was live at write time. This
    asks only "is it under an archive directory", which a purge *from* the
    archive also satisfies; both are correctly out of the live set, so the
    coarser question is the right one here.
    """
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return False
    return _ARCHIVE_DIRNAME in PurePosixPath(raw_path).parts[:-1]


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
        unmatched_live_all=tuple(sorted(unmatched_live)),
    )


@dataclass(frozen=True)
class _Selection:
    """What one pass over the audit records yields for a section's window."""

    selected: list[tuple[datetime, Row, bool]]
    counts: dict[str, int]
    unparsable: int
    unmatched: int
    archived: int
    purged: int
    approved_by_hash: dict[str, tuple[datetime, str]]
    window_approved: list[tuple[datetime, str, str]]


@dataclass
class _ApprovedIndex:
    """Approved content hashes, newest wins, plus the in-window subset.

    Mutable on purpose — a scratch accumulator built while the records are
    read, not a DTO. The two collections live together because the two
    invariants below are about their *relationship*, and separating them into
    loose parameters is how those invariants get quietly broken.
    """

    by_hash: dict[str, tuple[datetime, str]] = field(default_factory=dict)
    in_window: list[tuple[datetime, str, str]] = field(default_factory=list)

    def add(
        self,
        record: dict[str, Any],
        *,
        parsed: datetime,
        raw_ts: object,
        within_window: bool,
        retired: bool,
    ) -> None:
        """Record an approved row's content hash.

        Called BEFORE the window filter on purpose: bytes approved before the
        start commit are still approved bytes, and the live file carrying them
        must not read as unapproved. A retirement is excluded from
        :attr:`in_window` — the orphan side — only; it stays in
        :attr:`by_hash` so a restore from ``.archive/`` still traces to an
        approval.

        ``within_window`` is deliberately not spelled ``in_window``: that is the
        name of the field it gates, and the collision is the one place a future
        edit could write to the wrong thing (code review 2026-08-31).
        """
        digest = record.get("content_hash")
        if record.get("decision") != "approved" or not isinstance(digest, str):
            return
        if not digest.strip():
            return
        digest = digest.strip().lower()
        previous = self.by_hash.get(digest)
        if previous is None or parsed > previous[0]:
            self.by_hash[digest] = (parsed, str(raw_ts))
        if within_window and not retired:
            self.in_window.append((parsed, str(raw_ts), digest))


def _select_rows(
    records: list[dict[str, Any]],
    *,
    section: str,
    start: datetime,
    end: datetime,
    unparsable: int,
) -> _Selection:
    """One pass: place each record, tally its decision, collect approved hashes.

    Two orderings inside are load-bearing and must not be "tidied": approved
    hashes are collected BEFORE the window filter (bytes approved before the
    start commit are still approved bytes), and a retirement is excluded from
    the orphan side only — it stays in ``approved_by_hash`` so a restore from
    ``.archive/`` still traces to an approval.
    """
    selected: list[tuple[datetime, Row, bool]] = []
    counts = {"approved": 0, "staged": 0, "rejected": 0, "other": 0}
    unmatched = 0
    archived = 0
    purged = 0
    approved = _ApprovedIndex()
    for record in records:
        mine = _matches_section(record, section)
        retired = mine and _is_retired(record)
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
        approved.add(record, parsed=parsed, raw_ts=raw_ts, within_window=in_window, retired=retired)
        if not in_window:
            continue
        if retired and decision == "approved":
            archived += 1
            if record.get("source") in _PURGE_SOURCES:
                purged += 1
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
                retired,
            )
        )
    return _Selection(
        selected=selected,
        counts=counts,
        unparsable=unparsable,
        unmatched=unmatched,
        archived=archived,
        purged=purged,
        approved_by_hash=approved.by_hash,
        window_approved=approved.in_window,
    )


def _cap_rows(
    selected: list[tuple[datetime, Row, bool]], top: int
) -> list[tuple[datetime, Row, bool]]:
    """The rows to render, reserving the approved ones first.

    The cap must never spend itself on rows that do not answer the question. A
    busy skills week is ~110 rows dominated by same-second `staged` batches, so
    a plain head-of-list slice hid all 8 approved rows behind 25 staged ones —
    while the prompt asks the report to cite an approving row's ts and
    content_hash. Approved rows are reserved first, the remaining slots go to
    the earliest others, and the shown set is re-sorted chronologically so the
    table still reads as a timeline.
    """
    if top <= 0 or len(selected) <= top:
        return selected
    approved_rows = [item for item in selected if item[1].decision == "approved" and not item[2]]
    # Retirements are reserved after the other approvals: the diff above
    # this table no longer shows them (`weekly-analysis.sh` filters
    # `.archive/` out of the skills diff), and the header line states
    # their count, so a cap spent on them buys the reader nothing the
    # section has not already said.
    retired_rows = [item for item in selected if item[1].decision == "approved" and item[2]]
    others = [item for item in selected if item[1].decision != "approved"]
    shown = approved_rows[:top]
    shown.extend(retired_rows[: top - len(shown)])
    shown.extend(others[: top - len(shown)])
    shown.sort(key=lambda item: (item[0], item[1]))
    return shown


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

    The record pass and the cap live in ``_select_rows`` / ``_cap_rows`` for
    the C901 budget (2026-08-31); the invariants they carry are stated there.
    """
    picked = _select_rows(records, section=section, start=start, end=end, unparsable=unparsable)
    selected = picked.selected
    counts = picked.counts
    # Sort on the parsed timestamp, with the rendered tuple as tie-breaker so
    # same-second rows keep a stable order across runs.
    selected.sort(key=lambda item: (item[0], item[1]))
    shown = _cap_rows(selected, top)
    return Reading(
        section=section,
        changed=changed,
        rows=tuple(row for _, row, _ in shown),
        approved=counts["approved"],
        staged=counts["staged"],
        rejected=counts["rejected"],
        other=counts["other"],
        unparsable=picked.unparsable,
        unmatched=picked.unmatched,
        truncated=len(selected) - len(shown),
        window_start=_clean(start.isoformat()),
        window_end=_clean(end.isoformat()),
        reconciliation=(
            None
            if live is None
            else _reconcile(live, picked.approved_by_hash, picked.window_approved)
        ),
        archived=picked.archived,
        purged=picked.purged,
    )


def format_unavailable(reason: str) -> str:
    return (
        f"**Approval provenance**: unavailable (reason={reason}). "
        "This is NOT evidence that the change above lacks an approval record — "
        "the instrument could not read `logs/audit.jsonl`."
    )


def _format_trend(trend: Trend | None, now: int) -> str:
    if trend is None or trend.reason == "state-not-given":
        return ""
    if trend.reason is not None:
        return f"Trend: trend unavailable (reason={trend.reason}) — this is NOT a first reading."
    if trend.prior_end is None:
        return (
            "Trend: no prior reading for this section — the set is recorded for "
            "next week's comparison."
        )
    return (
        f"Trend vs prior reading @{trend.prior_end}: {trend.prior_total} then, {now} now "
        f"(+{trend.added} new, -{trend.removed} gone)."
    )


def format_reconciliation(
    recon: Reconciliation, section: str, trend: Trend | None = None
) -> list[str]:
    """Render the three named states. Digests and counts only.

    The unmatched-live line has two forms: the full four-causes paragraph
    with digests when the set is new or changed against the prior reading,
    and a single steady line when it is the same set as last time — the
    paragraph was rendered the week the set appeared, and repeating it is
    how a benign shipped default trains the reader to skip the line that
    will one day be the rise.
    """
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
    steady = (
        trend is not None
        and trend.reason is None
        and trend.prior_end is not None
        and trend.added == 0
        and trend.removed == 0
    )
    if recon.unmatched_live_total and steady:
        assert trend is not None
        lines.append(
            f"{recon.unmatched_live_total} live file(s) match NO approved row — steady: "
            f"the same set as the prior reading @{trend.prior_end}, unchanged since "
            f"@{trend.unchanged_since}. Not a rise; the four causes were listed the week "
            "this set first appeared and a shipped default sits here permanently."
        )
    elif recon.unmatched_live_total:
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
        trend_line = _format_trend(trend, recon.unmatched_live_total)
        if trend_line:
            lines.append(trend_line)
    elif trend is not None and trend.prior_total:
        lines.append(
            f"Trend vs prior reading @{trend.prior_end}: {trend.prior_total} unmatched then, 0 now."
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


def format_reading(reading: Reading, trend: Trend | None = None) -> str:
    total = reading.approved + reading.staged + reading.rejected + reading.other
    lines = [
        f"**Approval provenance** (`logs/audit.jsonl`, ADR-0012 gate; window "
        f"{reading.window_start} → {reading.window_end}, exclusive of the start "
        f"commit): {total} record(s) — approved {reading.approved}, staged "
        f"{reading.staged}, rejected {reading.rejected}, other {reading.other}."
    ]
    if reading.archived:
        retirements = reading.archived - reading.purged
        detail = f"{retirements} retirement(s)"
        if reading.purged:
            detail += f" and {reading.purged} purge(s) of an already-retired file"
        lines.append(
            f"{reading.archived} of the approved row(s) wrote under "
            f"`{reading.section}/.archive/` — {detail} (ADR-0097 D5 exit). Those "
            "bytes are *meant* not to be live, so they are excluded from the "
            "reconciliation below: a retirement is not an approved-but-not-live "
            "finding. Retirement and purge share the path and are told apart by "
            "the row's `source`, not by where it points."
        )
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
        lines.extend(format_reconciliation(reading.reconciliation, reading.section, trend))
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
    parser.add_argument(
        "--state",
        type=Path,
        default=None,
        help="committed trend baseline (per-section unmatched-live digest sets from the "
        "prior reading); omitted renders no trend line",
    )
    parser.add_argument(
        "--emit-state",
        type=Path,
        default=None,
        help="write this reading's unmatched-live set here (merged per section) instead "
        "of touching --state; the caller promotes it after the report lands",
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
    trend: Trend | None = None
    not_written = ""
    if args.state is not None or args.emit_state is not None:
        recon = reading.reconciliation
        unmatched_set: set[str] = set()
        if recon is not None and recon.reason is None:
            unmatched_set = set(recon.unmatched_live_all)
        trend = read_trend(args.state, args.section, args.end, unmatched_set)
        if args.emit_state is not None and (recon is None or recon.reason is None):
            try:
                emit_state(
                    args.emit_state,
                    args.section,
                    args.end,
                    unmatched_set,
                    trend,
                    state_path=args.state,
                )
            except JoinUnavailable as exc:
                not_written = f"(trend state not written: reason={exc.reason})"
            except OSError as exc:
                not_written = f"(trend state not written: reason={exc.__class__.__name__})"
    print(format_reading(reading, trend))
    if not_written:
        print(not_written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
