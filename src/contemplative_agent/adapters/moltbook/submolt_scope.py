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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

# Post ids reach the log as plain text.
_POST_ID_MAX_CHARS = 64

# Set to "1" to neuter an installed sweep without uninstalling its launchd
# job — read at configure time so a plist edit is enough (same shape as
# ADR-0081's MOLTBOOK_SKILL_SELECTION_ENFORCE).
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

    Three counts that must not be collapsed into each other:
    ``sampled_scans`` is how often the sweep actually read this submolt's
    feed, ``records`` how many posts it got back, and ``scored`` how many of
    those produced a real judgment. A submolt can be sampled and return
    nothing (quiet or dead — a liveness finding, and the reason it still
    appears here with zero records), or return posts that the scorer failed
    on (an outage, not an irrelevant feed).

    ``skips`` carries the per-reason count of scans that never read the feed
    at all (private / nsfw / feed_403 …).
    """

    name: str
    subscribed: bool
    sampled_scans: int
    skips: tuple[tuple[str, int], ...]
    records: int
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
    records: dict[str, int] = {}
    reasons: dict[str, dict[str, int]] = {}
    scores: dict[str, list[float]] = {}
    above: dict[str, int] = {}

    def _bump(table: dict[str, dict[str, int]], name: str, key: str) -> None:
        table.setdefault(name, {})
        table[name][key] = table[name].get(key, 0) + 1

    if log_dir.is_dir():
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
                event = rec.get("event")
                if event == "scan_end":
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
                    continue
                if event != "score":
                    continue
                name = rec.get("submolt")
                if not isinstance(name, str) or not name:
                    continue
                subscribed_label[name] = bool(rec.get("subscribed"))
                records[name] = records.get(name, 0) + 1
                reason = str(rec.get("reason", "unknown"))
                _bump(reasons, name, reason)
                if reason != "scored":
                    continue
                score = rec.get("score")
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    continue
                scores.setdefault(name, []).append(float(score))
                if score >= threshold:
                    above[name] = above.get(name, 0) + 1

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
    )


def _format_row(r: SubmoltReading) -> str:
    """One submolt line. Rows with nothing judged never render a percentage."""
    if r.hit_rate is None:
        if r.records:
            unscored = ", ".join(f"{k}: {v}" for k, v in r.reasons)
            return f"- {r.name}: {r.records} sampled, none judged — {unscored}"
        if r.skips:
            detail = ", ".join(f"{k} ×{v}" for k, v in r.skips)
            return f"- {r.name}: not read — {detail}"
        if r.sampled_scans:
            return f"- {r.name}: read {r.sampled_scans}×, feed returned no posts"
        return f"- {r.name}: never sampled in this window"
    detail = ""
    if r.scored < r.records:
        unscored = ", ".join(f"{k}: {v}" for k, v in r.reasons if k != "scored")
        detail = f"  [{r.records - r.scored} not judged — {unscored}]"
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
