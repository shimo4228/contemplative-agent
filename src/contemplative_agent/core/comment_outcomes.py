"""Instrument: what the platform returned about our own comments (RFC-0028).

Two halves, one file each way:

* **write** — :func:`record_comment_outcomes` appends to
  ``logs/comment-outcomes.jsonl`` one record per *reaction* the platform
  showed us (a reply under one of our comments) and one per *state change*
  of the comment itself (upvotes / reply count / thread depth). Append-only,
  deduped by reaction id, untrusted bodies stored as base64 + sha256 + length
  (ADR-0075). Every path that declines to write says why with a reason code —
  no silent fallback.
* **read** — :func:`read_comment_outcomes` joins those outcomes back to the
  skills that were injected into the generation, through the ``publish``
  record in ``skill-selection-*.jsonl``, and returns a per-week distribution.

**No judgment anywhere.** There is no LLM call in this module, and nothing
here feeds selection, extraction or retirement: the reading emits JSON and
stops (skill `read-only-instruments`; RFC-0028 keeps the attribution design —
randomized masking — out of scope). The reading is a *distribution*, not a
contribution estimate: which skill the selector picked is confounded with the
situation it picked it for, which is why :data:`OBSERVATION_NOTE` is written
into every reading rather than left to the reader's memory.

Coverage is bounded by where the reaction data is free. The source is the
comment tree the reply cycle already fetches for **our own posts**
(``GET /posts/{id}/comments``, which carries ids, ``upvotes`` and nested
``replies``); ``/home``'s ``activity_on_your_posts`` carries none of those
columns (Phase 0, 2026-09-09 against ``skill.md``), and reactions to our
comments on *other agents'* posts would need a GET per post that this RFC
does not spend. :data:`COVERAGE_NOTE` says so in the JSON.

The consumption plan (ADR-0101) lives in ADR-0106: read at the Saturday gate,
two windows, then either the reply distribution separates skills or this
instrument is removed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ._io import append_jsonl_restricted, b64_audit_fields, now_iso
from .config import MAX_ID_CHARS, VALID_ID_PATTERN
from .selection_window import (
    PUBLISH_RECORD_KIND,
    SELECTION_RECORD_KIND,
    _is_int,
    _iter_selection_days,
)

logger = logging.getLogger(__name__)


OUTCOME_LOG_NAME = "comment-outcomes.jsonl"


KIND_REPLY = "reply"


KIND_COMMENT_STATE = "comment_state"


# Reply bodies are stored for replay only (nobody decodes them in this
# module). A quarter of the selection log's 65536: a reply is a comment-sized
# body and there are more of them than there are selections.
_MAX_OUTCOME_AUDIT_BYTES = 16384


REASON_NOT_CONFIGURED = "not_configured"


REASON_MISSING_POST_ID = "missing_post_id"


REASON_MISSING_COMMENT_ID = "missing_comment_id"


REASON_MISSING_REPLY_ID = "missing_reply_id"


REASON_WRITE_FAILED = "write_failed"


OBSERVATION_NOTE = (
    "観察分布であり寄与推定ではない。どの skill が注入されたかは selector の判断で、"
    "その判断は状況と交絡する — 行間の差は skill の効果ではなく、その skill が選ばれる"
    "状況の差でもありうる（RFC-0028）。"
)


COVERAGE_NOTE = (
    "反応の観測源は返信サイクルが既に取得している自分の投稿のコメント木のみ"
    "（GET /posts/{id}/comments）。他エージェントの投稿に付けたコメントへの反応は"
    "追加 GET を要するため観測していない。分母 injected_comments が数えるのは"
    "**観測できたコメントだけ**で、観測できなかった公開は unobserved_publishes に"
    "分けてある（沈黙として 0 に数えると全 skill の返信率が一様に下がる）。"
    "unobserved_publishes が observed_publishes を大きく上回る週の行は、"
    "被覆の偏りを見ているのであって反応の差を見ていない。"
)


@dataclass(frozen=True)
class ObservedComment:
    """One node of a fetched comment tree, normalized by the adapter.

    The platform's JSON shape (and the ``is_self`` decision over it) belongs
    to the adapter; this module owns the record schema. Keeping the boundary
    here is what lets ``core`` record outcomes without importing an adapter,
    and what keeps the field-name fallbacks in one place instead of two.
    """

    comment_id: str
    is_own: bool
    upvotes: int | None
    body: str
    replies: tuple[ObservedComment, ...] = ()


@dataclass(frozen=True)
class OutcomeScan:
    """What one scan of one post's comment tree did — countable, not inferred."""

    written: int = 0
    duplicates: int = 0
    own_comments: int = 0
    reasons: tuple[str, ...] = ()


