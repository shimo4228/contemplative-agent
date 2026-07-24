"""launchd schedule management (install / uninstall / stale-job cleanup).

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from ..adapters.moltbook import config
from . import runtime
from .registry import CommandSpec, Tier

logger = logging.getLogger(__name__)


LAUNCHD_LABEL = "com.moltbook.agent"


LAUNCHD_DISTILL_LABEL = "com.moltbook.distill"


LAUNCHD_WEEKLY_ANALYSIS_LABEL = "com.moltbook.weekly-analysis"


LAUNCHD_INSIGHT_LABEL = "com.moltbook.insight"


LAUNCHD_BACKUP_LABEL = "com.moltbook.backup"


LAUNCHD_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


LAUNCHD_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_LABEL}.plist"


LAUNCHD_DISTILL_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_DISTILL_LABEL}.plist"


LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_WEEKLY_ANALYSIS_LABEL}.plist"


LAUNCHD_INSIGHT_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_INSIGHT_LABEL}.plist"


LAUNCHD_BACKUP_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_BACKUP_LABEL}.plist"


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
    project_root = runtime._repo_root()
    template_path = project_root / "config" / "launchd" / template_name

    if not template_path.exists():
        print(f"Error: Template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    venv_bin = project_root / ".venv" / "bin"
    if not venv_bin.exists():
        print(f"Error: venv not found: {venv_bin}", file=sys.stderr)
        sys.exit(1)

    log_path = config.MOLTBOOK_DATA_DIR / "logs" / log_name
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

    # ADR-0081 rollout: launchd does not inherit shell exports, so the
    # enforcement flag must be baked into the plist's EnvironmentVariables
    # at install time. Re-run install-schedule with the flag exported to
    # turn enforcement on for the production schedule (and without it to
    # turn it back off).
    enforce_env = ""
    if os.environ.get("MOLTBOOK_SKILL_SELECTION_ENFORCE") == "1":
        enforce_env = "\n\t\t<key>MOLTBOOK_SKILL_SELECTION_ENFORCE</key>\n\t\t<string>1</string>"

    log_path = _install_plist(
        template_name="com.moltbook.agent.plist",
        plist_path=LAUNCHD_PLIST_PATH,
        log_name="agent-launchd.log",
        substitutions={
            "{{SESSION_MINUTES}}": str(session),
            "{{CALENDAR_INTERVALS}}": _build_calendar_intervals(interval),
            "{{ENFORCE_ENV}}": enforce_env,
        },
    )

    hours = list(range(0, 24, interval))
    schedule_str = ", ".join(f"{h:02d}:00" for h in hours)
    print(f"Installed: {LAUNCHD_PLIST_PATH}")
    print(f"Schedule: every {interval}h ({schedule_str}), {session}min sessions")
    if enforce_env:
        print("Skill-selection enforcement: ON (ADR-0081 two-pass injection)")
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
    # :30 — the template offsets distill from the agent's HH:00 (audit M5).
    print(f"Schedule: daily at {distill_hour:02d}:30 (distill --days 1)")


def _do_install_weekly_analysis_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for weekly analysis report (macOS only)."""
    _install_plist(
        template_name="com.moltbook.weekly-analysis.plist",
        plist_path=LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH,
        log_name="weekly-analysis-launchd.log",
        substitutions={
            "{{WEEKDAY}}": str(weekday),
            "{{HOUR}}": str(hour),
        },
    )

    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    print(f"Installed: {LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH}")
    print(f"Schedule: {day_names[weekday]} at {hour:02d}:00 (weekly analysis)")


