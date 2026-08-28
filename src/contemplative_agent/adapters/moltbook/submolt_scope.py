"""Submolt-scope instrument (ADR-0086).

A read-only sweep that samples posts from **every** submolt the platform
lists — the eight this agent subscribes to and the ones it does not — and
scores each with the production relevance scorer. The scores land in an
append-only audit log; the ``report --submolt-scope`` reading aggregates
them.

The question it exists to answer is whether the human-curated
``domain.json`` scope is leaving relevant peers unread, and by extension
whether the agent choosing its own scope would beat the hand-picked eight.
Neither question has any evidence today: the production relevance
distribution only contains posts that already passed the subscribed-submolt
gate, so it cannot say anything about the submolts outside it.

Three constraints follow from ADR-0071 (instruments are observability, never
intervention) and ADR-0076 (shadow first, enforcement later):

* **The trust boundary does not move.** This module never subscribes,
  unsubscribes, comments, upvotes, or touches ``subscribed_submolts``. The
  ``feed_manager`` gate that skips posts from non-subscribed submolts is
  untouched, so nothing observed here can reach an outward action.
* **Nothing observed is retained as knowledge.** Sampled posts are scored
  and written to this instrument's own log. They never enter the episode
  log, the pattern store, or identity — an instrument must not become a
  back door into the memory pipeline.
* **The instrument is disableable by construction.** ``audit_dir`` unset
  makes ``scan_submolt_scope`` a no-op that touches no network and no LLM.
  Since the CLI always has a log directory to hand, the switch an operator
  can actually reach is ``MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1``, which forces
  the same state — an installed sweep can be neutered without uninstalling
  its launchd job.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ...core._io import append_jsonl_restricted, b64_audit_fields, now_iso, strip_to_printable
from ...core.domain import DomainConfig
from ...core.llm import circuit_shield
from ...core.run_context import new_session_id
from .client import MoltbookClient, MoltbookClientError, SubmoltInfo
from .config import ADAPTIVE_BACKOFF
from .llm_functions import score_relevance_detailed

logger = logging.getLogger(__name__)

# One feed GET returns 20 posts, so this is the whole page and needs no
# pagination. Weekly cadence over ~20 submolts puts the scan at ~400 local
# LLM calls — the reason this runs on its own schedule rather than inside a
# session (16 GB box, one Ollama).
DEFAULT_SAMPLE_SIZE = 20

# Sampled post bodies are untrusted external text kept for replay. The
# submolt feed serves a 500-char preview, so this holds a whole one with
# room for a full body should the endpoint ever stop truncating.
_MAX_POST_AUDIT_BYTES = 8192

# Terminal 429s tolerated before the sweep stops. A rate limit that keeps
# firing is a policy signal about this account's read volume, not a transient
# error to back off through — so the instrument aborts and says so rather
# than grinding on (rules/debugging.md).
_MAX_TERMINAL_429 = 2

# Hard ceiling on LLM calls per sweep, independent of the read budget.
# `_MAX_LISTED_SUBMOLTS` × `sample_size` bounds the sweep in principle, but a
# listing far larger than the ~20 this platform serves would run the local
# model for hours before the network-side guards (read budget, terminal 429)
# ever fired — they throttle GETs, and the scarce resource here is the single
# Ollama the agent shares (security review 2026-08-01). Generous against the
# ~400-call design point; hitting it is logged, never silent.
_MAX_SCORED_PER_SCAN = 1000

# Post ids reach the log as plain text. Since 2026-08-08 this is also an
# **identity key**: `read_submolt_scope_log` deduplicates on the stored
# string, so widening the platform's id format has to be evaluated against
# dedup and not only against log width. Two ids sharing a 64-char prefix
# would arrive identical; the reader refuses to dedup anything at the cap
# rather than merge distinct posts. Measured 2026-08-08: ids are 36 chars.
_POST_ID_MAX_CHARS = 64

# Set to "1" to neuter an installed sweep without uninstalling its launchd
# job — read at configure time so a plist edit is enough. ADR-0081's
# MOLTBOOK_SKILL_SELECTION_ENFORCE had this shape and was retired on
# 2026-08-08; the failure mode it left behind is worth inheriting knowingly
# rather than by copying — a bare `install-schedule` re-run regenerates the
# plist without the variable, with no error and no log line. That is
# survivable here (losing this flag re-enables a read-only sweep) and was
# not there (losing that one silently changed what the agent published).
DISABLE_ENV_VAR = "MOLTBOOK_SUBMOLT_SCOPE_DISABLE"

# Telemetry tag for this instrument's scoring calls, kept apart from the
# production `moltbook.score_relevance` gate calls.
_LLM_CALLER = "moltbook.submolt_scope"

# The instrument shares MOLTBOOK_HOME/logs/ with the episode log and the other
# audit trails; isolation is by filename prefix and consumer-side field
# matching, not by directory. `core.report.generate_all_reports` globs
# `*.jsonl` there and skips these records because they carry no
# `data.action` — checked, not assumed (security review 2026-08-01).
_LOG_PREFIX = "submolt-scope-"

_audit_dir: Path | None = None


def configure_submolt_scope(audit_dir: Path | None = None) -> None:
    """Point the instrument at its audit directory (module-global, as with
    ``configure_skill_selection``).

    An unset ``audit_dir`` disables the instrument outright: no discovery
    call, no feed reads, no LLM calls, nothing written. Tests and one-shot
    CLI paths that never configure it therefore stay clean.

    Setting ``MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1`` forces the same disabled
    state even when a directory is passed. Without it the off switch would be
    unreachable in production — the CLI always has a log directory to hand,
    so every ``submolt-scan`` invocation would do network and LLM work with
    no way to stop it short of uninstalling the job (codex review
    2026-08-01).
    """
    global _audit_dir
    if audit_dir is not None and os.environ.get(DISABLE_ENV_VAR) == "1":
        logger.info("Submolt-scope instrument disabled by %s=1", DISABLE_ENV_VAR)
        audit_dir = None
    _audit_dir = audit_dir


def reset_submolt_scope() -> None:
    """Reset module state (test isolation)."""
    global _audit_dir
    _audit_dir = None


@dataclass(frozen=True)
class SubmoltScopeScan:
    """Outcome of one sweep.

    ``verdict`` reason codes: ``completed``, ``disabled`` (no audit dir, or
    the disable env var), ``discovery_failed`` (the listing call broke —
    distinct from ``no_submolts``, which means the platform listed none),
    ``aborted_rate_limit``, ``aborted_read_budget``, ``aborted_scored_cap``.
    """

    verdict: str
    scan_id: str
    discovered: int
    scanned: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]
    scored: int


def _append(record: dict[str, Any]) -> None:
    if _audit_dir is None:
        return
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    append_jsonl_restricted(_audit_dir / f"{_LOG_PREFIX}{date_str}.jsonl", record)


def _candidate_set(
    listed: tuple[SubmoltInfo, ...],
    subscribed: tuple[str, ...],
) -> tuple[SubmoltInfo, ...]:
    """Listing ∪ subscribed, sorted by name.

    A subscribed submolt missing from the listing still gets sampled: it is
    the baseline the unsubscribed numbers are read against, and dropping it
    would leave the comparison one-sided. Synthesised entries carry zero
    counts, which is honest — the listing is where those counts come from.
    """
    by_name = {info.name: info for info in listed}
    for name in subscribed:
        if name not in by_name:
            by_name[name] = SubmoltInfo(
                name=name,
                description="",
                post_count=0,
                subscriber_count=0,
                is_private=False,
                is_nsfw=False,
            )
    return tuple(by_name[name] for name in sorted(by_name))


def _sample_posts(client: MoltbookClient, name: str, sample_size: int) -> list[dict]:
    """Read one page of a submolt's feed. Raises ``MoltbookClientError``."""
    response = client.get(f"/submolts/{name}/feed")
    try:
        body = response.json()
    except ValueError as exc:
        raise MoltbookClientError(f"Feed for {name} unparseable: {exc}") from exc
    posts = body.get("posts") if isinstance(body, dict) else None
    if not isinstance(posts, list):
        raise MoltbookClientError(f"Feed for {name} has unexpected shape ({type(posts).__name__})")
    return [p for p in posts[:sample_size] if isinstance(p, dict)]


