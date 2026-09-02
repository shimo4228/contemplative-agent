"""The Maintainer loop: episodes in, wiki ops out (RFC-0017 S2, D4).

WikiSkill gives its Maintainer the whole wiki plus a sample of traces in one
call. CA takes the *form* and not the engine (RFC-0022): the paper's sampling
is driven by a verification score CA has no counterpart for, so instead of
sampling a day down, the loop **reads the whole day, one batch of episodes per
call, until the day is consumed**. Between batches the wiki is read again, so a
page the previous batch created is in the next batch's prompt — recurrence is
what makes the model patch instead of create, and that is the substitute for
the paper's score.

- the model never supplies a page id it invented — every ``ops`` page id is
  constrained to an ``enum`` of the ids actually on disk;
- the model never supplies an episode citation it invented — ``sources`` are
  intersected with the ids of the episodes this batch actually rendered;
- the model never touches the filesystem — every edit goes through
  :class:`.wiki.WikiStore`, whose refusals are recorded verbatim;
- every LLM fault is a *named* outcome (``fail_closed_llm`` /
  ``fail_closed_parse`` / ``fail_closed_truncated``), never a quiet no-op that
  reads like an abstain (ADR-0075). A faulted batch ends the *day*: the next
  batch would be reasoning about a wiki the faulted one was supposed to have
  written into.

The episodes are the same reading distill takes — ``_is_rich_episode``
filtered, ``render_episode``'d, full text, no compression (D7 ①). What differs
is the *unit*: distill sends one episode per call, the Maintainer sends as many
as fit one call's budget and then sends the rest in the next call, so the model
can see a pattern recur and the day's coverage matches distill's.

Nothing here is a gate. The wiki is a derived layer with no human approval
(D6/D10) and no consumer until the Proposer (S3); a bad page costs a page.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypeAlias

from . import llm
from ._io import append_jsonl_restricted, now_iso, scrub_control
from .episode_log import EpisodeLog
from .episode_render import _is_rich_episode, render_episode
from .wiki import (
    Append,
    Create,
    InsertAfter,
    Replace,
    WikiOp,
    WikiStore,
    render_index,
)
from .wiki_loop import (
    OUTPUT_RESERVE,
    FailClosed,
    TurnFault,
    append_audit,
    append_turn_audit,
    call_turn,
    parse_turn,
)

logger = logging.getLogger(__name__)


MAINTAINER_LOG_NAME = "wiki-maintainer.jsonl"

_SOURCE_MAX_CHARS = 64
_REASON_MAX_CHARS = 200

# How long a catch-up may keep the run lock. The scheduled Maintainer holds
# that lock BLOCKING while the agent's own sessions take it non-blocking and
# give up immediately (cli/agent_cmds.py), so a catch-up that ran long would
# silently cost the 06:00 JST session — the activity this whole project
# observes. 90 minutes from a 04:15 start lands before it. Days are not split:
# the deadline decides whether the NEXT day starts, so the ceiling is this
# budget plus one day, which is the ceiling the single-day job already had.
CATCH_UP_SECONDS = 90 * 60

BatchOutcome: TypeAlias = Literal["written", "abstained"] | FailClosed

Outcome: TypeAlias = (
    Literal[
        "written",
        "abstained",
        "no_episodes",
        "already_done",
        "fail_closed_budget",
        "fail_closed_batches",
        "skipped_after_budget",
        "skipped_after_deadline",
    ]
    | FailClosed
)

_OP_CLASSES = ("create", "append", "replace", "insert_after")


@dataclass(frozen=True)
class MaintainerConfig:
    """The loop's bounds. Safety valves, not tuning knobs (D4).

    ``max_batches`` bounds one day's calls. It is a runaway guard, not a
    sample size: a day that needs more calls than this is a day whose shape
    changed (an episode log an order of magnitude larger, or a wiki that has
    grown until almost nothing else fits), and that deserves a named
    ``fail_closed_batches`` row rather than an unbounded spend.
    """

    output_reserve: int = OUTPUT_RESERVE
    context_window: int | None = None
    max_batches: int = 8


@dataclass(frozen=True)
class PreparedEpisode:
    """One rendered episode and what it costs — prepared once per day."""

    episode_id: str
    block: str
    cost: int


@dataclass(frozen=True)
class PreparedDay:
    """The day's readable episodes, in order, plus what was dropped and why."""

    episodes: tuple[PreparedEpisode, ...]
    skipped_ids: tuple[str, ...]
    skip_reasons: dict[str, int]