def _do_install_insight_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for weekly staged insight (ADR-0074, macOS only).

    Runs ``insight --stage``: candidates land in staging for later human
    review via ``adopt-staged``. The pending guard makes a skipped review
    week a no-op run, and the marker keeps windows disjoint, so the job is
    safe to fire unattended.
    """
    _install_plist(
        template_name="com.moltbook.insight.plist",
        plist_path=LAUNCHD_INSIGHT_PLIST_PATH,
        log_name="insight-launchd.log",
        substitutions={
            "{{WEEKDAY}}": str(weekday),
            "{{HOUR}}": str(hour),
        },
    )

    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    print(f"Installed: {LAUNCHD_INSIGHT_PLIST_PATH}")
    print(f"Schedule: {day_names[weekday]} at {hour:02d}:00 (weekly staged insight)")


def _do_install_backup_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for the weekly runtime backup (macOS only).

    Runs ``scripts/backup-runtime.sh``: a near-complete rsync mirror of
    MOLTBOOK_HOME (including logs/, which sync-data deliberately excludes
    from the public data repo) committed and pushed to a PRIVATE
    disaster-recovery repo. Failures write ERROR lines to the launchd log,
    which the weekly log-anomaly sweep scans.
    """
    _install_plist(
        template_name="com.moltbook.backup.plist",
        plist_path=LAUNCHD_BACKUP_PLIST_PATH,
        log_name="backup-launchd.log",
        substitutions={
            "{{WEEKDAY}}": str(weekday),
            "{{HOUR}}": str(hour),
        },
    )

    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    print(f"Installed: {LAUNCHD_BACKUP_PLIST_PATH}")
    print(f"Schedule: {day_names[weekday]} at {hour:02d}:00 (weekly runtime backup)")


def _unload_and_remove_plist(plist_path: Path, label: str) -> bool:
    """Unload and delete one launchd plist; True when a file was removed."""
    if not plist_path.exists():
        return False
    result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Warning: launchctl unload ({label}): {result.stderr.strip()}", file=sys.stderr)
    plist_path.unlink()
    print(f"Removed: {plist_path}")
    return True


def _do_uninstall_schedule() -> None:
    """Uninstall launchd plists (session + distill + weekly-analysis + insight + backup)."""
    removed = False

    for plist_path, label in [
        (LAUNCHD_PLIST_PATH, "session"),
        (LAUNCHD_DISTILL_PLIST_PATH, "distill"),
        (LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH, "weekly-analysis"),
        (LAUNCHD_INSIGHT_PLIST_PATH, "insight"),
        (LAUNCHD_BACKUP_PLIST_PATH, "backup"),
    ]:
        removed = _unload_and_remove_plist(plist_path, label) or removed

    if not removed:
        print("No schedule installed.")


def _remove_stale_schedule_jobs(
    *, distill: bool, weekly_analysis: bool, weekly_insight: bool, weekly_backup: bool
) -> None:
    """Remove previously-installed optional jobs whose flag is off this run.

    ``install-schedule`` is declarative over the full schedule set (round-2
    R2-M1): re-running with ``--no-distill`` previously left an earlier
    com.moltbook.distill job loaded on its stale schedule indefinitely, with
    no warning — same for a dropped ``--weekly-analysis`` / ``--weekly-insight``
    / ``--weekly-backup``. The always-on session job needs no reconcile
    (reinstall overwrites it in place).
    """
    if not distill and _unload_and_remove_plist(LAUNCHD_DISTILL_PLIST_PATH, "distill"):
        print("  (stale distill schedule removed: --no-distill on this run)")
    if not weekly_analysis and _unload_and_remove_plist(
        LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH, "weekly-analysis"
    ):
        print("  (stale weekly-analysis schedule removed: flag not set on this run)")
    if not weekly_insight and _unload_and_remove_plist(LAUNCHD_INSIGHT_PLIST_PATH, "insight"):
        print("  (stale insight schedule removed: flag not set on this run)")
    if not weekly_backup and _unload_and_remove_plist(LAUNCHD_BACKUP_PLIST_PATH, "backup"):
        print("  (stale backup schedule removed: flag not set on this run)")


