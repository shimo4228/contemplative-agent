"""Approval gate: audit logging and the interactive approval loop (ADR-0012).

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, get_args

from ..adapters.moltbook import config
from ..core._io import (
    append_jsonl_restricted,
    now_iso,
)

logger = logging.getLogger(__name__)


AUDIT_LOG_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "audit.jsonl"


AuditSource = Literal[
    "direct",
    "stage",
    "stage-adopted",
    "stage-adopted-names",
    "stage-adopted-auto",
    "stage-rejected-names",
    "stage-archived-names",
    "direct-remove",
    "direct-remove-auto",
    "direct-archive",
    "direct-archive-auto",
    "direct-purge",
    "direct-purge-auto",
    "correction",
]


# Why a gate said no (P1-12.1, ``schemas/audit.schema.json``). A closed enum
# plus the free text in ``reason``: the enum is what a later reader can count,
# the text is what the human actually meant. ``other`` is a real answer, not a
# default - a rejection with no code at all is the failure this field exists
# to make visible.
ReasonCode = Literal["duplicate", "off-constitution", "low-quality", "stale", "other"]
REASON_CODES: tuple[str, ...] = get_args(ReasonCode)

# Which door the decision came through (P1-12.1). Separates "a human answered a
# prompt" from "a human's choice was transcribed by someone else", which the
# bare ``source`` string only implied.
#   tty        - a prompt was shown to a terminal
#   names-file - the choice sits in a names FILE (--adopt-names / --reject-names
#                / --archive-names); the process showed no prompt
#   yes-flag   - --yes said "everything"
#   headless   - no terminal and no human at the keyboard (scheduled producers,
#                a piped prompt)
Channel = Literal["tty", "names-file", "yes-flag", "headless"]
CHANNELS: tuple[str, ...] = get_args(Channel)

# The directory a rejected candidate's text is moved into instead of being
# destroyed (P1-12.2). Under MOLTBOOK_HOME, named ``<ts>-<content_hash>.md``
# where ``content_hash`` is the audit row's key.
REJECTED_DIRNAME = ".rejected"

# The verdict recorded in ``audit.jsonl``. ``source`` says which path reached
# the gate; this says what the gate decided.
#
# **This is the writer's vocabulary, not the log's.** ``audit.jsonl`` is
# append-only, and rows written between 2026-08-15 and 2026-09-19 carry a
# fifth verdict, ``held`` (the deferral ``adopt-staged --hold-names`` wrote;
# removed by RFC-0042 work item 5). Every reader must keep tolerating it: the
# ADR-0093 approval join counts ``decision == "approved"`` and
# ``value_layer_due_check``'s constitution branch filters on a decision
# allowlist, so a ``held`` row falls through both rather than being miscounted
# — which is also how any future value would behave. The same script's
# identity branch does not filter on decision at all (it selects on
# ``source``), so it never learned the word in the first place. The census
# registry's ``audit.jsonl`` entry still lists ``held`` on purpose: it
# classifies historical rows.
Decision = Literal["staged", "approved", "rejected", "validation_failed", "corrected"]


_UNREADABLE_PREV = "unreadable"
_TAIL_CHUNK = 65536


def _last_line_digest(path: Path) -> str | None:
    """``sha256(raw bytes of the last line)[:16]``; None when there is none.

    The ``prev`` link of the audit chain (ADR-0012, 2026-10-09 addendum).
    Hashes the line exactly as it sits on disk — after
    ``append_jsonl_restricted`` has stamped ``run_id`` / ``session_id`` into
    it — because that is what a later edit would have to change. Reads
    backwards in chunks until a newline precedes the final line, so a row
    longer than one chunk (a long ``source_ids`` list) is still hashed whole.
    ``None`` for a missing or empty file: the first row has no predecessor.

    Raises ``OSError`` for anything other than a missing file; the caller
    records that as ``"unreadable"`` rather than as a clean link.
    """
    try:
        with path.open("rb") as f:
            pos = f.seek(0, os.SEEK_END)
            buf = b""
            while pos > 0:
                start = max(0, pos - _TAIL_CHUNK)
                f.seek(start)
                buf = f.read(pos - start) + buf
                pos = start
                stripped = buf.rstrip(b"\n")
                if b"\n" in stripped or pos == 0:
                    break
    except FileNotFoundError:
        return None
    stripped = buf.rstrip(b"\n")
    if not stripped:
        return None
    return hashlib.sha256(stripped.rsplit(b"\n", 1)[-1]).hexdigest()[:16]


def _log_approval(
    command: str,
    path: Path,
    approved: bool | None,
    content: str,
    *,
    source: AuditSource = "direct",
    snapshot_path: Path | str | None = None,
    reason: str | None = None,
    source_ids: Sequence[str] | None = None,
    epistemic_counts: dict[str, int] | None = None,
    reason_code: str | None = None,
    channel: str | None = None,
    session: str | None = None,
    approver: str | None = None,
) -> bool:
    """Append approval decision to audit log; False when it did not reach disk.

    Args:
        command: The CLI subcommand name (e.g. "insight", "distill-identity").
        path: Final target path for the generated content.
        approved: True = accepted, False = rejected, None = staged (not yet decided).
        content: Full text of the generated artifact (for hashing).
        source: Execution path identifier.
            - "direct": approval gate was invoked inline during the command run.
            - "stage": written to staging dir (decision deferred).
            - "stage-adopted": adopted interactively from staging via `adopt-staged`
              (a human answered the y/N prompt for this item).
            - "stage-adopted-names": adopted via `adopt-staged --adopt-names FILE`
              (per-item selection transcribed from a human decision, but no
              prompt was shown in this process — the provenance is the names
              file, not a TTY. Distinct so the audit trail never conflates the
              two; 2026-08-01 security review C1).
            - "stage-adopted-auto": adopted from staging via
              `adopt-staged --yes --reason TEXT` (blanket adoption; no prompt
              is shown in this process). It is a stand-in for the TTY answer,
              typed only in a session where a human is present and has read
              the batch, and it must carry that human's `reason`
              (ADR-0012, 2026-10-24 addendum). It is not a coding agent's
              approval: Claude Code explains and transcribes, it does not
              approve.
            - "stage-rejected-names": a staged item rejected by name via
              `adopt-staged --reject-names FILE` (RFC-0042 work item 9).
              Transcribed like "stage-adopted-names" and distinct from it for
              the same reason "stage-archived-names" is: the source is what
              separates a rejection from an adoption for a later reader, and
              a saturated store makes the all-reject week the common one.
            - "stage-archived-names": a store skill retired by
              `adopt-staged --archive-names FILE` — MOVED to `skills/.archive/`,
              not deleted (ADR-0097 D5). Transcribed like
              "stage-adopted-names": the decision is the names file, and no
              prompt is ever shown for an archive.
            - "direct-remove": a live store skill DELETED via
              `remove-skill --delete` (interactive).
            - "direct-remove-auto": the same with `--yes`.
            - "direct-archive": a live store skill retired via `remove-skill`
              — MOVED to `skills/.archive/`, restorable with `mv`
              (interactive).
            - "direct-archive-auto": the same with `--yes`.
            - "direct-purge": a file ALREADY in `skills/.archive/` deleted via
              `remove-skill --delete` (interactive). The archive is otherwise
              never pruned, so this is the one path that destroys retired
              text and it gets its own value rather than sharing
              "direct-remove".
            - "direct-purge-auto": the same with `--yes`.

            The three retirement outcomes are separated HERE, in a
            categorical field, and not by whether the row's ``path`` happens
            to sit under `.archive/`: a path convention is not a contract,
            and `direct-purge` rows carry an `.archive/` path while meaning
            the opposite of an archive (silent-failure review 2026-08-22).
        snapshot_path: Pivot snapshot directory written at run start (ADR-0020),
            recorded ``MOLTBOOK_HOME``-relative. ``None`` when the command did
            not produce one. Staged commands do produce one: ``stage`` rows
            carry it, and it rides the ``.meta.json`` ``snapshot`` key to the
            ``stage-adopted-*`` / ``stage-rejected-names`` row (P1-12.9), so a
            decision joins back to the run that generated its candidate.
        reason: Human-provided justification for the action (free text).
            Required for ``remove-skill``, for ``adopt-staged --yes`` (ADR-0012
            2026-10-24 addendum) and for rejections taken through a names
            file; the field is always present in the record (null when
            omitted) for forward compat.
        reason_code: One of :data:`REASON_CODES`; why a candidate was
            rejected. Always present (null for rows that are not rejections).
        channel: One of :data:`CHANNELS`. ``None`` derives it from ``source``
            (``stage`` -> headless, ``*-auto`` -> yes-flag, ``*-names`` ->
            names-file, otherwise tty when stdin is a terminal, else
            headless), so a call site only passes it to override.
        session: The session the decision was taken in - a Claude Code
            session id (``CLAUDE_CODE_SESSION_ID`` / ``MOLTBOOK_GATE_SESSION``)
            or null. Lets "who approved" and "who transcribed" be read apart:
            ``approver`` is a human string, ``session`` names the transcriber.
        approver: The human who made the decision (P1-12.1 PR-C, D-P1-12-2 =
            B). Comes from the signature line of the names FILE, the
            ``--approver`` flag or ``MOLTBOOK_OPERATOR`` - never from a
            constant in this code, because a fixed string would read the same
            whoever typed the command. Null when nothing said.
        source_ids: Lineage keys of the artifact's inputs (ADR-0050) —
            pattern content-hash ids for insight / distill-identity /
            amend-constitution, skill filenames for rules-distill. Always
            present in the record (null when the command has no lineage).
            Empty collections are deliberately normalized to null: every
            lineage-tracked command has ≥1 input by construction, so
            "tracked but empty" does not occur and null uniformly means
            "no lineage attached".
        epistemic_counts: Provenance-kind tally (generated/unknown) of the
            artifact's input patterns (ADR-0050, ADR-0082). Always present in
            the record (null when not applicable; empty dicts normalize to
            null, same rationale). NOT an external-grounding metric — external
            content enters as grounding text inside the rich render and was
            never counted here. Records written before ADR-0082 also carry a
            structurally-zero ``observed`` key; read with ``.get(...)``.

    The record also carries ``path`` relative to ``MOLTBOOK_HOME`` when the
    target is inside it (an absolute path pins a machine, and the roadmap's
    join keys on ``content_hash`` anyway), and ``prev`` (added by ``_log_decision``): the first 16
    hex of ``sha256`` over the raw previous line of the log, ``null`` for the
    first row, ``"unreadable"`` when the log existed but could not be read.
    Rows written before the field existed lack the key.
    """
    if approved is None:
        decision: Decision = "staged"
    elif approved:
        decision = "approved"
    else:
        decision = "rejected"
    return _log_decision(
        decision,
        command,
        path,
        content,
        source=source,
        snapshot_path=snapshot_path,
        reason=reason,
        source_ids=source_ids,
        epistemic_counts=epistemic_counts,
        reason_code=reason_code,
        channel=channel,
        session=session,
        approver=approver,
    )


def content_hash(content: str) -> str:
    """The audit key: ``sha256(content)[:16]``.

    One spelling, because the ``.rejected/`` file name has to equal the audit
    row's ``content_hash`` (P1-12.2) and two copies of the formula are how
    that stops being true.
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def home_relative(path: Path | str) -> str:
    """``path`` relative to ``MOLTBOOK_HOME`` (POSIX) when inside it, else as given.

    The audit log used to record the absolute path of whatever home was live,
    which ties a row to one machine and made the join script match on path
    *components* to cope. Relative is stable across homes; a target outside
    the home (a custom ``--constitution-dir``) stays absolute, which is the
    honest record of where it went.
    """
    raw = Path(path)
    if not raw.is_absolute():
        return raw.as_posix()
    root = config.MOLTBOOK_DATA_DIR
    for base in (root, root.resolve()):
        try:
            return raw.relative_to(base).as_posix()
        except ValueError:
            continue
    return str(raw)


