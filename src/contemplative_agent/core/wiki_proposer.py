"""The Proposer loop: wiki in, one atomic proposal out (RFC-0017 S3, D5).

Same machine as the Maintainer (:mod:`.wiki_loop`), different question. The
Maintainer asks "what did today evidence"; the Proposer asks "given everything
the wiki now holds, what is the ONE change to the skill store worth making" —
a new skill, or an incremental patch to one existing skill, or nothing.

Four inputs, all rendered by code and all handed over whole (D5: **no retrieval
filter** — the point of the experiment is what the model does with the full
picture, and a filter would silently become the judge):

- the wiki index (:func:`.wiki.render_index`)
- the skill index — every skill's name and description
  (:func:`.skill_selection.load_skill_catalog`)
- the evolution log — every candidate ever staged and how it ended
  (:func:`.wiki_render.render_evolution_log`)
- skill impact — per-skill selection evidence over a window
  (:func:`.wiki_render.render_skill_impact`)

If those four do not fit the context window the run ends ``fail_closed_budget``
rather than trimming one of them. Trimming would make the Proposer quietly
stop seeing the rejection history — the single input that stops it re-proposing
what a human already refused — and the whole D8 growth reading exists so that
day arrives as a dated log line instead of a silent degradation.

**S3 writes nothing into ``skills/`` or ``.staged/``.** A validated proposal is
rendered to ``wiki/proposals/`` in the shape D6 wants at the staging gate (a
create's full text; a patch's post-edit text plus a unified diff) and recorded
as a would-be in ``logs/wiki-proposer.jsonl``. Putting it in front of a human is
S6's job.

Everything the model names is checked against something code enumerated: pages
against the index, skills against the catalog, citations against the pages this
run actually opened, and a patch's anchor against the target's real text.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal, TypeAlias

from . import llm
from ._io import now_iso, scrub_control
from .skill_selection import load_skill_catalog
from .text_utils import skill_theme
from .wiki import render_index
from .wiki_loop import (
    OUTPUT_RESERVE,
    FailClosed,
    TurnFault,
    append_audit,
    append_turn_audit,
    call_turn,
    parse_turn,
)
from .wiki_render import render_evolution_log, render_skill_impact

logger = logging.getLogger(__name__)


PROPOSER_LOG_NAME = "wiki-proposer.jsonl"
PROPOSALS_DIRNAME = "proposals"

_NAME_MAX_CHARS = 80
_DESCRIPTION_MAX_CHARS = 300
_REASON_MAX_CHARS = 200

_PATCH_OPS = ("append", "replace", "insert_after")

Outcome: TypeAlias = Literal["proposed", "abstained", "fail_closed_budget"] | FailClosed

Capacity: TypeAlias = Literal["constrained", "paper"]

RefusalReason: TypeAlias = Literal[
    "UNKNOWN_PAGE_ID",
    "UNKNOWN_SKILL_NAME",
    "MAX_OPENS_REACHED",
    "UNOFFERED_ACTION",
    "BAD_PROPOSAL",
    "CITATIONS_EMPTY",
    "TARGET_NOT_FOUND",
    "NAME_COLLISION",
    "NAME_EMPTY",
    "TEXT_EMPTY",
    "ANCHOR_NOT_FOUND",
    "ANCHOR_AMBIGUOUS",
    "UNKNOWN_PATCH_OP",
]


@dataclass(frozen=True)
class ProposerConfig:
    """The loop's bounds and its two window choices.

    ``impact_days`` (28) is the skill-impact window: long enough that a skill
    selected weekly still shows a count, short enough that last quarter's
    behaviour does not outvote this month's.

    ``evolution_weeks`` defaults to ``None`` = the whole history, measured at
    10,370 tokens over 481 candidates on 2026-09-02 against a 32,768 window
    with roughly 6,800 tokens of headroom. It is a knob rather than a default
    window because the rejection history is precisely what stops a re-proposal,
    and the day it no longer fits should surface as ``fail_closed_budget``, not
    as a Proposer that quietly forgot the last two months.

    ``capacity`` is the RFC-0017 D9 replay knob, default ``"constrained"`` =
    the shipped loop unchanged. ``"paper"`` hands over every wiki page body
    and every skill body up front and offers no ``open_*`` turn, which is
    WikiSkill's own capacity for the replay's arm (1). The budget check that
    already guards the four rendered inputs then guards the bodies too, so a
    picture that does not fit is ``fail_closed_budget`` rather than a
    silently smaller one.
    """

    max_opens: int = 3
    step_cap: int | None = None
    output_reserve: int = OUTPUT_RESERVE
    context_window: int | None = None
    impact_days: int = 28
    evolution_weeks: int | None = None
    capacity: Capacity = "constrained"

    @property
    def effective_step_cap(self) -> int:
        return self.step_cap if self.step_cap is not None else self.max_opens + 2


@dataclass(frozen=True)
class Proposal:
    """One atomic proposal, after every code check passed (D5).

    A single dataclass for both kinds rather than a union: the two share every
    field a consumer reads (what it cites, what text it carries) and differ
    only in which of ``name`` / ``target`` is meaningful, so a union would make
    every reader branch to ask the same two questions.
    """

    kind: Literal["create", "patch"]
    name: str
    description: str
    target: str
    op: str
    anchor: str
    text: str
    cited_pages: tuple[str, ...]


@dataclass(frozen=True)
class ProposerRun:
    """One iteration's result. ``outcome`` is always one of the named states."""

    iteration: str
    outcome: Outcome
    reason: str | None
    opened_page_ids: tuple[str, ...]
    opened_skill_names: tuple[str, ...]
    proposal: Proposal | None
    proposal_path: str | None
    refusals: tuple[tuple[str, str], ...]
    budget: dict[str, int]
    catalog_size: int
    impact_window_days: int
    dry_run: bool


