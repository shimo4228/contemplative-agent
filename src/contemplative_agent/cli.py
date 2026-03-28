"""CLI entry point for the Contemplative Agent."""

import argparse
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from .adapters.moltbook.agent import Agent, AutonomyLevel
from .adapters.moltbook.config import (
    CONSTITUTION_DIR,
    IDENTITY_PATH,
    KNOWLEDGE_PATH,
    MEDITATION_DIR,
    MOLTBOOK_DATA_DIR,
    REPORTS_DIR,
    RULES_DIR,
    SKILLS_DIR,
)
from .core.domain import (
    get_domain_config,
    load_constitution,
    load_domain_config,
    reset_caches,
    set_domain_config_cache,
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
    print(f"Schedule: daily at {distill_hour:02d}:00 (distill --days 1)")


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


_APPROVAL_GATE_COMMANDS = frozenset({
    "insight", "rules-distill", "distill-identity", "amend-constitution",
})


def _approve_write(path: Path) -> bool:
    """Prompt user for write approval. Default is N (safe side)."""
    print(f"\nWrite to {path}? [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _is_dry_run(args: argparse.Namespace) -> bool:
    """Check if --dry-run was passed."""
    return getattr(args, "dry_run", False)


def _warn_dry_run_deprecated(args: argparse.Namespace) -> None:
    """Print deprecation warning if --dry-run is used on approval-gated commands."""
    if not _is_dry_run(args):
        return
    if getattr(args, "command", "") not in _APPROVAL_GATE_COMMANDS:
        return
    print(
        "Warning: --dry-run is deprecated for this command. "
        "The approval gate now serves the same purpose — "
        "reject at the prompt to discard.",
        file=sys.stderr,
    )


def _run_sync() -> None:
    """Run research data sync script (best-effort)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "sync-research-data.sh"
    if not script.exists():
        return
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        if result.stdout.strip():
            print(result.stdout.strip())
    else:
        print(f"Warning: sync failed: {result.stderr.strip()}", file=sys.stderr)


def _do_init() -> None:
    """Initialize runtime data files in MOLTBOOK_HOME."""
    import shutil

    MOLTBOOK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[2]
    templates_dir = project_root / "config" / "templates"

    if IDENTITY_PATH.exists():
        print(f"Identity file already exists: {IDENTITY_PATH}")
    else:
        IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        IDENTITY_PATH.write_text("\n", encoding="utf-8")
        os.chmod(IDENTITY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created identity file: {IDENTITY_PATH}")
        print(f"Tip: copy a template from {templates_dir}/ to seed your identity")

    if KNOWLEDGE_PATH.exists():
        print(f"Knowledge file already exists: {KNOWLEDGE_PATH}")
    else:
        import json as _json
        KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_PATH.write_text(_json.dumps([], ensure_ascii=False) + "\n", encoding="utf-8")
        os.chmod(KNOWLEDGE_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created knowledge file: {KNOWLEDGE_PATH}")

    # Copy default constitution if not already present
    src_constitution = templates_dir / "constitution"
    if CONSTITUTION_DIR.exists():
        print(f"Constitution already exists: {CONSTITUTION_DIR}")
    elif src_constitution.is_dir():
        shutil.copytree(src_constitution, CONSTITUTION_DIR)
        print(f"Copied default constitution: {CONSTITUTION_DIR}")
    else:
        CONSTITUTION_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created empty constitution dir: {CONSTITUTION_DIR}")


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
        "--file", type=Path, nargs="+", dest="log_files",
        help="Explicit JSONL log file(s) to process (overrides --days)"
    )

    # distill-identity
    distill_id_parser = subparsers.add_parser(
        "distill-identity", help="Distill knowledge into identity (without pattern distillation)"
    )
    distill_id_parser.add_argument(
        "--dry-run", action="store_true", help="[deprecated] Show results without writing (use approval gate instead)"
    )

    # rules-distill
    rules_distill_parser = subparsers.add_parser(
        "rules-distill", help="Distill universal behavioral rules from skill files"
    )
    rules_distill_parser.add_argument(
        "--dry-run", action="store_true", help="[deprecated] Show results without writing (use approval gate instead)"
    )
    rules_distill_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (not just new ones)"
    )

    # amend-constitution
    amend_parser = subparsers.add_parser(
        "amend-constitution", help="Propose amendments to the constitution from accumulated ethical experience"
    )
    amend_parser.add_argument(
        "--dry-run", action="store_true", help="[deprecated] Show proposed amendments without writing (use approval gate instead)"
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
        "--dry-run", action="store_true", help="[deprecated] Show result without writing (use approval gate instead)"
    )
    insight_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
    )

    # meditate
    meditate_parser = subparsers.add_parser(
        "meditate", help="Run active inference meditation on episode history"
    )
    meditate_parser.add_argument(
        "--days", type=int, default=7,
        help="Days of episodes to build POMDP from (default: 7)",
    )
    meditate_parser.add_argument(
        "--cycles", type=int, default=50,
        help="Number of meditation cycles (default: 50)",
    )
    meditate_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show results without writing to knowledge store",
    )

    # sync-data
    subparsers.add_parser("sync-data", help="Sync research data to external git repository")

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

    if args.command == "sync-data":
        _run_sync()
        return

    # Load domain config if custom path specified
    domain_config = None
    if args.domain_config is not None:
        reset_caches()
        domain_config = load_domain_config(args.domain_config)
        set_domain_config_cache(domain_config)

    # Load and inject CCAI constitutional clauses unless --no-axioms is set
    if not args.no_axioms:
        clauses = load_constitution(args.constitution_dir or CONSTITUTION_DIR)
        if clauses:
            configure_llm(axiom_prompt=clauses)

    # Inject learned skills and rules into system prompt
    skills_dir = SKILLS_DIR
    if skills_dir.is_dir():
        configure_llm(skills_dir=skills_dir)
    if RULES_DIR.is_dir():
        configure_llm(rules_dir=RULES_DIR)

    if args.command == "init":
        _do_init()
        return

    if args.command == "distill":
        from .core.distill import distill
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
        return

    if args.command == "distill-identity":
        from .core.distill import distill_identity
        from .core.memory import KnowledgeStore

        _warn_dry_run_deprecated(args)
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        result = distill_identity(
            knowledge_store=knowledge_store,
            identity_path=IDENTITY_PATH,
        )
        if isinstance(result, str):
            print(result)
            return
        print(result.text)
        if _is_dry_run(args) or not _approve_write(result.target_path):
            if not _is_dry_run(args):
                print("Discarded.")
            return
        result.target_path.write_text(result.text + "\n", encoding="utf-8")
        os.chmod(result.target_path, stat.S_IRUSR | stat.S_IWUSR)
        return

    if args.command == "insight":
        from .core._io import write_restricted
        from .core.insight import _write_last_insight, extract_insight
        from .core.memory import EpisodeLog as _EL, KnowledgeStore

        _warn_dry_run_deprecated(args)
        log_dir = MOLTBOOK_DATA_DIR / "logs"
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=SKILLS_DIR,
            episode_log=_EL(log_dir=log_dir),
            full=args.full,
        )
        if isinstance(result, str):
            print(result)
            return
        written = 0
        for i, skill in enumerate(result.skills, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(result.skills)}] {skill.filename}")
            print(skill.text)
            if not _is_dry_run(args) and _approve_write(skill.target_path):
                SKILLS_DIR.mkdir(parents=True, exist_ok=True)
                write_restricted(skill.target_path, skill.text)
                written += 1
            elif not _is_dry_run(args):
                print("Skipped.")
        if written > 0:
            _write_last_insight(SKILLS_DIR)
        print(f"\n--- Summary: {written} written, {len(result.skills) - written} skipped, {result.dropped_count} dropped ---")
        return

    if args.command == "rules-distill":
        from .core._io import write_restricted
        from .core.rules_distill import _write_last_run, distill_rules

        _warn_dry_run_deprecated(args)
        result = distill_rules(
            skills_dir=SKILLS_DIR,
            rules_dir=RULES_DIR,
            full=args.full,
        )
        if isinstance(result, str):
            print(result)
            return
        written = 0
        for i, rule in enumerate(result.rules, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(result.rules)}] {rule.filename}")
            print(rule.text)
            if not _is_dry_run(args) and _approve_write(rule.target_path):
                RULES_DIR.mkdir(parents=True, exist_ok=True)
                write_restricted(rule.target_path, rule.text)
                written += 1
            elif not _is_dry_run(args):
                print("Skipped.")
        if written > 0:
            _write_last_run(RULES_DIR)
        print(f"\n--- Summary: {written} written, {len(result.rules) - written} skipped, {result.dropped_count} dropped ---")
        return

    if args.command == "amend-constitution":
        from .core.constitution import amend_constitution
        from .core.memory import KnowledgeStore

        _warn_dry_run_deprecated(args)
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        constitution_dir = args.constitution_dir or CONSTITUTION_DIR
        result = amend_constitution(
            knowledge_store=knowledge_store,
            constitution_dir=constitution_dir,
        )
        if isinstance(result, str):
            print(result)
            return
        print(result.text)
        if _is_dry_run(args) or not _approve_write(result.target_path):
            if not _is_dry_run(args):
                print("Discarded.")
            return
        from datetime import datetime, timezone
        result.target_path.write_text(result.text + "\n", encoding="utf-8")
        os.chmod(result.target_path, stat.S_IRUSR | stat.S_IWUSR)
        marker = result.marker_dir / ".last_constitution_amend"
        marker.write_text(
            datetime.now(timezone.utc).isoformat(timespec="minutes") + "\n",
            encoding="utf-8",
        )
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
        output_dir = REPORTS_DIR

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

    if args.command == "meditate":
        from .adapters.meditation.config import MeditationConfig
        from .adapters.meditation.meditate import meditate as run_meditate
        from .adapters.meditation.pomdp import build_matrices
        from .adapters.meditation.report import interpret_and_save
        from .core.memory import EpisodeLog

        log_dir = MOLTBOOK_DATA_DIR / "logs"
        episode_log = EpisodeLog(log_dir=log_dir)
        results_path = MEDITATION_DIR / "results.json"

        config = MeditationConfig(meditation_cycles=args.cycles)
        matrices = build_matrices(episode_log, days=args.days, config=config)
        result = run_meditate(matrices, config=config)
        output = interpret_and_save(
            result, results_path, dry_run=args.dry_run,
        )
        print(output)
        return

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
        session_meta = {
            "axioms_enabled": not args.no_axioms,
            "domain": dc.name,
            "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen3.5:9b"),
        }
        agent.run_session(duration_minutes=args.session, session_meta=session_meta)

    elif args.command == "solve":
        agent.do_solve(args.text)


if __name__ == "__main__":
    main()