@dataclass(frozen=True)
class EpisodeSample:
    """What one batch reads (replayable — ADR-0075)."""

    read_ids: tuple[str, ...]
    rendered: str
    tokens: int


@dataclass(frozen=True)
class WikiSize:
    """D8's growth reading, taken every run.

    The first slice's end condition is stated in these numbers: the day the
    index plus the pages plus a batch of episodes stop fitting in 32k.
    Recorded per run so that day is a date in a log, not a surprise.
    """

    pages: int
    index_tokens: int
    page_chars_p90: int


@dataclass(frozen=True)
class BatchRecord:
    """One call's result. The unit a re-run resumes from."""

    batch: int
    outcome: BatchOutcome
    reason: str | None
    episode_ids_read: tuple[str, ...]
    ops_applied: tuple[str, ...]
    ops_refused: tuple[tuple[str, str], ...]
    budget: dict[str, int]
    wiki_size: WikiSize


@dataclass(frozen=True)
class MaintainerRun:
    """One day's result. ``outcome`` is always one of the named states.

    The day's outcome is the last batch's, so a day that faulted halfway
    reports the fault while ``batches`` still shows what the earlier calls
    wrote — the writes are on disk and must not read as having been rolled
    back.
    """

    date: str
    outcome: Outcome
    reason: str | None
    episode_ids_read: tuple[str, ...]
    episode_ids_skipped: tuple[str, ...]
    skip_reasons: dict[str, int]
    ops_applied: tuple[str, ...]
    ops_refused: tuple[tuple[str, str], ...]
    budget: dict[str, int]
    wiki_size: WikiSize
    batches: tuple[BatchRecord, ...]
    dry_run: bool


# --------------------------------------------------------------- sampling


def prepare_day(records: list[dict[str, Any]]) -> PreparedDay:
    """The day's episodes, rendered once, in the order they happened.

    Chronological, not shuffled: the batches are consumed in order, so the
    model reads the day the way it happened and a later batch sees the wiki
    that the morning's batch wrote.

    Three skip reasons are counted here and only here, because they are
    properties of the record rather than of any batch's budget. ``not_rich``
    is the ADR-0060 filter — interaction pairs and sparse actions carry no
    engagement content and distill drops them too. ``no_ts`` and
    ``empty_render`` are malformed or unrenderable records (data quality).
    The fourth reason, ``over_budget``, is counted once at the end of the day
    over what the day's batches never reached: it is D8's reading of how much
    of a day the window stopped holding, and counting it per batch would
    inflate it by the number of calls.

    An episode larger than a whole batch budget is skipped by
    :func:`pack_batch`, never truncated: a half-episode is evidence of
    nothing, and the whole premise is that the Maintainer reads episodes the
    way distill does (full text).
    """
    episodes: list[PreparedEpisode] = []
    skipped: list[str] = []
    reasons = {"not_rich": 0, "no_ts": 0, "empty_render": 0, "over_budget": 0, "unreached": 0}
    for record in records:
        record_id = str(record.get("ts", ""))
        if not _is_rich_episode(record):
            reasons["not_rich"] += 1
            if record_id:
                skipped.append(record_id)
            continue
        if not record_id:
            reasons["no_ts"] += 1
            continue
        rendered = render_episode(str(record.get("type", "")), record.get("data") or {})
        if not rendered:
            reasons["empty_render"] += 1
            skipped.append(record_id)
            continue
        block = f"### Episode {record_id}\n{rendered}"
        episodes.append(
            PreparedEpisode(
                episode_id=record_id,
                block=block,
                cost=llm._estimate_tokens(block + "\n\n"),
            )
        )
    return PreparedDay(
        episodes=tuple(episodes),
        skipped_ids=tuple(skipped),
        skip_reasons=reasons,
    )


