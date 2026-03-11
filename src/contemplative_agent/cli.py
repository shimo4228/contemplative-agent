"""CLI entry point for the Contemplative Agent."""

import argparse
import logging
import os
import stat
import sys
from pathlib import Path

from .adapters.moltbook.agent import Agent, AutonomyLevel
from .adapters.moltbook.config import IDENTITY_PATH, KNOWLEDGE_PATH, MOLTBOOK_DATA_DIR
from .core.domain import (
    get_rules,
    load_domain_config,
    load_rules,
    reset_caches,
    set_domain_config_cache,
    set_rules_cache,
)
from .core.llm import configure as configure_llm, get_default_system_prompt


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _do_init() -> None:
    """Initialize identity.md and knowledge.md files."""
    MOLTBOOK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if IDENTITY_PATH.exists():
        print(f"Identity file already exists: {IDENTITY_PATH}")
    else:
        IDENTITY_PATH.write_text(get_default_system_prompt(), encoding="utf-8")
        os.chmod(IDENTITY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created identity file: {IDENTITY_PATH}")

    if KNOWLEDGE_PATH.exists():
        print(f"Knowledge file already exists: {KNOWLEDGE_PATH}")
    else:
        KNOWLEDGE_PATH.write_text("# Knowledge Base\n\n## Agent Relationships\n\n## Recent Post Topics\n\n## Insights\n\n## Learned Patterns\n", encoding="utf-8")
        os.chmod(KNOWLEDGE_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created knowledge file: {KNOWLEDGE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="contemplative-agent",
        description="Contemplative AI agent for Moltbook",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    # Domain configuration flags
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=None,
        help="Path to domain rules directory (e.g. config/rules/contemplative/)",
    )
    parser.add_argument(
        "--domain-config",
        type=Path,
        default=None,
        help="Path to domain.json configuration file",
    )

    # Contemplative axioms (CCAI) flag
    parser.add_argument(
        "--no-axioms",
        action="store_true",
        help="Disable contemplative axiom injection (CCAI clauses) for A/B testing",
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

    # introduce
    subparsers.add_parser("introduce", help="Post introduction template")

    # run
    run_parser = subparsers.add_parser("run", help="Run autonomous session")
    run_parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes (default: 60)",
    )

    # init
    subparsers.add_parser("init", help="Initialize identity and knowledge files")

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

    # solve
    solve_parser = subparsers.add_parser(
        "solve", help="Test verification solver"
    )
    solve_parser.add_argument("text", help="Obfuscated challenge text")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Load domain config and rules if custom paths specified
    domain_config = None
    if args.domain_config is not None or args.rules_dir is not None:
        reset_caches()
    if args.domain_config is not None:
        domain_config = load_domain_config(args.domain_config)
        set_domain_config_cache(domain_config)
    if args.rules_dir is not None:
        set_rules_cache(load_rules(args.rules_dir))

    # Load and inject CCAI constitutional clauses unless --no-axioms is set
    if not args.no_axioms:
        clauses = get_rules().constitutional_clauses
        if clauses:
            configure_llm(axiom_prompt=clauses)

    if args.command == "init":
        _do_init()
        return

    if args.command == "distill":
        from .core.distill import distill

        result = distill(days=args.days, dry_run=args.dry_run)
        print(result)
        return

    agent = Agent(autonomy=args.autonomy, domain_config=domain_config)

    if args.command == "register":
        result = agent.do_register()
        print(f"Registration result: {result}")

    elif args.command == "status":
        result = agent.do_status()
        print(f"Agent status: {result}")

    elif args.command == "introduce":
        agent.do_introduce()

    elif args.command == "run":
        if args.session <= 0 or args.session > 1440:
            parser.error("--session must be between 1 and 1440 minutes")
        agent.run_session(duration_minutes=args.session)

    elif args.command == "solve":
        agent.do_solve(args.text)


if __name__ == "__main__":
    main()