def iteration_id(today: date) -> str:
    """The ISO week — the Proposer's unit (D5: weekly)."""
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ----------------------------------------------------------------- inputs


@dataclass(frozen=True)
class ProposerInputs:
    """The four rendered inputs plus the lookups the loop validates against."""

    wiki_index: str
    skill_index: str
    evolution: str
    impact: str
    catalog_names: tuple[str, ...]
    skill_paths: dict[str, Path]


def _skill_paths(skills_dir: Path) -> dict[str, Path]:
    """``catalog name -> file``, so ``open_skill`` can read a body.

    ``load_skill_catalog`` is the naming authority (D5 names it as the reader)
    but returns no path, and the mapping is not derivable from the filename:
    ``skill_theme`` prefers the frontmatter ``name`` over the stem. So this
    walks the same files under the same rules and applies the same
    normalisation.

    A name the two disagree about simply has no entry here, and the open is
    then refused ``UNKNOWN_SKILL_NAME`` — the drift fails closed rather than
    opening some other skill's file.
    """
    out: dict[str, Path] = {}
    if not skills_dir.is_dir():
        return out
    for path in sorted(skills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        name, _ = skill_theme(text, fallback_name=path.stem)
        out.setdefault(scrub_control(name, _NAME_MAX_CHARS), path)
    return out


def _evolution_since(config: ProposerConfig, today: date) -> str | None:
    if config.evolution_weeks is None:
        return None
    return (today - timedelta(weeks=config.evolution_weeks)).isoformat()


def _window_evolution(text: str, since: str | None) -> str:
    """Keep the heading and the rows dated on or after *since*.

    A window, not a truncation: rows are selected by their own date, so the
    result is "the last N weeks of history" rather than "as much history as
    fitted", which is the distinction ``fail_closed_budget`` exists to keep.
    """
    if since is None:
        return text
    kept: list[str] = []
    for line in text.splitlines():
        if len(line) >= 10 and line[:4].isdigit() and line[4] == "-":
            if line[:10] >= since:
                kept.append(line)
        else:
            kept.append(line)
    return "\n".join(kept)


def build_inputs(
    *, data_root: Path, wiki_dir: Path, skills_dir: Path, today: date, config: ProposerConfig
) -> ProposerInputs:
    """Render the four inputs. Read-only; nothing here can fail the run."""
    catalog = load_skill_catalog(skills_dir)
    return ProposerInputs(
        wiki_index=render_index(wiki_dir),
        skill_index="\n".join(f"{e.name} — {e.description}" for e in catalog) or "(no skills)",
        # ``until=today`` is a no-op live (today IS today) and is what keeps an
        # offline replay honest: a July iteration must not read August's staging
        # decisions or selections (RFC-0017 S4).
        evolution=_window_evolution(
            render_evolution_log(data_root, until=today), _evolution_since(config, today)
        ),
        impact=render_skill_impact(
            data_root, since=today - timedelta(days=config.impact_days), until=today
        ),
        catalog_names=tuple(e.name for e in catalog),
        skill_paths=_skill_paths(skills_dir),
    )


def _budget(
    config: ProposerConfig,
    *,
    inputs: ProposerInputs,
    system: str,
    shell: str,
    preloaded: int = 0,
) -> dict:
    """Window minus everything the loop must hold, itemised for the audit.

    ``preloaded`` is the paper arm's page and skill bodies. Counted here
    rather than left out because they sit in the very first prompt, so a
    headroom computed without them would report room the call does not have.
    """
    window = config.context_window or llm.NUM_CTX
    parts = {
        "wiki_index": llm._estimate_tokens(inputs.wiki_index),
        "skill_index": llm._estimate_tokens(inputs.skill_index),
        "evolution": llm._estimate_tokens(inputs.evolution),
        "impact": llm._estimate_tokens(inputs.impact),
        "preloaded": preloaded,
    }
    fixed = llm._estimate_tokens(system) + llm._estimate_tokens(shell)
    total_inputs = sum(parts.values())
    return {
        "window": window,
        "output_reserve": config.output_reserve,
        "fixed": fixed,
        "inputs": total_inputs,
        **parts,
        "headroom": window - config.output_reserve - fixed - total_inputs,
    }


# ----------------------------------------------------------------- schema


def _turn_schema(
    *, page_ids: tuple[str, ...], skill_names: tuple[str, ...], allow_open: bool
) -> dict[str, Any]:
    """The JSON Schema for one turn, rebuilt per turn.

    Both enums are state — the pages grow as the Maintainer runs, and the two
    ``open_*`` actions leave the action enum together once the shared open
    budget is spent. Constraining at the token level is what makes "the model
    cannot name a skill that does not exist" a property of the decoder rather
    than of a validation branch someone might forget.
    """
    actions: list[str] = []
    if allow_open and page_ids:
        actions.append("open_page")
    if allow_open and skill_names:
        actions.append("open_skill")
    actions += ["propose", "abstain"]

    page_schema: dict[str, Any] = {"type": "string"}
    if page_ids:
        page_schema = {"type": "string", "enum": list(page_ids)}
    skill_schema: dict[str, Any] = {"type": "string"}
    if skill_names:
        skill_schema = {"type": "string", "enum": list(skill_names)}

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": actions},
            "page_ids": {"type": "array", "items": page_schema},
            "skill_names": {"type": "array", "items": skill_schema},
            "proposal": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["create", "patch"]},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "target": skill_schema,
                    "op": {"type": "string", "enum": list(_PATCH_OPS)},
                    "anchor": {"type": "string"},
                    "text": {"type": "string"},
                    "body": {"type": "string"},
                    "cited_pages": {"type": "array", "items": page_schema},
                },
                "required": ["kind", "cited_pages"],
            },
            "reason": {"type": "string"},
        },
        "required": ["action"],
    }