def pack_batch(
    remaining: tuple[PreparedEpisode, ...], budget_tokens: int
) -> tuple[EpisodeSample, tuple[PreparedEpisode, ...], tuple[str, ...]]:
    """Take episodes off the front of *remaining* while the budget holds.

    Returns the batch, what is left, and the ids of episodes that do not fit
    a whole batch on their own. Such an episode is stepped over, never
    truncated and never allowed to end the day: a half-episode is evidence of
    nothing, and stopping on one fat record would leave the rest of the day
    unread *and* charge its length to ``over_budget``, which is D8's reading
    of wiki growth rather than of one long post.

    The batch is still contiguous otherwise: packing continues from the front
    so the model reads the day in order.
    """
    read_ids: list[str] = []
    blocks: list[str] = []
    oversized: list[str] = []
    used = 0
    taken = 0
    for episode in remaining:
        if used + episode.cost > budget_tokens:
            if used == 0 and episode.cost > budget_tokens:
                oversized.append(episode.episode_id)
                taken += 1
                continue
            break
        read_ids.append(episode.episode_id)
        blocks.append(episode.block)
        used += episode.cost
        taken += 1
    return (
        EpisodeSample(read_ids=tuple(read_ids), rendered="\n\n".join(blocks), tokens=used),
        remaining[taken:],
        tuple(oversized),
    )


def read_wiki_size(wiki_dir: Path, index: str) -> WikiSize:
    """Pages, index cost, and the 90th-percentile page length (D8)."""
    patterns = wiki_dir / "patterns"
    lengths: list[int] = []
    if patterns.is_dir():
        for path in sorted(patterns.glob("p-*.md")):
            try:
                lengths.append(len(path.read_text(encoding="utf-8")))
            except OSError:
                continue
    lengths.sort()
    # Nearest-rank p90 (ceil), not ``int(n * 0.9)``: with two pages the
    # floor form indexes the SMALLER one and reports the wiki as half its
    # real size — exactly backwards for a growth reading.
    p90 = lengths[-((-len(lengths) * 9) // 10) - 1] if lengths else 0
    return WikiSize(
        pages=len(lengths),
        index_tokens=llm._estimate_tokens(index),
        page_chars_p90=p90,
    )


# ----------------------------------------------------------------- schema


def _turn_schema(*, page_ids: tuple[str, ...]) -> dict[str, Any]:
    """The JSON Schema for one batch's answer, rebuilt per batch.

    Rebuilt rather than a constant because the page-id enum is state: the ids
    change as pages are created, and a batch must be able to patch a page an
    earlier batch of the same day made. Constraining at the token level is
    what makes "the model cannot name a page that does not exist" a property
    of the decoder rather than of a validation branch that might be forgotten.
    """
    page_id_schema: dict[str, Any] = {"type": "string"}
    if page_ids:
        page_id_schema = {"type": "string", "enum": list(page_ids)}
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["write", "abstain"]},
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": list(_OP_CLASSES)},
                        "page_id": page_id_schema,
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "text": {"type": "string"},
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                        "anchor": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["op", "sources"],
                },
            },
            "reason": {"type": "string"},
        },
        "required": ["action"],
    }


# -------------------------------------------------------------- op mapping


def _clean_sources(raw: object, allowed: frozenset[str]) -> tuple[str, ...]:
    """The op's citations, intersected with what this batch actually rendered.

    A model that cites an episode it was not shown is not making a small
    mistake — the citation is the page's only link back to the raw layer
    (D4), so an invented one turns a page into an unverifiable claim. Dropped
    here rather than refused wholesale: an op with one good citation and one
    hallucinated one is still evidence, and an op left with *no* citation is
    refused downstream by the store's own ``SOURCES_EMPTY``.
    """
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = scrub_control(item, _SOURCE_MAX_CHARS)
        if value in allowed and value not in out:
            out.append(value)
    return tuple(out)


