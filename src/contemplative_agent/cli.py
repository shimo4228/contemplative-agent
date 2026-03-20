"""CLI entry point for the Contemplative Agent."""

import argparse
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from .adapters.moltbook.agent import Agent, AutonomyLevel
from .adapters.moltbook.config import (
    IDENTITY_PATH,
    KNOWLEDGE_PATH,
    MOLTBOOK_DATA_DIR,
    SKILLS_DIR,
)
from .core.domain import (
    DEFAULT_RULES_DIR,
    get_domain_config,
    get_rules,
    load_domain_config,
    load_rules,
    reset_caches,
    set_domain_config_cache,
    set_rules_cache,
)
from .core.llm import configure as configure_llm


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


LAUNCHD_LABEL = "com.moltbook.agent"
LAUNCHD_DISTILL_LABEL = "com.moltbook.distill"
LAUNCHD_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_LABEL}.plist"
LAUNCHD_DISTILL_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_DISTILL_LABEL}.plist"


def _build_calendar_intervals(interval_hours: int) -> str:
    """Build StartCalendarInterval XML entries for given hour interval."""
    entries = []
    for hour in range(0, 24, interval_hours):
        entries.append(
            f"\t\t<dict>"
            f"<key>Hour</key><integer>{hour}</integer>"
            f"<key>Minute</key><integer>0</integer>"
            f"</dict>"
        )
    return "\n".join(entries)


def _install_plist(
    template_name: str,
    plist_path: Path,
    log_name: str,
    substitutions: dict[str, str],
) -> Path:
    """Install a launchd plist from a template.

    Returns the log path for caller messaging.
    """
    project_root = Path(__file__).resolve().parents[2]
    template_path = project_root / "config" / "launchd" / template_name

    if not template_path.exists():
        print(f"Error: Template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    venv_bin = project_root / ".venv" / "bin"
    if not venv_bin.exists():
        print(f"Error: venv not found: {venv_bin}", file=sys.stderr)
        sys.exit(1)

    log_path = MOLTBOOK_DATA_DIR / "logs" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)

    template = template_path.read_text(encoding="utf-8")
    plist_content = template
    for key, value in {
        "{{VENV_BIN}}": xml_escape(str(venv_bin)),
        "{{PROJECT_ROOT}}": xml_escape(str(project_root)),
        "{{LOG_PATH}}": xml_escape(str(log_path)),
        **substitutions,
    }.items():
        plist_content = plist_content.replace(key, value)

    LAUNCHD_PLIST_DIR.mkdir(parents=True, exist_ok=True)

    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Warning: launchctl unload: {result.stderr.strip()}", file=sys.stderr)

    plist_path.write_text(plist_content, encoding="utf-8")
    os.chmod(plist_path, stat.S_IRUSR | stat.S_IWUSR)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: launchctl load failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return log_path


def _do_install_schedule(interval: int, session: int) -> None:
    """Install launchd plist for periodic agent sessions (macOS only)."""
    if sys.platform != "darwin":
        print("Error: install-schedule is only supported on macOS (launchd).", file=sys.stderr)
        sys.exit(1)

    log_path = _install_plist(
        template_name="com.moltbook.agent.plist",
        plist_path=LAUNCHD_PLIST_PATH,
        log_name="agent-launchd.log",
        substitutions={
            "{{SESSION_MINUTES}}": str(session),
            "{{CALENDAR_INTERVALS}}": _build_calendar_intervals(interval),
        },
    )

    hours = list(range(0, 24, interval))
    schedule_str = ", ".join(f"{h:02d}:00" for h in hours)
    print(f"Installed: {LAUNCHD_PLIST_PATH}")
    print(f"Schedule: every {interval}h ({schedule_str}), {session}min sessions")
    print(f"Logs: {log_path}")


def _do_install_distill_schedule(distill_hour: int) -> None:
    """Install launchd plist for daily memory distillation (macOS only)."""
    _install_plist(
        template_name="com.moltbook.distill.plist",
        plist_path=LAUNCHD_DISTILL_PLIST_PATH,
        log_name="distill-launchd.log",
        substitutions={"{{DISTILL_HOUR}}": str(distill_hour)},
    )

    print(f"Installed: {LAUNCHD_DISTILL_PLIST_PATH}")
    print(f"Schedule: daily at {distill_hour:02d}:00 (distill --days 1 --identity)")


def _do_uninstall_schedule() -> None:
    """Uninstall launchd plists (session + distill)."""
    removed = False

    for plist_path, label in [
        (LAUNCHD_PLIST_PATH, "session"),
        (LAUNCHD_DISTILL_PLIST_PATH, "distill"),
    ]:
        if not plist_path.exists():
            continue
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Warning: launchctl unload ({label}): {result.stderr.strip()}", file=sys.stderr)
        plist_path.unlink()
        print(f"Removed: {plist_path}")
        removed = True

    if not removed:
        print("No schedule installed.")