# ------------------------------------------------------------- validation


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _field(raw: dict[str, Any], name: str, limit: int | None = None) -> str:
    value = raw.get(name)
    text = value if isinstance(value, str) else ""
    return scrub_control(text, limit) if limit is not None else text


def anchor_refusal(body: str, anchor: str, *, single_line: bool = False) -> RefusalReason | None:
    """``None`` when *anchor* occurs exactly once — the S1 rule, on a skill.

    Deliberately the same rule and the same two codes as
    :func:`.wiki._anchor_refusal`, because the guarantee is the same one: a
    patch whose anchor is missing was quoted from nowhere, and one that matches
    twice does not say which place it meant. Checked here only — S3 verifies,
    it never rewrites the skill.

    ``single_line`` mirrors :func:`.wiki._anchor_refusal`: insert_after splices
    after a line, so a multi-line anchor points at no line and would render a
    would-be patch whose diff is empty.
    """
    if not anchor:
        return "ANCHOR_NOT_FOUND"
    if single_line and "\n" in anchor:
        return "ANCHOR_NOT_FOUND"
    hits = body.count(anchor)
    if hits == 0:
        return "ANCHOR_NOT_FOUND"
    if hits > 1:
        return "ANCHOR_AMBIGUOUS"
    return None


def validate_proposal(
    raw: object,
    *,
    opened_pages: tuple[str, ...],
    catalog_names: tuple[str, ...],
    skill_paths: dict[str, Path],
) -> tuple[Proposal | None, RefusalReason | None]:
    """One JSON proposal as a checked :class:`Proposal`, or the reason it is not.

    Order matters: shape, then citations, then identity, then the anchor. Each
    later check needs the earlier one to have passed, and reporting the first
    failure means the refusal names the thing the model actually got wrong
    rather than a downstream symptom.
    """
    if not isinstance(raw, dict):
        return None, "BAD_PROPOSAL"
    kind = raw.get("kind")
    if kind not in ("create", "patch"):
        return None, "BAD_PROPOSAL"

    cited = tuple(dict.fromkeys(p for p in _strings(raw.get("cited_pages")) if p in opened_pages))
    if not cited:
        return None, "CITATIONS_EMPTY"

    if kind == "create":
        return _validate_create(raw, cited=cited, catalog_names=catalog_names)
    return _validate_patch(raw, cited=cited, catalog_names=catalog_names, skill_paths=skill_paths)