_audit_dir: Path | None = None


_seen_keys: set[str] | None = None


def configure_comment_outcomes(audit_dir: Path | None = None) -> None:
    """Configure the recorder (same module-global pattern as
    ``configure_skill_selection``).

    ``audit_dir`` unset disables it: the hook in the reply cycle becomes a
    no-op that still reports :data:`REASON_NOT_CONFIGURED`, so a disabled
    instrument is visible rather than indistinguishable from an idle one.
    The dedupe cache is dropped here so a re-configuration (tests, a second
    CLI invocation in-process) cannot inherit another store's keys.
    """
    global _audit_dir, _seen_keys
    _audit_dir = audit_dir
    _seen_keys = None


def _log_path() -> Path | None:
    return None if _audit_dir is None else _audit_dir / OUTCOME_LOG_NAME


def _seen(path: Path) -> set[str]:
    """Dedupe keys already in the log, read once per process.

    The log is append-only, so the process that appends is also the only one
    adding keys to this set — re-reading the file per scan would pay for the
    whole history on every post.
    """
    global _seen_keys
    if _seen_keys is not None:
        return _seen_keys
    keys: set[str] = set()
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("dedupe_key"), str):
                    keys.add(rec["dedupe_key"])
        except (OSError, ValueError):
            # Named, not swallowed: a log we cannot read means the dedupe set
            # is empty and the next scan will re-append reactions it already
            # holds. The reading tolerates that (it counts distinct ids), but
            # the operator should see why the file grew.
            logger.warning("comment outcomes: %s unreadable, dedupe set is empty", path.name)
    _seen_keys = keys
    return keys


def _walk(node: ObservedComment, depth: int) -> Iterable[tuple[ObservedComment, int]]:
    for child in node.replies:
        yield child, depth
        yield from _walk(child, depth + 1)


def _valid_id(value: str) -> bool:
    """Ids reach this module off an untrusted response and become log keys
    (``comment_id``, ``reply_id``, ``dedupe_key``), so they are held to the
    same shape the client requires of every id it sends.

    Two things depend on it: the outcome log stays free of plaintext
    attacker-chosen strings — the invariant that lets this repo classify
    ``logs/*.jsonl`` as readable, since untrusted *bodies* are base64 — and
    the reading's join key stays a bounded token. The publish side already
    did this (``adapters/moltbook/publish.created_comment_id``); this is the
    same check on the other path (security review 2026-09-09).
    """
    return bool(value) and len(value) <= MAX_ID_CHARS and bool(VALID_ID_PATTERN.match(value))


def record_comment_outcomes(
    post_id: str,
    comments: Sequence[ObservedComment],
    *,
    now: str | None = None,
) -> OutcomeScan:
    """Append the reactions visible in one fetched comment tree.

    ``comments`` is the tree as the adapter normalized it; only subtrees
    rooted at one of *our* comments are recorded, and every descendant of
    such a comment is a reaction to it (``by_self`` marks our own
    continuations so the reading can exclude them from a reply rate).

    Returns an :class:`OutcomeScan`; it never raises. A broken instrument
    must not break the reply cycle it observes (degrade-never-abort), and
    every degradation carries a reason code.
    """
    path = _log_path()
    if path is None:
        return OutcomeScan(reasons=(REASON_NOT_CONFIGURED,))
    if not _valid_id(post_id):
        return OutcomeScan(reasons=(REASON_MISSING_POST_ID,))
    ts = now or now_iso("seconds")
    reasons: list[str] = []
    written = 0
    duplicates = 0
    own = 0
    try:
        seen = _seen(path)
        for root in comments:
            for node, depth in _walk_own_roots(root):
                if not node.is_own:
                    continue
                own += 1
                if not _valid_id(node.comment_id):
                    _note(reasons, REASON_MISSING_COMMENT_ID)
                    continue
                written_here, dup_here = _record_own_comment(path, seen, post_id, node, ts, reasons)
                written += written_here
                duplicates += dup_here
                del depth
    except OSError as exc:
        logger.warning("comment outcomes: write failed (%s)", exc)
        _note(reasons, REASON_WRITE_FAILED)
    return OutcomeScan(
        written=written, duplicates=duplicates, own_comments=own, reasons=tuple(reasons)
    )


def _walk_own_roots(node: ObservedComment) -> Iterable[tuple[ObservedComment, int]]:
    """The node itself and every descendant, so a comment of ours nested
    under someone else's still gets its own subtree recorded.

    Every own node found here becomes a subtree root; :func:`_reactions_to`
    is what stops the roots from overlapping."""
    yield node, 0
    yield from _walk(node, 1)