def scan_submolt_scope(
    client: MoltbookClient,
    domain: DomainConfig,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> SubmoltScopeScan:
    """Sample and score every listed submolt; write the results; change nothing.

    Read-only by construction — the only client calls are ``list_submolts``
    and feed GETs. Scoring runs under ``circuit_shield`` so a failing
    instrument cannot open the breaker that guards the agent's publish path,
    and the sweep stops rather than pushing through a repeating rate limit.
    """
    scan_id = new_session_id()[:12]
    subscribed = tuple(domain.subscribed_submolts)
    if _audit_dir is None:
        logger.info("Submolt-scope instrument disabled (no audit dir configured)")
        return SubmoltScopeScan("disabled", scan_id, 0, (), (), 0)

    try:
        listed = client.list_submolts()
    except MoltbookClientError as exc:
        logger.warning("Submolt discovery failed: %s", exc)
        _append(
            {
                "ts": now_iso("seconds"),
                "event": "scan_end",
                "scan_id": scan_id,
                "verdict": "discovery_failed",
                "error": strip_to_printable(str(exc), 200),
                "discovered": 0,
                "scored": 0,
            }
        )
        return SubmoltScopeScan("discovery_failed", scan_id, 0, (), (), 0)

    candidates = _candidate_set(listed, subscribed)
    _append(
        {
            "ts": now_iso("seconds"),
            "event": "scan_start",
            "scan_id": scan_id,
            "discovered": len(listed),
            "candidates": [c.name for c in candidates],
            "subscribed": list(subscribed),
            "sample_size": sample_size,
            "relevance_threshold": domain.relevance_threshold,
        }
    )
    if not candidates:
        _append(
            {
                "ts": now_iso("seconds"),
                "event": "scan_end",
                "scan_id": scan_id,
                "verdict": "no_submolts",
                "discovered": 0,
                "scored": 0,
            }
        )
        return SubmoltScopeScan("no_submolts", scan_id, 0, (), (), 0)

    baseline_429 = client.recent_429_count
    scanned: list[str] = []
    skipped: list[tuple[str, str]] = []
    scored = 0
    verdict = "completed"

    for info in candidates:
        is_subscribed = info.name in subscribed
        if info.is_private or info.is_nsfw:
            # Skipping with a reason beats collecting a 403 and beats a
            # silent omission that would read as "this submolt is dead".
            reason = "private" if info.is_private else "nsfw"
            skipped.append((info.name, reason))
            continue
        if client.recent_429_count - baseline_429 >= _MAX_TERMINAL_429:
            verdict = "aborted_rate_limit"
            logger.warning(
                "Submolt scope scan aborting: %d terminal 429s during the sweep. "
                "This is a policy signal about read volume, not a transient error.",
                client.recent_429_count - baseline_429,
            )
            break
        if not client.has_read_budget(ADAPTIVE_BACKOFF.read_budget_reserve):
            verdict = "aborted_read_budget"
            logger.info("Submolt scope scan aborting: read budget low")
            break
        if scored >= _MAX_SCORED_PER_SCAN:
            verdict = "aborted_scored_cap"
            logger.warning(
                "Submolt scope scan aborting: %d posts scored, at the %d-call ceiling. "
                "%d candidate submolts left unread this sweep.",
                scored,
                _MAX_SCORED_PER_SCAN,
                len(candidates) - len(scanned) - len(skipped),
            )
            break

        try:
            posts = _sample_posts(client, info.name, sample_size)
        except MoltbookClientError as exc:
            status = exc.status_code if exc.status_code is not None else "error"
            skipped.append((info.name, f"feed_{status}"))
            logger.warning("Submolt scope: feed for %s unavailable: %s", info.name, exc)
            continue

        scanned.append(info.name)
        for post in posts:
            content = post.get("content")
            content = content if isinstance(content, str) else ""
            # Observability-only: this call's failures must not open the
            # breaker guarding the agent's own generations.
            with circuit_shield():
                # Distinct caller tag: without it these ~400 weekly
                # observation calls are indistinguishable from real feed
                # scoring in the LLM telemetry (python review 2026-08-01).
                result = score_relevance_detailed(content, caller=_LLM_CALLER)
            scored += 1
            _append(
                {
                    "ts": now_iso("seconds"),
                    "event": "score",
                    "scan_id": scan_id,
                    "submolt": info.name,
                    "subscribed": is_subscribed,
                    "post_id": strip_to_printable(post.get("id", ""), _POST_ID_MAX_CHARS),
                    "score": result.score,
                    "reason": result.reason,
                    "submolt_post_count": info.post_count,
                    "submolt_subscriber_count": info.subscriber_count,
                    **b64_audit_fields("content", content, max_bytes=_MAX_POST_AUDIT_BYTES),
                }
            )

    _append(
        {
            "ts": now_iso("seconds"),
            "event": "scan_end",
            "scan_id": scan_id,
            "verdict": verdict,
            "discovered": len(listed),
            "scanned": scanned,
            "skipped": [{"submolt": n, "reason": r} for n, r in skipped],
            "scored": scored,
        }
    )
    return SubmoltScopeScan(
        verdict=verdict,
        scan_id=scan_id,
        discovered=len(listed),
        scanned=tuple(scanned),
        skipped=tuple(skipped),
        scored=scored,
    )


# ---------------------------------------------------------------------------
# Reading (ADR-0071 instrument: aggregate only, wired to no gate)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmoltReading:
    """One submolt's aggregate over the window.

    Four counts that must not be collapsed into each other:
    ``sampled_scans`` is how often the sweep actually read this submolt's
    feed, ``records`` how many **distinct posts** those reads yielded,
    ``duplicate_records`` how many score events were dropped as re-samples
    of a post already represented, and ``scored`` how many of the distinct
    posts produced a real judgment. A submolt can be sampled and return
    nothing (quiet or dead — a liveness finding, and the reason it still
    appears here with zero records), return posts that the scorer failed on
    (an outage, not an irrelevant feed), or be read repeatedly and yield the
    same page every time (``sampled_scans`` 3 with ``records`` 1 — a fact
    about the sweep's usefulness, not about the feed's relevance).

    ``skips`` carries the per-reason count of scans that never read the feed
    at all (private / nsfw / feed_403 …).
    """

    name: str
    subscribed: bool
    sampled_scans: int
    skips: tuple[tuple[str, int], ...]
    # Distinct posts seen, not score events. See ``duplicate_records``.
    records: int
    # Score events dropped because the post was already counted for this
    # submolt. The sweep samples the first page of a feed, so a low-traffic
    # submolt returns the same posts every week: counting each event would
    # grow ``scored`` without adding one independent sample, while reading
    # as accumulating evidence. Surfaced rather than merely fixed, because
    # a high share here is the signal "repeating the sweep is not buying
    # anything for this submolt" — which is a fact about the instrument's
    # own usefulness, and the reason the 2026-08-08 reading stopped at one
    # sweep.
    duplicate_records: int
    scored: int
    above_threshold: int
    reasons: tuple[tuple[str, int], ...]
    p50: float
    p90: float

    @property
    def hit_rate(self) -> float | None:
        """Share of real judgments at or above the comment threshold.

        ``None`` when nothing was judged. A 0.0 here would say "we looked and
        found nothing relevant", which is precisely the claim an outage must
        not be allowed to make on the scorer's behalf.
        """
        return self.above_threshold / self.scored if self.scored else None


@dataclass(frozen=True)
class SubmoltScopeReading:
    """Read-only aggregate over the scope log.

    Feeds no gate, no ranking, no retrieval. It exists to inform one human
    decision — whether the subscribed set is worth changing, and whether the
    agent should be the one changing it.
    """

    days: int
    scans: tuple[tuple[str, int], ...]
    threshold: float
    per_submolt: tuple[SubmoltReading, ...]
    # Score records whose post_id could not serve as an identity key, so
    # dedup could not run on them. Carried in the reading and rendered, not
    # only logged: the scenario it warns about is a writer-side schema
    # change silently restoring the inflation, and on the scheduled path a
    # logger warning goes to a launchd stderr file the operator is
    # instructed not to open (python review, 2026-08-08). ADR-0075's shape
    # — the reason belongs in the read-out.
    records_without_post_id: int

    @property
    def subscribed(self) -> tuple[SubmoltReading, ...]:
        return tuple(r for r in self.per_submolt if r.subscribed)

    @property
    def unsubscribed(self) -> tuple[SubmoltReading, ...]:
        return tuple(r for r in self.per_submolt if not r.subscribed)


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), q))