def _validate_create(
    raw: dict[str, Any], *, cited: tuple[str, ...], catalog_names: tuple[str, ...]
) -> tuple[Proposal | None, RefusalReason | None]:
    """A new skill: a name nothing else claims, and a body."""
    name = scrub_control(_field(raw, "name"), _NAME_MAX_CHARS)
    # ``body`` is the documented field; ``text`` is accepted as the alias the
    # patch arm uses, so a model that reuses one key across both kinds is not
    # punished for a naming choice the schema does not enforce.
    body = _field(raw, "body") or _field(raw, "text")
    if not name:
        return None, "NAME_EMPTY"
    if name in catalog_names:
        return None, "NAME_COLLISION"
    if not body.strip():
        return None, "TEXT_EMPTY"
    return (
        Proposal(
            kind="create",
            name=name,
            description=scrub_control(_field(raw, "description"), _DESCRIPTION_MAX_CHARS),
            target="",
            op="",
            anchor="",
            text=body,
            cited_pages=cited,
        ),
        None,
    )


def _validate_patch(
    raw: dict[str, Any],
    *,
    cited: tuple[str, ...],
    catalog_names: tuple[str, ...],
    skill_paths: dict[str, Path],
) -> tuple[Proposal | None, RefusalReason | None]:
    """An edit to one existing skill: a real target, a known op, a unique anchor.

    The target is checked against the catalog AND the path map, not either
    alone: the catalog is what the model was shown, the map is what can
    actually be read, and a name in one but not the other is a store that
    changed under the run.
    """
    target = scrub_control(_field(raw, "target"), _NAME_MAX_CHARS)
    if target not in catalog_names or target not in skill_paths:
        return None, "TARGET_NOT_FOUND"
    op = _field(raw, "op")
    if op not in _PATCH_OPS:
        return None, "UNKNOWN_PATCH_OP"
    text = _field(raw, "text") or _field(raw, "body")
    if not text.strip():
        return None, "TEXT_EMPTY"
    current = _read_skill(skill_paths[target])
    if current is None:
        return None, "TARGET_NOT_FOUND"

    anchor = ""
    if op != "append":
        anchor = _field(raw, "anchor") or _field(raw, "old")
        refusal = anchor_refusal(current, anchor, single_line=op == "insert_after")
        if refusal is not None:
            return None, refusal

    return (
        Proposal(
            kind="patch",
            name="",
            description="",
            target=target,
            op=op,
            anchor=anchor,
            text=text,
            cited_pages=cited,
        ),
        None,
    )