def _to_op(raw: object, allowed_sources: frozenset[str]) -> WikiOp | None:
    """One JSON op as a store op, or ``None`` when the shape is not one.

    Missing string fields become ``""`` rather than an error: the store
    already refuses an empty title, body, anchor or source list with a named
    reason, and routing shape faults through the same refusal path keeps one
    place that decides what a bad op costs.
    """
    if not isinstance(raw, dict):
        return None
    kind = raw.get("op")
    sources = _clean_sources(raw.get("sources"), allowed_sources)

    def field(name: str) -> str:
        value = raw.get(name)
        return value if isinstance(value, str) else ""

    if kind == "create":
        return Create(title=field("title"), body=field("body"), sources=sources)
    if kind == "append":
        return Append(page_id=field("page_id"), text=field("text"), sources=sources)
    if kind == "replace":
        return Replace(
            page_id=field("page_id"), old=field("old"), new=field("new"), sources=sources
        )
    if kind == "insert_after":
        return InsertAfter(
            page_id=field("page_id"),
            anchor=field("anchor"),
            text=field("text"),
            sources=sources,
        )
    return None


# ------------------------------------------------------------------- audit


def _log_path(data_root: Path) -> Path:
    return data_root / "logs" / MAINTAINER_LOG_NAME


def _resumable_ids(line: str, target: str) -> tuple[str, ...]:
    """The episode ids one audit line proves were consumed, or ``()``.

    A batch counts only if it both ran for real (``dry_run`` false) and
    reached the model (``written`` / ``abstained``): a dry run changed no
    page, and a faulted batch's episodes were never actually reasoned about.
    """
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return ()
    if not isinstance(row, dict) or row.get("kind") != "batch":
        return ()
    if row.get("date") != target or row.get("dry_run"):
        return ()
    if row.get("outcome") not in ("written", "abstained"):
        return ()
    return tuple(v for v in row.get("episode_ids_read") or [] if isinstance(v, str))


def already_read_ids(data_root: Path, day: date) -> frozenset[str]:
    """Episode ids a previous real run of *day* already consumed.

    Read from the batch rows rather than kept in a separate state file: the
    audit log is the artefact that already has to be right, and a second
    record of the same fact is a second thing that can disagree. Which rows
    count is :func:`_resumable_ids`.
    """
    path = _log_path(data_root)
    if not path.is_file():
        return frozenset()
    target = day.isoformat()
    seen: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                # Streamed, and the two cheap substring tests come first: the
                # same file carries the ``turn`` rows, each up to 128 KiB of
                # base64 prompt and output, and the resume path runs once per
                # catch-up day. Reading the whole file into one string would
                # make a nightly job grow with the log rather than with the day.
                if '"batch"' not in line or target not in line:
                    continue
                seen.update(_resumable_ids(line, target))
    except OSError:
        logger.warning("wiki maintainer: could not read the audit log to resume a day")
        return frozenset()
    return frozenset(seen)


# -------------------------------------------------------------- the loop


@dataclass(frozen=True)
class _BatchState:
    """Accumulators for one batch — never persisted, never returned.

    Frozen with mutable lists rather than a mutable dataclass: the *identity*
    of each accumulator is fixed at construction (nothing may swap one out
    mid-batch), while the lists themselves grow, which is what the loop needs.
    """

    page_bodies: list[str]
    applied: list[str]
    refused: list[tuple[str, str]]


def _budget(
    config: MaintainerConfig,
    *,
    size: WikiSize,
    system: str,
    shell: str,
    page_tokens_total: int,
) -> dict[str, int]:
    """The token budget for one batch's episodes, itemised for the audit.

    Every subtrahend is named so a run that read two episodes can be diagnosed
    from its own row: an index that grew, pages that grew, or a day whose
    episodes are simply larger. That itemisation *is* the D8 instrument — a
    single "budget: 4000" would say the window ran out without saying what
    filled it.
    """
    window = config.context_window or llm.NUM_CTX
    fixed = llm._estimate_tokens(system) + llm._estimate_tokens(shell) + size.index_tokens
    episodes = window - config.output_reserve - page_tokens_total - fixed
    return {
        "window": window,
        "output_reserve": config.output_reserve,
        "index": size.index_tokens,
        "pages": page_tokens_total,
        "fixed": fixed,
        "episodes": max(0, episodes),
    }


def _load_all_pages(store: WikiStore, state: _BatchState) -> int:
    """Put every page body in this batch's prompt. Returns their token cost.

    Re-read for every batch rather than carried over: a batch that patched a
    page must show the patched text to the next one, or the model reasons
    about a wiki that no longer exists.
    """
    total = 0
    for page_id in _page_ids(store):
        page = store.read_page(page_id)
        if page is None:
            continue
        body = f"### {page.page_id} — {page.title}\n{page.body}"
        state.page_bodies.append(body)
        total += llm._estimate_tokens(body + "\n\n")
    return total