def _bump(table: dict[str, dict[str, int]], name: str, key: str) -> None:
    table.setdefault(name, {})
    table[name][key] = table[name].get(key, 0) + 1


def _is_judged(rec: dict[str, Any]) -> bool:
    """Did this record carry an actual score, not just an attempt?

    ``reason == "scored"`` alone is not enough: a record can claim to be
    scored and carry a non-numeric ``score``, and treating that as a
    judgment would let it outrank a genuine one.
    """
    if str(rec.get("reason", "unknown")) != "scored":
        return False
    score = rec.get("score")
    return isinstance(score, (int, float)) and not isinstance(score, bool)


def _iter_scope_records(log_dir: Path, cutoff: date) -> Iterator[dict[str, Any]]:
    """Yield every usable record of every scope log dated on or after ``cutoff``.

    Files are selected by the date in the filename (same daily rotation as
    the other audit logs); unreadable files and broken lines are skipped,
    never fatal.
    """
    if not log_dir.is_dir():
        return
    for path in sorted(log_dir.glob(f"{_LOG_PREFIX}*.jsonl")):
        date_part = path.stem.removeprefix(_LOG_PREFIX)
        try:
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.warning("submolt scope reading: unreadable %s", path.name)
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            yield rec


def _absorb_scan_end(
    rec: dict[str, Any],
    *,
    scan_verdicts: dict[str, int],
    sampled_scans: dict[str, int],
    skips: dict[str, dict[str, int]],
) -> None:
    """Fold one ``scan_end`` record: the sweep's verdict, which submolts it
    read, and the per-reason skips of the ones it did not."""
    verdict = str(rec.get("verdict", "unknown"))
    scan_verdicts[verdict] = scan_verdicts.get(verdict, 0) + 1
    for name in rec.get("scanned") or ():
        if isinstance(name, str) and name:
            sampled_scans[name] = sampled_scans.get(name, 0) + 1
    for entry in rec.get("skipped") or ():
        if not isinstance(entry, dict):
            continue
        name = entry.get("submolt")
        if isinstance(name, str) and name:
            _bump(skips, name, str(entry.get("reason", "unknown")))