def _read_skill(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


# -------------------------------------------------------------- rendering


def apply_patch(body: str, proposal: Proposal) -> str:
    """The target's text as the proposal would leave it. Pure — nothing written.

    The three ops mirror :mod:`.wiki`'s so a reviewer reads one edit
    vocabulary across the whole RFC; the anchor is already known unique by the
    time this runs.
    """
    if proposal.op == "append":
        return body.rstrip("\n") + "\n" + proposal.text + "\n"
    if proposal.op == "replace":
        return body.replace(proposal.anchor, proposal.text, 1)
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if proposal.anchor in line:
            return "\n".join(lines[: index + 1] + [proposal.text] + lines[index + 1 :])
    return body  # unreachable: validate_proposal checked the anchor first


def render_proposal(
    proposal: Proposal, *, current_body: str | None, iteration: str, run_ts: str
) -> str:
    """The would-be proposal in the shape the staging gate will want (D6).

    A create renders the skill file as it would land. A patch renders the
    target's **post-edit full text plus a unified diff**, because those answer
    the two questions a reviewer actually has — what would the skill say, and
    what exactly changed — and reading one out of the other is work the reader
    should not have to do.
    """
    header = [
        "---",
        f"kind: {proposal.kind}",
        f"iteration: {iteration}",
        f"created: {run_ts}",
    ]
    if proposal.kind == "create":
        header.append(f"name: {proposal.name}")
        if proposal.description:
            header.append(f"description: {proposal.description}")
    else:
        header.append(f"target: {proposal.target}")
        header.append(f"op: {proposal.op}")
    header.append("cited_pages:")
    header.extend(f"  - {page}" for page in proposal.cited_pages)
    header.append("---")

    if proposal.kind == "create":
        return "\n".join(header) + "\n\n" + proposal.text.rstrip("\n") + "\n"

    before = current_body or ""
    after = apply_patch(before, proposal)
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{proposal.target}",
            tofile=f"b/{proposal.target}",
            lineterm="",
        )
    )
    return (
        "\n".join(header)
        + "\n\n## Skill after the patch\n\n"
        + after.rstrip("\n")
        + "\n\n## Unified diff\n\n```diff\n"
        + diff
        + "\n```\n"
    )


def _proposal_path(wiki_dir: Path, iteration: str) -> Path:
    """The next free ``<iteration>-<seq>.md`` under ``wiki/proposals/``.

    Sequence derived from the directory, not a counter file, for the reason
    :meth:`.wiki.WikiStore._next_page_id` gives: nothing on disk can then be
    overwritten by a crash between the write and a counter update.

    Containment here is by construction rather than by check: every component
    of the path is code-generated — ``wiki_dir`` from config, the iteration
    from the calendar, the sequence from a listdir — so no model-supplied
    string reaches it and there is nothing for a ``_target_inside_data_root``
    test to catch. The moment a caller lets a proposal field name the file,
    that stops being true and this needs the S1 check.
    """
    directory = wiki_dir / PROPOSALS_DIRNAME
    existing = sorted(directory.glob(f"{iteration}-*.md")) if directory.is_dir() else []
    return directory / f"{iteration}-{len(existing) + 1:02d}.md"


# -------------------------------------------------------------- the loop


@dataclass(frozen=True)
class _LoopState:
    """Accumulators for one run — see the note in :mod:`.wiki_maintainer`."""

    opened_pages: list[str]
    opened_skills: list[str]
    opened_bodies: list[str]
    refusals: list[tuple[str, str]]


def _page_ids(wiki_index: str) -> tuple[str, ...]:
    """The ids the index actually lists — the same list the model is shown.

    Read off the rendered index rather than the directory so the enum and the
    prompt cannot disagree: a page the index omitted (unparseable) is a page
    the model was never offered and must not be able to open.
    """
    return tuple(
        line.split(" | ", 1)[0].strip() for line in wiki_index.splitlines() if line.startswith("p-")
    )


