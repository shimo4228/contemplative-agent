"""CLI entry point for the Contemplative Agent.

Package layout (ADR-0079): the former single-file cli.py is split into
subcommand modules; this ``__init__`` keeps argument parsing, dispatch,
and ``main`` (the console-script entry point — the only re-exported
name; submodule internals are not part of any API surface).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import assert_never

from ..adapters.moltbook.agent import AutonomyLevel
from . import adopt, agent_cmds, memory_cmds, schedule, session_cmds, stocktake_cmd
from .registry import CommandSpec, Tier, build_subparsers, index_by_name
from .runtime import (
    _configure_llm_and_domain,
    _configure_llm_runtime,
    _setup_logging,
)

logger = logging.getLogger(__name__)


# Every subcommand in the CLI, in help-listing order. Each module owns its own
# parser wiring and tier, so a new command is one entry in one module instead
# of paired edits to a parser block and a dispatch table that could disagree.
COMMANDS: tuple[CommandSpec, ...] = (
    *agent_cmds.COMMANDS,
    *session_cmds.COMMANDS,
    *memory_cmds.COMMANDS,
    *schedule.COMMANDS,
    *stocktake_cmd.COMMANDS,
    *adopt.COMMANDS,
)

_COMMANDS_BY_NAME = index_by_name(COMMANDS)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="contemplative-agent",
        description="Contemplative AI agent for Moltbook",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # Domain configuration flags
    parser.add_argument(
        "--domain-config",
        type=Path,
        default=None,
        help="Path to domain.json configuration file",
    )

    # Constitution (CCAI clauses) flags
    parser.add_argument(
        "--constitution-dir",
        type=Path,
        default=None,
        help="Path to constitution directory (e.g. config/constitution/)",
    )
    parser.add_argument(
        "--no-axioms",
        action="store_true",
        help="Disable constitutional clause injection (CCAI clauses) for A/B testing",
    )

    # Autonomy level flags (mutually exclusive)
    autonomy_group = parser.add_mutually_exclusive_group()
    autonomy_group.add_argument(
        "--approve",
        action="store_const",
        const=AutonomyLevel.APPROVE,
        dest="autonomy",
        help="Approval mode: confirm every post (default)",
    )
    autonomy_group.add_argument(
        "--guarded",
        action="store_const",
        const=AutonomyLevel.GUARDED,
        dest="autonomy",
        help="Guarded mode: auto-post if content passes filters",
    )
    autonomy_group.add_argument(
        "--auto",
        action="store_const",
        const=AutonomyLevel.AUTO,
        dest="autonomy",
        help="Auto mode: fully autonomous (use after trust established)",
    )
    parser.set_defaults(autonomy=AutonomyLevel.APPROVE)

    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    build_subparsers(subparsers, COMMANDS)

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    spec = _COMMANDS_BY_NAME.get(args.command)
    if spec is None:
        # Unreachable via argparse (it rejects unknown subcommands), but an
        # entry present in the parser and missing from the index used to fall
        # through to Agent construction instead of failing.
        parser.error(f"unknown command: {args.command}")
        return

    handler = spec.resolve()
    if spec.tier is Tier.NO_LLM:
        handler(args, parser)
        return
    if spec.tier is Tier.LLM_RUNTIME_ONLY:
        _configure_llm_runtime()
        handler(args, parser)
        return

    domain_config = _configure_llm_and_domain(args)
    if spec.tier is Tier.LLM_FULL:
        handler(args, parser)
        return
    if spec.tier is Tier.AGENT:
        # The only tier whose handlers take domain_config as a third argument.
        handler(args, parser, domain_config)
        return
    # Every tier is handled above; assert_never makes a newly added Tier a
    # type error here rather than a TypeError inside whichever handler happens
    # to accept the argument count this branch guesses at.
    assert_never(spec.tier)