def _do_init(rules_dir: Optional[Path] = None) -> None:
    """Initialize identity.md and knowledge.json files."""
    MOLTBOOK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if IDENTITY_PATH.exists():
        print(f"Identity file already exists: {IDENTITY_PATH}")
    else:
        # Use introduction as identity seed
        rules = get_rules(rules_dir)
        identity_content = rules.introduction or ""
        IDENTITY_PATH.write_text(identity_content + "\n", encoding="utf-8")
        os.chmod(IDENTITY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created identity file: {IDENTITY_PATH}")

    if KNOWLEDGE_PATH.exists():
        print(f"Knowledge file already exists: {KNOWLEDGE_PATH}")
    else:
        import json as _json
        KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_PATH.write_text(_json.dumps([], ensure_ascii=False) + "\n", encoding="utf-8")
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
    distill_parser.add_argument(
        "--identity", action="store_true", help="Also distill knowledge into identity"
    )
    distill_parser.add_argument(
        "--file", type=Path, nargs="+", dest="log_files",
        help="Explicit JSONL log file(s) to process (overrides --days)"
    )

    # report
    report_parser = subparsers.add_parser(
        "report", help="Show self-improvement metrics from episode logs"
    )
    report_parser.add_argument(
        "--days", type=int, default=7, help="Days to look back (default: 7)"
    )
    report_parser.add_argument(
        "--format", choices=["text", "md"], default="text",
        help="Output format (default: text)",
    )

    # generate-report
    gen_report_parser = subparsers.add_parser(
        "generate-report", help="Generate activity report from episode logs"
    )
    gen_report_parser.add_argument(
        "--date", type=str, default=None,
        help="Date to generate report for (YYYY-MM-DD, default: today)",
    )
    gen_report_parser.add_argument(
        "--all", action="store_true", dest="all_dates",
        help="Generate reports for all available log dates",
    )

    # install-schedule
    schedule_parser = subparsers.add_parser(
        "install-schedule", help="Install/uninstall launchd schedule for periodic sessions"
    )
    schedule_parser.add_argument(
        "--interval", type=int, default=6,
        help="Hours between sessions (default: 6)",
    )
    schedule_parser.add_argument(
        "--session", type=int, default=120,
        help="Session duration in minutes (default: 120)",
    )
    schedule_parser.add_argument(
        "--uninstall", action="store_true",
        help="Remove installed schedule",
    )
    schedule_parser.add_argument(
        "--no-distill", action="store_true",
        help="Skip installing daily distillation schedule",
    )
    schedule_parser.add_argument(
        "--distill-hour", type=int, default=3,
        help="Hour to run daily distillation (0-23, default: 3)",
    )

    # insight
    insight_parser = subparsers.add_parser(
        "insight", help="Extract behavioral skill from accumulated knowledge"
    )
    insight_parser.add_argument(
        "--dry-run", action="store_true", help="Show result without writing"
    )
    insight_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
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

    # Commands that don't need LLM or domain config — handle before loading
    if args.command == "install-schedule":
        if args.uninstall:
            _do_uninstall_schedule()
        else:
            if args.interval < 1 or args.interval > 24 or 24 % args.interval != 0:
                parser.error("--interval must evenly divide 24 (1, 2, 3, 4, 6, 8, 12, 24)")
            if args.session < 1 or args.session > 1440:
                parser.error("--session must be between 1 and 1440 minutes")
            if args.distill_hour < 0 or args.distill_hour > 23:
                parser.error("--distill-hour must be between 0 and 23")
            _do_install_schedule(interval=args.interval, session=args.session)
            if not args.no_distill:
                _do_install_distill_schedule(distill_hour=args.distill_hour)
        return

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

    # Inject learned skills into system prompt
    skills_dir = SKILLS_DIR
    if skills_dir.is_dir():
        configure_llm(skills_dir=skills_dir)

    if args.command == "init":
        _do_init(rules_dir=args.rules_dir)
        return

    if args.command == "distill":
        from .core.distill import distill, distill_identity
        from .core.memory import EpisodeLog, KnowledgeStore

        log_dir = MOLTBOOK_DATA_DIR / "logs"
        log_files = args.log_files
        if log_files:
            for f in log_files:
                if not f.exists():
                    parser.error(f"File not found: {f}")
                if f.suffix != ".jsonl":
                    parser.error(f"Not a JSONL file: {f}")
        episode_log = EpisodeLog(log_dir=log_dir)
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        result = distill(
            days=args.days,
            dry_run=args.dry_run,
            episode_log=episode_log,
            knowledge_store=knowledge_store,
            log_files=log_files,
        )
        print(result)

        if args.identity:
            print("\n--- Identity Distillation ---")
            identity_result = distill_identity(
                knowledge_store=knowledge_store,
                identity_path=IDENTITY_PATH,
                dry_run=args.dry_run,
            )
            print(identity_result)
        return

    if args.command == "insight":
        from .core.insight import extract_insight
        from .core.memory import EpisodeLog as _EL, KnowledgeStore

        log_dir = MOLTBOOK_DATA_DIR / "logs"
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=SKILLS_DIR,
            dry_run=args.dry_run,
            episode_log=_EL(log_dir=log_dir),
            full=args.full,
        )
        print(result)
        return

    if args.command == "report":
        from .core.memory import EpisodeLog
        from .core.metrics import compute_metrics, format_report

        log_dir = MOLTBOOK_DATA_DIR / "logs"
        episode_log = EpisodeLog(log_dir=log_dir)
        report = compute_metrics(episode_log, days=args.days)
        print(format_report(report, fmt=args.format))
        return

    if args.command == "generate-report":
        from .core.report import generate_all_reports, generate_report

        log_dir = MOLTBOOK_DATA_DIR / "logs"
        project_root = Path(__file__).resolve().parents[2]
        output_dir = project_root / "reports" / "comment-reports"

        if args.all_dates:
            results = generate_all_reports(log_dir, output_dir)
            print(f"Generated {len(results)} reports in {output_dir}")
        else:
            result = generate_report(log_dir, output_dir, date=args.date)
            if result:
                print(f"Report generated: {result}")
            else:
                print("No log data found for the specified date.")
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
        dc = domain_config or get_domain_config()
        session_meta = {
            "rules_dir": str(args.rules_dir or DEFAULT_RULES_DIR),
            "axioms_enabled": not args.no_axioms,
            "domain": dc.name,
            "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen3.5:9b"),
        }
        agent.run_session(duration_minutes=args.session, session_meta=session_meta)

    elif args.command == "solve":
        agent.do_solve(args.text)


if __name__ == "__main__":
    main()
