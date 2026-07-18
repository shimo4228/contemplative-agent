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
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..adapters.moltbook.agent import Agent, AutonomyLevel
from ..core._io import acquire_run_lock
from ..core.domain import DomainConfig, get_domain_config
from ..core.run_context import new_session_id, set_session_id
from .adopt import _handle_adopt_staged, _handle_remove_skill
from .memory_cmds import (
    _handle_amend_constitution,
    _handle_distill,
    _handle_distill_identity,
    _handle_enrich,
    _handle_insight,
    _handle_rules_distill,
)
from .runtime import (
    _configure_llm_and_domain,
    _configure_llm_runtime,
    _llm_session_meta,
    _setup_logging,
)
from .schedule import _handle_install_schedule
from .session_cmds import (
    _handle_dialogue,
    _handle_dialogue_peer,
    _handle_generate_report,
    _handle_init,
    _handle_meditate,
    _handle_report,
    _handle_sync_data,
)
from .stocktake_cmd import _handle_rules_stocktake, _handle_skill_stocktake

logger = logging.getLogger(__name__)


def _handle_agent_command(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    agent = Agent(autonomy=args.autonomy, domain_config=domain_config)

    if args.command == "register":
        result = agent.do_register()
        print(f"Registration result: {result}")
    elif args.command == "status":
        result = agent.do_status()
        print(f"Agent status: {result}")
    elif args.command == "run":
        if args.session <= 0 or args.session > 1440:
            parser.error("--session must be between 1 and 1440 minutes")
        dc = domain_config or get_domain_config()
        # Session identity (ADR-0078 follow-up): every audit record written
        # while this session runs carries session_id via the shared writer.
        # Cleared in finally — a same-process caller (tests, embedding) must
        # not have later non-session writes stamped with a stale session_id.
        session_id = new_session_id()
        set_session_id(session_id)
        session_meta = {
            "axioms_enabled": not args.no_axioms,
            "domain": dc.name,
            "session_id": session_id,
            **_llm_session_meta(),
        }
        try:
            # Non-blocking lock (audit M5): a second concurrent session would
            # double-spend rate budgets and race knowledge.json — fail fast
            # with a clear message instead of queueing behind it.
            with acquire_run_lock(config.RUN_LOCK_PATH, blocking=False) as acquired:
                if not acquired:
                    print(
                        f"Another run/distill process holds the run lock ({config.RUN_LOCK_PATH}); exiting."
                    )
                    return
                agent.run_session(duration_minutes=args.session, session_meta=session_meta)
        finally:
            set_session_id(None)
    elif args.command == "solve":
        agent.do_solve(args.text)


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

    # register
    subparsers.add_parser("register", help="Register a new agent on Moltbook")

    # status
    subparsers.add_parser("status", help="Check agent status")

    # run
    run_parser = subparsers.add_parser("run", help="Run autonomous session")
    run_parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes (default: 60)",
    )

    # init
    init_parser = subparsers.add_parser("init", help="Initialize identity and knowledge files")
    init_parser.add_argument(
        "--template",
        type=str,
        default="contemplative",
        help="Character template to use (default: contemplative)",
    )

    # distill
    distill_parser = subparsers.add_parser(
        "distill", help="Distill recent episodes into learned patterns"
    )
    distill_parser.add_argument(
        "--days", type=int, default=1, help="Days of episodes to process (default: 1)"
    )
    distill_parser.add_argument(
        "--dry-run", action="store_true", help="Show results without writing"
    )
    distill_parser.add_argument(
        "--file",
        type=Path,
        nargs="+",
        dest="log_files",
        help="Explicit JSONL log file(s) to process (overrides --days)",
    )

    # distill-identity
    distill_id_parser = subparsers.add_parser(
        "distill-identity", help="Distill knowledge into identity (without pattern distillation)"
    )
    distill_id_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write to staging dir instead of interactive approval (for coding agents)",
    )

    # rules-distill
    rules_distill_parser = subparsers.add_parser(
        "rules-distill", help="Distill universal behavioral rules from skill files"
    )
    rules_distill_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (not just new ones)"
    )
    rules_distill_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write to staging dir instead of interactive approval (for coding agents)",
    )

    # amend-constitution
    amend_parser = subparsers.add_parser(
        "amend-constitution",
        help="Propose amendments to the constitution from accumulated ethical experience",
    )
    amend_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write to staging dir instead of interactive approval (for coding agents)",
    )

    # report
    report_parser = subparsers.add_parser(
        "report", help="Show self-improvement metrics from episode logs"
    )
    report_parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    report_parser.add_argument(
        "--format",
        choices=["text", "md"],
        default="text",
        help="Output format (default: text)",
    )
    report_parser.add_argument(
        "--patterns",
        action="store_true",
        help="Append read-only knowledge-pattern composition instruments "
        "(consumed-view supply / diversity)",
    )
    report_parser.add_argument(
        "--skill-selection",
        action="store_true",
        help="Append the read-only skill-selection shadow reading "
        "(per-skill frequency, never-selected, would-be token reduction; "
        "ADR-0076)",
    )

    # generate-report
    gen_report_parser = subparsers.add_parser(
        "generate-report", help="Generate activity report from episode logs"
    )
    gen_report_parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to generate report for (YYYY-MM-DD, default: today)",
    )
    gen_report_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_dates",
        help="Generate reports for all available log dates",
    )

    # install-schedule
    schedule_parser = subparsers.add_parser(
        "install-schedule", help="Install/uninstall launchd schedule for periodic sessions"
    )
    schedule_parser.add_argument(
        "--interval",
        type=int,
        default=6,
        help="Hours between sessions (default: 6)",
    )
    schedule_parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes (default: 60)",
    )
    schedule_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed schedule",
    )
    schedule_parser.add_argument(
        "--no-distill",
        action="store_true",
        help="Skip installing daily distillation schedule",
    )
    schedule_parser.add_argument(
        "--distill-hour",
        type=int,
        default=3,
        help="Hour to run daily distillation (0-23, default: 3)",
    )
    schedule_parser.add_argument(
        "--weekly-analysis",
        action="store_true",
        help="Also install weekly analysis report schedule",
    )
    schedule_parser.add_argument(
        "--weekly-analysis-day",
        type=int,
        default=1,
        help="Day of week for weekly analysis (0=Sun..6=Sat, default: 1=Mon)",
    )
    schedule_parser.add_argument(
        "--weekly-analysis-hour",
        type=int,
        default=9,
        help="Hour to run weekly analysis (0-23, default: 9)",
    )
    schedule_parser.add_argument(
        "--weekly-insight",
        action="store_true",
        help="Also install weekly staged insight schedule (ADR-0074)",
    )
    schedule_parser.add_argument(
        "--weekly-insight-day",
        type=int,
        default=1,
        help="Day of week for weekly insight (0=Sun..6=Sat, default: 1=Mon)",
    )
    schedule_parser.add_argument(
        "--weekly-insight-hour",
        type=int,
        default=8,
        help=(
            "Hour to run weekly insight (0-23, default: 8 — one hour before "
            "weekly analysis, outside agent-session hours)"
        ),
    )
    schedule_parser.add_argument(
        "--weekly-backup",
        action="store_true",
        help="Also install weekly runtime backup schedule (private off-site mirror)",
    )
    schedule_parser.add_argument(
        "--weekly-backup-day",
        type=int,
        default=1,
        help="Day of week for weekly backup (0=Sun..6=Sat, default: 1=Mon)",
    )
    schedule_parser.add_argument(
        "--weekly-backup-hour",
        type=int,
        default=10,
        help="Hour to run weekly backup (0-23, default: 10 — outside agent-session hours)",
    )

    # insight
    insight_parser = subparsers.add_parser(
        "insight", help="Extract behavioral skill from accumulated knowledge"
    )
    insight_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
    )
    insight_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write to staging dir instead of interactive approval (for coding agents)",
    )

    # meditate
    meditate_parser = subparsers.add_parser(
        "meditate", help="Run active inference meditation on episode history"
    )
    meditate_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days of episodes to build POMDP from (default: 7)",
    )
    meditate_parser.add_argument(
        "--cycles",
        type=int,
        default=50,
        help="Number of meditation cycles (default: 50)",
    )
    meditate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show results without writing to knowledge store",
    )

    # dialogue — spawn two peer agents (each rooted at a different MOLTBOOK_HOME)
    # and pipe them together for a local turn-based conversation.
    dialogue_parser = subparsers.add_parser(
        "dialogue",
        help="Run a local dialogue between two agent instances (two MOLTBOOK_HOMEs)",
    )
    dialogue_parser.add_argument(
        "home_a",
        type=Path,
        help="MOLTBOOK_HOME for agent A (initiator). Must be pre-initialised.",
    )
    dialogue_parser.add_argument(
        "home_b",
        type=Path,
        help="MOLTBOOK_HOME for agent B (responder). Must be pre-initialised.",
    )
    dialogue_parser.add_argument(
        "--seed",
        type=str,
        required=True,
        help="Opening message from agent A that starts the dialogue",
    )
    dialogue_parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Max reply turns per side (hard cap, default: 5)",
    )

    # dialogue-peer — internal entry for each peer subprocess. Reads JSON line
    # messages from stdin, writes replies to stdout. Users should not invoke
    # this directly; it is spawned by `dialogue`.
    dialogue_peer_parser = subparsers.add_parser(
        "dialogue-peer",
        help="(internal) one side of a dialogue — spawned by 'dialogue'",
    )
    dialogue_peer_parser.add_argument(
        "--turns",
        type=int,
        required=True,
        help="Max reply turns this peer will generate",
    )
    dialogue_peer_parser.add_argument(
        "--seed",
        type=str,
        default=None,
        help="Opening message if this peer is the initiator",
    )
    dialogue_peer_parser.add_argument(
        "--label",
        type=str,
        default="peer",
        help="Short label for stderr traces",
    )

    # skill-stocktake
    skill_stocktake_parser = subparsers.add_parser(
        "skill-stocktake", help="Audit skills for duplicates and quality issues"
    )
    skill_stocktake_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write merged skills to staging dir instead of interactive approval",
    )

    # rules-stocktake
    rules_stocktake_parser = subparsers.add_parser(
        "rules-stocktake", help="Audit rules for duplicates and quality issues"
    )
    rules_stocktake_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write merged rules to staging dir instead of interactive approval",
    )

    # enrich
    enrich_parser = subparsers.add_parser(
        "enrich",
        help=(
            "(deprecated, no-op since ADR-0019) formerly enriched patterns "
            "with subcategories; subcategorisation is now query-time via views"
        ),
    )
    enrich_parser.add_argument(
        "--dry-run", action="store_true", help="Show results without writing"
    )

    # sync-data
    subparsers.add_parser("sync-data", help="Sync research data to external git repository")

    # adopt-staged
    adopt_p = subparsers.add_parser(
        "adopt-staged",
        help="Review files in the staging dir through the approval gate and adopt accepted ones",
    )
    adopt_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Auto-approve all staged items without prompting "
        "(for non-TTY / coding-agent workflows where stdin is not interactive)",
    )

    # remove-skill
    remove_skill_p = subparsers.add_parser(
        "remove-skill",
        help="Remove a skill from skills_dir with an audit trail",
    )
    remove_skill_p.add_argument(
        "name",
        help="Skill filename stem (with or without .md suffix)",
    )
    remove_skill_p.add_argument(
        "--reason",
        required=True,
        help="Justification recorded in audit.jsonl (required, non-empty)",
    )
    remove_skill_p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive prompt "
        "(for non-TTY / coding-agent workflows where stdin is not interactive)",
    )
    remove_skill_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the target without deleting or writing audit",
    )

    # solve
    solve_parser = subparsers.add_parser("solve", help="Test verification solver")
    solve_parser.add_argument("text", help="Obfuscated challenge text")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Tier 1: Commands that don't need LLM or domain config
    no_llm_handlers: dict[str, Callable[..., None]] = {
        "install-schedule": _handle_install_schedule,
        "sync-data": _handle_sync_data,
        "adopt-staged": _handle_adopt_staged,
        "remove-skill": _handle_remove_skill,
        "dialogue": _handle_dialogue,
    }
    handler = no_llm_handlers.get(args.command)
    if handler:
        handler(args, parser)
        return

    # Tier 1.5: LLM commands that need per-call telemetry but NOT the
    # skills/rules/axioms corpus (review 2026-06-27 M1). Stocktake calls
    # generate() with its own explicit system prompts, so loading the corpus
    # would pollute its prompt environment; routing here (instead of the old
    # no_llm_handlers slot) makes telemetry apply instead of silently running
    # with no telemetry.
    llm_runtime_only_handlers: dict[str, Callable[..., None]] = {
        "skill-stocktake": _handle_skill_stocktake,
        "rules-stocktake": _handle_rules_stocktake,
    }
    handler = llm_runtime_only_handlers.get(args.command)
    if handler:
        _configure_llm_runtime()
        handler(args, parser)
        return

    # Tier 2: Commands that need LLM/domain config but not Agent
    domain_config = _configure_llm_and_domain(args)

    llm_handlers: dict[str, Callable[..., None]] = {
        "init": _handle_init,
        "distill": _handle_distill,
        "enrich": _handle_enrich,
        "distill-identity": _handle_distill_identity,
        "insight": _handle_insight,
        "rules-distill": _handle_rules_distill,
        "amend-constitution": _handle_amend_constitution,
        "report": _handle_report,
        "generate-report": _handle_generate_report,
        "meditate": _handle_meditate,
        "dialogue-peer": _handle_dialogue_peer,
    }
    handler = llm_handlers.get(args.command)
    if handler:
        handler(args, parser)
        return

    # Tier 3: Commands that need an Agent instance
    _handle_agent_command(args, parser, domain_config)