def _render_prompt(
    template: str,
    *,
    index: str,
    state: _BatchState,
    sample: EpisodeSample,
    day: date,
) -> str:
    return template.format(
        index=index,
        pages="\n\n".join(state.page_bodies) if state.page_bodies else "(the wiki is empty)",
        episode_count=len(sample.read_ids),
        date=day.isoformat(),
        episodes=sample.rendered,
    )


def _handle_write(
    turn: dict[str, Any], *, store: WikiStore, state: _BatchState, sample: EpisodeSample, dry: bool
) -> None:
    """Apply a ``write`` turn's ops in order, recording each outcome.

    ``dry`` stops at the store's door: the ops are still parsed, source-checked
    and counted, so a would-be run's audit row is comparable to a live one's
    everywhere except whether the page moved.
    """
    raw_ops = turn.get("ops")
    allowed = frozenset(sample.read_ids)
    for raw in raw_ops if isinstance(raw_ops, list) else []:
        op = _to_op(raw, allowed)
        if op is None:
            state.refused.append(("unknown", "UNKNOWN_OP"))
            continue
        name = _op_label(op)
        if dry:
            state.applied.append(f"{name} would-be")
            continue
        result = store.apply(op)
        if result.applied:
            state.applied.append(f"{result.op} {result.page_id}")
        else:
            state.refused.append((result.op, str(result.reason)))


def _op_label(op: WikiOp) -> str:
    if isinstance(op, Create):
        return "create"
    if isinstance(op, Append):
        return "append"
    if isinstance(op, Replace):
        return "replace"
    return "insert_after"


def _render_index(wiki_dir: Path, store: WikiStore) -> str:
    """The index, rendered with the store's OWN length cap.

    Passed rather than defaulted: the ``FULL`` mark the model reads and the
    ``PAGE_FULL`` the store enforces have to be the same number, and two
    defaults that merely happen to agree today are a drift waiting for
    whichever one someone tunes first.
    """
    return render_index(wiki_dir, page_max_chars=store.page_max_chars)