def derive_channel(source: str) -> Channel:
    """The channel implied by ``source`` when the call site did not name one."""
    if source == "stage":
        return "headless"
    if source.endswith("-auto"):
        return "yes-flag"
    if source.endswith("-names"):
        return "names-file"
    return "tty" if _stdin_is_tty() else "headless"


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def ambient_session() -> str | None:
    """The gate session id from the environment, or None.

    Best effort: ``CLAUDE_CODE_SESSION_ID`` where the host exports it,
    ``MOLTBOOK_GATE_SESSION`` for a session id the operator (or the weekly
    chain's ``run_id``) wants to stamp by hand.
    """
    for key in ("CLAUDE_CODE_SESSION_ID", "MOLTBOOK_GATE_SESSION"):
        value = os.environ.get(key, "").strip()
        if value:
            return value[:80]
    return None


def ambient_approver() -> str | None:
    """``MOLTBOOK_OPERATOR`` - an override, never a source of truth.

    ``docs/GOVERNANCE.md`` names the Accountable operator; the environment
    only lets a second named human sign for themselves. See ``approver`` in
    :func:`_log_approval`.
    """
    value = os.environ.get("MOLTBOOK_OPERATOR", "").strip()
    return value[:80] or None


def preserve_rejected(text: str) -> Path | None:
    """Keep a rejected candidate's text under ``MOLTBOOK_HOME/.rejected/``.

    P1-12.2. The reject paths used to ``unlink`` the staged body, leaving the
    audit row's 16-hex hash as the only trace of what a human said no to. The
    file is named ``<UTC ts>-<content_hash>.md`` with the hash computed by
    :func:`content_hash` over the same text the audit row hashes, so the row
    leads to the file. Written with mode 0600; never published from here (the
    sync excludes it, publication is a separate decision).

    Returns the path, or None when it could not be written - the caller
    decides whether that blocks the rejection (the adopt paths do, so a
    rejection is never recorded for text that was not kept).
    """
    from ..core._io import write_restricted

    stamp = now_iso(timespec="seconds").replace("-", "").replace(":", "")
    stamp = stamp.split("+")[0] + "Z"
    target_dir = config.MOLTBOOK_DATA_DIR / REJECTED_DIRNAME
    target = target_dir / f"{stamp}-{content_hash(text)}.md"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        write_restricted(target, text)
    except OSError as err:
        logger.warning("Could not preserve rejected text under %s: %s", target_dir, err)
        return None
    return target