def _handle_install_schedule(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.uninstall:
        _do_uninstall_schedule()
    else:
        # Validate ALL arguments before installing ANY schedule (bug-audit
        # 2026-07-06 M9): a late parser.error() previously fired after the
        # session + distill launchd jobs were already loaded, so the user saw
        # only a usage error while two schedules were in fact live.
        if args.interval < 1 or args.interval > 24 or 24 % args.interval != 0:
            parser.error("--interval must evenly divide 24 (1, 2, 3, 4, 6, 8, 12, 24)")
        if args.session < 1 or args.session > 1440:
            parser.error("--session must be between 1 and 1440 minutes")
        if args.distill_hour < 0 or args.distill_hour > 23:
            parser.error("--distill-hour must be between 0 and 23")
        if args.weekly_analysis:
            if args.weekly_analysis_day < 0 or args.weekly_analysis_day > 6:
                parser.error("--weekly-analysis-day must be 0 (Sun) to 6 (Sat)")
            if args.weekly_analysis_hour < 0 or args.weekly_analysis_hour > 23:
                parser.error("--weekly-analysis-hour must be between 0 and 23")
        if args.weekly_insight:
            if args.weekly_insight_day < 0 or args.weekly_insight_day > 6:
                parser.error("--weekly-insight-day must be 0 (Sun) to 6 (Sat)")
            if args.weekly_insight_hour < 0 or args.weekly_insight_hour > 23:
                parser.error("--weekly-insight-hour must be between 0 and 23")
        if args.weekly_backup:
            if args.weekly_backup_day < 0 or args.weekly_backup_day > 6:
                parser.error("--weekly-backup-day must be 0 (Sun) to 6 (Sat)")
            if args.weekly_backup_hour < 0 or args.weekly_backup_hour > 23:
                parser.error("--weekly-backup-hour must be between 0 and 23")
        # Reconcile before installing (round-2 R2-M1): drop optional jobs
        # from a previous install whose flag is off this run, so the command
        # describes the complete desired schedule set.
        _remove_stale_schedule_jobs(
            distill=not args.no_distill,
            weekly_analysis=args.weekly_analysis,
            weekly_insight=args.weekly_insight,
            weekly_backup=args.weekly_backup,
        )
        _do_install_schedule(interval=args.interval, session=args.session)
        if not args.no_distill:
            _do_install_distill_schedule(distill_hour=args.distill_hour)
        if args.weekly_analysis:
            _do_install_weekly_analysis_schedule(
                weekday=args.weekly_analysis_day,
                hour=args.weekly_analysis_hour,
            )
        if args.weekly_insight:
            _do_install_insight_schedule(
                weekday=args.weekly_insight_day,
                hour=args.weekly_insight_hour,
            )
        if args.weekly_backup:
            _do_install_backup_schedule(
                weekday=args.weekly_backup_day,
                hour=args.weekly_backup_hour,
            )


def _add_install_schedule_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interval",
        type=int,
        default=6,
        help="Hours between sessions (default: 6)",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes (default: 60)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed schedule",
    )
    parser.add_argument(
        "--no-distill",
        action="store_true",
        help="Skip installing daily distillation schedule",
    )
    parser.add_argument(
        "--distill-hour",
        type=int,
        default=3,
        help="Hour to run daily distillation (0-23, default: 3)",
    )
    parser.add_argument(
        "--weekly-analysis",
        action="store_true",
        help="Also install weekly analysis report schedule",
    )
    parser.add_argument(
        "--weekly-analysis-day",
        type=int,
        default=1,
        help="Day of week for weekly analysis (0=Sun..6=Sat, default: 1=Mon)",
    )
    parser.add_argument(
        "--weekly-analysis-hour",
        type=int,
        default=9,
        help="Hour to run weekly analysis (0-23, default: 9)",
    )
    parser.add_argument(
        "--weekly-insight",
        action="store_true",
        help="Also install weekly staged insight schedule (ADR-0074)",
    )
    parser.add_argument(
        "--weekly-insight-day",
        type=int,
        default=1,
        help="Day of week for weekly insight (0=Sun..6=Sat, default: 1=Mon)",
    )
    parser.add_argument(
        "--weekly-insight-hour",
        type=int,
        default=8,
        help=(
            "Hour to run weekly insight (0-23, default: 8 — one hour before "
            "weekly analysis, outside agent-session hours)"
        ),
    )
    parser.add_argument(
        "--weekly-backup",
        action="store_true",
        help="Also install weekly runtime backup schedule (private off-site mirror)",
    )
    parser.add_argument(
        "--weekly-backup-day",
        type=int,
        default=1,
        help="Day of week for weekly backup (0=Sun..6=Sat, default: 1=Mon)",
    )
    parser.add_argument(
        "--weekly-backup-hour",
        type=int,
        default=10,
        help="Hour to run weekly backup (0-23, default: 10 — outside agent-session hours)",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="install-schedule",
        help="Install/uninstall launchd schedule for periodic sessions",
        handler=_handle_install_schedule,
        tier=Tier.NO_LLM,
        add_arguments=_add_install_schedule_arguments,
    ),
)