def run_maintainer(
    *,
    data_root: Path,
    wiki_dir: Path,
    day: date,
    config: MaintainerConfig | None = None,
    dry_run: bool = False,
) -> MaintainerRun:
    """Read one UTC day, batch by batch, and return what the day did.

    Never raises on a model fault — the outcome names it. Only a filesystem
    failure inside the store propagates, for the reason
    :meth:`.wiki.WikiStore.apply` gives: a broken disk must not read as a
    well-behaved abstain.
    """
    from .prompts import WIKI_MAINTAINER_PROMPT, WIKI_MAINTAINER_SYSTEM_PROMPT

    cfg = config or MaintainerConfig()
    store = WikiStore(wiki_dir=wiki_dir, data_root=data_root)

    records = EpisodeLog.read_file(data_root / "logs" / f"{day.isoformat()}.jsonl")
    prepared = prepare_day(records)
    skip_reasons = dict(prepared.skip_reasons)
    skipped_ids = list(prepared.skipped_ids)

    if dry_run:
        # A dry run reasons about the whole day: it writes nothing, so there is
        # no earlier batch whose pages it would be reading twice.
        already: frozenset[str] = frozenset()
    else:
        already = already_read_ids(data_root, day)
    remaining = tuple(e for e in prepared.episodes if e.episode_id not in already)

    index = _render_index(wiki_dir, store)
    size = read_wiki_size(wiki_dir, index)
    budget = _budget(
        cfg,
        size=size,
        system=WIKI_MAINTAINER_SYSTEM_PROMPT,
        shell=WIKI_MAINTAINER_PROMPT,
        page_tokens_total=0,
    )

    if not remaining:
        # Two different days, two different names: a day with nothing to read
        # (no_episodes) and a day this loop already finished (already_done).
        # Catch-up walks days it has mostly done already, so collapsing them
        # would make its log unreadable — and "no episodes" would be false.
        done = bool(prepared.episodes)
        return _finish(
            data_root,
            day=day,
            outcome="already_done" if done else "no_episodes",
            reason="every episode of this day was already read" if done else None,
            read_ids=(),
            skipped_ids=tuple(skipped_ids),
            skip_reasons=skip_reasons,
            batches=(),
            budget=budget,
            size=size,
            index=index,
            dry_run=dry_run,
        )

    batches: list[BatchRecord] = []
    read_ids: list[str] = []
    outcome: Outcome = "no_episodes"
    reason: str | None = None

    while remaining:
        if len(batches) >= cfg.max_batches:
            outcome, reason = "fail_closed_batches", None
            skip_reasons["unreached"] += len(remaining)
            skipped_ids.extend(e.episode_id for e in remaining)
            break

        state = _BatchState(page_bodies=[], applied=[], refused=[])
        index = _render_index(wiki_dir, store)
        size = read_wiki_size(wiki_dir, index)
        page_tokens_total = _load_all_pages(store, state)
        budget = _budget(
            cfg,
            size=size,
            system=WIKI_MAINTAINER_SYSTEM_PROMPT,
            shell=WIKI_MAINTAINER_PROMPT,
            page_tokens_total=page_tokens_total,
        )
        if budget["episodes"] <= 0:
            # The wiki alone fills the window — D8's end condition, and the
            # only thing fail_closed_budget means. Named, never sampled down:
            # a partial day would read as a smaller day rather than as the day
            # the window stopped holding one.
            outcome, reason = "fail_closed_budget", None
            skip_reasons["over_budget"] += len(remaining)
            skipped_ids.extend(e.episode_id for e in remaining)
            break

        sample, rest, oversized = pack_batch(remaining, budget["episodes"])
        if oversized:
            # Individually too large for a whole batch: stepped over, counted
            # apart from the wiki-growth reading (see pack_batch).
            skip_reasons["over_budget"] += len(oversized)
            skipped_ids.extend(oversized)
        if not sample.read_ids:
            remaining = rest
            continue

        batch_outcome, batch_reason = _run_batch(
            store=store,
            state=state,
            sample=sample,
            cfg=cfg,
            day=day,
            data_root=data_root,
            index=index,
            template=WIKI_MAINTAINER_PROMPT,
            system=WIKI_MAINTAINER_SYSTEM_PROMPT,
            dry_run=dry_run,
            step=len(batches),
        )
        batches.append(
            _finish_batch(
                data_root,
                day=day,
                batch=len(batches),
                outcome=batch_outcome,
                reason=batch_reason,
                sample=sample,
                state=state,
                budget=budget,
                size=read_wiki_size(wiki_dir, _render_index(wiki_dir, store)),
                dry_run=dry_run,
            )
        )
        outcome, reason = batch_outcome, batch_reason
        remaining = rest
        if batch_outcome not in ("written", "abstained"):
            # A faulted batch ends the day: the next one would be reasoning
            # about pages this one was supposed to have written. Its own
            # episodes do NOT count as read — ``already_read_ids`` will hand
            # them back to the next run, and a day whose read set included
            # them would double-count them across the two run rows.
            skip_reasons["unreached"] += len(remaining) + len(sample.read_ids)
            skipped_ids.extend(sample.read_ids)
            skipped_ids.extend(e.episode_id for e in remaining)
            break
        read_ids.extend(sample.read_ids)

    outcome = _day_outcome(outcome, batches=batches, skip_reasons=skip_reasons)
    reason = None if outcome == "fail_closed_budget" else reason

    return _finish(
        data_root,
        day=day,
        outcome=outcome,
        reason=reason,
        read_ids=tuple(read_ids),
        skipped_ids=tuple(skipped_ids),
        skip_reasons=skip_reasons,
        batches=tuple(batches),
        budget=budget,
        size=read_wiki_size(wiki_dir, _render_index(wiki_dir, store)),
        index=index,
        dry_run=dry_run,
    )