def _log_decision(
    decision: Decision,
    command: str,
    path: Path,
    content: str,
    *,
    source: AuditSource,
    snapshot_path: Path | str | None,
    reason: str | None,
    source_ids: Sequence[str] | None,
    epistemic_counts: dict[str, int] | None,
    reason_code: str | None = None,
    channel: str | None = None,
    session: str | None = None,
    approver: str | None = None,
    extra: dict[str, str] | None = None,
) -> bool:
    """Append one audit record; False when it did not reach disk.

    Single owner of the row shape, so no verdict can grow (or lose) a field
    the others have — a replay harness keying on a field only approvals
    carry would silently skip every other verdict.

    The return value exists for callers whose durable evidence IS this row —
    ``skill_archive``'s supersede stamp reads it, because swallowing the write
    failure there leaves a moved file with nothing in the audit log and the
    process exiting 0 (security review 2026-08-15). The adopt-staged paths
    read it too since P1-12.3: an approval whose row did not reach disk is
    not carried out, and a rejection whose row did not reach disk leaves the
    item staged. (The older reading - "their own mutation is the evidence" -
    let ``audit.jsonl`` miss an adoption while the process exited 0, which is
    the failure the record exists to rule out.)
    """
    if reason_code is not None and reason_code not in REASON_CODES:
        raise ValueError(f"reason_code {reason_code!r} is not one of {REASON_CODES}")
    if channel is not None and channel not in CHANNELS:
        raise ValueError(f"channel {channel!r} is not one of {CHANNELS}")
    try:
        prev: str | None = _last_line_digest(AUDIT_LOG_PATH)
    except OSError:
        prev = _UNREADABLE_PREV
    record = {
        "ts": now_iso(timespec="seconds"),
        "command": command,
        "path": home_relative(path),
        "decision": decision,
        "source": source,
        "content_hash": content_hash(content),
        "snapshot_path": home_relative(snapshot_path) if snapshot_path is not None else None,
        "reason": reason,
        "reason_code": reason_code,
        "channel": channel if channel is not None else derive_channel(source),
        "session": session if session is not None else ambient_session(),
        "approver": approver if approver is not None else _default_approver(decision),
        "source_ids": list(source_ids) if source_ids else None,
        "epistemic_counts": dict(epistemic_counts) if epistemic_counts else None,
        "prev": prev,
    }
    if extra:
        # Only a correction row has extra keys (schemas/audit.schema.json);
        # the verdict rows share one shape.
        record.update(extra)
    try:
        append_jsonl_restricted(AUDIT_LOG_PATH, record)
    except OSError:
        logger.warning("Failed to write audit log: %s", AUDIT_LOG_PATH)
        return False
    return True


