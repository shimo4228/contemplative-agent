"""``wiki-maintain`` — one day's Maintainer pass (RFC-0017 S2).

A thin handler: it resolves paths from :mod:`adapters.moltbook.config`, calls
:func:`core.wiki_maintainer.run_maintainer`, and prints what happened. Every
decision lives in core, which takes ``data_root`` / ``wiki_dir`` as arguments
and never reads the config module (ADR-0001).

Not an approval-gated command (ADR-0012). The wiki is a derived layer with no
human gate — RFC-0017 D6/D10 puts the gate at the Proposer's staging, not here
— so this runs unattended and needs no ``--yes`` sibling. What it does have is
``--dry-run``, which calls the model and records the would-be ops without
touching a page.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

from .registry import CommandSpec, Tier


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
        "--max-opens",
        type=int,
        default=None,
        metavar="N",
        help="How many wiki pages one run may open before it must write or abstain (default 3)",
    )


def _resolve_day(raw: str | None, parser: argparse.ArgumentParser) -> date:
    """The target UTC day.

    Yesterday by default, not today: the Maintainer runs after distill in the
    same slot, and a partial day would be sampled twice — once incomplete now,
    never again — because the seed is weekly and the run is idempotent by
    date, not by content.
    """
    if raw is None:
        return (datetime.now(timezone.utc) - timedelta(days=1)).date()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        parser.error(f"--date must be YYYY-MM-DD, got {raw!r}")
        raise  # unreachable: parser.error exits


def _handle_wiki_maintain(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from ..adapters.moltbook import config
    from ..core.wiki_maintainer import MaintainerConfig, run_maintainer

    day = _resolve_day(getattr(args, "wiki_date", None), parser)
    max_opens = getattr(args, "max_opens", None)
    cfg = MaintainerConfig() if max_opens is None else MaintainerConfig(max_opens=max_opens)

    run = run_maintainer(
        data_root=config.MOLTBOOK_DATA_DIR,
        wiki_dir=config.WIKI_DIR,
        day=day,
        config=cfg,
        dry_run=bool(getattr(args, "dry_run", False)),
    )

    mode = " (dry-run)" if run.dry_run else ""
    print(f"wiki-maintain {run.date}{mode}: {run.outcome}")
    if run.reason:
        print(f"  reason: {run.reason}")
    print(
        f"  episodes: {len(run.episode_ids_read)} read, "
        f"{len(run.episode_ids_skipped)} skipped "
        f"(budget {run.budget['episodes']} tokens)"
    )
    if run.opened_page_ids:
        print(f"  opened: {', '.join(run.opened_page_ids)}")
    for applied in run.ops_applied:
        print(f"  applied: {applied}")
    for op, reason in run.ops_refused:
        print(f"  refused: {op} ({reason})")
    print(
        f"  wiki: {run.wiki_size.pages} pages, "
        f"index {run.wiki_size.index_tokens} tokens, "
        f"page chars p90 {run.wiki_size.page_chars_p90}"
    )


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
)