def run_days(
    *,
    data_root: Path,
    wiki_dir: Path,
    days: list[date],
    config: MaintainerConfig | None = None,
    dry_run: bool = False,
    seconds: float = CATCH_UP_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> list[MaintainerRun]:
    """Run *days* oldest first — the catch-up the daily job never performs.

    The scheduled job only ever asks for yesterday, so a day the loop could
    not finish (Ollama down, a machine asleep, a faulted batch) is never
    revisited: the resume machinery exists but nothing drives it. This is the
    driver.

    Each day is independent — a fault on one does not stop the next, because
    the days share nothing but the wiki they write into. Two things stop the
    walk, and both are named in the row rather than left as a shorter list:

    - ``fail_closed_budget`` on any day: the wiki alone filling the window is
      a property of the wiki, not of the day, so every later day would fail
      identically. The rest become ``skipped_after_budget`` rather than being
      paid for in Ollama hours.
    - ``seconds`` elapsed: the caller holds the run lock across the whole
      walk, so an unbounded catch-up starves the agent's own scheduled
      session (see :data:`CATCH_UP_SECONDS`). The rest become
      ``skipped_after_deadline``, and tomorrow's catch-up picks them up —
      that is what a catch-up is for.

    ``clock`` is injectable so the deadline is testable without waiting.
    """
    runs: list[MaintainerRun] = []
    started = clock()
    stop: Outcome | None = None
    for day in days:
        if stop is None and clock() - started >= seconds:
            stop = "skipped_after_deadline"
        if stop is not None:
            runs.append(
                _finish_skipped(
                    data_root, wiki_dir=wiki_dir, day=day, outcome=stop, dry_run=dry_run
                )
            )
            continue
        run = run_maintainer(
            data_root=data_root, wiki_dir=wiki_dir, day=day, config=config, dry_run=dry_run
        )
        runs.append(run)
        if run.outcome == "fail_closed_budget":
            stop = "skipped_after_budget"
    return runs


_SKIP_REASONS = {
    "skipped_after_budget": "an earlier day in this catch-up did not fit the window",
    "skipped_after_deadline": "the catch-up ran out of its time budget",
}


def _finish_skipped(
    data_root: Path, *, wiki_dir: Path, day: date, outcome: Outcome, dry_run: bool
) -> MaintainerRun:
    """A day catch-up did not attempt, written down like every other day."""
    index = _render_index(wiki_dir, WikiStore(wiki_dir=wiki_dir, data_root=data_root))
    return _finish(
        data_root,
        day=day,
        outcome=outcome,
        reason=_SKIP_REASONS.get(str(outcome)),
        read_ids=(),
        skipped_ids=(),
        skip_reasons={},
        batches=(),
        budget={},
        size=read_wiki_size(wiki_dir, index),
        index=index,
        dry_run=dry_run,
    )


def _day_outcome(
    outcome: Outcome, *, batches: list[BatchRecord], skip_reasons: dict[str, int]
) -> Outcome:
    """The day's answer, which is not simply its last batch's.

    A day that wrote in the morning and abstained at night wrote. And a day
    whose every episode was individually too large for a batch never called
    the model at all, so the loop's initial ``no_episodes`` was still
    standing — that is the window failing to hold the day (D8's reading), not
    a day with nothing in it.
    """
    if outcome in ("written", "abstained"):
        return "written" if any(b.outcome == "written" for b in batches) else "abstained"
    if not batches and skip_reasons.get("over_budget"):
        return "fail_closed_budget"
    return outcome


def _run_batch(
    *,
    store: WikiStore,
    state: _BatchState,
    sample: EpisodeSample,
    cfg: MaintainerConfig,
    day: date,
    data_root: Path,
    index: str,
    template: str,
    system: str,
    dry_run: bool,
    step: int,
) -> tuple[BatchOutcome, str | None]:
    """One call: the whole wiki plus this batch's episodes, in and out."""
    schema = _turn_schema(page_ids=_page_ids(store))
    prompt = _render_prompt(template, index=index, state=state, sample=sample, day=day)
    raw: str | None = None
    try:
        raw = call_turn(prompt, system, schema, cfg.output_reserve, "wiki.maintainer")
        turn = parse_turn(raw)
    except TurnFault as fault:
        append_turn_audit(_log_path(data_root), step=step, prompt=prompt, raw=raw, action=None)
        return fault.outcome, None
    action = str(turn.get("action"))
    append_turn_audit(_log_path(data_root), step=step, prompt=prompt, raw=raw, action=action)

    if action == "abstain":
        return "abstained", scrub_control(str(turn.get("reason", "")), _REASON_MAX_CHARS)
    if action == "write":
        _handle_write(turn, store=store, state=state, sample=sample, dry=dry_run)
        return "written", None
    # An action the schema did not offer (a backend that ignored the enum).
    state.refused.append((action, "UNOFFERED_ACTION"))
    return "fail_closed_parse", None


def _page_ids(store: WikiStore) -> tuple[str, ...]:
    patterns = store.patterns_dir
    if not patterns.is_dir():
        return ()
    return tuple(sorted(p.stem for p in patterns.glob("p-*.md")))


def _finish_batch(
    data_root: Path,
    *,
    day: date,
    batch: int,
    outcome: BatchOutcome,
    reason: str | None,
    sample: EpisodeSample,
    state: _BatchState,
    budget: dict[str, int],
    size: WikiSize,
    dry_run: bool,
) -> BatchRecord:
    """Build one batch's record, write its audit row, and return it.

    The batch row is what a re-run of the same day resumes from, so it carries
    the episode ids and the outcome that decides whether they count as read.
    """
    record = BatchRecord(
        batch=batch,
        outcome=outcome,
        reason=reason or None,
        episode_ids_read=sample.read_ids,
        ops_applied=tuple(state.applied),
        ops_refused=tuple(state.refused),
        budget=dict(budget),
        wiki_size=size,
    )
    # NOT ``append_audit``: this row IS the resume state, so its loss would
    # silently make the next run re-read the same episodes and create a
    # near-duplicate page. Same stance the store takes on a broken disk — a
    # filesystem failure must not read as a well-behaved run.
    append_jsonl_restricted(
        _log_path(data_root),
        {
            "kind": "batch",
            "ts": now_iso(timespec="seconds"),
            "date": day.isoformat(),
            "batch": batch,
            "dry_run": dry_run,
            "outcome": record.outcome,
            "reason": record.reason,
            "episode_ids_read": list(record.episode_ids_read),
            "episode_tokens": sample.tokens,
            "budget": dict(budget),
            "ops_applied": list(record.ops_applied),
            "ops_refused": [list(pair) for pair in record.ops_refused],
            "wiki_size": {
                "pages": size.pages,
                "index_tokens": size.index_tokens,
                "page_chars_p90": size.page_chars_p90,
            },
        },
    )
    return record


def _finish(
    data_root: Path,
    *,
    day: date,
    outcome: Outcome,
    reason: str | None,
    read_ids: tuple[str, ...],
    skipped_ids: tuple[str, ...],
    skip_reasons: dict[str, int],
    batches: tuple[BatchRecord, ...],
    budget: dict[str, int],
    size: WikiSize,
    index: str,
    dry_run: bool,
) -> MaintainerRun:
    """Build the day's record, write its audit row, and return it."""
    import hashlib

    applied = tuple(entry for batch in batches for entry in batch.ops_applied)
    refused = tuple(entry for batch in batches for entry in batch.ops_refused)
    run = MaintainerRun(
        date=day.isoformat(),
        outcome=outcome,
        reason=reason or None,
        episode_ids_read=read_ids,
        episode_ids_skipped=skipped_ids,
        skip_reasons=skip_reasons,
        ops_applied=applied,
        ops_refused=refused,
        budget=budget,
        wiki_size=size,
        batches=batches,
        dry_run=dry_run,
    )
    append_audit(
        _log_path(data_root),
        {
            "kind": "run",
            "ts": now_iso(timespec="seconds"),
            "date": run.date,
            "dry_run": dry_run,
            "outcome": run.outcome,
            "reason": run.reason,
            "batches": len(batches),
            "episode_ids_read": list(run.episode_ids_read),
            "episode_ids_skipped": list(run.episode_ids_skipped),
            "skip_reasons": dict(skip_reasons),
            "budget": dict(budget),
            "index_sha256": hashlib.sha256(index.encode("utf-8")).hexdigest(),
            "ops_applied": list(run.ops_applied),
            "ops_refused": [list(pair) for pair in run.ops_refused],
            "wiki_size": {
                "pages": size.pages,
                "index_tokens": size.index_tokens,
                "page_chars_p90": size.page_chars_p90,
            },
        },
    )
    return run