def _select_score_record(
    rec: dict[str, Any],
    *,
    subscribed_label: dict[str, bool],
    chosen: dict[str, dict[str, dict[str, Any]]],
    undedupable: dict[str, list[dict[str, Any]]],
    duplicates: dict[str, int],
) -> bool:
    """Pick which record represents its post. Returns whether the record had
    no usable ``post_id`` — the caller's ``records_without_post_id`` tally.

    Selection only. Counting happens after the whole window is read, because
    which record wins for a post is not knowable from the record alone: a
    judged one supersedes an earlier unjudged one, and that cannot be
    expressed by a streaming accumulator without un-counting what it already
    added.
    """
    name = rec.get("submolt")
    if not isinstance(name, str) or not name:
        return False
    # The label is an observation about the submolt, not about the post, so
    # it is taken from every record including the ones dedup drops —
    # otherwise the fallback label would depend on which post happened to be
    # sampled first.
    subscribed_label[name] = bool(rec.get("subscribed"))
    post_id = rec.get("post_id")
    # A post_id sitting exactly at the writer's cap may have been truncated
    # (`_POST_ID_MAX_CHARS`, applied at write time), and two ids sharing that
    # prefix would collapse into one — an undercount with no symptom. The
    # reader cannot tell a truncated id from one that is naturally cap-length,
    # so it treats both as un-dedupable rather than risk merging distinct
    # posts. Measured 2026-08-08: every id is 36 chars against a cap of 64, so
    # this branch is currently unreachable — kept because the ids come from
    # the platform and the failure it guards is a silently wrong number in an
    # instrument whose only product is numbers.
    if not isinstance(post_id, str) or not post_id or len(post_id) >= _POST_ID_MAX_CHARS:
        # Cannot prove it is a re-sample, so keep it. Never silently: a
        # writer-side schema change that dropped or shortened post_id would
        # otherwise quietly restore the inflation this dedup removes, and the
        # reading would look richer for it.
        undedupable.setdefault(name, []).append(rec)
        return True
    bucket = chosen.setdefault(name, {})
    previous = bucket.get(post_id)
    if previous is None:
        bucket[post_id] = rec
        return False
    duplicates[name] = duplicates.get(name, 0) + 1
    # A re-score after a failed one is the FIRST judgment of that sample, not
    # a second one — keeping the failure would let a single outage sweep zero
    # out every post it touched for the rest of the 30-day window (fault
    # F-SCOPE-5, and the sweep is weekly). Among judged records first still
    # wins, so appending a sweep never rewrites an existing row.
    if _is_judged(rec) and not _is_judged(previous):
        bucket[post_id] = rec
    return False