def _reactions_to(node: ObservedComment) -> Iterable[tuple[ObservedComment, int]]:
    """The descendants that are reactions to *this* comment, with their depth.

    A comment of ours nested under another comment of ours is recorded as its
    own subtree, so its descendants belong to it and not also to the outer
    one — counting them twice would inflate the reply rate that decides
    whether this instrument survives (security review 2026-09-09). The
    traversal therefore stops at a nested own comment: that node still yields
    (it *is* a reaction to the outer one — we answered ourselves) but its
    children go to it.
    """
    for child in node.replies:
        yield child, 1
        if child.is_own:
            continue
        for grandchild, depth in _reactions_to(child):
            yield grandchild, depth + 1


def _record_own_comment(
    path: Path,
    seen: set[str],
    post_id: str,
    node: ObservedComment,
    ts: str,
    reasons: list[str],
) -> tuple[int, int]:
    written = 0
    duplicates = 0
    reply_count = 0
    max_depth = 0
    for child, depth in _reactions_to(node):
        max_depth = max(max_depth, depth)
        if not child.is_own:
            reply_count += 1
        if not _valid_id(child.comment_id):
            _note(reasons, REASON_MISSING_REPLY_ID)
            continue
        key = f"reply:{child.comment_id}"
        if key in seen:
            duplicates += 1
            continue
        append_jsonl_restricted(
            path,
            {
                "kind": KIND_REPLY,
                "ts": ts,
                "post_id": post_id,
                "comment_id": node.comment_id,
                "reply_id": child.comment_id,
                "depth": depth,
                "by_self": child.is_own,
                "dedupe_key": key,
                **b64_audit_fields("reply_body", child.body, max_bytes=_MAX_OUTCOME_AUDIT_BYTES),
            },
        )
        seen.add(key)
        written += 1
    upvotes = node.upvotes if _is_int(node.upvotes) else None
    state_key = f"state:{node.comment_id}:{upvotes}:{reply_count}:{max_depth}"
    if state_key in seen:
        duplicates += 1
    else:
        append_jsonl_restricted(
            path,
            {
                "kind": KIND_COMMENT_STATE,
                "ts": ts,
                "post_id": post_id,
                "comment_id": node.comment_id,
                "upvotes": upvotes,
                "reply_count": reply_count,
                "has_reply": reply_count > 0,
                "max_depth": max_depth,
                "dedupe_key": state_key,
            },
        )
        seen.add(state_key)
        written += 1
    return written, duplicates


