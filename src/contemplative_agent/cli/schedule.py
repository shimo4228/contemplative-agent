"""launchd schedule management (install / uninstall / stale-job cleanup).

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from ..adapters.moltbook import config
from ..core._io import write_restricted
from . import runtime
from .registry import CommandSpec, Tier

logger = logging.getLogger(__name__)


LAUNCHD_LABEL = "com.moltbook.agent"


LAUNCHD_DISTILL_LABEL = "com.moltbook.distill"


LAUNCHD_INSIGHT_LABEL = "com.moltbook.insight"


LAUNCHD_BACKUP_LABEL = "com.moltbook.backup"


LAUNCHD_WEEKLY_PIPELINE_LABEL = "com.moltbook.weekly-pipeline"


LAUNCHD_WATCHDOG_LABEL = "com.moltbook.watchdog"

# ADR-0086: weekly read-only submolt-scope sweep.
LAUNCHD_SUBMOLT_SCAN_LABEL = "com.moltbook.submolt-scan"


LAUNCHD_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


LAUNCHD_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_LABEL}.plist"


LAUNCHD_DISTILL_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_DISTILL_LABEL}.plist"


LAUNCHD_INSIGHT_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_INSIGHT_LABEL}.plist"


LAUNCHD_BACKUP_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_BACKUP_LABEL}.plist"


LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_WEEKLY_PIPELINE_LABEL}.plist"


LAUNCHD_WATCHDOG_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_WATCHDOG_LABEL}.plist"
LAUNCHD_SUBMOLT_SCAN_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_SUBMOLT_SCAN_LABEL}.plist"


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


# launchd weekday numbering (0 = Sunday), for the confirmation lines the four
# weekly installers print.
_DAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


@dataclass(frozen=True)
class _OptionalJob:
    """One optional launchd job, declared once instead of in six parallel lists.

    ``plist_attr`` / ``installer_attr`` are module attribute *names*, not the
    objects themselves: tests monkeypatch both the ``LAUNCHD_*_PLIST_PATH``
    constants (``plist_sandbox``, the guard for the Apr 8 / Jul 9 live-plist
    deletions) and the individual ``_do_install_*`` functions, so both have to
    be resolved at call time to stay patchable.

    ``day_attr`` is empty for the two jobs whose schedule is not an
    operator-chosen weekday/hour pair (distill is daily, watchdog's check
    times are anchored to the other jobs' deadlines inside its template);
    those are the jobs the weekly walkers skip.
    """

    label: str
    plist_attr: str
    stale_reason: str
    description: str = ""
    installer_attr: str = ""
    flag_attr: str = ""
    day_attr: str = ""
    hour_attr: str = ""
    day_flag: str = ""
    hour_flag: str = ""

    @property
    def template_name(self) -> str:
        """``config/launchd/`` template — named after the launchd label."""
        return f"com.moltbook.{self.label}.plist"

    @property
    def log_name(self) -> str:
        return f"{self.label}-launchd.log"


# Declaration order is the order the walkers print in: uninstall and stale
# cleanup walk this tuple, install and validation walk the weekly subset.
_OPTIONAL_JOBS: tuple[_OptionalJob, ...] = (
    _OptionalJob(
        label="distill",
        plist_attr="LAUNCHD_DISTILL_PLIST_PATH",
        stale_reason="--no-distill on this run",
    ),
    _OptionalJob(
        label="insight",
        plist_attr="LAUNCHD_INSIGHT_PLIST_PATH",
        stale_reason="flag not set on this run",
        description="weekly staged insight",
        installer_attr="_do_install_insight_schedule",
        flag_attr="weekly_insight",
        day_attr="weekly_insight_day",
        hour_attr="weekly_insight_hour",
        day_flag="--weekly-insight-day",
        hour_flag="--weekly-insight-hour",
    ),
    _OptionalJob(
        label="backup",
        plist_attr="LAUNCHD_BACKUP_PLIST_PATH",
        stale_reason="flag not set on this run",
        description="weekly runtime backup",
        installer_attr="_do_install_backup_schedule",
        flag_attr="weekly_backup",
        day_attr="weekly_backup_day",
        hour_attr="weekly_backup_hour",
        day_flag="--weekly-backup-day",
        hour_flag="--weekly-backup-hour",
    ),
    _OptionalJob(
        label="weekly-pipeline",
        plist_attr="LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH",
        stale_reason="flag not set on this run",
        description="weekly unattended chain",
        installer_attr="_do_install_weekly_pipeline_schedule",
        flag_attr="weekly_pipeline",
        day_attr="weekly_pipeline_day",
        hour_attr="weekly_pipeline_hour",
        day_flag="--weekly-pipeline-day",
        hour_flag="--weekly-pipeline-hour",
    ),
    _OptionalJob(
        label="watchdog",
        plist_attr="LAUNCHD_WATCHDOG_PLIST_PATH",
        stale_reason="flag not set on this run",
    ),
    _OptionalJob(
        label="submolt-scan",
        plist_attr="LAUNCHD_SUBMOLT_SCAN_PLIST_PATH",
        stale_reason="flag not set on this run",
        description="weekly submolt-scope sweep",
        installer_attr="_do_install_submolt_scan_schedule",
        flag_attr="weekly_submolt_scan",
        day_attr="weekly_submolt_scan_day",
        hour_attr="weekly_submolt_scan_hour",
        day_flag="--weekly-submolt-scan-day",
        hour_flag="--weekly-submolt-scan-hour",
    ),
)

_WEEKLY_JOBS: tuple[_OptionalJob, ...] = tuple(j for j in _OPTIONAL_JOBS if j.day_attr)


def _job_plist(job: _OptionalJob) -> Path:
    """Resolve a job's plist path by attribute name, so patches still apply."""
    return globals()[job.plist_attr]


def _job_installer(job: _OptionalJob) -> Callable[..., None]:
    """Resolve a job's installer by attribute name, so patches still apply."""
    return globals()[job.installer_attr]


def _job_by_label(label: str) -> _OptionalJob:
    return next(job for job in _OPTIONAL_JOBS if job.label == label)


def _launchctl_unload(plist_path: Path, label: str | None = None) -> None:
    """Unload one plist, warning (not failing) on a non-zero return.

    Both callers — reinstall and uninstall — want the same disposition: a job
    that was not loaded is not an error, and a real failure must be visible.
    """
    result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        where = f" ({label})" if label else ""
        print(f"Warning: launchctl unload{where}: {result.stderr.strip()}", file=sys.stderr)


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
        runtime._exit_with(f"Error: Template not found: {template_path}")

    venv_bin = project_root / ".venv" / "bin"
    if not venv_bin.exists():
        runtime._exit_with(f"Error: venv not found: {venv_bin}")

    log_path = config.MOLTBOOK_DATA_DIR / "logs" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)

    template = template_path.read_text(encoding="utf-8")
    plist_content = template
    for key, value in {
        "{{VENV_BIN}}": xml_escape(str(venv_bin)),
        # Claude Code's native installer lands in ~/.local/bin, which launchd's
        # PATH does not cover by default. Jobs that shell out to `claude` need
        # it explicitly or they die with "command not found" (2026-07-25).
        "{{USER_LOCAL_BIN}}": xml_escape(str(Path.home() / ".local" / "bin")),
        "{{PROJECT_ROOT}}": xml_escape(str(project_root)),
        "{{LOG_PATH}}": xml_escape(str(log_path)),
        **substitutions,
    }.items():
        plist_content = plist_content.replace(key, value)

    LAUNCHD_PLIST_DIR.mkdir(parents=True, exist_ok=True)

    if plist_path.exists():
        _launchctl_unload(plist_path)

    write_restricted(plist_path, plist_content)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        runtime._exit_with(f"Error: launchctl load failed: {result.stderr}")

    return log_path