def _count_selected(
    chosen: dict[str, dict[str, dict[str, Any]]],
    undedupable: dict[str, list[dict[str, Any]]],
    threshold: float,
) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, list[float]], dict[str, int]]:
    """Counting pass over the selected records, returning
    ``(records, reasons, scores, above)``.

    Runs over the selected records so every tally describes distinct posts,
    and so the judged-supersedes-unjudged rule lands in all of them at once
    rather than in whichever one the loop happened to reach first.
    """
    records: dict[str, int] = {}
    reasons: dict[str, dict[str, int]] = {}
    scores: dict[str, list[float]] = {}
    above: dict[str, int] = {}
    for name in set(chosen) | set(undedupable):
        picked = list(chosen.get(name, {}).values()) + undedupable.get(name, [])
        records[name] = len(picked)
        for rec in picked:
            _bump(reasons, name, str(rec.get("reason", "unknown")))
            if not _is_judged(rec):
                continue
            score = float(rec["score"])
            scores.setdefault(name, []).append(score)
            if score >= threshold:
                above[name] = above.get(name, 0) + 1
    return records, reasons, scores, above


def read_submolt_scope_log(
    log_dir: Path,
    *,
    days: int,
    threshold: float,
    subscribed: tuple[str, ...] | None = None,
) -> SubmoltScopeReading:
    """Aggregate ``submolt-scope-*.jsonl`` files within the window.

    Files are selected by the date in the filename (same daily rotation as
    the other audit logs); unreadable files and broken lines are skipped,
    never fatal.

    Every submolt the sweep *touched* gets a row, not only the ones that
    produced scores: a feed that came back empty and a feed that 403'd are
    both findings, and dropping them would hide exactly the dead-submolt
    signal this instrument claims to provide.

    Counts **distinct posts, not score events**: records are deduplicated on
    ``post_id`` per submolt across every scan in the window, and the drops
    are reported as ``duplicate_records``. Among judged records the first
    wins, so appending a sweep never rewrites an existing row — but a judged
    record supersedes an earlier unjudged one for the same post, because a
    re-score after a failure is that sample's first judgment rather than a
    second one. Records whose ``post_id`` cannot serve as an identity key
    (absent, or at the write cap and possibly truncated) are all kept and
    counted in ``records_without_post_id``.

    ``subscribed`` is the operator's **current** ``domain.json`` set and
    decides which side of the report a submolt appears on — the reader is
    deciding about the scope as it stands now, not as it stood when a given
    scan ran. Omit it and the label recorded at scan time is used instead
    (latest scan wins), which is the honest fallback when the caller has no
    domain config to hand.
    """
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    scan_verdicts: dict[str, int] = {}
    subscribed_label: dict[str, bool] = {}
    sampled_scans: dict[str, int] = {}
    skips: dict[str, dict[str, int]] = {}
    # submolt -> post_id -> the one record that represents that post.
    chosen: dict[str, dict[str, dict[str, Any]]] = {}
    # Records whose post_id cannot serve as an identity key; all kept.
    undedupable: dict[str, list[dict[str, Any]]] = {}
    duplicates: dict[str, int] = {}
    missing_post_id = 0

    for rec in _iter_scope_records(log_dir, cutoff):
        event = rec.get("event")
        if event == "scan_end":
            _absorb_scan_end(
                rec,
                scan_verdicts=scan_verdicts,
                sampled_scans=sampled_scans,
                skips=skips,
            )
            continue
        if event != "score":
            continue
        if _select_score_record(
            rec,
            subscribed_label=subscribed_label,
            chosen=chosen,
            undedupable=undedupable,
            duplicates=duplicates,
        ):
            missing_post_id += 1

    records, reasons, scores, above = _count_selected(chosen, undedupable, threshold)

    if missing_post_id:
        logger.warning(
            "submolt scope reading: %d score records had no usable post_id (absent, "
            "or at the %d-char write cap and possibly truncated) and could not be "
            "deduplicated — repeat sweeps of the same feed page will inflate their "
            "submolt's sample count",
            missing_post_id,
            _POST_ID_MAX_CHARS,
        )

    current = set(subscribed) if subscribed is not None else None
    names = set(records) | set(sampled_scans) | set(skips)
    if current is not None:
        # A subscribed submolt that appears in no scan at all is itself the
        # finding "the sweep never reached the baseline" — it must not simply
        # be absent from the table.
        names |= current
    names = sorted(names)
    per_submolt = tuple(
        SubmoltReading(
            name=name,
            subscribed=(
                name in current if current is not None else subscribed_label.get(name, False)
            ),
            sampled_scans=sampled_scans.get(name, 0),
            duplicate_records=duplicates.get(name, 0),
            skips=tuple(sorted(skips.get(name, {}).items())),
            records=records.get(name, 0),
            scored=len(scores.get(name, [])),
            above_threshold=above.get(name, 0),
            reasons=tuple(sorted(reasons.get(name, {}).items())),
            p50=_pct(scores.get(name, []), 50),
            p90=_pct(scores.get(name, []), 90),
        )
        for name in names
    )
    return SubmoltScopeReading(
        days=days,
        scans=tuple(sorted(scan_verdicts.items())),
        threshold=threshold,
        per_submolt=per_submolt,
        records_without_post_id=missing_post_id,
    )