def _handle_open_page(
    turn: dict, *, state: _LoopState, wiki_dir: Path, cfg: ProposerConfig
) -> bool:
    from .wiki import WikiStore

    store = WikiStore(wiki_dir=wiki_dir, data_root=wiki_dir)
    opened = False
    for page_id in _strings(turn.get("page_ids")):
        if _open_budget_spent(state, cfg):
            state.refusals.append(("open_page", "MAX_OPENS_REACHED"))
            continue
        page = store.read_page(page_id)
        if page is None:
            state.refusals.append(("open_page", "UNKNOWN_PAGE_ID"))
            continue
        if page_id in state.opened_pages:
            continue
        state.opened_pages.append(page_id)
        state.opened_bodies.append(f"### wiki page {page.page_id} — {page.title}\n{page.body}")
        opened = True
    return opened


def _handle_open_skill(
    turn: dict, *, state: _LoopState, inputs: ProposerInputs, cfg: ProposerConfig
) -> bool:
    opened = False
    for name in _strings(turn.get("skill_names")):
        if _open_budget_spent(state, cfg):
            state.refusals.append(("open_skill", "MAX_OPENS_REACHED"))
            continue
        path = inputs.skill_paths.get(name)
        body = _read_skill(path) if path is not None else None
        if body is None:
            state.refusals.append(("open_skill", "UNKNOWN_SKILL_NAME"))
            continue
        if name in state.opened_skills:
            continue
        state.opened_skills.append(name)
        # The full file, frontmatter included: a patch's anchor may sit in the
        # description, and a model shown only the body would quote text the
        # validator then cannot find.
        state.opened_bodies.append(f"### skill {name}\n{body}")
        opened = True
    return opened


def _open_budget_spent(state: _LoopState, cfg: ProposerConfig) -> bool:
    """``max_opens`` is a single budget across pages AND skills (D5)."""
    return len(state.opened_pages) + len(state.opened_skills) >= cfg.max_opens


def _preload_everything(state: _LoopState, *, wiki_dir: Path, inputs: ProposerInputs) -> int:
    """Every page body and every skill body, up front (paper capacity, D9).

    Filled into the same ``opened_*`` accumulators an ``open_*`` turn would
    fill, so validation is untouched: a proposal must still cite pages this
    run "opened", and under paper capacity it opened all of them. Returns the
    estimated token cost so the budget can refuse a picture that does not fit.
    """
    from .wiki import WikiStore

    store = WikiStore(wiki_dir=wiki_dir, data_root=wiki_dir)
    total = 0
    for page_id in _page_ids(inputs.wiki_index):
        page = store.read_page(page_id)
        if page is None:
            continue
        body = f"### wiki page {page.page_id} — {page.title}\n{page.body}"
        state.opened_pages.append(page_id)
        state.opened_bodies.append(body)
        total += llm._estimate_tokens(body + "\n\n")
    for name in inputs.catalog_names:
        path = inputs.skill_paths.get(name)
        text = _read_skill(path) if path is not None else None
        if text is None:
            continue
        body = f"### skill {name}\n{text}"
        state.opened_skills.append(name)
        state.opened_bodies.append(body)
        total += llm._estimate_tokens(body + "\n\n")
    return total