def _install_weekly_job(
    job: _OptionalJob,
    weekday: int,
    hour: int,
    extra_substitutions: dict[str, str] | None = None,
) -> None:
    """Render + load one weekday/hour job and print its two confirmation lines.

    The four weekly installers differed only in template name, log name and
    the description in the schedule line; those now live in _OPTIONAL_JOBS.
    """
    _install_plist(
        template_name=job.template_name,
        plist_path=_job_plist(job),
        log_name=job.log_name,
        substitutions={
            "{{WEEKDAY}}": str(weekday),
            "{{HOUR}}": str(hour),
            **(extra_substitutions or {}),
        },
    )

    print(f"Installed: {_job_plist(job)}")
    print(f"Schedule: {_DAY_NAMES[weekday]} at {hour:02d}:00 ({job.description})")


def _do_install_schedule(interval: int, session: int) -> None:
    """Install launchd plist for periodic agent sessions (macOS only)."""
    if sys.platform != "darwin":
        print("Error: install-schedule is only supported on macOS (launchd).", file=sys.stderr)
        sys.exit(1)

    # The ADR-0081 rollout flag used to be baked into the plist's
    # EnvironmentVariables here, because launchd does not inherit shell
    # exports. That made a plain re-run of install-schedule drop enforcement
    # silently — no error, no log line — which is why the live plist had to
    # be diffed by hand on 2026-07-25. The flag retired on 2026-08-08 with
    # the rollout, so there is nothing to propagate and nothing to lose.
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
    print("Skill-selection: ADR-0081 two-pass injection (unconditional)")
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