def log_correction(
    *,
    corrects_ts: str,
    content_hash_of_corrected: str,
    mv_from: str,
    mv_to: str,
    sha_checked: str,
    approver: str,
    reason: str,
) -> bool:
    """Append a ``command: correction`` row for an earlier row's wrong ``path``.

    P1-12.4. Two approved rows (constitution 2026-08-09, identity 2026-08-15)
    name a path that never held the bytes: the H5 collision guard wrote an
    inert twin and the owner ``mv``'d the file into place by hand. The log is
    append-only, so the repair is a new row - who (``approver``), when
    (``ts``), what (``mv_from`` -> ``mv_to``) and the evidence
    (``sha_checked``, the live file's digest verified equal to the corrected
    row's ``content_hash``). The row reuses ``_log_decision`` so it carries the
    ``prev`` link like any other. The corrected row stays as written; a reader
    joins the two by ``content_hash``.

    The row's own ``content_hash`` is the corrected row's, not a hash of any
    new text (``extra`` overrides the writer's): the correction is about that
    artifact.
    """
    return _log_decision(
        "corrected",
        "correction",
        Path(mv_to),
        "",
        source="correction",
        snapshot_path=None,
        reason=reason,
        source_ids=None,
        epistemic_counts=None,
        channel="headless",
        approver=approver,
        extra={
            "content_hash": content_hash_of_corrected,
            "corrects_ts": corrects_ts,
            "mv_from": mv_from,
            "mv_to": mv_to,
            "sha_checked": sha_checked,
        },
    )