def run_proposer(
    *,
    data_root: Path,
    wiki_dir: Path,
    skills_dir: Path,
    today: date,
    config: ProposerConfig | None = None,
    dry_run: bool = False,
) -> ProposerRun:
    """Run one weekly Proposer iteration and return what it proposed.

    Never raises on a model fault — the outcome names it. Writes at most one
    file, under ``wiki/proposals/``, and never touches ``skills/``.
    """
    from .prompts import WIKI_PROPOSER_PROMPT, WIKI_PROPOSER_SYSTEM_PROMPT

    cfg = config or ProposerConfig()
    iteration = iteration_id(today)
    inputs = build_inputs(
        data_root=data_root, wiki_dir=wiki_dir, skills_dir=skills_dir, today=today, config=cfg
    )
    state = _LoopState(opened_pages=[], opened_skills=[], opened_bodies=[], refusals=[])
    preloaded = (
        _preload_everything(state, wiki_dir=wiki_dir, inputs=inputs)
        if cfg.capacity == "paper"
        else 0
    )
    budget = _budget(
        cfg,
        inputs=inputs,
        system=WIKI_PROPOSER_SYSTEM_PROMPT,
        shell=WIKI_PROPOSER_PROMPT,
        preloaded=preloaded,
    )

    if budget["headroom"] <= 0:
        return _finish(
            data_root,
            wiki_dir=wiki_dir,
            iteration=iteration,
            outcome="fail_closed_budget",
            reason=None,
            state=state,
            proposal=None,
            inputs=inputs,
            budget=budget,
            cfg=cfg,
            dry_run=dry_run,
        )

    outcome, reason, proposal = _drive(
        data_root=data_root,
        wiki_dir=wiki_dir,
        state=state,
        inputs=inputs,
        cfg=cfg,
        template=WIKI_PROPOSER_PROMPT,
        system=WIKI_PROPOSER_SYSTEM_PROMPT,
    )
    return _finish(
        data_root,
        wiki_dir=wiki_dir,
        iteration=iteration,
        outcome=outcome,
        reason=reason,
        state=state,
        proposal=proposal,
        inputs=inputs,
        budget=budget,
        cfg=cfg,
        dry_run=dry_run,
    )


def _drive(
    *,
    data_root: Path,
    wiki_dir: Path,
    state: _LoopState,
    inputs: ProposerInputs,
    cfg: ProposerConfig,
    template: str,
    system: str,
) -> tuple[Outcome, str | None, Proposal | None]:
    """The bounded turn loop. Stops at the first valid proposal (D5: atomic)."""
    log_path = data_root / "logs" / PROPOSER_LOG_NAME
    page_ids = _page_ids(inputs.wiki_index)
    retried = False

    for step in range(cfg.effective_step_cap):
        allow_open = cfg.capacity == "constrained" and not _open_budget_spent(state, cfg)
        schema = _turn_schema(
            page_ids=page_ids, skill_names=inputs.catalog_names, allow_open=allow_open
        )
        prompt = _render_prompt(template, inputs=inputs, state=state, cfg=cfg)
        raw: str | None = None
        try:
            raw = call_turn(prompt, system, schema, cfg.output_reserve, "wiki.proposer")
            turn = parse_turn(raw)
        except TurnFault as fault:
            append_turn_audit(log_path, step=step, prompt=prompt, raw=raw, action=None)
            return fault.outcome, None, None
        action = str(turn.get("action"))
        append_turn_audit(log_path, step=step, prompt=prompt, raw=raw, action=action)

        if action == "abstain":
            return "abstained", scrub_control(_field(turn, "reason"), _REASON_MAX_CHARS), None
        if action == "propose":
            proposal, refusal = validate_proposal(
                turn.get("proposal"),
                opened_pages=tuple(state.opened_pages),
                catalog_names=inputs.catalog_names,
                skill_paths=inputs.skill_paths,
            )
            if proposal is not None:
                return "proposed", None, proposal
            state.refusals.append(("propose", str(refusal)))
        elif _try_open(
            action, turn, state=state, inputs=inputs, wiki_dir=wiki_dir, cfg=cfg, allow=allow_open
        ):
            continue

        if retried:
            return "fail_closed_parse", None, None
        retried = True
    return "fail_closed_parse", None, None


def _try_open(
    action: str,
    turn: dict[str, Any],
    *,
    state: _LoopState,
    inputs: ProposerInputs,
    wiki_dir: Path,
    cfg: ProposerConfig,
    allow: bool,
) -> bool:
    """Run an ``open_*`` action; False when the turn was spent without opening.

    An action the schema did not offer lands here too (a backend that ignored
    the enum, or an ``open_*`` after the budget is spent) and is recorded as
    ``UNOFFERED_ACTION`` rather than silently ignored — the caller then spends
    its single retry on it, exactly as it does for an unknown id.
    """
    if allow and action == "open_page":
        return _handle_open_page(turn, state=state, wiki_dir=wiki_dir, cfg=cfg)
    if allow and action == "open_skill":
        return _handle_open_skill(turn, state=state, inputs=inputs, cfg=cfg)
    if action not in ("open_page", "open_skill"):
        state.refusals.append((action, "UNOFFERED_ACTION"))
    else:
        state.refusals.append((action, "MAX_OPENS_REACHED"))
    return False


