"""The Maintainer loop: episodes in, wiki ops out (RFC-0017 S2, D4).

WikiSkill gives its Maintainer a tool-using agent with the whole wiki in
context. gemma4:e4b has 32k and no tools, so the loop is inverted: **code owns
the loop, the model only names things code already enumerated.**

- the model never supplies a page id it invented — ``open`` is constrained to
  an ``enum`` of the ids actually on disk, and an id outside it costs the turn
  (one retry, then fail-closed);
- the model never supplies an episode citation it invented — ``sources`` are
  intersected with the ids of the episodes this run actually rendered;
- the model never touches the filesystem — every edit goes through
  :class:`.wiki.WikiStore`, whose refusals are recorded verbatim;
- every LLM fault is a *named* outcome (``fail_closed_llm`` /
  ``fail_closed_parse`` / ``fail_closed_truncated``), never a quiet no-op that
  reads like an abstain (ADR-0075).

The episode sample is the same reading distill takes — ``_is_rich_episode``
filtered, ``render_episode``'d, full text, no compression (D7 ①). What differs
is the *unit*: distill sends one episode per call, the Maintainer sends as many
as fit one call's budget, so the model can see a pattern recur.

Nothing here is a gate. The wiki is a derived layer with no human approval
(D6/D10) and no consumer until the Proposer (S3); a bad page costs a page.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypeAlias

from . import llm
from ._io import now_iso, scrub_control
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

# What one opened page is assumed to cost when the wiki is empty and there is
# nothing to measure. Deliberately generous: under-reserving here would let the
# episode sample crowd out the pages the next turn has to hold.
_ASSUMED_PAGE_TOKENS = 1200

_SOURCE_MAX_CHARS = 64
_REASON_MAX_CHARS = 200

Outcome: TypeAlias = Literal["written", "abstained", "no_episodes"] | FailClosed

_OP_CLASSES = ("create", "append", "replace", "insert_after")


@dataclass(frozen=True)
class MaintainerConfig:
    """The loop's bounds. Safety valves, not tuning knobs (D4).

    ``step_cap`` defaults to ``max_opens + 2``: enough turns to open the
    budget and still write, and no more. It exists so a model that answers
    ``open`` forever terminates, not because some number of turns is right.
    """

    max_opens: int = 3
    step_cap: int | None = None
    output_reserve: int = OUTPUT_RESERVE
    context_window: int | None = None

    @property
    def effective_step_cap(self) -> int:
        return self.step_cap if self.step_cap is not None else self.max_opens + 2


@dataclass(frozen=True)
class EpisodeSample:
    """What one run read, what it did not, and why (replayable — ADR-0075)."""

    read_ids: tuple[str, ...]
    skipped_ids: tuple[str, ...]
    skip_reasons: dict[str, int]
    rendered: str
    tokens: int


@dataclass(frozen=True)
class WikiSize:
    """D8's growth reading, taken every run.

    The first slice's end condition is stated in these numbers: the day the
    index plus three pages plus a day's episodes stop fitting in 32k. Recorded
    per run so that day is a date in a log, not a surprise.
    """

    pages: int
    index_tokens: int
    page_chars_p90: int


@dataclass(frozen=True)
class MaintainerRun:
    """One day's result. ``outcome`` is always one of the named states."""

    date: str
    seed: str
    outcome: Outcome
    reason: str | None
    episode_ids_read: tuple[str, ...]
    episode_ids_skipped: tuple[str, ...]
    opened_page_ids: tuple[str, ...]
    ops_applied: tuple[str, ...]
    ops_refused: tuple[tuple[str, str], ...]
    budget: dict[str, int]
    wiki_size: WikiSize
    dry_run: bool


# --------------------------------------------------------------- sampling