def _resample_note(r: SubmoltReading) -> str:
    """``[N/M resampled]``, or empty when nothing was re-sampled.

    Rendered on judged and unjudged rows alike: an outage window where every
    post failed to score can still be re-reading the same page, and that is
    exactly when an operator is deciding whether to run the sweep again.
    """
    if not r.duplicate_records:
        return ""
    total = r.records + r.duplicate_records
    return f"  [{r.duplicate_records}/{total} resampled, already counted]"


def _format_row(r: SubmoltReading) -> str:
    """One submolt line. Rows with nothing judged never render a percentage."""
    if r.hit_rate is None:
        if r.records:
            unscored = ", ".join(f"{k}: {v}" for k, v in r.reasons)
            return f"- {r.name}: {r.records} sampled, none judged — {unscored}{_resample_note(r)}"
        if r.skips:
            detail = ", ".join(f"{k} ×{v}" for k, v in r.skips)
            return f"- {r.name}: not read — {detail}{_resample_note(r)}"
        if r.sampled_scans:
            return f"- {r.name}: read {r.sampled_scans}×, feed returned no posts{_resample_note(r)}"
        return f"- {r.name}: never sampled in this window"
    detail = ""
    if r.scored < r.records:
        unscored = ", ".join(f"{k}: {v}" for k, v in r.reasons if k != "scored")
        detail = f"  [{r.records - r.scored} not judged — {unscored}]"
    # Attached to the row rather than the header: the share is per submolt,
    # and a high one says "another sweep will not move this row" — which is
    # what decides whether repeating the 16-minute sweep is worth it.
    detail += _resample_note(r)
    if r.skips:
        detail += "  [not read: " + ", ".join(f"{k} ×{v}" for k, v in r.skips) + "]"
    return (
        f"- {r.name}: {r.above_threshold}/{r.scored} above threshold "
        f"({r.hit_rate:.0%}), p50 {r.p50:.2f} / p90 {r.p90:.2f}{detail}"
    )