def _render_prompt(
    template: str, *, inputs: ProposerInputs, state: _LoopState, cfg: ProposerConfig
) -> str:
    if cfg.capacity == "paper":
        opens_left = 0
    else:
        opens_left = max(0, cfg.max_opens - len(state.opened_pages) - len(state.opened_skills))
    return template.format(
        wiki_index=inputs.wiki_index,
        skill_index=inputs.skill_index,
        evolution=inputs.evolution,
        impact=inputs.impact,
        impact_days=cfg.impact_days,
        opened="\n\n".join(state.opened_bodies) if state.opened_bodies else "(none yet)",
        opens_left=opens_left,
    )


def _finish(
    data_root: Path,
    *,
    wiki_dir: Path,
    iteration: str,
    outcome: Outcome,
    reason: str | None,
    state: _LoopState,
    proposal: Proposal | None,
    inputs: ProposerInputs,
    budget: dict[str, int],
    cfg: ProposerConfig,
    dry_run: bool,
) -> ProposerRun:
    """Render the proposal (unless dry), write the run row, return the record."""
    run_ts = now_iso(timespec="seconds")
    written: Path | None = None
    if proposal is not None and not dry_run:
        current = (
            _read_skill(inputs.skill_paths[proposal.target]) if proposal.kind == "patch" else None
        )
        rendered = render_proposal(
            proposal, current_body=current, iteration=iteration, run_ts=run_ts
        )
        written = _proposal_path(wiki_dir, iteration)
        written.parent.mkdir(parents=True, exist_ok=True)
        from ._io import write_restricted

        write_restricted(written, rendered)

    run = ProposerRun(
        iteration=iteration,
        outcome=outcome,
        reason=reason or None,
        opened_page_ids=tuple(state.opened_pages),
        opened_skill_names=tuple(state.opened_skills),
        proposal=proposal,
        proposal_path=(str(written.relative_to(wiki_dir.parent)) if written is not None else None),
        refusals=tuple(state.refusals),
        budget=budget,
        catalog_size=len(inputs.catalog_names),
        impact_window_days=cfg.impact_days,
        dry_run=dry_run,
    )
    append_audit(
        data_root / "logs" / PROPOSER_LOG_NAME,
        {
            "kind": "run",
            "ts": run_ts,
            "iteration": run.iteration,
            "dry_run": dry_run,
            "outcome": run.outcome,
            "reason": run.reason,
            "index_sha256": hashlib.sha256(inputs.wiki_index.encode("utf-8")).hexdigest(),
            "catalog_size": run.catalog_size,
            "impact_window_days": run.impact_window_days,
            "budget": dict(budget),
            "opened_page_ids": list(run.opened_page_ids),
            "opened_skill_names": list(run.opened_skill_names),
            "proposal": _proposal_record(run),
            "refusals": [list(pair) for pair in run.refusals],
        },
    )
    return run


def _proposal_record(run: ProposerRun) -> dict[str, Any] | None:
    """The proposal as the audit stores it: identity, digest, path — no prose.

    The rendered file is the canonical copy (the same argument the wiki store
    makes about page bodies), so the row carries what is needed to find and
    verify it and nothing that could drift from it.
    """
    proposal = run.proposal
    if proposal is None:
        return None
    return {
        "kind": proposal.kind,
        "name": proposal.name,
        "target": proposal.target,
        "op": proposal.op,
        "cited_pages": list(proposal.cited_pages),
        "body_sha256": hashlib.sha256(proposal.text.encode("utf-8")).hexdigest(),
        "body_chars": len(proposal.text),
        "path": run.proposal_path,
    }