def _do_install_insight_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for weekly staged insight (ADR-0074, macOS only).

    Runs ``insight --stage``: candidates land in staging for later human
    review via ``adopt-staged``. The pending guard makes a skipped review
    week a no-op run, and the marker keeps windows disjoint, so the job is
    safe to fire unattended.
    """
    _install_weekly_job(_job_by_label("insight"), weekday, hour)


def _do_install_submolt_scan_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for the weekly submolt-scope sweep (ADR-0086).

    Runs ``submolt-scan``: read-only sampling and scoring across every listed
    submolt, subscribed or not. It writes only its own audit log and takes the
    run lock, so an unattended firing cannot disturb a session — the reason it
    is a job of its own rather than a stage inside one.
    """
    _install_weekly_job(_job_by_label("submolt-scan"), weekday, hour)


def _do_install_backup_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for the weekly runtime backup (macOS only).

    Runs ``scripts/backup-runtime.sh``: a near-complete rsync mirror of
    MOLTBOOK_HOME (including logs/, which sync-data deliberately excludes
    from the public data repo) committed and pushed to a PRIVATE
    disaster-recovery repo. Failures write ERROR lines to the launchd log,
    which the weekly log-anomaly sweep scans.
    """
    _install_weekly_job(_job_by_label("backup"), weekday, hour)


def _do_install_weekly_pipeline_schedule(weekday: int, hour: int) -> None:
    """Install launchd plist for the unattended weekly chain (ADR-0085).

    Runs ``scripts/weekly-pipeline.sh`` (ADR-0098 single-session form):
    materials → one ``/weekly-report`` session (A-E synthesis + diagnosis +
    candidate filing into the task ledger) → value-layer due check
    (ADR-0091) → dead-code scan → docs-consistency scan → never-selected
    reading. It replaced the standalone ``--weekly-analysis`` install path,
    removed 2026-08-29; the chain runs weekly-analysis.sh as its own
    materials collector. Nothing in the chain commits, adopts, or repairs —
    the Saturday ``/weekly-gate`` session and the task-triage loop hold the
    human gates.

    ADR-0085 shadow rollout: exporting ``MOLTBOOK_PIPELINE_STAGES`` in the
    installing shell bakes it into the plist (same mechanism as ADR-0081's
    enforcement flag — and with the same known sharp edge: a later re-install
    without the export silently reverts to the full chain, which here is the
    intended graduation direction).
    """
    stages_env = ""
    stages = os.environ.get("MOLTBOOK_PIPELINE_STAGES")
    if stages:
        stages_env = (
            f"\n\t\t<key>MOLTBOOK_PIPELINE_STAGES</key>\n\t\t<string>{xml_escape(stages)}</string>"
        )

    _install_weekly_job(
        _job_by_label("weekly-pipeline"),
        weekday,
        hour,
        extra_substitutions={"{{STAGES_ENV}}": stages_env},
    )

    if stages:
        print(f"Stage selection (shadow mode): {stages}")


def _do_install_watchdog_schedule() -> None:
    """Install launchd plist for the pipeline watchdog (ADR-0085).

    Runs ``scripts/pipeline_watchdog.sh``: pure-bash verification that every
    scheduled job produced its terminal artifact, written to
    ``reports/PIPELINE-STATUS.md`` plus a Notification Center alert on a
    changed failure set. The check times are fixed in the template (daily
    04:30 + Sat 12:30/13:30 + Mon 11:00) because they are anchored to the
    other jobs' deadlines, not operator preference.
    """
    _install_plist(
        template_name="com.moltbook.watchdog.plist",
        plist_path=LAUNCHD_WATCHDOG_PLIST_PATH,
        log_name="watchdog-launchd.log",
        substitutions={},
    )

    print(f"Installed: {LAUNCHD_WATCHDOG_PLIST_PATH}")
    print("Schedule: daily 04:30 + Sat 12:30/13:30 + Mon 11:00 (pipeline watchdog)")


def _unload_and_remove_plist(plist_path: Path, label: str) -> bool:
    """Unload and delete one launchd plist; True when a file was removed."""
    if not plist_path.exists():
        return False
    _launchctl_unload(plist_path, label=label)
    plist_path.unlink()
    print(f"Removed: {plist_path}")
    return True


def _do_uninstall_schedule() -> None:
    """Uninstall every launchd plist this installer manages (session + optional jobs).

    Out of scope, and left untouched: ``com.moltbook.ollama-restart`` (installed
    and updated manually) and two legacy jobs whose installers were removed, so
    they are no longer among the managed plists and must be removed by hand —
    ``com.moltbook.weekly-analysis`` (standalone installer removed 2026-08-29)
    and ``com.moltbook.wiki-maintain`` (the whole mechanism retired 2026-09-05,
    ADR-0103; never installed on the author's machine and never in a release,
    so this is a note for a checkout that ran ``--wiki-maintain`` from main).
    """
    removed = False

    for plist_path, label in [(LAUNCHD_PLIST_PATH, "session")] + [
        (_job_plist(job), job.label) for job in _OPTIONAL_JOBS
    ]:
        removed = _unload_and_remove_plist(plist_path, label) or removed

    if not removed:
        print("No schedule installed.")


def _remove_stale_schedule_jobs(
    *,
    distill: bool,
    weekly_insight: bool,
    weekly_backup: bool,
    weekly_pipeline: bool = False,
    watchdog: bool = False,
    submolt_scan: bool = False,
) -> None:
    """Remove previously-installed optional jobs whose flag is off this run.

    ``install-schedule`` is declarative over the full schedule set (round-2
    R2-M1): re-running with ``--no-distill`` previously left an earlier
    com.moltbook.distill job loaded on its stale schedule indefinitely, with
    no warning — same for a dropped ``--weekly-insight`` /
    ``--weekly-backup``. Every optional job in _OPTIONAL_JOBS is reconciled;
    the always-on session job needs none (reinstall overwrites it in place).
    """
    requested = {
        "distill": distill,
        "insight": weekly_insight,
        "backup": weekly_backup,
        "weekly-pipeline": weekly_pipeline,
        "watchdog": watchdog,
        "submolt-scan": submolt_scan,
    }
    for job in _OPTIONAL_JOBS:
        if requested[job.label]:
            continue
        if _unload_and_remove_plist(_job_plist(job), job.label):
            print(f"  (stale {job.label} schedule removed: {job.stale_reason})")


def _validate_weekday_hour_flag(
    parser: argparse.ArgumentParser,
    day: int,
    hour: int,
    day_flag: str,
    hour_flag: str,
) -> None:
    """Validate one weekday/hour flag pair shared by the weekly-* schedules.

    Split out of :func:`_validate_install_schedule_args` (behaviour-
    preserving): the day-0..6 / hour-0..23 range check and error text are
    identical across the five weekly schedules, only the flag names differ.
    """
    if day < 0 or day > 6:
        parser.error(f"{day_flag} must be 0 (Sun) to 6 (Sat)")
    if hour < 0 or hour > 23:
        parser.error(f"{hour_flag} must be between 0 and 23")


def _validate_install_schedule_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    """Validate every --install-schedule flag before any job is installed.

    Split out of :func:`_handle_install_schedule` (behaviour-preserving).
    Validate ALL arguments before installing ANY schedule (bug-audit
    2026-07-06 M9): a late parser.error() previously fired after the
    session + distill launchd jobs were already loaded, so the user saw
    only a usage error while two schedules were in fact live.
    """
    if args.interval < 1 or args.interval > 24 or 24 % args.interval != 0:
        parser.error("--interval must evenly divide 24 (1, 2, 3, 4, 6, 8, 12, 24)")
    if args.session < 1 or args.session > 1440:
        parser.error("--session must be between 1 and 1440 minutes")
    if args.distill_hour < 0 or args.distill_hour > 23:
        parser.error("--distill-hour must be between 0 and 23")
    for job in _WEEKLY_JOBS:
        if getattr(args, job.flag_attr):
            _validate_weekday_hour_flag(
                parser,
                getattr(args, job.day_attr),
                getattr(args, job.hour_attr),
                job.day_flag,
                job.hour_flag,
            )


def _dispatch_install_schedule_jobs(args: argparse.Namespace) -> None:
    """Reconcile stale jobs and install the requested schedule set.

    Split out of :func:`_handle_install_schedule` (behaviour-preserving).
    Called only after :func:`_validate_install_schedule_args` has passed.
    """
    # Reconcile before installing (round-2 R2-M1): drop optional jobs
    # from a previous install whose flag is off this run, so the command
    # describes the complete desired schedule set.
    _remove_stale_schedule_jobs(
        distill=not args.no_distill,
        weekly_insight=args.weekly_insight,
        weekly_backup=args.weekly_backup,
        weekly_pipeline=args.weekly_pipeline,
        watchdog=args.watchdog,
        submolt_scan=args.weekly_submolt_scan,
    )
    _do_install_schedule(interval=args.interval, session=args.session)
    if not args.no_distill:
        _do_install_distill_schedule(distill_hour=args.distill_hour)
    for job in _WEEKLY_JOBS:
        if getattr(args, job.flag_attr):
            _job_installer(job)(
                weekday=getattr(args, job.day_attr),
                hour=getattr(args, job.hour_attr),
            )
    if args.watchdog:
        _do_install_watchdog_schedule()


def _handle_install_schedule(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.uninstall:
        _do_uninstall_schedule()
    else:
        _validate_install_schedule_args(args, parser)
        _dispatch_install_schedule_jobs(args)


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
        "--weekly-insight",
        action="store_true",
        help="Also install weekly staged insight schedule (ADR-0074)",
    )
    parser.add_argument(
        "--weekly-insight-day",
        type=int,
        default=6,
        help=(
            "Day of week for weekly insight (0=Sun..6=Sat, default: 6=Sat — "
            "matches the watchdog's fixed Saturday anchor and the production "
            "schedule; ADR-0074's original Monday default was retired 2026-07-29)"
        ),
    )
    parser.add_argument(
        "--weekly-insight-hour",
        type=int,
        default=8,
        help=(
            "Hour to run weekly insight (0-23, default: 8 — outside "
            "agent-session hours, one hour before the weekly chain)"
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
    parser.add_argument(
        "--weekly-submolt-scan",
        action="store_true",
        help=(
            "Also install the weekly submolt-scope sweep (ADR-0086): read-only "
            "sampling and scoring across every listed submolt, subscribed or not"
        ),
    )
    parser.add_argument(
        "--weekly-submolt-scan-day",
        type=int,
        default=4,
        help="Day of week for the submolt-scope sweep (0=Sun..6=Sat, default: 4=Thu)",
    )
    parser.add_argument(
        "--weekly-submolt-scan-hour",
        type=int,
        default=3,
        help=(
            "Hour to run the submolt-scope sweep (0-23, default: 3 — between the "
            "agent-session hours, clear of the other weekly jobs)"
        ),
    )
    parser.add_argument(
        "--weekly-pipeline",
        action="store_true",
        help=(
            "Install the unattended weekly chain (ADR-0098: materials → one "
            "/weekly-report session (report + diagnosis + candidate filing) → "
            "instrument scans)."
        ),
    )
    parser.add_argument(
        "--weekly-pipeline-day",
        type=int,
        default=6,
        help="Day of week for the weekly chain (0=Sun..6=Sat, default: 6=Sat)",
    )
    parser.add_argument(
        "--weekly-pipeline-hour",
        type=int,
        default=9,
        help="Hour to run the weekly chain (0-23, default: 9)",
    )
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help=(
            "Install the pipeline watchdog (pure-bash artifact checks → "
            "reports/PIPELINE-STATUS.md + Notification Center; fixed times)"
        ),
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