def _default_approver(decision: str) -> str | None:
    """The ambient override for a human verdict; a staged row has no approver."""
    return ambient_approver() if decision != "staged" else None


def _approve(prompt: str) -> bool:
    """Prompt user for y/N approval. Default is N (safe side)."""
    print(f"\n{prompt} [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _approve_write(path: Path) -> bool:
    return _approve(f"Write to {path}?")


def _approve_delete(path: Path) -> bool:
    return _approve(f"Delete {path}?")


def same_text(existing: str, text: str) -> bool:
    """The idempotent-overwrite rule: equal once surrounding whitespace is off.

    One implementation, because ``adopt``'s budget projection has to answer
    this exactly as the write path does — the instrument's invariant is that
    the projection mirrors what the loop will do (codex 2026-07-10 P2), and
    two spellings of the rule are how that quietly stops being true.
    """
    return existing.strip() == text.strip()


def same_content(path: Path, text: str) -> bool:
    """:func:`same_text` against a file; an unreadable file counts as different."""
    try:
        return same_text(path.read_text(encoding="utf-8"), text)
    except OSError:
        return False


def _collision_free_path(target_path: Path, text: str) -> Path:
    """Return a write path that will not silently clobber a different file.

    Two batches in one run (or across runs on the same day) can slugify to
    the same ``<slug>-YYYYMMDD.md``; the second approved write previously
    overwrote the first with no warning, while audit.jsonl recorded both as
    "approved" (bug-audit 2026-07-06 H5). Identical content keeps the
    original path (idempotent re-write); differing content gets a ``-2``,
    ``-3``… suffix before the extension. A suffixed path whose content
    already matches is also reused (codex review 2026-07-06: a rerun of the
    same collision batch must not mint ``-3`` when an identical ``-2``
    exists). Same-minute M12 reprocessing regenerates DIFFERENT text for the
    same sources (LLM non-determinism), so this guard cannot recognize that
    case as a duplicate — stocktake dedup catches it downstream.
    """
    if not target_path.exists():
        return target_path

    if same_content(target_path, text):
        return target_path
    for n in range(2, 100):
        candidate = target_path.with_name(f"{target_path.stem}-{n}{target_path.suffix}")
        if not candidate.exists() or same_content(candidate, text):
            print(
                f"  Name collision: {target_path.name} exists with different "
                f"content; writing {candidate.name} instead"
            )
            return candidate
    raise RuntimeError(f"No collision-free name available for {target_path} after 98 tries")


def _run_approval_loop(
    items: Sequence[Any],
    *,
    command: str,
    target_dir: Path,
    snapshot_path: Path | None = None,
) -> int:
    """Iterate generated artifacts through the approval gate, write approved.

    Each item must expose ``filename``, ``text``, and ``target_path``
    (``SkillResult`` from core/ and ``StageItem`` here match this shape —
    kept structural to avoid dragging core types into the cli module
    signature).

    The per-handler post-loop hook (``write_last_insight``) and summary
    prints stay at the call site because the wording differs ("written" vs
    "revised", per-handler counters).

    Returns the count of approved+written items so the caller can
    decide whether to fire its post-loop hook.
    """
    from ..core._io import write_restricted

    written = 0
    for i, item in enumerate(items, 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(items)}] {item.filename}")
        print(item.text)
        # ADR-0069: show the reasoning trace (think-ON pipelines) so the owner
        # approves with the *why* visible. getattr keeps StageItem-shaped items
        # (no ``thinking`` attribute) working unchanged.
        thinking = getattr(item, "thinking", None)
        if thinking:
            print(f"\n--- Reasoning ---\n{thinking}")
        # Resolve slug collisions BEFORE the gate so the owner approves —
        # and the audit records — the path actually written (H5).
        target_path = _collision_free_path(item.target_path, item.text)
        approved = _approve_write(target_path)
        _log_approval(
            command,
            target_path,
            approved,
            item.text,
            snapshot_path=snapshot_path,
            # ADR-0050: SkillResult carries pattern_ids, StageItem carries
            # source_ids; the getattr pair accepts either shape and an item
            # with neither logs null lineage.
            source_ids=(getattr(item, "pattern_ids", None) or getattr(item, "source_ids", None)),
            epistemic_counts=getattr(item, "epistemic_counts", None),
        )
        if approved:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_restricted(target_path, item.text)
            written += 1
        else:
            preserve_rejected(item.text)
            print("Skipped.")
    return written