def _note(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


# ---------------------------------------------------------------------------
# Reading (read-only; nothing below writes or decodes an untrusted payload)
# ---------------------------------------------------------------------------


def _outcome_state_by_comment(log_dir: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Latest state record per comment id, plus the malformed-line count.

    Only ``comment_state`` rows are read. The ``reply`` rows carry the
    base64 bodies and this reading has no business opening them — the same
    rule ``scripts/skillsel_reading.py`` states for the selection log.
    """
    path = log_dir / OUTCOME_LOG_NAME
    states: dict[str, dict[str, Any]] = {}
    malformed = 0
    if not path.exists():
        return states, malformed
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        logger.warning("comment outcomes reading: %s unreadable", path.name)
        return states, malformed
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(rec, dict) or rec.get("kind") != KIND_COMMENT_STATE:
            continue
        comment_id = rec.get("comment_id")
        if isinstance(comment_id, str) and comment_id:
            # Later record wins: the state rows are a change log, so the last
            # one is the newest observation of that comment.
            states[comment_id] = rec
    return states, malformed


@dataclass(frozen=True)
class _SelectionScan:
    """Both record families of one window's selection logs, kept apart.

    ``selections`` maps selection id → the skills injected; ``publishes`` is
    the publish records with their file date attached (the join key is the id,
    but the maturity cut is by day).
    """

    selections: dict[str, list[str]]
    publishes: tuple[dict[str, Any], ...]
    days_read: tuple[str, ...]
    unreadable_days: int
    malformed_rows: int


def _scan_selection_families(log_dir: Path, since: date, until: date) -> _SelectionScan:
    selections: dict[str, list[str]] = {}
    publishes: list[dict[str, Any]] = []
    days_read: list[str] = []
    unreadable_days = 0
    malformed_rows = 0
    for day_file in _iter_selection_days(log_dir, lambda d: since <= d <= until, kind=None):
        if not day_file.readable:
            unreadable_days += 1
            continue
        days_read.append(day_file.date_part)
        malformed_rows += day_file.malformed_rows
        for rec in day_file.records:
            sel_id = rec.get("selection_id")
            if not isinstance(sel_id, str) or not sel_id:
                # Pre-RFC-0028 selections have no id and cannot be joined to a
                # comment. They still count in the selection instruments; here
                # they are simply outside the join.
                continue
            kind = rec.get("kind", SELECTION_RECORD_KIND)
            if kind == SELECTION_RECORD_KIND:
                selected = rec.get("selected")
                if isinstance(selected, list):
                    selections[sel_id] = [s for s in selected if isinstance(s, str)]
            elif kind == PUBLISH_RECORD_KIND:
                publishes.append({**rec, "_day": day_file.file_date})
    return _SelectionScan(
        selections=selections,
        publishes=tuple(publishes),
        days_read=tuple(days_read),
        unreadable_days=unreadable_days,
        malformed_rows=malformed_rows,
    )


def read_comment_outcomes(
    log_dir: Path,
    *,
    since: date,
    until: date,
    min_age_days: int = 2,
) -> dict[str, Any]:
    """Per-skill reaction distribution for one week, as JSON-ready data.

    Joins three record families, all already on disk:
    ``selection`` (which skills were injected) → ``publish`` (which comment
    that generation became) → ``comment_state`` (what came back).

    ``min_age_days`` drops comments published too recently for their
    reactions to have arrived (RFC-0028 Drawbacks: replies land hours to days
    later, so the tail of a window otherwise reads as silence). The excluded
    count is reported rather than hidden.
    """
    scan = _scan_selection_families(log_dir, since, until)
    selections = scan.selections
    publishes = scan.publishes
    days_read = scan.days_read
    unreadable_days = scan.unreadable_days
    cutoff = until.toordinal() - min_age_days
    states, outcome_malformed = _outcome_state_by_comment(log_dir)
    malformed_rows = scan.malformed_rows + outcome_malformed

    # skill -> one (had a reply, observed thread depth) pair per injected
    # comment. A list rather than running totals so the reading stays a
    # distribution: the mean below is derived, and nothing here can be
    # mistaken for a stored score.
    rows: dict[str, list[tuple[bool, int]]] = {}
    publish_failures = 0
    unjoined = 0
    immature = 0
    joined = 0
    unobserved = 0
    observed = 0
    for pub in publishes:
        comment_id = pub.get("comment_id")
        if not isinstance(comment_id, str) or not comment_id:
            publish_failures += 1
            continue
        day: date = pub["_day"]
        if day.toordinal() > cutoff:
            immature += 1
            continue
        skills = selections.get(str(pub.get("selection_id")))
        if skills is None:
            unjoined += 1
            continue
        joined += 1
        state = states.get(comment_id)
        if state is None:
            # A published comment the recorder never saw — it lives under
            # another agent's post, or our own post drew no activity for the
            # reply cycle to fetch. Counting it as an observed "no reply"
            # would drive every rate toward zero and make ADR-0106's exit
            # criterion unreachable, so it is excluded and named instead
            # (code review 2026-09-09).
            unobserved += 1
            continue
        observed += 1
        has_reply = bool(state.get("has_reply"))
        depth = state.get("max_depth")
        depth = depth if _is_int(depth) else 0
        for skill in skills:
            rows.setdefault(skill, []).append((has_reply, depth))

    skills_json = [
        {
            "skill": name,
            "injected_comments": len(observations),
            "comments_with_reply": sum(1 for replied, _ in observations if replied),
            "reply_rate": (
                sum(1 for replied, _ in observations if replied) / len(observations)
                if observations
                else 0.0
            ),
            "mean_thread_depth": (
                sum(depth for _, depth in observations) / len(observations) if observations else 0.0
            ),
        }
        for name, observations in sorted(rows.items())
    ]
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "min_age_days": min_age_days,
        "generated_at": now_iso("seconds"),
        "days_read": list(days_read),
        "unreadable_days": unreadable_days,
        "malformed_rows": malformed_rows,
        "joined_publishes": joined,
        "publish_failures": publish_failures,
        "unjoined_publishes": unjoined,
        "excluded_immature_publishes": immature,
        # Windowed, like every other count here: the number of this window's
        # publishes the recorder actually observed. A history-wide count of
        # the outcome log would grow every week and read as growing coverage.
        "observed_publishes": observed,
        "unobserved_publishes": unobserved,
        "skills": skills_json,
        "observation_note": OBSERVATION_NOTE,
        "coverage_note": COVERAGE_NOTE,
    }