def week_seed(day: date) -> str:
    """The ISO week id — the run's sample seed (D4).

    Weekly rather than daily so a re-run of the same day reads the same
    episodes, and so a week's runs share one shuffle stream that an offline
    replay can reproduce from the date alone.
    """
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def select_episodes(
    records: list[dict[str, Any]], *, seed: str, budget_tokens: int
) -> EpisodeSample:
    """The day's sample: rich episodes, shuffled by *seed*, packed to budget.

    Two skip reasons, kept apart because they mean opposite things.
    ``not_rich`` is the ADR-0060 filter — interaction pairs and sparse actions
    carry no engagement content and distill drops them too. ``over_budget`` is
    this run's own limit, and a rising count of it is the D8 signal that the
    window no longer holds a day.

    An episode larger than the whole budget is skipped, never truncated: a
    half-episode is evidence of nothing, and the packet's whole premise is
    that the Maintainer reads episodes the way distill does (full text).
    """
    rich: list[dict[str, Any]] = []
    skipped: list[str] = []
    reasons = {"not_rich": 0, "over_budget": 0}
    for record in records:
        record_id = str(record.get("ts", ""))
        if not _is_rich_episode(record):
            reasons["not_rich"] += 1
            if record_id:
                skipped.append(record_id)
            continue
        rich.append(record)

    order = list(rich)
    random.Random(seed).shuffle(order)  # noqa: S311 - sampling, not cryptography

    read_ids: list[str] = []
    blocks: list[str] = []
    used = 0
    for record in order:
        record_id = str(record.get("ts", ""))
        block = render_episode(str(record.get("type", "")), record.get("data") or {})
        cost = llm._estimate_tokens(block + "\n\n")
        if not record_id or not block or used + cost > budget_tokens:
            reasons["over_budget"] += 1
            if record_id:
                skipped.append(record_id)
            continue
        read_ids.append(record_id)
        blocks.append(f"### Episode {record_id}\n{block}")
        used += cost

    return EpisodeSample(
        read_ids=tuple(read_ids),
        skipped_ids=tuple(skipped),
        skip_reasons=reasons,
        rendered="\n\n".join(blocks),
        tokens=used,
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


def _turn_schema(*, page_ids: tuple[str, ...], allow_open: bool) -> dict[str, Any]:
    """The JSON Schema for one turn, rebuilt per turn.

    Rebuilt rather than a constant because both enums are state: the page ids
    change as pages are created, and ``open`` leaves the action enum once the
    open budget is spent. Constraining at the token level is what makes
    "the model cannot name a page that does not exist" a property of the
    decoder rather than of a validation branch that might be forgotten.
    """
    actions = (["open"] if allow_open and page_ids else []) + ["write", "abstain"]
    page_id_schema: dict[str, Any] = {"type": "string"}
    if page_ids:
        page_id_schema = {"type": "string", "enum": list(page_ids)}
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": actions},
            "page_ids": {"type": "array", "items": page_id_schema},
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
    """The op's citations, intersected with what this run actually rendered.

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


# -------------------------------------------------------------- the loop


@dataclass(frozen=True)
class _LoopState:
    """Accumulators for one run — never persisted, never returned.

    Frozen with mutable lists rather than a mutable dataclass: the *identity*
    of each accumulator is fixed at construction (nothing may swap one out
    mid-run), while the lists themselves grow, which is what the loop needs.
    The retry flag lives in :func:`_drive` as a local for the same reason — a
    rebindable field here would be the one piece of state two functions could
    disagree about.
    """

    opened: list[str]
    opened_bodies: list[str]
    applied: list[str]
    refused: list[tuple[str, str]]


def _budget(
    config: MaintainerConfig, *, index: str, size: WikiSize, system: str, shell: str
) -> dict[str, int]:
    """The token budget for the episode sample, itemised for the audit.

    Every subtrahend is named so a run that read two episodes can be diagnosed
    from its own row: an index that grew, pages that grew, or a day whose
    episodes are simply larger. That itemisation *is* the D8 instrument — a
    single "budget: 4000" would say the window ran out without saying what
    filled it.
    """
    window = config.context_window or llm.NUM_CTX
    page_tokens = (
        llm._estimate_tokens("x" * size.page_chars_p90) if size.pages else _ASSUMED_PAGE_TOKENS
    )
    reserved_pages = config.max_opens * page_tokens
    fixed = llm._estimate_tokens(system) + llm._estimate_tokens(shell) + size.index_tokens
    episodes = window - config.output_reserve - reserved_pages - fixed
    return {
        "window": window,
        "output_reserve": config.output_reserve,
        "index": size.index_tokens,
        "reserved_pages": reserved_pages,
        "fixed": fixed,
        "episodes": max(0, episodes),
    }


def _render_prompt(
    template: str,
    *,
    index: str,
    state: _LoopState,
    sample: EpisodeSample,
    day: date,
    opens_left: int,
) -> str:
    return template.format(
        index=index,
        opened="\n\n".join(state.opened_bodies) if state.opened_bodies else "(none yet)",
        episode_count=len(sample.read_ids),
        date=day.isoformat(),
        episodes=sample.rendered,
        opens_left=opens_left,
    )


def _handle_open(
    turn: dict[str, Any], *, store: WikiStore, state: _LoopState, max_opens: int
) -> bool:
    """Apply an ``open`` turn. False when the turn was refused.

    An unknown id reaches here only from a backend that ignored the schema's
    enum (an injected one, or an Ollama that dropped the constraint), so it is
    recorded as a refusal rather than trusted. One retry, then the run ends —
    a model that cannot name a listed id twice in a row is not going to on the
    third try, and each attempt costs a whole context.
    """
    wanted = turn.get("page_ids")
    ids = [i for i in wanted if isinstance(i, str)] if isinstance(wanted, list) else []
    opened_any = False
    for page_id in ids:
        if len(state.opened) >= max_opens:
            state.refused.append(("open", "MAX_OPENS_REACHED"))
            continue
        page = store.read_page(page_id)
        if page is None:
            state.refused.append(("open", "UNKNOWN_PAGE_ID"))
            continue
        if page_id in state.opened:
            continue
        state.opened.append(page_id)
        state.opened_bodies.append(f"### {page.page_id} — {page.title}\n{page.body}")
        opened_any = True
    return opened_any


def _handle_write(
    turn: dict[str, Any], *, store: WikiStore, state: _LoopState, sample: EpisodeSample, dry: bool
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


def run_maintainer(
    *,
    data_root: Path,
    wiki_dir: Path,
    day: date,
    config: MaintainerConfig | None = None,
    dry_run: bool = False,
) -> MaintainerRun:
    """Run one day's Maintainer pass and return what it did.

    Never raises on a model fault — the outcome names it. Only a filesystem
    failure inside the store propagates, for the reason
    :meth:`.wiki.WikiStore.apply` gives: a broken disk must not read as a
    well-behaved abstain.
    """
    from .prompts import WIKI_MAINTAINER_PROMPT, WIKI_MAINTAINER_SYSTEM_PROMPT

    cfg = config or MaintainerConfig()
    store = WikiStore(wiki_dir=wiki_dir, data_root=data_root)
    index = render_index(wiki_dir)
    size = read_wiki_size(wiki_dir, index)
    seed = week_seed(day)
    budget = _budget(
        cfg,
        index=index,
        size=size,
        system=WIKI_MAINTAINER_SYSTEM_PROMPT,
        shell=WIKI_MAINTAINER_PROMPT,
    )

    records = EpisodeLog.read_file(data_root / "logs" / f"{day.isoformat()}.jsonl")
    sample = select_episodes(records, seed=seed, budget_tokens=budget["episodes"])

    state = _LoopState(opened=[], opened_bodies=[], applied=[], refused=[])
    if not sample.read_ids:
        return _finish(
            data_root,
            day=day,
            seed=seed,
            outcome="no_episodes",
            reason=None,
            sample=sample,
            state=state,
            budget=budget,
            size=size,
            index=index,
            dry_run=dry_run,
        )

    outcome, reason = _drive(
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
    )
    return _finish(
        data_root,
        day=day,
        seed=seed,
        outcome=outcome,
        reason=reason,
        sample=sample,
        state=state,
        budget=budget,
        size=read_wiki_size(wiki_dir, render_index(wiki_dir)),
        index=index,
        dry_run=dry_run,
    )


def _drive(
    *,
    store: WikiStore,
    state: _LoopState,
    sample: EpisodeSample,
    cfg: MaintainerConfig,
    day: date,
    data_root: Path,
    index: str,
    template: str,
    system: str,
    dry_run: bool,
) -> tuple[Outcome, str | None]:
    """The bounded turn loop. Returns the run's outcome and its reason."""
    retried = False
    for step in range(cfg.effective_step_cap):
        page_ids = _page_ids(store)
        allow_open = len(state.opened) < cfg.max_opens
        schema = _turn_schema(page_ids=page_ids, allow_open=allow_open)
        prompt = _render_prompt(
            template,
            index=index,
            state=state,
            sample=sample,
            day=day,
            opens_left=max(0, cfg.max_opens - len(state.opened)),
        )
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
        if action == "open" and allow_open:
            if _handle_open(turn, store=store, state=state, max_opens=cfg.max_opens):
                continue
        else:
            # An action the schema did not offer (a backend that ignored the
            # enum, or ``open`` after the open budget is spent).
            state.refused.append((action, "UNOFFERED_ACTION"))
        if retried:
            return "fail_closed_parse", None
        retried = True
    return "fail_closed_parse", None


def _page_ids(store: WikiStore) -> tuple[str, ...]:
    patterns = store.patterns_dir
    if not patterns.is_dir():
        return ()
    return tuple(sorted(p.stem for p in patterns.glob("p-*.md")))


def _finish(
    data_root: Path,
    *,
    day: date,
    seed: str,
    outcome: Outcome,
    reason: str | None,
    sample: EpisodeSample,
    state: _LoopState,
    budget: dict[str, int],
    size: WikiSize,
    index: str,
    dry_run: bool,
) -> MaintainerRun:
    """Build the run record, write its audit row, and return it."""
    import hashlib

    run = MaintainerRun(
        date=day.isoformat(),
        seed=seed,
        outcome=outcome,
        reason=reason or None,
        episode_ids_read=sample.read_ids,
        episode_ids_skipped=sample.skipped_ids,
        opened_page_ids=tuple(state.opened),
        ops_applied=tuple(state.applied),
        ops_refused=tuple(state.refused),
        budget=budget,
        wiki_size=size,
        dry_run=dry_run,
    )
    append_audit(
        _log_path(data_root),
        {
            "kind": "run",
            "ts": now_iso(timespec="seconds"),
            "date": run.date,
            "seed": run.seed,
            "dry_run": dry_run,
            "outcome": run.outcome,
            "reason": run.reason,
            "episode_ids_read": list(run.episode_ids_read),
            "episode_ids_skipped": list(run.episode_ids_skipped),
            "skip_reasons": dict(sample.skip_reasons),
            "budget": dict(budget),
            "episode_tokens": sample.tokens,
            "index_sha256": hashlib.sha256(index.encode("utf-8")).hexdigest(),
            "opened_page_ids": list(run.opened_page_ids),
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
