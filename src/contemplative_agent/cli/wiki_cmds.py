"""``wiki-maintain`` / ``wiki-propose`` — the two wiki loops (RFC-0017 S2/S3).

A thin handler: it resolves paths from :mod:`adapters.moltbook.config`, calls
:func:`core.wiki_maintainer.run_maintainer`, and prints what happened. Every
decision lives in core, which takes ``data_root`` / ``wiki_dir`` as arguments
and never reads the config module (ADR-0001).

Neither is approval-gated (ADR-0012). Both write only into the derived layer —
``wiki/patterns/`` and ``wiki/proposals/`` — and RFC-0017 D6/D10 puts the human
gate at the point a proposal reaches staging, which is S6's job and not
reachable from here. Both take ``--dry-run``: call the model, record the
would-be result, change nothing on disk.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .registry import CommandSpec, Tier

if TYPE_CHECKING:  # the core import stays lazy at runtime (see the module docstring)
    from ..core.wiki_maintainer import MaintainerRun


def _add_wiki_maintain_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        dest="wiki_date",
        default=None,
        metavar="YYYY-MM-DD",
        help="UTC day to read (default: yesterday, the last day that is complete)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Call the model and audit the would-be ops without changing any page",
    )
    parser.add_argument(
        "--catch-up-days",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Also read the N days before yesterday, oldest first (default 0). "
            "A day an earlier run could not finish is resumed, not re-read"
        ),
    )


def _resolve_day(raw: str | None, parser: argparse.ArgumentParser) -> date:
    """The target UTC day.

    Yesterday by default, not today: the Maintainer runs after distill in the
    same slot, and a partial day would leave the rest of it unread — a re-run
    resumes from the batch rows in the audit log (the episodes an earlier run
    already consumed), so it would never come back for the missing hours.
    """
    if raw is None:
        return (datetime.now(timezone.utc) - timedelta(days=1)).date()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        parser.error(f"--date must be YYYY-MM-DD, got {raw!r}")
        raise  # unreachable: parser.error exits


def _resolve_days(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[date]:
    """The days to read, oldest first.

    ``--catch-up-days`` names an explicit day, so combining it with ``--date``
    would ask for two different answers to the same question; refused rather
    than silently preferring one.
    """
    catch_up = int(getattr(args, "catch_up_days", 0) or 0)
    raw = getattr(args, "wiki_date", None)
    if raw is not None and catch_up:
        parser.error("--date and --catch-up-days are mutually exclusive")
    if catch_up < 0:
        parser.error("--catch-up-days must be 0 or more")
    last = _resolve_day(raw, parser)
    return [last - timedelta(days=offset) for offset in range(catch_up, -1, -1)]


def _print_run(run: MaintainerRun, *, detailed: bool) -> None:
    """One line per day, plus the full block when a single day was asked for."""
    mode = " (dry-run)" if run.dry_run else ""
    batches = len(run.batches)
    print(f"wiki-maintain {run.date}{mode}: {run.outcome} ({batches} batches)")
    if not detailed:
        return
    if run.reason:
        print(f"  reason: {run.reason}")
    print(
        f"  episodes: {len(run.episode_ids_read)} read, "
        f"{len(run.episode_ids_skipped)} skipped "
        f"(budget {run.budget.get('episodes', 0)} tokens)"
    )
    print(f"  batches: {batches}")
    for applied in run.ops_applied:
        print(f"  applied: {applied}")
    for op, reason in run.ops_refused:
        print(f"  refused: {op} ({reason})")
    print(
        f"  wiki: {run.wiki_size.pages} pages, "
        f"index {run.wiki_size.index_tokens} tokens, "
        f"page chars p90 {run.wiki_size.page_chars_p90}"
    )


def _handle_wiki_maintain(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from ..adapters.moltbook import config
    from ..core._io import acquire_run_lock
    from ..core.wiki_maintainer import MaintainerConfig, run_days

    days = _resolve_days(args, parser)

    # Blocking lock, like distill (audit M5): this is a scheduled job on the
    # same single local Ollama, and its 04:15 slot is only clear of distill's
    # 03:30 while distill finishes inside 45 minutes — which nothing enforces.
    # Waiting costs a later start; overlapping costs both jobs on a 16GB box.
    # Held across the whole catch-up: the days are one job, not N jobs.
    with acquire_run_lock(config.RUN_LOCK_PATH, blocking=True):
        runs = run_days(
            data_root=config.MOLTBOOK_DATA_DIR,
            wiki_dir=config.WIKI_DIR,
            days=days,
            config=MaintainerConfig(),
            dry_run=bool(getattr(args, "dry_run", False)),
        )

    for run in runs:
        _print_run(run, detailed=len(runs) == 1)


def _add_wiki_propose_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Call the model and audit the would-be proposal without writing it",
    )
    parser.add_argument(
        "--max-opens",
        type=int,
        default=None,
        metavar="N",
        help="Wiki pages plus skills one run may open before it must propose or abstain (default 3)",
    )
    parser.add_argument(
        "--impact-days",
        type=int,
        default=None,
        metavar="N",
        help="Window for the skill-impact table (default 28)",
    )


def _handle_wiki_propose(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from datetime import datetime, timezone

    from ..adapters.moltbook import config
    from ..core.wiki_proposer import ProposerConfig, run_proposer

    # Named rather than ``**overrides``: an unrecognised key in a splat is a
    # silent widening, and only these two are the caller's to set.
    defaults = ProposerConfig()
    max_opens = getattr(args, "max_opens", None)
    impact_days = getattr(args, "impact_days", None)
    cfg = ProposerConfig(
        max_opens=defaults.max_opens if max_opens is None else max_opens,
        impact_days=defaults.impact_days if impact_days is None else impact_days,
    )

    run = run_proposer(
        data_root=config.MOLTBOOK_DATA_DIR,
        wiki_dir=config.WIKI_DIR,
        skills_dir=config.SKILLS_DIR,
        today=datetime.now(timezone.utc).date(),
        config=cfg,
        dry_run=bool(getattr(args, "dry_run", False)),
    )

    mode = " (dry-run)" if run.dry_run else ""
    print(f"wiki-propose {run.iteration}{mode}: {run.outcome}")
    if run.reason:
        print(f"  reason: {run.reason}")
    print(
        f"  inputs: {run.catalog_size} skills, impact window {run.impact_window_days}d, "
        f"{run.budget['inputs']} tokens ({run.budget['headroom']} headroom)"
    )
    if run.opened_page_ids:
        print(f"  opened: {', '.join(run.opened_page_ids)}")
    if run.opened_skill_names:
        print(f"  opened skills: {', '.join(run.opened_skill_names)}")
    if run.proposal is not None:
        subject = run.proposal.name or run.proposal.target
        print(f"  proposal: {run.proposal.kind} {subject} (cites {len(run.proposal.cited_pages)})")
        if run.proposal_path:
            print(f"  written: {run.proposal_path}")
    for action, reason in run.refusals:
        print(f"  refused: {action} ({reason})")


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="wiki-maintain",
        help=(
            "Read one UTC day of episodes and create or patch wiki pattern pages "
            "(RFC-0017 Maintainer; no approval gate, --dry-run available)"
        ),
        handler=_handle_wiki_maintain,
        # LLM_RUNTIME_ONLY, like skill-stocktake: the Maintainer supplies its
        # own system prompt and must not inherit the skills / rules / axioms
        # corpus — the value layer is what this experiment observes, not an
        # input to it (prompt-scaffold-vs-value-layers). It still needs
        # per-call telemetry and the untrusted-guard audit, which is exactly
        # what this tier configures.
        tier=Tier.LLM_RUNTIME_ONLY,
        add_arguments=_add_wiki_maintain_arguments,
    ),
    CommandSpec(
        name="wiki-propose",
        help=(
            "Read the wiki, the skill index, the evolution log and skill impact, and "
            "produce one atomic would-be proposal (RFC-0017 Proposer; writes nothing "
            "into skills/ — the human gate is at staging, S6)"
        ),
        handler=_handle_wiki_propose,
        tier=Tier.LLM_RUNTIME_ONLY,
        add_arguments=_add_wiki_propose_arguments,
    ),
)