def _format_rows(rows: tuple[SubmoltReading, ...]) -> list[str]:
    # Unjudged rows sort last (-1.0) rather than mixing in with genuine 0%
    # hit rates — they are a different kind of statement about the submolt.
    ordered = sorted(
        rows, key=lambda x: (-(x.hit_rate if x.hit_rate is not None else -1.0), x.name)
    )
    return [_format_row(r) for r in ordered]


def format_submolt_scope_report(reading: SubmoltScopeReading) -> str:
    """Render the reading for the ``report --submolt-scope`` flag."""
    lines = [
        "## Submolt-scope reading (ADR-0086)",
        "",
        f"Window: last {reading.days} days — threshold {reading.threshold:.2f}",
    ]
    if reading.scans:
        lines.append("Scans: " + ", ".join(f"{v}: {n}" for v, n in reading.scans))
    if reading.records_without_post_id:
        lines.append(
            f"⚠ {reading.records_without_post_id} score records had no usable post_id "
            f"(absent, or at the {_POST_ID_MAX_CHARS}-char write cap and possibly "
            "truncated) — those could not be deduplicated, so repeat sweeps of the "
            "same feed page inflate their submolt's sample count."
        )
    if not reading.per_submolt:
        lines.append("")
        lines.append("No submolts observed in the window.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Subscribed (the current human-curated scope — this is the baseline):")
    lines.extend(_format_rows(reading.subscribed) or ["- none"])
    lines.append("")
    lines.append("Not subscribed (candidate scope the agent cannot currently reach):")
    lines.extend(_format_rows(reading.unsubscribed) or ["- none"])
    lines.append("")
    lines.append(
        "Read the two lists against each other, not in isolation: an unsubscribed "
        "hit rate only means something next to what the subscribed set scores."
    )
    return "\n".join(lines)
